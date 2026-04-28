#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

echo "pdf-ingest-watch.sh is deprecated; forwarding to vault-watch.sh" >&2
exec "$SCRIPT_DIR/vault-watch.sh" "$@"
