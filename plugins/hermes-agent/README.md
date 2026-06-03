# Hermes Dashboard Workspace Plugins

This directory contains standalone Hermes dashboard plugins:

- `drive` - file manager for Workspace, Fleet, and Linked roots.
- `code` - code editor, file explorer, previews, and git source control.
- `terminal` - managed pty terminal sessions.
- `arclink-managed-context` - no-tab plugin that hot-injects refreshed local
  ArcLink managed context into Hermes turns (without mutating built-in
  `MEMORY.md` snapshots).
- `arclink-theme` - no-tab plugin that installs the ArcLink dashboard theme
  and makes it the default.

Each plugin follows the Hermes plugin layout:

```text
plugin-name/
  plugin.yaml
  __init__.py
  dashboard-themes/        # optional theme YAMLs copied into HERMES_HOME
  dashboard/
    manifest.json
    plugin_api.py
    dist/index.js
    dist/style.css
```

The dashboard extension surface requires Hermes `v2026.4.30` or newer. Install
by copying the desired plugin directories into `~/.hermes/plugins/` and adding
their names to `plugins.enabled` in `config.yaml`.

The plugins default to the ArcLink Workspace root (`ARCLINK_WORKSPACE_ROOT`,
then the vault/Drive root, then legacy workspace env vars) and stay
dependency-light: local filesystem APIs, browser-native preview surfaces,
standard `git`, and Python pty support. Optional roots and limits are configured
with generic env vars documented in each plugin README.
