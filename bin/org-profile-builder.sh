#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

umask 077
export PYTHONPATH="$REPO_DIR/python${PYTHONPATH:+:$PYTHONPATH}"
python_bin="${ALMANAC_ORG_PROFILE_BUILDER_PYTHON:-python3}"
exec "$python_bin" "$REPO_DIR/python/almanac_org_profile_builder.py" "$@"
