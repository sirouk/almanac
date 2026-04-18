#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

require_real_layout "vault watcher"
ensure_layout

if ! command -v inotifywait >/dev/null 2>&1; then
  echo "inotifywait is required for vault watching." >&2
  exit 1
fi

is_pdf_path() {
  local event_path="$1"
  local lower_path=""

  lower_path="$(printf '%s' "$event_path" | tr '[:upper:]' '[:lower:]')"
  [[ "$lower_path" == *.pdf ]]
}

is_direct_vault_text_path() {
  local event_path="$1"
  local lower_path=""

  lower_path="$(printf '%s' "$event_path" | tr '[:upper:]' '[:lower:]')"
  [[ "$lower_path" == *.md || "$lower_path" == *.markdown || "$lower_path" == *.mdx || "$lower_path" == *.txt || "$lower_path" == *.text ]]
}

pdf_status_needs_qmd_refresh() {
  python3 - "$PDF_INGEST_STATUS_FILE" <<'PY'
import json
import sys
from pathlib import Path

status_path = Path(sys.argv[1])
if not status_path.exists():
    raise SystemExit(1)
status = json.loads(status_path.read_text())
raise SystemExit(0 if status.get("qmd_refresh_needed") else 1)
PY
}

preserve_pdf_status_change_summary() {
  local previous_status="$1"

  python3 - "$previous_status" "$PDF_INGEST_STATUS_FILE" <<'PY'
import json
import sys
from pathlib import Path

previous_path = Path(sys.argv[1])
current_path = Path(sys.argv[2])

if not previous_path.exists() or not current_path.exists():
    raise SystemExit(1)

previous = json.loads(previous_path.read_text())
current = json.loads(current_path.read_text())


def delta_count(summary: dict) -> int:
    return sum(int(summary.get(key, 0)) for key in ("created", "updated", "removed", "failed"))


if delta_count(current) != 0 or delta_count(previous) == 0:
    raise SystemExit(1)

for key in (
    "created",
    "updated",
    "removed",
    "failed",
    "changed_documents",
    "removed_documents",
    "failed_documents",
    "vision_pages_rendered",
    "vision_pages_captioned",
    "vision_pages_failed",
    "vision_failures",
):
    current[key] = previous.get(key, current.get(key))

current["qmd_refresh_needed"] = False
current_path.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

run_qmd_refresh() {
  echo "Vault watcher: refreshing qmd index..."
  if [[ "$VAULT_WATCH_RUN_EMBED" == "1" ]]; then
    "$SCRIPT_DIR/qmd-refresh.sh" --embed
  else
    "$SCRIPT_DIR/qmd-refresh.sh" --skip-embed
  fi
}

run_qmd_embed() {
  echo "Vault watcher: embedding pending qmd updates..."
  ensure_nvm
  exec 8>"$QMD_REFRESH_LOCK_FILE"
  flock 8
  qmd --index "$QMD_INDEX_NAME" embed
}

maybe_run_qmd_embed() {
  local mode="${VAULT_WATCH_RUN_EMBED,,}"
  local pending=0

  case "$mode" in
    0|false|no|off)
      return 0
      ;;
    1|true|yes|on)
      return 0
      ;;
    auto|"")
      pending="$(qmd_pending_embeddings_count || printf '0\n')"
      if [[ "${pending:-0}" =~ ^[0-9]+$ ]] && (( pending > 0 )); then
        run_qmd_embed
      fi
      ;;
    *)
      pending="$(qmd_pending_embeddings_count || printf '0\n')"
      if [[ "${pending:-0}" =~ ^[0-9]+$ ]] && (( pending > 0 )); then
        run_qmd_embed
      fi
      ;;
  esac
}

is_vault_definition_path() {
  local event_path="$1"
  [[ "$(basename "$event_path")" == ".vault" ]]
}

run_vault_reload_defs() {
  echo "Vault watcher: reloading .vault definitions..."
  if [[ -x "$SCRIPT_DIR/almanac-ctl" ]]; then
    local err_file=""
    err_file="$(mktemp)"
    if ! PYTHONPATH="$BOOTSTRAP_DIR/python${PYTHONPATH:+:$PYTHONPATH}" \
        "$SCRIPT_DIR/almanac-ctl" --json vault reload-defs >/dev/null 2>"$err_file"; then
      echo "Vault watcher: reload-defs failed (continuing):" >&2
      cat "$err_file" >&2 || true
    fi
    rm -f "$err_file"
  fi
}

run_vault_notify_paths() {
  if (( ${#vault_watch_notify_paths[@]} == 0 )); then
    return 0
  fi
  if [[ ! -x "$SCRIPT_DIR/almanac-ctl" ]]; then
    return 0
  fi
  echo "Vault watcher: routing subscriber notifications for changed vault content..."
  local err_file=""
  err_file="$(mktemp)"
  if ! PYTHONPATH="$BOOTSTRAP_DIR/python${PYTHONPATH:+:$PYTHONPATH}" \
      "$SCRIPT_DIR/almanac-ctl" --json vault notify-paths --source vault-watch "${vault_watch_notify_paths[@]}" >/dev/null 2>"$err_file"; then
    echo "Vault watcher: notify-paths failed (continuing):" >&2
    cat "$err_file" >&2 || true
  fi
  rm -f "$err_file"
}

fold_event_into_flags() {
  local event_path="$1"
  local event_flags="$2"

  if [[ "$event_flags" == *ISDIR* ]]; then
    vault_watch_need_qmd=1
    if [[ "$PDF_INGEST_ENABLED" == "1" ]]; then
      vault_watch_need_pdf=1
    fi
    return 0
  fi

  if is_vault_definition_path "$event_path"; then
    vault_watch_need_vault_reload=1
    return 0
  fi

  if is_pdf_path "$event_path"; then
    if [[ "$PDF_INGEST_ENABLED" == "1" ]]; then
      vault_watch_need_pdf=1
      vault_watch_need_qmd=1
      vault_watch_notify_paths+=("$event_path")
    fi
    return 0
  fi

  if is_direct_vault_text_path "$event_path"; then
    vault_watch_need_qmd=1
    vault_watch_notify_paths+=("$event_path")
    return 0
  fi

  return 1
}

start_event_stream() {
  if [[ -n "${vault_watch_fd:-}" ]]; then
    exec {vault_watch_fd}<&- || true
  fi

  exec {vault_watch_fd}< <(
    inotifywait \
      --monitor \
      --quiet \
      --recursive \
      --format '%w%f|%e' \
      --event close_write,create,delete,moved_to,moved_from,attrib \
      "$VAULT_DIR" 2>/dev/null
  )
}

stop_event_stream() {
  if [[ -n "${vault_watch_fd:-}" ]]; then
    exec {vault_watch_fd}<&- || true
    unset vault_watch_fd
  fi
}

read_next_event() {
  local timeout_seconds="$1"
  local event_line=""

  if (( timeout_seconds > 0 )); then
    if IFS= read -r -t "$timeout_seconds" -u "$vault_watch_fd" event_line; then
      printf '%s\n' "$event_line"
      return 0
    fi
    return 1
  fi

  if IFS= read -r -u "$vault_watch_fd" event_line; then
    printf '%s\n' "$event_line"
    return 0
  fi

  return 1
}

drain_event_burst() {
  local next_deadline=0
  local wait_seconds=0
  local event_line=""
  local event_path=""
  local event_flags=""

  next_deadline=$((SECONDS + VAULT_WATCH_DEBOUNCE_SECONDS))

  while true; do
    wait_seconds=$((next_deadline - SECONDS))
    if (( wait_seconds <= 0 )); then
      return 0
    fi

    if ! event_line="$(read_next_event "$wait_seconds")"; then
      return 0
    fi

    event_path="${event_line%%|*}"
    event_flags="${event_line#*|}"
    fold_event_into_flags "$event_path" "$event_flags" || true
    next_deadline=$((SECONDS + VAULT_WATCH_DEBOUNCE_SECONDS))
  done
}

echo "Watching $VAULT_DIR for vault changes..."
trap stop_event_stream EXIT
start_event_stream

while true; do
  if ! event_line="$(read_next_event 0)"; then
    echo "Vault watcher: event stream ended; restarting..."
    sleep 2
    start_event_stream
    continue
  fi

  vault_watch_need_pdf=0
  vault_watch_need_qmd=0
  vault_watch_need_vault_reload=0
  vault_watch_notify_paths=()
  event_path="${event_line%%|*}"
  event_flags="${event_line#*|}"
  fold_event_into_flags "$event_path" "$event_flags" || continue

  drain_event_burst

  if (( vault_watch_need_vault_reload )); then
    run_vault_reload_defs
  fi

  if (( vault_watch_need_pdf )); then
    echo "Vault watcher: reconciling PDF-derived markdown..."
    PDF_INGEST_TRIGGER_QMD_REFRESH=0 "$SCRIPT_DIR/pdf-ingest.sh" --quiet
    if pdf_status_needs_qmd_refresh; then
      vault_watch_need_qmd=1
    fi
  fi

  if (( vault_watch_need_qmd )); then
    run_qmd_refresh
  fi

  if (( vault_watch_need_pdf )); then
    echo "Vault watcher: running post-refresh PDF reconciliation..."
    previous_pdf_status=""
    if [[ -f "$PDF_INGEST_STATUS_FILE" ]]; then
      previous_pdf_status="$(mktemp)"
      cp -f "$PDF_INGEST_STATUS_FILE" "$previous_pdf_status"
    fi
    PDF_INGEST_TRIGGER_QMD_REFRESH=0 "$SCRIPT_DIR/pdf-ingest.sh" --quiet
    if [[ -n "$previous_pdf_status" ]]; then
      preserve_pdf_status_change_summary "$previous_pdf_status" || true
      rm -f "$previous_pdf_status"
    fi
    if pdf_status_needs_qmd_refresh; then
      echo "Vault watcher: refreshing qmd index after late PDF changes..."
      run_qmd_refresh
    fi
  fi

  if (( ${#vault_watch_notify_paths[@]} > 0 )); then
    run_vault_notify_paths
  fi

  if [[ "${VAULT_WATCH_RUN_EMBED,,}" != "1" ]]; then
    maybe_run_qmd_embed
  fi
done
