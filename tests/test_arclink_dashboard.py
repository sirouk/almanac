#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


@contextmanager
def temp_env(values: dict[str, str | None]):
    previous = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


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


def rollout_state_roots(deployment_id: str) -> dict[str, str]:
    root = f"/arcdata/deployments/{deployment_id}"
    return {
        "root": root,
        "config": f"{root}/config",
        "state": f"{root}/state",
        "vault": f"{root}/vault",
        "hermes_home": f"{root}/state/hermes-home",
    }


def test_user_dashboard_read_model_projects_safe_operational_summary() -> None:
    control = load_module("arclink_control.py", "arclink_control_dashboard_user_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_dashboard_user_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_user_test")
    conn = memory_db(control)
    prepared = seed_dashboard(control, onboarding, conn)

    with temp_env({"ARCLINK_NOTION_WEBHOOK_PUBLIC_URL": "https://control.example.ts.net/notion/webhook"}):
        view = dashboard.read_arclink_user_dashboard(conn, user_id=prepared["user_id"])
    expect(view["user"]["email"] == "dashboard@example.test", str(view))
    expect(
        {section["section"] for section in view["sections"]}
        == {
            "deployment_health",
            "access_links",
            "wrapped",
            "academy_training",
            "bot_setup",
            "backup",
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
    expect(section_index["academy_training"]["status"] == "not_started", str(section_index["academy_training"]))
    expect(view["academy_training"]["status"] == "not_started", str(view["academy_training"]))
    expect(view["wrapped"]["wrapped_frequency"] == "daily", str(view["wrapped"]))
    expect(view["wrapped"]["reports"][0]["report_id"] == "wrap_dashboard", str(view["wrapped"]))
    expect("sk_test_dashboard_secret" not in view["wrapped"]["reports"][0]["plain_text"], str(view["wrapped"]["reports"][0]))
    expect(section_index["security"]["status"] == "masked", str(section_index["security"]))
    expect(section_index["support"]["status"] == "available", str(section_index["support"]))
    expect(deployment["billing"]["subscriptions"][0]["status"] == "active", str(deployment["billing"]))
    expect(deployment["billing"]["renewal_lifecycle"]["provider_access"] == "allowed", str(deployment["billing"]))
    expect(deployment["bot_contact"]["first_contacted"], str(deployment["bot_contact"]))
    expect(deployment["backup_setup"]["status"] == "not_requested", str(deployment["backup_setup"]))
    expect(section_index["backup"]["status"] == "not_requested", str(section_index["backup"]))
    expect(deployment["model"]["model_id"] == "model-default", str(deployment["model"]))
    expect(deployment["notion_setup"]["status"] == "available", str(deployment["notion_setup"]))
    expect(
        deployment["notion_setup"]["callback_url"] == "https://control.example.ts.net/notion/webhook",
        str(deployment["notion_setup"]),
    )
    with temp_env(
        {
            "ARCLINK_NOTION_WEBHOOK_PUBLIC_URL": None,
            "ARCLINK_TAILSCALE_CONTROL_URL": None,
            "ARCLINK_TAILSCALE_DNS_NAME": "control.example.ts.net",
            "ARCLINK_TAILSCALE_NOTION_PATH": "/notion/webhook",
            "ARCLINK_TAILSCALE_HTTPS_PORT": None,
            "TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT": None,
            "TAILSCALE_SERVE_PORT": "8444",
        }
    ):
        tailnet_view = dashboard.read_arclink_user_dashboard(conn, user_id=prepared["user_id"])
    tailnet_callback = tailnet_view["deployments"][0]["notion_setup"]["callback_url"]
    expect(tailnet_callback == "https://control.example.ts.net/notion/webhook", tailnet_callback)
    expect(":8444/notion/webhook" not in tailnet_callback, tailnet_callback)
    expect(deployment["notion_setup"]["verification"]["live_workspace"] == "proof_gated", str(deployment["notion_setup"]))
    expect(deployment["freshness"]["qmd"]["status"] == "healthy", str(deployment["freshness"]))
    expect(deployment["freshness"]["memory"]["status"] == "planned", str(deployment["freshness"]))
    expect(deployment["recent_events"][0]["event_type"] == "provisioning_rendered", str(deployment["recent_events"]))

    text = json.dumps(view, sort_keys=True)
    for forbidden in ("sk_", "whsec_", "xoxb-", "ntn_", "123456:"):
        expect(forbidden not in text, text)
    expect("metadata_json" not in text, text)
    print("PASS test_user_dashboard_read_model_projects_safe_operational_summary")


def test_user_dashboard_uses_deployment_provider_metadata_for_model_card() -> None:
    control = load_module("arclink_control.py", "arclink_control_dashboard_provider_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_dashboard_provider_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_provider_test")
    conn = memory_db(control)
    prepared = seed_dashboard(control, onboarding, conn)
    row = conn.execute(
        "SELECT metadata_json FROM arclink_deployments WHERE deployment_id = ?",
        (prepared["deployment_id"],),
    ).fetchone()
    metadata = json.loads(row["metadata_json"])
    metadata["provider_id"] = "anthropic"
    metadata["selected_model_id"] = "claude-opus-4-7"
    conn.execute(
        "UPDATE arclink_deployments SET metadata_json = ? WHERE deployment_id = ?",
        (json.dumps(metadata, sort_keys=True), prepared["deployment_id"]),
    )
    conn.commit()

    with temp_env({"ARCLINK_PRIMARY_PROVIDER": "chutes"}):
        view = dashboard.read_arclink_user_dashboard(conn, user_id=prepared["user_id"])
    model = view["deployments"][0]["model"]
    expect(model["provider"] == "anthropic", str(model))
    expect(model["model_id"] == "model-default", str(model))
    expect(model["credential_state"] == "secret_ref_pending", str(model))
    expect("allow_inference" not in model and "budget" not in model, str(model))
    print("PASS test_user_dashboard_uses_deployment_provider_metadata_for_model_card")


def test_user_dashboard_chutes_budget_available_cents_subtracts_open_reservations() -> None:
    # billing-H5: the dashboard chutes inference-provider budget card must expose available_cents
    # = max(0, remaining - open reservations) so the displayed headroom matches
    # what the router will allow, not the settled-only remaining_cents.
    control = load_module("arclink_control.py", "arclink_control_dashboard_available_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_dashboard_available_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_available_test")
    conn = memory_db(control)
    prepared = seed_dashboard(control, onboarding, conn)
    conn.execute(
        "UPDATE arclink_deployments SET metadata_json = ? WHERE deployment_id = ?",
        (
            json.dumps(
                {
                    "selected_model_id": "model-default",
                    "chutes": {  # inference provider budget block
                        "secret_ref": f"secret://arclink/chutes/{prepared['deployment_id']}",
                        "monthly_budget_cents": 100,
                        "used_cents": 30,
                    },
                },
                sort_keys=True,
            ),
            prepared["deployment_id"],
        ),
    )
    conn.execute(
        """
        INSERT INTO arclink_llm_budget_reservations (
          reservation_id, request_id, deployment_id, user_id, reserved_cents, status, created_at
        ) VALUES ('llmres_open', 'llmreq_open', ?, ?, 25, 'reserved', '2026-06-19T00:00:00+00:00')
        """,
        (prepared["deployment_id"], prepared["user_id"]),
    )
    conn.commit()

    with temp_env({"ARCLINK_PRIMARY_PROVIDER": "chutes"}):
        view = dashboard.read_arclink_user_dashboard(conn, user_id=prepared["user_id"])
    budget = view["deployments"][0]["model"]["budget"]
    expect(budget["remaining_cents"] == 70, str(budget))
    expect(budget["reserved_cents"] == 25, str(budget))
    expect(budget["available_cents"] == 45, f"available must subtract open reservations: {budget}")
    print("PASS test_user_dashboard_chutes_budget_available_cents_subtracts_open_reservations")


def test_user_dashboard_projects_staged_academy_review_status() -> None:
    control = load_module("arclink_control.py", "arclink_control_dashboard_academy_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_dashboard_academy_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_academy_test")
    academy = load_module("arclink_academy_trainer.py", "arclink_academy_dashboard_test")
    conn = memory_db(control)
    prepared = seed_dashboard(control, onboarding, conn)
    source = academy.fake_academy_source(
        source_id="src-dashboard-academy",
        lane_id="wikimedia",
        title="Dashboard Academy Source",
        origin_url="https://example.test/wiki/dashboard-academy",
        retrieved_at="2026-05-27T00:00:00Z",
        license_status="cc-by-sa",
        permission_status="public_allowed",
        storage_policy="derived_summary",
        content="Academy status should be compact enough for Captain dashboard review.",
        citations=["dashboard source", "review source", "quality source"],
        metadata={"revision": "dashboard-academy-1", "official": True, "examples": True},
    )
    manifest = academy.build_academy_corpus(
        role_id="role-dashboard-academy",
        role_title="Dashboard Academy Agent",
        topic="dashboard Academy review",
        sources=[source],
        created_at="2026-05-27T00:00:00Z",
    )
    application = academy.build_agent_application_plan(
        manifest,
        agent_id="agent-dashboard-academy",
        created_at="2026-05-27T01:00:00Z",
    )
    status = academy.build_academy_review_status(
        manifest=manifest,
        application_plan=application,
        staged_at="2026-05-27T02:00:00Z",
    )
    conn.execute(
        """
        INSERT INTO arclink_crew_recipes (
          recipe_id, user_id, preset, capacity, role, mission, treatment,
          soul_overlay_json, applied_at, archived_at, status
        ) VALUES (?, ?, 'Frontier', 'development', 'founder', 'ship',
          'peer', ?, ?, '', 'active')
        """,
        (
            "crew_dashboard_academy",
            prepared["user_id"],
            json.dumps({"crew_recipe_text": "Crew Recipe", "academy_training": status}, sort_keys=True),
            control.utc_now_iso(),
        ),
    )
    conn.commit()

    view = dashboard.read_arclink_user_dashboard(conn, user_id=prepared["user_id"])
    academy_status = view["academy_training"]
    deployment = view["deployments"][0]
    section_index = {section["section"]: section for section in deployment["sections"]}
    expect(academy_status["status"] == "ready_for_review", str(academy_status))
    expect(academy_status["source_count"] == 1, str(academy_status))
    expect("PG-PROVIDER" in academy_status["proof_gates"], str(academy_status))
    expect(section_index["academy_training"]["status"] == "ready_for_review", str(section_index["academy_training"]))
    expect(deployment["academy_training"]["manifest_id"] == manifest.manifest_id, str(deployment["academy_training"]))
    text = json.dumps(view, sort_keys=True)
    expect("secret://" not in text and "sk_" not in text, text)
    print("PASS test_user_dashboard_projects_staged_academy_review_status")


def test_dashboard_exposes_academy_weekly_and_graduation_status() -> None:
    control = load_module("arclink_control.py", "arclink_control_dashboard_academy_weekly_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_dashboard_academy_weekly_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_academy_weekly_test")
    academy = load_module("arclink_academy_trainer.py", "arclink_academy_dashboard_weekly_test")
    conn = memory_db(control)
    prepared = seed_dashboard(control, onboarding, conn)
    source = academy.fake_academy_source(
        source_id="src-dashboard-weekly",
        lane_id="wikimedia",
        title="Dashboard Weekly Academy Source",
        origin_url="https://example.test/wiki/dashboard-weekly",
        retrieved_at="2026-05-27T00:00:00Z",
        license_status="cc-by-sa",
        permission_status="public_allowed",
        storage_policy="derived_summary",
        content="Academy weekly status should be compact enough for Captain dashboard review.",
        citations=["dashboard source", "weekly source", "quality source"],
        metadata={"revision": "dashboard-weekly-1", "official": True, "examples": True},
    )
    manifest = academy.build_academy_corpus(
        role_id="role-dashboard-weekly",
        role_title="Dashboard Weekly Agent",
        topic="dashboard weekly Academy review",
        sources=[source],
        created_at="2026-05-27T00:00:00Z",
    )
    application = academy.build_agent_application_plan(
        manifest,
        agent_id="agent-dashboard-weekly",
        created_at="2026-05-27T01:00:00Z",
    )
    weekly = academy.build_continuing_education_plan(
        manifest,
        observed_sources={"src-dashboard-weekly": {"content_hash": "changed-" + manifest.sources["src-dashboard-weekly"]["content_hash"]}},
        checked_at="2026-06-15T00:00:00Z",
        next_review_at="2026-06-22T00:00:00Z",
    )
    graduation = academy.academy_graduation_gate(manifest=manifest)
    status = academy.build_academy_review_status(
        manifest=manifest,
        application_plan=application,
        continuing_education_plan=weekly,
        graduation_gate=graduation,
        staged_at="2026-06-15T01:00:00Z",
    )
    conn.execute(
        """
        INSERT INTO arclink_crew_recipes (
          recipe_id, user_id, preset, capacity, role, mission, treatment,
          soul_overlay_json, applied_at, archived_at, status
        ) VALUES (?, ?, 'Frontier', 'development', 'founder', 'ship',
          'peer', ?, ?, '', 'active')
        """,
        (
            "crew_dashboard_weekly",
            prepared["user_id"],
            json.dumps({"crew_recipe_text": "Crew Recipe", "academy_training": status}, sort_keys=True),
            control.utc_now_iso(),
        ),
    )
    conn.commit()

    view = dashboard.read_arclink_user_dashboard(conn, user_id=prepared["user_id"])
    academy_status = view["academy_training"]
    section_index = {section["section"]: section for section in view["deployments"][0]["sections"]}
    academy_section = section_index["academy_training"]
    expect(academy_status["weekly_review_status"] == "ready_for_review", str(academy_status))
    expect(academy_status["evaluation_status"] == "ready_for_review", str(academy_status))
    expect(academy_status["graduation_status"] == "blocked_by_live_proof", str(academy_status))
    expect(academy_status["next_review_at"] == "2026-06-22T00:00:00Z", str(academy_status))
    expect(academy_status["review_needed_count"] == 1, str(academy_status))
    expect(academy_status["blocked_source_count"] == 0, str(academy_status))
    expect(academy_section["weekly_review_status"] == "ready_for_review", str(academy_section))
    expect(academy_section["graduation_status"] == "blocked_by_live_proof", str(academy_section))
    expect(academy_section["next_review_at"] == "2026-06-22T00:00:00Z", str(academy_section))
    expect(academy_section["review_needed_count"] == 1, str(academy_section))
    text = json.dumps(view, sort_keys=True)
    expect("Academy weekly status should" not in text, text)
    expect("secret://" not in text and "sk_" not in text, text)
    print("PASS test_dashboard_exposes_academy_weekly_and_graduation_status")


def test_user_dashboard_share_inbox_counts_pending_owner_and_recipient_grants() -> None:
    control = load_module("arclink_control.py", "arclink_control_dashboard_share_inbox_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_dashboard_share_inbox_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_share_inbox_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_dashboard_share_inbox_test")
    conn = memory_db(control)
    owner = seed_dashboard(control, onboarding, conn)
    recipient_session = onboarding.create_or_resume_arclink_onboarding_session(
        conn,
        channel="web",
        channel_identity="dashboard-recipient@example.test",
        session_id="onb_dashboard_share_recipient",
        email_hint="dashboard-recipient@example.test",
        display_name_hint="Dashboard Recipient",
        selected_model_id="model-default",
    )
    recipient = onboarding.prepare_arclink_onboarding_deployment(
        conn,
        session_id=recipient_session["session_id"],
        base_domain="example.test",
        prefix="dashboard-recipient-1a2b",
    )
    control.set_arclink_user_entitlement(conn, user_id=recipient["user_id"], entitlement_state="paid")

    pending = api.create_user_share_grant_for_owner(
        conn,
        owner_user_id=owner["user_id"],
        recipient_user_id=recipient["user_id"],
        resource_kind="drive",
        resource_root="vault",
        resource_path="/Projects/pending",
        owner_deployment_id=owner["deployment_id"],
        display_name="Pending Share",
    ).payload["grant"]
    approved = api.create_user_share_grant_for_owner(
        conn,
        owner_user_id=owner["user_id"],
        recipient_user_id=recipient["user_id"],
        resource_kind="code",
        resource_root="workspace",
        resource_path="/repo",
        owner_deployment_id=owner["deployment_id"],
        display_name="Approved Share",
    ).payload["grant"]
    now = control.utc_now_iso()
    conn.execute(
        """
        UPDATE arclink_share_grants
        SET status = 'approved', approved_at = ?, updated_at = ?
        WHERE grant_id = ?
        """,
        (now, now, approved["grant_id"]),
    )
    conn.commit()

    owner_view = dashboard.read_arclink_user_dashboard(conn, user_id=owner["user_id"])
    owner_inbox = owner_view["share_inbox"]
    expect(owner_inbox["pending_owner_approvals"] == 1, str(owner_inbox))
    expect(owner_inbox["waiting_on_owner_approval"] == 0, str(owner_inbox))
    expect(owner_inbox["pending_recipient_acceptance"] == 0, str(owner_inbox))
    expect(owner_inbox["attention_count"] == 1, str(owner_inbox))
    expect(owner_inbox["recovery_action"] == "open_dashboard_share_inbox", str(owner_inbox))

    recipient_view = dashboard.read_arclink_user_dashboard(conn, user_id=recipient["user_id"])
    recipient_inbox = recipient_view["share_inbox"]
    expect(recipient_inbox["pending_owner_approvals"] == 0, str(recipient_inbox))
    expect(recipient_inbox["waiting_on_owner_approval"] == 1, str(recipient_inbox))
    expect(recipient_inbox["pending_recipient_acceptance"] == 1, str(recipient_inbox))
    expect(recipient_inbox["attention_count"] == 2, str(recipient_inbox))
    expect(pending["grant_id"] != approved["grant_id"], str((pending, approved)))
    print("PASS test_user_dashboard_share_inbox_counts_pending_owner_and_recipient_grants")


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
    expect(setup["status"] == "local_metadata_verified", str(setup))
    expect(setup["public_status"] == "ready_for_dashboard_verification", str(setup))
    expect(setup["webhook"]["configured"] is True, str(setup))
    expect(setup["webhook"]["verified"] is True, str(setup))
    expect(setup["webhook"]["status"] == "webhook_verified", str(setup))
    expect(setup["webhook"]["verified_at"] == now, str(setup))
    expect(setup["index"]["status"] == "available", str(setup))
    expect(setup["verification"]["state"] == "local_metadata_verified", str(setup))
    expect(setup["verification"]["dashboard"] == "local_metadata_verified", str(setup))
    expect(setup["verification"]["setup_intent"] == "ready_for_dashboard_verification", str(setup))
    expect(setup["verification"]["local_metadata"] == "local_metadata_verified", str(setup))
    expect(setup["verification"]["email_share"] == "not_proof", str(setup))
    expect(setup["verification"]["user_owned_oauth"] == "policy_question", str(setup))
    expect(setup["verification"]["shared_root_live_read"] == "proof_gated", str(setup))
    expect(setup["verification"]["brokered_write_preflight"] == "proof_gated", str(setup))
    expect(setup["verification"]["live_workspace"] == "proof_gated", str(setup))
    expect(setup["status"] != "verified", str(setup))
    expect(setup["verification"]["dashboard"] != "verified", str(setup))
    text = json.dumps(view, sort_keys=True)
    expect("token_configured_placeholder" not in text, text)
    expect("notion_webhook_verification_token" not in text, text)
    print("PASS test_user_dashboard_projects_local_notion_ssot_verification_without_secret_token")


def test_user_dashboard_projects_raven_backup_pending_key_setup() -> None:
    control = load_module("arclink_control.py", "arclink_control_dashboard_backup_setup_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_dashboard_backup_setup_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_backup_setup_test")
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
                    "config_backup_owner_repo": "sirouk/arclink-agent-backup",
                    "config_backup_public_status": "repo_recorded_pending_key_setup",
                    "config_backup_requested_at": now,
                },
                sort_keys=True,
            ),
            now,
            prepared["session_id"],
        ),
    )
    conn.commit()

    view = dashboard.read_arclink_user_dashboard(conn, user_id=prepared["user_id"])
    deployment = view["deployments"][0]
    backup = deployment["backup_setup"]
    section_index = {section["section"]: section for section in deployment["sections"]}
    expect(backup["status"] == "pending_key_setup", str(backup))
    expect(backup["model"] == "public_preparation_then_operator_verification", str(backup))
    expect(backup["public_status"] == "repo_recorded_pending_key_setup", str(backup))
    expect(backup["owner_repo"] == "sirouk/arclink-agent-backup", str(backup))
    expect(backup["settings_url"] == "https://github.com/sirouk/arclink-agent-backup/settings/keys", str(backup))
    expect(backup["requested_at"] == now, str(backup))
    expect(backup["verification"]["repo"] == "recorded", str(backup))
    expect(backup["verification"]["deploy_key"] == "pending_operator_setup", str(backup))
    expect(backup["verification"]["github_write_check"] == "not_run", str(backup))
    expect(backup["verification"]["backup_activation"] == "not_active", str(backup))
    expect(backup["verification"]["restore_proof"] == "proof_gated", str(backup))
    expect(section_index["backup"]["status"] == "pending_key_setup", str(section_index["backup"]))
    text = json.dumps(view, sort_keys=True)
    for forbidden in ("sk_", "ghp_", "deploy_key_private", "-----BEGIN"):
        expect(forbidden not in text, text)
    print("PASS test_user_dashboard_projects_raven_backup_pending_key_setup")


def test_user_dashboard_backup_deploy_key_request_exposes_public_key_without_activation() -> None:
    control = load_module("arclink_control.py", "arclink_control_dashboard_backup_key_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_dashboard_backup_key_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_backup_key_test")
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
                    "config_backup_owner_repo": "sirouk/arclink-agent-backup",
                    "config_backup_public_status": "repo_recorded_pending_key_setup",
                    "config_backup_requested_at": now,
                },
                sort_keys=True,
            ),
            now,
            prepared["session_id"],
        ),
    )
    conn.commit()

    with tempfile.TemporaryDirectory() as staging_dir:
        backup = dashboard.request_arclink_backup_deploy_key(
            conn,
            user_id=prepared["user_id"],
            deployment_id=prepared["deployment_id"],
            key_staging_dir=staging_dir,
        )
        public_key = backup["deploy_key"]["public_key"]
        expect(public_key.startswith("ssh-ed25519 "), str(backup))
        expect(backup["status"] == "pending_key_setup", str(backup))
        expect(backup["deploy_key"]["status"] == "staged_pending_github_install", str(backup))
        expect(backup["deploy_key"]["private_key_storage"] == "server_side_only", str(backup))
        expect(backup["verification"]["github_write_check"] == "not_run", str(backup))
        expect(backup["verification"]["backup_activation"] == "not_active", str(backup))
        expect(backup["verification"]["restore_proof"] == "proof_gated", str(backup))
        expect(backup["settings_url"] == "https://github.com/sirouk/arclink-agent-backup/settings/keys", str(backup))

        key_files = list(Path(staging_dir).glob("*/arclink-agent-backup-ed25519"))
        expect(len(key_files) == 1 and key_files[0].is_file(), f"expected one server-side private key under {staging_dir}")
        text = json.dumps(backup, sort_keys=True)
        private_key_text = key_files[0].read_text(encoding="utf-8")
        expect("BEGIN OPENSSH PRIVATE KEY" in private_key_text, "expected real private key to stay server-side")
        expect("BEGIN OPENSSH PRIVATE KEY" not in text, text)
        expect(str(key_files[0]) not in text and staging_dir not in text, text)

        view = dashboard.read_arclink_user_dashboard(conn, user_id=prepared["user_id"])
        viewed_backup = view["deployments"][0]["backup_setup"]
        expect(viewed_backup["deploy_key"]["public_key"] == public_key, str(viewed_backup))
        expect(viewed_backup["verification"]["deploy_key"] == "staged_pending_github_install", str(viewed_backup))
        expect(viewed_backup["verification"]["backup_activation"] == "not_active", str(viewed_backup))

    print("PASS test_user_dashboard_backup_deploy_key_request_exposes_public_key_without_activation")


def test_backup_verification_state_records_failed_closed_without_activation() -> None:
    control = load_module("arclink_control.py", "arclink_control_dashboard_backup_verify_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_dashboard_backup_verify_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_backup_verify_test")
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
                    "config_backup_owner_repo": "sirouk/arclink-agent-backup",
                    "config_backup_public_status": "repo_recorded_pending_key_setup",
                    "config_backup_requested_at": now,
                },
                sort_keys=True,
            ),
            now,
            prepared["session_id"],
        ),
    )
    conn.commit()

    with tempfile.TemporaryDirectory() as staging_dir:
        staged = dashboard.request_arclink_backup_deploy_key(
            conn,
            user_id=prepared["user_id"],
            deployment_id=prepared["deployment_id"],
            key_staging_dir=staging_dir,
        )
        public_key = staged["deploy_key"]["public_key"]
        verified = dashboard.request_arclink_backup_write_check(
            conn,
            user_id=prepared["user_id"],
            deployment_id=prepared["deployment_id"],
        )
        expect(verified["deploy_key"]["public_key"] == public_key, str(verified))
        expect(verified["verification"]["github_write_check"] == "failed_closed", str(verified))
        expect("PG-BACKUP" in verified["verification"]["github_write_check_reason"], str(verified))
        expect(verified["verification"]["backup_activation"] == "not_active", str(verified))
        expect(verified["verification"]["restore_proof"] == "proof_gated", str(verified))

        row = conn.execute(
            "SELECT metadata_json FROM arclink_deployments WHERE deployment_id = ?",
            (prepared["deployment_id"],),
        ).fetchone()
        metadata = json.loads(row["metadata_json"])
        expect(metadata["backup_github_write_check"] == "failed_closed", str(metadata))
        expect(metadata["backup_activation"] == "not_active", str(metadata))

        view = dashboard.read_arclink_user_dashboard(conn, user_id=prepared["user_id"])
        viewed_backup = view["deployments"][0]["backup_setup"]
        expect(viewed_backup["verification"]["github_write_check"] == "failed_closed", str(viewed_backup))
        expect(viewed_backup["verification"]["backup_activation"] == "not_active", str(viewed_backup))

    print("PASS test_backup_verification_state_records_failed_closed_without_activation")


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


def test_operator_snapshot_honors_live_journey_env_alternates() -> None:
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_operator_env_alternates_test")
    journey = load_module("arclink_live_journey.py", "arclink_live_journey_operator_env_alternates_test")
    env: dict[str, str] = {}
    for step in journey.build_journey():
        for key in step.required_env:
            env[key] = "present"
    env.pop("CLOUDFLARE_API_TOKEN", None)
    env["CLOUDFLARE_API_TOKEN_REF"] = "secret://arclink/cloudflare/token"

    snapshot = dashboard.build_operator_snapshot(
        env=env,
        docker_binary="arclink-test-missing-docker-binary",
    )
    missing = [
        name
        for blocker in snapshot["live_journey"]["blockers"]
        for name in blocker["missing_env"]
    ]
    expect("CLOUDFLARE_API_TOKEN" not in missing, str(snapshot["live_journey"]))
    print("PASS test_operator_snapshot_honors_live_journey_env_alternates")


def test_operator_snapshot_reads_latest_evidence_status_from_db() -> None:
    control = load_module("arclink_control.py", "arclink_control_dashboard_evidence_status_test")
    evidence = load_module("arclink_evidence.py", "arclink_evidence_dashboard_status_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_evidence_status_test")
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "arclink-control.sqlite3"
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            control.ensure_schema(conn)
            ledger = evidence.EvidenceLedger(run_id="run_operator_snapshot", commit_hash="abc123")
            ledger.add(evidence.EvidenceRecord(step_name="proof", status="passed", timestamp=1.0))
            evidence.store_evidence_run(conn, ledger=ledger, deployment_id="arcdep_dash")
        finally:
            conn.close()

        snapshot = dashboard.build_operator_snapshot(
            env={"ARCLINK_DB_PATH": str(db_path)},
            docker_binary="arclink-test-missing-docker-binary",
        )
    latest = snapshot["evidence"]["latest_run"]
    expect(latest["status"] == "passed", str(latest))
    expect(latest["run_id"] == "run_operator_snapshot", str(latest))
    governance = snapshot["evidence"]["governance"]
    expect(governance["production_ready"] is False, str(governance))
    expect("workspace" in governance["missing_journeys"], str(governance))
    expect(governance["journeys"]["hosted"]["status"] == "passed", str(governance))
    print("PASS test_operator_snapshot_reads_latest_evidence_status_from_db")


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
                    "tailnet_app_publication": {"status": "published", "successful_roles": ["hermes"], "failed_roles": []},
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


def test_user_dashboard_withholds_tailnet_urls_until_publication_record_exists() -> None:
    control = load_module("arclink_control.py", "arclink_control_dashboard_tailnet_missing_publish_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_dashboard_tailnet_missing_publish_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_tailnet_missing_publish_test")
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
                    "tailnet_service_ports": {"hermes": 8443},
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
    expect(deployment["access"]["urls"] == {}, str(deployment))
    expect(section_index["files"]["status"] == "pending" and not section_index["files"]["url"], str(section_index["files"]))
    expect(section_index["code"]["status"] == "pending" and not section_index["code"]["url"], str(section_index["code"]))
    expect(section_index["hermes"]["status"] == "pending" and not section_index["hermes"]["url"], str(section_index["hermes"]))
    print("PASS test_user_dashboard_withholds_tailnet_urls_until_publication_record_exists")


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
    expect("provisioning_readiness" in view, str(view.keys()))
    expect(view["provisioning_readiness"]["live_proof_required"] is True, str(view["provisioning_readiness"]))
    expect(view["provisioning_readiness"]["proof_gate"] == "PG-FLEET/PG-PROVISION", str(view["provisioning_readiness"]))
    expect(view["action_intents"][0]["status"] == "queued", str(view["action_intents"]))
    expect(view["dns_drift"][0]["metadata"]["kind"] == "missing", str(view["dns_drift"]))
    expect(view["audit_rows"][0]["action"] == "admin_action:restart", str(view["audit_rows"]))
    expect(any(item["kind"] == "provisioning_job" for item in view["recent_failures"]), str(view["recent_failures"]))
    expect(any(item["kind"] == "service_health" for item in view["recent_failures"]), str(view["recent_failures"]))
    expect("raw_json" not in json.dumps(view, sort_keys=True), str(view))
    print("PASS test_admin_dashboard_filters_funnel_health_jobs_drift_and_failures")


def test_scale_operations_snapshot_exposes_rollout_dry_run_plan() -> None:
    control = load_module("arclink_control.py", "arclink_control_dashboard_rollout_plan_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_rollout_plan_test")
    rollout = load_module("arclink_rollout.py", "arclink_rollout_dashboard_rollout_plan_test")
    conn = memory_db(control)
    control.upsert_arclink_user(
        conn,
        user_id="user-rollout",
        email="rollout@example.test",
        display_name="Rollout Captain",
        entitlement_state="paid",
    )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_rollout_dash",
        user_id="user-rollout",
        prefix="rollout-dash",
        base_domain="example.test",
        status="active",
        metadata={
            "release_version": "v1.0.0",
            "state_roots": rollout_state_roots("dep_rollout_dash"),
            "dashboard_password": "secret://arclink/deployments/dep_rollout_dash/dashboard",
        },
    )
    for service_name in ("hermes-gateway", "hermes-dashboard", "qmd-mcp"):
        control.upsert_arclink_service_health(
            conn,
            deployment_id="dep_rollout_dash",
            service_name=service_name,
            status="healthy",
        )
    before_rollouts = conn.execute("SELECT COUNT(*) AS n FROM arclink_rollouts").fetchone()["n"]
    before_actions = conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"]

    snapshot = dashboard.build_scale_operations_snapshot(
        conn,
        rollout_target_version="v2.0.0",
        rollout_batch_size=1,
    )
    plan = snapshot["rollout_dry_run_plan"]

    expect(snapshot["rollout_surface"] == "local_job_queueable_with_bounded_fake_execution", str(snapshot))
    expect("PG-UPGRADE/PG-HERMES" in snapshot["rollout_execution_boundary"], str(snapshot))
    expect(plan["status"] == "ready", str(plan))
    expect(plan["candidate_count"] == 1, str(plan))
    expect(plan["batches"][0]["deployment_ids"] == ["dep_rollout_dash"], str(plan["batches"]))
    expect(plan["execution"]["enabled"] is False, str(plan["execution"]))
    expect(plan["mutation_performed"] is False, str(plan))
    expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_rollouts").fetchone()["n"] == before_rollouts, "no rollout rows")
    expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"] == before_actions, "no actions queued")
    expect("secret://" not in json.dumps(plan, sort_keys=True), str(plan))

    env_snapshot = dashboard.build_scale_operations_snapshot(
        conn,
        env={
            "ARCLINK_ROLLOUT_TARGET_VERSION": "v3.0.0",
            "ARCLINK_FLEET_PLACEMENT_STRATEGY": "spread",
            "ARCLINK_CONTROL_PROVISIONER_ENABLED": "1",
        },
    )
    expect(env_snapshot["inventory"]["strategy"] == "spread", str(env_snapshot["inventory"]))
    expect(env_snapshot["rollout_dry_run_plan"]["target_version"] == "v3.0.0", str(env_snapshot["rollout_dry_run_plan"]))

    job = rollout.materialize_arcpod_update_rollout_job(
        conn,
        plan=plan,
        action_id="act_dash_rollout_status",
        idempotency_key="dash-rollout-status",
    )
    execution = rollout.execute_arcpod_update_rollout_batch(
        conn,
        rollout_group_id=job["rollout_group_id"],
        executor={
            "adapter": "fake",
            "record_only": True,
            "results": {"dep_rollout_dash": {"status": "failed", "reason": "fake local apply stopped"}},
        },
    )
    status_snapshot = dashboard.build_scale_operations_snapshot(conn)
    active = status_snapshot["active_rollouts"]
    expect(execution["status"] == "failed", str(execution))
    expect(len(active) == 1, str(active))
    expect(active[0]["status"] == "failed", str(active))
    expect(active[0]["execution_status"] == "failed", str(active))
    expect(active[0]["execution_adapter"] == "fake", str(active))
    expect(active[0]["health_smoke_status"] == "blocked_by_local_failure", str(active))
    expect(active[0]["proof_gate"] == "PG-UPGRADE/PG-HERMES", str(active))
    expect(active[0]["live_proof_required"] is True, str(active))
    expect("secret://" not in json.dumps(active, sort_keys=True), str(active))
    print("PASS test_scale_operations_snapshot_exposes_rollout_dry_run_plan")


def test_admin_dashboard_counts_only_unrevoked_unexpired_active_sessions() -> None:
    control = load_module("arclink_control.py", "arclink_control_dashboard_session_count_test")
    onboarding = load_module("arclink_onboarding.py", "arclink_onboarding_dashboard_session_count_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_dashboard_session_count_test")
    dashboard = load_module("arclink_dashboard.py", "arclink_dashboard_session_count_test")
    conn = memory_db(control)
    prepared = seed_dashboard(control, onboarding, conn)
    api.upsert_arclink_admin(conn, admin_id="admin_sessions", email="sessions-admin@example.test", role="ops")
    with temp_env({"ARCLINK_SESSION_HASH_PEPPER": "dashboard-session-count-test-pepper"}):
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
    test_user_dashboard_uses_deployment_provider_metadata_for_model_card()
    test_user_dashboard_chutes_budget_available_cents_subtracts_open_reservations()
    test_user_dashboard_projects_staged_academy_review_status()
    test_dashboard_exposes_academy_weekly_and_graduation_status()
    test_user_dashboard_share_inbox_counts_pending_owner_and_recipient_grants()
    test_user_dashboard_projects_local_notion_ssot_verification_without_secret_token()
    test_user_dashboard_projects_raven_backup_pending_key_setup()
    test_user_dashboard_backup_deploy_key_request_exposes_public_key_without_activation()
    test_backup_verification_state_records_failed_closed_without_activation()
    test_operator_evidence_template_state_is_computed_from_template_file()
    test_operator_snapshot_honors_live_journey_env_alternates()
    test_operator_snapshot_reads_latest_evidence_status_from_db()
    test_user_dashboard_canonicalizes_tailnet_path_app_urls()
    test_user_dashboard_withholds_unpublished_tailnet_app_urls()
    test_user_dashboard_withholds_tailnet_urls_until_publication_record_exists()
    test_admin_dashboard_filters_funnel_health_jobs_drift_and_failures()
    test_scale_operations_snapshot_exposes_rollout_dry_run_plan()
    test_admin_dashboard_counts_only_unrevoked_unexpired_active_sessions()
    print("PASS all ArcLink dashboard tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
