#!/usr/bin/env python3
"""Shared secret detection and redaction helpers for ArcLink boundaries."""
from __future__ import annotations

import re
from typing import Any, Iterable


REDACTION_TEXT = "[REDACTED]"

SECRET_REF_RE = re.compile(r"^secret://[A-Za-z0-9][A-Za-z0-9_.:/-]*$")
RUN_SECRET_RE = re.compile(r"^/run/secrets/[A-Za-z0-9][A-Za-z0-9_.-]*$")
COMPOSE_SECRET_SOURCE_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")

URL_CREDENTIAL_RE = re.compile(r"(?i)((?:https?|ssh)://[^/\s:@]+:)([^@\s/]+)(@)")
KEY_VALUE_SECRET_RE = re.compile(
    r"(?i)(\b[A-Za-z0-9_-]*(?:token|api[_-]?key|password|passwd|secret|credential|authorization|cookie|jwt|oauth)[A-Za-z0-9_-]*\b"
    r"\s*[:=]\s*)([^\s'\";,]+)"
)
PEM_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.DOTALL,
)
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
PLAINTEXT_SECRET_RE = re.compile(
    r"(?i)("
    r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b|"  # OpenAI
    r"\bsk-ant-[A-Za-z0-9_-]{20,}\b|"  # Anthropic
    r"\bAKIA[A-Z0-9]{16}\b|"  # AWS access key id
    r"\bASIA[A-Z0-9]{16}\b|"  # AWS temporary access key id
    r"\bcpk_(?:live|test)?[A-Za-z0-9_-]{8,}\b|"  # Chutes
    r"\b[MN][A-Za-z0-9_-]{22,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{20,}\b|"  # Discord bot token
    r"\bglpat-[A-Za-z0-9_-]{20,}\b|"  # GitLab PAT
    r"\bsk_(?:live|test)_[a-z0-9][a-z0-9_-]{8,}\b|"  # Stripe-like existing family
    r"\bwhsec_[a-z0-9][a-z0-9_-]{8,}\b|"
    r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b|"
    r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b|"
    r"\bntn_[A-Za-z0-9_-]{8,}\b|"
    r"\bcloudflare[a-z0-9_-]*token[a-z0-9_-]*\b|"
    r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b"  # Telegram bot token
    r")"
)

_SECRET_REF_KEY_RE = re.compile(
    r"(?i)(^secret_refs?$|(?:^|_)(?:secret|token|api_key|apikey|password|credential)(?:_|$)|client_secret|webhook_secret)"
)


def is_secret_ref(value: Any) -> bool:
    return bool(SECRET_REF_RE.fullmatch(str(value or "").strip()))


def is_run_secret_path(value: Any) -> bool:
    return bool(RUN_SECRET_RE.fullmatch(str(value or "").strip()))


def is_safe_secret_value(value: Any) -> bool:
    text = str(value or "").strip()
    return is_secret_ref(text) or is_run_secret_path(text)


def _path_segments(path: str) -> list[str]:
    text = str(path or "")
    if text.startswith("$."):
        text = text[2:]
    elif text == "$":
        return []
    elif text.startswith("$"):
        text = text[1:].lstrip(".")
    segments: list[str] = []
    for chunk in text.split("."):
        if not chunk:
            continue
        segment = re.sub(r"\[\d+\]", "", chunk).strip()
        if segment:
            segments.append(segment)
    return segments


def path_requires_secret_ref(path: str) -> bool:
    return any(_SECRET_REF_KEY_RE.search(segment) for segment in _path_segments(path))


def path_allows_compose_secret_source(path: str, value: Any) -> bool:
    segments = _path_segments(path)
    text = str(value or "").strip()
    return bool(
        segments
        and segments[-1] == "source"
        and any(segment in {"secrets", "secret_refs"} for segment in segments)
        and COMPOSE_SECRET_SOURCE_RE.fullmatch(text)
    )


def _secret_patterns() -> Iterable[re.Pattern[str]]:
    return (PEM_PRIVATE_KEY_RE, JWT_RE, PLAINTEXT_SECRET_RE, KEY_VALUE_SECRET_RE, URL_CREDENTIAL_RE)


def contains_secret_material(value: Any, *, allow_safe_refs: bool = True) -> bool:
    text = str(value or "")
    if allow_safe_refs and is_safe_secret_value(text):
        return False
    return any(pattern.search(text) for pattern in _secret_patterns())


def redact_secret_material(value: Any) -> str:
    text = str(value or "")
    text = URL_CREDENTIAL_RE.sub(r"\1" + REDACTION_TEXT + r"\3", text)
    text = PEM_PRIVATE_KEY_RE.sub(REDACTION_TEXT, text)
    text = JWT_RE.sub(REDACTION_TEXT, text)
    text = KEY_VALUE_SECRET_RE.sub(r"\1" + REDACTION_TEXT, text)
    text = PLAINTEXT_SECRET_RE.sub(REDACTION_TEXT, text)
    return text


def redact_then_truncate(value: Any, *, limit: int, tail: bool = False) -> str:
    redacted = redact_secret_material(value)
    if limit <= 0 or len(redacted) <= limit:
        return redacted
    return redacted[-limit:] if tail else redacted[:limit].rstrip()
