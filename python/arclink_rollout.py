#!/usr/bin/env python3
"""ArcLink rollout/rollback model: canary waves, pause, rollback records."""
from __future__ import annotations

import json
import secrets
import sqlite3
from typing import Any, Mapping, Sequence

from almanac_control import append_arclink_audit, append_arclink_event, utc_now_iso
from arclink_boundary import json_dumps_safe, json_loads_safe, reject_secret_material


class ArcLinkRolloutError(ValueError):
    pass


ROLLOUT_STATUSES = frozenset({"planned", "in_progress", "paused", "completed", "failed", "rolled_back"})


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
