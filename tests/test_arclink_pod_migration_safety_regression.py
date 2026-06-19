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


def main() -> int:
    test_h3_rollback_does_not_reactivate_source_when_restart_failed()
    test_h3_rollback_reactivates_source_when_restart_completed()
    test_h3_round2_live_active_source_not_left_serving_on_failed_restart()
    test_h4_same_root_materialize_is_atomic_and_non_destructive()
    test_h6_stale_running_migration_is_recovered_to_terminal()
    test_h6_round2_stale_recovery_tears_down_half_up_cross_host_target()
    test_h6_round2_fresh_running_migration_is_not_disturbed_on_reentry()
    print("PASS all 7 ArcLink pod migration safety regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
