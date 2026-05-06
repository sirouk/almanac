#!/usr/bin/env bash
set -euo pipefail

listen_host="${ARCLINK_HERMES_DASHBOARD_HOST:-0.0.0.0}"
listen_port="${ARCLINK_HERMES_DASHBOARD_PORT:-3210}"
backend_host="${ARCLINK_HERMES_DASHBOARD_BACKEND_HOST:-127.0.0.1}"
backend_port="${ARCLINK_HERMES_DASHBOARD_BACKEND_PORT:-13210}"
chutes_key_file="${ARCLINK_CHUTES_API_KEY_FILE:-}"

if [[ -n "$chutes_key_file" && -r "$chutes_key_file" ]]; then
  export CHUTES_API_KEY
  CHUTES_API_KEY="$(<"$chutes_key_file")"
fi

cleanup() {
  if [[ -n "${hermes_pid:-}" ]]; then
    kill "$hermes_pid" >/dev/null 2>&1 || true
    wait "$hermes_pid" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

hermes dashboard \
  --host "$backend_host" \
  --port "$backend_port" \
  --insecure \
  --no-open &
hermes_pid="$!"

python3 ./python/arclink_basic_auth_proxy.py \
  --no-auth \
  --listen-host "$listen_host" \
  --listen-port "$listen_port" \
  --target "http://$backend_host:$backend_port" \
  --realm "ArcLink Hermes"
