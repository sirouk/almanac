#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
import sqlite3
from typing import Any, Mapping

from arclink_control import append_arclink_audit, utc_now_iso
from arclink_adapters import arclink_access_urls
from arclink_boundary import json_dumps_safe, json_loads_safe, reject_secret_material, rowdict
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
ARCLINK_USER_DASHBOARD_SECTIONS = (
    "deployment_health",
    "access_links",
    "bot_setup",
    "files",
    "code",
    "terminal",
    "hermes",
    "qmd_memory",
    "skills",
    "model",
    "billing",
    "security",
    "support",
)
ARCLINK_ADMIN_DASHBOARD_SECTIONS = (
    "onboarding_funnel",
    "users",
    "deployments",
    "payments",
    "infrastructure",
    "bots",
    "security_abuse",
    "releases_maintenance",
    "logs_events",
    "audit",
    "queued_actions",
)

class ArcLinkDashboardError(ValueError):
    pass


def build_operator_snapshot(
    *,
    env: dict[str, str] | None = None,
    skip_ports: bool = True,
    docker_binary: str = "docker",
) -> dict[str, Any]:
    """Build a read-only operator snapshot aggregating host readiness,
    provider diagnostics, live journey blockers, and evidence status.

    Never returns secret values - only credential names and presence.
    """
    from arclink_host_readiness import run_readiness
    from arclink_diagnostics import run_diagnostics
    from arclink_live_journey import build_journey

    readiness = run_readiness(env=env, skip_ports=skip_ports, docker_binary=docker_binary)
    diagnostics = run_diagnostics(env=env, docker_binary=docker_binary)

    env_source = env if env is not None else os.environ
    journey_steps = build_journey()
    journey_blockers: list[dict[str, Any]] = []
    for step in journey_steps:
        missing = [key for key in step.required_env if not str(env_source.get(key, "")).strip()]
        if missing:
            journey_blockers.append({"step": step.name, "missing_env": missing})

    all_journey_creds_present = len(journey_blockers) == 0

    return {
        "host_readiness": readiness.to_dict(),
        "provider_diagnostics": diagnostics.to_dict(),
        "live_journey": {
            "total_steps": len(journey_steps),
            "blocked_steps": len(journey_blockers),
            "all_credentials_present": all_journey_creds_present,
            "blockers": journey_blockers,
        },
        "evidence": {
            "template_ready": True,
            "credentialed_evidence": "missing" if not all_journey_creds_present else "pending_run",
            "live_proof": "blocked" if not all_journey_creds_present else "pending_credentialed_run",
        },
    }


def build_scale_operations_snapshot(
    conn: sqlite3.Connection,
    *,
    stale_action_threshold_seconds: int = 3600,
) -> dict[str, Any]:
    """Build operator-visible scale operations read model."""
    from arclink_fleet import fleet_capacity_summary, list_fleet_hosts
    from arclink_rollout import list_rollouts

    capacity = fleet_capacity_summary(conn)

    # Stale queued actions (queued for over threshold)
    from arclink_control import parse_utc_iso, utc_now
    now = utc_now()
    queued_rows = conn.execute(
        "SELECT * FROM arclink_action_intents WHERE status IN ('queued', 'running') ORDER BY created_at ASC",
    ).fetchall()
    stale_actions = []
    for row in queued_rows:
        created = parse_utc_iso(row["created_at"])
        if created is None:
            continue
        elapsed = (now - created).total_seconds()
        if elapsed >= stale_action_threshold_seconds:
            stale_actions.append({
                "action_id": str(row["action_id"]),
                "action_type": str(row["action_type"]),
                "status": str(row["status"]),
                "target": f"{row['target_kind']}:{row['target_id']}",
                "elapsed_seconds": int(elapsed),
            })

    # Recent action attempts
    recent_attempts = [
        {
            "attempt_id": str(r["attempt_id"]),
            "action_id": str(r["action_id"]),
            "status": str(r["status"]),
            "executor_adapter": str(r["executor_adapter"]),
            "error": str(r["error"] or ""),
            "started_at": str(r["started_at"]),
            "finished_at": str(r["finished_at"] or ""),
        }
        for r in conn.execute(
            "SELECT * FROM arclink_action_attempts ORDER BY started_at DESC LIMIT 20",
        ).fetchall()
    ]
    placements = [
        {
            "placement_id": str(r["placement_id"]),
            "deployment_id": str(r["deployment_id"]),
            "host_id": str(r["host_id"]),
            "status": str(r["status"]),
            "placed_at": str(r["placed_at"]),
            "removed_at": str(r["removed_at"] or ""),
        }
        for r in conn.execute(
            "SELECT * FROM arclink_deployment_placements ORDER BY placed_at DESC LIMIT 20",
        ).fetchall()
    ]

    # Active rollouts
    active_rollouts = [
        {
            "rollout_id": str(r["rollout_id"]),
            "deployment_id": str(r["deployment_id"]),
            "version_tag": str(r["version_tag"]),
            "status": str(r["status"]),
            "current_wave": int(r["current_wave"]),
            "wave_count": int(r["wave_count"]),
        }
        for r in conn.execute(
            "SELECT * FROM arclink_rollouts WHERE status IN ('planned', 'in_progress', 'paused') ORDER BY created_at DESC LIMIT 20",
        ).fetchall()
    ]

    return {
        "fleet_capacity": capacity,
        "placements": placements,
        "stale_actions": stale_actions,
        "recent_action_attempts": recent_attempts,
        "last_executor_result": recent_attempts[0] if recent_attempts else {},
        "active_rollouts": active_rollouts,
    }


def _json_loads(value: str | None) -> dict[str, Any]:
    return json_loads_safe(value)


def _reject_secret_material(value: Any, *, path: str = "$") -> None:
    reject_secret_material(value, path=path, label="ArcLink dashboard contract", error_cls=ArcLinkDashboardError)


def _safe_json(value: Mapping[str, Any] | None) -> str:
    return json_dumps_safe(value, label="ArcLink dashboard contract", error_cls=ArcLinkDashboardError)


def _stable_action_id(idempotency_key: str) -> str:
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:24]
    return f"act_{digest}"


def _limit(value: int) -> int:
    return min(100, max(1, int(value or 25)))


def _deployment_urls(prefix: str, base_domain: str, metadata: Mapping[str, Any] | None = None) -> dict[str, str]:
    if not str(prefix or "").strip() or not str(base_domain or "").strip():
        return {}
    meta = dict(metadata or {})
    publish_state = meta.get("tailnet_app_publication")
    tailnet_apps_unavailable = isinstance(publish_state, Mapping) and str(publish_state.get("status") or "") == "unavailable"
    stored_urls = meta.get("access_urls")
    if isinstance(stored_urls, Mapping):
        safe_urls = {
            str(role): str(url).strip()
            for role, url in stored_urls.items()
            if str(role).strip() and str(url).strip().startswith("https://")
        }
        if {"dashboard", "files", "code", "hermes"} <= set(safe_urls):
            return safe_urls
        if tailnet_apps_unavailable and safe_urls.get("dashboard"):
            limited = {"dashboard": safe_urls["dashboard"]}
            if safe_urls.get("notion"):
                limited["notion"] = safe_urls["notion"]
            return limited
    ingress_mode = str(meta.get("ingress_mode") or os.environ.get("ARCLINK_INGRESS_MODE") or "domain").strip().lower()
    tailscale_dns_name = str(
        meta.get("tailscale_dns_name") or os.environ.get("ARCLINK_TAILSCALE_DNS_NAME") or base_domain
    ).strip()
    tailscale_host_strategy = str(
        meta.get("tailscale_host_strategy")
        or os.environ.get("ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY")
        or "path"
    ).strip()
    if ingress_mode == "tailscale" and tailnet_apps_unavailable:
        host = tailscale_dns_name or base_domain
        return {
            "dashboard": f"https://{host}/u/{prefix}",
            "notion": f"https://{host}/u/{prefix}/notion/webhook",
        }
    tailnet_ports = meta.get("tailnet_service_ports") if isinstance(meta.get("tailnet_service_ports"), Mapping) else None
    return arclink_access_urls(
        prefix=prefix,
        base_domain=base_domain,
        ingress_mode=ingress_mode,
        tailscale_dns_name=tailscale_dns_name,
        tailscale_host_strategy=tailscale_host_strategy,
        tailnet_service_ports=tailnet_ports,
    )


def _count(conn: sqlite3.Connection, sql: str, args: tuple[Any, ...] = ()) -> int:
    row = conn.execute(sql, args).fetchone()
    return int(row[0] if row is not None else 0)


def _health_status(health: list[dict[str, Any]]) -> str:
    statuses = {str(item.get("status") or "").lower() for item in health}
    if statuses & {"failed", "unhealthy"}:
        return "unhealthy"
    if statuses & {"degraded"}:
        return "degraded"
    if statuses & {"healthy"}:
        return "healthy"
    if statuses & {"planned", "pending"}:
        return "planned"
    return "unknown"


def _user_dashboard_sections(
    *,
    urls: Mapping[str, str],
    health: list[dict[str, Any]],
    onboarding: Mapping[str, Any],
    model: Mapping[str, Any],
    billing: Mapping[str, Any],
) -> list[dict[str, Any]]:
    qmd = next((item for item in health if item["service_name"] == "qmd-mcp"), {"status": "unknown", "checked_at": ""})
    memory = next((item for item in health if item["service_name"] == "memory-synth"), {"status": "unknown", "checked_at": ""})
    health_index = {str(item["service_name"]): item for item in health}
    hermes_url = str(urls.get("hermes") or "").rstrip("/")
    drive_url = f"{hermes_url}/drive" if hermes_url else str(urls.get("files") or "")
    code_url = f"{hermes_url}/code" if hermes_url else str(urls.get("code") or "")
    terminal_url = f"{hermes_url}/terminal" if hermes_url else str(urls.get("terminal") or "")
    plugin_links = [
        {"role": "Hermes Dashboard", "url": str(urls.get("hermes") or urls.get("dashboard") or "")},
        {"role": "Drive", "url": drive_url},
        {"role": "Code", "url": code_url},
        {"role": "Terminal", "url": terminal_url},
    ]
    return [
        {
            "section": "deployment_health",
            "label": "Deployment Health",
            "status": _health_status(health),
            "services": health,
        },
        {
            "section": "access_links",
            "label": "Access Links",
            "status": "ready" if urls else "pending",
            "links": [link for link in plugin_links if link["url"]],
        },
        {
            "section": "bot_setup",
            "label": "Bot Setup",
            "status": "contacted" if onboarding.get("first_contacted") else "pending",
            "channel": str(onboarding.get("channel") or ""),
            "handoff_recorded": bool(onboarding.get("handoff_recorded")),
        },
        {
            "section": "files",
            "label": "Drive",
            "status": "ready" if drive_url else "pending",
            "url": drive_url,
        },
        {
            "section": "code",
            "label": "Code",
            "status": "ready" if code_url else "pending",
            "url": code_url,
        },
        {
            "section": "terminal",
            "label": "Terminal",
            "status": "ready" if terminal_url else "pending",
            "url": terminal_url,
        },
        {
            "section": "hermes",
            "label": "Hermes Dashboard",
            "status": "ready" if urls.get("hermes") else "pending",
            "url": str(urls.get("hermes") or ""),
        },
        {
            "section": "qmd_memory",
            "label": "qmd And Memory",
            "status": _health_status([qmd, memory]),
            "qmd": qmd,
            "memory": memory,
        },
        {
            "section": "skills",
            "label": "Skills",
            "status": str(health_index.get("managed-context", {}).get("status") or "planned"),
            "summary": "managed context and org-published skills",
        },
        {
            "section": "model",
            "label": "Model",
            "status": str(model.get("credential_state") or "unknown"),
            "provider": str(model.get("provider") or ""),
            "model_id": str(model.get("model_id") or ""),
        },
        {
            "section": "billing",
            "label": "Billing",
            "status": str(billing.get("entitlement_state") or "none"),
            "subscriptions": billing.get("subscriptions") or [],
        },
        {
            "section": "security",
            "label": "Security",
            "status": "masked",
            "summary": "session-scoped dashboard access; secrets are reference-only",
        },
        {
            "section": "support",
            "label": "Support",
            "status": "available",
            "summary": "operator support actions are reason-required, queued, and audited",
        },
    ]


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
        rowdict(row)
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
        metadata = _json_loads(str(dep.get("metadata_json") or "{}"))
        model_id = onboarding.get("selected_model_id") or metadata.get("selected_model_id") or ""
        urls = _deployment_urls(str(dep["prefix"] or ""), str(dep["base_domain"] or ""), metadata)
        billing = {
            "entitlement_state": str(user["entitlement_state"] or "none"),
            "entitlement_updated_at": str(user["entitlement_updated_at"] or ""),
            "subscriptions": subscriptions,
        }
        model = {
            "provider": primary_provider({}),
            "model_id": str(model_id or ""),
            "credential_state": "secret_ref_pending",
        }
        deployment_cards.append(
            {
                "deployment_id": str(dep["deployment_id"] or ""),
                "status": str(dep["status"] or ""),
                "prefix": str(dep["prefix"] or ""),
                "base_domain": str(dep["base_domain"] or ""),
                "access": {"urls": urls},
                "billing": billing,
                "bot_contact": onboarding,
                "model": model,
                "freshness": {
                    "qmd": next((item for item in health if item["service_name"] == "qmd-mcp"), {"status": "unknown", "checked_at": ""}),
                    "memory": next((item for item in health if item["service_name"] == "memory-synth"), {"status": "unknown", "checked_at": ""}),
                },
                "sections": _user_dashboard_sections(urls=urls, health=health, onboarding=onboarding, model=model, billing=billing),
                "service_health": health,
                "recent_events": _deployment_events(conn, str(dep["deployment_id"]), limit=recent_limit),
            }
        )
    return {
        "sections": [{"section": section, "label": section.replace("_", " ").title()} for section in ARCLINK_USER_DASHBOARD_SECTIONS],
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
        rowdict(row)
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
        rowdict(row)
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
        rowdict(row)
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
        rowdict(row)
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

    general_event_args: list[Any] = []
    general_event_where = "WHERE 1 = 1"
    if filters["deployment_id"]:
        general_event_where += " AND subject_id = ?"
        general_event_args.append(filters["deployment_id"])
    general_event_where += _time_filter("created_at", filters["since"], general_event_args)
    events = [
        {
            "event_id": str(row["event_id"] or ""),
            "subject_kind": str(row["subject_kind"] or ""),
            "subject_id": str(row["subject_id"] or ""),
            "event_type": str(row["event_type"] or ""),
            "deployment_id": str(row["subject_id"] or ""),
            "created_at": str(row["created_at"] or ""),
        }
        for row in conn.execute(
            f"""
            SELECT event_id, subject_kind, subject_id, event_type, created_at
            FROM arclink_events
            {general_event_where}
            ORDER BY created_at DESC, event_id DESC
            LIMIT ?
            """,
            (*general_event_args, limit),
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
        {"kind": "provisioning_job", **rowdict(row)}
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
    user_args: list[Any] = []
    user_where = "WHERE 1 = 1"
    if filters["user_id"]:
        user_where += " AND user_id = ?"
        user_args.append(filters["user_id"])
    if filters["status"]:
        user_where += " AND entitlement_state = ?"
        user_args.append(filters["status"])
    user_where += _time_filter("created_at", filters["since"], user_args)
    users = [
        {
            "user_id": str(row["user_id"] or ""),
            "email": str(row["email"] or ""),
            "display_name": str(row["display_name"] or ""),
            "status": str(row["status"] or ""),
            "stripe_customer_id": str(row["stripe_customer_id"] or ""),
            "entitlement_state": str(row["entitlement_state"] or ""),
            "created_at": str(row["created_at"] or ""),
        }
        for row in conn.execute(
            f"""
            SELECT user_id, email, display_name, status, stripe_customer_id, entitlement_state, created_at
            FROM arclink_users
            {user_where}
            ORDER BY created_at DESC, user_id DESC
            LIMIT ?
            """,
            (*user_args, limit),
        ).fetchall()
    ]
    user_count = _count(conn, "SELECT COUNT(*) FROM arclink_users")
    now = utc_now_iso()
    active_user_sessions = _count(
        conn,
        """
        SELECT COUNT(*)
        FROM arclink_user_sessions
        WHERE status = 'active' AND revoked_at = '' AND expires_at > ?
        """,
        (now,),
    )
    active_admin_sessions = _count(
        conn,
        """
        SELECT COUNT(*)
        FROM arclink_admin_sessions
        WHERE status = 'active' AND revoked_at = '' AND expires_at > ?
        """,
        (now,),
    )
    admin_count = _count(conn, "SELECT COUNT(*) FROM arclink_admins WHERE status = 'active'")
    rate_limit_observations = _count(conn, "SELECT COUNT(*) FROM rate_limits")
    public_bot_sessions = _count(
        conn,
        "SELECT COUNT(*) FROM arclink_onboarding_sessions WHERE LOWER(channel) IN ('telegram', 'discord')",
    )
    event_count = _count(conn, "SELECT COUNT(*) FROM arclink_events")
    audit_count = _count(conn, "SELECT COUNT(*) FROM arclink_audit_log")
    queued_action_count = _count(conn, "SELECT COUNT(*) FROM arclink_action_intents WHERE status = 'queued'")
    failed_job_count = _count(conn, "SELECT COUNT(*) FROM arclink_provisioning_jobs WHERE status = 'failed'")
    admin_sections = [
        {
            "section": "onboarding_funnel",
            "label": "Onboarding Funnel",
            "status": "ready",
            "counts": {"sessions": sum(int(row["count"]) for row in session_counts), "events": sum(int(row["count"]) for row in event_counts)},
        },
        {"section": "users", "label": "Users", "status": "ready", "counts": {"users": user_count}},
        {
            "section": "deployments",
            "label": "Deployments",
            "status": "ready",
            "counts": {"visible": len(deployments)},
        },
        {
            "section": "payments",
            "label": "Payments",
            "status": "ready",
            "counts": {"subscriptions": len(subscriptions)},
        },
        {
            "section": "infrastructure",
            "label": "Infrastructure",
            "status": "degraded" if recent_failures or dns_drift else "ready",
            "counts": {"service_health": len(service_health), "dns_drift": len(dns_drift), "failed_jobs": failed_job_count},
        },
        {
            "section": "bots",
            "label": "Bots",
            "status": "ready",
            "counts": {"public_bot_sessions": public_bot_sessions},
        },
        {
            "section": "security_abuse",
            "label": "Security And Abuse",
            "status": "ready",
            "counts": {
                "active_admins": admin_count,
                "active_user_sessions": active_user_sessions,
                "active_admin_sessions": active_admin_sessions,
                "rate_limit_observations": rate_limit_observations,
            },
        },
        {
            "section": "releases_maintenance",
            "label": "Releases And Maintenance",
            "status": "ready",
            "counts": {"rollout_actions": sum(1 for row in action_intents if row["action_type"] == "rollout")},
        },
        {
            "section": "logs_events",
            "label": "Logs And Events",
            "status": "ready",
            "counts": {"events": event_count, "recent_failures": len(recent_failures[:limit])},
        },
        {"section": "audit", "label": "Audit", "status": "ready", "counts": {"audit_rows": audit_count}},
        {
            "section": "queued_actions",
            "label": "Queued Actions",
            "status": "pending" if queued_action_count else "clear",
            "counts": {"queued": queued_action_count},
        },
    ]

    return {
        "filters": filters,
        "sections": admin_sections,
        "onboarding_funnel": {"sessions": session_counts, "events": event_counts},
        "users": users,
        "subscriptions": subscriptions,
        "deployments": deployments,
        "service_health": service_health,
        "dns_drift": dns_drift,
        "provisioning_jobs": provisioning_jobs,
        "action_intents": action_intents,
        "events": events,
        "audit_rows": audit_rows,
        "audit": audit_rows,
        "recent_failures": recent_failures[:limit],
        "active_sessions": {"user": active_user_sessions, "admin": active_admin_sessions},
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
