#!/usr/bin/env bash
set -euo pipefail

BOOTSTRAP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SELF_PATH="$BOOTSTRAP_DIR/bin/deploy.sh"
ANSWERS_FILE="${ALMANAC_INSTALL_ANSWERS_FILE:-}"
MODE=""
PRIVILEGED_MODE=""
DISCOVERED_CONFIG=""
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

usage() {
  cat <<'EOF'
Usage:
  deploy.sh                # interactive menu
  deploy.sh install
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
    install|curator-setup|agent-payload|agent|write-config|remove|health|menu)
      MODE="$1"
      shift
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
  local answer

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
  local answer
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
  local answer

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
  local answer
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

choose_mode() {
  local answer

  cat <<'EOF'
Almanac deploy menu

  1) Install / update
  2) Write config only
  3) Curator setup / repair
  4) Print agent payload
  5) Health check
  6) Remove / teardown
  7) Exit
EOF

  while true; do
    read -r -p "Choose mode [1]: " answer
    case "${answer:-1}" in
      1) MODE="install"; return 0 ;;
      2) MODE="write-config"; return 0 ;;
      3) MODE="curator-setup"; return 0 ;;
      4) MODE="agent-payload"; return 0 ;;
      5) MODE="health"; return 0 ;;
      6) MODE="remove"; return 0 ;;
      7) exit 0 ;;
      *) echo "Please choose 1, 2, 3, 4, 5, 6, or 7." ;;
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

  local ts_json
  ts_json="$(tailscale status --json 2>/dev/null || true)"
  if [[ -z "$ts_json" ]]; then
    return 0
  fi

  local ts_info
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

  local ts_json
  ts_json="$(tailscale serve status --json 2>/dev/null || true)"
  if [[ -z "$ts_json" ]]; then
    return 0
  fi

  local ts_info
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

  local remote_url branch owner_repo
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
  local candidate
  local candidates=(
    "${ALMANAC_CONFIG_FILE:-}"
    "/home/almanac/almanac/almanac-priv/config/almanac.env"
    "$HOME/almanac/almanac-priv/config/almanac.env"
    "$HOME/almanac/almanac/almanac-priv/config/almanac.env"
    "$BOOTSTRAP_DIR/almanac-priv/config/almanac.env"
    "$BOOTSTRAP_DIR/config/almanac.env"
  )

  DISCOVERED_CONFIG=""

  for candidate in "${candidates[@]}"; do
    if [[ -n "$candidate" && -f "$candidate" ]]; then
      DISCOVERED_CONFIG="$candidate"
      return 0
    fi
  done

  candidate="$(find /home -maxdepth 5 -path '*/almanac/almanac-priv/config/almanac.env' -print -quit 2>/dev/null || true)"
  if [[ -n "$candidate" && -f "$candidate" ]]; then
    DISCOVERED_CONFIG="$candidate"
    return 0
  fi

  return 1
}

load_detected_config() {
  if discover_existing_config; then
    # shellcheck disable=SC1090
    source "$DISCOVERED_CONFIG"
    VAULT_QMD_COLLECTION_MASK="$(normalize_vault_qmd_collection_mask "${VAULT_QMD_COLLECTION_MASK:-}")"
    return 0
  fi

  return 1
}

reload_runtime_config_from_file() {
  local config_path="${1:-$CONFIG_TARGET}"

  if [[ -n "$config_path" && -f "$config_path" ]]; then
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

emit_runtime_config() {
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
    write_kv OPERATOR_GENERAL_CHANNEL_PLATFORM "${OPERATOR_GENERAL_CHANNEL_PLATFORM:-}"
    write_kv OPERATOR_GENERAL_CHANNEL_ID "${OPERATOR_GENERAL_CHANNEL_ID:-}"
    write_kv TELEGRAM_BOT_TOKEN "${TELEGRAM_BOT_TOKEN:-}"
    write_kv ALMANAC_MODEL_PRESET_CODEX "${ALMANAC_MODEL_PRESET_CODEX:-openai:codex}"
    write_kv ALMANAC_MODEL_PRESET_OPUS "${ALMANAC_MODEL_PRESET_OPUS:-anthropic:claude-opus}"
    write_kv ALMANAC_MODEL_PRESET_CHUTES "${ALMANAC_MODEL_PRESET_CHUTES:-chutes:auto-failover}"
    write_kv ALMANAC_CURATOR_MODEL_PRESET "${ALMANAC_CURATOR_MODEL_PRESET:-codex}"
    write_kv ALMANAC_CURATOR_CHANNELS "${ALMANAC_CURATOR_CHANNELS:-tui-only}"
    write_kv CHUTES_MCP_URL "${CHUTES_MCP_URL:-}"
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
  local source_dir="$BOOTSTRAP_DIR"
  local target_dir="$ALMANAC_REPO_DIR"
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
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.DS_Store' \
    "$source_dir/" "$target_dir/"
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
  local uid runtime_dir bus_path
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

  local key
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
  local i

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
  echo "    - first contact must resolve YAML .vault defaults, auto-subscribe every default_subscribed vault, and trigger the initial Curator refresh"
  echo "    - install exactly one 4h refresh timer/service for the user agent"
  echo "  memory_contract:"
  echo "    - maintain only [managed:vault-ref], [managed:qmd-ref], [managed:vault-topology]"
  echo "    - write or refresh those stubs now; MEMORY.md is a frozen snapshot at session start"
  echo "    - make [managed:qmd-ref] explicit: qmd first for private/shared-vault questions or follow-ups from the current discussion; use mixed lex+vec retrieval"
  if [[ "$PDF_INGEST_ENABLED" == "1" ]]; then
    echo "    - include \"$PDF_INGEST_COLLECTION_NAME\" when present, especially for newly uploaded PDFs"
  fi
  echo "    - do not store note bodies, PDF bodies, or large dumps in built-in memory"
  echo "    - do not rely on background memory review or session-end flush"
  echo "    - if cron lacks the native memory tool, patch only those three entries in \$HERMES_HOME/memories/MEMORY.md and preserve unrelated entries plus Hermes § delimiters"
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
  local target

  target="${1:-$(agent_install_payload_path)}"
  mkdir -p "$(dirname "$target")"
  render_agent_install_payload_body >"$target"
  printf '%s\n' "$target"
}

print_agent_install_payload() {
  local payload_path

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
  local default_user default_home default_domain default_repo default_priv
  local default_nextcloud_port default_git_name default_git_email
  local default_enable_nextcloud default_enable_quarto default_enable_private_git
  local default_seed_vault default_install_public_git
  local detected_user detected_home detected_repo detected_priv
  local detected_git_name detected_git_email use_almanac_user
  local default_nextcloud_admin_user nextcloud_admin_password_input
  local default_enable_tailscale_serve
  local default_tailscale_operator_user
  local default_pdf_vision_endpoint
  local default_pdf_vision_model
  local default_pdf_vision_api_key

  load_detected_config || true

  echo "Almanac deploy: install / update"
  echo

  detected_user="${ALMANAC_USER:-}"
  detected_home="${ALMANAC_HOME:-}"
  detected_repo="${ALMANAC_REPO_DIR:-}"
  detected_priv="${ALMANAC_PRIV_DIR:-}"
  detected_git_name="${BACKUP_GIT_AUTHOR_NAME:-}"
  detected_git_email="${BACKUP_GIT_AUTHOR_EMAIL:-}"
  use_almanac_user="$(ask_yes_no "Use 'almanac' as the service user" "1")"

  if [[ "$use_almanac_user" == "1" ]]; then
    ALMANAC_USER="almanac"
  else
    if [[ -n "$detected_user" && "$detected_user" != "almanac" ]]; then
      echo "Detected existing configured user: $detected_user"
    fi

    while true; do
      default_user="${detected_user:-}"
      ALMANAC_USER="$(ask "Service user" "$default_user")"
      if [[ -n "$ALMANAC_USER" ]]; then
        break
      fi
      echo "Service user cannot be blank."
    done
  fi

  if [[ -n "$detected_home" && "$detected_user" == "$ALMANAC_USER" ]]; then
    default_home="$detected_home"
  else
    default_home="/home/$ALMANAC_USER"
  fi

  if [[ -n "$detected_repo" && "$detected_user" == "$ALMANAC_USER" ]]; then
    default_repo="$detected_repo"
  else
    default_repo="$default_home/almanac"
  fi

  if [[ -n "$detected_priv" && "$detected_user" == "$ALMANAC_USER" ]]; then
    default_priv="$detected_priv"
  else
    default_priv="$default_repo/almanac-priv"
  fi

  default_nextcloud_port="${NEXTCLOUD_PORT:-18080}"
  default_git_name="${detected_git_name:-Almanac Backup}"
  if [[ -n "$detected_git_email" && "$detected_user" == "$ALMANAC_USER" ]]; then
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
  QMD_INDEX_NAME="almanac"
  QMD_COLLECTION_NAME="vault"
  QMD_RUN_EMBED="1"
  QMD_MCP_PORT="${QMD_MCP_PORT:-8181}"
  BACKUP_GIT_BRANCH="${BACKUP_GIT_BRANCH:-main}"
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
    nextcloud_admin_password_input="$(ask_secret "Nextcloud admin password (leave blank to keep current)")"
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
  local default_user default_home default_repo default_priv
  local default_remove_user default_remove_tooling
  local confirm_text
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
  QMD_INDEX_NAME="${QMD_INDEX_NAME:-almanac}"
  QMD_COLLECTION_NAME="${QMD_COLLECTION_NAME:-vault}"
  QMD_RUN_EMBED="${QMD_RUN_EMBED:-1}"
  QMD_MCP_PORT="${QMD_MCP_PORT:-8181}"
  BACKUP_GIT_BRANCH="${BACKUP_GIT_BRANCH:-main}"
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

restart_shared_user_services_root() {
  local uid

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
  export ALMANAC_NAME ALMANAC_USER ALMANAC_HOME ALMANAC_REPO_DIR ALMANAC_PRIV_DIR
  export ALMANAC_PRIV_CONFIG_DIR VAULT_DIR STATE_DIR NEXTCLOUD_STATE_DIR RUNTIME_DIR
  export ALMANAC_DB_PATH ALMANAC_AGENTS_STATE_DIR ALMANAC_CURATOR_DIR ALMANAC_CURATOR_MANIFEST ALMANAC_CURATOR_HERMES_HOME ALMANAC_ARCHIVED_AGENTS_DIR
  export PUBLISHED_DIR QMD_INDEX_NAME QMD_COLLECTION_NAME VAULT_QMD_COLLECTION_MASK BACKUP_GIT_BRANCH BACKUP_GIT_REMOTE
  export PDF_INGEST_COLLECTION_NAME PDF_INGEST_ENABLED PDF_INGEST_EXTRACTOR
  export PDF_VISION_ENDPOINT PDF_VISION_MODEL PDF_VISION_API_KEY PDF_VISION_MAX_PAGES
  export VAULT_WATCH_DEBOUNCE_SECONDS VAULT_WATCH_RUN_EMBED
  export QMD_RUN_EMBED QMD_MCP_PORT ALMANAC_MCP_HOST ALMANAC_MCP_PORT ALMANAC_NOTION_WEBHOOK_HOST ALMANAC_NOTION_WEBHOOK_PORT
  export ALMANAC_BOOTSTRAP_WINDOW_SECONDS ALMANAC_BOOTSTRAP_PER_IP_LIMIT ALMANAC_BOOTSTRAP_GLOBAL_PENDING_LIMIT ALMANAC_BOOTSTRAP_PENDING_TTL_SECONDS
  export BACKUP_GIT_AUTHOR_NAME BACKUP_GIT_AUTHOR_EMAIL NEXTCLOUD_PORT NEXTCLOUD_TRUSTED_DOMAIN
  export POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD
  export NEXTCLOUD_ADMIN_USER NEXTCLOUD_ADMIN_PASSWORD NEXTCLOUD_VAULT_MOUNT_POINT
  export OPERATOR_NOTIFY_CHANNEL_PLATFORM OPERATOR_NOTIFY_CHANNEL_ID OPERATOR_GENERAL_CHANNEL_PLATFORM OPERATOR_GENERAL_CHANNEL_ID
  export ALMANAC_MODEL_PRESET_CODEX ALMANAC_MODEL_PRESET_OPUS ALMANAC_MODEL_PRESET_CHUTES ALMANAC_CURATOR_MODEL_PRESET ALMANAC_CURATOR_CHANNELS CHUTES_MCP_URL
  export ENABLE_NEXTCLOUD ENABLE_TAILSCALE_SERVE TAILSCALE_OPERATOR_USER TAILSCALE_QMD_PATH TAILSCALE_ALMANAC_MCP_PATH ENABLE_PRIVATE_GIT ENABLE_QUARTO SEED_SAMPLE_VAULT
  export QUARTO_PROJECT_DIR QUARTO_OUTPUT_DIR

  "$BOOTSTRAP_DIR/bin/bootstrap-system.sh"
  sync_public_repo
  seed_private_repo "$ALMANAC_PRIV_DIR"
  write_runtime_config "$CONFIG_TARGET"
  chown -R "$ALMANAC_USER:$ALMANAC_USER" "$ALMANAC_REPO_DIR" "$ALMANAC_PRIV_DIR"
  wipe_nextcloud_state_if_requested

  init_public_repo_if_needed

  run_as_user "$ALMANAC_USER" "env ALMANAC_CONFIG_FILE='$CONFIG_TARGET' '$ALMANAC_REPO_DIR/bin/bootstrap-userland.sh'"
  run_as_user "$ALMANAC_USER" "env ALMANAC_CONFIG_FILE='$CONFIG_TARGET' ALMANAC_ALLOW_NO_USER_BUS='${ALMANAC_ALLOW_NO_USER_BUS:-0}' '$ALMANAC_REPO_DIR/bin/install-user-services.sh'"
  run_as_user "$ALMANAC_USER" "env $(curator_bootstrap_env_prefix) '$ALMANAC_REPO_DIR/bin/bootstrap-curator.sh'"
  reload_runtime_config_from_file "$CONFIG_TARGET" || true

  local uid
  restart_shared_user_services_root
  uid="$(id -u "$ALMANAC_USER")"

  if [[ "$ENABLE_NEXTCLOUD" == "1" && "$ENABLE_TAILSCALE_SERVE" == "1" ]]; then
    if [[ -n "${TAILSCALE_OPERATOR_USER:-}" ]] && command -v tailscale >/dev/null 2>&1; then
      tailscale set --operator="$TAILSCALE_OPERATOR_USER" >/dev/null 2>&1 || true
    fi
    ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$BOOTSTRAP_DIR/bin/tailscale-nextcloud-serve.sh"
  fi

  wait_for_port 127.0.0.1 "$QMD_MCP_PORT" 20 1
  wait_for_port 127.0.0.1 "$ALMANAC_MCP_PORT" 20 1
  wait_for_port 127.0.0.1 "$ALMANAC_NOTION_WEBHOOK_PORT" 20 1
  if [[ "$ENABLE_NEXTCLOUD" == "1" ]]; then
    wait_for_port 127.0.0.1 "$NEXTCLOUD_PORT" 45 2
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
  agent_payload_file="$(write_agent_install_payload_file || true)"
  if [[ -n "$agent_payload_file" && -f "$agent_payload_file" ]]; then
    chown "$ALMANAC_USER:$ALMANAC_USER" "$agent_payload_file" >/dev/null 2>&1 || true
  fi
  print_post_install_guide
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
      run_as_user_systemd "$ALMANAC_USER" "$uid" "ALMANAC_CONFIG_FILE='$CONFIG_TARGET' systemctl --user disable --now almanac-nextcloud.service almanac-qmd-mcp.service almanac-qmd-update.timer almanac-vault-watch.service almanac-pdf-ingest.timer almanac-pdf-ingest-watch.service almanac-github-backup.timer almanac-quarto-render.timer almanac-mcp.service almanac-notion-webhook.service almanac-ssot-batcher.timer almanac-notification-delivery.timer almanac-curator-refresh.timer almanac-curator-gateway.service >/dev/null 2>&1 || true" || true
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

run_health_check() {
  local uid

  load_detected_config || true

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
}

run_curator_setup_flow() {
  load_detected_config || true

  ALMANAC_USER="${ALMANAC_USER:-almanac}"
  ALMANAC_HOME="${ALMANAC_HOME:-/home/$ALMANAC_USER}"
  ALMANAC_REPO_DIR="${ALMANAC_REPO_DIR:-$ALMANAC_HOME/almanac}"
  ALMANAC_PRIV_DIR="${ALMANAC_PRIV_DIR:-$ALMANAC_REPO_DIR/almanac-priv}"
  ALMANAC_PRIV_CONFIG_DIR="${ALMANAC_PRIV_CONFIG_DIR:-$ALMANAC_PRIV_DIR/config}"
  CONFIG_TARGET="${DISCOVERED_CONFIG:-$ALMANAC_PRIV_CONFIG_DIR/almanac.env}"

  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
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
  load_answers
  if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    echo "Privileged step must run as root." >&2
    exit 1
  fi

  case "$PRIVILEGED_MODE" in
    install) run_root_install ;;
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
