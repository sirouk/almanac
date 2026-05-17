#!/usr/bin/env python3
from __future__ import annotations

import json

from arclink_test_helpers import expect, load_module, memory_db


def _seed_machine(control, inventory, conn):
    machine = inventory.register_inventory_machine(
        conn,
        provider="manual",
        hostname="worker-1.example.test",
        ssh_host="127.0.0.1",
        ssh_user="arclink",
        region="iad",
        status="ready",
        capacity_slots=4,
    )
    host = conn.execute(
        "SELECT * FROM arclink_fleet_hosts WHERE host_id = ?",
        (machine["machine_host_link"],),
    ).fetchone()
    expect(host is not None, "expected linked fleet host")
    return dict(machine), dict(host)


def _host(conn, host_id: str) -> dict:
    return dict(conn.execute("SELECT * FROM arclink_fleet_hosts WHERE host_id = ?", (host_id,)).fetchone())


def test_due_worker_records_probe_rows_and_updates_capacity() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_inventory_worker_due_test")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_fleet_inventory_worker_due_test")
    worker = load_module("arclink_fleet_inventory_worker.py", "arclink_fleet_inventory_worker_due_test")
    conn = memory_db(control)
    machine, host = _seed_machine(control, inventory, conn)

    def runner(host_row, kind):
        payload = {"ok": True, "kind": kind, "observed_load": 0}
        if kind in {"capacity", "inventory"}:
            payload["hardware_summary"] = {"vcpu_cores": 8, "ram_gib": 16, "disk_gib": 100}
        if kind == "inventory":
            payload["machine_fingerprint"] = "sha256:worker-fingerprint-abcdef1234567890"
        return worker.ProbeResult(ok=True, payload=payload, latency_ms=12)

    result = worker.process_due_hosts(
        conn,
        runner=runner,
        now_iso="2026-05-16T12:00:00+00:00",
        notify=False,
    )
    expect(result["probe_count"] == 3, str(result))
    probe_count = conn.execute("SELECT COUNT(*) AS count FROM arclink_fleet_host_probes").fetchone()["count"]
    expect(probe_count == 3, f"expected three probe rows, got {probe_count}")
    refreshed_host = _host(conn, host["host_id"])
    expect(refreshed_host["status"] == "active", str(refreshed_host))
    expect(refreshed_host["last_health_state"] == "active", str(refreshed_host))
    expect(int(refreshed_host["capacity_slots"]) == 8, str(refreshed_host))
    refreshed_machine = conn.execute(
        "SELECT status, machine_fingerprint, hardware_summary_json FROM arclink_inventory_machines WHERE machine_id = ?",
        (machine["machine_id"],),
    ).fetchone()
    expect(refreshed_machine["status"] == "ready", str(dict(refreshed_machine)))
    expect(refreshed_machine["machine_fingerprint"].startswith("sha256:"), str(dict(refreshed_machine)))
    expect(json.loads(refreshed_machine["hardware_summary_json"])["vcpu_cores"] == 8, refreshed_machine["hardware_summary_json"])

    skipped = worker.process_due_hosts(
        conn,
        runner=runner,
        now_iso="2026-05-16T12:00:30+00:00",
        notify=False,
    )
    expect(skipped["probe_count"] == 0, str(skipped))
    health = inventory.fleet_inventory_health(conn)
    expect(health["hosts"]["health_states"]["active"] == 1, str(health))
    expect(health["probes"]["total"] == 3 and health["probes"]["ok"] == 3, str(health))
    print("PASS test_due_worker_records_probe_rows_and_updates_capacity")


def test_liveness_thresholds_degrade_unreachable_and_recover() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_inventory_worker_threshold_test")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_fleet_inventory_worker_threshold_test")
    worker = load_module("arclink_fleet_inventory_worker.py", "arclink_fleet_inventory_worker_threshold_test")
    conn = memory_db(control)
    _, host = _seed_machine(control, inventory, conn)
    host_id = host["host_id"]

    for index in range(1, 4):
        worker.record_host_probe(
            conn,
            host=_host(conn, host_id),
            kind="liveness",
            result=worker.ProbeResult(ok=False, error="ssh timeout"),
            now_iso=f"2026-05-16T12:00:{index:02d}+00:00",
            notify=True,
        )
    degraded = _host(conn, host_id)
    expect(degraded["status"] == "degraded", str(degraded))
    expect(degraded["last_health_state"] == "degraded", str(degraded))

    for index in range(4, 11):
        worker.record_host_probe(
            conn,
            host=_host(conn, host_id),
            kind="liveness",
            result=worker.ProbeResult(ok=False, error="ssh timeout"),
            now_iso=f"2026-05-16T12:00:{index:02d}+00:00",
            notify=True,
        )
    unreachable = _host(conn, host_id)
    expect(unreachable["status"] == "offline", str(unreachable))
    expect(unreachable["last_health_state"] == "unreachable", str(unreachable))

    worker.record_host_probe(
        conn,
        host=_host(conn, host_id),
        kind="liveness",
        result=worker.ProbeResult(ok=True, payload={"ok": True}),
        now_iso="2026-05-16T12:01:00+00:00",
        notify=True,
    )
    recovered = _host(conn, host_id)
    expect(recovered["status"] == "active", str(recovered))
    expect(recovered["last_health_state"] == "active", str(recovered))
    messages = [
        str(row["message"])
        for row in conn.execute("SELECT message FROM notification_outbox WHERE target_kind = 'operator' ORDER BY id").fetchall()
    ]
    expect(any("degraded" in message for message in messages), str(messages))
    expect(any("unreachable" in message for message in messages), str(messages))
    expect(any("recovered" in message for message in messages), str(messages))
    print("PASS test_liveness_thresholds_degrade_unreachable_and_recover")


def test_probe_errors_are_redacted_and_retention_is_pruned() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_inventory_worker_redact_test")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_fleet_inventory_worker_redact_test")
    worker = load_module("arclink_fleet_inventory_worker.py", "arclink_fleet_inventory_worker_redact_test")
    conn = memory_db(control)
    _, host = _seed_machine(control, inventory, conn)
    host_id = host["host_id"]

    for index in range(5):
        worker.record_host_probe(
            conn,
            host=_host(conn, host_id),
            kind="capacity",
            result=worker.ProbeResult(
                ok=False,
                payload={"diagnostic": "api_key=verysecretvalue1234567890"},
                error="api_key=verysecretvalue1234567890",
            ),
            now_iso=f"2026-05-16T12:02:{index:02d}+00:00",
            notify=False,
        )
    row = conn.execute(
        "SELECT payload_json, error FROM arclink_fleet_host_probes WHERE kind = 'capacity' ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    rendered = json.dumps(dict(row), sort_keys=True)
    expect("verysecretvalue" not in rendered, rendered)
    expect("[REDACTED]" in rendered, rendered)

    pruned = worker.prune_host_probes(conn, retention_per_host_kind=2)
    remaining = conn.execute("SELECT COUNT(*) AS count FROM arclink_fleet_host_probes WHERE kind = 'capacity'").fetchone()["count"]
    expect(pruned == 3, f"expected three pruned rows, got {pruned}")
    expect(remaining == 2, f"expected two retained rows, got {remaining}")
    print("PASS test_probe_errors_are_redacted_and_retention_is_pruned")


if __name__ == "__main__":
    test_due_worker_records_probe_rows_and_updates_capacity()
    test_liveness_thresholds_degrade_unreachable_and_recover()
    test_probe_errors_are_redacted_and_retention_is_pruned()
