# Drive

Drive is a lightweight Hermes dashboard plugin that adds a native file manager
without patching Hermes core.

## Install

Copy this directory to `~/.hermes/plugins/drive` and enable `drive` under
`plugins.enabled` in `config.yaml`. The dashboard plugin surface requires
Hermes `v2026.4.30` or newer.

## Roots

Drive exposes four sibling tree roots in this order: Vault, Workspace, Fleet,
and Linked. The default selected root is Vault, then Workspace.

- Vault uses the first existing directory from `DRIVE_ROOT`,
  `KNOWLEDGE_VAULT_ROOT`, `AGENT_VAULT_DIR`, `VAULT_DIR`, `~/Vault`, or
  `$HERMES_HOME/Vault`.
- Workspace uses the first existing directory from `DRIVE_WORKSPACE_ROOT`,
  `CODE_WORKSPACE_ROOT`, or `$HERMES_HOME/workspace`.
- Fleet (the read-write git-synced fleet shared folder) uses the first existing
  directory from `DRIVE_FLEET_SHARED_ROOT`, `ARCLINK_FLEET_SHARED_ROOT`, or
  `$HERMES_HOME/fleet-shared`.
- Linked resources use the first existing directory from `DRIVE_LINKED_ROOT`,
  `ARCLINK_LINKED_RESOURCES_ROOT`, or `$HERMES_HOME/linked`.
- Drive uses local roots only; legacy Nextcloud/WebDAV browser access is not
  required.

## Behavior

- Vault, Workspace, Fleet, and Linked are sibling tree roots when available.
  Workspace and Fleet are writable; the Fleet root is the git-synced fleet
  shared folder. Linked is system-managed (see below).
- Search traverses available roots.
- Single-click selects and previews files; double-click opens folders.
- Drag/drop upload targets the current folder.
- Rename, move, delete, restore, and write-style batch operations are confined
  to writable roots.
- Direct share-link creation is not exposed from Drive. When
  `DRIVE_SHARE_REQUEST_BROKER_URL` or `ARCLINK_SHARE_REQUEST_BROKER_URL` is
  configured together with `DRIVE_SHARE_REQUEST_BROKER_TOKEN_FILE` or
  `ARCLINK_SHARE_REQUEST_BROKER_TOKEN_FILE`, writable Vault/Workspace items
  expose a brokered `Request Share` action that posts to `/share/request` using
  ArcLink share-grant semantics. The payload includes the owner deployment id
  from `ARCLINK_DEPLOYMENT_ID` or `state/arclink-web-access.json`, and the route
  sends the token only as the `X-ArcLink-Share-Request-Broker-Token` broker
  header. Without a configured broker URL, token file, and owner deployment
  identity, share requests fail closed before any external call. Linked roots
  never expose the action.
- Linked accepts writes inside accepted shared folders while keeping the Linked
  root itself system-managed. Browse, search, preview, download, upload, folder
  creation, rename, move, delete, and restore are confined to the accepted
  folder source. Sharing from Linked stays disabled, and copy/duplicate can
  still create owned copies in Vault or Workspace without granting reshare.
- Delete moves local files into `.drive-trash`.
- Text, Markdown, JSON, CSV/TSV, PDF, image, audio, video, and browser-native
  file previews render in place when browser-supported.

## Check

```bash
python3 -m py_compile plugins/hermes-agent/drive/dashboard/plugin_api.py
node --check plugins/hermes-agent/drive/dashboard/dist/index.js
```
