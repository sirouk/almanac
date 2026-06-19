#!/usr/bin/env python3
"""Regression tests for fleet inventory worker concurrency / data-integrity bugs.

Covers:
  H5  -- a capacity/inventory probe must NOT clobber observed_load (the live
         placement counter owned by place_deployment); a committed placement
         increment must survive a concurrent probe-apply.
  H5b -- liveness metadata patch preserves image_sync_* gate keys verbatim.
  H6  -- a machine removed after the caller's bulk snapshot is NOT resurrected to
         status='ready' by a stale-snapshot probe-apply.
  H7  -- record_host_probe runs under BEGIN IMMEDIATE and re-reads inside the lock.
  regr-M7 -- process_due_hosts refuses a connection with an already-open txn.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import threading

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


def _host_load(conn, host_id: str) -> int:
    return int(conn.execute("SELECT observed_load FROM arclink_fleet_hosts WHERE host_id = ?", (host_id,)).fetchone()["observed_load"])


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


def test_h5_capacity_probe_does_not_clobber_observed_load() -> None:
    control = load_module("arclink_control.py", "arclink_control_h5_load")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_h5_load")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_h5_load")
    worker = load_module("arclink_fleet_inventory_worker.py", "arclink_worker_h5_load")
    conn = memory_db(control)
    machine, host = _seed(control, inventory, conn)

    # Two real placements bump observed_load -> 2 via the atomic counter.
    fleet.place_deployment(conn, deployment_id="dep_h5_a")
    fleet.place_deployment(conn, deployment_id="dep_h5_b")
    expect(int(_host_load(conn, host["host_id"])) == 2, "two placements must increment observed_load to 2")

    # A capacity probe whose latency-stale payload reports an ABSOLUTE observed_load
    # of 1 (the view from ~20s ago, when only one placement existed). The old code
    # wrote that absolute value, erasing the second committed increment -> the host
    # looks emptier than it is -> over-placement past capacity. The fix must IGNORE
    # the payload's observed_load entirely and leave the live counter at 2.
    worker.record_host_probe(
        conn,
        host={**host, "machine_id": machine["machine_id"]},
        kind="capacity",
        result=worker.ProbeResult(
            ok=True,
            payload={"ok": True, "kind": "capacity", "observed_load": 1, "capacity_slots": 8},
        ),
        notify=False,
    )
    after = dict(conn.execute("SELECT observed_load, capacity_slots FROM arclink_fleet_hosts WHERE host_id = ?", (host["host_id"],)).fetchone())
    # observed_load is untouched by the probe (still 2); only capacity_slots moves.
    expect(int(after["observed_load"]) == 2, f"probe must not clobber observed_load: {after}")
    expect(int(after["capacity_slots"]) == 8, f"probe should still refresh capacity_slots: {after}")
    print("PASS test_h5_capacity_probe_does_not_clobber_observed_load")


def test_h5_concurrent_placement_survives_probe_apply() -> None:
    """A placement increment committed concurrently with a probe-apply survives."""
    control = load_module("arclink_control.py", "arclink_control_h5_race")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_h5_race")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_h5_race")
    worker = load_module("arclink_fleet_inventory_worker.py", "arclink_worker_h5_race")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = f"{tmpdir}/control.sqlite3"
        seed = sqlite3.connect(db_path, timeout=15)
        seed.row_factory = sqlite3.Row
        control.ensure_schema(seed)
        machine, host = _seed(control, inventory, seed)
        seed.commit()
        seed.close()

        barrier = threading.Barrier(2)
        errors: list[str] = []
        lock = threading.Lock()

        def do_place() -> None:
            c = sqlite3.connect(db_path, timeout=15)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA busy_timeout = 15000")
            try:
                barrier.wait(timeout=5)
                fleet.place_deployment(c, deployment_id="dep_race")
            except Exception as exc:  # noqa: BLE001
                with lock:
                    errors.append(f"place: {exc}")
            finally:
                c.close()

        def do_probe() -> None:
            c = sqlite3.connect(db_path, timeout=15)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA busy_timeout = 15000")
            try:
                barrier.wait(timeout=5)
                # Report a deliberately WRONG absolute observed_load (99). The fix
                # ignores it entirely, so the final live counter must equal the true
                # active placement count regardless of how the two serialize.
                worker.record_host_probe(
                    c,
                    host={**host, "machine_id": machine["machine_id"]},
                    kind="capacity",
                    result=worker.ProbeResult(ok=True, payload={"ok": True, "kind": "capacity", "observed_load": 99, "capacity_slots": 8}),
                    notify=False,
                )
            except Exception as exc:  # noqa: BLE001
                with lock:
                    errors.append(f"probe: {exc}")
            finally:
                c.close()

        threads = [threading.Thread(target=do_place), threading.Thread(target=do_probe)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        expect(errors == [], f"concurrent place/probe errors: {errors}")

        check = sqlite3.connect(db_path)
        check.row_factory = sqlite3.Row
        load = int(check.execute("SELECT observed_load FROM arclink_fleet_hosts WHERE host_id = ?", (host["host_id"],)).fetchone()["observed_load"])
        active = int(check.execute("SELECT COUNT(*) AS c FROM arclink_deployment_placements WHERE status = 'active'").fetchone()["c"])
        check.close()
        # Whichever order the two serialized, observed_load must equal the active
        # placement count (1) -- the probe must never have erased the increment.
        expect(active == 1, f"expected one active placement, got {active}")
        expect(load == 1, f"placement increment must survive concurrent probe-apply, got observed_load={load}")
    print("PASS test_h5_concurrent_placement_survives_probe_apply")


def test_h6_removed_machine_is_not_resurrected_by_probe() -> None:
    control = load_module("arclink_control.py", "arclink_control_h6_removed")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_h6_removed")
    worker = load_module("arclink_fleet_inventory_worker.py", "arclink_worker_h6_removed")
    conn = memory_db(control)
    machine, host = _seed(control, inventory, conn)

    # The caller captured a snapshot while the machine was 'ready'. The machine is
    # then removed (e.g. operator deprovision) AFTER the snapshot. A probe applied
    # to the stale snapshot must not write status='ready' back onto it.
    stale_host = {**host, "machine_id": machine["machine_id"]}
    conn.execute("UPDATE arclink_inventory_machines SET status = 'removed' WHERE machine_id = ?", (machine["machine_id"],))
    conn.commit()

    # capacity probe (full hardware -> success path that would normally set ready)
    worker.record_host_probe(
        conn,
        host=stale_host,
        kind="capacity",
        result=worker.ProbeResult(
            ok=True,
            payload={"ok": True, "kind": "capacity", "capacity_slots": 8, "hardware_summary": {"vcpu_cores": 8, "ram_gib": 16, "disk_gib": 100}},
        ),
        notify=False,
    )
    # liveness probe (also a status='ready' writer)
    worker.record_host_probe(
        conn,
        host=stale_host,
        kind="liveness",
        result=worker.ProbeResult(ok=True, payload={"ok": True}),
        notify=False,
    )
    status = str(conn.execute("SELECT status FROM arclink_inventory_machines WHERE machine_id = ?", (machine["machine_id"],)).fetchone()["status"])
    expect(status == "removed", f"removed machine must NOT be resurrected to ready, got {status!r}")
    print("PASS test_h6_removed_machine_is_not_resurrected_by_probe")


def test_regr_m7_process_due_hosts_rejects_open_txn() -> None:
    control = load_module("arclink_control.py", "arclink_control_m7_opentxn")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_m7_opentxn")
    worker = load_module("arclink_fleet_inventory_worker.py", "arclink_worker_m7_opentxn")
    conn = memory_db(control)
    _seed(control, inventory, conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        worker.process_due_hosts(conn, force=True, notify=False)
        raise AssertionError("process_due_hosts must reject an already-open transaction")
    except worker.ArcLinkFleetInventoryWorkerError as exc:
        expect("open transaction" in str(exc), str(exc))
    finally:
        if conn.in_transaction:
            conn.rollback()
    print("PASS test_regr_m7_process_due_hosts_rejects_open_txn")


def main() -> int:
    test_h5_liveness_activation_preserves_image_sync_gate_keys()
    test_h5_capacity_probe_does_not_clobber_observed_load()
    test_h5_concurrent_placement_survives_probe_apply()
    test_h6_removed_machine_is_not_resurrected_by_probe()
    test_h7_record_host_probe_uses_immediate_txn_and_rereads()
    test_h7_bad_host_does_not_abort_pass_and_prune_still_runs()
    test_regr_m7_process_due_hosts_rejects_open_txn()
    print("PASS all 7 ArcLink fleet inventory worker txn regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
