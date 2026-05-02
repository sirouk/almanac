#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
env_args=(DEBIAN_FRONTEND=noninteractive)

if command -v tailscale >/dev/null 2>&1 && tailscale status --json >/dev/null 2>&1; then
  env_args+=(ARCLINK_SMOKE_ENABLE_TAILSCALE_SERVE=1)
  env_args+=(ARCLINK_SMOKE_TAILSCALE_OPERATOR_USER="${USER:-$(id -un)}")
fi

"$ROOT_DIR/bin/ci-preflight.sh"

exec sudo env "${env_args[@]}" "$ROOT_DIR/bin/ci-install-smoke.sh"
