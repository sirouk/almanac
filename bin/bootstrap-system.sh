#!/usr/bin/env bash
set -euo pipefail

BOOTSTRAP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ALMANAC_USER="${ALMANAC_USER:-almanac}"
ALMANAC_HOME="${ALMANAC_HOME:-/home/$ALMANAC_USER}"
ALMANAC_REPO_DIR="${ALMANAC_REPO_DIR:-$ALMANAC_HOME/almanac}"
ALMANAC_PRIV_DIR="${ALMANAC_PRIV_DIR:-$ALMANAC_REPO_DIR/almanac-priv}"
ALMANAC_PRIV_CONFIG_DIR="${ALMANAC_PRIV_CONFIG_DIR:-$ALMANAC_PRIV_DIR/config}"
VAULT_DIR="${VAULT_DIR:-$ALMANAC_PRIV_DIR/vault}"
STATE_DIR="${STATE_DIR:-$ALMANAC_PRIV_DIR/state}"
NEXTCLOUD_STATE_DIR="${NEXTCLOUD_STATE_DIR:-$STATE_DIR/nextcloud}"
PUBLISHED_DIR="${PUBLISHED_DIR:-$ALMANAC_PRIV_DIR/published}"
QUARTO_PROJECT_DIR="${QUARTO_PROJECT_DIR:-$ALMANAC_PRIV_DIR/quarto}"

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run this as root or with sudo."
  exit 1
fi

apt-get update
apt-get install -y \
  acl \
  curl \
  dbus-user-session \
  inotify-tools \
  git \
  python3 \
  podman \
  poppler-utils \
  uidmap \
  slirp4netns \
  fuse-overlayfs \
  sqlite3 \
  rsync

if ! id -u "$ALMANAC_USER" >/dev/null 2>&1; then
  useradd -m -s /bin/bash "$ALMANAC_USER"
fi

install -d -m 0750 -o "$ALMANAC_USER" -g "$ALMANAC_USER" \
  "$ALMANAC_HOME" \
  "$ALMANAC_PRIV_DIR" \
  "$ALMANAC_PRIV_CONFIG_DIR" \
  "$VAULT_DIR" \
  "$STATE_DIR" \
  "$NEXTCLOUD_STATE_DIR" \
  "$PUBLISHED_DIR" \
  "$QUARTO_PROJECT_DIR"
install -d -m 0755 -o "$ALMANAC_USER" -g "$ALMANAC_USER" "$ALMANAC_REPO_DIR"

rsync -a --delete \
  --exclude ".git/" \
  --exclude "almanac-priv/" \
  --exclude "config/almanac.env" \
  "$BOOTSTRAP_DIR/" "$ALMANAC_REPO_DIR/"
chown -R "$ALMANAC_USER:$ALMANAC_USER" "$ALMANAC_REPO_DIR" "$ALMANAC_PRIV_DIR"
chmod 0755 "$ALMANAC_REPO_DIR"

loginctl enable-linger "$ALMANAC_USER" || true
systemctl start "user@$(id -u "$ALMANAC_USER").service" || true

cat <<EOF

System bootstrap complete.

Next steps:
  Write private config to: $ALMANAC_PRIV_CONFIG_DIR/almanac.env
  sudo -iu $ALMANAC_USER env ALMANAC_CONFIG_FILE="$ALMANAC_PRIV_CONFIG_DIR/almanac.env" "$ALMANAC_REPO_DIR/bin/bootstrap-userland.sh"
  sudo -iu $ALMANAC_USER env ALMANAC_CONFIG_FILE="$ALMANAC_PRIV_CONFIG_DIR/almanac.env" "$ALMANAC_REPO_DIR/bin/install-user-services.sh"

EOF
