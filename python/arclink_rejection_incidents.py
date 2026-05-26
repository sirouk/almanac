"""Small helpers for redacted broker/helper rejection incident logs."""
from __future__ import annotations

import json
import os
import re
import stat
import time
from pathlib import Path
from typing import Any

from arclink_boundary import docker_trusted_host_risk_is_accepted


SAFE_METADATA_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")


def _safe_existing_base(raw: Any) -> Path | None:
    clean = str(raw or "").strip()
    if not clean:
        return None
    path = Path(clean)
    if not path.is_absolute() or str(path) == "/":
        return None
    try:
        if path.resolve(strict=False) != path:
            return None
        stat_result = path.lstat()
        if stat.S_ISLNK(stat_result.st_mode) or not stat.S_ISDIR(stat_result.st_mode):
            return None
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if resolved != path:
        return None
    return path


def _safe_child_path(base: Path, *parts: str) -> Path | None:
    if any(not part or "/" in part or part in {".", ".."} for part in parts):
        return None
    try:
        current = base
        expected = base.resolve(strict=True)
        for part in parts[:-1]:
            current = current / part
            expected = expected / part
            if current.exists():
                stat_result = current.lstat()
                if stat.S_ISLNK(stat_result.st_mode) or not stat.S_ISDIR(stat_result.st_mode):
                    return None
            else:
                current.mkdir(mode=0o700)
                stat_result = current.lstat()
                if stat.S_ISLNK(stat_result.st_mode) or not stat.S_ISDIR(stat_result.st_mode):
                    return None
            if current.resolve(strict=False) != expected:
                return None
        path = current / parts[-1]
        expected_path = expected / parts[-1]
        if path.resolve(strict=False) != expected_path:
            return None
        if path.exists():
            stat_result = path.lstat()
            if stat.S_ISLNK(stat_result.st_mode) or not stat.S_ISREG(stat_result.st_mode):
                return None
        return path
    except (OSError, RuntimeError):
        return None


def state_root_rejection_path(service: str, *, helper: bool = False) -> Path | None:
    base = _safe_existing_base(os.environ.get("ARCLINK_STATE_ROOT_BASE"))
    if base is None:
        return None
    family = "_helper-incidents" if helper else "_broker-incidents"
    return _safe_child_path(base, family, service, "rejections.jsonl")


def private_state_rejection_path(
    service: str,
    *,
    env_name: str = "ARCLINK_DOCKER_CONTAINER_PRIV_DIR",
    env_names: tuple[str, ...] | None = None,
) -> Path | None:
    names = env_names or (env_name,)
    bases: list[Path] = []
    for name in names:
        raw = str(os.environ.get(name) or "").strip()
        if not raw:
            continue
        item = _safe_existing_base(raw)
        if item is None:
            return None
        bases.append(item)
    if not bases:
        return None
    base = bases[0]
    if any(other != base for other in bases[1:]):
        return None
    return _safe_child_path(base, "state", "docker", service, "rejections.jsonl")


def agent_home_root_rejection_path(service: str) -> Path | None:
    base = _safe_existing_base(os.environ.get("ARCLINK_DOCKER_AGENT_HOME_ROOT"))
    if base is None:
        return None
    return _safe_child_path(base, ".helper-incidents", service, "rejections.jsonl")


def safe_metadata(fields: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in fields.items():
        if not isinstance(key, str) or not SAFE_METADATA_RE.fullmatch(key):
            continue
        if isinstance(value, bool):
            safe[key] = value
            continue
        if isinstance(value, int) and not isinstance(value, bool):
            safe[key] = value
            continue
        clean = str(value or "").strip()
        if SAFE_METADATA_RE.fullmatch(clean):
            safe[key] = clean
    return safe


def record_rejection_incident(
    path: Path | None,
    *,
    service: str,
    event: str,
    reason: str,
    message: str,
    error_class: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    if path is None:
        return
    row: dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "service": service,
        "event": event,
        "trusted_host_acknowledged": docker_trusted_host_risk_is_accepted(),
        "error_class": error_class,
        "reason": reason,
        "message": message,
    }
    if metadata:
        row.update(safe_metadata(metadata))
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(str(path), flags, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    except OSError:
        return
