#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <job-name> <interval-seconds> <command> [args...]" >&2
  exit 2
fi

JOB_NAME="$1"
INTERVAL_SECONDS="$2"
shift 2

if ! [[ "$INTERVAL_SECONDS" =~ ^[0-9]+$ ]] || [[ "$INTERVAL_SECONDS" == "0" ]]; then
  echo "interval-seconds must be a positive integer" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

STATUS_DIR="${ALMANAC_DOCKER_JOB_STATUS_DIR:-$STATE_DIR/docker/jobs}"
STATUS_FILE="$STATUS_DIR/$JOB_NAME.json"
mkdir -p "$STATUS_DIR"
output_file=""

cleanup() {
  [[ -z "$output_file" ]] || rm -f "$output_file"
}
trap cleanup EXIT

write_status() {
  local status="$1"
  local rc="$2"
  local output_file="$3"
  python3 - "$STATUS_FILE" "$JOB_NAME" "$status" "$rc" "$output_file" <<'PY'
import datetime as dt
import json
import sys
from pathlib import Path

status_file = Path(sys.argv[1])
output = Path(sys.argv[5]).read_text(encoding="utf-8", errors="replace") if Path(sys.argv[5]).exists() else ""
payload = {
    "job": sys.argv[2],
    "status": sys.argv[3],
    "returncode": int(sys.argv[4]),
    "finished_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "output_tail": output[-4000:],
}
status_file.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

status_for_return_code() {
  local rc="$1"
  if [[ "$rc" == "0" ]]; then
    echo ok
  else
    echo fail
  fi
}

run_job_once() {
  output_file="$(mktemp)"
  local rc=0
  "$@" >"$output_file" 2>&1 || rc=$?
  if [[ "$rc" != "0" ]]; then
    cat "$output_file" >&2
  fi
  write_status "$(status_for_return_code "$rc")" "$rc" "$output_file"
  cleanup
  output_file=""
}

while true; do
  run_job_once "$@"
  sleep "$INTERVAL_SECONDS"
done
