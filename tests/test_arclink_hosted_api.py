#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from concurrent.futures import Future
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from arclink_test_helpers import auth_headers, expect, load_module, memory_db


def browser_auth_headers(session: dict, *, kind: str = "user", csrf: bool = False, token: str = "") -> dict[str, str]:
    cookie = (
        f"arclink_{kind}_session_id={session['session_id']}; "
        f"arclink_{kind}_session_token={token or session['session_token']}; "
        f"arclink_{kind}_csrf={session['csrf_token']}"
    )
    headers = {"Cookie": cookie}
    if csrf:
        headers["X-ArcLink-CSRF-Token"] = session["csrf_token"]
    return headers


def seed_paid_deployment(
    control,
    onboarding,
    conn,
    *,
    session_id: str = "onb_hosted",
    email: str = "hosted-user@example.test",
    display_name: str = "Hosted User",
    prefix: str = "hosted-vault-1a2b",
    model_id: str = "model-hosted",
):
    session = onboarding.create_or_resume_arclink_onboarding_session(
        conn,
        channel="web",
        channel_identity=email,
        session_id=session_id,
        email_hint=email,
        display_name_hint=display_name,
        selected_plan_id="sovereign",
        selected_model_id=model_id,
    )
    prepared = onboarding.prepare_arclink_onboarding_deployment(
        conn,
        session_id=session["session_id"],
        base_domain="example.test",
        prefix=prefix,
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
        body=json.dumps({"channel": "web", "email": "new@example.test", "plan_id": "sovereign"}),
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


def test_user_agent_identity_route_requires_csrf_and_updates_deployment() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_agent_identity_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_agent_identity_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_agent_identity_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_agent_identity_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    prepared = seed_paid_deployment(
        control,
        onboarding,
        conn,
        session_id="onb_hosted_agent_identity",
        email="agent-identity@example.test",
        prefix="agent-identity-1a2b",
    )
    session = api.create_arclink_user_session(conn, user_id=prepared["user_id"], session_id="usess_agent_identity_hosted")
    body = json.dumps({
        "deployment_id": prepared["deployment_id"],
        "agent_name": "Atlas",
        "agent_title": "the right hand",
    })

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/user/agent-identity",
        headers=browser_auth_headers(session),
        body=body,
        config=config,
    )
    expect(status == 401, f"agent identity without CSRF expected 401 got {status}: {payload}")

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/user/agent-identity",
        headers=browser_auth_headers(session, csrf=True),
        body=body,
        config=config,
    )
    expect(status == 200, f"agent identity update expected 200 got {status}: {payload}")
    expect(payload["deployment"]["agent_name"] == "Atlas", str(payload))
    expect(payload["deployment"]["agent_title"] == "the right hand", str(payload))
    print("PASS test_user_agent_identity_route_requires_csrf_and_updates_deployment")


def test_wrapped_routes_are_scoped_csrf_gated_and_admin_aggregate_only() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_wrapped_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_wrapped_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_wrapped_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_wrapped_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    prepared = seed_paid_deployment(control, onboarding, conn, session_id="onb_wrapped", email="wrapped@example.test")
    conn.execute(
        """
        INSERT INTO arclink_wrapped_reports (
          report_id, user_id, period, period_start, period_end, status,
          ledger_json, novelty_score, delivery_channel, created_at, delivered_at
        ) VALUES ('wrap_hosted', ?, 'daily', '2026-05-13T00:00:00+00:00',
          '2026-05-14T00:00:00+00:00', 'generated', ?, 81.0, 'telegram', ?, '')
        """,
        (
            prepared["user_id"],
            json.dumps(
                {
                    "formula_version": "wrapped_novelty_v1",
                    "plain_text": "Captain report with sk_test_hosted_wrapped_secret",
                    "markdown": "# ArcLink Wrapped",
                    "stats": [{"key": "quiet_build_index", "label": "Quiet build index", "value": 1.5}],
                    "source_counts": {"events": 2},
                },
                sort_keys=True,
            ),
            control.utc_now_iso(),
        ),
    )
    conn.commit()

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/user/wrapped", headers={}, config=config,
    )
    expect(status == 401, f"expected 401 got {status}: {payload}")

    user_session = api.create_arclink_user_session(conn, user_id=prepared["user_id"], session_id="usess_wrapped")
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/user/wrapped",
        headers=browser_auth_headers(user_session),
        config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect(payload["reports"][0]["report_id"] == "wrap_hosted", str(payload))
    expect("sk_test_hosted_wrapped_secret" not in payload["reports"][0]["plain_text"], str(payload["reports"][0]))

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/user/wrapped-frequency",
        headers=browser_auth_headers(user_session),
        body=json.dumps({"frequency": "weekly"}),
        config=config,
    )
    expect(status == 401, f"wrapped frequency without CSRF expected 401 got {status}: {payload}")

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/user/wrapped-frequency",
        headers=browser_auth_headers(user_session, csrf=True),
        body=json.dumps({"frequency": "weekly"}),
        config=config,
    )
    expect(status == 200 and payload["wrapped_frequency"] == "weekly", f"expected weekly update got {status}: {payload}")

    api.upsert_arclink_admin(conn, admin_id="admin_wrapped", email="admin-wrapped@example.test", role="ops")
    admin_session = api.create_arclink_admin_session(conn, admin_id="admin_wrapped", session_id="asess_wrapped")
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/admin/wrapped",
        headers=browser_auth_headers(admin_session, kind="admin"),
        config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    serialized = json.dumps(payload, sort_keys=True)
    expect("plain_text" not in serialized and "markdown" not in serialized, serialized)
    expect(payload["reports_by_status"]["generated"] == 1, str(payload))
    print("PASS test_wrapped_routes_are_scoped_csrf_gated_and_admin_aggregate_only")


def test_user_crew_recipe_routes_require_csrf_and_apply_recipe() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_crew_recipe_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_crew_recipe_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_crew_recipe_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_crew_recipe_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    prepared = seed_paid_deployment(
        control,
        onboarding,
        conn,
        session_id="onb_hosted_crew_recipe",
        email="crew-route@example.test",
        prefix="crew-route-1a2b",
    )
    session = api.create_arclink_user_session(conn, user_id=prepared["user_id"], session_id="usess_crew_recipe_hosted")
    body = json.dumps({
        "role": "founder",
        "mission": "ship the launch",
        "treatment": "peer",
        "preset": "Frontier",
        "capacity": "development",
    })

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/user/crew-recipe",
        headers=auth_headers(session),
        config=config,
    )
    expect(status == 200 and payload["current"] is None, f"crew recipe read expected empty 200 got {status}: {payload}")

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/user/crew-recipe/preview",
        headers=browser_auth_headers(session),
        body=body,
        config=config,
    )
    expect(status == 401, f"crew recipe preview without CSRF expected 401 got {status}: {payload}")

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/user/crew-recipe/preview",
        headers=browser_auth_headers(session, csrf=True),
        body=body,
        config=config,
    )
    expect(status == 200 and payload["preview"]["mode"] == "fallback", f"crew preview expected fallback 200 got {status}: {payload}")

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/user/crew-recipe/apply",
        headers=browser_auth_headers(session, csrf=True),
        body=body,
        config=config,
    )
    expect(status == 200 and payload["recipe"]["preset"] == "Frontier", f"crew apply expected 200 got {status}: {payload}")
    expect(payload["identity_projection"][prepared["deployment_id"]]["status"] in {"skipped", "projected"}, str(payload))
    print("PASS test_user_crew_recipe_routes_require_csrf_and_apply_recipe")


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
    expect(payload.get("error") == "unauthorized", str(payload))

    # With CSRF -> 202
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/admin/actions",
        headers=browser_auth_headers(session, kind="admin", csrf=True),
        body=action_body,
        config=config,
    )
    expect(status == 202, f"expected 202 got {status}: {payload}")
    expect(payload["action"]["status"] == "queued", str(payload))

    print("PASS test_admin_action_requires_csrf_and_mutation_role")


def test_admin_crew_recipe_route_is_admin_csrf_and_audited() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_admin_crew_recipe_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_admin_crew_recipe_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_admin_crew_recipe_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_admin_crew_recipe_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    prepared = seed_paid_deployment(
        control,
        onboarding,
        conn,
        session_id="onb_hosted_admin_crew_recipe",
        email="admin-crew-route@example.test",
        prefix="crew-route-behalf-1a2b",
    )
    api.upsert_arclink_admin(conn, admin_id="admin_crew_route", email="admin-crew-route@example.test", role="ops")
    session = api.create_arclink_admin_session(conn, admin_id="admin_crew_route", session_id="asess_crew_route", mfa_verified=True)
    body = json.dumps({
        "user_id": prepared["user_id"],
        "role": "operator",
        "mission": "stabilize launch",
        "treatment": "coach",
        "preset": "Vanguard",
        "capacity": "sales",
    })
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/admin/crew-recipe/apply",
        headers=auth_headers(session),
        body=body,
        config=config,
    )
    expect(status == 401, f"admin crew apply without CSRF expected 401 got {status}: {payload}")
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/admin/crew-recipe/apply",
        headers=browser_auth_headers(session, kind="admin", csrf=True),
        body=body,
        config=config,
    )
    expect(status == 200 and payload["recipe"]["preset"] == "Vanguard", f"admin crew apply expected 200 got {status}: {payload}")
    audit = [row["action"] for row in conn.execute("SELECT action FROM arclink_audit_log").fetchall()]
    expect("crew_recipe_applied_by_operator" in audit, str(audit))
    print("PASS test_admin_crew_recipe_route_is_admin_csrf_and_audited")


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
    expect("Authorization" not in cors_dict.get("access-control-allow-headers", ""), str(cors_dict))
    expect("X-ArcLink-Session-Id" not in cors_dict.get("access-control-allow-headers", ""), str(cors_dict))
    expect("X-ArcLink-Session-Token" not in cors_dict.get("access-control-allow-headers", ""), str(cors_dict))
    expect("X-ArcLink-CSRF-Token" in cors_dict.get("access-control-allow-headers", ""), str(cors_dict))
    expect(cors_dict.get("allow") == "POST, OPTIONS", str(cors_dict))

    status, payload, headers = hosted.route_arclink_hosted_api(
        conn,
        method="OPTIONS",
        path="/api/v1/does-not-exist",
        headers={},
        config=config,
    )
    expect(status == 404, f"unknown OPTIONS should route-check, got {status}: {payload}")
    cors_dict = {k.lower(): v for k, v in headers}
    expect("access-control-allow-origin" in cors_dict, str(cors_dict))

    local_config = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "localhost",
        "ARCLINK_CORS_ORIGIN": "http://localhost:3000",
    })
    expect(local_config.cookie_secure is False, "plain HTTP localhost should default to non-Secure cookies")
    expect(local_config.cookie_samesite == "Strict", "CSRF/session cookies should default SameSite=Strict")
    forced_secure = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "localhost",
        "ARCLINK_CORS_ORIGIN": "http://localhost:3000",
        "ARCLINK_COOKIE_SECURE": "1",
        "ARCLINK_COOKIE_SAMESITE": "Lax",
    })
    expect(forced_secure.cookie_secure is True, "explicit cookie secure override should win")
    expect(forced_secure.cookie_samesite == "Lax", "explicit SameSite compatibility override should win")

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
    api.upsert_arclink_admin(
        conn,
        admin_id="admin_login",
        email="login@example.test",
        role="owner",
        password="admin-test-password",
    )

    status, payload, headers = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/auth/admin/login",
        headers={},
        body=json.dumps({"email": "login@example.test", "password": "admin-test-password"}),
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


def test_unified_login_resolves_user_or_admin_session() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_unified_login_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_unified_login_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_unified_login_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_unified_login_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "example.test",
        "ARCLINK_COOKIE_DOMAIN": ".arclink.online",
    })
    prepared = seed_paid_deployment(
        control,
        onboarding,
        conn,
        session_id="onb_unified_login",
        email="unified-user@example.test",
    )
    api.set_arclink_user_password(conn, user_id=prepared["user_id"], password="user-unified-password")
    api.upsert_arclink_admin(
        conn,
        admin_id="admin_unified_login",
        email="unified-admin@example.test",
        role="ops",
        password="admin-unified-password",
    )

    status, payload, headers = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/auth/login",
        headers={},
        body=json.dumps({"email": "unified-user@example.test", "password": "user-unified-password"}),
        config=config,
    )
    expect(status == 201, f"user unified login expected 201 got {status}: {payload}")
    expect(payload["session_kind"] == "user", str(payload))
    cookie_text = " ".join(v for k, v in headers if k == "Set-Cookie")
    expect("arclink_user_session_id=" in cookie_text, cookie_text)
    expect("arclink_admin_session_id=;" in cookie_text, cookie_text)

    status, payload, headers = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/auth/login",
        headers={},
        body=json.dumps({"email": "unified-admin@example.test", "password": "admin-unified-password"}),
        config=config,
    )
    expect(status == 201, f"admin unified login expected 201 got {status}: {payload}")
    expect(payload["session_kind"] == "admin", str(payload))
    expect(payload["role"] == "ops", str(payload))
    cookie_text = " ".join(v for k, v in headers if k == "Set-Cookie")
    expect("arclink_admin_session_id=" in cookie_text, cookie_text)
    expect("arclink_user_session_id=;" in cookie_text, cookie_text)

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/auth/login",
        headers={},
        body=json.dumps({"email": "unified-admin@example.test", "password": "admin-unified-password"}),
        config=config,
        remote_addr="198.51.100.9",
    )
    expect(status == 401, f"admin unified login outside backend CIDR expected 401 got {status}: {payload}")

    print("PASS test_unified_login_resolves_user_or_admin_session")


def test_admin_login_ignores_client_asserted_mfa() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_login_mfa_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_login_mfa_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_login_mfa_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_login_mfa_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    prepared = seed_paid_deployment(control, onboarding, conn)
    api.upsert_arclink_admin(
        conn,
        admin_id="admin_login_mfa",
        email="login-mfa@example.test",
        role="owner",
        password="admin-test-password",
    )
    api.enroll_arclink_admin_totp_factor(
        conn,
        admin_id="admin_login_mfa",
        secret_ref="secret://arclink/admin/admin_login_mfa/totp",
        factor_id="totp_login_mfa",
    )
    api.verify_arclink_admin_totp_factor(conn, factor_id="totp_login_mfa")

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/auth/admin/login",
        headers={},
        body=json.dumps({"email": "login-mfa@example.test", "password": "admin-test-password", "mfa_verified": True}),
        config=config,
    )
    expect(status == 201, f"expected 201 got {status}: {payload}")
    session = payload["session"]
    expect(not session.get("mfa_verified_at"), str(session))

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/admin/actions",
        headers=browser_auth_headers(session, kind="admin", csrf=True),
        body=json.dumps({
            "action_type": "restart",
            "target_kind": "deployment",
            "target_id": prepared["deployment_id"],
            "reason": "mfa should not be self-asserted",
            "idempotency_key": "hosted-mfa-1",
        }),
        config=config,
    )
    expect(status == 401, f"expected MFA rejection got {status}: {payload}")
    expect(payload.get("error") == "unauthorized", str(payload))
    print("PASS test_admin_login_ignores_client_asserted_mfa")


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
        headers=browser_auth_headers(admin_session, kind="admin", csrf=True),
        body=json.dumps({"target_session_id": user_session["session_id"], "session_kind": "user", "reason": "test revoke"}),
        config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect(payload["session"]["status"] == "revoked", str(payload))

    print("PASS test_session_revoke_requires_admin_auth_and_csrf")


def test_stripe_webhook_route_rejects_without_secret() -> None:
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
    # Money-safety: misconfigured webhook MUST return 5xx so Stripe retries and
    # operators are forced to notice. A 200 would silently accept payments.
    expect(status == 503, f"expected 503 got {status}")
    expect(payload.get("error") == "stripe_webhook_secret_unset", str(payload))

    print("PASS test_stripe_webhook_route_rejects_without_secret")


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
    lifecycle = payload["renewal_lifecycle"]
    expect(lifecycle["provider_access"] == "allowed", str(lifecycle))
    expect(lifecycle["purge_policy"] == "not_applicable", str(lifecycle))

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


def test_user_provisioning_status_missing_requested_deployment_is_404() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_prov_missing_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_prov_missing_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_prov_missing_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_prov_missing_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    prepared = seed_paid_deployment(control, onboarding, conn)
    session = api.create_arclink_user_session(conn, user_id=prepared["user_id"], session_id="usess_prov_missing")

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/user/provisioning",
        headers=auth_headers(session),
        query={"deployment_id": "dep_missing_requested"},
        config=config,
    )
    expect(status == 404, f"expected requested deployment 404 got {status}: {payload}")
    expect(payload == {"error": "deployment_not_found", "deployments": []}, str(payload))
    print("PASS test_user_provisioning_status_missing_requested_deployment_is_404")


def test_user_routes_are_isolated_across_accounts() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_isolation_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_isolation_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_isolation_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_isolation_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    user_a = seed_paid_deployment(
        control,
        onboarding,
        conn,
        session_id="onb_hosted_iso_a",
        email="isolation-a@example.test",
        display_name="Isolation A",
        prefix="isolation-a-1a2b",
        model_id="model-a",
    )
    user_b = seed_paid_deployment(
        control,
        onboarding,
        conn,
        session_id="onb_hosted_iso_b",
        email="isolation-b@example.test",
        display_name="Isolation B",
        prefix="isolation-b-1a2b",
        model_id="model-b",
    )
    control.upsert_arclink_service_health(
        conn,
        deployment_id=user_b["deployment_id"],
        service_name="foreign-health-watch",
        status="degraded",
    )
    control.upsert_arclink_subscription_mirror(
        conn,
        subscription_id="sub_iso_a",
        user_id=user_a["user_id"],
        stripe_customer_id="cus_iso_a",
        stripe_subscription_id="stripe_sub_iso_a",
        status="active",
    )
    control.upsert_arclink_subscription_mirror(
        conn,
        subscription_id="sub_iso_b",
        user_id=user_b["user_id"],
        stripe_customer_id="cus_iso_b",
        stripe_subscription_id="stripe_sub_iso_b",
        status="active",
    )
    session_a = api.create_arclink_user_session(conn, user_id=user_a["user_id"], session_id="usess_iso_a")

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/user/dashboard",
        headers=auth_headers(session_a),
        query={"user_id": user_b["user_id"]},
        config=config,
    )
    expect(status == 401, f"cross-user dashboard query expected 401 got {status}: {payload}")
    expect(payload.get("error") == "unauthorized", str(payload))

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/user/dashboard",
        headers=auth_headers(session_a),
        config=config,
    )
    expect(status == 200, f"own dashboard expected 200 got {status}: {payload}")
    rendered = json.dumps(payload, sort_keys=True)
    expect(user_a["deployment_id"] in rendered and user_a["user_id"] in rendered, rendered)
    expect(user_b["deployment_id"] not in rendered and user_b["user_id"] not in rendered, rendered)
    expect("foreign-health-watch" not in rendered, rendered)

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/user/provider-state",
        headers=auth_headers(session_a),
        config=config,
    )
    expect(status == 200, f"provider state expected 200 got {status}: {payload}")
    provider_text = json.dumps(payload, sort_keys=True)
    expect("model-a" in provider_text and user_a["deployment_id"] in provider_text, provider_text)
    expect("model-b" not in provider_text and user_b["deployment_id"] not in provider_text, provider_text)

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/user/provisioning",
        headers=auth_headers(session_a),
        query={"deployment_id": user_b["deployment_id"]},
        config=config,
    )
    expect(status == 401, f"cross-user provisioning query expected 401 got {status}: {payload}")
    expect(payload.get("error") == "unauthorized", str(payload))

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/user/billing",
        headers=auth_headers(session_a),
        config=config,
    )
    expect(status == 200, f"billing expected 200 got {status}: {payload}")
    billing_text = json.dumps(payload, sort_keys=True)
    expect("sub_iso_a" in billing_text and "cus_iso_a" in billing_text, billing_text)
    expect("sub_iso_b" not in billing_text and "cus_iso_b" not in billing_text, billing_text)

    print("PASS test_user_routes_are_isolated_across_accounts")


def test_user_credentials_are_acknowledged_and_removed_after_storage() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_credentials_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_credentials_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_credentials_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_credentials_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    user_a = seed_paid_deployment(control, onboarding, conn)
    user_b = seed_paid_deployment(
        control,
        onboarding,
        conn,
        session_id="onb_hosted_creds_b",
        email="creds-b@example.test",
        display_name="Credentials B",
        prefix="creds-b-1a2b",
        model_id="model-b",
    )
    session_a = api.create_arclink_user_session(conn, user_id=user_a["user_id"], session_id="usess_creds_a")
    secret_tmp = tempfile.TemporaryDirectory()
    old_secret_store = os.environ.get("ARCLINK_SECRET_STORE_DIR")
    os.environ["ARCLINK_SECRET_STORE_DIR"] = secret_tmp.name
    dashboard_secret_ref = f"secret://arclink/dashboard/users/{user_a['user_id']}/password"
    dashboard_secret_dir = Path(secret_tmp.name) / "users"
    dashboard_secret_dir.mkdir(parents=True)
    dashboard_secret_path = dashboard_secret_dir / f"{hashlib.sha256(dashboard_secret_ref.encode('utf-8')).hexdigest()}.secret"
    dashboard_secret_path.write_text("arc_dashboard_test_password\n", encoding="utf-8")

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/user/credentials", headers={}, config=config,
    )
    expect(status == 401, f"expected credentials auth failure got {status}: {payload}")

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/user/credentials",
        headers=auth_headers(session_a),
        query={"deployment_id": user_b["deployment_id"]},
        config=config,
    )
    expect(status == 401, f"cross-user credentials expected 401 got {status}: {payload}")

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/user/credentials",
        headers=auth_headers(session_a),
        config=config,
    )
    expect(status == 200, f"expected credentials 200 got {status}: {payload}")
    credentials = payload["credentials"]
    expect(credentials, f"expected pending credential handoffs: {payload}")
    rendered = json.dumps(payload, sort_keys=True)
    expect("raw_secret" in rendered, rendered)
    expect("secret://masked" in rendered, rendered)
    expect("dashboard_password" in rendered, rendered)
    expect(user_b["deployment_id"] not in rendered and user_b["user_id"] not in rendered, rendered)
    dashboard_credential = next(item for item in credentials if item["credential_kind"] == "dashboard_password")
    provider_credential = next(item for item in credentials if item["credential_kind"] == "chutes_api_key")
    expect(dashboard_credential["raw_secret"] == "arc_dashboard_test_password", str(dashboard_credential))
    expect(dashboard_credential["reveal_mode"] == "user_dashboard", str(dashboard_credential))
    expect(dashboard_credential["expires_at"], str(dashboard_credential))
    expect(bool(dashboard_credential["revealed_at"]), str(dashboard_credential))
    expect(provider_credential["raw_secret"] == "", str(provider_credential))
    expect(provider_credential["reveal_mode"] == "not_revealable_from_user_api", str(provider_credential))
    handoff_id = dashboard_credential["handoff_id"]

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/user/credentials",
        headers=auth_headers(session_a),
        config=config,
    )
    expect(status == 200, f"second credentials read expected 200 got {status}: {payload}")
    repeated = next(item for item in payload["credentials"] if item["handoff_id"] == handoff_id)
    expect(repeated["raw_secret"] == "", str(repeated))
    expect(repeated["reveal_mode"] == "not_revealable_from_user_api", str(repeated))

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/user/credentials/acknowledge",
        headers=auth_headers(session_a),
        body=json.dumps({"handoff_id": handoff_id}),
        config=config,
    )
    expect(status == 401, f"credential ack without CSRF expected 401 got {status}: {payload}")

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/user/credentials/acknowledge",
        headers=browser_auth_headers(session_a, csrf=True),
        body=json.dumps({"handoff_id": handoff_id}),
        config=config,
    )
    expect(status == 200, f"credential ack expected 200 got {status}: {payload}")
    credential = payload["credential"]
    expect(credential["status"] == "removed", str(credential))
    expect("secret_ref" not in credential, str(credential))
    expect(credential["delivery_hint"] == "", str(credential))

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/user/credentials",
        headers=auth_headers(session_a),
        query={"deployment_id": user_a["deployment_id"]},
        config=config,
    )
    expect(status == 200, f"post-ack credentials expected 200 got {status}: {payload}")
    rendered_after = json.dumps(payload, sort_keys=True)
    expect(handoff_id not in rendered_after, rendered_after)
    expect(payload["removed_count"] >= 1, str(payload))
    if old_secret_store is None:
        os.environ.pop("ARCLINK_SECRET_STORE_DIR", None)
    else:
        os.environ["ARCLINK_SECRET_STORE_DIR"] = old_secret_store
    secret_tmp.cleanup()

    print("PASS test_user_credentials_are_acknowledged_and_removed_after_storage")


def test_user_share_grants_create_approved_accepted_linked_resources() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_share_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_share_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_share_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_share_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    owner = seed_paid_deployment(
        control,
        onboarding,
        conn,
        session_id="onb_share_owner",
        email="share-owner@example.test",
        display_name="Share Owner",
        prefix="share-owner-1a2b",
    )
    recipient = seed_paid_deployment(
        control,
        onboarding,
        conn,
        session_id="onb_share_recipient",
        email="share-recipient@example.test",
        display_name="Share Recipient",
        prefix="share-recipient-1a2b",
    )
    owner_session = api.create_arclink_user_session(conn, user_id=owner["user_id"], session_id="usess_share_owner")
    recipient_session = api.create_arclink_user_session(conn, user_id=recipient["user_id"], session_id="usess_share_recipient")

    with tempfile.TemporaryDirectory() as tmp:
        state_root = Path(tmp)
        owner_vault = state_root / "owner" / "vault"
        recipient_linked = state_root / "recipient" / "linked-resources"
        shared_dir = owner_vault / "Projects" / "brief"
        shared_dir.mkdir(parents=True, exist_ok=True)
        (shared_dir / "overview.md").write_text("# Project Brief\n\nShared read-only context.\n", encoding="utf-8")
        (shared_dir / ".env").write_text("TOKEN=do-not-project\n", encoding="utf-8")
        for deployment, roots in (
            (
                owner,
                {
                    "vault": str(owner_vault),
                    "code_workspace": str(state_root / "owner" / "workspace"),
                    "linked_resources": str(state_root / "owner" / "linked-resources"),
                },
            ),
            (
                recipient,
                {
                    "vault": str(state_root / "recipient" / "vault"),
                    "code_workspace": str(state_root / "recipient" / "workspace"),
                    "linked_resources": str(recipient_linked),
                },
            ),
        ):
            conn.execute(
                "UPDATE arclink_deployments SET metadata_json = ? WHERE deployment_id = ?",
                (json.dumps({"state_roots": roots}, sort_keys=True), deployment["deployment_id"]),
            )
        conn.commit()

        same_recipient_linked = state_root / "owner-second" / "linked-resources"
        same_recipient_deployment = control.reserve_arclink_deployment_prefix(
            conn,
            deployment_id="arcdep_share_owner_second",
            user_id=owner["user_id"],
            prefix="share-owner-second",
            base_domain="example.test",
            status="active",
            metadata={
                "state_roots": {
                    "vault": str(state_root / "owner-second" / "vault"),
                    "code_workspace": str(state_root / "owner-second" / "workspace"),
                    "linked_resources": str(same_recipient_linked),
                }
            },
        )

        body = {
            "recipient_user_id": recipient["user_id"],
            "owner_deployment_id": owner["deployment_id"],
            "resource_kind": "drive",
            "resource_root": "vault",
            "resource_path": "/Projects/brief",
            "display_name": "Project Brief",
        }
        status, payload, _ = hosted.route_arclink_hosted_api(
            conn,
            method="POST",
            path="/api/v1/user/share-grants",
            headers=auth_headers(owner_session),
            body=json.dumps(body),
            config=config,
        )
        expect(status == 401, f"share create without CSRF expected 401 got {status}: {payload}")

        status, payload, _ = hosted.route_arclink_hosted_api(
            conn,
            method="POST",
            path="/api/v1/user/share-grants",
            headers=browser_auth_headers(owner_session, csrf=True),
            body=json.dumps(body),
            config=config,
        )
        expect(status == 201, f"share create expected 201 got {status}: {payload}")
        grant = payload["grant"]
        grant_id = grant["grant_id"]
        expect(grant["status"] == "pending_owner_approval", str(grant))
        expect(grant["expires_at"], str(grant))
        expect(grant["reshare_allowed"] is False, str(grant))
        expect(grant["projection"]["status"] == "not_materialized", str(grant))
        expect(payload["owner_notification"]["queued"] is False, str(payload["owner_notification"]))

        status, payload, _ = hosted.route_arclink_hosted_api(
            conn,
            method="POST",
            path="/api/v1/user/share-grants/accept",
            headers=browser_auth_headers(recipient_session, csrf=True),
            body=json.dumps({"grant_id": grant_id}),
            config=config,
        )
        expect(status == 401, f"accept before approval expected 401 got {status}: {payload}")

        status, payload, _ = hosted.route_arclink_hosted_api(
            conn,
            method="POST",
            path="/api/v1/user/share-grants/approve",
            headers=browser_auth_headers(recipient_session, csrf=True),
            body=json.dumps({"grant_id": grant_id}),
            config=config,
        )
        expect(status == 401, f"recipient approve expected 401 got {status}: {payload}")

        status, payload, _ = hosted.route_arclink_hosted_api(
            conn,
            method="POST",
            path="/api/v1/user/share-grants/approve",
            headers=browser_auth_headers(owner_session, csrf=True),
            body=json.dumps({"grant_id": grant_id}),
            config=config,
        )
        expect(status == 200, f"owner approve expected 200 got {status}: {payload}")
        expect(payload["grant"]["status"] == "approved", str(payload))

        status, payload, _ = hosted.route_arclink_hosted_api(
            conn,
            method="POST",
            path="/api/v1/user/share-grants/accept",
            headers=browser_auth_headers(recipient_session, csrf=True),
            body=json.dumps({"grant_id": grant_id}),
            config=config,
        )
        expect(status == 200, f"recipient accept expected 200 got {status}: {payload}")
        expect(payload["grant"]["status"] == "accepted", str(payload))
        projection = payload["grant"]["projection"]
        expect(projection["status"] == "materialized", str(projection))
        expect(projection["linked_root"] == "linked", str(projection))
        expect(projection["linked_path"].startswith(f"/{grant_id}"), str(projection))
        expect(projection["projection_mode"] == "living_symlink", str(projection))
        expect(projection["read_only"] is True, str(projection))
        projected_dir = recipient_linked / projection["linked_path"].strip("/")
        expect(projected_dir.is_symlink(), "accepted linked directory should be a living link")
        expect((projected_dir / "overview.md").read_text(encoding="utf-8").startswith("# Project Brief"), str(projection))
        (shared_dir / "overview.md").write_text("# Project Brief\n\nUpdated at source.\n", encoding="utf-8")
        expect("Updated at source" in (projected_dir / "overview.md").read_text(encoding="utf-8"), "linked projection should stay live")
        manifest = recipient_linked / ".arclink-linked-resources.json"
        expect(manifest.is_file(), "linked resource manifest should be written")
        manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
        expect(projection["linked_path"].strip("/") in manifest_payload["entries"], str(manifest_payload))

        status, payload, _ = hosted.route_arclink_hosted_api(
            conn,
            method="GET",
            path="/api/v1/user/linked-resources",
            headers=auth_headers(recipient_session),
            config=config,
        )
        expect(status == 200, f"linked resources expected 200 got {status}: {payload}")
        linked = payload["linked_resources"]
        expect(len(linked) == 1 and linked[0]["grant_id"] == grant_id, str(payload))
        expect(linked[0]["owner_user_id"] == owner["user_id"], str(linked[0]))
        expect(linked[0]["reshare_allowed"] is False, str(linked[0]))
        expect(linked[0]["linked_path"] == projection["linked_path"], str(linked[0]))
        expect(linked[0]["projection"]["status"] == "materialized", str(linked[0]))

        status, payload, _ = hosted.route_arclink_hosted_api(
            conn,
            method="GET",
            path="/api/v1/user/linked-resources",
            headers=auth_headers(owner_session),
            query={"user_id": recipient["user_id"]},
            config=config,
        )
        expect(status == 401, f"cross-user linked resources expected 401 got {status}: {payload}")

        status, payload, _ = hosted.route_arclink_hosted_api(
            conn,
            method="POST",
            path="/api/v1/user/share-grants/revoke",
            headers=auth_headers(owner_session),
            body=json.dumps({"grant_id": grant_id}),
            config=config,
        )
        expect(status == 401, f"revoke without CSRF expected 401 got {status}: {payload}")

        status, payload, _ = hosted.route_arclink_hosted_api(
            conn,
            method="POST",
            path="/api/v1/user/share-grants/revoke",
            headers=browser_auth_headers(recipient_session, csrf=True),
            body=json.dumps({"grant_id": grant_id}),
            config=config,
        )
        expect(status == 401, f"recipient revoke expected 401 got {status}: {payload}")

        status, payload, _ = hosted.route_arclink_hosted_api(
            conn,
            method="POST",
            path="/api/v1/user/share-grants/revoke",
            headers=browser_auth_headers(owner_session, csrf=True),
            body=json.dumps({"grant_id": grant_id}),
            config=config,
        )
        expect(status == 200, f"owner revoke expected 200 got {status}: {payload}")
        expect(payload["grant"]["status"] == "revoked", str(payload))
        expect(payload["grant"]["revoked_at"], str(payload))
        expect(payload["grant"]["projection"]["status"] == "removed", str(payload["grant"]))
        expect(not projected_dir.exists(), "revoked linked projection should be removed")
        manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
        expect(projection["linked_path"].strip("/") not in manifest_payload.get("entries", {}), str(manifest_payload))

        status, payload, _ = hosted.route_arclink_hosted_api(
            conn,
            method="GET",
            path="/api/v1/user/linked-resources",
            headers=auth_headers(recipient_session),
            config=config,
        )
        expect(status == 200, f"linked resources after revoke expected 200 got {status}: {payload}")
        expect(payload["linked_resources"] == [], str(payload))

        status, payload, _ = hosted.route_arclink_hosted_api(
            conn,
            method="POST",
            path="/api/v1/user/share-grants/revoke",
            headers=browser_auth_headers(owner_session, csrf=True),
            body=json.dumps({"grant_id": grant_id}),
            config=config,
        )
        expect(status == 200, f"idempotent owner revoke expected 200 got {status}: {payload}")
        expect(payload["grant"]["status"] == "revoked", str(payload))

        reshare_body = dict(body)
        reshare_body["recipient_user_id"] = owner["user_id"]
        reshare_body["resource_root"] = "linked"
        status, payload, _ = hosted.route_arclink_hosted_api(
            conn,
            method="POST",
            path="/api/v1/user/share-grants",
            headers=browser_auth_headers(recipient_session, csrf=True),
            body=json.dumps(reshare_body),
            config=config,
        )
        expect(status == 401, f"linked-root reshare expected 401 got {status}: {payload}")

        deny_body = dict(body)
        deny_body["resource_path"] = "/Projects/closed.md"
        deny_body["display_name"] = "Closed Brief"
        status, payload, _ = hosted.route_arclink_hosted_api(
            conn,
            method="POST",
            path="/api/v1/user/share-grants",
            headers=browser_auth_headers(owner_session, csrf=True),
            body=json.dumps(deny_body),
            config=config,
        )
        expect(status == 201, f"share create for deny expected 201 got {status}: {payload}")
        denied_grant_id = payload["grant"]["grant_id"]
        status, payload, _ = hosted.route_arclink_hosted_api(
            conn,
            method="POST",
            path="/api/v1/user/share-grants/deny",
            headers=browser_auth_headers(recipient_session, csrf=True),
            body=json.dumps({"grant_id": denied_grant_id}),
            config=config,
        )
        expect(status == 401, f"recipient deny expected 401 got {status}: {payload}")
        status, payload, _ = hosted.route_arclink_hosted_api(
            conn,
            method="POST",
            path="/api/v1/user/share-grants/deny",
            headers=browser_auth_headers(owner_session, csrf=True),
            body=json.dumps({"grant_id": denied_grant_id}),
            config=config,
        )
        expect(status == 200, f"owner deny expected 200 got {status}: {payload}")
        expect(payload["grant"]["status"] == "denied", str(payload))
        status, payload, _ = hosted.route_arclink_hosted_api(
            conn,
            method="POST",
            path="/api/v1/user/share-grants/accept",
            headers=browser_auth_headers(recipient_session, csrf=True),
            body=json.dumps({"grant_id": denied_grant_id}),
            config=config,
        )
        expect(status == 401, f"accept denied share expected 401 got {status}: {payload}")

        same_body = {
            "recipient_user_id": owner["user_id"],
            "owner_deployment_id": owner["deployment_id"],
            "recipient_deployment_id": same_recipient_deployment["deployment_id"],
            "resource_kind": "drive",
            "resource_root": "vault",
            "resource_path": "/Projects/brief",
            "display_name": "Brief for second agent",
        }
        status, payload, _ = hosted.route_arclink_hosted_api(
            conn,
            method="POST",
            path="/api/v1/user/share-grants",
            headers=browser_auth_headers(owner_session, csrf=True),
            body=json.dumps(same_body),
            config=config,
        )
        expect(status == 201, f"same-account share create expected 201 got {status}: {payload}")
        same_grant = payload["grant"]
        same_grant_id = same_grant["grant_id"]
        expect(same_grant["owner_user_id"] == same_grant["recipient_user_id"] == owner["user_id"], str(same_grant))
        expect(same_grant["status"] == "accepted", str(same_grant))
        expect(same_grant["approved_at"] and same_grant["accepted_at"], str(same_grant))
        expect(same_grant["owner_deployment_id"] == owner["deployment_id"], str(same_grant))
        expect(same_grant["recipient_deployment_id"] == same_recipient_deployment["deployment_id"], str(same_grant))
        expect(payload["owner_notification"]["reason"] == "same_account_auto_accepted", str(payload["owner_notification"]))
        same_projection = same_grant["projection"]
        expect(same_projection["status"] == "materialized", str(same_projection))
        same_projected_dir = same_recipient_linked / same_projection["linked_path"].strip("/")
        expect(same_projected_dir.is_symlink(), "same-account linked directory should be a living link")
        expect("Updated at source" in (same_projected_dir / "overview.md").read_text(encoding="utf-8"), str(same_projection))

        bad_same_body = dict(same_body)
        bad_same_body.pop("recipient_deployment_id")
        status, payload, _ = hosted.route_arclink_hosted_api(
            conn,
            method="POST",
            path="/api/v1/user/share-grants",
            headers=browser_auth_headers(owner_session, csrf=True),
            body=json.dumps(bad_same_body),
            config=config,
        )
        expect(status == 401, f"same-account share without recipient deployment expected 401 got {status}: {payload}")

        status, payload, _ = hosted.route_arclink_hosted_api(
            conn,
            method="POST",
            path="/api/v1/user/share-grants/revoke",
            headers=browser_auth_headers(owner_session, csrf=True),
            body=json.dumps({"grant_id": same_grant_id}),
            config=config,
        )
        expect(status == 200, f"same-account owner revoke expected 200 got {status}: {payload}")
        expect(payload["grant"]["status"] == "revoked", str(payload))
        expect(not same_projected_dir.exists(), "same-account revoked linked projection should be removed")

    print("PASS test_user_share_grants_create_approved_accepted_linked_resources")


def test_admin_service_health_route() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_health_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_health_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_health_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_health_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    first_deployment = seed_paid_deployment(control, onboarding, conn)
    api.upsert_arclink_admin(conn, admin_id="admin_health", email="health@example.test", role="ops")
    session = api.create_arclink_admin_session(conn, admin_id="admin_health", session_id="asess_health")

    # No auth -> 401
    status, _, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/admin/service-health", headers={}, config=config,
    )
    expect(status == 401, f"expected 401 got {status}")

    user_prepared = seed_paid_deployment(
        control,
        onboarding,
        conn,
        session_id="onb_health_user",
        email="health-user@example.test",
        display_name="Health User",
        prefix="health-user-1a2b",
    )
    user_session = api.create_arclink_user_session(conn, user_id=user_prepared["user_id"], session_id="usess_health_user")
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/admin/service-health",
        headers=auth_headers(user_session),
        config=config,
    )
    expect(status == 401, f"user session should not read admin health got {status}: {payload}")

    # With auth -> 200
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/admin/service-health",
        headers=auth_headers(session),
        config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect("service_health" in payload, str(payload))
    expect("recent_failures" in payload, str(payload))
    health_deployments = {row["deployment_id"] for row in payload["service_health"]}
    expect(first_deployment["deployment_id"] in health_deployments, str(payload["service_health"]))
    expect(user_prepared["deployment_id"] in health_deployments, str(payload["service_health"]))

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/admin/service-health",
        headers=auth_headers(session),
        query={"deployment_id": user_prepared["deployment_id"]},
        config=config,
    )
    expect(status == 200, f"filtered admin health expected 200 got {status}: {payload}")
    filtered_deployments = {row["deployment_id"] for row in payload["service_health"]}
    expect(filtered_deployments == {user_prepared["deployment_id"]}, str(payload["service_health"]))

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
        headers=browser_auth_headers(session, kind="admin", csrf=True),
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
        headers=browser_auth_headers(session, csrf=True),
        body=json.dumps({"return_url": "https://app.arclink.online/dashboard"}),
        config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect("portal_url" in payload, str(payload))
    expect("stripe.test/portal" in payload["portal_url"], str(payload))

    print("PASS test_user_portal_link_route")


def test_user_login_sets_session_cookies_and_logout_clears_them() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_userlogin_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_userlogin_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_userlogin_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_userlogin_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "example.test",
        "ARCLINK_COOKIE_DOMAIN": ".arclink.online",
    })
    prepared = seed_paid_deployment(control, onboarding, conn)
    api.set_arclink_user_password(conn, user_id=prepared["user_id"], password="hosted-user-password")

    # Email-only login is not enough to create a session.
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/auth/user/login",
        headers={},
        body=json.dumps({"email": "hosted-user@example.test"}),
        config=config,
    )
    expect(status == 401, f"email-only login expected 401 got {status}: {payload}")

    # Login
    status, payload, headers = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/auth/user/login",
        headers={},
        body=json.dumps({"email": "hosted-user@example.test", "password": "hosted-user-password"}),
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
        headers=browser_auth_headers(session),
        config=config,
    )
    expect(status == 401, f"expected 401 without CSRF got {status}")

    # Logout is a browser-cookie route; header bearer credentials alone are not accepted.
    status, _, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/auth/user/logout",
        headers=auth_headers(session, csrf=True),
        config=config,
    )
    expect(status == 401, f"expected 401 for header-only browser logout got {status}")

    # A stolen session id plus CSRF must not revoke unless the session token authenticates first.
    status, _, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/auth/user/logout",
        headers=browser_auth_headers(session, csrf=True, token="wrong-token"),
        config=config,
    )
    expect(status == 401, f"expected 401 for wrong logout token got {status}")
    status, _, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/user/dashboard",
        headers=auth_headers(session),
        config=config,
    )
    expect(status == 200, f"session should remain active after wrong logout token got {status}")

    # Logout with CSRF
    status, payload, headers = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/auth/user/logout",
        headers=browser_auth_headers(session, csrf=True),
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
        body=json.dumps({"channel": "web", "email": "checkout@example.test", "plan_id": "sovereign"}),
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
        "ARCLINK_SOVEREIGN_PRICE_ID": "price_live_resolve",
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
        body=json.dumps({"channel": "web", "email": "live-resolve@example.test", "plan_id": "sovereign"}),
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
    expect(calls[0]["customer_email"] == "live-resolve@example.test", str(calls))
    print("PASS test_public_onboarding_checkout_resolves_live_stripe_from_config")


def test_public_onboarding_checkout_maps_package_price_ids() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_price_map_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_price_map_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "example.test",
        "STRIPE_SECRET_KEY": "sk_test_configured_secret",
        "ARCLINK_FOUNDERS_PRICE_ID": "price_founders_live",
        "ARCLINK_SOVEREIGN_PRICE_ID": "price_sovereign_live",
        "ARCLINK_SCALE_PRICE_ID": "price_scale_live",
    })
    calls: list[dict] = []

    class RecordingStripe:
        def create_checkout_session(self, **kwargs):
            calls.append(kwargs)
            return {"id": f"cs_{len(calls)}", "url": f"https://checkout.stripe.com/c/cs_{len(calls)}"}

    hosted.resolve_stripe_client = lambda env: RecordingStripe()

    expected = {
        "founders": "price_founders_live",
        "sovereign": "price_sovereign_live",
        "scale": "price_scale_live",
    }
    for plan_id, price_id in expected.items():
        status, payload, _ = hosted.route_arclink_hosted_api(
            conn,
            method="POST",
            path="/api/v1/onboarding/start",
            headers={},
            body=json.dumps({"channel": "web", "channel_identity": f"web:{plan_id}", "plan_id": plan_id}),
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
        expect(calls[-1]["price_id"] == price_id, str(calls[-1]))
    print("PASS test_public_onboarding_checkout_maps_package_price_ids")


def test_public_bot_checkout_button_redirects_to_stripe() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_public_bot_checkout_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_public_bot_checkout_test")
    bots = load_module("arclink_public_bots.py", "arclink_public_bots_hosted_checkout_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_hosted_public_bot_checkout_test")
    conn = memory_db(control)
    stripe = adapters.FakeStripeClient()
    config = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "example.test",
        "ARCLINK_FOUNDERS_PRICE_ID": "price_founders_live",
        "ARCLINK_SCALE_PRICE_ID": "price_scale_live",
    })

    bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:direct-checkout",
        text="/start",
        display_name_hint="Direct Buyer",
    )
    bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:direct-checkout",
        text="/agent-identity Atlas, the right hand",
        base_domain="example.test",
    )
    package = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:direct-checkout",
        text="/packages",
        base_domain="example.test",
    )
    expect([button.label for button in package.buttons] == ["Founders $149/mo", "Scale $275/mo"], str(package.buttons))
    expect(all(button.url for button in package.buttons), str(package.buttons))

    scale_url = package.buttons[1].url
    parsed = urlparse(scale_url)
    query = {key: values[0] for key, values in parse_qs(parsed.query).items() if values}
    status, payload, headers = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path=parsed.path,
        headers={},
        query=query,
        config=config,
        stripe_client=stripe,
    )
    expect(status == 303, f"expected redirect got {status}: {payload}")
    location = dict(headers).get("Location", "")
    expect(location.startswith("https://stripe.test/checkout/"), str(headers))
    checkout_session = stripe.checkout_sessions[location.rsplit("/", 1)[1]]
    expect(checkout_session["price_id"] == "price_scale_live", str(checkout_session))
    expect(checkout_session["success_url"] == "https://example.test/checkout/success?session=" + package.session_id, str(checkout_session))

    row = conn.execute(
        "SELECT user_id, selected_plan_id, selected_model_id, checkout_state FROM arclink_onboarding_sessions WHERE session_id = ?",
        (package.session_id,),
    ).fetchone()
    expect(row["selected_plan_id"] == "scale", str(dict(row)))
    expect(row["selected_model_id"], str(dict(row)))
    expect(row["checkout_state"] == "open", str(dict(row)))
    deployments = conn.execute(
        "SELECT COUNT(*) AS n FROM arclink_deployments WHERE user_id = ?",
        (row["user_id"],),
    ).fetchone()
    expect(deployments["n"] == 3, str(dict(deployments)))

    status2, payload2, headers2 = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path=parsed.path,
        headers={},
        query=query,
        config=config,
        stripe_client=stripe,
    )
    expect(status2 == 303, f"expected replay redirect got {status2}: {payload2}")
    expect(dict(headers2).get("Location") == location, str(headers2))
    expect(len(stripe.checkout_sessions) == 1, str(stripe.checkout_sessions))
    print("PASS test_public_bot_checkout_button_redirects_to_stripe")


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
    api.upsert_arclink_admin(
        conn,
        admin_id="admin_logout",
        email="logout@example.test",
        role="owner",
        password="admin-test-password",
    )

    # Login
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/auth/admin/login",
        headers={}, body=json.dumps({"email": "logout@example.test", "password": "admin-test-password"}), config=config,
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
        headers=browser_auth_headers(session, kind="admin"),
        config=config,
    )
    expect(status == 401, f"expected 401 without CSRF got {status}")

    status, _, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/auth/admin/logout",
        headers=auth_headers(session, csrf=True),
        config=config,
    )
    expect(status == 401, f"expected 401 for header-only browser logout got {status}")

    # Logout with CSRF
    status, payload, headers = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/auth/admin/logout",
        headers=browser_auth_headers(session, kind="admin", csrf=True),
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


def test_stripe_webhook_queues_paid_ping_for_telegram_user() -> None:
    """Raven speaks before silence: a Telegram user who pays must receive a
    queued outbound 'payment cleared' message back to their chat.
    """
    import time as _time
    control = load_module("arclink_control.py", "arclink_control_hosted_paid_ping_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_paid_ping_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_hosted_paid_ping_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_paid_ping_test")
    conn = memory_db(control)
    secret = "whsec_test_paidping"
    config = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "example.test",
        "STRIPE_WEBHOOK_SECRET": secret,
    })
    # Telegram-originated session: chat_id "987654321" is the channel_identity
    session = onboarding.create_or_resume_arclink_onboarding_session(
        conn,
        channel="telegram",
        channel_identity="987654321",
        session_id="onb_paidping",
        display_name_hint="Hera",
        selected_plan_id="sovereign",
        selected_model_id="model-test",
    )
    prepared = onboarding.prepare_arclink_onboarding_deployment(
        conn,
        session_id=session["session_id"],
        base_domain="example.test",
        prefix="paidping-1a",
    )
    event_payload = json.dumps({
        "id": "evt_paidping_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_paidping_1",
                "customer": "cus_paidping_1",
                "subscription": "sub_paidping_1",
                "client_reference_id": prepared["user_id"],
                "metadata": {"arclink_onboarding_session_id": session["session_id"]},
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

    row = conn.execute(
        """
        SELECT target_kind, target_id, channel_kind, message
        FROM notification_outbox
        WHERE target_kind = 'public-bot-user'
          AND channel_kind = 'telegram'
          AND target_id = '987654321'
        """
    ).fetchone()
    expect(row is not None, "expected a paid-ping queued for the Telegram user")
    expect(row["target_kind"] == "public-bot-user", str(row["target_kind"]))
    expect("payment cleared" in str(row["message"]).lower(), str(row["message"]))
    expect("Captain Hera" in str(row["message"]), str(row["message"]))

    # Replay must NOT re-queue (entitlement transition is idempotent)
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/webhooks/stripe",
        headers={"Stripe-Signature": signature},
        body=event_payload, config=config,
    )
    count = conn.execute(
        "SELECT COUNT(*) AS c FROM notification_outbox WHERE target_kind = 'public-bot-user' AND target_id = '987654321'"
    ).fetchone()["c"]
    expect(count == 1, f"expected exactly 1 paid-ping after replay, got {count}")
    print("PASS test_stripe_webhook_queues_paid_ping_for_telegram_user")


def test_stripe_webhook_queues_paid_ping_for_discord_user() -> None:
    """Discord users get the same paid-ping surface; notification delivery opens
    the DM later, but the webhook must enqueue the platform-specific row.
    """
    import time as _time
    control = load_module("arclink_control.py", "arclink_control_hosted_paid_ping_discord_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_paid_ping_discord_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_hosted_paid_ping_discord_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_paid_ping_discord_test")
    conn = memory_db(control)
    secret = "whsec_test_paidping_discord"
    config = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "example.test",
        "STRIPE_WEBHOOK_SECRET": secret,
    })
    session = onboarding.create_or_resume_arclink_onboarding_session(
        conn,
        channel="discord",
        channel_identity="discord:555777",
        session_id="onb_paidping_discord",
        display_name_hint="Raven Buyer",
        selected_plan_id="sovereign",
        selected_model_id="model-test",
    )
    prepared = onboarding.prepare_arclink_onboarding_deployment(
        conn,
        session_id=session["session_id"],
        base_domain="example.test",
        prefix="paidping-dc",
    )
    event_payload = json.dumps({
        "id": "evt_paidping_discord_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_paidping_discord_1",
                "customer": "cus_paidping_discord_1",
                "subscription": "sub_paidping_discord_1",
                "client_reference_id": prepared["user_id"],
                "metadata": {"arclink_onboarding_session_id": session["session_id"]},
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
    row = conn.execute(
        """
        SELECT target_kind, target_id, channel_kind, message, extra_json
        FROM notification_outbox
        WHERE target_kind = 'public-bot-user'
          AND channel_kind = 'discord'
          AND target_id = '555777'
        """
    ).fetchone()
    expect(row is not None, "expected a paid-ping queued for the Discord user")
    expect("payment cleared" in str(row["message"]).lower(), str(row["message"]))
    extra = json.loads(row["extra_json"])
    expect("discord_components" in extra, str(extra))
    print("PASS test_stripe_webhook_queues_paid_ping_for_discord_user")


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


def test_stripe_webhook_received_duplicate_is_acknowledged_as_replay() -> None:
    import time as _time
    control = load_module("arclink_control.py", "arclink_control_hosted_whreceived_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_whreceived_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_hosted_whreceived_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_whreceived_test")
    conn = memory_db(control)
    secret = "whsec_test_received"
    config = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "example.test",
        "STRIPE_WEBHOOK_SECRET": secret,
    })
    prepared = seed_paid_deployment(control, onboarding, conn)
    control.set_arclink_user_entitlement(conn, user_id=prepared["user_id"], entitlement_state="none")
    event_payload = json.dumps({
        "id": "evt_received_duplicate",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_received_duplicate",
                "customer": "cus_received_duplicate",
                "subscription": "sub_received_duplicate",
                "client_reference_id": prepared["user_id"],
                "metadata": {"arclink_onboarding_session_id": "onb_hosted"},
            }
        },
    })
    conn.execute(
        """
        INSERT INTO arclink_webhook_events (provider, event_id, event_type, received_at, status, payload_json)
        VALUES ('stripe', 'evt_received_duplicate', 'checkout.session.completed', '2026-05-11T00:00:00+00:00', 'received', ?)
        """,
        (event_payload,),
    )
    conn.commit()
    signature = adapters.sign_stripe_webhook(event_payload, secret, timestamp=int(_time.time()))

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/webhooks/stripe",
        headers={"Stripe-Signature": signature},
        body=event_payload,
        config=config,
    )
    expect(status == 200, f"received duplicate expected 200 got {status}: {payload}")
    expect(payload["replayed"] is True, str(payload))
    user = conn.execute("SELECT entitlement_state FROM arclink_users WHERE user_id = ?", (prepared["user_id"],)).fetchone()
    webhook = conn.execute("SELECT status FROM arclink_webhook_events WHERE event_id = 'evt_received_duplicate'").fetchone()
    expect(user["entitlement_state"] == "none", str(dict(user)))
    expect(webhook["status"] == "received", str(dict(webhook)))
    print("PASS test_stripe_webhook_received_duplicate_is_acknowledged_as_replay")


def test_telegram_webhook_route() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_tg_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_tg_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "example.test",
        "TELEGRAM_WEBHOOK_SECRET": "tg_secret",
    })

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
        headers={"X-Telegram-Bot-Api-Secret-Token": "tg_secret"}, body=update, config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect(payload.get("ok") is True, str(payload))
    expect(payload.get("action") != "ignored", f"expected handled action: {payload}")
    expect(payload.get("sent") is False, f"no live Telegram transport should be used in this test: {payload}")

    # Non-text update (no message) should be ignored
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/webhooks/telegram",
        headers={"X-Telegram-Bot-Api-Secret-Token": "tg_secret"}, body=json.dumps({"update_id": 2}), config=config,
    )
    expect(status == 200, f"expected 200 got {status}")
    expect(payload.get("action") == "ignored", str(payload))

    print("PASS test_telegram_webhook_route")


def test_telegram_webhook_secret_boundary() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_tg_secret_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_tg_secret_test")
    conn = memory_db(control)
    update = json.dumps({"update_id": 1})

    missing_config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/webhooks/telegram",
        headers={"X-Telegram-Bot-Api-Secret-Token": "tg_secret"},
        body=update,
        config=missing_config,
    )
    expect(status == 503, f"missing configured secret should fail closed got {status}: {payload}")
    expect(payload.get("error") == "telegram_webhook_secret_unset", str(payload))

    configured = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "example.test",
        "TELEGRAM_WEBHOOK_SECRET": "tg_secret",
    })
    for headers in ({}, {"X-Telegram-Bot-Api-Secret-Token": "wrong"}):
        status, payload, _ = hosted.route_arclink_hosted_api(
            conn,
            method="POST",
            path="/api/v1/webhooks/telegram",
            headers=headers,
            body=update,
            config=configured,
        )
        expect(status == 401, f"bad Telegram webhook secret should reject got {status}: {payload}")

    print("PASS test_telegram_webhook_secret_boundary")


def test_telegram_webhook_sends_reply_when_transport_is_available() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_tg_send_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_tg_send_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_hosted_tg_send_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(
        env={
            "ARCLINK_BASE_DOMAIN": "example.test",
            "ARCLINK_PUBLIC_AGENT_LIVE_TRIGGER_RUNNER": "local",
            "TELEGRAM_WEBHOOK_SECRET": "tg_secret",
        }
    )
    telegram_headers = {"X-Telegram-Bot-Api-Secret-Token": "tg_secret"}

    class CaptureTransport:
        def __init__(self) -> None:
            self.sent_messages = []
            self.message_reactions = []
            self.chat_actions = []

        def send_message(self, chat_id: str, text: str, reply_markup=None):
            self.sent_messages.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
            return {"message_id": len(self.sent_messages)}

        def set_message_reaction(self, chat_id: str, message_id: str, emoji: str):
            self.message_reactions.append({"chat_id": chat_id, "message_id": message_id, "emoji": emoji})
            return {"ok": True}

        def send_chat_action(self, chat_id: str, action: str = "typing"):
            self.chat_actions.append({"chat_id": chat_id, "action": action})
            return {"ok": True}

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
        headers=telegram_headers,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect(payload.get("sent") is True, str(payload))
    expect(len(transport.sent_messages) == 1, str(transport.sent_messages))
    expect(transport.sent_messages[0]["chat_id"] == "12345", str(transport.sent_messages))
    expect("Comms are open" in transport.sent_messages[0]["text"], transport.sent_messages[0]["text"])

    class FailingTransport:
        def send_message(self, chat_id: str, text: str, reply_markup=None):
            raise RuntimeError("telegram api unavailable")

    status, payload, _ = hosted._handle_telegram_webhook(
        conn,
        update,
        "req_tg_send_failure",
        config,
        adapters.FakeStripeClient(),
        telegram_transport=FailingTransport(),
        headers=telegram_headers,
    )
    expect(status == 200, f"reply send failure should still ack webhook: {status} {payload}")
    expect(payload.get("sent") is False, str(payload))

    def queued_agent_turn(*args, **kwargs):
        del args, kwargs
        return {
            "chat_id": "12345",
            "text": "",
            "reply_markup": None,
            "action": "agent_message_queued",
            "channel_identity": "tg:67890",
            "telegram_message_id": "1",
            "callback_query_id": "",
        }

    live_trigger_calls: list[dict[str, str]] = []

    def fake_live_trigger(cfg, *, channel_kind="", target_id="", limit=0, verbose=False):
        del cfg, limit, verbose
        live_trigger_calls.append({"channel_kind": channel_kind, "target_id": target_id})
        return {"processed": 1, "delivered": 1, "errors": 0}

    class ImmediateExecutor:
        def submit(self, fn):
            fut = Future()
            try:
                fn()
            except BaseException as exc:  # noqa: BLE001
                fut.set_exception(exc)
            else:
                fut.set_result(None)
            return fut

    class OpenGate:
        def __init__(self):
            self.released = False

        def acquire(self, *, blocking=False):
            expect(blocking is False, "live trigger should never block webhook ingress")
            return True

        def release(self):
            self.released = True

    live_gate = OpenGate()

    def fake_pool(_config):
        return ImmediateExecutor(), live_gate

    old_handle = hosted.handle_telegram_update
    old_trigger = hosted.run_public_agent_turns_once
    old_pool = hosted._public_agent_live_trigger_pool
    old_fast_pool = hosted._telegram_fast_ack_pool
    hosted.handle_telegram_update = queued_agent_turn
    hosted.run_public_agent_turns_once = fake_live_trigger
    hosted._public_agent_live_trigger_pool = fake_pool
    hosted._telegram_fast_ack_pool = fake_pool
    quiet_transport = CaptureTransport()
    try:
        status, payload, _ = hosted._handle_telegram_webhook(
            conn,
            update,
            "req_tg_send_empty",
            config,
            adapters.FakeStripeClient(),
            telegram_transport=quiet_transport,
            headers=telegram_headers,
        )
    finally:
        hosted.handle_telegram_update = old_handle
        hosted.run_public_agent_turns_once = old_trigger
        hosted._public_agent_live_trigger_pool = old_pool
        hosted._telegram_fast_ack_pool = old_fast_pool
    expect(status == 200, f"empty agent handoff should still ack webhook: {status} {payload}")
    expect(payload.get("sent") is False, str(payload))
    expect(payload.get("fast_acknowledged") is True, str(payload))
    expect(payload.get("live_triggered") is True, str(payload))
    expect(live_gate.released is True, "live trigger slot should be released after the worker completes")
    expect(quiet_transport.sent_messages == [], str(quiet_transport.sent_messages))
    expect(quiet_transport.message_reactions == [{"chat_id": "12345", "message_id": "1", "emoji": "👀"}], str(quiet_transport.message_reactions))
    expect(quiet_transport.chat_actions == [{"chat_id": "12345", "action": "typing"}], str(quiet_transport.chat_actions))
    expect(live_trigger_calls == [{"channel_kind": "telegram", "target_id": "tg:67890"}], str(live_trigger_calls))
    print("PASS test_telegram_webhook_sends_reply_when_transport_is_available")


def test_public_agent_live_trigger_backpressure_defers_to_delivery_worker() -> None:
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_live_trigger_backpressure_test")
    config = hosted.HostedApiConfig(
        env={
            "ARCLINK_BASE_DOMAIN": "example.test",
            "ARCLINK_PUBLIC_AGENT_LIVE_TRIGGER_RUNNER": "local",
            "ARCLINK_PUBLIC_AGENT_LIVE_TRIGGER_MAX_PENDING": "1",
        }
    )

    class UnusedExecutor:
        def submit(self, fn):
            raise AssertionError("saturated live trigger must not submit work")

    class ClosedGate:
        def acquire(self, *, blocking=False):
            expect(blocking is False, "live trigger should never block webhook ingress")
            return False

        def release(self):
            raise AssertionError("closed gate should not be released")

    old_pool = hosted._public_agent_live_trigger_pool
    hosted._public_agent_live_trigger_pool = lambda _config: (UnusedExecutor(), ClosedGate())
    try:
        triggered = hosted._kick_public_agent_live_trigger(
            config=config,
            channel_kind="telegram",
            target_id="tg:67890",
            request_id="req_saturated",
        )
    finally:
        hosted._public_agent_live_trigger_pool = old_pool
    expect(triggered is False, "saturated live trigger should leave the queued row for notification-delivery")
    print("PASS test_public_agent_live_trigger_backpressure_defers_to_delivery_worker")


def test_telegram_fast_ack_backpressure_is_cosmetic() -> None:
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_fast_ack_backpressure_test")
    config = hosted.HostedApiConfig(
        env={
            "ARCLINK_BASE_DOMAIN": "example.test",
            "ARCLINK_TELEGRAM_FAST_ACK_MAX_PENDING": "1",
        }
    )
    telegram_config = hosted.TelegramConfig(
        bot_token="test-token",
        bot_username="raven_test_bot",
        webhook_url="",
        webhook_secret="secret",
    )

    class UnusedExecutor:
        def submit(self, fn):
            raise AssertionError("saturated fast ack must not submit cosmetic work")

    class ClosedGate:
        def acquire(self, *, blocking=False):
            expect(blocking is False, "Telegram fast ack should never block webhook ingress")
            return False

        def release(self):
            raise AssertionError("closed fast-ack gate should not be released")

    old_pool = hosted._telegram_fast_ack_pool
    hosted._telegram_fast_ack_pool = lambda _config: (UnusedExecutor(), ClosedGate())
    try:
        acknowledged = hosted._kick_telegram_fast_agent_ack(
            config=config,
            telegram_config=telegram_config,
            chat_id="12345",
            message_id="10",
            request_id="req_fast_ack_saturated",
        )
    finally:
        hosted._telegram_fast_ack_pool = old_pool
    expect(acknowledged is False, "saturated cosmetic ack should be skipped, not queued behind ingress")
    print("PASS test_telegram_fast_ack_backpressure_is_cosmetic")


def test_public_agent_live_trigger_auto_mode_defers_without_docker_socket() -> None:
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_live_trigger_socket_boundary_test")
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})

    old_exists = hosted.os.path.exists
    old_pool = hosted._public_agent_live_trigger_pool
    hosted.os.path.exists = lambda path: False if path == "/var/run/docker.sock" else old_exists(path)
    hosted._public_agent_live_trigger_pool = lambda _config: (_ for _ in ()).throw(
        AssertionError("API ingress without Docker socket must not submit delivery work")
    )
    try:
        triggered = hosted._kick_public_agent_live_trigger(
            config=config,
            channel_kind="telegram",
            target_id="tg:67890",
            request_id="req_no_socket",
        )
    finally:
        hosted.os.path.exists = old_exists
        hosted._public_agent_live_trigger_pool = old_pool
    expect(triggered is False, "Dockerized API ingress should leave delivery to notification-delivery")
    print("PASS test_public_agent_live_trigger_auto_mode_defers_without_docker_socket")


def test_telegram_webhook_acknowledges_button_callbacks() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_tg_callback_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_tg_callback_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_hosted_tg_callback_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "example.test",
        "TELEGRAM_WEBHOOK_SECRET": "tg_secret",
    })

    class CaptureTransport:
        def __init__(self) -> None:
            self.sent_messages = []
            self.answered_callbacks = []

        def send_message(self, chat_id: str, text: str, reply_markup=None):
            self.sent_messages.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
            return {"message_id": len(self.sent_messages)}

        def answer_callback_query(self, callback_query_id: str, text: str = ""):
            self.answered_callbacks.append({"callback_query_id": callback_query_id, "text": text})
            return {"ok": True}

    transport = CaptureTransport()
    update = {
        "update_id": 2,
        "callback_query": {
            "id": "cb_start",
            "from": {"id": 67890},
            "message": {"message_id": 10, "chat": {"id": 12345}},
            "data": "arclink:/start",
        },
    }
    status, payload, _ = hosted._handle_telegram_webhook(
        conn,
        update,
        "req_tg_callback",
        config,
        adapters.FakeStripeClient(),
        telegram_transport=transport,
        headers={"X-Telegram-Bot-Api-Secret-Token": "tg_secret"},
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect(payload.get("sent") is True, str(payload))
    expect(payload.get("callback_acknowledged") is True, str(payload))
    expect(transport.answered_callbacks == [{"callback_query_id": "cb_start", "text": ""}], str(transport.answered_callbacks))
    expect(transport.sent_messages and "Raven here" in transport.sent_messages[0]["text"], str(transport.sent_messages))
    print("PASS test_telegram_webhook_acknowledges_button_callbacks")


def test_telegram_credential_ack_edits_original_secret_message() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_tg_credential_ack_edit_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_tg_credential_ack_edit_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_hosted_tg_credential_ack_edit_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "example.test",
        "TELEGRAM_WEBHOOK_SECRET": "tg_secret",
    })

    class CaptureTransport:
        def __init__(self) -> None:
            self.sent_messages = []
            self.edited_messages = []
            self.answered_callbacks = []

        def send_message(self, chat_id: str, text: str, reply_markup=None):
            self.sent_messages.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
            return {"message_id": len(self.sent_messages)}

        def edit_message_text(self, chat_id: str, message_id: int, text: str, reply_markup=None):
            self.edited_messages.append(
                {"chat_id": chat_id, "message_id": message_id, "text": text, "reply_markup": reply_markup}
            )
            return {"ok": True}

        def answer_callback_query(self, callback_query_id: str, text: str = ""):
            self.answered_callbacks.append({"callback_query_id": callback_query_id, "text": text})
            return {"ok": True}

    def credential_ack_result(*args, **kwargs):
        return {
            "chat_id": "12345",
            "text": "Locked in. I removed that dashboard credential handoff from future ArcLink responses.",
            "reply_markup": {"inline_keyboard": [[{"text": "Wire Notion", "callback_data": "arclink:/connect_notion"}]]},
            "session_id": "onb_credential_ack",
            "action": "credentials_stored",
            "channel_identity": "tg:67890",
            "callback_query_id": "cb_stored",
            "callback_message_id": "10",
        }

    old_handle = hosted.handle_telegram_update
    hosted.handle_telegram_update = credential_ack_result
    transport = CaptureTransport()
    try:
        status, payload, _ = hosted._handle_telegram_webhook(
            conn,
            {
                "update_id": 3,
                "callback_query": {
                    "id": "cb_stored",
                    "from": {"id": 67890},
                    "message": {"message_id": 10, "chat": {"id": 12345}},
                    "data": "arclink:/credentials-stored",
                },
            },
            "req_tg_credential_ack_edit",
            config,
            adapters.FakeStripeClient(),
            telegram_transport=transport,
            headers={"X-Telegram-Bot-Api-Secret-Token": "tg_secret"},
        )
    finally:
        hosted.handle_telegram_update = old_handle

    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect(payload.get("callback_acknowledged") is True, str(payload))
    expect(payload.get("edited") is True, str(payload))
    expect(payload.get("sent") is False, str(payload))
    expect(transport.sent_messages == [], str(transport.sent_messages))
    expect(len(transport.edited_messages) == 1, str(transport.edited_messages))
    edited = transport.edited_messages[0]
    expect(edited["message_id"] == 10, str(edited))
    expect("Password:" not in edited["text"], edited["text"])
    expect("removed" in edited["text"].lower(), edited["text"])
    print("PASS test_telegram_credential_ack_edits_original_secret_message")


def test_discord_webhook_route() -> None:
    import time as _time
    control = load_module("arclink_control.py", "arclink_control_hosted_dc_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_dc_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    timestamp = str(int(_time.time()))

    # Ping interaction (with test_public_key sentinel)
    import os
    os.environ["DISCORD_PUBLIC_KEY"] = "test_public_key"
    os.environ["DISCORD_BOT_TOKEN"] = "fake"
    os.environ["DISCORD_APP_ID"] = "app123"
    try:
        ping_body = json.dumps({"id": "int_ping", "type": 1})
        status, payload, _ = hosted.route_arclink_hosted_api(
            conn, method="POST", path="/api/v1/webhooks/discord",
            headers={"x-signature-ed25519": "abc", "x-signature-timestamp": timestamp},
            body=ping_body, config=config,
        )
        expect(status == 200, f"expected 200 got {status}: {payload}")
        expect(payload.get("type") == 1, f"expected PONG: {payload}")

        # Slash command
        interaction = json.dumps({
            "id": "int_slash",
            "type": 2,
            "channel_id": "chan1",
            "member": {"user": {"id": "user1"}},
            "data": {"name": "arclink", "options": [{"name": "message", "value": "hello"}]},
        })
        status, payload, _ = hosted.route_arclink_hosted_api(
            conn, method="POST", path="/api/v1/webhooks/discord",
            headers={"x-signature-ed25519": "abc", "x-signature-timestamp": timestamp},
            body=interaction, config=config,
        )
        expect(status == 200, f"expected 200 got {status}: {payload}")
        expect(payload.get("type") == 4, f"expected CHANNEL_MESSAGE: {payload}")
        expect("content" in payload.get("data", {}), str(payload))
    finally:
        os.environ.pop("DISCORD_PUBLIC_KEY", None)
        os.environ.pop("DISCORD_BOT_TOKEN", None)
        os.environ.pop("DISCORD_APP_ID", None)

    # No public key configured → fail closed so Discord retries and operators notice.
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/webhooks/discord",
        headers={}, body=json.dumps({"type": 1}), config=config,
    )
    expect(status == 503, f"expected 503 without config got {status}")
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
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test", "CHUTES_API_KEY": "raw_operator_secret_value"})
    prepared = seed_paid_deployment(control, onboarding, conn)
    conn.execute(
        "UPDATE arclink_deployments SET metadata_json = ? WHERE deployment_id = ?",
        (
            json.dumps(
                {
                    "selected_model_id": "model-hosted",
                    "chutes": {
                        "secret_ref": f"secret://arclink/chutes/{prepared['deployment_id']}",
                        "monthly_budget_cents": 10000,
                        "used_cents": 8500,
                        "warning_threshold_percent": 80,
                    },
                }
            ),
            prepared["deployment_id"],
        ),
    )
    conn.commit()
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
    provider_text = json.dumps(payload, sort_keys=True)
    expect("raw_operator_secret_value" not in provider_text, provider_text)
    expect(f"secret://arclink/chutes/{prepared['deployment_id']}" not in provider_text, provider_text)
    model = payload["deployment_models"][0]
    expect(model["credential_state"] == "budget_warning", str(model))
    expect(model["allow_inference"] is True, str(model))
    expect(model["chutes"]["budget"]["status"] == "warning", str(model))
    expect(model["provider_detail"]["budget"]["status"] == "warning", str(model))
    continuation = model["provider_detail"]["threshold_continuation"]
    expect(continuation["status"] == "policy_question", str(continuation))
    expect(continuation["raven_notifications"] == "disabled_until_warning_cadence_policy", str(continuation))
    expect(continuation["provider_fallback"] == "policy_question", str(continuation))
    expect(continuation["overage_refill"] == "policy_question", str(continuation))
    lifecycle = model["chutes"]["credential_lifecycle"]
    expect(lifecycle["canonical_mode"] == "scoped_secret_ref_per_user_or_deployment", str(lifecycle))
    expect(lifecycle["current_mode"] == "per_deployment_secret_ref", str(lifecycle))
    expect(lifecycle["posture"] == "active_scoped_secret_ref", str(lifecycle))
    expect(payload["provider_boundary"]["credential_lifecycle"]["live_key_creation"] == "proof_gated", str(payload["provider_boundary"]))
    expect(payload["provider_boundary"]["threshold_continuation"]["status"] == "policy_question", str(payload["provider_boundary"]))
    settings = payload["provider_settings"]
    expect(settings["self_service_provider_add"] == "policy_question", str(settings))
    expect(settings["dashboard_mutation"] == "disabled", str(settings))
    expect(settings["secret_input_policy"] == "dashboard_never_collects_raw_provider_tokens", str(settings))
    expect("raw provider" in settings["guidance"].lower() or "provider state" in settings["guidance"].lower(), str(settings))

    print("PASS test_user_provider_state_route")


def test_provider_state_suspends_chutes_on_past_due_billing() -> None:
    control = load_module("arclink_control.py", "arclink_control_provider_billing_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_provider_billing_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_provider_billing_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_provider_billing_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    prepared = seed_paid_deployment(control, onboarding, conn)
    conn.execute(
        "UPDATE arclink_deployments SET metadata_json = ? WHERE deployment_id = ?",
        (
            json.dumps({
                "chutes": {
                    "secret_ref": f"secret://arclink/chutes/{prepared['deployment_id']}",
                    "monthly_budget_cents": 10000,
                    "used_cents": 1000,
                }
            }),
            prepared["deployment_id"],
        ),
    )
    control.set_arclink_user_entitlement(conn, user_id=prepared["user_id"], entitlement_state="past_due")
    session = api.create_arclink_user_session(conn, user_id=prepared["user_id"], session_id="usess_provider_billing")

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/user/provider-state",
        headers=auth_headers(session), config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    item = payload["deployment_models"][0]
    expect(item["credential_state"] == "billing_suspended", str(item))
    expect(item["allow_inference"] is False, str(item))
    lifecycle = item["chutes"]["billing_lifecycle"]
    expect(lifecycle["payment_state"] == "past_due", str(lifecycle))
    expect(lifecycle["provider_access"] == "suspended", str(lifecycle))
    expect(lifecycle["warning_cadence"] == "immediate_notice_then_daily_reminders", str(lifecycle))
    expect(lifecycle["grace_period"] == "provider_suspended_immediately", str(lifecycle))
    expect(lifecycle["data_retention"] == "account_data_removed_warning_day_7", str(lifecycle))
    expect(lifecycle["purge_policy"] == "audited_purge_queue_day_14", str(lifecycle))
    expect(lifecycle["day_7_action"] == "warn_account_and_data_removal", str(lifecycle))
    expect(lifecycle["day_14_action"] == "queue_audited_purge", str(lifecycle))

    status, billing, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/user/billing",
        headers=auth_headers(session), config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {billing}")
    expect(billing["renewal_lifecycle"]["provider_access"] == "suspended", str(billing))
    expect(billing["renewal_lifecycle"]["warning_cadence"] == "immediate_notice_then_daily_reminders", str(billing))
    expect(billing["renewal_lifecycle"]["purge_policy"] == "audited_purge_queue_day_14", str(billing))
    print("PASS test_provider_state_suspends_chutes_on_past_due_billing")


def test_admin_provider_state_route() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_aprov_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_aprov_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_aprov_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test", "CHUTES_API_KEY": "raw_operator_secret_value"})
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_aprov_onboarding_test")
    prepared = seed_paid_deployment(control, onboarding, conn, session_id="onb_admin_provider")
    conn.execute(
        "UPDATE arclink_deployments SET metadata_json = ? WHERE deployment_id = ?",
        (
            json.dumps(
                {
                    "selected_model_id": "model-hosted",
                    "chutes": {
                        "secret_ref": f"secret://arclink/chutes/{prepared['deployment_id']}",
                        "key_id": "key_admin_visible",
                        "monthly_budget_cents": 10000,
                        "used_cents": 10000,
                    },
                }
            ),
            prepared["deployment_id"],
        ),
    )
    conn.commit()
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
    provider_text = json.dumps(payload, sort_keys=True)
    expect("raw_operator_secret_value" not in provider_text, provider_text)
    expect(f"secret://arclink/chutes/{prepared['deployment_id']}" not in provider_text, provider_text)
    expect(payload["chutes_summary"]["blocked_count"] == 1, str(payload))
    model = payload["deployment_models"][0]
    expect(model["credential_state"] == "budget_exhausted", str(model))
    expect(model["allow_inference"] is False, str(model))
    expect(model["chutes"]["key_id"] == "key_admin_visible", str(model))
    lifecycle = model["chutes"]["credential_lifecycle"]
    expect(lifecycle["current_mode"] == "per_deployment_secret_ref", str(lifecycle))
    expect(lifecycle["posture"] == "suspended_or_exhausted", str(lifecycle))

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


def test_wsgi_adapter_can_use_per_request_connections() -> None:
    from io import BytesIO

    control = load_module("arclink_control.py", "arclink_control_hosted_wsgi_per_request_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_wsgi_per_request_test")
    opened: list[object] = []
    closed: list[object] = []

    class TrackedConnection:
        def __init__(self) -> None:
            self.conn = memory_db(control)
            opened.append(self)

        def execute(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            return self.conn.execute(*args, **kwargs)

        def commit(self) -> None:
            self.conn.commit()

        def rollback(self) -> None:
            self.conn.rollback()

        def close(self) -> None:
            closed.append(self)
            self.conn.close()

        @property
        def in_transaction(self) -> bool:
            return self.conn.in_transaction

    def connect(_config):  # type: ignore[no-untyped-def]
        return TrackedConnection()

    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    app = hosted.make_arclink_hosted_api_wsgi(None, config=config, connect=connect)
    captured: list[tuple[str, list]] = []

    def start_response(status: str, headers: list) -> None:
        captured.append((status, headers))

    result = app(
        {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/api/v1/health",
            "QUERY_STRING": "",
            "CONTENT_LENGTH": "0",
            "REMOTE_ADDR": "127.0.0.1",
            "wsgi.input": BytesIO(b""),
        },
        start_response,
    )
    expect(captured and captured[0][0] == "200 OK", f"expected health 200 got {captured}: {result}")
    expect(len(opened) == 1 and opened == closed, f"per-request connection lifecycle mismatch opened={opened} closed={closed}")
    print("PASS test_wsgi_adapter_can_use_per_request_connections")


def test_request_body_limits_and_json_errors() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_body_boundary_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_body_boundary_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "example.test",
        "ARCLINK_CORS_ORIGIN": "https://app.arclink.online",
        "ARCLINK_HOSTED_API_MAX_BODY_BYTES": "32",
    })

    status, payload, headers = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/onboarding/start",
        headers={},
        body=json.dumps({"channel": "web", "email": "oversized@example.test", "padding": "x" * 80}),
        config=config,
    )
    expect(status == 413, f"expected 413 got {status}: {payload}")
    expect(payload.get("error") == "body_too_large", str(payload))
    header_dict = {k.lower(): v for k, v in headers}
    expect(header_dict.get("access-control-allow-origin") == "https://app.arclink.online", str(header_dict))

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/onboarding/start",
        headers={},
        body="{not-json",
        config=hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"}),
    )
    expect(status == 400, f"expected malformed JSON 400 got {status}: {payload}")
    expect(payload.get("error") == "invalid_json", str(payload))

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/onboarding/start",
        headers={},
        body=json.dumps(["not", "an", "object"]),
        config=hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"}),
    )
    expect(status == 400, f"expected non-object JSON 400 got {status}: {payload}")
    expect(payload.get("error") == "invalid_json", str(payload))

    print("PASS test_request_body_limits_and_json_errors")


def test_wsgi_body_limit_rejects_before_read() -> None:
    from io import BytesIO

    class FailingInput(BytesIO):
        def read(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("WSGI body was read before size rejection")

    control = load_module("arclink_control.py", "arclink_control_hosted_wsgi_body_limit_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_wsgi_body_limit_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "example.test",
        "ARCLINK_CORS_ORIGIN": "https://app.arclink.online",
        "ARCLINK_HOSTED_API_MAX_BODY_BYTES": "8",
    })
    app = hosted.make_arclink_hosted_api_wsgi(conn, config=config)

    captured: list[tuple[str, list]] = []

    def start_response(status: str, headers: list) -> None:
        captured.append((status, headers))

    result = app({
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/api/v1/onboarding/start",
        "QUERY_STRING": "",
        "CONTENT_LENGTH": "128",
        "CONTENT_TYPE": "application/json",
        "REMOTE_ADDR": "127.0.0.1",
        "wsgi.input": FailingInput(b""),
    }, start_response)
    expect(captured and captured[0][0] == "413 Payload Too Large", f"expected 413 got {captured}")
    payload = json.loads(result[0])
    expect(payload.get("error") == "body_too_large", str(payload))
    header_dict = {k.lower(): v for k, v in captured[0][1]}
    expect(header_dict.get("access-control-allow-origin") == "https://app.arclink.online", str(header_dict))

    print("PASS test_wsgi_body_limit_rejects_before_read")


def test_admin_cidr_boundary_uses_remote_ip_and_preserves_public_routes() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_cidr_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_cidr_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_cidr_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "example.test",
        "ARCLINK_CORS_ORIGIN": "https://app.arclink.online",
        "ARCLINK_BACKEND_ALLOWED_CIDRS": "203.0.113.0/24,172.16.0.0/12",
    })
    api.upsert_arclink_admin(conn, admin_id="admin_cidr", email="cidr@example.test", role="ops")
    session = api.create_arclink_admin_session(conn, admin_id="admin_cidr", session_id="asess_cidr")

    status, payload, headers = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/admin/dashboard",
        headers=auth_headers(session),
        config=config,
        remote_addr="198.51.100.9",
    )
    expect(status == 403, f"expected disallowed remote 403 got {status}: {payload}")
    header_dict = {k.lower(): v for k, v in headers}
    expect(header_dict.get("access-control-allow-origin") == "https://app.arclink.online", str(header_dict))

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/admin/dashboard",
        headers=auth_headers(session),
        config=config,
        remote_addr="203.0.113.7",
    )
    expect(status == 200, f"expected allowed remote 200 got {status}: {payload}")

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/admin/dashboard",
        headers={**auth_headers(session), "X-Forwarded-For": "198.51.100.9"},
        config=config,
        remote_addr="127.0.0.1",
    )
    expect(status == 403, f"expected forwarded disallowed remote 403 got {status}: {payload}")

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/admin/dashboard",
        headers={**auth_headers(session), "X-Forwarded-For": "203.0.113.8"},
        config=config,
        remote_addr="172.18.0.10",
    )
    expect(
        status == 200,
        f"expected trusted proxy forwarded allowed remote 200 got {status}: {payload}",
    )

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/admin/dashboard",
        headers={**auth_headers(session), "X-Forwarded-For": "203.0.113.8"},
        config=config,
        remote_addr="198.51.100.9",
    )
    expect(status == 403, f"expected untrusted direct spoofed forwarded remote 403 got {status}: {payload}")

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="POST",
        path="/api/v1/onboarding/start",
        headers={},
        body=json.dumps({"channel": "web", "email": "cidr-public@example.test"}),
        config=config,
        remote_addr="198.51.100.9",
    )
    expect(status == 201, f"public onboarding should bypass admin CIDR got {status}: {payload}")

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/adapter-mode",
        headers={},
        config=config,
        remote_addr="198.51.100.9",
    )
    expect(status == 200, f"public adapter-mode should bypass admin CIDR got {status}: {payload}")
    expect("fake_mode" in payload and "fake_stripe" in payload, str(payload))

    print("PASS test_admin_cidr_boundary_uses_remote_ip_and_preserves_public_routes")


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
        headers=browser_auth_headers(session, kind="admin", csrf=True),
        body=json.dumps({
            "action_type": "restart", "target_kind": "deployment",
            "target_id": prepared["deployment_id"], "reason": "ro test",
            "idempotency_key": "ro-test-1",
        }),
        config=config,
    )
    expect(status == 401, f"read_only mutation expected 401 got {status}: {payload}")
    expect(payload.get("error") == "unauthorized", str(payload))

    print("PASS test_read_only_admin_blocked_from_mutations")


def test_login_rejects_unknown_email() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_badlogin_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_badlogin_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_badlogin_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    api.upsert_arclink_admin(
        conn,
        admin_id="admin_badlogin",
        email="admin-badlogin@example.test",
        role="owner",
        password="admin-test-password",
    )

    # Admin login with unknown email -> 401
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/auth/admin/login",
        headers={}, body=json.dumps({"email": "nonexistent@example.test", "password": "admin-test-password"}),
        config=config,
    )
    expect(status == 401, f"admin login expected 401 got {status}: {payload}")

    # Admin login with wrong password -> 401
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/auth/admin/login",
        headers={}, body=json.dumps({"email": "admin-badlogin@example.test", "password": "wrong-password"}),
        config=config,
    )
    expect(status == 401, f"wrong admin password expected 401 got {status}: {payload}")

    # User login with unknown email -> 401
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/auth/user/login",
        headers={}, body=json.dumps({"email": "nonexistent@example.test", "password": "user-test-password"}),
        config=config,
    )
    expect(status == 401, f"user login expected 401 got {status}: {payload}")

    # Admin login with blank email -> 401
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/auth/admin/login",
        headers={}, body=json.dumps({"email": "", "password": "admin-test-password"}),
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
            headers={}, body=json.dumps({"email": "ratelimit@example.test", "password": "admin-test-password"}),
            config=config,
        )
        # These will return 401 (unknown email), but rate limit counter increments

    # 6th attempt with same subject should be rate limited -> 429
    status, payload, headers = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/auth/admin/login",
        headers={}, body=json.dumps({"email": "ratelimit@example.test", "password": "admin-test-password"}),
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


def test_webhook_rate_limits_are_provider_scoped() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_webhook_rl_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_webhook_rl_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "example.test",
        "TELEGRAM_WEBHOOK_SECRET": "tg_secret",
        "ARCLINK_WEBHOOK_RATE_LIMIT_DEFAULT": "1",
        "ARCLINK_WEBHOOK_RATE_LIMIT_WINDOW_SECONDS": "60",
    })

    cases = [
        (
            "/api/v1/webhooks/stripe",
            {},
            json.dumps({"id": "evt_rl", "type": "checkout.session.completed", "data": {"object": {}}}),
        ),
        (
            "/api/v1/webhooks/telegram",
            {"X-Telegram-Bot-Api-Secret-Token": "tg_secret"},
            json.dumps({"update_id": 1}),
        ),
        (
            "/api/v1/webhooks/discord",
            {"x-signature-ed25519": "sig", "x-signature-timestamp": "1"},
            json.dumps({"id": "int_rl", "type": 1}),
        ),
    ]

    for path, headers, body in cases:
        hosted.route_arclink_hosted_api(
            conn,
            method="POST",
            path=path,
            headers=headers,
            body=body,
            config=config,
            remote_addr="198.51.100.10",
        )
        status, payload, response_headers = hosted.route_arclink_hosted_api(
            conn,
            method="POST",
            path=path,
            headers=headers,
            body=body,
            config=config,
            remote_addr="198.51.100.10",
        )
        expect(status == 429, f"{path} expected provider-scoped 429 got {status}: {payload}")
        header_dict = {k.lower(): v for k, v in response_headers}
        expect(header_dict.get("x-ratelimit-limit") == "1", f"missing limit header for {path}: {header_dict}")

    scopes = {
        row["scope"]
        for row in conn.execute("SELECT DISTINCT scope FROM rate_limits WHERE scope LIKE 'arclink:webhook:%'")
    }
    expect(
        scopes == {"arclink:webhook:stripe", "arclink:webhook:telegram", "arclink:webhook:discord"},
        str(scopes),
    )
    print("PASS test_webhook_rate_limits_are_provider_scoped")


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


def test_wsgi_405_status_text_for_rejected_preflight_method() -> None:
    from io import BytesIO
    control = load_module("arclink_control.py", "arclink_control_hosted_405_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_405_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    app = hosted.make_arclink_hosted_api_wsgi(conn, config=config)

    captured: list[tuple[str, list]] = []

    def start_response(status: str, headers: list) -> None:
        captured.append((status, headers))

    environ = {
        "REQUEST_METHOD": "OPTIONS",
        "PATH_INFO": "/api/v1/onboarding/start",
        "QUERY_STRING": "",
        "CONTENT_LENGTH": "0",
        "HTTP_ACCESS_CONTROL_REQUEST_METHOD": "GET",
        "wsgi.input": BytesIO(b""),
    }
    app(environ, start_response)
    expect(len(captured) == 1, f"expected 1 start_response call, got {len(captured)}")
    expect(captured[0][0] == "405 Method Not Allowed", f"expected 405 text got '{captured[0][0]}'")

    print("PASS test_wsgi_405_status_text_for_rejected_preflight_method")


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
        headers={}, body=json.dumps({"price_id": "price_sovereign"}), config=config,
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


def test_onboarding_claim_session_creates_user_session_after_payment() -> None:
    """After Stripe payment, the browser exchanges the onboarding session_id
    for a user session via POST /onboarding/claim-session.
    """
    control = load_module("arclink_control.py", "arclink_control_hosted_claim_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_claim_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_claim_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_claim_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "example.test",
        "ARCLINK_COOKIE_DOMAIN": ".arclink.online",
    })
    prepared = seed_paid_deployment(control, onboarding, conn)
    claim_token = "browser-claim-proof-test"
    conn.execute(
        "UPDATE arclink_onboarding_sessions SET metadata_json = ? WHERE session_id = ?",
        (json.dumps({"browser_claim_proof_hash": api._hash_token(claim_token)}), "onb_hosted"),
    )
    conn.commit()

    # Claim session -> 201 with Set-Cookie headers
    status, payload, headers = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/onboarding/claim-session",
        headers={}, body=json.dumps({"session_id": "onb_hosted", "claim_token": claim_token}),
        config=config,
    )
    expect(status == 201, f"expected 201 got {status}: {payload}")
    expect("session" in payload, str(payload))
    expect(payload["user_id"] == prepared["user_id"], str(payload))
    expect(payload["email"] == "hosted-user@example.test", str(payload))
    cookie_headers = [v for k, v in headers if k == "Set-Cookie"]
    expect(len(cookie_headers) >= 3, f"expected at least 3 Set-Cookie headers, got {len(cookie_headers)}")
    cookie_text = " ".join(cookie_headers)
    expect("arclink_user_session_id=" in cookie_text, "missing session_id cookie")
    expect("arclink_user_session_token=" in cookie_text, "missing session_token cookie")
    expect("arclink_user_csrf=" in cookie_text, "missing csrf cookie")
    expect("HttpOnly" in cookie_text, "missing HttpOnly flag")

    # Claimed session should work for dashboard access
    session = payload["session"]
    status, _, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/user/dashboard",
        headers=auth_headers(session), config=config,
    )
    expect(status == 200, f"claimed session dashboard expected 200 got {status}")

    # If the browser loses the 201 response during a Stripe redirect/network
    # handoff, retrying with the same proof token should mint a replacement
    # session for the same user during the short replay window.
    status, replay_payload, replay_headers = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/onboarding/claim-session",
        headers={}, body=json.dumps({"session_id": "onb_hosted", "claim_token": claim_token}),
        config=config,
    )
    expect(status == 201, f"expected idempotent claim replay 201 got {status}: {replay_payload}")
    expect(replay_payload["user_id"] == prepared["user_id"], str(replay_payload))
    expect(replay_payload["session"]["session_id"] != session["session_id"], str(replay_payload))
    replay_cookie_headers = [v for k, v in replay_headers if k == "Set-Cookie"]
    expect(any("arclink_user_session_token=" in value for value in replay_cookie_headers), str(replay_cookie_headers))

    print("PASS test_onboarding_claim_session_creates_user_session_after_payment")


def test_onboarding_claim_session_rejects_unpaid() -> None:
    """Claim-session returns 402 if entitlement is not yet paid."""
    control = load_module("arclink_control.py", "arclink_control_hosted_claim_unpaid_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hosted_claim_unpaid_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_claim_unpaid_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_claim_unpaid_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})

    # Create onboarding session and prepare deployment (but do NOT set paid)
    session = onboarding.create_or_resume_arclink_onboarding_session(
        conn, channel="web", channel_identity="unpaid@example.test",
        session_id="onb_unpaid", email_hint="unpaid@example.test",
        display_name_hint="Unpaid", selected_plan_id="founders",
    )
    onboarding.prepare_arclink_onboarding_deployment(
        conn, session_id=session["session_id"],
        base_domain="example.test", prefix="unpaid-vault",
    )
    claim_token = "browser-claim-proof-unpaid"
    conn.execute(
        "UPDATE arclink_onboarding_sessions SET metadata_json = ? WHERE session_id = ?",
        (json.dumps({"browser_claim_proof_hash": api._hash_token(claim_token)}), "onb_unpaid"),
    )
    conn.commit()

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/onboarding/claim-session",
        headers={}, body=json.dumps({"session_id": "onb_unpaid", "claim_token": claim_token}),
        config=config,
    )
    expect(status == 402, f"expected 402 got {status}: {payload}")
    expect(payload["error"] == "entitlement_not_paid", str(payload))

    print("PASS test_onboarding_claim_session_rejects_unpaid")


def test_onboarding_claim_session_rejects_unknown_session() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_claim_unknown_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_claim_unknown_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/onboarding/claim-session",
        headers={}, body=json.dumps({"session_id": "nonexistent"}),
        config=config,
    )
    expect(status == 401, f"expected 401 got {status}: {payload}")

    print("PASS test_onboarding_claim_session_rejects_unknown_session")


def test_onboarding_cancel_marks_session_cancelled() -> None:
    control = load_module("arclink_control.py", "arclink_control_hosted_cancel_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_cancel_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})

    # Start onboarding
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/onboarding/start",
        headers={}, body=json.dumps({"channel": "web", "email": "cancel@example.test"}),
        config=config,
    )
    expect(status == 201, f"expected 201 got {status}")
    session_id = payload["session"]["session_id"]
    cancel_token = payload["browser_cancel_token"]

    # Cancel it
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/onboarding/cancel",
        headers={}, body=json.dumps({"session_id": session_id, "cancel_token": cancel_token}),
        config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect(payload["status"] == "abandoned", str(payload))
    expect(payload["changed"] is True, str(payload))

    # Cancelling again is idempotent
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/onboarding/cancel",
        headers={}, body=json.dumps({"session_id": session_id, "cancel_token": cancel_token}),
        config=config,
    )
    expect(status == 200, f"idempotent cancel expected 200 got {status}: {payload}")
    expect(payload["changed"] is False, str(payload))

    # Cancelling nonexistent session -> 404
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="POST", path="/api/v1/onboarding/cancel",
        headers={}, body=json.dumps({"session_id": "nonexistent", "cancel_token": cancel_token}),
        config=config,
    )
    expect(status == 404, f"expected 404 got {status}: {payload}")

    print("PASS test_onboarding_cancel_marks_session_cancelled")


def test_onboarding_status_returns_entitlement_and_identity() -> None:
    """The onboarding/status endpoint is the checkout success polling target.
    It must return entitlement_state and user identity fields."""
    control = load_module("arclink_control.py", "arclink_control_hosted_onbstatus_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_hosted_onbstatus_test")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_onbstatus_test")
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})
    prepared = seed_paid_deployment(control, onboarding, conn)
    conn.execute(
        "UPDATE arclink_deployments SET status = 'active', updated_at = ? WHERE deployment_id = ?",
        (control.utc_now_iso(), prepared["deployment_id"]),
    )
    conn.commit()

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="GET",
        path="/api/v1/onboarding/status",
        headers={}, query={"session_id": "onb_hosted"},
        config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect(payload["user_id"] == prepared["user_id"], str(payload))
    expect(payload["entitlement_state"] == "paid", str(payload))
    expect(payload["display_name"] == "Hosted User", str(payload))
    expect(payload["channel"] == "web", str(payload))
    expect(payload["deployment_id"] == prepared["deployment_id"], str(payload))
    expect(payload["deployment"]["ready"] is True, str(payload))
    expect(payload["deployment"]["access"]["urls"]["hermes"].startswith("https://"), str(payload))
    expect(payload["deployment"]["service_health"][0]["service_name"] == "qmd-mcp", str(payload))

    # Missing session_id -> 400
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/onboarding/status",
        headers={}, query={}, config=config,
    )
    expect(status == 400, f"expected 400 got {status}")

    # Unknown session_id -> 404
    status, payload, _ = hosted.route_arclink_hosted_api(
        conn, method="GET", path="/api/v1/onboarding/status",
        headers={}, query={"session_id": "nonexistent"}, config=config,
    )
    expect(status == 404, f"expected 404 got {status}")

    print("PASS test_onboarding_status_returns_entitlement_and_identity")


def main() -> int:
    test_public_onboarding_routes_work_without_session_auth()
    test_user_dashboard_requires_session_auth()
    test_user_agent_identity_route_requires_csrf_and_updates_deployment()
    test_wrapped_routes_are_scoped_csrf_gated_and_admin_aggregate_only()
    test_user_crew_recipe_routes_require_csrf_and_apply_recipe()
    test_admin_dashboard_requires_admin_session()
    test_admin_action_requires_csrf_and_mutation_role()
    test_admin_crew_recipe_route_is_admin_csrf_and_audited()
    test_safe_error_shapes_never_leak_internal_details()
    test_request_id_propagation_and_cors()
    test_admin_login_sets_session_cookies()
    test_unified_login_resolves_user_or_admin_session()
    test_admin_login_ignores_client_asserted_mfa()
    test_session_revoke_requires_admin_auth_and_csrf()
    test_stripe_webhook_route_rejects_without_secret()
    test_user_billing_route_returns_entitlement_and_subscriptions()
    test_user_provisioning_status_route()
    test_user_provisioning_status_missing_requested_deployment_is_404()
    test_user_routes_are_isolated_across_accounts()
    test_user_credentials_are_acknowledged_and_removed_after_storage()
    test_user_share_grants_create_approved_accepted_linked_resources()
    test_admin_service_health_route()
    test_admin_provisioning_jobs_route()
    test_admin_audit_route()
    test_admin_events_route()
    test_admin_queued_actions_list_route()
    test_user_portal_link_route()
    test_user_login_sets_session_cookies_and_logout_clears_them()
    test_public_onboarding_checkout_route()
    test_public_onboarding_checkout_resolves_live_stripe_from_config()
    test_public_onboarding_checkout_maps_package_price_ids()
    test_public_bot_checkout_button_redirects_to_stripe()
    test_web_telegram_discord_onboarding_parity()
    test_admin_dns_drift_route()
    test_admin_logout_clears_cookies_and_revokes_session()
    test_stripe_webhook_processes_entitlement_transition()
    test_stripe_webhook_received_duplicate_is_acknowledged_as_replay()
    test_stripe_webhook_queues_paid_ping_for_telegram_user()
    test_stripe_webhook_queues_paid_ping_for_discord_user()
    test_telegram_webhook_route()
    test_telegram_webhook_secret_boundary()
    test_telegram_webhook_sends_reply_when_transport_is_available()
    test_public_agent_live_trigger_backpressure_defers_to_delivery_worker()
    test_telegram_fast_ack_backpressure_is_cosmetic()
    test_public_agent_live_trigger_auto_mode_defers_without_docker_socket()
    test_telegram_webhook_acknowledges_button_callbacks()
    test_telegram_credential_ack_edits_original_secret_message()
    test_discord_webhook_route()
    test_health_endpoint_requires_no_auth()
    test_user_provider_state_route()
    test_provider_state_suspends_chutes_on_past_due_billing()
    test_admin_provider_state_route()
    test_admin_reconciliation_route()
    test_stripe_webhook_rejects_bad_signature()
    test_unauthenticated_logout_and_portal_rejected()
    test_wsgi_adapter_smoke()
    test_wsgi_adapter_can_use_per_request_connections()
    test_request_body_limits_and_json_errors()
    test_wsgi_body_limit_rejects_before_read()
    test_admin_cidr_boundary_uses_remote_ip_and_preserves_public_routes()
    test_hosted_api_has_executable_control_node_entrypoint()
    test_read_only_admin_blocked_from_mutations()
    test_login_rejects_unknown_email()
    test_openapi_spec_route_serves_valid_contract()
    test_openapi_spec_matches_static_copy()
    test_rate_limit_returns_429_with_headers()
    test_rate_limit_onboarding_returns_429()
    test_webhook_rate_limits_are_provider_scoped()
    test_wsgi_503_status_text_for_degraded_health()
    test_wsgi_405_status_text_for_rejected_preflight_method()
    test_onboarding_payload_validation_rejects_missing_fields()
    test_onboarding_payload_validation_rejects_invalid_channel()
    test_admin_operator_snapshot_requires_auth_and_returns_snapshot()
    test_admin_scale_operations_requires_auth_and_returns_snapshot()
    test_onboarding_claim_session_creates_user_session_after_payment()
    test_onboarding_claim_session_rejects_unpaid()
    test_onboarding_claim_session_rejects_unknown_session()
    test_onboarding_cancel_marks_session_cancelled()
    test_onboarding_status_returns_entitlement_and_identity()
    print("PASS all 75 ArcLink hosted API tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
