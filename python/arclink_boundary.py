#!/usr/bin/env python3
"""Shared boundary-safety utilities for ArcLink API and dashboard modules."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
from pathlib import Path
from typing import Any, Callable, Mapping

from arclink_secrets_regex import (
    contains_secret_material,
    path_requires_secret_ref,
    is_safe_secret_value,
)


DOCKER_TRUSTED_HOST_RISK_ENV = "ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED"
DOCKER_TRUSTED_HOST_RISK_ACCEPTED_VALUE = "accepted"
TRUSTED_DOCKER_BINARY_PATHS = (
    Path("/usr/bin/docker"),
    Path("/usr/local/bin/docker"),
    Path("/bin/docker"),
    Path("/snap/bin/docker"),
)


def json_loads_safe(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def reject_secret_material(
    value: Any,
    *,
    path: str = "$",
    label: str = "ArcLink boundary",
    error_cls: type[Exception] = ValueError,
) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            reject_secret_material(child, path=f"{path}.{key}", label=label, error_cls=error_cls)
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            reject_secret_material(child, path=f"{path}[{index}]", label=label, error_cls=error_cls)
        return
    if not isinstance(value, str):
        return
    text = value.strip()
    if not text:
        return
    if path_requires_secret_ref(path) and not is_safe_secret_value(text):
        raise error_cls(f"{label} cannot store plaintext secret material at {path}")
    if contains_secret_material(text):
        raise error_cls(f"{label} cannot store plaintext secret material at {path}")


def json_dumps_safe(
    value: Mapping[str, Any] | None,
    *,
    label: str = "ArcLink boundary",
    error_cls: type[Exception] = ValueError,
) -> str:
    payload = dict(value or {})
    reject_secret_material(payload, label=label, error_cls=error_cls)
    return json.dumps(payload, sort_keys=True)


def rowdict(row: sqlite3.Row | None) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def docker_trusted_host_risk_is_accepted(env: Mapping[str, str] | None = None) -> bool:
    values = env if env is not None else os.environ
    return str(values.get(DOCKER_TRUSTED_HOST_RISK_ENV) or "").strip() == DOCKER_TRUSTED_HOST_RISK_ACCEPTED_VALUE


def require_docker_trusted_host_risk_accepted(
    *,
    service: str,
    env: Mapping[str, str] | None = None,
    error_cls: type[Exception] = RuntimeError,
) -> None:
    if docker_trusted_host_risk_is_accepted(env):
        return
    raise error_cls(
        f"GAP-019 trusted-host residual risk is not accepted for {service}; "
        f"set {DOCKER_TRUSTED_HOST_RISK_ENV}={DOCKER_TRUSTED_HOST_RISK_ACCEPTED_VALUE} "
        "in private Docker config only after operator review."
    )


def _canonical_path(path: Path) -> Path:
    try:
        return path.resolve(strict=False)
    except (OSError, RuntimeError):
        return path


def require_trusted_docker_binary(
    configured: str | None,
    *,
    service: str,
    trusted_paths: tuple[Path, ...] = TRUSTED_DOCKER_BINARY_PATHS,
    which: Callable[[str], str | None] = shutil.which,
) -> str:
    clean = str(configured or "docker").strip() or "docker"
    if clean == "docker":
        resolved = which("docker")
        if not resolved:
            raise ValueError(f"{service} Docker CLI is not available")
        candidate = Path(resolved)
    else:
        candidate = Path(clean)
        if not candidate.is_absolute():
            raise ValueError(f"{service} Docker CLI must be 'docker' or an absolute docker path")
    if candidate.name != "docker":
        raise ValueError(f"{service} Docker CLI must point to the docker executable")
    if not candidate.is_absolute():
        raise ValueError(f"{service} Docker CLI must resolve to an absolute path")
    trusted = {_canonical_path(Path(path)) for path in trusted_paths}
    if _canonical_path(candidate) not in trusted and candidate not in trusted:
        raise ValueError(f"{service} Docker CLI path is not trusted")
    if not candidate.is_file() or not os.access(candidate, os.X_OK):
        raise ValueError(f"{service} Docker CLI is not executable")
    return str(candidate)
