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
    arclink-theme \
    arclink-managed-context \
    arclink-crew
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

backup_config_file_once() {
  local config_file="$HERMES_HOME/config.yaml"

  if [[ -f "$config_file" ]]; then
    cp -p "$config_file" "$config_file.arclink-pre-plugin-install.bak"
  fi
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

sync_dashboard_theme_config() {
  local theme_name="$1"
  local config_file="$HERMES_HOME/config.yaml"

  [[ -n "$theme_name" ]] || return 0

  python3 - "$config_file" "$theme_name" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

config_file = Path(sys.argv[1])
theme_name = sys.argv[2].strip()
if not theme_name:
    raise SystemExit(0)

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


start = None
for index, line in enumerate(lines):
    if re.match(r"^dashboard\s*:", line):
        start = index
        break

if start is None:
    block = ["dashboard:", f"  theme: {theme_name}"]
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

if not re.match(r"^dashboard\s*:\s*(?:#.*)?$", block[0]):
    block[0] = "dashboard:"

indent = child_indent(block)
prefix = " " * indent
theme_line = f"{prefix}theme: {theme_name}"
updated = False
new_block: list[str] = []
for line in block:
    if direct_child_key(line, indent) == "theme":
        comment = ""
        if "#" in line:
            comment = "  #" + line.split("#", 1)[1]
        new_block.append(theme_line + comment)
        updated = True
    else:
        new_block.append(line)

if not updated:
    insert_at = 1
    while insert_at < len(new_block) and (
        not new_block[insert_at].strip() or new_block[insert_at].lstrip().startswith("#")
    ):
        insert_at += 1
    new_block[insert_at:insert_at] = [theme_line]

config_file.write_text("\n".join(before + new_block + after).rstrip() + "\n", encoding="utf-8")
PY
}

sync_dashboard_hidden_plugins_config() {
  local config_file="${1:-$HERMES_HOME/config.yaml}"
  shift || true

  python3 - "$config_file" "$@" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

config_file = Path(sys.argv[1])
hidden_names = [item.strip() for item in sys.argv[2:] if item.strip()]
if not hidden_names:
    raise SystemExit(0)

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
        match = re.match(r"^(\s+)-\s*", line)
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
    if re.match(r"^dashboard\s*:", line):
        start = index
        break

if start is None:
    block = ["dashboard:", "  hidden_plugins:", *[f"  - {item}" for item in hidden_names]]
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
if not re.match(r"^dashboard\s*:\s*(?:#.*)?$", block[0]):
    block[0] = "dashboard:"

indent = child_indent(block)
prefix = " " * indent
hidden_index = None
hidden_end = len(block)
seen: set[str] = set()
for index, line in enumerate(block):
    key = direct_child_key(line, indent)
    if key == "hidden_plugins":
        hidden_index = index
        hidden_end = len(block)
        for scan_index in range(index + 1, len(block)):
            next_key = direct_child_key(block[scan_index], indent)
            if next_key:
                hidden_end = scan_index
                break
            item = list_item_name(block[scan_index])
            if item:
                seen.add(item)
        break

missing = [item for item in hidden_names if item not in seen]
if missing:
    additions = [f"{prefix}- {item}" for item in missing]
    if hidden_index is None:
        insert_at = 1
        while insert_at < len(block) and (
            not block[insert_at].strip() or block[insert_at].lstrip().startswith("#")
        ):
            insert_at += 1
        block[insert_at:insert_at] = [f"{prefix}hidden_plugins:", *additions]
    else:
        block[hidden_end:hidden_end] = additions

config_file.write_text("\n".join(before + block + after).rstrip() + "\n", encoding="utf-8")
PY
}

sync_dashboard_visible_plugins_config() {
  local config_file="${1:-$HERMES_HOME/config.yaml}"
  shift || true

  python3 - "$config_file" "$@" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

config_file = Path(sys.argv[1])
visible_names = {item.strip() for item in sys.argv[2:] if item.strip()}
if not visible_names or not config_file.exists():
    raise SystemExit(0)

lines = config_file.read_text(encoding="utf-8").splitlines()


def is_top_level_key(line: str) -> bool:
    return bool(re.match(r"^[A-Za-z0-9_][A-Za-z0-9_-]*\s*:", line))


def child_indent(block: list[str]) -> int:
    for line in block[1:]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.match(r"^(\s+)[A-Za-z0-9_][A-Za-z0-9_-]*\s*:", line)
        if match:
            return len(match.group(1).replace("\t", "  "))
        match = re.match(r"^(\s+)-\s*", line)
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
    if re.match(r"^dashboard\s*:", line):
        start = index
        break

if start is None:
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
        section = key if key == "hidden_plugins" else ""
    item = list_item_name(line)
    if item and section == "hidden_plugins" and item in visible_names:
        continue
    new_block.append(line)

config_file.write_text("\n".join(before + new_block + after).rstrip() + "\n", encoding="utf-8")
PY
}

plugin_dashboard_default_theme() {
  local manifest_file="$1"

  python3 - "$manifest_file" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

manifest_file = Path(sys.argv[1])
if not manifest_file.exists():
    raise SystemExit(0)

for line in manifest_file.read_text(encoding="utf-8").splitlines():
    match = re.match(r"^\s*(?:arclink_dashboard_default_theme|dashboard_default_theme)\s*:\s*(.*?)\s*(?:#.*)?$", line)
    if not match:
        continue
    value = match.group(1).strip().strip('"\'')
    if value:
        print(value)
    break
PY
}

render_dashboard_theme_file() {
  local src_file="$1"
  local dst_file="$2"
  local agent_label="${ARCLINK_DASHBOARD_AGENT_LABEL:-${ARCLINK_AGENT_NAME:-ArcLink Agent}}"
  local theme_label="${ARCLINK_DASHBOARD_THEME_LABEL:-ArcLink Signal Orange}"
  local accent_hex="${ARCLINK_DASHBOARD_ACCENT_HEX:-#FB5005}"

  python3 - "$src_file" "$dst_file" "$agent_label" "$theme_label" "$accent_hex" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
agent_label = sys.argv[3].strip() or "ArcLink Agent"
theme_label = sys.argv[4].strip() or "ArcLink Signal Orange"
accent_hex = sys.argv[5].strip() or "#FB5005"

text = src.read_text(encoding="utf-8")
text = text.replace("__ARCLINK_AGENT_LABEL__", json.dumps(agent_label)[1:-1])
text = text.replace("__ARCLINK_THEME_LABEL__", json.dumps(theme_label)[1:-1])
text = text.replace("__ARCLINK_THEME_ACCENT_HEX__", json.dumps(accent_hex)[1:-1])
dst.parent.mkdir(parents=True, exist_ok=True)
dst.write_text(text, encoding="utf-8")
dst.chmod(0o644)
PY
}

generate_arclink_theme_variants() {
  local theme_dir="$1"
  local base_file="$theme_dir/arclink.yaml"
  [[ -f "$base_file" ]] || return 0

  python3 - "$base_file" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

base = Path(sys.argv[1])
text = base.read_text(encoding="utf-8")
variants = {
    "arclink-violet": ("ArcLink Deep Violet", "#8B5CF6", "139, 92, 246"),
    "arclink-matrix": ("ArcLink Matrix Green", "#00E676", "0, 230, 118"),
    "arclink-blue": ("ArcLink Electric Blue", "#2075FE", "32, 117, 254"),
    "arclink-gold": ("ArcLink Solar Gold", "#FFD166", "255, 209, 102"),
    "arclink-crimson": ("ArcLink Crimson Pulse", "#FF3864", "255, 56, 100"),
}
for name, (label, hex_value, rgb_value) in variants.items():
    body = text
    body = body.replace("name: arclink", f"name: {name}", 1)
    body = body.replace('label: "ArcLink"', f'label: "{label}"', 1)
    body = body.replace(
        'description: "Carbon workspace with ArcLink signal orange, electric blue, and live-status green."',
        f'description: "Carbon ArcLink workspace with the {label} accent lane."',
        1,
    )
    body = body.replace("#FB5005", hex_value).replace("#fb5005", hex_value.lower())
    body = body.replace("251, 80, 5", rgb_value)
    (base.parent / f"{name}.yaml").write_text(body, encoding="utf-8")
PY
}

install_plugin_dashboard_themes() {
  local plugin_name="$1"
  local src_dir="$PLUGINS_ROOT/$plugin_name"
  local theme_dir="$HERMES_HOME/dashboard-themes"
  local candidate=""
  local theme_file=""

  for candidate in "$src_dir/dashboard-themes" "$src_dir/theme"; do
    [[ -d "$candidate" ]] || continue
    mkdir -p "$theme_dir"
    while IFS= read -r -d '' theme_file; do
      render_dashboard_theme_file "$theme_file" "$theme_dir/$(basename "$theme_file")"
    done < <(find "$candidate" -maxdepth 1 -type f \( -name '*.yaml' -o -name '*.yml' \) -print0 | sort -z)
  done
  if [[ "$plugin_name" == "arclink-theme" ]]; then
    generate_arclink_theme_variants "$theme_dir"
  fi

  plugin_dashboard_default_theme "$src_dir/plugin.yaml"
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
visible_dashboard_plugins=()
for plugin_name in "$@"; do
  normalized_plugin="$(normalize_plugin_name "$plugin_name")"
  normalized_plugins+=("$normalized_plugin")
  case "$normalized_plugin" in
    drive|code|terminal) visible_dashboard_plugins+=("$normalized_plugin") ;;
  esac
done

for plugin_name in "${normalized_plugins[@]}"; do
  install_one_plugin "$plugin_name"
done

dashboard_theme=""
for plugin_name in "${normalized_plugins[@]}"; do
  plugin_theme="$(install_plugin_dashboard_themes "$plugin_name")"
  if [[ -n "$plugin_theme" ]]; then
    dashboard_theme="$plugin_theme"
  fi
done
if [[ -n "${ARCLINK_DASHBOARD_THEME:-}" ]]; then
  dashboard_theme="$ARCLINK_DASHBOARD_THEME"
fi

backup_config_file_once
sync_plugin_config "${normalized_plugins[@]}"
sync_dashboard_theme_config "$dashboard_theme"
sync_dashboard_visible_plugins_config "$HERMES_HOME/config.yaml" "${visible_dashboard_plugins[@]}"
sync_dashboard_hidden_plugins_config "$HERMES_HOME/config.yaml" example

if [[ "${INSTALL_ARCLINK_PLUGINS_SKIP_HOOKS:-0}" != "1" ]]; then
  install_default_hooks
fi
