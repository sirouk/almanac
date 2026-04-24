#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

usage() {
  cat >&2 <<'EOF'
Usage: refresh-agent-install.sh --unix-user <user> [--bot-name <name>] [--user-name <name>] [--hermes-home <path>] [--repo-dir <path>] [--restart-gateway]

Re-sync Almanac skills/plugins into an enrolled user's Hermes home, upsert the
default Almanac MCP server entries without interactive prompts, refresh the
identity prompt, then kick the managed-memory refresh and restart agent-facing
services. By default, an already-running gateway is left alone to avoid
interrupting user work. Pass --restart-gateway only when the shared Hermes
runtime itself changed and the live gateway process must pick up new code.
EOF
}

UNIX_USER=""
BOT_NAME=""
USER_NAME=""
HERMES_HOME_ARG=""
REPO_DIR_ARG=""
RESTART_GATEWAY="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --unix-user)
      UNIX_USER="${2:-}"
      shift 2
      ;;
    --bot-name)
      BOT_NAME="${2:-}"
      shift 2
      ;;
    --user-name)
      USER_NAME="${2:-}"
      shift 2
      ;;
    --hermes-home)
      HERMES_HOME_ARG="${2:-}"
      shift 2
      ;;
    --repo-dir)
      REPO_DIR_ARG="${2:-}"
      shift 2
      ;;
    --restart-gateway)
      RESTART_GATEWAY="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$UNIX_USER" ]]; then
  usage
  exit 2
fi

HOME_DIR="$(resolve_user_home "$UNIX_USER")"
if [[ -z "$HOME_DIR" ]]; then
  echo "Could not resolve home directory for $UNIX_USER" >&2
  exit 1
fi

if ! id "$UNIX_USER" >/dev/null 2>&1; then
  echo "Unix user does not exist: $UNIX_USER" >&2
  exit 1
fi

TARGET_UID="$(id -u "$UNIX_USER")"
TARGET_HERMES_HOME="${HERMES_HOME_ARG:-$HOME_DIR/.local/share/almanac-agent/hermes-home}"
SOURCE_REPO_DIR="${REPO_DIR_ARG:-$ALMANAC_REPO_DIR}"
RUNTIME_PYTHON="$(require_runtime_python)"
RUNTIME_HERMES="$(require_runtime_hermes)"
ALMANAC_QMD_URL="${ALMANAC_QMD_URL:-http://127.0.0.1:${QMD_MCP_PORT:-8181}/mcp}"
TARGET_LOCAL_BIN_DIR="$HOME_DIR/.local/bin"
TARGET_VAULT_LINK_PATH="${ALMANAC_USER_VAULT_LINK_PATH:-$HOME_DIR/Vault}"

run_as_target() {
  local -a cmd=("$@")
  if [[ "$(id -un)" == "$UNIX_USER" ]]; then
    env HOME="$HOME_DIR" HERMES_HOME="$TARGET_HERMES_HOME" "${cmd[@]}"
    return
  fi
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "Run as $UNIX_USER or root to refresh $UNIX_USER's Hermes install." >&2
    exit 1
  fi
  runuser -u "$UNIX_USER" -- env HOME="$HOME_DIR" HERMES_HOME="$TARGET_HERMES_HOME" "${cmd[@]}"
}

run_user_systemctl() {
  local -a cmd=(systemctl --user "$@")
  local runtime_dir="/run/user/$TARGET_UID"
  local bus_path="$runtime_dir/bus"
  if [[ ! -S "$bus_path" ]]; then
    echo "User bus is not available at $bus_path; skipping systemd --user refresh/restart." >&2
    return 75
  fi
  if [[ "$(id -un)" == "$UNIX_USER" ]]; then
    env \
      HOME="$HOME_DIR" \
      HERMES_HOME="$TARGET_HERMES_HOME" \
      XDG_RUNTIME_DIR="$runtime_dir" \
      DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" \
      "${cmd[@]}"
    return
  fi
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "Run as $UNIX_USER or root to manage $UNIX_USER's user services." >&2
    exit 1
  fi
  runuser -u "$UNIX_USER" -- env \
    HOME="$HOME_DIR" \
    HERMES_HOME="$TARGET_HERMES_HOME" \
    XDG_RUNTIME_DIR="$runtime_dir" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" \
    "${cmd[@]}"
}

SERVICE_NOTES=()
try_user_systemctl() {
  local label="$1"
  shift
  if run_user_systemctl "$@" >/dev/null; then
    SERVICE_NOTES+=("    - $label: ok")
  else
    local rc=$?
    SERVICE_NOTES+=("    - $label: skipped or failed (rc=$rc)")
  fi
}

target_can_access_repo() {
  if [[ "$(id -un)" == "$UNIX_USER" ]]; then
    [[ -x "$SOURCE_REPO_DIR/bin/install-almanac-skills.sh" ]] && return 0
    return 1
  fi
  if [[ "$(id -u)" -ne 0 ]]; then
    return 1
  fi
  runuser -u "$UNIX_USER" -- test -x "$SOURCE_REPO_DIR/bin/install-almanac-skills.sh"
}

run_with_target_env_as_root() {
  env HOME="$HOME_DIR" HERMES_HOME="$TARGET_HERMES_HOME" "$@"
}

fix_target_ownership() {
  if [[ "$(id -u)" -eq 0 ]]; then
    chown -R "$UNIX_USER:$UNIX_USER" "$TARGET_HERMES_HOME"
  fi
}

ensure_one_vault_link() {
  local link_path="$1"
  local target_path="$VAULT_DIR"
  local parent_dir=""

  parent_dir="$(dirname "$link_path")"
  mkdir -p "$parent_dir"

  if [[ -L "$link_path" ]]; then
    local existing_target=""
    existing_target="$(readlink "$link_path" || true)"
    if [[ "$existing_target" == "$target_path" ]]; then
      return 0
    fi
    rm -f "$link_path"
  elif [[ -e "$link_path" ]]; then
    echo "Vault shortcut path already exists and is not a symlink: $link_path" >&2
    return 1
  fi

  ln -s "$target_path" "$link_path"
  if [[ "$(id -u)" -eq 0 ]]; then
    chown -h "$UNIX_USER:$UNIX_USER" "$link_path" >/dev/null 2>&1 || true
  fi
}

ensure_user_vault_link() {
  ensure_one_vault_link "$TARGET_VAULT_LINK_PATH" || return 1
  ensure_one_vault_link "$TARGET_HERMES_HOME/Vault" || return 1
}

install_local_user_wrappers() {
  local wrapper_path="$TARGET_LOCAL_BIN_DIR/almanac-agent-hermes"
  local backup_wrapper="$TARGET_LOCAL_BIN_DIR/almanac-agent-configure-backup"

  mkdir -p "$TARGET_LOCAL_BIN_DIR"
  cat >"$wrapper_path" <<EOF
#!/usr/bin/env bash
set -euo pipefail
HERMES_HOME="\${HERMES_HOME:-$TARGET_HERMES_HOME}"
exec env HERMES_HOME="\$HERMES_HOME" "$RUNTIME_HERMES" "\$@"
EOF
  chmod 755 "$wrapper_path"

  cat >"$backup_wrapper" <<EOF
#!/usr/bin/env bash
set -euo pipefail
HERMES_HOME="\${HERMES_HOME:-$TARGET_HERMES_HOME}"
exec env HERMES_HOME="\$HERMES_HOME" "$SOURCE_REPO_DIR/bin/configure-agent-backup.sh" "\$HERMES_HOME" "\$@"
EOF
  chmod 755 "$backup_wrapper"

  if [[ "$(id -u)" -eq 0 ]]; then
    chown "$UNIX_USER:$UNIX_USER" "$wrapper_path" "$backup_wrapper"
  fi
}

ensure_gateway_home_channel_env() {
  local state_file="$TARGET_HERMES_HOME/state/almanac-enrollment.json"
  local env_file="$TARGET_HERMES_HOME/.env"
  if [[ ! -f "$state_file" ]]; then
    return 0
  fi

  python3 - "$state_file" "$env_file" <<'PY'
import json
import shlex
import sys
from pathlib import Path

state_path = Path(sys.argv[1])
env_path = Path(sys.argv[2])
try:
    state = json.loads(state_path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)

home_channel = state.get("home_channel")
if not isinstance(home_channel, dict):
    raise SystemExit(0)
platform = str(home_channel.get("platform") or "").strip().lower()
channel_id = str(home_channel.get("channel_id") or "").strip()
if not platform or not channel_id:
    raise SystemExit(0)

updates = {}
if platform == "discord":
    updates["DISCORD_HOME_CHANNEL"] = channel_id
    updates["DISCORD_HOME_CHANNEL_NAME"] = "Home"
elif platform == "telegram":
    updates["TELEGRAM_HOME_CHANNEL"] = channel_id
    updates["TELEGRAM_HOME_CHANNEL_NAME"] = "Home"
else:
    raise SystemExit(0)

existing = {}
order = []
if env_path.exists():
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        existing[key] = value.strip().strip("'\"")
        order.append(key)

for key, value in updates.items():
    if key not in order:
        order.append(key)
    existing[key] = value

env_path.parent.mkdir(parents=True, exist_ok=True)
lines = [f"{key}={shlex.quote(str(existing[key]))}" for key in order if key in existing]
env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

  if [[ "$(id -u)" -eq 0 ]]; then
    chown "$UNIX_USER:$UNIX_USER" "$env_file"
  fi
  chmod 600 "$env_file" || true
}

ensure_gateway_running_without_interrupting_active_turns() {
  local state=""
  if run_user_systemctl is-active almanac-user-agent-gateway.service >/dev/null 2>&1; then
    if [[ "$RESTART_GATEWAY" == "1" ]]; then
      try_user_systemctl "Hermes gateway runtime restart" restart almanac-user-agent-gateway.service
      return 0
    fi
    SERVICE_NOTES+=("    - Hermes gateway: already active; restart deferred to avoid interrupting user work")
    return 0
  fi
  state="$(
    run_user_systemctl is-enabled almanac-user-agent-gateway.service 2>/dev/null || true
  )"
  case "$(printf '%s' "$state" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')" in
    enabled|static|indirect)
      try_user_systemctl "Hermes gateway" start almanac-user-agent-gateway.service
      ;;
    *)
      SERVICE_NOTES+=("    - Hermes gateway: not enabled; start skipped")
      ;;
  esac
}

if target_can_access_repo; then
  run_as_target "$SOURCE_REPO_DIR/bin/install-almanac-skills.sh" "$SOURCE_REPO_DIR" "$TARGET_HERMES_HOME"
  run_as_target "$SOURCE_REPO_DIR/bin/install-almanac-plugins.sh" "$SOURCE_REPO_DIR" "$TARGET_HERMES_HOME"
  run_as_target "$SOURCE_REPO_DIR/bin/upsert-hermes-mcps.sh" "$TARGET_HERMES_HOME"
  run_as_target \
    "$RUNTIME_PYTHON" \
    "$SOURCE_REPO_DIR/python/almanac_headless_hermes_setup.py" \
    --identity-only \
    --bot-name "${BOT_NAME:-$UNIX_USER}" \
    --unix-user "$UNIX_USER" \
    --user-name "${USER_NAME:-$UNIX_USER}"
else
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "Source repo $SOURCE_REPO_DIR is not accessible to $UNIX_USER; rerun as root or use an accessible --repo-dir." >&2
    exit 1
  fi
  run_with_target_env_as_root "$SOURCE_REPO_DIR/bin/install-almanac-skills.sh" "$SOURCE_REPO_DIR" "$TARGET_HERMES_HOME"
  run_with_target_env_as_root "$SOURCE_REPO_DIR/bin/install-almanac-plugins.sh" "$SOURCE_REPO_DIR" "$TARGET_HERMES_HOME"
  run_with_target_env_as_root "$SOURCE_REPO_DIR/bin/upsert-hermes-mcps.sh" "$TARGET_HERMES_HOME"
  run_with_target_env_as_root \
    "$RUNTIME_PYTHON" \
    "$SOURCE_REPO_DIR/python/almanac_headless_hermes_setup.py" \
    --identity-only \
    --bot-name "${BOT_NAME:-$UNIX_USER}" \
    --unix-user "$UNIX_USER" \
    --user-name "${USER_NAME:-$UNIX_USER}"
  fix_target_ownership
fi

ensure_user_vault_link || true
install_local_user_wrappers
ensure_gateway_home_channel_env

try_user_systemctl "user manager daemon-reload" daemon-reload
try_user_systemctl "managed-memory refresh service" start almanac-user-agent-refresh.service
ensure_gateway_running_without_interrupting_active_turns
try_user_systemctl "Hermes dashboard/proxy" restart almanac-user-agent-dashboard.service almanac-user-agent-dashboard-proxy.service

cat <<EOF
Refreshed Almanac install for $UNIX_USER
  repo: $SOURCE_REPO_DIR
  home: $HOME_DIR
  hermes_home: $TARGET_HERMES_HOME
  mcp_urls:
    - almanac-mcp: $ALMANAC_MCP_URL
    - almanac-qmd: $ALMANAC_QMD_URL
$(if [[ -n "${CHUTES_MCP_URL:-}" ]]; then printf '    - chutes-kb: %s\n' "$CHUTES_MCP_URL"; fi)
EOF

if [[ ${#SERVICE_NOTES[@]} -gt 0 ]]; then
  echo "  service_actions:"
  printf '%s\n' "${SERVICE_NOTES[@]}"
fi
