#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

require_real_layout "vault backup"
ensure_layout

BACKUP_RECONCILE_PUSH_REQUIRED=1

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
    echo "Backup remote branch '$remote_ref' has diverged from local '$branch'. Resolve the divergence in $repo_dir before retrying backup." >&2
    return 1
  fi

  remote_head="$(git -C "$repo_dir" rev-parse "$remote_ref")"
  remote_short="${remote_head:0:12}"
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  archive_branch="archive/${branch}-pre-align-${timestamp}-${remote_short}"

  echo "Backup remote branch '$remote_ref' has unrelated history; archiving it to '$archive_branch' before aligning '$branch' to local state." >&2
  git -C "$repo_dir" push origin "$remote_ref:refs/heads/$archive_branch" >/dev/null
  git -C "$repo_dir" push --force-with-lease="refs/heads/$branch:$remote_head" origin "$branch" >/dev/null
  BACKUP_RECONCILE_PUSH_REQUIRED=0
}

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

while IFS= read -r git_marker; do
  [[ -n "$git_marker" ]] || continue
  repo_path="$(dirname "$git_marker")"
  if [[ "$repo_path" == "$ALMANAC_PRIV_DIR" ]]; then
    continue
  fi
  rel_path="$(path_relative_to_dir "$repo_path" "$ALMANAC_PRIV_DIR")"
  [[ -n "$rel_path" ]] || continue
  exclude_paths+=("$rel_path")
  git -C "$ALMANAC_PRIV_DIR" rm --cached -r --ignore-unmatch "$rel_path" >/dev/null 2>&1 || true
done < <(
  find "$ALMANAC_PRIV_DIR" -mindepth 2 \
    \( -type d -name .git -print -prune \) -o \
    \( -type f -name .git -print \) \
    2>/dev/null
)

backup_top_level_pathspecs=()
while IFS= read -r top_entry; do
  [[ -n "$top_entry" ]] || continue
  top_name="$(basename "$top_entry")"
  [[ "$top_name" == ".git" ]] && continue
  if git -C "$ALMANAC_PRIV_DIR" check-ignore -q -- "$top_name"; then
    git -C "$ALMANAC_PRIV_DIR" rm --cached -r --ignore-unmatch "$top_name" >/dev/null 2>&1 || true
    continue
  fi
  backup_top_level_pathspecs+=("$top_name")
done < <(
  find "$ALMANAC_PRIV_DIR" -mindepth 1 -maxdepth 1 -print 2>/dev/null
)

if (( ${#backup_top_level_pathspecs[@]} > 0 )); then
  backup_add_pathspecs=("${backup_top_level_pathspecs[@]}")
  if (( ${#exclude_paths[@]} > 0 )); then
    for rel_path in "${exclude_paths[@]}"; do
      if git -C "$ALMANAC_PRIV_DIR" check-ignore -q -- "$rel_path"; then
        continue
      fi
      backup_add_pathspecs+=(":(exclude)$rel_path")
    done
  fi
  git -C "$ALMANAC_PRIV_DIR" add -A -- "${backup_add_pathspecs[@]}"
fi

if ! git -C "$ALMANAC_PRIV_DIR" diff --cached --quiet --exit-code; then
  GIT_AUTHOR_NAME="$BACKUP_GIT_AUTHOR_NAME" \
  GIT_AUTHOR_EMAIL="$BACKUP_GIT_AUTHOR_EMAIL" \
  GIT_COMMITTER_NAME="$BACKUP_GIT_AUTHOR_NAME" \
  GIT_COMMITTER_EMAIL="$BACKUP_GIT_AUTHOR_EMAIL" \
    git -C "$ALMANAC_PRIV_DIR" commit -m "almanac-priv backup: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
fi

if [[ -n "$BACKUP_GIT_REMOTE" ]]; then
  ensure_backup_git_origin_remote "$ALMANAC_PRIV_DIR"
  prepare_backup_git_transport "$BACKUP_GIT_REMOTE"
  reconcile_backup_git_remote_branch "$ALMANAC_PRIV_DIR" "$BACKUP_GIT_BRANCH"
  if [[ "$BACKUP_RECONCILE_PUSH_REQUIRED" == "1" ]]; then
    # The steady-state backup path is a single-writer timer on this host, so a
    # normal non-force push is the right default after reconciliation.
    git -C "$ALMANAC_PRIV_DIR" push origin "$BACKUP_GIT_BRANCH"
  fi
fi
