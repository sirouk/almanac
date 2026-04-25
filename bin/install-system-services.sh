#!/usr/bin/env bash
set -euo pipefail

BOOTSTRAP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$BOOTSTRAP_DIR/bin/common.sh"

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run this as root or with sudo."
  exit 1
fi

TARGET_DIR="/etc/systemd/system"
CONFIG_PATH="${CONFIG_FILE:-$ALMANAC_PRIV_CONFIG_DIR/almanac.env}"
mkdir -p "$TARGET_DIR"

cat >"$TARGET_DIR/almanac-enrollment-provision.service" <<EOF
[Unit]
Description=Provision approved Almanac enrollments
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
Environment=HOME=/root
Environment=ALMANAC_CONFIG_FILE=$CONFIG_PATH
ExecStart=$ALMANAC_REPO_DIR/bin/almanac-enrollment-provision.sh
EOF

cat >"$TARGET_DIR/almanac-enrollment-provision.timer" <<EOF
[Unit]
Description=Scan for approved Almanac enrollments that need host provisioning

[Timer]
OnBootSec=45s
OnUnitActiveSec=1m
Persistent=true
Unit=almanac-enrollment-provision.service

[Install]
WantedBy=timers.target
EOF

cat >"$TARGET_DIR/almanac-notion-claim-poll.service" <<EOF
[Unit]
Description=Poll pending Almanac self-serve Notion claims
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
Environment=HOME=/root
Environment=ALMANAC_CONFIG_FILE=$CONFIG_PATH
ExecStart=$ALMANAC_REPO_DIR/bin/almanac-enrollment-provision.sh --claims-only
EOF

cat >"$TARGET_DIR/almanac-notion-claim-poll.timer" <<EOF
[Unit]
Description=Poll pending Almanac self-serve Notion claims

[Timer]
OnBootSec=90s
OnUnitActiveSec=2m
Persistent=true
Unit=almanac-notion-claim-poll.service

[Install]
WantedBy=timers.target
EOF

chmod 0644 \
  "$TARGET_DIR/almanac-enrollment-provision.service" \
  "$TARGET_DIR/almanac-enrollment-provision.timer" \
  "$TARGET_DIR/almanac-notion-claim-poll.service" \
  "$TARGET_DIR/almanac-notion-claim-poll.timer"

systemctl daemon-reload
systemctl enable almanac-enrollment-provision.timer >/dev/null
systemctl restart almanac-enrollment-provision.timer
systemctl start almanac-enrollment-provision.service >/dev/null 2>&1 || true
systemctl enable almanac-notion-claim-poll.timer >/dev/null
systemctl restart almanac-notion-claim-poll.timer
systemctl start almanac-notion-claim-poll.service >/dev/null 2>&1 || true
