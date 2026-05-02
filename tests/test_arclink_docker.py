#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read(path: str) -> str:
    return (REPO / path).read_text(encoding="utf-8")


def test_dockerfile_installs_pinned_runtime_assets() -> None:
    body = read("Dockerfile")
    expect("FROM node:22-bookworm-slim" in body, body)
    expect("config/pins.json" in body, body)
    expect("@tobilu/qmd@${qmd_version}" in body, body)
    expect("hermes-agent" in body and "hermes-venv" in body, body)
    expect("stripe" in body, body)
    expect("cd /home/arclink/arclink/web" in body and "npm run build" in body, body)
    expect("ARCLINK_API_INTERNAL_URL=http://control-api:8900" in body, body)
    expect("poppler-utils" in body and "inotify-tools" in body and "sqlite3" in body, body)
    expect("download.docker.com/linux/debian" in body and "docker-ce-cli" in body, body)
    expect("docker-compose-plugin" in body, body)
    expect("iproute2" in body, body)
    print("PASS test_dockerfile_installs_pinned_runtime_assets")


def test_compose_defines_full_stack_services() -> None:
    body = read("compose.yaml")
    expect("arclink-app:" in body and "dockerfile: Dockerfile" in body, body)
    expect('profiles: ["build"]' in body, body)
    expect("ARCLINK_BACKEND_ALLOWED_CIDRS:" in body, body)
    expect("ARCLINK_BASE_DOMAIN:" in body and "ARCLINK_PRIMARY_PROVIDER:" in body, body)
    expect("ARCLINK_INGRESS_MODE:" in body and "ARCLINK_TAILSCALE_DNS_NAME:" in body, body)
    expect("ARCLINK_CONTROL_PROVISIONER_ENABLED:" in body and "ARCLINK_EXECUTOR_ADAPTER:" in body, body)
    expect("STRIPE_WEBHOOK_SECRET:" in body and "CLOUDFLARE_API_TOKEN:" in body and "CHUTES_API_KEY:" in body, body)
    expect("ARCLINK_SQLITE_JOURNAL_MODE: ${ARCLINK_SQLITE_JOURNAL_MODE:-DELETE}" in body, body)
    expect("QMD_MCP_HOST_PORT:" in body, body)
    expect("ARCLINK_DOCKER_AGENT_HOME_ROOT:" in body, body)
    expect("ARCLINK_DOCKER_HOST_PRIV_DIR:" in body, body)
    expect("host.docker.internal:host-gateway" in body, body)
    expect("ARCLINK_HEALTH_WATCH_HEALTH_CMD: ./bin/docker-health.sh" in body, body)
    expect("POSTGRES_PASSWORD:?run ./deploy.sh docker bootstrap first" in body, body)
    expect("NEXTCLOUD_ADMIN_PASSWORD:?run ./deploy.sh docker bootstrap first" in body, body)
    expect("POSTGRES_PASSWORD:-change-me" not in body, body)
    expect("NEXTCLOUD_ADMIN_PASSWORD:-change-me" not in body, body)
    for service in (
        "postgres:",
        "redis:",
        "nextcloud:",
        "arclink-mcp:",
        "qmd-mcp:",
        "notion-webhook:",
        "control-api:",
        "control-web:",
        "control-ingress:",
        "control-provisioner:",
        "vault-watch:",
        "agent-supervisor:",
        "ssot-batcher:",
        "notification-delivery:",
        "health-watch:",
        "curator-refresh:",
        "qmd-refresh:",
        "pdf-ingest:",
        "memory-synth:",
        "hermes-docs-sync:",
        "quarto-render:",
        "backup:",
    ):
        expect(service in body, f"missing service {service}\n{body}")
    expect("127.0.0.1:${ARCLINK_MCP_PORT:-8282}:8282" in body, body)
    expect("127.0.0.1:${QMD_MCP_PORT:-8181}:8181" in body, body)
    expect("127.0.0.1:${NEXTCLOUD_PORT:-18080}:80" in body, body)
    expect("127.0.0.1:${ARCLINK_API_PORT:-8900}:8900" in body, body)
    expect("127.0.0.1:${ARCLINK_WEB_PORT:-3000}:8080" in body, body)
    expect("python/arclink_hosted_api.py" in body and "cd web && npm run start" in body, body)
    expect("python/arclink_sovereign_worker.py" in body and "control-provisioner" in body, body)
    expect("./arclink-priv/secrets/ssh:/root/.ssh" in body, body)
    expect("ARCLINK_LOCAL_FLEET_SSH_USER: ${ARCLINK_LOCAL_FLEET_SSH_USER:-arclink}" in body, body)
    expect(
        "ARCLINK_FLEET_SSH_KEY_PATH: ${ARCLINK_FLEET_SSH_KEY_PATH:-/home/arclink/arclink/arclink-priv/secrets/ssh/id_ed25519}"
        in body,
        body,
    )
    expect("${ARCLINK_STATE_ROOT_BASE:-/arcdata/deployments}:${ARCLINK_STATE_ROOT_BASE:-/arcdata/deployments}" in body, body)
    expect("ARCLINK_AGENT_SERVICE_MANAGER: docker-supervisor" in body, body)
    expect("ARCLINK_DOCKER_NETWORK: ${ARCLINK_DOCKER_NETWORK:-arclink_default}" in body, body)
    expect("Intentional trusted-host boundary" in body, body)
    expect(
        "- .:/home/arclink/arclink" in body
        and "${ARCLINK_DOCKER_HOST_REPO_DIR:-.}:${ARCLINK_DOCKER_HOST_REPO_DIR:-/home/arclink/arclink}" in body,
        "agent-supervisor and curator-refresh must mount the live checkout for Docker operator actions",
    )
    expect(
        "/var/run/docker.sock:/var/run/docker.sock" in body,
        "agent-supervisor must intentionally mount the Docker socket to reconcile per-agent containers",
    )
    expect("ARCLINK_AGENT_DASHBOARD_PROXY_PORT_RANGE" not in body, body)
    expect("./bin/docker-agent-supervisor.sh" in body, body)
    print("PASS test_compose_defines_full_stack_services")


def test_docker_operator_commands_are_present() -> None:
    body = read("bin/arclink-docker.sh")
    deploy = read("bin/deploy.sh")
    component_upgrade = read("bin/component-upgrade.sh")
    job_loop = read("bin/docker-job-loop.sh")
    ctl = read("python/arclink_ctl.py")
    rotate = body[body.index("docker_rotate_nextcloud_secrets()"):body.index("docker_pins_show()")]
    for command in (
        "bootstrap)",
        "write-config)",
        "config)",
        "build)",
        "up)",
        "down)",
        "ports)",
        "logs)",
        "health)",
        "provision-once)",
        "notion-ssot)",
        "notion-migrate)",
        "notion-transfer)",
        "enrollment-status)",
        "enrollment-trace)",
        "enrollment-align)",
        "enrollment-reset)",
        "curator-setup)",
        "rotate-nextcloud-secrets)",
        "agent-payload|agent)",
        "pins-show)",
        "pins-check)",
        "pin-upgrade-notify)",
        "teardown)",
        "remove)",
    ):
        expect(command in body, f"missing command case {command}\n{body}")
    expect('DOCKER_ENV_FILE="${ARCLINK_DOCKER_ENV_FILE:-$REPO_DIR/arclink-priv/config/docker.env}"' in body, body)
    expect('ARCLINK_DOCKER_REWRITE_CONFIG="${ARCLINK_DOCKER_REWRITE_CONFIG:-0}"' in body, body)
    expect('env_args=(--env-file "$DOCKER_ENV_FILE")' in body, body)
    expect('docker compose "${env_args[@]}" -f "$COMPOSE_FILE"' in body, body)
    expect("compose build arclink-app" in body, body)
    expect("compose config -q" in body, "docker config should validate without printing expanded secrets by default")
    expect("--unsafe-print" in body, "full Docker config output should require an explicit unsafe flag")
    expect('elif [[ "$1" == "--unsafe-print" ]]' in body and 'compose config "$@"' in body, "full compose config should be reachable only behind --unsafe-print")
    expect("reserve_docker_ports()" in body, body)
    expect("compose up -d --no-build" in body, body)
    expect("show_ports()" in body, body)
    expect("docker_port_set_available()" in body, body)
    expect("host_port_available_for_service \"$web_port\" control-ingress 8080" in body, body)
    expect("QMD_MCP_PORT" in body and "ARCLINK_MCP_PORT" in body and "ARCLINK_API_PORT" in body and "ARCLINK_WEB_PORT" in body, body)
    expect("18181 + offset" in body and "18282 + offset" in body and "28080 + offset" in body, body)
    expect("18900 + offset" in body and "13000 + offset" in body, body)
    expect("ports.json" in body, body)
    expect("agent-supervisor" in body, body)
    expect("control-provisioner" in body, body)
    expect("http://127.0.0.1/status.php" in body, body)
    expect("http://127.0.0.1:8900/api/v1/health" in body and "http://127.0.0.1:3000" in body, body)
    expect("docker_provision_once()" in body and "arclink_sovereign_worker.py" in body, body)
    expect('ensure_env_file_value ARCLINK_LOCAL_FLEET_SSH_USER "arclink"' in body, body)
    expect(
        'ensure_env_file_value ARCLINK_FLEET_SSH_KEY_PATH "/home/arclink/arclink/arclink-priv/secrets/ssh/id_ed25519"'
        in body,
        body,
    )
    expect("qmd-mcp" in body and "qmd --version" in body, body)
    expect('pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' in body, body)
    expect("health-watch" in body and "compose exec -T health-watch ./bin/docker-health.sh" in body, body)
    expect("docker_reconcile()" in body and "./bin/arclink-ctl org-profile apply --yes" in body, body)
    expect("wait_for_docker_agent_reconcile()" in body and "arclink-vault-reconciler.json" in body, body)
    expect("docker_record_release_state()" in body and '"deployed_from": "docker-checkout"' in body, body)
    expect("docker_live_agent_smoke()" in body and "./bin/live-agent-tool-smoke.sh" in body, body)
    expect("COMPOSE_PROFILES=curator,quarto,backup" in body, body)
    expect("FAIL Docker Compose config is valid, but no ArcLink services are running." in body, body)
    expect("docker_enrollment_status()" in body, body)
    expect("docker_notion_migrate()" in body and "compose stop arclink-mcp ssot-batcher agent-supervisor" in body, body)
    expect("Docker supervisor loop (not systemd)" in body, body)
    expect("docker_enrollment_align()" in body and "./bin/arclink-enrollment-provision.sh" in body, body)
    expect("docker_enrollment_reset()" in body and "--remove-nextcloud-user" in body, body)
    expect("docker_rotate_nextcloud_secrets()" in body, body)
    expect("user:resetpassword --password-from-env" in body, body)
    expect("ALTER ROLE" in body and "PASSWORD" in body, body)
    expect(
        '-e OC_PASS="$new_admin_password"' not in rotate,
        "Docker Nextcloud rotation should not expose the admin password in compose argv",
    )
    expect(
        "sys.argv[2]" not in rotate,
        "Docker Nextcloud rotation should not pass the new database password through Python argv",
    )
    expect(
        "ARCLINK_NEXTCLOUD_DB_PASSWORD" in rotate and "-e ARCLINK_NEXTCLOUD_DB_PASSWORD" in rotate,
        "Docker Nextcloud rotation should pass the database password through environment passthrough",
    )
    expect("docker_component_upgrade_apply()" in body, body)
    expect("ARCLINK_COMPONENT_UPGRADE_MODE=docker" in body, body)
    expect("deploy.sh docker enrollment-status" in deploy, deploy)
    expect("deploy.sh control install" in deploy and "control-install" in deploy and "control-provision-once" in deploy, deploy)
    expect("docker-enrollment-status" in deploy and "docker-rotate-nextcloud-secrets" in deploy, deploy)
    expect("qmd-upgrade-check" in deploy and "node-upgrade" in deploy, deploy)
    expect('ARCLINK_COMPONENT_UPGRADE_MODE:-}" == "docker"' in component_upgrade, component_upgrade)
    expect('"$REPO_DIR/deploy.sh" docker upgrade' in component_upgrade, component_upgrade)
    expect('os.environ.get("ARCLINK_DOCKER_MODE") == "1"' in ctl and '["docker", "rm", "-f", container_name]' in ctl, ctl)
    expect("docker health passed" not in body.lower() or "Docker health passed." in body, body)
    expect("redact_output" in job_loop and 'cat "$output_file"' not in job_loop, "Docker job loop must redact failure output before logs/state")
    print("PASS test_docker_operator_commands_are_present")


def test_docker_component_upgrade_apply_loads_upstream_env_from_docker_config() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        (repo / "bin").mkdir(parents=True)
        (repo / "arclink-priv" / "config").mkdir(parents=True)
        shutil.copy(REPO / "bin" / "arclink-docker.sh", repo / "bin" / "arclink-docker.sh")
        fake_component_upgrade = repo / "bin" / "component-upgrade.sh"
        capture = root / "capture.txt"
        fake_component_upgrade.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env bash",
                    "set -euo pipefail",
                    "{",
                    '  printf "mode=%s\\n" "${ARCLINK_COMPONENT_UPGRADE_MODE:-}"',
                    '  printf "config=%s\\n" "${ARCLINK_CONFIG_FILE:-}"',
                    '  printf "repo=%s\\n" "${ARCLINK_UPSTREAM_REPO_URL:-}"',
                    '  printf "branch=%s\\n" "${ARCLINK_UPSTREAM_BRANCH:-}"',
                    '  printf "key_enabled=%s\\n" "${ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED:-}"',
                    '  printf "key_user=%s\\n" "${ARCLINK_UPSTREAM_DEPLOY_KEY_USER:-}"',
                    '  printf "key_path=%s\\n" "${ARCLINK_UPSTREAM_DEPLOY_KEY_PATH:-}"',
                    '  printf "known_hosts=%s\\n" "${ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE:-}"',
                    '  printf "args=%s\\n" "$*"',
                    '} >"$CAPTURE"',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        fake_component_upgrade.chmod(0o755)
        docker_env = repo / "arclink-priv" / "config" / "docker.env"
        docker_env.write_text(
            "\n".join(
                [
                    "ARCLINK_UPSTREAM_REPO_URL=git@github.com:example/arclink.git",
                    "ARCLINK_UPSTREAM_BRANCH=main",
                    "ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED=1",
                    "ARCLINK_UPSTREAM_DEPLOY_KEY_USER=operator",
                    f"ARCLINK_UPSTREAM_DEPLOY_KEY_PATH={root}/arclink-upstream-ed25519",
                    f"ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE={root}/known_hosts",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                "bash",
                str(repo / "bin" / "arclink-docker.sh"),
                "hermes-upgrade",
                "--ref",
                "abc123",
                "--skip-upgrade",
            ],
            cwd=repo,
            env={**os.environ, "CAPTURE": str(capture)},
            capture_output=True,
            text=True,
            timeout=30,
        )
        combined = (result.stdout or "") + (result.stderr or "")
        expect(result.returncode == 0, combined)
        captured = capture.read_text(encoding="utf-8")
        expect("mode=docker" in captured, captured)
        expect(f"config={docker_env}" in captured, captured)
        expect("repo=git@github.com:example/arclink.git" in captured, captured)
        expect("branch=main" in captured, captured)
        expect("key_enabled=1" in captured, captured)
        expect("key_user=operator" in captured, captured)
        expect(f"key_path={root}/arclink-upstream-ed25519" in captured, captured)
        expect(f"known_hosts={root}/known_hosts" in captured, captured)
        expect("args=hermes-agent apply --ref abc123 --skip-upgrade" in captured, captured)
    print("PASS test_docker_component_upgrade_apply_loads_upstream_env_from_docker_config")


def test_docker_agent_supervisor_replaces_user_systemd_units() -> None:
    supervisor = read("python/arclink_docker_agent_supervisor.py")
    installer = read("bin/install-agent-user-services.sh")
    provisioner = read("python/arclink_enrollment_provisioner.py")
    code_runner = read("bin/run-agent-code-server.sh")
    expect("def ensure_container_user" in supervisor, supervisor)
    expect('"gateway", "run", "--replace"' in supervisor, supervisor)
    expect('"--host",\n                        "0.0.0.0"' in supervisor, supervisor)
    expect("arclink_basic_auth_proxy.py" in supervisor, supervisor)
    expect('"docker",\n                    "run"' in supervisor, supervisor)
    expect('"--network"' in supervisor and "ARCLINK_DOCKER_NETWORK" in supervisor, supervisor)
    expect('"ARCLINK_DOCKER_CONTAINER_NAME"' in supervisor, supervisor)
    expect("run-agent-code-server.sh" in supervisor, supervisor)
    expect('"cron", "tick"' in supervisor, supervisor)
    expect("ensure_agent_mcp_auth" in supervisor and "ensure_agent_mcp_bootstrap_token" in supervisor, supervisor)
    expect('"docker-agent-supervisor"' in supervisor, supervisor)
    expect("run_headless_identity_setup" in supervisor and "arclink_headless_hermes_setup.py" in supervisor, supervisor)
    expect('"--identity-only"' in supervisor and "agent_label" in supervisor and "user_label" in supervisor, supervisor)
    expect('ARCLINK_AGENT_SERVICE_MANAGER:-systemd' in installer, installer)
    expect("def _ensure_docker_user_ready" in provisioner, provisioner)
    expect('"ARCLINK_AGENT_SERVICE_MANAGER": "docker-supervisor"' in provisioner, provisioner)
    expect("docker_host_path()" in code_runner, code_runner)
    expect("ARCLINK_DOCKER_HOST_PRIV_DIR" in code_runner, code_runner)
    print("PASS test_docker_agent_supervisor_replaces_user_systemd_units")


def test_docker_entrypoint_generates_fresh_secrets() -> None:
    body = read("bin/docker-entrypoint.sh")
    expect("generate_secret()" in body, body)
    expect("secrets.token_urlsafe(32)" in body, body)
    expect('repair_placeholder_secret POSTGRES_PASSWORD "$PRIV_DIR/state/nextcloud/db/PG_VERSION"' in body, body)
    expect(
        'repair_placeholder_secret NEXTCLOUD_ADMIN_PASSWORD "$PRIV_DIR/state/nextcloud/html/config/config.php"' in body,
        body,
    )
    expect("POSTGRES_PASSWORD=$postgres_password" in body, body)
    expect("NEXTCLOUD_ADMIN_PASSWORD=$nextcloud_admin_password" in body, body)
    expect("POSTGRES_PASSWORD=change-me" not in body, body)
    expect("NEXTCLOUD_ADMIN_PASSWORD=change-me" not in body, body)
    print("PASS test_docker_entrypoint_generates_fresh_secrets")


def test_docker_health_script_checks_container_runtime() -> None:
    body = read("bin/docker-health.sh")
    expect("http://arclink-mcp:8282/health" in body, body)
    expect("http://notion-webhook:8283/health" in body, body)
    expect("http://nextcloud/status.php" in body, body)
    expect("Host: $host_header" in body, body)
    expect('"host.docker.internal" "${QMD_MCP_HOST_PORT:-${QMD_MCP_PORT:-8181}}"' in body, body)
    expect('"postgres" "5432"' in body, body)
    expect('"redis" "6379"' in body, body)
    expect("check_docker_agent_mcp_auth" in body, body)
    expect("validate_token" in body and "MCP token validates" in body, body)
    expect("arclink-managed-context" in body and "SOUL.md" in body, body)
    expect("arclink-vault-reconciler.json" in body, body)
    expect("Summary: %d ok, %d warn, %d fail" in body, body)
    print("PASS test_docker_health_script_checks_container_runtime")


def test_dockerignore_excludes_sensitive_and_generated_context() -> None:
    body = read(".dockerignore")
    for pattern in (
        "/.env",
        "/.env.*",
        "/config/arclink.env",
        "/config/install.answers.env",
        "/.arclink-operator.env",
        "/arclink-priv",
        "/logs",
        "/consensus",
        "/completion_log",
        "/.ralphie",
        "HUMAN_INSTRUCTIONS.md",
        "/research/HUMAN_FEEDBACK.md",
    ):
        expect(pattern in body, f"missing .dockerignore pattern {pattern}\n{body}")
    print("PASS test_dockerignore_excludes_sensitive_and_generated_context")


def test_readme_keeps_canonical_host_layout_root() -> None:
    body = read("README.md")
    expect("/home/arclink/" in body, body)
    expect("  arclink/                 # public repo" in body, body)
    print("PASS test_readme_keeps_canonical_host_layout_root")


def test_readme_distinguishes_control_shared_host_and_docker_paths() -> None:
    body = read("README.md")
    expect("## Deployment Paths" in body, body)
    expect("| **Sovereign Control Node Mode** |" in body, body)
    expect("| **Shared Host Mode** |" in body, body)
    expect("| **Shared Host Docker Mode** |" in body, body)
    expect("top-level default is Sovereign Control Node Mode." in body, body)
    expect("## Shared Host Mode" in body and "### Shared Host Quick Start" in body, body)
    expect("## Sovereign Control Node Mode" in body and "### Sovereign Control Node Quick Start" in body, body)
    expect("## Shared Host Docker Mode" in body and "### Shared Host Docker Quick Start" in body, body)
    expect("control menu and are the Dockerized paid-customer pod path" in body, body)
    expect("not Sovereign pods" in body, body)
    expect("own Notion callback surface" in body, body)
    expect("./deploy.sh control install" in body and "./deploy.sh install" in body and "./deploy.sh docker install" in body, body)
    expect("./deploy.sh docker enrollment-status" in body, body)
    expect("./deploy.sh docker rotate-nextcloud-secrets" in body, body)
    expect("Pinned-component Docker upgrades re-enter `./deploy.sh docker upgrade`" in body, body)
    print("PASS test_readme_distinguishes_control_shared_host_and_docker_paths")


def test_sovereign_ingress_docs_cover_domain_and_tailscale_modes() -> None:
    ingress = read("docs/arclink/ingress-plan.md")
    live = read("docs/arclink/live-e2e-secrets-needed.md")
    plan = read("IMPLEMENTATION_PLAN.md")
    expect("ARCLINK_INGRESS_MODE=domain" in ingress and "ARCLINK_INGRESS_MODE=tailscale" in ingress, ingress)
    expect("u-{prefix}.{base_domain}" in ingress and "files-{prefix}.{base_domain}" in ingress, ingress)
    expect("https://{tailscale_dns_name}/u/{prefix}/files" in ingress, ingress)
    expect("cloudflare_access_tcp" in ingress and "tailscale_direct_ssh" in ingress, ingress)
    expect("Domain mode:" in live and "Tailscale mode:" in live, live)
    expect("domain-or-Tailscale ingress" in plan, plan)
    print("PASS test_sovereign_ingress_docs_cover_domain_and_tailscale_modes")


def test_docker_compose_config_validates_when_docker_is_available() -> None:
    docker = subprocess.run(["bash", "-lc", "command -v docker >/dev/null && docker compose version >/dev/null"], cwd=REPO)
    if docker.returncode != 0:
        print("SKIP test_docker_compose_config_validates_when_docker_is_available")
        return
    result = subprocess.run(
        ["docker", "compose", "-f", "compose.yaml", "config", "-q"],
        cwd=REPO,
        env={
            **os.environ,
            "POSTGRES_PASSWORD": "compose-config-test-postgres",
            "NEXTCLOUD_ADMIN_PASSWORD": "compose-config-test-nextcloud",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    expect(result.returncode == 0, f"compose config failed: stdout={result.stdout!r} stderr={result.stderr!r}")
    print("PASS test_docker_compose_config_validates_when_docker_is_available")


def main() -> int:
    test_dockerfile_installs_pinned_runtime_assets()
    test_compose_defines_full_stack_services()
    test_docker_operator_commands_are_present()
    test_docker_component_upgrade_apply_loads_upstream_env_from_docker_config()
    test_docker_agent_supervisor_replaces_user_systemd_units()
    test_docker_entrypoint_generates_fresh_secrets()
    test_docker_health_script_checks_container_runtime()
    test_dockerignore_excludes_sensitive_and_generated_context()
    test_readme_keeps_canonical_host_layout_root()
    test_readme_distinguishes_control_shared_host_and_docker_paths()
    test_sovereign_ingress_docs_cover_domain_and_tailscale_modes()
    test_docker_compose_config_validates_when_docker_is_available()
    print("PASS all 12 ArcLink Docker regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
