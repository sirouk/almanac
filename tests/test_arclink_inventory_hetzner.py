#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
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


def test_hetzner_provider_fails_closed_without_token() -> None:
    mod = load_module("arclink_inventory_hetzner.py", "arclink_inventory_hetzner_missing")
    try:
        mod.HetznerInventoryProvider(token="")
    except mod.InventoryProviderError as exc:
        expect("token missing" in str(exc), str(exc))
    else:
        raise AssertionError("missing token should fail closed")
    print("PASS test_hetzner_provider_fails_closed_without_token")


def test_hetzner_provider_lists_servers_and_redacts_errors() -> None:
    http = load_module("arclink_http.py", "arclink_http_hetzner_test")
    mod = load_module("arclink_inventory_hetzner.py", "arclink_inventory_hetzner_list")
    calls = []

    def fake_http(url, **kwargs):
        calls.append((url, kwargs))
        return http.HttpResponse(
            200,
            '{"servers":[{"id":123,"name":"worker-1","status":"running","public_net":{"ipv4":{"ip":"203.0.113.10"}},"datacenter":{"location":{"name":"fsn1"}},"server_type":{"cores":4,"memory":16,"disk":160}}]}',
            {},
        )

    provider = mod.HetznerInventoryProvider(token="hcloud-secret-token-value", http_request_fn=fake_http)
    servers = provider.list_servers()
    expect(servers[0]["provider_resource_id"] == "123", str(servers))
    expect(servers[0]["hardware_summary"]["vcpu_cores"] == 4, str(servers))
    expect("Authorization" in calls[0][1]["headers"], str(calls))

    def failing_http(url, **kwargs):
        return http.HttpResponse(403, "bad hcloud-secret-token-value", {})

    bad = mod.HetznerInventoryProvider(token="hcloud-secret-token-value", http_request_fn=failing_http)
    try:
        bad.list_servers()
    except mod.InventoryProviderError as exc:
        expect("hcloud-secret-token-value" not in str(exc), str(exc))
    else:
        raise AssertionError("HTTP failure should raise")
    print("PASS test_hetzner_provider_lists_servers_and_redacts_errors")


if __name__ == "__main__":
    test_hetzner_provider_fails_closed_without_token()
    test_hetzner_provider_lists_servers_and_redacts_errors()
    print("\nAll Hetzner inventory tests passed.")
