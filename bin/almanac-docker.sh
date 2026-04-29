#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="${ALMANAC_DOCKER_COMPOSE_FILE:-$REPO_DIR/compose.yaml}"
DOCKER_ENV_FILE="${ALMANAC_DOCKER_ENV_FILE:-$REPO_DIR/almanac-priv/config/docker.env}"
DOCKER_REQUIRED_STATE_DIRS=(
  "$REPO_DIR/almanac-priv/config"
  "$REPO_DIR/almanac-priv/vault"
  "$REPO_DIR/almanac-priv/state"
  "$REPO_DIR/almanac-priv/state/nextcloud"
  "$REPO_DIR/almanac-priv/state/pdf-ingest/markdown"
  "$REPO_DIR/almanac-priv/state/notion-index/markdown"
)
DOCKER_REQUIRED_RUNNING_SERVICES=(
  postgres
  redis
  nextcloud
  almanac-mcp
  qmd-mcp
  notion-webhook
  vault-watch
  agent-supervisor
  health-watch
)
DOCKER_PORT_MANIFEST="$REPO_DIR/almanac-priv/state/docker/ports.json"

usage() {
  cat <<'EOF'
Usage: bin/almanac-docker.sh <command> [args]

Commands:
  bootstrap   Seed Docker state/config directories under almanac-priv
  write-config
              Alias for bootstrap, matching deploy.sh's config-only lane
  config      Validate and print the Docker Compose configuration
  build       Build Almanac Docker images
  up          Start the Docker stack
  down        Stop the Docker stack
  ps          Show Compose service state
  ports       Show assigned Docker host ports
  logs        Follow or print Compose logs
  health      Validate Compose config, state directories, and running services
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
  compose_service_command almanac-mcp "$@"
}

compose_app_interactive() {
  compose_service_interactive almanac-mcp "$@"
}

compose_supervisor_command() {
  compose_service_command agent-supervisor "$@"
}

require_docker_compose() {
  if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    echo "docker compose is required for Almanac Docker mode." >&2
    return 1
  fi
}

prepare_compose() {
  require_docker_compose
  bootstrap
  reserve_docker_ports
}

bootstrap() {
  ALMANAC_REPO_DIR="$REPO_DIR" \
  ALMANAC_PRIV_DIR="$REPO_DIR/almanac-priv" \
  ALMANAC_PRIV_CONFIG_DIR="$REPO_DIR/almanac-priv/config" \
  ALMANAC_CONFIG_FILE="$DOCKER_ENV_FILE" \
  ALMANAC_DOCKER_CONFIG_REPO_DIR="/home/almanac/almanac" \
  ALMANAC_DOCKER_CONFIG_PRIV_DIR="/home/almanac/almanac/almanac-priv" \
  ALMANAC_DOCKER_CONFIG_RUNTIME_DIR="/opt/almanac/runtime" \
  ALMANAC_DOCKER_HOST_REPO_DIR="$REPO_DIR" \
  ALMANAC_DOCKER_HOST_PRIV_DIR="$REPO_DIR/almanac-priv" \
  ALMANAC_DOCKER_REWRITE_CONFIG="${ALMANAC_DOCKER_REWRITE_CONFIG:-0}" \
  XDG_CONFIG_HOME="$REPO_DIR/almanac-priv/state/qmd/config" \
  XDG_CACHE_HOME="$REPO_DIR/almanac-priv/state/qmd/cache" \
    "$SCRIPT_DIR/docker-entrypoint.sh" true
  set_env_file_value ALMANAC_DOCKER_HOST_REPO_DIR "$REPO_DIR"
  set_env_file_value ALMANAC_DOCKER_HOST_PRIV_DIR "$REPO_DIR/almanac-priv"
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

  [[ "$qmd_port" != "$mcp_port" ]] || return 1
  [[ "$qmd_port" != "$webhook_port" ]] || return 1
  [[ "$qmd_port" != "$nextcloud_port" ]] || return 1
  [[ "$mcp_port" != "$webhook_port" ]] || return 1
  [[ "$mcp_port" != "$nextcloud_port" ]] || return 1
  [[ "$webhook_port" != "$nextcloud_port" ]] || return 1

  host_port_available_for_service "$qmd_port" qmd-mcp 8181 &&
    host_port_available_for_service "$mcp_port" almanac-mcp 8282 &&
    host_port_available_for_service "$webhook_port" notion-webhook 8283 &&
    host_port_available_for_service "$nextcloud_port" nextcloud 80
}

persist_docker_ports() {
  local qmd_port="$1"
  local mcp_port="$2"
  local webhook_port="$3"
  local nextcloud_port="$4"

  set_env_file_value QMD_MCP_PORT "$qmd_port"
  set_env_file_value ALMANAC_MCP_PORT "$mcp_port"
  set_env_file_value ALMANAC_NOTION_WEBHOOK_PORT "$webhook_port"
  set_env_file_value NEXTCLOUD_PORT "$nextcloud_port"
  mkdir -p "$(dirname "$DOCKER_PORT_MANIFEST")"
  python3 - "$DOCKER_PORT_MANIFEST" "$qmd_port" "$mcp_port" "$webhook_port" "$nextcloud_port" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = {
    "qmd_mcp_port": int(sys.argv[2]),
    "almanac_mcp_port": int(sys.argv[3]),
    "notion_webhook_port": int(sys.argv[4]),
    "nextcloud_port": int(sys.argv[5]),
}
path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

reserve_docker_ports() {
  if [[ "${ALMANAC_DOCKER_AUTO_PORTS:-1}" == "0" ]]; then
    return 0
  fi

  local qmd_port=""
  local mcp_port=""
  local webhook_port=""
  local nextcloud_port=""
  local offset=0

  qmd_port="$(configured_or_default QMD_MCP_PORT 8181)"
  mcp_port="$(configured_or_default ALMANAC_MCP_PORT 8282)"
  webhook_port="$(configured_or_default ALMANAC_NOTION_WEBHOOK_PORT 8283)"
  nextcloud_port="$(configured_or_default NEXTCLOUD_PORT 18080)"

  if docker_port_set_available "$qmd_port" "$mcp_port" "$webhook_port" "$nextcloud_port"; then
    persist_docker_ports "$qmd_port" "$mcp_port" "$webhook_port" "$nextcloud_port"
    return 0
  fi

  for offset in $(seq 0 199); do
    qmd_port=$((18181 + offset))
    mcp_port=$((18282 + offset))
    webhook_port=$((18283 + offset))
    nextcloud_port=$((28080 + offset))
    if docker_port_set_available "$qmd_port" "$mcp_port" "$webhook_port" "$nextcloud_port"; then
      persist_docker_ports "$qmd_port" "$mcp_port" "$webhook_port" "$nextcloud_port"
      echo "Docker ports assigned: qmd=$qmd_port almanac-mcp=$mcp_port notion-webhook=$webhook_port nextcloud=$nextcloud_port"
      return 0
    fi
  done

  echo "Could not find an available Almanac Docker port block." >&2
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
  compose exec -T "$service" "$@" >/dev/null
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

  compose_exec_quiet "$service" "$@"
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
    echo "FAIL Docker Compose config is valid, but no Almanac services are running." >&2
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

  retry_compose_exec_quiet almanac-mcp curl -fsS http://127.0.0.1:8282/health
  retry_compose_exec_quiet notion-webhook curl -fsS http://127.0.0.1:8283/health
  retry_compose_exec_quiet nextcloud curl -fsS http://127.0.0.1/status.php
  retry_compose_exec_quiet qmd-mcp qmd --version
  retry_compose_exec_quiet redis redis-cli ping
  # shellcheck disable=SC2016
  retry_compose_exec_quiet postgres sh -lc 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
  compose exec -T health-watch ./bin/docker-health.sh
  echo "Docker health passed."
}

show_ports() {
  bootstrap >/dev/null
  if [[ -f "$DOCKER_PORT_MANIFEST" ]]; then
    python3 -m json.tool "$DOCKER_PORT_MANIFEST"
    return 0
  fi

  printf 'QMD_MCP_PORT=%s\n' "$(configured_or_default QMD_MCP_PORT 8181)"
  printf 'ALMANAC_MCP_PORT=%s\n' "$(configured_or_default ALMANAC_MCP_PORT 8282)"
  printf 'ALMANAC_NOTION_WEBHOOK_PORT=%s\n' "$(configured_or_default ALMANAC_NOTION_WEBHOOK_PORT 8283)"
  printf 'NEXTCLOUD_PORT=%s\n' "$(configured_or_default NEXTCLOUD_PORT 18080)"
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
  compose stop almanac-mcp ssot-batcher agent-supervisor >/dev/null 2>&1 || true
  compose_run_maybe_tty almanac-mcp ./deploy.sh notion-migrate "$@" || rc=$?
  echo "Restarting Docker Notion services."
  if ! compose up -d --no-build almanac-mcp ssot-batcher agent-supervisor notion-webhook; then
    return 1
  fi
  return "$rc"
}

docker_enrollment_status() {
  local onboarding_file="" provision_file="" supervisor_state="stopped" db_path=""

  onboarding_file="$(mktemp)"
  provision_file="$(mktemp)"
  if ! compose_app_command ./bin/almanac-ctl --json onboarding list >"$onboarding_file"; then
    rm -f "$onboarding_file" "$provision_file"
    return 1
  fi
  if ! compose_app_command ./bin/almanac-ctl --json provision list >"$provision_file"; then
    rm -f "$onboarding_file" "$provision_file"
    return 1
  fi

  if compose_service_running agent-supervisor; then
    supervisor_state="running"
  fi
  db_path="$REPO_DIR/almanac-priv/state/almanac-control.sqlite3"

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
  db_path="$REPO_DIR/almanac-priv/state/almanac-control.sqlite3"

  python3 - "$db_path" "$REPO_DIR/almanac-priv/state" "$selector_kind" "$selector_value" "$log_lines" <<'PY'
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
  compose exec -T agent-supervisor ./bin/almanac-enrollment-provision.sh || true
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

  purge_cmd=(./bin/almanac-ctl --json user purge-enrollment "$target_unix_user" --actor deploy-docker-enrollment-reset)
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
  compose_app_command ./bin/bootstrap-curator.sh
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

  echo "Almanac Docker: rotate Nextcloud credentials"
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
  ALMANAC_NEXTCLOUD_DB_PASSWORD="$new_postgres_password" \
    compose exec -T -e ALMANAC_NEXTCLOUD_DB_PASSWORD -u www-data nextcloud sh -eu -c \
      'php occ config:system:set dbpassword --type=string --value="$ALMANAC_NEXTCLOUD_DB_PASSWORD"' >/dev/null

  ALMANAC_NEXTCLOUD_DB_PASSWORD="$new_postgres_password" python3 - "$pg_user" <<'PY' | compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "$pg_user" -d "$pg_db"
import os
import sys


def ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


print(f"ALTER ROLE {ident(sys.argv[1])} PASSWORD {literal(os.environ['ALMANAC_NEXTCLOUD_DB_PASSWORD'])};")
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
  compose_app_command ./bin/almanac-ctl --json internal pin-upgrade-check
}

component_for_upgrade_command() {
  local command="$1"
  case "$command" in
    hermes-upgrade|hermes-upgrade-check) printf '%s\n' "hermes-agent" ;;
    qmd-upgrade|qmd-upgrade-check) printf '%s\n' "qmd" ;;
    nextcloud-upgrade|nextcloud-upgrade-check) printf '%s\n' "nextcloud" ;;
    postgres-upgrade|postgres-upgrade-check) printf '%s\n' "postgres" ;;
    redis-upgrade|redis-upgrade-check) printf '%s\n' "redis" ;;
    code-server-upgrade|code-server-upgrade-check) printf '%s\n' "code-server" ;;
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
  local component=""
  component="$(component_for_upgrade_command "$command")"
  if [[ -z "$component" ]]; then
    echo "Unsupported Docker component command: $command" >&2
    return 2
  fi
  env ALMANAC_COMPONENT_UPGRADE_MODE=docker "$SCRIPT_DIR/component-upgrade.sh" "$component" apply "$@"
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
        compose build almanac-app
      else
        compose build "$@"
      fi
      ;;
    up)
      prepare_compose
      compose up -d --no-build "$@"
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
    hermes-upgrade-check|qmd-upgrade-check|nextcloud-upgrade-check|postgres-upgrade-check|redis-upgrade-check|code-server-upgrade-check|nvm-upgrade-check|node-upgrade-check)
      docker_component_upgrade_check "$command" "$@"
      ;;
    hermes-upgrade|qmd-upgrade|nextcloud-upgrade|postgres-upgrade|redis-upgrade|code-server-upgrade|nvm-upgrade|node-upgrade)
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
