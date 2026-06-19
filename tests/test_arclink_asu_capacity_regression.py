#!/usr/bin/env python3
"""Regression tests for the ASU capacity wave (C1 zero-floor, C2 overcommit)."""
from __future__ import annotations

import sqlite3

from arclink_test_helpers import expect, load_module, memory_db


def _seed_linked_machine(control, fleet, inventory, conn, *, asu_capacity: float):
    host = fleet.register_fleet_host(conn, hostname="cap.test", capacity_slots=4)
    machine = inventory.register_inventory_machine(
        conn,
        provider="manual",
        hostname="cap.test",
        machine_host_link=host["host_id"],
        status="ready",
        asu_capacity=asu_capacity,
    )
    return dict(host), dict(machine)


def test_c1_zero_probe_dimension_is_invalid_not_zero_capacity() -> None:
    asu = load_module("arclink_asu.py", "arclink_asu_c1_zero")
    # A genuinely-present-but-tiny disk still computes a real (possibly 0-unit) value.
    expect(asu.compute_asu({"vcpu_cores": 8, "ram_gib": 64, "disk_gib": 20}, {}) == 0, "tiny-but-real disk floors to 0 units")
    # A ZERO probe dimension means the dimension could not be measured -> invalid,
    # must NOT silently produce a 0-capacity machine.
    for partial in (
        {"vcpu_cores": 8, "ram_gib": 16, "disk_gib": 0},
        {"vcpu_cores": 8, "ram_gib": 0, "disk_gib": 100},
        {"vcpu_cores": 0, "ram_gib": 16, "disk_gib": 100},
    ):
        try:
            asu.compute_asu(partial, {})
        except asu.ArcLinkASUError:
            pass
        else:
            raise AssertionError(f"zero probe dimension must fail closed: {partial}")
    # An absent field is also invalid (distinct from "tiny").
    try:
        asu.compute_asu({"vcpu_cores": 4, "ram_gib": 16}, {})
    except asu.ArcLinkASUError:
        pass
    else:
        raise AssertionError("absent disk field must fail closed")
    print("PASS test_c1_zero_probe_dimension_is_invalid_not_zero_capacity")


def test_c1_partial_probe_preserves_prior_capacity_and_schedulability() -> None:
    control = load_module("arclink_control.py", "arclink_control_c1_preserve")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_c1_preserve")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_c1_preserve")
    worker = load_module("arclink_fleet_inventory_worker.py", "arclink_worker_c1_preserve")
    conn = memory_db(control)
    host, machine = _seed_linked_machine(control, fleet, inventory, conn, asu_capacity=8.0)

    # A capacity probe with a zero disk dimension (partial) must NOT overwrite the
    # prior good capacity with 0, and must keep the machine schedulable.
    refreshed = worker.record_host_probe(
        conn,
        host={**host, "machine_id": machine["machine_id"]},
        kind="capacity",
        result=worker.ProbeResult(
            ok=True,
            payload={"hardware_summary": {"vcpu_cores": 8, "ram_gib": 16, "disk_gib": 0}, "observed_load": 0},
        ),
        notify=False,
    )
    machine_row = conn.execute(
        "SELECT status, asu_capacity, connectivity_summary_json FROM arclink_inventory_machines WHERE machine_id = ?",
        (machine["machine_id"],),
    ).fetchone()
    expect(float(machine_row["asu_capacity"]) == 8.0, f"prior capacity must be preserved: {dict(machine_row)}")
    expect(machine_row["status"] == "ready", f"healthy machine must stay schedulable: {dict(machine_row)}")
    import json

    summary = json.loads(machine_row["connectivity_summary_json"])
    expect(summary.get("partial_probe") is True, str(summary))
    expect(str(refreshed["status"]) == "active", str(refreshed))
    print("PASS test_c1_partial_probe_preserves_prior_capacity_and_schedulability")


def test_c2_overcommit_clamps_available_and_flags() -> None:
    control = load_module("arclink_control.py", "arclink_control_c2_overcommit")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_c2_overcommit")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_c2_overcommit")
    conn = memory_db(control)
    host, machine = _seed_linked_machine(control, fleet, inventory, conn, asu_capacity=1.0)

    # Force consumed (active placement COUNT) above the standard-unit capacity.
    import time

    for idx in range(3):
        conn.execute(
            "INSERT INTO arclink_deployment_placements (placement_id, deployment_id, host_id, status, placed_at) VALUES (?, ?, ?, 'active', ?)",
            (f"plc_{idx}", f"dep_{idx}", host["host_id"], "2026-01-01T00:00:00+00:00"),
        )
    conn.commit()
    del time

    rows = fleet.list_fleet_hosts(conn)
    target = next(h for h in rows if h["host_id"] == host["host_id"])
    expect(float(target["asu_consumed"]) == 3.0, str(target))
    expect(float(target["asu_capacity"]) == 1.0, str(target))
    # available must clamp at >= 0 (never negative phantom capacity).
    expect(float(target["asu_available"]) == 0.0, f"available must clamp at 0: {target}")
    expect(bool(target["asu_overcommitted"]) is True, f"overcommit must be flagged: {target}")

    summary = fleet.fleet_capacity_summary(conn)
    host_summary = next(h for h in summary["hosts"] if h["host_id"] == host["host_id"])
    expect(host_summary["asu_available"] >= 0.0, str(host_summary))
    expect(host_summary["asu_overcommitted"] is True, str(host_summary))
    # An overcommitted host is not schedulable under standard_unit strategy.
    import os

    os.environ["ARCLINK_PLACEMENT_STRATEGY"] = "standard_unit"
    try:
        eligible = fleet.host_is_placement_eligible({**target, "last_health_state": "active"}, strategy="standard_unit")
    finally:
        os.environ.pop("ARCLINK_PLACEMENT_STRATEGY", None)
    expect(eligible is False, f"overcommitted host must not be schedulable: {target}")
    print("PASS test_c2_overcommit_clamps_available_and_flags")


def main() -> int:
    test_c1_zero_probe_dimension_is_invalid_not_zero_capacity()
    test_c1_partial_probe_preserves_prior_capacity_and_schedulability()
    test_c2_overcommit_clamps_available_and_flags()
    print("PASS all 3 ArcLink ASU capacity regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
