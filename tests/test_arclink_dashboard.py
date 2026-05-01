#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sqlite3
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


def memory_db(control):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    control.ensure_schema(conn)
    return conn


def seed_dashboard(control, onboarding, conn):
    session = onboarding.create_or_resume_arclink_onboarding_session(
        conn,
        channel="web",
        channel_identity="dashboard@example.test",
        session_id="onb_dashboard",
        email_hint="dashboard@example.test",
        display_name_hint="Dashboard Person",
        selected_model_id="model-default",
    )
    prepared = onboarding.prepare_arclink_onboarding_deployment(
        conn,
        session_id=session["session_id"],
        base_domain="example.test",
        prefix="amber-vault-1a2b",
    )
    control.set_arclink_user_entitlement(conn, user_id=prepared["user_id"], entitlement_state="paid")
    control.upsert_arclink_subscription_mirror(
        conn,
        subscription_id="sub_local",
        user_id=prepared["user_id"],
        stripe_customer_id="cus_safe",
        stripe_subscription_id="sub_safe",
        status="active",
    )
    control.upsert_arclink_service_health(
        conn,
        deployment_id=prepared["deployment_id"],
        service_name="qmd-mcp",
        status="healthy",
        detail={"freshness": "planned"},
    )
    control.upsert_arclink_service_health(
        conn,
        deployment_id=prepared["deployment_id"],
        service_name="memory-synth",
        status="planned",
        detail={"freshness": "placeholder"},
    )
    control.append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=prepared["deployment_id"],
        event_type="provisioning_rendered",
        metadata={"source": "test"},
    )
    onboarding.record_arclink_onboarding_first_agent_contact(
        conn,
        session_id=prepared["session_id"],
        channel="web",
        channel_identity="dashboard@example.test",
    )
    return prepared


def test_user_dashboard_read_model_projects_safe_operational_summary() -> None:
    control = load_module("almanac_control.py", "almanac_control_dashboard_user_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_dashboard_user_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_user_test")
    conn = memory_db(control)
    prepared = seed_dashboard(control, onboarding, conn)

    view = dashboard.read_arclink_user_dashboard(conn, user_id=prepared["user_id"])
    expect(view["user"]["email"] == "dashboard@example.test", str(view))
    expect(view["entitlement"]["state"] == "paid", str(view))
    expect(len(view["deployments"]) == 1, str(view))
    deployment = view["deployments"][0]
    expect(deployment["deployment_id"] == prepared["deployment_id"], str(deployment))
    expect(deployment["access"]["urls"]["dashboard"] == "https://u-amber-vault-1a2b.example.test", str(deployment))
    expect(deployment["billing"]["subscriptions"][0]["status"] == "active", str(deployment["billing"]))
    expect(deployment["bot_contact"]["first_contacted"], str(deployment["bot_contact"]))
    expect(deployment["model"]["model_id"] == "model-default", str(deployment["model"]))
    expect(deployment["freshness"]["qmd"]["status"] == "healthy", str(deployment["freshness"]))
    expect(deployment["freshness"]["memory"]["status"] == "planned", str(deployment["freshness"]))
    expect(deployment["recent_events"][0]["event_type"] == "provisioning_rendered", str(deployment["recent_events"]))

    text = json.dumps(view, sort_keys=True)
    for forbidden in ("sk_", "whsec_", "xoxb-", "ntn_", "123456:"):
        expect(forbidden not in text, text)
    expect("metadata_json" not in text, text)
    print("PASS test_user_dashboard_read_model_projects_safe_operational_summary")


def test_admin_dashboard_filters_funnel_health_jobs_drift_and_failures() -> None:
    control = load_module("almanac_control.py", "almanac_control_dashboard_admin_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_dashboard_admin_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_admin_test")
    conn = memory_db(control)
    prepared = seed_dashboard(control, onboarding, conn)
    control.upsert_arclink_service_health(
        conn,
        deployment_id=prepared["deployment_id"],
        service_name="health-watch",
        status="degraded",
    )
    control.create_arclink_provisioning_job(
        conn,
        job_id="job_failed",
        deployment_id=prepared["deployment_id"],
        job_kind="docker_dry_run",
        idempotency_key="failed-job",
    )
    control.transition_arclink_provisioning_job(conn, job_id="job_failed", status="running")
    control.transition_arclink_provisioning_job(conn, job_id="job_failed", status="failed", error="render failed")
    control.append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id=prepared["deployment_id"],
        event_type="dns_drift",
        metadata={"kind": "missing", "hostname": "u-amber-vault-1a2b.example.test"},
    )
    dashboard.queue_arclink_admin_action(
        conn,
        admin_id="admin_1",
        action_type="restart",
        target_kind="deployment",
        target_id=prepared["deployment_id"],
        reason="restart unhealthy service",
        idempotency_key="dashboard-restart-1",
    )

    view = dashboard.read_arclink_admin_dashboard(conn, channel="web", deployment_id=prepared["deployment_id"])
    event_counts = {row["event_type"]: row["count"] for row in view["onboarding_funnel"]["events"]}
    expect(event_counts["started"] == 1 and event_counts["first_agent_contact"] == 1, str(event_counts))
    expect(view["deployments"][0]["deployment_id"] == prepared["deployment_id"], str(view["deployments"]))
    expect(any(row["status"] == "degraded" for row in view["service_health"]), str(view["service_health"]))
    expect(view["provisioning_jobs"][0]["status"] == "failed", str(view["provisioning_jobs"]))
    expect(view["action_intents"][0]["status"] == "queued", str(view["action_intents"]))
    expect(view["dns_drift"][0]["metadata"]["kind"] == "missing", str(view["dns_drift"]))
    expect(view["audit_rows"][0]["action"] == "admin_action:restart", str(view["audit_rows"]))
    expect(any(item["kind"] == "provisioning_job" for item in view["recent_failures"]), str(view["recent_failures"]))
    expect(any(item["kind"] == "service_health" for item in view["recent_failures"]), str(view["recent_failures"]))
    expect("raw_json" not in json.dumps(view, sort_keys=True), str(view))
    print("PASS test_admin_dashboard_filters_funnel_health_jobs_drift_and_failures")


def main() -> int:
    test_user_dashboard_read_model_projects_safe_operational_summary()
    test_admin_dashboard_filters_funnel_health_jobs_drift_and_failures()
    print("PASS all 2 ArcLink dashboard tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
