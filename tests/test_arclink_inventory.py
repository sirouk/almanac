#!/usr/bin/env python3
from __future__ import annotations

import json

from arclink_test_helpers import expect, load_module, memory_db


class _FakeCloudClient:
    def __init__(self, provider: str) -> None:
        self.provider = provider
        self.created = 0
        self.removed: list[tuple[str, bool]] = []

    def provision_server(self, **kwargs):
        self.created += 1
        hostname = str(kwargs.get("name") or kwargs.get("label") or "")
        region = str(kwargs.get("location") or kwargs.get("region") or "")
        prefix = "h" if self.provider == "hetzner" else "l"
        return {
            "provider": self.provider,
            "provider_resource_id": f"{prefix}-{self.created}",
            "hostname": hostname,
            "ssh_host": "203.0.113.30",
            "region": region,
            "status": "running",
            "hardware_summary": {"vcpu_cores": 4, "ram_gib": 8, "disk_gib": 80},
        }

    def remove_server(self, server_id, *, destroy=False):
        self.removed.append((server_id, bool(destroy)))
        return {"id": server_id, "destroy": bool(destroy)}


def test_inventory_list_filters_are_scriptable() -> None:
    control = load_module("arclink_control.py", "arclink_control_inventory_filters")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_filters")
    conn = memory_db(control)

    iad = inventory.register_inventory_machine(
        conn,
        provider="manual",
        hostname="worker-iad.example.test",
        ssh_host="10.0.0.10",
        ssh_user="arclink",
        region="iad",
        status="ready",
        capacity_slots=4,
    )
    inventory.register_inventory_machine(
        conn,
        provider="manual",
        hostname="worker-sfo.example.test",
        ssh_host="10.0.0.20",
        ssh_user="arclink",
        region="sfo",
        status="pending",
        capacity_slots=4,
    )

    ready = inventory.list_inventory_machines(conn, filters=["status=ready"])
    expect([row["hostname"] for row in ready] == ["worker-iad.example.test"], str(ready))

    by_region = inventory.list_inventory_machines(conn, filters=["region=iad", f"host_id={iad['machine_host_link']}"])
    expect(len(by_region) == 1 and by_region[0]["machine_id"] == iad["machine_id"], str(by_region))

    fuzzy = inventory.list_inventory_machines(conn, filters=["sfo"])
    expect(len(fuzzy) == 1 and fuzzy[0]["region"] == "sfo", str(fuzzy))

    try:
        inventory.list_inventory_machines(conn, filters=["token=secret"])
    except inventory.ArcLinkInventoryError as exc:
        expect("unsupported inventory filter" in str(exc), str(exc))
    else:
        raise AssertionError("unsupported filters should fail closed")

    print("PASS test_inventory_list_filters_are_scriptable")


def test_cloud_inventory_lifecycle_contract_is_provider_parity() -> None:
    control = load_module("arclink_control.py", "arclink_control_inventory_lifecycle_parity")
    inventory = load_module("arclink_inventory.py", "arclink_inventory_lifecycle_parity")

    for provider in ("hetzner", "linode"):
        conn = memory_db(control)
        client = _FakeCloudClient(provider)
        hostname = f"{provider}-worker.example.test"

        result = inventory.create_cloud_inventory_machine(
            conn,
            provider=provider,
            client=client,
            hostname=hostname,
            server_type="cx22" if provider == "hetzner" else "g6-standard-2",
            image="ubuntu-24.04" if provider == "hetzner" else "linode/ubuntu24.04",
            region="fsn1" if provider == "hetzner" else "us-east",
            ssh_keys=["fleet-key"],
            capacity_slots=4,
            tags={"provider_parity": provider},
            idempotency_key=f"{provider}-parity-create",
        )
        replay = inventory.create_cloud_inventory_machine(
            conn,
            provider=provider,
            client=client,
            hostname=hostname,
            server_type="cx22" if provider == "hetzner" else "g6-standard-2",
            image="ubuntu-24.04" if provider == "hetzner" else "linode/ubuntu24.04",
            region="fsn1" if provider == "hetzner" else "us-east",
            ssh_keys=["fleet-key"],
            capacity_slots=4,
            tags={"provider_parity": provider},
            idempotency_key=f"{provider}-parity-create",
        )
        duplicate = inventory.create_cloud_inventory_machine(
            conn,
            provider=provider,
            client=client,
            hostname=hostname,
            server_type="cx32" if provider == "hetzner" else "g6-standard-4",
            image="ubuntu-24.04" if provider == "hetzner" else "linode/ubuntu24.04",
            region="fsn1" if provider == "hetzner" else "us-east",
            idempotency_key=f"{provider}-parity-duplicate",
        )

        expect(client.created == 1, f"{provider} create was not idempotent: {client.created}")
        expect(replay["replay"] is True and replay["status"] == result["status"], str(replay))
        expect(duplicate["status"] == "existing", str(duplicate))
        machine = result["machine"]

        try:
            inventory.remove_cloud_inventory_machine(conn, key=machine["machine_id"], client=client, destroy=True)
        except inventory.ArcLinkInventoryError as exc:
            expect("drain" in str(exc), str(exc))
        else:
            raise AssertionError(f"{provider} removal must require drain or force")

        inventory.drain_inventory_machine(conn, machine["machine_id"])
        removed = inventory.remove_cloud_inventory_machine(
            conn,
            key=machine["machine_id"],
            client=client,
            destroy=True,
            idempotency_key=f"{provider}-parity-remove",
        )
        remove_replay = inventory.remove_cloud_inventory_machine(
            conn,
            key=machine["machine_id"],
            client=client,
            destroy=True,
            idempotency_key=f"{provider}-parity-remove",
        )

        expected_resource = "h-1" if provider == "hetzner" else "l-1"
        expect(client.removed == [(expected_resource, True)], str(client.removed))
        expect(removed["machine"]["status"] == "removed", str(removed))
        expect(remove_replay["replay"] is True, str(remove_replay))
        row = conn.execute(
            """
            SELECT result_json
            FROM arclink_operation_idempotency
            WHERE operation_kind = ? AND idempotency_key = ?
            """,
            (f"inventory_{provider}_create", f"{provider}-parity-create"),
        ).fetchone()
        expect(json.loads(row["result_json"])["status"] == result["status"], str(dict(row)))

    print("PASS test_cloud_inventory_lifecycle_contract_is_provider_parity")


if __name__ == "__main__":
    test_inventory_list_filters_are_scriptable()
    test_cloud_inventory_lifecycle_contract_is_provider_parity()
