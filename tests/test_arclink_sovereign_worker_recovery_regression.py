#!/usr/bin/env python3
"""Regression tests: cancelled-apply must not mark active; H1 orphan teardown."""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

from arclink_test_helpers import expect, load_module


def memory_db(control):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    control.ensure_schema(conn)
    return conn


def _seed_ready_deployment(control, conn):
    control.upsert_arclink_user(
        conn, user_id="user_1", email="u@example.test", display_name="U", entitlement_state="paid"
    )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_1",
        user_id="user_1",
        prefix="amber-vault-1234",
        base_domain="example.test",
        status="provisioning_ready",
    )
    conn.commit()


def _worker_config(worker_mod, tmpdir):
    return worker_mod.SovereignWorkerConfig(
        enabled=True,
        ingress_mode="domain",
        base_domain="example.test",
        edge_target="edge.example.test",
        tailscale_dns_name="",
        tailscale_host_strategy="path",
        tailscale_https_port="443",
        tailscale_notion_path="/notion/webhook",
        state_root_base=f"{tmpdir}/deployments",
        cloudflare_zone_id="zone_fake",
        executor_adapter="fake",
        batch_size=5,
        max_attempts=3,
        running_stale_seconds=60,
        register_local_host=False,
        local_hostname="worker-1.example.test",
        local_ssh_host="",
        local_ssh_user="root",
        local_region="us-east",
        local_capacity_slots=2,
        secret_store_dir=Path(tmpdir) / "secrets",
        env={
            "ARCLINK_BASE_DOMAIN": "example.test",
            "ARCLINK_PRIMARY_PROVIDER": "chutes",
            "ARCLINK_CHUTES_DEFAULT_MODEL": "moonshotai/Kimi-K2.6-TEE",
            "ARCLINK_FLEET_SHARE_HUB_ROOT": f"{tmpdir}/captains",
        },
    )


def test_cancelled_apply_job_does_not_mark_deployment_active() -> None:
    control = load_module("arclink_control.py", "arclink_control_cancelled_apply")
    worker_mod = load_module("arclink_sovereign_worker.py", "arclink_sovereign_worker_cancelled_apply")
    conn = memory_db(control)
    _seed_ready_deployment(control, conn)

    job = worker_mod._ensure_apply_job(conn, deployment_id="dep_1")
    # queued -> cancelled (the apply was cancelled before it completed).
    control.transition_arclink_provisioning_job(conn, job_id=job["job_id"], status="cancelled")
    conn.commit()

    deployment = dict(conn.execute("SELECT * FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone())
    with tempfile.TemporaryDirectory() as tmpdir:
        result = worker_mod.process_sovereign_deployment(
            conn, deployment=deployment, worker=_worker_config(worker_mod, tmpdir)
        )
    expect(result["status"] == "cancelled", str(result))
    dep = dict(conn.execute("SELECT status FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone())
    expect(dep["status"] != "active", f"a cancelled apply must NOT mark the deployment active: {dep}")
    expect(dep["status"] == "cancelled", str(dep))
    print("PASS test_cancelled_apply_job_does_not_mark_deployment_active")


def test_h1_failed_placement_teardown_issued_before_release() -> None:
    control = load_module("arclink_control.py", "arclink_control_h1_orphan")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_h1_orphan")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_h1_orphan")
    worker_mod = load_module("arclink_sovereign_worker.py", "arclink_sovereign_worker_h1_orphan")
    conn = memory_db(control)
    _seed_ready_deployment(control, conn)
    fleet.register_fleet_host(conn, hostname="worker-1.example.test", region="us-east", capacity_slots=4)
    placement = fleet.place_deployment(conn, deployment_id="dep_1")
    expect(placement is not None, "expected an active placement")

    # A failed apply job, exhausted attempts, with genuinely no durable runtime.
    job = worker_mod._ensure_apply_job(conn, deployment_id="dep_1")
    # Record a 'failed' service so durable runtime reads as False (terminal).
    conn.execute(
        "INSERT INTO arclink_service_health (deployment_id, service_name, status, checked_at, detail_json) VALUES ('dep_1', 'app', 'failed', ?, '{}')",
        (control.utc_now_iso(),),
    )
    conn.commit()

    with tempfile.TemporaryDirectory() as tmpdir:
        worker = _worker_config(worker_mod, tmpdir)
        # A live fake executor records compose lifecycle operations.
        executor = executor_mod.ArcLinkExecutor(
            config=executor_mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"),
        )
        removed = worker_mod._release_failed_deployment_placement_if_exhausted(
            conn,
            deployment_id="dep_1",
            job_id=str(job["job_id"]),
            reason="max_attempts_exhausted",
            had_durable_runtime=False,
            worker=worker,
            executor=executor,
        )

    expect(removed is not None, "placement should be released for a genuinely-dead failure")
    # A compose teardown was issued (recorded by the fake executor) for dep_1.
    teardown_actions = [str(run.get("action")) for run in executor._fake_lifecycle_runs.values()]
    expect("teardown" in teardown_actions, f"a compose teardown must be issued before release: {teardown_actions}")
    # The placement is now removed (host link gone) and the teardown status was recorded.
    active = conn.execute(
        "SELECT COUNT(*) AS c FROM arclink_deployment_placements WHERE deployment_id = 'dep_1' AND status = 'active'"
    ).fetchone()["c"]
    expect(int(active) == 0, "placement must be released after teardown")
    events = {row["event_type"] for row in conn.execute("SELECT event_type FROM arclink_events").fetchall()}
    expect("failed_placement_teardown_issued" in events, str(events))
    print("PASS test_h1_failed_placement_teardown_issued_before_release")


def main() -> int:
    test_cancelled_apply_job_does_not_mark_deployment_active()
    test_h1_failed_placement_teardown_issued_before_release()
    print("PASS all 2 ArcLink sovereign worker recovery regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
