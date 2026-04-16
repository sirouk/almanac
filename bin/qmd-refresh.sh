#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

run_embed="${QMD_RUN_EMBED:-0}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-embed)
      run_embed=0
      ;;
    --embed)
      run_embed=1
      ;;
    *)
      echo "Usage: $0 [--skip-embed|--embed]" >&2
      exit 2
      ;;
  esac
  shift
done

require_real_layout "qmd refresh"
ensure_layout
ensure_nvm

exec 9>"$QMD_REFRESH_LOCK_FILE"
flock 9

configure_qmd_collections
qmd --index "$QMD_INDEX_NAME" update

if [[ "$run_embed" == "1" ]]; then
  qmd --index "$QMD_INDEX_NAME" embed
fi
