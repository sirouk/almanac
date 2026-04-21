#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <repo-dir> <hermes-home> [plugin-name ...]" >&2
  exit 2
fi

REPO_DIR="$1"
HERMES_HOME="$2"
shift 2

if [[ $# -eq 0 ]]; then
  set -- \
    almanac-managed-context
fi

PLUGINS_ROOT="$REPO_DIR/plugins/hermes-agent"
TARGET_ROOT="$HERMES_HOME/plugins"
mkdir -p "$TARGET_ROOT"

install_one_plugin() {
  local plugin_name="$1"
  local src_dir="$PLUGINS_ROOT/$plugin_name"
  local dst_dir="$TARGET_ROOT/$plugin_name"

  if [[ ! -f "$src_dir/plugin.yaml" || ! -f "$src_dir/__init__.py" ]]; then
    echo "Missing Almanac plugin source: expected plugin.yaml and __init__.py under $src_dir" >&2
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

  if [[ ! -f "$dst_dir/plugin.yaml" || ! -f "$dst_dir/__init__.py" ]]; then
    echo "Failed to install Almanac plugin into $dst_dir" >&2
    exit 1
  fi
}

for plugin_name in "$@"; do
  install_one_plugin "$plugin_name"
done
