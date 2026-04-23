#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

usage() {
  cat >&2 <<'EOF'
Usage: configure-agent-backup.sh <hermes-home> [--remote git@github.com:owner/repo.git] [--branch main] [--include-sessions 0|1]

Configure a private GitHub backup for one enrolled user's Hermes home.
The backup snapshot is curated by default: SOUL, config, memories, installed
skills/plugins, selected state, and optionally sessions. Secrets and logs stay
local to the host.
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

HERMES_HOME_TARGET="$1"
shift

REMOTE_URL="${AGENT_BACKUP_REMOTE:-}"
BRANCH_NAME="${AGENT_BACKUP_BRANCH:-main}"
INCLUDE_SESSIONS="${AGENT_BACKUP_INCLUDE_SESSIONS:-0}"
KEY_PATH="${AGENT_BACKUP_KEY_PATH:-$HOME/.ssh/almanac-agent-backup-ed25519}"
KNOWN_HOSTS_FILE="${AGENT_BACKUP_KNOWN_HOSTS_FILE:-$HOME/.ssh/almanac-agent-backup-known_hosts}"
STATE_FILE="$HERMES_HOME_TARGET/state/almanac-agent-backup.env"
LOCAL_REPO_DIR="${AGENT_BACKUP_REPO_DIR:-$HERMES_HOME_TARGET/state/agent-home-backup/repo}"
GITHUB_API_BASE="${AGENT_BACKUP_GITHUB_API_BASE:-https://api.github.com}"

if [[ "${GITHUB_API_BASE%/}" != "https://api.github.com" && "${ALMANAC_AGENT_BACKUP_ALLOW_TEST_GITHUB_API_BASE:-0}" != "1" ]]; then
  echo "Refusing non-default GitHub API base for backup visibility checks: $GITHUB_API_BASE" >&2
  echo "This override is reserved for tests; production backup safety must verify against https://api.github.com." >&2
  exit 1
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --remote)
      REMOTE_URL="${2:-}"
      shift 2
      ;;
    --branch)
      BRANCH_NAME="${2:-main}"
      shift 2
      ;;
    --include-sessions)
      INCLUDE_SESSIONS="${2:-1}"
      shift 2
      ;;
    --key-path)
      KEY_PATH="${2:-}"
      shift 2
      ;;
    --known-hosts)
      KNOWN_HOSTS_FILE="${2:-}"
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

prompt_tty() {
  local prompt="$1"
  local default="${2:-}"
  local answer=""
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

github_owner_repo_from_remote() {
  local remote="${1:-}"
  local owner_repo=""
  case "$remote" in
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
  printf '%s\n' "$owner_repo"
}

github_repo_visibility() {
  local owner_repo="${1:-}"
  python3 - "$GITHUB_API_BASE" "$owner_repo" <<'PY'
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
        "User-Agent": "almanac-agent-backup-check",
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

if [[ ! -d "$HERMES_HOME_TARGET" ]]; then
  echo "Hermes home not found at $HERMES_HOME_TARGET" >&2
  exit 1
fi

mkdir -p "$(dirname "$STATE_FILE")" "$(dirname "$KEY_PATH")" "$(dirname "$KNOWN_HOSTS_FILE")"

if [[ -z "$REMOTE_URL" && -t 0 ]]; then
  owner_repo="$(prompt_tty "GitHub owner/repo for a private Hermes-home backup (blank to skip)" "")"
  if [[ -n "$owner_repo" ]]; then
    REMOTE_URL="git@github.com:${owner_repo}.git"
  fi
fi

if [[ -z "$REMOTE_URL" ]]; then
  echo "No backup remote configured; leaving per-user Hermes-home backup disabled."
  rm -f "$STATE_FILE"
  if [[ -S "/run/user/$(id -u)/bus" ]]; then
    env XDG_RUNTIME_DIR="/run/user/$(id -u)" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus" \
      systemctl --user disable --now almanac-user-agent-backup.timer >/dev/null 2>&1 || true
  fi
  exit 0
fi

owner_repo="$(github_owner_repo_from_remote "$REMOTE_URL")"
if [[ -z "$owner_repo" ]]; then
  echo "Per-user Hermes-home backups currently support GitHub SSH remotes only." >&2
  echo "Use a remote like git@github.com:owner/private-repo.git" >&2
  exit 1
fi

visibility="$(github_repo_visibility "$owner_repo")"
if [[ "$visibility" == "public" ]]; then
  echo "Refusing to back up a Hermes home to a public GitHub repository: $owner_repo" >&2
  exit 1
fi
if [[ "$visibility" == error:* ]]; then
  echo "Could not verify GitHub visibility for $owner_repo ($visibility)." >&2
  exit 1
fi

if [[ ! -f "$KEY_PATH" ]]; then
  key_comment="almanac-agent-backup@$(hostname -s 2>/dev/null || printf 'host')"
  ssh-keygen -q -t ed25519 -N '' -C "$key_comment" -f "$KEY_PATH"
fi
chmod 600 "$KEY_PATH"
chmod 644 "${KEY_PATH}.pub"

BACKUP_GIT_REMOTE="$REMOTE_URL"
BACKUP_GIT_DEPLOY_KEY_PATH="$KEY_PATH"
BACKUP_GIT_KNOWN_HOSTS_FILE="$KNOWN_HOSTS_FILE"
prepare_backup_git_transport "$BACKUP_GIT_REMOTE"

cat >"$STATE_FILE" <<EOF
AGENT_BACKUP_REMOTE=$(printf '%q' "$REMOTE_URL")
AGENT_BACKUP_BRANCH=$(printf '%q' "$BRANCH_NAME")
AGENT_BACKUP_INCLUDE_SESSIONS=$(printf '%q' "$INCLUDE_SESSIONS")
AGENT_BACKUP_KEY_PATH=$(printf '%q' "$KEY_PATH")
AGENT_BACKUP_KNOWN_HOSTS_FILE=$(printf '%q' "$KNOWN_HOSTS_FILE")
AGENT_BACKUP_REPO_DIR=$(printf '%q' "$LOCAL_REPO_DIR")
EOF
chmod 600 "$STATE_FILE"

if [[ -S "/run/user/$(id -u)/bus" ]]; then
  runtime_dir="/run/user/$(id -u)"
  bus_addr="unix:path=$runtime_dir/bus"
  env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="$bus_addr" \
    systemctl --user daemon-reload >/dev/null
  if env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="$bus_addr" \
      systemctl --user cat almanac-user-agent-backup.timer >/dev/null 2>&1; then
    env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="$bus_addr" \
      systemctl --user enable almanac-user-agent-backup.timer >/dev/null
    env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="$bus_addr" \
      systemctl --user restart almanac-user-agent-backup.timer >/dev/null
    env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="$bus_addr" \
      systemctl --user start almanac-user-agent-backup.service >/dev/null 2>&1 || true
  else
    echo "Backup timer unit is not installed in this Hermes home yet; rerun refresh-agent-install.sh after enrollment to activate periodic backups." >&2
  fi
fi

cat <<EOF
Configured private Hermes-home backup
  hermes_home: $HERMES_HOME_TARGET
  remote: $REMOTE_URL
  branch: $BRANCH_NAME
  include_sessions: $INCLUDE_SESSIONS
  state_file: $STATE_FILE
  deploy_key_public:
$(sed 's/^/    /' "${KEY_PATH}.pub")

Add that public key to the private repository as a deploy key with write access.
Session transcripts stay out of the backup unless you rerun this helper with --include-sessions 1.
EOF
