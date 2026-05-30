#!/usr/bin/env python3
"""Tests for ephemeral, single-use share claim nonces (/arclink_share_accept)."""
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"

os.environ.setdefault("ARCLINK_SESSION_HASH_PEPPER", "test-share-nonce-pepper")


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


def _setup(control, *, with_file: bool = True):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    control.ensure_schema(conn)
    tmp = Path(tempfile.mkdtemp())
    owner_root = tmp / "owner"
    (owner_root / "vault" / "Projects").mkdir(parents=True)
    if with_file:
        (owner_root / "vault" / "Projects" / "notes.md").write_text("hello fleet\n", encoding="utf-8")
    rcp_root = tmp / "rcp"
    (rcp_root / "vault").mkdir(parents=True)
    (rcp_root / "linked-resources").mkdir(parents=True)
    now = control.utc_now_iso()
    for uid in ("user_owner", "user_rcp"):
        conn.execute(
            "INSERT INTO arclink_users (user_id, email, status, created_at, updated_at) VALUES (?, ?, 'active', ?, ?)",
            (uid, uid + "@example.test", now, now),
        )

    def _dep(dep_id: str, uid: str, root: Path) -> None:
        metadata = {
            "state_roots": {
                "vault": str(root / "vault"),
                "code_workspace": str(root / "workspace"),
                "linked_resources": str(root / "linked-resources"),
            }
        }
        conn.execute(
            "INSERT INTO arclink_deployments (deployment_id, user_id, prefix, status, metadata_json, created_at, updated_at) "
            "VALUES (?, ?, ?, 'active', ?, ?, ?)",
            (dep_id, uid, dep_id, json.dumps(metadata), now, now),
        )

    _dep("dep_owner", "user_owner", owner_root)
    _dep("dep_rcp", "user_rcp", rcp_root)
    conn.commit()
    return conn, owner_root, rcp_root


def test_mint_returns_single_use_12h_nonce_and_stores_only_hash() -> None:
    control = load_module("arclink_control.py", "arclink_control_nonce_mint_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_nonce_mint_test")
    conn, _owner_root, _rcp_root = _setup(control)
    resp = api.mint_share_claim_nonce_for_owner(
        conn,
        owner_user_id="user_owner",
        owner_deployment_id="dep_owner",
        resource_kind="drive",
        resource_root="vault",
        resource_path="/Projects/notes.md",
        display_name="notes.md",
        source_plugin="drive",
    )
    expect(resp.status == 201, f"mint status {resp.status}")
    payload = resp.payload
    nonce = payload["nonce"]
    expect(nonce.startswith("asn_"), f"nonce prefix {nonce[:8]}")
    expect(payload["expires_in_hours"] == 12, str(payload))
    expect(payload["accept_command"] == f"/arclink_share_accept {nonce}", payload["accept_command"])
    expect("/arclink_share_accept " + nonce in payload["copy_text"], payload["copy_text"])
    expect("review by Raven" in payload["copy_text"], payload["copy_text"])
    expect(payload["reshare_allowed"] is False, str(payload))
    row = conn.execute("SELECT status, nonce_hash FROM arclink_share_claim_nonces").fetchone()
    expect(row["status"] == "pending", row["status"])
    expect(nonce not in row["nonce_hash"], "nonce must never be stored in cleartext")
    print("PASS test_mint_returns_single_use_12h_nonce_and_stores_only_hash")


def test_claim_materializes_read_only_linked_resource_and_is_single_use() -> None:
    control = load_module("arclink_control.py", "arclink_control_nonce_claim_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_nonce_claim_test")
    conn, _owner_root, rcp_root = _setup(control)
    nonce = api.mint_share_claim_nonce_for_owner(
        conn,
        owner_user_id="user_owner",
        owner_deployment_id="dep_owner",
        resource_kind="drive",
        resource_root="vault",
        resource_path="/Projects/notes.md",
        display_name="notes.md",
        source_plugin="drive",
    ).payload["nonce"]

    grant = api.claim_share_nonce_for_recipient(
        conn,
        recipient_user_id="user_rcp",
        nonce=nonce,
        recipient_deployment_id="dep_rcp",
    )
    expect(grant["status"] == "accepted", grant["status"])
    expect(grant["recipient_user_id"] == "user_rcp", grant["recipient_user_id"])
    expect(grant["owner_user_id"] == "user_owner", grant["owner_user_id"])
    expect(grant["access_mode"] == "read", grant["access_mode"])
    expect(grant["reshare_allowed"] is False, str(grant))
    expect(grant["projection"]["status"] == "materialized", str(grant["projection"]))
    expect(grant["projection"]["read_only"] is True, str(grant["projection"]))

    manifest = json.loads((rcp_root / "linked-resources" / ".arclink-linked-resources.json").read_text(encoding="utf-8"))
    entries = manifest["entries"]
    expect(len(entries) == 1, str(entries))
    slug = next(iter(entries))
    expect((rcp_root / "linked-resources" / slug).exists(), "projection path should exist for recipient")

    after = conn.execute("SELECT status, claimed_by_user_id, claimed_grant_id FROM arclink_share_claim_nonces").fetchone()
    expect(after["status"] == "claimed", after["status"])
    expect(after["claimed_by_user_id"] == "user_rcp", after["claimed_by_user_id"])
    expect(after["claimed_grant_id"] == grant["grant_id"], after["claimed_grant_id"])

    # Single use: a second claim must fail and create no second grant.
    try:
        api.claim_share_nonce_for_recipient(conn, recipient_user_id="user_rcp", nonce=nonce, recipient_deployment_id="dep_rcp")
        raise AssertionError("second claim should have been rejected")
    except api.ArcLinkApiAuthError as exc:
        expect("invalid or has expired" in str(exc), str(exc))
    grant_count = conn.execute("SELECT COUNT(*) AS n FROM arclink_share_grants").fetchone()["n"]
    expect(grant_count == 1, f"expected exactly one grant, got {grant_count}")
    print("PASS test_claim_materializes_read_only_linked_resource_and_is_single_use")


def test_expired_nonce_is_rejected_and_marked_expired() -> None:
    control = load_module("arclink_control.py", "arclink_control_nonce_expiry_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_nonce_expiry_test")
    conn, _owner_root, _rcp_root = _setup(control)
    nonce = api.mint_share_claim_nonce_for_owner(
        conn,
        owner_user_id="user_owner",
        owner_deployment_id="dep_owner",
        resource_kind="drive",
        resource_root="vault",
        resource_path="/Projects/notes.md",
        display_name="notes.md",
        source_plugin="drive",
    ).payload["nonce"]
    # Force the nonce to be expired (a timestamp well in the past).
    conn.execute(
        "UPDATE arclink_share_claim_nonces SET expires_at = ?",
        ("2000-01-01T00:00:00+00:00",),
    )
    conn.commit()
    try:
        api.claim_share_nonce_for_recipient(conn, recipient_user_id="user_rcp", nonce=nonce, recipient_deployment_id="dep_rcp")
        raise AssertionError("expired nonce should have been rejected")
    except api.ArcLinkApiAuthError as exc:
        expect("invalid or has expired" in str(exc), str(exc))
    status = conn.execute("SELECT status FROM arclink_share_claim_nonces").fetchone()["status"]
    expect(status == "expired", status)
    expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_share_grants").fetchone()["n"] == 0, "no grant on expiry")
    print("PASS test_expired_nonce_is_rejected_and_marked_expired")


def test_unknown_and_malformed_nonces_are_rejected_generically() -> None:
    control = load_module("arclink_control.py", "arclink_control_nonce_bad_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_nonce_bad_test")
    conn, _owner_root, _rcp_root = _setup(control)
    for bad in ("asn_" + "0" * 48, "not-a-nonce", "", "share_" + "0" * 32):
        try:
            api.claim_share_nonce_for_recipient(conn, recipient_user_id="user_rcp", nonce=bad, recipient_deployment_id="dep_rcp")
            raise AssertionError(f"nonce {bad!r} should have been rejected")
        except api.ArcLinkApiAuthError as exc:
            expect("invalid or has expired" in str(exc), str(exc))
    print("PASS test_unknown_and_malformed_nonces_are_rejected_generically")


def test_broker_claim_nonce_mode_mints_without_recipient() -> None:
    control = load_module("arclink_control.py", "arclink_control_nonce_broker_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_nonce_broker_test")
    conn, _owner_root, _rcp_root = _setup(control)
    token = "broker-token-" + "a" * 24
    api.set_deployment_share_request_broker_token_hash(conn, deployment_id="dep_owner", token=token)
    conn.commit()
    resp = api.create_user_share_grant_from_broker_api(
        conn,
        broker_token=token,
        owner_deployment_id="dep_owner",
        contract="arclink-share-grants",
        source_plugin="drive",
        resource_kind="drive",
        resource_root="vault",
        resource_path="/Projects/notes.md",
        display_name="notes.md",
        item_kind="file",
        share_mode="claim_nonce",
    )
    expect(resp.status == 201, f"broker mint status {resp.status}")
    expect(resp.payload["mode"] == "claim_nonce", str(resp.payload))
    expect(resp.payload["nonce"].startswith("asn_"), resp.payload["nonce"][:8])
    # No share grant is created at mint time; only a pending nonce exists.
    expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_share_grants").fetchone()["n"] == 0, "mint creates no grant")
    expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_share_claim_nonces").fetchone()["n"] == 1, "one nonce minted")

    # A bad broker token must be rejected.
    try:
        api.create_user_share_grant_from_broker_api(
            conn,
            broker_token="wrong-token",
            owner_deployment_id="dep_owner",
            contract="arclink-share-grants",
            source_plugin="drive",
            resource_kind="drive",
            resource_root="vault",
            resource_path="/Projects/notes.md",
            share_mode="claim_nonce",
        )
        raise AssertionError("bad broker token should have been rejected")
    except api.ArcLinkApiAuthError:
        pass
    print("PASS test_broker_claim_nonce_mode_mints_without_recipient")


def test_raven_claim_command_accepts_nonce_and_rejects_garbage() -> None:
    control = load_module("arclink_control.py", "arclink_control_nonce_raven_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_nonce_raven_test")
    bots = load_module("arclink_public_bots.py", "arclink_public_bots_nonce_raven_test")
    conn, _owner_root, _rcp_root = _setup(control)
    nonce = api.mint_share_claim_nonce_for_owner(
        conn,
        owner_user_id="user_owner",
        owner_deployment_id="dep_owner",
        resource_kind="drive",
        resource_root="vault",
        resource_path="/Projects/notes.md",
        display_name="notes.md",
        source_plugin="drive",
    ).payload["nonce"]

    # The command regex parses the nonce out of the typed command.
    match = bots.ARCLINK_PUBLIC_BOT_SHARE_CLAIM_RE.match(f"/arclink_share_accept {nonce}")
    expect(match is not None and match.group(1) == nonce, "claim regex should capture the nonce")

    session = {"user_id": "user_rcp", "channel": "telegram", "channel_identity": "555"}
    deployment = {"deployment_id": "dep_rcp", "user_id": "user_rcp", "status": "active"}
    turn = bots._share_claim_reply(
        conn,
        channel="telegram",
        channel_identity="555",
        nonce=nonce,
        session=session,
        deployment=deployment,
    )
    expect(turn.action == "share_claim_accepted", turn.action)
    expect("read-only Linked resource" in turn.reply, turn.reply)

    bad_turn = bots._share_claim_reply(
        conn,
        channel="telegram",
        channel_identity="555",
        nonce="asn_" + "0" * 48,
        session=session,
        deployment=deployment,
    )
    expect(bad_turn.action == "share_claim_invalid", bad_turn.action)
    expect("expire" in bad_turn.reply.lower(), bad_turn.reply)

    unlinked = bots._share_claim_reply(
        conn,
        channel="telegram",
        channel_identity="999",
        nonce=nonce,
        session={"channel": "telegram", "channel_identity": "999"},
        deployment={},
    )
    expect(unlinked.action == "share_claim_unavailable", unlinked.action)
    print("PASS test_raven_claim_command_accepts_nonce_and_rejects_garbage")


def test_owner_can_revoke_unclaimed_nonce_and_revoked_cannot_be_claimed() -> None:
    control = load_module("arclink_control.py", "arclink_control_nonce_revoke_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_nonce_revoke_test")
    conn, _owner_root, _rcp_root = _setup(control)
    resp = api.mint_share_claim_nonce_for_owner(
        conn,
        owner_user_id="user_owner",
        owner_deployment_id="dep_owner",
        resource_kind="drive",
        resource_root="vault",
        resource_path="/Projects/notes.md",
        display_name="notes.md",
        source_plugin="drive",
    )
    nonce = resp.payload["nonce"]
    nonce_id = resp.payload["nonce_id"]

    # A different user cannot revoke it.
    try:
        api.revoke_share_claim_nonce_for_owner(conn, owner_user_id="user_rcp", nonce_id=nonce_id)
        raise AssertionError("non-owner revoke should be rejected")
    except api.ArcLinkApiAuthError:
        pass

    revoked = api.revoke_share_claim_nonce_for_owner(conn, owner_user_id="user_owner", nonce_id=nonce_id)
    expect(revoked["status"] == "revoked", revoked["status"])
    expect("nonce" not in revoked and "nonce_hash" not in revoked, "public nonce view must not expose the secret")
    # Revoke is idempotent.
    again = api.revoke_share_claim_nonce_for_owner(conn, owner_user_id="user_owner", nonce_id=nonce_id)
    expect(again["status"] == "revoked", again["status"])
    # A revoked nonce can no longer be claimed.
    try:
        api.claim_share_nonce_for_recipient(conn, recipient_user_id="user_rcp", nonce=nonce, recipient_deployment_id="dep_rcp")
        raise AssertionError("revoked nonce should not be claimable")
    except api.ArcLinkApiAuthError as exc:
        expect("invalid or has expired" in str(exc), str(exc))
    expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_share_grants").fetchone()["n"] == 0, "revoked nonce must create no grant")
    print("PASS test_owner_can_revoke_unclaimed_nonce_and_revoked_cannot_be_claimed")


def test_batch_expiry_sweeps_stale_pending_nonces() -> None:
    control = load_module("arclink_control.py", "arclink_control_nonce_sweep_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_nonce_sweep_test")
    conn, _owner_root, _rcp_root = _setup(control)
    api.mint_share_claim_nonce_for_owner(
        conn,
        owner_user_id="user_owner",
        owner_deployment_id="dep_owner",
        resource_kind="drive",
        resource_root="vault",
        resource_path="/Projects/notes.md",
        display_name="notes.md",
        source_plugin="drive",
    )
    conn.execute("UPDATE arclink_share_claim_nonces SET expires_at = '2000-01-01T00:00:00+00:00'")
    conn.commit()
    summary = api.expire_revealable_user_material(conn)
    expect(summary.get("share_claim_nonces") == 1, str(summary))
    expect(conn.execute("SELECT status FROM arclink_share_claim_nonces").fetchone()["status"] == "expired", "stale pending nonce should be swept to expired")
    print("PASS test_batch_expiry_sweeps_stale_pending_nonces")


def test_claim_rolls_back_nonce_if_grant_materialization_fails() -> None:
    control = load_module("arclink_control.py", "arclink_control_nonce_rollback_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_nonce_rollback_test")
    conn, _owner_root, _rcp_root = _setup(control)
    nonce = api.mint_share_claim_nonce_for_owner(
        conn,
        owner_user_id="user_owner",
        owner_deployment_id="dep_owner",
        resource_kind="drive",
        resource_root="vault",
        resource_path="/Projects/notes.md",
        display_name="notes.md",
        source_plugin="drive",
    ).payload["nonce"]
    original = api._insert_accepted_share_grant

    def boom(*_args, **_kwargs):
        raise api.ArcLinkApiAuthError("forced materialization failure")

    api._insert_accepted_share_grant = boom
    try:
        try:
            api.claim_share_nonce_for_recipient(conn, recipient_user_id="user_rcp", nonce=nonce, recipient_deployment_id="dep_rcp")
            raise AssertionError("forced claim failure should have raised")
        except api.ArcLinkApiAuthError as exc:
            expect("forced materialization failure" in str(exc), str(exc))
    finally:
        api._insert_accepted_share_grant = original
    row = conn.execute("SELECT status, claimed_by_user_id, claimed_grant_id FROM arclink_share_claim_nonces").fetchone()
    expect(row["status"] == "pending", dict(row))
    expect(row["claimed_by_user_id"] == "" and row["claimed_grant_id"] == "", dict(row))
    expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_share_grants").fetchone()["n"] == 0, "failed claim must not leave grants")
    print("PASS test_claim_rolls_back_nonce_if_grant_materialization_fails")


def test_materialization_failure_cleans_partial_projection() -> None:
    control = load_module("arclink_control.py", "arclink_control_nonce_projection_cleanup_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_nonce_projection_cleanup_test")
    conn, _owner_root, rcp_root = _setup(control)
    nonce = api.mint_share_claim_nonce_for_owner(
        conn,
        owner_user_id="user_owner",
        owner_deployment_id="dep_owner",
        resource_kind="drive",
        resource_root="vault",
        resource_path="/Projects/notes.md",
        display_name="notes.md",
        source_plugin="drive",
    ).payload["nonce"]
    original = api._upsert_linked_manifest_entry

    def boom(*_args, **_kwargs):
        raise OSError("manifest write blocked")

    api._upsert_linked_manifest_entry = boom
    try:
        grant = api.claim_share_nonce_for_recipient(conn, recipient_user_id="user_rcp", nonce=nonce, recipient_deployment_id="dep_rcp")
    finally:
        api._upsert_linked_manifest_entry = original

    expect(grant["projection"]["status"] == "pending_materialization", str(grant["projection"]))
    linked_root = rcp_root / "linked-resources"
    leftovers = sorted(p.name for p in linked_root.iterdir())
    expect(leftovers == [], f"failed materialization must not leave partial projection files: {leftovers}")
    print("PASS test_materialization_failure_cleans_partial_projection")


def main() -> int:
    test_mint_returns_single_use_12h_nonce_and_stores_only_hash()
    test_claim_materializes_read_only_linked_resource_and_is_single_use()
    test_expired_nonce_is_rejected_and_marked_expired()
    test_unknown_and_malformed_nonces_are_rejected_generically()
    test_broker_claim_nonce_mode_mints_without_recipient()
    test_raven_claim_command_accepts_nonce_and_rejects_garbage()
    test_owner_can_revoke_unclaimed_nonce_and_revoked_cannot_be_claimed()
    test_batch_expiry_sweeps_stale_pending_nonces()
    test_claim_rolls_back_nonce_if_grant_materialization_fails()
    test_materialization_failure_cleans_partial_projection()
    print("PASS all 10 ArcLink share-nonce tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
