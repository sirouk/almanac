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
- Linked resources use the first existing directory from `DRIVE_LINKED_ROOT`,
  `ARCLINK_LINKED_RESOURCES_ROOT`, or `$HERMES_HOME/linked`.
- Drive uses local roots only; legacy Nextcloud/WebDAV browser access is not
  required.

## Behavior

- Workspace, Vault, and Linked are sibling tree roots when available.
- Search traverses available roots.
- Single-click selects and previews files; double-click opens folders.
- Drag/drop upload targets the current folder.
- Rename, move, delete, restore, and write-style batch operations are confined
  to writable roots.
- Right-click share-link creation is not exposed from Drive until a live
  ArcLink browser broker or approved Nextcloud-backed adapter is enabled.
  Agents can use the governed ArcLink MCP `shares.request` rail for named
  Vault/Workspace paths when that path is appropriate.
- Linked is read-only: browse, search, preview, and download are allowed;
  upload, rename, move, delete, restore, and sharing are disabled. Copy and
  duplicate from Linked create a new owned copy in Vault or Workspace and do not
  grant resharing on the original linked resource.
- Delete moves local files into `.drive-trash`.
- Text, Markdown, PDF, image, audio, and video previews render in place when
  browser-supported.

## Check

```bash
python3 -m py_compile plugins/hermes-agent/drive/dashboard/plugin_api.py
node --check plugins/hermes-agent/drive/dashboard/dist/index.js
```
