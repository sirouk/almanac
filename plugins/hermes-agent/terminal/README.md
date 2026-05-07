# Terminal

Terminal is a lightweight Hermes dashboard plugin that adds managed local pty
sessions without patching Hermes core. The browser surface uses vendored
xterm.js assets so cursor positioning, alternate-screen TUIs, control
characters, paste, selection, resize, and scrollback behave like a normal
terminal emulator.

## Install

Copy this directory to `~/.hermes/plugins/terminal` and enable `terminal` under
`plugins.enabled` in `config.yaml`. The dashboard plugin surface requires
Hermes `v2026.4.30` or newer.

## Runtime

- Workspace defaults to `$HOME`, `TERMINAL_WORKSPACE_ROOT`, or
  `CODE_WORKSPACE_ROOT` when set.
- Shell defaults to `$SHELL`, `/bin/bash`, then `/bin/sh`; set
  `TERMINAL_SHELL` to override.
- Root execution is blocked unless `TERMINAL_ALLOW_ROOT=1`.
- Session state lives under `$HERMES_HOME/state/terminal/sessions.json`.
- Backend scrollback defaults to `TERMINAL_SCROLLBACK_BYTES=1000000` and is
  bounded between 4 KB and 10 MB.
- Browser scrollback defaults to `TERMINAL_SCROLLBACK_LINES=10000` and is
  bounded between 500 and 100000 lines.
- Hermes TUI sessions use `TERMINAL_TUI_COMMAND` or `HERMES_TUI_COMMAND`, and
  optional `HERMES_TUI_DIR` / `TERMINAL_TUI_DIR` when the TUI bundle requires
  assets.

## Behavior

- Session list, inline rename, close confirmation, closed-session cleanup, and
  bounded scrollback are built in.
- Direct key input, backspace/delete, Ctrl shortcuts, bracketed paste, TUI
  cursor reports, SSE streaming, and polling fallback are supported through
  xterm.js and the managed pty API.
- The `+SSH` button opens the machine shell without asking for a remote target;
  `+TUI` opens the configured Hermes TUI command.

## Check

```bash
python3 -m py_compile plugins/hermes-agent/terminal/dashboard/plugin_api.py
node --check plugins/hermes-agent/terminal/dashboard/dist/index.js
```
