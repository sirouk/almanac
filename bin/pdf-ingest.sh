#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

quiet=0
if [[ "${1:-}" == "--quiet" ]]; then
  quiet=1
  shift
fi

require_real_layout "PDF ingestion"
ensure_layout

export VAULT_DIR
export PDF_INGEST_MARKDOWN_DIR
export PDF_INGEST_MANIFEST_DB
export PDF_INGEST_STATUS_FILE
export PDF_INGEST_EXTRACTOR
export NEXTCLOUD_VAULT_MOUNT_POINT
export PDF_INGEST_DOCLING_FORCE_OCR
export PDF_VISION_ENDPOINT
export PDF_VISION_MODEL
export PDF_VISION_API_KEY
export PDF_VISION_MAX_PAGES

if [[ "$PDF_INGEST_ENABLED" != "1" ]]; then
  if [[ "$quiet" != "1" ]]; then
    echo "PDF ingestion is disabled in config."
  fi
  exit 0
fi

summary_json="$(
  flock "$PDF_INGEST_LOCK_FILE" \
    python3 "$SCRIPT_DIR/pdf-ingest.py" "$@"
)"

if [[ "$quiet" != "1" ]]; then
  PDF_INGEST_SUMMARY_JSON="$summary_json" python3 - <<'PY'
import json
import os

summary = json.loads(os.environ["PDF_INGEST_SUMMARY_JSON"])
print(
    "PDF ingest: "
    f"{summary['total_pdfs']} pdf, "
    f"{summary['created']} created, "
    f"{summary['updated']} updated, "
    f"{summary['unchanged']} unchanged, "
    f"{summary['removed']} removed, "
    f"{summary['failed']} failed "
    f"(backend: {summary['backend']})"
)
for failure in summary.get("failed_documents", [])[:10]:
    print(f"  failed: {failure['path']}: {failure['error']}")
PY
fi

if [[ "$PDF_INGEST_TRIGGER_QMD_REFRESH" == "1" ]] && SUMMARY_JSON="$summary_json" python3 - <<'PY'
import json
import os

summary = json.loads(os.environ["SUMMARY_JSON"])
raise SystemExit(0 if summary.get("qmd_refresh_needed") else 1)
PY
then
  if [[ "$quiet" != "1" ]]; then
    echo "Refreshing qmd after PDF ingest changes..."
  fi
  "$SCRIPT_DIR/qmd-refresh.sh"
fi
