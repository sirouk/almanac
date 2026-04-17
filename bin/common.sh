#!/usr/bin/env bash
set -euo pipefail

BOOTSTRAP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

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
  local nested_priv
  local sibling_priv
  nested_priv="$BOOTSTRAP_DIR/almanac-priv/config/almanac.env"
  sibling_priv="$(cd "$BOOTSTRAP_DIR/.." && pwd)/almanac-priv/config/almanac.env"

  local candidates=(
    "${ALMANAC_CONFIG_FILE:-}"
    "$BOOTSTRAP_DIR/config/almanac.env"
    "$nested_priv"
    "$sibling_priv"
    "$HOME/almanac/almanac-priv/config/almanac.env"
    "$HOME/almanac-priv/config/almanac.env"
  )
  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -n "$candidate" && -f "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

CONFIG_FILE="$(find_config_file || true)"

if [[ -n "${CONFIG_FILE:-}" && -f "$CONFIG_FILE" ]]; then
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
QMD_INDEX_NAME="${QMD_INDEX_NAME:-almanac}"
QMD_COLLECTION_NAME="${QMD_COLLECTION_NAME:-vault}"
PDF_INGEST_COLLECTION_NAME="${PDF_INGEST_COLLECTION_NAME:-vault-pdf-ingest}"
VAULT_QMD_COLLECTION_MASK="${VAULT_QMD_COLLECTION_MASK:-**/*.{md,markdown,mdx,txt,text}}"
VAULT_QMD_COLLECTION_MASK="$(normalize_vault_qmd_collection_mask "$VAULT_QMD_COLLECTION_MASK")"
QMD_RUN_EMBED="${QMD_RUN_EMBED:-1}"
QMD_MCP_PORT="${QMD_MCP_PORT:-8181}"
ALMANAC_MCP_HOST="${ALMANAC_MCP_HOST:-127.0.0.1}"
ALMANAC_MCP_PORT="${ALMANAC_MCP_PORT:-8282}"
ALMANAC_MCP_URL="${ALMANAC_MCP_URL:-http://${ALMANAC_MCP_HOST}:${ALMANAC_MCP_PORT}/mcp}"
ALMANAC_NOTION_WEBHOOK_HOST="${ALMANAC_NOTION_WEBHOOK_HOST:-127.0.0.1}"
ALMANAC_NOTION_WEBHOOK_PORT="${ALMANAC_NOTION_WEBHOOK_PORT:-8283}"
ALMANAC_BOOTSTRAP_WINDOW_SECONDS="${ALMANAC_BOOTSTRAP_WINDOW_SECONDS:-3600}"
ALMANAC_BOOTSTRAP_PER_IP_LIMIT="${ALMANAC_BOOTSTRAP_PER_IP_LIMIT:-5}"
ALMANAC_BOOTSTRAP_GLOBAL_PENDING_LIMIT="${ALMANAC_BOOTSTRAP_GLOBAL_PENDING_LIMIT:-20}"
ALMANAC_BOOTSTRAP_PENDING_TTL_SECONDS="${ALMANAC_BOOTSTRAP_PENDING_TTL_SECONDS:-900}"
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
OPERATOR_GENERAL_CHANNEL_PLATFORM="${OPERATOR_GENERAL_CHANNEL_PLATFORM:-}"
OPERATOR_GENERAL_CHANNEL_ID="${OPERATOR_GENERAL_CHANNEL_ID:-}"
ALMANAC_MODEL_PRESET_CODEX="${ALMANAC_MODEL_PRESET_CODEX:-openai:codex}"
ALMANAC_MODEL_PRESET_OPUS="${ALMANAC_MODEL_PRESET_OPUS:-anthropic:claude-opus}"
ALMANAC_MODEL_PRESET_CHUTES="${ALMANAC_MODEL_PRESET_CHUTES:-chutes:auto-failover}"
CHUTES_MCP_URL="${CHUTES_MCP_URL:-}"

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
  if [[ -n "${XDG_CACHE_HOME:-}" ]]; then
    printf '%s/qmd\n' "$XDG_CACHE_HOME"
  else
    printf '%s/.cache/qmd\n' "$HOME"
  fi
}

qmd_db_path() {
  local normalized_name
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

ensure_shared_hermes_runtime() {
  ensure_uv
  local repo_dir="$RUNTIME_DIR/hermes-agent-src"
  local venv_dir="$RUNTIME_DIR/hermes-venv"

  if ! command -v uv >/dev/null 2>&1; then
    echo "uv is required to manage the shared Hermes runtime." >&2
    return 1
  fi

  if [[ ! -d "$repo_dir/.git" ]]; then
    git clone --depth 1 https://github.com/NousResearch/hermes-agent.git "$repo_dir"
  else
    git -C "$repo_dir" pull --ff-only
  fi

  if [[ ! -x "$venv_dir/bin/hermes" ]]; then
    uv venv "$venv_dir" --python 3.11
  fi

  # shellcheck disable=SC1090
  source "$venv_dir/bin/activate"
  uv pip install -e "$repo_dir[cli,mcp,messaging,cron]"
}

ensure_qmd_collection() {
  local collection_name="$1"
  local collection_path="$2"
  local collection_mask="${3:-**/*.md}"
  ensure_nvm
  local collection_info existing_path existing_mask

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
  export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
  if [[ -s "$NVM_DIR/nvm.sh" ]]; then
    # shellcheck disable=SC1090
    source "$NVM_DIR/nvm.sh"
  fi
}

ensure_uv() {
  export PATH="$HOME/.local/bin:$PATH"
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

ensure_layout() {
  local qmd_db_dir

  qmd_db_dir="$(dirname "$QMD_INDEX_DB_PATH")"

  mkdir -p \
    "$ALMANAC_PRIV_DIR" \
    "$ALMANAC_PRIV_CONFIG_DIR" \
    "$VAULT_DIR" \
    "$STATE_DIR" \
    "$NEXTCLOUD_STATE_DIR" \
    "$PDF_INGEST_DIR" \
    "$PDF_INGEST_MARKDOWN_DIR" \
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
