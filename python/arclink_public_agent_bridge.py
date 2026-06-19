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
import hmac
import json
import os
import stat
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


class _DeliveryEvidence:
    """Collect platform send/edit acknowledgements from the short-lived bridge."""

    def __init__(self) -> None:
        self.message_ids: list[str] = []
        self.events: list[dict[str, Any]] = []

    def _add_message_ids(self, *values: Any) -> list[str]:
        added: list[str] = []
        for value in values:
            if isinstance(value, (list, tuple)):
                added.extend(self._add_message_ids(*value))
                continue
            clean = str(value or "").strip()
            if not clean or clean in self.message_ids:
                continue
            self.message_ids.append(clean)
            added.append(clean)
        return added

    @staticmethod
    def _raw_message_ids(raw_response: Any) -> list[str]:
        if not isinstance(raw_response, Mapping):
            return []
        raw_ids = raw_response.get("message_ids")
        if isinstance(raw_ids, list):
            return [str(item).strip() for item in raw_ids if str(item or "").strip()]
        raw_id = str(raw_response.get("message_id") or raw_response.get("id") or "").strip()
        return [raw_id] if raw_id else []

    def record_result(
        self,
        action: str,
        result: Any,
        *,
        content: Any = "",
        finalize: bool = False,
        force_visible: bool = False,
    ) -> None:
        success = bool(getattr(result, "success", False))
        error = str(getattr(result, "error", "") or "").strip()
        raw_response = getattr(result, "raw_response", None)
        ids = self._raw_message_ids(raw_response)
        primary_id = str(getattr(result, "message_id", "") or "").strip()
        if primary_id:
            ids.insert(0, primary_id)
        continuations = getattr(result, "continuation_message_ids", ()) or ()
        ids.extend(str(item).strip() for item in continuations if str(item or "").strip())

        visible = force_visible or bool(str(content or "").strip())
        if success and visible:
            added = self._add_message_ids(ids)
            status = "confirmed" if added or ids else "unknown"
        elif not success and (visible or finalize):
            status = "failed"
            added = []
        else:
            return
        self.events.append(
            {
                "action": action,
                "status": status,
                "message_ids": added,
                "finalize": bool(finalize),
                "error": error[:220],
            }
        )

    def summary(self) -> dict[str, Any]:
        relevant = [event for event in self.events if str(event.get("status") or "")]
        if not relevant:
            status = "unknown"
            error = "bridge completed without an observed platform send acknowledgement"
        else:
            last = relevant[-1]
            status = str(last.get("status") or "unknown")
            error = str(last.get("error") or "")
            if status == "confirmed" and not self.message_ids:
                status = "unknown"
                error = "bridge observed a send success without a platform message id"
        return {
            "processed": True,
            "delivered": status == "confirmed" and bool(self.message_ids),
            "delivery_status": status,
            "message_ids": list(self.message_ids),
            "delivery_error": error[:500],
        }


def _content_arg(args: tuple[Any, ...], kwargs: Mapping[str, Any], index: int, *names: str) -> Any:
    for name in names:
        if name in kwargs:
            return kwargs.get(name)
    if len(args) > index:
        return args[index]
    return ""


def _install_delivery_evidence(adapter: Any, evidence: _DeliveryEvidence) -> None:
    def _wrap(method_name: str, *, content_index: int, force_visible: bool = False) -> None:
        original = getattr(adapter, method_name, None)
        if not callable(original):
            return

        async def _wrapped(*args: Any, **kwargs: Any) -> Any:
            result = await original(*args, **kwargs)
            content = _content_arg(args, kwargs, content_index, "content", "message", "description", "title")
            evidence.record_result(
                method_name,
                result,
                content=content,
                finalize=bool(kwargs.get("finalize")),
                force_visible=force_visible,
            )
            return result

        try:
            setattr(adapter, method_name, _wrapped)
        except Exception:
            pass

    _wrap("send", content_index=1)
    _wrap("edit_message", content_index=2)
    _wrap("send_exec_approval", content_index=1, force_visible=True)
    _wrap("send_slash_confirm", content_index=2, force_visible=True)
    _wrap("send_clarify", content_index=1, force_visible=True)
    _wrap("send_image", content_index=2, force_visible=True)
    _wrap("send_image_file", content_index=2, force_visible=True)
    _wrap("send_document", content_index=2, force_visible=True)
    _wrap("send_video", content_index=2, force_visible=True)
    _wrap("send_voice", content_index=2, force_visible=True)


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


def _restore_env(snapshot: Mapping[str, str]) -> None:
    for key, value in snapshot.items():
        os.environ[key] = value


def _unused_platform_env_prefixes(target_platform: str) -> tuple[str, ...]:
    platform = str(target_platform or "").strip().lower()
    if platform == "telegram":
        return ("DISCORD_",)
    if platform == "discord":
        return ("TELEGRAM_",)
    return ()


def _load_gateway_config_for_platform(load_gateway_config: Any, target_platform: str) -> Any:
    if not BRIDGE_SINGLE_PLATFORM_CONFIG_ENABLED:
        return load_gateway_config()

    prefixes = _unused_platform_env_prefixes(target_platform)
    if not prefixes:
        return load_gateway_config()

    keys = [key for key in list(os.environ) if any(key.startswith(prefix) for prefix in prefixes)]
    snapshot = {key: os.environ[key] for key in keys if key in os.environ}
    if not snapshot:
        return load_gateway_config()

    for key in snapshot:
        os.environ.pop(key, None)
    try:
        try:
            return load_gateway_config()
        except Exception:
            # Safe L1 fallback: restore the untouched environment and run the
            # same Hermes config loader the bridge used before this flag.
            _restore_env(snapshot)
            return load_gateway_config()
    finally:
        _restore_env(snapshot)


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
TRUE_VALUES = {"1", "true", "yes", "on"}
BRIDGE_STATE_DIRNAME = "arclink-public-bridge"
APPROVAL_POLL_SECONDS = 0.25
BRIDGE_GETME_CACHE_DEFAULT_TTL_SECONDS = 180
BRIDGE_GETME_CACHE_MAX_TTL_SECONDS = 300
BRIDGE_GETME_CACHE_DEFAULT_DIR = "/var/cache/arclink-public-agent-bridge/getme"
BRIDGE_GETME_PRELOADED_USER_ENV = "ARCLINK_BRIDGE_GETME_PRELOADED_USER_JSON"


def _bool_env(name: str, *, default: bool = False) -> bool:
    text = str(os.environ.get(name, "") or "").strip().lower()
    if not text:
        return default
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    return default


def _int_env_clamped(name: str, *, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(os.environ.get(name, "") or "").strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


BRIDGE_SINGLE_PLATFORM_CONFIG_ENABLED = _bool_env("ARCLINK_BRIDGE_SINGLE_PLATFORM_CONFIG", default=False)
BRIDGE_GETME_CACHE_ENABLED = _bool_env("ARCLINK_BRIDGE_GETME_CACHE", default=False)
BRIDGE_GETME_CACHE_TTL_SECONDS = _int_env_clamped(
    "ARCLINK_BRIDGE_GETME_CACHE_TTL_SECONDS",
    default=BRIDGE_GETME_CACHE_DEFAULT_TTL_SECONDS,
    minimum=1,
    maximum=BRIDGE_GETME_CACHE_MAX_TTL_SECONDS,
)


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


def _read_first_line(path_value: str) -> str:
    if not path_value:
        return ""
    try:
        path = Path(path_value)
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return ""
    return lines[0].strip() if lines else ""


_BRIDGE_GETME_CACHE_SECRET_MISSING_LOGGED = False


def _bridge_getme_cache_secret() -> bytes:
    """Resolve the DEDICATED getMe L2 cache secret -- and ONLY that secret.

    H2 fix: the cache key is HMAC(secret, bot_token). The writer is the root
    wrapper (arclink_public_agent_bridge_root) and the reader is this bridge child;
    they MUST derive the same key or every turn silently L2-misses. The previous
    chain mixed the session pepper, the operator-action-auth secret, and the web
    session/SSO secrets and fell back across them, so writer and reader could pick
    DIFFERENT secrets across reboots (whichever happened to be present first),
    causing permanent silent cache drift -- and it over-broadened the
    operator-action secret into a second, unrelated use.

    We now read ONLY the purpose-built secret, from purpose-built locations:
      * ARCLINK_BRIDGE_GETME_CACHE_SECRET_FILE (explicit override), then
      * <ARCLINK_OPERATOR_SECRET_DIR>/public-agent-bridge-getme-cache-secret, then
      * <ARCLINK_PRIV_DIR>/state/operator/secrets/public-agent-bridge-getme-cache-secret
    All three resolve to the same dedicated secret material, so writer and reader
    are stable. If none is present, L2 is disabled (callers get path None) and we
    log ONCE rather than silently falling back to a drift-prone shared secret.
    """
    candidates: list[str] = []
    explicit_file = str(os.environ.get("ARCLINK_BRIDGE_GETME_CACHE_SECRET_FILE") or "").strip()
    if explicit_file:
        candidates.append(_read_first_line(explicit_file))

    operator_secret_dir = str(os.environ.get("ARCLINK_OPERATOR_SECRET_DIR") or "").strip()
    if operator_secret_dir:
        candidates.append(_read_first_line(str(Path(operator_secret_dir) / "public-agent-bridge-getme-cache-secret")))

    priv_dir = str(os.environ.get("ARCLINK_PRIV_DIR") or "").strip()
    if priv_dir:
        priv_path = Path(priv_dir)
        candidates.append(
            _read_first_line(str(priv_path / "state" / "operator" / "secrets" / "public-agent-bridge-getme-cache-secret"))
        )

    for candidate in candidates:
        if candidate and candidate not in {"change-me", "changeme"}:
            return candidate.encode("utf-8")

    global _BRIDGE_GETME_CACHE_SECRET_MISSING_LOGGED
    if not _BRIDGE_GETME_CACHE_SECRET_MISSING_LOGGED:
        _BRIDGE_GETME_CACHE_SECRET_MISSING_LOGGED = True
        try:
            sys.stderr.write(
                "arclink-public-agent-bridge: dedicated getMe L2 cache secret not found "
                "(ARCLINK_BRIDGE_GETME_CACHE_SECRET_FILE / operator/secrets/"
                "public-agent-bridge-getme-cache-secret); L2 getMe cache disabled.\n"
            )
        except Exception:  # noqa: BLE001 - logging must never break the bridge.
            pass
    return b""


def _bridge_getme_cache_key(bot_token: str) -> str:
    secret = _bridge_getme_cache_secret()
    if not secret:
        return ""
    return hmac.new(secret, str(bot_token or "").encode("utf-8"), hashlib.sha256).hexdigest()


def _resolved_path(path: Path) -> Path:
    try:
        return path.expanduser().resolve(strict=False)
    except Exception:
        return path.expanduser().absolute()


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _bridge_getme_cache_outside_agent_roots(path: Path) -> bool:
    resolved = _resolved_path(path)
    roots: list[str] = []
    for name in (
        "HERMES_HOME",
        "VAULT_DIR",
        "DRIVE_ROOT",
        "CODE_WORKSPACE_ROOT",
        "TERMINAL_WORKSPACE_ROOT",
        "ARCLINK_WORKSPACE_ROOT",
        "ARCLINK_DRIVE_ROOT",
        "ARCLINK_CODE_WORKSPACE_ROOT",
    ):
        value = str(os.environ.get(name) or "").strip()
        if value:
            roots.append(value)
    for root_value in roots:
        root = _resolved_path(Path(root_value))
        if resolved == root or _path_is_within(resolved, root):
            return False
    return True


def _bridge_getme_secure_cache_dir() -> Path | None:
    if not BRIDGE_GETME_CACHE_ENABLED:
        return None
    raw_path = str(os.environ.get("ARCLINK_BRIDGE_GETME_CACHE_DIR") or BRIDGE_GETME_CACHE_DEFAULT_DIR).strip()
    if not raw_path:
        return None
    path = Path(raw_path)
    if not _bridge_getme_cache_outside_agent_roots(path):
        return None
    try:
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
        lst = path.lstat()
        if stat.S_ISLNK(lst.st_mode):
            return None
        os.chmod(path, 0o700)
        st = path.stat()
        if not stat.S_ISDIR(st.st_mode):
            return None
        if st.st_uid != 0:
            return None
        if stat.S_IMODE(st.st_mode) != 0o700:
            return None
        probe = path / ".probe"
        fd = os.open(str(probe), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, b"ok\n")
        finally:
            os.close(fd)
        try:
            probe.unlink()
        except OSError:
            pass
        return path
    except Exception:
        return None


def _bridge_getme_cache_path(bot_token: str) -> Path | None:
    cache_dir = _bridge_getme_secure_cache_dir()
    if cache_dir is None:
        return None
    key = _bridge_getme_cache_key(bot_token)
    if not key:
        return None
    return cache_dir / f"{key}.json"


def _read_getme_cache(path: Path) -> dict[str, Any]:
    data = _json_read(path)
    if not data:
        return {}
    try:
        expires_at = int(data.get("expires_at") or 0)
    except (TypeError, ValueError):
        return {}
    if expires_at <= int(time.time()):
        return {}
    bot_user = data.get("bot_user")
    if not isinstance(bot_user, dict) or not bot_user:
        return {}
    return bot_user


def _preloaded_getme_user() -> dict[str, Any]:
    raw = str(os.environ.get(BRIDGE_GETME_PRELOADED_USER_ENV) or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return dict(data) if isinstance(data, Mapping) else {}


def _telegram_user_from_cache(bot: Any, bot_user: Mapping[str, Any]) -> Any | None:
    try:
        from telegram import User

        de_json = getattr(User, "de_json", None)
        if callable(de_json):
            return de_json(dict(bot_user), bot)
    except Exception:
        return None
    return None


def _apply_cached_telegram_getme(bot: Any, bot_user: Mapping[str, Any]) -> bool:
    if not hasattr(bot, "_bot_user") or not hasattr(bot, "_initialized"):
        return False
    user = _telegram_user_from_cache(bot, bot_user)
    if user is None:
        return False
    try:
        setattr(bot, "_bot_user", user)
        setattr(bot, "_initialized", True)
    except Exception:
        return False
    return bool(getattr(bot, "_initialized", False))


def _bot_user_to_cache_dict(bot: Any) -> dict[str, Any]:
    try:
        user = getattr(bot, "_bot_user", None)
    except Exception:
        return {}
    if user is None:
        return {}
    if isinstance(user, Mapping):
        data = dict(user)
    else:
        to_dict = getattr(user, "to_dict", None)
        if callable(to_dict):
            try:
                raw = to_dict()
            except Exception:
                raw = {}
            data = dict(raw) if isinstance(raw, Mapping) else {}
        else:
            data = {}
            for name in ("id", "is_bot", "first_name", "last_name", "username"):
                try:
                    value = getattr(user, name)
                except Exception:
                    continue
                if value is not None:
                    data[name] = value
    if not data.get("id") and not data.get("username"):
        return {}
    return data


def _write_getme_cache(path: Path, bot: Any) -> None:
    bot_user = _bot_user_to_cache_dict(bot)
    if not bot_user:
        return
    now = int(time.time())
    try:
        _json_write(
            path,
            {
                "cached_at": now,
                "expires_at": now + BRIDGE_GETME_CACHE_TTL_SECONDS,
                "bot_user": bot_user,
            },
        )
    except Exception:
        return


async def _initialize_telegram_bot(bot: Any, bot_token: str) -> None:
    preloaded_user = _preloaded_getme_user()
    if preloaded_user and _apply_cached_telegram_getme(bot, preloaded_user):
        return

    cache_path: Path | None = None
    if BRIDGE_GETME_CACHE_ENABLED:
        try:
            cache_path = _bridge_getme_cache_path(bot_token)
            if cache_path is not None:
                bot_user = _read_getme_cache(cache_path)
                if bot_user and _apply_cached_telegram_getme(bot, bot_user):
                    return
        except Exception:
            cache_path = None

    await bot.initialize()

    if BRIDGE_GETME_CACHE_ENABLED:
        try:
            cache_path = cache_path or _bridge_getme_cache_path(bot_token)
            if cache_path is not None:
                _write_getme_cache(cache_path, bot)
        except Exception:
            return


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


async def _run_telegram(payload: Mapping[str, Any]) -> dict[str, Any]:
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

    cfg = _load_gateway_config_for_platform(load_gateway_config, "telegram")
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
    evidence = _DeliveryEvidence()
    _install_delivery_evidence(adapter, evidence)

    bot = Bot(token=bot_token)
    await _initialize_telegram_bot(bot, bot_token)
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
            # Only synthesize + dispatch a generic MessageEvent when native replay did
            # NOT already handle the update. When replayed is True the native handler
            # already delivered the turn and `event` is intentionally unbound — calling
            # adapter.handle_message(event) here would UnboundLocalError, fail the turn,
            # and retry a duplicate send of an already-delivered message.
            event = MessageEvent(
                text=text,
                message_type=MessageType.COMMAND if _is_slash_command(text) else MessageType.TEXT,
                source=source,
                message_id=message_id,
            )
            await adapter.handle_message(event)
        await _drain_bridge_adapter_tasks(adapter)
        _persist_telegram_bridge_state(runner, source)
        return evidence.summary()
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


async def _run_discord(payload: Mapping[str, Any]) -> dict[str, Any]:
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

    cfg = _load_gateway_config_for_platform(load_gateway_config, "discord")
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
        evidence = _DeliveryEvidence()
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
            result = SendResult(
                success=True,
                message_id=sent_ids[0] if sent_ids else None,
                raw_response={"message_ids": sent_ids},
            )
            evidence.record_result("send", result, content=content)
            return result

        async def _edit_message(chat_id: str, message_id_arg: str, content: str, *, finalize: bool = False) -> SendResult:
            target_channel = str(chat_id or channel_id)
            chunks = adapter.truncate_message(adapter.format_message(content), getattr(adapter, "MAX_MESSAGE_LENGTH", 2000))
            await rest.request(
                "PATCH",
                f"/channels/{target_channel}/messages/{message_id_arg}",
                payload={"content": (chunks[0] if chunks else "")},
            )
            result = SendResult(success=True, message_id=message_id_arg)
            evidence.record_result("edit_message", result, content=content, finalize=finalize)
            return result

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
        return evidence.summary()


async def _run(payload: Mapping[str, Any]) -> dict[str, Any]:
    _apply_public_bridge_options(payload)
    platform = str(payload.get("platform") or "").strip().lower()
    if platform == "telegram":
        return await _run_telegram(payload)
    if platform == "discord":
        return await _run_discord(payload)
    raise RuntimeError(f"public agent gateway bridge does not support platform {platform or 'blank'} yet")


def main() -> int:
    try:
        payload = _payload_from_stdin()
        result = asyncio.run(_run(payload))
    except Exception as exc:  # noqa: BLE001 - boundary process returns structured failure
        return _json_error(str(exc))
    response = {"ok": True}
    response.update(result)
    print(json.dumps(response, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
