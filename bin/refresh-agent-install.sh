#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

usage() {
  cat >&2 <<'EOF'
Usage: refresh-agent-install.sh --unix-user <user> [--bot-name <name>] [--user-name <name>] [--hermes-home <path>] [--repo-dir <path>]

Re-sync Almanac skills/plugins into an enrolled user's Hermes home, upsert the
default Almanac MCP server entries without interactive prompts, refresh the
identity prompt, then kick the managed-memory refresh and restart agent-facing
services.
EOF
}

UNIX_USER=""
BOT_NAME=""
USER_NAME=""
HERMES_HOME_ARG=""
REPO_DIR_ARG=""

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
ALMANAC_QMD_URL="${ALMANAC_QMD_URL:-http://127.0.0.1:${QMD_MCP_PORT:-8181}/mcp}"

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
    return 0
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

run_user_systemctl start almanac-user-agent-refresh.service >/dev/null 2>&1 || true
run_user_systemctl restart almanac-user-agent-gateway.service >/dev/null 2>&1 || true
run_user_systemctl restart almanac-user-agent-dashboard.service almanac-user-agent-dashboard-proxy.service >/dev/null 2>&1 || true

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
