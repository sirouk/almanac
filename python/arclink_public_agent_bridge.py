#!/usr/bin/env python3
"""Route a public ArcLink bot turn through Hermes' gateway pipeline.

Raven owns the public Telegram/Discord ingress webhook. Once a user is aboard,
normal messages should behave like active-agent channel messages, not like a
Raven-mediated quiet CLI call. This helper is executed inside the deployment
runtime container and builds a synthetic Hermes platform event so Hermes can use
its native gateway behavior: sessions, slash commands, typing, reactions,
interim messages, delivery formatting, and plugin hooks.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping


def _json_error(message: str) -> int:
    print(json.dumps({"ok": False, "error": message[:500]}, sort_keys=True))
    return 1


def _payload_from_stdin() -> dict[str, Any]:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid bridge payload: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("bridge payload must be an object")
    return payload


def _runtime_source_dir() -> Path:
    explicit = os.environ.get("HERMES_AGENT_SRC", "").strip()
    if explicit:
        return Path(explicit)
    runtime_dir = os.environ.get("RUNTIME_DIR", "/opt/arclink/runtime").strip() or "/opt/arclink/runtime"
    return Path(runtime_dir) / "hermes-agent-src"


def _add_runtime_paths() -> None:
    source_dir = _runtime_source_dir()
    if not source_dir.exists():
        raise RuntimeError(f"Hermes runtime source is missing at {source_dir}")
    source_text = str(source_dir)
    if source_text not in sys.path:
        sys.path.insert(0, source_text)


def _set_csv_env(name: str, *values: str) -> None:
    clean_values = [str(value).strip() for value in values if str(value).strip()]
    if not clean_values:
        return
    existing = [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]
    merged: list[str] = []
    for value in [*existing, *clean_values]:
        if value not in merged:
            merged.append(value)
    os.environ[name] = ",".join(merged)


def _required(payload: Mapping[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise RuntimeError(f"bridge payload missing {key}")
    return value


async def _run_telegram(payload: Mapping[str, Any]) -> None:
    _add_runtime_paths()

    bot_token = _required(payload, "bot_token")
    chat_id = _required(payload, "chat_id")
    user_id = str(payload.get("user_id") or chat_id).strip()
    text = _required(payload, "text")
    message_id = str(payload.get("message_id") or "").strip() or None
    display_name = str(payload.get("display_name") or "").strip() or None

    os.environ["TELEGRAM_BOT_TOKEN"] = bot_token
    os.environ["TELEGRAM_HOME_CHANNEL"] = chat_id
    os.environ.setdefault("TELEGRAM_HOME_CHANNEL_NAME", "ArcLink public channel")
    os.environ.setdefault("TELEGRAM_REACTIONS", "true")
    os.environ.setdefault("TELEGRAM_REPLY_TO_MODE", "first")
    _set_csv_env("TELEGRAM_ALLOWED_USERS", user_id, chat_id)

    from telegram import Bot
    from gateway.config import HomeChannel, Platform, PlatformConfig, load_gateway_config
    from gateway.platforms.base import MessageEvent, MessageType
    from gateway.run import GatewayRunner
    from gateway.session import SessionSource

    cfg = load_gateway_config()
    platform = Platform.TELEGRAM
    platform_cfg = cfg.platforms.get(platform) or PlatformConfig()
    platform_cfg.enabled = True
    platform_cfg.token = bot_token
    platform_cfg.gateway_restart_notification = False
    platform_cfg.reply_to_mode = os.environ.get("TELEGRAM_REPLY_TO_MODE", "first")
    platform_cfg.home_channel = HomeChannel(
        platform=platform,
        chat_id=chat_id,
        name=os.environ.get("TELEGRAM_HOME_CHANNEL_NAME", "ArcLink public channel"),
    )
    cfg.platforms[platform] = platform_cfg

    runner = GatewayRunner(cfg)
    adapter = runner._create_adapter(platform, platform_cfg)
    if adapter is None:
        raise RuntimeError("Hermes could not create a Telegram adapter")
    adapter.set_message_handler(runner._handle_message)
    adapter.set_fatal_error_handler(runner._handle_adapter_fatal_error)
    adapter.set_session_store(runner.session_store)
    adapter.set_busy_session_handler(runner._handle_active_session_busy_message)
    runner.adapters[platform] = adapter

    bot = Bot(token=bot_token)
    await bot.initialize()
    try:
        adapter._bot = bot  # type: ignore[attr-defined]
        source = SessionSource(
            platform=platform,
            chat_id=chat_id,
            chat_name=display_name,
            chat_type="dm",
            user_id=user_id,
            user_name=display_name,
            message_id=message_id,
        )
        event = MessageEvent(
            text=text,
            message_type=MessageType.TEXT,
            source=source,
            message_id=message_id,
        )
        await adapter.handle_message(event)
        while getattr(adapter, "_background_tasks", None):
            tasks = list(adapter._background_tasks)  # type: ignore[attr-defined]
            if not tasks:
                break
            await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED)
    finally:
        try:
            await bot.shutdown()
        except Exception:
            pass


async def _run(payload: Mapping[str, Any]) -> None:
    platform = str(payload.get("platform") or "").strip().lower()
    if platform == "telegram":
        await _run_telegram(payload)
        return
    raise RuntimeError(f"public agent gateway bridge does not support platform {platform or 'blank'} yet")


def main() -> int:
    try:
        payload = _payload_from_stdin()
        asyncio.run(_run(payload))
    except Exception as exc:  # noqa: BLE001 - boundary process returns structured failure
        return _json_error(str(exc))
    print(json.dumps({"ok": True, "delivered": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
