# Code

Code is a lightweight Hermes dashboard plugin that adds a native code
workspace, manual-save editor, file explorer, previews, and git source-control
surface without patching Hermes core.

## Install

Copy this directory to `~/.hermes/plugins/code` and enable `code` under
`plugins.enabled` in `config.yaml`. The dashboard plugin surface requires
Hermes `v2026.4.30` or newer.

## Roots

- Workspace defaults to `$HOME`, or `CODE_WORKSPACE_ROOT` when set.
- Vault uses `CODE_VAULT_ROOT`, `DRIVE_ROOT`,
  `KNOWLEDGE_VAULT_ROOT`, `VAULT_DIR`, `~/Vault`, or `$HERMES_HOME/Vault`.

## Behavior

- Workspace and Vault are browsable as sibling roots.
- Search is inline above the tree.
- File clicks open a rotating preview tab; double-click pins a tab.
- Saves are explicit and protected by disk-hash conflict checks.
- Source control is allowlisted to repo-confined `git` operations.
- Text, Markdown, PDF, image, audio, and video previews can open in tabs and
  full-screen preview mode when browser-supported.

## Check

```bash
python3 -m py_compile plugins/hermes-agent/code/dashboard/plugin_api.py
node --check plugins/hermes-agent/code/dashboard/dist/index.js
```
