#!/usr/bin/env python3
"""Regression tests for fleet inventory worker H5 (metadata patch) and H7 (txn)."""
from __future__ import annotations

import json
import sqlite3

from arclink_test_helpers import expect, load_module, memory_db


def _seed(control, inventory, conn):
    machine = inventory.register_inventory_machine(
        conn,
        provider="manual",
        hostname="txn-worker.example.test",
        ssh_host="127.0.0.1",
        ssh_user="arclink",
        status="ready",
        capacity_slots=4,
    )
    host = dict(conn.execute("SELECT * FROM arclink_fleet_hosts WHERE host_id = ?", (machine["machine_host_link"],)).fetchone())
    return dict(machine), host


def test_h5_liveness_activation_preserves_image_sync_gate_keys() -> None:
    control = load_module("arclink_control.py", "arclink_control_h5_meta")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_h5_meta")
    worker = load_module("arclink_fleet_inventory_worker.py", "arclink_worker_h5_meta")
    conn = memory_db(control)
    machine, host = _seed(control, inventory, conn)

    # Pending enrollment + an image_sync_* gate key whose value would be mangled
    # by a redacting/truncating serializer (long value + a "secretish" sibling).
    gate_meta = {
        "enrollment_pending_probe": True,
        "image_sync_state": "ok",
        "image_sync_digest": "sha256:" + ("a" * 200),
        "image_sync_token": "this-should-not-be-redacted-away-by-metadata-write",
    }
    conn.execute(
        "UPDATE arclink_fleet_hosts SET metadata_json = ? WHERE host_id = ?",
        (json.dumps(gate_meta), host["host_id"]),
    )
    conn.commit()

    worker.record_host_probe(
        conn,
        host={**host, "machine_id": machine["machine_id"]},
        kind="liveness",
        result=worker.ProbeResult(ok=True, payload={"ok": True}),
        notify=False,
    )

    refreshed = dict(conn.execute("SELECT metadata_json FROM arclink_fleet_hosts WHERE host_id = ?", (host["host_id"],)).fetchone())
    meta = json.loads(refreshed["metadata_json"])
    # The keys we own are patched.
    expect(meta["enrollment_pending_probe"] is False, str(meta))
    expect("placement_activated_at" in meta, str(meta))
    # The image_sync_* gate keys survive verbatim -- NOT truncated, NOT redacted.
    expect(meta["image_sync_state"] == "ok", str(meta))
    expect(meta["image_sync_digest"] == "sha256:" + ("a" * 200), str(meta))
    expect(meta["image_sync_token"] == "this-should-not-be-redacted-away-by-metadata-write", str(meta))
    print("PASS test_h5_liveness_activation_preserves_image_sync_gate_keys")


def test_h7_record_host_probe_uses_immediate_txn_and_rereads() -> None:
    control = load_module("arclink_control.py", "arclink_control_h7_txn")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_h7_txn")
    worker = load_module("arclink_fleet_inventory_worker.py", "arclink_worker_h7_txn")
    conn = memory_db(control)
    machine, host = _seed(control, inventory, conn)

    # Mutate the live host AFTER capturing the (now-stale) caller snapshot. The
    # transition must be computed from the freshly-locked row, not the snapshot.
    stale_host = {**host, "status": "offline", "last_health_state": "unreachable", "machine_id": machine["machine_id"]}
    conn.execute("UPDATE arclink_fleet_hosts SET status = 'active', last_health_state = 'degraded' WHERE host_id = ?", (host["host_id"],))
    conn.commit()

    refreshed = worker.record_host_probe(
        conn,
        host=stale_host,
        kind="liveness",
        result=worker.ProbeResult(ok=True, payload={"ok": True}),
        notify=False,
    )
    expect(str(refreshed["status"]) == "active", str(refreshed))
    expect(not conn.in_transaction, "record_host_probe must commit its own BEGIN IMMEDIATE txn")
    print("PASS test_h7_record_host_probe_uses_immediate_txn_and_rereads")


def test_h7_bad_host_does_not_abort_pass_and_prune_still_runs() -> None:
    control = load_module("arclink_control.py", "arclink_control_h7_continue")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_h7_continue")
    worker = load_module("arclink_fleet_inventory_worker.py", "arclink_worker_h7_continue")
    conn = memory_db(control)
    _seed(control, inventory, conn)

    calls = {"prune": 0}
    original_prune = worker.prune_host_probes

    def counting_prune(c, **kwargs):
        calls["prune"] += 1
        return original_prune(c, **kwargs)

    original_apply = worker._apply_liveness_state
    seen = {"count": 0}

    def flaky_apply(c, *, host, result, notify):
        seen["count"] += 1
        if seen["count"] == 1:
            raise RuntimeError("simulated bad row")
        return original_apply(c, host=host, result=result, notify=notify)

    worker.prune_host_probes = counting_prune
    worker._apply_liveness_state = flaky_apply
    try:
        out = worker.process_due_hosts(conn, force=True, notify=False)
    finally:
        worker.prune_host_probes = original_prune
        worker._apply_liveness_state = original_apply

    # The bad liveness row is logged-and-continued; the pass still completes and
    # prune always runs (it lives in a finally).
    expect(out.get("error_count", 0) >= 1, str(out))
    expect(calls["prune"] == 1, f"prune must run exactly once even after a bad row: {calls}")
    # The pass did not raise out (it returned a result dict despite the bad row).
    expect(isinstance(out, dict) and "probe_count" in out, str(out))
    print("PASS test_h7_bad_host_does_not_abort_pass_and_prune_still_runs")


def main() -> int:
    test_h5_liveness_activation_preserves_image_sync_gate_keys()
    test_h7_record_host_probe_uses_immediate_txn_and_rereads()
    test_h7_bad_host_does_not_abort_pass_and_prune_still_runs()
    print("PASS all 3 ArcLink fleet inventory worker txn regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
