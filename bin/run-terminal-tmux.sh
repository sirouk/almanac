#!/usr/bin/env bash
# Long-lived tmux server for Terminal forever-sessions.
#
# Runs as a dedicated compose service (terminal-tmux / control-operator-terminal-tmux)
# so dashboard container restarts, upgrades, crashes, and OOM kills never destroy
# terminal sessions. The Terminal dashboard plugin reaches this server through the
# tmux socket on the shared HERMES_HOME bind mount
# ($HERMES_HOME/state/terminal/tmux.sock), which both containers mount at the same
# path. Shell processes spawned for terminal sessions live in this container's
# own cgroup, so heavy terminal use cannot OOM the dashboard either.
set -euo pipefail

if ! command -v tmux >/dev/null 2>&1; then
  echo "run-terminal-tmux: tmux is not installed; refusing to start" >&2
  exit 1
fi

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
SOCKET_DIR="${TERMINAL_TMUX_SOCKET_DIR:-$HERMES_HOME/state/terminal}"
SOCKET_PATH="${TERMINAL_TMUX_SOCKET:-$SOCKET_DIR/tmux.sock}"
KEEPALIVE_SECONDS="${TERMINAL_TMUX_KEEPALIVE_SECONDS:-10}"
if ! [[ "$KEEPALIVE_SECONDS" =~ ^[0-9]+$ ]] || [[ "$KEEPALIVE_SECONDS" == "0" ]]; then
  KEEPALIVE_SECONDS=10
fi

# Honor the Terminal plugin's advertised reattach scrollback: tmux's default
# history-limit (~2000 lines) would silently truncate capture-pane recovery.
HISTORY_LIMIT="${TERMINAL_REATTACH_SCROLLBACK_LINES:-4000}"
if ! [[ "$HISTORY_LIMIT" =~ ^[0-9]+$ ]] || (( HISTORY_LIMIT < 4000 )); then
  HISTORY_LIMIT=4000
fi

mkdir -p "$(dirname "$SOCKET_PATH")"
chmod 700 "$(dirname "$SOCKET_PATH")" 2>/dev/null || true

ensure_server() {
  # start-server is idempotent: it connects to a live server or starts a new
  # one (replacing a stale socket). Sessions are created by the Terminal
  # dashboard plugin over the same socket.
  tmux -S "$SOCKET_PATH" start-server >/dev/null 2>&1 || return 1
  # Keep the server alive with zero sessions so reattach always has a home.
  tmux -S "$SOCKET_PATH" set-option -s exit-empty off >/dev/null 2>&1 || true
  tmux -S "$SOCKET_PATH" set-option -g history-limit "$HISTORY_LIMIT" >/dev/null 2>&1 || true
  return 0
}

echo "run-terminal-tmux: serving persistent tmux socket at $SOCKET_PATH"
while true; do
  if ! ensure_server; then
    echo "run-terminal-tmux: tmux server unavailable; retrying in ${KEEPALIVE_SECONDS}s" >&2
  fi
  sleep "$KEEPALIVE_SECONDS"
done
