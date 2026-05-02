#!/usr/bin/env python3
from __future__ import annotations

import json

from arclink_test_helpers import auth_headers, expect, load_module, memory_db


def seed_paid_deployment(control, onboarding, conn):
    session = onboarding.create_or_resume_arclink_onboarding_session(
        conn,
        channel="web",
        channel_identity="hosted-user@example.test",
        session_id="onb_hosted",
        email_hint="hosted-user@example.test",
        display_name_hint="Hosted User",
        selected_plan_id="starter",
        selected_model_id="model-hosted",
    )
    prepared = onboarding.prepare_arclink_onboarding_deployment(
        conn,
        session_id=session["session_id"],
        base_domain="example.test",
        prefix="hosted-vault-1a2b",
    )
    control.set_arclink_user_entitlement(conn, user_id=prepared["user_id"], entitlement_state="paid")
    control.upsert_arclink_service_health(
        conn,
        deployment_id=prepared["deployment_id"],
        service_name="qmd-mcp",
        status="healthy",
    )
    return prepared


def test_public_onboarding_routes_work_without_session_auth() -> None:
    control = load_module("almanac_control.py", "almanac_control_hosted_pub_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_pub_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})

    # Start onboarding - no auth needed
    status, payload, headers = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/onboarding/start",
        headers={},
        body=json.dumps({"channel": "web", "email": "new@example.test", "plan_id": "starter"}),
        config=config,
    )
    expect(status == 201, f"expected 201 got {status}: {payload}")
    expect("session" in payload, str(payload))
    session_id = payload["session"]["session_id"]

    # Answer onboarding question - no auth needed
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/onboarding/answer",
        headers={},
        body=json.dumps({"session_id": session_id, "question_key": "name", "display_name": "Test"}),
        config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")

    print("PASS test_public_onboarding_routes_work_without_session_auth")


def test_user_dashboard_requires_session_auth() -> None:
    control = load_module("almanac_control.py", "almanac_control_hosted_user_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_user_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_user_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_user_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    prepared = seed_paid_deployment(control, onboarding, conn)

    # No auth -> 401
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/user/dashboard",
        headers={},
        config=config,
    )
    expect(status == 401, f"expected 401 got {status}: {payload}")

    # With auth -> 200
    session = api.create_arclink_user_session(conn, user_id=prepared["user_id"], session_id="usess_hosted")
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/user/dashboard",
        headers=auth_headers(session),
        config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect(payload["user"]["user_id"] == prepared["user_id"], str(payload))

    print("PASS test_user_dashboard_requires_session_auth")


def test_admin_dashboard_requires_admin_session() -> None:
    control = load_module("almanac_control.py", "almanac_control_hosted_admin_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_admin_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_admin_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_admin_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    seed_paid_deployment(control, onboarding, conn)
    api.upsert_arclink_admin(conn, admin_id="admin_hosted", email="admin@example.test", role="ops")

    # No auth -> 401
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/admin/dashboard",
        headers={},
        config=config,
    )
    expect(status == 401, f"expected 401 got {status}")

    # With auth -> 200
    session = api.create_arclink_admin_session(conn, admin_id="admin_hosted", session_id="asess_hosted")
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/admin/dashboard",
        headers=auth_headers(session),
        config=config,
    )
    expect(status == 200, f"expected 200 got {status}")
    expect("deployments" in payload, str(payload.keys()))

    print("PASS test_admin_dashboard_requires_admin_session")


def test_admin_action_requires_csrf_and_mutation_role() -> None:
    control = load_module("almanac_control.py", "almanac_control_hosted_action_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_action_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_action_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_action_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    prepared = seed_paid_deployment(control, onboarding, conn)
    api.upsert_arclink_admin(conn, admin_id="admin_action", email="admin-action@example.test", role="ops")
    session = api.create_arclink_admin_session(conn, admin_id="admin_action", session_id="asess_action", mfa_verified=True)

    action_body = json.dumps({
        "action_type": "restart",
        "target_kind": "deployment",
        "target_id": prepared["deployment_id"],
        "reason": "hosted api test",
        "idempotency_key": "hosted-test-1",
    })

    # Missing CSRF -> 401
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/admin/actions",
        headers=auth_headers(session),
        body=action_body,
        config=config,
    )
    expect(status == 401, f"expected 401 got {status}: {payload}")
    expect("CSRF" in str(payload.get("error", "")), str(payload))

    # With CSRF -> 202
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/admin/actions",
        headers=auth_headers(session, csrf=True),
        body=action_body,
        config=config,
    )
    expect(status == 202, f"expected 202 got {status}: {payload}")
    expect(payload["action"]["status"] == "queued", str(payload))

    print("PASS test_admin_action_requires_csrf_and_mutation_role")


def test_safe_error_shapes_never_leak_internal_details() -> None:
    control = load_module("almanac_control.py", "almanac_control_hosted_error_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_error_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})

    # Invalid channel -> safe error, not raw traceback
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/onboarding/start",
        headers={},
        body=json.dumps({"channel": "email", "email": "bad@example.test"}),
        config=config,
    )
    expect(status == 400, f"expected 400 got {status}")
    rendered = json.dumps(payload)
    expect("Traceback" not in rendered, "traceback leaked")
    expect("sqlite3" not in rendered, "internal detail leaked")

    # Unknown route -> 404
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/nonexistent",
        headers={},
        config=config,
    )
    expect(status == 404, f"expected 404 got {status}")

    print("PASS test_safe_error_shapes_never_leak_internal_details")


def test_request_id_propagation_and_cors() -> None:
    control = load_module("almanac_control.py", "almanac_control_hosted_reqid_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_reqid_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "example.test",
        "ARCLINK_CORS_ORIGIN": "https://app.arclink.online",
    })

    # Request ID from client is returned
    status, payload, headers = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/onboarding/start",
        headers={"X-ArcLink-Request-Id": "req_custom_123"},
        body=json.dumps({"channel": "web", "email": "reqid@example.test"}),
        config=config,
    )
    header_dict = {k.lower(): v for k, v in headers}
    expect(header_dict.get("x-arclink-request-id") == "req_custom_123", str(header_dict))

    # CORS headers present when origin is configured
    expect("access-control-allow-origin" in header_dict, str(header_dict))
    expect(header_dict["access-control-allow-origin"] == "https://app.arclink.online", str(header_dict))

    # OPTIONS preflight
    status, _, headers = hosted.route_arclink_hosted_api(
        conn,
        method="OPTIONS",
        path="/api/v1/onboarding/start",
        headers={},
        config=config,
    )
    expect(status == 204, f"expected 204 got {status}")
    cors_dict = {k.lower(): v for k, v in headers}
    expect("access-control-allow-origin" in cors_dict, str(cors_dict))

    print("PASS test_request_id_propagation_and_cors")


def test_admin_login_sets_session_cookies() -> None:
    control = load_module("almanac_control.py", "almanac_control_hosted_login_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_login_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_login_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "example.test",
        "ARCLINK_COOKIE_DOMAIN": ".arclink.online",
    })
    api.upsert_arclink_admin(conn, admin_id="admin_login", email="login@example.test", role="owner")

    status, payload, headers = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/auth/admin/login",
        headers={},
        body=json.dumps({"email": "login@example.test"}),
        config=config,
    )
    expect(status == 201, f"expected 201 got {status}: {payload}")
    cookie_headers = [v for k, v in headers if k == "Set-Cookie"]
    expect(len(cookie_headers) >= 3, f"expected at least 3 Set-Cookie headers, got {len(cookie_headers)}")
    cookie_text = " ".join(cookie_headers)
    expect("arclink_admin_session_id=" in cookie_text, "missing session_id cookie")
    expect("arclink_admin_session_token=" in cookie_text, "missing session_token cookie")
    expect("arclink_admin_csrf=" in cookie_text, "missing csrf cookie")
    expect("HttpOnly" in cookie_text, "missing HttpOnly flag")
    expect(".arclink.online" in cookie_text, "missing cookie domain")

    print("PASS test_admin_login_sets_session_cookies")


def test_session_revoke_requires_admin_auth_and_csrf() -> None:
    control = load_module("almanac_control.py", "almanac_control_hosted_revoke_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_revoke_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_revoke_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_revoke_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    prepared = seed_paid_deployment(control, onboarding, conn)

    user_session = api.create_arclink_user_session(conn, user_id=prepared["user_id"], session_id="usess_revoke_hosted")
    api.upsert_arclink_admin(conn, admin_id="admin_revoke", email="revoke@example.test", role="ops")
    admin_session = api.create_arclink_admin_session(conn, admin_id="admin_revoke", session_id="asess_revoke_hosted")

    # No auth -> 401
    status, _, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/admin/sessions/revoke",
        headers={},
        body=json.dumps({"target_session_id": user_session["session_id"], "session_kind": "user", "reason": "test"}),
        config=config,
    )
    expect(status == 401, f"expected 401 got {status}")

    # With auth + CSRF -> 200
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/admin/sessions/revoke",
        headers=auth_headers(admin_session, csrf=True),
        body=json.dumps({"target_session_id": user_session["session_id"], "session_kind": "user", "reason": "test revoke"}),
        config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect(payload["session"]["status"] == "revoked", str(payload))

    print("PASS test_session_revoke_requires_admin_auth_and_csrf")


def test_stripe_webhook_route_skips_without_secret() -> None:
    control = load_module("almanac_control.py", "almanac_control_hosted_webhook_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_webhook_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/webhooks/stripe",
        headers={},
        body="{}",
        config=config,
    )
    expect(status == 200, f"expected 200 got {status}")
    expect(payload.get("status") == "skipped", str(payload))

    print("PASS test_stripe_webhook_route_skips_without_secret")


def test_user_billing_route_returns_entitlement_and_subscriptions() -> None:
    control = load_module("almanac_control.py", "almanac_control_hosted_billing_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_billing_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_billing_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_billing_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    prepared = seed_paid_deployment(control, onboarding, conn)
    session = api.create_arclink_user_session(conn, user_id=prepared["user_id"], session_id="usess_billing")

    # No auth -> 401
    status, _, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/user/billing", headers={}, config=config,
    )
    expect(status == 401, f"expected 401 got {status}")

    # With auth -> 200 with entitlement
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/user/billing",
        headers=auth_headers(session),
        config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect(payload["entitlement"]["state"] == "paid", str(payload))
    expect("subscriptions" in payload, str(payload))

    print("PASS test_user_billing_route_returns_entitlement_and_subscriptions")


def test_user_provisioning_status_route() -> None:
    control = load_module("almanac_control.py", "almanac_control_hosted_prov_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_prov_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_prov_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_prov_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    prepared = seed_paid_deployment(control, onboarding, conn)
    session = api.create_arclink_user_session(conn, user_id=prepared["user_id"], session_id="usess_prov")

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/user/provisioning",
        headers=auth_headers(session),
        config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect(len(payload["deployments"]) >= 1, str(payload))
    dep = payload["deployments"][0]
    expect(dep["deployment_id"] == prepared["deployment_id"], str(dep))
    expect("service_health" in dep, str(dep))

    print("PASS test_user_provisioning_status_route")


def test_admin_service_health_route() -> None:
    control = load_module("almanac_control.py", "almanac_control_hosted_health_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_health_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_health_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_health_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    seed_paid_deployment(control, onboarding, conn)
    api.upsert_arclink_admin(conn, admin_id="admin_health", email="health@example.test", role="ops")
    session = api.create_arclink_admin_session(conn, admin_id="admin_health", session_id="asess_health")

    # No auth -> 401
    status, _, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/admin/service-health", headers={}, config=config,
    )
    expect(status == 401, f"expected 401 got {status}")

    # With auth -> 200
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/admin/service-health",
        headers=auth_headers(session),
        config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect("service_health" in payload, str(payload))
    expect("recent_failures" in payload, str(payload))

    print("PASS test_admin_service_health_route")


def test_admin_provisioning_jobs_route() -> None:
    control = load_module("almanac_control.py", "almanac_control_hosted_jobs_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_jobs_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_jobs_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    api.upsert_arclink_admin(conn, admin_id="admin_jobs", email="jobs@example.test", role="ops")
    session = api.create_arclink_admin_session(conn, admin_id="admin_jobs", session_id="asess_jobs")

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/admin/provisioning-jobs",
        headers=auth_headers(session),
        config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect("provisioning_jobs" in payload, str(payload))

    print("PASS test_admin_provisioning_jobs_route")


def test_admin_audit_route() -> None:
    control = load_module("almanac_control.py", "almanac_control_hosted_audit_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_audit_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_audit_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_audit_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    seed_paid_deployment(control, onboarding, conn)
    api.upsert_arclink_admin(conn, admin_id="admin_audit", email="audit@example.test", role="ops")
    session = api.create_arclink_admin_session(conn, admin_id="admin_audit", session_id="asess_audit")

    # No auth -> 401
    status, _, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/admin/audit", headers={}, config=config,
    )
    expect(status == 401, f"expected 401 got {status}")

    # With auth -> 200
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/admin/audit",
        headers=auth_headers(session),
        config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect("audit" in payload, str(payload))

    print("PASS test_admin_audit_route")


def test_admin_events_route() -> None:
    control = load_module("almanac_control.py", "almanac_control_hosted_events_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_events_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_events_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    api.upsert_arclink_admin(conn, admin_id="admin_events", email="events@example.test", role="ops")
    session = api.create_arclink_admin_session(conn, admin_id="admin_events", session_id="asess_events")

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/admin/events",
        headers=auth_headers(session),
        config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect("events" in payload, str(payload))

    print("PASS test_admin_events_route")


def test_admin_queued_actions_list_route() -> None:
    control = load_module("almanac_control.py", "almanac_control_hosted_qalist_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_qalist_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_qalist_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_qalist_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    prepared = seed_paid_deployment(control, onboarding, conn)
    api.upsert_arclink_admin(conn, admin_id="admin_qalist", email="qalist@example.test", role="ops")
    session = api.create_arclink_admin_session(conn, admin_id="admin_qalist", session_id="asess_qalist", mfa_verified=True)

    # Queue an action first
    hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/admin/actions",
        headers=auth_headers(session, csrf=True),
        body=json.dumps({
            "action_type": "restart", "target_kind": "deployment",
            "target_id": prepared["deployment_id"], "reason": "list test",
            "idempotency_key": "qalist-test-1",
        }),
        config=config,
    )

    # GET list -> 200 with actions
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/admin/actions",
        headers=auth_headers(session),
        config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect("actions" in payload, str(payload))
    expect(len(payload["actions"]) >= 1, f"expected at least 1 action, got {len(payload['actions'])}")

    print("PASS test_admin_queued_actions_list_route")


def test_user_portal_link_route() -> None:
    control = load_module("almanac_control.py", "almanac_control_hosted_portal_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_portal_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_portal_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_portal_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    prepared = seed_paid_deployment(control, onboarding, conn)
    # Set stripe_customer_id on user
    conn.execute("UPDATE arclink_users SET stripe_customer_id = 'cus_portal_test' WHERE user_id = ?", (prepared["user_id"],))
    conn.commit()
    session = api.create_arclink_user_session(conn, user_id=prepared["user_id"], session_id="usess_portal")

    # No auth -> 401
    status, _, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/user/portal", headers={},
        body=json.dumps({"return_url": "https://app.arclink.online/dashboard"}),
        config=config,
    )
    expect(status == 401, f"expected 401 got {status}")

    # With auth -> 200 with portal_url
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/user/portal",
        headers=auth_headers(session),
        body=json.dumps({"return_url": "https://app.arclink.online/dashboard"}),
        config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect("portal_url" in payload, str(payload))
    expect("stripe.test/portal" in payload["portal_url"], str(payload))

    print("PASS test_user_portal_link_route")


def test_user_login_sets_session_cookies_and_logout_clears_them() -> None:
    control = load_module("almanac_control.py", "almanac_control_hosted_userlogin_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_userlogin_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_userlogin_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "example.test",
        "ARCLINK_COOKIE_DOMAIN": ".arclink.online",
    })
    prepared = seed_paid_deployment(control, onboarding, conn)

    # Login
    status, payload, headers = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/auth/user/login",
        headers={},
        body=json.dumps({"email": "hosted-user@example.test"}),
        config=config,
    )
    expect(status == 201, f"expected 201 got {status}: {payload}")
    cookie_headers = [v for k, v in headers if k == "Set-Cookie"]
    expect(len(cookie_headers) >= 3, f"expected at least 3 Set-Cookie headers, got {len(cookie_headers)}")
    cookie_text = " ".join(cookie_headers)
    expect("arclink_user_session_id=" in cookie_text, "missing session_id cookie")
    expect("arclink_user_session_token=" in cookie_text, "missing session_token cookie")
    expect("arclink_user_csrf=" in cookie_text, "missing csrf cookie")
    expect("HttpOnly" in cookie_text, "missing HttpOnly flag")
    expect(".arclink.online" in cookie_text, "missing cookie domain")

    session = payload["session"]

    # Use session to access dashboard
    status, _, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/user/dashboard",
        headers=auth_headers(session),
        config=config,
    )
    expect(status == 200, f"expected 200 got {status}")

    # Logout
    status, payload, headers = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/auth/user/logout",
        headers=auth_headers(session),
        config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect(payload["session"]["status"] == "revoked", str(payload))
    clear_cookies = [v for k, v in headers if k == "Set-Cookie"]
    expect(any("Max-Age=0" in c for c in clear_cookies), "expected clearing cookies")

    # Session should no longer work
    status, _, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/user/dashboard",
        headers=auth_headers(session),
        config=config,
    )
    expect(status == 401, f"expected 401 after logout got {status}")

    print("PASS test_user_login_sets_session_cookies_and_logout_clears_them")


def test_public_onboarding_checkout_route() -> None:
    control = load_module("almanac_control.py", "almanac_control_hosted_checkout_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_checkout_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_checkout_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})

    # Start onboarding first
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/onboarding/start",
        headers={},
        body=json.dumps({"channel": "web", "email": "checkout@example.test", "plan_id": "starter"}),
        config=config,
    )
    expect(status == 201, f"expected 201 got {status}")
    session_id = payload["session"]["session_id"]

    # Open checkout
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/onboarding/checkout",
        headers={},
        body=json.dumps({
            "session_id": session_id,
            "success_url": "https://app.arclink.online/success",
            "cancel_url": "https://app.arclink.online/cancel",
        }),
        config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect("session" in payload, str(payload))
    expect("checkout_url" in payload["session"], str(payload))
    expect(payload["session"]["checkout_url"].startswith("https://"), str(payload))

    print("PASS test_public_onboarding_checkout_route")


def test_web_telegram_discord_onboarding_parity() -> None:
    control = load_module("almanac_control.py", "almanac_control_hosted_parity_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_parity_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})

    sessions = {}
    for channel, identity in [
        ("web", "web@example.test"),
        ("telegram", "tg_user_123"),
        ("discord", "dc_user_456"),
    ]:
        status, payload, _ = hosted.route_arclink_hosted_api(
            conn,
            method="POST",
            path="/api/v1/onboarding/start",
            headers={},
            body=json.dumps({"channel": channel, "channel_identity": identity, "email": f"{channel}@example.test"}),
            config=config,
        )
        expect(status == 201, f"expected 201 for {channel} got {status}: {payload}")
        sessions[channel] = payload["session"]

    # All sessions must have the same shape (same keys)
    web_keys = set(sessions["web"].keys())
    for channel in ("telegram", "discord"):
        ch_keys = set(sessions[channel].keys())
        expect(web_keys == ch_keys, f"parity mismatch: web={web_keys} vs {channel}={ch_keys}")

    # All sessions should have distinct session_ids and user_ids
    session_ids = {s["session_id"] for s in sessions.values()}
    expect(len(session_ids) == 3, f"expected 3 distinct session_ids, got {session_ids}")

    # All answer the same question
    for channel, session in sessions.items():
        status, payload, _ = hosted.route_arclink_hosted_api(
            conn,
            method="POST",
            path="/api/v1/onboarding/answer",
            headers={},
            body=json.dumps({
                "session_id": session["session_id"],
                "question_key": "name",
                "display_name": f"User from {channel}",
            }),
            config=config,
        )
        expect(status == 200, f"expected 200 for {channel} answer got {status}: {payload}")

    print("PASS test_web_telegram_discord_onboarding_parity")


def test_admin_dns_drift_route() -> None:
    control = load_module("almanac_control.py", "almanac_control_hosted_dns_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_dns_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_dns_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    api.upsert_arclink_admin(conn, admin_id="admin_dns", email="dns@example.test", role="ops")
    session = api.create_arclink_admin_session(conn, admin_id="admin_dns", session_id="asess_dns")

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/admin/dns-drift",
        headers=auth_headers(session),
        config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect("dns_drift" in payload, str(payload))

    print("PASS test_admin_dns_drift_route")


def test_admin_logout_clears_cookies_and_revokes_session() -> None:
    control = load_module("almanac_control.py", "almanac_control_hosted_adminlogout_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_adminlogout_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_adminlogout_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "example.test",
        "ARCLINK_COOKIE_DOMAIN": ".arclink.online",
    })
    api.upsert_arclink_admin(conn, admin_id="admin_logout", email="logout@example.test", role="owner")

    # Login
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/auth/admin/login",
        headers={}, body=json.dumps({"email": "logout@example.test"}), config=config,
    )
    expect(status == 201, f"login expected 201 got {status}")
    session = payload["session"]

    # Verify session works
    status, _, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/admin/dashboard",
        headers=auth_headers(session),
        config=config,
    )
    expect(status == 200, f"expected 200 got {status}")

    # Logout
    status, payload, headers = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/auth/admin/logout",
        headers=auth_headers(session),
        config=config,
    )
    expect(status == 200, f"logout expected 200 got {status}")
    expect(payload["session"]["status"] == "revoked", str(payload))
    clear_cookies = [v for k, v in headers if k == "Set-Cookie"]
    expect(any("Max-Age=0" in c for c in clear_cookies), "expected clearing cookies")

    # Session should no longer work
    status, _, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/admin/dashboard",
        headers=auth_headers(session),
        config=config,
    )
    expect(status == 401, f"expected 401 after logout got {status}")

    print("PASS test_admin_logout_clears_cookies_and_revokes_session")


def test_stripe_webhook_processes_entitlement_transition() -> None:
    import time as _time
    control = load_module("almanac_control.py", "almanac_control_hosted_whprocess_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_whprocess_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_hosted_whprocess_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_whprocess_test")
    conn = memory_db(control)
    secret = "whsec_test_process"
    config = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "example.test",
        "STRIPE_WEBHOOK_SECRET": secret,
    })
    prepared = seed_paid_deployment(control, onboarding, conn)

    # Build a checkout.session.completed event payload
    event_payload = json.dumps({
        "id": "evt_checkout_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_1",
                "customer": "cus_test_1",
                "subscription": "sub_test_1",
                "client_reference_id": prepared["user_id"],
                "metadata": {"arclink_onboarding_session_id": "onb_hosted"},
            }
        },
    })
    signature = adapters.sign_stripe_webhook(event_payload, secret, timestamp=int(_time.time()))

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/webhooks/stripe",
        headers={"Stripe-Signature": signature},
        body=event_payload, config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect(payload["status"] == "processed", str(payload))
    expect(payload["event_id"] == "evt_checkout_1", str(payload))
    expect(payload["event_type"] == "checkout.session.completed", str(payload))
    expect(payload["replayed"] is False, str(payload))

    # Replay same event -> idempotent
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/webhooks/stripe",
        headers={"Stripe-Signature": signature},
        body=event_payload, config=config,
    )
    expect(status == 200, f"replay expected 200 got {status}")
    expect(payload["replayed"] is True, f"expected replayed=True: {payload}")

    print("PASS test_stripe_webhook_processes_entitlement_transition")


def test_wsgi_adapter_smoke() -> None:
    from io import BytesIO
    control = load_module("almanac_control.py", "almanac_control_hosted_wsgi_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_wsgi_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    app = hosted.make_arclink_hosted_api_wsgi(conn, config=config)

    captured: list[tuple[str, list]] = []

    def start_response(status: str, headers: list) -> None:
        captured.append((status, headers))

    body = json.dumps({"channel": "web", "email": "wsgi@example.test"}).encode()
    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/api/v1/onboarding/start",
        "QUERY_STRING": "",
        "CONTENT_LENGTH": str(len(body)),
        "CONTENT_TYPE": "application/json",
        "wsgi.input": BytesIO(body),
    }
    result = app(environ, start_response)
    expect(len(captured) == 1, f"expected 1 start_response call, got {len(captured)}")
    expect(captured[0][0].startswith("201"), f"expected 201 got {captured[0][0]}")
    response = json.loads(result[0])
    expect("session" in response, str(response))

    print("PASS test_wsgi_adapter_smoke")


def main() -> int:
    test_public_onboarding_routes_work_without_session_auth()
    test_user_dashboard_requires_session_auth()
    test_admin_dashboard_requires_admin_session()
    test_admin_action_requires_csrf_and_mutation_role()
    test_safe_error_shapes_never_leak_internal_details()
    test_request_id_propagation_and_cors()
    test_admin_login_sets_session_cookies()
    test_session_revoke_requires_admin_auth_and_csrf()
    test_stripe_webhook_route_skips_without_secret()
    test_user_billing_route_returns_entitlement_and_subscriptions()
    test_user_provisioning_status_route()
    test_admin_service_health_route()
    test_admin_provisioning_jobs_route()
    test_admin_audit_route()
    test_admin_events_route()
    test_admin_queued_actions_list_route()
    test_user_portal_link_route()
    test_user_login_sets_session_cookies_and_logout_clears_them()
    test_public_onboarding_checkout_route()
    test_web_telegram_discord_onboarding_parity()
    test_admin_dns_drift_route()
    test_admin_logout_clears_cookies_and_revokes_session()
    test_stripe_webhook_processes_entitlement_transition()
    test_wsgi_adapter_smoke()
    print("PASS all 24 ArcLink hosted API tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
