#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_module(filename: str, name: str):
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    path = PYTHON_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def memory_db(control):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    control.ensure_schema(conn)
    return conn


def _rollback_plan():
    return {
        "actions": ["preserve_state_roots", "stop_rendered_services"],
        "state_roots": {"root": "/arcdata/deployments/dep_1", "vault": "/arcdata/deployments/dep_1/vault"},
    }


def _state_roots(deployment_id: str) -> dict[str, str]:
    root = f"/arcdata/deployments/{deployment_id}"
    return {
        "root": root,
        "config": f"{root}/config",
        "state": f"{root}/state",
        "vault": f"{root}/vault",
        "hermes_home": f"{root}/state/hermes-home",
    }


def _seed_arcpod(
    control,
    conn,
    *,
    deployment_id: str,
    current_version: str = "v1.0.0",
    status: str = "active",
    state_roots: dict[str, str] | None = None,
    health_status: str = "healthy",
) -> None:
    user_id = f"user_{deployment_id}"
    control.upsert_arclink_user(
        conn,
        user_id=user_id,
        email=f"{deployment_id}@example.test",
        display_name=f"{deployment_id} Captain",
        entitlement_state="paid",
    )
    metadata = {
        "release_version": current_version,
        "state_roots": _state_roots(deployment_id) if state_roots is None else state_roots,
    }
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id=deployment_id,
        user_id=user_id,
        prefix=f"{deployment_id.replace('_', '-').replace('root', 'rt')}-pod",
        base_domain="example.test",
        status=status,
        metadata=metadata,
    )
    for service_name in ("hermes-gateway", "hermes-dashboard", "qmd-mcp"):
        control.upsert_arclink_service_health(
            conn,
            deployment_id=deployment_id,
            service_name=service_name,
            status=health_status,
        )


def _rollout_rows(conn) -> list[dict]:
    return [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM arclink_rollouts ORDER BY created_at ASC, rollout_id ASC",
        ).fetchall()
    ]


def test_create_rollout() -> None:
    control = load_module("arclink_control.py", "arclink_control_rlt_create")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_create")
    conn = memory_db(control)
    r = rollout.create_rollout(
        conn,
        deployment_id="dep_1",
        version_tag="v1.2.0",
        waves=[{"hosts": ["h1"], "percentage": 50}, {"hosts": ["h2"], "percentage": 100}],
        rollback_plan=_rollback_plan(),
    )
    expect(r["status"] == "planned", "initial status is planned")
    expect(int(r["wave_count"]) == 2, "two waves")
    expect(int(r["current_wave"]) == 0, "no waves advanced yet")
    print("PASS test_create_rollout")


def test_advance_rollout_waves() -> None:
    control = load_module("arclink_control.py", "arclink_control_rlt_advance")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_advance")
    conn = memory_db(control)
    r = rollout.create_rollout(
        conn, deployment_id="dep_1", version_tag="v1.0",
        waves=[{"hosts": ["h1"]}, {"hosts": ["h2"]}],
        rollback_plan=_rollback_plan(),
    )
    r = rollout.advance_rollout_wave(conn, rollout_id=r["rollout_id"])
    expect(r["status"] == "in_progress", "in progress after first wave")
    expect(int(r["current_wave"]) == 1, "wave 1")
    r = rollout.advance_rollout_wave(conn, rollout_id=r["rollout_id"])
    expect(r["status"] == "completed", "completed after all waves")
    expect(int(r["current_wave"]) == 2, "wave 2")
    print("PASS test_advance_rollout_waves")


def test_pause_rollout() -> None:
    control = load_module("arclink_control.py", "arclink_control_rlt_pause")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_pause")
    conn = memory_db(control)
    r = rollout.create_rollout(
        conn, deployment_id="dep_1", version_tag="v1.0",
        waves=[{"hosts": ["h1"]}, {"hosts": ["h2"]}],
        rollback_plan=_rollback_plan(),
    )
    r = rollout.advance_rollout_wave(conn, rollout_id=r["rollout_id"])
    r = rollout.pause_rollout(conn, rollout_id=r["rollout_id"])
    expect(r["status"] == "paused", "paused")
    print("PASS test_pause_rollout")


def test_fail_rollout() -> None:
    control = load_module("arclink_control.py", "arclink_control_rlt_fail")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_fail")
    conn = memory_db(control)
    r = rollout.create_rollout(
        conn, deployment_id="dep_1", version_tag="v1.0",
        waves=[{"hosts": ["h1"]}],
        rollback_plan=_rollback_plan(),
    )
    r = rollout.fail_rollout(conn, rollout_id=r["rollout_id"], reason="health check failed")
    expect(r["status"] == "failed", "failed")
    print("PASS test_fail_rollout")


def test_rollback_preserves_state_roots() -> None:
    control = load_module("arclink_control.py", "arclink_control_rlt_rb")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_rb")
    conn = memory_db(control)
    r = rollout.create_rollout(
        conn, deployment_id="dep_1", version_tag="v1.0",
        waves=[{"hosts": ["h1"]}, {"hosts": ["h2"]}],
        rollback_plan=_rollback_plan(),
    )
    r = rollout.advance_rollout_wave(conn, rollout_id=r["rollout_id"])
    expect(r["status"] == "in_progress", "in progress after first wave")
    r = rollout.rollback_rollout(conn, rollout_id=r["rollout_id"], reason="regression found")
    expect(r["status"] == "rolled_back", "rolled back")
    # Verify events recorded
    events = conn.execute(
        "SELECT * FROM arclink_events WHERE event_type = 'rollout_rolled_back'",
    ).fetchall()
    expect(len(events) == 1, "rollback event recorded")
    print("PASS test_rollback_preserves_state_roots")


def test_rollback_plan_requires_preserve_state_roots() -> None:
    control = load_module("arclink_control.py", "arclink_control_rlt_req")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_req")
    conn = memory_db(control)
    try:
        rollout.create_rollout(
            conn, deployment_id="dep_1", version_tag="v1.0",
            waves=[{"hosts": ["h1"]}],
            rollback_plan={"actions": ["stop_rendered_services"]},
        )
        raise AssertionError("should require preserve_state_roots")
    except rollout.ArcLinkRolloutError:
        pass
    print("PASS test_rollback_plan_requires_preserve_state_roots")


def test_version_drift() -> None:
    control = load_module("arclink_control.py", "arclink_control_rlt_drift")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_drift")
    conn = memory_db(control)
    r = rollout.create_rollout(
        conn, deployment_id="dep_1", version_tag="v1.0",
        waves=[{"hosts": ["h1"]}],
        rollback_plan=_rollback_plan(),
    )
    rollout.advance_rollout_wave(conn, rollout_id=r["rollout_id"])
    rollout.create_rollout(
        conn, deployment_id="dep_1", version_tag="v2.0",
        waves=[{"hosts": ["h1"]}],
        rollback_plan=_rollback_plan(),
    )
    drift = rollout.rollout_version_drift(conn, deployment_id="dep_1")
    expect(drift["current_version"] == "v1.0", "current is v1.0")
    expect(drift["pending_version"] == "v2.0", "pending is v2.0")
    expect(drift["has_drift"] is True, "drift detected")
    print("PASS test_version_drift")


def test_list_rollouts() -> None:
    control = load_module("arclink_control.py", "arclink_control_rlt_list")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_list")
    conn = memory_db(control)
    rollout.create_rollout(
        conn, deployment_id="dep_1", version_tag="v1.0",
        waves=[{"hosts": ["h1"]}], rollback_plan=_rollback_plan(),
    )
    rollout.create_rollout(
        conn, deployment_id="dep_2", version_tag="v2.0",
        waves=[{"hosts": ["h1"]}], rollback_plan=_rollback_plan(),
    )
    all_rollouts = rollout.list_rollouts(conn)
    expect(len(all_rollouts) == 2, "two rollouts")
    dep1_rollouts = rollout.list_rollouts(conn, deployment_id="dep_1")
    expect(len(dep1_rollouts) == 1, "one for dep_1")
    print("PASS test_list_rollouts")


def test_cannot_advance_completed() -> None:
    control = load_module("arclink_control.py", "arclink_control_rlt_adv_done")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_adv_done")
    conn = memory_db(control)
    r = rollout.create_rollout(
        conn, deployment_id="dep_1", version_tag="v1.0",
        waves=[{"hosts": ["h1"]}], rollback_plan=_rollback_plan(),
    )
    rollout.advance_rollout_wave(conn, rollout_id=r["rollout_id"])
    try:
        rollout.advance_rollout_wave(conn, rollout_id=r["rollout_id"])
        raise AssertionError("should not advance completed rollout")
    except rollout.ArcLinkRolloutError:
        pass
    print("PASS test_cannot_advance_completed")


def test_plan_arcpod_update_rollout_batches_without_mutation() -> None:
    control = load_module("arclink_control.py", "arclink_control_rlt_plan_batch_control")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_plan_batch")
    conn = memory_db(control)
    for deployment_id in ("dep_a", "dep_b", "dep_c"):
        _seed_arcpod(control, conn, deployment_id=deployment_id)
    before_rollouts = conn.execute("SELECT COUNT(*) AS n FROM arclink_rollouts").fetchone()["n"]
    before_actions = conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"]

    plan = rollout.plan_arcpod_update_rollout(conn, target_version="v2.0.0", batch_size=2)

    after_rollouts = conn.execute("SELECT COUNT(*) AS n FROM arclink_rollouts").fetchone()["n"]
    after_actions = conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"]
    expect(plan["status"] == "ready", str(plan))
    expect(plan["mode"] == "dry_run", str(plan))
    expect(plan["candidate_count"] == 3, str(plan))
    expect(plan["batch_count"] == 2, str(plan))
    expect(plan["batches"][0]["deployment_ids"] == ["dep_a", "dep_b"], str(plan["batches"]))
    expect(plan["batches"][1]["deployment_ids"] == ["dep_c"], str(plan["batches"]))
    expect(plan["stop_on_failure"] is True, str(plan))
    expect(plan["execution"]["enabled"] is False, str(plan["execution"]))
    expect(plan["proof_gate"] == "PG-UPGRADE/PG-HERMES", str(plan))
    expect("preserve_state_roots" in plan["rollback_plan"]["actions"], str(plan["rollback_plan"]))
    expect(plan["candidates"][0]["health_smoke"]["status"] == "pending_live_execution", str(plan["candidates"][0]))
    expect(before_rollouts == after_rollouts, "dry-run planner must not create rollout rows")
    expect(before_actions == after_actions, "dry-run planner must not queue action intents")
    print("PASS test_plan_arcpod_update_rollout_batches_without_mutation")


def test_plan_arcpod_update_rollout_blocks_unhealthy_or_missing_state_roots() -> None:
    control = load_module("arclink_control.py", "arclink_control_rlt_plan_block_control")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_plan_block")
    conn = memory_db(control)
    _seed_arcpod(control, conn, deployment_id="dep_ready")
    _seed_arcpod(control, conn, deployment_id="dep_missing_roots", state_roots={})
    _seed_arcpod(control, conn, deployment_id="dep_unhealthy", health_status="degraded")

    plan = rollout.plan_arcpod_update_rollout(conn, target_version="v2.0.0", batch_size=2)
    codes = {item["code"] for item in plan["preflight_blockers"]}

    expect(plan["status"] == "blocked", str(plan))
    expect(plan["ready_count"] == 1, str(plan))
    expect(plan["blocked_count"] == 2, str(plan))
    expect(plan["batches"] == [], str(plan["batches"]))
    expect("state_roots_missing" in codes, str(plan["preflight_blockers"]))
    expect("service_health_unhealthy" in codes, str(plan["preflight_blockers"]))
    expect(any("dep_missing_roots" in item for item in plan["repair_summary"]), str(plan["repair_summary"]))
    expect(any("dep_unhealthy" in item for item in plan["repair_summary"]), str(plan["repair_summary"]))
    expect(plan["state_preservation"]["missing_state_root_deployments"] == ["dep_missing_roots"], str(plan["state_preservation"]))
    print("PASS test_plan_arcpod_update_rollout_blocks_unhealthy_or_missing_state_roots")


def test_plan_arcpod_update_rollout_rejects_invalid_batch_sizes() -> None:
    control = load_module("arclink_control.py", "arclink_control_rlt_plan_batch_limits_control")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_plan_batch_limits")
    conn = memory_db(control)
    _seed_arcpod(control, conn, deployment_id="dep_batch_limits")

    for bad_size in (0, -1):
        try:
            rollout.plan_arcpod_update_rollout(conn, target_version="v2.0.0", batch_size=bad_size)
            raise AssertionError(f"batch size {bad_size} should be rejected")
        except rollout.ArcLinkRolloutError:
            pass
    try:
        rollout.plan_arcpod_update_rollout(
            conn,
            target_version="v2.0.0",
            batch_size=3,
            env={"ARCLINK_ROLLOUT_MAX_BATCH_SIZE": "2"},
        )
        raise AssertionError("batch size above policy max should be rejected")
    except rollout.ArcLinkRolloutError:
        pass
    expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_rollouts").fetchone()["n"] == 0, "no rollout rows")
    expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"] == 0, "no actions queued")
    print("PASS test_plan_arcpod_update_rollout_rejects_invalid_batch_sizes")


def test_plan_arcpod_update_rollout_skips_already_current_deployments() -> None:
    control = load_module("arclink_control.py", "arclink_control_rlt_plan_current_control")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_plan_current")
    conn = memory_db(control)
    _seed_arcpod(control, conn, deployment_id="dep_current", current_version="v2.0.0")

    plan = rollout.plan_arcpod_update_rollout(conn, target_version="v2.0.0", batch_size=1)

    expect(plan["status"] == "empty", str(plan))
    expect(plan["candidate_count"] == 0, str(plan))
    expect(plan["already_current_count"] == 1, str(plan))
    expect(plan["batches"] == [], str(plan))
    print("PASS test_plan_arcpod_update_rollout_skips_already_current_deployments")


def test_plan_arcpod_update_rollout_skips_operator_control_stack_identity() -> None:
    control = load_module("arclink_control.py", "arclink_control_rlt_plan_operator_skip_control")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_plan_operator_skip")
    conn = memory_db(control)
    _seed_arcpod(control, conn, deployment_id="dep_real")
    _seed_arcpod(control, conn, deployment_id="operator")
    conn.execute(
        """
        UPDATE arclink_deployments
           SET user_id = 'operator',
               prefix = 'operator-helm',
               metadata_json = ?
         WHERE deployment_id = 'operator'
        """,
        (
            json.dumps(
                {
                    "operator_agent": True,
                    "operator_agent_runtime": "control-stack",
                    "release_version": "v1.0.0",
                    "state_roots": _state_roots("operator"),
                },
                sort_keys=True,
            ),
        ),
    )
    conn.commit()

    plan = rollout.plan_arcpod_update_rollout(conn, target_version="v2.0.0", batch_size=1)

    expect(plan["status"] == "ready", str(plan))
    expect(plan["candidate_count"] == 1, str(plan))
    expect(plan["batches"][0]["deployment_ids"] == ["dep_real"], str(plan["batches"]))
    print("PASS test_plan_arcpod_update_rollout_skips_operator_control_stack_identity")


def test_materialize_arcpod_update_rollout_job_preserves_batches_and_gates() -> None:
    control = load_module("arclink_control.py", "arclink_control_rlt_materialize_control")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_materialize")
    conn = memory_db(control)
    for deployment_id in ("dep_job_a", "dep_job_b", "dep_job_c"):
        _seed_arcpod(control, conn, deployment_id=deployment_id)

    plan = rollout.plan_arcpod_update_rollout(conn, target_version="v2.0.0", batch_size=2)
    job = rollout.materialize_arcpod_update_rollout_job(
        conn,
        plan=plan,
        action_id="act_rollout_three",
        idempotency_key="rollout-three-pods",
    )
    rows = _rollout_rows(conn)

    expect(job["status"] == "queued_local_job", str(job))
    expect(job["operation_kind"] == "arcpod_update_rollout", str(job))
    expect(job["rollout_count"] == 3, str(job))
    expect(job["batch_count"] == 2, str(job))
    expect(job["batch_deployment_ids"] == [["dep_job_a", "dep_job_b"], ["dep_job_c"]], str(job))
    expect(job["live_mutation_performed"] is False, str(job))
    expect(job["live_proof_required"] is True, str(job))
    expect(job["proof_gate"] == "PG-UPGRADE/PG-HERMES", str(job))
    expect(len(rows) == 3, str(rows))
    expect([row["deployment_id"] for row in rows] == ["dep_job_a", "dep_job_b", "dep_job_c"], str(rows))
    expect(all(row["status"] == "planned" for row in rows), str(rows))
    expect(all(row["version_tag"] == "v2.0.0" for row in rows), str(rows))
    metadata = [json.loads(row["metadata_json"]) for row in rows]
    expect([item["batch_index"] for item in metadata] == [1, 1, 2], str(metadata))
    expect([item["batch_position"] for item in metadata] == [1, 2, 1], str(metadata))
    expect(all(item["rollout_group_id"] == job["rollout_group_id"] for item in metadata), str(metadata))
    expect(all(item["health_smoke"]["status"] == "pending_live_execution" for item in metadata), str(metadata))
    expect(all(item["backup_freshness"]["status"] == "not_checked_in_dry_run" for item in metadata), str(metadata))
    expect(all(item["proof_gate"] == "PG-UPGRADE/PG-HERMES" for item in metadata), str(metadata))
    rollback = [json.loads(row["rollback_plan_json"]) for row in rows]
    expect(all("preserve_state_roots" in item["actions"] for item in rollback), str(rollback))
    expect(all(item["state_roots"]["root"].startswith("/arcdata/deployments/dep_job_") for item in rollback), str(rollback))
    waves = [json.loads(row["waves_json"]) for row in rows]
    expect(all(item[0]["status"] == "planned_local_job" for item in waves), str(waves))
    expect("secret://" not in json.dumps(job, sort_keys=True), str(job))
    print("PASS test_materialize_arcpod_update_rollout_job_preserves_batches_and_gates")


def test_materialize_arcpod_update_rollout_job_is_idempotent() -> None:
    control = load_module("arclink_control.py", "arclink_control_rlt_materialize_idem_control")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_materialize_idem")
    conn = memory_db(control)
    for deployment_id in ("dep_idem_a", "dep_idem_b"):
        _seed_arcpod(control, conn, deployment_id=deployment_id)

    plan = rollout.plan_arcpod_update_rollout(conn, target_version="v2.0.0", batch_size=1)
    first = rollout.materialize_arcpod_update_rollout_job(
        conn,
        plan=plan,
        action_id="act_rollout_idem_1",
        idempotency_key="rollout-idem",
    )
    second = rollout.materialize_arcpod_update_rollout_job(
        conn,
        plan=plan,
        action_id="act_rollout_idem_2",
        idempotency_key="rollout-idem",
    )
    rows = _rollout_rows(conn)

    expect(first["rollout_group_id"] == second["rollout_group_id"], str((first, second)))
    expect(first["rollout_ids"] == second["rollout_ids"], str((first, second)))
    expect(first["created_rollout_count"] == 2, str(first))
    expect(second["created_rollout_count"] == 0, str(second))
    expect(len(rows) == 2, str(rows))
    print("PASS test_materialize_arcpod_update_rollout_job_is_idempotent")


def test_materialize_arcpod_update_rollout_job_refuses_blocked_or_empty_plan() -> None:
    control = load_module("arclink_control.py", "arclink_control_rlt_materialize_blocked_control")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_materialize_blocked")
    conn = memory_db(control)
    _seed_arcpod(control, conn, deployment_id="dep_ready")
    _seed_arcpod(control, conn, deployment_id="dep_blocked", health_status="failed")

    blocked = rollout.plan_arcpod_update_rollout(conn, target_version="v2.0.0", batch_size=1)
    try:
        rollout.materialize_arcpod_update_rollout_job(
            conn,
            plan=blocked,
            action_id="act_rollout_blocked",
            idempotency_key="rollout-blocked",
        )
        raise AssertionError("blocked rollout plan should not materialize")
    except rollout.ArcLinkRolloutError as exc:
        expect("ready" in str(exc) or "preflight" in str(exc), str(exc))

    empty = rollout.plan_arcpod_update_rollout(
        conn,
        target_version="v2.0.0",
        batch_size=1,
        deployment_ids=["dep_missing"],
    )
    try:
        rollout.materialize_arcpod_update_rollout_job(
            conn,
            plan=empty,
            action_id="act_rollout_empty",
            idempotency_key="rollout-empty",
        )
        raise AssertionError("empty rollout plan should not materialize")
    except rollout.ArcLinkRolloutError as exc:
        expect("ready" in str(exc) or "preflight" in str(exc), str(exc))

    expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_rollouts").fetchone()["n"] == 0, "no rollout rows")
    print("PASS test_materialize_arcpod_update_rollout_job_refuses_blocked_or_empty_plan")


def test_execute_arcpod_update_rollout_batch_refuses_without_executor_contract() -> None:
    control = load_module("arclink_control.py", "arclink_control_rlt_execute_refuse_control")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_execute_refuse")
    conn = memory_db(control)
    _seed_arcpod(control, conn, deployment_id="dep_exec_refuse")

    plan = rollout.plan_arcpod_update_rollout(conn, target_version="v2.0.0", batch_size=1)
    job = rollout.materialize_arcpod_update_rollout_job(
        conn,
        plan=plan,
        action_id="act_rollout_exec_refuse",
        idempotency_key="rollout-exec-refuse",
    )
    try:
        rollout.execute_arcpod_update_rollout_batch(
            conn,
            rollout_group_id=job["rollout_group_id"],
        )
        raise AssertionError("rollout execution should require an explicit fake/local executor contract")
    except rollout.ArcLinkRolloutError as exc:
        expect("executor contract" in str(exc), str(exc))

    row = conn.execute("SELECT * FROM arclink_rollouts WHERE deployment_id = 'dep_exec_refuse'").fetchone()
    expect(row["status"] == "planned", str(dict(row)))
    try:
        rollout.execute_arcpod_update_rollout_batch(
            conn,
            rollout_group_id=job["rollout_group_id"],
            executor={
                "adapter": "fake",
                "record_only": True,
                "results": {"dep_exec_refuse": {"status": "mystery"}},
            },
        )
        raise AssertionError("unsupported fake/local result status should fail before mutation")
    except rollout.ArcLinkRolloutError as exc:
        expect("unsupported fake/local rollout result status" in str(exc), str(exc))
    row = conn.execute("SELECT * FROM arclink_rollouts WHERE deployment_id = 'dep_exec_refuse'").fetchone()
    expect(row["status"] == "planned", str(dict(row)))
    print("PASS test_execute_arcpod_update_rollout_batch_refuses_without_executor_contract")


def test_execute_arcpod_update_rollout_batch_completes_batch_and_replays() -> None:
    control = load_module("arclink_control.py", "arclink_control_rlt_execute_success_control")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_execute_success")
    conn = memory_db(control)
    for deployment_id in ("dep_exec_a", "dep_exec_b", "dep_exec_c"):
        _seed_arcpod(control, conn, deployment_id=deployment_id)

    plan = rollout.plan_arcpod_update_rollout(conn, target_version="v2.0.0", batch_size=2)
    job = rollout.materialize_arcpod_update_rollout_job(
        conn,
        plan=plan,
        action_id="act_rollout_exec_success",
        idempotency_key="rollout-exec-success",
    )

    first = rollout.execute_arcpod_update_rollout_batch(
        conn,
        rollout_group_id=job["rollout_group_id"],
        executor={"adapter": "fake", "record_only": True},
    )
    rows = _rollout_rows(conn)
    by_dep = {row["deployment_id"]: row for row in rows}

    expect(first["status"] == "completed", str(first))
    expect(first["batch_index"] == 1, str(first))
    expect(first["deployment_ids"] == ["dep_exec_a", "dep_exec_b"], str(first))
    expect(first["local_mutation_performed"] is True, str(first))
    expect(first["live_mutation_performed"] is False, str(first))
    expect(by_dep["dep_exec_a"]["status"] == "completed", str(by_dep))
    expect(by_dep["dep_exec_b"]["status"] == "completed", str(by_dep))
    expect(by_dep["dep_exec_c"]["status"] == "planned", str(by_dep))
    metadata = json.loads(by_dep["dep_exec_a"]["metadata_json"])
    expect(metadata["execution"]["status"] == "completed", str(metadata))
    expect(metadata["execution"]["adapter"] == "fake", str(metadata))
    expect(metadata["execution"]["record_only"] is True, str(metadata))
    expect(metadata["health_smoke"]["status"] == "pending_live_proof", str(metadata))
    expect(metadata["proof_gate"] == "PG-UPGRADE/PG-HERMES", str(metadata))
    expect("secret://" not in json.dumps(first, sort_keys=True), str(first))

    replay = rollout.execute_arcpod_update_rollout_batch(
        conn,
        rollout_group_id=job["rollout_group_id"],
        batch_index=1,
        executor={"adapter": "fake", "record_only": True},
    )
    expect(replay["status"] == "completed_replay", str(replay))
    expect(replay["local_mutation_performed"] is False, str(replay))
    expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_rollouts").fetchone()["n"] == 3, "replay must not duplicate rows")

    second = rollout.execute_arcpod_update_rollout_batch(
        conn,
        rollout_group_id=job["rollout_group_id"],
        executor={"adapter": "fake", "record_only": True},
    )
    expect(second["status"] == "completed", str(second))
    expect(second["batch_index"] == 2, str(second))
    expect(all(row["status"] == "completed" for row in _rollout_rows(conn)), str(_rollout_rows(conn)))
    print("PASS test_execute_arcpod_update_rollout_batch_completes_batch_and_replays")


def test_execute_arcpod_update_rollout_batch_failure_halts_later_batches() -> None:
    control = load_module("arclink_control.py", "arclink_control_rlt_execute_fail_control")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_execute_fail")
    conn = memory_db(control)
    for deployment_id in ("dep_exec_fail_a", "dep_exec_fail_b", "dep_exec_fail_c"):
        _seed_arcpod(control, conn, deployment_id=deployment_id)

    plan = rollout.plan_arcpod_update_rollout(conn, target_version="v2.0.0", batch_size=2)
    job = rollout.materialize_arcpod_update_rollout_job(
        conn,
        plan=plan,
        action_id="act_rollout_exec_fail",
        idempotency_key="rollout-exec-fail",
    )
    failed = rollout.execute_arcpod_update_rollout_batch(
        conn,
        rollout_group_id=job["rollout_group_id"],
        executor={
            "adapter": "fake",
            "record_only": True,
            "results": {"dep_exec_fail_b": {"status": "failed", "reason": "fake health gate failed"}},
        },
    )
    rows = {row["deployment_id"]: row for row in _rollout_rows(conn)}
    failed_meta = json.loads(rows["dep_exec_fail_b"]["metadata_json"])

    expect(failed["status"] == "failed", str(failed))
    expect(failed["stop_on_failure"] is True, str(failed))
    expect(rows["dep_exec_fail_a"]["status"] == "completed", str(rows))
    expect(rows["dep_exec_fail_b"]["status"] == "failed", str(rows))
    expect(rows["dep_exec_fail_c"]["status"] == "planned", str(rows))
    expect(failed_meta["execution"]["status"] == "failed", str(failed_meta))
    expect(failed_meta["health_smoke"]["status"] == "blocked_by_local_failure", str(failed_meta))
    expect(failed_meta["repair_hints"], str(failed_meta))

    blocked = rollout.execute_arcpod_update_rollout_batch(
        conn,
        rollout_group_id=job["rollout_group_id"],
        executor={"adapter": "fake", "record_only": True},
    )
    expect(blocked["status"] == "blocked_failed_previous_batch", str(blocked))
    expect(blocked["local_mutation_performed"] is False, str(blocked))
    expect(rows["dep_exec_fail_c"]["status"] == "planned", str(rows))
    expect("secret://" not in json.dumps(failed, sort_keys=True), str(failed))
    print("PASS test_execute_arcpod_update_rollout_batch_failure_halts_later_batches")


if __name__ == "__main__":
    test_create_rollout()
    test_advance_rollout_waves()
    test_pause_rollout()
    test_fail_rollout()
    test_rollback_preserves_state_roots()
    test_rollback_plan_requires_preserve_state_roots()
    test_version_drift()
    test_list_rollouts()
    test_cannot_advance_completed()
    test_plan_arcpod_update_rollout_batches_without_mutation()
    test_plan_arcpod_update_rollout_blocks_unhealthy_or_missing_state_roots()
    test_plan_arcpod_update_rollout_rejects_invalid_batch_sizes()
    test_plan_arcpod_update_rollout_skips_already_current_deployments()
    test_plan_arcpod_update_rollout_skips_operator_control_stack_identity()
    test_materialize_arcpod_update_rollout_job_preserves_batches_and_gates()
    test_materialize_arcpod_update_rollout_job_is_idempotent()
    test_materialize_arcpod_update_rollout_job_refuses_blocked_or_empty_plan()
    test_execute_arcpod_update_rollout_batch_refuses_without_executor_contract()
    test_execute_arcpod_update_rollout_batch_completes_batch_and_replays()
    test_execute_arcpod_update_rollout_batch_failure_halts_later_batches()
    print("\nAll rollout tests passed.")
