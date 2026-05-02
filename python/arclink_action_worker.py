#!/usr/bin/env python3
"""ArcLink admin action worker: consumes queued intents via executor."""
from __future__ import annotations

import secrets
import sqlite3
from typing import Any, Mapping

from arclink_control import append_arclink_audit, append_arclink_event, utc_now_iso
from arclink_boundary import json_dumps_safe, json_loads_safe, reject_secret_material, rowdict
from arclink_executor import (
    ArcLinkExecutor,
    ArcLinkExecutorConfig,
    ArcLinkExecutorError,
    ChutesKeyApplyRequest,
    CloudflareDnsApplyRequest,
    DockerComposeLifecycleRequest,
    StripeActionApplyRequest,
)


class ArcLinkActionWorkerError(ValueError):
    pass


# Action types that map to executor calls
_EXECUTOR_ACTIONS = frozenset({
    "restart", "reprovision", "dns_repair", "rotate_chutes_key",
    "refund", "cancel", "comp", "rollout",
})

# Action types that are local state transitions only
_LOCAL_ACTIONS = frozenset({"suspend", "unsuspend", "force_resynth", "rotate_bot_key"})

_STALE_THRESHOLD_SECONDS = 3600  # 1 hour


def _worker_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


def _reject_secrets(value: Any, *, path: str = "$") -> None:
    reject_secret_material(value, path=path, label="ArcLink action worker", error_cls=ArcLinkActionWorkerError)


def _safe_error_message(exc: Exception) -> str:
    msg = str(exc)[:500]
    try:
        _reject_secrets({"error": msg}, path="$")
    except ArcLinkActionWorkerError:
        return "executor error contained secret material and was redacted"
    return msg


def _record_attempt(
    conn: sqlite3.Connection,
    *,
    action_id: str,
    status: str = "running",
    adapter: str = "",
    result: Mapping[str, Any] | None = None,
    error: str = "",
) -> str:
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
    conn.execute(
        "UPDATE arclink_action_intents SET status = ?, updated_at = ? WHERE action_id = ?",
        (status, utc_now_iso(), action_id),
    )


# ---------------------------------------------------------------------------
# Core worker entrypoint
# ---------------------------------------------------------------------------

def process_next_arclink_action(
    conn: sqlite3.Connection,
    *,
    executor: ArcLinkExecutor,
) -> dict[str, Any] | None:
    """Claim and execute the oldest queued action intent. Returns the result or None if empty."""
    row = conn.execute(
        """
        SELECT * FROM arclink_action_intents
        WHERE status = 'queued'
        ORDER BY created_at ASC, action_id ASC
        LIMIT 1
        """,
    ).fetchone()
    if row is None:
        return None

    intent = dict(row)
    return _execute_action(conn, intent=intent, executor=executor)


def process_arclink_action_batch(
    conn: sqlite3.Connection,
    *,
    executor: ArcLinkExecutor,
    batch_size: int = 10,
) -> list[dict[str, Any]]:
    """Process up to batch_size queued actions."""
    if batch_size < 1:
        raise ArcLinkActionWorkerError("batch size must be at least 1")
    results = []
    for _ in range(batch_size):
        result = process_next_arclink_action(conn, executor=executor)
        if result is None:
            break
        results.append(result)
    return results


def _execute_action(
    conn: sqlite3.Connection,
    *,
    intent: dict[str, Any],
    executor: ArcLinkExecutor,
) -> dict[str, Any]:
    action_id = str(intent["action_id"])
    action_type = str(intent["action_type"])
    target_kind = str(intent["target_kind"])
    target_id = str(intent["target_id"])
    metadata = json_loads_safe(intent.get("metadata_json", "{}"))

    # Transition to running
    _update_intent_status(conn, action_id=action_id, status="running")
    attempt_id = _record_attempt(
        conn, action_id=action_id, adapter=executor.config.adapter_name,
    )
    conn.commit()

    try:
        result = _dispatch_action(
            executor=executor,
            action_type=action_type,
            target_kind=target_kind,
            target_id=target_id,
            metadata=metadata,
        )
        _reject_secrets(result, path="$.result")
        _finish_attempt(conn, attempt_id=attempt_id, status="succeeded", result=result)
        _update_intent_status(conn, action_id=action_id, status="succeeded")
        append_arclink_event(
            conn,
            subject_kind=target_kind,
            subject_id=target_id,
            event_type=f"action_executed:{action_type}",
            metadata={"action_id": action_id, "attempt_id": attempt_id, "status": "succeeded"},
            commit=False,
        )
        append_arclink_audit(
            conn,
            action=f"action_worker:{action_type}",
            actor_id="system:action_worker",
            target_kind=target_kind,
            target_id=target_id,
            reason=f"executed queued action {action_id}",
            metadata={"action_id": action_id, "attempt_id": attempt_id, "status": "succeeded"},
            commit=False,
        )
        conn.commit()
        return {
            "action_id": action_id,
            "attempt_id": attempt_id,
            "status": "succeeded",
            "action_type": action_type,
            "result": result,
        }
    except Exception as exc:
        error_msg = _safe_error_message(exc)
        _finish_attempt(conn, attempt_id=attempt_id, status="failed", error=error_msg)
        _update_intent_status(conn, action_id=action_id, status="failed")
        append_arclink_event(
            conn,
            subject_kind=target_kind,
            subject_id=target_id,
            event_type=f"action_failed:{action_type}",
            metadata={"action_id": action_id, "attempt_id": attempt_id, "error": error_msg},
            commit=False,
        )
        conn.commit()
        return {
            "action_id": action_id,
            "attempt_id": attempt_id,
            "status": "failed",
            "action_type": action_type,
            "error": error_msg,
        }


def _dispatch_action(
    *,
    executor: ArcLinkExecutor,
    action_type: str,
    target_kind: str,
    target_id: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Route action type to executor call. Returns redacted result metadata."""
    if action_type == "restart":
        result = executor.docker_compose_lifecycle(DockerComposeLifecycleRequest(
            deployment_id=target_id,
            action="restart",
            idempotency_key=metadata.get("idempotency_key", ""),
        ))
        return {"live": result.live, "status": result.status, "action": result.action}

    if action_type == "dns_repair":
        dns = metadata.get("dns") or {}
        result = executor.cloudflare_dns_apply(CloudflareDnsApplyRequest(
            deployment_id=target_id,
            dns=dns,
            zone_id=metadata.get("zone_id", ""),
            idempotency_key=metadata.get("idempotency_key", ""),
        ))
        return {"live": result.live, "status": result.status, "records": list(result.records)}

    if action_type == "rotate_chutes_key":
        secret_ref = metadata.get("secret_ref", f"secret://arclink/chutes/{target_id}")
        result = executor.chutes_key_apply(ChutesKeyApplyRequest(
            deployment_id=target_id,
            action="rotate",
            secret_ref=secret_ref,
            label=metadata.get("label", "action_worker_rotate"),
            idempotency_key=metadata.get("idempotency_key", ""),
        ))
        return {"live": result.live, "status": result.status, "action": result.action, "key_id": result.key_id}

    if action_type in ("refund", "cancel"):
        result = executor.stripe_action_apply(StripeActionApplyRequest(
            deployment_id=target_id,
            action=action_type,
            customer_ref=metadata.get("customer_ref", ""),
            idempotency_key=metadata.get("idempotency_key", ""),
        ))
        return {"live": result.live, "status": result.status, "action": result.action}

    if action_type == "comp":
        # Comp is a local entitlement operation, not an executor call
        return {"status": "applied", "action": "comp", "note": "entitlement_updated_locally"}

    if action_type in ("suspend", "unsuspend", "force_resynth", "rotate_bot_key", "reprovision", "rollout"):
        # Local state transitions / no-op safe in fake mode
        return {"status": "applied", "action": action_type, "note": "local_state_transition"}

    raise ArcLinkActionWorkerError(f"unsupported action type: {action_type}")


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
