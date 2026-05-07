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
    drive \
    code \
    terminal \
    arclink-managed-context
fi

PLUGINS_ROOT="$REPO_DIR/plugins/hermes-agent"
TARGET_ROOT="$HERMES_HOME/plugins"
HOOKS_ROOT="$REPO_DIR/hooks/hermes-agent"
TARGET_HOOKS_ROOT="$HERMES_HOME/hooks"
LEGACY_PLUGIN_NAMES=(
  arclink-code-space
  arclink-knowledge-vault
  arclink-code
  arclink-drive
  arclink-terminal
)
mkdir -p "$TARGET_ROOT"

normalize_plugin_name() {
  case "$1" in
    arclink-code|code|codespace|code-space|arclink-code-space) printf '%s\n' "code" ;;
    arclink-drive|knowledge-vault|arclink-knowledge-vault) printf '%s\n' "drive" ;;
    arclink-terminal) printf '%s\n' "terminal" ;;
    *) printf '%s\n' "$1" ;;
  esac
}

cleanup_legacy_plugins() {
  local legacy_name=""

  for legacy_name in "${LEGACY_PLUGIN_NAMES[@]}"; do
    rm -rf "$TARGET_ROOT/$legacy_name"
  done
}

sync_plugin_config() {
  local config_file="$HERMES_HOME/config.yaml"

  python3 - "$config_file" "${LEGACY_PLUGIN_NAMES[@]}" -- "$@" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

config_file = Path(sys.argv[1])
separator = sys.argv.index("--")
legacy_names = {item.strip() for item in sys.argv[2:separator] if item.strip()}
enable_names = [item.strip() for item in sys.argv[separator + 1 :] if item.strip()]
enable_set = set(enable_names)
remove_from_disabled = legacy_names | enable_set
remove_from_enabled = legacy_names
config_file.parent.mkdir(parents=True, exist_ok=True)
lines = config_file.read_text(encoding="utf-8").splitlines() if config_file.exists() else []


def is_top_level_key(line: str) -> bool:
    return bool(re.match(r"^[A-Za-z0-9_][A-Za-z0-9_-]*\s*:", line))


def child_indent(block: list[str]) -> int:
    for line in block[1:]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.match(r"^(\s+)[A-Za-z0-9_][A-Za-z0-9_-]*\s*:", line)
        if match:
            return len(match.group(1).replace("\t", "  "))
    return 2


def direct_child_key(line: str, indent: int) -> str:
    match = re.match(r"^(\s+)([A-Za-z0-9_][A-Za-z0-9_-]*)\s*:", line)
    if not match:
        return ""
    return match.group(2) if len(match.group(1).replace("\t", "  ")) == indent else ""


def list_item_name(line: str) -> str:
    match = re.match(r"^\s*-\s*(.+?)\s*$", line)
    if not match:
        return ""
    return match.group(1).split("#", 1)[0].strip().strip("\"'")


start = None
for index, line in enumerate(lines):
    if re.match(r"^plugins\s*:\s*(?:#.*)?$", line):
        start = index
        break

if start is None:
    block = ["plugins:", "  disabled:", "  enabled:"]
    for item in enable_names:
        block.append(f"  - {item}")
    config_file.write_text("\n".join(lines + block).rstrip() + "\n", encoding="utf-8")
    raise SystemExit(0)

end = len(lines)
for index in range(start + 1, len(lines)):
    if lines[index].strip() and is_top_level_key(lines[index]):
        end = index
        break

before = lines[:start]
block = lines[start:end]
after = lines[end:]
indent = child_indent(block)
section = ""
new_block: list[str] = []
for line in block:
    key = direct_child_key(line, indent)
    if key:
        section = key if key in {"enabled", "disabled"} else ""
    item = list_item_name(line)
    if item and section == "enabled" and item in remove_from_enabled:
        continue
    if item and section == "disabled" and item in remove_from_disabled:
        continue
    new_block.append(line)

enabled_index = None
enabled_end = len(new_block)
enabled_seen: set[str] = set()
for index, line in enumerate(new_block):
    key = direct_child_key(line, indent)
    if key == "enabled":
        enabled_index = index
        enabled_end = len(new_block)
        for scan_index in range(index + 1, len(new_block)):
            next_key = direct_child_key(new_block[scan_index], indent)
            if next_key:
                enabled_end = scan_index
                break
            item = list_item_name(new_block[scan_index])
            if item:
                enabled_seen.add(item)
        break

missing = [item for item in enable_names if item not in enabled_seen]
if missing:
    prefix = " " * indent
    additions = [f"{prefix}- {item}" for item in missing]
    if enabled_index is None:
        new_block.extend([f"{prefix}enabled:", *additions])
    else:
        new_block[enabled_end:enabled_end] = additions

config_file.write_text("\n".join(before + new_block + after).rstrip() + "\n", encoding="utf-8")
PY
}

install_one_plugin() {
  local plugin_name
  plugin_name="$(normalize_plugin_name "$1")"
  local src_dir="$PLUGINS_ROOT/$plugin_name"
  local dst_dir="$TARGET_ROOT/$plugin_name"

  if [[ ! -f "$src_dir/plugin.yaml" || ! -f "$src_dir/__init__.py" ]]; then
    echo "Missing Hermes plugin source: expected plugin.yaml and __init__.py under $src_dir" >&2
    exit 1
  fi

  mkdir -p "$dst_dir"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
      --exclude='__pycache__/' \
      --exclude='*.pyc' \
      --exclude='*.pyo' \
      --exclude='.pytest_cache/' \
      --exclude='.mypy_cache/' \
      --exclude='.ruff_cache/' \
      --exclude='.DS_Store' \
      "$src_dir"/ "$dst_dir"/
  else
    rm -rf "$dst_dir"
    mkdir -p "$dst_dir"
    cp -R "$src_dir"/. "$dst_dir"/
    find "$dst_dir" \
      \( -type d \( -name '__pycache__' -o -name '.pytest_cache' -o -name '.mypy_cache' -o -name '.ruff_cache' \) -prune -exec rm -rf {} + \) \
      -o \( -type f \( -name '*.pyc' -o -name '*.pyo' -o -name '.DS_Store' \) -delete \)
  fi

  if [[ ! -f "$dst_dir/plugin.yaml" || ! -f "$dst_dir/__init__.py" ]]; then
    echo "Failed to install Hermes plugin into $dst_dir" >&2
    exit 1
  fi
}

install_default_hooks() {
  local hook_name="arclink-telegram-start"
  local src_dir="$HOOKS_ROOT/$hook_name"
  local dst_dir="$TARGET_HOOKS_ROOT/$hook_name"

  if [[ ! -f "$src_dir/HOOK.yaml" || ! -f "$src_dir/handler.py" ]]; then
    return 0
  fi

  mkdir -p "$TARGET_HOOKS_ROOT" "$dst_dir"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete "$src_dir"/ "$dst_dir"/
  else
    rm -rf "$dst_dir"
    mkdir -p "$dst_dir"
    cp -R "$src_dir"/. "$dst_dir"/
  fi
}

cleanup_legacy_plugins

normalized_plugins=()
for plugin_name in "$@"; do
  normalized_plugins+=("$(normalize_plugin_name "$plugin_name")")
done

for plugin_name in "${normalized_plugins[@]}"; do
  install_one_plugin "$plugin_name"
done
sync_plugin_config "${normalized_plugins[@]}"

if [[ "${INSTALL_ARCLINK_PLUGINS_SKIP_HOOKS:-0}" != "1" ]]; then
  install_default_hooks
fi
