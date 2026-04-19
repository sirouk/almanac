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

exclude_paths=()
candidate_paths=()
if [[ -n "${BACKUP_GIT_DEPLOY_KEY_PATH:-}" ]]; then
  candidate_paths+=("$BACKUP_GIT_DEPLOY_KEY_PATH" "${BACKUP_GIT_DEPLOY_KEY_PATH}.pub")
fi
if [[ -n "${BACKUP_GIT_KNOWN_HOSTS_FILE:-}" ]]; then
  candidate_paths+=("$BACKUP_GIT_KNOWN_HOSTS_FILE")
fi

for candidate in "${candidate_paths[@]}"; do
  [[ -n "$candidate" ]] || continue
  if path_is_within_dir "$candidate" "$ALMANAC_PRIV_DIR"; then
    rel_path="$(path_relative_to_dir "$candidate" "$ALMANAC_PRIV_DIR")"
    exclude_paths+=("$rel_path")
    git -C "$ALMANAC_PRIV_DIR" rm --cached --ignore-unmatch "$rel_path" >/dev/null 2>&1 || true
  fi
done

if (( ${#exclude_paths[@]} > 0 )); then
  add_cmd=(git -C "$ALMANAC_PRIV_DIR" add -A -- .)
  for rel_path in "${exclude_paths[@]}"; do
    add_cmd+=(":(exclude)$rel_path")
  done
  "${add_cmd[@]}"
else
  git -C "$ALMANAC_PRIV_DIR" add -A
fi

if [[ -n "$(git -C "$ALMANAC_PRIV_DIR" status --porcelain)" ]]; then
  GIT_AUTHOR_NAME="$BACKUP_GIT_AUTHOR_NAME" \
  GIT_AUTHOR_EMAIL="$BACKUP_GIT_AUTHOR_EMAIL" \
  GIT_COMMITTER_NAME="$BACKUP_GIT_AUTHOR_NAME" \
  GIT_COMMITTER_EMAIL="$BACKUP_GIT_AUTHOR_EMAIL" \
    git -C "$ALMANAC_PRIV_DIR" commit -m "almanac-priv backup: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
fi

if [[ -n "$BACKUP_GIT_REMOTE" ]]; then
  ensure_backup_git_origin_remote "$ALMANAC_PRIV_DIR"
  prepare_backup_git_transport "$BACKUP_GIT_REMOTE"
  git -C "$ALMANAC_PRIV_DIR" push origin "$BACKUP_GIT_BRANCH"
fi
