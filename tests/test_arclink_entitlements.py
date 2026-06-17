#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
import tempfile
import threading

from arclink_test_helpers import expect, load_module, memory_db, sign_stripe


def stripe_payload(
    *,
    event_id: str,
    event_type: str,
    user_id: str = "user_1",
    subscription_id: str = "sub_test",
    customer_id: str = "cus_test",
    status: str = "active",
) -> str:
    obj: dict[str, object] = {
        "id": subscription_id,
        "customer": customer_id,
        "status": status,
        "metadata": {"arclink_user_id": user_id},
    }
    if event_type == "checkout.session.completed":
        obj = {
            "id": "cs_test",
            "customer": customer_id,
            "subscription": subscription_id,
            "payment_status": "paid",
            "amount_total": 1000,
            "client_reference_id": user_id,
            "metadata": {"arclink_user_id": user_id},
        }
    if event_type == "invoice.payment_failed":
        obj = {
            "id": "in_test",
            "customer": customer_id,
            "subscription": subscription_id,
            "status": "open",
            "metadata": {"arclink_user_id": user_id},
        }
    if event_type in {"invoice.payment_succeeded", "invoice.paid"}:
        obj = {
            "id": "in_test",
            "customer": customer_id,
            "subscription": subscription_id,
            "status": status,
            "metadata": {"arclink_user_id": user_id},
        }
    return json.dumps({"id": event_id, "type": event_type, "data": {"object": obj}}, sort_keys=True)


def sign(adapters, payload: str) -> str:
    return sign_stripe(adapters, payload)


def test_stripe_webhook_verifier_rejects_blank_secret_and_accepts_fixture() -> None:
    adapters = load_module("arclink_adapters.py", "arclink_adapters_entitlement_verify_test")
    payload = stripe_payload(event_id="evt_verify", event_type="customer.subscription.updated")
    signature = sign(adapters, payload)
    for blank in ("", "   "):
        try:
            adapters.verify_stripe_webhook(payload, signature, blank)
        except adapters.StripeWebhookError as exc:
            expect("secret" in str(exc), str(exc))
        else:
            raise AssertionError("expected blank Stripe webhook secret to fail")
    event = adapters.verify_stripe_webhook(payload, signature, "whsec_test")
    expect(event["id"] == "evt_verify", str(event))
    print("PASS test_stripe_webhook_verifier_rejects_blank_secret_and_accepts_fixture")


def test_stripe_webhook_verifier_accepts_any_matching_v1_signature() -> None:
    adapters = load_module("arclink_adapters.py", "arclink_adapters_entitlement_verify_multi_v1_test")
    payload = stripe_payload(event_id="evt_verify_multi_v1", event_type="customer.subscription.updated")
    timestamp = 1_800_000_000
    good = adapters.sign_stripe_webhook(payload, "whsec_test", timestamp=timestamp).split("v1=", 1)[1]
    bad = adapters.sign_stripe_webhook(payload, "whsec_old", timestamp=timestamp).split("v1=", 1)[1]
    signature = f"t={timestamp},v1={good},v1={bad}"
    event = adapters.verify_stripe_webhook(payload, signature, "whsec_test", tolerance_seconds=10_000_000_000)
    expect(event["id"] == "evt_verify_multi_v1", str(event))
    print("PASS test_stripe_webhook_verifier_accepts_any_matching_v1_signature")


def test_stripe_webhook_rejects_signature_mismatch() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_sig_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_sig_test")
    conn = memory_db(control)
    payload = stripe_payload(event_id="evt_bad_sig", event_type="customer.subscription.updated")
    try:
        entitlements.process_stripe_webhook(conn, payload=payload, signature="t=1,v1=bad", secret="whsec_test")
    except Exception as exc:
        expect("timestamp" in str(exc) or "signature" in str(exc), str(exc))
    else:
        raise AssertionError("expected bad Stripe signature to fail")
    count = conn.execute("SELECT COUNT(*) AS n FROM arclink_webhook_events").fetchone()["n"]
    expect(count == 0, str(count))
    print("PASS test_stripe_webhook_rejects_signature_mismatch")


def test_paid_webhook_is_idempotent_and_lifts_entitlement_gate() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_paid_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_entitlement_paid_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_paid_test")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_1", stripe_customer_id="cus_test", entitlement_state="none")
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_1",
        user_id="user_1",
        prefix="paid-gate",
        status="entitlement_required",
    )
    payload = stripe_payload(event_id="evt_paid", event_type="customer.subscription.updated", status="active")
    result = entitlements.process_stripe_webhook(conn, payload=payload, signature=sign(adapters, payload), secret="whsec_test")
    expect(result.entitlement_state == "paid", str(result))
    expect(result.advanced_deployments == ("dep_1",), str(result))
    row = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = 'user_1'").fetchone()
    expect(row["entitlement_state"] == "paid", str(dict(row)))
    dep = conn.execute("SELECT status FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone()
    expect(dep["status"] == "provisioning_ready", str(dict(dep)))
    events_before = conn.execute("SELECT COUNT(*) AS n FROM arclink_events").fetchone()["n"]
    replay = entitlements.process_stripe_webhook(conn, payload=payload, signature=sign(adapters, payload), secret="whsec_test")
    expect(replay.replayed, str(replay))
    events_after = conn.execute("SELECT COUNT(*) AS n FROM arclink_events").fetchone()["n"]
    expect(events_after == events_before, f"{events_before} -> {events_after}")
    print("PASS test_paid_webhook_is_idempotent_and_lifts_entitlement_gate")


def test_failed_webhook_row_can_be_replayed_after_payload_fix() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_replay_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_entitlement_replay_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_replay_test")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_1", stripe_customer_id="cus_test", entitlement_state="none")
    bad_payload = json.dumps(
        {
            "id": "evt_replay_failed",
            "type": "customer.subscription.updated",
            "data": {"object": {"id": "sub_test", "customer": "cus_replay_missing", "status": "active", "metadata": {}}},
        },
        sort_keys=True,
    )
    try:
        entitlements.process_stripe_webhook(
            conn,
            payload=bad_payload,
            signature=sign(adapters, bad_payload),
            secret="whsec_test",
        )
    except entitlements.ArcLinkEntitlementError as exc:
        expect("user id" in str(exc), str(exc))
    else:
        raise AssertionError("expected webhook without user id to fail")
    failed = conn.execute("SELECT status FROM arclink_webhook_events WHERE event_id = 'evt_replay_failed'").fetchone()
    expect(failed["status"] == "failed", str(dict(failed)))

    fixed_payload = stripe_payload(event_id="evt_replay_failed", event_type="customer.subscription.updated")
    replay = entitlements.process_stripe_webhook(
        conn,
        payload=fixed_payload,
        signature=sign(adapters, fixed_payload),
        secret="whsec_test",
    )
    expect(replay.replayed and replay.entitlement_state == "paid", str(replay))
    row = conn.execute(
        "SELECT status, payload_json FROM arclink_webhook_events WHERE event_id = 'evt_replay_failed'"
    ).fetchone()
    expect(row["status"] == "processed", str(dict(row)))
    expect("arclink_user_id" in row["payload_json"], str(dict(row)))
    print("PASS test_failed_webhook_row_can_be_replayed_after_payload_fix")


def test_received_webhook_row_is_reprocessed_instead_of_silently_acknowledged() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_received_replay_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_entitlement_received_replay_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_received_replay_test")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_received", stripe_customer_id="cus_received", entitlement_state="none")
    payload = stripe_payload(
        event_id="evt_received_replay",
        event_type="customer.subscription.updated",
        user_id="user_received",
        subscription_id="sub_received",
        customer_id="cus_received",
        status="active",
    )
    conn.execute(
        """
        INSERT INTO arclink_webhook_events (provider, event_id, event_type, received_at, status, payload_json)
        VALUES ('stripe', 'evt_received_replay', 'customer.subscription.updated', '2026-05-11T00:00:00+00:00', 'received', ?)
        """,
        (payload,),
    )
    conn.commit()

    replay = entitlements.process_stripe_webhook(
        conn,
        payload=payload,
        signature=sign(adapters, payload),
        secret="whsec_test",
    )

    user = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = 'user_received'").fetchone()
    webhook = conn.execute("SELECT status FROM arclink_webhook_events WHERE event_id = 'evt_received_replay'").fetchone()
    expect(replay.replayed and replay.entitlement_state == "paid", str(replay))
    expect(user["entitlement_state"] == "paid", str(dict(user)))
    expect(webhook["status"] == "processed", str(dict(webhook)))
    print("PASS test_received_webhook_row_is_reprocessed_instead_of_silently_acknowledged")


def test_failed_payment_keeps_gate_blocked_and_audits_reason() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_failed_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_entitlement_failed_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_failed_test")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_1", stripe_customer_id="cus_test", entitlement_state="none")
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_1",
        user_id="user_1",
        prefix="failed-pay",
        status="entitlement_required",
    )
    payload = stripe_payload(event_id="evt_failed", event_type="invoice.payment_failed")
    result = entitlements.process_stripe_webhook(conn, payload=payload, signature=sign(adapters, payload), secret="whsec_test")
    expect(result.entitlement_state == "past_due", str(result))
    dep = conn.execute("SELECT status FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone()
    expect(dep["status"] == "entitlement_required", str(dict(dep)))
    subscription = conn.execute("SELECT status FROM arclink_subscriptions WHERE stripe_subscription_id = 'sub_test'").fetchone()
    expect(subscription["status"] == "past_due", str(dict(subscription)))
    audit = conn.execute("SELECT action, reason FROM arclink_audit_log WHERE target_id = 'user_1'").fetchone()
    expect(audit["action"] == "payment_entitlement_blocked", str(dict(audit)))
    expect("invoice.payment_failed" in audit["reason"], str(dict(audit)))
    print("PASS test_failed_payment_keeps_gate_blocked_and_audits_reason")


def test_supported_webhook_failure_rolls_back_entitlement_side_effects() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_atomicity_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_entitlement_atomicity_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_atomicity_test")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_1", stripe_customer_id="cus_test", entitlement_state="none")
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_1",
        user_id="user_1",
        prefix="atomic-paid",
        status="entitlement_required",
    )

    original_append_event = entitlements.append_arclink_event

    def fail_after_entitlement_work(*args, **kwargs):
        if kwargs.get("event_type") == "stripe_webhook_processed":
            raise RuntimeError("forced webhook atomicity failure")
        return original_append_event(*args, **kwargs)

    entitlements.append_arclink_event = fail_after_entitlement_work
    payload = stripe_payload(event_id="evt_atomicity", event_type="customer.subscription.updated", status="active")
    try:
        try:
            entitlements.process_stripe_webhook(
                conn,
                payload=payload,
                signature=sign(adapters, payload),
                secret="whsec_test",
            )
        except RuntimeError as exc:
            expect("atomicity" in str(exc), str(exc))
        else:
            raise AssertionError("expected forced webhook failure")
    finally:
        entitlements.append_arclink_event = original_append_event

    user = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = 'user_1'").fetchone()
    dep = conn.execute("SELECT status FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone()
    subscription_count = conn.execute("SELECT COUNT(*) AS n FROM arclink_subscriptions").fetchone()["n"]
    audit_count = conn.execute("SELECT COUNT(*) AS n FROM arclink_audit_log").fetchone()["n"]
    event_count = conn.execute("SELECT COUNT(*) AS n FROM arclink_events").fetchone()["n"]
    webhook = conn.execute(
        "SELECT status FROM arclink_webhook_events WHERE event_id = 'evt_atomicity'"
    ).fetchone()
    expect(user["entitlement_state"] == "none", str(dict(user)))
    expect(dep["status"] == "entitlement_required", str(dict(dep)))
    expect(subscription_count == 0, str(subscription_count))
    expect(audit_count == 0, str(audit_count))
    expect(event_count == 0, str(event_count))
    expect(webhook["status"] == "failed", str(dict(webhook)))

    replay = entitlements.process_stripe_webhook(
        conn,
        payload=payload,
        signature=sign(adapters, payload),
        secret="whsec_test",
    )
    expect(replay.replayed and replay.entitlement_state == "paid", str(replay))
    user_after = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = 'user_1'").fetchone()
    dep_after = conn.execute("SELECT status FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone()
    webhook_after = conn.execute(
        "SELECT status FROM arclink_webhook_events WHERE event_id = 'evt_atomicity'"
    ).fetchone()
    expect(user_after["entitlement_state"] == "paid", str(dict(user_after)))
    expect(dep_after["status"] == "provisioning_ready", str(dict(dep_after)))
    expect(webhook_after["status"] == "processed", str(dict(webhook_after)))
    print("PASS test_supported_webhook_failure_rolls_back_entitlement_side_effects")


def test_stripe_webhook_rejects_caller_owned_transaction_without_rollback() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_caller_txn_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_entitlement_caller_txn_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_caller_txn_test")
    conn = memory_db(control)
    conn.execute("BEGIN")
    conn.execute(
        """
        INSERT INTO arclink_users (user_id, display_name, status, entitlement_state, created_at, updated_at)
        VALUES ('pending_user', 'Pending User', 'active', 'none', '2026-05-01T00:00:00Z', '2026-05-01T00:00:00Z')
        """
    )
    payload = stripe_payload(event_id="evt_nested_txn", event_type="customer.subscription.updated", status="active")
    try:
        entitlements.process_stripe_webhook(
            conn,
            payload=payload,
            signature=sign(adapters, payload),
            secret="whsec_test",
        )
    except entitlements.ArcLinkEntitlementError as exc:
        expect("active transaction" in str(exc), str(exc))
    else:
        raise AssertionError("expected active caller transaction to be rejected")

    expect(conn.in_transaction, "caller-owned transaction should remain open")
    pending = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = 'pending_user'").fetchone()
    webhook_count = conn.execute("SELECT COUNT(*) AS n FROM arclink_webhook_events").fetchone()["n"]
    expect(pending["entitlement_state"] == "none", str(dict(pending)))
    expect(webhook_count == 0, str(webhook_count))
    conn.commit()
    committed = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = 'pending_user'").fetchone()
    expect(committed["entitlement_state"] == "none", str(dict(committed)))
    print("PASS test_stripe_webhook_rejects_caller_owned_transaction_without_rollback")


def test_invoice_success_sets_paid_and_lifts_entitlement_gate() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_invoice_success_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_entitlement_invoice_success_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_invoice_success_test")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_1", stripe_customer_id="cus_test", entitlement_state="none")
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_1",
        user_id="user_1",
        prefix="invoice-success",
        status="entitlement_required",
    )
    payload = stripe_payload(event_id="evt_invoice_success", event_type="invoice.payment_succeeded", status="paid")
    result = entitlements.process_stripe_webhook(conn, payload=payload, signature=sign(adapters, payload), secret="whsec_test")
    expect(result.entitlement_state == "paid", str(result))
    expect(result.advanced_deployments == ("dep_1",), str(result))
    user = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = 'user_1'").fetchone()
    dep = conn.execute("SELECT status FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone()
    subscription = conn.execute("SELECT status FROM arclink_subscriptions WHERE stripe_subscription_id = 'sub_test'").fetchone()
    expect(user["entitlement_state"] == "paid", str(dict(user)))
    expect(dep["status"] == "provisioning_ready", str(dict(dep)))
    expect(subscription["status"] == "paid", str(dict(subscription)))

    replay = entitlements.process_stripe_webhook(conn, payload=payload, signature=sign(adapters, payload), secret="whsec_test")
    expect(replay.replayed, str(replay))
    user_after_replay = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = 'user_1'").fetchone()
    dep_after_replay = conn.execute("SELECT status FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone()
    expect(user_after_replay["entitlement_state"] == "paid", str(dict(user_after_replay)))
    expect(dep_after_replay["status"] == "provisioning_ready", str(dict(dep_after_replay)))

    paid_payload = stripe_payload(event_id="evt_invoice_paid", event_type="invoice.paid", status="paid")
    paid_result = entitlements.process_stripe_webhook(
        conn,
        payload=paid_payload,
        signature=sign(adapters, paid_payload),
        secret="whsec_test",
    )
    user_after_paid = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = 'user_1'").fetchone()
    expect(paid_result.entitlement_state == "paid", str(paid_result))
    expect(user_after_paid["entitlement_state"] == "paid", str(dict(user_after_paid)))
    print("PASS test_invoice_success_sets_paid_and_lifts_entitlement_gate")


def test_invoice_success_reads_nested_parent_subscription_details() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_nested_invoice_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_entitlement_nested_invoice_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_nested_invoice_test")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_nested", stripe_customer_id="cus_nested", entitlement_state="none")
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_nested",
        user_id="user_nested",
        prefix="nested-invoice",
        status="entitlement_required",
    )
    payload = json.dumps(
        {
            "id": "evt_invoice_nested_parent",
            "type": "invoice.payment_succeeded",
            "data": {
                "object": {
                    "id": "in_nested",
                    "customer": "cus_nested",
                    "status": "paid",
                    "metadata": {},
                    "parent": {
                        "subscription_details": {
                            "subscription": "sub_nested",
                            "metadata": {"arclink_user_id": "user_nested"},
                        },
                    },
                },
            },
        },
        sort_keys=True,
    )

    result = entitlements.process_stripe_webhook(
        conn,
        payload=payload,
        signature=sign(adapters, payload),
        secret="whsec_test",
    )
    expect(result.user_id == "user_nested", str(result))
    expect(result.entitlement_state == "paid", str(result))
    expect(result.advanced_deployments == ("dep_nested",), str(result))
    user = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = 'user_nested'").fetchone()
    dep = conn.execute("SELECT status FROM arclink_deployments WHERE deployment_id = 'dep_nested'").fetchone()
    subscription = conn.execute(
        "SELECT user_id, status FROM arclink_subscriptions WHERE stripe_subscription_id = 'sub_nested'"
    ).fetchone()
    expect(user["entitlement_state"] == "paid", str(dict(user)))
    expect(dep["status"] == "provisioning_ready", str(dict(dep)))
    expect(subscription["user_id"] == "user_nested", str(dict(subscription)))
    expect(subscription["status"] == "paid", str(dict(subscription)))

    event_count = conn.execute("SELECT COUNT(*) AS n FROM arclink_events").fetchone()["n"]
    replay = entitlements.process_stripe_webhook(
        conn,
        payload=payload,
        signature=sign(adapters, payload),
        secret="whsec_test",
    )
    event_count_after_replay = conn.execute("SELECT COUNT(*) AS n FROM arclink_events").fetchone()["n"]
    expect(replay.replayed, str(replay))
    expect(event_count_after_replay == event_count, f"{event_count} -> {event_count_after_replay}")
    print("PASS test_invoice_success_reads_nested_parent_subscription_details")


def test_unsupported_signed_event_does_not_mutate_paid_entitlement() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_unsupported_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_entitlement_unsupported_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_unsupported_test")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_1", entitlement_state="paid")
    payload = stripe_payload(event_id="evt_customer_updated", event_type="customer.updated", status="")
    result = entitlements.process_stripe_webhook(conn, payload=payload, signature=sign(adapters, payload), secret="whsec_test")
    expect(result.event_type == "customer.updated", str(result))
    expect(result.entitlement_state == "", str(result))

    user = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = 'user_1'").fetchone()
    expect(user["entitlement_state"] == "paid", str(dict(user)))
    subscription_count = conn.execute("SELECT COUNT(*) AS n FROM arclink_subscriptions").fetchone()["n"]
    audit_count = conn.execute("SELECT COUNT(*) AS n FROM arclink_audit_log").fetchone()["n"]
    event_count = conn.execute("SELECT COUNT(*) AS n FROM arclink_events").fetchone()["n"]
    webhook = conn.execute(
        "SELECT status FROM arclink_webhook_events WHERE event_id = 'evt_customer_updated'"
    ).fetchone()
    expect(subscription_count == 0, str(subscription_count))
    expect(audit_count == 0, str(audit_count))
    expect(event_count == 0, str(event_count))
    expect(webhook["status"] == "processed", str(dict(webhook)))

    replay = entitlements.process_stripe_webhook(conn, payload=payload, signature=sign(adapters, payload), secret="whsec_test")
    expect(replay.replayed, str(replay))
    user_after_replay = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = 'user_1'").fetchone()
    expect(user_after_replay["entitlement_state"] == "paid", str(dict(user_after_replay)))
    print("PASS test_unsupported_signed_event_does_not_mutate_paid_entitlement")


def test_manual_comp_requires_reason_and_lifts_gate() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_comp_test")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_1", stripe_customer_id="cus_test", entitlement_state="none")
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_1",
        user_id="user_1",
        prefix="comp-gate",
        status="entitlement_required",
    )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_2",
        user_id="user_1",
        prefix="comp-gate-two",
        status="entitlement_required",
    )
    try:
        control.comp_arclink_subscription(conn, user_id="user_1", actor_id="admin_1", reason="")
    except ValueError as exc:
        expect("reason" in str(exc), str(exc))
    else:
        raise AssertionError("expected comp without reason to fail")
    control.comp_arclink_subscription(conn, user_id="user_1", actor_id="admin_1", reason="customer credit")
    user = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = 'user_1'").fetchone()
    dep = conn.execute("SELECT status FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone()
    dep_2 = conn.execute("SELECT status FROM arclink_deployments WHERE deployment_id = 'dep_2'").fetchone()
    audit = conn.execute("SELECT reason FROM arclink_audit_log WHERE action = 'comp_subscription'").fetchone()
    expect(user["entitlement_state"] == "comp", str(dict(user)))
    expect(dep["status"] == "provisioning_ready", str(dict(dep)))
    expect(dep_2["status"] == "provisioning_ready", str(dict(dep_2)))
    expect(audit["reason"] == "customer credit", str(dict(audit)))
    print("PASS test_manual_comp_requires_reason_and_lifts_gate")


def test_profile_only_upsert_preserves_paid_and_comp_entitlements() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_preserve_test")
    conn = memory_db(control)
    paid = control.upsert_arclink_user(
        conn,
        user_id="paid_user",
        email="old-paid@example.test",
        display_name="Old Paid",
        entitlement_state="paid",
    )
    comp = control.upsert_arclink_user(
        conn,
        user_id="comp_user",
        email="old-comp@example.test",
        display_name="Old Comp",
        entitlement_state="comp",
    )

    control.upsert_arclink_user(
        conn,
        user_id="paid_user",
        email="new-paid@example.test",
        display_name="New Paid",
        status="active",
    )
    control.upsert_arclink_user(
        conn,
        user_id="comp_user",
        email="new-comp@example.test",
        display_name="New Comp",
        status="active",
    )

    paid_after = conn.execute(
        "SELECT email, display_name, entitlement_state, entitlement_updated_at FROM arclink_users WHERE user_id = 'paid_user'"
    ).fetchone()
    comp_after = conn.execute(
        "SELECT email, display_name, entitlement_state, entitlement_updated_at FROM arclink_users WHERE user_id = 'comp_user'"
    ).fetchone()
    expect(paid_after["email"] == "new-paid@example.test", str(dict(paid_after)))
    expect(paid_after["display_name"] == "New Paid", str(dict(paid_after)))
    expect(paid_after["entitlement_state"] == "paid", str(dict(paid_after)))
    expect(paid_after["entitlement_updated_at"] == paid["entitlement_updated_at"], str(dict(paid_after)))
    expect(comp_after["email"] == "new-comp@example.test", str(dict(comp_after)))
    expect(comp_after["display_name"] == "New Comp", str(dict(comp_after)))
    expect(comp_after["entitlement_state"] == "comp", str(dict(comp_after)))
    expect(comp_after["entitlement_updated_at"] == comp["entitlement_updated_at"], str(dict(comp_after)))
    print("PASS test_profile_only_upsert_preserves_paid_and_comp_entitlements")


def test_new_user_without_explicit_entitlement_defaults_to_none() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_default_test")
    conn = memory_db(control)
    user = control.upsert_arclink_user(
        conn,
        user_id="new_user",
        email="new@example.test",
        display_name="New User",
    )
    expect(user["entitlement_state"] == "none", str(user))
    expect(user["entitlement_updated_at"] == "", str(user))
    print("PASS test_new_user_without_explicit_entitlement_defaults_to_none")


def test_targeted_comp_advances_only_named_deployment_without_global_comp() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_targeted_comp_test")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_1", stripe_customer_id="cus_test", entitlement_state="none")
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_1",
        user_id="user_1",
        prefix="targeted-comp-one",
        status="entitlement_required",
    )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_2",
        user_id="user_1",
        prefix="targeted-comp-two",
        status="entitlement_required",
    )
    control.comp_arclink_subscription(
        conn,
        user_id="user_1",
        actor_id="admin_1",
        reason="single deployment credit",
        deployment_id="dep_1",
    )
    user = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = 'user_1'").fetchone()
    dep_1 = conn.execute("SELECT status FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone()
    dep_2 = conn.execute("SELECT status FROM arclink_deployments WHERE deployment_id = 'dep_2'").fetchone()
    audit = conn.execute("SELECT target_kind, target_id FROM arclink_audit_log WHERE action = 'comp_subscription'").fetchone()
    expect(user["entitlement_state"] == "none", str(dict(user)))
    expect(dep_1["status"] == "provisioning_ready", str(dict(dep_1)))
    expect(dep_2["status"] == "entitlement_required", str(dict(dep_2)))
    expect(audit["target_kind"] == "deployment" and audit["target_id"] == "dep_1", str(dict(audit)))
    print("PASS test_targeted_comp_advances_only_named_deployment_without_global_comp")


def test_refuel_credit_uses_fair_local_accounting_without_live_purchase() -> None:
    control = load_module("arclink_control.py", "arclink_control_refuel_credit_test")
    chutes_provider_key = "chutes"
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_refuel", entitlement_state="paid")
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_refuel",
        user_id="user_refuel",
        prefix="refuel-local",
        status="active",
        metadata={chutes_provider_key: {"monthly_budget_cents": 1000, "used_cents": 900}},
    )

    sku = control.refuel_credit_sku_config({"ARCLINK_REFUEL_CREDIT_CENTS": "1500"})
    expect(sku["credit_cents"] == 1500, str(sku))
    expect(sku["live_purchase"] == "proof_gated", str(sku))
    credit = control.grant_arclink_refuel_credit(
        conn,
        user_id="user_refuel",
        actor_id="admin_refuel",
        reason="local credit ledger test",
        credit_cents=1500,
        source_kind="test",
    )
    expect(credit["remaining_cents"] == 1500, str(dict(credit)))
    balance = control.arclink_refuel_credit_balance(conn, user_id="user_refuel", deployment_id="dep_refuel")
    expect(balance["remaining_cents"] == 1500, str(balance))

    applied = control.apply_arclink_refuel_credit_to_chutes_budget(
        conn,
        user_id="user_refuel",
        deployment_id="dep_refuel",
        requested_cents=1200,
        actor_id="admin_refuel",
        reason="apply local credit",
    )
    expect(applied["applied_cents"] == 1200, str(applied))
    expect(applied["provider_balance_application"] == "local_budget_accounting_only_until_live_chutes_proof", str(applied))
    balance_after = control.arclink_refuel_credit_balance(conn, user_id="user_refuel", deployment_id="dep_refuel")
    expect(balance_after["remaining_cents"] == 300, str(balance_after))
    row = conn.execute("SELECT metadata_json FROM arclink_deployments WHERE deployment_id = 'dep_refuel'").fetchone()
    metadata = json.loads(row["metadata_json"])
    expect(metadata[chutes_provider_key]["monthly_budget_cents"] == 2200, str(metadata))
    expect(metadata[chutes_provider_key]["refuel_applied_credit_cents"] == 1200, str(metadata))
    audit = conn.execute("SELECT action, target_kind FROM arclink_audit_log WHERE action = 'refuel_credit_applied'").fetchone()
    expect(audit["target_kind"] == "deployment", str(dict(audit)))
    print("PASS test_refuel_credit_uses_fair_local_accounting_without_live_purchase")


def test_refuel_credit_source_id_is_idempotent() -> None:
    control = load_module("arclink_control.py", "arclink_control_refuel_source_id_test")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_refuel_source", entitlement_state="paid")
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_refuel_source",
        user_id="user_refuel_source",
        prefix="refuel-source",
        status="active",
    )
    first = control.grant_arclink_refuel_credit(
        conn,
        user_id="user_refuel_source",
        deployment_id="dep_refuel_source",
        actor_id="stripe",
        reason="source idempotency",
        credit_cents=1500,
        source_kind="stripe_checkout",
        source_id="cs_refuel_source",
    )
    second = control.grant_arclink_refuel_credit(
        conn,
        user_id="user_refuel_source",
        deployment_id="dep_refuel_source",
        actor_id="stripe",
        reason="source idempotency retry",
        credit_cents=1500,
        source_kind="stripe_checkout",
        source_id="cs_refuel_source",
    )
    count = conn.execute("SELECT COUNT(*) AS n FROM arclink_refuel_credits").fetchone()["n"]
    audit_count = conn.execute("SELECT COUNT(*) AS n FROM arclink_audit_log WHERE action = 'refuel_credit_granted'").fetchone()["n"]
    expect(second["credit_id"] == first["credit_id"], f"{first} != {second}")
    expect(count == 1, str(count))
    expect(audit_count == 1, str(audit_count))
    print("PASS test_refuel_credit_source_id_is_idempotent")


def test_refuel_credit_concurrent_spend_does_not_overspend() -> None:
    control = load_module("arclink_control.py", "arclink_control_refuel_credit_concurrent_test")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = f"{tmpdir}/control.sqlite3"
        seed_conn = sqlite3.connect(db_path, timeout=15)
        seed_conn.row_factory = sqlite3.Row
        control.ensure_schema(seed_conn)
        control.upsert_arclink_user(seed_conn, user_id="user_refuel", entitlement_state="paid")
        control.reserve_arclink_deployment_prefix(
            seed_conn,
            deployment_id="dep_refuel",
            user_id="user_refuel",
            prefix="refuel-race",
            status="active",
            metadata={"chutes": {"monthly_budget_cents": 0}},
        )
        control.grant_arclink_refuel_credit(
            seed_conn,
            user_id="user_refuel",
            actor_id="admin_refuel",
            reason="race credit",
            credit_cents=1500,
            source_kind="test",
        )
        seed_conn.close()

        barrier = threading.Barrier(2)
        results: list[dict[str, object]] = []
        errors: list[str] = []
        lock = threading.Lock()

        def spend() -> None:
            conn = sqlite3.connect(db_path, timeout=15)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout = 15000")
            try:
                barrier.wait(timeout=5)
                result = control.apply_arclink_refuel_credit_to_chutes_budget(
                    conn,
                    user_id="user_refuel",
                    deployment_id="dep_refuel",
                    requested_cents=1000,
                    actor_id="admin_refuel",
                    reason="parallel apply",
                )
                with lock:
                    results.append(result)
            except Exception as exc:  # noqa: BLE001 - test records any unexpected thread failure
                with lock:
                    errors.append(str(exc))
            finally:
                conn.close()

        threads = [threading.Thread(target=spend), threading.Thread(target=spend)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        expect(errors == [], f"parallel spend errors: {errors}")
        expect(sorted(int(r["applied_cents"]) for r in results) == [500, 1000], str(results))
        check_conn = sqlite3.connect(db_path)
        check_conn.row_factory = sqlite3.Row
        credit = check_conn.execute("SELECT remaining_cents, status FROM arclink_refuel_credits").fetchone()
        deployment = check_conn.execute("SELECT metadata_json FROM arclink_deployments WHERE deployment_id = 'dep_refuel'").fetchone()
        audit_count = check_conn.execute("SELECT COUNT(*) AS c FROM arclink_audit_log WHERE action = 'refuel_credit_applied'").fetchone()["c"]
        metadata = json.loads(deployment["metadata_json"])
        expect(int(credit["remaining_cents"]) == 0 and credit["status"] == "exhausted", str(dict(credit)))
        expect(metadata["chutes"]["monthly_budget_cents"] == 1500, str(metadata))
        expect(int(audit_count) == 2, f"expected two audited spend attempts, got {audit_count}")
        check_conn.close()
    print("PASS test_refuel_credit_concurrent_spend_does_not_overspend")


def test_refuel_credit_rejects_empty_and_wrong_owner_targets() -> None:
    control = load_module("arclink_control.py", "arclink_control_refuel_credit_guard_test")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_refuel", entitlement_state="paid")
    control.upsert_arclink_user(conn, user_id="user_other", entitlement_state="paid")
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_refuel",
        user_id="user_refuel",
        prefix="refuel-empty",
        status="active",
    )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_other",
        user_id="user_other",
        prefix="refuel-other",
        status="active",
    )
    credit = control.grant_arclink_refuel_credit(
        conn,
        user_id="user_refuel",
        actor_id="admin_refuel",
        reason="small credit",
        credit_cents=500,
        source_kind="test",
        deployment_id="dep_refuel",
    )
    exhausted = control.apply_arclink_refuel_credit_to_chutes_budget(
        conn,
        user_id="user_refuel",
        deployment_id="dep_refuel",
        requested_cents=500,
        actor_id="admin_refuel",
        reason="exhaust credit",
    )
    expect(exhausted["credits"][0]["credit_id"] == credit["credit_id"], str(exhausted))
    refreshed = conn.execute("SELECT remaining_cents, status FROM arclink_refuel_credits WHERE credit_id = ?", (credit["credit_id"],)).fetchone()
    expect(int(refreshed["remaining_cents"]) == 0 and refreshed["status"] == "exhausted", str(dict(refreshed)))
    try:
        control.apply_arclink_refuel_credit_to_chutes_budget(
            conn,
            user_id="user_refuel",
            deployment_id="dep_refuel",
            requested_cents=1,
            actor_id="admin_refuel",
            reason="empty credit",
        )
    except ValueError as exc:
        expect("balance is empty" in str(exc), str(exc))
    else:
        raise AssertionError("expected empty refuel balance to fail")
    try:
        control.apply_arclink_refuel_credit_to_chutes_budget(
            conn,
            user_id="user_refuel",
            deployment_id="dep_other",
            requested_cents=1,
            actor_id="admin_refuel",
            reason="wrong owner",
        )
    except ValueError as exc:
        expect("does not belong to user" in str(exc), str(exc))
    else:
        raise AssertionError("expected wrong-owner deployment to fail")
    print("PASS test_refuel_credit_rejects_empty_and_wrong_owner_targets")


def test_refuel_checkout_session_completed_grants_and_applies_credit() -> None:
    control = load_module("arclink_control.py", "arclink_control_refuel_webhook_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_refuel_webhook_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_refuel_webhook_test")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_refuel_paid", entitlement_state="paid")
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_refuel_paid",
        user_id="user_refuel_paid",
        prefix="refuel-paid",
        status="active",
        metadata={"chutes": {"monthly_budget_cents": 1000}},
    )
    payload = json.dumps({
        "id": "evt_refuel_paid",
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": "cs_refuel_paid",
            "status": "complete",
            "payment_status": "paid",
            "amount_total": 2500,
            "customer": "cus_refuel_paid",
            "client_reference_id": "user_refuel_paid",
            "customer_details": {"email": "refuel-paid@example.test"},
            "metadata": {
                "arclink_purchase_kind": "inference_refuel",
                "arclink_user_id": "user_refuel_paid",
                "arclink_deployment_id": "dep_refuel_paid",
                "retail_cents": "2500",
                "credit_cents": "1750",
            },
        }},
    }, sort_keys=True)
    result = entitlements.process_stripe_webhook(
        conn,
        payload=payload,
        signature=sign(adapters, payload),
        secret="whsec_test",
    )
    expect(result.entitlement_state == "refuel_paid", str(result))
    expect(result.advanced_deployments == ("dep_refuel_paid",), str(result))
    row = conn.execute("SELECT metadata_json FROM arclink_deployments WHERE deployment_id = 'dep_refuel_paid'").fetchone()
    metadata = json.loads(row["metadata_json"])
    expect(metadata["chutes"]["monthly_budget_cents"] == 2750, str(metadata))
    expect(metadata["chutes"]["refuel_applied_credit_cents"] == 1750, str(metadata))
    credit = conn.execute("SELECT credit_cents, remaining_cents, status, source_kind, source_id FROM arclink_refuel_credits").fetchone()
    expect(credit["credit_cents"] == 1750 and credit["remaining_cents"] == 0, str(dict(credit)))
    expect(credit["status"] == "exhausted", str(dict(credit)))
    expect(credit["source_kind"] == "stripe_checkout", str(dict(credit)))
    event = conn.execute("SELECT event_type FROM arclink_events WHERE event_type = 'stripe_refuel_checkout_processed'").fetchone()
    expect(event is not None, "missing refuel processed event")
    user = conn.execute("SELECT entitlement_state, stripe_customer_id FROM arclink_users WHERE user_id = 'user_refuel_paid'").fetchone()
    expect(user["entitlement_state"] == "paid", str(dict(user)))
    expect(user["stripe_customer_id"] == "cus_refuel_paid", str(dict(user)))
    replay = entitlements.process_stripe_webhook(
        conn,
        payload=payload,
        signature=sign(adapters, payload),
        secret="whsec_test",
    )
    expect(replay.replayed, str(replay))
    count = conn.execute("SELECT COUNT(*) AS n FROM arclink_refuel_credits").fetchone()["n"]
    expect(count == 1, str(count))
    print("PASS test_refuel_checkout_session_completed_grants_and_applies_credit")


def test_refuel_checkout_rejects_unpaid_or_underpaid_session() -> None:
    control = load_module("arclink_control.py", "arclink_control_refuel_unpaid_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_refuel_unpaid_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_refuel_unpaid_test")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_refuel_unpaid", entitlement_state="paid")
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_refuel_unpaid",
        user_id="user_refuel_unpaid",
        prefix="refuel-unpaid",
        status="active",
        metadata={"chutes": {"monthly_budget_cents": 1000}},
    )

    def payload(event_id: str, *, payment_status: str, amount_total: int) -> str:
        return json.dumps({
            "id": event_id,
            "type": "checkout.session.completed",
            "data": {"object": {
                "id": f"cs_{event_id}",
                "status": "complete",
                "payment_status": payment_status,
                "amount_total": amount_total,
                "customer": "cus_refuel_unpaid",
                "client_reference_id": "user_refuel_unpaid",
                "metadata": {
                    "arclink_purchase_kind": "inference_refuel",
                    "arclink_user_id": "user_refuel_unpaid",
                    "arclink_deployment_id": "dep_refuel_unpaid",
                    "retail_cents": "2500",
                    "credit_cents": "1750",
                },
            }},
        }, sort_keys=True)

    for event_id, payment_status, amount_total, expected in (
        ("evt_refuel_unpaid", "unpaid", 2500, "not paid"),
        ("evt_refuel_underpaid", "paid", 500, "below the expected total"),
    ):
        body = payload(event_id, payment_status=payment_status, amount_total=amount_total)
        try:
            entitlements.process_stripe_webhook(
                conn,
                payload=body,
                signature=sign(adapters, body),
                secret="whsec_test",
            )
        except entitlements.ArcLinkEntitlementError as exc:
            expect(expected in str(exc), str(exc))
        else:
            raise AssertionError(f"expected {event_id} to fail")

    credit_count = conn.execute("SELECT COUNT(*) AS n FROM arclink_refuel_credits").fetchone()["n"]
    dep = conn.execute("SELECT metadata_json FROM arclink_deployments WHERE deployment_id = 'dep_refuel_unpaid'").fetchone()
    metadata = json.loads(dep["metadata_json"])
    expect(credit_count == 0, str(credit_count))
    expect(metadata["chutes"]["monthly_budget_cents"] == 1000, str(metadata))
    print("PASS test_refuel_checkout_rejects_unpaid_or_underpaid_session")


def test_refuel_checkout_rejects_mismatched_stripe_customer() -> None:
    control = load_module("arclink_control.py", "arclink_control_refuel_mismatch_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_refuel_mismatch_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_refuel_mismatch_test")
    conn = memory_db(control)
    control.upsert_arclink_user(
        conn,
        user_id="user_refuel_owner",
        stripe_customer_id="cus_owner",
        entitlement_state="paid",
    )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_refuel_owner",
        user_id="user_refuel_owner",
        prefix="refuel-owner",
        status="active",
        metadata={"chutes": {"monthly_budget_cents": 1000}},
    )
    payload = json.dumps({
        "id": "evt_refuel_customer_mismatch",
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": "cs_refuel_customer_mismatch",
            "status": "complete",
            "payment_status": "paid",
            "amount_total": 2500,
            "customer": "cus_other",
            "client_reference_id": "user_refuel_owner",
            "metadata": {
                "arclink_purchase_kind": "inference_refuel",
                "arclink_user_id": "user_refuel_owner",
                "arclink_deployment_id": "dep_refuel_owner",
                "retail_cents": "2500",
                "credit_cents": "1750",
            },
        }},
    }, sort_keys=True)
    try:
        entitlements.process_stripe_webhook(
            conn,
            payload=payload,
            signature=sign(adapters, payload),
            secret="whsec_test",
        )
    except entitlements.ArcLinkEntitlementError as exc:
        expect("customer does not match" in str(exc), str(exc))
    else:
        raise AssertionError("expected mismatched Stripe customer to be rejected")
    credit_count = conn.execute("SELECT COUNT(*) AS n FROM arclink_refuel_credits").fetchone()["n"]
    expect(credit_count == 0, str(credit_count))
    dep = conn.execute("SELECT metadata_json FROM arclink_deployments WHERE deployment_id = 'dep_refuel_owner'").fetchone()
    metadata = json.loads(dep["metadata_json"])
    expect(metadata["chutes"]["monthly_budget_cents"] == 1000, str(metadata))
    print("PASS test_refuel_checkout_rejects_mismatched_stripe_customer")


def test_invoice_payment_tops_up_subscription_inference_allowance_once() -> None:
    control = load_module("arclink_control.py", "arclink_control_subscription_allowance_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_subscription_allowance_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_subscription_allowance_test")
    conn = memory_db(control)
    control.upsert_arclink_user(
        conn,
        user_id="user_scale",
        stripe_customer_id="cus_scale",
        entitlement_state="paid",
    )
    control.upsert_arclink_subscription_mirror(
        conn,
        subscription_id="stripe:sub_scale",
        user_id="user_scale",
        stripe_customer_id="cus_scale",
        stripe_subscription_id="sub_scale",
        status="active",
        current_period_end="",
        raw={},
    )
    for index in range(3):
        control.reserve_arclink_deployment_prefix(
            conn,
            deployment_id=f"dep_scale_{index}",
            user_id="user_scale",
            prefix=f"scale-{index}",
            status="active",
            metadata={"selected_plan_id": "scale", "chutes": {"monthly_budget_cents": 0}},
        )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_scale_retired",
        user_id="user_scale",
        prefix="scale-retired",
        status="teardown_requested",
        metadata={"selected_plan_id": "scale", "chutes": {"monthly_budget_cents": 0}},
    )
    payload = json.dumps({
        "id": "evt_scale_invoice_paid",
        "type": "invoice.payment_succeeded",
        "data": {"object": {
            "id": "in_scale_1",
            "customer": "cus_scale",
            "subscription": "sub_scale",
            "status": "paid",
            "metadata": {},
        }},
    }, sort_keys=True)
    result = entitlements.process_stripe_webhook(
        conn,
        payload=payload,
        signature=sign(adapters, payload),
        secret="whsec_test",
    )
    expect(result.user_id == "user_scale", str(result))
    budgets: list[int] = []
    for index in range(3):
        row = conn.execute(
            "SELECT metadata_json FROM arclink_deployments WHERE deployment_id = ?",
            (f"dep_scale_{index}",),
        ).fetchone()
        metadata = json.loads(row["metadata_json"])
        budgets.append(int(metadata["chutes"]["monthly_budget_cents"]))
    expect(sorted(budgets) == [1833, 1833, 1834], str(budgets))
    expect(sum(budgets) == 5500, str(budgets))
    retired_row = conn.execute(
        "SELECT metadata_json FROM arclink_deployments WHERE deployment_id = 'dep_scale_retired'"
    ).fetchone()
    retired_metadata = json.loads(retired_row["metadata_json"])
    expect(retired_metadata["chutes"]["monthly_budget_cents"] == 0, str(retired_metadata))
    credit_count = conn.execute(
        "SELECT COUNT(*) AS n FROM arclink_refuel_credits WHERE source_kind = 'stripe_subscription_renewal'"
    ).fetchone()["n"]
    expect(credit_count == 3, str(credit_count))

    replay_payload = json.dumps({
        "id": "evt_scale_invoice_paid_alias",
        "type": "invoice.paid",
        "data": {"object": {
            "id": "in_scale_1",
            "customer": "cus_scale",
            "subscription": "sub_scale",
            "status": "paid",
            "metadata": {},
        }},
    }, sort_keys=True)
    replay = entitlements.process_stripe_webhook(
        conn,
        payload=replay_payload,
        signature=sign(adapters, replay_payload),
        secret="whsec_test",
    )
    expect(replay.entitlement_state == "paid", str(replay))
    replay_credit_count = conn.execute(
        "SELECT COUNT(*) AS n FROM arclink_refuel_credits WHERE source_kind = 'stripe_subscription_renewal'"
    ).fetchone()["n"]
    expect(replay_credit_count == 3, str(replay_credit_count))
    replay_budgets: list[int] = []
    for index in range(3):
        row = conn.execute(
            "SELECT metadata_json FROM arclink_deployments WHERE deployment_id = ?",
            (f"dep_scale_{index}",),
        ).fetchone()
        replay_budgets.append(int(json.loads(row["metadata_json"])["chutes"]["monthly_budget_cents"]))
    expect(replay_budgets == budgets, str(replay_budgets))
    print("PASS test_invoice_payment_tops_up_subscription_inference_allowance_once")


def test_checkout_session_completed_rejects_unpaid_subscription_checkout() -> None:
    control = load_module("arclink_control.py", "arclink_control_checkout_unpaid_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_checkout_unpaid_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_checkout_unpaid_test")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_checkout_unpaid", entitlement_state="none")
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_checkout_unpaid",
        user_id="user_checkout_unpaid",
        prefix="checkout-unpaid",
        status="entitlement_required",
    )
    payload = json.dumps({
        "id": "evt_checkout_unpaid",
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": "cs_checkout_unpaid",
            "status": "complete",
            "payment_status": "unpaid",
            "amount_total": 1000,
            "customer": "cus_checkout_unpaid",
            "subscription": "sub_checkout_unpaid",
            "client_reference_id": "user_checkout_unpaid",
            "metadata": {"arclink_user_id": "user_checkout_unpaid"},
        }},
    }, sort_keys=True)

    try:
        entitlements.process_stripe_webhook(
            conn,
            payload=payload,
            signature=sign(adapters, payload),
            secret="whsec_test",
        )
    except entitlements.ArcLinkEntitlementError as exc:
        expect("not paid" in str(exc), str(exc))
    else:
        raise AssertionError("expected unpaid checkout to fail")

    user = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = 'user_checkout_unpaid'").fetchone()
    dep = conn.execute("SELECT status FROM arclink_deployments WHERE deployment_id = 'dep_checkout_unpaid'").fetchone()
    sub_count = conn.execute("SELECT COUNT(*) AS n FROM arclink_subscriptions").fetchone()["n"]
    webhook = conn.execute("SELECT status FROM arclink_webhook_events WHERE event_id = 'evt_checkout_unpaid'").fetchone()
    expect(user["entitlement_state"] == "none", str(dict(user)))
    expect(dep["status"] == "entitlement_required", str(dict(dep)))
    expect(sub_count == 0, str(sub_count))
    expect(webhook["status"] == "failed", str(dict(webhook)))
    print("PASS test_checkout_session_completed_rejects_unpaid_subscription_checkout")


def test_checkout_session_completed_lifts_entitlement_and_syncs_onboarding() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_checkout_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_entitlement_checkout_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_checkout_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_entitlement_checkout_test")
    conn = memory_db(control)
    # Create user through onboarding
    session = onboarding.create_or_resume_arclink_onboarding_session(
        conn, channel="web", channel_identity="checkout@example.test",
        session_id="onb_checkout", email_hint="checkout@example.test",
        display_name_hint="Checkout User", selected_plan_id="sovereign",
    )
    prepared = onboarding.prepare_arclink_onboarding_deployment(
        conn, session_id=session["session_id"], base_domain="example.test", prefix="ck-test-1a2b",
    )
    # Simulate checkout.session.completed webhook
    payload = json.dumps({
        "id": "evt_checkout_completed",
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": "cs_test_checkout",
            "status": "complete",
            "payment_status": "paid",
            "amount_total": 1000,
            "customer": "cus_checkout",
            "subscription": "sub_checkout",
            "client_reference_id": prepared["user_id"],
            "customer_details": {"email": "stripe-checkout@example.test"},
            "metadata": {
                "arclink_user_id": prepared["user_id"],
                "arclink_onboarding_session_id": session["session_id"],
            },
        }},
    }, sort_keys=True)
    result = entitlements.process_stripe_webhook(
        conn, payload=payload, signature=sign(adapters, payload), secret="whsec_test",
    )
    expect(result.event_type == "checkout.session.completed", str(result))
    expect(result.entitlement_state == "paid", str(result))
    expect(len(result.advanced_deployments) >= 1, str(result))
    user = conn.execute("SELECT email, entitlement_state, stripe_customer_id FROM arclink_users WHERE user_id = ?", (prepared["user_id"],)).fetchone()
    expect(user["email"] == "stripe-checkout@example.test", str(dict(user)))
    expect(user["entitlement_state"] == "paid", str(dict(user)))
    expect(user["stripe_customer_id"] == "cus_checkout", str(dict(user)))
    dep = conn.execute("SELECT status FROM arclink_deployments WHERE deployment_id = ?", (prepared["deployment_id"],)).fetchone()
    expect(dep["status"] == "provisioning_ready", str(dict(dep)))
    # Onboarding session should be synced
    sub = conn.execute("SELECT status FROM arclink_subscriptions WHERE stripe_subscription_id = ?", ("sub_checkout",)).fetchone()
    expect(sub["status"] == "paid", str(dict(sub)))
    onb = conn.execute("SELECT status, current_step, checkout_state, checkout_session_id, stripe_customer_id FROM arclink_onboarding_sessions WHERE session_id = ?", (session["session_id"],)).fetchone()
    expect(onb["status"] == "provisioning_ready", str(dict(onb)))
    expect(onb["current_step"] == "provisioning_requested", str(dict(onb)))
    expect(onb["checkout_state"] == "paid", str(dict(onb)))
    expect(onb["checkout_session_id"] == "cs_test_checkout", str(dict(onb)))
    expect(onb["stripe_customer_id"] == "cus_checkout", str(dict(onb)))
    print("PASS test_checkout_session_completed_lifts_entitlement_and_syncs_onboarding")


def test_unbound_subscription_metadata_cannot_first_bind_or_create_user() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_unbound_metadata_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_entitlement_unbound_metadata_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_unbound_metadata_test")
    conn = memory_db(control)
    payload = stripe_payload(
        event_id="evt_unbound_metadata",
        event_type="customer.subscription.created",
        user_id="arcusr_forged_metadata",
        subscription_id="sub_unbound_metadata",
        customer_id="cus_unbound_metadata",
        status="active",
    )

    try:
        entitlements.process_stripe_webhook(
            conn,
            payload=payload,
            signature=sign(adapters, payload),
            secret="whsec_test",
        )
    except entitlements.ArcLinkEntitlementError as exc:
        expect("local ArcLink user id" in str(exc), str(exc))
    else:
        raise AssertionError("expected unbound metadata-only subscription to fail closed")

    user_count = conn.execute("SELECT COUNT(*) AS n FROM arclink_users WHERE user_id = 'arcusr_forged_metadata'").fetchone()["n"]
    sub_count = conn.execute("SELECT COUNT(*) AS n FROM arclink_subscriptions WHERE stripe_subscription_id = 'sub_unbound_metadata'").fetchone()["n"]
    webhook = conn.execute("SELECT status FROM arclink_webhook_events WHERE event_id = 'evt_unbound_metadata'").fetchone()
    expect(user_count == 0, str(user_count))
    expect(sub_count == 0, str(sub_count))
    expect(webhook["status"] == "failed", str(dict(webhook)))
    print("PASS test_unbound_subscription_metadata_cannot_first_bind_or_create_user")


def test_checkout_session_completed_binds_by_local_checkout_session_id_without_metadata() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_checkout_id_owner_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_entitlement_checkout_id_owner_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_checkout_id_owner_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_entitlement_checkout_id_owner_test")
    conn = memory_db(control)
    stripe = adapters.FakeStripeClient()
    session = onboarding.create_or_resume_arclink_onboarding_session(
        conn,
        channel="web",
        channel_identity="checkout-id-owner@example.test",
        session_id="onb_checkout_id_owner",
        email_hint="checkout-id-owner@example.test",
        selected_plan_id="starter",
    )
    opened = onboarding.open_arclink_onboarding_checkout(
        conn,
        session_id=session["session_id"],
        stripe_client=stripe,
        price_id="price_starter",
        success_url="https://example.test/success",
        cancel_url="https://example.test/cancel",
        base_domain="example.test",
    )
    payload = json.dumps({
        "id": "evt_checkout_id_owner",
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": opened["checkout_session_id"],
            "status": "complete",
            "payment_status": "paid",
            "amount_total": 1000,
            "customer": "cus_checkout_id_owner",
            "subscription": "sub_checkout_id_owner",
            "client_reference_id": opened["user_id"],
            "customer_details": {"email": "checkout-id-owner@example.test"},
            "metadata": {},
        }},
    }, sort_keys=True)

    result = entitlements.process_stripe_webhook(
        conn,
        payload=payload,
        signature=sign(adapters, payload),
        secret="whsec_test",
    )

    user = conn.execute("SELECT entitlement_state, stripe_customer_id FROM arclink_users WHERE user_id = ?", (opened["user_id"],)).fetchone()
    onb = conn.execute("SELECT status, checkout_state, stripe_customer_id FROM arclink_onboarding_sessions WHERE session_id = ?", (opened["session_id"],)).fetchone()
    expect(result.user_id == opened["user_id"] and result.entitlement_state == "paid", str(result))
    expect(user["entitlement_state"] == "paid" and user["stripe_customer_id"] == "cus_checkout_id_owner", str(dict(user)))
    expect(onb["status"] == "provisioning_ready" and onb["checkout_state"] == "paid", str(dict(onb)))
    expect(onb["stripe_customer_id"] == "cus_checkout_id_owner", str(dict(onb)))
    print("PASS test_checkout_session_completed_binds_by_local_checkout_session_id_without_metadata")


def test_out_of_order_subscription_replays_after_checkout_binds_subscription() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_out_of_order_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_entitlement_out_of_order_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_out_of_order_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_entitlement_out_of_order_test")
    conn = memory_db(control)
    stripe = adapters.FakeStripeClient()
    session = onboarding.create_or_resume_arclink_onboarding_session(
        conn,
        channel="web",
        channel_identity="out-of-order@example.test",
        session_id="onb_out_of_order",
        email_hint="out-of-order@example.test",
        selected_plan_id="starter",
    )
    opened = onboarding.open_arclink_onboarding_checkout(
        conn,
        session_id=session["session_id"],
        stripe_client=stripe,
        price_id="price_starter",
        success_url="https://example.test/success",
        cancel_url="https://example.test/cancel",
        base_domain="example.test",
    )
    subscription_payload = json.dumps({
        "id": "evt_out_of_order_subscription",
        "type": "customer.subscription.created",
        "data": {"object": {
            "id": "sub_out_of_order",
            "customer": "cus_out_of_order",
            "status": "active",
            "metadata": {"arclink_onboarding_session_id": opened["session_id"]},
        }},
    }, sort_keys=True)

    try:
        entitlements.process_stripe_webhook(
            conn,
            payload=subscription_payload,
            signature=sign(adapters, subscription_payload),
            secret="whsec_test",
        )
    except entitlements.ArcLinkEntitlementError as exc:
        expect("local ArcLink user id" in str(exc), str(exc))
    else:
        raise AssertionError("expected out-of-order subscription to fail before checkout binds")
    failed = conn.execute("SELECT status FROM arclink_webhook_events WHERE event_id = 'evt_out_of_order_subscription'").fetchone()
    expect(failed["status"] == "failed", str(dict(failed)))

    checkout_payload = json.dumps({
        "id": "evt_out_of_order_checkout",
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": opened["checkout_session_id"],
            "status": "complete",
            "payment_status": "paid",
            "amount_total": 1000,
            "customer": "cus_out_of_order",
            "subscription": "sub_out_of_order",
            "client_reference_id": opened["user_id"],
            "metadata": {"arclink_onboarding_session_id": opened["session_id"]},
        }},
    }, sort_keys=True)
    checkout_result = entitlements.process_stripe_webhook(
        conn,
        payload=checkout_payload,
        signature=sign(adapters, checkout_payload),
        secret="whsec_test",
    )
    expect(checkout_result.entitlement_state == "paid", str(checkout_result))

    replay = entitlements.process_stripe_webhook(
        conn,
        payload=subscription_payload,
        signature=sign(adapters, subscription_payload),
        secret="whsec_test",
    )
    webhook = conn.execute("SELECT status FROM arclink_webhook_events WHERE event_id = 'evt_out_of_order_subscription'").fetchone()
    sub = conn.execute("SELECT user_id, status FROM arclink_subscriptions WHERE stripe_subscription_id = 'sub_out_of_order'").fetchone()
    expect(replay.replayed and replay.user_id == opened["user_id"], str(replay))
    expect(webhook["status"] == "processed", str(dict(webhook)))
    expect(sub["user_id"] == opened["user_id"] and sub["status"] == "active", str(dict(sub)))
    print("PASS test_out_of_order_subscription_replays_after_checkout_binds_subscription")


def test_metadata_only_checkout_does_not_auto_create_paid_user() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_metadata_auto_create_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_entitlement_metadata_auto_create_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_metadata_auto_create_test")
    conn = memory_db(control)
    payload = json.dumps({
        "id": "evt_metadata_auto_create",
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": "cs_metadata_auto_create",
            "status": "complete",
            "payment_status": "paid",
            "amount_total": 1000,
            "customer": "cus_metadata_auto_create",
            "subscription": "sub_metadata_auto_create",
            "metadata": {"arclink_user_id": "arcusr_metadata_auto_create"},
        }},
    }, sort_keys=True)

    try:
        entitlements.process_stripe_webhook(
            conn,
            payload=payload,
            signature=sign(adapters, payload),
            secret="whsec_test",
        )
    except entitlements.ArcLinkEntitlementError as exc:
        expect("local ArcLink user id" in str(exc), str(exc))
    else:
        raise AssertionError("expected metadata-only checkout to fail closed")

    user_count = conn.execute("SELECT COUNT(*) AS n FROM arclink_users WHERE user_id = 'arcusr_metadata_auto_create'").fetchone()["n"]
    paid_count = conn.execute("SELECT COUNT(*) AS n FROM arclink_users WHERE entitlement_state = 'paid'").fetchone()["n"]
    sub_count = conn.execute("SELECT COUNT(*) AS n FROM arclink_subscriptions").fetchone()["n"]
    webhook = conn.execute("SELECT status FROM arclink_webhook_events WHERE event_id = 'evt_metadata_auto_create'").fetchone()
    expect(user_count == 0, str(user_count))
    expect(paid_count == 0, str(paid_count))
    expect(sub_count == 0, str(sub_count))
    expect(webhook["status"] == "failed", str(dict(webhook)))
    print("PASS test_metadata_only_checkout_does_not_auto_create_paid_user")


def test_operator_stripe_entitlement_recovery_dry_run_and_apply_audit() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_recovery_action_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_recovery_action_test")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="arcusr_recovery", entitlement_state="none")
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="arcdep_recovery",
        user_id="arcusr_recovery",
        prefix="recover",
        status="entitlement_required",
    )

    dry_run = entitlements.apply_stripe_entitlement_recovery(
        conn,
        user_id="arcusr_recovery",
        actor_id="operator:alice",
        reason="verified Stripe import evidence",
        stripe_customer_id="cus_recovery_full",
        stripe_subscription_id="sub_recovery_full",
        dry_run=True,
    )
    user = conn.execute("SELECT entitlement_state, stripe_customer_id FROM arclink_users WHERE user_id = 'arcusr_recovery'").fetchone()
    sub_count = conn.execute("SELECT COUNT(*) AS n FROM arclink_subscriptions").fetchone()["n"]
    dry_audit = conn.execute(
        "SELECT metadata_json FROM arclink_audit_log WHERE action = 'stripe_entitlement_recovery_dry_run' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    expect(dry_run["status"] == "planned" and dry_run["dry_run"] is True, str(dry_run))
    expect(user["entitlement_state"] == "none" and user["stripe_customer_id"] == "", str(dict(user)))
    expect(sub_count == 0, str(sub_count))
    expect(dry_audit is not None, "expected dry-run recovery audit")
    expect("cus_recovery_full" not in dry_audit["metadata_json"], dry_audit["metadata_json"])
    expect("sub_recovery_full" not in dry_audit["metadata_json"], dry_audit["metadata_json"])

    applied = entitlements.apply_stripe_entitlement_recovery(
        conn,
        user_id="arcusr_recovery",
        actor_id="operator:alice",
        reason="verified Stripe import evidence",
        stripe_customer_id="cus_recovery_full",
        stripe_subscription_id="sub_recovery_full",
        dry_run=False,
    )
    user = conn.execute("SELECT entitlement_state, stripe_customer_id FROM arclink_users WHERE user_id = 'arcusr_recovery'").fetchone()
    dep = conn.execute("SELECT status FROM arclink_deployments WHERE deployment_id = 'arcdep_recovery'").fetchone()
    sub = conn.execute("SELECT user_id, status FROM arclink_subscriptions WHERE stripe_subscription_id = 'sub_recovery_full'").fetchone()
    applied_audit = conn.execute(
        "SELECT reason, metadata_json FROM arclink_audit_log WHERE action = 'stripe_entitlement_recovery_applied' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    expect(applied["status"] == "applied" and applied["advanced_deployments"] == ("arcdep_recovery",), str(applied))
    expect(user["entitlement_state"] == "paid" and user["stripe_customer_id"] == "cus_recovery_full", str(dict(user)))
    expect(dep["status"] == "provisioning_ready", str(dict(dep)))
    expect(sub["user_id"] == "arcusr_recovery" and sub["status"] == "active", str(dict(sub)))
    expect(applied_audit["reason"] == "verified Stripe import evidence", str(dict(applied_audit)))
    expect("cus_recovery_full" not in applied_audit["metadata_json"], applied_audit["metadata_json"])
    expect("sub_recovery_full" not in applied_audit["metadata_json"], applied_audit["metadata_json"])
    print("PASS test_operator_stripe_entitlement_recovery_dry_run_and_apply_audit")


def test_checkout_onboarding_sync_does_not_commit_before_webhook_processed() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_onboarding_atomic_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_entitlement_onboarding_atomic_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_onboarding_atomic_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_entitlement_atomic_test")
    conn = memory_db(control)
    stripe = adapters.FakeStripeClient()
    session = onboarding.create_or_resume_arclink_onboarding_session(
        conn,
        channel="web",
        channel_identity="atomic-onboarding@example.test",
        session_id="onb_atomic_checkout",
        email_hint="atomic-onboarding@example.test",
        selected_plan_id="starter",
    )
    opened = onboarding.open_arclink_onboarding_checkout(
        conn,
        session_id=session["session_id"],
        stripe_client=stripe,
        price_id="price_starter",
        success_url="https://example.test/success",
        cancel_url="https://example.test/cancel",
        base_domain="example.test",
    )
    payload = json.dumps({
        "id": "evt_onboarding_atomicity",
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": opened["checkout_session_id"],
            "status": "complete",
            "payment_status": "paid",
            "amount_total": 1000,
            "customer": "cus_onboarding_atomicity",
            "subscription": "sub_onboarding_atomicity",
            "client_reference_id": opened["user_id"],
            "metadata": {
                "arclink_user_id": opened["user_id"],
                "arclink_onboarding_session_id": opened["session_id"],
            },
        }},
    }, sort_keys=True)

    original_append_event = entitlements.append_arclink_event

    def fail_processed_event(*args, **kwargs):
        if kwargs.get("event_type") == "stripe_webhook_processed":
            raise RuntimeError("forced onboarding webhook atomicity failure")
        return original_append_event(*args, **kwargs)

    entitlements.append_arclink_event = fail_processed_event
    try:
        try:
            entitlements.process_stripe_webhook(
                conn,
                payload=payload,
                signature=sign(adapters, payload),
                secret="whsec_test",
            )
        except RuntimeError as exc:
            expect("atomicity" in str(exc), str(exc))
        else:
            raise AssertionError("expected forced webhook failure")
    finally:
        entitlements.append_arclink_event = original_append_event

    user = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = ?", (opened["user_id"],)).fetchone()
    dep = conn.execute("SELECT status FROM arclink_deployments WHERE deployment_id = ?", (opened["deployment_id"],)).fetchone()
    onb = conn.execute("SELECT status, checkout_state FROM arclink_onboarding_sessions WHERE session_id = ?", (opened["session_id"],)).fetchone()
    webhook = conn.execute("SELECT status FROM arclink_webhook_events WHERE event_id = 'evt_onboarding_atomicity'").fetchone()
    expect(user["entitlement_state"] == "none", str(dict(user)))
    expect(dep["status"] == "entitlement_required", str(dict(dep)))
    expect(onb["status"] == "checkout_open" and onb["checkout_state"] == "open", str(dict(onb)))
    expect(webhook["status"] == "failed", str(dict(webhook)))
    print("PASS test_checkout_onboarding_sync_does_not_commit_before_webhook_processed")


def test_checkout_onboarding_sync_skip_is_observable() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_onboarding_skip_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_entitlement_onboarding_skip_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_onboarding_skip_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_entitlement_skip_test")
    conn = memory_db(control)
    session = onboarding.create_or_resume_arclink_onboarding_session(
        conn,
        channel="web",
        channel_identity="sync-skip@example.test",
        session_id="onb_sync_skip",
        email_hint="sync-skip@example.test",
    )
    control.upsert_arclink_user(conn, user_id="arcusr_sync_skip", entitlement_state="none")
    conn.execute(
        "UPDATE arclink_onboarding_sessions SET user_id = ? WHERE session_id = ?",
        ("arcusr_sync_skip", session["session_id"]),
    )
    conn.commit()
    payload = json.dumps({
        "id": "evt_onboarding_sync_skip",
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": "cs_onboarding_sync_skip",
            "status": "complete",
            "payment_status": "paid",
            "amount_total": 1000,
            "customer": "cus_onboarding_sync_skip",
            "subscription": "sub_onboarding_sync_skip",
            "client_reference_id": "arcusr_sync_skip",
            "metadata": {
                "arclink_user_id": "arcusr_sync_skip",
                "arclink_onboarding_session_id": session["session_id"],
            },
        }},
    }, sort_keys=True)

    result = entitlements.process_stripe_webhook(
        conn,
        payload=payload,
        signature=sign(adapters, payload),
        secret="whsec_test",
    )

    event = conn.execute(
        """
        SELECT subject_kind, subject_id, event_type, metadata_json
        FROM arclink_events
        WHERE event_type = 'stripe_onboarding_sync_skipped'
        """,
    ).fetchone()
    webhook = conn.execute("SELECT status FROM arclink_webhook_events WHERE event_id = 'evt_onboarding_sync_skip'").fetchone()
    expect(result.entitlement_state == "paid", str(result))
    expect(webhook["status"] == "processed", str(dict(webhook)))
    expect(event is not None, "expected skipped onboarding sync event")
    expect(event["subject_kind"] == "onboarding_session" and event["subject_id"] == session["session_id"], str(dict(event)))
    metadata = json.loads(event["metadata_json"])
    expect(metadata["reason"] == "missing_or_unprovisionable_onboarding_deployment", str(metadata))
    print("PASS test_checkout_onboarding_sync_skip_is_observable")


def test_subscription_created_sets_paid_and_mirrors_subscription() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_sub_created_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_entitlement_sub_created_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_sub_created_test")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_1", stripe_customer_id="cus_test", entitlement_state="none")
    control.reserve_arclink_deployment_prefix(
        conn, deployment_id="dep_1", user_id="user_1",
        prefix="sub-created", status="entitlement_required",
    )
    payload = stripe_payload(
        event_id="evt_sub_created", event_type="customer.subscription.created",
        status="active",
    )
    result = entitlements.process_stripe_webhook(
        conn, payload=payload, signature=sign(adapters, payload), secret="whsec_test",
    )
    expect(result.entitlement_state == "paid", str(result))
    expect(result.advanced_deployments == ("dep_1",), str(result))
    user = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = 'user_1'").fetchone()
    expect(user["entitlement_state"] == "paid", str(dict(user)))
    sub = conn.execute("SELECT status FROM arclink_subscriptions WHERE stripe_subscription_id = 'sub_test'").fetchone()
    expect(sub["status"] == "active", str(dict(sub)))
    print("PASS test_subscription_created_sets_paid_and_mirrors_subscription")


def test_unknown_subscription_status_mirrors_as_incomplete_without_crashing() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_sub_unknown_status_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_entitlement_sub_unknown_status_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_sub_unknown_status_test")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_unknown_status", stripe_customer_id="cus_unknown_status", entitlement_state="paid")
    payload = stripe_payload(
        event_id="evt_sub_unknown_status",
        event_type="customer.subscription.updated",
        user_id="user_unknown_status",
        subscription_id="sub_unknown_status",
        customer_id="cus_unknown_status",
        status="mystery_status",
    )

    result = entitlements.process_stripe_webhook(
        conn,
        payload=payload,
        signature=sign(adapters, payload),
        secret="whsec_test",
    )

    user = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = 'user_unknown_status'").fetchone()
    sub = conn.execute(
        "SELECT status FROM arclink_subscriptions WHERE stripe_subscription_id = 'sub_unknown_status'"
    ).fetchone()
    webhook = conn.execute("SELECT status FROM arclink_webhook_events WHERE event_id = 'evt_sub_unknown_status'").fetchone()
    expect(result.entitlement_state == "none", str(result))
    expect(user["entitlement_state"] == "none", str(dict(user)))
    expect(sub["status"] == "incomplete", str(dict(sub)))
    expect(webhook["status"] == "processed", str(dict(webhook)))
    print("PASS test_unknown_subscription_status_mirrors_as_incomplete_without_crashing")


def test_subscription_deleted_cancels_entitlement_and_audits() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_sub_deleted_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_entitlement_sub_deleted_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_sub_deleted_test")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_1", stripe_customer_id="cus_test", entitlement_state="paid")
    control.reserve_arclink_deployment_prefix(
        conn, deployment_id="dep_1", user_id="user_1",
        prefix="sub-deleted", status="provisioning_ready",
    )
    payload = stripe_payload(
        event_id="evt_sub_deleted", event_type="customer.subscription.deleted",
        status="canceled",
    )
    result = entitlements.process_stripe_webhook(
        conn, payload=payload, signature=sign(adapters, payload), secret="whsec_test",
    )
    expect(result.entitlement_state == "cancelled", str(result))
    user = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = 'user_1'").fetchone()
    expect(user["entitlement_state"] == "cancelled", str(dict(user)))
    sub = conn.execute("SELECT status FROM arclink_subscriptions WHERE stripe_subscription_id = 'sub_test'").fetchone()
    expect(sub["status"] == "canceled", str(dict(sub)))
    audit = conn.execute("SELECT action FROM arclink_audit_log WHERE target_id = 'user_1'").fetchone()
    expect(audit["action"] == "payment_entitlement_blocked", str(dict(audit)))
    # Replay is idempotent
    replay = entitlements.process_stripe_webhook(
        conn, payload=payload, signature=sign(adapters, payload), secret="whsec_test",
    )
    expect(replay.replayed, str(replay))
    print("PASS test_subscription_deleted_cancels_entitlement_and_audits")


def test_stripe_webhook_merges_users_when_email_matches_existing_account() -> None:
    """A single human can show up under multiple user_ids: e.g. they started
    on Telegram earlier under one user_id (with their email captured), then
    onboarded again on web under a fresh user_id (without an email). When
    Stripe webhook arrives carrying the canonical email, the webhook must
    re-bind to the existing email-owning user_id and re-point any deployment
    rather than crashing on the email unique constraint.
    """
    control = load_module("arclink_control.py", "arclink_control_entitlement_merge_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_merge_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_entitlement_merge_test")
    conn = memory_db(control)

    secret = "whsec_test_merge"
    # Pre-existing email-owning user (from an earlier Telegram session).
    control.upsert_arclink_user(
        conn,
        user_id="arcusr_existing_email",
        email="captain@example.test",
        entitlement_state="none",
    )
    # Fresh web-onboarding user_id (no email yet) plus a reserved deployment.
    control.upsert_arclink_user(
        conn,
        user_id="arcusr_fresh_web",
        entitlement_state="none",
    )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="arcdep_fresh_web",
        user_id="arcusr_fresh_web",
        prefix="freshweb",
        status="entitlement_required",
    )

    # Stripe webhook carries the canonical email and references the fresh web user_id.
    payload = json.dumps({
        "id": "evt_merge_1",
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": "cs_merge_1",
            "payment_status": "paid",
            "amount_total": 1000,
            "customer": "cus_merge_1",
            "subscription": "sub_merge_1",
            "client_reference_id": "arcusr_fresh_web",
            "customer_details": {"email": "captain@example.test"},
            "metadata": {"arclink_user_id": "arcusr_fresh_web"},
        }},
    }, sort_keys=True)
    sig = adapters.sign_stripe_webhook(payload, secret)

    result = entitlements.process_stripe_webhook(conn, payload=payload, signature=sig, secret=secret)
    expect(result.user_id == "arcusr_existing_email", f"expected merge into existing email user, got {result.user_id}")
    expect(result.entitlement_state == "paid", f"expected paid, got {result.entitlement_state}")

    # The existing user now owns the deployment.
    dep = conn.execute(
        "SELECT user_id, status FROM arclink_deployments WHERE deployment_id = 'arcdep_fresh_web'"
    ).fetchone()
    expect(dep["user_id"] == "arcusr_existing_email", f"deployment user_id not re-pointed: {dep['user_id']}")

    # Existing user has its entitlement flipped and email preserved.
    user = conn.execute(
        "SELECT email, entitlement_state FROM arclink_users WHERE user_id = 'arcusr_existing_email'"
    ).fetchone()
    expect(user["email"] == "captain@example.test", f"existing user email lost: {user['email']}")
    expect(user["entitlement_state"] == "paid", f"existing user entitlement: {user['entitlement_state']}")

    # The fresh web user_id stays in the table (no orphan rows produced) but
    # has no deployment any more.
    fresh_dep = conn.execute(
        "SELECT COUNT(*) AS c FROM arclink_deployments WHERE user_id = 'arcusr_fresh_web'"
    ).fetchone()
    expect(fresh_dep["c"] == 0, f"expected no deployments left under fresh web user, got {fresh_dep['c']}")

    # An audit-style event records the merge for operators.
    merge_event = conn.execute(
        "SELECT subject_id, metadata_json FROM arclink_events WHERE event_type = 'stripe_user_merged' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    expect(merge_event is not None, "expected stripe_user_merged event")
    expect(merge_event["subject_id"] == "arcusr_existing_email", str(merge_event["subject_id"]))

    print("PASS test_stripe_webhook_merges_users_when_email_matches_existing_account")


def test_entitlement_webhook_rejects_customer_bound_to_another_account() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_customer_conflict_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_entitlement_customer_conflict_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_customer_conflict_test")
    conn = memory_db(control)
    control.upsert_arclink_user(
        conn,
        user_id="user_customer_owner",
        stripe_customer_id="cus_conflict",
        entitlement_state="none",
    )
    control.upsert_arclink_user(conn, user_id="user_metadata_target", entitlement_state="none")
    payload = stripe_payload(
        event_id="evt_customer_conflict",
        event_type="customer.subscription.updated",
        user_id="user_metadata_target",
        subscription_id="sub_customer_conflict",
        customer_id="cus_conflict",
        status="active",
    )

    try:
        entitlements.process_stripe_webhook(
            conn,
            payload=payload,
            signature=sign(adapters, payload),
            secret="whsec_test",
        )
    except entitlements.ArcLinkEntitlementError as exc:
        expect("another ArcLink account" in str(exc), str(exc))
    else:
        raise AssertionError("expected customer conflict to fail")

    owner = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = 'user_customer_owner'").fetchone()
    target = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = 'user_metadata_target'").fetchone()
    sub_count = conn.execute("SELECT COUNT(*) AS n FROM arclink_subscriptions").fetchone()["n"]
    webhook = conn.execute("SELECT status FROM arclink_webhook_events WHERE event_id = 'evt_customer_conflict'").fetchone()
    expect(owner["entitlement_state"] == "none", str(dict(owner)))
    expect(target["entitlement_state"] == "none", str(dict(target)))
    expect(sub_count == 0, str(sub_count))
    expect(webhook["status"] == "failed", str(dict(webhook)))
    print("PASS test_entitlement_webhook_rejects_customer_bound_to_another_account")


def test_reconciliation_drift_detects_subscription_without_deployment_and_vice_versa() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_drift_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_drift_test")
    conn = memory_db(control)

    # No drift when empty
    expect(entitlements.detect_stripe_reconciliation_drift(conn) == [], "expected no drift")

    # Active subscription without deployment
    control.upsert_arclink_user(conn, user_id="user_sub_only", entitlement_state="paid")
    control.upsert_arclink_subscription_mirror(
        conn, subscription_id="stripe:sub_1", user_id="user_sub_only",
        stripe_customer_id="cus_1", stripe_subscription_id="sub_1",
        status="active", current_period_end="", raw={},
    )
    drift = entitlements.detect_stripe_reconciliation_drift(conn)
    sub_drifts = [d for d in drift if d.kind == "subscription_without_deployment"]
    expect(len(sub_drifts) == 1, str(drift))
    expect(sub_drifts[0].user_id == "user_sub_only", str(sub_drifts[0]))

    # Active deployment without subscription (and not comp)
    control.upsert_arclink_user(conn, user_id="user_dep_only", entitlement_state="paid")
    control.reserve_arclink_deployment_prefix(
        conn, deployment_id="dep_orphan", user_id="user_dep_only",
        prefix="orphan", status="provisioning_ready",
    )
    drift = entitlements.detect_stripe_reconciliation_drift(conn)
    dep_drifts = [d for d in drift if d.kind == "deployment_without_subscription"]
    expect(len(dep_drifts) == 1, str(drift))
    expect(dep_drifts[0].user_id == "user_dep_only", str(dep_drifts[0]))

    # Non-live deployment states should not create false orphaned-deployment drift.
    for status in (
        "reserved",
        "entitlement_required",
        "provisioning_failed",
        "teardown_requested",
        "teardown_running",
        "teardown_complete",
        "teardown_failed",
        "torn_down",
        "cancelled",
    ):
        user_id = f"user_non_live_{status}"
        control.upsert_arclink_user(conn, user_id=user_id, entitlement_state="paid")
        control.reserve_arclink_deployment_prefix(
            conn,
            deployment_id=f"dep_non_live_{status}",
            user_id=user_id,
            prefix=f"nl-{status.replace('_', '-')[:14]}",
            status=status,
        )
    drift = entitlements.detect_stripe_reconciliation_drift(conn)
    non_live_drifts = [d for d in drift if d.user_id.startswith("user_non_live_")]
    expect(len(non_live_drifts) == 0, str(drift))

    # Past-due subscriptions are owed-service drift, not orphaned deployment drift.
    control.upsert_arclink_user(conn, user_id="user_past_due", entitlement_state="past_due")
    control.reserve_arclink_deployment_prefix(
        conn, deployment_id="dep_past_due", user_id="user_past_due",
        prefix="past-due", status="provisioning_ready",
    )
    control.upsert_arclink_subscription_mirror(
        conn, subscription_id="stripe:sub_past_due", user_id="user_past_due",
        stripe_customer_id="cus_past_due", stripe_subscription_id="sub_past_due",
        status="past_due", current_period_end="", raw={},
    )
    drift = entitlements.detect_stripe_reconciliation_drift(conn)
    owed_drifts = [d for d in drift if d.kind == "deployment_subscription_owed_service" and d.user_id == "user_past_due"]
    orphan_drifts = [d for d in drift if d.kind == "deployment_without_subscription" and d.user_id == "user_past_due"]
    expect(len(owed_drifts) == 1, str(drift))
    expect(len(orphan_drifts) == 0, str(drift))

    # Comp user with deployment should not show drift
    control.upsert_arclink_user(conn, user_id="user_comp", entitlement_state="comp")
    control.reserve_arclink_deployment_prefix(
        conn, deployment_id="dep_comp", user_id="user_comp",
        prefix="comp-ok", status="provisioning_ready",
    )
    drift = entitlements.detect_stripe_reconciliation_drift(conn)
    comp_drifts = [d for d in drift if d.user_id == "user_comp"]
    expect(len(comp_drifts) == 0, str(drift))

    print("PASS test_reconciliation_drift_detects_subscription_without_deployment_and_vice_versa")


def main() -> int:
    test_stripe_webhook_verifier_rejects_blank_secret_and_accepts_fixture()
    test_stripe_webhook_verifier_accepts_any_matching_v1_signature()
    test_stripe_webhook_rejects_signature_mismatch()
    test_paid_webhook_is_idempotent_and_lifts_entitlement_gate()
    test_failed_webhook_row_can_be_replayed_after_payload_fix()
    test_received_webhook_row_is_reprocessed_instead_of_silently_acknowledged()
    test_failed_payment_keeps_gate_blocked_and_audits_reason()
    test_supported_webhook_failure_rolls_back_entitlement_side_effects()
    test_stripe_webhook_rejects_caller_owned_transaction_without_rollback()
    test_invoice_success_sets_paid_and_lifts_entitlement_gate()
    test_invoice_success_reads_nested_parent_subscription_details()
    test_unsupported_signed_event_does_not_mutate_paid_entitlement()
    test_manual_comp_requires_reason_and_lifts_gate()
    test_profile_only_upsert_preserves_paid_and_comp_entitlements()
    test_new_user_without_explicit_entitlement_defaults_to_none()
    test_targeted_comp_advances_only_named_deployment_without_global_comp()
    test_refuel_credit_uses_fair_local_accounting_without_live_purchase()
    test_refuel_credit_source_id_is_idempotent()
    test_refuel_credit_concurrent_spend_does_not_overspend()
    test_refuel_credit_rejects_empty_and_wrong_owner_targets()
    test_refuel_checkout_session_completed_grants_and_applies_credit()
    test_refuel_checkout_rejects_unpaid_or_underpaid_session()
    test_refuel_checkout_rejects_mismatched_stripe_customer()
    test_invoice_payment_tops_up_subscription_inference_allowance_once()
    test_checkout_session_completed_rejects_unpaid_subscription_checkout()
    test_checkout_session_completed_lifts_entitlement_and_syncs_onboarding()
    test_unbound_subscription_metadata_cannot_first_bind_or_create_user()
    test_checkout_session_completed_binds_by_local_checkout_session_id_without_metadata()
    test_out_of_order_subscription_replays_after_checkout_binds_subscription()
    test_metadata_only_checkout_does_not_auto_create_paid_user()
    test_operator_stripe_entitlement_recovery_dry_run_and_apply_audit()
    test_checkout_onboarding_sync_does_not_commit_before_webhook_processed()
    test_checkout_onboarding_sync_skip_is_observable()
    test_subscription_created_sets_paid_and_mirrors_subscription()
    test_unknown_subscription_status_mirrors_as_incomplete_without_crashing()
    test_subscription_deleted_cancels_entitlement_and_audits()
    test_reconciliation_drift_detects_subscription_without_deployment_and_vice_versa()
    test_stripe_webhook_merges_users_when_email_matches_existing_account()
    test_entitlement_webhook_rejects_customer_bound_to_another_account()
    print("PASS all 39 ArcLink entitlement tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
