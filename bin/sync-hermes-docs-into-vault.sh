#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

require_real_layout "Hermes docs sync"
ensure_layout

sync_arclink_docs_into_vault() {
  if [[ "${ARCLINK_DOCS_SYNC_ENABLED:-1}" != "1" ]]; then
    return 0
  fi

  local arclink_repo_dir=""
  local arclink_target_dir=""
  local arclink_legacy_target_dir=""
  local arclink_meta_file=""
  local arclink_resolved_commit=""
  local tmp_dir=""
  local source_path=""
  local target_path=""

  arclink_repo_dir="${ARCLINK_DOCS_REPO_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
  arclink_target_dir="${ARCLINK_DOCS_VAULT_DIR:-$VAULT_DIR/Agents_KB/arclink-docs}"
  arclink_legacy_target_dir="$VAULT_DIR/Repos/arclink-docs"
  arclink_meta_file="$arclink_target_dir/.arclink-source.json"

  if [[ "$arclink_target_dir" == "$VAULT_DIR/Agents_KB/arclink-docs" && -d "$arclink_legacy_target_dir" ]]; then
    mkdir -p "$(dirname "$arclink_target_dir")"
    if [[ ! -e "$arclink_target_dir" ]]; then
      mv "$arclink_legacy_target_dir" "$arclink_target_dir"
    else
      if command -v rsync >/dev/null 2>&1; then
        rsync -a --ignore-existing "$arclink_legacy_target_dir"/ "$arclink_target_dir"/
      else
        cp -Rn "$arclink_legacy_target_dir"/. "$arclink_target_dir"/
      fi
      rm -rf "$arclink_legacy_target_dir"
    fi
  fi

  if [[ ! -d "$arclink_repo_dir/docs/arclink" ]]; then
    echo "ArcLink docs source directory is missing at $arclink_repo_dir/docs/arclink" >&2
    return 0
  fi

  tmp_dir="$(mktemp -d)"
  mkdir -p "$tmp_dir"
  for source_path in \
    README.md \
    AGENTS.md \
    docs/API_REFERENCE.md \
    docs/DOC_STATUS.md \
    docs/hermes-qmd-config.yaml; do
    if [[ -f "$arclink_repo_dir/$source_path" ]]; then
      target_path="$tmp_dir/${source_path#docs/}"
      mkdir -p "$(dirname "$target_path")"
      cp "$arclink_repo_dir/$source_path" "$target_path"
    fi
  done
  cp -R "$arclink_repo_dir/docs/arclink" "$tmp_dir/arclink"
  if [[ -d "$arclink_repo_dir/docs/openapi" ]]; then
    cp -R "$arclink_repo_dir/docs/openapi" "$tmp_dir/openapi"
  fi

  mkdir -p "$arclink_target_dir"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
      --exclude='.git' \
      --exclude='.github' \
      "$tmp_dir"/ "$arclink_target_dir"/
  else
    find "$arclink_target_dir" -mindepth 1 -maxdepth 1 ! -name '.arclink-source.json' -exec rm -rf {} +
    cp -R "$tmp_dir"/. "$arclink_target_dir"/
  fi
  rm -rf "$tmp_dir"

  arclink_resolved_commit="$(git -C "$arclink_repo_dir" rev-parse HEAD 2>/dev/null || true)"
  python3 - "$arclink_meta_file" "$arclink_repo_dir" "$arclink_resolved_commit" <<'PY'
import json
import sys
from pathlib import Path

meta_path = Path(sys.argv[1])
payload = {
    "repo_dir": sys.argv[2],
    "resolved_commit": sys.argv[3],
    "source_paths": [
        "README.md",
        "AGENTS.md",
        "docs/API_REFERENCE.md",
        "docs/DOC_STATUS.md",
        "docs/arclink",
        "docs/openapi",
    ],
}
meta_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

  echo "Synced ArcLink docs from $arclink_repo_dir${arclink_resolved_commit:+@$arclink_resolved_commit} into $arclink_target_dir"
}

if [[ "${ARCLINK_HERMES_DOCS_SYNC_ENABLED:-1}" != "1" ]]; then
  echo "Hermes docs sync is disabled."
  sync_arclink_docs_into_vault
  exit 0
fi

repo_url="${ARCLINK_HERMES_DOCS_REPO_URL:-https://github.com/NousResearch/hermes-agent.git}"
repo_ref="${ARCLINK_HERMES_DOCS_REF:-${ARCLINK_HERMES_AGENT_REF:-main}}"
source_subdir="${ARCLINK_HERMES_DOCS_SOURCE_SUBDIR:-website/docs}"
checkout_dir="${ARCLINK_HERMES_DOCS_STATE_DIR:-$STATE_DIR/hermes-docs-src}"
target_dir="${ARCLINK_HERMES_DOCS_VAULT_DIR:-$VAULT_DIR/Agents_KB/hermes-agent-docs}"
canonical_target_dir="$VAULT_DIR/Agents_KB/hermes-agent-docs"
legacy_target_dir="$VAULT_DIR/Repos/hermes-agent-docs"
meta_file="$target_dir/.arclink-source.json"

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
  find "$target_dir" -mindepth 1 -maxdepth 1 ! -name '.arclink-source.json' -exec rm -rf {} +
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
sync_arclink_docs_into_vault
