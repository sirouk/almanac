#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

usage() {
  cat >&2 <<'EOF'
Usage: configure-agent-backup.sh <hermes-home> [--remote git@github.com:owner/repo.git] [--branch main] [--include-sessions 0|1] [--verify]

Configure a private GitHub backup for one enrolled user's Hermes home.
This uses a per-user read/write deploy key. Do not reuse the ArcLink upstream
code-push key or the shared arclink-priv backup key.
The backup snapshot is curated by default: SOUL, config, memories, sessions,
installed skills/plugins, and selected state. Secrets and logs stay
local to the host.

The first run prepares a pending backup state and prints a deploy key. After
that key is installed in GitHub with write access, rerun with --verify to prove
read/write access and activate the periodic Hermes cron backup job.
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
INCLUDE_SESSIONS="${AGENT_BACKUP_INCLUDE_SESSIONS:-1}"
KEY_PATH="${AGENT_BACKUP_KEY_PATH:-$HOME/.ssh/arclink-agent-backup-ed25519}"
KNOWN_HOSTS_FILE="${AGENT_BACKUP_KNOWN_HOSTS_FILE:-$HOME/.ssh/arclink-agent-backup-known_hosts}"
STATE_FILE="$HERMES_HOME_TARGET/state/arclink-agent-backup.env"
PENDING_STATE_FILE="$HERMES_HOME_TARGET/state/arclink-agent-backup.pending.env"
LOCAL_REPO_DIR="${AGENT_BACKUP_REPO_DIR:-$HERMES_HOME_TARGET/state/agent-home-backup/repo}"
GITHUB_API_BASE="${AGENT_BACKUP_GITHUB_API_BASE:-https://api.github.com}"
VERIFY_ONLY=0

if [[ "${GITHUB_API_BASE%/}" != "https://api.github.com" && "${ARCLINK_AGENT_BACKUP_ALLOW_TEST_GITHUB_API_BASE:-0}" != "1" ]]; then
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
    --verify)
      VERIFY_ONLY=1
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

if [[ "$VERIFY_ONLY" == "1" && -f "$PENDING_STATE_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$PENDING_STATE_FILE"
elif [[ "$VERIFY_ONLY" == "1" && -f "$STATE_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$STATE_FILE"
fi

if [[ "$VERIFY_ONLY" == "1" ]]; then
  REMOTE_URL="${AGENT_BACKUP_REMOTE:-$REMOTE_URL}"
  BRANCH_NAME="${AGENT_BACKUP_BRANCH:-$BRANCH_NAME}"
  INCLUDE_SESSIONS="${AGENT_BACKUP_INCLUDE_SESSIONS:-$INCLUDE_SESSIONS}"
  KEY_PATH="${AGENT_BACKUP_KEY_PATH:-$KEY_PATH}"
  KNOWN_HOSTS_FILE="${AGENT_BACKUP_KNOWN_HOSTS_FILE:-$KNOWN_HOSTS_FILE}"
  LOCAL_REPO_DIR="${AGENT_BACKUP_REPO_DIR:-$LOCAL_REPO_DIR}"
fi

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
        "User-Agent": "arclink-agent-backup-check",
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

if [[ -z "$REMOTE_URL" && "$VERIFY_ONLY" != "1" && -t 0 ]]; then
  owner_repo="$(prompt_tty "GitHub owner/repo for this user's private Hermes-home backup (blank to skip)" "")"
  if [[ -n "$owner_repo" ]]; then
    REMOTE_URL="git@github.com:${owner_repo}.git"
  fi
fi

if [[ -z "$REMOTE_URL" ]]; then
  if [[ "$VERIFY_ONLY" == "1" ]]; then
    echo "No pending or active backup remote is configured for $HERMES_HOME_TARGET; run this helper with --remote first." >&2
    exit 1
  fi
  echo "No backup remote configured; leaving per-user Hermes-home backup disabled."
  rm -f "$STATE_FILE" "$PENDING_STATE_FILE"
  "$SCRIPT_DIR/install-agent-cron-jobs.sh" "$SCRIPT_DIR/.." "$HERMES_HOME_TARGET" >/dev/null 2>&1 || true
  if [[ -S "/run/user/$(id -u)/bus" ]]; then
    env XDG_RUNTIME_DIR="/run/user/$(id -u)" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus" \
      systemctl --user disable --now arclink-user-agent-backup.timer >/dev/null 2>&1 || true
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
  key_comment="arclink-agent-backup@$(hostname -s 2>/dev/null || printf 'host')"
  ssh-keygen -q -t ed25519 -N '' -C "$key_comment" -f "$KEY_PATH"
fi
chmod 600 "$KEY_PATH"
chmod 644 "${KEY_PATH}.pub"

BACKUP_GIT_REMOTE="$REMOTE_URL"
BACKUP_GIT_DEPLOY_KEY_PATH="$KEY_PATH"
BACKUP_GIT_KNOWN_HOSTS_FILE="$KNOWN_HOSTS_FILE"
prepare_backup_git_transport "$BACKUP_GIT_REMOTE"

write_backup_state() {
  local target_file="$1"
  cat >"$target_file" <<EOF
AGENT_BACKUP_REMOTE=$(printf '%q' "$REMOTE_URL")
AGENT_BACKUP_BRANCH=$(printf '%q' "$BRANCH_NAME")
AGENT_BACKUP_INCLUDE_SESSIONS=$(printf '%q' "$INCLUDE_SESSIONS")
AGENT_BACKUP_KEY_PATH=$(printf '%q' "$KEY_PATH")
AGENT_BACKUP_KNOWN_HOSTS_FILE=$(printf '%q' "$KNOWN_HOSTS_FILE")
AGENT_BACKUP_REPO_DIR=$(printf '%q' "$LOCAL_REPO_DIR")
EOF
  chmod 600 "$target_file"
}

disable_legacy_backup_timer() {
  local legacy_timer="$HOME/.config/systemd/user/arclink-user-agent-backup.timer"
  local runtime_dir="" bus_addr=""
  if [[ -S "/run/user/$(id -u)/bus" ]]; then
    runtime_dir="/run/user/$(id -u)"
    bus_addr="unix:path=$runtime_dir/bus"
    env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="$bus_addr" \
      systemctl --user daemon-reload >/dev/null
    env XDG_RUNTIME_DIR="$runtime_dir" DBUS_SESSION_BUS_ADDRESS="$bus_addr" \
      systemctl --user disable --now arclink-user-agent-backup.timer >/dev/null 2>&1 || true
  fi
  rm -f "$legacy_timer"
}

install_backup_cron_job() {
  local output=""
  if [[ ! -x "$SCRIPT_DIR/install-agent-cron-jobs.sh" ]]; then
    echo "Hermes cron job installer is missing at $SCRIPT_DIR/install-agent-cron-jobs.sh" >&2
    return 1
  fi
  output="$("$SCRIPT_DIR/install-agent-cron-jobs.sh" "$SCRIPT_DIR/.." "$HERMES_HOME_TARGET")"
  printf 'Hermes cron backup job installed: %s\n' "$output"
}

run_backup_cron_script_once() {
  local cron_script="$HERMES_HOME_TARGET/scripts/arclink_agent_backup.py"
  if [[ -f "$cron_script" ]]; then
    env HERMES_HOME="$HERMES_HOME_TARGET" python3 "$cron_script" >/dev/null 2>&1 || true
  fi
}

activate_backup_scheduler() {
  install_backup_cron_job
  disable_legacy_backup_timer
  run_backup_cron_script_once
}

verify_backup_git_access() {
  local tmp_dir="" output="" write_ref="refs/heads/arclink-agent-backup-write-check"

  echo "Verifying agent backup deploy-key read access with git ls-remote..."
  if ! output="$(git ls-remote "$REMOTE_URL" HEAD 2>&1)"; then
    echo "$output" >&2
    echo "Agent backup deploy-key read check failed for $REMOTE_URL." >&2
    return 1
  fi
  echo "Read check passed."

  tmp_dir="$(mktemp -d)"
  if ! (
    set -e
    git -C "$tmp_dir" init -b arclink-agent-backup-write-check >/dev/null
    git -C "$tmp_dir" config user.name "ArcLink Agent Backup Key Check"
    git -C "$tmp_dir" config user.email "arclink-agent-backup-check@localhost"
    printf 'ArcLink agent backup write check\n' >"$tmp_dir/README.md"
    git -C "$tmp_dir" add README.md
    git -C "$tmp_dir" commit -m "ArcLink agent backup write check" >/dev/null
  ); then
    rm -rf "$tmp_dir"
    echo "Failed to prepare a temporary dry-run push repo for agent backup verification." >&2
    return 1
  fi

  echo "Verifying agent backup deploy-key write access with git push --dry-run..."
  if ! output="$(git -C "$tmp_dir" push --dry-run "$REMOTE_URL" "HEAD:$write_ref" 2>&1)"; then
    rm -rf "$tmp_dir"
    echo "$output" >&2
    echo "Agent backup deploy-key write check failed for $REMOTE_URL." >&2
    echo "Make sure the deploy key is added to the private repo and Allow write access is enabled." >&2
    return 1
  fi
  rm -rf "$tmp_dir"
  echo "Write check passed (dry-run only; no branch or commit was pushed)."
}

if [[ "$VERIFY_ONLY" == "1" ]]; then
  verify_backup_git_access
  write_backup_state "$STATE_FILE"
  rm -f "$PENDING_STATE_FILE"
  activate_backup_scheduler
  cat <<EOF
Activated private Hermes-home backup
  hermes_home: $HERMES_HOME_TARGET
  remote: $REMOTE_URL
  branch: $BRANCH_NAME
  include_sessions: $INCLUDE_SESSIONS
  state_file: $STATE_FILE
  scheduler: Hermes cron job every 4 hours
EOF
  exit 0
fi

write_backup_state "$PENDING_STATE_FILE"

cat <<EOF
Prepared private Hermes-home backup
  hermes_home: $HERMES_HOME_TARGET
  remote: $REMOTE_URL
  branch: $BRANCH_NAME
  include_sessions: $INCLUDE_SESSIONS
  pending_state_file: $PENDING_STATE_FILE
  deploy_key_public:
$(sed 's/^/    /' "${KEY_PATH}.pub")

Add that public key to the private repository as a deploy key with write access.
After GitHub accepts the key, run:
  $0 $(printf '%q' "$HERMES_HOME_TARGET") --verify
This is a separate per-user backup key; do not reuse the ArcLink upstream code-push key or the shared arclink-priv backup key.
Session transcripts are included by default; prepare this helper with --include-sessions 0 if this repo should only hold the core soul/config/memory snapshot.
EOF
