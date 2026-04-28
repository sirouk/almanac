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
    warn "$label could not be reached at $host:$port"
  fi
}

check_dir "$ALMANAC_PRIV_DIR" "Docker private state"
check_dir "$VAULT_DIR" "Docker vault"
check_dir "$STATE_DIR" "Docker state"
check_dir "$NEXTCLOUD_STATE_DIR" "Docker Nextcloud state"
check_dir "$PDF_INGEST_MARKDOWN_DIR" "Docker PDF ingest markdown"
check_dir "$ALMANAC_NOTION_INDEX_MARKDOWN_DIR" "Docker Notion index markdown"

check_http "http://almanac-mcp:8282/health" "Almanac MCP"
check_http "http://notion-webhook:8283/health" "Notion webhook"
check_http_with_host "http://nextcloud/status.php" "localhost" "Nextcloud"
check_optional_tcp "host.docker.internal" "${QMD_MCP_HOST_PORT:-${QMD_MCP_PORT:-8181}}" "qmd MCP published host port"
check_tcp "postgres" "5432" "Postgres"
check_tcp "redis" "6379" "Redis"

if qmd --version >/dev/null 2>&1; then
  pass "qmd CLI is available"
else
  fail "qmd CLI is unavailable"
fi

if [[ "${POSTGRES_PASSWORD:-}" == "change-me" || "${NEXTCLOUD_ADMIN_PASSWORD:-}" == "change-me" ]]; then
  warn "Docker bootstrap is using placeholder Nextcloud/Postgres secrets; rotate before any durable live use"
fi

printf 'Summary: %d ok, %d warn, %d fail\n' "$PASS_COUNT" "$WARN_COUNT" "$FAIL_COUNT"
if [[ "$FAIL_COUNT" -gt 0 ]]; then
  exit 1
fi
