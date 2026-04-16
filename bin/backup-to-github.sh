#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

require_real_layout "vault backup"
ensure_layout

if [[ ! -d "$ALMANAC_PRIV_DIR/.git" ]]; then
  git -C "$ALMANAC_PRIV_DIR" init -b "$BACKUP_GIT_BRANCH"
fi

git -C "$ALMANAC_PRIV_DIR" add -A

if [[ -n "$(git -C "$ALMANAC_PRIV_DIR" status --porcelain)" ]]; then
  GIT_AUTHOR_NAME="$BACKUP_GIT_AUTHOR_NAME" \
  GIT_AUTHOR_EMAIL="$BACKUP_GIT_AUTHOR_EMAIL" \
  GIT_COMMITTER_NAME="$BACKUP_GIT_AUTHOR_NAME" \
  GIT_COMMITTER_EMAIL="$BACKUP_GIT_AUTHOR_EMAIL" \
    git -C "$ALMANAC_PRIV_DIR" commit -m "almanac-priv backup: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
fi

if [[ -n "$BACKUP_GIT_REMOTE" ]]; then
  if git -C "$ALMANAC_PRIV_DIR" remote get-url origin >/dev/null 2>&1; then
    git -C "$ALMANAC_PRIV_DIR" remote set-url origin "$BACKUP_GIT_REMOTE"
  else
    git -C "$ALMANAC_PRIV_DIR" remote add origin "$BACKUP_GIT_REMOTE"
  fi
  git -C "$ALMANAC_PRIV_DIR" push origin "$BACKUP_GIT_BRANCH"
fi
