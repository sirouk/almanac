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

systemctl --user daemon-reload
systemctl --user enable almanac-mcp.service
systemctl --user enable almanac-notion-webhook.service
systemctl --user enable almanac-ssot-batcher.timer
systemctl --user enable almanac-notification-delivery.timer
systemctl --user enable almanac-curator-refresh.timer
systemctl --user enable almanac-qmd-mcp.service
systemctl --user enable almanac-qmd-update.timer
systemctl --user enable almanac-vault-watch.service
systemctl --user enable almanac-github-backup.timer

if [[ "$PDF_INGEST_ENABLED" == "1" ]]; then
  systemctl --user enable almanac-pdf-ingest.timer
else
  systemctl --user disable --now almanac-pdf-ingest.timer >/dev/null 2>&1 || true
fi

systemctl --user disable --now almanac-pdf-ingest-watch.service >/dev/null 2>&1 || true

if [[ "$ENABLE_QUARTO" == "1" ]]; then
  systemctl --user enable almanac-quarto-render.timer
else
  systemctl --user disable --now almanac-quarto-render.timer >/dev/null 2>&1 || true
fi

if [[ "$ENABLE_NEXTCLOUD" == "1" ]]; then
  if have_compose_runtime; then
    systemctl --user enable almanac-nextcloud.service
  else
    systemctl --user disable --now almanac-nextcloud.service >/dev/null 2>&1 || true
    echo "Nextcloud requested, but no compose runtime is available yet; service not enabled."
  fi
else
  systemctl --user disable --now almanac-nextcloud.service >/dev/null 2>&1 || true
fi

if has_curator_telegram_onboarding; then
  systemctl --user enable almanac-curator-onboarding.service
else
  systemctl --user disable --now almanac-curator-onboarding.service >/dev/null 2>&1 || true
fi

if has_curator_discord_onboarding; then
  systemctl --user enable almanac-curator-discord-onboarding.service
else
  systemctl --user disable --now almanac-curator-discord-onboarding.service >/dev/null 2>&1 || true
fi

if has_curator_gateway_channels && { ! has_curator_onboarding || has_curator_non_onboarding_gateway_channels; }; then
  systemctl --user enable almanac-curator-gateway.service
else
  systemctl --user disable --now almanac-curator-gateway.service >/dev/null 2>&1 || true
fi
