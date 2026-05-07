# Hermes Dashboard Workspace Plugins

This directory contains standalone Hermes dashboard plugins:

- `drive` - file manager for Workspace and Vault roots.
- `code` - code editor, file explorer, previews, and git source control.
- `terminal` - managed pty terminal sessions.

Each plugin follows the Hermes plugin layout:

```text
plugin-name/
  plugin.yaml
  __init__.py
  dashboard/
    manifest.json
    plugin_api.py
    dist/index.js
    dist/style.css
```

The dashboard extension surface requires Hermes `v2026.4.30` or newer. Install
by copying the desired plugin directories into `~/.hermes/plugins/` and adding
their names to `plugins.enabled` in `config.yaml`.

The plugins default to `$HOME` for workspace access and stay dependency-light:
local filesystem APIs, browser-native preview surfaces, standard `git`, and
Python pty support. Optional roots and limits are configured with generic env
vars documented in each plugin README.
