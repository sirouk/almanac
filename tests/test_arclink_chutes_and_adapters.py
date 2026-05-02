#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from typing import Any, Mapping

from arclink_test_helpers import expect, load_module


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
    print("PASS test_cloudflare_drift_and_traefik_label_rendering")


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


def main() -> int:
    test_chutes_catalog_parses_and_validates_default_model()
    test_chutes_catalog_fails_for_missing_or_unsupported_default()
    test_fake_chutes_key_manager_uses_secret_references()
    test_fake_stripe_webhook_and_sessions()
    test_stripe_client_resolver_returns_fake_without_key_and_rejects_blank()
    test_cloudflare_drift_and_traefik_label_rendering()
    test_chutes_key_rotate_and_state_tracking()
    test_fake_inference_smoke_and_failure_reporting()
    print("PASS all 8 ArcLink Chutes/adapter tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
