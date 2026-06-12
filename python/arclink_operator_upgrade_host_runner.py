#!/usr/bin/env python3
"""Host-side executor for Raven queued operator upgrades.

The Docker broker authenticates requests and writes typed JSON into private
state. This runner is installed as a host systemd oneshot/timer and executes the
same canonical host upgrade flow an operator would run manually.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shlex
import stat
import subprocess
import time
from pathlib import Path
from typing import Any


HOST_RUNNER_SCHEMA_VERSION = 1
SAFE_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$")
REQUEST_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{7,80}$")
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
SCRIPT_READ_BITS = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
SCRIPT_EXEC_BITS = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH


def _repo_dir() -> Path:
    configured = str(os.environ.get("ARCLINK_OPERATOR_UPGRADE_HOST_REPO_DIR") or "").strip()
    if configured:
        path = Path(configured).resolve(strict=False)
    else:
        path = Path(__file__).resolve().parents[1]
    if not path.is_absolute():
        raise ValueError("operator upgrade host repo path must be absolute")
    return path


def _priv_dir(repo_dir: Path) -> Path:
    configured = str(os.environ.get("ARCLINK_OPERATOR_UPGRADE_HOST_PRIV_DIR") or "").strip()
    path = Path(configured).resolve(strict=False) if configured else (repo_dir / "arclink-priv").resolve(strict=False)
    if not path.is_absolute() or path.name != "arclink-priv":
        raise ValueError("operator upgrade host private-state path must be an absolute arclink-priv path")
    return path


def _queue_root(priv_dir: Path) -> Path:
    configured = str(os.environ.get("ARCLINK_OPERATOR_UPGRADE_HOST_QUEUE_DIR") or "").strip()
    root = Path(configured).resolve(strict=False) if configured else priv_dir / "state" / "operator-upgrade-host-runner"
    if not root.is_absolute():
        raise ValueError("operator upgrade host runner queue path must be absolute")
    return root


def _single_line(value: Any, *, label: str, allow_blank: bool = True, max_chars: int = 512) -> str:
    clean = str(value or "").strip()
    if not clean and allow_blank:
        return ""
    if not clean:
        raise ValueError(f"operator upgrade host runner {label} is required")
    if "\n" in clean or "\r" in clean or "\x00" in clean:
        raise ValueError(f"operator upgrade host runner {label} must be a single line")
    if len(clean) > max_chars:
        raise ValueError(f"operator upgrade host runner {label} is too long")
    return clean


def _require_child_path(value: str, *, root: Path, label: str, mkdir_parent: bool = False) -> Path:
    try:
        path = Path(value).resolve(strict=False)
    except OSError:
        raise ValueError(f"operator upgrade host runner {label} path is not valid") from None
    root = root.resolve(strict=False)
    try:
        path.relative_to(root)
    except ValueError:
        raise ValueError(f"operator upgrade host runner {label} must stay under {root}") from None
    if mkdir_parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _require_repo_script(repo_dir: Path, relative: str) -> Path:
    rel_path = Path(relative)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        raise ValueError("operator upgrade host runner script path is not allowlisted")
    path = repo_dir / rel_path
    current = repo_dir
    item_stat: os.stat_result | None = None
    for index, part in enumerate(rel_path.parts):
        current = current / part
        try:
            item_stat = current.lstat()
        except OSError:
            raise ValueError(f"operator upgrade host runner script is missing: {relative}") from None
        if stat.S_ISLNK(item_stat.st_mode):
            raise ValueError(f"operator upgrade host runner script must not be a symlink: {relative}")
        if index < len(rel_path.parts) - 1 and not stat.S_ISDIR(item_stat.st_mode):
            raise ValueError(f"operator upgrade host runner script parent is not a directory: {relative}")
    if item_stat is None or not stat.S_ISREG(item_stat.st_mode):
        raise ValueError(f"operator upgrade host runner script is not a regular file: {relative}")
    if not item_stat.st_mode & SCRIPT_READ_BITS:
        raise ValueError(f"operator upgrade host runner script is not readable: {relative}")
    if not item_stat.st_mode & SCRIPT_EXEC_BITS:
        raise ValueError(f"operator upgrade host runner script is not executable: {relative}")
    try:
        current.resolve(strict=True).relative_to(repo_dir.resolve(strict=True))
    except (OSError, ValueError):
        raise ValueError("operator upgrade host runner script escaped the host repo") from None
    return path


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _operator_timeout(request_body: dict[str, Any]) -> int:
    try:
        value = int(str(request_body.get("timeout_seconds") or "").strip())
    except (TypeError, ValueError):
        value = 7200
    return max(30, min(21600, value))


def _operator_env(request_body: dict[str, Any], *, repo_dir: Path, priv_dir: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for key in BASE_CHILD_ENV_KEYS:
        value = _single_line(os.environ.get(key), label=key, allow_blank=True, max_chars=4096)
        if value:
            env[key] = value
    env.setdefault("HOME", "/root")
    env.setdefault("PATH", os.defpath)
    env.update(
        {
            "ARCLINK_DOCKER_MODE": "1",
            "ARCLINK_CONTAINER_RUNTIME": "docker",
            "ARCLINK_COMPONENT_UPGRADE_MODE": "docker",
            "ARCLINK_REPO_DIR": str(repo_dir),
            "ARCLINK_PRIV_DIR": str(priv_dir),
            "ARCLINK_PRIV_CONFIG_DIR": str(priv_dir / "config"),
            "ARCLINK_DOCKER_HOST_REPO_DIR": str(repo_dir),
            "ARCLINK_DOCKER_HOST_PRIV_DIR": str(priv_dir),
            "ARCLINK_DOCKER_CONTAINER_PRIV_DIR": str(request_body.get("container_priv_dir") or priv_dir),
            "STATE_DIR": str(priv_dir / "state"),
            "ARCLINK_CONFIG_FILE": str(priv_dir / "config" / "docker.env"),
        }
    )
    for key in OPTIONAL_CHILD_ENV_KEYS:
        value = _single_line(os.environ.get(key), label=key, allow_blank=True, max_chars=4096)
        if value:
            env[key] = value
    env.setdefault("RUNTIME_DIR", "/opt/arclink/runtime")
    upstream = request_body.get("upstream")
    if isinstance(upstream, dict):
        for key in UPSTREAM_ENV_KEYS:
            value = _single_line(upstream.get(key), label=key, allow_blank=True, max_chars=4096)
            if value:
                env[key] = value
    return env


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
        if clean.startswith(prefix):
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


def _pin_upgrade_command(component_upgrade: Path, item: dict[str, Any]) -> list[str]:
    component = _single_line(item.get("component"), label="pin upgrade component", allow_blank=False, max_chars=96)
    if not SAFE_COMPONENT_RE.fullmatch(component) or component not in ALLOWED_PIN_COMPONENTS:
        raise ValueError("operator upgrade host runner pin upgrade component is not allowlisted")
    kind = _single_line(item.get("kind"), label=f"{component} pin upgrade kind", allow_blank=False, max_chars=64)
    target = _single_line(item.get("target"), label=f"{component} pin upgrade target", allow_blank=False, max_chars=240)
    flag = PIN_UPGRADE_FLAGS.get(kind)
    if not flag:
        raise ValueError(f"operator upgrade host runner pin upgrade kind is not allowlisted: {kind}")
    return [str(component_upgrade), component, "apply", flag, target, "--skip-upgrade"]


def _validate_request(request_body: dict[str, Any], *, repo_dir: Path, priv_dir: Path) -> dict[str, Any]:
    if any(key in request_body for key in ("args", "cmd", "command")):
        raise ValueError("operator upgrade host runner does not accept raw commands")
    if int(request_body.get("schema_version") or 0) != HOST_RUNNER_SCHEMA_VERSION:
        raise ValueError("operator upgrade host runner request schema is unsupported")
    request_id = _single_line(request_body.get("request_id"), label="request_id", allow_blank=False, max_chars=96)
    if not REQUEST_ID_RE.fullmatch(request_id):
        raise ValueError("operator upgrade host runner request id is invalid")
    operation = _single_line(request_body.get("operation"), label="operation", allow_blank=False, max_chars=64)
    if operation not in {"run_operator_upgrade", "run_pin_upgrade"}:
        raise ValueError("operator upgrade host runner operation is not allowlisted")
    supplied_repo = _single_line(request_body.get("repo_dir"), label="repo_dir", allow_blank=True, max_chars=4096)
    supplied_priv = _single_line(request_body.get("priv_dir"), label="priv_dir", allow_blank=True, max_chars=4096)
    if supplied_repo and Path(supplied_repo).resolve(strict=False) != repo_dir.resolve(strict=False):
        raise ValueError("operator upgrade host runner request repo_dir does not match this host")
    if supplied_priv and Path(supplied_priv).resolve(strict=False) != priv_dir.resolve(strict=False):
        raise ValueError("operator upgrade host runner request priv_dir does not match this host")
    log_root = priv_dir / "state" / "operator-actions"
    log_path = _require_child_path(
        _single_line(request_body.get("log_path"), label="log_path", allow_blank=False, max_chars=4096),
        root=log_root,
        label="operator log",
        mkdir_parent=True,
    )
    normalized: dict[str, Any] = {
        "request_id": request_id,
        "operation": operation,
        "log_path": log_path,
        "timeout_seconds": _operator_timeout(request_body),
        "container_priv_dir": _single_line(
            request_body.get("container_priv_dir"), label="container_priv_dir", allow_blank=True, max_chars=4096
        ),
        "upstream": {},
    }
    upstream = request_body.get("upstream")
    if isinstance(upstream, dict):
        normalized["upstream"] = {
            key: _single_line(upstream.get(key), label=key, allow_blank=True, max_chars=4096)
            for key in UPSTREAM_ENV_KEYS
            if _single_line(upstream.get(key), label=key, allow_blank=True, max_chars=4096)
        }
    if operation == "run_pin_upgrade":
        install_items = request_body.get("install_items")
        if not isinstance(install_items, list) or not install_items:
            raise ValueError("operator upgrade host runner pin upgrade request has no install items")
        normalized_items: list[dict[str, str]] = []
        for item in install_items:
            if not isinstance(item, dict):
                raise ValueError("operator upgrade host runner pin upgrade item must be a JSON object")
            command = _pin_upgrade_command(Path("/tmp/component-upgrade-placeholder"), item)
            normalized_items.append(
                {
                    "component": command[1],
                    "kind": _single_line(item.get("kind"), label="pin upgrade kind", allow_blank=False, max_chars=64),
                    "target": command[4],
                }
            )
        normalized["install_items"] = normalized_items
    return normalized


def _run_request(request_body: dict[str, Any], *, repo_dir: Path, priv_dir: Path) -> int:
    request = _validate_request(request_body, repo_dir=repo_dir, priv_dir=priv_dir)
    deploy = _require_repo_script(repo_dir, "deploy.sh")
    component_upgrade = _require_repo_script(repo_dir, "bin/component-upgrade.sh")
    env = _operator_env(request, repo_dir=repo_dir, priv_dir=priv_dir)
    timeout_seconds = int(request["timeout_seconds"])
    log_path = request["log_path"]
    assert isinstance(log_path, Path)
    with log_path.open("w", encoding="utf-8") as handle:
        handle.write("ArcLink host operator upgrade runner executing canonical host upgrade path.\n")
        handle.flush()
        if request["operation"] == "run_operator_upgrade":
            result = _run_logged_command(handle, [str(deploy), "upgrade"], cwd=repo_dir, env=env, timeout_seconds=timeout_seconds)
            return int(result.returncode)
        last_result: subprocess.CompletedProcess[str] | None = None
        install_items = request.get("install_items")
        if not isinstance(install_items, list):
            raise ValueError("operator upgrade host runner pin upgrade request has no install items")
        for item in install_items:
            if not isinstance(item, dict):
                raise ValueError("operator upgrade host runner pin upgrade item must be a JSON object")
            command = _pin_upgrade_command(component_upgrade, item)
            last_result = _run_logged_command(handle, command, cwd=repo_dir, env=env, timeout_seconds=timeout_seconds)
            if last_result.returncode != 0:
                return int(last_result.returncode)
        handle.flush()
        if not _pin_upgrade_log_requires_deploy(log_path, expected_statuses=len(install_items)):
            handle.write("All requested pinned components were already current; skipping deploy upgrade.\n")
            handle.flush()
            return int(last_result.returncode if last_result is not None else 0)
        last_result = _run_logged_command(handle, [str(deploy), "upgrade"], cwd=repo_dir, env=env, timeout_seconds=timeout_seconds)
        return int(last_result.returncode if last_result is not None else 0)


def _process_request_file(path: Path, *, repo_dir: Path, priv_dir: Path, queue_root: Path) -> None:
    stat_result = path.lstat()
    if stat.S_ISLNK(stat_result.st_mode) or not stat.S_ISREG(stat_result.st_mode):
        raise ValueError(f"operator upgrade host runner refusing non-regular request file {path}")
    request_body = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(request_body, dict):
        raise ValueError("operator upgrade host runner request must be a JSON object")
    request_id = _single_line(request_body.get("request_id"), label="request_id", allow_blank=False, max_chars=96)
    if not REQUEST_ID_RE.fullmatch(request_id):
        raise ValueError("operator upgrade host runner request id is invalid")
    result_path = queue_root / "results" / f"{request_id}.json"
    done_dir = queue_root / "processed"
    result: dict[str, Any]
    try:
        returncode = _run_request(request_body, repo_dir=repo_dir, priv_dir=priv_dir)
        result = {"ok": True, "request_id": request_id, "returncode": int(returncode), "completed_at": int(time.time())}
    except BaseException as exc:
        result = {
            "ok": False,
            "request_id": request_id,
            "error": str(exc),
            "error_class": exc.__class__.__name__,
            "completed_at": int(time.time()),
        }
    _atomic_write_json(result_path, result)
    done_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(path, done_dir / path.name)
    except OSError:
        path.unlink(missing_ok=True)


def process_once() -> int:
    repo_dir = _repo_dir()
    priv_dir = _priv_dir(repo_dir)
    queue_root = _queue_root(priv_dir)
    pending_dir = queue_root / "pending"
    lock_path = queue_root / "runner.lock"
    pending_dir.mkdir(parents=True, exist_ok=True)
    (queue_root / "results").mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as lock_handle:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        for request_path in sorted(pending_dir.glob("*.json"), key=lambda item: (item.stat().st_mtime, item.name)):
            _process_request_file(request_path, repo_dir=repo_dir, priv_dir=priv_dir, queue_root=queue_root)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Drain ArcLink host operator upgrade requests")
    parser.add_argument("--once", action="store_true", help="drain pending requests once and exit")
    args = parser.parse_args(argv)
    del args
    os.umask(0o077)
    return process_once()


if __name__ == "__main__":
    raise SystemExit(main())
