#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from typing import Any, Mapping

from almanac_control import append_arclink_audit, utc_now_iso
from arclink_adapters import arclink_hostnames
from arclink_product import primary_provider


ARCLINK_ADMIN_ACTION_TYPES = frozenset(
    {
        "restart",
        "reprovision",
        "suspend",
        "unsuspend",
        "force_resynth",
        "rotate_bot_key",
        "rotate_chutes_key",
        "dns_repair",
        "refund",
        "comp",
        "cancel",
        "rollout",
    }
)
ARCLINK_ADMIN_TARGET_KINDS = frozenset({"deployment", "user", "subscription", "dns_record", "system"})
ARCLINK_ACTION_INTENT_STATUSES = frozenset({"queued", "running", "succeeded", "failed", "cancelled"})

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


class ArcLinkDashboardError(ValueError):
    pass


def _json_loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def _reject_secret_material(value: Any, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            _reject_secret_material(child, path=f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_secret_material(child, path=f"{path}[{index}]")
        return
    if not isinstance(value, str):
        return
    text = value.strip()
    if not text:
        return
    if _SECRET_KEY_RE.search(path) and not text.startswith("secret://"):
        raise ArcLinkDashboardError(f"ArcLink dashboard contract cannot store plaintext secret material at {path}")
    if _PLAINTEXT_SECRET_RE.search(text):
        raise ArcLinkDashboardError(f"ArcLink dashboard contract cannot store plaintext secret material at {path}")


def _safe_json(value: Mapping[str, Any] | None) -> str:
    payload = dict(value or {})
    _reject_secret_material(payload)
    return json.dumps(payload, sort_keys=True)


def _stable_action_id(idempotency_key: str) -> str:
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:24]
    return f"act_{digest}"


def _limit(value: int) -> int:
    return min(100, max(1, int(value or 25)))


def _rowdict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def _deployment_urls(prefix: str, base_domain: str) -> dict[str, str]:
    if not str(prefix or "").strip() or not str(base_domain or "").strip():
        return {}
    return {role: f"https://{host}" for role, host in arclink_hostnames(prefix, base_domain).items()}


def _service_health(conn: sqlite3.Connection, deployment_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT service_name, status, checked_at, detail_json
        FROM arclink_service_health
        WHERE deployment_id = ?
        ORDER BY service_name
        """,
        (deployment_id,),
    ).fetchall()
    return [
        {
            "service_name": str(row["service_name"] or ""),
            "status": str(row["status"] or ""),
            "checked_at": str(row["checked_at"] or ""),
            "detail": _json_loads(str(row["detail_json"] or "{}")),
        }
        for row in rows
    ]


def _deployment_events(conn: sqlite3.Connection, deployment_id: str, *, limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT event_id, event_type, metadata_json, created_at
        FROM arclink_events
        WHERE subject_kind = 'deployment' AND subject_id = ?
        ORDER BY created_at DESC, event_id DESC
        LIMIT ?
        """,
        (deployment_id, _limit(limit)),
    ).fetchall()
    return [
        {
            "event_id": str(row["event_id"] or ""),
            "event_type": str(row["event_type"] or ""),
            "metadata": _json_loads(str(row["metadata_json"] or "{}")),
            "created_at": str(row["created_at"] or ""),
        }
        for row in rows
    ]


def _deployment_onboarding(conn: sqlite3.Connection, deployment_id: str) -> dict[str, Any]:
    session = conn.execute(
        """
        SELECT session_id, channel, channel_identity, status, checkout_state, selected_model_id, updated_at
        FROM arclink_onboarding_sessions
        WHERE deployment_id = ?
        ORDER BY updated_at DESC, created_at DESC
        LIMIT 1
        """,
        (deployment_id,),
    ).fetchone()
    if session is None:
        return {
            "session_id": "",
            "channel": "",
            "status": "",
            "checkout_state": "",
            "first_contacted": False,
            "handoff_recorded": False,
        }
    events = {
        str(row["event_type"] or "")
        for row in conn.execute(
            "SELECT event_type FROM arclink_onboarding_events WHERE session_id = ?",
            (str(session["session_id"] or ""),),
        ).fetchall()
    }
    return {
        "session_id": str(session["session_id"] or ""),
        "channel": str(session["channel"] or ""),
        "status": str(session["status"] or ""),
        "checkout_state": str(session["checkout_state"] or ""),
        "selected_model_id": str(session["selected_model_id"] or ""),
        "first_contacted": "first_agent_contact" in events or str(session["status"] or "") in {"first_contacted", "completed"},
        "handoff_recorded": "channel_handoff" in events,
        "updated_at": str(session["updated_at"] or ""),
    }


def read_arclink_user_dashboard(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    deployment_id: str = "",
    recent_limit: int = 10,
) -> dict[str, Any]:
    user = conn.execute("SELECT * FROM arclink_users WHERE user_id = ?", (user_id,)).fetchone()
    if user is None:
        raise KeyError(user_id)
    deployment_args: list[Any] = [user_id]
    deployment_filter = ""
    if deployment_id:
        deployment_filter = "AND deployment_id = ?"
        deployment_args.append(deployment_id)
    deployments = conn.execute(
        f"""
        SELECT *
        FROM arclink_deployments
        WHERE user_id = ? {deployment_filter}
        ORDER BY created_at DESC, deployment_id DESC
        """,
        tuple(deployment_args),
    ).fetchall()
    subscriptions = [
        _rowdict(row)
        for row in conn.execute(
            """
            SELECT subscription_id, stripe_customer_id, stripe_subscription_id, status, current_period_end, updated_at
            FROM arclink_subscriptions
            WHERE user_id = ?
            ORDER BY updated_at DESC, subscription_id DESC
            """,
            (user_id,),
        ).fetchall()
    ]
    deployment_cards: list[dict[str, Any]] = []
    for row in deployments:
        dep = dict(row)
        health = _service_health(conn, str(dep["deployment_id"]))
        onboarding = _deployment_onboarding(conn, str(dep["deployment_id"]))
        model_id = onboarding.get("selected_model_id") or _json_loads(str(dep.get("metadata_json") or "{}")).get("selected_model_id") or ""
        deployment_cards.append(
            {
                "deployment_id": str(dep["deployment_id"] or ""),
                "status": str(dep["status"] or ""),
                "prefix": str(dep["prefix"] or ""),
                "base_domain": str(dep["base_domain"] or ""),
                "access": {"urls": _deployment_urls(str(dep["prefix"] or ""), str(dep["base_domain"] or ""))},
                "billing": {
                    "entitlement_state": str(user["entitlement_state"] or "none"),
                    "entitlement_updated_at": str(user["entitlement_updated_at"] or ""),
                    "subscriptions": subscriptions,
                },
                "bot_contact": onboarding,
                "model": {
                    "provider": primary_provider({}),
                    "model_id": str(model_id or ""),
                    "credential_state": "secret_ref_pending",
                },
                "freshness": {
                    "qmd": next((item for item in health if item["service_name"] == "qmd-mcp"), {"status": "unknown", "checked_at": ""}),
                    "memory": next((item for item in health if item["service_name"] == "memory-synth"), {"status": "unknown", "checked_at": ""}),
                },
                "service_health": health,
                "recent_events": _deployment_events(conn, str(dep["deployment_id"]), limit=recent_limit),
            }
        )
    return {
        "user": {
            "user_id": str(user["user_id"] or ""),
            "email": str(user["email"] or ""),
            "display_name": str(user["display_name"] or ""),
            "status": str(user["status"] or ""),
        },
        "entitlement": {
            "state": str(user["entitlement_state"] or "none"),
            "updated_at": str(user["entitlement_updated_at"] or ""),
        },
        "deployments": deployment_cards,
    }


def _time_filter(column: str, since: str, args: list[Any]) -> str:
    clean = str(since or "").strip()
    if not clean:
        return ""
    args.append(clean)
    return f" AND {column} >= ?"


def read_arclink_admin_dashboard(
    conn: sqlite3.Connection,
    *,
    channel: str = "",
    status: str = "",
    deployment_id: str = "",
    user_id: str = "",
    since: str = "",
    recent_limit: int = 25,
) -> dict[str, Any]:
    limit = _limit(recent_limit)
    filters = {
        "channel": str(channel or "").strip().lower(),
        "status": str(status or "").strip().lower(),
        "deployment_id": str(deployment_id or "").strip(),
        "user_id": str(user_id or "").strip(),
        "since": str(since or "").strip(),
    }

    onboarding_args: list[Any] = []
    onboarding_where = "WHERE 1 = 1"
    if filters["channel"]:
        onboarding_where += " AND LOWER(channel) = LOWER(?)"
        onboarding_args.append(filters["channel"])
    if filters["status"]:
        onboarding_where += " AND status = ?"
        onboarding_args.append(filters["status"])
    onboarding_where += _time_filter("created_at", filters["since"], onboarding_args)
    session_counts = [
        _rowdict(row)
        for row in conn.execute(
            f"""
            SELECT channel, status, COUNT(*) AS count
            FROM arclink_onboarding_sessions
            {onboarding_where}
            GROUP BY channel, status
            ORDER BY channel, status
            """,
            tuple(onboarding_args),
        ).fetchall()
    ]

    event_args: list[Any] = []
    event_where = "WHERE 1 = 1"
    if filters["channel"]:
        event_where += " AND LOWER(channel) = LOWER(?)"
        event_args.append(filters["channel"])
    event_where += _time_filter("created_at", filters["since"], event_args)
    event_counts = [
        _rowdict(row)
        for row in conn.execute(
            f"""
            SELECT event_type, COUNT(*) AS count
            FROM arclink_onboarding_events
            {event_where}
            GROUP BY event_type
            ORDER BY event_type
            """,
            tuple(event_args),
        ).fetchall()
    ]

    deployment_args: list[Any] = []
    deployment_where = "WHERE 1 = 1"
    if filters["deployment_id"]:
        deployment_where += " AND deployment_id = ?"
        deployment_args.append(filters["deployment_id"])
    if filters["user_id"]:
        deployment_where += " AND user_id = ?"
        deployment_args.append(filters["user_id"])
    if filters["status"]:
        deployment_where += " AND status = ?"
        deployment_args.append(filters["status"])
    deployment_where += _time_filter("created_at", filters["since"], deployment_args)

    deployments = [
        {
            "deployment_id": str(row["deployment_id"] or ""),
            "user_id": str(row["user_id"] or ""),
            "prefix": str(row["prefix"] or ""),
            "base_domain": str(row["base_domain"] or ""),
            "status": str(row["status"] or ""),
            "updated_at": str(row["updated_at"] or ""),
        }
        for row in conn.execute(
            f"""
            SELECT deployment_id, user_id, prefix, base_domain, status, updated_at, created_at
            FROM arclink_deployments
            {deployment_where}
            ORDER BY created_at DESC, deployment_id DESC
            LIMIT ?
            """,
            (*deployment_args, limit),
        ).fetchall()
    ]

    subscription_args: list[Any] = []
    subscription_where = "WHERE 1 = 1"
    if filters["user_id"]:
        subscription_where += " AND user_id = ?"
        subscription_args.append(filters["user_id"])
    if filters["status"]:
        subscription_where += " AND status = ?"
        subscription_args.append(filters["status"])
    subscription_where += _time_filter("updated_at", filters["since"], subscription_args)
    subscriptions = [
        _rowdict(row)
        for row in conn.execute(
            f"""
            SELECT subscription_id, user_id, stripe_customer_id, stripe_subscription_id, status, current_period_end, updated_at
            FROM arclink_subscriptions
            {subscription_where}
            ORDER BY updated_at DESC, subscription_id DESC
            LIMIT ?
            """,
            (*subscription_args, limit),
        ).fetchall()
    ]

    health_args: list[Any] = []
    health_where = "WHERE 1 = 1"
    if filters["deployment_id"]:
        health_where += " AND h.deployment_id = ?"
        health_args.append(filters["deployment_id"])
    if filters["user_id"]:
        health_where += " AND d.user_id = ?"
        health_args.append(filters["user_id"])
    if filters["status"]:
        health_where += " AND h.status = ?"
        health_args.append(filters["status"])
    health_where += _time_filter("h.checked_at", filters["since"], health_args)
    service_health = [
        {
            "deployment_id": str(row["deployment_id"] or ""),
            "service_name": str(row["service_name"] or ""),
            "status": str(row["status"] or ""),
            "checked_at": str(row["checked_at"] or ""),
        }
        for row in conn.execute(
            f"""
            SELECT h.deployment_id, h.service_name, h.status, h.checked_at
            FROM arclink_service_health h
            LEFT JOIN arclink_deployments d ON d.deployment_id = h.deployment_id
            {health_where}
            ORDER BY h.checked_at DESC, h.deployment_id, h.service_name
            LIMIT ?
            """,
            (*health_args, limit),
        ).fetchall()
    ]

    jobs_args: list[Any] = []
    jobs_where = "WHERE 1 = 1"
    if filters["deployment_id"]:
        jobs_where += " AND deployment_id = ?"
        jobs_args.append(filters["deployment_id"])
    if filters["status"]:
        jobs_where += " AND status = ?"
        jobs_args.append(filters["status"])
    jobs_where += _time_filter("requested_at", filters["since"], jobs_args)
    provisioning_jobs = [
        _rowdict(row)
        for row in conn.execute(
            f"""
            SELECT job_id, deployment_id, job_kind, status, attempt_count, requested_at, started_at, finished_at, error
            FROM arclink_provisioning_jobs
            {jobs_where}
            ORDER BY requested_at DESC, job_id DESC
            LIMIT ?
            """,
            (*jobs_args, limit),
        ).fetchall()
    ]

    dns_args: list[Any] = []
    dns_where = "WHERE event_type = 'dns_drift'"
    if filters["deployment_id"]:
        dns_where += " AND subject_id = ?"
        dns_args.append(filters["deployment_id"])
    dns_where += _time_filter("created_at", filters["since"], dns_args)
    dns_drift = [
        {
            "deployment_id": str(row["subject_id"] or ""),
            "metadata": _json_loads(str(row["metadata_json"] or "{}")),
            "created_at": str(row["created_at"] or ""),
        }
        for row in conn.execute(
            f"""
            SELECT subject_id, metadata_json, created_at
            FROM arclink_events
            {dns_where}
            ORDER BY created_at DESC, event_id DESC
            LIMIT ?
            """,
            (*dns_args, limit),
        ).fetchall()
    ]

    audit_args: list[Any] = []
    audit_where = "WHERE 1 = 1"
    if filters["deployment_id"]:
        audit_where += " AND target_id = ?"
        audit_args.append(filters["deployment_id"])
    audit_where += _time_filter("created_at", filters["since"], audit_args)
    audit_rows = [
        {
            "audit_id": str(row["audit_id"] or ""),
            "actor_id": str(row["actor_id"] or ""),
            "action": str(row["action"] or ""),
            "target_kind": str(row["target_kind"] or ""),
            "target_id": str(row["target_id"] or ""),
            "reason": str(row["reason"] or ""),
            "created_at": str(row["created_at"] or ""),
        }
        for row in conn.execute(
            f"""
            SELECT audit_id, actor_id, action, target_kind, target_id, reason, created_at
            FROM arclink_audit_log
            {audit_where}
            ORDER BY created_at DESC, audit_id DESC
            LIMIT ?
            """,
            (*audit_args, limit),
        ).fetchall()
    ]

    action_args: list[Any] = []
    action_where = "WHERE 1 = 1"
    if filters["deployment_id"]:
        action_where += " AND target_id = ?"
        action_args.append(filters["deployment_id"])
    if filters["status"]:
        action_where += " AND status = ?"
        action_args.append(filters["status"])
    action_where += _time_filter("created_at", filters["since"], action_args)
    action_intents = [
        {
            "action_id": str(row["action_id"] or ""),
            "admin_id": str(row["admin_id"] or ""),
            "action_type": str(row["action_type"] or ""),
            "target_kind": str(row["target_kind"] or ""),
            "target_id": str(row["target_id"] or ""),
            "status": str(row["status"] or ""),
            "reason": str(row["reason"] or ""),
            "audit_id": str(row["audit_id"] or ""),
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
        }
        for row in conn.execute(
            f"""
            SELECT action_id, admin_id, action_type, target_kind, target_id, status, reason, audit_id, created_at, updated_at
            FROM arclink_action_intents
            {action_where}
            ORDER BY created_at DESC, action_id DESC
            LIMIT ?
            """,
            (*action_args, limit),
        ).fetchall()
    ]

    failure_job_args: list[Any] = []
    failure_job_where = "WHERE status = 'failed'"
    if filters["deployment_id"]:
        failure_job_where += " AND deployment_id = ?"
        failure_job_args.append(filters["deployment_id"])
    failure_job_where += _time_filter("COALESCE(finished_at, requested_at)", filters["since"], failure_job_args)
    recent_failures = [
        {"kind": "provisioning_job", **_rowdict(row)}
        for row in conn.execute(
            f"""
            SELECT job_id, deployment_id, job_kind, status, error, finished_at AS occurred_at
            FROM arclink_provisioning_jobs
            {failure_job_where}
            ORDER BY COALESCE(finished_at, requested_at) DESC, job_id DESC
            LIMIT ?
            """,
            (*failure_job_args, limit),
        ).fetchall()
    ]
    failure_health_args: list[Any] = []
    failure_health_where = "WHERE h.status IN ('degraded', 'unhealthy', 'failed')"
    if filters["deployment_id"]:
        failure_health_where += " AND h.deployment_id = ?"
        failure_health_args.append(filters["deployment_id"])
    if filters["user_id"]:
        failure_health_where += " AND d.user_id = ?"
        failure_health_args.append(filters["user_id"])
    failure_health_where += _time_filter("h.checked_at", filters["since"], failure_health_args)
    recent_failures.extend(
        {
            "kind": "service_health",
            "deployment_id": str(row["deployment_id"] or ""),
            "service_name": str(row["service_name"] or ""),
            "status": str(row["status"] or ""),
            "occurred_at": str(row["checked_at"] or ""),
        }
        for row in conn.execute(
            f"""
            SELECT h.deployment_id, h.service_name, h.status, h.checked_at
            FROM arclink_service_health h
            LEFT JOIN arclink_deployments d ON d.deployment_id = h.deployment_id
            {failure_health_where}
            ORDER BY h.checked_at DESC, h.deployment_id, h.service_name
            LIMIT ?
            """,
            (*failure_health_args, limit),
        ).fetchall()
    )

    return {
        "filters": filters,
        "onboarding_funnel": {"sessions": session_counts, "events": event_counts},
        "subscriptions": subscriptions,
        "deployments": deployments,
        "service_health": service_health,
        "dns_drift": dns_drift,
        "provisioning_jobs": provisioning_jobs,
        "action_intents": action_intents,
        "audit_rows": audit_rows,
        "recent_failures": recent_failures[:limit],
    }


def queue_arclink_admin_action(
    conn: sqlite3.Connection,
    *,
    admin_id: str,
    action_type: str,
    target_kind: str,
    target_id: str,
    reason: str,
    idempotency_key: str,
    metadata: Mapping[str, Any] | None = None,
    action_id: str = "",
) -> dict[str, Any]:
    clean_admin = str(admin_id or "").strip()
    clean_action = str(action_type or "").strip().lower()
    clean_target_kind = str(target_kind or "").strip().lower()
    clean_target_id = str(target_id or "").strip()
    clean_reason = str(reason or "").strip()
    clean_key = str(idempotency_key or "").strip()
    if not clean_admin:
        raise ArcLinkDashboardError("ArcLink admin actions require an admin id")
    if clean_action not in ARCLINK_ADMIN_ACTION_TYPES:
        raise ArcLinkDashboardError(f"unsupported ArcLink admin action type: {clean_action or 'blank'}")
    if clean_target_kind not in ARCLINK_ADMIN_TARGET_KINDS or not clean_target_id:
        raise ArcLinkDashboardError("ArcLink admin actions require a supported target")
    if not clean_reason:
        raise ArcLinkDashboardError("ArcLink admin actions require a reason")
    if not clean_key:
        raise ArcLinkDashboardError("ArcLink admin actions require an idempotency key")
    metadata_json = _safe_json(metadata)

    existing = conn.execute(
        "SELECT * FROM arclink_action_intents WHERE idempotency_key = ?",
        (clean_key,),
    ).fetchone()
    if existing is not None:
        row = dict(existing)
        if (
            row["admin_id"] != clean_admin
            or row["action_type"] != clean_action
            or row["target_kind"] != clean_target_kind
            or row["target_id"] != clean_target_id
        ):
            raise ArcLinkDashboardError("ArcLink admin action idempotency key is already bound to another request")
        return row

    clean_action_id = action_id.strip() if action_id else _stable_action_id(clean_key)
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO arclink_action_intents (
          action_id, admin_id, action_type, target_kind, target_id, status,
          idempotency_key, reason, metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?)
        """,
        (
            clean_action_id,
            clean_admin,
            clean_action,
            clean_target_kind,
            clean_target_id,
            clean_key,
            clean_reason,
            metadata_json,
            now,
            now,
        ),
    )
    audit_id = append_arclink_audit(
        conn,
        action=f"admin_action:{clean_action}",
        actor_id=clean_admin,
        target_kind=clean_target_kind,
        target_id=clean_target_id,
        reason=clean_reason,
        metadata={"action_id": clean_action_id, "idempotency_key": clean_key, "queued": True},
        commit=False,
    )
    conn.execute(
        "UPDATE arclink_action_intents SET audit_id = ? WHERE action_id = ?",
        (audit_id, clean_action_id),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM arclink_action_intents WHERE action_id = ?", (clean_action_id,)).fetchone())
