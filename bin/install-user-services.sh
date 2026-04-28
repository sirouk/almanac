#!/usr/bin/env bash
set -euo pipefail

BOOTSTRAP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_DIR="$HOME/.config/systemd/user"
# shellcheck disable=SC1091
source "$BOOTSTRAP_DIR/bin/common.sh"

mkdir -p "$TARGET_DIR"
rsync -a "$BOOTSTRAP_DIR/systemd/user/" "$TARGET_DIR/"

if ! set_user_systemd_bus_env; then
  if [[ "${ALMANAC_ALLOW_NO_USER_BUS:-0}" == "1" ]]; then
    echo "Systemd user bus unavailable; skipping unit enable because ALMANAC_ALLOW_NO_USER_BUS=1."
    exit 0
  fi
  runtime_dir="/run/user/$(id -u)"
  bus_path="$runtime_dir/bus"
  cat <<EOF
Could not find the systemd user bus for $(id -un).

Try:
  sudo loginctl enable-linger $(id -un)
  sudo systemctl start user@$(id -u).service
  sudo -iu $(id -un) env XDG_RUNTIME_DIR=$runtime_dir DBUS_SESSION_BUS_ADDRESS=unix:path=$bus_path $BOOTSTRAP_DIR/bin/install-user-services.sh
EOF
  exit 1
fi

enable_user_units() {
  if [[ $# -gt 0 ]]; then
    systemctl --user enable "$@"
  fi
}

restart_user_units() {
  if [[ $# -gt 0 ]]; then
    systemctl --user restart "$@"
  fi
}

start_user_units() {
  if [[ $# -gt 0 ]]; then
    systemctl --user start "$@"
  fi
}

systemctl --user daemon-reload
enable_user_units almanac-mcp.service
enable_user_units almanac-notion-webhook.service
enable_user_units almanac-ssot-batcher.timer
enable_user_units almanac-notification-delivery.timer
enable_user_units almanac-health-watch.timer
enable_user_units almanac-curator-refresh.timer
enable_user_units almanac-qmd-mcp.service
enable_user_units almanac-qmd-update.timer
enable_user_units almanac-vault-watch.service
enable_user_units almanac-github-backup.timer
if [[ "${ALMANAC_HERMES_DOCS_SYNC_ENABLED:-1}" == "1" ]]; then
  enable_user_units almanac-hermes-docs-sync.timer
else
  systemctl --user disable --now almanac-hermes-docs-sync.timer >/dev/null 2>&1 || true
fi

if [[ "$PDF_INGEST_ENABLED" == "1" ]]; then
  enable_user_units almanac-pdf-ingest.timer
else
  systemctl --user disable --now almanac-pdf-ingest.timer >/dev/null 2>&1 || true
fi

systemctl --user disable --now almanac-pdf-ingest-watch.service >/dev/null 2>&1 || true

if [[ "$ENABLE_QUARTO" == "1" ]]; then
  enable_user_units almanac-quarto-render.timer
else
  systemctl --user disable --now almanac-quarto-render.timer >/dev/null 2>&1 || true
fi

if [[ "$ENABLE_NEXTCLOUD" == "1" ]]; then
  if have_compose_runtime; then
    enable_user_units almanac-nextcloud.service
  else
    systemctl --user disable --now almanac-nextcloud.service >/dev/null 2>&1 || true
    echo "Nextcloud requested, but no compose runtime is available yet; service not enabled."
  fi
else
  systemctl --user disable --now almanac-nextcloud.service >/dev/null 2>&1 || true
fi

if has_curator_telegram_onboarding; then
  enable_user_units almanac-curator-onboarding.service
else
  systemctl --user disable --now almanac-curator-onboarding.service >/dev/null 2>&1 || true
fi

if has_curator_discord_onboarding; then
  enable_user_units almanac-curator-discord-onboarding.service
else
  systemctl --user disable --now almanac-curator-discord-onboarding.service >/dev/null 2>&1 || true
fi

if has_curator_gateway_channels && { ! has_curator_onboarding || has_curator_non_onboarding_gateway_channels; }; then
  enable_user_units almanac-curator-gateway.service
else
  systemctl --user disable --now almanac-curator-gateway.service >/dev/null 2>&1 || true
fi

restart_user_units \
  almanac-mcp.service \
  almanac-notion-webhook.service \
  almanac-ssot-batcher.timer \
  almanac-notification-delivery.timer \
  almanac-health-watch.timer \
  almanac-curator-refresh.timer \
  almanac-qmd-mcp.service \
  almanac-qmd-update.timer \
  almanac-vault-watch.service \
  almanac-github-backup.timer
if [[ "${ALMANAC_HERMES_DOCS_SYNC_ENABLED:-1}" == "1" ]]; then
  restart_user_units almanac-hermes-docs-sync.timer
  start_user_units almanac-hermes-docs-sync.service
fi
start_user_units almanac-curator-refresh.service

if [[ "$PDF_INGEST_ENABLED" == "1" ]]; then
  restart_user_units almanac-pdf-ingest.timer
fi

if [[ "$ENABLE_QUARTO" == "1" ]]; then
  restart_user_units almanac-quarto-render.timer
fi

if [[ "$ENABLE_NEXTCLOUD" == "1" ]] && have_compose_runtime; then
  restart_user_units almanac-nextcloud.service
fi

if has_curator_telegram_onboarding; then
  restart_user_units almanac-curator-onboarding.service
fi

if has_curator_discord_onboarding; then
  restart_user_units almanac-curator-discord-onboarding.service
fi

if has_curator_gateway_channels && { ! has_curator_onboarding || has_curator_non_onboarding_gateway_channels; }; then
  restart_user_units almanac-curator-gateway.service
fi
