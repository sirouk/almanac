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
  python3 - "$ACCESS_STATE_FILE" "$HERMES_HOME" <<'PY'
import json
import shlex
import sys
from pathlib import Path

state = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
hermes_home = Path(sys.argv[2])
code_state_dir = hermes_home / "state" / "code-server"
config_dir = code_state_dir / "config"
data_dir = code_state_dir / "data"
app_name = f"Almanac Agent Code ({state.get('unix_user') or 'agent'})"
values = {
    "CODE_PORT": str(state["code_port"]),
    "PASSWORD": str(state["password"]),
    "IMAGE": str(state.get("code_server_image") or "docker.io/codercom/code-server:4.116.0"),
    "CONTAINER_NAME": str(state.get("code_container_name") or "almanac-agent-code"),
    "CONFIG_DIR": str(config_dir),
    "DATA_DIR": str(data_dir),
    "APP_NAME": app_name,
}
for key, value in values.items():
    print(f"{key}={shlex.quote(value)}")
PY
)"

mkdir -p "$CONFIG_DIR" "$DATA_DIR"

python3 - "$CONFIG_DIR" <<'PY'
import json
import os
import sys
import tempfile
from pathlib import Path

config_dir = Path(sys.argv[1])
user_dir = config_dir / "User"
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

changed = False
if not str(settings.get("workbench.colorTheme") or "").strip():
    settings["workbench.colorTheme"] = "Default Dark+"
    changed = True

if changed:
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
PY

exec podman run \
  --rm \
  --replace \
  --name "$CONTAINER_NAME" \
  --pull=missing \
  --user 0:0 \
  -p "127.0.0.1:${CODE_PORT}:8080" \
  -e PASSWORD="$PASSWORD" \
  -e HOME=/home/coder \
  -v "$WORKSPACE_HOME:/workspace:rw" \
  -v "$CONFIG_DIR:/home/coder/.config/code-server:rw" \
  -v "$DATA_DIR:/home/coder/.local/share/code-server:rw" \
  "$IMAGE" \
  --bind-addr 0.0.0.0:8080 \
  --auth password \
  --app-name "$APP_NAME" \
  /workspace
