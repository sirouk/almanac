#!/usr/bin/env bash
set -euo pipefail

SOURCE_PATH="${BASH_SOURCE[0]-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SOURCE_PATH")" && pwd)"
if [[ -x "$SCRIPT_DIR/bin/init.sh" ]]; then
  exec "$SCRIPT_DIR/bin/init.sh" "$@"
fi

REPO_URL="${ALMANAC_INIT_REPO_URL:-https://github.com/sirouk/almanac.git}"
CACHE_DIR="${ALMANAC_INIT_CACHE_DIR:-$HOME/.cache/almanac-init}"
REPO_DIR="$CACHE_DIR/repo"

mkdir -p "$CACHE_DIR"
if [[ ! -d "$REPO_DIR/.git" ]]; then
  git clone --depth 1 "$REPO_URL" "$REPO_DIR"
else
  git -C "$REPO_DIR" pull --ff-only
fi

exec "$REPO_DIR/bin/init.sh" "$@"
