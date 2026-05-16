#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${ARCLINK_REPO_DIR:-/home/arclink/arclink}"
PRIV_DIR="${ARCLINK_PRIV_DIR:-$REPO_DIR/arclink-priv}"
CONFIG_DIR="${ARCLINK_PRIV_CONFIG_DIR:-$PRIV_DIR/config}"
CONFIG_FILE="${ARCLINK_CONFIG_FILE:-$CONFIG_DIR/docker.env}"
TEMPLATE_DIR="$REPO_DIR/templates/arclink-priv"
CONFIG_REPO_DIR="${ARCLINK_DOCKER_CONFIG_REPO_DIR:-$REPO_DIR}"
CONFIG_PRIV_DIR="${ARCLINK_DOCKER_CONFIG_PRIV_DIR:-$CONFIG_REPO_DIR/arclink-priv}"
CONFIG_RUNTIME_DIR="${ARCLINK_DOCKER_CONFIG_RUNTIME_DIR:-/opt/arclink/runtime}"
CONFIG_AGENT_HOME_ROOT="$CONFIG_PRIV_DIR/state/docker/users"

runtime_env_config_enabled() {
  case "${ARCLINK_RUNTIME_ENV_CONFIG:-0}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

write_runtime_env_config() {
  local target="${ARCLINK_RUNTIME_CONFIG_FILE:-/tmp/arclink-runtime.env}"
  mkdir -p "$(dirname "$target")"
  python3 - "$target" <<'PY'
import os
import shlex
import sys

target = sys.argv[1]
state_dir = os.environ.get("STATE_DIR") or os.environ.get("ARCLINK_MEMORY_SYNTH_STATE_DIR") or "/srv/memory"
repo_dir = os.environ.get("ARCLINK_REPO_DIR") or "/home/arclink/arclink"
runtime_dir = os.environ.get("RUNTIME_DIR") or "/opt/arclink/runtime"
defaults = {
    "ARCLINK_NAME": "arclink",
    "ARCLINK_USER": "arclink",
    "ARCLINK_REPO_DIR": repo_dir,
    "ARCLINK_HOME": "/home/arclink",
    "ARCLINK_PRIV_DIR": f"{state_dir}/arclink-priv",
    "ARCLINK_PRIV_CONFIG_DIR": f"{state_dir}/arclink-priv/config",
    "VAULT_DIR": "/srv/vault",
    "STATE_DIR": state_dir,
    "RUNTIME_DIR": runtime_dir,
    "PUBLISHED_DIR": f"{state_dir}/published",
    "ARCLINK_DB_PATH": f"{state_dir}/arclink-control.sqlite3",
    "ARCLINK_NOTION_INDEX_DIR": f"{state_dir}/notion-index",
    "ARCLINK_NOTION_INDEX_MARKDOWN_DIR": f"{state_dir}/notion-index/markdown",
    "PDF_INGEST_DIR": f"{state_dir}/pdf-ingest",
    "PDF_INGEST_MARKDOWN_DIR": f"{state_dir}/pdf-ingest/markdown",
    "PDF_INGEST_STATUS_FILE": f"{state_dir}/pdf-ingest/status.json",
    "PDF_INGEST_MANIFEST_DB": f"{state_dir}/pdf-ingest/manifest.sqlite3",
    "PDF_INGEST_LOCK_FILE": f"{state_dir}/pdf-ingest/ingest.lock",
    "QMD_REFRESH_LOCK_FILE": f"{state_dir}/qmd-refresh.lock",
    "ARCLINK_MEMORY_SYNTH_STATE_DIR": state_dir,
    "ARCLINK_MEMORY_SYNTH_STATUS_FILE": f"{state_dir}/memory-synth/status.json",
    "ARCLINK_MEMORY_SYNTH_LOCK_FILE": f"{state_dir}/memory-synth/synth.lock",
}
keys = [
    "ARCLINK_NAME",
    "ARCLINK_USER",
    "ARCLINK_HOME",
    "ARCLINK_REPO_DIR",
    "ARCLINK_PRIV_DIR",
    "ARCLINK_PRIV_CONFIG_DIR",
    "VAULT_DIR",
    "STATE_DIR",
    "RUNTIME_DIR",
    "PUBLISHED_DIR",
    "ARCLINK_DB_PATH",
    "ARCLINK_AGENTS_STATE_DIR",
    "ARCLINK_NOTION_INDEX_DIR",
    "ARCLINK_NOTION_INDEX_MARKDOWN_DIR",
    "PDF_INGEST_DIR",
    "PDF_INGEST_MARKDOWN_DIR",
    "PDF_INGEST_STATUS_FILE",
    "PDF_INGEST_MANIFEST_DB",
    "PDF_INGEST_LOCK_FILE",
    "QMD_REFRESH_LOCK_FILE",
    "QMD_STATE_DIR",
    "QMD_INDEX_NAME",
    "QMD_COLLECTION_NAME",
    "PDF_INGEST_COLLECTION_NAME",
    "ARCLINK_NOTION_INDEX_COLLECTION_NAME",
    "ARCLINK_NOTION_INDEX_ROOTS",
    "ARCLINK_NOTION_INDEX_RUN_EMBED",
    "VAULT_QMD_COLLECTION_MASK",
    "QMD_RUN_EMBED",
    "QMD_EMBED_PROVIDER",
    "QMD_EMBED_ENDPOINT",
    "QMD_EMBED_ENDPOINT_MODEL",
    "QMD_EMBED_DIMENSIONS",
    "QMD_EMBED_TIMEOUT_SECONDS",
    "QMD_EMBED_MAX_DOCS_PER_BATCH",
    "QMD_EMBED_MAX_BATCH_MB",
    "QMD_EMBED_FORCE_ON_NEXT_REFRESH",
    "QMD_MCP_PORT",
    "QMD_MCP_CONTAINER_PORT",
    "QMD_MCP_LOOPBACK_PORT",
    "QMD_MCP_INTERNAL_PORT",
    "QMD_PROXY_BIND_HOST",
    "ARCLINK_MCP_HOST",
    "ARCLINK_MCP_PORT",
    "ARCLINK_MCP_URL",
    "ARCLINK_BOOTSTRAP_URL",
    "ARCLINK_NOTION_WEBHOOK_HOST",
    "ARCLINK_NOTION_WEBHOOK_PORT",
    "ARCLINK_NOTION_WEBHOOK_PUBLIC_URL",
    "ARCLINK_MEMORY_SYNTH_ENABLED",
    "ARCLINK_MEMORY_SYNTH_ENDPOINT",
    "ARCLINK_MEMORY_SYNTH_MODEL",
    "ARCLINK_MEMORY_SYNTH_MAX_SOURCES_PER_RUN",
    "ARCLINK_MEMORY_SYNTH_MAX_SOURCE_CHARS",
    "ARCLINK_MEMORY_SYNTH_MAX_OUTPUT_TOKENS",
    "ARCLINK_MEMORY_SYNTH_TIMEOUT_SECONDS",
    "ARCLINK_MEMORY_SYNTH_FAILURE_RETRY_SECONDS",
    "ARCLINK_MEMORY_SYNTH_CARDS_IN_CONTEXT",
    "ARCLINK_MEMORY_SYNTH_STATE_DIR",
    "ARCLINK_MEMORY_SYNTH_STATUS_FILE",
    "ARCLINK_MEMORY_SYNTH_LOCK_FILE",
    "ARCLINK_MEMORY_SYNTH_ON_VAULT_CHANGE",
    "PDF_VISION_ENDPOINT",
    "PDF_VISION_MODEL",
    "PDF_VISION_MAX_PAGES",
    "VAULT_WATCH_DEBOUNCE_SECONDS",
    "VAULT_WATCH_MAX_BATCH_SECONDS",
    "VAULT_WATCH_RUN_EMBED",
    "HERMES_HOME",
    "DRIVE_ROOT",
    "CODE_WORKSPACE_ROOT",
    "DRIVE_LINKED_ROOT",
    "CODE_LINKED_ROOT",
    "ARCLINK_LINKED_RESOURCES_ROOT",
    "TERMINAL_WORKSPACE_ROOT",
    "ARCLINK_DRIVE_ROOT",
    "ARCLINK_CODE_WORKSPACE_ROOT",
    "ARCLINK_TERMINAL_TUI_COMMAND",
    "HERMES_TUI_DIR",
    "ARCLINK_DEPLOYMENT_ID",
    "ARCLINK_PREFIX",
    "ARCLINK_DASHBOARD_HOST",
    "ARCLINK_FILES_HOST",
    "ARCLINK_CODE_HOST",
    "ARCLINK_HERMES_HOST",
    "ARCLINK_DASHBOARD_URL",
    "ARCLINK_HERMES_URL",
    "ARCLINK_FILES_URL",
    "ARCLINK_CODE_URL",
    "ARCLINK_NOTION_CALLBACK_URL",
    "ARCLINK_NOTION_ROOT_URL",
    "ARCLINK_CAPTAIN_NAME",
    "ARCLINK_CAPTAIN_EMAIL",
    "ARCLINK_AGENT_NAME",
    "ARCLINK_AGENT_TITLE",
    "ARCLINK_PRIMARY_PROVIDER",
    "ARCLINK_CHUTES_BASE_URL",
    "ARCLINK_CHUTES_DEFAULT_MODEL",
    "ARCLINK_MODEL_REASONING_DEFAULT",
    "TELEGRAM_REACTIONS",
    "DISCORD_REACTIONS",
]
values = {key: defaults[key] for key in defaults}
for key in keys:
    if key in os.environ:
        values[key] = os.environ[key]
for key in keys:
    if key not in values and key in defaults:
        values[key] = defaults[key]
with open(target, "w", encoding="utf-8") as handle:
    handle.write("# Generated by bin/docker-entrypoint.sh from the per-Pod runtime environment.\n")
    for key in keys:
        if key in values:
            handle.write(f"{key}={shlex.quote(str(values[key]))}\n")
PY
  chmod 600 "$target" 2>/dev/null || true
}

if runtime_env_config_enabled; then
  CONFIG_FILE="${ARCLINK_RUNTIME_CONFIG_FILE:-/tmp/arclink-runtime.env}"
  write_runtime_env_config
  export ARCLINK_CONFIG_FILE="$CONFIG_FILE"
  if [[ -d "$CONFIG_RUNTIME_DIR/hermes-venv" ]]; then
    export PATH="$CONFIG_RUNTIME_DIR/hermes-venv/bin:$PATH"
  fi
  exec "$@"
fi

ensure_docker_state_dirs() {
  local qmd_config_dir="${XDG_CONFIG_HOME:-/home/arclink/.qmd/config}/qmd"
  local qmd_cache_dir="${XDG_CACHE_HOME:-/home/arclink/.qmd/cache}/qmd"
  local dir=""
  local -a dirs=(
    "$CONFIG_DIR"
    "$PRIV_DIR/state"
    "$PRIV_DIR/state/agents"
    "$PRIV_DIR/state/archived-agents"
    "$PRIV_DIR/state/curator/hermes-home"
    "$PRIV_DIR/state/nextcloud/config"
    "$PRIV_DIR/state/nextcloud/db"
    "$PRIV_DIR/state/nextcloud/redis"
    "$PRIV_DIR/state/nextcloud/html"
    "$PRIV_DIR/state/nextcloud/html/data"
    "$PRIV_DIR/state/nextcloud/data"
    "$PRIV_DIR/state/nextcloud/hooks/pre-installation"
    "$PRIV_DIR/state/nextcloud/hooks/post-installation"
    "$PRIV_DIR/state/nextcloud/hooks/before-starting"
    "$PRIV_DIR/state/nextcloud/empty-skeleton"
    "$PRIV_DIR/state/notion-index/markdown"
    "$PRIV_DIR/state/pdf-ingest/markdown"
    "$PRIV_DIR/state/runtime"
    "$PRIV_DIR/state/docker/jobs"
    "$PRIV_DIR/state/docker/users"
    "$PRIV_DIR/secrets/ssh"
    "$PRIV_DIR/published"
    "$PRIV_DIR/quarto"
    "$PRIV_DIR/vault"
    "$qmd_config_dir"
    "$qmd_cache_dir"
  )

  for dir in "${dirs[@]}"; do
    if mkdir -p "$dir" 2>/dev/null; then
      continue
    fi
    if [[ -d "$dir" ]]; then
      continue
    fi
    case "$dir" in
      "$CONFIG_DIR"|"$PRIV_DIR"/*|"$CONFIG_DIR"/*|"$qmd_config_dir"|"$qmd_cache_dir")
        echo "Warning: unable to create Docker state directory $dir; continuing because split private mounts may provide it at runtime." >&2
        ;;
      *)
        echo "Unable to create required Docker state directory $dir." >&2
        return 1
        ;;
    esac
  done
}

ensure_docker_state_dirs

if [[ -d "$TEMPLATE_DIR" ]]; then
  rsync -a --no-owner --no-group --no-perms --omit-dir-times --ignore-existing \
    --exclude='/.gitignore' \
    "$TEMPLATE_DIR"/ "$PRIV_DIR"/
fi

generate_secret() {
  python3 - <<'PY'
import secrets

print(secrets.token_urlsafe(32))
PY
}

config_value() {
  local key="$1"
  [[ -f "$CONFIG_FILE" ]] || return 1
  awk -v key="$key" '
    index($0, key "=") == 1 {
      value = substr($0, length(key) + 2)
      gsub(/^"|"$/, "", value)
      print value
      exit
    }
  ' "$CONFIG_FILE"
}

set_config_value() {
  local key="$1"
  local value="$2"
  local tmp_file=""

  tmp_file="$(mktemp "$CONFIG_FILE.XXXXXX")"
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
  ' "$CONFIG_FILE" >"$tmp_file"
  chmod 600 "$tmp_file"
  mv "$tmp_file" "$CONFIG_FILE"
}

repair_placeholder_secret() {
  local key="$1"
  local initialized_marker="$2"
  local value=""

  value="$(config_value "$key" 2>/dev/null || true)"
  if [[ -n "$value" && "$value" != "change-me" ]]; then
    return 0
  fi
  if [[ -z "$value" && -e "$initialized_marker" ]]; then
    set_config_value "$key" "change-me"
    return 0
  fi
  if [[ -e "$initialized_marker" ]]; then
    return 0
  fi

  set_config_value "$key" "$(generate_secret)"
}

write_default_docker_config() {
  local postgres_password="${POSTGRES_PASSWORD:-}"
  local nextcloud_admin_password="${NEXTCLOUD_ADMIN_PASSWORD:-}"
  local session_hash_pepper="${ARCLINK_SESSION_HASH_PEPPER:-}"

  if [[ -z "$postgres_password" || "$postgres_password" == "change-me" ]]; then
    postgres_password="$(generate_secret)"
  fi
  if [[ -z "$nextcloud_admin_password" || "$nextcloud_admin_password" == "change-me" ]]; then
    nextcloud_admin_password="$(generate_secret)"
  fi
  if [[ -z "$session_hash_pepper" || "$session_hash_pepper" == "change-me" ]]; then
    session_hash_pepper="$(generate_secret)"
  fi

  cat >"$CONFIG_FILE" <<EOF
# Generated by bin/docker-entrypoint.sh for Docker Compose runtime.
ARCLINK_NAME=arclink
ARCLINK_USER=arclink
ARCLINK_BACKEND_ALLOWED_CIDRS=172.16.0.0/12
ARCLINK_HOME=/home/arclink
ARCLINK_REPO_DIR=$CONFIG_REPO_DIR
ARCLINK_PRIV_DIR=$CONFIG_PRIV_DIR
ARCLINK_PRIV_CONFIG_DIR=$CONFIG_PRIV_DIR/config
VAULT_DIR=$CONFIG_PRIV_DIR/vault
STATE_DIR=$CONFIG_PRIV_DIR/state
NEXTCLOUD_STATE_DIR=$CONFIG_PRIV_DIR/state/nextcloud
RUNTIME_DIR=$CONFIG_RUNTIME_DIR
PUBLISHED_DIR=$CONFIG_PRIV_DIR/published
ARCLINK_DB_PATH=$CONFIG_PRIV_DIR/state/arclink-control.sqlite3
ARCLINK_AGENTS_STATE_DIR=$CONFIG_PRIV_DIR/state/agents
ARCLINK_CURATOR_DIR=$CONFIG_PRIV_DIR/state/curator
ARCLINK_CURATOR_MANIFEST=$CONFIG_PRIV_DIR/state/curator/manifest.json
ARCLINK_CURATOR_HERMES_HOME=$CONFIG_PRIV_DIR/state/curator/hermes-home
ARCLINK_ARCHIVED_AGENTS_DIR=$CONFIG_PRIV_DIR/state/archived-agents
ARCLINK_NOTION_INDEX_DIR=$CONFIG_PRIV_DIR/state/notion-index
ARCLINK_NOTION_INDEX_MARKDOWN_DIR=$CONFIG_PRIV_DIR/state/notion-index/markdown
QMD_INDEX_NAME=arclink
QMD_COLLECTION_NAME=vault
VAULT_QMD_COLLECTION_MASK=**/*.{md,markdown,mdx,txt,text}
PDF_INGEST_COLLECTION_NAME=vault-pdf-ingest
QMD_RUN_EMBED=1
QMD_MCP_PORT=8181
ARCLINK_PRODUCT_NAME=ArcLink
ARCLINK_BASE_DOMAIN=arclink.online
ARCLINK_INGRESS_MODE=domain
ARCLINK_TAILSCALE_DNS_NAME=
ARCLINK_TAILSCALE_CONTROL_URL=
ARCLINK_TAILSCALE_HTTPS_PORT=443
ARCLINK_TAILSCALE_NOTION_PATH=/notion/webhook
ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY=path
ARCLINK_PRIMARY_PROVIDER=chutes
ARCLINK_MCP_HOST=0.0.0.0
ARCLINK_MCP_PORT=8282
ARCLINK_MCP_URL=http://arclink-mcp:8282/mcp
ARCLINK_BOOTSTRAP_URL=http://arclink-mcp:8282/mcp
ARCLINK_API_HOST=0.0.0.0
ARCLINK_API_PORT=8900
ARCLINK_WEB_PORT=3000
ARCLINK_CORS_ORIGIN=
ARCLINK_COOKIE_DOMAIN=
ARCLINK_SESSION_HASH_PEPPER=$session_hash_pepper
ARCLINK_SESSION_HASH_PEPPER_REQUIRED=1
ARCLINK_DEFAULT_PRICE_ID=price_arclink_founders
ARCLINK_FOUNDERS_PRICE_ID=price_arclink_founders
ARCLINK_SOVEREIGN_PRICE_ID=price_arclink_sovereign
ARCLINK_SCALE_PRICE_ID=price_arclink_scale
ARCLINK_FIRST_AGENT_PRICE_ID=price_arclink_founders
ARCLINK_SOVEREIGN_AGENT_EXPANSION_PRICE_ID=price_arclink_sovereign_agent_expansion
ARCLINK_SCALE_AGENT_EXPANSION_PRICE_ID=price_arclink_scale_agent_expansion
ARCLINK_ADDITIONAL_AGENT_PRICE_ID=price_arclink_sovereign_agent_expansion
ARCLINK_FOUNDERS_MONTHLY_CENTS=14900
ARCLINK_SOVEREIGN_MONTHLY_CENTS=19900
ARCLINK_SCALE_MONTHLY_CENTS=27500
ARCLINK_FIRST_AGENT_MONTHLY_CENTS=14900
ARCLINK_SOVEREIGN_AGENT_EXPANSION_MONTHLY_CENTS=9900
ARCLINK_SCALE_AGENT_EXPANSION_MONTHLY_CENTS=7900
ARCLINK_ADDITIONAL_AGENT_MONTHLY_CENTS=9900
ARCLINK_CONTROL_PROVISIONER_ENABLED=1
ARCLINK_CONTROL_PROVISIONER_INTERVAL_SECONDS=30
ARCLINK_CONTROL_PROVISIONER_BATCH_SIZE=5
ARCLINK_SOVEREIGN_PROVISION_MAX_ATTEMPTS=5
ARCLINK_EXECUTOR_ADAPTER=disabled
ARCLINK_EXECUTOR_MACHINE_MODE_ENABLED=0
ARCLINK_EXECUTOR_MACHINE_HOST_ALLOWLIST=
ARCLINK_EDGE_TARGET=edge.arclink.online
ARCLINK_STATE_ROOT_BASE=/arcdata/deployments
ARCLINK_SECRET_STORE_DIR=$CONFIG_PRIV_DIR/state/sovereign-secrets
ARCLINK_REGISTER_LOCAL_FLEET_HOST=0
ARCLINK_LOCAL_FLEET_HOSTNAME=
ARCLINK_LOCAL_FLEET_SSH_HOST=
ARCLINK_LOCAL_FLEET_SSH_USER=arclink
ARCLINK_LOCAL_FLEET_REGION=
ARCLINK_LOCAL_FLEET_CAPACITY_SLOTS=4
ARCLINK_FLEET_SSH_KEY_PATH=
ARCLINK_FLEET_SSH_KNOWN_HOSTS_FILE=
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
CLOUDFLARE_API_TOKEN=
CLOUDFLARE_API_TOKEN_REF=
CLOUDFLARE_ZONE_ID=
CHUTES_API_KEY=
ARCLINK_QMD_URL=http://qmd-mcp:8181/mcp
ARCLINK_NOTION_WEBHOOK_HOST=0.0.0.0
ARCLINK_NOTION_WEBHOOK_PORT=8283
PDF_INGEST_ENABLED=1
PDF_INGEST_EXTRACTOR=auto
PDF_INGEST_TRIGGER_QMD_REFRESH=1
PDF_INGEST_DOCLING_FORCE_OCR=0
PDF_VISION_ENDPOINT=
PDF_VISION_MODEL=
PDF_VISION_API_KEY=
PDF_VISION_MAX_PAGES=6
ARCLINK_MEMORY_SYNTH_ENABLED=auto
ARCLINK_MEMORY_SYNTH_ENDPOINT=
ARCLINK_MEMORY_SYNTH_MODEL=
ARCLINK_MEMORY_SYNTH_API_KEY=
ARCLINK_MEMORY_SYNTH_MAX_SOURCES_PER_RUN=12
ARCLINK_MEMORY_SYNTH_MAX_SOURCE_CHARS=4500
ARCLINK_MEMORY_SYNTH_MAX_OUTPUT_TOKENS=450
ARCLINK_MEMORY_SYNTH_TIMEOUT_SECONDS=60
ARCLINK_MEMORY_SYNTH_FAILURE_RETRY_SECONDS=3600
ARCLINK_MEMORY_SYNTH_CARDS_IN_CONTEXT=8
VAULT_WATCH_DEBOUNCE_SECONDS=5
VAULT_WATCH_RUN_EMBED=auto
BACKUP_GIT_BRANCH=main
BACKUP_GIT_REMOTE=
BACKUP_GIT_AUTHOR_NAME="ArcLink Backup"
BACKUP_GIT_AUTHOR_EMAIL=arclink@localhost
NEXTCLOUD_PORT=18080
NEXTCLOUD_TRUSTED_DOMAIN=localhost
POSTGRES_DB=nextcloud
POSTGRES_USER=nextcloud
POSTGRES_PASSWORD=$postgres_password
NEXTCLOUD_ADMIN_USER=admin
NEXTCLOUD_ADMIN_PASSWORD=$nextcloud_admin_password
NEXTCLOUD_VAULT_MOUNT_POINT=/Vault
ENABLE_NEXTCLOUD=1
ENABLE_TAILSCALE_SERVE=0
OPERATOR_NOTIFY_CHANNEL_PLATFORM=tui-only
OPERATOR_NOTIFY_CHANNEL_ID=
OPERATOR_GENERAL_CHANNEL_PLATFORM=
OPERATOR_GENERAL_CHANNEL_ID=
TELEGRAM_BOT_TOKEN=
TELEGRAM_BOT_USERNAME=
TELEGRAM_WEBHOOK_URL=
TELEGRAM_WEBHOOK_SECRET=
DISCORD_BOT_TOKEN=
DISCORD_APP_ID=
DISCORD_PUBLIC_KEY=
ARCLINK_CURATOR_CHANNELS=tui-only
ARCLINK_HERMES_DOCS_SYNC_ENABLED=1
ARCLINK_HERMES_DOCS_REPO_URL=https://github.com/NousResearch/hermes-agent.git
ARCLINK_HERMES_DOCS_SOURCE_SUBDIR=website/docs
ARCLINK_HERMES_DOCS_STATE_DIR=$CONFIG_PRIV_DIR/state/hermes-docs-src
ARCLINK_HERMES_DOCS_VAULT_DIR=$CONFIG_PRIV_DIR/vault/Agents_KB/hermes-agent-docs
ARCLINK_AGENT_DASHBOARD_BACKEND_PORT_BASE=19000
ARCLINK_AGENT_DASHBOARD_PROXY_PORT_BASE=29000
ARCLINK_AGENT_PORT_SLOT_SPAN=5000
ARCLINK_DOCKER_AGENT_HOME_ROOT=$CONFIG_AGENT_HOME_ROOT
ARCLINK_DOCKER_CONTAINER_PRIV_DIR=$CONFIG_PRIV_DIR
ARCLINK_DOCKER_HOST_REPO_DIR=${ARCLINK_DOCKER_HOST_REPO_DIR:-}
ARCLINK_DOCKER_HOST_PRIV_DIR=${ARCLINK_DOCKER_HOST_PRIV_DIR:-}
ARCLINK_SSOT_NOTION_ROOT_PAGE_URL=
ARCLINK_SSOT_NOTION_ROOT_PAGE_ID=
ARCLINK_SSOT_NOTION_SPACE_URL=
ARCLINK_SSOT_NOTION_SPACE_ID=
ARCLINK_SSOT_NOTION_SPACE_KIND=
ARCLINK_SSOT_NOTION_API_VERSION=2026-03-11
ARCLINK_SSOT_NOTION_TOKEN=
ENABLE_PRIVATE_GIT=0
ENABLE_QUARTO=0
SEED_SAMPLE_VAULT=1
QUARTO_PROJECT_DIR=$CONFIG_PRIV_DIR/quarto
QUARTO_OUTPUT_DIR=$CONFIG_PRIV_DIR/published
EOF
  chmod 600 "$CONFIG_FILE"
}

ensure_nextcloud_config() {
  local nextcloud_config="$PRIV_DIR/state/nextcloud/config/arclink.config.php"
  if [[ -f "$nextcloud_config" ]]; then
    return 0
  fi
  if [[ ! -w "$(dirname "$nextcloud_config")" ]]; then
    return 0
  fi

  cat >"$nextcloud_config" <<'EOF'
<?php
$CONFIG = [
  'skeletondirectory' => '',
  'templatedirectory' => '',
];
EOF
}

copy_legacy_nextcloud_data_if_needed() {
  local legacy_data="$PRIV_DIR/state/nextcloud/data"
  local live_data="$PRIV_DIR/state/nextcloud/html/data"

  if [[ -f "$live_data/.ncdata" || ! -f "$legacy_data/.ncdata" ]]; then
    return 0
  fi

  if command -v rsync >/dev/null 2>&1; then
    rsync -a --no-owner --no-group --ignore-existing "$legacy_data"/ "$live_data"/
  else
    cp -Rpn "$legacy_data"/. "$live_data"/
  fi
}

ensure_nextcloud_data_dir() {
  local live_data="$PRIV_DIR/state/nextcloud/html/data"

  if [[ -d "$live_data" && ! -w "$live_data" ]]; then
    return 0
  fi
  mkdir -p "$live_data"
  if [[ ! -w "$live_data" ]]; then
    return 0
  fi
  copy_legacy_nextcloud_data_if_needed
  if [[ ! -f "$live_data/.ncdata" ]]; then
    cat >"$live_data/.ncdata" <<'EOF'
# Nextcloud data directory
# Do not change this file
EOF
  fi
  if [[ ! -f "$live_data/index.html" ]]; then
    : >"$live_data/index.html"
  fi
  chmod 0770 "$live_data" 2>/dev/null || true
  chmod 0644 "$live_data/.ncdata" "$live_data/index.html" 2>/dev/null || true
}

if [[ ! -f "$CONFIG_FILE" || "${ARCLINK_DOCKER_REWRITE_CONFIG:-0}" == "1" ]]; then
  write_default_docker_config
fi

repair_placeholder_secret POSTGRES_PASSWORD "$PRIV_DIR/state/nextcloud/db/PG_VERSION"
repair_placeholder_secret NEXTCLOUD_ADMIN_PASSWORD "$PRIV_DIR/state/nextcloud/html/config/config.php"
if [[ -z "$(config_value ARCLINK_SESSION_HASH_PEPPER 2>/dev/null || true)" || "$(config_value ARCLINK_SESSION_HASH_PEPPER 2>/dev/null || true)" == "change-me" ]]; then
  set_config_value ARCLINK_SESSION_HASH_PEPPER "$(generate_secret)"
fi
if [[ -z "$(config_value ARCLINK_SESSION_HASH_PEPPER_REQUIRED 2>/dev/null || true)" ]]; then
  set_config_value ARCLINK_SESSION_HASH_PEPPER_REQUIRED "1"
fi

ensure_nextcloud_config
ensure_nextcloud_data_dir

export ARCLINK_CONFIG_FILE="$CONFIG_FILE"
if [[ -d "$CONFIG_RUNTIME_DIR/hermes-venv" ]]; then
  export PATH="$CONFIG_RUNTIME_DIR/hermes-venv/bin:$PATH"
fi
exec "$@"
