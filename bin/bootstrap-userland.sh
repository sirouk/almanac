#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

seed_private_repo_layout() {
  ensure_layout

  if [[ -d "$ALMANAC_PRIV_TEMPLATE_DIR/" ]]; then
    rsync -a --ignore-existing "$ALMANAC_PRIV_TEMPLATE_DIR/" "$ALMANAC_PRIV_DIR/"
  fi

  if [[ ! -f "$ALMANAC_PRIV_CONFIG_DIR/almanac.env" ]]; then
    cp "$BOOTSTRAP_DIR/config/almanac.env.example" "$ALMANAC_PRIV_CONFIG_DIR/almanac.env"
  fi
}

install_uv_if_missing() {
  ensure_uv
  if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ensure_uv
  fi
  uv python install 3.11
}

install_node_if_missing() {
  ensure_nvm
  if ! command -v nvm >/dev/null 2>&1; then
    curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
    ensure_nvm
  fi
  nvm install 22
  nvm alias default 22
}

install_qmd() {
  ensure_nvm
  if ! command -v qmd >/dev/null 2>&1; then
    npm install -g @tobilu/qmd
  fi
}

install_hermes() {
  ensure_shared_hermes_runtime
  "$RUNTIME_DIR/hermes-venv/bin/hermes" skills install official/research/qmd --yes || true
}

install_podman_compose_if_available() {
  ensure_uv
  if command -v podman >/dev/null 2>&1 && ! command -v podman-compose >/dev/null 2>&1; then
    uv tool install podman-compose || true
  fi
}

initialize_private_git_repo() {
  if [[ "$ENABLE_PRIVATE_GIT" != "1" ]]; then
    return 0
  fi

  if [[ ! -d "$ALMANAC_PRIV_DIR/.git" ]]; then
    git -C "$ALMANAC_PRIV_DIR" init -b "$BACKUP_GIT_BRANCH"
  fi

  if [[ -n "$BACKUP_GIT_REMOTE" ]]; then
    if git -C "$ALMANAC_PRIV_DIR" remote get-url origin >/dev/null 2>&1; then
      git -C "$ALMANAC_PRIV_DIR" remote set-url origin "$BACKUP_GIT_REMOTE"
    else
      git -C "$ALMANAC_PRIV_DIR" remote add origin "$BACKUP_GIT_REMOTE"
    fi
  fi
}

seed_private_repo_layout
install_uv_if_missing
install_node_if_missing
install_qmd
install_hermes
install_podman_compose_if_available
initialize_private_git_repo
configure_qmd_collections

if [[ "${QMD_RUN_EMBED:-1}" == "1" ]]; then
  "$SCRIPT_DIR/qmd-refresh.sh"
fi

cat <<EOF

Userland bootstrap complete.

Private repo: $ALMANAC_PRIV_DIR
Vault:        $VAULT_DIR
QMD index:    $QMD_INDEX_NAME
Hermes:       $RUNTIME_DIR/hermes-venv/bin/hermes

Suggested next steps:
  $BOOTSTRAP_DIR/bin/install-user-services.sh
  systemctl --user start almanac-qmd-mcp.service
  systemctl --user start almanac-qmd-update.service

Hermes MCP config snippet:
  $BOOTSTRAP_DIR/docs/hermes-qmd-config.yaml

EOF
