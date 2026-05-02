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


def test_register_fleet_host() -> None:
    control = load_module("almanac_control.py", "almanac_control_fleet_reg")
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


def test_register_rejects_empty_hostname() -> None:
    control = load_module("almanac_control.py", "almanac_control_fleet_empty")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_empty")
    conn = memory_db(control)
    try:
        fleet.register_fleet_host(conn, hostname="")
        raise AssertionError("should reject empty hostname")
    except fleet.ArcLinkFleetError:
        pass
    print("PASS test_register_rejects_empty_hostname")


def test_update_fleet_host_drain() -> None:
    control = load_module("almanac_control.py", "almanac_control_fleet_drain")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_drain")
    conn = memory_db(control)
    host = fleet.register_fleet_host(conn, hostname="h1.test", capacity_slots=10)
    updated = fleet.update_fleet_host(conn, host_id=host["host_id"], drain=True)
    expect(int(updated["drain"]) == 1, "drain flag set")
    print("PASS test_update_fleet_host_drain")


def test_fleet_capacity_summary() -> None:
    control = load_module("almanac_control.py", "almanac_control_fleet_cap")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_cap")
    conn = memory_db(control)
    fleet.register_fleet_host(conn, hostname="h1.test", capacity_slots=10)
    fleet.register_fleet_host(conn, hostname="h2.test", capacity_slots=5)
    summary = fleet.fleet_capacity_summary(conn)
    expect(summary["total_hosts"] == 2, "two hosts")
    expect(summary["total_slots"] == 15, "total slots")
    expect(summary["available_slots"] == 15, "all available")
    print("PASS test_fleet_capacity_summary")


def test_place_deployment_chooses_healthy_host() -> None:
    control = load_module("almanac_control.py", "almanac_control_fleet_place")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_place")
    conn = memory_db(control)
    fleet.register_fleet_host(conn, hostname="h1.test", capacity_slots=5)
    h2 = fleet.register_fleet_host(conn, hostname="h2.test", capacity_slots=10)
    placement = fleet.place_deployment(conn, deployment_id="dep_1")
    expect(placement["host_id"] == h2["host_id"], "picks host with more headroom")
    expect(placement["status"] == "active", "placement is active")
    print("PASS test_place_deployment_chooses_healthy_host")


def test_place_deployment_rejects_saturated_hosts() -> None:
    control = load_module("almanac_control.py", "almanac_control_fleet_sat")
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
    control = load_module("almanac_control.py", "almanac_control_fleet_drn")
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
    control = load_module("almanac_control.py", "almanac_control_fleet_unh")
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
    control = load_module("almanac_control.py", "almanac_control_fleet_idem")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_idem")
    conn = memory_db(control)
    fleet.register_fleet_host(conn, hostname="h1.test", capacity_slots=10)
    p1 = fleet.place_deployment(conn, deployment_id="dep_1")
    p2 = fleet.place_deployment(conn, deployment_id="dep_1")
    expect(p1["placement_id"] == p2["placement_id"], "idempotent placement")
    print("PASS test_placement_idempotent")


def test_remove_placement() -> None:
    control = load_module("almanac_control.py", "almanac_control_fleet_rm")
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
    control = load_module("almanac_control.py", "almanac_control_fleet_rgn")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_rgn")
    conn = memory_db(control)
    fleet.register_fleet_host(conn, hostname="h1.test", region="us-east", capacity_slots=10)
    h2 = fleet.register_fleet_host(conn, hostname="h2.test", region="eu-west", capacity_slots=10)
    placement = fleet.place_deployment(conn, deployment_id="dep_1", region="eu-west")
    expect(placement["host_id"] == h2["host_id"], "picked eu-west host")
    print("PASS test_region_filter")


def test_placement_rejects_secret_required_tags() -> None:
    control = load_module("almanac_control.py", "almanac_control_fleet_secret_tags")
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
    test_register_rejects_empty_hostname()
    test_update_fleet_host_drain()
    test_fleet_capacity_summary()
    test_place_deployment_chooses_healthy_host()
    test_place_deployment_rejects_saturated_hosts()
    test_place_deployment_rejects_draining_hosts()
    test_place_deployment_rejects_unhealthy_hosts()
    test_placement_idempotent()
    test_remove_placement()
    test_region_filter()
    test_placement_rejects_secret_required_tags()
    print(f"\nAll 12 fleet tests passed.")
