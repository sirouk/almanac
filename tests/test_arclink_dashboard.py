#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
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
    conn.execute(
        """
        INSERT INTO arclink_wrapped_reports (
          report_id, user_id, period, period_start, period_end, status,
          ledger_json, novelty_score, delivery_channel, created_at, delivered_at
        ) VALUES (?, ?, 'daily', '2026-05-13T00:00:00+00:00', '2026-05-14T00:00:00+00:00',
          'generated', ?, 72.5, 'telegram', ?, '')
        """,
        (
            "wrap_dashboard",
            prepared["user_id"],
            json.dumps(
                {
                    "formula_version": "wrapped_novelty_v1",
                    "plain_text": "ArcLink Wrapped report with sk_test_dashboard_secret",
                    "markdown": "# ArcLink Wrapped",
                    "stats": [{"key": "signal_variety", "label": "Signal variety", "value": 4}],
                    "source_counts": {"events": 1},
                },
                sort_keys=True,
            ),
            control.utc_now_iso(),
        ),
    )
    onboarding.record_arclink_onboarding_first_agent_contact(
        conn,
        session_id=prepared["session_id"],
        channel="web",
        channel_identity="dashboard@example.test",
    )
    return prepared


def test_user_dashboard_read_model_projects_safe_operational_summary() -> None:
    control = load_module("arclink_control.py", "arclink_control_dashboard_user_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_dashboard_user_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_user_test")
    conn = memory_db(control)
    prepared = seed_dashboard(control, onboarding, conn)

    view = dashboard.read_arclink_user_dashboard(conn, user_id=prepared["user_id"])
    expect(view["user"]["email"] == "dashboard@example.test", str(view))
    expect(
        {section["section"] for section in view["sections"]}
        == {
            "deployment_health",
            "access_links",
            "wrapped",
            "bot_setup",
            "files",
            "code",
            "terminal",
            "hermes",
            "qmd_memory",
            "skills",
            "model",
            "billing",
            "security",
            "support",
        },
        str(view["sections"]),
    )
    expect(view["entitlement"]["state"] == "paid", str(view))
    expect(view["entitlement"]["renewal_lifecycle"]["provider_access"] == "allowed", str(view["entitlement"]))
    expect(len(view["deployments"]) == 1, str(view))
    deployment = view["deployments"][0]
    section_index = {section["section"]: section for section in deployment["sections"]}
    expect(deployment["deployment_id"] == prepared["deployment_id"], str(deployment))
    expect(deployment["agent_label"] == "Dashboard Person", str(deployment))
    expect(deployment["access"]["urls"]["dashboard"] == "https://u-amber-vault-1a2b.example.test", str(deployment))
    expect(section_index["files"]["label"] == "Drive", str(section_index["files"]))
    expect(section_index["files"]["url"] == "https://u-amber-vault-1a2b.example.test/drive", str(section_index["files"]))
    expect(section_index["code"]["url"] == "https://u-amber-vault-1a2b.example.test/code", str(section_index["code"]))
    expect(section_index["terminal"]["url"] == "https://hermes-amber-vault-1a2b.example.test/terminal", str(section_index["terminal"]))
    expect(section_index["hermes"]["label"] == "Hermes Dashboard", str(section_index["hermes"]))
    expect(section_index["hermes"]["url"] == "https://hermes-amber-vault-1a2b.example.test", str(section_index["hermes"]))
    expect(section_index["wrapped"]["status"] == "ready", str(section_index["wrapped"]))
    expect(view["wrapped"]["wrapped_frequency"] == "daily", str(view["wrapped"]))
    expect(view["wrapped"]["reports"][0]["report_id"] == "wrap_dashboard", str(view["wrapped"]))
    expect("sk_test_dashboard_secret" not in view["wrapped"]["reports"][0]["plain_text"], str(view["wrapped"]["reports"][0]))
    expect(section_index["security"]["status"] == "masked", str(section_index["security"]))
    expect(section_index["support"]["status"] == "available", str(section_index["support"]))
    expect(deployment["billing"]["subscriptions"][0]["status"] == "active", str(deployment["billing"]))
    expect(deployment["billing"]["renewal_lifecycle"]["provider_access"] == "allowed", str(deployment["billing"]))
    expect(deployment["bot_contact"]["first_contacted"], str(deployment["bot_contact"]))
    expect(deployment["model"]["model_id"] == "model-default", str(deployment["model"]))
    expect(deployment["notion_setup"]["status"] == "available", str(deployment["notion_setup"]))
    expect(
        deployment["notion_setup"]["callback_url"] == "https://u-amber-vault-1a2b.example.test/notion/webhook",
        str(deployment["notion_setup"]),
    )
    expect(deployment["notion_setup"]["verification"]["live_workspace"] == "proof_gated", str(deployment["notion_setup"]))
    expect(deployment["freshness"]["qmd"]["status"] == "healthy", str(deployment["freshness"]))
    expect(deployment["freshness"]["memory"]["status"] == "planned", str(deployment["freshness"]))
    expect(deployment["recent_events"][0]["event_type"] == "provisioning_rendered", str(deployment["recent_events"]))

    text = json.dumps(view, sort_keys=True)
    for forbidden in ("sk_", "whsec_", "xoxb-", "ntn_", "123456:"):
        expect(forbidden not in text, text)
    expect("metadata_json" not in text, text)
    print("PASS test_user_dashboard_read_model_projects_safe_operational_summary")


def test_user_dashboard_projects_local_notion_ssot_verification_without_secret_token() -> None:
    control = load_module("arclink_control.py", "arclink_control_dashboard_notion_setup_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_dashboard_notion_setup_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_notion_setup_test")
    conn = memory_db(control)
    prepared = seed_dashboard(control, onboarding, conn)
    now = control.utc_now_iso()

    conn.execute(
        """
        UPDATE arclink_onboarding_sessions
        SET metadata_json = ?, updated_at = ?
        WHERE session_id = ?
        """,
        (
            json.dumps(
                {
                    "connect_notion_requested_at": now,
                    "connect_notion_user_marked_ready_at": now,
                    "connect_notion_public_status": "ready_for_dashboard_verification",
                },
                sort_keys=True,
            ),
            now,
            prepared["session_id"],
        ),
    )
    control.upsert_setting(conn, "notion_webhook_verification_token", "token_configured_placeholder")
    control.upsert_setting(conn, "notion_webhook_verification_token_installed_at", now)
    control.upsert_setting(conn, "notion_webhook_verified_at", now)
    control.upsert_setting(conn, "notion_webhook_verified_by", "operator")
    conn.execute(
        """
        INSERT INTO notion_index_documents (
          doc_key, root_id, source_page_id, source_page_url, file_path,
          page_title, section_heading, section_ordinal, content_hash,
          indexed_at, state
        ) VALUES (
          'doc_dashboard_notion', 'root_test', 'page_test',
          'https://www.notion.so/shared-root', '/tmp/notion-shared.md',
          'Shared Root', 'Summary', 0, 'hash-local', ?, 'active'
        )
        """,
        (now,),
    )
    conn.commit()

    view = dashboard.read_arclink_user_dashboard(conn, user_id=prepared["user_id"])
    setup = view["deployments"][0]["notion_setup"]
    expect(setup["status"] == "verified", str(setup))
    expect(setup["public_status"] == "ready_for_dashboard_verification", str(setup))
    expect(setup["webhook"]["configured"] is True, str(setup))
    expect(setup["webhook"]["verified"] is True, str(setup))
    expect(setup["webhook"]["verified_at"] == now, str(setup))
    expect(setup["index"]["status"] == "available", str(setup))
    expect(setup["verification"]["email_share"] == "not_proof", str(setup))
    expect(setup["verification"]["live_workspace"] == "proof_gated", str(setup))
    text = json.dumps(view, sort_keys=True)
    expect("token_configured_placeholder" not in text, text)
    expect("notion_webhook_verification_token" not in text, text)
    print("PASS test_user_dashboard_projects_local_notion_ssot_verification_without_secret_token")


def test_operator_evidence_template_state_is_computed_from_template_file() -> None:
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_template_state_test")
    with tempfile.TemporaryDirectory() as tmp:
        template = Path(tmp) / "evidence.md"
        missing = dashboard.operator_evidence_template_state({"ARCLINK_LIVE_EVIDENCE_TEMPLATE": str(template)})
        expect(missing["ready"] is False, str(missing))
        template.write_text("# Evidence\n\n## Run\n\n## Credentials\n\n## Result\n", encoding="utf-8")
        ready = dashboard.operator_evidence_template_state({"ARCLINK_LIVE_EVIDENCE_TEMPLATE": str(template)})
        expect(ready["ready"] is True, str(ready))
        template.write_text("# Evidence\n\n## Run\n", encoding="utf-8")
        incomplete = dashboard.operator_evidence_template_state({"ARCLINK_LIVE_EVIDENCE_TEMPLATE": str(template)})
        expect(incomplete["ready"] is False, str(incomplete))
        expect("Credentials" in incomplete["missing_markers"], str(incomplete))
    print("PASS test_operator_evidence_template_state_is_computed_from_template_file")


def test_user_dashboard_canonicalizes_tailnet_path_app_urls() -> None:
    control = load_module("arclink_control.py", "arclink_control_dashboard_tailnet_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_dashboard_tailnet_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_tailnet_test")
    conn = memory_db(control)
    prepared = seed_dashboard(control, onboarding, conn)
    urls = {
        "dashboard": "https://worker.example.test/u/amber-vault-1a2b",
        "files": "https://worker.example.test/u/amber-vault-1a2b/drive",
        "code": "https://worker.example.test/u/amber-vault-1a2b/code",
        "hermes": "https://worker.example.test/u/amber-vault-1a2b/hermes",
        "notion": "https://worker.example.test/u/amber-vault-1a2b/notion/webhook",
    }
    conn.execute(
        """
        UPDATE arclink_deployments
        SET metadata_json = ?
        WHERE deployment_id = ?
        """,
        (
            json.dumps(
                {
                    "ingress_mode": "tailscale",
                    "tailscale_dns_name": "worker.example.test",
                    "tailscale_host_strategy": "path",
                    "tailnet_service_ports": {"hermes": 8443},
                    "access_urls": urls,
                },
                sort_keys=True,
            ),
            prepared["deployment_id"],
        ),
    )
    conn.commit()

    view = dashboard.read_arclink_user_dashboard(conn, user_id=prepared["user_id"])
    deployment = view["deployments"][0]
    section_index = {section["section"]: section for section in deployment["sections"]}
    expect(deployment["access"]["urls"]["dashboard"] == "https://worker.example.test:8443", str(deployment))
    expect(deployment["access"]["urls"]["hermes"] == "https://worker.example.test:8443", str(deployment))
    expect(section_index["files"]["url"] == "https://worker.example.test:8443/drive", str(section_index["files"]))
    expect(section_index["code"]["url"] == "https://worker.example.test:8443/code", str(section_index["code"]))
    expect(section_index["terminal"]["url"] == "https://worker.example.test:8443/terminal", str(section_index["terminal"]))
    print("PASS test_user_dashboard_canonicalizes_tailnet_path_app_urls")


def test_user_dashboard_withholds_unpublished_tailnet_app_urls() -> None:
    control = load_module("arclink_control.py", "arclink_control_dashboard_tailnet_unavailable_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_dashboard_tailnet_unavailable_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_tailnet_unavailable_test")
    conn = memory_db(control)
    prepared = seed_dashboard(control, onboarding, conn)
    conn.execute(
        """
        UPDATE arclink_deployments
        SET metadata_json = ?
        WHERE deployment_id = ?
        """,
        (
            json.dumps(
                {
                    "ingress_mode": "tailscale",
                    "tailscale_dns_name": "worker.example.test",
                    "tailscale_host_strategy": "path",
                    "tailnet_service_ports": {"hermes": 8443, "files": 8444, "code": 8445},
                    "tailnet_app_publication": {"status": "unavailable", "failed_roles": ["files"]},
                },
                sort_keys=True,
            ),
            prepared["deployment_id"],
        ),
    )
    conn.commit()

    view = dashboard.read_arclink_user_dashboard(conn, user_id=prepared["user_id"])
    deployment = view["deployments"][0]
    section_index = {section["section"]: section for section in deployment["sections"]}
    links = {link["role"]: link["url"] for link in section_index["access_links"]["links"]}
    expect(links == {"Hermes Dashboard": "https://worker.example.test/u/amber-vault-1a2b"}, str(links))
    expect(section_index["files"]["status"] == "pending" and not section_index["files"]["url"], str(section_index["files"]))
    expect(section_index["code"]["status"] == "pending" and not section_index["code"]["url"], str(section_index["code"]))
    expect(section_index["hermes"]["status"] == "pending" and not section_index["hermes"]["url"], str(section_index["hermes"]))
    print("PASS test_user_dashboard_withholds_unpublished_tailnet_app_urls")


def test_admin_dashboard_filters_funnel_health_jobs_drift_and_failures() -> None:
    control = load_module("arclink_control.py", "arclink_control_dashboard_admin_test")
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
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_cancelled_drift",
        user_id=prepared["user_id"],
        prefix="cancelled-drift",
        base_domain="example.test",
        status="torn_down",
    )
    control.append_arclink_event(
        conn,
        subject_kind="deployment",
        subject_id="dep_cancelled_drift",
        event_type="dns_drift",
        metadata={"kind": "missing", "hostname": "u-cancelled-drift.example.test"},
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

    all_view = dashboard.read_arclink_admin_dashboard(conn, channel="web")
    expect(all(item["deployment_id"] != "dep_cancelled_drift" for item in all_view["dns_drift"]), str(all_view["dns_drift"]))
    expect(all_view["wrapped"]["reports_by_status"]["generated"] == 1, str(all_view["wrapped"]))
    expect("plain_text" not in json.dumps(all_view["wrapped"]), str(all_view["wrapped"]))
    expect(any(section["section"] == "wrapped" for section in all_view["sections"]), str(all_view["sections"]))
    view = dashboard.read_arclink_admin_dashboard(conn, channel="web", deployment_id=prepared["deployment_id"])
    section_index = {section["section"]: section for section in view["sections"]}
    expect(
        set(section_index)
        == {
            "onboarding_funnel",
            "users",
            "deployments",
            "wrapped",
            "payments",
            "infrastructure",
            "bots",
            "security_abuse",
            "releases_maintenance",
            "logs_events",
            "audit",
            "queued_actions",
        },
        str(view["sections"]),
    )
    expect(section_index["infrastructure"]["status"] == "degraded", str(section_index["infrastructure"]))
    expect(section_index["queued_actions"]["counts"]["queued"] == 1, str(section_index["queued_actions"]))
    expect(section_index["security_abuse"]["counts"]["active_admin_sessions"] == 0, str(section_index["security_abuse"]))
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


def test_admin_dashboard_counts_only_unrevoked_unexpired_active_sessions() -> None:
    control = load_module("arclink_control.py", "arclink_control_dashboard_session_count_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_dashboard_session_count_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_dashboard_session_count_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_session_count_test")
    conn = memory_db(control)
    prepared = seed_dashboard(control, onboarding, conn)
    api.upsert_arclink_admin(conn, admin_id="admin_sessions", email="sessions-admin@example.test", role="ops")
    api.create_arclink_user_session(conn, user_id=prepared["user_id"], session_id="usess_active")
    api.create_arclink_admin_session(conn, admin_id="admin_sessions", session_id="asess_active")
    now = control.utc_now_iso()

    conn.execute(
        """
        INSERT INTO arclink_user_sessions (
          session_id, user_id, session_token_hash, csrf_token_hash, status,
          metadata_json, created_at, last_seen_at, expires_at, revoked_at
        ) VALUES (?, ?, 'hash', 'csrf', 'active', '{}', ?, ?, ?, '')
        """,
        ("usess_expired", prepared["user_id"], now, now, "2000-01-01T00:00:00+00:00"),
    )
    conn.execute(
        """
        INSERT INTO arclink_user_sessions (
          session_id, user_id, session_token_hash, csrf_token_hash, status,
          metadata_json, created_at, last_seen_at, expires_at, revoked_at
        ) VALUES (?, ?, 'hash', 'csrf', 'active', '{}', ?, ?, ?, ?)
        """,
        ("usess_revoked", prepared["user_id"], now, now, "2999-01-01T00:00:00+00:00", now),
    )
    conn.execute(
        """
        INSERT INTO arclink_admin_sessions (
          session_id, admin_id, role, session_token_hash, csrf_token_hash, status,
          mfa_verified_at, metadata_json, created_at, last_seen_at, expires_at, revoked_at
        ) VALUES (?, 'admin_sessions', 'ops', 'hash', 'csrf', 'active', '', '{}', ?, ?, ?, '')
        """,
        ("asess_expired", now, now, "2000-01-01T00:00:00+00:00"),
    )
    conn.execute(
        """
        INSERT INTO arclink_admin_sessions (
          session_id, admin_id, role, session_token_hash, csrf_token_hash, status,
          mfa_verified_at, metadata_json, created_at, last_seen_at, expires_at, revoked_at
        ) VALUES (?, 'admin_sessions', 'ops', 'hash', 'csrf', 'active', '', '{}', ?, ?, ?, ?)
        """,
        ("asess_revoked", now, now, "2999-01-01T00:00:00+00:00", now),
    )
    conn.commit()

    view = dashboard.read_arclink_admin_dashboard(conn)
    counts = {section["section"]: section["counts"] for section in view["sections"]}
    security = counts["security_abuse"]
    expect(security["active_user_sessions"] == 1, str(security))
    expect(security["active_admin_sessions"] == 1, str(security))
    print("PASS test_admin_dashboard_counts_only_unrevoked_unexpired_active_sessions")


def main() -> int:
    test_user_dashboard_read_model_projects_safe_operational_summary()
    test_user_dashboard_projects_local_notion_ssot_verification_without_secret_token()
    test_operator_evidence_template_state_is_computed_from_template_file()
    test_user_dashboard_canonicalizes_tailnet_path_app_urls()
    test_user_dashboard_withholds_unpublished_tailnet_app_urls()
    test_admin_dashboard_filters_funnel_health_jobs_drift_and_failures()
    test_admin_dashboard_counts_only_unrevoked_unexpired_active_sessions()
    print("PASS all 7 ArcLink dashboard tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
