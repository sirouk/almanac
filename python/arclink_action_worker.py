#!/usr/bin/env python3
"""ArcLink admin action worker: consumes queued intents via executor."""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import tempfile
import time
from typing import Any, Callable, Mapping

from arclink_control import (
    ARCLINK_ACTION_ATTEMPT_STATUSES,
    ARCLINK_ACTION_INTENT_STATUSES,
    Config,
    append_arclink_audit,
    append_arclink_event,
    comp_arclink_subscription,
    connect_db,
    link_arclink_action_operation,
    note_refresh_job,
    utc_now_iso,
)
from arclink_boundary import json_dumps_safe, json_loads_safe, reject_secret_material, rowdict
from arclink_secrets_regex import contains_secret_material, redact_then_truncate
from arclink_adapters import DnsRecord
from arclink_ingress import desired_arclink_ingress_records, mark_arclink_dns_provisioned, persist_arclink_dns_records
from arclink_executor import (
    ArcLinkExecutor,
    ArcLinkExecutorConfig,
    ArcLinkExecutorError,
    ChutesKeyApplyRequest,
    CloudflareDnsApplyRequest,
    DockerComposeLifecycleRequest,
    FakeSecretResolver,
    StripeActionApplyRequest,
    executor_for_fleet_host,
)
from arclink_provisioning import render_arclink_state_roots
from arclink_pod_migration import garbage_collect_pod_migrations, migrate_pod
from arclink_dashboard import ARCLINK_BACKUP_FAILED_CLOSED_REASON, record_arclink_backup_write_check_failed_closed
from arclink_rollout import (
    ArcLinkRolloutError,
    execute_arcpod_update_rollout_batch,
    materialize_arcpod_update_rollout_job,
    plan_arcpod_update_rollout,
)


class ArcLinkActionWorkerError(ValueError):
    pass


AcademyPostApplyRunner = Callable[[Mapping[str, Any]], Mapping[str, Any] | None]


# Action types that map to implemented executor or local control-plane calls.
_EXECUTOR_ACTIONS = frozenset({
    "restart", "reprovision", "dns_repair", "rotate_chutes_key", "refund", "cancel", "comp", "stripe_entitlement_recovery", "backup_write_check",
})

_STALE_THRESHOLD_SECONDS = 3600  # 1 hour
_STALE_RECOVERY_MAX_ATTEMPTS = 3
_ActionExecutorCache = dict[tuple[str, str, str], ArcLinkExecutor]
_ACTION_EXECUTOR_CACHE: _ActionExecutorCache = {}
_LIFECYCLE_PATH_OVERRIDE_KEYS = ("project_name", "env_file", "compose_file")
_DNS_REPAIR_RECORD_TYPES = frozenset({"A", "AAAA", "CNAME", "TXT"})


def _worker_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


def _reject_secrets(value: Any, *, path: str = "$") -> None:
    reject_secret_material(value, path=path, label="ArcLink action worker", error_cls=ArcLinkActionWorkerError)


def _safe_error_message(exc: Exception) -> str:
    msg = redact_then_truncate(str(exc), limit=500)
    fallback = "executor error contained secret material and was redacted"
    if contains_secret_material(msg, allow_safe_refs=False):
        return fallback
    if contains_secret_material(str(exc)):
        return msg or fallback
    return msg


def _safe_error_code(exc: Exception) -> str:
    if isinstance(exc, (ArcLinkActionWorkerError, ArcLinkRolloutError)):
        return "action_validation_error"
    if isinstance(exc, ArcLinkExecutorError) or exc.__class__.__name__ == "ArcLinkExecutorError":
        return "executor_error"
    if isinstance(exc, sqlite3.Error):
        return "database_error"
    return "unexpected_error"


def _safe_mapping_json(raw: Any) -> dict[str, Any]:
    parsed = json_loads_safe(str(raw or "{}"))
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _lifecycle_path_overrides(metadata: Mapping[str, Any], *, env: Mapping[str, str] | None = None) -> dict[str, str]:
    overrides = {
        key: str(metadata.get(key) or "").strip()
        for key in _LIFECYCLE_PATH_OVERRIDE_KEYS
        if str(metadata.get(key) or "").strip()
    }
    if not overrides:
        return {}
    source = env or os.environ
    if _truthy(source.get("ARCLINK_ACTION_WORKER_ALLOW_LIFECYCLE_PATH_OVERRIDES")):
        return overrides
    fields = ", ".join(sorted(overrides))
    raise ArcLinkActionWorkerError(
        "ArcLink lifecycle actions derive Docker Compose project/env/compose paths "
        "from deployment state; metadata override(s) "
        f"{fields} require ARCLINK_ACTION_WORKER_ALLOW_LIFECYCLE_PATH_OVERRIDES=1"
    )


def _dns_role_from_record_id(record_id: str, deployment_id: str, hostname: str) -> str:
    prefix = f"dns_{deployment_id}_"
    if record_id.startswith(prefix) and record_id[len(prefix):]:
        return record_id[len(prefix):]
    return hostname.replace(".", "_").replace("-", "_")[:80] or "record"


def _deployment_row(conn: sqlite3.Connection, deployment_id: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM arclink_deployments WHERE deployment_id = ?",
        (deployment_id,),
    ).fetchone()
    if row is None:
        raise ArcLinkActionWorkerError("ArcLink action target deployment was not found")
    return row


def _resolve_dns_repair(
    conn: sqlite3.Connection,
    *,
    target_kind: str,
    target_id: str,
    metadata: Mapping[str, Any],
) -> tuple[str, dict[str, dict[str, Any]], str]:
    deployment_id = str(metadata.get("deployment_id") or "").strip()
    if target_kind == "deployment":
        if deployment_id and deployment_id != target_id:
            raise ArcLinkActionWorkerError("ArcLink DNS repair metadata deployment_id does not match action target")
        deployment_id = target_id
    elif target_kind == "dns_record":
        record = conn.execute(
            "SELECT deployment_id FROM arclink_dns_records WHERE record_id = ?",
            (target_id,),
        ).fetchone()
        if record is None:
            raise ArcLinkActionWorkerError("ArcLink DNS repair target record was not found")
        if deployment_id and deployment_id != str(record["deployment_id"] or ""):
            raise ArcLinkActionWorkerError("ArcLink DNS repair metadata deployment_id does not match DNS record target")
        deployment_id = str(record["deployment_id"] or "")
    if not deployment_id:
        raise ArcLinkActionWorkerError("ArcLink DNS repair requires a deployment target")

    deployment = _deployment_row(conn, deployment_id)
    explicit_dns = metadata.get("dns")
    if explicit_dns is not None:
        if not isinstance(explicit_dns, Mapping):
            raise ArcLinkActionWorkerError("ArcLink DNS repair metadata dns must be an object")
        if not explicit_dns:
            raise ArcLinkActionWorkerError("ArcLink DNS repair metadata dns must include at least one record")
        dns: dict[str, dict[str, Any]] = {}
        for role, record in explicit_dns.items():
            if not isinstance(record, Mapping):
                raise ArcLinkActionWorkerError(f"invalid ArcLink DNS record: {role}")
            dns[str(role)] = dict(record)
        return deployment_id, dns, str(metadata.get("zone_id") or "")

    rows = conn.execute(
        """
        SELECT record_id, hostname, record_type, target
        FROM arclink_dns_records
        WHERE deployment_id = ? AND status != 'torn_down'
        ORDER BY record_id
        """,
        (deployment_id,),
    ).fetchall()
    if rows:
        dns: dict[str, dict[str, Any]] = {}
        for row in rows:
            hostname = str(row["hostname"] or "").strip().lower()
            role = _dns_role_from_record_id(str(row["record_id"] or ""), deployment_id, hostname)
            dns[role] = {
                "hostname": hostname,
                "record_type": str(row["record_type"] or "CNAME").strip().upper(),
                "target": str(row["target"] or "").strip(),
                "proxied": True,
            }
        return deployment_id, dns, str(metadata.get("zone_id") or "")

    deployment_meta = _safe_mapping_json(deployment["metadata_json"])
    ingress_mode = str(metadata.get("ingress_mode") or deployment_meta.get("ingress_mode") or "domain").strip().lower()
    base_domain = str(metadata.get("base_domain") or deployment["base_domain"] or deployment_meta.get("base_domain") or "").strip()
    edge_target = str(metadata.get("edge_target") or deployment_meta.get("edge_target") or (f"edge.{base_domain}" if base_domain else "")).strip()
    tailscale_dns_name = str(metadata.get("tailscale_dns_name") or deployment_meta.get("tailscale_dns_name") or "").strip()
    tailscale_strategy = str(metadata.get("tailscale_host_strategy") or deployment_meta.get("tailscale_host_strategy") or "path").strip()
    try:
        desired = desired_arclink_ingress_records(
            prefix=str(deployment["prefix"] or ""),
            base_domain=base_domain,
            target=edge_target,
            ingress_mode=ingress_mode,
            tailscale_dns_name=tailscale_dns_name,
            tailscale_host_strategy=tailscale_strategy,
        )
    except Exception as exc:
        raise ArcLinkActionWorkerError(_safe_error_message(exc)) from exc
    dns = {
        role: {
            "hostname": record.hostname,
            "record_type": record.record_type,
            "target": record.target,
            "proxied": record.proxied,
        }
        for role, record in desired.items()
    }
    if not dns:
        raise ArcLinkActionWorkerError("ArcLink DNS repair found no domain DNS records for deployment")
    return deployment_id, dns, str(metadata.get("zone_id") or deployment_meta.get("cloudflare_zone_id") or "")


def _dns_repair_records_for_persist(dns: Mapping[str, Mapping[str, Any]]) -> dict[str, DnsRecord]:
    records: dict[str, DnsRecord] = {}
    for role, record in dns.items():
        if not isinstance(record, Mapping):
            raise ArcLinkActionWorkerError(f"invalid ArcLink DNS record: {role}")
        hostname = str(record.get("hostname") or "").strip().lower()
        record_type = str(record.get("record_type") or "CNAME").strip().upper()
        target = str(record.get("target") or "").strip()
        if not hostname or not target:
            raise ArcLinkActionWorkerError(f"ArcLink DNS record requires hostname and target: {role}")
        if record_type not in _DNS_REPAIR_RECORD_TYPES:
            allowed = ", ".join(sorted(_DNS_REPAIR_RECORD_TYPES))
            raise ArcLinkActionWorkerError(f"unsupported ArcLink DNS record type; allowed types: {allowed}")
        records[str(role)] = DnsRecord(
            hostname=hostname,
            record_type=record_type,
            target=target,
            proxied=bool(record.get("proxied", True)),
        )
    return records


def _latest_subscription_for_user(conn: sqlite3.Connection, user_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM arclink_subscriptions
        WHERE user_id = ?
        ORDER BY
          CASE status WHEN 'active' THEN 0 WHEN 'trialing' THEN 1 ELSE 2 END,
          updated_at DESC,
          created_at DESC
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()


def _validate_explicit_target(metadata: Mapping[str, Any], key: str, resolved: str) -> None:
    explicit = str(metadata.get(key) or "").strip()
    if explicit and resolved and explicit != resolved:
        raise ArcLinkActionWorkerError(f"ArcLink action metadata {key} does not match server-resolved target")


def _rollout_deployment_ids(
    *,
    target_kind: str,
    target_id: str,
    metadata: Mapping[str, Any],
) -> list[str]:
    raw = metadata.get("deployment_ids", metadata.get("deployments", ()))
    deployment_ids: list[str] = []
    if isinstance(raw, str):
        deployment_ids = [item.strip() for item in raw.split(",") if item.strip()]
    elif isinstance(raw, (list, tuple)):
        deployment_ids = [str(item or "").strip() for item in raw if str(item or "").strip()]
    elif raw:
        raise ArcLinkActionWorkerError("rollout deployment_ids metadata must be a list or comma-separated string")
    seen: set[str] = set()
    deployment_ids = [item for item in deployment_ids if not (item in seen or seen.add(item))]

    if target_kind == "deployment":
        if deployment_ids and target_id not in deployment_ids:
            raise ArcLinkActionWorkerError("rollout deployment_ids must include the deployment action target")
        return deployment_ids or [target_id]
    if target_kind == "system":
        return deployment_ids
    raise ArcLinkActionWorkerError("rollout action requires a deployment or system target")


def _rollout_batch_size(metadata: Mapping[str, Any]) -> int | None:
    raw = metadata.get("batch_size")
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ArcLinkActionWorkerError("rollout batch_size metadata must be an integer") from exc


def _rollout_execution_batch_index(metadata: Mapping[str, Any]) -> int | None:
    raw = metadata.get("execute_batch_index", metadata.get("batch_index"))
    if raw is None or str(raw).strip() == "":
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ArcLinkActionWorkerError("rollout execution batch_index metadata must be an integer") from exc
    if value < 1:
        raise ArcLinkActionWorkerError("rollout execution batch_index metadata must be at least 1")
    return value


def _resolve_stripe_action(
    conn: sqlite3.Connection,
    *,
    action_type: str,
    target_kind: str,
    target_id: str,
    metadata: Mapping[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    user_id = ""
    deployment_id = str(metadata.get("deployment_id") or "").strip()
    subscription_id = ""
    stripe_customer_id = ""
    stripe_subscription_id = ""
    row: sqlite3.Row | None = None

    if target_kind == "deployment":
        row = _deployment_row(conn, target_id)
        deployment_id = target_id
        user_id = str(row["user_id"] or "")
    elif target_kind == "user":
        user = conn.execute("SELECT * FROM arclink_users WHERE user_id = ?", (target_id,)).fetchone()
        if user is None:
            raise ArcLinkActionWorkerError("ArcLink Stripe action user target was not found")
        user_id = target_id
        stripe_customer_id = str(user["stripe_customer_id"] or "")
    elif target_kind == "subscription":
        sub = conn.execute(
            "SELECT * FROM arclink_subscriptions WHERE subscription_id = ? OR stripe_subscription_id = ?",
            (target_id, target_id),
        ).fetchone()
        if sub is None:
            raise ArcLinkActionWorkerError("ArcLink Stripe action subscription target was not found")
        subscription_id = str(sub["subscription_id"] or "")
        user_id = str(sub["user_id"] or "")
        stripe_customer_id = str(sub["stripe_customer_id"] or "")
        stripe_subscription_id = str(sub["stripe_subscription_id"] or "")
    else:
        raise ArcLinkActionWorkerError("ArcLink Stripe action requires a user, deployment, or subscription target")

    if user_id and not stripe_customer_id:
        user = conn.execute("SELECT stripe_customer_id FROM arclink_users WHERE user_id = ?", (user_id,)).fetchone()
        stripe_customer_id = str(user["stripe_customer_id"] or "") if user is not None else ""
    if user_id and (not subscription_id or not stripe_subscription_id):
        sub = _latest_subscription_for_user(conn, user_id)
        if sub is not None:
            subscription_id = subscription_id or str(sub["subscription_id"] or "")
            stripe_customer_id = stripe_customer_id or str(sub["stripe_customer_id"] or "")
            stripe_subscription_id = stripe_subscription_id or str(sub["stripe_subscription_id"] or "")

    _validate_explicit_target(metadata, "user_id", user_id)
    _validate_explicit_target(metadata, "deployment_id", deployment_id)
    _validate_explicit_target(metadata, "stripe_customer_id", stripe_customer_id)
    _validate_explicit_target(metadata, "stripe_subscription_id", stripe_subscription_id)

    customer_ref = f"secret://arclink/stripe/customer/{user_id}" if user_id and stripe_customer_id else ""
    if action_type == "refund" and not stripe_customer_id:
        raise ArcLinkActionWorkerError("ArcLink refund target could not be resolved to a Stripe customer")
    if action_type == "cancel" and not stripe_subscription_id:
        raise ArcLinkActionWorkerError("ArcLink cancel target could not be resolved to a Stripe subscription")

    resolved_metadata = dict(metadata)
    resolved_metadata.update(
        {
            "action_target_kind": target_kind,
            "action_target_id": target_id,
            "user_id": user_id,
            "deployment_id": deployment_id,
            "subscription_id": subscription_id,
            "stripe_customer_id": stripe_customer_id,
            "stripe_subscription_id": stripe_subscription_id,
            "target_resolved_by": "control_db",
        }
    )
    return deployment_id or user_id or subscription_id, customer_ref, resolved_metadata


def _record_attempt(
    conn: sqlite3.Connection,
    *,
    action_id: str,
    status: str = "running",
    adapter: str = "",
    result: Mapping[str, Any] | None = None,
    error: str = "",
) -> str:
    if status not in ARCLINK_ACTION_ATTEMPT_STATUSES:
        raise ArcLinkActionWorkerError(f"unsupported ArcLink action attempt status: {status or 'blank'}")
    attempt_id = _worker_id("att")
    now = utc_now_iso()
    result_json = json_dumps_safe(result, label="ArcLink action worker", error_cls=ArcLinkActionWorkerError) if result else "{}"
    if error:
        _reject_secrets({"error": error}, path="$")
    finished = now if status in ("succeeded", "failed") else ""
    conn.execute(
        """
        INSERT INTO arclink_action_attempts (
          attempt_id, action_id, status, executor_adapter, result_json, error, started_at, finished_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (attempt_id, action_id, status, adapter, result_json, error, now, finished),
    )
    return attempt_id


def _finish_attempt(
    conn: sqlite3.Connection,
    *,
    attempt_id: str,
    status: str,
    result: Mapping[str, Any] | None = None,
    error: str = "",
) -> None:
    if status not in ARCLINK_ACTION_ATTEMPT_STATUSES:
        raise ArcLinkActionWorkerError(f"unsupported ArcLink action attempt status: {status or 'blank'}")
    now = utc_now_iso()
    result_json = json_dumps_safe(result, label="ArcLink action worker", error_cls=ArcLinkActionWorkerError) if result else "{}"
    if error:
        _reject_secrets({"error": error}, path="$")
    conn.execute(
        "UPDATE arclink_action_attempts SET status = ?, result_json = ?, error = ?, finished_at = ? WHERE attempt_id = ?",
        (status, result_json, error, now, attempt_id),
    )


def _update_intent_status(
    conn: sqlite3.Connection,
    *,
    action_id: str,
    status: str,
) -> None:
    if status not in ARCLINK_ACTION_INTENT_STATUSES:
        raise ArcLinkActionWorkerError(f"unsupported ArcLink action intent status: {status or 'blank'}")
    if status == "queued":
        conn.execute(
            """
            UPDATE arclink_action_intents
            SET status = ?, worker_id = '', claimed_at = '', updated_at = ?
            WHERE action_id = ?
            """,
            (status, utc_now_iso(), action_id),
        )
    else:
        conn.execute(
            "UPDATE arclink_action_intents SET status = ?, updated_at = ? WHERE action_id = ?",
            (status, utc_now_iso(), action_id),
        )


def _claim_next_queued_action(conn: sqlite3.Connection, *, worker_id: str) -> dict[str, Any] | None:
    """Atomically claim the oldest queued action for this worker."""
    now = utc_now_iso()
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            """
            SELECT action_id
            FROM arclink_action_intents
            WHERE status = 'queued'
            ORDER BY created_at ASC, action_id ASC
            LIMIT 1
            """,
        ).fetchone()
        if row is None:
            conn.commit()
            return None

        action_id = str(row["action_id"])
        cursor = conn.execute(
            """
            UPDATE arclink_action_intents
            SET status = 'running',
                worker_id = ?,
                claimed_at = ?,
                updated_at = ?
            WHERE action_id = ?
              AND status = 'queued'
            """,
            (worker_id, now, now, action_id),
        )
        if cursor.rowcount != 1:
            conn.commit()
            return None

        claimed = conn.execute(
            "SELECT * FROM arclink_action_intents WHERE action_id = ?",
            (action_id,),
        ).fetchone()
        conn.commit()
        return dict(claimed) if claimed is not None else None
    except Exception:
        conn.rollback()
        raise


def _active_action_placement_host(conn: sqlite3.Connection, *, deployment_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT h.*
        FROM arclink_deployment_placements p
        JOIN arclink_fleet_hosts h ON h.host_id = p.host_id
        WHERE p.deployment_id = ? AND p.status = 'active'
        ORDER BY p.placed_at DESC
        LIMIT 1
        """,
        (str(deployment_id or "").strip(),),
    ).fetchone()
    return dict(row) if row is not None else None


def _secret_refs_for_action(metadata: Any) -> dict[str, str]:
    refs: dict[str, str] = {}

    def walk(value: Any) -> None:
        if isinstance(value, str) and value.startswith("secret://"):
            refs[value] = "fake-secret-material"
        elif isinstance(value, Mapping):
            for nested in value.values():
                walk(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                walk(nested)
    walk(metadata)
    return refs


def _action_executor_cache_key(
    *,
    adapter: str,
    host: Mapping[str, Any],
    fake_secret_refs: Mapping[str, str] | None = None,
    deployment_id: str = "",
) -> tuple[str, str, str]:
    host_id = str(host.get("host_id") or "").strip()
    if adapter != "fake":
        return host_id, adapter, str(deployment_id or "")
    ref_hash = hashlib.sha256(
        json.dumps(sorted((fake_secret_refs or {}).keys()), separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return host_id, adapter, ref_hash


def _executor_for_action_host(
    *,
    env: Mapping[str, str],
    host: Mapping[str, Any],
    metadata: Any,
    cache: _ActionExecutorCache,
    deployment_id: str = "",
) -> ArcLinkExecutor:
    adapter = str(env.get("ARCLINK_EXECUTOR_ADAPTER") or "").strip().lower()
    if adapter not in {"fake", "local", "ssh"}:
        raise ArcLinkActionWorkerError("ArcLink action worker placement routing requires ARCLINK_EXECUTOR_ADAPTER")
    fake_secret_refs = _secret_refs_for_action(metadata) if adapter == "fake" else {}
    cache_key = _action_executor_cache_key(
        adapter=adapter,
        host=host,
        fake_secret_refs=fake_secret_refs,
        deployment_id=deployment_id,
    )
    if cache_key in cache:
        return cache[cache_key]
    if adapter == "fake":
        executor = executor_for_fleet_host(adapter=adapter, env=env, host=host, fake_secret_refs=fake_secret_refs)
    else:
        from arclink_sovereign_worker import SovereignSecretResolver
        host_id = str(host.get("host_id") or "").strip()
        secret_store_dir = Path(
            env.get("ARCLINK_SECRET_STORE_DIR")
            or "/home/arclink/arclink/arclink-priv/state/sovereign-secrets"
        )
        materialization_root = Path(
            env.get("ARCLINK_ACTION_WORKER_SECRET_MATERIALIZATION_DIR")
            or "/tmp/arclink-action-worker/secrets"
        )
        secret_scope = str(deployment_id or host_id or "unknown-host").strip()
        resolver = SovereignSecretResolver(
            env=env,
            secret_store_dir=secret_store_dir / secret_scope,
            # Scope the plaintext materialization root per deployment so two
            # deployments cannot collide on a shared root / basename.
            materialization_root=materialization_root / secret_scope,
            deployment_id=secret_scope,
        )
        executor = executor_for_fleet_host(adapter=adapter, env=env, host=host, secret_resolver=resolver)
    cache[cache_key] = executor
    return executor


def _select_action_executor(
    conn: sqlite3.Connection,
    *,
    intent: Mapping[str, Any],
    metadata: Any,
    fallback_executor: ArcLinkExecutor,
    env: Mapping[str, str],
    cache: _ActionExecutorCache,
) -> tuple[ArcLinkExecutor, dict[str, Any]]:
    target_kind = str(intent.get("target_kind") or "")
    target_id = str(intent.get("target_id") or "")
    routing = {
        "host_id": "",
        "hostname": "",
        "adapter": fallback_executor.config.adapter_name,
        "fallback_reason": "not_deployment_target" if target_kind != "deployment" else "no_active_placement",
    }
    if target_kind != "deployment":
        return fallback_executor, routing
    host = _active_action_placement_host(conn, deployment_id=target_id)
    if host is None:
        return fallback_executor, routing
    adapter = str(env.get("ARCLINK_EXECUTOR_ADAPTER") or "").strip().lower()
    if adapter not in {"fake", "local", "ssh"}:
        routing.update(
            {
                "host_id": str(host.get("host_id") or ""),
                "hostname": str(host.get("hostname") or ""),
                "fallback_reason": "executor_injected",
            }
        )
        return fallback_executor, routing
    selected = _executor_for_action_host(env=env, host=host, metadata=metadata, cache=cache, deployment_id=target_id)
    return selected, {
        "host_id": str(host.get("host_id") or ""),
        "hostname": str(host.get("hostname") or ""),
        "adapter": selected.config.adapter_name,
        "fallback_reason": "",
    }


# ---------------------------------------------------------------------------
# Core worker entrypoint
# ---------------------------------------------------------------------------

def process_next_arclink_action(
    conn: sqlite3.Connection,
    *,
    executor: ArcLinkExecutor,
    worker_id: str = "",
    env: Mapping[str, str] | None = None,
    executor_cache: _ActionExecutorCache | None = None,
) -> dict[str, Any] | None:
    """Claim and execute the oldest queued action intent. Returns the result or None if empty."""
    clean_worker_id = str(worker_id or "").strip() or _worker_id("wrk")
    intent = _claim_next_queued_action(conn, worker_id=clean_worker_id)
    if intent is None:
        return None

    return _execute_action(conn, intent=intent, executor=executor, env=env, executor_cache=executor_cache)


def process_arclink_action_batch(
    conn: sqlite3.Connection,
    *,
    executor: ArcLinkExecutor,
    batch_size: int = 10,
    worker_id: str = "",
    env: Mapping[str, str] | None = None,
    executor_cache: _ActionExecutorCache | None = None,
) -> list[dict[str, Any]]:
    """Process up to batch_size queued actions."""
    if batch_size < 1:
        raise ArcLinkActionWorkerError("batch size must be at least 1")
    clean_worker_id = str(worker_id or "").strip() or _worker_id("wrk")
    results = []
    for _ in range(batch_size):
        result = process_next_arclink_action(
            conn,
            executor=executor,
            worker_id=clean_worker_id,
            env=env,
            executor_cache=executor_cache,
        )
        if result is None:
            break
        results.append(result)
    return results


def _execute_action(
    conn: sqlite3.Connection,
    *,
    intent: dict[str, Any],
    executor: ArcLinkExecutor,
    env: Mapping[str, str] | None = None,
    executor_cache: _ActionExecutorCache | None = None,
) -> dict[str, Any]:
    action_id = str(intent["action_id"])
    action_type = str(intent["action_type"])
    target_kind = str(intent["target_kind"])
    target_id = str(intent["target_id"])
    metadata = json_loads_safe(intent.get("metadata_json", "{}"))
    worker_env = dict(env or os.environ)
    try:
        selected_executor, routing = _select_action_executor(
            conn,
            intent=intent,
            metadata=metadata,
            fallback_executor=executor,
            env=worker_env,
            cache=executor_cache if executor_cache is not None else _ACTION_EXECUTOR_CACHE,
        )
    except Exception as exc:
        error_msg = _safe_error_message(exc)
        error_code = _safe_error_code(exc)
        adapter_name = str(getattr(getattr(executor, "config", None), "adapter_name", "") or "")
        attempt_id = _record_attempt(conn, action_id=action_id, status="failed", adapter=adapter_name, error=error_msg)
        _update_intent_status(conn, action_id=action_id, status="failed")
        append_arclink_event(
            conn,
            subject_kind=target_kind,
            subject_id=target_id,
            event_type=f"action_failed:{action_type}",
            metadata={
                "action_id": action_id,
                "attempt_id": attempt_id,
                "error_code": error_code,
                "error": error_msg,
                "phase": "executor_selection",
            },
            commit=False,
        )
        conn.commit()
        return {
            "action_id": action_id,
            "attempt_id": attempt_id,
            "status": "failed",
            "action_type": action_type,
            "error_code": error_code,
            "error": error_msg,
        }

    attempt_id = _record_attempt(
        conn, action_id=action_id, adapter=selected_executor.config.adapter_name,
    )
    append_arclink_event(
        conn,
        subject_kind=target_kind,
        subject_id=target_id,
        event_type=f"action_attempt_started:{action_type}",
        metadata={
            "action_id": action_id,
            "attempt_id": attempt_id,
            "worker_id": str(intent.get("worker_id") or ""),
            **routing,
        },
        commit=False,
    )
    append_arclink_audit(
        conn,
        action=f"action_worker_attempt_started:{action_type}",
        actor_id="system:action_worker",
        target_kind=target_kind,
        target_id=target_id,
        reason=f"started queued action {action_id}",
        metadata={
            "action_id": action_id,
            "attempt_id": attempt_id,
            "worker_id": str(intent.get("worker_id") or ""),
            **routing,
        },
        commit=False,
    )
    conn.commit()

    try:
        result = _dispatch_action(
            conn=conn,
            executor=selected_executor,
            action_id=action_id,
            action_type=action_type,
            target_kind=target_kind,
            target_id=target_id,
            metadata=metadata,
            idempotency_key=str(intent.get("idempotency_key") or ""),
            requested_by=str(intent.get("admin_id") or ""),
            action_reason=str(intent.get("reason") or ""),
            env=worker_env,
        )
        _reject_secrets(result, path="$.result")

        # Honest status: if dispatch says pending_not_implemented, reflect that
        dispatch_status = str(result.get("status", ""))
        if dispatch_status == "pending_not_implemented":
            intent_status = "failed"
            attempt_status = "failed"
            event_type = f"action_pending_not_implemented:{action_type}"
            outcome_status = "pending_not_implemented"
            error = str(result.get("note", "action type not yet wired to executor"))
        elif dispatch_status == "failed_closed":
            intent_status = "failed"
            attempt_status = "failed"
            event_type = f"action_failed_closed:{action_type}"
            outcome_status = "failed_closed"
            error = str(result.get("note", "action failed closed"))
        else:
            intent_status = "succeeded"
            attempt_status = "succeeded"
            event_type = f"action_executed:{action_type}"
            outcome_status = "succeeded"
            error = ""

        _finish_attempt(conn, attempt_id=attempt_id, status=attempt_status, result=result, error=error)
        _update_intent_status(conn, action_id=action_id, status=intent_status)
        append_arclink_event(
            conn,
            subject_kind=target_kind,
            subject_id=target_id,
            event_type=event_type,
            metadata={"action_id": action_id, "attempt_id": attempt_id, "status": outcome_status, **routing},
            commit=False,
        )
        append_arclink_audit(
            conn,
            action=f"action_worker:{action_type}",
            actor_id="system:action_worker",
            target_kind=target_kind,
            target_id=target_id,
            reason=f"executed queued action {action_id}" if outcome_status == "succeeded" else f"action {action_id} not yet implemented: {action_type}",
            metadata={"action_id": action_id, "attempt_id": attempt_id, "status": outcome_status, **routing},
            commit=False,
        )
        conn.commit()
        return {
            "action_id": action_id,
            "attempt_id": attempt_id,
            "status": outcome_status,
            "action_type": action_type,
            "result": result,
        }
    except Exception as exc:
        error_msg = _safe_error_message(exc)
        error_code = _safe_error_code(exc)
        _finish_attempt(conn, attempt_id=attempt_id, status="failed", error=error_msg)
        _update_intent_status(conn, action_id=action_id, status="failed")
        append_arclink_event(
            conn,
            subject_kind=target_kind,
            subject_id=target_id,
            event_type=f"action_failed:{action_type}",
            metadata={"action_id": action_id, "attempt_id": attempt_id, "error_code": error_code, "error": error_msg, **routing},
            commit=False,
        )
        conn.commit()
        return {
            "action_id": action_id,
            "attempt_id": attempt_id,
            "status": "failed",
            "action_type": action_type,
            "error_code": error_code,
            "error": error_msg,
        }


def _dispatch_action(
    *,
    conn: sqlite3.Connection,
    executor: ArcLinkExecutor,
    action_id: str,
    action_type: str,
    target_kind: str,
    target_id: str,
    metadata: dict[str, Any],
    idempotency_key: str = "",
    requested_by: str = "",
    action_reason: str = "",
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Route action type to executor call. Returns redacted result metadata."""
    if action_type == "restart":
        lifecycle_meta = _deployment_lifecycle_metadata(conn, deployment_id=target_id)
        lifecycle_overrides = _lifecycle_path_overrides(metadata, env=env)
        operation_key = str(metadata.get("idempotency_key") or idempotency_key)
        _link_action_operation(
            conn,
            action_id=action_id,
            operation_kind="docker_compose_lifecycle",
            idempotency_key=operation_key,
            target_kind=target_kind,
            target_id=target_id,
        )
        result = executor.docker_compose_lifecycle(DockerComposeLifecycleRequest(
            deployment_id=target_id,
            action="restart",
            project_name=str(lifecycle_overrides.get("project_name") or lifecycle_meta.get("project_name") or ""),
            env_file=str(lifecycle_overrides.get("env_file") or lifecycle_meta.get("env_file") or ""),
            compose_file=str(lifecycle_overrides.get("compose_file") or lifecycle_meta.get("compose_file") or ""),
            idempotency_key=operation_key,
        ))
        return {"live": result.live, "status": result.status, "action": result.action, "operation_kind": "docker_compose_lifecycle", "operation_idempotency_key": operation_key}

    if action_type == "dns_repair":
        deployment_id, dns, zone_id = _resolve_dns_repair(
            conn,
            target_kind=target_kind,
            target_id=target_id,
            metadata=metadata,
        )
        persist_arclink_dns_records(
            conn,
            deployment_id=deployment_id,
            records=_dns_repair_records_for_persist(dns),
        )
        operation_key = str(metadata.get("idempotency_key") or idempotency_key)
        _link_action_operation(
            conn,
            action_id=action_id,
            operation_kind="cloudflare_dns_apply",
            idempotency_key=operation_key,
            target_kind=target_kind,
            target_id=target_id,
        )
        result = executor.cloudflare_dns_apply(CloudflareDnsApplyRequest(
            deployment_id=deployment_id,
            dns=dns,
            zone_id=zone_id,
            idempotency_key=operation_key,
        ))
        raw_provider_ids = result.metadata.get("provider_record_ids") if isinstance(result.metadata, Mapping) else ()
        provider_ids = tuple(str(item or "").strip() for item in raw_provider_ids) if isinstance(raw_provider_ids, (list, tuple)) else ()
        mark_arclink_dns_provisioned(
            conn,
            deployment_id=deployment_id,
            provisioned=tuple(result.records),
            provider_record_ids=provider_ids,
            metadata={"action_id": action_id, "status": result.status},
        )
        return {"live": result.live, "status": result.status, "deployment_id": deployment_id, "records": list(result.records), "operation_kind": "cloudflare_dns_apply", "operation_idempotency_key": operation_key}

    if action_type == "rotate_chutes_key":
        secret_ref = metadata.get("secret_ref", f"secret://arclink/chutes/{target_id}")
        operation_key = str(metadata.get("idempotency_key") or idempotency_key)
        _link_action_operation(
            conn,
            action_id=action_id,
            operation_kind="chutes_key_apply",
            idempotency_key=operation_key,
            target_kind=target_kind,
            target_id=target_id,
        )
        result = executor.chutes_key_apply(ChutesKeyApplyRequest(
            deployment_id=target_id,
            action="rotate",
            secret_ref=secret_ref,
            label=metadata.get("label", "action_worker_rotate"),
            idempotency_key=operation_key,
        ))
        return {"live": result.live, "status": result.status, "action": result.action, "key_id": result.key_id, "operation_kind": "chutes_key_apply", "operation_idempotency_key": operation_key}

    if action_type in ("refund", "cancel"):
        deployment_or_target_id, customer_ref, stripe_metadata = _resolve_stripe_action(
            conn,
            action_type=action_type,
            target_kind=target_kind,
            target_id=target_id,
            metadata=metadata,
        )
        operation_key = str(metadata.get("idempotency_key") or idempotency_key)
        stripe_metadata["arclink_action_id"] = action_id
        _link_action_operation(
            conn,
            action_id=action_id,
            operation_kind="stripe_action_apply",
            idempotency_key=operation_key,
            target_kind=target_kind,
            target_id=target_id,
        )
        result = executor.stripe_action_apply(StripeActionApplyRequest(
            deployment_id=deployment_or_target_id,
            action=action_type,
            customer_ref=customer_ref,
            idempotency_key=operation_key,
            metadata=stripe_metadata,
        ))
        return {"live": result.live, "status": result.status, "action": result.action, "target_resolved_by": "control_db", "operation_kind": "stripe_action_apply", "operation_idempotency_key": operation_key}

    if action_type == "comp":
        operation_key = str(metadata.get("idempotency_key") or idempotency_key)
        _link_action_operation(
            conn,
            action_id=action_id,
            operation_kind="control_db_comp",
            idempotency_key=operation_key,
            target_kind=target_kind,
            target_id=target_id,
        )
        user_id = str(metadata.get("user_id") or (target_id if target_kind == "user" else "")).strip()
        if not user_id and target_kind == "deployment":
            row = conn.execute("SELECT user_id FROM arclink_deployments WHERE deployment_id = ?", (target_id,)).fetchone()
            user_id = str(row["user_id"] or "") if row is not None else ""
        if not user_id:
            raise ArcLinkActionWorkerError("comp action requires a user target or deployment with owner")
        comp_arclink_subscription(
            conn,
            user_id=user_id,
            deployment_id=target_id if target_kind == "deployment" else str(metadata.get("deployment_id") or ""),
            actor_id=str(metadata.get("actor_id") or "system:action_worker"),
            reason=str(metadata.get("reason") or "operator queued comp action"),
        )
        return {"status": "applied", "action": "comp", "user_id": user_id, "operation_kind": "control_db_comp", "operation_idempotency_key": operation_key}

    if action_type == "stripe_entitlement_recovery":
        if target_kind != "user":
            raise ArcLinkActionWorkerError("stripe_entitlement_recovery action requires a user target")
        operation_key = str(metadata.get("idempotency_key") or idempotency_key)
        _link_action_operation(
            conn,
            action_id=action_id,
            operation_kind="control_db_stripe_entitlement_recovery",
            idempotency_key=operation_key,
            target_kind=target_kind,
            target_id=target_id,
        )
        from arclink_entitlements import apply_stripe_entitlement_recovery

        recovery = apply_stripe_entitlement_recovery(
            conn,
            user_id=target_id,
            actor_id=str(metadata.get("actor_id") or requested_by or "operator:action_worker"),
            reason=str(metadata.get("reason") or action_reason or "operator queued Stripe entitlement recovery"),
            stripe_customer_id=str(metadata.get("stripe_customer_id") or ""),
            stripe_subscription_id=str(metadata.get("stripe_subscription_id") or metadata.get("subscription_id") or ""),
            entitlement_state=str(metadata.get("entitlement_state") or "paid"),
            subscription_status=str(metadata.get("subscription_status") or "active"),
            current_period_end=str(metadata.get("current_period_end") or ""),
            dry_run=_truthy(metadata.get("dry_run")),
        )
        return {
            **recovery,
            "action": "stripe_entitlement_recovery",
            "operation_kind": "control_db_stripe_entitlement_recovery",
            "operation_idempotency_key": operation_key,
        }

    if action_type == "backup_write_check":
        if target_kind != "deployment":
            raise ArcLinkActionWorkerError("backup_write_check action requires a deployment target")
        operation_key = str(metadata.get("idempotency_key") or idempotency_key)
        _link_action_operation(
            conn,
            action_id=action_id,
            operation_kind="backup_git_write_check",
            idempotency_key=operation_key,
            target_kind=target_kind,
            target_id=target_id,
        )
        requested_activation = _truthy(metadata.get("activate_after_verify") or metadata.get("activate"))
        reason = ARCLINK_BACKUP_FAILED_CLOSED_REASON
        if requested_activation:
            reason = (
                "Backup activation requires verified private-repo write access from an authorized PG-BACKUP runner; "
                "no live git command was run."
            )
        backup_setup = record_arclink_backup_write_check_failed_closed(
            conn,
            deployment_id=target_id,
            actor_id="system:action_worker",
            reason=reason,
        )
        return {
            "status": "failed_closed",
            "action": "backup_write_check",
            "deployment_id": target_id,
            "backup_setup": backup_setup,
            "note": str(backup_setup.get("verification", {}).get("github_write_check_reason") or reason),
            "operation_kind": "backup_git_write_check",
            "operation_idempotency_key": operation_key,
        }

    if action_type == "academy_apply_preview":
        if target_kind not in {"user", "deployment"}:
            raise ArcLinkActionWorkerError("academy_apply_preview action requires a user or deployment target")
        if target_kind == "deployment":
            deployment = _deployment_row(conn, target_id)
            user_id = str(deployment["user_id"] or "").strip()
        else:
            user_id = target_id
        if not user_id:
            raise ArcLinkActionWorkerError("academy_apply_preview action could not resolve a user target")
        explicit_user = str(metadata.get("user_id") or "").strip()
        if explicit_user and explicit_user != user_id:
            raise ArcLinkActionWorkerError("academy_apply_preview metadata user_id does not match action target")
        from arclink_academy_trainer import (
            build_academy_application_preview_request,
            build_academy_application_preview_result,
        )
        from arclink_crew_recipes import crew_academy_status

        operation_key = str(metadata.get("idempotency_key") or idempotency_key or action_id)
        staged_status = crew_academy_status(conn, user_id=user_id)
        request_payload = {
            **dict(metadata),
            "request_id": action_id,
            "user_id": user_id,
            "target_kind": target_kind,
            "target_id": target_id,
            "requested_by": str(metadata.get("actor_id") or "system:action_worker"),
        }
        preview_request = build_academy_application_preview_request(
            request_payload,
            request_id=action_id,
            target_kind=target_kind,
            target_id=target_id,
            requested_at=utc_now_iso(),
            requested_by=str(metadata.get("actor_id") or "system:action_worker"),
        )
        preview = build_academy_application_preview_result(
            preview_request,
            staged_status=staged_status,
            created_at=utc_now_iso(),
        )
        result = preview.to_dict()
        _link_action_operation(
            conn,
            action_id=action_id,
            operation_kind=str(result["operation_kind"]),
            idempotency_key=operation_key,
            target_kind=target_kind,
            target_id=target_id,
        )
        event_metadata = {
            "action_id": action_id,
            "operation_kind": str(result["operation_kind"]),
            "operation_idempotency_key": operation_key,
            "recipe_id": str(result["recipe_id"]),
            "manifest_id": str(result["manifest_id"]),
            "application_plan_id": str(result["application_plan_id"]),
            "agent_id": str(result["agent_id"]),
            "proof_gates": list(result["proof_gates"]),
            "local_only": True,
            "no_write": True,
            "writes_enabled": False,
        }
        append_arclink_event(
            conn,
            subject_kind="user",
            subject_id=user_id,
            event_type="academy_application_preview_recorded",
            metadata=event_metadata,
            commit=False,
        )
        append_arclink_audit(
            conn,
            action="academy_application_preview_recorded",
            actor_id=str(metadata.get("actor_id") or "system:action_worker"),
            target_kind="user",
            target_id=user_id,
            reason="Academy application preview recorded; no Agent application was performed",
            metadata=event_metadata,
            commit=False,
        )
        return {
            **result,
            "action": "academy_apply_preview",
            "operation_idempotency_key": operation_key,
        }

    if action_type == "academy_apply":
        trainee_id = str(metadata.get("trainee_id") or "").strip()
        if not trainee_id:
            raise ArcLinkActionWorkerError("academy_apply action requires trainee_id metadata")
        from arclink_academy_programs import stage_academy_apply

        # Live Agent-home writes require a live adapter AND explicit PG-HERMES
        # authorization. Without both, the apply is recorded fail-closed.
        live_authorized = _truthy((env or os.environ).get("ARCLINK_ACADEMY_APPLY_LIVE"))
        staged_result = stage_academy_apply(
            conn,
            trainee_id=trainee_id,
            adapter_name=str(executor.config.adapter_name),
            live_authorized=live_authorized,
            actor=str(metadata.get("actor_id") or "system:action_worker"),
            created_at=utc_now_iso(),
            target_kind=target_kind,
            target_id=target_id,
        )
        result = _materialize_academy_apply(
            conn,
            result=staged_result,
            target_kind=target_kind,
            target_id=target_id,
            applied_at=utc_now_iso(),
        )
        operation_key = str(metadata.get("idempotency_key") or idempotency_key or action_id)
        _link_action_operation(
            conn,
            action_id=action_id,
            operation_kind=str(result["operation_kind"]),
            idempotency_key=operation_key,
            target_kind=target_kind,
            target_id=target_id,
        )
        event_metadata = {
            "action_id": action_id,
            "operation_kind": str(result["operation_kind"]),
            "operation_idempotency_key": operation_key,
            "trainee_id": result["trainee_id"],
            "program_id": result["program_id"],
            "manifest_id": result["manifest_id"],
            "plan_id": result["plan_id"],
            "status": result["status"],
            "writes_enabled": result["writes_enabled"],
            "intent_counts": result["intent_counts"],
            "proof_gates": result["proof_gates"],
        }
        subject_id = result["deployment_id"] or result["user_id"] or trainee_id
        subject_kind = "deployment" if result["deployment_id"] else "user"
        append_arclink_event(
            conn,
            subject_kind=subject_kind,
            subject_id=subject_id,
            event_type="academy_agent_apply_recorded",
            metadata=event_metadata,
            commit=False,
        )
        append_arclink_audit(
            conn,
            action="academy_agent_apply_recorded",
            actor_id=str(metadata.get("actor_id") or "system:action_worker"),
            target_kind=subject_kind,
            target_id=subject_id,
            reason=str(result["note"]),
            metadata=event_metadata,
            commit=False,
        )
        return {
            **result,
            "action": "academy_apply",
            "operation_idempotency_key": operation_key,
        }

    if action_type == "reprovision":
        if target_kind != "deployment":
            raise ArcLinkActionWorkerError("reprovision action requires a deployment target")
        migration_id = str(metadata.get("migration_id") or "").strip()
        if not migration_id:
            migration_id = "mig_" + hashlib.sha256(action_id.encode("utf-8")).hexdigest()[:24]
        operation_key = f"arclink:migration:{migration_id}"
        _link_action_operation(
            conn,
            action_id=action_id,
            operation_kind="pod_migration",
            idempotency_key=operation_key,
            target_kind=target_kind,
            target_id=target_id,
        )
        dry_run = _truthy(metadata.get("dry_run"))
        metadata_env = {key: str(value) for key, value in dict(metadata.get("env") or {}).items()} if isinstance(metadata.get("env"), Mapping) else {}
        migration_env = {**dict(env or os.environ), **metadata_env}
        result = migrate_pod(
            conn,
            executor=executor,
            deployment_id=target_id,
            target_machine_id=str(metadata.get("target_machine_id") or "current"),
            migration_id=migration_id,
            reason=str(metadata.get("reason") or "operator queued reprovision action"),
            dry_run=dry_run,
            env=migration_env,
        )
        if str(result.get("status") or "") != "succeeded" and not (dry_run and str(result.get("status") or "") == "planned"):
            raise ArcLinkActionWorkerError(f"reprovision migration did not succeed: {result.get('status') or 'unknown'}")
        return {
            **result,
            "action": "reprovision",
            "operation_kind": "pod_migration",
            "operation_idempotency_key": operation_key,
        }

    if action_type == "rollout":
        target_version = str(
            metadata.get("target_version")
            or metadata.get("version_tag")
            or metadata.get("target_release")
            or ""
        ).strip()
        if not target_version:
            raise ArcLinkActionWorkerError("rollout action requires target_version metadata")
        _reject_secrets(target_version, path="$.metadata.target_version")
        deployment_ids = _rollout_deployment_ids(
            target_kind=target_kind,
            target_id=target_id,
            metadata=metadata,
        )
        operation_key = str(metadata.get("idempotency_key") or idempotency_key or action_id).strip()
        if not operation_key:
            raise ArcLinkActionWorkerError("rollout action requires an operation idempotency key")
        _reject_secrets(operation_key, path="$.metadata.idempotency_key")
        rollout_env = {**dict(env or os.environ)}
        metadata_env = {key: str(value) for key, value in dict(metadata.get("env") or {}).items()} if isinstance(metadata.get("env"), Mapping) else {}
        if metadata_env:
            rollout_env.update(metadata_env)
        plan = plan_arcpod_update_rollout(
            conn,
            target_version=target_version,
            batch_size=_rollout_batch_size(metadata),
            deployment_ids=deployment_ids,
            env=rollout_env,
        )
        job = materialize_arcpod_update_rollout_job(
            conn,
            plan=plan,
            action_id=action_id,
            idempotency_key=operation_key,
            actor_id=str(metadata.get("actor_id") or "system:action_worker"),
        )
        batch_execution: dict[str, Any] | None = None
        if _truthy(metadata.get("execute_local_batch") or metadata.get("execute_batch")):
            execution_results = metadata.get("rollout_execution_results", {})
            if execution_results and not isinstance(execution_results, Mapping):
                raise ArcLinkActionWorkerError("rollout_execution_results metadata must be an object")
            batch_execution = execute_arcpod_update_rollout_batch(
                conn,
                rollout_group_id=str(job["rollout_group_id"]),
                batch_index=_rollout_execution_batch_index(metadata),
                executor={
                    "adapter": str(executor.config.adapter_name),
                    "record_only": True,
                    "results": dict(execution_results) if isinstance(execution_results, Mapping) else {},
                },
                actor_id=str(metadata.get("actor_id") or "system:action_worker"),
            )
        _link_action_operation(
            conn,
            action_id=action_id,
            operation_kind="arcpod_update_rollout",
            idempotency_key=operation_key,
            target_kind=target_kind,
            target_id=target_id,
        )
        result = {
            **job,
            "action": "rollout",
            "operation_kind": "arcpod_update_rollout",
            "operation_idempotency_key": operation_key,
        }
        if batch_execution is not None:
            result.update(
                {
                    "status": "executed_local_batch",
                    "batch_execution": batch_execution,
                    "execution": {
                        "enabled": True,
                        "reason": "explicit execute_local_batch requested; one fake/local rollout batch was recorded only",
                        "adapter": str(executor.config.adapter_name),
                        "record_only": True,
                    },
                }
            )
            # An upgraded Pod can carry a changed Hermes command registry, so
            # re-push the active-chat Telegram command scope for the rolled
            # Pods. Best-effort: menu refresh must never fail the rollout.
            try:
                from arclink_public_bot_commands import refresh_active_telegram_command_scopes

                result["telegram_command_scope_refresh"] = refresh_active_telegram_command_scopes(
                    rollout_env,
                    deployment_ids=deployment_ids or None,
                )
            except Exception as exc:  # noqa: BLE001 - rollout truth already recorded
                result["telegram_command_scope_refresh"] = {
                    "skipped": True,
                    "reason": f"refresh_failed: {str(exc)[:160]}",
                }
            # Discord's application-command list mirrors the Hermes inventory,
            # so re-register it after a rollout when credentials are present.
            try:
                from arclink_discord import DiscordConfig, register_arclink_public_discord_commands

                discord_config = DiscordConfig.from_env(rollout_env)
                if discord_config.bot_token and discord_config.app_id:
                    result["discord_command_refresh"] = register_arclink_public_discord_commands(discord_config)
                else:
                    result["discord_command_refresh"] = {"skipped": True, "reason": "discord_not_configured"}
            except Exception as exc:  # noqa: BLE001 - rollout truth already recorded
                result["discord_command_refresh"] = {
                    "skipped": True,
                    "reason": f"refresh_failed: {str(exc)[:160]}",
                }
        return result

    raise ArcLinkActionWorkerError(f"unsupported action type: {action_type}")


def _link_action_operation(
    conn: sqlite3.Connection,
    *,
    action_id: str,
    operation_kind: str,
    idempotency_key: str,
    target_kind: str,
    target_id: str,
) -> None:
    if not str(idempotency_key or "").strip():
        return
    link_arclink_action_operation(
        conn,
        action_id=action_id,
        operation_kind=operation_kind,
        idempotency_key=idempotency_key,
        target_kind=target_kind,
        target_id=target_id,
    )


def _deployment_lifecycle_metadata(conn: sqlite3.Connection, *, deployment_id: str) -> dict[str, str]:
    row = conn.execute(
        "SELECT deployment_id, prefix, metadata_json FROM arclink_deployments WHERE deployment_id = ?",
        (str(deployment_id or "").strip(),),
    ).fetchone()
    if row is None:
        return {}
    deployment = dict(row)
    metadata = json_loads_safe(str(deployment.get("metadata_json") or "{}"))
    raw_roots = metadata.get("state_roots")
    if isinstance(raw_roots, Mapping):
        roots = {str(key): str(value) for key, value in raw_roots.items() if str(value or "").strip()}
    else:
        roots = {}
    if not roots.get("root") or not roots.get("config"):
        roots = render_arclink_state_roots(
            deployment_id=str(deployment.get("deployment_id") or deployment_id),
            prefix=str(deployment.get("prefix") or ""),
            state_root_base=str(metadata.get("state_root_base") or os.environ.get("ARCLINK_STATE_ROOT_BASE") or "/arcdata/deployments"),
        )
    config_root = Path(str(roots["config"]))
    return {
        "env_file": str(config_root / "arclink.env"),
        "compose_file": str(config_root / "compose.yaml"),
    }


def _safe_child_path(path: str, root: Path, *, label: str) -> Path:
    candidate = Path(str(path or "")).expanduser()
    if not candidate.is_absolute():
        raise ArcLinkActionWorkerError(f"Academy apply {label} path must be absolute")
    resolved = candidate.resolve(strict=False)
    resolved_root = root.resolve(strict=False)
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ArcLinkActionWorkerError(f"Academy apply {label} path is outside deployment state root")
    return resolved


def _deployment_academy_roots(conn: sqlite3.Connection, *, deployment_id: str) -> dict[str, Path]:
    row = _deployment_row(conn, deployment_id)
    metadata = json_loads_safe(str(row["metadata_json"] or "{}"))
    raw_roots = metadata.get("state_roots")
    if isinstance(raw_roots, Mapping):
        roots = {str(key): str(value) for key, value in raw_roots.items() if str(value or "").strip()}
    else:
        roots = {}
    if not roots.get("root") or not roots.get("hermes_home") or not roots.get("vault"):
        roots = render_arclink_state_roots(
            deployment_id=str(row["deployment_id"] or deployment_id),
            prefix=str(row["prefix"] or ""),
            state_root_base=str(metadata.get("state_root_base") or os.environ.get("ARCLINK_STATE_ROOT_BASE") or "/arcdata/deployments"),
        )
    root = Path(str(roots["root"])).expanduser().resolve(strict=False)
    return {
        "root": root,
        "hermes_home": _safe_child_path(str(roots.get("hermes_home") or ""), root, label="Hermes home"),
        "vault": _safe_child_path(str(roots.get("vault") or ""), root, label="vault"),
    }


def _write_private_text_atomic(path: Path, body: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = ""
    try:
        existing = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        existing = ""
    if existing == body:
        try:
            os.chmod(path, 0o600)
        except FileNotFoundError:
            pass
        return False
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
    return True


def _academy_safe_relative_path(value: Any, *, fallback: str) -> Path:
    raw = str(value or fallback).strip() or fallback
    candidate = Path(raw)
    if candidate.is_absolute():
        raise ArcLinkActionWorkerError("Academy apply intent path must be relative")
    parts = []
    for part in candidate.parts:
        clean = str(part or "").strip()
        if clean in {"", ".", ".."}:
            raise ArcLinkActionWorkerError("Academy apply intent path must stay inside the Academy vault folder")
        parts.append(clean)
    if not parts:
        parts = [fallback]
    return Path(*parts)


def _academy_slug(value: Any, *, fallback: str = "academy-specialist") -> str:
    clean = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value or "").strip())
    clean = "-".join(part for part in clean.split("-") if part)
    return clean[:80] or fallback


def _academy_markdown_list(title: str, values: Any) -> str:
    items = [str(item or "").strip() for item in (values or []) if str(item or "").strip()]
    if not items:
        return f"## {title}\n\n- None staged.\n"
    return "## " + title + "\n\n" + "\n".join(f"- {item}" for item in items) + "\n"


def _academy_vault_body(intent: Mapping[str, Any], *, payload: Mapping[str, Any], applied_at: str) -> str:
    path = str(intent.get("path") or "")
    name = Path(path).name.lower()
    header = [
        "# ArcLink Academy",
        "",
        f"- Applied: {applied_at}",
        f"- Program: {payload.get('program_id') or 'unknown'}",
        f"- Trainee: {payload.get('trainee_id') or 'unknown'}",
        f"- Manifest: {payload.get('manifest_id') or 'unknown'}",
        f"- Plan: {payload.get('plan_id') or 'unknown'}",
        f"- Specialist: {payload.get('academy_specialist_uid') or 'unknown'}",
        "",
    ]
    if name == "curriculum.md":
        return "\n".join(header) + _academy_markdown_list("First Week Practice", payload.get("first_week_practice_tasks")) + "\n" + _academy_markdown_list("Evaluation", payload.get("evaluation_tasks"))
    if name == "source_map.md":
        return (
            "\n".join(header)
            + _academy_markdown_list("Proof Gates", payload.get("proof_gates"))
            + "\n"
            + f"## Source Count\n\n- {intent.get('source_count') or payload.get('intent_counts', {}).get('vault_file_intents') or 0}\n"
        )
    if str(intent.get("source_id") or "").strip():
        return (
            "\n".join(header)
            + f"## Lesson Card\n\n- Source id: {str(intent.get('source_id') or '').strip()}\n"
            + "- Retrieval posture: search and cite Academy/vault sources before specialist answers.\n"
        )
    return (
        "\n".join(header)
        + "## Canon\n\nThis folder contains the Captain-approved, Trainer-reviewed Academy specialist package for this Hermes Agent.\n"
        + "\n"
        + _academy_markdown_list("First Week Practice", payload.get("first_week_practice_tasks"))
    )


def _academy_post_apply_refresh_request(
    *,
    payload: Mapping[str, Any],
    deployment_id: str,
    applied_at: str,
    applied_paths: list[str],
    qmd_memory_seed_intents: list[dict[str, Any]],
    approved_skill_intents: list[dict[str, Any]],
) -> dict[str, Any]:
    request_seed = "|".join(
        (
            deployment_id,
            str(payload.get("trainee_id") or ""),
            str(payload.get("program_id") or ""),
            str(payload.get("manifest_id") or ""),
            str(payload.get("academy_capsule_version") or ""),
            applied_at,
        )
    )
    request_id = "academy_refresh_" + hashlib.sha256(request_seed.encode("utf-8")).hexdigest()[:24]
    return {
        "request_id": request_id,
        "requested_at": applied_at,
        "deployment_id": deployment_id,
        "trainee_id": str(payload.get("trainee_id") or ""),
        "program_id": str(payload.get("program_id") or ""),
        "manifest_id": str(payload.get("manifest_id") or ""),
        "academy_specialist_uid": str(payload.get("academy_specialist_uid") or ""),
        "academy_capsule_version": int(payload.get("academy_capsule_version") or 0),
        "status": "requested",
        "queue_policy": "post-apply handoff only; the action worker does not run qmd, memory synthesis, Hermes skill enablement, Docker, SSH, or provider commands inline",
        "refreshes": [
            {
                "kind": "qmd_index",
                "status": "requested",
                "reason": "Vault/Academy markdown changed and should be discoverable through qmd retrieval.",
                "proof_gate": "PG-HERMES",
            },
            {
                "kind": "memory_synthesis",
                "status": "requested" if qmd_memory_seed_intents else "not_requested",
                "reason": "Academy memory seeds were staged for recall-stub synthesis." if qmd_memory_seed_intents else "No Academy memory seed intents were staged.",
                "proof_gate": "PG-HERMES",
                "seed_count": len(qmd_memory_seed_intents),
            },
            {
                "kind": "skill_activation",
                "status": "staged" if approved_skill_intents else "not_requested",
                "reason": "Approved Academy skills were recorded; activation stays explicit and proof-gated." if approved_skill_intents else "No approved skill intents were staged.",
                "proof_gate": "PG-HERMES",
                "skill_count": len(approved_skill_intents),
            },
        ],
        "applied_paths": list(applied_paths),
    }


def _academy_refresh_handoff_path(roots: Mapping[str, Path]) -> Path:
    return Path(roots["hermes_home"]) / "state" / "arclink-academy-post-apply-refresh.json"


def _academy_resolve_refresh_applied_path(roots: Mapping[str, Path], raw_path: str) -> Path:
    clean = str(raw_path or "").strip()
    if not clean:
        raise ArcLinkActionWorkerError("Academy post-apply refresh path is blank")
    candidate = Path(clean)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ArcLinkActionWorkerError(f"Academy post-apply refresh path is unsafe: {clean}")
    if clean == "SOUL.md":
        root = Path(roots["hermes_home"])
        relative = Path("SOUL.md")
    elif candidate.parts and candidate.parts[0] == "vault":
        root = Path(roots["vault"])
        relative = Path(*candidate.parts[1:]) if len(candidate.parts) > 1 else Path()
    elif candidate.parts and candidate.parts[0] == "state":
        root = Path(roots["hermes_home"]) / "state"
        relative = Path(*candidate.parts[1:]) if len(candidate.parts) > 1 else Path()
    else:
        raise ArcLinkActionWorkerError(f"Academy post-apply refresh path has no supported root: {clean}")
    if not relative.parts:
        raise ArcLinkActionWorkerError(f"Academy post-apply refresh path has no file component: {clean}")
    resolved = (root / relative).resolve(strict=False)
    resolved_root = root.resolve(strict=False)
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ArcLinkActionWorkerError(f"Academy post-apply refresh path escapes deployment root: {clean}")
    return resolved


def _academy_refresh_runner_payload(
    *,
    deployment_id: str,
    kind: str,
    roots: Mapping[str, Path],
    request: Mapping[str, Any],
    existing_paths: list[str],
) -> dict[str, Any]:
    return {
        "deployment_id": deployment_id,
        "kind": kind,
        "request_id": str(request.get("request_id") or ""),
        "trainee_id": str(request.get("trainee_id") or ""),
        "program_id": str(request.get("program_id") or ""),
        "manifest_id": str(request.get("manifest_id") or ""),
        "academy_specialist_uid": str(request.get("academy_specialist_uid") or ""),
        "hermes_home": str(roots["hermes_home"]),
        "vault": str(roots["vault"]),
        "state": str(Path(roots["hermes_home"]) / "state"),
        "applied_paths": list(existing_paths),
    }


def _academy_run_refresh_kind(
    *,
    refresh: Mapping[str, Any],
    runner: AcademyPostApplyRunner | None,
    payload: Mapping[str, Any],
    blocked: bool,
) -> dict[str, Any]:
    item = dict(refresh)
    kind = str(item.get("kind") or "unknown")
    current_status = str(item.get("status") or "requested")
    if current_status in {"not_requested", "succeeded"}:
        return item
    if blocked:
        item["status"] = "blocked"
        item["last_error"] = "Applied path validation failed; refresh runner was not invoked."
        return item
    if runner is None and current_status == "queued":
        item["last_error"] = ""
        return item
    if kind == "skill_activation" and int(item.get("skill_count") or 0) > 0:
        state_path = Path(str(payload.get("state") or "")) / "arclink-academy-approved-skills.json"
        if not state_path.is_file():
            item["status"] = "blocked"
            item["last_error"] = "Approved skill state file is missing; activation runner was not invoked."
            return item
        if current_status == "staged" and runner is None:
            item["last_error"] = ""
            item["runner_result"] = {
                "status": "staged",
                "summary": "Approved skills remain staged until an explicit PG-HERMES activation runner is supplied.",
            }
            return item
    if runner is None:
        item["status"] = "validated_pending_runner"
        item["last_error"] = ""
        return item
    try:
        result = runner(payload)
    except Exception as exc:  # noqa: BLE001 - runner errors must be recorded safely.
        item["status"] = "failed"
        item["last_error"] = _safe_error_message(exc)
        return item
    result_map = dict(result or {})
    item["status"] = str(result_map.get("status") or "succeeded")
    item["last_error"] = redact_then_truncate(str(result_map.get("last_error") or ""), limit=240)
    runner_result: dict[str, Any] = {}
    for key in ("status", "summary", "changed", "proof"):
        if key not in result_map:
            continue
        value = result_map[key]
        runner_result[key] = redact_then_truncate(value, limit=240) if isinstance(value, str) else value
    for key in ("verified_skills", "missing_skills"):
        if key not in result_map:
            continue
        values = result_map[key]
        if isinstance(values, (list, tuple)):
            runner_result[key] = [redact_then_truncate(str(value), limit=120) for value in values][:50]
    item["runner_result"] = runner_result
    return item


def run_academy_post_apply_refresh(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    qmd_runner: AcademyPostApplyRunner | None = None,
    memory_runner: AcademyPostApplyRunner | None = None,
    skill_runner: AcademyPostApplyRunner | None = None,
    requested_by: str = "system:academy_post_apply_refresh",
) -> dict[str, Any]:
    """Consume and validate a deployment's Academy post-apply refresh handoff.

    Runners are injectable proof hooks. Without runners this validates the
    handoff and records ``validated_pending_runner`` refresh items for active
    refreshes. Callers that materialize Academy canon should pass queue runners
    so qmd and memory work have durable out-of-band handoff markers; the action
    worker still does not run qmd, memory synthesis, Hermes skill activation,
    Docker, SSH, or provider calls inline.
    """
    clean_deployment = str(deployment_id or "").strip()
    if not clean_deployment:
        raise ArcLinkActionWorkerError("Academy post-apply refresh requires a deployment id")
    roots = _deployment_academy_roots(conn, deployment_id=clean_deployment)
    refresh_path = _academy_refresh_handoff_path(roots)
    try:
        request = json.loads(refresh_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ArcLinkActionWorkerError("Academy post-apply refresh handoff is missing") from exc
    except json.JSONDecodeError as exc:
        raise ArcLinkActionWorkerError("Academy post-apply refresh handoff is invalid JSON") from exc
    if not isinstance(request, dict):
        raise ArcLinkActionWorkerError("Academy post-apply refresh handoff must be a JSON object")
    if str(request.get("deployment_id") or "").strip() != clean_deployment:
        raise ArcLinkActionWorkerError("Academy post-apply refresh handoff deployment mismatch")

    applied_paths = [str(item or "").strip() for item in (request.get("applied_paths") or []) if str(item or "").strip()]
    verified_paths: list[str] = []
    missing_paths: list[str] = []
    for raw_path in applied_paths:
        resolved = _academy_resolve_refresh_applied_path(roots, raw_path)
        if resolved.is_file():
            verified_paths.append(raw_path)
        else:
            missing_paths.append(raw_path)
    blocked = bool(missing_paths)
    runner_payload = _academy_refresh_runner_payload(
        deployment_id=clean_deployment,
        kind="",
        roots=roots,
        request=request,
        existing_paths=verified_paths,
    )
    runner_by_kind = {
        "qmd_index": qmd_runner,
        "memory_synthesis": memory_runner,
        "skill_activation": skill_runner,
    }
    refreshes = []
    for refresh in [item for item in (request.get("refreshes") or []) if isinstance(item, Mapping)]:
        kind = str(refresh.get("kind") or "unknown")
        payload = {**runner_payload, "kind": kind}
        refreshes.append(
            _academy_run_refresh_kind(
                refresh=refresh,
                runner=runner_by_kind.get(kind),
                payload=payload,
                blocked=blocked,
            )
        )
    statuses = {str(item.get("status") or "") for item in refreshes}
    if statuses & {"failed", "blocked"} or blocked:
        status = "blocked"
    elif statuses and statuses <= {"succeeded", "not_requested"}:
        status = "succeeded"
    elif statuses & {"queued", "staged"}:
        status = "queued"
    else:
        status = "validated"
    consumed_at = utc_now_iso()
    updated_request = {
        **request,
        "status": status,
        "consumed_at": consumed_at,
        "consumed_by": requested_by,
        "verified_paths": verified_paths,
        "missing_paths": missing_paths,
        "refreshes": refreshes,
    }
    _write_private_text_atomic(refresh_path, json.dumps(updated_request, indent=2, sort_keys=True) + "\n")
    note_refresh_job(
        conn,
        job_name=f"academy-post-apply-refresh:{clean_deployment}",
        job_kind="academy-post-apply",
        target_id=clean_deployment,
        schedule="on demand after academy_apply",
        status=status,
        note=(
            f"Academy post-apply refresh {status}: {request.get('request_id') or 'unknown'}; "
            f"verified_paths={len(verified_paths)} missing_paths={len(missing_paths)}"
        ),
    )
    append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=clean_deployment,
        event_type="academy_post_apply_refresh_consumed",
        metadata={
            "request_id": str(request.get("request_id") or ""),
            "status": status,
            "verified_paths": len(verified_paths),
            "missing_paths": len(missing_paths),
        },
        commit=False,
    )
    append_arclink_audit(
        conn,
        action="academy_post_apply_refresh_consumed",
        actor_id=requested_by,
        target_kind="deployment",
        target_id=clean_deployment,
        reason="Academy post-apply refresh handoff consumed through validated runner hooks",
        metadata={
            "request_id": str(request.get("request_id") or ""),
            "status": status,
            "refresh_statuses": [str(item.get("status") or "") for item in refreshes],
            "missing_paths": missing_paths,
        },
        commit=False,
    )
    conn.commit()
    return {
        "status": status,
        "request_id": str(request.get("request_id") or ""),
        "deployment_id": clean_deployment,
        "verified_paths": verified_paths,
        "missing_paths": missing_paths,
        "refreshes": refreshes,
        "handoff_path": str(refresh_path),
        "live_execution_performed": bool(qmd_runner or memory_runner or skill_runner),
    }


def _academy_durable_refresh_queue_runner(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Record a durable post-apply queue marker for timer/worker refresh lanes."""
    kind = str(payload.get("kind") or "").strip()
    marker_by_kind = {
        "qmd_index": "arclink-academy-qmd-refresh-request.json",
        "memory_synthesis": "arclink-academy-memory-synthesis-request.json",
    }
    marker_name = marker_by_kind.get(kind)
    if not marker_name:
        raise ArcLinkActionWorkerError(f"Academy post-apply queue marker does not support refresh kind: {kind or 'unknown'}")
    state_dir = Path(str(payload.get("state") or ""))
    if not str(state_dir).strip():
        raise ArcLinkActionWorkerError("Academy post-apply queue marker requires a state directory")
    marker = state_dir / marker_name
    queued_at = utc_now_iso()
    consumer_by_kind = {
        # memory_synthesis markers are consumed automatically: every completed
        # memory-synth run calls consume_academy_refresh_queue_markers_for_all.
        "memory_synthesis": "memory-synth run completion (consume_academy_refresh_queue_markers)",
        # qmd_index markers stay runner-gated: the standing qmd refresh lane
        # (5-15 min) reindexes the applied vault markdown regardless, but it
        # runs in bash without control-DB access, so consumption requires a
        # caller to supply lane evidence to consume_academy_refresh_queue_markers.
        "qmd_index": "runner-gated: consume_academy_refresh_queue_markers with explicit lane evidence",
    }
    marker_payload = {
        "status": "queued",
        "queued_at": queued_at,
        "request_id": str(payload.get("request_id") or ""),
        "deployment_id": str(payload.get("deployment_id") or ""),
        "kind": kind,
        "trainee_id": str(payload.get("trainee_id") or ""),
        "program_id": str(payload.get("program_id") or ""),
        "manifest_id": str(payload.get("manifest_id") or ""),
        "academy_specialist_uid": str(payload.get("academy_specialist_uid") or ""),
        "applied_paths": list(payload.get("applied_paths") or []),
        "consumer": consumer_by_kind.get(kind, ""),
        "runner_gated": kind == "qmd_index",
    }
    changed = _write_private_text_atomic(marker, json.dumps(marker_payload, indent=2, sort_keys=True) + "\n")
    return {
        "status": "queued",
        "summary": (
            f"Academy {kind} refresh marker queued for the deployment refresh/timer lane; "
            f"consumer: {consumer_by_kind.get(kind, 'unspecified')}."
        ),
        "changed": changed,
        "proof": marker.name,
    }


_ACADEMY_REFRESH_MARKER_BY_KIND = {
    "qmd_index": "arclink-academy-qmd-refresh-request.json",
    "memory_synthesis": "arclink-academy-memory-synthesis-request.json",
}


def consume_academy_refresh_queue_markers(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    lane_evidence: Mapping[str, str] | None = None,
    consumed_by: str = "system:academy_refresh_marker_consumer",
) -> dict[str, Any]:
    """Transition queued Academy refresh markers once their lane has run.

    ``lane_evidence`` maps refresh kind -> ISO timestamp of a completed lane
    run. For ``memory_synthesis`` the evidence defaults to the control-plane
    ``refresh_jobs`` record written by every memory-synth run. ``qmd_index``
    has no default evidence (the qmd refresh lane is bash-only with no DB
    writes), so those markers stay queued/runner-gated unless the caller
    supplies evidence. Markers whose lane completed after queued_at move to
    ``consumed``; everything else is reported untouched.
    """
    from arclink_control import parse_utc_iso

    clean_deployment = str(deployment_id or "").strip()
    if not clean_deployment:
        raise ArcLinkActionWorkerError("Academy refresh marker consumption requires a deployment id")
    roots = _deployment_academy_roots(conn, deployment_id=clean_deployment)
    state_dir = Path(roots["hermes_home"]) / "state"
    evidence = {str(key): str(value or "") for key, value in dict(lane_evidence or {}).items()}
    if "memory_synthesis" not in evidence:
        job_row = conn.execute(
            "SELECT last_run_at, last_status FROM refresh_jobs WHERE job_name = 'memory-synth'"
        ).fetchone()
        if job_row is not None and str(job_row["last_status"] or "") in {"ok", "warn"}:
            evidence["memory_synthesis"] = str(job_row["last_run_at"] or "")
    markers: list[dict[str, Any]] = []
    consumed = 0
    for kind, marker_name in _ACADEMY_REFRESH_MARKER_BY_KIND.items():
        marker_path = state_dir / marker_name
        try:
            payload = json.loads(marker_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except json.JSONDecodeError:
            markers.append({"kind": kind, "status": "invalid", "marker": marker_name})
            continue
        if not isinstance(payload, dict):
            markers.append({"kind": kind, "status": "invalid", "marker": marker_name})
            continue
        current_status = str(payload.get("status") or "")
        if current_status != "queued":
            markers.append({"kind": kind, "status": current_status, "marker": marker_name})
            continue
        completed_at = str(evidence.get(kind) or "").strip()
        queued_at = parse_utc_iso(str(payload.get("queued_at") or ""))
        completed = parse_utc_iso(completed_at)
        if not completed_at or completed is None or (queued_at is not None and completed < queued_at):
            markers.append(
                {
                    "kind": kind,
                    "status": "queued",
                    "marker": marker_name,
                    "note": "no lane completion evidence after queued_at yet",
                }
            )
            continue
        payload.update(
            {
                "status": "consumed",
                "consumed_at": utc_now_iso(),
                "consumed_by": str(consumed_by or "").strip(),
                "lane_completed_at": completed_at,
            }
        )
        _write_private_text_atomic(marker_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        consumed += 1
        markers.append({"kind": kind, "status": "consumed", "marker": marker_name})
    if consumed:
        note_refresh_job(
            conn,
            job_name=f"academy-refresh-markers:{clean_deployment}",
            job_kind="academy-post-apply",
            target_id=clean_deployment,
            schedule="on lane completion",
            status="ok",
            note=f"consumed {consumed} Academy refresh marker(s) via {consumed_by}",
        )
    return {
        "deployment_id": clean_deployment,
        "consumed": consumed,
        "markers": markers,
    }


def consume_academy_refresh_queue_markers_for_all(
    conn: sqlite3.Connection,
    *,
    kind: str,
    lane_completed_at: str,
    consumed_by: str = "system:academy_refresh_marker_consumer",
) -> dict[str, Any]:
    """Consume queued markers of one kind across all deployments.

    Called by lane owners on completion (memory-synth run_once). Deployments
    without the marker file are skipped cheaply; per-deployment errors are
    recorded instead of raised so one bad deployment row cannot wedge a lane.
    """
    clean_kind = str(kind or "").strip()
    if clean_kind not in _ACADEMY_REFRESH_MARKER_BY_KIND:
        raise ArcLinkActionWorkerError(f"Academy refresh marker consumption does not support kind: {clean_kind or 'unknown'}")
    rows = conn.execute(
        "SELECT deployment_id FROM arclink_deployments ORDER BY deployment_id ASC"
    ).fetchall()
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    consumed = 0
    for row in rows:
        deployment_id = str(row["deployment_id"] or "").strip()
        if not deployment_id:
            continue
        try:
            roots = _deployment_academy_roots(conn, deployment_id=deployment_id)
        except Exception:  # noqa: BLE001 - skip deployments without resolvable roots.
            continue
        marker_path = Path(roots["hermes_home"]) / "state" / _ACADEMY_REFRESH_MARKER_BY_KIND[clean_kind]
        if not marker_path.is_file():
            continue
        try:
            result = consume_academy_refresh_queue_markers(
                conn,
                deployment_id=deployment_id,
                lane_evidence={clean_kind: str(lane_completed_at or "")},
                consumed_by=consumed_by,
            )
        except Exception as exc:  # noqa: BLE001 - keep the lane moving.
            errors.append(f"{deployment_id}: {_safe_error_message(exc)}")
            continue
        consumed += int(result.get("consumed") or 0)
        results.append(result)
    return {
        "ok": not errors,
        "kind": clean_kind,
        "consumed": consumed,
        "deployments": [str(item.get("deployment_id") or "") for item in results],
        "errors": errors[:8],
    }


def _academy_skill_enablement_runner(
    conn: sqlite3.Connection,
    *,
    approved_skill_intents: list[dict[str, Any]],
) -> AcademyPostApplyRunner:
    """Real skill_activation refresh runner for academy_apply.

    Records each Trainer-approved skill intent as an enablement row in the
    central arclink_agent_skill_enablement registry (source academy:<slug>,
    status approved) and reports verified/missing skill ids instead of
    raising. The per-agent refresh lane applies approved rows; actual Hermes
    skill activation stays out-of-band and PG-HERMES gated.
    """

    def _runner(payload: Mapping[str, Any]) -> dict[str, Any]:
        from arclink_control import record_agent_skill_enablement_intent

        deployment_id = str(payload.get("deployment_id") or "").strip()
        if not deployment_id:
            return {
                "status": "blocked",
                "summary": "Skill enablement intents require a deployment id.",
                "last_error": "missing deployment id in skill activation payload",
            }
        program_slug = _academy_slug(
            payload.get("program_id") or payload.get("academy_specialist_uid") or payload.get("trainee_id")
        )
        source = f"academy:{program_slug}"
        verified: list[str] = []
        missing: list[str] = []
        for intent in approved_skill_intents:
            skill_id = str(intent.get("skill_id") or intent.get("source_id") or "").strip()
            if not skill_id:
                missing.append(str(intent.get("source_id") or "unknown"))
                continue
            provenance_hash = hashlib.sha256(
                json.dumps(intent, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()
            record_agent_skill_enablement_intent(
                conn,
                deployment_id=deployment_id,
                skill_id=skill_id,
                source=source,
                status="approved",
                provenance_hash=provenance_hash,
                requested_by=str(payload.get("request_id") or "system:academy_apply"),
                metadata={
                    "source_id": str(intent.get("source_id") or ""),
                    "review_status": str(intent.get("review_status") or ""),
                    "tool_recipes": [str(item or "") for item in (intent.get("tool_recipes") or [])],
                    "trainee_id": str(payload.get("trainee_id") or ""),
                    "program_id": str(payload.get("program_id") or ""),
                    "manifest_id": str(payload.get("manifest_id") or ""),
                    "effective_at": "next_session",
                },
            )
            verified.append(skill_id)
        return {
            "status": "recorded",
            "summary": (
                f"{len(verified)} approved skill enablement intent(s) recorded in "
                f"arclink_agent_skill_enablement (source {source}); "
                f"{len(missing)} intent(s) missing a skill id. The per-agent refresh lane "
                "applies enablement; skills enter the Hermes prompt index at next session start."
            ),
            "changed": bool(verified),
            "proof": "arclink_agent_skill_enablement",
            "verified_skills": verified,
            "missing_skills": missing,
        }

    return _runner


def _materialize_academy_apply(
    conn: sqlite3.Connection,
    *,
    result: Mapping[str, Any],
    target_kind: str,
    target_id: str,
    applied_at: str,
) -> dict[str, Any]:
    payload = dict(result)
    if not payload.get("writes_enabled"):
        return payload
    deployment_id = str(payload.get("deployment_id") or (target_id if target_kind == "deployment" else "")).strip()
    if not deployment_id:
        raise ArcLinkActionWorkerError("academy_apply requires a deployment target for live Hermes-home materialization")
    section = str(payload.get("academy_soul_section") or "").strip()
    if not section:
        raise ArcLinkActionWorkerError("academy_apply has no Trainer-reviewed Academy SOUL section to materialize")
    roots = _deployment_academy_roots(conn, deployment_id=deployment_id)
    hermes_home = roots["hermes_home"]
    from arclink_org_profile import merge_academy_overlay

    soul_path = hermes_home / "SOUL.md"
    try:
        existing_soul = soul_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        existing_soul = ""
    soul_changed = _write_private_text_atomic(soul_path, merge_academy_overlay(existing_soul, section))
    applied_paths = ["SOUL.md"]
    changed_any = bool(soul_changed)
    vault_file_intents = [dict(item) for item in (payload.get("vault_file_intents") or []) if isinstance(item, Mapping)]
    qmd_memory_seed_intents = [dict(item) for item in (payload.get("qmd_memory_seed_intents") or []) if isinstance(item, Mapping)]
    approved_skill_intents = [dict(item) for item in (payload.get("approved_skill_intents") or []) if isinstance(item, Mapping)]
    academy_base = _academy_slug(payload.get("program_id") or payload.get("academy_specialist_uid") or payload.get("trainee_id"))
    vault = roots["vault"]
    for index, intent in enumerate(vault_file_intents, start=1):
        relative = _academy_safe_relative_path(intent.get("path"), fallback=f"Academy/{academy_base}/Intent_{index}.md")
        path = vault / relative
        changed = _write_private_text_atomic(path, _academy_vault_body(intent, payload=payload, applied_at=applied_at))
        changed_any = changed_any or changed
        applied_paths.append(str(Path("vault") / relative))
    if qmd_memory_seed_intents:
        memory_relative = Path("Academy") / academy_base / "Memory_Seeds.md"
        memory_body = (
            "# ArcLink Academy Memory Seeds\n\n"
            + f"- Applied: {applied_at}\n"
            + f"- Program: {payload.get('program_id') or 'unknown'}\n\n"
            + "\n".join(
                f"- {str(item.get('lesson_card_id') or item.get('source_id') or 'seed').strip()}: {str(item.get('text') or item.get('note') or '').strip()}"
                for item in qmd_memory_seed_intents
            )
            + "\n"
        )
        changed = _write_private_text_atomic(vault / memory_relative, memory_body)
        changed_any = changed_any or changed
        applied_paths.append(str(Path("vault") / memory_relative))
    if approved_skill_intents:
        skills_relative = Path("Academy") / academy_base / "Approved_Skills.md"
        skills_body = (
            "# ArcLink Academy Approved Skills\n\n"
            + f"- Applied: {applied_at}\n"
            + f"- Program: {payload.get('program_id') or 'unknown'}\n\n"
            + "\n".join(
                f"- {str(item.get('skill_id') or item.get('source_id') or 'skill').strip()} ({str(item.get('review_status') or 'reviewed').strip()})"
                for item in approved_skill_intents
            )
            + "\n"
        )
        changed = _write_private_text_atomic(vault / skills_relative, skills_body)
        changed_any = changed_any or changed
        applied_paths.append(str(Path("vault") / skills_relative))
    state_payload = {
        "applied_at": applied_at,
        "deployment_id": deployment_id,
        "trainee_id": str(payload.get("trainee_id") or ""),
        "program_id": str(payload.get("program_id") or ""),
        "manifest_id": str(payload.get("manifest_id") or ""),
        "plan_id": str(payload.get("plan_id") or ""),
        "academy_specialist_uid": str(payload.get("academy_specialist_uid") or ""),
        "academy_capsule_version": int(payload.get("academy_capsule_version") or 0),
        "academy_trainer_review_ready": bool(payload.get("academy_trainer_review_ready")),
        "academy_trainer_reviewed_at": str(payload.get("academy_trainer_reviewed_at") or ""),
        "academy_trainer_live_status": str(payload.get("academy_trainer_live_status") or ""),
        "intent_counts": dict(payload.get("intent_counts") or {}),
        "vault_file_intents": vault_file_intents,
        "qmd_memory_seed_intents": qmd_memory_seed_intents,
        "approved_skill_intents": approved_skill_intents,
        "first_week_practice_tasks": list(payload.get("first_week_practice_tasks") or []),
        "evaluation_tasks": list(payload.get("evaluation_tasks") or []),
        "applied_paths": applied_paths,
    }
    applied_paths.append("state/arclink-academy-apply.json")
    if qmd_memory_seed_intents:
        seeds_changed = _write_private_text_atomic(
            hermes_home / "state" / "arclink-academy-memory-seeds.json",
            json.dumps(qmd_memory_seed_intents, indent=2, sort_keys=True) + "\n",
        )
        changed_any = changed_any or seeds_changed
        applied_paths.append("state/arclink-academy-memory-seeds.json")
    if approved_skill_intents:
        skills_changed = _write_private_text_atomic(
            hermes_home / "state" / "arclink-academy-approved-skills.json",
            json.dumps(approved_skill_intents, indent=2, sort_keys=True) + "\n",
        )
        changed_any = changed_any or skills_changed
        applied_paths.append("state/arclink-academy-approved-skills.json")
    refresh_request = _academy_post_apply_refresh_request(
        payload=payload,
        deployment_id=deployment_id,
        applied_at=applied_at,
        applied_paths=applied_paths,
        qmd_memory_seed_intents=qmd_memory_seed_intents,
        approved_skill_intents=approved_skill_intents,
    )
    refresh_changed = _write_private_text_atomic(
        hermes_home / "state" / "arclink-academy-post-apply-refresh.json",
        json.dumps(refresh_request, indent=2, sort_keys=True) + "\n",
    )
    changed_any = changed_any or refresh_changed
    applied_paths.append("state/arclink-academy-post-apply-refresh.json")
    note_refresh_job(
        conn,
        job_name=f"academy-post-apply-refresh:{deployment_id}",
        job_kind="academy-post-apply",
        target_id=deployment_id,
        schedule="on demand after academy_apply",
        status="warn",
        note=(
            f"Academy post-apply refresh requested: {refresh_request['request_id']} "
            "(qmd index, memory synthesis, and skill activation proof stay out-of-band)."
        ),
    )
    state_payload["post_apply_refresh_request"] = refresh_request
    state_body = json.dumps(
        state_payload,
        indent=2,
        sort_keys=True,
    ) + "\n"
    state_changed = _write_private_text_atomic(hermes_home / "state" / "arclink-academy-apply.json", state_body)
    changed_any = changed_any or state_changed
    post_apply_refresh_result = run_academy_post_apply_refresh(
        conn,
        deployment_id=deployment_id,
        qmd_runner=_academy_durable_refresh_queue_runner,
        memory_runner=_academy_durable_refresh_queue_runner,
        skill_runner=_academy_skill_enablement_runner(conn, approved_skill_intents=approved_skill_intents),
        requested_by="system:academy_apply",
    )
    conn.execute(
        """
        UPDATE academy_specialist_subscriptions
        SET last_applied_capsule_version = ?
        WHERE trainee_id = ?
        """,
        (int(payload.get("academy_capsule_version") or 0), str(payload.get("trainee_id") or "")),
    )
    payload.update(
        {
            "status": "applied_hermes_home",
            "note": "PG-HERMES authorized: Academy specialist SOUL section was materialized into the deployment Hermes home.",
            "mutation_performed": True,
            "workspace_mutation_performed": False,
            "filesystem_mutation_performed": bool(changed_any),
            "applied_paths": applied_paths,
            "post_apply_refresh_request": refresh_request,
            "post_apply_refresh_result": post_apply_refresh_result,
        }
    )
    return payload


# ---------------------------------------------------------------------------
# Stale action recovery
# ---------------------------------------------------------------------------

def recover_stale_actions(
    conn: sqlite3.Connection,
    *,
    stale_threshold_seconds: int = _STALE_THRESHOLD_SECONDS,
    max_attempts: int = _STALE_RECOVERY_MAX_ATTEMPTS,
) -> list[dict[str, Any]]:
    """Return running actions older than threshold to queued or failed."""
    from arclink_control import parse_utc_iso, utc_now
    now = utc_now()
    rows = conn.execute(
        "SELECT * FROM arclink_action_intents WHERE status = 'running' ORDER BY updated_at ASC",
    ).fetchall()
    recovered = []
    for row in rows:
        updated = parse_utc_iso(row["updated_at"])
        if updated is None:
            continue
        elapsed = (now - updated).total_seconds()
        if elapsed < stale_threshold_seconds:
            continue
        action_id = str(row["action_id"])
        attempts_row = conn.execute(
            "SELECT COUNT(*) AS n FROM arclink_action_attempts WHERE action_id = ?",
            (action_id,),
        ).fetchone()
        attempt_count = int(attempts_row["n"] if attempts_row is not None else 0)
        terminal = int(max_attempts or 0) > 0 and attempt_count >= int(max_attempts or 0)
        new_status = "failed" if terminal else "queued"
        if terminal:
            error = f"stale running action exceeded {int(max_attempts)} attempt(s)"
            conn.execute(
                """
                UPDATE arclink_action_attempts
                SET status = 'failed',
                    error = CASE WHEN error = '' THEN ? ELSE error END,
                    finished_at = CASE WHEN finished_at = '' THEN ? ELSE finished_at END
                WHERE action_id = ?
                  AND status = 'running'
                """,
                (error, utc_now_iso(), action_id),
            )
        _update_intent_status(conn, action_id=action_id, status=new_status)
        append_arclink_event(
            conn,
            subject_kind=row["target_kind"],
            subject_id=row["target_id"],
            event_type="action_stale_failed" if terminal else "action_stale_recovered",
            metadata={"action_id": action_id, "elapsed_seconds": int(elapsed), "attempt_count": attempt_count},
            commit=False,
        )
        append_arclink_audit(
            conn,
            action="stale_action_failed" if terminal else "stale_action_recovery",
            actor_id="system:action_worker",
            target_kind=row["target_kind"],
            target_id=row["target_id"],
            reason=(
                f"stale running action failed after {attempt_count} attempt(s) and {int(elapsed)}s"
                if terminal
                else f"stale running action returned to queued after {int(elapsed)}s"
            ),
            metadata={"action_id": action_id, "attempt_count": attempt_count},
            commit=False,
        )
        recovered.append({
            "action_id": action_id,
            "elapsed_seconds": int(elapsed),
            "attempt_count": attempt_count,
            "new_status": new_status,
        })
    conn.commit()
    return recovered


def list_action_attempts(
    conn: sqlite3.Connection,
    *,
    action_id: str,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM arclink_action_attempts WHERE action_id = ? ORDER BY started_at DESC",
        (action_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def run_pod_migration_gc(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return garbage_collect_pod_migrations(conn)


def _executor_from_env(env: Mapping[str, str] | None = None) -> ArcLinkExecutor:
    source = dict(env or os.environ)
    adapter = str(source.get("ARCLINK_EXECUTOR_ADAPTER") or "disabled").strip().lower()
    if adapter == "fake":
        return ArcLinkExecutor(
            config=ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"),
            secret_resolver=FakeSecretResolver({}),
        )
    if adapter not in {"local", "ssh"}:
        raise ArcLinkActionWorkerError(
            "set ARCLINK_EXECUTOR_ADAPTER to fake, local, or ssh before running the action worker"
        )
    from arclink_sovereign_worker import SovereignSecretResolver

    secret_store_dir = Path(
        source.get("ARCLINK_SECRET_STORE_DIR")
        or "/home/arclink/arclink/arclink-priv/state/sovereign-secrets"
    )
    materialization_root = Path(
        source.get("ARCLINK_ACTION_WORKER_SECRET_MATERIALIZATION_DIR")
        or "/tmp/arclink-action-worker/secrets"
    )
    resolver = SovereignSecretResolver(
        env=source,
        secret_store_dir=secret_store_dir,
        materialization_root=materialization_root,
    )
    try:
        return executor_for_fleet_host(
            adapter=adapter,
            env=source,
            host={
                "hostname": str(
                    source.get("ARCLINK_ACTION_WORKER_SSH_HOST")
                    or source.get("ARCLINK_LOCAL_FLEET_SSH_HOST")
                    or "localhost"
                ),
                "metadata_json": json.dumps(
                    {
                        "ssh_host": str(
                            source.get("ARCLINK_ACTION_WORKER_SSH_HOST")
                            or source.get("ARCLINK_LOCAL_FLEET_SSH_HOST")
                            or ""
                        ),
                        "ssh_user": str(
                            source.get("ARCLINK_ACTION_WORKER_SSH_USER")
                            or source.get("ARCLINK_LOCAL_FLEET_SSH_USER")
                            or "arclink"
                        ),
                    },
                    sort_keys=True,
                ),
            },
            secret_resolver=resolver,
        )
    except ArcLinkExecutorError as exc:
        raise ArcLinkActionWorkerError(str(exc) or "failed to build ArcLink action executor") from exc


def _db_connect(path: str) -> sqlite3.Connection:
    db_path = str(path or os.environ.get("ARCLINK_DB_PATH") or "/home/arclink/arclink/arclink-priv/state/arclink-control.sqlite3")
    cfg = Config.from_env()
    cfg = replace(cfg, db_path=Path(db_path).resolve(), state_dir=Path(db_path).resolve().parent)
    return connect_db(cfg)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Consume queued ArcLink admin action intents.")
    parser.add_argument("--db", default=os.environ.get("ARCLINK_DB_PATH", ""))
    parser.add_argument("--batch-size", type=int, default=int(os.environ.get("ARCLINK_ACTION_WORKER_BATCH_SIZE", "10")))
    parser.add_argument("--interval", type=float, default=float(os.environ.get("ARCLINK_ACTION_WORKER_INTERVAL_SECONDS", "30")))
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    adapter = str(os.environ.get("ARCLINK_EXECUTOR_ADAPTER") or "disabled").strip().lower()
    if adapter in {"", "disabled", "off", "none"}:
        with _db_connect(args.db) as conn:
            pending = conn.execute(
                "SELECT COUNT(*) AS c FROM arclink_action_intents WHERE status IN ('queued', 'running')"
            ).fetchone()
        payload = {
            "status": "disabled",
            "reason": "ARCLINK_EXECUTOR_ADAPTER is disabled",
            "pending_actions": int(pending["c"] if pending is not None else 0),
        }
        if args.json:
            print(json.dumps(payload, sort_keys=True))
        else:
            print(f"ArcLink action worker disabled; pending_actions={payload['pending_actions']}")
        return 0

    executor = _executor_from_env(os.environ)
    worker_id = _worker_id("wrk")
    executor_cache: _ActionExecutorCache = {}
    with _db_connect(args.db) as conn:
        while True:
            recovered = recover_stale_actions(conn)
            results = process_arclink_action_batch(
                conn,
                executor=executor,
                batch_size=max(1, args.batch_size),
                worker_id=worker_id,
                env=os.environ,
                executor_cache=executor_cache,
            )
            migration_gc = run_pod_migration_gc(conn)
            payload = {"recovered": recovered, "processed": results}
            if migration_gc:
                payload["migration_gc"] = migration_gc
            if args.json:
                print(json.dumps(payload, sort_keys=True))
            elif results or recovered:
                print(f"ArcLink action worker: recovered={len(recovered)} processed={len(results)}")
            if args.once:
                return 0
            time.sleep(max(1.0, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
