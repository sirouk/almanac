#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sqlite3
import sys
import tempfile
import threading
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


def test_register_fleet_host() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_reg")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_reg")
    conn = memory_db(control)
    host = fleet.register_fleet_host(conn, hostname="host-1.example.com", region="eu-central", capacity_slots=20)
    expect(host["hostname"] == "host-1.example.com", "hostname preserved")
    expect(host["region"] == "eu-central", "region preserved")
    expect(int(host["capacity_slots"]) == 20, "capacity preserved")
    expect(host["status"] == "active", "default status is active")
    # Idempotent re-register
    host2 = fleet.register_fleet_host(conn, hostname="host-1.example.com")
    expect(host2["host_id"] == host["host_id"], "idempotent re-register")
    print("PASS test_register_fleet_host")


def test_register_existing_fleet_host_updates_config_without_touching_load() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_rereg")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_rereg")
    conn = memory_db(control)
    host = fleet.register_fleet_host(
        conn,
        hostname="worker-1.example.test",
        region="old",
        capacity_slots=1,
        metadata={"edge_target": "old.example.test"},
    )
    fleet.update_fleet_host(conn, host_id=host["host_id"], observed_load=1)
    updated = fleet.register_fleet_host(
        conn,
        hostname="WORKER-1.EXAMPLE.TEST",
        region="us-east",
        capacity_slots=4,
        metadata={"edge_target": "new.example.test", "executor": "local"},
    )
    expect(updated["host_id"] == host["host_id"], "existing host preserved")
    expect(updated["region"] == "us-east", "region refreshed")
    expect(int(updated["capacity_slots"]) == 4, "capacity refreshed")
    expect(int(updated["observed_load"]) == 1, "load is not blindly reset during registration")
    expect("new.example.test" in updated["metadata_json"], updated["metadata_json"])
    print("PASS test_register_existing_fleet_host_updates_config_without_touching_load")


def test_register_rejects_empty_hostname() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_empty")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_empty")
    conn = memory_db(control)
    try:
        fleet.register_fleet_host(conn, hostname="")
        raise AssertionError("should reject empty hostname")
    except fleet.ArcLinkFleetError:
        pass
    print("PASS test_register_rejects_empty_hostname")


def test_update_fleet_host_drain() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_drain")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_drain")
    conn = memory_db(control)
    host = fleet.register_fleet_host(conn, hostname="h1.test", capacity_slots=10)
    updated = fleet.update_fleet_host(conn, host_id=host["host_id"], drain=True)
    expect(int(updated["drain"]) == 1, "drain flag set")
    print("PASS test_update_fleet_host_drain")


def test_fleet_capacity_summary() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_cap")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_cap")
    conn = memory_db(control)
    fleet.register_fleet_host(conn, hostname="h1.test", capacity_slots=10)
    fleet.register_fleet_host(conn, hostname="h2.test", capacity_slots=5)
    summary = fleet.fleet_capacity_summary(conn)
    expect(summary["total_hosts"] == 2, "two hosts")
    expect(summary["total_slots"] == 15, "total slots")
    expect(summary["available_slots"] == 15, "all available")
    print("PASS test_fleet_capacity_summary")


def test_reconcile_fleet_observed_loads_repairs_stale_load() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_reconcile")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_reconcile")
    conn = memory_db(control)
    host = fleet.register_fleet_host(conn, hostname="h1.test", capacity_slots=4)
    fleet.update_fleet_host(conn, host_id=host["host_id"], observed_load=4)
    repaired = fleet.reconcile_fleet_observed_loads(conn)
    expect(len(repaired) == 1, str(repaired))
    expect(repaired[0]["old_load"] == 4 and repaired[0]["observed_load"] == 0, str(repaired))
    refreshed = fleet.get_fleet_host(conn, host_id=host["host_id"])
    expect(int(refreshed["observed_load"]) == 0, str(refreshed))
    placement = fleet.place_deployment(conn, deployment_id="dep_1")
    expect(placement["host_id"] == host["host_id"], str(placement))
    repaired_again = fleet.reconcile_fleet_observed_loads(conn)
    expect(repaired_again == [], str(repaired_again))
    print("PASS test_reconcile_fleet_observed_loads_repairs_stale_load")


def test_place_deployment_chooses_healthy_host() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_place")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_place")
    conn = memory_db(control)
    fleet.register_fleet_host(conn, hostname="h1.test", capacity_slots=5)
    h2 = fleet.register_fleet_host(conn, hostname="h2.test", capacity_slots=10)
    placement = fleet.place_deployment(conn, deployment_id="dep_1")
    expect(placement["host_id"] == h2["host_id"], "picks host with more headroom")
    expect(placement["status"] == "active", "placement is active")
    print("PASS test_place_deployment_chooses_healthy_host")


def test_place_deployment_rejects_saturated_hosts() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_sat")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_sat")
    conn = memory_db(control)
    host = fleet.register_fleet_host(conn, hostname="h1.test", capacity_slots=1)
    fleet.update_fleet_host(conn, host_id=host["host_id"], observed_load=1)
    try:
        fleet.place_deployment(conn, deployment_id="dep_1")
        raise AssertionError("should reject when all hosts saturated")
    except fleet.ArcLinkFleetError as exc:
        expect("saturated" in str(exc), f"expected useful saturated error, got {exc}")
    print("PASS test_place_deployment_rejects_saturated_hosts")


def test_place_deployment_rejects_draining_hosts() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_drn")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_drn")
    conn = memory_db(control)
    host = fleet.register_fleet_host(conn, hostname="h1.test", capacity_slots=10)
    fleet.update_fleet_host(conn, host_id=host["host_id"], drain=True)
    try:
        fleet.place_deployment(conn, deployment_id="dep_1")
        raise AssertionError("should reject draining hosts")
    except fleet.ArcLinkFleetError as exc:
        expect("draining" in str(exc), f"expected useful draining error, got {exc}")
    print("PASS test_place_deployment_rejects_draining_hosts")


def test_place_deployment_rejects_unhealthy_hosts() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_unh")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_unh")
    conn = memory_db(control)
    host = fleet.register_fleet_host(conn, hostname="h1.test", capacity_slots=10)
    fleet.update_fleet_host(conn, host_id=host["host_id"], status="offline")
    try:
        fleet.place_deployment(conn, deployment_id="dep_1")
        raise AssertionError("should reject offline hosts")
    except fleet.ArcLinkFleetError as exc:
        expect("unhealthy" in str(exc), f"expected useful unhealthy error, got {exc}")
    print("PASS test_place_deployment_rejects_unhealthy_hosts")


def test_placement_idempotent() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_idem")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_idem")
    conn = memory_db(control)
    fleet.register_fleet_host(conn, hostname="h1.test", capacity_slots=10)
    p1 = fleet.place_deployment(conn, deployment_id="dep_1")
    p2 = fleet.place_deployment(conn, deployment_id="dep_1")
    expect(p1["placement_id"] == p2["placement_id"], "idempotent placement")
    print("PASS test_placement_idempotent")


def test_active_placement_unique_index_migrates_existing_duplicates() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_unique_migration")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE arclink_deployment_placements (
          placement_id TEXT PRIMARY KEY,
          deployment_id TEXT NOT NULL,
          host_id TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'active',
          placed_at TEXT NOT NULL,
          removed_at TEXT NOT NULL DEFAULT ''
        );
        INSERT INTO arclink_deployment_placements (placement_id, deployment_id, host_id, status, placed_at)
        VALUES
          ('plc_old_1', 'dep_1', 'host_1', 'active', '2026-05-11T00:00:00+00:00'),
          ('plc_old_2', 'dep_1', 'host_2', 'active', '2026-05-11T00:00:01+00:00');
        """
    )
    control.ensure_schema(conn)
    active = conn.execute("SELECT COUNT(*) AS c FROM arclink_deployment_placements WHERE deployment_id = 'dep_1' AND status = 'active'").fetchone()["c"]
    removed = conn.execute("SELECT COUNT(*) AS c FROM arclink_deployment_placements WHERE deployment_id = 'dep_1' AND status = 'removed'").fetchone()["c"]
    expect(int(active) == 1 and int(removed) == 1, f"expected duplicate migration to leave one active, got active={active}, removed={removed}")
    try:
        conn.execute(
            """
            INSERT INTO arclink_deployment_placements (placement_id, deployment_id, host_id, status, placed_at)
            VALUES ('plc_old_3', 'dep_1', 'host_3', 'active', '2026-05-11T00:00:02+00:00')
            """
        )
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("expected active placement unique index to reject duplicates")
    print("PASS test_active_placement_unique_index_migrates_existing_duplicates")


def test_concurrent_placement_returns_one_active_row() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_concurrent")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_concurrent")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = f"{tmpdir}/control.sqlite3"
        seed = sqlite3.connect(db_path, timeout=15)
        seed.row_factory = sqlite3.Row
        control.ensure_schema(seed)
        fleet.register_fleet_host(seed, hostname="h1.test", capacity_slots=2)
        seed.close()

        barrier = threading.Barrier(2)
        results: list[dict[str, object]] = []
        errors: list[str] = []
        lock = threading.Lock()

        def place() -> None:
            conn = sqlite3.connect(db_path, timeout=15)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout = 15000")
            try:
                barrier.wait(timeout=5)
                placement = fleet.place_deployment(conn, deployment_id="dep_1")
                with lock:
                    results.append(placement)
            except Exception as exc:  # noqa: BLE001 - test records any unexpected thread failure
                with lock:
                    errors.append(str(exc))
            finally:
                conn.close()

        threads = [threading.Thread(target=place), threading.Thread(target=place)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        expect(errors == [], f"parallel placement errors: {errors}")
        expect(len({str(row["placement_id"]) for row in results}) == 1, str(results))
        check = sqlite3.connect(db_path)
        check.row_factory = sqlite3.Row
        active = check.execute("SELECT COUNT(*) AS c FROM arclink_deployment_placements WHERE deployment_id = 'dep_1' AND status = 'active'").fetchone()["c"]
        host = check.execute("SELECT observed_load FROM arclink_fleet_hosts").fetchone()
        events = check.execute("SELECT COUNT(*) AS c FROM arclink_events WHERE event_type = 'placement_assigned'").fetchone()["c"]
        expect(int(active) == 1, f"expected one active placement, got {active}")
        expect(int(host["observed_load"]) == 1, str(dict(host)))
        expect(int(events) == 1, f"expected one placement event, got {events}")
        check.close()
    print("PASS test_concurrent_placement_returns_one_active_row")


def test_remove_placement() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_rm")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_rm")
    conn = memory_db(control)
    fleet.register_fleet_host(conn, hostname="h1.test", capacity_slots=10)
    fleet.place_deployment(conn, deployment_id="dep_1")
    removed = fleet.remove_placement(conn, deployment_id="dep_1")
    expect(removed is not None, "removed placement returned")
    expect(removed["status"] == "removed", "status is removed")
    expect(fleet.get_deployment_placement(conn, deployment_id="dep_1") is None, "no active placement")
    print("PASS test_remove_placement")


def test_region_filter() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_rgn")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_rgn")
    conn = memory_db(control)
    fleet.register_fleet_host(conn, hostname="h1.test", region="us-east", capacity_slots=10)
    h2 = fleet.register_fleet_host(conn, hostname="h2.test", region="eu-west", capacity_slots=10)
    placement = fleet.place_deployment(conn, deployment_id="dep_1", region="eu-west")
    expect(placement["host_id"] == h2["host_id"], "picked eu-west host")
    print("PASS test_region_filter")


def test_placement_rejects_secret_required_tags() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_secret_tags")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_secret_tags")
    conn = memory_db(control)
    fleet.register_fleet_host(conn, hostname="h1.test", tags={"tier": "paid"})
    try:
        fleet.place_deployment(conn, deployment_id="dep_1", required_tags={"api_key": "sk_test_secretvalue123"})
        raise AssertionError("should reject secret-looking required tags")
    except fleet.ArcLinkFleetError:
        pass
    print("PASS test_placement_rejects_secret_required_tags")


if __name__ == "__main__":
    test_register_fleet_host()
    test_register_existing_fleet_host_updates_config_without_touching_load()
    test_register_rejects_empty_hostname()
    test_update_fleet_host_drain()
    test_fleet_capacity_summary()
    test_reconcile_fleet_observed_loads_repairs_stale_load()
    test_place_deployment_chooses_healthy_host()
    test_place_deployment_rejects_saturated_hosts()
    test_place_deployment_rejects_draining_hosts()
    test_place_deployment_rejects_unhealthy_hosts()
    test_placement_idempotent()
    test_active_placement_unique_index_migrates_existing_duplicates()
    test_concurrent_placement_returns_one_active_row()
    test_remove_placement()
    test_region_filter()
    test_placement_rejects_secret_required_tags()
    print(f"\nAll 16 fleet tests passed.")
