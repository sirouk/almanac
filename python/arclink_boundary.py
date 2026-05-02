#!/usr/bin/env python3
"""Shared boundary-safety utilities for ArcLink API and dashboard modules."""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any, Mapping

_SECRET_KEY_RE = re.compile(r"(secret|token|api[_-]?key|password|credential|webhook|client[_-]?secret)", re.I)
_PLAINTEXT_SECRET_RE = re.compile(
    r"(?i)("
    r"sk_(live|test)_[a-z0-9]|"
    r"whsec_[a-z0-9]|"
    r"gh[pousr]_[a-z0-9]|"
    r"xox[baprs]-|"
    r"ntn_[a-z0-9]|"
    r"cloudflare[a-z0-9_-]*token|"
    r"\b\d{6,}:[a-z0-9_-]{20,}\b"
    r")"
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
    if _SECRET_KEY_RE.search(path) and not text.startswith("secret://"):
        raise error_cls(f"{label} cannot store plaintext secret material at {path}")
    if _PLAINTEXT_SECRET_RE.search(text):
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
