#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any, Mapping


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


def main() -> int:
    test_chutes_catalog_parses_and_validates_default_model()
    test_chutes_catalog_fails_for_missing_or_unsupported_default()
    test_fake_chutes_key_manager_uses_secret_references()
    test_fake_stripe_webhook_and_sessions()
    test_cloudflare_drift_and_traefik_label_rendering()
    print("PASS all 5 ArcLink Chutes/adapter tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
