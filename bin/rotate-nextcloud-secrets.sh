#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

COMPOSE_FILE="$BOOTSTRAP_DIR/compose/nextcloud-compose.yml"

validate_rotation_secret() {
  local label="$1"
  local value="${2:-}"

  if [[ -z "$value" ]]; then
    echo "$label cannot be blank." >&2
    return 1
  fi
  if [[ "$value" == *$'\n'* || "$value" == *$'\r'* ]]; then
    echo "$label cannot contain newlines." >&2
    return 1
  fi
  if [[ "$value" == *"'"* ]]; then
    echo "$label cannot contain single quotes." >&2
    return 1
  fi

  return 0
}

nextcloud_runtime_exec_db() {
  if command -v podman >/dev/null 2>&1; then
    podman exec "$(nextcloud_db_container_name)" "$@"
    return 0
  fi

  run_compose "$COMPOSE_FILE" exec -T db "$@"
}

nextcloud_runtime_exec_app() {
  if command -v podman >/dev/null 2>&1; then
    podman exec -u 33:33 "$(nextcloud_app_container_name)" "$@"
    return 0
  fi

  run_compose "$COMPOSE_FILE" exec -T -u 33:33 app "$@"
}

nextcloud_runtime_exec_app_with_env() {
  local env_name="$1"
  local env_value="$2"
  shift 2

  if command -v podman >/dev/null 2>&1; then
    podman exec -e "${env_name}=${env_value}" -u 33:33 "$(nextcloud_app_container_name)" "$@"
    return 0
  fi

  run_compose "$COMPOSE_FILE" exec -T -e "${env_name}=${env_value}" -u 33:33 app "$@"
}

nextcloud_verify_runtime_ready() {
  nextcloud_runtime_exec_app php /var/www/html/occ status --output=json >/dev/null

  if ! curl --max-time 5 -fsS -H "Host: $NEXTCLOUD_TRUSTED_DOMAIN" \
    "http://127.0.0.1:${NEXTCLOUD_PORT}/status.php" >/dev/null 2>&1; then
    echo "Nextcloud HTTP health check failed after credential rotation." >&2
    return 1
  fi
}

nextcloud_reset_admin_password() {
  local user="$1"
  local password="$2"

  nextcloud_runtime_exec_app_with_env OC_PASS "$password" \
    php /var/www/html/occ user:resetpassword --password-from-env "$user" >/dev/null
}

nextcloud_rotate_postgres_password() {
  local old_password="$1"
  local new_password="$2"

  validate_rotation_secret "Existing Postgres password" "$old_password"
  validate_rotation_secret "New Postgres password" "$new_password"

  nextcloud_runtime_exec_db sh -eu -c '
role="$1"
new_password="$2"
psql -v ON_ERROR_STOP=1 -U "$role" -d postgres -c "ALTER ROLE \"$role\" WITH PASSWORD '\''$new_password'\''"
' sh "$POSTGRES_USER" "$new_password"
}

nextcloud_set_dbpassword_config() {
  local new_password="$1"

  nextcloud_runtime_exec_app php /var/www/html/occ config:system:set dbpassword \
    --type=string \
    --value="$new_password" >/dev/null
}

rotate_nextcloud_runtime_secrets() {
  local old_postgres_password="${POSTGRES_PASSWORD:-}"
  local old_admin_password="${NEXTCLOUD_ADMIN_PASSWORD:-}"
  local new_postgres_password="${NEXTCLOUD_ROTATE_POSTGRES_PASSWORD:-}"
  local new_admin_password="${NEXTCLOUD_ROTATE_ADMIN_PASSWORD:-}"

  if [[ "${ENABLE_NEXTCLOUD:-0}" != "1" ]]; then
    echo "Nextcloud is disabled in the active config." >&2
    return 1
  fi

  validate_rotation_secret "New Postgres password" "$new_postgres_password"
  validate_rotation_secret "New Nextcloud admin password" "$new_admin_password"
  validate_rotation_secret "Existing Postgres password" "$old_postgres_password"
  validate_rotation_secret "Existing Nextcloud admin password" "$old_admin_password"

  require_real_layout "Nextcloud secret rotation"
  nextcloud_verify_runtime_ready

  nextcloud_reset_admin_password "$NEXTCLOUD_ADMIN_USER" "$new_admin_password"
  nextcloud_rotate_postgres_password "$old_postgres_password" "$new_postgres_password"

  if ! nextcloud_set_dbpassword_config "$new_postgres_password"; then
    nextcloud_rotate_postgres_password "$new_postgres_password" "$old_postgres_password" || true
    nextcloud_reset_admin_password "$NEXTCLOUD_ADMIN_USER" "$old_admin_password" || true
    echo "Failed to update Nextcloud dbpassword config; rolled the live credentials back." >&2
    return 1
  fi

  nextcloud_verify_runtime_ready
}

rotate_nextcloud_runtime_secrets
