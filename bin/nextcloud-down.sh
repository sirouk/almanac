#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

COMPOSE_FILE="$BOOTSTRAP_DIR/compose/nextcloud-compose.yml"

nextcloud_docker_mode_requested() {
  [[ "${ALMANAC_CONTAINER_RUNTIME:-}" == "docker" || "${ALMANAC_DOCKER_MODE:-0}" == "1" ]]
}

run_compose_nextcloud_down() {
  with_nextcloud_compose_env run_compose "$COMPOSE_FILE" down
}

cleanup_legacy_compose_cni() {
  local cni_file="$HOME/.config/cni/net.d/compose_default.conflist"

  if [[ -f "$cni_file" ]] && grep -q '"cniVersion": "1.0.0"' "$cni_file"; then
    rm -f "$cni_file"
  fi
}

if nextcloud_docker_mode_requested; then
  if have_compose_runtime; then
    run_compose_nextcloud_down
    exit 0
  fi
  echo "Docker mode requested, but no compose runtime is available." >&2
  exit 1
fi

if command -v podman >/dev/null 2>&1; then
  if podman pod inspect "$(nextcloud_pod_name)" >/dev/null 2>&1; then
    podman pod rm -f "$(nextcloud_pod_name)" >/dev/null 2>&1 || true
  fi
  cleanup_legacy_compose_cni
  exit 0
fi

if have_compose_runtime; then
  run_compose_nextcloud_down
  exit 0
fi

echo "No compose runtime found."
exit 1
