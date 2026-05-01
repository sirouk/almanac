#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"


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


def memory_db(control):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    control.ensure_schema(conn)
    return conn


def test_admin_action_requires_reason_and_queues_audited_intent() -> None:
    control = load_module("almanac_control.py", "almanac_control_admin_action_reason_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_admin_action_reason_test")
    conn = memory_db(control)
    try:
        dashboard.queue_arclink_admin_action(
            conn,
            admin_id="admin_1",
            action_type="restart",
            target_kind="deployment",
            target_id="dep_1",
            reason="",
            idempotency_key="restart-1",
        )
    except dashboard.ArcLinkDashboardError as exc:
        expect("reason" in str(exc), str(exc))
    else:
        raise AssertionError("expected reasonless admin action to fail")

    action = dashboard.queue_arclink_admin_action(
        conn,
        admin_id="admin_1",
        action_type="restart",
        target_kind="deployment",
        target_id="dep_1",
        reason="operator requested restart",
        idempotency_key="restart-1",
        metadata={"source": "admin_dashboard"},
    )
    expect(action["status"] == "queued", str(action))
    expect(action["audit_id"], str(action))
    audits = conn.execute("SELECT * FROM arclink_audit_log WHERE target_id = 'dep_1'").fetchall()
    expect(len(audits) == 1, str([dict(row) for row in audits]))
    expect(audits[0]["action"] == "admin_action:restart", str(dict(audits[0])))
    print("PASS test_admin_action_requires_reason_and_queues_audited_intent")


def test_admin_action_idempotency_reuses_intent_without_duplicate_audit() -> None:
    control = load_module("almanac_control.py", "almanac_control_admin_action_idempotency_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_admin_action_idempotency_test")
    conn = memory_db(control)
    first = dashboard.queue_arclink_admin_action(
        conn,
        admin_id="admin_1",
        action_type="dns_repair",
        target_kind="deployment",
        target_id="dep_1",
        reason="repair recorded DNS drift",
        idempotency_key="dns-repair-1",
    )
    second = dashboard.queue_arclink_admin_action(
        conn,
        admin_id="admin_1",
        action_type="dns_repair",
        target_kind="deployment",
        target_id="dep_1",
        reason="repair recorded DNS drift",
        idempotency_key="dns-repair-1",
    )
    expect(first["action_id"] == second["action_id"], str((first, second)))
    audit_count = conn.execute("SELECT COUNT(*) AS n FROM arclink_audit_log").fetchone()["n"]
    expect(audit_count == 1, str(audit_count))
    try:
        dashboard.queue_arclink_admin_action(
            conn,
            admin_id="admin_1",
            action_type="restart",
            target_kind="deployment",
            target_id="dep_1",
            reason="different action with reused key",
            idempotency_key="dns-repair-1",
        )
    except dashboard.ArcLinkDashboardError as exc:
        expect("idempotency" in str(exc), str(exc))
    else:
        raise AssertionError("expected conflicting idempotency key to fail")
    print("PASS test_admin_action_idempotency_reuses_intent_without_duplicate_audit")


def test_admin_action_metadata_rejects_plaintext_secrets_and_has_no_live_side_effects() -> None:
    control = load_module("almanac_control.py", "almanac_control_admin_action_secret_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_admin_action_secret_test")
    conn = memory_db(control)
    try:
        dashboard.queue_arclink_admin_action(
            conn,
            admin_id="admin_1",
            action_type="rotate_chutes_key",
            target_kind="deployment",
            target_id="dep_1",
            reason="rotate leaked test fixture",
            idempotency_key="rotate-1",
            metadata={"provider_api_key": "sk_test_plaintext"},
        )
    except dashboard.ArcLinkDashboardError as exc:
        expect("secret material" in str(exc), str(exc))
    else:
        raise AssertionError("expected plaintext metadata secret to fail")
    expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"] == 0, "unexpected action")

    action = dashboard.queue_arclink_admin_action(
        conn,
        admin_id="admin_1",
        action_type="rotate_chutes_key",
        target_kind="deployment",
        target_id="dep_1",
        reason="rotate provider key through executor later",
        idempotency_key="rotate-2",
        metadata={"provider_api_key_ref": "secret://arclink/provider/dep_1"},
    )
    rendered = json.dumps(dict(action), sort_keys=True)
    expect("sk_test" not in rendered and "secret://" in rendered, rendered)
    expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_provisioning_jobs").fetchone()["n"] == 0, "live job was created")
    expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_dns_records").fetchone()["n"] == 0, "DNS was mutated")
    print("PASS test_admin_action_metadata_rejects_plaintext_secrets_and_has_no_live_side_effects")


def main() -> int:
    test_admin_action_requires_reason_and_queues_audited_intent()
    test_admin_action_idempotency_reuses_intent_without_duplicate_audit()
    test_admin_action_metadata_rejects_plaintext_secrets_and_has_no_live_side_effects()
    print("PASS all 3 ArcLink admin action tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
