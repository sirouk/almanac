#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
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
    expect("poppler-utils" in body and "inotify-tools" in body and "sqlite3" in body, body)
    expect("download.docker.com/linux/debian" in body and "docker-ce-cli" in body, body)
    expect("iproute2" in body, body)
    print("PASS test_dockerfile_installs_pinned_runtime_assets")


def test_compose_defines_full_stack_services() -> None:
    body = read("compose.yaml")
    expect("almanac-app:" in body and "dockerfile: Dockerfile" in body, body)
    expect('profiles: ["build"]' in body, body)
    expect("ALMANAC_BACKEND_ALLOWED_CIDRS:" in body, body)
    expect("ALMANAC_SQLITE_JOURNAL_MODE: ${ALMANAC_SQLITE_JOURNAL_MODE:-DELETE}" in body, body)
    expect("QMD_MCP_HOST_PORT:" in body, body)
    expect("ALMANAC_DOCKER_AGENT_HOME_ROOT:" in body, body)
    expect("ALMANAC_DOCKER_HOST_PRIV_DIR:" in body, body)
    expect("host.docker.internal:host-gateway" in body, body)
    expect("ALMANAC_HEALTH_WATCH_HEALTH_CMD: ./bin/docker-health.sh" in body, body)
    expect("POSTGRES_PASSWORD:?run ./deploy.sh docker bootstrap first" in body, body)
    expect("NEXTCLOUD_ADMIN_PASSWORD:?run ./deploy.sh docker bootstrap first" in body, body)
    expect("POSTGRES_PASSWORD:-change-me" not in body, body)
    expect("NEXTCLOUD_ADMIN_PASSWORD:-change-me" not in body, body)
    for service in (
        "postgres:",
        "redis:",
        "nextcloud:",
        "almanac-mcp:",
        "qmd-mcp:",
        "notion-webhook:",
        "vault-watch:",
        "agent-supervisor:",
        "ssot-batcher:",
        "notification-delivery:",
        "health-watch:",
        "curator-refresh:",
        "qmd-refresh:",
        "pdf-ingest:",
        "hermes-docs-sync:",
        "quarto-render:",
        "backup:",
    ):
        expect(service in body, f"missing service {service}\n{body}")
    expect("127.0.0.1:${ALMANAC_MCP_PORT:-8282}:8282" in body, body)
    expect("127.0.0.1:${QMD_MCP_PORT:-8181}:8181" in body, body)
    expect("127.0.0.1:${NEXTCLOUD_PORT:-18080}:80" in body, body)
    expect("ALMANAC_AGENT_SERVICE_MANAGER: docker-supervisor" in body, body)
    expect("ALMANAC_DOCKER_NETWORK: ${ALMANAC_DOCKER_NETWORK:-almanac_default}" in body, body)
    expect("Intentional trusted-host boundary" in body, body)
    expect(
        "/var/run/docker.sock:/var/run/docker.sock" in body,
        "agent-supervisor must intentionally mount the Docker socket to reconcile per-agent containers",
    )
    expect("ALMANAC_AGENT_DASHBOARD_PROXY_PORT_RANGE" not in body, body)
    expect("./bin/docker-agent-supervisor.sh" in body, body)
    print("PASS test_compose_defines_full_stack_services")


def test_docker_operator_commands_are_present() -> None:
    body = read("bin/almanac-docker.sh")
    deploy = read("bin/deploy.sh")
    component_upgrade = read("bin/component-upgrade.sh")
    ctl = read("python/almanac_ctl.py")
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
        "notion-ssot)",
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
    expect('DOCKER_ENV_FILE="${ALMANAC_DOCKER_ENV_FILE:-$REPO_DIR/almanac-priv/config/docker.env}"' in body, body)
    expect('ALMANAC_DOCKER_REWRITE_CONFIG="${ALMANAC_DOCKER_REWRITE_CONFIG:-0}"' in body, body)
    expect('env_args=(--env-file "$DOCKER_ENV_FILE")' in body, body)
    expect('docker compose "${env_args[@]}" -f "$COMPOSE_FILE"' in body, body)
    expect("compose build almanac-app" in body, body)
    expect("reserve_docker_ports()" in body, body)
    expect("compose up -d --no-build" in body, body)
    expect("show_ports()" in body, body)
    expect("docker_port_set_available()" in body, body)
    expect("QMD_MCP_PORT" in body and "ALMANAC_MCP_PORT" in body, body)
    expect("18181 + offset" in body and "18282 + offset" in body and "28080 + offset" in body, body)
    expect("ports.json" in body, body)
    expect("agent-supervisor" in body, body)
    expect("http://127.0.0.1/status.php" in body, body)
    expect("qmd-mcp" in body and "qmd --version" in body, body)
    expect('pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' in body, body)
    expect("health-watch" in body and "compose exec -T health-watch ./bin/docker-health.sh" in body, body)
    expect("COMPOSE_PROFILES=curator,quarto,backup" in body, body)
    expect("FAIL Docker Compose config is valid, but no Almanac services are running." in body, body)
    expect("docker_enrollment_status()" in body, body)
    expect("Docker supervisor loop (not systemd)" in body, body)
    expect("docker_enrollment_align()" in body and "./bin/almanac-enrollment-provision.sh" in body, body)
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
        "ALMANAC_NEXTCLOUD_DB_PASSWORD" in rotate and "-e ALMANAC_NEXTCLOUD_DB_PASSWORD" in rotate,
        "Docker Nextcloud rotation should pass the database password through environment passthrough",
    )
    expect("docker_component_upgrade_apply()" in body, body)
    expect("ALMANAC_COMPONENT_UPGRADE_MODE=docker" in body, body)
    expect("deploy.sh docker enrollment-status" in deploy, deploy)
    expect("docker-enrollment-status" in deploy and "docker-rotate-nextcloud-secrets" in deploy, deploy)
    expect("qmd-upgrade-check" in deploy and "node-upgrade" in deploy, deploy)
    expect('ALMANAC_COMPONENT_UPGRADE_MODE:-}" == "docker"' in component_upgrade, component_upgrade)
    expect('"$REPO_DIR/deploy.sh" docker upgrade' in component_upgrade, component_upgrade)
    expect('os.environ.get("ALMANAC_DOCKER_MODE") == "1"' in ctl and '["docker", "rm", "-f", container_name]' in ctl, ctl)
    expect("docker health passed" not in body.lower() or "Docker health passed." in body, body)
    print("PASS test_docker_operator_commands_are_present")


def test_docker_agent_supervisor_replaces_user_systemd_units() -> None:
    supervisor = read("python/almanac_docker_agent_supervisor.py")
    installer = read("bin/install-agent-user-services.sh")
    provisioner = read("python/almanac_enrollment_provisioner.py")
    code_runner = read("bin/run-agent-code-server.sh")
    expect("def ensure_container_user" in supervisor, supervisor)
    expect('"gateway", "run", "--replace"' in supervisor, supervisor)
    expect('"--host",\n                        "0.0.0.0"' in supervisor, supervisor)
    expect("almanac_basic_auth_proxy.py" in supervisor, supervisor)
    expect('"docker",\n                    "run"' in supervisor, supervisor)
    expect('"--network"' in supervisor and "ALMANAC_DOCKER_NETWORK" in supervisor, supervisor)
    expect('"ALMANAC_DOCKER_CONTAINER_NAME"' in supervisor, supervisor)
    expect("run-agent-code-server.sh" in supervisor, supervisor)
    expect('"cron", "tick"' in supervisor, supervisor)
    expect('ALMANAC_AGENT_SERVICE_MANAGER:-systemd' in installer, installer)
    expect("def _ensure_docker_user_ready" in provisioner, provisioner)
    expect('"ALMANAC_AGENT_SERVICE_MANAGER": "docker-supervisor"' in provisioner, provisioner)
    expect("docker_host_path()" in code_runner, code_runner)
    expect("ALMANAC_DOCKER_HOST_PRIV_DIR" in code_runner, code_runner)
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
    expect("http://almanac-mcp:8282/health" in body, body)
    expect("http://notion-webhook:8283/health" in body, body)
    expect("http://nextcloud/status.php" in body, body)
    expect("Host: $host_header" in body, body)
    expect('"host.docker.internal" "${QMD_MCP_HOST_PORT:-${QMD_MCP_PORT:-8181}}"' in body, body)
    expect('"postgres" "5432"' in body, body)
    expect('"redis" "6379"' in body, body)
    expect("Summary: %d ok, %d warn, %d fail" in body, body)
    print("PASS test_docker_health_script_checks_container_runtime")


def test_dockerignore_excludes_sensitive_and_generated_context() -> None:
    body = read(".dockerignore")
    for pattern in (
        "/.env",
        "/.env.*",
        "/config/almanac.env",
        "/config/install.answers.env",
        "/.almanac-operator.env",
        "/almanac-priv",
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
    expect("/home/almanac/" in body, body)
    expect("  almanac/                 # public repo" in body, body)
    print("PASS test_readme_keeps_canonical_host_layout_root")


def test_readme_distinguishes_baremetal_and_containerized_paths() -> None:
    body = read("README.md")
    expect("## Deployment Paths" in body, body)
    expect("| **Baremetal** |" in body, body)
    expect("| **Containerized** |" in body, body)
    expect("If a command does not include the word `docker`, it uses the baremetal path." in body, body)
    expect("## Baremetal Path" in body and "### Baremetal Quick Start" in body, body)
    expect("## Containerized Path" in body and "### Containerized Quick Start" in body, body)
    expect("./deploy.sh install" in body and "./deploy.sh docker install" in body, body)
    expect("./deploy.sh docker enrollment-status" in body, body)
    expect("./deploy.sh docker rotate-nextcloud-secrets" in body, body)
    expect("Pinned-component Docker upgrades re-enter `./deploy.sh docker upgrade`" in body, body)
    print("PASS test_readme_distinguishes_baremetal_and_containerized_paths")


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
    test_docker_agent_supervisor_replaces_user_systemd_units()
    test_docker_entrypoint_generates_fresh_secrets()
    test_docker_health_script_checks_container_runtime()
    test_dockerignore_excludes_sensitive_and_generated_context()
    test_readme_keeps_canonical_host_layout_root()
    test_readme_distinguishes_baremetal_and_containerized_paths()
    test_docker_compose_config_validates_when_docker_is_available()
    print("PASS all 10 Almanac Docker regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
