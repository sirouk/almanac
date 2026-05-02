#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <repo-dir> <hermes-home> [skill-name ...]" >&2
  exit 2
fi

REPO_DIR="$1"
HERMES_HOME="$2"
shift 2

if [[ $# -eq 0 ]]; then
  set -- \
    arclink-qmd-mcp \
    arclink-vault-reconciler \
    arclink-first-contact \
    arclink-vaults \
    arclink-ssot \
    arclink-notion-knowledge \
    arclink-ssot-connect \
    arclink-notion-mcp \
    arclink-resources
fi

SKILLS_ROOT="$REPO_DIR/skills"
TARGET_ROOT="$HERMES_HOME/skills"
mkdir -p "$TARGET_ROOT"

install_one_skill() {
  local skill_name="$1"
  local src_dir="$SKILLS_ROOT/$skill_name"
  local dst_dir="$TARGET_ROOT/$skill_name"

  if [[ ! -f "$src_dir/SKILL.md" ]]; then
    echo "Missing ArcLink skill source: $src_dir/SKILL.md" >&2
    exit 1
  fi

  mkdir -p "$dst_dir"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete "$src_dir"/ "$dst_dir"/
  else
    rm -rf "$dst_dir"
    mkdir -p "$dst_dir"
    cp -R "$src_dir"/. "$dst_dir"/
  fi

  if [[ ! -f "$dst_dir/SKILL.md" ]]; then
    echo "Failed to install ArcLink skill into $dst_dir" >&2
    exit 1
  fi
}

for skill_name in "$@"; do
  install_one_skill "$skill_name"
done
