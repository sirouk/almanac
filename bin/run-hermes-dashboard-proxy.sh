#!/usr/bin/env bash
set -euo pipefail

listen_host="${ARCLINK_HERMES_DASHBOARD_HOST:-0.0.0.0}"
listen_port="${ARCLINK_HERMES_DASHBOARD_PORT:-3210}"
backend_host="${ARCLINK_HERMES_DASHBOARD_BACKEND_HOST:-127.0.0.1}"
backend_port="${ARCLINK_HERMES_DASHBOARD_BACKEND_PORT:-13210}"
chutes_key_file="${ARCLINK_CHUTES_API_KEY_FILE:-}"
hermes_home="${HERMES_HOME:-/home/arclink/.hermes}"
access_file="${ARCLINK_HERMES_DASHBOARD_ACCESS_FILE:-$hermes_home/state/arclink-web-access.json}"
ready_file="${ARCLINK_HERMES_HOME_READY_FILE:-$hermes_home/state/arclink-hermes-home-ready.json}"
ready_wait="${ARCLINK_HERMES_HOME_READY_WAIT:-1}"
ready_timeout="${ARCLINK_HERMES_HOME_READY_TIMEOUT:-180}"
runtime_dir="${RUNTIME_DIR:-/opt/arclink/runtime}"
hermes_bin="${ARCLINK_HERMES_BIN:-$runtime_dir/hermes-venv/bin/hermes}"
if [[ ! -x "$hermes_bin" ]]; then
  hermes_bin="$(command -v hermes || true)"
fi

if [[ -z "$hermes_bin" || ! -x "$hermes_bin" ]]; then
  echo "Hermes dashboard binary not found; expected $runtime_dir/hermes-venv/bin/hermes" >&2
  exit 1
fi

if [[ -n "$chutes_key_file" && -r "$chutes_key_file" ]]; then
  export CHUTES_API_KEY
  CHUTES_API_KEY="$(<"$chutes_key_file")"
fi

check_dashboard_ready() {
  python3 - "$hermes_home" "$access_file" "$ready_file" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

hermes_home = Path(sys.argv[1])
access_file = Path(sys.argv[2])
ready_file = Path(sys.argv[3])
required = {"drive", "code", "terminal"}
missing: list[str] = []

def sequence_for(text: str, parent: str, child: str) -> set[str]:
    values: set[str] = set()
    parent_indent: int | None = None
    child_indent: int | None = None
    in_parent = False
    in_child = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        stripped = line.strip()
        if in_child:
            if indent > int(child_indent or 0) and stripped.startswith("-"):
                values.add(stripped[1:].strip().strip("\"'"))
                continue
            in_child = False
        if in_parent and parent_indent is not None and indent <= parent_indent and not stripped.startswith("-"):
            in_parent = False
        if not in_parent and indent == 0 and stripped == f"{parent}:":
            in_parent = True
            parent_indent = indent
            continue
        if in_parent and stripped == f"{child}:":
            in_child = True
            child_indent = indent
    return values

try:
    ready = json.loads(ready_file.read_text(encoding="utf-8"))
except Exception:
    ready = {}
if ready.get("status") != "ready":
    missing.append(str(ready_file))

for path in (access_file, hermes_home / "config.yaml"):
    if not path.is_file():
        missing.append(str(path))

for name in sorted(required):
    root = hermes_home / "plugins" / name
    for rel in ("plugin.yaml", "__init__.py", "dashboard/manifest.json", "dashboard/plugin_api.py", "dashboard/dist/index.js", "dashboard/dist/style.css"):
        if not (root / rel).is_file():
            missing.append(str(root / rel))

config_path = hermes_home / "config.yaml"
if config_path.is_file():
    text = config_path.read_text(encoding="utf-8", errors="replace")
    enabled = sequence_for(text, "plugins", "enabled")
    hidden = sequence_for(text, "dashboard", "hidden_plugins")
    if not required <= enabled:
        missing.append("config.plugins.enabled missing " + ",".join(sorted(required - enabled)))
    blocked = sorted(required & hidden)
    if blocked:
        missing.append("config.dashboard.hidden_plugins contains " + ",".join(blocked))

if missing:
    print("Hermes Dashboard prerequisites are not ready: " + "; ".join(missing[:12]), file=sys.stderr)
    raise SystemExit(1)
PY
}

wait_for_deployment_hermes_home() {
  if [[ "$ready_wait" == "0" ]]; then
    return 0
  fi
  local deadline=$((SECONDS + ready_timeout))
  local last_error=""
  while (( SECONDS <= deadline )); do
    if last_error="$(check_dashboard_ready 2>&1)"; then
      return 0
    fi
    sleep 2
  done
  if [[ -n "$last_error" ]]; then
    echo "$last_error" >&2
  fi
  echo "Timed out waiting for ArcLink Hermes Dashboard plugins to finish installing." >&2
  return 1
}

cleanup() {
  if [[ -n "${hermes_pid:-}" ]]; then
    kill "$hermes_pid" >/dev/null 2>&1 || true
    wait "$hermes_pid" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

wait_for_deployment_hermes_home

"$hermes_bin" dashboard \
  --host "$backend_host" \
  --port "$backend_port" \
  --insecure \
  --no-open &
hermes_pid="$!"

python3 ./python/arclink_dashboard_auth_proxy.py \
  --listen-host "$listen_host" \
  --listen-port "$listen_port" \
  --target "http://$backend_host:$backend_port" \
  --access-file "$access_file" \
  --realm "Hermes"
