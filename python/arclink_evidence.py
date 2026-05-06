#!/usr/bin/env python3
"""ArcLink deployment evidence ledger - Gap E scaffolding.

Deterministic, secret-redacted evidence records for live journey steps.
Each record captures step name, status, timestamps, commit hash,
URLs/hostnames, health summaries, and redacted provider identifiers.

Evidence can be serialized to JSON for audit trails and reporting.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

_SECRET_PATTERNS = (
    re.compile(r"(sk_(?:live|test)_)[A-Za-z0-9_]+"),         # Stripe secret keys
    re.compile(r"(whsec_)[A-Za-z0-9_]+"),                    # Stripe webhook secrets
    re.compile(r"(rk_(?:live|test)_)[A-Za-z0-9_]+"),         # Stripe restricted keys
    re.compile(r"([?&](?:api_?key|key|secret|token|password)=)[^&\s]+", re.I),
)

_SENSITIVE_KEY_PARTS = (
    "api_key",
    "auth",
    "bot_token",
    "password",
    "private_key",
    "secret",
    "token",
    "webhook",
)

_REDACT_ENV_KEYS = {
    "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
    "CLOUDFLARE_API_TOKEN", "CHUTES_API_KEY",
    "TELEGRAM_BOT_TOKEN", "DISCORD_BOT_TOKEN",
    "ARCLINK_WORKSPACE_PROOF_AUTH",
}


def redact_value(value: str, *, keep_prefix: int = 8) -> str:
    """Redact a secret value, keeping only a short prefix for identification."""
    if not value or len(value) <= keep_prefix:
        return "***"
    return value[:keep_prefix] + "***"


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def redact_text(value: str) -> str:
    """Redact known secret-looking substrings inside a larger string."""
    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(lambda match: match.group(1) + "***", redacted)
    return redacted


def redact_any(value: Any, *, key: str = "", sensitive_keys: set[str] | None = None) -> Any:
    keys = sensitive_keys or _REDACT_ENV_KEYS
    if isinstance(value, dict):
        return redact_dict(value, keys)
    if isinstance(value, list):
        return [redact_any(item, key=key, sensitive_keys=keys) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_any(item, key=key, sensitive_keys=keys) for item in value)
    if isinstance(value, str):
        if key in keys or _is_sensitive_key(key):
            return redact_value(value)
        return redact_text(value)
    return value


def redact_dict(d: dict[str, Any], sensitive_keys: set[str] | None = None) -> dict[str, Any]:
    """Return a copy of d with sensitive values and token-like substrings redacted."""
    keys = sensitive_keys or _REDACT_ENV_KEYS
    result = {}
    for k, v in d.items():
        result[k] = redact_any(v, key=k, sensitive_keys=keys)
    return result


# ---------------------------------------------------------------------------
# Evidence record
# ---------------------------------------------------------------------------

@dataclass
class EvidenceRecord:
    """One evidence entry for a journey step."""
    step_name: str
    status: str                      # passed | failed | skipped
    timestamp: float = 0.0
    commit_hash: str = ""
    hostname: str = ""
    url: str = ""
    health_summary: str = ""
    provider_id: str = ""            # redacted provider identifier
    detail: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["provider_id"] = redact_any(data.get("provider_id", ""), key="provider_id")
        data["url"] = redact_any(data.get("url", ""), key="url")
        data["health_summary"] = redact_any(data.get("health_summary", ""), key="health_summary")
        data["detail"] = redact_dict(dict(data.get("detail") or {}))
        data["error"] = redact_any(data.get("error", ""), key="error")
        return data


@dataclass
class EvidenceLedger:
    """Ordered collection of evidence records."""
    run_id: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0
    commit_hash: str = ""
    records: list[EvidenceRecord] = field(default_factory=list)

    def add(self, record: EvidenceRecord) -> None:
        self.records.append(record)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "commit_hash": self.commit_hash,
            "records": [record.to_dict() for record in self.records],
        }
        d["duration_ms"] = self.duration_ms
        return d

    @property
    def duration_ms(self) -> float:
        if self.started_at and self.finished_at:
            return round((self.finished_at - self.started_at) * 1000, 1)
        return 0.0

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @property
    def all_passed(self) -> bool:
        return all(r.status == "passed" for r in self.records)

    @property
    def summary(self) -> dict[str, int]:
        by_status: dict[str, int] = {}
        for r in self.records:
            by_status[r.status] = by_status.get(r.status, 0) + 1
        return by_status


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_commit_hash() -> str:
    """Return current git HEAD short hash, or empty string if unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def generate_run_id(*, prefix: str = "run", commit: str = "", ts: float = 0.0) -> str:
    """Generate a deterministic run ID from prefix, commit, and timestamp."""
    ts = ts or time.time()
    raw = f"{prefix}-{commit}-{ts}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"{prefix}_{digest}"


def record_from_step(step: Any, *, commit_hash: str = "") -> EvidenceRecord:
    """Create an EvidenceRecord from a JourneyStep (or compatible dict)."""
    if hasattr(step, "to_dict"):
        d = step.to_dict()
    elif isinstance(step, dict):
        d = step
    else:
        d = {}
    detail = redact_dict(dict(d.get("evidence", {}) or {}))
    if d.get("skip_reason"):
        detail["skip_reason"] = d.get("skip_reason", "")
    return EvidenceRecord(
        step_name=d.get("name", ""),
        status=d.get("status", ""),
        timestamp=d.get("finished_at", 0.0) or d.get("started_at", 0.0) or 0.0,
        commit_hash=commit_hash,
        detail=detail,
        error=d.get("error", ""),
    )


def ledger_from_journey(
    steps: list[Any],
    *,
    run_id: str = "",
    commit_hash: str = "",
) -> EvidenceLedger:
    """Build an EvidenceLedger from a list of evaluated JourneySteps."""
    commit = commit_hash or get_commit_hash()
    ledger = EvidenceLedger(
        run_id=run_id or generate_run_id(commit=commit),
        commit_hash=commit,
    )
    for step in steps:
        ledger.add(record_from_step(step, commit_hash=commit))
    if steps:
        first = steps[0]
        last = steps[-1]
        sa = first.started_at if hasattr(first, "started_at") else (first.get("started_at", 0) if isinstance(first, dict) else 0)
        fa = last.finished_at if hasattr(last, "finished_at") else (last.get("finished_at", 0) if isinstance(last, dict) else 0)
        ledger.started_at = sa
        ledger.finished_at = fa
    return ledger
