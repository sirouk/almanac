#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <access-state-file> <workspace-home> <hermes-home>" >&2
  exit 2
fi

ACCESS_STATE_FILE="$1"
WORKSPACE_HOME="$2"
HERMES_HOME="$3"

if [[ ! -f "$ACCESS_STATE_FILE" ]]; then
  echo "Access state file not found: $ACCESS_STATE_FILE" >&2
  exit 1
fi

if ! command -v podman >/dev/null 2>&1; then
  echo "podman is required for the agent code workspace." >&2
  exit 1
fi

eval "$(
  python3 - "$ACCESS_STATE_FILE" "$WORKSPACE_HOME" "$HERMES_HOME" <<'PY'
import json
import os
import shlex
import sys
from pathlib import Path

state = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
workspace_home = Path(sys.argv[2])
hermes_home = Path(sys.argv[3])
code_state_dir = hermes_home / "state" / "code-server"
config_dir = code_state_dir / "config"
data_dir = code_state_dir / "data"
workspace_dir = code_state_dir / "workspace"
workspace_file = workspace_dir / "almanac.code-workspace"
app_name = f"Almanac Agent Code ({state.get('unix_user') or 'agent'})"

vault_dir = ""
vault_alias = ""

def symlink_target_dir(candidate: Path) -> str:
    if candidate.is_symlink():
        target = os.readlink(candidate)
        if not os.path.isabs(target):
            target = str((candidate.parent / target).resolve(strict=False))
        if Path(target).is_dir():
            return target
    return ""

for alias_name in ("Almanac", "Vault"):
    target = symlink_target_dir(workspace_home / alias_name)
    if target:
        vault_dir = target
        vault_alias = alias_name
        break

if not vault_dir:
    for alias_name in ("Almanac", "Vault"):
        target = symlink_target_dir(hermes_home / alias_name)
        if target:
            vault_dir = target
            break

if vault_dir and vault_alias != "Almanac":
    almanac_alias = workspace_home / "Almanac"
    if not almanac_alias.exists() and not almanac_alias.is_symlink():
        try:
            almanac_alias.symlink_to(vault_dir)
            vault_alias = "Almanac"
        except OSError:
            pass

vault_container_dir = "/almanac-vault"
workspace_container_dir = "/almanac-workspace"
workspace_container_file = f"{workspace_container_dir}/almanac.code-workspace"
open_path = workspace_container_file if vault_dir else "/workspace"

values = {
    "CODE_PORT": str(state["code_port"]),
    "PASSWORD": str(state["password"]),
    "IMAGE": str(state.get("code_server_image") or "docker.io/codercom/code-server:4.116.0"),
    "CONTAINER_NAME": str(state.get("code_container_name") or "almanac-agent-code"),
    "CONFIG_DIR": str(config_dir),
    "DATA_DIR": str(data_dir),
    "WORKSPACE_DIR": str(workspace_dir),
    "WORKSPACE_FILE": str(workspace_file),
    "VAULT_DIR": vault_dir,
    "VAULT_CONTAINER_DIR": vault_container_dir,
    "WORKSPACE_CONTAINER_DIR": workspace_container_dir,
    "OPEN_PATH": open_path,
    "APP_NAME": app_name,
}
for key, value in values.items():
    print(f"{key}={shlex.quote(value)}")
PY
)"

mkdir -p "$CONFIG_DIR" "$DATA_DIR" "$WORKSPACE_DIR"

python3 - "$CONFIG_DIR" "$DATA_DIR" "$WORKSPACE_FILE" "${VAULT_DIR:-}" "${VAULT_CONTAINER_DIR:-/almanac-vault}" <<'PY'
import json
import os
import sys
import tempfile
from pathlib import Path

config_dir = Path(sys.argv[1])
data_dir = Path(sys.argv[2])
workspace_file = Path(sys.argv[3])
vault_dir = sys.argv[4].strip()
vault_container_dir = sys.argv[5].strip() or "/almanac-vault"
legacy_user_dir = config_dir / "User"
user_dir = data_dir / "User"
settings_path = user_dir / "settings.json"
user_dir.mkdir(parents=True, exist_ok=True)

settings = {}
if settings_path.is_file():
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        if not isinstance(settings, dict):
            settings = {}
    except Exception:
        settings = {}
elif (legacy_user_dir / "settings.json").is_file():
    # Older Almanac builds seeded this file under the config dir, but
    # code-server reads VS Code user settings from the data dir.
    try:
        legacy_settings = json.loads((legacy_user_dir / "settings.json").read_text(encoding="utf-8"))
        if isinstance(legacy_settings, dict):
            settings = legacy_settings
    except Exception:
        settings = {}

changed = False
if not str(settings.get("workbench.colorTheme") or "").strip():
    settings["workbench.colorTheme"] = "Default Dark Modern"
    changed = True

if changed or not settings_path.is_file():
    fd, tmp_path = tempfile.mkstemp(dir=str(user_dir), prefix=".settings-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(settings, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, settings_path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

if vault_dir:
    workspace_file.parent.mkdir(parents=True, exist_ok=True)
    workspace = {
        "folders": [
            {"name": "Workspace", "path": "/workspace"},
            {"name": "Almanac", "path": vault_container_dir},
        ],
        "settings": {},
    }
    fd, tmp_path = tempfile.mkstemp(dir=str(workspace_file.parent), prefix=".workspace-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(workspace, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, workspace_file)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
else:
    try:
        workspace_file.unlink()
    except FileNotFoundError:
        pass
PY

mount_args=(
  -v "$WORKSPACE_HOME:/workspace:rw"
  -v "$CONFIG_DIR:/home/coder/.config/code-server:rw"
  -v "$DATA_DIR:/home/coder/.local/share/code-server:rw"
)

if [[ -n "${VAULT_DIR:-}" && -d "$VAULT_DIR" ]]; then
  # Present Almanac as a first-class VS Code workspace folder instead of
  # relying on symlink traversal across container bind-mount boundaries.
  mount_args+=(
    -v "$VAULT_DIR:$VAULT_CONTAINER_DIR:rw"
    -v "$WORKSPACE_DIR:$WORKSPACE_CONTAINER_DIR:ro"
    # Keep the host-level ~/Almanac symlink valid inside the container too.
    -v "$VAULT_DIR:$VAULT_DIR:rw"
  )
fi

exec podman run \
  --rm \
  --replace \
  --name "$CONTAINER_NAME" \
  --pull=missing \
  --user 0:0 \
  -p "127.0.0.1:${CODE_PORT}:8080" \
  -e PASSWORD="$PASSWORD" \
  -e HOME=/home/coder \
  "${mount_args[@]}" \
  "$IMAGE" \
  --bind-addr 0.0.0.0:8080 \
  --auth password \
  --app-name "$APP_NAME" \
  "$OPEN_PATH"
