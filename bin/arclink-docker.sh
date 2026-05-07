#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="${ARCLINK_DOCKER_COMPOSE_FILE:-$REPO_DIR/compose.yaml}"
DOCKER_ENV_FILE="${ARCLINK_DOCKER_ENV_FILE:-$REPO_DIR/arclink-priv/config/docker.env}"
DOCKER_REQUIRED_STATE_DIRS=(
  "$REPO_DIR/arclink-priv/config"
  "$REPO_DIR/arclink-priv/vault"
  "$REPO_DIR/arclink-priv/state"
  "$REPO_DIR/arclink-priv/state/nextcloud"
  "$REPO_DIR/arclink-priv/state/pdf-ingest/markdown"
  "$REPO_DIR/arclink-priv/state/notion-index/markdown"
  "$REPO_DIR/arclink-priv/secrets/ssh"
)
DOCKER_REQUIRED_RUNNING_SERVICES=(
  postgres
  redis
  nextcloud
  arclink-mcp
  qmd-mcp
  notion-webhook
  control-api
  control-web
  control-provisioner
  vault-watch
  agent-supervisor
  health-watch
)
DOCKER_PORT_MANIFEST="$REPO_DIR/arclink-priv/state/docker/ports.json"

usage() {
  cat <<'EOF'
Usage: bin/arclink-docker.sh <command> [args]

Commands:
  bootstrap   Seed Docker state/config directories under arclink-priv
  write-config
              Alias for bootstrap, matching deploy.sh's config-only lane
  config      Validate and print the Docker Compose configuration
  build       Build ArcLink Docker images
  up          Start the Docker stack
  reconcile   Apply private org profile and refresh Docker agent supervisor state
  down        Stop the Docker stack
  ps          Show Compose service state
  ports       Show assigned Docker host ports
  logs        Follow or print Compose logs
  health      Validate Compose config, state directories, control API/web, and running services
  provision-once
              Run one Sovereign Control Node provisioner batch now
  record-release
              Record the current Docker checkout as the deployed ArcLink release
  live-smoke  Run the live agent MCP tool smoke inside the Docker supervisor
  notion-ssot
              Run the shared Notion SSOT setup against Docker config
  notion-migrate
              Guide migration from one Notion workspace to another
  notion-transfer
              Back up or restore a Notion page subtree with token files
  enrollment-status
              Show Docker enrollment/provisioning state
  enrollment-trace
              Trace a Docker enrollment by --unix-user, --session-id, or --request-id
  enrollment-align
              Reconcile Docker enrollment/provisioning and agent supervisor state
  enrollment-reset
              Reset one Docker enrollment; set ENROLLMENT_RESET_UNIX_USER or pass --unix-user
  curator-setup
              Rebuild Curator runtime assets and start Curator-profile services
  rotate-nextcloud-secrets
              Rotate Docker Nextcloud admin and Postgres credentials
  agent-payload
              Print the Docker-aware agent install payload
  pins-show | pins-check | pin-upgrade-notify
              Inspect pinned runtime components for the Docker checkout
  <component>-upgrade-check
              Check a pinned component, for example qmd-upgrade-check
  <component>-upgrade
              Bump a pinned component and re-apply with deploy.sh docker upgrade
  teardown    Stop the stack and remove Compose volumes
  remove      Alias for teardown

Set COMPOSE_PROFILES=curator,quarto,backup to include optional profiles.
EOF
}

compose() {
  local -a env_args=()
  if [[ -f "$DOCKER_ENV_FILE" ]]; then
    env_args=(--env-file "$DOCKER_ENV_FILE")
  fi

  docker compose "${env_args[@]}" -f "$COMPOSE_FILE" "$@"
}

compose_service_running() {
  local service="$1"
  compose ps --status running --services 2>/dev/null | grep -Fxq "$service"
}

compose_exec_maybe_tty() {
  local service="$1"
  shift
  if [[ -t 0 && -t 1 ]]; then
    compose exec "$service" "$@"
  else
    compose exec -T "$service" "$@"
  fi
}

compose_run_maybe_tty() {
  local service="$1"
  shift
  if [[ -t 0 && -t 1 ]]; then
    compose run --rm --no-deps "$service" "$@"
  else
    compose run -T --rm --no-deps "$service" "$@"
  fi
}

compose_service_command() {
  local service="$1"
  shift
  prepare_compose
  if compose_service_running "$service"; then
    compose exec -T "$service" "$@"
  else
    compose run -T --rm --no-deps "$service" "$@"
  fi
}

compose_service_interactive() {
  local service="$1"
  shift
  prepare_compose
  if compose_service_running "$service"; then
    compose_exec_maybe_tty "$service" "$@"
  else
    compose_run_maybe_tty "$service" "$@"
  fi
}

compose_app_command() {
  compose_service_command arclink-mcp "$@"
}

compose_app_interactive() {
  compose_service_interactive arclink-mcp "$@"
}

compose_supervisor_command() {
  compose_service_command agent-supervisor "$@"
}

require_docker_compose() {
  if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    echo "docker compose is required for ArcLink Docker mode." >&2
    return 1
  fi
}

prepare_compose() {
  require_docker_compose
  bootstrap
  reserve_docker_ports
}

bootstrap() {
  ARCLINK_REPO_DIR="$REPO_DIR" \
  ARCLINK_PRIV_DIR="$REPO_DIR/arclink-priv" \
  ARCLINK_PRIV_CONFIG_DIR="$REPO_DIR/arclink-priv/config" \
  ARCLINK_CONFIG_FILE="$DOCKER_ENV_FILE" \
  ARCLINK_DOCKER_CONFIG_REPO_DIR="/home/arclink/arclink" \
  ARCLINK_DOCKER_CONFIG_PRIV_DIR="/home/arclink/arclink/arclink-priv" \
  ARCLINK_DOCKER_CONFIG_RUNTIME_DIR="/opt/arclink/runtime" \
  ARCLINK_DOCKER_HOST_REPO_DIR="$REPO_DIR" \
  ARCLINK_DOCKER_HOST_PRIV_DIR="$REPO_DIR/arclink-priv" \
  ARCLINK_DOCKER_REWRITE_CONFIG="${ARCLINK_DOCKER_REWRITE_CONFIG:-0}" \
  XDG_CONFIG_HOME="$REPO_DIR/arclink-priv/state/qmd/config" \
  XDG_CACHE_HOME="$REPO_DIR/arclink-priv/state/qmd/cache" \
    "$SCRIPT_DIR/docker-entrypoint.sh" true
  set_env_file_value ARCLINK_DOCKER_HOST_REPO_DIR "$REPO_DIR"
  set_env_file_value ARCLINK_DOCKER_HOST_PRIV_DIR "$REPO_DIR/arclink-priv"
  ensure_env_file_value ARCLINK_PRODUCT_NAME "ArcLink"
  ensure_env_file_value ARCLINK_BASE_DOMAIN "arclink.online"
  ensure_env_file_value ARCLINK_INGRESS_MODE "domain"
  ensure_env_file_value ARCLINK_TAILSCALE_DNS_NAME ""
  ensure_env_file_value ARCLINK_TAILSCALE_CONTROL_URL ""
  ensure_env_file_value ARCLINK_TAILSCALE_HTTPS_PORT "443"
  ensure_env_file_value ARCLINK_TAILSCALE_NOTION_PATH "/notion/webhook"
  ensure_env_file_value ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY "path"
  ensure_env_file_value ARCLINK_TAILNET_SERVICE_PORT_BASE "8443"
  ensure_env_file_value ARCLINK_PRIMARY_PROVIDER "chutes"
  ensure_env_file_value ARCLINK_API_HOST "0.0.0.0"
  ensure_env_file_value ARCLINK_CORS_ORIGIN ""
  ensure_env_file_value ARCLINK_COOKIE_DOMAIN ""
  ensure_env_file_value ARCLINK_DEFAULT_PRICE_ID "price_arclink_founders"
  ensure_env_file_value ARCLINK_FOUNDERS_PRICE_ID "price_arclink_founders"
  ensure_env_file_value ARCLINK_SOVEREIGN_PRICE_ID "price_arclink_sovereign"
  ensure_env_file_value ARCLINK_SCALE_PRICE_ID "price_arclink_scale"
  ensure_env_file_value ARCLINK_FIRST_AGENT_PRICE_ID "price_arclink_founders"
  ensure_env_file_value ARCLINK_SOVEREIGN_AGENT_EXPANSION_PRICE_ID "price_arclink_sovereign_agent_expansion"
  ensure_env_file_value ARCLINK_SCALE_AGENT_EXPANSION_PRICE_ID "price_arclink_scale_agent_expansion"
  ensure_env_file_value ARCLINK_ADDITIONAL_AGENT_PRICE_ID "price_arclink_sovereign_agent_expansion"
  ensure_env_file_value ARCLINK_FOUNDERS_MONTHLY_CENTS "14900"
  ensure_env_file_value ARCLINK_SOVEREIGN_MONTHLY_CENTS "19900"
  ensure_env_file_value ARCLINK_SCALE_MONTHLY_CENTS "27500"
  ensure_env_file_value ARCLINK_FIRST_AGENT_MONTHLY_CENTS "14900"
  ensure_env_file_value ARCLINK_SOVEREIGN_AGENT_EXPANSION_MONTHLY_CENTS "9900"
  ensure_env_file_value ARCLINK_SCALE_AGENT_EXPANSION_MONTHLY_CENTS "7900"
  ensure_env_file_value ARCLINK_ADDITIONAL_AGENT_MONTHLY_CENTS "9900"
  ensure_env_file_value ARCLINK_CONTROL_PROVISIONER_ENABLED "0"
  ensure_env_file_value ARCLINK_CONTROL_PROVISIONER_INTERVAL_SECONDS "30"
  ensure_env_file_value ARCLINK_CONTROL_PROVISIONER_BATCH_SIZE "5"
  ensure_env_file_value ARCLINK_SOVEREIGN_PROVISION_MAX_ATTEMPTS "5"
  ensure_env_file_value ARCLINK_EXECUTOR_ADAPTER "disabled"
  ensure_env_file_value ARCLINK_EDGE_TARGET "edge.arclink.online"
  ensure_env_file_value ARCLINK_STATE_ROOT_BASE "/arcdata/deployments"
  ensure_env_file_value ARCLINK_SECRET_STORE_DIR "$REPO_DIR/arclink-priv/state/sovereign-secrets"
  ensure_env_file_value ARCLINK_REGISTER_LOCAL_FLEET_HOST "0"
  ensure_env_file_value ARCLINK_LOCAL_FLEET_HOSTNAME ""
  ensure_env_file_value ARCLINK_LOCAL_FLEET_SSH_HOST ""
  ensure_env_file_value ARCLINK_LOCAL_FLEET_SSH_USER "arclink"
  ensure_env_file_value ARCLINK_LOCAL_FLEET_REGION ""
  ensure_env_file_value ARCLINK_LOCAL_FLEET_CAPACITY_SLOTS "4"
  ensure_env_file_value ARCLINK_FLEET_SSH_KEY_PATH "/home/arclink/arclink/arclink-priv/secrets/ssh/id_ed25519"
  ensure_env_file_value ARCLINK_FLEET_SSH_KNOWN_HOSTS_FILE "/home/arclink/arclink/arclink-priv/secrets/ssh/known_hosts"
  reserve_docker_ports
}

env_file_value() {
  local key="$1"
  [[ -f "$DOCKER_ENV_FILE" ]] || return 1
  awk -v key="$key" '
    index($0, key "=") == 1 {
      value = substr($0, length(key) + 2)
      gsub(/^"|"$/, "", value)
      print value
      exit
    }
  ' "$DOCKER_ENV_FILE"
}

set_env_file_value() {
  local key="$1"
  local value="$2"
  local tmp_file=""

  mkdir -p "$(dirname "$DOCKER_ENV_FILE")"
  tmp_file="$(mktemp "$DOCKER_ENV_FILE.XXXXXX")"
  if [[ -f "$DOCKER_ENV_FILE" ]]; then
    awk -v key="$key" -v value="$value" '
      BEGIN { replaced = 0 }
      index($0, key "=") == 1 {
        print key "=" value
        replaced = 1
        next
      }
      { print }
      END {
        if (!replaced) {
          print key "=" value
        }
      }
    ' "$DOCKER_ENV_FILE" >"$tmp_file"
  else
    printf '%s=%s\n' "$key" "$value" >"$tmp_file"
  fi
  chmod 600 "$tmp_file"
  mv "$tmp_file" "$DOCKER_ENV_FILE"
}

ensure_env_file_value() {
  local key="$1"
  local default_value="$2"
  local existing=""

  existing="$(env_file_value "$key" 2>/dev/null || true)"
  if [[ -z "$existing" ]]; then
    set_env_file_value "$key" "$default_value"
  fi
}

configured_or_default() {
  local key="$1"
  local default_value="$2"
  local env_value="${!key-}"
  local file_value=""

  if [[ -n "$env_value" ]]; then
    printf '%s\n' "$env_value"
    return 0
  fi
  file_value="$(env_file_value "$key" 2>/dev/null || true)"
  printf '%s\n' "${file_value:-$default_value}"
}

port_is_integer() {
  [[ "${1:-}" =~ ^[0-9]+$ ]] && [[ "$1" -gt 0 ]] && [[ "$1" -lt 65536 ]]
}

host_port_bindable() {
  local port="$1"
  python3 - "$port" <<'PY' >/dev/null 2>&1
import socket
import sys

port = int(sys.argv[1])
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    sock.bind(("127.0.0.1", port))
finally:
    sock.close()
PY
}

compose_service_owns_port() {
  local service="$1"
  local internal_port="$2"
  local host_port="$3"
  local mapping=""

  if ! command -v docker >/dev/null 2>&1; then
    return 1
  fi
  mapping="$(compose port "$service" "$internal_port" 2>/dev/null | head -n 1 || true)"
  [[ "$mapping" == *":$host_port" ]]
}

host_port_available_for_service() {
  local port="$1"
  local service="$2"
  local internal_port="$3"

  port_is_integer "$port" || return 1
  if host_port_bindable "$port"; then
    return 0
  fi
  compose_service_owns_port "$service" "$internal_port" "$port"
}

docker_port_set_available() {
  local qmd_port="$1"
  local mcp_port="$2"
  local webhook_port="$3"
  local nextcloud_port="$4"
  local api_port="$5"
  local web_port="$6"

  local -a ports=("$qmd_port" "$mcp_port" "$webhook_port" "$nextcloud_port" "$api_port" "$web_port")
  local i=0 j=0
  for i in "${!ports[@]}"; do
    for j in "${!ports[@]}"; do
      if [[ "$i" != "$j" && "${ports[$i]}" == "${ports[$j]}" ]]; then
        return 1
      fi
    done
  done

  host_port_available_for_service "$qmd_port" qmd-mcp 8181 &&
    host_port_available_for_service "$mcp_port" arclink-mcp 8282 &&
    host_port_available_for_service "$webhook_port" notion-webhook 8283 &&
    host_port_available_for_service "$nextcloud_port" nextcloud 80 &&
    host_port_available_for_service "$api_port" control-api 8900 &&
    host_port_available_for_service "$web_port" control-ingress 8080
}

persist_docker_ports() {
  local qmd_port="$1"
  local mcp_port="$2"
  local webhook_port="$3"
  local nextcloud_port="$4"
  local api_port="$5"
  local web_port="$6"

  set_env_file_value QMD_MCP_PORT "$qmd_port"
  set_env_file_value ARCLINK_MCP_PORT "$mcp_port"
  set_env_file_value ARCLINK_NOTION_WEBHOOK_PORT "$webhook_port"
  set_env_file_value NEXTCLOUD_PORT "$nextcloud_port"
  set_env_file_value ARCLINK_API_PORT "$api_port"
  set_env_file_value ARCLINK_WEB_PORT "$web_port"
  mkdir -p "$(dirname "$DOCKER_PORT_MANIFEST")"
  python3 - "$DOCKER_PORT_MANIFEST" "$qmd_port" "$mcp_port" "$webhook_port" "$nextcloud_port" "$api_port" "$web_port" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = {
    "qmd_mcp_port": int(sys.argv[2]),
    "arclink_mcp_port": int(sys.argv[3]),
    "notion_webhook_port": int(sys.argv[4]),
    "nextcloud_port": int(sys.argv[5]),
    "control_api_port": int(sys.argv[6]),
    "control_web_port": int(sys.argv[7]),
}
path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

reserve_docker_ports() {
  if [[ "${ARCLINK_DOCKER_AUTO_PORTS:-1}" == "0" ]]; then
    return 0
  fi

  local qmd_port=""
  local mcp_port=""
  local webhook_port=""
  local nextcloud_port=""
  local api_port=""
  local web_port=""
  local offset=0

  qmd_port="$(configured_or_default QMD_MCP_PORT 8181)"
  mcp_port="$(configured_or_default ARCLINK_MCP_PORT 8282)"
  webhook_port="$(configured_or_default ARCLINK_NOTION_WEBHOOK_PORT 8283)"
  nextcloud_port="$(configured_or_default NEXTCLOUD_PORT 18080)"
  api_port="$(configured_or_default ARCLINK_API_PORT 8900)"
  web_port="$(configured_or_default ARCLINK_WEB_PORT 3000)"

  if docker_port_set_available "$qmd_port" "$mcp_port" "$webhook_port" "$nextcloud_port" "$api_port" "$web_port"; then
    persist_docker_ports "$qmd_port" "$mcp_port" "$webhook_port" "$nextcloud_port" "$api_port" "$web_port"
    return 0
  fi

  for offset in $(seq 0 199); do
    qmd_port=$((18181 + offset))
    mcp_port=$((18282 + offset))
    webhook_port=$((18283 + offset))
    nextcloud_port=$((28080 + offset))
    api_port=$((18900 + offset))
    web_port=$((13000 + offset))
    if docker_port_set_available "$qmd_port" "$mcp_port" "$webhook_port" "$nextcloud_port" "$api_port" "$web_port"; then
      persist_docker_ports "$qmd_port" "$mcp_port" "$webhook_port" "$nextcloud_port" "$api_port" "$web_port"
      echo "Docker ports assigned: qmd=$qmd_port arclink-mcp=$mcp_port notion-webhook=$webhook_port nextcloud=$nextcloud_port control-api=$api_port control-web=$web_port"
      return 0
    fi
  done

  echo "Could not find an available ArcLink Docker port block." >&2
  return 1
}

require_running_service() {
  local running="$1"
  local service="$2"

  if grep -Fxq "$service" <<<"$running"; then
    return 0
  fi

  echo "FAIL service is not running: $service" >&2
  return 1
}

compose_exec_quiet() {
  local service="$1"
  shift
  compose exec -T "$service" "$@" >/dev/null 2>&1
}

retry_compose_exec_quiet() {
  local service="$1"
  shift
  local attempt=0

  for attempt in $(seq 1 20); do
    if compose_exec_quiet "$service" "$@"; then
      return 0
    fi
    sleep 2
  done

  return 1
}

repair_running_nextcloud_data_dir() {
  if ! compose_service_running nextcloud; then
    return 0
  fi

  compose exec -T nextcloud sh -lc '
    set -eu
    mkdir -p /var/www/html/data
    if [ ! -f /var/www/html/data/.ncdata ]; then
      {
        printf "%s\n" "# Nextcloud data directory"
        printf "%s\n" "# Do not change this file"
      } > /var/www/html/data/.ncdata
    fi
    [ -f /var/www/html/data/index.html ] || : > /var/www/html/data/index.html
    chown -R www-data:www-data /var/www/html/data 2>/dev/null || true
    chmod 0770 /var/www/html/data 2>/dev/null || true
    chmod 0644 /var/www/html/data/.ncdata /var/www/html/data/index.html 2>/dev/null || true
  ' >/dev/null 2>&1 || true
}

diagnose_nextcloud_health_failure() {
  local http_status=""

  echo "FAIL Nextcloud did not respond at http://127.0.0.1/status.php" >&2
  http_status="$(
    compose exec -T nextcloud sh -lc \
      'curl -sS -o /tmp/arclink-nextcloud-status.out -w "%{http_code}" http://127.0.0.1/status.php' \
      2>/dev/null || true
  )"
  if [[ -n "$http_status" ]]; then
    echo "Nextcloud HTTP status: $http_status" >&2
  fi
  compose exec -T nextcloud sh -lc '
    if [ ! -f /var/www/html/data/.ncdata ]; then
      echo "Nextcloud data marker is missing at /var/www/html/data/.ncdata"
    fi
    php /var/www/html/occ status 2>&1 | sed -n "1,12p"
  ' >&2 || true
}

health() {
  prepare_compose
  compose config -q

  local required_dir=""
  for required_dir in "${DOCKER_REQUIRED_STATE_DIRS[@]}"; do
    if [[ ! -d "$required_dir" ]]; then
      echo "FAIL missing Docker state directory: $required_dir" >&2
      return 1
    fi
  done

  local running
  running="$(compose ps --status running --services 2>/dev/null || true)"
  if [[ -z "$running" ]]; then
    echo "FAIL Docker Compose config is valid, but no ArcLink services are running." >&2
    echo "Run: ./deploy.sh docker install"
    return 1
  fi

  local service missing=0
  for service in "${DOCKER_REQUIRED_RUNNING_SERVICES[@]}"; do
    if ! require_running_service "$running" "$service"; then
      missing=1
    fi
  done
  if [[ "$missing" != "0" ]]; then
    return 1
  fi

  retry_compose_exec_quiet arclink-mcp curl -fsS http://127.0.0.1:8282/health
  retry_compose_exec_quiet notion-webhook curl -fsS http://127.0.0.1:8283/health
  retry_compose_exec_quiet control-api curl -fsS http://127.0.0.1:8900/api/v1/health
  retry_compose_exec_quiet control-web curl -fsS http://127.0.0.1:3000
  repair_running_nextcloud_data_dir
  retry_compose_exec_quiet nextcloud curl -fsS http://127.0.0.1/status.php || {
    diagnose_nextcloud_health_failure
    return 1
  }
  retry_compose_exec_quiet qmd-mcp qmd --version
  retry_compose_exec_quiet redis redis-cli ping
  # shellcheck disable=SC2016
  retry_compose_exec_quiet postgres sh -lc 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
  compose exec -T health-watch ./bin/docker-health.sh
  docker_publish_tailnet_deployment_apps || true
  docker_refresh_deployment_service_health || true
  echo "Docker health passed."
}

docker_publish_tailnet_deployment_apps() {
  local ingress_mode="" strategy="" host="" web_port="" base_port="" db_path="" routes_file=""

  ingress_mode="$(configured_or_default ARCLINK_INGRESS_MODE domain)"
  strategy="$(configured_or_default ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY path)"
  if [[ "$ingress_mode" != "tailscale" || "$strategy" != "path" ]]; then
    return 0
  fi
  if ! command -v tailscale >/dev/null 2>&1; then
    echo "tailscale CLI not found; skipping per-deployment tailnet app publishing." >&2
    return 0
  fi

  host="$(configured_or_default ARCLINK_TAILSCALE_DNS_NAME "")"
  web_port="$(configured_or_default ARCLINK_WEB_PORT 3000)"
  base_port="$(configured_or_default ARCLINK_TAILNET_SERVICE_PORT_BASE 8443)"
  db_path="$REPO_DIR/arclink-priv/state/arclink-control.sqlite3"
  if [[ -z "$host" || ! -f "$db_path" ]]; then
    return 0
  fi

  routes_file="$(mktemp)"
  PYTHONPATH="$REPO_DIR/python" python3 - "$db_path" "$base_port" >"$routes_file" <<'PY'
from __future__ import annotations

import json
import sqlite3
import sys
from typing import Any, Mapping

db_path, base_port_raw = sys.argv[1:3]
roles = ("hermes",)
try:
    base_port = int(base_port_raw)
except ValueError:
    base_port = 8443
if base_port < 1 or base_port + len(roles) >= 65536:
    base_port = 8443


def valid_port(value: Any) -> int:
    try:
        port = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return port if 0 < port < 65536 else 0


def clean_ports(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    return {role: port for role in roles if (port := valid_port(value.get(role)))}


with sqlite3.connect(db_path) as conn:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT deployment_id, prefix, base_domain, metadata_json
        FROM arclink_deployments
        WHERE status IN ('active', 'provisioning', 'provisioning_ready')
        ORDER BY created_at, deployment_id
        """
    ).fetchall()
    records: list[tuple[sqlite3.Row, dict[str, Any]]] = []
    used: set[int] = set()
    for row in rows:
        metadata = json.loads(row["metadata_json"] or "{}")
        ports = clean_ports(metadata.get("tailnet_service_ports"))
        used.update(ports.values())
        records.append((row, metadata))

    next_block = base_port
    for row, metadata in records:
        prefix = str(row["prefix"] or "").strip()
        if not prefix:
            continue
        ports = clean_ports(metadata.get("tailnet_service_ports"))
        if set(roles) - set(ports):
            while True:
                candidate = {role: next_block + offset for offset, role in enumerate(roles)}
                if all(0 < port < 65536 and port not in used for port in candidate.values()):
                    ports = candidate
                    used.update(candidate.values())
                    next_block += len(roles)
                    break
                next_block += len(roles)
        print(
            "\t".join(
                [
                    str(row["deployment_id"]),
                    prefix,
                    str(ports["hermes"]),
                ]
            )
        )
PY

  while IFS=$'\t' read -r deployment_id prefix hermes_port; do
    [[ -n "$deployment_id" && -n "$prefix" ]] || continue
    local status="published"
    local successful_roles=()
    if tailscale serve --bg --yes --https="$hermes_port" "http://127.0.0.1:$web_port/u/$prefix/hermes" >/dev/null; then
      successful_roles+=(hermes)
    else
      status="unavailable"
    fi
    docker_record_tailnet_deployment_app_publish \
      "$db_path" "$deployment_id" "$host" "$prefix" \
      "$hermes_port" "$status" "${successful_roles[*]}"
  done <"$routes_file"
  rm -f "$routes_file"
}

docker_record_tailnet_deployment_app_publish() {
  local db_path="$1"
  local deployment_id="$2"
  local host="$3"
  local prefix="$4"
  local hermes_port="$5"
  local status="$6"
  local successful_roles="${7:-}"

  PYTHONPATH="$REPO_DIR/python" python3 - \
    "$db_path" "$deployment_id" "$host" "$prefix" \
    "$hermes_port" "$status" "$successful_roles" <<'PY'
from __future__ import annotations

import json
import sqlite3
import sys
from typing import Any

from arclink_control import utc_now_iso

db_path, deployment_id, host, prefix, hermes_port, status, successful_raw = sys.argv[1:8]
roles = ("hermes",)


def valid_port(value: Any) -> int:
    try:
        port = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return port if 0 < port < 65536 else 0


ports = {
    "hermes": valid_port(hermes_port),
}
if set(ports.values()) == {0}:
    raise SystemExit(0)
successful = [role for role in successful_raw.split() if role in roles]
published = status == "published" and set(successful) == set(roles) and all(ports.values())
checked_at = utc_now_iso()
with sqlite3.connect(db_path) as conn:
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT metadata_json FROM arclink_deployments WHERE deployment_id = ?",
        (deployment_id,),
    ).fetchone()
    if row is None:
        raise SystemExit(0)
    try:
        metadata = json.loads(row["metadata_json"] or "{}")
    except json.JSONDecodeError:
        metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    metadata.update(
        {
            "ingress_mode": "tailscale",
            "tailscale_dns_name": host,
            "tailscale_host_strategy": "path",
            "tailnet_service_ports": ports,
            "tailnet_service_ports_checked_at": checked_at,
        }
    )
    metadata["tailnet_app_publication"] = {
        "status": "published" if published else "unavailable",
        "checked_at": checked_at,
        "successful_roles": successful,
        "failed_roles": [role for role in roles if role not in successful],
    }
    if published:
        metadata["access_urls"] = {
            "dashboard": f"https://{host}/u/{prefix}",
            "hermes": f"https://{host}:{ports['hermes']}/",
            "files": f"https://{host}/u/{prefix}/drive",
            "code": f"https://{host}/u/{prefix}/code",
            "notion": f"https://{host}/u/{prefix}/notion/webhook",
        }
    else:
        metadata.pop("access_urls", None)
        metadata["tailnet_app_publication"]["message"] = "tailnet app publication failed; app URLs intentionally withheld"
    conn.execute(
        "UPDATE arclink_deployments SET metadata_json = ? WHERE deployment_id = ?",
        (json.dumps(metadata, sort_keys=True), deployment_id),
    )
    conn.commit()
PY
}

docker_configure_deployment_nextcloud_overwrite() {
  local deployment_id="$1"
  local overwrite_host="$2"
  local overwrite_url="$3"
  local container="arclink-${deployment_id}-nextcloud-1"

  if ! docker ps --format '{{.Names}}' | grep -Fxq "$container"; then
    return 0
  fi
  docker exec "$container" php occ config:system:set overwriteprotocol --value=https >/dev/null
  docker exec "$container" php occ config:system:set overwritehost --value="$overwrite_host" >/dev/null
  docker exec "$container" php occ config:system:set overwrite.cli.url --value="$overwrite_url" >/dev/null
}

docker_refresh_deployment_service_health() {
  local db_path="$REPO_DIR/arclink-priv/state/arclink-control.sqlite3"
  local state_root_base=""

  [[ -f "$db_path" ]] || return 0
  state_root_base="$(configured_or_default ARCLINK_STATE_ROOT_BASE /arcdata/deployments)"
  PYTHONPATH="$REPO_DIR/python" python3 - "$db_path" "$state_root_base" <<'PY'
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from arclink_control import upsert_arclink_service_health
from arclink_provisioning import ARCLINK_PROVISIONING_SERVICE_NAMES
from arclink_sovereign_worker import _docker_compose_service_statuses, _parse_docker_compose_ps_json

db_path = Path(sys.argv[1])
state_root_base = Path(sys.argv[2])

with sqlite3.connect(db_path) as conn:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT deployment_id, prefix
        FROM arclink_deployments
        WHERE status IN ('active', 'provisioning', 'provisioning_ready')
        ORDER BY created_at, deployment_id
        """
    ).fetchall()
    refreshed = 0
    for row in rows:
        deployment_id = str(row["deployment_id"])
        prefix = str(row["prefix"])
        project = f"arclink-{deployment_id}"
        config_dir = state_root_base / f"{deployment_id}-{prefix}" / "config"
        compose_file = config_dir / "compose.yaml"
        env_file = config_dir / "arclink.env"
        if not compose_file.is_file():
            continue
        try:
            result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-p",
                    project,
                    "-f",
                    str(compose_file),
                    "--env-file",
                    str(env_file),
                    "ps",
                    "--all",
                    "--format",
                    "json",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            statuses = _docker_compose_service_statuses(_parse_docker_compose_ps_json(result.stdout))
        except Exception as exc:  # noqa: BLE001 - status refresh should not break deploy flow
            for service_name in ARCLINK_PROVISIONING_SERVICE_NAMES:
                upsert_arclink_service_health(
                    conn,
                    deployment_id=deployment_id,
                    service_name=service_name,
                    status="starting",
                    detail={"source": "docker_refresh_deployment_service_health", "reconcile_error": str(exc)[:240]},
                )
            continue
        for service_name in ARCLINK_PROVISIONING_SERVICE_NAMES:
            service = statuses.get(service_name)
            if service is None:
                upsert_arclink_service_health(
                    conn,
                    deployment_id=deployment_id,
                    service_name=service_name,
                    status="missing",
                    detail={"source": "docker_refresh_deployment_service_health", "project": project},
                )
                continue
            upsert_arclink_service_health(
                conn,
                deployment_id=deployment_id,
                service_name=service_name,
                status=str(service["status"]),
                detail={
                    "source": "docker_refresh_deployment_service_health",
                    "project": service.get("project") or project,
                    "container": service.get("container") or "",
                    "state": service.get("state") or "",
                    "health": service.get("health") or "",
                    "exit_code": service.get("exit_code"),
                    "status_text": service.get("status_text") or "",
                },
            )
        refreshed += 1
print(f"Refreshed Docker deployment service health for {refreshed} deployment(s).")
PY
}

docker_repair_deployment_dashboard_plugin_mounts() {
  local deployments_root=""

  deployments_root="$(configured_or_default ARCLINK_STATE_ROOT_BASE /arcdata/deployments)"
  [[ -d "$deployments_root" ]] || return 0

  python3 - "$deployments_root" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

deployments_root = Path(sys.argv[1])
changed = 0


def ensure_volume(volumes: list[dict[str, Any]], *, source: str, target: str) -> bool:
    for item in volumes:
        if str(item.get("target") or "") != target:
            continue
        new_item = {**item, "source": source, "target": target, "type": "bind"}
        if new_item != item:
            item.clear()
            item.update(new_item)
            return True
        return False
    volumes.append({"source": source, "target": target, "type": "bind"})
    return True


def ensure_secret(service: dict[str, Any], *, source: str, target: str) -> bool:
    secrets = service.setdefault("secrets", [])
    if not isinstance(secrets, list):
        service["secrets"] = [{"source": source, "target": target}]
        return True
    desired = {"source": source, "target": target}
    for item in secrets:
        if isinstance(item, dict) and str(item.get("source") or "") == source:
            if item != desired:
                item.clear()
                item.update(desired)
                return True
            return False
    secrets.append(desired)
    return True


for compose_file in sorted(deployments_root.glob("*/config/compose.yaml")):
    try:
        payload = json.loads(compose_file.read_text(encoding="utf-8"))
    except Exception:
        continue
    services = payload.get("services")
    if not isinstance(services, dict):
        continue
    compose_secrets = payload.get("secrets")
    has_chutes_secret = isinstance(compose_secrets, dict) and "chutes_api_key" in compose_secrets
    service = services.get("hermes-dashboard")
    if not isinstance(service, dict):
        continue
    deployment_root = compose_file.parents[1]
    service_changed = False
    dashboard_command = ["./bin/run-hermes-dashboard-proxy.sh"]
    if service.get("command") != dashboard_command:
        service["command"] = dashboard_command
        service_changed = True
    env = service.setdefault("environment", {})
    if isinstance(env, dict):
        for key, value in {
            "VAULT_DIR": "/srv/vault",
            "ARCLINK_DRIVE_ROOT": "/srv/vault",
            "ARCLINK_CODE_WORKSPACE_ROOT": "/workspace",
            "ARCLINK_TERMINAL_ALLOW_ROOT": "1",
            "ARCLINK_TERMINAL_TUI_COMMAND": "/opt/arclink/runtime/hermes-venv/bin/hermes",
            "HERMES_TUI_DIR": "/opt/arclink/runtime/hermes-agent-src/ui-tui",
            **({"ARCLINK_CHUTES_API_KEY_FILE": "/run/secrets/chutes_api_key"} if has_chutes_secret else {}),
        }.items():
            if env.get(key) != value:
                env[key] = value
                service_changed = True
    if has_chutes_secret:
        service_changed = ensure_secret(service, source="chutes_api_key", target="/run/secrets/chutes_api_key") or service_changed
    volumes = service.setdefault("volumes", [])
    if isinstance(volumes, list):
        service_changed = ensure_volume(
            volumes,
            source=str(deployment_root / "state" / "hermes-home"),
            target="/home/arclink/.hermes",
        ) or service_changed
        service_changed = ensure_volume(volumes, source=str(deployment_root / "vault"), target="/srv/vault") or service_changed
        service_changed = ensure_volume(volumes, source=str(deployment_root / "workspace"), target="/workspace") or service_changed
    installer = services.get("managed-context-install")
    if isinstance(installer, dict):
        installer_changed = False
        installer_command = ["./bin/install-deployment-hermes-home.sh", "/home/arclink/arclink", "/home/arclink/.hermes"]
        if installer.get("command") != installer_command:
            installer["command"] = installer_command
            installer_changed = True
        installer_env = installer.setdefault("environment", {})
        if isinstance(installer_env, dict):
            for key, value in {
                "HERMES_HOME": "/home/arclink/.hermes",
                **({"ARCLINK_CHUTES_API_KEY_FILE": "/run/secrets/chutes_api_key"} if has_chutes_secret else {}),
            }.items():
                if installer_env.get(key) != value:
                    installer_env[key] = value
                    installer_changed = True
            dashboard_env = service.get("environment") if isinstance(service.get("environment"), dict) else {}
            for key in (
                "ARCLINK_PREFIX",
                "ARCLINK_PRIMARY_PROVIDER",
                "ARCLINK_CHUTES_BASE_URL",
                "ARCLINK_CHUTES_DEFAULT_MODEL",
                "ARCLINK_MODEL_REASONING_DEFAULT",
            ):
                value = dashboard_env.get(key)
                if value and installer_env.get(key) != value:
                    installer_env[key] = value
                    installer_changed = True
        if has_chutes_secret:
            installer_changed = ensure_secret(installer, source="chutes_api_key", target="/run/secrets/chutes_api_key") or installer_changed
        service_changed = installer_changed or service_changed
    if service_changed:
        compose_file.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        changed += 1

if changed:
    print(f"Repaired Hermes dashboard plugin mounts for {changed} deployment compose file(s).")
PY
}

docker_refresh_deployment_managed_plugins() {
  local deployments_root=""
  local compose_file="" deploy_root="" root_name="" deployment_id="" clean_id="" project="" refreshed=0

  deployments_root="$(configured_or_default ARCLINK_STATE_ROOT_BASE /arcdata/deployments)"
  [[ -d "$deployments_root" ]] || return 0

  while IFS= read -r compose_file; do
    if ! docker compose -f "$compose_file" config --services 2>/dev/null | grep -Fxq managed-context-install; then
      continue
    fi

    deploy_root="$(dirname "$(dirname "$compose_file")")"
    root_name="$(basename "$deploy_root")"
    deployment_id="${root_name%%-*}"
    clean_id="$(printf '%s' "$deployment_id" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9_-]+/-/g; s/^[-_]+//; s/[-_]+$//')"
    if [[ -z "$clean_id" ]]; then
      echo "Skipping deployment plugin refresh for $compose_file: could not derive deployment id." >&2
      continue
    fi
    project="arclink-$clean_id"

    env ARCLINK_DOCKER_IMAGE="${ARCLINK_DOCKER_IMAGE:-arclink/app:local}" \
      docker compose -p "$project" -f "$compose_file" run --rm --no-deps managed-context-install >/dev/null

    if docker compose -f "$compose_file" config --services 2>/dev/null | grep -Fxq hermes-dashboard; then
      env ARCLINK_DOCKER_IMAGE="${ARCLINK_DOCKER_IMAGE:-arclink/app:local}" \
        docker compose -p "$project" -f "$compose_file" up -d --no-deps --force-recreate hermes-dashboard >/dev/null
    fi
    refreshed=$((refreshed + 1))
  done < <(find "$deployments_root" -mindepth 3 -maxdepth 3 -path '*/config/compose.yaml' -type f 2>/dev/null | sort)

  if (( refreshed > 0 )); then
    echo "Refreshed deployment-managed Hermes plugins for $refreshed deployment(s)."
  fi
}

docker_reconcile() {
  prepare_compose
  if [[ -f "$REPO_DIR/arclink-priv/config/org-profile.yaml" ]]; then
    echo "Applying Docker private operating profile..."
    compose_app_command ./bin/arclink-ctl org-profile apply --yes
  fi
  compose up -d --no-build agent-supervisor
  if compose_service_running agent-supervisor; then
    compose restart agent-supervisor >/dev/null
  fi
  wait_for_docker_agent_reconcile ||
    echo "Docker agent supervisor is still reconciling; docker health will report details if it remains incomplete."
  docker_repair_deployment_dashboard_plugin_mounts || true
  docker_refresh_deployment_managed_plugins || true
  docker_publish_tailnet_deployment_apps || true
  docker_refresh_deployment_service_health || true
  echo "Docker agent supervisor realigned."
}

docker_provision_once() {
  local rc=0
  prepare_compose
  compose run --rm --no-deps control-provisioner python3 python/arclink_sovereign_worker.py --once --json "$@" || rc=$?
  docker_repair_deployment_dashboard_plugin_mounts || true
  docker_refresh_deployment_managed_plugins || true
  docker_publish_tailnet_deployment_apps || true
  docker_refresh_deployment_service_health || true
  return "$rc"
}

wait_for_docker_agent_reconcile() {
  local attempt=0

  for attempt in $(seq 1 60); do
    if compose exec -T agent-supervisor python3 - <<'PY' >/dev/null 2>&1
from pathlib import Path

from arclink_control import Config, connect_db

cfg = Config.from_env()
with connect_db(cfg) as conn:
    conn.row_factory = __import__("sqlite3").Row
    rows = conn.execute(
        """
        SELECT agent_id, unix_user, hermes_home
        FROM agents
        WHERE role = 'user' AND status = 'active'
        ORDER BY unix_user
        """
    ).fetchall()
    for row in rows:
        agent_id = str(row["agent_id"] or "")
        hermes_home = Path(str(row["hermes_home"] or ""))
        required = (
            hermes_home / "plugins" / "arclink-managed-context" / "plugin.yaml",
            hermes_home / "SOUL.md",
            hermes_home / "state" / "arclink-vault-reconciler.json",
            hermes_home / "secrets" / "arclink-bootstrap-token",
        )
        if not all(path.is_file() for path in required):
            raise SystemExit(1)
        job = conn.execute(
            "SELECT last_status FROM refresh_jobs WHERE job_name = ?",
            (f"{agent_id}-refresh",),
        ).fetchone()
        if job is None or str(job["last_status"] or "") != "ok":
            raise SystemExit(1)
PY
    then
      return 0
    fi
    sleep 2
  done
  return 1
}

docker_record_release_state() {
  local commit="" branch="" origin_url="" upstream_url="" upstream_branch=""
  local target="$REPO_DIR/arclink-priv/state/arclink-release.json"

  bootstrap >/dev/null
  commit="$(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || true)"
  branch="$(git -C "$REPO_DIR" symbolic-ref --quiet --short HEAD 2>/dev/null || git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  origin_url="$(git -C "$REPO_DIR" remote get-url origin 2>/dev/null || true)"
  upstream_url="$(configured_or_default ARCLINK_UPSTREAM_REPO_URL "$origin_url")"
  upstream_branch="$(configured_or_default ARCLINK_UPSTREAM_BRANCH "${branch:-main}")"
  mkdir -p "$(dirname "$target")"
  python3 - "$target" "$commit" "$origin_url" "$branch" "$REPO_DIR" "$upstream_url" "$upstream_branch" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

target = Path(sys.argv[1])
payload = {
    "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "deployed_from": "docker-checkout",
    "deployed_commit": sys.argv[2],
    "deployed_source_repo": sys.argv[3],
    "deployed_source_branch": sys.argv[4],
    "deployed_source_path": sys.argv[5],
    "tracked_upstream_repo_url": sys.argv[6],
    "tracked_upstream_branch": sys.argv[7],
}
target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
  echo "Docker release state recorded: $target"
}

docker_live_agent_smoke() {
  compose_supervisor_command ./bin/live-agent-tool-smoke.sh "$@"
}

show_ports() {
  bootstrap >/dev/null
  if [[ -f "$DOCKER_PORT_MANIFEST" ]]; then
    python3 -m json.tool "$DOCKER_PORT_MANIFEST"
    return 0
  fi

  printf 'QMD_MCP_PORT=%s\n' "$(configured_or_default QMD_MCP_PORT 8181)"
  printf 'ARCLINK_MCP_PORT=%s\n' "$(configured_or_default ARCLINK_MCP_PORT 8282)"
  printf 'ARCLINK_NOTION_WEBHOOK_PORT=%s\n' "$(configured_or_default ARCLINK_NOTION_WEBHOOK_PORT 8283)"
  printf 'NEXTCLOUD_PORT=%s\n' "$(configured_or_default NEXTCLOUD_PORT 18080)"
  printf 'ARCLINK_API_PORT=%s\n' "$(configured_or_default ARCLINK_API_PORT 8900)"
  printf 'ARCLINK_WEB_PORT=%s\n' "$(configured_or_default ARCLINK_WEB_PORT 3000)"
}

random_secret() {
  python3 - <<'PY'
import secrets

print(secrets.token_urlsafe(32))
PY
}

mask_secret() {
  local value="$1"
  if [[ ${#value} -le 8 ]]; then
    printf '****\n'
  else
    printf '%s...%s\n' "${value:0:4}" "${value: -4}"
  fi
}

require_single_line_secret() {
  local name="$1"
  local value="$2"
  if [[ -z "$value" || "$value" == *$'\n'* || "$value" == *$'\r'* ]]; then
    echo "$name must be a non-empty single-line value." >&2
    return 1
  fi
}

nextcloud_config_value() {
  local key="$1"
  # shellcheck disable=SC2016
  compose exec -T nextcloud php -r '
    $key = $argv[1] ?? "";
    $CONFIG = [];
    $path = "/var/www/html/config/config.php";
    if (is_file($path)) {
      include $path;
    }
    $value = $CONFIG[$key] ?? "";
    if (is_string($value)) {
      echo $value;
    }
  ' "$key"
}

docker_deploy_in_app() {
  compose_app_interactive ./deploy.sh "$@"
}

docker_notion_migrate() {
  local rc=0

  prepare_compose
  echo "Pausing Docker Notion write/batcher services; keeping notion-webhook online for verification."
  compose stop arclink-mcp ssot-batcher agent-supervisor >/dev/null 2>&1 || true
  compose_run_maybe_tty arclink-mcp ./deploy.sh notion-migrate "$@" || rc=$?
  echo "Restarting Docker Notion services."
  if ! compose up -d --no-build arclink-mcp ssot-batcher agent-supervisor notion-webhook; then
    return 1
  fi
  return "$rc"
}

docker_enrollment_status() {
  local onboarding_file="" provision_file="" supervisor_state="stopped" db_path=""

  onboarding_file="$(mktemp)"
  provision_file="$(mktemp)"
  if ! compose_app_command ./bin/arclink-ctl --json onboarding list >"$onboarding_file"; then
    rm -f "$onboarding_file" "$provision_file"
    return 1
  fi
  if ! compose_app_command ./bin/arclink-ctl --json provision list >"$provision_file"; then
    rm -f "$onboarding_file" "$provision_file"
    return 1
  fi

  if compose_service_running agent-supervisor; then
    supervisor_state="running"
  fi
  db_path="$REPO_DIR/arclink-priv/state/arclink-control.sqlite3"

  echo "Enrollment status (Docker)"
  echo
  echo "Config:              $DOCKER_ENV_FILE"
  echo "Repo:                $REPO_DIR"
  echo "DB:                  $db_path"
  echo "Agent supervisor:    $supervisor_state"
  echo "Provisioner:         Docker supervisor loop (not systemd)"
  echo "Notion claim poller: Docker supervisor provisioner pass (not systemd)"
  echo

  python3 - "$onboarding_file" "$provision_file" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    onboarding = json.load(handle)
with open(sys.argv[2], "r", encoding="utf-8") as handle:
    provisions = json.load(handle)

active_onboarding = [
    {
        "session_id": row.get("session_id", ""),
        "state": row.get("state", ""),
        "unix_user": (row.get("answers") or {}).get("unix_user", ""),
        "platform": row.get("platform", ""),
        "updated_at": row.get("updated_at", ""),
        "error": row.get("provision_error", "") or "",
    }
    for row in onboarding
    if row.get("state") not in {"denied", "completed", "cancelled"}
]

active_provisions = [
    {
        "request_id": row.get("request_id", ""),
        "provision_state": row.get("provision_state", ""),
        "status": row.get("status", ""),
        "unix_user": row.get("unix_user", ""),
        "attempts": row.get("provision_attempts", 0),
        "next_attempt_at": row.get("provision_next_attempt_at", "") or "",
        "error": row.get("provision_error", "") or "",
    }
    for row in provisions
    if row.get("provision_state") not in {"completed", "cancelled", "denied"}
]

print("Active onboarding sessions:")
if not active_onboarding:
    print("  none")
else:
    for row in active_onboarding:
        detail = f"  {row['session_id']} state={row['state']} unix_user={row['unix_user'] or '-'} platform={row['platform'] or '-'} updated={row['updated_at'] or '-'}"
        if row["error"]:
            detail += f" error={row['error']}"
        print(detail)

print()
print("Active auto-provision requests:")
if not active_provisions:
    print("  none")
else:
    for row in active_provisions:
        detail = (
            f"  {row['request_id']} provision_state={row['provision_state']} status={row['status']} "
            f"unix_user={row['unix_user'] or '-'} attempts={row['attempts']}"
        )
        if row["next_attempt_at"]:
            detail += f" next={row['next_attempt_at']}"
        if row["error"]:
            detail += f" error={row['error']}"
        print(detail)
PY

  rm -f "$onboarding_file" "$provision_file"
  echo
  echo "Repair commands:"
  echo "  ./deploy.sh docker enrollment-trace --unix-user <unix-user>"
  echo "  ./deploy.sh docker enrollment-align"
  echo "  ./deploy.sh docker enrollment-reset --unix-user <unix-user>"
}

resolve_enrollment_trace_selector() {
  local selector_kind="" selector_value=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --unix-user)
        selector_kind="unix-user"
        selector_value="${2:-}"
        shift 2
        ;;
      --session-id)
        selector_kind="session-id"
        selector_value="${2:-}"
        shift 2
        ;;
      --request-id)
        selector_kind="request-id"
        selector_value="${2:-}"
        shift 2
        ;;
      --log-lines)
        shift 2
        ;;
      *)
        if [[ -z "$selector_value" ]]; then
          selector_value="$1"
          case "$selector_value" in
            onb_*) selector_kind="session-id" ;;
            req_*) selector_kind="request-id" ;;
            *) selector_kind="unix-user" ;;
          esac
        else
          echo "Unexpected enrollment-trace argument: $1" >&2
          return 1
        fi
        shift
        ;;
    esac
  done

  if [[ -z "$selector_value" && -t 0 ]]; then
    read -r -p "Trace unix user, onboarding session id, or bootstrap request id: " selector_value
    case "$selector_value" in
      onb_*) selector_kind="session-id" ;;
      req_*) selector_kind="request-id" ;;
      *) selector_kind="unix-user" ;;
    esac
  fi
  if [[ -z "$selector_kind" || -z "$selector_value" ]]; then
    echo "Provide --unix-user, --session-id, or --request-id." >&2
    return 1
  fi
  printf '%s\t%s\n' "$selector_kind" "$selector_value"
}

docker_enrollment_trace() {
  local selector_spec="" selector_kind="" selector_value="" log_lines="${TRACE_LOG_LINES:-80}" db_path=""
  local -a selector_args=()

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --log-lines)
        log_lines="${2:-80}"
        shift 2
        ;;
      *)
        selector_args+=("$1")
        shift
        ;;
    esac
  done
  selector_spec="$(resolve_enrollment_trace_selector "${selector_args[@]}")"
  IFS=$'\t' read -r selector_kind selector_value <<<"$selector_spec"
  bootstrap >/dev/null
  db_path="$REPO_DIR/arclink-priv/state/arclink-control.sqlite3"

  python3 - "$db_path" "$REPO_DIR/arclink-priv/state" "$selector_kind" "$selector_value" "$log_lines" <<'PY'
import json
import sqlite3
import sys
from pathlib import Path

db_path = Path(sys.argv[1])
state_dir = Path(sys.argv[2])
selector_kind = sys.argv[3]
selector_value = sys.argv[4]
log_lines = int(sys.argv[5])


def json_loads(raw, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def rows(conn, table):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone():
        return []
    return [dict(row) for row in conn.execute(f"SELECT * FROM {table}").fetchall()]


if not db_path.exists():
    raise SystemExit(f"Docker control DB not found: {db_path}")

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
onboarding = rows(conn, "onboarding_sessions")
requests = rows(conn, "bootstrap_requests")
agents = rows(conn, "agents")

matched_sessions = []
matched_requests = []
matched_agents = []

if selector_kind == "session-id":
    matched_sessions = [row for row in onboarding if row.get("session_id") == selector_value]
    linked_requests = {str(row.get("linked_request_id") or "") for row in matched_sessions}
    unix_users = {json_loads(row.get("answers_json"), {}).get("unix_user", "") for row in matched_sessions}
    matched_requests = [row for row in requests if row.get("request_id") in linked_requests or row.get("unix_user") in unix_users]
    matched_agents = [row for row in agents if row.get("unix_user") in unix_users]
elif selector_kind == "request-id":
    matched_requests = [row for row in requests if row.get("request_id") == selector_value]
    unix_users = {str(row.get("unix_user") or "") for row in matched_requests}
    matched_sessions = [
        row for row in onboarding
        if row.get("linked_request_id") == selector_value or json_loads(row.get("answers_json"), {}).get("unix_user", "") in unix_users
    ]
    matched_agents = [row for row in agents if row.get("unix_user") in unix_users]
else:
    unix_users = {selector_value}
    matched_sessions = [row for row in onboarding if json_loads(row.get("answers_json"), {}).get("unix_user", "") == selector_value]
    matched_requests = [row for row in requests if row.get("unix_user") == selector_value]
    matched_agents = [row for row in agents if row.get("unix_user") == selector_value]

print("Enrollment trace (Docker)")
print(f"selector: {selector_kind}={selector_value}")
print()

print("Onboarding sessions:")
if not matched_sessions:
    print("  none")
for row in matched_sessions:
    answers = json_loads(row.get("answers_json"), {})
    print(
        f"  {row.get('session_id')} state={row.get('state')} platform={row.get('platform')} "
        f"unix_user={answers.get('unix_user') or '-'} linked_request={row.get('linked_request_id') or '-'} "
        f"agent={row.get('linked_agent_id') or '-'} updated={row.get('updated_at') or '-'}"
    )
    if row.get("provision_error"):
        print(f"    provision_error={row.get('provision_error')}")

print()
print("Auto-provision requests:")
if not matched_requests:
    print("  none")
for row in matched_requests:
    print(
        f"  {row.get('request_id')} status={row.get('status')} unix_user={row.get('unix_user') or '-'} "
        f"attempts={row.get('provision_attempts') or 0} started={row.get('provision_started_at') or '-'} "
        f"next={row.get('provision_next_attempt_at') or '-'} provisioned={row.get('provisioned_at') or '-'}"
    )
    if row.get("provision_error"):
        print(f"    provision_error={row.get('provision_error')}")

print()
print("Agents:")
if not matched_agents:
    print("  none")
for row in matched_agents:
    print(
        f"  {row.get('agent_id')} status={row.get('status')} unix_user={row.get('unix_user')} "
        f"hermes_home={row.get('hermes_home')}"
    )

print()
print("Recent Docker supervisor logs:")
log_root = state_dir / "docker" / "agent-supervisor"
paths = [log_root / "enrollment-provisioner.log"]
for agent in matched_agents:
    agent_id = str(agent.get("agent_id") or "")
    if agent_id:
        paths.append(log_root / f"{agent_id}-supervisor.log")
for path in paths:
    if not path.exists():
        continue
    print(f"  {path}:")
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-log_lines:]
    for line in lines:
        print(f"    {line}")
PY
}

docker_enrollment_align() {
  prepare_compose
  compose up -d --no-build agent-supervisor
  compose exec -T agent-supervisor ./bin/arclink-enrollment-provision.sh || true
  compose restart agent-supervisor
  echo "Docker enrollment provisioner and agent supervisor realigned."
  echo
  docker_enrollment_status
}

docker_enrollment_reset() {
  local target_unix_user="${ENROLLMENT_RESET_UNIX_USER:-}" confirm_text=""
  local remove_archives="${ENROLLMENT_RESET_REMOVE_ARCHIVES:-0}"
  local purge_rate_limits="${ENROLLMENT_RESET_PURGE_RATE_LIMITS:-1}"
  local remove_nextcloud_user="${ENROLLMENT_RESET_REMOVE_NEXTCLOUD_USER:-1}"
  local extra_subject="${ENROLLMENT_RESET_EXTRA_SUBJECT:-}"
  local -a purge_cmd=()

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --unix-user)
        target_unix_user="${2:-}"
        shift 2
        ;;
      --remove-archives)
        remove_archives=1
        shift
        ;;
      --keep-nextcloud-user)
        remove_nextcloud_user=0
        shift
        ;;
      --keep-rate-limits)
        purge_rate_limits=0
        shift
        ;;
      --extra-rate-limit-subject)
        extra_subject="${2:-}"
        shift 2
        ;;
      *)
        echo "Unexpected enrollment-reset argument: $1" >&2
        return 2
        ;;
    esac
  done

  if [[ -z "$target_unix_user" && -t 0 ]]; then
    read -r -p "Docker enrollment unix user to reset: " target_unix_user
  fi
  if [[ -z "$target_unix_user" ]]; then
    echo "Provide --unix-user or ENROLLMENT_RESET_UNIX_USER." >&2
    return 1
  fi

  echo "Docker enrollment reset will purge control-plane state for: $target_unix_user"
  echo "Container-local Unix users are recreated by the Docker supervisor when needed."
  if [[ "${ENROLLMENT_RESET_ASSUME_YES:-0}" != "1" ]]; then
    read -r -p "Type RESET to confirm Docker enrollment cleanup: " confirm_text
    if [[ "$confirm_text" != "RESET" ]]; then
      echo "Docker enrollment reset cancelled."
      return 1
    fi
  fi

  purge_cmd=(./bin/arclink-ctl --json user purge-enrollment "$target_unix_user" --actor deploy-docker-enrollment-reset)
  if [[ "$remove_archives" == "1" ]]; then
    purge_cmd+=(--remove-archives)
  fi
  if [[ "$purge_rate_limits" == "1" ]]; then
    purge_cmd+=(--purge-rate-limits)
  fi
  if [[ "$remove_nextcloud_user" == "1" ]]; then
    purge_cmd+=(--remove-nextcloud-user)
  fi
  if [[ -n "$extra_subject" ]]; then
    purge_cmd+=(--extra-rate-limit-subject "$extra_subject")
  fi

  compose_supervisor_command "${purge_cmd[@]}"
  prepare_compose
  compose restart agent-supervisor >/dev/null 2>&1 || true
  echo "Docker enrollment purge complete for $target_unix_user."
  echo
  docker_enrollment_status
}

docker_curator_setup() {
  prepare_compose
  compose_app_interactive ./bin/bootstrap-curator.sh
  compose up -d --no-build curator-refresh
  COMPOSE_PROFILES="${COMPOSE_PROFILES:-curator}" compose up -d --no-build curator-gateway curator-onboarding curator-discord-onboarding || true
  echo "Docker Curator runtime assets refreshed. Curator-profile services were started when their configured credentials allow them to run."
}

docker_rotate_nextcloud_secrets() {
  local new_postgres_password="" new_admin_password="" masked_postgres="" masked_admin="" confirm_text=""
  local pg_user="" pg_db="" admin_user=""

  prepare_compose
  compose up -d --no-build postgres redis nextcloud

  pg_user="$(nextcloud_config_value dbuser 2>/dev/null || true)"
  pg_user="${pg_user:-$(configured_or_default POSTGRES_USER nextcloud)}"
  pg_db="$(nextcloud_config_value dbname 2>/dev/null || true)"
  pg_db="${pg_db:-$(configured_or_default POSTGRES_DB nextcloud)}"
  admin_user="$(configured_or_default NEXTCLOUD_ADMIN_USER admin)"
  new_postgres_password="${NEXTCLOUD_ROTATE_POSTGRES_PASSWORD:-$(random_secret)}"
  new_admin_password="${NEXTCLOUD_ROTATE_ADMIN_PASSWORD:-$(random_secret)}"
  require_single_line_secret NEXTCLOUD_ROTATE_POSTGRES_PASSWORD "$new_postgres_password"
  require_single_line_secret NEXTCLOUD_ROTATE_ADMIN_PASSWORD "$new_admin_password"

  masked_postgres="$(mask_secret "$new_postgres_password")"
  masked_admin="$(mask_secret "$new_admin_password")"

  echo "ArcLink Docker: rotate Nextcloud credentials"
  echo
  echo "Config:             $DOCKER_ENV_FILE"
  echo "Nextcloud admin:    $admin_user"
  echo "New Postgres pass:  $masked_postgres"
  echo "New admin pass:     $masked_admin"
  if [[ "${NEXTCLOUD_ROTATE_ASSUME_YES:-0}" != "1" ]]; then
    read -r -p "Type ROTATE to apply the Docker credential rotation: " confirm_text
    if [[ "$confirm_text" != "ROTATE" ]]; then
      echo "Docker credential rotation cancelled."
      return 1
    fi
  fi

  OC_PASS="$new_admin_password" \
    compose exec -T -e OC_PASS -u www-data nextcloud php occ user:resetpassword --password-from-env "$admin_user" >/dev/null
  ARCLINK_NEXTCLOUD_DB_PASSWORD="$new_postgres_password" \
    compose exec -T -e ARCLINK_NEXTCLOUD_DB_PASSWORD -u www-data nextcloud sh -eu -c \
      'php occ config:system:set dbpassword --type=string --value="$ARCLINK_NEXTCLOUD_DB_PASSWORD"' >/dev/null

  ARCLINK_NEXTCLOUD_DB_PASSWORD="$new_postgres_password" python3 - "$pg_user" <<'PY' | compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "$pg_user" -d "$pg_db"
import os
import sys


def ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


print(f"ALTER ROLE {ident(sys.argv[1])} PASSWORD {literal(os.environ['ARCLINK_NEXTCLOUD_DB_PASSWORD'])};")
PY

  set_env_file_value POSTGRES_PASSWORD "$new_postgres_password"
  set_env_file_value POSTGRES_USER "$pg_user"
  set_env_file_value POSTGRES_DB "$pg_db"
  set_env_file_value NEXTCLOUD_ADMIN_PASSWORD "$new_admin_password"
  compose restart nextcloud
  local attempt=0
  for attempt in $(seq 1 30); do
    if compose exec -T nextcloud curl -fsS http://127.0.0.1/status.php >/dev/null 2>&1; then
      break
    fi
    if [[ "$attempt" -eq 30 ]]; then
      echo "Nextcloud did not report healthy after credential rotation." >&2
      return 1
    fi
    sleep 2
  done
  echo
  echo "Docker Nextcloud credentials rotated and persisted to $DOCKER_ENV_FILE."
}

docker_pins_show() {
  "$REPO_DIR/deploy.sh" pins-show
}

docker_pins_check() {
  "$REPO_DIR/deploy.sh" pins-check
}

docker_pin_upgrade_notify() {
  compose_app_command ./bin/arclink-ctl --json internal pin-upgrade-check
}

component_for_upgrade_command() {
  local command="$1"
  case "$command" in
    hermes-upgrade|hermes-upgrade-check) printf '%s\n' "hermes-agent" ;;
    qmd-upgrade|qmd-upgrade-check) printf '%s\n' "qmd" ;;
    nextcloud-upgrade|nextcloud-upgrade-check) printf '%s\n' "nextcloud" ;;
    postgres-upgrade|postgres-upgrade-check) printf '%s\n' "postgres" ;;
    redis-upgrade|redis-upgrade-check) printf '%s\n' "redis" ;;
    nvm-upgrade|nvm-upgrade-check) printf '%s\n' "nvm" ;;
    node-upgrade|node-upgrade-check) printf '%s\n' "node" ;;
    *) printf '%s\n' "" ;;
  esac
}

docker_component_upgrade_check() {
  local command="$1"
  shift
  local component=""
  component="$(component_for_upgrade_command "$command")"
  if [[ -z "$component" ]]; then
    echo "Unsupported Docker component command: $command" >&2
    return 2
  fi
  "$SCRIPT_DIR/component-upgrade.sh" "$component" check "$@"
}

docker_component_upgrade_apply() {
  local command="$1"
  shift
  local component="" origin_url="" branch="" upstream_url="" upstream_branch=""
  component="$(component_for_upgrade_command "$command")"
  if [[ -z "$component" ]]; then
    echo "Unsupported Docker component command: $command" >&2
    return 2
  fi
  origin_url="$(git -C "$REPO_DIR" remote get-url origin 2>/dev/null || true)"
  branch="$(git -C "$REPO_DIR" symbolic-ref --quiet --short HEAD 2>/dev/null || git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  [[ "$branch" == "HEAD" ]] && branch=""
  upstream_url="$(configured_or_default ARCLINK_UPSTREAM_REPO_URL "$origin_url")"
  upstream_branch="$(configured_or_default ARCLINK_UPSTREAM_BRANCH "${branch:-main}")"
  env \
    ARCLINK_COMPONENT_UPGRADE_MODE=docker \
    ARCLINK_CONFIG_FILE="$DOCKER_ENV_FILE" \
    ARCLINK_UPSTREAM_REPO_URL="$upstream_url" \
    ARCLINK_UPSTREAM_BRANCH="$upstream_branch" \
    ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED="$(configured_or_default ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED "")" \
    ARCLINK_UPSTREAM_DEPLOY_KEY_USER="$(configured_or_default ARCLINK_UPSTREAM_DEPLOY_KEY_USER "")" \
    ARCLINK_UPSTREAM_DEPLOY_KEY_PATH="$(configured_or_default ARCLINK_UPSTREAM_DEPLOY_KEY_PATH "")" \
    ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE="$(configured_or_default ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE "")" \
    "$SCRIPT_DIR/component-upgrade.sh" "$component" apply "$@"
}

main() {
  local command="${1:-}"
  if [[ -z "$command" || "$command" == "-h" || "$command" == "--help" ]]; then
    usage
    return 0
  fi
  shift || true

  case "$command" in
    bootstrap)
      bootstrap "$@"
      ;;
    write-config)
      bootstrap "$@"
      echo "Docker config: $DOCKER_ENV_FILE"
      ;;
    config)
      prepare_compose
      if [[ "$#" -eq 0 ]]; then
        compose config -q
        echo "Docker Compose config is valid. Full config output is redacted by default; use --unsafe-print only for local debugging."
      elif [[ "$1" == "-q" || "$1" == "--quiet" ]]; then
        compose config -q
      elif [[ "$1" == "--unsafe-print" ]]; then
        shift
        echo "WARNING: printing full Docker Compose config may expose generated passwords and tokens." >&2
        compose config "$@"
      else
        echo "Refusing to print Docker Compose config because it may expose generated passwords and tokens." >&2
        echo "Use './deploy.sh docker config -q' to validate, or '--unsafe-print' for explicit local debugging." >&2
        return 2
      fi
      ;;
    build)
      prepare_compose
      if [[ "$#" -eq 0 ]]; then
        compose build arclink-app
      else
        compose build "$@"
      fi
      ;;
    up)
      prepare_compose
      compose up -d --no-build "$@"
      ;;
    reconcile)
      docker_reconcile "$@"
      ;;
    down)
      require_docker_compose
      compose down "$@"
      ;;
    ps)
      require_docker_compose
      compose ps "$@"
      ;;
    ports)
      show_ports "$@"
      ;;
    logs)
      require_docker_compose
      compose logs "$@"
      ;;
    health)
      health "$@"
      ;;
    provision-once)
      docker_provision_once "$@"
      ;;
    record-release)
      docker_record_release_state "$@"
      ;;
    live-smoke)
      docker_live_agent_smoke "$@"
      ;;
    notion-ssot)
      docker_deploy_in_app notion-ssot "$@"
      ;;
    notion-migrate)
      docker_notion_migrate "$@"
      ;;
    notion-transfer)
      docker_deploy_in_app notion-transfer "$@"
      ;;
    enrollment-status)
      docker_enrollment_status "$@"
      ;;
    enrollment-trace)
      docker_enrollment_trace "$@"
      ;;
    enrollment-align)
      docker_enrollment_align "$@"
      ;;
    enrollment-reset)
      docker_enrollment_reset "$@"
      ;;
    curator-setup)
      docker_curator_setup "$@"
      ;;
    rotate-nextcloud-secrets)
      docker_rotate_nextcloud_secrets "$@"
      ;;
    agent-payload|agent)
      docker_deploy_in_app agent-payload "$@"
      ;;
    pins-show)
      docker_pins_show "$@"
      ;;
    pins-check)
      docker_pins_check "$@"
      ;;
    pin-upgrade-notify)
      docker_pin_upgrade_notify "$@"
      ;;
    hermes-upgrade-check|qmd-upgrade-check|nextcloud-upgrade-check|postgres-upgrade-check|redis-upgrade-check|nvm-upgrade-check|node-upgrade-check)
      docker_component_upgrade_check "$command" "$@"
      ;;
    hermes-upgrade|qmd-upgrade|nextcloud-upgrade|postgres-upgrade|redis-upgrade|nvm-upgrade|node-upgrade)
      docker_component_upgrade_apply "$command" "$@"
      ;;
    teardown)
      require_docker_compose
      compose down --volumes --remove-orphans "$@"
      ;;
    remove)
      require_docker_compose
      compose down --volumes --remove-orphans "$@"
      ;;
    *)
      usage >&2
      return 2
      ;;
  esac
}

main "$@"
