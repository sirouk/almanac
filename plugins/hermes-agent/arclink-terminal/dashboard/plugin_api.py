from __future__ import annotations

import atexit
import asyncio
import errno
import fcntl
import json
import os
import pty
import re
import signal
import shlex
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from typing import Any
import uuid

try:
    from fastapi import APIRouter, HTTPException, Request
    from fastapi.responses import StreamingResponse
except Exception:
    class HTTPException(Exception):  # type: ignore
        def __init__(self, status_code: int = 500, detail: str = "") -> None:
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class APIRouter:  # type: ignore
        def get(self, *_args, **_kwargs):
            return lambda fn: fn

        def post(self, *_args, **_kwargs):
            return lambda fn: fn

    class Request:  # type: ignore
        pass

    class StreamingResponse:  # type: ignore
        def __init__(self, content, media_type: str = "", headers: dict[str, str] | None = None) -> None:
            self.body_iterator = content
            self.media_type = media_type
            self.headers = headers or {}


router = APIRouter()

_STATE_VERSION = 1
_MAX_INPUT_BYTES = 8_000
_MAX_READ_BYTES = 64_000
_DEFAULT_MAX_SESSIONS = 6
_DEFAULT_SCROLLBACK_BYTES = 32_000
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
_SSH_TARGET_RE = re.compile(r"^[A-Za-z0-9_.@:-]{1,180}$")
_DEFAULT_TUI_COMMAND = "/opt/arclink/runtime/hermes-venv/bin/hermes"
_DEFAULT_TUI_DIR = "/opt/arclink/runtime/hermes-agent-src/ui-tui"
_RUNTIMES: dict[str, dict[str, Any]] = {}


def _cleanup_runtimes() -> None:
    for session_id, runtime in list(_RUNTIMES.items()):
        process = runtime.get("process")
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except Exception:
                pass
        try:
            os.close(int(runtime.get("fd")))
        except Exception:
            pass
        _RUNTIMES.pop(session_id, None)


atexit.register(_cleanup_runtimes)


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes")).expanduser()


def _state_dir() -> Path:
    return _hermes_home() / "state" / "arclink-terminal"


def _sessions_path() -> Path:
    return _state_dir() / "sessions.json"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".arclink-terminal-", suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _workspace_root() -> Path:
    for key in ("ARCLINK_TERMINAL_WORKSPACE_ROOT", "ARCLINK_CODE_WORKSPACE_ROOT", "HOME"):
        value = str(os.environ.get(key) or "").strip()
        if value:
            return Path(value).expanduser().resolve(strict=False)
    return Path.home().expanduser().resolve(strict=False)


def _shell_path() -> str:
    for value in (os.environ.get("ARCLINK_TERMINAL_SHELL"), os.environ.get("SHELL"), "/bin/bash", "/bin/sh"):
        text = str(value or "").strip()
        if text and Path(text).is_absolute() and os.access(text, os.X_OK):
            return text
    return ""


def _shell_name() -> str:
    shell = _shell_path()
    if not shell:
        return "sh"
    return Path(shell).name or "sh"


def _clean_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(str(value or "").strip())
    except ValueError:
        return default
    return max(minimum, min(maximum, parsed))


def _max_sessions() -> int:
    return _clean_int(os.environ.get("ARCLINK_TERMINAL_MAX_SESSIONS"), _DEFAULT_MAX_SESSIONS, 1, 24)


def _scrollback_limit() -> int:
    return _clean_int(os.environ.get("ARCLINK_TERMINAL_SCROLLBACK_BYTES"), _DEFAULT_SCROLLBACK_BYTES, 4_000, 250_000)


def _runtime_user_safe() -> bool:
    if not hasattr(os, "geteuid"):
        return True
    return os.geteuid() != 0 or str(os.environ.get("ARCLINK_TERMINAL_ALLOW_ROOT") or "").strip() == "1"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _clean_name(value: Any, default: str = "Terminal") -> str:
    text = " ".join(str(value or "").split())
    return (text or default)[:80]


def _clean_folder(value: Any) -> str:
    text = " ".join(str(value or "").split())
    return text[:80]


def _clean_session_mode(value: Any) -> str:
    mode = str(value or "shell").strip().lower()
    return mode if mode in {"shell", "ssh", "tui"} else "shell"


def _clean_ssh_target(value: Any) -> str:
    text = str(value or "").strip()
    if not text or not _SSH_TARGET_RE.match(text):
        raise HTTPException(status_code=400, detail="A safe SSH target like user@host is required")
    return text


def _clean_relative_path(raw_path: Any) -> str:
    text = str(raw_path or "/").replace("\\", "/").strip()
    if text in {"", "/", "."}:
        return ""
    text = text.lstrip("/")
    parts: list[str] = []
    for part in text.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            raise HTTPException(status_code=400, detail="Path traversal is not allowed")
        parts.append(part)
    return "/".join(parts)


def _display_path(relative_path: str) -> str:
    return "/" + relative_path.strip("/") if relative_path else "/"


def _resolve_cwd(raw_path: Any) -> tuple[Path, str]:
    root = _workspace_root()
    relative = _clean_relative_path(raw_path)
    target = (root / relative).resolve(strict=False)
    if target != root and root not in target.parents:
        raise HTTPException(status_code=403, detail="Terminal cwd is outside the ArcLink workspace")
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="Terminal cwd does not exist")
    return target, relative


def _resolve_machine_cwd(raw_path: Any) -> tuple[Path, str]:
    text = str(raw_path or "/").replace("\\", "/").strip() or "/"
    if not text.startswith("/"):
        text = "/" + _clean_relative_path(text)
    target = Path(text).expanduser().resolve(strict=False)
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="Terminal cwd does not exist")
    display = "/" if str(target) == "/" else str(target)
    return target, display


def _resolve_session_cwd(mode: str, raw_path: Any) -> tuple[Path, str]:
    if mode == "ssh":
        return _resolve_machine_cwd(raw_path)
    return _resolve_cwd(raw_path)


def _clean_session_id(value: Any) -> str:
    session_id = str(value or "").strip()
    if not session_id or not _SESSION_ID_RE.match(session_id):
        raise HTTPException(status_code=400, detail="A valid terminal session id is required")
    return session_id


def _redact_text(value: Any) -> str:
    text = str(value or "")
    replacements = {
        str(_workspace_root()): "[workspace]",
        str(_hermes_home()): "[hermes-home]",
        str(Path.home().expanduser()): "[home]",
    }
    for needle, replacement in replacements.items():
        if needle and needle != "/":
            text = text.replace(needle, replacement)
    text = re.sub(r"(?i)(token|password|secret|key)=\S+", r"\1=[redacted]", text)
    return text[:600]


def _sanitize_scrollback(value: Any) -> str:
    text = str(value or "")
    limit = _scrollback_limit()
    if len(text.encode("utf-8", errors="ignore")) <= limit:
        return text
    encoded = text.encode("utf-8", errors="ignore")[-limit:]
    return encoded.decode("utf-8", errors="ignore")


def _load_sessions() -> dict[str, Any]:
    payload = _load_json(_sessions_path())
    sessions = payload.get("sessions")
    if not isinstance(sessions, list):
        sessions = []
    return {"version": _STATE_VERSION, "sessions": [entry for entry in sessions if isinstance(entry, dict)]}


def _save_sessions(payload: dict[str, Any]) -> None:
    payload["version"] = _STATE_VERSION
    _write_json_atomic(_sessions_path(), payload)


def _session_payload(entry: dict[str, Any], *, include_scrollback: bool = True) -> dict[str, Any]:
    payload = {
        "id": str(entry.get("id") or ""),
        "name": _clean_name(entry.get("name"), "Terminal"),
        "folder": _clean_folder(entry.get("folder")),
        "order": int(entry.get("order") or 0),
        "cwd": _display_path(str(entry.get("cwd") or "")),
        "shell": _shell_name(),
        "backend": "managed-pty",
        "mode": _clean_session_mode(entry.get("mode")),
        "target": _clean_name(entry.get("target"), ""),
        "state": str(entry.get("state") or "closed"),
        "created_at": str(entry.get("created_at") or ""),
        "updated_at": str(entry.get("updated_at") or ""),
        "exit_code": entry.get("exit_code"),
    }
    if include_scrollback:
        payload["scrollback"] = _sanitize_scrollback(entry.get("scrollback") or "")
    return payload


def _sse_event(event: str, payload: dict[str, Any]) -> str:
    data = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return f"event: {event}\ndata: {data}\n\n"


def _find_session(payload: dict[str, Any], session_id: str) -> dict[str, Any]:
    for entry in payload["sessions"]:
        if str(entry.get("id") or "") == session_id:
            return entry
    raise HTTPException(status_code=404, detail="Terminal session was not found")


def _active_sessions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [entry for entry in payload["sessions"] if str(entry.get("state") or "") in {"starting", "running"}]


def _runtime(session_id: str) -> dict[str, Any] | None:
    runtime = _RUNTIMES.get(session_id)
    process = runtime.get("process") if isinstance(runtime, dict) else None
    if process is None:
        return None
    return runtime


def _append_scrollback(entry: dict[str, Any], text: str) -> None:
    if not text:
        return
    entry["scrollback"] = _sanitize_scrollback(str(entry.get("scrollback") or "") + text)
    entry["updated_at"] = _now()


def _read_runtime(entry: dict[str, Any]) -> bool:
    session_id = str(entry.get("id") or "")
    runtime = _runtime(session_id)
    if not runtime:
        if str(entry.get("state") or "") in {"starting", "running"}:
            entry["state"] = "detached"
            entry["updated_at"] = _now()
            return True
        return False
    changed = False
    fd = int(runtime["fd"])
    total = 0
    while total < _MAX_READ_BYTES:
        try:
            chunk = os.read(fd, min(4096, _MAX_READ_BYTES - total))
        except BlockingIOError:
            break
        except OSError as exc:
            if exc.errno in {errno.EIO, errno.EBADF}:
                break
            _append_scrollback(entry, "\n[terminal backend error: " + _redact_text(exc) + "]\n")
            changed = True
            break
        if not chunk:
            break
        total += len(chunk)
        _append_scrollback(entry, chunk.decode("utf-8", errors="replace"))
        changed = True
    process: subprocess.Popen[bytes] = runtime["process"]
    exit_code = process.poll()
    if exit_code is not None:
        entry["state"] = "exited"
        entry["exit_code"] = exit_code
        entry["updated_at"] = _now()
        try:
            os.close(fd)
        except OSError:
            pass
        _RUNTIMES.pop(session_id, None)
        changed = True
    elif str(entry.get("state") or "") == "starting":
        entry["state"] = "running"
        entry["updated_at"] = _now()
        changed = True
    return changed


def _poll_sessions(payload: dict[str, Any]) -> bool:
    changed = False
    for entry in payload["sessions"]:
        changed = _read_runtime(entry) or changed
    if changed:
        _save_sessions(payload)
    return changed


def _runtime_argv(entry: dict[str, Any]) -> tuple[list[str], str]:
    mode = _clean_session_mode(entry.get("mode"))
    if mode == "ssh":
        shell = _shell_path()
        if not shell:
            raise HTTPException(status_code=503, detail="No supported terminal shell is available")
        return [shell, "-i"], "Machine Terminal"
    if mode == "tui":
        raw_command = str(os.environ.get("ARCLINK_TERMINAL_TUI_COMMAND") or _DEFAULT_TUI_COMMAND).strip()
        argv = shlex.split(raw_command)
        if not argv:
            raise HTTPException(status_code=503, detail="Hermes TUI command is not configured")
        if not Path(argv[0]).is_absolute():
            executable = shutil.which(argv[0]) or ""
            if not executable:
                raise HTTPException(status_code=503, detail="Hermes TUI command is not installed")
            argv[0] = executable
        return argv, "Hermes TUI"
    shell = _shell_path()
    if not shell:
        raise HTTPException(status_code=503, detail="No supported terminal shell is available")
    return [shell, "-i"], "Terminal"


def _tui_dist_available() -> bool:
    tui_dir = Path(os.environ.get("HERMES_TUI_DIR") or _DEFAULT_TUI_DIR).expanduser()
    return (tui_dir / "dist" / "entry.js").is_file() and (tui_dir / "node_modules").is_dir()


def _start_runtime(entry: dict[str, Any]) -> None:
    argv, label = _runtime_argv(entry)
    mode = _clean_session_mode(entry.get("mode"))
    cwd, cwd_display = _resolve_session_cwd(mode, entry.get("cwd") or "/")
    entry["cwd"] = cwd_display
    session_id = str(entry.get("id") or "")
    master_fd, slave_fd = pty.openpty()
    env = os.environ.copy()
    env["TERM"] = env.get("TERM") or "xterm-256color"
    env["PS1"] = "$ "
    if mode == "tui":
        env.setdefault("HERMES_TUI_DIR", _DEFAULT_TUI_DIR)
    try:
        process = subprocess.Popen(
            argv,
            cwd=str(cwd),
            env=env,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
            start_new_session=True,
        )
    except Exception as exc:
        try:
            os.close(master_fd)
            os.close(slave_fd)
        except OSError:
            pass
        raise HTTPException(status_code=503, detail="Terminal backend failed to start: " + _redact_text(exc))
    os.close(slave_fd)
    flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
    fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    _RUNTIMES[session_id] = {"process": process, "fd": master_fd}
    entry["state"] = "starting"
    entry["exit_code"] = None
    _append_scrollback(entry, "ArcLink " + label + " session ready. Cwd: " + _display_path(str(entry.get("cwd") or "")) + "\n")
    time.sleep(0.05)
    _read_runtime(entry)


def _status_payload() -> dict[str, Any]:
    workspace_root = _workspace_root()
    tmux_path = shutil.which("tmux") or ""
    shell = _shell_path()
    tui_command = str(os.environ.get("ARCLINK_TERMINAL_TUI_COMMAND") or _DEFAULT_TUI_COMMAND).strip()
    tui_argv = shlex.split(tui_command) if tui_command else []
    tui_command_available = bool(tui_argv and (Path(tui_argv[0]).is_absolute() or shutil.which(tui_argv[0])))
    tui_requires_dist = "--tui" in tui_argv
    tui_available = tui_command_available and (not tui_requires_dist or _tui_dist_available())
    runtime_user_safe = _runtime_user_safe()
    available = bool(shell and workspace_root.exists() and workspace_root.is_dir() and runtime_user_safe)
    return {
        "plugin": "arclink-terminal",
        "label": "ArcLink Terminal",
        "version": "0.2.0",
        "status_contract": 1,
        "available": available,
        "backend": "managed-pty" if available else "unavailable",
        "workspace_root": "[workspace]",
        "workspace_root_available": bool(workspace_root.exists() and workspace_root.is_dir()),
        "hermes_state": "[hermes-state]",
        "shell": _shell_name(),
        "runtime_user_safe": runtime_user_safe,
        "limits": {
            "max_sessions": _max_sessions(),
            "scrollback_bytes": _scrollback_limit(),
            "input_bytes": _MAX_INPUT_BYTES,
        },
        "backend_candidates": {
            "tmux": bool(tmux_path),
            "managed_pty": available,
        },
        "transport": {
            "mode": "sse",
            "stream_path": "/sessions/{session_id}/stream",
            "fallback": "polling",
            "fallback_poll_interval_ms": 1000,
        },
        "capabilities": {
            "persistent_sessions": available,
            "streaming_output": available,
            "bounded_scrollback": True,
            "reload_reconnect": available,
            "rename_sessions": available,
            "group_sessions": available,
            "reorder_sessions": available,
            "confirm_close_or_kill": True,
            "direct_input": available,
            "machine_terminal_sessions": available,
            "ssh_sessions": available,
            "hermes_tui_sessions": available and tui_available,
            "clear_closed_sessions": True,
        },
    }


@router.get("/status")
async def status() -> dict[str, Any]:
    return _status_payload()


@router.get("/sessions")
async def sessions() -> dict[str, Any]:
    payload = _load_sessions()
    _poll_sessions(payload)
    ordered = sorted(payload["sessions"], key=lambda entry: (int(entry.get("order") or 0), str(entry.get("created_at") or "")))
    return {
        "sessions": [_session_payload(entry, include_scrollback=False) for entry in ordered],
        "limits": _status_payload()["limits"],
        "transport": _status_payload()["transport"],
    }


@router.post("/sessions")
async def create_session(request: Request) -> dict[str, Any]:
    status_payload = _status_payload()
    if not status_payload["available"]:
        raise HTTPException(status_code=503, detail="Terminal backend is unavailable")
    body = await request.json()
    payload = _load_sessions()
    _poll_sessions(payload)
    if len(_active_sessions(payload)) >= _max_sessions():
        raise HTTPException(status_code=429, detail="Terminal session limit reached")
    mode = _clean_session_mode(body.get("mode"))
    cwd_path, cwd_relative = _resolve_session_cwd(mode, body.get("cwd") or "/")
    del cwd_path
    session_id = "term-" + uuid.uuid4().hex[:16]
    now = _now()
    entry = {
        "id": session_id,
        "name": _clean_name(body.get("name"), "Machine Terminal" if mode == "ssh" else "Hermes TUI" if mode == "tui" else "Terminal"),
        "folder": _clean_folder(body.get("folder")),
        "order": int(body.get("order") or len(payload["sessions"])),
        "cwd": cwd_relative,
        "shell": _shell_name(),
        "backend": "managed-pty",
        "mode": mode,
        "target": "",
        "state": "starting",
        "created_at": now,
        "updated_at": now,
        "exit_code": None,
        "scrollback": "",
    }
    _start_runtime(entry)
    payload["sessions"].append(entry)
    _save_sessions(payload)
    return {"session": _session_payload(entry)}


@router.post("/sessions/clear-closed")
async def clear_closed_sessions() -> dict[str, Any]:
    payload = _load_sessions()
    before = len(payload["sessions"])
    payload["sessions"] = [
        entry for entry in payload["sessions"]
        if str(entry.get("state") or "") not in {"closed", "exited"}
    ]
    removed = before - len(payload["sessions"])
    _save_sessions(payload)
    return {"ok": True, "removed": removed, "sessions": [_session_payload(entry, include_scrollback=False) for entry in payload["sessions"]]}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict[str, Any]:
    payload = _load_sessions()
    entry = _find_session(payload, _clean_session_id(session_id))
    _poll_sessions(payload)
    entry = _find_session(payload, session_id)
    return {"session": _session_payload(entry)}


@router.get("/sessions/{session_id}/stream")
async def stream_session(session_id: str, request: Request) -> StreamingResponse:
    clean_id = _clean_session_id(session_id)

    async def events():
        last_signature = ""
        last_heartbeat = 0.0
        while True:
            is_disconnected = getattr(request, "is_disconnected", None)
            if callable(is_disconnected) and await is_disconnected():
                break
            try:
                payload = _load_sessions()
                entry = _find_session(payload, clean_id)
                _poll_sessions(payload)
                entry = _find_session(payload, clean_id)
                session_payload = _session_payload(entry)
                signature = "|".join(
                    [
                        str(session_payload.get("state") or ""),
                        str(session_payload.get("updated_at") or ""),
                        str(session_payload.get("exit_code")),
                        str(len(str(session_payload.get("scrollback") or ""))),
                    ]
                )
                now = time.time()
                if signature != last_signature:
                    yield _sse_event("session", {"session": session_payload})
                    last_signature = signature
                    last_heartbeat = now
                elif now - last_heartbeat >= 15:
                    yield _sse_event("heartbeat", {"session_id": clean_id, "ts": _now()})
                    last_heartbeat = now
                if str(session_payload.get("state") or "") in {"closed", "exited", "detached"}:
                    break
            except HTTPException as exc:
                yield _sse_event(
                    "error",
                    {
                        "status_code": getattr(exc, "status_code", 500),
                        "detail": _redact_text(getattr(exc, "detail", "terminal stream failed")),
                    },
                )
                break
            await asyncio.sleep(0.4)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/sessions/{session_id}/input")
async def send_input(session_id: str, request: Request) -> dict[str, Any]:
    payload = _load_sessions()
    entry = _find_session(payload, _clean_session_id(session_id))
    _poll_sessions(payload)
    if str(entry.get("state") or "") not in {"starting", "running"}:
        raise HTTPException(status_code=409, detail="Terminal session is not running")
    runtime = _runtime(session_id)
    if not runtime:
        entry["state"] = "detached"
        _save_sessions(payload)
        raise HTTPException(status_code=409, detail="Terminal session is detached")
    body = await request.json()
    text = str(body.get("input") or "")
    if not text:
        return {"session": _session_payload(entry)}
    encoded = text.encode("utf-8", errors="ignore")
    if len(encoded) > _MAX_INPUT_BYTES:
        raise HTTPException(status_code=413, detail="Terminal input is too large")
    try:
        os.write(int(runtime["fd"]), encoded)
    except OSError as exc:
        _append_scrollback(entry, "\n[terminal input error: " + _redact_text(exc) + "]\n")
        _save_sessions(payload)
        raise HTTPException(status_code=503, detail="Terminal input failed")
    time.sleep(0.05)
    _poll_sessions(payload)
    entry = _find_session(payload, session_id)
    return {"session": _session_payload(entry)}


@router.post("/sessions/{session_id}/rename")
async def rename_session(session_id: str, request: Request) -> dict[str, Any]:
    payload = _load_sessions()
    entry = _find_session(payload, _clean_session_id(session_id))
    body = await request.json()
    if "name" in body:
        entry["name"] = _clean_name(body.get("name"), "Terminal")
    if "folder" in body:
        entry["folder"] = _clean_folder(body.get("folder"))
    if "order" in body:
        entry["order"] = int(body.get("order") or 0)
    entry["updated_at"] = _now()
    _poll_sessions(payload)
    _save_sessions(payload)
    return {"session": _session_payload(entry)}


@router.post("/sessions/{session_id}/close")
async def close_session(session_id: str, request: Request) -> dict[str, Any]:
    payload = _load_sessions()
    entry = _find_session(payload, _clean_session_id(session_id))
    body = await request.json()
    if body.get("confirm") is not True:
        raise HTTPException(status_code=400, detail="Closing a terminal session requires confirmation")
    runtime = _runtime(session_id)
    if runtime:
        process: subprocess.Popen[bytes] = runtime["process"]
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=2)
        except Exception:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except Exception:
                pass
        try:
            os.close(int(runtime["fd"]))
        except OSError:
            pass
        _RUNTIMES.pop(session_id, None)
    entry["state"] = "closed"
    entry["exit_code"] = entry.get("exit_code")
    _append_scrollback(entry, "\n[terminal session closed]\n")
    _save_sessions(payload)
    return {"session": _session_payload(entry)}
