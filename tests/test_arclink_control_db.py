#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONTROL_PY = REPO / "python" / "arclink_control.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def memory_db(mod):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    mod.ensure_schema(conn)
    return conn


def test_connect_db_tolerates_locked_journal_mode_pragma() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_db_lock_test")

    class FakeConn:
        row_factory = None

        def __init__(self) -> None:
            self.statements: list[str] = []

        def execute(self, sql: str, *args, **kwargs):
            self.statements.append(sql)
            if sql == "PRAGMA journal_mode = DELETE":
                raise sqlite3.OperationalError("database is locked")
            return self

    fake_conn = FakeConn()
    original_connect = mod.sqlite3.connect
    original_schema = mod.ensure_schema
    original_migrate = mod._migrate_onboarding_bot_tokens
    original_expire = mod.expire_stale_ssot_pending_writes
    original_env = mod.config_env_value
    old_env = os.environ.copy()
    try:
        mod.sqlite3.connect = lambda *_args, **_kwargs: fake_conn
        mod.ensure_schema = lambda *_args, **_kwargs: None
        mod._migrate_onboarding_bot_tokens = lambda *_args, **_kwargs: None
        mod.expire_stale_ssot_pending_writes = lambda *_args, **_kwargs: None
        mod.config_env_value = lambda key, default="": "DELETE" if key == "ARCLINK_SQLITE_JOURNAL_MODE" else default
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config" / "arclink.env"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                "\n".join(
                    [
                        f"ARCLINK_REPO_DIR={root}",
                        f"ARCLINK_PRIV_DIR={root / 'priv'}",
                        f"STATE_DIR={root / 'state'}",
                        f"RUNTIME_DIR={root / 'runtime'}",
                        f"VAULT_DIR={root / 'vault'}",
                    ]
                ),
                encoding="utf-8",
            )
            os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
        expect(conn is fake_conn, "connect_db should return the opened connection")
        expect(fake_conn.statements[0] == "PRAGMA busy_timeout = 15000", str(fake_conn.statements))
        expect("PRAGMA foreign_keys = ON" in fake_conn.statements, str(fake_conn.statements))
        print("PASS test_connect_db_tolerates_locked_journal_mode_pragma")
    finally:
        mod.sqlite3.connect = original_connect
        mod.ensure_schema = original_schema
        mod._migrate_onboarding_bot_tokens = original_migrate
        mod.expire_stale_ssot_pending_writes = original_expire
        mod.config_env_value = original_env
        os.environ.clear()
        os.environ.update(old_env)


def test_operation_idempotency_reserve_complete_and_replay() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_db_operation_idem_replay")
    conn = memory_db(mod)
    intent = {"deployment_id": "dep_1", "action": "refund", "amount_cents": 500}

    reserved = mod.reserve_arclink_operation_idempotency(
        conn,
        operation_kind="stripe.refund",
        idempotency_key="idem_refund_1",
        intent=intent,
        status="running",
    )
    expect(reserved["reserved"] is True, str(reserved))
    expect(reserved["replay"] is False, str(reserved))
    expect(reserved["status"] == "running", str(reserved))

    completed = mod.complete_arclink_operation_idempotency(
        conn,
        operation_kind="stripe.refund",
        idempotency_key="idem_refund_1",
        intent={"amount_cents": 500, "action": "refund", "deployment_id": "dep_1"},
        provider_refs={"refund_id": "re_123"},
        result={"status": "applied"},
    )
    expect(completed["status"] == "succeeded", str(completed))
    expect(json.loads(completed["provider_refs_json"])["refund_id"] == "re_123", str(completed))

    replay = mod.replay_arclink_operation_idempotency(
        conn,
        operation_kind="stripe.refund",
        idempotency_key="idem_refund_1",
        intent=intent,
    )
    expect(replay is not None and replay["replay"] is True, str(replay))

    reserved_again = mod.reserve_arclink_operation_idempotency(
        conn,
        operation_kind="stripe.refund",
        idempotency_key="idem_refund_1",
        intent=intent,
    )
    expect(reserved_again["reserved"] is False, str(reserved_again))
    expect(reserved_again["replay"] is True, str(reserved_again))
    print("PASS test_operation_idempotency_reserve_complete_and_replay")


def test_parse_utc_iso_normalizes_z_and_offset_timestamps() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_db_timestamp_parse")
    zulu = mod.parse_utc_iso("2026-05-11T12:00:00Z")
    offset = mod.parse_utc_iso("2026-05-11T08:00:00-04:00")
    plus = mod.parse_utc_iso("2026-05-11T12:00:00+00:00")
    expect(zulu is not None and offset is not None and plus is not None, "timestamps should parse")
    expect(zulu == offset == plus, f"expected normalized equality: {zulu} {offset} {plus}")
    expect(mod.parse_utc_iso("not a timestamp") is None, "invalid timestamp should return None")
    print("PASS test_parse_utc_iso_normalizes_z_and_offset_timestamps")


def test_operation_idempotency_rejects_same_key_different_intent() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_db_operation_idem_conflict")
    conn = memory_db(mod)
    mod.reserve_arclink_operation_idempotency(
        conn,
        operation_kind="chutes.key",
        idempotency_key="idem_chutes_1",
        intent={"deployment_id": "dep_1", "action": "rotate"},
    )
    try:
        mod.reserve_arclink_operation_idempotency(
            conn,
            operation_kind="chutes.key",
            idempotency_key="idem_chutes_1",
            intent={"deployment_id": "dep_1", "action": "revoke"},
        )
    except ValueError as exc:
        expect("already bound" in str(exc), str(exc))
    else:
        raise AssertionError("expected same idempotency key with changed intent to fail")
    print("PASS test_operation_idempotency_rejects_same_key_different_intent")


def test_operation_idempotency_failed_attempt_replays_without_completion() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_db_operation_idem_failed")
    conn = memory_db(mod)
    intent = {"deployment_id": "dep_1", "action": "create"}
    mod.reserve_arclink_operation_idempotency(
        conn,
        operation_kind="chutes.key",
        idempotency_key="idem_chutes_fail_1",
        intent=intent,
    )
    failed = mod.fail_arclink_operation_idempotency(
        conn,
        operation_kind="chutes.key",
        idempotency_key="idem_chutes_fail_1",
        intent=intent,
        error="adapter unavailable",
    )
    expect(failed["status"] == "failed", str(failed))
    replay = mod.reserve_arclink_operation_idempotency(
        conn,
        operation_kind="chutes.key",
        idempotency_key="idem_chutes_fail_1",
        intent=intent,
    )
    expect(replay["reserved"] is False and replay["replay"] is True, str(replay))
    try:
        mod.complete_arclink_operation_idempotency(
            conn,
            operation_kind="chutes.key",
            idempotency_key="idem_chutes_fail_1",
            intent=intent,
            result={"status": "applied"},
        )
    except ValueError as exc:
        expect("already failed" in str(exc), str(exc))
    else:
        raise AssertionError("expected failed idempotency row to reject completion")
    print("PASS test_operation_idempotency_failed_attempt_replays_without_completion")


def test_operation_idempotency_persists_across_restart() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_db_operation_idem_restart")
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "control.sqlite3"
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        mod.ensure_schema(conn)
        intent = {"deployment_id": "dep_restart", "action": "cancel"}
        mod.reserve_arclink_operation_idempotency(
            conn,
            operation_kind="stripe.cancel",
            idempotency_key="idem_restart_1",
            intent=intent,
        )
        mod.complete_arclink_operation_idempotency(
            conn,
            operation_kind="stripe.cancel",
            idempotency_key="idem_restart_1",
            intent=intent,
            provider_refs={"subscription_id": "sub_123"},
            result={"status": "cancelled"},
        )
        conn.close()

        reopened = sqlite3.connect(db_path)
        reopened.row_factory = sqlite3.Row
        mod.ensure_schema(reopened)
        replay = mod.replay_arclink_operation_idempotency(
            reopened,
            operation_kind="stripe.cancel",
            idempotency_key="idem_restart_1",
            intent=intent,
        )
        expect(replay is not None and replay["status"] == "succeeded", str(replay))
        expect(json.loads(replay["result_json"])["status"] == "cancelled", str(replay))
        reopened.close()
    print("PASS test_operation_idempotency_persists_across_restart")


def test_upsert_user_preserves_protected_status_without_privileged_transition() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_db_user_status_test")
    conn = memory_db(mod)
    mod.upsert_arclink_user(conn, user_id="user_suspended", email="suspended@example.test", status="suspended")
    updated = mod.upsert_arclink_user(conn, user_id="user_suspended", display_name="Suspended", status="active")
    expect(updated["status"] == "suspended", str(updated))
    forced = mod.upsert_arclink_user(
        conn,
        user_id="user_suspended",
        status="active",
        force_status_transition=True,
    )
    expect(forced["status"] == "active", str(forced))
    print("PASS test_upsert_user_preserves_protected_status_without_privileged_transition")


def test_email_merge_is_deterministic_and_repoints_owned_rows() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_db_email_merge_test")
    conn = memory_db(mod)
    conn.execute("DROP INDEX IF EXISTS idx_arclink_users_email")
    mod.upsert_arclink_user(conn, user_id="user_winner", email="Person@Example.Test", status="active")
    mod.upsert_arclink_user(conn, user_id="user_loser", email="person@example.test", status="active")
    mod.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_loser",
        user_id="user_loser",
        prefix="loser",
        status="reserved",
    )
    mod.upsert_arclink_subscription_mirror(
        conn,
        subscription_id="sub_loser",
        user_id="user_loser",
        status="active",
        commit=False,
    )
    conn.execute(
        """
        INSERT INTO arclink_credential_handoffs (
          handoff_id, user_id, deployment_id, credential_kind, status, created_at, updated_at
        ) VALUES ('handoff_loser', 'user_loser', 'dep_loser', 'dashboard_password', 'available', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
        """
    )
    conn.execute(
        """
        INSERT INTO arclink_share_grants (
          grant_id, owner_user_id, recipient_user_id, resource_kind, resource_root,
          resource_path, status, created_at, updated_at
        ) VALUES ('share_loser', 'user_loser', 'user_winner', 'file', 'vault', 'notes.md', 'pending_owner_approval', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
        """
    )
    conn.execute(
        """
        INSERT INTO arclink_onboarding_sessions (
          session_id, channel, channel_identity, status, user_id, created_at, updated_at
        ) VALUES ('onb_loser', 'web', 'browser_loser', 'started', 'user_loser', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
        """
    )
    merged = mod.merge_arclink_user_identity_by_email(
        conn,
        email="person@example.test",
        candidate_user_id="user_loser",
        actor_id="test",
        reason="test merge",
    )
    expect(merged["user_id"] == "user_winner", str(merged))
    expect(merged["merged_user_ids"] == ["user_loser"], str(merged))
    loser = conn.execute("SELECT status, email FROM arclink_users WHERE user_id = 'user_loser'").fetchone()
    expect(loser["status"] == "merged" and loser["email"] == "", str(dict(loser)))
    for table, column, row_id in (
        ("arclink_deployments", "user_id", "dep_loser"),
        ("arclink_subscriptions", "user_id", "sub_loser"),
        ("arclink_credential_handoffs", "user_id", "handoff_loser"),
        ("arclink_onboarding_sessions", "user_id", "onb_loser"),
    ):
        id_col = {
            "arclink_deployments": "deployment_id",
            "arclink_subscriptions": "subscription_id",
            "arclink_credential_handoffs": "handoff_id",
            "arclink_onboarding_sessions": "session_id",
        }[table]
        row = conn.execute(f"SELECT {column} FROM {table} WHERE {id_col} = ?", (row_id,)).fetchone()
        expect(row[column] == "user_winner", f"{table} was not repointed: {dict(row)}")
    share = conn.execute("SELECT owner_user_id, recipient_user_id FROM arclink_share_grants WHERE grant_id = 'share_loser'").fetchone()
    expect(share["owner_user_id"] == "user_winner" and share["recipient_user_id"] == "user_winner", str(dict(share)))
    audit = conn.execute("SELECT action FROM arclink_audit_log WHERE target_id = 'user_winner'").fetchone()
    expect(audit is not None and audit["action"] == "user_identity_merged", "merge audit missing")
    print("PASS test_email_merge_is_deterministic_and_repoints_owned_rows")


def test_wave4_schema_indexes_exist_and_totp_active_factor_is_unique() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_db_wave4_index_test")
    conn = memory_db(mod)
    indexes = {
        str(row["name"])
        for row in conn.execute("PRAGMA index_list(arclink_admin_totp_factors)").fetchall()
    }
    expect("idx_arclink_admin_totp_one_active" in indexes, str(indexes))
    user_indexes = {
        str(row["name"])
        for row in conn.execute("PRAGMA index_list(arclink_users)").fetchall()
    }
    expect("idx_arclink_users_stripe_customer" in user_indexes, str(user_indexes))
    conn.execute(
        """
        INSERT INTO arclink_admins (admin_id, email, role, status, created_at, updated_at)
        VALUES ('admin_totp_unique', 'totp@example.test', 'ops', 'active', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
        """
    )
    conn.execute(
        """
        INSERT INTO arclink_admin_totp_factors (factor_id, admin_id, status, secret_ref, enrolled_at)
        VALUES ('totp_one', 'admin_totp_unique', 'pending', 'secret://arclink/admin/totp/one', '2026-01-01T00:00:00+00:00')
        """
    )
    try:
        conn.execute(
            """
            INSERT INTO arclink_admin_totp_factors (factor_id, admin_id, status, secret_ref, enrolled_at)
            VALUES ('totp_two', 'admin_totp_unique', 'verified', 'secret://arclink/admin/totp/two', '2026-01-02T00:00:00+00:00')
            """
        )
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("expected active TOTP factor uniqueness to reject duplicate")
    print("PASS test_wave4_schema_indexes_exist_and_totp_active_factor_is_unique")


def test_wave4_status_checks_and_relationship_drift_are_reported() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_db_wave4_status_drift_test")
    conn = memory_db(mod)
    mod.upsert_arclink_user(conn, user_id="user_drift", email="drift@example.test")
    mod.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_drift",
        user_id="missing_user",
        prefix="drift",
        status="reserved",
    )
    conn.execute(
        """
        INSERT INTO arclink_provisioning_jobs (
          job_id, deployment_id, job_kind, status, requested_at
        ) VALUES ('job_drift', 'missing_dep', 'docker_apply', 'queued', '2026-01-01T00:00:00+00:00')
        """
    )
    conn.execute("PRAGMA ignore_check_constraints = ON")
    conn.execute(
        """
        INSERT INTO arclink_action_intents (
          action_id, admin_id, action_type, target_kind, target_id, status,
          idempotency_key, reason, created_at, updated_at
        ) VALUES ('act_bad_status', 'missing_admin', 'restart', 'deployment', 'dep_drift',
          'bogus', 'idem_bad_status', 'test', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
        """
    )
    conn.execute("PRAGMA ignore_check_constraints = OFF")

    drift = mod.arclink_drift_checks(conn)
    kinds = {item["kind"] for item in drift}
    expect("provisioning_job_deployment_missing" in kinds, str(drift))
    expect("action_intent_admin_missing" in kinds, str(drift))
    expect("action_intent_status_invalid" in kinds, str(drift))
    print("PASS test_wave4_status_checks_and_relationship_drift_are_reported")


def test_wave4_fresh_schema_rejects_invalid_high_value_status() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_db_wave4_check_test")
    conn = memory_db(mod)
    try:
        conn.execute(
            """
            INSERT INTO arclink_users (user_id, email, status, created_at, updated_at)
            VALUES ('user_bad_status', 'bad-status@example.test', 'bogus', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
            """
        )
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("expected fresh schema CHECK to reject invalid user status")
    print("PASS test_wave4_fresh_schema_rejects_invalid_high_value_status")


if __name__ == "__main__":
    test_connect_db_tolerates_locked_journal_mode_pragma()
    test_operation_idempotency_reserve_complete_and_replay()
    test_parse_utc_iso_normalizes_z_and_offset_timestamps()
    test_operation_idempotency_rejects_same_key_different_intent()
    test_operation_idempotency_failed_attempt_replays_without_completion()
    test_operation_idempotency_persists_across_restart()
    test_upsert_user_preserves_protected_status_without_privileged_transition()
    test_email_merge_is_deterministic_and_repoints_owned_rows()
    test_wave4_schema_indexes_exist_and_totp_active_factor_is_unique()
    test_wave4_status_checks_and_relationship_drift_are_reported()
    test_wave4_fresh_schema_rejects_invalid_high_value_status()
