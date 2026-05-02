#!/usr/bin/env python3
"""ArcLink Telegram runtime adapter.

Provides a long-polling bot runner that connects Telegram messages to the
shared public bot turn handler. Requires TELEGRAM_BOT_TOKEN to start.
Uses fake mode (no network) when the token is absent.
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

logger = logging.getLogger("arclink.telegram")

TELEGRAM_API_BASE = "https://api.telegram.org"


class ArcLinkTelegramError(RuntimeError):
    pass


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    bot_username: str
    webhook_url: str
    api_base: str = TELEGRAM_API_BASE

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> TelegramConfig:
        e = dict(env or os.environ)
        token = str(e.get("TELEGRAM_BOT_TOKEN", "")).strip()
        username = str(e.get("TELEGRAM_BOT_USERNAME", "")).strip()
        webhook = str(e.get("TELEGRAM_WEBHOOK_URL", "")).strip()
        api_base = str(e.get("TELEGRAM_API_BASE", TELEGRAM_API_BASE)).strip()
        return cls(bot_token=token, bot_username=username, webhook_url=webhook, api_base=api_base)

    @property
    def is_live(self) -> bool:
        return bool(self.bot_token)


def _telegram_api_url(config: TelegramConfig, method: str) -> str:
    return f"{config.api_base}/bot{config.bot_token}/{method}"


def parse_telegram_update(update: Mapping[str, Any]) -> dict[str, str] | None:
    """Extract chat_id, user_id, and text from a Telegram update dict."""
    msg = update.get("message") or update.get("edited_message") or {}
    text = str(msg.get("text") or "").strip()
    chat = msg.get("chat") or {}
    user = msg.get("from") or {}
    chat_id = str(chat.get("id") or "")
    user_id = str(user.get("id") or "")
    if not chat_id or not text:
        return None
    return {"chat_id": chat_id, "user_id": user_id, "text": text}


def handle_telegram_update(
    conn: sqlite3.Connection,
    update: Mapping[str, Any],
    *,
    stripe_client: Any | None = None,
    price_id: str = "price_arclink_starter",
    base_domain: str = "",
) -> dict[str, Any] | None:
    """Process a single Telegram update through the shared bot contract.

    Returns a dict with chat_id and reply text, or None if the update
    is not a text message.
    """
    parsed = parse_telegram_update(update)
    if parsed is None:
        return None
    channel_identity = f"tg:{parsed['user_id']}" if parsed["user_id"] else f"tg:{parsed['chat_id']}"
    turn = handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity=channel_identity,
        text=parsed["text"],
        stripe_client=stripe_client,
        price_id=price_id,
        base_domain=base_domain,
    )
    return {
        "chat_id": parsed["chat_id"],
        "text": turn.reply,
        "session_id": turn.session_id,
        "action": turn.action,
    }


class LiveTelegramTransport:
    """HTTP transport calling the real Telegram Bot API."""

    def __init__(self, config: TelegramConfig) -> None:
        if not config.is_live:
            raise ArcLinkTelegramError("TELEGRAM_BOT_TOKEN is required for live transport")
        self.config = config

    def _call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        import json
        import urllib.request
        import urllib.error

        url = _telegram_api_url(self.config, method)
        data = json.dumps(params or {}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            logger.error("telegram_api_error method=%s status=%d body=%s", method, exc.code, body[:200])
            raise ArcLinkTelegramError(f"Telegram API error {exc.code}: {body[:200]}") from exc

    def send_message(self, chat_id: str, text: str) -> dict[str, Any]:
        result = self._call("sendMessage", {"chat_id": chat_id, "text": text})
        return result.get("result", {})

    def get_updates(self, offset: int = 0, timeout: int = 30) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"timeout": timeout}
        if offset:
            params["offset"] = offset
        result = self._call("getUpdates", params)
        return result.get("result", [])


class FakeTelegramTransport:
    """In-memory transport for testing without network calls."""

    def __init__(self) -> None:
        self.sent_messages: list[dict[str, Any]] = []
        self.updates_queue: list[dict[str, Any]] = []

    def send_message(self, chat_id: str, text: str) -> dict[str, Any]:
        msg = {"chat_id": chat_id, "text": text, "message_id": len(self.sent_messages) + 1}
        self.sent_messages.append(msg)
        return msg

    def get_updates(self, offset: int = 0, timeout: int = 0) -> list[dict[str, Any]]:
        updates = [u for u in self.updates_queue if u.get("update_id", 0) >= offset]
        self.updates_queue = [u for u in self.updates_queue if u.get("update_id", 0) >= offset + len(updates)]
        return updates

    def enqueue_update(self, chat_id: str, user_id: str, text: str) -> dict[str, Any]:
        update_id = len(self.sent_messages) + len(self.updates_queue) + 1
        update = {
            "update_id": update_id,
            "message": {
                "message_id": update_id,
                "chat": {"id": int(chat_id)},
                "from": {"id": int(user_id)},
                "text": text,
            },
        }
        self.updates_queue.append(update)
        return update


def run_telegram_polling(
    conn: sqlite3.Connection,
    config: TelegramConfig,
    *,
    transport: FakeTelegramTransport | None = None,
    stripe_client: Any | None = None,
    price_id: str = "price_arclink_starter",
    base_domain: str = "",
    max_iterations: int = 0,
) -> None:
    """Run the Telegram long-polling loop.

    In live mode, this calls the Telegram Bot API. In test mode, use a
    FakeTelegramTransport. Set max_iterations > 0 for bounded execution.
    """
    if not config.is_live and transport is None:
        raise ArcLinkTelegramError(
            "TELEGRAM_BOT_TOKEN is required for live mode; "
            "provide a FakeTelegramTransport for testing"
        )

    # Use live transport when no fake is provided
    if transport is None:
        transport = LiveTelegramTransport(config)

    offset = 0
    iterations = 0
    while max_iterations == 0 or iterations < max_iterations:
        iterations += 1
        updates = transport.get_updates(offset=offset)

        for update in updates:
            update_id = update.get("update_id", 0)
            if update_id >= offset:
                offset = update_id + 1
            try:
                result = handle_telegram_update(
                    conn, update,
                    stripe_client=stripe_client,
                    price_id=price_id,
                    base_domain=base_domain,
                )
                if result:
                    transport.send_message(result["chat_id"], result["text"])
                    logger.info("telegram_reply chat_id=%s action=%s", result["chat_id"], result["action"])
            except Exception:
                logger.exception("telegram_update_error update_id=%s", update_id)
