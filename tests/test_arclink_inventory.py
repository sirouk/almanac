#!/usr/bin/env python3
from __future__ import annotations

from arclink_test_helpers import expect, load_module, memory_db


def test_inventory_list_filters_are_scriptable() -> None:
    control = load_module("arclink_control.py", "arclink_control_inventory_filters")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_filters")
    conn = memory_db(control)

    iad = inventory.register_inventory_machine(
        conn,
        provider="manual",
        hostname="worker-iad.example.test",
        ssh_host="10.0.0.10",
        ssh_user="arclink",
        region="iad",
        status="ready",
        capacity_slots=4,
    )
    inventory.register_inventory_machine(
        conn,
        provider="manual",
        hostname="worker-sfo.example.test",
        ssh_host="10.0.0.20",
        ssh_user="arclink",
        region="sfo",
        status="pending",
        capacity_slots=4,
    )

    ready = inventory.list_inventory_machines(conn, filters=["status=ready"])
    expect([row["hostname"] for row in ready] == ["worker-iad.example.test"], str(ready))

    by_region = inventory.list_inventory_machines(conn, filters=["region=iad", f"host_id={iad['machine_host_link']}"])
    expect(len(by_region) == 1 and by_region[0]["machine_id"] == iad["machine_id"], str(by_region))

    fuzzy = inventory.list_inventory_machines(conn, filters=["sfo"])
    expect(len(fuzzy) == 1 and fuzzy[0]["region"] == "sfo", str(fuzzy))

    try:
        inventory.list_inventory_machines(conn, filters=["token=secret"])
    except inventory.ArcLinkInventoryError as exc:
        expect("unsupported inventory filter" in str(exc), str(exc))
    else:
        raise AssertionError("unsupported filters should fail closed")

    print("PASS test_inventory_list_filters_are_scriptable")


if __name__ == "__main__":
    test_inventory_list_filters_are_scriptable()
