#!/usr/bin/env bash
# hermes-upgrade.sh - operator-facing alias for the Hermes-runtime upgrade.
#
# Kept as its own entry point because it's the most-frequently-bumped pin and
# the documentation already references this filename. The actual logic lives
# in component-upgrade.sh, which handles every kind in pins.json the same way.
#
# Usage:
#   hermes-upgrade.sh check
#   hermes-upgrade.sh apply [--ref REF] [--branch B] [--dry-run] [--skip-push] [--skip-upgrade]
#
# Bumping hermes-agent automatically also bumps hermes-docs (declared in
# pins.json with `inherits_from: hermes-agent`) so docs and runtime never
# drift apart.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/component-upgrade.sh" hermes-agent "$@"
