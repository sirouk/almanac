#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
CONTROL_PY = PYTHON_DIR / "arclink_control.py"
FLEET_PY = PYTHON_DIR / "arclink_fleet.py"
OPERATOR_RAVEN_PY = PYTHON_DIR / "arclink_operator_raven.py"
UPGRADE_POLICY_PY = PYTHON_DIR / "arclink_upgrade_policy.py"
CURATOR_TELEGRAM_PY = PYTHON_DIR / "arclink_curator_onboarding.py"
CURATOR_DISCORD_PY = PYTHON_DIR / "arclink_curator_discord_onboarding.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_config(path: Path, values: dict[str, str]) -> None:
    lines = [f"{key}={json.dumps(value)}" for key, value in values.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def config_values(root: Path) -> dict[str, str]:
    return {
        "ARCLINK_USER": "arclink",
        "ARCLINK_HOME": str(root / "home-arclink"),
        "ARCLINK_REPO_DIR": str(REPO),
        "ARCLINK_PRIV_DIR": str(root / "priv"),
        "STATE_DIR": str(root / "state"),
        "RUNTIME_DIR": str(root / "state" / "runtime"),
        "VAULT_DIR": str(root / "vault"),
        "ARCLINK_DB_PATH": str(root / "state" / "arclink-control.sqlite3"),
        "ARCLINK_AGENTS_STATE_DIR": str(root / "state" / "agents"),
        "ARCLINK_CURATOR_DIR": str(root / "state" / "curator"),
        "ARCLINK_CURATOR_MANIFEST": str(root / "state" / "curator" / "manifest.json"),
        "ARCLINK_CURATOR_HERMES_HOME": str(root / "state" / "curator" / "hermes-home"),
        "ARCLINK_ARCHIVED_AGENTS_DIR": str(root / "state" / "archived-agents"),
        "ARCLINK_RELEASE_STATE_FILE": str(root / "state" / "arclink-release.json"),
        "ARCLINK_QMD_URL": "http://127.0.0.1:8181/mcp",
        "ARCLINK_MCP_HOST": "127.0.0.1",
        "ARCLINK_MCP_PORT": "8282",
        "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "telegram",
        "OPERATOR_NOTIFY_CHANNEL_ID": "42",
    }


def seed_control_state(control, fleet, conn) -> None:
    user = control.upsert_arclink_user(
        conn,
        user_id="user-alex",
        email="alex@example.test",
        display_name="Alex Rivera",
        entitlement_state="paid",
        stripe_customer_id="cus_should_not_render",
    )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep-alex",
        user_id=str(user["user_id"]),
        prefix="alex-pod-1234",
        base_domain="example.test",
        agent_id="agent-alex",
        agent_title="Alex Agent",
        status="provisioning_failed",
        metadata={"dashboard_password": "secret://arclink/deployments/dep-alex/dashboard"},
    )
    fleet.register_fleet_host(
        conn,
        host_id="host-local",
        hostname="local-worker",
        region="iad",
        capacity_slots=4,
        metadata={"token_ref": "secret://arclink/fleet/local-worker"},
    )
    for deployment_id in ("dep-rollout-1", "dep-rollout-2"):
        root = f"/arcdata/deployments/{deployment_id}"
        control.reserve_arclink_deployment_prefix(
            conn,
            deployment_id=deployment_id,
            user_id=str(user["user_id"]),
            prefix=deployment_id,
            base_domain="example.test",
            status="active",
            metadata={
                "release_version": "v1.0.0",
                "state_roots": {
                    "root": root,
                    "config": f"{root}/config",
                    "state": f"{root}/state",
                    "vault": f"{root}/vault",
                    "hermes_home": f"{root}/state/hermes-home",
                },
            },
        )
        for service_name in ("hermes-gateway", "hermes-dashboard", "qmd-mcp"):
            control.upsert_arclink_service_health(
                conn,
                deployment_id=deployment_id,
                service_name=service_name,
                status="healthy",
            )


def with_seeded_db():
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_operator_raven_test")
    fleet = load_module(FLEET_PY, "arclink_fleet_operator_raven_test")
    raven = load_module(OPERATOR_RAVEN_PY, "arclink_operator_raven_test")
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    config_path = root / "config" / "arclink.env"
    write_config(config_path, config_values(root))
    old_env = os.environ.copy()
    os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
    try:
        cfg = control.Config.from_env()
        conn = control.connect_db(cfg)
        seed_control_state(control, fleet, conn)
        return tmp, old_env, conn, raven
    except Exception:
        os.environ.clear()
        os.environ.update(old_env)
        tmp.cleanup()
        raise


def cleanup_db(tmp: tempfile.TemporaryDirectory, old_env: dict[str, str]) -> None:
    os.environ.clear()
    os.environ.update(old_env)
    tmp.cleanup()


def seed_pin_upgrade_payload(
    conn,
    *,
    component: str,
    current: str = "aaaa1111",
    target: str = "bbbb2222",
    throttle_target: str = "",
    kind: str = "git-commit",
) -> str:
    import arclink_control as control

    field = "ref" if kind.startswith("git") else "version"
    effective_throttle = throttle_target or target
    conn.execute(
        """
        INSERT OR REPLACE INTO pin_upgrade_notifications (
          component, field, current_pin, target_value, first_seen_at,
          last_notified_at, notify_count, silenced, applied_at, extra_json
        ) VALUES (?, ?, ?, ?, '2026-06-01T00:00:00+00:00', NULL, 1, 0, NULL, ?)
        """,
        (
            component,
            field,
            current,
            effective_throttle,
            json.dumps({"raw_target": target, "throttle_target": effective_throttle}),
        ),
    )
    conn.commit()
    return control.register_pin_upgrade_action(
        conn,
        items=[
            {
                "component": component,
                "kind": kind,
                "field": field,
                "current": current,
                "target": target,
                "throttle_target": effective_throttle,
            }
        ],
        install_items=[
            {
                "component": component,
                "kind": kind,
                "field": field,
                "current": current,
                "target": target,
                "throttle_target": effective_throttle,
            }
        ],
    )


def test_operator_raven_status_is_read_only_and_truthful() -> None:
    tmp, old_env, conn, raven = with_seeded_db()
    try:
        before_actions = conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"]
        result = raven.dispatch_operator_raven_command(
            conn,
            "/operator_status",
            env={"ARCLINK_CONTROL_PROVISIONER_ENABLED": "1", "ARCLINK_EXECUTOR_ADAPTER": "fake"},
        )
        after_actions = conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"]
        text = result["message"]
        expect(result["handled"] is True, str(result))
        expect(result["mutation_performed"] is False, str(result))
        expect(before_actions == after_actions, "status command must not queue an action")
        expect("Operator Raven status" in text, text)
        expect("ready to provision ArcPods" in text, text)
        expect("Rollouts:" in text and "honor ARCLINK_EXECUTOR_ADAPTER" in text, text)
        expect("Queued/running operator actions:" in text, text)
        expect("/pod_repair" in text and "/rollout" in text and "/upgrade" in text, text)
        expect(result["provisioning_readiness"]["state"] == "ready_to_provision", str(result["provisioning_readiness"]))
        expect(result["provisioning_readiness"]["live_proof_required"] is True, str(result["provisioning_readiness"]))
        expect("PG-PROD" in text and "PG-UPGRADE" in text, text)
        expect("secret://" not in text, text)
        expect("cus_should_not_render" not in text, text)
        print("PASS test_operator_raven_status_is_read_only_and_truthful")
    finally:
        cleanup_db(tmp, old_env)


def test_operator_raven_agents_reports_arclink_arcpods_not_hermes_tasks() -> None:
    tmp, old_env, conn, raven = with_seeded_db()
    try:
        conn.execute(
            """
            INSERT INTO arclink_deployments (
              deployment_id, user_id, prefix, base_domain, agent_id, agent_title,
              status, metadata_json, created_at, updated_at
            ) VALUES (
              'operator', 'operator', 'operator-helm', 'example.test',
              'operator-agent', 'Operator Hermes', 'active', ?, '2026-05-29T00:00:00+00:00',
              '2026-05-29T00:00:00+00:00'
            )
            """,
            (json.dumps({"operator_agent": True, "dashboard_password": "secret://operator/password"}),),
        )
        conn.commit()

        result = raven.dispatch_operator_raven_command(conn, "/agents")
        text = result["message"]
        expect(result.get("command") == "agents", str(result))
        expect("Operator Raven ArcLink agents" in text, text)
        expect("Captain ArcPods: 3 total" in text and "2 active" in text, text)
        expect("dep-rollout-1" in text and "dep-rollout-2" in text, text)
        expect("Operator Hermes: active (operator)" in text, text)
        expect("Hermes /agents means internal helper/task agents" in text, text)
        expect("secret://" not in text and "dashboard_password" not in json.dumps(result), str(result))
        alias = raven.dispatch_operator_raven_command(conn, "/operator_agents")
        expect(alias.get("command") == "agents", str(alias))
        print("PASS test_operator_raven_agents_reports_arclink_arcpods_not_hermes_tasks")
    finally:
        cleanup_db(tmp, old_env)


def test_operator_raven_fleet_and_worker_probe_are_dry_run_only() -> None:
    tmp, old_env, conn, raven = with_seeded_db()
    try:
        fleet = raven.dispatch_operator_raven_command(conn, "/operator_fleet")
        expect("local-worker" in fleet["message"], fleet["message"])
        expect("secret://" not in fleet["message"], fleet["message"])

        blocked = raven.dispatch_operator_raven_command(conn, "/worker_probe host-local")
        expect("dry-run only" in blocked["message"], blocked["message"])

        dry_run = raven.dispatch_operator_raven_command(conn, "/worker_probe host-local --dry-run")
        expect("Worker probe dry-run" in dry_run["message"], dry_run["message"])
        expect("No SSH, provider, Docker, or health-probe command was run." in dry_run["message"], dry_run["message"])
        expect(dry_run["mutation_performed"] is False, str(dry_run))
        print("PASS test_operator_raven_fleet_and_worker_probe_are_dry_run_only")
    finally:
        cleanup_db(tmp, old_env)


def test_operator_raven_upgrade_policy_is_read_only_and_component_specific() -> None:
    tmp, old_env, conn, raven = with_seeded_db()
    try:
        before_actions = conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"]
        before_operator_actions = conn.execute("SELECT COUNT(*) AS n FROM operator_actions").fetchone()["n"]
        catalog = raven.dispatch_operator_raven_command(conn, "/upgrade_policy")
        text = catalog["message"]
        expect("Operator Raven upgrade policy" in text, text)
        expect("control plane first" in text, text)
        expect("arcpod-runtime" in text and "stateful-infra" in text and "worker-fabric" in text, text)
        expect("/pin_upgrade <component>" in text and "/fleet_drain <worker>" in text, text)
        expect(catalog["mutation_performed"] is False, str(catalog))
        expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"] == before_actions, "catalog must not queue admin action")
        expect(conn.execute("SELECT COUNT(*) AS n FROM operator_actions").fetchone()["n"] == before_operator_actions, "catalog must not queue operator action")

        hermes = raven.dispatch_operator_raven_command(conn, "/upgrade_policy hermes")
        hermes_text = hermes["message"]
        expect("Hermes Runtime" in hermes_text, hermes_text)
        expect("canary one ArcPod" in hermes_text, hermes_text)
        expect("PG-UPGRADE" in hermes_text and "PG-HERMES" in hermes_text, hermes_text)
        expect(hermes["upgrade_policy"]["policy"]["component"] == "hermes", str(hermes["upgrade_policy"]))

        docker = raven.dispatch_operator_raven_command(conn, "/update_policy docker")
        expect("/fleet_drain <worker>" in docker["message"], docker["message"])
        expect("Drain one worker" in docker["message"] and "one worker at a time" in docker["message"], docker["message"])

        bad = raven.dispatch_operator_raven_command(conn, "/upgrade_policy imaginary")
        expect("unknown ArcLink upgrade component" in bad["message"], bad["message"])
        print("PASS test_operator_raven_upgrade_policy_is_read_only_and_component_specific")
    finally:
        cleanup_db(tmp, old_env)


def test_upgrade_policy_catalog_is_sorted_grouped_and_read_only() -> None:
    policy = load_module(UPGRADE_POLICY_PY, "arclink_upgrade_policy_direct_test")
    catalog = policy.upgrade_policy_catalog()
    components = [item["component"] for item in catalog]
    rollout_order = [item["rollout_order"] for item in catalog]
    expect(components[0] == "arclink-control", str(components))
    expect(rollout_order == sorted(rollout_order), str(rollout_order))
    expect(set(policy.PIN_UPGRADE_COMPONENTS).issubset(set(components)), str(components))
    expect(policy.STATEFUL_PIN_UPGRADE_COMPONENTS == {"nextcloud", "postgres", "redis"}, str(policy.STATEFUL_PIN_UPGRADE_COMPONENTS))

    summary = policy.upgrade_policy_summary()
    expect(summary["mode"] == "catalog" and summary["mutation_performed"] is False, str(summary))
    expect(summary["default_sequence"] == components, str(summary))
    grouped = dict(policy.policy_components_by_scope(summary))
    expect("hermes" in grouped["arcpod-runtime"], str(grouped))
    expect("postgres" in grouped["stateful-infra"], str(grouped))

    hermes = policy.upgrade_policy_summary("hermes")
    expect(hermes["mode"] == "component" and hermes["mutation_performed"] is False, str(hermes))
    expect(hermes["policy"]["component"] == "hermes", str(hermes))
    expect("PG-HERMES" in hermes["policy"]["proof_gates"], str(hermes))
    expect(policy.upgrade_policy_for("plugins")["component"] == "dashboard-plugins", "plugins alias must normalize")
    expect(policy.upgrade_policy_for("wg")["component"] == "wireguard", "wg alias must normalize")

    try:
        policy.upgrade_policy_for("imaginary")
    except ValueError as exc:
        expect("unknown ArcLink upgrade component" in str(exc) and "hermes" in str(exc), str(exc))
    else:
        raise AssertionError("unknown components must fail closed")
    print("PASS test_upgrade_policy_catalog_is_sorted_grouped_and_read_only")


def test_operator_raven_fleet_drain_and_resume_are_gated_and_audited() -> None:
    tmp, old_env, conn, raven = with_seeded_db()
    try:
        before_audit = conn.execute("SELECT COUNT(*) AS n FROM arclink_audit_log").fetchone()["n"]
        preview = raven.dispatch_operator_raven_command(conn, "/fleet_drain local-worker --dry-run")
        expect("Fleet drain dry-run" in preview["message"], preview["message"])
        expect("Blocked unless --force" in preview["message"], preview["message"])
        expect("No fleet state" in preview["message"], preview["message"])
        row = conn.execute("SELECT drain FROM arclink_fleet_hosts WHERE host_id = 'host-local'").fetchone()
        expect(int(row["drain"]) == 0, str(dict(row)))

        actorless = raven.dispatch_operator_raven_command(conn, "/fleet_drain local-worker --force confirm")
        expect("requires a verified operator identity" in actorless["message"], actorless["message"])
        expect(conn.execute("SELECT drain FROM arclink_fleet_hosts WHERE host_id = 'host-local'").fetchone()["drain"] == 0, "actorless drain must not mutate")

        blocked = raven.dispatch_operator_raven_command(conn, "/fleet_drain local-worker confirm", actor_id="telegram:42")
        expect("would leave zero active" in blocked["message"], blocked["message"])
        expect(conn.execute("SELECT drain FROM arclink_fleet_hosts WHERE host_id = 'host-local'").fetchone()["drain"] == 0, "guarded drain must not mutate")

        needs_confirm = raven.dispatch_operator_raven_command(conn, "/fleet_drain local-worker --force", actor_id="telegram:42")
        expect("append `confirm`" in needs_confirm["message"], needs_confirm["message"])
        expect(conn.execute("SELECT drain FROM arclink_fleet_hosts WHERE host_id = 'host-local'").fetchone()["drain"] == 0, "unconfirmed drain must not mutate")

        drained = raven.dispatch_operator_raven_command(conn, "/fleet_drain local-worker --force confirm", actor_id="telegram:42")
        expect("fleet drain applied" in drained["message"].lower(), drained["message"])
        expect(drained["mutation_performed"] is True, str(drained))
        expect(conn.execute("SELECT drain FROM arclink_fleet_hosts WHERE host_id = 'host-local'").fetchone()["drain"] == 1, "confirmed drain must set flag")
        expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_audit_log").fetchone()["n"] == before_audit + 1, "drain should audit")

        resumed = raven.dispatch_operator_raven_command(conn, "/fleet_resume host-local confirm", actor_id="telegram:42")
        expect("fleet resume applied" in resumed["message"].lower(), resumed["message"])
        expect(conn.execute("SELECT drain FROM arclink_fleet_hosts WHERE host_id = 'host-local'").fetchone()["drain"] == 0, "resume must clear flag")
        expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_audit_log").fetchone()["n"] == before_audit + 2, "resume should audit")
        print("PASS test_operator_raven_fleet_drain_and_resume_are_gated_and_audited")
    finally:
        cleanup_db(tmp, old_env)


def test_operator_raven_user_lookup_and_pod_repair_do_not_expose_or_queue_secrets() -> None:
    tmp, old_env, conn, raven = with_seeded_db()
    try:
        user = raven.dispatch_operator_raven_command(conn, "/user_lookup alex@example.test")
        expect("user-alex" in user["message"], user["message"])
        expect("provisioning_failed=1" in user["message"], user["message"])
        expect("academy=not_started" in user["message"], user["message"])
        expect("cus_should_not_render" not in user["message"], user["message"])
        expect("secret://" not in user["message"], user["message"])

        before_actions = conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"]
        # No --dry-run and no operator actor identity must fail closed and queue nothing.
        blocked = raven.dispatch_operator_raven_command(conn, "/pod_repair dep-alex")
        after_blocked = conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"]
        expect("requires a verified operator identity" in blocked["message"], blocked["message"])
        expect(blocked["mutation_performed"] is False, str(blocked))
        expect(before_actions == after_blocked, "actorless pod repair must not queue")

        dry_run = raven.dispatch_operator_raven_command(
            conn,
            "/pod_repair dep-alex --dry-run",
            env={"ARCLINK_EXECUTOR_ADAPTER": "fake"},
        )
        after_dry_run = conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"]
        expect("Pod repair dry-run" in dry_run["message"], dry_run["message"])
        expect("No action was queued" in dry_run["message"], dry_run["message"])
        expect(before_actions == after_dry_run, "dry-run pod repair must not queue")

        needs_confirm = raven.dispatch_operator_raven_command(
            conn,
            "/pod_repair dep-alex restart",
            env={"ARCLINK_EXECUTOR_ADAPTER": "fake"},
            actor_id="telegram:42",
        )
        expect("append `confirm`" in needs_confirm["message"], needs_confirm["message"])
        expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"] == before_actions, "unconfirmed pod repair must not queue")
        print("PASS test_operator_raven_user_lookup_and_pod_repair_do_not_expose_or_queue_secrets")
    finally:
        cleanup_db(tmp, old_env)


def test_operator_raven_billing_backup_and_workspace_statuses_are_read_only() -> None:
    tmp, old_env, conn, raven = with_seeded_db()
    try:
        now = "2026-06-04T00:00:00+00:00"
        conn.execute(
            """
            INSERT INTO arclink_subscriptions (
              subscription_id, user_id, stripe_customer_id, stripe_subscription_id,
              status, current_period_end, raw_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("sub-local", "user-alex", "cus_should_not_render", "sub_should_not_render", "active", now, "{}", now, now),
        )
        conn.execute(
            """
            INSERT INTO arclink_refuel_credits (
              credit_id, user_id, deployment_id, source_kind, source_id,
              credit_cents, remaining_cents, status, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("refuel-local", "user-alex", "dep-alex", "operator", "local", 2500, 1400, "active", "{}", now, now),
        )
        conn.execute(
            """
            UPDATE arclink_deployments
            SET metadata_json = ?
            WHERE deployment_id = 'dep-rollout-1'
            """,
            (
                json.dumps(
                    {
                        "backup_owner_repo": "sirouk/arclink-agent-backup",
                        "backup_github_write_check": "failed_closed",
                        "backup_activation": "not_active",
                        "backup_github_write_check_reason": "secret://must-not-render",
                    },
                    sort_keys=True,
                ),
            ),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO arclink_service_health (
              deployment_id, service_name, status, checked_at
            ) VALUES
              ('dep-rollout-1', 'memory-synth', 'healthy', ?),
              ('dep-rollout-1', 'managed-context', 'healthy', ?)
            """,
            (now, now),
        )
        conn.execute(
            """
            INSERT INTO memory_synthesis_cards (
              card_id, source_kind, source_key, source_title, source_signature,
              prompt_version, model, status, card_json, card_text, source_count,
              token_estimate, last_error, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("card-local", "vault", "Vault/Academy/Memory_Seeds.md", "Academy seeds", "sig", "v1", "local", "active", "{}", "seed", 1, 10, "", now, now),
        )
        conn.execute(
            """
            INSERT INTO notion_index_documents (
              doc_key, root_id, source_page_id, source_page_url, source_kind,
              file_path, page_title, section_heading, section_ordinal,
              breadcrumb_json, owners_json, last_edited_time, content_hash,
              indexed_at, state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("notion-local", "root", "page", "https://www.notion.so/public", "page", "/tmp/notion.md", "Runbook", "", 0, "[]", "[]", now, "hash", now, "active"),
        )
        conn.execute(
            """
            INSERT INTO refresh_jobs (
              job_name, job_kind, target_id, schedule, last_run_at, last_status, last_note
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("academy-post-apply", "academy", "dep-rollout-1", "", now, "queued", "pending refresh"),
        )
        conn.execute(
            """
            INSERT INTO arclink_share_grants (
              grant_id, owner_user_id, recipient_user_id, resource_kind, resource_root,
              resource_path, display_name, access_mode, status, expires_at, approved_at,
              accepted_at, revoked_at, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("share-local", "user-alex", "user-alex", "drive", "vault", "Fleet", "Fleet", "write", "accepted", "", now, now, "", "{}", now, now),
        )
        conn.commit()

        before_intents = conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"]
        before_operator_actions = conn.execute("SELECT COUNT(*) AS n FROM operator_actions").fetchone()["n"]
        billing = raven.dispatch_operator_raven_command(conn, "/billing_status")
        backup = raven.dispatch_operator_raven_command(conn, "/backup_status")
        workspace = raven.dispatch_operator_raven_command(conn, "/workspace_status")
        combined = "\n".join([billing["message"], backup["message"], workspace["message"]])
        expect("Operator Raven billing status" in billing["message"], billing["message"])
        expect("remaining=$14.00" in billing["message"], billing["message"])
        expect("Operator Raven backup status" in backup["message"], backup["message"])
        expect("failed_closed" in backup["message"], backup["message"])
        expect("Operator Raven workspace status" in workspace["message"], workspace["message"])
        expect("Shared Notion index: 1 active document" in workspace["message"], workspace["message"])
        expect("accepted=1" in workspace["message"], workspace["message"])
        expect("No qmd, Notion, memory, share, filesystem, or provider mutation was run." in workspace["message"], workspace["message"])
        expect("cus_should_not_render" not in combined and "sub_should_not_render" not in combined, combined)
        expect("secret://" not in combined, combined)
        expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"] == before_intents, "readouts must not queue admin actions")
        expect(conn.execute("SELECT COUNT(*) AS n FROM operator_actions").fetchone()["n"] == before_operator_actions, "readouts must not queue operator actions")
        print("PASS test_operator_raven_billing_backup_and_workspace_statuses_are_read_only")
    finally:
        cleanup_db(tmp, old_env)


def test_operator_raven_upgrade_check_is_injected_and_fail_closed() -> None:
    tmp, old_env, conn, raven = with_seeded_db()
    try:
        fail_closed = raven.dispatch_operator_raven_command(conn, "/upgrade_check")
        expect("fail-closed" in fail_closed["message"], fail_closed["message"])
        hermes_alias = raven.dispatch_operator_raven_command(
            conn,
            "/upgrade_hermes",
            upgrade_check_runner=lambda: {"status": "ok", "current": "abcdef1234567890"},
        )
        expect(hermes_alias.get("command") == "upgrade_check", str(hermes_alias))
        expect("Operator Raven upgrade check" in hermes_alias["message"], hermes_alias["message"])

        result = raven.dispatch_operator_raven_command(
            conn,
            "/upgrade_check",
            upgrade_check_runner=lambda: {
                "status": "update_available",
                "current": "abcdef1234567890",
                "available": "fedcba9876543210",
                "note": "fake runner, no network",
            },
        )
        expect("Operator Raven upgrade check" in result["message"], result["message"])
        expect("abcdef123456" in result["message"], result["message"])
        expect("fedcba987654" in result["message"], result["message"])
        expect("No upgrade was queued or run." in result["message"], result["message"])
        print("PASS test_operator_raven_upgrade_check_is_injected_and_fail_closed")
    finally:
        cleanup_db(tmp, old_env)


def test_operator_raven_rollout_plan_is_dry_run_only() -> None:
    tmp, old_env, conn, raven = with_seeded_db()
    try:
        before_rollouts = conn.execute("SELECT COUNT(*) AS n FROM arclink_rollouts").fetchone()["n"]
        before_actions = conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"]

        blocked = raven.dispatch_operator_raven_command(conn, "/rollout_plan v2.0.0")
        expect("requires a verified operator identity" in blocked["message"], blocked["message"])
        expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_rollouts").fetchone()["n"] == before_rollouts, "actorless rollout must not queue rows")

        result = raven.dispatch_operator_raven_command(
            conn,
            "/rollout_plan v2.0.0 --dry-run --batch-size=1",
        )
        text = result["message"]
        expect("Operator Raven rollout plan dry-run" in text, text)
        expect("Target: v2.0.0" in text, text)
        expect("Candidates: 2 ready=2 blocked=0" in text, text)
        expect("Batches: 2 at batch size 1" in text, text)
        expect("Batch 1: dep-rollout-1" in text, text)
        expect("No rollout or action was queued." in text, text)
        expect("/arcdata/" not in text, text)
        expect("secret://" not in text, text)
        expect(result["rollout_plan"]["mutation_performed"] is False, str(result["rollout_plan"]))
        expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_rollouts").fetchone()["n"] == before_rollouts, "no rollout rows")
        expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"] == before_actions, "no actions queued")
        print("PASS test_operator_raven_rollout_plan_is_dry_run_only")
    finally:
        cleanup_db(tmp, old_env)


def test_operator_raven_academy_status_is_read_only_and_proof_gated() -> None:
    tmp, old_env, conn, raven = with_seeded_db()
    try:
        academy_status = {
            "status": "ready_for_review",
            "summary": "Academy local corpus is staged for review with 2 source(s); live trained-Agent proof remains pending.",
            "manifest_id": "academy-local-test",
            "source_count": 2,
            "weekly_review_status": "ready_for_review",
            "evaluation_status": "ready_for_review",
            "graduation_status": "blocked_by_live_proof",
            "next_review_at": "2026-06-22T00:00:00Z",
            "review_needed_count": 1,
            "blocked_source_count": 0,
            "source_state_counts": {"changed": 1, "unchanged": 1, "review_needed": 1},
            "proof_gates": ["PG-PROVIDER", "PG-HERMES"],
            "next_actions": ["Run authorized PG-PROVIDER and PG-HERMES proof before claiming a trained Agent."],
            "live_proof_required": True,
            "local_only": True,
            "no_write": True,
        }
        conn.execute(
            """
            INSERT INTO arclink_crew_recipes (
              recipe_id, user_id, preset, capacity, role, mission, treatment,
              soul_overlay_json, applied_at, archived_at, status
            ) VALUES (?, 'user-alex', 'Frontier', 'development', 'operator',
              'review Academy status', 'peer', ?, ?, '', 'active')
            """,
            (
                "crew_operator_academy",
                json.dumps({"crew_recipe_text": "Crew Recipe", "academy_training": academy_status}, sort_keys=True),
                "2026-05-27T00:00:00+00:00",
            ),
        )
        conn.commit()
        before_actions = conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"]
        result = raven.dispatch_operator_raven_command(conn, "/academy_status alex@example.test")
        text = result["message"]
        expect("Operator Raven Academy status" in text, text)
        expect("academy=ready_for_review" in text, text)
        expect("sources=2" in text, text)
        expect("weekly=ready_for_review" in text, text)
        expect("evaluation=ready_for_review" in text, text)
        expect("graduation=blocked_by_live_proof" in text, text)
        expect("review_needed=1" in text, text)
        expect("next_review=2026-06-22T00:00:00Z" in text, text)
        expect("PG-PROVIDER,PG-HERMES" in text, text)
        expect("No action was queued" in text, text)
        expect(result["mutation_performed"] is False, str(result))
        expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"] == before_actions, "academy status must not queue actions")
        expect("secret://" not in text, text)
        print("PASS test_operator_raven_academy_status_is_read_only_and_proof_gated")
    finally:
        cleanup_db(tmp, old_env)


def test_operator_raven_academy_roster_is_read_only() -> None:
    tmp, old_env, conn, raven = with_seeded_db()
    try:
        programs = load_module(PYTHON_DIR / "arclink_academy_programs.py", "arclink_academy_programs_raven_roster_test")
        programs.seed_default_academy_programs(conn)
        trainee = programs.enroll_academy_trainee(
            conn, program_id="research_analyst", user_id="user-alex", deployment_id="dep-alex", name="Ada"
        )
        session = programs.open_academy_mode(conn, trainee_id=trainee["trainee_id"], opened_by="user-alex")
        programs.record_academy_resource_proposal(
            conn,
            deployment_id="dep-alex",
            lane_id="web_article",
            title="Operator roster Academy source",
            origin_url="https://example.test/operator-roster-academy-source",
            summary="Compressed governed public source notes for the Operator Raven Academy roster fixture.",
            proposed_by="agent-operator-roster",
        )
        programs.end_academy_mode(conn, session_id=session["session"]["session_id"], actor="user-alex", graduate=True)

        before_actions = conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"]
        result = raven.dispatch_operator_raven_command(conn, "/academy_roster")
        text = result["message"]
        expect(result["handled"] is True and result["mutation_performed"] is False, str(result))
        expect("Operator Raven Academy roster" in text and "fleet-wide" in text, text)
        expect("graduate" in text and "Ada" in text, text)
        expect(len(result["academy_roster"]["graduates"]) == 1, str(result["academy_roster"]))
        expect("No action was queued" in text and "PG-PROVIDER/PG-HERMES" in text, text)
        expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"] == before_actions, "roster must not queue")
        expect("secret://" not in text, text)
        print("PASS test_operator_raven_academy_roster_is_read_only")
    finally:
        cleanup_db(tmp, old_env)


def test_operator_raven_pod_repair_queues_real_intent_with_actor() -> None:
    tmp, old_env, conn, raven = with_seeded_db()
    try:
        before = conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"]
        result = raven.dispatch_operator_raven_command(
            conn,
            "/pod_repair dep-alex restart confirm",
            env={"ARCLINK_EXECUTOR_ADAPTER": "fake"},
            actor_id="telegram:42",
            idempotency_key="msg-1001",
        )
        after = conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"]
        text = result["message"]
        expect("Operator Raven pod repair queued" in text, text)
        expect("action=restart" in text, text)
        expect("Executor adapter: fake (record-only)" in text, text)
        expect(result["mutation_performed"] is True, str(result))
        expect(after == before + 1, "pod repair with actor must queue exactly one intent")
        row = conn.execute(
            "SELECT action_type, target_kind, target_id, admin_id, status FROM arclink_action_intents ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        expect(row["action_type"] == "restart", dict(row))
        expect(row["target_kind"] == "deployment" and row["target_id"] == "dep-alex", dict(row))
        expect(row["admin_id"] == "telegram:42", dict(row))
        expect(row["status"] == "queued", dict(row))

        # Re-dispatch with the same idempotency key must dedupe (no second row)
        # and must report mutation_performed=False (nothing new was queued).
        repeat = raven.dispatch_operator_raven_command(
            conn,
            "/pod_repair dep-alex restart confirm",
            env={"ARCLINK_EXECUTOR_ADAPTER": "fake"},
            actor_id="telegram:42",
            idempotency_key="msg-1001",
        )
        expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"] == before + 1, "idempotent pod repair must not double-queue")
        expect(repeat["mutation_performed"] is False, str(repeat))
        expect("already queued (idempotent)" in repeat["message"], repeat["message"])

        # Adapter disabled => not queueable => blocked, no new row.
        blocked = raven.dispatch_operator_raven_command(
            conn,
            "/pod_repair dep-alex restart confirm",
            env={"ARCLINK_EXECUTOR_ADAPTER": "disabled"},
            actor_id="telegram:42",
            idempotency_key="msg-1002",
        )
        expect("Pod repair blocked" in blocked["message"], blocked["message"])
        expect(blocked["mutation_performed"] is False, str(blocked))
        expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"] == before + 1, "blocked pod repair must not queue")
        print("PASS test_operator_raven_pod_repair_queues_real_intent_with_actor")
    finally:
        cleanup_db(tmp, old_env)


def test_operator_raven_host_and_pin_upgrade_queue_operator_actions() -> None:
    tmp, old_env, conn, raven = with_seeded_db()
    try:
        before = conn.execute("SELECT COUNT(*) AS n FROM operator_actions").fetchone()["n"]
        # Dry-run must not queue.
        preview = raven.dispatch_operator_raven_command(conn, "/upgrade --dry-run", actor_id="telegram:42")
        expect("Host upgrade dry-run" in preview["message"], preview["message"])
        expect(conn.execute("SELECT COUNT(*) AS n FROM operator_actions").fetchone()["n"] == before, "dry-run host upgrade must not queue")

        # Bare /upgrade is now the one-tap menu: read-only, queues nothing.
        # Actorless renders the summary but mints no one-tap buttons.
        actorless = raven.dispatch_operator_raven_command(conn, "/upgrade")
        expect("upgrade menu" in actorless["message"], actorless["message"])
        expect(not actorless.get("buttons"), str(actorless.get("buttons")))
        expect(conn.execute("SELECT COUNT(*) AS n FROM operator_actions").fetchone()["n"] == before, "actorless upgrade menu must not queue")

        menu = raven.dispatch_operator_raven_command(conn, "/upgrade", actor_id="telegram:42")
        expect("upgrade menu" in menu["message"], menu["message"])
        menu_buttons = list(menu.get("buttons") or [])
        expect(menu_buttons and menu_buttons[0]["label"] == "Apply Control Upgrade", str(menu_buttons))
        expect(menu_buttons[0]["callback_data"].startswith("arclink:/upgrade_apply "), str(menu_buttons))
        expect(conn.execute("SELECT COUNT(*) AS n FROM operator_actions").fetchone()["n"] == before, "menu render must not queue")

        # One-tap apply: the nonce in the button is the confirmation.
        one_tap_command = menu_buttons[0]["callback_data"][len("arclink:"):]
        actorless_tap = raven.dispatch_operator_raven_command(conn, one_tap_command)
        expect("requires a verified operator identity" in actorless_tap["message"], actorless_tap["message"])
        applied = raven.dispatch_operator_raven_command(conn, one_tap_command, actor_id="telegram:42")
        expect("queued an ArcLink upgrade" in applied["message"], applied["message"])
        expect(applied["mutation_performed"] is True, str(applied))
        row = conn.execute("SELECT action_kind, requested_by, status FROM operator_actions ORDER BY id DESC LIMIT 1").fetchone()
        expect(row["action_kind"] == "upgrade", dict(row))
        expect(row["requested_by"] == "telegram:42", dict(row))

        # Replaying the same button nonce fails closed and queues nothing new.
        after_apply = conn.execute("SELECT COUNT(*) AS n FROM operator_actions").fetchone()["n"]
        replay = raven.dispatch_operator_raven_command(conn, one_tap_command, actor_id="telegram:42")
        expect("expired or was already used" in replay["message"], replay["message"])
        expect(conn.execute("SELECT COUNT(*) AS n FROM operator_actions").fetchone()["n"] == after_apply, "nonce replay must not queue")
        bogus = raven.dispatch_operator_raven_command(conn, "/upgrade_apply not-a-real-nonce", actor_id="telegram:42")
        expect("expired or was already used" in bogus["message"], bogus["message"])

        # Typed lane keeps working: an active upgrade dedupes.
        result = raven.dispatch_operator_raven_command(conn, "/upgrade confirm", actor_id="telegram:42")
        expect("already queued" in result["message"] or "already running" in result["message"], result["message"])
        expect(result["mutation_performed"] is False, str(result))

        no_payload = raven.dispatch_operator_raven_command(conn, "/pin_upgrade hermes confirm", actor_id="telegram:42")
        expect("no active detector payload" in no_payload["message"], no_payload["message"])

        token = seed_pin_upgrade_payload(conn, component="hermes-agent", target="bbbb2222", throttle_target="v0.12.0")
        pin_preview = raven.dispatch_operator_raven_command(conn, "/pin_upgrade hermes --dry-run", actor_id="telegram:42")
        expect(token in pin_preview["message"] and "No action was queued" in pin_preview["message"], pin_preview["message"])

        # The menu lists the pending payload with a one-tap pin button.
        pin_menu = raven.dispatch_operator_raven_command(conn, "/upgrade", actor_id="telegram:42")
        pin_buttons = [button for button in pin_menu.get("buttons") or [] if button["label"].startswith("Pin ")]
        expect(pin_buttons, str(pin_menu.get("buttons")))
        pin_tap_command = pin_buttons[0]["callback_data"][len("arclink:"):]
        pin = raven.dispatch_operator_raven_command(conn, pin_tap_command, actor_id="telegram:42")
        expect("pinned-component upgrade for hermes" in pin["message"], pin["message"])
        expect(token in pin["message"], pin["message"])
        expect(pin["mutation_performed"] is True, str(pin))
        pin_row = conn.execute("SELECT action_kind, requested_target FROM operator_actions ORDER BY id DESC LIMIT 1").fetchone()
        expect(pin_row["action_kind"] == "pin-upgrade" and pin_row["requested_target"] == token, dict(pin_row))

        # Typed component confirm still works and dedupes against the one-tap queue row.
        typed_pin = raven.dispatch_operator_raven_command(conn, "/pin_upgrade hermes confirm", actor_id="telegram:42")
        expect("already queued" in typed_pin["message"] or "already running" in typed_pin["message"], typed_pin["message"])

        bad = raven.dispatch_operator_raven_command(conn, "/pin_upgrade not-a-component", actor_id="telegram:42")
        expect("unknown component" in bad["message"], bad["message"])
        print("PASS test_operator_raven_host_and_pin_upgrade_queue_operator_actions")
    finally:
        cleanup_db(tmp, old_env)


def test_operator_raven_upgrade_sweep_queues_pending_detector_payloads() -> None:
    tmp, old_env, conn, raven = with_seeded_db()
    try:
        hermes_token = seed_pin_upgrade_payload(
            conn,
            component="hermes-agent",
            target="bbbb2222",
            throttle_target="v0.12.0",
        )
        qmd_token = seed_pin_upgrade_payload(
            conn,
            component="qmd",
            current="v1.0.0",
            target="v1.1.0",
            kind="git-tag",
        )
        postgres_token = seed_pin_upgrade_payload(
            conn,
            component="postgres",
            current="16",
            target="17",
            kind="container-image",
        )
        before = conn.execute("SELECT COUNT(*) AS n FROM operator_actions").fetchone()["n"]

        preview = raven.dispatch_operator_raven_command(conn, "/upgrade_sweep --dry-run", actor_id="telegram:42")
        text = preview["message"]
        expect("Operator Raven upgrade sweep" in text, text)
        expect(hermes_token in text and qmd_token in text, text)
        expect(postgres_token in text and "Skipped stateful" in text, text)
        expect(conn.execute("SELECT COUNT(*) AS n FROM operator_actions").fetchone()["n"] == before, "dry-run sweep must not queue")

        actorless = raven.dispatch_operator_raven_command(conn, "/upgrade_sweep")
        expect("requires a verified operator identity" in actorless["message"], actorless["message"])
        expect(conn.execute("SELECT COUNT(*) AS n FROM operator_actions").fetchone()["n"] == before, "actorless sweep must not queue")

        queued = raven.dispatch_operator_raven_command(conn, "/upgrade_sweep confirm", actor_id="telegram:42")
        expect("Queued 2 pinned-component upgrade action" in queued["message"], queued["message"])
        rows = conn.execute(
            "SELECT action_kind, requested_target FROM operator_actions WHERE action_kind='pin-upgrade' ORDER BY requested_target"
        ).fetchall()
        targets = {row["requested_target"] for row in rows}
        expect(targets == {hermes_token, qmd_token}, str(targets))

        with_stateful = raven.dispatch_operator_raven_command(
            conn,
            "/upgrade_sweep --include-stateful confirm",
            actor_id="telegram:42",
        )
        expect("Queued 1 pinned-component upgrade action" in with_stateful["message"], with_stateful["message"])
        rows = conn.execute(
            "SELECT requested_target FROM operator_actions WHERE action_kind='pin-upgrade'"
        ).fetchall()
        expect({row["requested_target"] for row in rows} == {hermes_token, qmd_token, postgres_token}, str(rows))
        print("PASS test_operator_raven_upgrade_sweep_queues_pending_detector_payloads")
    finally:
        cleanup_db(tmp, old_env)


def test_operator_raven_rollout_queues_real_admin_action_with_actor() -> None:
    tmp, old_env, conn, raven = with_seeded_db()
    try:
        before = conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"]
        result = raven.dispatch_operator_raven_command(
            conn,
            "/rollout v2.0.0 --batch-size=1 confirm",
            env={"ARCLINK_EXECUTOR_ADAPTER": "fake"},
            actor_id="telegram:42",
            idempotency_key="msg-2001",
        )
        text = result["message"]
        expect("Operator Raven rollout queued" in text, text)
        expect("Target: v2.0.0" in text, text)
        expect(result["mutation_performed"] is True, str(result))
        expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"] == before + 1, "rollout must queue one admin action")
        row = conn.execute("SELECT action_type, target_kind, target_id FROM arclink_action_intents ORDER BY created_at DESC LIMIT 1").fetchone()
        expect(row["action_type"] == "rollout" and row["target_kind"] == "system", dict(row))
        expect("secret://" not in text, text)
        expect("/arcdata/" not in text, text)
        print("PASS test_operator_raven_rollout_queues_real_admin_action_with_actor")
    finally:
        cleanup_db(tmp, old_env)


def test_operator_raven_action_status_reads_both_queues() -> None:
    tmp, old_env, conn, raven = with_seeded_db()
    try:
        raven.dispatch_operator_raven_command(
            conn,
            "/pod_repair dep-alex restart confirm",
            env={"ARCLINK_EXECUTOR_ADAPTER": "fake"},
            actor_id="telegram:42",
            idempotency_key="msg-3001",
        )
        raven.dispatch_operator_raven_command(conn, "/upgrade confirm", actor_id="telegram:42")
        before_actions = conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"]
        result = raven.dispatch_operator_raven_command(conn, "/action_status")
        text = result["message"]
        expect("Operator Raven action status" in text, text)
        expect("Admin action intents:" in text, text)
        expect("restart" in text and "dep-alex" in text, text)
        expect("Operator actions:" in text and "upgrade" in text, text)
        expect(result["mutation_performed"] is False, str(result))
        expect(conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"] == before_actions, "action_status must not queue")
        print("PASS test_operator_raven_action_status_reads_both_queues")
    finally:
        cleanup_db(tmp, old_env)


def test_operator_raven_mutation_helpers_and_approval_code() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    raven = load_module(OPERATOR_RAVEN_PY, "arclink_operator_raven_helpers_test")
    expect(raven.operator_raven_command_is_mutating("/pod_repair dep-alex restart") is True, "pod_repair is mutating")
    expect(raven.operator_raven_command_is_mutating("/pod_repair dep-alex --dry-run") is False, "dry-run pod_repair is not mutating")
    expect(raven.operator_raven_command_is_mutating("/operator_status") is False, "status is not mutating")
    expect(raven.operator_raven_command_is_mutating("/billing_status") is False, "billing_status is read-only")
    expect(raven.operator_raven_command_is_mutating("/backup_status") is False, "backup_status is read-only")
    expect(raven.operator_raven_command_is_mutating("/workspace_status") is False, "workspace_status is read-only")
    expect(raven.operator_raven_command_is_mutating("/rollout v2.0.0") is True, "rollout is mutating")
    expect(raven.operator_raven_command_is_mutating("/upgrade") is False, "bare /upgrade renders the read-only one-tap menu")
    expect(raven.operator_raven_command_is_mutating("/pin_upgrade") is False, "bare /pin_upgrade renders the read-only one-tap menu")
    expect(raven.operator_raven_command_is_mutating("/upgrade confirm") is True, "confirmed upgrade is mutating")
    expect(raven.operator_raven_command_is_mutating("/pin_upgrade hermes") is True, "component pin upgrade stays mutating")
    expect(raven.operator_raven_command_is_mutating("/upgrade_apply abc123") is False, "one-tap apply self-gates on its single-use nonce")
    expect(raven.operator_raven_command_is_mutating("/upgrade_sweep") is True, "upgrade_sweep is mutating")
    expect(raven.operator_raven_command_is_mutating("/upgrade_sweep --dry-run") is False, "dry-run upgrade_sweep is not mutating")
    expect(raven.operator_raven_command_is_mutating("/upgrade_check") is False, "upgrade_check is read-only")
    expect(raven.operator_raven_command_is_mutating("/upgrade_policy hermes") is False, "upgrade_policy is read-only")
    expect(raven.operator_raven_command_is_mutating("/fleet_drain host-local") is True, "fleet_drain is mutating")
    expect(raven.operator_raven_command_is_mutating("/fleet_drain host-local --dry-run") is False, "dry-run fleet_drain is not mutating")
    expect(raven.operator_raven_command_is_mutating("/fleet_resume host-local") is True, "fleet_resume is mutating")

    # Component inference must skip option-value pairs, not return the flag value.
    parsed = raven.parse_operator_raven_command("/pin_upgrade --batch-size 2 hermes")
    expect(parsed is not None and parsed.component == "hermes", str(parsed))
    parsed_confirm = raven.parse_operator_raven_command("/pin_upgrade --batch-size 2 hermes confirm")
    expect(parsed_confirm is not None and parsed_confirm.component == "hermes" and parsed_confirm.confirmed is True, str(parsed_confirm))
    parsed_plain = raven.parse_operator_raven_command("/pin_upgrade qmd")
    expect(parsed_plain is not None and parsed_plain.component == "qmd", str(parsed_plain))

    ok, cleaned = raven.strip_operator_approval_code("/upgrade s3cr3t", "s3cr3t")
    expect(ok is True and cleaned == "/upgrade", (ok, cleaned))
    bad, raw = raven.strip_operator_approval_code("/upgrade wrong", "s3cr3t")
    expect(bad is False, (bad, raw))
    no_code_ok, passthrough = raven.strip_operator_approval_code("/upgrade", "")
    expect(no_code_ok is True and passthrough == "/upgrade", (no_code_ok, passthrough))
    print("PASS test_operator_raven_mutation_helpers_and_approval_code")


def test_operator_raven_chat_adapters_preserve_authorization_boundaries() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_operator_raven_adapter_test")
    telegram = load_module(CURATOR_TELEGRAM_PY, "arclink_curator_onboarding_operator_raven_adapter_test")
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            expect(telegram._operator_command_requested("/operator_status"), "Telegram should recognize Operator Raven commands")
            expect(telegram._operator_command_requested("/billing_status"), "Telegram should recognize Operator Raven billing status")
            expect(telegram._operator_command_requested("/backup_status"), "Telegram should recognize Operator Raven backup status")
            expect(telegram._operator_command_requested("/workspace_status"), "Telegram should recognize Operator Raven workspace status")
            expect(telegram._operator_command_requested("/agents"), "Telegram operator /agents should resolve to Operator Raven, not Hermes internals")
            allowed = {"chat": {"id": "42", "type": "private"}, "from": {"id": "42"}}
            denied = {"chat": {"id": "99", "type": "private"}, "from": {"id": "99"}}
            expect(telegram.operator_message_allowed(cfg, allowed), "configured operator channel should be allowed")
            expect(not telegram.operator_message_allowed(cfg, denied), "other Telegram chats must be refused before dispatch")
        finally:
            os.environ.clear()
            os.environ.update(old_env)

    discord_text = CURATOR_DISCORD_PY.read_text(encoding="utf-8")
    expect("operator_raven_command_requested" in discord_text, "Discord adapter should use shared Operator Raven parser")
    expect('dispatch_text = f"{dispatch_text} --confirm"' in discord_text, "Discord approval code should satisfy the Operator Raven confirmation token")
    expect("@tree.command(name=\"operator-status\"" in discord_text, "Discord should expose an operator status command")
    expect("@tree.command(name=\"operator-agents\"" in discord_text, "Discord should expose an operator ArcLink agents command")
    expect("@tree.command(name=\"billing-status\"" in discord_text, "Discord should expose operator billing status")
    expect("@tree.command(name=\"backup-status\"" in discord_text, "Discord should expose operator backup status")
    expect("@tree.command(name=\"workspace-status\"" in discord_text, "Discord should expose operator workspace status")
    expect(
        "@tree.command(name=\"upgrade\"" in discord_text and "Bare /upgrade renders the one-tap menu" in discord_text,
        "Discord bare /upgrade must render the read-only one-tap menu, never queue directly",
    )
    expect("@tree.command(name=\"pin-upgrade\"" in discord_text, "Discord should expose a confirmed pinned-component upgrade command")
    expect("_queue_upgrade_operator_action" not in discord_text, "Discord /upgrade must not bypass Operator Raven confirmation")
    expect('request_source="discord-button"' not in discord_text, "Discord upgrade buttons must not queue operator actions directly")
    expect("_ensure_operator_channel" in discord_text, "Discord operator commands must keep channel authorization")
    expect("ARCLINK_OPERATOR_DISCORD_USER_IDS" in discord_text, "Discord operator commands must support an explicit operator user allowlist")
    expect("ARCLINK_OPERATOR_DISCORD_ROLE_IDS" in discord_text, "Discord operator guild commands must support an explicit operator role allowlist")
    expect("guild is None" in discord_text, "Discord operator DMs should remain available when no guild allowlist is configured")
    expect('dispatch_text = f"{dispatch_text} --confirm"' in CURATOR_TELEGRAM_PY.read_text(encoding="utf-8"), "Curator Telegram approval code should satisfy confirmation")
    curator_telegram_text = CURATOR_TELEGRAM_PY.read_text(encoding="utf-8")
    expect('request_source="telegram-button"' not in curator_telegram_text, "Telegram upgrade buttons must not queue operator actions directly")
    expect('dispatch_text = f"{dispatch_text} --confirm"' in (PYTHON_DIR / "arclink_telegram.py").read_text(encoding="utf-8"), "Public Telegram approval code should satisfy confirmation")
    print("PASS test_operator_raven_chat_adapters_preserve_authorization_boundaries")


def test_operator_telegram_gate_unified_across_transports() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_operator_gate_unify_test")
    curator = load_module(CURATOR_TELEGRAM_PY, "arclink_curator_onboarding_operator_gate_unify_test")
    tg = load_module(PYTHON_DIR / "arclink_telegram.py", "arclink_telegram_operator_gate_unify_test")

    scenarios = [
        # (label, env overrides, chat_id, sender_id, chat_type, expected)
        ("configured channel + allowlisted sender", {"ARCLINK_OPERATOR_TELEGRAM_USER_IDS": "99"}, "42", "99", "private", True),
        ("allowlisted sender own private DM", {"ARCLINK_OPERATOR_TELEGRAM_USER_IDS": "99"}, "99", "99", "private", True),
        ("allowlisted sender in a group", {"ARCLINK_OPERATOR_TELEGRAM_USER_IDS": "99"}, "-555", "99", "group", False),
        ("non-allowlisted sender", {"ARCLINK_OPERATOR_TELEGRAM_USER_IDS": "99"}, "98", "98", "private", False),
        ("no allowlist, configured private channel", {}, "42", "42", "private", True),
        ("no allowlist, other private chat", {}, "99", "99", "private", False),
        (
            "telegram secondary surface, allowlisted DM",
            {
                "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "discord",
                "OPERATOR_NOTIFY_CHANNEL_ID": "1234567890",
                "ARCLINK_CURATOR_CHANNELS": "telegram,discord",
                "ARCLINK_OPERATOR_TELEGRAM_USER_IDS": "99",
            },
            "99",
            "99",
            "private",
            True,
        ),
        (
            "telegram secondary surface, no allowlist",
            {
                "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "discord",
                "OPERATOR_NOTIFY_CHANNEL_ID": "1234567890",
                "ARCLINK_CURATOR_CHANNELS": "telegram,discord",
            },
            "99",
            "99",
            "private",
            False,
        ),
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        old_env = os.environ.copy()
        try:
            for label, overrides, chat_id, sender_id, chat_type, expected in scenarios:
                values = config_values(root)
                values.update(overrides)
                config_path = root / "config" / "arclink.env"
                write_config(config_path, values)
                os.environ.clear()
                os.environ.update(old_env)
                os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
                cfg = control.Config.from_env()
                message = {
                    "chat": {"id": chat_id, "type": chat_type},
                    "from": {"id": sender_id},
                }
                longpoll = curator.operator_message_allowed(cfg, message)
                env = {
                    "OPERATOR_NOTIFY_CHANNEL_PLATFORM": values.get("OPERATOR_NOTIFY_CHANNEL_PLATFORM", ""),
                    "OPERATOR_NOTIFY_CHANNEL_ID": values.get("OPERATOR_NOTIFY_CHANNEL_ID", ""),
                    "ARCLINK_OPERATOR_TELEGRAM_USER_IDS": values.get("ARCLINK_OPERATOR_TELEGRAM_USER_IDS", ""),
                    "ARCLINK_CURATOR_CHANNELS": values.get("ARCLINK_CURATOR_CHANNELS", ""),
                }
                webhook = tg._operator_telegram_sender_allowed(
                    {"chat_id": chat_id, "user_id": sender_id, "chat_type": chat_type},
                    env,
                )
                expect(
                    longpoll == webhook == expected,
                    f"{label}: long-poll={longpoll} webhook={webhook} expected={expected}",
                )
        finally:
            os.environ.clear()
            os.environ.update(old_env)
    print("PASS test_operator_telegram_gate_unified_across_transports")


if __name__ == "__main__":
    test_operator_raven_status_is_read_only_and_truthful()
    test_operator_raven_agents_reports_arclink_arcpods_not_hermes_tasks()
    test_operator_raven_fleet_and_worker_probe_are_dry_run_only()
    test_operator_raven_upgrade_policy_is_read_only_and_component_specific()
    test_upgrade_policy_catalog_is_sorted_grouped_and_read_only()
    test_operator_raven_fleet_drain_and_resume_are_gated_and_audited()
    test_operator_raven_user_lookup_and_pod_repair_do_not_expose_or_queue_secrets()
    test_operator_raven_billing_backup_and_workspace_statuses_are_read_only()
    test_operator_raven_upgrade_check_is_injected_and_fail_closed()
    test_operator_raven_rollout_plan_is_dry_run_only()
    test_operator_raven_academy_status_is_read_only_and_proof_gated()
    test_operator_raven_academy_roster_is_read_only()
    test_operator_raven_pod_repair_queues_real_intent_with_actor()
    test_operator_raven_host_and_pin_upgrade_queue_operator_actions()
    test_operator_raven_upgrade_sweep_queues_pending_detector_payloads()
    test_operator_raven_rollout_queues_real_admin_action_with_actor()
    test_operator_raven_action_status_reads_both_queues()
    test_operator_raven_mutation_helpers_and_approval_code()
    test_operator_raven_chat_adapters_preserve_authorization_boundaries()
    test_operator_telegram_gate_unified_across_transports()
    print("PASS all Operator Raven tests")
