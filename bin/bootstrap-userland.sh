#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

reconcile_vault_layout() {
  local -a hermes_skills_args=()
  if [[ -d "$RUNTIME_DIR/hermes-agent-src/skills" ]]; then
    hermes_skills_args=(--hermes-skills-dir "$RUNTIME_DIR/hermes-agent-src/skills")
  fi

  python3 "$SCRIPT_DIR/reconcile-vault-layout.py" \
    --repo-dir "$BOOTSTRAP_DIR" \
    --vault-dir "$VAULT_DIR" \
    --repo-url "${ALMANAC_UPSTREAM_REPO_URL:-}" \
    "${hermes_skills_args[@]}"
}

seed_private_repo_layout() {
  ensure_layout

  if [[ -d "$ALMANAC_PRIV_TEMPLATE_DIR/" ]]; then
    rsync -a --ignore-existing "$ALMANAC_PRIV_TEMPLATE_DIR/" "$ALMANAC_PRIV_DIR/"
  fi

  reconcile_vault_layout

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
  uv self update >/dev/null 2>&1 || true
  if ! uv python install 3.12; then
    uv python install 3.11
  fi
}

install_node_if_missing() {
  # Both nvm tag + node version are pinned in config/pins.json; env vars still
  # provide fallback values for partially-bootstrapped hosts.
  local nvm_tag node_version
  nvm_tag="$(__pins_get_or_default nvm tag "${ALMANAC_NVM_TAG:-v0.40.3}")"
  node_version="$(__pins_get_or_default node version "${ALMANAC_NODE_VERSION:-22}")"
  ensure_nvm
  if ! command -v nvm >/dev/null 2>&1; then
    curl -fsSL "https://raw.githubusercontent.com/nvm-sh/nvm/${nvm_tag}/install.sh" | bash
    ensure_nvm
  fi
  nvm install "$node_version"
  nvm alias default "$node_version"
}

install_qmd() {
  # qmd version is pinned in config/pins.json. An explicit semver is enforced
  # on every bootstrap so retrieval semantics cannot drift under agents.
  local qmd_pkg qmd_version qmd_spec installed_version
  qmd_pkg="$(__pins_get_or_default qmd package "${ALMANAC_QMD_PACKAGE:-@tobilu/qmd}")"
  qmd_version="$(__pins_get_or_default qmd version "${ALMANAC_QMD_VERSION:-2.1.0}")"
  qmd_spec="${qmd_pkg}@${qmd_version}"
  ensure_nvm
  installed_version=""
  if command -v qmd >/dev/null 2>&1; then
    installed_version="$(qmd --version 2>/dev/null | awk 'NR==1 {print $2}' || true)"
  fi
  if [[ "$qmd_version" == "latest" || "$installed_version" != "$qmd_version" ]]; then
    npm install -g "$qmd_spec"
  fi
}

install_hermes_runtime() {
  # The shared Almanac runtime only needs Hermes itself here. Almanac skills are
  # installed into Curator and user Hermes homes later from local repo paths.
  # Avoid legacy remote skill fetches during host bootstrap.
  ensure_shared_hermes_runtime
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

  ensure_backup_git_origin_remote "$ALMANAC_PRIV_DIR"
}

seed_private_repo_layout
install_uv_if_missing
install_node_if_missing
install_qmd
install_hermes_runtime
reconcile_vault_layout
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
