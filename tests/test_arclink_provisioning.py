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
    control = load_module("arclink_control.py", "arclink_control_provisioning_render_test")
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
        "notion-webhook",
        "notification-delivery",
        "health-watch",
        "managed-context-install",
    }
    expect(set(services) == expected_services, sorted(services))
    expect(
        services["notification-delivery"]["command"] == [
            "./bin/docker-job-loop.sh",
            "notification-delivery",
            "5",
            "./bin/arclink-notification-delivery.sh",
        ],
        str(services["notification-delivery"]),
    )
    expect(intent["execution"]["ready"], str(intent["execution"]))
    expect(intent["state_roots"]["root"] == "/arcdata/deployments/dep_1-amber-vault-1a2b", str(intent["state_roots"]))
    expect(intent["state_roots"]["linked_resources"].endswith("/linked-resources"), str(intent["state_roots"]))
    expect(intent["state_roots"]["nextcloud"].endswith("/state/nextcloud"), str(intent["state_roots"]))
    expect(intent["state_roots"]["nextcloud_db"].endswith("/state/nextcloud/db"), str(intent["state_roots"]))
    expect(intent["state_roots"]["nextcloud_redis"].endswith("/state/nextcloud/redis"), str(intent["state_roots"]))
    expect(compose_secrets["nextcloud_db_password"]["secret_ref"] == "secret://arclink/nextcloud/dep_1/db-password", str(compose_secrets))
    expect(compose_secrets["nextcloud_db_password"]["target"] == "/run/secrets/nextcloud_db_password", str(compose_secrets))
    expect(compose_secrets["nextcloud_admin_password"]["target"] == "/run/secrets/nextcloud_admin_password", str(compose_secrets))
    expect(compose_secrets["dashboard_password"]["secret_ref"] == "secret://arclink/dashboard/users/user_1/password", str(compose_secrets))
    expect(compose_secrets["dashboard_password"]["target"] == "/run/secrets/dashboard_password", str(compose_secrets))
    expect("code_server_password" not in compose_secrets, str(compose_secrets))
    expect(intent["environment"]["HERMES_HOME"] == "/home/arclink/.hermes", str(intent["environment"]))
    expect(intent["environment"]["VAULT_DIR"] == "/srv/vault", str(intent["environment"]))
    expect(intent["environment"]["DRIVE_ROOT"] == "/srv/vault", str(intent["environment"]))
    expect(intent["environment"]["CODE_WORKSPACE_ROOT"] == "/workspace", str(intent["environment"]))
    expect(intent["environment"]["DRIVE_LINKED_ROOT"] == "/linked-resources", str(intent["environment"]))
    expect(intent["environment"]["CODE_LINKED_ROOT"] == "/linked-resources", str(intent["environment"]))
    expect(intent["environment"]["ARCLINK_LINKED_RESOURCES_ROOT"] == "/linked-resources", str(intent["environment"]))
    expect(intent["environment"]["TERMINAL_WORKSPACE_ROOT"] == "/workspace", str(intent["environment"]))
    expect(intent["environment"]["TERMINAL_TUI_COMMAND"] == "/opt/arclink/runtime/hermes-venv/bin/hermes", str(intent["environment"]))
    expect(intent["environment"]["ARCLINK_DRIVE_ROOT"] == "/srv/vault", str(intent["environment"]))
    expect(intent["environment"]["ARCLINK_CODE_WORKSPACE_ROOT"] == "/workspace", str(intent["environment"]))
    expect(intent["environment"]["ARCLINK_TERMINAL_TUI_COMMAND"] == "/opt/arclink/runtime/hermes-venv/bin/hermes", str(intent["environment"]))
    expect(intent["environment"]["HERMES_TUI_DIR"] == "/opt/arclink/runtime/hermes-agent-src/ui-tui", str(intent["environment"]))
    expect(intent["environment"]["TELEGRAM_REACTIONS"] == "true", str(intent["environment"]))
    expect(intent["environment"]["DISCORD_REACTIONS"] == "true", str(intent["environment"]))
    expect(intent["environment"]["ARCLINK_CHUTES_API_KEY_FILE"] == "/run/secrets/chutes_api_key", str(intent["environment"]))
    expect(intent["environment"]["ARCLINK_DASHBOARD_USERNAME"] == "person@example.test", str(intent["environment"]))
    expect(intent["environment"]["QMD_STATE_DIR"] == "/home/arclink/.qmd", str(intent["environment"]))
    expect(intent["environment"]["QMD_MCP_CONTAINER_PORT"] == "8181", str(intent["environment"]))
    expect(intent["environment"]["QMD_MCP_LOOPBACK_PORT"] == "18181", str(intent["environment"]))
    expect(intent["environment"]["ARCLINK_MEMORY_SYNTH_STATE_DIR"] == "/srv/memory", str(intent["environment"]))
    expect(intent["environment"]["ARCLINK_BACKEND_ALLOWED_CIDRS"] == "172.16.0.0/12", str(intent["environment"]))
    for key in ("HERMES_HOME", "VAULT_DIR", "DRIVE_ROOT", "CODE_WORKSPACE_ROOT", "DRIVE_LINKED_ROOT", "CODE_LINKED_ROOT", "ARCLINK_LINKED_RESOURCES_ROOT", "TERMINAL_WORKSPACE_ROOT", "ARCLINK_DRIVE_ROOT", "ARCLINK_CODE_WORKSPACE_ROOT", "QMD_STATE_DIR", "ARCLINK_MEMORY_SYNTH_STATE_DIR"):
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
    expect(services["qmd-mcp"]["environment"]["QMD_INDEX_NAME"] == "vault-dep_1", str(services["qmd-mcp"]))
    hermes_dashboard_volumes = {item["target"]: item["source"] for item in services["hermes-dashboard"]["volumes"]}
    expect(hermes_dashboard_volumes["/home/arclink/.hermes"] == intent["state_roots"]["hermes_home"], str(services["hermes-dashboard"]))
    expect(hermes_dashboard_volumes["/srv/vault"] == intent["state_roots"]["vault"], str(services["hermes-dashboard"]))
    expect(hermes_dashboard_volumes["/workspace"] == intent["state_roots"]["code_workspace"], str(services["hermes-dashboard"]))
    expect(hermes_dashboard_volumes["/linked-resources"] == intent["state_roots"]["linked_resources"], str(services["hermes-dashboard"]))
    linked_volume = next(item for item in services["hermes-dashboard"]["volumes"] if item["target"] == "/linked-resources")
    expect(linked_volume["read_only"] is True, str(linked_volume))
    memory_synth_volumes = {item["target"]: item["source"] for item in services["memory-synth"]["volumes"]}
    expect(memory_synth_volumes["/srv/vault"] == intent["state_roots"]["vault"], str(services["memory-synth"]))
    expect(memory_synth_volumes[intent["environment"]["ARCLINK_MEMORY_SYNTH_STATE_DIR"]] == intent["state_roots"]["memory"], str(services["memory-synth"]))
    for service_name in ("vault-watch", "notion-webhook", "notification-delivery", "health-watch"):
        service_volumes = {item["target"]: item["source"] for item in services[service_name]["volumes"]}
        expect(
            service_volumes[intent["environment"]["ARCLINK_MEMORY_SYNTH_STATE_DIR"]] == intent["state_roots"]["memory"],
            f"{service_name} missing writable memory state volume: {services[service_name]}",
        )
    expect("code-server" not in services, str(services))
    expect(services["managed-context-install"]["command"][:2] == ["./bin/install-deployment-hermes-home.sh", "/home/arclink/arclink"], str(services["managed-context-install"]))
    managed_installer_volumes = {item["target"]: item["source"] for item in services["managed-context-install"]["volumes"]}
    expect(managed_installer_volumes["/home/arclink/.hermes"] == intent["state_roots"]["hermes_home"], str(services["managed-context-install"]))
    expect(managed_installer_volumes["/srv/vault"] == intent["state_roots"]["vault"], str(services["managed-context-install"]))
    expect(services["managed-context-install"]["environment"]["RUNTIME_DIR"] == "/opt/arclink/runtime", str(services["managed-context-install"]))
    expect(services["managed-context-install"]["environment"]["VAULT_DIR"] == "/srv/vault", str(services["managed-context-install"]))
    expect(services["managed-context-install"]["environment"]["ARCLINK_DASHBOARD_USERNAME"] == "person@example.test", str(services["managed-context-install"]))
    expect(services["managed-context-install"]["environment"]["ARCLINK_DASHBOARD_PASSWORD_FILE"] == "/run/secrets/dashboard_password", str(services["managed-context-install"]))
    expect(
        services["managed-context-install"]["environment"]["ARCLINK_HERMES_DOCS_VAULT_DIR"] == "/srv/vault/Agents_KB/hermes-agent-docs",
        str(services["managed-context-install"]),
    )
    expect({"source": "chutes_api_key", "target": "/run/secrets/chutes_api_key"} in services["managed-context-install"]["secrets"], str(services["managed-context-install"]))
    expect({"source": "dashboard_password", "target": "/run/secrets/dashboard_password"} in services["managed-context-install"]["secrets"], str(services["managed-context-install"]))
    expect({"source": "chutes_api_key", "target": "/run/secrets/chutes_api_key"} in services["hermes-dashboard"]["secrets"], str(services["hermes-dashboard"]))
    expect(services["hermes-dashboard"]["command"] == ["./bin/run-hermes-dashboard-proxy.sh"], str(services["hermes-dashboard"]))
    expect(
        intent["runtime_resolution"]["stock_image_file_env"]["nextcloud"] == [
            "POSTGRES_PASSWORD_FILE",
            "NEXTCLOUD_ADMIN_PASSWORD_FILE",
        ],
        str(intent["runtime_resolution"]),
    )
    expect(intent["runtime_resolution"]["entrypoint_file_resolver"] == {}, str(intent["runtime_resolution"]))
    expect("chutes_api_key" in intent["runtime_resolution"]["app_ref_resolver_required"], str(intent["runtime_resolution"]))
    expect("dashboard_password" in intent["runtime_resolution"]["app_ref_resolver_required"], str(intent["runtime_resolution"]))
    expect(services["hermes-gateway"]["labels"] == {}, str(services["hermes-gateway"]))
    expect(services["hermes-dashboard"]["labels"]["traefik.http.routers.arclink-amber-vault-1a2b-hermes.rule"] == "Host(`hermes-amber-vault-1a2b.example.test`)", str(services["hermes-dashboard"]))
    expect(services["hermes-dashboard"]["labels"]["traefik.docker.network"] == "arclink_default", str(services["hermes-dashboard"]))
    expect(services["nextcloud"]["labels"] == {}, str(services["nextcloud"]))
    expect(set(intent["dns"]) == {"dashboard", "hermes"}, str(intent["dns"]))
    expect(intent["access"]["urls"]["files"] == "https://u-amber-vault-1a2b.example.test/drive", str(intent["access"]))
    expect(intent["access"]["urls"]["code"] == "https://u-amber-vault-1a2b.example.test/code", str(intent["access"]))
    expect(intent["access"]["urls"]["notion"] == "https://u-amber-vault-1a2b.example.test/notion/webhook", str(intent["access"]))
    expect(intent["access"]["ssh"]["strategy"] == "cloudflare_access_tcp", str(intent["access"]))
    expect(intent["integrations"]["notion"]["mode"] == "per_deployment", str(intent["integrations"]))
    expect(intent["integrations"]["notion"]["callback_url"] == intent["access"]["urls"]["notion"], str(intent["integrations"]))
    expect(intent["integrations"]["notion"]["secret_ref"] == "secret://arclink/notion/dep_1/webhook-secret", str(intent["integrations"]))
    expect(services["notion-webhook"]["labels"]["traefik.http.routers.arclink-amber-vault-1a2b-notion-webhook.rule"] == "Host(`u-amber-vault-1a2b.example.test`) && PathPrefix(`/notion/webhook`)", str(services["notion-webhook"]))
    expect(services["notion-webhook"]["labels"]["traefik.http.routers.arclink-amber-vault-1a2b-notion-webhook.priority"] == "200", str(services["notion-webhook"]))
    expect(services["notion-webhook"]["environment"]["ARCLINK_NOTION_CALLBACK_URL"] == intent["access"]["urls"]["notion"], str(services["notion-webhook"]))
    text = render_text(intent)
    for forbidden in ("sk_", "whsec_", "xoxb-", "ntn_", "123456:"):
        expect(forbidden not in text, text)
    health = conn.execute("SELECT service_name, status FROM arclink_service_health WHERE deployment_id = 'dep_1'").fetchall()
    expect(len(health) == len(expected_services), str([dict(row) for row in health]))
    expect({row["status"] for row in health} == {"dry_run_planned"}, str([dict(row) for row in health]))
    events = conn.execute("SELECT event_type FROM arclink_events WHERE subject_id = 'dep_1' ORDER BY created_at").fetchall()
    event_types = {row["event_type"] for row in events}
    expect({"provisioning_planned", "provisioning_rendered", "provisioning_ready_for_execution"} <= event_types, str(event_types))
    print("PASS test_dry_run_renders_full_service_dns_access_intent_without_secrets")


def test_dashboard_password_defaults_to_user_scoped_secret_for_agent_sso() -> None:
    control = load_module("arclink_control.py", "arclink_control_provisioning_user_sso_test")
    provisioning = load_module("arclink_provisioning.py", "arclink_provisioning_user_sso_test")
    conn = memory_db(control)
    seed_deployment(control, conn)
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_2",
        user_id="user_1",
        prefix="second-vault-2b3c",
        base_domain="example.test",
        status="provisioning_ready",
    )
    control.upsert_arclink_user(conn, user_id="user_2", email="other@example.test", entitlement_state="paid")
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_3",
        user_id="user_2",
        prefix="other-vault-3c4d",
        base_domain="example.test",
        status="provisioning_ready",
    )
    intent_1 = provisioning.render_arclink_provisioning_intent(conn, deployment_id="dep_1")
    intent_2 = provisioning.render_arclink_provisioning_intent(conn, deployment_id="dep_2")
    intent_3 = provisioning.render_arclink_provisioning_intent(conn, deployment_id="dep_3")
    ref_1 = intent_1["secret_refs"]["dashboard_password"]
    ref_2 = intent_2["secret_refs"]["dashboard_password"]
    ref_3 = intent_3["secret_refs"]["dashboard_password"]
    expect(ref_1 == "secret://arclink/dashboard/users/user_1/password", ref_1)
    expect(ref_2 == ref_1, f"same user deployments should share the dashboard password ref: {ref_1} vs {ref_2}")
    expect(ref_3 == "secret://arclink/dashboard/users/user_2/password", ref_3)
    expect(ref_3 != ref_1, f"different users must not share dashboard password refs: {ref_1} vs {ref_3}")
    print("PASS test_dashboard_password_defaults_to_user_scoped_secret_for_agent_sso")


def test_entitlement_gate_blocks_executable_intent_but_keeps_dry_run_visible() -> None:
    control = load_module("arclink_control.py", "arclink_control_provisioning_gate_test")
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
    control = load_module("arclink_control.py", "arclink_control_provisioning_resume_test")
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
    control = load_module("arclink_control.py", "arclink_control_provisioning_timestamp_test")
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
        "aws": {"notes": "AWS_ACCESS_KEY_ID=AKIAABCDEFGHIJKLMNOP"},
        "jwt": {"notes": "jwt=eyJaaaaaaaaaaaa.eyJbbbbbbbbbbbb.cccccccccccccccc"},
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
            "integrations": {
                "notion": {
                    "callback_url": "https://u-amber-vault-1a2b.example.test/notion/webhook",
                    "secret_ref": "secret://arclink/notion/dep_1/webhook-secret",
                }
            },
            "compose": {
                "secrets": {
                    "chutes_api_key": {
                        "source": "chutes_api_key",
                        "target": "/run/secrets/chutes_api_key",
                    }
                }
            },
        }
    )
    print("PASS test_secret_validator_rejects_plaintext_provider_and_gateway_values")


def test_stock_image_credentials_use_file_env_and_resolver_fallbacks_are_explicit() -> None:
    control = load_module("arclink_control.py", "arclink_control_provisioning_secret_resolution_test")
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
    for secret_name in ("nextcloud_db_password", "nextcloud_admin_password", "dashboard_password"):
        expect(compose_secrets[secret_name]["secret_ref"].startswith("secret://"), str(compose_secrets[secret_name]))
        expect(compose_secrets[secret_name]["target"] == f"/run/secrets/{secret_name}", str(compose_secrets[secret_name]))
    expect("code_server_password" not in compose_secrets, str(compose_secrets))
    expect(intent["runtime_resolution"]["entrypoint_file_resolver"] == {}, str(intent["runtime_resolution"]))
    expect(
        intent["runtime_resolution"]["app_ref_resolver_required"] == ["chutes_api_key", "dashboard_password", "notion_webhook_secret"],
        str(intent["runtime_resolution"]),
    )
    print("PASS test_stock_image_credentials_use_file_env_and_resolver_fallbacks_are_explicit")


def test_nextcloud_postgres_database_name_is_identifier_safe() -> None:
    control = load_module("arclink_control.py", "arclink_control_provisioning_db_name_test")
    provisioning = load_module("arclink_provisioning.py", "arclink_provisioning_db_name_test")
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_1", email="person@example.test", entitlement_state="paid")
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep.with-dash.and.dot",
        user_id="user_1",
        prefix="amber-vault-1a2b",
        base_domain="example.test",
        status="provisioning_ready",
    )
    intent = provisioning.render_arclink_provisioning_intent(conn, deployment_id="dep.with-dash.and.dot")
    db_service_env = intent["compose"]["services"]["nextcloud-db"]["environment"]
    app_service_env = intent["compose"]["services"]["nextcloud"]["environment"]
    db_name = db_service_env["POSTGRES_DB"]
    expect(db_name == "nextcloud_dep_with_dash_and_dot", str(db_service_env))
    expect(app_service_env["POSTGRES_DB"] == db_name, str(app_service_env))
    expect("-" not in db_name and "." not in db_name, db_name)
    expect(len(db_name) <= 63, db_name)
    print("PASS test_nextcloud_postgres_database_name_is_identifier_safe")


def test_failed_execution_job_gets_idempotent_rollback_plan_event() -> None:
    control = load_module("arclink_control.py", "arclink_control_provisioning_rollback_test")
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
    control = load_module("arclink_control.py", "arclink_control_provisioning_limits_test")
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
    for name in ("nextcloud-db", "nextcloud-redis", "nextcloud"):
        expect("healthcheck" in services[name], f"{name} missing healthcheck")
        hc = services[name]["healthcheck"]
        expect("test" in hc and "interval" in hc, f"{name} healthcheck incomplete: {hc}")

    # App-only services should NOT have healthcheck
    for name in ("dashboard", "vault-watch", "notion-webhook", "notification-delivery", "health-watch", "managed-context-install"):
        expect("healthcheck" not in services[name], f"{name} should not have healthcheck")

    # Volume isolation: each service's volumes only reference its own deployment root
    dep_root = intent["state_roots"]["root"]
    for name, svc in services.items():
        for vol in svc["volumes"]:
            expect(vol["source"].startswith(dep_root), f"{name} volume {vol['source']} not under {dep_root}")

    print("PASS test_rendered_services_include_resource_limits_and_healthchecks")


def test_tailscale_ingress_renders_path_urls_and_no_cloudflare_dns() -> None:
    control = load_module("arclink_control.py", "arclink_control_provisioning_tailscale_test")
    provisioning = load_module("arclink_provisioning.py", "arclink_provisioning_tailscale_test")
    conn = memory_db(control)
    seed_deployment(control, conn)
    intent = provisioning.render_arclink_provisioning_intent(
        conn,
        deployment_id="dep_1",
        ingress_mode="tailscale",
        tailscale_dns_name="worker.example.test",
        tailscale_host_strategy="path",
        tailscale_notion_path="/notion/webhook",
    )
    expect(intent["deployment"]["ingress_mode"] == "tailscale", str(intent["deployment"]))
    expect(intent["dns"] == {}, str(intent["dns"]))
    expect(intent["execution"]["dns_provider"] == "tailscale", str(intent["execution"]))
    expect(intent["access"]["urls"]["dashboard"] == "https://worker.example.test/u/amber-vault-1a2b", str(intent["access"]))
    expect(intent["access"]["urls"]["files"] == "https://worker.example.test/u/amber-vault-1a2b/drive", str(intent["access"]))
    expect(intent["access"]["urls"]["code"] == "https://worker.example.test/u/amber-vault-1a2b/code", str(intent["access"]))
    expect(intent["access"]["urls"]["hermes"] == "https://worker.example.test/u/amber-vault-1a2b/hermes", str(intent["access"]))
    expect(intent["access"]["urls"]["notion"] == "https://worker.example.test/u/amber-vault-1a2b/notion/webhook", str(intent["access"]))
    expect(intent["access"]["ssh"]["strategy"] == "tailscale_direct_ssh", str(intent["access"]))
    expect(intent["access"]["ssh"]["command_hint"] == "ssh arc-amber-vault-1a2b@worker.example.test", str(intent["access"]))
    labels = intent["compose"]["services"]["nextcloud"]["labels"]
    expect(labels == {}, str(labels))
    dashboard_labels = intent["compose"]["services"]["dashboard"]["labels"]
    expect(dashboard_labels == {}, str(dashboard_labels))
    hermes_labels = intent["compose"]["services"]["hermes-dashboard"]["labels"]
    expect(
        hermes_labels["traefik.http.routers.arclink-amber-vault-1a2b-hermes-root.rule"]
        == "Host(`worker.example.test`) && PathPrefix(`/u/amber-vault-1a2b`)",
        str(hermes_labels),
    )
    expect(
        hermes_labels["traefik.http.middlewares.arclink-amber-vault-1a2b-hermes-root-strip.stripprefix.prefixes"]
        == "/u/amber-vault-1a2b",
        str(hermes_labels),
    )
    expect(
        hermes_labels["traefik.http.routers.arclink-amber-vault-1a2b-hermes.rule"]
        == "Host(`worker.example.test`) && PathPrefix(`/u/amber-vault-1a2b/hermes`)",
        str(hermes_labels),
    )
    notion_labels = intent["compose"]["services"]["notion-webhook"]["labels"]
    expect(
        notion_labels["traefik.http.routers.arclink-amber-vault-1a2b-notion-webhook.rule"]
        == "Host(`worker.example.test`) && PathPrefix(`/u/amber-vault-1a2b/notion/webhook`)",
        str(notion_labels),
    )
    expect(
        notion_labels["traefik.http.middlewares.arclink-amber-vault-1a2b-notion-webhook-strip-user-prefix.stripprefix.prefixes"]
        == "/u/amber-vault-1a2b",
        str(notion_labels),
    )
    expect(intent["environment"]["ARCLINK_TAILSCALE_NOTION_PATH"] == "/notion/webhook", str(intent["environment"]))
    print("PASS test_tailscale_ingress_renders_path_urls_and_no_cloudflare_dns")


def test_tailscale_ingress_uses_dedicated_app_ports_when_recorded() -> None:
    control = load_module("arclink_control.py", "arclink_control_provisioning_tailnet_ports_test")
    provisioning = load_module("arclink_provisioning.py", "arclink_provisioning_tailnet_ports_test")
    conn = memory_db(control)
    seed_deployment(
        control,
        conn,
        metadata={"tailnet_service_ports": {"hermes": 8443, "files": 8444, "code": 8445}},
    )
    intent = provisioning.render_arclink_provisioning_intent(
        conn,
        deployment_id="dep_1",
        ingress_mode="tailscale",
        tailscale_dns_name="worker.example.test",
        tailscale_host_strategy="path",
    )
    env = intent["environment"]
    services = intent["compose"]["services"]
    expect(intent["access"]["urls"]["dashboard"] == "https://worker.example.test/u/amber-vault-1a2b", str(intent["access"]))
    expect(intent["access"]["urls"]["hermes"] == "https://worker.example.test/u/amber-vault-1a2b/hermes", str(intent["access"]))
    expect(intent["access"]["urls"]["files"] == "https://worker.example.test/u/amber-vault-1a2b/drive", str(intent["access"]))
    expect(intent["access"]["urls"]["code"] == "https://worker.example.test/u/amber-vault-1a2b/code", str(intent["access"]))
    expect(env["ARCLINK_HERMES_URL"] == "https://worker.example.test/u/amber-vault-1a2b/hermes", str(env))
    expect(env["ARCLINK_FILES_URL"] == "https://worker.example.test/u/amber-vault-1a2b/drive", str(env))
    nextcloud_env = services["nextcloud"]["environment"]
    expect("OVERWRITEPROTOCOL" not in nextcloud_env, str(nextcloud_env))
    expect("OVERWRITEHOST" not in nextcloud_env, str(nextcloud_env))
    expect("OVERWRITECLIURL" not in nextcloud_env, str(nextcloud_env))
    print("PASS test_tailscale_ingress_uses_dedicated_app_ports_when_recorded")


def main() -> int:
    test_dry_run_renders_full_service_dns_access_intent_without_secrets()
    test_dashboard_password_defaults_to_user_scoped_secret_for_agent_sso()
    test_entitlement_gate_blocks_executable_intent_but_keeps_dry_run_visible()
    test_secret_validator_fails_job_and_same_idempotency_key_can_resume_after_fix()
    test_failed_provisioning_retry_clears_stale_timestamps_and_error()
    test_secret_validator_rejects_plaintext_provider_and_gateway_values()
    test_stock_image_credentials_use_file_env_and_resolver_fallbacks_are_explicit()
    test_nextcloud_postgres_database_name_is_identifier_safe()
    test_failed_execution_job_gets_idempotent_rollback_plan_event()
    test_rendered_services_include_resource_limits_and_healthchecks()
    test_tailscale_ingress_renders_path_urls_and_no_cloudflare_dns()
    test_tailscale_ingress_uses_dedicated_app_ports_when_recorded()
    print("PASS all 12 ArcLink provisioning tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
