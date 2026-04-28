#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <hermes-home> [runtime-dir]" >&2
  exit 2
fi

HERMES_HOME_ARG="$1"
RUNTIME_DIR_ARG="${2:-${RUNTIME_DIR:-}}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

runtime_candidates=()
if [[ -n "$RUNTIME_DIR_ARG" ]]; then
  runtime_candidates+=("$RUNTIME_DIR_ARG")
fi
if [[ -n "${ALMANAC_HERMES_BIN:-}" ]]; then
  runtime_candidates+=("$(cd "$(dirname "$ALMANAC_HERMES_BIN")/../.." 2>/dev/null && pwd -P || true)")
fi
runtime_candidates+=("$REPO_DIR/almanac-priv/state/runtime")

runtime_dir=""
for candidate in "${runtime_candidates[@]}"; do
  if [[ -z "$candidate" ]]; then
    continue
  fi
  if [[ -f "$candidate/hermes-agent-src/tools/skills_sync.py" && -d "$candidate/hermes-agent-src/skills" ]]; then
    runtime_dir="$candidate"
    break
  fi
done

if [[ -z "$runtime_dir" ]]; then
  echo "Hermes bundled skills source not available; skipping bundled skill sync." >&2
  exit 0
fi

python_bin="$runtime_dir/hermes-venv/bin/python3"
if [[ ! -x "$python_bin" ]]; then
  python_bin="$(command -v python3 || true)"
fi
if [[ -z "$python_bin" || ! -x "$python_bin" ]]; then
  echo "python3 is required to sync Hermes bundled skills." >&2
  exit 1
fi

env \
  HERMES_HOME="$HERMES_HOME_ARG" \
  HERMES_BUNDLED_SKILLS="$runtime_dir/hermes-agent-src/skills" \
  "$python_bin" "$runtime_dir/hermes-agent-src/tools/skills_sync.py"
