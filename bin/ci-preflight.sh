#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_ROOT="$(mktemp -d /tmp/almanac-preflight.XXXXXX)"

cleanup() {
  rm -rf "$TMP_ROOT"
}

trap cleanup EXIT

log() {
  printf '[preflight] %s\n' "$*"
}

write_test_pdf() {
  local target="$1"

  python3 - "$target" <<'PY'
import sys
from pathlib import Path

target = Path(sys.argv[1])
target.parent.mkdir(parents=True, exist_ok=True)
target.write_bytes(
    b"%PDF-1.4\n"
    b"1 0 obj<<>>endobj\n"
    b"trailer<<>>\n%%EOF\n"
)
PY
}

setup_fake_pdftotext() {
  local fakebin="$1"

  mkdir -p "$fakebin"
  cat >"$fakebin/pdftotext" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -enc)
      shift 2
      ;;
    *)
      args+=("$1")
      shift
      ;;
  esac
done

if [[ "${#args[@]}" -lt 2 ]]; then
  echo "fake pdftotext expected input and output markers" >&2
  exit 1
fi

if [[ "${args[-1]}" == "-" ]]; then
  printf 'Chutes MESH preflight PDF\n'
else
  printf 'Chutes MESH preflight PDF\n' >"${args[-1]}"
fi
EOF
  chmod +x "$fakebin/pdftotext"
}

setup_fake_pdftoppm() {
  local fakebin="$1"

  mkdir -p "$fakebin"
  cat >"$fakebin/pdftoppm" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "fake pdftoppm expected an output prefix" >&2
  exit 1
fi

prefix="${@: -1}"

python3 - "$prefix-1.png" <<'PY'
import base64
import sys
from pathlib import Path

png_bytes = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlTH0kAAAAASUVORK5CYII="
)
target = Path(sys.argv[1])
target.parent.mkdir(parents=True, exist_ok=True)
target.write_bytes(png_bytes)
PY
EOF
  chmod +x "$fakebin/pdftoppm"
}

setup_fake_runtime_python() {
  local runtime_dir="$1"
  local bin_dir="$runtime_dir/hermes-venv/bin"
  mkdir -p "$bin_dir"
  ln -sf "$(command -v python3)" "$bin_dir/python3"
}

start_fake_vision_server() {
  local request_log="$1"
  local port_file="$2"
  local server_log="$3"
  local server_py="$TMP_ROOT/fake-vision-server.py"

  cat >"$server_py" <<'PY'
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

request_log = Path(sys.argv[1])
port_file = Path(sys.argv[2])


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        entry = {
            "path": self.path,
            "headers": {
                "authorization": self.headers.get("Authorization"),
                "content_type": self.headers.get("Content-Type"),
            },
            "body": json.loads(body),
        }
        if request_log.exists():
            payload = json.loads(request_log.read_text(encoding="utf-8"))
        else:
            payload = []
        payload.append(entry)
        request_log.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        response = {
            "choices": [
                {
                    "message": {
                        "content": "- Diagram shows Chutes MESH routing and node links.\n- Visual layout adds topology context beyond OCR text."
                    }
                }
            ]
        }
        payload = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):  # noqa: A003
        return


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
port_file.write_text(str(server.server_port), encoding="utf-8")
server.serve_forever()
PY

  python3 "$server_py" "$request_log" "$port_file" >"$server_log" 2>&1 &
  echo $!
}

run_shell_lint() {
  local files=("$ROOT_DIR/test.sh")
  local rel=""

  while IFS= read -r rel; do
    files+=("$ROOT_DIR/$rel")
  done < <(cd "$ROOT_DIR" && rg --files bin -g '*.sh')

  log "bash -n on ${#files[@]} shell scripts"
  bash -n "${files[@]}"
}

run_python_checks() {
  log "python compile check for control-plane and PDF ingest modules"
  PYTHONPYCACHEPREFIX="$TMP_ROOT/pycache" python3 -m py_compile \
    "$ROOT_DIR/bin/pdf-ingest.py" \
    "$ROOT_DIR/python/almanac_control.py" \
    "$ROOT_DIR/python/almanac_ctl.py"
}

run_systemd_verify() {
  local verify_log=""

  if ! command -v systemd-analyze >/dev/null 2>&1; then
    log "systemd-analyze not present, skipping unit verification"
    return 0
  fi

  verify_log="$(mktemp /tmp/almanac-systemd-verify.XXXXXX.log)"
  if ! systemd-analyze verify \
    "$ROOT_DIR"/systemd/user/*.service \
    "$ROOT_DIR"/systemd/user/*.timer >"$verify_log" 2>&1; then
    cat "$verify_log" >&2
    rm -f "$verify_log"
    return 1
  fi
  rm -f "$verify_log"
  log "systemd unit verification passed"
}

run_pdf_ingest_preflight() {
  local fakebin="$TMP_ROOT/fakebin"
  local repo_dir="$TMP_ROOT/repo"
  local priv_dir="$repo_dir/almanac-priv"
  local vault_dir="$priv_dir/vault"
  local state_dir="$priv_dir/state"
  local runtime_dir="$state_dir/runtime"
  local pdf_path="$vault_dir/Inbox/chutes-mesh-preflight.pdf"
  local generated_md="$state_dir/pdf-ingest/markdown/Inbox/chutes-mesh-preflight-pdf.md"
  local status_json="$state_dir/pdf-ingest/status.json"

  mkdir -p "$repo_dir"
  setup_fake_pdftotext "$fakebin"
  setup_fake_runtime_python "$runtime_dir"
  write_test_pdf "$pdf_path"

  log "exercising pdf-ingest create/update/delete flow"

  env \
    PATH="$fakebin:$PATH" \
    ALMANAC_ALLOW_SCAFFOLD_DEFAULTS=1 \
    ALMANAC_REPO_DIR="$repo_dir" \
    ALMANAC_PRIV_DIR="$priv_dir" \
    VAULT_DIR="$vault_dir" \
    STATE_DIR="$state_dir" \
    PDF_INGEST_EXTRACTOR=auto \
    PDF_INGEST_TRIGGER_QMD_REFRESH=0 \
    "$ROOT_DIR/bin/pdf-ingest.sh" >/tmp/almanac-preflight-ingest.log

  [[ -f "$generated_md" ]]
  grep -q "Chutes MESH preflight PDF" "$generated_md"
  python3 - "$status_json" <<'PY'
import json
import sys
from pathlib import Path

status = json.loads(Path(sys.argv[1]).read_text())
assert status["backend"] == "pdftotext"
assert int(status["created"]) == 1
assert int(status["failed"]) == 0
PY

  env \
    PATH="$fakebin:$PATH" \
    ALMANAC_ALLOW_SCAFFOLD_DEFAULTS=1 \
    ALMANAC_REPO_DIR="$repo_dir" \
    ALMANAC_PRIV_DIR="$priv_dir" \
    VAULT_DIR="$vault_dir" \
    STATE_DIR="$state_dir" \
    PDF_INGEST_EXTRACTOR=auto \
    PDF_INGEST_TRIGGER_QMD_REFRESH=0 \
    "$ROOT_DIR/bin/pdf-ingest.sh" --quiet

  python3 - "$status_json" <<'PY'
import json
import sys
from pathlib import Path

status = json.loads(Path(sys.argv[1]).read_text())
assert int(status["unchanged"]) >= 1
assert int(status["failed"]) == 0
PY

  rm -f "$pdf_path"

  env \
    PATH="$fakebin:$PATH" \
    ALMANAC_ALLOW_SCAFFOLD_DEFAULTS=1 \
    ALMANAC_REPO_DIR="$repo_dir" \
    ALMANAC_PRIV_DIR="$priv_dir" \
    VAULT_DIR="$vault_dir" \
    STATE_DIR="$state_dir" \
    PDF_INGEST_EXTRACTOR=auto \
    PDF_INGEST_TRIGGER_QMD_REFRESH=0 \
    "$ROOT_DIR/bin/pdf-ingest.sh" --quiet

  [[ ! -e "$generated_md" ]]
  python3 - "$status_json" <<'PY'
import json
import sys
from pathlib import Path

status = json.loads(Path(sys.argv[1]).read_text())
assert int(status["removed"]) == 1
assert int(status["total_pdfs"]) == 0
assert int(status["failed"]) == 0
PY
}

run_pdf_ingest_vision_preflight() {
  local fakebin="$TMP_ROOT/fakevision-bin"
  local repo_dir="$TMP_ROOT/vision-repo"
  local priv_dir="$repo_dir/almanac-priv"
  local vault_dir="$priv_dir/vault"
  local state_dir="$priv_dir/state"
  local runtime_dir="$state_dir/runtime"
  local pdf_path="$vault_dir/Inbox/chutes-mesh-vision.pdf"
  local generated_md="$state_dir/pdf-ingest/markdown/Inbox/chutes-mesh-vision-pdf.md"
  local status_json="$state_dir/pdf-ingest/status.json"
  local request_log="$TMP_ROOT/fake-vision-request.json"
  local port_file="$TMP_ROOT/fake-vision-port.txt"
  local server_log="$TMP_ROOT/fake-vision-server.log"
  local server_pid=""
  local vision_port=""

  mkdir -p "$repo_dir"
  setup_fake_pdftotext "$fakebin"
  setup_fake_pdftoppm "$fakebin"
  setup_fake_runtime_python "$runtime_dir"
  write_test_pdf "$pdf_path"

  log "exercising pdf-ingest vision caption flow"

  server_pid="$(start_fake_vision_server "$request_log" "$port_file" "$server_log")"
  trap 'kill "${server_pid:-}" 2>/dev/null || true; cleanup' EXIT

  for _ in $(seq 1 40); do
    if [[ -s "$port_file" ]]; then
      break
    fi
    sleep 0.1
  done
  [[ -s "$port_file" ]]
  vision_port="$(cat "$port_file")"

  env \
    PATH="$fakebin:$PATH" \
    ALMANAC_ALLOW_SCAFFOLD_DEFAULTS=1 \
    ALMANAC_REPO_DIR="$repo_dir" \
    ALMANAC_PRIV_DIR="$priv_dir" \
    VAULT_DIR="$vault_dir" \
    STATE_DIR="$state_dir" \
    PDF_INGEST_EXTRACTOR=auto \
    PDF_INGEST_TRIGGER_QMD_REFRESH=0 \
    PDF_VISION_ENDPOINT="http://127.0.0.1:$vision_port/v1" \
    PDF_VISION_MODEL="fake-vision-model" \
    PDF_VISION_API_KEY="fake-secret-key" \
    PDF_VISION_MAX_PAGES=1 \
    "$ROOT_DIR/bin/pdf-ingest.sh" --quiet

  [[ -f "$generated_md" ]]
  grep -q "## Visual Notes" "$generated_md"
  grep -q "Diagram shows Chutes MESH routing and node links." "$generated_md"

  python3 - "$status_json" "$request_log" <<'PY'
import json
import sys
from pathlib import Path

status = json.loads(Path(sys.argv[1]).read_text())
requests = json.loads(Path(sys.argv[2]).read_text())
request = requests[-1]

assert status["vision_enabled"] is True
assert status["vision_model"] == "fake-vision-model"
assert int(status["vision_pages_rendered"]) == 1
assert int(status["vision_pages_captioned"]) == 1
assert int(status["vision_pages_failed"]) == 0
assert len(requests) == 1
assert request["path"] == "/v1/chat/completions"
assert request["headers"]["authorization"] == "Bearer fake-secret-key"
messages = request["body"]["messages"]
assert messages[1]["content"][1]["type"] == "image_url"
PY

  rm -f "$request_log"
  printf '\n' >>"$pdf_path"

  env \
    PATH="$fakebin:$PATH" \
    ALMANAC_ALLOW_SCAFFOLD_DEFAULTS=1 \
    ALMANAC_REPO_DIR="$repo_dir" \
    ALMANAC_PRIV_DIR="$priv_dir" \
    VAULT_DIR="$vault_dir" \
    STATE_DIR="$state_dir" \
    PDF_INGEST_EXTRACTOR=auto \
    PDF_INGEST_TRIGGER_QMD_REFRESH=0 \
    PDF_VISION_ENDPOINT="http://127.0.0.1:$vision_port/v1/chat/completions" \
    PDF_VISION_MODEL="fake-vision-model" \
    PDF_VISION_API_KEY="fake-secret-key" \
    PDF_VISION_MAX_PAGES=1 \
    "$ROOT_DIR/bin/pdf-ingest.sh" --quiet

  python3 - "$status_json" "$request_log" <<'PY'
import json
import sys
from pathlib import Path

status = json.loads(Path(sys.argv[1]).read_text())
requests = json.loads(Path(sys.argv[2]).read_text())

assert int(status["created"]) + int(status["updated"]) >= 1
assert len(requests) == 1
assert requests[0]["path"] == "/v1/chat/completions"
PY

  kill "$server_pid" 2>/dev/null || true
  wait "$server_pid" 2>/dev/null || true
  trap cleanup EXIT
}

wait_for_path_state() {
  local path="$1"
  local desired="$2"
  local attempts="${3:-20}"
  local delay="${4:-0.25}"
  local i=""

  for ((i = 1; i <= attempts; i++)); do
    if [[ "$desired" == "present" && -e "$path" ]]; then
      return 0
    fi
    if [[ "$desired" == "absent" && ! -e "$path" ]]; then
      return 0
    fi
    sleep "$delay"
  done

  return 1
}

run_vault_watch_preflight() {
  local repo_dir="$TMP_ROOT/watch-repo"
  local bin_dir="$repo_dir/bin"
  local config_dir="$repo_dir/config"
  local priv_dir="$repo_dir/almanac-priv"
  local vault_dir="$priv_dir/vault"
  local state_dir="$priv_dir/state"
  local generated_md="$state_dir/pdf-ingest/markdown/Inbox/chutes-mesh-watch-pdf.md"
  local config_file="$config_dir/almanac.env"
  local watcher_pid=""

  mkdir -p "$bin_dir" "$config_dir" "$vault_dir/Inbox"
  cp "$ROOT_DIR/bin/common.sh" "$bin_dir/common.sh"
  cp "$ROOT_DIR/bin/vault-watch.sh" "$bin_dir/vault-watch.sh"

  cat >"$bin_dir/pdf-ingest.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

ensure_layout

while IFS= read -r -d '' pdf; do
  rel="${pdf#$VAULT_DIR/}"
  out="$PDF_INGEST_MARKDOWN_DIR/${rel%.pdf}-pdf.md"
  mkdir -p "$(dirname "$out")"
  printf '# %s\n\nstub ingest\n' "$(basename "$pdf")" >"$out"
done < <(find "$VAULT_DIR" -type f -name '*.pdf' -print0)

while IFS= read -r -d '' md; do
  rel="${md#$PDF_INGEST_MARKDOWN_DIR/}"
  src="$VAULT_DIR/${rel%-pdf.md}.pdf"
  if [[ ! -f "$src" ]]; then
    rm -f "$md"
  fi
done < <(find "$PDF_INGEST_MARKDOWN_DIR" -type f -name '*-pdf.md' -print0 2>/dev/null || true)
EOF
  chmod +x "$bin_dir/pdf-ingest.sh"

  cat >"$bin_dir/qmd-refresh.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
sleep 2
EOF
  chmod +x "$bin_dir/qmd-refresh.sh"

  cat >"$config_file" <<EOF
ALMANAC_REPO_DIR=$repo_dir
ALMANAC_PRIV_DIR=$priv_dir
ALMANAC_PRIV_CONFIG_DIR=$priv_dir/config
VAULT_DIR=$vault_dir
STATE_DIR=$state_dir
PDF_INGEST_ENABLED=1
VAULT_WATCH_DEBOUNCE_SECONDS=1
EOF

  log "exercising vault watcher create/delete flow while refresh work is in-flight"

  env ALMANAC_CONFIG_FILE="$config_file" bash "$bin_dir/vault-watch.sh" >"$TMP_ROOT/watch.log" 2>&1 &
  watcher_pid=$!
  sleep 1

  write_test_pdf "$vault_dir/Inbox/chutes-mesh-watch.pdf"
  wait_for_path_state "$generated_md" present 40 0.25
  rm -f "$vault_dir/Inbox/chutes-mesh-watch.pdf"
  wait_for_path_state "$generated_md" absent 40 0.25

  kill "$watcher_pid" 2>/dev/null || true
  wait "$watcher_pid" 2>/dev/null || true
}

run_vault_notification_preflight() {
  local fakebin="$TMP_ROOT/notify-fakebin"
  local repo_dir="$TMP_ROOT/notify-repo"
  local bin_dir="$repo_dir/bin"
  local config_dir="$repo_dir/config"
  local priv_dir="$repo_dir/almanac-priv"
  local vault_dir="$priv_dir/vault"
  local state_dir="$priv_dir/state"
  local runtime_dir="$state_dir/runtime"
  local config_file="$config_dir/almanac.env"
  local generated_md="$state_dir/pdf-ingest/markdown/Projects/notify-me-pdf.md"
  local trigger_default="$state_dir/activation-triggers/agent-default.json"
  local trigger_optin="$state_dir/activation-triggers/agent-optin.json"
  local trigger_optout="$state_dir/activation-triggers/agent-optout.json"
  local watcher_pid=""

  mkdir -p "$bin_dir" "$config_dir" "$vault_dir/Projects" "$vault_dir/Teams"
  setup_fake_pdftotext "$fakebin"
  cp "$ROOT_DIR/bin/common.sh" "$bin_dir/common.sh"
  cp "$ROOT_DIR/bin/vault-watch.sh" "$bin_dir/vault-watch.sh"
  cp "$ROOT_DIR/bin/pdf-ingest.sh" "$bin_dir/pdf-ingest.sh"
  cp "$ROOT_DIR/bin/pdf-ingest.py" "$bin_dir/pdf-ingest.py"
  ln -s "$ROOT_DIR/python" "$repo_dir/python"
  setup_fake_runtime_python "$runtime_dir"

  cat >"$bin_dir/qmd-refresh.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exit 0
EOF
  chmod +x "$bin_dir/qmd-refresh.sh"

  cat >"$bin_dir/almanac-ctl" <<EOF
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="\$(cd "\$(dirname "\$0")" && pwd)"
REPO_DIR="\$(cd "\$SCRIPT_DIR/.." && pwd)"
export ALMANAC_CONFIG_FILE="$config_file"
export PYTHONPATH="\$REPO_DIR/python\${PYTHONPATH:+:\$PYTHONPATH}"
exec python3 "\$REPO_DIR/python/almanac_ctl.py" "\$@"
EOF
  chmod +x "$bin_dir/almanac-ctl"


  cat >"$config_file" <<EOF
ALMANAC_REPO_DIR=$repo_dir
ALMANAC_PRIV_DIR=$priv_dir
ALMANAC_PRIV_CONFIG_DIR=$priv_dir/config
VAULT_DIR=$vault_dir
STATE_DIR=$state_dir
ALMANAC_DB_PATH=$state_dir/almanac-control.sqlite3
ALMANAC_AGENTS_STATE_DIR=$state_dir/agents
ALMANAC_CURATOR_DIR=$state_dir/curator
ALMANAC_CURATOR_MANIFEST=$state_dir/curator/manifest.json
ALMANAC_CURATOR_HERMES_HOME=$state_dir/curator/hermes-home
ALMANAC_ARCHIVED_AGENTS_DIR=$state_dir/archived-agents
ALMANAC_RELEASE_STATE_FILE=$state_dir/almanac-release.json
ALMANAC_QMD_URL=http://127.0.0.1:8181/mcp
ALMANAC_MCP_HOST=127.0.0.1
ALMANAC_MCP_PORT=8282
ALMANAC_MODEL_PRESET_CODEX=openai:codex
ALMANAC_MODEL_PRESET_OPUS=anthropic:claude-opus
ALMANAC_MODEL_PRESET_CHUTES=chutes:auto-failover
OPERATOR_NOTIFY_CHANNEL_PLATFORM=tui-only
OPERATOR_NOTIFY_CHANNEL_ID=operator
PDF_INGEST_ENABLED=1
PDF_INGEST_EXTRACTOR=auto
PDF_INGEST_TRIGGER_QMD_REFRESH=0
VAULT_WATCH_DEBOUNCE_SECONDS=1
EOF

  cat >"$vault_dir/Projects/.vault" <<'EOF'
name: Projects
description: Active project workspaces
owner: operator
default_subscribed: true
category: workspace
EOF
  cat >"$vault_dir/Teams/.vault" <<'EOF'
name: Teams
description: Team space that requires an explicit opt-in
owner: operator
default_subscribed: false
category: workspace
EOF

  python3 - "$config_file" "$ROOT_DIR" <<'PY'
import json
import os
import sys
from pathlib import Path

config_file, repo_root = sys.argv[1:3]
os.environ["ALMANAC_CONFIG_FILE"] = config_file
sys.path.insert(0, str(Path(repo_root) / "python"))

import almanac_control as mod

cfg = mod.Config.from_env()
conn = mod.connect_db(cfg)
mod.reload_vault_definitions(conn, cfg)

now = mod.utc_now_iso()
root = cfg.state_dir.parent

agents = [
    ("agent-default", "defaultuser", "Default User"),
    ("agent-optout", "optoutuser", "Opt-Out User"),
    ("agent-optin", "optinuser", "Opt-In User"),
]
for agent_id, unix_user, display_name in agents:
    conn.execute(
        """
        INSERT INTO agents (
          agent_id, role, unix_user, display_name, status, hermes_home, manifest_path,
          archived_state_path, model_preset, model_string, channels_json,
          allowed_mcps_json, home_channel_json, operator_notify_channel_json,
          notes, created_at, last_enrolled_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            agent_id,
            "user",
            unix_user,
            display_name,
            "active",
            str(root / f"home-{unix_user}" / ".local" / "share" / "almanac-agent" / "hermes-home"),
            str(cfg.state_dir / "agents" / agent_id / "manifest.json"),
            None,
            "codex",
            "openai:codex",
            json.dumps(["tui-only"]),
            json.dumps([]),
            json.dumps({"platform": "tui", "channel_id": ""}),
            json.dumps({}),
            "",
            now,
            now,
        ),
    )
conn.commit()

for agent_id, _, _ in agents:
    mod.ensure_default_subscriptions(conn, agent_id)
mod.set_vault_subscription(conn, agent_id="agent-optout", vault_name="Projects", subscribed=False, source="user")
mod.set_vault_subscription(conn, agent_id="agent-optin", vault_name="Projects", subscribed=False, source="user")
mod.set_vault_subscription(conn, agent_id="agent-optin", vault_name="Teams", subscribed=True, source="user")
PY

  log "exercising watcher-driven PDF conversion + subscriber notification routing"

  env \
    PATH="$fakebin:$PATH" \
    ALMANAC_ALLOW_SCAFFOLD_DEFAULTS=1 \
    ALMANAC_CONFIG_FILE="$config_file" \
    bash "$bin_dir/vault-watch.sh" >"$TMP_ROOT/notify-watch.log" 2>&1 &
  watcher_pid=$!
  sleep 1

  write_test_pdf "$vault_dir/Projects/notify-me.pdf"
  printf 'opt-in team note\n' >"$vault_dir/Teams/opt-in.md"

  wait_for_path_state "$generated_md" present 40 0.25
  wait_for_path_state "$trigger_default" present 40 0.25
  wait_for_path_state "$trigger_optin" present 40 0.25

  python3 - "$config_file" "$ROOT_DIR" "$generated_md" "$trigger_default" "$trigger_optin" "$trigger_optout" <<'PY'
import os
import sys
from pathlib import Path

config_file, repo_root, generated_md, trigger_default, trigger_optin, trigger_optout = sys.argv[1:7]
os.environ["ALMANAC_CONFIG_FILE"] = config_file
sys.path.insert(0, str(Path(repo_root) / "python"))

import almanac_control as mod

cfg = mod.Config.from_env()
conn = mod.connect_db(cfg)

assert Path(generated_md).is_file(), generated_md
assert Path(trigger_default).is_file(), trigger_default
assert Path(trigger_optin).is_file(), trigger_optin
assert not Path(trigger_optout).exists(), trigger_optout

default_notifications = mod.consume_agent_notifications(conn, agent_id="agent-default")
optout_notifications = mod.consume_agent_notifications(conn, agent_id="agent-optout")
optin_notifications = mod.consume_agent_notifications(conn, agent_id="agent-optin")

assert len(default_notifications) == 1, default_notifications
assert default_notifications[0]["channel_kind"] == "vault-change", default_notifications
assert "Projects" in default_notifications[0]["message"], default_notifications
assert optout_notifications == [], optout_notifications
assert len(optin_notifications) == 1, optin_notifications
assert optin_notifications[0]["channel_kind"] == "vault-change", optin_notifications
assert "Teams" in optin_notifications[0]["message"], optin_notifications
PY

  kill "$watcher_pid" 2>/dev/null || true
  wait "$watcher_pid" 2>/dev/null || true
}

run_repo_sync_preflight() {
  local repo_dir="$TMP_ROOT/repo-sync-repo"
  local bin_dir="$repo_dir/bin"
  local config_dir="$repo_dir/config"
  local priv_dir="$repo_dir/almanac-priv"
  local vault_dir="$priv_dir/vault"
  local state_dir="$priv_dir/state"
  local config_file="$config_dir/almanac.env"
  local source_repo="$TMP_ROOT/repo-sync-source"
  local mirror_readme="$vault_dir/Repos/_mirrors/example-almanac/README.md"
  local mirror_doc="$vault_dir/Repos/_mirrors/example-almanac/docs/architecture.md"
  local trigger_default="$state_dir/activation-triggers/agent-default.json"
  local trigger_optout="$state_dir/activation-triggers/agent-optout.json"
  local watcher_pid=""

  mkdir -p "$bin_dir" "$config_dir" "$vault_dir/Repos" "$source_repo"
  cp "$ROOT_DIR/bin/common.sh" "$bin_dir/common.sh"
  cp "$ROOT_DIR/bin/vault-watch.sh" "$bin_dir/vault-watch.sh"
  ln -s "$ROOT_DIR/python" "$repo_dir/python"

  cat >"$bin_dir/qmd-refresh.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exit 0
EOF
  chmod +x "$bin_dir/qmd-refresh.sh"

  cat >"$bin_dir/almanac-ctl" <<EOF
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="\$(cd "\$(dirname "\$0")" && pwd)"
REPO_DIR="\$(cd "\$SCRIPT_DIR/.." && pwd)"
export ALMANAC_CONFIG_FILE="$config_file"
export PYTHONPATH="\$REPO_DIR/python\${PYTHONPATH:+:\$PYTHONPATH}"
exec python3 "\$REPO_DIR/python/almanac_ctl.py" "\$@"
EOF
  chmod +x "$bin_dir/almanac-ctl"

  cat >"$config_file" <<EOF
ALMANAC_REPO_DIR=$repo_dir
ALMANAC_PRIV_DIR=$priv_dir
ALMANAC_PRIV_CONFIG_DIR=$priv_dir/config
VAULT_DIR=$vault_dir
STATE_DIR=$state_dir
ALMANAC_DB_PATH=$state_dir/almanac-control.sqlite3
ALMANAC_AGENTS_STATE_DIR=$state_dir/agents
ALMANAC_CURATOR_DIR=$state_dir/curator
ALMANAC_CURATOR_MANIFEST=$state_dir/curator/manifest.json
ALMANAC_CURATOR_HERMES_HOME=$state_dir/curator/hermes-home
ALMANAC_ARCHIVED_AGENTS_DIR=$state_dir/archived-agents
ALMANAC_RELEASE_STATE_FILE=$state_dir/almanac-release.json
ALMANAC_QMD_URL=http://127.0.0.1:8181/mcp
ALMANAC_MCP_HOST=127.0.0.1
ALMANAC_MCP_PORT=8282
ALMANAC_MODEL_PRESET_CODEX=openai:codex
ALMANAC_MODEL_PRESET_OPUS=anthropic:claude-opus
ALMANAC_MODEL_PRESET_CHUTES=chutes:auto-failover
OPERATOR_NOTIFY_CHANNEL_PLATFORM=tui-only
OPERATOR_NOTIFY_CHANNEL_ID=operator
PDF_INGEST_ENABLED=0
VAULT_WATCH_DEBOUNCE_SECONDS=1
VAULT_WATCH_RUN_EMBED=0
EOF

  cat >"$vault_dir/Repos/.vault" <<'EOF'
name: Repos
description: Repository inventory
owner: organization
default_subscribed: true
category: inventory
EOF
  cat >"$vault_dir/Repos/almanac.md" <<'EOF'
# Almanac

Repository URL: https://github.com/example/almanac
EOF

  git init -b main "$source_repo" >/dev/null
  git -C "$source_repo" config user.name 'Almanac Preflight'
  git -C "$source_repo" config user.email 'almanac-preflight@example.com'
  printf 'repo readme v1\n' >"$source_repo/README.md"
  mkdir -p "$source_repo/docs" "$source_repo/src"
  printf 'architecture v1\n' >"$source_repo/docs/architecture.md"
  printf 'print("ignored")\n' >"$source_repo/src/main.py"
  git -C "$source_repo" add -A
  git -C "$source_repo" commit -m 'initial repo sync fixture' >/dev/null

  python3 - "$config_file" "$ROOT_DIR" <<'PY'
import json
import os
import sys
from pathlib import Path

config_file, repo_root = sys.argv[1:3]
os.environ["ALMANAC_CONFIG_FILE"] = config_file
sys.path.insert(0, str(Path(repo_root) / "python"))

import almanac_control as mod

cfg = mod.Config.from_env()
conn = mod.connect_db(cfg)
mod.reload_vault_definitions(conn, cfg)
now = mod.utc_now_iso()
root = cfg.state_dir.parent

agents = [
    ("agent-default", "defaultuser", "Default User"),
    ("agent-optout", "optoutuser", "Opt-Out User"),
]
for agent_id, unix_user, display_name in agents:
    conn.execute(
        """
        INSERT INTO agents (
          agent_id, role, unix_user, display_name, status, hermes_home, manifest_path,
          archived_state_path, model_preset, model_string, channels_json,
          allowed_mcps_json, home_channel_json, operator_notify_channel_json,
          notes, created_at, last_enrolled_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            agent_id,
            "user",
            unix_user,
            display_name,
            "active",
            str(root / f"home-{unix_user}" / ".local" / "share" / "almanac-agent" / "hermes-home"),
            str(cfg.state_dir / "agents" / agent_id / "manifest.json"),
            None,
            "codex",
            "openai:codex",
            json.dumps(["tui-only"]),
            json.dumps([]),
            json.dumps({"platform": "tui", "channel_id": ""}),
            json.dumps({}),
            "",
            now,
            now,
        ),
    )
conn.commit()
for agent_id, _, _ in agents:
    mod.ensure_default_subscriptions(conn, agent_id)
mod.set_vault_subscription(conn, agent_id="agent-optout", vault_name="Repos", subscribed=False, source="user")
PY

  log "exercising watcher-driven GitHub repo sync mirroring + notification routing"

  env \
    ALMANAC_ALLOW_SCAFFOLD_DEFAULTS=1 \
    ALMANAC_CONFIG_FILE="$config_file" \
    bash "$bin_dir/vault-watch.sh" >"$TMP_ROOT/repo-sync-watch.log" 2>&1 &
  watcher_pid=$!
  sleep 1

  python3 - "$config_file" "$ROOT_DIR" "$source_repo" <<'PY'
import os
import sys
from pathlib import Path

config_file, repo_root, source_repo = sys.argv[1:4]
os.environ["ALMANAC_CONFIG_FILE"] = config_file
sys.path.insert(0, str(Path(repo_root) / "python"))

import almanac_control as mod

cfg = mod.Config.from_env()
conn = mod.connect_db(cfg)
discovered = mod.discover_vault_repo_sources(cfg)
assert len(discovered) == 1, discovered
discovered[0]["remote_url"] = source_repo
result = mod.sync_vault_repo_mirrors(conn, cfg, repo_sources=discovered)
assert result["repos_total"] == 1, result
assert result["repos_failed"] == [], result
PY

  wait_for_path_state "$mirror_readme" present 40 0.25
  wait_for_path_state "$mirror_doc" present 40 0.25
  wait_for_path_state "$trigger_default" present 40 0.25

  python3 - "$config_file" "$ROOT_DIR" "$mirror_readme" "$mirror_doc" "$trigger_default" "$trigger_optout" <<'PY'
import os
import sys
from pathlib import Path

config_file, repo_root, mirror_readme, mirror_doc, trigger_default, trigger_optout = sys.argv[1:7]
os.environ["ALMANAC_CONFIG_FILE"] = config_file
sys.path.insert(0, str(Path(repo_root) / "python"))

import almanac_control as mod

cfg = mod.Config.from_env()
conn = mod.connect_db(cfg)

assert Path(mirror_readme).is_file(), mirror_readme
assert Path(mirror_doc).is_file(), mirror_doc
assert not (Path(mirror_readme).parent / "src" / "main.py").exists(), "unexpected source mirror"
assert Path(trigger_default).is_file(), trigger_default
assert not Path(trigger_optout).exists(), trigger_optout

default_notifications = mod.consume_agent_notifications(conn, agent_id="agent-default")
optout_notifications = mod.consume_agent_notifications(conn, agent_id="agent-optout")

assert len(default_notifications) == 1, default_notifications
assert default_notifications[0]["channel_kind"] == "vault-change", default_notifications
assert "Repos" in default_notifications[0]["message"], default_notifications
assert optout_notifications == [], optout_notifications
PY

  kill "$watcher_pid" 2>/dev/null || true
  wait "$watcher_pid" 2>/dev/null || true
}

main() {
  log "running Almanac preflight checks"
  run_shell_lint
  run_python_checks
  run_systemd_verify
  run_pdf_ingest_preflight
  run_pdf_ingest_vision_preflight
  run_vault_watch_preflight
  run_vault_notification_preflight
  run_repo_sync_preflight
  log "preflight checks passed"
}

main "$@"
