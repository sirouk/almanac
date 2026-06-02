#!/usr/bin/env bash
set -euo pipefail

ARCLINK_PREREQ_SURFACE="${ARCLINK_PREREQ_SURFACE:-control}"
ARCLINK_SKIP_PREREQ_INSTALL="${ARCLINK_SKIP_PREREQ_INSTALL:-0}"
ARCLINK_PREREQ_CHECK_ONLY="${ARCLINK_PREREQ_CHECK_ONLY:-0}"
ARCLINK_PREREQ_JSON="${ARCLINK_PREREQ_JSON:-0}"
ARCLINK_PREREQ_AUDIT_FILE="${ARCLINK_PREREQ_AUDIT_FILE:-${STATE_DIR:+$STATE_DIR/arclink-prereq-audit.jsonl}}"
ARCLINK_PREREQ_DOCKER_INSTALL_URL="${ARCLINK_PREREQ_DOCKER_INSTALL_URL:-https://get.docker.com}"
ARCLINK_PREREQ_PYTHON_PACKAGES="${ARCLINK_PREREQ_PYTHON_PACKAGES:-}"
ARCLINK_PREREQ_WIREGUARD="${ARCLINK_PREREQ_WIREGUARD:-0}"

prereq_command_exists() {
  command -v "$1" >/dev/null 2>&1
}

prereq_truthy() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

prereq_detect_package_manager() {
  if [[ -n "${ARCLINK_PREREQ_PACKAGE_MANAGER:-}" ]]; then
    printf '%s\n' "$ARCLINK_PREREQ_PACKAGE_MANAGER"
  elif prereq_command_exists apt-get; then
    printf '%s\n' "apt"
  elif prereq_command_exists dnf; then
    printf '%s\n' "dnf"
  else
    printf '%s\n' "unsupported"
  fi
}

prereq_have_python_pip() {
  prereq_command_exists python3 && python3 -m pip --version >/dev/null 2>&1
}

prereq_have_python_venv() {
  prereq_command_exists python3 && python3 -m venv --help >/dev/null 2>&1
}

prereq_have_python_package() {
  local package="$1"
  python3 - "$package" <<'PY' >/dev/null 2>&1
import importlib.util
import sys

name = sys.argv[1].replace("-", "_")
raise SystemExit(0 if importlib.util.find_spec(name) else 1)
PY
}

prereq_have_docker_compose() {
  prereq_command_exists docker && docker compose version >/dev/null 2>&1
}

prereq_have_wireguard_tools() {
  prereq_command_exists wg && prereq_command_exists wg-quick
}

prereq_audit() {
  local action="$1"
  local target="$2"
  local status="$3"
  local detail="${4:-}"
  local audit_file="${ARCLINK_PREREQ_AUDIT_FILE:-}"

  if [[ -z "$audit_file" ]]; then
    return 0
  fi
  mkdir -p "$(dirname "$audit_file")" 2>/dev/null || return 0
  if prereq_command_exists python3; then
    python3 - "$audit_file" "$ARCLINK_PREREQ_SURFACE" "$action" "$target" "$status" "$detail" <<'PY' || true
import json
import sys
from datetime import datetime, timezone

path, surface, action, target, status, detail = sys.argv[1:7]
payload = {
    "ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "surface": surface,
    "action": action,
    "target": target,
    "status": status,
    "detail": detail,
}
with open(path, "a", encoding="utf-8") as handle:
    handle.write(json.dumps(payload, sort_keys=True) + "\n")
PY
  else
    printf '{"surface":"%s","action":"%s","target":"%s","status":"%s"}\n' \
      "$ARCLINK_PREREQ_SURFACE" "$action" "$target" "$status" >>"$audit_file" 2>/dev/null || true
  fi
}

prereq_json_array() {
  local name="$1"
  local item=""
  local first=1
  shift
  printf '{"%s":[' "$name"
  for item in "$@"; do
    item="${item//\\/\\\\}"
    item="${item//\"/\\\"}"
    if [[ "$first" == "1" ]]; then
      first=0
    else
      printf ','
    fi
    printf '"%s"' "$item"
  done
  printf ']}\n'
}

prereq_install_os_packages() {
  local package_manager="$1"
  shift
  local -a packages=("$@")

  if (( ${#packages[@]} == 0 )); then
    return 0
  fi
  prereq_audit "install_packages" "$package_manager" "started" "${packages[*]}"
  case "$package_manager" in
    apt)
      if ! apt-get update; then
        prereq_audit "install_packages" "$package_manager" "failed" "apt-get update failed"
        return 1
      fi
      if ! DEBIAN_FRONTEND=noninteractive apt-get install -y "${packages[@]}"; then
        prereq_audit "install_packages" "$package_manager" "failed" "apt-get install failed"
        return 1
      fi
      ;;
    dnf)
      if ! dnf install -y "${packages[@]}"; then
        prereq_audit "install_packages" "$package_manager" "failed" "dnf install failed"
        return 1
      fi
      ;;
    *)
      prereq_audit "install_packages" "$package_manager" "failed" "unsupported package manager"
      echo "ArcLink prerequisite installation supports apt-get and dnf hosts only." >&2
      return 1
      ;;
  esac
  prereq_audit "install_packages" "$package_manager" "completed" "${packages[*]}"
}

prereq_install_docker() {
  if prereq_have_docker_compose; then
    prereq_audit "install_docker" "docker-compose-plugin" "present"
    return 0
  fi
  if prereq_truthy "$ARCLINK_PREREQ_CHECK_ONLY" || prereq_truthy "$ARCLINK_SKIP_PREREQ_INSTALL"; then
    prereq_audit "install_docker" "docker-compose-plugin" "planned"
    echo "Docker Engine with the Compose plugin is missing." >&2
    return 1
  fi
  if ! prereq_command_exists curl; then
    prereq_audit "install_docker" "docker-compose-plugin" "failed" "curl missing"
    echo "curl is required before installing Docker from $ARCLINK_PREREQ_DOCKER_INSTALL_URL." >&2
    return 1
  fi
  prereq_audit "install_docker" "docker-compose-plugin" "started" "$ARCLINK_PREREQ_DOCKER_INSTALL_URL"
  if ! curl -fsSL "$ARCLINK_PREREQ_DOCKER_INSTALL_URL" | sh; then
    prereq_audit "install_docker" "docker-compose-plugin" "failed" "docker installer failed"
    echo "Docker installer failed while fetching or running $ARCLINK_PREREQ_DOCKER_INSTALL_URL." >&2
    return 1
  fi
  if ! prereq_have_docker_compose; then
    prereq_audit "install_docker" "docker-compose-plugin" "failed" "docker compose still unavailable"
    echo "Docker installer finished, but docker compose is still unavailable." >&2
    return 1
  fi
  prereq_audit "install_docker" "docker-compose-plugin" "completed"
}

prereq_install_wireguard_tools() {
  local package_manager="$1"

  if ! prereq_truthy "$ARCLINK_PREREQ_WIREGUARD"; then
    return 0
  fi
  if prereq_have_wireguard_tools; then
    prereq_audit "install_wireguard" "wireguard-tools" "present"
    return 0
  fi
  if prereq_truthy "$ARCLINK_PREREQ_CHECK_ONLY" || prereq_truthy "$ARCLINK_SKIP_PREREQ_INSTALL"; then
    prereq_audit "install_wireguard" "wireguard-tools" "planned"
    echo "WireGuard tools are missing." >&2
    return 1
  fi
  prereq_audit "install_wireguard" "wireguard-tools" "started"
  if ! prereq_install_os_packages "$package_manager" wireguard-tools; then
    prereq_audit "install_wireguard" "wireguard-tools" "failed" "package install failed"
    return 1
  fi
  if ! prereq_have_wireguard_tools; then
    prereq_audit "install_wireguard" "wireguard-tools" "failed" "wg or wg-quick unavailable after install"
    echo "wireguard-tools installed, but wg or wg-quick is still unavailable." >&2
    return 1
  fi
  prereq_audit "install_wireguard" "wireguard-tools" "completed"
}

prereq_install_python_packages() {
  local package=""
  local -a missing=()

  if [[ -z "$ARCLINK_PREREQ_PYTHON_PACKAGES" ]]; then
    return 0
  fi
  if ! prereq_have_python_pip; then
    prereq_audit "install_python_packages" "pip" "failed" "pip missing"
    echo "python3 pip is required before installing ArcLink Python prerequisites." >&2
    return 1
  fi
  for package in $ARCLINK_PREREQ_PYTHON_PACKAGES; do
    if ! prereq_have_python_package "$package"; then
      missing+=("$package")
    fi
  done
  if (( ${#missing[@]} == 0 )); then
    prereq_audit "install_python_packages" "python3" "present"
    return 0
  fi
  if prereq_truthy "$ARCLINK_PREREQ_CHECK_ONLY" || prereq_truthy "$ARCLINK_SKIP_PREREQ_INSTALL"; then
    prereq_audit "install_python_packages" "python3" "planned" "${missing[*]}"
    echo "Missing Python packages: ${missing[*]}" >&2
    return 1
  fi
  prereq_audit "install_python_packages" "python3" "started" "${missing[*]}"
  python3 -m pip install "${missing[@]}"
  prereq_audit "install_python_packages" "python3" "completed" "${missing[*]}"
}

ensure_arclink_prereqs() {
  local package_manager=""
  local check_only="$ARCLINK_PREREQ_CHECK_ONLY"
  local json="$ARCLINK_PREREQ_JSON"
  local arg=""
  local -a missing_commands=()
  local -a missing_packages=()
  local -a package_list=()
  local -a planned=()

  while (($#)); do
    arg="$1"
    case "$arg" in
      --surface)
        ARCLINK_PREREQ_SURFACE="${2:-}"
        shift 2
        ;;
      --skip-prereq-install|--check-only|--verify-only)
        ARCLINK_SKIP_PREREQ_INSTALL=1
        check_only=1
        shift
        ;;
      --json)
        json=1
        shift
        ;;
      *)
        echo "Unknown prerequisite option: $arg" >&2
        return 2
        ;;
    esac
  done
  if prereq_truthy "$ARCLINK_SKIP_PREREQ_INSTALL"; then
    check_only=1
  fi
  ARCLINK_PREREQ_CHECK_ONLY="$check_only"

  package_manager="$(prereq_detect_package_manager)"
  case "$package_manager" in
    apt)
      package_list=(ca-certificates curl jq rsync openssh-client python3 python3-pip python3-venv)
      ;;
    dnf)
      package_list=(ca-certificates curl jq rsync openssh-clients python3 python3-pip)
      ;;
    *)
      prereq_audit "detect_package_manager" "$package_manager" "failed"
      echo "Unsupported OS package manager. ArcLink can install prerequisites with apt-get or dnf." >&2
      return 1
      ;;
  esac

  prereq_command_exists curl || missing_commands+=(curl)
  prereq_command_exists jq || missing_commands+=(jq)
  prereq_command_exists rsync || missing_commands+=(rsync)
  prereq_command_exists ssh || missing_commands+=(openssh-client)
  prereq_command_exists python3 || missing_commands+=(python3)
  prereq_have_python_pip || missing_commands+=(python3-pip)
  prereq_have_python_venv || missing_commands+=(python3-venv)
  prereq_have_docker_compose || missing_commands+=(docker-compose-plugin)

  if (( ${#missing_commands[@]} > 0 )); then
    for arg in "${missing_commands[@]}"; do
      case "$arg" in
        docker-compose-plugin) ;;
        openssh-client)
          if [[ "$package_manager" == "dnf" ]]; then
            missing_packages+=(openssh-clients)
          else
            missing_packages+=(openssh-client)
          fi
          ;;
        *)
          if [[ " ${package_list[*]} " == *" $arg "* ]]; then
            missing_packages+=("$arg")
          fi
          ;;
      esac
    done
  fi

  if (( ${#missing_packages[@]} > 0 )); then
    if prereq_truthy "$check_only"; then
      prereq_audit "install_packages" "$package_manager" "planned" "${missing_packages[*]}"
      planned+=("packages:${missing_packages[*]}")
    else
      prereq_install_os_packages "$package_manager" "${missing_packages[@]}"
    fi
  fi

  if prereq_have_docker_compose; then
    prereq_audit "install_docker" "docker-compose-plugin" "present"
  elif prereq_truthy "$check_only"; then
    prereq_audit "install_docker" "docker-compose-plugin" "planned"
    planned+=("docker-compose-plugin")
  else
    prereq_install_docker
  fi

  if ! prereq_install_python_packages; then
    planned+=("python-packages")
  fi

  if ! prereq_install_wireguard_tools "$package_manager"; then
    planned+=("wireguard-tools")
  fi

  if (( ${#planned[@]} > 0 )); then
    if prereq_truthy "$json"; then
      prereq_json_array planned "${planned[@]}"
    else
      echo "ArcLink prerequisite installation is disabled; missing prerequisites: ${planned[*]}" >&2
    fi
    return 1
  fi

  prereq_audit "ensure_prereqs" "$ARCLINK_PREREQ_SURFACE" "completed"
  if prereq_truthy "$json"; then
    python3 - "$ARCLINK_PREREQ_SURFACE" "$package_manager" <<'PY'
import json
import sys

print(json.dumps({"ok": True, "surface": sys.argv[1], "package_manager": sys.argv[2]}, sort_keys=True))
PY
  else
    echo "ArcLink prerequisites are ready for $ARCLINK_PREREQ_SURFACE."
  fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  ensure_arclink_prereqs "$@"
fi
