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


def seed_paid_deployment(control, onboarding, conn):
    session = onboarding.create_or_resume_arclink_onboarding_session(
        conn,
        channel="web",
        channel_identity="api-user@example.test",
        session_id="onb_api_auth",
        email_hint="api-user@example.test",
        display_name_hint="API User",
        selected_plan_id="starter",
        selected_model_id="model-api",
    )
    prepared = onboarding.prepare_arclink_onboarding_deployment(
        conn,
        session_id=session["session_id"],
        base_domain="example.test",
        prefix="opal-vault-1a2b",
    )
    control.set_arclink_user_entitlement(conn, user_id=prepared["user_id"], entitlement_state="paid")
    control.upsert_arclink_service_health(
        conn,
        deployment_id=prepared["deployment_id"],
        service_name="qmd-mcp",
        status="healthy",
    )
    return prepared


def test_sessions_store_hashes_and_user_api_is_scoped_to_principal() -> None:
    control = load_module("almanac_control.py", "almanac_control_api_auth_user_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_api_auth_user_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_user_test")
    conn = memory_db(control)
    prepared = seed_paid_deployment(control, onboarding, conn)

    session = api.create_arclink_user_session(
        conn,
        user_id=prepared["user_id"],
        metadata={"surface": "browser"},
        session_id="usess_api",
    )
    stored = conn.execute("SELECT * FROM arclink_user_sessions WHERE session_id = 'usess_api'").fetchone()
    expect(session["session_token"] not in json.dumps(dict(stored)), str(dict(stored)))
    expect(session["csrf_token"] not in json.dumps(dict(stored)), str(dict(stored)))

    view = api.read_user_dashboard_api(
        conn,
        session_id=session["session_id"],
        session_token=session["session_token"],
    )
    expect(view.status == 200, str(view))
    expect(view.payload["user"]["user_id"] == prepared["user_id"], str(view.payload))
    try:
        api.read_user_dashboard_api(
            conn,
            session_id=session["session_id"],
            session_token=session["session_token"],
            user_id="arcusr_other",
        )
    except api.ArcLinkApiAuthError as exc:
        expect("another user" in str(exc), str(exc))
    else:
        raise AssertionError("expected cross-user dashboard read to fail")
    print("PASS test_sessions_store_hashes_and_user_api_is_scoped_to_principal")


def test_public_onboarding_api_rate_limits_and_reuses_shared_contract() -> None:
    control = load_module("almanac_control.py", "almanac_control_api_auth_onboarding_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_api_auth_onboarding_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_onboarding_test")
    conn = memory_db(control)
    stripe = adapters.FakeStripeClient()

    started = api.start_public_onboarding_api(
        conn,
        channel="discord",
        channel_identity="discord:api-user",
        email_hint="bot-api@example.test",
        selected_plan_id="starter",
    )
    answered = api.answer_public_onboarding_api(
        conn,
        session_id=started.payload["session"]["session_id"],
        question_key="name",
        answer_summary="display name captured",
        display_name_hint="Bot API User",
    )
    checkout = api.open_public_onboarding_checkout_api(
        conn,
        session_id=started.payload["session"]["session_id"],
        stripe_client=stripe,
        price_id="price_starter",
        success_url="https://example.test/success",
        cancel_url="https://example.test/cancel",
        base_domain="example.test",
    )
    expect(started.status == 201 and answered.status == 200 and checkout.status == 200, str((started, answered, checkout)))
    expect(checkout.payload["session"]["checkout_url"].startswith("https://stripe.test/checkout/"), str(checkout.payload))
    for _ in range(5):
        api.start_public_onboarding_api(conn, channel="discord", channel_identity="discord:limited")
    try:
        api.start_public_onboarding_api(conn, channel="discord", channel_identity="discord:limited")
    except api.ArcLinkApiAuthError as exc:
        expect("rate limit" in str(exc), str(exc))
    else:
        raise AssertionError("expected public onboarding rate limit to fail")
    print("PASS test_public_onboarding_api_rate_limits_and_reuses_shared_contract")


def test_public_onboarding_api_rejects_invalid_channel_before_rate_limit() -> None:
    control = load_module("almanac_control.py", "almanac_control_api_auth_invalid_onboarding_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_invalid_onboarding_test")
    conn = memory_db(control)

    try:
        api.start_public_onboarding_api(conn, channel="email", channel_identity="bad@example.test")
    except Exception as exc:
        expect(type(exc).__name__ == "ArcLinkOnboardingError", str(exc))
        expect("unsupported ArcLink onboarding channel" in str(exc), str(exc))
    else:
        raise AssertionError("expected unsupported public onboarding channel to fail")
    rate_limit_count = conn.execute("SELECT COUNT(*) AS n FROM rate_limits").fetchone()["n"]
    expect(rate_limit_count == 0, f"invalid public onboarding channel wrote {rate_limit_count} rate-limit rows")
    print("PASS test_public_onboarding_api_rejects_invalid_channel_before_rate_limit")


def test_admin_api_requires_csrf_reason_idempotency_and_mfa_ready_schema() -> None:
    control = load_module("almanac_control.py", "almanac_control_api_auth_admin_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_api_auth_admin_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_admin_test")
    conn = memory_db(control)
    prepared = seed_paid_deployment(control, onboarding, conn)
    admin = api.upsert_arclink_admin(
        conn,
        admin_id="admin_api",
        email="admin@example.test",
        role="ops",
        role_scope={"deployments": ["*"]},
    )
    expect(admin["role"] == "ops" and not admin["totp_enabled"], str(admin))
    api.enroll_arclink_admin_totp_factor(
        conn,
        admin_id="admin_api",
        factor_id="totp_api",
        secret_ref="secret://arclink/admin/admin_api/totp",
    )
    verified_admin = api.verify_arclink_admin_totp_factor(conn, factor_id="totp_api")
    expect(verified_admin["totp"]["enabled"] and verified_admin["totp"]["secret_ref"] == "secret://masked", str(verified_admin))

    read_session = api.create_arclink_admin_session(conn, admin_id="admin_api", session_id="asess_read")
    read_view = api.read_admin_dashboard_api(
        conn,
        session_id=read_session["session_id"],
        session_token=read_session["session_token"],
        deployment_id=prepared["deployment_id"],
    )
    expect(read_view.status == 200 and read_view.payload["deployments"][0]["deployment_id"] == prepared["deployment_id"], str(read_view))
    try:
        api.queue_admin_action_api(
            conn,
            session_id=read_session["session_id"],
            session_token=read_session["session_token"],
            csrf_token=read_session["csrf_token"],
            action_type="restart",
            target_kind="deployment",
            target_id=prepared["deployment_id"],
            reason="restart through api auth test",
            idempotency_key="api-auth-restart-blocked",
        )
    except api.ArcLinkApiAuthError as exc:
        expect("MFA" in str(exc), str(exc))
    else:
        raise AssertionError("expected MFA-bound admin mutation to fail")

    write_session = api.create_arclink_admin_session(
        conn,
        admin_id="admin_api",
        session_id="asess_write",
        mfa_verified=True,
    )
    try:
        api.queue_admin_action_api(
            conn,
            session_id=write_session["session_id"],
            session_token=write_session["session_token"],
            csrf_token="wrong",
            action_type="restart",
            target_kind="deployment",
            target_id=prepared["deployment_id"],
            reason="restart through api auth test",
            idempotency_key="api-auth-restart-csrf",
        )
    except api.ArcLinkApiAuthError as exc:
        expect("CSRF" in str(exc), str(exc))
    else:
        raise AssertionError("expected CSRF failure")
    queued = api.queue_admin_action_api(
        conn,
        session_id=write_session["session_id"],
        session_token=write_session["session_token"],
        csrf_token=write_session["csrf_token"],
        action_type="restart",
        target_kind="deployment",
        target_id=prepared["deployment_id"],
        reason="restart through api auth test",
        idempotency_key="api-auth-restart-1",
    )
    expect(queued.status == 202 and queued.payload["action"]["status"] == "queued", str(queued))
    rendered = json.dumps(verified_admin, sort_keys=True) + json.dumps(queued.payload, sort_keys=True)
    expect("secret://arclink/admin/admin_api/totp" not in rendered, rendered)
    expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_audit_log").fetchone()["n"] == 1, "missing queued action audit")
    print("PASS test_admin_api_requires_csrf_reason_idempotency_and_mfa_ready_schema")


def test_api_transport_helpers_extract_credentials_and_shape_safe_errors() -> None:
    control = load_module("almanac_control.py", "almanac_control_api_auth_transport_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_api_auth_transport_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_transport_test")
    conn = memory_db(control)
    prepared = seed_paid_deployment(control, onboarding, conn)
    session = api.create_arclink_user_session(conn, user_id=prepared["user_id"], session_id="usess_transport")

    header_creds = api.extract_arclink_session_credentials(
        {
            "Authorization": f"Bearer {session['session_token']}",
            "X-ArcLink-Session-Id": session["session_id"],
            "X-ArcLink-CSRF-Token": session["csrf_token"],
        },
        session_kind="user",
    )
    expect(header_creds == {"session_id": session["session_id"], "session_token": session["session_token"]}, str(header_creds))
    expect(
        api.extract_arclink_csrf_token({"X-ArcLink-CSRF-Token": session["csrf_token"]}, session_kind="user")
        == session["csrf_token"],
        "CSRF header extraction failed",
    )

    cookie = (
        f"arclink_user_session_id={session['session_id']}; "
        f"arclink_user_session_token={session['session_token']}; "
        f"arclink_user_csrf={session['csrf_token']}"
    )
    cookie_creds = api.extract_arclink_session_credentials({"Cookie": cookie}, session_kind="user")
    expect(cookie_creds == header_creds, str(cookie_creds))
    expect(api.extract_arclink_csrf_token({"Cookie": cookie}, session_kind="user") == session["csrf_token"], "CSRF cookie extraction failed")

    for bad_kind in ("", "root"):
        try:
            api.extract_arclink_session_credentials({"Authorization": "Bearer example", "X-ArcLink-Session-Id": "sess"}, session_kind=bad_kind)
        except api.ArcLinkApiAuthError as exc:
            expect("session kind" in str(exc), str(exc))
        else:
            raise AssertionError(f"expected unsupported session kind {bad_kind!r} to fail")

    domain_error = api.arclink_api_error_response(api.ArcLinkApiAuthError("ArcLink session token mismatch"), request_id="req_1")
    generic_error = api.arclink_api_error_response(RuntimeError("internal database detail should stay private"), request_id="req_2")
    expect(domain_error.status == 401 and domain_error.payload["error"] == "ArcLink session token mismatch", str(domain_error))
    expect(generic_error.status == 400 and "internal database detail" not in json.dumps(generic_error.payload), str(generic_error))
    expect(generic_error.payload["request_id"] == "req_2", str(generic_error))
    print("PASS test_api_transport_helpers_extract_credentials_and_shape_safe_errors")


def test_revoke_session_rejects_invalid_kind_before_update_or_audit() -> None:
    control = load_module("almanac_control.py", "almanac_control_api_auth_revoke_kind_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_api_auth_revoke_kind_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_revoke_kind_test")
    conn = memory_db(control)
    prepared = seed_paid_deployment(control, onboarding, conn)
    session = api.create_arclink_user_session(conn, user_id=prepared["user_id"], session_id="usess_revoke_guard")

    for bad_kind in ("", "billing", "system"):
        before_audit = conn.execute("SELECT COUNT(*) AS n FROM arclink_audit_log").fetchone()["n"]
        try:
            api.revoke_arclink_session(
                conn,
                session_id=session["session_id"],
                session_kind=bad_kind,
                actor_id="admin_api",
                reason="invalid kind regression",
            )
        except api.ArcLinkApiAuthError as exc:
            expect("session kind" in str(exc), str(exc))
        else:
            raise AssertionError(f"expected invalid session kind {bad_kind!r} to fail")
        row = conn.execute("SELECT status, revoked_at FROM arclink_user_sessions WHERE session_id = ?", (session["session_id"],)).fetchone()
        after_audit = conn.execute("SELECT COUNT(*) AS n FROM arclink_audit_log").fetchone()["n"]
        expect(row["status"] == "active" and row["revoked_at"] == "", str(dict(row)))
        expect(after_audit == before_audit, f"invalid kind wrote audit row: {before_audit} -> {after_audit}")

    revoked = api.revoke_arclink_session(
        conn,
        session_id=session["session_id"],
        session_kind="user",
        actor_id="admin_api",
        reason="valid revoke regression",
    )
    expect(revoked["status"] == "revoked" and revoked["revoked_at"], str(revoked))
    expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_audit_log").fetchone()["n"] == 1, "valid revoke audit missing")
    print("PASS test_revoke_session_rejects_invalid_kind_before_update_or_audit")


def test_revoke_session_rejects_missing_user_and_admin_before_update_or_audit() -> None:
    control = load_module("almanac_control.py", "almanac_control_api_auth_missing_revoke_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_api_auth_missing_revoke_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_missing_revoke_test")
    conn = memory_db(control)
    prepared = seed_paid_deployment(control, onboarding, conn)
    user_session = api.create_arclink_user_session(conn, user_id=prepared["user_id"], session_id="usess_revoke_present")
    api.upsert_arclink_admin(conn, admin_id="admin_revoke_present", email="admin-revoke@example.test", role="ops")
    admin_session = api.create_arclink_admin_session(
        conn,
        admin_id="admin_revoke_present",
        session_id="asess_revoke_present",
    )

    missing_cases = (
        ("user", "usess_missing", "ArcLink user session not found", user_session["session_id"], "arclink_user_sessions"),
        ("admin", "asess_missing", "ArcLink admin session not found", admin_session["session_id"], "arclink_admin_sessions"),
    )
    for session_kind, missing_id, message, present_id, table in missing_cases:
        before_audit = conn.execute("SELECT COUNT(*) AS n FROM arclink_audit_log").fetchone()["n"]
        try:
            api.revoke_arclink_session(
                conn,
                session_id=missing_id,
                session_kind=session_kind,
                actor_id="admin_api",
                reason="missing revoke regression",
            )
        except api.ArcLinkApiAuthError as exc:
            expect(str(exc) == message, str(exc))
        else:
            raise AssertionError(f"expected missing {session_kind} session revoke to fail")
        row = conn.execute(f"SELECT status, revoked_at FROM {table} WHERE session_id = ?", (present_id,)).fetchone()
        after_audit = conn.execute("SELECT COUNT(*) AS n FROM arclink_audit_log").fetchone()["n"]
        expect(row["status"] == "active" and row["revoked_at"] == "", str(dict(row)))
        expect(after_audit == before_audit, f"missing {session_kind} revoke wrote audit row: {before_audit} -> {after_audit}")

    print("PASS test_revoke_session_rejects_missing_user_and_admin_before_update_or_audit")


def main() -> int:
    test_sessions_store_hashes_and_user_api_is_scoped_to_principal()
    test_public_onboarding_api_rate_limits_and_reuses_shared_contract()
    test_public_onboarding_api_rejects_invalid_channel_before_rate_limit()
    test_admin_api_requires_csrf_reason_idempotency_and_mfa_ready_schema()
    test_api_transport_helpers_extract_credentials_and_shape_safe_errors()
    test_revoke_session_rejects_invalid_kind_before_update_or_audit()
    test_revoke_session_rejects_missing_user_and_admin_before_update_or_audit()
    print("PASS all 7 ArcLink API/auth tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
