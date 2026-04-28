#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

require_real_layout "Hermes docs sync"
ensure_layout

if [[ "${ALMANAC_HERMES_DOCS_SYNC_ENABLED:-1}" != "1" ]]; then
  echo "Hermes docs sync is disabled."
  exit 0
fi

repo_url="${ALMANAC_HERMES_DOCS_REPO_URL:-https://github.com/NousResearch/hermes-agent.git}"
repo_ref="${ALMANAC_HERMES_DOCS_REF:-${ALMANAC_HERMES_AGENT_REF:-main}}"
source_subdir="${ALMANAC_HERMES_DOCS_SOURCE_SUBDIR:-website/docs}"
checkout_dir="${ALMANAC_HERMES_DOCS_STATE_DIR:-$STATE_DIR/hermes-docs-src}"
target_dir="${ALMANAC_HERMES_DOCS_VAULT_DIR:-$VAULT_DIR/Agents_KB/hermes-agent-docs}"
canonical_target_dir="$VAULT_DIR/Agents_KB/hermes-agent-docs"
legacy_target_dir="$VAULT_DIR/Repos/hermes-agent-docs"
meta_file="$target_dir/.almanac-source.json"

if [[ "$target_dir" == "$canonical_target_dir" && -d "$legacy_target_dir" ]]; then
  mkdir -p "$(dirname "$target_dir")"
  if [[ ! -e "$target_dir" ]]; then
    mv "$legacy_target_dir" "$target_dir"
  else
    if command -v rsync >/dev/null 2>&1; then
      rsync -a --ignore-existing "$legacy_target_dir"/ "$target_dir"/
    else
      cp -Rn "$legacy_target_dir"/. "$target_dir"/
    fi
    rm -rf "$legacy_target_dir"
  fi
fi

mkdir -p "$checkout_dir" "$target_dir"

if [[ ! -d "$checkout_dir/.git" ]]; then
  rm -rf "$checkout_dir"
  git clone --depth 1 "$repo_url" "$checkout_dir" >/dev/null
else
  current_origin="$(git -C "$checkout_dir" remote get-url origin 2>/dev/null || true)"
  if [[ "$current_origin" != "$repo_url" ]]; then
    git -C "$checkout_dir" remote remove origin >/dev/null 2>&1 || true
    git -C "$checkout_dir" remote add origin "$repo_url"
  fi
fi

git -C "$checkout_dir" fetch --depth 1 origin "$repo_ref" >/dev/null
resolved_commit="$(git -C "$checkout_dir" rev-parse FETCH_HEAD)"
git -C "$checkout_dir" checkout --force --detach "$resolved_commit" >/dev/null

source_dir="$checkout_dir/$source_subdir"
if [[ ! -d "$source_dir" ]]; then
  echo "Hermes docs source directory is missing at $source_dir" >&2
  exit 1
fi

mkdir -p "$target_dir"
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete \
    --exclude='.git' \
    --exclude='.github' \
    "$source_dir"/ "$target_dir"/
else
  find "$target_dir" -mindepth 1 -maxdepth 1 ! -name '.almanac-source.json' -exec rm -rf {} +
  cp -R "$source_dir"/. "$target_dir"/
fi

python3 - "$meta_file" "$repo_url" "$repo_ref" "$resolved_commit" "$source_subdir" <<'PY'
import json
import sys
from pathlib import Path

meta_path = Path(sys.argv[1])
payload = {
    "repo_url": sys.argv[2],
    "repo_ref": sys.argv[3],
    "resolved_commit": sys.argv[4],
    "source_subdir": sys.argv[5],
}
meta_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

echo "Synced Hermes docs from $repo_url@$resolved_commit into $target_dir"
