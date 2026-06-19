#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sqlite3

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


def test_liveness_probe_activates_pending_enrollment_before_placement() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_inventory_worker_pending_enroll_test")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_fleet_inventory_worker_pending_enroll_test")
    worker = load_module("arclink_fleet_inventory_worker.py", "arclink_fleet_inventory_worker_pending_enroll_test")
    conn = memory_db(control)
    machine, host = _seed_machine(control, inventory, conn)
    metadata = json.loads(host["metadata_json"] or "{}")
    metadata["enrollment_pending_probe"] = True
    conn.execute(
        """
        UPDATE arclink_fleet_hosts
        SET status = 'degraded', drain = 1, last_health_state = 'awaiting_control_probe',
            metadata_json = ?
        WHERE host_id = ?
        """,
        (json.dumps(metadata, sort_keys=True), host["host_id"]),
    )
    conn.execute(
        "UPDATE arclink_inventory_machines SET status = 'pending' WHERE machine_id = ?",
        (machine["machine_id"],),
    )
    conn.commit()

    host_for_probe = _host(conn, host["host_id"])
    host_for_probe["machine_id"] = machine["machine_id"]
    worker.record_host_probe(
        conn,
        host=host_for_probe,
        kind="liveness",
        result=worker.ProbeResult(ok=True, payload={"ok": True}),
        now_iso="2026-05-16T12:00:00+00:00",
        notify=False,
    )
    activated = _host(conn, host["host_id"])
    activated_meta = json.loads(activated["metadata_json"] or "{}")
    expect(activated["status"] == "active" and int(activated["drain"]) == 0, str(activated))
    expect(activated["last_health_state"] == "active", str(activated))
    expect(activated_meta["enrollment_pending_probe"] is False, str(activated_meta))
    expect(str(activated_meta.get("placement_activated_at") or ""), str(activated_meta))
    machine_row = conn.execute(
        "SELECT status FROM arclink_inventory_machines WHERE machine_id = ?",
        (machine["machine_id"],),
    ).fetchone()
    expect(machine_row["status"] == "ready", str(dict(machine_row)))
    print("PASS test_liveness_probe_activates_pending_enrollment_before_placement")


def test_capacity_probe_caps_untrusted_worker_reported_slots() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_inventory_worker_capacity_cap_test")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_fleet_inventory_worker_capacity_cap_test")
    worker = load_module("arclink_fleet_inventory_worker.py", "arclink_fleet_inventory_worker_capacity_cap_test")
    conn = memory_db(control)
    _, host = _seed_machine(control, inventory, conn)

    worker.record_host_probe(
        conn,
        host=_host(conn, host["host_id"]),
        kind="capacity",
        result=worker.ProbeResult(
            ok=True,
            payload={"ok": True, "capacity_slots": 100_000, "observed_load": 0},
        ),
        now_iso="2026-05-16T12:00:00+00:00",
        notify=False,
    )
    capped = _host(conn, host["host_id"])
    expect(int(capped["capacity_slots"]) == 64, str(capped))
    print("PASS test_capacity_probe_caps_untrusted_worker_reported_slots")


def test_invalid_hardware_summary_does_not_abort_probe_pass() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_inventory_worker_invalid_hardware_test")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_fleet_inventory_worker_invalid_hardware_test")
    worker = load_module("arclink_fleet_inventory_worker.py", "arclink_fleet_inventory_worker_invalid_hardware_test")
    conn = memory_db(control)
    machine, host = _seed_machine(control, inventory, conn)

    def runner(host_row, kind):
        payload = {"ok": True, "kind": kind}
        if kind in {"capacity", "inventory"}:
            payload["hardware_summary"] = {"vcpu_cores": 0, "ram_gib": 16, "disk_gib": 100}
        return worker.ProbeResult(ok=True, payload=payload, latency_ms=7)

    result = worker.process_due_hosts(
        conn,
        runner=runner,
        now_iso="2026-05-16T12:00:00+00:00",
        force=True,
        notify=False,
    )
    expect(result["probe_count"] == 3, str(result))
    probe_count = conn.execute("SELECT COUNT(*) AS count FROM arclink_fleet_host_probes WHERE host_id = ?", (host["host_id"],)).fetchone()["count"]
    expect(probe_count == 3, f"expected all probes to be recorded, got {probe_count}")
    machine_row = conn.execute(
        "SELECT status, connectivity_summary_json FROM arclink_inventory_machines WHERE machine_id = ?",
        (machine["machine_id"],),
    ).fetchone()
    summary = json.loads(machine_row["connectivity_summary_json"])
    expect(machine_row["status"] == "degraded", str(dict(machine_row)))
    expect(summary["ok"] is False and "invalid hardware summary" in summary["error"], str(summary))
    print("PASS test_invalid_hardware_summary_does_not_abort_probe_pass")


def test_legacy_probe_schema_is_migrated_for_worker() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_inventory_worker_legacy_probe_test")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_fleet_inventory_worker_legacy_probe_test")
    worker = load_module("arclink_fleet_inventory_worker.py", "arclink_fleet_inventory_worker_legacy_probe_test")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE arclink_fleet_host_probes (
          probe_id TEXT PRIMARY KEY,
          host_id TEXT NOT NULL DEFAULT '',
          machine_id TEXT NOT NULL DEFAULT '',
          probe_kind TEXT NOT NULL,
          status TEXT NOT NULL,
          payload_json TEXT NOT NULL DEFAULT '{}',
          error TEXT NOT NULL DEFAULT '',
          probed_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO arclink_fleet_host_probes (
          probe_id, host_id, machine_id, probe_kind, status, payload_json, error, probed_at
        ) VALUES ('flprb_legacy', 'host_legacy', '', 'capacity', 'ok', '{}', '', '2026-05-16T11:00:00+00:00')
        """
    )
    control.ensure_schema(conn)
    columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(arclink_fleet_host_probes)").fetchall()}
    expect({"kind", "ok", "latency_ms"} <= columns, str(columns))
    legacy = conn.execute("SELECT kind, ok, latency_ms FROM arclink_fleet_host_probes WHERE probe_id = 'flprb_legacy'").fetchone()
    expect(dict(legacy) == {"kind": "capacity", "ok": 1, "latency_ms": 0}, str(dict(legacy)))
    _, host = _seed_machine(control, inventory, conn)

    def runner(host_row, kind):
        return worker.ProbeResult(ok=True, payload={"ok": True, "kind": kind, "observed_load": 0}, latency_ms=7)

    result = worker.process_due_hosts(
        conn,
        runner=runner,
        now_iso="2026-05-16T12:00:00+00:00",
        force=True,
        notify=False,
    )
    expect(result["probe_count"] == 3, str(result))
    probe_count = conn.execute("SELECT COUNT(*) AS count FROM arclink_fleet_host_probes WHERE host_id = ?", (host["host_id"],)).fetchone()["count"]
    expect(probe_count == 3, f"expected three migrated-schema probe rows, got {probe_count}")
    print("PASS test_legacy_probe_schema_is_migrated_for_worker")


def test_worker_uses_fleet_host_metadata_ssh_endpoint_without_inventory_machine() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_inventory_worker_metadata_ssh_test")
    worker = load_module("arclink_fleet_inventory_worker.py", "arclink_fleet_inventory_worker_metadata_ssh_test")
    conn = memory_db(control)
    conn.execute(
        """
        INSERT INTO arclink_fleet_hosts (
          host_id, hostname, region, tags_json, status, drain, capacity_slots,
          observed_load, metadata_json, created_at, updated_at
        ) VALUES (
          'host_local', 's1396', 'starter', '{}', 'active', 0, 8, 0,
          '{"ssh_host":"localhost","ssh_user":"arclink"}',
          '2026-05-16T12:00:00+00:00', '2026-05-16T12:00:00+00:00'
        )
        """
    )
    conn.commit()
    seen: list[tuple[str, str]] = []

    def runner(host_row, kind):
        seen.append((str(host_row.get("ssh_host") or ""), str(host_row.get("ssh_user") or "")))
        return worker.ProbeResult(ok=True, payload={"ok": True, "kind": kind, "observed_load": 0}, latency_ms=3)

    result = worker.process_due_hosts(
        conn,
        runner=runner,
        now_iso="2026-05-16T12:01:00+00:00",
        force=True,
        notify=False,
    )
    expect(result["probe_count"] == 3, str(result))
    expect(seen == [("localhost", "arclink"), ("localhost", "arclink"), ("localhost", "arclink")], str(seen))
    print("PASS test_worker_uses_fleet_host_metadata_ssh_endpoint_without_inventory_machine")


def test_worker_prefers_private_mesh_endpoint_over_legacy_inventory_ssh_host() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_inventory_worker_private_mesh_test")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_fleet_inventory_worker_private_mesh_test")
    worker = load_module("arclink_fleet_inventory_worker.py", "arclink_fleet_inventory_worker_private_mesh_test")
    conn = memory_db(control)
    machine, host = _seed_machine(control, inventory, conn)
    conn.execute(
        "UPDATE arclink_inventory_machines SET ssh_host = '203.0.113.10' WHERE machine_id = ?",
        (machine["machine_id"],),
    )
    conn.execute(
        "UPDATE arclink_fleet_hosts SET metadata_json = ? WHERE host_id = ?",
        (
            json.dumps(
                {
                    "control_network_mode": "remote",
                    "executor": "ssh",
                    "private_dns_name": "10.44.0.11",
                    "ssh_host": "203.0.113.10",
                    "ssh_user": "arclink",
                },
                sort_keys=True,
            ),
            host["host_id"],
        ),
    )
    conn.commit()
    seen: list[str] = []

    def runner(host_row, kind):
        seen.append(str(host_row.get("ssh_host") or ""))
        return worker.ProbeResult(ok=True, payload={"ok": True, "kind": kind, "observed_load": 0}, latency_ms=3)

    result = worker.process_due_hosts(
        conn,
        runner=runner,
        now_iso="2026-05-16T12:01:00+00:00",
        force=True,
        notify=False,
    )
    expect(result["probe_count"] == 3, str(result))
    expect(seen == ["10.44.0.11", "10.44.0.11", "10.44.0.11"], str(seen))
    print("PASS test_worker_prefers_private_mesh_endpoint_over_legacy_inventory_ssh_host")


def test_worker_uses_container_safe_probe_for_docker_local_starter() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_inventory_worker_docker_local_starter_test")
    worker = load_module("arclink_fleet_inventory_worker.py", "arclink_fleet_inventory_worker_docker_local_starter_test")
    conn = memory_db(control)
    conn.execute(
        """
        INSERT INTO arclink_fleet_hosts (
          host_id, hostname, region, tags_json, status, drain, capacity_slots,
          observed_load, metadata_json, created_at, updated_at
        ) VALUES (
          'host_local', 's1396', 'starter', '{}', 'active', 0, 8, 0,
          '{"executor":"local","ssh_host":"localhost","ssh_user":"arclink"}',
          '2026-05-16T12:00:00+00:00', '2026-05-16T12:00:00+00:00'
        )
        """
    )
    conn.commit()
    previous = os.environ.get("ARCLINK_DOCKER_MODE")
    os.environ["ARCLINK_DOCKER_MODE"] = "1"
    try:
        result = worker.process_due_hosts(
            conn,
            now_iso="2026-05-16T12:01:00+00:00",
            force=True,
            notify=False,
        )
    finally:
        if previous is None:
            os.environ.pop("ARCLINK_DOCKER_MODE", None)
        else:
            os.environ["ARCLINK_DOCKER_MODE"] = previous
    expect(result["probe_count"] == 3, str(result))
    probes = conn.execute("SELECT kind, ok, payload_json FROM arclink_fleet_host_probes ORDER BY kind").fetchall()
    expect({str(row["kind"]): int(row["ok"]) for row in probes} == {"capacity": 1, "inventory": 1, "liveness": 1}, [dict(row) for row in probes])
    expect(all('"probe_mode": "docker-local-starter"' in str(row["payload_json"]) for row in probes), [dict(row) for row in probes])
    host = conn.execute("SELECT status, capacity_slots FROM arclink_fleet_hosts WHERE host_id = 'host_local'").fetchone()
    expect(dict(host) == {"status": "active", "capacity_slots": 8}, str(dict(host)))
    print("PASS test_worker_uses_container_safe_probe_for_docker_local_starter")


def test_worker_uses_container_safe_probe_for_legacy_control_reserve() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_inventory_worker_legacy_control_reserve_test")
    worker = load_module("arclink_fleet_inventory_worker.py", "arclink_fleet_inventory_worker_legacy_control_reserve_test")
    conn = memory_db(control)
    conn.execute(
        """
        INSERT INTO arclink_fleet_hosts (
          host_id, hostname, region, tags_json, status, drain, capacity_slots,
          observed_load, metadata_json, created_at, updated_at
        ) VALUES (
          'host_local', 's1396', 'starter', '{}', 'active', 0, 2, 0,
          '{"executor":"ssh","control_network_mode":"local","control_plane_host":true,"ssh_host":"localhost","ssh_user":"arclink"}',
          '2026-05-16T12:00:00+00:00', '2026-05-16T12:00:00+00:00'
        )
        """
    )
    conn.commit()
    previous = os.environ.get("ARCLINK_DOCKER_MODE")
    os.environ["ARCLINK_DOCKER_MODE"] = "1"
    try:
        result = worker.process_due_hosts(
            conn,
            now_iso="2026-05-16T12:01:00+00:00",
            force=True,
            notify=False,
        )
    finally:
        if previous is None:
            os.environ.pop("ARCLINK_DOCKER_MODE", None)
        else:
            os.environ["ARCLINK_DOCKER_MODE"] = previous
    expect(result["probe_count"] == 3, str(result))
    probes = conn.execute("SELECT kind, ok, payload_json, error FROM arclink_fleet_host_probes ORDER BY kind").fetchall()
    expect(all(int(row["ok"] or 0) == 1 for row in probes), [dict(row) for row in probes])
    expect(all("Connection refused" not in str(row["error"]) for row in probes), [dict(row) for row in probes])
    expect(all('"probe_mode": "docker-local-starter"' in str(row["payload_json"]) for row in probes), [dict(row) for row in probes])
    host = conn.execute("SELECT status, last_health_state FROM arclink_fleet_hosts WHERE host_id = 'host_local'").fetchone()
    expect(dict(host) == {"status": "active", "last_health_state": "active"}, str(dict(host)))
    print("PASS test_worker_uses_container_safe_probe_for_legacy_control_reserve")


def test_liveness_thresholds_degrade_unreachable_and_recover() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_inventory_worker_threshold_test")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_fleet_inventory_worker_threshold_test")
    worker = load_module("arclink_fleet_inventory_worker.py", "arclink_fleet_inventory_worker_threshold_test")
    conn = memory_db(control)
    _, host = _seed_machine(control, inventory, conn)
    host_id = host["host_id"]
    notification_commits: list[bool] = []
    real_queue_notification = worker.queue_notification

    def spy_queue_notification(*args, **kwargs):
        notification_commits.append(bool(kwargs.get("commit", True)))
        return real_queue_notification(*args, **kwargs)

    worker.queue_notification = spy_queue_notification

    try:
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
    finally:
        worker.queue_notification = real_queue_notification
    recovered = _host(conn, host_id)
    expect(recovered["status"] == "active", str(recovered))
    expect(recovered["last_health_state"] == "active", str(recovered))
    expect(notification_commits and all(commit is False for commit in notification_commits), str(notification_commits))
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
    test_liveness_probe_activates_pending_enrollment_before_placement()
    test_capacity_probe_caps_untrusted_worker_reported_slots()
    test_invalid_hardware_summary_does_not_abort_probe_pass()
    test_legacy_probe_schema_is_migrated_for_worker()
    test_worker_uses_fleet_host_metadata_ssh_endpoint_without_inventory_machine()
    test_worker_prefers_private_mesh_endpoint_over_legacy_inventory_ssh_host()
    test_worker_uses_container_safe_probe_for_docker_local_starter()
    test_worker_uses_container_safe_probe_for_legacy_control_reserve()
    test_liveness_thresholds_degrade_unreachable_and_recover()
    test_probe_errors_are_redacted_and_retention_is_pruned()
