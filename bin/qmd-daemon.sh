#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

require_real_layout "qmd daemon startup"
ensure_nvm
mkdir -p "$(dirname "$QMD_INDEX_DB_PATH")"

loopback_port="${QMD_MCP_LOOPBACK_PORT:-${QMD_MCP_PORT:-8181}}"
container_port="${QMD_MCP_CONTAINER_PORT:-$loopback_port}"

if [[ "$loopback_port" == "$container_port" ]]; then
  exec qmd --index "$QMD_INDEX_NAME" mcp --http --port "$loopback_port"
fi

python3 - "$container_port" "$loopback_port" <<'PY' &
import socket
import socketserver
import sys
import threading

listen_port = int(sys.argv[1])
target_port = int(sys.argv[2])


def pipe(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for sock in (src, dst):
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            upstream = socket.create_connection(("127.0.0.1", target_port), timeout=5)
        except OSError:
            return
        left = threading.Thread(target=pipe, args=(self.request, upstream), daemon=True)
        right = threading.Thread(target=pipe, args=(upstream, self.request), daemon=True)
        left.start()
        right.start()
        left.join()
        right.join()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


with Server(("0.0.0.0", listen_port), Handler) as server:
    print(f"QMD MCP TCP forwarder listening on 0.0.0.0:{listen_port} -> 127.0.0.1:{target_port}", flush=True)
    server.serve_forever()
PY
proxy_pid="$!"
qmd --index "$QMD_INDEX_NAME" mcp --http --port "$loopback_port" &
qmd_pid="$!"

cleanup() {
  kill "$qmd_pid" "$proxy_pid" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM
wait "$qmd_pid"
