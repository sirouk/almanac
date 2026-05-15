#!/usr/bin/env python3
"""ArcLink Wrapped report generation.

Novelty score formula:

```
score = min(100, round(
    10 * unique_event_types
  + 8 * unique_audit_actions
  + 12 * unique_same_captain_comms_pairs
  + 6 * memory_card_count
  + 2 * hermes_turn_count
  + 3 * vault_change_count
  + 10 * completion_ratio
  + min(12, quiet_build_index * 4),
  2,
))
```

The formula intentionally rewards varied, cross-surface activity more than raw
volume. Inputs are scoped to one Captain and period, then redacted before any
rendered text or persisted ledger is returned.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import math
import os
import re
import secrets
import sqlite3
import sys
from typing import Any, Callable, Mapping, Sequence

from arclink_control import utc_now_iso
from arclink_evidence import redact_value
from arclink_secrets_regex import contains_secret_material, redact_secret_material


WRAPPED_FREQUENCIES = {"daily", "weekly", "monthly"}
WRAPPED_STATUSES = {"pending", "generated", "delivered", "failed"}
_TERMINAL_DEPLOYMENT_STATUSES = {"cancelled", "teardown_complete", "torn_down"}
_PERSISTENT_FAILURE_THRESHOLD = 3


SessionCounter = Callable[..., Mapping[str, Any]]
VaultDeltaReader = Callable[..., Mapping[str, Any]]


class ArcLinkWrappedError(ValueError):
    pass


def normalize_wrapped_frequency(value: str | None) -> str:
    clean = re.sub(r"\s+", " ", str(value or "").strip()).casefold()
    if not clean:
        return "daily"
    if clean not in WRAPPED_FREQUENCIES:
        raise ArcLinkWrappedError(f"unsupported ArcLink Wrapped frequency: {clean}")
    return clean


def normalize_wrapped_period(value: str | None) -> str:
    return normalize_wrapped_frequency(value)


def _parse_dt(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value or "").strip()
        if not text:
            raise ArcLinkWrappedError("ArcLink Wrapped timestamp is required")
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _month_start(dt: datetime) -> datetime:
    return datetime(dt.year, dt.month, 1, tzinfo=timezone.utc)


def resolve_wrapped_period(period: str, *, now: str | datetime | None = None) -> tuple[str, str]:
    clean = normalize_wrapped_period(period)
    current = _parse_dt(now or utc_now_iso())
    today = datetime(current.year, current.month, current.day, tzinfo=timezone.utc)
    if clean == "daily":
        end = today
        start = end - timedelta(days=1)
    elif clean == "weekly":
        end = today - timedelta(days=today.weekday())
        start = end - timedelta(days=7)
    else:
        end = _month_start(today)
        if end.month == 1:
            start = datetime(end.year - 1, 12, 1, tzinfo=timezone.utc)
        else:
            start = datetime(end.year, end.month - 1, 1, tzinfo=timezone.utc)
    return _iso(start), _iso(end)


def _json_loads(value: str | None, default: Any) -> Any:
    try:
        return json.loads(str(value or ""))
    except (TypeError, json.JSONDecodeError):
        return default


def _json_dumps(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), sort_keys=True)


def _report_id() -> str:
    return f"wrap_{secrets.token_hex(12)}"


def _failure_report_id(user_id: str, period: str, period_start: str, attempt: int) -> str:
    safe_user = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(user_id or "").strip())[:48] or "user"
    safe_start = re.sub(r"[^A-Za-z0-9]+", "", str(period_start or ""))[:24] or "period"
    return f"wrap_failed_{safe_user}_{period}_{safe_start}_{max(1, int(attempt))}"


def _redact_text(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    redacted = redact_secret_material(text)
    if redacted != text:
        return redacted
    if contains_secret_material(text, allow_safe_refs=False):
        return redact_value(text)
    return redacted


def _redact_any(value: Any) -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, child in value.items():
            if re.search(r"(?i)(token|secret|password|api[_-]?key|credential|authorization|cookie|jwt|oauth)", str(key)):
                result[str(key)] = redact_value(str(child or ""))
            else:
                result[str(key)] = _redact_any(child)
        return result
    if isinstance(value, list):
        return [_redact_any(child) for child in value]
    if isinstance(value, tuple):
        return [_redact_any(child) for child in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _user_row(conn: sqlite3.Connection, user_id: str) -> dict[str, Any]:
    clean = str(user_id or "").strip()
    row = conn.execute("SELECT * FROM arclink_users WHERE user_id = ?", (clean,)).fetchone()
    if row is None:
        raise KeyError(clean)
    return dict(row)


def set_wrapped_frequency(
    conn: sqlite3.Connection,
    user_id: str,
    frequency: str,
    *,
    actor_id: str = "",
    reason: str = "",
    now: str | datetime | None = None,
) -> dict[str, Any]:
    """Set a Captain's Wrapped cadence, rejecting anything more frequent than daily."""
    clean_user_id = str(user_id or "").strip()
    clean_frequency = normalize_wrapped_frequency(frequency)
    _user_row(conn, clean_user_id)
    changed_at = _iso(_parse_dt(now or utc_now_iso()))
    conn.execute(
        """
        UPDATE arclink_users
        SET wrapped_frequency = ?, updated_at = ?
        WHERE user_id = ?
        """,
        (clean_frequency, changed_at, clean_user_id),
    )
    conn.execute(
        """
        INSERT INTO arclink_audit_log (
          audit_id, actor_id, action, target_kind, target_id, reason, metadata_json, created_at
        ) VALUES (?, ?, 'wrapped_frequency_updated', 'user', ?, ?, ?, ?)
        """,
        (
            f"aud_wrapped_{secrets.token_hex(10)}",
            str(actor_id or clean_user_id),
            clean_user_id,
            _redact_text(reason or "ArcLink Wrapped frequency updated"),
            _json_dumps({"wrapped_frequency": clean_frequency}),
            changed_at,
        ),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM arclink_users WHERE user_id = ?", (clean_user_id,)).fetchone())


def _deployment_rows(conn: sqlite3.Connection, user_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM arclink_deployments
        WHERE user_id = ?
        ORDER BY created_at ASC, deployment_id ASC
        """,
        (str(user_id or "").strip(),),
    ).fetchall()
    return [dict(row) for row in rows if str(row["status"]) not in _TERMINAL_DEPLOYMENT_STATUSES]


def _between_clause(column: str) -> str:
    return f"{column} >= ? AND {column} < ?"


def _event_rows(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    deployment_ids: Sequence[str],
    period_start: str,
    period_end: str,
) -> list[dict[str, Any]]:
    params: list[Any] = [period_start, period_end, "user", user_id]
    deployment_filter = ""
    if deployment_ids:
        placeholders = ",".join("?" for _ in deployment_ids)
        deployment_filter = f" OR (subject_kind = 'deployment' AND subject_id IN ({placeholders}))"
        params.extend(deployment_ids)
    rows = conn.execute(
        f"""
        SELECT event_id, subject_kind, subject_id, event_type, metadata_json, created_at
        FROM arclink_events
        WHERE {_between_clause("created_at")}
          AND ((subject_kind = ? AND subject_id = ?){deployment_filter})
        ORDER BY created_at ASC, event_id ASC
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def _audit_rows(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    deployment_ids: Sequence[str],
    period_start: str,
    period_end: str,
) -> list[dict[str, Any]]:
    params: list[Any] = [period_start, period_end, "user", user_id]
    deployment_filter = ""
    if deployment_ids:
        placeholders = ",".join("?" for _ in deployment_ids)
        deployment_filter = f" OR (target_kind = 'deployment' AND target_id IN ({placeholders}))"
        params.extend(deployment_ids)
    rows = conn.execute(
        f"""
        SELECT audit_id, actor_id, action, target_kind, target_id, reason, metadata_json, created_at
        FROM arclink_audit_log
        WHERE {_between_clause("created_at")}
          AND ((target_kind = ? AND target_id = ?){deployment_filter})
        ORDER BY created_at ASC, audit_id ASC
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def _message_rows(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    period_start: str,
    period_end: str,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""
        SELECT message_id, sender_deployment_id, recipient_deployment_id, body, status, created_at, delivered_at
        FROM arclink_pod_messages
        WHERE {_between_clause("created_at")}
          AND sender_user_id = ?
          AND recipient_user_id = ?
        ORDER BY created_at ASC, message_id ASC
        """,
        (period_start, period_end, user_id, user_id),
    ).fetchall()
    return [dict(row) for row in rows]


def _memory_rows(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    deployment_ids: Sequence[str],
    period_start: str,
    period_end: str,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""
        SELECT card_id, source_kind, source_key, source_title, status, card_json,
               card_text, source_count, token_estimate, created_at, updated_at
        FROM memory_synthesis_cards
        WHERE status = 'ok'
          AND {_between_clause("updated_at")}
        ORDER BY updated_at ASC, card_id ASC
        """,
        (period_start, period_end),
    ).fetchall()
    scoped: list[dict[str, Any]] = []
    deployment_set = set(deployment_ids)
    for row in rows:
        item = dict(row)
        parsed = _json_loads(str(item.get("card_json") or "{}"), {})
        source_key = str(item.get("source_key") or "")
        if isinstance(parsed, Mapping) and str(parsed.get("user_id") or parsed.get("captain_user_id") or "") == user_id:
            scoped.append(item)
            continue
        if isinstance(parsed, Mapping) and str(parsed.get("deployment_id") or "") in deployment_set:
            scoped.append(item)
            continue
        if deployment_set and any(deployment_id and deployment_id in source_key for deployment_id in deployment_set):
            scoped.append(item)
    return scoped


def _call_session_counter(
    session_counter: SessionCounter | None,
    *,
    user_id: str,
    deployment_ids: Sequence[str],
    period_start: str,
    period_end: str,
) -> dict[str, int]:
    if session_counter is None:
        return {"session_count": 0, "turn_count": 0}
    data = session_counter(
        user_id=user_id,
        deployment_ids=list(deployment_ids),
        period_start=period_start,
        period_end=period_end,
    )
    return {
        "session_count": max(0, int(data.get("session_count") or data.get("sessions") or 0)),
        "turn_count": max(0, int(data.get("turn_count") or data.get("turns") or 0)),
    }


def _call_vault_delta_reader(
    vault_delta_reader: VaultDeltaReader | None,
    *,
    user_id: str,
    deployment_ids: Sequence[str],
    period_start: str,
    period_end: str,
) -> dict[str, Any]:
    if vault_delta_reader is None:
        return {"files_added": 0, "files_updated": 0, "files_deleted": 0}
    data = dict(
        vault_delta_reader(
            user_id=user_id,
            deployment_ids=list(deployment_ids),
            period_start=period_start,
            period_end=period_end,
        )
        or {}
    )
    return _redact_any(data)


def _int_value(data: Mapping[str, Any], key: str) -> int:
    try:
        return max(0, int(data.get(key) or 0))
    except (TypeError, ValueError):
        return 0


def _unique_event_type_count(events: Sequence[Mapping[str, Any]]) -> int:
    return len({str(row.get("event_type") or "") for row in events if str(row.get("event_type") or "")})


def _audit_action_counts(audits: Sequence[Mapping[str, Any]]) -> Counter[str]:
    return Counter(str(row.get("action") or "") for row in audits if str(row.get("action") or ""))


def _same_captain_message_pairs(messages: Sequence[Mapping[str, Any]]) -> set[tuple[str, str]]:
    return {
        (str(row.get("sender_deployment_id") or ""), str(row.get("recipient_deployment_id") or ""))
        for row in messages
        if str(row.get("sender_deployment_id") or "") and str(row.get("recipient_deployment_id") or "")
    }


def _delivered_message_count(messages: Sequence[Mapping[str, Any]]) -> int:
    return sum(1 for row in messages if str(row.get("status") or "") == "delivered")


def _completion_ratio(messages: Sequence[Mapping[str, Any]]) -> float:
    return _delivered_message_count(messages) / max(1, len(messages))


def _vault_change_count(vault_deltas: Mapping[str, Any]) -> int:
    return sum(_int_value(vault_deltas, key) for key in ("files_added", "files_updated", "files_deleted"))


def _stat(key: str, label: str, value: Any, detail: str) -> dict[str, Any]:
    return {"key": key, "label": label, "value": value, "detail": detail}


def _stats_for_ledger(
    *,
    deployments: Sequence[Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
    audits: Sequence[Mapping[str, Any]],
    messages: Sequence[Mapping[str, Any]],
    memory_cards: Sequence[Mapping[str, Any]],
    session_counts: Mapping[str, int],
    vault_deltas: Mapping[str, Any],
) -> list[dict[str, Any]]:
    unique_event_types = _unique_event_type_count(events)
    action_counts = _audit_action_counts(audits)
    unique_actions = len(action_counts)
    pairs = _same_captain_message_pairs(messages)
    completion_ratio = round(_completion_ratio(messages), 3)
    vault_change_count = _vault_change_count(vault_deltas)
    pod_count = max(1, len(deployments))
    memory_density = round(len(memory_cards) / pod_count, 3)
    turn_count = int(session_counts.get("turn_count") or 0)
    session_count = int(session_counts.get("session_count") or 0)
    quiet_build_index = round((vault_change_count + len(memory_cards)) / max(1, len(messages) + turn_count), 3)
    action_entropy = 0.0
    if action_counts:
        total = sum(action_counts.values())
        action_entropy = round(
            -sum((count / total) * math.log2(count / total) for count in action_counts.values()),
            3,
        )
    return [
        _stat("signal_variety", "Signal variety", unique_event_types + unique_actions, "Unique event types plus audit actions in the period."),
        _stat("crew_cross_pollination", "Crew cross-pollination", len(pairs), "Distinct same-Captain Pod-to-Pod Comms paths."),
        _stat("delivery_followthrough", "Delivery follow-through", completion_ratio, "Share of same-Captain Comms that reached delivered state."),
        _stat("recall_density", "Recall density", memory_density, "Memory synthesis cards per active Pod."),
        _stat("vault_churn", "Vault churn", vault_change_count, "Vault reconciler file adds, updates, and deletes."),
        _stat("quiet_build_index", "Quiet build index", quiet_build_index, "Vault and memory movement compared with chat/session volume."),
        _stat("action_entropy", "Action entropy", action_entropy, "How varied the Captain's operational actions were."),
        _stat("hermes_turns_per_session", "Hermes turns per session", round(turn_count / max(1, session_count), 3), "Hermes turns divided by read-only session count."),
    ]


def _novelty_score(
    *,
    events: Sequence[Mapping[str, Any]],
    audits: Sequence[Mapping[str, Any]],
    messages: Sequence[Mapping[str, Any]],
    memory_cards: Sequence[Mapping[str, Any]],
    session_counts: Mapping[str, int],
    vault_deltas: Mapping[str, Any],
    stats: Sequence[Mapping[str, Any]],
) -> float:
    unique_event_types = _unique_event_type_count(events)
    unique_actions = len(_audit_action_counts(audits))
    pairs = _same_captain_message_pairs(messages)
    completion_ratio = _completion_ratio(messages)
    vault_change_count = _vault_change_count(vault_deltas)
    quiet_build = next((float(row["value"]) for row in stats if row.get("key") == "quiet_build_index"), 0.0)
    score = (
        10 * unique_event_types
        + 8 * unique_actions
        + 12 * len(pairs)
        + 6 * len(memory_cards)
        + 2 * int(session_counts.get("turn_count") or 0)
        + 3 * vault_change_count
        + 10 * completion_ratio
        + min(12, quiet_build * 4)
    )
    return round(min(100.0, score), 2)


def _render_report(
    *,
    user: Mapping[str, Any],
    period: str,
    period_start: str,
    period_end: str,
    stats: Sequence[Mapping[str, Any]],
    novelty_score: float,
    source_counts: Mapping[str, int],
) -> tuple[str, str]:
    captain = _redact_text(str(user.get("display_name") or user.get("email") or "Captain"))
    heading = f"ArcLink Wrapped for {captain}"
    lines = [
        heading,
        f"Period: {period} ({period_start} to {period_end})",
        f"Novelty score: {novelty_score}",
        "Highlights:",
    ]
    for item in stats[:8]:
        lines.append(f"- {item['label']}: {item['value']} - {item['detail']}")
    lines.append(
        "Sources: "
        + ", ".join(f"{key}={value}" for key, value in sorted(source_counts.items()))
    )
    plain = "\n".join(lines)
    md_lines = [
        f"# {heading}",
        "",
        f"**Period:** `{period}` from `{period_start}` to `{period_end}`",
        f"**Novelty score:** `{novelty_score}`",
        "",
        "## Highlights",
    ]
    for item in stats[:8]:
        md_lines.append(f"- **{item['label']}**: `{item['value']}` - {item['detail']}")
    md_lines.extend(
        [
            "",
            "## Source Counts",
            *[f"- `{key}`: `{value}`" for key, value in sorted(source_counts.items())],
        ]
    )
    return _redact_text(plain), _redact_text("\n".join(md_lines))


def generate_wrapped_report(
    conn: sqlite3.Connection,
    user_id: str,
    period: str,
    period_start: str,
    period_end: str,
    *,
    session_counter: SessionCounter | None = None,
    vault_delta_reader: VaultDeltaReader | None = None,
    report_id: str = "",
    created_at: str = "",
) -> dict[str, Any]:
    clean_user_id = str(user_id or "").strip()
    clean_period = normalize_wrapped_period(period)
    start = _iso(_parse_dt(period_start))
    end = _iso(_parse_dt(period_end))
    if start >= end:
        raise ArcLinkWrappedError("ArcLink Wrapped period_start must be before period_end")
    user = _user_row(conn, clean_user_id)
    deployments = _deployment_rows(conn, clean_user_id)
    deployment_ids = [str(row.get("deployment_id") or "") for row in deployments if str(row.get("deployment_id") or "")]
    events = _event_rows(conn, user_id=clean_user_id, deployment_ids=deployment_ids, period_start=start, period_end=end)
    audits = _audit_rows(conn, user_id=clean_user_id, deployment_ids=deployment_ids, period_start=start, period_end=end)
    messages = _message_rows(conn, user_id=clean_user_id, period_start=start, period_end=end)
    memory_cards = _memory_rows(conn, user_id=clean_user_id, deployment_ids=deployment_ids, period_start=start, period_end=end)
    session_counts = _call_session_counter(
        session_counter,
        user_id=clean_user_id,
        deployment_ids=deployment_ids,
        period_start=start,
        period_end=end,
    )
    vault_deltas = _call_vault_delta_reader(
        vault_delta_reader,
        user_id=clean_user_id,
        deployment_ids=deployment_ids,
        period_start=start,
        period_end=end,
    )
    stats = _stats_for_ledger(
        deployments=deployments,
        events=events,
        audits=audits,
        messages=messages,
        memory_cards=memory_cards,
        session_counts=session_counts,
        vault_deltas=vault_deltas,
    )
    novelty_score = _novelty_score(
        events=events,
        audits=audits,
        messages=messages,
        memory_cards=memory_cards,
        session_counts=session_counts,
        vault_deltas=vault_deltas,
        stats=stats,
    )
    source_counts = {
        "deployments": len(deployments),
        "events": len(events),
        "audits": len(audits),
        "pod_messages": len(messages),
        "memory_cards": len(memory_cards),
        "hermes_sessions": int(session_counts.get("session_count") or 0),
        "hermes_turns": int(session_counts.get("turn_count") or 0),
        "vault_changes": _vault_change_count(vault_deltas),
    }
    plain, markdown = _render_report(
        user=user,
        period=clean_period,
        period_start=start,
        period_end=end,
        stats=stats,
        novelty_score=novelty_score,
        source_counts=source_counts,
    )
    rid = str(report_id or _report_id()).strip()
    now = _iso(_parse_dt(created_at or utc_now_iso()))
    ledger = {
        "formula_version": "wrapped_novelty_v1",
        "period": clean_period,
        "period_start": start,
        "period_end": end,
        "source_counts": source_counts,
        "session_counts": dict(session_counts),
        "vault_deltas": vault_deltas,
        "stats": stats,
        "plain_text": plain,
        "markdown": markdown,
        "scoped_ledger": _redact_any(
            {
                "events": events,
                "audits": audits,
                "pod_messages": messages,
                "memory_cards": memory_cards,
            }
        ),
    }
    conn.execute(
        """
        INSERT INTO arclink_wrapped_reports (
          report_id, user_id, period, period_start, period_end, status,
          ledger_json, novelty_score, delivery_channel, created_at, delivered_at
        ) VALUES (?, ?, ?, ?, ?, 'generated', ?, ?, '', ?, '')
        """,
        (rid, clean_user_id, clean_period, start, end, _json_dumps(_redact_any(ledger)), novelty_score, now),
    )
    conn.commit()
    return {
        "report_id": rid,
        "user_id": clean_user_id,
        "period": clean_period,
        "period_start": start,
        "period_end": end,
        "status": "generated",
        "novelty_score": novelty_score,
        "stats": stats,
        "plain_text": plain,
        "markdown": markdown,
        "source_counts": source_counts,
        "created_at": now,
    }


def list_user_wrapped_reports(
    conn: sqlite3.Connection,
    user_id: str,
    *,
    limit: int = 20,
) -> dict[str, Any]:
    """Return Captain-visible Wrapped history with rendered text included."""
    user = _user_row(conn, str(user_id or "").strip())
    clean_limit = min(100, max(1, int(limit or 20)))
    rows = conn.execute(
        """
        SELECT report_id, period, period_start, period_end, status, ledger_json,
               novelty_score, delivery_channel, created_at, delivered_at
        FROM arclink_wrapped_reports
        WHERE user_id = ?
        ORDER BY created_at DESC, report_id DESC
        LIMIT ?
        """,
        (str(user["user_id"]), clean_limit),
    ).fetchall()
    reports: list[dict[str, Any]] = []
    for row in rows:
        ledger = _json_loads(str(row["ledger_json"] or "{}"), {})
        if not isinstance(ledger, Mapping):
            ledger = {}
        reports.append(
            {
                "report_id": str(row["report_id"] or ""),
                "period": str(row["period"] or ""),
                "period_start": str(row["period_start"] or ""),
                "period_end": str(row["period_end"] or ""),
                "status": str(row["status"] or ""),
                "novelty_score": float(row["novelty_score"] or 0),
                "delivery_channel": str(row["delivery_channel"] or ""),
                "created_at": str(row["created_at"] or ""),
                "delivered_at": str(row["delivered_at"] or ""),
                "formula_version": str(ledger.get("formula_version") or "wrapped_novelty_v1"),
                "stats": _redact_any(ledger.get("stats") if isinstance(ledger.get("stats"), list) else []),
                "source_counts": _redact_any(ledger.get("source_counts") if isinstance(ledger.get("source_counts"), Mapping) else {}),
                "plain_text": _redact_text(str(ledger.get("plain_text") or "")),
                "markdown": _redact_text(str(ledger.get("markdown") or "")),
            }
        )
    return {
        "wrapped_frequency": normalize_wrapped_frequency(str(user.get("wrapped_frequency") or "daily")),
        "reports": reports,
    }


def _parse_quiet_hours(value: str) -> tuple[int, int, int, int] | None:
    match = re.search(r"\b([01]\d|2[0-3]):([0-5]\d)\s*-\s*([01]\d|2[0-3]):([0-5]\d)\b", str(value or ""))
    if not match:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def next_attempt_after_quiet_hours(now: str | datetime | None = None, *, quiet_hours: str = "") -> str:
    """Return now, or the first supported local quiet-hours boundary after now."""
    current = _parse_dt(now or utc_now_iso())
    parsed = _parse_quiet_hours(quiet_hours or os.environ.get("ARCLINK_ORG_QUIET_HOURS", ""))
    if parsed is None:
        return _iso(current)
    start_hour, start_minute, end_hour, end_minute = parsed
    start = current.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
    end = current.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
    if (start_hour, start_minute) == (end_hour, end_minute):
        return _iso(current)
    if start < end:
        if start <= current < end:
            return _iso(end)
        return _iso(current)
    if current >= start:
        return _iso(end + timedelta(days=1))
    if current < end:
        return _iso(end)
    return _iso(current)


def _captain_delivery_channel(conn: sqlite3.Connection, user_id: str) -> dict[str, str]:
    row = conn.execute(
        """
        SELECT channel, channel_identity
        FROM arclink_onboarding_sessions
        WHERE user_id = ?
          AND channel IN ('telegram', 'discord')
          AND channel_identity != ''
          AND status IN ('paid', 'provisioning_ready', 'completed')
        ORDER BY completed_at DESC, updated_at DESC, created_at DESC, session_id DESC
        LIMIT 1
        """,
        (str(user_id or "").strip(),),
    ).fetchone()
    if row is None:
        return {"channel_kind": "user-agent", "target_id": str(user_id or "").strip()}
    return {"channel_kind": str(row["channel"]), "target_id": str(row["channel_identity"])}


def enqueue_wrapped_report_notification(
    conn: sqlite3.Connection,
    report_id: str,
    *,
    now: str | datetime | None = None,
    quiet_hours: str = "",
) -> int:
    row = conn.execute(
        """
        SELECT report_id, user_id, period, period_start, period_end, status,
               ledger_json, novelty_score, delivery_channel, created_at
        FROM arclink_wrapped_reports
        WHERE report_id = ?
        """,
        (str(report_id or "").strip(),),
    ).fetchone()
    if row is None:
        raise KeyError(str(report_id or "").strip())
    if str(row["status"]) not in {"generated", "delivered"}:
        raise ArcLinkWrappedError("only generated ArcLink Wrapped reports can be queued for delivery")
    ledger = _json_loads(str(row["ledger_json"] or "{}"), {})
    if not isinstance(ledger, Mapping):
        ledger = {}
    message = _redact_text(str(ledger.get("plain_text") or "ArcLink Wrapped is ready."))
    channel = _captain_delivery_channel(conn, str(row["user_id"]))
    created_at = _iso(_parse_dt(now or utc_now_iso()))
    next_attempt_at = next_attempt_after_quiet_hours(created_at, quiet_hours=quiet_hours)
    extra = {
        "report_id": str(row["report_id"]),
        "user_id": str(row["user_id"]),
        "period": str(row["period"]),
        "period_start": str(row["period_start"]),
        "period_end": str(row["period_end"]),
        "novelty_score": float(row["novelty_score"]),
        "render_kind": "plain_text",
    }
    cursor = conn.execute(
        """
        INSERT INTO notification_outbox (
          target_kind, target_id, channel_kind, message, extra_json, created_at,
          attempt_count, last_attempt_at, next_attempt_at, delivered_at, delivery_error
        ) VALUES ('captain-wrapped', ?, ?, ?, ?, ?, 0, NULL, ?, NULL, NULL)
        """,
        (
            channel["target_id"],
            channel["channel_kind"],
            message,
            _json_dumps(extra),
            created_at,
            next_attempt_at,
        ),
    )
    conn.execute(
        """
        UPDATE arclink_wrapped_reports
        SET delivery_channel = ?
        WHERE report_id = ?
        """,
        (channel["channel_kind"], str(row["report_id"])),
    )
    conn.commit()
    return int(cursor.lastrowid)


def _record_wrapped_failure(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    period: str,
    period_start: str,
    period_end: str,
    error: str,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    created_at = _iso(_parse_dt(now or utc_now_iso()))
    prior_failures = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM arclink_wrapped_reports
        WHERE user_id = ? AND period = ? AND period_start = ? AND period_end = ? AND status = 'failed'
        """,
        (user_id, period, period_start, period_end),
    ).fetchone()
    attempt = int(prior_failures["count"] or 0) + 1
    rid = _failure_report_id(user_id, period, period_start, attempt)
    ledger = {
        "formula_version": "wrapped_novelty_v1",
        "period": period,
        "period_start": period_start,
        "period_end": period_end,
        "error": _redact_text(str(error or "ArcLink Wrapped generation failed"))[:500],
        "failure_attempt": attempt,
    }
    conn.execute(
        """
        INSERT OR REPLACE INTO arclink_wrapped_reports (
          report_id, user_id, period, period_start, period_end, status,
          ledger_json, novelty_score, delivery_channel, created_at, delivered_at
        ) VALUES (?, ?, ?, ?, ?, 'failed', ?, 0, '', ?, '')
        """,
        (rid, user_id, period, period_start, period_end, _json_dumps(ledger), created_at),
    )
    if attempt >= _PERSISTENT_FAILURE_THRESHOLD:
        conn.execute(
            """
            INSERT INTO notification_outbox (
              target_kind, target_id, channel_kind, message, extra_json, created_at,
              attempt_count, last_attempt_at, next_attempt_at, delivered_at, delivery_error
            ) VALUES ('operator', 'operator', 'tui-only', ?, ?, ?, 0, NULL, ?, NULL, NULL)
            """,
            (
                f"ArcLink Wrapped generation is failing persistently for a Captain: user_id={user_id}, period={period}.",
                _json_dumps(
                    {
                        "kind": "wrapped_persistent_failure",
                        "user_id": user_id,
                        "period": period,
                        "period_start": period_start,
                        "period_end": period_end,
                        "failure_attempt": attempt,
                    }
                ),
                created_at,
                created_at,
            ),
        )
    conn.commit()
    return {"report_id": rid, "status": "failed", "failure_attempt": attempt}


def run_wrapped_scheduler_once(
    conn: sqlite3.Connection,
    *,
    now: str | datetime | None = None,
    limit: int = 25,
    quiet_hours: str = "",
    session_counter: SessionCounter | None = None,
    vault_delta_reader: VaultDeltaReader | None = None,
) -> dict[str, Any]:
    summary = {"due": 0, "generated": 0, "queued": 0, "failed": 0, "operator_notifications": 0}
    due = list_due_wrapped_captains(conn, now=now)[: max(1, int(limit))]
    summary["due"] = len(due)
    before_operator = conn.execute(
        "SELECT COUNT(*) AS count FROM notification_outbox WHERE target_kind = 'operator'"
    ).fetchone()["count"]
    for item in due:
        try:
            report = generate_wrapped_report(
                conn,
                item["user_id"],
                item["frequency"],
                item["period_start"],
                item["period_end"],
                session_counter=session_counter,
                vault_delta_reader=vault_delta_reader,
                created_at=_iso(_parse_dt(now or utc_now_iso())),
            )
            summary["generated"] += 1
            enqueue_wrapped_report_notification(conn, report["report_id"], now=now, quiet_hours=quiet_hours)
            summary["queued"] += 1
        except Exception as exc:  # noqa: BLE001
            summary["failed"] += 1
            _record_wrapped_failure(
                conn,
                user_id=str(item["user_id"]),
                period=str(item["frequency"]),
                period_start=str(item["period_start"]),
                period_end=str(item["period_end"]),
                error=str(exc),
                now=now,
            )
    after_operator = conn.execute(
        "SELECT COUNT(*) AS count FROM notification_outbox WHERE target_kind = 'operator'"
    ).fetchone()["count"]
    summary["operator_notifications"] = max(0, int(after_operator or 0) - int(before_operator or 0))
    return summary


def list_due_wrapped_captains(conn: sqlite3.Connection, *, now: str | datetime | None = None) -> list[dict[str, Any]]:
    due: list[dict[str, Any]] = []
    rows = conn.execute(
        """
        SELECT user_id, wrapped_frequency
        FROM arclink_users
        WHERE status = 'active'
        ORDER BY user_id ASC
        """
    ).fetchall()
    for row in rows:
        frequency = normalize_wrapped_frequency(str(row["wrapped_frequency"] or "daily"))
        period_start, period_end = resolve_wrapped_period(frequency, now=now)
        latest = conn.execute(
            """
            SELECT status, novelty_score, created_at
            FROM arclink_wrapped_reports
            WHERE user_id = ? AND period = ? AND period_start = ? AND period_end = ?
            ORDER BY created_at DESC, report_id DESC
            LIMIT 1
            """,
            (row["user_id"], frequency, period_start, period_end),
        ).fetchone()
        if latest is None:
            reason = "missing"
        elif str(latest["status"]) == "failed":
            reason = "failed_retry"
        else:
            continue
        due.append(
            {
                "user_id": str(row["user_id"]),
                "frequency": frequency,
                "period_start": period_start,
                "period_end": period_end,
                "due_reason": reason,
            }
        )
    return due


def wrapped_admin_aggregate(conn: sqlite3.Connection, *, now: str | datetime | None = None) -> dict[str, Any]:
    status_rows = conn.execute(
        """
        SELECT status, COUNT(*) AS count
        FROM arclink_wrapped_reports
        GROUP BY status
        ORDER BY status
        """
    ).fetchall()
    latest = conn.execute(
        """
        SELECT user_id, period, period_start, period_end, status, novelty_score, created_at, delivered_at
        FROM arclink_wrapped_reports
        ORDER BY created_at DESC, report_id DESC
        LIMIT 10
        """
    ).fetchall()
    scores = [
        float(row["novelty_score"])
        for row in conn.execute("SELECT novelty_score FROM arclink_wrapped_reports WHERE status IN ('generated', 'delivered')")
    ]
    due = list_due_wrapped_captains(conn, now=now)
    return {
        "reports_by_status": {str(row["status"]): int(row["count"]) for row in status_rows},
        "latest": [
            {
                "user_id": str(row["user_id"]),
                "period": str(row["period"]),
                "period_start": str(row["period_start"]),
                "period_end": str(row["period_end"]),
                "status": str(row["status"]),
                "novelty_score": float(row["novelty_score"]),
                "created_at": str(row["created_at"]),
                "delivered_at": str(row["delivered_at"] or ""),
            }
            for row in latest
        ],
        "average_novelty_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
        "due_count": len(due),
        "failed_count": int(dict((str(row["status"]), int(row["count"])) for row in status_rows).get("failed", 0)),
    }


def main() -> int:
    import argparse

    from arclink_control import Config, connect_db

    parser = argparse.ArgumentParser(description="Generate and queue due ArcLink Wrapped reports.")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    cfg = Config.from_env()
    with connect_db(cfg) as conn:
        summary = run_wrapped_scheduler_once(conn, limit=args.limit)
    if args.json:
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(f"ArcLink Wrapped: {summary}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
