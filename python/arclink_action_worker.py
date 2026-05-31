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
from typing import Any, Mapping

from arclink_control import (
    ARCLINK_ACTION_ATTEMPT_STATUSES,
    ARCLINK_ACTION_INTENT_STATUSES,
    Config,
    append_arclink_audit,
    append_arclink_event,
    comp_arclink_subscription,
    connect_db,
    link_arclink_action_operation,
    utc_now_iso,
)
from arclink_boundary import json_dumps_safe, json_loads_safe, reject_secret_material, rowdict
from arclink_secrets_regex import contains_secret_material, redact_then_truncate
from arclink_ingress import desired_arclink_ingress_records
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


# Action types that map to implemented executor or local control-plane calls.
_EXECUTOR_ACTIONS = frozenset({
    "restart", "reprovision", "dns_repair", "rotate_chutes_key", "refund", "cancel", "comp", "backup_write_check",
})

_STALE_THRESHOLD_SECONDS = 3600  # 1 hour
_ActionExecutorCache = dict[tuple[str, str, str], ArcLinkExecutor]
_ACTION_EXECUTOR_CACHE: _ActionExecutorCache = {}
_LIFECYCLE_PATH_OVERRIDE_KEYS = ("project_name", "env_file", "compose_file")


def _worker_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


def _reject_secrets(value: Any, *, path: str = "$") -> None:
    reject_secret_material(value, path=path, label="ArcLink action worker", error_cls=ArcLinkActionWorkerError)


def _safe_error_message(exc: Exception) -> str:
    msg = redact_then_truncate(str(exc), limit=500)
    if contains_secret_material(str(exc)):
        return msg or "executor error contained secret material and was redacted"
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
            materialization_root=materialization_root,
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
    selected_executor, routing = _select_action_executor(
        conn,
        intent=intent,
        metadata=metadata,
        fallback_executor=executor,
        env=worker_env,
        cache=executor_cache if executor_cache is not None else _ACTION_EXECUTOR_CACHE,
    )

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
    state_body = json.dumps(
        {
            "applied_at": applied_at,
            "deployment_id": deployment_id,
            "trainee_id": str(payload.get("trainee_id") or ""),
            "program_id": str(payload.get("program_id") or ""),
            "manifest_id": str(payload.get("manifest_id") or ""),
            "plan_id": str(payload.get("plan_id") or ""),
            "academy_specialist_uid": str(payload.get("academy_specialist_uid") or ""),
            "academy_capsule_version": int(payload.get("academy_capsule_version") or 0),
        },
        indent=2,
        sort_keys=True,
    ) + "\n"
    state_changed = _write_private_text_atomic(hermes_home / "state" / "arclink-academy-apply.json", state_body)
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
            "filesystem_mutation_performed": bool(soul_changed or state_changed),
            "applied_paths": ["SOUL.md", "state/arclink-academy-apply.json"],
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
        _update_intent_status(conn, action_id=action_id, status="queued")
        append_arclink_event(
            conn,
            subject_kind=row["target_kind"],
            subject_id=row["target_id"],
            event_type="action_stale_recovered",
            metadata={"action_id": action_id, "elapsed_seconds": int(elapsed)},
            commit=False,
        )
        append_arclink_audit(
            conn,
            action="stale_action_recovery",
            actor_id="system:action_worker",
            target_kind=row["target_kind"],
            target_id=row["target_id"],
            reason=f"stale running action returned to queued after {int(elapsed)}s",
            metadata={"action_id": action_id},
            commit=False,
        )
        recovered.append({"action_id": action_id, "elapsed_seconds": int(elapsed), "new_status": "queued"})
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
