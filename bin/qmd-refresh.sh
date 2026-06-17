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

clear_qmd_embed_force_flag() {
  local config="${CONFIG_FILE:-}"
  local mode=""
  local old_umask=""
  local temp=""

  if [[ "${QMD_EMBED_FORCE_ON_NEXT_REFRESH:-0}" != "1" || -z "$config" || ! -f "$config" || ! -w "$config" ]]; then
    return 0
  fi

  old_umask="$(umask)"
  umask 077
  temp="$(mktemp "${config}.tmp.XXXXXX")" || {
    umask "$old_umask"
    return 0
  }
  if awk '
    BEGIN { cleared = 0 }
    /^QMD_EMBED_FORCE_ON_NEXT_REFRESH=/ {
      print "QMD_EMBED_FORCE_ON_NEXT_REFRESH=0"
      cleared = 1
      next
    }
    { print }
    END {
      if (!cleared) {
        print "QMD_EMBED_FORCE_ON_NEXT_REFRESH=0"
      }
    }
  ' "$config" >"$temp"; then
    umask "$old_umask"
    mode="$(stat -c '%a' "$config" 2>/dev/null || true)"
    if [[ -n "$mode" ]]; then
      chmod "$mode" "$temp" 2>/dev/null || true
    fi
    if mv -f "$temp" "$config"; then
      temp=""
      QMD_EMBED_FORCE_ON_NEXT_REFRESH=0
    fi
  else
    umask "$old_umask"
  fi
  if [[ -n "$temp" ]]; then
    rm -f "$temp"
  fi
}

run_qmd_embed() {
  local timeout_seconds="${QMD_EMBED_TIMEOUT_SECONDS:-0}"
  local rc=0
  local -a embed_cmd=(qmd --index "$QMD_INDEX_NAME" embed)

  case "${QMD_EMBED_PROVIDER:-local}" in
    endpoint|openai-compatible|remote|api)
      # The pinned qmd release has no endpoint-backed embedding support, so
      # honoring this provider literally would silently disable ALL vector
      # search. Fall back to local embedding and keep the endpoint env vars
      # (QMD_EMBED_ENDPOINT/QMD_EMBED_ENDPOINT_MODEL/...) untouched so a future
      # qmd upgrade can adopt them without reconfiguration.
      echo "WARNING: QMD embedding endpoint provider selected, but the pinned qmd release does not support endpoint-backed embeddings; falling back to local qmd embeddings so vector search stays available. QMD_EMBED_ENDPOINT settings are preserved for a future qmd upgrade." >&2
      ;;
    none|off|disabled)
      echo "QMD embeddings are disabled; text index is updated." >&2
      return 0
      ;;
  esac

  if [[ "${QMD_EMBED_FORCE_ON_NEXT_REFRESH:-0}" == "1" ]]; then
    echo "QMD local embedding force refresh requested; rebuilding local vectors." >&2
    embed_cmd+=(-f)
  fi

  if [[ -n "${QMD_EMBED_MAX_DOCS_PER_BATCH:-}" ]]; then
    embed_cmd+=(--max-docs-per-batch "$QMD_EMBED_MAX_DOCS_PER_BATCH")
  fi
  if [[ -n "${QMD_EMBED_MAX_BATCH_MB:-}" ]]; then
    embed_cmd+=(--max-batch-mb "$QMD_EMBED_MAX_BATCH_MB")
  fi

  if [[ "$timeout_seconds" =~ ^[0-9]+$ ]] && (( timeout_seconds > 0 )) && command -v timeout >/dev/null 2>&1; then
    if timeout --foreground "${timeout_seconds}s" "${embed_cmd[@]}"; then
      clear_qmd_embed_force_flag
      return 0
    else
      rc=$?
    fi
    if [[ "$rc" == "124" || "$rc" == "137" ]]; then
      echo "QMD embedding timed out after ${timeout_seconds}s; text index is updated and embeddings will retry on the next refresh." >&2
      return "$rc"
    fi
    echo "QMD embedding exited with status $rc; text index is updated and embeddings will retry on the next refresh." >&2
    return "$rc"
  fi

  if "${embed_cmd[@]}"; then
    clear_qmd_embed_force_flag
    return 0
  else
    rc=$?
    echo "QMD embedding exited with status $rc; text index is updated and embeddings will retry on the next refresh." >&2
    return "$rc"
  fi
}

exec 9>"$QMD_REFRESH_LOCK_FILE"
flock 9

configure_qmd_collections
qmd --index "$QMD_INDEX_NAME" update

embed_status=0
if [[ "$run_embed" == "1" ]]; then
  run_qmd_embed || embed_status=$?
fi

# Track how long documents have been waiting for embeddings so a quietly
# starved embed lane surfaces as a health/diagnostics warning instead of
# leaving vector search stale indefinitely.
qmd_note_pending_embeddings_state || true

exit "$embed_status"
