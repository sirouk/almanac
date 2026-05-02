#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

from arclink_test_helpers import expect, load_module


def memory_db(control):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    control.ensure_schema(conn)
    return conn


def seed_ready_deployment(control, conn):
    control.upsert_arclink_user(
        conn,
        user_id="user_1",
        email="user@example.test",
        display_name="User One",
        entitlement_state="paid",
    )
    return control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_1",
        user_id="user_1",
        prefix="amber-vault-1234",
        base_domain="example.test",
        status="provisioning_ready",
    )


def worker_config(worker_mod, tmpdir, *, enabled=True, register_local=True):
    return worker_mod.SovereignWorkerConfig(
        enabled=enabled,
        ingress_mode="domain",
        base_domain="example.test",
        edge_target="edge.example.test",
        tailscale_dns_name="",
        tailscale_host_strategy="path",
        tailscale_https_port="443",
        tailscale_notion_path="/notion/webhook",
        state_root_base=f"{tmpdir}/deployments",
        cloudflare_zone_id="zone_fake",
        executor_adapter="fake",
        batch_size=5,
        max_attempts=3,
        register_local_host=register_local,
        local_hostname="worker-1.example.test",
        local_ssh_host="",
        local_ssh_user="root",
        local_region="us-east",
        local_capacity_slots=2,
        secret_store_dir=Path(tmpdir) / "secrets",
        env={
            "ARCLINK_BASE_DOMAIN": "example.test",
            "ARCLINK_PRIMARY_PROVIDER": "chutes",
            "ARCLINK_CHUTES_BASE_URL": "https://llm.chutes.ai/v1",
            "ARCLINK_CHUTES_DEFAULT_MODEL": "moonshotai/Kimi-K2.6-TEE",
        },
    )


def test_fake_sovereign_worker_applies_ready_deployment() -> None:
    control = load_module("arclink_control.py", "arclink_control_sovereign_apply")
    worker_mod = load_module("arclink_sovereign_worker.py", "arclink_sovereign_worker_apply")
    conn = memory_db(control)
    seed_ready_deployment(control, conn)
    with tempfile.TemporaryDirectory() as tmpdir:
        results = worker_mod.process_sovereign_batch(conn, worker=worker_config(worker_mod, tmpdir))

    expect(len(results) == 1, str(results))
    result = results[0]
    expect(result["status"] == "applied", str(result))
    expect(result["placement"]["hostname"] == "worker-1.example.test", str(result))
    expect("dashboard" in result["services"], str(result))
    dep = conn.execute("SELECT status FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone()
    expect(dep["status"] == "active", str(dict(dep)))
    job = conn.execute("SELECT job_kind, status, attempt_count FROM arclink_provisioning_jobs").fetchone()
    expect(job["job_kind"] == "sovereign_pod_apply" and job["status"] == "succeeded", str(dict(job)))
    expect(int(job["attempt_count"]) == 1, str(dict(job)))
    dns_statuses = {row["status"] for row in conn.execute("SELECT status FROM arclink_dns_records").fetchall()}
    expect(dns_statuses == {"provisioned"}, str(dns_statuses))
    health_statuses = {row["status"] for row in conn.execute("SELECT status FROM arclink_service_health").fetchall()}
    expect(health_statuses == {"healthy"}, str(health_statuses))
    event_types = {row["event_type"] for row in conn.execute("SELECT event_type FROM arclink_events").fetchall()}
    expect({"sovereign_provisioning_started", "sovereign_pod_applied", "user_handoff_ready"} <= event_types, str(event_types))
    print("PASS test_fake_sovereign_worker_applies_ready_deployment")


def test_tailscale_sovereign_worker_skips_cloudflare_dns() -> None:
    control = load_module("arclink_control.py", "arclink_control_sovereign_tailscale")
    worker_mod = load_module("arclink_sovereign_worker.py", "arclink_sovereign_worker_tailscale")
    conn = memory_db(control)
    seed_ready_deployment(control, conn)
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = worker_config(worker_mod, tmpdir)
        cfg = worker_mod.SovereignWorkerConfig(
            **{
                **cfg.__dict__,
                "ingress_mode": "tailscale",
                "base_domain": "worker.example.test",
                "edge_target": "worker.example.test",
                "tailscale_dns_name": "worker.example.test",
                "tailscale_host_strategy": "path",
                "env": {
                    **dict(cfg.env),
                    "ARCLINK_INGRESS_MODE": "tailscale",
                    "ARCLINK_TAILSCALE_DNS_NAME": "worker.example.test",
                    "ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY": "path",
                },
            }
        )
        results = worker_mod.process_sovereign_batch(conn, worker=cfg)

    expect(results[0]["status"] == "applied", str(results))
    expect(results[0]["dns_records"] == [], str(results))
    expect(results[0]["urls"]["dashboard"] == "https://worker.example.test/u/amber-vault-1234", str(results))
    dns_count = conn.execute("SELECT COUNT(*) AS c FROM arclink_dns_records").fetchone()["c"]
    expect(dns_count == 0, str(dns_count))
    event = conn.execute("SELECT metadata_json FROM arclink_events WHERE event_type = 'sovereign_pod_applied'").fetchone()
    expect('"ingress_mode": "tailscale"' in event["metadata_json"], event["metadata_json"])
    print("PASS test_tailscale_sovereign_worker_skips_cloudflare_dns")


def test_sovereign_worker_is_disabled_until_explicitly_enabled() -> None:
    control = load_module("arclink_control.py", "arclink_control_sovereign_disabled")
    worker_mod = load_module("arclink_sovereign_worker.py", "arclink_sovereign_worker_disabled")
    conn = memory_db(control)
    seed_ready_deployment(control, conn)
    with tempfile.TemporaryDirectory() as tmpdir:
        results = worker_mod.process_sovereign_batch(conn, worker=worker_config(worker_mod, tmpdir, enabled=False))
    expect(results == [{"status": "disabled", "reason": "ARCLINK_CONTROL_PROVISIONER_ENABLED is not set"}], str(results))
    job_count = conn.execute("SELECT COUNT(*) AS c FROM arclink_provisioning_jobs").fetchone()["c"]
    expect(job_count == 0, str(job_count))
    print("PASS test_sovereign_worker_is_disabled_until_explicitly_enabled")


def test_sovereign_worker_fails_closed_without_fleet_capacity() -> None:
    control = load_module("arclink_control.py", "arclink_control_sovereign_nohost")
    worker_mod = load_module("arclink_sovereign_worker.py", "arclink_sovereign_worker_nohost")
    conn = memory_db(control)
    seed_ready_deployment(control, conn)
    with tempfile.TemporaryDirectory() as tmpdir:
        results = worker_mod.process_sovereign_batch(
            conn,
            worker=worker_config(worker_mod, tmpdir, enabled=True, register_local=False),
        )
    expect(results[0]["status"] == "failed", str(results))
    expect("no eligible ArcLink fleet hosts" in results[0]["error"], str(results))
    dep = conn.execute("SELECT status FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone()
    expect(dep["status"] == "provisioning_failed", str(dict(dep)))
    print("PASS test_sovereign_worker_fails_closed_without_fleet_capacity")


def test_notion_webhook_secret_is_generated_without_notion_token() -> None:
    worker_mod = load_module("arclink_sovereign_worker.py", "arclink_sovereign_worker_notion_secret")
    with tempfile.TemporaryDirectory() as tmpdir:
        resolver = worker_mod.SovereignSecretResolver(
            env={},
            secret_store_dir=Path(tmpdir) / "store",
            materialization_root=Path(tmpdir) / "materialized",
        )
        resolved = resolver.materialize(
            "secret://arclink/notion/dep_1/webhook-secret",
            "/run/secrets/notion_webhook_secret",
        )
        secret_file = Path(resolved.source_path)
        expect(secret_file.exists(), "expected generated Notion webhook secret file")
        expect(secret_file.read_text(encoding="utf-8").strip().startswith("arc_"), "expected generated ArcLink secret")
    print("PASS test_notion_webhook_secret_is_generated_without_notion_token")


if __name__ == "__main__":
    test_fake_sovereign_worker_applies_ready_deployment()
    test_tailscale_sovereign_worker_skips_cloudflare_dns()
    test_sovereign_worker_is_disabled_until_explicitly_enabled()
    test_sovereign_worker_fails_closed_without_fleet_capacity()
    test_notion_webhook_secret_is_generated_without_notion_token()
    print("\nAll 5 Sovereign worker tests passed.")
