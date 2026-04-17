#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$SCRIPT_DIR/../python${PYTHONPATH:+:$PYTHONPATH}"

exec python3 "$SCRIPT_DIR/../python/almanac_curator_discord_onboarding.py" "$@"
