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
  set -- drive code terminal
fi

INSTALL_ARCLINK_PLUGINS_SKIP_HOOKS=1 \
  "$REPO_DIR/bin/install-arclink-plugins.sh" "$REPO_DIR" "$HERMES_HOME" "$@"
