#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
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


def test_compute_asu_defaults_and_edges() -> None:
    asu = load_module("arclink_asu.py", "arclink_asu_test")
    expect(asu.compute_asu({"vcpu_cores": 4, "ram_gib": 16, "disk_gib": 120}, {}) == 4, "expected 4 ASU")
    expect(asu.compute_asu({"vcpu_cores": 8, "ram_gib": 64, "disk_gib": 20}, {}) == 0, "tiny disk is unusable")
    try:
        asu.compute_asu({"vcpu_cores": 0, "ram_gib": 16, "disk_gib": 120}, {})
    except asu.ArcLinkASUError:
        pass
    else:
        raise AssertionError("zero vCPU should fail closed")
    try:
        asu.compute_asu({"vcpu_cores": 4, "ram_gib": 16}, {})
    except asu.ArcLinkASUError:
        pass
    else:
        raise AssertionError("missing disk should fail closed")
    expect(
        asu.compute_asu(
            {"vcpu_cores": 8, "ram_gib": 32, "disk_gib": 240},
            {"ARCLINK_ASU_VCPU_PER_POD": "2", "ARCLINK_ASU_RAM_PER_POD": "8", "ARCLINK_ASU_DISK_PER_POD": "60"},
        )
        == 4,
        "env sizing should be honored",
    )
    print("PASS test_compute_asu_defaults_and_edges")


def test_current_load_counts_active_placements() -> None:
    control = load_module("arclink_control.py", "arclink_control_asu_load")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_asu_load")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_asu_load")
    asu = load_module("arclink_asu.py", "arclink_asu_load")
    conn = memory_db(control)
    host = fleet.register_fleet_host(conn, hostname="h1.test", capacity_slots=4)
    machine = inventory.register_inventory_machine(
        conn,
        provider="manual",
        hostname="h1.test",
        machine_host_link=host["host_id"],
        status="ready",
        asu_capacity=4,
    )
    fleet.place_deployment(conn, deployment_id="dep_1")
    expect(asu.current_load(machine["machine_id"], conn) == 1.0, "one active placement consumes one ASU")
    print("PASS test_current_load_counts_active_placements")


if __name__ == "__main__":
    test_compute_asu_defaults_and_edges()
    test_current_load_counts_active_placements()
    print("\nAll ASU tests passed.")
