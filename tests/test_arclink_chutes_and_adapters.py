#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from typing import Any, Mapping

from arclink_test_helpers import expect, load_module, memory_db


class FixtureHttpClient:
    def __init__(self, payload: Mapping[str, Any]) -> None:
        self.payload = payload
        self.headers: Mapping[str, str] = {}

    def get_json(self, path: str, *, headers: Mapping[str, str] | None = None) -> Mapping[str, Any]:
        expect(path == "/models", path)
        self.headers = dict(headers or {})
        return self.payload


CATALOG = {
    "data": [
        {
            "id": "moonshotai/Kimi-K2.6-TEE",
            "capabilities": {
                "tools": True,
                "reasoning": True,
                "structured_outputs": True,
                "confidential_compute": True,
            },
        },
        {
            "id": "basic-model",
            "capabilities": {
                "tools": True,
                "reasoning": False,
                "structured_outputs": True,
                "confidential_compute": False,
            },
        },
    ]
}


def test_chutes_catalog_parses_and_validates_default_model() -> None:
    mod = load_module("arclink_chutes.py", "arclink_chutes_catalog_test")
    http = FixtureHttpClient(CATALOG)
    client = mod.ChutesCatalogClient(http)
    models = client.list_models(api_key="test_key")
    expect(http.headers == {"X-API-Key": "test_key"}, str(http.headers))
    model = mod.validate_default_chutes_model(models, env={})
    expect(model.model_id == "moonshotai/Kimi-K2.6-TEE", model.model_id)
    print("PASS test_chutes_catalog_parses_and_validates_default_model")


def test_chutes_catalog_fails_for_missing_or_unsupported_default() -> None:
    mod = load_module("arclink_chutes.py", "arclink_chutes_failure_test")
    models = mod.parse_chutes_models(CATALOG)
    try:
        mod.validate_default_chutes_model(models, env={"ARCLINK_CHUTES_DEFAULT_MODEL": "missing-model"})
    except mod.ChutesCatalogError as exc:
        expect("not in catalog" in str(exc), str(exc))
    else:
        raise AssertionError("expected missing model to fail")
    try:
        mod.validate_default_chutes_model(models, env={"ARCLINK_CHUTES_DEFAULT_MODEL": "basic-model"})
    except mod.ChutesCatalogError as exc:
        expect("reasoning" in str(exc) and "confidential_compute" in str(exc), str(exc))
    else:
        raise AssertionError("expected unsupported model to fail")
    print("PASS test_chutes_catalog_fails_for_missing_or_unsupported_default")


def test_fake_chutes_key_manager_uses_secret_references() -> None:
    mod = load_module("arclink_chutes.py", "arclink_chutes_key_manager_test")
    manager = mod.FakeChutesKeyManager()
    record = manager.create_key("dep_1", label="test")
    expect(record["secret_ref"] == "secret://arclink/chutes/dep_1", str(record))
    expect("api" not in json.dumps(record).lower(), str(record))
    revoked = manager.revoke_key(record["key_id"])
    expect(revoked["status"] == "revoked", str(revoked))
    print("PASS test_fake_chutes_key_manager_uses_secret_references")


def test_fake_stripe_webhook_and_sessions() -> None:
    mod = load_module("arclink_adapters.py", "arclink_adapters_stripe_test")
    stripe = mod.FakeStripeClient()
    session = stripe.create_checkout_session(
        user_id="user_1",
        price_id="price_test",
        success_url="https://example.test/success",
        cancel_url="https://example.test/cancel",
    )
    expect(session["url"].startswith("https://stripe.test/checkout/"), str(session))
    payload = json.dumps({"id": "evt_test", "type": "checkout.session.completed"})
    signature = mod.sign_stripe_webhook(payload, "whsec_test", timestamp=int(time.time()))
    event = mod.verify_stripe_webhook(payload, signature, "whsec_test")
    expect(event["type"] == "checkout.session.completed", str(event))
    print("PASS test_fake_stripe_webhook_and_sessions")


def test_stripe_client_resolver_returns_fake_without_key_and_rejects_blank() -> None:
    mod = load_module("arclink_adapters.py", "arclink_adapters_resolver_test")
    # No key -> FakeStripeClient
    client = mod.resolve_stripe_client(env={})
    expect(isinstance(client, mod.FakeStripeClient), type(client).__name__)
    client = mod.resolve_stripe_client(env={"STRIPE_SECRET_KEY": ""})
    expect(isinstance(client, mod.FakeStripeClient), type(client).__name__)
    # LiveStripeClient refuses blank key
    try:
        mod.LiveStripeClient(secret_key="")
    except ValueError as exc:
        expect("STRIPE_SECRET_KEY" in str(exc), str(exc))
    else:
        raise AssertionError("expected blank key to fail")
    # With key -> LiveStripeClient (construction only, no network call)
    client = mod.resolve_stripe_client(env={"STRIPE_SECRET_KEY": "sk_test_fake"})
    expect(isinstance(client, mod.LiveStripeClient), type(client).__name__)
    print("PASS test_stripe_client_resolver_returns_fake_without_key_and_rejects_blank")


def test_cloudflare_drift_and_traefik_label_rendering() -> None:
    mod = load_module("arclink_adapters.py", "arclink_adapters_dns_test")
    hostnames = mod.arclink_hostnames("abc123", "example.test")
    expect(hostnames["dashboard"] == "u-abc123.example.test", str(hostnames))
    expect(hostnames["files"] == "files-abc123.example.test", str(hostnames))
    desired = [mod.DnsRecord(hostname=hostnames["dashboard"], record_type="CNAME", target="edge.example.test")]
    cloudflare = mod.FakeCloudflareClient()
    expect(cloudflare.drift(desired) == ["missing CNAME u-abc123.example.test"], str(cloudflare.drift(desired)))
    cloudflare.upsert_record(desired[0])
    expect(cloudflare.drift(desired) == [], str(cloudflare.drift(desired)))
    labels = mod.render_traefik_http_labels(service_name="dashboard", hostname=hostnames["dashboard"], port=8080)
    expect(labels["traefik.http.routers.arclink-dashboard.rule"] == "Host(`u-abc123.example.test`)", str(labels))
    expect(labels["traefik.http.services.arclink-dashboard.loadbalancer.server.port"] == "8080", str(labels))
    labels = mod.render_traefik_http_path_labels(
        service_name="dashboard",
        hostname=hostnames["dashboard"],
        path_prefix="/u/abc123",
        port=3000,
        docker_network="arclink_default",
        priority=10,
    )
    expect(labels["traefik.docker.network"] == "arclink_default", str(labels))
    expect(labels["traefik.http.routers.arclink-dashboard.priority"] == "10", str(labels))
    print("PASS test_cloudflare_drift_and_traefik_label_rendering")


def test_tailscale_path_access_urls_can_use_dedicated_tls_ports() -> None:
    mod = load_module("arclink_adapters.py", "arclink_adapters_tailnet_ports_test")
    urls = mod.arclink_access_urls(
        prefix="abc123",
        base_domain="worker.example.test",
        ingress_mode="tailscale",
        tailscale_dns_name="worker.example.test",
        tailscale_host_strategy="path",
        tailnet_service_ports={"hermes": "8443", "files": 8444, "code": 8445},
    )
    expect(urls["dashboard"] == "https://worker.example.test/u/abc123", str(urls))
    expect(urls["hermes"] == "https://worker.example.test:8443/", str(urls))
    expect(urls["files"] == "https://worker.example.test/u/abc123/drive", str(urls))
    expect(urls["code"] == "https://worker.example.test/u/abc123/code", str(urls))
    print("PASS test_tailscale_path_access_urls_can_use_dedicated_tls_ports")


def test_chutes_key_rotate_and_state_tracking() -> None:
    chutes = load_module("arclink_chutes.py", "arclink_chutes_rotate_test")
    mgr = chutes.FakeChutesKeyManager()
    created = mgr.create_key("dep_rot_1", label="initial")
    expect(created["status"] == "active", str(created))
    expect(mgr.key_state("dep_rot_1") is not None, "expected key state")

    rotated = mgr.rotate_key("dep_rot_1", label="rotated")
    expect(rotated["status"] == "active", str(rotated))
    state = mgr.key_state("dep_rot_1")
    expect(state is not None and state["status"] == "active", str(state))

    revoked = mgr.revoke_key(rotated["key_id"])
    expect(revoked["status"] == "revoked", str(revoked))
    expect(mgr.key_state("dep_rot_1")["status"] == "revoked", "expected revoked")  # type: ignore[index]
    print("PASS test_chutes_key_rotate_and_state_tracking")


def test_fake_inference_smoke_and_failure_reporting() -> None:
    chutes = load_module("arclink_chutes.py", "arclink_chutes_inference_test")

    # Success path
    client = chutes.FakeChutesInferenceClient()
    result = client.chat_completion(model="deepseek-ai/DeepSeek-R1", messages=[{"role": "user", "content": "hi"}])
    expect("choices" in result, str(result))
    expect(len(client.calls) == 1, str(client.calls))

    # Failure path
    failing = chutes.FakeChutesInferenceClient(fail=True)
    try:
        failing.chat_completion(model="deepseek-ai/DeepSeek-R1", messages=[{"role": "user", "content": "hi"}])
        expect(False, "expected ChutesCatalogError")
    except chutes.ChutesCatalogError:
        pass
    expect(len(failing.calls) == 1, "failure should still record the call")
    print("PASS test_fake_inference_smoke_and_failure_reporting")


def test_fake_stripe_billing_portal_session() -> None:
    mod = load_module("arclink_adapters.py", "arclink_adapters_portal_test")
    stripe = mod.FakeStripeClient()
    session = stripe.create_portal_session(customer_id="cus_test_1", return_url="https://example.test/dashboard")
    expect(session["id"].startswith("bps_test_"), str(session))
    expect(session["url"].startswith("https://stripe.test/portal/"), str(session))
    expect(session["customer_id"] == "cus_test_1", str(session))
    expect(session["return_url"] == "https://example.test/dashboard", str(session))
    expect(len(stripe.portal_sessions) == 1, str(stripe.portal_sessions))
    # Second portal session gets a new id
    session2 = stripe.create_portal_session(customer_id="cus_test_1", return_url="https://example.test/dashboard")
    expect(session2["id"] != session["id"], f"expected unique portal session ids: {session['id']} {session2['id']}")
    print("PASS test_fake_stripe_billing_portal_session")


def test_fake_cloudflare_propagation_check_after_provision() -> None:
    mod = load_module("arclink_adapters.py", "arclink_adapters_propagation_test")
    cloudflare = mod.FakeCloudflareClient()
    hostnames = mod.arclink_hostnames("prop123", "example.test")
    desired = [
        mod.DnsRecord(hostname=hostnames[role], record_type="CNAME", target="edge.example.test")
        for role in ("dashboard", "files", "code", "hermes")
    ]
    # Before provisioning: all missing
    drift_before = cloudflare.drift(desired)
    expect(len(drift_before) == 4, str(drift_before))
    # Provision all records
    for record in desired:
        cloudflare.upsert_record(record)
    # After provisioning: no drift (propagation check passes)
    drift_after = cloudflare.drift(desired)
    expect(drift_after == [], str(drift_after))
    # Teardown and verify records removed
    removed = cloudflare.teardown_records([r.hostname for r in desired])
    expect(len(removed) == 4, str(removed))
    drift_torn = cloudflare.drift(desired)
    expect(len(drift_torn) == 4, str(drift_torn))
    print("PASS test_fake_cloudflare_propagation_check_after_provision")


def test_chutes_catalog_refresh_picks_up_new_models() -> None:
    mod = load_module("arclink_chutes.py", "arclink_chutes_catalog_refresh_test")
    initial_catalog: dict[str, Any] = {
        "data": [
            {"id": "moonshotai/Kimi-K2.6-TEE", "capabilities": {"tools": True, "reasoning": True, "structured_outputs": True, "confidential_compute": True}},
        ]
    }
    http = FixtureHttpClient(initial_catalog)
    client = mod.ChutesCatalogClient(http)
    models_v1 = client.list_models()
    expect(len(models_v1) == 1, str(models_v1))

    # Simulate catalog update with a new model added
    updated_catalog: dict[str, Any] = {
        "data": [
            {"id": "moonshotai/Kimi-K2.6-TEE", "capabilities": {"tools": True, "reasoning": True, "structured_outputs": True, "confidential_compute": True}},
            {"id": "new-model/v2-TEE", "capabilities": {"tools": True, "reasoning": True, "structured_outputs": True, "confidential_compute": True}},
        ]
    }
    http.payload = updated_catalog
    models_v2 = client.list_models()
    expect(len(models_v2) == 2, str(models_v2))
    expect("new-model/v2-TEE" in models_v2, str(models_v2))
    # Validate the new model passes validation
    model = mod.validate_default_chutes_model(
        models_v2,
        env={"ARCLINK_CHUTES_DEFAULT_MODEL": "new-model/v2-TEE"},
    )
    expect(model.model_id == "new-model/v2-TEE", str(model))
    print("PASS test_chutes_catalog_refresh_picks_up_new_models")


def test_chutes_boundary_fails_closed_without_scoped_secret_or_budget() -> None:
    mod = load_module("arclink_chutes.py", "arclink_chutes_boundary_closed_test")
    state = mod.evaluate_chutes_deployment_boundary(
        "dep_budget_1",
        "user_budget_1",
        {},
        env={"CHUTES_API_KEY": "raw_operator_secret_value"},
    )
    expect(state.isolation_mode == "operator_shared_key_rejected", str(state))
    expect(state.credential_state == "missing_secret_ref", str(state))
    expect(state.allow_inference is False, str(state))
    public = state.to_public(include_user_id=True, include_admin_fields=True)
    public_text = json.dumps(public, sort_keys=True)
    expect("raw_operator_secret_value" not in public_text, public_text)
    expect(public["budget"]["limit_enforced"] is True, str(public))

    unscoped = mod.evaluate_chutes_deployment_boundary(
        "dep_budget_1",
        "user_budget_1",
        {"chutes": {"secret_ref": "secret://arclink/chutes/other_user", "monthly_budget_cents": 5000}},
    )
    expect(unscoped.credential_state == "unscoped_secret_ref", str(unscoped))
    expect(unscoped.allow_inference is False, str(unscoped))
    unsafe_key_id = mod.evaluate_chutes_deployment_boundary(
        "dep_budget_1",
        "user_budget_1",
        {"chutes": {"secret_ref": "secret://arclink/chutes/dep_budget_1", "monthly_budget_cents": 5000, "key_id": "sk_test_bad"}},
    )
    expect(unsafe_key_id.to_public(include_admin_fields=True)["key_id"] == "", str(unsafe_key_id))
    print("PASS test_chutes_boundary_fails_closed_without_scoped_secret_or_budget")


def test_chutes_boundary_publishes_defined_credential_lifecycle() -> None:
    mod = load_module("arclink_chutes.py", "arclink_chutes_lifecycle_test")
    missing = mod.evaluate_chutes_deployment_boundary(
        "dep_lifecycle_1",
        "user_lifecycle_1",
        {},
        env={"CHUTES_API_KEY": "raw_operator_secret_value"},
    )
    missing_lifecycle = missing.to_public()["credential_lifecycle"]
    expect(missing_lifecycle["canonical_mode"] == "scoped_secret_ref_per_user_or_deployment", str(missing_lifecycle))
    expect(
        missing_lifecycle["accepted_modes"] == [
            "per_deployment_secret_ref",
            "per_user_secret_ref",
            "per_user_chutes_account_oauth",
        ],
        str(missing_lifecycle),
    )
    expect(missing_lifecycle["current_mode"] == "operator_shared_key_rejected", str(missing_lifecycle))
    expect(missing_lifecycle["operator_shared_key_policy"] == "rejected_for_user_isolation", str(missing_lifecycle))
    expect(missing_lifecycle["live_key_creation"] == "proof_gated", str(missing_lifecycle))
    expect(
        missing_lifecycle["fallback"] == "per_user_chutes_account_oauth_required_when_per_key_metering_unavailable",
        str(missing_lifecycle),
    )
    expect(missing_lifecycle["posture"] == "disabled_until_scoped_secret_ref_and_budget", str(missing_lifecycle))

    scoped = mod.evaluate_chutes_deployment_boundary(
        "dep_lifecycle_2",
        "user_lifecycle_2",
        {
            "chutes": {
                "secret_ref": "secret://arclink/chutes/user_lifecycle_2",
                "monthly_budget_cents": 1000,
                "used_cents": 100,
            }
        },
    )
    scoped_public = scoped.to_public(include_admin_fields=True)
    scoped_lifecycle = scoped_public["credential_lifecycle"]
    expect(scoped.isolation_mode == "per_user_secret_ref", str(scoped))
    expect(scoped_lifecycle["current_mode"] == "per_user_secret_ref", str(scoped_lifecycle))
    expect(scoped_lifecycle["posture"] == "active_scoped_secret_ref", str(scoped_lifecycle))
    expect(scoped_public["secret_ref_present"] is True, str(scoped_public))
    serialized = json.dumps(scoped_public, sort_keys=True)
    expect("secret://arclink/chutes/user_lifecycle_2" not in serialized, serialized)
    expect("raw_operator_secret_value" not in json.dumps(missing.to_public(), sort_keys=True), str(missing.to_public()))
    print("PASS test_chutes_boundary_publishes_defined_credential_lifecycle")


def test_chutes_boundary_warns_and_blocks_at_budget_limit() -> None:
    mod = load_module("arclink_chutes.py", "arclink_chutes_boundary_budget_test")
    metadata = {
        "chutes": {
            "secret_ref": "secret://arclink/chutes/dep_budget_2",
            "key_id": "key_budget_2",
            "monthly_budget_cents": 10000,
            "used_cents": 8500,
            "warning_threshold_percent": 80,
        }
    }
    warning = mod.evaluate_chutes_deployment_boundary("dep_budget_2", "user_budget_2", metadata)
    expect(warning.credential_state == "budget_warning", str(warning))
    expect(warning.allow_inference is True, str(warning))
    expect(warning.remaining_cents == 1500, str(warning))
    public = warning.to_public(include_admin_fields=True)
    expect(public["key_id"] == "key_budget_2", str(public))
    continuation = public["threshold_continuation"]
    expect(continuation["status"] == "policy_question", str(continuation))
    expect(continuation["dashboard_guidance"] == "show_sanitized_threshold_state_only", str(continuation))
    expect(continuation["raven_notifications"] == "disabled_until_warning_cadence_policy", str(continuation))
    expect(continuation["provider_fallback"] == "policy_question", str(continuation))
    expect(continuation["overage_refill"] == "policy_question", str(continuation))
    expect("secret://" not in json.dumps(public, sort_keys=True), str(public))

    exhausted_meta = dict(metadata)
    exhausted_meta["chutes"] = dict(metadata["chutes"], used_cents=10000)
    exhausted = mod.evaluate_chutes_deployment_boundary("dep_budget_2", "user_budget_2", exhausted_meta)
    expect(exhausted.credential_state == "budget_exhausted", str(exhausted))
    expect(exhausted.allow_inference is False, str(exhausted))
    expect(exhausted.to_public()["threshold_continuation"]["status"] == "policy_question", str(exhausted.to_public()))

    suspended_meta = dict(metadata)
    suspended_meta["chutes"] = dict(metadata["chutes"], status="suspended")
    suspended = mod.evaluate_chutes_deployment_boundary("dep_budget_2", "user_budget_2", suspended_meta)
    expect(suspended.credential_state == "suspended", str(suspended))
    expect(suspended.allow_inference is False, str(suspended))
    print("PASS test_chutes_boundary_warns_and_blocks_at_budget_limit")


def test_chutes_boundary_suspends_provider_for_noncurrent_billing() -> None:
    mod = load_module("arclink_chutes.py", "arclink_chutes_boundary_billing_test")
    metadata = {
        "chutes": {
            "secret_ref": "secret://arclink/chutes/dep_billing_1",
            "monthly_budget_cents": 10000,
            "used_cents": 1000,
        }
    }
    current = mod.evaluate_chutes_deployment_boundary(
        "dep_billing_1",
        "user_billing_1",
        metadata,
        billing_state="paid",
    )
    expect(current.allow_inference is True, str(current))
    expect(current.billing_lifecycle["provider_access"] == "allowed", str(current.billing_lifecycle))

    past_due = mod.evaluate_chutes_deployment_boundary(
        "dep_billing_1",
        "user_billing_1",
        metadata,
        billing_state="past_due",
    )
    expect(past_due.credential_state == "billing_suspended", str(past_due))
    expect(past_due.allow_inference is False, str(past_due))
    public = past_due.to_public()
    lifecycle = public["billing_lifecycle"]
    expect(lifecycle["provider_access"] == "suspended", str(lifecycle))
    expect(lifecycle["warning_cadence"] == "immediate_notice_then_daily_reminders", str(lifecycle))
    expect(lifecycle["grace_period"] == "provider_suspended_immediately", str(lifecycle))
    expect(lifecycle["data_retention"] == "account_data_removed_warning_day_7", str(lifecycle))
    expect(lifecycle["purge_policy"] == "audited_purge_queue_day_14", str(lifecycle))
    expect(lifecycle["day_7_action"] == "warn_account_and_data_removal", str(lifecycle))
    expect(lifecycle["day_14_action"] == "queue_audited_purge", str(lifecycle))
    print("PASS test_chutes_boundary_suspends_provider_for_noncurrent_billing")


def test_chutes_boundary_prefers_user_account_oauth_when_key_metering_unavailable() -> None:
    mod = load_module("arclink_chutes.py", "arclink_chutes_account_oauth_fallback_test")
    state = mod.evaluate_chutes_deployment_boundary(
        "dep_oauth_1",
        "user_oauth_1",
        {"chutes": {"monthly_budget_cents": 5000}},
        env={"ARCLINK_CHUTES_PER_KEY_METERING_AVAILABLE": "0"},
        billing_state="paid",
    )
    expect(state.credential_state == "account_oauth_required", str(state))
    expect(state.allow_inference is False, str(state))
    public = state.to_public()
    expect(public["credential_lifecycle"]["fallback"] == "per_user_chutes_account_oauth_required_when_per_key_metering_unavailable", str(public))
    expect("secret://" not in json.dumps(public, sort_keys=True), str(public))
    print("PASS test_chutes_boundary_prefers_user_account_oauth_when_key_metering_unavailable")


def test_fake_inference_enforces_chutes_boundary() -> None:
    mod = load_module("arclink_chutes.py", "arclink_chutes_inference_boundary_test")
    allowed = mod.evaluate_chutes_deployment_boundary(
        "dep_budget_3",
        "user_budget_3",
        {"chutes": {"secret_ref": "secret://arclink/chutes/dep_budget_3", "monthly_budget_cents": 1000, "used_cents": 250}},
    )
    blocked = mod.evaluate_chutes_deployment_boundary(
        "dep_budget_3",
        "user_budget_3",
        {"chutes": {"secret_ref": "secret://arclink/chutes/dep_budget_3", "monthly_budget_cents": 1000, "used_cents": 1000}},
    )
    client = mod.FakeChutesInferenceClient()
    result = client.chat_completion(
        model="moonshotai/Kimi-K2.6-TEE",
        messages=[{"role": "user", "content": "hi"}],
        boundary=allowed,
    )
    expect(result["choices"][0]["message"]["content"], str(result))
    expect(client.calls[0]["boundary_checked"] is True, str(client.calls))
    try:
        client.chat_completion(
            model="moonshotai/Kimi-K2.6-TEE",
            messages=[{"role": "user", "content": "hi"}],
            boundary=blocked,
        )
    except mod.ChutesCatalogError as exc:
        expect("budget_exhausted" in str(exc), str(exc))
    else:
        raise AssertionError("expected exhausted Chutes boundary to block inference")
    print("PASS test_fake_inference_enforces_chutes_boundary")


def test_chutes_usage_ingestion_updates_budget_boundary_without_secrets() -> None:
    control = load_module("arclink_control.py", "arclink_control_chutes_usage_ingest_test")
    mod = load_module("arclink_chutes.py", "arclink_chutes_usage_ingest_test")
    conn = memory_db(control)
    control.upsert_arclink_user(
        conn,
        user_id="user_usage_1",
        email="usage@example.test",
        entitlement_state="paid",
    )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_usage_1",
        user_id="user_usage_1",
        prefix="usage-one",
        base_domain="example.test",
        status="active",
        metadata={
            "chutes": {
                "secret_ref": "secret://arclink/chutes/dep_usage_1",
                "monthly_budget_cents": 10000,
                "used_cents": 7900,
                "warning_threshold_percent": 80,
            }
        },
    )

    result = mod.record_chutes_usage_event(
        conn,
        deployment_id="dep_usage_1",
        user_id="user_usage_1",
        usage_event={
            "request_id": "req_usage_1",
            "model_id": "moonshotai/Kimi-K2.6-TEE",
            "cost_cents": 150,
            "input_tokens": 500,
            "output_tokens": 50,
            "source": "fake-runtime",
            "authorization": "sk_should_not_be_stored",
        },
        billing_state="paid",
    )
    expect(result.recorded is True, str(result))
    expect(result.delta_cents == 150, str(result))
    expect(result.used_cents_before == 7900, str(result))
    expect(result.used_cents_after == 8050, str(result))
    expect(result.boundary.credential_state == "budget_warning", str(result.boundary))
    expect(result.boundary.allow_inference is True, str(result.boundary))

    duplicate = mod.record_chutes_usage_event(
        conn,
        deployment_id="dep_usage_1",
        user_id="user_usage_1",
        usage_event={"request_id": "req_usage_1", "model_id": "moonshotai/Kimi-K2.6-TEE", "cost_cents": 150},
        billing_state="paid",
    )
    expect(duplicate.recorded is False, str(duplicate))
    expect(duplicate.used_cents_after == 8050, str(duplicate))

    stored = conn.execute("SELECT metadata_json FROM arclink_deployments WHERE deployment_id = 'dep_usage_1'").fetchone()
    metadata = json.loads(stored["metadata_json"])
    expect(metadata["chutes"]["used_cents"] == 8050, str(metadata))
    expect(metadata["chutes"]["usage_event_count"] == 1, str(metadata))
    event_row = conn.execute(
        "SELECT event_type, metadata_json FROM arclink_events WHERE subject_id = 'dep_usage_1'"
    ).fetchone()
    expect(event_row["event_type"] == "chutes_usage_ingested", str(dict(event_row)))
    event_text = event_row["metadata_json"]
    expect("sk_should_not_be_stored" not in event_text, event_text)
    expect("secret://" not in event_text, event_text)
    event_metadata = json.loads(event_text)
    expect(event_metadata["delta_cents"] == 150, str(event_metadata))
    expect(event_metadata["total_tokens"] == 550, str(event_metadata))
    print("PASS test_chutes_usage_ingestion_updates_budget_boundary_without_secrets")


def test_chutes_usage_ingestion_blocks_after_hard_limit() -> None:
    control = load_module("arclink_control.py", "arclink_control_chutes_usage_limit_test")
    mod = load_module("arclink_chutes.py", "arclink_chutes_usage_limit_test")
    conn = memory_db(control)
    control.upsert_arclink_user(
        conn,
        user_id="user_usage_2",
        email="usage-limit@example.test",
        entitlement_state="paid",
    )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_usage_2",
        user_id="user_usage_2",
        prefix="usage-two",
        base_domain="example.test",
        status="active",
        metadata={
            "chutes": {
                "secret_ref": "secret://arclink/chutes/user_usage_2",
                "monthly_budget_cents": 1000,
                "used_cents": 900,
                "hard_limit_percent": 100,
            }
        },
    )
    result = mod.record_chutes_usage_event(
        conn,
        deployment_id="dep_usage_2",
        user_id="user_usage_2",
        usage_event={"request_id": "req_limit_1", "cost_cents": 150},
        billing_state="paid",
    )
    expect(result.boundary.credential_state == "budget_exhausted", str(result.boundary))
    expect(result.boundary.allow_inference is False, str(result.boundary))
    try:
        mod.record_chutes_usage_event(
            conn,
            deployment_id="dep_usage_2",
            user_id="other_user",
            usage_event={"request_id": "req_bad_owner", "cost_cents": 1},
        )
    except PermissionError:
        pass
    else:
        raise AssertionError("expected usage ingestion to reject wrong user scope")
    print("PASS test_chutes_usage_ingestion_blocks_after_hard_limit")


def main() -> int:
    test_chutes_catalog_parses_and_validates_default_model()
    test_chutes_catalog_fails_for_missing_or_unsupported_default()
    test_fake_chutes_key_manager_uses_secret_references()
    test_fake_stripe_webhook_and_sessions()
    test_stripe_client_resolver_returns_fake_without_key_and_rejects_blank()
    test_cloudflare_drift_and_traefik_label_rendering()
    test_tailscale_path_access_urls_can_use_dedicated_tls_ports()
    test_chutes_key_rotate_and_state_tracking()
    test_fake_inference_smoke_and_failure_reporting()
    test_fake_stripe_billing_portal_session()
    test_fake_cloudflare_propagation_check_after_provision()
    test_chutes_catalog_refresh_picks_up_new_models()
    test_chutes_boundary_fails_closed_without_scoped_secret_or_budget()
    test_chutes_boundary_publishes_defined_credential_lifecycle()
    test_chutes_boundary_warns_and_blocks_at_budget_limit()
    test_chutes_boundary_suspends_provider_for_noncurrent_billing()
    test_chutes_boundary_prefers_user_account_oauth_when_key_metering_unavailable()
    test_fake_inference_enforces_chutes_boundary()
    test_chutes_usage_ingestion_updates_budget_boundary_without_secrets()
    test_chutes_usage_ingestion_blocks_after_hard_limit()
    print("PASS all 20 ArcLink Chutes/adapter tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
