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


def seed_deployment(control, conn, *, entitlement_state: str = "paid", status: str = "provisioning_ready", metadata=None):
    control.upsert_arclink_user(
        conn,
        user_id="user_1",
        email="person@example.test",
        entitlement_state=entitlement_state,
    )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_1",
        user_id="user_1",
        prefix="amber-vault-1a2b",
        base_domain="example.test",
        status=status,
        metadata=metadata or {},
    )


def render_text(value) -> str:
    return json.dumps(value, sort_keys=True)


def test_dry_run_renders_full_service_dns_access_intent_without_secrets() -> None:
    control = load_module("almanac_control.py", "almanac_control_provisioning_render_test")
    provisioning = load_module("arclink_provisioning.py", "arclink_provisioning_render_test")
    conn = memory_db(control)
    seed_deployment(
        control,
        conn,
        metadata={
            "telegram_bot_token_ref": "secret://arclink/telegram/dep_1/bot-token",
            "discord_bot_token_ref": "secret://arclink/discord/dep_1/bot-token",
            "notion_token_ref": "secret://arclink/notion/dep_1/token",
        },
    )
    result = provisioning.render_arclink_provisioning_dry_run(
        conn,
        deployment_id="dep_1",
        edge_target="edge.example.test",
        state_root_base="/arcdata/deployments",
        idempotency_key="dry-run-1",
    )
    intent = result["intent"]
    services = intent["compose"]["services"]
    compose_secrets = intent["compose"]["secrets"]
    expected_services = {
        "dashboard",
        "hermes-gateway",
        "hermes-dashboard",
        "qmd-mcp",
        "vault-watch",
        "memory-synth",
        "nextcloud-db",
        "nextcloud-redis",
        "nextcloud",
        "code-server",
        "notification-delivery",
        "health-watch",
        "managed-context-install",
    }
    expect(set(services) == expected_services, sorted(services))
    expect(intent["execution"]["ready"], str(intent["execution"]))
    expect(intent["state_roots"]["root"] == "/arcdata/deployments/dep_1-amber-vault-1a2b", str(intent["state_roots"]))
    expect(intent["state_roots"]["nextcloud"].endswith("/state/nextcloud"), str(intent["state_roots"]))
    expect(intent["state_roots"]["nextcloud_db"].endswith("/state/nextcloud/db"), str(intent["state_roots"]))
    expect(intent["state_roots"]["nextcloud_redis"].endswith("/state/nextcloud/redis"), str(intent["state_roots"]))
    expect(compose_secrets["nextcloud_db_password"]["secret_ref"] == "secret://arclink/nextcloud/dep_1/db-password", str(compose_secrets))
    expect(compose_secrets["nextcloud_db_password"]["target"] == "/run/secrets/nextcloud_db_password", str(compose_secrets))
    expect(compose_secrets["nextcloud_admin_password"]["target"] == "/run/secrets/nextcloud_admin_password", str(compose_secrets))
    expect(compose_secrets["code_server_password"]["target"] == "/run/secrets/code_server_password", str(compose_secrets))
    expect(intent["environment"]["HERMES_HOME"] == "/home/almanac/.hermes", str(intent["environment"]))
    expect(intent["environment"]["VAULT_DIR"] == "/srv/vault", str(intent["environment"]))
    expect(intent["environment"]["QMD_STATE_DIR"] == "/home/almanac/.qmd", str(intent["environment"]))
    expect(intent["environment"]["ALMANAC_MEMORY_SYNTH_STATE_DIR"] == "/srv/memory", str(intent["environment"]))
    for key in ("HERMES_HOME", "VAULT_DIR", "QMD_STATE_DIR", "ALMANAC_MEMORY_SYNTH_STATE_DIR"):
        expect(not intent["environment"][key].startswith("/arcdata/"), f"{key} leaked host root")
    expect(services["nextcloud"]["volumes"][0]["source"] == intent["state_roots"]["nextcloud_html"], str(services["nextcloud"]))
    expect(services["nextcloud"]["environment"]["POSTGRES_HOST"] == "nextcloud-db", str(services["nextcloud"]))
    expect(services["nextcloud"]["environment"]["REDIS_HOST"] == "nextcloud-redis", str(services["nextcloud"]))
    expect(services["nextcloud"]["environment"]["POSTGRES_PASSWORD_FILE"] == "/run/secrets/nextcloud_db_password", str(services["nextcloud"]))
    expect(
        services["nextcloud"]["environment"]["NEXTCLOUD_ADMIN_PASSWORD_FILE"] == "/run/secrets/nextcloud_admin_password",
        str(services["nextcloud"]),
    )
    expect(services["nextcloud"]["depends_on"] == ["nextcloud-db", "nextcloud-redis"], str(services["nextcloud"]))
    expect(services["nextcloud"]["secrets"] == [
        {"source": "nextcloud_db_password", "target": "/run/secrets/nextcloud_db_password"},
        {"source": "nextcloud_admin_password", "target": "/run/secrets/nextcloud_admin_password"},
    ], str(services["nextcloud"]))
    expect(services["nextcloud-db"]["environment"]["POSTGRES_PASSWORD_FILE"] == "/run/secrets/nextcloud_db_password", str(services["nextcloud-db"]))
    expect(services["nextcloud-db"]["secrets"] == [
        {"source": "nextcloud_db_password", "target": "/run/secrets/nextcloud_db_password"}
    ], str(services["nextcloud-db"]))
    expect(services["nextcloud-db"]["volumes"][0]["source"] == intent["state_roots"]["nextcloud_db"], str(services["nextcloud-db"]))
    expect(services["nextcloud-redis"]["volumes"][0]["source"] == intent["state_roots"]["nextcloud_redis"], str(services["nextcloud-redis"]))
    expect(services["qmd-mcp"]["volumes"][1]["target"] == intent["environment"]["QMD_STATE_DIR"], str(services["qmd-mcp"]))
    expect(services["memory-synth"]["volumes"][0]["target"] == intent["environment"]["ALMANAC_MEMORY_SYNTH_STATE_DIR"], str(services["memory-synth"]))
    expect("PASSWORD_REF" not in services["code-server"]["environment"], str(services["code-server"]))
    expect("cat /run/secrets/code_server_password" in " ".join(services["code-server"]["command"]), str(services["code-server"]))
    expect(
        intent["runtime_resolution"]["stock_image_file_env"]["nextcloud"] == [
            "POSTGRES_PASSWORD_FILE",
            "NEXTCLOUD_ADMIN_PASSWORD_FILE",
        ],
        str(intent["runtime_resolution"]),
    )
    expect(
        intent["runtime_resolution"]["entrypoint_file_resolver"]["code-server"]["source_file"] == "/run/secrets/code_server_password",
        str(intent["runtime_resolution"]),
    )
    expect("chutes_api_key" in intent["runtime_resolution"]["app_ref_resolver_required"], str(intent["runtime_resolution"]))
    expect(services["hermes-gateway"]["labels"]["traefik.http.routers.arclink-amber-vault-1a2b-hermes.rule"] == "Host(`hermes-amber-vault-1a2b.example.test`)", str(services["hermes-gateway"]))
    expect(intent["dns"]["files"]["hostname"] == "files-amber-vault-1a2b.example.test", str(intent["dns"]))
    expect(intent["access"]["urls"]["code"] == "https://code-amber-vault-1a2b.example.test", str(intent["access"]))
    expect(intent["access"]["ssh"]["strategy"] == "cloudflare_access_tcp", str(intent["access"]))
    text = render_text(intent)
    for forbidden in ("sk_", "whsec_", "xoxb-", "ntn_", "123456:"):
        expect(forbidden not in text, text)
    health = conn.execute("SELECT service_name, status FROM arclink_service_health WHERE deployment_id = 'dep_1'").fetchall()
    expect(len(health) == len(expected_services), str([dict(row) for row in health]))
    expect({row["status"] for row in health} == {"planned"}, str([dict(row) for row in health]))
    events = conn.execute("SELECT event_type FROM arclink_events WHERE subject_id = 'dep_1' ORDER BY created_at").fetchall()
    event_types = {row["event_type"] for row in events}
    expect({"provisioning_planned", "provisioning_rendered", "provisioning_ready_for_execution"} <= event_types, str(event_types))
    print("PASS test_dry_run_renders_full_service_dns_access_intent_without_secrets")


def test_entitlement_gate_blocks_executable_intent_but_keeps_dry_run_visible() -> None:
    control = load_module("almanac_control.py", "almanac_control_provisioning_gate_test")
    provisioning = load_module("arclink_provisioning.py", "arclink_provisioning_gate_test")
    conn = memory_db(control)
    seed_deployment(control, conn, entitlement_state="none", status="entitlement_required")
    result = provisioning.render_arclink_provisioning_dry_run(conn, deployment_id="dep_1", idempotency_key="dry-run-gated")
    intent = result["intent"]
    expect(not intent["execution"]["ready"], str(intent["execution"]))
    expect(intent["execution"]["blocked_reason"] == "entitlement_required", str(intent["execution"]))
    events = conn.execute("SELECT event_type FROM arclink_events WHERE subject_id = 'dep_1'").fetchall()
    event_types = {row["event_type"] for row in events}
    expect("provisioning_rendered" in event_types, str(event_types))
    expect("provisioning_ready_for_execution" not in event_types, str(event_types))
    print("PASS test_entitlement_gate_blocks_executable_intent_but_keeps_dry_run_visible")


def test_secret_validator_fails_job_and_same_idempotency_key_can_resume_after_fix() -> None:
    control = load_module("almanac_control.py", "almanac_control_provisioning_resume_test")
    provisioning = load_module("arclink_provisioning.py", "arclink_provisioning_resume_test")
    conn = memory_db(control)
    seed_deployment(control, conn, metadata={"chutes_secret_ref": "sk_live_plaintext"})
    try:
        provisioning.render_arclink_provisioning_dry_run(conn, deployment_id="dep_1", idempotency_key="dry-run-resume")
    except provisioning.ArcLinkSecretReferenceError as exc:
        expect("plaintext" in str(exc), str(exc))
    else:
        raise AssertionError("expected plaintext secret validation to fail")
    failed = conn.execute("SELECT job_id, status, attempt_count, error FROM arclink_provisioning_jobs").fetchone()
    expect(failed["status"] == "failed" and failed["attempt_count"] == 1, str(dict(failed)))
    expect("plaintext" in failed["error"], str(dict(failed)))
    conn.execute(
        "UPDATE arclink_deployments SET metadata_json = ? WHERE deployment_id = 'dep_1'",
        (json.dumps({"chutes_secret_ref": "secret://arclink/chutes/dep_1"}, sort_keys=True),),
    )
    conn.commit()
    resumed = provisioning.render_arclink_provisioning_dry_run(conn, deployment_id="dep_1", idempotency_key="dry-run-resume")
    expect(resumed["job_id"] == failed["job_id"], str(resumed))
    row = conn.execute("SELECT status, attempt_count FROM arclink_provisioning_jobs WHERE job_id = ?", (failed["job_id"],)).fetchone()
    expect(row["status"] == "succeeded" and row["attempt_count"] == 2, str(dict(row)))
    events = conn.execute("SELECT event_type FROM arclink_events WHERE subject_id = 'dep_1'").fetchall()
    event_types = {event["event_type"] for event in events}
    expect({"provisioning_failed", "provisioning_rendered"} <= event_types, str(event_types))
    print("PASS test_secret_validator_fails_job_and_same_idempotency_key_can_resume_after_fix")


def test_failed_provisioning_retry_clears_stale_timestamps_and_error() -> None:
    control = load_module("almanac_control.py", "almanac_control_provisioning_timestamp_test")
    conn = memory_db(control)
    control.create_arclink_provisioning_job(
        conn,
        job_id="job_retry_1",
        deployment_id="dep_1",
        job_kind="docker_dry_run",
        idempotency_key="retry-timestamps",
    )
    control.transition_arclink_provisioning_job(conn, job_id="job_retry_1", status="running")
    control.transition_arclink_provisioning_job(conn, job_id="job_retry_1", status="failed", error="old render error")
    conn.execute(
        """
        UPDATE arclink_provisioning_jobs
        SET started_at = '2000-01-01T00:00:00+00:00',
            finished_at = '2000-01-01T00:00:01+00:00'
        WHERE job_id = 'job_retry_1'
        """
    )
    conn.commit()
    control.transition_arclink_provisioning_job(conn, job_id="job_retry_1", status="queued")
    queued = conn.execute("SELECT status, started_at, finished_at, error FROM arclink_provisioning_jobs").fetchone()
    expect(queued["status"] == "queued", str(dict(queued)))
    expect(queued["started_at"] is None and queued["finished_at"] is None, str(dict(queued)))
    expect(queued["error"] == "", str(dict(queued)))
    control.transition_arclink_provisioning_job(conn, job_id="job_retry_1", status="running")
    running = conn.execute("SELECT status, attempt_count, started_at, finished_at, error FROM arclink_provisioning_jobs").fetchone()
    expect(running["status"] == "running", str(dict(running)))
    expect(running["attempt_count"] == 2, str(dict(running)))
    expect(running["started_at"] and running["started_at"] != "2000-01-01T00:00:00+00:00", str(dict(running)))
    expect(running["finished_at"] is None and running["error"] == "", str(dict(running)))
    print("PASS test_failed_provisioning_retry_clears_stale_timestamps_and_error")


def test_secret_validator_rejects_plaintext_provider_and_gateway_values() -> None:
    provisioning = load_module("arclink_provisioning.py", "arclink_provisioning_secret_matrix_test")
    cases = {
        "stripe": {"secret_refs": {"stripe_customer": "sk_test_plaintext"}},
        "cloudflare": {"secret_refs": {"cloudflare_tunnel": "cloudflare-api-token-plaintext"}},
        "telegram": {"environment": {"TELEGRAM_BOT_TOKEN_REF": "123456:abcdefghijklmnopqrstuvwxyz"}},
        "discord": {"environment": {"DISCORD_BOT_TOKEN_REF": "discord-token-plaintext"}},
        "notion": {"environment": {"NOTION_TOKEN_REF": "ntn_plaintext"}},
    }
    for name, payload in cases.items():
        try:
            provisioning.validate_no_plaintext_secrets(payload)
        except provisioning.ArcLinkSecretReferenceError as exc:
            expect("plaintext" in str(exc), f"{name}: {exc}")
        else:
            raise AssertionError(f"expected plaintext secret validation to fail for {name}")
    provisioning.validate_no_plaintext_secrets(
        {
            "secret_refs": {
                "stripe_customer": "secret://arclink/stripe/customer",
                "cloudflare_tunnel": "secret://arclink/cloudflare/tunnel",
            },
            "environment": {
                "TELEGRAM_BOT_TOKEN_REF": "secret://arclink/telegram/dep_1/bot-token",
                "DISCORD_BOT_TOKEN_REF": "secret://arclink/discord/dep_1/bot-token",
                "NOTION_TOKEN_REF": "secret://arclink/notion/dep_1/token",
            },
        }
    )
    print("PASS test_secret_validator_rejects_plaintext_provider_and_gateway_values")


def test_stock_image_credentials_use_file_env_and_resolver_fallbacks_are_explicit() -> None:
    control = load_module("almanac_control.py", "almanac_control_provisioning_secret_resolution_test")
    provisioning = load_module("arclink_provisioning.py", "arclink_provisioning_secret_resolution_test")
    conn = memory_db(control)
    seed_deployment(control, conn)
    intent = provisioning.render_arclink_provisioning_intent(conn, deployment_id="dep_1")
    services = intent["compose"]["services"]
    compose_secrets = intent["compose"]["secrets"]
    expect(services["nextcloud-db"]["environment"] == {
        "POSTGRES_DB": "nextcloud_dep_1",
        "POSTGRES_USER": "nextcloud",
        "POSTGRES_PASSWORD_FILE": "/run/secrets/nextcloud_db_password",
    }, str(services["nextcloud-db"]))
    expect(services["nextcloud"]["environment"]["POSTGRES_PASSWORD_FILE"] == "/run/secrets/nextcloud_db_password", str(services["nextcloud"]))
    expect(services["nextcloud"]["environment"]["NEXTCLOUD_ADMIN_PASSWORD_FILE"] == "/run/secrets/nextcloud_admin_password", str(services["nextcloud"]))
    for secret_name in ("nextcloud_db_password", "nextcloud_admin_password", "code_server_password"):
        expect(compose_secrets[secret_name]["secret_ref"].startswith("secret://"), str(compose_secrets[secret_name]))
        expect(compose_secrets[secret_name]["target"] == f"/run/secrets/{secret_name}", str(compose_secrets[secret_name]))
    expect(
        intent["runtime_resolution"]["entrypoint_file_resolver"]["code-server"] == {
            "env_var": "PASSWORD",
            "source_file": "/run/secrets/code_server_password",
        },
        str(intent["runtime_resolution"]),
    )
    expect(
        intent["runtime_resolution"]["app_ref_resolver_required"] == ["chutes_api_key"],
        str(intent["runtime_resolution"]),
    )
    print("PASS test_stock_image_credentials_use_file_env_and_resolver_fallbacks_are_explicit")


def test_failed_execution_job_gets_idempotent_rollback_plan_event() -> None:
    control = load_module("almanac_control.py", "almanac_control_provisioning_rollback_test")
    provisioning = load_module("arclink_provisioning.py", "arclink_provisioning_rollback_test")
    conn = memory_db(control)
    seed_deployment(control, conn)
    control.create_arclink_provisioning_job(
        conn,
        job_id="job_execute_1",
        deployment_id="dep_1",
        job_kind="docker_execute",
        idempotency_key="execute-1",
    )
    control.transition_arclink_provisioning_job(conn, job_id="job_execute_1", status="running")
    control.transition_arclink_provisioning_job(conn, job_id="job_execute_1", status="failed", error="container health failed")
    first = provisioning.plan_arclink_provisioning_rollback(
        conn,
        deployment_id="dep_1",
        failed_job_id="job_execute_1",
        idempotency_key="rollback-1",
    )
    second = provisioning.plan_arclink_provisioning_rollback(
        conn,
        deployment_id="dep_1",
        failed_job_id="job_execute_1",
        idempotency_key="rollback-1",
    )
    expect(first == second, f"{first} != {second}")
    expect("preserve_state_roots" in first["actions"], str(first))
    jobs = conn.execute("SELECT job_kind FROM arclink_provisioning_jobs WHERE job_kind = 'docker_rollback_plan'").fetchall()
    expect(len(jobs) == 1, str([dict(row) for row in jobs]))
    events = conn.execute("SELECT event_type FROM arclink_events WHERE subject_id = 'dep_1'").fetchall()
    event_types = {row["event_type"] for row in events}
    expect("provisioning_rollback_requested" in event_types, str(event_types))
    print("PASS test_failed_execution_job_gets_idempotent_rollback_plan_event")


def test_rendered_services_include_resource_limits_and_healthchecks() -> None:
    control = load_module("almanac_control.py", "almanac_control_provisioning_limits_test")
    provisioning = load_module("arclink_provisioning.py", "arclink_provisioning_limits_test")
    conn = memory_db(control)
    seed_deployment(control, conn)
    intent = provisioning.render_arclink_provisioning_intent(conn, deployment_id="dep_1")
    services = intent["compose"]["services"]

    # Every service has deploy.resources.limits
    for name, svc in services.items():
        expect("deploy" in svc, f"{name} missing deploy")
        limits = svc["deploy"]["resources"]["limits"]
        expect("memory" in limits and "cpus" in limits, f"{name} missing limits: {limits}")

    # Specific healthchecks on data/web services
    for name in ("nextcloud-db", "nextcloud-redis", "nextcloud", "code-server"):
        expect("healthcheck" in services[name], f"{name} missing healthcheck")
        hc = services[name]["healthcheck"]
        expect("test" in hc and "interval" in hc, f"{name} healthcheck incomplete: {hc}")

    # App-only services should NOT have healthcheck
    for name in ("dashboard", "vault-watch", "notification-delivery", "health-watch", "managed-context-install"):
        expect("healthcheck" not in services[name], f"{name} should not have healthcheck")

    # Volume isolation: each service's volumes only reference its own deployment root
    dep_root = intent["state_roots"]["root"]
    for name, svc in services.items():
        for vol in svc["volumes"]:
            expect(vol["source"].startswith(dep_root), f"{name} volume {vol['source']} not under {dep_root}")

    print("PASS test_rendered_services_include_resource_limits_and_healthchecks")


def main() -> int:
    test_dry_run_renders_full_service_dns_access_intent_without_secrets()
    test_entitlement_gate_blocks_executable_intent_but_keeps_dry_run_visible()
    test_secret_validator_fails_job_and_same_idempotency_key_can_resume_after_fix()
    test_failed_provisioning_retry_clears_stale_timestamps_and_error()
    test_secret_validator_rejects_plaintext_provider_and_gateway_values()
    test_stock_image_credentials_use_file_env_and_resolver_fallbacks_are_explicit()
    test_failed_execution_job_gets_idempotent_rollback_plan_event()
    test_rendered_services_include_resource_limits_and_healthchecks()
    print("PASS all 8 ArcLink provisioning tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
