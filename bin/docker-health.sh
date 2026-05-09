#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0

pass() {
  PASS_COUNT=$((PASS_COUNT + 1))
  printf '[ok]   %s\n' "$1"
}

warn() {
  WARN_COUNT=$((WARN_COUNT + 1))
  printf '[warn] %s\n' "$1"
}

fail() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  printf '[fail] %s\n' "$1"
}

check_dir() {
  local path="$1"
  local label="$2"
  if [[ -d "$path" ]]; then
    pass "$label exists"
  else
    fail "$label is missing at $path"
  fi
}

check_http() {
  local url="$1"
  local label="$2"
  if curl --max-time 5 -fsS "$url" >/dev/null 2>&1; then
    pass "$label responds"
  else
    fail "$label did not respond at $url"
  fi
}

check_http_with_host() {
  local url="$1"
  local host_header="$2"
  local label="$3"
  if curl --max-time 5 -fsS -H "Host: $host_header" "$url" >/dev/null 2>&1; then
    pass "$label responds"
  else
    fail "$label did not respond at $url"
  fi
}

check_tcp() {
  local host="$1"
  local port="$2"
  local label="$3"
  if python3 - "$host" "$port" <<'PY' >/dev/null 2>&1
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
with socket.create_connection((host, port), timeout=5):
    pass
PY
  then
    pass "$label accepts TCP connections"
  else
    fail "$label did not accept TCP connections at $host:$port"
  fi
}

check_optional_tcp() {
  local host="$1"
  local port="$2"
  local label="$3"
  if tcp_accepts "$host" "$port"; then
    pass "$label accepts TCP connections"
  else
    warn "$label could not be reached at $host:$port"
  fi
}

tcp_accepts() {
  local host="$1"
  local port="$2"
  python3 - "$host" "$port" <<'PY' >/dev/null 2>&1
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
with socket.create_connection((host, port), timeout=5):
    pass
PY
}

check_optional_tcp_with_fallback() {
  local primary_host="$1"
  local primary_port="$2"
  local fallback_host="$3"
  local fallback_port="$4"
  local label="$5"
  if tcp_accepts "$primary_host" "$primary_port"; then
    pass "$label accepts TCP connections at $primary_host:$primary_port"
    return
  fi
  if tcp_accepts "$fallback_host" "$fallback_port"; then
    pass "$label accepts TCP connections at $fallback_host:$fallback_port"
    return
  fi
  warn "$label could not be reached at $primary_host:$primary_port or $fallback_host:$fallback_port"
}

check_dir "$ARCLINK_PRIV_DIR" "Docker private state"
check_dir "$VAULT_DIR" "Docker vault"
check_dir "$STATE_DIR" "Docker state"
check_dir "$NEXTCLOUD_STATE_DIR" "Docker Nextcloud state"
check_dir "$PDF_INGEST_MARKDOWN_DIR" "Docker PDF ingest markdown"
check_dir "$ARCLINK_NOTION_INDEX_MARKDOWN_DIR" "Docker Notion index markdown"

check_http "http://arclink-mcp:8282/health" "ArcLink MCP"
check_http "http://notion-webhook:8283/health" "Notion webhook"
check_http_with_host "http://nextcloud/status.php" "localhost" "Nextcloud"
check_optional_tcp_with_fallback "qmd-mcp" "${QMD_MCP_CONTAINER_PORT:-8181}" "host.docker.internal" "${QMD_MCP_HOST_PORT:-${QMD_MCP_PORT:-8181}}" "qmd MCP runtime port"
check_tcp "postgres" "5432" "Postgres"
check_tcp "redis" "6379" "Redis"
check_tcp "control-ingress" "80" "Traefik ingress (HTTP)"
check_optional_tcp "control-ingress" "443" "Traefik ingress (HTTPS)"

check_docker_refresh_jobs() {
  local output=""
  if output="$(PYTHONPATH="$SCRIPT_DIR/../python${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
import datetime as dt
from arclink_control import Config, connect_db, parse_utc_iso

cfg = Config.from_env()
now = dt.datetime.now(dt.timezone.utc)
failures = 0
with connect_db(cfg) as conn:
    conn.row_factory = __import__("sqlite3").Row
    jobs = conn.execute(
        "SELECT job_name, last_run_at, last_status FROM refresh_jobs ORDER BY job_name"
    ).fetchall()
    if not jobs:
        print("OK no refresh jobs recorded yet")
        raise SystemExit(0)
    for job in jobs:
        name = str(job["job_name"] or "")
        status = str(job["last_status"] or "unknown")
        last_run = parse_utc_iso(str(job["last_run_at"] or ""))
        if last_run is None:
            print(f"WARN {name}: no valid last_run_at")
            continue
        age_h = (now - last_run).total_seconds() / 3600
        if status not in ("ok", "skipped"):
            print(f"FAIL {name}: last_status={status}")
            failures += 1
        elif age_h > 8:
            print(f"WARN {name}: stale ({age_h:.1f}h since last run)")
        else:
            print(f"OK {name}: {status} ({age_h:.1f}h ago)")
raise SystemExit(1 if failures else 0)
PY
  )"; then
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      case "$line" in
        OK\ *) pass "${line#OK }" ;;
        WARN\ *) warn "${line#WARN }" ;;
        *) pass "$line" ;;
      esac
    done <<<"$output"
  else
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      case "$line" in
        FAIL\ *) fail "${line#FAIL }" ;;
        WARN\ *) warn "${line#WARN }" ;;
        OK\ *) pass "${line#OK }" ;;
        *) fail "$line" ;;
      esac
    done <<<"$output"
  fi
}

check_docker_refresh_jobs

check_docker_job_status_files() {
  local job_status_dir="${ARCLINK_DOCKER_JOB_STATUS_DIR:-$STATE_DIR/docker/jobs}"
  if [[ ! -d "$job_status_dir" ]]; then
    fail "Docker job status directory not found at $job_status_dir"
    return
  fi
  local required_jobs=(
    control-provisioner
    control-action-worker
    ssot-batcher
    notification-delivery
    health-watch
    curator-refresh
    qmd-refresh
    pdf-ingest
    memory-synth
    hermes-docs-sync
  )
  local job_name="" status="" last_exit="" finished_at=""
  for job_name in "${required_jobs[@]}"; do
    local status_file="$job_status_dir/$job_name.json"
    if [[ ! -f "$status_file" ]]; then
      fail "Docker recurring job $job_name has no status file"
      continue
    fi
    local fields=""
    if ! fields="$(python3 - "$status_file" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print("unknown\terror\t1\t")
    raise SystemExit(0)
job_name = str(data.get("job_name") or data.get("job") or path.stem)
status = str(data.get("status") or "unknown")
last_exit = str(data.get("exit_code") if "exit_code" in data else data.get("returncode", 0))
finished_at = str(data.get("finished_at") or data.get("last_run_at") or "")
print("\t".join((job_name, status, last_exit, finished_at)))
PY
    )"; then
      fail "Docker job $job_name status file could not be parsed"
      continue
    fi
    IFS=$'\t' read -r job_name status last_exit finished_at <<<"$fields"
    case "$status" in
      ok|success)
        pass "Docker job $job_name: $status${finished_at:+ at $finished_at}" ;;
      skipped)
        pass "Docker job $job_name: skipped${finished_at:+ at $finished_at}" ;;
      error|failed|fail)
        fail "Docker job $job_name: $status (exit $last_exit)" ;;
      *)
        warn "Docker job $job_name: $status" ;;
    esac
  done
}

check_docker_job_status_files

if [[ -f "$ARCLINK_MEMORY_SYNTH_STATUS_FILE" ]]; then
  pass "memory synthesis status file exists"
else
  warn "memory synthesis status file not written yet"
fi

if qmd --version >/dev/null 2>&1; then
  pass "qmd CLI is available"
else
  fail "qmd CLI is unavailable"
fi

check_docker_agent_mcp_auth() {
  local output=""
  if output="$(PYTHONPATH="$SCRIPT_DIR/../python${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
import datetime as dt
from pathlib import Path

from arclink_control import Config, connect_db, parse_utc_iso, validate_token

cfg = Config.from_env()
now = dt.datetime.now(dt.timezone.utc)
failures = 0
with connect_db(cfg) as conn:
    conn.row_factory = __import__("sqlite3").Row
    agents = conn.execute(
        """
        SELECT agent_id, unix_user, display_name, hermes_home
        FROM agents
        WHERE role = 'user' AND status = 'active'
        ORDER BY unix_user
        """
    ).fetchall()
    if not agents:
        print("OK no active Docker user agents yet")
        raise SystemExit(0)

    for agent in agents:
        agent_id = str(agent["agent_id"] or "")
        unix_user = str(agent["unix_user"] or "")
        hermes_home = Path(str(agent["hermes_home"] or ""))
        token_file = hermes_home / "secrets" / "arclink-bootstrap-token"
        managed_context_plugin = hermes_home / "plugins" / "arclink-managed-context" / "plugin.yaml"
        soul_file = hermes_home / "SOUL.md"
        vault_reconciler_state = hermes_home / "state" / "arclink-vault-reconciler.json"
        if not managed_context_plugin.is_file():
            print(f"FAIL {agent_id}: Docker managed-context plugin is missing at {managed_context_plugin}")
            failures += 1
            continue
        if not soul_file.is_file():
            print(f"FAIL {agent_id}: Docker agent SOUL.md is missing at {soul_file}")
            failures += 1
            continue
        if not vault_reconciler_state.is_file():
            print(f"FAIL {agent_id}: Docker managed memory/vault refresh state is missing at {vault_reconciler_state}")
            failures += 1
            continue
        try:
            raw_token = token_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            print(f"FAIL {agent_id}: Docker agent MCP token file is unreadable at {token_file}: {exc}")
            failures += 1
            continue
        if not raw_token:
            print(f"FAIL {agent_id}: Docker agent MCP token file is empty at {token_file}")
            failures += 1
            continue
        try:
            token_row = validate_token(conn, raw_token)
        except Exception as exc:
            print(f"FAIL {agent_id}: Docker agent MCP token did not validate: {exc}")
            failures += 1
            continue
        if str(token_row["agent_id"] or "") != agent_id:
            print(f"FAIL {agent_id}: Docker agent MCP token belongs to {token_row['agent_id']}")
            failures += 1
            continue

        job = conn.execute(
            "SELECT last_run_at, last_status FROM refresh_jobs WHERE job_name = ?",
            (f"{agent_id}-refresh",),
        ).fetchone()
        if job is None or not job["last_run_at"]:
            print(f"FAIL {agent_id}: Docker user-agent refresh has not completed")
            failures += 1
            continue
        if str(job["last_status"] or "") != "ok":
            print(f"FAIL {agent_id}: Docker user-agent refresh last_status={job['last_status'] or 'unknown'}")
            failures += 1
            continue
        last_run = parse_utc_iso(str(job["last_run_at"] or ""))
        if last_run is None:
            print(f"FAIL {agent_id}: Docker user-agent refresh timestamp is invalid: {job['last_run_at']}")
            failures += 1
            continue
        if (now - last_run).total_seconds() > 8 * 3600:
            print(f"FAIL {agent_id}: Docker user-agent refresh stale since {job['last_run_at']}")
            failures += 1
            continue
        print(f"OK {agent_id}: unix_user={unix_user} Docker managed plugin/SOUL present, MCP token validates, and refresh={job['last_status']} at {job['last_run_at']}")

raise SystemExit(1 if failures else 0)
PY
  )"; then
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      case "$line" in
        OK\ *) pass "${line#OK }" ;;
        *) warn "$line" ;;
      esac
    done <<<"$output"
  else
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      case "$line" in
        FAIL\ *) fail "${line#FAIL }" ;;
        OK\ *) pass "${line#OK }" ;;
        *) fail "$line" ;;
      esac
    done <<<"$output"
  fi
}

check_docker_agent_mcp_auth

if [[ "${POSTGRES_PASSWORD:-}" == "change-me" || "${NEXTCLOUD_ADMIN_PASSWORD:-}" == "change-me" ]]; then
  warn "Docker bootstrap is using placeholder Nextcloud/Postgres secrets; rotate before any durable live use"
fi

printf 'Summary: %d ok, %d warn, %d fail\n' "$PASS_COUNT" "$WARN_COUNT" "$FAIL_COUNT"
if [[ "$FAIL_COUNT" -gt 0 ]]; then
  exit 1
fi
