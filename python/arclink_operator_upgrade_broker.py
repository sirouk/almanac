#!/usr/bin/env python3
"""Dedicated Docker-mode operator upgrade broker.

The enrollment provisioner queues typed operator-upgrade requests here in
Docker mode. This broker authenticates and validates the request, then hands it
to the host-side operator upgrade runner so queued Raven upgrades use the same
host namespace path as ./deploy.sh upgrade.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import shutil
import shlex
import stat
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from arclink_boundary import (
    TRUSTED_DOCKER_BINARY_PATHS,
    require_docker_trusted_host_risk_accepted,
    require_trusted_docker_binary,
)
from arclink_rejection_incidents import private_state_rejection_path, record_rejection_incident


MAX_REQUEST_BYTES = 16384
REQUEST_SIGNATURE_TTL_SECONDS = 300
MAX_SEEN_SIGNATURE_NONCES = 4096
HOST_RUNNER_RESULT_GRACE_SECONDS = 30
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8917
OPERATOR_UPGRADE_BROKER_TOKEN_HEADER = "X-ArcLink-Operator-Upgrade-Broker-Token"
OPERATOR_UPGRADE_BROKER_TIMESTAMP_HEADER = "X-ArcLink-Operator-Upgrade-Timestamp"
OPERATOR_UPGRADE_BROKER_NONCE_HEADER = "X-ArcLink-Operator-Upgrade-Nonce"
OPERATOR_UPGRADE_BROKER_SIGNATURE_HEADER = "X-ArcLink-Operator-Upgrade-Signature"
_SEEN_SIGNATURE_NONCES: dict[str, float] = {}
_SEEN_SIGNATURE_NONCES_LOCK = threading.Lock()
_SEEN_SIGNATURE_NONCES_LOADED_FROM = ""
SAFE_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$")
ALLOWED_PIN_COMPONENTS = {"hermes-agent", "qmd", "nextcloud", "postgres", "redis", "nvm", "node"}
PIN_UPGRADE_FLAGS = {
    "git-commit": "--ref",
    "git-tag": "--tag",
    "container-image": "--tag",
    "npm": "--version",
    "nvm-version": "--version",
    "release-asset": "--version",
}
UPSTREAM_ENV_KEYS = (
    "ARCLINK_UPSTREAM_REPO_URL",
    "ARCLINK_UPSTREAM_BRANCH",
    "ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED",
    "ARCLINK_UPSTREAM_DEPLOY_KEY_USER",
    "ARCLINK_UPSTREAM_DEPLOY_KEY_PATH",
    "ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE",
)
UPSTREAM_PRIVATE_PATH_ENV_KEYS = {
    "ARCLINK_UPSTREAM_DEPLOY_KEY_PATH",
    "ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE",
}
BASE_CHILD_ENV_KEYS = (
    "HOME",
    "PATH",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "TERM",
    "SSL_CERT_FILE",
    "REQUESTS_CA_BUNDLE",
)
OPTIONAL_CHILD_ENV_KEYS = (
    "ARCLINK_DOCKER_BINARY",
    "ARCLINK_DOCKER_IMAGE",
    "ARCLINK_DOCKER_NETWORK",
    "ARCLINK_DOCKER_UID",
    "ARCLINK_DOCKER_GID",
    "ARCLINK_DOCKER_SOCKET_GID",
    "ARCLINK_STATE_ROOT_BASE",
    "RUNTIME_DIR",
)
SERVICE_NAME = "operator-upgrade-broker"
SCRIPT_READ_BITS = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
SCRIPT_EXEC_BITS = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
HOST_RUNNER_SCHEMA_VERSION = 1
HOST_RUNNER_REQUEST_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{7,80}$")


def _broker_token() -> str:
    return str(os.environ.get("ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN") or "").strip()


def _docker_binary() -> str:
    return require_trusted_docker_binary(
        os.environ.get("ARCLINK_DOCKER_BINARY"),
        service="operator upgrade broker",
        trusted_paths=TRUSTED_DOCKER_BINARY_PATHS,
        which=shutil.which,
    )


def _host_priv_dir() -> str:
    host_priv = str(os.environ.get("ARCLINK_DOCKER_HOST_PRIV_DIR") or "").strip()
    if not host_priv:
        raise ValueError("ARCLINK_DOCKER_HOST_PRIV_DIR is required for operator upgrade broker operations")
    if not Path(host_priv).is_absolute():
        raise ValueError("ARCLINK_DOCKER_HOST_PRIV_DIR must be an absolute host path")
    return host_priv


def _host_repo_dir() -> Path:
    host_repo = str(os.environ.get("ARCLINK_DOCKER_HOST_REPO_DIR") or "").strip()
    if not host_repo:
        raise ValueError("ARCLINK_DOCKER_HOST_REPO_DIR is required for operator upgrades")
    path = Path(host_repo).resolve(strict=False)
    if not path.is_absolute():
        raise ValueError("ARCLINK_DOCKER_HOST_REPO_DIR must be an absolute host path")
    return path


def _container_priv_dir() -> str:
    container_priv = str(
        os.environ.get("ARCLINK_DOCKER_CONTAINER_PRIV_DIR") or "/home/arclink/arclink/arclink-priv"
    ).strip()
    path = Path(container_priv)
    if not path.is_absolute() or "arclink-priv" not in path.parts:
        raise ValueError("ARCLINK_DOCKER_CONTAINER_PRIV_DIR is not an ArcLink private-state path")
    return container_priv


def _reject_raw_commands(request_body: dict[str, Any]) -> None:
    if any(key in request_body for key in ("args", "cmd", "command")):
        raise ValueError("operator upgrade broker does not accept raw commands")


def _single_line(value: Any, *, label: str, allow_blank: bool = True, max_chars: int = 512) -> str:
    clean = str(value or "").strip()
    if not clean and allow_blank:
        return ""
    if not clean:
        raise ValueError(f"operator upgrade broker {label} is required")
    if "\n" in clean or "\r" in clean or "\x00" in clean:
        raise ValueError(f"operator upgrade broker {label} must be a single line")
    if len(clean) > max_chars:
        raise ValueError(f"operator upgrade broker {label} is too long")
    return clean


def _require_private_upstream_path(value: str, *, label: str, private_dir: Path) -> str:
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"operator upgrade broker upstream {label} must be an absolute private-state path")
    private_root = private_dir.resolve(strict=False)
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(private_root)
    except ValueError:
        raise ValueError(f"operator upgrade broker upstream {label} must stay under private state") from None
    try:
        rel_path = path.relative_to(private_dir)
    except ValueError:
        raise ValueError(f"operator upgrade broker upstream {label} must stay under private state") from None
    try:
        root_stat = private_dir.lstat()
    except OSError:
        raise ValueError("operator upgrade broker upstream private state root is unavailable") from None
    if stat.S_ISLNK(root_stat.st_mode):
        raise ValueError("operator upgrade broker upstream private state root must not be a symlink")
    current = private_dir
    for index, part in enumerate(rel_path.parts):
        if part in ("", ".") or part == "..":
            raise ValueError(f"operator upgrade broker upstream {label} must stay under private state")
        current = current / part
        try:
            item_stat = current.lstat()
        except OSError:
            if index < len(rel_path.parts) - 1:
                raise ValueError(f"operator upgrade broker upstream {label} parent path is unavailable") from None
            break
        if stat.S_ISLNK(item_stat.st_mode):
            raise ValueError(f"operator upgrade broker upstream {label} must not be a symlink")
        if index < len(rel_path.parts) - 1 and not stat.S_ISDIR(item_stat.st_mode):
            raise ValueError(f"operator upgrade broker upstream {label} parent is not a directory")
    return value


def _upstream_env_value(key: str, value: Any, *, private_dir: Path) -> str:
    clean = _single_line(value, label=key, allow_blank=True)
    if not clean:
        return ""
    if key in UPSTREAM_PRIVATE_PATH_ENV_KEYS:
        return _require_private_upstream_path(clean, label=key, private_dir=private_dir)
    return clean


def _operator_env(request_body: dict[str, Any]) -> dict[str, str]:
    repo_dir = _host_repo_dir()
    private_dir_raw = Path(_host_priv_dir())
    private_dir = private_dir_raw.resolve(strict=False)
    container_priv_dir = Path(_container_priv_dir()).resolve(strict=False)
    env: dict[str, str] = {}
    for key in BASE_CHILD_ENV_KEYS:
        value = _single_line(os.environ.get(key), label=key, allow_blank=True, max_chars=4096)
        if value:
            env[key] = value
    env.setdefault("HOME", "/home/arclink")
    env.setdefault("PATH", os.defpath)
    env.update(
        {
            "ARCLINK_DOCKER_MODE": "1",
            "ARCLINK_CONTAINER_RUNTIME": "docker",
            "ARCLINK_COMPONENT_UPGRADE_MODE": "docker",
            "ARCLINK_REPO_DIR": str(repo_dir),
            "ARCLINK_PRIV_DIR": str(private_dir),
            "ARCLINK_PRIV_CONFIG_DIR": str(private_dir / "config"),
            "ARCLINK_DOCKER_HOST_REPO_DIR": str(repo_dir),
            "ARCLINK_DOCKER_HOST_PRIV_DIR": str(private_dir),
            "ARCLINK_DOCKER_CONTAINER_PRIV_DIR": str(container_priv_dir),
            "STATE_DIR": str(private_dir / "state"),
            "ARCLINK_CONFIG_FILE": str(private_dir / "config" / "docker.env"),
        }
    )
    for key in OPTIONAL_CHILD_ENV_KEYS:
        if key == "ARCLINK_DOCKER_BINARY":
            if _single_line(os.environ.get(key), label=key, allow_blank=True, max_chars=4096):
                env[key] = _docker_binary()
            continue
        value = _single_line(os.environ.get(key), label=key, allow_blank=True, max_chars=4096)
        if value:
            env[key] = value
    env.setdefault("RUNTIME_DIR", "/opt/arclink/runtime")
    upstream = request_body.get("upstream")
    if isinstance(upstream, dict):
        for key in UPSTREAM_ENV_KEYS:
            value = _upstream_env_value(key, upstream.get(key), private_dir=private_dir_raw)
            if value:
                env[key] = value
    return env


def _host_runner_enabled() -> bool:
    value = str(os.environ.get("ARCLINK_OPERATOR_UPGRADE_HOST_RUNNER_ENABLED", "1") or "").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _normalized_upstream(request_body: dict[str, Any], *, private_dir: Path) -> dict[str, str]:
    upstream = request_body.get("upstream")
    normalized: dict[str, str] = {}
    if isinstance(upstream, dict):
        for key in UPSTREAM_ENV_KEYS:
            value = _upstream_env_value(key, upstream.get(key), private_dir=private_dir)
            if value:
                normalized[key] = value
    return normalized


def _normalized_pin_upgrade_item(item: dict[str, Any]) -> dict[str, str]:
    component = _single_line(item.get("component"), label="pin upgrade component", allow_blank=False, max_chars=96)
    if not SAFE_COMPONENT_RE.fullmatch(component) or component not in ALLOWED_PIN_COMPONENTS:
        raise ValueError("operator upgrade broker pin upgrade component is not allowlisted")
    kind = _single_line(item.get("kind"), label=f"{component} pin upgrade kind", allow_blank=False, max_chars=64)
    target = _single_line(item.get("target"), label=f"{component} pin upgrade target", allow_blank=False, max_chars=240)
    if kind not in PIN_UPGRADE_FLAGS:
        raise ValueError(f"operator upgrade broker pin upgrade kind is not allowlisted: {kind}")
    return {"component": component, "kind": kind, "target": target}


def _host_runner_queue_root() -> Path:
    configured = str(os.environ.get("ARCLINK_OPERATOR_UPGRADE_HOST_QUEUE_DIR") or "").strip()
    host_state_root = Path(_host_priv_dir()).resolve(strict=False) / "state"
    if configured:
        root = Path(configured).resolve(strict=False)
        if not root.is_absolute():
            raise ValueError("operator upgrade host runner queue path must be absolute")
        try:
            root.relative_to(host_state_root)
        except ValueError:
            raise ValueError("operator upgrade host runner queue path must stay under private state") from None
        return root
    return host_state_root / "operator-upgrade-host-runner"


def _host_runner_request_id() -> str:
    return f"op-{int(time.time())}-{uuid.uuid4().hex}"


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _host_runner_poll_interval() -> float:
    raw = str(os.environ.get("ARCLINK_OPERATOR_UPGRADE_HOST_RUNNER_POLL_SECONDS") or "1").strip()
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = 1.0
    return max(0.05, min(5.0, value))


def _run_host_runner_request(operation: str, request_body: dict[str, Any]) -> dict[str, Any]:
    _reject_raw_commands(request_body)
    repo_dir = _host_repo_dir()
    private_dir_raw = Path(_host_priv_dir())
    private_dir = private_dir_raw.resolve(strict=False)
    log_path = _require_operator_log_path(str(request_body.get("log_path") or ""))
    timeout_seconds = _operator_timeout(request_body)
    request_id = _host_runner_request_id()
    if not HOST_RUNNER_REQUEST_ID_RE.fullmatch(request_id):
        raise ValueError("operator upgrade host runner request id is invalid")
    queue_root = _host_runner_queue_root()
    pending_dir = queue_root / "pending"
    results_dir = queue_root / "results"
    result_path = results_dir / f"{request_id}.json"
    poll_interval = _host_runner_poll_interval()
    wait_seconds = max(30, min(21630, timeout_seconds + HOST_RUNNER_RESULT_GRACE_SECONDS))
    payload: dict[str, Any] = {
        "schema_version": HOST_RUNNER_SCHEMA_VERSION,
        "request_id": request_id,
        "created_at": int(time.time()),
        "operation": operation,
        "repo_dir": str(repo_dir),
        "priv_dir": str(private_dir),
        "container_priv_dir": _container_priv_dir(),
        "log_path": str(log_path),
        "timeout_seconds": timeout_seconds,
        "upstream": _normalized_upstream(request_body, private_dir=private_dir_raw),
    }
    if operation == "run_pin_upgrade":
        install_items = request_body.get("install_items")
        if not isinstance(install_items, list) or not install_items:
            raise ValueError("operator upgrade broker pin upgrade request has no install items")
        normalized_items: list[dict[str, str]] = []
        for item in install_items:
            if not isinstance(item, dict):
                raise ValueError("operator upgrade broker pin upgrade item must be a JSON object")
            normalized_items.append(_normalized_pin_upgrade_item(item))
        payload["install_items"] = normalized_items
    request_path = pending_dir / f"{request_id}.json"
    _atomic_write_json(request_path, payload)
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if result_path.exists():
            try:
                result = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"operator upgrade host runner returned an unreadable result: {exc}") from None
            if not isinstance(result, dict):
                raise RuntimeError("operator upgrade host runner returned an invalid result")
            try:
                result_path.unlink(missing_ok=True)
            except OSError:
                pass
            if result.get("ok") is not True:
                raise RuntimeError(
                    str(result.get("error") or result.get("message") or "operator upgrade host runner failed")
                )
            returncode = result.get("returncode")
            if type(returncode) is not int:
                raise RuntimeError("operator upgrade host runner result did not include an integer returncode") from None
            return {"returncode": returncode, "host_runner": True, "request_id": request_id}
        time.sleep(poll_interval)
    raise RuntimeError(
        "operator upgrade host runner did not complete the queued request before timeout; "
        "check arclink-operator-upgrade-host-runner.timer on the host"
    )


def _operator_timeout(request_body: dict[str, Any]) -> int:
    try:
        value = int(str(request_body.get("timeout_seconds") or "").strip())
    except (TypeError, ValueError):
        value = 7200
    return max(30, min(21600, value))


def _require_operator_log_path(value: str) -> Path:
    container_priv = Path(_container_priv_dir()).resolve(strict=False)
    host_priv = Path(_host_priv_dir()).resolve(strict=False)
    container_root = (container_priv / "state" / "operator-actions").resolve(strict=False)
    host_root = (host_priv / "state" / "operator-actions").resolve(strict=False)
    try:
        path = Path(str(value or "").strip()).resolve(strict=False)
    except OSError:
        raise ValueError("operator upgrade broker operator log path is not valid") from None
    for allowed_root, target_root in ((host_root, host_root), (container_root, host_root)):
        try:
            rel_path = path.relative_to(allowed_root)
        except ValueError:
            continue
        mapped_path = (target_root / rel_path).resolve(strict=False)
        try:
            mapped_path.relative_to(host_root)
        except ValueError:
            raise ValueError("operator upgrade broker operator log path must stay under private operator-actions state") from None
        mapped_path.parent.mkdir(parents=True, exist_ok=True)
        return mapped_path
    raise ValueError("operator upgrade broker operator log path must stay under private operator-actions state")


def _require_operator_repo_script(repo_dir: Path, relative: str) -> Path:
    rel_path = Path(relative)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        raise ValueError("operator upgrade broker operator script path is not allowlisted")
    path = repo_dir / rel_path
    try:
        path.relative_to(repo_dir)
    except ValueError:
        raise ValueError("operator upgrade broker operator script escaped the host repo") from None
    current = repo_dir
    for index, part in enumerate(rel_path.parts):
        current = current / part
        try:
            item_stat = current.lstat()
        except OSError:
            raise ValueError(f"operator upgrade broker operator script is missing: {relative}") from None
        if stat.S_ISLNK(item_stat.st_mode):
            raise ValueError(f"operator upgrade broker operator script must not be a symlink: {relative}")
        if index < len(rel_path.parts) - 1 and not stat.S_ISDIR(item_stat.st_mode):
            raise ValueError(f"operator upgrade broker operator script parent is not a directory: {relative}")
    if not stat.S_ISREG(item_stat.st_mode):
        raise ValueError(f"operator upgrade broker operator script is not a regular file: {relative}")
    if not item_stat.st_mode & SCRIPT_READ_BITS:
        raise ValueError(f"operator upgrade broker operator script is not readable: {relative}")
    if not item_stat.st_mode & SCRIPT_EXEC_BITS:
        raise ValueError(f"operator upgrade broker operator script is not executable: {relative}")
    try:
        current.resolve(strict=True).relative_to(repo_dir)
    except (OSError, ValueError):
        raise ValueError("operator upgrade broker operator script escaped the host repo") from None
    if current.resolve(strict=True) != path.resolve(strict=True):
        raise ValueError(f"operator upgrade broker operator script is not the fixed repo target: {relative}")
    if not path.is_file():
        raise ValueError(f"operator upgrade broker operator script is missing: {relative}")
    return path


def _run_logged_command(
    handle: Any,
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    handle.write(f"$ {' '.join(shlex.quote(str(arg)) for arg in args)}\n")
    handle.flush()
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd),
            env=env,
            text=True,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        handle.write(f"\ncommand timed out after {timeout_seconds}s\n")
        handle.flush()
        return subprocess.CompletedProcess(args=args, returncode=124, stdout="", stderr="timeout")
    handle.write(f"\n[exit {result.returncode}]\n")
    handle.flush()
    return result


def _component_upgrade_statuses_from_text(text: str) -> list[str]:
    prefix = "ARCLINK_COMPONENT_UPGRADE_STATUS="
    statuses: list[str] = []
    for line in text.splitlines():
        clean = line.strip()
        if not clean.startswith(prefix):
            continue
        status = clean[len(prefix) :].strip().lower()
        if status:
            statuses.append(status)
    return statuses


def _pin_upgrade_log_requires_deploy(log_path: Path, *, expected_statuses: int) -> bool:
    try:
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True
    statuses = _component_upgrade_statuses_from_text(log_text)
    recent = statuses[-expected_statuses:] if expected_statuses > 0 else []
    if len(recent) < expected_statuses:
        return True
    if any(status not in {"noop", "changed", "pushed"} for status in recent):
        return True
    return any(status in {"changed", "pushed"} for status in recent)


def _run_operator_upgrade(request_body: dict[str, Any]) -> dict[str, Any]:
    _reject_raw_commands(request_body)
    log_path = _require_operator_log_path(str(request_body.get("log_path") or ""))
    repo_dir = _host_repo_dir()
    deploy = _require_operator_repo_script(repo_dir, "deploy.sh")
    env = _operator_env(request_body)
    timeout_seconds = _operator_timeout(request_body)
    with log_path.open("w", encoding="utf-8") as handle:
        result = _run_logged_command(
            handle,
            [str(deploy), "upgrade"],
            cwd=repo_dir,
            env=env,
            timeout_seconds=timeout_seconds,
        )
    return {"returncode": int(result.returncode)}


def _pin_upgrade_command(component_upgrade: Path, item: dict[str, Any]) -> list[str]:
    component = _single_line(item.get("component"), label="pin upgrade component", allow_blank=False, max_chars=96)
    if not SAFE_COMPONENT_RE.fullmatch(component) or component not in ALLOWED_PIN_COMPONENTS:
        raise ValueError("operator upgrade broker pin upgrade component is not allowlisted")
    kind = _single_line(item.get("kind"), label=f"{component} pin upgrade kind", allow_blank=False, max_chars=64)
    target = _single_line(item.get("target"), label=f"{component} pin upgrade target", allow_blank=False, max_chars=240)
    flag = PIN_UPGRADE_FLAGS.get(kind)
    if not flag:
        raise ValueError(f"operator upgrade broker pin upgrade kind is not allowlisted: {kind}")
    return [str(component_upgrade), component, "apply", flag, target, "--skip-push", "--skip-upgrade"]


def _run_pin_upgrade(request_body: dict[str, Any]) -> dict[str, Any]:
    _reject_raw_commands(request_body)
    install_items = request_body.get("install_items")
    if not isinstance(install_items, list) or not install_items:
        raise ValueError("operator upgrade broker pin upgrade request has no install items")
    log_path = _require_operator_log_path(str(request_body.get("log_path") or ""))
    repo_dir = _host_repo_dir()
    deploy = _require_operator_repo_script(repo_dir, "deploy.sh")
    component_upgrade = _require_operator_repo_script(repo_dir, "bin/component-upgrade.sh")
    commands: list[list[str]] = []
    for item in install_items:
        if not isinstance(item, dict):
            raise ValueError("operator upgrade broker pin upgrade item must be a JSON object")
        commands.append(_pin_upgrade_command(component_upgrade, item))
    env = _operator_env(request_body)
    timeout_seconds = _operator_timeout(request_body)
    with log_path.open("w", encoding="utf-8") as handle:
        last_result: subprocess.CompletedProcess[str] | None = None
        for command in commands:
            last_result = _run_logged_command(
                handle,
                command,
                cwd=repo_dir,
                env=env,
                timeout_seconds=timeout_seconds,
            )
            if last_result.returncode != 0:
                return {"returncode": int(last_result.returncode)}
        handle.flush()
        if not _pin_upgrade_log_requires_deploy(log_path, expected_statuses=len(commands)):
            handle.write("All requested pinned components were already current; skipping deploy upgrade.\n")
            handle.flush()
            return {"returncode": int(last_result.returncode if last_result is not None else 0)}
        deploy_env = dict(env)
        deploy_env["ARCLINK_CONTROL_UPGRADE_ALLOW_DIRTY"] = "1"
        handle.write("Applying queued pin changes from the local checkout without pushing upstream.\n")
        handle.flush()
        last_result = _run_logged_command(
            handle,
            [str(deploy), "upgrade"],
            cwd=repo_dir,
            env=deploy_env,
            timeout_seconds=timeout_seconds,
        )
    return {"returncode": int(last_result.returncode if last_result is not None else 0)}


def _rejection_reason(exc: BaseException) -> str:
    text = str(exc).lower()
    if "raw commands" in text:
        return "raw_command_rejected"
    if "trusted-host residual risk" in text:
        return "trusted_host_risk_not_accepted"
    if "operation" in text and "allowlisted" in text:
        return "operation_not_allowlisted"
    if "docker cli" in text:
        return "docker_cli_rejected"
    if "operator script" in text:
        return "operator_script_rejected"
    if "upstream" in text:
        return "upstream_private_path_rejected"
    if "operator log path" in text:
        return "operator_log_path_rejected"
    if "pin upgrade" in text:
        return "pin_upgrade_request_rejected"
    if isinstance(exc, subprocess.SubprocessError):
        return "subprocess_failed"
    if isinstance(exc, OSError):
        return "filesystem_error"
    return "validation_rejected"


def _rejection_message(reason: str) -> str:
    messages = {
        "raw_command_rejected": "Rejected raw command input.",
        "trusted_host_risk_not_accepted": "Rejected request before trusted-host acknowledgement.",
        "operation_not_allowlisted": "Rejected non-allowlisted operator upgrade operation.",
        "docker_cli_rejected": "Rejected unsafe Docker CLI configuration.",
        "operator_script_rejected": "Rejected unsafe fixed operator script target.",
        "upstream_private_path_rejected": "Rejected unsafe upstream private path.",
        "operator_log_path_rejected": "Rejected unsafe operator log path.",
        "pin_upgrade_request_rejected": "Rejected unsafe pin-upgrade request.",
        "subprocess_failed": "Operator upgrade subprocess failed.",
        "filesystem_error": "Operator upgrade broker filesystem preflight failed.",
        "validation_rejected": "Rejected operator upgrade broker request during validation.",
    }
    return messages.get(reason, messages["validation_rejected"])


def _incident_metadata(request_body: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if not isinstance(request_body, dict):
        return metadata
    operation = str(request_body.get("operation") or "").strip()
    if operation in {"run_operator_upgrade", "run_pin_upgrade"}:
        metadata["operation"] = operation
    install_items = request_body.get("install_items")
    if operation == "run_pin_upgrade" and isinstance(install_items, list):
        metadata["install_item_count"] = len(install_items)
    return metadata


def _record_rejection_incident(request_body: Any, exc: BaseException) -> None:
    reason = _rejection_reason(exc)
    record_rejection_incident(
        private_state_rejection_path(SERVICE_NAME, env_name="ARCLINK_DOCKER_HOST_PRIV_DIR"),
        service=SERVICE_NAME,
        event="operator_upgrade_broker_request_rejected",
        reason=reason,
        message=_rejection_message(reason),
        error_class=exc.__class__.__name__,
        metadata=_incident_metadata(request_body),
    )


def run_operator_upgrade_request(request_body: dict[str, Any]) -> tuple[bool, dict[str, Any] | str]:
    try:
        require_docker_trusted_host_risk_accepted(service=SERVICE_NAME, error_cls=ValueError)
        if not isinstance(request_body, dict):
            raise ValueError("operator upgrade broker request must be a JSON object")
        operation = str(request_body.get("operation") or "").strip()
        if operation == "run_operator_upgrade":
            if _host_runner_enabled():
                return True, _run_host_runner_request(operation, request_body)
            return True, _run_operator_upgrade(request_body)
        if operation == "run_pin_upgrade":
            if _host_runner_enabled():
                return True, _run_host_runner_request(operation, request_body)
            return True, _run_pin_upgrade(request_body)
        raise ValueError("operator upgrade broker operation is not allowlisted")
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        _record_rejection_incident(request_body, exc)
        return False, str(exc)


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _nonce_store_path() -> Path | None:
    try:
        host_priv = Path(_host_priv_dir()).resolve(strict=False)
    except ValueError:
        return None
    return host_priv / "state" / "docker" / SERVICE_NAME / "signature-nonces.json"


def _prune_seen_nonces_locked(cutoff: float) -> None:
    for key, observed in list(_SEEN_SIGNATURE_NONCES.items()):
        if observed < cutoff:
            _SEEN_SIGNATURE_NONCES.pop(key, None)


def _load_persisted_nonces_locked(path: Path | None, now: float) -> bool:
    global _SEEN_SIGNATURE_NONCES_LOADED_FROM
    if path is None:
        return True
    path_key = str(path)
    if _SEEN_SIGNATURE_NONCES_LOADED_FROM == path_key:
        return True
    cutoff = now - REQUEST_SIGNATURE_TTL_SECONDS
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        data = {}
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    for key, observed in data.items():
        nonce = str(key or "")
        try:
            observed_at = float(observed)
        except (TypeError, ValueError):
            continue
        if observed_at >= cutoff and re.fullmatch(r"[A-Za-z0-9_.~+/=-]{16,160}", nonce):
            _SEEN_SIGNATURE_NONCES[nonce] = observed_at
    _SEEN_SIGNATURE_NONCES_LOADED_FROM = path_key
    return True


def _persist_seen_nonces_locked(path: Path | None) -> bool:
    if path is None:
        return True
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(_SEEN_SIGNATURE_NONCES, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        return False
    return True


def _record_nonce_if_unseen(nonce: str, now: float) -> bool:
    cutoff = now - REQUEST_SIGNATURE_TTL_SECONDS
    with _SEEN_SIGNATURE_NONCES_LOCK:
        path = _nonce_store_path()
        if not _load_persisted_nonces_locked(path, now):
            return False
        _prune_seen_nonces_locked(cutoff)
        if nonce in _SEEN_SIGNATURE_NONCES:
            return False
        while len(_SEEN_SIGNATURE_NONCES) >= MAX_SEEN_SIGNATURE_NONCES:
            oldest = min(_SEEN_SIGNATURE_NONCES, key=_SEEN_SIGNATURE_NONCES.get)
            _SEEN_SIGNATURE_NONCES.pop(oldest, None)
        _SEEN_SIGNATURE_NONCES[nonce] = now
        if not _persist_seen_nonces_locked(path):
            _SEEN_SIGNATURE_NONCES.pop(nonce, None)
            return False
        return True


def _is_authorized(headers: Any, raw_body: bytes) -> bool:
    expected = _broker_token()
    supplied = str(headers.get(OPERATOR_UPGRADE_BROKER_TOKEN_HEADER) or "").strip()
    if not (expected and supplied and hmac.compare_digest(expected, supplied)):
        return False
    timestamp_raw = str(headers.get(OPERATOR_UPGRADE_BROKER_TIMESTAMP_HEADER) or "").strip()
    nonce = str(headers.get(OPERATOR_UPGRADE_BROKER_NONCE_HEADER) or "").strip()
    supplied_signature = str(headers.get(OPERATOR_UPGRADE_BROKER_SIGNATURE_HEADER) or "").strip()
    if not (timestamp_raw and nonce and supplied_signature):
        return False
    try:
        timestamp = int(timestamp_raw)
    except (TypeError, ValueError):
        return False
    now = time.time()
    if abs(now - timestamp) > REQUEST_SIGNATURE_TTL_SECONDS:
        return False
    if not re.fullmatch(r"[A-Za-z0-9_.~+/=-]{16,160}", nonce):
        return False
    body_hash = hashlib.sha256(raw_body).hexdigest()
    expected_signature = hmac.new(
        expected.encode("utf-8"),
        f"{timestamp}\n{nonce}\n{body_hash}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_signature, supplied_signature):
        return False
    return _record_nonce_if_unseen(nonce, now)


class OperatorUpgradeBrokerHandler(BaseHTTPRequestHandler):
    server_version = "ArcLinkOperatorUpgradeBroker/1"

    def log_message(self, fmt: str, *args: Any) -> None:
        del fmt, args

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            _json_response(self, 404, {"ok": False, "error": "not found"})
            return
        if not _broker_token():
            _json_response(self, 503, {"ok": False, "error": "operator upgrade broker token is not configured"})
            return
        _json_response(self, 200, {"ok": True})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/operator-upgrade":
            _json_response(self, 404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_REQUEST_BYTES:
            _json_response(self, 413, {"ok": False, "error": "invalid operator upgrade request size"})
            return
        raw_body = self.rfile.read(length)
        if not _is_authorized(self.headers, raw_body):
            _json_response(self, 401, {"ok": False, "error": "unauthorized"})
            return
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            _json_response(self, 400, {"ok": False, "error": "invalid JSON"})
            return
        if not isinstance(body, dict):
            _json_response(self, 400, {"ok": False, "error": "operator upgrade request must be a JSON object"})
            return
        ok, payload = run_operator_upgrade_request(body)
        if ok:
            _json_response(self, 200, {"ok": True, "result": payload if isinstance(payload, dict) else {}})
        else:
            _json_response(self, 400, {"ok": False, "error": str(payload)})


def serve(*, host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), OperatorUpgradeBrokerHandler)
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the ArcLink operator upgrade broker")
    parser.add_argument("--host", default=os.environ.get("ARCLINK_OPERATOR_UPGRADE_BROKER_HOST", DEFAULT_HOST))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("ARCLINK_OPERATOR_UPGRADE_BROKER_PORT", str(DEFAULT_PORT)) or DEFAULT_PORT),
    )
    args = parser.parse_args(argv)
    require_docker_trusted_host_risk_accepted(service=SERVICE_NAME, error_cls=SystemExit)
    if not _broker_token():
        raise SystemExit("ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN is required")
    serve(host=str(args.host), port=int(args.port))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
