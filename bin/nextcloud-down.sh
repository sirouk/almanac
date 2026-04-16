#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

COMPOSE_FILE="$BOOTSTRAP_DIR/compose/nextcloud-compose.yml"

cleanup_legacy_compose_cni() {
  local cni_file="$HOME/.config/cni/net.d/compose_default.conflist"

  if [[ -f "$cni_file" ]] && grep -q '"cniVersion": "1.0.0"' "$cni_file"; then
    rm -f "$cni_file"
  fi
}

export NEXTCLOUD_PORT NEXTCLOUD_TRUSTED_DOMAIN
export POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD
export NEXTCLOUD_ADMIN_USER NEXTCLOUD_ADMIN_PASSWORD
export NEXTCLOUD_DB_DIR NEXTCLOUD_REDIS_DIR NEXTCLOUD_HTML_DIR NEXTCLOUD_DATA_DIR
export NEXTCLOUD_CUSTOM_CONFIG_DIR NEXTCLOUD_EMPTY_SKELETON_DIR NEXTCLOUD_ALMANAC_CONFIG_FILE
export NEXTCLOUD_HOOKS_DIR NEXTCLOUD_PRE_INSTALL_HOOK_DIR NEXTCLOUD_POST_INSTALL_HOOK_DIR NEXTCLOUD_BEFORE_STARTING_HOOK_DIR
export NEXTCLOUD_PRE_INSTALL_HOOK_FILE NEXTCLOUD_POST_INSTALL_HOOK_FILE NEXTCLOUD_BEFORE_STARTING_HOOK_FILE VAULT_DIR

if command -v podman >/dev/null 2>&1; then
  if podman pod inspect "$(nextcloud_pod_name)" >/dev/null 2>&1; then
    podman pod rm -f "$(nextcloud_pod_name)" >/dev/null 2>&1 || true
  fi
  cleanup_legacy_compose_cni
  exit 0
fi

if have_compose_runtime; then
  run_compose "$COMPOSE_FILE" down
  exit 0
fi

echo "No compose runtime found."
exit 1
