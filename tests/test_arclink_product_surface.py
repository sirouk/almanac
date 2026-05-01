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


def test_product_surface_renders_usable_first_screen_and_checkout_flow() -> None:
    control = load_module("almanac_control.py", "almanac_control_product_surface_flow_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_product_surface_flow_test")
    surface = load_module("arclink_product_surface.py", "arclink_product_surface_flow_test")
    conn = memory_db(control)
    stripe = adapters.FakeStripeClient()

    home = surface.handle_arclink_product_surface_request(conn, method="GET", path="/")
    expect(home.status == 200, home.body)
    expect("Start Deployment" in home.body and "User Dashboard" in home.body and "Admin" in home.body, home.body)
    expect("#FB5005" in home.body and "purple" not in home.body.lower(), home.body)
    expect("Live provider mutations" in home.body, home.body)

    started = surface.handle_arclink_product_surface_request(
        conn,
        method="POST",
        path="/onboarding/start",
        params={
            "email": "surface@example.test",
            "name": "Surface Buyer",
            "plan": "starter",
            "model": "moonshotai/Kimi-K2.6-TEE",
        },
        stripe_client=stripe,
    )
    expect(started.status == 303 and started.headers[0][0] == "Location", str(started))
    session_id = started.headers[0][1].rsplit("/", 1)[-1]
    session_page = surface.handle_arclink_product_surface_request(conn, method="GET", path=f"/onboarding/{session_id}")
    expect("checkout_open" not in session_page.body and "surface@example.test" in session_page.body, session_page.body)

    checkout = surface.handle_arclink_product_surface_request(
        conn,
        method="POST",
        path=f"/onboarding/{session_id}/checkout",
        stripe_client=stripe,
    )
    expect(checkout.status == 303, str(checkout))
    api = surface.handle_arclink_product_surface_request(conn, method="GET", path=f"/api/onboarding/{session_id}")
    payload = json.loads(api.body)
    expect(payload["session"]["checkout_state"] == "open", str(payload))
    expect(payload["session"]["checkout_url"].startswith("https://stripe.test/checkout/"), str(payload))
    expect(any(event["event_type"] == "checkout_opened" for event in payload["events"]), str(payload["events"]))
    print("PASS test_product_surface_renders_usable_first_screen_and_checkout_flow")


def test_product_surface_user_and_admin_dashboards_are_secret_free_and_queue_only() -> None:
    control = load_module("almanac_control.py", "almanac_control_product_surface_dashboard_test")
    api_auth = load_module("arclink_api_auth.py", "arclink_api_auth_product_surface_dashboard_test")
    surface = load_module("arclink_product_surface.py", "arclink_product_surface_dashboard_test")
    conn = memory_db(control)
    prepared = surface.seed_arclink_product_surface_fixture(conn, env={"ARCLINK_BASE_DOMAIN": "example.test"})
    api_auth.upsert_arclink_admin(
        conn,
        admin_id="admin_surface",
        email="admin-surface@example.test",
        role="ops",
    )
    admin_session = api_auth.create_arclink_admin_session(
        conn,
        admin_id="admin_surface",
        session_id="asess_surface",
        mfa_verified=True,
    )

    user = surface.handle_arclink_product_surface_request(conn, method="GET", path=f"/user?user_id={prepared['user_id']}")
    expect(user.status == 200, user.body)
    expect("fixture-core-1a2b" in user.body and "qmd freshness" in user.body, user.body)
    expect("https://u-fixture-core-1a2b.example.test" in user.body, user.body)
    for label in ("Files", "Code", "Hermes", "Security", "Support"):
        expect(label in user.body, user.body)

    admin = surface.handle_arclink_product_surface_request(conn, method="GET", path="/admin")
    expect(admin.status == 200, admin.body)
    expect("Onboarding Funnel" in admin.body and "Queued Actions" in admin.body, admin.body)
    for label in ("Payments", "Infrastructure", "Security And Abuse", "Releases And Maintenance", "Logs And Events", "Audit"):
        expect(label in admin.body, admin.body)
    unauth_form_action = surface.handle_arclink_product_surface_request(
        conn,
        method="POST",
        path="/admin/actions",
        params={
            "action_type": "restart",
            "target_kind": "deployment",
            "target_id": prepared["deployment_id"],
            "reason": "restart from product surface contract test",
            "idempotency_key": "surface-action-unauth-form",
        },
    )
    expect(unauth_form_action.status == 401, unauth_form_action.body)
    unauth_api_action = surface.handle_arclink_product_surface_request(
        conn,
        method="POST",
        path="/api/admin/actions",
        params={
            "action_type": "restart",
            "target_kind": "deployment",
            "target_id": prepared["deployment_id"],
            "reason": "restart from product surface contract test",
            "idempotency_key": "surface-action-unauth-api",
        },
    )
    expect(unauth_api_action.status == 401, unauth_api_action.body)
    expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"] == 0, "unauth action queued")

    form_action = surface.handle_arclink_product_surface_request(
        conn,
        method="POST",
        path="/admin/actions",
        params={
            "session_id": admin_session["session_id"],
            "session_token": admin_session["session_token"],
            "csrf_token": admin_session["csrf_token"],
            "action_type": "restart",
            "target_kind": "deployment",
            "target_id": prepared["deployment_id"],
            "reason": "restart from product surface contract test",
            "idempotency_key": "surface-action-form-1",
        },
    )
    expect(form_action.status == 303, str(form_action))
    api_action = surface.handle_arclink_product_surface_request(
        conn,
        method="POST",
        path="/api/admin/actions",
        params={
            "session_id": admin_session["session_id"],
            "session_token": admin_session["session_token"],
            "csrf_token": admin_session["csrf_token"],
            "action_type": "restart",
            "target_kind": "deployment",
            "target_id": prepared["deployment_id"],
            "reason": "restart from product surface contract test",
            "idempotency_key": "surface-action-api-1",
        },
    )
    expect(api_action.status == 202, api_action.body)
    action_payload = json.loads(api_action.body)
    expect(action_payload["action"]["status"] == "queued", str(action_payload))
    expect(control.ensure_schema is not None, "control module import sanity")
    expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"] == 2, "action not queued")
    expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_audit_log").fetchone()["n"] == 2, "audit not written")
    expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_dns_records").fetchone()["n"] == 0, "DNS mutated")

    rendered = user.body + admin.body + unauth_api_action.body + api_action.body
    for forbidden in ("sk_", "whsec_", "xoxb-", "ntn_", "123456:"):
        expect(forbidden not in rendered, rendered)
    print("PASS test_product_surface_user_and_admin_dashboards_are_secret_free_and_queue_only")


def test_product_surface_css_contains_mobile_overflow_guards() -> None:
    control = load_module("almanac_control.py", "almanac_control_product_surface_responsive_test")
    surface = load_module("arclink_product_surface.py", "arclink_product_surface_responsive_test")
    conn = memory_db(control)
    surface.seed_arclink_product_surface_fixture(conn, env={"ARCLINK_BASE_DOMAIN": "example.test"})

    pages = (
        surface.handle_arclink_product_surface_request(conn, method="GET", path="/"),
        surface.handle_arclink_product_surface_request(conn, method="GET", path="/onboarding/onb_surface_fixture"),
        surface.handle_arclink_product_surface_request(conn, method="GET", path="/user"),
        surface.handle_arclink_product_surface_request(conn, method="GET", path="/admin"),
    )
    for page in pages:
        expect(page.status == 200, page.body)
        expect('name="viewport"' in page.body, page.body)
        expect(".hero, .grid, .grid.two { grid-template-columns: minmax(0, 1fr); }" in page.body, page.body)
        expect(".grid > *, .hero > *, .stack > * { min-width: 0; max-width: 100%; }" in page.body, page.body)
        expect("table { display: block; width: 100%; max-width: 100%; overflow-x: auto;" in page.body, page.body)
        expect("overflow-wrap: anywhere;" in page.body, page.body)
    print("PASS test_product_surface_css_contains_mobile_overflow_guards")


def test_product_surface_favicon_does_not_fall_through_to_404() -> None:
    control = load_module("almanac_control.py", "almanac_control_product_surface_favicon_test")
    surface = load_module("arclink_product_surface.py", "arclink_product_surface_favicon_test")
    conn = memory_db(control)

    favicon = surface.handle_arclink_product_surface_request(conn, method="GET", path="/favicon.ico")
    expect(favicon.status == 200, favicon.body)
    expect(favicon.content_type == "image/svg+xml", favicon.content_type)
    expect("FB5005" in favicon.body and "sk_" not in favicon.body, favicon.body)
    print("PASS test_product_surface_favicon_does_not_fall_through_to_404")


def test_product_surface_generic_errors_do_not_expose_internal_exception_text() -> None:
    control = load_module("almanac_control.py", "almanac_control_product_surface_generic_error_test")
    surface = load_module("arclink_product_surface.py", "arclink_product_surface_generic_error_test")
    conn = memory_db(control)
    raw_detail = "raw internal failure sk_test_should_not_render"
    original = surface.read_arclink_user_dashboard

    def fail_dashboard(*args, **kwargs):
        raise RuntimeError(raw_detail)

    surface.read_arclink_user_dashboard = fail_dashboard
    try:
        html_error = surface.handle_arclink_product_surface_request(
            conn,
            method="GET",
            path="/user?user_id=arcusr_hidden",
        )
        json_error = surface.handle_arclink_product_surface_request(
            conn,
            method="GET",
            path="/api/user?user_id=arcusr_hidden",
        )
    finally:
        surface.read_arclink_user_dashboard = original

    expect(html_error.status == 400, html_error.body)
    expect("Request blocked. Check input and try again." in html_error.body, html_error.body)
    expect(raw_detail not in html_error.body and "sk_test_should_not_render" not in html_error.body, html_error.body)
    payload = json.loads(json_error.body)
    expect(json_error.status == 400 and payload["error"] == "Request blocked. Check input and try again.", str(json_error))
    expect(raw_detail not in json_error.body and "sk_test_should_not_render" not in json_error.body, json_error.body)
    print("PASS test_product_surface_generic_errors_do_not_expose_internal_exception_text")


def main() -> int:
    test_product_surface_renders_usable_first_screen_and_checkout_flow()
    test_product_surface_user_and_admin_dashboards_are_secret_free_and_queue_only()
    test_product_surface_css_contains_mobile_overflow_guards()
    test_product_surface_favicon_does_not_fall_through_to_404()
    test_product_surface_generic_errors_do_not_expose_internal_exception_text()
    print("PASS all 5 ArcLink product surface tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
