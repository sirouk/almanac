#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEPLOY_BIN="$ROOT_DIR/bin/deploy.sh"
ALMANAC_NAME="${ALMANAC_SMOKE_NAME:-almanac}"
ALMANAC_USER="${ALMANAC_SMOKE_USER:-almanac}"
ALMANAC_HOME="${ALMANAC_SMOKE_HOME:-/home/$ALMANAC_USER}"
ALMANAC_REPO_DIR="$ALMANAC_HOME/almanac"
ALMANAC_PRIV_DIR="$ALMANAC_REPO_DIR/almanac-priv"
ALMANAC_PRIV_CONFIG_DIR="$ALMANAC_PRIV_DIR/config"
CONFIG_TARGET="$ALMANAC_PRIV_CONFIG_DIR/almanac.env"
STATE_DIR="$ALMANAC_PRIV_DIR/state"
RUNTIME_DIR="$STATE_DIR/runtime"
ALMANAC_DB_PATH="$STATE_DIR/almanac-control.sqlite3"
ALMANAC_AGENTS_STATE_DIR="$STATE_DIR/agents"
ALMANAC_CURATOR_DIR="$STATE_DIR/curator"
ALMANAC_CURATOR_MANIFEST="$ALMANAC_CURATOR_DIR/manifest.json"
ALMANAC_CURATOR_HERMES_HOME="$ALMANAC_CURATOR_DIR/hermes-home"
ALMANAC_ARCHIVED_AGENTS_DIR="$STATE_DIR/archived-agents"
QMD_INDEX_NAME="${ALMANAC_SMOKE_QMD_INDEX_NAME:-almanac}"
QMD_COLLECTION_NAME="${ALMANAC_SMOKE_QMD_COLLECTION_NAME:-vault}"
NEXTCLOUD_ADMIN_USER="${ALMANAC_SMOKE_NEXTCLOUD_ADMIN_USER:-admin}"
NEXTCLOUD_VAULT_MOUNT_POINT="/Vault"
PDF_INGEST_ENABLED="${PDF_INGEST_ENABLED:-1}"
PDF_INGEST_COLLECTION_NAME="vault-pdf-ingest"
QMD_MCP_PORT="${ALMANAC_SMOKE_QMD_MCP_PORT:-8181}"
NEXTCLOUD_PORT="${ALMANAC_SMOKE_NEXTCLOUD_PORT:-18080}"
ALMANAC_MCP_PORT="${ALMANAC_MCP_PORT:-8282}"
ALMANAC_NOTION_WEBHOOK_PORT="${ALMANAC_NOTION_WEBHOOK_PORT:-8283}"
ENABLE_TAILSCALE_SERVE="${ALMANAC_SMOKE_ENABLE_TAILSCALE_SERVE:-0}"
TAILSCALE_OPERATOR_USER="${ALMANAC_SMOKE_TAILSCALE_OPERATOR_USER:-${SUDO_USER:-}}"
AUTOPROV_UNIX_USER="${ALMANAC_SMOKE_AUTOPROV_USER:-autoprovbot}"
ANSWERS_FILE="$(mktemp /tmp/almanac-ci-install.XXXXXX.env)"
INSTALLED=0
LAST_QMD_SEARCH_OUTPUT=""
LAST_QMD_MCP_OUTPUT=""

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run this as root. In CI, use: sudo ./bin/ci-install-smoke.sh" >&2
  exit 1
fi

write_answers() {
  cat >"$ANSWERS_FILE" <<EOF
ALMANAC_NAME=$ALMANAC_NAME
ALMANAC_USER=$ALMANAC_USER
ALMANAC_HOME=$ALMANAC_HOME
ALMANAC_REPO_DIR=$ALMANAC_REPO_DIR
ALMANAC_PRIV_DIR=$ALMANAC_PRIV_DIR
ALMANAC_PRIV_CONFIG_DIR=$ALMANAC_PRIV_CONFIG_DIR
VAULT_DIR=$ALMANAC_PRIV_DIR/vault
STATE_DIR=$STATE_DIR
NEXTCLOUD_STATE_DIR=$STATE_DIR/nextcloud
RUNTIME_DIR=$RUNTIME_DIR
ALMANAC_DB_PATH=$ALMANAC_DB_PATH
ALMANAC_AGENTS_STATE_DIR=$ALMANAC_AGENTS_STATE_DIR
ALMANAC_CURATOR_DIR=$ALMANAC_CURATOR_DIR
ALMANAC_CURATOR_MANIFEST=$ALMANAC_CURATOR_MANIFEST
ALMANAC_CURATOR_HERMES_HOME=$ALMANAC_CURATOR_HERMES_HOME
ALMANAC_ARCHIVED_AGENTS_DIR=$ALMANAC_ARCHIVED_AGENTS_DIR
PUBLISHED_DIR=$ALMANAC_PRIV_DIR/published
QMD_INDEX_NAME=$QMD_INDEX_NAME
QMD_COLLECTION_NAME=$QMD_COLLECTION_NAME
VAULT_QMD_COLLECTION_MASK=**/*.{md,markdown,mdx,txt,text}
PDF_INGEST_COLLECTION_NAME=$PDF_INGEST_COLLECTION_NAME
QMD_RUN_EMBED=1
QMD_MCP_PORT=$QMD_MCP_PORT
ALMANAC_MCP_HOST=127.0.0.1
ALMANAC_MCP_PORT=$ALMANAC_MCP_PORT
ALMANAC_NOTION_WEBHOOK_HOST=127.0.0.1
ALMANAC_NOTION_WEBHOOK_PORT=$ALMANAC_NOTION_WEBHOOK_PORT
ALMANAC_BOOTSTRAP_WINDOW_SECONDS=3600
ALMANAC_BOOTSTRAP_PER_IP_LIMIT=5
ALMANAC_BOOTSTRAP_GLOBAL_PENDING_LIMIT=20
ALMANAC_BOOTSTRAP_PENDING_TTL_SECONDS=900
PDF_INGEST_ENABLED=1
PDF_INGEST_EXTRACTOR=auto
PDF_VISION_ENDPOINT=
PDF_VISION_MODEL=
PDF_VISION_API_KEY=
PDF_VISION_MAX_PAGES=6
VAULT_WATCH_DEBOUNCE_SECONDS=1
VAULT_WATCH_RUN_EMBED=auto
BACKUP_GIT_BRANCH=main
BACKUP_GIT_REMOTE=
BACKUP_GIT_AUTHOR_NAME=Almanac\ Backup
BACKUP_GIT_AUTHOR_EMAIL=almanac@localhost
NEXTCLOUD_PORT=$NEXTCLOUD_PORT
NEXTCLOUD_TRUSTED_DOMAIN=almanac-ci.local
POSTGRES_DB=nextcloud
POSTGRES_USER=nextcloud
POSTGRES_PASSWORD=almanac-ci-postgres
NEXTCLOUD_ADMIN_USER=$NEXTCLOUD_ADMIN_USER
NEXTCLOUD_ADMIN_PASSWORD=almanac-ci-admin
NEXTCLOUD_VAULT_MOUNT_POINT=$NEXTCLOUD_VAULT_MOUNT_POINT
ENABLE_NEXTCLOUD=1
ENABLE_TAILSCALE_SERVE=$ENABLE_TAILSCALE_SERVE
ALMANAC_AGENT_ENABLE_TAILSCALE_SERVE=$ENABLE_TAILSCALE_SERVE
TAILSCALE_OPERATOR_USER=$TAILSCALE_OPERATOR_USER
TAILSCALE_QMD_PATH=/mcp
ENABLE_PRIVATE_GIT=1
ENABLE_QUARTO=1
SEED_SAMPLE_VAULT=1
OPERATOR_NOTIFY_CHANNEL_PLATFORM=tui-only
OPERATOR_NOTIFY_CHANNEL_ID=
OPERATOR_GENERAL_CHANNEL_PLATFORM=
OPERATOR_GENERAL_CHANNEL_ID=
ALMANAC_MODEL_PRESET_CODEX=openai:codex
ALMANAC_MODEL_PRESET_OPUS=anthropic:claude-opus
ALMANAC_MODEL_PRESET_CHUTES=chutes:auto-failover
ALMANAC_CURATOR_MODEL_PRESET=codex
ALMANAC_CURATOR_CHANNELS=tui-only
CHUTES_MCP_URL=https://chutes.example.test/mcp
QUARTO_PROJECT_DIR=$ALMANAC_PRIV_DIR/quarto
QUARTO_OUTPUT_DIR=$ALMANAC_PRIV_DIR/published
ALMANAC_INSTALL_PUBLIC_GIT=1
REMOVE_PUBLIC_REPO=1
REMOVE_USER_TOOLING=1
REMOVE_SERVICE_USER=1
EOF
  chmod 600 "$ANSWERS_FILE"
}

load_answers_into_env() {
  set -a
  # shellcheck disable=SC1090
  source "$ANSWERS_FILE"
  set +a
}

wait_for_port() {
  local host="$1"
  local port="$2"
  local attempts="${3:-60}"
  local delay="${4:-2}"
  local i=""

  for ((i = 1; i <= attempts; i++)); do
    if python3 - "$host" "$port" <<'PY'
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(1.0)
try:
    sock.connect((host, port))
except OSError:
    raise SystemExit(1)
finally:
    sock.close()
PY
    then
      return 0
    fi
    sleep "$delay"
  done

  return 1
}

http_status_code() {
  local url="$1"
  local auth="${2:-}"
  local host_header="${3:-}"
  local curl_args=(
    --max-time 10
    -sS
    -o /dev/null
    -w '%{http_code}'
  )

  if [[ -n "$auth" ]]; then
    curl_args+=(-u "$auth")
  fi
  if [[ -n "$host_header" ]]; then
    curl_args+=(-H "Host: $host_header")
  fi

  curl "${curl_args[@]}" "$url"
}

wait_for_http_status() {
  local url="$1"
  local expected_csv="$2"
  local auth="${3:-}"
  local host_header="${4:-}"
  local attempts="${5:-120}"
  local delay="${6:-2}"
  local i=""
  local status=""

  for ((i = 1; i <= attempts; i++)); do
    status="$(http_status_code "$url" "$auth" "$host_header" 2>/dev/null || true)"
    if [[ ",$expected_csv," == *",$status,"* ]]; then
      return 0
    fi
    sleep "$delay"
  done

  echo "Expected $url to return one of [$expected_csv], last status was ${status:-<none>}." >&2
  return 1
}

wait_for_http_success() {
  local url="$1"
  local host_header="${2:-}"
  local output_file="${3:-/dev/null}"
  local attempts="${4:-120}"
  local delay="${5:-2}"
  local i=""
  local error_file=""

  error_file="$(mktemp /tmp/almanac-http-check.XXXXXX.log)"

  for ((i = 1; i <= attempts; i++)); do
    if [[ -n "$host_header" ]]; then
      if curl --max-time 5 -fsS -H "Host: $host_header" "$url" -o "$output_file" 2>"$error_file"; then
        rm -f "$error_file"
        return 0
      fi
    else
      if curl --max-time 5 -fsS "$url" -o "$output_file" 2>"$error_file"; then
        rm -f "$error_file"
        return 0
      fi
    fi

    if (( i == 1 || i % 10 == 0 )); then
      echo "Waiting for Nextcloud HTTP readiness ($i/$attempts)..."
    fi
    sleep "$delay"
  done

  echo "Nextcloud HTTP readiness probe failed after $attempts attempts." >&2
  if [[ -s "$error_file" ]]; then
    sed 's/^/  /' "$error_file" >&2
  fi
  rm -f "$error_file"
  return 1
}

wait_for_file() {
  local path="$1"
  local attempts="${2:-120}"
  local delay="${3:-1}"
  local i=""

  for ((i = 1; i <= attempts; i++)); do
    if [[ -f "$path" ]]; then
      return 0
    fi
    sleep "$delay"
  done

  return 1
}

wait_for_path_absent() {
  local path="$1"
  local attempts="${2:-120}"
  local delay="${3:-1}"
  local i=""

  for ((i = 1; i <= attempts; i++)); do
    if [[ ! -e "$path" ]]; then
      return 0
    fi
    sleep "$delay"
  done

  return 1
}

run_almanac_shell() {
  local user_cmd="$1"
  local wrapped=""

  wrapped="source '$ALMANAC_REPO_DIR/bin/common.sh'; ensure_nvm; ensure_uv; export ALMANAC_CONFIG_FILE='$CONFIG_TARGET'; $user_cmd"
  su - "$ALMANAC_USER" -c "bash -lc $(printf '%q' "$wrapped")"
}

shell_join() {
  local joined=""
  local arg=""
  for arg in "$@"; do
    if [[ -n "$joined" ]]; then
      joined+=" "
    fi
    joined+="$(printf '%q' "$arg")"
  done
  printf '%s' "$joined"
}

run_login_user_command() {
  local unix_user="$1"
  shift
  su - "$unix_user" -c "$(shell_join "$@")"
}

run_login_user_systemctl() {
  local unix_user="$1"
  shift
  local uid=""

  uid="$(id -u "$unix_user")"
  run_login_user_command \
    "$unix_user" \
    env \
    "XDG_RUNTIME_DIR=/run/user/$uid" \
    "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$uid/bus" \
    systemctl \
    --user \
    "$@"
}

wait_for_qmd_search_match() {
  local query="$1"
  local expected="$2"
  local collection="${3:-$QMD_COLLECTION_NAME}"
  local attempts="${4:-120}"
  local delay="${5:-1}"
  local i=""

  for ((i = 1; i <= attempts; i++)); do
    LAST_QMD_SEARCH_OUTPUT="$(
      run_almanac_shell \
        "qmd --index '$QMD_INDEX_NAME' search '$query' --files -c '$collection'" \
        2>&1 || true
    )"
    if grep -Fq "$expected" <<<"$LAST_QMD_SEARCH_OUTPUT"; then
      return 0
    fi
    sleep "$delay"
  done

  return 1
}

wait_for_qmd_search_absent() {
  local query="$1"
  local unexpected="$2"
  local collection="${3:-$QMD_COLLECTION_NAME}"
  local attempts="${4:-120}"
  local delay="${5:-1}"
  local i=""

  for ((i = 1; i <= attempts; i++)); do
    LAST_QMD_SEARCH_OUTPUT="$(
      run_almanac_shell \
        "qmd --index '$QMD_INDEX_NAME' search '$query' --files -c '$collection'" \
        2>&1 || true
    )"
    if ! grep -Fq "$unexpected" <<<"$LAST_QMD_SEARCH_OUTPUT"; then
      return 0
    fi
    sleep "$delay"
  done

  return 1
}

wait_for_qmd_pending_embeddings_zero() {
  local attempts="${1:-120}"
  local delay="${2:-1}"
  local i=""
  local pending=""

  for ((i = 1; i <= attempts; i++)); do
    pending="$(
      run_almanac_shell \
        "qmd_pending_embeddings_count" \
        2>/dev/null || printf '0\n'
    )"
    pending="${pending##*$'\n'}"
    pending="${pending//[[:space:]]/}"
    if [[ "$pending" =~ ^[0-9]+$ ]] && (( pending == 0 )); then
      return 0
    fi
    sleep "$delay"
  done

  return 1
}

wait_for_user_unit_active() {
  local unix_user="$1"
  local unit_name="$2"
  local attempts="${3:-120}"
  local delay="${4:-2}"
  local uid=""
  local i=""
  local state=""

  uid="$(id -u "$unix_user")"
  for ((i = 1; i <= attempts; i++)); do
    state="$(run_login_user_systemctl "$unix_user" is-active "$unit_name" 2>/dev/null || true)"
    if [[ "$state" == "active" ]]; then
      return 0
    fi
    sleep "$delay"
  done

  echo "Expected user unit $unit_name for $unix_user to become active, saw ${state:-<none>}." >&2
  run_login_user_systemctl "$unix_user" status "$unit_name" -n 80 --no-pager >&2 || true
  return 1
}

assert_agent_access_surfaces() {
  local unix_user="$1"
  local agent_id="$2"
  local hermes_home="$3"
  local access_file="$hermes_home/state/almanac-web-access.json"
  local username="" password="" dashboard_backend_port="" dashboard_proxy_port="" code_port="" dashboard_url="" code_url="" dashboard_label="" code_label="" code_container_name="" code_server_image=""
  local before_signature="" after_signature="" home_dir="" uid=""
  local podman_bin=""

  wait_for_file "$access_file" 240 2
  eval "$(
    python3 - "$access_file" <<'PY'
import json
import shlex
import sys
from pathlib import Path

state = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for key in (
    "username",
    "password",
    "dashboard_backend_port",
    "dashboard_proxy_port",
    "code_port",
    "dashboard_url",
    "code_url",
    "dashboard_label",
    "code_label",
    "code_container_name",
    "code_server_image",
):
    print(f"{key}={shlex.quote(str(state.get(key, '')))}")
PY
  )"

  if [[ -z "$username" || -z "$password" ]]; then
    echo "Expected dashboard/code credentials to be written for $agent_id." >&2
    return 1
  fi
  if [[ "$username" != "$unix_user" ]]; then
    echo "Expected cleaned access username to match unix user for $agent_id: $username vs $unix_user" >&2
    return 1
  fi
  if [[ ! "$username" =~ ^[a-z0-9_-]+$ ]]; then
    echo "Expected cleaned access username for $agent_id, saw: $username" >&2
    return 1
  fi

  wait_for_port 127.0.0.1 "$dashboard_backend_port" 120 2
  wait_for_port 127.0.0.1 "$dashboard_proxy_port" 180 2
  wait_for_port 127.0.0.1 "$code_port" 300 2
  wait_for_user_unit_active "$unix_user" "almanac-user-agent-dashboard.service" 120 2
  wait_for_user_unit_active "$unix_user" "almanac-user-agent-dashboard-proxy.service" 120 2
  wait_for_user_unit_active "$unix_user" "almanac-user-agent-code.service" 180 2

  wait_for_http_status "http://127.0.0.1:$dashboard_proxy_port/" "401" "" "" 90 2
  wait_for_http_status "http://127.0.0.1:$dashboard_proxy_port/" "200" "$username:$password" "" 90 2
  wait_for_http_status "http://127.0.0.1:$dashboard_proxy_port/api/status" "200" "$username:$password" "" 90 2
  wait_for_http_status "http://127.0.0.1:$code_port/" "200,302,303" "" "" 180 2

  before_signature="$(
    python3 - "$access_file" <<'PY'
import json
import sys
from pathlib import Path

state = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print("|".join(str(state.get(key, "")) for key in ("username", "password", "dashboard_backend_port", "dashboard_proxy_port", "code_port")))
PY
  )"

  ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$ALMANAC_REPO_DIR/bin/almanac-ctl" user sync-access "$unix_user" --agent-id "$agent_id" >/dev/null
  wait_for_user_unit_active "$unix_user" "almanac-user-agent-dashboard.service" 120 2
  wait_for_user_unit_active "$unix_user" "almanac-user-agent-dashboard-proxy.service" 120 2
  wait_for_user_unit_active "$unix_user" "almanac-user-agent-code.service" 180 2

  after_signature="$(
    python3 - "$access_file" <<'PY'
import json
import sys
from pathlib import Path

state = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print("|".join(str(state.get(key, "")) for key in ("username", "password", "dashboard_backend_port", "dashboard_proxy_port", "code_port")))
PY
  )"
  if [[ "$before_signature" != "$after_signature" ]]; then
    echo "Expected agent access state to remain stable across sync-access for $agent_id." >&2
    echo "before: $before_signature" >&2
    echo "after:  $after_signature" >&2
    return 1
  fi

  home_dir="$(getent passwd "$unix_user" | cut -d: -f6)"
  uid="$(id -u "$unix_user")"
  podman_bin="$(command -v podman || true)"
  if [[ -z "$podman_bin" ]]; then
    podman_bin="/usr/bin/podman"
  fi
  python3 - "$(
    run_login_user_command "$unix_user" "$podman_bin" inspect "$code_container_name"
  )" "$home_dir" "$password" "$code_server_image" <<'PY'
import json
import sys

inspect_json, home_dir, password, image_name = sys.argv[1:5]
payload = json.loads(inspect_json)
if not payload:
    raise SystemExit("expected podman inspect data for code container")
container = payload[0]
state = container.get("State") or {}
if state.get("Status") != "running":
    raise SystemExit(f"expected code container running, saw {state.get('Status')!r}")
mounts = container.get("Mounts") or []
if not any(mount.get("Destination") == "/workspace" and mount.get("Source") == home_dir for mount in mounts):
    raise SystemExit(f"expected /workspace bind mount from {home_dir}")
env = (container.get("Config") or {}).get("Env") or []
if f"PASSWORD={password}" not in env:
    raise SystemExit("expected code container PASSWORD env to match shared access password")
image = container.get("ImageName") or ""
if image_name and image_name not in image:
    raise SystemExit(f"expected code container image {image_name!r}, saw {image!r}")
cmd = " ".join((container.get("Config") or {}).get("Cmd") or [])
for marker in ("--auth", "password", "/workspace"):
    if marker not in cmd:
        raise SystemExit(f"expected code-server command marker {marker!r}, saw {cmd!r}")
PY

  if [[ "$ENABLE_TAILSCALE_SERVE" == "1" ]]; then
    python3 - "$dashboard_url" "$code_url" "$dashboard_label" "$code_label" <<'PY'
import sys

dashboard_url, code_url, dashboard_label, code_label = sys.argv[1:5]
for url, label in ((dashboard_url, dashboard_label), (code_url, code_label)):
    if not url.startswith("https://") or f"/{label}/" not in url:
        raise SystemExit(f"expected tailscale https URL for path label {label!r}, saw {url!r}")
PY
    wait_for_http_status "$dashboard_url" "401" "" "" 90 2
    wait_for_http_status "$dashboard_url" "200" "$username:$password" "" 90 2
    wait_for_http_status "${dashboard_url}api/status" "200" "$username:$password" "" 90 2
    wait_for_http_status "$code_url" "200,302,303" "" "" 180 2
  else
    python3 - "$dashboard_url" "$code_url" "$dashboard_proxy_port" "$code_port" <<'PY'
import sys

dashboard_url, code_url, dashboard_port, code_port = sys.argv[1:5]
expected = (
    (dashboard_url, dashboard_port),
    (code_url, code_port),
)
for url, port in expected:
    target = f"http://127.0.0.1:{port}/"
    if url != target:
        raise SystemExit(f"expected local URL {target!r}, saw {url!r}")
PY
  fi

  run_login_user_systemctl "$unix_user" is-enabled almanac-user-agent-dashboard.service >/dev/null
  run_login_user_systemctl "$unix_user" is-enabled almanac-user-agent-dashboard-proxy.service >/dev/null
  run_login_user_systemctl "$unix_user" is-enabled almanac-user-agent-code.service >/dev/null
}

qmd_mcp_query_files() {
  local query="$1"
  local collection="${2:-$QMD_COLLECTION_NAME}"

  python3 - "$QMD_MCP_PORT" "$query" "$collection" <<'PY'
import json
import sys
import urllib.request

port = int(sys.argv[1])
query = sys.argv[2]
collection = sys.argv[3]
url = f"http://127.0.0.1:{port}/mcp"
headers = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def rpc(payload, session_id=None):
    request_headers = dict(headers)
    if session_id:
        request_headers["mcp-session-id"] = session_id
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=request_headers)
    with urllib.request.urlopen(request, timeout=15) as response:
        body = response.read().decode("utf-8", errors="replace")
        parsed = json.loads(body) if body.strip() else {}
        return response.headers.get("mcp-session-id") or session_id, parsed


session_id, _ = rpc(
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "almanac-smoke", "version": "1.0"},
        },
    }
)
rpc({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}, session_id)
_, body = rpc(
    {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "query",
            "arguments": {
                "searches": [{"type": "lex", "query": query}],
                "collections": [collection],
                "intent": "Almanac smoke test verification",
                "rerank": False,
                "limit": 10,
            },
        },
    },
    session_id,
)

results = (((body or {}).get("result") or {}).get("structuredContent") or {}).get("results") or []
collection_prefix = collection.lower().strip("/") + "/"
for result in results:
    file_path = str(result.get("file") or "").strip()
    if file_path:
        normalized = file_path.lower()
        if normalized.startswith("qmd://"):
            normalized = normalized[len("qmd://"):]
        if normalized.startswith(collection_prefix):
            normalized = normalized[len(collection_prefix):]
        print(normalized)
PY
}

wait_for_mcp_query_match() {
  local query="$1"
  local expected="$2"
  local collection="${3:-$QMD_COLLECTION_NAME}"
  local attempts="${4:-120}"
  local delay="${5:-1}"
  local i=""

  for ((i = 1; i <= attempts; i++)); do
    LAST_QMD_MCP_OUTPUT="$(qmd_mcp_query_files "$query" "$collection" 2>&1 || true)"
    if grep -Fq "$expected" <<<"$LAST_QMD_MCP_OUTPUT"; then
      return 0
    fi
    sleep "$delay"
  done

  return 1
}

wait_for_mcp_query_absent() {
  local query="$1"
  local unexpected="$2"
  local collection="${3:-$QMD_COLLECTION_NAME}"
  local attempts="${4:-120}"
  local delay="${5:-1}"
  local i=""

  for ((i = 1; i <= attempts; i++)); do
    LAST_QMD_MCP_OUTPUT="$(qmd_mcp_query_files "$query" "$collection" 2>&1 || true)"
    if ! grep -Fq "$unexpected" <<<"$LAST_QMD_MCP_OUTPUT"; then
      return 0
    fi
    sleep "$delay"
  done

  return 1
}

assert_mcp_status_alignment() {
  local expected_docs=""

  expected_docs="$(find "$ALMANAC_PRIV_DIR/vault" -type f \( -iname '*.md' -o -iname '*.markdown' -o -iname '*.mdx' -o -iname '*.txt' -o -iname '*.text' \) | wc -l | tr -d ' ')"

  if [[ "$expected_docs" == "0" ]]; then
    return 0
  fi

  if ! python3 - "$QMD_MCP_PORT" "$expected_docs" <<'PY'
import json
import sys
import urllib.request

port = int(sys.argv[1])
expected_docs = int(sys.argv[2])
url = f"http://127.0.0.1:{port}/mcp"
headers = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def rpc(payload, session_id=None):
    request_headers = dict(headers)
    if session_id:
        request_headers["mcp-session-id"] = session_id
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=request_headers)
    with urllib.request.urlopen(request, timeout=15) as response:
        body = response.read().decode("utf-8", errors="replace")
        parsed = json.loads(body) if body.strip() else {}
        return response.headers.get("mcp-session-id") or session_id, parsed


session_id, _ = rpc(
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "almanac-smoke", "version": "1.0"},
        },
    }
)
rpc({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}, session_id)
_, body = rpc(
    {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "status", "arguments": {}},
    },
    session_id,
)

structured = ((body or {}).get("result") or {}).get("structuredContent") or {}
total_documents = int(structured.get("totalDocuments", 0))
collection_count = len(structured.get("collections") or [])

if total_documents < 1 or collection_count < 1:
    print(
        f"Expected qmd MCP to expose the seeded index, but it reported "
        f"{total_documents} document(s) across {collection_count} collection(s) "
        f"while the shared vault has at least {expected_docs} direct text file(s)."
    )
    raise SystemExit(1)
PY
  then
    echo "Expected qmd MCP status to align with the seeded vault." >&2
    return 1
  fi
}

show_nextcloud_diagnostics() {
  local containers=""
  local prefix=""

  echo
  echo "Nextcloud diagnostics..."
  su - "$ALMANAC_USER" -c "podman pod ps" || true
  su - "$ALMANAC_USER" -c "podman ps --all --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'" || true

  prefix="${ALMANAC_NAME:-almanac}-nextcloud"
  containers="$(su - "$ALMANAC_USER" -c "podman ps --all --format '{{.Names}}'" 2>/dev/null | grep -E \"^(compose_|${prefix})\" || true)"
  if [[ -z "$containers" ]]; then
    echo "No Nextcloud containers found."
    return 0
  fi

  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    echo
    echo "Logs: $name"
    su - "$ALMANAC_USER" -c "podman logs --tail 120 '$name'" || true
  done <<<"$containers"
}

show_pdf_ingest_diagnostics() {
  local uid=""

  echo
  echo "PDF ingest diagnostics..."
  uid="$(id -u "$ALMANAC_USER")"

  if [[ -f "$ALMANAC_PRIV_DIR/state/pdf-ingest/status.json" ]]; then
    echo "Status:"
    sed 's/^/  /' "$ALMANAC_PRIV_DIR/state/pdf-ingest/status.json" || true
  fi

  echo "Generated markdown tree:"
  find "$ALMANAC_PRIV_DIR/state/pdf-ingest/markdown" -maxdepth 5 -type f | sed 's/^/  /' || true

  echo "QMD collection:"
  run_almanac_shell "qmd --index '$QMD_INDEX_NAME' collection show '$PDF_INGEST_COLLECTION_NAME'" || true

  if [[ -S "/run/user/$uid/bus" ]]; then
    su - "$ALMANAC_USER" -c "env XDG_RUNTIME_DIR='/run/user/$uid' DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/$uid/bus' systemctl --user --no-pager --full status almanac-vault-watch.service almanac-pdf-ingest.service almanac-pdf-ingest.timer" || true
    su - "$ALMANAC_USER" -c "env XDG_RUNTIME_DIR='/run/user/$uid' DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/$uid/bus' journalctl --user -u almanac-vault-watch.service -u almanac-pdf-ingest.service -n 120 --no-pager" || true
  fi
}

assert_agent_payload() {
  local payload=""
  local payload_file=""
  local required=""
  local payload_len=""
  local payload_file_len=""

  payload="$(ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$ALMANAC_REPO_DIR/deploy.sh" agent-payload)"
  payload_file="$ALMANAC_PRIV_DIR/state/agent-install-payload.txt"
  payload_len="$(printf '%s' "$payload" | wc -c | tr -d ' ')"

  for required in \
    "almanac_task_v1:" \
    "goal: enroll one shared-host user agent with explicit hermes setup, default Almanac skills, almanac-mcp + qmd + chutes MCP registration, first-contact vault defaults, and exactly one 4h refresh timer" \
    "almanac_mcp_url:" \
    "hermes mcp add almanac-qmd" \
    "hermes mcp add almanac-mcp" \
    "run hermes setup explicitly for model preset selection and optional Discord or Telegram gateway setup" \
    "first contact must resolve YAML .vault defaults" \
    "maintain only [managed:almanac-skill-ref], [managed:vault-ref], [managed:qmd-ref], [managed:vault-topology]" \
    "MEMORY.md is a frozen snapshot at session start" \
    "Almanac skills are active defaults, not passive extras" \
    "qmd first for private/shared-vault questions or follow-ups from the current discussion; use mixed lex+vec retrieval" \
    "if cron lacks the native memory tool, patch only those four entries in \$HERMES_HOME/memories/MEMORY.md" \
    "recurring success output: exactly 1 short line" \
    "recurring warn/fail output: at most 2 short lines" \
    "$ALMANAC_REPO_DIR/skills/almanac-qmd-mcp" \
    "$ALMANAC_REPO_DIR/skills/almanac-vault-reconciler" \
    "$ALMANAC_REPO_DIR/skills/almanac-first-contact" \
    "$ALMANAC_REPO_DIR/skills/almanac-vaults" \
    "$ALMANAC_REPO_DIR/skills/almanac-ssot"
  do
    if ! grep -Fq "$required" <<<"$payload"; then
      echo "Agent payload is missing expected text: $required" >&2
      printf '%s\n' "$payload" >&2
      return 1
    fi
  done

  if (( payload_len > 5200 )); then
    echo "Agent payload is too large for a single Telegram message: ${payload_len} bytes" >&2
    return 1
  fi

  if [[ ! -f "$payload_file" ]]; then
    echo "Expected canonical agent payload file at $payload_file" >&2
    return 1
  fi

  payload_file_len="$(wc -c <"$payload_file" | tr -d ' ')"

  for required in \
    "almanac_task_v1:" \
    "goal: enroll one shared-host user agent with explicit hermes setup, default Almanac skills, almanac-mcp + qmd + chutes MCP registration, first-contact vault defaults, and exactly one 4h refresh timer" \
    "MEMORY.md is a frozen snapshot at session start" \
    "first contact must resolve YAML .vault defaults" \
    "Almanac skills are active defaults, not passive extras" \
    "qmd first for private/shared-vault questions or follow-ups from the current discussion; use mixed lex+vec retrieval" \
    "if cron lacks the native memory tool, patch only those four entries in \$HERMES_HOME/memories/MEMORY.md" \
    "recurring success output: exactly 1 short line"
  do
    if ! grep -Fq "$required" "$payload_file"; then
      echo "Canonical agent payload file is missing expected text: $required" >&2
      sed -n '1,220p' "$payload_file" >&2
      return 1
    fi
  done

  if (( payload_file_len > 4800 )); then
    echo "Canonical agent payload file is too large for a single Telegram message: ${payload_file_len} bytes" >&2
    sed -n '1,220p' "$payload_file" >&2
    return 1
  fi
}

assert_default_vault_bootstrap_layout() {
  python3 - "$ALMANAC_REPO_DIR" "$VAULT_DIR" <<'PY'
import sys
from pathlib import Path

repo_dir = Path(sys.argv[1])
vault_dir = Path(sys.argv[2])
required_dirs = ["Research", "Skills", "Projects", "Repos"]
for name in required_dirs:
    target = vault_dir / name
    if not target.is_dir():
        raise SystemExit(f"expected default vault directory to exist: {target}")
    for rel in (".vault", "README.md"):
        path = target / rel
        if not path.is_file():
            raise SystemExit(f"expected default vault file to exist: {path}")

for legacy in ("Inbox", "People", "Teams"):
    if (vault_dir / legacy).exists():
        raise SystemExit(f"expected legacy default vault to be absent after bootstrap: {vault_dir / legacy}")

repo_note = vault_dir / "Repos" / "almanac.md"
if not repo_note.is_file():
    raise SystemExit(f"expected repo starter note: {repo_note}")
project_note = vault_dir / "Projects" / "almanac.md"
if not project_note.is_file():
    raise SystemExit(f"expected project starter note: {project_note}")

skills_dir = repo_dir / "skills"
missing = []
for skill_dir in sorted(path for path in skills_dir.iterdir() if path.is_dir() and (path / "SKILL.md").is_file()):
    note = vault_dir / "Skills" / f"{skill_dir.name}.md"
    if not note.is_file():
        missing.append(note.name)
if missing:
    raise SystemExit(f"expected shipped skill starter notes, missing: {', '.join(missing)}")
PY
}

assert_vault_definition_reload() {
  local docs_dir="$VAULT_DIR/TeamDocs"
  local nested_dir="$docs_dir/Compliance"
  local malformed_dir="$VAULT_DIR/TeamForms"
  local scan_json=""

  mkdir -p "$nested_dir" "$malformed_dir"
  cat >"$docs_dir/.vault" <<'EOF'
name: Team Docs
description: Shared rollout documentation
owner: smoke
default_subscribed: true
tags:
  - docs
category: docs
EOF
  cat >"$nested_dir/.vault" <<'EOF'
name: Team Compliance
description: Nested vault should be rejected in v1
owner: smoke
default_subscribed: false
EOF
  cat >"$malformed_dir/.vault" <<'EOF'
name: Team Forms
description: Broken vault file for smoke coverage
owner: smoke
default_subscribed: maybe
EOF
  chown -R "$ALMANAC_USER:$ALMANAC_USER" "$docs_dir" "$malformed_dir"

  scan_json="$(
    run_almanac_shell \
      "PYTHONPATH='$ALMANAC_REPO_DIR/python' python3 '$ALMANAC_REPO_DIR/python/almanac_ctl.py' --json vault reload-defs"
  )"

  python3 - "$scan_json" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
active_names = {row["vault_name"] for row in payload.get("active_vaults", [])}
warnings = payload.get("warnings", [])

if "Team Docs" not in active_names:
    raise SystemExit("expected Team Docs to be active after reloading .vault definitions")
if not any("nested .vault is invalid in v1" in warning for warning in warnings):
    raise SystemExit("expected nested .vault warning during reload-defs")
if not any("default_subscribed must be true or false" in warning for warning in warnings):
    raise SystemExit("expected malformed .vault warning during reload-defs")
PY
}

assert_almanac_control_plane_roundtrip() {
  local status_json=""
  local request_json=""
  local request_id=""
  local approve_json=""
  local poll_json=""
  local token=""
  local register_json=""
  local agent_id=""
  local refresh_json=""
  local token_list_json=""
  local revoke_output=""
  local refresh_error=""
  local smoke_home="/tmp/almanac-smoke-agent-home"

  mkdir -p "$smoke_home/secrets"
  chown -R "$ALMANAC_USER:$ALMANAC_USER" "$smoke_home"
  run_almanac_shell \
    "'$ALMANAC_REPO_DIR/bin/install-almanac-skills.sh' '$ALMANAC_REPO_DIR' '$smoke_home'" >/dev/null

  status_json="$(
    run_almanac_shell \
      "'$ALMANAC_REPO_DIR/bin/almanac-rpc' --url 'http://127.0.0.1:$ALMANAC_MCP_PORT/mcp' --tool status"
  )"
  python3 - "$status_json" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
if payload.get("service") != "almanac-mcp":
    raise SystemExit("unexpected almanac-mcp status payload")
PY

  request_json="$(
    run_almanac_shell \
      "'$ALMANAC_REPO_DIR/bin/almanac-rpc' --url 'http://127.0.0.1:$ALMANAC_MCP_PORT/mcp' --tool 'bootstrap.request' --json-args '{\"requester_identity\":\"Smoke Bot\",\"unix_user\":\"smokebot\",\"source_ip\":\"127.0.0.1\"}'"
  )"
  request_id="$(python3 - "$request_json" <<'PY'
import json
import sys

print(json.loads(sys.argv[1])["request_id"])
PY
)"
  if [[ -z "$request_id" ]]; then
    echo "Expected bootstrap.request to return a request_id." >&2
    exit 1
  fi

  approve_json="$(
    run_almanac_shell \
      "'$ALMANAC_REPO_DIR/bin/almanac-ctl' --json request approve '$request_id' --surface ctl --actor smoke-test"
  )"
  python3 - "$approve_json" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
if payload.get("approved_by_surface") != "ctl":
    raise SystemExit("expected approval audit surface to be ctl")
PY

  poll_json="$(
    run_almanac_shell \
      "'$ALMANAC_REPO_DIR/bin/almanac-rpc' --url 'http://127.0.0.1:$ALMANAC_MCP_PORT/mcp' --tool 'bootstrap.status' --json-args '{\"request_id\":\"$request_id\"}'"
  )"
  token="$(python3 - "$poll_json" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
print(payload["raw_token"])
PY
)"
  if [[ -z "$token" ]]; then
    echo "Expected bootstrap.status to return a raw token after approval." >&2
    exit 1
  fi
  printf '%s\n' "$token" >"$smoke_home/secrets/almanac-bootstrap-token"
  chmod 600 "$smoke_home/secrets/almanac-bootstrap-token"
  chown "$ALMANAC_USER:$ALMANAC_USER" "$smoke_home/secrets/almanac-bootstrap-token"

  register_json="$(
    run_almanac_shell \
      "'$ALMANAC_REPO_DIR/bin/almanac-rpc' --url 'http://127.0.0.1:$ALMANAC_MCP_PORT/mcp' --tool 'agents.register' --json-args '{\"token\":\"$token\",\"unix_user\":\"smokebot\",\"display_name\":\"Smoke Bot\",\"role\":\"user\",\"hermes_home\":\"$smoke_home\",\"model_preset\":\"codex\",\"model_string\":\"openai:codex\",\"channels\":[\"tui-only\"]}'"
  )"
  agent_id="$(python3 - "$register_json" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
allowed = {item["name"] for item in payload.get("allowed_mcps", [])}
expected = {"almanac-mcp", "almanac-qmd", "chutes-kb"}
missing = sorted(expected - allowed)
if missing:
    raise SystemExit(f"missing default MCP registrations in register response: {missing}")
print(payload["agent_id"])
PY
)"

  refresh_json="$(
    run_almanac_shell \
      "'$ALMANAC_REPO_DIR/bin/almanac-rpc' --url 'http://127.0.0.1:$ALMANAC_MCP_PORT/mcp' --tool 'vaults.refresh' --json-args '{\"token\":\"$token\"}'"
  )"
  python3 - "$refresh_json" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
if "Team Docs" not in payload.get("active_subscriptions", []):
    raise SystemExit("expected default_subscribed vault to appear in active_subscriptions after refresh")
PY

  token_list_json="$(
    run_almanac_shell \
      "'$ALMANAC_REPO_DIR/bin/almanac-ctl' --json token list"
  )"
  python3 - "$token_list_json" "$agent_id" <<'PY'
import json
import sys

tokens = json.loads(sys.argv[1])
agent_id = sys.argv[2]
matches = [row for row in tokens if row["agent_id"] == agent_id]
if not matches:
    raise SystemExit("expected hashed bootstrap token row for smoke agent")
if any("raw_token" in row for row in matches):
    raise SystemExit("raw tokens must not be stored in token list output")
PY

  revoke_output="$(
    run_almanac_shell \
      "'$ALMANAC_REPO_DIR/bin/almanac-ctl' --json token revoke '$agent_id' --surface ctl --actor smoke-test --reason 'smoke revoke'"
  )"
  python3 - "$revoke_output" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
if int(payload.get("revoked", 0)) < 1:
    raise SystemExit("expected token revoke to revoke at least one token")
PY

  refresh_error="$(mktemp)"
  if run_almanac_shell \
    "'$ALMANAC_REPO_DIR/bin/almanac-rpc' --url 'http://127.0.0.1:$ALMANAC_MCP_PORT/mcp' --tool 'vaults.refresh' --json-args '{\"token\":\"$token\"}'" \
    > /tmp/almanac-refresh-after-revoke.out 2>"$refresh_error"; then
    echo "Expected vaults.refresh to reject revoked token." >&2
    cat /tmp/almanac-refresh-after-revoke.out >&2
    rm -f "$refresh_error" /tmp/almanac-refresh-after-revoke.out
    exit 1
  fi
  if ! grep -Eq "revoked|missing" "$refresh_error"; then
    echo "Expected revoked-token refresh failure to mention revocation." >&2
    cat "$refresh_error" >&2
    rm -f "$refresh_error" /tmp/almanac-refresh-after-revoke.out
    exit 1
  fi
  rm -f "$refresh_error" /tmp/almanac-refresh-after-revoke.out
}

assert_async_bootstrap_handshake() {
  local handshake_json="" duplicate_json="" request_id="" token="" token_id="" pending_err="" status_json="" refresh_json=""
  local activation_trigger_path=""

  handshake_json="$(
    run_almanac_shell \
      "'$ALMANAC_REPO_DIR/bin/almanac-rpc' --url 'http://127.0.0.1:$ALMANAC_MCP_PORT/mcp' --tool 'bootstrap.handshake' --json-args '{\"requester_identity\":\"Async Bot\",\"unix_user\":\"asyncbot\",\"source_ip\":\"127.0.0.1\"}'"
  )"
  read -r request_id token token_id <<EOF
$(python3 - "$handshake_json" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
print(payload["request_id"], payload["raw_token"], payload["token_id"])
PY
)
EOF

  if [[ -z "$request_id" || -z "$token" || -z "$token_id" ]]; then
    echo "Expected bootstrap.handshake to return request_id, raw_token, and token_id." >&2
    exit 1
  fi

  duplicate_json="$(
    run_almanac_shell \
      "'$ALMANAC_REPO_DIR/bin/almanac-rpc' --url 'http://127.0.0.1:$ALMANAC_MCP_PORT/mcp' --tool 'bootstrap.handshake' --json-args '{\"requester_identity\":\"Async Bot\",\"unix_user\":\"asyncbot\",\"source_ip\":\"127.0.0.1\"}'"
  )"
  python3 - "$duplicate_json" "$request_id" "$token_id" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
if payload.get("request_id") != sys.argv[2]:
    raise SystemExit("duplicate handshake should return the existing pending request")
if payload.get("token_id") == sys.argv[3]:
    raise SystemExit("duplicate handshake should rotate the pending token_id")
if not payload.get("raw_token"):
    raise SystemExit("duplicate handshake should mint a fresh raw token for the retrying client")
PY
  read -r token token_id <<EOF
$(python3 - "$duplicate_json" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
print(payload["raw_token"], payload["token_id"])
PY
)
EOF

  if pending_err="$(
    run_almanac_shell \
      "'$ALMANAC_REPO_DIR/bin/almanac-rpc' --url 'http://127.0.0.1:$ALMANAC_MCP_PORT/mcp' --tool 'vaults.refresh' --json-args '{\"token\":\"$token\"}'" \
      2>&1
  )"; then
    echo "Expected pending handshake token to remain unusable before approval." >&2
    exit 1
  fi
  if [[ "$pending_err" != *"pending operator approval"* ]]; then
    echo "Expected pending token failure to mention operator approval." >&2
    printf '%s\n' "$pending_err" >&2
    exit 1
  fi

  run_almanac_shell \
    "'$ALMANAC_REPO_DIR/bin/almanac-ctl' --json request approve '$request_id' --surface ctl --actor async-smoke" >/dev/null

  status_json="$(
    run_almanac_shell \
      "'$ALMANAC_REPO_DIR/bin/almanac-rpc' --url 'http://127.0.0.1:$ALMANAC_MCP_PORT/mcp' --tool 'bootstrap.status' --json-args '{\"request_id\":\"$request_id\"}'"
  )"
  python3 - "$status_json" "$token_id" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
if payload.get("token_id") != sys.argv[2]:
    raise SystemExit("approved handshake should retain the original token_id")
if "raw_token" in payload:
    raise SystemExit("approved handshake status should not mint a second raw token")
PY
  activation_trigger_path="$ALMANAC_PRIV_DIR/state/activation-triggers/agent-asyncbot.json"
  python3 - "$activation_trigger_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.is_file():
    raise SystemExit(f"activation trigger missing: {path}")
payload = json.loads(path.read_text(encoding="utf-8"))
if payload.get("status") != "approved":
    raise SystemExit(f"expected activation trigger status=approved, saw {payload.get('status')!r}")
PY

  refresh_json="$(
    run_almanac_shell \
      "'$ALMANAC_REPO_DIR/bin/almanac-rpc' --url 'http://127.0.0.1:$ALMANAC_MCP_PORT/mcp' --tool 'vaults.refresh' --json-args '{\"token\":\"$token\"}'"
  )"
  python3 - "$refresh_json" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
if not payload.get("agent_id"):
    raise SystemExit("approved handshake token should succeed against authenticated tools")
PY
}

assert_remote_auto_provision_enrollment() {
  local handshake_json="" duplicate_json="" request_id="" unix_user="$AUTOPROV_UNIX_USER"
  local home_dir="" hermes_home="" agent_id=""

  handshake_json="$(
    run_almanac_shell \
      "'$ALMANAC_REPO_DIR/bin/almanac-rpc' --url 'http://127.0.0.1:$ALMANAC_MCP_PORT/mcp' --tool 'bootstrap.handshake' --json-args '{\"requester_identity\":\"Remote Auto\",\"unix_user\":\"$unix_user\",\"source_ip\":\"127.0.0.1\",\"auto_provision\":true}'"
  )"

  request_id="$(
    python3 - "$handshake_json" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
if not payload.get("auto_provision"):
    raise SystemExit("expected auto_provision handshake response")
if payload.get("raw_token"):
    raise SystemExit("auto-provision handshake should not expose a pending raw token")
print(payload["request_id"])
PY
  )"

  duplicate_json="$(
    run_almanac_shell \
      "'$ALMANAC_REPO_DIR/bin/almanac-rpc' --url 'http://127.0.0.1:$ALMANAC_MCP_PORT/mcp' --tool 'bootstrap.handshake' --json-args '{\"requester_identity\":\"Remote Auto\",\"unix_user\":\"$unix_user\",\"source_ip\":\"127.0.0.1\",\"auto_provision\":true}'"
  )"
  python3 - "$duplicate_json" "$request_id" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
if payload.get("request_id") != sys.argv[2]:
    raise SystemExit("duplicate auto-provision handshake should reuse the pending request")
if not payload.get("resume_existing"):
    raise SystemExit("duplicate auto-provision handshake should mark resume_existing")
if payload.get("raw_token"):
    raise SystemExit("duplicate auto-provision handshake should not mint a raw token")
PY

  ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$ALMANAC_REPO_DIR/bin/almanac-ctl" --json request approve "$request_id" --surface ctl --actor auto-provision-smoke >/dev/null
  ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$ALMANAC_REPO_DIR/bin/almanac-enrollment-provision.sh" >/dev/null

  python3 - "$ALMANAC_DB_PATH" "$request_id" "$unix_user" "$ALMANAC_PRIV_DIR" <<'PY'
import json
import sqlite3
import sys
from pathlib import Path

db_path, request_id, unix_user, priv_dir = sys.argv[1:5]
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

row = conn.execute(
    """
    SELECT provisioned_at, provision_error
    FROM bootstrap_requests
    WHERE request_id = ?
    """,
    (request_id,),
).fetchone()
if row is None:
    raise SystemExit("auto-provision request missing from DB")
if not row["provisioned_at"]:
    raise SystemExit(f"expected provisioned_at for {request_id}, saw none (error={row['provision_error']!r})")
if row["provision_error"]:
    raise SystemExit(f"unexpected auto-provision error for {request_id}: {row['provision_error']}")

agent_id = f"agent-{unix_user}"
agent = conn.execute(
    "SELECT status, manifest_path, hermes_home FROM agents WHERE agent_id = ?",
    (agent_id,),
).fetchone()
if agent is None or agent["status"] != "active":
    raise SystemExit(f"expected active agent row for {agent_id}")
for field in ("manifest_path", "hermes_home"):
    path = Path(agent[field])
    if not path.exists():
        raise SystemExit(f"expected {field} to exist for {agent_id}: {path}")

state_path = Path(agent["hermes_home"]) / "state" / "almanac-enrollment.json"
if not state_path.is_file():
    raise SystemExit(f"missing enrollment state file for {agent_id}: {state_path}")
state = json.loads(state_path.read_text(encoding="utf-8"))
if state.get("status") != "active":
    raise SystemExit(f"expected host-side enrollment state active for {agent_id}, saw {state.get('status')!r}")
PY

  agent_id="agent-$unix_user"
  home_dir="$(getent passwd "$unix_user" | cut -d: -f6)"
  hermes_home="$home_dir/.local/share/almanac-agent/hermes-home"
  assert_agent_access_surfaces "$unix_user" "$agent_id" "$hermes_home"
}

assert_upgrade_check_notification_dedup() {
  # Prove two things about the upgrade-check flow:
  #   1. When deployed_commit is stale, the check flags update_available=True
  #      and queues exactly ONE operator notification.
  #   2. A second identical check does not re-queue another notification for
  #      the same upstream SHA (dedup via almanac_upgrade_last_notified_sha).
  # We do not care what the live upstream SHA is; we only check the state
  # machine behaves correctly when deployed != upstream.
  local notif_before="" notif_after_first="" notif_after_second="" first_result="" second_result=""

  run_almanac_shell \
    "PYTHONPATH='$ALMANAC_REPO_DIR/python' python3 - <<'PY'
import json
from pathlib import Path
import sqlite3

import almanac_control

cfg = almanac_control.Config.from_env()
state_path = cfg.release_state_file
state_path.parent.mkdir(parents=True, exist_ok=True)
# Force the deployed commit to a sentinel value that cannot match any live
# upstream, so update_available is guaranteed to be true.
state_path.write_text(json.dumps({
    'deployed_from': 'smoke-fixture',
    'deployed_commit': '0000000000000000000000000000000000000000',
    'deployed_source_repo': cfg.upstream_repo_url,
    'deployed_source_branch': cfg.upstream_branch,
    'tracked_upstream_repo_url': cfg.upstream_repo_url,
    'tracked_upstream_branch': cfg.upstream_branch,
}), encoding='utf-8')

# Also clear any previous dedup state so this run is deterministic.
conn = sqlite3.connect(cfg.db_path)
conn.row_factory = sqlite3.Row
conn.execute('DELETE FROM settings WHERE key IN (\"almanac_upgrade_last_seen_sha\", \"almanac_upgrade_last_notified_sha\")')
conn.commit()
conn.close()
PY"

  notif_before="$(run_almanac_shell \
    "sqlite3 '$ALMANAC_DB_PATH' \"SELECT COUNT(*) FROM notification_outbox WHERE message LIKE 'Almanac update available%'\"")"

  first_result="$(run_almanac_shell \
    "'$ALMANAC_REPO_DIR/bin/almanac-ctl' --json upgrade check --notify --actor upgrade-smoke")"
  notif_after_first="$(run_almanac_shell \
    "sqlite3 '$ALMANAC_DB_PATH' \"SELECT COUNT(*) FROM notification_outbox WHERE message LIKE 'Almanac update available%'\"")"

  second_result="$(run_almanac_shell \
    "'$ALMANAC_REPO_DIR/bin/almanac-ctl' --json upgrade check --notify --actor upgrade-smoke")"
  notif_after_second="$(run_almanac_shell \
    "sqlite3 '$ALMANAC_DB_PATH' \"SELECT COUNT(*) FROM notification_outbox WHERE message LIKE 'Almanac update available%'\"")"

  python3 - "$first_result" "$second_result" "$notif_before" "$notif_after_first" "$notif_after_second" <<'PY'
import json
import sys

first = json.loads(sys.argv[1])
second = json.loads(sys.argv[2])
before = int(sys.argv[3].strip())
after_first = int(sys.argv[4].strip())
after_second = int(sys.argv[5].strip())

# A live upstream lookup may fail in restricted CI networks; in that case the
# check returns status=warn with error set, which is still a valid shape. We
# only assert stronger behavior when the network lookup succeeded.
if first.get("error"):
    if second.get("error"):
        # Both network lookups failed; still make sure no notifications were
        # incorrectly fired on a failed upstream query.
        if after_first != before or after_second != before:
            raise SystemExit(
                f"upgrade-check fired operator notifications on failed upstream lookups "
                f"(before={before}, after_first={after_first}, after_second={after_second})"
            )
        print("upgrade-check network lookup unavailable in this environment; dedup path skipped.")
        raise SystemExit(0)

if not first.get("update_available"):
    raise SystemExit(
        f"expected update_available=True with fake stale deployed_commit; got {first!r}"
    )
if not first.get("notification_sent"):
    raise SystemExit("expected first upgrade-check to fire operator notification")
if second.get("notification_sent"):
    raise SystemExit("second upgrade-check must not re-fire for the same upstream SHA")

if after_first - before != 1:
    raise SystemExit(
        f"expected first check to queue exactly 1 notification; delta={after_first - before}"
    )
if after_second != after_first:
    raise SystemExit(
        f"expected second check to queue 0 notifications; delta={after_second - after_first}"
    )

if first["deployed_commit_short"] != "000000000000":
    raise SystemExit(
        f"expected sentinel deployed_commit to round-trip into result, got {first!r}"
    )
PY
}

assert_bootstrap_rate_limit() {
  # The configured per-IP cap is ALMANAC_BOOTSTRAP_PER_IP_LIMIT; after we exceed it
  # the server must respond with status 429 (RuntimeError mapping in almanac-mcp) AND
  # expose Retry-After + retry_after_seconds in the error body.
  local cap="${ALMANAC_BOOTSTRAP_PER_IP_LIMIT:-5}"
  local source_ip="10.99.$((RANDOM % 250 + 1)).$((RANDOM % 250 + 1))"
  local i=""
  # Fill the bucket from a synthetic source IP (avoids polluting real one).
  for ((i = 0; i < cap; i++)); do
    run_almanac_shell \
      "'$ALMANAC_REPO_DIR/bin/almanac-rpc' --url 'http://127.0.0.1:$ALMANAC_MCP_PORT/mcp' --tool 'bootstrap.request' --json-args '{\"requester_identity\":\"rate-$i\",\"unix_user\":\"rate-$i\",\"source_ip\":\"100.64.55.1\"}'" \
      >/dev/null
  done

  local raw_resp=""
  local err_file=""
  err_file="$(mktemp)"
  # Call the MCP HTTP endpoint directly so we can observe the Retry-After header.
  raw_resp="$(curl --max-time 5 -sS -o "$err_file" -D "$err_file.headers" \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json' \
    -X POST "http://127.0.0.1:$ALMANAC_MCP_PORT/mcp" \
    --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"rl-smoke","version":"1"}}}' || true)"
  local session_id=""
  session_id="$(awk 'tolower($0) ~ /^mcp-session-id:/ {gsub(/\r/, ""); print $2; exit}' "$err_file.headers" 2>/dev/null || true)"
  if [[ -z "$session_id" ]]; then
    echo "Expected mcp-session-id header from initialize." >&2
    cat "$err_file.headers" >&2
    rm -f "$err_file" "$err_file.headers"
    exit 1
  fi

  curl --max-time 5 -sS -o /dev/null \
    -H 'Content-Type: application/json' \
    -H "mcp-session-id: $session_id" \
    -X POST "http://127.0.0.1:$ALMANAC_MCP_PORT/mcp" \
    --data '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}' >/dev/null

  local status_line=""
  status_line="$(curl --max-time 5 -sS -o "$err_file" -w '%{http_code}' -D "$err_file.headers" \
    -H 'Content-Type: application/json' \
    -H "mcp-session-id: $session_id" \
    -X POST "http://127.0.0.1:$ALMANAC_MCP_PORT/mcp" \
    --data '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"bootstrap.request","arguments":{"requester_identity":"over-limit","unix_user":"over-limit","source_ip":"100.64.55.1"}}}')"

  if [[ "$status_line" != "429" ]]; then
    echo "Expected HTTP 429 on rate-limit overflow, got $status_line" >&2
    cat "$err_file.headers" >&2
    cat "$err_file" >&2
    rm -f "$err_file" "$err_file.headers"
    exit 1
  fi
  if ! awk 'tolower($0) ~ /^retry-after:/' "$err_file.headers" | grep -q '[0-9]'; then
    echo "Expected Retry-After header on 429 response" >&2
    cat "$err_file.headers" >&2
    rm -f "$err_file" "$err_file.headers"
    exit 1
  fi
  python3 - "$err_file" <<'PY'
import json, sys
body = json.loads(open(sys.argv[1]).read() or "{}")
error = body.get("error") or {}
data = error.get("data") or {}
if "retry_after_seconds" not in data:
    raise SystemExit("expected retry_after_seconds in 429 error.data")
if data.get("scope") not in {"per-ip", "global-pending"}:
    raise SystemExit(f"unexpected rate-limit scope: {data.get('scope')}")
PY
  rm -f "$err_file" "$err_file.headers"
}

assert_admin_endpoint_auth() {
  # bootstrap.approve must reject calls without an operator token.
  local err_file=""
  err_file="$(mktemp)"
  if run_almanac_shell \
    "'$ALMANAC_REPO_DIR/bin/almanac-rpc' --url 'http://127.0.0.1:$ALMANAC_MCP_PORT/mcp' --tool 'bootstrap.approve' --json-args '{\"request_id\":\"req_doesnotexist\"}'" \
    >/dev/null 2>"$err_file"; then
    echo "Expected bootstrap.approve without operator_token to fail." >&2
    rm -f "$err_file"
    exit 1
  fi
  if ! grep -Eiq 'operator_token' "$err_file"; then
    echo "Expected operator_token error message." >&2
    cat "$err_file" >&2
    rm -f "$err_file"
    exit 1
  fi
  rm -f "$err_file"

  # bootstrap.status must reject calls from a different source_ip than the one that
  # created the request.
  local request_json="" request_id=""
  request_json="$(run_almanac_shell \
    "'$ALMANAC_REPO_DIR/bin/almanac-rpc' --url 'http://127.0.0.1:$ALMANAC_MCP_PORT/mcp' --tool 'bootstrap.request' --json-args '{\"requester_identity\":\"auth-bot\",\"unix_user\":\"auth-bot\",\"source_ip\":\"100.64.200.7\"}'")"
  request_id="$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['request_id'])" "$request_json")"

  err_file="$(mktemp)"
  if run_almanac_shell \
    "'$ALMANAC_REPO_DIR/bin/almanac-rpc' --url 'http://127.0.0.1:$ALMANAC_MCP_PORT/mcp' --tool 'bootstrap.status' --json-args '{\"request_id\":\"$request_id\",\"source_ip\":\"100.64.200.99\"}'" \
    >/dev/null 2>"$err_file"; then
    echo "Expected bootstrap.status to reject mismatched source_ip." >&2
    rm -f "$err_file"
    exit 1
  fi
  if ! grep -Eiq 'source ip' "$err_file"; then
    echo "Expected source-ip mismatch error message." >&2
    cat "$err_file" >&2
    rm -f "$err_file"
    exit 1
  fi
  rm -f "$err_file"
}

assert_token_reinstate() {
  # create a throwaway agent via CLI approval path, revoke, reinstate, then
  # verify the token works again for vaults.refresh.
  local request_json="" request_id="" token="" reinstate_json=""
  request_json="$(run_almanac_shell \
    "'$ALMANAC_REPO_DIR/bin/almanac-rpc' --url 'http://127.0.0.1:$ALMANAC_MCP_PORT/mcp' --tool 'bootstrap.request' --json-args '{\"requester_identity\":\"reins-bot\",\"unix_user\":\"reinsbot\",\"source_ip\":\"127.0.0.1\"}'")"
  request_id="$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['request_id'])" "$request_json")"

  run_almanac_shell \
    "'$ALMANAC_REPO_DIR/bin/almanac-ctl' --json request approve '$request_id' --surface ctl --actor smoke-reinstate" >/dev/null

  local status_json=""
  status_json="$(run_almanac_shell \
    "'$ALMANAC_REPO_DIR/bin/almanac-rpc' --url 'http://127.0.0.1:$ALMANAC_MCP_PORT/mcp' --tool 'bootstrap.status' --json-args '{\"request_id\":\"$request_id\"}'")"
  token="$(python3 -c "import json,sys; p=json.loads(sys.argv[1]); print(p['raw_token'])" "$status_json")"
  local token_id=""
  token_id="$(python3 -c "import json,sys; p=json.loads(sys.argv[1]); print(p['token_id'])" "$status_json")"

  run_almanac_shell \
    "'$ALMANAC_REPO_DIR/bin/almanac-ctl' --json token revoke '$token_id' --surface ctl --actor smoke-reinstate" >/dev/null

  reinstate_json="$(run_almanac_shell \
    "'$ALMANAC_REPO_DIR/bin/almanac-ctl' --json token reinstate '$token_id' --surface ctl --actor smoke-reinstate")"
  python3 - "$reinstate_json" "$token_id" <<'PY'
import json, sys
payload = json.loads(sys.argv[1])
if payload.get("token_id") != sys.argv[2]:
    raise SystemExit("reinstate did not return the original token_id")
if payload.get("reinstated_by_surface") != "ctl":
    raise SystemExit("reinstate did not record surface audit")
PY
}

assert_ssot_rails() {
  # Use the already-enrolled smoke agent's token (still revoked above — create
  # a fresh one via the CLI path so we have an active token).
  local req_json="" req_id="" tok_json="" token="" ssot_home="/tmp/almanac-smoke-ssot-home"
  mkdir -p "$ssot_home/secrets"
  chown -R "$ALMANAC_USER:$ALMANAC_USER" "$ssot_home"
  run_almanac_shell \
    "'$ALMANAC_REPO_DIR/bin/install-almanac-skills.sh' '$ALMANAC_REPO_DIR' '$ssot_home'" >/dev/null
  req_json="$(run_almanac_shell \
    "'$ALMANAC_REPO_DIR/bin/almanac-rpc' --url 'http://127.0.0.1:$ALMANAC_MCP_PORT/mcp' --tool 'bootstrap.request' --json-args '{\"requester_identity\":\"ssot-bot\",\"unix_user\":\"ssotbot\",\"source_ip\":\"127.0.0.1\"}'")"
  req_id="$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['request_id'])" "$req_json")"
  run_almanac_shell \
    "'$ALMANAC_REPO_DIR/bin/almanac-ctl' --json request approve '$req_id' --surface ctl --actor smoke-ssot" >/dev/null
  tok_json="$(run_almanac_shell \
    "'$ALMANAC_REPO_DIR/bin/almanac-rpc' --url 'http://127.0.0.1:$ALMANAC_MCP_PORT/mcp' --tool 'bootstrap.status' --json-args '{\"request_id\":\"$req_id\"}'")"
  token="$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['raw_token'])" "$tok_json")"
  run_almanac_shell \
    "'$ALMANAC_REPO_DIR/bin/almanac-rpc' --url 'http://127.0.0.1:$ALMANAC_MCP_PORT/mcp' --tool 'agents.register' --json-args '{\"token\":\"$token\",\"unix_user\":\"ssotbot\",\"display_name\":\"SSOT Bot\",\"role\":\"user\",\"hermes_home\":\"$ssot_home\",\"model_preset\":\"codex\",\"model_string\":\"openai:codex\",\"channels\":[\"tui-only\"]}'" >/dev/null
  run_almanac_shell \
    "'$ALMANAC_REPO_DIR/bin/almanac-rpc' --url 'http://127.0.0.1:$ALMANAC_MCP_PORT/mcp' --tool 'vaults.refresh' --json-args '{\"token\":\"$token\"}'" >/dev/null

  local err_file=""
  err_file="$(mktemp)"
  if run_almanac_shell \
    "'$ALMANAC_REPO_DIR/bin/almanac-rpc' --url 'http://127.0.0.1:$ALMANAC_MCP_PORT/mcp' --tool 'ssot.write' --json-args '{\"token\":\"$token\",\"operation\":\"delete\",\"target_id\":\"page_1\",\"payload\":{}}'" \
    >/dev/null 2>"$err_file"; then
    echo "Expected ssot.write delete to be refused." >&2
    rm -f "$err_file"
    exit 1
  fi
  if ! grep -Eiq 'rail violation|not permitted' "$err_file"; then
    echo "Expected SSOT rail violation in error message." >&2
    cat "$err_file" >&2
    rm -f "$err_file"
    exit 1
  fi
  rm -f "$err_file"

  # update with foreign owner should require approval (not hard-fail; returned flag).
  local write_json=""
  write_json="$(run_almanac_shell \
    "'$ALMANAC_REPO_DIR/bin/almanac-rpc' --url 'http://127.0.0.1:$ALMANAC_MCP_PORT/mcp' --tool 'ssot.write' --json-args '{\"token\":\"$token\",\"operation\":\"update\",\"target_id\":\"page_2\",\"payload\":{\"properties\":{\"Owner\":{\"people\":[{\"name\":\"someone-else\"}]}}}}'")"
  python3 - "$write_json" <<'PY'
import json, sys
payload = json.loads(sys.argv[1])
if not payload.get("approval_required"):
    raise SystemExit("expected approval_required=true when owner is a non-matching user")
if payload.get("queued"):
    raise SystemExit("foreign-owner write should not be queued")
if payload.get("owner_source") not in ("owner-property", "created-by", "needs-approval"):
    raise SystemExit(f"unexpected owner_source: {payload.get('owner_source')}")
PY

  # insert should be queued without approval.
  write_json="$(run_almanac_shell \
    "'$ALMANAC_REPO_DIR/bin/almanac-rpc' --url 'http://127.0.0.1:$ALMANAC_MCP_PORT/mcp' --tool 'ssot.write' --json-args '{\"token\":\"$token\",\"operation\":\"insert\",\"target_id\":\"page_3\",\"payload\":{\"properties\":{}}}'")"
  python3 - "$write_json" <<'PY'
import json, sys
payload = json.loads(sys.argv[1])
if not payload.get("queued"):
    raise SystemExit("insert should be queued")
if payload.get("approval_required"):
    raise SystemExit("insert should not require approval")
PY
}

assert_notion_webhook_flow() {
  local webhook_url="http://127.0.0.1:$ALMANAC_NOTION_WEBHOOK_PORT/notion/webhook"
  local verify_token="smoke-verify-$(date +%s)"

  # 1) POST a verification_token (no signature) -> server stores it and returns 202.
  local body="" signature="" resp=""
  resp=""
  if ! resp="$(run_almanac_shell \
    "curl --max-time 5 -sS -o /tmp/almanac-notion-verify.out -w '%{http_code}\n' -H 'Content-Type: application/json' -X POST '$webhook_url' --data '{\"verification_token\":\"$verify_token\"}'")"; then
    :
  fi
  if [[ "$resp" != "202" && "$resp" != "200" ]]; then
    echo "verification_token POST should be accepted (got $resp)" >&2
    cat /tmp/almanac-notion-verify.out >&2 || true
    exit 1
  fi

  # 2) POST a signed event; expect 202 and persisted row.
  body='{"id":"evt-smoke-001","type":"page.created","created_by":{"name":"smokebot"},"properties":{}}'
  signature="sha256=$(printf '%s' "$body" | openssl dgst -sha256 -hmac "$verify_token" -hex | awk '{print $2}')"
  resp=""
  if ! resp="$(run_almanac_shell \
    "curl --max-time 5 -sS -o /tmp/almanac-notion-signed.out -w '%{http_code}\n' -H 'Content-Type: application/json' -H 'X-Notion-Signature: $signature' -X POST '$webhook_url' --data '$body'")"; then
    :
  fi
  if [[ "$resp" != "202" ]]; then
    echo "Expected signed webhook POST to return 202, got $resp" >&2
    cat /tmp/almanac-notion-signed.out >&2
    exit 1
  fi

  # 3) POST with a BAD signature; expect 403.
  resp=""
  if ! resp="$(run_almanac_shell \
    "curl --max-time 5 -sS -o /tmp/almanac-notion-bad.out -w '%{http_code}\n' -H 'Content-Type: application/json' -H 'X-Notion-Signature: sha256=00deadbeef' -X POST '$webhook_url' --data '$body'")"; then
    :
  fi
  if [[ "$resp" != "403" ]]; then
    echo "Expected bad signature to return 403, got $resp" >&2
    cat /tmp/almanac-notion-bad.out >&2
    exit 1
  fi

  # 4) Run batcher and confirm the stored event is now processed. Owner 'smokebot'
  # should resolve to the smokebot agent from assert_almanac_control_plane_roundtrip.
  local batcher_json=""
  batcher_json="$(run_almanac_shell \
    "'$ALMANAC_REPO_DIR/bin/almanac-ctl' --json notion process-pending")"
  python3 - "$batcher_json" <<'PY'
import json, sys
payload = json.loads(sys.argv[1])
if payload.get("processed", 0) < 1:
    raise SystemExit("batcher did not process any events")
nudges = payload.get("nudges") or {}
# owner is `smokebot` via created_by; smokebot is an enrolled user agent in the
# earlier roundtrip. nudges should be keyed by that agent_id.
if not any("smokebot" in k for k in nudges):
    # This is allowed if the smokebot agent was deenrolled before this step ran.
    pass
PY
}

assert_notification_delivery_backlog() {
  run_almanac_shell "PYTHONPATH='$ALMANAC_REPO_DIR/python' python3 - <<'PY'
import datetime as dt

from almanac_control import Config, connect_db, queue_notification

cfg = Config.from_env()
with connect_db(cfg) as conn:
    conn.execute('DELETE FROM notification_outbox')
    conn.commit()
    for idx in range(60):
        queue_notification(
            conn,
            target_kind='user-agent',
            target_id='agent-backlog',
            channel_kind='notion-webhook',
            message=f'deferred backlog {idx}',
        )
    stale_at = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=30)).replace(microsecond=0).isoformat()
    conn.execute(
        \"UPDATE notification_outbox SET created_at = ? WHERE target_kind = 'user-agent'\",
        (stale_at,),
    )
    conn.commit()
    queue_notification(
        conn,
        target_kind='operator',
        target_id='tui-only',
        channel_kind='tui-only',
        message='operator backlog probe',
    )
    queue_notification(
        conn,
        target_kind='curator',
        target_id='ghost-agent',
        channel_kind='brief-fanout',
        message='curator backlog probe',
    )
PY"

  local delivery_json=""
  delivery_json="$(run_almanac_shell "'$ALMANAC_REPO_DIR/bin/almanac-notification-delivery.sh' --limit 10")"

  python3 - "$delivery_json" "$ALMANAC_DB_PATH" <<'PY'
import json
import sqlite3
import sys

summary = json.loads(sys.argv[1])
if int(summary.get("delivered", 0)) < 1:
    raise SystemExit("delivery worker did not deliver the operator backlog row")
if int(summary.get("curator_fanout_batches", 0)) != 1:
    raise SystemExit("delivery worker did not actuate curator brief-fanout from backlog")

conn = sqlite3.connect(sys.argv[2])
conn.row_factory = sqlite3.Row
operator_delivered = conn.execute(
    """
    SELECT COUNT(*) AS c
    FROM notification_outbox
    WHERE target_kind = 'operator'
      AND delivered_at IS NOT NULL
    """
).fetchone()["c"]
curator_delivered = conn.execute(
    """
    SELECT COUNT(*) AS c
    FROM notification_outbox
    WHERE target_kind = 'curator'
      AND channel_kind = 'brief-fanout'
      AND delivered_at IS NOT NULL
    """
).fetchone()["c"]
user_agent_pending = conn.execute(
    """
    SELECT COUNT(*) AS c
    FROM notification_outbox
    WHERE target_kind = 'user-agent'
      AND delivered_at IS NULL
    """
).fetchone()["c"]

if operator_delivered != 1:
    raise SystemExit(f"expected 1 delivered operator row, found {operator_delivered}")
if curator_delivered != 1:
    raise SystemExit(f"expected 1 delivered curator fanout row, found {curator_delivered}")
if user_agent_pending != 60:
    raise SystemExit(f"expected 60 deferred user-agent rows, found {user_agent_pending}")
PY
}

assert_nextcloud_admin_home_empty() {
  local app_container=""

  app_container="${ALMANAC_NAME:-almanac}-nextcloud-app"
  if ! su - "$ALMANAC_USER" -c "podman container inspect '$app_container' >/dev/null 2>&1"; then
    echo "Expected Nextcloud app container '$app_container' to exist." >&2
    show_nextcloud_diagnostics
    return 1
  fi

  if ! su - "$ALMANAC_USER" -c "podman exec '$app_container' sh -lc 'test -d /var/www/html/data/${NEXTCLOUD_ADMIN_USER:-admin}/files && [ -z \"\$(find /var/www/html/data/${NEXTCLOUD_ADMIN_USER:-admin}/files -mindepth 1 -maxdepth 1 -print -quit)\" ]'"; then
    echo "Expected initial Nextcloud admin home to be empty." >&2
    su - "$ALMANAC_USER" -c "podman exec '$app_container' sh -lc 'ls -la /var/www/html/data/${NEXTCLOUD_ADMIN_USER:-admin}/files || true'" || true
    show_nextcloud_diagnostics
    return 1
  fi
}

assert_nextcloud_vault_mount_configured() {
  local app_container="" mounts_json=""

  app_container="${ALMANAC_NAME:-almanac}-nextcloud-app"
  if ! su - "$ALMANAC_USER" -c "podman container inspect '$app_container' >/dev/null 2>&1"; then
    echo "Expected Nextcloud app container '$app_container' to exist." >&2
    show_nextcloud_diagnostics
    return 1
  fi

  if ! mounts_json="$(su - "$ALMANAC_USER" -c "podman exec -u 33:33 '$app_container' php /var/www/html/occ files_external:list --output=json")"; then
    echo "Could not inspect Nextcloud external storage mounts." >&2
    show_nextcloud_diagnostics
    return 1
  fi

  if ! NEXTCLOUD_MOUNTS_JSON="$mounts_json" python3 - "$NEXTCLOUD_VAULT_MOUNT_POINT" "/srv/vault" <<'PY'
import json
import os
import sys

mount_point = sys.argv[1]
datadir = sys.argv[2]
mounts = json.loads(os.environ["NEXTCLOUD_MOUNTS_JSON"])

for mount in mounts:
    if mount.get("mount_point") == mount_point:
        config = mount.get("configuration") or {}
        if config.get("datadir") == datadir and not (mount.get("applicable_users") or []) and not (mount.get("applicable_groups") or []):
            raise SystemExit(0)
        raise SystemExit(2)

raise SystemExit(1)
PY
  then
    echo "Expected Nextcloud to expose the shared vault as /Vault." >&2
    printf '%s\n' "$mounts_json" >&2
    show_nextcloud_diagnostics
    return 1
  fi

  if ! su - "$ALMANAC_USER" -c "podman exec -u 33:33 '$app_container' sh -lc 'test -w /srv/vault'"; then
    echo "Expected Nextcloud www-data to have write access to /srv/vault." >&2
    show_nextcloud_diagnostics
    return 1
  fi
}

write_smoke_pdf() {
  local target="$1"

  python3 - "$target" <<'PY'
import sys
from pathlib import Path

target = Path(sys.argv[1])
text = "Chutes MESH smoke test PDF"
stream = f"BT\n/F1 24 Tf\n72 720 Td\n({text}) Tj\nET\n".encode("ascii")
objects = [
    b"<< /Type /Catalog /Pages 2 0 R >>",
    b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"endstream",
    b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
]

pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
offsets = []
for index, obj in enumerate(objects, start=1):
    offsets.append(len(pdf))
    pdf.extend(f"{index} 0 obj\n".encode("ascii"))
    pdf.extend(obj)
    pdf.extend(b"\nendobj\n")

xref_offset = len(pdf)
pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
pdf.extend(b"0000000000 65535 f \n")
for offset in offsets:
    pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
pdf.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii"))

target.parent.mkdir(parents=True, exist_ok=True)
target.write_bytes(pdf)
PY
}

vault_watch_ready() {
  local uid=""

  uid="$(id -u "$ALMANAC_USER")"
  [[ -S "/run/user/$uid/bus" ]] || return 1

  su - "$ALMANAC_USER" -c "env XDG_RUNTIME_DIR='/run/user/$uid' DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/$uid/bus' systemctl --user is-active --quiet almanac-vault-watch.service" &&
    (
      [[ "${PDF_INGEST_ENABLED:-1}" != "1" ]] ||
      su - "$ALMANAC_USER" -c "env XDG_RUNTIME_DIR='/run/user/$uid' DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/$uid/bus' systemctl --user is-active --quiet almanac-pdf-ingest.timer"
    )
}

assert_markdown_watch_pipeline() {
  local watcher_mode=0
  local smoke_note=""
  local query=""

  smoke_note="$ALMANAC_PRIV_DIR/vault/Inbox/chutes-mesh-note.md"
  query="Chutes MESH filesystem watcher note"

  if vault_watch_ready; then
    watcher_mode=1
  fi

  mkdir -p "$(dirname "$smoke_note")"
  cat >"$smoke_note" <<EOF
# Chutes MESH Watch Test

$query
EOF
  chown "$ALMANAC_USER:$ALMANAC_USER" "$smoke_note"

  if (( ! watcher_mode )); then
    run_almanac_shell "'$ALMANAC_REPO_DIR/bin/qmd-refresh.sh' --skip-embed"
    run_almanac_shell "qmd --index '$QMD_INDEX_NAME' embed"
  fi

  if ! wait_for_qmd_search_match "$query" "chutes-mesh-note.md" "$QMD_COLLECTION_NAME" 120 1; then
    echo "Expected qmd search to surface direct markdown changes from the shared vault." >&2
    printf '%s\n' "$LAST_QMD_SEARCH_OUTPUT" >&2
    show_pdf_ingest_diagnostics
    return 1
  fi

  if ! wait_for_mcp_query_match "$query" "inbox/chutes-mesh-note.md" "$QMD_COLLECTION_NAME" 120 1; then
    echo "Expected qmd MCP search to surface direct markdown changes from the shared vault." >&2
    printf '%s\n' "$LAST_QMD_MCP_OUTPUT" >&2
    show_pdf_ingest_diagnostics
    return 1
  fi

  if ! wait_for_qmd_pending_embeddings_zero 120 1; then
    echo "Expected watcher-driven qmd embedding backlog to clear after direct markdown changes." >&2
    run_almanac_shell "qmd --index '$QMD_INDEX_NAME' status" >&2 || true
    show_pdf_ingest_diagnostics
    return 1
  fi

  rm -f "$smoke_note"

  if (( ! watcher_mode )); then
    run_almanac_shell "'$ALMANAC_REPO_DIR/bin/qmd-refresh.sh' --skip-embed"
  fi

  if ! wait_for_qmd_search_absent "$query" "chutes-mesh-note.md" "$QMD_COLLECTION_NAME" 120 1; then
    echo "Expected qmd search to stop surfacing removed markdown files from the shared vault." >&2
    printf '%s\n' "$LAST_QMD_SEARCH_OUTPUT" >&2
    show_pdf_ingest_diagnostics
    return 1
  fi

  if ! wait_for_mcp_query_absent "$query" "inbox/chutes-mesh-note.md" "$QMD_COLLECTION_NAME" 120 1; then
    echo "Expected qmd MCP search to stop surfacing removed markdown files from the shared vault." >&2
    printf '%s\n' "$LAST_QMD_MCP_OUTPUT" >&2
    show_pdf_ingest_diagnostics
    return 1
  fi
}

assert_text_watch_pipeline() {
  local watcher_mode=0
  local smoke_note=""
  local query=""

  smoke_note="$ALMANAC_PRIV_DIR/vault/Inbox/chutes-mesh-note.txt"
  query="Chutes MESH filesystem watcher text note"

  if vault_watch_ready; then
    watcher_mode=1
  fi

  mkdir -p "$(dirname "$smoke_note")"
  cat >"$smoke_note" <<EOF
Chutes MESH text watch test

$query
EOF
  chown "$ALMANAC_USER:$ALMANAC_USER" "$smoke_note"

  if (( ! watcher_mode )); then
    run_almanac_shell "'$ALMANAC_REPO_DIR/bin/qmd-refresh.sh' --skip-embed"
    run_almanac_shell "qmd --index '$QMD_INDEX_NAME' embed"
  fi

  if ! wait_for_qmd_search_match "$query" "chutes-mesh-note.txt" "$QMD_COLLECTION_NAME" 120 1; then
    echo "Expected qmd search to surface direct text changes from the shared vault." >&2
    printf '%s\n' "$LAST_QMD_SEARCH_OUTPUT" >&2
    show_pdf_ingest_diagnostics
    return 1
  fi

  if ! wait_for_mcp_query_match "$query" "inbox/chutes-mesh-note.txt" "$QMD_COLLECTION_NAME" 120 1; then
    echo "Expected qmd MCP search to surface direct text changes from the shared vault." >&2
    printf '%s\n' "$LAST_QMD_MCP_OUTPUT" >&2
    show_pdf_ingest_diagnostics
    return 1
  fi

  if ! wait_for_qmd_pending_embeddings_zero 120 1; then
    echo "Expected watcher-driven qmd embedding backlog to clear after direct text changes." >&2
    run_almanac_shell "qmd --index '$QMD_INDEX_NAME' status" >&2 || true
    show_pdf_ingest_diagnostics
    return 1
  fi

  rm -f "$smoke_note"

  if (( ! watcher_mode )); then
    run_almanac_shell "'$ALMANAC_REPO_DIR/bin/qmd-refresh.sh' --skip-embed"
  fi

  if ! wait_for_qmd_search_absent "$query" "chutes-mesh-note.txt" "$QMD_COLLECTION_NAME" 120 1; then
    echo "Expected qmd search to stop surfacing removed text files from the shared vault." >&2
    printf '%s\n' "$LAST_QMD_SEARCH_OUTPUT" >&2
    show_pdf_ingest_diagnostics
    return 1
  fi

  if ! wait_for_mcp_query_absent "$query" "inbox/chutes-mesh-note.txt" "$QMD_COLLECTION_NAME" 120 1; then
    echo "Expected qmd MCP search to stop surfacing removed text files from the shared vault." >&2
    printf '%s\n' "$LAST_QMD_MCP_OUTPUT" >&2
    show_pdf_ingest_diagnostics
    return 1
  fi
}

pdf_ingest_units_ready() {
  local uid=""

  if ! vault_watch_ready; then
    return 1
  fi

  uid="$(id -u "$ALMANAC_USER")"
  su - "$ALMANAC_USER" -c "env XDG_RUNTIME_DIR='/run/user/$uid' DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/$uid/bus' systemctl --user is-active --quiet almanac-pdf-ingest.timer" &&
    true
}

assert_pdf_ingest_pipeline() {
  local uid=""
  local watcher_mode=""
  local smoke_pdf=""
  local generated_md=""
  local search_term=""
  local pdf_qmd_uri_prefix=""

  uid="$(id -u "$ALMANAC_USER")"
  watcher_mode=0
  smoke_pdf="$ALMANAC_PRIV_DIR/vault/Inbox/chutes-mesh-smoke.pdf"
  generated_md="$ALMANAC_PRIV_DIR/state/pdf-ingest/markdown/Inbox/chutes-mesh-smoke-pdf.md"
  search_term="Chutes MESH smoke test PDF"
  pdf_qmd_uri_prefix="qmd://$PDF_INGEST_COLLECTION_NAME/"

  if pdf_ingest_units_ready; then
    watcher_mode=1
  elif [[ -S "/run/user/$uid/bus" ]]; then
    echo "Expected the vault watcher and PDF ingest timer to be active." >&2
    show_pdf_ingest_diagnostics
    return 1
  else
    echo "No user systemd bus detected for $ALMANAC_USER; using direct PDF ingest fallback." >&2
  fi

  write_smoke_pdf "$smoke_pdf"
  chown "$ALMANAC_USER:$ALMANAC_USER" "$smoke_pdf"

  if (( watcher_mode )); then
    if ! wait_for_file "$generated_md" 120 1; then
      echo "Expected PDF ingest watch path to generate $generated_md." >&2
      show_pdf_ingest_diagnostics
      return 1
    fi
  else
    run_almanac_shell "'$ALMANAC_REPO_DIR/bin/pdf-ingest.sh'"
  fi

  if [[ ! -f "$generated_md" ]]; then
    echo "Expected PDF ingest to generate $generated_md." >&2
    show_pdf_ingest_diagnostics
    return 1
  fi

  if ! grep -q "$search_term" "$generated_md"; then
    echo "Expected generated markdown to contain extracted PDF text." >&2
    show_pdf_ingest_diagnostics
    return 1
  fi

  if ! run_almanac_shell "qmd --index '$QMD_INDEX_NAME' collection show '$PDF_INGEST_COLLECTION_NAME' >/dev/null"; then
    echo "Expected qmd collection '$PDF_INGEST_COLLECTION_NAME' to exist after PDF ingest bootstrap." >&2
    show_pdf_ingest_diagnostics
    return 1
  fi

  if ! wait_for_qmd_search_match "$search_term" "$pdf_qmd_uri_prefix" "$PDF_INGEST_COLLECTION_NAME" 120 1; then
    echo "Expected qmd search to surface the generated PDF markdown." >&2
    printf '%s\n' "$LAST_QMD_SEARCH_OUTPUT" >&2
    show_pdf_ingest_diagnostics
    return 1
  fi

  if ! wait_for_mcp_query_match "$search_term" "inbox/chutes-mesh-smoke-pdf.md" "$PDF_INGEST_COLLECTION_NAME" 120 1; then
    echo "Expected qmd MCP search to surface the generated PDF markdown." >&2
    printf '%s\n' "$LAST_QMD_MCP_OUTPUT" >&2
    show_pdf_ingest_diagnostics
    return 1
  fi

  if ! wait_for_qmd_pending_embeddings_zero 180 1; then
    echo "Expected watcher-driven qmd embedding backlog to clear after PDF-derived markdown changes." >&2
    run_almanac_shell "qmd --index '$QMD_INDEX_NAME' status" >&2 || true
    show_pdf_ingest_diagnostics
    return 1
  fi

  if ! python3 - "$ALMANAC_PRIV_DIR/state/pdf-ingest/status.json" <<'PY'
import json
import sys
from pathlib import Path

status_path = Path(sys.argv[1])
status = json.loads(status_path.read_text())
if int(status.get("failed", 0)) != 0:
    raise SystemExit(1)
if int(status.get("created", 0)) + int(status.get("updated", 0)) < 1:
    raise SystemExit(2)
PY
  then
    echo "Expected PDF ingest status to show a successful conversion run." >&2
    show_pdf_ingest_diagnostics
    return 1
  fi

  rm -f "$smoke_pdf"

  if (( watcher_mode )); then
    if ! wait_for_path_absent "$generated_md" 120 1; then
      echo "Expected PDF ingest watch path to remove generated markdown for deleted PDFs." >&2
      show_pdf_ingest_diagnostics
      return 1
    fi
  else
    run_almanac_shell "'$ALMANAC_REPO_DIR/bin/pdf-ingest.sh' --quiet"
  fi

  if [[ -e "$generated_md" ]]; then
    echo "Expected generated PDF markdown to be removed after deleting the source PDF." >&2
    show_pdf_ingest_diagnostics
    return 1
  fi

  if ! wait_for_qmd_search_absent "$search_term" "$pdf_qmd_uri_prefix" "$PDF_INGEST_COLLECTION_NAME" 120 1; then
    echo "Expected qmd search to stop surfacing deleted generated PDF markdown." >&2
    printf '%s\n' "$LAST_QMD_SEARCH_OUTPUT" >&2
    show_pdf_ingest_diagnostics
    return 1
  fi

  if ! wait_for_mcp_query_absent "$search_term" "inbox/chutes-mesh-smoke-pdf.md" "$PDF_INGEST_COLLECTION_NAME" 120 1; then
    echo "Expected qmd MCP search to stop surfacing deleted generated PDF markdown." >&2
    printf '%s\n' "$LAST_QMD_MCP_OUTPUT" >&2
    show_pdf_ingest_diagnostics
    return 1
  fi

  if ! python3 - "$ALMANAC_PRIV_DIR/state/pdf-ingest/status.json" <<'PY'
import json
import sys
from pathlib import Path

status = json.loads(Path(sys.argv[1]).read_text())
if int(status.get("failed", 0)) != 0:
    raise SystemExit(1)
if int(status.get("removed", 0)) < 1:
    raise SystemExit(2)
PY
  then
    echo "Expected PDF ingest status to record PDF removal cleanup." >&2
    show_pdf_ingest_diagnostics
    return 1
  fi
}

teardown() {
  if [[ "$INSTALLED" == "1" ]]; then
    ALMANAC_INSTALL_ANSWERS_FILE="$ANSWERS_FILE" "$DEPLOY_BIN" --apply-remove || true
    INSTALLED=0
  fi
  if id -u "$AUTOPROV_UNIX_USER" >/dev/null 2>&1; then
    loginctl disable-linger "$AUTOPROV_UNIX_USER" >/dev/null 2>&1 || true
    userdel -r "$AUTOPROV_UNIX_USER" >/dev/null 2>&1 || userdel "$AUTOPROV_UNIX_USER" >/dev/null 2>&1 || true
  fi
}

preclean() {
  if id -u "$ALMANAC_USER" >/dev/null 2>&1 || [[ -e "$ALMANAC_HOME" ]]; then
    echo "Removing existing Almanac smoke target before test..."
    ALMANAC_INSTALL_ANSWERS_FILE="$ANSWERS_FILE" "$DEPLOY_BIN" --apply-remove || true
  fi
  if id -u "$AUTOPROV_UNIX_USER" >/dev/null 2>&1; then
    echo "Removing existing smoke auto-provision user '$AUTOPROV_UNIX_USER' before test..."
    loginctl disable-linger "$AUTOPROV_UNIX_USER" >/dev/null 2>&1 || true
    userdel -r "$AUTOPROV_UNIX_USER" >/dev/null 2>&1 || userdel "$AUTOPROV_UNIX_USER" >/dev/null 2>&1 || true
  fi
}

on_exit() {
  local status="$1"
  if [[ "$status" -ne 0 ]]; then
    echo
    echo "Smoke test failed; attempting teardown..."
  fi
  teardown
  rm -f "$ANSWERS_FILE"
  exit "$status"
}

trap 'on_exit $?' EXIT

write_answers
load_answers_into_env
preclean

echo "Installing Almanac with default smoke-test answers..."
ALMANAC_ALLOW_NO_USER_BUS=1 \
ALMANAC_CURATOR_SKIP_HERMES_SETUP=1 \
ALMANAC_CURATOR_SKIP_GATEWAY_SETUP=1 \
ALMANAC_INSTALL_ANSWERS_FILE="$ANSWERS_FILE" \
  "$DEPLOY_BIN" --apply-install
INSTALLED=1

wait_for_port 127.0.0.1 "$ALMANAC_MCP_PORT" 120 1
wait_for_port 127.0.0.1 "$ALMANAC_NOTION_WEBHOOK_PORT" 120 1
echo

echo "Checking agent payload..."
assert_agent_payload

echo "Checking default vault bootstrap layout..."
assert_default_vault_bootstrap_layout

echo "Checking .vault discovery and reload-defs..."
assert_vault_definition_reload

echo "Checking almanac control-plane bootstrap/token roundtrip..."
assert_almanac_control_plane_roundtrip

echo "Checking async bootstrap handshake activation..."
assert_async_bootstrap_handshake

echo "Checking remote auto-provision enrollment..."
assert_remote_auto_provision_enrollment

echo "Checking upgrade-check notification dedup..."
assert_upgrade_check_notification_dedup

echo "Checking rate-limit enforcement with structured 429..."
assert_bootstrap_rate_limit

echo "Checking operator-gated admin MCP endpoints..."
assert_admin_endpoint_auth

echo "Checking token reinstate flow..."
assert_token_reinstate

echo "Checking SSOT rails (archive/delete refusal + owner mismatch)..."
assert_ssot_rails

echo "Checking Notion webhook signature verification and owner mapping..."
assert_notion_webhook_flow

echo "Checking notification delivery backlog routing..."
assert_notification_delivery_backlog

echo
echo "Starting runtime checks..."

if ! wait_for_port 127.0.0.1 "$QMD_MCP_PORT" 10 1; then
  su - "$ALMANAC_USER" -c "env ALMANAC_CONFIG_FILE='$CONFIG_TARGET' nohup '$ALMANAC_REPO_DIR/bin/qmd-daemon.sh' > '$RUNTIME_DIR/qmd-daemon.log' 2>&1 &"
fi

if ! wait_for_port 127.0.0.1 "$NEXTCLOUD_PORT" 10 1; then
  su - "$ALMANAC_USER" -c "env ALMANAC_CONFIG_FILE='$CONFIG_TARGET' '$ALMANAC_REPO_DIR/bin/nextcloud-up.sh'"
fi

wait_for_port 127.0.0.1 "$QMD_MCP_PORT" 120 1
wait_for_port 127.0.0.1 "$NEXTCLOUD_PORT" 300 2
assert_mcp_status_alignment

if ! wait_for_http_success \
  "http://127.0.0.1:$NEXTCLOUD_PORT/status.php" \
  "almanac-ci.local" \
  "/tmp/almanac-nextcloud-status.json" \
  180 \
  2; then
  show_nextcloud_diagnostics
  exit 1
fi

assert_nextcloud_admin_home_empty
assert_nextcloud_vault_mount_configured
assert_text_watch_pipeline
assert_markdown_watch_pipeline
assert_pdf_ingest_pipeline

uid="$(id -u "$ALMANAC_USER")"
if [[ -S "/run/user/$uid/bus" ]]; then
  su - "$ALMANAC_USER" -c "env XDG_RUNTIME_DIR='/run/user/$uid' DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/$uid/bus' ALMANAC_CONFIG_FILE='$CONFIG_TARGET' '$ALMANAC_REPO_DIR/bin/health.sh'"
else
  su - "$ALMANAC_USER" -c "env ALMANAC_CONFIG_FILE='$CONFIG_TARGET' '$ALMANAC_REPO_DIR/bin/health.sh'"
fi

echo
echo "Tearing Almanac back down..."
teardown

if id -u "$ALMANAC_USER" >/dev/null 2>&1; then
  echo "Expected service user '$ALMANAC_USER' to be removed." >&2
  exit 1
fi

if [[ -e "$ALMANAC_HOME" ]]; then
  echo "Expected $ALMANAC_HOME to be removed." >&2
  exit 1
fi

rm -f "$ANSWERS_FILE"
trap - EXIT
echo "Install smoke test completed successfully."
