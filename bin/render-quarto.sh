#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

if [[ "$ENABLE_QUARTO" != "1" ]]; then
  echo "Quarto is disabled in config; skipping render."
  exit 0
fi

if ! command -v quarto >/dev/null 2>&1; then
  echo "quarto is not installed; skipping render."
  exit 0
fi

if [[ ! -f "$QUARTO_PROJECT_DIR/_quarto.yml" && ! -f "$QUARTO_PROJECT_DIR/_quarto.yaml" ]]; then
  echo "No Quarto project found at $QUARTO_PROJECT_DIR"
  exit 0
fi

mkdir -p "$QUARTO_OUTPUT_DIR"
quarto render "$QUARTO_PROJECT_DIR" --output-dir "$QUARTO_OUTPUT_DIR"
