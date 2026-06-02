#!/usr/bin/env python3
from __future__ import annotations

import json

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
    host_meta = json.loads(
        conn.execute(
            "SELECT metadata_json FROM arclink_fleet_hosts WHERE host_id = ?",
            (machine["machine_host_link"],),
        ).fetchone()["metadata_json"]
    )
    expect(host_meta["private_dns_name"] == "10.44.0.11", str(host_meta))
    expect(host_meta["tailscale_dns_name"] == "worker-1.tailnet.ts.net", str(host_meta))
    expect(host_meta["control_network_mode"] == "remote", str(host_meta))
    expect(host_meta["wireguard"]["private_ip"] == "10.44.0.11", str(host_meta))

    verified = enrollment.verify_fleet_audit_chain(conn)
    expect(verified["ok"] is True and verified["checked_entries"] == 2, str(verified))
    print("PASS test_callback_attests_worker_links_inventory_and_verifies_chain")


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
    verified = enrollment.verify_fleet_audit_chain(conn, notify=True)
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

    health = inventory.fleet_inventory_health(conn, notify=True)
    expect(health["ok"] is True, str(health))
    expect(health["audit_chain"]["checked_entries"] == 2, str(health))
    expect(health["enrollments"]["expired_now"] == 1, str(health))
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
    new_fingerprint = "sha256:reattested-fingerprint-abcdef1234567890"
    result = enrollment.reattest_inventory_machine(
        conn,
        key=worker["machine_id"],
        machine_fingerprint=new_fingerprint,
        actor="operator-1",
        reason="operator approved replacement disk attestation",
    )
    expect(result["machine_id"] == worker["machine_id"], str(result))
    expect(new_fingerprint not in json.dumps(result, sort_keys=True), str(result))
    stored = conn.execute(
        "SELECT machine_fingerprint, audit_trail_chain FROM arclink_inventory_machines WHERE machine_id = ?",
        (worker["machine_id"],),
    ).fetchone()
    expect(stored["machine_fingerprint"] == new_fingerprint, str(dict(stored)))
    verified = enrollment.verify_fleet_audit_chain(conn)
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
    test_fingerprint_mismatch_requires_explicit_reattest()
    test_audit_chain_tampering_notifies_operator()
    test_cli_list_and_revoke_never_render_token_hash()
    test_hmac_root_rotation_revokes_pending_tokens_without_rendering_secret()
    test_inventory_health_verifies_chain_and_notifies_expired_enrollments()
    test_explicit_reattest_updates_fingerprint_without_rendering_it()
    print("PASS all 9 ArcLink fleet enrollment tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
