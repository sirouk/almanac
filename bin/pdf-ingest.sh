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

PYTHON_BIN="$(require_runtime_python)"
if command -v flock >/dev/null 2>&1; then
  summary_json="$(
    flock "$PDF_INGEST_LOCK_FILE" \
      "$PYTHON_BIN" "$SCRIPT_DIR/pdf-ingest.py" "$@"
  )"
else
  summary_json="$(
    PDF_INGEST_LOCK_FILE="$PDF_INGEST_LOCK_FILE" "$PYTHON_BIN" - "$SCRIPT_DIR/pdf-ingest.py" "$@" <<'PY'
import fcntl
import os
import subprocess
import sys
from pathlib import Path

lock_path = Path(os.environ["PDF_INGEST_LOCK_FILE"])
lock_path.parent.mkdir(parents=True, exist_ok=True)
with lock_path.open("a", encoding="utf-8") as lock:
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
    result = subprocess.run([sys.executable, sys.argv[1], *sys.argv[2:]], text=True, stdout=subprocess.PIPE)
    sys.stdout.write(result.stdout)
    raise SystemExit(result.returncode)
PY
  )"
fi

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
