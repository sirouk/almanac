#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

COMPOSE_FILE="$BOOTSTRAP_DIR/compose/nextcloud-compose.yml"

dump_nextcloud_diagnostics() {
  local db_name="" redis_name="" app_name=""

  db_name="$(nextcloud_db_container_name)"
  redis_name="$(nextcloud_redis_container_name)"
  app_name="$(nextcloud_app_container_name)"

  {
    echo
    echo "Nextcloud startup diagnostics..."
    if command -v podman >/dev/null 2>&1; then
      podman pod ps || true
      podman ps --all --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' || true
      for name in "$db_name" "$redis_name" "$app_name"; do
        if podman container inspect "$name" >/dev/null 2>&1; then
          echo
          echo "Logs: $name"
          podman logs --tail 120 "$name" || true
        fi
      done
    fi
  } >&2
}

pod_exists() {
  podman pod inspect "$1" >/dev/null 2>&1
}

container_exists() {
  podman container inspect "$1" >/dev/null 2>&1
}

cleanup_legacy_compose_stack() {
  local cni_file="$HOME/.config/cni/net.d/compose_default.conflist"

  if have_compose_runtime; then
    run_compose "$COMPOSE_FILE" down >/dev/null 2>&1 || true
  fi

  if [[ -f "$cni_file" ]] && grep -q '"cniVersion": "1.0.0"' "$cni_file"; then
    rm -f "$cni_file"
  fi
}

podman_host_uid_for_container_uid() {
  local container_uid="$1"
  local subuid_start=""

  if (( container_uid == 0 )); then
    echo "$(id -u)"
    return 0
  fi

  subuid_start="$(awk -F: -v user="$(id -un)" '$1 == user { print $2; exit }' /etc/subuid 2>/dev/null || true)"
  if [[ -z "$subuid_start" ]]; then
    return 1
  fi

  echo $((subuid_start + container_uid - 1))
}

apply_vault_acls_for_nextcloud() {
  local host_uid="" mapped_www_data_uid="" acl_dirs="" acl_files=""

  mkdir -p "$VAULT_DIR"

  if ! command -v setfacl >/dev/null 2>&1; then
    echo "setfacl is required to share the vault with rootless Nextcloud safely." >&2
    return 1
  fi

  mapped_www_data_uid="$(podman_host_uid_for_container_uid 33)" || {
    echo "Could not determine the host uid mapped to container uid 33 for $(id -un)." >&2
    return 1
  }
  host_uid="$(id -u)"
  acl_dirs="u:${host_uid}:rwx,u:${mapped_www_data_uid}:rwx,m:rwx"
  acl_files="u:${host_uid}:rw-,u:${mapped_www_data_uid}:rw-,m:rw-"

  chmod 0770 "$VAULT_DIR"

  while IFS= read -r path; do
    setfacl -m "$acl_dirs" "$path"
    setfacl -d -m "$acl_dirs" "$path"
  done < <(find "$VAULT_DIR" -type d -print)

  while IFS= read -r path; do
    setfacl -m "$acl_files" "$path"
  done < <(find "$VAULT_DIR" -type f -print)
}

normalize_nextcloud_permissions() {
  if ! command -v podman >/dev/null 2>&1; then
    return 0
  fi

  apply_vault_acls_for_nextcloud

  podman unshare sh -eu <<EOF
mkdir -p "$NEXTCLOUD_DB_DIR" "$NEXTCLOUD_REDIS_DIR" "$NEXTCLOUD_HTML_DIR" "$NEXTCLOUD_DATA_DIR"
chown -R 70:70 "$NEXTCLOUD_DB_DIR"
chown -R 999:999 "$NEXTCLOUD_REDIS_DIR"
chown -R 33:33 "$NEXTCLOUD_HTML_DIR" "$NEXTCLOUD_DATA_DIR"

find "$NEXTCLOUD_HTML_DIR" -type d -exec chmod 755 {} +
find "$NEXTCLOUD_HTML_DIR" -type f -exec chmod 644 {} +
if [ -f "$NEXTCLOUD_HTML_DIR/config/config.php" ]; then
  chmod 640 "$NEXTCLOUD_HTML_DIR/config/config.php"
fi

find "$NEXTCLOUD_DATA_DIR" -type d -exec chmod 750 {} +
find "$NEXTCLOUD_DATA_DIR" -type f -exec chmod 640 {} +
find "$NEXTCLOUD_DATA_DIR" -type f -name '.htaccess' -exec chmod 644 {} +
EOF
}

nextcloud_occ() {
  if command -v podman >/dev/null 2>&1; then
    podman exec -u 33:33 "$(nextcloud_app_container_name)" php /var/www/html/occ "$@"
    return 0
  fi

  run_compose "$COMPOSE_FILE" exec -T -u 33:33 app php /var/www/html/occ "$@"
}

nextcloud_exec_www_data() {
  local command_string="$1"

  if command -v podman >/dev/null 2>&1; then
    podman exec -u 33:33 "$(nextcloud_app_container_name)" sh -lc "$command_string"
    return 0
  fi

  run_compose "$COMPOSE_FILE" exec -T -u 33:33 app sh -lc "$command_string"
}

write_nextcloud_custom_config() {
  mkdir -p "$NEXTCLOUD_CUSTOM_CONFIG_DIR" "$NEXTCLOUD_EMPTY_SKELETON_DIR"
  cat >"$NEXTCLOUD_ALMANAC_CONFIG_FILE" <<'EOF'
<?php
$CONFIG = array (
  'skeletondirectory' => '/srv/nextcloud-empty-skeleton',
);
EOF
  chmod 0644 "$NEXTCLOUD_ALMANAC_CONFIG_FILE"
}

write_nextcloud_hook_script() {
  local target="$1"

  mkdir -p "$(dirname "$target")"
  cat >"$target" <<'EOF'
#!/bin/sh
set -eu

src='/almanac-config/almanac.config.php'
dst='/var/www/html/config/almanac.config.php'

if [ -f "$src" ]; then
  cp -f "$src" "$dst"
fi
EOF
  chmod 0755 "$target"
}

write_nextcloud_post_install_hook() {
  mkdir -p "$(dirname "$NEXTCLOUD_POST_INSTALL_HOOK_FILE")"
  cat >"$NEXTCLOUD_POST_INSTALL_HOOK_FILE" <<'EOF'
#!/bin/sh
set -eu

admin_user="${NEXTCLOUD_ADMIN_USER:-}"
files_dir="/var/www/html/data/${admin_user}/files"

if [ -n "$admin_user" ] && [ -d "$files_dir" ]; then
  find "$files_dir" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
fi
EOF
  chmod 0755 "$NEXTCLOUD_POST_INSTALL_HOOK_FILE"
}

write_nextcloud_hook_scripts() {
  write_nextcloud_post_install_hook
  write_nextcloud_hook_script "$NEXTCLOUD_BEFORE_STARTING_HOOK_FILE"
}

wait_for_container_health() {
  local name="$1"
  local attempts="${2:-60}"
  local delay="${3:-2}"
  local i=0
  local status=""

  for ((i = 1; i <= attempts; i++)); do
    status="$(podman inspect --format '{{if .State.Healthcheck}}{{.State.Healthcheck.Status}}{{else}}{{.State.Status}}{{end}}' "$name" 2>/dev/null || true)"
    case "$status" in
      healthy|running)
        return 0
        ;;
      exited|stopped|configured)
        sleep "$delay"
        ;;
      *)
        sleep "$delay"
        ;;
    esac
  done

  return 1
}

wait_for_postgres_ready() {
  local attempts="${1:-60}"
  local delay="${2:-2}"
  local i=0

  for ((i = 1; i <= attempts; i++)); do
    if command -v podman >/dev/null 2>&1; then
      if podman exec "$(nextcloud_db_container_name)" pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; then
        return 0
      fi
    elif run_compose "$COMPOSE_FILE" exec -T db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$delay"
  done

  return 1
}

wait_for_redis_ready() {
  local attempts="${1:-30}"
  local delay="${2:-1}"
  local i=0

  for ((i = 1; i <= attempts; i++)); do
    if command -v podman >/dev/null 2>&1; then
      if podman exec "$(nextcloud_redis_container_name)" redis-cli ping >/dev/null 2>&1; then
        return 0
      fi
    elif run_compose "$COMPOSE_FILE" exec -T redis redis-cli ping >/dev/null 2>&1; then
      return 0
    fi
    sleep "$delay"
  done

  return 1
}

wait_for_nextcloud_occ() {
  local attempts="${1:-120}"
  local delay="${2:-2}"
  local i=0
  local status_json=""

  for ((i = 1; i <= attempts; i++)); do
    status_json="$(nextcloud_occ status --output=json 2>/dev/null || true)"
    if [[ -n "$status_json" ]] && NEXTCLOUD_STATUS_JSON="$status_json" python3 - <<'PY'
import json
import os

try:
    status = json.loads(os.environ["NEXTCLOUD_STATUS_JSON"])
except Exception:
    raise SystemExit(1)

raise SystemExit(0 if status.get("installed") is True and status.get("maintenance") is False else 1)
PY
    then
      return 0
    fi
    sleep "$delay"
  done

  return 1
}

wait_for_nextcloud_http() {
  local attempts="${1:-120}"
  local delay="${2:-2}"
  local i=0

  for ((i = 1; i <= attempts; i++)); do
    if curl --max-time 5 -fsS -H "Host: $NEXTCLOUD_TRUSTED_DOMAIN" \
      "http://127.0.0.1:${NEXTCLOUD_PORT}/status.php" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$delay"
  done

  return 1
}

nextcloud_mount_state_from_json() {
  local mount_json="$1"
  local mount_point="$2"

  NEXTCLOUD_MOUNT_JSON="$mount_json" python3 - "$mount_point" <<'PY'
import json
import os
import shlex
import sys

mount_point = sys.argv[1]
try:
    mounts = json.loads(os.environ["NEXTCLOUD_MOUNT_JSON"])
except Exception:
    mounts = []

match = None
for mount in mounts:
    if mount.get("mount_point") == mount_point:
        match = mount
        break

if match is None:
    print("mount_id=''")
    print("mount_point=''")
    print("mount_datadir=''")
    print("users_count=0")
    print("groups_count=0")
else:
    config = match.get("configuration") or {}
    print(f"mount_id={shlex.quote(str(match.get('mount_id', '')))}")
    print(f"mount_point={shlex.quote(str(match.get('mount_point', '')))}")
    print(f"mount_datadir={shlex.quote(str(config.get('datadir', '')))}")
    print(f"users_count={len(match.get('applicable_users') or [])}")
    print(f"groups_count={len(match.get('applicable_groups') or [])}")
PY
}

ensure_nextcloud_vault_mount() {
  local mount_json="" mount_id="" mount_point="" mount_datadir="" users_count=0 groups_count=0
  local parsed_state=""

  nextcloud_occ app:enable files_external >/dev/null

  mount_json="$(nextcloud_occ files_external:list --output=json 2>/dev/null || printf '[]')"
  parsed_state="$(nextcloud_mount_state_from_json "$mount_json" "$NEXTCLOUD_VAULT_MOUNT_POINT")"
  # shellcheck disable=SC2086
  eval "$parsed_state"

  if [[ -z "$mount_id" ]]; then
    nextcloud_occ files_external:create "$NEXTCLOUD_VAULT_MOUNT_POINT" local null::null -c "datadir=$NEXTCLOUD_VAULT_CONTAINER_PATH" >/dev/null
    mount_json="$(nextcloud_occ files_external:list --output=json)"
    parsed_state="$(nextcloud_mount_state_from_json "$mount_json" "$NEXTCLOUD_VAULT_MOUNT_POINT")"
    # shellcheck disable=SC2086
    eval "$parsed_state"
  fi

  if [[ -z "$mount_id" ]]; then
    echo "Nextcloud external storage mount ${NEXTCLOUD_VAULT_MOUNT_POINT} was not created." >&2
    return 1
  fi

  if [[ "$mount_point" != "$NEXTCLOUD_VAULT_MOUNT_POINT" ]]; then
    nextcloud_occ files_external:config "$mount_id" mount_point "$NEXTCLOUD_VAULT_MOUNT_POINT" >/dev/null
  fi

  if [[ "$mount_datadir" != "$NEXTCLOUD_VAULT_CONTAINER_PATH" ]]; then
    nextcloud_occ files_external:config "$mount_id" datadir "$NEXTCLOUD_VAULT_CONTAINER_PATH" >/dev/null
  fi

  if (( users_count > 0 || groups_count > 0 )); then
    nextcloud_occ files_external:applicable "$mount_id" --remove-all >/dev/null
  fi

  nextcloud_occ files_external:option "$mount_id" readonly false >/dev/null || true
  nextcloud_occ files_external:option "$mount_id" enable_sharing true >/dev/null || true

  if ! nextcloud_exec_www_data "test -w '$NEXTCLOUD_VAULT_CONTAINER_PATH'"; then
    echo "Nextcloud can see the shared vault mount but cannot write to $NEXTCLOUD_VAULT_CONTAINER_PATH." >&2
    return 1
  fi
}

run_podman_nextcloud() {
  local pod_name=""
  local db_name=""
  local redis_name=""
  local app_name=""

  pod_name="$(nextcloud_pod_name)"
  db_name="$(nextcloud_db_container_name)"
  redis_name="$(nextcloud_redis_container_name)"
  app_name="$(nextcloud_app_container_name)"

  ensure_layout
  require_real_layout "Nextcloud startup"
  write_nextcloud_custom_config
  write_nextcloud_hook_scripts
  normalize_nextcloud_permissions
  cleanup_legacy_compose_stack

  if ! pod_exists "$pod_name"; then
    podman pod create --name "$pod_name" -p "127.0.0.1:${NEXTCLOUD_PORT}:80" >/dev/null
  else
    podman pod start "$pod_name" >/dev/null 2>&1 || true
  fi

  if container_exists "$db_name"; then
    podman start "$db_name" >/dev/null 2>&1 || true
  else
    podman run -d \
      --name "$db_name" \
      --pod "$pod_name" \
      --restart unless-stopped \
      --health-cmd "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}" \
      --health-interval 10s \
      --health-timeout 5s \
      --health-retries 5 \
      -e "POSTGRES_DB=${POSTGRES_DB}" \
      -e "POSTGRES_USER=${POSTGRES_USER}" \
      -e "POSTGRES_PASSWORD=${POSTGRES_PASSWORD}" \
      -v "${NEXTCLOUD_DB_DIR}:/var/lib/postgresql/data" \
      docker.io/library/postgres:16-alpine >/dev/null
  fi

  if container_exists "$redis_name"; then
    podman start "$redis_name" >/dev/null 2>&1 || true
  else
    podman run -d \
      --name "$redis_name" \
      --pod "$pod_name" \
      --restart unless-stopped \
      --health-cmd "redis-cli ping || exit 1" \
      --health-interval 10s \
      --health-timeout 5s \
      --health-retries 5 \
      -v "${NEXTCLOUD_REDIS_DIR}:/data" \
      docker.io/library/redis:7-alpine >/dev/null
  fi

  wait_for_postgres_ready 60 2
  wait_for_redis_ready 30 1 || true

  if container_exists "$app_name"; then
    podman start "$app_name" >/dev/null 2>&1 || true
  else
    podman run -d \
      --name "$app_name" \
      --pod "$pod_name" \
      --restart unless-stopped \
      -e "POSTGRES_DB=${POSTGRES_DB}" \
      -e "POSTGRES_USER=${POSTGRES_USER}" \
      -e "POSTGRES_PASSWORD=${POSTGRES_PASSWORD}" \
      -e "POSTGRES_HOST=127.0.0.1" \
      -e "NEXTCLOUD_ADMIN_USER=${NEXTCLOUD_ADMIN_USER}" \
      -e "NEXTCLOUD_ADMIN_PASSWORD=${NEXTCLOUD_ADMIN_PASSWORD}" \
      -e "REDIS_HOST=127.0.0.1" \
      -e "NEXTCLOUD_TRUSTED_DOMAINS=localhost 127.0.0.1 ${NEXTCLOUD_TRUSTED_DOMAIN}" \
      -e "OVERWRITEPROTOCOL=https" \
      -v "${NEXTCLOUD_ALMANAC_CONFIG_FILE}:/almanac-config/almanac.config.php:ro" \
      -v "${NEXTCLOUD_HTML_DIR}:/var/www/html" \
      -v "${NEXTCLOUD_DATA_DIR}:/var/www/html/data" \
      -v "${NEXTCLOUD_POST_INSTALL_HOOK_DIR}:/docker-entrypoint-hooks.d/post-installation" \
      -v "${NEXTCLOUD_BEFORE_STARTING_HOOK_DIR}:/docker-entrypoint-hooks.d/before-starting" \
      -v "${NEXTCLOUD_EMPTY_SKELETON_DIR}:/srv/nextcloud-empty-skeleton" \
      -v "${VAULT_DIR}:/srv/vault" \
      docker.io/library/nextcloud:31-apache >/dev/null
  fi

  wait_for_nextcloud_occ 180 2
  ensure_nextcloud_vault_mount
  normalize_nextcloud_permissions
  wait_for_nextcloud_http 180 2
}

if [[ "$ENABLE_NEXTCLOUD" != "1" ]]; then
  echo "Nextcloud is disabled in config."
  exit 0
fi

export NEXTCLOUD_PORT NEXTCLOUD_TRUSTED_DOMAIN
export POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD
export NEXTCLOUD_ADMIN_USER NEXTCLOUD_ADMIN_PASSWORD
export NEXTCLOUD_DB_DIR NEXTCLOUD_REDIS_DIR NEXTCLOUD_HTML_DIR NEXTCLOUD_DATA_DIR
export NEXTCLOUD_CUSTOM_CONFIG_DIR NEXTCLOUD_EMPTY_SKELETON_DIR NEXTCLOUD_ALMANAC_CONFIG_FILE
export NEXTCLOUD_HOOKS_DIR NEXTCLOUD_PRE_INSTALL_HOOK_DIR NEXTCLOUD_POST_INSTALL_HOOK_DIR NEXTCLOUD_BEFORE_STARTING_HOOK_DIR
export NEXTCLOUD_PRE_INSTALL_HOOK_FILE NEXTCLOUD_POST_INSTALL_HOOK_FILE NEXTCLOUD_BEFORE_STARTING_HOOK_FILE VAULT_DIR

trap dump_nextcloud_diagnostics ERR

if command -v podman >/dev/null 2>&1; then
  run_podman_nextcloud
  exit 0
fi

if have_compose_runtime; then
  require_real_layout "Nextcloud startup"
  write_nextcloud_custom_config
  write_nextcloud_hook_scripts
  run_compose "$COMPOSE_FILE" up -d
  wait_for_nextcloud_occ 180 2
  ensure_nextcloud_vault_mount
  normalize_nextcloud_permissions
  wait_for_nextcloud_http 180 2
  exit 0
fi

echo "No Nextcloud runtime found. Install podman or docker compose."
exit 1
