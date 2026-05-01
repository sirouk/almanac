#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import time
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


def sign(adapters, payload: str) -> str:
    return adapters.sign_stripe_webhook(payload, "whsec_test", timestamp=int(time.time()))


def checkout_completed_payload(session: dict[str, str], *, event_id: str = "evt_checkout_done") -> str:
    obj = {
        "id": session["checkout_session_id"],
        "customer": "cus_onboarding",
        "subscription": "sub_onboarding",
        "client_reference_id": session["user_id"],
        "metadata": {
            "arclink_user_id": session["user_id"],
            "arclink_onboarding_session_id": session["session_id"],
            "arclink_deployment_id": session["deployment_id"],
        },
    }
    return json.dumps({"id": event_id, "type": "checkout.session.completed", "data": {"object": obj}}, sort_keys=True)


def test_public_onboarding_sessions_resume_without_duplicate_active_rows() -> None:
    control = load_module("almanac_control.py", "almanac_control_onboarding_resume_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_resume_test")
    conn = memory_db(control)
    first = onboarding.create_or_resume_arclink_onboarding_session(
        conn,
        channel="web",
        channel_identity="person@example.test",
        email_hint="person@example.test",
        selected_plan_id="starter",
    )
    second = onboarding.create_or_resume_arclink_onboarding_session(
        conn,
        channel="web",
        channel_identity="PERSON@example.test",
        selected_model_id="moonshotai/Kimi-K2.6-TEE",
    )
    expect(second["session_id"] == first["session_id"], str((first, second)))
    answered = onboarding.answer_arclink_onboarding_question(
        conn,
        session_id=first["session_id"],
        question_key="model",
        answer_summary="selected default model",
        selected_model_id="moonshotai/Kimi-K2.6-TEE",
    )
    expect(answered["status"] == "collecting", str(answered))
    count = conn.execute("SELECT COUNT(*) AS n FROM arclink_onboarding_sessions").fetchone()["n"]
    started_events = conn.execute(
        "SELECT COUNT(*) AS n FROM arclink_onboarding_events WHERE event_type = 'started'"
    ).fetchone()["n"]
    question_events = conn.execute(
        "SELECT COUNT(*) AS n FROM arclink_onboarding_events WHERE event_type = 'question_answered'"
    ).fetchone()["n"]
    expect(count == 1 and started_events == 1, f"count={count} started={started_events}")
    expect(question_events == 1, str(question_events))
    for channel, identity in (("telegram", "tg:12345"), ("discord", "discord:67890")):
        row = onboarding.create_or_resume_arclink_onboarding_session(
            conn,
            channel=channel,
            channel_identity=identity,
        )
        expect(row["channel"] == channel, str(row))
    print("PASS test_public_onboarding_sessions_resume_without_duplicate_active_rows")


def test_fake_checkout_is_deterministic_and_cancel_expire_keep_provisioning_blocked() -> None:
    control = load_module("almanac_control.py", "almanac_control_onboarding_checkout_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_onboarding_checkout_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_checkout_test")
    conn = memory_db(control)
    stripe = adapters.FakeStripeClient()
    session = onboarding.create_or_resume_arclink_onboarding_session(
        conn,
        channel="web",
        channel_identity="buyer@example.test",
        session_id="onb_checkout",
        email_hint="buyer@example.test",
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
    reopened = onboarding.open_arclink_onboarding_checkout(
        conn,
        session_id=session["session_id"],
        stripe_client=stripe,
        price_id="price_starter",
        success_url="https://example.test/success",
        cancel_url="https://example.test/cancel",
        base_domain="example.test",
    )
    expect(opened["checkout_session_id"] == reopened["checkout_session_id"], str((opened, reopened)))
    expect(opened["checkout_url"].endswith(opened["checkout_session_id"]), str(opened))
    cancelled = onboarding.mark_arclink_onboarding_checkout_cancelled(
        conn,
        session_id=session["session_id"],
        reason="customer_returned",
    )
    expect(cancelled["status"] == "payment_cancelled", str(cancelled))
    dep = conn.execute(
        "SELECT status FROM arclink_deployments WHERE deployment_id = ?",
        (opened["deployment_id"],),
    ).fetchone()
    expect(dep["status"] == "entitlement_required", str(dict(dep)))

    replacement = onboarding.create_or_resume_arclink_onboarding_session(
        conn,
        channel="web",
        channel_identity="buyer@example.test",
        session_id="onb_checkout_retry",
    )
    expect(replacement["session_id"] != session["session_id"], str(replacement))
    opened_expiring = onboarding.open_arclink_onboarding_checkout(
        conn,
        session_id=replacement["session_id"],
        stripe_client=stripe,
        price_id="price_starter",
        success_url="https://example.test/success",
        cancel_url="https://example.test/cancel",
    )
    expired = onboarding.mark_arclink_onboarding_checkout_expired(conn, session_id=replacement["session_id"])
    expect(expired["status"] == "payment_expired", str(expired))
    dep2 = conn.execute(
        "SELECT status FROM arclink_deployments WHERE deployment_id = ?",
        (opened_expiring["deployment_id"],),
    ).fetchone()
    events = {
        row["event_type"]
        for row in conn.execute("SELECT event_type FROM arclink_onboarding_events").fetchall()
    }
    expect(dep2["status"] == "entitlement_required", str(dict(dep2)))
    expect({"checkout_opened", "payment_cancelled", "payment_expired"} <= events, str(events))
    print("PASS test_fake_checkout_is_deterministic_and_cancel_expire_keep_provisioning_blocked")


def test_successful_checkout_uses_entitlement_gate_before_provisioning_ready() -> None:
    control = load_module("almanac_control.py", "almanac_control_onboarding_success_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_onboarding_success_test")
    entitlements = load_module("arclink_entitlements.py", "arclink_entitlements_onboarding_success_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_success_test")
    provisioning = load_module("arclink_provisioning.py", "arclink_provisioning_onboarding_success_test")
    conn = memory_db(control)
    stripe = adapters.FakeStripeClient()
    session = onboarding.create_or_resume_arclink_onboarding_session(
        conn,
        channel="telegram",
        channel_identity="tg:4242",
        session_id="onb_paid",
        selected_plan_id="starter",
        selected_model_id="moonshotai/Kimi-K2.6-TEE",
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
    blocked = provisioning.render_arclink_provisioning_dry_run(
        conn,
        deployment_id=opened["deployment_id"],
        idempotency_key="onboarding-before-pay",
    )
    expect(not blocked["intent"]["execution"]["ready"], str(blocked["intent"]["execution"]))
    payload = checkout_completed_payload(opened)
    result = entitlements.process_stripe_webhook(conn, payload=payload, signature=sign(adapters, payload), secret="whsec_test")
    expect(result.entitlement_state == "paid", str(result))
    ready_session = conn.execute(
        "SELECT status, checkout_state FROM arclink_onboarding_sessions WHERE session_id = 'onb_paid'"
    ).fetchone()
    ready_dep = conn.execute(
        "SELECT status FROM arclink_deployments WHERE deployment_id = ?",
        (opened["deployment_id"],),
    ).fetchone()
    expect(ready_session["status"] == "provisioning_ready" and ready_session["checkout_state"] == "paid", str(dict(ready_session)))
    expect(ready_dep["status"] == "provisioning_ready", str(dict(ready_dep)))
    ready = provisioning.render_arclink_provisioning_dry_run(
        conn,
        deployment_id=opened["deployment_id"],
        idempotency_key="onboarding-after-pay",
    )
    expect(ready["intent"]["execution"]["ready"], str(ready["intent"]["execution"]))
    events = {
        row["event_type"]
        for row in conn.execute("SELECT event_type FROM arclink_onboarding_events WHERE session_id = 'onb_paid'").fetchall()
    }
    expect({"payment_success", "provisioning_requested"} <= events, str(events))
    print("PASS test_successful_checkout_uses_entitlement_gate_before_provisioning_ready")


def test_channel_handoff_keeps_public_state_separate_from_private_bot_tokens() -> None:
    control = load_module("almanac_control.py", "almanac_control_onboarding_handoff_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_handoff_test")
    conn = memory_db(control)
    source = onboarding.create_or_resume_arclink_onboarding_session(
        conn,
        channel="web",
        channel_identity="handoff@example.test",
        session_id="onb_handoff",
        email_hint="handoff@example.test",
        selected_plan_id="starter",
    )
    prepared = onboarding.prepare_arclink_onboarding_deployment(
        conn,
        session_id=source["session_id"],
        base_domain="example.test",
    )
    target = onboarding.handoff_arclink_onboarding_channel(
        conn,
        source_session_id=source["session_id"],
        target_channel="discord",
        target_channel_identity="discord:abc123",
    )
    expect(target["deployment_id"] == prepared["deployment_id"], str(target))
    resumed = onboarding.handoff_arclink_onboarding_channel(
        conn,
        source_session_id=source["session_id"],
        target_channel="discord",
        target_channel_identity="discord:abc123",
    )
    expect(resumed["session_id"] == target["session_id"], str((target, resumed)))
    try:
        onboarding.create_or_resume_arclink_onboarding_session(
            conn,
            channel="telegram",
            channel_identity="tg:token-test",
            metadata={"telegram_bot_token": "123456:abcdefghijklmnopqrstuvwxyz123456"},
        )
    except onboarding.ArcLinkOnboardingError as exc:
        expect("secret material" in str(exc), str(exc))
    else:
        raise AssertionError("expected public onboarding metadata to reject bot tokens")
    stored = json.dumps(
        [dict(row) for row in conn.execute("SELECT * FROM arclink_onboarding_sessions").fetchall()],
        sort_keys=True,
    )
    expect("bot_token" not in stored and "123456:" not in stored, stored)
    print("PASS test_channel_handoff_keeps_public_state_separate_from_private_bot_tokens")


def test_prepare_onboarding_preserves_existing_entitlement() -> None:
    control = load_module("almanac_control.py", "almanac_control_onboarding_entitlement_preserve_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_entitlement_preserve_test")
    conn = memory_db(control)
    session = onboarding.create_or_resume_arclink_onboarding_session(
        conn,
        channel="web",
        channel_identity="returning@example.test",
        session_id="onb_returning",
        email_hint="old-returning@example.test",
        display_name_hint="Old Returning",
        selected_plan_id="starter",
    )
    user_id = "arcusr_789a0a5804347d61fd"
    paid_user = control.upsert_arclink_user(conn, user_id=user_id, entitlement_state="paid")

    prepared = onboarding.prepare_arclink_onboarding_deployment(
        conn,
        session_id=session["session_id"],
        base_domain="example.test",
    )
    resumed = onboarding.prepare_arclink_onboarding_deployment(
        conn,
        session_id=session["session_id"],
        base_domain="example.test",
    )

    user = conn.execute(
        "SELECT email, display_name, entitlement_state, entitlement_updated_at FROM arclink_users WHERE user_id = ?",
        (prepared["user_id"],),
    ).fetchone()
    expect(prepared["user_id"] == user_id, str(prepared))
    expect(resumed["deployment_id"] == prepared["deployment_id"], str((prepared, resumed)))
    expect(user["email"] == "old-returning@example.test", str(dict(user)))
    expect(user["display_name"] == "Old Returning", str(dict(user)))
    expect(user["entitlement_state"] == "paid", str(dict(user)))
    expect(user["entitlement_updated_at"] == paid_user["entitlement_updated_at"], str(dict(user)))
    print("PASS test_prepare_onboarding_preserves_existing_entitlement")


def main() -> int:
    test_public_onboarding_sessions_resume_without_duplicate_active_rows()
    test_fake_checkout_is_deterministic_and_cancel_expire_keep_provisioning_blocked()
    test_successful_checkout_uses_entitlement_gate_before_provisioning_ready()
    test_channel_handoff_keeps_public_state_separate_from_private_bot_tokens()
    test_prepare_onboarding_preserves_existing_entitlement()
    print("PASS all 5 ArcLink onboarding tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
