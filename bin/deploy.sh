#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${ARCLINK_DEPLOY_BOOTSTRAP_DIR:-}" ]]; then
  BOOTSTRAP_DIR="$(cd "$ARCLINK_DEPLOY_BOOTSTRAP_DIR" && pwd)"
else
  BOOTSTRAP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
fi
SELF_PATH="$BOOTSTRAP_DIR/bin/deploy.sh"
DEPLOY_EXEC_PATH="${ARCLINK_DEPLOY_EXEC_PATH:-$SELF_PATH}"
if [[ "${ARCLINK_DEPLOY_STABLE_COPY:-0}" != "1" && "${ARCLINK_DEPLOY_DISABLE_STABLE_COPY:-0}" != "1" ]]; then
  DEPLOY_EXEC_PATH="$(mktemp "${TMPDIR:-/tmp}/arclink-deploy.XXXXXX")"
  cp "$SELF_PATH" "$DEPLOY_EXEC_PATH"
  chmod 700 "$DEPLOY_EXEC_PATH"
  export ARCLINK_DEPLOY_BOOTSTRAP_DIR="$BOOTSTRAP_DIR"
  export ARCLINK_DEPLOY_EXEC_PATH="$DEPLOY_EXEC_PATH"
  export ARCLINK_DEPLOY_STABLE_COPY=1
  export ARCLINK_DEPLOY_STABLE_OWNER_PID="$$"
  exec bash "$DEPLOY_EXEC_PATH" "$@"
fi
if [[ "${ARCLINK_DEPLOY_STABLE_COPY:-0}" == "1" && "${ARCLINK_DEPLOY_STABLE_OWNER_PID:-}" == "$$" ]]; then
  trap 'arclink_deploy_stable_copy_cleanup' EXIT
fi
ANSWERS_FILE="${ARCLINK_INSTALL_ANSWERS_FILE:-}"
MODE=""
PRIVILEGED_MODE=""
CONTROL_DEPLOY_COMMAND=""
CONTROL_DEPLOY_ARGS=()
DOCKER_DEPLOY_COMMAND=""
DOCKER_DEPLOY_ARGS=()
DISCOVERED_CONFIG=""
ARCLINK_REEXEC_ATTEMPTED=0
ARCLINK_NAME="${ARCLINK_NAME:-arclink}"
TRACE_UNIX_USER="${TRACE_UNIX_USER:-}"
TRACE_SESSION_ID="${TRACE_SESSION_ID:-}"
TRACE_REQUEST_ID="${TRACE_REQUEST_ID:-}"
TRACE_LOG_LINES="${TRACE_LOG_LINES:-12}"
QMD_MCP_PORT="${QMD_MCP_PORT:-8181}"
QMD_EMBED_PROVIDER="${QMD_EMBED_PROVIDER:-local}"
QMD_EMBED_ENDPOINT="${QMD_EMBED_ENDPOINT:-}"
QMD_EMBED_ENDPOINT_MODEL="${QMD_EMBED_ENDPOINT_MODEL:-}"
QMD_EMBED_API_KEY="${QMD_EMBED_API_KEY:-}"
QMD_EMBED_DIMENSIONS="${QMD_EMBED_DIMENSIONS:-}"
QMD_EMBED_TIMEOUT_SECONDS="${QMD_EMBED_TIMEOUT_SECONDS:-120}"
QMD_EMBED_MAX_DOCS_PER_BATCH="${QMD_EMBED_MAX_DOCS_PER_BATCH:-8}"
QMD_EMBED_MAX_BATCH_MB="${QMD_EMBED_MAX_BATCH_MB:-16}"
QMD_EMBED_FORCE_ON_NEXT_REFRESH="${QMD_EMBED_FORCE_ON_NEXT_REFRESH:-0}"
PDF_INGEST_ENABLED="${PDF_INGEST_ENABLED:-1}"
PDF_INGEST_EXTRACTOR="${PDF_INGEST_EXTRACTOR:-auto}"
PDF_INGEST_COLLECTION_NAME="${PDF_INGEST_COLLECTION_NAME:-vault-pdf-ingest}"
VAULT_QMD_COLLECTION_MASK="${VAULT_QMD_COLLECTION_MASK:-**/*.{md,markdown,mdx,txt,text}}"
PDF_VISION_ENDPOINT="${PDF_VISION_ENDPOINT:-}"
PDF_VISION_MODEL="${PDF_VISION_MODEL:-}"
PDF_VISION_API_KEY="${PDF_VISION_API_KEY:-}"
PDF_VISION_MAX_PAGES="${PDF_VISION_MAX_PAGES:-6}"
ARCLINK_MEMORY_SYNTH_ENABLED="${ARCLINK_MEMORY_SYNTH_ENABLED:-auto}"
ARCLINK_MEMORY_SYNTH_ENDPOINT="${ARCLINK_MEMORY_SYNTH_ENDPOINT:-}"
ARCLINK_MEMORY_SYNTH_MODEL="${ARCLINK_MEMORY_SYNTH_MODEL:-}"
ARCLINK_MEMORY_SYNTH_API_KEY="${ARCLINK_MEMORY_SYNTH_API_KEY:-}"
ARCLINK_MEMORY_SYNTH_MAX_SOURCES_PER_RUN="${ARCLINK_MEMORY_SYNTH_MAX_SOURCES_PER_RUN:-12}"
ARCLINK_MEMORY_SYNTH_MAX_SOURCE_CHARS="${ARCLINK_MEMORY_SYNTH_MAX_SOURCE_CHARS:-4500}"
ARCLINK_MEMORY_SYNTH_MAX_OUTPUT_TOKENS="${ARCLINK_MEMORY_SYNTH_MAX_OUTPUT_TOKENS:-450}"
ARCLINK_MEMORY_SYNTH_TIMEOUT_SECONDS="${ARCLINK_MEMORY_SYNTH_TIMEOUT_SECONDS:-60}"
ARCLINK_MEMORY_SYNTH_FAILURE_RETRY_SECONDS="${ARCLINK_MEMORY_SYNTH_FAILURE_RETRY_SECONDS:-3600}"
ARCLINK_MEMORY_SYNTH_CARDS_IN_CONTEXT="${ARCLINK_MEMORY_SYNTH_CARDS_IN_CONTEXT:-8}"
ARCLINK_MEMORY_SYNTH_ON_VAULT_CHANGE="${ARCLINK_MEMORY_SYNTH_ON_VAULT_CHANGE:-1}"
NEXTCLOUD_TRUSTED_DOMAIN="${NEXTCLOUD_TRUSTED_DOMAIN:-arclink.your-tailnet.ts.net}"
NEXTCLOUD_VAULT_MOUNT_POINT="${NEXTCLOUD_VAULT_MOUNT_POINT:-/Vault}"
ENABLE_NEXTCLOUD="${ENABLE_NEXTCLOUD:-1}"
ENABLE_TAILSCALE_SERVE="${ENABLE_TAILSCALE_SERVE:-0}"
TAILSCALE_SERVE_PORT="${TAILSCALE_SERVE_PORT:-443}"
ARCLINK_INSTALL_PODMAN="${ARCLINK_INSTALL_PODMAN:-auto}"
ARCLINK_INSTALL_TAILSCALE="${ARCLINK_INSTALL_TAILSCALE:-auto}"
TAILSCALE_OPERATOR_USER="${TAILSCALE_OPERATOR_USER:-}"
TAILSCALE_QMD_PATH="${TAILSCALE_QMD_PATH:-/mcp}"
TAILSCALE_ARCLINK_MCP_PATH="${TAILSCALE_ARCLINK_MCP_PATH:-/arclink-mcp}"
ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL="${ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL:-0}"
TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT="${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-443}"
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
ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED="${ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED:-0}"
ARCLINK_UPSTREAM_DEPLOY_KEY_USER="${ARCLINK_UPSTREAM_DEPLOY_KEY_USER:-}"
ARCLINK_UPSTREAM_DEPLOY_KEY_PATH="${ARCLINK_UPSTREAM_DEPLOY_KEY_PATH:-}"
ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE="${ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE:-}"
ARCLINK_MCP_HOST="${ARCLINK_MCP_HOST:-127.0.0.1}"
ARCLINK_MCP_PORT="${ARCLINK_MCP_PORT:-8282}"
ARCLINK_NOTION_WEBHOOK_HOST="${ARCLINK_NOTION_WEBHOOK_HOST:-127.0.0.1}"
ARCLINK_NOTION_WEBHOOK_PORT="${ARCLINK_NOTION_WEBHOOK_PORT:-8283}"
ARCLINK_NOTION_WEBHOOK_PUBLIC_URL="${ARCLINK_NOTION_WEBHOOK_PUBLIC_URL:-}"
ARCLINK_PRODUCT_NAME="${ARCLINK_PRODUCT_NAME:-ArcLink}"
ARCLINK_BASE_DOMAIN="${ARCLINK_BASE_DOMAIN:-arclink.online}"
ARCLINK_INGRESS_MODE="${ARCLINK_INGRESS_MODE:-domain}"
ARCLINK_TAILSCALE_DNS_NAME="${ARCLINK_TAILSCALE_DNS_NAME:-}"
ARCLINK_TAILSCALE_CONTROL_URL="${ARCLINK_TAILSCALE_CONTROL_URL:-}"
ARCLINK_TAILSCALE_HTTPS_PORT="${ARCLINK_TAILSCALE_HTTPS_PORT:-443}"
ARCLINK_TAILSCALE_NOTION_PATH="${ARCLINK_TAILSCALE_NOTION_PATH:-/notion/webhook}"
ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY="${ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY:-path}"
ARCLINK_PRIMARY_PROVIDER="${ARCLINK_PRIMARY_PROVIDER:-chutes}"
ARCLINK_API_HOST="${ARCLINK_API_HOST:-127.0.0.1}"
ARCLINK_API_PORT="${ARCLINK_API_PORT:-8900}"
ARCLINK_WEB_PORT="${ARCLINK_WEB_PORT:-3000}"
ARCLINK_CORS_ORIGIN="${ARCLINK_CORS_ORIGIN:-}"
ARCLINK_COOKIE_DOMAIN="${ARCLINK_COOKIE_DOMAIN:-}"
ARCLINK_DEFAULT_PRICE_ID="${ARCLINK_DEFAULT_PRICE_ID:-price_arclink_starter}"
ARCLINK_FIRST_AGENT_PRICE_ID="${ARCLINK_FIRST_AGENT_PRICE_ID:-$ARCLINK_DEFAULT_PRICE_ID}"
ARCLINK_ADDITIONAL_AGENT_PRICE_ID="${ARCLINK_ADDITIONAL_AGENT_PRICE_ID:-price_arclink_additional_agent}"
ARCLINK_FIRST_AGENT_MONTHLY_CENTS="${ARCLINK_FIRST_AGENT_MONTHLY_CENTS:-3500}"
ARCLINK_ADDITIONAL_AGENT_MONTHLY_CENTS="${ARCLINK_ADDITIONAL_AGENT_MONTHLY_CENTS:-1500}"
ARCLINK_CONTROL_PROVISIONER_ENABLED="${ARCLINK_CONTROL_PROVISIONER_ENABLED:-0}"
ARCLINK_CONTROL_PROVISIONER_INTERVAL_SECONDS="${ARCLINK_CONTROL_PROVISIONER_INTERVAL_SECONDS:-30}"
ARCLINK_CONTROL_PROVISIONER_BATCH_SIZE="${ARCLINK_CONTROL_PROVISIONER_BATCH_SIZE:-5}"
ARCLINK_SOVEREIGN_PROVISION_MAX_ATTEMPTS="${ARCLINK_SOVEREIGN_PROVISION_MAX_ATTEMPTS:-5}"
ARCLINK_EXECUTOR_ADAPTER="${ARCLINK_EXECUTOR_ADAPTER:-disabled}"
ARCLINK_EDGE_TARGET="${ARCLINK_EDGE_TARGET:-edge.arclink.online}"
ARCLINK_STATE_ROOT_BASE="${ARCLINK_STATE_ROOT_BASE:-/arcdata/deployments}"
ARCLINK_SECRET_STORE_DIR="${ARCLINK_SECRET_STORE_DIR:-}"
ARCLINK_REGISTER_LOCAL_FLEET_HOST="${ARCLINK_REGISTER_LOCAL_FLEET_HOST:-0}"
ARCLINK_LOCAL_FLEET_HOSTNAME="${ARCLINK_LOCAL_FLEET_HOSTNAME:-}"
ARCLINK_LOCAL_FLEET_SSH_HOST="${ARCLINK_LOCAL_FLEET_SSH_HOST:-}"
ARCLINK_LOCAL_FLEET_SSH_USER="${ARCLINK_LOCAL_FLEET_SSH_USER:-arclink}"
ARCLINK_LOCAL_FLEET_REGION="${ARCLINK_LOCAL_FLEET_REGION:-}"
ARCLINK_LOCAL_FLEET_CAPACITY_SLOTS="${ARCLINK_LOCAL_FLEET_CAPACITY_SLOTS:-4}"
ARCLINK_FLEET_SSH_KEY_PATH="${ARCLINK_FLEET_SSH_KEY_PATH:-}"
ARCLINK_FLEET_SSH_KNOWN_HOSTS_FILE="${ARCLINK_FLEET_SSH_KNOWN_HOSTS_FILE:-}"
STRIPE_SECRET_KEY="${STRIPE_SECRET_KEY:-}"
STRIPE_WEBHOOK_SECRET="${STRIPE_WEBHOOK_SECRET:-}"
CLOUDFLARE_API_TOKEN="${CLOUDFLARE_API_TOKEN:-}"
CLOUDFLARE_ZONE_ID="${CLOUDFLARE_ZONE_ID:-}"
CHUTES_API_KEY="${CHUTES_API_KEY:-}"
ARCLINK_SSOT_NOTION_ROOT_PAGE_URL="${ARCLINK_SSOT_NOTION_ROOT_PAGE_URL:-}"
ARCLINK_SSOT_NOTION_ROOT_PAGE_ID="${ARCLINK_SSOT_NOTION_ROOT_PAGE_ID:-}"
ARCLINK_SSOT_NOTION_SPACE_URL="${ARCLINK_SSOT_NOTION_SPACE_URL:-}"
ARCLINK_SSOT_NOTION_SPACE_ID="${ARCLINK_SSOT_NOTION_SPACE_ID:-}"
ARCLINK_SSOT_NOTION_SPACE_KIND="${ARCLINK_SSOT_NOTION_SPACE_KIND:-}"
ARCLINK_SSOT_NOTION_API_VERSION="${ARCLINK_SSOT_NOTION_API_VERSION:-2026-03-11}"
ARCLINK_SSOT_NOTION_TOKEN="${ARCLINK_SSOT_NOTION_TOKEN:-}"
ARCLINK_NOTION_INDEX_ROOTS="${ARCLINK_NOTION_INDEX_ROOTS:-}"
ARCLINK_NOTION_INDEX_RUN_EMBED="${ARCLINK_NOTION_INDEX_RUN_EMBED:-1}"
ARCLINK_ORG_NAME="${ARCLINK_ORG_NAME:-}"
ARCLINK_ORG_MISSION="${ARCLINK_ORG_MISSION:-}"
ARCLINK_ORG_PRIMARY_PROJECT="${ARCLINK_ORG_PRIMARY_PROJECT:-}"
ARCLINK_ORG_TIMEZONE="${ARCLINK_ORG_TIMEZONE:-Etc/UTC}"
ARCLINK_ORG_QUIET_HOURS="${ARCLINK_ORG_QUIET_HOURS:-}"
ARCLINK_ORG_PROFILE_BUILDER_ENABLED="${ARCLINK_ORG_PROFILE_BUILDER_ENABLED:-}"
ARCLINK_BOOTSTRAP_WINDOW_SECONDS="${ARCLINK_BOOTSTRAP_WINDOW_SECONDS:-3600}"
ARCLINK_BOOTSTRAP_PER_IP_LIMIT="${ARCLINK_BOOTSTRAP_PER_IP_LIMIT:-5}"
ARCLINK_BOOTSTRAP_GLOBAL_PENDING_LIMIT="${ARCLINK_BOOTSTRAP_GLOBAL_PENDING_LIMIT:-20}"
ARCLINK_BOOTSTRAP_PENDING_TTL_SECONDS="${ARCLINK_BOOTSTRAP_PENDING_TTL_SECONDS:-900}"
ARCLINK_AUTO_PROVISION_MAX_ATTEMPTS="${ARCLINK_AUTO_PROVISION_MAX_ATTEMPTS:-5}"
ARCLINK_AUTO_PROVISION_RETRY_BASE_SECONDS="${ARCLINK_AUTO_PROVISION_RETRY_BASE_SECONDS:-60}"
ARCLINK_AUTO_PROVISION_RETRY_MAX_SECONDS="${ARCLINK_AUTO_PROVISION_RETRY_MAX_SECONDS:-900}"
OPERATOR_NOTIFY_CHANNEL_PLATFORM="${OPERATOR_NOTIFY_CHANNEL_PLATFORM:-tui-only}"
OPERATOR_NOTIFY_CHANNEL_ID="${OPERATOR_NOTIFY_CHANNEL_ID:-}"
OPERATOR_GENERAL_CHANNEL_PLATFORM="${OPERATOR_GENERAL_CHANNEL_PLATFORM:-}"
OPERATOR_GENERAL_CHANNEL_ID="${OPERATOR_GENERAL_CHANNEL_ID:-}"
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_BOT_USERNAME="${TELEGRAM_BOT_USERNAME:-}"
TELEGRAM_WEBHOOK_URL="${TELEGRAM_WEBHOOK_URL:-}"
DISCORD_BOT_TOKEN="${DISCORD_BOT_TOKEN:-}"
DISCORD_APP_ID="${DISCORD_APP_ID:-}"
DISCORD_PUBLIC_KEY="${DISCORD_PUBLIC_KEY:-}"
. "$BOOTSTRAP_DIR/bin/model-providers.sh" 2>/dev/null || true
if declare -f model_provider_resolve_target_or_default >/dev/null 2>&1; then
  ARCLINK_MODEL_PRESET_CODEX="$(model_provider_resolve_target_or_default codex "${ARCLINK_MODEL_PRESET_CODEX:-}" "openai-codex:gpt-5.5")"
  ARCLINK_MODEL_PRESET_OPUS="$(model_provider_resolve_target_or_default opus "${ARCLINK_MODEL_PRESET_OPUS:-}" "anthropic:claude-opus-4-7")"
  ARCLINK_MODEL_PRESET_CHUTES="$(model_provider_resolve_target_or_default chutes "${ARCLINK_MODEL_PRESET_CHUTES:-}" "chutes:moonshotai/Kimi-K2.6-TEE")"
else
  ARCLINK_MODEL_PRESET_CODEX="${ARCLINK_MODEL_PRESET_CODEX:-openai-codex:gpt-5.5}"
  ARCLINK_MODEL_PRESET_OPUS="${ARCLINK_MODEL_PRESET_OPUS:-anthropic:claude-opus-4-7}"
  ARCLINK_MODEL_PRESET_CHUTES="${ARCLINK_MODEL_PRESET_CHUTES:-chutes:moonshotai/Kimi-K2.6-TEE}"
fi
ARCLINK_ORG_PROVIDER_ENABLED="${ARCLINK_ORG_PROVIDER_ENABLED:-}"
ARCLINK_ORG_PROVIDER_PRESET="${ARCLINK_ORG_PROVIDER_PRESET:-}"
ARCLINK_ORG_PROVIDER_MODEL_ID="${ARCLINK_ORG_PROVIDER_MODEL_ID:-}"
ARCLINK_ORG_PROVIDER_REASONING_EFFORT="${ARCLINK_ORG_PROVIDER_REASONING_EFFORT:-medium}"
ARCLINK_ORG_PROVIDER_SECRET_PROVIDER="${ARCLINK_ORG_PROVIDER_SECRET_PROVIDER:-}"
ARCLINK_ORG_PROVIDER_SECRET="${ARCLINK_ORG_PROVIDER_SECRET:-}"
ARCLINK_CURATOR_MODEL_PRESET="${ARCLINK_CURATOR_MODEL_PRESET:-codex}"
ARCLINK_CURATOR_CHANNELS="${ARCLINK_CURATOR_CHANNELS:-tui-only}"
ARCLINK_EXTRA_MCP_NAME="${ARCLINK_EXTRA_MCP_NAME:-external-kb}"
ARCLINK_EXTRA_MCP_LABEL="${ARCLINK_EXTRA_MCP_LABEL:-External knowledge rail}"
ARCLINK_EXTRA_MCP_URL="${ARCLINK_EXTRA_MCP_URL:-}"
__arclink_upstream_repo_default=""
__arclink_canonical_upstream_repo_url="https://github.com/sirouk/arclink.git"
if command -v git >/dev/null 2>&1; then
  __arclink_upstream_repo_default="$(git -C "$BOOTSTRAP_DIR" remote get-url origin 2>/dev/null || true)"
fi
__arclink_legacy_repo_name="alma""nac"
case "$__arclink_upstream_repo_default" in
  *github.com:sirouk/$__arclink_legacy_repo_name.git|*github.com/sirouk/$__arclink_legacy_repo_name|*github.com/sirouk/$__arclink_legacy_repo_name.git)
    __arclink_upstream_repo_default="$__arclink_canonical_upstream_repo_url"
    ;;
esac
ARCLINK_UPSTREAM_REPO_URL="${ARCLINK_UPSTREAM_REPO_URL:-${__arclink_upstream_repo_default:-$__arclink_canonical_upstream_repo_url}}"
unset __arclink_upstream_repo_default __arclink_legacy_repo_name __arclink_canonical_upstream_repo_url
__arclink_upstream_branch_default=""
if command -v git >/dev/null 2>&1; then
  __arclink_upstream_branch_default="$(git -C "$BOOTSTRAP_DIR" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
fi
ARCLINK_UPSTREAM_BRANCH="${ARCLINK_UPSTREAM_BRANCH:-${__arclink_upstream_branch_default:-arclink}}"
unset __arclink_upstream_branch_default
ARCLINK_AGENT_DASHBOARD_BACKEND_PORT_BASE="${ARCLINK_AGENT_DASHBOARD_BACKEND_PORT_BASE:-19000}"
ARCLINK_AGENT_DASHBOARD_PROXY_PORT_BASE="${ARCLINK_AGENT_DASHBOARD_PROXY_PORT_BASE:-29000}"
ARCLINK_AGENT_CODE_PORT_BASE="${ARCLINK_AGENT_CODE_PORT_BASE:-39000}"
ARCLINK_AGENT_PORT_SLOT_SPAN="${ARCLINK_AGENT_PORT_SLOT_SPAN:-5000}"
ARCLINK_AGENT_CODE_SERVER_IMAGE="${ARCLINK_AGENT_CODE_SERVER_IMAGE:-docker.io/codercom/code-server:4.116.0}"
ARCLINK_AGENT_ENABLE_TAILSCALE_SERVE="${ARCLINK_AGENT_ENABLE_TAILSCALE_SERVE:-$ENABLE_TAILSCALE_SERVE}"
ARCLINK_RELEASE_STATE_FILE="${ARCLINK_RELEASE_STATE_FILE:-}"
ARCLINK_OPERATOR_ARTIFACT_FILE="${ARCLINK_OPERATOR_ARTIFACT_FILE:-$BOOTSTRAP_DIR/.arclink-operator.env}"
NEXTCLOUD_ROTATE_POSTGRES_PASSWORD="${NEXTCLOUD_ROTATE_POSTGRES_PASSWORD:-}"
NEXTCLOUD_ROTATE_ADMIN_PASSWORD="${NEXTCLOUD_ROTATE_ADMIN_PASSWORD:-}"
NEXTCLOUD_ROTATE_ASSUME_YES="${NEXTCLOUD_ROTATE_ASSUME_YES:-0}"
ARCLINK_DEPLOY_OPERATION_TTL_SECONDS="${ARCLINK_DEPLOY_OPERATION_TTL_SECONDS:-21600}"
ARCLINK_DEPLOY_OPERATION_MARKER=""

arclink_deploy_stable_copy_cleanup() {
  if [[ "${ARCLINK_DEPLOY_STABLE_COPY:-0}" == "1" && "${ARCLINK_DEPLOY_STABLE_OWNER_PID:-}" == "$$" ]]; then
    rm -f "${ARCLINK_DEPLOY_EXEC_PATH:-}"
  fi
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
  local artifact="${ARCLINK_OPERATOR_ARTIFACT_FILE:-$BOOTSTRAP_DIR/.arclink-operator.env}"

  if [[ ! -r "$artifact" ]]; then
    return 1
  fi

  (
    ARCLINK_OPERATOR_DEPLOYED_USER=""
    ARCLINK_OPERATOR_DEPLOYED_REPO_DIR=""
    ARCLINK_OPERATOR_DEPLOYED_PRIV_DIR=""
    ARCLINK_OPERATOR_DEPLOYED_CONFIG_FILE=""
    # shellcheck disable=SC1090
    source "$artifact"
    printf '%s\n' "${ARCLINK_OPERATOR_DEPLOYED_USER:-}"
    printf '%s\n' "${ARCLINK_OPERATOR_DEPLOYED_REPO_DIR:-}"
    printf '%s\n' "${ARCLINK_OPERATOR_DEPLOYED_PRIV_DIR:-}"
    printf '%s\n' "${ARCLINK_OPERATOR_DEPLOYED_CONFIG_FILE:-}"
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
Native macOS is not a supported ArcLink host or runtime environment.
Helper-only commands like `./deploy.sh write-config` and `./deploy.sh agent-payload`
may still be useful from an operator checkout, but install, upgrade, remove,
health, and service management must run on Debian/Ubuntu Linux or WSL2 Ubuntu
with systemd enabled.
EOF
    return 1
  fi

  if host_is_wsl; then
    cat >&2 <<'EOF'
WSL2 was detected, but the Linux guest is not ready for full ArcLink deployment yet.
ArcLink needs `apt`, `systemd`, and `loginctl` inside the Ubuntu instance.

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
Full ArcLink host deployment currently supports Debian/Ubuntu-style Linux hosts with
`apt`, `systemd`, and `loginctl` available.
EOF
  return 1
}

collect_host_dependency_answers() {
  local podman_default="1"
  local tailscale_default="0"

  ARCLINK_INSTALL_PODMAN="0"
  ARCLINK_INSTALL_TAILSCALE="0"

  if ! command_exists podman; then
    ARCLINK_INSTALL_PODMAN="$(ask_yes_no "Podman is not installed. Install it now for Nextcloud and per-agent code workspaces" "$podman_default")"
  fi

  if ! command_exists tailscale; then
    if [[ "$ENABLE_TAILSCALE_SERVE" == "1" || "${ARCLINK_AGENT_ENABLE_TAILSCALE_SERVE:-$ENABLE_TAILSCALE_SERVE}" == "1" ]]; then
      tailscale_default="1"
    fi
    ARCLINK_INSTALL_TAILSCALE="$(ask_yes_no "Tailscale is not installed. Install it now for tailnet-only access and HTTPS serve" "$tailscale_default")"
  fi
}

usage() {
  cat <<'EOF'
Usage:
  deploy.sh                # interactive menu
  deploy.sh control install
  deploy.sh control upgrade
  deploy.sh control health
  deploy.sh control ports
  deploy.sh install
  deploy.sh upgrade
  deploy.sh notion-ssot
  deploy.sh notion-migrate
  deploy.sh notion-transfer
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

Sovereign Control Node:
  deploy.sh control install       # idempotent control-plane bootstrap + build + up + health
  deploy.sh control upgrade       # rebuild/recreate from current checkout + health
  deploy.sh control reconfigure   # refresh control-node config/ports only
  deploy.sh control health
  deploy.sh control ports
  deploy.sh control logs [SERVICE]
  deploy.sh control ps

Shared Host Docker control center:
  deploy.sh docker install        # idempotent bootstrap + operator config + build + up + Curator setup + health + smoke
  deploy.sh docker upgrade        # rebuild/recreate from current checkout + reconcile + health + smoke
  deploy.sh docker reconfigure    # refresh generated Docker config/ports only
  deploy.sh docker health
  deploy.sh docker ports
  deploy.sh docker logs [SERVICE]
  deploy.sh docker ps
  deploy.sh docker notion-ssot
  deploy.sh docker notion-migrate
  deploy.sh docker notion-transfer
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

Control and Docker shortcut aliases:
  deploy.sh control-install
  deploy.sh control-upgrade
  deploy.sh control-reconfigure
  deploy.sh control-health
  deploy.sh control-ports
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
    control|sovereign)
      MODE="control"
      shift
      if [[ $# -gt 0 ]]; then
        case "$1" in
          -h|--help)
            CONTROL_DEPLOY_COMMAND="help"
            shift
            ;;
          *)
            CONTROL_DEPLOY_COMMAND="$1"
            shift
            ;;
        esac
      fi
      CONTROL_DEPLOY_ARGS=("$@")
      break
      ;;
    control-install|control-upgrade|control-reconfigure|control-bootstrap|control-config|control-build|control-up|control-down|control-ps|control-ports|control-logs|control-health|control-teardown|control-write-config|control-remove)
      MODE="$1"
      shift
      CONTROL_DEPLOY_ARGS=("$@")
      break
      ;;
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
    docker-install|docker-upgrade|docker-reconfigure|docker-bootstrap|docker-config|docker-build|docker-up|docker-down|docker-ps|docker-ports|docker-logs|docker-health|docker-teardown|docker-write-config|docker-remove|docker-notion-ssot|docker-notion-migrate|docker-notion-transfer|docker-enrollment-status|docker-enrollment-trace|docker-enrollment-align|docker-enrollment-reset|docker-curator-setup|docker-rotate-nextcloud-secrets|docker-agent-payload|docker-pins-show|docker-pins-check|docker-pin-upgrade-notify|docker-hermes-upgrade|docker-hermes-upgrade-check|docker-qmd-upgrade|docker-qmd-upgrade-check|docker-nextcloud-upgrade|docker-nextcloud-upgrade-check|docker-postgres-upgrade|docker-postgres-upgrade-check|docker-redis-upgrade|docker-redis-upgrade-check|docker-code-server-upgrade|docker-code-server-upgrade-check|docker-nvm-upgrade|docker-nvm-upgrade-check|docker-node-upgrade|docker-node-upgrade-check)
      MODE="$1"
      shift
      DOCKER_DEPLOY_ARGS=("$@")
      break
      ;;
    install|upgrade|notion-ssot|notion-migrate|notion-transfer|enrollment-status|enrollment-trace|enrollment-align|enrollment-reset|curator-setup|rotate-nextcloud-secrets|agent-payload|agent|write-config|remove|health|menu|pins-show|pins-check|pin-upgrade-notify|hermes-upgrade|hermes-upgrade-check|qmd-upgrade|qmd-upgrade-check|nextcloud-upgrade|nextcloud-upgrade-check|postgres-upgrade|postgres-upgrade-check|redis-upgrade|redis-upgrade-check|code-server-upgrade|code-server-upgrade-check|nvm-upgrade|nvm-upgrade-check|node-upgrade|node-upgrade-check)
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
  env ARCLINK_CONFIG_FILE="$CONFIG_TARGET" \
    "$ctl_bin" --json notion webhook-status --show-public-url --show-secret
}

run_notion_webhook_setup_flow() {
  local ctl_bin="$1"
  local actor="$2"
  local status_json="" configured="" verified="" token="" public_url="" verified_at="" verified_by="" armed_json="" armed_until=""

  if [[ -z "${ARCLINK_NOTION_WEBHOOK_PUBLIC_URL:-}" ]]; then
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
  echo "  ${public_url:-${ARCLINK_NOTION_WEBHOOK_PUBLIC_URL}}"
  echo "  - If a subscription already exists for this exact URL, edit it."
  echo "  - Do not create a duplicate subscription for the same ArcLink endpoint."
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
    echo "  - That click is what causes Notion to send the verification token to ArcLink."
    read -r -p "Press ENTER when you are ready for deploy to arm the window. " _
    armed_json="$(env ARCLINK_CONFIG_FILE="$CONFIG_TARGET" \
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

  env ARCLINK_CONFIG_FILE="$CONFIG_TARGET" \
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
  echo "  - ArcLink cannot press Notion's Manage page access buttons for you via"
  echo "    a supported API."
  echo "  - The internal integration only automatically inherits access to child"
  echo "    pages and databases created under a granted parent/root subtree."
  echo "  - Anything created outside that granted subtree will need manual page"
  echo "    access later."
  echo "  - The sane setup is to grant one stable Teamspace root page or parent"
  echo "    page, then keep ArcLink-managed content under it."
  echo

  while true; do
    read -r -p "Type YES to confirm you understand this Notion access model: " answer
    if [[ "$answer" == "YES" ]]; then
      return 0
    fi
    echo "Please type YES exactly. That guardrail keeps the Teamspace/subtree model explicit."
  done
}

choose_shared_host_mode() {
  local answer=""

  cat <<'EOF'
ArcLink Shared Host control center

  1) Install / repair from current checkout
  2) Upgrade from configured upstream
  3) Write config only
  4) Notion SSOT setup / test
  5) Notion workspace migration
  6) Notion page backup / restore
  7) Enrollment status
  8) Enrollment trace
  9) Enrollment align / repair
 10) Enrollment reset / cleanup
 11) Curator setup / repair
 12) Rotate Nextcloud secrets
 13) Print agent payload
 14) Health check
 15) Remove / teardown
 16) Back
 17) Exit
EOF

  while true; do
    read -r -p "Choose Shared Host action [1]: " answer
    case "${answer:-1}" in
      1) MODE="install"; return 0 ;;
      2) MODE="upgrade"; return 0 ;;
      3) MODE="write-config"; return 0 ;;
      4) MODE="notion-ssot"; return 0 ;;
      5) MODE="notion-migrate"; return 0 ;;
      6) MODE="notion-transfer"; return 0 ;;
      7) MODE="enrollment-status"; return 0 ;;
      8) MODE="enrollment-trace"; return 0 ;;
      9) MODE="enrollment-align"; return 0 ;;
      10) MODE="enrollment-reset"; return 0 ;;
      11) MODE="curator-setup"; return 0 ;;
      12) MODE="rotate-nextcloud-secrets"; return 0 ;;
      13) MODE="agent-payload"; return 0 ;;
      14) MODE="health"; return 0 ;;
      15) MODE="remove"; return 0 ;;
      16) return 1 ;;
      17) exit 0 ;;
      *) echo "Please choose 1 through 17." ;;
    esac
  done
}

choose_mode() {
  local answer=""

  while true; do
    cat <<'EOF'
ArcLink deploy menu

  1) Sovereign Control Node control center (Dockerized billing, bots, fleet, provisioning)
  2) Shared Host mode control center (operator-led)
  3) Shared Host Docker control center (operator-led shared services, not Sovereign pods)
  4) Exit
EOF

    read -r -p "Choose ArcLink mode [1]: " answer
    case "${answer:-1}" in
      1)
        MODE="control"
        CONTROL_DEPLOY_COMMAND="menu"
        return 0
        ;;
      2)
        if choose_shared_host_mode; then
          return 0
        fi
        ;;
      3)
        MODE="docker"
        DOCKER_DEPLOY_COMMAND="menu"
        return 0
        ;;
      4)
        exit 0
        ;;
      *)
        echo "Please choose 1 through 4."
        ;;
    esac
  done
}

control_usage() {
  cat <<'EOF'
Usage:
  deploy.sh control install        # idempotent Sovereign Control Node bootstrap + build + up + health
  deploy.sh control upgrade        # rebuild/recreate from current checkout + health
  deploy.sh control reconfigure    # refresh generated control config/ports only
  deploy.sh control bootstrap
  deploy.sh control config [-q]
  deploy.sh control build [SERVICE...]
  deploy.sh control up [SERVICE...]
  deploy.sh control down
  deploy.sh control ps
  deploy.sh control ports
  deploy.sh control logs [SERVICE]
  deploy.sh control health
  deploy.sh control provision-once # run one provisioner batch now

Shortcut aliases:
  deploy.sh control-install
  deploy.sh control-upgrade
  deploy.sh control-reconfigure
  deploy.sh control-health
  deploy.sh control-ports
EOF
}

docker_usage() {
  cat <<'EOF'
Usage:
  deploy.sh docker install        # idempotent bootstrap + operator config + build + up + Curator setup + health + smoke
  deploy.sh docker upgrade        # rebuild/recreate from current checkout + reconcile + health + smoke
  deploy.sh docker reconfigure    # refresh generated Docker config/ports only
  deploy.sh docker bootstrap
  deploy.sh docker config [-q]
  deploy.sh docker build [SERVICE...]
  deploy.sh docker up [SERVICE...]
  deploy.sh docker reconcile
  deploy.sh docker down
  deploy.sh docker ps
  deploy.sh docker ports
  deploy.sh docker logs [SERVICE]
  deploy.sh docker health
  deploy.sh docker record-release
  deploy.sh docker live-smoke
  deploy.sh docker notion-ssot
  deploy.sh docker notion-migrate
  deploy.sh docker notion-transfer
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
ArcLink Shared Host Docker control center
  Operator-led shared services only; for Dockerized paid customer pods use
  Sovereign Control Node mode.

  1) Install / repair Docker stack from current checkout
  2) Upgrade / rebuild Docker stack from current checkout
  3) Reconfigure Docker generated config and ports
  4) Docker health check
  5) Show Docker ports
  6) Show Docker service state
  7) Notion workspace migration
  8) Notion page backup / restore
  9) Enrollment status
 10) Enrollment align / repair
 11) Curator setup
 12) Rotate Nextcloud secrets
 13) Show Docker logs
 14) Stop Docker stack
 15) Teardown Docker stack and named volumes
 16) Exit
EOF

  while true; do
    read -r -p "Choose Shared Host Docker action [1]: " answer
    case "${answer:-1}" in
      1) DOCKER_DEPLOY_COMMAND="install"; return 0 ;;
      2) DOCKER_DEPLOY_COMMAND="upgrade"; return 0 ;;
      3) DOCKER_DEPLOY_COMMAND="reconfigure"; return 0 ;;
      4) DOCKER_DEPLOY_COMMAND="health"; return 0 ;;
      5) DOCKER_DEPLOY_COMMAND="ports"; return 0 ;;
      6) DOCKER_DEPLOY_COMMAND="ps"; return 0 ;;
      7) DOCKER_DEPLOY_COMMAND="notion-migrate"; return 0 ;;
      8) DOCKER_DEPLOY_COMMAND="notion-transfer"; return 0 ;;
      9) DOCKER_DEPLOY_COMMAND="enrollment-status"; return 0 ;;
      10) DOCKER_DEPLOY_COMMAND="enrollment-align"; return 0 ;;
      11) DOCKER_DEPLOY_COMMAND="curator-setup"; return 0 ;;
      12) DOCKER_DEPLOY_COMMAND="rotate-nextcloud-secrets"; return 0 ;;
      13) DOCKER_DEPLOY_COMMAND="logs"; return 0 ;;
      14) DOCKER_DEPLOY_COMMAND="down"; return 0 ;;
      15) DOCKER_DEPLOY_COMMAND="teardown"; return 0 ;;
      16) exit 0 ;;
      *) echo "Please choose 1 through 16." ;;
    esac
  done
}

choose_control_mode() {
  local answer=""

  cat <<'EOF'
ArcLink Sovereign Control Node control center

  1) Install / repair control node from current checkout
  2) Upgrade / rebuild control node from current checkout
  3) Reconfigure generated control config and ports
  4) Control node health check
  5) Show control node ports
  6) Show control node service state
  7) Show control node logs
  8) Stop control node stack
  9) Teardown control node stack and named volumes
 10) Exit
EOF

  while true; do
    read -r -p "Choose Sovereign Control Node action [1]: " answer
    case "${answer:-1}" in
      1) CONTROL_DEPLOY_COMMAND="install"; return 0 ;;
      2) CONTROL_DEPLOY_COMMAND="upgrade"; return 0 ;;
      3) CONTROL_DEPLOY_COMMAND="reconfigure"; return 0 ;;
      4) CONTROL_DEPLOY_COMMAND="health"; return 0 ;;
      5) CONTROL_DEPLOY_COMMAND="ports"; return 0 ;;
      6) CONTROL_DEPLOY_COMMAND="ps"; return 0 ;;
      7) CONTROL_DEPLOY_COMMAND="logs"; return 0 ;;
      8) CONTROL_DEPLOY_COMMAND="down"; return 0 ;;
      9) CONTROL_DEPLOY_COMMAND="teardown"; return 0 ;;
      10) exit 0 ;;
      *) echo "Please choose 1 through 10." ;;
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
  TAILSCALE_SERVE_HAS_ARCLINK_MCP="0"

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
    TAILSCALE_SERVE_JSON="$ts_json" python3 - "${TAILSCALE_SERVE_PORT:-443}" "$QMD_MCP_PORT" "$TAILSCALE_QMD_PATH" "$ARCLINK_MCP_PORT" "$TAILSCALE_ARCLINK_MCP_PATH" <<'PY'
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
arclink_mcp_port = sys.argv[4]
arclink_mcp_path = sys.argv[5]
web = data.get("Web") or {}

host = ""
has_root = False
has_qmd = False
has_arclink_mcp = False

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
    arclink_handler = handlers.get(arclink_mcp_path) or {}
    qmd_proxy = str(qmd_handler.get("Proxy") or "")
    arclink_proxy = str(arclink_handler.get("Proxy") or "")
    if qmd_proxy == f"http://127.0.0.1:{qmd_port}/mcp":
        has_qmd = True
    if arclink_proxy == f"http://127.0.0.1:{arclink_mcp_port}/mcp":
        has_arclink_mcp = True
    for path, handler in handlers.items():
        proxy = str((handler or {}).get("Proxy") or "")
        if path == qmd_path and proxy == f"http://127.0.0.1:{qmd_port}/mcp":
            has_qmd = True
        if path == arclink_mcp_path and proxy == f"http://127.0.0.1:{arclink_mcp_port}/mcp":
            has_arclink_mcp = True

values = {
    "host": host,
    "root": "1" if has_root else "0",
    "qmd": "1" if has_qmd else "0",
    "arclink_mcp": "1" if has_arclink_mcp else "0",
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
      arclink_mcp) TAILSCALE_SERVE_HAS_ARCLINK_MCP="$value" ;;
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
    derived_url="$(build_public_https_url "$TAILSCALE_DNS_NAME" "${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-443}" "$funnel_path" || true)"
  fi

  if [[ "$ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL" == "1" ]]; then
    if [[ -n "$derived_url" ]]; then
      ARCLINK_NOTION_WEBHOOK_PUBLIC_URL="$derived_url"
    fi
  elif [[ -n "$derived_url" && "${ARCLINK_NOTION_WEBHOOK_PUBLIC_URL:-}" == "$derived_url" ]]; then
    ARCLINK_NOTION_WEBHOOK_PUBLIC_URL=""
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
    TAILSCALE_FUNNEL_JSON="$ts_json" python3 - "${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-443}" "$funnel_path" "$ARCLINK_NOTION_WEBHOOK_PORT" <<'PY'
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
        "${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-443}" \
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

  AGENT_ARCLINK_MCP_TAILNET_HOST="${TAILSCALE_SERVE_HOST:-${TAILSCALE_DNS_NAME:-$NEXTCLOUD_TRUSTED_DOMAIN}}"
  AGENT_ARCLINK_MCP_TAILNET_URL=""
  AGENT_ARCLINK_MCP_URL="http://${ARCLINK_MCP_HOST:-127.0.0.1}:${ARCLINK_MCP_PORT:-8282}/mcp"
  AGENT_ARCLINK_MCP_URL_MODE="local"
  AGENT_ARCLINK_MCP_ROUTE_STATUS="local_only"

  if [[ -n "$AGENT_ARCLINK_MCP_TAILNET_HOST" ]]; then
    AGENT_ARCLINK_MCP_TAILNET_URL="$(build_public_https_url "$AGENT_ARCLINK_MCP_TAILNET_HOST" "${TAILSCALE_SERVE_PORT:-443}" "${TAILSCALE_ARCLINK_MCP_PATH}")"
  fi

  if [[ -n "$TAILSCALE_DNS_NAME" || -n "$TAILSCALE_SERVE_HOST" || "$ENABLE_TAILSCALE_SERVE" == "1" ]]; then
    if [[ -n "$AGENT_ARCLINK_MCP_TAILNET_URL" ]]; then
      AGENT_ARCLINK_MCP_URL="$AGENT_ARCLINK_MCP_TAILNET_URL"
      AGENT_ARCLINK_MCP_URL_MODE="tailnet"
      if [[ "$TAILSCALE_SERVE_HAS_ARCLINK_MCP" == "1" ]]; then
        AGENT_ARCLINK_MCP_ROUTE_STATUS="live"
      else
        AGENT_ARCLINK_MCP_ROUTE_STATUS="expected"
      fi
    fi
  fi
}

detect_github_repo() {
  GITHUB_REPO_URL=""
  GITHUB_REPO_OWNER_REPO=""
  GITHUB_REPO_BRANCH="main"

  if ! command -v git >/dev/null 2>&1; then
    GITHUB_REPO_URL="https://github.com/example/arclink"
    GITHUB_REPO_OWNER_REPO="example/arclink"
    return 0
  fi

  local remote_url="" branch="" owner_repo=""
  remote_url="$(git -C "$ARCLINK_REPO_DIR" remote get-url origin 2>/dev/null || true)"
  branch="$(git -C "$ARCLINK_REPO_DIR" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
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
    GITHUB_REPO_URL="https://github.com/example/arclink"
    GITHUB_REPO_OWNER_REPO="example/arclink"
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
  explicit_config="${ARCLINK_CONFIG_FILE:-}"
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
      "$artifact_priv/config/arclink.env"
      "$artifact_priv/arclink.env"
    )
  fi

  if [[ -n "$artifact_repo" ]]; then
    candidates+=(
      "$artifact_repo/arclink-priv/config/arclink.env"
      "$artifact_repo/config/arclink.env"
    )
  fi

  if [[ -n "$artifact_user" ]]; then
    artifact_home="$(resolve_user_home "$artifact_user" || true)"
    if [[ -n "$artifact_home" ]]; then
      candidates+=(
        "$artifact_home/arclink/arclink-priv/config/arclink.env"
        "$artifact_home/arclink-priv/config/arclink.env"
      )
    fi
  fi

  candidates+=(
    "/home/arclink/arclink/arclink-priv/config/arclink.env"
    "$HOME/arclink/arclink-priv/config/arclink.env"
    "$HOME/arclink/arclink/arclink-priv/config/arclink.env"
    "$BOOTSTRAP_DIR/arclink-priv/config/arclink.env"
    "$BOOTSTRAP_DIR/config/arclink.env"
  )

  for candidate in "${candidates[@]}"; do
    status="$(probe_path_status "$candidate")"
    if [[ "$status" == "exists" || "$status" == "exists-unreadable" ]]; then
      DISCOVERED_CONFIG="$candidate"
      return 0
    fi
  done

  candidate="$(find /home -maxdepth 5 -path '*/arclink/arclink-priv/config/arclink.env' -print -quit 2>/dev/null || true)"
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
    ARCLINK_MODEL_PRESET_CODEX="$(model_provider_resolve_target_or_default codex "${ARCLINK_MODEL_PRESET_CODEX:-}" "openai-codex:gpt-5.5")"
    ARCLINK_MODEL_PRESET_OPUS="$(model_provider_resolve_target_or_default opus "${ARCLINK_MODEL_PRESET_OPUS:-}" "anthropic:claude-opus-4-7")"
    ARCLINK_MODEL_PRESET_CHUTES="$(model_provider_resolve_target_or_default chutes "${ARCLINK_MODEL_PRESET_CHUTES:-}" "chutes:moonshotai/Kimi-K2.6-TEE")"
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

normalize_qmd_embed_provider() {
  local value=""

  value="$(lowercase "${1:-}")"
  value="${value//[ _-]/}"
  case "$value" in
    ""|l|local|gguf|qmd)
      printf '%s\n' "local"
      ;;
    e|endpoint|remote|api|openai|openaicompatible|openaiapi)
      printf '%s\n' "endpoint"
      ;;
    none|off|disable|disabled)
      printf '%s\n' "none"
      ;;
    *)
      return 1
      ;;
  esac
}

remember_qmd_embed_provider_transition() {
  local previous_provider="$1"
  local next_provider="$2"

  if [[ "$next_provider" == "local" ]]; then
    if [[ "$previous_provider" != "local" ]]; then
      QMD_EMBED_FORCE_ON_NEXT_REFRESH=1
      echo "Switching to local qmd embeddings; the next qmd refresh will rebuild local vectors."
    else
      QMD_EMBED_FORCE_ON_NEXT_REFRESH="${QMD_EMBED_FORCE_ON_NEXT_REFRESH:-0}"
    fi
  else
    QMD_EMBED_FORCE_ON_NEXT_REFRESH=0
  fi
}

collect_qmd_embedding_answers() {
  local default_provider="" provider_answer="" provider=""
  local default_endpoint="" default_model="" default_api_key="" default_dimensions=""

  default_provider="$(normalize_qmd_embed_provider "${QMD_EMBED_PROVIDER:-local}" || printf '%s\n' "local")"
  default_endpoint="${QMD_EMBED_ENDPOINT:-}"
  default_model="${QMD_EMBED_ENDPOINT_MODEL:-}"
  if [[ -z "$default_model" && "$default_provider" == "endpoint" ]]; then
    # Compatibility with short-lived pre-release installer builds that wrote
    # the endpoint model into qmd's local-model env name.
    default_model="${QMD_EMBED_MODEL:-}"
  fi
  default_api_key="${QMD_EMBED_API_KEY:-}"
  default_dimensions="${QMD_EMBED_DIMENSIONS:-}"
  if [[ "$default_provider" == "endpoint" && -z "$default_model" ]]; then
    default_model="text-embedding-3-small"
  fi

  cat <<'EOF'
QMD semantic embeddings
  local    - qmd local GGUF embeddings; private and offline, but can be slow on CPU
  endpoint - OpenAI-compatible /v1/embeddings credentials; skips slow local embedding until endpoint-backed qmd search is available
EOF

  while true; do
    provider_answer="$(ask "QMD semantic embedding backend (local/endpoint)" "$default_provider")"
    if provider="$(normalize_qmd_embed_provider "$provider_answer")"; then
      break
    fi
    echo "Choose local or endpoint."
  done

  case "$provider" in
    endpoint)
      QMD_EMBED_PROVIDER="endpoint"
      QMD_EMBED_ENDPOINT="$(normalize_optional_answer "$(ask "OpenAI-compatible embeddings endpoint (base /v1 or full /v1/embeddings; type none to use local)" "$default_endpoint")")"
      if [[ -z "$QMD_EMBED_ENDPOINT" ]]; then
        echo "No embeddings endpoint provided; using local qmd embeddings."
        QMD_EMBED_PROVIDER="local"
        QMD_EMBED_ENDPOINT_MODEL=""
        QMD_EMBED_API_KEY=""
        QMD_EMBED_DIMENSIONS=""
        QMD_RUN_EMBED="1"
        remember_qmd_embed_provider_transition "$default_provider" "$QMD_EMBED_PROVIDER"
        return 0
      fi
      QMD_EMBED_ENDPOINT_MODEL="$(normalize_optional_answer "$(ask "Embedding endpoint model name (type none to leave unset)" "${default_model:-text-embedding-3-small}")")"
      QMD_EMBED_DIMENSIONS="$(normalize_optional_answer "$(ask "Embedding dimensions (optional; type none to omit)" "$default_dimensions")")"
      QMD_EMBED_API_KEY="$(ask_secret_with_default "Embedding API key (ENTER keeps current, type none to clear)" "$default_api_key")"
      QMD_RUN_EMBED="0"
      remember_qmd_embed_provider_transition "$default_provider" "$QMD_EMBED_PROVIDER"
      ;;
    none)
      QMD_EMBED_PROVIDER="none"
      QMD_EMBED_ENDPOINT=""
      QMD_EMBED_ENDPOINT_MODEL=""
      QMD_EMBED_API_KEY=""
      QMD_EMBED_DIMENSIONS=""
      QMD_RUN_EMBED="0"
      remember_qmd_embed_provider_transition "$default_provider" "$QMD_EMBED_PROVIDER"
      ;;
    *)
      QMD_EMBED_PROVIDER="local"
      QMD_EMBED_ENDPOINT=""
      QMD_EMBED_ENDPOINT_MODEL=""
      QMD_EMBED_API_KEY=""
      QMD_EMBED_DIMENSIONS=""
      QMD_RUN_EMBED="1"
      remember_qmd_embed_provider_transition "$default_provider" "$QMD_EMBED_PROVIDER"
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
    "${ARCLINK_PINS_FILE:-}" \
    "${ARCLINK_REPO_DIR:-}/config/pins.json" \
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
  local channels=",${ARCLINK_CURATOR_CHANNELS:-tui-only},"
  if [[ "$channels" == *",telegram,"* || "${OPERATOR_NOTIFY_CHANNEL_PLATFORM:-}" == "telegram" ]]; then
    printf '%s' "1"
  else
    printf '%s' "0"
  fi
}

default_curator_discord_onboarding_enabled() {
  local channels=",${ARCLINK_CURATOR_CHANNELS:-tui-only},"
  if [[ "$channels" == *",discord,"* ]]; then
    printf '%s' "1"
  else
    printf '%s' "0"
  fi
}

default_arclink_public_telegram_webhook_url() {
  local control_url="" base_domain=""
  if [[ -n "${ARCLINK_TAILSCALE_CONTROL_URL:-}" ]]; then
    control_url="${ARCLINK_TAILSCALE_CONTROL_URL%/}"
  elif [[ -n "${ARCLINK_BASE_DOMAIN:-}" ]]; then
    base_domain="${ARCLINK_BASE_DOMAIN#http://}"
    base_domain="${base_domain#https://}"
    base_domain="${base_domain%%/*}"
    if [[ -n "$base_domain" ]]; then
      control_url="https://$base_domain"
    fi
  fi
  if [[ -n "$control_url" ]]; then
    printf '%s/api/v1/webhooks/telegram' "$control_url"
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
  if [[ -z "${ARCLINK_CURATOR_TELEGRAM_ONBOARDING_ENABLED:-}" ]]; then
    ARCLINK_CURATOR_TELEGRAM_ONBOARDING_ENABLED="$(default_curator_telegram_onboarding_enabled)"
  fi
  if [[ -z "${ARCLINK_CURATOR_DISCORD_ONBOARDING_ENABLED:-}" ]]; then
    ARCLINK_CURATOR_DISCORD_ONBOARDING_ENABLED="$(default_curator_discord_onboarding_enabled)"
  fi
  if declare -F refresh_notion_webhook_public_url_from_tailscale >/dev/null 2>&1; then
    refresh_notion_webhook_public_url_from_tailscale
  fi
  if [[ -z "${TELEGRAM_WEBHOOK_URL:-}" ]]; then
    TELEGRAM_WEBHOOK_URL="$(default_arclink_public_telegram_webhook_url)"
  fi
}

emit_runtime_config() {
  local notion_funnel_path="${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH:-/notion/webhook}"
  local hermes_agent_ref=""
  local hermes_docs_repo_url=""
  local hermes_docs_ref=""
  local code_server_image=""

  normalize_runtime_config_defaults
  hermes_agent_ref="$(deploy_pin_get_or_default hermes-agent ref "${ARCLINK_HERMES_AGENT_REF:-ce089169d578b96c82641f17186ba63c288b22d8}")"
  hermes_docs_repo_url="${ARCLINK_HERMES_DOCS_REPO_URL:-https://github.com/NousResearch/hermes-agent.git}"
  if [[ "$hermes_docs_repo_url" == "https://github.com/NousResearch/hermes-agent.git" ]]; then
    hermes_docs_ref="$(deploy_pin_get_or_default hermes-docs ref "${ARCLINK_HERMES_DOCS_REF:-$hermes_agent_ref}")"
  else
    hermes_docs_ref="${ARCLINK_HERMES_DOCS_REF:-$hermes_agent_ref}"
  fi
  code_server_image="$(deploy_pin_image_or_default code-server "${ARCLINK_AGENT_CODE_SERVER_IMAGE:-docker.io/codercom/code-server:4.116.0}")"
  if declare -F normalize_http_path >/dev/null 2>&1; then
    notion_funnel_path="$(normalize_http_path "$notion_funnel_path")"
  elif [[ "$notion_funnel_path" != /* ]]; then
    notion_funnel_path="/$notion_funnel_path"
  fi
  {
    write_kv ARCLINK_NAME "$ARCLINK_NAME"
    write_kv ARCLINK_PRODUCT_NAME "${ARCLINK_PRODUCT_NAME:-ArcLink}"
    write_kv ARCLINK_BASE_DOMAIN "${ARCLINK_BASE_DOMAIN:-arclink.online}"
    write_kv ARCLINK_INGRESS_MODE "${ARCLINK_INGRESS_MODE:-domain}"
    write_kv ARCLINK_TAILSCALE_DNS_NAME "${ARCLINK_TAILSCALE_DNS_NAME:-}"
    write_kv ARCLINK_TAILSCALE_CONTROL_URL "${ARCLINK_TAILSCALE_CONTROL_URL:-}"
    write_kv ARCLINK_TAILSCALE_HTTPS_PORT "${ARCLINK_TAILSCALE_HTTPS_PORT:-443}"
    write_kv ARCLINK_TAILSCALE_NOTION_PATH "${ARCLINK_TAILSCALE_NOTION_PATH:-/notion/webhook}"
    write_kv ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY "${ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY:-path}"
    write_kv ARCLINK_PRIMARY_PROVIDER "${ARCLINK_PRIMARY_PROVIDER:-chutes}"
    write_kv ARCLINK_USER "$ARCLINK_USER"
    write_kv ARCLINK_HOME "$ARCLINK_HOME"
    write_kv ARCLINK_REPO_DIR "$ARCLINK_REPO_DIR"
    write_kv ARCLINK_PRIV_DIR "$ARCLINK_PRIV_DIR"
    write_kv ARCLINK_PRIV_CONFIG_DIR "$ARCLINK_PRIV_CONFIG_DIR"
    write_kv VAULT_DIR "$VAULT_DIR"
    write_kv STATE_DIR "$STATE_DIR"
    write_kv NEXTCLOUD_STATE_DIR "$NEXTCLOUD_STATE_DIR"
    write_kv RUNTIME_DIR "$RUNTIME_DIR"
    write_kv PUBLISHED_DIR "$PUBLISHED_DIR"
    write_kv ARCLINK_DB_PATH "${ARCLINK_DB_PATH:-$STATE_DIR/arclink-control.sqlite3}"
    write_kv ARCLINK_AGENTS_STATE_DIR "${ARCLINK_AGENTS_STATE_DIR:-$STATE_DIR/agents}"
    write_kv ARCLINK_CURATOR_DIR "${ARCLINK_CURATOR_DIR:-$STATE_DIR/curator}"
    write_kv ARCLINK_CURATOR_MANIFEST "${ARCLINK_CURATOR_MANIFEST:-$STATE_DIR/curator/manifest.json}"
    write_kv ARCLINK_CURATOR_HERMES_HOME "${ARCLINK_CURATOR_HERMES_HOME:-$STATE_DIR/curator/hermes-home}"
    write_kv ARCLINK_ARCHIVED_AGENTS_DIR "${ARCLINK_ARCHIVED_AGENTS_DIR:-$STATE_DIR/archived-agents}"
    write_kv QMD_INDEX_NAME "$QMD_INDEX_NAME"
    write_kv QMD_COLLECTION_NAME "$QMD_COLLECTION_NAME"
    write_kv VAULT_QMD_COLLECTION_MASK "$(normalize_vault_qmd_collection_mask "${VAULT_QMD_COLLECTION_MASK:-}")"
    write_kv PDF_INGEST_COLLECTION_NAME "$PDF_INGEST_COLLECTION_NAME"
    write_kv QMD_RUN_EMBED "$QMD_RUN_EMBED"
    write_kv QMD_EMBED_PROVIDER "${QMD_EMBED_PROVIDER:-local}"
    write_kv QMD_EMBED_ENDPOINT "${QMD_EMBED_ENDPOINT:-}"
    write_kv QMD_EMBED_ENDPOINT_MODEL "${QMD_EMBED_ENDPOINT_MODEL:-}"
    write_kv QMD_EMBED_API_KEY "${QMD_EMBED_API_KEY:-}"
    write_kv QMD_EMBED_DIMENSIONS "${QMD_EMBED_DIMENSIONS:-}"
    write_kv QMD_EMBED_TIMEOUT_SECONDS "$QMD_EMBED_TIMEOUT_SECONDS"
    write_kv QMD_EMBED_MAX_DOCS_PER_BATCH "$QMD_EMBED_MAX_DOCS_PER_BATCH"
    write_kv QMD_EMBED_MAX_BATCH_MB "$QMD_EMBED_MAX_BATCH_MB"
    write_kv QMD_EMBED_FORCE_ON_NEXT_REFRESH "${QMD_EMBED_FORCE_ON_NEXT_REFRESH:-0}"
    write_kv QMD_MCP_PORT "$QMD_MCP_PORT"
    write_kv ARCLINK_MCP_HOST "$ARCLINK_MCP_HOST"
    write_kv ARCLINK_MCP_PORT "$ARCLINK_MCP_PORT"
    write_kv ARCLINK_API_HOST "${ARCLINK_API_HOST:-127.0.0.1}"
    write_kv ARCLINK_API_PORT "${ARCLINK_API_PORT:-8900}"
    write_kv ARCLINK_WEB_PORT "${ARCLINK_WEB_PORT:-3000}"
    write_kv ARCLINK_CORS_ORIGIN "${ARCLINK_CORS_ORIGIN:-}"
    write_kv ARCLINK_COOKIE_DOMAIN "${ARCLINK_COOKIE_DOMAIN:-}"
    write_kv ARCLINK_DEFAULT_PRICE_ID "${ARCLINK_DEFAULT_PRICE_ID:-price_arclink_starter}"
    write_kv ARCLINK_FIRST_AGENT_PRICE_ID "${ARCLINK_FIRST_AGENT_PRICE_ID:-${ARCLINK_DEFAULT_PRICE_ID:-price_arclink_starter}}"
    write_kv ARCLINK_ADDITIONAL_AGENT_PRICE_ID "${ARCLINK_ADDITIONAL_AGENT_PRICE_ID:-price_arclink_additional_agent}"
    write_kv ARCLINK_FIRST_AGENT_MONTHLY_CENTS "${ARCLINK_FIRST_AGENT_MONTHLY_CENTS:-3500}"
    write_kv ARCLINK_ADDITIONAL_AGENT_MONTHLY_CENTS "${ARCLINK_ADDITIONAL_AGENT_MONTHLY_CENTS:-1500}"
    write_kv ARCLINK_CONTROL_PROVISIONER_ENABLED "${ARCLINK_CONTROL_PROVISIONER_ENABLED:-0}"
    write_kv ARCLINK_CONTROL_PROVISIONER_INTERVAL_SECONDS "${ARCLINK_CONTROL_PROVISIONER_INTERVAL_SECONDS:-30}"
    write_kv ARCLINK_CONTROL_PROVISIONER_BATCH_SIZE "${ARCLINK_CONTROL_PROVISIONER_BATCH_SIZE:-5}"
    write_kv ARCLINK_SOVEREIGN_PROVISION_MAX_ATTEMPTS "${ARCLINK_SOVEREIGN_PROVISION_MAX_ATTEMPTS:-5}"
    write_kv ARCLINK_EXECUTOR_ADAPTER "${ARCLINK_EXECUTOR_ADAPTER:-disabled}"
    write_kv ARCLINK_EDGE_TARGET "${ARCLINK_EDGE_TARGET:-edge.arclink.online}"
    write_kv ARCLINK_STATE_ROOT_BASE "${ARCLINK_STATE_ROOT_BASE:-/arcdata/deployments}"
    write_kv ARCLINK_SECRET_STORE_DIR "${ARCLINK_SECRET_STORE_DIR:-$STATE_DIR/sovereign-secrets}"
    write_kv ARCLINK_REGISTER_LOCAL_FLEET_HOST "${ARCLINK_REGISTER_LOCAL_FLEET_HOST:-0}"
    write_kv ARCLINK_LOCAL_FLEET_HOSTNAME "${ARCLINK_LOCAL_FLEET_HOSTNAME:-}"
    write_kv ARCLINK_LOCAL_FLEET_SSH_HOST "${ARCLINK_LOCAL_FLEET_SSH_HOST:-}"
    write_kv ARCLINK_LOCAL_FLEET_SSH_USER "${ARCLINK_LOCAL_FLEET_SSH_USER:-arclink}"
    write_kv ARCLINK_LOCAL_FLEET_REGION "${ARCLINK_LOCAL_FLEET_REGION:-}"
    write_kv ARCLINK_LOCAL_FLEET_CAPACITY_SLOTS "${ARCLINK_LOCAL_FLEET_CAPACITY_SLOTS:-4}"
    write_kv ARCLINK_FLEET_SSH_KEY_PATH "${ARCLINK_FLEET_SSH_KEY_PATH:-}"
    write_kv ARCLINK_FLEET_SSH_KNOWN_HOSTS_FILE "${ARCLINK_FLEET_SSH_KNOWN_HOSTS_FILE:-}"
    write_kv STRIPE_SECRET_KEY "${STRIPE_SECRET_KEY:-}"
    write_kv STRIPE_WEBHOOK_SECRET "${STRIPE_WEBHOOK_SECRET:-}"
    write_kv CLOUDFLARE_API_TOKEN "${CLOUDFLARE_API_TOKEN:-}"
    write_kv CLOUDFLARE_ZONE_ID "${CLOUDFLARE_ZONE_ID:-}"
    write_kv CHUTES_API_KEY "${CHUTES_API_KEY:-}"
    write_kv ARCLINK_NOTION_WEBHOOK_HOST "$ARCLINK_NOTION_WEBHOOK_HOST"
    write_kv ARCLINK_NOTION_WEBHOOK_PORT "$ARCLINK_NOTION_WEBHOOK_PORT"
    write_kv ARCLINK_NOTION_WEBHOOK_PUBLIC_URL "${ARCLINK_NOTION_WEBHOOK_PUBLIC_URL:-}"
    write_kv ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL "${ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL:-0}"
    write_kv TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT "${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-443}"
    write_kv TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH "$notion_funnel_path"
    write_kv ARCLINK_SSOT_NOTION_ROOT_PAGE_URL "${ARCLINK_SSOT_NOTION_ROOT_PAGE_URL:-}"
    write_kv ARCLINK_SSOT_NOTION_ROOT_PAGE_ID "${ARCLINK_SSOT_NOTION_ROOT_PAGE_ID:-}"
    write_kv ARCLINK_SSOT_NOTION_SPACE_URL "${ARCLINK_SSOT_NOTION_SPACE_URL:-}"
    write_kv ARCLINK_SSOT_NOTION_SPACE_ID "${ARCLINK_SSOT_NOTION_SPACE_ID:-}"
    write_kv ARCLINK_SSOT_NOTION_SPACE_KIND "${ARCLINK_SSOT_NOTION_SPACE_KIND:-}"
    write_kv ARCLINK_SSOT_NOTION_API_VERSION "${ARCLINK_SSOT_NOTION_API_VERSION:-2026-03-11}"
    write_kv ARCLINK_SSOT_NOTION_TOKEN "${ARCLINK_SSOT_NOTION_TOKEN:-}"
    write_kv ARCLINK_NOTION_INDEX_ROOTS "${ARCLINK_NOTION_INDEX_ROOTS:-}"
    write_kv ARCLINK_NOTION_INDEX_RUN_EMBED "${ARCLINK_NOTION_INDEX_RUN_EMBED:-1}"
    write_kv ARCLINK_ORG_NAME "${ARCLINK_ORG_NAME:-}"
    write_kv ARCLINK_ORG_MISSION "${ARCLINK_ORG_MISSION:-}"
    write_kv ARCLINK_ORG_PRIMARY_PROJECT "${ARCLINK_ORG_PRIMARY_PROJECT:-}"
    write_kv ARCLINK_ORG_TIMEZONE "${ARCLINK_ORG_TIMEZONE:-Etc/UTC}"
    write_kv ARCLINK_ORG_QUIET_HOURS "${ARCLINK_ORG_QUIET_HOURS:-}"
    write_kv ARCLINK_BOOTSTRAP_WINDOW_SECONDS "$ARCLINK_BOOTSTRAP_WINDOW_SECONDS"
    write_kv ARCLINK_BOOTSTRAP_PER_IP_LIMIT "$ARCLINK_BOOTSTRAP_PER_IP_LIMIT"
    write_kv ARCLINK_BOOTSTRAP_GLOBAL_PENDING_LIMIT "$ARCLINK_BOOTSTRAP_GLOBAL_PENDING_LIMIT"
    write_kv ARCLINK_BOOTSTRAP_PENDING_TTL_SECONDS "$ARCLINK_BOOTSTRAP_PENDING_TTL_SECONDS"
    write_kv ARCLINK_AUTO_PROVISION_MAX_ATTEMPTS "$ARCLINK_AUTO_PROVISION_MAX_ATTEMPTS"
    write_kv ARCLINK_AUTO_PROVISION_RETRY_BASE_SECONDS "$ARCLINK_AUTO_PROVISION_RETRY_BASE_SECONDS"
    write_kv ARCLINK_AUTO_PROVISION_RETRY_MAX_SECONDS "$ARCLINK_AUTO_PROVISION_RETRY_MAX_SECONDS"
    write_kv PDF_INGEST_ENABLED "$PDF_INGEST_ENABLED"
    write_kv PDF_INGEST_EXTRACTOR "$PDF_INGEST_EXTRACTOR"
    write_kv PDF_INGEST_TRIGGER_QMD_REFRESH "${PDF_INGEST_TRIGGER_QMD_REFRESH:-1}"
    write_kv PDF_INGEST_WATCH_DEBOUNCE_SECONDS "${PDF_INGEST_WATCH_DEBOUNCE_SECONDS:-10}"
    write_kv PDF_INGEST_DOCLING_FORCE_OCR "${PDF_INGEST_DOCLING_FORCE_OCR:-0}"
    write_kv PDF_VISION_ENDPOINT "${PDF_VISION_ENDPOINT:-}"
    write_kv PDF_VISION_MODEL "${PDF_VISION_MODEL:-}"
    write_kv PDF_VISION_API_KEY "${PDF_VISION_API_KEY:-}"
    write_kv PDF_VISION_MAX_PAGES "${PDF_VISION_MAX_PAGES:-6}"
    write_kv ARCLINK_MEMORY_SYNTH_ENABLED "${ARCLINK_MEMORY_SYNTH_ENABLED:-auto}"
    write_kv ARCLINK_MEMORY_SYNTH_ENDPOINT "${ARCLINK_MEMORY_SYNTH_ENDPOINT:-}"
    write_kv ARCLINK_MEMORY_SYNTH_MODEL "${ARCLINK_MEMORY_SYNTH_MODEL:-}"
    write_kv ARCLINK_MEMORY_SYNTH_API_KEY "${ARCLINK_MEMORY_SYNTH_API_KEY:-}"
    write_kv ARCLINK_MEMORY_SYNTH_MAX_SOURCES_PER_RUN "${ARCLINK_MEMORY_SYNTH_MAX_SOURCES_PER_RUN:-12}"
    write_kv ARCLINK_MEMORY_SYNTH_MAX_SOURCE_CHARS "${ARCLINK_MEMORY_SYNTH_MAX_SOURCE_CHARS:-4500}"
    write_kv ARCLINK_MEMORY_SYNTH_MAX_OUTPUT_TOKENS "${ARCLINK_MEMORY_SYNTH_MAX_OUTPUT_TOKENS:-450}"
    write_kv ARCLINK_MEMORY_SYNTH_TIMEOUT_SECONDS "${ARCLINK_MEMORY_SYNTH_TIMEOUT_SECONDS:-60}"
    write_kv ARCLINK_MEMORY_SYNTH_FAILURE_RETRY_SECONDS "${ARCLINK_MEMORY_SYNTH_FAILURE_RETRY_SECONDS:-3600}"
    write_kv ARCLINK_MEMORY_SYNTH_CARDS_IN_CONTEXT "${ARCLINK_MEMORY_SYNTH_CARDS_IN_CONTEXT:-8}"
    write_kv ARCLINK_MEMORY_SYNTH_ON_VAULT_CHANGE "${ARCLINK_MEMORY_SYNTH_ON_VAULT_CHANGE:-1}"
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
    write_kv ARCLINK_OPERATOR_TELEGRAM_USER_IDS "${ARCLINK_OPERATOR_TELEGRAM_USER_IDS:-}"
    write_kv ARCLINK_CURATOR_TELEGRAM_ONBOARDING_ENABLED "${ARCLINK_CURATOR_TELEGRAM_ONBOARDING_ENABLED:-}"
    write_kv ARCLINK_CURATOR_DISCORD_ONBOARDING_ENABLED "${ARCLINK_CURATOR_DISCORD_ONBOARDING_ENABLED:-}"
    write_kv ARCLINK_ONBOARDING_WINDOW_SECONDS "${ARCLINK_ONBOARDING_WINDOW_SECONDS:-3600}"
    write_kv ARCLINK_ONBOARDING_PER_USER_LIMIT "${ARCLINK_ONBOARDING_PER_USER_LIMIT:-${ARCLINK_ONBOARDING_PER_TELEGRAM_USER_LIMIT:-3}}"
    write_kv ARCLINK_ONBOARDING_PER_TELEGRAM_USER_LIMIT "${ARCLINK_ONBOARDING_PER_TELEGRAM_USER_LIMIT:-3}"
    write_kv ARCLINK_ONBOARDING_GLOBAL_PENDING_LIMIT "${ARCLINK_ONBOARDING_GLOBAL_PENDING_LIMIT:-20}"
    write_kv ARCLINK_ONBOARDING_UPDATE_FAILURE_LIMIT "${ARCLINK_ONBOARDING_UPDATE_FAILURE_LIMIT:-3}"
    write_kv OPERATOR_GENERAL_CHANNEL_PLATFORM "${OPERATOR_GENERAL_CHANNEL_PLATFORM:-}"
    write_kv OPERATOR_GENERAL_CHANNEL_ID "${OPERATOR_GENERAL_CHANNEL_ID:-}"
    write_kv TELEGRAM_BOT_TOKEN "${TELEGRAM_BOT_TOKEN:-}"
    write_kv TELEGRAM_BOT_USERNAME "${TELEGRAM_BOT_USERNAME:-}"
    write_kv TELEGRAM_WEBHOOK_URL "${TELEGRAM_WEBHOOK_URL:-}"
    write_kv DISCORD_BOT_TOKEN "${DISCORD_BOT_TOKEN:-}"
    write_kv DISCORD_APP_ID "${DISCORD_APP_ID:-}"
    write_kv DISCORD_PUBLIC_KEY "${DISCORD_PUBLIC_KEY:-}"
    write_kv ARCLINK_MODEL_PRESET_CODEX "${ARCLINK_MODEL_PRESET_CODEX:-openai-codex:gpt-5.5}"
    write_kv ARCLINK_MODEL_PRESET_OPUS "${ARCLINK_MODEL_PRESET_OPUS:-anthropic:claude-opus-4-7}"
    write_kv ARCLINK_MODEL_PRESET_CHUTES "${ARCLINK_MODEL_PRESET_CHUTES:-chutes:moonshotai/Kimi-K2.6-TEE}"
    write_kv ARCLINK_ORG_PROVIDER_ENABLED "${ARCLINK_ORG_PROVIDER_ENABLED:-0}"
    write_kv ARCLINK_ORG_PROVIDER_PRESET "${ARCLINK_ORG_PROVIDER_PRESET:-}"
    write_kv ARCLINK_ORG_PROVIDER_MODEL_ID "${ARCLINK_ORG_PROVIDER_MODEL_ID:-}"
    write_kv ARCLINK_ORG_PROVIDER_REASONING_EFFORT "${ARCLINK_ORG_PROVIDER_REASONING_EFFORT:-medium}"
    write_kv ARCLINK_ORG_PROVIDER_SECRET_PROVIDER "${ARCLINK_ORG_PROVIDER_SECRET_PROVIDER:-}"
    write_kv ARCLINK_ORG_PROVIDER_SECRET "${ARCLINK_ORG_PROVIDER_SECRET:-}"
    write_kv ARCLINK_CURATOR_MODEL_PRESET "${ARCLINK_CURATOR_MODEL_PRESET:-codex}"
    write_kv ARCLINK_CURATOR_CHANNELS "${ARCLINK_CURATOR_CHANNELS:-tui-only}"
    write_kv ARCLINK_HERMES_AGENT_REF "$hermes_agent_ref"
    write_kv ARCLINK_HERMES_DOCS_SYNC_ENABLED "${ARCLINK_HERMES_DOCS_SYNC_ENABLED:-1}"
    write_kv ARCLINK_HERMES_DOCS_REPO_URL "$hermes_docs_repo_url"
    write_kv ARCLINK_HERMES_DOCS_REF "$hermes_docs_ref"
    write_kv ARCLINK_HERMES_DOCS_SOURCE_SUBDIR "${ARCLINK_HERMES_DOCS_SOURCE_SUBDIR:-website/docs}"
    write_kv ARCLINK_HERMES_DOCS_STATE_DIR "${ARCLINK_HERMES_DOCS_STATE_DIR:-$STATE_DIR/hermes-docs-src}"
    write_kv ARCLINK_HERMES_DOCS_VAULT_DIR "${ARCLINK_HERMES_DOCS_VAULT_DIR:-$VAULT_DIR/Agents_KB/hermes-agent-docs}"
    write_kv ARCLINK_EXTRA_MCP_NAME "${ARCLINK_EXTRA_MCP_NAME:-external-kb}"
    write_kv ARCLINK_EXTRA_MCP_LABEL "${ARCLINK_EXTRA_MCP_LABEL:-External knowledge rail}"
    write_kv ARCLINK_EXTRA_MCP_URL "${ARCLINK_EXTRA_MCP_URL:-}"
    write_kv ARCLINK_UPSTREAM_REPO_URL "${ARCLINK_UPSTREAM_REPO_URL:-$(canonical_arclink_upstream_repo_url)}"
    write_kv ARCLINK_UPSTREAM_BRANCH "${ARCLINK_UPSTREAM_BRANCH:-arclink}"
    write_kv ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED "${ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED:-0}"
    write_kv ARCLINK_UPSTREAM_DEPLOY_KEY_USER "${ARCLINK_UPSTREAM_DEPLOY_KEY_USER:-}"
    write_kv ARCLINK_UPSTREAM_DEPLOY_KEY_PATH "${ARCLINK_UPSTREAM_DEPLOY_KEY_PATH:-}"
    write_kv ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE "${ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE:-}"
    write_kv ARCLINK_AGENT_DASHBOARD_BACKEND_PORT_BASE "${ARCLINK_AGENT_DASHBOARD_BACKEND_PORT_BASE:-19000}"
    write_kv ARCLINK_AGENT_DASHBOARD_PROXY_PORT_BASE "${ARCLINK_AGENT_DASHBOARD_PROXY_PORT_BASE:-29000}"
    write_kv ARCLINK_AGENT_CODE_PORT_BASE "${ARCLINK_AGENT_CODE_PORT_BASE:-39000}"
    write_kv ARCLINK_AGENT_PORT_SLOT_SPAN "${ARCLINK_AGENT_PORT_SLOT_SPAN:-5000}"
    write_kv ARCLINK_AGENT_CODE_SERVER_IMAGE "$code_server_image"
    write_kv ARCLINK_AGENT_ENABLE_TAILSCALE_SERVE "$ENABLE_TAILSCALE_SERVE"
    write_kv ARCLINK_RELEASE_STATE_FILE "${ARCLINK_RELEASE_STATE_FILE:-$STATE_DIR/arclink-release.json}"
    write_kv ENABLE_NEXTCLOUD "$ENABLE_NEXTCLOUD"
    write_kv ENABLE_TAILSCALE_SERVE "$ENABLE_TAILSCALE_SERVE"
    write_kv TAILSCALE_SERVE_PORT "${TAILSCALE_SERVE_PORT:-443}"
    write_kv TAILSCALE_OPERATOR_USER "${TAILSCALE_OPERATOR_USER:-}"
    write_kv TAILSCALE_QMD_PATH "${TAILSCALE_QMD_PATH:-/mcp}"
    write_kv TAILSCALE_ARCLINK_MCP_PATH "${TAILSCALE_ARCLINK_MCP_PATH:-/arclink-mcp}"
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
    write_kv ARCLINK_INSTALL_PODMAN "${ARCLINK_INSTALL_PODMAN:-auto}"
    write_kv ARCLINK_INSTALL_TAILSCALE "${ARCLINK_INSTALL_TAILSCALE:-auto}"
    write_kv ARCLINK_INSTALL_PUBLIC_GIT "${ARCLINK_INSTALL_PUBLIC_GIT:-0}"
    write_kv ARCLINK_ORG_PROFILE_BUILDER_ENABLED "${ARCLINK_ORG_PROFILE_BUILDER_ENABLED:-0}"
    write_kv WIPE_NEXTCLOUD_STATE "${WIPE_NEXTCLOUD_STATE:-0}"
    write_kv REMOVE_PUBLIC_REPO "${REMOVE_PUBLIC_REPO:-1}"
    write_kv REMOVE_USER_TOOLING "${REMOVE_USER_TOOLING:-1}"
    write_kv REMOVE_SERVICE_USER "${REMOVE_SERVICE_USER:-0}"
  } >"$target"
  chmod 600 "$target"
}

org_profile_builder_python() {
  local repo_dir="${1:-$BOOTSTRAP_DIR}"
  local venv_dir="" python_bin=""

  if python3 -c 'import yaml, jsonschema' >/dev/null 2>&1; then
    printf '%s\n' "python3"
    return 0
  fi

  venv_dir="${ARCLINK_ORG_PROFILE_BUILDER_VENV:-${ARCLINK_PRIV_DIR:-$repo_dir/arclink-priv}/state/runtime/org-profile-builder-venv}"
  python_bin="$venv_dir/bin/python3"
  if [[ ! -x "$python_bin" ]]; then
    mkdir -p "$(dirname "$venv_dir")"
    python3 -m venv "$venv_dir"
  fi
  if ! "$python_bin" -c 'import yaml, jsonschema' >/dev/null 2>&1; then
    "$python_bin" -m pip install --upgrade --quiet PyYAML jsonschema
  fi
  "$python_bin" -c 'import yaml, jsonschema' >/dev/null
  printf '%s\n' "$python_bin"
}

maybe_run_org_profile_builder() {
  local repo_dir="${1:-$BOOTSTRAP_DIR}"
  local profile_path="${ARCLINK_PRIV_CONFIG_DIR:-$ARCLINK_PRIV_DIR/config}/org-profile.yaml"
  local builder_python=""

  if [[ "${ARCLINK_ORG_PROFILE_BUILDER_ENABLED:-0}" != "1" ]]; then
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
  if ! builder_python="$(org_profile_builder_python "$repo_dir")"; then
    echo "Could not prepare Python dependencies for the operating profile builder." >&2
    return 1
  fi
  ARCLINK_ORG_PROFILE_BUILDER_PYTHON="$builder_python" "$repo_dir/bin/org-profile-builder.sh" --file "$profile_path"
  chmod 600 "$profile_path" >/dev/null 2>&1 || true
  if [[ ${EUID:-$(id -u)} -eq 0 && -n "${ARCLINK_USER:-}" ]]; then
    chown "$ARCLINK_USER:$ARCLINK_USER" "$profile_path" >/dev/null 2>&1 || true
  fi
}

apply_org_profile_if_present_root() {
  local profile_path="${ARCLINK_PRIV_CONFIG_DIR:-$ARCLINK_PRIV_DIR/config}/org-profile.yaml"

  if [[ ! -f "$profile_path" ]]; then
    return 0
  fi
  if [[ ! -x "$ARCLINK_REPO_DIR/bin/arclink-ctl" ]]; then
    echo "Skipping operating profile apply because arclink-ctl is not installed yet."
    return 0
  fi

  echo
  echo "Applying private operating profile..."
  run_service_user_cmd "$ARCLINK_REPO_DIR/bin/arclink-ctl" org-profile apply --file "$profile_path" --yes --actor "deploy"
}

seed_private_repo() {
  local target_dir="$1"
  mkdir -p "$target_dir"
  if [[ -d "$BOOTSTRAP_DIR/templates/arclink-priv/" ]]; then
    rsync -a --ignore-existing "$BOOTSTRAP_DIR/templates/arclink-priv/" "$target_dir/"
  fi
}

sync_public_repo() {
  sync_public_repo_from_source "$BOOTSTRAP_DIR" "$ARCLINK_REPO_DIR"
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
    --exclude '/arclink-priv/' \
    --exclude '/.arclink-operator.env' \
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
  if [[ ! -d "$target_dir/.git" && "${ARCLINK_INSTALL_PUBLIC_GIT:-0}" != "1" ]]; then
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

canonical_arclink_upstream_repo_url() {
  printf '%s\n' "https://github.com/sirouk/arclink.git"
}

is_legacy_pre_rebrand_repo_url() {
  local legacy_repo_name="alma""nac"

  case "${1:-}" in
    *github.com:sirouk/$legacy_repo_name.git|*github.com/sirouk/$legacy_repo_name|*github.com/sirouk/$legacy_repo_name.git)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

is_placeholder_arclink_upstream_repo_url() {
  if is_legacy_pre_rebrand_repo_url "${1:-}"; then
    return 0
  fi

  case "${1:-}" in
    ""|https://github.com/example/arclink|https://github.com/example/arclink.git|git@github.com:example/arclink.git)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

default_arclink_upstream_repo_url() {
  local origin_url=""

  origin_url="$(git_origin_url "$BOOTSTRAP_DIR")"
  if [[ -n "$origin_url" ]] && ! is_legacy_pre_rebrand_repo_url "$origin_url"; then
    printf '%s\n' "$origin_url"
  else
    canonical_arclink_upstream_repo_url
  fi
}

use_detected_upstream_repo_url_if_placeholder() {
  if is_placeholder_arclink_upstream_repo_url "${ARCLINK_UPSTREAM_REPO_URL:-}"; then
    ARCLINK_UPSTREAM_REPO_URL="$(default_arclink_upstream_repo_url)"
  fi
}

begin_deploy_operation() {
  local operation="$1"
  local state_dir="${2:-${STATE_DIR:-}}"
  local marker=""
  local state_parent=""

  if [[ -z "$state_dir" ]]; then
    return 0
  fi
  state_parent="$(dirname "$state_dir")"
  if [[ ! -d "$state_dir" && ! -d "$state_parent" ]]; then
    return 0
  fi

  marker="$state_dir/arclink-deploy-operation.json"
  mkdir -p "$state_dir" 2>/dev/null || return 0
  if python3 - "$marker" "$operation" "$$" "$ARCLINK_DEPLOY_OPERATION_TTL_SECONDS" <<'PY'
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

target = Path(sys.argv[1])
operation = sys.argv[2]
pid = sys.argv[3]
ttl = max(60, int(sys.argv[4] or "21600"))
now = datetime.now(timezone.utc).replace(microsecond=0)
payload = {
    "operation": operation,
    "pid": pid,
    "started_at": now.isoformat().replace("+00:00", "Z"),
    "expires_at": (now + timedelta(seconds=ttl)).isoformat().replace("+00:00", "Z"),
}
target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
  then
    ARCLINK_DEPLOY_OPERATION_MARKER="$marker"
  fi
}

finish_deploy_operation() {
  if [[ -n "${ARCLINK_DEPLOY_OPERATION_MARKER:-}" ]]; then
    rm -f "$ARCLINK_DEPLOY_OPERATION_MARKER"
    ARCLINK_DEPLOY_OPERATION_MARKER=""
  fi
}

write_release_state() {
  local source_kind="$1"
  local deployed_commit="$2"
  local source_repo_url="${3:-}"
  local source_branch="${4:-}"
  local source_path="${5:-}"
  local target="${ARCLINK_RELEASE_STATE_FILE:-$STATE_DIR/arclink-release.json}"

  mkdir -p "$(dirname "$target")"
  python3 - "$target" "$source_kind" "$deployed_commit" "$source_repo_url" "$source_branch" "$source_path" "${ARCLINK_UPSTREAM_REPO_URL:-}" "${ARCLINK_UPSTREAM_BRANCH:-}" <<'PY'
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
  if git_remote_uses_ssh "${ARCLINK_UPSTREAM_REPO_URL:-}" && [[ "${ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED:-0}" != "1" ]]; then
    echo "Refusing SSH upstream without the ArcLink upstream deploy-key lane enabled." >&2
    echo "Run ./deploy.sh install to configure ARCLINK_UPSTREAM_DEPLOY_KEY_* or use an HTTPS upstream." >&2
    return 1
  fi

  rm -rf "$checkout_dir"
  if [[ "${ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED:-0}" == "1" ]] && git_remote_uses_ssh "$ARCLINK_UPSTREAM_REPO_URL"; then
    GIT_TERMINAL_PROMPT=0 \
    GIT_ASKPASS=/bin/false \
    SSH_ASKPASS=/bin/false \
    GCM_INTERACTIVE=Never \
    GIT_SSH_COMMAND="$(upstream_git_ssh_command)" \
      git clone --depth 1 --branch "$ARCLINK_UPSTREAM_BRANCH" --single-branch \
      "$ARCLINK_UPSTREAM_REPO_URL" "$checkout_dir" >/dev/null
  else
    GIT_TERMINAL_PROMPT=0 \
    GIT_ASKPASS=/bin/false \
    SSH_ASKPASS=/bin/false \
    GCM_INTERACTIVE=Never \
      git clone --depth 1 --branch "$ARCLINK_UPSTREAM_BRANCH" --single-branch \
      "$ARCLINK_UPSTREAM_REPO_URL" "$checkout_dir" >/dev/null
  fi
}

require_main_upstream_branch_for_upgrade() {
  local branch="${ARCLINK_UPSTREAM_BRANCH:-main}"
  if [[ "$branch" == "main" || "${ARCLINK_ALLOW_NON_MAIN_UPGRADE:-0}" == "1" ]]; then
    return 0
  fi
  echo "Refusing production upgrade from non-main upstream branch: $branch" >&2
  echo "Set ARCLINK_ALLOW_NON_MAIN_UPGRADE=1 only for an explicit staging or emergency deployment." >&2
  return 1
}

write_operator_checkout_artifact() {
  local artifact="${ARCLINK_OPERATOR_ARTIFACT_FILE:-$BOOTSTRAP_DIR/.arclink-operator.env}"
  local config_target="${CONFIG_TARGET:-${DISCOVERED_CONFIG:-}}"
  local status=""

  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    return 0
  fi
  if [[ -n "${ARCLINK_CONFIG_FILE:-}" ]]; then
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
    printf '# Managed by ArcLink deploy helpers. Local maintenance pointer only.\n'
    printf 'ARCLINK_OPERATOR_DEPLOYED_USER=%q\n' "${ARCLINK_USER:-}"
    printf 'ARCLINK_OPERATOR_DEPLOYED_REPO_DIR=%q\n' "${ARCLINK_REPO_DIR:-}"
    printf 'ARCLINK_OPERATOR_DEPLOYED_PRIV_DIR=%q\n' "${ARCLINK_PRIV_DIR:-}"
    printf 'ARCLINK_OPERATOR_DEPLOYED_CONFIG_FILE=%q\n' "$config_target"
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
  local tracked_repo="${2:-${ARCLINK_UPSTREAM_REPO_URL:-}}"
  local tracked_branch="${3:-${ARCLINK_UPSTREAM_BRANCH:-main}}"
  if [[ -z "$deployed_commit" || -z "${ARCLINK_DB_PATH:-}" ]]; then
    return 0
  fi

  python3 - "$ARCLINK_DB_PATH" "$deployed_commit" "$tracked_repo" "$tracked_branch" <<'PY' || true
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
    ("arclink_upgrade_last_seen_sha", deployed_commit),
    ("arclink_upgrade_relation", "equal"),
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
    VALUES ('arclink-upgrade-check', 'upgrade-check', 'arclink', 'every 1h', ?, 'ok', ?)
    ON CONFLICT(job_name) DO UPDATE SET
      target_id = excluded.target_id,
      schedule = excluded.schedule,
      last_run_at = excluded.last_run_at,
      last_status = excluded.last_status,
      last_note = excluded.last_note
    """,
    (now, note),
)
table = conn.execute(
    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'notification_outbox'"
).fetchone()
if table is not None:
    columns = {
        str(row[1])
        for row in conn.execute("PRAGMA table_info(notification_outbox)").fetchall()
    }
    if {"target_kind", "channel_kind", "message", "delivered_at"}.issubset(columns):
        # A successful deploy makes any earlier "update available" nudge stale.
        conn.execute(
            """
            UPDATE notification_outbox
            SET delivered_at = ?
            WHERE delivered_at IS NULL
              AND (
                (target_kind = 'operator' AND message LIKE 'ArcLink update available:%')
                OR (
                  target_kind = 'user-agent'
                  AND channel_kind = 'arclink-upgrade'
                  AND message LIKE 'Curator reports an ArcLink host update is available:%'
                )
              )
            """,
            (now,),
        )
conn.commit()
conn.close()
PY
  chown "$ARCLINK_USER:$ARCLINK_USER" "$ARCLINK_DB_PATH" "$ARCLINK_DB_PATH"-* >/dev/null 2>&1 || true
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
  printf '%s' "ARCLINK_CONFIG_FILE='$CONFIG_TARGET'"

  local key=""
  for key in \
    ARCLINK_CURATOR_SKIP_HERMES_SETUP \
    ARCLINK_CURATOR_SKIP_GATEWAY_SETUP \
    ARCLINK_CURATOR_FORCE_HERMES_SETUP \
    ARCLINK_CURATOR_FORCE_GATEWAY_SETUP \
    ARCLINK_CURATOR_FORCE_CHANNEL_RECONFIGURE \
    ARCLINK_CURATOR_NOTIFY_PLATFORM \
    ARCLINK_CURATOR_NOTIFY_CHANNEL_ID \
    ARCLINK_CURATOR_GENERAL_PLATFORM \
    ARCLINK_CURATOR_GENERAL_CHANNEL_ID \
    ARCLINK_CURATOR_MODEL_PRESET \
    ARCLINK_CURATOR_CHANNELS
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

print_qmd_embedding_summary() {
  echo "  Semantic embeddings:"
  case "$(lowercase "${QMD_EMBED_PROVIDER:-local}")" in
    endpoint|openai-compatible|remote|api)
      echo "    endpoint requested (${QMD_EMBED_ENDPOINT_MODEL:-model unset} via ${QMD_EMBED_ENDPOINT:-endpoint unset}); local qmd embedding is skipped for now"
      ;;
    none|off|disabled)
      echo "    disabled"
      ;;
    *)
      echo "    local qmd GGUF backend"
      ;;
  esac
}

maybe_offer_notion_ssot_setup_root() {
  if [[ "${ARCLINK_INSTALL_OFFER_NOTION_SSOT:-1}" != "1" || ! -t 0 ]]; then
    return 0
  fi

  reload_runtime_config_from_file "$CONFIG_TARGET" || true
  if [[ -n "${ARCLINK_SSOT_NOTION_SPACE_URL:-}" || -n "${ARCLINK_SSOT_NOTION_TOKEN:-}" ]]; then
    return 0
  fi

  echo
  echo "Shared Notion SSOT is not configured yet."
  echo "This optional walkthrough asks for the normal Notion page ArcLink should use,"
  echo "the internal integration secret, and the webhook verification if public ingress is enabled."
  if [[ "$(ask_yes_no "Configure the shared Notion SSOT page now" "0")" != "1" ]]; then
    echo "Skipping shared Notion setup. Run $ARCLINK_REPO_DIR/deploy.sh notion-ssot when the page and integration are ready."
    return 0
  fi

  if ! ( run_notion_ssot_setup ); then
    echo "Optional shared Notion setup did not complete; continuing with the core ArcLink install." >&2
    return 0
  fi

  reload_runtime_config_from_file "$CONFIG_TARGET" || true
  if [[ -z "${ARCLINK_SSOT_NOTION_SPACE_URL:-}" ]]; then
    return 0
  fi

  notion_migration_restart_services || true
  if [[ "$ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL" == "1" ]]; then
    ARCLINK_CONFIG_FILE="$CONFIG_TARGET" "$ARCLINK_REPO_DIR/bin/tailscale-notion-webhook-funnel.sh" || true
  fi
  wait_for_port 127.0.0.1 "$ARCLINK_MCP_PORT" 20 1 || true
  wait_for_port 127.0.0.1 "$ARCLINK_NOTION_WEBHOOK_PORT" 20 1 || true
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
  echo "    arclink-vault-watch.service"
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
    print_qmd_embedding_summary
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
    print_qmd_embedding_summary
    echo "  Watcher embeddings:"
    echo "    enabled"
  elif [[ "$watch_embed_mode" == "auto" ]]; then
    print_qmd_embedding_summary
    echo "  Watcher embeddings:"
    echo "    auto (embed only when qmd reports new pending work)"
  else
    print_qmd_embedding_summary
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
  echo "    $ARCLINK_REPO_DIR/docs/hermes-qmd-config.yaml"
  if [[ "$PDF_INGEST_ENABLED" == "1" ]]; then
    echo "  PDF-derived qmd collection:"
    echo "    $PDF_INGEST_COLLECTION_NAME"
  fi
  echo "  Quick check:"
  echo "    $ARCLINK_REPO_DIR/deploy.sh health"
  echo

  echo "ArcLink control plane"
  echo "  Control-plane MCP:"
  echo "    http://${ARCLINK_MCP_HOST:-127.0.0.1}:${ARCLINK_MCP_PORT:-8282}/mcp"
  if [[ "$AGENT_ARCLINK_MCP_URL_MODE" == "tailnet" ]]; then
    echo "  Tailnet bootstrap MCP:"
    echo "    $AGENT_ARCLINK_MCP_URL"
    if [[ "$AGENT_ARCLINK_MCP_ROUTE_STATUS" != "live" ]]; then
      echo "  Tailnet route note:"
      echo "    hostname detected, but current tailscale serve status does not show ${TAILSCALE_ARCLINK_MCP_PATH}"
    fi
  fi
  echo "  Notion webhook receiver (local):"
  echo "    http://${ARCLINK_NOTION_WEBHOOK_HOST:-127.0.0.1}:${ARCLINK_NOTION_WEBHOOK_PORT:-8283}/notion/webhook"
  if [[ -n "${ARCLINK_NOTION_WEBHOOK_PUBLIC_URL:-}" ]]; then
    echo "  Notion webhook URL (public HTTPS):"
    echo "    ${ARCLINK_NOTION_WEBHOOK_PUBLIC_URL}"
    if [[ "$ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL" == "1" ]]; then
      echo "  Exposure:"
      echo "    public internet via Tailscale Funnel on port ${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-443}"
      if [[ "$TAILSCALE_FUNNEL_HAS_NOTION_WEBHOOK" != "1" ]]; then
        echo "  Funnel route note:"
        echo "    config expects ${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH:-/notion/webhook}, but current tailscale funnel status does not show it yet"
      fi
    fi
    echo "  Notion webhook setup:"
    echo "    1. Open the Notion Developer Portal for this integration and go to the Webhooks tab."
    echo "    2. If a subscription already exists for this exact URL, edit that subscription."
    echo "       Do not create a second webhook subscription for the same ArcLink endpoint."
    echo "    3. Use this exact event selection:"
    echo "       - Page: select all Page events"
    echo "       - Database: select all Database events"
    echo "       - Data source: select all Data source events"
    echo "       - File uploads: select all File upload events"
    echo "       - View: leave all View events unchecked"
    echo "       - Comment: leave all Comment events unchecked"
    echo "    4. Run $ARCLINK_REPO_DIR/deploy.sh notion-ssot for the full step-by-step webhook walkthrough."
    echo "       It will pause at each Notion UI step, arm the install window,"
    echo "       wait for Notion to deliver the token, print the verification_token,"
    echo "       and record operator confirmation once Notion accepts the Verify step."
  else
    echo "  Notion webhook URL (public HTTPS):"
    echo "    not configured; Notion cannot reach 127.0.0.1 without separate public ingress"
  fi
  if [[ -n "${ARCLINK_SSOT_NOTION_SPACE_URL:-}" ]]; then
    echo "  Shared Notion SSOT:"
    echo "    ${ARCLINK_SSOT_NOTION_SPACE_URL}"
    if [[ -n "${ARCLINK_SSOT_NOTION_SPACE_KIND:-}" || -n "${ARCLINK_SSOT_NOTION_SPACE_ID:-}" ]]; then
      echo "  Shared Notion target:"
      echo "    ${ARCLINK_SSOT_NOTION_SPACE_KIND:-object} ${ARCLINK_SSOT_NOTION_SPACE_ID:-}"
    fi
    echo "  Shared Notion index roots:"
    echo "    ${ARCLINK_NOTION_INDEX_ROOTS:-${ARCLINK_SSOT_NOTION_ROOT_PAGE_URL:-${ARCLINK_SSOT_NOTION_SPACE_URL:-not configured}}}"
  else
    echo "  Shared Notion SSOT:"
    echo "    not configured yet; run $ARCLINK_REPO_DIR/deploy.sh notion-ssot"
  fi
  echo "  Curator Hermes home:"
  echo "    ${ARCLINK_CURATOR_HERMES_HOME:-$STATE_DIR/curator/hermes-home}"
  echo "  Operator notification channel:"
  echo "    $(describe_operator_channel_summary "${OPERATOR_NOTIFY_CHANNEL_PLATFORM:-tui-only}" "${OPERATOR_NOTIFY_CHANNEL_ID:-}")"
  echo "  Recovery CLI:"
  echo "    $ARCLINK_REPO_DIR/bin/arclink-ctl"
  echo "  Enrollment maintenance:"
  echo "    $ARCLINK_REPO_DIR/deploy.sh enrollment-status"
  echo "    $ARCLINK_REPO_DIR/deploy.sh enrollment-align"
  echo "    $ARCLINK_REPO_DIR/deploy.sh enrollment-reset"
  echo

  echo "ArcLink software updates"
  echo "  Tracked upstream:"
  echo "    ${ARCLINK_UPSTREAM_REPO_URL:-$(canonical_arclink_upstream_repo_url)}#${ARCLINK_UPSTREAM_BRANCH:-arclink}"
  echo "  Release state:"
  echo "    ${ARCLINK_RELEASE_STATE_FILE:-$STATE_DIR/arclink-release.json}"
  echo "  Upgrade command:"
  echo "    $ARCLINK_REPO_DIR/deploy.sh upgrade"
  if [[ "${ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED:-0}" == "1" ]]; then
    local upstream_repo_page="" upstream_pub_key_path="" upstream_pub_key=""
    upstream_repo_page="$(github_repo_page_from_remote "${ARCLINK_UPSTREAM_REPO_URL:-}")"
    upstream_pub_key_path="${ARCLINK_UPSTREAM_DEPLOY_KEY_PATH:-$(default_upstream_git_deploy_key_path)}.pub"
    if [[ -f "$upstream_pub_key_path" ]]; then
      upstream_pub_key="$(<"$upstream_pub_key_path")"
    fi
    echo "  Upstream deploy key:"
    echo "    ${ARCLINK_UPSTREAM_DEPLOY_KEY_PATH:-$(default_upstream_git_deploy_key_path)}"
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
    echo "    rerun install or write-config and answer yes to the ArcLink upstream deploy-key prompt"
  fi
  echo "  Manual upstream check:"
  echo "    $ARCLINK_REPO_DIR/bin/arclink-ctl upgrade check"
  echo "  Curator routine:"
  echo "    hourly via arclink-curator-refresh.timer using skill arclink-upgrade-orchestrator"
  echo

  print_agent_install_payload
  echo

  echo "GitHub: backup / history"
  echo "  Private repo:"
  echo "    $ARCLINK_PRIV_DIR"
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
    echo "    sudo -iu $ARCLINK_USER env ARCLINK_CONFIG_FILE=\"$CONFIG_TARGET\" \"$ARCLINK_REPO_DIR/bin/backup-to-github.sh\""
  else
    echo "  Configure it on the next deploy run:"
    echo "    GitHub owner/repo for arclink-priv backup"
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
    echo "    $ARCLINK_REPO_DIR/bin/render-quarto.sh"
  else
    echo "  Disabled in config. Enable it later in:"
    echo "    $CONFIG_TARGET"
  fi
}

agent_install_payload_path() {
  local state_dir="${STATE_DIR:-${ARCLINK_PRIV_DIR:-$BOOTSTRAP_DIR/arclink-priv}/state}"
  printf '%s/agent-install-payload.txt\n' "$state_dir"
}

render_agent_install_payload_body() {
  local -a payload_skills=(
    "arclink-qmd-mcp"
    "arclink-vault-reconciler"
    "arclink-first-contact"
    "arclink-vaults"
    "arclink-ssot"
    "arclink-notion-knowledge"
    "arclink-ssot-connect"
    "arclink-notion-mcp"
    "arclink-resources"
  )
  local skill_name=""

  detect_github_repo
  resolve_agent_qmd_endpoint
  resolve_agent_control_plane_endpoint
  echo "arclink_task_v1:"
  echo "  goal: enroll one shared-host user agent with explicit hermes setup, default ArcLink skills, arclink-mcp + qmd + external MCP registration, first-contact vault defaults, and exactly one 4h refresh timer"
  echo "  qmd_url: \"$AGENT_QMD_URL\""
  echo "  arclink_mcp_url: \"http://${ARCLINK_MCP_HOST:-127.0.0.1}:${ARCLINK_MCP_PORT:-8282}/mcp\""
  echo "  arclink_bootstrap_url: \"$AGENT_ARCLINK_MCP_URL\""
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
    echo "    - \"$ARCLINK_REPO_DIR/skills/$skill_name\""
  done
  echo "  model_presets:"
  echo "    codex: \"$ARCLINK_MODEL_PRESET_CODEX\""
  echo "    opus: \"$ARCLINK_MODEL_PRESET_OPUS\""
  echo "    chutes: \"$ARCLINK_MODEL_PRESET_CHUTES\""
  echo "  actions:"
  echo "    - run hermes setup explicitly for model preset selection and optional Discord or Telegram gateway setup; keep local TUI available under the user's Unix account"
  echo "    - install default ArcLink skills: qmd MCP, vault reconciler, first-contact, vaults, ssot, notion-knowledge, ssot-connect, and notion-mcp"
  echo "    - \"hermes mcp add arclink-mcp --url http://${ARCLINK_MCP_HOST:-127.0.0.1}:${ARCLINK_MCP_PORT:-8282}/mcp\""
  echo "    - \"hermes mcp add arclink-qmd --url $AGENT_QMD_URL\""
  local extra_mcp_name="${ARCLINK_EXTRA_MCP_NAME:-external-kb}"
  if [[ -n "${ARCLINK_EXTRA_MCP_URL:-}" ]]; then
    echo "    - \"hermes mcp add ${extra_mcp_name} --url ${ARCLINK_EXTRA_MCP_URL}\""
  else
    echo "    - register ${extra_mcp_name} during first contact when ARCLINK_EXTRA_MCP_URL is provided"
  fi
  echo "    - install the shipped arclink-managed-context plugin; bin/install-arclink-plugins.sh auto-enables it for Hermes homes"
  echo "    - rely on arclink-managed-context to inject ArcLink MCP auth, per-intent recipe cards, and telemetry before tool dispatch"
  echo "    - do not read HERMES_HOME secrets files and do not pass token in ArcLink MCP tool calls; the plugin injects the bootstrap token automatically"
  echo "    - run arclink-first-contact immediately after MCP registration"
  echo "    - first contact must resolve YAML .vault defaults, auto-subscribe every default_subscribed vault, fetch agents.managed-memory, and materialize the initial plugin-managed context state"
  echo "    - prefer the arclink-mcp recipe-card rails directly for vault catalog/subscription, shared Notion lookup, and SSOT reads/writes; shell wrappers are human fallback only"
  echo "    - install exactly one 4h refresh timer/service for the user agent, and rely on Curator fanout -> activation trigger -> user-agent-refresh for immediate plugin-context sync after vault/catalog changes"
  echo "  memory_contract:"
  echo "    - maintain [managed:arclink-skill-ref], [managed:vault-ref], [managed:resource-ref], [managed:qmd-ref], [managed:notion-ref], [managed:vault-topology], [managed:vault-landmarks], [managed:recall-stubs], [managed:notion-landmarks], [managed:notion-stub], and [managed:today-plate] in plugin-managed context state"
  echo "    - do not write dynamic [managed:*] stubs into HERMES_HOME/memories/MEMORY.md; MEMORY.md is user-owned long-lived memory, not the ArcLink hot-swap rail"
  echo "    - make [managed:arclink-skill-ref] explicit: ArcLink skills are active defaults, not passive extras"
  echo "    - make [managed:resource-ref] explicit: keep the user's dashboard/code URLs plus shared ArcLink rails in memory, but never store the user's credentials there"
  echo "    - make [managed:qmd-ref] explicit: qmd first for private/shared-vault questions or follow-ups from the current discussion; use mixed lex+vec retrieval"
  echo "    - make [managed:notion-ref] explicit: use shared Notion knowledge rails for indexed search/fetch context without confusing them with the governed SSOT write lane"
  echo "    - make [managed:vault-landmarks] explicit: keep a compact top-level vault map, including plain qmd-indexed folders, while leaving content depth to retrieval tools"
  echo "    - make [managed:recall-stubs] explicit: keep only high-level awareness cards and source-lane pointers; use MCP search-and-fetch for evidence and depth"
  echo "    - make [managed:notion-landmarks] explicit: keep a compact local-index map of shared Notion areas without treating it as evidence or live structured state"
  echo "    - make [managed:notion-stub] explicit: keep verification, scope, and pending-write posture visible so the agent can predict whether writes apply or queue"
  echo "    - make [managed:today-plate] explicit: surface what is on deck for the user, due pressure, and pending approvals before exploring tools"
  if [[ "$PDF_INGEST_ENABLED" == "1" ]]; then
    echo "    - include \"$PDF_INGEST_COLLECTION_NAME\" when present, especially for newly uploaded PDFs"
  fi
  echo "    - do not store note bodies, PDF bodies, or large dumps in built-in memory"
  echo "    - do not rely on background memory review or session-end flush"
  echo "    - if legacy [managed:*] entries exist in \$HERMES_HOME/memories/MEMORY.md, remove only those entries and preserve unrelated entries plus Hermes § delimiters"
  echo "  report_contract:"
  echo "    - recurring success output: exactly 1 short line"
  echo "    - recurring warn/fail output: at most 2 short lines"
  echo "    - recurring output should say only ArcLink sync, qmd indexing, memory status, and drift/blocked state"
  echo "    - preferred success form: 'ArcLink health ok: sync current, qmd indexed, managed context refreshed, drift=none.'"
  echo "  rails:"
  echo "    - prefer qmd/MCP over filesystem access; direct local qmd service or CLI is fallback only when MCP is unavailable"
  echo "    - prefer tool calls over bash mimicry; do not reach for scripts/curate-*.sh or python heredocs from a normal Hermes turn"
  echo "    - prefer the deployed arclink-owned qmd/vault over repo-scaffold guesses"
  if [[ "$AGENT_QMD_URL_MODE" == "tailnet" && "$AGENT_QMD_ROUTE_STATUS" != "live" ]]; then
    echo "    - tailnet hostname is known but ${TAILSCALE_QMD_PATH} is not visibly published; republish Tailscale Serve if MCP test fails"
  fi
  if [[ "$AGENT_ARCLINK_MCP_URL_MODE" == "tailnet" && "$AGENT_ARCLINK_MCP_ROUTE_STATUS" != "live" ]]; then
    echo "    - tailnet hostname is known but ${TAILSCALE_ARCLINK_MCP_PATH} is not visibly published; republish Tailscale Serve if remote bootstrap test fails"
  fi
  echo "    - GET /mcp returning 404 is not an MCP failure; use hermes mcp test"
  echo "    - done means: first reconciliation ran and the single 4h cron exists"
  echo "  report:"
  echo "    - active vault path"
  echo "    - arclink-mcp endpoint"
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
  CONFIG_TARGET="${ARCLINK_PRIV_CONFIG_DIR}/arclink.env"
}

init_public_repo_if_needed() {
  if [[ "${ARCLINK_INSTALL_PUBLIC_GIT:-0}" != "1" ]]; then
    return 0
  fi

  if [[ -d "$ARCLINK_REPO_DIR/.git" ]]; then
    return 0
  fi

  run_as_user "$ARCLINK_USER" "git -C '$ARCLINK_REPO_DIR' init -b main"
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

  if id -u "$ARCLINK_USER" >/dev/null 2>&1; then
    uid="$(id -u "$ARCLINK_USER")"
    systemctl start "user@$uid.service" >/dev/null 2>&1 || true

    if [[ -x "$ARCLINK_REPO_DIR/bin/nextcloud-down.sh" ]]; then
      run_as_user "$ARCLINK_USER" "env ARCLINK_CONFIG_FILE='$CONFIG_TARGET' '$ARCLINK_REPO_DIR/bin/nextcloud-down.sh'" >/dev/null 2>&1 || true
    fi

    if [[ -S "/run/user/$uid/bus" ]]; then
      run_as_user_systemd "$ARCLINK_USER" "$uid" "ARCLINK_CONFIG_FILE='$CONFIG_TARGET' systemctl --user stop arclink-nextcloud.service >/dev/null 2>&1 || true" || true
    fi
  fi

  safe_remove_path "$NEXTCLOUD_STATE_DIR"
  install -d -m 0750 -o "$ARCLINK_USER" -g "$ARCLINK_USER" "$NEXTCLOUD_STATE_DIR"
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
        "User-Agent": "arclink-backup-visibility-check",
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
    echo "arclink-priv backups currently support GitHub remotes only." >&2
    echo "Use a remote like git@github.com:owner/private-repo.git" >&2
    return 1
  fi

  visibility="$(github_repo_visibility "$owner_repo")"
  if [[ "$visibility" == "public" ]]; then
    echo "Refusing to back up arclink-priv to a public GitHub repository: $owner_repo" >&2
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
  local repo_dir="${1:-$ARCLINK_PRIV_DIR}"

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

  remote="$(backup_private_repo_origin_remote "${ARCLINK_PRIV_DIR:-}")"
  if [[ -n "$remote" ]]; then
    printf '%s\n' "$remote"
  fi
}

default_backup_git_deploy_key_path() {
  printf '%s' "${ARCLINK_HOME:-$(default_home_for_user "$ARCLINK_USER")}/.ssh/arclink-backup-ed25519"
}

default_backup_git_known_hosts_file() {
  printf '%s' "${ARCLINK_HOME:-$(default_home_for_user "$ARCLINK_USER")}/.ssh/arclink-backup-known_hosts"
}

upstream_deploy_key_user_default() {
  if [[ -n "${ARCLINK_UPSTREAM_DEPLOY_KEY_USER:-}" ]]; then
    printf '%s\n' "$ARCLINK_UPSTREAM_DEPLOY_KEY_USER"
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
  printf '%s\n' "${ARCLINK_USER:-arclink}"
}

default_upstream_git_deploy_key_path() {
  local key_user="" key_home=""

  key_user="$(upstream_deploy_key_user_default)"
  if [[ "$key_user" == "${ARCLINK_USER:-}" && -n "${ARCLINK_HOME:-}" ]]; then
    key_home="$ARCLINK_HOME"
  else
    key_home="$(resolve_user_home "$key_user" 2>/dev/null || default_home_for_user "$key_user")"
  fi
  printf '%s' "$key_home/.ssh/arclink-upstream-ed25519"
}

default_upstream_git_known_hosts_file() {
  local key_path=""

  key_path="${ARCLINK_UPSTREAM_DEPLOY_KEY_PATH:-$(default_upstream_git_deploy_key_path)}"
  printf '%s' "$(dirname "$key_path")/arclink-upstream-known_hosts"
}

upstream_git_ssh_command() {
  local key_path="" known_hosts="" quoted_key="" quoted_known_hosts=""

  key_path="${ARCLINK_UPSTREAM_DEPLOY_KEY_PATH:-$(default_upstream_git_deploy_key_path)}"
  known_hosts="${ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE:-$(default_upstream_git_known_hosts_file)}"
  printf -v quoted_key '%q' "$key_path"
  printf -v quoted_known_hosts '%q' "$known_hosts"
  printf 'ssh -i %s -o BatchMode=yes -o IPQoS=none -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=%s' \
    "$quoted_key" "$quoted_known_hosts"
}

collect_upstream_git_answers() {
  local default_remote="" default_owner_repo="" owner_repo="" default_enabled="" repo_page=""
  local default_key_user="" key_user=""

  default_remote="${ARCLINK_UPSTREAM_REPO_URL:-$(git_origin_url "$BOOTSTRAP_DIR")}"
  default_owner_repo="$(github_owner_repo_from_remote "$default_remote")"
  default_enabled="${ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED:-0}"
  default_key_user="${ARCLINK_UPSTREAM_DEPLOY_KEY_USER:-$(upstream_deploy_key_user_default)}"
  if [[ -n "${ARCLINK_UPSTREAM_DEPLOY_KEY_PATH:-}" && -f "${ARCLINK_UPSTREAM_DEPLOY_KEY_PATH:-}" ]]; then
    default_enabled="1"
  fi

  echo
  echo "GitHub deploy key for ArcLink upstream"
  echo "  This is the read/write deploy key for operator/agent code pushes to the ArcLink repo."
  echo "  The arclink-priv backup and per-user Hermes-home backups use separate deploy keys."
  echo "  In GitHub deploy key settings, enable: Allow write access."

  ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED="$(ask_yes_no "Set up an operator deploy key for the ArcLink upstream repo" "$default_enabled")"
  if [[ "$ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED" != "1" ]]; then
    ARCLINK_UPSTREAM_DEPLOY_KEY_USER="${ARCLINK_UPSTREAM_DEPLOY_KEY_USER:-}"
    ARCLINK_UPSTREAM_DEPLOY_KEY_PATH="${ARCLINK_UPSTREAM_DEPLOY_KEY_PATH:-}"
    ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE="${ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE:-}"
    return 0
  fi

  while true; do
    owner_repo="$(ask "GitHub owner/repo for ArcLink upstream deploy key" "$default_owner_repo")"
    owner_repo="${owner_repo#/}"
    owner_repo="${owner_repo%/}"
    if [[ "$owner_repo" == */* && "$owner_repo" != */ && "$owner_repo" != /* ]]; then
      ARCLINK_UPSTREAM_REPO_URL="$(github_ssh_remote_from_owner_repo "$owner_repo")"
      key_user="$(ask "Unix user that should own the ArcLink repo push deploy key" "$default_key_user")"
      if [[ "$key_user" != "${ARCLINK_UPSTREAM_DEPLOY_KEY_USER:-}" ]]; then
        ARCLINK_UPSTREAM_DEPLOY_KEY_USER="$key_user"
        ARCLINK_UPSTREAM_DEPLOY_KEY_PATH="$(default_upstream_git_deploy_key_path)"
        ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE="$(default_upstream_git_known_hosts_file)"
      else
        ARCLINK_UPSTREAM_DEPLOY_KEY_USER="$key_user"
        ARCLINK_UPSTREAM_DEPLOY_KEY_PATH="${ARCLINK_UPSTREAM_DEPLOY_KEY_PATH:-$(default_upstream_git_deploy_key_path)}"
        ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE="${ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE:-$(default_upstream_git_known_hosts_file)}"
      fi
      key_user="$ARCLINK_UPSTREAM_DEPLOY_KEY_USER"
      repo_page="$(github_repo_page_from_remote "$ARCLINK_UPSTREAM_REPO_URL")"
      echo "  Upstream SSH remote:"
      echo "    $ARCLINK_UPSTREAM_REPO_URL"
      echo "  Key owner on this host:"
      echo "    $key_user"
      echo "  Deploy key public file:"
      echo "    ${ARCLINK_UPSTREAM_DEPLOY_KEY_PATH}.pub"
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
    echo "Please enter GitHub owner/repo, for example example/arclink."
  done
}

ensure_upstream_git_deploy_key_material_for_user() {
  local key_user="${1:-$(upstream_deploy_key_user_default)}"
  local key_path="" pub_path="" key_dir="" known_hosts="" key_comment="" quoted_key="" quoted_pub="" quoted_dir="" quoted_known_hosts=""
  local key_script=""

  if [[ "${ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED:-0}" != "1" ]]; then
    return 0
  fi
  if ! git_remote_uses_ssh "${ARCLINK_UPSTREAM_REPO_URL:-}"; then
    return 0
  fi

  key_path="${ARCLINK_UPSTREAM_DEPLOY_KEY_PATH:-$(default_upstream_git_deploy_key_path)}"
  pub_path="${key_path}.pub"
  key_dir="$(dirname "$key_path")"
  known_hosts="${ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE:-$(default_upstream_git_known_hosts_file)}"
  key_comment="arclink-upstream@$(hostname -f 2>/dev/null || hostname)"

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

  if [[ "${ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED:-0}" != "1" ]]; then
    return 0
  fi
  key_user="${ARCLINK_UPSTREAM_DEPLOY_KEY_USER:-$(upstream_deploy_key_user_default)}"
  if ! id -u "$key_user" >/dev/null 2>&1; then
    echo "Configured ArcLink upstream deploy key user '$key_user' does not exist on this host." >&2
    return 1
  fi
  ensure_upstream_git_deploy_key_material_for_user "$key_user"
}

print_upstream_deploy_key_public_key() {
  local pub_path="" pub_key=""

  if [[ "${ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED:-0}" != "1" ]]; then
    return 0
  fi

  pub_path="${ARCLINK_UPSTREAM_DEPLOY_KEY_PATH:-$(default_upstream_git_deploy_key_path)}.pub"
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

  if [[ "${ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED:-0}" != "1" ]]; then
    return 0
  fi

  pub_path="${ARCLINK_UPSTREAM_DEPLOY_KEY_PATH:-$(default_upstream_git_deploy_key_path)}.pub"
  repo_page="$(github_repo_page_from_remote "${ARCLINK_UPSTREAM_REPO_URL:-}")"
  echo
  echo "ArcLink upstream deploy key"
  echo "  SSH remote:"
  echo "    ${ARCLINK_UPSTREAM_REPO_URL:-}"
  echo "  Key owner:"
  echo "    ${ARCLINK_UPSTREAM_DEPLOY_KEY_USER:-$(upstream_deploy_key_user_default)}"
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

  if [[ "${ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED:-0}" != "1" ]]; then
    return 0
  fi
  if [[ -z "$repo_dir" || ! -d "$repo_dir/.git" ]]; then
    return 0
  fi
  if ! git_remote_uses_ssh "${ARCLINK_UPSTREAM_REPO_URL:-}"; then
    return 0
  fi

  ssh_command="$(upstream_git_ssh_command)"
  if git -C "$repo_dir" remote get-url origin >/dev/null 2>&1; then
    git -C "$repo_dir" remote set-url origin "$ARCLINK_UPSTREAM_REPO_URL"
  else
    git -C "$repo_dir" remote add origin "$ARCLINK_UPSTREAM_REPO_URL"
  fi
  git -C "$repo_dir" config core.sshCommand "$ssh_command"
}

verify_upstream_git_deploy_key_access() {
  local remote="" ssh_command="" branch="" tmp_dir="" output="" write_ref=""

  if [[ "${ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED:-0}" != "1" ]]; then
    return 0
  fi

  remote="${ARCLINK_UPSTREAM_REPO_URL:-}"
  if ! git_remote_uses_ssh "$remote"; then
    return 0
  fi

  if [[ ! -f "${ARCLINK_UPSTREAM_DEPLOY_KEY_PATH:-$(default_upstream_git_deploy_key_path)}" ]]; then
    echo "ArcLink upstream deploy key private file is missing; cannot verify GitHub access." >&2
    return 1
  fi
  if [[ ! -f "${ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE:-$(default_upstream_git_known_hosts_file)}" ]]; then
    echo "ArcLink upstream deploy key known_hosts file is missing; cannot verify GitHub access." >&2
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

  branch="${ARCLINK_UPSTREAM_BRANCH:-main}"
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
    git -C "$tmp_dir" config user.name "ArcLink Deploy Key Check"
    git -C "$tmp_dir" config user.email "arclink-deploy-key-check@localhost"
    printf 'ArcLink deploy key write check for %s at %s\n' "$branch" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$tmp_dir/.arclink-deploy-key-write-check"
    git -C "$tmp_dir" add .arclink-deploy-key-write-check
    git -C "$tmp_dir" commit -m "ArcLink deploy key write check" >/dev/null
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

  key_user="${ARCLINK_UPSTREAM_DEPLOY_KEY_USER:-$(upstream_deploy_key_user_default)}"
  key_path="${ARCLINK_UPSTREAM_DEPLOY_KEY_PATH:-$(default_upstream_git_deploy_key_path)}"
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
  echo "  Generated a new ArcLink upstream deploy key. Remove the previous deploy key entry from GitHub and add the new public key below."
}

prompt_and_verify_upstream_deploy_key_access() {
  local pub_path="" repo_page="" retry="" reuse=""

  if [[ "${ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED:-0}" != "1" ]]; then
    return 0
  fi
  if [[ "${ARCLINK_UPSTREAM_DEPLOY_KEY_ACCESS_VERIFIED:-0}" == "1" ]]; then
    return 0
  fi

  pub_path="${ARCLINK_UPSTREAM_DEPLOY_KEY_PATH:-$(default_upstream_git_deploy_key_path)}.pub"
  repo_page="$(github_repo_page_from_remote "${ARCLINK_UPSTREAM_REPO_URL:-}")"
  if [[ ! -t 0 || -z "$repo_page" || ! -f "$pub_path" ]]; then
    return 0
  fi

  # Pre-flight: if the existing key already authenticates against GitHub for
  # both read and dry-run write, mirror the "Reuse existing" pattern used for
  # org-provided credentials and let the operator skip the manual paste step.
  if verify_upstream_git_deploy_key_access >/dev/null 2>&1; then
    echo
    echo "  Detected an existing ArcLink upstream deploy key with verified GitHub read+write access."
    reuse="$(ask_yes_no "Reuse existing ArcLink upstream deploy key" "1")"
    if [[ "$reuse" == "1" ]]; then
      ARCLINK_UPSTREAM_DEPLOY_KEY_ACCESS_VERIFIED=1
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
      ARCLINK_UPSTREAM_DEPLOY_KEY_ACCESS_VERIFIED=1
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
  if [[ "${ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED:-0}" != "1" ]]; then
    return 0
  fi
  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    return 0
  fi

  ensure_upstream_git_deploy_key_material_for_user "${ARCLINK_UPSTREAM_DEPLOY_KEY_USER:-$(upstream_deploy_key_user_default)}"
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
      configured="$(model_provider_resolve_target_or_default codex "${ARCLINK_MODEL_PRESET_CODEX:-}" "openai-codex:gpt-5.5")"
      configured="${configured#*:}"
      ;;
    opus)
      configured="$(model_provider_resolve_target_or_default opus "${ARCLINK_MODEL_PRESET_OPUS:-}" "anthropic:claude-opus-4-7")"
      configured="${configured#*:}"
      ;;
    chutes|*)
      configured="$(model_provider_resolve_target_or_default chutes "${ARCLINK_MODEL_PRESET_CHUTES:-}" "chutes:moonshotai/Kimi-K2.6-TEE")"
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

from arclink_onboarding_provider_auth import poll_codex_device_authorization, start_codex_device_authorization

try:
    state = start_codex_device_authorization()
except Exception as exc:
    print(f"OpenAI Codex sign-in could not start: {exc}", file=sys.stderr)
    raise SystemExit(1)

print("OpenAI Codex sign-in for the organization-provided default:", file=sys.stderr)
print(f"1. Open {state.get('verification_url')}", file=sys.stderr)
print(f"2. Enter this code: {state.get('user_code')}", file=sys.stderr)
print("Waiting for approval...", file=sys.stderr)

while True:
    time.sleep(max(3, int(state.get("poll_interval") or 5)))
    try:
        token_payload, state = poll_codex_device_authorization(state)
    except Exception as exc:
        print(f"OpenAI Codex sign-in polling failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
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

from arclink_onboarding_provider_auth import complete_anthropic_pkce_authorization, start_anthropic_pkce_authorization

try:
    state = start_anthropic_pkce_authorization()
except Exception as exc:
    print(f"Claude Opus OAuth could not start: {exc}", file=sys.stderr)
    raise SystemExit(1)

print("Claude Code OAuth for the organization-provided default:", file=sys.stderr)
print("Open this link with the Claude account and plan to share with onboarded lanes:", file=sys.stderr)
print(state.get("auth_url") or "", file=sys.stderr)
callback = input("Paste the Claude callback code string here: ").strip()
try:
    secret, _updated_state = complete_anthropic_pkce_authorization(state, callback)
except Exception as exc:
    print(f"Claude Opus OAuth failed: {exc}", file=sys.stderr)
    raise SystemExit(1)
print(secret)
PY
}

disable_org_provider_answers() {
  ARCLINK_ORG_PROVIDER_ENABLED="0"
  ARCLINK_ORG_PROVIDER_PRESET=""
  ARCLINK_ORG_PROVIDER_MODEL_ID=""
  ARCLINK_ORG_PROVIDER_REASONING_EFFORT="medium"
  ARCLINK_ORG_PROVIDER_SECRET_PROVIDER=""
  ARCLINK_ORG_PROVIDER_SECRET=""
}

ask_org_provider_auth_failure_action() {
  local provider_label="$1"
  local default_action="${2:-change}"
  local allow_retry="${3:-1}"
  local answer="" normalized_answer=""
  local choices="retry/change/skip"

  default_action="$(printf '%s' "$default_action" | tr '[:upper:]' '[:lower:]')"
  case "$default_action" in
    retry|change|skip) ;;
    *) default_action="change" ;;
  esac
  if [[ "$allow_retry" != "1" ]]; then
    choices="change/skip"
    [[ "$default_action" == "retry" ]] && default_action="change"
  fi

  if [[ ! -t 0 ]]; then
    printf '%s\n' "skip"
    return 0
  fi

  while true; do
    answer="$(ask "$provider_label credential setup failed. Action ($choices)" "$default_action")"
    normalized_answer="$(printf '%s' "$answer" | tr '[:upper:]' '[:lower:]')"
    normalized_answer="${normalized_answer//[ _-]/}"
    case "$normalized_answer" in
      r|retry|again)
        if [[ "$allow_retry" != "1" ]]; then
          echo "Retry limit reached for this provider. Choose change or skip."
          continue
        fi
        printf '%s\n' "retry"
        return 0
        ;;
      c|change|provider|chooseanother|another)
        printf '%s\n' "change"
        return 0
        ;;
      s|skip|none|without|disable)
        printf '%s\n' "skip"
        return 0
        ;;
    esac
    echo "Choose $choices."
  done
}

collect_org_provider_answers() {
  local default_enabled="${ARCLINK_ORG_PROVIDER_ENABLED:-1}"
  local provider_answer="" provider_preset="" default_model="" reasoning_answer=""
  local existing_secret_provider="${ARCLINK_ORG_PROVIDER_SECRET_PROVIDER:-}"
  local reuse_secret="0" auth_action="" provider_label=""
  local auth_attempts=0 max_auth_attempts="${ARCLINK_ORG_PROVIDER_AUTH_MAX_ATTEMPTS:-2}"
  local default_auth_action="retry" allow_auth_retry="1"

  case "$max_auth_attempts" in
    ""|*[!0-9]*) max_auth_attempts="2" ;;
  esac
  if (( max_auth_attempts < 1 )); then
    max_auth_attempts="1"
  fi

  if [[ ! -t 0 && "${ARCLINK_ORG_PROVIDER_PROMPT_NONINTERACTIVE:-0}" != "1" ]]; then
    if [[ "${ARCLINK_ORG_PROVIDER_ENABLED:-0}" == "1" && -n "${ARCLINK_ORG_PROVIDER_SECRET:-}" ]]; then
      return 0
    fi
    disable_org_provider_answers
    return 0
  fi

  ARCLINK_ORG_PROVIDER_ENABLED="$(ask_yes_no "Provide an organization-wide inference provider/default model for onboarded users" "$default_enabled")"
  if [[ "$ARCLINK_ORG_PROVIDER_ENABLED" != "1" ]]; then
    disable_org_provider_answers
    return 0
  fi

  cat <<EOF
Organization-wide inference provider:
  1) chutes - Chutes API key + default model id
  2) codex  - OpenAI Codex sign-in link + default model id
  3) opus   - Claude Opus OAuth link + default model id
EOF
  while true; do
    provider_answer="$(ask "Org inference provider" "${ARCLINK_ORG_PROVIDER_PRESET:-chutes}")"
    if provider_preset="$(normalize_org_provider_preset "$provider_answer")"; then
      break
    fi
    echo "Choose chutes, codex, or opus."
  done

  ARCLINK_ORG_PROVIDER_PRESET="$provider_preset"
  default_model="${ARCLINK_ORG_PROVIDER_MODEL_ID:-$(org_provider_default_model_id "$provider_preset")}"
  ARCLINK_ORG_PROVIDER_MODEL_ID="$(ask "Org default model id" "$default_model")"

  while true; do
    reasoning_answer="$(ask "Org default reasoning effort (xhigh/high/medium/low/minimal/none)" "${ARCLINK_ORG_PROVIDER_REASONING_EFFORT:-medium}")"
    if ARCLINK_ORG_PROVIDER_REASONING_EFFORT="$(normalize_org_reasoning_effort "$reasoning_answer")"; then
      break
    fi
    echo "Choose xhigh, high, medium, low, minimal, or none."
  done

  if [[ -n "${ARCLINK_ORG_PROVIDER_SECRET:-}" && "$existing_secret_provider" == "$provider_preset" ]]; then
    reuse_secret="$(ask_yes_no "Reuse existing org-provided $provider_preset credential" "1")"
  fi
  if [[ "$reuse_secret" == "1" ]]; then
    ARCLINK_ORG_PROVIDER_SECRET_PROVIDER="$provider_preset"
    return 0
  fi

  ARCLINK_ORG_PROVIDER_SECRET=""
  case "$provider_preset" in
    chutes)
      while [[ -z "${ARCLINK_ORG_PROVIDER_SECRET:-}" ]]; do
        ARCLINK_ORG_PROVIDER_SECRET="$(ask_secret_keep_default "Chutes API key for org-provided agents (ENTER keeps current)" "")"
        if [[ -z "$ARCLINK_ORG_PROVIDER_SECRET" ]]; then
          echo "A Chutes API key is required for org-provided Chutes."
        fi
      done
      ;;
    codex)
      if [[ "${ARCLINK_ORG_PROVIDER_CODEX_AUTH_MODE:-curator}" != "direct" ]]; then
        echo
        echo "OpenAI Codex org provider will use the Curator Codex sign-in later in setup."
        echo "If Curator is configured with a different provider, org-provided Codex will stay disabled until reconfigured."
        ARCLINK_ORG_PROVIDER_SECRET_PROVIDER="curator-codex-pending"
        ARCLINK_ORG_PROVIDER_SECRET=""
      else
        provider_label="OpenAI Codex"
        auth_attempts=0
        while [[ -z "${ARCLINK_ORG_PROVIDER_SECRET:-}" ]]; do
          auth_attempts=$((auth_attempts + 1))
          if ARCLINK_ORG_PROVIDER_SECRET="$(mint_org_codex_secret)"; then
            break
          fi
          if [[ "$auth_attempts" -ge "$max_auth_attempts" ]]; then
            default_auth_action="change"
            allow_auth_retry="0"
          else
            default_auth_action="change"
            allow_auth_retry="1"
          fi
          auth_action="$(ask_org_provider_auth_failure_action "$provider_label" "$default_auth_action" "$allow_auth_retry")"
          case "$auth_action" in
            retry)
              continue
              ;;
            change)
              ARCLINK_ORG_PROVIDER_PRESET=""
              collect_org_provider_answers
              return 0
              ;;
            skip)
              disable_org_provider_answers
              return 0
              ;;
          esac
        done
      fi
      ;;
    opus)
      provider_label="Claude Opus"
      auth_attempts=0
      while [[ -z "${ARCLINK_ORG_PROVIDER_SECRET:-}" ]]; do
        auth_attempts=$((auth_attempts + 1))
        if ARCLINK_ORG_PROVIDER_SECRET="$(mint_org_opus_secret)"; then
          break
        fi
        if [[ "$auth_attempts" -ge "$max_auth_attempts" ]]; then
          default_auth_action="change"
          allow_auth_retry="0"
        else
          default_auth_action="change"
          allow_auth_retry="1"
        fi
        auth_action="$(ask_org_provider_auth_failure_action "$provider_label" "$default_auth_action" "$allow_auth_retry")"
        case "$auth_action" in
          retry)
            continue
            ;;
          change)
            ARCLINK_ORG_PROVIDER_PRESET=""
            collect_org_provider_answers
            return 0
            ;;
          skip)
            disable_org_provider_answers
            return 0
            ;;
        esac
      done
      ;;
  esac
  ARCLINK_ORG_PROVIDER_SECRET_PROVIDER="$provider_preset"
}

collect_backup_git_answers() {
  local default_owner_repo="" owner_repo="" repo_page="" default_remote=""

  default_remote="$(resolve_backup_git_remote_default "${BACKUP_GIT_REMOTE:-}")"
  default_owner_repo="$(backup_github_owner_repo_from_remote "$default_remote")"

  echo
  echo "GitHub backup for arclink-priv"
  echo "  ArcLink can push the private repo to a private GitHub repository using a deploy-only SSH key."
  echo "  Deploy will generate that key on this host and print the public key for you to paste into GitHub."
  echo "  In GitHub deploy key settings, enable: Allow write access."

  while true; do
    owner_repo="$(ask "GitHub owner/repo for arclink-priv backup (blank to skip)" "$default_owner_repo")"
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

    echo "Please enter GitHub owner/repo, for example acme/arclink-priv, or leave it blank to skip."
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
  key_comment="arclink-backup@$(hostname -f 2>/dev/null || hostname)"

  printf -v quoted_key '%q' "$key_path"
  printf -v quoted_pub '%q' "$pub_path"

  run_as_user "$ARCLINK_USER" "
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

  echo "ArcLink deploy: Shared Host mode install / repair from current checkout"
  echo "For Sovereign Control Node mode, use: ./deploy.sh control install"
  echo

  detected_user="${ARCLINK_USER:-}"
  detected_home="${ARCLINK_HOME:-}"
  detected_repo="${ARCLINK_REPO_DIR:-}"
  detected_priv="${ARCLINK_PRIV_DIR:-}"
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

  if [[ -n "$detected_user" && "$detected_user" != "arclink" ]]; then
    echo "Detected existing configured user: $detected_user"
  fi

  while true; do
    default_user="${detected_user:-arclink}"
    ARCLINK_USER="$(ask "Service user" "$default_user")"
    if [[ -n "$ARCLINK_USER" ]]; then
      break
    fi
    echo "Service user cannot be blank."
  done

  if [[ -n "$detected_home" && ( -z "$detected_user" || "$detected_user" == "$ARCLINK_USER" ) ]]; then
    default_home="$detected_home"
  else
    default_home="$(default_home_for_user "$ARCLINK_USER")"
  fi

  if [[ -n "$detected_repo" && ( -z "$detected_user" || "$detected_user" == "$ARCLINK_USER" ) ]]; then
    default_repo="$detected_repo"
  else
    default_repo="$default_home/arclink"
  fi

  if [[ -n "$detected_priv" && ( -z "$detected_user" || "$detected_user" == "$ARCLINK_USER" ) ]]; then
    default_priv="$detected_priv"
  else
    default_priv="$default_repo/arclink-priv"
  fi

  default_nextcloud_port="${NEXTCLOUD_PORT:-18080}"
  default_git_name="${detected_git_name:-ArcLink Backup}"
  if [[ -n "$detected_git_email" && ( -z "$detected_user" || "$detected_user" == "$ARCLINK_USER" ) ]]; then
    default_git_email="$detected_git_email"
  else
    default_git_email="$ARCLINK_USER@localhost"
  fi
  default_enable_nextcloud="${ENABLE_NEXTCLOUD:-1}"
  default_enable_tailscale_serve="${ENABLE_TAILSCALE_SERVE:-0}"
  default_tailscale_serve_port="${TAILSCALE_SERVE_PORT:-443}"
  default_enable_tailscale_notion_webhook_funnel="${ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL:-0}"
  default_tailscale_operator_user="${TAILSCALE_OPERATOR_USER:-${SUDO_USER:-}}"
  default_tailscale_notion_webhook_funnel_port="${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-443}"
  default_tailscale_notion_webhook_funnel_path="$(normalize_http_path "${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH:-/notion/webhook}")"
  if [[ -z "$default_tailscale_operator_user" || "$default_tailscale_operator_user" == "root" ]]; then
    default_tailscale_operator_user="$(id -un)"
  fi
  if [[ "$default_tailscale_operator_user" == "root" ]]; then
    default_tailscale_operator_user="$ARCLINK_USER"
  fi
  default_enable_private_git="${ENABLE_PRIVATE_GIT:-1}"
  default_enable_quarto="${ENABLE_QUARTO:-1}"
  default_seed_vault="${SEED_SAMPLE_VAULT:-1}"
  default_install_public_git="${ARCLINK_INSTALL_PUBLIC_GIT:-1}"
  default_nextcloud_admin_user="${NEXTCLOUD_ADMIN_USER:-$(id -un)}"
  default_pdf_vision_endpoint="${PDF_VISION_ENDPOINT:-}"
  default_pdf_vision_model="${PDF_VISION_MODEL:-}"
  default_pdf_vision_api_key="${PDF_VISION_API_KEY:-}"

  print_tailscale_https_certificate_guidance() {
    cat <<'EOF'
Tailscale Serve/Funnel prerequisite
  Before enabling Tailscale HTTPS routes here, open:
    https://login.tailscale.com/admin/dns
  In the same tailnet as this host, enable MagicDNS and HTTPS Certificates.
  Without HTTPS Certificates, Tailscale Serve/Funnel will pause on a browser
  consent URL or fail before ArcLink can publish the routes.
  If the installer prints a Tailscale approval URL later:
    https://login.tailscale.com/f/funnel?...  for the shared-host Notion webhook
    https://login.tailscale.com/f/serve?...   for tailnet-only Nextcloud/MCP
  open it as a tailnet admin, approve the feature for this node, then return
  to this terminal and press ENTER so ArcLink can retry the route.

EOF
  }

  ARCLINK_NAME="arclink"
  ARCLINK_HOME="$(ask "Service home" "$default_home")"
  ARCLINK_REPO_DIR="$(ask "Public repo path" "$default_repo")"
  ARCLINK_PRIV_DIR="$(ask "Private repo path" "$default_priv")"
  ARCLINK_ORG_NAME="$(normalize_optional_answer "$(ask "Organization name (type none to clear)" "${ARCLINK_ORG_NAME:-}")")"
  ARCLINK_ORG_MISSION="$(normalize_optional_answer "$(ask "Organization mission (type none to clear)" "${ARCLINK_ORG_MISSION:-}")")"
  ARCLINK_ORG_PRIMARY_PROJECT="$(normalize_optional_answer "$(ask "Primary project or focus (type none to clear)" "${ARCLINK_ORG_PRIMARY_PROJECT:-}")")"
  ARCLINK_ORG_TIMEZONE="$(ask_validated_optional "Organization timezone (IANA, e.g. America/New_York; type none to clear)" "${ARCLINK_ORG_TIMEZONE:-Etc/UTC}" validate_org_timezone "Please enter a valid IANA timezone like America/New_York or type none.")"
  ARCLINK_ORG_QUIET_HOURS="$(ask_validated_optional "Organization quiet hours in local time (HH:MM-HH:MM, optional note; type none to clear)" "${ARCLINK_ORG_QUIET_HOURS:-}" validate_org_quiet_hours "Please enter quiet hours like 22:00-08:00 or 22:00-08:00 weekdays, or type none.")"
  collect_org_provider_answers
  ARCLINK_PRIV_CONFIG_DIR="$ARCLINK_PRIV_DIR/config"
  VAULT_DIR="$ARCLINK_PRIV_DIR/vault"
  STATE_DIR="$ARCLINK_PRIV_DIR/state"
  NEXTCLOUD_STATE_DIR="$STATE_DIR/nextcloud"
  RUNTIME_DIR="$STATE_DIR/runtime"
  PUBLISHED_DIR="$ARCLINK_PRIV_DIR/published"
  ARCLINK_RELEASE_STATE_FILE="${ARCLINK_RELEASE_STATE_FILE:-$STATE_DIR/arclink-release.json}"
  local default_org_profile_builder="0"
  if [[ ! -f "$ARCLINK_PRIV_CONFIG_DIR/org-profile.yaml" ]]; then
    default_org_profile_builder="1"
  fi
  if [[ ! -t 0 ]]; then
    default_org_profile_builder="0"
  fi
  ARCLINK_ORG_PROFILE_BUILDER_ENABLED="$(ask_yes_no "Build or edit the private operating profile interactively now" "$default_org_profile_builder")"
  QMD_INDEX_NAME="arclink"
  QMD_COLLECTION_NAME="vault"
  QMD_RUN_EMBED="${QMD_RUN_EMBED:-1}"
  QMD_MCP_PORT="${QMD_MCP_PORT:-8181}"
  BACKUP_GIT_BRANCH="${BACKUP_GIT_BRANCH:-main}"
  ARCLINK_UPSTREAM_REPO_URL="${ARCLINK_UPSTREAM_REPO_URL:-$(canonical_arclink_upstream_repo_url)}"
  use_detected_upstream_repo_url_if_placeholder
  ARCLINK_UPSTREAM_BRANCH="${ARCLINK_UPSTREAM_BRANCH:-arclink}"
  collect_upstream_git_answers
  ARCLINK_INSTALL_PUBLIC_GIT="$(ask_yes_no "Initialize the public repo as git if needed" "$default_install_public_git")"
  collect_backup_git_answers
  BACKUP_GIT_AUTHOR_NAME="$(ask "Git author name" "$default_git_name")"
  BACKUP_GIT_AUTHOR_EMAIL="$(ask "Git author email" "$default_git_email")"
  NEXTCLOUD_PORT="$(ask "Nextcloud local port" "$default_nextcloud_port")"

  detect_tailscale
  default_domain="${NEXTCLOUD_TRUSTED_DOMAIN:-arclink.your-tailnet.ts.net}"
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
  if [[ -n "$TAILSCALE_DNS_NAME" || -n "$TAILSCALE_TAILNET" || "$default_enable_tailscale_serve" == "1" || "$default_enable_tailscale_notion_webhook_funnel" == "1" ]]; then
    print_tailscale_https_certificate_guidance
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
    ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL="$(ask_yes_no "Enable public Tailscale Funnel for the shared-host Notion webhook only" "$default_enable_tailscale_notion_webhook_funnel")"
    if [[ "$ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL" == "1" ]]; then
      TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT="$(ask "Public Tailscale Funnel HTTPS port for the shared-host Notion webhook" "$default_tailscale_notion_webhook_funnel_port")"
      TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH="$(normalize_http_path "$(ask "Public Tailscale Funnel path for the shared-host Notion webhook" "$default_tailscale_notion_webhook_funnel_path")")"
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
    if [[ "$ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL" == "1" && "${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-443}" == "$default_tailscale_serve_port" ]]; then
      default_tailscale_serve_port="8443"
    fi
    TAILSCALE_SERVE_PORT="$(ask "Tailnet-only Tailscale HTTPS port for Nextcloud and internal MCP routes" "$default_tailscale_serve_port")"
  else
    TAILSCALE_SERVE_PORT="$default_tailscale_serve_port"
  fi
  if [[ "$ENABLE_TAILSCALE_SERVE" == "1" && "$ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL" == "1" && "${TAILSCALE_SERVE_PORT:-443}" == "${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-443}" ]]; then
    echo "Tailscale Serve and the shared-host Notion webhook Funnel cannot share the same HTTPS port." >&2
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
  ENABLE_PRIVATE_GIT="$(ask_yes_no "Initialize arclink-priv as a git repo" "$default_enable_private_git")"
  ENABLE_QUARTO="$(ask_yes_no "Enable Quarto timer/hooks" "$default_enable_quarto")"
  SEED_SAMPLE_VAULT="$(ask_yes_no "Seed a starter vault structure" "$default_seed_vault")"
  collect_qmd_embedding_answers
  PDF_VISION_ENDPOINT="$(normalize_optional_answer "$(ask "OpenAI-compatible vision endpoint for PDF page captions (base /v1 or full /v1/chat/completions; type none to disable)" "$default_pdf_vision_endpoint")")"
  PDF_VISION_MODEL="$(normalize_optional_answer "$(ask "Vision model name for PDF page captions (type none to disable)" "$default_pdf_vision_model")")"
  PDF_VISION_API_KEY="$(ask_secret_with_default "Vision API key for PDF page captions (ENTER keeps current, type none to clear)" "$default_pdf_vision_api_key")"
  PDF_VISION_MAX_PAGES="${PDF_VISION_MAX_PAGES:-6}"

  if [[ -z "$PDF_VISION_ENDPOINT" && -z "$PDF_VISION_MODEL" && -z "$PDF_VISION_API_KEY" ]]; then
    PDF_VISION_ENDPOINT=""
    PDF_VISION_MODEL=""
    PDF_VISION_API_KEY=""
  fi
  QUARTO_PROJECT_DIR="$ARCLINK_PRIV_DIR/quarto"
  QUARTO_OUTPUT_DIR="$ARCLINK_PRIV_DIR/published"
  CONFIG_TARGET="$ARCLINK_PRIV_CONFIG_DIR/arclink.env"
}

collect_remove_answers() {
  local default_user="" default_home="" default_repo="" default_priv=""
  local default_remove_user="" default_remove_tooling=""
  local confirm_text=""
  local use_detected_config="0"

  if load_detected_config; then
    use_detected_config="$(ask_yes_no "Use detected config from $DISCOVERED_CONFIG for teardown" "1")"
  fi

  echo "ArcLink deploy: remove / teardown"
  echo

  default_user="${ARCLINK_USER:-arclink}"
  default_home="${ARCLINK_HOME:-$(default_home_for_user "$default_user")}"
  default_repo="${ARCLINK_REPO_DIR:-$default_home/arclink}"
  default_priv="${ARCLINK_PRIV_DIR:-$default_repo/arclink-priv}"
  default_remove_user="0"
  if [[ "$default_user" == "arclink" && "$default_home" == "/home/arclink" ]]; then
    default_remove_user="1"
  fi
  default_remove_tooling="$default_remove_user"

  ARCLINK_NAME="${ARCLINK_NAME:-arclink}"

  if [[ "$use_detected_config" == "1" ]]; then
    ARCLINK_USER="${ARCLINK_USER:-$default_user}"
    ARCLINK_HOME="${ARCLINK_HOME:-$default_home}"
    ARCLINK_REPO_DIR="${ARCLINK_REPO_DIR:-$default_repo}"
    ARCLINK_PRIV_DIR="${ARCLINK_PRIV_DIR:-$default_priv}"

    echo "Using config:   $DISCOVERED_CONFIG"
    echo "Service user:   $ARCLINK_USER"
    echo "Service home:   $ARCLINK_HOME"
    echo "Public repo:    $ARCLINK_REPO_DIR"
    echo "Private repo:   $ARCLINK_PRIV_DIR"
    echo
  else
    ARCLINK_USER="$(ask "Service user to remove" "$default_user")"
    ARCLINK_HOME="$(ask "Service home" "$default_home")"
    ARCLINK_REPO_DIR="$(ask "Deployed public repo path" "$default_repo")"
    ARCLINK_PRIV_DIR="$(ask "Deployed private repo path" "$default_priv")"
  fi

  ARCLINK_PRIV_CONFIG_DIR="$ARCLINK_PRIV_DIR/config"
  VAULT_DIR="$ARCLINK_PRIV_DIR/vault"
  STATE_DIR="$ARCLINK_PRIV_DIR/state"
  NEXTCLOUD_STATE_DIR="$STATE_DIR/nextcloud"
  RUNTIME_DIR="$STATE_DIR/runtime"
  PUBLISHED_DIR="$ARCLINK_PRIV_DIR/published"
  ARCLINK_RELEASE_STATE_FILE="${ARCLINK_RELEASE_STATE_FILE:-$STATE_DIR/arclink-release.json}"
  QMD_INDEX_NAME="${QMD_INDEX_NAME:-arclink}"
  QMD_COLLECTION_NAME="${QMD_COLLECTION_NAME:-vault}"
  QMD_RUN_EMBED="${QMD_RUN_EMBED:-1}"
  QMD_MCP_PORT="${QMD_MCP_PORT:-8181}"
  BACKUP_GIT_BRANCH="${BACKUP_GIT_BRANCH:-main}"
  ARCLINK_UPSTREAM_REPO_URL="${ARCLINK_UPSTREAM_REPO_URL:-$(canonical_arclink_upstream_repo_url)}"
  use_detected_upstream_repo_url_if_placeholder
  ARCLINK_UPSTREAM_BRANCH="${ARCLINK_UPSTREAM_BRANCH:-arclink}"
  BACKUP_GIT_REMOTE="${BACKUP_GIT_REMOTE:-}"
  BACKUP_GIT_AUTHOR_NAME="${BACKUP_GIT_AUTHOR_NAME:-ArcLink Backup}"
  BACKUP_GIT_AUTHOR_EMAIL="${BACKUP_GIT_AUTHOR_EMAIL:-$ARCLINK_USER@localhost}"
  NEXTCLOUD_PORT="${NEXTCLOUD_PORT:-18080}"
  NEXTCLOUD_TRUSTED_DOMAIN="${NEXTCLOUD_TRUSTED_DOMAIN:-arclink.your-tailnet.ts.net}"
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
  TAILSCALE_ARCLINK_MCP_PATH="${TAILSCALE_ARCLINK_MCP_PATH:-/arclink-mcp}"
  ENABLE_PRIVATE_GIT="${ENABLE_PRIVATE_GIT:-1}"
  ENABLE_QUARTO="${ENABLE_QUARTO:-1}"
  SEED_SAMPLE_VAULT="${SEED_SAMPLE_VAULT:-1}"
  QUARTO_PROJECT_DIR="${QUARTO_PROJECT_DIR:-$ARCLINK_PRIV_DIR/quarto}"
  QUARTO_OUTPUT_DIR="${QUARTO_OUTPUT_DIR:-$ARCLINK_PRIV_DIR/published}"
  CONFIG_TARGET="${DISCOVERED_CONFIG:-$ARCLINK_PRIV_CONFIG_DIR/arclink.env}"
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

  ARCLINK_USER="${ARCLINK_USER:-arclink}"
  ARCLINK_HOME="${ARCLINK_HOME:-$(default_home_for_user "$ARCLINK_USER")}"
  ARCLINK_REPO_DIR="${ARCLINK_REPO_DIR:-$ARCLINK_HOME/arclink}"
  ARCLINK_PRIV_DIR="${ARCLINK_PRIV_DIR:-$ARCLINK_REPO_DIR/arclink-priv}"
  ARCLINK_PRIV_CONFIG_DIR="${ARCLINK_PRIV_CONFIG_DIR:-$ARCLINK_PRIV_DIR/config}"
  VAULT_DIR="${VAULT_DIR:-$ARCLINK_PRIV_DIR/vault}"
  STATE_DIR="${STATE_DIR:-$ARCLINK_PRIV_DIR/state}"
  NEXTCLOUD_STATE_DIR="${NEXTCLOUD_STATE_DIR:-$STATE_DIR/nextcloud}"
  RUNTIME_DIR="${RUNTIME_DIR:-$STATE_DIR/runtime}"
  PUBLISHED_DIR="${PUBLISHED_DIR:-$ARCLINK_PRIV_DIR/published}"
  ARCLINK_DB_PATH="${ARCLINK_DB_PATH:-$STATE_DIR/arclink-control.sqlite3}"
  ARCLINK_AGENTS_STATE_DIR="${ARCLINK_AGENTS_STATE_DIR:-$STATE_DIR/agents}"
  ARCLINK_ARCHIVED_AGENTS_DIR="${ARCLINK_ARCHIVED_AGENTS_DIR:-$STATE_DIR/archived-agents}"
  CONFIG_TARGET="${DISCOVERED_CONFIG:-${ARCLINK_CONFIG_FILE:-$ARCLINK_PRIV_CONFIG_DIR/arclink.env}}"
  ARCLINK_RELEASE_STATE_FILE="${ARCLINK_RELEASE_STATE_FILE:-$STATE_DIR/arclink-release.json}"
  ARCLINK_UPSTREAM_REPO_URL="${ARCLINK_UPSTREAM_REPO_URL:-$(canonical_arclink_upstream_repo_url)}"
  use_detected_upstream_repo_url_if_placeholder
  ARCLINK_UPSTREAM_BRANCH="${ARCLINK_UPSTREAM_BRANCH:-arclink}"
  ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED="${ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED:-0}"
  ARCLINK_UPSTREAM_DEPLOY_KEY_USER="${ARCLINK_UPSTREAM_DEPLOY_KEY_USER:-}"
  ARCLINK_UPSTREAM_DEPLOY_KEY_PATH="${ARCLINK_UPSTREAM_DEPLOY_KEY_PATH:-}"
  ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE="${ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE:-}"
}

ensure_deployed_config_exists() {
  local status=""
  status="$(probe_path_status "$CONFIG_TARGET")"
  if [[ "$status" == "exists" || "$status" == "exists-unreadable" ]]; then
    return 0
  fi
  if [[ ! -f "$CONFIG_TARGET" ]]; then
    echo "Deployed config not found at $CONFIG_TARGET" >&2
    echo "Run ./deploy.sh install first, or point ARCLINK_CONFIG_FILE at the deployed arclink.env." >&2
    exit 1
  fi
}

maybe_reexec_with_sudo_for_config() {
  local mode="$1"
  local status=""
  local -a cmd=()

  ARCLINK_REEXEC_ATTEMPTED=0
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
  ARCLINK_REEXEC_ATTEMPTED=1
  cmd=(sudo_deploy ARCLINK_CONFIG_FILE="$CONFIG_TARGET" "${DEPLOY_EXEC_PATH:-$SELF_PATH}" "$mode")
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

  ARCLINK_REEXEC_ATTEMPTED=0
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
  ARCLINK_REEXEC_ATTEMPTED=1
  if sudo_deploy ARCLINK_CONFIG_FILE="$DISCOVERED_CONFIG" "${DEPLOY_EXEC_PATH:-$SELF_PATH}" "$requested_mode"; then
    write_operator_checkout_artifact
    return 0
  else
    local reexec_status="$?"
    return "$reexec_status"
  fi
}

sudo_deploy() {
  sudo env \
    "ARCLINK_DEPLOY_BOOTSTRAP_DIR=$BOOTSTRAP_DIR" \
    "ARCLINK_DEPLOY_EXEC_PATH=${DEPLOY_EXEC_PATH:-$SELF_PATH}" \
    "ARCLINK_DEPLOY_STABLE_COPY=1" \
    "ARCLINK_DEPLOY_STABLE_OWNER_PID=${ARCLINK_DEPLOY_STABLE_OWNER_PID:-}" \
    "$@"
}

run_root_env_cmd() {
  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    env ARCLINK_CONFIG_FILE="$CONFIG_TARGET" "$@"
    return 0
  fi
  sudo env ARCLINK_CONFIG_FILE="$CONFIG_TARGET" "$@"
}

run_service_user_cmd() {
  if [[ "$(id -un)" == "$ARCLINK_USER" ]]; then
    env ARCLINK_CONFIG_FILE="$CONFIG_TARGET" "$@"
    return 0
  fi
  sudo -iu "$ARCLINK_USER" env ARCLINK_CONFIG_FILE="$CONFIG_TARGET" "$@"
}

repair_active_agent_runtime_access() {
  local agent_id="" unix_user=""

  if [[ ! -f "$ARCLINK_DB_PATH" ]]; then
    return 0
  fi

  while IFS=$'\t' read -r agent_id unix_user; do
    [[ -n "$agent_id" && -n "$unix_user" ]] || continue
    if ! getent passwd "$unix_user" >/dev/null 2>&1; then
      echo "Skipping shared-runtime ACL repair for $agent_id: unix user '$unix_user' is missing."
      continue
    fi
    echo "Repairing shared-runtime access for $agent_id ($unix_user)..."
    run_root_env_cmd "$ARCLINK_REPO_DIR/bin/arclink-ctl" user sync-access "$unix_user" --agent-id "$agent_id" >/dev/null
  done < <(run_root_env_cmd python3 - "$ARCLINK_DB_PATH" <<'PY'
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
    run_root_env_cmd "$ARCLINK_REPO_DIR/bin/arclink-ctl" user sync-access "$unix_user" --agent-id "$agent_id" >/dev/null 2>&1 || true
    if [[ -n "$bot_label" ]]; then
      run_root_env_cmd env \
        ARCLINK_CONFIG_FILE="$CONFIG_TARGET" \
        PYTHONPATH="$ARCLINK_REPO_DIR/python${PYTHONPATH:+:$PYTHONPATH}" \
        python3 - "$agent_id" "$bot_label" <<'PY' >/dev/null 2>&1 || true
import sys

from arclink_control import Config, connect_db, update_agent_display_name

cfg = Config.from_env()
with connect_db(cfg) as conn:
    update_agent_display_name(conn, cfg, agent_id=sys.argv[1], display_name=sys.argv[2])
PY
    fi
    echo "Realigning user-agent install for $agent_id ($unix_user)..."
    run_root_env_cmd env \
      ARCLINK_CONFIG_FILE="$CONFIG_TARGET" \
      "$ARCLINK_REPO_DIR/bin/refresh-agent-install.sh" \
      --unix-user "$unix_user" \
      --hermes-home "$hermes_home" \
      --repo-dir "$ARCLINK_REPO_DIR" \
      --bot-name "$bot_label" \
      --user-name "$user_name" \
      "${restart_gateway_arg[@]}" >/dev/null
  done < <(run_root_env_cmd python3 - "$ARCLINK_DB_PATH" <<'PY'
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

refresh_active_agent_context_root() {
  local agent_id="" unix_user="" hermes_home="" home_dir=""
  local agents_state_dir="${ARCLINK_AGENTS_STATE_DIR:-$STATE_DIR/agents}"
  local mcp_url="${ARCLINK_MCP_URL:-http://127.0.0.1:${ARCLINK_MCP_PORT:-8282}/mcp}"

  if [[ ! -f "$ARCLINK_DB_PATH" || ! -x "$ARCLINK_REPO_DIR/bin/user-agent-refresh.sh" ]]; then
    return 0
  fi

  while IFS=$'\t' read -r agent_id unix_user hermes_home; do
    [[ -n "$agent_id" && -n "$unix_user" && -n "$hermes_home" ]] || continue
    if ! getent passwd "$unix_user" >/dev/null 2>&1; then
      echo "Skipping immediate user-agent refresh for $agent_id: unix user '$unix_user' is missing."
      continue
    fi
    home_dir="$(resolve_user_home "$unix_user")"
    echo "Refreshing user-agent managed context for $agent_id ($unix_user)..."
    if ! runuser -u "$unix_user" -- env \
      HOME="$home_dir" \
      HERMES_HOME="$hermes_home" \
      ARCLINK_AGENT_ID="$agent_id" \
      ARCLINK_AGENTS_STATE_DIR="$agents_state_dir" \
      ARCLINK_MCP_URL="$mcp_url" \
      ARCLINK_MCP_PORT="$ARCLINK_MCP_PORT" \
      ARCLINK_SHARED_REPO_DIR="$ARCLINK_REPO_DIR" \
      "$ARCLINK_REPO_DIR/bin/user-agent-refresh.sh" >/dev/null; then
      echo "Warning: immediate user-agent refresh failed for $agent_id ($unix_user); health will report the remaining state." >&2
    fi
  done < <(run_root_env_cmd python3 - "$ARCLINK_DB_PATH" <<'PY'
import sqlite3
import sys

conn = sqlite3.connect(sys.argv[1])
conn.row_factory = sqlite3.Row
rows = conn.execute(
    """
    SELECT agent_id, unix_user, hermes_home
    FROM agents
    WHERE role = 'user' AND status = 'active'
    ORDER BY unix_user
    """
).fetchall()
for row in rows:
    print("\t".join([
        str(row["agent_id"] or ""),
        str(row["unix_user"] or ""),
        str(row["hermes_home"] or ""),
    ]))
PY
  )
}

chown_managed_paths() {
  if [[ -d "$ARCLINK_REPO_DIR" ]]; then
    find "$ARCLINK_REPO_DIR" -ignore_readdir_race \
      -path "$ARCLINK_PRIV_DIR" -prune -o \
      -exec chown -h "$ARCLINK_USER:$ARCLINK_USER" {} +
  fi

  if [[ ! -d "$ARCLINK_PRIV_DIR" ]]; then
    return 0
  fi

  if [[ "$ENABLE_NEXTCLOUD" == "1" && -n "${NEXTCLOUD_STATE_DIR:-}" && -d "$NEXTCLOUD_STATE_DIR" ]]; then
    find "$ARCLINK_PRIV_DIR" -ignore_readdir_race \
      -path "$NEXTCLOUD_STATE_DIR" -prune -o \
      -name "*.sqlite3-shm" -prune -o \
      -name "*.sqlite3-wal" -prune -o \
      -exec chown -h "$ARCLINK_USER:$ARCLINK_USER" {} +
    return 0
  fi

  find "$ARCLINK_PRIV_DIR" -ignore_readdir_race \
    -name "*.sqlite3-shm" -prune -o \
    -name "*.sqlite3-wal" -prune -o \
    -exec chown -h "$ARCLINK_USER:$ARCLINK_USER" {} +
}

enrollment_snapshot_json() {
  local target_unix_user="$1"

  run_root_env_cmd python3 - "$ARCLINK_DB_PATH" "$target_unix_user" <<'PY'
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

curator_native_gateway_system_unit_name_root() {
  local python_bin="$RUNTIME_DIR/hermes-venv/bin/python3"
  if [[ ! -x "$python_bin" ]]; then
    return 1
  fi

  HERMES_HOME="$ARCLINK_CURATOR_HERMES_HOME" "$python_bin" <<'PY'
try:
    from hermes_cli.gateway import get_service_name
except Exception:
    raise SystemExit(1)

print(f"{get_service_name()}.service")
PY
}

disable_curator_native_gateway_system_unit_root() {
  local unit=""

  unit="$(curator_native_gateway_system_unit_name_root 2>/dev/null || true)"
  if [[ -z "$unit" ]]; then
    return 0
  fi

  systemctl disable --now "$unit" >/dev/null 2>&1 || true
  systemctl reset-failed "$unit" >/dev/null 2>&1 || true
}

restart_shared_user_services_root() {
  local uid=""

  disable_curator_native_gateway_system_unit_root

  uid="$(id -u "$ARCLINK_USER")"
  systemctl start "user@$uid.service" >/dev/null 2>&1 || true
  if [[ -S "/run/user/$uid/bus" ]]; then
    run_as_user_systemd "$ARCLINK_USER" "$uid" "systemctl --user daemon-reload"
    run_as_user_systemd "$ARCLINK_USER" "$uid" "ARCLINK_CONFIG_FILE='$CONFIG_TARGET' systemctl --user restart arclink-mcp.service arclink-notion-webhook.service arclink-qmd-mcp.service arclink-qmd-update.timer arclink-vault-watch.service arclink-github-backup.timer arclink-ssot-batcher.timer arclink-notification-delivery.timer arclink-health-watch.timer arclink-curator-refresh.timer arclink-memory-synth.timer"
    run_as_user_systemd "$ARCLINK_USER" "$uid" "ARCLINK_CONFIG_FILE='$CONFIG_TARGET' systemctl --user start arclink-curator-refresh.service" || true
    run_as_user_systemd "$ARCLINK_USER" "$uid" "ARCLINK_CONFIG_FILE='$CONFIG_TARGET' systemctl --user start arclink-memory-synth.service" || true
    run_as_user_systemd "$ARCLINK_USER" "$uid" "ARCLINK_CONFIG_FILE='$CONFIG_TARGET' systemctl --user start arclink-health-watch.service" || true

    if [[ "$PDF_INGEST_ENABLED" == "1" ]]; then
      run_as_user_systemd "$ARCLINK_USER" "$uid" "ARCLINK_CONFIG_FILE='$CONFIG_TARGET' systemctl --user restart arclink-pdf-ingest.timer"
      run_as_user_systemd "$ARCLINK_USER" "$uid" "ARCLINK_CONFIG_FILE='$CONFIG_TARGET' systemctl --user stop arclink-pdf-ingest-watch.service >/dev/null 2>&1 || true"
    fi

    if [[ "$ENABLE_QUARTO" == "1" ]]; then
      run_as_user_systemd "$ARCLINK_USER" "$uid" "ARCLINK_CONFIG_FILE='$CONFIG_TARGET' systemctl --user restart arclink-quarto-render.timer"
    fi

    if [[ "$ENABLE_NEXTCLOUD" == "1" ]]; then
      run_as_user_systemd "$ARCLINK_USER" "$uid" "ARCLINK_CONFIG_FILE='$CONFIG_TARGET' systemctl --user restart arclink-nextcloud.service"
    fi
    if [[ "${ARCLINK_CURATOR_TELEGRAM_ONBOARDING_ENABLED:-0}" == "1" ]]; then
      run_as_user_systemd "$ARCLINK_USER" "$uid" "ARCLINK_CONFIG_FILE='$CONFIG_TARGET' systemctl --user restart arclink-curator-onboarding.service" || true
    fi
    if [[ "${ARCLINK_CURATOR_DISCORD_ONBOARDING_ENABLED:-0}" == "1" ]]; then
      run_as_user_systemd "$ARCLINK_USER" "$uid" "ARCLINK_CONFIG_FILE='$CONFIG_TARGET' systemctl --user restart arclink-curator-discord-onboarding.service" || true
    fi
    if [[ "${ARCLINK_CURATOR_CHANNELS:-tui-only}" == *discord* || "${ARCLINK_CURATOR_CHANNELS:-tui-only}" == *telegram* ]]; then
      run_as_user_systemd "$ARCLINK_USER" "$uid" "ARCLINK_CONFIG_FILE='$CONFIG_TARGET' systemctl --user restart arclink-curator-gateway.service" || true
    fi
    return 0
  fi

  if [[ "${ARCLINK_ALLOW_NO_USER_BUS:-0}" != "1" ]]; then
    echo "Systemd user bus unavailable for $ARCLINK_USER; services were installed but not started." >&2
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

  begin_deploy_operation "install" "$STATE_DIR"
  trap 'finish_deploy_operation; arclink_deploy_stable_copy_cleanup' EXIT

  env \
    ARCLINK_USER="$ARCLINK_USER" \
    ARCLINK_HOME="$ARCLINK_HOME" \
    ARCLINK_REPO_DIR="$ARCLINK_REPO_DIR" \
    ARCLINK_PRIV_DIR="$ARCLINK_PRIV_DIR" \
    ARCLINK_PRIV_CONFIG_DIR="$ARCLINK_PRIV_CONFIG_DIR" \
    VAULT_DIR="$VAULT_DIR" \
    STATE_DIR="$STATE_DIR" \
    NEXTCLOUD_STATE_DIR="$NEXTCLOUD_STATE_DIR" \
    PUBLISHED_DIR="$PUBLISHED_DIR" \
    QUARTO_PROJECT_DIR="$QUARTO_PROJECT_DIR" \
    ARCLINK_INSTALL_PODMAN="${ARCLINK_INSTALL_PODMAN:-auto}" \
    ARCLINK_INSTALL_TAILSCALE="${ARCLINK_INSTALL_TAILSCALE:-auto}" \
    ENABLE_TAILSCALE_SERVE="${ENABLE_TAILSCALE_SERVE:-0}" \
    ARCLINK_AGENT_ENABLE_TAILSCALE_SERVE="${ARCLINK_AGENT_ENABLE_TAILSCALE_SERVE:-$ENABLE_TAILSCALE_SERVE}" \
    "$BOOTSTRAP_DIR/bin/bootstrap-system.sh"
  sync_public_repo
  seed_private_repo "$ARCLINK_PRIV_DIR"
  write_runtime_config "$CONFIG_TARGET"
  maybe_run_org_profile_builder "$ARCLINK_REPO_DIR"
  chown_managed_paths
  ensure_upstream_git_deploy_key_material_root
  env ARCLINK_CONFIG_FILE="$CONFIG_TARGET" "$ARCLINK_REPO_DIR/bin/install-system-services.sh"
  wipe_nextcloud_state_if_requested

  init_public_repo_if_needed
  configure_upstream_git_for_repo "$ARCLINK_REPO_DIR"

  hermes_runtime_before="$(shared_hermes_runtime_commit)"
  run_as_user "$ARCLINK_USER" "env ARCLINK_CONFIG_FILE='$CONFIG_TARGET' '$ARCLINK_REPO_DIR/bin/bootstrap-userland.sh'"
  hermes_runtime_after="$(shared_hermes_runtime_commit)"
  report_shared_hermes_runtime_transition "$hermes_runtime_before" "$hermes_runtime_after"
  if [[ -n "$hermes_runtime_after" && "$hermes_runtime_before" != "$hermes_runtime_after" ]]; then
    gateway_restart_policy="restart"
  fi
  run_as_user "$ARCLINK_USER" "env ARCLINK_CONFIG_FILE='$CONFIG_TARGET' ARCLINK_ALLOW_NO_USER_BUS='${ARCLINK_ALLOW_NO_USER_BUS:-0}' '$ARCLINK_REPO_DIR/bin/install-user-services.sh'"
  chown_managed_paths
  run_as_user "$ARCLINK_USER" "env $(curator_bootstrap_env_prefix) '$ARCLINK_REPO_DIR/bin/bootstrap-curator.sh'"
  reload_runtime_config_from_file "$CONFIG_TARGET" || true
  ensure_upstream_git_deploy_key_material_root
  configure_upstream_git_for_repo "$ARCLINK_REPO_DIR"
  ensure_backup_git_deploy_key_material_root
  repair_active_agent_runtime_access
  apply_org_profile_if_present_root
  realign_active_enrolled_agents_root "$gateway_restart_policy"

  local uid=""
  restart_shared_user_services_root
  uid="$(id -u "$ARCLINK_USER")"

  if [[ -n "${TAILSCALE_OPERATOR_USER:-}" ]] && command -v tailscale >/dev/null 2>&1 && { [[ "$ENABLE_NEXTCLOUD" == "1" && "$ENABLE_TAILSCALE_SERVE" == "1" ]] || [[ "$ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL" == "1" ]]; }; then
    tailscale set --operator="$TAILSCALE_OPERATOR_USER" >/dev/null 2>&1 || true
  fi

  if [[ "$ENABLE_NEXTCLOUD" == "1" && "$ENABLE_TAILSCALE_SERVE" == "1" ]]; then
    ARCLINK_CONFIG_FILE="$CONFIG_TARGET" "$ARCLINK_REPO_DIR/bin/tailscale-nextcloud-serve.sh"
  fi
  if [[ "$ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL" == "1" ]]; then
    ARCLINK_CONFIG_FILE="$CONFIG_TARGET" "$ARCLINK_REPO_DIR/bin/tailscale-notion-webhook-funnel.sh"
  elif [[ -x "$ARCLINK_REPO_DIR/bin/tailscale-notion-webhook-unfunnel.sh" ]]; then
    ARCLINK_CONFIG_FILE="$CONFIG_TARGET" "$ARCLINK_REPO_DIR/bin/tailscale-notion-webhook-unfunnel.sh" >/dev/null 2>&1 || true
  fi

  wait_for_port 127.0.0.1 "$QMD_MCP_PORT" 20 1
  wait_for_port 127.0.0.1 "$ARCLINK_MCP_PORT" 20 1
  wait_for_port 127.0.0.1 "$ARCLINK_NOTION_WEBHOOK_PORT" 20 1
  if [[ "$ENABLE_NEXTCLOUD" == "1" ]]; then
    wait_for_port 127.0.0.1 "$NEXTCLOUD_PORT" 45 2
  fi
  maybe_offer_notion_ssot_setup_root
  refresh_active_agent_context_root

  # Record the release state before health so the check_upgrade_state probe
  # doesn't false-warn about a missing release file on a first install.
  source_commit="$(git_head_commit "$BOOTSTRAP_DIR")"
  source_branch="$(git_head_branch "$BOOTSTRAP_DIR")"
  source_repo_url="$(git_origin_url "$BOOTSTRAP_DIR")"
  if [[ -n "$source_commit" ]]; then
    write_release_state "local-checkout" "$source_commit" "$source_repo_url" "$source_branch" "$BOOTSTRAP_DIR"
    chown "$ARCLINK_USER:$ARCLINK_USER" "${ARCLINK_RELEASE_STATE_FILE:-$STATE_DIR/arclink-release.json}" >/dev/null 2>&1 || true
    refresh_upgrade_check_state_root "$source_commit" "${ARCLINK_UPSTREAM_REPO_URL:-$source_repo_url}" "${ARCLINK_UPSTREAM_BRANCH:-$source_branch}"
  fi

  echo
  echo "Running health check..."
  if [[ -S "/run/user/$uid/bus" ]]; then
    run_as_user_systemd "$ARCLINK_USER" "$uid" "ARCLINK_CONFIG_FILE='$CONFIG_TARGET' ARCLINK_HEALTH_STRICT=1 '$ARCLINK_REPO_DIR/bin/health.sh'"
  else
    run_as_user "$ARCLINK_USER" "env ARCLINK_CONFIG_FILE='$CONFIG_TARGET' ARCLINK_HEALTH_STRICT=1 '$ARCLINK_REPO_DIR/bin/health.sh'"
  fi

  if [[ -x "$ARCLINK_REPO_DIR/bin/live-agent-tool-smoke.sh" ]]; then
    echo
    echo "Running live agent tool smoke..."
    env ARCLINK_CONFIG_FILE="$CONFIG_TARGET" "$ARCLINK_REPO_DIR/bin/live-agent-tool-smoke.sh"
  fi

  echo
  echo "ArcLink install complete."
  echo "Public repo:  $ARCLINK_REPO_DIR"
  echo "Private repo: $ARCLINK_PRIV_DIR"
  echo "Config:       $CONFIG_TARGET"
  if [[ -n "$source_commit" ]]; then
    echo "Release:      ${source_commit:0:12} from current checkout"
  fi
  agent_payload_file="$(write_agent_install_payload_file || true)"
  if [[ -n "$agent_payload_file" && -f "$agent_payload_file" ]]; then
    chown "$ARCLINK_USER:$ARCLINK_USER" "$agent_payload_file" >/dev/null 2>&1 || true
  fi
  print_post_install_guide
  finish_deploy_operation
  trap 'arclink_deploy_stable_copy_cleanup' EXIT
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

  tmp_dir="$(mktemp -d /tmp/arclink-upgrade.XXXXXX)"
  checkout_dir="$tmp_dir/repo"
  begin_deploy_operation "upgrade" "$STATE_DIR"
  trap 'finish_deploy_operation; rm -rf "${tmp_dir:-}"; arclink_deploy_stable_copy_cleanup' EXIT

  require_main_upstream_branch_for_upgrade
  ensure_upstream_git_deploy_key_material_root

  echo "Fetching ArcLink upstream..."
  echo "  repo:   $ARCLINK_UPSTREAM_REPO_URL"
  echo "  branch: $ARCLINK_UPSTREAM_BRANCH"
  checkout_upstream_release "$checkout_dir"
  upstream_commit="$(git_head_commit "$checkout_dir")"
  if [[ -z "$upstream_commit" ]]; then
    echo "Could not determine upstream commit after cloning $ARCLINK_UPSTREAM_REPO_URL." >&2
    return 1
  fi

  sync_public_repo_from_source "$checkout_dir" "$ARCLINK_REPO_DIR"
  seed_private_repo "$ARCLINK_PRIV_DIR"
  write_runtime_config "$CONFIG_TARGET"
  chown_managed_paths
  configure_upstream_git_for_repo "$ARCLINK_REPO_DIR"

  env \
    ARCLINK_USER="$ARCLINK_USER" \
    ARCLINK_HOME="$ARCLINK_HOME" \
    ARCLINK_REPO_DIR="$ARCLINK_REPO_DIR" \
    ARCLINK_PRIV_DIR="$ARCLINK_PRIV_DIR" \
    ARCLINK_PRIV_CONFIG_DIR="$ARCLINK_PRIV_CONFIG_DIR" \
    VAULT_DIR="$VAULT_DIR" \
    STATE_DIR="$STATE_DIR" \
    NEXTCLOUD_STATE_DIR="$NEXTCLOUD_STATE_DIR" \
    PUBLISHED_DIR="$PUBLISHED_DIR" \
    QUARTO_PROJECT_DIR="$QUARTO_PROJECT_DIR" \
    ARCLINK_INSTALL_PODMAN="${ARCLINK_INSTALL_PODMAN:-auto}" \
    ARCLINK_INSTALL_TAILSCALE="${ARCLINK_INSTALL_TAILSCALE:-auto}" \
    ENABLE_TAILSCALE_SERVE="${ENABLE_TAILSCALE_SERVE:-0}" \
    ARCLINK_AGENT_ENABLE_TAILSCALE_SERVE="${ARCLINK_AGENT_ENABLE_TAILSCALE_SERVE:-$ENABLE_TAILSCALE_SERVE}" \
    "$ARCLINK_REPO_DIR/bin/bootstrap-system.sh"
  env ARCLINK_CONFIG_FILE="$CONFIG_TARGET" "$ARCLINK_REPO_DIR/bin/install-system-services.sh"
  hermes_runtime_before="$(shared_hermes_runtime_commit)"
  run_as_user "$ARCLINK_USER" "env ARCLINK_CONFIG_FILE='$CONFIG_TARGET' '$ARCLINK_REPO_DIR/bin/bootstrap-userland.sh'"
  hermes_runtime_after="$(shared_hermes_runtime_commit)"
  report_shared_hermes_runtime_transition "$hermes_runtime_before" "$hermes_runtime_after"
  if [[ -n "$hermes_runtime_after" && "$hermes_runtime_before" != "$hermes_runtime_after" ]]; then
    gateway_restart_policy="restart"
  fi
  run_as_user "$ARCLINK_USER" "env ARCLINK_CONFIG_FILE='$CONFIG_TARGET' ARCLINK_ALLOW_NO_USER_BUS='${ARCLINK_ALLOW_NO_USER_BUS:-0}' '$ARCLINK_REPO_DIR/bin/install-user-services.sh'"
  chown_managed_paths
  run_as_user "$ARCLINK_USER" "env ARCLINK_CURATOR_SKIP_HERMES_SETUP='1' ARCLINK_CURATOR_SKIP_GATEWAY_SETUP='1' $(curator_bootstrap_env_prefix) '$ARCLINK_REPO_DIR/bin/bootstrap-curator.sh'"
  reload_runtime_config_from_file "$CONFIG_TARGET" || true
  ensure_upstream_git_deploy_key_material_root
  configure_upstream_git_for_repo "$ARCLINK_REPO_DIR"
  ensure_backup_git_deploy_key_material_root
  repair_active_agent_runtime_access
  apply_org_profile_if_present_root
  realign_active_enrolled_agents_root "$gateway_restart_policy"

  restart_shared_user_services_root
  uid="$(id -u "$ARCLINK_USER")"

  if [[ -n "${TAILSCALE_OPERATOR_USER:-}" ]] && command -v tailscale >/dev/null 2>&1 && { [[ "$ENABLE_NEXTCLOUD" == "1" && "$ENABLE_TAILSCALE_SERVE" == "1" ]] || [[ "$ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL" == "1" ]]; }; then
    tailscale set --operator="$TAILSCALE_OPERATOR_USER" >/dev/null 2>&1 || true
  fi

  if [[ "$ENABLE_NEXTCLOUD" == "1" && "$ENABLE_TAILSCALE_SERVE" == "1" ]]; then
    ARCLINK_CONFIG_FILE="$CONFIG_TARGET" "$ARCLINK_REPO_DIR/bin/tailscale-nextcloud-serve.sh"
  fi
  if [[ "$ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL" == "1" ]]; then
    ARCLINK_CONFIG_FILE="$CONFIG_TARGET" "$ARCLINK_REPO_DIR/bin/tailscale-notion-webhook-funnel.sh"
  elif [[ -x "$ARCLINK_REPO_DIR/bin/tailscale-notion-webhook-unfunnel.sh" ]]; then
    ARCLINK_CONFIG_FILE="$CONFIG_TARGET" "$ARCLINK_REPO_DIR/bin/tailscale-notion-webhook-unfunnel.sh" >/dev/null 2>&1 || true
  fi

  wait_for_port 127.0.0.1 "$QMD_MCP_PORT" 20 1
  wait_for_port 127.0.0.1 "$ARCLINK_MCP_PORT" 20 1
  wait_for_port 127.0.0.1 "$ARCLINK_NOTION_WEBHOOK_PORT" 20 1
  if [[ "$ENABLE_NEXTCLOUD" == "1" ]]; then
    wait_for_port 127.0.0.1 "$NEXTCLOUD_PORT" 45 2
  fi
  refresh_active_agent_context_root

  # Record the release state before health so the check_upgrade_state probe can
  # see the new deployed_commit. Services have already been restarted against
  # the new code at this point; the release state reflects reality regardless
  # of whether strict health passes. If health fails, the operator inspects
  # the failures against an accurately-recorded current deployment.
  write_release_state "upstream" "$upstream_commit" "$ARCLINK_UPSTREAM_REPO_URL" "$ARCLINK_UPSTREAM_BRANCH" ""
  chown "$ARCLINK_USER:$ARCLINK_USER" "${ARCLINK_RELEASE_STATE_FILE:-$STATE_DIR/arclink-release.json}" >/dev/null 2>&1 || true
  refresh_upgrade_check_state_root "$upstream_commit" "$ARCLINK_UPSTREAM_REPO_URL" "$ARCLINK_UPSTREAM_BRANCH"

  echo
  echo "Running health check..."
  if [[ -S "/run/user/$uid/bus" ]]; then
    run_as_user_systemd "$ARCLINK_USER" "$uid" "ARCLINK_CONFIG_FILE='$CONFIG_TARGET' ARCLINK_HEALTH_STRICT=1 '$ARCLINK_REPO_DIR/bin/health.sh'"
  else
    run_as_user "$ARCLINK_USER" "env ARCLINK_CONFIG_FILE='$CONFIG_TARGET' ARCLINK_HEALTH_STRICT=1 '$ARCLINK_REPO_DIR/bin/health.sh'"
  fi

  if [[ -x "$ARCLINK_REPO_DIR/bin/live-agent-tool-smoke.sh" ]]; then
    echo
    echo "Running live agent tool smoke..."
    env ARCLINK_CONFIG_FILE="$CONFIG_TARGET" "$ARCLINK_REPO_DIR/bin/live-agent-tool-smoke.sh"
  fi

  echo
  echo "ArcLink upgrade complete."
  echo "Public repo:  $ARCLINK_REPO_DIR"
  echo "Private repo: $ARCLINK_PRIV_DIR"
  echo "Config:       $CONFIG_TARGET"
  echo "Release:      ${upstream_commit:0:12} from ${ARCLINK_UPSTREAM_REPO_URL}#${ARCLINK_UPSTREAM_BRANCH}"
  agent_payload_file="$(write_agent_install_payload_file || true)"
  if [[ -n "$agent_payload_file" && -f "$agent_payload_file" ]]; then
    chown "$ARCLINK_USER:$ARCLINK_USER" "$agent_payload_file" >/dev/null 2>&1 || true
  fi
  rm -rf "$tmp_dir"
  finish_deploy_operation
  trap 'arclink_deploy_stable_copy_cleanup' EXIT
  echo
  echo "Manual upstream check:"
  echo "  $ARCLINK_REPO_DIR/bin/arclink-ctl upgrade check"
  echo "Host health check:"
  echo "  $ARCLINK_REPO_DIR/deploy.sh health"
}

run_root_remove() {
  local uid=""
  local remove_repo_with_user_home="0"

  if id -u "$ARCLINK_USER" >/dev/null 2>&1; then
    uid="$(id -u "$ARCLINK_USER")"
    systemctl start "user@$uid.service" >/dev/null 2>&1 || true

    if [[ -x "$ARCLINK_REPO_DIR/bin/nextcloud-down.sh" ]]; then
      run_as_user "$ARCLINK_USER" "env ARCLINK_CONFIG_FILE='$CONFIG_TARGET' '$ARCLINK_REPO_DIR/bin/nextcloud-down.sh'" >/dev/null 2>&1 || true
    fi

    if [[ -S "/run/user/$uid/bus" ]]; then
      run_as_user_systemd "$ARCLINK_USER" "$uid" "ARCLINK_CONFIG_FILE='$CONFIG_TARGET' systemctl --user disable --now arclink-nextcloud.service arclink-qmd-mcp.service arclink-qmd-update.timer arclink-vault-watch.service arclink-pdf-ingest.timer arclink-pdf-ingest-watch.service arclink-github-backup.timer arclink-quarto-render.timer arclink-mcp.service arclink-notion-webhook.service arclink-ssot-batcher.timer arclink-notification-delivery.timer arclink-health-watch.timer arclink-curator-refresh.timer arclink-memory-synth.timer arclink-memory-synth.service arclink-curator-gateway.service arclink-curator-onboarding.service arclink-curator-discord-onboarding.service >/dev/null 2>&1 || true" || true
      run_as_user_systemd "$ARCLINK_USER" "$uid" "systemctl --user daemon-reload >/dev/null 2>&1 || true" || true
    fi

    find "$ARCLINK_HOME/.config/systemd/user" -maxdepth 1 -type f \
      \( -name 'arclink-*.service' -o -name 'arclink-*.timer' \) -delete 2>/dev/null || true

    loginctl disable-linger "$ARCLINK_USER" >/dev/null 2>&1 || true
    pkill -u "$ARCLINK_USER" >/dev/null 2>&1 || true
    systemctl stop "user@$uid.service" >/dev/null 2>&1 || true
  fi

  if [[ "$REMOVE_SERVICE_USER" == "1" && -d "$ARCLINK_HOME" ]]; then
    if path_is_within "$ARCLINK_REPO_DIR" "$ARCLINK_HOME"; then
      remove_repo_with_user_home="1"
    fi
  fi

  if [[ "$REMOVE_PUBLIC_REPO" == "1" && -x "$ARCLINK_REPO_DIR/bin/tailscale-nextcloud-unserve.sh" ]]; then
    ARCLINK_CONFIG_FILE="$CONFIG_TARGET" "$ARCLINK_REPO_DIR/bin/tailscale-nextcloud-unserve.sh" >/dev/null 2>&1 || true
  fi
  if [[ "$REMOVE_PUBLIC_REPO" == "1" && -x "$ARCLINK_REPO_DIR/bin/tailscale-notion-webhook-unfunnel.sh" ]]; then
    ARCLINK_CONFIG_FILE="$CONFIG_TARGET" "$ARCLINK_REPO_DIR/bin/tailscale-notion-webhook-unfunnel.sh" >/dev/null 2>&1 || true
  fi

  systemctl disable --now arclink-enrollment-provision.timer arclink-notion-claim-poll.timer >/dev/null 2>&1 || true
  systemctl stop arclink-enrollment-provision.service arclink-notion-claim-poll.service >/dev/null 2>&1 || true
  rm -f /etc/systemd/system/arclink-enrollment-provision.service /etc/systemd/system/arclink-enrollment-provision.timer
  rm -f /etc/systemd/system/arclink-notion-claim-poll.service /etc/systemd/system/arclink-notion-claim-poll.timer
  systemctl daemon-reload >/dev/null 2>&1 || true

  if [[ "$REMOVE_PUBLIC_REPO" == "1" && "$remove_repo_with_user_home" != "1" ]]; then
    safe_remove_path "$ARCLINK_REPO_DIR"
    if [[ "$ARCLINK_PRIV_DIR" != "$ARCLINK_REPO_DIR" ]] && ! path_is_within "$ARCLINK_PRIV_DIR" "$ARCLINK_REPO_DIR"; then
      safe_remove_path "$ARCLINK_PRIV_DIR"
    fi
  fi

  if [[ "$REMOVE_USER_TOOLING" == "1" && "$REMOVE_SERVICE_USER" != "1" ]]; then
    safe_remove_path "$ARCLINK_HOME/.cache/qmd"
    safe_remove_path "$ARCLINK_HOME/.cache/containers"
    safe_remove_path "$ARCLINK_HOME/.config/cni"
    safe_remove_path "$ARCLINK_HOME/.config/containers"
    safe_remove_path "$ARCLINK_HOME/.local/share/containers"
    safe_remove_path "$ARCLINK_HOME/.local/bin/podman-compose"
    safe_remove_path "$ARCLINK_HOME/.nvm"
  fi

  if [[ "$REMOVE_SERVICE_USER" == "1" ]] && id -u "$ARCLINK_USER" >/dev/null 2>&1; then
    userdel -r "$ARCLINK_USER" >/dev/null 2>&1 || userdel "$ARCLINK_USER" >/dev/null 2>&1 || true
  fi

  if [[ "$REMOVE_PUBLIC_REPO" == "1" ]]; then
    if [[ -e "$ARCLINK_REPO_DIR" ]]; then
      safe_remove_path "$ARCLINK_REPO_DIR"
    fi
    if [[ "$ARCLINK_PRIV_DIR" != "$ARCLINK_REPO_DIR" ]] && [[ -e "$ARCLINK_PRIV_DIR" ]] && ! path_is_within "$ARCLINK_PRIV_DIR" "$ARCLINK_REPO_DIR"; then
      safe_remove_path "$ARCLINK_PRIV_DIR"
    fi
  fi

  echo
  echo "ArcLink teardown complete."
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
    if [[ "${ARCLINK_REEXEC_ATTEMPTED:-0}" == "1" ]]; then
      return "$reexec_status"
    fi
  fi
  ensure_deployed_config_exists

  onboarding_file="$(mktemp)"
  provision_file="$(mktemp)"

  run_service_user_cmd "$ARCLINK_REPO_DIR/bin/arclink-ctl" --json onboarding list >"$onboarding_file"
  run_service_user_cmd "$ARCLINK_REPO_DIR/bin/arclink-ctl" --json provision list >"$provision_file"

  timer_enabled="$(systemctl is-enabled arclink-enrollment-provision.timer 2>/dev/null || true)"
  timer_active="$(systemctl is-active arclink-enrollment-provision.timer 2>/dev/null || true)"
  service_active="$(systemctl is-active arclink-enrollment-provision.service 2>/dev/null || true)"
  claim_timer_enabled="$(systemctl is-enabled arclink-notion-claim-poll.timer 2>/dev/null || true)"
  claim_timer_active="$(systemctl is-active arclink-notion-claim-poll.timer 2>/dev/null || true)"
  claim_service_active="$(systemctl is-active arclink-notion-claim-poll.service 2>/dev/null || true)"

  echo "Enrollment status"
  echo
  echo "Config:        $CONFIG_TARGET"
  echo "Service user:  $ARCLINK_USER"
  echo "Repo:          $ARCLINK_REPO_DIR"
  echo "DB:            $ARCLINK_DB_PATH"
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
  echo "  $ARCLINK_REPO_DIR/deploy.sh enrollment-trace --unix-user <unix-user>"
  echo "  $ARCLINK_REPO_DIR/deploy.sh enrollment-align"
  echo "  $ARCLINK_REPO_DIR/deploy.sh enrollment-reset"
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
    if [[ "${ARCLINK_REEXEC_ATTEMPTED:-0}" == "1" ]]; then
      return "$reexec_status"
    fi
  fi
  ensure_deployed_config_exists

  selector_spec="$(resolve_enrollment_trace_selector)"
  IFS=$'\t' read -r selector_kind selector_value <<<"$selector_spec"
  trace_file="$(mktemp)"

  run_root_env_cmd python3 - "$ARCLINK_DB_PATH" "$STATE_DIR" "$selector_kind" "$selector_value" <<'PY' >"$trace_file"
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
                payload["next_action"] = "Wait for the root provisioner timer or start arclink-enrollment-provision.service once."
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

  timer_enabled="$(systemctl is-enabled arclink-enrollment-provision.timer 2>/dev/null || true)"
  timer_active="$(systemctl is-active arclink-enrollment-provision.timer 2>/dev/null || true)"
  service_active="$(systemctl is-active arclink-enrollment-provision.service 2>/dev/null || true)"
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
  echo "Service user:  $ARCLINK_USER"
  echo "Repo:          $ARCLINK_REPO_DIR"
  echo "DB:            $ARCLINK_DB_PATH"
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
    user_gateway_unit="/home/$resolved_unix_user/.config/systemd/user/arclink-user-agent-gateway.service"
    gateway_enabled="$(run_root_env_cmd runuser -u "$resolved_unix_user" -- env XDG_RUNTIME_DIR="/run/user/$resolved_uid" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$resolved_uid/bus" systemctl --user is-enabled arclink-user-agent-gateway.service 2>/dev/null || true)"
    gateway_active="$(run_root_env_cmd runuser -u "$resolved_unix_user" -- env XDG_RUNTIME_DIR="/run/user/$resolved_uid" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$resolved_uid/bus" systemctl --user is-active arclink-user-agent-gateway.service 2>/dev/null || true)"
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
    run_root_env_cmd runuser -u "$resolved_unix_user" -- env XDG_RUNTIME_DIR="/run/user/$resolved_uid" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$resolved_uid/bus" systemctl --user status arclink-user-agent-gateway.service -n "$TRACE_LOG_LINES" --no-pager || true
  fi

  echo
  echo "Recent root provisioner journal:"
  run_root_env_cmd journalctl -u arclink-enrollment-provision.service -n "$TRACE_LOG_LINES" --no-pager || true

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
  echo "  $ARCLINK_REPO_DIR/deploy.sh enrollment-align"
  if [[ -n "$resolved_unix_user" ]]; then
    echo "  ENROLLMENT_RESET_UNIX_USER=$resolved_unix_user $ARCLINK_REPO_DIR/deploy.sh enrollment-reset"
  else
    echo "  $ARCLINK_REPO_DIR/deploy.sh enrollment-reset"
  fi
}

run_enrollment_align() {
  local reexec_status=""

  prepare_deployed_context
  if maybe_reexec_with_sudo_for_config enrollment-align; then
    return 0
  else
    reexec_status="$?"
    if [[ "${ARCLINK_REEXEC_ATTEMPTED:-0}" == "1" ]]; then
      return "$reexec_status"
    fi
  fi
  ensure_deployed_config_exists

  if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    sudo_deploy ARCLINK_CONFIG_FILE="$CONFIG_TARGET" "${DEPLOY_EXEC_PATH:-$SELF_PATH}" enrollment-align
    write_operator_checkout_artifact
    return 0
  fi

  echo "Realigning enrollment services..."
  env ARCLINK_CONFIG_FILE="$CONFIG_TARGET" "$ARCLINK_REPO_DIR/bin/install-system-services.sh"
  run_as_user "$ARCLINK_USER" "env ARCLINK_CONFIG_FILE='$CONFIG_TARGET' ARCLINK_ALLOW_NO_USER_BUS='${ARCLINK_ALLOW_NO_USER_BUS:-1}' '$ARCLINK_REPO_DIR/bin/install-user-services.sh'"
  realign_active_enrolled_agents_root
  restart_shared_user_services_root || true
  systemctl reset-failed arclink-enrollment-provision.service arclink-enrollment-provision.timer arclink-notion-claim-poll.service arclink-notion-claim-poll.timer >/dev/null 2>&1 || true
  systemctl enable arclink-enrollment-provision.timer arclink-notion-claim-poll.timer >/dev/null
  systemctl restart arclink-enrollment-provision.timer arclink-notion-claim-poll.timer
  systemctl start arclink-enrollment-provision.service >/dev/null 2>&1 || true
  systemctl start arclink-notion-claim-poll.service >/dev/null 2>&1 || true
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
    if [[ "${ARCLINK_REEXEC_ATTEMPTED:-0}" == "1" ]]; then
      return "$reexec_status"
    fi
  fi
  ensure_deployed_config_exists

  if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    sudo_deploy ARCLINK_CONFIG_FILE="$CONFIG_TARGET" "${DEPLOY_EXEC_PATH:-$SELF_PATH}" enrollment-reset
    write_operator_checkout_artifact
    return 0
  fi

  target_unix_user="$(ask "Unix user to reset" "${ENROLLMENT_RESET_UNIX_USER:-}")"
  if [[ -z "$target_unix_user" ]]; then
    echo "Unix user is required." >&2
    exit 1
  fi
  if [[ "$target_unix_user" == "$ARCLINK_USER" ]]; then
    echo "Refusing to reset the ArcLink service user '$ARCLINK_USER'." >&2
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
      ARCLINK_CONFIG_FILE="$CONFIG_TARGET"
      "$ARCLINK_REPO_DIR/bin/arclink-ctl"
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
    systemctl start arclink-enrollment-provision.service >/dev/null 2>&1 || true
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
      env ARCLINK_CONFIG_FILE="$CONFIG_TARGET" \
        "$ARCLINK_REPO_DIR/bin/arclink-ctl" provision cancel "$request_id" \
        --reason "reset via deploy.sh enrollment-reset" >/dev/null 2>&1 || true
    elif [[ "$request_status" == "pending" ]]; then
      run_service_user_cmd "$ARCLINK_REPO_DIR/bin/arclink-ctl" request deny "$request_id" \
        --surface ctl --actor deploy-enrollment-reset >/dev/null 2>&1 || true
    fi
  done

  for session_id in "${session_ids[@]}"; do
    [[ -n "$session_id" ]] || continue
    run_service_user_cmd "$ARCLINK_REPO_DIR/bin/arclink-ctl" onboarding deny "$session_id" \
      --actor deploy-enrollment-reset --reason "reset via deploy.sh enrollment-reset" >/dev/null 2>&1 || true
  done

  if [[ "$agent_status" == "active" || "$agent_status" == "pending" ]]; then
    env ARCLINK_CONFIG_FILE="$CONFIG_TARGET" \
      "$ARCLINK_REPO_DIR/bin/arclink-ctl" agent deenroll "$target_unix_user" \
      --actor deploy-enrollment-reset >/dev/null 2>&1 || true
  fi

  rm -rf "$ARCLINK_AGENTS_STATE_DIR/$agent_id"
  if [[ "$remove_archives" == "1" ]]; then
    rm -rf "$ARCLINK_ARCHIVED_AGENTS_DIR/$agent_id"
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
    run_root_env_cmd python3 - "$ARCLINK_DB_PATH" "${rate_subjects[@]}" <<'PY'
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

  systemctl start arclink-enrollment-provision.service >/dev/null 2>&1 || true
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
  # On-demand detector run: same logic that arclink-curator-refresh.timer
  # invokes hourly via `arclink-ctl internal pin-upgrade-check`.
  load_detected_config || true
  exec sudo -u "${ARCLINK_USER:-arclink}" \
    env ARCLINK_CONFIG_FILE="${ARCLINK_CONFIG_FILE:-/home/arclink/arclink/arclink-priv/config/arclink.env}" \
    "$BOOTSTRAP_DIR/bin/arclink-ctl" --json internal pin-upgrade-check
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
  echo "config/pins.json: $ARCLINK_PINS_FILE (validated)"
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
    ARCLINK_UPSTREAM_REPO_URL="${ARCLINK_UPSTREAM_REPO_URL:-}" \
    ARCLINK_UPSTREAM_BRANCH="${ARCLINK_UPSTREAM_BRANCH:-arclink}" \
    ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED="${ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED:-}" \
    ARCLINK_UPSTREAM_DEPLOY_KEY_USER="${ARCLINK_UPSTREAM_DEPLOY_KEY_USER:-}" \
    ARCLINK_UPSTREAM_DEPLOY_KEY_PATH="${ARCLINK_UPSTREAM_DEPLOY_KEY_PATH:-}" \
    ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE="${ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE:-}" \
    ARCLINK_CONFIG_FILE="${ARCLINK_CONFIG_FILE:-}" \
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
    if ! sudo_deploy ARCLINK_CONFIG_FILE="$DISCOVERED_CONFIG" "${DEPLOY_EXEC_PATH:-$SELF_PATH}" health; then
      return 1
    fi
    write_operator_checkout_artifact
    return 0
  fi

  if [[ -z "${ARCLINK_USER:-}" ]]; then
    ARCLINK_USER="arclink"
  fi
  if [[ -z "${ARCLINK_HOME:-}" ]]; then
    ARCLINK_HOME="$(default_home_for_user "$ARCLINK_USER")"
  fi
  if [[ -z "${ARCLINK_REPO_DIR:-}" ]]; then
    ARCLINK_REPO_DIR="$ARCLINK_HOME/arclink"
  fi
  if [[ -z "${ARCLINK_PRIV_DIR:-}" ]]; then
    ARCLINK_PRIV_DIR="$ARCLINK_REPO_DIR/arclink-priv"
  fi

  ARCLINK_PRIV_CONFIG_DIR="${ARCLINK_PRIV_CONFIG_DIR:-$ARCLINK_PRIV_DIR/config}"
  CONFIG_TARGET="${DISCOVERED_CONFIG:-$ARCLINK_PRIV_CONFIG_DIR/arclink.env}"

  if ! id -u "$ARCLINK_USER" >/dev/null 2>&1; then
    echo "Service user '$ARCLINK_USER' does not exist." >&2
    exit 1
  fi

  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    if [[ ! -x "$ARCLINK_REPO_DIR/bin/health.sh" ]]; then
      echo "Health script not found at $ARCLINK_REPO_DIR/bin/health.sh" >&2
      exit 1
    fi
    uid="$(id -u "$ARCLINK_USER")"
    if [[ -S "/run/user/$uid/bus" ]]; then
      run_as_user_systemd "$ARCLINK_USER" "$uid" "ARCLINK_CONFIG_FILE='$CONFIG_TARGET' '$ARCLINK_REPO_DIR/bin/health.sh'"
    else
      run_as_user "$ARCLINK_USER" "env ARCLINK_CONFIG_FILE='$CONFIG_TARGET' '$ARCLINK_REPO_DIR/bin/health.sh'"
    fi
    return 0
  fi

  if [[ "$(id -un)" == "$ARCLINK_USER" ]]; then
    if [[ ! -x "$ARCLINK_REPO_DIR/bin/health.sh" ]]; then
      echo "Health script not found at $ARCLINK_REPO_DIR/bin/health.sh" >&2
      exit 1
    fi
    env ARCLINK_CONFIG_FILE="$CONFIG_TARGET" "$ARCLINK_REPO_DIR/bin/health.sh"
    return 0
  fi

  uid="$(id -u "$ARCLINK_USER")"
  if [[ -S "/run/user/$uid/bus" ]]; then
    sudo -iu "$ARCLINK_USER" env \
      XDG_RUNTIME_DIR="/run/user/$uid" \
      DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" \
      ARCLINK_CONFIG_FILE="$CONFIG_TARGET" \
      "$ARCLINK_REPO_DIR/bin/health.sh"
  else
    sudo -iu "$ARCLINK_USER" env \
      ARCLINK_CONFIG_FILE="$CONFIG_TARGET" \
      "$ARCLINK_REPO_DIR/bin/health.sh"
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
      sudo_deploy
      "ARCLINK_CONFIG_FILE=$CONFIG_TARGET"
      "NEXTCLOUD_ROTATE_ASSUME_YES=${NEXTCLOUD_ROTATE_ASSUME_YES:-0}"
    )
    if [[ -n "${NEXTCLOUD_ROTATE_POSTGRES_PASSWORD:-}" ]]; then
      sudo_pg_file="$(mktemp /tmp/arclink-nextcloud-pg.XXXXXX)"
      chmod 600 "$sudo_pg_file"
      printf '%s\n' "$NEXTCLOUD_ROTATE_POSTGRES_PASSWORD" >"$sudo_pg_file"
      cmd+=("NEXTCLOUD_ROTATE_POSTGRES_PASSWORD_FILE=$sudo_pg_file")
    fi
    if [[ -n "${NEXTCLOUD_ROTATE_ADMIN_PASSWORD:-}" ]]; then
      sudo_admin_file="$(mktemp /tmp/arclink-nextcloud-admin.XXXXXX)"
      chmod 600 "$sudo_admin_file"
      printf '%s\n' "$NEXTCLOUD_ROTATE_ADMIN_PASSWORD" >"$sudo_admin_file"
      cmd+=("NEXTCLOUD_ROTATE_ADMIN_PASSWORD_FILE=$sudo_admin_file")
    fi
    cmd+=("${DEPLOY_EXEC_PATH:-$SELF_PATH}" rotate-nextcloud-secrets)

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

  if ! id -u "$ARCLINK_USER" >/dev/null 2>&1; then
    echo "Service user '$ARCLINK_USER' does not exist." >&2
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

  echo "ArcLink deploy: rotate live Nextcloud credentials"
  echo
  echo "Config:             $CONFIG_TARGET"
  echo "Service user:       $ARCLINK_USER"
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

  uid="$(id -u "$ARCLINK_USER")"
  systemctl start "user@$uid.service" >/dev/null 2>&1 || true
  run_as_user_systemd "$ARCLINK_USER" "$uid" "ARCLINK_CONFIG_FILE='$CONFIG_TARGET' systemctl --user start arclink-nextcloud.service >/dev/null 2>&1 || true"

  pg_file="$(mktemp /tmp/arclink-nextcloud-pg.XXXXXX)"
  admin_file="$(mktemp /tmp/arclink-nextcloud-admin.XXXXXX)"
  chmod 600 "$pg_file" "$admin_file"
  printf '%s\n' "$new_postgres_password" >"$pg_file"
  printf '%s\n' "$new_admin_password" >"$admin_file"
  chown "$ARCLINK_USER:$ARCLINK_USER" "$pg_file" "$admin_file"
  run_as_user "$ARCLINK_USER" \
    "env ARCLINK_CONFIG_FILE='$CONFIG_TARGET' NEXTCLOUD_ROTATE_POSTGRES_PASSWORD_FILE='$pg_file' NEXTCLOUD_ROTATE_ADMIN_PASSWORD_FILE='$admin_file' '$ARCLINK_REPO_DIR/bin/rotate-nextcloud-secrets.sh'" || rotate_status=$?
  rm -f "$pg_file" "$admin_file"
  if (( rotate_status != 0 )); then
    return "$rotate_status"
  fi

  POSTGRES_PASSWORD="$new_postgres_password"
  NEXTCLOUD_ADMIN_PASSWORD="$new_admin_password"
  write_runtime_config "$CONFIG_TARGET"
  reload_runtime_config_from_file "$CONFIG_TARGET" || true

  run_as_user_systemd "$ARCLINK_USER" "$uid" "ARCLINK_CONFIG_FILE='$CONFIG_TARGET' systemctl --user restart arclink-nextcloud.service"
  run_as_user_systemd "$ARCLINK_USER" "$uid" "ARCLINK_CONFIG_FILE='$CONFIG_TARGET' ARCLINK_HEALTH_STRICT=1 '$ARCLINK_REPO_DIR/bin/health.sh'"

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
    if [[ "${ARCLINK_REEXEC_ATTEMPTED:-0}" == "1" ]]; then
      return "$reexec_status"
    fi
  fi
  ensure_deployed_config_exists
  reload_runtime_config_from_file "$CONFIG_TARGET" || true
  if [[ "${ARCLINK_NOTION_MIGRATION_FRESH_DEFAULTS:-0}" == "1" ]]; then
    ARCLINK_SSOT_NOTION_ROOT_PAGE_URL=""
    ARCLINK_SSOT_NOTION_ROOT_PAGE_ID=""
    ARCLINK_SSOT_NOTION_SPACE_URL=""
    ARCLINK_SSOT_NOTION_SPACE_ID=""
    ARCLINK_SSOT_NOTION_SPACE_KIND=""
    ARCLINK_SSOT_NOTION_TOKEN=""
    ARCLINK_NOTION_INDEX_ROOTS=""
  fi

  if [[ ${EUID:-$(id -u)} -ne 0 && "$(id -un)" != "$ARCLINK_USER" ]]; then
    echo "Switching to sudo for Notion SSOT setup..."
    sudo_deploy ARCLINK_CONFIG_FILE="$CONFIG_TARGET" "${DEPLOY_EXEC_PATH:-$SELF_PATH}" notion-ssot
    write_operator_checkout_artifact
    return 0
  fi

  echo "ArcLink deploy: Notion SSOT setup / handshake"
  echo
  echo "Make one normal Notion page for ArcLink, such as 'The ArcLink', then"
  echo "paste that page URL below."
  echo "Do not use the workspace Home screen."
  echo
  echo "Before you continue in Notion:"
  echo "  1) Create a normal page for ArcLink in the Teamspace you want it to use."
  echo "  2) Open this page in your browser:"
  echo "     https://www.notion.so/profile/integrations/internal"
  echo "  3) If Notion lands you back in the workspace UI, open your workspace"
  echo "     switcher in the top-left, then go to Settings -> Integrations."
  echo "  4) Click Create new integration."
  echo "  5) Name it something like ArcLink Curator, optionally upload an icon"
  echo "     (the Curator Discord avatar in this repo works well), choose the"
  echo "     associated workspace, and click Create."
  echo "  6) On the capabilities screen:"
  echo "     - turn on every checkbox capability Notion offers on that screen"
  echo "     - for user information, choose Read user information including email addresses"
  echo "       so ArcLink can verify users against their Notion email"
  echo "     - click Save"
  echo "  7) If you land on Discover new connections / Show all and see options like"
  echo "     Notion MCP, GitHub, Slack, Jira, or other partner apps, stop there:"
  echo "     those are not the right choice for ArcLink's shared SSOT setup."
  echo "  8) Open that internal integration and, near Internal integration secret,"
  echo "     click Show and then copy the key."
  echo "  9) In that integration, open Manage page access and grant access to the"
  echo "     parent page or Teamspace root ArcLink should live under."
  echo "     New child pages and databases under that granted subtree inherit"
  echo "     access automatically."
  echo
  echo "ArcLink will use the page you paste below as its shared Notion home and"
  echo "create its verification scaffolding under it when needed."
  require_notion_subtree_ack
  if [[ -n "${ARCLINK_SSOT_NOTION_SPACE_URL:-}" ]]; then
    echo "Current shared Notion target:"
    echo "  ${ARCLINK_SSOT_NOTION_SPACE_URL}"
    if [[ -n "${ARCLINK_SSOT_NOTION_SPACE_KIND:-}" || -n "${ARCLINK_SSOT_NOTION_SPACE_ID:-}" ]]; then
      echo "  ${ARCLINK_SSOT_NOTION_SPACE_KIND:-object} ${ARCLINK_SSOT_NOTION_SPACE_ID:-}"
    fi
  else
    echo "No shared Notion SSOT target is configured yet."
  fi
  echo

  local notion_index_roots=""

  notion_space_url="$(normalize_optional_answer "$(ask "Shared Notion page URL for ArcLink (use a normal page, not the workspace Home screen) (ENTER keeps current, type none to clear)" "${ARCLINK_SSOT_NOTION_SPACE_URL:-}")")"
  notion_api_version="$(normalize_optional_answer "$(ask "Notion API version" "${ARCLINK_SSOT_NOTION_API_VERSION:-2026-03-11}")")"
  notion_api_version="${notion_api_version:-2026-03-11}"
  notion_token="$(ask_secret_with_default "Notion Internal Integration Secret for your ArcLink internal integration (start at https://www.notion.so/profile/integrations/internal) (ENTER keeps current, type none to clear)" "${ARCLINK_SSOT_NOTION_TOKEN:-}")"
  notion_public_webhook_url="${ARCLINK_NOTION_WEBHOOK_PUBLIC_URL:-}"

  if [[ -z "$notion_space_url" && -z "$notion_token" ]]; then
    ARCLINK_SSOT_NOTION_ROOT_PAGE_URL=""
    ARCLINK_SSOT_NOTION_ROOT_PAGE_ID=""
    ARCLINK_SSOT_NOTION_SPACE_URL=""
    ARCLINK_SSOT_NOTION_SPACE_ID=""
    ARCLINK_SSOT_NOTION_SPACE_KIND=""
    ARCLINK_SSOT_NOTION_API_VERSION="$notion_api_version"
    ARCLINK_SSOT_NOTION_TOKEN=""
    ARCLINK_NOTION_INDEX_ROOTS=""
    ARCLINK_NOTION_WEBHOOK_PUBLIC_URL=""
    write_runtime_config "$CONFIG_TARGET"
    if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
      chown "$ARCLINK_USER:$ARCLINK_USER" "$CONFIG_TARGET" >/dev/null 2>&1 || true
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
    ARCLINK_CONFIG_FILE="$CONFIG_TARGET" \
    "$BOOTSTRAP_DIR/bin/arclink-ctl" --json notion handshake \
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
    ARCLINK_CONFIG_FILE="$CONFIG_TARGET" \
    "$BOOTSTRAP_DIR/bin/arclink-ctl" --json notion preflight-root \
      --root-page-id "$root_page_id" \
      --token-file "$notion_token_file" \
      --api-version "$notion_api_version" >/dev/null; then
    rm -f "$handshake_file" "$notion_token_file"
    echo "Notion root preflight failed; leaving the current config unchanged." >&2
    exit 1
  fi

  local notion_index_roots_default="${ARCLINK_NOTION_INDEX_ROOTS:-$root_page_url}"
  if [[ "${ARCLINK_NOTION_MIGRATION_DEFAULT_INDEX_ROOT:-0}" == "1" ]]; then
    notion_index_roots_default="$root_page_url"
  fi
  notion_index_roots="$(normalize_optional_answer "$(ask "Shared Notion index roots (comma-separated page/database URLs or IDs; ENTER keeps current/default root)" "$notion_index_roots_default")")"
  notion_index_roots="${notion_index_roots:-$root_page_url}"

  ARCLINK_SSOT_NOTION_ROOT_PAGE_URL="$root_page_url"
  ARCLINK_SSOT_NOTION_ROOT_PAGE_ID="$root_page_id"
  ARCLINK_SSOT_NOTION_SPACE_URL="$notion_space_url"
  ARCLINK_SSOT_NOTION_SPACE_ID="$space_id"
  ARCLINK_SSOT_NOTION_SPACE_KIND="$space_kind"
  ARCLINK_SSOT_NOTION_API_VERSION="$notion_api_version"
  ARCLINK_SSOT_NOTION_TOKEN="$notion_token"
  ARCLINK_NOTION_INDEX_ROOTS="$notion_index_roots"
  ARCLINK_NOTION_WEBHOOK_PUBLIC_URL="$notion_public_webhook_url"
  write_runtime_config "$CONFIG_TARGET"
  rm -f "$handshake_file" "$notion_token_file"
  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    chown "$ARCLINK_USER:$ARCLINK_USER" "$CONFIG_TARGET" >/dev/null 2>&1 || true
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
  echo "  ${ARCLINK_NOTION_INDEX_ROOTS:-$root_page_url}"
  echo "Resolved URL:"
  echo "  ${target_url:-$notion_space_url}"
  if [[ -n "${ARCLINK_NOTION_WEBHOOK_PUBLIC_URL:-}" ]]; then
    echo "Webhook URL:"
    echo "  ${ARCLINK_NOTION_WEBHOOK_PUBLIC_URL}"
    echo "Webhook subscription checklist:"
    echo "  1. Open the Notion Developer Portal for this integration and go to Webhooks."
    echo "  2. If a subscription already exists for this exact URL, edit it instead of creating a duplicate:"
    echo "     ${ARCLINK_NOTION_WEBHOOK_PUBLIC_URL}"
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

  if [[ -n "${ARCLINK_NOTION_WEBHOOK_PUBLIC_URL:-}" ]]; then
    if [[ "${ARCLINK_NOTION_MIGRATION_FORCE_WEBHOOK_RESET:-0}" == "1" ]]; then
      echo
      echo "Migration mode: clearing the previous Notion webhook verification token before the new subscription handshake."
      if ! env ARCLINK_CONFIG_FILE="$CONFIG_TARGET" \
        "$BOOTSTRAP_DIR/bin/arclink-ctl" --json notion webhook-reset-token \
          --actor "${SUDO_USER:-$(id -un)}" --minutes 0 --force >/dev/null; then
        echo "Could not clear the previous Notion webhook token; leaving migration paused before webhook verification." >&2
        exit 1
      fi
    fi
    if ! run_notion_webhook_setup_flow "$BOOTSTRAP_DIR/bin/arclink-ctl" "${SUDO_USER:-$(id -un)}"; then
      rm -f "$handshake_file"
      echo "Shared Notion configuration was saved, but webhook verification is still incomplete." >&2
      exit 1
    fi
  fi

  rm -f "$handshake_file"
}

notion_migration_pause() {
  local prompt="${1:-Press ENTER to continue.}"
  if [[ -t 0 ]]; then
    read -r -p "$prompt " _
  fi
}

print_notion_migration_runbook() {
  cat <<'EOF'
Notion workspace migration guide

This flow moves ArcLink's shared Notion SSOT lane from one Notion workspace to
another. It does not copy Notion pages for you; create or import the new Notion
content first, then point ArcLink at the new shared root page.

The guided migration will:
  1. Show the current Notion config without revealing the integration secret.
  2. Create private backups under arclink-priv/state/migrations/.
  3. Drain pending Notion webhook events before the cutover when possible.
  4. Pause write/batcher surfaces while leaving the webhook receiver reachable.
  5. Re-run the Notion SSOT setup against the new workspace, including the
     internal integration checklist and webhook verification walkthrough.
  6. Archive old workspace-specific rows, then clear cached verification
     database IDs, identity claims, identity overrides, queued writes, webhook
     events, and generated notion-shared index rows/files.
  7. Run a full notion-shared index sync for the new workspace.
  8. Restart shared services and remind users to verify Notion again.

What you need before starting:
  - A normal Notion page in the new workspace for ArcLink to use as its root.
  - A new Notion internal integration secret from the new workspace.
  - Page access granted from that new integration to the ArcLink root subtree.
  - Access to the Notion Developer Portal Webhooks tab if webhooks are enabled.

Expected user impact:
  - Pending writes that target old Notion page/database IDs are archived and
    removed instead of replayed.
  - Users lose verified Notion write access until they re-run verification.
  - Historical SSOT audit rows remain as audit history, but operational caches
    are rebuilt against the new workspace.
EOF
}

choose_notion_migration_action() {
  local answer=""

  cat >&2 <<'EOF'
Notion workspace migration

  1) Read the migration guide
  2) Start guided migration
  3) Retry last migration index sync
  4) Exit
EOF

  while true; do
    read -r -p "Choose Notion migration action [1]: " answer
    case "${answer:-1}" in
      1) printf '%s\n' "read"; return 0 ;;
      2) printf '%s\n' "start"; return 0 ;;
      3) printf '%s\n' "retry-index"; return 0 ;;
      4) printf '%s\n' "exit"; return 0 ;;
      *) echo "Please choose 1 through 4." >&2 ;;
    esac
  done
}

notion_migration_backup_state() {
  local timestamp="" db_backup="" config_backup="" index_backup=""

  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  NOTION_MIGRATION_DIR="$STATE_DIR/migrations/notion-workspace-$timestamp"
  mkdir -p "$NOTION_MIGRATION_DIR"

  echo "Creating private migration backups:"
  echo "  $NOTION_MIGRATION_DIR"

  if [[ -f "$CONFIG_TARGET" ]]; then
    config_backup="$NOTION_MIGRATION_DIR/arclink.env.before"
    cp -p "$CONFIG_TARGET" "$config_backup"
    echo "  config: $config_backup"
  fi

  if [[ -f "$ARCLINK_DB_PATH" ]]; then
    db_backup="$NOTION_MIGRATION_DIR/arclink-control.sqlite3.before"
    python3 - "$ARCLINK_DB_PATH" "$db_backup" <<'PY'
import sqlite3
import sys

source, target = sys.argv[1], sys.argv[2]
src = sqlite3.connect(source)
dst = sqlite3.connect(target)
try:
    src.backup(dst)
finally:
    dst.close()
    src.close()
PY
    echo "  sqlite: $db_backup"
  else
    echo "  sqlite: skipped; DB not found at $ARCLINK_DB_PATH"
  fi

  if [[ -d "$STATE_DIR/notion-index" ]]; then
    index_backup="$NOTION_MIGRATION_DIR/notion-index.before.tar.gz"
    tar -C "$STATE_DIR" -czf "$index_backup" notion-index
    echo "  notion index cache: $index_backup"
  fi
}

notion_migration_pause_write_surfaces() {
  local uid=""

  echo
  echo "Pausing shared Notion write/batcher surfaces."
  echo "The Notion webhook receiver stays online so the new subscription can complete its verification handshake."

  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    systemctl stop arclink-notion-claim-poll.timer arclink-notion-claim-poll.service >/dev/null 2>&1 || true
    uid="$(id -u "$ARCLINK_USER" 2>/dev/null || true)"
    if [[ -n "$uid" ]]; then
      systemctl start "user@$uid.service" >/dev/null 2>&1 || true
      if [[ -S "/run/user/$uid/bus" ]]; then
        run_as_user_systemd "$ARCLINK_USER" "$uid" \
          "ARCLINK_CONFIG_FILE='$CONFIG_TARGET' systemctl --user stop arclink-mcp.service arclink-ssot-batcher.timer arclink-ssot-batcher.service >/dev/null 2>&1 || true" || true
      fi
    fi
    return 0
  fi

  if [[ "$(id -un)" == "$ARCLINK_USER" ]]; then
    if set_user_systemd_bus_env; then
      systemctl --user stop arclink-mcp.service arclink-ssot-batcher.timer arclink-ssot-batcher.service >/dev/null 2>&1 || true
    fi
  fi
}

notion_migration_restart_services() {
  local uid=""

  echo
  echo "Restarting shared ArcLink services."
  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    restart_shared_user_services_root || true
    systemctl restart arclink-notion-claim-poll.timer >/dev/null 2>&1 || true
    systemctl start arclink-notion-claim-poll.service >/dev/null 2>&1 || true
    return 0
  fi

  if [[ "$(id -un)" == "$ARCLINK_USER" ]]; then
    if set_user_systemd_bus_env; then
      systemctl --user daemon-reload
      systemctl --user restart arclink-mcp.service arclink-notion-webhook.service arclink-qmd-mcp.service arclink-qmd-update.timer arclink-vault-watch.service arclink-ssot-batcher.timer arclink-notification-delivery.timer arclink-health-watch.timer arclink-curator-refresh.timer arclink-memory-synth.timer || true
      systemctl --user start arclink-curator-refresh.service >/dev/null 2>&1 || true
      systemctl --user start arclink-memory-synth.service >/dev/null 2>&1 || true
      systemctl --user start arclink-health-watch.service >/dev/null 2>&1 || true
    fi
    return 0
  fi

  uid="$(id -u "$ARCLINK_USER" 2>/dev/null || true)"
  if [[ -n "$uid" && -S "/run/user/$uid/bus" ]]; then
    run_as_user_systemd "$ARCLINK_USER" "$uid" \
      "ARCLINK_CONFIG_FILE='$CONFIG_TARGET' systemctl --user restart arclink-mcp.service arclink-notion-webhook.service arclink-ssot-batcher.timer >/dev/null 2>&1 || true" || true
  fi
}

notion_migration_restore_paused_services() {
  if [[ "${NOTION_MIGRATION_SERVICES_PAUSED:-0}" == "1" ]]; then
    NOTION_MIGRATION_SERVICES_PAUSED=0
    notion_migration_restart_services || true
  fi
}

notion_migration_repair_state_ownership() {
  if [[ ${EUID:-$(id -u)} -ne 0 || "${ARCLINK_DOCKER_MODE:-0}" == "1" ]]; then
    return 0
  fi
  chown -R "$ARCLINK_USER:$ARCLINK_USER" "$STATE_DIR/notion-index" "$NOTION_MIGRATION_DIR" >/dev/null 2>&1 || true
  chown "$ARCLINK_USER:$ARCLINK_USER" "$ARCLINK_DB_PATH" "$ARCLINK_DB_PATH"-* >/dev/null 2>&1 || true
}

run_notion_migration_index_sync() {
  local actor="$1"
  local ctl_bin="$ARCLINK_REPO_DIR/bin/arclink-ctl"

  if [[ "${ARCLINK_DOCKER_MODE:-0}" == "1" || "$(id -un)" == "$ARCLINK_USER" ]]; then
    env ARCLINK_CONFIG_FILE="$CONFIG_TARGET" "$ctl_bin" --json notion index-sync --full --actor "$actor"
    return $?
  fi

  run_service_user_cmd "$ctl_bin" --json notion index-sync --full --actor "$actor"
}

latest_notion_migration_dir() {
  local dir="" latest=""

  if [[ ! -d "$STATE_DIR/migrations" ]]; then
    return 1
  fi
  for dir in "$STATE_DIR"/migrations/notion-workspace-*; do
    if [[ -d "$dir" ]]; then
      latest="$dir"
    fi
  done
  if [[ -z "$latest" ]]; then
    return 1
  fi
  printf '%s\n' "$latest"
}

run_notion_migration_retry_index_sync() {
  local actor="$1"

  if ! NOTION_MIGRATION_DIR="$(latest_notion_migration_dir)"; then
    echo "No previous Notion workspace migration directory found under $STATE_DIR/migrations." >&2
    return 1
  fi

  echo
  echo "Retrying full Notion index sync for the latest migration:"
  echo "  $NOTION_MIGRATION_DIR"
  notion_migration_repair_state_ownership
  if ! run_notion_migration_index_sync "$actor" >"$NOTION_MIGRATION_DIR/notion-index-sync.json"; then
    echo "Notion index sync failed; details may be in $NOTION_MIGRATION_DIR/notion-index-sync.json" >&2
    notion_migration_restart_services
    return 1
  fi
  echo "Notion index sync result: $NOTION_MIGRATION_DIR/notion-index-sync.json"
  notion_migration_restart_services
}

notion_migration_clear_workspace_state() {
  if [[ ! -f "$ARCLINK_DB_PATH" ]]; then
    echo "Skipping DB state cleanup; DB not found at $ARCLINK_DB_PATH"
    return 0
  fi

  python3 - "$ARCLINK_DB_PATH" "$STATE_DIR" "$NOTION_MIGRATION_DIR" <<'PY'
import datetime as dt
import json
import shutil
import sqlite3
import sys
from pathlib import Path

db_path = Path(sys.argv[1])
state_dir = Path(sys.argv[2])
migration_dir = Path(sys.argv[3])
archive_path = migration_dir / "notion-workspace-state-archive.json"
now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row


def table_exists(name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone() is not None


def rows(name: str, where: str = "", params: tuple = ()) -> list[dict]:
    if not table_exists(name):
        return []
    sql = f"SELECT * FROM {name}"
    if where:
        sql += f" WHERE {where}"
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


archive = {
    "archived_at": now,
    "reason": "notion workspace migration",
    "tables": {
        "settings": rows("settings", "key LIKE 'notion_verification_database%'"),
        "agent_identity": rows("agent_identity"),
        "notion_identity_claims": rows("notion_identity_claims"),
        "notion_identity_overrides": rows("notion_identity_overrides"),
        "notion_webhook_events": rows("notion_webhook_events"),
        "ssot_pending_writes": rows("ssot_pending_writes"),
        "notion_index_documents": rows("notion_index_documents"),
    },
}
migration_dir.mkdir(parents=True, exist_ok=True)
archive_path.write_text(json.dumps(archive, indent=2, sort_keys=True) + "\n", encoding="utf-8")

counts: dict[str, int] = {}
with conn:
    if table_exists("settings"):
        counts["settings_verification_database"] = conn.execute(
            "DELETE FROM settings WHERE key LIKE 'notion_verification_database%'"
        ).rowcount
    if table_exists("agent_identity"):
        counts["agent_identity_reset"] = conn.execute(
            """
            UPDATE agent_identity
            SET claimed_notion_email = '',
                notion_user_id = '',
                notion_user_email = '',
                verification_status = 'unverified',
                write_mode = 'read_only',
                verified_at = NULL,
                verification_source = 'notion-workspace-migration',
                updated_at = ?
            """,
            (now,),
        ).rowcount
    for table in (
        "notion_identity_claims",
        "notion_identity_overrides",
        "notion_webhook_events",
        "ssot_pending_writes",
        "notion_index_documents",
    ):
        if table_exists(table):
            counts[table] = conn.execute(f"DELETE FROM {table}").rowcount

markdown_dir = state_dir / "notion-index" / "markdown"
removed_markdown = markdown_dir.exists()
if removed_markdown:
    shutil.rmtree(markdown_dir)
markdown_dir.mkdir(parents=True, exist_ok=True)

print(f"archive={archive_path}")
for key in sorted(counts):
    print(f"{key}={counts[key]}")
print(f"notion_index_markdown_reset={1 if removed_markdown else 0}")
PY
}

run_notion_migrate_flow() {
  local reexec_status="" action="" answer="" actor="" index_rc=0 setup_rc=0
  local old_notion_space_url="" old_notion_space_id="" old_notion_root_page_id=""

  prepare_deployed_context
  if maybe_reexec_with_sudo_for_config notion-migrate; then
    return 0
  else
    reexec_status="$?"
    if [[ "${ARCLINK_REEXEC_ATTEMPTED:-0}" == "1" ]]; then
      return "$reexec_status"
    fi
  fi
  ensure_deployed_config_exists
  reload_runtime_config_from_file "$CONFIG_TARGET" || true

  if [[ ${EUID:-$(id -u)} -ne 0 && "$(id -un)" != "$ARCLINK_USER" ]]; then
    echo "Switching to sudo for Notion workspace migration..."
    sudo_deploy ARCLINK_CONFIG_FILE="$CONFIG_TARGET" "${DEPLOY_EXEC_PATH:-$SELF_PATH}" notion-migrate
    write_operator_checkout_artifact
    return 0
  fi

  if [[ ! -t 0 ]]; then
    print_notion_migration_runbook
    echo
    echo "Notion workspace migration is intentionally interactive; rerun with a terminal." >&2
    return 1
  fi

  echo "ArcLink deploy: Notion workspace migration"
  echo
  echo "Current deployment:"
  echo "  config:          $CONFIG_TARGET"
  echo "  db:              $ARCLINK_DB_PATH"
  echo "  current root:    ${ARCLINK_SSOT_NOTION_ROOT_PAGE_URL:-not configured}"
  echo "  current target:  ${ARCLINK_SSOT_NOTION_SPACE_URL:-not configured}"
  echo "  current index:   ${ARCLINK_NOTION_INDEX_ROOTS:-${ARCLINK_SSOT_NOTION_ROOT_PAGE_URL:-not configured}}"
  echo "  webhook URL:     ${ARCLINK_NOTION_WEBHOOK_PUBLIC_URL:-not configured}"
  if [[ -n "${ARCLINK_SSOT_NOTION_TOKEN:-}" ]]; then
    echo "  Notion token:    configured ($(mask_secret "$ARCLINK_SSOT_NOTION_TOKEN"))"
  else
    echo "  Notion token:    not configured"
  fi
  echo

  actor="${SUDO_USER:-$(id -un)}"
  old_notion_space_url="${ARCLINK_SSOT_NOTION_SPACE_URL:-}"
  old_notion_space_id="${ARCLINK_SSOT_NOTION_SPACE_ID:-}"
  old_notion_root_page_id="${ARCLINK_SSOT_NOTION_ROOT_PAGE_ID:-}"

  action="$(choose_notion_migration_action)"
  case "$action" in
    read)
      echo
      print_notion_migration_runbook
      return 0
      ;;
    exit)
      return 0
      ;;
    retry-index)
      run_notion_migration_retry_index_sync "$actor"
      return $?
      ;;
  esac

  print_notion_migration_runbook
  echo
  echo "This will change live Notion configuration and clear old workspace-specific operational state."
  while true; do
    read -r -p "Type MIGRATE NOTION to continue: " answer
    if [[ "$answer" == "MIGRATE NOTION" ]]; then
      break
    fi
    echo "Please type MIGRATE NOTION exactly, or press Ctrl-C to abort."
  done

  notion_migration_backup_state
  notion_migration_pause "Press ENTER after you have confirmed the backup paths above."

  if [[ "$(ask_yes_no "Drain pending Notion webhook events before the cutover" "1")" == "1" ]]; then
    echo "Draining pending Notion webhook events..."
    if ! env ARCLINK_CONFIG_FILE="$CONFIG_TARGET" "$BOOTSTRAP_DIR/bin/arclink-ctl" --json notion process-pending; then
      echo "Pending Notion event processing failed." >&2
      if [[ "$(ask_yes_no "Continue migration anyway" "0")" != "1" ]]; then
        return 1
      fi
    fi
  fi

  NOTION_MIGRATION_SERVICES_PAUSED=0
  trap notion_migration_restore_paused_services EXIT
  trap 'notion_migration_restore_paused_services; exit 130' INT TERM

  notion_migration_pause_write_surfaces
  NOTION_MIGRATION_SERVICES_PAUSED=1

  echo
  echo "Starting the new workspace SSOT setup."
  echo "Old Notion URL and token values will not be offered as defaults; paste the new workspace page URL and new integration secret."
  if (
    ARCLINK_NOTION_MIGRATION_FRESH_DEFAULTS=1
    ARCLINK_NOTION_MIGRATION_DEFAULT_INDEX_ROOT=1
    ARCLINK_NOTION_MIGRATION_FORCE_WEBHOOK_RESET=1
    run_notion_ssot_setup
  ); then
    setup_rc=0
  else
    setup_rc=$?
    reload_runtime_config_from_file "$CONFIG_TARGET" || true
    if [[ -n "${ARCLINK_SSOT_NOTION_SPACE_URL:-}${ARCLINK_SSOT_NOTION_SPACE_ID:-}" ]] &&
      [[ "${ARCLINK_SSOT_NOTION_SPACE_URL:-}" != "$old_notion_space_url" ||
         "${ARCLINK_SSOT_NOTION_SPACE_ID:-}" != "$old_notion_space_id" ||
         "${ARCLINK_SSOT_NOTION_ROOT_PAGE_ID:-}" != "$old_notion_root_page_id" ]]; then
      echo "New Notion configuration was saved before setup stopped." >&2
      echo "Continuing workspace-state cleanup so old Notion identities and queued writes cannot be used against the new workspace." >&2
      index_rc=1
    else
      echo "New Notion SSOT setup failed before a new workspace config was saved; restarting services and leaving the migration backup intact." >&2
      notion_migration_restore_paused_services
      trap - EXIT
      trap - INT TERM
      return "$setup_rc"
    fi
  fi
  reload_runtime_config_from_file "$CONFIG_TARGET" || true

  if [[ -z "${ARCLINK_NOTION_WEBHOOK_PUBLIC_URL:-}" ]]; then
    echo
    echo "No Notion webhook public URL is configured; clearing any stored webhook verification token from the old workspace."
    env ARCLINK_CONFIG_FILE="$CONFIG_TARGET" "$BOOTSTRAP_DIR/bin/arclink-ctl" --json notion webhook-reset-token \
      --actor "$actor" --minutes 0 --force >/dev/null || true
  fi

  echo
  echo "Clearing old workspace-specific ArcLink state."
  notion_migration_clear_workspace_state
  notion_migration_repair_state_ownership

  if [[ "$(ask_yes_no "Run a full notion-shared index sync for the new workspace now" "1")" == "1" ]]; then
    echo "Running full Notion index sync. This can take a while on large workspaces..."
    if ! run_notion_migration_index_sync "$actor" >"$NOTION_MIGRATION_DIR/notion-index-sync.json"; then
      index_rc=1
      echo "Notion index sync failed; details may be in $NOTION_MIGRATION_DIR/notion-index-sync.json" >&2
    else
      echo "Notion index sync result: $NOTION_MIGRATION_DIR/notion-index-sync.json"
    fi
  else
    echo "Skipped full Notion index sync. Run this later:"
    echo "  ./bin/arclink-ctl notion index-sync --full"
  fi

  notion_migration_restart_services
  NOTION_MIGRATION_SERVICES_PAUSED=0
  trap - EXIT
  trap - INT TERM

  echo
  echo "Notion workspace migration guide complete."
  echo "Backups and archived old workspace state:"
  echo "  $NOTION_MIGRATION_DIR"
  echo "Users must re-run Notion identity verification before shared Notion writes are enabled again."
  echo "Run a final health check when ready:"
  echo "  ./deploy.sh health"

  return "$index_rc"
}

notion_transfer_prepare_context() {
  ARCLINK_REPO_DIR="${ARCLINK_REPO_DIR:-$BOOTSTRAP_DIR}"
  ARCLINK_PRIV_DIR="${ARCLINK_PRIV_DIR:-$ARCLINK_REPO_DIR/arclink-priv}"
  STATE_DIR="${STATE_DIR:-$ARCLINK_PRIV_DIR/state}"
  NOTION_TRANSFER_DIR="${ARCLINK_NOTION_TRANSFER_DIR:-$STATE_DIR/notion-transfer}"
  NOTION_TRANSFER_TOOL="$BOOTSTRAP_DIR/bin/notion-transfer.py"
  mkdir -p "$NOTION_TRANSFER_DIR/backups"
  chmod 700 "$NOTION_TRANSFER_DIR" "$NOTION_TRANSFER_DIR/backups" >/dev/null 2>&1 || true
}

print_notion_transfer_runbook() {
  cat <<'EOF'
Notion page backup / restore guide

This flow backs up one Notion page subtree and can restore it under a page in
another Notion workspace. It is generic: the source can be any normal Notion
page the source integration can read, and the destination can be any normal
page the destination integration can create children under.

Important access model:
  - Notion integration tokens do not grant broad teamspace export access.
  - Share the source root page/subtree with the source integration.
  - Share the destination parent/root page with the destination integration.
  - This creates a new child page under the destination parent. It does not
    overwrite, delete, or merge into existing destination pages.

Expected fidelity:
  - Pages, nested pages, child databases, database rows, text-like blocks,
    external media links, covers, icons, and common properties are restored.
  - Uploaded Notion-hosted files are referenced as skipped placeholders unless
    they were external URLs.
  - Relations/rollups/formulas/people are not automatically rewired across
    workspaces.
  - Unsupported blocks are preserved as visible placeholder notes so missing
    content is obvious.

Secrets:
  - Keep Notion tokens in private token files, for example
    arclink-priv/state/notion-transfer/source.token and dest.token.
  - The tool never accepts tokens on argv.
EOF
}

choose_notion_transfer_action() {
  local answer=""

  cat >&2 <<'EOF'
Notion page backup / restore

  1) Read the backup / restore guide
  2) Discover token access
  3) Back up a source root page
  4) Restore a backup to a destination parent page
  5) Back up then restore
  6) Exit
EOF

  while true; do
    read -r -p "Choose Notion transfer action [1]: " answer
    case "${answer:-1}" in
      1) printf '%s\n' "read"; return 0 ;;
      2) printf '%s\n' "discover"; return 0 ;;
      3) printf '%s\n' "backup"; return 0 ;;
      4) printf '%s\n' "restore"; return 0 ;;
      5) printf '%s\n' "backup-restore"; return 0 ;;
      6) printf '%s\n' "exit"; return 0 ;;
      *) echo "Please choose 1 through 6." >&2 ;;
    esac
  done
}

notion_transfer_prompt_required() {
  local prompt="$1"
  local default="${2:-}"
  local answer=""

  while true; do
    answer="$(ask "$prompt" "$default")"
    if [[ -n "$answer" ]]; then
      printf '%s\n' "$answer"
      return 0
    fi
    echo "This value is required." >&2
  done
}

notion_transfer_prompt_token_file() {
  local prompt="$1"
  local default="$2"
  local answer=""

  while true; do
    answer="$(notion_transfer_prompt_required "$prompt" "$default")"
    if [[ -r "$answer" ]]; then
      printf '%s\n' "$answer"
      return 0
    fi
    echo "Token file is not readable: $answer" >&2
  done
}

latest_notion_transfer_backup_dir() {
  if [[ ! -d "$NOTION_TRANSFER_DIR/backups" ]]; then
    return 1
  fi
  find "$NOTION_TRANSFER_DIR/backups" -mindepth 1 -maxdepth 1 -type d -print 2>/dev/null | sort | tail -n 1
}

notion_transfer_discover() {
  local token_file="" label=""

  token_file="$(notion_transfer_prompt_token_file "Notion token file" "$NOTION_TRANSFER_DIR/source.token")"
  label="$(notion_transfer_prompt_required "Label for this token" "source")"
  python3 "$NOTION_TRANSFER_TOOL" discover \
    --token-file "$token_file" \
    --label "$label"
}

notion_transfer_backup() {
  local token_file="" source_root="" output_dir="" timestamp="" default_source_root=""

  token_file="$(notion_transfer_prompt_token_file "Source Notion token file" "$NOTION_TRANSFER_DIR/source.token")"
  default_source_root="${ARCLINK_SSOT_NOTION_ROOT_PAGE_URL:-${ARCLINK_SSOT_NOTION_SPACE_URL:-}}"
  source_root="$(notion_transfer_prompt_required "Source root page URL or ID to back up" "$default_source_root")"
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  output_dir="$(notion_transfer_prompt_required "Backup output directory" "$NOTION_TRANSFER_DIR/backups/$timestamp")"

  python3 "$NOTION_TRANSFER_TOOL" backup \
    --source-token-file "$token_file" \
    --source-root "$source_root" \
    --output-dir "$output_dir"
  NOTION_TRANSFER_LAST_BACKUP_DIR="$output_dir"
}

notion_transfer_restore() {
  local backup_dir="${1:-}" latest_backup="" token_file="" dest_parent="" title="" confirm=""

  if [[ -z "$backup_dir" ]]; then
    latest_backup="$(latest_notion_transfer_backup_dir || true)"
    backup_dir="$(notion_transfer_prompt_required "Backup directory" "$latest_backup")"
  fi
  if [[ ! -f "$backup_dir/backup.json" ]]; then
    echo "Backup directory does not contain backup.json: $backup_dir" >&2
    return 1
  fi

  token_file="$(notion_transfer_prompt_token_file "Destination Notion token file" "$NOTION_TRANSFER_DIR/dest.token")"
  dest_parent="$(notion_transfer_prompt_required "Destination parent/root page URL or ID" "${ARCLINK_SSOT_NOTION_ROOT_PAGE_URL:-}")"
  title="$(ask "Title for the restored root page (ENTER keeps source title)" "")"

  echo
  echo "Running restore dry-run first. This verifies destination page access and reports the planned writes."
  python3 "$NOTION_TRANSFER_TOOL" restore \
    --dest-token-file "$token_file" \
    --backup-dir "$backup_dir" \
    --dest-parent "$dest_parent" \
    --title "$title" \
    --dry-run

  echo
  echo "The dry-run wrote: $backup_dir/restore-dry-run.json"
  echo "No Notion pages have been created yet."
  while true; do
    read -r -p "Type RESTORE NOTION to create the destination copy, or press Ctrl-C to abort: " confirm
    if [[ "$confirm" == "RESTORE NOTION" ]]; then
      break
    fi
    echo "Please type RESTORE NOTION exactly, or press Ctrl-C to abort."
  done

  python3 "$NOTION_TRANSFER_TOOL" restore \
    --dest-token-file "$token_file" \
    --backup-dir "$backup_dir" \
    --dest-parent "$dest_parent" \
    --title "$title"
  echo
  echo "Restore result: $backup_dir/restore-result.json"
}

run_notion_transfer_flow() {
  local action=""

  notion_transfer_prepare_context
  if [[ ! -x "$NOTION_TRANSFER_TOOL" && ! -f "$NOTION_TRANSFER_TOOL" ]]; then
    echo "Notion transfer tool is missing: $NOTION_TRANSFER_TOOL" >&2
    return 1
  fi
  if [[ ! -t 0 ]]; then
    print_notion_transfer_runbook
    echo
    echo "Notion page backup / restore is intentionally interactive; rerun with a terminal." >&2
    echo "Automation can call bin/notion-transfer.py directly with token files." >&2
    return 1
  fi

  echo "ArcLink deploy: Notion page backup / restore"
  echo
  echo "Private working directory:"
  echo "  $NOTION_TRANSFER_DIR"
  echo "Token file defaults:"
  echo "  source: $NOTION_TRANSFER_DIR/source.token"
  echo "  dest:   $NOTION_TRANSFER_DIR/dest.token"
  echo

  action="$(choose_notion_transfer_action)"
  case "$action" in
    read)
      echo
      print_notion_transfer_runbook
      ;;
    discover)
      notion_transfer_discover
      ;;
    backup)
      notion_transfer_backup
      ;;
    restore)
      notion_transfer_restore
      ;;
    backup-restore)
      notion_transfer_backup
      notion_transfer_restore "$NOTION_TRANSFER_LAST_BACKUP_DIR"
      ;;
    exit)
      return 0
      ;;
  esac
}

run_curator_setup_flow() {
  prepare_deployed_context

  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    env ARCLINK_CONFIG_FILE="$CONFIG_TARGET" "$ARCLINK_REPO_DIR/bin/install-system-services.sh"
    run_as_user "$ARCLINK_USER" "env ARCLINK_CONFIG_FILE='$CONFIG_TARGET' ARCLINK_ALLOW_NO_USER_BUS='${ARCLINK_ALLOW_NO_USER_BUS:-0}' '$ARCLINK_REPO_DIR/bin/install-user-services.sh'"
    run_as_user "$ARCLINK_USER" "env $(curator_bootstrap_env_prefix) '$ARCLINK_REPO_DIR/bin/bootstrap-curator.sh'"
    reload_runtime_config_from_file "$CONFIG_TARGET" || true
    restart_shared_user_services_root
    return 0
  fi

  if [[ "$(id -un)" == "$ARCLINK_USER" ]]; then
    env ARCLINK_CONFIG_FILE="$CONFIG_TARGET" ARCLINK_ALLOW_NO_USER_BUS="${ARCLINK_ALLOW_NO_USER_BUS:-0}" "$ARCLINK_REPO_DIR/bin/install-user-services.sh"
    env $(curator_bootstrap_env_prefix) "$ARCLINK_REPO_DIR/bin/bootstrap-curator.sh"
    reload_runtime_config_from_file "$CONFIG_TARGET" || true
    if set_user_systemd_bus_env; then
      systemctl --user daemon-reload
      systemctl --user restart arclink-mcp.service arclink-notion-webhook.service arclink-qmd-mcp.service arclink-qmd-update.timer arclink-vault-watch.service arclink-github-backup.timer arclink-ssot-batcher.timer arclink-notification-delivery.timer arclink-health-watch.timer arclink-curator-refresh.timer arclink-memory-synth.timer
      systemctl --user start arclink-curator-refresh.service >/dev/null 2>&1 || true
      systemctl --user start arclink-memory-synth.service >/dev/null 2>&1 || true
      systemctl --user start arclink-health-watch.service >/dev/null 2>&1 || true
      if [[ "$PDF_INGEST_ENABLED" == "1" ]]; then
        systemctl --user restart arclink-pdf-ingest.timer
        systemctl --user stop arclink-pdf-ingest-watch.service >/dev/null 2>&1 || true
      fi
      if [[ "$ENABLE_QUARTO" == "1" ]]; then
        systemctl --user restart arclink-quarto-render.timer
      fi
      if [[ "$ENABLE_NEXTCLOUD" == "1" ]]; then
        systemctl --user restart arclink-nextcloud.service
      fi
      if [[ "${ARCLINK_CURATOR_TELEGRAM_ONBOARDING_ENABLED:-0}" == "1" ]]; then
        systemctl --user restart arclink-curator-onboarding.service >/dev/null 2>&1 || true
      fi
      if [[ "${ARCLINK_CURATOR_DISCORD_ONBOARDING_ENABLED:-0}" == "1" ]]; then
        systemctl --user restart arclink-curator-discord-onboarding.service >/dev/null 2>&1 || true
      fi
      if [[ "${ARCLINK_CURATOR_CHANNELS:-tui-only}" == *discord* || "${ARCLINK_CURATOR_CHANNELS:-tui-only}" == *telegram* ]]; then
        systemctl --user restart arclink-curator-gateway.service >/dev/null 2>&1 || true
      fi
    fi
    return 0
  fi

  sudo env \
    ARCLINK_USER="$ARCLINK_USER" \
    ARCLINK_HOME="$ARCLINK_HOME" \
    ARCLINK_REPO_DIR="$ARCLINK_REPO_DIR" \
    ARCLINK_PRIV_DIR="$ARCLINK_PRIV_DIR" \
    ARCLINK_PRIV_CONFIG_DIR="$ARCLINK_PRIV_CONFIG_DIR" \
    ARCLINK_CONFIG_FILE="$CONFIG_TARGET" \
    ARCLINK_ALLOW_NO_USER_BUS="${ARCLINK_ALLOW_NO_USER_BUS:-0}" \
    ARCLINK_CURATOR_SKIP_HERMES_SETUP="${ARCLINK_CURATOR_SKIP_HERMES_SETUP:-}" \
    ARCLINK_CURATOR_SKIP_GATEWAY_SETUP="${ARCLINK_CURATOR_SKIP_GATEWAY_SETUP:-}" \
    ARCLINK_CURATOR_FORCE_HERMES_SETUP="${ARCLINK_CURATOR_FORCE_HERMES_SETUP:-}" \
    ARCLINK_CURATOR_FORCE_GATEWAY_SETUP="${ARCLINK_CURATOR_FORCE_GATEWAY_SETUP:-}" \
    ARCLINK_CURATOR_FORCE_CHANNEL_RECONFIGURE="${ARCLINK_CURATOR_FORCE_CHANNEL_RECONFIGURE:-}" \
    ARCLINK_CURATOR_NOTIFY_PLATFORM="${ARCLINK_CURATOR_NOTIFY_PLATFORM:-}" \
    ARCLINK_CURATOR_NOTIFY_CHANNEL_ID="${ARCLINK_CURATOR_NOTIFY_CHANNEL_ID:-}" \
    ARCLINK_CURATOR_GENERAL_PLATFORM="${ARCLINK_CURATOR_GENERAL_PLATFORM:-}" \
    ARCLINK_CURATOR_GENERAL_CHANNEL_ID="${ARCLINK_CURATOR_GENERAL_CHANNEL_ID:-}" \
    ARCLINK_CURATOR_MODEL_PRESET="${ARCLINK_CURATOR_MODEL_PRESET:-}" \
    ARCLINK_CURATOR_CHANNELS="${ARCLINK_CURATOR_CHANNELS:-}" \
    TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}" \
    "$BOOTSTRAP_DIR/deploy.sh" curator-setup
  write_operator_checkout_artifact
}

run_upgrade_flow() {
  require_supported_host_mode "upgrade"
  prepare_deployed_context

  if [[ ${EUID:-$(id -u)} -ne 0 && -n "${CONFIG_TARGET:-}" && ! -r "$CONFIG_TARGET" ]]; then
    echo "Switching to sudo to inspect the deployed config..."
    if ! sudo_deploy \
      ARCLINK_CONFIG_FILE="$CONFIG_TARGET" \
      ARCLINK_UPSTREAM_REPO_URL="${ARCLINK_UPSTREAM_REPO_URL:-}" \
      ARCLINK_UPSTREAM_BRANCH="${ARCLINK_UPSTREAM_BRANCH:-}" \
      ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED="${ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED:-}" \
      ARCLINK_UPSTREAM_DEPLOY_KEY_USER="${ARCLINK_UPSTREAM_DEPLOY_KEY_USER:-}" \
      ARCLINK_UPSTREAM_DEPLOY_KEY_PATH="${ARCLINK_UPSTREAM_DEPLOY_KEY_PATH:-}" \
      ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE="${ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE:-}" \
      "${DEPLOY_EXEC_PATH:-$SELF_PATH}" --apply-upgrade; then
      return 1
    fi
    write_operator_checkout_artifact
    return 0
  fi

  if [[ ! -f "$CONFIG_TARGET" ]]; then
    echo "ArcLink upgrade needs an existing deployed config. Expected: $CONFIG_TARGET" >&2
    echo "Run ./deploy.sh install first, or point ARCLINK_CONFIG_FILE at the deployed arclink.env." >&2
    exit 1
  fi

  echo "ArcLink deploy: upgrade from configured upstream"
  echo
  echo "Config:   $CONFIG_TARGET"
  echo "Upstream: ${ARCLINK_UPSTREAM_REPO_URL:-$(canonical_arclink_upstream_repo_url)}#${ARCLINK_UPSTREAM_BRANCH:-arclink}"
  echo "Target:   $ARCLINK_REPO_DIR"

  require_main_upstream_branch_for_upgrade

  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    run_root_upgrade
    return 0
  fi

  echo
  echo "Switching to sudo for upgrade..."
  if ! sudo_deploy \
    ARCLINK_CONFIG_FILE="$CONFIG_TARGET" \
    ARCLINK_UPSTREAM_REPO_URL="${ARCLINK_UPSTREAM_REPO_URL:-}" \
    ARCLINK_UPSTREAM_BRANCH="${ARCLINK_UPSTREAM_BRANCH:-}" \
    ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED="${ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED:-}" \
    ARCLINK_UPSTREAM_DEPLOY_KEY_USER="${ARCLINK_UPSTREAM_DEPLOY_KEY_USER:-}" \
    ARCLINK_UPSTREAM_DEPLOY_KEY_PATH="${ARCLINK_UPSTREAM_DEPLOY_KEY_PATH:-}" \
    ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE="${ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE:-}" \
    "${DEPLOY_EXEC_PATH:-$SELF_PATH}" --apply-upgrade; then
    return 1
  fi
  write_operator_checkout_artifact
}

run_agent_payload() {
  load_detected_config || true

  ARCLINK_USER="${ARCLINK_USER:-arclink}"
  ARCLINK_HOME="${ARCLINK_HOME:-$(default_home_for_user "$ARCLINK_USER")}"
  ARCLINK_REPO_DIR="${ARCLINK_REPO_DIR:-$BOOTSTRAP_DIR}"
  ARCLINK_PRIV_DIR="${ARCLINK_PRIV_DIR:-$ARCLINK_REPO_DIR/arclink-priv}"
  ARCLINK_PRIV_CONFIG_DIR="${ARCLINK_PRIV_CONFIG_DIR:-$ARCLINK_PRIV_DIR/config}"
  STATE_DIR="${STATE_DIR:-$ARCLINK_PRIV_DIR/state}"
  QMD_COLLECTION_NAME="${QMD_COLLECTION_NAME:-vault}"
  QMD_MCP_PORT="${QMD_MCP_PORT:-8181}"
  NEXTCLOUD_TRUSTED_DOMAIN="${NEXTCLOUD_TRUSTED_DOMAIN:-arclink.your-tailnet.ts.net}"
  ENABLE_TAILSCALE_SERVE="${ENABLE_TAILSCALE_SERVE:-0}"
  TAILSCALE_QMD_PATH="${TAILSCALE_QMD_PATH:-/mcp}"
  TAILSCALE_ARCLINK_MCP_PATH="${TAILSCALE_ARCLINK_MCP_PATH:-/arclink-mcp}"

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
    docker-notion-migrate) printf '%s\n' "notion-migrate" ;;
    docker-notion-transfer) printf '%s\n' "notion-transfer" ;;
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

run_arclink_docker() {
  local helper="$BOOTSTRAP_DIR/bin/arclink-docker.sh"

  if [[ ! -x "$helper" ]]; then
    echo "Docker helper is missing or not executable: $helper" >&2
    return 1
  fi

  "$helper" "$@"
}

docker_env_file_path() {
  printf '%s\n' "$BOOTSTRAP_DIR/arclink-priv/config/docker.env"
}

load_docker_runtime_config() {
  local docker_env=""

  docker_env="$(docker_env_file_path)"
  if [[ -f "$docker_env" && -r "$docker_env" ]]; then
    # shellcheck disable=SC1090
    source "$docker_env"
    VAULT_QMD_COLLECTION_MASK="$(normalize_vault_qmd_collection_mask "${VAULT_QMD_COLLECTION_MASK:-}")"
    resolve_model_provider_presets
  fi
}

docker_nextcloud_state_has_existing_data() {
  local host_nextcloud_state="$BOOTSTRAP_DIR/arclink-priv/state/nextcloud"

  if [[ ! -d "$host_nextcloud_state" ]]; then
    return 1
  fi

  find "$host_nextcloud_state" -mindepth 1 -print -quit 2>/dev/null | grep -q .
}

write_docker_runtime_config() {
  local target="${1:-$(docker_env_file_path)}"
  local container_repo_dir="/home/arclink/arclink"
  local container_priv_dir="/home/arclink/arclink/arclink-priv"
  local container_state_dir="$container_priv_dir/state"
  local container_runtime_dir="/opt/arclink/runtime"

  ARCLINK_NAME="arclink"
  ARCLINK_USER="arclink"
  ARCLINK_HOME="/home/arclink"
  ARCLINK_REPO_DIR="$container_repo_dir"
  ARCLINK_PRIV_DIR="$container_priv_dir"
  ARCLINK_PRIV_CONFIG_DIR="$container_priv_dir/config"
  VAULT_DIR="$container_priv_dir/vault"
  STATE_DIR="$container_state_dir"
  NEXTCLOUD_STATE_DIR="$container_state_dir/nextcloud"
  RUNTIME_DIR="$container_runtime_dir"
  PUBLISHED_DIR="$container_priv_dir/published"
  QUARTO_PROJECT_DIR="$container_priv_dir/quarto"
  QUARTO_OUTPUT_DIR="$container_priv_dir/published"
  ARCLINK_RELEASE_STATE_FILE="${ARCLINK_RELEASE_STATE_FILE:-$container_state_dir/arclink-release.json}"
  ARCLINK_MCP_HOST="0.0.0.0"
  ARCLINK_NOTION_WEBHOOK_HOST="0.0.0.0"
  BACKUP_GIT_DEPLOY_KEY_PATH="${BACKUP_GIT_DEPLOY_KEY_PATH:-$container_priv_dir/secrets/arclink-backup-ed25519}"
  BACKUP_GIT_KNOWN_HOSTS_FILE="${BACKUP_GIT_KNOWN_HOSTS_FILE:-$container_priv_dir/secrets/arclink-backup-known_hosts}"

  mkdir -p "$(dirname "$target")"
  {
    emit_runtime_config
    write_kv ARCLINK_BACKEND_ALLOWED_CIDRS "${ARCLINK_BACKEND_ALLOWED_CIDRS:-172.16.0.0/12}"
    write_kv ARCLINK_MCP_URL "http://arclink-mcp:8282/mcp"
    write_kv ARCLINK_BOOTSTRAP_URL "http://arclink-mcp:8282/mcp"
    write_kv ARCLINK_QMD_URL "http://qmd-mcp:8181/mcp"
    write_kv ARCLINK_NOTION_INDEX_DIR "$container_state_dir/notion-index"
    write_kv ARCLINK_NOTION_INDEX_MARKDOWN_DIR "$container_state_dir/notion-index/markdown"
    write_kv ARCLINK_DOCKER_AGENT_HOME_ROOT "$container_state_dir/docker/users"
    write_kv ARCLINK_DOCKER_CONTAINER_PRIV_DIR "$container_priv_dir"
    write_kv ARCLINK_DOCKER_HOST_REPO_DIR "$BOOTSTRAP_DIR"
    write_kv ARCLINK_DOCKER_HOST_PRIV_DIR "$BOOTSTRAP_DIR/arclink-priv"
  } >"$target"
  chmod 600 "$target"
}

maybe_run_docker_org_profile_builder() {
  local saved_priv_config_dir="${ARCLINK_PRIV_CONFIG_DIR:-}"
  local saved_priv_dir="${ARCLINK_PRIV_DIR:-}"

  ARCLINK_PRIV_DIR="$BOOTSTRAP_DIR/arclink-priv"
  ARCLINK_PRIV_CONFIG_DIR="$BOOTSTRAP_DIR/arclink-priv/config"
  maybe_run_org_profile_builder "$BOOTSTRAP_DIR"
  ARCLINK_PRIV_DIR="$saved_priv_dir"
  ARCLINK_PRIV_CONFIG_DIR="$saved_priv_config_dir"
}

collect_docker_install_answers() {
  local docker_env="" default_domain="" default_nextcloud_port="" default_nextcloud_admin_user=""
  local default_enable_nextcloud="" default_enable_private_git="" default_enable_quarto="" default_seed_vault=""
  local default_enable_tailscale_serve="" default_tailscale_serve_port=""
  local default_enable_tailscale_notion_webhook_funnel="" default_tailscale_notion_webhook_funnel_port=""
  local default_tailscale_notion_webhook_funnel_path="" default_tailscale_operator_user=""
  local default_pdf_vision_endpoint="" default_pdf_vision_model="" default_pdf_vision_api_key=""
  local default_git_name="" default_git_email="" current_postgres_password="" current_nextcloud_admin_password=""
  local nextcloud_state_present="0" nextcloud_admin_password_input="" default_org_profile_builder="0"

  docker_env="$(docker_env_file_path)"
  load_docker_runtime_config

  echo "ArcLink deploy: Shared Host Docker install / repair from current checkout"
  echo
  echo "This is the operator-led Shared Host substrate in Docker. It does not"
  echo "configure Sovereign customer pod ingress or ask Cloudflare vs Tailscale."
  echo "For the Dockerized paid control node, run: ./deploy.sh control install"
  echo
  echo "Shared Host Docker mode uses fixed container paths and the current checkout as the host bind mount:"
  echo "  host repo:    $BOOTSTRAP_DIR"
  echo "  host private: $BOOTSTRAP_DIR/arclink-priv"
  echo "  container:    /home/arclink/arclink"
  echo

  default_nextcloud_port="${NEXTCLOUD_PORT:-18080}"
  default_git_name="${BACKUP_GIT_AUTHOR_NAME:-ArcLink Backup}"
  default_git_email="${BACKUP_GIT_AUTHOR_EMAIL:-arclink@localhost}"
  default_enable_nextcloud="${ENABLE_NEXTCLOUD:-1}"
  default_enable_tailscale_serve="${ENABLE_TAILSCALE_SERVE:-0}"
  default_tailscale_serve_port="${TAILSCALE_SERVE_PORT:-443}"
  default_enable_tailscale_notion_webhook_funnel="${ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL:-0}"
  default_tailscale_notion_webhook_funnel_port="${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-443}"
  default_tailscale_notion_webhook_funnel_path="$(normalize_http_path "${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH:-/notion/webhook}")"
  default_tailscale_operator_user="${TAILSCALE_OPERATOR_USER:-$(id -un)}"
  default_enable_private_git="${ENABLE_PRIVATE_GIT:-1}"
  default_enable_quarto="${ENABLE_QUARTO:-0}"
  default_seed_vault="${SEED_SAMPLE_VAULT:-1}"
  default_nextcloud_admin_user="${NEXTCLOUD_ADMIN_USER:-admin}"
  default_pdf_vision_endpoint="${PDF_VISION_ENDPOINT:-}"
  default_pdf_vision_model="${PDF_VISION_MODEL:-}"
  default_pdf_vision_api_key="${PDF_VISION_API_KEY:-}"

  print_tailscale_https_certificate_guidance() {
    cat <<'EOF'
Tailscale Serve/Funnel prerequisite
  Before enabling Tailscale HTTPS routes here, open:
    https://login.tailscale.com/admin/dns
  In the same tailnet as this host, enable MagicDNS and HTTPS Certificates.
  Without HTTPS Certificates, Tailscale Serve/Funnel will pause on a browser
  consent URL or fail before ArcLink can publish the routes.
  If the installer prints a Tailscale approval URL later:
    https://login.tailscale.com/f/funnel?...  for the shared-host Notion webhook
    https://login.tailscale.com/f/serve?...   for tailnet-only Nextcloud/MCP
  open it as a tailnet admin, approve the feature for this node, then return
  to this terminal and press ENTER so ArcLink can retry the route.

EOF
  }

  ARCLINK_ORG_NAME="$(normalize_optional_answer "$(ask "Organization name (type none to clear)" "${ARCLINK_ORG_NAME:-}")")"
  ARCLINK_ORG_MISSION="$(normalize_optional_answer "$(ask "Organization mission (type none to clear)" "${ARCLINK_ORG_MISSION:-}")")"
  ARCLINK_ORG_PRIMARY_PROJECT="$(normalize_optional_answer "$(ask "Primary project or focus (type none to clear)" "${ARCLINK_ORG_PRIMARY_PROJECT:-}")")"
  ARCLINK_ORG_TIMEZONE="$(ask_validated_optional "Organization timezone (IANA, e.g. America/New_York; type none to clear)" "${ARCLINK_ORG_TIMEZONE:-Etc/UTC}" validate_org_timezone "Please enter a valid IANA timezone like America/New_York or type none.")"
  ARCLINK_ORG_QUIET_HOURS="$(ask_validated_optional "Organization quiet hours in local time (HH:MM-HH:MM, optional note; type none to clear)" "${ARCLINK_ORG_QUIET_HOURS:-}" validate_org_quiet_hours "Please enter quiet hours like 22:00-08:00 or 22:00-08:00 weekdays, or type none.")"
  collect_org_provider_answers

  if [[ ! -f "$BOOTSTRAP_DIR/arclink-priv/config/org-profile.yaml" ]]; then
    default_org_profile_builder="1"
  fi
  ARCLINK_ORG_PROFILE_BUILDER_ENABLED="$(ask_yes_no "Build or edit the private operating profile interactively now" "$default_org_profile_builder")"

  QMD_INDEX_NAME="${QMD_INDEX_NAME:-arclink}"
  QMD_COLLECTION_NAME="${QMD_COLLECTION_NAME:-vault}"
  QMD_RUN_EMBED="${QMD_RUN_EMBED:-1}"
  QMD_MCP_PORT="${QMD_MCP_PORT:-8181}"
  ARCLINK_MCP_PORT="${ARCLINK_MCP_PORT:-8282}"
  ARCLINK_NOTION_WEBHOOK_PORT="${ARCLINK_NOTION_WEBHOOK_PORT:-8283}"
  BACKUP_GIT_BRANCH="${BACKUP_GIT_BRANCH:-main}"
  ARCLINK_UPSTREAM_REPO_URL="${ARCLINK_UPSTREAM_REPO_URL:-$(canonical_arclink_upstream_repo_url)}"
  use_detected_upstream_repo_url_if_placeholder
  ARCLINK_UPSTREAM_BRANCH="${ARCLINK_UPSTREAM_BRANCH:-arclink}"
  collect_upstream_git_answers

  BACKUP_GIT_DEPLOY_KEY_PATH="${BACKUP_GIT_DEPLOY_KEY_PATH:-/home/arclink/arclink/arclink-priv/secrets/arclink-backup-ed25519}"
  BACKUP_GIT_KNOWN_HOSTS_FILE="${BACKUP_GIT_KNOWN_HOSTS_FILE:-/home/arclink/arclink/arclink-priv/secrets/arclink-backup-known_hosts}"
  collect_backup_git_answers
  BACKUP_GIT_AUTHOR_NAME="$(ask "Git author name" "$default_git_name")"
  BACKUP_GIT_AUTHOR_EMAIL="$(ask "Git author email" "$default_git_email")"
  NEXTCLOUD_PORT="$(ask "Nextcloud local port" "$default_nextcloud_port")"

  detect_tailscale
  default_domain="${NEXTCLOUD_TRUSTED_DOMAIN:-localhost}"
  if [[ -n "$TAILSCALE_DNS_NAME" ]]; then
    default_domain="$TAILSCALE_DNS_NAME"
    default_enable_tailscale_serve="1"
    echo "Detected Tailscale DNS name: $TAILSCALE_DNS_NAME"
    echo
  elif [[ -n "$TAILSCALE_TAILNET" ]]; then
    default_domain="$TAILSCALE_TAILNET"
    default_enable_tailscale_serve="1"
    echo "Detected Tailscale tailnet:  $TAILSCALE_TAILNET"
    echo
  fi
  if [[ -n "$TAILSCALE_DNS_NAME" || -n "$TAILSCALE_TAILNET" || "$default_enable_tailscale_serve" == "1" || "$default_enable_tailscale_notion_webhook_funnel" == "1" ]]; then
    print_tailscale_https_certificate_guidance
  fi

  NEXTCLOUD_TRUSTED_DOMAIN="$(ask "Nextcloud trusted domain / Tailscale hostname" "$default_domain")"
  POSTGRES_DB="${POSTGRES_DB:-nextcloud}"
  POSTGRES_USER="${POSTGRES_USER:-nextcloud}"
  NEXTCLOUD_VAULT_MOUNT_POINT="${NEXTCLOUD_VAULT_MOUNT_POINT:-/Vault}"
  ENABLE_NEXTCLOUD="$(ask_yes_no "Enable Nextcloud" "$default_enable_nextcloud")"
  if [[ "$ENABLE_NEXTCLOUD" == "1" ]]; then
    ENABLE_TAILSCALE_SERVE="$(ask_yes_no "Enable Tailscale HTTPS proxy for Nextcloud (tailnet only)" "$default_enable_tailscale_serve")"
  else
    ENABLE_TAILSCALE_SERVE="0"
  fi
  if [[ -n "$TAILSCALE_DNS_NAME" || -n "$TAILSCALE_TAILNET" || "${ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL:-0}" == "1" ]]; then
    ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL="$(ask_yes_no "Enable public Tailscale Funnel for the shared-host Notion webhook only" "$default_enable_tailscale_notion_webhook_funnel")"
    if [[ "$ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL" == "1" ]]; then
      TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT="$(ask "Public Tailscale Funnel HTTPS port for the shared-host Notion webhook" "$default_tailscale_notion_webhook_funnel_port")"
      TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH="$(normalize_http_path "$(ask "Public Tailscale Funnel path for the shared-host Notion webhook" "$default_tailscale_notion_webhook_funnel_path")")"
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
    if [[ "$ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL" == "1" && "${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-443}" == "$default_tailscale_serve_port" ]]; then
      default_tailscale_serve_port="8443"
    fi
    TAILSCALE_SERVE_PORT="$(ask "Tailnet-only Tailscale HTTPS port for Nextcloud and internal MCP routes" "$default_tailscale_serve_port")"
  else
    TAILSCALE_SERVE_PORT="$default_tailscale_serve_port"
  fi
  if [[ "$ENABLE_TAILSCALE_SERVE" == "1" && "$ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL" == "1" && "${TAILSCALE_SERVE_PORT:-443}" == "${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT:-443}" ]]; then
    echo "Tailscale Serve and the shared-host Notion webhook Funnel cannot share the same HTTPS port." >&2
    echo "Choose different values for the private tailnet port and the public webhook port." >&2
    return 1
  fi
  if [[ "$ENABLE_TAILSCALE_SERVE" == "1" || "$ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL" == "1" ]]; then
    TAILSCALE_OPERATOR_USER="$(ask "Tailscale operator user for serve/funnel management" "$default_tailscale_operator_user")"
  else
    TAILSCALE_OPERATOR_USER=""
  fi

  if docker_nextcloud_state_has_existing_data; then
    nextcloud_state_present="1"
  fi
  current_postgres_password="${POSTGRES_PASSWORD:-}"
  if [[ -z "$current_postgres_password" || "$nextcloud_state_present" != "1" ]]; then
    POSTGRES_PASSWORD="$(preserve_or_randomize_secret "$current_postgres_password")"
  else
    POSTGRES_PASSWORD="$current_postgres_password"
  fi
  NEXTCLOUD_ADMIN_USER="$(ask "Nextcloud admin user" "$default_nextcloud_admin_user")"
  current_nextcloud_admin_password="${NEXTCLOUD_ADMIN_PASSWORD:-}"
  if [[ -z "$current_nextcloud_admin_password" || "$nextcloud_state_present" != "1" ]]; then
    NEXTCLOUD_ADMIN_PASSWORD="$(preserve_or_randomize_secret "$current_nextcloud_admin_password")"
  else
    NEXTCLOUD_ADMIN_PASSWORD="$current_nextcloud_admin_password"
  fi
  nextcloud_admin_password_input="$(ask_secret_keep_default "Nextcloud admin password (ENTER keeps current)" "$NEXTCLOUD_ADMIN_PASSWORD")"
  NEXTCLOUD_ADMIN_PASSWORD="${nextcloud_admin_password_input:-$NEXTCLOUD_ADMIN_PASSWORD}"

  ENABLE_PRIVATE_GIT="$(ask_yes_no "Initialize arclink-priv as a git repo" "$default_enable_private_git")"
  ENABLE_QUARTO="$(ask_yes_no "Enable Quarto job container" "$default_enable_quarto")"
  SEED_SAMPLE_VAULT="$(ask_yes_no "Seed a starter vault structure" "$default_seed_vault")"
  collect_qmd_embedding_answers
  PDF_VISION_ENDPOINT="$(normalize_optional_answer "$(ask "OpenAI-compatible vision endpoint for PDF page captions (base /v1 or full /v1/chat/completions; type none to disable)" "$default_pdf_vision_endpoint")")"
  PDF_VISION_MODEL="$(normalize_optional_answer "$(ask "Vision model name for PDF page captions (type none to disable)" "$default_pdf_vision_model")")"
  PDF_VISION_API_KEY="$(ask_secret_with_default "Vision API key for PDF page captions (ENTER keeps current, type none to clear)" "$default_pdf_vision_api_key")"
  PDF_VISION_MAX_PAGES="${PDF_VISION_MAX_PAGES:-6}"
  if [[ -z "$PDF_VISION_ENDPOINT" && -z "$PDF_VISION_MODEL" && -z "$PDF_VISION_API_KEY" ]]; then
    PDF_VISION_ENDPOINT=""
    PDF_VISION_MODEL=""
    PDF_VISION_API_KEY=""
  fi

  write_docker_runtime_config "$docker_env"
  maybe_run_docker_org_profile_builder
  CONFIG_TARGET="$docker_env"
  echo
  echo "Wrote Docker config to: $docker_env"
}

normalize_control_ingress_mode() {
  local value="${1:-domain}"
  value="$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]')"
  case "$value" in
    domain|tailscale) printf '%s\n' "$value" ;;
    *) printf '%s\n' "domain" ;;
  esac
}

normalize_tailscale_host_strategy() {
  local value="${1:-path}"
  value="$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]')"
  case "$value" in
    path|subdomain) printf '%s\n' "$value" ;;
    *) printf '%s\n' "path" ;;
  esac
}

ensure_control_fleet_ssh_key() {
  local runtime_priv_dir="/home/arclink/arclink/arclink-priv"
  local default_host_key_path="$BOOTSTRAP_DIR/arclink-priv/secrets/ssh/id_ed25519"
  local default_host_known_hosts="$BOOTSTRAP_DIR/arclink-priv/secrets/ssh/known_hosts"
  local key_path="${ARCLINK_FLEET_SSH_KEY_PATH:-$default_host_key_path}"
  local known_hosts="${ARCLINK_FLEET_SSH_KNOWN_HOSTS_FILE:-$default_host_known_hosts}"

  case "$key_path" in
    "$runtime_priv_dir"/*)
      key_path="$BOOTSTRAP_DIR/arclink-priv/${key_path#"$runtime_priv_dir"/}"
      ;;
  esac
  case "$known_hosts" in
    "$runtime_priv_dir"/*)
      known_hosts="$BOOTSTRAP_DIR/arclink-priv/${known_hosts#"$runtime_priv_dir"/}"
      ;;
  esac

  mkdir -p "$(dirname "$key_path")"
  chmod 700 "$(dirname "$key_path")"
  if [[ ! -f "$key_path" ]]; then
    ssh-keygen -t ed25519 -N "" -C "arclink-control-fleet@$(hostname 2>/dev/null || printf arclink)" -f "$key_path" >/dev/null
  fi
  touch "$known_hosts"
  chmod 600 "$key_path" "$known_hosts"
  [[ -f "$key_path.pub" ]] && chmod 644 "$key_path.pub"
  ARCLINK_FLEET_SSH_KEY_HOST_PATH="$key_path"
  ARCLINK_FLEET_SSH_KNOWN_HOSTS_HOST_FILE="$known_hosts"
  if [[ "$key_path" == "$default_host_key_path" ]]; then
    ARCLINK_FLEET_SSH_KEY_PATH="$runtime_priv_dir/secrets/ssh/id_ed25519"
  else
    ARCLINK_FLEET_SSH_KEY_PATH="$key_path"
  fi
  if [[ "$known_hosts" == "$default_host_known_hosts" ]]; then
    ARCLINK_FLEET_SSH_KNOWN_HOSTS_FILE="$runtime_priv_dir/secrets/ssh/known_hosts"
  else
    ARCLINK_FLEET_SSH_KNOWN_HOSTS_FILE="$known_hosts"
  fi
}

print_control_fleet_ssh_key_guidance() {
  local key_path="${ARCLINK_FLEET_SSH_KEY_HOST_PATH:-${ARCLINK_FLEET_SSH_KEY_PATH:-}}"
  if [[ -z "$key_path" || ! -r "$key_path.pub" ]]; then
    return 0
  fi
  cat <<EOF
ArcLink fleet SSH control key
  Add this public key to the starter/fleet node account that ArcLink will use
  for SSH provisioning. This is idempotent; rerunning deploy.sh reuses it.

$(cat "$key_path.pub")

EOF
}

is_safe_local_fleet_user() {
  local user="${1:-}"
  [[ "$user" =~ ^[a-z_][a-z0-9_-]*$ ]]
}

is_local_fleet_ssh_host() {
  local host="${1:-}" candidate=""

  host="$(printf '%s' "$host" | tr '[:upper:]' '[:lower:]')"
  host="${host%.}"
  case "$host" in
    ""|localhost|127.0.0.1|::1)
      return 0
      ;;
  esac
  for candidate in \
    "$(hostname 2>/dev/null || true)" \
    "$(hostname -f 2>/dev/null || true)" \
    "${TAILSCALE_DNS_NAME:-}" \
    "${ARCLINK_TAILSCALE_DNS_NAME:-}"; do
    candidate="$(printf '%s' "$candidate" | tr '[:upper:]' '[:lower:]')"
    candidate="${candidate%.}"
    if [[ -n "$candidate" && "$host" == "$candidate" ]]; then
      return 0
    fi
  done
  return 1
}

ensure_local_fleet_ssh_access() {
  local user="${ARCLINK_LOCAL_FLEET_SSH_USER:-arclink}"
  local host="${ARCLINK_LOCAL_FLEET_SSH_HOST:-localhost}"
  local pub_path="${ARCLINK_FLEET_SSH_KEY_HOST_PATH:-${ARCLINK_FLEET_SSH_KEY_PATH:-}}.pub"
  local pub_key="" user_home="" user_group="" ssh_dir="" authorized_keys=""

  if ! is_local_fleet_ssh_host "$host"; then
    echo "Local fleet SSH bootstrap only manages this machine; '$host' looks remote." >&2
    return 1
  fi
  if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    echo "Local fleet SSH bootstrap needs root so it can create/repair the target Unix user." >&2
    return 1
  fi
  if ! is_safe_local_fleet_user "$user"; then
    echo "Refusing unsafe local fleet Unix user: $user" >&2
    return 1
  fi
  if [[ ! -r "$pub_path" ]]; then
    echo "Missing ArcLink fleet public key: $pub_path" >&2
    return 1
  fi

  pub_key="$(cat "$pub_path")"
  if ! id -u "$user" >/dev/null 2>&1; then
    useradd -m -s /bin/bash "$user"
    echo "Created local fleet Unix user: $user"
  fi
  user_home="$(resolve_user_home "$user" 2>/dev/null || getent passwd "$user" | awk -F: '{print $6}')"
  user_group="$(id -gn "$user" 2>/dev/null || printf '%s' "$user")"
  if [[ -z "$user_home" || ! -d "$user_home" ]]; then
    echo "Could not resolve home directory for local fleet Unix user: $user" >&2
    return 1
  fi

  ssh_dir="$user_home/.ssh"
  authorized_keys="$ssh_dir/authorized_keys"
  install -d -m 0700 -o "$user" -g "$user_group" "$ssh_dir"
  touch "$authorized_keys"
  if ! grep -Fxq "$pub_key" "$authorized_keys" 2>/dev/null; then
    printf '%s\n' "$pub_key" >>"$authorized_keys"
  fi
  chown "$user:$user_group" "$authorized_keys"
  chmod 0600 "$authorized_keys"

  if getent group docker >/dev/null 2>&1; then
    usermod -aG docker "$user" || true
  fi
  if [[ -n "${ARCLINK_STATE_ROOT_BASE:-}" ]]; then
    mkdir -p "$ARCLINK_STATE_ROOT_BASE"
    chown "$user:$user_group" "$ARCLINK_STATE_ROOT_BASE" || true
  fi
  echo "Prepared local fleet SSH access for $user@$host."
}

test_local_fleet_ssh_access() {
  local user="${ARCLINK_LOCAL_FLEET_SSH_USER:-arclink}"
  local host="${ARCLINK_LOCAL_FLEET_SSH_HOST:-localhost}"
  local key_path="${ARCLINK_FLEET_SSH_KEY_HOST_PATH:-${ARCLINK_FLEET_SSH_KEY_PATH:-}}"
  local known_hosts="${ARCLINK_FLEET_SSH_KNOWN_HOSTS_HOST_FILE:-${ARCLINK_FLEET_SSH_KNOWN_HOSTS_FILE:-}}"
  local -a ssh_opts=()

  if [[ -z "$key_path" || ! -r "$key_path" ]]; then
    echo "Skipping local fleet SSH smoke test: missing private key." >&2
    return 1
  fi
  if ! command -v ssh >/dev/null 2>&1; then
    echo "Skipping local fleet SSH smoke test: ssh client is not installed." >&2
    return 1
  fi
  if [[ -n "$known_hosts" ]]; then
    mkdir -p "$(dirname "$known_hosts")"
    touch "$known_hosts"
    chmod 0600 "$known_hosts" 2>/dev/null || true
    if command -v ssh-keyscan >/dev/null 2>&1; then
      ssh-keyscan -H "$host" >>"$known_hosts" 2>/dev/null || true
      sort -u -o "$known_hosts" "$known_hosts" 2>/dev/null || true
    fi
  fi
  ssh_opts=(
    -i "$key_path"
    -o BatchMode=yes
    -o ConnectTimeout=5
    -o IdentitiesOnly=yes
    -o StrictHostKeyChecking=accept-new
  )
  if [[ -n "$known_hosts" ]]; then
    ssh_opts+=(-o "UserKnownHostsFile=$known_hosts")
  fi
  if ssh "${ssh_opts[@]}" "$user@$host" true >/dev/null 2>&1; then
    echo "Verified local fleet SSH connectivity: $user@$host"
    return 0
  fi
  echo "Could not verify local fleet SSH connectivity for $user@$host." >&2
  echo "Install/enable OpenSSH server on this host, then rerun ./deploy.sh control install or reconfigure." >&2
  return 1
}

publish_control_tailscale_ingress() {
  local port="${ARCLINK_TAILSCALE_HTTPS_PORT:-443}"
  local notion_path="${ARCLINK_TAILSCALE_NOTION_PATH:-${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH:-/notion/webhook}}"
  local web_port="${ARCLINK_WEB_PORT:-3000}"
  local api_port="${ARCLINK_API_PORT:-8900}"
  local notion_port="${ARCLINK_NOTION_WEBHOOK_PORT:-8283}"

  if [[ "${ARCLINK_INGRESS_MODE:-domain}" != "tailscale" ]]; then
    return 0
  fi
  if ! command -v tailscale >/dev/null 2>&1; then
    echo "Tailscale ingress selected, but tailscale CLI is not installed on the control host." >&2
    echo "Docker services are up; install/login Tailscale and rerun ./deploy.sh control reconfigure." >&2
    return 0
  fi
  if ! tailscale status --json >/dev/null 2>&1; then
    echo "Tailscale ingress selected, but tailscale is not logged in or running on this host." >&2
    echo "Docker services are up; run tailscale up and rerun ./deploy.sh control reconfigure." >&2
    return 0
  fi
  notion_path="$(normalize_http_path "$notion_path")"
  echo "Publishing Dockerized Sovereign Control Node over Tailscale Funnel on HTTPS :$port ..."
  tailscale funnel --bg --yes --https="$port" "http://127.0.0.1:$web_port" >/dev/null
  tailscale funnel --bg --yes --https="$port" --set-path="/api" "http://127.0.0.1:$api_port/api" >/dev/null
  tailscale funnel --bg --yes --https="$port" --set-path="$notion_path" "http://127.0.0.1:$notion_port$notion_path" >/dev/null
}

collect_control_install_answers() {
  local docker_env="" default_base_domain="" default_api_port="" default_web_port=""
  local default_cors_origin="" default_cookie_domain="" default_price_id=""
  local detected_tailscale_dns="" ingress_answer="" default_tailscale_dns=""
  local ssh_key_confirmed="" setup_local_fleet_ssh="" local_fleet_access_prepared="0"

  docker_env="$(docker_env_file_path)"
  load_docker_runtime_config

  echo "ArcLink deploy: Sovereign Control Node install / repair from current checkout"
  echo
  echo "This path runs the public onboarding API, website control center,"
  echo "shared Telegram/Discord bot webhooks, Stripe webhook boundary, and"
  echo "fleet/provisioning/admin control-plane services from this host."
  echo
  echo "Provider credentials are optional during bootstrap. Missing credentials"
  echo "leave live E2E provider checks gated until you add them to:"
  echo "  $docker_env"
  echo

  ARCLINK_PRODUCT_NAME="${ARCLINK_PRODUCT_NAME:-ArcLink}"
  ARCLINK_PRIMARY_PROVIDER="${ARCLINK_PRIMARY_PROVIDER:-chutes}"
  detect_tailscale
  detected_tailscale_dns="${TAILSCALE_DNS_NAME:-}"
  default_tailscale_dns="${ARCLINK_TAILSCALE_DNS_NAME:-$detected_tailscale_dns}"
  ARCLINK_INGRESS_MODE="$(normalize_control_ingress_mode "${ARCLINK_INGRESS_MODE:-domain}")"
  default_base_domain="${ARCLINK_BASE_DOMAIN:-arclink.online}"
  default_api_port="${ARCLINK_API_PORT:-8900}"
  default_web_port="${ARCLINK_WEB_PORT:-3000}"
  default_cors_origin="${ARCLINK_CORS_ORIGIN:-https://$default_base_domain}"
  default_cookie_domain="${ARCLINK_COOKIE_DOMAIN:-.$default_base_domain}"
  default_first_agent_price_id="${ARCLINK_FIRST_AGENT_PRICE_ID:-${ARCLINK_DEFAULT_PRICE_ID:-price_arclink_starter}}"
  default_additional_agent_price_id="${ARCLINK_ADDITIONAL_AGENT_PRICE_ID:-price_arclink_additional_agent}"

  if [[ -n "$detected_tailscale_dns" ]]; then
    echo "Detected Tailscale DNS name: $detected_tailscale_dns"
    echo
  fi
  ingress_answer="$(normalize_optional_answer "$(ask "ArcLink ingress mode (domain/tailscale)" "$ARCLINK_INGRESS_MODE")")"
  ARCLINK_INGRESS_MODE="$(normalize_control_ingress_mode "${ingress_answer:-$ARCLINK_INGRESS_MODE}")"
  if [[ "$ARCLINK_INGRESS_MODE" == "tailscale" ]]; then
    ARCLINK_TAILSCALE_DNS_NAME="$(normalize_optional_answer "$(ask "Tailscale DNS name for this control node" "${default_tailscale_dns:-$default_base_domain}")")"
    if [[ -z "$ARCLINK_TAILSCALE_DNS_NAME" ]]; then
      ARCLINK_TAILSCALE_DNS_NAME="$default_base_domain"
    fi
    ARCLINK_TAILSCALE_HTTPS_PORT="$(ask "Tailscale HTTPS/Funnel port for public control and Notion" "${ARCLINK_TAILSCALE_HTTPS_PORT:-443}")"
    if [[ -z "$ARCLINK_TAILSCALE_HTTPS_PORT" ]]; then
      ARCLINK_TAILSCALE_HTTPS_PORT="443"
    fi
    case "$ARCLINK_TAILSCALE_HTTPS_PORT" in
      443|8443|10000) ;;
      *)
        echo "Tailscale Funnel supports HTTPS ports 443, 8443, and 10000. Using 443." >&2
        ARCLINK_TAILSCALE_HTTPS_PORT="443"
        ;;
    esac
    ARCLINK_TAILSCALE_NOTION_PATH="$(normalize_http_path "$(ask "Tailscale public control-node Notion webhook path (customer pod callbacks are per deployment)" "${ARCLINK_TAILSCALE_NOTION_PATH:-${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH:-/notion/webhook}}")")"
    ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY="$(normalize_tailscale_host_strategy "$(ask "Tailscale deployment URL strategy (path/subdomain)" "${ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY:-path}")")"
    ARCLINK_BASE_DOMAIN="$ARCLINK_TAILSCALE_DNS_NAME"
    ARCLINK_EDGE_TARGET="$ARCLINK_TAILSCALE_DNS_NAME"
    ARCLINK_TAILSCALE_CONTROL_URL="https://$ARCLINK_TAILSCALE_DNS_NAME"
    if [[ "$ARCLINK_TAILSCALE_HTTPS_PORT" != "443" ]]; then
      ARCLINK_TAILSCALE_CONTROL_URL="https://$ARCLINK_TAILSCALE_DNS_NAME:$ARCLINK_TAILSCALE_HTTPS_PORT"
    fi
    ENABLE_TAILSCALE_NOTION_WEBHOOK_FUNNEL="1"
    TAILSCALE_NOTION_WEBHOOK_FUNNEL_PORT="$ARCLINK_TAILSCALE_HTTPS_PORT"
    TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH="$ARCLINK_TAILSCALE_NOTION_PATH"
    ARCLINK_NOTION_WEBHOOK_PUBLIC_URL="$ARCLINK_TAILSCALE_CONTROL_URL$ARCLINK_TAILSCALE_NOTION_PATH"
    default_cors_origin="$ARCLINK_TAILSCALE_CONTROL_URL"
    default_cookie_domain=""
  else
    ARCLINK_BASE_DOMAIN="$(normalize_optional_answer "$(ask "ArcLink public root domain" "$default_base_domain")")"
    if [[ -z "$ARCLINK_BASE_DOMAIN" ]]; then
      ARCLINK_BASE_DOMAIN="arclink.online"
    fi
    ARCLINK_EDGE_TARGET="$(normalize_optional_answer "$(ask "Cloudflare DNS edge target" "${ARCLINK_EDGE_TARGET:-edge.$ARCLINK_BASE_DOMAIN}")")"
    if [[ -z "$ARCLINK_EDGE_TARGET" ]]; then
      ARCLINK_EDGE_TARGET="edge.$ARCLINK_BASE_DOMAIN"
    fi
    ARCLINK_TAILSCALE_CONTROL_URL="${ARCLINK_TAILSCALE_CONTROL_URL:-}"
    ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY="$(normalize_tailscale_host_strategy "${ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY:-path}")"
    default_cors_origin="${ARCLINK_CORS_ORIGIN:-https://$ARCLINK_BASE_DOMAIN}"
    default_cookie_domain="${ARCLINK_COOKIE_DOMAIN:-.$ARCLINK_BASE_DOMAIN}"
  fi
  ARCLINK_API_HOST="0.0.0.0"
  ARCLINK_API_PORT="$(ask "Control API local port" "$default_api_port")"
  ARCLINK_WEB_PORT="$(ask "Control web local port" "$default_web_port")"
  ARCLINK_CORS_ORIGIN="$(normalize_optional_answer "$(ask "Browser CORS origin (type none to clear)" "$default_cors_origin")")"
  ARCLINK_COOKIE_DOMAIN="$(normalize_optional_answer "$(ask "Session cookie domain (type none to clear)" "$default_cookie_domain")")"
  ARCLINK_FIRST_AGENT_PRICE_ID="$(normalize_optional_answer "$(ask "Stripe first Raven agent price ID ($35/month)" "$default_first_agent_price_id")")"
  if [[ -z "$ARCLINK_FIRST_AGENT_PRICE_ID" ]]; then
    ARCLINK_FIRST_AGENT_PRICE_ID="price_arclink_starter"
  fi
  ARCLINK_DEFAULT_PRICE_ID="$ARCLINK_FIRST_AGENT_PRICE_ID"
  ARCLINK_ADDITIONAL_AGENT_PRICE_ID="$(normalize_optional_answer "$(ask "Stripe additional Raven agent price ID ($15/month)" "$default_additional_agent_price_id")")"
  if [[ -z "$ARCLINK_ADDITIONAL_AGENT_PRICE_ID" ]]; then
    ARCLINK_ADDITIONAL_AGENT_PRICE_ID="price_arclink_additional_agent"
  fi
  ARCLINK_FIRST_AGENT_MONTHLY_CENTS="${ARCLINK_FIRST_AGENT_MONTHLY_CENTS:-3500}"
  ARCLINK_ADDITIONAL_AGENT_MONTHLY_CENTS="${ARCLINK_ADDITIONAL_AGENT_MONTHLY_CENTS:-1500}"
  ARCLINK_CONTROL_PROVISIONER_ENABLED="$(ask_yes_no "Enable Sovereign pod provisioner now" "${ARCLINK_CONTROL_PROVISIONER_ENABLED:-0}")"
  ARCLINK_EXECUTOR_ADAPTER="${ARCLINK_EXECUTOR_ADAPTER:-disabled}"
  if [[ "$ARCLINK_CONTROL_PROVISIONER_ENABLED" == "1" ]]; then
    echo
    echo "Sovereign executor adapter:"
    echo "  fake  - no external changes; useful only for dry validation"
    echo "  local - apply pods on this machine with Docker Compose"
    echo "  ssh   - copy pod bundles to fleet hosts and run Docker Compose over SSH"
    ARCLINK_EXECUTOR_ADAPTER="$(normalize_optional_answer "$(ask "Executor adapter" "${ARCLINK_EXECUTOR_ADAPTER:-ssh}")")"
    if [[ -z "$ARCLINK_EXECUTOR_ADAPTER" ]]; then
      ARCLINK_EXECUTOR_ADAPTER="ssh"
    fi
  fi
  ARCLINK_STATE_ROOT_BASE="$(normalize_optional_answer "$(ask "Worker deployment state root base" "${ARCLINK_STATE_ROOT_BASE:-/arcdata/deployments}")")"
  if [[ -z "$ARCLINK_STATE_ROOT_BASE" ]]; then
    ARCLINK_STATE_ROOT_BASE="/arcdata/deployments"
  fi
  ARCLINK_REGISTER_LOCAL_FLEET_HOST="$(ask_yes_no "Register this machine as a starter Sovereign worker host" "${ARCLINK_REGISTER_LOCAL_FLEET_HOST:-0}")"
  if [[ "$ARCLINK_REGISTER_LOCAL_FLEET_HOST" == "1" ]]; then
    ARCLINK_LOCAL_FLEET_HOSTNAME="$(normalize_optional_answer "$(ask "Local fleet hostname" "${ARCLINK_LOCAL_FLEET_HOSTNAME:-$(hostname -f 2>/dev/null || hostname)}")")"
    if [[ "${ARCLINK_EXECUTOR_ADAPTER:-}" == "ssh" || "${ARCLINK_EXECUTOR_ADAPTER:-}" == "local" ]]; then
      ARCLINK_LOCAL_FLEET_SSH_HOST="$(normalize_optional_answer "$(ask "Local/starter fleet SSH host" "${ARCLINK_LOCAL_FLEET_SSH_HOST:-localhost}")")"
      if [[ -z "$ARCLINK_LOCAL_FLEET_SSH_HOST" ]]; then
        ARCLINK_LOCAL_FLEET_SSH_HOST="localhost"
      fi
      ARCLINK_LOCAL_FLEET_SSH_USER="$(normalize_optional_answer "$(ask "Local/starter fleet SSH user" "${ARCLINK_LOCAL_FLEET_SSH_USER:-arclink}")")"
      if [[ -z "$ARCLINK_LOCAL_FLEET_SSH_USER" ]]; then
        ARCLINK_LOCAL_FLEET_SSH_USER="arclink"
      fi
    fi
    ARCLINK_LOCAL_FLEET_REGION="$(normalize_optional_answer "$(ask "Local fleet region/tag (type none to clear)" "${ARCLINK_LOCAL_FLEET_REGION:-}")")"
    ARCLINK_LOCAL_FLEET_CAPACITY_SLOTS="$(ask "Local fleet capacity slots" "${ARCLINK_LOCAL_FLEET_CAPACITY_SLOTS:-4}")"
  fi
  if [[ "$ARCLINK_CONTROL_PROVISIONER_ENABLED" == "1" ]]; then
    ensure_control_fleet_ssh_key
    print_control_fleet_ssh_key_guidance
    if [[ "$ARCLINK_REGISTER_LOCAL_FLEET_HOST" == "1" ]] && \
      [[ "${ARCLINK_EXECUTOR_ADAPTER:-}" == "local" || "${ARCLINK_EXECUTOR_ADAPTER:-}" == "ssh" ]] && \
      is_local_fleet_ssh_host "${ARCLINK_LOCAL_FLEET_SSH_HOST:-localhost}"; then
      if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
        setup_local_fleet_ssh="$(ask_yes_no "Create/repair local fleet Unix user and authorize this key now" "1")"
        if [[ "$setup_local_fleet_ssh" == "1" ]] && ensure_local_fleet_ssh_access; then
          local_fleet_access_prepared="1"
          test_local_fleet_ssh_access || true
        fi
      else
        echo "Run deploy.sh as root to create/repair the local fleet Unix user automatically." >&2
      fi
    fi
    if [[ "$local_fleet_access_prepared" != "1" ]] && \
      { [[ "${ARCLINK_EXECUTOR_ADAPTER:-}" == "ssh" ]] || [[ "$ARCLINK_REGISTER_LOCAL_FLEET_HOST" == "1" ]]; }; then
      ssh_key_confirmed="$(ask_yes_no "I have added this public key to the starter/fleet node authorized_keys" "0")"
      if [[ "$ssh_key_confirmed" != "1" ]]; then
        echo "Continuing. SSH fleet applies will remain blocked until that key is trusted by the target node." >&2
      fi
    fi
  fi

  STRIPE_SECRET_KEY="$(ask_secret_with_default "Stripe secret key (ENTER keeps current, type none to clear)" "${STRIPE_SECRET_KEY:-}")"
  STRIPE_WEBHOOK_SECRET="$(ask_secret_with_default "Stripe webhook secret (ENTER keeps current, type none to clear)" "${STRIPE_WEBHOOK_SECRET:-}")"
  if [[ "$ARCLINK_INGRESS_MODE" == "domain" ]]; then
    CLOUDFLARE_API_TOKEN="$(ask_secret_with_default "Cloudflare DNS API token (ENTER keeps current, type none to clear)" "${CLOUDFLARE_API_TOKEN:-}")"
    CLOUDFLARE_ZONE_ID="$(normalize_optional_answer "$(ask "Cloudflare zone ID (type none to clear)" "${CLOUDFLARE_ZONE_ID:-}")")"
  else
    echo "Tailscale ingress selected: Cloudflare DNS credentials are not required for Sovereign pod routing."
  fi
  CHUTES_API_KEY="$(ask_secret_with_default "Chutes owner API key (ENTER keeps current, type none to clear)" "${CHUTES_API_KEY:-}")"
  TELEGRAM_BOT_TOKEN="$(ask_secret_with_default "Public Telegram bot token (ENTER keeps current, type none to clear)" "${TELEGRAM_BOT_TOKEN:-}")"
  TELEGRAM_BOT_USERNAME="$(normalize_optional_answer "$(ask "Public Telegram bot username (type none to clear)" "${TELEGRAM_BOT_USERNAME:-}")")"
  DISCORD_BOT_TOKEN="$(ask_secret_with_default "Public Discord bot token (ENTER keeps current, type none to clear)" "${DISCORD_BOT_TOKEN:-}")"
  DISCORD_APP_ID="$(normalize_optional_answer "$(ask "Discord application ID (type none to clear)" "${DISCORD_APP_ID:-}")")"
  DISCORD_PUBLIC_KEY="$(ask_secret_with_default "Discord public key (ENTER keeps current, type none to clear)" "${DISCORD_PUBLIC_KEY:-}")"

  write_docker_runtime_config "$docker_env"
  CONFIG_TARGET="$docker_env"
  echo
  echo "Wrote Sovereign Control Node config to: $docker_env"
}

run_docker_install_flow() {
  local run_curator_setup="${1:-1}"
  local operation="docker-upgrade"

  if [[ "$run_curator_setup" == "1" ]]; then
    operation="docker-install"
  fi
  begin_deploy_operation "$operation" "$BOOTSTRAP_DIR/arclink-priv/state"
  trap 'finish_deploy_operation; arclink_deploy_stable_copy_cleanup' EXIT

  echo "Installing or repairing ArcLink Docker stack from this checkout..."
  run_arclink_docker bootstrap
  if [[ "$run_curator_setup" == "1" && "${ARCLINK_DOCKER_SKIP_OPERATOR_CONFIG:-0}" != "1" && -t 0 ]]; then
    collect_docker_install_answers
  fi
  run_arclink_docker build
  run_arclink_docker up
  if [[ "$run_curator_setup" == "1" && "${ARCLINK_DOCKER_SKIP_CURATOR_SETUP:-0}" != "1" ]]; then
    run_arclink_docker curator-setup
  fi
  run_arclink_docker reconcile
  run_arclink_docker record-release
  run_arclink_docker ports
  run_arclink_docker health
  run_arclink_docker live-smoke
  finish_deploy_operation
  trap 'arclink_deploy_stable_copy_cleanup' EXIT
}

register_control_public_bot_actions() {
  local docker_env=""

  docker_env="$(docker_env_file_path)"
  if [[ ! -r "$docker_env" ]]; then
    echo "ArcLink public bot action registration skipped: config not readable at $docker_env" >&2
    return 0
  fi
  if [[ ! -f "$BOOTSTRAP_DIR/python/arclink_public_bot_commands.py" ]]; then
    echo "ArcLink public bot action registration skipped: helper is missing" >&2
    return 0
  fi
  echo "Registering ArcLink public bot actions with Telegram and Discord..."
  if ! ARCLINK_CONFIG_FILE="$docker_env" \
    PYTHONPATH="$BOOTSTRAP_DIR/python${PYTHONPATH:+:$PYTHONPATH}" \
    python3 "$BOOTSTRAP_DIR/python/arclink_public_bot_commands.py"; then
    echo "ArcLink public bot action registration failed; the control node remains deployed." >&2
    return 0
  fi
}

run_control_install_flow() {
  local run_interactive="${1:-1}"
  local operation="control-upgrade"

  if [[ "$run_interactive" == "1" ]]; then
    operation="control-install"
  fi
  begin_deploy_operation "$operation" "$BOOTSTRAP_DIR/arclink-priv/state"
  trap 'finish_deploy_operation; arclink_deploy_stable_copy_cleanup' EXIT

  echo "Installing or repairing ArcLink Sovereign Control Node from this checkout..."
  run_arclink_docker bootstrap
  if [[ "$run_interactive" == "1" && "${ARCLINK_CONTROL_SKIP_CONFIG:-0}" != "1" && -t 0 ]]; then
    collect_control_install_answers
  fi
  run_arclink_docker build
  run_arclink_docker up
  load_docker_runtime_config
  publish_control_tailscale_ingress
  register_control_public_bot_actions
  run_arclink_docker record-release
  run_arclink_docker ports
  run_arclink_docker health
  finish_deploy_operation
  trap 'arclink_deploy_stable_copy_cleanup' EXIT
}

run_control_reconfigure_flow() {
  echo "Refreshing ArcLink Sovereign Control Node generated config and port assignments..."
  run_arclink_docker bootstrap
  if [[ "${ARCLINK_CONTROL_SKIP_CONFIG:-0}" != "1" && -t 0 ]]; then
    collect_control_install_answers
  fi
  run_arclink_docker config -q
  load_docker_runtime_config
  publish_control_tailscale_ingress
  register_control_public_bot_actions
  run_arclink_docker ports
}

control_command_from_mode() {
  case "$1" in
    control-install) printf '%s\n' "install" ;;
    control-upgrade) printf '%s\n' "upgrade" ;;
    control-reconfigure) printf '%s\n' "reconfigure" ;;
    control-bootstrap) printf '%s\n' "bootstrap" ;;
    control-config) printf '%s\n' "config" ;;
    control-build) printf '%s\n' "build" ;;
    control-up) printf '%s\n' "up" ;;
    control-down) printf '%s\n' "down" ;;
    control-ps) printf '%s\n' "ps" ;;
    control-ports) printf '%s\n' "ports" ;;
    control-logs) printf '%s\n' "logs" ;;
    control-health) printf '%s\n' "health" ;;
    control-provision-once) printf '%s\n' "provision-once" ;;
    control-teardown) printf '%s\n' "teardown" ;;
    control-write-config) printf '%s\n' "write-config" ;;
    control-remove) printf '%s\n' "remove" ;;
    *) printf '%s\n' "" ;;
  esac
}

run_control_deploy_flow() {
  local command="${CONTROL_DEPLOY_COMMAND:-}"

  if [[ "$MODE" != "control" ]]; then
    command="$(control_command_from_mode "$MODE")"
  fi
  if [[ -z "$command" || "$command" == "menu" ]]; then
    if choose_control_mode; then
      command="${CONTROL_DEPLOY_COMMAND:-}"
    else
      choose_mode
      return 0
    fi
  fi

  case "$command" in
    help|-h|--help)
      control_usage
      ;;
    install)
      run_control_install_flow 1
      ;;
    upgrade)
      run_control_install_flow 0
      ;;
    reconfigure)
      run_control_reconfigure_flow
      ;;
    bootstrap|write-config|config|build|up|down|ps|ports|logs|health|record-release|provision-once|teardown|remove)
      run_arclink_docker "$command" ${CONTROL_DEPLOY_ARGS[@]+"${CONTROL_DEPLOY_ARGS[@]}"}
      ;;
    *)
      echo "Unknown Sovereign Control Node command: ${command:-<empty>}" >&2
      control_usage >&2
      return 2
      ;;
  esac
}

run_docker_reconfigure_flow() {
  echo "Refreshing ArcLink Docker generated config and port assignments..."
  run_arclink_docker bootstrap
  run_arclink_docker config -q
  run_arclink_docker ports
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
    install)
      run_docker_install_flow 1
      ;;
    upgrade)
      run_docker_install_flow 0
      ;;
    reconfigure)
      run_docker_reconfigure_flow
      ;;
    bootstrap|write-config|config|build|up|reconcile|down|ps|ports|logs|health|record-release|live-smoke|teardown|remove|notion-ssot|notion-migrate|notion-transfer|enrollment-status|enrollment-trace|enrollment-align|enrollment-reset|curator-setup|rotate-nextcloud-secrets|agent-payload|agent|pins-show|pins-check|pin-upgrade-notify|hermes-upgrade|hermes-upgrade-check|qmd-upgrade|qmd-upgrade-check|nextcloud-upgrade|nextcloud-upgrade-check|postgres-upgrade|postgres-upgrade-check|redis-upgrade|redis-upgrade-check|code-server-upgrade|code-server-upgrade-check|nvm-upgrade|nvm-upgrade-check|node-upgrade|node-upgrade-check)
      run_arclink_docker "$command" ${DOCKER_DEPLOY_ARGS[@]+"${DOCKER_DEPLOY_ARGS[@]}"}
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
    if [[ "${ARCLINK_REEXEC_ATTEMPTED:-0}" == "1" ]]; then
      return "$reexec_status"
    fi
  fi

  require_supported_host_mode "$MODE"

  collect_install_answers
  prepare_operator_upstream_deploy_key_before_sudo

  if [[ "$MODE" == "write-config" ]]; then
    seed_private_repo "$ARCLINK_PRIV_DIR"
    write_runtime_config "$CONFIG_TARGET"
    maybe_run_org_profile_builder "$BOOTSTRAP_DIR"
    echo
    echo "Wrote config to: $CONFIG_TARGET"
    echo "Private repo scaffold: $ARCLINK_PRIV_DIR"
    return 0
  fi

  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    run_root_install
    return 0
  fi

  ANSWERS_FILE="$(mktemp /tmp/arclink-install.XXXXXX.env)"
  trap 'rm -f "${ANSWERS_FILE:-}"' EXIT
  write_answers_file "$ANSWERS_FILE"
  echo
  echo "Switching to sudo for system setup..."
  if ! sudo_deploy ARCLINK_INSTALL_ANSWERS_FILE="$ANSWERS_FILE" "${DEPLOY_EXEC_PATH:-$SELF_PATH}" --apply-install; then
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

  ANSWERS_FILE="$(mktemp /tmp/arclink-remove.XXXXXX.env)"
  trap 'rm -f "${ANSWERS_FILE:-}"' EXIT
  write_answers_file "$ANSWERS_FILE"
  echo
  echo "Switching to sudo for teardown..."
  if ! sudo_deploy ARCLINK_INSTALL_ANSWERS_FILE="$ANSWERS_FILE" "${DEPLOY_EXEC_PATH:-$SELF_PATH}" --apply-remove; then
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
  control|control-install|control-upgrade|control-reconfigure|control-bootstrap|control-config|control-build|control-up|control-down|control-ps|control-ports|control-logs|control-health|control-teardown|control-write-config|control-remove)
    run_control_deploy_flow
    ;;
  docker|docker-install|docker-upgrade|docker-reconfigure|docker-bootstrap|docker-config|docker-build|docker-up|docker-down|docker-ps|docker-ports|docker-logs|docker-health|docker-teardown|docker-write-config|docker-remove|docker-notion-ssot|docker-notion-migrate|docker-notion-transfer|docker-enrollment-status|docker-enrollment-trace|docker-enrollment-align|docker-enrollment-reset|docker-curator-setup|docker-rotate-nextcloud-secrets|docker-agent-payload|docker-pins-show|docker-pins-check|docker-pin-upgrade-notify|docker-hermes-upgrade|docker-hermes-upgrade-check|docker-qmd-upgrade|docker-qmd-upgrade-check|docker-nextcloud-upgrade|docker-nextcloud-upgrade-check|docker-postgres-upgrade|docker-postgres-upgrade-check|docker-redis-upgrade|docker-redis-upgrade-check|docker-code-server-upgrade|docker-code-server-upgrade-check|docker-nvm-upgrade|docker-nvm-upgrade-check|docker-node-upgrade|docker-node-upgrade-check)
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
  notion-migrate)
    run_notion_migrate_flow
    ;;
  notion-transfer)
    run_notion_transfer_flow
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
