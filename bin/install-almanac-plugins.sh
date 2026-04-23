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

enable_one_plugin() {
  local plugin_name="$1"
  local config_file="$HERMES_HOME/config.yaml"

  python3 - "$config_file" "$plugin_name" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

config_file = Path(sys.argv[1])
plugin_name = str(sys.argv[2]).strip()
config_file.parent.mkdir(parents=True, exist_ok=True)

lines = config_file.read_text(encoding="utf-8").splitlines() if config_file.exists() else []


def is_top_level_key(line: str) -> bool:
    return bool(re.match(r"^[A-Za-z0-9_][A-Za-z0-9_-]*\s*:", line))


start = None
for index, line in enumerate(lines):
    if re.match(r"^plugins\s*:\s*(?:#.*)?$", line):
        start = index
        break

if start is None:
    before = lines
    after: list[str] = []
    block: list[str] = ["plugins:"]
else:
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].strip() and is_top_level_key(lines[index]):
            end = index
            break
    before = lines[:start]
    block = lines[start:end]
    after = lines[end:]

enabled: list[str] = []
disabled: list[str] = []
section = ""
for line in block[1:]:
    if re.match(r"^\s+enabled\s*:\s*(?:#.*)?$", line):
        section = "enabled"
        continue
    if re.match(r"^\s+disabled\s*:\s*(?:#.*)?$", line):
        section = "disabled"
        continue
    item_match = re.match(r"^\s+-\s+(.+?)\s*$", line)
    if item_match and section:
        item = item_match.group(1).strip().strip("\"'")
        if item:
            if section == "enabled":
                enabled.append(item)
            elif item != plugin_name:
                disabled.append(item)

if plugin_name not in enabled:
    enabled.append(plugin_name)
enabled = list(dict.fromkeys(enabled))
disabled = [item for item in dict.fromkeys(disabled) if item not in enabled]

new_block = ["plugins:", "  disabled:"]
new_block.extend(f"  - {item}" for item in disabled)
new_block.append("  enabled:")
new_block.extend(f"  - {item}" for item in enabled)

new_lines = before + new_block + after
config_file.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")
PY
}

for plugin_name in "$@"; do
  install_one_plugin "$plugin_name"
  enable_one_plugin "$plugin_name"
done
