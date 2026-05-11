#!/usr/bin/env python3
"""ArcLink Telegram runtime adapter.

Provides a long-polling bot runner that connects Telegram messages to the
shared public bot turn handler. Requires TELEGRAM_BOT_TOKEN to start.
Uses fake mode (no network) when the token is absent.
"""
from __future__ import annotations

import logging
import json
import os
import pathlib
import re
import sqlite3
import sys
import urllib.parse
from dataclasses import dataclass
from typing import Any, Mapping

_PYTHON_DIR = pathlib.Path(__file__).resolve().parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from arclink_public_bots import (
    ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES,
    arclink_public_bot_telegram_commands,
    arclink_public_bot_turn_telegram_reply_markup,
    handle_arclink_public_bot_turn,
)
from arclink_http import http_request, parse_json_object

logger = logging.getLogger("arclink.telegram")

TELEGRAM_API_BASE = "https://api.telegram.org"
ARCLINK_PUBLIC_TELEGRAM_ALLOWED_UPDATES = ("message", "edited_message", "callback_query")
ARCLINK_TELEGRAM_COMMAND_LIMIT = 100
_TELEGRAM_COMMAND_RE = re.compile(r"[^a-z0-9_]")
_TELEGRAM_MULTI_UNDERSCORE_RE = re.compile(r"_{2,}")
_TELEGRAM_CHAT_COMMAND_SCOPE_CACHE: set[tuple[str, str]] = set()

ARCLINK_TELEGRAM_AGENT_FALLBACK_COMMANDS: tuple[tuple[str, str], ...] = (
    ("new", "Agent: start a fresh session"),
    ("topic", "Agent: inspect Telegram topic sessions"),
    ("retry", "Agent: retry the last message"),
    ("undo", "Agent: remove the last exchange"),
    ("title", "Agent: set or show session title"),
    ("branch", "Agent: branch the current session"),
    ("compress", "Agent: compress conversation context"),
    ("rollback", "Agent: list or restore checkpoints"),
    ("stop", "Agent: stop the running agent"),
    ("approve", "Agent: approve a pending command"),
    ("deny", "Agent: deny a pending command"),
    ("goal", "Agent: set or inspect standing goal"),
    ("profile", "Agent: show profile and home"),
    ("sethome", "Agent: set this chat as home"),
    ("resume", "Agent: resume a named session"),
    ("model", "Agent: switch or inspect model"),
    ("provider", "Agent: alias for model/provider"),
    ("personality", "Agent: set personality"),
    ("footer", "Agent: toggle reply footer"),
    ("yolo", "Agent: toggle approval mode"),
    ("reasoning", "Agent: manage reasoning effort"),
    ("fast", "Agent: toggle fast mode"),
    ("voice", "Agent: manage voice mode"),
    ("curator", "Agent: skill maintenance"),
    ("kanban", "Agent: collaboration board"),
    ("reload_mcp", "Agent: reload MCP servers"),
    ("reload_skills", "Agent: reload skills"),
    ("restart", "Agent: restart gateway"),
    ("usage", "Agent: show token usage"),
    ("insights", "Agent: usage insights"),
    ("debug", "Agent: prepare debug report"),
)
ARCLINK_TELEGRAM_AGENT_ALIAS_COMMANDS: tuple[tuple[str, str], ...] = (
    ("provider", "Agent: alias for model/provider"),
)
ARCLINK_TELEGRAM_RAVEN_CONTROL_CANDIDATES = ("raven", "arclink", "arclink_control")
ARCLINK_TELEGRAM_RAVEN_ACTIVE_DESCRIPTION = "Raven: ArcLink controls, roster, status, and setup"
ARCLINK_TELEGRAM_POLICY_SUPPRESSED_AGENT_COMMANDS = frozenset({"update"})
ARCLINK_TELEGRAM_LEGACY_RAVEN_COMMAND_NAMES = frozenset(
    _telegram_name
    for _telegram_name in (
        "agent",
        "agents",
        "cancel",
        "checkout",
        "commands",
        "config_backup",
        "connect_notion",
        "credentials",
        "help",
        "link_channel",
        "name",
        "pair_channel",
        "plan",
        "raven_name",
        "start",
        "status",
        "upgrade_hermes",
    )
)


class ArcLinkTelegramError(RuntimeError):
    pass


def _telegram_url(bot_token: str, method: str) -> str:
    return f"{TELEGRAM_API_BASE}/bot{bot_token}/{method}"


def _request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    headers = {}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    response = http_request(
        url,
        method=method,
        headers=headers,
        json_payload=payload,
        timeout=timeout,
        allow_loopback_http=False,
    )
    try:
        payload_json = parse_json_object(response, label="telegram")
    except RuntimeError as exc:
        if response.status_code >= 400:
            raise RuntimeError(f"telegram http {response.status_code}: {response.text[:200]}") from exc
        raise
    if not payload_json.get("ok", False):
        description = str(payload_json.get("description") or "unknown telegram error")
        raise RuntimeError(description)
    result = payload_json.get("result")
    return result if isinstance(result, dict) else {"result": result}


def telegram_send_message(
    *,
    bot_token: str,
    chat_id: str,
    text: str,
    reply_to_message_id: int | None = None,
    reply_markup: dict[str, Any] | None = None,
    parse_mode: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text if len(text) <= 4000 else text[:3997] + "...",
    }
    if reply_to_message_id is not None:
        payload["reply_to_message_id"] = int(reply_to_message_id)
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    if parse_mode:
        payload["parse_mode"] = parse_mode
    return _request_json(
        _telegram_url(bot_token, "sendMessage"),
        method="POST",
        payload=payload,
        timeout=20,
    )


def telegram_answer_callback_query(
    *,
    bot_token: str,
    callback_query_id: str,
    text: str = "",
    show_alert: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "callback_query_id": callback_query_id,
        "show_alert": bool(show_alert),
    }
    if text:
        payload["text"] = text[:200]
    return _request_json(
        _telegram_url(bot_token, "answerCallbackQuery"),
        method="POST",
        payload=payload,
        timeout=20,
    )


def telegram_edit_message_reply_markup(
    *,
    bot_token: str,
    chat_id: str,
    message_id: int,
    reply_markup: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": int(message_id),
        "reply_markup": reply_markup if reply_markup is not None else {"inline_keyboard": []},
    }
    return _request_json(
        _telegram_url(bot_token, "editMessageReplyMarkup"),
        method="POST",
        payload=payload,
        timeout=20,
    )


def telegram_edit_message_text(
    *,
    bot_token: str,
    chat_id: str,
    message_id: int,
    text: str,
    reply_markup: dict[str, Any] | None = None,
    parse_mode: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": int(message_id),
        "text": text if len(text) <= 4000 else text[:3997] + "...",
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    if parse_mode:
        payload["parse_mode"] = parse_mode
    return _request_json(
        _telegram_url(bot_token, "editMessageText"),
        method="POST",
        payload=payload,
        timeout=20,
    )


def telegram_get_me(*, bot_token: str) -> dict[str, Any]:
    return _request_json(_telegram_url(bot_token, "getMe"), timeout=20)


def telegram_set_my_commands(
    *,
    bot_token: str,
    commands: list[dict[str, str]],
    scope: dict[str, Any] | None = None,
    language_code: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "commands": [
            {
                "command": str(item.get("command") or "").strip().lstrip("/"),
                "description": str(item.get("description") or "").strip(),
            }
            for item in commands
            if str(item.get("command") or "").strip() and str(item.get("description") or "").strip()
        ]
    }
    if scope is not None:
        payload["scope"] = scope
    if language_code:
        payload["language_code"] = language_code
    return _request_json(
        _telegram_url(bot_token, "setMyCommands"),
        method="POST",
        payload=payload,
        timeout=20,
    )


def telegram_get_my_commands(
    *,
    bot_token: str,
    scope: dict[str, Any] | None = None,
    language_code: str = "",
) -> list[dict[str, str]]:
    payload: dict[str, Any] = {}
    if scope is not None:
        payload["scope"] = scope
    if language_code:
        payload["language_code"] = language_code
    result = _request_json(
        _telegram_url(bot_token, "getMyCommands"),
        method="POST" if payload else "GET",
        payload=payload or None,
        timeout=20,
    )
    value = result.get("result", result)
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _telegram_command_name(raw: str) -> str:
    name = str(raw or "").strip().lower().lstrip("/").replace("-", "_")
    name = _TELEGRAM_COMMAND_RE.sub("", name)
    name = _TELEGRAM_MULTI_UNDERSCORE_RE.sub("_", name)
    return name.strip("_")[:32]


def _telegram_chat_scope(chat_id: str) -> dict[str, Any]:
    clean = str(chat_id or "").strip()
    scoped_id: int | str
    if re.fullmatch(r"-?\d+", clean):
        scoped_id = int(clean)
    else:
        scoped_id = clean
    return {"type": "chat", "chat_id": scoped_id}


def _hermes_agent_source_candidates(env: Mapping[str, str] | None = None) -> list[pathlib.Path]:
    e = dict(env or os.environ)
    raw_candidates: list[str] = []
    for key in ("ARCLINK_HERMES_AGENT_SRC", "ARCLINK_HERMES_SOURCE_DIR", "HERMES_AGENT_SRC"):
        value = str(e.get(key) or "").strip()
        if value:
            raw_candidates.append(value)
    for key in ("ARCLINK_RUNTIME_DIR", "RUNTIME_DIR"):
        value = str(e.get(key) or "").strip()
        if value:
            raw_candidates.append(str(pathlib.Path(value) / "hermes-agent-src"))
    for key in ("STATE_DIR", "ARCLINK_STATE_DIR"):
        value = str(e.get(key) or "").strip()
        if value:
            raw_candidates.append(str(pathlib.Path(value) / "runtime" / "hermes-agent-src"))
    for key in ("ARCLINK_PRIV_DIR", "CONFIG_PRIV_DIR"):
        value = str(e.get(key) or "").strip()
        if value:
            raw_candidates.append(str(pathlib.Path(value) / "state" / "runtime" / "hermes-agent-src"))
    raw_candidates.extend(
        [
            "/home/arclink/arclink/arclink-priv/state/runtime/hermes-agent-src",
            "/srv/config-priv/state/runtime/hermes-agent-src",
            "/opt/arclink/runtime/hermes-agent-src",
        ]
    )
    seen: set[str] = set()
    candidates: list[pathlib.Path] = []
    for raw in raw_candidates:
        path = pathlib.Path(raw).expanduser()
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if (path / "hermes_cli" / "commands.py").exists():
            candidates.append(path)
    return candidates


def _load_hermes_telegram_menu_commands(
    *,
    max_commands: int = ARCLINK_TELEGRAM_COMMAND_LIMIT,
    env: Mapping[str, str] | None = None,
) -> tuple[list[tuple[str, str]], int, str]:
    """Best-effort read of Hermes's own Telegram command menu helper."""
    for source_root in _hermes_agent_source_candidates(env):
        added = False
        root = str(source_root)
        if root not in sys.path:
            sys.path.insert(0, root)
            added = True
        try:
            from hermes_cli.commands import (  # type: ignore
                COMMAND_REGISTRY,
                _is_gateway_available,
                _requires_argument,
                _resolve_config_gates,
                _sanitize_telegram_name,
            )

            overrides = _resolve_config_gates()
            commands: list[tuple[str, str]] = []
            for cmd_def in COMMAND_REGISTRY:
                if not _is_gateway_available(cmd_def, overrides):
                    continue
                if _requires_argument(str(getattr(cmd_def, "args_hint", ""))):
                    continue
                name = _sanitize_telegram_name(str(getattr(cmd_def, "name", "")))
                description = str(getattr(cmd_def, "description", "") or f"Run /{name}").strip()
                if name and description:
                    commands.append((name, description))
                if len(commands) >= max_commands:
                    break
            return commands, 0, root
        except Exception as exc:  # noqa: BLE001 - command menu must fall back safely
            logger.debug("hermes_telegram_menu_load_failed source=%s error=%s", root, str(exc)[:160])
        finally:
            if added:
                try:
                    sys.path.remove(root)
                except ValueError:
                    pass
    return list(ARCLINK_TELEGRAM_AGENT_FALLBACK_COMMANDS), 0, "fallback"


def arclink_public_bot_telegram_agent_commands(
    *,
    env: Mapping[str, str] | None = None,
    max_commands: int = ARCLINK_TELEGRAM_COMMAND_LIMIT,
) -> list[dict[str, str]]:
    raw_commands, _hidden_count, _source = _load_hermes_telegram_menu_commands(
        max_commands=max_commands,
        env=env,
    )
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    raw_with_aliases = list(raw_commands) + list(ARCLINK_TELEGRAM_AGENT_ALIAS_COMMANDS)
    for raw_name, raw_description in raw_with_aliases:
        name = _telegram_command_name(raw_name)
        if not name or name in seen:
            continue
        description = str(raw_description or f"Agent: run /{name}").strip()
        if not description.lower().startswith("agent:"):
            description = f"Agent: {description[:90]}"
        result.append({"command": name, "description": description[:256]})
        seen.add(name)
        if len(result) >= max_commands:
            break
    return result


def arclink_public_bot_telegram_active_command_plan(
    *,
    agent_commands: list[dict[str, str]] | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build a conflict-free active-chat Telegram command plan.

    In active chats the active agent owns the bare slash namespace. Raven gets
    one safe control command whose name is selected after the agent command
    inventory is known, so an upstream Hermes/plugin/skill command cannot
    accidentally steal or shadow Raven's visible control entry.
    """
    raw_agent = list(agent_commands) if agent_commands is not None else arclink_public_bot_telegram_agent_commands(env=env)
    normalized_agent: list[dict[str, str]] = []
    seen_agent: set[str] = set()
    suppressed: list[str] = []
    for item in raw_agent:
        name = _telegram_command_name(str(item.get("command") or ""))
        description = str(item.get("description") or "").strip()
        if not name or not description or name in seen_agent:
            continue
        if name in ARCLINK_TELEGRAM_POLICY_SUPPRESSED_AGENT_COMMANDS:
            suppressed.append(name)
            continue
        normalized_agent.append({"command": name, "description": description[:256]})
        seen_agent.add(name)

    raven_command = ""
    for candidate in ARCLINK_TELEGRAM_RAVEN_CONTROL_CANDIDATES:
        if candidate not in seen_agent:
            raven_command = candidate
            break
    if not raven_command:
        # Last-resort deterministic escape hatch. It is intentionally clunky so
        # any upstream collision is obvious in the operator alert.
        for suffix in range(10):
            candidate = f"arclink_ops{suffix}"
            if candidate not in seen_agent:
                raven_command = candidate
                break
    if not raven_command:
        raven_command = "arclink_ops"

    commands: list[dict[str, str]] = [
        {"command": raven_command, "description": ARCLINK_TELEGRAM_RAVEN_ACTIVE_DESCRIPTION[:256]}
    ]
    used = {raven_command}
    for item in normalized_agent:
        if item["command"] in used:
            continue
        commands.append(item)
        used.add(item["command"])
        if len(commands) >= ARCLINK_TELEGRAM_COMMAND_LIMIT:
            break

    legacy_conflicts = sorted(seen_agent & ARCLINK_TELEGRAM_LEGACY_RAVEN_COMMAND_NAMES)
    hard_conflicts = sorted(seen_agent & set(ARCLINK_TELEGRAM_RAVEN_CONTROL_CANDIDATES))
    hidden_count = max(0, len(normalized_agent) + 1 - len(commands))
    return {
        "commands": commands,
        "agent_command_names": sorted(seen_agent),
        "legacy_raven_conflicts": legacy_conflicts,
        "hard_raven_conflicts": hard_conflicts,
        "policy_suppressed": sorted(set(suppressed)),
        "raven_command": raven_command,
        "hidden_count": hidden_count,
    }


def arclink_public_bot_telegram_chat_commands(
    *,
    include_agent_commands: bool,
    env: Mapping[str, str] | None = None,
) -> list[dict[str, str]]:
    if include_agent_commands:
        plan = arclink_public_bot_telegram_active_command_plan(env=env)
        return list(plan["commands"])

    merged: list[dict[str, str]] = []
    seen: set[str] = set()

    def add_commands(commands: list[dict[str, str]]) -> None:
        for item in commands:
            name = _telegram_command_name(str(item.get("command") or ""))
            description = str(item.get("description") or "").strip()
            if not name or not description or name in seen:
                continue
            merged.append({"command": name, "description": description[:256]})
            seen.add(name)
            if len(merged) >= ARCLINK_TELEGRAM_COMMAND_LIMIT:
                return

    add_commands(arclink_public_bot_telegram_commands())
    return merged[:ARCLINK_TELEGRAM_COMMAND_LIMIT]


def refresh_arclink_public_telegram_chat_commands(
    *,
    bot_token: str,
    chat_id: str,
    include_agent_commands: bool,
    env: Mapping[str, str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    clean_token = str(bot_token or "").strip()
    clean_chat_id = str(chat_id or "").strip()
    if not clean_token or not clean_chat_id:
        return {"skipped": True, "reason": "missing_token_or_chat"}
    plan: dict[str, Any] = {}
    if include_agent_commands:
        plan = arclink_public_bot_telegram_active_command_plan(env=env)
        commands = list(plan["commands"])
    else:
        commands = arclink_public_bot_telegram_chat_commands(
            include_agent_commands=False,
            env=env,
        )
    signature = ",".join(item["command"] for item in commands)
    cache_key = (clean_chat_id, signature)
    if not force and cache_key in _TELEGRAM_CHAT_COMMAND_SCOPE_CACHE:
        return {
            "skipped": True,
            "reason": "unchanged",
            "chat_id": clean_chat_id,
            "command_count": len(commands),
            "include_agent_commands": include_agent_commands,
            "raven_command": plan.get("raven_command", ""),
            "legacy_raven_conflicts": plan.get("legacy_raven_conflicts", []),
            "hard_raven_conflicts": plan.get("hard_raven_conflicts", []),
            "policy_suppressed": plan.get("policy_suppressed", []),
        }
    scope = _telegram_chat_scope(clean_chat_id)
    telegram_set_my_commands(bot_token=clean_token, commands=commands, scope=scope)
    _TELEGRAM_CHAT_COMMAND_SCOPE_CACHE.add(cache_key)
    return {
        "registered": [item["command"] for item in commands],
        "scope": scope,
        "chat_id": clean_chat_id,
        "command_count": len(commands),
        "include_agent_commands": include_agent_commands,
        "raven_command": plan.get("raven_command", ""),
        "agent_command_names": plan.get("agent_command_names", []),
        "legacy_raven_conflicts": plan.get("legacy_raven_conflicts", []),
        "hard_raven_conflicts": plan.get("hard_raven_conflicts", []),
        "policy_suppressed": plan.get("policy_suppressed", []),
        "hidden_count": plan.get("hidden_count", 0),
    }


def telegram_set_webhook(
    *,
    bot_token: str,
    webhook_url: str,
    allowed_updates: tuple[str, ...] = ARCLINK_PUBLIC_TELEGRAM_ALLOWED_UPDATES,
    drop_pending_updates: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "url": str(webhook_url or "").strip(),
        "allowed_updates": list(allowed_updates),
        "drop_pending_updates": bool(drop_pending_updates),
    }
    return _request_json(
        _telegram_url(bot_token, "setWebhook"),
        method="POST",
        payload=payload,
        timeout=20,
    )


def ensure_arclink_public_telegram_webhook(
    bot_token: str,
    webhook_url: str,
) -> dict[str, Any]:
    clean_token = str(bot_token or "").strip()
    clean_url = str(webhook_url or "").strip()
    if not clean_url:
        return {"skipped": True}
    if not clean_token:
        raise ArcLinkTelegramError("TELEGRAM_BOT_TOKEN is required to configure the ArcLink Telegram webhook")
    telegram_set_webhook(
        bot_token=clean_token,
        webhook_url=clean_url,
        allowed_updates=ARCLINK_PUBLIC_TELEGRAM_ALLOWED_UPDATES,
    )
    return {
        "url": clean_url,
        "allowed_updates": list(ARCLINK_PUBLIC_TELEGRAM_ALLOWED_UPDATES),
    }


def register_arclink_public_telegram_commands(
    bot_token: str,
    *,
    include_private_scope: bool = True,
) -> dict[str, Any]:
    clean_token = str(bot_token or "").strip()
    if not clean_token:
        raise ArcLinkTelegramError("TELEGRAM_BOT_TOKEN is required to register ArcLink public bot commands")
    commands = arclink_public_bot_telegram_commands()
    scopes: list[dict[str, Any] | None] = [None]
    if include_private_scope:
        scopes.append({"type": "all_private_chats"})
    registered_scopes: list[str] = []
    for scope in scopes:
        telegram_set_my_commands(bot_token=clean_token, commands=commands, scope=scope)
        registered_scopes.append(str((scope or {}).get("type") or "default"))
    return {
        "registered": [item["command"] for item in commands],
        "scopes": registered_scopes,
    }


def telegram_get_updates(
    *,
    bot_token: str,
    offset: int | None = None,
    timeout: int = 25,
) -> list[dict[str, Any]]:
    params = {"timeout": str(timeout)}
    if offset is not None:
        params["offset"] = str(offset)
    query = urllib.parse.urlencode(params)
    url = _telegram_url(bot_token, "getUpdates")
    if query:
        url = f"{url}?{query}"
    payload = _request_json(url, timeout=timeout + 10)
    result = payload.get("result", payload)
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    return []


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

    def validate_live_readiness(self) -> list[str]:
        """Return a list of missing config fields required for live operation."""
        missing: list[str] = []
        if not self.bot_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not self.bot_username:
            missing.append("TELEGRAM_BOT_USERNAME")
        return missing


def _telegram_api_url(config: TelegramConfig, method: str) -> str:
    return f"{config.api_base}/bot{config.bot_token}/{method}"


def _telegram_display_name(user: Mapping[str, Any]) -> str:
    """Pick the friendliest display name from a Telegram `from` object.

    Prefer first_name (the human name shown in the chat header), fall back to
    @username if the user has hidden their first name, otherwise empty.
    """
    first = str(user.get("first_name") or "").strip()
    if first:
        return first[:40]
    username = str(user.get("username") or "").strip()
    if username:
        return username[:40]
    return ""


def _telegram_update_json(update: Mapping[str, Any]) -> str:
    try:
        return json.dumps(update, sort_keys=True, separators=(",", ":"))[:60000]
    except TypeError:
        return ""


def _telegram_message_kind(msg: Mapping[str, Any]) -> str:
    if msg.get("photo"):
        return "photo"
    if msg.get("video"):
        return "video"
    if msg.get("audio"):
        return "audio"
    if msg.get("voice"):
        return "voice"
    if msg.get("document"):
        return "document"
    if msg.get("sticker"):
        return "sticker"
    if msg.get("venue"):
        return "venue"
    if msg.get("location"):
        return "location"
    if msg.get("contact"):
        return "contact"
    if msg.get("poll"):
        return "poll"
    return "message"


def _telegram_fallback_text_for_kind(kind: str) -> str:
    labels = {
        "photo": "[Telegram photo]",
        "video": "[Telegram video]",
        "audio": "[Telegram audio]",
        "voice": "[Telegram voice message]",
        "document": "[Telegram document]",
        "sticker": "[Telegram sticker]",
        "venue": "[Telegram venue pin]",
        "location": "[Telegram location pin]",
        "contact": "[Telegram contact card]",
        "poll": "[Telegram poll]",
    }
    return labels.get(kind, "[Telegram update]")


def parse_telegram_update(update: Mapping[str, Any]) -> dict[str, Any] | None:
    """Extract routing identity and preserve the native Telegram update.

    Text is still used for Raven command routing, but the raw update is carried
    to active-agent delivery so Hermes' own Telegram adapter can parse rich
    messages and callback queries without ArcLink shadowing upstream logic.
    """
    callback = update.get("callback_query") or {}
    if callback:
        data = str(callback.get("data") or "").strip()
        native_callback = not data.startswith("arclink:")
        if data.startswith("arclink:"):
            data = data[len("arclink:"):].strip()
        msg = callback.get("message") or {}
        chat = msg.get("chat") or {}
        user = callback.get("from") or {}
        chat_id = str(chat.get("id") or "")
        user_id = str(user.get("id") or "")
        if chat_id and data:
            return {
                "chat_id": chat_id,
                "user_id": user_id,
                "text": data,
                "callback_query_id": str(callback.get("id") or ""),
                "callback_message_id": str(msg.get("message_id") or ""),
                "display_name": _telegram_display_name(user),
                "telegram_message_id": str(msg.get("message_id") or ""),
                "telegram_update_kind": "callback_query",
                "telegram_native_callback": native_callback,
                "telegram_update_json": _telegram_update_json(update),
            }
    msg = update.get("message") or update.get("edited_message") or {}
    kind = _telegram_message_kind(msg)
    text = str(msg.get("text") or msg.get("caption") or "").strip()
    if not text and kind != "message":
        text = _telegram_fallback_text_for_kind(kind)
    chat = msg.get("chat") or {}
    user = msg.get("from") or {}
    chat_id = str(chat.get("id") or "")
    user_id = str(user.get("id") or "")
    if not chat_id or not text:
        return None
    return {
        "chat_id": chat_id,
        "user_id": user_id,
        "text": text,
        "message_id": str(msg.get("message_id") or ""),
        "display_name": _telegram_display_name(user),
        "telegram_update_kind": kind,
        "telegram_update_json": _telegram_update_json(update),
    }


def handle_telegram_update(
    conn: sqlite3.Connection,
    update: Mapping[str, Any],
    *,
    stripe_client: Any | None = None,
    price_id: str = "price_arclink_sovereign",
    founders_price_id: str = "price_arclink_founders",
    scale_price_id: str = "",
    additional_agent_price_id: str = "",
    sovereign_agent_expansion_price_id: str = "",
    scale_agent_expansion_price_id: str = "",
    base_domain: str = "",
    telegram_bot_token: str = "",
) -> dict[str, Any] | None:
    """Process a single Telegram update through the shared bot contract.

    Returns a dict with chat_id and reply text, or None if the update
    is not a text message.
    """
    parsed = parse_telegram_update(update)
    if parsed is None:
        return None
    channel_identity = f"tg:{parsed['user_id']}" if parsed["user_id"] else f"tg:{parsed['chat_id']}"
    turn_metadata: dict[str, Any] = {
        "telegram_message_id": parsed.get("message_id", "") or parsed.get("telegram_message_id", ""),
        "telegram_update_kind": parsed.get("telegram_update_kind", ""),
        "telegram_update_json": parsed.get("telegram_update_json", ""),
    }
    if parsed.get("telegram_native_callback"):
        turn_metadata["telegram_native_callback"] = True
    if str(parsed.get("text") or "").strip().startswith("/"):
        turn_metadata["active_agent_command_names"] = [
            item["command"] for item in arclink_public_bot_telegram_agent_commands()
        ]
    turn = handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity=channel_identity,
        text=parsed["text"],
        stripe_client=stripe_client,
        price_id=price_id,
        founders_price_id=founders_price_id,
        scale_price_id=scale_price_id,
        additional_agent_price_id=additional_agent_price_id,
        sovereign_agent_expansion_price_id=sovereign_agent_expansion_price_id,
        scale_agent_expansion_price_id=scale_agent_expansion_price_id,
        base_domain=base_domain,
        metadata=turn_metadata,
        display_name_hint=parsed.get("display_name", ""),
    )
    command_scope: dict[str, Any] | None = None
    clean_token = str(telegram_bot_token or "").strip()
    if clean_token:
        include_agent_commands = bool(
            turn.deployment_id and turn.status in ARCLINK_PUBLIC_BOT_DEPLOYMENT_READY_STATUSES
        )
        try:
            command_scope = refresh_arclink_public_telegram_chat_commands(
                bot_token=clean_token,
                chat_id=parsed["chat_id"],
                include_agent_commands=include_agent_commands,
                force=turn.action == "switch_agent",
            )
        except Exception as exc:  # noqa: BLE001 - never fail the webhook on menu refresh
            logger.warning("telegram_command_scope_refresh_failed action=%s error=%s", turn.action, str(exc)[:160])
    return {
        "chat_id": parsed["chat_id"],
        "text": turn.reply,
        "reply_markup": arclink_public_bot_turn_telegram_reply_markup(turn),
        "session_id": turn.session_id,
        "action": turn.action,
        "channel_identity": channel_identity,
        "callback_query_id": parsed.get("callback_query_id", ""),
        "callback_message_id": parsed.get("callback_message_id", ""),
        "command_scope": command_scope,
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

    def send_message(self, chat_id: str, text: str, reply_markup: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        result = self._call("sendMessage", payload)
        return result.get("result", {})

    def answer_callback_query(self, callback_query_id: str, text: str = "") -> dict[str, Any]:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text[:200]
        result = self._call("answerCallbackQuery", payload)
        return result.get("result", {})

    def edit_message_text(
        self,
        chat_id: str,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"chat_id": chat_id, "message_id": int(message_id), "text": text}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        result = self._call("editMessageText", payload)
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
        self.edited_messages: list[dict[str, Any]] = []
        self.updates_queue: list[dict[str, Any]] = []

    def send_message(self, chat_id: str, text: str, reply_markup: dict[str, Any] | None = None) -> dict[str, Any]:
        msg = {"chat_id": chat_id, "text": text, "message_id": len(self.sent_messages) + 1}
        if reply_markup is not None:
            msg["reply_markup"] = reply_markup
        self.sent_messages.append(msg)
        return msg

    def answer_callback_query(self, callback_query_id: str, text: str = "") -> dict[str, Any]:
        return {"callback_query_id": callback_query_id, "text": text}

    def edit_message_text(
        self,
        chat_id: str,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        msg = {"chat_id": chat_id, "message_id": int(message_id), "text": text}
        if reply_markup is not None:
            msg["reply_markup"] = reply_markup
        self.edited_messages.append(msg)
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
    price_id: str = "price_arclink_sovereign",
    founders_price_id: str = "price_arclink_founders",
    scale_price_id: str = "",
    additional_agent_price_id: str = "",
    sovereign_agent_expansion_price_id: str = "",
    scale_agent_expansion_price_id: str = "",
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
                    founders_price_id=founders_price_id,
                    scale_price_id=scale_price_id,
                    additional_agent_price_id=additional_agent_price_id,
                    sovereign_agent_expansion_price_id=sovereign_agent_expansion_price_id,
                    scale_agent_expansion_price_id=scale_agent_expansion_price_id,
                    base_domain=base_domain,
                    telegram_bot_token=config.bot_token,
                )
                if result:
                    transport.send_message(result["chat_id"], result["text"], reply_markup=result.get("reply_markup"))
                    logger.info("telegram_reply chat_id=%s action=%s", result["chat_id"], result["action"])
            except Exception:
                logger.exception("telegram_update_error update_id=%s", update_id)
