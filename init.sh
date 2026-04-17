#!/usr/bin/env bash
set -euo pipefail

SOURCE_PATH="${BASH_SOURCE[0]-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SOURCE_PATH")" && pwd)"
LOCAL_REPO_DIR=""
if [[ -x "$SCRIPT_DIR/bin/init.sh" ]]; then
  LOCAL_REPO_DIR="$SCRIPT_DIR"
fi

MODE=""
FORWARD_ARGS=()
REPO_URL="${ALMANAC_INIT_REPO_URL:-https://github.com/sirouk/almanac.git}"
RAW_INIT_URL="${ALMANAC_INIT_RAW_URL:-https://raw.githubusercontent.com/sirouk/almanac/main/init.sh}"
CACHE_DIR="${ALMANAC_INIT_CACHE_DIR:-$HOME/.cache/almanac-init}"
REPO_DIR="$CACHE_DIR/repo"
TARGET_HOST="${ALMANAC_TARGET_HOST:-}"
TARGET_USER="${ALMANAC_TARGET_USER:-$(id -un 2>/dev/null || printf '')}"
PUBLIC_MCP_URL="${ALMANAC_PUBLIC_MCP_URL:-}"
PUBLIC_MCP_PATH="${ALMANAC_PUBLIC_MCP_PATH:-/almanac-mcp}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    agent|infra|update)
      if [[ -z "$MODE" ]]; then
        MODE="$1"
      else
        FORWARD_ARGS+=("$1")
      fi
      shift
      ;;
    --target-host)
      if [[ $# -lt 2 ]]; then
        echo "--target-host requires a hostname." >&2
        exit 2
      fi
      TARGET_HOST="$2"
      shift 2
      ;;
    --target-user)
      if [[ $# -lt 2 ]]; then
        echo "--target-user requires a username." >&2
        exit 2
      fi
      TARGET_USER="$2"
      shift 2
      ;;
    --public-mcp-url)
      if [[ $# -lt 2 ]]; then
        echo "--public-mcp-url requires a URL." >&2
        exit 2
      fi
      PUBLIC_MCP_URL="$2"
      shift 2
      ;;
    --public-mcp-path)
      if [[ $# -lt 2 ]]; then
        echo "--public-mcp-path requires a path." >&2
        exit 2
      fi
      PUBLIC_MCP_PATH="$2"
      shift 2
      ;;
    *)
      FORWARD_ARGS+=("$1")
      shift
      ;;
  esac
done

MODE="${MODE:-agent}"

current_os() {
  uname -s 2>/dev/null || printf 'unknown'
}

have_tty() {
  [[ -e /dev/tty ]] && (: </dev/tty) 2>/dev/null
}

remote_bootstrap_hint() {
  local host_example="${TARGET_HOST:-kor.tailnet.ts.net}"
  cat >&2 <<EOF
Remote enrollment from a non-Linux client needs the Almanac host.

Use one of these forms:
  curl -fsSL $RAW_INIT_URL | ALMANAC_TARGET_HOST=$host_example bash -s -- $MODE
  curl -fsSL $RAW_INIT_URL | bash -s -- $MODE --target-host $host_example

Note: ALMANAC_TARGET_HOST must be set for bash, not curl. This will not work:
  ALMANAC_TARGET_HOST=$host_example curl -fsSL ... | bash -s -- $MODE
EOF
}

prompt_tty() {
  local prompt="$1"
  local default="${2:-}"
  local answer=""

  if ! have_tty; then
    remote_bootstrap_hint
    return 1
  fi

  if [[ -n "$default" ]]; then
    printf '%s [%s]: ' "$prompt" "$default" >/dev/tty
  else
    printf '%s: ' "$prompt" >/dev/tty
  fi
  IFS= read -r answer </dev/tty || true
  if [[ -z "$answer" ]]; then
    answer="$default"
  fi
  printf '%s\n' "$answer"
}

ensure_repo_cache() {
  if [[ -n "$LOCAL_REPO_DIR" ]]; then
    REPO_DIR="$LOCAL_REPO_DIR"
    return 0
  fi

  mkdir -p "$CACHE_DIR"
  if [[ ! -d "$REPO_DIR/.git" ]]; then
    git clone --depth 1 "$REPO_URL" "$REPO_DIR"
  else
    git -C "$REPO_DIR" pull --ff-only
  fi
}

should_delegate_remote() {
  if [[ -n "$TARGET_HOST" ]]; then
    return 0
  fi

  if [[ "$MODE" == "agent" && "$(current_os)" != "Linux" ]]; then
    return 0
  fi

  return 1
}

exec_real_init() {
  local init_path="$1"
  shift

  if have_tty; then
    exec "$init_path" "$@" </dev/tty
  fi

  exec "$init_path" "$@"
}

build_remote_command() {
  local cmd=""
  local arg
  local bootstrap_url="$PUBLIC_MCP_URL"

  if [[ -z "$bootstrap_url" && -n "$TARGET_HOST" ]]; then
    bootstrap_url="https://${TARGET_HOST}${PUBLIC_MCP_PATH}"
  fi

  cmd+="export ALMANAC_INIT_REPO_URL=$(printf '%q' "$REPO_URL"); "
  cmd+="export ALMANAC_INIT_RAW_URL=$(printf '%q' "$RAW_INIT_URL"); "
  if [[ -n "$bootstrap_url" ]]; then
    cmd+="export ALMANAC_BOOTSTRAP_URL=$(printf '%q' "$bootstrap_url"); "
  fi
  cmd+="curl -fsSL \"\$ALMANAC_INIT_RAW_URL\" | bash -s -- $(printf '%q' "$MODE")"
  for arg in "$@"; do
    cmd+=" $(printf '%q' "$arg")"
  done

  printf '%s\n' "$cmd"
}

delegate_to_remote_host() {
  local ssh_target remote_cmd os_name

  os_name="$(current_os)"
  if [[ -z "$TARGET_HOST" ]]; then
    TARGET_HOST="$(prompt_tty "Target Almanac hostname")"
  fi
  if [[ -n "${ALMANAC_TARGET_USER:-}" ]]; then
    :
  elif [[ -z "$TARGET_USER" ]]; then
    TARGET_USER="$(prompt_tty "SSH user for $TARGET_HOST" "$(id -un 2>/dev/null || printf '')")"
  elif have_tty; then
    TARGET_USER="$(prompt_tty "SSH user for $TARGET_HOST" "$TARGET_USER")"
  fi

  if [[ -z "$TARGET_HOST" ]]; then
    echo "Target Almanac hostname is required." >&2
    exit 1
  fi

  if ! command -v ssh >/dev/null 2>&1; then
    echo "ssh is required to continue enrollment from $os_name." >&2
    exit 1
  fi

  ssh_target="$TARGET_HOST"
  if [[ -n "$TARGET_USER" ]]; then
    ssh_target="$TARGET_USER@$TARGET_HOST"
  fi
  remote_cmd="$(build_remote_command "$@")"

  cat >&2 <<EOF
Delegating Almanac $MODE to $ssh_target ...
The host-side enrollment flow will install the shared-host Hermes agent there.
Bootstrap approval will be requested against the Almanac control plane over:
  ${PUBLIC_MCP_URL:-https://${TARGET_HOST}${PUBLIC_MCP_PATH}}
EOF

  exec ssh -tt "$ssh_target" "$remote_cmd"
}

main() {
  if should_delegate_remote; then
    delegate_to_remote_host "${FORWARD_ARGS[@]}"
  fi

  ensure_repo_cache
  exec_real_init "$REPO_DIR/bin/init.sh" "$MODE" "${FORWARD_ARGS[@]}"
}

main "$@"
