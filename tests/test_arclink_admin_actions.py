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
    control = load_module("arclink_control.py", "arclink_control_admin_action_reason_test")
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
    control = load_module("arclink_control.py", "arclink_control_admin_action_idempotency_test")
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


def test_admin_action_rejects_unwired_action_types() -> None:
    control = load_module("arclink_control.py", "arclink_control_admin_action_unwired_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_admin_action_unwired_test")
    conn = memory_db(control)
    for action_type in ("reprovision", "rollout", "force_resynth", "rotate_bot_key", "suspend", "unsuspend"):
        try:
            dashboard.queue_arclink_admin_action(
                conn,
                admin_id="admin_1",
                action_type=action_type,
                target_kind="deployment",
                target_id=f"dep_{action_type}",
                reason="operator requested unsupported action",
                idempotency_key=f"{action_type}-1",
            )
        except dashboard.ArcLinkDashboardError as exc:
            expect("not queueable" in str(exc), str(exc))
        else:
            raise AssertionError(f"expected {action_type} to be rejected before queueing")
    queued = conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"]
    expect(queued == 0, str(queued))
    print("PASS test_admin_action_rejects_unwired_action_types")


def test_admin_action_metadata_rejects_plaintext_secrets_and_has_no_live_side_effects() -> None:
    control = load_module("arclink_control.py", "arclink_control_admin_action_secret_test")
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


def test_admin_refund_and_cancel_actions_record_audited_notes() -> None:
    control = load_module("arclink_control.py", "arclink_control_admin_refund_cancel_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_admin_refund_cancel_test")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_1", entitlement_state="paid")
    control.reserve_arclink_deployment_prefix(
        conn, deployment_id="dep_1", user_id="user_1",
        prefix="refund-test", status="provisioning_ready",
    )
    # Queue a refund admin action with admin notes
    refund = dashboard.queue_arclink_admin_action(
        conn,
        admin_id="admin_1",
        action_type="refund",
        target_kind="user",
        target_id="user_1",
        reason="customer requested refund for billing error",
        idempotency_key="refund-user1-1",
        metadata={"stripe_customer_ref": "secret://arclink/stripe/customer/user_1", "admin_note": "prorated refund approved"},
    )
    expect(refund["status"] == "queued", str(refund))
    # Queue a cancel admin action
    cancel = dashboard.queue_arclink_admin_action(
        conn,
        admin_id="admin_1",
        action_type="cancel",
        target_kind="user",
        target_id="user_1",
        reason="customer requested subscription cancellation",
        idempotency_key="cancel-user1-1",
        metadata={"admin_note": "immediate cancellation per support ticket #42"},
    )
    expect(cancel["status"] == "queued", str(cancel))
    # Both actions should have audit entries with reasons
    audits = conn.execute(
        "SELECT action, reason FROM arclink_audit_log WHERE target_id = 'user_1' ORDER BY created_at"
    ).fetchall()
    expect(len(audits) == 2, str([dict(r) for r in audits]))
    expect(audits[0]["action"] == "admin_action:refund", str(dict(audits[0])))
    expect("billing error" in audits[0]["reason"], str(dict(audits[0])))
    expect(audits[1]["action"] == "admin_action:cancel", str(dict(audits[1])))
    expect("cancellation" in audits[1]["reason"], str(dict(audits[1])))
    # Action intents store the admin notes in metadata
    intents = conn.execute(
        "SELECT action_type, metadata_json FROM arclink_action_intents WHERE target_id = 'user_1' ORDER BY created_at"
    ).fetchall()
    expect(len(intents) == 2, str([dict(r) for r in intents]))
    refund_meta = json.loads(intents[0]["metadata_json"])
    expect("admin_note" in refund_meta, str(refund_meta))
    expect(refund_meta["admin_note"] == "prorated refund approved", str(refund_meta))
    cancel_meta = json.loads(intents[1]["metadata_json"])
    expect("admin_note" in cancel_meta, str(cancel_meta))
    # No plaintext secrets in stored metadata
    for intent in intents:
        expect("sk_" not in intent["metadata_json"], str(dict(intent)))
    print("PASS test_admin_refund_and_cancel_actions_record_audited_notes")


def test_admin_dashboard_exposes_action_execution_readiness() -> None:
    control = load_module("arclink_control.py", "arclink_control_admin_action_readiness_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_admin_action_readiness_test")
    conn = memory_db(control)
    view = dashboard.read_arclink_admin_dashboard(conn)
    readiness = view["action_execution_readiness"]
    expect(readiness["executable"] == [], str(readiness))
    expect("restart" in readiness["disabled"], str(readiness))
    expect("fail closed" in readiness["note"], str(readiness))

    ready = dashboard.admin_action_execution_readiness(env={"ARCLINK_EXECUTOR_ADAPTER": "fake"})
    expect("restart" in ready["executable"], str(ready))
    expect("dns_repair" in ready["executable"], str(ready))
    expect("comp" in ready["executable"], str(ready))
    expect("rollout" in ready["pending_not_implemented"], str(ready))
    expect("force_resynth" in ready["disabled"], str(ready))
    expect(ready["probes"][0]["ok"] is True, str(ready))
    expect(set(ready["executable"]).isdisjoint(set(ready["pending_not_implemented"])), str(ready))
    ssh_blocked = dashboard.admin_action_execution_readiness(env={"ARCLINK_EXECUTOR_ADAPTER": "ssh"})
    expect(ssh_blocked["executable"] == [], str(ssh_blocked))
    expect(any(probe["name"] == "ssh_key" and not probe["ok"] for probe in ssh_blocked["probes"]), str(ssh_blocked))
    print("PASS test_admin_dashboard_exposes_action_execution_readiness")


def main() -> int:
    test_admin_action_requires_reason_and_queues_audited_intent()
    test_admin_action_idempotency_reuses_intent_without_duplicate_audit()
    test_admin_action_rejects_unwired_action_types()
    test_admin_action_metadata_rejects_plaintext_secrets_and_has_no_live_side_effects()
    test_admin_refund_and_cancel_actions_record_audited_notes()
    test_admin_dashboard_exposes_action_execution_readiness()
    print("PASS all 6 ArcLink admin action tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
