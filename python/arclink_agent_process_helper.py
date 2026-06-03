#!/usr/bin/env python3
"""Root-scoped Docker agent process helper.

The Docker agent supervisor owns active-agent discovery and reconciliation.
This helper owns only the root setpriv process boundary for Docker-mode agent
commands. It rejects raw command input, reconstructs allowlisted command forms,
and keeps gateway/dashboard process handles out of the supervisor.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import ipaddress
import json
import os
import re
import signal
import stat
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from arclink_boundary import require_docker_trusted_host_risk_accepted
from arclink_rejection_incidents import private_state_rejection_path, record_rejection_incident


MAX_REQUEST_BYTES = 32768
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8916
AGENT_PROCESS_HELPER_TOKEN_HEADER = "X-ArcLink-Agent-Process-Helper-Token"
SAFE_PATH = "/home/arclink/.local/bin:/opt/arclink/runtime/hermes-venv/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin"
SETPRIV_BIN = "/usr/bin/setpriv"
SAFE_AGENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$")
SAFE_UNIX_USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,30}$")
SAFE_LOG_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,120}$")
SAFE_ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
SAFE_CHANNEL_RE = re.compile(r"^[a-z][a-z0-9_-]{0,40}$")
HERMES_HOME_SUFFIX = Path(".local/share/arclink-agent/hermes-home")
RUN_ONCE_KINDS = {"install", "identity", "refresh", "cron"}
PROCESS_KINDS = {"gateway", "dashboard"}
MIN_AGENT_PROCESS_ID = 1
MAX_AGENT_PROCESS_ID = 2147483647
AGENT_PROCESS_ENV_BLOCKLIST = {
    "ARCLINK_AGENT_PROCESS_HELPER_TOKEN",
    "ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN",
    "ARCLINK_AGENT_USER_HELPER_TOKEN",
    "ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN",
    "ARCLINK_GATEWAY_EXEC_BROKER_TOKEN",
    "ARCLINK_MIGRATION_CAPTURE_HELPER_TOKEN",
    "ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN",
}
AGENT_PROCESS_UNAPPROVED_ENV_KEYS = {
    "BASH_ENV",
    "ENV",
    "GIT_ASKPASS",
    "GIT_SSH",
    "GIT_SSH_COMMAND",
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "SSH_ASKPASS",
    "SSH_AUTH_SOCK",
}
AGENT_PROCESS_UNAPPROVED_ENV_PREFIXES = ("LD_",)
AGENT_PROCESS_SECRET_ENV_SUFFIXES = ("_TOKEN", "_SECRET", "_PASSWORD", "_KEY")

PROCESS_LOCK = threading.Lock()
PROCESSES: dict[str, subprocess.Popen[str]] = {}
PROCESS_SIGNATURES: dict[str, str] = {}
PROCESS_STOP_TIMEOUT_SECONDS = 5.0
PROCESS_KILL_TIMEOUT_SECONDS = 2.0
SERVICE_NAME = "agent-process-helper"


def _helper_token() -> str:
    return str(os.environ.get("ARCLINK_AGENT_PROCESS_HELPER_TOKEN") or "").strip()


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _is_authorized(headers: Any) -> bool:
    expected = _helper_token()
    supplied = str(headers.get(AGENT_PROCESS_HELPER_TOKEN_HEADER) or "").strip()
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def _reject_raw_commands(request_body: dict[str, Any]) -> None:
    if any(key in request_body for key in ("args", "cmd", "command")):
        raise ValueError("agent process helper does not accept raw commands")


def _require_safe_agent_id(value: Any, *, label: str = "agent_id") -> str:
    clean = str(value or "").strip()
    if not SAFE_AGENT_ID_RE.fullmatch(clean):
        raise ValueError(f"agent process helper {label} is not a safe identifier")
    return clean


def _require_safe_unix_user(value: Any) -> str:
    clean = str(value or "").strip().lower()
    if not SAFE_UNIX_USER_RE.fullmatch(clean):
        raise ValueError("agent process helper unix_user is not a safe local account name")
    return clean


def _single_line(value: Any, *, label: str, allow_blank: bool = True, max_chars: int = 512) -> str:
    clean = str(value or "").strip()
    if not clean and allow_blank:
        return ""
    if not clean:
        raise ValueError(f"agent process helper {label} is required")
    if "\n" in clean or "\r" in clean or "\x00" in clean:
        raise ValueError(f"agent process helper {label} must be a single line")
    if len(clean) > max_chars:
        raise ValueError(f"agent process helper {label} is too long")
    return clean


def _require_dashboard_backend_host(value: Any) -> str:
    clean = _single_line(value, label="dashboard backend host", allow_blank=False, max_chars=128)
    try:
        parsed = ipaddress.ip_address(clean)
    except ValueError:
        raise ValueError("agent process helper dashboard backend host must be an IP address") from None
    if parsed.is_unspecified:
        raise ValueError("agent process helper dashboard backend host must not be a wildcard address")
    if parsed.is_multicast:
        raise ValueError("agent process helper dashboard backend host must not be multicast")
    if parsed.is_global:
        raise ValueError("agent process helper dashboard backend host must not be globally routable")
    if not (parsed.is_loopback or parsed.is_private or parsed.is_link_local):
        raise ValueError("agent process helper dashboard backend host must be loopback or Docker-internal")
    return clean


def _absolute_path(value: Any, *, label: str) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"agent process helper {label} is required")
    path = Path(os.path.normpath(raw))
    if not path.is_absolute():
        raise ValueError(f"agent process helper {label} must be absolute")
    if str(path) == "/":
        raise ValueError(f"agent process helper {label} must not be filesystem root")
    return path


def _require_no_symlink_components(path: Path, *, label: str) -> Path:
    path = _absolute_path(path, label=label)
    try:
        resolved = path.resolve(strict=False)
    except (OSError, RuntimeError):
        raise ValueError(f"agent process helper {label} is not a valid path") from None
    if resolved != path:
        raise ValueError(f"agent process helper {label} must not include symlink components")
    return path


def _configured_paths(env_names: tuple[str, ...], *, label: str) -> list[tuple[str, Path]]:
    paths: list[tuple[str, Path]] = []
    for env_name in env_names:
        raw = str(os.environ.get(env_name) or "").strip()
        if raw:
            paths.append(
                (
                    env_name,
                    _require_no_symlink_components(raw, label=f"configured {label}"),
                )
            )
    return paths


def _require_configured_path(path: Path, env_names: tuple[str, ...], *, label: str) -> Path:
    path = _require_no_symlink_components(path, label=label)
    configured = _configured_paths(env_names, label=label)
    if not configured:
        return path
    expected = configured[0][1]
    for env_name, configured_path in configured[1:]:
        if configured_path != expected:
            names = ", ".join(name for name, _path in configured)
            raise ValueError(f"agent process helper configured {label} paths disagree: {names}")
    if path != expected:
        names = ", ".join(env_names)
        raise ValueError(f"agent process helper {label} must match configured {names}")
    return path


def _require_agent_home_root(home_root: Any) -> Path:
    root = _require_no_symlink_components(
        _absolute_path(home_root, label="agent home root"),
        label="agent home root",
    )
    return _require_configured_path(
        root,
        ("ARCLINK_DOCKER_AGENT_HOME_ROOT",),
        label="agent home root",
    )


def _require_state_dir(state_dir: Path, priv_dir: Path) -> Path:
    state = _require_no_symlink_components(state_dir, label="state dir")
    expected = _absolute_path(priv_dir / "state", label="canonical state dir")
    if state != expected:
        raise ValueError("agent process helper state dir must be the canonical child of the private dir")
    return state


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
        raise ValueError(f"agent process helper {label} must be the canonical child path")
    try:
        expected_resolved = parent.resolve(strict=False) / suffix
        child_resolved = child.resolve(strict=False)
    except (OSError, RuntimeError):
        raise ValueError(f"agent process helper {label} is not a valid path") from None
    if child_resolved != expected_resolved:
        raise ValueError(f"agent process helper {label} must not resolve outside the canonical child path")
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
        raise ValueError("agent process helper agent home must stay under the Docker agent home root")
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
        raise ValueError("agent process helper Hermes home must be the canonical child of the agent home")
    return hermes


def _require_workspace(hermes_home: Path, workspace: Any) -> Path:
    hermes = _absolute_path(hermes_home, label="Hermes home")
    workspace_path = _require_canonical_child_path(
        hermes,
        _absolute_path(str(workspace or hermes / "workspace"), label="workspace"),
        "workspace",
        label="workspace",
    )
    if workspace_path != hermes / "workspace":
        raise ValueError("agent process helper workspace must be the canonical child of the Hermes home")
    return workspace_path


def _require_log_name(name: Any) -> str:
    clean = str(name or "").strip()
    if not SAFE_LOG_NAME_RE.fullmatch(clean):
        raise ValueError("agent process helper log name is not safe")
    return clean


def _require_log_dir(state_dir: Path) -> Path:
    state = _absolute_path(state_dir, label="state dir")
    log_dir = _absolute_path(state / "docker" / "agent-process-helper", label="log directory")
    try:
        expected_resolved = state.resolve(strict=False) / "docker" / "agent-process-helper"
        log_dir_resolved = log_dir.resolve(strict=False)
    except (OSError, RuntimeError):
        raise ValueError("agent process helper log directory is not a valid path") from None
    if log_dir_resolved != expected_resolved:
        raise ValueError("agent process helper log directory symlink must not resolve outside its canonical state path")
    if log_dir.exists() and not log_dir.is_dir():
        raise ValueError("agent process helper log directory is not a directory")
    log_dir.mkdir(parents=True, exist_ok=True)
    if log_dir.is_symlink():
        raise ValueError("agent process helper log directory symlink is not allowed")
    try:
        if log_dir.resolve(strict=False) != expected_resolved:
            raise ValueError("agent process helper log directory symlink must not resolve outside its canonical state path")
    except (OSError, RuntimeError):
        raise ValueError("agent process helper log directory is not a valid path") from None
    return log_dir


def _require_agent_process_id(value: Any, *, label: str) -> int:
    text = str(value or "").strip()
    if not text.isdecimal():
        raise ValueError(f"agent process helper {label} is required for numeric privilege drop")
    numeric = int(text)
    if numeric < MIN_AGENT_PROCESS_ID or numeric > MAX_AGENT_PROCESS_ID:
        raise ValueError(f"agent process helper {label} is outside the allowed numeric id range")
    return numeric


def _is_agent_process_control_token_env_key(key: str) -> bool:
    return key in AGENT_PROCESS_ENV_BLOCKLIST or (key.startswith("ARCLINK_") and key.endswith("_TOKEN"))


def _is_agent_process_unapproved_env_key(key: str) -> bool:
    return (
        key in AGENT_PROCESS_UNAPPROVED_ENV_KEYS
        or key.startswith(AGENT_PROCESS_UNAPPROVED_ENV_PREFIXES)
        or key.endswith(AGENT_PROCESS_SECRET_ENV_SUFFIXES)
    )


def _require_env(env: Any, *, unix_user: str, home: Path, hermes_home: Path, workspace: Path, uid: int, gid: int) -> dict[str, str]:
    if not isinstance(env, dict):
        raise ValueError("agent process helper env must be an object")
    clean_env: dict[str, str] = {}
    for key, value in env.items():
        key_text = str(key or "").strip()
        if not SAFE_ENV_KEY_RE.fullmatch(key_text):
            raise ValueError("agent process helper env key is not safe")
        if _is_agent_process_control_token_env_key(key_text):
            raise ValueError("agent process helper env must not include ArcLink control token keys")
        if _is_agent_process_unapproved_env_key(key_text):
            raise ValueError("agent process helper env key is not approved for agent process execution")
        value_text = str(value)
        if "\x00" in value_text:
            raise ValueError("agent process helper env value contains a NUL byte")
        clean_env[key_text] = value_text

    expected = {
        "HOME": str(home),
        "USER": unix_user,
        "LOGNAME": unix_user,
        "HERMES_HOME": str(hermes_home),
        "ARCLINK_WORKSPACE_ROOT": str(workspace),
        "DRIVE_WORKSPACE_ROOT": str(workspace),
        "CODE_WORKSPACE_ROOT": str(workspace),
        "TERMINAL_WORKSPACE_ROOT": str(workspace),
        "ARCLINK_AGENT_UID": str(uid),
        "ARCLINK_AGENT_GID": str(gid),
    }
    for key, expected_value in expected.items():
        if clean_env.get(key) != expected_value:
            raise ValueError(f"agent process helper env {key} does not match the validated agent context")
    supplied_path = str(clean_env.get("PATH") or "")
    if supplied_path and supplied_path != SAFE_PATH:
        raise ValueError("agent process helper env PATH must match the safe helper PATH")
    clean_env["PATH"] = SAFE_PATH
    return clean_env


def _channels(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("agent process helper channels must be a list")
    channels: list[str] = []
    for item in value:
        channel = str(item or "").strip().lower()
        if not SAFE_CHANNEL_RE.fullmatch(channel):
            raise ValueError("agent process helper channel is not safe")
        channels.append(channel)
    return channels


def _validate_common(request_body: dict[str, Any]) -> dict[str, Any]:
    _reject_raw_commands(request_body)
    agent_id = _require_safe_agent_id(request_body.get("agent_id"))
    unix_user = _require_safe_unix_user(request_body.get("unix_user"))
    home_root = _require_agent_home_root(request_body.get("home_root"))
    home = _require_agent_home(unix_user, home_root, _absolute_path(request_body.get("home"), label="agent home"))
    hermes_home = _require_hermes_home(home, _absolute_path(request_body.get("hermes_home"), label="Hermes home"))
    workspace = _require_workspace(hermes_home, request_body.get("workspace"))
    uid = _require_agent_process_id(request_body.get("uid"), label="agent uid")
    gid = _require_agent_process_id(request_body.get("gid"), label="agent gid")
    repo_dir = _require_configured_path(
        _absolute_path(request_body.get("repo_dir"), label="repo dir"),
        ("ARCLINK_REPO_DIR",),
        label="repo dir",
    )
    priv_dir = _require_configured_path(
        _absolute_path(request_body.get("priv_dir"), label="private dir"),
        ("ARCLINK_PRIV_DIR", "ARCLINK_DOCKER_CONTAINER_PRIV_DIR"),
        label="private dir",
    )
    state_dir = _require_state_dir(_absolute_path(request_body.get("state_dir"), label="state dir"), priv_dir)
    runtime_dir = _require_configured_path(
        _absolute_path(request_body.get("runtime_dir"), label="runtime dir"),
        ("RUNTIME_DIR",),
        label="runtime dir",
    )
    env = _require_env(
        request_body.get("env"),
        unix_user=unix_user,
        home=home,
        hermes_home=hermes_home,
        workspace=workspace,
        uid=uid,
        gid=gid,
    )
    return {
        "agent_id": agent_id,
        "unix_user": unix_user,
        "home_root": home_root,
        "home": home,
        "hermes_home": hermes_home,
        "workspace": workspace,
        "uid": uid,
        "gid": gid,
        "repo_dir": repo_dir,
        "priv_dir": priv_dir,
        "state_dir": state_dir,
        "runtime_dir": runtime_dir,
        "env": env,
    }


def _setpriv_cmd(ctx: dict[str, Any], command: list[str]) -> list[str]:
    clean_command: list[str] = []
    for item in command:
        value = str(item)
        if not value or "\x00" in value:
            raise ValueError("agent process helper command contains an unsafe argument")
        clean_command.append(value)
    return [
        SETPRIV_BIN,
        "--reuid",
        str(ctx["uid"]),
        "--regid",
        str(ctx["gid"]),
        "--clear-groups",
        "--no-new-privs",
        "--inh-caps=-all",
        "--ambient-caps=-all",
        "--bounding-set=-all",
        "--",
        *clean_command,
    ]


def _require_repo_command_target(
    repo_dir: Path,
    suffix: str,
    *,
    label: str,
    executable: bool,
) -> Path:
    repo = _absolute_path(repo_dir, label="repo dir")
    relative = Path(suffix)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"agent process helper {label} command target must be a fixed repo child")
    target = _absolute_path(repo / relative, label=f"{label} command target")
    expected = _absolute_path(repo / relative, label=f"canonical {label} command target")
    if target != expected:
        raise ValueError(f"agent process helper {label} command target must be a fixed repo child")
    try:
        repo_resolved = repo.resolve(strict=False)
        target_resolved = target.resolve(strict=False)
    except (OSError, RuntimeError):
        raise ValueError(f"agent process helper {label} command target is not a valid path") from None
    expected_resolved = repo_resolved / relative
    if target_resolved != expected_resolved:
        raise ValueError(f"agent process helper {label} command target symlink is not allowed")
    try:
        target_stat = target.lstat()
    except FileNotFoundError:
        raise ValueError(f"agent process helper {label} command target is missing") from None
    except OSError:
        raise ValueError(f"agent process helper {label} command target is not accessible") from None
    if stat.S_ISLNK(target_stat.st_mode):
        raise ValueError(f"agent process helper {label} command target symlink is not allowed")
    if not stat.S_ISREG(target_stat.st_mode):
        raise ValueError(f"agent process helper {label} command target must be a regular file")
    if not target_stat.st_mode & (stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH):
        raise ValueError(f"agent process helper {label} command target must be readable")
    if executable and not target_stat.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
        raise ValueError(f"agent process helper {label} command target must be executable")
    return target


def _require_repo_shell_target(repo_dir: Path, suffix: str, *, label: str) -> Path:
    return _require_repo_command_target(repo_dir, suffix, label=label, executable=True)


def _require_repo_python_target(repo_dir: Path, suffix: str, *, label: str) -> Path:
    return _require_repo_command_target(repo_dir, suffix, label=label, executable=False)


def _log_path(state_dir: Path, name: str) -> Path:
    name = _require_log_name(name)
    log_dir = _require_log_dir(state_dir)
    path = log_dir / f"{name}.log"
    try:
        resolved_path = path.resolve(strict=False)
        expected_path = log_dir.resolve(strict=False) / f"{name}.log"
    except (OSError, RuntimeError):
        raise ValueError("agent process helper log path is not a valid path") from None
    if resolved_path != expected_path:
        raise ValueError("agent process helper log path symlink must not resolve outside its canonical state path")
    try:
        resolved_path.relative_to(log_dir.resolve(strict=False))
    except ValueError:
        raise ValueError("agent process helper log path escaped its state directory") from None
    return path


def _incident_operation(request_body: Any) -> str:
    if not isinstance(request_body, dict):
        return "invalid"
    operation = str(request_body.get("operation") or "").strip()
    if operation in {"run_once", "ensure_processes", "terminate_all"}:
        return operation
    return "invalid"


def _incident_agent_id(request_body: Any) -> str | None:
    candidates: list[Any] = []
    if isinstance(request_body, dict):
        candidates.append(request_body.get("agent_id"))
        processes = request_body.get("processes")
        if isinstance(processes, list):
            for item in processes:
                if isinstance(item, dict):
                    candidates.append(item.get("agent_id"))
    for candidate in candidates:
        clean = str(candidate or "").strip()
        if SAFE_AGENT_ID_RE.fullmatch(clean):
            return clean
    return None


def _incident_metadata(request_body: Any) -> dict[str, Any]:
    metadata = {"operation": _incident_operation(request_body)}
    agent_id = _incident_agent_id(request_body)
    if agent_id:
        metadata["agent_id"] = agent_id
    return metadata


def _rejection_reason(exc: BaseException) -> str:
    text = str(exc).lower()
    if "raw commands" in text:
        return "raw_command_rejected"
    if "dashboard backend host" in text:
        return "dashboard_backend_host_rejected"
    if "not approved for agent process execution" in text:
        return "unapproved_env_rejected"
    if "control token" in text:
        return "control_token_env_rejected"
    if "env key" in text:
        return "unsafe_env_rejected"
    if "trusted-host residual risk" in text:
        return "trusted_host_risk_not_accepted"
    if "symlink" in text:
        return "symlink_path_rejected"
    if "configured" in text or "canonical" in text:
        return "configured_root_rejected"
    if "operation" in text and "allowlisted" in text:
        return "operation_not_allowlisted"
    if "request must be a json object" in text:
        return "invalid_request"
    if isinstance(exc, subprocess.SubprocessError):
        return "subprocess_failed"
    if isinstance(exc, OSError):
        return "filesystem_error"
    return "validation_rejected"


def _rejection_message(reason: str) -> str:
    messages = {
        "raw_command_rejected": "Rejected raw command input.",
        "dashboard_backend_host_rejected": "Rejected unsafe dashboard backend host.",
        "unapproved_env_rejected": "Rejected unapproved process environment key.",
        "control_token_env_rejected": "Rejected ArcLink control token environment key.",
        "unsafe_env_rejected": "Rejected unsafe process environment key.",
        "trusted_host_risk_not_accepted": "Rejected request before trusted-host acknowledgement.",
        "symlink_path_rejected": "Rejected symlink-steered helper path.",
        "configured_root_rejected": "Rejected configured-root mismatch.",
        "operation_not_allowlisted": "Rejected non-allowlisted operation.",
        "invalid_request": "Rejected invalid request shape.",
        "subprocess_failed": "Helper subprocess failed.",
        "filesystem_error": "Helper filesystem preflight failed.",
        "validation_rejected": "Rejected helper request during validation.",
    }
    return messages.get(reason, messages["validation_rejected"])


def _record_rejection_incident(request_body: Any, exc: BaseException) -> None:
    reason = _rejection_reason(exc)
    record_rejection_incident(
        private_state_rejection_path(
            SERVICE_NAME,
            env_names=("ARCLINK_PRIV_DIR", "ARCLINK_DOCKER_CONTAINER_PRIV_DIR"),
        ),
        service=SERVICE_NAME,
        event="agent_process_helper_request_rejected",
        reason=reason,
        message=_rejection_message(reason),
        error_class=exc.__class__.__name__,
        metadata=_incident_metadata(request_body),
    )


def _run_once_command(kind: str, request_body: dict[str, Any], ctx: dict[str, Any]) -> tuple[list[str], str, int]:
    agent_id = str(ctx["agent_id"])
    repo_dir = Path(ctx["repo_dir"])
    hermes_home = Path(ctx["hermes_home"])
    if kind == "install":
        channels = _channels(request_body.get("channels"))
        install_script = _require_repo_shell_target(
            repo_dir,
            "bin/install-agent-user-services.sh",
            label="install",
        )
        hermes_shell = _require_repo_shell_target(repo_dir, "bin/hermes-shell.sh", label="Hermes shell")
        return (
            [
                str(install_script),
                agent_id,
                str(repo_dir),
                str(hermes_home),
                json.dumps(channels),
                str(Path(ctx["state_dir"]) / "activation-triggers" / f"{agent_id}.json"),
                str(hermes_shell),
            ],
            f"{agent_id}-install",
            1800,
        )
    if kind == "identity":
        python_bin = Path(ctx["runtime_dir"]) / "hermes-venv" / "bin" / "python3"
        if not python_bin.is_file():
            raise ValueError("agent process helper identity python interpreter is missing under runtime dir")
        identity_script = _require_repo_python_target(
            repo_dir,
            "python/arclink_headless_hermes_setup.py",
            label="identity setup",
        )
        return (
            [
                str(python_bin),
                str(identity_script),
                "--identity-only",
                "--bot-name",
                _single_line(request_body.get("bot_name"), label="bot name", allow_blank=False),
                "--unix-user",
                str(ctx["unix_user"]),
                "--user-name",
                _single_line(request_body.get("user_name"), label="user name", allow_blank=False),
            ],
            f"{agent_id}-install",
            1800,
        )
    if kind == "refresh":
        refresh_script = _require_repo_shell_target(repo_dir, "bin/user-agent-refresh.sh", label="refresh")
        return ([str(refresh_script)], f"{agent_id}-refresh", 1800)
    if kind == "cron":
        hermes_shell = _require_repo_shell_target(repo_dir, "bin/hermes-shell.sh", label="Hermes shell")
        return ([str(hermes_shell), "cron", "tick"], f"{agent_id}-cron", 300)
    raise ValueError("agent process helper run_once kind is not allowlisted")


def _run_once(request_body: dict[str, Any]) -> dict[str, Any]:
    kind = str(request_body.get("kind") or "").strip()
    if kind not in RUN_ONCE_KINDS:
        raise ValueError("agent process helper run_once kind is not allowlisted")
    ctx = _validate_common(request_body)
    command, log_name, timeout = _run_once_command(kind, request_body, ctx)
    full_command = _setpriv_cmd(ctx, command)
    log_path = _log_path(Path(ctx["state_dir"]), log_name)
    with log_path.open("a", encoding="utf-8") as log:
        result = subprocess.run(
            full_command,
            cwd=str(ctx["repo_dir"]),
            env=ctx["env"],
            text=True,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout,
        )
    return {"kind": kind, "returncode": int(result.returncode), "log": str(log_path)}


def _process_command(kind: str, request_body: dict[str, Any], ctx: dict[str, Any]) -> list[str]:
    repo_dir = Path(ctx["repo_dir"])
    if kind == "gateway":
        hermes_shell = _require_repo_shell_target(repo_dir, "bin/hermes-shell.sh", label="Hermes shell")
        return [str(hermes_shell), "gateway", "run", "--replace"]
    if kind == "dashboard":
        backend_host = _require_dashboard_backend_host(request_body.get("dashboard_backend_host"))
        backend_port = _single_line(request_body.get("dashboard_backend_port"), label="dashboard backend port", allow_blank=False)
        if not backend_port.isdecimal() or not (1 <= int(backend_port) <= 65535):
            raise ValueError("agent process helper dashboard backend port is invalid")
        hermes_shell = _require_repo_shell_target(repo_dir, "bin/hermes-shell.sh", label="Hermes shell")
        return [
            str(hermes_shell),
            "dashboard",
            "--host",
            backend_host,
            "--port",
            backend_port,
            "--no-open",
        ]
    raise ValueError("agent process helper process kind is not allowlisted")


def _process_key(ctx: dict[str, Any], kind: str) -> str:
    if kind not in PROCESS_KINDS:
        raise ValueError("agent process helper process kind is not allowlisted")
    return f"{ctx['agent_id']}:{kind}"


def _process_signature(command: list[str], ctx: dict[str, Any]) -> str:
    payload = {
        "command": command,
        "cwd": str(ctx["hermes_home"]),
        "env": sorted((str(key), str(value)) for key, value in dict(ctx["env"]).items()),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _send_process_signal(process: subprocess.Popen[str], signum: int) -> None:
    pid = getattr(process, "pid", None)
    if isinstance(pid, int) and pid > 0:
        try:
            os.killpg(pid, signum)
            return
        except ProcessLookupError:
            return
        except OSError:
            pass
    try:
        if signum == signal.SIGTERM:
            process.terminate()
        elif signum == signal.SIGKILL:
            process.kill()
        else:
            process.send_signal(signum)
    except ProcessLookupError:
        pass


def _wait_for_process_exit(process: subprocess.Popen[str], timeout: float) -> bool:
    wait = getattr(process, "wait", None)
    if callable(wait):
        try:
            wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return False
        except ProcessLookupError:
            return True
        return process.poll() is not None

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return True
        time.sleep(0.05)
    return process.poll() is not None


def _terminate_process(key: str, process: subprocess.Popen[str]) -> str:
    status = "already-exited"
    if process.poll() is None:
        _send_process_signal(process, signal.SIGTERM)
        if _wait_for_process_exit(process, PROCESS_STOP_TIMEOUT_SECONDS):
            status = "terminated"
        else:
            _send_process_signal(process, signal.SIGKILL)
            if not _wait_for_process_exit(process, PROCESS_KILL_TIMEOUT_SECONDS):
                raise subprocess.TimeoutExpired(
                    cmd=f"agent process {key}",
                    timeout=PROCESS_STOP_TIMEOUT_SECONDS + PROCESS_KILL_TIMEOUT_SECONDS,
                )
            status = "killed"
    PROCESSES.pop(key, None)
    PROCESS_SIGNATURES.pop(key, None)
    return status


def _running_signature_matches(key: str, process: subprocess.Popen[str], desired_signature: str) -> bool:
    return process.poll() is None and PROCESS_SIGNATURES.get(key) == desired_signature


def _ensure_processes(request_body: dict[str, Any]) -> dict[str, Any]:
    _reject_raw_commands(request_body)
    specs = request_body.get("processes")
    if not isinstance(specs, list):
        raise ValueError("agent process helper processes must be a list")
    desired: dict[str, tuple[list[str], dict[str, Any], str]] = {}
    for item in specs:
        if not isinstance(item, dict):
            raise ValueError("agent process helper process spec must be an object")
        _reject_raw_commands(item)
        kind = str(item.get("kind") or "").strip()
        if kind not in PROCESS_KINDS:
            raise ValueError("agent process helper process kind is not allowlisted")
        ctx = _validate_common(item)
        key = _process_key(ctx, kind)
        command = _setpriv_cmd(ctx, _process_command(kind, item, ctx))
        desired[key] = (command, ctx, _process_signature(command, ctx))

    started: list[str] = []
    stopped: list[str] = []
    stop_results: dict[str, str] = {}
    with PROCESS_LOCK:
        for key in list(PROCESSES):
            process = PROCESSES[key]
            desired_signature = desired[key][2] if key in desired else ""
            if key in desired and _running_signature_matches(key, process, desired_signature):
                continue
            if key not in desired and process.poll() is None:
                stopped.append(key)
            elif key in desired and process.poll() is None:
                stopped.append(key)
            stop_results[key] = _terminate_process(key, process)
        for key, (command, ctx, signature) in desired.items():
            process = PROCESSES.get(key)
            if process is not None and _running_signature_matches(key, process, signature):
                continue
            name = key.replace(":", "-")
            log_path = _log_path(Path(ctx["state_dir"]), name)
            log = log_path.open("a", encoding="utf-8")
            log.write(f"\n[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] starting: {' '.join(command)}\n")
            log.flush()
            PROCESSES[key] = subprocess.Popen(
                command,
                cwd=str(ctx["hermes_home"]),
                env=ctx["env"],
                text=True,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            PROCESS_SIGNATURES[key] = signature
            started.append(key)
    return {"desired": sorted(desired), "started": started, "stopped": stopped, "stop_results": stop_results}


def _terminate_all() -> dict[str, Any]:
    stopped: list[str] = []
    stop_results: dict[str, str] = {}
    with PROCESS_LOCK:
        for key, process in list(PROCESSES.items()):
            if process.poll() is None:
                stopped.append(key)
            stop_results[key] = _terminate_process(key, process)
    return {"stopped": stopped, "stop_results": stop_results}


def run_agent_process_helper_request(request_body: dict[str, Any]) -> tuple[bool, dict[str, Any] | str]:
    try:
        require_docker_trusted_host_risk_accepted(service=SERVICE_NAME, error_cls=ValueError)
        if not isinstance(request_body, dict):
            raise ValueError("agent process helper request must be a JSON object")
        _reject_raw_commands(request_body)
        operation = str(request_body.get("operation") or "").strip()
        if operation == "run_once":
            return True, _run_once(request_body)
        if operation == "ensure_processes":
            return True, _ensure_processes(request_body)
        if operation == "terminate_all":
            return True, _terminate_all()
        raise ValueError("agent process helper operation is not allowlisted")
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError, KeyError) as exc:
        _record_rejection_incident(request_body, exc)
        return False, str(exc)


class AgentProcessHelperHandler(BaseHTTPRequestHandler):
    server_version = "ArcLinkAgentProcessHelper/1"

    def log_message(self, fmt: str, *args: Any) -> None:
        del fmt, args

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            _json_response(self, 404, {"ok": False, "error": "not found"})
            return
        if not _helper_token():
            _json_response(self, 503, {"ok": False, "error": "agent process helper token is not configured"})
            return
        _json_response(self, 200, {"ok": True})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/agent-process":
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
            _json_response(self, 413, {"ok": False, "error": "invalid agent process helper request size"})
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            _json_response(self, 400, {"ok": False, "error": "invalid JSON"})
            return
        ok, payload = run_agent_process_helper_request(body)
        if ok:
            _json_response(self, 200, {"ok": True, "result": payload if isinstance(payload, dict) else {}})
        else:
            _json_response(self, 400, {"ok": False, "error": str(payload)})


def serve(*, host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), AgentProcessHelperHandler)
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the ArcLink agent process helper")
    parser.add_argument("--host", default=os.environ.get("ARCLINK_AGENT_PROCESS_HELPER_HOST", DEFAULT_HOST))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("ARCLINK_AGENT_PROCESS_HELPER_PORT", str(DEFAULT_PORT)) or DEFAULT_PORT),
    )
    args = parser.parse_args(argv)
    require_docker_trusted_host_risk_accepted(service=SERVICE_NAME, error_cls=SystemExit)
    if not _helper_token():
        raise SystemExit("ARCLINK_AGENT_PROCESS_HELPER_TOKEN is required")

    def stop_and_exit(_signum: int, _frame: Any) -> None:
        _terminate_all()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop_and_exit)
    signal.signal(signal.SIGINT, stop_and_exit)
    serve(host=str(args.host), port=int(args.port))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
