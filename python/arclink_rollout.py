#!/usr/bin/env python3
"""ArcLink rollout/rollback model: canary waves, pause, rollback records."""
from __future__ import annotations

import json
import hashlib
import secrets
import sqlite3
from typing import Any, Mapping, Sequence

from arclink_control import append_arclink_audit, append_arclink_event, utc_now_iso
from arclink_boundary import json_dumps_safe, json_loads_safe, reject_secret_material


class ArcLinkRolloutError(ValueError):
    pass


ROLLOUT_STATUSES = frozenset({"planned", "in_progress", "paused", "completed", "failed", "rolled_back"})
ARCPOD_UPDATE_CANDIDATE_STATUSES = frozenset({"active"})
ARCPOD_UPDATE_REQUIRED_STATE_ROOTS = ("root", "config", "state", "vault", "hermes_home")
ARCPOD_UPDATE_HEALTHY_STATUSES = frozenset({"healthy", "ok", "ready", "running", "planned"})
ARCPOD_UPDATE_DEFAULT_BATCH_SIZE = 1
ARCPOD_UPDATE_DEFAULT_MAX_BATCH_SIZE = 25
ARCPOD_UPDATE_PROOF_GATE = "PG-UPGRADE/PG-HERMES"
ARCPOD_UPDATE_SMOKE_CHECKS = (
    "refresh_hermes_runtime",
    "sync_arclink_skills",
    "sync_dashboard_plugins",
    "refresh_command_menus",
    "verify_managed_context",
    "sync_pinned_hermes_docs",
    "qmd_memory_health",
    "live_agent_tool_smoke",
)


def _rollout_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


def _reject_secrets(value: Any, *, path: str = "$") -> None:
    reject_secret_material(value, path=path, label="ArcLink rollout", error_cls=ArcLinkRolloutError)


def create_rollout(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    version_tag: str,
    waves: Sequence[Mapping[str, Any]],
    rollback_plan: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    rollout_id: str = "",
) -> dict[str, Any]:
    clean_deployment = str(deployment_id or "").strip()
    clean_version = str(version_tag or "").strip()
    if not clean_deployment:
        raise ArcLinkRolloutError("rollout requires a deployment id")
    if not clean_version:
        raise ArcLinkRolloutError("rollout requires a version tag")
    if not waves:
        raise ArcLinkRolloutError("rollout requires at least one wave")
    _reject_secrets(metadata, path="$.metadata")
    _reject_secrets(rollback_plan, path="$.rollback_plan")
    for i, wave in enumerate(waves):
        _reject_secrets(wave, path=f"$.waves[{i}]")

    # Validate rollback plan preserves state roots
    if rollback_plan:
        actions = list(rollback_plan.get("actions", []))
        if "preserve_state_roots" not in actions:
            raise ArcLinkRolloutError("rollout rollback plan must include preserve_state_roots")

    waves_json = json.dumps(list(waves), sort_keys=True, default=str)
    rollback_json = json_dumps_safe(rollback_plan, label="ArcLink rollout", error_cls=ArcLinkRolloutError)
    metadata_json = json_dumps_safe(metadata, label="ArcLink rollout", error_cls=ArcLinkRolloutError)

    clean_id = rollout_id.strip() if rollout_id else _rollout_id("rlt")
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO arclink_rollouts (
          rollout_id, deployment_id, version_tag, status, wave_count, current_wave,
          waves_json, rollback_plan_json, metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, 'planned', ?, 0, ?, ?, ?, ?, ?)
        """,
        (clean_id, clean_deployment, clean_version, len(waves), waves_json, rollback_json, metadata_json, now, now),
    )
    conn.commit()
    append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=clean_deployment,
        event_type="rollout_created",
        metadata={"rollout_id": clean_id, "version_tag": clean_version, "wave_count": len(waves)},
    )
    return dict(conn.execute("SELECT * FROM arclink_rollouts WHERE rollout_id = ?", (clean_id,)).fetchone())


def advance_rollout_wave(
    conn: sqlite3.Connection,
    *,
    rollout_id: str,
) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM arclink_rollouts WHERE rollout_id = ?", (rollout_id,)).fetchone()
    if row is None:
        raise ArcLinkRolloutError(f"unknown rollout: {rollout_id}")
    rollout = dict(row)
    status = rollout["status"]
    if status not in ("planned", "in_progress"):
        raise ArcLinkRolloutError(f"cannot advance rollout in status: {status}")
    current = int(rollout["current_wave"])
    wave_count = int(rollout["wave_count"])
    next_wave = current + 1
    if next_wave > wave_count:
        raise ArcLinkRolloutError("all waves already completed")
    new_status = "completed" if next_wave >= wave_count else "in_progress"
    now = utc_now_iso()
    conn.execute(
        "UPDATE arclink_rollouts SET current_wave = ?, status = ?, updated_at = ? WHERE rollout_id = ?",
        (next_wave, new_status, now, rollout_id),
    )
    conn.commit()
    append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=rollout["deployment_id"],
        event_type="rollout_wave_advanced",
        metadata={"rollout_id": rollout_id, "wave": next_wave, "status": new_status},
    )
    return dict(conn.execute("SELECT * FROM arclink_rollouts WHERE rollout_id = ?", (rollout_id,)).fetchone())


def pause_rollout(
    conn: sqlite3.Connection,
    *,
    rollout_id: str,
) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM arclink_rollouts WHERE rollout_id = ?", (rollout_id,)).fetchone()
    if row is None:
        raise ArcLinkRolloutError(f"unknown rollout: {rollout_id}")
    if row["status"] != "in_progress":
        raise ArcLinkRolloutError(f"cannot pause rollout in status: {row['status']}")
    now = utc_now_iso()
    conn.execute(
        "UPDATE arclink_rollouts SET status = 'paused', updated_at = ? WHERE rollout_id = ?",
        (now, rollout_id),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM arclink_rollouts WHERE rollout_id = ?", (rollout_id,)).fetchone())


def fail_rollout(
    conn: sqlite3.Connection,
    *,
    rollout_id: str,
    reason: str = "",
) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM arclink_rollouts WHERE rollout_id = ?", (rollout_id,)).fetchone()
    if row is None:
        raise ArcLinkRolloutError(f"unknown rollout: {rollout_id}")
    if row["status"] in ("completed", "rolled_back"):
        raise ArcLinkRolloutError(f"cannot fail rollout in status: {row['status']}")
    now = utc_now_iso()
    conn.execute(
        "UPDATE arclink_rollouts SET status = 'failed', updated_at = ? WHERE rollout_id = ?",
        (now, rollout_id),
    )
    conn.commit()
    append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=row["deployment_id"],
        event_type="rollout_failed",
        metadata={"rollout_id": rollout_id, "reason": reason},
    )
    return dict(conn.execute("SELECT * FROM arclink_rollouts WHERE rollout_id = ?", (rollout_id,)).fetchone())


def rollback_rollout(
    conn: sqlite3.Connection,
    *,
    rollout_id: str,
    reason: str = "",
) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM arclink_rollouts WHERE rollout_id = ?", (rollout_id,)).fetchone()
    if row is None:
        raise ArcLinkRolloutError(f"unknown rollout: {rollout_id}")
    if row["status"] in ("completed", "rolled_back"):
        raise ArcLinkRolloutError(f"cannot rollback rollout in status: {row['status']}")
    rollback_plan = json_loads_safe(row["rollback_plan_json"] if "rollback_plan_json" in row.keys() else "{}")
    now = utc_now_iso()
    conn.execute(
        "UPDATE arclink_rollouts SET status = 'rolled_back', updated_at = ? WHERE rollout_id = ?",
        (now, rollout_id),
    )
    conn.commit()
    state_roots = rollback_plan.get("state_roots", {})
    append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=row["deployment_id"],
        event_type="rollout_rolled_back",
        metadata={
            "rollout_id": rollout_id,
            "reason": reason,
            "preserved_state_roots": list(state_roots.keys()) if state_roots else [],
        },
    )
    append_arclink_audit(
        conn,
        action="rollout_rollback",
        actor_id="system:rollout",
        target_kind="deployment",
        target_id=row["deployment_id"],
        reason=reason or f"rollback of {rollout_id}",
        metadata={"rollout_id": rollout_id, "rollback_plan_keys": list(rollback_plan.keys())},
    )
    return dict(conn.execute("SELECT * FROM arclink_rollouts WHERE rollout_id = ?", (rollout_id,)).fetchone())


def get_rollout(conn: sqlite3.Connection, *, rollout_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM arclink_rollouts WHERE rollout_id = ?", (rollout_id,)).fetchone()
    if row is None:
        raise ArcLinkRolloutError(f"unknown rollout: {rollout_id}")
    return dict(row)


def list_rollouts(
    conn: sqlite3.Connection,
    *,
    deployment_id: str = "",
    status: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    conditions = []
    params: list[Any] = []
    if deployment_id:
        conditions.append("deployment_id = ?")
        params.append(deployment_id)
    if status:
        conditions.append("status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    rows = conn.execute(
        f"SELECT * FROM arclink_rollouts {where} ORDER BY created_at DESC LIMIT ?",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def plan_arcpod_update_rollout(
    conn: sqlite3.Connection,
    *,
    target_version: str,
    batch_size: int | None = None,
    deployment_ids: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build a no-side-effect dry-run plan for rolling ArcPod updates.

    This planner intentionally does not create arclink_rollouts rows, queue
    action intents, run deploy scripts, contact workers, or touch pod state.
    It gives admin/Raven surfaces one deterministic schema to review before a
    later execution slice wires real workers.
    """
    source_env = env or {}
    clean_target = str(target_version or "").strip()
    if not clean_target:
        raise ArcLinkRolloutError("ArcPod update rollout planning requires a target version")
    _reject_secrets(clean_target, path="$.target_version")

    clean_batch_size = _coerce_batch_size(
        batch_size,
        env=source_env,
    )
    max_batch_size = _coerce_max_batch_size(source_env)
    if clean_batch_size < 1:
        raise ArcLinkRolloutError("ArcPod update rollout batch_size must be at least 1")
    if clean_batch_size > max_batch_size:
        raise ArcLinkRolloutError(
            f"ArcPod update rollout batch_size must be <= {max_batch_size} for dry-run planning"
        )

    requested_ids = _clean_requested_deployment_ids(deployment_ids or ())
    deployments = _select_update_candidate_deployments(conn, requested_ids=requested_ids)
    found_ids = {str(row["deployment_id"]) for row in deployments}
    missing_requested_ids = [deployment_id for deployment_id in requested_ids if deployment_id not in found_ids]

    candidates: list[dict[str, Any]] = []
    already_current: list[dict[str, str]] = []
    preflight_blockers: list[dict[str, str]] = []
    state_roots_by_deployment: dict[str, dict[str, str]] = {}

    for row in deployments:
        deployment = dict(row)
        metadata = json_loads_safe(str(deployment.get("metadata_json") or "{}"))
        current_version = _deployment_current_version(metadata)
        deployment_id = str(deployment["deployment_id"])
        if current_version and current_version == clean_target:
            already_current.append(
                {
                    "deployment_id": deployment_id,
                    "current_version": current_version,
                    "status": str(deployment["status"]),
                }
            )
            continue

        state_roots = _deployment_state_roots(metadata)
        missing_roots = [name for name in ARCPOD_UPDATE_REQUIRED_STATE_ROOTS if not state_roots.get(name)]
        health_rows = _deployment_service_health(conn, deployment_id)
        health_blockers = _health_blockers(deployment_id, health_rows)
        blockers: list[dict[str, str]] = []
        if missing_roots:
            blockers.append(
                {
                    "deployment_id": deployment_id,
                    "code": "state_roots_missing",
                    "message": f"missing state root metadata: {', '.join(missing_roots)}",
                }
            )
        blockers.extend(health_blockers)
        preflight_blockers.extend(blockers)
        if state_roots:
            state_roots_by_deployment[deployment_id] = state_roots
        candidates.append(
            {
                "deployment_id": deployment_id,
                "user_id": str(deployment["user_id"]),
                "prefix": str(deployment["prefix"]),
                "status": str(deployment["status"]),
                "current_version": current_version,
                "target_version": clean_target,
                "preflight_status": "blocked" if blockers else "ready",
                "blockers": blockers,
                "state_roots": state_roots,
                "rollback_plan": _deployment_rollback_plan(
                    deployment_id=deployment_id,
                    current_version=current_version,
                    state_roots=state_roots,
                ),
                "health": {
                    "observed_services": [
                        {
                            "service_name": str(item["service_name"]),
                            "status": str(item["status"]),
                            "checked_at": str(item["checked_at"] or ""),
                        }
                        for item in health_rows
                    ],
                    "required_statuses": sorted(ARCPOD_UPDATE_HEALTHY_STATUSES),
                },
                "health_smoke": _pending_health_smoke(clean_target),
                "backup_freshness": {
                    "status": "not_checked_in_dry_run",
                    "proof_gate": "PG-BACKUP",
                },
            }
        )

    for missing_id in missing_requested_ids:
        preflight_blockers.append(
            {
                "deployment_id": missing_id,
                "code": "deployment_not_found",
                "message": "requested deployment was not found in the local control DB",
            }
        )

    ready_candidates = [candidate for candidate in candidates if candidate["preflight_status"] == "ready"]
    blocked_candidates = [candidate for candidate in candidates if candidate["preflight_status"] == "blocked"]
    batches = [] if preflight_blockers else _batch_candidates(ready_candidates, clean_batch_size)
    status = "blocked" if preflight_blockers else ("ready" if ready_candidates else "empty")
    repair_summary = [
        f"{item['deployment_id']}: {item['message']}"
        for item in preflight_blockers
    ]

    return {
        "plan_kind": "arcpod_update_rollout",
        "mode": "dry_run",
        "status": status,
        "target_version": clean_target,
        "batch_size": clean_batch_size,
        "max_batch_size": max_batch_size,
        "candidate_statuses": sorted(ARCPOD_UPDATE_CANDIDATE_STATUSES),
        "candidate_count": len(candidates),
        "ready_count": len(ready_candidates),
        "blocked_count": len(blocked_candidates),
        "preflight_blocker_count": len(preflight_blockers),
        "already_current_count": len(already_current),
        "batch_count": len(batches),
        "batches": batches,
        "candidates": candidates,
        "already_current": already_current,
        "preflight_blockers": preflight_blockers,
        "repair_summary": repair_summary,
        "stop_on_failure": True,
        "state_preservation": {
            "required": True,
            "required_state_roots": list(ARCPOD_UPDATE_REQUIRED_STATE_ROOTS),
            "state_roots_by_deployment": state_roots_by_deployment,
            "missing_state_root_deployments": [
                item["deployment_id"]
                for item in preflight_blockers
                if item["code"] == "state_roots_missing"
            ],
        },
        "rollback_plan": {
            "required": True,
            "actions": [
                "preserve_state_roots",
                "restore_previous_release_metadata",
                "restart_previous_services",
                "route_failed_batch_to_repair",
            ],
            "stop_on_failure": True,
        },
        "execution": {
            "enabled": False,
            "reason": "dry-run planner only; no rollout row, action intent, deploy, Docker, SSH, or provider command was run",
        },
        "mutation_performed": False,
        "rollout_row_created": False,
        "action_intent_created": False,
        "proof_gate": ARCPOD_UPDATE_PROOF_GATE,
        "live_proof_required": True,
    }


def materialize_arcpod_update_rollout_job(
    conn: sqlite3.Connection,
    *,
    plan: Mapping[str, Any],
    action_id: str = "",
    idempotency_key: str = "",
    actor_id: str = "system:action_worker",
) -> dict[str, Any]:
    """Materialize a ready ArcPod update dry-run plan as local rollout rows.

    This is intentionally a local typed job transition only. It does not run
    deploy scripts, refresh Pods, contact Docker/systemd/SSH/provider APIs, or
    claim live health evidence.
    """
    if not isinstance(plan, Mapping):
        raise ArcLinkRolloutError("ArcPod update rollout materialization requires a plan object")
    clean_plan = dict(plan)
    _reject_secrets(clean_plan, path="$.plan")
    if str(clean_plan.get("plan_kind") or "") != "arcpod_update_rollout":
        raise ArcLinkRolloutError("ArcPod update rollout materialization requires an arcpod_update_rollout plan")
    if str(clean_plan.get("status") or "") != "ready":
        raise ArcLinkRolloutError("ArcPod update rollout materialization requires a ready preflight plan")
    if str(clean_plan.get("mode") or "") != "dry_run":
        raise ArcLinkRolloutError("ArcPod update rollout materialization requires a dry-run source plan")

    target_version = str(clean_plan.get("target_version") or "").strip()
    if not target_version:
        raise ArcLinkRolloutError("ArcPod update rollout materialization requires a target version")
    _reject_secrets(target_version, path="$.target_version")

    batches = _materialization_batches(clean_plan)
    candidates = _materialization_candidates(clean_plan)
    if not batches:
        raise ArcLinkRolloutError("ArcPod update rollout materialization requires at least one ready batch")
    batch_deployment_ids = [[str(item["deployment_id"]) for item in batch] for batch in batches]
    deployment_ids = [deployment_id for batch in batch_deployment_ids for deployment_id in batch]
    if not deployment_ids:
        raise ArcLinkRolloutError("ArcPod update rollout materialization requires at least one ready deployment")

    for deployment_id in deployment_ids:
        candidate = candidates.get(deployment_id)
        if candidate is None:
            raise ArcLinkRolloutError(f"ArcPod update rollout plan is missing candidate data for {deployment_id}")
        if str(candidate.get("preflight_status") or "") != "ready":
            raise ArcLinkRolloutError(f"ArcPod update rollout candidate is not ready: {deployment_id}")

    clean_action_id = str(action_id or "").strip()
    clean_key = str(idempotency_key or "").strip()
    rollout_group_id = _arcpod_update_rollout_group_id(
        clean_plan,
        action_id=clean_action_id,
        idempotency_key=clean_key,
    )
    expected_shape = {
        "target_version": target_version,
        "batch_deployment_ids": batch_deployment_ids,
    }
    existing_group_rows = _rollout_rows_for_group(conn, rollout_group_id=rollout_group_id)
    if existing_group_rows:
        existing_shape = _group_shape_from_existing_rows(existing_group_rows)
        if existing_shape != expected_shape:
            raise ArcLinkRolloutError(
                "ArcPod update rollout idempotency key is already bound to a different rollout plan"
            )

    rollout_ids: list[str] = []
    created_rollout_count = 0
    rollout_rows: list[dict[str, Any]] = []
    batch_lookup = {
        deployment_id: (batch_index, batch_position, batch_ids)
        for batch_index, batch_ids in enumerate(batch_deployment_ids, start=1)
        for batch_position, deployment_id in enumerate(batch_ids, start=1)
    }
    for deployment_id in deployment_ids:
        batch_index, batch_position, batch_ids = batch_lookup[deployment_id]
        candidate = candidates[deployment_id]
        rollout_id = _arcpod_update_rollout_id(
            rollout_group_id=rollout_group_id,
            deployment_id=deployment_id,
            batch_index=batch_index,
            batch_position=batch_position,
        )
        rollout_ids.append(rollout_id)
        existing = conn.execute(
            "SELECT * FROM arclink_rollouts WHERE rollout_id = ?",
            (rollout_id,),
        ).fetchone()
        if existing is None:
            wave = _materialized_rollout_wave(
                candidate=candidate,
                rollout_group_id=rollout_group_id,
                batch_index=batch_index,
                batch_position=batch_position,
                batch_deployment_ids=batch_ids,
            )
            metadata = _materialized_rollout_metadata(
                plan=clean_plan,
                candidate=candidate,
                rollout_group_id=rollout_group_id,
                action_id=clean_action_id,
                idempotency_key=clean_key,
                batch_index=batch_index,
                batch_position=batch_position,
                batch_deployment_ids=batch_ids,
                all_batch_deployment_ids=batch_deployment_ids,
            )
            create_rollout(
                conn,
                deployment_id=deployment_id,
                version_tag=target_version,
                waves=[wave],
                rollback_plan=dict(candidate.get("rollback_plan") or {}),
                metadata=metadata,
                rollout_id=rollout_id,
            )
            created_rollout_count += 1
        row = conn.execute(
            "SELECT * FROM arclink_rollouts WHERE rollout_id = ?",
            (rollout_id,),
        ).fetchone()
        if row is not None:
            rollout_rows.append(dict(row))

    append_arclink_event(
        conn,
        subject_kind="system",
        subject_id=rollout_group_id,
        event_type="arcpod_update_rollout_job_materialized",
        metadata={
            "rollout_group_id": rollout_group_id,
            "action_id": clean_action_id,
            "target_version": target_version,
            "rollout_count": len(rollout_ids),
            "created_rollout_count": created_rollout_count,
            "proof_gate": ARCPOD_UPDATE_PROOF_GATE,
        },
        commit=False,
    )
    append_arclink_audit(
        conn,
        action="arcpod_update_rollout_job_materialized",
        actor_id=str(actor_id or "system:action_worker"),
        target_kind="system",
        target_id=rollout_group_id,
        reason="materialized local ArcPod update rollout job from ready dry-run plan",
        metadata={
            "rollout_group_id": rollout_group_id,
            "action_id": clean_action_id,
            "target_version": target_version,
            "rollout_count": len(rollout_ids),
            "created_rollout_count": created_rollout_count,
            "live_proof_required": True,
        },
        commit=False,
    )
    conn.commit()

    result = {
        "status": "queued_local_job",
        "operation_kind": "arcpod_update_rollout",
        "rollout_group_id": rollout_group_id,
        "rollout_ids": rollout_ids,
        "rollout_count": len(rollout_ids),
        "created_rollout_count": created_rollout_count,
        "batch_count": len(batch_deployment_ids),
        "batch_deployment_ids": batch_deployment_ids,
        "target_version": target_version,
        "proof_gate": ARCPOD_UPDATE_PROOF_GATE,
        "live_proof_required": True,
        "live_mutation_performed": False,
        "local_mutation_performed": created_rollout_count > 0,
        "execution": {
            "enabled": False,
            "reason": "local typed rollout rows were queued only; live Pod refresh and health/smoke proof remain gated",
        },
        "rollouts": [
            {
                "rollout_id": str(row["rollout_id"]),
                "deployment_id": str(row["deployment_id"]),
                "status": str(row["status"]),
                "version_tag": str(row["version_tag"]),
            }
            for row in rollout_rows
        ],
    }
    _reject_secrets(result, path="$.result")
    return result


def execute_arcpod_update_rollout_batch(
    conn: sqlite3.Connection,
    *,
    rollout_group_id: str,
    executor: Mapping[str, Any] | None = None,
    batch_index: int | None = None,
    actor_id: str = "system:action_worker",
) -> dict[str, Any]:
    """Record one bounded fake/local ArcPod update batch execution.

    This helper is intentionally a local state-machine harness. The explicit
    executor contract is a record-only fake/local adapter declaration; this
    function never invokes deploy scripts, Docker, systemd, SSH, provider APIs,
    or live health/smoke probes.
    """
    clean_group_id = str(rollout_group_id or "").strip()
    if not clean_group_id:
        raise ArcLinkRolloutError("ArcPod update rollout execution requires a rollout group id")
    contract = _validate_rollout_executor_contract(executor)
    requested_batch = _coerce_requested_batch_index(batch_index)
    rows = _rollout_rows_for_group(conn, rollout_group_id=clean_group_id)
    if not rows:
        raise ArcLinkRolloutError(f"unknown ArcPod update rollout group: {clean_group_id}")
    batches = _group_rollout_rows_by_batch(rows)
    selected = _select_executable_rollout_batch(batches, requested_batch=requested_batch)
    status = selected["status"]
    selected_batch_index = int(selected.get("batch_index") or 0)
    selected_rows = list(selected.get("rows") or [])

    if status != "execute":
        result = _rollout_execution_non_mutating_result(
            status=status,
            rollout_group_id=clean_group_id,
            batch_index=selected_batch_index,
            rows=selected_rows,
            contract=contract,
        )
        _reject_secrets(result, path="$.result")
        return result

    pod_contract_results = {
        str(row["deployment_id"]): _rollout_contract_result(contract, str(row["deployment_id"]))
        for row in selected_rows
    }
    started_at = utc_now_iso()
    for row in selected_rows:
        metadata = _rollout_metadata_from_row(row)
        metadata["execution"] = {
            "status": "in_progress",
            "adapter": contract["adapter"],
            "record_only": True,
            "started_at": started_at,
            "finished_at": "",
            "batch_index": selected_batch_index,
            "status_transitions": ["planned", "in_progress"],
            "commands_run": [],
        }
        _reject_secrets(metadata, path="$.metadata")
        conn.execute(
            """
            UPDATE arclink_rollouts
            SET status = 'in_progress', metadata_json = ?, updated_at = ?
            WHERE rollout_id = ?
            """,
            (
                json_dumps_safe(metadata, label="ArcLink rollout", error_cls=ArcLinkRolloutError),
                started_at,
                str(row["rollout_id"]),
            ),
        )

    deployment_results: list[dict[str, Any]] = []
    any_failed = False
    for row in selected_rows:
        deployment_id = str(row["deployment_id"])
        target_version = str(row["version_tag"])
        pod_contract_result = pod_contract_results[deployment_id]
        pod_failed = str(pod_contract_result.get("status") or "").lower() in {"failed", "failure", "error"}
        final_status = "failed" if pod_failed else "completed"
        if pod_failed:
            any_failed = True
        finished_at = utc_now_iso()
        latest_row = conn.execute(
            "SELECT * FROM arclink_rollouts WHERE rollout_id = ?",
            (str(row["rollout_id"]),),
        ).fetchone()
        metadata = _rollout_metadata_from_row(dict(latest_row) if latest_row is not None else row)
        steps = _recorded_rollout_execution_steps(final_status=final_status)
        metadata.update(
            {
                "execution": {
                    "status": final_status,
                    "adapter": contract["adapter"],
                    "record_only": True,
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "batch_index": selected_batch_index,
                    "status_transitions": ["planned", "in_progress", final_status],
                    "commands_run": [],
                    "recorded_steps": steps,
                    "result": pod_contract_result,
                },
                "health_smoke": _executed_health_smoke(target_version, final_status=final_status),
                "backup_freshness": {
                    "status": "not_checked_in_local_execution",
                    "proof_gate": "PG-BACKUP",
                },
                "proof_gate": ARCPOD_UPDATE_PROOF_GATE,
                "live_proof_required": True,
                "live_mutation_performed": False,
                "local_execution_recorded": True,
                "repair_hints": _rollout_repair_hints(final_status=final_status),
            }
        )
        _reject_secrets(metadata, path="$.metadata")
        conn.execute(
            """
            UPDATE arclink_rollouts
            SET status = ?, current_wave = ?, metadata_json = ?, updated_at = ?
            WHERE rollout_id = ?
            """,
            (
                final_status,
                1 if final_status == "completed" else 0,
                json_dumps_safe(metadata, label="ArcLink rollout", error_cls=ArcLinkRolloutError),
                finished_at,
                str(row["rollout_id"]),
            ),
        )
        event_type = "arcpod_update_rollout_pod_failed" if pod_failed else "arcpod_update_rollout_pod_completed"
        append_arclink_event(
            conn,
            subject_kind="deployment",
            subject_id=deployment_id,
            event_type=event_type,
            metadata={
                "rollout_group_id": clean_group_id,
                "rollout_id": str(row["rollout_id"]),
                "batch_index": selected_batch_index,
                "target_version": target_version,
                "proof_gate": ARCPOD_UPDATE_PROOF_GATE,
            },
            commit=False,
        )
        deployment_results.append(
            {
                "deployment_id": deployment_id,
                "rollout_id": str(row["rollout_id"]),
                "status": final_status,
                "recorded_step_count": len(steps),
                "health_smoke_status": str(metadata["health_smoke"]["status"]),
                "proof_gate": ARCPOD_UPDATE_PROOF_GATE,
            }
        )

    final_batch_status = "failed" if any_failed else "completed"
    append_arclink_event(
        conn,
        subject_kind="system",
        subject_id=clean_group_id,
        event_type="arcpod_update_rollout_batch_executed",
        metadata={
            "rollout_group_id": clean_group_id,
            "batch_index": selected_batch_index,
            "status": final_batch_status,
            "deployment_ids": [item["deployment_id"] for item in deployment_results],
            "stop_on_failure": True,
            "proof_gate": ARCPOD_UPDATE_PROOF_GATE,
        },
        commit=False,
    )
    append_arclink_audit(
        conn,
        action="arcpod_update_rollout_batch_executed",
        actor_id=str(actor_id or "system:action_worker"),
        target_kind="system",
        target_id=clean_group_id,
        reason="recorded bounded fake/local ArcPod update rollout batch execution",
        metadata={
            "rollout_group_id": clean_group_id,
            "batch_index": selected_batch_index,
            "status": final_batch_status,
            "deployment_count": len(deployment_results),
            "live_proof_required": True,
        },
        commit=False,
    )
    conn.commit()

    result = {
        "status": final_batch_status,
        "operation_kind": "arcpod_update_rollout_batch",
        "rollout_group_id": clean_group_id,
        "batch_index": selected_batch_index,
        "batch_count": len(batches),
        "deployment_ids": [item["deployment_id"] for item in deployment_results],
        "deployment_results": deployment_results,
        "execution": {
            "enabled": True,
            "adapter": contract["adapter"],
            "record_only": True,
            "commands_run": [],
            "reason": "fake/local rollout execution recorded intended refresh/apply steps only",
        },
        "stop_on_failure": True,
        "proof_gate": ARCPOD_UPDATE_PROOF_GATE,
        "live_proof_required": True,
        "live_mutation_performed": False,
        "local_mutation_performed": True,
    }
    _reject_secrets(result, path="$.result")
    return result


def _validate_rollout_executor_contract(executor: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(executor, Mapping):
        raise ArcLinkRolloutError(
            "ArcPod update rollout execution requires an explicit fake/local executor contract"
        )
    contract = dict(executor)
    _reject_secrets(contract, path="$.executor")
    adapter = str(contract.get("adapter") or contract.get("adapter_name") or "").strip().lower()
    if adapter not in {"fake", "local"}:
        raise ArcLinkRolloutError(
            "ArcPod update rollout execution requires a fake/local executor contract"
        )
    if not _rollout_truthy(contract.get("record_only")):
        raise ArcLinkRolloutError(
            "ArcPod update rollout execution requires record_only=true so no live command can run"
        )
    raw_results = contract.get("results") if isinstance(contract.get("results"), Mapping) else {}
    results = {
        str(deployment_id): dict(result) if isinstance(result, Mapping) else {"status": str(result)}
        for deployment_id, result in dict(raw_results).items()
    }
    clean = {
        "adapter": adapter,
        "record_only": True,
        "results": results,
    }
    _reject_secrets(clean, path="$.executor")
    return clean


def _rollout_truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _coerce_requested_batch_index(batch_index: int | None) -> int | None:
    if batch_index is None:
        return None
    try:
        value = int(batch_index)
    except (TypeError, ValueError) as exc:
        raise ArcLinkRolloutError("ArcPod update rollout batch_index must be an integer") from exc
    if value < 1:
        raise ArcLinkRolloutError("ArcPod update rollout batch_index must be at least 1")
    return value


def _rollout_metadata_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    metadata = json_loads_safe(str(row.get("metadata_json") or "{}"))
    return dict(metadata) if isinstance(metadata, Mapping) else {}


def _group_rollout_rows_by_batch(rows: Sequence[Mapping[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        item = dict(row)
        metadata = row.get("_metadata") if isinstance(row.get("_metadata"), Mapping) else _rollout_metadata_from_row(item)
        batch_index = int(metadata.get("batch_index") or 0)
        batch_position = int(metadata.get("batch_position") or 0)
        if batch_index < 1:
            raise ArcLinkRolloutError("ArcPod update rollout row is missing batch metadata")
        item["_metadata"] = dict(metadata)
        item["_batch_position"] = batch_position
        grouped.setdefault(batch_index, []).append(item)
    for batch_rows in grouped.values():
        batch_rows.sort(key=lambda row: (int(row.get("_batch_position") or 0), str(row.get("deployment_id") or "")))
    return dict(sorted(grouped.items()))


def _select_executable_rollout_batch(
    batches: Mapping[int, Sequence[Mapping[str, Any]]],
    *,
    requested_batch: int | None,
) -> dict[str, Any]:
    if requested_batch is not None and requested_batch not in batches:
        raise ArcLinkRolloutError(f"unknown ArcPod update rollout batch: {requested_batch}")
    batch_indexes = sorted(batches)
    if requested_batch is not None:
        previous_indexes = [index for index in batch_indexes if index < requested_batch]
        previous_status = _previous_rollout_batches_status(batches, previous_indexes)
        if previous_status:
            return {"status": previous_status, "batch_index": requested_batch, "rows": list(batches[requested_batch])}
        return _batch_execution_status(requested_batch, batches[requested_batch])

    last_completed = 0
    for index in batch_indexes:
        status = _batch_execution_status(index, batches[index])
        if status["status"] == "completed_replay":
            last_completed = index
            continue
        if status["status"] == "failed_replay":
            return {"status": "blocked_failed_previous_batch", "batch_index": index, "rows": list(batches[index])}
        if status["status"] != "execute":
            return status
        return status
    return {
        "status": "completed_replay",
        "batch_index": last_completed,
        "rows": list(batches[last_completed]) if last_completed in batches else [],
    }


def _previous_rollout_batches_status(
    batches: Mapping[int, Sequence[Mapping[str, Any]]],
    indexes: Sequence[int],
) -> str:
    for index in indexes:
        status = _batch_execution_status(index, batches[index])["status"]
        if status == "failed_replay":
            return "blocked_failed_previous_batch"
        if status != "completed_replay":
            return "blocked_previous_batch_incomplete"
    return ""


def _batch_execution_status(index: int, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    statuses = {str(row.get("status") or "") for row in rows}
    if statuses <= {"completed"}:
        return {"status": "completed_replay", "batch_index": index, "rows": list(rows)}
    if statuses & {"failed", "rolled_back"}:
        return {"status": "failed_replay", "batch_index": index, "rows": list(rows)}
    if statuses & {"in_progress", "paused"}:
        return {"status": "blocked_batch_not_ready", "batch_index": index, "rows": list(rows)}
    if statuses <= {"planned"}:
        return {"status": "execute", "batch_index": index, "rows": list(rows)}
    return {"status": "blocked_batch_not_ready", "batch_index": index, "rows": list(rows)}


def _rollout_execution_non_mutating_result(
    *,
    status: str,
    rollout_group_id: str,
    batch_index: int,
    rows: Sequence[Mapping[str, Any]],
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "status": status,
        "operation_kind": "arcpod_update_rollout_batch",
        "rollout_group_id": rollout_group_id,
        "batch_index": batch_index,
        "deployment_ids": [str(row.get("deployment_id") or "") for row in rows],
        "execution": {
            "enabled": True,
            "adapter": str(contract.get("adapter") or ""),
            "record_only": True,
            "commands_run": [],
            "reason": "no batch mutation was performed; rollout state was replayed or blocked",
        },
        "stop_on_failure": True,
        "proof_gate": ARCPOD_UPDATE_PROOF_GATE,
        "live_proof_required": True,
        "live_mutation_performed": False,
        "local_mutation_performed": False,
    }


def _rollout_contract_result(contract: Mapping[str, Any], deployment_id: str) -> dict[str, Any]:
    raw_results = contract.get("results") if isinstance(contract.get("results"), Mapping) else {}
    raw = raw_results.get(deployment_id, {}) if isinstance(raw_results, Mapping) else {}
    result = dict(raw) if isinstance(raw, Mapping) else {"status": str(raw)}
    status = str(result.get("status") or "completed").strip().lower()
    if status in {"", "ok", "ready", "succeeded", "success", "completed"}:
        status = "completed"
    elif status in {"failed", "failure", "error"}:
        status = "failed"
    else:
        raise ArcLinkRolloutError(f"unsupported fake/local rollout result status for {deployment_id}: {status}")
    reason = str(result.get("reason") or result.get("message") or "").strip()
    clean = {"status": status}
    if reason:
        clean["reason"] = reason
    _reject_secrets(clean, path=f"$.executor.results.{deployment_id}")
    return clean


def _recorded_rollout_execution_steps(*, final_status: str) -> list[dict[str, Any]]:
    step_status = "recorded" if final_status == "completed" else "blocked_by_local_failure"
    return [
        {"name": "preserve_state_roots", "status": "recorded"},
        {"name": "refresh_hermes_runtime", "status": step_status},
        {"name": "sync_arclink_skills", "status": step_status},
        {"name": "sync_dashboard_plugins", "status": step_status},
        {"name": "refresh_command_menus", "status": step_status},
        {"name": "verify_managed_context", "status": step_status},
        {"name": "sync_pinned_hermes_docs", "status": step_status},
        {
            "name": "record_health_smoke_placeholders",
            "status": "pending_live_proof" if final_status == "completed" else "blocked_by_local_failure",
            "proof_gate": ARCPOD_UPDATE_PROOF_GATE,
        },
    ]


def _executed_health_smoke(target_version: str, *, final_status: str) -> dict[str, Any]:
    if final_status == "completed":
        return {
            "status": "pending_live_proof",
            "target_version": target_version,
            "checks": [
                {
                    "name": name,
                    "status": "pending_live_execution",
                    "proof_gate": "PG-HERMES" if name == "live_agent_tool_smoke" else "PG-UPGRADE",
                }
                for name in ARCPOD_UPDATE_SMOKE_CHECKS
            ],
        }
    return {
        "status": "blocked_by_local_failure",
        "target_version": target_version,
        "checks": [
            {
                "name": name,
                "status": "blocked_by_local_failure",
                "proof_gate": "PG-HERMES" if name == "live_agent_tool_smoke" else "PG-UPGRADE",
            }
            for name in ARCPOD_UPDATE_SMOKE_CHECKS
        ],
    }


def _rollout_repair_hints(*, final_status: str) -> list[str]:
    if final_status != "failed":
        return []
    return [
        "Inspect the failed Pod's private refresh/apply logs before retrying the rollout batch.",
        "Repair the Pod, rerun the bounded local batch, then run PG-UPGRADE/PG-HERMES before claiming live rolling updates.",
    ]


def _materialization_batches(plan: Mapping[str, Any]) -> list[list[dict[str, Any]]]:
    raw_batches = plan.get("batches")
    if not isinstance(raw_batches, Sequence) or isinstance(raw_batches, (str, bytes)):
        raise ArcLinkRolloutError("ArcPod update rollout plan batches must be a list")
    batches: list[list[dict[str, Any]]] = []
    for raw_batch in raw_batches:
        if not isinstance(raw_batch, Mapping):
            raise ArcLinkRolloutError("ArcPod update rollout batch must be an object")
        deployments = raw_batch.get("deployments")
        if not isinstance(deployments, Sequence) or isinstance(deployments, (str, bytes)):
            raise ArcLinkRolloutError("ArcPod update rollout batch deployments must be a list")
        batch: list[dict[str, Any]] = []
        for raw_deployment in deployments:
            if not isinstance(raw_deployment, Mapping):
                raise ArcLinkRolloutError("ArcPod update rollout batch deployment must be an object")
            deployment = dict(raw_deployment)
            deployment_id = str(deployment.get("deployment_id") or "").strip()
            if not deployment_id:
                raise ArcLinkRolloutError("ArcPod update rollout batch deployment requires an id")
            batch.append(deployment)
        if batch:
            batches.append(batch)
    return batches


def _materialization_candidates(plan: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    raw_candidates = plan.get("candidates")
    if not isinstance(raw_candidates, Sequence) or isinstance(raw_candidates, (str, bytes)):
        raise ArcLinkRolloutError("ArcPod update rollout plan candidates must be a list")
    candidates: dict[str, dict[str, Any]] = {}
    for raw_candidate in raw_candidates:
        if not isinstance(raw_candidate, Mapping):
            raise ArcLinkRolloutError("ArcPod update rollout candidate must be an object")
        candidate = dict(raw_candidate)
        deployment_id = str(candidate.get("deployment_id") or "").strip()
        if deployment_id:
            candidates[deployment_id] = candidate
    return candidates


def _arcpod_update_rollout_group_id(
    plan: Mapping[str, Any],
    *,
    action_id: str,
    idempotency_key: str,
) -> str:
    seed = idempotency_key or action_id or _plan_digest(plan)
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
    return f"rltgrp_{digest}"


def _arcpod_update_rollout_id(
    *,
    rollout_group_id: str,
    deployment_id: str,
    batch_index: int,
    batch_position: int,
) -> str:
    digest = hashlib.sha256(f"{rollout_group_id}:{deployment_id}".encode("utf-8")).hexdigest()[:10]
    return f"rlt_{rollout_group_id[7:15]}_{batch_index:03d}_{batch_position:03d}_{digest}"


def _plan_digest(plan: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(plan), sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _rollout_rows_for_group(conn: sqlite3.Connection, *, rollout_group_id: str) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM arclink_rollouts ORDER BY created_at ASC, rollout_id ASC").fetchall()
    matches: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        metadata = json_loads_safe(str(item.get("metadata_json") or "{}"))
        if str(metadata.get("rollout_group_id") or "") == rollout_group_id:
            item["_metadata"] = metadata
            matches.append(item)
    return matches


def _group_shape_from_existing_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    target_version = ""
    batch_deployment_ids: list[list[str]] = []
    if rows:
        metadata = rows[0].get("_metadata")
        if isinstance(metadata, Mapping):
            target_version = str(metadata.get("target_version") or rows[0].get("version_tag") or "")
            raw_batches = metadata.get("all_batch_deployment_ids")
            if isinstance(raw_batches, Sequence) and not isinstance(raw_batches, (str, bytes)):
                for raw_batch in raw_batches:
                    if isinstance(raw_batch, Sequence) and not isinstance(raw_batch, (str, bytes)):
                        batch_deployment_ids.append([str(item) for item in raw_batch])
    if not batch_deployment_ids:
        grouped: dict[int, list[tuple[int, str]]] = {}
        for row in rows:
            metadata = row.get("_metadata")
            if not isinstance(metadata, Mapping):
                continue
            batch_index = int(metadata.get("batch_index") or 0)
            batch_position = int(metadata.get("batch_position") or 0)
            deployment_id = str(row.get("deployment_id") or "")
            grouped.setdefault(batch_index, []).append((batch_position, deployment_id))
        for batch_index in sorted(grouped):
            batch_deployment_ids.append([deployment_id for _, deployment_id in sorted(grouped[batch_index])])
    return {
        "target_version": target_version,
        "batch_deployment_ids": batch_deployment_ids,
    }


def _materialized_rollout_wave(
    *,
    candidate: Mapping[str, Any],
    rollout_group_id: str,
    batch_index: int,
    batch_position: int,
    batch_deployment_ids: Sequence[str],
) -> dict[str, Any]:
    deployment_id = str(candidate.get("deployment_id") or "")
    target_version = str(candidate.get("target_version") or "")
    return {
        "wave_kind": "arcpod_update",
        "status": "planned_local_job",
        "rollout_group_id": rollout_group_id,
        "batch_index": batch_index,
        "batch_position": batch_position,
        "batch_deployment_ids": list(batch_deployment_ids),
        "deployment_id": deployment_id,
        "current_version": str(candidate.get("current_version") or ""),
        "target_version": target_version,
        "health_smoke": dict(candidate.get("health_smoke") or _pending_health_smoke(target_version)),
        "stop_on_failure": True,
        "proof_gate": ARCPOD_UPDATE_PROOF_GATE,
        "live_proof_required": True,
        "live_mutation_performed": False,
    }


def _materialized_rollout_metadata(
    *,
    plan: Mapping[str, Any],
    candidate: Mapping[str, Any],
    rollout_group_id: str,
    action_id: str,
    idempotency_key: str,
    batch_index: int,
    batch_position: int,
    batch_deployment_ids: Sequence[str],
    all_batch_deployment_ids: Sequence[Sequence[str]],
) -> dict[str, Any]:
    metadata = {
        "job_kind": "arcpod_update_rollout",
        "rollout_group_id": rollout_group_id,
        "action_id": action_id,
        "operation_idempotency_key": idempotency_key,
        "plan_mode": str(plan.get("mode") or ""),
        "target_version": str(plan.get("target_version") or ""),
        "current_version": str(candidate.get("current_version") or ""),
        "batch_index": batch_index,
        "batch_position": batch_position,
        "batch_deployment_ids": list(batch_deployment_ids),
        "all_batch_deployment_ids": [list(batch) for batch in all_batch_deployment_ids],
        "group_batch_count": len(all_batch_deployment_ids),
        "state_roots": dict(candidate.get("state_roots") or {}),
        "rollback_plan": dict(candidate.get("rollback_plan") or {}),
        "health_smoke": dict(candidate.get("health_smoke") or _pending_health_smoke(str(plan.get("target_version") or ""))),
        "backup_freshness": dict(candidate.get("backup_freshness") or {}),
        "proof_gate": ARCPOD_UPDATE_PROOF_GATE,
        "live_proof_required": True,
        "live_mutation_performed": False,
        "local_job_materialized": True,
        "execution": {
            "enabled": False,
            "reason": "local rollout job materialization only; live Pod refresh remains proof-gated",
        },
    }
    _reject_secrets(metadata, path="$.metadata")
    return metadata


def _coerce_batch_size(batch_size: int | None, *, env: Mapping[str, str]) -> int:
    if batch_size is not None:
        try:
            return int(batch_size)
        except (TypeError, ValueError) as exc:
            raise ArcLinkRolloutError("ArcPod update rollout batch_size must be an integer") from exc
    raw = str(env.get("ARCLINK_ROLLOUT_BATCH_SIZE") or "").strip()
    if not raw:
        return ARCPOD_UPDATE_DEFAULT_BATCH_SIZE
    try:
        return int(raw)
    except ValueError as exc:
        raise ArcLinkRolloutError("ARCLINK_ROLLOUT_BATCH_SIZE must be an integer") from exc


def _coerce_max_batch_size(env: Mapping[str, str]) -> int:
    raw = str(env.get("ARCLINK_ROLLOUT_MAX_BATCH_SIZE") or "").strip()
    if not raw:
        return ARCPOD_UPDATE_DEFAULT_MAX_BATCH_SIZE
    try:
        value = int(raw)
    except ValueError as exc:
        raise ArcLinkRolloutError("ARCLINK_ROLLOUT_MAX_BATCH_SIZE must be an integer") from exc
    if value < 1:
        raise ArcLinkRolloutError("ARCLINK_ROLLOUT_MAX_BATCH_SIZE must be at least 1")
    return value


def _clean_requested_deployment_ids(deployment_ids: Sequence[str]) -> list[str]:
    clean: list[str] = []
    seen: set[str] = set()
    for deployment_id in deployment_ids:
        value = str(deployment_id or "").strip()
        if not value or value in seen:
            continue
        _reject_secrets(value, path="$.deployment_ids[]")
        clean.append(value)
        seen.add(value)
    return clean


def _select_update_candidate_deployments(
    conn: sqlite3.Connection,
    *,
    requested_ids: Sequence[str],
) -> list[dict[str, Any]]:
    params: list[Any] = []
    requested_filter = ""
    if requested_ids:
        requested_filter = f"AND deployment_id IN ({','.join('?' for _ in requested_ids)})"
        params.extend(requested_ids)
    rows = conn.execute(
        f"""
        SELECT deployment_id, user_id, prefix, status, metadata_json, created_at, updated_at
        FROM arclink_deployments
        WHERE status IN ({','.join('?' for _ in sorted(ARCPOD_UPDATE_CANDIDATE_STATUSES))})
          AND COALESCE(metadata_json, '') NOT LIKE '%"operator_agent"%'
        {requested_filter}
        ORDER BY created_at ASC, deployment_id ASC
        """,
        [*sorted(ARCPOD_UPDATE_CANDIDATE_STATUSES), *params],
    ).fetchall()
    return [dict(row) for row in rows]


def _deployment_current_version(metadata: Mapping[str, Any]) -> str:
    for key in (
        "arclink_release",
        "release_version",
        "version_tag",
        "current_version",
        "arclink_version",
    ):
        value = str(metadata.get(key) or "").strip()
        if value:
            return value
    for key in ("component_pins", "pins", "release_pins"):
        pins = metadata.get(key)
        if not isinstance(pins, Mapping):
            continue
        for pin_key in ("arclink", "arclink_repo", "repo", "release"):
            value = str(pins.get(pin_key) or "").strip()
            if value:
                return value
    return ""


def _deployment_state_roots(metadata: Mapping[str, Any]) -> dict[str, str]:
    raw = metadata.get("state_roots")
    if not isinstance(raw, Mapping):
        return {}
    roots: dict[str, str] = {}
    for key, value in raw.items():
        clean_key = str(key or "").strip()
        clean_value = str(value or "").strip()
        if clean_key and clean_value:
            roots[clean_key] = clean_value
    return roots


def _deployment_service_health(conn: sqlite3.Connection, deployment_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT service_name, status, checked_at, detail_json
        FROM arclink_service_health
        WHERE deployment_id = ?
        ORDER BY service_name
        """,
        (deployment_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _health_blockers(deployment_id: str, health_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    if not health_rows:
        return [
            {
                "deployment_id": deployment_id,
                "code": "service_health_missing",
                "message": "no local service health rows exist for this deployment",
            }
        ]
    blockers: list[dict[str, str]] = []
    for row in health_rows:
        status = str(row.get("status") or "").strip().lower()
        if status not in ARCPOD_UPDATE_HEALTHY_STATUSES:
            blockers.append(
                {
                    "deployment_id": deployment_id,
                    "code": "service_health_unhealthy",
                    "message": f"{row.get('service_name')}: service health is {status or 'unknown'}",
                }
            )
    return blockers


def _deployment_rollback_plan(
    *,
    deployment_id: str,
    current_version: str,
    state_roots: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "deployment_id": deployment_id,
        "previous_version": current_version,
        "actions": [
            "preserve_state_roots",
            "restore_previous_release_metadata",
            "restart_previous_services",
        ],
        "state_roots": dict(state_roots),
    }


def _pending_health_smoke(target_version: str) -> dict[str, Any]:
    return {
        "status": "pending_live_execution",
        "target_version": target_version,
        "checks": [
            {
                "name": name,
                "status": "pending_live_execution",
                "proof_gate": "PG-HERMES" if name == "live_agent_tool_smoke" else "PG-UPGRADE",
            }
            for name in ARCPOD_UPDATE_SMOKE_CHECKS
        ],
    }


def _batch_candidates(candidates: Sequence[Mapping[str, Any]], batch_size: int) -> list[dict[str, Any]]:
    batches: list[dict[str, Any]] = []
    for start in range(0, len(candidates), batch_size):
        items = [dict(candidate) for candidate in candidates[start:start + batch_size]]
        batches.append(
            {
                "batch_index": len(batches) + 1,
                "deployment_ids": [str(item["deployment_id"]) for item in items],
                "deployments": items,
                "health_smoke": _pending_health_smoke(str(items[0]["target_version"]) if items else ""),
                "stop_on_failure": True,
                "status": "planned_dry_run",
            }
        )
    return batches


def rollout_version_drift(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
) -> dict[str, Any]:
    """Show current vs latest rollout version for a deployment."""
    latest = conn.execute(
        """
        SELECT * FROM arclink_rollouts
        WHERE deployment_id = ? AND status IN ('completed', 'in_progress')
        ORDER BY created_at DESC LIMIT 1
        """,
        (deployment_id,),
    ).fetchone()
    planned = conn.execute(
        "SELECT * FROM arclink_rollouts WHERE deployment_id = ? AND status = 'planned' ORDER BY created_at DESC LIMIT 1",
        (deployment_id,),
    ).fetchone()
    return {
        "deployment_id": deployment_id,
        "current_version": str(latest["version_tag"]) if latest else "",
        "current_rollout_id": str(latest["rollout_id"]) if latest else "",
        "current_status": str(latest["status"]) if latest else "",
        "pending_version": str(planned["version_tag"]) if planned else "",
        "pending_rollout_id": str(planned["rollout_id"]) if planned else "",
        "has_drift": bool(planned and latest and planned["version_tag"] != latest["version_tag"]),
    }
