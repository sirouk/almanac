#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <hermes-home> [runtime-dir]" >&2
  exit 2
fi

HERMES_HOME_ARG="$1"
RUNTIME_DIR_ARG="${2:-${RUNTIME_DIR:-}}"
PYTHON_BIN=""

if [[ -n "$RUNTIME_DIR_ARG" && -x "$RUNTIME_DIR_ARG/hermes-venv/bin/python3" ]]; then
  PYTHON_BIN="$RUNTIME_DIR_ARG/hermes-venv/bin/python3"
else
  PYTHON_BIN="$(command -v python3 || true)"
fi

if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  echo "python3 is required to migrate Hermes config." >&2
  exit 1
fi

mkdir -p "$HERMES_HOME_ARG"

HERMES_HOME="$HERMES_HOME_ARG" "$PYTHON_BIN" <<'PY'
from __future__ import annotations

try:
    from hermes_cli.config import check_config_version, migrate_config
except ModuleNotFoundError as exc:
    if exc.name == "hermes_cli":
        print("Hermes config migration skipped: hermes_cli is not installed")
        raise SystemExit(0)
    raise

before, latest = check_config_version()
result = migrate_config(interactive=False, quiet=True)
after, _ = check_config_version()

changed = bool(result.get("env_added") or result.get("config_added") or before != after)
if changed:
    print(f"Hermes config migrated: {before} -> {after}")
else:
    print(f"Hermes config already current: {after}/{latest}")

warnings = result.get("warnings") or []
if warnings:
    print(f"Hermes config migration warnings: {len(warnings)}")
PY
