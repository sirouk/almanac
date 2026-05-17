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


class FakeHetznerClient:
    def __init__(self) -> None:
        self.created = 0
        self.removed: list[tuple[str, bool]] = []

    def provision_server(self, *, name, server_type, image, location, ssh_keys):
        self.created += 1
        return {
            "provider": "hetzner",
            "provider_resource_id": "h-123",
            "hostname": name,
            "ssh_host": "203.0.113.10",
            "region": location,
            "status": "running",
            "hardware_summary": {"vcpu_cores": 4, "ram_gib": 8, "disk_gib": 80},
        }

    def remove_server(self, server_id, *, destroy=False):
        self.removed.append((server_id, bool(destroy)))
        return {"action": {"id": 1}}


def test_hetzner_cloud_create_is_idempotent_and_persists_metadata() -> None:
    control = load_module("arclink_control.py", "arclink_control_hetzner_create")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_hetzner_create")
    conn = __import__("sqlite3").connect(":memory:")
    conn.row_factory = __import__("sqlite3").Row
    control.ensure_schema(conn)
    client = FakeHetznerClient()

    result = inventory.create_cloud_inventory_machine(
        conn,
        provider="hetzner",
        client=client,
        hostname="worker-fsn1",
        server_type="cx22",
        image="ubuntu-24.04",
        region="fsn1",
        ssh_keys=["fleet-key"],
        capacity_slots=6,
        tags={"region_tier": "primary"},
        idempotency_key="hetzner-create-1",
        provider_billing_ref="bill-redacted-test",
    )
    replay = inventory.create_cloud_inventory_machine(
        conn,
        provider="hetzner",
        client=client,
        hostname="worker-fsn1",
        server_type="cx22",
        image="ubuntu-24.04",
        region="fsn1",
        ssh_keys=["fleet-key"],
        capacity_slots=6,
        tags={"region_tier": "primary"},
        idempotency_key="hetzner-create-1",
        provider_billing_ref="bill-redacted-test",
    )

    expect(client.created == 1, f"provider create should not replay: {client.created}")
    expect(result["machine"]["provider_resource_id"] == "h-123", str(result))
    expect(result["machine"]["provider_billing_ref"] == "bill-redacted-test", str(result))
    metadata = json.loads(result["machine"]["metadata_json"])
    expect(metadata["provider_bootstrap"]["prereq_library"] == "bin/lib/ensure-prereqs.sh", str(metadata))
    expect(replay["replay"] is True, str(replay))
    rows = conn.execute("SELECT COUNT(*) AS count FROM arclink_inventory_machines WHERE provider = 'hetzner'").fetchone()
    expect(rows["count"] == 1, str(rows["count"]))
    print("PASS test_hetzner_cloud_create_is_idempotent_and_persists_metadata")


def test_hetzner_cloud_duplicate_hostname_does_not_create_second_server() -> None:
    control = load_module("arclink_control.py", "arclink_control_hetzner_duplicate")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_hetzner_duplicate")
    conn = __import__("sqlite3").connect(":memory:")
    conn.row_factory = __import__("sqlite3").Row
    control.ensure_schema(conn)
    client = FakeHetznerClient()
    inventory.create_cloud_inventory_machine(
        conn,
        provider="hetzner",
        client=client,
        hostname="worker-fsn1",
        server_type="cx22",
        image="ubuntu-24.04",
        region="fsn1",
        idempotency_key="hetzner-create-a",
    )
    duplicate = inventory.create_cloud_inventory_machine(
        conn,
        provider="hetzner",
        client=client,
        hostname="worker-fsn1",
        server_type="cx32",
        image="ubuntu-24.04",
        region="fsn1",
        idempotency_key="hetzner-create-b",
    )
    expect(client.created == 1, f"duplicate hostname created extra server: {client.created}")
    expect(duplicate["status"] == "existing", str(duplicate))
    print("PASS test_hetzner_cloud_duplicate_hostname_does_not_create_second_server")


def test_hetzner_cloud_remove_requires_drain_and_destroy_then_replays() -> None:
    control = load_module("arclink_control.py", "arclink_control_hetzner_remove")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_hetzner_remove")
    conn = __import__("sqlite3").connect(":memory:")
    conn.row_factory = __import__("sqlite3").Row
    control.ensure_schema(conn)
    client = FakeHetznerClient()
    machine = inventory.create_cloud_inventory_machine(
        conn,
        provider="hetzner",
        client=client,
        hostname="worker-fsn1",
        server_type="cx22",
        image="ubuntu-24.04",
        region="fsn1",
        idempotency_key="hetzner-create-remove",
    )["machine"]
    try:
        inventory.remove_cloud_inventory_machine(conn, key=machine["machine_id"], client=client, destroy=True)
    except inventory.ArcLinkInventoryError as exc:
        expect("drain" in str(exc), str(exc))
    else:
        raise AssertionError("cloud removal must require drain or force")
    inventory.drain_inventory_machine(conn, machine["machine_id"])
    removed = inventory.remove_cloud_inventory_machine(
        conn,
        key=machine["machine_id"],
        client=client,
        destroy=True,
        idempotency_key="hetzner-remove-1",
    )
    replay = inventory.remove_cloud_inventory_machine(
        conn,
        key=machine["machine_id"],
        client=client,
        destroy=True,
        idempotency_key="hetzner-remove-1",
    )
    expect(client.removed == [("h-123", True)], str(client.removed))
    expect(removed["machine"]["status"] == "removed", str(removed))
    expect(replay["replay"] is True, str(replay))
    print("PASS test_hetzner_cloud_remove_requires_drain_and_destroy_then_replays")


if __name__ == "__main__":
    test_hetzner_provider_fails_closed_without_token()
    test_hetzner_provider_lists_servers_and_redacts_errors()
    test_hetzner_cloud_create_is_idempotent_and_persists_metadata()
    test_hetzner_cloud_duplicate_hostname_does_not_create_second_server()
    test_hetzner_cloud_remove_requires_drain_and_destroy_then_replays()
    print("\nAll Hetzner inventory tests passed.")
