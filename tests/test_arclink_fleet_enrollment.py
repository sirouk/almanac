#!/usr/bin/env python3
from __future__ import annotations

import json
import os

from arclink_test_helpers import expect, load_module, memory_db


SECRET = "test-fleet-enrollment-secret"
WORKER_WG_PUBLIC_KEY = "BcDeFgHiJkLmNoPqRsTuVwXyZ0123456789+/ABC="


def _attestation_payload(hostname: str = "worker-1.example.test") -> dict:
    return {
        "hostname": hostname,
        "ssh_host": hostname,
        "ssh_user": "arclink",
        "region": "iad",
        "capacity_slots": 6,
        "machine_fingerprint": "sha256:worker-fingerprint-1234567890abcdef",
        "hardware_summary": {"vcpu_cores": 8, "ram_gib": 16},
        "connectivity_summary": {"ok": True},
        "prereq_audit": {"docker": "present", "compose": "present"},
        "tags": {"tier": "sovereign"},
    }


def _consume_callback_and_machine_metadata(
    enrollment,
    hosted,
    conn,
    config,
    *,
    enrollment_id: str,
    hostname: str,
    headers: dict[str, str],
    remote_addr: str,
) -> dict:
    minted = enrollment.mint_fleet_enrollment(
        conn,
        created_by_user_id="operator-1",
        secret=SECRET,
        enrollment_id=enrollment_id,
    )
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/fleet/enrollment/callback",
        headers={"Authorization": f"Bearer {minted['token']}", **headers},
        body=json.dumps(_attestation_payload(hostname)),
        config=config,
        remote_addr=remote_addr,
    )
    expect(status == 201, f"{enrollment_id} expected callback 201 got {status}: {payload}")
    machine = conn.execute(
        "SELECT metadata_json FROM arclink_inventory_machines WHERE machine_id = ?",
        (payload["worker"]["machine_id"],),
    ).fetchone()
    return json.loads(machine["metadata_json"])


def test_mint_stores_only_hmac_hash_and_lists_without_token() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_enrollment_mint_test")
    enrollment = load_module("arclink_fleet_enrollment.py", "arclink_fleet_enrollment_mint_test")
    conn = memory_db(control)

    minted = enrollment.mint_fleet_enrollment(
        conn,
        created_by_user_id="operator-1",
        ttl_seconds=600,
        secret=SECRET,
        enrollment_id="flenr_testmint",
        now_iso="2026-05-15T12:00:00+00:00",
    )
    expect(minted["token"].startswith("arcfleet_v1.flenr_testmint."), str(minted))
    stored = conn.execute(
        "SELECT token_hash, status FROM arclink_fleet_enrollments WHERE enrollment_id = 'flenr_testmint'"
    ).fetchone()
    expect(str(stored["token_hash"]).startswith("hmac_sha256_v1$"), str(dict(stored)))
    expect(minted["token"] not in str(dict(stored)), "cleartext token leaked into enrollment row")

    listed = enrollment.list_fleet_enrollments(conn)
    expect(len(listed) == 1, str(listed))
    rendered = json.dumps(listed, sort_keys=True)
    expect("arcfleet_v1" not in rendered and "token_hash" not in rendered, rendered)
    print("PASS test_mint_stores_only_hmac_hash_and_lists_without_token")


def test_tokens_fail_closed_when_malformed_wrong_revoked_expired_or_reused() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_enrollment_fail_test")
    enrollment = load_module("arclink_fleet_enrollment.py", "arclink_fleet_enrollment_fail_test")
    conn = memory_db(control)

    minted = enrollment.mint_fleet_enrollment(
        conn,
        created_by_user_id="operator-1",
        ttl_seconds=600,
        secret=SECRET,
        enrollment_id="flenr_failstates",
    )
    for bad in ("", "not-a-token", minted["token"] + "x"):
        try:
            enrollment.consume_fleet_enrollment(conn, token=bad, payload=_attestation_payload(), secret=SECRET)
        except enrollment.ArcLinkFleetEnrollmentError:
            pass
        else:
            raise AssertionError(f"expected bad token {bad!r} to fail")

    revoked = enrollment.mint_fleet_enrollment(
        conn,
        created_by_user_id="operator-1",
        ttl_seconds=600,
        secret=SECRET,
        enrollment_id="flenr_revoked",
    )
    enrollment.revoke_fleet_enrollment(conn, enrollment_id="flenr_revoked", actor="operator-1")
    try:
        enrollment.consume_fleet_enrollment(conn, token=revoked["token"], payload=_attestation_payload("revoked.example.test"), secret=SECRET)
    except enrollment.ArcLinkFleetEnrollmentError as exc:
        expect("revoked" in str(exc), str(exc))
    else:
        raise AssertionError("revoked token should fail")

    expired = enrollment.mint_fleet_enrollment(
        conn,
        created_by_user_id="operator-1",
        ttl_seconds=1,
        secret=SECRET,
        enrollment_id="flenr_expired",
        now_iso="2026-05-15T12:00:00+00:00",
    )
    try:
        enrollment._require_pending_enrollment(
            conn,
            token=expired["token"],
            secret=SECRET,
            now_iso="2026-05-15T12:00:02+00:00",
        )
    except enrollment.ArcLinkFleetEnrollmentError as exc:
        expect("expired" in str(exc), str(exc))
    else:
        raise AssertionError("expired token should fail")

    result = enrollment.consume_fleet_enrollment(conn, token=minted["token"], payload=_attestation_payload(), secret=SECRET)
    expect(result["machine_id"].startswith("machine_"), str(result))
    try:
        enrollment.consume_fleet_enrollment(conn, token=minted["token"], payload=_attestation_payload("worker-reuse.example.test"), secret=SECRET)
    except enrollment.ArcLinkFleetEnrollmentError as exc:
        expect("consumed" in str(exc), str(exc))
    else:
        raise AssertionError("reused token should fail")
    print("PASS test_tokens_fail_closed_when_malformed_wrong_revoked_expired_or_reused")


def test_callback_attests_worker_links_inventory_and_verifies_chain() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_enrollment_callback_test")
    enrollment = load_module("arclink_fleet_enrollment.py", "arclink_fleet_enrollment_callback_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_fleet_enrollment_callback_test")
    conn = memory_db(control)
    minted = enrollment.mint_fleet_enrollment(
        conn,
        created_by_user_id="operator-1",
        secret=SECRET,
        enrollment_id="flenr_callback",
    )
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test", "ARCLINK_FLEET_ENROLLMENT_SECRET": SECRET})
    attestation = _attestation_payload()
    attestation["ssh_host"] = "10.44.0.11"
    attestation["tailscale_dns_name"] = "worker-1.tailnet.ts.net"
    attestation["wireguard_private_ip"] = "10.44.0.11"
    attestation["wireguard_private_cidr"] = "10.44.0.11/32"
    attestation["wireguard_public_key"] = WORKER_WG_PUBLIC_KEY
    attestation["wireguard_interface"] = "wg-arclink"
    attestation["wireguard_control_endpoint"] = "control.wg.example.test:51820"
    attestation["fleet_share_ssh_key_path"] = "/var/lib/arclink-fleet/fleet-share-ssh/id_ed25519"
    attestation["fleet_share_ssh_known_hosts_file"] = "/var/lib/arclink-fleet/fleet-share-ssh/known_hosts"
    attestation["fleet_share_ssh_public_key"] = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestArcLinkFleetShareKey arclink-fleet-share@test"
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/fleet/enrollment/callback",
        headers={"Authorization": f"Bearer {minted['token']}"},
        body=json.dumps(attestation),
        config=config,
    )
    expect(status == 201, f"expected callback 201 got {status}: {payload}")
    rendered = json.dumps(payload, sort_keys=True)
    expect(minted["token"] not in rendered, rendered)
    worker = payload["worker"]
    expect(worker["host_id"].startswith("host_"), str(worker))
    expect(worker["private_dns_name"] == "10.44.0.11", str(worker))
    expect(worker["tailscale_dns_name"] == "worker-1.tailnet.ts.net", str(worker))
    expect(worker["wireguard_private_ip"] == "10.44.0.11", str(worker))
    expect(worker["wireguard_public_key"] == WORKER_WG_PUBLIC_KEY, str(worker))
    expect(worker["fleet_share_ssh_public_key"].startswith("ssh-ed25519 "), str(worker))
    machine = conn.execute(
        "SELECT enrollment_id, machine_fingerprint, attested_at, machine_host_link, audit_trail_chain, metadata_json FROM arclink_inventory_machines WHERE machine_id = ?",
        (worker["machine_id"],),
    ).fetchone()
    expect(machine["enrollment_id"] == "flenr_callback", str(dict(machine)))
    expect(machine["machine_fingerprint"] == _attestation_payload()["machine_fingerprint"], str(dict(machine)))
    expect(str(machine["attested_at"]), str(dict(machine)))
    expect(str(machine["machine_host_link"]).startswith("host_"), str(dict(machine)))
    expect(str(machine["audit_trail_chain"]), str(dict(machine)))
    machine_meta = json.loads(machine["metadata_json"])
    expect(machine_meta["private_dns_name"] == "10.44.0.11", str(machine_meta))
    expect(machine_meta["tailscale_dns_name"] == "worker-1.tailnet.ts.net", str(machine_meta))
    expect(machine_meta["control_network_mode"] == "remote", str(machine_meta))
    expect(machine_meta["wireguard"]["public_key"] == WORKER_WG_PUBLIC_KEY, str(machine_meta))
    expect(machine_meta["fleet_share"]["ssh_key_path"] == "/var/lib/arclink-fleet/fleet-share-ssh/id_ed25519", str(machine_meta))
    expect(machine_meta["fleet_share"]["known_hosts_file"] == "/var/lib/arclink-fleet/fleet-share-ssh/known_hosts", str(machine_meta))
    host = conn.execute(
        "SELECT status, drain, capacity_slots, last_health_state, metadata_json FROM arclink_fleet_hosts WHERE host_id = ?",
        (machine["machine_host_link"],),
    ).fetchone()
    expect(host["status"] == "degraded", str(dict(host)))
    expect(int(host["drain"]) == 1, str(dict(host)))
    expect(host["last_health_state"] == "awaiting_control_probe", str(dict(host)))
    expect(int(host["capacity_slots"]) == 6, str(dict(host)))
    host_meta = json.loads(host["metadata_json"])
    expect(host_meta["enrollment_pending_probe"] is True, str(host_meta))
    expect(host_meta["private_dns_name"] == "10.44.0.11", str(host_meta))
    expect(host_meta["tailscale_dns_name"] == "worker-1.tailnet.ts.net", str(host_meta))
    expect(host_meta["control_network_mode"] == "remote", str(host_meta))
    expect(host_meta["wireguard"]["private_ip"] == "10.44.0.11", str(host_meta))
    expect(host_meta["fleet_share"]["public_key"].startswith("ssh-ed25519 "), str(host_meta))

    verified = enrollment.verify_fleet_audit_chain(conn, secret=SECRET)
    expect(verified["ok"] is True and verified["checked_entries"] == 2, str(verified))
    print("PASS test_callback_attests_worker_links_inventory_and_verifies_chain")


def test_callback_source_ip_ignores_spoofed_headers_from_untrusted_peer() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_source_untrusted_test")
    enrollment = load_module("arclink_fleet_enrollment.py", "arclink_fleet_source_untrusted_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_fleet_source_untrusted_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "example.test",
        "ARCLINK_FLEET_ENROLLMENT_SECRET": SECRET,
    })
    metadata = _consume_callback_and_machine_metadata(
        enrollment,
        hosted,
        conn,
        config,
        enrollment_id="flenr_source_untrusted",
        hostname="worker-source-untrusted.example.test",
        headers={
            "X-Forwarded-For": "203.0.113.66",
            "X-Real-IP": "203.0.113.77",
        },
        remote_addr="198.51.100.10",
    )
    expect(metadata["source_ip"] == "198.51.100.10", str(metadata))
    expect(metadata["source_ip_trust"] == "direct-peer", str(metadata))
    expect("203.0.113.66" not in json.dumps(metadata, sort_keys=True), str(metadata))
    print("PASS test_callback_source_ip_ignores_spoofed_headers_from_untrusted_peer")


def test_callback_source_ip_uses_forwarded_ip_only_from_trusted_proxy() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_source_trusted_test")
    enrollment = load_module("arclink_fleet_enrollment.py", "arclink_fleet_source_trusted_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_fleet_source_trusted_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "example.test",
        "ARCLINK_FLEET_ENROLLMENT_SECRET": SECRET,
        "ARCLINK_TRUSTED_PROXY_CIDRS": "172.16.0.0/12",
    })
    metadata = _consume_callback_and_machine_metadata(
        enrollment,
        hosted,
        conn,
        config,
        enrollment_id="flenr_source_trusted",
        hostname="worker-source-trusted.example.test",
        headers={"X-Forwarded-For": "203.0.113.88, 198.51.100.99"},
        remote_addr="172.18.0.10",
    )
    expect(metadata["source_ip"] == "203.0.113.88", str(metadata))
    expect(metadata["source_ip_trust"] == "trusted-proxy-forwarded", str(metadata))
    print("PASS test_callback_source_ip_uses_forwarded_ip_only_from_trusted_proxy")


def test_callback_source_ip_is_unverified_without_remote_addr() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_source_unverified_test")
    enrollment = load_module("arclink_fleet_enrollment.py", "arclink_fleet_source_unverified_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_fleet_source_unverified_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "example.test",
        "ARCLINK_FLEET_ENROLLMENT_SECRET": SECRET,
        "ARCLINK_TRUSTED_PROXY_CIDRS": "172.16.0.0/12",
    })
    metadata = _consume_callback_and_machine_metadata(
        enrollment,
        hosted,
        conn,
        config,
        enrollment_id="flenr_source_unverified",
        hostname="worker-source-unverified.example.test",
        headers={"X-Forwarded-For": "203.0.113.123", "X-Real-IP": "203.0.113.124"},
        remote_addr="",
    )
    expect(metadata["source_ip"] == "unverified", str(metadata))
    expect(metadata["source_ip_trust"] == "unverified", str(metadata))
    expect("203.0.113.123" not in json.dumps(metadata, sort_keys=True), str(metadata))
    print("PASS test_callback_source_ip_is_unverified_without_remote_addr")


def test_callback_authorization_stays_bearer_token_based_not_source_ip_based() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_source_auth_test")
    enrollment = load_module("arclink_fleet_enrollment.py", "arclink_fleet_source_auth_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_fleet_source_auth_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "example.test",
        "ARCLINK_FLEET_ENROLLMENT_SECRET": SECRET,
        "ARCLINK_TRUSTED_PROXY_CIDRS": "172.16.0.0/12",
    })

    accepted = _consume_callback_and_machine_metadata(
        enrollment,
        hosted,
        conn,
        config,
        enrollment_id="flenr_source_auth_valid",
        hostname="worker-source-auth-valid.example.test",
        headers={},
        remote_addr="198.51.100.44",
    )
    expect(accepted["source_ip"] == "198.51.100.44", str(accepted))

    minted = enrollment.mint_fleet_enrollment(
        conn,
        created_by_user_id="operator-1",
        secret=SECRET,
        enrollment_id="flenr_source_auth_invalid",
    )
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/fleet/enrollment/callback",
        headers={
            "Authorization": f"Bearer {minted['token']}x",
            "X-Forwarded-For": "203.0.113.200",
        },
        body=json.dumps(_attestation_payload("worker-source-auth-invalid.example.test")),
        config=config,
        remote_addr="172.18.0.10",
    )
    expect(status == 401, f"invalid bearer should fail even through trusted proxy: {status} {payload}")
    row = conn.execute(
        "SELECT status, redeemed_by_inventory_id FROM arclink_fleet_enrollments WHERE enrollment_id = 'flenr_source_auth_invalid'"
    ).fetchone()
    expect(row["status"] == "pending" and not str(row["redeemed_by_inventory_id"] or ""), str(dict(row)))
    print("PASS test_callback_authorization_stays_bearer_token_based_not_source_ip_based")


def test_attestation_capacity_is_capped_until_control_probe() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_enrollment_capacity_cap_test")
    enrollment = load_module("arclink_fleet_enrollment.py", "arclink_fleet_enrollment_capacity_cap_test")
    conn = memory_db(control)
    minted = enrollment.mint_fleet_enrollment(
        conn,
        created_by_user_id="operator-1",
        secret=SECRET,
        enrollment_id="flenr_capacity_cap",
    )
    payload = _attestation_payload("worker-capacity.example.test")
    payload["capacity_slots"] = 100_000
    result = enrollment.consume_fleet_enrollment(conn, token=minted["token"], payload=payload, secret=SECRET)
    host = conn.execute(
        "SELECT status, drain, capacity_slots FROM arclink_fleet_hosts WHERE host_id = ?",
        (result["host_id"],),
    ).fetchone()
    expect(host["status"] == "degraded" and int(host["drain"]) == 1, str(dict(host)))
    expect(int(host["capacity_slots"]) == 64, str(dict(host)))
    print("PASS test_attestation_capacity_is_capped_until_control_probe")


def test_attestation_rejects_unsafe_network_identity_values() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_enrollment_hardening_test")
    enrollment = load_module("arclink_fleet_enrollment.py", "arclink_fleet_enrollment_hardening_test")
    conn = memory_db(control)
    cases = [
        ("hostname_control", {"hostname": "bad\nhost"}, "hostname"),
        ("ssh_host_scheme", {"ssh_host": "https://worker.example.test"}, "SSH host"),
        ("ssh_user_shell", {"ssh_user": "root;id"}, "SSH user"),
        ("wg_bad_ip", {"wireguard_private_ip": "10.44.0.999"}, "private CIDR"),
        ("wg_bad_prefix", {"wireguard_private_cidr": "10.44.0.11/999"}, "private CIDR"),
        (
            "wg_ip_mismatch",
            {"wireguard_private_cidr": "10.44.0.11/32", "wireguard_private_ip": "10.44.0.12"},
            "does not match",
        ),
        ("wg_bad_interface", {"wireguard_interface": "../../../wg"}, "interface"),
        ("wg_bad_endpoint", {"wireguard_control_endpoint": "control.example.test:99999"}, "endpoint"),
        ("wg_bad_listen", {"wireguard_listen_port": 70000}, "listen port"),
        ("wg_bad_firewall", {"wireguard_firewall_status": "allowed\nok"}, "firewall"),
    ]
    for suffix, override, expected in cases:
        enrollment_id = f"flenr_hardening_{suffix}"
        minted = enrollment.mint_fleet_enrollment(
            conn,
            created_by_user_id="operator-1",
            secret=SECRET,
            enrollment_id=enrollment_id,
        )
        payload = _attestation_payload(f"worker-{suffix.replace('_', '-')}.example.test")
        payload.update(override)
        try:
            enrollment.consume_fleet_enrollment(conn, token=minted["token"], payload=payload, secret=SECRET)
        except enrollment.ArcLinkFleetEnrollmentError as exc:
            expect(expected in str(exc), f"{suffix} expected {expected!r}, saw {exc!r}")
        else:
            raise AssertionError(f"{suffix} should fail closed")
        row = conn.execute(
            "SELECT status FROM arclink_fleet_enrollments WHERE enrollment_id = ?",
            (enrollment_id,),
        ).fetchone()
        expect(row["status"] == "pending", f"{suffix} consumed or revoked token unexpectedly: {dict(row)}")
    print("PASS test_attestation_rejects_unsafe_network_identity_values")


def test_attestation_accepts_valid_ipv6_wireguard_defaults() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_enrollment_ipv6_test")
    enrollment = load_module("arclink_fleet_enrollment.py", "arclink_fleet_enrollment_ipv6_test")
    conn = memory_db(control)
    minted = enrollment.mint_fleet_enrollment(
        conn,
        created_by_user_id="operator-1",
        secret=SECRET,
        enrollment_id="flenr_ipv6",
    )
    payload = _attestation_payload("worker-ipv6.example.test")
    payload["wireguard_private_ip"] = "fd44::11"
    payload["wireguard_public_key"] = WORKER_WG_PUBLIC_KEY
    payload["wireguard_control_endpoint"] = "[fd44::1]:51820"
    result = enrollment.consume_fleet_enrollment(conn, token=minted["token"], payload=payload, secret=SECRET)
    expect(result["wireguard_private_ip"] == "fd44::11", str(result))
    expect(result["wireguard_private_cidr"] == "fd44::11/128", str(result))
    machine = conn.execute(
        "SELECT metadata_json FROM arclink_inventory_machines WHERE machine_id = ?",
        (result["machine_id"],),
    ).fetchone()
    metadata = json.loads(machine["metadata_json"])
    expect(metadata["wireguard"]["control_endpoint"] == "[fd44::1]:51820", str(metadata))
    print("PASS test_attestation_accepts_valid_ipv6_wireguard_defaults")


def test_consume_fleet_enrollment_preserves_image_sync_under_concurrent_gate_write() -> None:
    # H7 (worker enrollment path): consume_fleet_enrollment must open BEGIN IMMEDIATE
    # around the host+machine read->merge->write unit BEFORE the
    # register_inventory_machine(commit=False) -> register_fleet_host(commit=False)
    # chain. register_fleet_host(commit=False) only DEFERS to the caller's lock -- so if
    # consume runs unlocked, register_fleet_host's existence SELECT -> image_sync_* merge
    # -> whole-metadata_json UPDATE runs in autocommit, and a NEW gate value committed by
    # a concurrent writer BETWEEN that SELECT and UPDATE is silently lost (the merge is
    # recomputed from the stale pre-write row) -- a host can lose its image_sync_failed
    # gate and become wrongly placement-eligible.
    #
    # We expose the lost-update window deterministically: interpose register_fleet_host's
    # host existence SELECT so that, the instant it reads the host row, a SECOND
    # connection commits a brand-new image_sync_state value. Under the fix consume holds
    # BEGIN IMMEDIATE, so that second write BLOCKS until consume commits and lands AFTER
    # (its value wins, unharmed). Without the lock the second write commits immediately
    # and consume's stale-read UPDATE clobbers it.
    import sqlite3 as _sqlite3
    import tempfile

    control = load_module("arclink_control.py", "arclink_control_consume_gate_race")
    enrollment = load_module("arclink_fleet_enrollment.py", "arclink_fleet_enrollment_consume_gate_race")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_consume_gate_race")

    hostname = "worker-consume-gate.example.test"

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = f"{tmpdir}/control.sqlite3"
        seed = _sqlite3.connect(db_path, timeout=15)
        seed.row_factory = _sqlite3.Row
        control.ensure_schema(seed)
        # Pre-existing fleet host carrying the placement gate keys. The enrollment will
        # re-register the SAME hostname (no matching inventory machine yet), so
        # register_fleet_host takes its existing-host carryover path -- the incoming
        # enrollment metadata sets no image_sync_* keys.
        host = fleet.register_fleet_host(
            seed,
            hostname=hostname,
            capacity_slots=4,
            metadata={"image_sync_state": "failed", "image_sync_digest": "sha256:" + ("b" * 64)},
        )
        host_id = host["host_id"]
        minted = enrollment.mint_fleet_enrollment(
            seed,
            created_by_user_id="operator-1",
            secret=SECRET,
            enrollment_id="flenr_consume_gate_race",
        )
        seed.commit()
        seed.close()

        import threading
        import time as _time

        state = {"fired": False, "competed": False}
        writer_thread = {"t": None}

        # The competing writer commits the AUTHORITATIVE new gate value (image_sync just
        # succeeded). It runs on its own connection with a long busy_timeout so that if
        # consume holds the write lock it cleanly serializes behind it; if consume does
        # NOT hold the lock it commits immediately and is then clobbered.
        def competing_gate_write() -> None:
            c = _sqlite3.connect(db_path, timeout=15)
            c.row_factory = _sqlite3.Row
            c.execute("PRAGMA busy_timeout = 8000")
            try:
                import json as _json
                cur = c.execute("SELECT metadata_json FROM arclink_fleet_hosts WHERE host_id = ?", (host_id,)).fetchone()
                meta = _json.loads(cur["metadata_json"])
                meta["image_sync_state"] = "ok"
                # This UPDATE blocks until consume's BEGIN IMMEDIATE commits (fix) or
                # commits immediately into the gap (bug).
                c.execute("UPDATE arclink_fleet_hosts SET metadata_json = ? WHERE host_id = ?", (_json.dumps(meta), host_id))
                c.commit()
                state["competed"] = True
            finally:
                c.close()

        # sqlite3.Connection.execute is read-only, so interpose via a Connection
        # subclass: the first time register_fleet_host reads arclink_fleet_hosts by
        # hostname, kick off the competing writer and give it a moment to attempt its
        # write -- precisely the lost-update window between the SELECT and the UPDATE.
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
            enrollment.consume_fleet_enrollment(
                reg,
                token=minted["token"],
                payload=_attestation_payload(hostname),
                secret=SECRET,
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
        # Under the fix the competing writer was serialized AFTER consume's locked
        # read-merge-write, so its authoritative new value ('ok') survives. The digest
        # gate key (set by neither writer's incoming metadata) is preserved by the
        # carryover throughout.
        expect(meta.get("image_sync_state") == "ok", f"concurrent gate write was lost (H7 lost-update): {meta}")
        expect(meta.get("image_sync_digest") == "sha256:" + ("b" * 64), f"image_sync_digest gate key dropped: {meta}")
    print("PASS test_consume_fleet_enrollment_preserves_image_sync_under_concurrent_gate_write")


def test_fingerprint_mismatch_requires_explicit_reattest() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_enrollment_fp_test")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_fleet_enrollment_fp_test")
    enrollment = load_module("arclink_fleet_enrollment.py", "arclink_fleet_enrollment_fp_test")
    conn = memory_db(control)
    existing = inventory.register_inventory_machine(
        conn,
        provider="manual",
        hostname="worker-fp.example.test",
        status="ready",
        capacity_slots=4,
    )
    conn.execute(
        "UPDATE arclink_inventory_machines SET machine_fingerprint = 'sha256:existing-fingerprint-abcdef1234567890' WHERE machine_id = ?",
        (existing["machine_id"],),
    )
    conn.commit()
    minted = enrollment.mint_fleet_enrollment(
        conn,
        created_by_user_id="operator-1",
        secret=SECRET,
        enrollment_id="flenr_fpmismatch",
    )
    payload = _attestation_payload("worker-fp.example.test")
    try:
        enrollment.consume_fleet_enrollment(conn, token=minted["token"], payload=payload, secret=SECRET)
    except enrollment.ArcLinkFleetEnrollmentError as exc:
        expect("re-attest" in str(exc), str(exc))
    else:
        raise AssertionError("fingerprint mismatch should fail")
    row = conn.execute("SELECT status FROM arclink_fleet_enrollments WHERE enrollment_id = 'flenr_fpmismatch'").fetchone()
    expect(row["status"] == "pending", str(dict(row)))
    print("PASS test_fingerprint_mismatch_requires_explicit_reattest")


def test_failed_consume_guard_rolls_back_inventory_side_effects() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_enrollment_consume_rollback_test")
    enrollment = load_module("arclink_fleet_enrollment.py", "arclink_fleet_enrollment_consume_rollback_test")
    conn = memory_db(control)
    minted = enrollment.mint_fleet_enrollment(
        conn,
        created_by_user_id="operator-1",
        secret=SECRET,
        enrollment_id="flenr_guard_rollback",
    )
    original_register = enrollment.register_inventory_machine

    def racing_register(conn_arg, **kwargs):
        machine = original_register(conn_arg, **kwargs)
        conn_arg.execute(
            "UPDATE arclink_fleet_enrollments SET status = 'consumed' WHERE enrollment_id = 'flenr_guard_rollback'"
        )
        return machine

    enrollment.register_inventory_machine = racing_register
    try:
        try:
            enrollment.consume_fleet_enrollment(
                conn,
                token=minted["token"],
                payload=_attestation_payload("worker-rollback.example.test"),
                secret=SECRET,
            )
        except enrollment.ArcLinkFleetEnrollmentError as exc:
            expect("could not be consumed" in str(exc), str(exc))
        else:
            raise AssertionError("consume guard failure should be surfaced")
    finally:
        enrollment.register_inventory_machine = original_register

    machines = conn.execute("SELECT COUNT(*) AS count FROM arclink_inventory_machines").fetchone()
    hosts = conn.execute("SELECT COUNT(*) AS count FROM arclink_fleet_hosts").fetchone()
    token_row = conn.execute("SELECT status FROM arclink_fleet_enrollments WHERE enrollment_id = 'flenr_guard_rollback'").fetchone()
    expect(machines["count"] == 0, str(dict(machines)))
    expect(hosts["count"] == 0, str(dict(hosts)))
    expect(token_row["status"] == "pending", str(dict(token_row)))
    print("PASS test_failed_consume_guard_rolls_back_inventory_side_effects")


def test_audit_chain_tampering_notifies_operator() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_enrollment_chain_test")
    enrollment = load_module("arclink_fleet_enrollment.py", "arclink_fleet_enrollment_chain_test")
    conn = memory_db(control)
    minted = enrollment.mint_fleet_enrollment(
        conn,
        created_by_user_id="operator-1",
        secret=SECRET,
        enrollment_id="flenr_chain",
    )
    result = enrollment.consume_fleet_enrollment(conn, token=minted["token"], payload=_attestation_payload("worker-chain.example.test"), secret=SECRET)
    conn.execute(
        "UPDATE arclink_fleet_audit_chain SET metadata_json = ? WHERE inventory_id = ? AND event = 'verified'",
        (json.dumps({"tampered": True}, sort_keys=True), result["machine_id"]),
    )
    conn.commit()
    verified = enrollment.verify_fleet_audit_chain(conn, notify=True, secret=SECRET)
    expect(verified["ok"] is False, str(verified))
    messages = [
        dict(row)
        for row in conn.execute(
            "SELECT target_kind, target_id, message, extra_json FROM notification_outbox WHERE target_kind = 'operator'"
        ).fetchall()
    ]
    expect(messages and "P0" in messages[-1]["message"], str(messages))
    expect("arcfleet_v1" not in json.dumps(messages, sort_keys=True), str(messages))
    print("PASS test_audit_chain_tampering_notifies_operator")


def test_audit_chain_rejects_unkeyed_legacy_entries_when_secret_is_configured() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_enrollment_legacy_chain_test")
    enrollment = load_module("arclink_fleet_enrollment.py", "arclink_fleet_enrollment_legacy_chain_test")
    conn = memory_db(control)
    minted = enrollment.mint_fleet_enrollment(
        conn,
        created_by_user_id="operator-1",
        secret=SECRET,
        enrollment_id="flenr_legacy_chain",
    )
    worker = enrollment.consume_fleet_enrollment(
        conn,
        token=minted["token"],
        payload=_attestation_payload("worker-legacy-chain.example.test"),
        secret=SECRET,
    )
    prev_hash = ""
    rows = conn.execute(
        "SELECT * FROM arclink_fleet_audit_chain WHERE inventory_id = ? ORDER BY rowid ASC",
        (worker["machine_id"],),
    ).fetchall()
    for row in rows:
        legacy_hash = enrollment._chain_hash(
            inventory_id=str(row["inventory_id"] or ""),
            event=str(row["event"] or ""),
            actor=str(row["actor"] or ""),
            event_at=str(row["event_at"] or ""),
            prev_hash=prev_hash,
            metadata_json=str(row["metadata_json"] or "{}"),
            secret="",
        )
        conn.execute(
            "UPDATE arclink_fleet_audit_chain SET prev_hash = ?, entry_hash = ? WHERE entry_id = ?",
            (prev_hash, legacy_hash, str(row["entry_id"])),
        )
        prev_hash = legacy_hash
    conn.commit()

    verified = enrollment.verify_fleet_audit_chain(conn, notify=True, secret=SECRET)
    expect(verified["ok"] is False, str(verified))
    expect(any(error.get("error") == "legacy_unkeyed_entry" for error in verified["errors"]), str(verified))
    notification = conn.execute(
        "SELECT message FROM notification_outbox WHERE target_id = 'fleet-audit-chain' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    expect(notification is not None and "P0" in notification["message"], str(notification))
    print("PASS test_audit_chain_rejects_unkeyed_legacy_entries_when_secret_is_configured")


def test_cli_list_and_revoke_never_render_token_hash() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_enrollment_cli_test")
    enrollment = load_module("arclink_fleet_enrollment.py", "arclink_fleet_enrollment_cli_test")
    conn = memory_db(control)
    minted = enrollment.mint_fleet_enrollment(
        conn,
        created_by_user_id="operator-1",
        secret=SECRET,
        enrollment_id="flenr_cli",
    )

    listed = enrollment.list_fleet_enrollments(conn)
    revoked = enrollment.revoke_fleet_enrollment(conn, enrollment_id="flenr_cli", actor="operator-1")
    rendered = json.dumps({"listed": listed, "revoked": revoked}, sort_keys=True)
    expect(minted["token"] not in rendered, rendered)
    expect("token_hash" not in rendered and "hmac_sha256_v1" not in rendered, rendered)
    expect(revoked["status"] == "revoked", rendered)
    print("PASS test_cli_list_and_revoke_never_render_token_hash")


def test_hmac_root_rotation_revokes_pending_tokens_without_rendering_secret() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_enrollment_rotate_test")
    enrollment = load_module("arclink_fleet_enrollment.py", "arclink_fleet_enrollment_rotate_test")
    conn = memory_db(control)
    pending = enrollment.mint_fleet_enrollment(
        conn,
        created_by_user_id="operator-1",
        secret=SECRET,
        enrollment_id="flenr_rotate_pending",
    )
    consumed = enrollment.mint_fleet_enrollment(
        conn,
        created_by_user_id="operator-1",
        secret=SECRET,
        enrollment_id="flenr_rotate_consumed",
    )
    enrollment.consume_fleet_enrollment(
        conn,
        token=consumed["token"],
        payload=_attestation_payload("worker-rotate.example.test"),
        secret=SECRET,
    )
    result = enrollment.record_fleet_enrollment_secret_rotation(
        conn,
        actor="operator-1",
        reason=f"rotate root after token {pending['token']}",
    )
    expect(result["rotated"] is True, str(result))
    expect(result["revoked_pending_enrollments"] == 1, str(result))
    rows = {
        str(row["enrollment_id"]): str(row["status"])
        for row in conn.execute("SELECT enrollment_id, status FROM arclink_fleet_enrollments").fetchall()
    }
    expect(rows["flenr_rotate_pending"] == "revoked", str(rows))
    expect(rows["flenr_rotate_consumed"] == "consumed", str(rows))
    rendered = json.dumps(
        {
            "result": result,
            "audit": [
                dict(row)
                for row in conn.execute(
                    "SELECT action, reason, metadata_json FROM arclink_audit_log WHERE action = 'fleet_enrollment_hmac_root_rotated'"
                ).fetchall()
            ],
        },
        sort_keys=True,
    )
    expect(pending["token"] not in rendered and consumed["token"] not in rendered, rendered)
    expect("arcfleet_v1" not in rendered and SECRET not in rendered, rendered)
    print("PASS test_hmac_root_rotation_revokes_pending_tokens_without_rendering_secret")


def test_inventory_health_verifies_chain_and_notifies_expired_enrollments() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_enrollment_health_test")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_fleet_enrollment_health_test")
    enrollment = load_module("arclink_fleet_enrollment.py", "arclink_fleet_enrollment_health_test")
    conn = memory_db(control)
    expired = enrollment.mint_fleet_enrollment(
        conn,
        created_by_user_id="operator-1",
        ttl_seconds=1,
        secret=SECRET,
        enrollment_id="flenr_health_expired",
        now_iso="2026-05-15T12:00:00+00:00",
    )
    active = enrollment.mint_fleet_enrollment(
        conn,
        created_by_user_id="operator-1",
        secret=SECRET,
        enrollment_id="flenr_health_active",
    )
    enrollment.consume_fleet_enrollment(
        conn,
        token=active["token"],
        payload=_attestation_payload("worker-health.example.test"),
        secret=SECRET,
    )

    old_env = os.environ.copy()
    os.environ["ARCLINK_FLEET_ENROLLMENT_SECRET"] = SECRET
    try:
        health = inventory.fleet_inventory_health(conn, notify=True)
        expect(health["ok"] is True, str(health))
        expect(health["audit_chain"]["checked_entries"] == 2, str(health))
        expect(health["enrollments"]["expired_now"] == 1, str(health))
    finally:
        os.environ.clear()
        os.environ.update(old_env)
    rendered = json.dumps(health, sort_keys=True)
    expect(expired["token"] not in rendered and active["token"] not in rendered, rendered)
    notification = conn.execute(
        "SELECT message, extra_json FROM notification_outbox WHERE target_id = 'fleet-enrollment-expiry'"
    ).fetchone()
    expect(notification is not None and "expired 1 pending" in notification["message"], str(notification))
    print("PASS test_inventory_health_verifies_chain_and_notifies_expired_enrollments")


def test_explicit_reattest_updates_fingerprint_without_rendering_it() -> None:
    control = load_module("arclink_control.py", "arclink_control_fleet_enrollment_reattest_test")
    enrollment = load_module("arclink_fleet_enrollment.py", "arclink_fleet_enrollment_reattest_test")
    conn = memory_db(control)
    minted = enrollment.mint_fleet_enrollment(
        conn,
        created_by_user_id="operator-1",
        secret=SECRET,
        enrollment_id="flenr_reattest",
    )
    worker = enrollment.consume_fleet_enrollment(
        conn,
        token=minted["token"],
        payload=_attestation_payload("worker-reattest.example.test"),
        secret=SECRET,
    )
    old_env = os.environ.copy()
    os.environ["ARCLINK_FLEET_ENROLLMENT_SECRET"] = SECRET
    try:
        new_fingerprint = "sha256:reattested-fingerprint-abcdef1234567890"
        result = enrollment.reattest_inventory_machine(
            conn,
            key=worker["machine_id"],
            machine_fingerprint=new_fingerprint,
            actor="operator-1",
            reason="operator approved replacement disk attestation",
        )
    finally:
        os.environ.clear()
        os.environ.update(old_env)
    expect(result["machine_id"] == worker["machine_id"], str(result))
    expect(new_fingerprint not in json.dumps(result, sort_keys=True), str(result))
    stored = conn.execute(
        "SELECT machine_fingerprint, audit_trail_chain FROM arclink_inventory_machines WHERE machine_id = ?",
        (worker["machine_id"],),
    ).fetchone()
    expect(stored["machine_fingerprint"] == new_fingerprint, str(dict(stored)))
    verified = enrollment.verify_fleet_audit_chain(conn, secret=SECRET)
    expect(verified["ok"] is True and verified["checked_entries"] == 3, str(verified))
    audit_json = json.dumps(
        [dict(row) for row in conn.execute("SELECT metadata_json FROM arclink_fleet_audit_chain").fetchall()],
        sort_keys=True,
    )
    expect(new_fingerprint not in audit_json, audit_json)
    print("PASS test_explicit_reattest_updates_fingerprint_without_rendering_it")


def main() -> int:
    test_mint_stores_only_hmac_hash_and_lists_without_token()
    test_tokens_fail_closed_when_malformed_wrong_revoked_expired_or_reused()
    test_callback_attests_worker_links_inventory_and_verifies_chain()
    test_callback_source_ip_ignores_spoofed_headers_from_untrusted_peer()
    test_callback_source_ip_uses_forwarded_ip_only_from_trusted_proxy()
    test_callback_source_ip_is_unverified_without_remote_addr()
    test_callback_authorization_stays_bearer_token_based_not_source_ip_based()
    test_attestation_capacity_is_capped_until_control_probe()
    test_attestation_rejects_unsafe_network_identity_values()
    test_attestation_accepts_valid_ipv6_wireguard_defaults()
    test_consume_fleet_enrollment_preserves_image_sync_under_concurrent_gate_write()
    test_fingerprint_mismatch_requires_explicit_reattest()
    test_failed_consume_guard_rolls_back_inventory_side_effects()
    test_audit_chain_tampering_notifies_operator()
    test_audit_chain_rejects_unkeyed_legacy_entries_when_secret_is_configured()
    test_cli_list_and_revoke_never_render_token_hash()
    test_hmac_root_rotation_revokes_pending_tokens_without_rendering_secret()
    test_inventory_health_verifies_chain_and_notifies_expired_enrollments()
    test_explicit_reattest_updates_fingerprint_without_rendering_it()
    print("PASS all 19 ArcLink fleet enrollment tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
