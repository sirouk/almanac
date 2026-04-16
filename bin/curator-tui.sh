#!/usr/bin/env bash
# Godmode operator surface: drop the operator into a Curator-context Hermes TUI.
#
# TUI access is always available and cannot be disabled. If Discord or Telegram
# gateways are broken, this is the recovery path.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

require_real_layout "curator TUI"
ensure_layout

if [[ ! -d "$ALMANAC_CURATOR_HERMES_HOME" ]]; then
  echo "Curator Hermes home not found at $ALMANAC_CURATOR_HERMES_HOME" >&2
  echo "Run deploy.sh curator-setup to provision it." >&2
  exit 2
fi

HERMES_BIN="$RUNTIME_DIR/hermes-venv/bin/hermes"
if [[ ! -x "$HERMES_BIN" ]]; then
  echo "Curator Hermes binary not found at $HERMES_BIN" >&2
  echo "Run bootstrap-userland.sh first." >&2
  exit 2
fi

exec env HERMES_HOME="$ALMANAC_CURATOR_HERMES_HOME" "$HERMES_BIN" "$@"
