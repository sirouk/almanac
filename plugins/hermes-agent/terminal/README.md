# Terminal

Terminal is a lightweight Hermes dashboard plugin that adds managed local pty
sessions without patching Hermes core. The browser surface uses vendored
xterm.js assets so cursor positioning, alternate-screen TUIs, control
characters, paste, selection, resize, and scrollback behave like a normal
terminal emulator.

## Install

Copy this directory to `~/.hermes/plugins/terminal` and enable `terminal` under
`plugins.enabled` in `config.yaml`. The dashboard plugin surface requires
Hermes `v2026.4.30` or newer (`minimum_hermes_version` in `plugin.yaml`).

Version note: `plugin.yaml` carries `version: 0.2.0`, while the `/status`
payload reports `version: "0.3.0"` (the running surface). Treat `0.3.0` as the
current behavior level described below; the `plugin.yaml` pin is stale and not
yet reconciled.

## Runtime

- Workspace uses `TERMINAL_WORKSPACE_ROOT`, `CODE_WORKSPACE_ROOT`, or
  `DRIVE_WORKSPACE_ROOT` when set, otherwise `$HERMES_HOME/workspace`.
- Terminal is a full ArcPod Unix-user shell surface. Drive and Code hide
  sensitive paths for their file-browser workflows, but those filters are not a
  security boundary once Terminal is enabled for the same dashboard principal.
- Shell defaults to `$SHELL`, `/bin/bash`, then `/bin/sh`; set
  `TERMINAL_SHELL` to override.
- Root execution is blocked unless `TERMINAL_ALLOW_ROOT=1`.
- Session state lives under `$HERMES_HOME/state/terminal/sessions.json`.
- When `tmux` is installed, Terminal runs sessions inside an ArcLink-owned tmux
  socket under `$HERMES_HOME/state/terminal/` and reattaches a browser pty
  client after dashboard refreshes or worker restarts. Without `tmux`, it falls
  back to the in-process managed pty backend.
- Backend scrollback defaults to `TERMINAL_SCROLLBACK_BYTES=8000000` and is
  bounded between 4 KB and 50 MB.
- Browser scrollback defaults to `TERMINAL_SCROLLBACK_LINES=50000` and is
  bounded between 500 and 200000 lines.
- Hermes TUI sessions use `TERMINAL_TUI_COMMAND` or `HERMES_TUI_COMMAND`, and
  optional `HERMES_TUI_DIR` / `TERMINAL_TUI_DIR` when the TUI bundle requires
  assets.

## Behavior

- Session list, inline rename, close confirmation, closed-session cleanup, and
  bounded scrollback are built in.
- Direct key input, backspace/delete, Ctrl shortcuts, bracketed paste, TUI
  cursor reports, SSE streaming, and polling fallback are supported through
  xterm.js and the terminal pty API.
- Cached browser terminals are caught up before they are revealed again, so
  switching back to a TUI session does not visibly replay already-buffered text.
- The `+SSH` button opens a shell on the local machine (the ArcPod's own host)
  without asking for a remote target; despite the `ssh` mode name the session is
  created with an empty `target`, so it is never a remote dial-out. `+TUI` opens
  the configured Hermes TUI command.

## Check

```bash
python3 -m py_compile plugins/hermes-agent/terminal/dashboard/plugin_api.py
node --check plugins/hermes-agent/terminal/dashboard/dist/index.js
```
