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
        expect("Rollouts:" in text and "fake/local batch records only" in text, text)
        expect(result["provisioning_readiness"]["state"] == "ready_to_provision", str(result["provisioning_readiness"]))
        expect(result["provisioning_readiness"]["live_proof_required"] is True, str(result["provisioning_readiness"]))
        expect("PG-PROD" in text and "PG-UPGRADE" in text, text)
        expect("secret://" not in text, text)
        expect("cus_should_not_render" not in text, text)
        print("PASS test_operator_raven_status_is_read_only_and_truthful")
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
        blocked = raven.dispatch_operator_raven_command(conn, "/pod_repair dep-alex")
        after_blocked = conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"]
        expect("dry-run only" in blocked["message"], blocked["message"])
        expect(before_actions == after_blocked, "blocked pod repair must not queue")

        dry_run = raven.dispatch_operator_raven_command(
            conn,
            "/pod_repair dep-alex --dry-run",
            env={"ARCLINK_EXECUTOR_ADAPTER": "fake"},
        )
        after_dry_run = conn.execute("SELECT COUNT(*) AS n FROM arclink_action_intents").fetchone()["n"]
        expect("Pod repair dry-run" in dry_run["message"], dry_run["message"])
        expect("No action was queued" in dry_run["message"], dry_run["message"])
        expect(before_actions == after_dry_run, "dry-run pod repair must not queue")
        print("PASS test_operator_raven_user_lookup_and_pod_repair_do_not_expose_or_queue_secrets")
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
        expect("dry-run only" in blocked["message"], blocked["message"])

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
            allowed = {"chat": {"id": "42", "type": "private"}, "from": {"id": "42"}}
            denied = {"chat": {"id": "99", "type": "private"}, "from": {"id": "99"}}
            expect(telegram.operator_message_allowed(cfg, allowed), "configured operator channel should be allowed")
            expect(not telegram.operator_message_allowed(cfg, denied), "other Telegram chats must be refused before dispatch")
        finally:
            os.environ.clear()
            os.environ.update(old_env)

    discord_text = CURATOR_DISCORD_PY.read_text(encoding="utf-8")
    expect("operator_raven_command_requested" in discord_text, "Discord adapter should use shared Operator Raven parser")
    expect("@tree.command(name=\"operator-status\"" in discord_text, "Discord should expose an operator status command")
    expect("_ensure_operator_channel" in discord_text, "Discord operator commands must keep channel authorization")
    print("PASS test_operator_raven_chat_adapters_preserve_authorization_boundaries")


if __name__ == "__main__":
    test_operator_raven_status_is_read_only_and_truthful()
    test_operator_raven_fleet_and_worker_probe_are_dry_run_only()
    test_operator_raven_user_lookup_and_pod_repair_do_not_expose_or_queue_secrets()
    test_operator_raven_upgrade_check_is_injected_and_fail_closed()
    test_operator_raven_rollout_plan_is_dry_run_only()
    test_operator_raven_academy_status_is_read_only_and_proof_gated()
    test_operator_raven_chat_adapters_preserve_authorization_boundaries()
    print("PASS all 7 Operator Raven tests")
