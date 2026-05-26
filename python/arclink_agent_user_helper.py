#!/usr/bin/env python3
"""Root-scoped Docker agent user/home helper.

The Docker agent supervisor owns reconciliation and process supervision. This
helper owns only container-local Unix user creation and canonical Docker agent
home ownership repair. It rejects raw command input and validates all paths
before creating directories or invoking root user-management commands.
"""
from __future__ import annotations

import argparse
import grp
import hashlib
import hmac
import json
import os
import pwd
import re
import stat
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from arclink_boundary import require_docker_trusted_host_risk_accepted
from arclink_rejection_incidents import agent_home_root_rejection_path, record_rejection_incident


MAX_REQUEST_BYTES = 16384
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8915
AGENT_USER_HELPER_TOKEN_HEADER = "X-ArcLink-Agent-User-Helper-Token"
SAFE_AGENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$")
SAFE_UNIX_USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,30}$")
HERMES_HOME_SUFFIX = Path(".local/share/arclink-agent/hermes-home")
ALLOWED_OPERATIONS = {"ensure_user_home"}
AGENT_UID_MIN = 20000
AGENT_UID_SPAN = 40000
ASSIGNMENTS_FILE = ".arclink-user-ids.json"
ASSIGNMENTS_LOCK = threading.Lock()
TRUSTED_ROOT_EXECUTABLES = {
    "groupadd": Path("/usr/sbin/groupadd"),
    "useradd": Path("/usr/sbin/useradd"),
    "chown": Path("/usr/bin/chown"),
}
SERVICE_NAME = "agent-user-helper"


def _helper_token() -> str:
    return str(os.environ.get("ARCLINK_AGENT_USER_HELPER_TOKEN") or "").strip()


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _is_authorized(headers: Any) -> bool:
    expected = _helper_token()
    supplied = str(headers.get(AGENT_USER_HELPER_TOKEN_HEADER) or "").strip()
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def _require_safe_agent_id(value: Any) -> str:
    clean = str(value or "").strip()
    if not SAFE_AGENT_ID_RE.fullmatch(clean):
        raise ValueError("agent user helper agent_id is not a safe identifier")
    return clean


def _require_safe_unix_user(value: Any) -> str:
    clean = str(value or "").strip().lower()
    if not SAFE_UNIX_USER_RE.fullmatch(clean):
        raise ValueError("agent user helper unix_user is not a safe local account name")
    return clean


def _absolute_path(value: Any, *, label: str) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"agent user helper {label} is required")
    path = Path(os.path.normpath(raw))
    if not path.is_absolute():
        raise ValueError(f"agent user helper {label} must be absolute")
    if str(path) == "/":
        raise ValueError(f"agent user helper {label} must not be filesystem root")
    return path


def _require_no_symlink_components(path: Path, *, label: str) -> Path:
    path = _absolute_path(path, label=label)
    try:
        resolved = path.resolve(strict=False)
    except (OSError, RuntimeError):
        raise ValueError(f"agent user helper {label} is not a valid path") from None
    if resolved != path:
        raise ValueError(f"agent user helper {label} must not include symlink components")
    return path


def _configured_path(env_name: str, *, label: str) -> Path | None:
    raw = str(os.environ.get(env_name) or "").strip()
    if not raw:
        return None
    return _require_no_symlink_components(
        _absolute_path(raw, label=f"configured {label}"),
        label=f"configured {label}",
    )


def _require_configured_agent_home_root(home_root: Path) -> Path:
    root = _require_no_symlink_components(
        _absolute_path(home_root, label="agent home root"),
        label="agent home root",
    )
    configured = _configured_path("ARCLINK_DOCKER_AGENT_HOME_ROOT", label="agent home root")
    if configured is not None and root != configured:
        raise ValueError(
            "agent user helper agent home root must match configured ARCLINK_DOCKER_AGENT_HOME_ROOT"
        )
    return root


def _require_canonical_child_path(
    parent: Path,
    child: Path,
    suffix: Path | str,
    *,
    label: str,
) -> Path:
    parent = _absolute_path(parent, label=f"{label} parent")
    child = _absolute_path(child, label=label)
    expected = _absolute_path(parent / suffix, label=f"canonical {label}")
    if child != expected:
        raise ValueError(f"agent user helper {label} must be the canonical child path")
    try:
        expected_resolved = parent.resolve(strict=False) / suffix
        child_resolved = child.resolve(strict=False)
    except (OSError, RuntimeError):
        raise ValueError(f"agent user helper {label} is not a valid path") from None
    if child_resolved != expected_resolved:
        raise ValueError(f"agent user helper {label} must not resolve outside the canonical child path")
    return child


def _require_agent_home(unix_user: str, home_root: Path, home: Path) -> Path:
    unix_user = _require_safe_unix_user(unix_user)
    root = _absolute_path(home_root, label="agent home root")
    home_path = _require_canonical_child_path(
        root,
        _absolute_path(home, label="agent home"),
        unix_user,
        label="agent home",
    )
    if home_path.name != unix_user:
        raise ValueError("agent user helper agent home must stay under the Docker agent home root")
    return home_path


def _require_hermes_home(home: Path, hermes_home: Path) -> Path:
    home = _absolute_path(home, label="agent home")
    hermes = _require_canonical_child_path(
        home,
        _absolute_path(hermes_home, label="Hermes home"),
        HERMES_HOME_SUFFIX,
        label="Hermes home",
    )
    if hermes != home / HERMES_HOME_SUFFIX:
        raise ValueError("agent user helper Hermes home must be the canonical child of the agent home")
    return hermes


def _require_workspace(hermes_home: Path, workspace: Any) -> Path:
    hermes = _absolute_path(hermes_home, label="Hermes home")
    raw = str(workspace or "").strip()
    workspace_path = _require_canonical_child_path(
        hermes,
        _absolute_path(raw or hermes / "workspace", label="workspace"),
        "workspace",
        label="workspace",
    )
    if workspace_path != hermes / "workspace":
        raise ValueError("agent user helper workspace must be the canonical child of the Hermes home")
    return workspace_path


def _require_agent_id_value(value: Any, *, label: str) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"agent user helper {label} is not numeric") from None
    if numeric < AGENT_UID_MIN or numeric >= AGENT_UID_MIN + AGENT_UID_SPAN:
        raise ValueError(f"agent user helper {label} is outside the managed Docker agent id range")
    return numeric


def _agent_id_base(unix_user: str) -> int:
    digest = hashlib.sha256(unix_user.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % AGENT_UID_SPAN


def _assignment_temp_path(path: Path) -> Path:
    return path.with_name(path.name + ".tmp")


def _require_id_assignment_file(home_root: Path, path: Path, *, label: str) -> Path:
    root = _require_no_symlink_components(
        _absolute_path(home_root, label="agent home root"),
        label="agent home root",
    )
    target = _absolute_path(path, label=label)
    if target.name not in {ASSIGNMENTS_FILE, f"{ASSIGNMENTS_FILE}.tmp"}:
        raise ValueError("agent user helper id assignment path is not allowlisted")
    if target != root / target.name:
        raise ValueError("agent user helper id assignment path must stay under the Docker agent home root")
    try:
        expected_resolved = root.resolve(strict=False) / target.name
        target_resolved = target.resolve(strict=False)
    except (OSError, RuntimeError):
        raise ValueError(f"agent user helper {label} is not a valid path") from None
    if target_resolved != expected_resolved:
        raise ValueError(f"agent user helper {label} must not resolve outside the Docker agent home root")
    try:
        info = os.lstat(target)
    except FileNotFoundError:
        return target
    except OSError:
        raise ValueError(f"agent user helper {label} is not a valid path") from None
    mode = info.st_mode
    if stat.S_ISLNK(mode):
        raise ValueError(f"agent user helper {label} must not be a symlink")
    if not stat.S_ISREG(mode):
        raise ValueError(f"agent user helper {label} must be a regular file")
    return target


def _preflight_id_assignment_files(home_root: Path) -> tuple[Path, Path]:
    assignment_path = _absolute_path(home_root / ASSIGNMENTS_FILE, label="id assignment file")
    assignment_path = _require_id_assignment_file(home_root, assignment_path, label="id assignment file")
    tmp_path = _require_id_assignment_file(
        home_root,
        _assignment_temp_path(assignment_path),
        label="id assignment temporary file",
    )
    return assignment_path, tmp_path


def _read_assignments(path: Path) -> dict[str, dict[str, int]]:
    path = _require_id_assignment_file(path.parent, path, label="id assignment file")
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ValueError("agent user helper id assignment file is invalid") from None
    if not isinstance(raw, dict):
        raise ValueError("agent user helper id assignment file is invalid")
    assignments: dict[str, dict[str, int]] = {}
    for user, entry in raw.items():
        safe_user = _require_safe_unix_user(user)
        if not isinstance(entry, dict):
            raise ValueError("agent user helper id assignment entry is invalid")
        uid = _require_agent_id_value(entry.get("uid"), label="uid")
        gid = _require_agent_id_value(entry.get("gid"), label="gid")
        if uid != gid:
            raise ValueError("agent user helper id assignment entry must use matching uid/gid")
        assignments[safe_user] = {"uid": uid, "gid": gid}
    return assignments


def _write_assignments(path: Path, assignments: dict[str, dict[str, int]]) -> None:
    path = _require_id_assignment_file(path.parent, path, label="id assignment file")
    path.parent.mkdir(parents=True, exist_ok=True)
    path = _require_id_assignment_file(path.parent, path, label="id assignment file")
    tmp = _require_id_assignment_file(
        path.parent,
        _assignment_temp_path(path),
        label="id assignment temporary file",
    )
    if tmp.exists():
        tmp.unlink()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    data = json.dumps(assignments, sort_keys=True, indent=2) + "\n"
    fd = -1
    try:
        fd = os.open(tmp, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1
            handle.write(data)
        _require_id_assignment_file(path.parent, path, label="id assignment file")
        os.replace(tmp, path)
    except Exception:
        if fd >= 0:
            os.close(fd)
        try:
            if tmp.exists() and not tmp.is_symlink() and tmp.is_file():
                tmp.unlink()
        except OSError:
            pass
        raise


def _trusted_root_executable(name: str) -> Path:
    path = TRUSTED_ROOT_EXECUTABLES.get(name)
    if path is None or not path.is_absolute():
        raise ValueError(f"agent user helper required executable is not pinned: {name}")
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError(f"agent user helper required executable is unavailable: {path}")
    return path


def _trusted_root_executables() -> dict[str, Path]:
    return {name: _trusted_root_executable(name) for name in ("groupadd", "useradd", "chown")}


def _uid_or_gid_is_available(candidate: int, unix_user: str) -> bool:
    try:
        user_info = pwd.getpwuid(candidate)
    except KeyError:
        user_ok = True
    else:
        user_ok = user_info.pw_name == unix_user
    try:
        group_info = grp.getgrgid(candidate)
    except KeyError:
        group_ok = True
    else:
        group_ok = group_info.gr_name == unix_user
    return user_ok and group_ok


def _assigned_uid_gid(home_root: Path, unix_user: str) -> tuple[int, int]:
    unix_user = _require_safe_unix_user(unix_user)
    home_root = _require_configured_agent_home_root(home_root)
    with ASSIGNMENTS_LOCK:
        assignment_path, _tmp_path = _preflight_id_assignment_files(home_root)
        assignments = _read_assignments(assignment_path)
        existing = assignments.get(unix_user)
        if existing:
            if not _uid_or_gid_is_available(existing["uid"], unix_user):
                raise ValueError("agent user helper persisted uid/gid conflicts with an existing account")
            return existing["uid"], existing["gid"]

        used = {entry["uid"] for entry in assignments.values()} | {entry["gid"] for entry in assignments.values()}
        base = _agent_id_base(unix_user)
        for offset in range(AGENT_UID_SPAN):
            candidate = AGENT_UID_MIN + ((base + offset) % AGENT_UID_SPAN)
            if candidate in used:
                continue
            if not _uid_or_gid_is_available(candidate, unix_user):
                continue
            assignments[unix_user] = {"uid": candidate, "gid": candidate}
            _write_assignments(assignment_path, assignments)
            return candidate, candidate
    raise ValueError("agent user helper could not allocate a Docker agent uid/gid")


def _ensure_group(unix_user: str, gid: int, *, groupadd: Path | None = None) -> None:
    try:
        group_info = grp.getgrnam(unix_user)
    except KeyError:
        try:
            existing_gid = grp.getgrgid(gid)
        except KeyError:
            existing_gid = None
        if existing_gid is not None and existing_gid.gr_name != unix_user:
            raise ValueError("agent user helper managed gid is already assigned")
        executable = groupadd or _trusted_root_executable("groupadd")
        subprocess.run([str(executable), "--gid", str(gid), unix_user], check=True)
        return
    if int(group_info.gr_gid) != gid:
        raise ValueError("agent user helper managed group has the wrong gid")


def _ensure_user(unix_user: str, home: Path, uid: int, gid: int, *, useradd: Path | None = None) -> None:
    try:
        info = pwd.getpwnam(unix_user)
    except KeyError:
        executable = useradd or _trusted_root_executable("useradd")
        subprocess.run(
            [
                str(executable),
                "--uid",
                str(uid),
                "--gid",
                str(gid),
                "--home-dir",
                str(home),
                "--shell",
                "/bin/bash",
                "--create-home",
                unix_user,
            ],
            check=True,
        )
        return
    if int(info.pw_uid) != uid or int(info.pw_gid) != gid:
        raise ValueError("agent user helper managed user has the wrong uid/gid")


def _validate_request(request_body: dict[str, Any]) -> tuple[str, str, Path, Path, Path, Path]:
    if any(key in request_body for key in ("args", "cmd", "command")):
        raise ValueError("agent user helper does not accept raw commands")
    operation = str(request_body.get("operation") or "").strip()
    if operation not in ALLOWED_OPERATIONS:
        raise ValueError("agent user helper operation is not allowlisted")
    _require_safe_agent_id(request_body.get("agent_id"))
    unix_user = _require_safe_unix_user(request_body.get("unix_user"))
    home_root = _require_configured_agent_home_root(
        _absolute_path(request_body.get("home_root"), label="agent home root")
    )
    home = _require_agent_home(unix_user, home_root, _absolute_path(request_body.get("home"), label="agent home"))
    hermes_home = _require_hermes_home(home, _absolute_path(request_body.get("hermes_home"), label="Hermes home"))
    workspace = _require_workspace(hermes_home, request_body.get("workspace"))
    return operation, unix_user, home, hermes_home, workspace, home_root


def _ensure_user_home(
    *,
    unix_user: str,
    home: Path,
    hermes_home: Path,
    workspace: Path,
    home_root: Path,
) -> dict[str, Any]:
    executables = _trusted_root_executables()
    uid, gid = _assigned_uid_gid(home_root, unix_user)
    home.mkdir(parents=True, exist_ok=True)
    _ensure_group(unix_user, gid, groupadd=executables["groupadd"])
    _ensure_user(unix_user, home, uid, gid, useradd=executables["useradd"])
    for path in (
        home / ".config" / "systemd" / "user",
        home / ".local" / "share" / "arclink-agent",
        home / ".local" / "state" / "arclink-agent",
        hermes_home,
        workspace,
    ):
        path.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(executables["chown"]), "-R", f"{uid}:{gid}", str(home)], check=True)
    return {
        "uid": int(uid),
        "gid": int(gid),
        "home": str(home),
        "hermes_home": str(hermes_home),
        "workspace": str(workspace),
    }


def _rejection_reason(exc: BaseException) -> str:
    text = str(exc).lower()
    if "raw commands" in text:
        return "raw_command_rejected"
    if "trusted-host residual risk" in text:
        return "trusted_host_risk_not_accepted"
    if "operation" in text and "allowlisted" in text:
        return "operation_not_allowlisted"
    if "safe" in text and ("agent_id" in text or "account" in text):
        return "identifier_rejected"
    if "symlink" in text:
        return "symlink_path_rejected"
    if "configured" in text or "canonical" in text or "home root" in text:
        return "agent_home_root_rejected"
    if "id assignment" in text:
        return "id_assignment_rejected"
    if "required executable" in text:
        return "root_executable_rejected"
    if isinstance(exc, subprocess.SubprocessError):
        return "subprocess_failed"
    if isinstance(exc, OSError):
        return "filesystem_error"
    return "validation_rejected"


def _rejection_message(reason: str) -> str:
    messages = {
        "raw_command_rejected": "Rejected raw command input.",
        "trusted_host_risk_not_accepted": "Rejected request before trusted-host acknowledgement.",
        "operation_not_allowlisted": "Rejected non-allowlisted agent user operation.",
        "identifier_rejected": "Rejected unsafe agent or Unix-user identifier.",
        "symlink_path_rejected": "Rejected symlink-steered agent user path.",
        "agent_home_root_rejected": "Rejected unsafe Docker agent-home root.",
        "id_assignment_rejected": "Rejected unsafe uid/gid assignment file.",
        "root_executable_rejected": "Rejected unsafe root executable configuration.",
        "subprocess_failed": "Agent user helper subprocess failed.",
        "filesystem_error": "Agent user helper filesystem preflight failed.",
        "validation_rejected": "Rejected agent user helper request during validation.",
    }
    return messages.get(reason, messages["validation_rejected"])


def _incident_metadata(request_body: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if not isinstance(request_body, dict):
        return metadata
    operation = str(request_body.get("operation") or "").strip()
    if operation in ALLOWED_OPERATIONS:
        metadata["operation"] = operation
    agent_id = str(request_body.get("agent_id") or "").strip()
    if SAFE_AGENT_ID_RE.fullmatch(agent_id):
        metadata["agent_id"] = agent_id
    unix_user = str(request_body.get("unix_user") or "").strip().lower()
    if SAFE_UNIX_USER_RE.fullmatch(unix_user):
        metadata["unix_user"] = unix_user
    return metadata


def _record_rejection_incident(request_body: Any, exc: BaseException) -> None:
    reason = _rejection_reason(exc)
    record_rejection_incident(
        agent_home_root_rejection_path(SERVICE_NAME),
        service=SERVICE_NAME,
        event="agent_user_helper_request_rejected",
        reason=reason,
        message=_rejection_message(reason),
        error_class=exc.__class__.__name__,
        metadata=_incident_metadata(request_body),
    )


def run_agent_user_helper_request(request_body: dict[str, Any]) -> tuple[bool, dict[str, Any] | str]:
    try:
        require_docker_trusted_host_risk_accepted(service=SERVICE_NAME, error_cls=ValueError)
        operation, unix_user, home, hermes_home, workspace, home_root = _validate_request(request_body)
        if operation == "ensure_user_home":
            return True, _ensure_user_home(
                unix_user=unix_user,
                home=home,
                hermes_home=hermes_home,
                workspace=workspace,
                home_root=home_root,
            )
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError, KeyError) as exc:
        _record_rejection_incident(request_body, exc)
        return False, str(exc)
    return False, "agent user helper operation is not allowlisted"


class AgentUserHelperHandler(BaseHTTPRequestHandler):
    server_version = "ArcLinkAgentUserHelper/1"

    def log_message(self, fmt: str, *args: Any) -> None:
        del fmt, args

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            _json_response(self, 404, {"ok": False, "error": "not found"})
            return
        if not _helper_token():
            _json_response(self, 503, {"ok": False, "error": "agent user helper token is not configured"})
            return
        _json_response(self, 200, {"ok": True})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/agent-user":
            _json_response(self, 404, {"ok": False, "error": "not found"})
            return
        if not _is_authorized(self.headers):
            _json_response(self, 401, {"ok": False, "error": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_REQUEST_BYTES:
            _json_response(self, 413, {"ok": False, "error": "invalid agent user helper request size"})
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            _json_response(self, 400, {"ok": False, "error": "invalid JSON"})
            return
        if not isinstance(body, dict):
            _json_response(self, 400, {"ok": False, "error": "agent user helper request must be a JSON object"})
            return
        ok, payload = run_agent_user_helper_request(body)
        if ok:
            _json_response(self, 200, {"ok": True, "result": payload if isinstance(payload, dict) else {}})
        else:
            _json_response(self, 400, {"ok": False, "error": str(payload)})


def serve(*, host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), AgentUserHelperHandler)
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the ArcLink agent user helper")
    parser.add_argument("--host", default=os.environ.get("ARCLINK_AGENT_USER_HELPER_HOST", DEFAULT_HOST))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("ARCLINK_AGENT_USER_HELPER_PORT", str(DEFAULT_PORT)) or DEFAULT_PORT),
    )
    args = parser.parse_args(argv)
    require_docker_trusted_host_risk_accepted(service=SERVICE_NAME, error_cls=SystemExit)
    if not _helper_token():
        raise SystemExit("ARCLINK_AGENT_USER_HELPER_TOKEN is required")
    serve(host=str(args.host), port=int(args.port))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
