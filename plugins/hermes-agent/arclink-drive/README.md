# ArcLink Drive

ArcLink Drive is a Hermes dashboard plugin that presents agent files as a
native file manager without patching Hermes core dashboard code.

## Ownership

- Plugin package: `plugins/hermes-agent/arclink-drive/`
- Dashboard API: `plugins/hermes-agent/arclink-drive/dashboard/plugin_api.py`
- Dashboard assets: `plugins/hermes-agent/arclink-drive/dashboard/dist/`
- Default install path: `bin/install-arclink-plugins.sh`

Hermes owns the plugin host. ArcLink owns the allowed roots, backend selection,
status contract, UI assets, and secret redaction.

## Backends

- Local vault backend: uses `ARCLINK_DRIVE_ROOT`,
  `ARCLINK_KNOWLEDGE_VAULT_ROOT`, `ARCLINK_AGENT_VAULT_DIR`, `VAULT_DIR`,
  `~/ArcLink`, `~/Vault`, `$HERMES_HOME/ArcLink`, or `$HERMES_HOME/Vault`, in
  that order.
- Nextcloud WebDAV backend: uses sanitized Nextcloud access state from
  `$HERMES_HOME/state/arclink-web-access.json` and the reconciler resource ref.
  Credentials stay server-side inside the plugin API.
- `ARCLINK_DRIVE_BACKEND=nextcloud-webdav` can force WebDAV when credentials
  are available. The default `auto` prefers the local mounted vault when it
  exists because that avoids extra network/service overhead.

## Current Behavior

- `/status` returns backend, mount, username, URL, local root, and capability
  flags without returning WebDAV passwords.
- `/items` browses folders. Local backend search is bounded by filename.
- `/content` previews bounded text-like files only.
- `/download` returns files from the selected backend.
- `/upload` accepts file uploads into the selected folder.
- `/mkdir`, `/move`, and `/rename` mutate files under the selected backend.
- `/favorite` stores local favorite metadata and maps to Nextcloud favorite
  metadata where WebDAV supports it.
- `/delete` moves local files into `.arclink-trash`; WebDAV delete uses the
  provider delete call.
- `/trash` and `/restore` are local-backend recovery APIs.
- The dashboard presents Workspace and Vault as sibling tree roots, with
  expandable folder carets, minimal file/folder icons, cross-root search,
  directory contents in the main pane, and selected-item metadata/actions in
  the detail strip rather than opening file contents.

## Assumptions

- Local file operations must remain confined to the selected vault root.
- Symlink or path traversal outside the root is not a supported access path.
- WebDAV credentials are never returned through status, logs, or docs.
- UI confirmations own the human safety step for delete, restore, overwrite,
  and drag/drop operations.

## Runbook

After changing Drive behavior:

```bash
python3 -m py_compile plugins/hermes-agent/arclink-drive/dashboard/plugin_api.py
python3 tests/test_arclink_plugins.py
node --check plugins/hermes-agent/arclink-drive/dashboard/dist/index.js
git diff --check
```

## Boundaries

Drive is a first-generation local/WebDAV file manager moving toward Google
Drive parity. Share-link management, collaborative comments, tags, chunked
uploads, richer trash browsing, and cross-root copy/move remain future release
gates. Do not claim Nextcloud sharing is implemented until the backend has a
real adapter and tests.
