#!/usr/bin/env python3
from __future__ import annotations

import json

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
    control.upsert_arclink_user(conn, user_id="user_1", entitlement_state="none")
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
    control.upsert_arclink_user(conn, user_id="user_1", entitlement_state="none")
    bad_payload = json.dumps(
        {
            "id": "evt_replay_failed",
            "type": "customer.subscription.updated",
            "data": {"object": {"id": "sub_test", "customer": "cus_test", "status": "active", "metadata": {}}},
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


def test_failed_payment_keeps_gate_blocked_and_audits_reason() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_failed_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_entitlement_failed_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_failed_test")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_1", entitlement_state="none")
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
    control.upsert_arclink_user(conn, user_id="user_1", entitlement_state="none")
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
    control.upsert_arclink_user(conn, user_id="user_1", entitlement_state="none")
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
    control.upsert_arclink_user(conn, user_id="user_nested", entitlement_state="none")
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
    control.upsert_arclink_user(conn, user_id="user_1", entitlement_state="none")
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
    control.upsert_arclink_user(conn, user_id="user_1", entitlement_state="none")
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
        display_name_hint="Checkout User", selected_plan_id="starter",
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
    onb = conn.execute("SELECT checkout_session_id, stripe_customer_id FROM arclink_onboarding_sessions WHERE session_id = ?", (session["session_id"],)).fetchone()
    expect(onb["checkout_session_id"] == "cs_test_checkout", str(dict(onb)))
    expect(onb["stripe_customer_id"] == "cus_checkout", str(dict(onb)))
    print("PASS test_checkout_session_completed_lifts_entitlement_and_syncs_onboarding")


def test_subscription_created_sets_paid_and_mirrors_subscription() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_sub_created_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_entitlement_sub_created_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_sub_created_test")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_1", entitlement_state="none")
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


def test_subscription_deleted_cancels_entitlement_and_audits() -> None:
    control = load_module("arclink_control.py", "arclink_control_entitlement_sub_deleted_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_entitlement_sub_deleted_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_sub_deleted_test")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_1", entitlement_state="paid")
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
    test_stripe_webhook_rejects_signature_mismatch()
    test_paid_webhook_is_idempotent_and_lifts_entitlement_gate()
    test_failed_webhook_row_can_be_replayed_after_payload_fix()
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
    test_checkout_session_completed_lifts_entitlement_and_syncs_onboarding()
    test_subscription_created_sets_paid_and_mirrors_subscription()
    test_subscription_deleted_cancels_entitlement_and_audits()
    test_reconciliation_drift_detects_subscription_without_deployment_and_vice_versa()
    print("PASS all 18 ArcLink entitlement tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
