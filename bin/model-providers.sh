#!/usr/bin/env bash
# Read ArcLink model-provider defaults from config/model-providers.yaml.

__model_providers_repo_dir() {
  if [[ -n "${BOOTSTRAP_DIR:-}" ]]; then
    printf '%s\n' "$BOOTSTRAP_DIR"
    return 0
  fi
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  printf '%s/..\n' "$script_dir"
}

__model_provider_python() {
  local op="$1" preset="$2" raw="${3:-}" fallback="${4:-}" repo_dir=""
  repo_dir="$(__model_providers_repo_dir)"
  python3 - "$repo_dir" "$op" "$preset" "$raw" "$fallback" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

repo_dir = Path(sys.argv[1]).resolve()
op = sys.argv[2]
preset = sys.argv[3]
raw = sys.argv[4]
fallback = sys.argv[5]
sys.path.insert(0, str(repo_dir / "python"))

try:
    from arclink_model_providers import (
        provider_default_model,
        provider_preset_target,
        resolve_preset_target,
    )
    if op == "target":
        value = provider_preset_target(preset, repo_dir)
    elif op == "default-model":
        value = provider_default_model(preset, repo_dir)
    elif op == "resolve-target":
        value = resolve_preset_target(preset, raw, repo_dir)
    else:
        value = ""
except Exception:
    value = ""

print(value or fallback)
PY
}

model_provider_target_or_default() {
  __model_provider_python target "$1" "" "${2:-}"
}

model_provider_default_model_or_default() {
  __model_provider_python default-model "$1" "" "${2:-}"
}

model_provider_resolve_target_or_default() {
  __model_provider_python resolve-target "$1" "${2:-}" "${3:-}"
}
