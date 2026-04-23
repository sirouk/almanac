#!/usr/bin/env bash
set -euo pipefail

BOOTSTRAP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ALMANAC_OPERATOR_ARTIFACT_FILE="${ALMANAC_OPERATOR_ARTIFACT_FILE:-$BOOTSTRAP_DIR/.almanac-operator.env}"

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

host_uname_s() {
  uname -s 2>/dev/null || printf '%s\n' "unknown"
}

default_home_for_user() {
  local user="${1:-}"

  if [[ -z "$user" ]]; then
    return 1
  fi

  if [[ "$(host_uname_s)" == "Darwin" ]]; then
    printf '/Users/%s\n' "$user"
    return 0
  fi

  printf '/home/%s\n' "$user"
}

lowercase() {
  printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]'
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

resolve_home_dir() {
  local home_dir="${HOME:-}"
  if [[ -n "$home_dir" ]]; then
    printf '%s\n' "$home_dir"
    return 0
  fi

  if command_exists python3; then
    home_dir="$(
      python3 - <<'PY'
import os
import pwd
import sys

try:
    print(pwd.getpwuid(os.getuid()).pw_dir)
except Exception:
    raise SystemExit(1)
PY
    )" || home_dir=""
  fi
  if [[ -z "$home_dir" ]] && command_exists getent; then
    home_dir="$(getent passwd "$(id -u)" 2>/dev/null | cut -d: -f6)"
  fi
  if [[ -n "$home_dir" ]]; then
    printf '%s\n' "$home_dir"
    return 0
  fi

  return 1
}

resolve_user_home() {
  local user="${1:-}"
  local home_dir=""

  if [[ -z "$user" ]]; then
    return 1
  fi

  if command_exists python3; then
    home_dir="$(
      python3 - "$user" <<'PY'
import pwd
import sys

user = sys.argv[1]
try:
    print(pwd.getpwnam(user).pw_dir)
except KeyError:
    raise SystemExit(1)
PY
    )" || home_dir=""
  fi
  if [[ -z "$home_dir" ]] && command_exists dscl; then
    home_dir="$(dscl . -read "/Users/$user" NFSHomeDirectory 2>/dev/null | awk 'NR==1 {print $2}')"
  fi
  if [[ -z "$home_dir" ]] && command_exists getent; then
    home_dir="$(getent passwd "$user" 2>/dev/null | cut -d: -f6)"
  fi
  if [[ -z "$home_dir" ]]; then
    home_dir="$(default_home_for_user "$user")"
  fi

  printf '%s\n' "$home_dir"
}

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

find_config_file() {
  local -a artifact_hints=()
  local nested_priv=""
  local sibling_priv=""
  local explicit_config=""
  local artifact_user="" artifact_repo="" artifact_priv="" artifact_config="" artifact_home=""
  local home_dir=""
  local line=""
  nested_priv="$BOOTSTRAP_DIR/almanac-priv/config/almanac.env"
  sibling_priv="$(cd "$BOOTSTRAP_DIR/.." && pwd)/almanac-priv/config/almanac.env"
  home_dir="$(resolve_home_dir || true)"

  explicit_config="${ALMANAC_CONFIG_FILE:-}"
  if [[ -n "$explicit_config" ]]; then
    echo "$explicit_config"
    return 0
  fi

  while IFS= read -r line; do
    artifact_hints+=("$line")
  done < <(read_operator_artifact_hints || true)
  artifact_user="${artifact_hints[0]:-}"
  artifact_repo="${artifact_hints[1]:-}"
  artifact_priv="${artifact_hints[2]:-}"
  artifact_config="${artifact_hints[3]:-}"
  artifact_home="$(resolve_user_home "$artifact_user" || true)"

  local -a candidates=()
  if [[ -n "$artifact_config" ]]; then
    candidates+=("$artifact_config")
  fi
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
  if [[ -n "$artifact_home" ]]; then
    candidates+=(
      "$artifact_home/almanac/almanac-priv/config/almanac.env"
      "$artifact_home/almanac-priv/config/almanac.env"
    )
  fi

  candidates+=(
    "$BOOTSTRAP_DIR/config/almanac.env"
    "$nested_priv"
    "$sibling_priv"
  )
  if [[ -n "$home_dir" ]]; then
    candidates+=(
      "$home_dir/almanac/almanac-priv/config/almanac.env"
      "$home_dir/almanac-priv/config/almanac.env"
    )
  fi
  local candidate=""
  for candidate in "${candidates[@]}"; do
    if [[ -n "$candidate" && -f "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

CONFIG_FILE="$(find_config_file || true)"

if [[ -n "${CONFIG_FILE:-}" && -f "$CONFIG_FILE" && -r "$CONFIG_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$CONFIG_FILE"
fi

ALMANAC_NAME="${ALMANAC_NAME:-almanac}"
ALMANAC_USER="${ALMANAC_USER:-$(id -un)}"
ALMANAC_REPO_DIR="${ALMANAC_REPO_DIR:-$BOOTSTRAP_DIR}"
ALMANAC_HOME="${ALMANAC_HOME:-$(cd "$ALMANAC_REPO_DIR/.." && pwd)}"
ALMANAC_PRIV_DIR="${ALMANAC_PRIV_DIR:-$ALMANAC_REPO_DIR/almanac-priv}"
ALMANAC_PRIV_CONFIG_DIR="${ALMANAC_PRIV_CONFIG_DIR:-$ALMANAC_PRIV_DIR/config}"
VAULT_DIR="${VAULT_DIR:-$ALMANAC_PRIV_DIR/vault}"
STATE_DIR="${STATE_DIR:-$ALMANAC_PRIV_DIR/state}"
NEXTCLOUD_STATE_DIR="${NEXTCLOUD_STATE_DIR:-$STATE_DIR/nextcloud}"
PDF_INGEST_DIR="${PDF_INGEST_DIR:-$STATE_DIR/pdf-ingest}"
PDF_INGEST_MARKDOWN_DIR="${PDF_INGEST_MARKDOWN_DIR:-$PDF_INGEST_DIR/markdown}"
PDF_INGEST_STATUS_FILE="${PDF_INGEST_STATUS_FILE:-$PDF_INGEST_DIR/status.json}"
PDF_INGEST_MANIFEST_DB="${PDF_INGEST_MANIFEST_DB:-$PDF_INGEST_DIR/manifest.sqlite3}"
PDF_INGEST_LOCK_FILE="${PDF_INGEST_LOCK_FILE:-$PDF_INGEST_DIR/ingest.lock}"
QMD_REFRESH_LOCK_FILE="${QMD_REFRESH_LOCK_FILE:-$STATE_DIR/qmd-refresh.lock}"
RUNTIME_DIR="${RUNTIME_DIR:-$STATE_DIR/runtime}"
PUBLISHED_DIR="${PUBLISHED_DIR:-$ALMANAC_PRIV_DIR/published}"
ALMANAC_DB_PATH="${ALMANAC_DB_PATH:-$STATE_DIR/almanac-control.sqlite3}"
ALMANAC_AGENTS_STATE_DIR="${ALMANAC_AGENTS_STATE_DIR:-$STATE_DIR/agents}"
ALMANAC_CURATOR_DIR="${ALMANAC_CURATOR_DIR:-$STATE_DIR/curator}"
ALMANAC_CURATOR_MANIFEST="${ALMANAC_CURATOR_MANIFEST:-$ALMANAC_CURATOR_DIR/manifest.json}"
ALMANAC_CURATOR_HERMES_HOME="${ALMANAC_CURATOR_HERMES_HOME:-$ALMANAC_CURATOR_DIR/hermes-home}"
ALMANAC_ARCHIVED_AGENTS_DIR="${ALMANAC_ARCHIVED_AGENTS_DIR:-$STATE_DIR/archived-agents}"
ALMANAC_RELEASE_STATE_FILE="${ALMANAC_RELEASE_STATE_FILE:-$STATE_DIR/almanac-release.json}"
ALMANAC_NOTION_INDEX_DIR="${ALMANAC_NOTION_INDEX_DIR:-$STATE_DIR/notion-index}"
ALMANAC_NOTION_INDEX_MARKDOWN_DIR="${ALMANAC_NOTION_INDEX_MARKDOWN_DIR:-$ALMANAC_NOTION_INDEX_DIR/markdown}"
QMD_INDEX_NAME="${QMD_INDEX_NAME:-almanac}"
QMD_COLLECTION_NAME="${QMD_COLLECTION_NAME:-vault}"
PDF_INGEST_COLLECTION_NAME="${PDF_INGEST_COLLECTION_NAME:-vault-pdf-ingest}"
ALMANAC_NOTION_INDEX_COLLECTION_NAME="${ALMANAC_NOTION_INDEX_COLLECTION_NAME:-notion-shared}"
ALMANAC_NOTION_INDEX_ROOTS="${ALMANAC_NOTION_INDEX_ROOTS:-}"
ALMANAC_NOTION_INDEX_RUN_EMBED="${ALMANAC_NOTION_INDEX_RUN_EMBED:-1}"
VAULT_QMD_COLLECTION_MASK="${VAULT_QMD_COLLECTION_MASK:-**/*.{md,markdown,mdx,txt,text}}"
VAULT_QMD_COLLECTION_MASK="$(normalize_vault_qmd_collection_mask "$VAULT_QMD_COLLECTION_MASK")"
QMD_RUN_EMBED="${QMD_RUN_EMBED:-1}"
QMD_MCP_PORT="${QMD_MCP_PORT:-8181}"
ALMANAC_MCP_HOST="${ALMANAC_MCP_HOST:-127.0.0.1}"
ALMANAC_MCP_PORT="${ALMANAC_MCP_PORT:-8282}"
ALMANAC_MCP_URL="${ALMANAC_MCP_URL:-http://${ALMANAC_MCP_HOST}:${ALMANAC_MCP_PORT}/mcp}"
ALMANAC_NOTION_WEBHOOK_HOST="${ALMANAC_NOTION_WEBHOOK_HOST:-127.0.0.1}"
ALMANAC_NOTION_WEBHOOK_PORT="${ALMANAC_NOTION_WEBHOOK_PORT:-8283}"
ALMANAC_NOTION_WEBHOOK_PUBLIC_URL="${ALMANAC_NOTION_WEBHOOK_PUBLIC_URL:-}"
ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL="${ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL:-0}"
TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT="${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-8443}"
TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH="${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH:-/notion/webhook}"
ALMANAC_SSOT_NOTION_ROOT_PAGE_URL="${ALMANAC_SSOT_NOTION_ROOT_PAGE_URL:-}"
ALMANAC_SSOT_NOTION_ROOT_PAGE_ID="${ALMANAC_SSOT_NOTION_ROOT_PAGE_ID:-}"
ALMANAC_SSOT_NOTION_SPACE_URL="${ALMANAC_SSOT_NOTION_SPACE_URL:-}"
ALMANAC_SSOT_NOTION_SPACE_ID="${ALMANAC_SSOT_NOTION_SPACE_ID:-}"
ALMANAC_SSOT_NOTION_SPACE_KIND="${ALMANAC_SSOT_NOTION_SPACE_KIND:-}"
ALMANAC_SSOT_NOTION_API_VERSION="${ALMANAC_SSOT_NOTION_API_VERSION:-2026-03-11}"
ALMANAC_SSOT_NOTION_TOKEN="${ALMANAC_SSOT_NOTION_TOKEN:-}"
ALMANAC_ORG_NAME="${ALMANAC_ORG_NAME:-}"
ALMANAC_ORG_MISSION="${ALMANAC_ORG_MISSION:-}"
ALMANAC_ORG_PRIMARY_PROJECT="${ALMANAC_ORG_PRIMARY_PROJECT:-}"
ALMANAC_ORG_TIMEZONE="${ALMANAC_ORG_TIMEZONE:-Etc/UTC}"
ALMANAC_ORG_QUIET_HOURS="${ALMANAC_ORG_QUIET_HOURS:-}"
ALMANAC_BOOTSTRAP_WINDOW_SECONDS="${ALMANAC_BOOTSTRAP_WINDOW_SECONDS:-3600}"
ALMANAC_BOOTSTRAP_PER_IP_LIMIT="${ALMANAC_BOOTSTRAP_PER_IP_LIMIT:-5}"
ALMANAC_BOOTSTRAP_GLOBAL_PENDING_LIMIT="${ALMANAC_BOOTSTRAP_GLOBAL_PENDING_LIMIT:-20}"
ALMANAC_BOOTSTRAP_PENDING_TTL_SECONDS="${ALMANAC_BOOTSTRAP_PENDING_TTL_SECONDS:-900}"
ALMANAC_AUTO_PROVISION_MAX_ATTEMPTS="${ALMANAC_AUTO_PROVISION_MAX_ATTEMPTS:-5}"
ALMANAC_AUTO_PROVISION_RETRY_BASE_SECONDS="${ALMANAC_AUTO_PROVISION_RETRY_BASE_SECONDS:-60}"
ALMANAC_AUTO_PROVISION_RETRY_MAX_SECONDS="${ALMANAC_AUTO_PROVISION_RETRY_MAX_SECONDS:-900}"
PDF_INGEST_ENABLED="${PDF_INGEST_ENABLED:-1}"
PDF_INGEST_EXTRACTOR="${PDF_INGEST_EXTRACTOR:-auto}"
PDF_INGEST_TRIGGER_QMD_REFRESH="${PDF_INGEST_TRIGGER_QMD_REFRESH:-1}"
PDF_INGEST_WATCH_DEBOUNCE_SECONDS="${PDF_INGEST_WATCH_DEBOUNCE_SECONDS:-10}"
PDF_INGEST_DOCLING_FORCE_OCR="${PDF_INGEST_DOCLING_FORCE_OCR:-0}"
PDF_VISION_ENDPOINT="${PDF_VISION_ENDPOINT:-}"
PDF_VISION_MODEL="${PDF_VISION_MODEL:-}"
PDF_VISION_API_KEY="${PDF_VISION_API_KEY:-}"
PDF_VISION_MAX_PAGES="${PDF_VISION_MAX_PAGES:-6}"
VAULT_WATCH_DEBOUNCE_SECONDS="${VAULT_WATCH_DEBOUNCE_SECONDS:-5}"
VAULT_WATCH_RUN_EMBED="${VAULT_WATCH_RUN_EMBED:-auto}"
QUARTO_PROJECT_DIR="${QUARTO_PROJECT_DIR:-$ALMANAC_PRIV_DIR/quarto}"
QUARTO_OUTPUT_DIR="${QUARTO_OUTPUT_DIR:-$PUBLISHED_DIR}"
BACKUP_GIT_BRANCH="${BACKUP_GIT_BRANCH:-main}"
BACKUP_GIT_REMOTE="${BACKUP_GIT_REMOTE:-}"
BACKUP_GIT_DEPLOY_KEY_PATH="${BACKUP_GIT_DEPLOY_KEY_PATH:-$ALMANAC_HOME/.ssh/almanac-backup-ed25519}"
BACKUP_GIT_KNOWN_HOSTS_FILE="${BACKUP_GIT_KNOWN_HOSTS_FILE:-$ALMANAC_HOME/.ssh/almanac-backup-known_hosts}"

resolve_runtime_python() {
  local python_bin="${RUNTIME_DIR:-}/hermes-venv/bin/python3"
  if [[ -n "$python_bin" && -x "$python_bin" ]]; then
    printf '%s\n' "$python_bin"
    return 0
  fi
  command -v python3
}

require_runtime_python() {
  local python_bin="${RUNTIME_DIR:-}/hermes-venv/bin/python3"
  if [[ -n "$python_bin" && -x "$python_bin" ]]; then
    printf '%s\n' "$python_bin"
    return 0
  fi
  echo "Managed Almanac runtime python is missing at $python_bin. Run bootstrap-userland first." >&2
  return 1
}

runtime_python_realpath() {
  local python_bin="${1:-${RUNTIME_DIR:-}/hermes-venv/bin/python3}"
  python3 - "$python_bin" <<'PY'
import os
import sys

path = sys.argv[1]
if not path:
    raise SystemExit(1)
print(os.path.realpath(path))
PY
}

shared_runtime_python_is_share_safe() {
  local venv_dir="${1:-${RUNTIME_DIR:-}/hermes-venv}"
  local python_bin="$venv_dir/bin/python3"
  local resolved=""
  local home_dir=""

  if [[ ! -x "$python_bin" ]]; then
    return 1
  fi

  resolved="$(runtime_python_realpath "$python_bin" 2>/dev/null || true)"
  if [[ -z "$resolved" ]]; then
    return 1
  fi
  home_dir="$(resolve_home_dir || true)"

  case "$resolved" in
    "$venv_dir"/*|/usr/*|/bin/*|/usr/local/*|/opt/*)
      return 0
      ;;
    "$home_dir"/.local/share/uv/python/*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

python_supports_hermes_runtime() {
  local python_bin="${1:-}"
  if [[ -z "$python_bin" || ! -x "$python_bin" ]]; then
    return 1
  fi
  "$python_bin" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
}

runtime_python_has_pip() {
  local python_bin="${1:-}"
  if [[ -z "$python_bin" || ! -x "$python_bin" ]]; then
    return 1
  fi
  "$python_bin" -m pip --version >/dev/null 2>&1
}

resolve_shared_runtime_seed_python() {
  local candidate=""

  if command -v uv >/dev/null 2>&1; then
    candidate="$(uv python find 3.12 2>/dev/null || true)"
    if python_supports_hermes_runtime "$candidate"; then
      printf '%s\n' "$candidate"
      return 0
    fi
    candidate="$(uv python find 3.11 2>/dev/null || true)"
    if python_supports_hermes_runtime "$candidate"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  fi

  for candidate in /usr/bin/python3.12 /usr/bin/python3.11; do
    if python_supports_hermes_runtime "$candidate"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  for candidate in "$(command -v python3.12 2>/dev/null || true)" "$(command -v python3.11 2>/dev/null || true)" "$(command -v python3 2>/dev/null || true)"; do
    if python_supports_hermes_runtime "$candidate"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  return 1
}

resolve_runtime_hermes() {
  local hermes_bin="${RUNTIME_DIR:-}/hermes-venv/bin/hermes"
  if [[ -n "$hermes_bin" && -x "$hermes_bin" ]]; then
    printf '%s\n' "$hermes_bin"
    return 0
  fi
  command -v hermes
}

require_runtime_hermes() {
  local hermes_bin="${RUNTIME_DIR:-}/hermes-venv/bin/hermes"
  if [[ -n "$hermes_bin" && -x "$hermes_bin" ]]; then
    printf '%s\n' "$hermes_bin"
    return 0
  fi
  echo "Managed Almanac runtime hermes is missing at $hermes_bin. Run bootstrap-userland first." >&2
  return 1
}
BACKUP_GIT_AUTHOR_NAME="${BACKUP_GIT_AUTHOR_NAME:-Almanac Backup}"
BACKUP_GIT_AUTHOR_EMAIL="${BACKUP_GIT_AUTHOR_EMAIL:-almanac@localhost}"
NEXTCLOUD_PORT="${NEXTCLOUD_PORT:-18080}"
NEXTCLOUD_TRUSTED_DOMAIN="${NEXTCLOUD_TRUSTED_DOMAIN:-almanac.your-tailnet.ts.net}"
POSTGRES_DB="${POSTGRES_DB:-${MARIADB_DATABASE:-nextcloud}}"
POSTGRES_USER="${POSTGRES_USER:-${MARIADB_USER:-nextcloud}}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-${MARIADB_PASSWORD:-}}"
NEXTCLOUD_ADMIN_USER="${NEXTCLOUD_ADMIN_USER:-}"
NEXTCLOUD_ADMIN_PASSWORD="${NEXTCLOUD_ADMIN_PASSWORD:-}"
ENABLE_NEXTCLOUD="${ENABLE_NEXTCLOUD:-1}"
ENABLE_TAILSCALE_SERVE="${ENABLE_TAILSCALE_SERVE:-0}"
TAILSCALE_SERVE_PORT="${TAILSCALE_SERVE_PORT:-443}"
TAILSCALE_OPERATOR_USER="${TAILSCALE_OPERATOR_USER:-}"
ENABLE_PRIVATE_GIT="${ENABLE_PRIVATE_GIT:-1}"
ENABLE_QUARTO="${ENABLE_QUARTO:-1}"
SEED_SAMPLE_VAULT="${SEED_SAMPLE_VAULT:-1}"
NEXTCLOUD_DB_DIR="${NEXTCLOUD_DB_DIR:-$NEXTCLOUD_STATE_DIR/db}"
NEXTCLOUD_REDIS_DIR="${NEXTCLOUD_REDIS_DIR:-$NEXTCLOUD_STATE_DIR/redis}"
NEXTCLOUD_HTML_DIR="${NEXTCLOUD_HTML_DIR:-$NEXTCLOUD_STATE_DIR/html}"
NEXTCLOUD_DATA_DIR="${NEXTCLOUD_DATA_DIR:-$NEXTCLOUD_STATE_DIR/data}"
NEXTCLOUD_CUSTOM_CONFIG_DIR="${NEXTCLOUD_CUSTOM_CONFIG_DIR:-$NEXTCLOUD_STATE_DIR/config}"
NEXTCLOUD_EMPTY_SKELETON_DIR="${NEXTCLOUD_EMPTY_SKELETON_DIR:-$NEXTCLOUD_STATE_DIR/empty-skeleton}"
NEXTCLOUD_ALMANAC_CONFIG_FILE="${NEXTCLOUD_ALMANAC_CONFIG_FILE:-$NEXTCLOUD_CUSTOM_CONFIG_DIR/almanac.config.php}"
NEXTCLOUD_HOOKS_DIR="${NEXTCLOUD_HOOKS_DIR:-$NEXTCLOUD_STATE_DIR/hooks}"
NEXTCLOUD_PRE_INSTALL_HOOK_DIR="${NEXTCLOUD_PRE_INSTALL_HOOK_DIR:-$NEXTCLOUD_HOOKS_DIR/pre-installation}"
NEXTCLOUD_POST_INSTALL_HOOK_DIR="${NEXTCLOUD_POST_INSTALL_HOOK_DIR:-$NEXTCLOUD_HOOKS_DIR/post-installation}"
NEXTCLOUD_BEFORE_STARTING_HOOK_DIR="${NEXTCLOUD_BEFORE_STARTING_HOOK_DIR:-$NEXTCLOUD_HOOKS_DIR/before-starting}"
NEXTCLOUD_PRE_INSTALL_HOOK_FILE="${NEXTCLOUD_PRE_INSTALL_HOOK_FILE:-$NEXTCLOUD_PRE_INSTALL_HOOK_DIR/20-almanac-config.sh}"
NEXTCLOUD_POST_INSTALL_HOOK_FILE="${NEXTCLOUD_POST_INSTALL_HOOK_FILE:-$NEXTCLOUD_POST_INSTALL_HOOK_DIR/20-almanac-clean-admin-files.sh}"
NEXTCLOUD_BEFORE_STARTING_HOOK_FILE="${NEXTCLOUD_BEFORE_STARTING_HOOK_FILE:-$NEXTCLOUD_BEFORE_STARTING_HOOK_DIR/20-almanac-config.sh}"
NEXTCLOUD_VAULT_MOUNT_POINT="${NEXTCLOUD_VAULT_MOUNT_POINT:-/Vault}"
NEXTCLOUD_VAULT_CONTAINER_PATH="${NEXTCLOUD_VAULT_CONTAINER_PATH:-/srv/vault}"
TAILSCALE_QMD_PATH="${TAILSCALE_QMD_PATH:-/mcp}"
TAILSCALE_ALMANAC_MCP_PATH="${TAILSCALE_ALMANAC_MCP_PATH:-/almanac-mcp}"
ALMANAC_PRIV_TEMPLATE_DIR="${ALMANAC_PRIV_TEMPLATE_DIR:-$BOOTSTRAP_DIR/templates/almanac-priv}"
OPERATOR_NOTIFY_CHANNEL_PLATFORM="${OPERATOR_NOTIFY_CHANNEL_PLATFORM:-tui-only}"
OPERATOR_NOTIFY_CHANNEL_ID="${OPERATOR_NOTIFY_CHANNEL_ID:-}"
ALMANAC_OPERATOR_TELEGRAM_USER_IDS="${ALMANAC_OPERATOR_TELEGRAM_USER_IDS:-}"
ALMANAC_CURATOR_CHANNELS="${ALMANAC_CURATOR_CHANNELS:-tui-only}"
if [[ -z "${ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED:-}" ]]; then
  if [[ ",${ALMANAC_CURATOR_CHANNELS}," == *",telegram,"* || "${OPERATOR_NOTIFY_CHANNEL_PLATFORM:-}" == "telegram" ]]; then
    ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED="1"
  else
    ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED="0"
  fi
fi
if [[ -z "${ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED:-}" ]]; then
  if [[ ",${ALMANAC_CURATOR_CHANNELS}," == *",discord,"* ]]; then
    ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED="1"
  else
    ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED="0"
  fi
fi
ALMANAC_ONBOARDING_WINDOW_SECONDS="${ALMANAC_ONBOARDING_WINDOW_SECONDS:-3600}"
ALMANAC_ONBOARDING_PER_USER_LIMIT="${ALMANAC_ONBOARDING_PER_USER_LIMIT:-${ALMANAC_ONBOARDING_PER_TELEGRAM_USER_LIMIT:-3}}"
ALMANAC_ONBOARDING_PER_TELEGRAM_USER_LIMIT="${ALMANAC_ONBOARDING_PER_TELEGRAM_USER_LIMIT:-$ALMANAC_ONBOARDING_PER_USER_LIMIT}"
ALMANAC_ONBOARDING_GLOBAL_PENDING_LIMIT="${ALMANAC_ONBOARDING_GLOBAL_PENDING_LIMIT:-20}"
ALMANAC_ONBOARDING_UPDATE_FAILURE_LIMIT="${ALMANAC_ONBOARDING_UPDATE_FAILURE_LIMIT:-3}"
OPERATOR_GENERAL_CHANNEL_PLATFORM="${OPERATOR_GENERAL_CHANNEL_PLATFORM:-}"
OPERATOR_GENERAL_CHANNEL_ID="${OPERATOR_GENERAL_CHANNEL_ID:-}"
ALMANAC_MODEL_PRESET_CODEX="${ALMANAC_MODEL_PRESET_CODEX:-openai:codex}"
ALMANAC_MODEL_PRESET_OPUS="${ALMANAC_MODEL_PRESET_OPUS:-anthropic:claude-opus}"
ALMANAC_MODEL_PRESET_CHUTES="${ALMANAC_MODEL_PRESET_CHUTES:-chutes:auto-failover}"
CHUTES_MCP_URL="${CHUTES_MCP_URL:-}"
ALMANAC_UPSTREAM_REPO_URL="${ALMANAC_UPSTREAM_REPO_URL:-https://github.com/sirouk/almanac.git}"
ALMANAC_UPSTREAM_BRANCH="${ALMANAC_UPSTREAM_BRANCH:-main}"
# Hermes upstream pin: vetted against the live shared runtime and Jeef smoke.
ALMANAC_HERMES_AGENT_REF="${ALMANAC_HERMES_AGENT_REF:-ce089169d578b96c82641f17186ba63c288b22d8}"
ALMANAC_AGENT_DASHBOARD_BACKEND_PORT_BASE="${ALMANAC_AGENT_DASHBOARD_BACKEND_PORT_BASE:-19000}"
ALMANAC_AGENT_DASHBOARD_PROXY_PORT_BASE="${ALMANAC_AGENT_DASHBOARD_PROXY_PORT_BASE:-29000}"
ALMANAC_AGENT_CODE_PORT_BASE="${ALMANAC_AGENT_CODE_PORT_BASE:-39000}"
ALMANAC_AGENT_PORT_SLOT_SPAN="${ALMANAC_AGENT_PORT_SLOT_SPAN:-5000}"
ALMANAC_AGENT_CODE_SERVER_IMAGE="${ALMANAC_AGENT_CODE_SERVER_IMAGE:-docker.io/codercom/code-server:4.116.0}"
ALMANAC_AGENT_ENABLE_TAILSCALE_SERVE="${ALMANAC_AGENT_ENABLE_TAILSCALE_SERVE:-$ENABLE_TAILSCALE_SERVE}"

qmd_normalize_index_name() {
  local index_name="${1:-index}"

  if [[ "$index_name" == *"/"* ]]; then
    python3 - "$index_name" <<'PY'
import os
import sys

name = sys.argv[1]
absolute = os.path.abspath(name)
normalized = absolute.replace("/", "_").lstrip("_")
print(normalized)
PY
    return 0
  fi

  printf '%s\n' "$index_name"
}

qmd_cache_dir() {
  local home_dir=""
  if [[ -n "${XDG_CACHE_HOME:-}" ]]; then
    printf '%s/qmd\n' "$XDG_CACHE_HOME"
  else
    home_dir="$(resolve_home_dir || true)"
    if [[ -n "$home_dir" ]]; then
      printf '%s/.cache/qmd\n' "$home_dir"
    else
      printf '%s\n' "/tmp/qmd-cache"
    fi
  fi
}

qmd_db_path() {
  local normalized_name=""
  normalized_name="$(qmd_normalize_index_name "${1:-$QMD_INDEX_NAME}")"
  printf '%s/%s.sqlite\n' "$(qmd_cache_dir)" "$normalized_name"
}

QMD_INDEX_DB_PATH="${QMD_INDEX_DB_PATH:-$(qmd_db_path "$QMD_INDEX_NAME")}"
export QMD_INDEX_DB_PATH

# qmd 2.1.0's HTTP MCP server ignores the named index when resolving the
# SQLite database path and falls back to the default "index.sqlite". Pinning
# INDEX_PATH keeps the CLI/update path and the MCP daemon on the same DB.
INDEX_PATH="${INDEX_PATH:-$QMD_INDEX_DB_PATH}"
export INDEX_PATH

resolve_pdf_ingest_backend() {
  ensure_uv

  case "$PDF_INGEST_EXTRACTOR" in
    auto)
      if command -v docling >/dev/null 2>&1; then
        echo "docling"
        return 0
      fi
      if command -v pdftotext >/dev/null 2>&1; then
        echo "pdftotext"
        return 0
      fi
      return 1
      ;;
    docling|pdftotext)
      if command -v "$PDF_INGEST_EXTRACTOR" >/dev/null 2>&1; then
        echo "$PDF_INGEST_EXTRACTOR"
        return 0
      fi
      return 1
      ;;
    none|disabled)
      echo "disabled"
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

have_pdf_ingest_backend() {
  resolve_pdf_ingest_backend >/dev/null 2>&1
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

have_pdf_vision_backend() {
  [[ -n "${PDF_VISION_ENDPOINT:-}" ]] &&
    [[ -n "${PDF_VISION_MODEL:-}" ]] &&
    [[ -n "${PDF_VISION_API_KEY:-}" ]] &&
    command -v pdftoppm >/dev/null 2>&1
}

have_pdf_vision_partial_config() {
  [[ -n "${PDF_VISION_ENDPOINT:-}" || -n "${PDF_VISION_MODEL:-}" || -n "${PDF_VISION_API_KEY:-}" ]]
}

env_file_value() {
  local path="$1"
  local key="$2"

  python3 - "$path" "$key" <<'PY'
import shlex
import sys
from pathlib import Path

path = Path(sys.argv[1])
key = sys.argv[2]

try:
    text = path.read_text(encoding="utf-8")
except OSError:
    raise SystemExit(0)

for raw_line in text.splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    name, raw_value = line.split("=", 1)
    if name.strip() != key:
        continue
    raw_value = raw_value.strip()
    try:
        parsed = shlex.split(raw_value, posix=True)
    except ValueError:
        parsed = []
    if parsed:
        print(parsed[0])
    else:
        print(raw_value.strip("'\""))
    raise SystemExit(0)
PY
}

has_curator_gateway_channels() {
  [[ ",${ALMANAC_CURATOR_CHANNELS:-tui-only}," == *",discord,"* || ",${ALMANAC_CURATOR_CHANNELS:-tui-only}," == *",telegram,"* ]]
}

has_curator_non_onboarding_gateway_channels() {
  local raw_channels="${ALMANAC_CURATOR_CHANNELS:-tui-only}"
  local channel=""
  local channels=()

  IFS=',' read -r -a channels <<<"$raw_channels"
  for channel in "${channels[@]}"; do
    channel="${channel//[[:space:]]/}"
    [[ -z "$channel" || "$channel" == "tui-only" ]] && continue
    if [[ "$channel" == "telegram" && "${ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED:-0}" == "1" ]]; then
      continue
    fi
    if [[ "$channel" == "discord" && "${ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED:-0}" == "1" ]]; then
      continue
    fi
    return 0
  done
  return 1
}

has_curator_non_telegram_gateway_channels() {
  has_curator_non_onboarding_gateway_channels
}

has_curator_telegram_onboarding() {
  [[ "${ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED:-0}" == "1" ]]
}

has_curator_discord_onboarding() {
  [[ "${ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED:-0}" == "1" ]]
}

has_curator_onboarding() {
  has_curator_telegram_onboarding || has_curator_discord_onboarding
}

resolve_hermes_agent_ref_commit() {
  local repo_dir="$1"
  local ref="${2:-$ALMANAC_HERMES_AGENT_REF}"
  local candidate=""
  local resolved=""

  if [[ -z "$repo_dir" || -z "$ref" ]]; then
    return 1
  fi

  for candidate in \
    "$ref" \
    "refs/tags/$ref" \
    "refs/remotes/origin/$ref" \
    "origin/$ref"; do
    resolved="$(git -C "$repo_dir" rev-parse --verify --quiet "${candidate}^{commit}" 2>/dev/null || true)"
    if [[ -n "$resolved" ]]; then
      printf '%s\n' "$resolved"
      return 0
    fi
  done

  return 1
}

ensure_hermes_agent_checkout() {
  local repo_dir="$1"
  local remote_url="https://github.com/NousResearch/hermes-agent.git"
  local ref="${ALMANAC_HERMES_AGENT_REF:-}"
  local current_remote=""
  local is_shallow="false"
  local resolved_commit=""
  local current_commit=""
  local head_ref=""

  if [[ -z "$ref" ]]; then
    echo "ALMANAC_HERMES_AGENT_REF must not be empty." >&2
    return 1
  fi

  if [[ -e "$repo_dir" && ! -d "$repo_dir/.git" ]]; then
    echo "Managed Hermes source directory at $repo_dir is not a git checkout; recreating it." >&2
    rm -rf "$repo_dir"
  fi

  if [[ ! -d "$repo_dir/.git" ]]; then
    git clone "$remote_url" "$repo_dir"
  else
    current_remote="$(git -C "$repo_dir" remote get-url origin 2>/dev/null || true)"
    if [[ -z "$current_remote" ]]; then
      git -C "$repo_dir" remote add origin "$remote_url"
    elif [[ "$current_remote" != "$remote_url" ]]; then
      git -C "$repo_dir" remote set-url origin "$remote_url"
    fi
  fi

  is_shallow="$(git -C "$repo_dir" rev-parse --is-shallow-repository 2>/dev/null || printf '%s\n' "false")"
  if [[ "$is_shallow" == "true" ]]; then
    git -C "$repo_dir" fetch --tags --force --unshallow origin
  else
    git -C "$repo_dir" fetch --tags --force origin
  fi

  resolved_commit="$(resolve_hermes_agent_ref_commit "$repo_dir" "$ref" || true)"
  if [[ -z "$resolved_commit" ]]; then
    git -C "$repo_dir" fetch --tags --force origin "$ref"
    resolved_commit="$(resolve_hermes_agent_ref_commit "$repo_dir" "$ref" || true)"
  fi
  if [[ -z "$resolved_commit" ]]; then
    echo "Could not resolve Hermes ref '$ref' from $remote_url." >&2
    return 1
  fi

  current_commit="$(git -C "$repo_dir" rev-parse HEAD 2>/dev/null || true)"
  head_ref="$(git -C "$repo_dir" symbolic-ref -q HEAD 2>/dev/null || true)"
  if [[ "$current_commit" != "$resolved_commit" || -n "$head_ref" ]]; then
    git -C "$repo_dir" checkout --force --detach "$resolved_commit"
  fi
}

ensure_shared_hermes_runtime() {
  ensure_uv
  local repo_dir="$RUNTIME_DIR/hermes-agent-src"
  local venv_dir="$RUNTIME_DIR/hermes-venv"
  local seed_python=""
  local rebuild_runtime="0"

  if ! command -v uv >/dev/null 2>&1; then
    echo "uv is required to manage the shared Hermes runtime." >&2
    return 1
  fi

  ensure_hermes_agent_checkout "$repo_dir"

  if [[ ! -x "$venv_dir/bin/hermes" ]]; then
    rebuild_runtime="1"
  elif ! shared_runtime_python_is_share_safe "$venv_dir"; then
    rebuild_runtime="1"
    echo "Rebuilding shared Hermes runtime with a system Python so enrolled users can execute it." >&2
  elif ! runtime_python_has_pip "$venv_dir/bin/python3"; then
    rebuild_runtime="1"
    echo "Rebuilding shared Hermes runtime with pip seeded so Hermes setup can install optional dependencies." >&2
  fi

  if [[ "$rebuild_runtime" == "1" ]]; then
    seed_python="$(resolve_shared_runtime_seed_python || true)"
    if [[ -z "$seed_python" ]]; then
      echo "A system-accessible python3 is required to build the shared Hermes runtime." >&2
      return 1
    fi
    rm -rf "$venv_dir"
    uv venv "$venv_dir" --python "$seed_python" --seed
  fi

  uv pip install --python "$venv_dir/bin/python3" --reinstall "$repo_dir[cli,mcp,messaging,cron,web]"
  ensure_hermes_dashboard_assets "$repo_dir"
  sync_hermes_dashboard_assets_into_runtime "$repo_dir" "$venv_dir/bin/python3"
}

ensure_hermes_dashboard_assets() {
  local repo_dir="$1"
  local web_dir="$repo_dir/web"
  local dist_dir="$repo_dir/hermes_cli/web_dist"
  local dist_index="$dist_dir/index.html"
  local stamp_file="$dist_dir/.almanac-build-stamp"
  local current_rev=""

  if [[ ! -d "$web_dir" ]]; then
    echo "Hermes web source is missing at $web_dir" >&2
    return 1
  fi

  current_rev="$(git -C "$repo_dir" rev-parse HEAD 2>/dev/null || true)"
  if [[ -f "$dist_index" && -n "$current_rev" && -f "$stamp_file" && "$(cat "$stamp_file" 2>/dev/null || true)" == "$current_rev" ]]; then
    return 0
  fi

  ensure_nvm
  if ! command -v npm >/dev/null 2>&1; then
    echo "npm is required to build Hermes dashboard assets." >&2
    return 1
  fi

  (cd "$web_dir" && npm ci --no-audit --no-fund && npm run build)
  mkdir -p "$dist_dir"
  if [[ -n "$current_rev" ]]; then
    printf '%s\n' "$current_rev" >"$stamp_file"
  fi
}

sync_hermes_dashboard_assets_into_runtime() {
  local repo_dir="$1"
  local python_bin="$2"
  local source_dir="$repo_dir/hermes_cli/web_dist"
  local target_parent=""
  local target_dir=""

  if [[ ! -d "$source_dir" ]]; then
    echo "Hermes dashboard assets are missing at $source_dir" >&2
    return 1
  fi

  target_parent="$("$python_bin" - <<'PY'
from pathlib import Path
import hermes_cli

print(Path(hermes_cli.__file__).resolve().parent)
PY
)"
  if [[ -z "$target_parent" ]]; then
    echo "Could not resolve installed hermes_cli package path." >&2
    return 1
  fi

  target_dir="$target_parent/web_dist"
  if [[ "$target_dir" == "$source_dir" ]]; then
    return 0
  fi

  rm -rf "$target_dir"
  cp -a "$source_dir" "$target_dir"
}

ensure_qmd_collection() {
  local collection_name="$1"
  local collection_path="$2"
  local collection_mask="${3:-**/*.md}"
  ensure_nvm
  local collection_info="" existing_path="" existing_mask=""

  if collection_info="$(qmd --index "$QMD_INDEX_NAME" collection show "$collection_name" 2>/dev/null)"; then
    existing_path="$(printf '%s\n' "$collection_info" | awk -F': *' '/Path:/{print $2; exit}')"
    existing_mask="$(printf '%s\n' "$collection_info" | awk -F': *' '/Pattern:/{print $2; exit}')"
    if [[ "$existing_path" != "$collection_path" || "$existing_mask" != "$collection_mask" ]]; then
      qmd --index "$QMD_INDEX_NAME" collection remove "$collection_name" || true
      qmd --index "$QMD_INDEX_NAME" collection add "$collection_path" --name "$collection_name" --mask "$collection_mask"
    fi
  else
    qmd --index "$QMD_INDEX_NAME" collection add "$collection_path" --name "$collection_name" --mask "$collection_mask"
  fi
}

vault_source_file_count() {
  local target_dir="${1:-$VAULT_DIR}"

  if [[ ! -d "$target_dir" ]]; then
    printf '0\n'
    return 0
  fi

  find "$target_dir" -type f \
    \( -iname '*.md' -o -iname '*.markdown' -o -iname '*.mdx' -o -iname '*.txt' -o -iname '*.text' \) \
    2>/dev/null | wc -l | tr -d ' '
}

pdf_ingest_markdown_file_count() {
  local target_dir="${1:-$PDF_INGEST_MARKDOWN_DIR}"

  if [[ ! -d "$target_dir" ]]; then
    printf '0\n'
    return 0
  fi

  find "$target_dir" -type f -iname '*.md' 2>/dev/null | wc -l | tr -d ' '
}

qmd_pending_embeddings_count() {
  ensure_nvm
  qmd --index "$QMD_INDEX_NAME" status 2>/dev/null | python3 - <<'PY'
import re
import sys

text = sys.stdin.read()
match = re.search(r"Pending:\s+(\d+)\s+need embedding", text)
print(match.group(1) if match else "0")
PY
}

configure_qmd_collections() {
  ensure_qmd_collection "$QMD_COLLECTION_NAME" "$VAULT_DIR" "$VAULT_QMD_COLLECTION_MASK"
  ensure_qmd_collection "$ALMANAC_NOTION_INDEX_COLLECTION_NAME" "$ALMANAC_NOTION_INDEX_MARKDOWN_DIR" "**/*.md"

  if [[ "$PDF_INGEST_ENABLED" == "1" ]]; then
    ensure_qmd_collection "$PDF_INGEST_COLLECTION_NAME" "$PDF_INGEST_MARKDOWN_DIR" "**/*.md"
  elif qmd --index "$QMD_INDEX_NAME" collection show "$PDF_INGEST_COLLECTION_NAME" >/dev/null 2>&1; then
    qmd --index "$QMD_INDEX_NAME" collection remove "$PDF_INGEST_COLLECTION_NAME" || true
  fi
}

using_repo_local_scaffold_defaults() {
  [[ -z "${CONFIG_FILE:-}" && "$ALMANAC_PRIV_DIR" == "$BOOTSTRAP_DIR/almanac-priv" && -d "$ALMANAC_PRIV_DIR" ]]
}

require_real_layout() {
  local action="${1:-this command}"

  if [[ "${ALMANAC_ALLOW_SCAFFOLD_DEFAULTS:-0}" == "1" ]]; then
    return 0
  fi

  if using_repo_local_scaffold_defaults && [[ ! -f "$ALMANAC_PRIV_DIR/config/almanac.env" ]]; then
    cat >&2 <<EOF
No almanac.env was found, and this checkout is falling back to the repo-local scaffold:
  $ALMANAC_PRIV_DIR

Refusing to run $action against the scaffold default.

Provide ALMANAC_CONFIG_FILE pointing at the deployed config, or set
ALMANAC_ALLOW_SCAFFOLD_DEFAULTS=1 if you intentionally want to use the
repo-local scaffold.
EOF
    return 1
  fi

  return 0
}

nextcloud_pod_name() {
  printf '%s-nextcloud' "$ALMANAC_NAME"
}

nextcloud_db_container_name() {
  printf '%s-db' "$(nextcloud_pod_name)"
}

nextcloud_redis_container_name() {
  printf '%s-redis' "$(nextcloud_pod_name)"
}

nextcloud_app_container_name() {
  printf '%s-app' "$(nextcloud_pod_name)"
}

ensure_nvm() {
  local home_dir=""
  home_dir="$(resolve_home_dir || true)"
  if [[ -z "${NVM_DIR:-}" && -n "$home_dir" ]]; then
    export NVM_DIR="$home_dir/.nvm"
  fi
  if [[ -z "${NVM_DIR:-}" ]]; then
    return 0
  fi
  if [[ -s "$NVM_DIR/nvm.sh" ]]; then
    # shellcheck disable=SC1090
    source "$NVM_DIR/nvm.sh"
  fi
}

ensure_uv() {
  local home_dir=""
  home_dir="$(resolve_home_dir || true)"
  if [[ -n "$home_dir" ]]; then
    export PATH="$home_dir/.local/bin:$PATH"
  fi
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

have_compose_runtime() {
  ensure_uv

  if command -v podman-compose >/dev/null 2>&1; then
    return 0
  fi

  if command -v podman >/dev/null 2>&1 && podman compose version >/dev/null 2>&1; then
    return 0
  fi

  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    return 0
  fi

  return 1
}

compose_runtime_label() {
  ensure_uv

  if command -v podman-compose >/dev/null 2>&1; then
    echo "podman-compose"
    return 0
  fi

  if command -v podman >/dev/null 2>&1 && podman compose version >/dev/null 2>&1; then
    echo "podman compose"
    return 0
  fi

  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    echo "docker compose"
    return 0
  fi

  return 1
}

backup_git_remote_uses_ssh() {
  local remote="${1:-$BACKUP_GIT_REMOTE}"

  case "$remote" in
    git@*:*|ssh://*)
      return 0
      ;;
  esac

  return 1
}

backup_git_remote_host() {
  local remote="${1:-$BACKUP_GIT_REMOTE}"
  local host=""

  case "$remote" in
    git@*:* )
      host="${remote#git@}"
      host="${host%%:*}"
      ;;
    ssh://* )
      host="${remote#ssh://}"
      host="${host#*@}"
      host="${host%%/*}"
      host="${host%%:*}"
      ;;
    * )
      return 1
      ;;
  esac

  if [[ -z "$host" ]]; then
    return 1
  fi

  printf '%s\n' "$host"
}

ensure_backup_git_known_hosts() {
  local remote="${1:-$BACKUP_GIT_REMOTE}"
  local host=""

  if ! backup_git_remote_uses_ssh "$remote"; then
    return 0
  fi

  host="$(backup_git_remote_host "$remote" || true)"
  if [[ -z "$host" ]]; then
    echo "Could not determine the SSH host for BACKUP_GIT_REMOTE=$remote" >&2
    return 1
  fi

  if ! command -v ssh-keyscan >/dev/null 2>&1; then
    echo "ssh-keyscan is required to prepare backup Git SSH host keys." >&2
    return 1
  fi

  mkdir -p "$(dirname "$BACKUP_GIT_KNOWN_HOSTS_FILE")"
  touch "$BACKUP_GIT_KNOWN_HOSTS_FILE"
  chmod 600 "$BACKUP_GIT_KNOWN_HOSTS_FILE"

  if command -v ssh-keygen >/dev/null 2>&1 && \
    ssh-keygen -F "$host" -f "$BACKUP_GIT_KNOWN_HOSTS_FILE" >/dev/null 2>&1; then
    return 0
  fi

  ssh-keyscan -H "$host" >>"$BACKUP_GIT_KNOWN_HOSTS_FILE" 2>/dev/null
}

prepare_backup_git_transport() {
  local remote="${1:-$BACKUP_GIT_REMOTE}"

  unset GIT_SSH_COMMAND

  if [[ -z "$remote" ]]; then
    return 0
  fi

  if ! backup_git_remote_uses_ssh "$remote"; then
    return 0
  fi

  if [[ ! -f "$BACKUP_GIT_DEPLOY_KEY_PATH" ]]; then
    echo "Backup deploy key missing at $BACKUP_GIT_DEPLOY_KEY_PATH. Run ./deploy.sh install or upgrade again to regenerate it." >&2
    return 1
  fi

  ensure_backup_git_known_hosts "$remote"
  chmod 600 "$BACKUP_GIT_DEPLOY_KEY_PATH" >/dev/null 2>&1 || true
  if [[ -f "${BACKUP_GIT_DEPLOY_KEY_PATH}.pub" ]]; then
    chmod 644 "${BACKUP_GIT_DEPLOY_KEY_PATH}.pub" >/dev/null 2>&1 || true
  fi

  export GIT_SSH_COMMAND="ssh -i \"$BACKUP_GIT_DEPLOY_KEY_PATH\" -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=\"$BACKUP_GIT_KNOWN_HOSTS_FILE\""
}

ensure_backup_git_origin_remote() {
  local repo_dir="$1"
  local remote="${2:-$BACKUP_GIT_REMOTE}"

  if [[ -z "$remote" ]]; then
    return 0
  fi

  if git -C "$repo_dir" remote get-url origin >/dev/null 2>&1; then
    git -C "$repo_dir" remote set-url origin "$remote"
  else
    git -C "$repo_dir" remote add origin "$remote"
  fi
}

path_is_within_dir() {
  local path="$1"
  local parent="$2"

  python3 - "$path" "$parent" <<'PY'
import os
import sys

path = os.path.realpath(sys.argv[1])
parent = os.path.realpath(sys.argv[2])
try:
    common = os.path.commonpath([path, parent])
except ValueError:
    raise SystemExit(1)
raise SystemExit(0 if common == parent else 1)
PY
}

path_relative_to_dir() {
  local path="$1"
  local parent="$2"

  python3 - "$path" "$parent" <<'PY'
import os
import sys

path = os.path.realpath(sys.argv[1])
parent = os.path.realpath(sys.argv[2])
print(os.path.relpath(path, parent))
PY
}

run_compose() {
  local compose_file="$1"
  shift

  ensure_uv

  if command -v podman-compose >/dev/null 2>&1; then
    podman-compose -f "$compose_file" "$@"
    return 0
  fi

  if command -v podman >/dev/null 2>&1 && podman compose version >/dev/null 2>&1; then
    podman compose -f "$compose_file" "$@"
    return 0
  fi

  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    docker compose -f "$compose_file" "$@"
    return 0
  fi

  echo "No compose runtime found. Install podman + podman-compose or docker compose."
  return 1
}

with_nextcloud_compose_env() {
  (
    export NEXTCLOUD_PORT NEXTCLOUD_TRUSTED_DOMAIN
    export POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD
    export NEXTCLOUD_ADMIN_USER NEXTCLOUD_ADMIN_PASSWORD
    export NEXTCLOUD_DB_DIR NEXTCLOUD_REDIS_DIR NEXTCLOUD_HTML_DIR NEXTCLOUD_DATA_DIR
    export NEXTCLOUD_CUSTOM_CONFIG_DIR NEXTCLOUD_EMPTY_SKELETON_DIR NEXTCLOUD_ALMANAC_CONFIG_FILE
    export NEXTCLOUD_HOOKS_DIR NEXTCLOUD_PRE_INSTALL_HOOK_DIR NEXTCLOUD_POST_INSTALL_HOOK_DIR NEXTCLOUD_BEFORE_STARTING_HOOK_DIR
    export NEXTCLOUD_PRE_INSTALL_HOOK_FILE NEXTCLOUD_POST_INSTALL_HOOK_FILE NEXTCLOUD_BEFORE_STARTING_HOOK_FILE VAULT_DIR
    "$@"
  )
}

ensure_layout() {
  local qmd_db_dir=""

  qmd_db_dir="$(dirname "$QMD_INDEX_DB_PATH")"

  mkdir -p \
    "$ALMANAC_PRIV_DIR" \
    "$ALMANAC_PRIV_CONFIG_DIR" \
    "$VAULT_DIR" \
    "$STATE_DIR" \
    "$NEXTCLOUD_STATE_DIR" \
    "$PDF_INGEST_DIR" \
    "$PDF_INGEST_MARKDOWN_DIR" \
    "$ALMANAC_NOTION_INDEX_DIR" \
    "$ALMANAC_NOTION_INDEX_MARKDOWN_DIR" \
    "$RUNTIME_DIR" \
    "$ALMANAC_AGENTS_STATE_DIR" \
    "$ALMANAC_CURATOR_DIR" \
    "$ALMANAC_CURATOR_HERMES_HOME" \
    "$ALMANAC_ARCHIVED_AGENTS_DIR" \
    "$PUBLISHED_DIR" \
    "$QUARTO_PROJECT_DIR" \
    "$NEXTCLOUD_DB_DIR" \
    "$NEXTCLOUD_REDIS_DIR" \
    "$NEXTCLOUD_HTML_DIR" \
    "$NEXTCLOUD_DATA_DIR" \
    "$NEXTCLOUD_CUSTOM_CONFIG_DIR" \
    "$NEXTCLOUD_EMPTY_SKELETON_DIR" \
    "$NEXTCLOUD_PRE_INSTALL_HOOK_DIR" \
    "$NEXTCLOUD_POST_INSTALL_HOOK_DIR" \
    "$NEXTCLOUD_BEFORE_STARTING_HOOK_DIR" \
    "$(dirname "$ALMANAC_DB_PATH")" \
    "$qmd_db_dir"
}
