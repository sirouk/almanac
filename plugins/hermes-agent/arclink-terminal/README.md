# ArcLink Terminal

ArcLink Terminal is a Hermes dashboard plugin shipped by ArcLink. In the
current slice it provides native, persistent dashboard terminal sessions through
an ArcLink-managed pty backend. It does not patch Hermes core.

## Ownership

- Plugin package: `plugins/hermes-agent/arclink-terminal/`
- Dashboard API: `plugins/hermes-agent/arclink-terminal/dashboard/plugin_api.py`
- Dashboard assets: `plugins/hermes-agent/arclink-terminal/dashboard/dist/`
- Default install path: `bin/install-arclink-plugins.sh`

Hermes owns the plugin host. ArcLink owns the terminal capability contract,
managed-pty session backend, UI assets, lifecycle safety, and secret redaction.

## Current Behavior

- `/status` returns plugin identity, sanitized workspace/state labels, shell
  name, backend candidates, limits, transport mode, and capability flags.
- `backend` is `managed-pty` when a shell, workspace root, and non-root runtime
  user boundary are available.
- Sessions have stable IDs, names, folders, order values, cwd metadata,
  lifecycle state, exit code, bounded scrollback, and atomic JSON state under
  `HERMES_HOME/state/arclink-terminal/sessions.json`.
- The dashboard supports session list, new shell session, new SSH session, new
  Hermes TUI session, revisit after browser reload, rename, folder assignment,
  reorder controls, terminal pane, direct pty keystroke input, SSE output
  streaming with polling fallback, closed-session cleanup, and
  confirmation-gated close.
- Session actions live on the left rail: plus buttons create shell/SSH/TUI
  sessions, right-click opens rename/folder/reorder/close actions, and the
  lightweight row `x` starts the close-confirmation flow.
- Selecting terminal text attempts to copy it to the clipboard. Browser
  clipboard permissions may still require user activation depending on the
  client.
- `streaming_output` is `true` when the managed-pty backend is available. The
  primary browser transport is same-origin Server-Sent Events; bounded polling
  remains as a reconnect/fallback path when EventSource is unavailable or the
  stream errors.
- Terminal startup is blocked when the dashboard process is unrestricted root.
  `ARCLINK_TERMINAL_ALLOW_ROOT=1` exists for tests and deliberate operator
  diagnostics only, not normal deployment.

## Assumptions

- Terminal execution runs as the dashboard process user in the configured
  workspace root. It is blocked for unrestricted root by default.
- Streaming events, scrollback, metadata, and backend errors must be bounded
  and redacted.
- Session close/kill must be confirmation-gated.
- The current backend is a managed pty fallback rather than tmux. tmux remains
  a future candidate if Docker/baremetal runtime installation is standardized.

## Runbook

After changing Terminal behavior:

```bash
python3 -m py_compile plugins/hermes-agent/arclink-terminal/dashboard/plugin_api.py
python3 tests/test_arclink_plugins.py
node --check plugins/hermes-agent/arclink-terminal/dashboard/dist/index.js
git diff --check
```

## Backend Notes

The implemented backend opens a local pty for each session, launches the
configured shell in the resolved workspace cwd, stores bounded state atomically,
and exposes session snapshots through both direct API reads and a same-origin
SSE stream. This keeps the first production path dependency-light and testable
without requiring tmux in every ArcLink runtime. A future tmux-backed backend
can replace or augment this path if it is installed by the Docker and baremetal
refresh flows and covered by equivalent session lifecycle tests.
