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
    control = load_module("almanac_control.py", "almanac_control_ingress_dns_test")
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


def main() -> int:
    test_dns_reconciler_persists_desired_records_and_records_drift_events()
    test_traefik_dynamic_labels_match_golden_file_for_all_host_roles()
    print("PASS all 2 ArcLink ingress tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
