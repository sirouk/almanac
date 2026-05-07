# Drive

Drive is a lightweight Hermes dashboard plugin that adds a native file manager
without patching Hermes core.

## Install

Copy this directory to `~/.hermes/plugins/drive` and enable `drive` under
`plugins.enabled` in `config.yaml`. The dashboard plugin surface requires
Hermes `v2026.4.30` or newer.

## Roots

- Workspace defaults to `$HOME`.
- Vault uses the first existing directory from `DRIVE_ROOT`,
  `KNOWLEDGE_VAULT_ROOT`, `AGENT_VAULT_DIR`, `VAULT_DIR`, `~/Vault`, or
  `$HERMES_HOME/Vault`.
- Optional WebDAV/Nextcloud preview uses `NEXTCLOUD_URL` or
  `DRIVE_NEXTCLOUD_URL` with sanitized server-side access state from
  `$HERMES_HOME/state/web-access.json`.

## Behavior

- Workspace and Vault are sibling tree roots.
- Search traverses both roots.
- Single-click selects and previews files; double-click opens folders.
- Drag/drop upload targets the current folder.
- Rename, move, copy, duplicate, delete, restore, and batch operations are
  confined to the selected root.
- Delete moves local files into `.drive-trash`.
- Text, Markdown, PDF, image, audio, and video previews render in place when
  browser-supported.

## Check

```bash
python3 -m py_compile plugins/hermes-agent/drive/dashboard/plugin_api.py
node --check plugins/hermes-agent/drive/dashboard/dist/index.js
```
