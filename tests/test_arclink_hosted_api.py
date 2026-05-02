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
    control = load_module("arclink_control.py", "arclink_control_hosted_pub_test")
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
    control = load_module("arclink_control.py", "arclink_control_hosted_user_test")
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
    control = load_module("arclink_control.py", "arclink_control_hosted_admin_test")
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
    control = load_module("arclink_control.py", "arclink_control_hosted_action_test")
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
    control = load_module("arclink_control.py", "arclink_control_hosted_error_test")
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
    control = load_module("arclink_control.py", "arclink_control_hosted_reqid_test")
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
    control = load_module("arclink_control.py", "arclink_control_hosted_login_test")
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
    control = load_module("arclink_control.py", "arclink_control_hosted_revoke_test")
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
    control = load_module("arclink_control.py", "arclink_control_hosted_webhook_test")
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
    control = load_module("arclink_control.py", "arclink_control_hosted_billing_test")
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
    control = load_module("arclink_control.py", "arclink_control_hosted_prov_test")
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
    control = load_module("arclink_control.py", "arclink_control_hosted_health_test")
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
    control = load_module("arclink_control.py", "arclink_control_hosted_jobs_test")
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
    control = load_module("arclink_control.py", "arclink_control_hosted_audit_test")
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
    control = load_module("arclink_control.py", "arclink_control_hosted_events_test")
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
    control = load_module("arclink_control.py", "arclink_control_hosted_qalist_test")
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
    control = load_module("arclink_control.py", "arclink_control_hosted_portal_test")
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

    # With auth but no CSRF -> 401
    status, _, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/user/portal",
        headers=auth_headers(session),
        body=json.dumps({"return_url": "https://app.arclink.online/dashboard"}),
        config=config,
    )
    expect(status == 401, f"expected 401 without CSRF got {status}")

    # With auth + CSRF -> 200 with portal_url
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/user/portal",
        headers=auth_headers(session, csrf=True),
        body=json.dumps({"return_url": "https://app.arclink.online/dashboard"}),
        config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect("portal_url" in payload, str(payload))
    expect("stripe.test/portal" in payload["portal_url"], str(payload))

    print("PASS test_user_portal_link_route")


def test_user_login_sets_session_cookies_and_logout_clears_them() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_userlogin_test")
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

    # Logout without CSRF should fail
    status, _, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/auth/user/logout",
        headers=auth_headers(session),
        config=config,
    )
    expect(status == 401, f"expected 401 without CSRF got {status}")

    # Logout with CSRF
    status, payload, headers = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/auth/user/logout",
        headers=auth_headers(session, csrf=True),
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
    control = load_module("arclink_control.py", "arclink_control_hosted_checkout_test")
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


def test_public_onboarding_checkout_resolves_live_stripe_from_config() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_checkout_live_resolve_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_checkout_live_resolve_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "example.test",
        "STRIPE_SECRET_KEY": "sk_test_configured_secret",
        "ARCLINK_DEFAULT_PRICE_ID": "price_live_resolve",
    })
    calls: list[dict] = []

    class RecordingStripe:
        def create_checkout_session(self, **kwargs):
            calls.append(kwargs)
            return {"id": "cs_live_resolved", "url": "https://checkout.stripe.com/c/cs_live_resolved"}

    def fake_resolve(env):
        expect(env["STRIPE_SECRET_KEY"] == "sk_test_configured_secret", str(env))
        return RecordingStripe()

    hosted.resolve_stripe_client = fake_resolve
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/onboarding/start",
        headers={},
        body=json.dumps({"channel": "web", "email": "live-resolve@example.test", "plan_id": "starter"}),
        config=config,
    )
    expect(status == 201, f"expected 201 got {status}: {payload}")
    session_id = payload["session"]["session_id"]

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
    expect(payload["session"]["checkout_url"].startswith("https://checkout.stripe.com/"), str(payload))
    expect(calls and calls[0]["price_id"] == "price_live_resolve", str(calls))
    print("PASS test_public_onboarding_checkout_resolves_live_stripe_from_config")


def test_web_telegram_discord_onboarding_parity() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_parity_test")
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
    control = load_module("arclink_control.py", "arclink_control_hosted_dns_test")
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
    control = load_module("arclink_control.py", "arclink_control_hosted_adminlogout_test")
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

    # Logout without CSRF should fail
    status, _, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/auth/admin/logout",
        headers=auth_headers(session),
        config=config,
    )
    expect(status == 401, f"expected 401 without CSRF got {status}")

    # Logout with CSRF
    status, payload, headers = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/auth/admin/logout",
        headers=auth_headers(session, csrf=True),
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
    control = load_module("arclink_control.py", "arclink_control_hosted_whprocess_test")
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

    invoice_payload = json.dumps({
        "id": "evt_invoice_1",
        "type": "invoice.payment_succeeded",
        "data": {
            "object": {
                "id": "in_test_1",
                "customer": "cus_test_1",
                "subscription": "sub_test_1",
                "status": "paid",
                "metadata": {},
            }
        },
    })
    invoice_signature = adapters.sign_stripe_webhook(invoice_payload, secret, timestamp=int(_time.time()))
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/webhooks/stripe",
        headers={"Stripe-Signature": invoice_signature},
        body=invoice_payload, config=config,
    )
    expect(status == 200, f"invoice expected 200 got {status}: {payload}")
    expect(payload["event_type"] == "invoice.payment_succeeded", str(payload))
    subscription = conn.execute(
        "SELECT user_id, status FROM arclink_subscriptions WHERE stripe_subscription_id = 'sub_test_1'"
    ).fetchone()
    expect(subscription is not None, "expected Stripe subscription mirror")
    expect(subscription["user_id"] == prepared["user_id"], str(dict(subscription)))
    expect(subscription["status"] == "paid", str(dict(subscription)))

    print("PASS test_stripe_webhook_processes_entitlement_transition")


def test_telegram_webhook_route() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_tg_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_tg_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})

    # Valid update
    update = json.dumps({
        "update_id": 1,
        "message": {
            "message_id": 1,
            "chat": {"id": 12345},
            "from": {"id": 67890},
            "text": "/start",
        },
    })
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/webhooks/telegram",
        headers={}, body=update, config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect(payload.get("ok") is True, str(payload))
    expect(payload.get("action") != "ignored", f"expected handled action: {payload}")
    expect(payload.get("sent") is False, f"no live Telegram transport should be used in this test: {payload}")

    # Non-text update (no message) should be ignored
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/webhooks/telegram",
        headers={}, body=json.dumps({"update_id": 2}), config=config,
    )
    expect(status == 200, f"expected 200 got {status}")
    expect(payload.get("action") == "ignored", str(payload))

    print("PASS test_telegram_webhook_route")


def test_telegram_webhook_sends_reply_when_transport_is_available() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_tg_send_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_tg_send_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_hosted_tg_send_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})

    class CaptureTransport:
        def __init__(self) -> None:
            self.sent_messages = []

        def send_message(self, chat_id: str, text: str):
            self.sent_messages.append({"chat_id": chat_id, "text": text})
            return {"message_id": len(self.sent_messages)}

    transport = CaptureTransport()
    update = {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "chat": {"id": 12345},
            "from": {"id": 67890},
            "text": "/help",
        },
    }
    status, payload, _ = hosted._handle_telegram_webhook(
        conn,
        update,
        "req_tg_send",
        config,
        adapters.FakeStripeClient(),
        telegram_transport=transport,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect(payload.get("sent") is True, str(payload))
    expect(len(transport.sent_messages) == 1, str(transport.sent_messages))
    expect(transport.sent_messages[0]["chat_id"] == "12345", str(transport.sent_messages))
    expect("/connect-notion" in transport.sent_messages[0]["text"], transport.sent_messages[0]["text"])

    class FailingTransport:
        def send_message(self, chat_id: str, text: str):
            raise RuntimeError("telegram api unavailable")

    status, payload, _ = hosted._handle_telegram_webhook(
        conn,
        update,
        "req_tg_send_failure",
        config,
        adapters.FakeStripeClient(),
        telegram_transport=FailingTransport(),
    )
    expect(status == 200, f"reply send failure should still ack webhook: {status} {payload}")
    expect(payload.get("sent") is False, str(payload))
    print("PASS test_telegram_webhook_sends_reply_when_transport_is_available")


def test_discord_webhook_route() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_dc_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_dc_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})

    # Ping interaction (with test_public_key sentinel)
    import os
    os.environ["DISCORD_PUBLIC_KEY"] = "test_public_key"
    os.environ["DISCORD_BOT_TOKEN"] = "fake"
    os.environ["DISCORD_APP_ID"] = "app123"
    try:
        ping_body = json.dumps({"type": 1})
        status, payload, _ = hosted.route_arclink_hosted_api(
            conn, method="POST", path="/api/v1/webhooks/discord",
            headers={"x-signature-ed25519": "abc", "x-signature-timestamp": "123"},
            body=ping_body, config=config,
        )
        expect(status == 200, f"expected 200 got {status}: {payload}")
        expect(payload.get("type") == 1, f"expected PONG: {payload}")

        # Slash command
        interaction = json.dumps({
            "type": 2,
            "channel_id": "chan1",
            "member": {"user": {"id": "user1"}},
            "data": {"name": "arclink", "options": [{"name": "message", "value": "hello"}]},
        })
        status, payload, _ = hosted.route_arclink_hosted_api(
            conn, method="POST", path="/api/v1/webhooks/discord",
            headers={"x-signature-ed25519": "abc", "x-signature-timestamp": "123"},
            body=interaction, config=config,
        )
        expect(status == 200, f"expected 200 got {status}: {payload}")
        expect(payload.get("type") == 4, f"expected CHANNEL_MESSAGE: {payload}")
        expect("content" in payload.get("data", {}), str(payload))
    finally:
        os.environ.pop("DISCORD_PUBLIC_KEY", None)
        os.environ.pop("DISCORD_BOT_TOKEN", None)
        os.environ.pop("DISCORD_APP_ID", None)

    # No public key configured → 500
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/webhooks/discord",
        headers={}, body=json.dumps({"type": 1}), config=config,
    )
    expect(status == 500, f"expected 500 without config got {status}")
    expect(payload.get("error") == "discord_not_configured", str(payload))

    print("PASS test_discord_webhook_route")


def test_health_endpoint_requires_no_auth() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_healthep_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_healthep_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/health", headers={}, config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect(payload["status"] == "ok", str(payload))
    expect(payload["db"] is True, str(payload))

    print("PASS test_health_endpoint_requires_no_auth")


def test_user_provider_state_route() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_uprov_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_uprov_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_uprov_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_uprov_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    prepared = seed_paid_deployment(control, onboarding, conn)
    session = api.create_arclink_user_session(conn, user_id=prepared["user_id"], session_id="usess_uprov")

    # No auth -> 401
    status, _, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/user/provider-state", headers={}, config=config,
    )
    expect(status == 401, f"expected 401 got {status}")

    # With auth -> 200
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/user/provider-state",
        headers=auth_headers(session), config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect("provider" in payload, str(payload))
    expect("default_model" in payload, str(payload))
    expect("deployment_models" in payload, str(payload))

    print("PASS test_user_provider_state_route")


def test_admin_provider_state_route() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_aprov_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_aprov_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_aprov_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    api.upsert_arclink_admin(conn, admin_id="admin_aprov", email="aprov@example.test", role="ops")
    session = api.create_arclink_admin_session(conn, admin_id="admin_aprov", session_id="asess_aprov")

    # No auth -> 401
    status, _, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/admin/provider-state", headers={}, config=config,
    )
    expect(status == 401, f"expected 401 got {status}")

    # With auth -> 200
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/admin/provider-state",
        headers=auth_headers(session), config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect(payload["provider"] == "chutes", str(payload))
    expect("default_model" in payload, str(payload))

    print("PASS test_admin_provider_state_route")


def test_admin_reconciliation_route() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_recon_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_recon_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_recon_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_recon_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    seed_paid_deployment(control, onboarding, conn)
    api.upsert_arclink_admin(conn, admin_id="admin_recon", email="recon@example.test", role="ops")
    session = api.create_arclink_admin_session(conn, admin_id="admin_recon", session_id="asess_recon")

    # No auth -> 401
    status, _, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/admin/reconciliation", headers={}, config=config,
    )
    expect(status == 401, f"expected 401 got {status}")

    # With auth -> 200
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/admin/reconciliation",
        headers=auth_headers(session), config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect("reconciliation" in payload, str(payload))
    expect("drift_count" in payload, str(payload))
    expect(isinstance(payload["reconciliation"], list), str(payload))

    print("PASS test_admin_reconciliation_route")


def test_stripe_webhook_rejects_bad_signature() -> None:
    import time as _time
    control = load_module("arclink_control.py", "arclink_control_hosted_badsig_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_badsig_test")
    conn = memory_db(control)
    secret = "whsec_test_badsig"
    config = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "example.test",
        "STRIPE_WEBHOOK_SECRET": secret,
    })
    event_payload = json.dumps({"id": "evt_bad", "type": "checkout.session.completed", "data": {"object": {}}})

    # Bad signature -> 400
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/webhooks/stripe",
        headers={"Stripe-Signature": "t=9999,v1=badsig"},
        body=event_payload, config=config,
    )
    expect(status == 400, f"expected 400 got {status}: {payload}")

    print("PASS test_stripe_webhook_rejects_bad_signature")


def test_unauthenticated_logout_and_portal_rejected() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_noauth_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_noauth_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})

    # User logout without any session -> 401
    status, _, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/auth/user/logout",
        headers={}, config=config,
    )
    expect(status == 401, f"user logout expected 401 got {status}")

    # Admin logout without any session -> 401
    status, _, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/auth/admin/logout",
        headers={}, config=config,
    )
    expect(status == 401, f"admin logout expected 401 got {status}")

    # User portal without any session -> 401
    status, _, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/user/portal",
        headers={}, body=json.dumps({"return_url": "https://example.test"}),
        config=config,
    )
    expect(status == 401, f"user portal expected 401 got {status}")

    print("PASS test_unauthenticated_logout_and_portal_rejected")


def test_wsgi_adapter_smoke() -> None:
    from io import BytesIO
    control = load_module("arclink_control.py", "arclink_control_hosted_wsgi_test")
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


def test_read_only_admin_blocked_from_mutations() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_ro_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_ro_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_ro_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_ro_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    prepared = seed_paid_deployment(control, onboarding, conn)
    api.upsert_arclink_admin(conn, admin_id="admin_ro", email="ro@example.test", role="read_only")
    session = api.create_arclink_admin_session(conn, admin_id="admin_ro", session_id="asess_ro")

    # read_only admin can read dashboard
    status, _, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/admin/dashboard",
        headers=auth_headers(session), config=config,
    )
    expect(status == 200, f"read expected 200 got {status}")

    # read_only admin cannot queue actions even with CSRF
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/admin/actions",
        headers=auth_headers(session, csrf=True),
        body=json.dumps({
            "action_type": "restart", "target_kind": "deployment",
            "target_id": prepared["deployment_id"], "reason": "ro test",
            "idempotency_key": "ro-test-1",
        }),
        config=config,
    )
    expect(status == 401, f"read_only mutation expected 401 got {status}: {payload}")
    expect("role" in str(payload.get("error", "")).lower(), f"expected role error: {payload}")

    print("PASS test_read_only_admin_blocked_from_mutations")


def test_login_rejects_unknown_email() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_badlogin_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_badlogin_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})

    # Admin login with unknown email -> 401
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/auth/admin/login",
        headers={}, body=json.dumps({"email": "nonexistent@example.test"}),
        config=config,
    )
    expect(status == 401, f"admin login expected 401 got {status}: {payload}")

    # User login with unknown email -> 401
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/auth/user/login",
        headers={}, body=json.dumps({"email": "nonexistent@example.test"}),
        config=config,
    )
    expect(status == 401, f"user login expected 401 got {status}: {payload}")

    # Admin login with blank email -> 401
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/auth/admin/login",
        headers={}, body=json.dumps({"email": ""}),
        config=config,
    )
    expect(status == 401, f"blank admin login expected 401 got {status}")

    print("PASS test_login_rejects_unknown_email")


def test_openapi_spec_route_serves_valid_contract() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_openapi_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_openapi_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/openapi.json", headers={}, config=config,
    )
    expect(status == 200, f"expected 200 got {status}")
    expect(payload.get("openapi") == "3.1.0", f"missing openapi version: {payload.get('openapi')}")
    expect("paths" in payload, "missing paths")
    expect("/api/v1/health" in payload["paths"], f"missing /api/v1/health in paths: {list(payload['paths'].keys())}")
    expect("/api/v1/openapi.json" in payload["paths"], "missing /api/v1/openapi.json in paths")

    # Every _ROUTES entry must be represented
    for (method, path_suffix), route_key in hosted._ROUTES.items():
        full_path = f"/api/v1{path_suffix}"
        expect(full_path in payload["paths"], f"route {full_path} missing from OpenAPI spec")
        expect(method.lower() in payload["paths"][full_path], f"{method} {full_path} missing from spec")

    print("PASS test_openapi_spec_route_serves_valid_contract")


def test_openapi_spec_matches_static_copy() -> None:
    import os
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_openapi_static_test")
    spec = hosted.build_arclink_openapi_spec()

    static_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "openapi", "arclink-v1.openapi.json")
    with open(static_path) as f:
        static_spec = json.load(f)

    spec_json = json.dumps(spec, sort_keys=True)
    static_json = json.dumps(static_spec, sort_keys=True)
    expect(spec_json == static_json, "served OpenAPI spec does not match checked-in static copy")

    print("PASS test_openapi_spec_matches_static_copy")


def test_rate_limit_returns_429_with_headers() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_ratelimit_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_ratelimit_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})

    # Exhaust the admin login rate limit (5 per 15 min, same subject)
    for i in range(5):
        status, _, _ = hosted.route_arclink_hosted_api(
            conn, method="POST", path="/api/v1/auth/admin/login",
            headers={}, body=json.dumps({"email": "ratelimit@example.test"}),
            config=config,
        )
        # These will return 401 (unknown email), but rate limit counter increments

    # 6th attempt with same subject should be rate limited -> 429
    status, payload, headers = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/auth/admin/login",
        headers={}, body=json.dumps({"email": "ratelimit@example.test"}),
        config=config,
    )
    expect(status == 429, f"expected 429 got {status}: {payload}")
    header_dict = {k.lower(): v for k, v in headers}
    expect("retry-after" in header_dict, f"missing Retry-After: {header_dict}")
    expect("x-ratelimit-limit" in header_dict, f"missing X-RateLimit-Limit: {header_dict}")
    expect("x-ratelimit-remaining" in header_dict, f"missing X-RateLimit-Remaining: {header_dict}")
    expect("x-ratelimit-reset" in header_dict, f"missing X-RateLimit-Reset: {header_dict}")
    expect(header_dict["x-ratelimit-remaining"] == "0", f"expected remaining=0: {header_dict}")
    expect(int(header_dict["retry-after"]) > 0, f"Retry-After must be positive: {header_dict}")
    # Should not leak subject/email
    rendered = json.dumps(payload)
    expect("ratelimit@example.test" not in rendered, "subject leaked in rate limit response")

    print("PASS test_rate_limit_returns_429_with_headers")


def test_rate_limit_onboarding_returns_429() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_rl_onb_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_rl_onb_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})

    # Exhaust onboarding rate limit (5 per 15 min for same identity)
    for i in range(5):
        hosted.route_arclink_hosted_api(
            conn, method="POST", path="/api/v1/onboarding/start",
            headers={}, body=json.dumps({"channel": "web", "email": "rl-same@example.test"}),
            config=config,
        )

    # 6th should be rate limited
    status, payload, headers = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/onboarding/start",
        headers={}, body=json.dumps({"channel": "web", "email": "rl-same@example.test"}),
        config=config,
    )
    expect(status == 429, f"expected 429 got {status}: {payload}")
    header_dict = {k.lower(): v for k, v in headers}
    expect("retry-after" in header_dict, f"missing Retry-After: {header_dict}")
    expect("x-ratelimit-limit" in header_dict, f"missing X-RateLimit-Limit: {header_dict}")

    print("PASS test_rate_limit_onboarding_returns_429")


def test_wsgi_503_status_text_for_degraded_health() -> None:
    from io import BytesIO
    control = load_module("arclink_control.py", "arclink_control_hosted_503_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_503_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    app = hosted.make_arclink_hosted_api_wsgi(conn, config=config)

    # Close the connection to simulate DB failure
    conn.close()

    captured: list[tuple[str, list]] = []

    def start_response(status: str, headers: list) -> None:
        captured.append((status, headers))

    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": "/api/v1/health",
        "QUERY_STRING": "",
        "CONTENT_LENGTH": "0",
        "wsgi.input": BytesIO(b""),
    }
    app(environ, start_response)
    expect(len(captured) == 1, f"expected 1 start_response call, got {len(captured)}")
    expect(captured[0][0] == "503 Service Unavailable", f"expected '503 Service Unavailable' got '{captured[0][0]}'")

    print("PASS test_wsgi_503_status_text_for_degraded_health")


def test_hosted_api_has_executable_control_node_entrypoint() -> None:
    source = (load_module("arclink_hosted_api.py", "arclink_hosted_api_entrypoint_test").__loader__.path)  # type: ignore[attr-defined]
    text = open(source, encoding="utf-8").read()
    expect("def main() -> int:" in text, "hosted API needs a direct deployable entrypoint")
    expect("make_server(host, port, app)" in text, "hosted API entrypoint should bind the configured API host/port")
    expect('if __name__ == "__main__":' in text, "hosted API should be executable by compose")
    print("PASS test_hosted_api_has_executable_control_node_entrypoint")


def test_onboarding_payload_validation_rejects_missing_fields() -> None:
    control = load_module("arclink_control.py", "arclink_control_onb_validation_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_onb_validation_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})

    # answer without session_id -> error
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/onboarding/answer",
        headers={}, body=json.dumps({"question_key": "name"}), config=config,
    )
    expect(status in (400, 401), f"expected 400/401 got {status}: {payload}")

    # answer without question_key -> error
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/onboarding/answer",
        headers={}, body=json.dumps({"session_id": "onb_fake"}), config=config,
    )
    expect(status in (400, 401), f"expected 400/401 got {status}: {payload}")

    # checkout without session_id -> error
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/onboarding/checkout",
        headers={}, body=json.dumps({"price_id": "price_starter"}), config=config,
    )
    expect(status in (400, 401), f"expected 400/401 got {status}: {payload}")

    # start without channel_identity -> error (blank identity)
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/onboarding/start",
        headers={}, body=json.dumps({"channel": "web"}), config=config,
    )
    expect(status == 400, f"expected 400 got {status}: {payload}")

    print("PASS test_onboarding_payload_validation_rejects_missing_fields")


def test_onboarding_payload_validation_rejects_invalid_channel() -> None:
    control = load_module("arclink_control.py", "arclink_control_onb_channel_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_onb_channel_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/onboarding/start",
        headers={},
        body=json.dumps({"channel": "sms", "channel_identity": "user@test.test"}),
        config=config,
    )
    expect(status == 400, f"expected 400 for invalid channel, got {status}: {payload}")

    print("PASS test_onboarding_payload_validation_rejects_invalid_channel")


def test_admin_operator_snapshot_requires_auth_and_returns_snapshot() -> None:
    control = load_module("arclink_control.py", "arclink_control_op_snap_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_op_snap_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_op_snap_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={
        "ARCLINK_PRODUCT_NAME": "ArcLink",
        "ARCLINK_BASE_DOMAIN": "example.test",
        "ARCLINK_PRIMARY_PROVIDER": "chutes",
        "ARCLINK_E2E_LIVE": "1",
        "ARCLINK_E2E_DOCKER": "1",
        "STRIPE_SECRET_KEY": "sk_test_operator_snapshot_secret",
        "STRIPE_WEBHOOK_SECRET": "whsec_operator_snapshot_secret",
        "CLOUDFLARE_API_TOKEN": "cf_operator_snapshot_secret",
        "CLOUDFLARE_ZONE_ID": "zone_operator_snapshot",
        "CHUTES_API_KEY": "chutes_operator_snapshot_secret",
        "TELEGRAM_BOT_TOKEN": "telegram_operator_snapshot_secret",
        "DISCORD_BOT_TOKEN": "discord_operator_snapshot_secret",
        "DISCORD_APP_ID": "discord_app_operator_snapshot",
    })
    api.upsert_arclink_admin(conn, admin_id="admin_op", email="op@example.test", role="ops")

    # No auth -> 401
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/admin/operator-snapshot",
        headers={}, config=config,
    )
    expect(status == 401, f"expected 401 got {status}")

    # With auth -> 200 with expected keys
    session = api.create_arclink_admin_session(conn, admin_id="admin_op", session_id="asess_op")
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/admin/operator-snapshot",
        headers=auth_headers(session), config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect("host_readiness" in payload, f"missing host_readiness: {list(payload.keys())}")
    expect("provider_diagnostics" in payload, f"missing provider_diagnostics: {list(payload.keys())}")
    expect("live_journey" in payload, f"missing live_journey: {list(payload.keys())}")
    expect("evidence" in payload, f"missing evidence: {list(payload.keys())}")
    expect(payload["live_journey"]["all_credentials_present"] is True, f"expected config env to satisfy journey: {payload['live_journey']}")
    expect(payload["evidence"]["live_proof"] == "pending_credentialed_run", f"live proof should wait for evidence: {payload['evidence']}")
    # Verify no secret values leak
    snapshot_str = json.dumps(payload)
    for secret_value in (
        "sk_test_operator_snapshot_secret",
        "whsec_operator_snapshot_secret",
        "cf_operator_snapshot_secret",
        "chutes_operator_snapshot_secret",
        "telegram_operator_snapshot_secret",
        "discord_operator_snapshot_secret",
    ):
        expect(secret_value not in snapshot_str, f"secret value leaked in snapshot: {secret_value}")

    print("PASS test_admin_operator_snapshot_requires_auth_and_returns_snapshot")


def test_admin_scale_operations_requires_auth_and_returns_snapshot() -> None:
    control = load_module("arclink_control.py", "arclink_control_scale_ops_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_scale_ops_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_scale_ops_test")
    executor_mod = load_module("arclink_executor.py", "arclink_executor_scale_ops_test")
    fleet = load_module("arclink_fleet.py", "arclink_fleet_scale_ops_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_scale_ops_test")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_scale_ops_test")
    worker = load_module("arclink_action_worker.py", "arclink_action_worker_scale_ops_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    api.upsert_arclink_admin(conn, admin_id="admin_scale", email="scale@example.test", role="ops")

    fleet.register_fleet_host(conn, hostname="scale-1.example.test", region="us-east", capacity_slots=4)
    fleet.place_deployment(conn, deployment_id="dep_scale", region="us-east")

    dashboard.queue_arclink_admin_action(
        conn,
        admin_id="admin_scale",
        action_type="restart",
        target_kind="deployment",
        target_id="dep_scale",
        reason="test worker route",
        idempotency_key="scale_ops_worker",
    )
    executor = executor_mod.ArcLinkExecutor(
        config=executor_mod.ArcLinkExecutorConfig(live_enabled=True, adapter_name="fake"),
    )
    worker.process_next_arclink_action(conn, executor=executor)

    stale = dashboard.queue_arclink_admin_action(
        conn,
        admin_id="admin_scale",
        action_type="dns_repair",
        target_kind="deployment",
        target_id="dep_scale",
        reason="test stale route",
        idempotency_key="scale_ops_stale",
    )
    conn.execute(
        "UPDATE arclink_action_intents SET created_at = '2020-01-01T00:00:00+00:00' WHERE action_id = ?",
        (stale["action_id"],),
    )
    rollout.create_rollout(
        conn,
        deployment_id="dep_scale",
        version_tag="v1.2.3",
        waves=[{"percentage": 10, "hosts": ["scale-1.example.test"]}],
        rollback_plan={
            "actions": ["preserve_state_roots"],
            "state_roots": {"deployment": "/arcdata/deployments/dep_scale"},
        },
    )
    conn.commit()

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/admin/scale-operations",
        headers={}, config=config,
    )
    expect(status == 401, f"expected 401 got {status}: {payload}")

    session = api.create_arclink_admin_session(conn, admin_id="admin_scale", session_id="asess_scale")
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/admin/scale-operations",
        headers=auth_headers(session), config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect(payload["fleet_capacity"]["total_hosts"] == 1, f"fleet capacity missing: {payload}")
    expect(payload["fleet_capacity"]["available_slots"] == 3, f"placement load missing: {payload['fleet_capacity']}")
    expect(len(payload["placements"]) == 1, f"placement missing: {payload['placements']}")
    expect(len(payload["recent_action_attempts"]) == 1, f"attempt missing: {payload['recent_action_attempts']}")
    expect(payload["last_executor_result"]["status"] == "succeeded", f"last executor result missing: {payload}")
    expect(len(payload["stale_actions"]) == 1, f"stale action missing: {payload['stale_actions']}")
    expect(len(payload["active_rollouts"]) == 1, f"active rollout missing: {payload['active_rollouts']}")

    print("PASS test_admin_scale_operations_requires_auth_and_returns_snapshot")


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
    test_public_onboarding_checkout_resolves_live_stripe_from_config()
    test_web_telegram_discord_onboarding_parity()
    test_admin_dns_drift_route()
    test_admin_logout_clears_cookies_and_revokes_session()
    test_stripe_webhook_processes_entitlement_transition()
    test_telegram_webhook_route()
    test_telegram_webhook_sends_reply_when_transport_is_available()
    test_discord_webhook_route()
    test_health_endpoint_requires_no_auth()
    test_user_provider_state_route()
    test_admin_provider_state_route()
    test_admin_reconciliation_route()
    test_stripe_webhook_rejects_bad_signature()
    test_unauthenticated_logout_and_portal_rejected()
    test_wsgi_adapter_smoke()
    test_hosted_api_has_executable_control_node_entrypoint()
    test_read_only_admin_blocked_from_mutations()
    test_login_rejects_unknown_email()
    test_openapi_spec_route_serves_valid_contract()
    test_openapi_spec_matches_static_copy()
    test_rate_limit_returns_429_with_headers()
    test_rate_limit_onboarding_returns_429()
    test_wsgi_503_status_text_for_degraded_health()
    test_onboarding_payload_validation_rejects_missing_fields()
    test_onboarding_payload_validation_rejects_invalid_channel()
    test_admin_operator_snapshot_requires_auth_and_returns_snapshot()
    test_admin_scale_operations_requires_auth_and_returns_snapshot()
    print("PASS all 46 ArcLink hosted API tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
