#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
SESSION_HASH_ENV_KEYS = (
    "ARCLINK_CONFIG_FILE",
    "ARCLINK_BASE_DOMAIN",
    "ARCLINK_SESSION_HASH_PEPPER",
    "ARCLINK_SESSION_HASH_PEPPER_REQUIRED",
)


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
    use_explicit_local_session_hash_env()
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    control.ensure_schema(conn)
    return conn


def save_session_hash_env() -> dict[str, str | None]:
    return {key: os.environ.get(key) for key in SESSION_HASH_ENV_KEYS}


def restore_env(saved: dict[str, str | None]) -> None:
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def use_explicit_local_session_hash_env() -> None:
    os.environ["ARCLINK_CONFIG_FILE"] = os.devnull
    os.environ["ARCLINK_BASE_DOMAIN"] = "localhost"
    os.environ.pop("ARCLINK_SESSION_HASH_PEPPER", None)
    os.environ.pop("ARCLINK_SESSION_HASH_PEPPER_REQUIRED", None)


def seed_paid_deployment(control, onboarding, conn):
    session = onboarding.create_or_resume_arclink_onboarding_session(
        conn,
        channel="web",
        channel_identity="api-user@example.test",
        session_id="onb_api_auth",
        email_hint="api-user@example.test",
        display_name_hint="API User",
        selected_plan_id="sovereign",
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
    control = load_module("arclink_control.py", "arclink_control_api_auth_user_test")
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
    expect(str(stored["session_token_hash"]).startswith("hmac_sha256_v1$"), str(dict(stored)))
    expect(str(stored["csrf_token_hash"]).startswith("hmac_sha256_v1$"), str(dict(stored)))

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


def test_user_agent_identity_update_requires_session_and_csrf() -> None:
    control = load_module("arclink_control.py", "arclink_control_api_auth_agent_identity_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_api_auth_agent_identity_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_agent_identity_test")
    conn = memory_db(control)
    prepared = seed_paid_deployment(control, onboarding, conn)
    with tempfile.TemporaryDirectory() as tmpdir:
        hermes_home = Path(tmpdir) / "state" / "hermes-home"
        (hermes_home / "state").mkdir(parents=True)
        (hermes_home / "state" / "arclink-identity-context.json").write_text(
            json.dumps({"agent_label": "Old", "org_name": "Kept Org"}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        conn.execute(
            "UPDATE arclink_deployments SET metadata_json = ? WHERE deployment_id = ?",
            (
                json.dumps({"state_roots": {"hermes_home": str(hermes_home)}}, sort_keys=True),
                prepared["deployment_id"],
            ),
        )
        conn.commit()
        session = api.create_arclink_user_session(
            conn,
            user_id=prepared["user_id"],
            metadata={"surface": "browser"},
            session_id="usess_agent_identity",
        )
        try:
            api.user_update_agent_identity_api(
                conn,
                session_id=session["session_id"],
                session_token=session["session_token"],
                csrf_token="wrong",
                deployment_id=prepared["deployment_id"],
                agent_name="Atlas",
                agent_title="the right hand",
            )
        except api.ArcLinkApiAuthError as exc:
            expect("CSRF" in str(exc), str(exc))
        else:
            raise AssertionError("expected CSRF failure")
        updated = api.user_update_agent_identity_api(
            conn,
            session_id=session["session_id"],
            session_token=session["session_token"],
            csrf_token=session["csrf_token"],
            deployment_id=prepared["deployment_id"],
            agent_name="Atlas",
            agent_title="the right hand",
        )
        expect(updated.status == 200, str(updated))
        expect(updated.payload["deployment"]["agent_name"] == "Atlas", str(updated.payload))
        expect(updated.payload["identity_projection"]["status"] == "projected", str(updated.payload))
        row = conn.execute("SELECT agent_name, agent_title FROM arclink_deployments WHERE deployment_id = ?", (prepared["deployment_id"],)).fetchone()
        expect(row["agent_name"] == "Atlas" and row["agent_title"] == "the right hand", str(dict(row)))
        identity = json.loads((hermes_home / "state" / "arclink-identity-context.json").read_text(encoding="utf-8"))
        expect(identity["agent_label"] == "Atlas" and identity["agent_title"] == "the right hand", str(identity))
        expect(identity["org_name"] == "Kept Org", str(identity))
    print("PASS test_user_agent_identity_update_requires_session_and_csrf")


def test_provider_state_demotes_spoofed_unlimited_policy_from_operator_settings() -> None:
    control = load_module("arclink_control.py", "arclink_control_api_auth_provider_demote_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_api_auth_provider_demote_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_provider_demote_test")
    conn = memory_db(control)
    prepared = seed_paid_deployment(control, onboarding, conn)
    conn.execute(
        "UPDATE arclink_deployments SET metadata_json = ? WHERE deployment_id = ?",
        (
            json.dumps(
                {
                    "selected_model_id": "model-api",
                    "chutes": {
                        "secret_ref": f"secret://arclink/chutes/{prepared['deployment_id']}",
                        "monthly_budget_cents": 0,
                        "used_cents": 12,
                        "budget_policy": "observe_only_unlimited",
                    },
                },
                sort_keys=True,
            ),
            prepared["deployment_id"],
        ),
    )
    conn.commit()
    session = api.create_arclink_user_session(conn, user_id=prepared["user_id"], session_id="usess_provider_demote")
    result = api.read_provider_state_api(
        conn,
        session_id=session["session_id"],
        session_token=session["session_token"],
        env={"ARCLINK_PRIMARY_PROVIDER": "chutes"},
    )
    expect(result.status == 200, str(result))
    model = result.payload["deployment_models"][0]
    expect(model["credential_state"] == "budget_unconfigured", str(model))
    expect(model["allow_inference"] is False, str(model))
    expect(model["chutes"]["budget"]["status"] == "unconfigured", str(model))
    expect(model["chutes"]["budget"]["limit_enforced"] is True, str(model))
    expect(model["chutes"]["budget"]["status"] != "unlimited", str(model))
    print("PASS test_provider_state_demotes_spoofed_unlimited_policy_from_operator_settings")


def test_provider_state_available_cents_subtracts_open_reservations() -> None:
    # billing-H5: settled remaining_cents overstates spendable headroom because the
    # router subtracts open reservations before allowing new spend. Provider-state
    # must surface available_cents = max(0, remaining - reserved) so the dashboard
    # matches what the router enforces.
    control = load_module("arclink_control.py", "arclink_control_api_auth_available_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_api_auth_available_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_available_test")
    conn = memory_db(control)
    prepared = seed_paid_deployment(control, onboarding, conn)
    conn.execute(
        "UPDATE arclink_deployments SET metadata_json = ? WHERE deployment_id = ?",
        (
            json.dumps(
                {
                    "selected_model_id": "model-api",
                    "chutes": {
                        "secret_ref": f"secret://arclink/chutes/{prepared['deployment_id']}",
                        "monthly_budget_cents": 100,
                        "used_cents": 30,
                    },
                },
                sort_keys=True,
            ),
            prepared["deployment_id"],
        ),
    )
    # An open (status='reserved') reservation holds 25c of the 70c settled remaining.
    conn.execute(
        """
        INSERT INTO arclink_llm_budget_reservations (
          reservation_id, request_id, deployment_id, user_id, reserved_cents, status, created_at
        ) VALUES ('llmres_open', 'llmreq_open', ?, ?, 25, 'reserved', '2026-06-19T00:00:00+00:00')
        """,
        (prepared["deployment_id"], prepared["user_id"]),
    )
    conn.commit()
    session = api.create_arclink_user_session(conn, user_id=prepared["user_id"], session_id="usess_available")
    result = api.read_provider_state_api(
        conn,
        session_id=session["session_id"],
        session_token=session["session_token"],
        env={"ARCLINK_PRIMARY_PROVIDER": "chutes"},
    )
    expect(result.status == 200, str(result))
    budget = result.payload["deployment_models"][0]["chutes"]["budget"]
    expect(budget["remaining_cents"] == 70, str(budget))
    expect(budget["reserved_cents"] == 25, str(budget))
    expect(budget["available_cents"] == 45, f"available must subtract open reservations: {budget}")
    print("PASS test_provider_state_available_cents_subtracts_open_reservations")


def test_user_crew_recipe_api_applies_overlay_and_admin_on_behalf_is_audited() -> None:
    control = load_module("arclink_control.py", "arclink_control_api_auth_crew_recipe_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_api_auth_crew_recipe_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_crew_recipe_test")
    conn = memory_db(control)
    prepared = seed_paid_deployment(control, onboarding, conn)
    session = api.create_arclink_user_session(
        conn,
        user_id=prepared["user_id"],
        metadata={"surface": "browser"},
        session_id="usess_crew_recipe",
    )
    try:
        api.preview_user_crew_recipe_api(
            conn,
            session_id=session["session_id"],
            session_token=session["session_token"],
            csrf_token="wrong",
            role="founder",
            mission="ship the launch",
            treatment="peer",
            preset="Frontier",
            capacity="development",
        )
    except api.ArcLinkApiAuthError as exc:
        expect("CSRF" in str(exc), str(exc))
    else:
        raise AssertionError("expected Crew Recipe preview CSRF failure")
    preview = api.preview_user_crew_recipe_api(
        conn,
        session_id=session["session_id"],
        session_token=session["session_token"],
        csrf_token=session["csrf_token"],
        role="founder",
        mission="ship the launch",
        treatment="peer",
        preset="Frontier",
        capacity="development",
    )
    expect(preview.status == 200 and preview.payload["preview"]["mode"] == "fallback", str(preview))
    applied = api.apply_user_crew_recipe_api(
        conn,
        session_id=session["session_id"],
        session_token=session["session_token"],
        csrf_token=session["csrf_token"],
        role="founder",
        mission="ship the launch",
        treatment="peer",
        preset="Frontier",
        capacity="development",
    )
    expect(applied.status == 200 and applied.payload["recipe"]["status"] == "active", str(applied))
    current = api.read_user_crew_recipe_api(
        conn,
        session_id=session["session_id"],
        session_token=session["session_token"],
    )
    expect(current.payload["current"]["preset"] == "Frontier", str(current.payload))
    expect(current.payload["academy_training"]["status"] == "not_started", str(current.payload))
    api.upsert_arclink_admin(conn, admin_id="admin_crew_recipe", email="crew-admin@example.test", role="ops")
    admin_session = api.create_arclink_admin_session(
        conn,
        admin_id="admin_crew_recipe",
        session_id="asess_crew_recipe",
        mfa_verified=True,
    )
    admin_applied = api.admin_apply_user_crew_recipe_api(
        conn,
        session_id=admin_session["session_id"],
        session_token=admin_session["session_token"],
        csrf_token=admin_session["csrf_token"],
        user_id=prepared["user_id"],
        role="operator",
        mission="stabilize launch",
        treatment="coach",
        preset="Vanguard",
        capacity="sales",
    )
    expect(admin_applied.status == 200 and admin_applied.payload["recipe"]["preset"] == "Vanguard", str(admin_applied))
    active_count = conn.execute("SELECT COUNT(*) AS n FROM arclink_crew_recipes WHERE user_id = ? AND status = 'active'", (prepared["user_id"],)).fetchone()["n"]
    archived_count = conn.execute("SELECT COUNT(*) AS n FROM arclink_crew_recipes WHERE user_id = ? AND status = 'archived'", (prepared["user_id"],)).fetchone()["n"]
    expect(active_count == 1 and archived_count == 1, f"active={active_count} archived={archived_count}")
    audit = [row["action"] for row in conn.execute("SELECT action FROM arclink_audit_log").fetchall()]
    expect("crew_recipe_applied_by_operator" in audit, str(audit))
    print("PASS test_user_crew_recipe_api_applies_overlay_and_admin_on_behalf_is_audited")


def test_public_onboarding_api_rate_limits_and_reuses_shared_contract() -> None:
    control = load_module("arclink_control.py", "arclink_control_api_auth_onboarding_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_api_auth_onboarding_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_onboarding_test")
    conn = memory_db(control)
    stripe = adapters.FakeStripeClient()

    started = api.start_public_onboarding_api(
        conn,
        channel="discord",
        channel_identity="discord:api-user",
        email_hint="bot-api@example.test",
        selected_plan_id="sovereign",
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
        price_id="price_sovereign",
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
    control = load_module("arclink_control.py", "arclink_control_api_auth_invalid_onboarding_test")
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


def test_public_onboarding_cancel_does_not_regress_paid_session() -> None:
    control = load_module("arclink_control.py", "arclink_control_api_auth_onboarding_cancel_paid_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_onboarding_cancel_paid_test")
    conn = memory_db(control)

    started = api.start_public_onboarding_api(
        conn,
        channel="web",
        channel_identity="paid-cancel@example.test",
        email_hint="paid-cancel@example.test",
        selected_plan_id="starter",
    )
    session_id = started.payload["session"]["session_id"]
    cancel_token = started.payload["browser_cancel_token"]
    conn.execute(
        """
        UPDATE arclink_onboarding_sessions
        SET status = 'provisioning_ready', current_step = 'provisioning_requested', checkout_state = 'paid'
        WHERE session_id = ?
        """,
        (session_id,),
    )
    conn.commit()

    cancelled = api.cancel_onboarding_session_api(
        conn,
        onboarding_session_id=session_id,
        browser_cancel_token=cancel_token,
    )

    row = conn.execute("SELECT status, current_step, checkout_state FROM arclink_onboarding_sessions WHERE session_id = ?", (session_id,)).fetchone()
    event_count = conn.execute(
        "SELECT COUNT(*) AS n FROM arclink_onboarding_events WHERE session_id = ? AND event_type IN ('abandoned', 'payment_cancelled')",
        (session_id,),
    ).fetchone()["n"]
    expect(cancelled.status == 200, str(cancelled))
    expect(cancelled.payload["changed"] is False, str(cancelled.payload))
    expect(row["status"] == "provisioning_ready", str(dict(row)))
    expect(row["current_step"] == "provisioning_requested", str(dict(row)))
    expect(row["checkout_state"] == "paid", str(dict(row)))
    expect(event_count == 0, str(event_count))
    print("PASS test_public_onboarding_cancel_does_not_regress_paid_session")


def test_rate_limit_exceeded_rolls_back_internal_lock_transaction() -> None:
    control = load_module("arclink_control.py", "arclink_control_api_auth_rate_tx_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_rate_tx_test")
    conn = memory_db(control)

    api.check_arclink_rate_limit(conn, scope="test", subject="actor", limit=1, window_seconds=900)
    try:
        api.check_arclink_rate_limit(conn, scope="test", subject="actor", limit=1, window_seconds=900)
    except api.ArcLinkRateLimitError:
        pass
    else:
        raise AssertionError("expected rate limit")
    expect(not conn.in_transaction, "rate-limit failure left the connection inside a transaction")
    rows = conn.execute("SELECT COUNT(*) AS n FROM rate_limits WHERE scope = 'arclink:test' AND subject = 'actor'").fetchone()
    expect(rows["n"] == 1, str(dict(rows)))
    print("PASS test_rate_limit_exceeded_rolls_back_internal_lock_transaction")


def test_login_rate_limit_uses_immediate_transaction() -> None:
    control = load_module("arclink_control.py", "arclink_control_api_auth_login_rate_tx_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_login_rate_tx_test")
    conn = memory_db(control)
    traces: list[str] = []
    conn.set_trace_callback(traces.append)
    try:
        api._check_login_rate_limits(
            conn,
            scope="user_login",
            clean_email="locked@example.test",
            client_ip="198.51.100.10",
            account_limit=10,
            ip_limit=50,
        )
    finally:
        conn.set_trace_callback(None)
    expect(any(trace.strip().upper() == "BEGIN IMMEDIATE" for trace in traces), str(traces))
    expect(not conn.in_transaction, "login rate-limit transaction was not closed")
    print("PASS test_login_rate_limit_uses_immediate_transaction")


def test_admin_api_requires_csrf_reason_idempotency_and_mfa_ready_schema() -> None:
    control = load_module("arclink_control.py", "arclink_control_api_auth_admin_test")
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
        confirm=True,
    )
    expect(queued.status == 202 and queued.payload["action"]["status"] == "queued", str(queued))
    rendered = json.dumps(verified_admin, sort_keys=True) + json.dumps(queued.payload, sort_keys=True)
    expect("secret://arclink/admin/admin_api/totp" not in rendered, rendered)
    expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_audit_log").fetchone()["n"] == 1, "missing queued action audit")
    print("PASS test_admin_api_requires_csrf_reason_idempotency_and_mfa_ready_schema")


def test_admin_action_api_rate_limits_by_admin_and_target() -> None:
    control = load_module("arclink_control.py", "arclink_control_api_auth_admin_action_rate_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_api_auth_admin_action_rate_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_admin_action_rate_test")
    conn = memory_db(control)
    prepared = seed_paid_deployment(control, onboarding, conn)
    api.upsert_arclink_admin(conn, admin_id="admin_rate", email="rate@example.test", role="ops", role_scope={"deployments": ["*"]})
    api.enroll_arclink_admin_totp_factor(
        conn,
        admin_id="admin_rate",
        factor_id="totp_rate",
        secret_ref="secret://arclink/admin/admin_rate/totp",
    )
    api.verify_arclink_admin_totp_factor(conn, factor_id="totp_rate")
    session = api.create_arclink_admin_session(conn, admin_id="admin_rate", session_id="asess_rate", mfa_verified=True)
    for index in range(12):
        response = api.queue_admin_action_api(
            conn,
            session_id=session["session_id"],
            session_token=session["session_token"],
            csrf_token=session["csrf_token"],
            action_type="restart",
            target_kind="deployment",
            target_id=prepared["deployment_id"],
            reason=f"rate limit test {index}",
            idempotency_key=f"rate-{index}",
            confirm=True,
        )
        expect(response.status == 202, str(response))
    try:
        api.queue_admin_action_api(
            conn,
            session_id=session["session_id"],
            session_token=session["session_token"],
            csrf_token=session["csrf_token"],
            action_type="restart",
            target_kind="deployment",
            target_id=prepared["deployment_id"],
            reason="rate limit overflow",
            idempotency_key="rate-overflow",
            confirm=True,
        )
    except api.ArcLinkRateLimitError as exc:
        expect("rate limit exceeded" in str(exc), str(exc))
    else:
        raise AssertionError("expected admin target rate limit to fail")
    scopes = {
        row["scope"]
        for row in conn.execute("SELECT DISTINCT scope FROM rate_limits WHERE scope LIKE 'arclink:admin_action:%'")
    }
    expect(scopes == {"arclink:admin_action:admin", "arclink:admin_action:target"}, str(scopes))
    print("PASS test_admin_action_api_rate_limits_by_admin_and_target")


def test_admin_passwords_are_hashed_and_required_for_login() -> None:
    control = load_module("arclink_control.py", "arclink_control_api_auth_admin_password_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_admin_password_test")
    conn = memory_db(control)
    api.upsert_arclink_admin(
        conn,
        admin_id="admin_password",
        email="admin-password@example.test",
        role="owner",
        password="admin-test-password",
    )
    stored = conn.execute("SELECT password_hash FROM arclink_admins WHERE admin_id = 'admin_password'").fetchone()
    expect("admin-test-password" not in str(stored["password_hash"]), str(stored["password_hash"]))
    expect(api.verify_arclink_admin_password("admin-test-password", str(stored["password_hash"])), str(stored["password_hash"]))
    try:
        api.create_arclink_admin_login_session_api(
            conn,
            email="admin-password@example.test",
            password="wrong-password",
            login_subject="admin-password@example.test",
        )
    except api.ArcLinkApiAuthError as exc:
        expect("Invalid ArcLink admin credentials" in str(exc), str(exc))
    else:
        raise AssertionError("expected wrong admin password to fail")
    response = api.create_arclink_admin_login_session_api(
        conn,
        email="admin-password@example.test",
        password="admin-test-password",
        login_subject="admin-password@example.test",
    )
    expect(response.status == 201 and response.payload["session"]["admin_id"] == "admin_password", str(response))
    updated = api.set_arclink_admin_password(
        conn,
        email="admin-password@example.test",
        password="admin-test-password-rotated",
    )
    expect(updated["password"]["configured"], str(updated))
    print("PASS test_admin_passwords_are_hashed_and_required_for_login")


def test_user_passwords_are_hashed_and_required_for_login() -> None:
    control = load_module("arclink_control.py", "arclink_control_api_auth_user_password_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_api_auth_user_password_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_user_password_test")
    conn = memory_db(control)
    prepared = seed_paid_deployment(control, onboarding, conn)
    api.set_arclink_user_password(conn, user_id=prepared["user_id"], password="user-test-password")
    stored = conn.execute("SELECT password_hash FROM arclink_users WHERE user_id = ?", (prepared["user_id"],)).fetchone()
    expect("user-test-password" not in str(stored["password_hash"]), str(stored["password_hash"]))
    expect(api.verify_arclink_password("user-test-password", str(stored["password_hash"])), str(stored["password_hash"]))
    for password in ("", "wrong-password"):
        try:
            api.create_arclink_user_login_session_api(
                conn,
                email="api-user@example.test",
                password=password,
                login_subject="api-user@example.test",
            )
        except api.ArcLinkApiAuthError as exc:
            expect(str(exc) == "Invalid ArcLink user credentials", str(exc))
        else:
            raise AssertionError("expected wrong user password to fail")
    response = api.create_arclink_user_login_session_api(
        conn,
        email="api-user@example.test",
        password="user-test-password",
        login_subject="api-user@example.test",
    )
    expect(response.status == 201 and response.payload["session"]["user_id"] == prepared["user_id"], str(response))
    print("PASS test_user_passwords_are_hashed_and_required_for_login")


def test_login_rate_limit_uses_server_derived_account_not_client_subject() -> None:
    control = load_module("arclink_control.py", "arclink_control_api_auth_login_subject_rate_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_api_auth_login_subject_rate_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_login_subject_rate_test")
    conn = memory_db(control)
    prepared = seed_paid_deployment(control, onboarding, conn)
    api.set_arclink_user_password(conn, user_id=prepared["user_id"], password="user-test-password")
    for index in range(10):
        try:
            api.create_arclink_user_login_session_api(
                conn,
                email="api-user@example.test",
                password="wrong-password",
                login_subject=f"attacker-controlled-alias-{index}@example.test",
                client_ip="198.51.100.10",
            )
        except api.ArcLinkApiAuthError as exc:
            expect(str(exc) == "Invalid ArcLink user credentials", str(exc))
        else:
            raise AssertionError("expected wrong user password to fail")
    try:
        api.create_arclink_user_login_session_api(
            conn,
            email="api-user@example.test",
            password="wrong-password",
            login_subject="fresh-attacker-controlled-alias@example.test",
            client_ip="198.51.100.10",
        )
    except api.ArcLinkRateLimitError as exc:
        expect("rate limit exceeded" in str(exc), str(exc))
    else:
        raise AssertionError("expected account-keyed login throttle to ignore caller login_subject changes")
    rows = [
        dict(row)
        for row in conn.execute(
            "SELECT scope, subject FROM rate_limits WHERE scope LIKE 'arclink:user_login:%' ORDER BY scope, subject"
        ).fetchall()
    ]
    account_subjects = {row["subject"] for row in rows if row["scope"] == "arclink:user_login:account"}
    expect(account_subjects == {"api-user@example.test"}, str(rows))
    rendered = json.dumps(rows, sort_keys=True)
    expect("attacker-controlled-alias" not in rendered, rendered)
    print("PASS test_login_rate_limit_uses_server_derived_account_not_client_subject")


def test_api_transport_helpers_extract_credentials_and_shape_safe_errors() -> None:
    control = load_module("arclink_control.py", "arclink_control_api_auth_transport_test")
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
    browser_creds = api.extract_arclink_browser_session_credentials({"Cookie": cookie}, session_kind="user")
    expect(browser_creds == header_creds, str(browser_creds))
    try:
        api.extract_arclink_browser_session_credentials(
            {
                "Authorization": f"Bearer {session['session_token']}",
                "X-ArcLink-Session-Id": session["session_id"],
            },
            session_kind="user",
        )
    except api.ArcLinkApiAuthError as exc:
        expect("browser session cookies" in str(exc), str(exc))
    else:
        raise AssertionError("browser session extraction should reject header credentials")
    try:
        api.extract_arclink_csrf_token({"Cookie": cookie}, session_kind="user")
    except api.ArcLinkApiAuthError as exc:
        expect("CSRF header" in str(exc), str(exc))
    else:
        raise AssertionError("CSRF extraction should require the explicit header, not the cookie")

    for bad_kind in ("", "root"):
        try:
            api.extract_arclink_session_credentials({"Authorization": "Bearer example", "X-ArcLink-Session-Id": "sess"}, session_kind=bad_kind)
        except api.ArcLinkApiAuthError as exc:
            expect("session kind" in str(exc), str(exc))
        else:
            raise AssertionError(f"expected unsupported session kind {bad_kind!r} to fail")

    domain_error = api.arclink_api_error_response(api.ArcLinkApiAuthError("ArcLink session token mismatch"), request_id="req_1")
    generic_error = api.arclink_api_error_response(RuntimeError("internal database detail should stay private"), request_id="req_2")
    expect(domain_error.status == 401 and domain_error.payload["error"] == "unauthorized", str(domain_error))
    expect(generic_error.status == 400 and "internal database detail" not in json.dumps(generic_error.payload), str(generic_error))
    expect(generic_error.payload["request_id"] == "req_2", str(generic_error))
    print("PASS test_api_transport_helpers_extract_credentials_and_shape_safe_errors")


def test_session_hashes_upgrade_legacy_sha256_after_successful_verification() -> None:
    control = load_module("arclink_control.py", "arclink_control_api_auth_hash_migration_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_api_auth_hash_migration_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_hash_migration_test")
    conn = memory_db(control)
    prepared = seed_paid_deployment(control, onboarding, conn)
    session = api.create_arclink_user_session(conn, user_id=prepared["user_id"], session_id="usess_legacy_hash")
    legacy_session_hash = api._hash_token(session["session_token"])
    legacy_csrf_hash = api._hash_token(session["csrf_token"])
    conn.execute(
        "UPDATE arclink_user_sessions SET session_token_hash = ?, csrf_token_hash = ? WHERE session_id = ?",
        (legacy_session_hash, legacy_csrf_hash, session["session_id"]),
    )
    conn.commit()

    authenticated = api.authenticate_arclink_user_session(
        conn,
        session_id=session["session_id"],
        session_token=session["session_token"],
    )
    expect(authenticated["session_id"] == session["session_id"], str(authenticated))
    api.require_arclink_csrf(
        conn,
        session_id=session["session_id"],
        csrf_token=session["csrf_token"],
        session_kind="user",
    )
    stored = conn.execute(
        "SELECT session_token_hash, csrf_token_hash FROM arclink_user_sessions WHERE session_id = ?",
        (session["session_id"],),
    ).fetchone()
    expect(str(stored["session_token_hash"]).startswith("hmac_sha256_v1$"), str(dict(stored)))
    expect(str(stored["csrf_token_hash"]).startswith("hmac_sha256_v1$"), str(dict(stored)))
    expect(str(stored["session_token_hash"]) != legacy_session_hash, str(dict(stored)))
    expect(str(stored["csrf_token_hash"]) != legacy_csrf_hash, str(dict(stored)))
    print("PASS test_session_hashes_upgrade_legacy_sha256_after_successful_verification")


def test_session_kind_prefixes_are_enforced() -> None:
    control = load_module("arclink_control.py", "arclink_control_api_auth_prefix_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_api_auth_prefix_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_prefix_test")
    conn = memory_db(control)
    prepared = seed_paid_deployment(control, onboarding, conn)
    user_session = api.create_arclink_user_session(conn, user_id=prepared["user_id"], session_id="usess_prefix_user")
    api.upsert_arclink_admin(conn, admin_id="admin_prefix", email="prefix-admin@example.test", role="ops")
    admin_session = api.create_arclink_admin_session(conn, admin_id="admin_prefix", session_id="asess_prefix_admin")

    for call, message in (
        (
            lambda: api.authenticate_arclink_user_session(
                conn,
                session_id=admin_session["session_id"],
                session_token=admin_session["session_token"],
            ),
            "user auth accepted admin-prefixed session id",
        ),
        (
            lambda: api.authenticate_arclink_admin_session(
                conn,
                session_id=user_session["session_id"],
                session_token=user_session["session_token"],
            ),
            "admin auth accepted user-prefixed session id",
        ),
        (
            lambda: api.create_arclink_user_session(conn, user_id=prepared["user_id"], session_id="sess_bad"),
            "user session creation accepted bad prefix",
        ),
    ):
        try:
            call()
        except api.ArcLinkApiAuthError as exc:
            expect("prefix" in str(exc), str(exc))
        else:
            raise AssertionError(message)
    print("PASS test_session_kind_prefixes_are_enforced")


def test_session_auth_failures_use_generic_error_detail() -> None:
    control = load_module("arclink_control.py", "arclink_control_api_auth_generic_session_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_api_auth_generic_session_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_generic_session_test")
    conn = memory_db(control)
    prepared = seed_paid_deployment(control, onboarding, conn)
    session = api.create_arclink_user_session(conn, user_id=prepared["user_id"], session_id="usess_generic_auth")

    messages = []
    for call in (
        lambda: api.authenticate_arclink_user_session(
            conn,
            session_id="usess_missing_generic",
            session_token=session["session_token"],
        ),
        lambda: api.authenticate_arclink_user_session(
            conn,
            session_id=session["session_id"],
            session_token="wrong-token",
        ),
    ):
        try:
            call()
        except api.ArcLinkApiAuthError as exc:
            messages.append(str(exc))
        else:
            raise AssertionError("expected generic session auth failure")
    conn.execute(
        "UPDATE arclink_user_sessions SET status = 'revoked', revoked_at = '2026-05-11T00:00:00+00:00' WHERE session_id = ?",
        (session["session_id"],),
    )
    conn.commit()
    try:
        api.authenticate_arclink_user_session(
            conn,
            session_id=session["session_id"],
            session_token=session["session_token"],
        )
    except api.ArcLinkApiAuthError as exc:
        messages.append(str(exc))
    else:
        raise AssertionError("expected revoked session auth failure")
    expect(set(messages) == {"ArcLink user session authentication failed"}, str(messages))
    print("PASS test_session_auth_failures_use_generic_error_detail")


def test_session_hash_pepper_fails_closed_when_base_domain_unset_or_blank() -> None:
    api = load_module("arclink_api_auth.py", "arclink_api_auth_pepper_blank_domain_test")
    saved = save_session_hash_env()
    try:
        os.environ["ARCLINK_CONFIG_FILE"] = os.devnull
        os.environ.pop("ARCLINK_SESSION_HASH_PEPPER", None)
        os.environ.pop("ARCLINK_SESSION_HASH_PEPPER_REQUIRED", None)
        for label, value in (("unset", None), ("blank", "")):
            if value is None:
                os.environ.pop("ARCLINK_BASE_DOMAIN", None)
            else:
                os.environ["ARCLINK_BASE_DOMAIN"] = value
            try:
                api._session_hash_pepper()
            except api.ArcLinkApiAuthError as exc:
                expect("pepper" in str(exc), f"{label}: {exc}")
            else:
                raise AssertionError(f"expected {label} base domain without pepper to fail closed")
    finally:
        restore_env(saved)
    print("PASS test_session_hash_pepper_fails_closed_when_base_domain_unset_or_blank")


def test_session_hash_pepper_dev_fallback_requires_explicit_local_domain() -> None:
    api = load_module("arclink_api_auth.py", "arclink_api_auth_pepper_local_domain_test")
    saved = save_session_hash_env()
    try:
        os.environ["ARCLINK_CONFIG_FILE"] = os.devnull
        os.environ.pop("ARCLINK_SESSION_HASH_PEPPER", None)
        os.environ.pop("ARCLINK_SESSION_HASH_PEPPER_REQUIRED", None)
        for domain in ("localhost", "127.0.0.1", "::1", "example.test", "pod.example.test"):
            os.environ["ARCLINK_BASE_DOMAIN"] = domain
            expect(
                api._session_hash_pepper() == "arclink-dev-session-hash-pepper",
                f"expected explicit local/test domain {domain} to use dev pepper",
            )
        os.environ["ARCLINK_SESSION_HASH_PEPPER_REQUIRED"] = "1"
        os.environ["ARCLINK_BASE_DOMAIN"] = "localhost"
        try:
            api._session_hash_pepper()
        except api.ArcLinkApiAuthError as exc:
            expect("pepper" in str(exc), str(exc))
        else:
            raise AssertionError("expected required flag to reject dev pepper fallback")
    finally:
        restore_env(saved)
    print("PASS test_session_hash_pepper_dev_fallback_requires_explicit_local_domain")


def test_production_session_creation_requires_pepper() -> None:
    control = load_module("arclink_control.py", "arclink_control_api_auth_pepper_required_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_api_auth_pepper_required_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_pepper_required_test")
    conn = memory_db(control)
    prepared = seed_paid_deployment(control, onboarding, conn)
    saved = save_session_hash_env()
    try:
        os.environ["ARCLINK_CONFIG_FILE"] = os.devnull
        os.environ["ARCLINK_BASE_DOMAIN"] = "arclink.online"
        os.environ.pop("ARCLINK_SESSION_HASH_PEPPER", None)
        os.environ.pop("ARCLINK_SESSION_HASH_PEPPER_REQUIRED", None)
        try:
            api.create_arclink_user_session(conn, user_id=prepared["user_id"], session_id="usess_no_pepper")
        except api.ArcLinkApiAuthError as exc:
            expect("pepper" in str(exc), str(exc))
        else:
            raise AssertionError("expected production session creation without pepper to fail")
        os.environ["ARCLINK_SESSION_HASH_PEPPER"] = "test-pepper"
        session = api.create_arclink_user_session(conn, user_id=prepared["user_id"], session_id="usess_with_pepper")
        expect(session["session_id"] == "usess_with_pepper", str(session))
    finally:
        restore_env(saved)
    print("PASS test_production_session_creation_requires_pepper")


def test_session_hash_pepper_reads_generated_config_file() -> None:
    api = load_module("arclink_api_auth.py", "arclink_api_auth_pepper_config_file_test")
    saved = {
        key: os.environ.get(key)
        for key in (
            "ARCLINK_CONFIG_FILE",
            "ARCLINK_BASE_DOMAIN",
            "ARCLINK_SESSION_HASH_PEPPER",
            "ARCLINK_SESSION_HASH_PEPPER_REQUIRED",
        )
    }
    try:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "arclink.env"
            config_path.write_text(
                "\n".join(
                    [
                        "ARCLINK_BASE_DOMAIN=arclink.online",
                        "ARCLINK_SESSION_HASH_PEPPER=config-file-pepper",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
            os.environ.pop("ARCLINK_BASE_DOMAIN", None)
            os.environ.pop("ARCLINK_SESSION_HASH_PEPPER", None)
            os.environ.pop("ARCLINK_SESSION_HASH_PEPPER_REQUIRED", None)
            expect(
                api._session_hash_pepper() == "config-file-pepper",
                "session pepper should read generated config file",
            )
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    print("PASS test_session_hash_pepper_reads_generated_config_file")


def test_revoke_session_rejects_invalid_kind_before_update_or_audit() -> None:
    control = load_module("arclink_control.py", "arclink_control_api_auth_revoke_kind_test")
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
    control = load_module("arclink_control.py", "arclink_control_api_auth_missing_revoke_test")
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


def test_staged_revoke_requires_explicit_transaction() -> None:
    control = load_module("arclink_control.py", "arclink_control_api_auth_staged_revoke_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_api_auth_staged_revoke_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_staged_revoke_test")
    conn = memory_db(control)
    prepared = seed_paid_deployment(control, onboarding, conn)
    session = api.create_arclink_user_session(conn, user_id=prepared["user_id"], session_id="usess_staged_revoke")

    try:
        api.revoke_arclink_session(
            conn,
            session_id=session["session_id"],
            session_kind="user",
            actor_id="admin_api",
            reason="staged revoke without transaction",
            commit=False,
        )
    except api.ArcLinkApiAuthError as exc:
        expect("explicit transaction" in str(exc), str(exc))
    else:
        raise AssertionError("expected staged revoke without an explicit transaction to fail")

    row = conn.execute("SELECT status FROM arclink_user_sessions WHERE session_id = ?", (session["session_id"],)).fetchone()
    expect(row["status"] == "active", str(dict(row)))

    conn.execute("BEGIN IMMEDIATE")
    revoked = api.revoke_arclink_session(
        conn,
        session_id=session["session_id"],
        session_kind="user",
        actor_id="admin_api",
        reason="staged revoke with transaction",
        commit=False,
    )
    expect(revoked["status"] == "revoked", str(revoked))
    conn.rollback()
    row = conn.execute("SELECT status FROM arclink_user_sessions WHERE session_id = ?", (session["session_id"],)).fetchone()
    expect(row["status"] == "active", str(dict(row)))
    print("PASS test_staged_revoke_requires_explicit_transaction")


def test_single_operator_policy_rejects_second_active_owner() -> None:
    control = load_module("arclink_control.py", "arclink_control_api_auth_single_operator_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_single_operator_test")
    conn = memory_db(control)
    first = api.upsert_arclink_admin(conn, admin_id="owner_one", email="one@example.test", role="owner")
    expect(first["role"] == "owner", str(first))
    api.upsert_arclink_admin(conn, admin_id="ops_one", email="ops@example.test", role="ops")
    try:
        api.upsert_arclink_admin(conn, admin_id="owner_two", email="two@example.test", role="owner")
    except api.ArcLinkApiAuthError as exc:
        expect("single-operator" in str(exc), str(exc))
    else:
        raise AssertionError("expected second active owner to fail")
    inactive = api.upsert_arclink_admin(
        conn,
        admin_id="owner_two",
        email="two@example.test",
        role="owner",
        status="inactive",
    )
    expect(inactive["status"] == "inactive", str(inactive))
    owners = conn.execute("SELECT COUNT(*) AS n FROM arclink_admins WHERE role = 'owner' AND status = 'active'").fetchone()["n"]
    expect(owners == 1, f"expected one active owner, got {owners}")
    print("PASS test_single_operator_policy_rejects_second_active_owner")


def test_proof_token_hashes_use_hmac_and_accept_legacy() -> None:
    api = load_module("arclink_api_auth.py", "arclink_api_auth_proof_hash_test")
    import secrets as _secrets
    token = _secrets.token_urlsafe(32)
    peppered = api._hash_proof_token(token)
    expect(peppered.startswith("hmac_sha256_v1$"), f"proof hash should be peppered: {peppered}")
    expect(api._verify_proof_token_hash(token, peppered), "peppered proof hash should verify")
    legacy = api._hash_token(token)
    expect(not legacy.startswith("hmac_sha256_v1$"), f"legacy hash should be plain SHA-256: {legacy}")
    expect(api._verify_proof_token_hash(token, legacy), "legacy SHA-256 proof hash should still verify")
    expect(not api._verify_proof_token_hash(token, legacy, allow_legacy=False), "strict proof verification should reject legacy SHA-256")
    expect(not api._verify_proof_token_hash("wrong_token", peppered), "wrong token should not verify (peppered)")
    expect(not api._verify_proof_token_hash("wrong_token", legacy), "wrong token should not verify (legacy)")
    expect(not api._verify_proof_token_hash(token, ""), "empty stored hash should not verify")
    print("PASS test_proof_token_hashes_use_hmac_and_accept_legacy")


def test_share_notifications_escape_cross_tenant_markdown_and_links() -> None:
    api = load_module("arclink_api_auth.py", "arclink_api_auth_share_label_escape_test")

    # An owner-supplied display name carrying a markdown link, a code span, and a
    # mention must be neutralized so it cannot render cross-tenant into the
    # recipient's (or owner's) notification reply.
    hostile = "[click me](https://evil.example) `code` @everyone <@&role>"
    safe = api._safe_share_label(hostile)
    for metachar in ("[", "]", "(", ")", "`", "@", "<", ">"):
        expect(metachar not in safe, f"{metachar!r} still present in {safe!r}")
    expect("click me" in safe and "code" in safe, safe)

    # The recipient notification builder must emit the escaped label/path, never
    # the raw metacharacters, so a markdown link cannot be smuggled cross-tenant.
    grant = {
        "recipient_user_id": "arcusr_recipient",
        "grant_id": "share_test_grant",
        "owner_user_id": "arcusr_owner",
        "display_name": "[steal](https://evil.example)",
        "resource_kind": "drive",
        "resource_root": "vault",
        "resource_path": "/Projects/<@&everyone>",
    }
    captured: dict[str, object] = {}

    def fake_channel(conn, user_id):
        return {"available": True, "channel": "telegram", "target_id": "tg:recipient"}

    def fake_queue_notification(conn, **kwargs):
        captured["message"] = kwargs.get("message")
        return "notif_test"

    def fake_event(conn, **kwargs):
        return None

    old_channel = api._share_public_channel_for_user
    old_queue = api.queue_notification
    old_event = api.append_arclink_event
    api._share_public_channel_for_user = fake_channel
    api.queue_notification = fake_queue_notification
    api.append_arclink_event = fake_event
    try:
        result = api.queue_share_grant_recipient_notification(None, grant=grant)
    finally:
        api._share_public_channel_for_user = old_channel
        api.queue_notification = old_queue
        api.append_arclink_event = old_event

    expect(result.get("queued") is True, str(result))
    message = str(captured.get("message") or "")
    expect("[steal]" not in message and "(https://evil.example)" not in message, message)
    expect("<@&everyone>" not in message, message)
    print("PASS test_share_notifications_escape_cross_tenant_markdown_and_links")


def test_clean_share_path_rejects_markdown_metacharacters() -> None:
    api = load_module("arclink_api_auth.py", "arclink_api_auth_clean_share_path_test")

    # Benign paths still resolve -- including normal path characters such as the
    # underscore, which is NOT a markdown injection vector and must keep working
    # so legitimate paths (e.g. ``Q1_notes``) and the grants they materialize do
    # not break.
    expect(api._clean_share_path("Projects/Briefs") == "/Projects/Briefs", "benign path should pass")
    expect(api._clean_share_path("Projects/Q1_notes") == "/Projects/Q1_notes", "underscore path should pass")
    expect(api._clean_share_path("Projects/under_score") == "/Projects/under_score", "underscore path should pass")

    # Each TRUE markdown/mention metacharacter in a path segment is rejected so a
    # malicious resource_path cannot inject markup into share notifications.
    for hostile in (
        "Projects/[link](evil)",
        "Projects/`code`",
        "Projects/@everyone",
        "Projects/<@&role>",
        "Projects/bold*name",
        "Projects/tilde~name",
        "Projects/pipe|name",
    ):
        try:
            api._clean_share_path(hostile)
        except api.ArcLinkApiAuthError:
            continue
        raise AssertionError(f"expected rejection for {hostile!r}")

    # Traversal and secret guards remain intact.
    for blocked in ("../etc", "vault/.ssh", "x/.env"):
        try:
            api._clean_share_path(blocked)
        except api.ArcLinkApiAuthError:
            continue
        raise AssertionError(f"expected rejection for {blocked!r}")
    print("PASS test_clean_share_path_rejects_markdown_metacharacters")


def _setup_share_projection_fixture(control, api):
    """Build owner/recipient users + deployments with on-disk state roots so
    _materialize_share_projection can project a real living-symlink folder share."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    control.ensure_schema(conn)
    tmp = Path(tempfile.mkdtemp())
    owner_root = tmp / "owner"
    (owner_root / "vault" / "Projects").mkdir(parents=True)
    (owner_root / "vault" / "Projects" / "notes.md").write_text("hello fleet\n", encoding="utf-8")
    rcp_root = tmp / "rcp"
    (rcp_root / "vault").mkdir(parents=True)
    (rcp_root / "linked-resources").mkdir(parents=True)
    now = control.utc_now_iso()
    for uid in ("user_owner", "user_rcp"):
        conn.execute(
            "INSERT INTO arclink_users (user_id, email, status, created_at, updated_at) VALUES (?, ?, 'active', ?, ?)",
            (uid, uid + "@example.test", now, now),
        )

    def _dep(dep_id: str, uid: str, root: Path) -> None:
        metadata = {
            "state_roots": {
                "vault": str(root / "vault"),
                "code_workspace": str(root / "workspace"),
                "linked_resources": str(root / "linked-resources"),
            }
        }
        conn.execute(
            "INSERT INTO arclink_deployments (deployment_id, user_id, prefix, status, metadata_json, created_at, updated_at) "
            "VALUES (?, ?, ?, 'active', ?, ?, ?)",
            (dep_id, uid, dep_id, json.dumps(metadata), now, now),
        )

    _dep("dep_owner", "user_owner", owner_root)
    _dep("dep_rcp", "user_rcp", rcp_root)
    conn.commit()
    grant = {
        "grant_id": "share_proj_test",
        "owner_user_id": "user_owner",
        "recipient_user_id": "user_rcp",
        "resource_kind": "drive",
        "resource_root": "vault",
        "resource_path": "/Projects",
        "display_name": "Projects",
        "metadata_json": json.dumps(
            {"owner_deployment_id": "dep_owner", "recipient_deployment_id": "dep_rcp"}
        ),
    }
    return conn, owner_root, rcp_root, grant


def test_default_drive_share_grant_is_read_write() -> None:
    api = load_module("arclink_api_auth.py", "arclink_api_auth_share_default_mode_test")

    # A drive/code share grant created without an explicit access_mode must
    # default to read_write (an editable shared folder), while non-folder kinds
    # (notion/pod_comms) keep the read-only default.
    expect(api._clean_share_access_mode("") == "read_write", "blank mode should default read_write")
    expect(
        api._clean_share_access_mode("", default="read_write") == "read_write",
        "drive/code default should be read_write",
    )
    # An explicit choice still wins over the default in both directions.
    expect(api._clean_share_access_mode("read", default="read_write") == "read", "explicit read must win")
    expect(api._clean_share_access_mode("read_write", default="read") == "read_write", "explicit read_write must win")

    # _share_projection_read_only is the gate: read_write drive/code folders are
    # writable; everything else (explicit read, or non-folder kinds) is read-only.
    expect(api._share_projection_read_only("read_write", "drive") is False, "read_write drive must be writable")
    expect(api._share_projection_read_only("read_write", "code") is False, "read_write code must be writable")
    expect(api._share_projection_read_only("read", "drive") is True, "explicit read drive must be read-only")
    expect(api._share_projection_read_only("read_write", "notion") is True, "non-folder read_write stays read-only")
    expect(api._share_projection_read_only("read_write", "pod_comms") is True, "pod_comms stays read-only")
    print("PASS test_default_drive_share_grant_is_read_write")


def test_read_write_share_projection_is_writable_not_chmod_read_only() -> None:
    control = load_module("arclink_control.py", "arclink_control_share_rw_proj_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_share_rw_proj_test")
    conn, owner_root, rcp_root, grant = _setup_share_projection_fixture(control, api)

    # Grant carries NO explicit access_mode -> the materialize default decides.
    # With the read-write default, a folder share projects as writable.
    metadata = api._materialize_share_projection(conn, grant=grant, now=control.utc_now_iso())
    projection = metadata["projection"]
    expect(projection["status"] == "materialized", str(projection))
    expect(projection["read_only"] is False, str(projection))
    expect(projection["access_mode"] == "read_write", str(projection))
    expect(projection["resource_kind"] == "directory", str(projection))

    # The manifest the Drive plugin reads must mark the entry read_write/not read_only.
    manifest = json.loads(
        (rcp_root / "linked-resources" / ".arclink-linked-resources.json").read_text(encoding="utf-8")
    )
    entries = manifest["entries"]
    expect(len(entries) == 1, str(entries))
    slug, entry = next(iter(entries.items()))
    expect(entry["read_only"] is False, str(entry))
    expect(entry["access_mode"] == "read_write", str(entry))

    # The projected folder is a living symlink and its tree must NOT be chmod'd
    # read-only: a recipient edit lands on the owner's real file.
    projection_dir = rcp_root / "linked-resources" / slug
    expect(projection_dir.is_symlink(), "directory share should project as a living symlink")
    projected_note = projection_dir / "notes.md"
    projected_note.write_text("# recipient edit\n", encoding="utf-8")
    expect(
        "recipient edit" in (owner_root / "vault" / "Projects" / "notes.md").read_text(encoding="utf-8"),
        "read_write projection must be writable through to the owner source",
    )
    print("PASS test_read_write_share_projection_is_writable_not_chmod_read_only")


def test_explicit_read_only_share_projection_stays_read_only() -> None:
    control = load_module("arclink_control.py", "arclink_control_share_ro_proj_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_share_ro_proj_test")
    conn, _owner_root, rcp_root, grant = _setup_share_projection_fixture(control, api)

    # When the captain EXPLICITLY chooses access_mode="read", the projection must
    # stay read-only even though the default is now read_write.
    grant["access_mode"] = "read"
    metadata = api._materialize_share_projection(conn, grant=grant, now=control.utc_now_iso())
    projection = metadata["projection"]
    expect(projection["status"] == "materialized", str(projection))
    expect(projection["read_only"] is True, str(projection))
    expect(projection["access_mode"] == "read", str(projection))

    manifest = json.loads(
        (rcp_root / "linked-resources" / ".arclink-linked-resources.json").read_text(encoding="utf-8")
    )
    entry = next(iter(manifest["entries"].values()))
    expect(entry["read_only"] is True, str(entry))
    expect(entry["access_mode"] == "read", str(entry))
    # The Drive plugin gate must treat this entry as non-writable.
    expect(api is not None, "module loaded")
    print("PASS test_explicit_read_only_share_projection_stays_read_only")


def main() -> int:
    test_sessions_store_hashes_and_user_api_is_scoped_to_principal()
    test_user_agent_identity_update_requires_session_and_csrf()
    test_provider_state_demotes_spoofed_unlimited_policy_from_operator_settings()
    test_provider_state_available_cents_subtracts_open_reservations()
    test_user_crew_recipe_api_applies_overlay_and_admin_on_behalf_is_audited()
    test_public_onboarding_api_rate_limits_and_reuses_shared_contract()
    test_public_onboarding_api_rejects_invalid_channel_before_rate_limit()
    test_public_onboarding_cancel_does_not_regress_paid_session()
    test_rate_limit_exceeded_rolls_back_internal_lock_transaction()
    test_login_rate_limit_uses_immediate_transaction()
    test_admin_api_requires_csrf_reason_idempotency_and_mfa_ready_schema()
    test_admin_action_api_rate_limits_by_admin_and_target()
    test_admin_passwords_are_hashed_and_required_for_login()
    test_user_passwords_are_hashed_and_required_for_login()
    test_login_rate_limit_uses_server_derived_account_not_client_subject()
    test_api_transport_helpers_extract_credentials_and_shape_safe_errors()
    test_session_hashes_upgrade_legacy_sha256_after_successful_verification()
    test_session_kind_prefixes_are_enforced()
    test_session_auth_failures_use_generic_error_detail()
    test_session_hash_pepper_fails_closed_when_base_domain_unset_or_blank()
    test_session_hash_pepper_dev_fallback_requires_explicit_local_domain()
    test_production_session_creation_requires_pepper()
    test_session_hash_pepper_reads_generated_config_file()
    test_revoke_session_rejects_invalid_kind_before_update_or_audit()
    test_revoke_session_rejects_missing_user_and_admin_before_update_or_audit()
    test_staged_revoke_requires_explicit_transaction()
    test_single_operator_policy_rejects_second_active_owner()
    test_proof_token_hashes_use_hmac_and_accept_legacy()
    test_share_notifications_escape_cross_tenant_markdown_and_links()
    test_clean_share_path_rejects_markdown_metacharacters()
    test_default_drive_share_grant_is_read_write()
    test_read_write_share_projection_is_writable_not_chmod_read_only()
    test_explicit_read_only_share_projection_stays_read_only()
    print("PASS all 33 ArcLink API/auth tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
