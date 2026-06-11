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

Version: `0.4.0` everywhere — `plugin.yaml`, `dashboard/manifest.json`, and the
`/status` payload all carry the same number and must be bumped together.

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
  socket under `$HERMES_HOME/state/terminal/` (override with
  `TERMINAL_TMUX_SOCKET`) and reattaches a browser pty client after dashboard
  refreshes or worker restarts. Without `tmux`, it falls back to the in-process
  managed pty backend, which does NOT survive dashboard restarts — `/status`
  only advertises `persistent_sessions` on the tmux backend.
- On ArcLink Pods the tmux server runs in a dedicated long-lived `terminal-tmux`
  compose service (`bin/run-terminal-tmux.sh`) that shares the `HERMES_HOME`
  bind mount, so sessions survive dashboard container restarts, upgrades,
  crashes, and OOM kills, and terminal shells live in their own cgroup.
- New tmux sessions set `history-limit` to at least 4000 lines (or the
  configured `TERMINAL_REATTACH_SCROLLBACK_LINES`) so reattach recovery can
  actually capture the advertised scrollback.
- Backend scrollback defaults to `TERMINAL_SCROLLBACK_BYTES=8000000` and is
  bounded between 4 KB and 50 MB.
- Browser scrollback defaults to `TERMINAL_SCROLLBACK_LINES=50000` and is
  bounded between 500 and 200000 lines.
- Hermes TUI sessions use `TERMINAL_TUI_COMMAND` or `HERMES_TUI_COMMAND`, and
  optional `HERMES_TUI_DIR` / `TERMINAL_TUI_DIR` when the TUI bundle requires
  assets.

## Behavior

- Session list, inline rename, close confirmation, closed-session cleanup, and
  bounded scrollback are built in. "Clear Closed" never removes or kills a
  detached tmux session that is still alive — those stay listed and
  reattachable; the confirm-gated Close action is the only user kill path.
- Direct key input, backspace/delete, Ctrl shortcuts, bracketed paste, TUI
  cursor reports, SSE streaming, and polling fallback are supported through
  xterm.js and the terminal pty API. If the SSE stream drops, the UI keeps
  polling at 1s and re-establishes the stream with exponential backoff instead
  of permanently downgrading.
- Cached browser terminals are caught up before they are revealed again, so
  switching back to a TUI session does not visibly replay already-buffered text.
- Detached, exited, and closed sessions are visibly dimmed with an overlay
  notice (`[data-session-state]` styling) so it is obvious why keystrokes are
  not accepted.
- `+Shell` opens a shell confined to the configured workspace root. `+Machine`
  opens a shell on the local machine (the ArcPod's own host) without asking for
  a remote target; the session keeps the internal `ssh` mode name for stored
  state compatibility but it is never a remote dial-out and no `ssh_sessions`
  capability is advertised. `+TUI` opens the configured Hermes TUI command.

## Check

```bash
python3 -m py_compile plugins/hermes-agent/terminal/dashboard/plugin_api.py
node --check plugins/hermes-agent/terminal/dashboard/dist/index.js
```
