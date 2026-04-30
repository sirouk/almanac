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

run_qmd_embed() {
  local timeout_seconds="${QMD_EMBED_TIMEOUT_SECONDS:-0}"
  local rc=0
  local -a embed_cmd=(qmd --index "$QMD_INDEX_NAME" embed)

  case "${QMD_EMBED_PROVIDER:-local}" in
    endpoint|openai-compatible|remote|api)
      echo "QMD embedding endpoint provider selected; local qmd embedding is skipped. Text index is updated, and endpoint-backed qmd vector search can use QMD_EMBED_ENDPOINT/QMD_EMBED_ENDPOINT_MODEL when available." >&2
      return 0
      ;;
    none|off|disabled)
      echo "QMD embeddings are disabled; text index is updated." >&2
      return 0
      ;;
  esac

  if [[ -n "${QMD_EMBED_MAX_DOCS_PER_BATCH:-}" ]]; then
    embed_cmd+=(--max-docs-per-batch "$QMD_EMBED_MAX_DOCS_PER_BATCH")
  fi
  if [[ -n "${QMD_EMBED_MAX_BATCH_MB:-}" ]]; then
    embed_cmd+=(--max-batch-mb "$QMD_EMBED_MAX_BATCH_MB")
  fi

  if [[ "$timeout_seconds" =~ ^[0-9]+$ ]] && (( timeout_seconds > 0 )) && command -v timeout >/dev/null 2>&1; then
    if timeout --foreground "${timeout_seconds}s" "${embed_cmd[@]}"; then
      return 0
    else
      rc=$?
    fi
    if [[ "$rc" == "124" || "$rc" == "137" ]]; then
      echo "QMD embedding timed out after ${timeout_seconds}s; text index is updated and embeddings will retry on the next refresh." >&2
      return 0
    fi
    echo "QMD embedding exited with status $rc; text index is updated and embeddings will retry on the next refresh." >&2
    return 0
  fi

  if "${embed_cmd[@]}"; then
    return 0
  else
    rc=$?
    echo "QMD embedding exited with status $rc; text index is updated and embeddings will retry on the next refresh." >&2
  fi
}

exec 9>"$QMD_REFRESH_LOCK_FILE"
flock 9

configure_qmd_collections
qmd --index "$QMD_INDEX_NAME" update

if [[ "$run_embed" == "1" ]]; then
  run_qmd_embed
fi
