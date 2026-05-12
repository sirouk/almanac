#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shlex
import sqlite3
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


def extract(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def test_dockerfile_installs_pinned_runtime_assets() -> None:
    body = read("Dockerfile")
    expect("FROM node:22-bookworm-slim" in body, body)
    expect("config/pins.json" in body, body)
    expect("@tobilu/qmd@${qmd_version}" in body, body)
    expect("hermes-agent" in body and "hermes-venv" in body, body)
    expect("stripe" in body, body)
    expect("[ -f /home/arclink/arclink/web/package-lock.json ]" in body, body)
    expect("cd /home/arclink/arclink/web" in body and "npm run build" in body, body)
    expect("hermes-agent-src/ui-tui" in body and "npm run build" in body, body)
    expect("ARCLINK_API_INTERNAL_URL=http://control-api:8900" in body, body)
    expect("poppler-utils" in body and "inotify-tools" in body and "sqlite3" in body, body)
    expect("download.docker.com/linux/debian" in body and "docker-ce-cli" in body, body)
    expect("docker-compose-plugin" in body, body)
    expect("iproute2" in body, body)
    expect("ARG ARCLINK_UID=1000" in body and "ARG ARCLINK_GID=1000" in body, body)
    expect('getent passwd "$ARCLINK_UID"' in body and 'chown -R "$ARCLINK_UID:$ARCLINK_GID"' in body, body)
    expect("USER arclink" in body, body)
    print("PASS test_dockerfile_installs_pinned_runtime_assets")


def test_compose_defines_full_stack_services() -> None:
    body = read("compose.yaml")
    expect("arclink-app:" in body and "dockerfile: Dockerfile" in body, body)
    expect("ARCLINK_UID: ${ARCLINK_DOCKER_UID:-1000}" in body, body)
    expect("ARCLINK_GID: ${ARCLINK_DOCKER_GID:-1000}" in body, body)
    expect('profiles: ["build"]' in body, body)
    expect("ARCLINK_BACKEND_ALLOWED_CIDRS:" in body, body)
    expect("ARCLINK_BASE_DOMAIN:" in body and "ARCLINK_PRIMARY_PROVIDER:" in body, body)
    expect("ARCLINK_INGRESS_MODE:" in body and "ARCLINK_TAILSCALE_DNS_NAME:" in body, body)
    expect("ARCLINK_CONTROL_PROVISIONER_ENABLED:" in body and "ARCLINK_EXECUTOR_ADAPTER:" in body, body)
    expect("STRIPE_WEBHOOK_SECRET:" in body and "CLOUDFLARE_API_TOKEN:" in body and "CHUTES_API_KEY:" in body, body)
    expect("ARCLINK_SQLITE_JOURNAL_MODE: ${ARCLINK_SQLITE_JOURNAL_MODE:-DELETE}" in body, body)
    expect("QMD_MCP_HOST_PORT:" in body, body)
    expect("QMD_MCP_CONTAINER_PORT:" in body, body)
    expect("QMD_MCP_LOOPBACK_PORT:" in body, body)
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
        "control-action-worker:",
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
    expect("python/arclink_action_worker.py" in body and "control-action-worker" in body, body)
    expect(
        '["./bin/docker-job-loop.sh", "notification-delivery", "1", "./bin/arclink-notification-delivery.sh"]'
        in body,
        "public-channel agent turns should stay on the Docker-capable delivery worker with a low-latency poll",
    )
    expect("./arclink-priv/secrets/ssh:/root/.ssh" not in body, body)
    expect("./arclink-priv/secrets/ssh:/home/arclink/.ssh" in body, body)
    expect("ARCLINK_LOCAL_FLEET_SSH_USER: ${ARCLINK_LOCAL_FLEET_SSH_USER:-arclink}" in body, body)
    expect(
        "ARCLINK_FLEET_SSH_KEY_PATH: ${ARCLINK_FLEET_SSH_KEY_PATH:-/home/arclink/arclink/arclink-priv/secrets/ssh/id_ed25519}"
        in body,
        body,
    )
    expect("${ARCLINK_STATE_ROOT_BASE:-/arcdata/deployments}:${ARCLINK_STATE_ROOT_BASE:-/arcdata/deployments}" in body, body)
    expect("ARCLINK_AGENT_SERVICE_MANAGER: docker-supervisor" in body, body)
    expect("ARCLINK_DOCKER_NETWORK: ${ARCLINK_DOCKER_NETWORK:-arclink_default}" in body, body)
    expect("ARCLINK_DOCKER_SOCKET_GID: ${ARCLINK_DOCKER_SOCKET_GID:-0}" in body, body)
    expect("Intentional trusted-host boundary" in body, body)
    expect(
        "- .:/home/arclink/arclink" in body
        and "${ARCLINK_DOCKER_HOST_REPO_DIR:-.}:${ARCLINK_DOCKER_HOST_REPO_DIR:-/home/arclink/arclink}" in body,
        "agent-supervisor and curator-refresh must mount the live checkout for Docker operator actions",
    )
    socket_mounts = re.findall(r"^\s+- /var/run/docker\.sock:/var/run/docker\.sock(?::ro)?\s*$", body, re.MULTILINE)
    expect(len(socket_mounts) == 6, f"unexpected Docker socket mount count: {socket_mounts}\n{body}")
    expect(body.count("/var/run/docker.sock:/var/run/docker.sock:ro") == 1, body)
    expect(body.count("/var/run/docker.sock:/var/run/docker.sock\n") == 5, body)
    expect(body.count("group_add:\n      - ${ARCLINK_DOCKER_SOCKET_GID:-0}") == 5, body)
    for socket_service in ("control-provisioner", "control-action-worker", "agent-supervisor", "notification-delivery", "curator-refresh"):
        block = extract(body, f"  {socket_service}:", "\n\n")
        expect("group_add:" in block, f"{socket_service} missing socket gid group_add\n{block}")
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
    expect("repair_docker_app_named_volumes()" in body and "arclink_arclink-qmd" in body, body)
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
    expect(
        'ensure_env_file_value ARCLINK_DOCKER_SOCKET_GID "$(stat -c %g /var/run/docker.sock 2>/dev/null || printf ' in body,
        body,
    )
    expect('ensure_env_file_value ARCLINK_DOCKER_UID "$(docker_default_runtime_uid)"' in body, body)
    expect("ensure_docker_app_bind_permissions()" in body, body)
    expect('-path "$REPO_DIR/arclink-priv/state/nextcloud" -prune' in body, body)
    expect("qmd-mcp" in body and "qmd --version" in body, body)
    expect('pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' in body, body)
    expect("health-watch" in body and "compose exec -T health-watch ./bin/docker-health.sh" in body, body)
    expect("docker_reconcile()" in body and "./bin/arclink-ctl org-profile apply --yes" in body, body)
    expect("docker_publish_tailnet_deployment_apps()" in body and "tailscale serve --bg --yes --https" in body, body)
    expect("docker_refresh_deployment_service_health()" in body and "docker compose" in body and "upsert_arclink_service_health" in body, body)
    expect("docker_refresh_deployment_managed_plugins()" in body, body)
    expect("sync-dashboard-user-passwords.py" in body and "control-provisioner" in body, body)
    expect("managed-context-install" in body and "--force-recreate hermes-dashboard" in body, body)
    expect("--force-recreate dashboard" in body, body)
    expect("--force-recreate nextcloud" in body, body)
    expect("--force-recreate memory-synth" in body, body)
    expect("Refreshed deployment-managed Hermes plugins" in body, body)
    expect("docker_repair_deployment_dashboard_plugin_mounts()" in body, body)
    expect("run-hermes-dashboard-proxy.sh" in body, body)
    expect("DRIVE_ROOT" in body and "CODE_WORKSPACE_ROOT" in body, body)
    expect("TERMINAL_ALLOW_ROOT" in body and "HERMES_TUI_DIR" in body, body)
    expect('"VAULT_DIR": "/srv/vault"' in body and '"/srv/vault/Agents_KB/hermes-agent-docs"' in body, body)
    expect('services.pop("code-server", None)' in body, body)
    expect('compose_secrets.pop("code_server_password", None)' in body, body)
    expect('env.pop("CODE_SERVER_PASSWORD_REF", None)' in body, body)
    expect('label=com.docker.compose.service=code-server' in body and "docker rm -f" in body, body)
    expect("Repaired Hermes dashboard plugin mounts" in body, body)
    expect("ARCLINK_TAILNET_SERVICE_PORT_BASE" in body, body)
    expect("wait_for_docker_agent_reconcile()" in body and "arclink-vault-reconciler.json" in body, body)
    expect("docker_record_release_state()" in body and '"deployed_from": "docker-checkout"' in body, body)
    expect('"revision_mode": revision_mode' in body, body)
    expect('"checkout_commit": checkout_commit' in body, body)
    expect('"baked_image_commit": baked_commit' in body, body)
    expect('"image_name": image_name' in body and '"image_created": image_created' in body, body)
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


def test_deployment_hermes_home_installer_seeds_runtime_knowledge() -> None:
    body = read("bin/install-deployment-hermes-home.sh")
    expect("sync-hermes-bundled-skills.sh" in body, body)
    expect("install-arclink-skills.sh" in body, body)
    expect("install-arclink-plugins.sh" in body, body)
    expect("migrate-hermes-config.sh" in body, body)
    expect("reconcile-vault-layout.py" in body and "--hermes-skills-dir" in body, body)
    expect("sync-hermes-docs-into-vault.sh" in body, body)
    expect("ARCLINK_CONFIG_FILE=/dev/null" in body, body)
    expect("ARCLINK_ALLOW_SCAFFOLD_DEFAULTS=1" in body, body)
    expect('ARCLINK_HERMES_DOCS_VAULT_DIR="$docs_vault_dir"' in body, body)
    expect("Hermes docs sync failed; continuing" in body, body)
    print("PASS test_deployment_hermes_home_installer_seeds_runtime_knowledge")


def test_docker_tailnet_publish_failure_withholds_app_urls() -> None:
    body = read("bin/arclink-docker.sh")
    snippet = extract(body, "docker_publish_tailnet_deployment_apps() {", "docker_configure_deployment_nextcloud_overwrite() {")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        state = repo / "arclink-priv" / "state"
        state.mkdir(parents=True)
        (repo / "python").symlink_to(REPO / "python")
        db_path = state / "arclink-control.sqlite3"
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE arclink_deployments (
                  deployment_id TEXT PRIMARY KEY,
                  prefix TEXT,
                  base_domain TEXT,
                  status TEXT,
                  metadata_json TEXT,
                  created_at TEXT
                )
                """
            )
            conn.execute(
                """
                INSERT INTO arclink_deployments (
                  deployment_id, prefix, base_domain, status, metadata_json, created_at
                ) VALUES ('dep_1', 'amber-vault-1a2b', 'worker.example.ts.net', 'active', '{}', '2026-01-01T00:00:00+00:00')
                """
            )
            conn.commit()
        bin_dir = root / "bin"
        bin_dir.mkdir()
        log_path = root / "tailscale.log"
        (bin_dir / "tailscale").write_text(
            "#!/usr/bin/env bash\n"
            f"printf '%s\\n' \"$*\" >> {shlex.quote(str(log_path))}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        (bin_dir / "tailscale").chmod(0o755)
        script = f"""
set -euo pipefail
{snippet}
REPO_DIR={shlex.quote(str(repo))}
configured_or_default() {{
  case "$1" in
    ARCLINK_INGRESS_MODE) printf '%s\\n' tailscale ;;
    ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY) printf '%s\\n' path ;;
    ARCLINK_TAILSCALE_DNS_NAME) printf '%s\\n' worker.example.ts.net ;;
    ARCLINK_WEB_PORT) printf '%s\\n' 3000 ;;
    ARCLINK_TAILNET_SERVICE_PORT_BASE) printf '%s\\n' 8443 ;;
    *) printf '%s\\n' "${{2:-}}" ;;
  esac
}}
docker_configure_deployment_nextcloud_overwrite() {{
  printf 'called\\n' >> {shlex.quote(str(root / "nextcloud-called"))}
}}
docker_publish_tailnet_deployment_apps
"""
        result = subprocess.run(
            ["bash", "-lc", script],
            cwd=REPO,
            env={**os.environ, "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"},
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode == 0, f"tailnet publish probe failed: stdout={result.stdout!r} stderr={result.stderr!r}")
        with sqlite3.connect(db_path) as conn:
            metadata = json.loads(conn.execute("SELECT metadata_json FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone()[0])
        expect(metadata["tailnet_app_publication"]["status"] == "published", str(metadata))
        expect(metadata["tailnet_app_publication"]["failed_roles"] == [], str(metadata))
        expect(metadata["access_urls"]["hermes"] == "https://worker.example.ts.net/u/amber-vault-1a2b/hermes", str(metadata))
        expect(metadata["access_urls"]["files"] == "https://worker.example.ts.net/u/amber-vault-1a2b/drive", str(metadata))
        expect(metadata["access_urls"]["code"] == "https://worker.example.ts.net/u/amber-vault-1a2b/code", str(metadata))
        expect(":8443" not in "\n".join(metadata["access_urls"].values()), str(metadata))
        expect(metadata["tailnet_service_ports"] == {"hermes": 8443}, str(metadata))
        expect(not (root / "nextcloud-called").exists(), "Nextcloud overwrite must not be configured for dashboard-native Drive")
        print("PASS test_docker_tailnet_publish_uses_dashboard_native_plugin_urls")


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
                    "ARCLINK_UPSTREAM_BRANCH=arclink",
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
        expect("branch=arclink" in captured, captured)
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
    expect("def ensure_container_user" in supervisor, supervisor)
    expect('"gateway", "run", "--replace"' in supervisor, supervisor)
    expect("ensure_dashboard_backend_network" in supervisor, supervisor)
    expect('"docker", "network", "create", "--internal"' in supervisor, supervisor)
    expect('"docker", "network", "connect"' in supervisor, supervisor)
    expect("startswith(container_name)" in supervisor, supervisor)
    expect('"--host",\n                        dashboard_backend_host' in supervisor, supervisor)
    expect('"--target",\n                    f"http://{dashboard_backend_host}:{dashboard_backend_port}"' in supervisor, supervisor)
    expect('"--host",\n                        "0.0.0.0"' not in supervisor, supervisor)
    expect("arclink_dashboard_auth_proxy.py" in supervisor, supervisor)
    expect('"docker",\n                    "run"' in supervisor, supervisor)
    expect('"--network"' in supervisor and "ARCLINK_DOCKER_NETWORK" in supervisor, supervisor)
    expect('"ARCLINK_DOCKER_CONTAINER_NAME"' in supervisor, supervisor)
    expect("run-agent-code-server.sh" not in supervisor, supervisor)
    expect('"cron", "tick"' in supervisor, supervisor)
    expect('refresh_seconds = int(os.environ.get("ARCLINK_DOCKER_AGENT_REFRESH_SECONDS", "14400"))' in supervisor, supervisor)
    expect('cron_seconds = int(os.environ.get("ARCLINK_DOCKER_AGENT_CRON_SECONDS", "60"))' in supervisor, supervisor)
    expect('commands = [[str(cfg.repo_dir / "bin" / "hermes-shell.sh"), "cron", "tick"]]' in supervisor, supervisor)
    expect('commands = [[str(cfg.repo_dir / "bin" / "user-agent-refresh.sh")]]' in supervisor, supervisor)
    expect("ensure_agent_mcp_auth" in supervisor and "ensure_agent_mcp_bootstrap_token" in supervisor, supervisor)
    expect('"docker-agent-supervisor"' in supervisor, supervisor)
    expect("run_headless_identity_setup" in supervisor and "arclink_headless_hermes_setup.py" in supervisor, supervisor)
    expect('"--identity-only"' in supervisor and "agent_label" in supervisor and "user_label" in supervisor, supervisor)
    expect('ARCLINK_AGENT_SERVICE_MANAGER:-systemd' in installer, installer)
    expect("def _ensure_docker_user_ready" in provisioner, provisioner)
    expect('"ARCLINK_AGENT_SERVICE_MANAGER": "docker-supervisor"' in provisioner, provisioner)
    expect("arclink_dashboard_auth_proxy.py" in supervisor and "arclink-web-access.json" in supervisor, supervisor)
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
    expect(
        "rsync -a --no-owner --no-group --ignore-existing" in body,
        "rootless Docker entrypoint rsync must not preserve owner/group on bind mounts",
    )
    expect('[[ -d "$live_data" && ! -w "$live_data" ]]' in body, body)
    expect('[[ ! -w "$(dirname "$nextcloud_config")" ]]' in body, body)
    print("PASS test_docker_entrypoint_generates_fresh_secrets")


def test_docker_health_script_checks_container_runtime() -> None:
    body = read("bin/docker-health.sh")
    expect("http://arclink-mcp:8282/health" in body, body)
    expect("http://notion-webhook:8283/health" in body, body)
    expect("http://nextcloud/status.php" in body, body)
    expect("Host: $host_header" in body, body)
    expect('check_optional_tcp_with_fallback "qmd-mcp" "${QMD_MCP_CONTAINER_PORT:-8181}"' in body, body)
    expect('"host.docker.internal" "${QMD_MCP_HOST_PORT:-${QMD_MCP_PORT:-8181}}"' in body, body)
    qmd_daemon = read("bin/qmd-daemon.sh")
    expect("QMD MCP TCP forwarder listening" in qmd_daemon, qmd_daemon)
    expect('QMD_PROXY_BIND_HOST:-127.0.0.1' in qmd_daemon, qmd_daemon)
    expect('QMD_PROXY_BIND_HOST: ${QMD_PROXY_BIND_HOST:-0.0.0.0}' in read("compose.yaml"), read("compose.yaml"))
    expect('"postgres" "5432"' in body, body)
    expect('"redis" "6379"' in body, body)
    expect("check_docker_agent_mcp_auth" in body, body)
    expect('"control-ingress" "8080" "Traefik ingress (HTTP)"' in body, body)
    expect("check_control_ingress_https()" in body, body)
    expect('ARCLINK_INGRESS_MODE:-domain' in body, body)
    expect('ARCLINK_TAILSCALE_CONTROL_URL:-' in body, body)
    expect("configured Tailscale/Funnel route" in body, body)
    expect('status in ("warn", "warning", "disabled")' in body, body)
    for job in (
        "control-provisioner",
        "control-action-worker",
        "ssot-batcher",
        "notification-delivery",
        "health-watch",
        "curator-refresh",
        "qmd-refresh",
        "pdf-ingest",
        "memory-synth",
        "hermes-docs-sync",
    ):
        expect(job in body, f"docker health must inspect recurring job {job}\n{body}")
    expect('data.get("job_name") or data.get("job")' in body, body)
    expect('data.get("exit_code") if "exit_code" in data else data.get("returncode", 0)' in body, body)
    expect('eval "$(' not in body, "docker health must not eval JSON status fields")
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
        "arclink-priv/**",
        "node_modules",
        "**/node_modules",
        ".next",
        "**/.next",
        "*.sqlite3",
        "*.sqlite3-shm",
        "*.sqlite3-wal",
    ):
        expect(pattern in body, f"missing .dockerignore pattern {pattern}\n{body}")
    print("PASS test_dockerignore_excludes_sensitive_and_generated_context")


def test_docker_docs_cover_socket_and_private_state_boundaries() -> None:
    body = read("docs/docker.md")
    for service in ("control-ingress", "control-provisioner", "control-action-worker", "agent-supervisor", "notification-delivery", "curator-refresh"):
        expect(f"| `{service}` |" in body, f"docs/docker.md must document socket boundary for {service}\n{body}")
    expect("writeable Docker socket access has host-root-equivalent capabilities" in body, body)
    expect("control-ingress` has read-only socket access" in body, body)
    expect("ARCLINK_DOCKER_SOCKET_GID" in body and "shared ArcLink app image as the `arclink` Unix user" in body, body)
    expect("recurring" in body and "job status files" in body, body)
    expect("health-watch` service does not mount the Docker socket" in body, body)
    print("PASS test_docker_docs_cover_socket_and_private_state_boundaries")


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
    expect("u-{prefix}.{base_domain}" in ingress and "hermes-{prefix}.{base_domain}" in ingress, ingress)
    expect("https://{tailscale_dns_name}/u/{prefix}/drive" in ingress, ingress)
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
    test_deployment_hermes_home_installer_seeds_runtime_knowledge()
    test_docker_tailnet_publish_failure_withholds_app_urls()
    test_docker_component_upgrade_apply_loads_upstream_env_from_docker_config()
    test_docker_agent_supervisor_replaces_user_systemd_units()
    test_docker_entrypoint_generates_fresh_secrets()
    test_docker_health_script_checks_container_runtime()
    test_dockerignore_excludes_sensitive_and_generated_context()
    test_docker_docs_cover_socket_and_private_state_boundaries()
    test_readme_keeps_canonical_host_layout_root()
    test_readme_distinguishes_control_shared_host_and_docker_paths()
    test_sovereign_ingress_docs_cover_domain_and_tailscale_modes()
    test_docker_compose_config_validates_when_docker_is_available()
    print("PASS all 15 ArcLink Docker regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
