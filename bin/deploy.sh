#!/usr/bin/env bash
set -euo pipefail

BOOTSTRAP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SELF_PATH="$BOOTSTRAP_DIR/bin/deploy.sh"
ANSWERS_FILE="${ALMANAC_INSTALL_ANSWERS_FILE:-}"
MODE=""
PRIVILEGED_MODE=""
DOCKER_DEPLOY_COMMAND=""
DOCKER_DEPLOY_ARGS=()
DISCOVERED_CONFIG=""
ALMANAC_REEXEC_ATTEMPTED=0
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
TAILSCALE_SERVE_PORT="${TAILSCALE_SERVE_PORT:-443}"
ALMANAC_INSTALL_PODMAN="${ALMANAC_INSTALL_PODMAN:-auto}"
ALMANAC_INSTALL_TAILSCALE="${ALMANAC_INSTALL_TAILSCALE:-auto}"
TAILSCALE_OPERATOR_USER="${TAILSCALE_OPERATOR_USER:-}"
TAILSCALE_QMD_PATH="${TAILSCALE_QMD_PATH:-/mcp}"
TAILSCALE_ALMANAC_MCP_PATH="${TAILSCALE_ALMANAC_MCP_PATH:-/almanac-mcp}"
ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL="${ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL:-0}"
TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT="${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-8443}"
TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH="${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH:-/notion/webhook}"
VAULT_WATCH_DEBOUNCE_SECONDS="${VAULT_WATCH_DEBOUNCE_SECONDS:-0.5}"
VAULT_WATCH_MAX_BATCH_SECONDS="${VAULT_WATCH_MAX_BATCH_SECONDS:-10}"
VAULT_WATCH_RUN_EMBED="${VAULT_WATCH_RUN_EMBED:-auto}"
ENABLE_PRIVATE_GIT="${ENABLE_PRIVATE_GIT:-1}"
ENABLE_QUARTO="${ENABLE_QUARTO:-1}"
SEED_SAMPLE_VAULT="${SEED_SAMPLE_VAULT:-1}"
BACKUP_GIT_REMOTE="${BACKUP_GIT_REMOTE:-}"
BACKUP_GIT_DEPLOY_KEY_PATH="${BACKUP_GIT_DEPLOY_KEY_PATH:-}"
BACKUP_GIT_KNOWN_HOSTS_FILE="${BACKUP_GIT_KNOWN_HOSTS_FILE:-}"
ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED="${ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED:-0}"
ALMANAC_UPSTREAM_DEPLOY_KEY_USER="${ALMANAC_UPSTREAM_DEPLOY_KEY_USER:-}"
ALMANAC_UPSTREAM_DEPLOY_KEY_PATH="${ALMANAC_UPSTREAM_DEPLOY_KEY_PATH:-}"
ALMANAC_UPSTREAM_KNOWN_HOSTS_FILE="${ALMANAC_UPSTREAM_KNOWN_HOSTS_FILE:-}"
ALMANAC_MCP_HOST="${ALMANAC_MCP_HOST:-127.0.0.1}"
ALMANAC_MCP_PORT="${ALMANAC_MCP_PORT:-8282}"
ALMANAC_NOTION_WEBHOOK_HOST="${ALMANAC_NOTION_WEBHOOK_HOST:-127.0.0.1}"
ALMANAC_NOTION_WEBHOOK_PORT="${ALMANAC_NOTION_WEBHOOK_PORT:-8283}"
ALMANAC_NOTION_WEBHOOK_PUBLIC_URL="${ALMANAC_NOTION_WEBHOOK_PUBLIC_URL:-}"
ALMANAC_SSOT_NOTION_ROOT_PAGE_URL="${ALMANAC_SSOT_NOTION_ROOT_PAGE_URL:-}"
ALMANAC_SSOT_NOTION_ROOT_PAGE_ID="${ALMANAC_SSOT_NOTION_ROOT_PAGE_ID:-}"
ALMANAC_SSOT_NOTION_SPACE_URL="${ALMANAC_SSOT_NOTION_SPACE_URL:-}"
ALMANAC_SSOT_NOTION_SPACE_ID="${ALMANAC_SSOT_NOTION_SPACE_ID:-}"
ALMANAC_SSOT_NOTION_SPACE_KIND="${ALMANAC_SSOT_NOTION_SPACE_KIND:-}"
ALMANAC_SSOT_NOTION_API_VERSION="${ALMANAC_SSOT_NOTION_API_VERSION:-2026-03-11}"
ALMANAC_SSOT_NOTION_TOKEN="${ALMANAC_SSOT_NOTION_TOKEN:-}"
ALMANAC_NOTION_INDEX_ROOTS="${ALMANAC_NOTION_INDEX_ROOTS:-}"
ALMANAC_NOTION_INDEX_RUN_EMBED="${ALMANAC_NOTION_INDEX_RUN_EMBED:-1}"
ALMANAC_ORG_NAME="${ALMANAC_ORG_NAME:-}"
ALMANAC_ORG_MISSION="${ALMANAC_ORG_MISSION:-}"
ALMANAC_ORG_PRIMARY_PROJECT="${ALMANAC_ORG_PRIMARY_PROJECT:-}"
ALMANAC_ORG_TIMEZONE="${ALMANAC_ORG_TIMEZONE:-Etc/UTC}"
ALMANAC_ORG_QUIET_HOURS="${ALMANAC_ORG_QUIET_HOURS:-}"
ALMANAC_ORG_PROFILE_BUILDER_ENABLED="${ALMANAC_ORG_PROFILE_BUILDER_ENABLED:-}"
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
. "$BOOTSTRAP_DIR/bin/model-providers.sh" 2>/dev/null || true
if declare -f model_provider_resolve_target_or_default >/dev/null 2>&1; then
  ALMANAC_MODEL_PRESET_CODEX="$(model_provider_resolve_target_or_default codex "${ALMANAC_MODEL_PRESET_CODEX:-}" "openai-codex:gpt-5.5")"
  ALMANAC_MODEL_PRESET_OPUS="$(model_provider_resolve_target_or_default opus "${ALMANAC_MODEL_PRESET_OPUS:-}" "anthropic:claude-opus-4-7")"
  ALMANAC_MODEL_PRESET_CHUTES="$(model_provider_resolve_target_or_default chutes "${ALMANAC_MODEL_PRESET_CHUTES:-}" "chutes:moonshotai/Kimi-K2.6-TEE")"
else
  ALMANAC_MODEL_PRESET_CODEX="${ALMANAC_MODEL_PRESET_CODEX:-openai-codex:gpt-5.5}"
  ALMANAC_MODEL_PRESET_OPUS="${ALMANAC_MODEL_PRESET_OPUS:-anthropic:claude-opus-4-7}"
  ALMANAC_MODEL_PRESET_CHUTES="${ALMANAC_MODEL_PRESET_CHUTES:-chutes:moonshotai/Kimi-K2.6-TEE}"
fi
ALMANAC_ORG_PROVIDER_ENABLED="${ALMANAC_ORG_PROVIDER_ENABLED:-}"
ALMANAC_ORG_PROVIDER_PRESET="${ALMANAC_ORG_PROVIDER_PRESET:-}"
ALMANAC_ORG_PROVIDER_MODEL_ID="${ALMANAC_ORG_PROVIDER_MODEL_ID:-}"
ALMANAC_ORG_PROVIDER_REASONING_EFFORT="${ALMANAC_ORG_PROVIDER_REASONING_EFFORT:-medium}"
ALMANAC_ORG_PROVIDER_SECRET_PROVIDER="${ALMANAC_ORG_PROVIDER_SECRET_PROVIDER:-}"
ALMANAC_ORG_PROVIDER_SECRET="${ALMANAC_ORG_PROVIDER_SECRET:-}"
ALMANAC_CURATOR_MODEL_PRESET="${ALMANAC_CURATOR_MODEL_PRESET:-codex}"
ALMANAC_CURATOR_CHANNELS="${ALMANAC_CURATOR_CHANNELS:-tui-only}"
ALMANAC_EXTRA_MCP_NAME="${ALMANAC_EXTRA_MCP_NAME:-external-kb}"
ALMANAC_EXTRA_MCP_LABEL="${ALMANAC_EXTRA_MCP_LABEL:-External knowledge rail}"
ALMANAC_EXTRA_MCP_URL="${ALMANAC_EXTRA_MCP_URL:-}"
ALMANAC_UPSTREAM_REPO_URL="${ALMANAC_UPSTREAM_REPO_URL:-https://github.com/example/almanac.git}"
ALMANAC_UPSTREAM_BRANCH="${ALMANAC_UPSTREAM_BRANCH:-main}"
ALMANAC_AGENT_DASHBOARD_BACKEND_PORT_BASE="${ALMANAC_AGENT_DASHBOARD_BACKEND_PORT_BASE:-19000}"
ALMANAC_AGENT_DASHBOARD_PROXY_PORT_BASE="${ALMANAC_AGENT_DASHBOARD_PROXY_PORT_BASE:-29000}"
ALMANAC_AGENT_CODE_PORT_BASE="${ALMANAC_AGENT_CODE_PORT_BASE:-39000}"
ALMANAC_AGENT_PORT_SLOT_SPAN="${ALMANAC_AGENT_PORT_SLOT_SPAN:-5000}"
ALMANAC_AGENT_CODE_SERVER_IMAGE="${ALMANAC_AGENT_CODE_SERVER_IMAGE:-docker.io/codercom/code-server:4.116.0}"
ALMANAC_AGENT_ENABLE_TAILSCALE_SERVE="${ALMANAC_AGENT_ENABLE_TAILSCALE_SERVE:-$ENABLE_TAILSCALE_SERVE}"
ALMANAC_RELEASE_STATE_FILE="${ALMANAC_RELEASE_STATE_FILE:-}"
ALMANAC_OPERATOR_ARTIFACT_FILE="${ALMANAC_OPERATOR_ARTIFACT_FILE:-$BOOTSTRAP_DIR/.almanac-operator.env}"
NEXTCLOUD_ROTATE_POSTGRES_PASSWORD="${NEXTCLOUD_ROTATE_POSTGRES_PASSWORD:-}"
NEXTCLOUD_ROTATE_ADMIN_PASSWORD="${NEXTCLOUD_ROTATE_ADMIN_PASSWORD:-}"
NEXTCLOUD_ROTATE_ASSUME_YES="${NEXTCLOUD_ROTATE_ASSUME_YES:-0}"

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
  local line=""

  while IFS= read -r line; do
    artifact_hints+=("$line")
  done < <(read_operator_artifact_hints || true)
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

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

host_uname_s() {
  uname -s 2>/dev/null || printf '%s\n' "unknown"
}

host_is_linux() {
  [[ "$(host_uname_s)" == "Linux" ]]
}

host_is_macos() {
  [[ "$(host_uname_s)" == "Darwin" ]]
}

host_is_wsl() {
  local marker=""

  if ! host_is_linux; then
    return 1
  fi

  marker="$(cat /proc/sys/kernel/osrelease /proc/version 2>/dev/null || true)"
  [[ "$marker" =~ [Mm]icrosoft|WSL ]]
}

default_home_for_user() {
  local user="${1:-}"

  if [[ -z "$user" ]]; then
    return 1
  fi

  if host_is_macos; then
    printf '/Users/%s\n' "$user"
    return 0
  fi

  printf '/home/%s\n' "$user"
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

host_supports_full_deploy() {
  host_is_linux || return 1
  command_exists apt-get || return 1
  command_exists systemctl || return 1
  command_exists loginctl || return 1
  [[ -d /run/systemd/system ]] || return 1
}

require_supported_host_mode() {
  local mode="${1:-$MODE}"

  if [[ "$mode" == "write-config" || "$mode" == "agent-payload" || "$mode" == "menu" ]]; then
    return 0
  fi

  if host_supports_full_deploy; then
    return 0
  fi

  if host_is_macos; then
    cat >&2 <<'EOF'
Native macOS is not a supported Almanac host or runtime environment.
Helper-only commands like `./deploy.sh write-config` and `./deploy.sh agent-payload`
may still be useful from an operator checkout, but install, upgrade, remove,
health, and service management must run on Debian/Ubuntu Linux or WSL2 Ubuntu
with systemd enabled.
EOF
    return 1
  fi

  if host_is_wsl; then
    cat >&2 <<'EOF'
WSL2 was detected, but the Linux guest is not ready for full Almanac deployment yet.
Almanac needs `apt`, `systemd`, and `loginctl` inside the Ubuntu instance.

If systemd is not enabled yet, add this to /etc/wsl.conf inside Ubuntu:
  [boot]
  systemd=true

Then restart WSL from Windows with:
  wsl --shutdown

Reopen the Ubuntu instance and rerun ./deploy.sh.
EOF
    return 1
  fi

  cat >&2 <<'EOF'
Full Almanac host deployment currently supports Debian/Ubuntu-style Linux hosts with
`apt`, `systemd`, and `loginctl` available.
EOF
  return 1
}

collect_host_dependency_answers() {
  local podman_default="1"
  local tailscale_default="0"

  ALMANAC_INSTALL_PODMAN="0"
  ALMANAC_INSTALL_TAILSCALE="0"

  if ! command_exists podman; then
    ALMANAC_INSTALL_PODMAN="$(ask_yes_no "Podman is not installed. Install it now for Nextcloud and per-agent code workspaces" "$podman_default")"
  fi

  if ! command_exists tailscale; then
    if [[ "$ENABLE_TAILSCALE_SERVE" == "1" || "${ALMANAC_AGENT_ENABLE_TAILSCALE_SERVE:-$ENABLE_TAILSCALE_SERVE}" == "1" ]]; then
      tailscale_default="1"
    fi
    ALMANAC_INSTALL_TAILSCALE="$(ask_yes_no "Tailscale is not installed. Install it now for tailnet-only access and HTTPS serve" "$tailscale_default")"
  fi
}

usage() {
  cat <<'EOF'
Usage:
  deploy.sh                # interactive menu
  deploy.sh install
  deploy.sh upgrade
  deploy.sh notion-ssot
  deploy.sh enrollment-status
  deploy.sh enrollment-trace [--unix-user USER | --session-id onb_xxx | --request-id req_xxx]
  deploy.sh enrollment-align
  deploy.sh enrollment-reset
  deploy.sh curator-setup
  deploy.sh rotate-nextcloud-secrets
  deploy.sh agent-payload
  deploy.sh write-config
  deploy.sh remove
  deploy.sh health

Docker control center:
  deploy.sh docker install        # idempotent bootstrap + build + up + health
  deploy.sh docker upgrade        # rebuild/recreate from current checkout + health
  deploy.sh docker reconfigure    # refresh generated Docker config/ports only
  deploy.sh docker health
  deploy.sh docker ports
  deploy.sh docker logs [SERVICE]
  deploy.sh docker ps
  deploy.sh docker notion-ssot
  deploy.sh docker enrollment-status
  deploy.sh docker enrollment-trace --unix-user <user>
  deploy.sh docker enrollment-align
  deploy.sh docker enrollment-reset --unix-user <user>
  deploy.sh docker curator-setup
  deploy.sh docker rotate-nextcloud-secrets
  deploy.sh docker agent-payload
  deploy.sh docker pins-show
  deploy.sh docker pins-check
  deploy.sh docker <component>-upgrade-check
  deploy.sh docker <component>-upgrade [--tag/--version/--ref ...]
  deploy.sh docker down
  deploy.sh docker teardown

Docker shortcut aliases:
  deploy.sh docker-install
  deploy.sh docker-upgrade
  deploy.sh docker-reconfigure
  deploy.sh docker-enrollment-status
  deploy.sh docker-health
  deploy.sh docker-ports

Pinned-component upgrades (config/pins.json is the source of truth):
  deploy.sh pins-show                          # pretty-print every pinned component
  deploy.sh pins-check                         # cross-component drift report (read-only)
  deploy.sh pin-upgrade-notify                 # detector run: emit operator digest, honor per-release throttle
  deploy.sh hermes-upgrade-check               # gap vs upstream HEAD
  deploy.sh hermes-upgrade [--ref REF]         # bump + commit/push + re-exec upgrade
  deploy.sh qmd-upgrade-check                  # npm dist-tags.latest vs pinned
  deploy.sh qmd-upgrade [--version V]
  deploy.sh nextcloud-upgrade-check            # Docker Hub recent tags + current digest
  deploy.sh nextcloud-upgrade --tag TAG        # explicit tag bump (no auto-bump for containers)
  deploy.sh postgres-upgrade-check
  deploy.sh postgres-upgrade --tag TAG
  deploy.sh redis-upgrade-check
  deploy.sh redis-upgrade --tag TAG
  deploy.sh code-server-upgrade-check
  deploy.sh code-server-upgrade --tag TAG
  deploy.sh nvm-upgrade-check                  # latest semver tag of nvm-sh/nvm
  deploy.sh nvm-upgrade [--tag TAG]
  deploy.sh node-upgrade-check                 # latest patch within pinned major
  deploy.sh node-upgrade --version vX.Y.Z      # explicit semver bump

Compatibility:
  deploy.sh --write-config-only   # helper-only; not a full host deployment path
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    docker)
      MODE="$1"
      shift
      if [[ $# -gt 0 ]]; then
        case "$1" in
          -h|--help)
            DOCKER_DEPLOY_COMMAND="help"
            shift
            ;;
          *)
            DOCKER_DEPLOY_COMMAND="$1"
            shift
            ;;
        esac
      fi
      DOCKER_DEPLOY_ARGS=("$@")
      break
      ;;
    docker-install|docker-upgrade|docker-reconfigure|docker-bootstrap|docker-config|docker-build|docker-up|docker-down|docker-ps|docker-ports|docker-logs|docker-health|docker-teardown|docker-write-config|docker-remove|docker-notion-ssot|docker-enrollment-status|docker-enrollment-trace|docker-enrollment-align|docker-enrollment-reset|docker-curator-setup|docker-rotate-nextcloud-secrets|docker-agent-payload|docker-pins-show|docker-pins-check|docker-pin-upgrade-notify|docker-hermes-upgrade|docker-hermes-upgrade-check|docker-qmd-upgrade|docker-qmd-upgrade-check|docker-nextcloud-upgrade|docker-nextcloud-upgrade-check|docker-postgres-upgrade|docker-postgres-upgrade-check|docker-redis-upgrade|docker-redis-upgrade-check|docker-code-server-upgrade|docker-code-server-upgrade-check|docker-nvm-upgrade|docker-nvm-upgrade-check|docker-node-upgrade|docker-node-upgrade-check)
      MODE="$1"
      shift
      DOCKER_DEPLOY_ARGS=("$@")
      break
      ;;
    install|upgrade|notion-ssot|enrollment-status|enrollment-trace|enrollment-align|enrollment-reset|curator-setup|rotate-nextcloud-secrets|agent-payload|agent|write-config|remove|health|menu|pins-show|pins-check|pin-upgrade-notify|hermes-upgrade|hermes-upgrade-check|qmd-upgrade|qmd-upgrade-check|nextcloud-upgrade|nextcloud-upgrade-check|postgres-upgrade|postgres-upgrade-check|redis-upgrade|redis-upgrade-check|code-server-upgrade|code-server-upgrade-check|nvm-upgrade|nvm-upgrade-check|node-upgrade|node-upgrade-check)
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
  printf '\n' >&2
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

validate_org_timezone() {
  local value="${1:-}"
  if [[ -z "$value" ]]; then
    return 0
  fi
  python3 - "$value" <<'PY'
import sys
from zoneinfo import available_timezones

value = (sys.argv[1] or "").strip()
raise SystemExit(0 if value in available_timezones() else 1)
PY
}

validate_org_quiet_hours() {
  local value="${1:-}"
  if [[ -z "$value" ]]; then
    return 0
  fi
  python3 - "$value" <<'PY'
import re
import sys

value = (sys.argv[1] or "").strip()
pattern = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d-(?:[01]\d|2[0-3]):[0-5]\d(?:\s+\S.*)?$")
raise SystemExit(0 if pattern.fullmatch(value) else 1)
PY
}

ask_validated_optional() {
  local prompt="$1"
  local default="${2:-}"
  local validator="$3"
  local error_message="$4"
  local answer=""

  while true; do
    answer="$(normalize_optional_answer "$(ask "$prompt" "$default")")"
    if "$validator" "$answer"; then
      printf '%s' "$answer"
      return 0
    fi
    printf '%s\n' "$error_message" >&2
  done
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
  printf '\n' >&2

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
  printf '\n' >&2

  if [[ -z "$answer" ]]; then
    answer="$default"
  fi

  printf '%s' "$answer"
}

json_field() {
  local payload="$1"
  local field="$2"

  python3 - "$field" "$payload" <<'PY'
import json
import sys

field = sys.argv[1]
try:
    data = json.loads(sys.argv[2])
except Exception:
    raise SystemExit(1)

value = data
for part in field.split("."):
    if isinstance(value, dict):
        value = value.get(part)
    else:
        value = None
        break

if isinstance(value, bool):
    print("1" if value else "0")
elif value is None:
    print("")
else:
    print(str(value))
PY
}

notion_webhook_status_json() {
  local ctl_bin="$1"
  env ALMANAC_CONFIG_FILE="$CONFIG_TARGET" \
    "$ctl_bin" --json notion webhook-status --show-public-url --show-secret
}

run_notion_webhook_setup_flow() {
  local ctl_bin="$1"
  local actor="$2"
  local status_json="" configured="" verified="" token="" public_url="" verified_at="" verified_by="" armed_json="" armed_until=""

  if [[ -z "${ALMANAC_NOTION_WEBHOOK_PUBLIC_URL:-}" ]]; then
    return 0
  fi

  status_json="$(notion_webhook_status_json "$ctl_bin" 2>/dev/null || true)"
  if [[ -z "$status_json" ]]; then
    echo "Could not read Notion webhook verification state; cannot continue the deploy-owned webhook setup flow." >&2
    return 1
  fi

  verified="$(json_field "$status_json" "verified" 2>/dev/null || true)"
  if [[ "$verified" == "1" ]]; then
    verified_at="$(json_field "$status_json" "verified_at" 2>/dev/null || true)"
    verified_by="$(json_field "$status_json" "verified_by" 2>/dev/null || true)"
    echo
    echo "Notion webhook verification is already confirmed."
    if [[ -n "$verified_at" || -n "$verified_by" ]]; then
      echo "  confirmed_at: ${verified_at:-unknown}"
      if [[ -n "$verified_by" ]]; then
        echo "  confirmed_by: $verified_by"
      fi
    fi
    return 0
  fi

  if [[ ! -t 0 ]]; then
    echo "Notion webhook verification is not yet confirmed. Run \`$SELF_PATH notion-ssot\` interactively to finish the webhook setup flow." >&2
    return 1
  fi

  public_url="$(json_field "$status_json" "public_url" 2>/dev/null || true)"
  configured="$(json_field "$status_json" "configured" 2>/dev/null || true)"
  token="$(json_field "$status_json" "verification_token" 2>/dev/null || true)"

  echo
  echo "Notion webhook verification walkthrough"
  echo
  echo "Step 1. Open the Notion Developer Portal for this integration."
  echo "  - Go to the Webhooks tab."
  echo "  - Keep this terminal open; deploy will walk you through each step."
  read -r -p "Press ENTER when the Notion Webhooks tab is open. " _

  echo
  echo "Step 2. Use this exact webhook URL."
  echo "  ${public_url:-${ALMANAC_NOTION_WEBHOOK_PUBLIC_URL}}"
  echo "  - If a subscription already exists for this exact URL, edit it."
  echo "  - Do not create a duplicate subscription for the same Almanac endpoint."
  read -r -p "Press ENTER when the webhook URL is entered or the existing matching subscription is open for editing. " _

  echo
  echo "Step 3. Set the event selection exactly like this."
  echo "  - Page: all Page events"
  echo "  - Database: all Database events"
  echo "  - Data source: all Data source events"
  echo "  - File uploads: all File upload events"
  echo "  - View: leave unchecked"
  echo "  - Comment: leave unchecked"
  read -r -p "Press ENTER once the event selection in Notion matches this checklist exactly. " _

  echo
  if [[ "$configured" != "1" || -z "${token//[[:space:]]/}" ]]; then
    echo "Step 4. Deploy will arm a fresh 30-minute verification window."
    echo "  - After the window is armed, immediately click Create subscription or Save in Notion."
    echo "  - That click is what causes Notion to send the verification token to Almanac."
    read -r -p "Press ENTER when you are ready for deploy to arm the window. " _
    armed_json="$(env ALMANAC_CONFIG_FILE="$CONFIG_TARGET" \
      "$ctl_bin" --json notion webhook-arm-install --actor "$actor" --minutes 30)"
    armed_until="$(json_field "$armed_json" "armed_until" 2>/dev/null || true)"
    echo "  Verification window armed."
    if [[ -n "$armed_until" ]]; then
      echo "  armed_until: $armed_until"
    fi
    read -r -p "Press ENTER immediately after Notion says the verification token was sent to the URL. " _
  else
    echo "Step 4. A verification token is already installed."
    echo "  - We will reuse that token for the final Verify step."
    read -r -p "Press ENTER once the Notion Verify dialog is open and ready for the token. " _
  fi

  if [[ "$configured" != "1" || -z "${token//[[:space:]]/}" ]]; then
    local attempt=""
    for attempt in $(seq 1 45); do
      status_json="$(notion_webhook_status_json "$ctl_bin" 2>/dev/null || true)"
      configured="$(json_field "$status_json" "configured" 2>/dev/null || true)"
      token="$(json_field "$status_json" "verification_token" 2>/dev/null || true)"
      if [[ "$configured" == "1" && -n "${token//[[:space:]]/}" ]]; then
        break
      fi
      sleep 2
    done
  fi

  if [[ "$configured" != "1" || -z "${token//[[:space:]]/}" ]]; then
    echo "Notion did not install a verification token within the waiting window." >&2
    echo "The webhook URL is configured, but verification is still incomplete." >&2
    return 1
  fi

  echo
  echo "Step 5. Paste this Notion verification token into the Notion Verify dialog."
  echo "  $token"
  echo
  read -r -p "Press ENTER after you paste the token into Notion. " _
  echo
  echo "Step 6. Click Verify subscription in Notion."
  if [[ "$(ask_yes_no "Did Notion accept the token and mark the subscription verified" "1")" != "1" ]]; then
    echo "Notion webhook verification was not confirmed. You can rerun \`$SELF_PATH notion-ssot\` to finish it later." >&2
    return 1
  fi

  env ALMANAC_CONFIG_FILE="$CONFIG_TARGET" \
    "$ctl_bin" --json notion webhook-confirm-verified --actor "$actor" >/dev/null
  status_json="$(notion_webhook_status_json "$ctl_bin")"
  verified_at="$(json_field "$status_json" "verified_at" 2>/dev/null || true)"
  verified_by="$(json_field "$status_json" "verified_by" 2>/dev/null || true)"
  echo
  echo "Notion webhook verification confirmed."
  if [[ -n "$verified_at" || -n "$verified_by" ]]; then
    echo "  verified_at: ${verified_at:-unknown}"
    if [[ -n "$verified_by" ]]; then
      echo "  verified_by: $verified_by"
    fi
  fi
}

require_notion_subtree_ack() {
  local answer=""

  echo
  echo "Important Notion access model:"
  echo "  - Almanac cannot press Notion's Manage page access buttons for you via"
  echo "    a supported API."
  echo "  - The internal integration only automatically inherits access to child"
  echo "    pages and databases created under a granted parent/root subtree."
  echo "  - Anything created outside that granted subtree will need manual page"
  echo "    access later."
  echo "  - The sane setup is to grant one stable Teamspace root page or parent"
  echo "    page, then keep Almanac-managed content under it."
  echo

  while true; do
    read -r -p "Type YES to confirm you understand this Notion access model: " answer
    if [[ "$answer" == "YES" ]]; then
      return 0
    fi
    echo "Please type YES exactly. That guardrail keeps the Teamspace/subtree model explicit."
  done
}

choose_mode() {
  local answer=""

  cat <<'EOF'
Almanac deploy menu

  1) Install / repair from current checkout
  2) Upgrade deployed host from configured upstream
  3) Write config only
  4) Notion SSOT setup / test
  5) Enrollment status
  6) Enrollment trace
  7) Enrollment align / repair
  8) Enrollment reset / cleanup
  9) Curator setup / repair
 10) Rotate Nextcloud secrets
 11) Print agent payload
 12) Health check
 13) Remove / teardown
 14) Docker control center
 15) Exit
EOF

  while true; do
    read -r -p "Choose mode [1]: " answer
    case "${answer:-1}" in
      1) MODE="install"; return 0 ;;
      2) MODE="upgrade"; return 0 ;;
      3) MODE="write-config"; return 0 ;;
      4) MODE="notion-ssot"; return 0 ;;
      5) MODE="enrollment-status"; return 0 ;;
      6) MODE="enrollment-trace"; return 0 ;;
      7) MODE="enrollment-align"; return 0 ;;
      8) MODE="enrollment-reset"; return 0 ;;
      9) MODE="curator-setup"; return 0 ;;
      10) MODE="rotate-nextcloud-secrets"; return 0 ;;
      11) MODE="agent-payload"; return 0 ;;
      12) MODE="health"; return 0 ;;
      13) MODE="remove"; return 0 ;;
      14) MODE="docker"; DOCKER_DEPLOY_COMMAND="menu"; return 0 ;;
      15) exit 0 ;;
      *) echo "Please choose 1 through 15." ;;
    esac
  done
}

docker_usage() {
  cat <<'EOF'
Usage:
  deploy.sh docker install        # idempotent bootstrap + build + up + health
  deploy.sh docker upgrade        # rebuild/recreate from current checkout + health
  deploy.sh docker reconfigure    # refresh generated Docker config/ports only
  deploy.sh docker bootstrap
  deploy.sh docker config [-q]
  deploy.sh docker build [SERVICE...]
  deploy.sh docker up [SERVICE...]
  deploy.sh docker down
  deploy.sh docker ps
  deploy.sh docker ports
  deploy.sh docker logs [SERVICE]
  deploy.sh docker health
  deploy.sh docker notion-ssot
  deploy.sh docker enrollment-status
  deploy.sh docker enrollment-trace --unix-user <user>
  deploy.sh docker enrollment-align
  deploy.sh docker enrollment-reset --unix-user <user>
  deploy.sh docker curator-setup
  deploy.sh docker rotate-nextcloud-secrets
  deploy.sh docker agent-payload
  deploy.sh docker pins-show
  deploy.sh docker pins-check
  deploy.sh docker <component>-upgrade-check
  deploy.sh docker <component>-upgrade [--tag/--version/--ref ...]
  deploy.sh docker teardown
  deploy.sh docker remove

Shortcut aliases:
  deploy.sh docker-install
  deploy.sh docker-upgrade
  deploy.sh docker-reconfigure
  deploy.sh docker-enrollment-status
  deploy.sh docker-health
  deploy.sh docker-ports
EOF
}

choose_docker_mode() {
  local answer=""

  cat <<'EOF'
Almanac Docker control center

  1) Install / repair Docker stack from current checkout
  2) Upgrade / rebuild Docker stack from current checkout
  3) Reconfigure Docker generated config and ports
  4) Docker health check
  5) Show Docker ports
  6) Show Docker service state
  7) Enrollment status
  8) Enrollment align / repair
  9) Curator setup
 10) Rotate Nextcloud secrets
 11) Show Docker logs
 12) Stop Docker stack
 13) Teardown Docker stack and named volumes
 14) Exit
EOF

  while true; do
    read -r -p "Choose Docker mode [1]: " answer
    case "${answer:-1}" in
      1) DOCKER_DEPLOY_COMMAND="install"; return 0 ;;
      2) DOCKER_DEPLOY_COMMAND="upgrade"; return 0 ;;
      3) DOCKER_DEPLOY_COMMAND="reconfigure"; return 0 ;;
      4) DOCKER_DEPLOY_COMMAND="health"; return 0 ;;
      5) DOCKER_DEPLOY_COMMAND="ports"; return 0 ;;
      6) DOCKER_DEPLOY_COMMAND="ps"; return 0 ;;
      7) DOCKER_DEPLOY_COMMAND="enrollment-status"; return 0 ;;
      8) DOCKER_DEPLOY_COMMAND="enrollment-align"; return 0 ;;
      9) DOCKER_DEPLOY_COMMAND="curator-setup"; return 0 ;;
      10) DOCKER_DEPLOY_COMMAND="rotate-nextcloud-secrets"; return 0 ;;
      11) DOCKER_DEPLOY_COMMAND="logs"; return 0 ;;
      12) DOCKER_DEPLOY_COMMAND="down"; return 0 ;;
      13) DOCKER_DEPLOY_COMMAND="teardown"; return 0 ;;
      14) exit 0 ;;
      *) echo "Please choose 1 through 14." ;;
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
    TAILSCALE_SERVE_JSON="$ts_json" python3 - "${TAILSCALE_SERVE_PORT:-443}" "$QMD_MCP_PORT" "$TAILSCALE_QMD_PATH" "$ALMANAC_MCP_PORT" "$TAILSCALE_ALMANAC_MCP_PATH" <<'PY'
import json
import os
import sys

try:
    data = json.loads(os.environ["TAILSCALE_SERVE_JSON"])
except Exception:
    raise SystemExit(0)

serve_port = str(sys.argv[1])
qmd_port = sys.argv[2]
qmd_path = sys.argv[3]
almanac_mcp_port = sys.argv[4]
almanac_mcp_path = sys.argv[5]
web = data.get("Web") or {}

host = ""
has_root = False
has_qmd = False
has_almanac_mcp = False

for hostport, entry in web.items():
    parsed_host, sep, parsed_port = hostport.rpartition(":")
    actual_port = parsed_port if sep and parsed_port.isdigit() else "443"
    if actual_port != serve_port:
        continue
    if not host:
        host = parsed_host if sep and parsed_port.isdigit() else hostport
    handlers = (entry or {}).get("Handlers") or {}
    if "/" in handlers:
        has_root = True
    qmd_handler = handlers.get(qmd_path) or {}
    almanac_handler = handlers.get(almanac_mcp_path) or {}
    qmd_proxy = str(qmd_handler.get("Proxy") or "")
    almanac_proxy = str(almanac_handler.get("Proxy") or "")
    if qmd_proxy == f"http://127.0.0.1:{qmd_port}/mcp":
        has_qmd = True
    if almanac_proxy == f"http://127.0.0.1:{almanac_mcp_port}/mcp":
        has_almanac_mcp = True
    for path, handler in handlers.items():
        proxy = str((handler or {}).get("Proxy") or "")
        if path == qmd_path and proxy == f"http://127.0.0.1:{qmd_port}/mcp":
            has_qmd = True
        if path == almanac_mcp_path and proxy == f"http://127.0.0.1:{almanac_mcp_port}/mcp":
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

normalize_http_path() {
  local path="${1:-/}"
  if [[ -z "$path" ]]; then
    path="/"
  fi
  if [[ "$path" != /* ]]; then
    path="/$path"
  fi
  printf '%s\n' "$path"
}

build_public_https_url() {
  local host="${1:-}"
  local port="${2:-443}"
  local path=""

  path="$(normalize_http_path "${3:-/}")"
  if [[ -z "$host" ]]; then
    return 1
  fi
  if [[ -z "$port" || "$port" == "443" ]]; then
    printf 'https://%s%s\n' "$host" "$path"
  else
    printf 'https://%s:%s%s\n' "$host" "$port" "$path"
  fi
}

refresh_notion_webhook_public_url_from_tailscale() {
  local derived_url=""
  local funnel_path=""

  funnel_path="$(normalize_http_path "${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH:-/notion/webhook}")"
  TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH="$funnel_path"

  detect_tailscale
  if [[ -n "${TAILSCALE_DNS_NAME:-}" ]]; then
    derived_url="$(build_public_https_url "$TAILSCALE_DNS_NAME" "${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-8443}" "$funnel_path" || true)"
  fi

  if [[ "$ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL" == "1" ]]; then
    if [[ -n "$derived_url" ]]; then
      ALMANAC_NOTION_WEBHOOK_PUBLIC_URL="$derived_url"
    fi
  elif [[ -n "$derived_url" && "${ALMANAC_NOTION_WEBHOOK_PUBLIC_URL:-}" == "$derived_url" ]]; then
    ALMANAC_NOTION_WEBHOOK_PUBLIC_URL=""
  fi
}

detect_tailscale_notion_webhook_funnel() {
  TAILSCALE_FUNNEL_WEBHOOK_HOST=""
  TAILSCALE_FUNNEL_WEBHOOK_URL=""
  TAILSCALE_FUNNEL_HAS_NOTION_WEBHOOK="0"

  if ! command -v tailscale >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1; then
    return 0
  fi

  local ts_json=""
  ts_json="$(tailscale funnel status --json 2>/dev/null || true)"
  if [[ -z "$ts_json" ]]; then
    return 0
  fi

  local funnel_path=""
  funnel_path="$(normalize_http_path "${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH:-/notion/webhook}")"

  local ts_info=""
  ts_info="$(
    TAILSCALE_FUNNEL_JSON="$ts_json" python3 - "${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-8443}" "$funnel_path" "$ALMANAC_NOTION_WEBHOOK_PORT" <<'PY'
import json
import os
import sys

port = str(sys.argv[1])
path = sys.argv[2]
backend_port = str(sys.argv[3])

try:
    data = json.loads(os.environ["TAILSCALE_FUNNEL_JSON"])
except Exception:
    raise SystemExit(0)

web = data.get("Web") or {}
allow = data.get("AllowFunnel") or {}
expected_proxy = f"http://127.0.0.1:{backend_port}"

for hostport, entry in web.items():
    if not hostport.endswith(f":{port}"):
        continue
    handlers = (entry or {}).get("Handlers") or {}
    handler = handlers.get(path) or handlers.get("/") or {}
    if str(handler.get("Proxy") or "") != expected_proxy:
        continue
    if not allow.get(hostport):
        continue
    host = hostport.rsplit(":", 1)[0]
    print(f"host={host}")
    print("active=1")
    raise SystemExit(0)
PY
  )"

  while IFS='=' read -r key value; do
    case "$key" in
      host) TAILSCALE_FUNNEL_WEBHOOK_HOST="$value" ;;
      active) TAILSCALE_FUNNEL_HAS_NOTION_WEBHOOK="$value" ;;
    esac
  done <<<"$ts_info"

  if [[ "$TAILSCALE_FUNNEL_HAS_NOTION_WEBHOOK" == "1" && -n "$TAILSCALE_FUNNEL_WEBHOOK_HOST" ]]; then
    TAILSCALE_FUNNEL_WEBHOOK_URL="$(
      build_public_https_url \
        "$TAILSCALE_FUNNEL_WEBHOOK_HOST" \
        "${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-8443}" \
        "${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH:-/notion/webhook}" || true
    )"
  fi
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
    AGENT_QMD_TAILNET_URL="$(build_public_https_url "$AGENT_QMD_TAILNET_HOST" "${TAILSCALE_SERVE_PORT:-443}" "${TAILSCALE_QMD_PATH}")"
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
    AGENT_ALMANAC_MCP_TAILNET_URL="$(build_public_https_url "$AGENT_ALMANAC_MCP_TAILNET_HOST" "${TAILSCALE_SERVE_PORT:-443}" "${TAILSCALE_ALMANAC_MCP_PATH}")"
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
  GITHUB_REPO_OWNER_REPO=""
  GITHUB_REPO_BRANCH="main"

  if ! command -v git >/dev/null 2>&1; then
    GITHUB_REPO_URL="https://github.com/example/almanac"
    GITHUB_REPO_OWNER_REPO="example/almanac"
    return 0
  fi

  local remote_url="" branch="" owner_repo=""
  remote_url="$(git -C "$ALMANAC_REPO_DIR" remote get-url origin 2>/dev/null || true)"
  branch="$(git -C "$ALMANAC_REPO_DIR" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
  GITHUB_REPO_BRANCH="${branch:-main}"

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
    GITHUB_REPO_OWNER_REPO="$owner_repo"
  else
    GITHUB_REPO_URL="https://github.com/example/almanac"
    GITHUB_REPO_OWNER_REPO="example/almanac"
    GITHUB_REPO_BRANCH="main"
  fi
}

discover_existing_config() {
  local -a artifact_hints=()
  local candidate=""
  local explicit_config=""
  local artifact_config=""
  local artifact_user="" artifact_repo="" artifact_priv="" artifact_home=""
  local status=""
  local line=""
  explicit_config="${ALMANAC_CONFIG_FILE:-}"
  while IFS= read -r line; do
    artifact_hints+=("$line")
  done < <(read_operator_artifact_hints || true)
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
    resolve_model_provider_presets
    return 0
  fi

  return 1
}

resolve_model_provider_presets() {
  if declare -f model_provider_resolve_target_or_default >/dev/null 2>&1; then
    ALMANAC_MODEL_PRESET_CODEX="$(model_provider_resolve_target_or_default codex "${ALMANAC_MODEL_PRESET_CODEX:-}" "openai-codex:gpt-5.5")"
    ALMANAC_MODEL_PRESET_OPUS="$(model_provider_resolve_target_or_default opus "${ALMANAC_MODEL_PRESET_OPUS:-}" "anthropic:claude-opus-4-7")"
    ALMANAC_MODEL_PRESET_CHUTES="$(model_provider_resolve_target_or_default chutes "${ALMANAC_MODEL_PRESET_CHUTES:-}" "chutes:moonshotai/Kimi-K2.6-TEE")"
  fi
}

reload_runtime_config_from_file() {
  local config_path="${1:-$CONFIG_TARGET}"

  if [[ -n "$config_path" && -f "$config_path" && -r "$config_path" ]]; then
    # shellcheck disable=SC1090
    source "$config_path"
    VAULT_QMD_COLLECTION_MASK="$(normalize_vault_qmd_collection_mask "${VAULT_QMD_COLLECTION_MASK:-}")"
    resolve_model_provider_presets
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

trim_secret_marker() {
  local value="${1:-}"

  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

read_single_line_secret_file() {
  local label="$1"
  local path="$2"

  python3 - "$label" "$path" <<'PY'
from pathlib import Path
import sys

label = sys.argv[1]
path = Path(sys.argv[2])
try:
    value = path.read_text(encoding="utf-8")
except OSError as exc:
    raise SystemExit(f"{label} file cannot be read: {exc}") from exc

if value.endswith("\n"):
    value = value[:-1]
if not value or "\n" in value or "\r" in value:
    raise SystemExit(f"{label} file must contain one non-empty line.")

print(value, end="")
PY
}

lowercase() {
  printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]'
}

is_placeholder_secret() {
  local value=""

  value="$(trim_secret_marker "${1:-}")"
  case "$(lowercase "$value")" in
    change-me|changeme|generated-at-deploy)
      return 0
      ;;
  esac

  return 1
}

preserve_or_randomize_secret() {
  local value="${1:-}"

  if [[ -z "$value" ]] || is_placeholder_secret "$value"; then
    random_secret
    return 0
  fi

  printf '%s' "$value"
}

write_kv() {
  local key="$1"
  local value="${2:-}"
  printf '%s=%q\n' "$key" "$value"
}

deploy_pins_file() {
  local candidate=""
  for candidate in \
    "${ALMANAC_PINS_FILE:-}" \
    "${ALMANAC_REPO_DIR:-}/config/pins.json" \
    "${BOOTSTRAP_DIR:-}/config/pins.json" \
    "./config/pins.json"; do
    if [[ -n "$candidate" && -r "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

deploy_pin_get_or_default() {
  local component="$1"
  local field="$2"
  local fallback="${3:-}"
  local pins_file=""
  local value=""
  pins_file="$(deploy_pins_file || true)"
  if [[ -n "$pins_file" ]] && command -v jq >/dev/null 2>&1; then
    value="$(jq -r --arg component "$component" --arg field "$field" '.components[$component][$field] // empty' "$pins_file" 2>/dev/null || true)"
  fi
  if [[ -z "$value" ]]; then
    value="$fallback"
  fi
  printf '%s' "$value"
}

deploy_pin_image_or_default() {
  local component="$1"
  local fallback="${2:-}"
  local image=""
  local tag=""
  image="$(deploy_pin_get_or_default "$component" image "")"
  tag="$(deploy_pin_get_or_default "$component" tag "")"
  if [[ -n "$image" && -n "$tag" ]]; then
    printf '%s:%s' "$image" "$tag"
    return 0
  fi
  printf '%s' "$fallback"
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
  case "${VAULT_WATCH_DEBOUNCE_SECONDS:-}" in
    ""|5|5.0|5.00)
      VAULT_WATCH_DEBOUNCE_SECONDS="0.5"
      ;;
  esac
  if [[ -z "${VAULT_WATCH_MAX_BATCH_SECONDS:-}" ]]; then
    VAULT_WATCH_MAX_BATCH_SECONDS="10"
  fi
  if [[ -z "${ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED:-}" ]]; then
    ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED="$(default_curator_telegram_onboarding_enabled)"
  fi
  if [[ -z "${ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED:-}" ]]; then
    ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED="$(default_curator_discord_onboarding_enabled)"
  fi
  if declare -F refresh_notion_webhook_public_url_from_tailscale >/dev/null 2>&1; then
    refresh_notion_webhook_public_url_from_tailscale
  fi
}

emit_runtime_config() {
  local notion_funnel_path="${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH:-/notion/webhook}"
  local hermes_agent_ref=""
  local hermes_docs_repo_url=""
  local hermes_docs_ref=""
  local code_server_image=""

  normalize_runtime_config_defaults
  hermes_agent_ref="$(deploy_pin_get_or_default hermes-agent ref "${ALMANAC_HERMES_AGENT_REF:-ce089169d578b96c82641f17186ba63c288b22d8}")"
  hermes_docs_repo_url="${ALMANAC_HERMES_DOCS_REPO_URL:-https://github.com/NousResearch/hermes-agent.git}"
  if [[ "$hermes_docs_repo_url" == "https://github.com/NousResearch/hermes-agent.git" ]]; then
    hermes_docs_ref="$(deploy_pin_get_or_default hermes-docs ref "${ALMANAC_HERMES_DOCS_REF:-$hermes_agent_ref}")"
  else
    hermes_docs_ref="${ALMANAC_HERMES_DOCS_REF:-$hermes_agent_ref}"
  fi
  code_server_image="$(deploy_pin_image_or_default code-server "${ALMANAC_AGENT_CODE_SERVER_IMAGE:-docker.io/codercom/code-server:4.116.0}")"
  if declare -F normalize_http_path >/dev/null 2>&1; then
    notion_funnel_path="$(normalize_http_path "$notion_funnel_path")"
  elif [[ "$notion_funnel_path" != /* ]]; then
    notion_funnel_path="/$notion_funnel_path"
  fi
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
    write_kv ALMANAC_NOTION_WEBHOOK_PUBLIC_URL "${ALMANAC_NOTION_WEBHOOK_PUBLIC_URL:-}"
    write_kv ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL "${ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL:-0}"
    write_kv TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT "${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-8443}"
    write_kv TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH "$notion_funnel_path"
    write_kv ALMANAC_SSOT_NOTION_ROOT_PAGE_URL "${ALMANAC_SSOT_NOTION_ROOT_PAGE_URL:-}"
    write_kv ALMANAC_SSOT_NOTION_ROOT_PAGE_ID "${ALMANAC_SSOT_NOTION_ROOT_PAGE_ID:-}"
    write_kv ALMANAC_SSOT_NOTION_SPACE_URL "${ALMANAC_SSOT_NOTION_SPACE_URL:-}"
    write_kv ALMANAC_SSOT_NOTION_SPACE_ID "${ALMANAC_SSOT_NOTION_SPACE_ID:-}"
    write_kv ALMANAC_SSOT_NOTION_SPACE_KIND "${ALMANAC_SSOT_NOTION_SPACE_KIND:-}"
    write_kv ALMANAC_SSOT_NOTION_API_VERSION "${ALMANAC_SSOT_NOTION_API_VERSION:-2026-03-11}"
    write_kv ALMANAC_SSOT_NOTION_TOKEN "${ALMANAC_SSOT_NOTION_TOKEN:-}"
    write_kv ALMANAC_NOTION_INDEX_ROOTS "${ALMANAC_NOTION_INDEX_ROOTS:-}"
    write_kv ALMANAC_NOTION_INDEX_RUN_EMBED "${ALMANAC_NOTION_INDEX_RUN_EMBED:-1}"
    write_kv ALMANAC_ORG_NAME "${ALMANAC_ORG_NAME:-}"
    write_kv ALMANAC_ORG_MISSION "${ALMANAC_ORG_MISSION:-}"
    write_kv ALMANAC_ORG_PRIMARY_PROJECT "${ALMANAC_ORG_PRIMARY_PROJECT:-}"
    write_kv ALMANAC_ORG_TIMEZONE "${ALMANAC_ORG_TIMEZONE:-Etc/UTC}"
    write_kv ALMANAC_ORG_QUIET_HOURS "${ALMANAC_ORG_QUIET_HOURS:-}"
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
    write_kv VAULT_WATCH_DEBOUNCE_SECONDS "${VAULT_WATCH_DEBOUNCE_SECONDS:-0.5}"
    write_kv VAULT_WATCH_MAX_BATCH_SECONDS "${VAULT_WATCH_MAX_BATCH_SECONDS:-10}"
    write_kv VAULT_WATCH_RUN_EMBED "${VAULT_WATCH_RUN_EMBED:-auto}"
    write_kv BACKUP_GIT_BRANCH "$BACKUP_GIT_BRANCH"
    write_kv BACKUP_GIT_REMOTE "$BACKUP_GIT_REMOTE"
    write_kv BACKUP_GIT_DEPLOY_KEY_PATH "${BACKUP_GIT_DEPLOY_KEY_PATH:-}"
    write_kv BACKUP_GIT_KNOWN_HOSTS_FILE "${BACKUP_GIT_KNOWN_HOSTS_FILE:-}"
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
    write_kv ALMANAC_MODEL_PRESET_CODEX "${ALMANAC_MODEL_PRESET_CODEX:-openai-codex:gpt-5.5}"
    write_kv ALMANAC_MODEL_PRESET_OPUS "${ALMANAC_MODEL_PRESET_OPUS:-anthropic:claude-opus-4-7}"
    write_kv ALMANAC_MODEL_PRESET_CHUTES "${ALMANAC_MODEL_PRESET_CHUTES:-chutes:moonshotai/Kimi-K2.6-TEE}"
    write_kv ALMANAC_ORG_PROVIDER_ENABLED "${ALMANAC_ORG_PROVIDER_ENABLED:-0}"
    write_kv ALMANAC_ORG_PROVIDER_PRESET "${ALMANAC_ORG_PROVIDER_PRESET:-}"
    write_kv ALMANAC_ORG_PROVIDER_MODEL_ID "${ALMANAC_ORG_PROVIDER_MODEL_ID:-}"
    write_kv ALMANAC_ORG_PROVIDER_REASONING_EFFORT "${ALMANAC_ORG_PROVIDER_REASONING_EFFORT:-medium}"
    write_kv ALMANAC_ORG_PROVIDER_SECRET_PROVIDER "${ALMANAC_ORG_PROVIDER_SECRET_PROVIDER:-}"
    write_kv ALMANAC_ORG_PROVIDER_SECRET "${ALMANAC_ORG_PROVIDER_SECRET:-}"
    write_kv ALMANAC_CURATOR_MODEL_PRESET "${ALMANAC_CURATOR_MODEL_PRESET:-codex}"
    write_kv ALMANAC_CURATOR_CHANNELS "${ALMANAC_CURATOR_CHANNELS:-tui-only}"
    write_kv ALMANAC_HERMES_AGENT_REF "$hermes_agent_ref"
    write_kv ALMANAC_HERMES_DOCS_SYNC_ENABLED "${ALMANAC_HERMES_DOCS_SYNC_ENABLED:-1}"
    write_kv ALMANAC_HERMES_DOCS_REPO_URL "$hermes_docs_repo_url"
    write_kv ALMANAC_HERMES_DOCS_REF "$hermes_docs_ref"
    write_kv ALMANAC_HERMES_DOCS_SOURCE_SUBDIR "${ALMANAC_HERMES_DOCS_SOURCE_SUBDIR:-website/docs}"
    write_kv ALMANAC_HERMES_DOCS_STATE_DIR "${ALMANAC_HERMES_DOCS_STATE_DIR:-$STATE_DIR/hermes-docs-src}"
    write_kv ALMANAC_HERMES_DOCS_VAULT_DIR "${ALMANAC_HERMES_DOCS_VAULT_DIR:-$VAULT_DIR/Agents_KB/hermes-agent-docs}"
    write_kv ALMANAC_EXTRA_MCP_NAME "${ALMANAC_EXTRA_MCP_NAME:-external-kb}"
    write_kv ALMANAC_EXTRA_MCP_LABEL "${ALMANAC_EXTRA_MCP_LABEL:-External knowledge rail}"
    write_kv ALMANAC_EXTRA_MCP_URL "${ALMANAC_EXTRA_MCP_URL:-}"
    write_kv ALMANAC_UPSTREAM_REPO_URL "${ALMANAC_UPSTREAM_REPO_URL:-https://github.com/example/almanac.git}"
    write_kv ALMANAC_UPSTREAM_BRANCH "${ALMANAC_UPSTREAM_BRANCH:-main}"
    write_kv ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED "${ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED:-0}"
    write_kv ALMANAC_UPSTREAM_DEPLOY_KEY_USER "${ALMANAC_UPSTREAM_DEPLOY_KEY_USER:-}"
    write_kv ALMANAC_UPSTREAM_DEPLOY_KEY_PATH "${ALMANAC_UPSTREAM_DEPLOY_KEY_PATH:-}"
    write_kv ALMANAC_UPSTREAM_KNOWN_HOSTS_FILE "${ALMANAC_UPSTREAM_KNOWN_HOSTS_FILE:-}"
    write_kv ALMANAC_AGENT_DASHBOARD_BACKEND_PORT_BASE "${ALMANAC_AGENT_DASHBOARD_BACKEND_PORT_BASE:-19000}"
    write_kv ALMANAC_AGENT_DASHBOARD_PROXY_PORT_BASE "${ALMANAC_AGENT_DASHBOARD_PROXY_PORT_BASE:-29000}"
    write_kv ALMANAC_AGENT_CODE_PORT_BASE "${ALMANAC_AGENT_CODE_PORT_BASE:-39000}"
    write_kv ALMANAC_AGENT_PORT_SLOT_SPAN "${ALMANAC_AGENT_PORT_SLOT_SPAN:-5000}"
    write_kv ALMANAC_AGENT_CODE_SERVER_IMAGE "$code_server_image"
    write_kv ALMANAC_AGENT_ENABLE_TAILSCALE_SERVE "$ENABLE_TAILSCALE_SERVE"
    write_kv ALMANAC_RELEASE_STATE_FILE "${ALMANAC_RELEASE_STATE_FILE:-$STATE_DIR/almanac-release.json}"
    write_kv ENABLE_NEXTCLOUD "$ENABLE_NEXTCLOUD"
    write_kv ENABLE_TAILSCALE_SERVE "$ENABLE_TAILSCALE_SERVE"
    write_kv TAILSCALE_SERVE_PORT "${TAILSCALE_SERVE_PORT:-443}"
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

describe_operator_channel_summary() {
  local platform="${1:-tui-only}"
  local channel_id="${2:-}"

  if [[ "$platform" == "tui-only" ]]; then
    printf '%s\n' 'tui-only'
    return 0
  fi
  if [[ -n "$channel_id" ]]; then
    printf '%s %s\n' "$platform" "$channel_id"
    return 0
  fi
  printf '%s\n' "$platform"
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
    write_kv ALMANAC_INSTALL_PODMAN "${ALMANAC_INSTALL_PODMAN:-auto}"
    write_kv ALMANAC_INSTALL_TAILSCALE "${ALMANAC_INSTALL_TAILSCALE:-auto}"
    write_kv ALMANAC_INSTALL_PUBLIC_GIT "${ALMANAC_INSTALL_PUBLIC_GIT:-0}"
    write_kv ALMANAC_ORG_PROFILE_BUILDER_ENABLED "${ALMANAC_ORG_PROFILE_BUILDER_ENABLED:-0}"
    write_kv WIPE_NEXTCLOUD_STATE "${WIPE_NEXTCLOUD_STATE:-0}"
    write_kv REMOVE_PUBLIC_REPO "${REMOVE_PUBLIC_REPO:-1}"
    write_kv REMOVE_USER_TOOLING "${REMOVE_USER_TOOLING:-1}"
    write_kv REMOVE_SERVICE_USER "${REMOVE_SERVICE_USER:-0}"
  } >"$target"
  chmod 600 "$target"
}

maybe_run_org_profile_builder() {
  local repo_dir="${1:-$BOOTSTRAP_DIR}"
  local profile_path="${ALMANAC_PRIV_CONFIG_DIR:-$ALMANAC_PRIV_DIR/config}/org-profile.yaml"

  if [[ "${ALMANAC_ORG_PROFILE_BUILDER_ENABLED:-0}" != "1" ]]; then
    return 0
  fi
  if [[ ! -t 0 ]]; then
    echo "Skipping interactive operating profile builder because stdin is not a terminal."
    return 0
  fi
  if [[ ! -x "$repo_dir/bin/org-profile-builder.sh" ]]; then
    echo "Operating profile builder is missing at $repo_dir/bin/org-profile-builder.sh" >&2
    return 1
  fi

  mkdir -p "$(dirname "$profile_path")"
  echo
  echo "Launching private operating profile builder..."
  "$repo_dir/bin/org-profile-builder.sh" --file "$profile_path"
  chmod 600 "$profile_path" >/dev/null 2>&1 || true
  if [[ ${EUID:-$(id -u)} -eq 0 && -n "${ALMANAC_USER:-}" ]]; then
    chown "$ALMANAC_USER:$ALMANAC_USER" "$profile_path" >/dev/null 2>&1 || true
  fi
}

apply_org_profile_if_present_root() {
  local profile_path="${ALMANAC_PRIV_CONFIG_DIR:-$ALMANAC_PRIV_DIR/config}/org-profile.yaml"

  if [[ ! -f "$profile_path" ]]; then
    return 0
  fi
  if [[ ! -x "$ALMANAC_REPO_DIR/bin/almanac-ctl" ]]; then
    echo "Skipping operating profile apply because almanac-ctl is not installed yet."
    return 0
  fi

  echo
  echo "Applying private operating profile..."
  run_service_user_cmd "$ALMANAC_REPO_DIR/bin/almanac-ctl" org-profile apply --file "$profile_path" --yes --actor "deploy"
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
    --exclude '/.git' \
    --exclude '/.git/' \
    --exclude '/almanac-priv/' \
    --exclude '/.almanac-operator.env' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.DS_Store' \
    "$source_dir/" "$target_dir/"

  sync_public_repo_git_metadata_from_source "$source_dir" "$target_dir"
}

sync_public_repo_git_metadata_from_source() {
  local source_dir="$1"
  local target_dir="$2"

  if [[ ! -d "$source_dir/.git" ]]; then
    return 0
  fi
  if [[ ! -d "$target_dir/.git" && "${ALMANAC_INSTALL_PUBLIC_GIT:-0}" != "1" ]]; then
    return 0
  fi

  rm -rf "$target_dir/.git"
  rsync -a --delete "$source_dir/.git/" "$target_dir/.git/"
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
  if git_remote_uses_ssh "${ALMANAC_UPSTREAM_REPO_URL:-}" && [[ "${ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED:-0}" != "1" ]]; then
    echo "Refusing SSH upstream without the Almanac upstream deploy-key lane enabled." >&2
    echo "Run ./deploy.sh install to configure ALMANAC_UPSTREAM_DEPLOY_KEY_* or use an HTTPS upstream." >&2
    return 1
  fi

  rm -rf "$checkout_dir"
  if [[ "${ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED:-0}" == "1" ]] && git_remote_uses_ssh "$ALMANAC_UPSTREAM_REPO_URL"; then
    GIT_TERMINAL_PROMPT=0 \
    GIT_ASKPASS=/bin/false \
    SSH_ASKPASS=/bin/false \
    GCM_INTERACTIVE=Never \
    GIT_SSH_COMMAND="$(upstream_git_ssh_command)" \
      git clone --depth 1 --branch "$ALMANAC_UPSTREAM_BRANCH" --single-branch \
      "$ALMANAC_UPSTREAM_REPO_URL" "$checkout_dir" >/dev/null
  else
    GIT_TERMINAL_PROMPT=0 \
    GIT_ASKPASS=/bin/false \
    SSH_ASKPASS=/bin/false \
    GCM_INTERACTIVE=Never \
      git clone --depth 1 --branch "$ALMANAC_UPSTREAM_BRANCH" --single-branch \
      "$ALMANAC_UPSTREAM_REPO_URL" "$checkout_dir" >/dev/null
  fi
}

require_main_upstream_branch_for_upgrade() {
  local branch="${ALMANAC_UPSTREAM_BRANCH:-main}"
  if [[ "$branch" == "main" || "${ALMANAC_ALLOW_NON_MAIN_UPGRADE:-0}" == "1" ]]; then
    return 0
  fi
  echo "Refusing production upgrade from non-main upstream branch: $branch" >&2
  echo "Set ALMANAC_ALLOW_NON_MAIN_UPGRADE=1 only for an explicit staging or emergency deployment." >&2
  return 1
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

refresh_upgrade_check_state_root() {
  local deployed_commit="${1:-}"
  local tracked_repo="${2:-${ALMANAC_UPSTREAM_REPO_URL:-}}"
  local tracked_branch="${3:-${ALMANAC_UPSTREAM_BRANCH:-main}}"
  if [[ -z "$deployed_commit" || -z "${ALMANAC_DB_PATH:-}" ]]; then
    return 0
  fi

  python3 - "$ALMANAC_DB_PATH" "$deployed_commit" "$tracked_repo" "$tracked_branch" <<'PY' || true
import datetime as dt
import sqlite3
import sys

db_path, deployed_commit, tracked_repo, tracked_branch = sys.argv[1:5]
now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
short = deployed_commit[:12]
note = f"up to date at {short} from {tracked_repo}#{tracked_branch} (recorded by deploy)"
conn = sqlite3.connect(db_path)
conn.execute(
    """
    CREATE TABLE IF NOT EXISTS settings (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )
    """
)
conn.execute(
    """
    CREATE TABLE IF NOT EXISTS refresh_jobs (
      job_name TEXT PRIMARY KEY,
      job_kind TEXT NOT NULL,
      target_id TEXT NOT NULL,
      schedule TEXT,
      last_run_at TEXT,
      last_status TEXT,
      last_note TEXT
    )
    """
)
for key, value in [
    ("almanac_upgrade_last_seen_sha", deployed_commit),
    ("almanac_upgrade_relation", "equal"),
]:
    conn.execute(
        """
        INSERT INTO settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (key, value, now),
    )
conn.execute(
    """
    INSERT INTO refresh_jobs (job_name, job_kind, target_id, schedule, last_run_at, last_status, last_note)
    VALUES ('almanac-upgrade-check', 'upgrade-check', 'almanac', 'every 1h', ?, 'ok', ?)
    ON CONFLICT(job_name) DO UPDATE SET
      target_id = excluded.target_id,
      schedule = excluded.schedule,
      last_run_at = excluded.last_run_at,
      last_status = excluded.last_status,
      last_note = excluded.last_note
    """,
    (now, note),
)
conn.commit()
conn.close()
PY
  chown "$ALMANAC_USER:$ALMANAC_USER" "$ALMANAC_DB_PATH" "$ALMANAC_DB_PATH"-* >/dev/null 2>&1 || true
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
  local watch_embed_mode=""

  reload_runtime_config_from_file "$CONFIG_TARGET" || true
  detect_github_repo
  resolve_agent_qmd_endpoint
  resolve_agent_control_plane_endpoint
  detect_tailscale_notion_webhook_funnel
  watch_embed_mode="$(lowercase "${VAULT_WATCH_RUN_EMBED:-}")"

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
    if [[ "$watch_embed_mode" == "1" ]]; then
      echo "  Watcher embeddings:"
      echo "    enabled"
    elif [[ "$watch_embed_mode" == "auto" ]]; then
      echo "  Watcher embeddings:"
      echo "    auto (embed only when qmd reports new pending work)"
    else
      echo "  Watcher embeddings:"
      echo "    deferred to scheduled/manual qmd refresh"
    fi
  elif [[ "$watch_embed_mode" == "1" ]]; then
    echo "  Watcher embeddings:"
    echo "    enabled"
  elif [[ "$watch_embed_mode" == "auto" ]]; then
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
      echo "    $(build_public_https_url "${TAILSCALE_DNS_NAME:-$NEXTCLOUD_TRUSTED_DOMAIN}" "${TAILSCALE_SERVE_PORT:-443}" "/")"
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
  echo "  Notion webhook receiver (local):"
  echo "    http://${ALMANAC_NOTION_WEBHOOK_HOST:-127.0.0.1}:${ALMANAC_NOTION_WEBHOOK_PORT:-8283}/notion/webhook"
  if [[ -n "${ALMANAC_NOTION_WEBHOOK_PUBLIC_URL:-}" ]]; then
    echo "  Notion webhook URL (public HTTPS):"
    echo "    ${ALMANAC_NOTION_WEBHOOK_PUBLIC_URL}"
    if [[ "$ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL" == "1" ]]; then
      echo "  Exposure:"
      echo "    public internet via Tailscale Funnel on port ${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-8443}"
      if [[ "$TAILSCALE_FUNNEL_HAS_NOTION_WEBHOOK" != "1" ]]; then
        echo "  Funnel route note:"
        echo "    config expects ${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH:-/notion/webhook}, but current tailscale funnel status does not show it yet"
      fi
    fi
    echo "  Notion webhook setup:"
    echo "    1. Open the Notion Developer Portal for this integration and go to the Webhooks tab."
    echo "    2. If a subscription already exists for this exact URL, edit that subscription."
    echo "       Do not create a second webhook subscription for the same Almanac endpoint."
    echo "    3. Use this exact event selection:"
    echo "       - Page: select all Page events"
    echo "       - Database: select all Database events"
    echo "       - Data source: select all Data source events"
    echo "       - File uploads: select all File upload events"
    echo "       - View: leave all View events unchecked"
    echo "       - Comment: leave all Comment events unchecked"
    echo "    4. Run $ALMANAC_REPO_DIR/deploy.sh notion-ssot for the full step-by-step webhook walkthrough."
    echo "       It will pause at each Notion UI step, arm the install window,"
    echo "       wait for Notion to deliver the token, print the verification_token,"
    echo "       and record operator confirmation once Notion accepts the Verify step."
  else
    echo "  Notion webhook URL (public HTTPS):"
    echo "    not configured; Notion cannot reach 127.0.0.1 without separate public ingress"
  fi
  if [[ -n "${ALMANAC_SSOT_NOTION_SPACE_URL:-}" ]]; then
    echo "  Shared Notion SSOT:"
    echo "    ${ALMANAC_SSOT_NOTION_SPACE_URL}"
    if [[ -n "${ALMANAC_SSOT_NOTION_SPACE_KIND:-}" || -n "${ALMANAC_SSOT_NOTION_SPACE_ID:-}" ]]; then
      echo "  Shared Notion target:"
      echo "    ${ALMANAC_SSOT_NOTION_SPACE_KIND:-object} ${ALMANAC_SSOT_NOTION_SPACE_ID:-}"
    fi
    echo "  Shared Notion index roots:"
    echo "    ${ALMANAC_NOTION_INDEX_ROOTS:-${ALMANAC_SSOT_NOTION_ROOT_PAGE_URL:-${ALMANAC_SSOT_NOTION_SPACE_URL:-not configured}}}"
  else
    echo "  Shared Notion SSOT:"
    echo "    not configured yet; run $ALMANAC_REPO_DIR/deploy.sh notion-ssot"
  fi
  echo "  Curator Hermes home:"
  echo "    ${ALMANAC_CURATOR_HERMES_HOME:-$STATE_DIR/curator/hermes-home}"
  echo "  Operator notification channel:"
  echo "    $(describe_operator_channel_summary "${OPERATOR_NOTIFY_CHANNEL_PLATFORM:-tui-only}" "${OPERATOR_NOTIFY_CHANNEL_ID:-}")"
  echo "  Recovery CLI:"
  echo "    $ALMANAC_REPO_DIR/bin/almanac-ctl"
  echo "  Enrollment maintenance:"
  echo "    $ALMANAC_REPO_DIR/deploy.sh enrollment-status"
  echo "    $ALMANAC_REPO_DIR/deploy.sh enrollment-align"
  echo "    $ALMANAC_REPO_DIR/deploy.sh enrollment-reset"
  echo

  echo "Almanac software updates"
  echo "  Tracked upstream:"
  echo "    ${ALMANAC_UPSTREAM_REPO_URL:-https://github.com/example/almanac.git}#${ALMANAC_UPSTREAM_BRANCH:-main}"
  echo "  Release state:"
  echo "    ${ALMANAC_RELEASE_STATE_FILE:-$STATE_DIR/almanac-release.json}"
  echo "  Upgrade command:"
  echo "    $ALMANAC_REPO_DIR/deploy.sh upgrade"
  if [[ "${ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED:-0}" == "1" ]]; then
    local upstream_repo_page="" upstream_pub_key_path="" upstream_pub_key=""
    upstream_repo_page="$(github_repo_page_from_remote "${ALMANAC_UPSTREAM_REPO_URL:-}")"
    upstream_pub_key_path="${ALMANAC_UPSTREAM_DEPLOY_KEY_PATH:-$(default_upstream_git_deploy_key_path)}.pub"
    if [[ -f "$upstream_pub_key_path" ]]; then
      upstream_pub_key="$(<"$upstream_pub_key_path")"
    fi
    echo "  Upstream deploy key:"
    echo "    ${ALMANAC_UPSTREAM_DEPLOY_KEY_PATH:-$(default_upstream_git_deploy_key_path)}"
    if [[ -n "$upstream_repo_page" ]]; then
      echo "  Add or review that deploy key here:"
      echo "    $upstream_repo_page/settings/keys"
      echo "  Enable GitHub Allow write access. This upstream deploy key is for operator/agent code pushes."
    fi
    if [[ -n "$upstream_pub_key" ]]; then
      echo "  Public key to paste into GitHub:"
      printf '    %s\n' "$upstream_pub_key"
    fi
  else
    echo "  Optional deploy key:"
    echo "    rerun install or write-config and answer yes to the Almanac upstream deploy-key prompt"
  fi
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
    local backup_repo_page="" backup_pub_key_path="" backup_pub_key=""
    backup_repo_page="$(backup_github_repo_page_from_remote "$BACKUP_GIT_REMOTE")"
    backup_pub_key_path="${BACKUP_GIT_DEPLOY_KEY_PATH:-$(default_backup_git_deploy_key_path)}.pub"
    if [[ -f "$backup_pub_key_path" ]]; then
      backup_pub_key="$(<"$backup_pub_key_path")"
    fi
    echo "  Backup remote:"
    echo "    $BACKUP_GIT_REMOTE"
    if [[ -n "$backup_repo_page" ]]; then
      echo "  Create or reuse this private GitHub repo:"
      echo "    $backup_repo_page"
      echo "  If it does not exist yet, create it as a new empty private repository."
      echo "  Then add a deploy key with write access here:"
      echo "    $backup_repo_page/settings/keys"
    fi
    echo "  Deploy key public file:"
    echo "    $backup_pub_key_path"
    if [[ -n "$backup_pub_key" ]]; then
      echo "  Public key to paste into GitHub (enable Allow write access):"
      printf '    %s\n' "$backup_pub_key"
    fi
    echo "  Backup smoke test:"
    echo "    sudo -iu $ALMANAC_USER env ALMANAC_CONFIG_FILE=\"$CONFIG_TARGET\" \"$ALMANAC_REPO_DIR/bin/backup-to-github.sh\""
  else
    echo "  Configure it on the next deploy run:"
    echo "    GitHub owner/repo for almanac-priv backup"
    echo "  Or set these values in:"
    echo "    $CONFIG_TARGET"
    echo "    BACKUP_GIT_REMOTE=git@github.com:owner/repo.git"
    echo "    BACKUP_GIT_DEPLOY_KEY_PATH=$(default_backup_git_deploy_key_path)"
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
  local -a payload_skills=(
    "almanac-qmd-mcp"
    "almanac-vault-reconciler"
    "almanac-first-contact"
    "almanac-vaults"
    "almanac-ssot"
    "almanac-notion-knowledge"
    "almanac-ssot-connect"
    "almanac-notion-mcp"
    "almanac-resources"
  )
  local skill_name=""

  detect_github_repo
  resolve_agent_qmd_endpoint
  resolve_agent_control_plane_endpoint
  echo "almanac_task_v1:"
  echo "  goal: enroll one shared-host user agent with explicit hermes setup, default Almanac skills, almanac-mcp + qmd + external MCP registration, first-contact vault defaults, and exactly one 4h refresh timer"
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
  if [[ -n "$GITHUB_REPO_OWNER_REPO" ]]; then
    echo "  skill_docs:"
    for skill_name in "${payload_skills[@]}"; do
      echo "    - \"https://raw.githubusercontent.com/$GITHUB_REPO_OWNER_REPO/$GITHUB_REPO_BRANCH/skills/$skill_name/SKILL.md\""
    done
    echo "  skill_sources_github:"
    for skill_name in "${payload_skills[@]}"; do
      echo "    - \"$GITHUB_REPO_OWNER_REPO/skills/$skill_name\""
    done
  fi
  echo "  skill_sources_local:"
  for skill_name in "${payload_skills[@]}"; do
    echo "    - \"$ALMANAC_REPO_DIR/skills/$skill_name\""
  done
  echo "  model_presets:"
  echo "    codex: \"$ALMANAC_MODEL_PRESET_CODEX\""
  echo "    opus: \"$ALMANAC_MODEL_PRESET_OPUS\""
  echo "    chutes: \"$ALMANAC_MODEL_PRESET_CHUTES\""
  echo "  actions:"
  echo "    - run hermes setup explicitly for model preset selection and optional Discord or Telegram gateway setup; keep local TUI available under the user's Unix account"
  echo "    - install default Almanac skills: qmd MCP, vault reconciler, first-contact, vaults, ssot, notion-knowledge, ssot-connect, and notion-mcp"
  echo "    - \"hermes mcp add almanac-mcp --url http://${ALMANAC_MCP_HOST:-127.0.0.1}:${ALMANAC_MCP_PORT:-8282}/mcp\""
  echo "    - \"hermes mcp add almanac-qmd --url $AGENT_QMD_URL\""
  local extra_mcp_name="${ALMANAC_EXTRA_MCP_NAME:-external-kb}"
  if [[ -n "${ALMANAC_EXTRA_MCP_URL:-}" ]]; then
    echo "    - \"hermes mcp add ${extra_mcp_name} --url ${ALMANAC_EXTRA_MCP_URL}\""
  else
    echo "    - register ${extra_mcp_name} during first contact when ALMANAC_EXTRA_MCP_URL is provided"
  fi
  echo "    - install the shipped almanac-managed-context plugin; bin/install-almanac-plugins.sh auto-enables it for Hermes homes"
  echo "    - rely on almanac-managed-context to inject Almanac MCP auth, per-intent recipe cards, and telemetry before tool dispatch"
  echo "    - do not read HERMES_HOME secrets files and do not pass token in Almanac MCP tool calls; the plugin injects the bootstrap token automatically"
  echo "    - run almanac-first-contact immediately after MCP registration"
  echo "    - first contact must resolve YAML .vault defaults, auto-subscribe every default_subscribed vault, fetch agents.managed-memory, and materialize the initial managed-memory stubs"
  echo "    - prefer the almanac-mcp recipe-card rails directly for vault catalog/subscription, shared Notion lookup, and SSOT reads/writes; shell wrappers are human fallback only"
  echo "    - install exactly one 4h refresh timer/service for the user agent, and rely on Curator fanout -> activation trigger -> user-agent-refresh for immediate stub sync after vault/catalog changes"
  echo "  memory_contract:"
  echo "    - maintain only [managed:almanac-skill-ref], [managed:vault-ref], [managed:resource-ref], [managed:qmd-ref], [managed:notion-ref], [managed:vault-topology], [managed:recall-stubs], [managed:notion-stub], [managed:today-plate]"
  echo "    - write or refresh those stubs now; MEMORY.md is a frozen snapshot at session start"
  echo "    - make [managed:almanac-skill-ref] explicit: Almanac skills are active defaults, not passive extras"
  echo "    - make [managed:resource-ref] explicit: keep the user's dashboard/code URLs plus shared Almanac rails in memory, but never store the user's credentials there"
  echo "    - make [managed:qmd-ref] explicit: qmd first for private/shared-vault questions or follow-ups from the current discussion; use mixed lex+vec retrieval"
  echo "    - make [managed:notion-ref] explicit: use shared Notion knowledge rails for indexed search/fetch context without confusing them with the governed SSOT write lane"
  echo "    - make [managed:recall-stubs] explicit: keep only high-level awareness cards and source-lane pointers; use MCP search-and-fetch for evidence and depth"
  echo "    - make [managed:notion-stub] explicit: keep verification, scope, and pending-write posture visible so the agent can predict whether writes apply or queue"
  echo "    - make [managed:today-plate] explicit: surface what is on deck for the user, due pressure, and pending approvals before exploring tools"
  if [[ "$PDF_INGEST_ENABLED" == "1" ]]; then
    echo "    - include \"$PDF_INGEST_COLLECTION_NAME\" when present, especially for newly uploaded PDFs"
  fi
  echo "    - do not store note bodies, PDF bodies, or large dumps in built-in memory"
  echo "    - do not rely on background memory review or session-end flush"
  echo "    - if cron lacks the native memory tool, patch only those nine entries in \$HERMES_HOME/memories/MEMORY.md and preserve unrelated entries plus Hermes § delimiters"
  echo "  report_contract:"
  echo "    - recurring success output: exactly 1 short line"
  echo "    - recurring warn/fail output: at most 2 short lines"
  echo "    - recurring output should say only Almanac sync, qmd indexing, memory status, and drift/blocked state"
  echo "    - preferred success form: 'Almanac health ok: sync current, qmd indexed, managed memory refreshed, drift=none.'"
  echo "  rails:"
  echo "    - prefer qmd/MCP over filesystem access; direct local qmd service or CLI is fallback only when MCP is unavailable"
  echo "    - prefer tool calls over bash mimicry; do not reach for scripts/curate-*.sh or python heredocs from a normal Hermes turn"
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
  resolve_model_provider_presets
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

  python3 - "$path" "$base" <<'PY'
import os
import sys

path = sys.argv[1]
base = sys.argv[2]

if not path or not base:
    raise SystemExit(1)

path_real = os.path.realpath(path)
base_real = os.path.realpath(base)

if path_real == base_real:
    raise SystemExit(0)

base_prefix = base_real if base_real.endswith(os.sep) else base_real + os.sep
raise SystemExit(0 if path_real.startswith(base_prefix) else 1)
PY
}

safe_remove_path() {
  local path="$1"
  local resolved=""

  if [[ -z "$path" ]]; then
    return 0
  fi

  if [[ "$path" != /* ]]; then
    echo "Refusing to remove non-absolute path: $path" >&2
    return 1
  fi

  resolved="$(python3 - "$path" <<'PY'
import os
import sys

print(os.path.realpath(sys.argv[1]))
PY
)"

  case "$resolved" in
    /|/home|/root|/usr|/etc|/var|/bin|/sbin|/lib|/lib64|/boot|/run|/opt)
      echo "Refusing to remove unsafe path: $path -> $resolved" >&2
      return 1
      ;;
  esac

  rm -rf -- "$resolved"
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

github_owner_repo_from_remote() {
  local remote="${1:-}"
  local owner_repo=""

  case "$remote" in
    https://github.com/*)
      owner_repo="${remote#https://github.com/}"
      ;;
    git@github.com:*)
      owner_repo="${remote#git@github.com:}"
      ;;
    ssh://git@github.com/*)
      owner_repo="${remote#ssh://git@github.com/}"
      ;;
    *)
      owner_repo=""
      ;;
  esac

  owner_repo="${owner_repo%.git}"
  printf '%s' "$owner_repo"
}

github_repo_page_from_remote() {
  local owner_repo=""

  owner_repo="$(github_owner_repo_from_remote "${1:-}")"
  if [[ -n "$owner_repo" ]]; then
    printf 'https://github.com/%s' "$owner_repo"
  fi
}

github_ssh_remote_from_owner_repo() {
  local owner_repo="${1:-}"

  owner_repo="${owner_repo#/}"
  owner_repo="${owner_repo%/}"
  if [[ "$owner_repo" == */* && "$owner_repo" != */ && "$owner_repo" != /* ]]; then
    printf 'git@github.com:%s.git' "$owner_repo"
  fi
}

git_remote_uses_ssh() {
  local remote="${1:-}"

  case "$remote" in
    git@*|ssh://*)
      return 0
      ;;
  esac

  return 1
}

backup_github_owner_repo_from_remote() {
  github_owner_repo_from_remote "${1:-}"
}

github_repo_visibility() {
  local owner_repo="${1:-}"
  local api_base="${GITHUB_API_BASE:-${BACKUP_GIT_GITHUB_API_BASE:-https://api.github.com}}"

  python3 - "$api_base" "$owner_repo" <<'PY'
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

base = sys.argv[1].rstrip("/")
owner_repo = sys.argv[2].strip("/")
if not owner_repo:
    print("unsupported")
    raise SystemExit(0)

request = urllib.request.Request(
    f"{base}/repos/{owner_repo}",
    headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "almanac-backup-visibility-check",
    },
)
try:
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8") or "{}")
except urllib.error.HTTPError as exc:
    if exc.code == 404:
        print("non-public-or-missing")
        raise SystemExit(0)
    print(f"error:{exc.code}")
    raise SystemExit(0)
except Exception as exc:  # noqa: BLE001
    print(f"error:{exc}")
    raise SystemExit(0)

print("private" if bool(payload.get("private")) else "public")
PY
}

require_private_github_backup_remote() {
  local remote="${1:-$BACKUP_GIT_REMOTE}"
  local owner_repo="" visibility=""

  [[ -n "$remote" ]] || return 0
  owner_repo="$(backup_github_owner_repo_from_remote "$remote")"
  if [[ -z "$owner_repo" ]]; then
    echo "almanac-priv backups currently support GitHub remotes only." >&2
    echo "Use a remote like git@github.com:owner/private-repo.git" >&2
    return 1
  fi

  visibility="$(github_repo_visibility "$owner_repo")"
  if [[ "$visibility" == "public" ]]; then
    echo "Refusing to back up almanac-priv to a public GitHub repository: $owner_repo" >&2
    return 1
  fi
  if [[ "$visibility" == error:* || "$visibility" == "unsupported" ]]; then
    echo "Could not verify GitHub visibility for $owner_repo ($visibility)." >&2
    return 1
  fi
}

backup_github_repo_page_from_remote() {
  github_repo_page_from_remote "${1:-}"
}

backup_git_remote_uses_ssh() {
  git_remote_uses_ssh "${1:-$BACKUP_GIT_REMOTE}"
}

backup_private_repo_origin_remote() {
  local repo_dir="${1:-$ALMANAC_PRIV_DIR}"

  if [[ -z "$repo_dir" || ! -d "$repo_dir/.git" ]]; then
    return 0
  fi

  git -C "$repo_dir" remote get-url origin 2>/dev/null || true
}

resolve_backup_git_remote_default() {
  local remote="${1:-${BACKUP_GIT_REMOTE:-}}"

  if [[ -n "$remote" ]]; then
    printf '%s\n' "$remote"
    return 0
  fi

  remote="$(backup_private_repo_origin_remote "${ALMANAC_PRIV_DIR:-}")"
  if [[ -n "$remote" ]]; then
    printf '%s\n' "$remote"
  fi
}

default_backup_git_deploy_key_path() {
  printf '%s' "${ALMANAC_HOME:-$(default_home_for_user "$ALMANAC_USER")}/.ssh/almanac-backup-ed25519"
}

default_backup_git_known_hosts_file() {
  printf '%s' "${ALMANAC_HOME:-$(default_home_for_user "$ALMANAC_USER")}/.ssh/almanac-backup-known_hosts"
}

upstream_deploy_key_user_default() {
  if [[ -n "${ALMANAC_UPSTREAM_DEPLOY_KEY_USER:-}" ]]; then
    printf '%s\n' "$ALMANAC_UPSTREAM_DEPLOY_KEY_USER"
    return 0
  fi
  if [[ -n "${SUDO_USER:-}" && "${SUDO_USER:-}" != "root" ]]; then
    printf '%s\n' "$SUDO_USER"
    return 0
  fi
  if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    id -un
    return 0
  fi
  printf '%s\n' "${ALMANAC_USER:-almanac}"
}

default_upstream_git_deploy_key_path() {
  local key_user="" key_home=""

  key_user="$(upstream_deploy_key_user_default)"
  if [[ "$key_user" == "${ALMANAC_USER:-}" && -n "${ALMANAC_HOME:-}" ]]; then
    key_home="$ALMANAC_HOME"
  else
    key_home="$(resolve_user_home "$key_user" 2>/dev/null || default_home_for_user "$key_user")"
  fi
  printf '%s' "$key_home/.ssh/almanac-upstream-ed25519"
}

default_upstream_git_known_hosts_file() {
  local key_path=""

  key_path="${ALMANAC_UPSTREAM_DEPLOY_KEY_PATH:-$(default_upstream_git_deploy_key_path)}"
  printf '%s' "$(dirname "$key_path")/almanac-upstream-known_hosts"
}

upstream_git_ssh_command() {
  local key_path="" known_hosts="" quoted_key="" quoted_known_hosts=""

  key_path="${ALMANAC_UPSTREAM_DEPLOY_KEY_PATH:-$(default_upstream_git_deploy_key_path)}"
  known_hosts="${ALMANAC_UPSTREAM_KNOWN_HOSTS_FILE:-$(default_upstream_git_known_hosts_file)}"
  printf -v quoted_key '%q' "$key_path"
  printf -v quoted_known_hosts '%q' "$known_hosts"
  printf 'ssh -i %s -o BatchMode=yes -o IPQoS=none -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=%s' \
    "$quoted_key" "$quoted_known_hosts"
}

collect_upstream_git_answers() {
  local default_remote="" default_owner_repo="" owner_repo="" default_enabled="" repo_page=""
  local default_key_user="" key_user=""

  default_remote="${ALMANAC_UPSTREAM_REPO_URL:-$(git_origin_url "$BOOTSTRAP_DIR")}"
  default_owner_repo="$(github_owner_repo_from_remote "$default_remote")"
  default_enabled="${ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED:-0}"
  default_key_user="${ALMANAC_UPSTREAM_DEPLOY_KEY_USER:-$(upstream_deploy_key_user_default)}"
  if [[ -n "${ALMANAC_UPSTREAM_DEPLOY_KEY_PATH:-}" && -f "${ALMANAC_UPSTREAM_DEPLOY_KEY_PATH:-}" ]]; then
    default_enabled="1"
  fi

  echo
  echo "GitHub deploy key for Almanac upstream"
  echo "  This is the read/write deploy key for operator/agent code pushes to the Almanac repo."
  echo "  The almanac-priv backup and per-user Hermes-home backups use separate deploy keys."
  echo "  In GitHub deploy key settings, enable: Allow write access."

  ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED="$(ask_yes_no "Set up an operator deploy key for the Almanac upstream repo" "$default_enabled")"
  if [[ "$ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED" != "1" ]]; then
    ALMANAC_UPSTREAM_DEPLOY_KEY_USER="${ALMANAC_UPSTREAM_DEPLOY_KEY_USER:-}"
    ALMANAC_UPSTREAM_DEPLOY_KEY_PATH="${ALMANAC_UPSTREAM_DEPLOY_KEY_PATH:-}"
    ALMANAC_UPSTREAM_KNOWN_HOSTS_FILE="${ALMANAC_UPSTREAM_KNOWN_HOSTS_FILE:-}"
    return 0
  fi

  while true; do
    owner_repo="$(ask "GitHub owner/repo for Almanac upstream deploy key" "$default_owner_repo")"
    owner_repo="${owner_repo#/}"
    owner_repo="${owner_repo%/}"
    if [[ "$owner_repo" == */* && "$owner_repo" != */ && "$owner_repo" != /* ]]; then
      ALMANAC_UPSTREAM_REPO_URL="$(github_ssh_remote_from_owner_repo "$owner_repo")"
      key_user="$(ask "Unix user that should own the Almanac repo push deploy key" "$default_key_user")"
      if [[ "$key_user" != "${ALMANAC_UPSTREAM_DEPLOY_KEY_USER:-}" ]]; then
        ALMANAC_UPSTREAM_DEPLOY_KEY_USER="$key_user"
        ALMANAC_UPSTREAM_DEPLOY_KEY_PATH="$(default_upstream_git_deploy_key_path)"
        ALMANAC_UPSTREAM_KNOWN_HOSTS_FILE="$(default_upstream_git_known_hosts_file)"
      else
        ALMANAC_UPSTREAM_DEPLOY_KEY_USER="$key_user"
        ALMANAC_UPSTREAM_DEPLOY_KEY_PATH="${ALMANAC_UPSTREAM_DEPLOY_KEY_PATH:-$(default_upstream_git_deploy_key_path)}"
        ALMANAC_UPSTREAM_KNOWN_HOSTS_FILE="${ALMANAC_UPSTREAM_KNOWN_HOSTS_FILE:-$(default_upstream_git_known_hosts_file)}"
      fi
      key_user="$ALMANAC_UPSTREAM_DEPLOY_KEY_USER"
      repo_page="$(github_repo_page_from_remote "$ALMANAC_UPSTREAM_REPO_URL")"
      echo "  Upstream SSH remote:"
      echo "    $ALMANAC_UPSTREAM_REPO_URL"
      echo "  Key owner on this host:"
      echo "    $key_user"
      echo "  Deploy key public file:"
      echo "    ${ALMANAC_UPSTREAM_DEPLOY_KEY_PATH}.pub"
      if [[ -n "$repo_page" ]]; then
        echo "  Add the public key to GitHub here:"
        echo "    $repo_page/settings/keys"
        echo "  Required GitHub setting:"
        echo "    Enable Allow write access."
      fi
      if id -u "$key_user" >/dev/null 2>&1; then
        ensure_upstream_git_deploy_key_material_for_user "$key_user"
        print_upstream_deploy_key_public_key
        prompt_and_verify_upstream_deploy_key_access
      else
        echo "  Public key:"
        echo "    Will be generated after Unix user '$key_user' exists on this host."
        echo "    Re-run deploy.sh, or run upgrade after creating the user, to print and verify it."
      fi
      return 0
    fi
    echo "Please enter GitHub owner/repo, for example example/almanac."
  done
}

ensure_upstream_git_deploy_key_material_for_user() {
  local key_user="${1:-$(upstream_deploy_key_user_default)}"
  local key_path="" pub_path="" key_dir="" known_hosts="" key_comment="" quoted_key="" quoted_pub="" quoted_dir="" quoted_known_hosts=""
  local key_script=""

  if [[ "${ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED:-0}" != "1" ]]; then
    return 0
  fi
  if ! git_remote_uses_ssh "${ALMANAC_UPSTREAM_REPO_URL:-}"; then
    return 0
  fi

  key_path="${ALMANAC_UPSTREAM_DEPLOY_KEY_PATH:-$(default_upstream_git_deploy_key_path)}"
  pub_path="${key_path}.pub"
  key_dir="$(dirname "$key_path")"
  known_hosts="${ALMANAC_UPSTREAM_KNOWN_HOSTS_FILE:-$(default_upstream_git_known_hosts_file)}"
  key_comment="almanac-upstream@$(hostname -f 2>/dev/null || hostname)"

  printf -v quoted_key '%q' "$key_path"
  printf -v quoted_pub '%q' "$pub_path"
  printf -v quoted_dir '%q' "$key_dir"
  printf -v quoted_known_hosts '%q' "$known_hosts"

  key_script="
    set -e
    mkdir -p $quoted_dir
    chmod 700 $quoted_dir
    if [[ ! -f $quoted_key ]]; then
      ssh-keygen -q -t ed25519 -N '' -C $(printf '%q' "$key_comment") -f $quoted_key
    elif [[ ! -f $quoted_pub ]]; then
      ssh-keygen -y -f $quoted_key > $quoted_pub
    fi
    chmod 600 $quoted_key
    chmod 644 $quoted_pub
    touch $quoted_known_hosts
    chmod 644 $quoted_known_hosts
    ssh-keyscan github.com >> $quoted_known_hosts 2>/dev/null || true
    sort -u -o $quoted_known_hosts $quoted_known_hosts 2>/dev/null || true
  "

  if [[ "$(id -un)" == "$key_user" ]]; then
    bash -lc "$key_script"
  else
    run_as_user "$key_user" "$key_script"
  fi
}

ensure_upstream_git_deploy_key_material_root() {
  local key_user=""

  if [[ "${ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED:-0}" != "1" ]]; then
    return 0
  fi
  key_user="${ALMANAC_UPSTREAM_DEPLOY_KEY_USER:-$(upstream_deploy_key_user_default)}"
  if ! id -u "$key_user" >/dev/null 2>&1; then
    echo "Configured Almanac upstream deploy key user '$key_user' does not exist on this host." >&2
    return 1
  fi
  ensure_upstream_git_deploy_key_material_for_user "$key_user"
}

print_upstream_deploy_key_public_key() {
  local pub_path="" pub_key=""

  if [[ "${ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED:-0}" != "1" ]]; then
    return 0
  fi

  pub_path="${ALMANAC_UPSTREAM_DEPLOY_KEY_PATH:-$(default_upstream_git_deploy_key_path)}.pub"
  if [[ ! -f "$pub_path" ]]; then
    echo "  Public key to paste into GitHub:"
    echo "    Not generated yet: $pub_path"
    return 1
  fi

  pub_key="$(<"$pub_path")"
  echo "  Public key to paste into GitHub as a deploy key:"
  printf '    %s\n' "$pub_key"
}

print_upstream_deploy_key_instructions() {
  local repo_page="" pub_path=""

  if [[ "${ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED:-0}" != "1" ]]; then
    return 0
  fi

  pub_path="${ALMANAC_UPSTREAM_DEPLOY_KEY_PATH:-$(default_upstream_git_deploy_key_path)}.pub"
  repo_page="$(github_repo_page_from_remote "${ALMANAC_UPSTREAM_REPO_URL:-}")"
  echo
  echo "Almanac upstream deploy key"
  echo "  SSH remote:"
  echo "    ${ALMANAC_UPSTREAM_REPO_URL:-}"
  echo "  Key owner:"
  echo "    ${ALMANAC_UPSTREAM_DEPLOY_KEY_USER:-$(upstream_deploy_key_user_default)}"
  echo "  Public key file:"
  echo "    $pub_path"
  if [[ -n "$repo_page" ]]; then
    echo "  Add it to GitHub here:"
    echo "    $repo_page/settings/keys"
    echo "  Required GitHub setting: enable Allow write access."
  fi
  print_upstream_deploy_key_public_key
}

configure_upstream_git_for_repo() {
  local repo_dir="${1:-}"
  local ssh_command=""

  if [[ "${ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED:-0}" != "1" ]]; then
    return 0
  fi
  if [[ -z "$repo_dir" || ! -d "$repo_dir/.git" ]]; then
    return 0
  fi
  if ! git_remote_uses_ssh "${ALMANAC_UPSTREAM_REPO_URL:-}"; then
    return 0
  fi

  ssh_command="$(upstream_git_ssh_command)"
  if git -C "$repo_dir" remote get-url origin >/dev/null 2>&1; then
    git -C "$repo_dir" remote set-url origin "$ALMANAC_UPSTREAM_REPO_URL"
  else
    git -C "$repo_dir" remote add origin "$ALMANAC_UPSTREAM_REPO_URL"
  fi
  git -C "$repo_dir" config core.sshCommand "$ssh_command"
}

verify_upstream_git_deploy_key_access() {
  local remote="" ssh_command="" branch="" tmp_dir="" output="" write_ref=""

  if [[ "${ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED:-0}" != "1" ]]; then
    return 0
  fi

  remote="${ALMANAC_UPSTREAM_REPO_URL:-}"
  if ! git_remote_uses_ssh "$remote"; then
    return 0
  fi

  if [[ ! -f "${ALMANAC_UPSTREAM_DEPLOY_KEY_PATH:-$(default_upstream_git_deploy_key_path)}" ]]; then
    echo "Almanac upstream deploy key private file is missing; cannot verify GitHub access." >&2
    return 1
  fi
  if [[ ! -f "${ALMANAC_UPSTREAM_KNOWN_HOSTS_FILE:-$(default_upstream_git_known_hosts_file)}" ]]; then
    echo "Almanac upstream deploy key known_hosts file is missing; cannot verify GitHub access." >&2
    return 1
  fi

  ssh_command="$(upstream_git_ssh_command)"

  echo "  Verifying deploy-key read access with git ls-remote..."
  if ! output="$(GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/bin/false SSH_ASKPASS=/bin/false GCM_INTERACTIVE=Never GIT_SSH_COMMAND="$ssh_command" git ls-remote "$remote" HEAD 2>&1)"; then
    echo "$output" >&2
    echo "GitHub deploy-key read check failed for $remote." >&2
    return 1
  fi
  echo "  Read check passed."

  branch="${ALMANAC_UPSTREAM_BRANCH:-main}"
  write_ref="refs/heads/$branch"
  tmp_dir="$(mktemp -d)"
  if ! (
    set -e
    GIT_TERMINAL_PROMPT=0 \
    GIT_ASKPASS=/bin/false \
    SSH_ASKPASS=/bin/false \
    GCM_INTERACTIVE=Never \
    GIT_SSH_COMMAND="$ssh_command" \
      git clone --depth 1 --branch "$branch" --single-branch "$remote" "$tmp_dir" >/dev/null
    git -C "$tmp_dir" config user.name "Almanac Deploy Key Check"
    git -C "$tmp_dir" config user.email "almanac-deploy-key-check@localhost"
    printf 'Almanac deploy key write check for %s at %s\n' "$branch" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$tmp_dir/.almanac-deploy-key-write-check"
    git -C "$tmp_dir" add .almanac-deploy-key-write-check
    git -C "$tmp_dir" commit -m "Almanac deploy key write check" >/dev/null
  ); then
    rm -rf "$tmp_dir"
    echo "Failed to prepare a temporary dry-run push repo for deploy-key verification." >&2
    return 1
  fi

  echo "  Verifying deploy-key write access with git push --dry-run..."
  if ! output="$(GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/bin/false SSH_ASKPASS=/bin/false GCM_INTERACTIVE=Never GIT_SSH_COMMAND="$ssh_command" git -C "$tmp_dir" push --dry-run "$remote" "HEAD:$write_ref" 2>&1)"; then
    rm -rf "$tmp_dir"
    echo "$output" >&2
    echo "GitHub deploy-key write check failed for $remote." >&2
    echo "Make sure the deploy key is added to the repo and Allow write access is enabled." >&2
    return 1
  fi
  rm -rf "$tmp_dir"
  echo "  Write check passed (dry-run only; no branch or commit was pushed)."
}

rotate_upstream_git_deploy_key_material() {
  local key_user="" key_path="" pub_path="" quoted_key="" quoted_pub=""

  key_user="${ALMANAC_UPSTREAM_DEPLOY_KEY_USER:-$(upstream_deploy_key_user_default)}"
  key_path="${ALMANAC_UPSTREAM_DEPLOY_KEY_PATH:-$(default_upstream_git_deploy_key_path)}"
  pub_path="${key_path}.pub"

  printf -v quoted_key '%q' "$key_path"
  printf -v quoted_pub '%q' "$pub_path"

  echo "  Removing the existing key files:"
  echo "    $key_path"
  echo "    $pub_path"
  if [[ "$(id -un)" == "$key_user" ]]; then
    bash -lc "rm -f -- $quoted_key $quoted_pub"
  else
    run_as_user "$key_user" "rm -f -- $quoted_key $quoted_pub"
  fi
  ensure_upstream_git_deploy_key_material_for_user "$key_user"
  echo "  Generated a new Almanac upstream deploy key. Remove the previous deploy key entry from GitHub and add the new public key below."
}

prompt_and_verify_upstream_deploy_key_access() {
  local pub_path="" repo_page="" retry="" reuse=""

  if [[ "${ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED:-0}" != "1" ]]; then
    return 0
  fi
  if [[ "${ALMANAC_UPSTREAM_DEPLOY_KEY_ACCESS_VERIFIED:-0}" == "1" ]]; then
    return 0
  fi

  pub_path="${ALMANAC_UPSTREAM_DEPLOY_KEY_PATH:-$(default_upstream_git_deploy_key_path)}.pub"
  repo_page="$(github_repo_page_from_remote "${ALMANAC_UPSTREAM_REPO_URL:-}")"
  if [[ ! -t 0 || -z "$repo_page" || ! -f "$pub_path" ]]; then
    return 0
  fi

  # Pre-flight: if the existing key already authenticates against GitHub for
  # both read and dry-run write, mirror the "Reuse existing" pattern used for
  # org-provided credentials and let the operator skip the manual paste step.
  if verify_upstream_git_deploy_key_access >/dev/null 2>&1; then
    echo
    echo "  Detected an existing Almanac upstream deploy key with verified GitHub read+write access."
    reuse="$(ask_yes_no "Reuse existing Almanac upstream deploy key" "1")"
    if [[ "$reuse" == "1" ]]; then
      ALMANAC_UPSTREAM_DEPLOY_KEY_ACCESS_VERIFIED=1
      return 0
    fi
    echo
    rotate_upstream_git_deploy_key_material
    print_upstream_deploy_key_public_key
  fi

  echo
  read -r -p "Press ENTER after adding this deploy key in GitHub with Allow write access, or Ctrl-C to stop: " _
  while true; do
    if verify_upstream_git_deploy_key_access; then
      ALMANAC_UPSTREAM_DEPLOY_KEY_ACCESS_VERIFIED=1
      return 0
    fi
    echo
    echo "The deploy key is not ready yet. GitHub must accept both read and dry-run write access before deploy continues."
    retry="$(ask_yes_no "Retry the upstream deploy key access check after fixing GitHub settings" "1")"
    if [[ "$retry" != "1" ]]; then
      echo "Cannot continue with upstream deploy-key setup enabled until GitHub access verifies." >&2
      return 1
    fi
    read -r -p "Press ENTER after fixing the deploy key in GitHub: " _
  done
}

prepare_operator_upstream_deploy_key_before_sudo() {
  if [[ "${ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED:-0}" != "1" ]]; then
    return 0
  fi
  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    return 0
  fi

  ensure_upstream_git_deploy_key_material_for_user "${ALMANAC_UPSTREAM_DEPLOY_KEY_USER:-$(upstream_deploy_key_user_default)}"
  configure_upstream_git_for_repo "$BOOTSTRAP_DIR"
  print_upstream_deploy_key_instructions
  prompt_and_verify_upstream_deploy_key_access
}

normalize_org_provider_preset() {
  local value
  value="$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')"
  value="${value//[ _-]/}"
  case "$value" in
    1|chute|chutes|chutesai)
      printf '%s' "chutes"
      ;;
    2|codex|openai|openaicodex)
      printf '%s' "codex"
      ;;
    3|opus|claude|anthropic|claudeopus)
      printf '%s' "opus"
      ;;
    *)
      return 1
      ;;
  esac
}

normalize_org_reasoning_effort() {
  local value
  value="$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')"
  value="${value//[ _-]/}"
  case "$value" in
    ""|default|recommended|normal|standard|medium|med)
      printf '%s' "medium"
      ;;
    xhigh|extra|extrahigh|veryhigh|max|maximum)
      printf '%s' "xhigh"
      ;;
    high|low|minimal|none)
      printf '%s' "$value"
      ;;
    off|disabled|disable|no|false)
      printf '%s' "none"
      ;;
    *)
      return 1
      ;;
  esac
}

org_provider_default_model_id() {
  local preset="$1"
  local configured=""
  case "$preset" in
    codex)
      configured="$(model_provider_resolve_target_or_default codex "${ALMANAC_MODEL_PRESET_CODEX:-}" "openai-codex:gpt-5.5")"
      configured="${configured#*:}"
      ;;
    opus)
      configured="$(model_provider_resolve_target_or_default opus "${ALMANAC_MODEL_PRESET_OPUS:-}" "anthropic:claude-opus-4-7")"
      configured="${configured#*:}"
      ;;
    chutes|*)
      configured="$(model_provider_resolve_target_or_default chutes "${ALMANAC_MODEL_PRESET_CHUTES:-}" "chutes:moonshotai/Kimi-K2.6-TEE")"
      configured="${configured#*:}"
      ;;
  esac
  printf '%s' "$configured"
}

mint_org_codex_secret() {
  PYTHONPATH="$BOOTSTRAP_DIR/python${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
import json
import sys
import time

from almanac_onboarding_provider_auth import poll_codex_device_authorization, start_codex_device_authorization

state = start_codex_device_authorization()
print("OpenAI Codex sign-in for the organization-provided default:", file=sys.stderr)
print(f"1. Open {state.get('verification_url')}", file=sys.stderr)
print(f"2. Enter this code: {state.get('user_code')}", file=sys.stderr)
print("Waiting for approval...", file=sys.stderr)

while True:
    time.sleep(max(3, int(state.get("poll_interval") or 5)))
    token_payload, state = poll_codex_device_authorization(state)
    if token_payload is not None:
        print(json.dumps(token_payload, sort_keys=True))
        raise SystemExit(0)
    status = str(state.get("status") or "pending")
    if status in {"error", "expired"}:
        print(state.get("error_message") or f"Codex authorization ended with {status}.", file=sys.stderr)
        raise SystemExit(1)
PY
}

mint_org_opus_secret() {
  PYTHONPATH="$BOOTSTRAP_DIR/python${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
import sys

from almanac_onboarding_provider_auth import complete_anthropic_pkce_authorization, start_anthropic_pkce_authorization

state = start_anthropic_pkce_authorization()
print("Claude Code OAuth for the organization-provided default:", file=sys.stderr)
print("Open this link with the Claude account and plan to share with onboarded lanes:", file=sys.stderr)
print(state.get("auth_url") or "", file=sys.stderr)
callback = input("Paste the Claude callback code string here: ").strip()
secret, _updated_state = complete_anthropic_pkce_authorization(state, callback)
print(secret)
PY
}

collect_org_provider_answers() {
  local default_enabled="${ALMANAC_ORG_PROVIDER_ENABLED:-1}"
  local provider_answer="" provider_preset="" default_model="" reasoning_answer=""
  local existing_secret_provider="${ALMANAC_ORG_PROVIDER_SECRET_PROVIDER:-}"
  local reuse_secret="0"

  if [[ ! -t 0 && "${ALMANAC_ORG_PROVIDER_PROMPT_NONINTERACTIVE:-0}" != "1" ]]; then
    if [[ "${ALMANAC_ORG_PROVIDER_ENABLED:-0}" == "1" && -n "${ALMANAC_ORG_PROVIDER_SECRET:-}" ]]; then
      return 0
    fi
    ALMANAC_ORG_PROVIDER_ENABLED="0"
    return 0
  fi

  ALMANAC_ORG_PROVIDER_ENABLED="$(ask_yes_no "Provide an organization-wide inference provider/default model for onboarded users" "$default_enabled")"
  if [[ "$ALMANAC_ORG_PROVIDER_ENABLED" != "1" ]]; then
    ALMANAC_ORG_PROVIDER_PRESET=""
    ALMANAC_ORG_PROVIDER_MODEL_ID=""
    ALMANAC_ORG_PROVIDER_REASONING_EFFORT="medium"
    ALMANAC_ORG_PROVIDER_SECRET_PROVIDER=""
    ALMANAC_ORG_PROVIDER_SECRET=""
    return 0
  fi

  cat <<EOF
Organization-wide inference provider:
  1) chutes - Chutes API key + default model id
  2) codex  - OpenAI Codex sign-in link + default model id
  3) opus   - Claude Opus OAuth link + default model id
EOF
  while true; do
    provider_answer="$(ask "Org inference provider" "${ALMANAC_ORG_PROVIDER_PRESET:-chutes}")"
    if provider_preset="$(normalize_org_provider_preset "$provider_answer")"; then
      break
    fi
    echo "Choose chutes, codex, or opus."
  done

  ALMANAC_ORG_PROVIDER_PRESET="$provider_preset"
  default_model="${ALMANAC_ORG_PROVIDER_MODEL_ID:-$(org_provider_default_model_id "$provider_preset")}"
  ALMANAC_ORG_PROVIDER_MODEL_ID="$(ask "Org default model id" "$default_model")"

  while true; do
    reasoning_answer="$(ask "Org default reasoning effort (xhigh/high/medium/low/minimal/none)" "${ALMANAC_ORG_PROVIDER_REASONING_EFFORT:-medium}")"
    if ALMANAC_ORG_PROVIDER_REASONING_EFFORT="$(normalize_org_reasoning_effort "$reasoning_answer")"; then
      break
    fi
    echo "Choose xhigh, high, medium, low, minimal, or none."
  done

  if [[ -n "${ALMANAC_ORG_PROVIDER_SECRET:-}" && "$existing_secret_provider" == "$provider_preset" ]]; then
    reuse_secret="$(ask_yes_no "Reuse existing org-provided $provider_preset credential" "1")"
  fi
  if [[ "$reuse_secret" == "1" ]]; then
    ALMANAC_ORG_PROVIDER_SECRET_PROVIDER="$provider_preset"
    return 0
  fi

  ALMANAC_ORG_PROVIDER_SECRET=""
  case "$provider_preset" in
    chutes)
      while [[ -z "${ALMANAC_ORG_PROVIDER_SECRET:-}" ]]; do
        ALMANAC_ORG_PROVIDER_SECRET="$(ask_secret_keep_default "Chutes API key for org-provided agents (ENTER keeps current)" "")"
        if [[ -z "$ALMANAC_ORG_PROVIDER_SECRET" ]]; then
          echo "A Chutes API key is required for org-provided Chutes."
        fi
      done
      ;;
    codex)
      ALMANAC_ORG_PROVIDER_SECRET="$(mint_org_codex_secret)"
      ;;
    opus)
      ALMANAC_ORG_PROVIDER_SECRET="$(mint_org_opus_secret)"
      ;;
  esac
  ALMANAC_ORG_PROVIDER_SECRET_PROVIDER="$provider_preset"
}

collect_backup_git_answers() {
  local default_owner_repo="" owner_repo="" repo_page="" default_remote=""

  default_remote="$(resolve_backup_git_remote_default "${BACKUP_GIT_REMOTE:-}")"
  default_owner_repo="$(backup_github_owner_repo_from_remote "$default_remote")"

  echo
  echo "GitHub backup for almanac-priv"
  echo "  Almanac can push the private repo to a private GitHub repository using a deploy-only SSH key."
  echo "  Deploy will generate that key on this host and print the public key for you to paste into GitHub."
  echo "  In GitHub deploy key settings, enable: Allow write access."

  while true; do
    owner_repo="$(ask "GitHub owner/repo for almanac-priv backup (blank to skip)" "$default_owner_repo")"
    owner_repo="${owner_repo#/}"
    owner_repo="${owner_repo%/}"

    if [[ -z "$owner_repo" ]]; then
      BACKUP_GIT_REMOTE=""
      BACKUP_GIT_DEPLOY_KEY_PATH="${BACKUP_GIT_DEPLOY_KEY_PATH:-$(default_backup_git_deploy_key_path)}"
      BACKUP_GIT_KNOWN_HOSTS_FILE="${BACKUP_GIT_KNOWN_HOSTS_FILE:-$(default_backup_git_known_hosts_file)}"
      return 0
    fi

    if [[ "$owner_repo" == */* && "$owner_repo" != */ && "$owner_repo" != /* ]]; then
      BACKUP_GIT_REMOTE="git@github.com:${owner_repo}.git"
      BACKUP_GIT_DEPLOY_KEY_PATH="${BACKUP_GIT_DEPLOY_KEY_PATH:-$(default_backup_git_deploy_key_path)}"
      BACKUP_GIT_KNOWN_HOSTS_FILE="${BACKUP_GIT_KNOWN_HOSTS_FILE:-$(default_backup_git_known_hosts_file)}"
      require_private_github_backup_remote "$BACKUP_GIT_REMOTE"
      repo_page="$(backup_github_repo_page_from_remote "$BACKUP_GIT_REMOTE")"
      echo "  Repo to create or reuse:"
      echo "    $repo_page"
      return 0
    fi

    echo "Please enter GitHub owner/repo, for example acme/almanac-priv, or leave it blank to skip."
  done
}

ensure_backup_git_deploy_key_material_root() {
  local key_path="" pub_path="" key_dir="" pub_contents="" key_comment="" quoted_key="" quoted_pub=""

  if [[ -z "${BACKUP_GIT_REMOTE:-}" ]] || ! backup_git_remote_uses_ssh "$BACKUP_GIT_REMOTE"; then
    return 0
  fi

  key_path="${BACKUP_GIT_DEPLOY_KEY_PATH:-$(default_backup_git_deploy_key_path)}"
  pub_path="${key_path}.pub"
  key_dir="$(dirname "$key_path")"
  key_comment="almanac-backup@$(hostname -f 2>/dev/null || hostname)"

  printf -v quoted_key '%q' "$key_path"
  printf -v quoted_pub '%q' "$pub_path"

  run_as_user "$ALMANAC_USER" "
    mkdir -p $(printf '%q' "$key_dir")
    chmod 700 $(printf '%q' "$key_dir")
    if [[ ! -f $quoted_key ]]; then
      ssh-keygen -q -t ed25519 -N '' -C $(printf '%q' "$key_comment") -f $quoted_key
    elif [[ ! -f $quoted_pub ]]; then
      ssh-keygen -y -f $quoted_key > $quoted_pub
    fi
    chmod 600 $quoted_key
    chmod 644 $quoted_pub
  "
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
  local current_postgres_password="" current_nextcloud_admin_password=""
  local nextcloud_state_present="0"
  local line=""

  load_detected_config || true

  echo "Almanac deploy: install / repair from current checkout"
  echo

  detected_user="${ALMANAC_USER:-}"
  detected_home="${ALMANAC_HOME:-}"
  detected_repo="${ALMANAC_REPO_DIR:-}"
  detected_priv="${ALMANAC_PRIV_DIR:-}"
  detected_git_name="${BACKUP_GIT_AUTHOR_NAME:-}"
  detected_git_email="${BACKUP_GIT_AUTHOR_EMAIL:-}"
  while IFS= read -r line; do
    artifact_hints+=("$line")
  done < <(read_operator_artifact_hints || true)
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
    default_home="$(default_home_for_user "$ALMANAC_USER")"
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
  default_tailscale_serve_port="${TAILSCALE_SERVE_PORT:-443}"
  default_enable_tailscale_notion_webhook_funnel="${ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL:-0}"
  default_tailscale_operator_user="${TAILSCALE_OPERATOR_USER:-${SUDO_USER:-}}"
  default_tailscale_notion_webhook_funnel_port="${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-8443}"
  default_tailscale_notion_webhook_funnel_path="$(normalize_http_path "${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH:-/notion/webhook}")"
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

  ALMANAC_NAME="almanac"
  ALMANAC_HOME="$(ask "Service home" "$default_home")"
  ALMANAC_REPO_DIR="$(ask "Public repo path" "$default_repo")"
  ALMANAC_PRIV_DIR="$(ask "Private repo path" "$default_priv")"
  ALMANAC_ORG_NAME="$(normalize_optional_answer "$(ask "Organization name (type none to clear)" "${ALMANAC_ORG_NAME:-}")")"
  ALMANAC_ORG_MISSION="$(normalize_optional_answer "$(ask "Organization mission (type none to clear)" "${ALMANAC_ORG_MISSION:-}")")"
  ALMANAC_ORG_PRIMARY_PROJECT="$(normalize_optional_answer "$(ask "Primary project or focus (type none to clear)" "${ALMANAC_ORG_PRIMARY_PROJECT:-}")")"
  ALMANAC_ORG_TIMEZONE="$(ask_validated_optional "Organization timezone (IANA, e.g. America/New_York; type none to clear)" "${ALMANAC_ORG_TIMEZONE:-Etc/UTC}" validate_org_timezone "Please enter a valid IANA timezone like America/New_York or type none.")"
  ALMANAC_ORG_QUIET_HOURS="$(ask_validated_optional "Organization quiet hours in local time (HH:MM-HH:MM, optional note; type none to clear)" "${ALMANAC_ORG_QUIET_HOURS:-}" validate_org_quiet_hours "Please enter quiet hours like 22:00-08:00 or 22:00-08:00 weekdays, or type none.")"
  collect_org_provider_answers
  ALMANAC_PRIV_CONFIG_DIR="$ALMANAC_PRIV_DIR/config"
  VAULT_DIR="$ALMANAC_PRIV_DIR/vault"
  STATE_DIR="$ALMANAC_PRIV_DIR/state"
  NEXTCLOUD_STATE_DIR="$STATE_DIR/nextcloud"
  RUNTIME_DIR="$STATE_DIR/runtime"
  PUBLISHED_DIR="$ALMANAC_PRIV_DIR/published"
  ALMANAC_RELEASE_STATE_FILE="${ALMANAC_RELEASE_STATE_FILE:-$STATE_DIR/almanac-release.json}"
  local default_org_profile_builder="0"
  if [[ ! -f "$ALMANAC_PRIV_CONFIG_DIR/org-profile.yaml" ]]; then
    default_org_profile_builder="1"
  fi
  if [[ ! -t 0 ]]; then
    default_org_profile_builder="0"
  fi
  ALMANAC_ORG_PROFILE_BUILDER_ENABLED="$(ask_yes_no "Build or edit the private operating profile interactively now" "$default_org_profile_builder")"
  QMD_INDEX_NAME="almanac"
  QMD_COLLECTION_NAME="vault"
  QMD_RUN_EMBED="1"
  QMD_MCP_PORT="${QMD_MCP_PORT:-8181}"
  BACKUP_GIT_BRANCH="${BACKUP_GIT_BRANCH:-main}"
  ALMANAC_UPSTREAM_REPO_URL="${ALMANAC_UPSTREAM_REPO_URL:-https://github.com/example/almanac.git}"
  ALMANAC_UPSTREAM_BRANCH="${ALMANAC_UPSTREAM_BRANCH:-main}"
  collect_upstream_git_answers
  ALMANAC_INSTALL_PUBLIC_GIT="$(ask_yes_no "Initialize the public repo as git if needed" "$default_install_public_git")"
  collect_backup_git_answers
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
  NEXTCLOUD_VAULT_MOUNT_POINT="${NEXTCLOUD_VAULT_MOUNT_POINT:-/Vault}"
  ENABLE_NEXTCLOUD="$(ask_yes_no "Enable Nextcloud" "$default_enable_nextcloud")"
  if [[ "$ENABLE_NEXTCLOUD" == "1" ]]; then
    ENABLE_TAILSCALE_SERVE="$(ask_yes_no "Enable Tailscale HTTPS proxy for Nextcloud (tailnet only)" "$default_enable_tailscale_serve")"
  else
    ENABLE_TAILSCALE_SERVE="0"
  fi
  if [[ -n "$TAILSCALE_DNS_NAME" || -n "$TAILSCALE_TAILNET" || "${ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL:-0}" == "1" ]]; then
    ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL="$(ask_yes_no "Enable public Tailscale Funnel for the Notion webhook only" "$default_enable_tailscale_notion_webhook_funnel")"
    if [[ "$ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL" == "1" ]]; then
      TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT="$(ask "Public Tailscale Funnel HTTPS port for the Notion webhook" "$default_tailscale_notion_webhook_funnel_port")"
      TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH="$(normalize_http_path "$(ask "Public Tailscale Funnel path for the Notion webhook" "$default_tailscale_notion_webhook_funnel_path")")"
    else
      TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT="$default_tailscale_notion_webhook_funnel_port"
      TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH="$default_tailscale_notion_webhook_funnel_path"
    fi
  else
    ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL="0"
    TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT="$default_tailscale_notion_webhook_funnel_port"
    TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH="$default_tailscale_notion_webhook_funnel_path"
  fi
  if [[ "$ENABLE_TAILSCALE_SERVE" == "1" ]]; then
    if [[ "$ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL" == "1" && "${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-8443}" == "$default_tailscale_serve_port" ]]; then
      default_tailscale_serve_port="8445"
    fi
    TAILSCALE_SERVE_PORT="$(ask "Tailnet-only Tailscale HTTPS port for Nextcloud and internal MCP routes" "$default_tailscale_serve_port")"
  else
    TAILSCALE_SERVE_PORT="$default_tailscale_serve_port"
  fi
  if [[ "$ENABLE_TAILSCALE_SERVE" == "1" && "$ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL" == "1" && "${TAILSCALE_SERVE_PORT:-443}" == "${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-443}" ]]; then
    echo "Tailscale Serve and the public Notion webhook Funnel cannot share the same HTTPS port." >&2
    echo "Choose different values for the private tailnet port and the public webhook port." >&2
    return 1
  fi
  if [[ "$ENABLE_TAILSCALE_SERVE" == "1" || "$ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL" == "1" ]]; then
    TAILSCALE_OPERATOR_USER="$(ask "Tailscale operator user for serve/funnel management" "$default_tailscale_operator_user")"
  else
    TAILSCALE_OPERATOR_USER=""
  fi
  if [[ "$MODE" != "write-config" ]]; then
    collect_host_dependency_answers
  fi
  WIPE_NEXTCLOUD_STATE="0"
  if nextcloud_state_has_existing_data; then
    nextcloud_state_present="1"
  fi
  if [[ "$MODE" != "write-config" && "$ENABLE_NEXTCLOUD" == "1" && "$nextcloud_state_present" == "1" ]]; then
    echo "Detected existing Nextcloud state under:"
    echo "  $NEXTCLOUD_STATE_DIR"
    echo "This wipes Nextcloud app/db/data state only; the vault stays untouched."
    WIPE_NEXTCLOUD_STATE="$(ask_yes_no "Wipe existing Nextcloud state for a clean install" "0")"
  fi
  current_postgres_password="${POSTGRES_PASSWORD:-${MARIADB_PASSWORD:-}}"
  if [[ -z "$current_postgres_password" || "$nextcloud_state_present" != "1" || "$WIPE_NEXTCLOUD_STATE" == "1" ]]; then
    POSTGRES_PASSWORD="$(preserve_or_randomize_secret "$current_postgres_password")"
  else
    POSTGRES_PASSWORD="$current_postgres_password"
  fi
  NEXTCLOUD_ADMIN_USER="$(ask "Nextcloud admin user" "$default_nextcloud_admin_user")"
  current_nextcloud_admin_password="${NEXTCLOUD_ADMIN_PASSWORD:-}"
  if [[ -z "$current_nextcloud_admin_password" || "$nextcloud_state_present" != "1" || "$WIPE_NEXTCLOUD_STATE" == "1" ]]; then
    NEXTCLOUD_ADMIN_PASSWORD="$(preserve_or_randomize_secret "$current_nextcloud_admin_password")"
  else
    NEXTCLOUD_ADMIN_PASSWORD="$current_nextcloud_admin_password"
  fi
  nextcloud_admin_password_input="$(ask_secret_keep_default "Nextcloud admin password (ENTER keeps current)" "$NEXTCLOUD_ADMIN_PASSWORD")"
  NEXTCLOUD_ADMIN_PASSWORD="${nextcloud_admin_password_input:-$NEXTCLOUD_ADMIN_PASSWORD}"
  ENABLE_PRIVATE_GIT="$(ask_yes_no "Initialize almanac-priv as a git repo" "$default_enable_private_git")"
  ENABLE_QUARTO="$(ask_yes_no "Enable Quarto timer/hooks" "$default_enable_quarto")"
  SEED_SAMPLE_VAULT="$(ask_yes_no "Seed a starter vault structure" "$default_seed_vault")"
  PDF_VISION_ENDPOINT="$(normalize_optional_answer "$(ask "OpenAI-compatible vision endpoint for PDF page captions (base /v1 or full /v1/chat/completions; type none to disable)" "$default_pdf_vision_endpoint")")"
  PDF_VISION_MODEL="$(normalize_optional_answer "$(ask "Vision model name for PDF page captions (type none to disable)" "$default_pdf_vision_model")")"
  PDF_VISION_API_KEY="$(ask_secret_with_default "Vision API key for PDF page captions (ENTER keeps current, type none to clear)" "$default_pdf_vision_api_key")"
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
  default_home="${ALMANAC_HOME:-$(default_home_for_user "$default_user")}"
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
  ALMANAC_UPSTREAM_REPO_URL="${ALMANAC_UPSTREAM_REPO_URL:-https://github.com/example/almanac.git}"
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
  ALMANAC_HOME="${ALMANAC_HOME:-$(default_home_for_user "$ALMANAC_USER")}"
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
  ALMANAC_UPSTREAM_REPO_URL="${ALMANAC_UPSTREAM_REPO_URL:-https://github.com/example/almanac.git}"
  ALMANAC_UPSTREAM_BRANCH="${ALMANAC_UPSTREAM_BRANCH:-main}"
  ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED="${ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED:-0}"
  ALMANAC_UPSTREAM_DEPLOY_KEY_USER="${ALMANAC_UPSTREAM_DEPLOY_KEY_USER:-}"
  ALMANAC_UPSTREAM_DEPLOY_KEY_PATH="${ALMANAC_UPSTREAM_DEPLOY_KEY_PATH:-}"
  ALMANAC_UPSTREAM_KNOWN_HOSTS_FILE="${ALMANAC_UPSTREAM_KNOWN_HOSTS_FILE:-}"
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

  ALMANAC_REEXEC_ATTEMPTED=0
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
  ALMANAC_REEXEC_ATTEMPTED=1
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

  ALMANAC_REEXEC_ATTEMPTED=0
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
  ALMANAC_REEXEC_ATTEMPTED=1
  if sudo env ALMANAC_CONFIG_FILE="$DISCOVERED_CONFIG" "$SELF_PATH" "$requested_mode"; then
    write_operator_checkout_artifact
    return 0
  else
    local reexec_status="$?"
    return "$reexec_status"
  fi
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

shared_hermes_runtime_commit() {
  local repo_dir="${RUNTIME_DIR:-}/hermes-agent-src"

  if [[ -z "${RUNTIME_DIR:-}" || ! -d "$repo_dir/.git" ]]; then
    return 0
  fi
  git -c safe.directory="$repo_dir" -C "$repo_dir" rev-parse HEAD 2>/dev/null || true
}

report_shared_hermes_runtime_transition() {
  local before_commit="${1:-}"
  local after_commit="${2:-}"

  if [[ -z "$after_commit" ]]; then
    return 0
  fi
  if [[ "$before_commit" == "$after_commit" ]]; then
    echo "Hermes runtime unchanged at ${after_commit:0:12}; active gateways stay undisturbed."
    return 0
  fi
  if [[ -n "$before_commit" ]]; then
    echo "Hermes runtime updated ${before_commit:0:12} -> ${after_commit:0:12}; enrolled agent gateways will restart to pick up the new runtime."
  else
    echo "Hermes runtime installed at ${after_commit:0:12}; enrolled agent gateways will be aligned to it."
  fi
}

realign_active_enrolled_agents_root() {
  local agent_id="" unix_user="" hermes_home="" bot_label="" user_name="" uid=""
  local gateway_restart_policy="${1:-defer}"
  local restart_gateway_arg=()

  if [[ "$gateway_restart_policy" == "restart" ]]; then
    restart_gateway_arg=(--restart-gateway)
  fi

  while IFS=$'\t' read -r agent_id unix_user hermes_home bot_label user_name; do
    [[ -n "$agent_id" && -n "$unix_user" && -n "$hermes_home" ]] || continue
    if ! getent passwd "$unix_user" >/dev/null 2>&1; then
      echo "Skipping $agent_id: unix user '$unix_user' is missing."
      continue
    fi
    uid="$(id -u "$unix_user")"
    systemctl start "user@$uid.service" >/dev/null 2>&1 || true
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
    fi
    echo "Realigning user-agent install for $agent_id ($unix_user)..."
    run_root_env_cmd env \
      ALMANAC_CONFIG_FILE="$CONFIG_TARGET" \
      "$ALMANAC_REPO_DIR/bin/refresh-agent-install.sh" \
      --unix-user "$unix_user" \
      --hermes-home "$hermes_home" \
      --repo-dir "$ALMANAC_REPO_DIR" \
      --bot-name "$bot_label" \
      --user-name "$user_name" \
      "${restart_gateway_arg[@]}" >/dev/null
  done < <(run_root_env_cmd python3 - "$ALMANAC_DB_PATH" <<'PY'
import json
import sqlite3
import sys

conn = sqlite3.connect(sys.argv[1])
conn.row_factory = sqlite3.Row

rows = conn.execute(
    """
    SELECT agent_id, unix_user, hermes_home, display_name
    FROM agents
    WHERE role = 'user' AND status = 'active'
    ORDER BY unix_user
    """
).fetchall()

session_rows = conn.execute(
    """
    SELECT linked_agent_id, answers_json, sender_display_name
    FROM onboarding_sessions
    WHERE state = 'completed'
    ORDER BY COALESCE(completed_at, updated_at, created_at) DESC
    """
).fetchall()

bot_labels = {}
user_names = {}
for row in session_rows:
    agent_id = str(row["linked_agent_id"] or "").strip()
    if not agent_id:
        continue
    try:
        answers = json.loads(row["answers_json"] or "{}")
    except Exception:
        answers = {}
    if agent_id not in bot_labels:
        label = str(
            answers.get("bot_display_name")
            or answers.get("bot_username")
            or answers.get("preferred_bot_name")
            or ""
        ).strip()
        if label:
            bot_labels[agent_id] = label
    if agent_id not in user_names:
        user_name = str(
            answers.get("full_name")
            or row["sender_display_name"]
            or ""
        ).strip()
        if user_name:
            user_names[agent_id] = user_name

for row in rows:
    agent_id = str(row["agent_id"] or "")
    print("\t".join([
        agent_id,
        str(row["unix_user"] or ""),
        str(row["hermes_home"] or ""),
        bot_labels.get(agent_id, str(row["display_name"] or "").strip()),
        user_names.get(agent_id, ""),
    ]))
PY
  )
}

chown_managed_paths() {
  chown -hR "$ALMANAC_USER:$ALMANAC_USER" "$ALMANAC_REPO_DIR"

  if [[ ! -d "$ALMANAC_PRIV_DIR" ]]; then
    return 0
  fi

  if [[ "$ENABLE_NEXTCLOUD" == "1" && -n "${NEXTCLOUD_STATE_DIR:-}" && -d "$NEXTCLOUD_STATE_DIR" ]]; then
    chown -h "$ALMANAC_USER:$ALMANAC_USER" "$ALMANAC_PRIV_DIR"
    find "$ALMANAC_PRIV_DIR" -ignore_readdir_race \
      -path "$NEXTCLOUD_STATE_DIR" -prune -o \
      -name "*.sqlite3-shm" -prune -o \
      -name "*.sqlite3-wal" -prune -o \
      -exec chown -h "$ALMANAC_USER:$ALMANAC_USER" {} +
    return 0
  fi

  find "$ALMANAC_PRIV_DIR" -ignore_readdir_race \
    -name "*.sqlite3-shm" -prune -o \
    -name "*.sqlite3-wal" -prune -o \
    -exec chown -h "$ALMANAC_USER:$ALMANAC_USER" {} +
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
    run_as_user_systemd "$ALMANAC_USER" "$uid" "ALMANAC_CONFIG_FILE='$CONFIG_TARGET' systemctl --user restart almanac-mcp.service almanac-notion-webhook.service almanac-qmd-mcp.service almanac-qmd-update.timer almanac-vault-watch.service almanac-github-backup.timer almanac-ssot-batcher.timer almanac-notification-delivery.timer almanac-health-watch.timer almanac-curator-refresh.timer"
    run_as_user_systemd "$ALMANAC_USER" "$uid" "ALMANAC_CONFIG_FILE='$CONFIG_TARGET' systemctl --user start almanac-curator-refresh.service" || true
    run_as_user_systemd "$ALMANAC_USER" "$uid" "ALMANAC_CONFIG_FILE='$CONFIG_TARGET' systemctl --user start almanac-health-watch.service" || true

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
  local hermes_runtime_before=""
  local hermes_runtime_after=""
  local gateway_restart_policy="defer"

  env \
    ALMANAC_USER="$ALMANAC_USER" \
    ALMANAC_HOME="$ALMANAC_HOME" \
    ALMANAC_REPO_DIR="$ALMANAC_REPO_DIR" \
    ALMANAC_PRIV_DIR="$ALMANAC_PRIV_DIR" \
    ALMANAC_PRIV_CONFIG_DIR="$ALMANAC_PRIV_CONFIG_DIR" \
    VAULT_DIR="$VAULT_DIR" \
    STATE_DIR="$STATE_DIR" \
    NEXTCLOUD_STATE_DIR="$NEXTCLOUD_STATE_DIR" \
    PUBLISHED_DIR="$PUBLISHED_DIR" \
    QUARTO_PROJECT_DIR="$QUARTO_PROJECT_DIR" \
    ALMANAC_INSTALL_PODMAN="${ALMANAC_INSTALL_PODMAN:-auto}" \
    ALMANAC_INSTALL_TAILSCALE="${ALMANAC_INSTALL_TAILSCALE:-auto}" \
    ENABLE_TAILSCALE_SERVE="${ENABLE_TAILSCALE_SERVE:-0}" \
    ALMANAC_AGENT_ENABLE_TAILSCALE_SERVE="${ALMANAC_AGENT_ENABLE_TAILSCALE_SERVE:-$ENABLE_TAILSCALE_SERVE}" \
    "$BOOTSTRAP_DIR/bin/bootstrap-system.sh"
  sync_public_repo
  seed_private_repo "$ALMANAC_PRIV_DIR"
  write_runtime_config "$CONFIG_TARGET"
  maybe_run_org_profile_builder "$ALMANAC_REPO_DIR"
  chown_managed_paths
  ensure_upstream_git_deploy_key_material_root
  env ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$ALMANAC_REPO_DIR/bin/install-system-services.sh"
  wipe_nextcloud_state_if_requested

  init_public_repo_if_needed
  configure_upstream_git_for_repo "$ALMANAC_REPO_DIR"

  hermes_runtime_before="$(shared_hermes_runtime_commit)"
  run_as_user "$ALMANAC_USER" "env ALMANAC_CONFIG_FILE='$CONFIG_TARGET' '$ALMANAC_REPO_DIR/bin/bootstrap-userland.sh'"
  hermes_runtime_after="$(shared_hermes_runtime_commit)"
  report_shared_hermes_runtime_transition "$hermes_runtime_before" "$hermes_runtime_after"
  if [[ -n "$hermes_runtime_after" && "$hermes_runtime_before" != "$hermes_runtime_after" ]]; then
    gateway_restart_policy="restart"
  fi
  run_as_user "$ALMANAC_USER" "env ALMANAC_CONFIG_FILE='$CONFIG_TARGET' ALMANAC_ALLOW_NO_USER_BUS='${ALMANAC_ALLOW_NO_USER_BUS:-0}' '$ALMANAC_REPO_DIR/bin/install-user-services.sh'"
  chown -hR "$ALMANAC_USER:$ALMANAC_USER" "$ALMANAC_PRIV_DIR"
  run_as_user "$ALMANAC_USER" "env $(curator_bootstrap_env_prefix) '$ALMANAC_REPO_DIR/bin/bootstrap-curator.sh'"
  reload_runtime_config_from_file "$CONFIG_TARGET" || true
  ensure_upstream_git_deploy_key_material_root
  configure_upstream_git_for_repo "$ALMANAC_REPO_DIR"
  ensure_backup_git_deploy_key_material_root
  repair_active_agent_runtime_access
  apply_org_profile_if_present_root
  realign_active_enrolled_agents_root "$gateway_restart_policy"

  local uid=""
  restart_shared_user_services_root
  uid="$(id -u "$ALMANAC_USER")"

  if [[ -n "${TAILSCALE_OPERATOR_USER:-}" ]] && command -v tailscale >/dev/null 2>&1 && { [[ "$ENABLE_NEXTCLOUD" == "1" && "$ENABLE_TAILSCALE_SERVE" == "1" ]] || [[ "$ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL" == "1" ]]; }; then
    tailscale set --operator="$TAILSCALE_OPERATOR_USER" >/dev/null 2>&1 || true
  fi

  if [[ "$ENABLE_NEXTCLOUD" == "1" && "$ENABLE_TAILSCALE_SERVE" == "1" ]]; then
    ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$ALMANAC_REPO_DIR/bin/tailscale-nextcloud-serve.sh"
  fi
  if [[ "$ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL" == "1" ]]; then
    ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$ALMANAC_REPO_DIR/bin/tailscale-notion-webhook-funnel.sh"
  elif [[ -x "$ALMANAC_REPO_DIR/bin/tailscale-notion-webhook-unfunnel.sh" ]]; then
    ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$ALMANAC_REPO_DIR/bin/tailscale-notion-webhook-unfunnel.sh" >/dev/null 2>&1 || true
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
    refresh_upgrade_check_state_root "$source_commit" "${ALMANAC_UPSTREAM_REPO_URL:-$source_repo_url}" "${ALMANAC_UPSTREAM_BRANCH:-$source_branch}"
  fi

  echo
  echo "Running health check..."
  if [[ -S "/run/user/$uid/bus" ]]; then
    run_as_user_systemd "$ALMANAC_USER" "$uid" "ALMANAC_CONFIG_FILE='$CONFIG_TARGET' ALMANAC_HEALTH_STRICT=1 '$ALMANAC_REPO_DIR/bin/health.sh'"
  else
    run_as_user "$ALMANAC_USER" "env ALMANAC_CONFIG_FILE='$CONFIG_TARGET' ALMANAC_HEALTH_STRICT=1 '$ALMANAC_REPO_DIR/bin/health.sh'"
  fi

  if [[ -x "$ALMANAC_REPO_DIR/bin/live-agent-tool-smoke.sh" ]]; then
    echo
    echo "Running live agent tool smoke..."
    env ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$ALMANAC_REPO_DIR/bin/live-agent-tool-smoke.sh"
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
  local hermes_runtime_before=""
  local hermes_runtime_after=""
  local gateway_restart_policy="defer"

  tmp_dir="$(mktemp -d /tmp/almanac-upgrade.XXXXXX)"
  checkout_dir="$tmp_dir/repo"
  trap 'rm -rf "${tmp_dir:-}"' EXIT

  require_main_upstream_branch_for_upgrade
  ensure_upstream_git_deploy_key_material_root

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
  configure_upstream_git_for_repo "$ALMANAC_REPO_DIR"

  env \
    ALMANAC_USER="$ALMANAC_USER" \
    ALMANAC_HOME="$ALMANAC_HOME" \
    ALMANAC_REPO_DIR="$ALMANAC_REPO_DIR" \
    ALMANAC_PRIV_DIR="$ALMANAC_PRIV_DIR" \
    ALMANAC_PRIV_CONFIG_DIR="$ALMANAC_PRIV_CONFIG_DIR" \
    VAULT_DIR="$VAULT_DIR" \
    STATE_DIR="$STATE_DIR" \
    NEXTCLOUD_STATE_DIR="$NEXTCLOUD_STATE_DIR" \
    PUBLISHED_DIR="$PUBLISHED_DIR" \
    QUARTO_PROJECT_DIR="$QUARTO_PROJECT_DIR" \
    ALMANAC_INSTALL_PODMAN="${ALMANAC_INSTALL_PODMAN:-auto}" \
    ALMANAC_INSTALL_TAILSCALE="${ALMANAC_INSTALL_TAILSCALE:-auto}" \
    ENABLE_TAILSCALE_SERVE="${ENABLE_TAILSCALE_SERVE:-0}" \
    ALMANAC_AGENT_ENABLE_TAILSCALE_SERVE="${ALMANAC_AGENT_ENABLE_TAILSCALE_SERVE:-$ENABLE_TAILSCALE_SERVE}" \
    "$ALMANAC_REPO_DIR/bin/bootstrap-system.sh"
  env ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$ALMANAC_REPO_DIR/bin/install-system-services.sh"
  hermes_runtime_before="$(shared_hermes_runtime_commit)"
  run_as_user "$ALMANAC_USER" "env ALMANAC_CONFIG_FILE='$CONFIG_TARGET' '$ALMANAC_REPO_DIR/bin/bootstrap-userland.sh'"
  hermes_runtime_after="$(shared_hermes_runtime_commit)"
  report_shared_hermes_runtime_transition "$hermes_runtime_before" "$hermes_runtime_after"
  if [[ -n "$hermes_runtime_after" && "$hermes_runtime_before" != "$hermes_runtime_after" ]]; then
    gateway_restart_policy="restart"
  fi
  run_as_user "$ALMANAC_USER" "env ALMANAC_CONFIG_FILE='$CONFIG_TARGET' ALMANAC_ALLOW_NO_USER_BUS='${ALMANAC_ALLOW_NO_USER_BUS:-0}' '$ALMANAC_REPO_DIR/bin/install-user-services.sh'"
  chown -hR "$ALMANAC_USER:$ALMANAC_USER" "$ALMANAC_PRIV_DIR"
  run_as_user "$ALMANAC_USER" "env ALMANAC_CURATOR_SKIP_HERMES_SETUP='1' ALMANAC_CURATOR_SKIP_GATEWAY_SETUP='1' $(curator_bootstrap_env_prefix) '$ALMANAC_REPO_DIR/bin/bootstrap-curator.sh'"
  reload_runtime_config_from_file "$CONFIG_TARGET" || true
  ensure_upstream_git_deploy_key_material_root
  configure_upstream_git_for_repo "$ALMANAC_REPO_DIR"
  ensure_backup_git_deploy_key_material_root
  repair_active_agent_runtime_access
  apply_org_profile_if_present_root
  realign_active_enrolled_agents_root "$gateway_restart_policy"

  restart_shared_user_services_root
  uid="$(id -u "$ALMANAC_USER")"

  if [[ -n "${TAILSCALE_OPERATOR_USER:-}" ]] && command -v tailscale >/dev/null 2>&1 && { [[ "$ENABLE_NEXTCLOUD" == "1" && "$ENABLE_TAILSCALE_SERVE" == "1" ]] || [[ "$ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL" == "1" ]]; }; then
    tailscale set --operator="$TAILSCALE_OPERATOR_USER" >/dev/null 2>&1 || true
  fi

  if [[ "$ENABLE_NEXTCLOUD" == "1" && "$ENABLE_TAILSCALE_SERVE" == "1" ]]; then
    ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$ALMANAC_REPO_DIR/bin/tailscale-nextcloud-serve.sh"
  fi
  if [[ "$ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL" == "1" ]]; then
    ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$ALMANAC_REPO_DIR/bin/tailscale-notion-webhook-funnel.sh"
  elif [[ -x "$ALMANAC_REPO_DIR/bin/tailscale-notion-webhook-unfunnel.sh" ]]; then
    ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$ALMANAC_REPO_DIR/bin/tailscale-notion-webhook-unfunnel.sh" >/dev/null 2>&1 || true
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
  refresh_upgrade_check_state_root "$upstream_commit" "$ALMANAC_UPSTREAM_REPO_URL" "$ALMANAC_UPSTREAM_BRANCH"

  echo
  echo "Running health check..."
  if [[ -S "/run/user/$uid/bus" ]]; then
    run_as_user_systemd "$ALMANAC_USER" "$uid" "ALMANAC_CONFIG_FILE='$CONFIG_TARGET' ALMANAC_HEALTH_STRICT=1 '$ALMANAC_REPO_DIR/bin/health.sh'"
  else
    run_as_user "$ALMANAC_USER" "env ALMANAC_CONFIG_FILE='$CONFIG_TARGET' ALMANAC_HEALTH_STRICT=1 '$ALMANAC_REPO_DIR/bin/health.sh'"
  fi

  if [[ -x "$ALMANAC_REPO_DIR/bin/live-agent-tool-smoke.sh" ]]; then
    echo
    echo "Running live agent tool smoke..."
    env ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$ALMANAC_REPO_DIR/bin/live-agent-tool-smoke.sh"
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
      run_as_user_systemd "$ALMANAC_USER" "$uid" "ALMANAC_CONFIG_FILE='$CONFIG_TARGET' systemctl --user disable --now almanac-nextcloud.service almanac-qmd-mcp.service almanac-qmd-update.timer almanac-vault-watch.service almanac-pdf-ingest.timer almanac-pdf-ingest-watch.service almanac-github-backup.timer almanac-quarto-render.timer almanac-mcp.service almanac-notion-webhook.service almanac-ssot-batcher.timer almanac-notification-delivery.timer almanac-health-watch.timer almanac-curator-refresh.timer almanac-curator-gateway.service almanac-curator-onboarding.service almanac-curator-discord-onboarding.service >/dev/null 2>&1 || true" || true
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
  if [[ "$REMOVE_PUBLIC_REPO" == "1" && -x "$ALMANAC_REPO_DIR/bin/tailscale-notion-webhook-unfunnel.sh" ]]; then
    ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$ALMANAC_REPO_DIR/bin/tailscale-notion-webhook-unfunnel.sh" >/dev/null 2>&1 || true
  fi

  systemctl disable --now almanac-enrollment-provision.timer almanac-notion-claim-poll.timer >/dev/null 2>&1 || true
  systemctl stop almanac-enrollment-provision.service almanac-notion-claim-poll.service >/dev/null 2>&1 || true
  rm -f /etc/systemd/system/almanac-enrollment-provision.service /etc/systemd/system/almanac-enrollment-provision.timer
  rm -f /etc/systemd/system/almanac-notion-claim-poll.service /etc/systemd/system/almanac-notion-claim-poll.timer
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
  local onboarding_file="" provision_file="" timer_enabled="" timer_active="" service_active="" claim_timer_enabled="" claim_timer_active="" claim_service_active="" reexec_status=""

  prepare_deployed_context
  if maybe_reexec_with_sudo_for_config enrollment-status; then
    return 0
  else
    reexec_status="$?"
    if [[ "${ALMANAC_REEXEC_ATTEMPTED:-0}" == "1" ]]; then
      return "$reexec_status"
    fi
  fi
  ensure_deployed_config_exists

  onboarding_file="$(mktemp)"
  provision_file="$(mktemp)"

  run_service_user_cmd "$ALMANAC_REPO_DIR/bin/almanac-ctl" --json onboarding list >"$onboarding_file"
  run_service_user_cmd "$ALMANAC_REPO_DIR/bin/almanac-ctl" --json provision list >"$provision_file"

  timer_enabled="$(systemctl is-enabled almanac-enrollment-provision.timer 2>/dev/null || true)"
  timer_active="$(systemctl is-active almanac-enrollment-provision.timer 2>/dev/null || true)"
  service_active="$(systemctl is-active almanac-enrollment-provision.service 2>/dev/null || true)"
  claim_timer_enabled="$(systemctl is-enabled almanac-notion-claim-poll.timer 2>/dev/null || true)"
  claim_timer_active="$(systemctl is-active almanac-notion-claim-poll.timer 2>/dev/null || true)"
  claim_service_active="$(systemctl is-active almanac-notion-claim-poll.service 2>/dev/null || true)"

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
  echo "Notion claim poller:"
  echo "  timer enabled: $claim_timer_enabled"
  echo "  timer active:  $claim_timer_active"
  echo "  service:       $claim_service_active"
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
  local timer_enabled="" timer_active="" service_active="" resolved_unix_user="" resolved_hermes_home="" reexec_status=""

  prepare_deployed_context
  if maybe_reexec_with_sudo_for_config enrollment-trace; then
    return 0
  else
    reexec_status="$?"
    if [[ "${ALMANAC_REEXEC_ATTEMPTED:-0}" == "1" ]]; then
      return "$reexec_status"
    fi
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
  local reexec_status=""

  prepare_deployed_context
  if maybe_reexec_with_sudo_for_config enrollment-align; then
    return 0
  else
    reexec_status="$?"
    if [[ "${ALMANAC_REEXEC_ATTEMPTED:-0}" == "1" ]]; then
      return "$reexec_status"
    fi
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
  realign_active_enrolled_agents_root
  restart_shared_user_services_root || true
  systemctl reset-failed almanac-enrollment-provision.service almanac-enrollment-provision.timer almanac-notion-claim-poll.service almanac-notion-claim-poll.timer >/dev/null 2>&1 || true
  systemctl enable almanac-enrollment-provision.timer almanac-notion-claim-poll.timer >/dev/null
  systemctl restart almanac-enrollment-provision.timer almanac-notion-claim-poll.timer
  systemctl start almanac-enrollment-provision.service >/dev/null 2>&1 || true
  systemctl start almanac-notion-claim-poll.service >/dev/null 2>&1 || true
  echo "Enrollment provisioner, shared services, and active external user-agent units realigned."
  echo
  run_enrollment_status
}

run_enrollment_reset() {
  local target_unix_user="" remove_unix_user="" purge_rate_limits="" remove_archives="" confirm_text="" extra_subject="" uid=""
  local forget_history="" remove_nextcloud_user=""
  local snapshot_file="" agent_id="" agent_status="" reexec_status=""
  local -a session_ids=() request_specs=() rate_subjects=() purge_cmd=()

  prepare_deployed_context
  if maybe_reexec_with_sudo_for_config enrollment-reset; then
    return 0
  else
    reexec_status="$?"
    if [[ "${ALMANAC_REEXEC_ATTEMPTED:-0}" == "1" ]]; then
      return "$reexec_status"
    fi
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
  forget_history="$(ask_yes_no "Forget completed enrollment history and local app accounts so this user can onboard as new" "${ENROLLMENT_RESET_FORGET_HISTORY:-1}")"
  if [[ "$forget_history" == "1" ]]; then
    remove_nextcloud_user="$(ask_yes_no "Remove the matching Nextcloud user if present" "${ENROLLMENT_RESET_REMOVE_NEXTCLOUD_USER:-1}")"
  fi
  extra_subject="$(ask "Extra rate-limit subject to clear (optional, e.g. discord:123456789)" "${ENROLLMENT_RESET_EXTRA_SUBJECT:-}")"
  confirm_text="$(ask "Type RESET to confirm enrollment cleanup" "")"
  if [[ "$confirm_text" != "RESET" ]]; then
    rm -f "$snapshot_file"
    echo "Enrollment reset cancelled."
    exit 1
  fi

  if [[ "$forget_history" == "1" ]]; then
    purge_cmd=(
      env
      ALMANAC_CONFIG_FILE="$CONFIG_TARGET"
      "$ALMANAC_REPO_DIR/bin/almanac-ctl"
      user
      purge-enrollment
      "$target_unix_user"
      --actor
      deploy-enrollment-reset
    )
    if [[ "$remove_unix_user" == "1" ]]; then
      purge_cmd+=(--remove-unix-user)
    fi
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
    if ! "${purge_cmd[@]}"; then
      rm -f "$snapshot_file"
      echo "Enrollment purge failed." >&2
      exit 1
    fi
    systemctl start almanac-enrollment-provision.service >/dev/null 2>&1 || true
    rm -f "$snapshot_file"
    echo "Enrollment purge complete for $target_unix_user."
    echo
    run_enrollment_status
    return 0
  fi

  session_ids=()
  while IFS= read -r line; do
    session_ids+=("$line")
  done < <(python3 - "$snapshot_file" <<'PY'
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)
for row in data.get("onboarding") or []:
    if row.get("state") not in {"denied", "completed", "cancelled"}:
        print(row.get("session_id", ""))
PY
)
  request_specs=()
  while IFS= read -r line; do
    request_specs+=("$line")
  done < <(python3 - "$snapshot_file" <<'PY'
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
  rate_subjects=()
  while IFS= read -r line; do
    rate_subjects+=("$line")
  done < <(python3 - "$snapshot_file" <<'PY'
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

run_pins_show() {
  # shellcheck disable=SC1091
  source "$BOOTSTRAP_DIR/bin/pins.sh"
  pins_show
}

run_pin_upgrade_notify() {
  # On-demand detector run: same logic that almanac-curator-refresh.timer
  # invokes hourly via `almanac-ctl internal pin-upgrade-check`.
  load_detected_config || true
  exec sudo -u "${ALMANAC_USER:-almanac}" \
    env ALMANAC_CONFIG_FILE="${ALMANAC_CONFIG_FILE:-/home/almanac/almanac/almanac-priv/config/almanac.env}" \
    "$BOOTSTRAP_DIR/bin/almanac-ctl" --json internal pin-upgrade-check
}

# Components in pins.json that have a concrete upstream-check resolver wired in
# component-upgrade.sh. Floating-by-design components (uv, tailscale, python,
# quarto) and installer-url components are excluded.
_pins_managed_components() {
  printf '%s\n' \
    hermes-agent \
    hermes-docs \
    code-server \
    nvm \
    node \
    qmd \
    nextcloud \
    postgres \
    redis
}

run_pins_check() {
  # shellcheck disable=SC1091
  source "$BOOTSTRAP_DIR/bin/pins.sh"
  pins_require
  pins_validate || return 1
  echo "config/pins.json: $ALMANAC_PINS_FILE (validated)"
  echo
  echo "Per-component drift (read-only; no pins.json or git modifications):"
  while IFS= read -r component; do
    [[ -z "$component" ]] && continue
    echo
    echo "--- $component ---"
    "$BOOTSTRAP_DIR/bin/component-upgrade.sh" "$component" check || true
  done < <(_pins_managed_components)
  echo
  echo "Floating by design (no upstream check): python uv tailscale quarto"
}

# Generic dispatcher used for every <component>-upgrade-check subcommand.
_run_component_check() {
  local component="$1"; shift
  exec "$BOOTSTRAP_DIR/bin/component-upgrade.sh" "$component" check "$@"
}

# Generic dispatcher used for every <component>-upgrade subcommand. Forwards
# all the upstream + deploy-key env vars that component-upgrade.sh needs to
# commit + push + re-exec ./deploy.sh upgrade.
_run_component_apply() {
  local component="$1"; shift
  load_detected_config || true
  exec env \
    ALMANAC_UPSTREAM_REPO_URL="${ALMANAC_UPSTREAM_REPO_URL:-}" \
    ALMANAC_UPSTREAM_BRANCH="${ALMANAC_UPSTREAM_BRANCH:-main}" \
    ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED="${ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED:-}" \
    ALMANAC_UPSTREAM_DEPLOY_KEY_USER="${ALMANAC_UPSTREAM_DEPLOY_KEY_USER:-}" \
    ALMANAC_UPSTREAM_DEPLOY_KEY_PATH="${ALMANAC_UPSTREAM_DEPLOY_KEY_PATH:-}" \
    ALMANAC_UPSTREAM_KNOWN_HOSTS_FILE="${ALMANAC_UPSTREAM_KNOWN_HOSTS_FILE:-}" \
    ALMANAC_CONFIG_FILE="${ALMANAC_CONFIG_FILE:-}" \
    "$BOOTSTRAP_DIR/bin/component-upgrade.sh" "$component" apply "$@"
}

run_hermes_upgrade_check()       { _run_component_check hermes-agent "$@"; }
run_hermes_upgrade()             { _run_component_apply hermes-agent "$@"; }
run_qmd_upgrade_check()          { _run_component_check qmd "$@"; }
run_qmd_upgrade()                { _run_component_apply qmd "$@"; }
run_nextcloud_upgrade_check()    { _run_component_check nextcloud "$@"; }
run_nextcloud_upgrade()          { _run_component_apply nextcloud "$@"; }
run_postgres_upgrade_check()     { _run_component_check postgres "$@"; }
run_postgres_upgrade()           { _run_component_apply postgres "$@"; }
run_redis_upgrade_check()        { _run_component_check redis "$@"; }
run_redis_upgrade()              { _run_component_apply redis "$@"; }
run_code_server_upgrade_check()  { _run_component_check code-server "$@"; }
run_code_server_upgrade()        { _run_component_apply code-server "$@"; }
run_nvm_upgrade_check()          { _run_component_check nvm "$@"; }
run_nvm_upgrade()                { _run_component_apply nvm "$@"; }
run_node_upgrade_check()         { _run_component_check node "$@"; }
run_node_upgrade()               { _run_component_apply node "$@"; }

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
    ALMANAC_HOME="$(default_home_for_user "$ALMANAC_USER")"
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
    if [[ -S "/run/user/$uid/bus" ]]; then
      run_as_user_systemd "$ALMANAC_USER" "$uid" "ALMANAC_CONFIG_FILE='$CONFIG_TARGET' '$ALMANAC_REPO_DIR/bin/health.sh'"
    else
      run_as_user "$ALMANAC_USER" "env ALMANAC_CONFIG_FILE='$CONFIG_TARGET' '$ALMANAC_REPO_DIR/bin/health.sh'"
    fi
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
  if [[ -S "/run/user/$uid/bus" ]]; then
    sudo -iu "$ALMANAC_USER" env \
      XDG_RUNTIME_DIR="/run/user/$uid" \
      DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" \
      ALMANAC_CONFIG_FILE="$CONFIG_TARGET" \
      "$ALMANAC_REPO_DIR/bin/health.sh"
  else
    sudo -iu "$ALMANAC_USER" env \
      ALMANAC_CONFIG_FILE="$CONFIG_TARGET" \
      "$ALMANAC_REPO_DIR/bin/health.sh"
  fi
  write_operator_checkout_artifact
}

run_rotate_nextcloud_secrets() {
  local new_postgres_password="" new_admin_password="" masked_postgres="" masked_admin="" confirm_text=""
  local uid="" pg_file="" admin_file="" rotate_status=0

  prepare_deployed_context
  ensure_deployed_config_exists
  reload_runtime_config_from_file "$CONFIG_TARGET" || true

  if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    local sudo_pg_file="" sudo_admin_file="" sudo_status=0
    local -a cmd=(
      sudo env
      "ALMANAC_CONFIG_FILE=$CONFIG_TARGET"
      "NEXTCLOUD_ROTATE_ASSUME_YES=${NEXTCLOUD_ROTATE_ASSUME_YES:-0}"
    )
    if [[ -n "${NEXTCLOUD_ROTATE_POSTGRES_PASSWORD:-}" ]]; then
      sudo_pg_file="$(mktemp /tmp/almanac-nextcloud-pg.XXXXXX)"
      chmod 600 "$sudo_pg_file"
      printf '%s\n' "$NEXTCLOUD_ROTATE_POSTGRES_PASSWORD" >"$sudo_pg_file"
      cmd+=("NEXTCLOUD_ROTATE_POSTGRES_PASSWORD_FILE=$sudo_pg_file")
    fi
    if [[ -n "${NEXTCLOUD_ROTATE_ADMIN_PASSWORD:-}" ]]; then
      sudo_admin_file="$(mktemp /tmp/almanac-nextcloud-admin.XXXXXX)"
      chmod 600 "$sudo_admin_file"
      printf '%s\n' "$NEXTCLOUD_ROTATE_ADMIN_PASSWORD" >"$sudo_admin_file"
      cmd+=("NEXTCLOUD_ROTATE_ADMIN_PASSWORD_FILE=$sudo_admin_file")
    fi
    cmd+=("$SELF_PATH" rotate-nextcloud-secrets)

    echo "Switching to sudo for live Nextcloud credential rotation..."
    "${cmd[@]}" || sudo_status=$?
    rm -f "$sudo_pg_file" "$sudo_admin_file"
    if (( sudo_status != 0 )); then
      return "$sudo_status"
    fi
    write_operator_checkout_artifact
    return 0
  fi

  if [[ "${ENABLE_NEXTCLOUD:-0}" != "1" ]]; then
    echo "Nextcloud is disabled in $CONFIG_TARGET; nothing to rotate." >&2
    exit 1
  fi

  if ! id -u "$ALMANAC_USER" >/dev/null 2>&1; then
    echo "Service user '$ALMANAC_USER' does not exist." >&2
    exit 1
  fi

  if [[ -n "${NEXTCLOUD_ROTATE_POSTGRES_PASSWORD_FILE:-}" ]]; then
    NEXTCLOUD_ROTATE_POSTGRES_PASSWORD="$(read_single_line_secret_file "NEXTCLOUD_ROTATE_POSTGRES_PASSWORD" "$NEXTCLOUD_ROTATE_POSTGRES_PASSWORD_FILE")"
  fi
  if [[ -n "${NEXTCLOUD_ROTATE_ADMIN_PASSWORD_FILE:-}" ]]; then
    NEXTCLOUD_ROTATE_ADMIN_PASSWORD="$(read_single_line_secret_file "NEXTCLOUD_ROTATE_ADMIN_PASSWORD" "$NEXTCLOUD_ROTATE_ADMIN_PASSWORD_FILE")"
  fi

  new_postgres_password="${NEXTCLOUD_ROTATE_POSTGRES_PASSWORD:-$(random_secret)}"
  new_admin_password="${NEXTCLOUD_ROTATE_ADMIN_PASSWORD:-$(random_secret)}"
  masked_postgres="$(mask_secret "$new_postgres_password")"
  masked_admin="$(mask_secret "$new_admin_password")"

  echo "Almanac deploy: rotate live Nextcloud credentials"
  echo
  echo "Config:             $CONFIG_TARGET"
  echo "Service user:       $ALMANAC_USER"
  echo "Nextcloud admin:    ${NEXTCLOUD_ADMIN_USER:-admin}"
  echo "New Postgres pass:  $masked_postgres"
  echo "New admin pass:     $masked_admin"

  if [[ "${NEXTCLOUD_ROTATE_ASSUME_YES:-0}" != "1" ]]; then
    confirm_text="$(ask "Type ROTATE to apply the live credential rotation" "")"
    if [[ "$confirm_text" != "ROTATE" ]]; then
      echo "Credential rotation cancelled."
      exit 1
    fi
  fi

  uid="$(id -u "$ALMANAC_USER")"
  systemctl start "user@$uid.service" >/dev/null 2>&1 || true
  run_as_user_systemd "$ALMANAC_USER" "$uid" "ALMANAC_CONFIG_FILE='$CONFIG_TARGET' systemctl --user start almanac-nextcloud.service >/dev/null 2>&1 || true"

  pg_file="$(mktemp /tmp/almanac-nextcloud-pg.XXXXXX)"
  admin_file="$(mktemp /tmp/almanac-nextcloud-admin.XXXXXX)"
  chmod 600 "$pg_file" "$admin_file"
  printf '%s\n' "$new_postgres_password" >"$pg_file"
  printf '%s\n' "$new_admin_password" >"$admin_file"
  chown "$ALMANAC_USER:$ALMANAC_USER" "$pg_file" "$admin_file"
  run_as_user "$ALMANAC_USER" \
    "env ALMANAC_CONFIG_FILE='$CONFIG_TARGET' NEXTCLOUD_ROTATE_POSTGRES_PASSWORD_FILE='$pg_file' NEXTCLOUD_ROTATE_ADMIN_PASSWORD_FILE='$admin_file' '$ALMANAC_REPO_DIR/bin/rotate-nextcloud-secrets.sh'" || rotate_status=$?
  rm -f "$pg_file" "$admin_file"
  if (( rotate_status != 0 )); then
    return "$rotate_status"
  fi

  POSTGRES_PASSWORD="$new_postgres_password"
  NEXTCLOUD_ADMIN_PASSWORD="$new_admin_password"
  write_runtime_config "$CONFIG_TARGET"
  reload_runtime_config_from_file "$CONFIG_TARGET" || true

  run_as_user_systemd "$ALMANAC_USER" "$uid" "ALMANAC_CONFIG_FILE='$CONFIG_TARGET' systemctl --user restart almanac-nextcloud.service"
  run_as_user_systemd "$ALMANAC_USER" "$uid" "ALMANAC_CONFIG_FILE='$CONFIG_TARGET' ALMANAC_HEALTH_STRICT=1 '$ALMANAC_REPO_DIR/bin/health.sh'"

  echo
  echo "Live Nextcloud credentials rotated and persisted to $CONFIG_TARGET."
}

run_notion_ssot_setup() {
  local notion_space_url="" notion_token="" notion_api_version="" notion_public_webhook_url="" handshake_file="" notion_token_file=""
  local integration_name="" workspace_name="" space_title="" space_id="" space_kind="" target_url=""
  local root_page_id="" root_page_url="" root_page_title="" reexec_status=""

  prepare_deployed_context
  if maybe_reexec_with_sudo_for_config notion-ssot; then
    return 0
  else
    reexec_status="$?"
    if [[ "${ALMANAC_REEXEC_ATTEMPTED:-0}" == "1" ]]; then
      return "$reexec_status"
    fi
  fi
  ensure_deployed_config_exists
  reload_runtime_config_from_file "$CONFIG_TARGET" || true

  if [[ ${EUID:-$(id -u)} -ne 0 && "$(id -un)" != "$ALMANAC_USER" ]]; then
    echo "Switching to sudo for Notion SSOT setup..."
    sudo env ALMANAC_CONFIG_FILE="$CONFIG_TARGET" "$SELF_PATH" notion-ssot
    write_operator_checkout_artifact
    return 0
  fi

  echo "Almanac deploy: Notion SSOT setup / handshake"
  echo
  echo "Make one normal Notion page for Almanac, such as 'The Almanac', then"
  echo "paste that page URL below."
  echo "Do not use the workspace Home screen."
  echo
  echo "Before you continue in Notion:"
  echo "  1) Create a normal page for Almanac in the Teamspace you want it to use."
  echo "  2) Open this page in your browser:"
  echo "     https://www.notion.so/profile/integrations/internal"
  echo "  3) If Notion lands you back in the workspace UI, open your workspace"
  echo "     switcher in the top-left, then go to Settings -> Integrations."
  echo "  4) Click Create new integration."
  echo "  5) Name it something like Almanac Curator, optionally upload an icon"
  echo "     (the Curator Discord avatar in this repo works well), choose the"
  echo "     associated workspace, and click Create."
  echo "  6) On the capabilities screen:"
  echo "     - turn on every checkbox capability Notion offers on that screen"
  echo "     - for user information, choose Read user information including email addresses"
  echo "       so Almanac can verify users against their Notion email"
  echo "     - click Save"
  echo "  7) If you land on Discover new connections / Show all and see options like"
  echo "     Notion MCP, GitHub, Slack, Jira, or other partner apps, stop there:"
  echo "     those are not the right choice for Almanac's shared SSOT setup."
  echo "  8) Open that internal integration and, near Internal integration secret,"
  echo "     click Show and then copy the key."
  echo "  9) In that integration, open Manage page access and grant access to the"
  echo "     parent page or Teamspace root Almanac should live under."
  echo "     New child pages and databases under that granted subtree inherit"
  echo "     access automatically."
  echo
  echo "Almanac will use the page you paste below as its shared Notion home and"
  echo "create its verification scaffolding under it when needed."
  require_notion_subtree_ack
  if [[ -n "${ALMANAC_SSOT_NOTION_SPACE_URL:-}" ]]; then
    echo "Current shared Notion target:"
    echo "  ${ALMANAC_SSOT_NOTION_SPACE_URL}"
    if [[ -n "${ALMANAC_SSOT_NOTION_SPACE_KIND:-}" || -n "${ALMANAC_SSOT_NOTION_SPACE_ID:-}" ]]; then
      echo "  ${ALMANAC_SSOT_NOTION_SPACE_KIND:-object} ${ALMANAC_SSOT_NOTION_SPACE_ID:-}"
    fi
  else
    echo "No shared Notion SSOT target is configured yet."
  fi
  echo

  local notion_index_roots=""

  notion_space_url="$(normalize_optional_answer "$(ask "Shared Notion page URL for Almanac (use a normal page, not the workspace Home screen) (ENTER keeps current, type none to clear)" "${ALMANAC_SSOT_NOTION_SPACE_URL:-}")")"
  notion_api_version="$(normalize_optional_answer "$(ask "Notion API version" "${ALMANAC_SSOT_NOTION_API_VERSION:-2026-03-11}")")"
  notion_api_version="${notion_api_version:-2026-03-11}"
  notion_token="$(ask_secret_with_default "Notion Internal Integration Secret for your Almanac internal integration (start at https://www.notion.so/profile/integrations/internal) (ENTER keeps current, type none to clear)" "${ALMANAC_SSOT_NOTION_TOKEN:-}")"
  notion_public_webhook_url="${ALMANAC_NOTION_WEBHOOK_PUBLIC_URL:-}"

  if [[ -z "$notion_space_url" && -z "$notion_token" ]]; then
    ALMANAC_SSOT_NOTION_ROOT_PAGE_URL=""
    ALMANAC_SSOT_NOTION_ROOT_PAGE_ID=""
    ALMANAC_SSOT_NOTION_SPACE_URL=""
    ALMANAC_SSOT_NOTION_SPACE_ID=""
    ALMANAC_SSOT_NOTION_SPACE_KIND=""
    ALMANAC_SSOT_NOTION_API_VERSION="$notion_api_version"
    ALMANAC_SSOT_NOTION_TOKEN=""
    ALMANAC_NOTION_INDEX_ROOTS=""
    ALMANAC_NOTION_WEBHOOK_PUBLIC_URL=""
    write_runtime_config "$CONFIG_TARGET"
    if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
      chown "$ALMANAC_USER:$ALMANAC_USER" "$CONFIG_TARGET" >/dev/null 2>&1 || true
    fi
    echo
    echo "Cleared shared Notion SSOT configuration in $CONFIG_TARGET."
    return 0
  fi

  if [[ -z "$notion_space_url" || -z "$notion_token" ]]; then
    echo "Notion SSOT setup needs both a Notion page URL and an integration secret, or neither if you are clearing it." >&2
    exit 1
  fi

  handshake_file="$(mktemp)"
  notion_token_file="$(mktemp)"
  chmod 600 "$notion_token_file" || true
  printf '%s\n' "$notion_token" >"$notion_token_file"
  if ! env \
    ALMANAC_CONFIG_FILE="$CONFIG_TARGET" \
    "$BOOTSTRAP_DIR/bin/almanac-ctl" --json notion handshake \
      --space-url "$notion_space_url" \
      --token-file "$notion_token_file" \
      --api-version "$notion_api_version" >"$handshake_file"; then
    rm -f "$handshake_file" "$notion_token_file"
    echo "Notion handshake failed; leaving the current config unchanged." >&2
    exit 1
  fi

  space_id="$(python3 - "$handshake_file" <<'PY'
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)
print(str(data.get("space_id") or "").strip())
PY
)"
  space_kind="$(python3 - "$handshake_file" <<'PY'
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)
print(str(data.get("space_kind") or "").strip())
PY
)"
  space_title="$(python3 - "$handshake_file" <<'PY'
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)
print(str(data.get("space_title") or "").strip())
PY
)"
  target_url="$(python3 - "$handshake_file" <<'PY'
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)
print(str(data.get("target_url") or "").strip())
PY
)"
  notion_space_url="$(python3 - "$handshake_file" <<'PY'
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)
print(str(data.get("space_url") or "").strip())
PY
)"
  root_page_id="$(python3 - "$handshake_file" <<'PY'
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)
print(str(data.get("root_page_id") or "").strip())
PY
)"
  root_page_url="$(python3 - "$handshake_file" <<'PY'
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)
print(str(data.get("root_page_url") or "").strip())
PY
)"
  root_page_title="$(python3 - "$handshake_file" <<'PY'
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)
print(str(data.get("root_page_title") or "").strip())
PY
)"
  integration_name="$(python3 - "$handshake_file" <<'PY'
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)
integration = data.get("integration") or {}
print(str(integration.get("name") or "").strip())
PY
)"
  workspace_name="$(python3 - "$handshake_file" <<'PY'
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)
integration = data.get("integration") or {}
print(str(integration.get("workspace_name") or "").strip())
PY
)"
  if ! env \
    ALMANAC_CONFIG_FILE="$CONFIG_TARGET" \
    "$BOOTSTRAP_DIR/bin/almanac-ctl" --json notion preflight-root \
      --root-page-id "$root_page_id" \
      --token-file "$notion_token_file" \
      --api-version "$notion_api_version" >/dev/null; then
    rm -f "$handshake_file" "$notion_token_file"
    echo "Notion root preflight failed; leaving the current config unchanged." >&2
    exit 1
  fi

  notion_index_roots="$(normalize_optional_answer "$(ask "Shared Notion index roots (comma-separated page/database URLs or IDs; ENTER keeps current/default root)" "${ALMANAC_NOTION_INDEX_ROOTS:-$root_page_url}")")"
  notion_index_roots="${notion_index_roots:-$root_page_url}"

  ALMANAC_SSOT_NOTION_ROOT_PAGE_URL="$root_page_url"
  ALMANAC_SSOT_NOTION_ROOT_PAGE_ID="$root_page_id"
  ALMANAC_SSOT_NOTION_SPACE_URL="$notion_space_url"
  ALMANAC_SSOT_NOTION_SPACE_ID="$space_id"
  ALMANAC_SSOT_NOTION_SPACE_KIND="$space_kind"
  ALMANAC_SSOT_NOTION_API_VERSION="$notion_api_version"
  ALMANAC_SSOT_NOTION_TOKEN="$notion_token"
  ALMANAC_NOTION_INDEX_ROOTS="$notion_index_roots"
  ALMANAC_NOTION_WEBHOOK_PUBLIC_URL="$notion_public_webhook_url"
  write_runtime_config "$CONFIG_TARGET"
  rm -f "$handshake_file" "$notion_token_file"
  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    chown "$ALMANAC_USER:$ALMANAC_USER" "$CONFIG_TARGET" >/dev/null 2>&1 || true
  fi
  reload_runtime_config_from_file "$CONFIG_TARGET" || true

  echo
  echo "Notion handshake succeeded."
  echo "Integration:"
  echo "  ${integration_name:-Notion integration}"
  if [[ -n "$workspace_name" ]]; then
    echo "Workspace:"
    echo "  $workspace_name"
  fi
  echo "Root page:"
  echo "  ${root_page_title:-$root_page_id}"
  echo "  ${root_page_id:-unknown}"
  echo "Shared SSOT target:"
  echo "  ${space_kind:-object} ${space_id:-}"
  if [[ -n "$space_title" ]]; then
    echo "  $space_title"
  fi
  echo "Shared Notion index roots:"
  echo "  ${ALMANAC_NOTION_INDEX_ROOTS:-$root_page_url}"
  echo "Resolved URL:"
  echo "  ${target_url:-$notion_space_url}"
  if [[ -n "${ALMANAC_NOTION_WEBHOOK_PUBLIC_URL:-}" ]]; then
    echo "Webhook URL:"
    echo "  ${ALMANAC_NOTION_WEBHOOK_PUBLIC_URL}"
    echo "Webhook subscription checklist:"
    echo "  1. Open the Notion Developer Portal for this integration and go to Webhooks."
    echo "  2. If a subscription already exists for this exact URL, edit it instead of creating a duplicate:"
    echo "     ${ALMANAC_NOTION_WEBHOOK_PUBLIC_URL}"
    echo "  3. Select events exactly as follows:"
    echo "     - Page: all Page events"
    echo "     - Database: all Database events"
    echo "     - Data source: all Data source events"
    echo "     - File uploads: all File upload events"
    echo "     - View: leave unchecked"
    echo "     - Comment: leave unchecked"
    echo "  4. deploy.sh notion-ssot will walk you through the Webhooks tab step by step, arm the install window, wait for Notion to send the token, and print the verification_token for you."
    echo "  5. Paste that verification_token into Notion and click Verify when deploy tells you to."
  fi
  echo "Config persisted to:"
  echo "  $CONFIG_TARGET"

  if [[ -n "${ALMANAC_NOTION_WEBHOOK_PUBLIC_URL:-}" ]]; then
    if ! run_notion_webhook_setup_flow "$BOOTSTRAP_DIR/bin/almanac-ctl" "${SUDO_USER:-$(id -un)}"; then
      rm -f "$handshake_file"
      echo "Shared Notion configuration was saved, but webhook verification is still incomplete." >&2
      exit 1
    fi
  fi

  rm -f "$handshake_file"
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
      systemctl --user restart almanac-mcp.service almanac-notion-webhook.service almanac-qmd-mcp.service almanac-qmd-update.timer almanac-vault-watch.service almanac-github-backup.timer almanac-ssot-batcher.timer almanac-notification-delivery.timer almanac-health-watch.timer almanac-curator-refresh.timer
      systemctl --user start almanac-curator-refresh.service >/dev/null 2>&1 || true
      systemctl --user start almanac-health-watch.service >/dev/null 2>&1 || true
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
  require_supported_host_mode "upgrade"
  prepare_deployed_context

  if [[ ${EUID:-$(id -u)} -ne 0 && -n "${CONFIG_TARGET:-}" && ! -r "$CONFIG_TARGET" ]]; then
    echo "Switching to sudo to inspect the deployed config..."
    if ! sudo env \
      ALMANAC_CONFIG_FILE="$CONFIG_TARGET" \
      ALMANAC_UPSTREAM_REPO_URL="${ALMANAC_UPSTREAM_REPO_URL:-}" \
      ALMANAC_UPSTREAM_BRANCH="${ALMANAC_UPSTREAM_BRANCH:-}" \
      ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED="${ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED:-}" \
      ALMANAC_UPSTREAM_DEPLOY_KEY_USER="${ALMANAC_UPSTREAM_DEPLOY_KEY_USER:-}" \
      ALMANAC_UPSTREAM_DEPLOY_KEY_PATH="${ALMANAC_UPSTREAM_DEPLOY_KEY_PATH:-}" \
      ALMANAC_UPSTREAM_KNOWN_HOSTS_FILE="${ALMANAC_UPSTREAM_KNOWN_HOSTS_FILE:-}" \
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
  echo "Upstream: ${ALMANAC_UPSTREAM_REPO_URL:-https://github.com/example/almanac.git}#${ALMANAC_UPSTREAM_BRANCH:-main}"
  echo "Target:   $ALMANAC_REPO_DIR"

  require_main_upstream_branch_for_upgrade

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
    ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED="${ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED:-}" \
    ALMANAC_UPSTREAM_DEPLOY_KEY_USER="${ALMANAC_UPSTREAM_DEPLOY_KEY_USER:-}" \
    ALMANAC_UPSTREAM_DEPLOY_KEY_PATH="${ALMANAC_UPSTREAM_DEPLOY_KEY_PATH:-}" \
    ALMANAC_UPSTREAM_KNOWN_HOSTS_FILE="${ALMANAC_UPSTREAM_KNOWN_HOSTS_FILE:-}" \
    "$SELF_PATH" --apply-upgrade; then
    return 1
  fi
  write_operator_checkout_artifact
}

run_agent_payload() {
  load_detected_config || true

  ALMANAC_USER="${ALMANAC_USER:-almanac}"
  ALMANAC_HOME="${ALMANAC_HOME:-$(default_home_for_user "$ALMANAC_USER")}"
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

docker_command_from_mode() {
  case "$1" in
    docker-install) printf '%s\n' "install" ;;
    docker-upgrade) printf '%s\n' "upgrade" ;;
    docker-reconfigure) printf '%s\n' "reconfigure" ;;
    docker-bootstrap) printf '%s\n' "bootstrap" ;;
    docker-config) printf '%s\n' "config" ;;
    docker-build) printf '%s\n' "build" ;;
    docker-up) printf '%s\n' "up" ;;
    docker-down) printf '%s\n' "down" ;;
    docker-ps) printf '%s\n' "ps" ;;
    docker-ports) printf '%s\n' "ports" ;;
    docker-logs) printf '%s\n' "logs" ;;
    docker-health) printf '%s\n' "health" ;;
    docker-teardown) printf '%s\n' "teardown" ;;
    docker-write-config) printf '%s\n' "write-config" ;;
    docker-remove) printf '%s\n' "remove" ;;
    docker-notion-ssot) printf '%s\n' "notion-ssot" ;;
    docker-enrollment-status) printf '%s\n' "enrollment-status" ;;
    docker-enrollment-trace) printf '%s\n' "enrollment-trace" ;;
    docker-enrollment-align) printf '%s\n' "enrollment-align" ;;
    docker-enrollment-reset) printf '%s\n' "enrollment-reset" ;;
    docker-curator-setup) printf '%s\n' "curator-setup" ;;
    docker-rotate-nextcloud-secrets) printf '%s\n' "rotate-nextcloud-secrets" ;;
    docker-agent-payload) printf '%s\n' "agent-payload" ;;
    docker-pins-show) printf '%s\n' "pins-show" ;;
    docker-pins-check) printf '%s\n' "pins-check" ;;
    docker-pin-upgrade-notify) printf '%s\n' "pin-upgrade-notify" ;;
    docker-hermes-upgrade) printf '%s\n' "hermes-upgrade" ;;
    docker-hermes-upgrade-check) printf '%s\n' "hermes-upgrade-check" ;;
    docker-qmd-upgrade) printf '%s\n' "qmd-upgrade" ;;
    docker-qmd-upgrade-check) printf '%s\n' "qmd-upgrade-check" ;;
    docker-nextcloud-upgrade) printf '%s\n' "nextcloud-upgrade" ;;
    docker-nextcloud-upgrade-check) printf '%s\n' "nextcloud-upgrade-check" ;;
    docker-postgres-upgrade) printf '%s\n' "postgres-upgrade" ;;
    docker-postgres-upgrade-check) printf '%s\n' "postgres-upgrade-check" ;;
    docker-redis-upgrade) printf '%s\n' "redis-upgrade" ;;
    docker-redis-upgrade-check) printf '%s\n' "redis-upgrade-check" ;;
    docker-code-server-upgrade) printf '%s\n' "code-server-upgrade" ;;
    docker-code-server-upgrade-check) printf '%s\n' "code-server-upgrade-check" ;;
    docker-nvm-upgrade) printf '%s\n' "nvm-upgrade" ;;
    docker-nvm-upgrade-check) printf '%s\n' "nvm-upgrade-check" ;;
    docker-node-upgrade) printf '%s\n' "node-upgrade" ;;
    docker-node-upgrade-check) printf '%s\n' "node-upgrade-check" ;;
    *) printf '%s\n' "" ;;
  esac
}

run_almanac_docker() {
  local helper="$BOOTSTRAP_DIR/bin/almanac-docker.sh"

  if [[ ! -x "$helper" ]]; then
    echo "Docker helper is missing or not executable: $helper" >&2
    return 1
  fi

  "$helper" "$@"
}

run_docker_install_flow() {
  echo "Installing or repairing Almanac Docker stack from this checkout..."
  run_almanac_docker bootstrap
  run_almanac_docker build
  run_almanac_docker up
  run_almanac_docker ports
  run_almanac_docker health
}

run_docker_reconfigure_flow() {
  echo "Refreshing Almanac Docker generated config and port assignments..."
  run_almanac_docker bootstrap
  run_almanac_docker config -q
  run_almanac_docker ports
}

run_docker_deploy_flow() {
  local command="${DOCKER_DEPLOY_COMMAND:-}"

  if [[ "$MODE" != "docker" ]]; then
    command="$(docker_command_from_mode "$MODE")"
  fi
  if [[ -z "$command" || "$command" == "menu" ]]; then
    choose_docker_mode
    command="${DOCKER_DEPLOY_COMMAND:-}"
  fi

  case "$command" in
    help|-h|--help)
      docker_usage
      ;;
    install|upgrade)
      run_docker_install_flow
      ;;
    reconfigure)
      run_docker_reconfigure_flow
      ;;
    bootstrap|write-config|config|build|up|down|ps|ports|logs|health|teardown|remove|notion-ssot|enrollment-status|enrollment-trace|enrollment-align|enrollment-reset|curator-setup|rotate-nextcloud-secrets|agent-payload|agent|pins-show|pins-check|pin-upgrade-notify|hermes-upgrade|hermes-upgrade-check|qmd-upgrade|qmd-upgrade-check|nextcloud-upgrade|nextcloud-upgrade-check|postgres-upgrade|postgres-upgrade-check|redis-upgrade|redis-upgrade-check|code-server-upgrade|code-server-upgrade-check|nvm-upgrade|nvm-upgrade-check|node-upgrade|node-upgrade-check)
      run_almanac_docker "$command" ${DOCKER_DEPLOY_ARGS[@]+"${DOCKER_DEPLOY_ARGS[@]}"}
      ;;
    *)
      echo "Unknown Docker deploy command: ${command:-<empty>}" >&2
      docker_usage >&2
      return 2
      ;;
  esac
}

run_install_flow() {
  local reexec_status=""

  if maybe_reexec_install_for_config_defaults "$MODE"; then
    return 0
  else
    reexec_status="$?"
    if [[ "${ALMANAC_REEXEC_ATTEMPTED:-0}" == "1" ]]; then
      return "$reexec_status"
    fi
  fi

  require_supported_host_mode "$MODE"

  collect_install_answers
  prepare_operator_upstream_deploy_key_before_sudo

  if [[ "$MODE" == "write-config" ]]; then
    seed_private_repo "$ALMANAC_PRIV_DIR"
    write_runtime_config "$CONFIG_TARGET"
    maybe_run_org_profile_builder "$BOOTSTRAP_DIR"
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
  trap 'rm -f "${ANSWERS_FILE:-}"' EXIT
  write_answers_file "$ANSWERS_FILE"
  echo
  echo "Switching to sudo for system setup..."
  if ! sudo env ALMANAC_INSTALL_ANSWERS_FILE="$ANSWERS_FILE" "$SELF_PATH" --apply-install; then
    return 1
  fi
  rm -f "$ANSWERS_FILE"
  trap - EXIT
  write_operator_checkout_artifact
}

run_remove_flow() {
  require_supported_host_mode "remove"
  collect_remove_answers

  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    run_root_remove
    return 0
  fi

  ANSWERS_FILE="$(mktemp /tmp/almanac-remove.XXXXXX.env)"
  trap 'rm -f "${ANSWERS_FILE:-}"' EXIT
  write_answers_file "$ANSWERS_FILE"
  echo
  echo "Switching to sudo for teardown..."
  if ! sudo env ALMANAC_INSTALL_ANSWERS_FILE="$ANSWERS_FILE" "$SELF_PATH" --apply-remove; then
    return 1
  fi
  rm -f "$ANSWERS_FILE"
  trap - EXIT
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
  docker|docker-install|docker-upgrade|docker-reconfigure|docker-bootstrap|docker-config|docker-build|docker-up|docker-down|docker-ps|docker-ports|docker-logs|docker-health|docker-teardown|docker-write-config|docker-remove|docker-notion-ssot|docker-enrollment-status|docker-enrollment-trace|docker-enrollment-align|docker-enrollment-reset|docker-curator-setup|docker-rotate-nextcloud-secrets|docker-agent-payload|docker-pins-show|docker-pins-check|docker-pin-upgrade-notify|docker-hermes-upgrade|docker-hermes-upgrade-check|docker-qmd-upgrade|docker-qmd-upgrade-check|docker-nextcloud-upgrade|docker-nextcloud-upgrade-check|docker-postgres-upgrade|docker-postgres-upgrade-check|docker-redis-upgrade|docker-redis-upgrade-check|docker-code-server-upgrade|docker-code-server-upgrade-check|docker-nvm-upgrade|docker-nvm-upgrade-check|docker-node-upgrade|docker-node-upgrade-check)
    run_docker_deploy_flow
    ;;
  install|write-config)
    run_install_flow
    ;;
  upgrade)
    run_upgrade_flow
    ;;
  notion-ssot)
    run_notion_ssot_setup
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
  rotate-nextcloud-secrets)
    run_rotate_nextcloud_secrets
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
  pins-show)
    run_pins_show
    ;;
  pins-check)
    run_pins_check
    ;;
  pin-upgrade-notify)
    run_pin_upgrade_notify
    ;;
  hermes-upgrade-check)        run_hermes_upgrade_check ;;
  hermes-upgrade)              run_hermes_upgrade ;;
  qmd-upgrade-check)           run_qmd_upgrade_check ;;
  qmd-upgrade)                 run_qmd_upgrade ;;
  nextcloud-upgrade-check)     run_nextcloud_upgrade_check ;;
  nextcloud-upgrade)           run_nextcloud_upgrade ;;
  postgres-upgrade-check)      run_postgres_upgrade_check ;;
  postgres-upgrade)            run_postgres_upgrade ;;
  redis-upgrade-check)         run_redis_upgrade_check ;;
  redis-upgrade)               run_redis_upgrade ;;
  code-server-upgrade-check)   run_code_server_upgrade_check ;;
  code-server-upgrade)         run_code_server_upgrade ;;
  nvm-upgrade-check)           run_nvm_upgrade_check ;;
  nvm-upgrade)                 run_nvm_upgrade ;;
  node-upgrade-check)          run_node_upgrade_check ;;
  node-upgrade)                run_node_upgrade ;;
  *)
    usage >&2
    exit 1
    ;;
esac
