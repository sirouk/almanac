#!/usr/bin/env python3
"""Regression tests for pod migration H3 (rollback verify), H4 (same-root), H6 (lease)."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
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


def _seed_migration_row(control, conn, *, migration_id: str, status: str, updated_at: str, source_status: str = "removed"):
    control.upsert_arclink_user(conn, user_id="user_1", email="u@example.test", entitlement_state="paid")
    control.reserve_arclink_deployment_prefix(
        conn, deployment_id="dep_1", user_id="user_1", prefix="cap-one", base_domain="example.test", status="active"
    )
    conn.execute(
        "INSERT INTO arclink_deployment_placements (placement_id, deployment_id, host_id, status, placed_at) VALUES ('plc_source', 'dep_1', 'host_source', ?, ?)",
        (source_status, updated_at),
    )
    conn.execute(
        """
        INSERT INTO arclink_pod_migrations (
          migration_id, deployment_id, source_host_id, target_host_id, target_machine_id,
          source_placement_id, target_placement_id, source_state_root, target_state_root,
          capture_dir, status, operation_idempotency_key, created_at, updated_at
        ) VALUES (?, 'dep_1', 'host_source', 'host_source', 'current',
          'plc_source', '', '/arcdata/deployments/dep_1', '/arcdata/deployments/dep_1',
          '/arcdata/deployments/.migrations/' || ?, ?, ?, ?, ?)
        """,
        (migration_id, migration_id, status, f"arclink:migration:{migration_id}", updated_at, updated_at),
    )
    conn.commit()


def test_h3_rollback_does_not_reactivate_source_when_restart_failed() -> None:
    control = load_module("arclink_control.py", "arclink_control_h3_rollback")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_h3_rollback")
    conn = memory_db(control)
    _seed_migration_row(control, conn, migration_id="mig_h3failed", status="running", updated_at=control.utc_now_iso())
    row = dict(conn.execute("SELECT * FROM arclink_pod_migrations WHERE migration_id = 'mig_h3failed'").fetchone())

    migration._mark_rollback(
        conn,
        row=row,
        verification={"healthy": False, "error": "verify failed"},
        error="verify failed",
        lifecycle_metadata={"source_restart": {"status": "failed", "error_type": "ArcLinkExecutorError"}},
    )

    placement = dict(conn.execute("SELECT status FROM arclink_deployment_placements WHERE placement_id = 'plc_source'").fetchone())
    expect(placement["status"] != "active", f"source must NOT be reactivated when its restart failed: {placement}")
    meta = json.loads(conn.execute("SELECT rollback_metadata_json FROM arclink_pod_migrations WHERE migration_id = 'mig_h3failed'").fetchone()[0])
    expect(meta.get("manual_recovery_required") is True, str(meta))
    expect(meta.get("source_restart_verified") is False, str(meta))
    events = {r["event_type"] for r in conn.execute("SELECT event_type FROM arclink_events").fetchall()}
    expect("pod_migration_rollback_source_restart_failed" in events, str(events))
    print("PASS test_h3_rollback_does_not_reactivate_source_when_restart_failed")


def test_h3_rollback_reactivates_source_when_restart_completed() -> None:
    control = load_module("arclink_control.py", "arclink_control_h3_ok")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_h3_ok")
    conn = memory_db(control)
    _seed_migration_row(control, conn, migration_id="mig_h3ok", status="running", updated_at=control.utc_now_iso())
    row = dict(conn.execute("SELECT * FROM arclink_pod_migrations WHERE migration_id = 'mig_h3ok'").fetchone())

    migration._mark_rollback(
        conn,
        row=row,
        verification={"healthy": False, "error": "verify failed"},
        error="verify failed",
        lifecycle_metadata={"source_restart": {"status": "completed", "action": "restart"}},
    )

    placement = dict(conn.execute("SELECT status FROM arclink_deployment_placements WHERE placement_id = 'plc_source'").fetchone())
    expect(placement["status"] == "active", f"a verified-healthy source restart re-activates the source: {placement}")
    meta = json.loads(conn.execute("SELECT rollback_metadata_json FROM arclink_pod_migrations WHERE migration_id = 'mig_h3ok'").fetchone()[0])
    expect(meta.get("source_restart_verified") is True, str(meta))
    expect("manual_recovery_required" not in meta, str(meta))
    print("PASS test_h3_rollback_reactivates_source_when_restart_completed")


def test_h4_same_root_materialize_is_atomic_and_non_destructive() -> None:
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_h4")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "deployments" / "dep_1-cap-one"
        (root / "vault").mkdir(parents=True)
        (root / "vault" / "mission.md").write_text("live data\n", encoding="utf-8")

        capture_dir = Path(tmp) / "deployments" / ".migrations" / "mig_h4"
        staged = capture_dir / "source-root"
        (staged / "vault").mkdir(parents=True)
        (staged / "vault" / "mission.md").write_text("captured data\n", encoding="utf-8")
        (staged / "vault" / "extra.md").write_text("new file\n", encoding="utf-8")

        # Same source == target root: must materialize ATOMICALLY (no destroy-first).
        migration._materialize_capture(capture_dir, root, source_root=root)

        expect((root / "vault" / "mission.md").read_text(encoding="utf-8") == "captured data\n", "materialized content")
        expect((root / "vault" / "extra.md").read_text(encoding="utf-8") == "new file\n", "new captured file present")
        # No leftover temp/backup dirs.
        leftovers = [p.name for p in root.parent.iterdir() if p.name.startswith(".") and "arclink-" in p.name]
        expect(not leftovers, f"no temp/backup dirs must remain: {leftovers}")

        # Same-root with an EMPTY/absent capture must NOT wipe the live data.
        empty_capture = Path(tmp) / "deployments" / ".migrations" / "mig_h4_empty"
        empty_capture.mkdir(parents=True)
        migration._materialize_capture(empty_capture, root, source_root=root)
        expect((root / "vault" / "mission.md").exists(), "empty capture must not destroy live data")
    print("PASS test_h4_same_root_materialize_is_atomic_and_non_destructive")


def test_h6_stale_running_migration_is_recovered_to_terminal() -> None:
    control = load_module("arclink_control.py", "arclink_control_h6")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_h6")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_h6")
    conn = memory_db(control)
    # updated_at far in the past -> the running lease has expired.
    _seed_migration_row(control, conn, migration_id="mig_h6", status="running", updated_at="2000-01-01T00:00:00+00:00")
    # Reserve the idempotency row as 'running' (as the original run would have).
    control.reserve_arclink_operation_idempotency(
        conn,
        operation_kind=migration.OPERATION_KIND,
        idempotency_key="arclink:migration:mig_h6",
        intent=migration._operation_intent(
            dict(conn.execute("SELECT * FROM arclink_pod_migrations WHERE migration_id = 'mig_h6'").fetchone()),
            dry_run=False,
        ),
        status="running",
    )

    stranded = migration._stranded_running_migration(conn, deployment_id="dep_1")
    expect(stranded is not None, "the stranded running migration must be found")

    executor = executor_mod.ArcLinkExecutor(
        config=executor_mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"),
    )
    recovered = migration._recover_stale_running_migration(
        conn,
        row=stranded,
        operation_key="arclink:migration:mig_h6",
        intent=migration._operation_intent(stranded, dry_run=False),
        executor=executor,
        env={},
    )
    expect(recovered is not None, "stale lease must be recovered")
    final = dict(conn.execute("SELECT status FROM arclink_pod_migrations WHERE migration_id = 'mig_h6'").fetchone())
    expect(final["status"] in migration.TERMINAL_MIGRATION_STATUSES, f"recovered migration must be terminal: {final}")
    # The idempotency row is released (failed) so a fresh migration is no longer refused.
    idem = dict(conn.execute(
        "SELECT status FROM arclink_operation_idempotency WHERE idempotency_key = 'arclink:migration:mig_h6'"
    ).fetchone())
    expect(idem["status"] == "failed", f"idempotency lease must be released: {idem}")
    # A fresh-lease running migration must NOT be recovered (deployment already
    # seeded; only insert another migration row).
    fresh_now = control.utc_now_iso()
    conn.execute(
        """
        INSERT INTO arclink_pod_migrations (
          migration_id, deployment_id, source_host_id, target_host_id, target_machine_id,
          source_placement_id, target_placement_id, source_state_root, target_state_root,
          capture_dir, status, operation_idempotency_key, created_at, updated_at
        ) VALUES ('mig_fresh', 'dep_1', 'host_source', 'host_source', 'current',
          'plc_source', '', '/arcdata/deployments/dep_1', '/arcdata/deployments/dep_1',
          '/arcdata/deployments/.migrations/mig_fresh', 'running', 'arclink:migration:mig_fresh', ?, ?)
        """,
        (fresh_now, fresh_now),
    )
    conn.commit()
    fresh = dict(conn.execute("SELECT * FROM arclink_pod_migrations WHERE migration_id = 'mig_fresh'").fetchone())
    not_recovered = migration._recover_stale_running_migration(
        conn,
        row=fresh,
        operation_key="arclink:migration:mig_fresh",
        intent=migration._operation_intent(fresh, dry_run=False),
        executor=executor,
        env={},
    )
    expect(not_recovered is None, "a fresh-lease running migration must not be recovered")
    print("PASS test_h6_stale_running_migration_is_recovered_to_terminal")


def test_h3_round2_live_active_source_not_left_serving_on_failed_restart() -> None:
    # Round 2: in the LIVE flow the source placement stays 'active' until success.
    # A failed rollback restart must NOT leave that real active row serving.
    control = load_module("arclink_control.py", "arclink_control_h3_round2")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_h3_round2")
    conn = memory_db(control)
    _seed_migration_row(
        control,
        conn,
        migration_id="mig_h3live",
        status="running",
        updated_at=control.utc_now_iso(),
        source_status="active",
    )
    row = dict(conn.execute("SELECT * FROM arclink_pod_migrations WHERE migration_id = 'mig_h3live'").fetchone())
    before = dict(conn.execute("SELECT status FROM arclink_deployment_placements WHERE placement_id = 'plc_source'").fetchone())
    expect(before["status"] == "active", f"precondition: live source is active: {before}")

    migration._mark_rollback(
        conn,
        row=row,
        verification={"healthy": False, "error": "verify failed"},
        error="verify failed",
        lifecycle_metadata={"source_restart": {"status": "failed", "error_type": "ArcLinkExecutorError"}},
    )

    placement = dict(conn.execute("SELECT status FROM arclink_deployment_placements WHERE placement_id = 'plc_source'").fetchone())
    expect(placement["status"] != "active", f"a dead source must NOT stay advertised active: {placement}")
    meta = json.loads(conn.execute("SELECT rollback_metadata_json FROM arclink_pod_migrations WHERE migration_id = 'mig_h3live'").fetchone()[0])
    expect(meta.get("manual_recovery_required") is True, str(meta))
    expect(meta.get("source_restart_verified") is False, str(meta))
    events = {r["event_type"] for r in conn.execute("SELECT event_type FROM arclink_events").fetchall()}
    expect("pod_migration_rollback_source_restart_failed" in events, str(events))
    print("PASS test_h3_round2_live_active_source_not_left_serving_on_failed_restart")


def _seed_cross_host_deployment(control, conn, tmp: Path):
    provisioning = load_module("arclink_provisioning.py", "arclink_provisioning_safety_seed")
    source_base = tmp / "source"
    target_base = tmp / "target"
    source_roots = provisioning.render_arclink_state_roots(
        deployment_id="dep_1", prefix="cap-one", state_root_base=str(source_base)
    )
    now = control.utc_now_iso()
    control.upsert_arclink_user(conn, user_id="user_1", email="u@example.test", entitlement_state="paid")
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_1",
        user_id="user_1",
        prefix="cap-one",
        base_domain="example.test",
        status="active",
        metadata={
            "state_roots": source_roots,
            "state_root_base": str(source_base),
            "base_domain": "example.test",
        },
    )
    conn.execute(
        """
        INSERT INTO arclink_fleet_hosts (
          host_id, hostname, status, capacity_slots, observed_load, metadata_json, created_at, updated_at
        ) VALUES
          ('host_source', 'source.example.test', 'active', 10, 1, ?, ?, ?),
          ('host_target', 'target.example.test', 'active', 10, 0, ?, ?, ?)
        """,
        (
            json.dumps({"state_root_base": str(source_base), "edge_target": "source-edge.example.test"}),
            now,
            now,
            json.dumps({"state_root_base": str(target_base), "edge_target": "target-edge.example.test"}),
            now,
            now,
        ),
    )
    conn.commit()
    return source_roots, target_base


def test_h6_round2_stale_recovery_tears_down_half_up_cross_host_target() -> None:
    # Round 2: a stranded run that already brought a CROSS-HOST target partway up
    # must have that target torn down during stale recovery (previously the
    # recovery passed target_intent=None so teardown never ran).
    control = load_module("arclink_control.py", "arclink_control_h6_teardown")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_h6_teardown")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_h6_teardown")
    conn = memory_db(control)
    with tempfile.TemporaryDirectory() as tmpdir:
        source_roots, target_base = _seed_cross_host_deployment(control, conn, Path(tmpdir))
        conn.execute(
            "INSERT INTO arclink_deployment_placements (placement_id, deployment_id, host_id, status, placed_at) VALUES ('plc_source', 'dep_1', 'host_source', 'active', ?)",
            (control.utc_now_iso(),),
        )
        conn.execute(
            "INSERT INTO arclink_deployment_placements (placement_id, deployment_id, host_id, status, placed_at) VALUES ('plc_target', 'dep_1', 'host_target', 'removed', ?)",
            ("migration_target_pending",),
        )
        target_root = str(Path(str(source_roots["root"]).replace(str(Path(tmpdir) / "source"), str(target_base))))
        conn.execute(
            """
            INSERT INTO arclink_pod_migrations (
              migration_id, deployment_id, source_host_id, target_host_id, target_machine_id,
              source_placement_id, target_placement_id, source_state_root, target_state_root,
              capture_dir, status, operation_idempotency_key, created_at, updated_at
            ) VALUES ('mig_h6td', 'dep_1', 'host_source', 'host_target', 'host_target',
              'plc_source', 'plc_target', ?, ?, ?, 'running', 'arclink:migration:mig_h6td',
              '2000-01-01T00:00:00+00:00', '2000-01-01T00:00:00+00:00')
            """,
            (str(source_roots["root"]), target_root, str(target_base / ".migrations" / "mig_h6td")),
        )
        conn.commit()

        stranded = migration._stranded_running_migration(conn, deployment_id="dep_1")
        expect(stranded is not None, "stranded cross-host running migration must be found")
        executor = executor_mod.ArcLinkExecutor(
            config=executor_mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"),
        )
        recovered = migration._recover_stale_running_migration(
            conn,
            row=stranded,
            operation_key="arclink:migration:mig_h6td",
            intent=migration._operation_intent(stranded, dry_run=False),
            executor=executor,
            env={},
        )
        expect(recovered is not None, "stale cross-host migration must be recovered")
        actions = {
            str(run["action"])
            for key, run in executor._fake_lifecycle_runs.items()
            if str(key).startswith("arclink:migration:mig_h6td:")
        }
        expect("teardown" in actions, f"half-up cross-host target must be torn down during stale recovery: {actions}")
        rollback = json.loads(
            conn.execute("SELECT rollback_metadata_json FROM arclink_pod_migrations WHERE migration_id = 'mig_h6td'").fetchone()[0]
        )
        expect(rollback["lifecycle"].get("target_teardown", {}).get("action") == "teardown", str(rollback))
    print("PASS test_h6_round2_stale_recovery_tears_down_half_up_cross_host_target")


def test_h6_round2_fresh_running_migration_is_not_disturbed_on_reentry() -> None:
    # Round 2 NEW-BUG: a fresh, non-expired running migration must NOT be rolled
    # back or disturbed when migrate_pod is re-entered; it bails out cleanly with
    # an already-in-progress result and does no host mutation.
    control = load_module("arclink_control.py", "arclink_control_h6_fresh")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_h6_fresh")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_h6_fresh")
    conn = memory_db(control)
    with tempfile.TemporaryDirectory() as tmpdir:
        source_roots, _ = _seed_cross_host_deployment(control, conn, Path(tmpdir))
        conn.execute(
            "INSERT INTO arclink_deployment_placements (placement_id, deployment_id, host_id, status, placed_at) VALUES ('plc_source', 'dep_1', 'host_source', 'active', ?)",
            (control.utc_now_iso(),),
        )
        fresh_now = control.utc_now_iso()
        conn.execute(
            """
            INSERT INTO arclink_pod_migrations (
              migration_id, deployment_id, source_host_id, target_host_id, target_machine_id,
              source_placement_id, target_placement_id, source_state_root, target_state_root,
              capture_dir, status, operation_idempotency_key, created_at, updated_at
            ) VALUES ('mig_h6fresh', 'dep_1', 'host_source', 'host_target', 'host_target',
              'plc_source', '', ?, ?, ?, 'running', 'arclink:migration:mig_h6fresh', ?, ?)
            """,
            (str(source_roots["root"]), str(source_roots["root"]), "/arcdata/deployments/.migrations/mig_h6fresh", fresh_now, fresh_now),
        )
        conn.commit()

        executor = executor_mod.ArcLinkExecutor(
            config=executor_mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"),
        )
        result = migration.migrate_pod(
            conn,
            executor=executor,
            deployment_id="dep_1",
            target_machine_id="host_target",
            migration_id="mig_h6fresh",
            verifier=lambda _conn, _row, _intent: {"healthy": True},
            env={"ARCLINK_ACTION_WORKER_ALLOW_ROOT_MIGRATION_CAPTURE": "1"},
        )
        expect(result["idempotent_replay"] is True and result["status"] == "running", str(result))
        expect(executor._fake_lifecycle_runs == {}, f"fresh live migration must not be touched: {executor._fake_lifecycle_runs}")
        still = dict(conn.execute("SELECT status FROM arclink_pod_migrations WHERE migration_id = 'mig_h6fresh'").fetchone())
        expect(still["status"] == "running", f"fresh migration must NOT be rolled back: {still}")
    print("PASS test_h6_round2_fresh_running_migration_is_not_disturbed_on_reentry")


def _seed_two_placement_migration(
    control, conn, *, migration_id: str, status: str, updated_at: str,
    source_status: str, target_status: str,
):
    """Seed a migration with DISTINCT source + target placements (cross-placement)."""
    control.upsert_arclink_user(conn, user_id="user_1", email="u@example.test", entitlement_state="paid")
    control.reserve_arclink_deployment_prefix(
        conn, deployment_id="dep_1", user_id="user_1", prefix="cap-one", base_domain="example.test", status="active"
    )
    conn.execute(
        "INSERT INTO arclink_deployment_placements (placement_id, deployment_id, host_id, status, placed_at) VALUES ('plc_source', 'dep_1', 'host_source', ?, ?)",
        (source_status, updated_at),
    )
    conn.execute(
        "INSERT INTO arclink_deployment_placements (placement_id, deployment_id, host_id, status, placed_at) VALUES ('plc_target', 'dep_1', 'host_target', ?, ?)",
        (target_status, updated_at),
    )
    conn.execute(
        """
        INSERT INTO arclink_pod_migrations (
          migration_id, deployment_id, source_host_id, target_host_id, target_machine_id,
          source_placement_id, target_placement_id, source_state_root, target_state_root,
          capture_dir, status, operation_idempotency_key, created_at, updated_at
        ) VALUES (?, 'dep_1', 'host_source', 'host_target', 'host_target',
          'plc_source', 'plc_target', '/arcdata/deployments/dep_1', '/arcdata/deployments/dep_1-t',
          '/arcdata/deployments/.migrations/' || ?, ?, ?, ?, ?)
        """,
        (migration_id, migration_id, status, f"arclink:migration:{migration_id}", updated_at, updated_at),
    )
    conn.commit()


def test_c1_mark_rollback_against_succeeded_row_is_noop() -> None:
    # C1: a slow-but-alive migration commits 'succeeded'; a concurrent stale-lease
    # recovery must NOT clobber it back to 'rolled_back'. _mark_rollback fences on
    # status='running', so against a terminal 'succeeded' row it is a pure no-op:
    # the live serving target stays active, the (already-removed) source stays
    # removed, and the migration row is left 'succeeded'.
    control = load_module("arclink_control.py", "arclink_control_c1_noop")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_c1_noop")
    conn = memory_db(control)
    # The success outcome: target serving (active), source retired (removed).
    _seed_two_placement_migration(
        control, conn, migration_id="mig_c1ok", status="succeeded",
        updated_at=control.utc_now_iso(), source_status="removed", target_status="active",
    )
    row = dict(conn.execute("SELECT * FROM arclink_pod_migrations WHERE migration_id = 'mig_c1ok'").fetchone())

    applied = migration._mark_rollback(
        conn,
        row=row,
        verification={"healthy": False, "error": "stale lease (should not apply)"},
        error="stale lease (should not apply)",
        lifecycle_metadata={"source_restart": {"status": "completed", "action": "restart"}},
    )
    expect(applied is False, "rollback against a terminal 'succeeded' row must be a no-op (returns False)")

    placements = {
        r["placement_id"]: r["status"]
        for r in conn.execute("SELECT placement_id, status FROM arclink_deployment_placements").fetchall()
    }
    expect(placements["plc_target"] == "active", f"live serving target must NOT be removed by a no-op rollback: {placements}")
    expect(placements["plc_source"] == "removed", f"retired source must NOT be reactivated by a no-op rollback: {placements}")
    final = dict(conn.execute("SELECT status FROM arclink_pod_migrations WHERE migration_id = 'mig_c1ok'").fetchone())
    expect(final["status"] == "succeeded", f"succeeded row must NOT be clobbered to rolled_back: {final}")
    rolled = conn.execute("SELECT COUNT(*) AS c FROM arclink_events WHERE event_type = 'pod_migration_rolled_back'").fetchone()
    expect(int(rolled["c"]) == 0, "no rollback event must be emitted for a no-op")
    print("PASS test_c1_mark_rollback_against_succeeded_row_is_noop")


def test_c1_mark_rollback_against_running_row_applies() -> None:
    # Counterpart: a genuinely 'running' row IS rolled back (returns True) so the
    # fence does not regress the normal rollback path.
    control = load_module("arclink_control.py", "arclink_control_c1_apply")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_c1_apply")
    conn = memory_db(control)
    _seed_migration_row(control, conn, migration_id="mig_c1run", status="running", updated_at=control.utc_now_iso())
    row = dict(conn.execute("SELECT * FROM arclink_pod_migrations WHERE migration_id = 'mig_c1run'").fetchone())

    applied = migration._mark_rollback(
        conn,
        row=row,
        verification={"healthy": False, "error": "verify failed"},
        error="verify failed",
        lifecycle_metadata={"source_restart": {"status": "completed", "action": "restart"}},
    )
    expect(applied is True, "a running row must actually roll back (returns True)")
    final = dict(conn.execute("SELECT status FROM arclink_pod_migrations WHERE migration_id = 'mig_c1run'").fetchone())
    expect(final["status"] == "rolled_back", f"running row must be rolled back: {final}")
    print("PASS test_c1_mark_rollback_against_running_row_applies")


def test_c1_two_concurrent_recoveries_only_one_rolls_back() -> None:
    # C1: two workers find the SAME stranded 'running' row and both try to recover
    # it. The atomic CAS claim (status='running' AND updated_at=<observed stale>)
    # lets exactly ONE win; the loser does NO Docker lifecycle work and returns
    # None. Previously both ran -> double source-restart + double target-teardown.
    control = load_module("arclink_control.py", "arclink_control_c1_race")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_c1_race")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_c1_race")
    conn = memory_db(control)
    # Stale lease (far past) so the row is recoverable.
    _seed_migration_row(control, conn, migration_id="mig_c1race", status="running", updated_at="2000-01-01T00:00:00+00:00")
    stranded = migration._stranded_running_migration(conn, deployment_id="dep_1")
    expect(stranded is not None, "stranded running migration must be found")
    snapshot = dict(stranded)  # both 'workers' start from the same stale snapshot

    executor = executor_mod.ArcLinkExecutor(
        config=executor_mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"),
    )

    first = migration._recover_stale_running_migration(
        conn, row=dict(snapshot), operation_key="arclink:migration:mig_c1race",
        intent=migration._operation_intent(snapshot, dry_run=False), executor=executor, env={},
    )
    second = migration._recover_stale_running_migration(
        conn, row=dict(snapshot), operation_key="arclink:migration:mig_c1race",
        intent=migration._operation_intent(snapshot, dry_run=False), executor=executor, env={},
    )
    expect(first is not None, "the first recovery must win and roll the row back")
    expect(second is None, "the second recovery of the SAME stranded snapshot must be a no-op (lost the CAS claim)")
    final = dict(conn.execute("SELECT status FROM arclink_pod_migrations WHERE migration_id = 'mig_c1race'").fetchone())
    expect(final["status"] in migration.TERMINAL_MIGRATION_STATUSES, f"row must be terminal once: {final}")
    rolled = conn.execute("SELECT COUNT(*) AS c FROM arclink_events WHERE event_type = 'pod_migration_rolled_back'").fetchone()
    expect(int(rolled["c"]) == 1, f"exactly one rollback must be recorded, not two: {dict(rolled)}")
    # The source restart must have happened exactly once -- not twice against real Docker.
    restarts = [
        key for key, run in executor._fake_lifecycle_runs.items()
        if str(key).startswith("arclink:migration:mig_c1race:") and str(run["action"]) == "restart"
    ]
    expect(len(restarts) == 1, f"source must be restarted exactly once across both recoveries: {restarts}")
    print("PASS test_c1_two_concurrent_recoveries_only_one_rolls_back")


def test_c1_heartbeat_keeps_live_slow_migration_from_going_stale() -> None:
    # C1: a live-but-slow migration must not be declared stale by wall-clock age.
    # The heartbeat advances updated_at so _stranded/_recover see a FRESH lease and
    # refuse to recover the still-alive row.
    control = load_module("arclink_control.py", "arclink_control_c1_hb")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_c1_hb")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_c1_hb")
    conn = memory_db(control)
    # Seed updated_at JUST past the ENFORCED minimum lease so without a heartbeat it
    # would be recoverable. Round 3 / FIX 2: the lease is now clamped UP to
    # MINIMUM_MIGRATION_RUNNING_LEASE_SECONDS (> the longest uninterrupted migration
    # op), so an env override of "60" is intentionally NOT honored -- seed past the
    # real floor instead of relying on an artificially tiny lease.
    env = {"ARCLINK_POD_MIGRATION_RUNNING_LEASE_SECONDS": "60"}
    import datetime as _dt
    over_lease = migration.MINIMUM_MIGRATION_RUNNING_LEASE_SECONDS + 120
    stale_ts = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(seconds=over_lease)).isoformat()
    _seed_migration_row(control, conn, migration_id="mig_c1hb", status="running", updated_at=stale_ts)

    # Pre-heartbeat: the row is over the lease and would be recovered.
    pre = dict(conn.execute("SELECT * FROM arclink_pod_migrations WHERE migration_id = 'mig_c1hb'").fetchone())
    executor = executor_mod.ArcLinkExecutor(
        config=executor_mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"),
    )
    would_recover = migration._recover_stale_running_migration(
        conn, row=dict(pre), operation_key="arclink:migration:mig_c1hb",
        intent=migration._operation_intent(pre, dry_run=False), executor=executor, env=env,
    )
    # Re-seed to running (the line above just rolled it back to prove it WAS stale).
    expect(would_recover is not None, "precondition: an un-beaten over-lease row IS recoverable")
    conn.execute("UPDATE arclink_pod_migrations SET status = 'running', updated_at = ? WHERE migration_id = 'mig_c1hb'", (stale_ts,))
    conn.commit()

    # Now BEAT the lease: updated_at jumps to now, so the row is no longer stale.
    beat_ts, still_owned = migration._heartbeat_running_migration(conn, "mig_c1hb")
    expect(beat_ts != stale_ts, "heartbeat must advance updated_at")
    expect(still_owned is True, "an un-tokened running row is still owned under the legacy guard")
    after = dict(conn.execute("SELECT * FROM arclink_pod_migrations WHERE migration_id = 'mig_c1hb'").fetchone())
    executor2 = executor_mod.ArcLinkExecutor(
        config=executor_mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"),
    )
    not_recovered = migration._recover_stale_running_migration(
        conn, row=after, operation_key="arclink:migration:mig_c1hb",
        intent=migration._operation_intent(after, dry_run=False), executor=executor2, env=env,
    )
    expect(not_recovered is None, "a heart-beaten (fresh) live migration must NOT be declared stale / recovered")
    expect(executor2._fake_lifecycle_runs == {}, f"a fresh live migration must not be disturbed: {executor2._fake_lifecycle_runs}")
    still = dict(conn.execute("SELECT status FROM arclink_pod_migrations WHERE migration_id = 'mig_c1hb'").fetchone())
    expect(still["status"] == "running", f"beaten live migration stays running: {still}")
    print("PASS test_c1_heartbeat_keeps_live_slow_migration_from_going_stale")


def test_c1_heartbeat_cannot_resurrect_terminal_row() -> None:
    # Defensive: a heartbeat against a terminal row is a guarded no-op (never flips
    # a succeeded/rolled_back row back to a fresh-looking running row).
    control = load_module("arclink_control.py", "arclink_control_c1_hb_term")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_c1_hb_term")
    conn = memory_db(control)
    _seed_migration_row(control, conn, migration_id="mig_c1term", status="succeeded", updated_at="2000-01-01T00:00:00+00:00")
    migration._heartbeat_running_migration(conn, "mig_c1term")
    row = dict(conn.execute("SELECT status, updated_at FROM arclink_pod_migrations WHERE migration_id = 'mig_c1term'").fetchone())
    expect(row["status"] == "succeeded", f"heartbeat must not change a terminal status: {row}")
    expect(row["updated_at"] == "2000-01-01T00:00:00+00:00", f"heartbeat must not touch a terminal row's updated_at: {row}")
    print("PASS test_c1_heartbeat_cannot_resurrect_terminal_row")


def test_m3_orphan_prev_backup_is_restored_when_target_missing() -> None:
    # M3: a same-root materialize that crashed between its two os.replace calls
    # leaves target_root MISSING and an orphan .arclink-prev-* backup holding the
    # live data. The next materialize must restore that backup, not lose it.
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_m3")
    with tempfile.TemporaryDirectory() as tmp:
        deployments = Path(tmp) / "deployments"
        target_root = deployments / "dep_1-cap-one"
        # Simulate the crash state: target_root gone, backup holds the live data.
        backup = deployments / ".dep_1-cap-one.arclink-prev-12345"
        (backup / "vault").mkdir(parents=True)
        (backup / "vault" / "mission.md").write_text("live data\n", encoding="utf-8")
        expect(not target_root.exists(), "precondition: target_root is missing after the crash")

        capture_dir = deployments / ".migrations" / "mig_m3"
        staged = capture_dir / "source-root"
        (staged / "vault").mkdir(parents=True)
        (staged / "vault" / "mission.md").write_text("recaptured\n", encoding="utf-8")

        # Same-root materialize: first restores the orphan backup, then re-materializes.
        migration._materialize_capture(capture_dir, target_root, source_root=target_root)

        expect(target_root.exists(), "target_root must be restored / present after recovery")
        expect((target_root / "vault" / "mission.md").exists(), "live data must survive the crash recovery")
        leftovers = [p.name for p in deployments.iterdir() if p.name.startswith(".dep_1-cap-one.arclink-prev-")]
        expect(not leftovers, f"orphan backup must be consumed, not left behind: {leftovers}")
    print("PASS test_m3_orphan_prev_backup_is_restored_when_target_missing")


def test_m4_recovery_loops_over_all_stale_running_rows() -> None:
    # M4: more than one row of the same deployment can be stranded in 'running'.
    # _stranded_running_migrations must surface ALL of them so migrate_pod recovers
    # every stale row, not just the oldest.
    control = load_module("arclink_control.py", "arclink_control_m4")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_m4")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_m4")
    conn = memory_db(control)
    _seed_migration_row(control, conn, migration_id="mig_m4a", status="running", updated_at="2000-01-01T00:00:00+00:00")
    # A second stranded row for the same deployment (older + newer to check ordering).
    conn.execute(
        """
        INSERT INTO arclink_pod_migrations (
          migration_id, deployment_id, source_host_id, target_host_id, target_machine_id,
          source_placement_id, target_placement_id, source_state_root, target_state_root,
          capture_dir, status, operation_idempotency_key, created_at, updated_at
        ) VALUES ('mig_m4b', 'dep_1', 'host_source', 'host_source', 'current',
          'plc_source', '', '/arcdata/deployments/dep_1', '/arcdata/deployments/dep_1',
          '/arcdata/deployments/.migrations/mig_m4b', 'running', 'arclink:migration:mig_m4b',
          '2001-01-01T00:00:00+00:00', '2001-01-01T00:00:00+00:00')
        """
    )
    conn.commit()

    candidates = migration._stranded_running_migrations(conn, deployment_id="dep_1")
    ids = [c["migration_id"] for c in candidates]
    expect(ids == ["mig_m4a", "mig_m4b"], f"all stale running rows must be returned oldest-first: {ids}")

    executor = executor_mod.ArcLinkExecutor(
        config=executor_mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"),
    )
    for stranded in migration._stranded_running_migrations(conn, deployment_id="dep_1"):
        migration._recover_stale_running_migration(
            conn, row=stranded, operation_key=str(stranded["operation_idempotency_key"]),
            intent=migration._operation_intent(stranded, dry_run=False), executor=executor, env={},
        )
    remaining = migration._stranded_running_migrations(conn, deployment_id="dep_1")
    expect(remaining == [], f"every stale running row must be recovered to terminal: {[r['migration_id'] for r in remaining]}")
    statuses = {
        r["migration_id"]: r["status"]
        for r in conn.execute("SELECT migration_id, status FROM arclink_pod_migrations").fetchall()
    }
    expect(all(s in migration.TERMINAL_MIGRATION_STATUSES for s in statuses.values()), f"all rows terminal: {statuses}")
    print("PASS test_m4_recovery_loops_over_all_stale_running_rows")


def _stamp_owner_nonce(migration, conn, migration_id: str, nonce: str) -> None:
    """Stamp an ownership nonce into a row's rollback_metadata_json (as the live
    worker's _mark_migration_started would), so the C2 ownership guards engage."""
    conn.execute(
        "UPDATE arclink_pod_migrations "
        "SET rollback_metadata_json = json_set(COALESCE(NULLIF(rollback_metadata_json, ''), '{}'), ?, ?) "
        "WHERE migration_id = ?",
        (migration._OWNER_TOKEN_JSON_PATH, nonce, migration_id),
    )
    conn.commit()


def test_c2_recovery_rotates_ownership_nonce_out_of_running_row() -> None:
    # C2 core: when a stale-lease recovery wins its CAS it ROTATES the ownership
    # nonce in the SAME atomic UPDATE, revoking the original live worker's
    # ownership while the row is still 'running'. This is the "transition out of
    # running" mechanism (the schema CHECK forbids a literal sentinel status).
    control = load_module("arclink_control.py", "arclink_control_c2_rotate")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_c2_rotate")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_c2_rotate")
    conn = memory_db(control)
    _seed_migration_row(control, conn, migration_id="mig_c2rot", status="running", updated_at="2000-01-01T00:00:00+00:00")
    _stamp_owner_nonce(migration, conn, "mig_c2rot", "own_LIVE_worker")

    stranded = dict(conn.execute("SELECT * FROM arclink_pod_migrations WHERE migration_id = 'mig_c2rot'").fetchone())
    expect(migration._row_owner_token(stranded) == "own_LIVE_worker", "precondition: live worker owns the row")

    executor = executor_mod.ArcLinkExecutor(
        config=executor_mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"),
    )
    recovered = migration._recover_stale_running_migration(
        conn, row=stranded, operation_key="arclink:migration:mig_c2rot",
        intent=migration._operation_intent(stranded, dry_run=False), executor=executor, env={},
    )
    expect(recovered is not None, "stale row must be recovered")
    # The recovery rotated the nonce to its own value (NOT the live worker's).
    final = dict(conn.execute("SELECT rollback_metadata_json, status FROM arclink_pod_migrations WHERE migration_id = 'mig_c2rot'").fetchone())
    rolled_nonce = json.loads(final["rollback_metadata_json"]).get(migration.OWNER_TOKEN_KEY)
    expect(rolled_nonce and rolled_nonce != "own_LIVE_worker", f"recovery must rotate the nonce away from the live worker: {rolled_nonce}")
    expect(final["status"] == "rolled_back", f"recovery drives the row terminal: {final}")
    print("PASS test_c2_recovery_rotates_ownership_nonce_out_of_running_row")


def test_c2_mark_success_fails_when_recovery_rotated_nonce() -> None:
    # C2: the live worker calls _mark_success holding its ORIGINAL nonce, but a
    # recovery has rotated the row's nonce. The token-fenced claim matches zero
    # rows -> _mark_success raises (so the caller's txn rolls back), the terminal
    # status the recovery set is NOT clobbered to 'succeeded', and the live serving
    # placement set is NOT re-flipped under the recovered row.
    control = load_module("arclink_control.py", "arclink_control_c2_ms")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_c2_ms")
    conn = memory_db(control)
    _seed_two_placement_migration(
        control, conn, migration_id="mig_c2ms", status="running",
        updated_at=control.utc_now_iso(), source_status="active", target_status="removed",
    )
    # The live worker's view of the row carries its ORIGINAL nonce.
    _stamp_owner_nonce(migration, conn, "mig_c2ms", "own_LIVE")
    live_row = dict(conn.execute("SELECT * FROM arclink_pod_migrations WHERE migration_id = 'mig_c2ms'").fetchone())
    # Meanwhile a recovery rotated the DB nonce (and would drive it terminal).
    _stamp_owner_nonce(migration, conn, "mig_c2ms", "own_RECOVERY")

    raised = False
    try:
        migration._mark_success(
            conn,
            row=live_row,
            target_intent={"state_roots": {"root": "/arcdata/deployments/dep_1-t"}},
            capture_manifest={"files": [], "file_count": 0},
            verification={"healthy": True},
            retention_days=7,
            commit=True,
        )
    except migration.ArcLinkPodMigrationError:
        raised = True
    if conn.in_transaction:
        conn.rollback()
    expect(raised, "_mark_success must FAIL when the live worker's nonce was rotated out by a recovery")
    # Placements untouched by the failed success: target still removed, source still active.
    placements = {
        r["placement_id"]: r["status"]
        for r in conn.execute("SELECT placement_id, status FROM arclink_deployment_placements").fetchall()
    }
    expect(placements["plc_target"] == "removed", f"target must NOT be flipped active by a rejected success: {placements}")
    expect(placements["plc_source"] == "active", f"source must NOT be retired by a rejected success: {placements}")
    status = dict(conn.execute("SELECT status FROM arclink_pod_migrations WHERE migration_id = 'mig_c2ms'").fetchone())
    expect(status["status"] != "succeeded", f"row must NOT be clobbered to succeeded: {status}")
    print("PASS test_c2_mark_success_fails_when_recovery_rotated_nonce")


def test_c2_mark_rollback_noops_when_recovery_rotated_nonce() -> None:
    # C2: the loser's _mark_rollback (holding the stale nonce) must no-op against a
    # row a recovery re-owned -- no double placement mutation, returns False.
    control = load_module("arclink_control.py", "arclink_control_c2_mr")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_c2_mr")
    conn = memory_db(control)
    _seed_migration_row(control, conn, migration_id="mig_c2mr", status="running", updated_at=control.utc_now_iso())
    _stamp_owner_nonce(migration, conn, "mig_c2mr", "own_LIVE")
    live_row = dict(conn.execute("SELECT * FROM arclink_pod_migrations WHERE migration_id = 'mig_c2mr'").fetchone())
    _stamp_owner_nonce(migration, conn, "mig_c2mr", "own_RECOVERY")

    applied = migration._mark_rollback(
        conn,
        row=live_row,
        verification={"healthy": False, "error": "loser rollback (should not apply)"},
        error="loser rollback (should not apply)",
        lifecycle_metadata={"source_restart": {"status": "completed", "action": "restart"}},
    )
    expect(applied is False, "_mark_rollback must no-op (False) when the nonce was rotated out by a recovery")
    status = dict(conn.execute("SELECT status FROM arclink_pod_migrations WHERE migration_id = 'mig_c2mr'").fetchone())
    expect(status["status"] == "running", f"the loser must NOT drive the row terminal: {status}")
    rolled = conn.execute("SELECT COUNT(*) AS c FROM arclink_events WHERE event_type = 'pod_migration_rolled_back'").fetchone()
    expect(int(rolled["c"]) == 0, "no rollback event for a nonce-mismatched no-op")
    print("PASS test_c2_mark_rollback_noops_when_recovery_rotated_nonce")


def test_c2_heartbeat_reports_lost_ownership_after_recovery_rotation() -> None:
    # C2: the heartbeat returns (ts, still_owned). After a recovery rotates the
    # nonce, the live worker's beat (holding its original nonce) reports
    # still_owned=False -- the signal migrate_pod uses to ABORT its lifecycle work.
    control = load_module("arclink_control.py", "arclink_control_c2_hb")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_c2_hb")
    conn = memory_db(control)
    _seed_migration_row(control, conn, migration_id="mig_c2hb", status="running", updated_at=control.utc_now_iso())
    _stamp_owner_nonce(migration, conn, "mig_c2hb", "own_LIVE")

    _ts, owned = migration._heartbeat_running_migration(conn, "mig_c2hb", owner_token="own_LIVE")
    expect(owned is True, "the owning worker's heartbeat reports still_owned=True")

    # A recovery rotates the nonce out from under the live worker.
    _stamp_owner_nonce(migration, conn, "mig_c2hb", "own_RECOVERY")
    _ts2, owned2 = migration._heartbeat_running_migration(conn, "mig_c2hb", owner_token="own_LIVE")
    expect(owned2 is False, "after the nonce is rotated, the original worker's heartbeat reports lost ownership")
    print("PASS test_c2_heartbeat_reports_lost_ownership_after_recovery_rotation")


def test_c2_live_worker_stops_applying_when_recovered_away_mid_flight() -> None:
    # C2 (the still-broken case Codex flagged): a live worker and a stale-recovery
    # both proceed. Here a recovery rotates the ownership nonce while the live
    # worker is mid-materialize; the live worker's NEXT heartbeat (before
    # docker_compose_apply) reports lost ownership and migrate_pod ABORTS -- it must
    # NOT run docker_compose_apply, NOT double-restart the source, and NOT double-
    # tear-down the target. We count EVERY Docker call (not idempotency-deduped) to
    # prove no double-execution.
    control = load_module("arclink_control.py", "arclink_control_c2_midflight")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_c2_midflight")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_c2_midflight")
    conn = memory_db(control)

    with tempfile.TemporaryDirectory() as tmpdir:
        source_roots, _ = _seed_cross_host_deployment(control, conn, Path(tmpdir))
        source_root = Path(str(source_roots["root"]))
        (source_root / "vault").mkdir(parents=True)
        (source_root / "vault" / "mission.md").write_text("state\n", encoding="utf-8")
        conn.execute(
            "INSERT INTO arclink_deployment_placements (placement_id, deployment_id, host_id, status, placed_at) VALUES ('plc_source', 'dep_1', 'host_source', 'active', ?)",
            (control.utc_now_iso(),),
        )
        conn.commit()

        class _CountingExecutor:
            """Wraps the fake executor and counts EVERY lifecycle/apply call.

            A second worker (the recovery) rotates the ownership nonce the first
            time materialize-time work happens, simulating the concurrent recovery
            winning ownership while this worker is mid-flight.
            """
            def __init__(self, inner):
                self._inner = inner
                self.lifecycle_calls = []   # (action,) for every call, not deduped
                self.apply_calls = 0
                self._rotated = False

            def _rotate_once(self):
                if not self._rotated:
                    self._rotated = True
                    # The concurrent recovery claims the row: rotate the nonce.
                    _stamp_owner_nonce(migration, conn, "mig_c2mid", "own_RECOVERY")

            def docker_compose_lifecycle(self, request):
                self.lifecycle_calls.append(str(request.action))
                return self._inner.docker_compose_lifecycle(request)

            def docker_compose_apply(self, request):
                # If apply is ever reached after ownership was lost, that is the bug.
                self.apply_calls += 1
                # Rotate right before apply so the PRECEDING beat already aborted.
                return self._inner.docker_compose_apply(request)

            def docker_compose_dry_run(self, request):
                return self._inner.docker_compose_dry_run(request)

        class _PermissiveSecretResolver:
            def materialize(self, secret_ref: str, target_path: str):
                return executor_mod.ResolvedSecretFile(secret_ref=secret_ref, target_path=target_path)

        inner = executor_mod.ArcLinkExecutor(
            config=executor_mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"),
            secret_resolver=_PermissiveSecretResolver(),
        )
        counting = _CountingExecutor(inner)

        # Trigger the recovery's nonce rotation during the materialize step by
        # patching _materialize_files to rotate then delegate.
        original_materialize = migration._materialize_files

        def _materialize_then_recover(conn_arg, *, row, target_root, env):
            counting._rotate_once()  # the recovery wins ownership mid-flight
            return original_materialize(conn_arg, row=row, target_root=target_root, env=env)

        migration._materialize_files = _materialize_then_recover
        try:
            raised = False
            try:
                migration.migrate_pod(
                    conn,
                    executor=counting,
                    deployment_id="dep_1",
                    target_machine_id="host_target",
                    migration_id="mig_c2mid",
                    verifier=lambda _c, _r, _i: {"healthy": True},
                    env={"ARCLINK_ACTION_WORKER_ALLOW_ROOT_MIGRATION_CAPTURE": "1"},
                )
            except migration.ArcLinkPodMigrationError:
                raised = True
        finally:
            migration._materialize_files = original_materialize

        expect(raised, "the recovered-away live worker must abort (raise) rather than finish applying")
        # The bug would let the live worker keep going: docker_compose_apply must NOT run.
        expect(counting.apply_calls == 0, f"a recovered-away worker must NOT run docker_compose_apply: {counting.apply_calls}")
        # And it must NOT perform its own rollback lifecycle (the recovery owns that
        # now), so no extra source-restart / target-teardown from the loser.
        expect("restart" not in counting.lifecycle_calls, f"loser must NOT restart the source (recovery owns rollback): {counting.lifecycle_calls}")
        expect("teardown" not in counting.lifecycle_calls, f"loser must NOT tear down the target: {counting.lifecycle_calls}")
        # The source 'stop' is the only lifecycle action the loser legitimately did.
        expect(counting.lifecycle_calls == ["stop"], f"loser only stopped the source before being recovered away: {counting.lifecycle_calls}")
    print("PASS test_c2_live_worker_stops_applying_when_recovered_away_mid_flight")


def test_c2_no_clobber_terminal_invariant_holds_under_recovery_then_late_success() -> None:
    # C2 invariant: a recovery drives the row terminal ('rolled_back'); a LATE
    # success from the original worker (stale nonce) must NOT clobber it. End state:
    # exactly one terminal transition, the recovery's outcome wins.
    control = load_module("arclink_control.py", "arclink_control_c2_inv")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_c2_inv")
    conn = memory_db(control)
    _seed_two_placement_migration(
        control, conn, migration_id="mig_c2inv", status="running",
        updated_at=control.utc_now_iso(), source_status="active", target_status="removed",
    )
    _stamp_owner_nonce(migration, conn, "mig_c2inv", "own_LIVE")
    live_row = dict(conn.execute("SELECT * FROM arclink_pod_migrations WHERE migration_id = 'mig_c2inv'").fetchone())

    # Recovery re-owns + rolls back (terminal).
    _stamp_owner_nonce(migration, conn, "mig_c2inv", "own_RECOVERY")
    recovery_row = dict(conn.execute("SELECT * FROM arclink_pod_migrations WHERE migration_id = 'mig_c2inv'").fetchone())
    applied = migration._mark_rollback(
        conn, row=recovery_row,
        verification={"healthy": False, "error": "recovery"}, error="recovery",
        lifecycle_metadata={"source_restart": {"status": "completed", "action": "restart"}},
    )
    expect(applied is True, "recovery rolls the row back")
    expect(dict(conn.execute("SELECT status FROM arclink_pod_migrations WHERE migration_id = 'mig_c2inv'").fetchone())["status"] == "rolled_back", "row terminal")

    # Late success from the original worker (stale nonce + now-terminal row): must fail.
    raised = False
    try:
        migration._mark_success(
            conn, row=live_row,
            target_intent={"state_roots": {"root": "/arcdata/deployments/dep_1-t"}},
            capture_manifest={"files": [], "file_count": 0},
            verification={"healthy": True}, retention_days=7, commit=True,
        )
    except migration.ArcLinkPodMigrationError:
        raised = True
    if conn.in_transaction:
        conn.rollback()
    expect(raised, "a late success must FAIL against the recovery's terminal row")
    final = dict(conn.execute("SELECT status FROM arclink_pod_migrations WHERE migration_id = 'mig_c2inv'").fetchone())
    expect(final["status"] == "rolled_back", f"no-clobber-terminal: recovery's outcome stands: {final}")
    print("PASS test_c2_no_clobber_terminal_invariant_holds_under_recovery_then_late_success")


def test_r3_recovered_away_worker_does_not_stop_source_or_rollback_lifecycle() -> None:
    # Round 3 / FIX 1: the residual window Codex flagged -- the INITIAL source stop
    # ran BEFORE the first ownership heartbeat, so a worker recovered-away between
    # _mark_migration_started and the stop could still take the live source down
    # (and then run its own _rollback_lifecycle). With the pre-stop _beat_or_abort,
    # a recovered-away worker aborts BEFORE the stop: zero lifecycle calls at all.
    control = load_module("arclink_control.py", "arclink_control_r3_prestop")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_r3_prestop")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_r3_prestop")
    conn = memory_db(control)

    with tempfile.TemporaryDirectory() as tmpdir:
        source_roots, _ = _seed_cross_host_deployment(control, conn, Path(tmpdir))
        (Path(str(source_roots["root"])) / "vault").mkdir(parents=True)
        conn.execute(
            "INSERT INTO arclink_deployment_placements (placement_id, deployment_id, host_id, status, placed_at) VALUES ('plc_source', 'dep_1', 'host_source', 'active', ?)",
            (control.utc_now_iso(),),
        )
        conn.commit()

        class _CountingExecutor:
            def __init__(self, inner):
                self._inner = inner
                self.lifecycle_calls = []
                self.apply_calls = 0

            def docker_compose_lifecycle(self, request):
                self.lifecycle_calls.append(str(request.action))
                return self._inner.docker_compose_lifecycle(request)

            def docker_compose_apply(self, request):
                self.apply_calls += 1
                return self._inner.docker_compose_apply(request)

            def docker_compose_dry_run(self, request):
                return self._inner.docker_compose_dry_run(request)

        inner = executor_mod.ArcLinkExecutor(
            config=executor_mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"),
        )
        counting = _CountingExecutor(inner)

        # Simulate the recovery winning ownership the instant the row goes 'running':
        # patch _mark_migration_started to start the row normally, then ROTATE the
        # nonce out (as a concurrent stale-lease recovery would) before control
        # returns to migrate_pod's pre-stop heartbeat.
        original_started = migration._mark_migration_started

        def _start_then_recover(conn_arg, *, row, reason):
            started = original_started(conn_arg, row=row, reason=reason)
            _stamp_owner_nonce(migration, conn_arg, str(started["migration_id"]), "own_RECOVERY")
            return started

        migration._mark_migration_started = _start_then_recover
        try:
            raised = False
            try:
                migration.migrate_pod(
                    conn,
                    executor=counting,
                    deployment_id="dep_1",
                    target_machine_id="host_target",
                    migration_id="mig_r3prestop",
                    verifier=lambda _c, _r, _i: {"healthy": True},
                    env={"ARCLINK_ACTION_WORKER_ALLOW_ROOT_MIGRATION_CAPTURE": "1"},
                )
            except migration.ArcLinkPodMigrationError:
                raised = True
        finally:
            migration._mark_migration_started = original_started

        expect(raised, "a recovered-away worker must abort (raise) before the source stop")
        # The whole point: NO lifecycle work at all -- not even the source stop, and
        # certainly not a rollback restart/teardown (the recovery owns all of that).
        expect(counting.lifecycle_calls == [], f"recovered-away worker must NOT run ANY Docker lifecycle (incl. the initial stop): {counting.lifecycle_calls}")
        expect(counting.apply_calls == 0, f"recovered-away worker must NOT apply: {counting.apply_calls}")
        # The live source placement must be untouched (never marked removed by a stop
        # that never happened).
        src = dict(conn.execute("SELECT status FROM arclink_deployment_placements WHERE placement_id = 'plc_source'").fetchone())
        expect(src["status"] == "active", f"live source must remain active (never stopped): {src}")
    print("PASS test_r3_recovered_away_worker_does_not_stop_source_or_rollback_lifecycle")


def test_r3_verify_fail_after_recovery_rotation_does_not_double_rollback_lifecycle() -> None:
    # Round 3 / FIX 1 (second window): after docker_compose_apply, if verification
    # FAILS, the code used to run _rollback_lifecycle unconditionally -- even when a
    # concurrent recovery had already rotated the nonce out and owns the rollback.
    # That double-ran the source-restart / target-teardown Docker work. Now the
    # verify-fail branch re-checks ownership and SKIPS _rollback_lifecycle when the
    # row was recovered away. We exercise the branch directly: own_token mismatch ->
    # _still_owns_running_row is False -> no Docker lifecycle.
    control = load_module("arclink_control.py", "arclink_control_r3_verifyfail")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_r3_verifyfail")
    conn = memory_db(control)
    _seed_migration_row(control, conn, migration_id="mig_r3vf", status="running", updated_at=control.utc_now_iso())
    _stamp_owner_nonce(migration, conn, "mig_r3vf", "own_RECOVERY")  # recovery now owns it

    # The live worker still holds its ORIGINAL token; _still_owns_running_row must
    # report False so the verify-fail branch would skip _rollback_lifecycle.
    owns = migration._still_owns_running_row(conn, migration_id="mig_r3vf", owner_token="own_LIVE")
    expect(owns is False, "a worker whose nonce was rotated out must NOT be reported as still owning the row")
    # And the owning (recovery) token IS reported as owner.
    owns_recovery = migration._still_owns_running_row(conn, migration_id="mig_r3vf", owner_token="own_RECOVERY")
    expect(owns_recovery is True, "the current owner must be reported as still owning the running row")
    # A terminal row is never 'still owned' (defensive).
    conn.execute("UPDATE arclink_pod_migrations SET status = 'rolled_back' WHERE migration_id = 'mig_r3vf'")
    conn.commit()
    owns_terminal = migration._still_owns_running_row(conn, migration_id="mig_r3vf", owner_token="own_RECOVERY")
    expect(owns_terminal is False, "a terminal row must never be reported as a still-owned running row")
    print("PASS test_r3_verify_fail_after_recovery_rotation_does_not_double_rollback_lifecycle")


def test_r3_lease_exceeds_max_uninterrupted_docker_op() -> None:
    # Round 3 / FIX 2: a worker actively inside a single max-duration migration op
    # (e.g. docker_compose_apply, which chains rsync + compose up = up to TWO
    # back-to-back long executor ops with NO heartbeat between) must never be
    # declared stale before the op returns. The enforced minimum lease must exceed
    # that worst-case uninterrupted duration, and the env-configured lease must be
    # clamped UP to it (mirrors the LLM reaper TTL > read_timeout fix).
    executor_mod = load_module("arclink_executor.py", "arclink_executor_r3_lease")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_r3_lease")

    long_op = int(executor_mod._SUBPROCESS_LONG_TIMEOUT)
    # The relationship the comment documents: lease floor >= 2 * long-op + margin.
    expect(
        migration.MINIMUM_MIGRATION_RUNNING_LEASE_SECONDS >= 2 * long_op,
        f"minimum lease ({migration.MINIMUM_MIGRATION_RUNNING_LEASE_SECONDS}) must exceed two back-to-back "
        f"max-duration Docker ops (2*{long_op})",
    )
    expect(
        migration.MINIMUM_MIGRATION_RUNNING_LEASE_SECONDS > migration._MAX_UNINTERRUPTED_MIGRATION_OP_SECONDS,
        "minimum lease must include headroom above the worst-case uninterrupted op",
    )
    # An operator who shortens the lease via env CANNOT push it below the floor.
    clamped = migration._migration_running_lease_seconds({"ARCLINK_POD_MIGRATION_RUNNING_LEASE_SECONDS": "60"})
    expect(
        clamped == migration.MINIMUM_MIGRATION_RUNNING_LEASE_SECONDS,
        f"an env lease below the floor must be clamped UP to the floor: {clamped}",
    )
    # A larger env value is honored as-is.
    big = migration.MINIMUM_MIGRATION_RUNNING_LEASE_SECONDS + 10_000
    honored = migration._migration_running_lease_seconds({"ARCLINK_POD_MIGRATION_RUNNING_LEASE_SECONDS": str(big)})
    expect(honored == big, f"a lease above the floor must be honored: {honored}")
    # The default lease is itself heartbeat-safe.
    expect(
        migration.DEFAULT_MIGRATION_RUNNING_LEASE_SECONDS >= migration.MINIMUM_MIGRATION_RUNNING_LEASE_SECONDS,
        "the default lease must be at least the enforced floor",
    )

    # Behavioral check: a worker whose updated_at is younger than the floor (i.e.
    # it could plausibly be mid-apply) is NOT recovered, even at the shortest
    # configurable lease. We simulate "inside one max-duration op": the row's
    # updated_at is (max-op - 1) old -- younger than the floor -> not stale.
    control = load_module("arclink_control.py", "arclink_control_r3_lease")
    ex2 = load_module("arclink_executor.py", "arclink_executor_r3_lease2")
    conn = memory_db(control)
    import datetime as _dt
    inside_op = migration._MAX_UNINTERRUPTED_MIGRATION_OP_SECONDS - 1
    mid_apply_ts = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(seconds=inside_op)).isoformat()
    _seed_migration_row(control, conn, migration_id="mig_r3midop", status="running", updated_at=mid_apply_ts)
    executor = ex2.ArcLinkExecutor(config=ex2.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"))
    row = dict(conn.execute("SELECT * FROM arclink_pod_migrations WHERE migration_id = 'mig_r3midop'").fetchone())
    not_recovered = migration._recover_stale_running_migration(
        conn, row=row, operation_key="arclink:migration:mig_r3midop",
        intent=migration._operation_intent(row, dry_run=False), executor=executor,
        env={"ARCLINK_POD_MIGRATION_RUNNING_LEASE_SECONDS": "60"},  # below floor -> clamped up
    )
    expect(not_recovered is None, "a worker inside one max-duration op must NOT be declared stale / recovered")
    expect(executor._fake_lifecycle_runs == {}, f"a mid-apply worker must not be disturbed: {executor._fake_lifecycle_runs}")
    print("PASS test_r3_lease_exceeds_max_uninterrupted_docker_op")


def test_r3_mark_rollback_releases_write_lock_before_capture_rmtree() -> None:
    # Round 3 / FIX 3: _mark_rollback used to hold BEGIN IMMEDIATE across the slow
    # capture-dir rmtree. It now COMMITS the claim + placement mutation + terminal
    # UPDATE first (short writer lock), then does the rmtree OUTSIDE the lock. We
    # prove the writer lock is NOT held during the rmtree by detecting it from
    # inside shutil.rmtree: a concurrent writer (a second connection) must be able
    # to acquire BEGIN IMMEDIATE while the rmtree runs. We also confirm the capture
    # dir is actually removed and the terminal state is correct.
    control = load_module("arclink_control.py", "arclink_control_r3_lock")
    migration = load_module("arclink_pod_migration.py", "arclink_pod_migration_r3_lock")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "control.sqlite")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        control.ensure_schema(conn)
        # A real capture dir under .migrations so the rmtree has something to delete.
        capture_dir = Path(tmpdir) / "deployments" / ".migrations" / "mig_r3lock"
        (capture_dir / "source-root" / "vault").mkdir(parents=True)
        (capture_dir / "source-root" / "vault" / "mission.md").write_text("captured\n", encoding="utf-8")

        control.upsert_arclink_user(conn, user_id="user_1", email="u@example.test", entitlement_state="paid")
        control.reserve_arclink_deployment_prefix(
            conn, deployment_id="dep_1", user_id="user_1", prefix="cap-one", base_domain="example.test", status="active"
        )
        conn.execute(
            "INSERT INTO arclink_deployment_placements (placement_id, deployment_id, host_id, status, placed_at) VALUES ('plc_source', 'dep_1', 'host_source', 'active', ?)",
            (control.utc_now_iso(),),
        )
        now = control.utc_now_iso()
        conn.execute(
            """
            INSERT INTO arclink_pod_migrations (
              migration_id, deployment_id, source_host_id, target_host_id, target_machine_id,
              source_placement_id, target_placement_id, source_state_root, target_state_root,
              capture_dir, status, operation_idempotency_key, created_at, updated_at
            ) VALUES ('mig_r3lock', 'dep_1', 'host_source', 'host_source', 'current',
              'plc_source', '', '/arcdata/deployments/dep_1', '/arcdata/deployments/dep_1',
              ?, 'running', 'arclink:migration:mig_r3lock', ?, ?)
            """,
            (str(capture_dir), now, now),
        )
        conn.commit()
        row = dict(conn.execute("SELECT * FROM arclink_pod_migrations WHERE migration_id = 'mig_r3lock'").fetchone())

        # A SECOND connection used to probe whether the writer lock is held DURING
        # the rmtree. Short busy timeout so a held lock surfaces quickly as an error.
        probe = sqlite3.connect(db_path, timeout=0.0)
        probe.execute("PRAGMA busy_timeout = 0")
        lock_free_during_rmtree = {"value": None}

        real_rmtree = migration.shutil.rmtree

        def _probing_rmtree(path, *args, **kwargs):
            # While we are inside the rmtree, the _mark_rollback writer lock must be
            # released (committed). Prove it: a concurrent BEGIN IMMEDIATE succeeds.
            try:
                probe.execute("BEGIN IMMEDIATE")
                probe.execute("ROLLBACK")
                lock_free_during_rmtree["value"] = True
            except sqlite3.OperationalError:
                lock_free_during_rmtree["value"] = False
            return real_rmtree(path, *args, **kwargs)

        migration.shutil.rmtree = _probing_rmtree
        try:
            applied = migration._mark_rollback(
                conn,
                row=row,
                verification={"healthy": False, "error": "verify failed"},
                error="verify failed",
                lifecycle_metadata={"source_restart": {"status": "completed", "action": "restart"}},
            )
        finally:
            migration.shutil.rmtree = real_rmtree
            probe.close()

        expect(applied is True, "the running row must roll back")
        expect(lock_free_during_rmtree["value"] is True,
               "the SQLite writer lock must be RELEASED before the capture rmtree (a concurrent BEGIN IMMEDIATE must succeed)")
        expect(not capture_dir.exists(), "the capture dir must actually be removed by the deferred rmtree")
        final = dict(conn.execute(
            "SELECT status, rollback_metadata_json, source_garbage_collected_at FROM arclink_pod_migrations WHERE migration_id = 'mig_r3lock'"
        ).fetchone())
        expect(final["status"] == "rolled_back", f"row must be terminal: {final}")
        meta = json.loads(final["rollback_metadata_json"])
        expect(meta["capture_cleanup"]["removed"] is True, f"capture_cleanup must record the actual removal: {meta}")
        expect(final["source_garbage_collected_at"], f"source_garbage_collected_at must be stamped after a successful rmtree: {final}")
        conn.close()
    print("PASS test_r3_mark_rollback_releases_write_lock_before_capture_rmtree")


def main() -> int:
    test_h3_rollback_does_not_reactivate_source_when_restart_failed()
    test_h3_rollback_reactivates_source_when_restart_completed()
    test_h3_round2_live_active_source_not_left_serving_on_failed_restart()
    test_h4_same_root_materialize_is_atomic_and_non_destructive()
    test_h6_stale_running_migration_is_recovered_to_terminal()
    test_h6_round2_stale_recovery_tears_down_half_up_cross_host_target()
    test_h6_round2_fresh_running_migration_is_not_disturbed_on_reentry()
    test_c1_mark_rollback_against_succeeded_row_is_noop()
    test_c1_mark_rollback_against_running_row_applies()
    test_c1_two_concurrent_recoveries_only_one_rolls_back()
    test_c1_heartbeat_keeps_live_slow_migration_from_going_stale()
    test_c1_heartbeat_cannot_resurrect_terminal_row()
    test_m3_orphan_prev_backup_is_restored_when_target_missing()
    test_m4_recovery_loops_over_all_stale_running_rows()
    test_c2_recovery_rotates_ownership_nonce_out_of_running_row()
    test_c2_mark_success_fails_when_recovery_rotated_nonce()
    test_c2_mark_rollback_noops_when_recovery_rotated_nonce()
    test_c2_heartbeat_reports_lost_ownership_after_recovery_rotation()
    test_c2_live_worker_stops_applying_when_recovered_away_mid_flight()
    test_c2_no_clobber_terminal_invariant_holds_under_recovery_then_late_success()
    test_r3_recovered_away_worker_does_not_stop_source_or_rollback_lifecycle()
    test_r3_verify_fail_after_recovery_rotation_does_not_double_rollback_lifecycle()
    test_r3_lease_exceeds_max_uninterrupted_docker_op()
    test_r3_mark_rollback_releases_write_lock_before_capture_rmtree()
    print("PASS all 24 ArcLink pod migration safety regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
