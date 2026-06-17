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
import hashlib
import json
import os
import sys
import tempfile
import threading
import time
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


def _is_slash_command(text: str) -> bool:
    return str(text or "").lstrip().startswith("/")


FALSE_VALUES = {"0", "false", "no", "off"}
BRIDGE_STATE_DIRNAME = "arclink-public-bridge"
APPROVAL_POLL_SECONDS = 0.25


def _bool_payload(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return default
    if text in FALSE_VALUES:
        return False
    if text in {"1", "true", "yes", "on"}:
        return True
    return default


def _public_bridge_streaming_enabled() -> bool:
    return os.environ.get("ARCLINK_PUBLIC_AGENT_BRIDGE_STREAMING", "1").strip().lower() not in FALSE_VALUES


def _apply_public_bridge_options(payload: Mapping[str, Any]) -> None:
    if "streaming_enabled" in payload:
        os.environ["ARCLINK_PUBLIC_AGENT_BRIDGE_STREAMING"] = (
            "1" if _bool_payload(payload.get("streaming_enabled"), default=True) else "0"
        )
    if _public_bridge_streaming_enabled():
        os.environ.setdefault("HERMES_TOOL_PROGRESS_MODE", "all")


def _bridge_state_dir() -> Path:
    hermes_home = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")
    path = hermes_home / "state" / BRIDGE_STATE_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _hash_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "ignore")).hexdigest()[:32]


def _json_read(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _json_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(payload), handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def _session_state_file(session_key: str) -> Path:
    return _bridge_state_dir() / "sessions" / f"{_hash_id(session_key)}.json"


def _load_bridge_session_state(session_key: str) -> None:
    if not session_key:
        return
    state = _json_read(_session_state_file(session_key))
    try:
        from tools.approval import disable_session_yolo, enable_session_yolo

        if bool(state.get("yolo_enabled")):
            enable_session_yolo(session_key)
        else:
            disable_session_yolo(session_key)
    except Exception:
        pass


def _persist_bridge_session_state(session_key: str) -> None:
    if not session_key:
        return
    try:
        from tools.approval import is_session_yolo_enabled

        yolo_enabled = bool(is_session_yolo_enabled(session_key))
    except Exception:
        yolo_enabled = False
    _json_write(
        _session_state_file(session_key),
        {
            "session_key_hash": _hash_id(session_key),
            "updated_at": int(time.time()),
            "yolo_enabled": yolo_enabled,
        },
    )


def _approval_paths(*, platform: str, chat_id: str, approval_id: int, message_id: str = "") -> list[Path]:
    base = _bridge_state_dir() / "approvals" / platform
    safe_chat = _hash_id(str(chat_id or ""))
    paths: list[Path] = []
    if str(message_id or "").strip():
        paths.append(base / f"{safe_chat}-{str(message_id).strip()}-{approval_id}.json")
    paths.append(base / f"{safe_chat}-{approval_id}.json")
    return paths


def _write_approval_mapping(
    *,
    platform: str,
    chat_id: str,
    approval_id: int,
    message_id: str,
    session_key: str,
    timeout_seconds: int = 300,
) -> list[Path]:
    now = int(time.time())
    payload = {
        "platform": platform,
        "chat_id_hash": _hash_id(str(chat_id or "")),
        "approval_id": approval_id,
        "message_id": str(message_id or ""),
        "session_key": session_key,
        "created_at": now,
        "expires_at": now + max(30, min(3600, int(timeout_seconds or 300))),
        "choice": "",
    }
    paths = _approval_paths(platform=platform, chat_id=chat_id, approval_id=approval_id, message_id=message_id)
    for path in paths:
        _json_write(path, payload)
    return paths


def _approval_mapping_for_callback(*, platform: str, chat_id: str, approval_id: int, message_id: str = "") -> tuple[Path | None, dict[str, Any]]:
    now = int(time.time())
    for path in _approval_paths(platform=platform, chat_id=chat_id, approval_id=approval_id, message_id=message_id):
        data = _json_read(path)
        if not data:
            continue
        try:
            expires_at = int(data.get("expires_at") or 0)
        except (TypeError, ValueError):
            expires_at = 0
        if expires_at and expires_at < now:
            continue
        return path, data
    return None, {}


def _record_approval_choice(paths: list[Path], choice: str) -> None:
    now = int(time.time())
    for path in paths:
        data = _json_read(path)
        if not data:
            continue
        data["choice"] = str(choice or "")
        data["resolved_at"] = now
        _json_write(path, data)


def _watch_durable_approval(paths: list[Path], *, session_key: str, timeout_seconds: int) -> None:
    deadline = time.monotonic() + max(30, min(3600, int(timeout_seconds or 300)))
    while time.monotonic() < deadline:
        for path in paths:
            data = _json_read(path)
            choice = str(data.get("choice") or "").strip().lower()
            if choice in {"once", "session", "always", "deny"}:
                try:
                    from tools.approval import resolve_gateway_approval

                    resolve_gateway_approval(session_key, choice)
                except Exception:
                    pass
                return
        time.sleep(APPROVAL_POLL_SECONDS)


def _install_telegram_bridge_state(adapter: Any, runner: Any, source: Any, *, chat_id: str) -> None:
    try:
        session_key = runner._session_key_for_source(source)
    except Exception:
        session_key = ""
    _load_bridge_session_state(session_key)

    original_send = getattr(adapter, "send_exec_approval", None)
    if not callable(original_send):
        return

    async def _send_exec_approval_with_durable_state(*args: Any, **kwargs: Any) -> Any:
        before = set(getattr(adapter, "_approval_state", {}) or {})
        result = await original_send(*args, **kwargs)
        after_state = getattr(adapter, "_approval_state", {}) or {}
        new_ids = [item for item in after_state if item not in before]
        approval_session = str(kwargs.get("session_key") or session_key or "")
        result_message_id = str(getattr(result, "message_id", "") or "")
        for approval_id in new_ids:
            try:
                approval_int = int(approval_id)
            except (TypeError, ValueError):
                continue
            mapped_session = str(after_state.get(approval_id) or approval_session)
            if not mapped_session:
                continue
            paths = _write_approval_mapping(
                platform="telegram",
                chat_id=str(kwargs.get("chat_id") or chat_id or ""),
                approval_id=approval_int,
                message_id=result_message_id,
                session_key=mapped_session,
            )
            thread = threading.Thread(
                target=_watch_durable_approval,
                kwargs={"paths": paths, "session_key": mapped_session, "timeout_seconds": 300},
                daemon=True,
            )
            thread.start()
        return result

    try:
        adapter.send_exec_approval = _send_exec_approval_with_durable_state  # type: ignore[method-assign]
    except Exception:
        pass


def _persist_telegram_bridge_state(runner: Any, source: Any) -> None:
    try:
        session_key = runner._session_key_for_source(source)
    except Exception:
        session_key = ""
    _persist_bridge_session_state(session_key)


def _enable_public_bridge_gateway_defaults(cfg: Any) -> None:
    """Make bridged public turns feel like native Hermes gateway turns.

    ArcLink's public bot owns Telegram/Discord webhooks, so these turns enter
    Hermes through a synthetic platform event. Deployment homes can have global
    gateway streaming disabled for other uses; public channel turns should still
    get Hermes typing/progress/streaming unless the operator explicitly turns
    the bridge knob off. This intentionally does not enable show_reasoning.
    """
    if not _public_bridge_streaming_enabled():
        return
    streaming = getattr(cfg, "streaming", None)
    if streaming is None:
        return
    try:
        streaming.enabled = True
        if not getattr(streaming, "transport", ""):
            streaming.transport = "edit"
    except Exception:
        return


async def _drain_bridge_adapter_tasks(adapter: Any) -> None:
    """Wait for Hermes adapter work spawned by synthetic public turns.

    Telegram text/media handlers intentionally debounce batches before calling
    ``handle_message``. The bridge is a short-lived process, so exiting as soon
    as the update handler returns can cancel that pending flush before Hermes
    starts the Agent turn. Drain both those platform batch timers and the
    standard gateway background tasks they may spawn.
    """
    while True:
        pending: list[asyncio.Task[Any]] = []
        background_tasks = getattr(adapter, "_background_tasks", None)
        if background_tasks:
            pending.extend(task for task in list(background_tasks) if task and not task.done())
        for attr in ("_pending_text_batch_tasks", "_pending_photo_batch_tasks"):
            task_map = getattr(adapter, attr, None)
            if isinstance(task_map, dict):
                pending.extend(task for task in list(task_map.values()) if task and not task.done())
        if not pending:
            return
        results = await asyncio.gather(*pending, return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException) and not isinstance(result, asyncio.CancelledError):
                raise result


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
    _enable_public_bridge_gateway_defaults(cfg)
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
        _install_telegram_bridge_state(adapter, runner, source, chat_id=chat_id)
        replayed = False
        # A Telegram album arrives as one update per item; the delivery layer
        # absorbs sibling outbox rows into telegram_update_json_list so this
        # single bridge process can replay them together and Hermes' native
        # media-group debounce merges them into one Agent turn.
        update_list = payload.get("telegram_update_json_list")
        if isinstance(update_list, list) and update_list:
            for raw_update in update_list:
                item_payload = {**payload, "telegram_update_json": raw_update}
                item_payload.pop("telegram_update_json_list", None)
                if await _try_replay_native_telegram_update(adapter, bot, item_payload):
                    replayed = True
        else:
            replayed = await _try_replay_native_telegram_update(adapter, bot, payload)
        if not replayed:
            event = MessageEvent(
                text=text,
                message_type=MessageType.COMMAND if _is_slash_command(text) else MessageType.TEXT,
                source=source,
                message_id=message_id,
            )
            await adapter.handle_message(event)
        await _drain_bridge_adapter_tasks(adapter)
        _persist_telegram_bridge_state(runner, source)
    finally:
        try:
            await bot.shutdown()
        except Exception:
            pass


async def _try_replay_native_telegram_update(adapter: Any, bot: Any, payload: Mapping[str, Any]) -> bool:
    """Replay a raw Telegram update through Hermes' own Telegram handlers.

    ArcLink owns the public Raven webhook, but active-agent turns should not
    require us to clone every upstream Telegram media/callback branch. When the
    ingress layer passes the original update JSON, rebuild the PTB Update and
    dispatch it to Hermes' native adapter methods. If an upstream Hermes update
    changes media handling, this bridge follows that code instead of a forked
    ArcLink parser.
    """
    raw_update = str(payload.get("telegram_update_json") or "").strip()
    if not raw_update:
        return False
    try:
        from telegram import Update

        update_payload = json.loads(raw_update)
        if not isinstance(update_payload, dict):
            return False
        update = Update.de_json(update_payload, bot)
    except Exception:
        return False

    context = SimpleNamespace(bot=bot)
    callback = getattr(update, "callback_query", None)
    if callback is not None:
        data = str(getattr(callback, "data", "") or "")
        if data.startswith("ea:"):
            parts = data.split(":", 2)
            if len(parts) == 3:
                try:
                    approval_id = int(parts[2])
                except (TypeError, ValueError):
                    approval_id = 0
                if approval_id:
                    message_obj = getattr(callback, "message", None)
                    callback_chat = getattr(message_obj, "chat", None)
                    callback_chat_id = str(getattr(callback_chat, "id", "") or payload.get("chat_id") or "")
                    callback_message_id = str(getattr(message_obj, "message_id", "") or payload.get("message_id") or "")
                    mapping_path, mapping = _approval_mapping_for_callback(
                        platform="telegram",
                        chat_id=callback_chat_id,
                        approval_id=approval_id,
                        message_id=callback_message_id,
                    )
                    session_key = str(mapping.get("session_key") or "")
                    if session_key:
                        try:
                            getattr(adapter, "_approval_state", {})[approval_id] = session_key
                        except Exception:
                            pass
                        try:
                            from tools import approval as approval_tools

                            original_resolve = approval_tools.resolve_gateway_approval

                            def _resolve_with_durable_choice(
                                resolved_session: str,
                                choice: str,
                                resolve_all: bool = False,
                            ) -> int:
                                if resolved_session == session_key and mapping_path is not None:
                                    _record_approval_choice(
                                        _approval_paths(
                                            platform="telegram",
                                            chat_id=callback_chat_id,
                                            approval_id=approval_id,
                                            message_id=callback_message_id,
                                        ),
                                        choice,
                                    )
                                return original_resolve(resolved_session, choice, resolve_all)

                            approval_tools.resolve_gateway_approval = _resolve_with_durable_choice
                        except Exception:
                            pass
        try:
            original_answer = callback.answer

            async def _safe_answer(*args: Any, **kwargs: Any) -> Any:
                try:
                    return await original_answer(*args, **kwargs)
                except Exception as exc:  # Telegram callback ids may already be acked by ArcLink ingress.
                    text = str(exc)
                    if (
                        "Query is too old" in text
                        or "query id is invalid" in text
                        or "response timeout expired" in text
                    ):
                        return None
                    raise

            setattr(callback, "answer", _safe_answer)
        except Exception:
            pass
        handler = getattr(adapter, "_handle_callback_query", None)
        if callable(handler):
            await handler(update, context)
            return True
        return False

    # PTB exposes edited messages as update.edited_message; Hermes treats an
    # edit as a fresh message, so replaying it through the same handlers keeps
    # native parity (text, captions, and media all re-enter) instead of
    # degrading the edit to a placeholder turn.
    message = getattr(update, "message", None) or getattr(update, "edited_message", None)
    if message is None:
        return False

    if getattr(message, "text", None):
        handler_name = "_handle_command" if str(message.text or "").strip().startswith("/") else "_handle_text_message"
        handler = getattr(adapter, handler_name, None)
        if callable(handler):
            await handler(update, context)
            return True
        return False

    if getattr(message, "location", None) is not None or getattr(message, "venue", None) is not None:
        handler = getattr(adapter, "_handle_location_message", None)
        if callable(handler):
            await handler(update, context)
            return True
        return False

    media_fields = ("photo", "video", "audio", "voice", "document", "sticker")
    if any(getattr(message, field, None) for field in media_fields):
        handler = getattr(adapter, "_handle_media_message", None)
        if callable(handler):
            await handler(update, context)
            return True
        return False

    return False


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
    _enable_public_bridge_gateway_defaults(cfg)
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
                body: dict[str, Any] = {
                    "content": chunk,
                    # Default-deny mass mentions: agent output must never ping
                    # @everyone/@here or roles, matching native Hermes policy.
                    "allowed_mentions": {"parse": ["users"], "replied_user": True},
                }
                meta = metadata or {}
                if idx == 0:
                    components = meta.get("discord_components")
                    embeds = meta.get("discord_embeds")
                    attachments = meta.get("discord_attachments")
                    if isinstance(components, list):
                        body["components"] = [dict(item) for item in components[:5] if isinstance(item, Mapping)]
                    if isinstance(embeds, list):
                        body["embeds"] = [dict(item) for item in embeds[:10] if isinstance(item, Mapping)]
                    if isinstance(attachments, list):
                        body["attachments"] = [dict(item) for item in attachments[:10] if isinstance(item, Mapping)]
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
            message_type=MessageType.COMMAND if _is_slash_command(text) else MessageType.TEXT,
            source=source,
            raw_message=_DiscordRawMessage(rest=rest, channel_id=channel_id, message_id=message_id),
            message_id=message_id or None,
        )
        await adapter.handle_message(event)
        await _drain_bridge_adapter_tasks(adapter)


async def _run(payload: Mapping[str, Any]) -> None:
    _apply_public_bridge_options(payload)
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
