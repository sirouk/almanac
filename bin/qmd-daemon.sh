#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

require_real_layout "qmd daemon startup"
ensure_nvm

# qmd's MCP server hard-codes its listener to localhost (see
# @tobilu/qmd dist/mcp/server.js: `httpServer.listen(port, "localhost", ...)`),
# which makes it unreachable from sibling containers in Docker mode. When we
# detect docker mode, run qmd on an internal loopback port and bridge the
# published port through a small Python TCP forwarder so almanac-mcp,
# vault-watch, agents and health probes can all dial qmd-mcp:$QMD_MCP_PORT.
if [[ "${ALMANAC_DOCKER_MODE:-0}" == "1" ]]; then
  internal_port="${QMD_MCP_INTERNAL_PORT:-18181}"
  qmd --index "$QMD_INDEX_NAME" mcp --http --port "$internal_port" &
  qmd_pid=$!
  trap 'kill "$qmd_pid" 2>/dev/null || true' EXIT TERM INT
  exec python3 -u - "0.0.0.0:$QMD_MCP_PORT" "localhost:$internal_port" <<'PY'
import socket
import sys
import threading

listen_host, _, listen_port = sys.argv[1].rpartition(":")
upstream_host, _, upstream_port = sys.argv[2].rpartition(":")
upstream = (upstream_host, int(upstream_port))


def pump(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            chunk = src.recv(65536)
            if not chunk:
                break
            dst.sendall(chunk)
    except OSError:
        pass
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def handle(client: socket.socket) -> None:
    try:
        peer = socket.create_connection(upstream)
    except OSError:
        client.close()
        return
    threading.Thread(target=pump, args=(client, peer), daemon=True).start()
    pump(peer, client)
    client.close()
    peer.close()


server = socket.socket()
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind((listen_host, int(listen_port)))
server.listen(64)
while True:
    conn, _ = server.accept()
    threading.Thread(target=handle, args=(conn,), daemon=True).start()
PY
fi

exec qmd --index "$QMD_INDEX_NAME" mcp --http --port "$QMD_MCP_PORT"
