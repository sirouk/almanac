#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
FIXTURES = REPO / "tests" / "fixtures"


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


def test_dns_reconciler_persists_desired_records_and_records_drift_events() -> None:
    control = load_module("arclink_control.py", "arclink_control_ingress_dns_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_ingress_dns_test")
    ingress = load_module("arclink_ingress.py", "arclink_ingress_dns_test")
    conn = memory_db(control)
    cloudflare = adapters.FakeCloudflareClient()
    cloudflare.upsert_record(adapters.DnsRecord(hostname="u-abc123.example.test", record_type="CNAME", target="old.example.test"))

    drift = ingress.reconcile_arclink_dns(
        conn,
        deployment_id="dep_1",
        prefix="abc123",
        base_domain="example.test",
        target="edge.example.test",
        cloudflare=cloudflare,
    )
    drift_kinds = {(item.kind, item.hostname) for item in drift}
    expect(("changed", "u-abc123.example.test") in drift_kinds, str(drift))
    expect(("missing", "files-abc123.example.test") in drift_kinds, str(drift))
    records = conn.execute("SELECT hostname, record_type, target, status FROM arclink_dns_records ORDER BY hostname").fetchall()
    expect(len(records) == 4, str([dict(row) for row in records]))
    expect({row["status"] for row in records} == {"desired"}, str([dict(row) for row in records]))
    events = conn.execute("SELECT event_type, metadata_json FROM arclink_events WHERE subject_id = 'dep_1'").fetchall()
    expect(len(events) == len(drift), str([dict(row) for row in events]))
    expect(all(row["event_type"] == "dns_drift" for row in events), str([dict(row) for row in events]))
    print("PASS test_dns_reconciler_persists_desired_records_and_records_drift_events")


def test_traefik_dynamic_labels_match_golden_file_for_all_host_roles() -> None:
    ingress = load_module("arclink_ingress.py", "arclink_ingress_traefik_test")
    actual = ingress.render_traefik_dynamic_labels(prefix="amber-vault-1a2b", base_domain="example.test")
    expected = json.loads((FIXTURES / "arclink_traefik_labels.golden.json").read_text(encoding="utf-8"))
    expect(actual == expected, json.dumps(actual, sort_keys=True, indent=2))
    expect(set(actual) == {"dashboard", "files", "code", "hermes"}, str(actual))
    print("PASS test_traefik_dynamic_labels_match_golden_file_for_all_host_roles")


def test_dns_provision_creates_records_and_marks_provisioned() -> None:
    control = load_module("arclink_control.py", "arclink_control_ingress_prov_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_ingress_prov_test")
    ingress = load_module("arclink_ingress.py", "arclink_ingress_prov_test")
    conn = memory_db(control)
    cloudflare = adapters.FakeCloudflareClient()

    records = ingress.provision_arclink_dns(
        conn,
        deployment_id="dep_prov_1",
        prefix="testprov",
        base_domain="example.test",
        target="edge.example.test",
        cloudflare=cloudflare,
    )
    expect(len(records) == 4, str(records))
    expect(len(cloudflare.records) == 4, str(cloudflare.records))
    db_records = conn.execute(
        "SELECT status FROM arclink_dns_records WHERE deployment_id = 'dep_prov_1'"
    ).fetchall()
    expect(all(r["status"] == "provisioned" for r in db_records), str([dict(r) for r in db_records]))
    events = conn.execute(
        "SELECT event_type FROM arclink_events WHERE subject_id = 'dep_prov_1' AND event_type = 'dns_provisioned'"
    ).fetchall()
    expect(len(events) == 1, str([dict(r) for r in events]))
    print("PASS test_dns_provision_creates_records_and_marks_provisioned")


def test_dns_teardown_removes_records_and_marks_torn_down() -> None:
    control = load_module("arclink_control.py", "arclink_control_ingress_tear_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_ingress_tear_test")
    ingress = load_module("arclink_ingress.py", "arclink_ingress_tear_test")
    conn = memory_db(control)
    cloudflare = adapters.FakeCloudflareClient()

    # First provision
    ingress.provision_arclink_dns(
        conn, deployment_id="dep_tear_1", prefix="teartest",
        base_domain="example.test", target="edge.example.test", cloudflare=cloudflare,
    )
    expect(len(cloudflare.records) == 4, "expected 4 records after provision")

    # Then teardown
    removed = ingress.teardown_arclink_dns(
        conn, deployment_id="dep_tear_1", prefix="teartest",
        base_domain="example.test", cloudflare=cloudflare,
    )
    expect(len(removed) == 4, f"expected 4 removed, got {len(removed)}")
    expect(len(cloudflare.records) == 0, "expected 0 records after teardown")
    db_records = conn.execute(
        "SELECT status FROM arclink_dns_records WHERE deployment_id = 'dep_tear_1'"
    ).fetchall()
    expect(all(r["status"] == "torn_down" for r in db_records), str([dict(r) for r in db_records]))
    events = conn.execute(
        "SELECT event_type FROM arclink_events WHERE subject_id = 'dep_tear_1' AND event_type = 'dns_teardown'"
    ).fetchall()
    expect(len(events) == 1, str([dict(r) for r in events]))
    print("PASS test_dns_teardown_removes_records_and_marks_torn_down")


def test_dns_provision_is_idempotent_on_retry() -> None:
    control = load_module("arclink_control.py", "arclink_control_ingress_retry_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_ingress_retry_test")
    ingress = load_module("arclink_ingress.py", "arclink_ingress_retry_test")
    conn = memory_db(control)
    cloudflare = adapters.FakeCloudflareClient()

    # Provision twice - should be idempotent
    ingress.provision_arclink_dns(
        conn, deployment_id="dep_retry", prefix="retrytest",
        base_domain="example.test", target="edge.example.test", cloudflare=cloudflare,
    )
    ingress.provision_arclink_dns(
        conn, deployment_id="dep_retry", prefix="retrytest",
        base_domain="example.test", target="edge2.example.test", cloudflare=cloudflare,
    )
    expect(len(cloudflare.records) == 4, "expected 4 records")
    # All should point to new target
    for rec in cloudflare.records.values():
        expect(rec.target == "edge2.example.test", f"expected updated target, got {rec.target}")
    print("PASS test_dns_provision_is_idempotent_on_retry")


def main() -> int:
    test_dns_reconciler_persists_desired_records_and_records_drift_events()
    test_traefik_dynamic_labels_match_golden_file_for_all_host_roles()
    test_dns_provision_creates_records_and_marks_provisioned()
    test_dns_teardown_removes_records_and_marks_torn_down()
    test_dns_provision_is_idempotent_on_retry()
    print("PASS all 5 ArcLink ingress tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
