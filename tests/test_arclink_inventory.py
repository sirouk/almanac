#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess

from arclink_test_helpers import expect, load_module, memory_db


class _FakeCloudClient:
    def __init__(self, provider: str) -> None:
        self.provider = provider
        self.created = 0
        self.removed: list[tuple[str, bool]] = []

    def provision_server(self, **kwargs):
        self.created += 1
        hostname = str(kwargs.get("name") or kwargs.get("label") or "")
        region = str(kwargs.get("location") or kwargs.get("region") or "")
        prefix = "h" if self.provider == "hetzner" else "l"
        return {
            "provider": self.provider,
            "provider_resource_id": f"{prefix}-{self.created}",
            "hostname": hostname,
            "ssh_host": "203.0.113.30",
            "region": region,
            "status": "running",
            "hardware_summary": {"vcpu_cores": 4, "ram_gib": 8, "disk_gib": 80},
        }

    def remove_server(self, server_id, *, destroy=False):
        self.removed.append((server_id, bool(destroy)))
        return {"id": server_id, "destroy": bool(destroy)}


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


def test_inventory_list_includes_live_fleet_hosts() -> None:
    control = load_module("arclink_control.py", "arclink_control_inventory_fleet_hosts")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_fleet_hosts")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_inventory_fleet_hosts")
    conn = memory_db(control)

    host = fleet.register_fleet_host(
        conn,
        hostname="fleet-live.example.test",
        region="iad",
        capacity_slots=8,
        metadata={"control_network_mode": "remote"},
    )
    fleet.update_fleet_host(conn, host_id=host["host_id"], observed_load=2)

    hosts = inventory.list_fleet_inventory_hosts(conn)
    expect(len(hosts) == 1, str(hosts))
    expect(hosts[0]["hostname"] == "fleet-live.example.test", str(hosts))
    expect(hosts[0]["headroom"] == 6, str(hosts))

    by_provider = inventory.list_fleet_inventory_hosts(conn, filters=["provider=fleet"])
    expect(len(by_provider) == 1, str(by_provider))
    by_region = inventory.list_fleet_inventory_hosts(conn, filters=["region=iad"])
    expect(len(by_region) == 1, str(by_region))
    hidden = inventory.list_fleet_inventory_hosts(conn, filters=["provider=manual"])
    expect(hidden == [], str(hidden))

    print("PASS test_inventory_list_includes_live_fleet_hosts")


def test_inventory_registration_rejects_unsafe_host_identity_values() -> None:
    control = load_module("arclink_control.py", "arclink_control_inventory_hardening")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_hardening")
    conn = memory_db(control)
    cases = [
        {"hostname": "worker\nbad.example.test"},
        {"hostname": "worker-safe.example.test", "ssh_host": "https://worker-safe.example.test"},
        {"hostname": "worker-safe.example.test", "ssh_user": "root;id"},
        {"hostname": "worker-safe.example.test", "region": "iad\nx"},
    ]
    for idx, override in enumerate(cases):
        payload = {
            "provider": "manual",
            "hostname": f"worker-hardening-{idx}.example.test",
            "ssh_host": "10.0.0.10",
            "ssh_user": "arclink",
            "region": "iad",
            "status": "ready",
            "capacity_slots": 4,
        }
        payload.update(override)
        try:
            inventory.register_inventory_machine(conn, **payload)
        except inventory.ArcLinkInventoryError:
            pass
        else:
            raise AssertionError(f"unsafe inventory payload should fail: {payload}")
    rows = conn.execute("SELECT COUNT(*) AS count FROM arclink_inventory_machines").fetchone()
    expect(rows["count"] == 0, f"unsafe inventory rows were inserted: {dict(rows)}")
    print("PASS test_inventory_registration_rejects_unsafe_host_identity_values")


def test_inventory_registration_secret_rejection_does_not_commit_fleet_host() -> None:
    control = load_module("arclink_control.py", "arclink_control_inventory_atomic_register")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_atomic_register")
    conn = memory_db(control)

    try:
        inventory.register_inventory_machine(
            conn,
            provider="manual",
            hostname="worker-secret.example.test",
            ssh_host="10.0.0.10",
            ssh_user="arclink",
            region="iad",
            status="pending",
            capacity_slots=4,
            metadata={"note": "AKIAIOSFODNN7EXAMPLE"},
        )
    except inventory.ArcLinkInventoryError:
        pass
    else:
        raise AssertionError("secret-shaped metadata should fail closed")

    machines = conn.execute("SELECT COUNT(*) AS count FROM arclink_inventory_machines").fetchone()
    hosts = conn.execute("SELECT COUNT(*) AS count FROM arclink_fleet_hosts").fetchone()
    expect(machines["count"] == 0, str(dict(machines)))
    expect(hosts["count"] == 0, str(dict(hosts)))
    print("PASS test_inventory_registration_secret_rejection_does_not_commit_fleet_host")


def test_parse_probe_output_reads_real_df_device_rows() -> None:
    inventory = load_module("arclink_inventory.py", "arclink_inventory_parse_probe")
    stdout = """4
MemTotal:       16384000 kB
MemFree:         1024000 kB
MemAvailable:    2048000 kB
Filesystem     1G-blocks  Used Available Use% Mounted on
/dev/sda1            160G   20G      140G  13% /
overlay              200G   50G      150G  25% /var/lib/docker
Docker version 27.0.0, build test
Docker Compose version v2.27.0
"""
    parsed = inventory.parse_probe_output(stdout)
    expect(parsed["vcpu_cores"] == 4, str(parsed))
    expect(parsed["disk_gib"] == 200, str(parsed))
    expect(parsed["docker_version"].startswith("Docker version"), str(parsed))

    wrapped = """2
MemTotal:        8388608 kB
Filesystem     1G-blocks  Used Available Use% Mounted on
/dev/mapper/very-long-volume-name
                    160G   20G      140G  13% /
Docker version 27.0.0, build test
"""
    wrapped_parsed = inventory.parse_probe_output(wrapped)
    expect(wrapped_parsed["disk_gib"] == 160, str(wrapped_parsed))
    print("PASS test_parse_probe_output_reads_real_df_device_rows")


def test_probe_success_with_bad_parse_marks_machine_degraded() -> None:
    control = load_module("arclink_control.py", "arclink_control_inventory_probe_bad_parse")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_probe_bad_parse")
    conn = memory_db(control)
    machine = inventory.register_inventory_machine(
        conn,
        provider="manual",
        hostname="worker-bad-parse.example.test",
        ssh_host="10.0.0.10",
        ssh_user="arclink",
        status="ready",
        asu_capacity=4,
    )

    def runner(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, stdout="4\nDocker version 27.0.0\n", stderr="")

    try:
        inventory.probe_inventory_machine(conn, key=machine["machine_id"], runner=runner)
    except inventory.ArcLinkInventoryError as exc:
        expect("MemTotal" in str(exc), str(exc))
    else:
        raise AssertionError("bad successful probe output should fail closed")

    refreshed = inventory.get_inventory_machine(conn, machine["machine_id"])
    expect(refreshed["status"] == "degraded", str(refreshed))
    connectivity = json.loads(refreshed["connectivity_summary_json"])
    expect(connectivity["ok"] is False and "MemTotal" in connectivity["error"], str(connectivity))
    print("PASS test_probe_success_with_bad_parse_marks_machine_degraded")


def test_manual_probe_does_not_clobber_observed_load() -> None:
    # H5 (manual inventory path): probe_inventory_machine must NEVER absolute-write
    # observed_load. observed_load is the live placement counter owned exclusively by
    # place_deployment (atomic +1), remove_placement, and reconcile. The probe reads
    # current_load() OUTSIDE the write lock; writing it back races a placement
    # increment committed in between -> erases it -> over-placement past capacity.
    control = load_module("arclink_control.py", "arclink_control_inventory_probe_no_clobber")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_probe_no_clobber")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_inventory_probe_no_clobber")
    conn = memory_db(control)
    host = fleet.register_fleet_host(conn, hostname="worker-no-clobber.example.test", capacity_slots=4)
    machine = inventory.register_inventory_machine(
        conn,
        provider="manual",
        hostname="worker-no-clobber.example.test",
        ssh_host="10.0.0.10",
        ssh_user="arclink",
        status="ready",
        machine_host_link=host["host_id"],
    )
    stdout = """4
MemTotal:       16384000 kB
Filesystem     1G-blocks  Used Available Use% Mounted on
/dev/sda1            160G   20G      140G  13% /
Docker version 27.0.0, build test
"""

    def runner(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, stdout=stdout, stderr="")

    # Two real placements bump observed_load -> 2 via the atomic counter. The probe's
    # current_load() view is deliberately stale (reports 1, the world from ~20s ago).
    # The buggy code wrote that stale absolute back, erasing the second increment.
    fleet.place_deployment(conn, deployment_id="dep_no_clobber_a")
    fleet.place_deployment(conn, deployment_id="dep_no_clobber_b")
    expect(int(fleet.get_fleet_host(conn, host_id=host["host_id"])["observed_load"]) == 2, "two placements -> observed_load 2")

    original_current_load = inventory.current_load
    inventory.current_load = lambda machine_id, conn: 1.0
    try:
        inventory.probe_inventory_machine(conn, key=machine["machine_id"], runner=runner)
    finally:
        inventory.current_load = original_current_load

    refreshed_host = fleet.get_fleet_host(conn, host_id=host["host_id"])
    # observed_load is untouched by the probe (still 2, the true placement count) --
    # the host is still marked active and the machine refreshed to ready.
    expect(int(refreshed_host["observed_load"]) == 2, f"probe must not clobber observed_load: {refreshed_host}")
    expect(str(refreshed_host["status"]) == "active", str(refreshed_host))
    refreshed_machine = inventory.get_inventory_machine(conn, machine["machine_id"])
    expect(str(refreshed_machine["status"]) == "ready", str(refreshed_machine))
    print("PASS test_manual_probe_does_not_clobber_observed_load")


def test_manual_probe_survives_concurrent_placement_increment() -> None:
    # H5 concurrency proof: a placement increment committed concurrently with a
    # manual probe-apply survives -- the probe never erases it regardless of order.
    import sqlite3 as _sqlite3
    import tempfile
    import threading

    control = load_module("arclink_control.py", "arclink_control_manual_probe_race")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_manual_probe_race")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_manual_probe_race")

    stdout = """4
MemTotal:       16384000 kB
Filesystem     1G-blocks  Used Available Use% Mounted on
/dev/sda1            160G   20G      140G  13% /
Docker version 27.0.0, build test
"""

    def runner(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, stdout=stdout, stderr="")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = f"{tmpdir}/control.sqlite3"
        seed = _sqlite3.connect(db_path, timeout=15)
        seed.row_factory = _sqlite3.Row
        control.ensure_schema(seed)
        host = fleet.register_fleet_host(seed, hostname="worker-manual-race.example.test", capacity_slots=8)
        machine = inventory.register_inventory_machine(
            seed,
            provider="manual",
            hostname="worker-manual-race.example.test",
            ssh_host="10.0.0.10",
            ssh_user="arclink",
            status="ready",
            machine_host_link=host["host_id"],
        )
        seed.commit()
        host_id = host["host_id"]
        machine_id = machine["machine_id"]
        seed.close()

        barrier = threading.Barrier(2)
        errors: list[str] = []
        lock = threading.Lock()

        def do_place() -> None:
            c = _sqlite3.connect(db_path, timeout=15)
            c.row_factory = _sqlite3.Row
            c.execute("PRAGMA busy_timeout = 15000")
            try:
                barrier.wait(timeout=5)
                fleet.place_deployment(c, deployment_id="dep_manual_race")
            except Exception as exc:  # noqa: BLE001
                with lock:
                    errors.append(f"place: {exc}")
            finally:
                c.close()

        def do_probe() -> None:
            c = _sqlite3.connect(db_path, timeout=15)
            c.row_factory = _sqlite3.Row
            c.execute("PRAGMA busy_timeout = 15000")
            # current_load() reports a deliberately WRONG absolute (0). The fix
            # ignores it, so the live counter must equal the true active placement
            # count however the two threads serialize.
            original = inventory.current_load
            inventory.current_load = lambda mid, conn: 0.0
            try:
                barrier.wait(timeout=5)
                inventory.probe_inventory_machine(c, key=machine_id, runner=runner)
            except Exception as exc:  # noqa: BLE001
                with lock:
                    errors.append(f"probe: {exc}")
            finally:
                inventory.current_load = original
                c.close()

        threads = [threading.Thread(target=do_place), threading.Thread(target=do_probe)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        expect(errors == [], f"concurrent place/probe errors: {errors}")

        check = _sqlite3.connect(db_path)
        check.row_factory = _sqlite3.Row
        load = int(check.execute("SELECT observed_load FROM arclink_fleet_hosts WHERE host_id = ?", (host_id,)).fetchone()["observed_load"])
        active = int(check.execute("SELECT COUNT(*) AS c FROM arclink_deployment_placements WHERE status = 'active'").fetchone()["c"])
        check.close()
        expect(active == 1, f"expected one active placement, got {active}")
        expect(load == 1, f"placement increment must survive concurrent manual probe-apply, got observed_load={load}")
    print("PASS test_manual_probe_survives_concurrent_placement_increment")


def test_register_inventory_machine_preserves_image_sync_under_concurrent_gate_write() -> None:
    # H7 (manual inventory path): register_inventory_machine (commit=True default)
    # must open BEGIN IMMEDIATE around the host+machine read->merge->write unit BEFORE
    # calling register_fleet_host(commit=False). register_fleet_host(commit=False)
    # only DEFERS to the caller's lock -- so if the caller is unlocked, its existence
    # SELECT -> image_sync_* merge -> whole-metadata_json UPDATE runs in autocommit and
    # a NEW gate value committed by a concurrent writer BETWEEN that SELECT and UPDATE
    # is silently lost (the merge is recomputed from the stale pre-write row).
    #
    # We expose the lost-update window deterministically: interpose the host existence
    # SELECT inside register_fleet_host so that, the instant register reads the host
    # row, a SECOND connection commits a brand-new image_sync_state value. Under the
    # fix register holds BEGIN IMMEDIATE, so that second write BLOCKS until register
    # commits and lands AFTER (its value wins, unharmed). Without the lock the second
    # write commits immediately and register's stale-read UPDATE clobbers it.
    import sqlite3 as _sqlite3
    import tempfile

    control = load_module("arclink_control.py", "arclink_control_reg_gate_race")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_reg_gate_race")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_reg_gate_race")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = f"{tmpdir}/control.sqlite3"
        seed = _sqlite3.connect(db_path, timeout=15)
        seed.row_factory = _sqlite3.Row
        control.ensure_schema(seed)
        host = fleet.register_fleet_host(
            seed,
            hostname="worker-gate.example.test",
            capacity_slots=4,
            metadata={"image_sync_state": "stale", "image_sync_digest": "sha256:" + ("b" * 64)},
        )
        seed.commit()
        host_id = host["host_id"]
        seed.close()

        import threading
        import time as _time

        state = {"fired": False, "competed": False}
        writer_thread = {"t": None}

        # The competing writer commits the AUTHORITATIVE new gate value (image_sync
        # just succeeded). It runs on its own connection with a long busy_timeout so
        # that if register holds the write lock it cleanly serializes behind it; if
        # register does NOT hold the lock it commits immediately and is then clobbered.
        def competing_gate_write() -> None:
            c = _sqlite3.connect(db_path, timeout=15)
            c.row_factory = _sqlite3.Row
            c.execute("PRAGMA busy_timeout = 8000")
            try:
                import json as _json
                cur = c.execute("SELECT metadata_json FROM arclink_fleet_hosts WHERE host_id = ?", (host_id,)).fetchone()
                meta = _json.loads(cur["metadata_json"])
                meta["image_sync_state"] = "ok"
                # This UPDATE blocks until register's BEGIN IMMEDIATE commits (fix) or
                # commits immediately into the gap (bug).
                c.execute("UPDATE arclink_fleet_hosts SET metadata_json = ? WHERE host_id = ?", (_json.dumps(meta), host_id))
                c.commit()
                state["competed"] = True
            finally:
                c.close()

        # sqlite3.Connection.execute is read-only, so interpose via a Connection
        # subclass: the first time register reads arclink_fleet_hosts by hostname,
        # kick off the competing writer and give it a moment to attempt its write --
        # precisely the lost-update window between register's SELECT and UPDATE.
        class _InterposingConnection(_sqlite3.Connection):
            def execute(self, sql, *params):  # type: ignore[override]
                cursor = super().execute(sql, *params)
                if (
                    not state["fired"]
                    and isinstance(sql, str)
                    and "FROM arclink_fleet_hosts" in sql
                    and "LOWER(hostname)" in sql
                ):
                    state["fired"] = True
                    t = threading.Thread(target=competing_gate_write)
                    t.start()
                    writer_thread["t"] = t
                    _time.sleep(0.3)  # let the competing writer reach its UPDATE/commit
                return cursor

        reg = _sqlite3.connect(db_path, timeout=15, factory=_InterposingConnection)
        reg.row_factory = _sqlite3.Row
        try:
            inventory.register_inventory_machine(
                reg,
                provider="manual",
                hostname="worker-gate.example.test",
                ssh_host="10.0.0.10",
                ssh_user="arclink",
                status="pending",
                capacity_slots=4,
                metadata={"refreshed": True},  # does NOT set image_sync_* -> carryover path
            )
        finally:
            reg.close()
            if writer_thread["t"] is not None:
                writer_thread["t"].join(timeout=10)

        expect(state["fired"], "interposer never saw the host existence SELECT")
        expect(state["competed"], "competing gate writer never committed")

        check = _sqlite3.connect(db_path)
        check.row_factory = _sqlite3.Row
        meta = json.loads(check.execute("SELECT metadata_json FROM arclink_fleet_hosts WHERE host_id = ?", (host_id,)).fetchone()["metadata_json"])
        check.close()
        # Under the fix the competing writer was serialized AFTER register's locked
        # read-merge-write, so its authoritative new value ('ok') survives. The digest
        # gate key (set by neither writer's incoming metadata) is preserved by the
        # carryover throughout.
        expect(meta.get("image_sync_state") == "ok", f"concurrent gate write was lost (H7 lost-update): {meta}")
        expect(meta.get("image_sync_digest") == "sha256:" + ("b" * 64), f"image_sync_digest gate key dropped: {meta}")
    print("PASS test_register_inventory_machine_preserves_image_sync_under_concurrent_gate_write")


def test_cloud_inventory_lifecycle_contract_is_provider_parity() -> None:
    control = load_module("arclink_control.py", "arclink_control_inventory_lifecycle_parity")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_lifecycle_parity")

    for provider in ("hetzner", "linode"):
        conn = memory_db(control)
        client = _FakeCloudClient(provider)
        hostname = f"{provider}-worker.example.test"

        result = inventory.create_cloud_inventory_machine(
            conn,
            provider=provider,
            client=client,
            hostname=hostname,
            server_type="cx22" if provider == "hetzner" else "g6-standard-2",
            image="ubuntu-24.04" if provider == "hetzner" else "linode/ubuntu24.04",
            region="fsn1" if provider == "hetzner" else "us-east",
            ssh_keys=["fleet-key"],
            capacity_slots=4,
            tags={"provider_parity": provider},
            idempotency_key=f"{provider}-parity-create",
        )
        replay = inventory.create_cloud_inventory_machine(
            conn,
            provider=provider,
            client=client,
            hostname=hostname,
            server_type="cx22" if provider == "hetzner" else "g6-standard-2",
            image="ubuntu-24.04" if provider == "hetzner" else "linode/ubuntu24.04",
            region="fsn1" if provider == "hetzner" else "us-east",
            ssh_keys=["fleet-key"],
            capacity_slots=4,
            tags={"provider_parity": provider},
            idempotency_key=f"{provider}-parity-create",
        )
        duplicate = inventory.create_cloud_inventory_machine(
            conn,
            provider=provider,
            client=client,
            hostname=hostname,
            server_type="cx32" if provider == "hetzner" else "g6-standard-4",
            image="ubuntu-24.04" if provider == "hetzner" else "linode/ubuntu24.04",
            region="fsn1" if provider == "hetzner" else "us-east",
            idempotency_key=f"{provider}-parity-duplicate",
        )

        expect(client.created == 1, f"{provider} create was not idempotent: {client.created}")
        expect(replay["replay"] is True and replay["status"] == result["status"], str(replay))
        expect(duplicate["status"] == "existing", str(duplicate))
        machine = result["machine"]

        try:
            inventory.remove_cloud_inventory_machine(conn, key=machine["machine_id"], client=client, destroy=True)
        except inventory.ArcLinkInventoryError as exc:
            expect("drain" in str(exc), str(exc))
        else:
            raise AssertionError(f"{provider} removal must require drain or force")

        inventory.drain_inventory_machine(conn, machine["machine_id"])
        removed = inventory.remove_cloud_inventory_machine(
            conn,
            key=machine["machine_id"],
            client=client,
            destroy=True,
            idempotency_key=f"{provider}-parity-remove",
        )
        remove_replay = inventory.remove_cloud_inventory_machine(
            conn,
            key=machine["machine_id"],
            client=client,
            destroy=True,
            idempotency_key=f"{provider}-parity-remove",
        )

        expected_resource = "h-1" if provider == "hetzner" else "l-1"
        expect(client.removed == [(expected_resource, True)], str(client.removed))
        expect(removed["machine"]["status"] == "removed", str(removed))
        expect(remove_replay["replay"] is True, str(remove_replay))
        row = conn.execute(
            """
            SELECT result_json
            FROM arclink_operation_idempotency
            WHERE operation_kind = ? AND idempotency_key = ?
            """,
            (f"inventory_{provider}_create", f"{provider}-parity-create"),
        ).fetchone()
        expect(json.loads(row["result_json"])["status"] == result["status"], str(dict(row)))

    print("PASS test_cloud_inventory_lifecycle_contract_is_provider_parity")


def test_cloud_create_cleans_up_post_provision_registration_failure() -> None:
    control = load_module("arclink_control.py", "arclink_control_inventory_create_cleanup")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_create_cleanup")
    conn = memory_db(control)
    client = _FakeCloudClient("hetzner")

    kwargs = {
        "provider": "hetzner",
        "client": client,
        "hostname": "hetzner-secret.example.test",
        "server_type": "cx22",
        "image": "ubuntu-24.04",
        "region": "fsn1",
        "capacity_slots": 4,
        "tags": {"bad": "AKIAIOSFODNN7EXAMPLE"},
        "idempotency_key": "hetzner-cleanup-create",
    }
    try:
        inventory.create_cloud_inventory_machine(conn, **kwargs)
    except inventory.ArcLinkInventoryError:
        pass
    else:
        raise AssertionError("post-provision registration failure should be surfaced")

    expect(client.created == 1, str(client.created))
    expect(client.removed == [("h-1", True)], str(client.removed))
    machines = conn.execute("SELECT COUNT(*) AS count FROM arclink_inventory_machines").fetchone()
    hosts = conn.execute("SELECT COUNT(*) AS count FROM arclink_fleet_hosts").fetchone()
    expect(machines["count"] == 0, str(dict(machines)))
    expect(hosts["count"] == 0, str(dict(hosts)))
    row = conn.execute(
        """
        SELECT status, provider_refs_json, result_json
        FROM arclink_operation_idempotency
        WHERE operation_kind = 'inventory_hetzner_create' AND idempotency_key = 'hetzner-cleanup-create'
        """
    ).fetchone()
    result = json.loads(row["result_json"])
    expect(row["status"] == "failed", str(dict(row)))
    expect(json.loads(row["provider_refs_json"])["provider_resource_id"] == "h-1", str(dict(row)))
    expect(result["status"] == "failed" and result["cleanup"]["removed"] is True, str(result))

    try:
        inventory.create_cloud_inventory_machine(conn, **kwargs)
    except inventory.ArcLinkInventoryError as exc:
        expect("previous cloud inventory operation failed" in str(exc), str(exc))
    else:
        raise AssertionError("failed idempotency replay should not look like success")
    expect(client.created == 1, "failed replay should not provision another server")
    print("PASS test_cloud_create_cleans_up_post_provision_registration_failure")


if __name__ == "__main__":
    test_inventory_list_filters_are_scriptable()
    test_inventory_list_includes_live_fleet_hosts()
    test_inventory_registration_rejects_unsafe_host_identity_values()
    test_inventory_registration_secret_rejection_does_not_commit_fleet_host()
    test_parse_probe_output_reads_real_df_device_rows()
    test_probe_success_with_bad_parse_marks_machine_degraded()
    test_manual_probe_does_not_clobber_observed_load()
    test_manual_probe_survives_concurrent_placement_increment()
    test_register_inventory_machine_preserves_image_sync_under_concurrent_gate_write()
    test_cloud_inventory_lifecycle_contract_is_provider_parity()
    test_cloud_create_cleans_up_post_provision_registration_failure()
