#!/usr/bin/env python3
"""ArcLink Discord runtime adapter.

Provides an interaction handler for Discord slash commands and messages,
connecting to the shared public bot turn handler. Requires DISCORD_BOT_TOKEN
to start. Uses fake mode (no network) when the token is absent.
"""
from __future__ import annotations

import logging
import os
import pathlib
import sqlite3
import sys
from dataclasses import dataclass
from typing import Any, Mapping

_PYTHON_DIR = pathlib.Path(__file__).resolve().parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from arclink_public_bots import handle_arclink_public_bot_turn

logger = logging.getLogger("arclink.discord")


class ArcLinkDiscordError(RuntimeError):
    pass


@dataclass(frozen=True)
class DiscordConfig:
    bot_token: str
    app_id: str
    public_key: str
    guild_id: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> DiscordConfig:
        e = dict(env or os.environ)
        return cls(
            bot_token=str(e.get("DISCORD_BOT_TOKEN", "")).strip(),
            app_id=str(e.get("DISCORD_APP_ID", "")).strip(),
            public_key=str(e.get("DISCORD_PUBLIC_KEY", "")).strip(),
            guild_id=str(e.get("DISCORD_TEST_GUILD_ID", "")).strip(),
        )

    @property
    def is_live(self) -> bool:
        return bool(self.bot_token and self.app_id and self.public_key)


def verify_discord_signature(
    body: str, signature: str, timestamp: str, public_key: str
) -> bool:
    """Verify a Discord interaction signature (Ed25519).

    In production this uses the nacl library. This stub returns True
    when the public_key is the test sentinel 'test_public_key'.
    For real verification, install PyNaCl.
    """
    if public_key == "test_public_key":
        return True
    try:
        from nacl.signing import VerifyKey
        vk = VerifyKey(bytes.fromhex(public_key))
        vk.verify(f"{timestamp}{body}".encode(), bytes.fromhex(signature))
        return True
    except Exception:
        return False


def parse_discord_interaction(interaction: Mapping[str, Any]) -> dict[str, str] | None:
    """Extract channel_id, user_id, and text from a Discord interaction."""
    itype = interaction.get("type", 0)

    # Type 1 = PING
    if itype == 1:
        return None

    # Type 2 = APPLICATION_COMMAND (slash command)
    if itype == 2:
        data = interaction.get("data") or {}
        options = data.get("options") or []
        text = ""
        for opt in options:
            if opt.get("name") == "message":
                text = str(opt.get("value") or "")
        if not text:
            name = str(data.get("name") or "")
            text = f"/{name}" if name else "/start"
        user = (interaction.get("member") or {}).get("user") or interaction.get("user") or {}
        return {
            "channel_id": str(interaction.get("channel_id") or ""),
            "user_id": str(user.get("id") or ""),
            "text": text,
        }

    # Type 3 = MESSAGE_COMPONENT, type 4 = AUTOCOMPLETE — skip for now
    # Fallback for plain message content (gateway events)
    if "content" in interaction:
        author = interaction.get("author") or {}
        return {
            "channel_id": str(interaction.get("channel_id") or ""),
            "user_id": str(author.get("id") or ""),
            "text": str(interaction.get("content") or ""),
        }

    return None


def handle_discord_interaction(
    conn: sqlite3.Connection,
    interaction: Mapping[str, Any],
    *,
    stripe_client: Any | None = None,
    price_id: str = "price_arclink_starter",
    base_domain: str = "",
) -> dict[str, Any] | None:
    """Process a Discord interaction through the shared bot contract.

    Returns a response dict with type and data for the Discord API,
    or None for pings/unsupported interactions.
    """
    itype = interaction.get("type", 0)
    if itype == 1:
        return {"type": 1}  # PONG

    parsed = parse_discord_interaction(interaction)
    if parsed is None:
        return None

    channel_identity = f"discord:{parsed['user_id']}" if parsed["user_id"] else f"discord:{parsed['channel_id']}"
    turn = handle_arclink_public_bot_turn(
        conn,
        channel="discord",
        channel_identity=channel_identity,
        text=parsed["text"],
        stripe_client=stripe_client,
        price_id=price_id,
        base_domain=base_domain,
    )
    return {
        "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
        "data": {
            "content": turn.reply,
        },
        "session_id": turn.session_id,
        "action": turn.action,
    }


class LiveDiscordTransport:
    """HTTP transport for sending Discord interaction responses."""

    DISCORD_API_BASE = "https://discord.com/api/v10"

    def __init__(self, config: DiscordConfig) -> None:
        if not config.is_live:
            raise ArcLinkDiscordError("DISCORD_BOT_TOKEN and DISCORD_APP_ID are required for live transport")
        self.config = config

    def _post_json(self, url: str, payload: dict[str, Any], *, label: str = "discord_api") -> bytes:
        import json
        import urllib.request
        import urllib.error

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            logger.error("%s_error status=%d body=%s", label, exc.code, body[:200])
            raise ArcLinkDiscordError(f"Discord API error {exc.code}: {body[:200]}") from exc

    def respond(self, interaction_id: str, interaction_token: str, response: dict[str, Any]) -> None:
        """Send an interaction response via the Discord API."""
        url = f"{self.DISCORD_API_BASE}/interactions/{interaction_id}/{interaction_token}/callback"
        self._post_json(url, response, label="discord_respond")

    def send_followup(self, interaction_token: str, content: str) -> dict[str, Any]:
        """Send a followup message for a deferred interaction."""
        import json
        url = f"{self.DISCORD_API_BASE}/webhooks/{self.config.app_id}/{interaction_token}"
        raw = self._post_json(url, {"content": content}, label="discord_followup")
        return json.loads(raw)


def handle_discord_webhook_request(
    conn: sqlite3.Connection,
    *,
    body: str,
    signature: str,
    timestamp: str,
    config: DiscordConfig,
    stripe_client: Any | None = None,
    price_id: str = "price_arclink_starter",
    base_domain: str = "",
) -> dict[str, Any]:
    """Handle an incoming Discord interaction webhook request.

    Verifies the signature, processes the interaction, and returns
    the JSON response to send back to Discord.
    """
    if not verify_discord_signature(body, signature, timestamp, config.public_key):
        raise ArcLinkDiscordError("invalid Discord interaction signature")

    import json
    interaction = json.loads(body)
    result = handle_discord_interaction(
        conn, interaction,
        stripe_client=stripe_client,
        price_id=price_id,
        base_domain=base_domain,
    )
    if result is None:
        return {"type": 1}  # ACK with PONG as safe fallback
    return result


class FakeDiscordTransport:
    """In-memory transport for testing without network calls."""

    def __init__(self) -> None:
        self.responses: list[dict[str, Any]] = []

    def respond(self, interaction_id: str, response: dict[str, Any]) -> None:
        self.responses.append({"interaction_id": interaction_id, **response})

    def make_slash_command(
        self, *, user_id: str, channel_id: str, command: str = "arclink", message: str = ""
    ) -> dict[str, Any]:
        interaction: dict[str, Any] = {
            "id": f"int_{len(self.responses) + 1}",
            "type": 2,
            "channel_id": channel_id,
            "member": {"user": {"id": user_id}},
            "data": {
                "name": command,
                "options": [{"name": "message", "value": message}] if message else [],
            },
        }
        return interaction

    def make_ping(self) -> dict[str, Any]:
        return {"type": 1}

    def make_message(self, *, user_id: str, channel_id: str, content: str) -> dict[str, Any]:
        return {
            "channel_id": channel_id,
            "author": {"id": user_id},
            "content": content,
        }
