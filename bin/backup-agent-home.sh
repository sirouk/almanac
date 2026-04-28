#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

usage() {
  echo "Usage: $0 <hermes-home>" >&2
}

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

HERMES_HOME_TARGET="$1"
STATE_FILE="$HERMES_HOME_TARGET/state/almanac-agent-backup.env"
GITHUB_API_BASE="${AGENT_BACKUP_GITHUB_API_BASE:-https://api.github.com}"
BACKUP_RECONCILE_PUSH_REQUIRED=1

if [[ "${GITHUB_API_BASE%/}" != "https://api.github.com" && "${ALMANAC_AGENT_BACKUP_ALLOW_TEST_GITHUB_API_BASE:-0}" != "1" ]]; then
  echo "Refusing non-default GitHub API base for backup visibility checks: $GITHUB_API_BASE" >&2
  echo "This override is reserved for tests; production backup safety must verify against https://api.github.com." >&2
  exit 1
fi

if [[ ! -f "$STATE_FILE" ]]; then
  echo "Agent backup is not configured for $HERMES_HOME_TARGET" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$STATE_FILE"

AGENT_BACKUP_REMOTE="${AGENT_BACKUP_REMOTE:-}"
AGENT_BACKUP_BRANCH="${AGENT_BACKUP_BRANCH:-main}"
AGENT_BACKUP_INCLUDE_SESSIONS="${AGENT_BACKUP_INCLUDE_SESSIONS:-1}"
AGENT_BACKUP_KEY_PATH="${AGENT_BACKUP_KEY_PATH:-$HOME/.ssh/almanac-agent-backup-ed25519}"
AGENT_BACKUP_KNOWN_HOSTS_FILE="${AGENT_BACKUP_KNOWN_HOSTS_FILE:-$HOME/.ssh/almanac-agent-backup-known_hosts}"
AGENT_BACKUP_REPO_DIR="${AGENT_BACKUP_REPO_DIR:-$HERMES_HOME_TARGET/state/agent-home-backup/repo}"

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

reconcile_backup_git_remote_branch() {
  local repo_dir="$1"
  local branch="$2"
  local remote_ref="origin/$branch"
  local remote_tracking_ref="refs/remotes/origin/$branch"
  local remote_head=""
  local archive_branch=""
  local timestamp=""
  local remote_short=""

  BACKUP_RECONCILE_PUSH_REQUIRED=1
  git -C "$repo_dir" fetch origin "$branch" >/dev/null 2>&1 || return 0

  if ! git -C "$repo_dir" show-ref --verify --quiet "$remote_tracking_ref"; then
    return 0
  fi

  if git -C "$repo_dir" merge-base --is-ancestor "$remote_ref" "$branch" >/dev/null 2>&1; then
    return 0
  fi

  if git -C "$repo_dir" merge-base --is-ancestor "$branch" "$remote_ref" >/dev/null 2>&1; then
    git -C "$repo_dir" merge --ff-only "$remote_ref" >/dev/null
    BACKUP_RECONCILE_PUSH_REQUIRED=0
    return 0
  fi

  if git -C "$repo_dir" merge-base "$branch" "$remote_ref" >/dev/null 2>&1; then
    echo "Agent backup remote branch '$remote_ref' has diverged from local '$branch'. Resolve the divergence in $repo_dir before retrying backup." >&2
    return 1
  fi

  remote_head="$(git -C "$repo_dir" rev-parse "$remote_ref")"
  remote_short="${remote_head:0:12}"
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  archive_branch="archive/${branch}-pre-align-${timestamp}-${remote_short}"

  echo "Agent backup remote branch '$remote_ref' has unrelated history; archiving it to '$archive_branch' before aligning '$branch' to local state." >&2
  git -C "$repo_dir" push origin "$remote_ref:refs/heads/$archive_branch" >/dev/null
  git -C "$repo_dir" push --force-with-lease="refs/heads/$branch:$remote_head" origin "$branch" >/dev/null
  BACKUP_RECONCILE_PUSH_REQUIRED=0
}

copy_path() {
  local rel_path="$1"
  local src="$HERMES_HOME_TARGET/$rel_path"
  local dst="$AGENT_BACKUP_REPO_DIR/$rel_path"
  [[ -e "$src" ]] || return 0
  mkdir -p "$(dirname "$dst")"
  if [[ -d "$src" ]]; then
    mkdir -p "$dst"
    if command -v rsync >/dev/null 2>&1; then
      rsync -a --delete "$src"/ "$dst"/
    else
      rm -rf "$dst"
      mkdir -p "$dst"
      cp -R "$src"/. "$dst"/
    fi
    return 0
  fi
  if command -v rsync >/dev/null 2>&1; then
    rsync -a "$src" "$dst"
  else
    rm -f "$dst"
    cp "$src" "$dst"
  fi
}

if [[ -z "$AGENT_BACKUP_REMOTE" ]]; then
  echo "Agent backup remote is not configured in $STATE_FILE" >&2
  exit 1
fi

owner_repo="$(github_owner_repo_from_remote "$AGENT_BACKUP_REMOTE")"
if [[ -z "$owner_repo" ]]; then
  echo "Per-user Hermes-home backups currently support GitHub SSH remotes only." >&2
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

mkdir -p "$AGENT_BACKUP_REPO_DIR"
if [[ ! -d "$AGENT_BACKUP_REPO_DIR/.git" ]]; then
  git -C "$AGENT_BACKUP_REPO_DIR" init -b "$AGENT_BACKUP_BRANCH" >/dev/null
fi

current_origin="$(git -C "$AGENT_BACKUP_REPO_DIR" remote get-url origin 2>/dev/null || true)"
if [[ -z "$current_origin" ]]; then
  git -C "$AGENT_BACKUP_REPO_DIR" remote add origin "$AGENT_BACKUP_REMOTE"
elif [[ "$current_origin" != "$AGENT_BACKUP_REMOTE" ]]; then
  git -C "$AGENT_BACKUP_REPO_DIR" remote set-url origin "$AGENT_BACKUP_REMOTE"
fi

find "$AGENT_BACKUP_REPO_DIR" -mindepth 1 -maxdepth 1 ! -name '.git' -exec rm -rf {} +

copy_path "SOUL.md"
copy_path "config.yaml"
copy_path "memories"
copy_path "skills"
copy_path "plugins"
copy_path "cron"
copy_path "state/almanac-identity-context.json"
copy_path "state/almanac-enrollment.json"
copy_path "state/almanac-prefill-messages.json"
copy_path "state/almanac-vault-reconciler.json"

if [[ "$AGENT_BACKUP_INCLUDE_SESSIONS" == "1" ]]; then
  copy_path "sessions"
fi

python3 - "$AGENT_BACKUP_REPO_DIR/MANIFEST.json" "$HERMES_HOME_TARGET" "$AGENT_BACKUP_INCLUDE_SESSIONS" <<'PY'
from __future__ import annotations

import json
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
payload = {
    "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    "hermes_home": sys.argv[2],
    "include_sessions": bool(int(sys.argv[3] or "0")),
    "host": socket.gethostname(),
    "unix_user": os.environ.get("USER") or "",
}
path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

git -C "$AGENT_BACKUP_REPO_DIR" add -A
if [[ -n "$(git -C "$AGENT_BACKUP_REPO_DIR" status --porcelain)" ]]; then
  GIT_AUTHOR_NAME="Almanac Agent Backup" \
  GIT_AUTHOR_EMAIL="almanac-agent@localhost" \
  GIT_COMMITTER_NAME="Almanac Agent Backup" \
  GIT_COMMITTER_EMAIL="almanac-agent@localhost" \
    git -C "$AGENT_BACKUP_REPO_DIR" commit -m "agent backup: $(date -u +%Y-%m-%dT%H:%M:%SZ)" >/dev/null
fi

BACKUP_GIT_REMOTE="$AGENT_BACKUP_REMOTE"
BACKUP_GIT_DEPLOY_KEY_PATH="$AGENT_BACKUP_KEY_PATH"
BACKUP_GIT_KNOWN_HOSTS_FILE="$AGENT_BACKUP_KNOWN_HOSTS_FILE"
prepare_backup_git_transport "$BACKUP_GIT_REMOTE"
reconcile_backup_git_remote_branch "$AGENT_BACKUP_REPO_DIR" "$AGENT_BACKUP_BRANCH"
if [[ "$BACKUP_RECONCILE_PUSH_REQUIRED" == "1" ]]; then
  git -C "$AGENT_BACKUP_REPO_DIR" push origin "$AGENT_BACKUP_BRANCH"
fi

echo "Backed up Hermes home from $HERMES_HOME_TARGET to $AGENT_BACKUP_REMOTE"
