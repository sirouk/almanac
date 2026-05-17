#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
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


def test_linode_provider_fails_closed_without_token() -> None:
    mod = load_module("arclink_inventory_linode.py", "arclink_inventory_linode_missing")
    try:
        mod.LinodeInventoryProvider(token="")
    except mod.InventoryProviderError as exc:
        expect("token missing" in str(exc), str(exc))
    else:
        raise AssertionError("missing token should fail closed")
    print("PASS test_linode_provider_fails_closed_without_token")


def test_linode_provider_lists_instances_and_redacts_errors() -> None:
    http = load_module("arclink_http.py", "arclink_http_linode_test")
    mod = load_module("arclink_inventory_linode.py", "arclink_inventory_linode_list")
    calls = []

    def fake_http(url, **kwargs):
        calls.append((url, kwargs))
        return http.HttpResponse(
            200,
            '{"data":[{"id":456,"label":"linode-1","status":"running","ipv4":["203.0.113.20"],"region":"us-east","specs":{"vcpus":4,"memory":16384,"disk":163840}}]}',
            {},
        )

    provider = mod.LinodeInventoryProvider(token="linode-secret-token-value", http_request_fn=fake_http)
    servers = provider.list_servers()
    expect(servers[0]["provider_resource_id"] == "456", str(servers))
    expect(servers[0]["hardware_summary"]["ram_gib"] == 16.0, str(servers))
    expect("Authorization" in calls[0][1]["headers"], str(calls))

    def failing_http(url, **kwargs):
        return http.HttpResponse(401, "bad linode-secret-token-value", {})

    bad = mod.LinodeInventoryProvider(token="linode-secret-token-value", http_request_fn=failing_http)
    try:
        bad.list_servers()
    except mod.InventoryProviderError as exc:
        expect("linode-secret-token-value" not in str(exc), str(exc))
    else:
        raise AssertionError("HTTP failure should raise")
    print("PASS test_linode_provider_lists_instances_and_redacts_errors")


class FakeLinodeClient:
    def __init__(self) -> None:
        self.created = 0

    def provision_server(self, *, label, linode_type, image, region, authorized_keys):
        self.created += 1
        return {
            "provider": "linode",
            "provider_resource_id": "l-456",
            "hostname": label,
            "ssh_host": "203.0.113.20",
            "region": region,
            "status": "provisioning",
            "hardware_summary": {"vcpu_cores": 4, "ram_gib": 8, "disk_gib": 160},
        }


def test_linode_cloud_create_records_bootstrap_failure_without_secret_leak() -> None:
    control = load_module("arclink_control.py", "arclink_control_linode_bootstrap")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_linode_bootstrap")
    conn = __import__("sqlite3").connect(":memory:")
    conn.row_factory = __import__("sqlite3").Row
    control.ensure_schema(conn)
    client = FakeLinodeClient()

    def failing_bootstrap(context):
        expect(context["prereq_library"] == "bin/lib/ensure-prereqs.sh", str(context))
        raise RuntimeError("join failed with token=linode-secret-token-value")

    result = inventory.create_cloud_inventory_machine(
        conn,
        provider="linode",
        client=client,
        hostname="worker-us-east",
        server_type="g6-standard-2",
        image="linode/ubuntu24.04",
        region="us-east",
        ssh_keys=["ssh-rsa AAAA..."],
        idempotency_key="linode-create-1",
        bootstrap_runner=failing_bootstrap,
    )
    expect(result["status"] == "degraded", str(result))
    metadata = json.loads(result["machine"]["metadata_json"])
    metadata_text = json.dumps(metadata, sort_keys=True)
    expect(metadata["provider_bootstrap"]["status"] == "failed", metadata_text)
    expect("linode-secret-token-value" not in metadata_text, metadata_text)
    expect("sensitive detail redacted" in metadata_text, metadata_text)
    print("PASS test_linode_cloud_create_records_bootstrap_failure_without_secret_leak")


if __name__ == "__main__":
    test_linode_provider_fails_closed_without_token()
    test_linode_provider_lists_instances_and_redacts_errors()
    test_linode_cloud_create_records_bootstrap_failure_without_secret_leak()
    print("\nAll Linode inventory tests passed.")
