#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import warnings
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


def config_for_root(mod, root: Path):
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
        )
        + "\n",
        encoding="utf-8",
    )
    old_env = os.environ.copy()
    try:
        os.environ.clear()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        return mod.Config.from_env()
    finally:
        os.environ.clear()
        os.environ.update(old_env)


def test_config_loader_preserves_multi_token_values_and_export_prefix() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_db_config_parser_test")
    old_env = os.environ.copy()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "arclink.env"
            config_path.write_text(
                "\n".join(
                    [
                        "ARCLINK_BACKEND_ALLOWED_CIDRS=10.0.0.0/8 192.168.0.0/16",
                        "export ARCLINK_MCP_PORT=9999",
                        'ARCLINK_EXTRA_MCP_LABEL="External knowledge rail"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            os.environ.clear()
            os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
            merged = mod._load_config_env()
            expect(
                merged["ARCLINK_BACKEND_ALLOWED_CIDRS"] == "10.0.0.0/8 192.168.0.0/16",
                str(merged),
            )
            expect(merged["ARCLINK_MCP_PORT"] == "9999", str(merged))
            expect("export ARCLINK_MCP_PORT" not in merged, str(merged))
            expect(merged["ARCLINK_EXTRA_MCP_LABEL"] == "External knowledge rail", str(merged))
            cfg = mod.Config.from_env()
            expect(cfg.public_mcp_port == 9999, str(cfg.public_mcp_port))
        print("PASS test_config_loader_preserves_multi_token_values_and_export_prefix")
    finally:
        os.environ.clear()
        os.environ.update(old_env)


def test_explicit_missing_config_file_fails_loudly_but_devnull_remains_sentinel() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_db_missing_config_test")
    old_env = os.environ.copy()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ.clear()
            os.environ["ARCLINK_CONFIG_FILE"] = str(Path(tmp) / "missing.env")
            try:
                mod._load_config_env()
            except FileNotFoundError:
                pass
            else:
                raise AssertionError("expected missing explicit ARCLINK_CONFIG_FILE to fail")
            os.environ["ARCLINK_CONFIG_FILE"] = os.devnull
            merged = mod._load_config_env()
            expect(merged["ARCLINK_CONFIG_FILE"] == os.devnull, str(merged))
        print("PASS test_explicit_missing_config_file_fails_loudly_but_devnull_remains_sentinel")
    finally:
        os.environ.clear()
        os.environ.update(old_env)


def test_config_from_env_defaults_invalid_int_values_without_crashing() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_db_invalid_int_test")
    old_env = os.environ.copy()
    try:
        os.environ.clear()
        os.environ["ARCLINK_CONFIG_FILE"] = os.devnull
        os.environ["ARCLINK_MCP_PORT"] = "not-a-port"
        os.environ["ARCLINK_BOOTSTRAP_WINDOW_SECONDS"] = "not-seconds"
        os.environ["ARCLINK_AGENT_PORT_SLOT_SPAN"] = "not-span"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            cfg = mod.Config.from_env()
        expect(cfg.public_mcp_port == 8282, str(cfg.public_mcp_port))
        expect(cfg.bootstrap_window_seconds == 3600, str(cfg.bootstrap_window_seconds))
        expect(cfg.agent_port_slot_span == 5000, str(cfg.agent_port_slot_span))
        expect(len(caught) >= 3, str([str(item.message) for item in caught]))
        print("PASS test_config_from_env_defaults_invalid_int_values_without_crashing")
    finally:
        os.environ.clear()
        os.environ.update(old_env)


def test_config_model_presets_are_deeply_immutable() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_db_model_presets_test")
    old_env = os.environ.copy()
    try:
        os.environ.clear()
        os.environ["ARCLINK_CONFIG_FILE"] = os.devnull
        cfg = mod.Config.from_env()
        try:
            cfg.model_presets["codex"] = "changed"
        except TypeError:
            pass
        else:
            raise AssertionError("expected Config.model_presets to reject in-place mutation")
        print("PASS test_config_model_presets_are_deeply_immutable")
    finally:
        os.environ.clear()
        os.environ.update(old_env)


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

        def fetchone(self):
            return None

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
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                conn = mod.connect_db(cfg)
        expect(conn is fake_conn, "connect_db should return the opened connection")
        expect(fake_conn.statements[0] == "PRAGMA busy_timeout = 15000", str(fake_conn.statements))
        expect("PRAGMA foreign_keys = ON" in fake_conn.statements, str(fake_conn.statements))
        expect(any("database is locked" in str(item.message) for item in caught), str([str(item.message) for item in caught]))
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


def test_event_and_notification_json_reject_plaintext_secrets() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_db_secret_json_test")
    conn = memory_db(mod)
    secret_payload = {"token": "sk-ant-abc123SECRET"}
    for call in (
        lambda: mod.append_arclink_event(
            conn,
            subject_kind="deployment",
            subject_id="dep_secret",
            event_type="secret_test",
            metadata=secret_payload,
        ),
        lambda: mod.append_arclink_event(
            conn,
            subject_kind="deployment",
            subject_id="dep_secret",
            event_type="secret_test",
            metadata='{"token":"sk-ant-abc123SECRET"}',
        ),
        lambda: mod.queue_notification(
            conn,
            target_kind="user-agent",
            target_id="agent-secret",
            channel_kind="telegram",
            message="secret",
            extra=secret_payload,
        ),
    ):
        try:
            call()
        except ValueError as exc:
            expect("secret material" in str(exc), str(exc))
        else:
            raise AssertionError("expected plaintext secret payload to be rejected")
    event_count = conn.execute("SELECT COUNT(*) AS count FROM arclink_events").fetchone()["count"]
    notification_count = conn.execute("SELECT COUNT(*) AS count FROM notification_outbox").fetchone()["count"]
    expect(event_count == 0, str(event_count))
    expect(notification_count == 0, str(notification_count))
    print("PASS test_event_and_notification_json_reject_plaintext_secrets")


def test_expire_stale_ssot_pending_writes_skips_write_when_nothing_due() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_db_ssot_expiry_noop_test")

    class FakeCursor:
        rowcount = 0

        def fetchone(self):
            return None

    class FakeConn:
        def __init__(self) -> None:
            self.update_count = 0
            self.commit_count = 0

        def execute(self, sql: str, *_args):
            if "UPDATE ssot_pending_writes" in sql:
                self.update_count += 1
            return FakeCursor()

        def commit(self) -> None:
            self.commit_count += 1

    conn = FakeConn()
    expired = mod.expire_stale_ssot_pending_writes(conn)
    expect(expired == 0, str(expired))
    expect(conn.update_count == 0, str(conn.update_count))
    expect(conn.commit_count == 0, str(conn.commit_count))
    print("PASS test_expire_stale_ssot_pending_writes_skips_write_when_nothing_due")


def test_legacy_onboarding_token_migration_ignores_uncontained_stored_path() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_db_token_migration_path_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cfg = config_for_root(mod, root)
        conn = memory_db(mod)
        outside_path = root / "outside-token"
        conn.execute(
            """
            INSERT INTO onboarding_sessions (
              session_id, platform, chat_id, sender_id, state,
              pending_bot_token, pending_bot_token_path, created_at, updated_at
            ) VALUES (
              'onb_path_escape', 'telegram', 'chat', 'sender', 'awaiting_bot_token',
              '123456:telegram-token', ?, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
            )
            """,
            (str(outside_path),),
        )
        conn.commit()
        mod._migrate_onboarding_bot_tokens(conn, cfg)
        expect(not outside_path.exists(), f"outside path should not be written: {outside_path}")
        row = conn.execute(
            "SELECT pending_bot_token, pending_bot_token_path FROM onboarding_sessions WHERE session_id = 'onb_path_escape'"
        ).fetchone()
        secret_path = Path(row["pending_bot_token_path"])
        expect(row["pending_bot_token"] == "", str(dict(row)))
        expect(secret_path.read_text(encoding="utf-8").strip() == "123456:telegram-token", str(secret_path))
        secret_path.resolve(strict=False).relative_to(mod.onboarding_secret_dir(cfg).resolve(strict=False))
    print("PASS test_legacy_onboarding_token_migration_ignores_uncontained_stored_path")


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


def test_notification_errors_backoff_and_due_fetch_skips_future_rows() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_db_notification_retry_test")
    conn = memory_db(mod)
    first = mod.queue_notification(
        conn,
        target_kind="operator",
        target_id="operator",
        channel_kind="tui-only",
        message="first",
    )
    mod.mark_notification_error(conn, first, "temporary failure")
    retry = conn.execute(
        "SELECT attempt_count, last_attempt_at, next_attempt_at, delivery_error FROM notification_outbox WHERE id = ?",
        (first,),
    ).fetchone()
    expect(retry["attempt_count"] == 1, dict(retry))
    expect(str(retry["last_attempt_at"] or ""), dict(retry))
    expect(mod.parse_utc_iso(str(retry["next_attempt_at"] or "")) > mod.utc_now(), dict(retry))
    expect(retry["delivery_error"] == "temporary failure", dict(retry))

    second = mod.queue_notification(
        conn,
        target_kind="operator",
        target_id="operator",
        channel_kind="tui-only",
        message="second",
    )
    due = mod.fetch_undelivered_notifications(conn, limit=1)
    expect(len(due) == 1 and due[0]["id"] == second, str(due))
    print("PASS test_notification_errors_backoff_and_due_fetch_skips_future_rows")


def test_notification_retry_backoff_jitters_by_notification_id() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_db_notification_retry_jitter_test")
    base = mod.notification_error_retry_delay_seconds(3)
    values = {mod.notification_error_retry_delay_seconds(3, notification_id=i) for i in range(1, 16)}
    expect(base == 240, str(base))
    expect(len(values) > 1, str(values))
    expect(all(180 <= value <= 300 for value in values), str(values))
    print("PASS test_notification_retry_backoff_jitters_by_notification_id")


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


def test_mark_notification_error_does_not_clobber_delivered_row() -> None:
    # C2: a late/duplicate error must NOT overwrite a delivered row's clean state.
    mod = load_module(CONTROL_PY, "arclink_control_db_c2_delivered_guard_test")
    conn = memory_db(mod)
    nid = mod.queue_notification(
        conn,
        target_kind="public-agent-turn",
        target_id="tg:1",
        channel_kind="telegram",
        message="hi",
    )
    mod.mark_notification_delivered(conn, nid)
    delivered = conn.execute(
        "SELECT delivered_at, delivery_error, attempt_count FROM notification_outbox WHERE id = ?",
        (nid,),
    ).fetchone()
    expect(str(delivered["delivered_at"] or "").strip() != "", dict(delivered))
    expect(delivered["delivery_error"] is None, dict(delivered))
    delivered_at_before = delivered["delivered_at"]

    # A late error (e.g. a recycled worker) must be a no-op on the delivered row.
    mod.mark_notification_error(conn, nid, "late duplicate failure")
    after_error = conn.execute(
        "SELECT delivered_at, delivery_error, attempt_count, next_attempt_at FROM notification_outbox WHERE id = ?",
        (nid,),
    ).fetchone()
    expect(after_error["delivered_at"] == delivered_at_before, dict(after_error))
    expect(after_error["delivery_error"] is None, dict(after_error))
    expect(int(after_error["attempt_count"] or 0) == 0, dict(after_error))

    # A second delivered-mark must not re-stamp delivered_at (idempotent).
    mod.mark_notification_delivered(conn, nid)
    after_redeliver = conn.execute(
        "SELECT delivered_at FROM notification_outbox WHERE id = ?", (nid,)
    ).fetchone()
    expect(after_redeliver["delivered_at"] == delivered_at_before, dict(after_redeliver))

    # A non-delivered row still records the error normally (guard does not over-block).
    nid2 = mod.queue_notification(
        conn, target_kind="operator", target_id="operator", channel_kind="tui-only", message="x"
    )
    mod.mark_notification_error(conn, nid2, "real failure")
    err_row = conn.execute(
        "SELECT delivery_error, attempt_count FROM notification_outbox WHERE id = ?", (nid2,)
    ).fetchone()
    expect(err_row["delivery_error"] == "real failure", dict(err_row))
    expect(int(err_row["attempt_count"] or 0) == 1, dict(err_row))
    print("PASS test_mark_notification_error_does_not_clobber_delivered_row")


def test_operator_hiccup_arm_resolve_is_atomic_and_single_outcome() -> None:
    # H1: interleaved resolve/report on one key resolves to a single deterministic
    # outcome, and the arm-check + audit-insert run in one BEGIN IMMEDIATE txn.
    mod = load_module(CONTROL_PY, "arclink_control_db_h1_operator_hiccup_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cfg = config_for_root(mod, root)
        conn = mod.connect_db(cfg)
        try:
            key = "h1-test-key"
            # First report arms the alert + queues one operator notice.
            first = mod.report_operator_hiccup(
                conn, cfg, source="unit", key=key, message="down"
            )
            expect(int(first) > 0, str(first))
            # A second report on the SAME key while still armed is deduped (no notice).
            second = mod.report_operator_hiccup(
                conn, cfg, source="unit", key=key, message="down again"
            )
            expect(int(second) == 0, str(second))
            armed = conn.execute(
                "SELECT COUNT(*) AS c FROM arclink_audit_log WHERE action = ?",
                (f"{mod.OPERATOR_HICCUP_AUDIT_PREFIX}{key}",),
            ).fetchone()
            expect(int(armed["c"]) == 1, dict(armed))

            # Resolve re-arms; a second resolve is a no-op.
            expect(mod.resolve_operator_hiccup(conn, cfg, source="unit", key=key) is True, "first resolve must apply")
            expect(
                mod.resolve_operator_hiccup(conn, cfg, source="unit", key=key) is False,
                "second resolve on a not-armed key must be a no-op",
            )

            # After resolve, a fresh report pages again (re-arm worked).
            third = mod.report_operator_hiccup(conn, cfg, source="unit", key=key, message="down 3")
            expect(int(third) > 0, str(third))

            # Same-second resolve-then-report ordering must be deterministic: the
            # audit query orders by rowid DESC so the latest action wins even when
            # created_at collides at whole-second resolution.
            mod.resolve_operator_hiccup(conn, cfg, source="unit", key=key)
            mod.report_operator_hiccup(conn, cfg, source="unit", key=key, message="down 4")
            expect(
                mod._operator_hiccup_already_armed(conn, key=key) is True,
                "after resolve->report the key must read as armed (rowid tiebreak)",
            )
            # And a still-armed report dedups.
            dup = mod.report_operator_hiccup(conn, cfg, source="unit", key=key, message="dup")
            expect(int(dup) == 0, str(dup))
        finally:
            conn.close()
    print("PASS test_operator_hiccup_arm_resolve_is_atomic_and_single_outcome")


def _seed_router_key_deployment(mod, conn, *, raw_key: str) -> None:
    mod.upsert_arclink_user(conn, user_id="user_rk", email="rk@example.test", entitlement_state="paid")
    mod.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_rk",
        user_id="user_rk",
        prefix="rk-vault-1a2b",
        base_domain="example.test",
        status="active",
    )
    mod.ensure_llm_router_key(
        conn,
        deployment_id="dep_rk",
        user_id="user_rk",
        secret_ref="secret://arclink/llm-router/dep_rk/api-key",
        raw_key=raw_key,
        allowed_models=["model-a"],
    )


def test_llm_router_key_hash_pepper_fails_closed_outside_local_dev() -> None:
    # sec-C1: the router-key hash pepper must mirror the session pepper guard --
    # raise when no real pepper is configured and the base domain is not local-dev.
    mod = load_module(CONTROL_PY, "arclink_control_db_router_pepper_test")
    old_env = os.environ.copy()
    try:
        # Production-shaped: a real (non-local-dev) base domain and no pepper.
        os.environ.clear()
        os.environ["ARCLINK_CONFIG_FILE"] = os.devnull
        os.environ["ARCLINK_BASE_DOMAIN"] = "arclink.ai"
        raised = False
        try:
            mod._llm_router_key_hash_pepper()
        except ValueError as exc:
            raised = "pepper is not configured" in str(exc)
        expect(raised, "missing pepper outside local-dev must raise")

        # REQUIRED forces the raise even on a local-dev domain.
        os.environ["ARCLINK_BASE_DOMAIN"] = "localhost"
        os.environ["ARCLINK_LLM_ROUTER_KEY_HASH_PEPPER_REQUIRED"] = "1"
        raised_required = False
        try:
            mod._llm_router_key_hash_pepper()
        except ValueError:
            raised_required = True
        expect(raised_required, "REQUIRED must force the raise even on local-dev")

        # A real configured pepper is used verbatim.
        os.environ.pop("ARCLINK_LLM_ROUTER_KEY_HASH_PEPPER_REQUIRED", None)
        os.environ["ARCLINK_BASE_DOMAIN"] = "arclink.ai"
        os.environ["ARCLINK_LLM_ROUTER_KEY_HASH_PEPPER"] = "a-real-router-pepper-value"
        expect(mod._llm_router_key_hash_pepper() == "a-real-router-pepper-value", "configured pepper must win")

        # Local-dev domain with no pepper falls back to the documented dev value.
        os.environ.pop("ARCLINK_LLM_ROUTER_KEY_HASH_PEPPER", None)
        os.environ["ARCLINK_BASE_DOMAIN"] = "example.test"
        expect(
            mod._llm_router_key_hash_pepper() == "arclink-dev-llm-router-key-hash-pepper",
            "local-dev must use the dev fallback",
        )
    finally:
        os.environ.clear()
        os.environ.update(old_env)
    print("PASS test_llm_router_key_hash_pepper_fails_closed_outside_local_dev")


def test_verify_llm_router_key_migrates_legacy_hash_and_throttles_last_seen() -> None:
    # sec-C1 + M3: a legacy (unpeppered) hash is migrated to the peppered hash on
    # successful auth; thereafter last_seen_at is only written when stale (>60s),
    # not on every request.
    mod = load_module(CONTROL_PY, "arclink_control_db_router_verify_test")
    old_env = os.environ.copy()
    try:
        os.environ.clear()
        os.environ["ARCLINK_CONFIG_FILE"] = os.devnull
        os.environ["ARCLINK_BASE_DOMAIN"] = "example.test"  # local-dev dev pepper
        conn = memory_db(mod)
        try:
            raw_key = mod.generate_llm_router_raw_key()
            _seed_router_key_deployment(mod, conn, raw_key=raw_key)
            peppered = mod._hash_llm_router_key(raw_key)
            legacy = mod._legacy_hash_llm_router_key(raw_key)
            expect(peppered != legacy, "peppered and legacy hashes must differ")

            # Force the stored hash back to the legacy (unpeppered) form and a very
            # old last_seen to simulate a pre-migration row.
            conn.execute(
                "UPDATE arclink_llm_router_keys SET key_hash = ?, last_seen_at = '2026-01-01T00:00:00+00:00' WHERE key_id = ?",
                (legacy, "llmk_" + raw_key.split("_")[2]),
            )
            conn.commit()

            record = mod.verify_llm_router_key(conn, raw_key)
            expect(record is not None, "legacy-hash key must still authenticate")
            stored = conn.execute(
                "SELECT key_hash, last_seen_at FROM arclink_llm_router_keys"
            ).fetchone()
            expect(str(stored["key_hash"]) == peppered, "legacy hash must migrate to peppered on auth")
            migrated_seen = str(stored["last_seen_at"])
            expect(migrated_seen != "2026-01-01T00:00:00+00:00", "migration writes a fresh last_seen")

            # M3: an immediate re-auth is within the 60s window -> last_seen NOT rewritten.
            mod.verify_llm_router_key(conn, raw_key)
            after = conn.execute("SELECT last_seen_at FROM arclink_llm_router_keys").fetchone()
            expect(str(after["last_seen_at"]) == migrated_seen, "fresh last_seen must be throttled (no rewrite)")

            # A stale last_seen IS refreshed on the next auth.
            conn.execute(
                "UPDATE arclink_llm_router_keys SET last_seen_at = '2026-02-01T00:00:00+00:00'"
            )
            conn.commit()
            mod.verify_llm_router_key(conn, raw_key)
            refreshed = conn.execute("SELECT last_seen_at FROM arclink_llm_router_keys").fetchone()
            expect(str(refreshed["last_seen_at"]) != "2026-02-01T00:00:00+00:00", "stale last_seen must refresh")
        finally:
            conn.close()
    finally:
        os.environ.clear()
        os.environ.update(old_env)
    print("PASS test_verify_llm_router_key_migrates_legacy_hash_and_throttles_last_seen")


def test_upsert_model_catalog_commit_false_folds_into_caller_txn() -> None:
    # M4: upsert_model_catalog(commit=False) must NOT commit, so the caller can
    # fold the catalog mutation and its audit row into one atomic transaction.
    mod = load_module(CONTROL_PY, "arclink_control_db_catalog_commit_test")
    conn = memory_db(mod)
    try:
        conn.execute("BEGIN")
        rows = mod.upsert_model_catalog(
            conn,
            provider="chutes",
            models={"x-TEE": {"confidential_compute": True}},
            commit=False,
        )
        expect(len(rows) == 1, str(rows))
        expect(conn.in_transaction, "commit=False must leave the txn open for the caller")
        conn.rollback()
        # The rollback discarded the uncommitted upsert.
        remaining = conn.execute("SELECT COUNT(*) AS c FROM arclink_model_catalog").fetchone()["c"]
        expect(int(remaining) == 0, f"rolled-back catalog upsert must not persist, got {remaining}")

        # Default (commit=True) still persists on its own.
        mod.upsert_model_catalog(conn, provider="chutes", models={"y-TEE": {"confidential_compute": True}})
        persisted = conn.execute("SELECT COUNT(*) AS c FROM arclink_model_catalog").fetchone()["c"]
        expect(int(persisted) == 1, str(persisted))
    finally:
        conn.close()
    print("PASS test_upsert_model_catalog_commit_false_folds_into_caller_txn")


def test_llm_budget_reservations_legacy_check_migrates_to_expired_with_heartbeat() -> None:
    # C2: the heartbeat reaper needs a `heartbeat_at` column and an `'expired'`
    # status. Legacy DBs have neither (CHECK lacks 'expired', no heartbeat col).
    # ensure_schema must idempotently add the column (backfilled from created_at)
    # and rebuild the CHECK to admit 'expired', preserving existing rows.
    mod = load_module(CONTROL_PY, "arclink_control_db_reservation_migration_test")
    tmp = tempfile.TemporaryDirectory()
    try:
        db_path = str(Path(tmp.name) / "legacy.sqlite3")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        # Build the OLD reservations table: no heartbeat_at, CHECK without 'expired'.
        conn.executescript(
            """
            CREATE TABLE arclink_llm_budget_reservations (
              reservation_id TEXT PRIMARY KEY,
              request_id TEXT NOT NULL,
              deployment_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              reserved_cents INTEGER NOT NULL,
              settled_cents INTEGER NOT NULL DEFAULT 0,
              status TEXT NOT NULL CHECK (status IN ('reserved', 'settled', 'released', 'failed')),
              metadata_json TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL,
              settled_at TEXT NOT NULL DEFAULT ''
            );
            """
        )
        conn.execute(
            """
            INSERT INTO arclink_llm_budget_reservations (
              reservation_id, request_id, deployment_id, user_id, reserved_cents, status, created_at
            ) VALUES ('llmres_legacy', 'req_legacy', 'dep_1', 'user_1', 5, 'reserved', '2026-01-01T00:00:00+00:00')
            """
        )
        conn.commit()
        # Pre-migration: 'expired' is rejected by the old CHECK.
        try:
            conn.execute(
                "INSERT INTO arclink_llm_budget_reservations "
                "(reservation_id, request_id, deployment_id, user_id, reserved_cents, status, created_at) "
                "VALUES ('llmres_x', 'r', 'd', 'u', 1, 'expired', '2026-01-01T00:00:00+00:00')"
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("legacy CHECK should reject 'expired' before migration")
        conn.rollback()

        # Run the live schema migration.
        mod.ensure_schema(conn)

        cols = {row[1] for row in conn.execute("PRAGMA table_info(arclink_llm_budget_reservations)").fetchall()}
        expect("heartbeat_at" in cols, f"heartbeat_at column must be added: {cols}")
        legacy = conn.execute(
            "SELECT status, heartbeat_at, created_at FROM arclink_llm_budget_reservations WHERE reservation_id='llmres_legacy'"
        ).fetchone()
        expect(str(legacy["status"]) == "reserved", dict(legacy))
        # Backfilled from created_at so a pre-heartbeat leaked row still ages out.
        expect(str(legacy["heartbeat_at"]) == str(legacy["created_at"]), dict(legacy))

        # 'expired' is now an accepted status.
        conn.execute(
            "INSERT INTO arclink_llm_budget_reservations "
            "(reservation_id, request_id, deployment_id, user_id, reserved_cents, status, created_at, heartbeat_at) "
            "VALUES ('llmres_exp', 'r', 'd', 'u', 1, 'expired', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
        )
        conn.commit()
        expired = conn.execute(
            "SELECT status FROM arclink_llm_budget_reservations WHERE reservation_id='llmres_exp'"
        ).fetchone()
        expect(str(expired["status"]) == "expired", dict(expired))

        # Idempotent: a second ensure_schema does not error or re-rebuild needlessly.
        mod.ensure_schema(conn)
        still = conn.execute(
            "SELECT COUNT(*) AS c FROM arclink_llm_budget_reservations"
        ).fetchone()["c"]
        expect(int(still) == 2, f"rows preserved across idempotent migration, got {still}")
        conn.close()
    finally:
        tmp.cleanup()
    print("PASS test_llm_budget_reservations_legacy_check_migrates_to_expired_with_heartbeat")


def test_llm_budget_reservations_rebuild_is_atomic_and_keeps_index_on_first_pass() -> None:
    # Round-3 (deploy-blocking): the 'expired' CHECK rebuild DROPs the table, which
    # also drops idx_arclink_llm_reservations_request_status (created earlier in the
    # ensure_schema index block). The old rebuild left the index missing until a
    # LATER ensure_schema pass and ran outside a transaction (a crash between DROP
    # old and RENAME __new could strand rows). The fix recreates the index INSIDE
    # the rebuild and folds the whole copy/swap into a single transaction.
    #
    # This proves: ONE ensure_schema pass yields the table WITH the index AND the
    # 'expired' CHECK AND all rows preserved; the change is committed durably; and a
    # second pass is a clean no-op.
    mod = load_module(CONTROL_PY, "arclink_control_db_reservation_atomic_test")
    tmp = tempfile.TemporaryDirectory()
    try:
        db_path = str(Path(tmp.name) / "legacy_atomic.sqlite3")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        # Legacy table: CHECK lacks 'expired', no heartbeat_at; plus the legacy index
        # that the DROP-rebuild will tear down (so we prove it is recreated, not just
        # never-dropped).
        conn.executescript(
            """
            CREATE TABLE arclink_llm_budget_reservations (
              reservation_id TEXT PRIMARY KEY,
              request_id TEXT NOT NULL,
              deployment_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              reserved_cents INTEGER NOT NULL,
              settled_cents INTEGER NOT NULL DEFAULT 0,
              status TEXT NOT NULL CHECK (status IN ('reserved', 'settled', 'released', 'failed')),
              metadata_json TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL,
              settled_at TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX idx_arclink_llm_reservations_request_status
              ON arclink_llm_budget_reservations (request_id, status);
            INSERT INTO arclink_llm_budget_reservations
              (reservation_id, request_id, deployment_id, user_id, reserved_cents, status, created_at)
              VALUES ('llmres_a', 'req_a', 'dep_1', 'user_1', 5, 'reserved', '2026-01-01T00:00:00+00:00'),
                     ('llmres_b', 'req_b', 'dep_1', 'user_1', 7, 'settled', '2026-01-02T00:00:00+00:00');
            """
        )
        conn.commit()

        def _index_present(c: sqlite3.Connection) -> bool:
            row = c.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_arclink_llm_reservations_request_status'"
            ).fetchone()
            return row is not None

        def _expired_in_check(c: sqlite3.Connection) -> bool:
            ddl = str(
                c.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name='arclink_llm_budget_reservations'"
                ).fetchone()["sql"]
            )
            return "'expired'" in ddl

        # ONE ensure_schema pass.
        mod.ensure_schema(conn)

        # Index present after the FIRST pass (the core regression) -- not deferred.
        expect(_index_present(conn), "index must exist after a single ensure_schema pass")
        # 'expired' CHECK present.
        expect(_expired_in_check(conn), "rebuilt CHECK must admit 'expired' after one pass")
        # All rows preserved through the copy/swap.
        ids = sorted(
            str(r["reservation_id"])
            for r in conn.execute("SELECT reservation_id FROM arclink_llm_budget_reservations").fetchall()
        )
        expect(ids == ["llmres_a", "llmres_b"], f"all rows must survive the rebuild: {ids}")
        # heartbeat_at column added + backfilled from created_at.
        cols = {row[1] for row in conn.execute("PRAGMA table_info(arclink_llm_budget_reservations)").fetchall()}
        expect("heartbeat_at" in cols, f"heartbeat_at column must be present: {cols}")
        conn.close()

        # Durability: reopen a FRESH connection -> the rebuild committed (atomic
        # swap landed), index and CHECK persist, rows intact.
        conn2 = sqlite3.connect(db_path)
        conn2.row_factory = sqlite3.Row
        expect(_index_present(conn2), "index must persist after reopen (committed)")
        expect(_expired_in_check(conn2), "'expired' CHECK must persist after reopen (committed)")
        durable = conn2.execute("SELECT COUNT(*) AS c FROM arclink_llm_budget_reservations").fetchone()["c"]
        expect(int(durable) == 2, f"rows must be durable after commit, got {durable}")
        # 'expired' is insertable post-migration.
        conn2.execute(
            "INSERT INTO arclink_llm_budget_reservations "
            "(reservation_id, request_id, deployment_id, user_id, reserved_cents, status, created_at, heartbeat_at) "
            "VALUES ('llmres_exp', 'r', 'd', 'u', 1, 'expired', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
        )
        conn2.commit()

        # Second pass is a clean no-op: index/CHECK unchanged, no extra/duplicate
        # rebuild, rows preserved.
        mod.ensure_schema(conn2)
        expect(_index_present(conn2), "index still present after 2nd pass")
        expect(_expired_in_check(conn2), "'expired' CHECK still present after 2nd pass")
        # No leftover __new scratch table from a stranded/partial rebuild.
        leftover = conn2.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='arclink_llm_budget_reservations__new'"
        ).fetchone()
        expect(leftover is None, "no __new scratch table may be left behind")
        final_count = conn2.execute("SELECT COUNT(*) AS c FROM arclink_llm_budget_reservations").fetchone()["c"]
        expect(int(final_count) == 3, f"rows preserved across idempotent 2nd pass, got {final_count}")
        conn2.close()
    finally:
        tmp.cleanup()
    print("PASS test_llm_budget_reservations_rebuild_is_atomic_and_keeps_index_on_first_pass")


def test_operator_action_secret_at_rest_is_rejected_and_hiccup_message_redacted() -> None:
    # sec-H1: operator action authorization payload + JSON targets must reject
    # plaintext secret material at rest; operator-hiccup notice bodies must be
    # redacted before being persisted.
    mod = load_module(CONTROL_PY, "arclink_control_db_operator_secret_test")
    with tempfile.TemporaryDirectory() as tmp:
        cfg = config_for_root(mod, Path(tmp))
        conn = mod.connect_db(cfg)
        try:
            # A JSON requested_target carrying a secret must be rejected.
            rejected_target = False
            try:
                mod.request_operator_action(
                    conn,
                    action_kind="some-action",
                    requested_by="operator",
                    requested_target=json.dumps({"api_key": "sk-ant-SECRET-target-123456"}),
                )
            except ValueError as exc:
                rejected_target = "secret material" in str(exc)
            expect(rejected_target, "JSON target with plaintext secret must be rejected")
            count = conn.execute("SELECT COUNT(*) AS c FROM operator_actions").fetchone()["c"]
            expect(int(count) == 0, "rejected target must not persist a row")

            # The authorization payload builder rejects embedded secrets.
            rejected_payload = False
            try:
                mod._operator_action_auth_payload_json({"confirmation_id": "ok", "token": "sk-ant-SECRET-payload-123456"})
            except ValueError as exc:
                rejected_payload = "secret material" in str(exc)
            expect(rejected_payload, "authorization payload with plaintext secret must be rejected")

            # An operator-hiccup notice body carrying a secret is redacted at rest.
            mod.report_operator_hiccup(
                conn,
                cfg,
                source="unit",
                key="secret-body-key",
                message="upstream failed with key sk-ant-SECRET-body-1234567890",
            )
            body = conn.execute(
                "SELECT message FROM notification_outbox ORDER BY id DESC LIMIT 1"
            ).fetchone()
            expect(body is not None, "hiccup must queue a notice")
            expect("sk-ant-SECRET-body" not in str(body["message"]), str(body["message"]))
            expect("REDACTED" in str(body["message"]), str(body["message"]))
        finally:
            conn.close()
    print("PASS test_operator_action_secret_at_rest_is_rejected_and_hiccup_message_redacted")


def _indexes_on(conn: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(r["name"])
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = ? AND name NOT LIKE 'sqlite_%'",
            (table,),
        ).fetchall()
    }


def _table_sql(conn: sqlite3.Connection, table: str) -> str:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return str(row["sql"] or "") if row is not None else ""


def _scratch_tables(conn: sqlite3.Connection) -> list[str]:
    return [
        str(r["name"])
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE '%\\_\\_new' ESCAPE '\\'"
        ).fetchall()
    ]


def _seed_legacy_migration_db(conn: sqlite3.Connection) -> None:
    # Build the FIVE legacy-shaped tables that the *__new rebuild migrations target,
    # each PRE-POPULATED with rows + the live index that the DROP-rebuild tears down,
    # so we can prove rows + indexes survive and the new schema lands.
    conn.executescript(
        """
        -- arclink_fleet_enrollments: legacy CHECK without the 'pending'/'consumed' set.
        CREATE TABLE arclink_fleet_enrollments (
          enrollment_id TEXT PRIMARY KEY,
          token_hash TEXT NOT NULL,
          created_by_user_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          expires_at TEXT NOT NULL,
          consumed_at TEXT NOT NULL DEFAULT '',
          redeemed_by_inventory_id TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL,
          audit_ref TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX idx_arclink_fleet_enrollments_status_expiry
          ON arclink_fleet_enrollments (status, expires_at);
        INSERT INTO arclink_fleet_enrollments
          (enrollment_id, token_hash, created_by_user_id, created_at, expires_at, status)
          VALUES ('flenr_1', 'h1', 'u1', '2026-01-01T00:00:00+00:00', '2026-02-01T00:00:00+00:00', 'minted'),
                 ('flenr_2', 'h2', 'u1', '2026-01-02T00:00:00+00:00', '2026-02-02T00:00:00+00:00', 'used');

        -- arclink_fleet_host_probes: legacy column shape (probe_kind/status, no 'kind'/'ok').
        CREATE TABLE arclink_fleet_host_probes (
          probe_id TEXT PRIMARY KEY,
          host_id TEXT NOT NULL,
          probed_at TEXT NOT NULL,
          probe_kind TEXT NOT NULL,
          status TEXT NOT NULL,
          latency_ms INTEGER NOT NULL DEFAULT 0,
          payload_json TEXT NOT NULL DEFAULT '{}',
          error TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX idx_arclink_fleet_host_probes_host_kind_time
          ON arclink_fleet_host_probes (host_id, probe_kind, probed_at);
        INSERT INTO arclink_fleet_host_probes
          (probe_id, host_id, probed_at, probe_kind, status)
          VALUES ('flprb_1', 'host_a', '2026-01-01T00:00:00+00:00', 'liveness', 'ok'),
                 ('flprb_2', 'host_a', '2026-01-02T00:00:00+00:00', 'capacity', 'failed');

        -- arclink_fleet_audit_chain: legacy 'event_type' column + placeholder hashes.
        CREATE TABLE arclink_fleet_audit_chain (
          chain_id TEXT PRIMARY KEY,
          inventory_id TEXT NOT NULL,
          event_type TEXT NOT NULL,
          actor TEXT NOT NULL,
          created_at TEXT NOT NULL,
          previous_hash TEXT NOT NULL DEFAULT '',
          metadata_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX idx_arclink_fleet_audit_chain_inventory_time
          ON arclink_fleet_audit_chain (inventory_id, created_at);
        INSERT INTO arclink_fleet_audit_chain
          (chain_id, inventory_id, event_type, actor, created_at)
          VALUES ('fac_1', 'inv_a', 'enrolled', 'system', '2026-01-01T00:00:00+00:00'),
                 ('fac_2', 'inv_a', 'verified', 'system', '2026-01-02T00:00:00+00:00');

        -- arclink_rollouts: legacy 'running'/'succeeded' status values + CHECK.
        CREATE TABLE arclink_rollouts (
          rollout_id TEXT PRIMARY KEY,
          deployment_id TEXT NOT NULL DEFAULT '',
          version_tag TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'running', 'succeeded', 'failed', 'rolled_back')),
          wave_count INTEGER NOT NULL DEFAULT 1,
          current_wave INTEGER NOT NULL DEFAULT 0,
          waves_json TEXT NOT NULL DEFAULT '[]',
          rollback_plan_json TEXT NOT NULL DEFAULT '{}',
          metadata_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE INDEX idx_arclink_rollouts_deployment_status
          ON arclink_rollouts (deployment_id, status);
        INSERT INTO arclink_rollouts (rollout_id, deployment_id, status, created_at, updated_at)
          VALUES ('rol_1', 'dep_1', 'running', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'),
                 ('rol_2', 'dep_2', 'succeeded', '2026-01-02T00:00:00+00:00', '2026-01-02T00:00:00+00:00');

        -- notion_identity_claims: legacy 'verification_nonce' column present.
        CREATE TABLE notion_identity_claims (
          claim_id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL DEFAULT '',
          agent_id TEXT NOT NULL,
          unix_user TEXT NOT NULL,
          claimed_notion_email TEXT NOT NULL,
          notion_page_id TEXT NOT NULL DEFAULT '',
          notion_page_url TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'pending',
          failure_reason TEXT NOT NULL DEFAULT '',
          verified_notion_user_id TEXT NOT NULL DEFAULT '',
          verified_notion_email TEXT NOT NULL DEFAULT '',
          verification_nonce TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          expires_at TEXT NOT NULL,
          verified_at TEXT
        );
        CREATE INDEX idx_notion_identity_claims_status_expires
          ON notion_identity_claims (status, expires_at);
        INSERT INTO notion_identity_claims
          (claim_id, agent_id, unix_user, claimed_notion_email, notion_page_id, verification_nonce, created_at, updated_at, expires_at)
          VALUES ('claim_1', 'ag_1', 'svc_a', 'a@example.com', 'page_1', 'nonce_xyz', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', '2026-02-01T00:00:00+00:00');
        """
    )
    conn.commit()


def test_migration_rebuilds_are_atomic_idempotent_and_index_preserving_on_populated_db() -> None:
    # conc/integrity (deploy-blocking): the FIVE *__new rebuild migrations must be
    # atomic (a crash mid-rebuild rolls back to the original), index-preserving (the
    # live index survives a SINGLE ensure_schema pass -- not deferred to a later one),
    # row-preserving, and a clean no-op on the second pass with no __new scratch left.
    mod = load_module(CONTROL_PY, "arclink_control_db_migration_atomic_test")
    tmp = tempfile.TemporaryDirectory()
    try:
        db_path = str(Path(tmp.name) / "legacy_migrations.sqlite3")

        # --- Crash-safety probe FIRST, on a fresh populated copy: simulate a worker
        # crash mid-rebuild (after DROP old, before RENAME __new) and prove the
        # original table + index + rows are intact (the BEGIN IMMEDIATE rolled back).
        crash_conn = sqlite3.connect(db_path)
        crash_conn.row_factory = sqlite3.Row
        _seed_legacy_migration_db(crash_conn)
        legacy_rollout_sql = _table_sql(crash_conn, "arclink_rollouts")
        expect("'running'" in legacy_rollout_sql, "precondition: legacy rollouts CHECK has 'running'")

        class _BoomAfterDrop:
            def __init__(self, real: sqlite3.Connection) -> None:
                self._real = real

            def __getattr__(self, name: str):
                return getattr(self._real, name)

            @property
            def in_transaction(self) -> bool:
                return self._real.in_transaction

            def execute(self, sql: str, *args):
                cur = self._real.execute(sql, *args)
                if sql.strip().upper().startswith("DROP TABLE ARCLINK_ROLLOUTS"):
                    # Crash AFTER the old table is dropped but BEFORE the RENAME lands.
                    raise RuntimeError("simulated worker crash mid-rebuild")
                return cur

        crashed = False
        try:
            mod._migrate_arclink_rollouts_status_schema(_BoomAfterDrop(crash_conn))
        except RuntimeError as exc:
            crashed = "simulated worker crash" in str(exc)
        expect(crashed, "crash injection must propagate (rebuild must not swallow it)")
        # The whole rebuild rolled back: original table + index + rows are intact.
        expect(
            _table_sql(crash_conn, "arclink_rollouts") == legacy_rollout_sql,
            "a crash mid-rebuild must roll back to the ORIGINAL rollouts table",
        )
        expect(
            "idx_arclink_rollouts_deployment_status" in _indexes_on(crash_conn, "arclink_rollouts"),
            "original index must survive a rolled-back rebuild",
        )
        rows = crash_conn.execute("SELECT COUNT(*) AS c FROM arclink_rollouts").fetchone()["c"]
        expect(int(rows) == 2, f"rows must survive a rolled-back rebuild, got {rows}")
        expect(_scratch_tables(crash_conn) == [], "no __new scratch may survive a rolled-back rebuild")
        crash_conn.close()

        # Fresh populated DB for the full ensure_schema pass.
        Path(db_path).unlink()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        _seed_legacy_migration_db(conn)

        # --- ONE ensure_schema pass migrates all five.
        mod.ensure_schema(conn)

        checks = [
            ("arclink_fleet_enrollments", "idx_arclink_fleet_enrollments_status_expiry", "'consumed'", 2),
            ("arclink_fleet_host_probes", "idx_arclink_fleet_host_probes_host_kind_time", "ok INTEGER", 2),
            ("arclink_fleet_audit_chain", "idx_arclink_fleet_audit_chain_inventory_time", "event_at", 2),
            ("arclink_rollouts", "idx_arclink_rollouts_deployment_status", "'in_progress'", 2),
            ("notion_identity_claims", "idx_notion_identity_claims_status_expires", "claim_id", 1),
        ]
        for table, index_name, schema_marker, expected_rows in checks:
            sql = _table_sql(conn, table)
            expect(schema_marker in sql, f"{table} must have new schema marker {schema_marker!r} after one pass")
            expect(
                index_name in _indexes_on(conn, table),
                f"{table} must retain index {index_name} after a SINGLE ensure_schema pass",
            )
            count = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
            expect(int(count) == expected_rows, f"{table} rows must be preserved: {count} != {expected_rows}")

        # New status/kind CHECKs really hold (legacy values were normalized).
        statuses = sorted(str(r["status"]) for r in conn.execute("SELECT status FROM arclink_fleet_enrollments").fetchall())
        expect(statuses == ["consumed", "pending"], f"enrollment statuses normalized: {statuses}")
        rollout_statuses = sorted(str(r["status"]) for r in conn.execute("SELECT status FROM arclink_rollouts").fetchall())
        expect(rollout_statuses == ["completed", "in_progress"], f"rollout statuses normalized: {rollout_statuses}")
        # verification_nonce removed.
        notion_cols = {r[1] for r in conn.execute("PRAGMA table_info(notion_identity_claims)").fetchall()}
        expect("verification_nonce" not in notion_cols, "notion legacy nonce column removed")
        # No __new scratch left behind.
        expect(_scratch_tables(conn) == [], f"no __new scratch after first pass: {_scratch_tables(conn)}")

        # --- SECOND pass is a clean no-op (guards short-circuit; concurrency re-check).
        before = {t: _table_sql(conn, t) for t, *_ in checks}
        mod.ensure_schema(conn)
        for table, *_ in checks:
            expect(_table_sql(conn, table) == before[table], f"{table} schema must be unchanged on 2nd pass")
        expect(_scratch_tables(conn) == [], "no __new scratch after idempotent 2nd pass")
        conn.close()

        # --- Durability + a SIMULATED concurrent pass: a fresh connection (a second
        # worker) runs ensure_schema again -> still a no-op, schema committed.
        conn2 = sqlite3.connect(db_path)
        conn2.row_factory = sqlite3.Row
        for table, index_name, schema_marker, expected_rows in checks:
            expect(schema_marker in _table_sql(conn2, table), f"{table} schema durable after reopen")
            expect(index_name in _indexes_on(conn2, table), f"{table} index durable after reopen")
        mod.ensure_schema(conn2)
        expect(_scratch_tables(conn2) == [], "second worker pass leaves no __new scratch")
        conn2.close()
    finally:
        tmp.cleanup()
    print("PASS test_migration_rebuilds_are_atomic_idempotent_and_index_preserving_on_populated_db")


def test_transition_provisioning_job_cas_rejects_double_claim() -> None:
    # conc-C2: two sovereign workers must not both move one 'queued' job to 'running'
    # and double-execute. The guarded CAS lets exactly ONE claim win; the loser gets
    # a False ("lost claim") return so the caller SKIPS.
    mod = load_module(CONTROL_PY, "arclink_control_db_job_cas_test")
    conn = memory_db(mod)
    try:
        mod.create_arclink_provisioning_job(
            conn, job_id="job_cas", deployment_id="dep_1", job_kind="apply"
        )

        first = mod.transition_arclink_provisioning_job(conn, job_id="job_cas", status="running")
        expect(first is True, "first queued->running claim must succeed")

        # A second worker that still believes the job is 'queued' attempts the SAME
        # transition. The CAS guard (status IN allowed-from) matches 0 rows because the
        # row is already 'running' -> lost claim, returns False, does NOT re-run apply.
        second = mod.transition_arclink_provisioning_job(conn, job_id="job_cas", status="running")
        expect(second is False, "double queued->running claim must be reported lost (False)")

        # attempt_count incremented exactly once (no double execution side effect).
        attempts = conn.execute(
            "SELECT attempt_count FROM arclink_provisioning_jobs WHERE job_id = ?", ("job_cas",)
        ).fetchone()["attempt_count"]
        expect(int(attempts) == 1, f"attempt_count must increment exactly once, got {attempts}")

        # A genuine forward transition from the real current state still works.
        done = mod.transition_arclink_provisioning_job(conn, job_id="job_cas", status="succeeded")
        expect(done is True, "running->succeeded must succeed")
        # A structurally invalid transition from the observed status still raises.
        raised = False
        try:
            mod.transition_arclink_provisioning_job(conn, job_id="job_cas", status="running")
        except ValueError:
            raised = True
        expect(raised, "succeeded->running is structurally invalid and must raise")
        # Missing job still raises KeyError.
        missing = False
        try:
            mod.transition_arclink_provisioning_job(conn, job_id="nope", status="running")
        except KeyError:
            missing = True
        expect(missing, "unknown job_id must raise KeyError")
    finally:
        conn.close()
    print("PASS test_transition_provisioning_job_cas_rejects_double_claim")


def test_comp_subscription_double_comp_is_prevented() -> None:
    # conc-M3: a partial UNIQUE index on arclink_audit_log(action, target_id) WHERE
    # action='comp_subscription' makes a SECOND comp INSERT for the same target a hard
    # IntegrityError; comp_arclink_subscription treats it as "already comped" -> never
    # two comp audit rows for one user.
    mod = load_module(CONTROL_PY, "arclink_control_db_double_comp_test")
    conn = memory_db(mod)
    try:
        mod.upsert_arclink_user(conn, user_id="u_comp", entitlement_state="none")

        first = mod.comp_arclink_subscription(
            conn, user_id="u_comp", actor_id="admin", reason="goodwill"
        )
        expect(str(first.get("entitlement_state")) == "comp", "first comp must set entitlement to comp")

        # A concurrent/duplicate comp call must be a safe no-op (already comped).
        second = mod.comp_arclink_subscription(
            conn, user_id="u_comp", actor_id="admin2", reason="goodwill again"
        )
        expect(second is not None, "duplicate comp must return the existing user, not crash")

        comp_rows = conn.execute(
            "SELECT COUNT(*) AS c FROM arclink_audit_log WHERE action = 'comp_subscription' AND target_id = ?",
            ("u_comp",),
        ).fetchone()["c"]
        expect(int(comp_rows) == 1, f"exactly one comp audit row may exist, got {comp_rows}")

        # The UNIQUE index itself rejects a raw second insert (the DB-level guarantee).
        rejected = False
        try:
            mod.append_arclink_audit(
                conn,
                action="comp_subscription",
                actor_id="rogue",
                target_kind="user",
                target_id="u_comp",
                reason="dupe",
            )
        except sqlite3.IntegrityError:
            rejected = True
        conn.rollback()
        expect(rejected, "the partial UNIQUE index must reject a second comp row at the DB layer")
    finally:
        conn.close()
    print("PASS test_comp_subscription_double_comp_is_prevented")


def test_stale_subscription_and_entitlement_events_do_not_overwrite_newer() -> None:
    # billing-C2: out-of-order Stripe deliveries must apply MONOTONICALLY. A NEWER
    # event lands; a later-delivered but OLDER event (smaller event.created) is dropped
    # and must not revert status/entitlement.
    mod = load_module(CONTROL_PY, "arclink_control_db_event_ordering_test")
    conn = memory_db(mod)
    try:
        mod.upsert_arclink_user(conn, user_id="u_evt", entitlement_state="none")

        # --- Subscription mirror monotonicity.
        # Newer event (created=2000) applies 'active'.
        mod.upsert_arclink_subscription_mirror(
            conn, subscription_id="sub_1", user_id="u_evt", status="active", event_at=2000
        )
        # Stale event (created=1000) delivered LATER tries to set 'canceled' -> dropped.
        mod.upsert_arclink_subscription_mirror(
            conn, subscription_id="sub_1", user_id="u_evt", status="canceled", event_at=1000
        )
        sub_status = conn.execute(
            "SELECT status FROM arclink_subscriptions WHERE subscription_id = ?", ("sub_1",)
        ).fetchone()["status"]
        expect(sub_status == "active", f"stale subscription event must not overwrite newer: {sub_status}")
        # A genuinely newer event (created=3000) still applies.
        mod.upsert_arclink_subscription_mirror(
            conn, subscription_id="sub_1", user_id="u_evt", status="past_due", event_at=3000
        )
        sub_status2 = conn.execute(
            "SELECT status FROM arclink_subscriptions WHERE subscription_id = ?", ("sub_1",)
        ).fetchone()["status"]
        expect(sub_status2 == "past_due", f"a newer subscription event must apply: {sub_status2}")

        # --- Entitlement monotonicity (ISO-string ordering keys also supported).
        mod.set_arclink_user_entitlement(
            conn, user_id="u_evt", entitlement_state="paid", event_at="2026-02-01T00:00:00+00:00"
        )
        # Stale event (earlier ISO) tries to revert to 'none' -> dropped.
        mod.set_arclink_user_entitlement(
            conn, user_id="u_evt", entitlement_state="none", event_at="2026-01-01T00:00:00+00:00"
        )
        ent = conn.execute(
            "SELECT entitlement_state FROM arclink_users WHERE user_id = ?", ("u_evt",)
        ).fetchone()["entitlement_state"]
        expect(ent == "paid", f"stale entitlement event must not revert newer paid state: {ent}")
        # A newer event applies.
        mod.set_arclink_user_entitlement(
            conn, user_id="u_evt", entitlement_state="comp", event_at="2026-03-01T00:00:00+00:00"
        )
        ent2 = conn.execute(
            "SELECT entitlement_state FROM arclink_users WHERE user_id = ?", ("u_evt",)
        ).fetchone()["entitlement_state"]
        expect(ent2 == "comp", f"a newer entitlement event must apply: {ent2}")

        # Backward compatibility: with no event_at the write applies unconditionally.
        mod.set_arclink_user_entitlement(conn, user_id="u_evt", entitlement_state="paid")
        ent3 = conn.execute(
            "SELECT entitlement_state FROM arclink_users WHERE user_id = ?", ("u_evt",)
        ).fetchone()["entitlement_state"]
        expect(ent3 == "paid", "an unordered (no event_at) write must apply unconditionally")
    finally:
        conn.close()
    print("PASS test_stale_subscription_and_entitlement_events_do_not_overwrite_newer")


if __name__ == "__main__":
    test_config_loader_preserves_multi_token_values_and_export_prefix()
    test_explicit_missing_config_file_fails_loudly_but_devnull_remains_sentinel()
    test_config_from_env_defaults_invalid_int_values_without_crashing()
    test_config_model_presets_are_deeply_immutable()
    test_connect_db_tolerates_locked_journal_mode_pragma()
    test_operation_idempotency_reserve_complete_and_replay()
    test_event_and_notification_json_reject_plaintext_secrets()
    test_expire_stale_ssot_pending_writes_skips_write_when_nothing_due()
    test_legacy_onboarding_token_migration_ignores_uncontained_stored_path()
    test_parse_utc_iso_normalizes_z_and_offset_timestamps()
    test_operation_idempotency_rejects_same_key_different_intent()
    test_operation_idempotency_failed_attempt_replays_without_completion()
    test_notification_errors_backoff_and_due_fetch_skips_future_rows()
    test_notification_retry_backoff_jitters_by_notification_id()
    test_operation_idempotency_persists_across_restart()
    test_upsert_user_preserves_protected_status_without_privileged_transition()
    test_email_merge_is_deterministic_and_repoints_owned_rows()
    test_wave4_schema_indexes_exist_and_totp_active_factor_is_unique()
    test_wave4_status_checks_and_relationship_drift_are_reported()
    test_wave4_fresh_schema_rejects_invalid_high_value_status()
    test_mark_notification_error_does_not_clobber_delivered_row()
    test_operator_hiccup_arm_resolve_is_atomic_and_single_outcome()
    test_llm_router_key_hash_pepper_fails_closed_outside_local_dev()
    test_verify_llm_router_key_migrates_legacy_hash_and_throttles_last_seen()
    test_upsert_model_catalog_commit_false_folds_into_caller_txn()
    test_llm_budget_reservations_legacy_check_migrates_to_expired_with_heartbeat()
    test_llm_budget_reservations_rebuild_is_atomic_and_keeps_index_on_first_pass()
    test_operator_action_secret_at_rest_is_rejected_and_hiccup_message_redacted()
    test_migration_rebuilds_are_atomic_idempotent_and_index_preserving_on_populated_db()
    test_transition_provisioning_job_cas_rejects_double_claim()
    test_comp_subscription_double_comp_is_prevented()
    test_stale_subscription_and_entitlement_events_do_not_overwrite_newer()
