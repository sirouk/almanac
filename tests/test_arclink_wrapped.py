#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
CONTROL_PY = PYTHON_DIR / "arclink_control.py"
WRAPPED_PY = PYTHON_DIR / "arclink_wrapped.py"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_module(path: Path, name: str):
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def memory_db() -> sqlite3.Connection:
    control = load_module(CONTROL_PY, "arclink_control_wrapped_test")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    control.ensure_schema(conn)
    return conn


def seed_wrapped_fixture(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """
        INSERT INTO arclink_users (
          user_id, email, display_name, agent_title, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'active', ?, ?)
        """,
        [
            ("user_1", "captain@example.test", "Captain One", "Lead Agent", "2026-05-01T00:00:00+00:00", "2026-05-01T00:00:00+00:00"),
            ("user_2", "other@example.test", "Captain Two", "Other Agent", "2026-05-01T00:00:00+00:00", "2026-05-01T00:00:00+00:00"),
        ],
    )
    conn.executemany(
        """
        INSERT INTO arclink_deployments (
          deployment_id, user_id, prefix, agent_name, agent_title, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("dep_a", "user_1", "alpha", "Aster", "Research Agent", "active", "2026-05-01T00:00:00+00:00", "2026-05-01T00:00:00+00:00"),
            ("dep_b", "user_1", "beta", "Beryl", "Comms Agent", "active", "2026-05-01T00:00:00+00:00", "2026-05-01T00:00:00+00:00"),
            ("dep_other", "user_2", "other", "Other", "Other Agent", "active", "2026-05-01T00:00:00+00:00", "2026-05-01T00:00:00+00:00"),
        ],
    )
    conn.execute(
        """
        INSERT INTO arclink_onboarding_sessions (
          session_id, channel, channel_identity, status, current_step,
          email_hint, display_name_hint, agent_name, agent_title,
          selected_plan_id, selected_model_id, user_id, deployment_id,
          checkout_state, metadata_json, created_at, updated_at, completed_at
        ) VALUES (
          'sess_1', 'telegram', 'tg:42', 'completed', 'done',
          'captain@example.test', 'Captain One', 'Aster', 'Research Agent',
          'sovereign', 'moonshotai/Kimi-K2.6-TEE', 'user_1', 'dep_a',
          'paid', '{}', '2026-05-01T00:00:00+00:00',
          '2026-05-01T00:00:00+00:00', '2026-05-01T00:00:00+00:00'
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO arclink_events (
          event_id, subject_kind, subject_id, event_type, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            ("evt_1", "user", "user_1", "agent_identity_updated", '{"note":"captain renamed Agent"}', "2026-05-12T01:00:00+00:00"),
            ("evt_2", "deployment", "dep_a", "pod_message_sent", '{"detail":"safe"}', "2026-05-12T02:00:00+00:00"),
            ("evt_old", "deployment", "dep_a", "outside_period", "{}", "2026-05-10T02:00:00+00:00"),
            ("evt_other", "deployment", "dep_other", "other_user", "{}", "2026-05-12T02:00:00+00:00"),
        ],
    )
    conn.executemany(
        """
        INSERT INTO arclink_audit_log (
          audit_id, actor_id, action, target_kind, target_id, reason, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "aud_1",
                "user_1",
                "crew_recipe_applied",
                "user",
                "user_1",
                "Captain applied recipe with token=sk-proj-abcdefghijklmnopqrstuvwxyz",
                "{}",
                "2026-05-12T03:00:00+00:00",
            ),
            ("aud_2", "admin", "dns_repair", "deployment", "dep_a", "Repair check", "{}", "2026-05-12T04:00:00+00:00"),
            ("aud_other", "user_2", "other", "user", "user_2", "Other user", "{}", "2026-05-12T04:00:00+00:00"),
        ],
    )
    conn.executemany(
        """
        INSERT INTO arclink_pod_messages (
          message_id, sender_deployment_id, recipient_deployment_id, sender_user_id,
          recipient_user_id, body, status, created_at, delivered_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "msg_1",
                "dep_a",
                "dep_b",
                "user_1",
                "user_1",
                "Shared plan with password=hunter2",
                "delivered",
                "2026-05-12T05:00:00+00:00",
                "2026-05-12T05:01:00+00:00",
            ),
            ("msg_2", "dep_b", "dep_a", "user_1", "user_1", "Reply", "queued", "2026-05-12T06:00:00+00:00", ""),
            ("msg_cross", "dep_a", "dep_other", "user_1", "user_2", "Do not leak", "delivered", "2026-05-12T07:00:00+00:00", ""),
        ],
    )
    conn.executemany(
        """
        INSERT INTO memory_synthesis_cards (
          card_id, source_kind, source_key, source_title, source_signature,
          prompt_version, model, status, card_json, card_text, source_count,
          token_estimate, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'ok', ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "card_1",
                "vault",
                "dep_a/research.md",
                "Research",
                "sig1",
                "v1",
                "test",
                '{"user_id":"user_1","deployment_id":"dep_a","theme":"new customers"}',
                "Memory card mentions whsec_abcdefghijklmnopqrstuvwxyz",
                3,
                111,
                "2026-05-12T08:00:00+00:00",
                "2026-05-12T08:00:00+00:00",
            ),
            (
                "card_other",
                "vault",
                "dep_other/research.md",
                "Other",
                "sig2",
                "v1",
                "test",
                '{"user_id":"user_2","deployment_id":"dep_other"}',
                "Other card",
                1,
                50,
                "2026-05-12T08:00:00+00:00",
                "2026-05-12T08:00:00+00:00",
            ),
        ],
    )
    conn.commit()


def test_generate_wrapped_report_is_scoped_redacted_and_persisted() -> None:
    wrapped = load_module(WRAPPED_PY, "arclink_wrapped_test_core")
    conn = memory_db()
    seed_wrapped_fixture(conn)

    def session_counts(**kwargs):
        expect(kwargs["user_id"] == "user_1", str(kwargs))
        expect(kwargs["deployment_ids"] == ["dep_a", "dep_b"], str(kwargs))
        return {"session_count": 4, "turn_count": 9}

    def vault_deltas(**kwargs):
        expect(kwargs["user_id"] == "user_1", str(kwargs))
        return {
            "files_added": 2,
            "files_updated": 3,
            "files_deleted": 1,
            "sample": ["api_key=sk-ant-abcdefghijklmnopqrstuvwxyz"],
        }

    report = wrapped.generate_wrapped_report(
        conn,
        "user_1",
        "daily",
        "2026-05-12T00:00:00+00:00",
        "2026-05-13T00:00:00+00:00",
        session_counter=session_counts,
        vault_delta_reader=vault_deltas,
        report_id="wrap_fixed",
        created_at="2026-05-13T00:05:00+00:00",
    )
    expect(report["report_id"] == "wrap_fixed", str(report))
    expect(report["status"] == "generated", str(report))
    expect(report["novelty_score"] > 0, str(report))
    expect(len(report["stats"]) >= 5, str(report["stats"]))
    dumped = json.dumps(report, sort_keys=True)
    for forbidden in (
        "sk-proj-abcdefghijklmnopqrstuvwxyz",
        "hunter2",
        "whsec_abcdefghijklmnopqrstuvwxyz",
        "sk-ant-abcdefghijklmnopqrstuvwxyz",
        "Do not leak",
        "other_user",
    ):
        expect(forbidden not in dumped, forbidden)
    row = conn.execute("SELECT * FROM arclink_wrapped_reports WHERE report_id = 'wrap_fixed'").fetchone()
    expect(row is not None, "missing persisted report")
    ledger = json.loads(row["ledger_json"])
    ledger_dumped = json.dumps(ledger, sort_keys=True)
    expect("[REDACTED]" in ledger_dumped or "***" in ledger_dumped, ledger_dumped)
    expect(ledger["markdown"] == report["markdown"], str(ledger))
    expect(ledger["plain_text"] == report["plain_text"], str(ledger))
    expect(len(ledger["source_counts"]) >= 5, str(ledger))
    print("PASS test_generate_wrapped_report_is_scoped_redacted_and_persisted")


def test_wrapped_report_score_is_deterministic_for_same_inputs() -> None:
    wrapped = load_module(WRAPPED_PY, "arclink_wrapped_test_deterministic")
    conn = memory_db()
    seed_wrapped_fixture(conn)
    kwargs = {
        "session_counter": lambda **_: {"session_count": 2, "turn_count": 5},
        "vault_delta_reader": lambda **_: {"files_added": 1, "files_updated": 1, "files_deleted": 0},
        "created_at": "2026-05-13T00:05:00+00:00",
    }
    one = wrapped.generate_wrapped_report(
        conn,
        "user_1",
        "daily",
        "2026-05-12T00:00:00+00:00",
        "2026-05-13T00:00:00+00:00",
        report_id="wrap_one",
        **kwargs,
    )
    two = wrapped.generate_wrapped_report(
        conn,
        "user_1",
        "daily",
        "2026-05-12T00:00:00+00:00",
        "2026-05-13T00:00:00+00:00",
        report_id="wrap_two",
        **kwargs,
    )
    expect(one["novelty_score"] == two["novelty_score"], f"{one['novelty_score']} != {two['novelty_score']}")
    expect(one["stats"] == two["stats"], f"{one['stats']} != {two['stats']}")
    expect(one["markdown"].replace("wrap_one", "") == two["markdown"].replace("wrap_two", ""), "markdown drifted")
    print("PASS test_wrapped_report_score_is_deterministic_for_same_inputs")


def test_wrapped_frequency_periods_due_and_admin_privacy() -> None:
    wrapped = load_module(WRAPPED_PY, "arclink_wrapped_test_helpers")
    conn = memory_db()
    seed_wrapped_fixture(conn)
    expect(wrapped.normalize_wrapped_frequency("") == "daily", "blank should default daily")
    expect(wrapped.normalize_wrapped_frequency(" Weekly ") == "weekly", "weekly normalization failed")
    try:
        wrapped.normalize_wrapped_frequency("hourly")
    except ValueError as exc:
        expect("unsupported ArcLink Wrapped frequency" in str(exc), str(exc))
    else:
        raise AssertionError("hourly frequency should be rejected")

    start, end = wrapped.resolve_wrapped_period("daily", now="2026-05-14T12:00:00+00:00")
    expect(start == "2026-05-13T00:00:00+00:00", start)
    expect(end == "2026-05-14T00:00:00+00:00", end)
    conn.execute(
        """
        INSERT INTO arclink_wrapped_reports (
          report_id, user_id, period, period_start, period_end, status,
          ledger_json, novelty_score, created_at
        ) VALUES (
          'wrap_failed', 'user_1', 'daily', ?, ?, 'failed',
          '{"plain_text":"Captain narrative must stay private","markdown":"# Private"}', 44.4, ?
        )
        """,
        (start, end, end),
    )
    conn.commit()
    due = wrapped.list_due_wrapped_captains(conn, now="2026-05-14T12:00:00+00:00")
    user_due = [row for row in due if row["user_id"] == "user_1"]
    expect(user_due and user_due[0]["due_reason"] == "failed_retry", str(due))
    aggregate = wrapped.wrapped_admin_aggregate(conn, now="2026-05-14T12:00:00+00:00")
    dumped = json.dumps(aggregate, sort_keys=True)
    expect("Captain narrative must stay private" not in dumped, dumped)
    expect("markdown" not in dumped and "plain_text" not in dumped, dumped)
    expect(aggregate["reports_by_status"]["failed"] == 1, str(aggregate))
    print("PASS test_wrapped_frequency_periods_due_and_admin_privacy")


def test_wrapped_delivery_queue_respects_quiet_hours_and_marks_cadence() -> None:
    wrapped = load_module(WRAPPED_PY, "arclink_wrapped_test_delivery")
    conn = memory_db()
    seed_wrapped_fixture(conn)
    updated = wrapped.set_wrapped_frequency(
        conn,
        "user_1",
        "monthly",
        actor_id="user_1",
        reason="Captain selected monthly Wrapped",
        now="2026-05-13T20:00:00+00:00",
    )
    expect(updated["wrapped_frequency"] == "monthly", str(dict(updated)))
    audit = conn.execute(
        "SELECT action, metadata_json FROM arclink_audit_log WHERE action = 'wrapped_frequency_updated'"
    ).fetchone()
    expect(audit is not None, "missing wrapped frequency audit")
    report = wrapped.generate_wrapped_report(
        conn,
        "user_1",
        "daily",
        "2026-05-12T00:00:00+00:00",
        "2026-05-13T00:00:00+00:00",
        session_counter=lambda **_: {"session_count": 1, "turn_count": 2},
        vault_delta_reader=lambda **_: {"files_added": 1},
        report_id="wrap_delivery",
        created_at="2026-05-13T20:05:00+00:00",
    )
    notification_id = wrapped.enqueue_wrapped_report_notification(
        conn,
        report["report_id"],
        now="2026-05-13T23:15:00+00:00",
        quiet_hours="22:00-08:00",
    )
    outbox = conn.execute("SELECT * FROM notification_outbox WHERE id = ?", (notification_id,)).fetchone()
    expect(outbox["target_kind"] == "captain-wrapped", str(dict(outbox)))
    expect(outbox["target_id"] == "tg:42", str(dict(outbox)))
    expect(outbox["channel_kind"] == "telegram", str(dict(outbox)))
    expect(outbox["next_attempt_at"] == "2026-05-14T08:00:00+00:00", str(dict(outbox)))
    extra = json.loads(outbox["extra_json"])
    expect(extra["report_id"] == "wrap_delivery", str(extra))
    expect("plain_text" not in extra and "markdown" not in extra, str(extra))
    persisted = conn.execute("SELECT delivery_channel FROM arclink_wrapped_reports WHERE report_id = 'wrap_delivery'").fetchone()
    expect(persisted["delivery_channel"] == "telegram", str(dict(persisted)))
    print("PASS test_wrapped_delivery_queue_respects_quiet_hours_and_marks_cadence")


def test_wrapped_scheduler_retries_failures_and_notifies_operator_after_persistent_failure() -> None:
    wrapped = load_module(WRAPPED_PY, "arclink_wrapped_test_scheduler")
    conn = memory_db()
    seed_wrapped_fixture(conn)
    conn.execute("UPDATE arclink_users SET status = 'suspended' WHERE user_id = 'user_2'")
    conn.commit()

    def broken_counter(**_kwargs):
        raise RuntimeError("provider token=sk-proj-abcdefghijklmnopqrstuvwxyz unavailable")

    for _ in range(3):
        summary = wrapped.run_wrapped_scheduler_once(
            conn,
            now="2026-05-14T12:00:00+00:00",
            session_counter=broken_counter,
        )
    expect(summary["failed"] == 1, str(summary))
    failures = conn.execute(
        "SELECT COUNT(*) AS count FROM arclink_wrapped_reports WHERE user_id = 'user_1' AND status = 'failed'"
    ).fetchone()["count"]
    expect(failures == 3, str(failures))
    operator = conn.execute(
        "SELECT message, extra_json FROM notification_outbox WHERE target_kind = 'operator' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    expect(operator is not None, "persistent failure should notify operator")
    dumped = json.dumps(dict(operator), sort_keys=True)
    expect("sk-proj-abcdefghijklmnopqrstuvwxyz" not in dumped, dumped)
    expect("plain_text" not in dumped and "markdown" not in dumped, dumped)
    print("PASS test_wrapped_scheduler_retries_failures_and_notifies_operator_after_persistent_failure")


def main() -> int:
    test_generate_wrapped_report_is_scoped_redacted_and_persisted()
    test_wrapped_report_score_is_deterministic_for_same_inputs()
    test_wrapped_frequency_periods_due_and_admin_privacy()
    test_wrapped_delivery_queue_respects_quiet_hours_and_marks_cadence()
    test_wrapped_scheduler_retries_failures_and_notifies_operator_after_persistent_failure()
    print("PASS all 5 ArcLink Wrapped tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
