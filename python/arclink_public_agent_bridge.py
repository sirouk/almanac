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
from types import SimpleNamespace
from urllib.parse import quote


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


class _DiscordRest:
    def __init__(self, token: str) -> None:
        self.token = token
        self._session: Any | None = None

    async def __aenter__(self) -> "_DiscordRest":
        import aiohttp

        self._session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bot {self.token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "ArcLinkPublicAgentBridge/1.0",
            }
        )
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._session is not None:
            await self._session.close()

    async def request(self, method: str, path: str, *, payload: Any | None = None) -> Any:
        if self._session is None:
            raise RuntimeError("Discord REST session is not open")
        url = f"https://discord.com/api/v10{path}"
        async with self._session.request(method, url, json=payload) as response:
            text = await response.text()
            if response.status >= 300:
                raise RuntimeError(f"discord http {response.status}: {text[:240]}")
            if not text.strip():
                return {}
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"raw": text}


class _DiscordRawMessage:
    def __init__(self, *, rest: _DiscordRest, channel_id: str, message_id: str) -> None:
        self._rest = rest
        self.channel_id = channel_id
        self.id = message_id

    async def add_reaction(self, emoji: str) -> None:
        if not self.id:
            return
        await self._rest.request(
            "PUT",
            f"/channels/{self.channel_id}/messages/{self.id}/reactions/{quote(emoji, safe='')}/@me",
        )

    async def remove_reaction(self, emoji: str, user: Any = None) -> None:
        del user
        if not self.id:
            return
        await self._rest.request(
            "DELETE",
            f"/channels/{self.channel_id}/messages/{self.id}/reactions/{quote(emoji, safe='')}/@me",
        )


async def _run_discord(payload: Mapping[str, Any]) -> None:
    _add_runtime_paths()

    bot_token = _required(payload, "bot_token")
    channel_id = _required(payload, "channel_id")
    user_id = _required(payload, "user_id")
    text = _required(payload, "text")
    message_id = str(payload.get("message_id") or "").strip()
    display_name = str(payload.get("display_name") or "").strip() or None

    os.environ["DISCORD_BOT_TOKEN"] = bot_token
    os.environ.setdefault("DISCORD_REACTIONS", "true")
    os.environ.setdefault("DISCORD_REPLY_TO_MODE", "first")
    _set_csv_env("DISCORD_ALLOWED_USERS", user_id)
    _set_csv_env("DISCORD_FREE_RESPONSE_CHANNELS", channel_id)

    from gateway.config import HomeChannel, Platform, PlatformConfig, load_gateway_config
    from gateway.platforms.base import MessageEvent, MessageType, SendResult
    from gateway.run import GatewayRunner
    from gateway.session import SessionSource

    cfg = load_gateway_config()
    platform = Platform.DISCORD
    platform_cfg = cfg.platforms.get(platform) or PlatformConfig()
    platform_cfg.enabled = True
    platform_cfg.token = bot_token
    platform_cfg.gateway_restart_notification = False
    platform_cfg.reply_to_mode = os.environ.get("DISCORD_REPLY_TO_MODE", "first")
    platform_cfg.home_channel = HomeChannel(
        platform=platform,
        chat_id=channel_id,
        name=os.environ.get("DISCORD_HOME_CHANNEL_NAME", "ArcLink public channel"),
    )
    cfg.platforms[platform] = platform_cfg

    async with _DiscordRest(bot_token) as rest:
        runner = GatewayRunner(cfg)
        adapter = runner._create_adapter(platform, platform_cfg)
        if adapter is None:
            raise RuntimeError("Hermes could not create a Discord adapter")

        async def _send(
            chat_id: str,
            content: str,
            reply_to: str | None = None,
            metadata: Mapping[str, Any] | None = None,
        ) -> SendResult:
            target_channel = str((metadata or {}).get("thread_id") or chat_id or channel_id)
            chunks = adapter.truncate_message(adapter.format_message(content), getattr(adapter, "MAX_MESSAGE_LENGTH", 2000))
            sent_ids: list[str] = []
            for idx, chunk in enumerate(chunks or [""]):
                body: dict[str, Any] = {"content": chunk}
                if reply_to and idx == 0 and getattr(adapter, "_reply_to_mode", "first") != "off":
                    body["message_reference"] = {
                        "message_id": str(reply_to),
                        "channel_id": target_channel,
                        "fail_if_not_exists": False,
                    }
                sent = await rest.request("POST", f"/channels/{target_channel}/messages", payload=body)
                sent_id = str(sent.get("id") or "")
                if sent_id:
                    sent_ids.append(sent_id)
            return SendResult(success=True, message_id=sent_ids[0] if sent_ids else None, raw_response={"message_ids": sent_ids})

        async def _edit_message(chat_id: str, message_id_arg: str, content: str, *, finalize: bool = False) -> SendResult:
            del finalize
            target_channel = str(chat_id or channel_id)
            chunks = adapter.truncate_message(adapter.format_message(content), getattr(adapter, "MAX_MESSAGE_LENGTH", 2000))
            await rest.request(
                "PATCH",
                f"/channels/{target_channel}/messages/{message_id_arg}",
                payload={"content": (chunks[0] if chunks else "")},
            )
            return SendResult(success=True, message_id=message_id_arg)

        async def _send_typing(chat_id: str, metadata: Mapping[str, Any] | None = None) -> None:
            del metadata
            await rest.request("POST", f"/channels/{chat_id or channel_id}/typing")

        async def _stop_typing(chat_id: str) -> None:
            del chat_id

        adapter.send = _send  # type: ignore[method-assign]
        adapter.edit_message = _edit_message  # type: ignore[method-assign]
        adapter.send_typing = _send_typing  # type: ignore[method-assign]
        adapter.stop_typing = _stop_typing  # type: ignore[method-assign]
        adapter._client = SimpleNamespace(user=SimpleNamespace(id="arclink-public-bridge"))  # type: ignore[attr-defined]
        adapter.set_message_handler(runner._handle_message)
        adapter.set_fatal_error_handler(runner._handle_adapter_fatal_error)
        adapter.set_session_store(runner.session_store)
        adapter.set_busy_session_handler(runner._handle_active_session_busy_message)
        runner.adapters[platform] = adapter

        source = SessionSource(
            platform=platform,
            chat_id=channel_id,
            chat_name=display_name,
            chat_type=str(payload.get("chat_type") or "dm"),
            user_id=user_id,
            user_name=display_name,
            message_id=message_id or None,
        )
        event = MessageEvent(
            text=text,
            message_type=MessageType.COMMAND if text.startswith("/") else MessageType.TEXT,
            source=source,
            raw_message=_DiscordRawMessage(rest=rest, channel_id=channel_id, message_id=message_id),
            message_id=message_id or None,
        )
        await adapter.handle_message(event)
        while getattr(adapter, "_background_tasks", None):
            tasks = list(adapter._background_tasks)  # type: ignore[attr-defined]
            if not tasks:
                break
            await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED)


async def _run(payload: Mapping[str, Any]) -> None:
    platform = str(payload.get("platform") or "").strip().lower()
    if platform == "telegram":
        await _run_telegram(payload)
        return
    if platform == "discord":
        await _run_discord(payload)
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
