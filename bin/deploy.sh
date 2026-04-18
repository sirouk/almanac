#!/usr/bin/env bash
set -euo pipefail

BOOTSTRAP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SELF_PATH="$BOOTSTRAP_DIR/bin/deploy.sh"
ANSWERS_FILE="${ALMANAC_INSTALL_ANSWERS_FILE:-}"
MODE=""
PRIVILEGED_MODE=""
DISCOVERED_CONFIG=""
ALMANAC_NAME="${ALMANAC_NAME:-almanac}"
TRACE_UNIX_USER="${TRACE_UNIX_USER:-}"
TRACE_SESSION_ID="${TRACE_SESSION_ID:-}"
TRACE_REQUEST_ID="${TRACE_REQUEST_ID:-}"
TRACE_LOG_LINES="${TRACE_LOG_LINES:-12}"
QMD_MCP_PORT="${QMD_MCP_PORT:-8181}"
PDF_INGEST_ENABLED="${PDF_INGEST_ENABLED:-1}"
PDF_INGEST_EXTRACTOR="${PDF_INGEST_EXTRACTOR:-auto}"
PDF_INGEST_COLLECTION_NAME="${PDF_INGEST_COLLECTION_NAME:-vault-pdf-ingest}"
VAULT_QMD_COLLECTION_MASK="${VAULT_QMD_COLLECTION_MASK:-**/*.{md,markdown,mdx,txt,text}}"
PDF_VISION_ENDPOINT="${PDF_VISION_ENDPOINT:-}"
PDF_VISION_MODEL="${PDF_VISION_MODEL:-}"
PDF_VISION_API_KEY="${PDF_VISION_API_KEY:-}"
PDF_VISION_MAX_PAGES="${PDF_VISION_MAX_PAGES:-6}"
NEXTCLOUD_TRUSTED_DOMAIN="${NEXTCLOUD_TRUSTED_DOMAIN:-almanac.your-tailnet.ts.net}"
NEXTCLOUD_VAULT_MOUNT_POINT="${NEXTCLOUD_VAULT_MOUNT_POINT:-/Vault}"
ENABLE_NEXTCLOUD="${ENABLE_NEXTCLOUD:-1}"
ENABLE_TAILSCALE_SERVE="${ENABLE_TAILSCALE_SERVE:-0}"
TAILSCALE_OPERATOR_USER="${TAILSCALE_OPERATOR_USER:-}"
TAILSCALE_QMD_PATH="${TAILSCALE_QMD_PATH:-/mcp}"
TAILSCALE_ALMANAC_MCP_PATH="${TAILSCALE_ALMANAC_MCP_PATH:-/almanac-mcp}"
VAULT_WATCH_DEBOUNCE_SECONDS="${VAULT_WATCH_DEBOUNCE_SECONDS:-5}"
VAULT_WATCH_RUN_EMBED="${VAULT_WATCH_RUN_EMBED:-auto}"
ENABLE_PRIVATE_GIT="${ENABLE_PRIVATE_GIT:-1}"
ENABLE_QUARTO="${ENABLE_QUARTO:-1}"
SEED_SAMPLE_VAULT="${SEED_SAMPLE_VAULT:-1}"
BACKUP_GIT_REMOTE="${BACKUP_GIT_REMOTE:-}"
ALMANAC_MCP_HOST="${ALMANAC_MCP_HOST:-127.0.0.1}"
ALMANAC_MCP_PORT="${ALMANAC_MCP_PORT:-8282}"
ALMANAC_NOTION_WEBHOOK_HOST="${ALMANAC_NOTION_WEBHOOK_HOST:-127.0.0.1}"
ALMANAC_NOTION_WEBHOOK_PORT="${ALMANAC_NOTION_WEBHOOK_PORT:-8283}"
ALMANAC_BOOTSTRAP_WINDOW_SECONDS="${ALMANAC_BOOTSTRAP_WINDOW_SECONDS:-3600}"
ALMANAC_BOOTSTRAP_PER_IP_LIMIT="${ALMANAC_BOOTSTRAP_PER_IP_LIMIT:-5}"
ALMANAC_BOOTSTRAP_GLOBAL_PENDING_LIMIT="${ALMANAC_BOOTSTRAP_GLOBAL_PENDING_LIMIT:-20}"
ALMANAC_BOOTSTRAP_PENDING_TTL_SECONDS="${ALMANAC_BOOTSTRAP_PENDING_TTL_SECONDS:-900}"
ALMANAC_AUTO_PROVISION_MAX_ATTEMPTS="${ALMANAC_AUTO_PROVISION_MAX_ATTEMPTS:-5}"
ALMANAC_AUTO_PROVISION_RETRY_BASE_SECONDS="${ALMANAC_AUTO_PROVISION_RETRY_BASE_SECONDS:-60}"
ALMANAC_AUTO_PROVISION_RETRY_MAX_SECONDS="${ALMANAC_AUTO_PROVISION_RETRY_MAX_SECONDS:-900}"
OPERATOR_NOTIFY_CHANNEL_PLATFORM="${OPERATOR_NOTIFY_CHANNEL_PLATFORM:-tui-only}"
OPERATOR_NOTIFY_CHANNEL_ID="${OPERATOR_NOTIFY_CHANNEL_ID:-}"
OPERATOR_GENERAL_CHANNEL_PLATFORM="${OPERATOR_GENERAL_CHANNEL_PLATFORM:-}"
OPERATOR_GENERAL_CHANNEL_ID="${OPERATOR_GENERAL_CHANNEL_ID:-}"
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
ALMANAC_MODEL_PRESET_CODEX="${ALMANAC_MODEL_PRESET_CODEX:-openai:codex}"
ALMANAC_MODEL_PRESET_OPUS="${ALMANAC_MODEL_PRESET_OPUS:-anthropic:claude-opus}"
ALMANAC_MODEL_PRESET_CHUTES="${ALMANAC_MODEL_PRESET_CHUTES:-chutes:auto-failover}"
ALMANAC_CURATOR_MODEL_PRESET="${ALMANAC_CURATOR_MODEL_PRESET:-codex}"
ALMANAC_CURATOR_CHANNELS="${ALMANAC_CURATOR_CHANNELS:-tui-only}"
CHUTES_MCP_URL="${CHUTES_MCP_URL:-}"
ALMANAC_UPSTREAM_REPO_URL="${ALMANAC_UPSTREAM_REPO_URL:-https://github.com/sirouk/almanac.git}"
ALMANAC_UPSTREAM_BRANCH="${ALMANAC_UPSTREAM_BRANCH:-main}"
ALMANAC_RELEASE_STATE_FILE="${ALMANAC_RELEASE_STATE_FILE:-}"
ALMANAC_OPERATOR_ARTIFACT_FILE="${ALMANAC_OPERATOR_ARTIFACT_FILE:-$BOOTSTRAP_DIR/.almanac-operator.env}"

normalize_vault_qmd_collection_mask() {
  local mask="${1:-}"

  if [[ -z "$mask" ]]; then
    printf '%s\n' '**/*.{md,markdown,mdx,txt,text}'
    return 0
  fi

  if [[ "$mask" =~ ^\*\*/\*\.\{md,markdown,mdx,txt,text\}+$ ]]; then
    printf '%s\n' '**/*.{md,markdown,mdx,txt,text}'
    return 0
  fi

  printf '%s\n' "$mask"
}

probe_path_status() {
  local path="${1:-}"

  python3 - "$path" <<'PY'
import os
import sys

path = sys.argv[1]
if not path:
    print("missing")
    raise SystemExit(0)
try:
    os.stat(path)
except FileNotFoundError:
    print("missing")
except PermissionError:
    print("exists-unreadable")
except OSError:
    print("missing")
else:
    print("exists")
PY
}

read_operator_artifact_config_file() {
  local -a artifact_hints=()
  local artifact_config=""
  local status=""

  mapfile -t artifact_hints < <(read_operator_artifact_hints || true)
  artifact_config="${artifact_hints[3]:-}"
  if [[ -n "$artifact_config" ]]; then
    status="$(probe_path_status "$artifact_config")"
    if [[ "$status" == "exists" || "$status" == "exists-unreadable" ]]; then
      printf '%s\n' "$artifact_config"
      return 0
    fi
  fi

  return 1
}

read_operator_artifact_hints() {
  local artifact="${ALMANAC_OPERATOR_ARTIFACT_FILE:-$BOOTSTRAP_DIR/.almanac-operator.env}"

  if [[ ! -r "$artifact" ]]; then
    return 1
  fi

  (
    ALMANAC_OPERATOR_DEPLOYED_USER=""
    ALMANAC_OPERATOR_DEPLOYED_REPO_DIR=""
    ALMANAC_OPERATOR_DEPLOYED_PRIV_DIR=""
    ALMANAC_OPERATOR_DEPLOYED_CONFIG_FILE=""
    # shellcheck disable=SC1090
    source "$artifact"
    printf '%s\n' "${ALMANAC_OPERATOR_DEPLOYED_USER:-}"
    printf '%s\n' "${ALMANAC_OPERATOR_DEPLOYED_REPO_DIR:-}"
    printf '%s\n' "${ALMANAC_OPERATOR_DEPLOYED_PRIV_DIR:-}"
    printf '%s\n' "${ALMANAC_OPERATOR_DEPLOYED_CONFIG_FILE:-}"
  )
}

resolve_user_home() {
  local user="${1:-}"
  local home_dir=""

  if [[ -z "$user" ]]; then
    return 1
  fi

  home_dir="$(getent passwd "$user" 2>/dev/null | cut -d: -f6)"
  if [[ -z "$home_dir" ]]; then
    home_dir="/home/$user"
  fi

  printf '%s\n' "$home_dir"
}

usage() {
  cat <<'EOF'
Usage:
  deploy.sh                # interactive menu
  deploy.sh install
  deploy.sh upgrade
  deploy.sh enrollment-status
  deploy.sh enrollment-trace [--unix-user USER | --session-id onb_xxx | --request-id req_xxx]
  deploy.sh enrollment-align
  deploy.sh enrollment-reset
  deploy.sh curator-setup
  deploy.sh agent-payload
  deploy.sh write-config
  deploy.sh remove
  deploy.sh health

Compatibility:
  deploy.sh --write-config-only
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    install|upgrade|enrollment-status|enrollment-trace|enrollment-align|enrollment-reset|curator-setup|agent-payload|agent|write-config|remove|health|menu)
      MODE="$1"
      shift
      ;;
    --unix-user)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for --unix-user" >&2
        exit 1
      fi
      TRACE_UNIX_USER="$2"
      shift 2
      ;;
    --session-id)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for --session-id" >&2
        exit 1
      fi
      TRACE_SESSION_ID="$2"
      shift 2
      ;;
    --request-id)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for --request-id" >&2
        exit 1
      fi
      TRACE_REQUEST_ID="$2"
      shift 2
      ;;
    --log-lines)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for --log-lines" >&2
        exit 1
      fi
      TRACE_LOG_LINES="$2"
      shift 2
      ;;
    --write-config-only)
      MODE="write-config"
      shift
      ;;
    --apply-install)
      PRIVILEGED_MODE="install"
      if [[ $# -gt 1 && "${2#-}" != "$2" ]]; then
        shift
      elif [[ $# -gt 1 ]]; then
        ANSWERS_FILE="$2"
        shift 2
      else
        shift
      fi
      ;;
    --apply-remove)
      PRIVILEGED_MODE="remove"
      if [[ $# -gt 1 && "${2#-}" != "$2" ]]; then
        shift
      elif [[ $# -gt 1 ]]; then
        ANSWERS_FILE="$2"
        shift 2
      else
        shift
      fi
      ;;
    --apply-upgrade)
      PRIVILEGED_MODE="upgrade"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

ask() {
  local prompt="$1"
  local default="${2:-}"
  local answer=""

  if [[ -n "$default" ]]; then
    read -r -p "$prompt [$default]: " answer
  else
    read -r -p "$prompt: " answer
  fi

  if [[ -z "$answer" ]]; then
    answer="$default"
  fi

  printf '%s' "$answer"
}

ask_yes_no() {
  local prompt="$1"
  local default="$2"
  local answer=""
  local hint="y/N"

  if [[ "$default" == "1" ]]; then
    hint="Y/n"
  fi

  read -r -p "$prompt [$hint]: " answer
  if [[ -z "$answer" ]]; then
    answer="$default"
  fi

  case "$answer" in
    y|Y|yes|YES|1) echo 1 ;;
    *) echo 0 ;;
  esac
}

ask_secret() {
  local prompt="$1"
  local answer=""

  read -r -s -p "$prompt: " answer
  echo
  printf '%s' "$answer"
}

mask_secret() {
  local value="${1:-}"
  local length="${#value}"

  if (( length == 0 )); then
    printf '%s' ""
    return 0
  fi

  if (( length <= 4 )); then
    printf '%*s' "$length" '' | tr ' ' '*'
    return 0
  fi

  printf '%*s%s' "$((length - 4))" '' "${value: -4}" | tr ' ' '*'
}

normalize_optional_answer() {
  case "${1:-}" in
    none|NONE|off|OFF|-)
      printf '%s' ""
      ;;
    *)
      printf '%s' "${1:-}"
      ;;
  esac
}

ask_secret_with_default() {
  local prompt="$1"
  local default="${2:-}"
  local answer=""
  local masked_default=""

  if [[ -n "$default" ]]; then
    masked_default="$(mask_secret "$default")"
    read -r -s -p "$prompt [$masked_default]: " answer
  else
    read -r -s -p "$prompt: " answer
  fi
  echo

  if [[ -z "$answer" ]]; then
    answer="$default"
  fi

  normalize_optional_answer "$answer"
}

ask_secret_keep_default() {
  local prompt="$1"
  local default="${2:-}"
  local answer=""
  local masked_default=""

  if [[ -n "$default" ]]; then
    masked_default="$(mask_secret "$default")"
    read -r -s -p "$prompt [$masked_default]: " answer
  else
    read -r -s -p "$prompt: " answer
  fi
  echo

  if [[ -z "$answer" ]]; then
    answer="$default"
  fi

  printf '%s' "$answer"
}

choose_mode() {
  local answer=""

  cat <<'EOF'
Almanac deploy menu

  1) Install / repair from current checkout
  2) Upgrade deployed host from configured upstream
  3) Write config only
  4) Enrollment status
  5) Enrollment trace
  6) Enrollment align / repair
  7) Enrollment reset / cleanup
  8) Curator setup / repair
  9) Print agent payload
 10) Health check
 11) Remove / teardown
 12) Exit
EOF

  while true; do
    read -r -p "Choose mode [1]: " answer
    case "${answer:-1}" in
      1) MODE="install"; return 0 ;;
      2) MODE="upgrade"; return 0 ;;
      3) MODE="write-config"; return 0 ;;
      4) MODE="enrollment-status"; return 0 ;;
      5) MODE="enrollment-trace"; return 0 ;;
      6) MODE="enrollment-align"; return 0 ;;
      7) MODE="enrollment-reset"; return 0 ;;
      8) MODE="curator-setup"; return 0 ;;
      9) MODE="agent-payload"; return 0 ;;
      10) MODE="health"; return 0 ;;
      11) MODE="remove"; return 0 ;;
      12) exit 0 ;;
      *) echo "Please choose 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, or 12." ;;
    esac
  done
}

detect_tailscale() {
  TAILSCALE_DNS_NAME=""
  TAILSCALE_HOST_NAME=""
  TAILSCALE_IPV4=""
  TAILSCALE_TAILNET=""

  if ! command -v tailscale >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1; then
    return 0
  fi

  local ts_json=""
  ts_json="$(tailscale status --json 2>/dev/null || true)"
  if [[ -z "$ts_json" ]]; then
    return 0
  fi

  local ts_info=""
  ts_info="$(
    printf '%s' "$ts_json" | python3 -c '
import json
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    raise SystemExit(0)

self_info = data.get("Self") or {}
current_tailnet = data.get("CurrentTailnet") or {}
ips = self_info.get("TailscaleIPs") or data.get("TailscaleIPs") or []

values = {
    "dns": (self_info.get("DNSName") or "").rstrip("."),
    "host": self_info.get("HostName") or "",
    "ipv4": next((ip for ip in ips if "." in ip), ""),
    "tailnet": current_tailnet.get("MagicDNSSuffix") or "",
}

for key, value in values.items():
    if value:
        print(f"{key}={value}")
'
  )"

  while IFS='=' read -r key value; do
    case "$key" in
      dns) TAILSCALE_DNS_NAME="$value" ;;
      host) TAILSCALE_HOST_NAME="$value" ;;
      ipv4) TAILSCALE_IPV4="$value" ;;
      tailnet) TAILSCALE_TAILNET="$value" ;;
    esac
  done <<<"$ts_info"
}

detect_tailscale_serve() {
  TAILSCALE_SERVE_HOST=""
  TAILSCALE_SERVE_HAS_ROOT="0"
  TAILSCALE_SERVE_HAS_QMD="0"
  TAILSCALE_SERVE_HAS_ALMANAC_MCP="0"

  if ! command -v tailscale >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1; then
    return 0
  fi

  local ts_json=""
  ts_json="$(tailscale serve status --json 2>/dev/null || true)"
  if [[ -z "$ts_json" ]]; then
    return 0
  fi

  local ts_info=""
  ts_info="$(
    TAILSCALE_SERVE_JSON="$ts_json" python3 - "$QMD_MCP_PORT" "$TAILSCALE_QMD_PATH" "$ALMANAC_MCP_PORT" "$TAILSCALE_ALMANAC_MCP_PATH" <<'PY'
import json
import os
import sys

try:
    data = json.loads(os.environ["TAILSCALE_SERVE_JSON"])
except Exception:
    raise SystemExit(0)

qmd_port = sys.argv[1]
qmd_path = sys.argv[2]
almanac_mcp_port = sys.argv[3]
almanac_mcp_path = sys.argv[4]
web = data.get("Web") or {}

host = ""
has_root = False
has_qmd = False
has_almanac_mcp = False

for hostport, entry in web.items():
    if not host:
        host = hostport.rsplit(":", 1)[0]
    handlers = (entry or {}).get("Handlers") or {}
    if "/" in handlers:
        has_root = True
    if qmd_path in handlers:
        has_qmd = True
    if almanac_mcp_path in handlers:
        has_almanac_mcp = True
    for path, handler in handlers.items():
        proxy = str((handler or {}).get("Proxy") or "")
        if path == qmd_path or f":{qmd_port}/mcp" in proxy or proxy.endswith("/mcp"):
            has_qmd = True
        if path == almanac_mcp_path or f":{almanac_mcp_port}/mcp" in proxy:
            has_almanac_mcp = True

values = {
    "host": host,
    "root": "1" if has_root else "0",
    "qmd": "1" if has_qmd else "0",
    "almanac_mcp": "1" if has_almanac_mcp else "0",
}

for key, value in values.items():
    if value:
        print(f"{key}={value}")
PY
  )"

  while IFS='=' read -r key value; do
    case "$key" in
      host) TAILSCALE_SERVE_HOST="$value" ;;
      root) TAILSCALE_SERVE_HAS_ROOT="$value" ;;
      qmd) TAILSCALE_SERVE_HAS_QMD="$value" ;;
      almanac_mcp) TAILSCALE_SERVE_HAS_ALMANAC_MCP="$value" ;;
    esac
  done <<<"$ts_info"
}

resolve_agent_qmd_endpoint() {
  detect_tailscale
  detect_tailscale_serve

  AGENT_QMD_TAILNET_HOST="${TAILSCALE_SERVE_HOST:-${TAILSCALE_DNS_NAME:-$NEXTCLOUD_TRUSTED_DOMAIN}}"
  AGENT_QMD_TAILNET_URL=""
  AGENT_QMD_URL="http://127.0.0.1:$QMD_MCP_PORT/mcp"
  AGENT_QMD_URL_MODE="local"
  AGENT_QMD_ROUTE_STATUS="local_only"

  if [[ -n "$AGENT_QMD_TAILNET_HOST" ]]; then
    AGENT_QMD_TAILNET_URL="https://${AGENT_QMD_TAILNET_HOST}${TAILSCALE_QMD_PATH}"
  fi

  if [[ -n "$TAILSCALE_DNS_NAME" || -n "$TAILSCALE_SERVE_HOST" || "$ENABLE_TAILSCALE_SERVE" == "1" ]]; then
    if [[ -n "$AGENT_QMD_TAILNET_URL" ]]; then
      AGENT_QMD_URL="$AGENT_QMD_TAILNET_URL"
      AGENT_QMD_URL_MODE="tailnet"
      if [[ "$TAILSCALE_SERVE_HAS_QMD" == "1" ]]; then
        AGENT_QMD_ROUTE_STATUS="live"
      else
        AGENT_QMD_ROUTE_STATUS="expected"
      fi
    fi
  fi
}

resolve_agent_control_plane_endpoint() {
  detect_tailscale
  detect_tailscale_serve

  AGENT_ALMANAC_MCP_TAILNET_HOST="${TAILSCALE_SERVE_HOST:-${TAILSCALE_DNS_NAME:-$NEXTCLOUD_TRUSTED_DOMAIN}}"
  AGENT_ALMANAC_MCP_TAILNET_URL=""
  AGENT_ALMANAC_MCP_URL="http://${ALMANAC_MCP_HOST:-127.0.0.1}:${ALMANAC_MCP_PORT:-8282}/mcp"
  AGENT_ALMANAC_MCP_URL_MODE="local"
  AGENT_ALMANAC_MCP_ROUTE_STATUS="local_only"

  if [[ -n "$AGENT_ALMANAC_MCP_TAILNET_HOST" ]]; then
    AGENT_ALMANAC_MCP_TAILNET_URL="https://${AGENT_ALMANAC_MCP_TAILNET_HOST}${TAILSCALE_ALMANAC_MCP_PATH}"
  fi

  if [[ -n "$TAILSCALE_DNS_NAME" || -n "$TAILSCALE_SERVE_HOST" || "$ENABLE_TAILSCALE_SERVE" == "1" ]]; then
    if [[ -n "$AGENT_ALMANAC_MCP_TAILNET_URL" ]]; then
      AGENT_ALMANAC_MCP_URL="$AGENT_ALMANAC_MCP_TAILNET_URL"
      AGENT_ALMANAC_MCP_URL_MODE="tailnet"
      if [[ "$TAILSCALE_SERVE_HAS_ALMANAC_MCP" == "1" ]]; then
        AGENT_ALMANAC_MCP_ROUTE_STATUS="live"
      else
        AGENT_ALMANAC_MCP_ROUTE_STATUS="expected"
      fi
    fi
  fi
}

detect_github_repo() {
  GITHUB_REPO_URL=""
  GITHUB_SKILL_RAW_URL=""
  GITHUB_SKILL_IDENTIFIER=""
  GITHUB_RECONCILER_SKILL_RAW_URL=""
  GITHUB_RECONCILER_SKILL_IDENTIFIER=""

  if ! command -v git >/dev/null 2>&1; then
    GITHUB_REPO_URL="https://github.com/sirouk/almanac"
    GITHUB_SKILL_RAW_URL="https://raw.githubusercontent.com/sirouk/almanac/main/skills/almanac-qmd-mcp/SKILL.md"
    GITHUB_SKILL_IDENTIFIER="sirouk/almanac/skills/almanac-qmd-mcp"
    GITHUB_RECONCILER_SKILL_RAW_URL="https://raw.githubusercontent.com/sirouk/almanac/main/skills/almanac-vault-reconciler/SKILL.md"
    GITHUB_RECONCILER_SKILL_IDENTIFIER="sirouk/almanac/skills/almanac-vault-reconciler"
    return 0
  fi

  local remote_url="" branch="" owner_repo=""
  remote_url="$(git -C "$ALMANAC_REPO_DIR" remote get-url origin 2>/dev/null || true)"
  branch="$(git -C "$ALMANAC_REPO_DIR" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
  branch="${branch:-main}"

  case "$remote_url" in
    https://github.com/*)
      owner_repo="${remote_url#https://github.com/}"
      ;;
    git@github.com:*)
      owner_repo="${remote_url#git@github.com:}"
      ;;
    *)
      owner_repo=""
      ;;
  esac

  owner_repo="${owner_repo%.git}"
  if [[ -n "$owner_repo" ]]; then
    GITHUB_REPO_URL="https://github.com/$owner_repo"
    GITHUB_SKILL_RAW_URL="https://raw.githubusercontent.com/$owner_repo/$branch/skills/almanac-qmd-mcp/SKILL.md"
    GITHUB_SKILL_IDENTIFIER="$owner_repo/skills/almanac-qmd-mcp"
    GITHUB_RECONCILER_SKILL_RAW_URL="https://raw.githubusercontent.com/$owner_repo/$branch/skills/almanac-vault-reconciler/SKILL.md"
    GITHUB_RECONCILER_SKILL_IDENTIFIER="$owner_repo/skills/almanac-vault-reconciler"
  else
    GITHUB_REPO_URL="https://github.com/sirouk/almanac"
    GITHUB_SKILL_RAW_URL="https://raw.githubusercontent.com/sirouk/almanac/main/skills/almanac-qmd-mcp/SKILL.md"
    GITHUB_SKILL_IDENTIFIER="sirouk/almanac/skills/almanac-qmd-mcp"
    GITHUB_RECONCILER_SKILL_RAW_URL="https://raw.githubusercontent.com/sirouk/almanac/main/skills/almanac-vault-reconciler/SKILL.md"
    GITHUB_RECONCILER_SKILL_IDENTIFIER="sirouk/almanac/skills/almanac-vault-reconciler"
  fi
}

discover_existing_config() {
  local -a artifact_hints=()
  local candidate=""
  local explicit_config=""
  local artifact_config=""
  local artifact_user="" artifact_repo="" artifact_priv="" artifact_home=""
  local status=""
  explicit_config="${ALMANAC_CONFIG_FILE:-}"
  mapfile -t artifact_hints < <(read_operator_artifact_hints || true)
  artifact_user="${artifact_hints[0]:-}"
  artifact_repo="${artifact_hints[1]:-}"
  artifact_priv="${artifact_hints[2]:-}"
  artifact_config="${artifact_hints[3]:-}"

  DISCOVERED_CONFIG=""

  if [[ -n "$explicit_config" ]]; then
    DISCOVERED_CONFIG="$explicit_config"
    return 0
  fi
  if [[ -n "$artifact_config" ]]; then
    DISCOVERED_CONFIG="$artifact_config"
    return 0
  fi

  local -a candidates=()

  if [[ -n "$artifact_priv" ]]; then
    candidates+=(
      "$artifact_priv/config/almanac.env"
      "$artifact_priv/almanac.env"
    )
  fi

  if [[ -n "$artifact_repo" ]]; then
    candidates+=(
      "$artifact_repo/almanac-priv/config/almanac.env"
      "$artifact_repo/config/almanac.env"
    )
  fi

  if [[ -n "$artifact_user" ]]; then
    artifact_home="$(resolve_user_home "$artifact_user" || true)"
    if [[ -n "$artifact_home" ]]; then
      candidates+=(
        "$artifact_home/almanac/almanac-priv/config/almanac.env"
        "$artifact_home/almanac-priv/config/almanac.env"
      )
    fi
  fi

  candidates+=(
    "/home/almanac/almanac/almanac-priv/config/almanac.env"
    "$HOME/almanac/almanac-priv/config/almanac.env"
    "$HOME/almanac/almanac/almanac-priv/config/almanac.env"
    "$BOOTSTRAP_DIR/almanac-priv/config/almanac.env"
    "$BOOTSTRAP_DIR/config/almanac.env"
  )

  for candidate in "${candidates[@]}"; do
    status="$(probe_path_status "$candidate")"
    if [[ "$status" == "exists" || "$status" == "exists-unreadable" ]]; then
      DISCOVERED_CONFIG="$candidate"
      return 0
    fi
  done

  candidate="$(find /home -maxdepth 5 -path '*/almanac/almanac-priv/config/almanac.env' -print -quit 2>/dev/null || true)"
  status="$(probe_path_status "$candidate")"
  if [[ "$status" == "exists" || "$status" == "exists-unreadable" ]]; then
    DISCOVERED_CONFIG="$candidate"
    return 0
  fi

  return 1
}

load_detected_config() {
  if discover_existing_config; then
    if [[ ! -r "$DISCOVERED_CONFIG" ]]; then
      return 1
    fi
    # shellcheck disable=SC1090
    source "$DISCOVERED_CONFIG"
    VAULT_QMD_COLLECTION_MASK="$(normalize_vault_qmd_collection_mask "${VAULT_QMD_COLLECTION_MASK:-}")"
    return 0
  fi

  return 1
}

reload_runtime_config_from_file() {
  local config_path="${1:-$CONFIG_TARGET}"

  if [[ -n "$config_path" && -f "$config_path" && -r "$config_path" ]]; then
    # shellcheck disable=SC1090
    source "$config_path"
    VAULT_QMD_COLLECTION_MASK="$(normalize_vault_qmd_collection_mask "${VAULT_QMD_COLLECTION_MASK:-}")"
    return 0
  fi

  return 1
}

resolve_pdf_vision_endpoint() {
  local endpoint="${1:-${PDF_VISION_ENDPOINT:-}}"

  endpoint="${endpoint#"${endpoint%%[![:space:]]*}"}"
  endpoint="${endpoint%"${endpoint##*[![:space:]]}"}"
  endpoint="${endpoint%/}"

  if [[ -z "$endpoint" ]]; then
    return 1
  fi

  case "$endpoint" in
    */chat/completions)
      printf '%s\n' "$endpoint"
      ;;
    */completions)
      printf '%s\n' "${endpoint%/completions}/chat/completions"
      ;;
    */v1)
      printf '%s/chat/completions\n' "$endpoint"
      ;;
    *)
      printf '%s\n' "$endpoint"
      ;;
  esac
}

random_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 16
  else
    tr -dc 'a-f0-9' </dev/urandom | head -c 32
  fi
}

write_kv() {
  local key="$1"
  local value="${2:-}"
  printf '%s=%q\n' "$key" "$value"
}

default_curator_telegram_onboarding_enabled() {
  local channels=",${ALMANAC_CURATOR_CHANNELS:-tui-only},"
  if [[ "$channels" == *",telegram,"* || "${OPERATOR_NOTIFY_CHANNEL_PLATFORM:-}" == "telegram" ]]; then
    printf '%s' "1"
  else
    printf '%s' "0"
  fi
}

default_curator_discord_onboarding_enabled() {
  local channels=",${ALMANAC_CURATOR_CHANNELS:-tui-only},"
  if [[ "$channels" == *",discord,"* ]]; then
    printf '%s' "1"
  else
    printf '%s' "0"
  fi
}

normalize_runtime_config_defaults() {
  if [[ -z "${ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED:-}" ]]; then
    ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED="$(default_curator_telegram_onboarding_enabled)"
  fi
  if [[ -z "${ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED:-}" ]]; then
    ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED="$(default_curator_discord_onboarding_enabled)"
  fi
}

emit_runtime_config() {
  normalize_runtime_config_defaults
  {
    write_kv ALMANAC_NAME "$ALMANAC_NAME"
    write_kv ALMANAC_USER "$ALMANAC_USER"
    write_kv ALMANAC_HOME "$ALMANAC_HOME"
    write_kv ALMANAC_REPO_DIR "$ALMANAC_REPO_DIR"
    write_kv ALMANAC_PRIV_DIR "$ALMANAC_PRIV_DIR"
    write_kv ALMANAC_PRIV_CONFIG_DIR "$ALMANAC_PRIV_CONFIG_DIR"
    write_kv VAULT_DIR "$VAULT_DIR"
    write_kv STATE_DIR "$STATE_DIR"
    write_kv NEXTCLOUD_STATE_DIR "$NEXTCLOUD_STATE_DIR"
    write_kv RUNTIME_DIR "$RUNTIME_DIR"
    write_kv PUBLISHED_DIR "$PUBLISHED_DIR"
    write_kv ALMANAC_DB_PATH "${ALMANAC_DB_PATH:-$STATE_DIR/almanac-control.sqlite3}"
    write_kv ALMANAC_AGENTS_STATE_DIR "${ALMANAC_AGENTS_STATE_DIR:-$STATE_DIR/agents}"
    write_kv ALMANAC_CURATOR_DIR "${ALMANAC_CURATOR_DIR:-$STATE_DIR/curator}"
    write_kv ALMANAC_CURATOR_MANIFEST "${ALMANAC_CURATOR_MANIFEST:-$STATE_DIR/curator/manifest.json}"
    write_kv ALMANAC_CURATOR_HERMES_HOME "${ALMANAC_CURATOR_HERMES_HOME:-$STATE_DIR/curator/hermes-home}"
    write_kv ALMANAC_ARCHIVED_AGENTS_DIR "${ALMANAC_ARCHIVED_AGENTS_DIR:-$STATE_DIR/archived-agents}"
    write_kv QMD_INDEX_NAME "$QMD_INDEX_NAME"
    write_kv QMD_COLLECTION_NAME "$QMD_COLLECTION_NAME"
    write_kv VAULT_QMD_COLLECTION_MASK "$(normalize_vault_qmd_collection_mask "${VAULT_QMD_COLLECTION_MASK:-}")"
    write_kv PDF_INGEST_COLLECTION_NAME "$PDF_INGEST_COLLECTION_NAME"
    write_kv QMD_RUN_EMBED "$QMD_RUN_EMBED"
    write_kv QMD_MCP_PORT "$QMD_MCP_PORT"
    write_kv ALMANAC_MCP_HOST "$ALMANAC_MCP_HOST"
    write_kv ALMANAC_MCP_PORT "$ALMANAC_MCP_PORT"
    write_kv ALMANAC_NOTION_WEBHOOK_HOST "$ALMANAC_NOTION_WEBHOOK_HOST"
    write_kv ALMANAC_NOTION_WEBHOOK_PORT "$ALMANAC_NOTION_WEBHOOK_PORT"
    write_kv ALMANAC_BOOTSTRAP_WINDOW_SECONDS "$ALMANAC_BOOTSTRAP_WINDOW_SECONDS"
    write_kv ALMANAC_BOOTSTRAP_PER_IP_LIMIT "$ALMANAC_BOOTSTRAP_PER_IP_LIMIT"
    write_kv ALMANAC_BOOTSTRAP_GLOBAL_PENDING_LIMIT "$ALMANAC_BOOTSTRAP_GLOBAL_PENDING_LIMIT"
    write_kv ALMANAC_BOOTSTRAP_PENDING_TTL_SECONDS "$ALMANAC_BOOTSTRAP_PENDING_TTL_SECONDS"
    write_kv ALMANAC_AUTO_PROVISION_MAX_ATTEMPTS "$ALMANAC_AUTO_PROVISION_MAX_ATTEMPTS"
    write_kv ALMANAC_AUTO_PROVISION_RETRY_BASE_SECONDS "$ALMANAC_AUTO_PROVISION_RETRY_BASE_SECONDS"
    write_kv ALMANAC_AUTO_PROVISION_RETRY_MAX_SECONDS "$ALMANAC_AUTO_PROVISION_RETRY_MAX_SECONDS"
    write_kv PDF_INGEST_ENABLED "$PDF_INGEST_ENABLED"
    write_kv PDF_INGEST_EXTRACTOR "$PDF_INGEST_EXTRACTOR"
    write_kv PDF_INGEST_TRIGGER_QMD_REFRESH "${PDF_INGEST_TRIGGER_QMD_REFRESH:-1}"
    write_kv PDF_INGEST_WATCH_DEBOUNCE_SECONDS "${PDF_INGEST_WATCH_DEBOUNCE_SECONDS:-10}"
    write_kv PDF_INGEST_DOCLING_FORCE_OCR "${PDF_INGEST_DOCLING_FORCE_OCR:-0}"
    write_kv PDF_VISION_ENDPOINT "${PDF_VISION_ENDPOINT:-}"
    write_kv PDF_VISION_MODEL "${PDF_VISION_MODEL:-}"
    write_kv PDF_VISION_API_KEY "${PDF_VISION_API_KEY:-}"
    write_kv PDF_VISION_MAX_PAGES "${PDF_VISION_MAX_PAGES:-6}"
    write_kv VAULT_WATCH_DEBOUNCE_SECONDS "${VAULT_WATCH_DEBOUNCE_SECONDS:-5}"
    write_kv VAULT_WATCH_RUN_EMBED "${VAULT_WATCH_RUN_EMBED:-auto}"
    write_kv BACKUP_GIT_BRANCH "$BACKUP_GIT_BRANCH"
    write_kv BACKUP_GIT_REMOTE "$BACKUP_GIT_REMOTE"
    write_kv BACKUP_GIT_AUTHOR_NAME "$BACKUP_GIT_AUTHOR_NAME"
    write_kv BACKUP_GIT_AUTHOR_EMAIL "$BACKUP_GIT_AUTHOR_EMAIL"
    write_kv NEXTCLOUD_PORT "$NEXTCLOUD_PORT"
    write_kv NEXTCLOUD_TRUSTED_DOMAIN "$NEXTCLOUD_TRUSTED_DOMAIN"
    write_kv POSTGRES_DB "$POSTGRES_DB"
    write_kv POSTGRES_USER "$POSTGRES_USER"
    write_kv POSTGRES_PASSWORD "$POSTGRES_PASSWORD"
    write_kv NEXTCLOUD_ADMIN_USER "$NEXTCLOUD_ADMIN_USER"
    write_kv NEXTCLOUD_ADMIN_PASSWORD "$NEXTCLOUD_ADMIN_PASSWORD"
    write_kv NEXTCLOUD_VAULT_MOUNT_POINT "${NEXTCLOUD_VAULT_MOUNT_POINT:-/Vault}"
    write_kv OPERATOR_NOTIFY_CHANNEL_PLATFORM "${OPERATOR_NOTIFY_CHANNEL_PLATFORM:-tui-only}"
    write_kv OPERATOR_NOTIFY_CHANNEL_ID "${OPERATOR_NOTIFY_CHANNEL_ID:-}"
    write_kv ALMANAC_OPERATOR_TELEGRAM_USER_IDS "${ALMANAC_OPERATOR_TELEGRAM_USER_IDS:-}"
    write_kv ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED "${ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED:-}"
    write_kv ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED "${ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED:-}"
    write_kv ALMANAC_ONBOARDING_WINDOW_SECONDS "${ALMANAC_ONBOARDING_WINDOW_SECONDS:-3600}"
    write_kv ALMANAC_ONBOARDING_PER_USER_LIMIT "${ALMANAC_ONBOARDING_PER_USER_LIMIT:-${ALMANAC_ONBOARDING_PER_TELEGRAM_USER_LIMIT:-3}}"
    write_kv ALMANAC_ONBOARDING_PER_TELEGRAM_USER_LIMIT "${ALMANAC_ONBOARDING_PER_TELEGRAM_USER_LIMIT:-3}"
    write_kv ALMANAC_ONBOARDING_GLOBAL_PENDING_LIMIT "${ALMANAC_ONBOARDING_GLOBAL_PENDING_LIMIT:-20}"
    write_kv ALMANAC_ONBOARDING_UPDATE_FAILURE_LIMIT "${ALMANAC_ONBOARDING_UPDATE_FAILURE_LIMIT:-3}"
    write_kv OPERATOR_GENERAL_CHANNEL_PLATFORM "${OPERATOR_GENERAL_CHANNEL_PLATFORM:-}"
    write_kv OPERATOR_GENERAL_CHANNEL_ID "${OPERATOR_GENERAL_CHANNEL_ID:-}"
    write_kv TELEGRAM_BOT_TOKEN "${TELEGRAM_BOT_TOKEN:-}"
    write_kv ALMANAC_MODEL_PRESET_CODEX "${ALMANAC_MODEL_PRESET_CODEX:-openai:codex}"
    write_kv ALMANAC_MODEL_PRESET_OPUS "${ALMANAC_MODEL_PRESET_OPUS:-anthropic:claude-opus}"
    write_kv ALMANAC_MODEL_PRESET_CHUTES "${ALMANAC_MODEL_PRESET_CHUTES:-chutes:auto-failover}"
    write_kv ALMANAC_CURATOR_MODEL_PRESET "${ALMANAC_CURATOR_MODEL_PRESET:-codex}"
    write_kv ALMANAC_CURATOR_CHANNELS "${ALMANAC_CURATOR_CHANNELS:-tui-only}"
    write_kv CHUTES_MCP_URL "${CHUTES_MCP_URL:-}"
    write_kv ALMANAC_UPSTREAM_REPO_URL "${ALMANAC_UPSTREAM_REPO_URL:-https://github.com/sirouk/almanac.git}"
    write_kv ALMANAC_UPSTREAM_BRANCH "${ALMANAC_UPSTREAM_BRANCH:-main}"
    write_kv ALMANAC_RELEASE_STATE_FILE "${ALMANAC_RELEASE_STATE_FILE:-$STATE_DIR/almanac-release.json}"
    write_kv ENABLE_NEXTCLOUD "$ENABLE_NEXTCLOUD"
    write_kv ENABLE_TAILSCALE_SERVE "$ENABLE_TAILSCALE_SERVE"
    write_kv TAILSCALE_OPERATOR_USER "${TAILSCALE_OPERATOR_USER:-}"
    write_kv TAILSCALE_QMD_PATH "${TAILSCALE_QMD_PATH:-/mcp}"
    write_kv TAILSCALE_ALMANAC_MCP_PATH "${TAILSCALE_ALMANAC_MCP_PATH:-/almanac-mcp}"
    write_kv ENABLE_PRIVATE_GIT "$ENABLE_PRIVATE_GIT"
    write_kv ENABLE_QUARTO "$ENABLE_QUARTO"
    write_kv SEED_SAMPLE_VAULT "$SEED_SAMPLE_VAULT"
    write_kv QUARTO_PROJECT_DIR "$QUARTO_PROJECT_DIR"
    write_kv QUARTO_OUTPUT_DIR "$QUARTO_OUTPUT_DIR"
  }
}

write_runtime_config() {
  local target="$1"
  mkdir -p "$(dirname "$target")"
  emit_runtime_config >"$target"
  chmod 600 "$target"
}

write_answers_file() {
  local target="$1"
  mkdir -p "$(dirname "$target")"
  {
    emit_runtime_config
    write_kv ALMANAC_INSTALL_PUBLIC_GIT "${ALMANAC_INSTALL_PUBLIC_GIT:-0}"
    write_kv WIPE_NEXTCLOUD_STATE "${WIPE_NEXTCLOUD_STATE:-0}"
    write_kv REMOVE_PUBLIC_REPO "${REMOVE_PUBLIC_REPO:-1}"
    write_kv REMOVE_USER_TOOLING "${REMOVE_USER_TOOLING:-1}"
    write_kv REMOVE_SERVICE_USER "${REMOVE_SERVICE_USER:-0}"
  } >"$target"
  chmod 600 "$target"
}

seed_private_repo() {
  local target_dir="$1"
  mkdir -p "$target_dir"
  if [[ -d "$BOOTSTRAP_DIR/templates/almanac-priv/" ]]; then
    rsync -a --ignore-existing "$BOOTSTRAP_DIR/templates/almanac-priv/" "$target_dir/"
  fi
}

sync_public_repo() {
  sync_public_repo_from_source "$BOOTSTRAP_DIR" "$ALMANAC_REPO_DIR"
}

sync_public_repo_from_source() {
  local source_dir="$1"
  local target_dir="$2"
  local same_path=""

  same_path="$(
    python3 - "$source_dir" "$target_dir" <<'PY'
import os
import sys

source = os.path.realpath(sys.argv[1])
target = os.path.realpath(sys.argv[2])
print("1" if source == target else "0")
PY
  )"

  if [[ "$same_path" == "1" ]]; then
    return 0
  fi

  mkdir -p "$target_dir"
  rsync -a --delete \
    --exclude '.git/' \
    --exclude 'almanac-priv/' \
    --exclude '.almanac-operator.env' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.DS_Store' \
    "$source_dir/" "$target_dir/"
}

git_head_commit() {
  local repo_dir="$1"
  git -C "$repo_dir" rev-parse HEAD 2>/dev/null || true
}

git_head_branch() {
  local repo_dir="$1"
  git -C "$repo_dir" symbolic-ref --quiet --short HEAD 2>/dev/null ||
    git -C "$repo_dir" rev-parse --abbrev-ref HEAD 2>/dev/null || true
}

git_origin_url() {
  local repo_dir="$1"
  git -C "$repo_dir" remote get-url origin 2>/dev/null || true
}

write_release_state() {
  local source_kind="$1"
  local deployed_commit="$2"
  local source_repo_url="${3:-}"
  local source_branch="${4:-}"
  local source_path="${5:-}"
  local target="${ALMANAC_RELEASE_STATE_FILE:-$STATE_DIR/almanac-release.json}"

  mkdir -p "$(dirname "$target")"
  python3 - "$target" "$source_kind" "$deployed_commit" "$source_repo_url" "$source_branch" "$source_path" "${ALMANAC_UPSTREAM_REPO_URL:-}" "${ALMANAC_UPSTREAM_BRANCH:-}" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

target = Path(sys.argv[1])
payload = {
    "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "deployed_from": sys.argv[2],
    "deployed_commit": sys.argv[3],
    "deployed_source_repo": sys.argv[4],
    "deployed_source_branch": sys.argv[5],
    "deployed_source_path": sys.argv[6],
    "tracked_upstream_repo_url": sys.argv[7],
    "tracked_upstream_branch": sys.argv[8],
}
target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

checkout_upstream_release() {
  local checkout_dir="$1"

  if ! command -v git >/dev/null 2>&1; then
    echo "git is required for deploy.sh upgrade." >&2
    return 1
  fi

  rm -rf "$checkout_dir"
  git clone --depth 1 --branch "$ALMANAC_UPSTREAM_BRANCH" --single-branch \
    "$ALMANAC_UPSTREAM_REPO_URL" "$checkout_dir" >/dev/null
}

write_operator_checkout_artifact() {
  local artifact="${ALMANAC_OPERATOR_ARTIFACT_FILE:-$BOOTSTRAP_DIR/.almanac-operator.env}"
  local config_target="${CONFIG_TARGET:-${DISCOVERED_CONFIG:-}}"
  local status=""

  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    return 0
  fi
  if [[ -n "${ALMANAC_CONFIG_FILE:-}" ]]; then
    return 0
  fi
  if [[ ! -d "$BOOTSTRAP_DIR" || ! -w "$BOOTSTRAP_DIR" ]]; then
    return 0
  fi
  status="$(probe_path_status "$config_target")"
  if [[ "$status" != "exists" && "$status" != "exists-unreadable" ]]; then
    return 0
  fi

  mkdir -p "$(dirname "$artifact")"
  {
    printf '# Managed by Almanac deploy helpers. Local maintenance pointer only.\n'
    printf 'ALMANAC_OPERATOR_DEPLOYED_USER=%q\n' "${ALMANAC_USER:-}"
    printf 'ALMANAC_OPERATOR_DEPLOYED_REPO_DIR=%q\n' "${ALMANAC_REPO_DIR:-}"
    printf 'ALMANAC_OPERATOR_DEPLOYED_PRIV_DIR=%q\n' "${ALMANAC_PRIV_DIR:-}"
    printf 'ALMANAC_OPERATOR_DEPLOYED_CONFIG_FILE=%q\n' "$config_target"
  } >"$artifact"
}

run_as_user() {
  local user="$1"
  shift
  su - "$user" -c "$*"
}

run_as_user_systemd() {
  local user="$1"
  local uid="$2"
  shift 2
  su - "$user" -c "env XDG_RUNTIME_DIR='/run/user/$uid' DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/$uid/bus' $*"
}

set_user_systemd_bus_env() {
  local uid="" runtime_dir="" bus_path=""
  uid="$(id -u)"
  runtime_dir="/run/user/$uid"
  bus_path="$runtime_dir/bus"

  if [[ -z "${XDG_RUNTIME_DIR:-}" && -d "$runtime_dir" ]]; then
    export XDG_RUNTIME_DIR="$runtime_dir"
  fi

  if [[ -z "${DBUS_SESSION_BUS_ADDRESS:-}" && -S "$bus_path" ]]; then
    export DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path"
  fi

  [[ -n "${XDG_RUNTIME_DIR:-}" && -n "${DBUS_SESSION_BUS_ADDRESS:-}" ]]
}

curator_bootstrap_env_prefix() {
  printf '%s' "ALMANAC_CONFIG_FILE='$CONFIG_TARGET'"

  local key=""
  for key in \
    ALMANAC_CURATOR_SKIP_HERMES_SETUP \
    ALMANAC_CURATOR_SKIP_GATEWAY_SETUP \
    ALMANAC_CURATOR_FORCE_HERMES_SETUP \
    ALMANAC_CURATOR_FORCE_GATEWAY_SETUP \
    ALMANAC_CURATOR_FORCE_CHANNEL_RECONFIGURE \
    ALMANAC_CURATOR_NOTIFY_PLATFORM \
    ALMANAC_CURATOR_NOTIFY_CHANNEL_ID \
    ALMANAC_CURATOR_GENERAL_PLATFORM \
    ALMANAC_CURATOR_GENERAL_CHANNEL_ID \
    ALMANAC_CURATOR_MODEL_PRESET \
    ALMANAC_CURATOR_CHANNELS
  do
    if [[ -n "${!key:-}" ]]; then
      printf ' %s=%q' "$key" "${!key}"
    fi
  done
}

wait_for_port() {
  local host="$1"
  local port="$2"
  local attempts="${3:-30}"
  local delay="${4:-2}"
  local i=0

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

print_post_install_guide() {
  reload_runtime_config_from_file "$CONFIG_TARGET" || true
  detect_github_repo
  resolve_agent_qmd_endpoint
  resolve_agent_control_plane_endpoint

  echo
  echo "What to do next"
  echo
  echo "Shared vault: source of truth"
  echo "  Host path:"
  echo "    $VAULT_DIR"
  echo "  qmd indexes markdown and direct text files from this exact path."
  echo "  Host watcher:"
  echo "    almanac-vault-watch.service"
  echo "  Direct vault file types:"
  echo "    .md, .markdown, .mdx, .txt, .text"
  if [[ "$PDF_INGEST_ENABLED" == "1" ]]; then
    echo "  PDFs dropped into that tree are converted into generated Markdown and reindexed automatically."
    if [[ -n "${PDF_VISION_ENDPOINT:-}" && -n "${PDF_VISION_MODEL:-}" && -n "${PDF_VISION_API_KEY:-}" ]]; then
      echo "  PDF vision captions:"
      echo "    enabled ($PDF_VISION_MODEL via $(resolve_pdf_vision_endpoint "${PDF_VISION_ENDPOINT:-}") for up to ${PDF_VISION_MAX_PAGES:-6} page(s) per PDF)"
    elif [[ -n "${PDF_VISION_ENDPOINT:-}" || -n "${PDF_VISION_MODEL:-}" || -n "${PDF_VISION_API_KEY:-}" ]]; then
      echo "  PDF vision captions:"
      echo "    partially configured; finish PDF_VISION_ENDPOINT, PDF_VISION_MODEL, and PDF_VISION_API_KEY in $CONFIG_TARGET"
    else
      echo "  PDF vision captions:"
      echo "    disabled"
    fi
    if [[ "${VAULT_WATCH_RUN_EMBED,,}" == "1" ]]; then
      echo "  Watcher embeddings:"
      echo "    enabled"
    elif [[ "${VAULT_WATCH_RUN_EMBED,,}" == "auto" ]]; then
      echo "  Watcher embeddings:"
      echo "    auto (embed only when qmd reports new pending work)"
    else
      echo "  Watcher embeddings:"
      echo "    deferred to scheduled/manual qmd refresh"
    fi
  elif [[ "${VAULT_WATCH_RUN_EMBED,,}" == "1" ]]; then
    echo "  Watcher embeddings:"
    echo "    enabled"
  elif [[ "${VAULT_WATCH_RUN_EMBED,,}" == "auto" ]]; then
    echo "  Watcher embeddings:"
    echo "    auto (embed only when qmd reports new pending work)"
  else
    echo "  Watcher embeddings:"
    echo "    deferred to scheduled/manual qmd refresh"
  fi
  if [[ "$ENABLE_NEXTCLOUD" == "1" ]]; then
    echo "  Nextcloud exposes it at:"
    echo "    $NEXTCLOUD_VAULT_MOUNT_POINT"
  fi
  echo

  echo "Nextcloud: browser access / folder management / uploads"
  if [[ "$ENABLE_NEXTCLOUD" == "1" ]]; then
    echo "  Local URL:"
    echo "    http://127.0.0.1:$NEXTCLOUD_PORT"
    echo "  Trusted hostname:"
    echo "    $NEXTCLOUD_TRUSTED_DOMAIN"
    echo "  Admin user:"
    echo "    $NEXTCLOUD_ADMIN_USER"
    echo "  Admin password stored in:"
    echo "    $CONFIG_TARGET"
    echo "  Shared vault mount in Nextcloud:"
    echo "    $NEXTCLOUD_VAULT_MOUNT_POINT"
    if [[ "$PDF_INGEST_ENABLED" == "1" ]]; then
      echo "  PDF ingestion:"
      echo "    enabled ($PDF_INGEST_EXTRACTOR backend preference)"
      if [[ -n "${PDF_VISION_ENDPOINT:-}" && -n "${PDF_VISION_MODEL:-}" && -n "${PDF_VISION_API_KEY:-}" ]]; then
        echo "  PDF vision captions:"
        echo "    enabled ($PDF_VISION_MODEL)"
      fi
    fi
    if [[ "$ENABLE_TAILSCALE_SERVE" == "1" ]]; then
      echo "  Tailnet HTTPS URL:"
      echo "    https://${TAILSCALE_DNS_NAME:-$NEXTCLOUD_TRUSTED_DOMAIN}"
      echo "  Exposure:"
      echo "    tailnet only"
    else
      echo "  Tailscale HTTPS proxy:"
      echo "    disabled in config"
    fi
  else
    echo "  Disabled in config."
  fi
  echo

  echo "Hermes + qmd: retrieval / search"
  echo "  MCP endpoint:"
  echo "    http://127.0.0.1:$QMD_MCP_PORT/mcp"
  if [[ "$AGENT_QMD_URL_MODE" == "tailnet" ]]; then
    echo "  Tailnet MCP endpoint:"
    echo "    $AGENT_QMD_URL"
    if [[ "$AGENT_QMD_ROUTE_STATUS" != "live" ]]; then
      echo "  Tailnet route note:"
      echo "    hostname detected, but current tailscale serve status does not show ${TAILSCALE_QMD_PATH}"
    fi
  fi
  echo "  Config snippet:"
  echo "    $ALMANAC_REPO_DIR/docs/hermes-qmd-config.yaml"
  if [[ "$PDF_INGEST_ENABLED" == "1" ]]; then
    echo "  PDF-derived qmd collection:"
    echo "    $PDF_INGEST_COLLECTION_NAME"
  fi
  echo "  Quick check:"
  echo "    $ALMANAC_REPO_DIR/deploy.sh health"
  echo

  echo "Almanac control plane"
  echo "  Control-plane MCP:"
  echo "    http://${ALMANAC_MCP_HOST:-127.0.0.1}:${ALMANAC_MCP_PORT:-8282}/mcp"
  if [[ "$AGENT_ALMANAC_MCP_URL_MODE" == "tailnet" ]]; then
    echo "  Tailnet bootstrap MCP:"
    echo "    $AGENT_ALMANAC_MCP_URL"
    if [[ "$AGENT_ALMANAC_MCP_ROUTE_STATUS" != "live" ]]; then
      echo "  Tailnet route note:"
      echo "    hostname detected, but current tailscale serve status does not show ${TAILSCALE_ALMANAC_MCP_PATH}"
    fi
  fi
  echo "  Notion webhook:"
  echo "    http://${ALMANAC_NOTION_WEBHOOK_HOST:-127.0.0.1}:${ALMANAC_NOTION_WEBHOOK_PORT:-8283}/notion/webhook"
  echo "  Curator Hermes home:"
  echo "    ${ALMANAC_CURATOR_HERMES_HOME:-$STATE_DIR/curator/hermes-home}"
  echo "  Operator notification channel:"
  echo "    ${OPERATOR_NOTIFY_CHANNEL_PLATFORM:-tui-only} ${OPERATOR_NOTIFY_CHANNEL_ID:-"(tui-only)"}"
  echo "  Recovery CLI:"
  echo "    $ALMANAC_REPO_DIR/bin/almanac-ctl"
  echo "  Enrollment maintenance:"
  echo "    $ALMANAC_REPO_DIR/deploy.sh enrollment-status"
  echo "    $ALMANAC_REPO_DIR/deploy.sh enrollment-align"
  echo "    $ALMANAC_REPO_DIR/deploy.sh enrollment-reset"
  echo

  echo "Almanac software updates"
  echo "  Tracked upstream:"
  echo "    ${ALMANAC_UPSTREAM_REPO_URL:-https://github.com/sirouk/almanac.git}#${ALMANAC_UPSTREAM_BRANCH:-main}"
  echo "  Release state:"
  echo "    ${ALMANAC_RELEASE_STATE_FILE:-$STATE_DIR/almanac-release.json}"
  echo "  Upgrade command:"
  echo "    $ALMANAC_REPO_DIR/deploy.sh upgrade"
  echo "  Manual upstream check:"
  echo "    $ALMANAC_REPO_DIR/bin/almanac-ctl upgrade check"
  echo "  Curator routine:"
  echo "    hourly via almanac-curator-refresh.timer using skill almanac-upgrade-orchestrator"
  echo

  print_agent_install_payload
  echo

  echo "GitHub: backup / history"
  echo "  Private repo:"
  echo "    $ALMANAC_PRIV_DIR"
  if [[ -n "$BACKUP_GIT_REMOTE" ]]; then
    echo "  Backup remote:"
    echo "    $BACKUP_GIT_REMOTE"
  else
    echo "  Set BACKUP_GIT_REMOTE in:"
    echo "    $CONFIG_TARGET"
    echo "  Then run:"
    echo "    $ALMANAC_REPO_DIR/bin/backup-to-github.sh"
  fi
  echo

  echo "Quarto: optional human-facing published site"
  if [[ "$ENABLE_QUARTO" == "1" ]]; then
    echo "  Project:"
    echo "    $QUARTO_PROJECT_DIR"
    echo "  Output:"
    echo "    $QUARTO_OUTPUT_DIR"
    echo "  Manual render:"
    echo "    $ALMANAC_REPO_DIR/bin/render-quarto.sh"
  else
    echo "  Disabled in config. Enable it later in:"
    echo "    $CONFIG_TARGET"
  fi
}

agent_install_payload_path() {
  local state_dir="${STATE_DIR:-${ALMANAC_PRIV_DIR:-$BOOTSTRAP_DIR/almanac-priv}/state}"
  printf '%s/agent-install-payload.txt\n' "$state_dir"
}

render_agent_install_payload_body() {
  detect_github_repo
  resolve_agent_qmd_endpoint
  resolve_agent_control_plane_endpoint
  echo "almanac_task_v1:"
  echo "  goal: enroll one shared-host user agent with explicit hermes setup, default Almanac skills, almanac-mcp + qmd + chutes MCP registration, first-contact vault defaults, and exactly one 4h refresh timer"
  echo "  qmd_url: \"$AGENT_QMD_URL\""
  echo "  almanac_mcp_url: \"http://${ALMANAC_MCP_HOST:-127.0.0.1}:${ALMANAC_MCP_PORT:-8282}/mcp\""
  echo "  almanac_bootstrap_url: \"$AGENT_ALMANAC_MCP_URL\""
  echo "  qmd_collections:"
  echo "    - \"$QMD_COLLECTION_NAME\""
  if [[ "$PDF_INGEST_ENABLED" == "1" ]]; then
    echo "    - \"$PDF_INGEST_COLLECTION_NAME\""
  fi
  if [[ -n "$GITHUB_REPO_URL" ]]; then
    echo "  repo: \"$GITHUB_REPO_URL\""
  fi
  if [[ -n "$GITHUB_SKILL_RAW_URL" || -n "$GITHUB_RECONCILER_SKILL_RAW_URL" ]]; then
    echo "  skill_docs:"
    if [[ -n "$GITHUB_SKILL_RAW_URL" ]]; then
      echo "    - \"$GITHUB_SKILL_RAW_URL\""
    fi
    if [[ -n "$GITHUB_RECONCILER_SKILL_RAW_URL" ]]; then
      echo "    - \"$GITHUB_RECONCILER_SKILL_RAW_URL\""
    fi
  fi
  if [[ -n "$GITHUB_SKILL_IDENTIFIER" || -n "$GITHUB_RECONCILER_SKILL_IDENTIFIER" ]]; then
    echo "  skill_sources_github:"
    if [[ -n "$GITHUB_SKILL_IDENTIFIER" ]]; then
      echo "    - \"$GITHUB_SKILL_IDENTIFIER\""
    fi
    if [[ -n "$GITHUB_RECONCILER_SKILL_IDENTIFIER" ]]; then
      echo "    - \"$GITHUB_RECONCILER_SKILL_IDENTIFIER\""
    fi
  fi
  echo "  skill_sources_local:"
  echo "    - \"$ALMANAC_REPO_DIR/skills/almanac-qmd-mcp\""
  echo "    - \"$ALMANAC_REPO_DIR/skills/almanac-vault-reconciler\""
  echo "    - \"$ALMANAC_REPO_DIR/skills/almanac-first-contact\""
  echo "    - \"$ALMANAC_REPO_DIR/skills/almanac-vaults\""
  echo "    - \"$ALMANAC_REPO_DIR/skills/almanac-ssot\""
  echo "  model_presets:"
  echo "    codex: \"$ALMANAC_MODEL_PRESET_CODEX\""
  echo "    opus: \"$ALMANAC_MODEL_PRESET_OPUS\""
  echo "    chutes: \"$ALMANAC_MODEL_PRESET_CHUTES\""
  echo "  actions:"
  echo "    - run hermes setup explicitly for model preset selection and optional Discord or Telegram gateway setup; keep local TUI available under the user's Unix account"
  echo "    - install default Almanac skills: qmd MCP, vault reconciler, first-contact, vaults, and ssot"
  echo "    - \"hermes mcp add almanac-mcp --url http://${ALMANAC_MCP_HOST:-127.0.0.1}:${ALMANAC_MCP_PORT:-8282}/mcp\""
  echo "    - \"hermes mcp add almanac-qmd --url $AGENT_QMD_URL\""
  if [[ -n "${CHUTES_MCP_URL:-}" ]]; then
    echo "    - \"hermes mcp add chutes-kb --url ${CHUTES_MCP_URL}\""
  else
    echo "    - register chutes-kb during first contact when CHUTES_MCP_URL is provided"
  fi
  echo "    - run almanac-first-contact immediately after MCP registration"
  echo "    - first contact must resolve YAML .vault defaults, auto-subscribe every default_subscribed vault, fetch agents.managed-memory, and materialize the initial managed-memory stubs"
  echo "    - use almanac-vaults via scripts/curate-vaults.sh for catalog, subscription, and stub curation work"
  echo "    - install exactly one 4h refresh timer/service for the user agent, and rely on Curator fanout -> activation trigger -> user-agent-refresh for immediate stub sync after vault/catalog changes"
  echo "  memory_contract:"
  echo "    - maintain only [managed:almanac-skill-ref], [managed:vault-ref], [managed:qmd-ref], [managed:vault-topology]"
  echo "    - write or refresh those stubs now; MEMORY.md is a frozen snapshot at session start"
  echo "    - make [managed:almanac-skill-ref] explicit: Almanac skills are active defaults, not passive extras"
  echo "    - make [managed:qmd-ref] explicit: qmd first for private/shared-vault questions or follow-ups from the current discussion; use mixed lex+vec retrieval"
  if [[ "$PDF_INGEST_ENABLED" == "1" ]]; then
    echo "    - include \"$PDF_INGEST_COLLECTION_NAME\" when present, especially for newly uploaded PDFs"
  fi
  echo "    - do not store note bodies, PDF bodies, or large dumps in built-in memory"
  echo "    - do not rely on background memory review or session-end flush"
  echo "    - if cron lacks the native memory tool, patch only those four entries in \$HERMES_HOME/memories/MEMORY.md and preserve unrelated entries plus Hermes § delimiters"
  echo "  report_contract:"
  echo "    - recurring success output: exactly 1 short line"
  echo "    - recurring warn/fail output: at most 2 short lines"
  echo "    - recurring output should say only Almanac sync, qmd indexing, memory status, and drift/blocked state"
  echo "    - preferred success form: 'Almanac health ok: sync current, qmd indexed, managed memory refreshed, drift=none.'"
  echo "  rails:"
  echo "    - prefer qmd/MCP over filesystem access; direct local qmd service or CLI is fallback only when MCP is unavailable"
  echo "    - prefer the deployed almanac-owned qmd/vault over repo-scaffold guesses"
  if [[ "$AGENT_QMD_URL_MODE" == "tailnet" && "$AGENT_QMD_ROUTE_STATUS" != "live" ]]; then
    echo "    - tailnet hostname is known but ${TAILSCALE_QMD_PATH} is not visibly published; republish Tailscale Serve if MCP test fails"
  fi
  if [[ "$AGENT_ALMANAC_MCP_URL_MODE" == "tailnet" && "$AGENT_ALMANAC_MCP_ROUTE_STATUS" != "live" ]]; then
    echo "    - tailnet hostname is known but ${TAILSCALE_ALMANAC_MCP_PATH} is not visibly published; republish Tailscale Serve if remote bootstrap test fails"
  fi
  echo "    - GET /mcp returning 404 is not an MCP failure; use hermes mcp test"
  echo "    - done means: first reconciliation ran and the single 4h cron exists"
  echo "  report:"
  echo "    - active vault path"
  echo "    - almanac-mcp endpoint"
  echo "    - qmd collection(s) and endpoint"
  echo "    - chosen model preset and enabled channels"
  echo "    - whether the first reconciliation ran"
  echo "    - refresh timer name and schedule"
  echo "    - drift or blocked memory writes"
}

write_agent_install_payload_file() {
  local target=""

  target="${1:-$(agent_install_payload_path)}"
  mkdir -p "$(dirname "$target")"
  render_agent_install_payload_body >"$target"
  printf '%s\n' "$target"
}

print_agent_install_payload() {
  local payload_path=""

  payload_path="$(agent_install_payload_path)"

  echo "Agent install payload"
  echo "  This is the canonical prompt to hand to Hermes or another agent."
  echo "  Raw prompt file:"
  echo "    $payload_path"
  echo
  echo '```yaml'
  render_agent_install_payload_body
  echo '```'
}

load_answers() {
  if [[ -z "$ANSWERS_FILE" || ! -f "$ANSWERS_FILE" ]]; then
    echo "Missing answers file for privileged step." >&2
    exit 1
  fi

  # shellcheck disable=SC1090
  source "$ANSWERS_FILE"
  CONFIG_TARGET="${ALMANAC_PRIV_CONFIG_DIR}/almanac.env"
}

init_public_repo_if_needed() {
  if [[ "${ALMANAC_INSTALL_PUBLIC_GIT:-0}" != "1" ]]; then
    return 0
  fi

  if [[ -d "$ALMANAC_REPO_DIR/.git" ]]; then
    return 0
  fi

  run_as_user "$ALMANAC_USER" "git -C '$ALMANAC_REPO_DIR' init -b main"
}

path_is_within() {
  local path="$1"
  local base="$2"

  case "$path" in
    "$base"|"${base}/"*) return 0 ;;
    *) return 1 ;;
  esac
}

safe_remove_path() {
  local path="$1"

  if [[ -z "$path" ]]; then
    return 0
  fi

  case "$path" in
    /|/home|/root|/usr|/etc|/var)
      echo "Refusing to remove unsafe path: $path" >&2
      return 1
      ;;
  esac

  rm -rf -- "$path"
}

nextcloud_state_has_existing_data() {
  if [[ ! -d "$NEXTCLOUD_STATE_DIR" ]]; then
    return 1
  fi

  find "$NEXTCLOUD_STATE_DIR" -mindepth 1 -print -quit 2>/dev/null | grep -q .
}

wipe_nextcloud_state_if_requested() {
  local uid=""

  if [[ "${WIPE_NEXTCLOUD_STATE:-0}" != "1" || "$ENABLE_NEXTCLOUD" != "1" ]]; then
    return 0
  fi

  echo "Wiping existing Nextcloud state under $NEXTCLOUD_STATE_DIR ..."

  if id -u "$ALMANAC_USER" >/dev/null 2>&1; then
    uid="$(id -u "$ALMANAC_USER")"
    systemctl start "user@$uid.service" >/dev/null 2>&1 || true

    if [[ -x "$ALMANAC_REPO_DIR/bin/nextcloud-down.sh" ]]; then
      run_as_user "$ALMANAC_USER" "env ALMANAC_CONFIG_FILE='$CONFIG_TARGET' '$ALMANAC_REPO_DIR/bin/nextcloud-down.sh'" >/dev/null 2>&1 || true
    fi

    if [[ -S "/run/user/$uid/bus" ]]; then
      run_as_user_systemd "$ALMANAC_USER" "$uid" "ALMANAC_CONFIG_FILE='$CONFIG_TARGET' systemctl --user stop almanac-nextcloud.service >/dev/null 2>&1 || true" || true
    fi
  fi

  safe_remove_path "$NEXTCLOUD_STATE_DIR"
  install -d -m 0750 -o "$ALMANAC_USER" -g "$ALMANAC_USER" "$NEXTCLOUD_STATE_DIR"
}

collect_install_answers() {
  local -a artifact_hints=()
  local default_user="" default_home="" default_domain="" default_repo="" default_priv=""
  local default_nextcloud_port="" default_git_name="" default_git_email=""
  local default_enable_nextcloud="" default_enable_quarto="" default_enable_private_git=""
  local default_seed_vault="" default_install_public_git=""
  local detected_user="" detected_home="" detected_repo="" detected_priv=""
  local detected_git_name="" detected_git_email=""
  local artifact_user="" artifact_repo="" artifact_priv="" artifact_home=""
  local default_nextcloud_admin_user="" nextcloud_admin_password_input=""
  local default_enable_tailscale_serve=""
  local default_tailscale_operator_user=""
  local default_pdf_vision_endpoint=""
  local default_pdf_vision_model=""
  local default_pdf_vision_api_key=""
  local default_telegram_bot_token=""

  load_detected_config || true

  echo "Almanac deploy: install / repair from current checkout"
  echo

  detected_user="${ALMANAC_USER:-}"
  detected_home="${ALMANAC_HOME:-}"
  detected_repo="${ALMANAC_REPO_DIR:-}"
  detected_priv="${ALMANAC_PRIV_DIR:-}"
  detected_git_name="${BACKUP_GIT_AUTHOR_NAME:-}"
  detected_git_email="${BACKUP_GIT_AUTHOR_EMAIL:-}"
  mapfile -t artifact_hints < <(read_operator_artifact_hints || true)
  artifact_user="${artifact_hints[0]:-}"
  artifact_repo="${artifact_hints[1]:-}"
  artifact_priv="${artifact_hints[2]:-}"
  artifact_home="$(resolve_user_home "$artifact_user" || true)"

  if [[ -z "$detected_user" && -n "$artifact_user" ]]; then
    detected_user="$artifact_user"
  fi
  if [[ -z "$detected_home" && -n "$artifact_home" ]]; then
    detected_home="$artifact_home"
  fi
  if [[ -z "$detected_home" && -n "$artifact_repo" ]]; then
    detected_home="$(dirname "$artifact_repo")"
  fi
  if [[ -z "$detected_repo" && -n "$artifact_repo" ]]; then
    detected_repo="$artifact_repo"
  fi
  if [[ -z "$detected_priv" && -n "$artifact_priv" ]]; then
    detected_priv="$artifact_priv"
  fi

  if [[ -n "$detected_user" && "$detected_user" != "almanac" ]]; then
    echo "Detected existing configured user: $detected_user"
  fi

  while true; do
    default_user="${detected_user:-almanac}"
    ALMANAC_USER="$(ask "Service user" "$default_user")"
    if [[ -n "$ALMANAC_USER" ]]; then
      break
    fi
    echo "Service user cannot be blank."
  done

  if [[ -n "$detected_home" && ( -z "$detected_user" || "$detected_user" == "$ALMANAC_USER" ) ]]; then
    default_home="$detected_home"
  else
    default_home="/home/$ALMANAC_USER"
  fi

  if [[ -n "$detected_repo" && ( -z "$detected_user" || "$detected_user" == "$ALMANAC_USER" ) ]]; then
    default_repo="$detected_repo"
  else
    default_repo="$default_home/almanac"
  fi

  if [[ -n "$detected_priv" && ( -z "$detected_user" || "$detected_user" == "$ALMANAC_USER" ) ]]; then
    default_priv="$detected_priv"
  else
    default_priv="$default_repo/almanac-priv"
  fi

  default_nextcloud_port="${NEXTCLOUD_PORT:-18080}"
  default_git_name="${detected_git_name:-Almanac Backup}"
  if [[ -n "$detected_git_email" && ( -z "$detected_user" || "$detected_user" == "$ALMANAC_USER" ) ]]; then
    default_git_email="$detected_git_email"
  else
    default_git_email="$ALMANAC_USER@localhost"
  fi
  default_enable_nextcloud="${ENABLE_NEXTCLOUD:-1}"
  default_enable_tailscale_serve="${ENABLE_TAILSCALE_SERVE:-0}"
  default_tailscale_operator_user="${TAILSCALE_OPERATOR_USER:-${SUDO_USER:-}}"
  if [[ -z "$default_tailscale_operator_user" || "$default_tailscale_operator_user" == "root" ]]; then
    default_tailscale_operator_user="$(id -un)"
  fi
  if [[ "$default_tailscale_operator_user" == "root" ]]; then
    default_tailscale_operator_user="$ALMANAC_USER"
  fi
  default_enable_private_git="${ENABLE_PRIVATE_GIT:-1}"
  default_enable_quarto="${ENABLE_QUARTO:-1}"
  default_seed_vault="${SEED_SAMPLE_VAULT:-1}"
  default_install_public_git="${ALMANAC_INSTALL_PUBLIC_GIT:-1}"
  default_nextcloud_admin_user="${NEXTCLOUD_ADMIN_USER:-$(id -un)}"
  default_pdf_vision_endpoint="${PDF_VISION_ENDPOINT:-}"
  default_pdf_vision_model="${PDF_VISION_MODEL:-}"
  default_pdf_vision_api_key="${PDF_VISION_API_KEY:-}"
  default_telegram_bot_token="${TELEGRAM_BOT_TOKEN:-}"

  ALMANAC_NAME="almanac"
  ALMANAC_HOME="$(ask "Service home" "$default_home")"
  ALMANAC_REPO_DIR="$(ask "Public repo path" "$default_repo")"
  ALMANAC_PRIV_DIR="$(ask "Private repo path" "$default_priv")"
  ALMANAC_PRIV_CONFIG_DIR="$ALMANAC_PRIV_DIR/config"
  VAULT_DIR="$ALMANAC_PRIV_DIR/vault"
  STATE_DIR="$ALMANAC_PRIV_DIR/state"
  NEXTCLOUD_STATE_DIR="$STATE_DIR/nextcloud"
  RUNTIME_DIR="$STATE_DIR/runtime"
  PUBLISHED_DIR="$ALMANAC_PRIV_DIR/published"
  ALMANAC_RELEASE_STATE_FILE="${ALMANAC_RELEASE_STATE_FILE:-$STATE_DIR/almanac-release.json}"
  QMD_INDEX_NAME="almanac"
  QMD_COLLECTION_NAME="vault"
  QMD_RUN_EMBED="1"
  QMD_MCP_PORT="${QMD_MCP_PORT:-8181}"
  BACKUP_GIT_BRANCH="${BACKUP_GIT_BRANCH:-main}"
  ALMANAC_UPSTREAM_REPO_URL="${ALMANAC_UPSTREAM_REPO_URL:-https://github.com/sirouk/almanac.git}"
  ALMANAC_UPSTREAM_BRANCH="${ALMANAC_UPSTREAM_BRANCH:-main}"
  ALMANAC_INSTALL_PUBLIC_GIT="$(ask_yes_no "Initialize the public repo as git if needed" "$default_install_public_git")"
  BACKUP_GIT_REMOTE="$(ask "Private GitHub remote for almanac-priv (blank to skip)" "${BACKUP_GIT_REMOTE:-}")"
  BACKUP_GIT_AUTHOR_NAME="$(ask "Git author name" "$default_git_name")"
  BACKUP_GIT_AUTHOR_EMAIL="$(ask "Git author email" "$default_git_email")"
  NEXTCLOUD_PORT="$(ask "Nextcloud local port" "$default_nextcloud_port")"

  detect_tailscale
  default_domain="${NEXTCLOUD_TRUSTED_DOMAIN:-almanac.your-tailnet.ts.net}"
  if [[ -n "$TAILSCALE_DNS_NAME" ]]; then
    default_domain="$TAILSCALE_DNS_NAME"
    default_enable_tailscale_serve="1"
    echo "Detected Tailscale DNS name: $TAILSCALE_DNS_NAME"
    if [[ -n "$TAILSCALE_IPV4" ]]; then
      echo "Detected Tailscale IPv4:    $TAILSCALE_IPV4"
    fi
    echo
  elif [[ -n "$TAILSCALE_TAILNET" ]]; then
    default_domain="$TAILSCALE_TAILNET"
    default_enable_tailscale_serve="1"
    echo "Detected Tailscale tailnet:  $TAILSCALE_TAILNET"
    echo
  fi

  NEXTCLOUD_TRUSTED_DOMAIN="$(ask "Nextcloud trusted domain / Tailscale hostname" "$default_domain")"
  POSTGRES_DB="${POSTGRES_DB:-${MARIADB_DATABASE:-nextcloud}}"
  POSTGRES_USER="${POSTGRES_USER:-${MARIADB_USER:-nextcloud}}"
  POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-${MARIADB_PASSWORD:-$(random_secret)}}"
  NEXTCLOUD_ADMIN_USER="$(ask "Nextcloud admin user" "$default_nextcloud_admin_user")"
  if [[ -n "${NEXTCLOUD_ADMIN_PASSWORD:-}" ]]; then
    nextcloud_admin_password_input="$(ask_secret_keep_default "Nextcloud admin password (ENTER keeps current)" "$NEXTCLOUD_ADMIN_PASSWORD")"
    NEXTCLOUD_ADMIN_PASSWORD="${nextcloud_admin_password_input:-$NEXTCLOUD_ADMIN_PASSWORD}"
  else
    nextcloud_admin_password_input="$(ask_secret "Nextcloud admin password (leave blank to auto-generate)")"
    NEXTCLOUD_ADMIN_PASSWORD="${nextcloud_admin_password_input:-$(random_secret)}"
  fi
  NEXTCLOUD_VAULT_MOUNT_POINT="${NEXTCLOUD_VAULT_MOUNT_POINT:-/Vault}"
  ENABLE_NEXTCLOUD="$(ask_yes_no "Enable Nextcloud" "$default_enable_nextcloud")"
  if [[ "$ENABLE_NEXTCLOUD" == "1" ]]; then
    ENABLE_TAILSCALE_SERVE="$(ask_yes_no "Enable Tailscale HTTPS proxy for Nextcloud (tailnet only)" "$default_enable_tailscale_serve")"
    if [[ "$ENABLE_TAILSCALE_SERVE" == "1" ]]; then
      TAILSCALE_OPERATOR_USER="$(ask "Tailscale operator user for serve management" "$default_tailscale_operator_user")"
    else
      TAILSCALE_OPERATOR_USER=""
    fi
  else
    ENABLE_TAILSCALE_SERVE="0"
    TAILSCALE_OPERATOR_USER=""
  fi
  WIPE_NEXTCLOUD_STATE="0"
  if [[ "$MODE" != "write-config" && "$ENABLE_NEXTCLOUD" == "1" && nextcloud_state_has_existing_data ]]; then
    echo "Detected existing Nextcloud state under:"
    echo "  $NEXTCLOUD_STATE_DIR"
    echo "This wipes Nextcloud app/db/data state only; the vault stays untouched."
    WIPE_NEXTCLOUD_STATE="$(ask_yes_no "Wipe existing Nextcloud state for a clean install" "0")"
  fi
  ENABLE_PRIVATE_GIT="$(ask_yes_no "Initialize almanac-priv as a git repo" "$default_enable_private_git")"
  ENABLE_QUARTO="$(ask_yes_no "Enable Quarto timer/hooks" "$default_enable_quarto")"
  SEED_SAMPLE_VAULT="$(ask_yes_no "Seed a starter vault structure" "$default_seed_vault")"
  PDF_VISION_ENDPOINT="$(normalize_optional_answer "$(ask "OpenAI-compatible vision endpoint for PDF page captions (base /v1 or full /v1/chat/completions; type none to disable)" "$default_pdf_vision_endpoint")")"
  PDF_VISION_MODEL="$(normalize_optional_answer "$(ask "Vision model name for PDF page captions (type none to disable)" "$default_pdf_vision_model")")"
  PDF_VISION_API_KEY="$(ask_secret_with_default "Vision API key for PDF page captions (ENTER keeps current, type none to clear)" "$default_pdf_vision_api_key")"
  TELEGRAM_BOT_TOKEN="$(ask_secret_with_default "Telegram bot token for operator notifications and delivery (optional; ENTER keeps current, type none to clear)" "$default_telegram_bot_token")"
  PDF_VISION_MAX_PAGES="${PDF_VISION_MAX_PAGES:-6}"

  if [[ -z "$PDF_VISION_ENDPOINT" && -z "$PDF_VISION_MODEL" && -z "$PDF_VISION_API_KEY" ]]; then
    PDF_VISION_ENDPOINT=""
    PDF_VISION_MODEL=""
    PDF_VISION_API_KEY=""
  fi
  QUARTO_PROJECT_DIR="$ALMANAC_PRIV_DIR/quarto"
  QUARTO_OUTPUT_DIR="$ALMANAC_PRIV_DIR/published"
  CONFIG_TARGET="$ALMANAC_PRIV_CONFIG_DIR/almanac.env"
}

collect_remove_answers() {
  local default_user="" default_home="" default_repo="" default_priv=""
  local default_remove_user="" default_remove_tooling=""
  local confirm_text=""
  local use_detected_config="0"

  if load_detected_config; then
    use_detected_config="$(ask_yes_no "Use detected config from $DISCOVERED_CONFIG for teardown" "1")"
  fi

  echo "Almanac deploy: remove / teardown"
  echo

  default_user="${ALMANAC_USER:-almanac}"
  default_home="${ALMANAC_HOME:-/home/$default_user}"
  default_repo="${ALMANAC_REPO_DIR:-$default_home/almanac}"
  default_priv="${ALMANAC_PRIV_DIR:-$default_repo/almanac-priv}"
  default_remove_user="0"
  if [[ "$default_user" == "almanac" && "$default_home" == "/home/almanac" ]]; then
    default_remove_user="1"
  fi
  default_remove_tooling="$default_remove_user"

  ALMANAC_NAME="${ALMANAC_NAME:-almanac}"

  if [[ "$use_detected_config" == "1" ]]; then
    ALMANAC_USER="${ALMANAC_USER:-$default_user}"
    ALMANAC_HOME="${ALMANAC_HOME:-$default_home}"
    ALMANAC_REPO_DIR="${ALMANAC_REPO_DIR:-$default_repo}"
    ALMANAC_PRIV_DIR="${ALMANAC_PRIV_DIR:-$default_priv}"

    echo "Using config:   $DISCOVERED_CONFIG"
    echo "Service user:   $ALMANAC_USER"
    echo "Service home:   $ALMANAC_HOME"
    echo "Public repo:    $ALMANAC_REPO_DIR"
    echo "Private repo:   $ALMANAC_PRIV_DIR"
    echo
  else
    ALMANAC_USER="$(ask "Service user to remove" "$default_user")"
    ALMANAC_HOME="$(ask "Service home" "$default_home")"
    ALMANAC_REPO_DIR="$(ask "Deployed public repo path" "$default_repo")"
    ALMANAC_PRIV_DIR="$(ask "Deployed private repo path" "$default_priv")"
  fi

  ALMANAC_PRIV_CONFIG_DIR="$ALMANAC_PRIV_DIR/config"
  VAULT_DIR="$ALMANAC_PRIV_DIR/vault"
  STATE_DIR="$ALMANAC_PRIV_DIR/state"
  NEXTCLOUD_STATE_DIR="$STATE_DIR/nextcloud"
  RUNTIME_DIR="$STATE_DIR/runtime"
  PUBLISHED_DIR="$ALMANAC_PRIV_DIR/published"
  ALMANAC_RELEASE_STATE_FILE="${ALMANAC_RELEASE_STATE_FILE:-$STATE_DIR/almanac-release.json}"
  QMD_INDEX_NAME="${QMD_INDEX_NAME:-almanac}"
  QMD_COLLECTION_NAME="${QMD_COLLECTION_NAME:-vault}"
  QMD_RUN_EMBED="${QMD_RUN_EMBED:-1}"
  QMD_MCP_PORT="${QMD_MCP_PORT:-8181}"
  BACKUP_GIT_BRANCH="${BACKUP_GIT_BRANCH:-main}"
  ALMANAC_UPSTREAM_REPO_URL="${ALMANAC_UPSTREAM_REPO_URL:-https://github.com/sirouk/almanac.git}"
  ALMANAC_UPSTREAM_BRANCH="${ALMANAC_UPSTREAM_BRANCH:-main}"
  BACKUP_GIT_REMOTE="${BACKUP_GIT_REMOTE:-}"
  BACKUP_GIT_AUTHOR_NAME="${BACKUP_GIT_AUTHOR_NAME:-Almanac Backup}"
  BACKUP_GIT_AUTHOR_EMAIL="${BACKUP_GIT_AUTHOR_EMAIL:-$ALMANAC_USER@localhost}"
  NEXTCLOUD_PORT="${NEXTCLOUD_PORT:-18080}"
  NEXTCLOUD_TRUSTED_DOMAIN="${NEXTCLOUD_TRUSTED_DOMAIN:-almanac.your-tailnet.ts.net}"
  POSTGRES_DB="${POSTGRES_DB:-${MARIADB_DATABASE:-nextcloud}}"
  POSTGRES_USER="${POSTGRES_USER:-${MARIADB_USER:-nextcloud}}"
  POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-${MARIADB_PASSWORD:-}}"
  NEXTCLOUD_ADMIN_USER="${NEXTCLOUD_ADMIN_USER:-}"
  NEXTCLOUD_ADMIN_PASSWORD="${NEXTCLOUD_ADMIN_PASSWORD:-}"
  NEXTCLOUD_VAULT_MOUNT_POINT="${NEXTCLOUD_VAULT_MOUNT_POINT:-/Vault}"
  ENABLE_NEXTCLOUD="${ENABLE_NEXTCLOUD:-1}"
  ENABLE_TAILSCALE_SERVE="${ENABLE_TAILSCALE_SERVE:-0}"
  TAILSCALE_OPERATOR_USER="${TAILSCALE_OPERATOR_USER:-}"
  TAILSCALE_QMD_PATH="${TAILSCALE_QMD_PATH:-/mcp}"
  TAILSCALE_ALMANAC_MCP_PATH="${TAILSCALE_ALMANAC_MCP_PATH:-/almanac-mcp}"
  ENABLE_PRIVATE_GIT="${ENABLE_PRIVATE_GIT:-1}"
  ENABLE_QUARTO="${ENABLE_QUARTO:-1}"
  SEED_SAMPLE_VAULT="${SEED_SAMPLE_VAULT:-1}"
  QUARTO_PROJECT_DIR="${QUARTO_PROJECT_DIR:-$ALMANAC_PRIV_DIR/quarto}"
  QUARTO_OUTPUT_DIR="${QUARTO_OUTPUT_DIR:-$ALMANAC_PRIV_DIR/published}"
  CONFIG_TARGET="${DISCOVERED_CONFIG:-$ALMANAC_PRIV_CONFIG_DIR/almanac.env}"
  REMOVE_PUBLIC_REPO="$(ask_yes_no "Remove the deployed repo directory and private state" "1")"
  REMOVE_USER_TOOLING="$(ask_yes_no "Remove user-scoped tooling and caches" "$default_remove_tooling")"
  REMOVE_SERVICE_USER="$(ask_yes_no "Remove the service user and its home" "$default_remove_user")"
  confirm_text="$(ask "Type REMOVE to confirm teardown" "")"

  if [[ "$confirm_text" != "REMOVE" ]]; then
    echo "Teardown cancelled."
    exit 1
  fi
}

prepare_deployed_context() {
  load_detected_config || true

  ALMANAC_USER="${ALMANAC_USER:-almanac}"
  ALMANAC_HOME="${ALMANAC_HOME:-/home/$ALMANAC_USER}"
  ALMANAC_REPO_DIR="${ALMANAC_REPO_DIR:-$ALMANAC_HOME/almanac}"
  ALMANAC_PRIV_DIR="${ALMANAC_PRIV_DIR:-$ALMANAC_REPO_DIR/almanac-priv}"
  ALMANAC_PRIV_CONFIG_DIR="${ALMANAC_PRIV_CONFIG_DIR:-$ALMANAC_PRIV_DIR/config}"
  VAULT_DIR="${VAULT_DIR:-$ALMANAC_PRIV_DIR/vault}"
  STATE_DIR="${STATE_DIR:-$ALMANAC_PRIV_DIR/state}"
  NEXTCLOUD_STATE_DIR="${NEXTCLOUD_STATE_DIR:-$STATE_DIR/nextcloud}"
  RUNTIME_DIR="${RUNTIME_DIR:-$STATE_DIR/runtime}"
  PUBLISHED_DIR="${PUBLISHED_DIR:-$ALMANAC_PRIV_DIR/published}"
  ALMANAC_DB_PATH="${ALMANAC_DB_PATH:-$STATE_DIR/almanac-control.sqlite3}"
  ALMANAC_AGENTS_STATE_DIR="${ALMANAC_AGENTS_STATE_DIR:-$STATE_DIR/agents}"
  ALMANAC_ARCHIVED_AGENTS_DIR="${ALMANAC_ARCHIVED_AGENTS_DIR:-$STATE_DIR/archived-agents}"
  CONFIG_TARGET="${DISCOVERED_CONFIG:-${ALMANAC_CONFIG_FILE:-$ALMANAC_PRIV_CONFIG_DIR/almanac.env}}"
  ALMANAC_RELEASE_STATE_FILE="${ALMANAC_RELEASE_STATE_FILE:-$STATE_DIR/almanac-release.json}"
  ALMANAC_UPSTREAM_REPO_URL="${ALMANAC_UPSTREAM_REPO_URL:-https://github.com/sirouk/almanac.git}"
  ALMANAC_UPSTREAM_BRANCH="${ALMANAC_UPSTREAM_BRANCH:-main}"
}

ensure_deployed_config_exists() {
  local status=""
  status="$(probe_path_status "$CONFIG_TARGET")"
  if [[ "$status" == "exists" || "$status" == "exists-unreadable" ]]; then
    return 0
  fi
  if [[ ! -f "$CONFIG_TARGET" ]]; then
    echo "Deployed config not found at $CONFIG_TARGET" >&2
    echo "Run ./deploy.sh install first, or point ALMANAC_CONFIG_FILE at the deployed almanac.env." >&2
    exit 1
  fi
}

maybe_reexec_with_sudo_for_config() {
  local mode="$1"
  local status=""
  local -a cmd=()

  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    return 1
  fi
  if [[ -z "${CONFIG_TARGET:-}" ]]; then
    return 1
  fi
  if [[ -r "$CONFIG_TARGET" ]]; then
    return 1
  fi

  status="$(probe_path_status "$CONFIG_TARGET")"
  if [[ "$status" != "exists-unreadable" ]]; then
    return 1
  fi

  echo "Switching to sudo to inspect the deployed config..."
  cmd=(sudo env ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$SELF_PATH" "$mode")
  if [[ "$mode" == "enrollment-trace" ]]; then
    if [[ -n "${TRACE_UNIX_USER:-}" ]]; then
      cmd+=(--unix-user "$TRACE_UNIX_USER")
    fi
    if [[ -n "${TRACE_SESSION_ID:-}" ]]; then
      cmd+=(--session-id "$TRACE_SESSION_ID")
    fi
    if [[ -n "${TRACE_REQUEST_ID:-}" ]]; then
      cmd+=(--request-id "$TRACE_REQUEST_ID")
    fi
    if [[ -n "${TRACE_LOG_LINES:-}" ]]; then
      cmd+=(--log-lines "$TRACE_LOG_LINES")
    fi
  fi
  "${cmd[@]}"
  write_operator_checkout_artifact
  return 0
}

maybe_reexec_install_for_config_defaults() {
  local requested_mode="${1:-$MODE}"
  local status=""

  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    return 1
  fi
  if ! discover_existing_config; then
    return 1
  fi

  status="$(probe_path_status "$DISCOVERED_CONFIG")"
  if [[ "$status" != "exists-unreadable" ]]; then
    return 1
  fi

  CONFIG_TARGET="$DISCOVERED_CONFIG"
  echo "Switching to sudo before prompting so existing defaults can be loaded from $DISCOVERED_CONFIG ..."
  if ! sudo env ALMANAC_CONFIG_FILE="$DISCOVERED_CONFIG" "$SELF_PATH" "$requested_mode"; then
    return 1
  fi
  write_operator_checkout_artifact
  return 0
}

run_root_env_cmd() {
  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    env ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$@"
    return 0
  fi
  sudo env ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$@"
}

run_service_user_cmd() {
  if [[ "$(id -un)" == "$ALMANAC_USER" ]]; then
    env ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$@"
    return 0
  fi
  sudo -iu "$ALMANAC_USER" env ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$@"
}

repair_active_agent_runtime_access() {
  local agent_id="" unix_user=""

  if [[ ! -f "$ALMANAC_DB_PATH" ]]; then
    return 0
  fi

  while IFS=$'\t' read -r agent_id unix_user; do
    [[ -n "$agent_id" && -n "$unix_user" ]] || continue
    if ! getent passwd "$unix_user" >/dev/null 2>&1; then
      echo "Skipping shared-runtime ACL repair for $agent_id: unix user '$unix_user' is missing."
      continue
    fi
    echo "Repairing shared-runtime access for $agent_id ($unix_user)..."
    run_root_env_cmd "$ALMANAC_REPO_DIR/bin/almanac-ctl" user sync-access "$unix_user" --agent-id "$agent_id" >/dev/null
  done < <(run_root_env_cmd python3 - "$ALMANAC_DB_PATH" <<'PY'
import sqlite3
import sys

conn = sqlite3.connect(sys.argv[1])
conn.row_factory = sqlite3.Row
try:
    rows = conn.execute(
        """
        SELECT agent_id, unix_user
        FROM agents
        WHERE role = 'user' AND status = 'active'
        ORDER BY unix_user
        """
    ).fetchall()
except sqlite3.Error:
    rows = []
for row in rows:
    print(f"{row['agent_id']}\t{row['unix_user']}")
PY
  )
}

chown_managed_paths() {
  chown -R "$ALMANAC_USER:$ALMANAC_USER" "$ALMANAC_REPO_DIR"

  if [[ ! -d "$ALMANAC_PRIV_DIR" ]]; then
    return 0
  fi

  if [[ "$ENABLE_NEXTCLOUD" == "1" && -n "${NEXTCLOUD_STATE_DIR:-}" && -d "$NEXTCLOUD_STATE_DIR" ]]; then
    chown "$ALMANAC_USER:$ALMANAC_USER" "$ALMANAC_PRIV_DIR"
    find "$ALMANAC_PRIV_DIR" -path "$NEXTCLOUD_STATE_DIR" -prune -o -exec chown "$ALMANAC_USER:$ALMANAC_USER" {} +
    return 0
  fi

  chown -R "$ALMANAC_USER:$ALMANAC_USER" "$ALMANAC_PRIV_DIR"
}

enrollment_snapshot_json() {
  local target_unix_user="$1"

  run_root_env_cmd python3 - "$ALMANAC_DB_PATH" "$target_unix_user" <<'PY'
import json
import sqlite3
import sys
from pathlib import Path

db_path = Path(sys.argv[1])
target_unix_user = sys.argv[2]
agent_id = f"agent-{target_unix_user}"
payload = {
    "unix_user": target_unix_user,
    "agent_id": agent_id,
    "agent": None,
    "onboarding": [],
    "requests": [],
    "rate_limit_subjects": [],
}

if not db_path.exists():
    print(json.dumps(payload, sort_keys=True))
    raise SystemExit(0)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

agent_row = conn.execute(
    "SELECT agent_id, status, display_name, hermes_home, archived_state_path, manifest_path FROM agents WHERE unix_user = ? ORDER BY last_enrolled_at DESC LIMIT 1",
    (target_unix_user,),
).fetchone()
if agent_row is not None:
    payload["agent"] = dict(agent_row)
    agent_id = str(agent_row["agent_id"])
    payload["agent_id"] = agent_id

subjects = set()

for row in conn.execute("SELECT * FROM onboarding_sessions ORDER BY updated_at DESC").fetchall():
    try:
        answers = json.loads(row["answers_json"] or "{}")
    except Exception:
        answers = {}
    linked_agent_id = str(row["linked_agent_id"] or "")
    if str(answers.get("unix_user") or "") != target_unix_user and linked_agent_id != agent_id:
        continue
    payload["onboarding"].append(
        {
            "session_id": row["session_id"],
            "state": row["state"],
            "platform": row["platform"],
            "sender_id": row["sender_id"],
            "sender_username": row["sender_username"],
            "linked_request_id": row["linked_request_id"],
            "linked_agent_id": linked_agent_id,
            "updated_at": row["updated_at"],
            "provision_error": row["provision_error"],
        }
    )
    subjects.add(f"{row['platform']}:{row['sender_id']}")

for row in conn.execute(
    """
    SELECT request_id, status, source_ip, requested_at, approved_at,
           provisioned_at, provision_error, provision_attempts, provision_next_attempt_at
    FROM bootstrap_requests
    WHERE unix_user = ? AND auto_provision = 1
    ORDER BY requested_at DESC
    """,
    (target_unix_user,),
).fetchall():
    payload["requests"].append(dict(row))
    source_ip = str(row["source_ip"] or "")
    if ":" in source_ip:
        subjects.add(source_ip)

payload["rate_limit_subjects"] = sorted(subjects)
print(json.dumps(payload, sort_keys=True))
PY
}

restart_shared_user_services_root() {
  local uid=""

  uid="$(id -u "$ALMANAC_USER")"
  systemctl start "user@$uid.service" >/dev/null 2>&1 || true
  if [[ -S "/run/user/$uid/bus" ]]; then
    run_as_user_systemd "$ALMANAC_USER" "$uid" "systemctl --user daemon-reload"
    run_as_user_systemd "$ALMANAC_USER" "$uid" "ALMANAC_CONFIG_FILE='$CONFIG_TARGET' systemctl --user restart almanac-mcp.service almanac-notion-webhook.service almanac-qmd-mcp.service almanac-qmd-update.timer almanac-vault-watch.service almanac-github-backup.timer almanac-ssot-batcher.timer almanac-notification-delivery.timer almanac-curator-refresh.timer"
    run_as_user_systemd "$ALMANAC_USER" "$uid" "ALMANAC_CONFIG_FILE='$CONFIG_TARGET' systemctl --user start almanac-curator-refresh.service" || true

    if [[ "$PDF_INGEST_ENABLED" == "1" ]]; then
      run_as_user_systemd "$ALMANAC_USER" "$uid" "ALMANAC_CONFIG_FILE='$CONFIG_TARGET' systemctl --user restart almanac-pdf-ingest.timer"
      run_as_user_systemd "$ALMANAC_USER" "$uid" "ALMANAC_CONFIG_FILE='$CONFIG_TARGET' systemctl --user stop almanac-pdf-ingest-watch.service >/dev/null 2>&1 || true"
    fi

    if [[ "$ENABLE_QUARTO" == "1" ]]; then
      run_as_user_systemd "$ALMANAC_USER" "$uid" "ALMANAC_CONFIG_FILE='$CONFIG_TARGET' systemctl --user restart almanac-quarto-render.timer"
    fi

    if [[ "$ENABLE_NEXTCLOUD" == "1" ]]; then
      run_as_user_systemd "$ALMANAC_USER" "$uid" "ALMANAC_CONFIG_FILE='$CONFIG_TARGET' systemctl --user restart almanac-nextcloud.service"
    fi
    if [[ "${ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED:-0}" == "1" ]]; then
      run_as_user_systemd "$ALMANAC_USER" "$uid" "ALMANAC_CONFIG_FILE='$CONFIG_TARGET' systemctl --user restart almanac-curator-onboarding.service" || true
    fi
    if [[ "${ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED:-0}" == "1" ]]; then
      run_as_user_systemd "$ALMANAC_USER" "$uid" "ALMANAC_CONFIG_FILE='$CONFIG_TARGET' systemctl --user restart almanac-curator-discord-onboarding.service" || true
    fi
    if [[ "${ALMANAC_CURATOR_CHANNELS:-tui-only}" == *discord* || "${ALMANAC_CURATOR_CHANNELS:-tui-only}" == *telegram* ]]; then
      run_as_user_systemd "$ALMANAC_USER" "$uid" "ALMANAC_CONFIG_FILE='$CONFIG_TARGET' systemctl --user restart almanac-curator-gateway.service" || true
    fi
    return 0
  fi

  if [[ "${ALMANAC_ALLOW_NO_USER_BUS:-0}" != "1" ]]; then
    echo "Systemd user bus unavailable for $ALMANAC_USER; services were installed but not started." >&2
    return 1
  fi

  return 0
}

run_root_install() {
  local agent_payload_file=""
  local source_commit=""
  local source_branch=""
  local source_repo_url=""
  export ALMANAC_NAME ALMANAC_USER ALMANAC_HOME ALMANAC_REPO_DIR ALMANAC_PRIV_DIR
  export ALMANAC_PRIV_CONFIG_DIR VAULT_DIR STATE_DIR NEXTCLOUD_STATE_DIR RUNTIME_DIR
  export ALMANAC_DB_PATH ALMANAC_AGENTS_STATE_DIR ALMANAC_CURATOR_DIR ALMANAC_CURATOR_MANIFEST ALMANAC_CURATOR_HERMES_HOME ALMANAC_ARCHIVED_AGENTS_DIR
  export PUBLISHED_DIR QMD_INDEX_NAME QMD_COLLECTION_NAME VAULT_QMD_COLLECTION_MASK BACKUP_GIT_BRANCH BACKUP_GIT_REMOTE
  export PDF_INGEST_COLLECTION_NAME PDF_INGEST_ENABLED PDF_INGEST_EXTRACTOR
  export PDF_VISION_ENDPOINT PDF_VISION_MODEL PDF_VISION_API_KEY PDF_VISION_MAX_PAGES
  export VAULT_WATCH_DEBOUNCE_SECONDS VAULT_WATCH_RUN_EMBED
  export QMD_RUN_EMBED QMD_MCP_PORT ALMANAC_MCP_HOST ALMANAC_MCP_PORT ALMANAC_NOTION_WEBHOOK_HOST ALMANAC_NOTION_WEBHOOK_PORT
  export ALMANAC_BOOTSTRAP_WINDOW_SECONDS ALMANAC_BOOTSTRAP_PER_IP_LIMIT ALMANAC_BOOTSTRAP_GLOBAL_PENDING_LIMIT ALMANAC_BOOTSTRAP_PENDING_TTL_SECONDS
  export ALMANAC_AUTO_PROVISION_MAX_ATTEMPTS ALMANAC_AUTO_PROVISION_RETRY_BASE_SECONDS ALMANAC_AUTO_PROVISION_RETRY_MAX_SECONDS
  export BACKUP_GIT_AUTHOR_NAME BACKUP_GIT_AUTHOR_EMAIL NEXTCLOUD_PORT NEXTCLOUD_TRUSTED_DOMAIN
  export POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD
  export NEXTCLOUD_ADMIN_USER NEXTCLOUD_ADMIN_PASSWORD NEXTCLOUD_VAULT_MOUNT_POINT
  export OPERATOR_NOTIFY_CHANNEL_PLATFORM OPERATOR_NOTIFY_CHANNEL_ID OPERATOR_GENERAL_CHANNEL_PLATFORM OPERATOR_GENERAL_CHANNEL_ID
  export ALMANAC_MODEL_PRESET_CODEX ALMANAC_MODEL_PRESET_OPUS ALMANAC_MODEL_PRESET_CHUTES ALMANAC_CURATOR_MODEL_PRESET ALMANAC_CURATOR_CHANNELS CHUTES_MCP_URL
  export ALMANAC_UPSTREAM_REPO_URL ALMANAC_UPSTREAM_BRANCH ALMANAC_RELEASE_STATE_FILE
  export ENABLE_NEXTCLOUD ENABLE_TAILSCALE_SERVE TAILSCALE_OPERATOR_USER TAILSCALE_QMD_PATH TAILSCALE_ALMANAC_MCP_PATH ENABLE_PRIVATE_GIT ENABLE_QUARTO SEED_SAMPLE_VAULT
  export QUARTO_PROJECT_DIR QUARTO_OUTPUT_DIR

  "$BOOTSTRAP_DIR/bin/bootstrap-system.sh"
  sync_public_repo
  seed_private_repo "$ALMANAC_PRIV_DIR"
  write_runtime_config "$CONFIG_TARGET"
  chown_managed_paths
  env ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$ALMANAC_REPO_DIR/bin/install-system-services.sh"
  wipe_nextcloud_state_if_requested

  init_public_repo_if_needed

  run_as_user "$ALMANAC_USER" "env ALMANAC_CONFIG_FILE='$CONFIG_TARGET' '$ALMANAC_REPO_DIR/bin/bootstrap-userland.sh'"
  run_as_user "$ALMANAC_USER" "env ALMANAC_CONFIG_FILE='$CONFIG_TARGET' ALMANAC_ALLOW_NO_USER_BUS='${ALMANAC_ALLOW_NO_USER_BUS:-0}' '$ALMANAC_REPO_DIR/bin/install-user-services.sh'"
  chown -R "$ALMANAC_USER:$ALMANAC_USER" "$ALMANAC_PRIV_DIR"
  run_as_user "$ALMANAC_USER" "env $(curator_bootstrap_env_prefix) '$ALMANAC_REPO_DIR/bin/bootstrap-curator.sh'"
  reload_runtime_config_from_file "$CONFIG_TARGET" || true
  repair_active_agent_runtime_access

  local uid=""
  restart_shared_user_services_root
  uid="$(id -u "$ALMANAC_USER")"

  if [[ "$ENABLE_NEXTCLOUD" == "1" && "$ENABLE_TAILSCALE_SERVE" == "1" ]]; then
    if [[ -n "${TAILSCALE_OPERATOR_USER:-}" ]] && command -v tailscale >/dev/null 2>&1; then
      tailscale set --operator="$TAILSCALE_OPERATOR_USER" >/dev/null 2>&1 || true
    fi
    ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$ALMANAC_REPO_DIR/bin/tailscale-nextcloud-serve.sh"
  fi

  wait_for_port 127.0.0.1 "$QMD_MCP_PORT" 20 1
  wait_for_port 127.0.0.1 "$ALMANAC_MCP_PORT" 20 1
  wait_for_port 127.0.0.1 "$ALMANAC_NOTION_WEBHOOK_PORT" 20 1
  if [[ "$ENABLE_NEXTCLOUD" == "1" ]]; then
    wait_for_port 127.0.0.1 "$NEXTCLOUD_PORT" 45 2
  fi

  # Record the release state before health so the check_upgrade_state probe
  # doesn't false-warn about a missing release file on a first install.
  source_commit="$(git_head_commit "$BOOTSTRAP_DIR")"
  source_branch="$(git_head_branch "$BOOTSTRAP_DIR")"
  source_repo_url="$(git_origin_url "$BOOTSTRAP_DIR")"
  if [[ -n "$source_commit" ]]; then
    write_release_state "local-checkout" "$source_commit" "$source_repo_url" "$source_branch" "$BOOTSTRAP_DIR"
    chown "$ALMANAC_USER:$ALMANAC_USER" "${ALMANAC_RELEASE_STATE_FILE:-$STATE_DIR/almanac-release.json}" >/dev/null 2>&1 || true
  fi

  echo
  echo "Running health check..."
  if [[ -S "/run/user/$uid/bus" ]]; then
    run_as_user_systemd "$ALMANAC_USER" "$uid" "ALMANAC_CONFIG_FILE='$CONFIG_TARGET' ALMANAC_HEALTH_STRICT=1 '$ALMANAC_REPO_DIR/bin/health.sh'"
  else
    run_as_user "$ALMANAC_USER" "env ALMANAC_CONFIG_FILE='$CONFIG_TARGET' ALMANAC_HEALTH_STRICT=1 '$ALMANAC_REPO_DIR/bin/health.sh'"
  fi

  echo
  echo "Almanac install complete."
  echo "Public repo:  $ALMANAC_REPO_DIR"
  echo "Private repo: $ALMANAC_PRIV_DIR"
  echo "Config:       $CONFIG_TARGET"
  if [[ -n "$source_commit" ]]; then
    echo "Release:      ${source_commit:0:12} from current checkout"
  fi
  agent_payload_file="$(write_agent_install_payload_file || true)"
  if [[ -n "$agent_payload_file" && -f "$agent_payload_file" ]]; then
    chown "$ALMANAC_USER:$ALMANAC_USER" "$agent_payload_file" >/dev/null 2>&1 || true
  fi
  print_post_install_guide
}

run_root_upgrade() {
  local tmp_dir=""
  local checkout_dir=""
  local upstream_commit=""
  local uid=""
  local agent_payload_file=""

  export ALMANAC_NAME ALMANAC_USER ALMANAC_HOME ALMANAC_REPO_DIR ALMANAC_PRIV_DIR
  export ALMANAC_PRIV_CONFIG_DIR VAULT_DIR STATE_DIR NEXTCLOUD_STATE_DIR RUNTIME_DIR
  export ALMANAC_DB_PATH ALMANAC_AGENTS_STATE_DIR ALMANAC_CURATOR_DIR ALMANAC_CURATOR_MANIFEST ALMANAC_CURATOR_HERMES_HOME ALMANAC_ARCHIVED_AGENTS_DIR
  export PUBLISHED_DIR QMD_INDEX_NAME QMD_COLLECTION_NAME VAULT_QMD_COLLECTION_MASK BACKUP_GIT_BRANCH BACKUP_GIT_REMOTE
  export PDF_INGEST_COLLECTION_NAME PDF_INGEST_ENABLED PDF_INGEST_EXTRACTOR
  export PDF_VISION_ENDPOINT PDF_VISION_MODEL PDF_VISION_API_KEY PDF_VISION_MAX_PAGES
  export VAULT_WATCH_DEBOUNCE_SECONDS VAULT_WATCH_RUN_EMBED
  export QMD_RUN_EMBED QMD_MCP_PORT ALMANAC_MCP_HOST ALMANAC_MCP_PORT ALMANAC_NOTION_WEBHOOK_HOST ALMANAC_NOTION_WEBHOOK_PORT
  export ALMANAC_BOOTSTRAP_WINDOW_SECONDS ALMANAC_BOOTSTRAP_PER_IP_LIMIT ALMANAC_BOOTSTRAP_GLOBAL_PENDING_LIMIT ALMANAC_BOOTSTRAP_PENDING_TTL_SECONDS
  export ALMANAC_AUTO_PROVISION_MAX_ATTEMPTS ALMANAC_AUTO_PROVISION_RETRY_BASE_SECONDS ALMANAC_AUTO_PROVISION_RETRY_MAX_SECONDS
  export BACKUP_GIT_AUTHOR_NAME BACKUP_GIT_AUTHOR_EMAIL NEXTCLOUD_PORT NEXTCLOUD_TRUSTED_DOMAIN
  export POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD
  export NEXTCLOUD_ADMIN_USER NEXTCLOUD_ADMIN_PASSWORD NEXTCLOUD_VAULT_MOUNT_POINT
  export OPERATOR_NOTIFY_CHANNEL_PLATFORM OPERATOR_NOTIFY_CHANNEL_ID OPERATOR_GENERAL_CHANNEL_PLATFORM OPERATOR_GENERAL_CHANNEL_ID
  export ALMANAC_MODEL_PRESET_CODEX ALMANAC_MODEL_PRESET_OPUS ALMANAC_MODEL_PRESET_CHUTES ALMANAC_CURATOR_MODEL_PRESET ALMANAC_CURATOR_CHANNELS CHUTES_MCP_URL
  export ALMANAC_UPSTREAM_REPO_URL ALMANAC_UPSTREAM_BRANCH ALMANAC_RELEASE_STATE_FILE
  export ENABLE_NEXTCLOUD ENABLE_TAILSCALE_SERVE TAILSCALE_OPERATOR_USER TAILSCALE_QMD_PATH TAILSCALE_ALMANAC_MCP_PATH ENABLE_PRIVATE_GIT ENABLE_QUARTO SEED_SAMPLE_VAULT
  export QUARTO_PROJECT_DIR QUARTO_OUTPUT_DIR

  tmp_dir="$(mktemp -d /tmp/almanac-upgrade.XXXXXX)"
  checkout_dir="$tmp_dir/repo"
  trap 'rm -rf "${tmp_dir:-}"' EXIT

  echo "Fetching Almanac upstream..."
  echo "  repo:   $ALMANAC_UPSTREAM_REPO_URL"
  echo "  branch: $ALMANAC_UPSTREAM_BRANCH"
  checkout_upstream_release "$checkout_dir"
  upstream_commit="$(git_head_commit "$checkout_dir")"
  if [[ -z "$upstream_commit" ]]; then
    echo "Could not determine upstream commit after cloning $ALMANAC_UPSTREAM_REPO_URL." >&2
    return 1
  fi

  sync_public_repo_from_source "$checkout_dir" "$ALMANAC_REPO_DIR"
  seed_private_repo "$ALMANAC_PRIV_DIR"
  write_runtime_config "$CONFIG_TARGET"
  chown_managed_paths

  "$ALMANAC_REPO_DIR/bin/bootstrap-system.sh"
  env ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$ALMANAC_REPO_DIR/bin/install-system-services.sh"
  run_as_user "$ALMANAC_USER" "env ALMANAC_CONFIG_FILE='$CONFIG_TARGET' '$ALMANAC_REPO_DIR/bin/bootstrap-userland.sh'"
  run_as_user "$ALMANAC_USER" "env ALMANAC_CONFIG_FILE='$CONFIG_TARGET' ALMANAC_ALLOW_NO_USER_BUS='${ALMANAC_ALLOW_NO_USER_BUS:-0}' '$ALMANAC_REPO_DIR/bin/install-user-services.sh'"
  chown -R "$ALMANAC_USER:$ALMANAC_USER" "$ALMANAC_PRIV_DIR"
  run_as_user "$ALMANAC_USER" "env ALMANAC_CURATOR_SKIP_HERMES_SETUP='1' ALMANAC_CURATOR_SKIP_GATEWAY_SETUP='1' $(curator_bootstrap_env_prefix) '$ALMANAC_REPO_DIR/bin/bootstrap-curator.sh'"
  reload_runtime_config_from_file "$CONFIG_TARGET" || true
  repair_active_agent_runtime_access

  restart_shared_user_services_root
  uid="$(id -u "$ALMANAC_USER")"

  if [[ "$ENABLE_NEXTCLOUD" == "1" && "$ENABLE_TAILSCALE_SERVE" == "1" ]]; then
    if [[ -n "${TAILSCALE_OPERATOR_USER:-}" ]] && command -v tailscale >/dev/null 2>&1; then
      tailscale set --operator="$TAILSCALE_OPERATOR_USER" >/dev/null 2>&1 || true
    fi
    ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$ALMANAC_REPO_DIR/bin/tailscale-nextcloud-serve.sh"
  fi

  wait_for_port 127.0.0.1 "$QMD_MCP_PORT" 20 1
  wait_for_port 127.0.0.1 "$ALMANAC_MCP_PORT" 20 1
  wait_for_port 127.0.0.1 "$ALMANAC_NOTION_WEBHOOK_PORT" 20 1
  if [[ "$ENABLE_NEXTCLOUD" == "1" ]]; then
    wait_for_port 127.0.0.1 "$NEXTCLOUD_PORT" 45 2
  fi

  # Record the release state before health so the check_upgrade_state probe can
  # see the new deployed_commit. Services have already been restarted against
  # the new code at this point; the release state reflects reality regardless
  # of whether strict health passes. If health fails, the operator inspects
  # the failures against an accurately-recorded current deployment.
  write_release_state "upstream" "$upstream_commit" "$ALMANAC_UPSTREAM_REPO_URL" "$ALMANAC_UPSTREAM_BRANCH" ""
  chown "$ALMANAC_USER:$ALMANAC_USER" "${ALMANAC_RELEASE_STATE_FILE:-$STATE_DIR/almanac-release.json}" >/dev/null 2>&1 || true

  echo
  echo "Running health check..."
  if [[ -S "/run/user/$uid/bus" ]]; then
    run_as_user_systemd "$ALMANAC_USER" "$uid" "ALMANAC_CONFIG_FILE='$CONFIG_TARGET' ALMANAC_HEALTH_STRICT=1 '$ALMANAC_REPO_DIR/bin/health.sh'"
  else
    run_as_user "$ALMANAC_USER" "env ALMANAC_CONFIG_FILE='$CONFIG_TARGET' ALMANAC_HEALTH_STRICT=1 '$ALMANAC_REPO_DIR/bin/health.sh'"
  fi

  echo
  echo "Almanac upgrade complete."
  echo "Public repo:  $ALMANAC_REPO_DIR"
  echo "Private repo: $ALMANAC_PRIV_DIR"
  echo "Config:       $CONFIG_TARGET"
  echo "Release:      ${upstream_commit:0:12} from ${ALMANAC_UPSTREAM_REPO_URL}#${ALMANAC_UPSTREAM_BRANCH}"
  agent_payload_file="$(write_agent_install_payload_file || true)"
  if [[ -n "$agent_payload_file" && -f "$agent_payload_file" ]]; then
    chown "$ALMANAC_USER:$ALMANAC_USER" "$agent_payload_file" >/dev/null 2>&1 || true
  fi
  rm -rf "$tmp_dir"
  trap - EXIT
  echo
  echo "Manual upstream check:"
  echo "  $ALMANAC_REPO_DIR/bin/almanac-ctl upgrade check"
  echo "Host health check:"
  echo "  $ALMANAC_REPO_DIR/deploy.sh health"
}

run_root_remove() {
  local uid=""
  local remove_repo_with_user_home="0"

  if id -u "$ALMANAC_USER" >/dev/null 2>&1; then
    uid="$(id -u "$ALMANAC_USER")"
    systemctl start "user@$uid.service" >/dev/null 2>&1 || true

    if [[ -x "$ALMANAC_REPO_DIR/bin/nextcloud-down.sh" ]]; then
      run_as_user "$ALMANAC_USER" "env ALMANAC_CONFIG_FILE='$CONFIG_TARGET' '$ALMANAC_REPO_DIR/bin/nextcloud-down.sh'" >/dev/null 2>&1 || true
    fi

    if [[ -S "/run/user/$uid/bus" ]]; then
      run_as_user_systemd "$ALMANAC_USER" "$uid" "ALMANAC_CONFIG_FILE='$CONFIG_TARGET' systemctl --user disable --now almanac-nextcloud.service almanac-qmd-mcp.service almanac-qmd-update.timer almanac-vault-watch.service almanac-pdf-ingest.timer almanac-pdf-ingest-watch.service almanac-github-backup.timer almanac-quarto-render.timer almanac-mcp.service almanac-notion-webhook.service almanac-ssot-batcher.timer almanac-notification-delivery.timer almanac-curator-refresh.timer almanac-curator-gateway.service almanac-curator-onboarding.service almanac-curator-discord-onboarding.service >/dev/null 2>&1 || true" || true
      run_as_user_systemd "$ALMANAC_USER" "$uid" "systemctl --user daemon-reload >/dev/null 2>&1 || true" || true
    fi

    find "$ALMANAC_HOME/.config/systemd/user" -maxdepth 1 -type f \
      \( -name 'almanac-*.service' -o -name 'almanac-*.timer' \) -delete 2>/dev/null || true

    loginctl disable-linger "$ALMANAC_USER" >/dev/null 2>&1 || true
    pkill -u "$ALMANAC_USER" >/dev/null 2>&1 || true
    systemctl stop "user@$uid.service" >/dev/null 2>&1 || true
  fi

  if [[ "$REMOVE_SERVICE_USER" == "1" && -d "$ALMANAC_HOME" ]]; then
    if path_is_within "$ALMANAC_REPO_DIR" "$ALMANAC_HOME"; then
      remove_repo_with_user_home="1"
    fi
  fi

  if [[ "$REMOVE_PUBLIC_REPO" == "1" && -x "$ALMANAC_REPO_DIR/bin/tailscale-nextcloud-unserve.sh" ]]; then
    ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$ALMANAC_REPO_DIR/bin/tailscale-nextcloud-unserve.sh" >/dev/null 2>&1 || true
  fi

  systemctl disable --now almanac-enrollment-provision.timer >/dev/null 2>&1 || true
  systemctl stop almanac-enrollment-provision.service >/dev/null 2>&1 || true
  rm -f /etc/systemd/system/almanac-enrollment-provision.service /etc/systemd/system/almanac-enrollment-provision.timer
  systemctl daemon-reload >/dev/null 2>&1 || true

  if [[ "$REMOVE_PUBLIC_REPO" == "1" && "$remove_repo_with_user_home" != "1" ]]; then
    safe_remove_path "$ALMANAC_REPO_DIR"
    if [[ "$ALMANAC_PRIV_DIR" != "$ALMANAC_REPO_DIR" ]] && ! path_is_within "$ALMANAC_PRIV_DIR" "$ALMANAC_REPO_DIR"; then
      safe_remove_path "$ALMANAC_PRIV_DIR"
    fi
  fi

  if [[ "$REMOVE_USER_TOOLING" == "1" && "$REMOVE_SERVICE_USER" != "1" ]]; then
    safe_remove_path "$ALMANAC_HOME/.cache/qmd"
    safe_remove_path "$ALMANAC_HOME/.cache/containers"
    safe_remove_path "$ALMANAC_HOME/.config/cni"
    safe_remove_path "$ALMANAC_HOME/.config/containers"
    safe_remove_path "$ALMANAC_HOME/.local/share/containers"
    safe_remove_path "$ALMANAC_HOME/.local/bin/podman-compose"
    safe_remove_path "$ALMANAC_HOME/.nvm"
  fi

  if [[ "$REMOVE_SERVICE_USER" == "1" ]] && id -u "$ALMANAC_USER" >/dev/null 2>&1; then
    userdel -r "$ALMANAC_USER" >/dev/null 2>&1 || userdel "$ALMANAC_USER" >/dev/null 2>&1 || true
  fi

  if [[ "$REMOVE_PUBLIC_REPO" == "1" ]]; then
    if [[ -e "$ALMANAC_REPO_DIR" ]]; then
      safe_remove_path "$ALMANAC_REPO_DIR"
    fi
    if [[ "$ALMANAC_PRIV_DIR" != "$ALMANAC_REPO_DIR" ]] && [[ -e "$ALMANAC_PRIV_DIR" ]] && ! path_is_within "$ALMANAC_PRIV_DIR" "$ALMANAC_REPO_DIR"; then
      safe_remove_path "$ALMANAC_PRIV_DIR"
    fi
  fi

  echo
  echo "Almanac teardown complete."
  echo "Removed service user: $REMOVE_SERVICE_USER"
  echo "Removed repo/state:   $REMOVE_PUBLIC_REPO"
  echo "Removed tooling:      $REMOVE_USER_TOOLING"
}

run_enrollment_status() {
  local onboarding_file="" provision_file="" timer_enabled="" timer_active="" service_active=""

  prepare_deployed_context
  if maybe_reexec_with_sudo_for_config enrollment-status; then
    return 0
  fi
  ensure_deployed_config_exists

  onboarding_file="$(mktemp)"
  provision_file="$(mktemp)"

  run_service_user_cmd "$ALMANAC_REPO_DIR/bin/almanac-ctl" --json onboarding list >"$onboarding_file"
  run_service_user_cmd "$ALMANAC_REPO_DIR/bin/almanac-ctl" --json provision list >"$provision_file"

  timer_enabled="$(systemctl is-enabled almanac-enrollment-provision.timer 2>/dev/null || true)"
  timer_active="$(systemctl is-active almanac-enrollment-provision.timer 2>/dev/null || true)"
  service_active="$(systemctl is-active almanac-enrollment-provision.service 2>/dev/null || true)"

  echo "Enrollment status"
  echo
  echo "Config:        $CONFIG_TARGET"
  echo "Service user:  $ALMANAC_USER"
  echo "Repo:          $ALMANAC_REPO_DIR"
  echo "DB:            $ALMANAC_DB_PATH"
  echo "Provisioner:"
  echo "  timer enabled: $timer_enabled"
  echo "  timer active:  $timer_active"
  echo "  service:       $service_active"
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
  echo "  $ALMANAC_REPO_DIR/deploy.sh enrollment-trace --unix-user <unix-user>"
  echo "  $ALMANAC_REPO_DIR/deploy.sh enrollment-align"
  echo "  $ALMANAC_REPO_DIR/deploy.sh enrollment-reset"
}

resolve_enrollment_trace_selector() {
  local provided_count=0
  local selector=""
  local kind=""

  [[ -n "${TRACE_UNIX_USER:-}" ]] && provided_count=$((provided_count + 1))
  [[ -n "${TRACE_SESSION_ID:-}" ]] && provided_count=$((provided_count + 1))
  [[ -n "${TRACE_REQUEST_ID:-}" ]] && provided_count=$((provided_count + 1))

  if (( provided_count > 1 )); then
    echo "Provide only one of --unix-user, --session-id, or --request-id." >&2
    exit 1
  fi

  if [[ -n "${TRACE_UNIX_USER:-}" ]]; then
    kind="unix-user"
    selector="$TRACE_UNIX_USER"
  elif [[ -n "${TRACE_SESSION_ID:-}" ]]; then
    kind="session-id"
    selector="$TRACE_SESSION_ID"
  elif [[ -n "${TRACE_REQUEST_ID:-}" ]]; then
    kind="request-id"
    selector="$TRACE_REQUEST_ID"
  else
    selector="$(ask "Trace unix user, onboarding session id, or bootstrap request id" "${ENROLLMENT_TRACE_TARGET:-}")"
    if [[ -z "$selector" ]]; then
      echo "A trace target is required." >&2
      exit 1
    fi
    case "$selector" in
      onb_*) kind="session-id" ;;
      req_*) kind="request-id" ;;
      *) kind="unix-user" ;;
    esac
  fi

  printf '%s\t%s\n' "$kind" "$selector"
}

run_enrollment_trace() {
  local selector_spec="" selector_kind="" selector_value="" trace_file=""
  local timer_enabled="" timer_active="" service_active="" resolved_unix_user="" resolved_hermes_home=""

  prepare_deployed_context
  if maybe_reexec_with_sudo_for_config enrollment-trace; then
    return 0
  fi
  ensure_deployed_config_exists

  selector_spec="$(resolve_enrollment_trace_selector)"
  IFS=$'\t' read -r selector_kind selector_value <<<"$selector_spec"
  trace_file="$(mktemp)"

  run_root_env_cmd python3 - "$ALMANAC_DB_PATH" "$STATE_DIR" "$selector_kind" "$selector_value" <<'PY' >"$trace_file"
import json
import sqlite3
import sys
from pathlib import Path

db_path = Path(sys.argv[1])
state_dir = Path(sys.argv[2])
selector_kind = sys.argv[3]
selector_value = sys.argv[4]


def json_loads(raw, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def request_provision_state(row):
    attempts = int(row.get("provision_attempts") or 0)
    status = str(row.get("status") or "")
    if row.get("provisioned_at"):
        return "completed"
    if status == "cancelled":
        return "cancelled"
    if status != "approved":
        return status or "pending"
    if row.get("provision_error") and not row.get("provision_next_attempt_at"):
        return "failed"
    if row.get("provision_error"):
        return "retry-scheduled"
    if row.get("provision_started_at"):
        return "running"
    if attempts > 0:
        return "running"
    return "queued"


def summarize_session(row):
    answers = json_loads(row["answers_json"], {})
    return {
        "session_id": row["session_id"],
        "platform": row["platform"],
        "chat_id": row["chat_id"],
        "sender_id": row["sender_id"],
        "sender_username": row["sender_username"],
        "sender_display_name": row["sender_display_name"],
        "state": row["state"],
        "answers": {
            "name": answers.get("name", ""),
            "unix_user": answers.get("unix_user", ""),
            "purpose": answers.get("purpose", ""),
            "bot_platform": answers.get("bot_platform", ""),
            "bot_name": answers.get("bot_name", ""),
            "model_preset": answers.get("model_preset", ""),
            "pending_provider_setup": bool(answers.get("pending_provider_setup")),
            "pending_provider_secret_path": str(answers.get("pending_provider_secret_path") or ""),
        },
        "operator_notified_at": row["operator_notified_at"],
        "approved_at": row["approved_at"],
        "approved_by_actor": row["approved_by_actor"],
        "denied_at": row["denied_at"],
        "denied_by_actor": row["denied_by_actor"],
        "denial_reason": row["denial_reason"],
        "linked_request_id": row["linked_request_id"],
        "linked_agent_id": row["linked_agent_id"],
        "pending_bot_token_path": row["pending_bot_token_path"],
        "provision_error": row["provision_error"],
        "completed_at": row["completed_at"],
        "last_prompt_at": row["last_prompt_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def summarize_request(row):
    payload = dict(row)
    payload["requested_channels"] = json_loads(row["requested_channels_json"], [])
    payload["prior_defaults"] = json_loads(row["prior_defaults_json"], {})
    payload["provision_state"] = request_provision_state(payload)
    payload["log_path"] = str(state_dir / "auto-provision" / f"{row['request_id']}.log")
    return payload


payload = {
    "selector_kind": selector_kind,
    "selector_value": selector_value,
    "unix_user": "",
    "agent_id": "",
    "agent": None,
    "onboarding": [],
    "requests": [],
    "rate_limit_subjects": [],
    "inferred_stage": "not-found",
    "next_action": "No matching onboarding session, request, or agent was found.",
}

if not db_path.exists():
    print(json.dumps(payload, sort_keys=True))
    raise SystemExit(0)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

selected_session = None
selected_request = None
target_unix_user = ""
agent_id = ""

if selector_kind == "session-id":
    selected_session = conn.execute(
        "SELECT * FROM onboarding_sessions WHERE session_id = ?",
        (selector_value,),
    ).fetchone()
    if selected_session is not None:
        answers = json_loads(selected_session["answers_json"], {})
        target_unix_user = str(answers.get("unix_user") or "")
        agent_id = str(selected_session["linked_agent_id"] or "")
        linked_request_id = str(selected_session["linked_request_id"] or "")
        if linked_request_id:
            selected_request = conn.execute(
                "SELECT * FROM bootstrap_requests WHERE request_id = ?",
                (linked_request_id,),
            ).fetchone()
            if selected_request is not None and not target_unix_user:
                target_unix_user = str(selected_request["unix_user"] or "")
elif selector_kind == "request-id":
    selected_request = conn.execute(
        "SELECT * FROM bootstrap_requests WHERE request_id = ?",
        (selector_value,),
    ).fetchone()
    if selected_request is not None:
        target_unix_user = str(selected_request["unix_user"] or "")
        agent_id = str(selected_request["prior_agent_id"] or "")
else:
    target_unix_user = selector_value

if target_unix_user and not agent_id:
    agent_id = f"agent-{target_unix_user}"

agent_row = None
if target_unix_user:
    agent_row = conn.execute(
        """
        SELECT *
        FROM agents
        WHERE unix_user = ?
        ORDER BY last_enrolled_at DESC
        LIMIT 1
        """,
        (target_unix_user,),
    ).fetchone()
elif agent_id:
    agent_row = conn.execute(
        "SELECT * FROM agents WHERE agent_id = ?",
        (agent_id,),
    ).fetchone()

if agent_row is not None:
    agent_payload = dict(agent_row)
    agent_payload["channels"] = json_loads(agent_row["channels_json"], [])
    agent_payload["allowed_mcps"] = json_loads(agent_row["allowed_mcps_json"], [])
    agent_payload["home_channel"] = json_loads(agent_row["home_channel_json"], {})
    payload["agent"] = agent_payload
    payload["agent_id"] = str(agent_row["agent_id"])
    if not target_unix_user:
        target_unix_user = str(agent_row["unix_user"])
else:
    payload["agent_id"] = agent_id

payload["unix_user"] = target_unix_user

subjects = set()
session_rows = conn.execute(
    """
    SELECT *
    FROM onboarding_sessions
    ORDER BY updated_at DESC
    """
).fetchall()
for row in session_rows:
    answers = json_loads(row["answers_json"], {})
    linked_agent_id = str(row["linked_agent_id"] or "")
    session_unix_user = str(answers.get("unix_user") or "")
    if selector_kind == "session-id":
        matches = (
            str(row["session_id"]) == selector_value
            or (target_unix_user and session_unix_user == target_unix_user)
            or (payload["agent_id"] and linked_agent_id == payload["agent_id"])
        )
    else:
        matches = (
            (target_unix_user and session_unix_user == target_unix_user)
            or (payload["agent_id"] and linked_agent_id == payload["agent_id"])
        )
    if not matches:
        continue
    payload["onboarding"].append(summarize_session(row))
    subjects.add(f"{row['platform']}:{row['sender_id']}")

request_rows = []
if target_unix_user:
    request_rows = conn.execute(
        """
        SELECT *
        FROM bootstrap_requests
        WHERE unix_user = ? AND auto_provision = 1
        ORDER BY requested_at DESC
        """,
        (target_unix_user,),
    ).fetchall()
elif selected_request is not None:
    request_rows = [selected_request]
for row in request_rows:
    request_payload = summarize_request(row)
    payload["requests"].append(request_payload)
    source_ip = str(row["source_ip"] or "")
    if ":" in source_ip:
        subjects.add(source_ip)

latest_session = payload["onboarding"][0] if payload["onboarding"] else None
latest_request = payload["requests"][0] if payload["requests"] else None
agent = payload["agent"] or {}

if latest_session is not None:
    state = str(latest_session.get("state") or "")
    if state in {"awaiting-name", "awaiting-unix-user", "awaiting-purpose", "awaiting-bot-platform", "awaiting-bot-name", "awaiting-model-preset"}:
        payload["inferred_stage"] = "intake-in-progress"
        payload["next_action"] = "Continue the Curator interview in DM until it reaches operator approval."
    elif state == "awaiting-operator-approval":
        payload["inferred_stage"] = "waiting-on-operator-approval"
        payload["next_action"] = f"Approve onboarding session {latest_session['session_id']} or deny it."
    elif state == "awaiting-bot-token":
        payload["inferred_stage"] = "waiting-on-user-bot-token"
        payload["next_action"] = "The user must send their private bot token to Curator."
    elif state == "awaiting-provider-browser-auth":
        payload["inferred_stage"] = "waiting-on-provider-browser-auth"
        payload["next_action"] = "The user must finish provider authorization in the browser; the root provisioner will poll and continue."
    elif state == "provision-pending":
        if latest_request is None:
            payload["inferred_stage"] = "provision-pending-without-request"
            payload["next_action"] = "Inspect the linked onboarding session; it reached provisioning without a bootstrap request."
        else:
            provision_state = str(latest_request.get("provision_state") or "")
            if provision_state == "queued":
                payload["inferred_stage"] = "queued-for-root-provisioner"
                payload["next_action"] = "Wait for the root provisioner timer or start almanac-enrollment-provision.service once."
            elif provision_state == "running":
                payload["inferred_stage"] = "root-provisioner-running"
                payload["next_action"] = "Inspect the root provisioner journal and the per-request auto-provision log."
            elif provision_state == "retry-scheduled":
                payload["inferred_stage"] = "root-provisioner-retry-scheduled"
                payload["next_action"] = "Inspect the provision error, repair the host-side issue, then let the timer retry or force a retry."
            elif provision_state == "failed":
                payload["inferred_stage"] = "root-provisioner-failed"
                payload["next_action"] = "Repair the failure, then cancel/reset or retry the failed provisioning request."
            elif provision_state == "completed":
                payload["inferred_stage"] = "post-provision-gateway-config"
                payload["next_action"] = "Base provisioning completed. If onboarding is not completed yet, inspect post-provision gateway configuration."
            else:
                payload["inferred_stage"] = provision_state or "provision-pending"
                payload["next_action"] = "Inspect the linked request and provisioner logs."
    elif state == "completed":
        if str(agent.get("status") or "") == "active":
            payload["inferred_stage"] = "completed"
            payload["next_action"] = "Onboarding is completed and the user agent is active."
        else:
            payload["inferred_stage"] = "completed-with-agent-drift"
            payload["next_action"] = "Onboarding is marked completed, but the agent is not active; inspect the user agent services."
    elif state == "denied":
        payload["inferred_stage"] = "denied"
        payload["next_action"] = "No action is pending. Start a new onboarding session if needed."
    elif state == "cancelled":
        payload["inferred_stage"] = "cancelled"
        payload["next_action"] = "No action is pending. Start a new onboarding session if needed."
elif latest_request is not None:
    provision_state = str(latest_request.get("provision_state") or "")
    payload["inferred_stage"] = provision_state or str(latest_request.get("status") or "request-only")
    if provision_state == "completed":
        payload["next_action"] = "Provisioning completed. Inspect the user agent or gateway if the user still cannot talk to their bot."
    elif provision_state in {"running", "retry-scheduled", "failed", "queued"}:
        payload["next_action"] = "Inspect the root provisioner journal and the per-request auto-provision log."
    else:
        payload["next_action"] = "Inspect the bootstrap request lifecycle."
elif agent:
    payload["inferred_stage"] = f"agent-{agent.get('status') or 'unknown'}"
    payload["next_action"] = "Inspect the user agent services and refresh path."

payload["rate_limit_subjects"] = sorted(subjects)
print(json.dumps(payload, sort_keys=True))
PY

  timer_enabled="$(systemctl is-enabled almanac-enrollment-provision.timer 2>/dev/null || true)"
  timer_active="$(systemctl is-active almanac-enrollment-provision.timer 2>/dev/null || true)"
  service_active="$(systemctl is-active almanac-enrollment-provision.service 2>/dev/null || true)"
  resolved_unix_user="$(python3 - "$trace_file" <<'PY'
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)
print(data.get("unix_user", ""))
PY
)"
  resolved_hermes_home="$(python3 - "$trace_file" <<'PY'
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)
agent = data.get("agent") or {}
print(agent.get("hermes_home", ""))
PY
)"

  echo "Enrollment trace"
  echo
  echo "Config:        $CONFIG_TARGET"
  echo "Service user:  $ALMANAC_USER"
  echo "Repo:          $ALMANAC_REPO_DIR"
  echo "DB:            $ALMANAC_DB_PATH"
  echo "Selector:      $selector_kind=$selector_value"
  echo "Provisioner:"
  echo "  timer enabled: $timer_enabled"
  echo "  timer active:  $timer_active"
  echo "  service:       $service_active"
  echo

  python3 - "$trace_file" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)

print("Resolved state:")
print(f"  unix_user:      {data.get('unix_user') or '-'}")
print(f"  agent_id:       {data.get('agent_id') or '-'}")
print(f"  inferred stage: {data.get('inferred_stage') or '-'}")
print(f"  next action:    {data.get('next_action') or '-'}")

agent = data.get("agent") or {}
print()
print("Agent:")
if not agent:
    print("  missing")
else:
    channels = ", ".join(agent.get("channels") or []) or "-"
    print(f"  status:         {agent.get('status') or '-'}")
    print(f"  unix_user:      {agent.get('unix_user') or '-'}")
    print(f"  model preset:   {agent.get('model_preset') or '-'}")
    print(f"  channels:       {channels}")
    print(f"  hermes home:    {agent.get('hermes_home') or '-'}")
    print(f"  last enrolled:  {agent.get('last_enrolled_at') or '-'}")

print()
print("Onboarding sessions:")
if not data.get("onboarding"):
    print("  none")
else:
    for row in data["onboarding"]:
        answers = row.get("answers") or {}
        print(
            f"  {row.get('session_id') or '-'} state={row.get('state') or '-'} "
            f"platform={row.get('platform') or '-'} updated={row.get('updated_at') or '-'}"
        )
        print(
            f"    unix_user={answers.get('unix_user') or '-'} "
            f"bot_platform={answers.get('bot_platform') or '-'} "
            f"bot_name={answers.get('bot_name') or '-'} "
            f"model={answers.get('model_preset') or '-'}"
        )
        if row.get("linked_request_id"):
            print(f"    linked_request={row['linked_request_id']}")
        if row.get("provision_error"):
            print(f"    error={row['provision_error']}")

print()
print("Auto-provision requests:")
if not data.get("requests"):
    print("  none")
else:
    for row in data["requests"]:
        print(
            f"  {row.get('request_id') or '-'} provision_state={row.get('provision_state') or '-'} "
            f"status={row.get('status') or '-'} attempts={row.get('provision_attempts') or 0} "
            f"requested={row.get('requested_at') or '-'}"
        )
        print(
            f"    source={row.get('source_ip') or '-'} "
            f"channels={','.join(row.get('requested_channels') or []) or '-'} "
            f"model={row.get('requested_model_preset') or '-'}"
        )
        if row.get("approved_at") or row.get("provisioned_at") or row.get("provision_next_attempt_at"):
            print(
                f"    approved={row.get('approved_at') or '-'} "
                f"provisioned={row.get('provisioned_at') or '-'} "
                f"next_attempt={row.get('provision_next_attempt_at') or '-'}"
            )
        if row.get("provision_error"):
            print(f"    error={row['provision_error']}")
        if row.get("log_path"):
            print(f"    log={row['log_path']}")

subjects = data.get("rate_limit_subjects") or []
print()
print(f"Related rate-limit subjects: {', '.join(subjects) if subjects else '(none)'}")
PY

  if [[ -n "$resolved_unix_user" ]]; then
    echo
    echo "Unix account:"
    if getent passwd "$resolved_unix_user" >/dev/null 2>&1; then
      getent passwd "$resolved_unix_user" | awk -F: '{printf "  passwd: %s uid=%s gid=%s home=%s shell=%s\n", $1, $3, $4, $6, $7}'
      if [[ -d "/home/$resolved_unix_user" ]]; then
        echo "  home:   present"
      else
        echo "  home:   missing"
      fi
    else
      echo "  missing"
    fi
  fi

  user_gateway_expected="$(python3 - "$trace_file" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)

agent = data.get("agent") or {}
channels = [str(item).strip().lower() for item in (agent.get("channels") or [])]
latest_session = (data.get("onboarding") or [None])[0] or {}
answers = latest_session.get("answers") or {}
bot_platform = str(answers.get("bot_platform") or "").strip().lower()

expected = any(channel in {"discord", "telegram"} for channel in channels)
if not expected and bot_platform in {"discord", "telegram"}:
    state = str(latest_session.get("state") or "")
    expected = state in {"provision-pending", "completed"}

print("1" if expected else "0")
PY
)"
  if [[ "$user_gateway_expected" == "1" && -n "$resolved_unix_user" ]] && getent passwd "$resolved_unix_user" >/dev/null 2>&1; then
    resolved_uid="$(getent passwd "$resolved_unix_user" | awk -F: '{print $3}')"
    user_gateway_unit="/home/$resolved_unix_user/.config/systemd/user/almanac-user-agent-gateway.service"
    gateway_enabled="$(run_root_env_cmd runuser -u "$resolved_unix_user" -- env XDG_RUNTIME_DIR="/run/user/$resolved_uid" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$resolved_uid/bus" systemctl --user is-enabled almanac-user-agent-gateway.service 2>/dev/null || true)"
    gateway_active="$(run_root_env_cmd runuser -u "$resolved_unix_user" -- env XDG_RUNTIME_DIR="/run/user/$resolved_uid" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$resolved_uid/bus" systemctl --user is-active almanac-user-agent-gateway.service 2>/dev/null || true)"
    echo
    echo "User gateway:"
    if [[ -f "$user_gateway_unit" ]]; then
      echo "  unit file:      $user_gateway_unit"
    else
      echo "  unit file:      missing ($user_gateway_unit)"
    fi
    echo "  enabled:        ${gateway_enabled:-unknown}"
    echo "  active:         ${gateway_active:-unknown}"
    if [[ -n "$resolved_hermes_home" ]]; then
      echo "  runtime state:"
      run_root_env_cmd runuser -u "$resolved_unix_user" -- env HERMES_HOME="$resolved_hermes_home" "$RUNTIME_DIR/hermes-venv/bin/python3" - <<'PY' || true
import json
import os
from pathlib import Path

state_path = Path(os.environ["HERMES_HOME"]) / "gateway_state.json"
if not state_path.is_file():
    print(f"    missing ({state_path})")
    raise SystemExit(0)

try:
    payload = json.loads(state_path.read_text(encoding="utf-8"))
except Exception as exc:
    print(f"    unreadable ({state_path}): {exc}")
    raise SystemExit(0)

print(f"    file:          {state_path}")
print(f"    gateway_state: {payload.get('gateway_state') or '-'}")
print(f"    updated_at:    {payload.get('updated_at') or '-'}")
if payload.get("exit_reason"):
    print(f"    exit_reason:   {payload.get('exit_reason')}")

platforms = payload.get("platforms") or {}
if not isinstance(platforms, dict) or not platforms:
    print("    platforms:     none")
    raise SystemExit(0)

for name in sorted(platforms):
    platform_payload = platforms.get(name) or {}
    state = platform_payload.get("state") or "-"
    error = platform_payload.get("error_message") or ""
    if error:
        print(f"    platform[{name}]: {state} ({error})")
    else:
        print(f"    platform[{name}]: {state}")
PY
    fi
    echo
    echo "Recent user gateway status:"
    run_root_env_cmd runuser -u "$resolved_unix_user" -- env XDG_RUNTIME_DIR="/run/user/$resolved_uid" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$resolved_uid/bus" systemctl --user status almanac-user-agent-gateway.service -n "$TRACE_LOG_LINES" --no-pager || true
  fi

  echo
  echo "Recent root provisioner journal:"
  run_root_env_cmd journalctl -u almanac-enrollment-provision.service -n "$TRACE_LOG_LINES" --no-pager || true

  while IFS= read -r log_path; do
    [[ -n "$log_path" ]] || continue
    if [[ -f "$log_path" ]]; then
      echo
      echo "Recent auto-provision log: $log_path"
      run_root_env_cmd tail -n "$TRACE_LOG_LINES" "$log_path" || true
    fi
  done < <(python3 - "$trace_file" <<'PY'
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)
for row in data.get("requests") or []:
    path = str(row.get("log_path") or "")
    if path:
        print(path)
PY
)

  rm -f "$trace_file"
  echo
  echo "Repair commands:"
  echo "  $ALMANAC_REPO_DIR/deploy.sh enrollment-align"
  if [[ -n "$resolved_unix_user" ]]; then
    echo "  ENROLLMENT_RESET_UNIX_USER=$resolved_unix_user $ALMANAC_REPO_DIR/deploy.sh enrollment-reset"
  else
    echo "  $ALMANAC_REPO_DIR/deploy.sh enrollment-reset"
  fi
}

run_enrollment_align() {
  local agent_id="" unix_user="" hermes_home="" channels_json="" bot_label="" uid="" activation_path="" user_home=""

  prepare_deployed_context
  if maybe_reexec_with_sudo_for_config enrollment-align; then
    return 0
  fi
  ensure_deployed_config_exists

  if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    sudo env ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$SELF_PATH" enrollment-align
    write_operator_checkout_artifact
    return 0
  fi

  echo "Realigning enrollment services..."
  env ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$ALMANAC_REPO_DIR/bin/install-system-services.sh"
  run_as_user "$ALMANAC_USER" "env ALMANAC_CONFIG_FILE='$CONFIG_TARGET' ALMANAC_ALLOW_NO_USER_BUS='${ALMANAC_ALLOW_NO_USER_BUS:-1}' '$ALMANAC_REPO_DIR/bin/install-user-services.sh'"
  while IFS=$'\t' read -r agent_id unix_user hermes_home channels_json bot_label; do
    [[ -n "$agent_id" && -n "$unix_user" && -n "$hermes_home" && -n "$channels_json" ]] || continue
    if ! getent passwd "$unix_user" >/dev/null 2>&1; then
      echo "Skipping $agent_id: unix user '$unix_user' is missing."
      continue
    fi
    uid="$(id -u "$unix_user")"
    user_home="$(getent passwd "$unix_user" | cut -d: -f6)"
    activation_path="$STATE_DIR/activation-triggers/$agent_id.json"
    run_root_env_cmd "$ALMANAC_REPO_DIR/bin/almanac-ctl" user sync-access "$unix_user" --agent-id "$agent_id" >/dev/null 2>&1 || true
    if [[ -n "$bot_label" ]]; then
      run_root_env_cmd env \
        ALMANAC_CONFIG_FILE="$CONFIG_TARGET" \
        PYTHONPATH="$ALMANAC_REPO_DIR/python${PYTHONPATH:+:$PYTHONPATH}" \
        python3 - "$agent_id" "$bot_label" <<'PY' >/dev/null 2>&1 || true
import sys

from almanac_control import Config, connect_db, update_agent_display_name

cfg = Config.from_env()
with connect_db(cfg) as conn:
    update_agent_display_name(conn, cfg, agent_id=sys.argv[1], display_name=sys.argv[2])
PY
      run_root_env_cmd runuser -u "$unix_user" -- env \
        HOME="$user_home" \
        USER="$unix_user" \
        LOGNAME="$unix_user" \
        HERMES_HOME="$hermes_home" \
        "$RUNTIME_DIR/hermes-venv/bin/python3" \
        "$ALMANAC_REPO_DIR/python/almanac_headless_hermes_setup.py" \
        --prefill-only \
        --bot-name "$bot_label" \
        --unix-user "$unix_user" >/dev/null 2>&1 || true
    fi
    run_root_env_cmd runuser -u "$unix_user" -- env \
      HOME="$user_home" \
      USER="$unix_user" \
      LOGNAME="$unix_user" \
      HERMES_HOME="$hermes_home" \
      "$ALMANAC_REPO_DIR/bin/install-almanac-skills.sh" \
      "$ALMANAC_REPO_DIR" \
      "$hermes_home" \
      almanac-qmd-mcp \
      almanac-vault-reconciler \
      almanac-first-contact \
      almanac-vaults \
      almanac-ssot >/dev/null
    echo "Reinstalling user-agent services for $agent_id ($unix_user)..."
    run_root_env_cmd runuser -u "$unix_user" -- env \
      XDG_RUNTIME_DIR="/run/user/$uid" \
      DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" \
      HERMES_HOME="$hermes_home" \
      "$ALMANAC_REPO_DIR/bin/install-agent-user-services.sh" \
      "$agent_id" \
      "$ALMANAC_REPO_DIR" \
      "$hermes_home" \
      "$channels_json" \
      "$activation_path" \
      "$RUNTIME_DIR/hermes-venv/bin/hermes" || true
    run_root_env_cmd runuser -u "$unix_user" -- env \
      XDG_RUNTIME_DIR="/run/user/$uid" \
      DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" \
      systemctl --user start almanac-user-agent-refresh.service >/dev/null 2>&1 || true
  done < <(run_root_env_cmd python3 - "$ALMANAC_DB_PATH" <<'PY'
import json
import sqlite3
import sys

conn = sqlite3.connect(sys.argv[1])
conn.row_factory = sqlite3.Row

rows = conn.execute(
    """
    SELECT agent_id, unix_user, hermes_home, channels_json
    FROM agents
    WHERE role = 'user' AND status = 'active'
    ORDER BY unix_user
    """
).fetchall()

session_rows = conn.execute(
    """
    SELECT linked_agent_id, answers_json
    FROM onboarding_sessions
    WHERE state = 'completed'
    ORDER BY COALESCE(completed_at, updated_at, created_at) DESC
    """
).fetchall()

bot_labels = {}
for row in session_rows:
    agent_id = str(row["linked_agent_id"] or "").strip()
    if not agent_id or agent_id in bot_labels:
        continue
    try:
        answers = json.loads(row["answers_json"] or "{}")
    except Exception:
        continue
    label = str(
        answers.get("bot_display_name")
        or answers.get("bot_username")
        or answers.get("preferred_bot_name")
        or ""
    ).strip()
    if label:
        bot_labels[agent_id] = label

for row in rows:
    channels = []
    try:
        channels = json.loads(row["channels_json"] or "[]")
    except Exception:
        channels = []
    print("\t".join([
        str(row["agent_id"] or ""),
        str(row["unix_user"] or ""),
        str(row["hermes_home"] or ""),
        json.dumps(channels),
        bot_labels.get(str(row["agent_id"] or ""), ""),
    ]))
PY
)
  restart_shared_user_services_root || true
  systemctl reset-failed almanac-enrollment-provision.service almanac-enrollment-provision.timer >/dev/null 2>&1 || true
  systemctl enable almanac-enrollment-provision.timer >/dev/null
  systemctl restart almanac-enrollment-provision.timer
  systemctl start almanac-enrollment-provision.service >/dev/null 2>&1 || true
  echo "Enrollment provisioner, shared services, and active external user-agent units realigned."
  echo
  run_enrollment_status
}

run_enrollment_reset() {
  local target_unix_user="" remove_unix_user="" purge_rate_limits="" remove_archives="" confirm_text="" extra_subject="" uid=""
  local snapshot_file="" agent_id="" agent_status=""
  local -a session_ids=() request_specs=() rate_subjects=()

  prepare_deployed_context
  if maybe_reexec_with_sudo_for_config enrollment-reset; then
    return 0
  fi
  ensure_deployed_config_exists

  if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    sudo env ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$SELF_PATH" enrollment-reset
    write_operator_checkout_artifact
    return 0
  fi

  target_unix_user="$(ask "Unix user to reset" "${ENROLLMENT_RESET_UNIX_USER:-}")"
  if [[ -z "$target_unix_user" ]]; then
    echo "Unix user is required." >&2
    exit 1
  fi
  if [[ "$target_unix_user" == "$ALMANAC_USER" ]]; then
    echo "Refusing to reset the Almanac service user '$ALMANAC_USER'." >&2
    exit 1
  fi

  snapshot_file="$(mktemp)"
  enrollment_snapshot_json "$target_unix_user" >"$snapshot_file"

  echo "Matched enrollment state:"
  python3 - "$snapshot_file" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)

agent = data.get("agent") or {}
print(f"  unix_user: {data.get('unix_user') or '-'}")
print(f"  agent_id:  {data.get('agent_id') or '-'}")
print(f"  agent:     {(agent.get('status') or 'missing') if agent else 'missing'}")
print(f"  onboarding sessions: {len(data.get('onboarding') or [])}")
for row in data.get("onboarding") or []:
    print(f"    - {row.get('session_id')} state={row.get('state')} platform={row.get('platform')} linked_request={row.get('linked_request_id') or '-'}")
print(f"  auto-provision requests: {len(data.get('requests') or [])}")
for row in data.get("requests") or []:
    print(f"    - {row.get('request_id')} status={row.get('status')} attempts={row.get('provision_attempts')} provisioned_at={row.get('provisioned_at') or '-'}")
subjects = data.get("rate_limit_subjects") or []
print(f"  related rate-limit subjects: {', '.join(subjects) if subjects else '(none)'}")
PY

  remove_unix_user="$(ask_yes_no "Remove the Unix user and its home if present" "${ENROLLMENT_RESET_REMOVE_USER:-1}")"
  purge_rate_limits="$(ask_yes_no "Clear related onboarding/bootstrap rate-limit buckets" "${ENROLLMENT_RESET_PURGE_RATE_LIMITS:-1}")"
  remove_archives="$(ask_yes_no "Remove archived agent state for this user" "${ENROLLMENT_RESET_REMOVE_ARCHIVES:-0}")"
  extra_subject="$(ask "Extra rate-limit subject to clear (optional, e.g. discord:123456789)" "${ENROLLMENT_RESET_EXTRA_SUBJECT:-}")"
  confirm_text="$(ask "Type RESET to confirm enrollment cleanup" "")"
  if [[ "$confirm_text" != "RESET" ]]; then
    rm -f "$snapshot_file"
    echo "Enrollment reset cancelled."
    exit 1
  fi

  mapfile -t session_ids < <(python3 - "$snapshot_file" <<'PY'
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)
for row in data.get("onboarding") or []:
    if row.get("state") not in {"denied", "completed", "cancelled"}:
        print(row.get("session_id", ""))
PY
)
  mapfile -t request_specs < <(python3 - "$snapshot_file" <<'PY'
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)
for row in data.get("requests") or []:
    print("\t".join([
        str(row.get("request_id", "")),
        str(row.get("status", "")),
        str(row.get("provisioned_at", "") or ""),
    ]))
PY
)
  mapfile -t rate_subjects < <(python3 - "$snapshot_file" <<'PY'
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)
for value in data.get("rate_limit_subjects") or []:
    print(value)
PY
)
  agent_id="$(python3 - "$snapshot_file" <<'PY'
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)
print(data.get("agent_id", ""))
PY
)"
  agent_status="$(python3 - "$snapshot_file" <<'PY'
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)
agent = data.get("agent") or {}
print(agent.get("status", ""))
PY
)"

  for request_spec in "${request_specs[@]}"; do
    [[ -n "$request_spec" ]] || continue
    IFS=$'\t' read -r request_id request_status request_provisioned_at <<<"$request_spec"
    if [[ -z "$request_id" ]]; then
      continue
    fi
    if [[ "$request_status" == "approved" && -z "$request_provisioned_at" ]]; then
      env ALMANAC_CONFIG_FILE="$CONFIG_TARGET" \
        "$ALMANAC_REPO_DIR/bin/almanac-ctl" provision cancel "$request_id" \
        --reason "reset via deploy.sh enrollment-reset" >/dev/null 2>&1 || true
    elif [[ "$request_status" == "pending" ]]; then
      run_service_user_cmd "$ALMANAC_REPO_DIR/bin/almanac-ctl" request deny "$request_id" \
        --surface ctl --actor deploy-enrollment-reset >/dev/null 2>&1 || true
    fi
  done

  for session_id in "${session_ids[@]}"; do
    [[ -n "$session_id" ]] || continue
    run_service_user_cmd "$ALMANAC_REPO_DIR/bin/almanac-ctl" onboarding deny "$session_id" \
      --actor deploy-enrollment-reset --reason "reset via deploy.sh enrollment-reset" >/dev/null 2>&1 || true
  done

  if [[ "$agent_status" == "active" || "$agent_status" == "pending" ]]; then
    env ALMANAC_CONFIG_FILE="$CONFIG_TARGET" \
      "$ALMANAC_REPO_DIR/bin/almanac-ctl" agent deenroll "$target_unix_user" \
      --actor deploy-enrollment-reset >/dev/null 2>&1 || true
  fi

  rm -rf "$ALMANAC_AGENTS_STATE_DIR/$agent_id"
  if [[ "$remove_archives" == "1" ]]; then
    rm -rf "$ALMANAC_ARCHIVED_AGENTS_DIR/$agent_id"
  fi
  rm -f "$STATE_DIR/activation-triggers/$agent_id.json"

  for request_spec in "${request_specs[@]}"; do
    [[ -n "$request_spec" ]] || continue
    IFS=$'\t' read -r request_id _ <<<"$request_spec"
    [[ -n "$request_id" ]] || continue
    rm -f "$STATE_DIR/auto-provision/$request_id.log"
  done

  for session_id in "${session_ids[@]}"; do
    [[ -n "$session_id" ]] || continue
    rm -rf "$STATE_DIR/onboarding-secrets/$session_id"
  done

  if [[ -n "$extra_subject" ]]; then
    rate_subjects+=("$extra_subject")
  fi
  if [[ "$purge_rate_limits" == "1" && ${#rate_subjects[@]} -gt 0 ]]; then
    run_root_env_cmd python3 - "$ALMANAC_DB_PATH" "${rate_subjects[@]}" <<'PY'
import sqlite3
import sys

db_path = sys.argv[1]
subjects = sorted({item for item in sys.argv[2:] if item})
if not subjects:
    raise SystemExit(0)

conn = sqlite3.connect(db_path)
conn.executemany("DELETE FROM rate_limits WHERE subject = ?", [(item,) for item in subjects])
conn.commit()
PY
  fi

  if id -u "$target_unix_user" >/dev/null 2>&1 && [[ "$remove_unix_user" == "1" ]]; then
    uid="$(id -u "$target_unix_user")"
    loginctl disable-linger "$target_unix_user" >/dev/null 2>&1 || true
    systemctl stop "user@$uid.service" >/dev/null 2>&1 || true
    pkill -u "$target_unix_user" >/dev/null 2>&1 || true
    userdel -r "$target_unix_user" >/dev/null 2>&1 || userdel "$target_unix_user" >/dev/null 2>&1 || true
  fi

  systemctl start almanac-enrollment-provision.service >/dev/null 2>&1 || true
  rm -f "$snapshot_file"
  echo "Enrollment reset complete for $target_unix_user."
  echo
  run_enrollment_status
}

run_health_check() {
  local uid=""
  local status=""

  load_detected_config || true

  if [[ ${EUID:-$(id -u)} -ne 0 && -n "${DISCOVERED_CONFIG:-}" ]]; then
    status="$(probe_path_status "$DISCOVERED_CONFIG")"
  fi
  if [[ "$status" == "exists-unreadable" ]]; then
    if ! sudo env ALMANAC_CONFIG_FILE="$DISCOVERED_CONFIG" "$SELF_PATH" health; then
      return 1
    fi
    write_operator_checkout_artifact
    return 0
  fi

  if [[ -z "${ALMANAC_USER:-}" ]]; then
    ALMANAC_USER="almanac"
  fi
  if [[ -z "${ALMANAC_HOME:-}" ]]; then
    ALMANAC_HOME="/home/$ALMANAC_USER"
  fi
  if [[ -z "${ALMANAC_REPO_DIR:-}" ]]; then
    ALMANAC_REPO_DIR="$ALMANAC_HOME/almanac"
  fi
  if [[ -z "${ALMANAC_PRIV_DIR:-}" ]]; then
    ALMANAC_PRIV_DIR="$ALMANAC_REPO_DIR/almanac-priv"
  fi

  ALMANAC_PRIV_CONFIG_DIR="${ALMANAC_PRIV_CONFIG_DIR:-$ALMANAC_PRIV_DIR/config}"
  CONFIG_TARGET="${DISCOVERED_CONFIG:-$ALMANAC_PRIV_CONFIG_DIR/almanac.env}"

  if ! id -u "$ALMANAC_USER" >/dev/null 2>&1; then
    echo "Service user '$ALMANAC_USER' does not exist." >&2
    exit 1
  fi

  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    if [[ ! -x "$ALMANAC_REPO_DIR/bin/health.sh" ]]; then
      echo "Health script not found at $ALMANAC_REPO_DIR/bin/health.sh" >&2
      exit 1
    fi
    uid="$(id -u "$ALMANAC_USER")"
    run_as_user_systemd "$ALMANAC_USER" "$uid" "ALMANAC_CONFIG_FILE='$CONFIG_TARGET' '$ALMANAC_REPO_DIR/bin/health.sh'"
    return 0
  fi

  if [[ "$(id -un)" == "$ALMANAC_USER" ]]; then
    if [[ ! -x "$ALMANAC_REPO_DIR/bin/health.sh" ]]; then
      echo "Health script not found at $ALMANAC_REPO_DIR/bin/health.sh" >&2
      exit 1
    fi
    env ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$ALMANAC_REPO_DIR/bin/health.sh"
    return 0
  fi

  uid="$(id -u "$ALMANAC_USER")"
  sudo -iu "$ALMANAC_USER" env \
    XDG_RUNTIME_DIR="/run/user/$uid" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" \
    ALMANAC_CONFIG_FILE="$CONFIG_TARGET" \
    "$ALMANAC_REPO_DIR/bin/health.sh"
  write_operator_checkout_artifact
}

run_curator_setup_flow() {
  prepare_deployed_context

  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    env ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$ALMANAC_REPO_DIR/bin/install-system-services.sh"
    run_as_user "$ALMANAC_USER" "env ALMANAC_CONFIG_FILE='$CONFIG_TARGET' ALMANAC_ALLOW_NO_USER_BUS='${ALMANAC_ALLOW_NO_USER_BUS:-0}' '$ALMANAC_REPO_DIR/bin/install-user-services.sh'"
    run_as_user "$ALMANAC_USER" "env $(curator_bootstrap_env_prefix) '$ALMANAC_REPO_DIR/bin/bootstrap-curator.sh'"
    reload_runtime_config_from_file "$CONFIG_TARGET" || true
    restart_shared_user_services_root
    return 0
  fi

  if [[ "$(id -un)" == "$ALMANAC_USER" ]]; then
    env ALMANAC_CONFIG_FILE="$CONFIG_TARGET" ALMANAC_ALLOW_NO_USER_BUS="${ALMANAC_ALLOW_NO_USER_BUS:-0}" "$ALMANAC_REPO_DIR/bin/install-user-services.sh"
    env $(curator_bootstrap_env_prefix) "$ALMANAC_REPO_DIR/bin/bootstrap-curator.sh"
    reload_runtime_config_from_file "$CONFIG_TARGET" || true
    if set_user_systemd_bus_env; then
      systemctl --user daemon-reload
      systemctl --user restart almanac-mcp.service almanac-notion-webhook.service almanac-qmd-mcp.service almanac-qmd-update.timer almanac-vault-watch.service almanac-github-backup.timer almanac-ssot-batcher.timer almanac-notification-delivery.timer almanac-curator-refresh.timer
      systemctl --user start almanac-curator-refresh.service >/dev/null 2>&1 || true
      if [[ "$PDF_INGEST_ENABLED" == "1" ]]; then
        systemctl --user restart almanac-pdf-ingest.timer
        systemctl --user stop almanac-pdf-ingest-watch.service >/dev/null 2>&1 || true
      fi
      if [[ "$ENABLE_QUARTO" == "1" ]]; then
        systemctl --user restart almanac-quarto-render.timer
      fi
      if [[ "$ENABLE_NEXTCLOUD" == "1" ]]; then
        systemctl --user restart almanac-nextcloud.service
      fi
      if [[ "${ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED:-0}" == "1" ]]; then
        systemctl --user restart almanac-curator-onboarding.service >/dev/null 2>&1 || true
      fi
      if [[ "${ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED:-0}" == "1" ]]; then
        systemctl --user restart almanac-curator-discord-onboarding.service >/dev/null 2>&1 || true
      fi
      if [[ "${ALMANAC_CURATOR_CHANNELS:-tui-only}" == *discord* || "${ALMANAC_CURATOR_CHANNELS:-tui-only}" == *telegram* ]]; then
        systemctl --user restart almanac-curator-gateway.service >/dev/null 2>&1 || true
      fi
    fi
    return 0
  fi

  sudo env \
    ALMANAC_USER="$ALMANAC_USER" \
    ALMANAC_HOME="$ALMANAC_HOME" \
    ALMANAC_REPO_DIR="$ALMANAC_REPO_DIR" \
    ALMANAC_PRIV_DIR="$ALMANAC_PRIV_DIR" \
    ALMANAC_PRIV_CONFIG_DIR="$ALMANAC_PRIV_CONFIG_DIR" \
    ALMANAC_CONFIG_FILE="$CONFIG_TARGET" \
    ALMANAC_ALLOW_NO_USER_BUS="${ALMANAC_ALLOW_NO_USER_BUS:-0}" \
    ALMANAC_CURATOR_SKIP_HERMES_SETUP="${ALMANAC_CURATOR_SKIP_HERMES_SETUP:-}" \
    ALMANAC_CURATOR_SKIP_GATEWAY_SETUP="${ALMANAC_CURATOR_SKIP_GATEWAY_SETUP:-}" \
    ALMANAC_CURATOR_FORCE_HERMES_SETUP="${ALMANAC_CURATOR_FORCE_HERMES_SETUP:-}" \
    ALMANAC_CURATOR_FORCE_GATEWAY_SETUP="${ALMANAC_CURATOR_FORCE_GATEWAY_SETUP:-}" \
    ALMANAC_CURATOR_FORCE_CHANNEL_RECONFIGURE="${ALMANAC_CURATOR_FORCE_CHANNEL_RECONFIGURE:-}" \
    ALMANAC_CURATOR_NOTIFY_PLATFORM="${ALMANAC_CURATOR_NOTIFY_PLATFORM:-}" \
    ALMANAC_CURATOR_NOTIFY_CHANNEL_ID="${ALMANAC_CURATOR_NOTIFY_CHANNEL_ID:-}" \
    ALMANAC_CURATOR_GENERAL_PLATFORM="${ALMANAC_CURATOR_GENERAL_PLATFORM:-}" \
    ALMANAC_CURATOR_GENERAL_CHANNEL_ID="${ALMANAC_CURATOR_GENERAL_CHANNEL_ID:-}" \
    ALMANAC_CURATOR_MODEL_PRESET="${ALMANAC_CURATOR_MODEL_PRESET:-}" \
    ALMANAC_CURATOR_CHANNELS="${ALMANAC_CURATOR_CHANNELS:-}" \
    TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}" \
    "$BOOTSTRAP_DIR/deploy.sh" curator-setup
  write_operator_checkout_artifact
}

run_upgrade_flow() {
  prepare_deployed_context

  if [[ ${EUID:-$(id -u)} -ne 0 && -n "${CONFIG_TARGET:-}" && ! -r "$CONFIG_TARGET" ]]; then
    echo "Switching to sudo to inspect the deployed config..."
    if ! sudo env \
      ALMANAC_CONFIG_FILE="$CONFIG_TARGET" \
      ALMANAC_UPSTREAM_REPO_URL="${ALMANAC_UPSTREAM_REPO_URL:-}" \
      ALMANAC_UPSTREAM_BRANCH="${ALMANAC_UPSTREAM_BRANCH:-}" \
      "$SELF_PATH" --apply-upgrade; then
      return 1
    fi
    write_operator_checkout_artifact
    return 0
  fi

  if [[ ! -f "$CONFIG_TARGET" ]]; then
    echo "Almanac upgrade needs an existing deployed config. Expected: $CONFIG_TARGET" >&2
    echo "Run ./deploy.sh install first, or point ALMANAC_CONFIG_FILE at the deployed almanac.env." >&2
    exit 1
  fi

  echo "Almanac deploy: upgrade from configured upstream"
  echo
  echo "Config:   $CONFIG_TARGET"
  echo "Upstream: ${ALMANAC_UPSTREAM_REPO_URL:-https://github.com/sirouk/almanac.git}#${ALMANAC_UPSTREAM_BRANCH:-main}"
  echo "Target:   $ALMANAC_REPO_DIR"

  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    run_root_upgrade
    return 0
  fi

  echo
  echo "Switching to sudo for upgrade..."
  if ! sudo env \
    ALMANAC_CONFIG_FILE="$CONFIG_TARGET" \
    ALMANAC_UPSTREAM_REPO_URL="${ALMANAC_UPSTREAM_REPO_URL:-}" \
    ALMANAC_UPSTREAM_BRANCH="${ALMANAC_UPSTREAM_BRANCH:-}" \
    "$SELF_PATH" --apply-upgrade; then
    return 1
  fi
  write_operator_checkout_artifact
}

run_agent_payload() {
  load_detected_config || true

  ALMANAC_USER="${ALMANAC_USER:-almanac}"
  ALMANAC_HOME="${ALMANAC_HOME:-/home/$ALMANAC_USER}"
  ALMANAC_REPO_DIR="${ALMANAC_REPO_DIR:-$BOOTSTRAP_DIR}"
  ALMANAC_PRIV_DIR="${ALMANAC_PRIV_DIR:-$ALMANAC_REPO_DIR/almanac-priv}"
  ALMANAC_PRIV_CONFIG_DIR="${ALMANAC_PRIV_CONFIG_DIR:-$ALMANAC_PRIV_DIR/config}"
  STATE_DIR="${STATE_DIR:-$ALMANAC_PRIV_DIR/state}"
  QMD_COLLECTION_NAME="${QMD_COLLECTION_NAME:-vault}"
  QMD_MCP_PORT="${QMD_MCP_PORT:-8181}"
  NEXTCLOUD_TRUSTED_DOMAIN="${NEXTCLOUD_TRUSTED_DOMAIN:-almanac.your-tailnet.ts.net}"
  ENABLE_TAILSCALE_SERVE="${ENABLE_TAILSCALE_SERVE:-0}"
  TAILSCALE_QMD_PATH="${TAILSCALE_QMD_PATH:-/mcp}"
  TAILSCALE_ALMANAC_MCP_PATH="${TAILSCALE_ALMANAC_MCP_PATH:-/almanac-mcp}"

  if [[ -d "$STATE_DIR" && -w "$STATE_DIR" ]]; then
    write_agent_install_payload_file >/dev/null 2>&1 || true
  fi

  print_agent_install_payload
}

run_install_flow() {
  if maybe_reexec_install_for_config_defaults "$MODE"; then
    return 0
  fi

  collect_install_answers

  if [[ "$MODE" == "write-config" ]]; then
    seed_private_repo "$ALMANAC_PRIV_DIR"
    write_runtime_config "$CONFIG_TARGET"
    echo
    echo "Wrote config to: $CONFIG_TARGET"
    echo "Private repo scaffold: $ALMANAC_PRIV_DIR"
    return 0
  fi

  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    run_root_install
    return 0
  fi

  ANSWERS_FILE="$(mktemp /tmp/almanac-install.XXXXXX.env)"
  write_answers_file "$ANSWERS_FILE"
  echo
  echo "Switching to sudo for system setup..."
  if ! sudo env ALMANAC_INSTALL_ANSWERS_FILE="$ANSWERS_FILE" "$SELF_PATH" --apply-install; then
    rm -f "$ANSWERS_FILE"
    return 1
  fi
  rm -f "$ANSWERS_FILE"
  write_operator_checkout_artifact
}

run_remove_flow() {
  collect_remove_answers

  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    run_root_remove
    return 0
  fi

  ANSWERS_FILE="$(mktemp /tmp/almanac-remove.XXXXXX.env)"
  write_answers_file "$ANSWERS_FILE"
  echo
  echo "Switching to sudo for teardown..."
  if ! sudo env ALMANAC_INSTALL_ANSWERS_FILE="$ANSWERS_FILE" "$SELF_PATH" --apply-remove; then
    rm -f "$ANSWERS_FILE"
    return 1
  fi
  rm -f "$ANSWERS_FILE"
}

if [[ -n "$PRIVILEGED_MODE" ]]; then
  case "$PRIVILEGED_MODE" in
    install|remove)
      load_answers
      ;;
    upgrade)
      prepare_deployed_context
      ;;
  esac
  if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    echo "Privileged step must run as root." >&2
    exit 1
  fi

  case "$PRIVILEGED_MODE" in
    install) run_root_install ;;
    upgrade) run_root_upgrade ;;
    remove) run_root_remove ;;
  esac
  exit 0
fi

if [[ -z "$MODE" || "$MODE" == "menu" ]]; then
  choose_mode
fi

case "$MODE" in
  install|write-config)
    run_install_flow
    ;;
  upgrade)
    run_upgrade_flow
    ;;
  enrollment-status)
    run_enrollment_status
    ;;
  enrollment-trace)
    run_enrollment_trace
    ;;
  enrollment-align)
    run_enrollment_align
    ;;
  enrollment-reset)
    run_enrollment_reset
    ;;
  curator-setup)
    run_curator_setup_flow
    ;;
  agent-payload|agent)
    run_agent_payload
    ;;
  remove)
    run_remove_flow
    ;;
  health)
    run_health_check
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
