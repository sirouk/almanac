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


def test_lost_apply_claim_does_not_call_apply_or_advance_status() -> None:
    # conc-C2: when transition_arclink_provisioning_job returns False (another worker
    # already claimed queued->running), process_sovereign_deployment must SKIP and
    # never call _apply_deployment (the double-execute deploy-blocker).
    control = load_module("arclink_control.py", "arclink_control_lost_apply_claim")
    worker_mod = load_module("arclink_sovereign_worker.py", "arclink_sovereign_worker_lost_apply_claim")
    conn = memory_db(control)
    _seed_ready_deployment(control, conn)

    job = worker_mod._ensure_apply_job(conn, deployment_id="dep_1")
    # Simulate a concurrent worker that already won the claim: the job is already
    # 'running', so this worker's CAS to 'running' returns False (lost claim).
    control.transition_arclink_provisioning_job(conn, job_id=job["job_id"], status="running")
    conn.commit()

    apply_calls: list[str] = []
    worker_mod._apply_deployment = lambda *a, **k: apply_calls.append("called") or {}  # type: ignore[assignment]

    deployment = dict(conn.execute("SELECT * FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone())
    with tempfile.TemporaryDirectory() as tmpdir:
        # The apply job is already 'running'. process_sovereign_deployment returns
        # 'already_running' on the explicit running-status check, so to exercise the
        # CAS-lost branch we drive the claim site directly with a queued job that a
        # concurrent worker steals between our ensure and our CAS.
        result = worker_mod.process_sovereign_deployment(
            conn, deployment=deployment, worker=_worker_config(worker_mod, tmpdir)
        )
    # The job is already running -> the explicit running guard returns first; either
    # way _apply_deployment must NOT run.
    expect(apply_calls == [], f"_apply_deployment must not be called on a running/lost job: {result}")

    # Now exercise the CAS-lost branch precisely: a queued job whose CAS loses.
    conn.execute("UPDATE arclink_provisioning_jobs SET status='queued' WHERE job_id = ?", (job["job_id"],))
    conn.commit()
    original_transition = worker_mod.transition_arclink_provisioning_job

    def _losing_transition(c, *, job_id, status, error=""):
        if status == "running":
            # Emulate a concurrent worker stealing the queued->running claim: the row
            # is already 'running' by the time our CAS runs, so it matches 0 rows.
            original_transition(c, job_id=job_id, status="running")
            return False
        return original_transition(c, job_id=job_id, status=status, error=error)

    worker_mod.transition_arclink_provisioning_job = _losing_transition  # type: ignore[assignment]
    apply_calls.clear()
    deployment2 = dict(conn.execute("SELECT * FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone())
    with tempfile.TemporaryDirectory() as tmpdir:
        result2 = worker_mod.process_sovereign_deployment(
            conn, deployment=deployment2, worker=_worker_config(worker_mod, tmpdir)
        )
    expect(result2.get("status") == "claim_lost", f"lost CAS must return claim_lost: {result2}")
    expect(apply_calls == [], f"a lost CAS claim must NOT call _apply_deployment: {result2}")
    dep = dict(conn.execute("SELECT status FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone())
    expect(dep["status"] != "active", f"a lost claim must not advance the deployment to active: {dep}")
    events = {row["event_type"] for row in conn.execute("SELECT event_type FROM arclink_events").fetchall()}
    expect("sovereign_apply_claim_lost" in events, str(events))
    print("PASS test_lost_apply_claim_does_not_call_apply_or_advance_status")


def test_lost_teardown_claim_does_not_call_teardown() -> None:
    # conc-C2: a lost teardown CAS must SKIP _teardown_deployment.
    control = load_module("arclink_control.py", "arclink_control_lost_teardown_claim")
    worker_mod = load_module("arclink_sovereign_worker.py", "arclink_sovereign_worker_lost_teardown_claim")
    conn = memory_db(control)
    control.upsert_arclink_user(
        conn, user_id="user_1", email="u@example.test", display_name="U", entitlement_state="paid"
    )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_t",
        user_id="user_1",
        prefix="amber-vault-9999",
        base_domain="example.test",
        status="teardown_requested",
    )
    conn.commit()

    job = worker_mod._ensure_teardown_job(conn, deployment_id="dep_t")
    teardown_calls: list[str] = []
    worker_mod._teardown_deployment = lambda *a, **k: teardown_calls.append("called") or {}  # type: ignore[assignment]
    original_transition = worker_mod.transition_arclink_provisioning_job

    def _losing_transition(c, *, job_id, status, error=""):
        if status == "running":
            original_transition(c, job_id=job_id, status="running")
            return False
        return original_transition(c, job_id=job_id, status=status, error=error)

    worker_mod.transition_arclink_provisioning_job = _losing_transition  # type: ignore[assignment]

    deployment = dict(conn.execute("SELECT * FROM arclink_deployments WHERE deployment_id = 'dep_t'").fetchone())
    with tempfile.TemporaryDirectory() as tmpdir:
        result = worker_mod.process_sovereign_teardown(
            conn, deployment=deployment, worker=_worker_config(worker_mod, tmpdir)
        )
    expect(result.get("status") == "claim_lost", f"lost teardown CAS must return claim_lost: {result}")
    expect(teardown_calls == [], f"a lost CAS claim must NOT call _teardown_deployment: {result}")
    dep = dict(conn.execute("SELECT status FROM arclink_deployments WHERE deployment_id = 'dep_t'").fetchone())
    expect(dep["status"] != "torn_down", f"a lost claim must not advance the deployment to torn_down: {dep}")
    events = {row["event_type"] for row in conn.execute("SELECT event_type FROM arclink_events").fetchall()}
    expect("sovereign_teardown_claim_lost" in events, str(events))
    print("PASS test_lost_teardown_claim_does_not_call_teardown")


def test_unverified_teardown_does_not_release_placement() -> None:
    # regr-H2: a NON-completed teardown (here: skipped_no_executor, because no
    # executor/worker can resolve the host) must NOT remove the placement -- doing so
    # would orphan the containers, since the teardown batch never re-selects a
    # provisioning_failed deployment. Instead, the placement is retained and an
    # operator is paged.
    control = load_module("arclink_control.py", "arclink_control_unverified_teardown")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_unverified_teardown")
    worker_mod = load_module("arclink_sovereign_worker.py", "arclink_sovereign_worker_unverified_teardown")
    conn = memory_db(control)
    _seed_ready_deployment(control, conn)
    fleet.register_fleet_host(conn, hostname="worker-1.example.test", region="us-east", capacity_slots=4)
    placement = fleet.place_deployment(conn, deployment_id="dep_1")
    expect(placement is not None, "expected an active placement")

    job = worker_mod._ensure_apply_job(conn, deployment_id="dep_1")
    conn.execute(
        "INSERT INTO arclink_service_health (deployment_id, service_name, status, checked_at, detail_json) VALUES ('dep_1', 'app', 'failed', ?, '{}')",
        (control.utc_now_iso(),),
    )
    conn.commit()

    # No worker AND no executor -> _best_effort_failed_placement_teardown returns
    # 'skipped_no_executor' (a NON-completed teardown). The placement must be retained.
    removed = worker_mod._release_failed_deployment_placement_if_exhausted(
        conn,
        deployment_id="dep_1",
        job_id=str(job["job_id"]),
        reason="max_attempts_exhausted",
        had_durable_runtime=False,
        worker=None,
        executor=None,
    )
    expect(removed is None, "an unverified teardown must NOT release the placement")
    active = conn.execute(
        "SELECT COUNT(*) AS c FROM arclink_deployment_placements WHERE deployment_id = 'dep_1' AND status = 'active'"
    ).fetchone()["c"]
    expect(int(active) == 1, "placement must be RETAINED when teardown did not complete")
    events = {row["event_type"] for row in conn.execute("SELECT event_type FROM arclink_events").fetchall()}
    expect("placement_retained_teardown_unverified" in events, str(events))
    expect("placement_released_after_provisioning_failure" not in events, str(events))
    print("PASS test_unverified_teardown_does_not_release_placement")


def test_concurrent_metadata_write_is_not_clobbered() -> None:
    # conc-H2: a metadata_json read-modify-write must not clobber a concurrent writer's
    # keys. We capture a STALE deployment dict, then a concurrent writer commits an
    # out-of-band key, then we run the writer with the stale dict. With the old
    # whole-blob rewrite the concurrent key would vanish; the merge-safe write keeps it.
    control = load_module("arclink_control.py", "arclink_control_conc_metadata")
    worker_mod = load_module("arclink_sovereign_worker.py", "arclink_sovereign_worker_conc_metadata")
    conn = memory_db(control)
    _seed_ready_deployment(control, conn)
    # Move to 'provisioning' so the runtime-metadata persist path is realistic.
    conn.execute("UPDATE arclink_deployments SET status='provisioning' WHERE deployment_id='dep_1'")
    conn.commit()

    # Concurrent writer B commits its own key directly to the DB blob.
    conn.execute(
        "UPDATE arclink_deployments SET metadata_json = json_set(COALESCE(metadata_json,'{}'), '$.writer_b_key', 'B') WHERE deployment_id='dep_1'"
    )
    conn.commit()

    # Writer A (_persist_deployment_runtime_metadata) re-reads the CURRENT blob inside
    # its BEGIN IMMEDIATE critical section, so writer B's key survives.
    worker_mod._persist_deployment_runtime_metadata(
        conn,
        deployment_id="dep_1",
        urls={"hermes": "https://h.example.test"},
        state_roots={"config": "/srv/dep_1/config"},
        state_root_base="/srv",
        runtime_metadata={"writer_a_key": "A"},
    )
    meta = json.loads(
        dict(conn.execute("SELECT metadata_json FROM arclink_deployments WHERE deployment_id='dep_1'").fetchone())["metadata_json"]
    )
    expect(meta.get("writer_b_key") == "B", f"concurrent writer B's key must survive: {meta}")
    expect(meta.get("writer_a_key") == "A", f"writer A's key must be persisted: {meta}")
    expect(meta.get("access_urls", {}).get("hermes") == "https://h.example.test", str(meta))

    # Also assert the single-key json_set deferral path is merge-safe.
    conn.execute(
        "UPDATE arclink_deployments SET metadata_json = json_set(COALESCE(metadata_json,'{}'), '$.writer_c_key', 'C') WHERE deployment_id='dep_1'"
    )
    conn.commit()
    worker_mod._record_tailnet_handoff_deferral(
        conn, deployment_id="dep_1", job_id="job_x", state={"reason": "test"}
    )
    meta2 = json.loads(
        dict(conn.execute("SELECT metadata_json FROM arclink_deployments WHERE deployment_id='dep_1'").fetchone())["metadata_json"]
    )
    expect(meta2.get("writer_c_key") == "C", f"concurrent writer C's key must survive deferral write: {meta2}")
    expect(str(meta2.get("tailnet_handoff_deferred_at") or "").strip() != "", f"deferral key must be written: {meta2}")

    # STALE-SNAPSHOT vector (the strongest case): _focus_public_bot_session_on_deployment
    # previously mutated the PASSED-IN session dict and wrote the whole blob back. We
    # capture a stale session dict, a concurrent writer commits a key to the row, then
    # we run focus with the stale dict. The merge-safe json_set keeps the concurrent key.
    now = control.utc_now_iso()
    conn.execute(
        """
        INSERT INTO arclink_onboarding_sessions (session_id, channel, channel_identity, status, metadata_json, created_at, updated_at)
        VALUES ('sess_1', 'telegram', 'tg:1', 'provisioning_ready', '{}', ?, ?)
        """,
        (now, now),
    )
    conn.commit()
    stale_session = dict(conn.execute("SELECT * FROM arclink_onboarding_sessions WHERE session_id='sess_1'").fetchone())
    # Concurrent writer commits a key to the session blob AFTER we captured the stale dict.
    conn.execute(
        "UPDATE arclink_onboarding_sessions SET metadata_json = json_set(COALESCE(metadata_json,'{}'), '$.session_writer_key', 'S') WHERE session_id='sess_1'"
    )
    conn.commit()
    worker_mod._focus_public_bot_session_on_deployment(
        conn,
        session=stale_session,
        deployment={"deployment_id": "dep_1", "agent_name": "Atlas"},
    )
    sess_meta = json.loads(
        dict(conn.execute("SELECT metadata_json FROM arclink_onboarding_sessions WHERE session_id='sess_1'").fetchone())["metadata_json"]
    )
    expect(sess_meta.get("session_writer_key") == "S", f"concurrent session writer's key must survive a stale-snapshot focus write: {sess_meta}")
    expect(sess_meta.get("active_deployment_id") == "dep_1", str(sess_meta))
    expect(sess_meta.get("active_agent_label") == "Atlas", str(sess_meta))
    print("PASS test_concurrent_metadata_write_is_not_clobbered")


def main() -> int:
    test_cancelled_apply_job_does_not_mark_deployment_active()
    test_h1_failed_placement_teardown_issued_before_release()
    test_lost_apply_claim_does_not_call_apply_or_advance_status()
    test_lost_teardown_claim_does_not_call_teardown()
    test_unverified_teardown_does_not_release_placement()
    test_concurrent_metadata_write_is_not_clobbered()
    print("PASS all 6 ArcLink sovereign worker recovery regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
