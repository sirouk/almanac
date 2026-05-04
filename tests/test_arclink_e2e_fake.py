#!/usr/bin/env python3
"""ArcLink fake E2E harness - Production 11.

Proves the full journey using only fake adapters and in-memory SQLite:
  web signup -> onboarding answers -> checkout simulation -> Stripe webhook
  -> entitlement activation -> provisioning request -> service health
  -> user dashboard state -> admin audit -> admin action.

No live credentials required.
"""
from __future__ import annotations

import json
import time

from arclink_test_helpers import auth_headers, expect, load_module, memory_db, sign_stripe


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOD_SUFFIX = "_e2e_fake"


def _load():
    control = load_module("arclink_control.py", f"control{_MOD_SUFFIX}")
    api = load_module("arclink_api_auth.py", f"api{_MOD_SUFFIX}")
    hosted = load_module("arclink_hosted_api.py", f"hosted{_MOD_SUFFIX}")
    adapters = load_module("arclink_adapters.py", f"adapters{_MOD_SUFFIX}")
    return control, api, hosted, adapters


def _setup(control, hosted):
    conn = memory_db(control)
    config = hosted.HostedApiConfig(env={
        "ARCLINK_BASE_DOMAIN": "example.test",
        "STRIPE_WEBHOOK_SECRET": "whsec_test",
    })
    stripe_client = hosted.FakeStripeClient()
    return conn, config, stripe_client


def _api(hosted, conn, config, method, path, headers=None, body=None, stripe_client=None):
    status, payload, resp_headers = hosted.route_arclink_hosted_api(
        conn,
        method=method,
        path=f"/api/v1{path}",
        headers=headers or {},
        body=json.dumps(body) if isinstance(body, dict) else (body or ""),
        config=config,
        stripe_client=stripe_client,
    )
    return status, payload, resp_headers


# ---------------------------------------------------------------------------
# Full journey test
# ---------------------------------------------------------------------------

def test_full_fake_journey():
    """Web signup -> checkout -> webhook -> entitlement -> dashboard -> admin."""
    control, api, hosted, adapters = _load()
    conn, config, stripe_client = _setup(control, hosted)

    # ---- 1. Web onboarding: start ----------------------------------------
    status, payload, _ = _api(hosted, conn, config, "POST", "/onboarding/start", body={
        "channel": "web",
        "email": "alice@example.test",
        "plan_id": "starter",
        "display_name": "Alice",
    })
    expect(status == 201, f"onboarding/start: expected 201 got {status}: {payload}")
    session_id = payload["session"]["session_id"]
    expect(bool(session_id), "onboarding/start: missing session_id")

    # ---- 2. Onboarding: answer question ----------------------------------
    status, payload, _ = _api(hosted, conn, config, "POST", "/onboarding/answer", body={
        "session_id": session_id,
        "question_key": "name",
        "display_name": "Alice Wonderland",
        "email": "alice@example.test",
    })
    expect(status == 200, f"onboarding/answer: expected 200 got {status}: {payload}")

    # ---- 3. Onboarding: open checkout ------------------------------------
    status, payload, _ = _api(hosted, conn, config, "POST", "/onboarding/checkout", body={
        "session_id": session_id,
        "price_id": "price_starter",
        "success_url": "https://app.example.test/success",
        "cancel_url": "https://app.example.test/cancel",
    }, stripe_client=stripe_client)
    expect(status == 200, f"onboarding/checkout: expected 200 got {status}: {payload}")
    checkout_session_id = payload["session"].get("checkout_session_id", "")
    user_id = payload["session"]["user_id"]
    deployment_id = payload["session"]["deployment_id"]
    expect(bool(checkout_session_id), "checkout: missing checkout_session_id")
    expect(bool(user_id), "checkout: missing user_id")
    expect(bool(deployment_id), "checkout: missing deployment_id")

    # ---- 4. Simulate Stripe webhook: checkout.session.completed ----------
    webhook_payload = json.dumps({
        "id": "evt_e2e_checkout",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": checkout_session_id,
                "customer": "cus_e2e_test",
                "subscription": "sub_e2e_test",
                "client_reference_id": user_id,
                "metadata": {
                    "arclink_user_id": user_id,
                    "arclink_onboarding_session_id": session_id,
                    "arclink_deployment_id": deployment_id,
                },
            }
        },
    })
    sig = sign_stripe(adapters, webhook_payload)
    status, payload, _ = _api(hosted, conn, config, "POST", "/webhooks/stripe",
                              headers={"Stripe-Signature": sig}, body=webhook_payload)
    expect(status == 200, f"webhook: expected 200 got {status}: {payload}")
    expect(payload["status"] == "processed", f"webhook: expected processed got {payload['status']}")
    expect(not payload.get("replayed"), "webhook: should not be replayed")

    # ---- 5. Verify entitlement is now paid -------------------------------
    row = conn.execute(
        "SELECT entitlement_state FROM arclink_users WHERE user_id = ?", (user_id,)
    ).fetchone()
    expect(row is not None, "user row missing after webhook")
    expect(row["entitlement_state"] == "paid", f"expected paid got {row['entitlement_state']}")

    # ---- 6. Mark service healthy (simulates provisioning completion) -----
    control.upsert_arclink_service_health(
        conn, deployment_id=deployment_id, service_name="qmd-mcp", status="healthy",
    )

    # ---- 7. User login ---------------------------------------------------
    status, payload, _ = _api(hosted, conn, config, "POST", "/auth/user/login", body={
        "email": "alice@example.test",
    })
    expect(status == 201, f"user login: expected 201 got {status}: {payload}")
    user_session = payload["session"]
    expect(bool(user_session["session_token"]), "user login: missing session_token")

    # ---- 8. User dashboard -----------------------------------------------
    status, payload, _ = _api(hosted, conn, config, "GET", "/user/dashboard",
                              headers=auth_headers(user_session))
    expect(status == 200, f"user dashboard: expected 200 got {status}: {payload}")
    expect(payload["user"]["user_id"] == user_id, "dashboard: wrong user_id")

    # ---- 9. User billing -------------------------------------------------
    status, payload, _ = _api(hosted, conn, config, "GET", "/user/billing",
                              headers=auth_headers(user_session))
    expect(status == 200, f"user billing: expected 200 got {status}: {payload}")
    expect(payload["entitlement"]["state"] == "paid", f"billing: expected paid got {payload['entitlement']}")

    # ---- 10. User provisioning status ------------------------------------
    status, payload, _ = _api(hosted, conn, config, "GET", "/user/provisioning",
                              headers=auth_headers(user_session))
    expect(status == 200, f"user provisioning: expected 200 got {status}: {payload}")
    expect(len(payload["deployments"]) >= 1, "provisioning: no deployments")

    # ---- 11. User provider state -----------------------------------------
    status, payload, _ = _api(hosted, conn, config, "GET", "/user/provider-state",
                              headers=auth_headers(user_session))
    expect(status == 200, f"user provider-state: expected 200 got {status}: {payload}")

    # ---- 12. Admin setup and login ---------------------------------------
    api.upsert_arclink_admin(conn, admin_id="admin_e2e", email="ops@example.test", role="ops")
    admin_session = api.create_arclink_admin_session(
        conn, admin_id="admin_e2e", session_id="asess_e2e", mfa_verified=True,
    )

    # ---- 13. Admin dashboard ---------------------------------------------
    status, payload, _ = _api(hosted, conn, config, "GET", "/admin/dashboard",
                              headers=auth_headers(admin_session))
    expect(status == 200, f"admin dashboard: expected 200 got {status}: {payload}")
    expect("deployments" in payload, "admin dashboard: missing deployments key")
    # Verify our user's deployment is visible
    dep_ids = [d["deployment_id"] for d in payload["deployments"]]
    expect(deployment_id in dep_ids, f"admin dashboard: deployment {deployment_id} not listed")

    # ---- 14. Admin service health ----------------------------------------
    status, payload, _ = _api(hosted, conn, config, "GET", "/admin/service-health",
                              headers=auth_headers(admin_session))
    expect(status == 200, f"admin service-health: expected 200 got {status}: {payload}")

    # ---- 15. Admin audit -------------------------------------------------
    status, payload, _ = _api(hosted, conn, config, "GET", "/admin/audit",
                              headers=auth_headers(admin_session))
    expect(status == 200, f"admin audit: expected 200 got {status}: {payload}")

    # ---- 16. Admin events ------------------------------------------------
    status, payload, _ = _api(hosted, conn, config, "GET", "/admin/events",
                              headers=auth_headers(admin_session))
    expect(status == 200, f"admin events: expected 200 got {status}: {payload}")

    # ---- 17. Admin provisioning jobs -------------------------------------
    status, payload, _ = _api(hosted, conn, config, "GET", "/admin/provisioning-jobs",
                              headers=auth_headers(admin_session))
    expect(status == 200, f"admin provisioning-jobs: expected 200 got {status}: {payload}")

    # ---- 18. Admin reconciliation ----------------------------------------
    status, payload, _ = _api(hosted, conn, config, "GET", "/admin/reconciliation",
                              headers=auth_headers(admin_session))
    expect(status == 200, f"admin reconciliation: expected 200 got {status}: {payload}")

    # ---- 19. Admin provider state ----------------------------------------
    status, payload, _ = _api(hosted, conn, config, "GET", "/admin/provider-state",
                              headers=auth_headers(admin_session))
    expect(status == 200, f"admin provider-state: expected 200 got {status}: {payload}")

    # ---- 20. Admin queues action -----------------------------------------
    status, payload, _ = _api(hosted, conn, config, "POST", "/admin/actions",
                              headers=auth_headers(admin_session, csrf=True),
                              body={
                                  "action_type": "restart",
                                  "target_kind": "deployment",
                                  "target_id": deployment_id,
                                  "reason": "e2e fake test",
                                  "idempotency_key": "e2e-fake-restart-1",
                              })
    expect(status == 202, f"admin action: expected 202 got {status}: {payload}")
    expect(payload["action"]["status"] == "queued", f"admin action: expected queued got {payload['action']}")

    # ---- 21. Admin can see queued actions --------------------------------
    status, payload, _ = _api(hosted, conn, config, "GET", "/admin/actions",
                              headers=auth_headers(admin_session))
    expect(status == 200, f"admin actions list: expected 200 got {status}: {payload}")
    expect(len(payload["actions"]) >= 1, "admin actions list: no actions")

    # ---- 22. Admin DNS drift (empty is fine with fake adapter) -----------
    status, payload, _ = _api(hosted, conn, config, "GET", "/admin/dns-drift",
                              headers=auth_headers(admin_session))
    expect(status == 200, f"admin dns-drift: expected 200 got {status}: {payload}")

    # ---- 23. User portal link (Stripe billing portal) --------------------
    status, payload, _ = _api(hosted, conn, config, "POST", "/user/portal",
                              headers=auth_headers(user_session, csrf=True),
                              stripe_client=stripe_client)
    expect(status == 200, f"user portal: expected 200 got {status}: {payload}")

    # ---- 24. Webhook replay is idempotent --------------------------------
    sig2 = sign_stripe(adapters, webhook_payload)
    status, payload, _ = _api(hosted, conn, config, "POST", "/webhooks/stripe",
                              headers={"Stripe-Signature": sig2}, body=webhook_payload)
    expect(status == 200, f"webhook replay: expected 200 got {status}: {payload}")
    expect(payload.get("replayed") is True, "webhook replay: should be replayed")

    # ---- 25. User logout -------------------------------------------------
    status, payload, _ = _api(hosted, conn, config, "POST", "/auth/user/logout",
                              headers=auth_headers(user_session, csrf=True))
    expect(status == 200, f"user logout: expected 200 got {status}: {payload}")

    # ---- 26. Dashboard after logout returns 401 --------------------------
    status, payload, _ = _api(hosted, conn, config, "GET", "/user/dashboard",
                              headers=auth_headers(user_session))
    expect(status == 401, f"after logout: expected 401 got {status}")

    print("PASS test_full_fake_journey")


# ---------------------------------------------------------------------------
# Negative / boundary tests
# ---------------------------------------------------------------------------

def test_unauthenticated_user_routes_return_401():
    """User routes reject requests without valid session."""
    control, _, hosted, _ = _load()
    conn, config, _ = _setup(control, hosted)

    for path in ("/user/dashboard", "/user/billing", "/user/provisioning"):
        status, _, _ = _api(hosted, conn, config, "GET", path)
        expect(status == 401, f"{path} without auth: expected 401 got {status}")

    print("PASS test_unauthenticated_user_routes_return_401")


def test_unauthenticated_admin_routes_return_401():
    """Admin routes reject requests without valid session."""
    control, _, hosted, _ = _load()
    conn, config, _ = _setup(control, hosted)

    for path in ("/admin/dashboard", "/admin/service-health", "/admin/audit",
                 "/admin/events", "/admin/provisioning-jobs"):
        status, _, _ = _api(hosted, conn, config, "GET", path)
        expect(status == 401, f"{path} without auth: expected 401 got {status}")

    print("PASS test_unauthenticated_admin_routes_return_401")


def test_admin_action_requires_csrf():
    """Admin mutation without CSRF token is rejected."""
    control, api, hosted, _ = _load()
    conn, config, _ = _setup(control, hosted)
    api.upsert_arclink_admin(conn, admin_id="admin_csrf", email="csrf@example.test", role="ops")
    session = api.create_arclink_admin_session(conn, admin_id="admin_csrf", mfa_verified=True)

    # POST without CSRF
    status, _, _ = _api(hosted, conn, config, "POST", "/admin/actions",
                        headers=auth_headers(session),  # no csrf=True
                        body={
                            "action_type": "restart",
                            "target_kind": "deployment",
                            "target_id": "dep_test",
                            "reason": "test",
                            "idempotency_key": "csrf-test-1",
                        })
    expect(status == 401, f"admin action without CSRF: expected 401 got {status}")

    print("PASS test_admin_action_requires_csrf")


def test_health_endpoint_public():
    """Health endpoint is public and returns 200."""
    control, _, hosted, _ = _load()
    conn, config, _ = _setup(control, hosted)

    status, payload, _ = _api(hosted, conn, config, "GET", "/health")
    expect(status == 200, f"health: expected 200 got {status}: {payload}")

    print("PASS test_health_endpoint_public")


def test_onboarding_checkout_creates_deployment():
    """Checkout flow creates user, deployment, and returns checkout URL."""
    control, _, hosted, adapters = _load()
    conn, config, stripe_client = _setup(control, hosted)

    # Start + checkout
    status, payload, _ = _api(hosted, conn, config, "POST", "/onboarding/start", body={
        "channel": "web", "email": "bob@example.test", "plan_id": "starter",
    })
    expect(status == 201, f"start: {status}")
    sid = payload["session"]["session_id"]

    status, payload, _ = _api(hosted, conn, config, "POST", "/onboarding/checkout", body={
        "session_id": sid,
        "success_url": "https://app.example.test/ok",
        "cancel_url": "https://app.example.test/no",
    }, stripe_client=stripe_client)
    expect(status == 200, f"checkout: {status}: {payload}")
    expect(bool(payload["session"]["user_id"]), "checkout: no user_id")
    expect(bool(payload["session"]["deployment_id"]), "checkout: no deployment_id")
    expect(bool(payload["session"]["checkout_url"]), "checkout: no checkout_url")

    print("PASS test_onboarding_checkout_creates_deployment")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_full_fake_journey()
    test_unauthenticated_user_routes_return_401()
    test_unauthenticated_admin_routes_return_401()
    test_admin_action_requires_csrf()
    test_health_endpoint_public()
    test_onboarding_checkout_creates_deployment()
    print("\nAll fake E2E tests passed.")
