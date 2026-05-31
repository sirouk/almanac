# Code

Code is a lightweight Hermes dashboard plugin that adds a native code
workspace, manual-save editor, file explorer, previews, and git source-control
surface without patching Hermes core.

## Install

Copy this directory to `~/.hermes/plugins/code` and enable `code` under
`plugins.enabled` in `config.yaml`. The dashboard plugin surface requires
Hermes `v2026.4.30` or newer.

## Roots

- Workspace uses `CODE_WORKSPACE_ROOT` or `DRIVE_WORKSPACE_ROOT` when set,
  otherwise `$HERMES_HOME/workspace`.
- Vault uses `CODE_VAULT_ROOT`, `DRIVE_ROOT`,
  `KNOWLEDGE_VAULT_ROOT`, `VAULT_DIR`, `~/Vault`, or `$HERMES_HOME/Vault`.
- Fleet (the git-synced fleet shared folder) uses the first existing directory
  from `CODE_FLEET_SHARED_ROOT`, `ARCLINK_FLEET_SHARED_ROOT`, or
  `$HERMES_HOME/fleet-shared`.
- Linked resources use the first existing directory from `CODE_LINKED_ROOT`,
  `ARCLINK_LINKED_RESOURCES_ROOT`, or `$HERMES_HOME/linked`.

## Behavior

- Workspace, Vault, Fleet, and Linked are browsable as sibling roots when
  available.
- Search is inline above the tree.
- File clicks open a rotating preview tab; double-click pins a tab.
- Saves are explicit and protected by disk-hash conflict checks.
- Source control is allowlisted to repo-confined `git` operations. Read
  operations (status, commits, diff) are allowed on every root. Mutating git
  operations require a writable root: `git pull` (run as `pull --ff-only`) and
  `git push` both require `confirm: true` in the request body and are rejected
  otherwise. Git mutations are blocked on the Linked root (returns
  `403 Git mutations are disabled for Linked resources`).
- Direct share-link creation is not exposed from Code. When
  `CODE_SHARE_REQUEST_BROKER_URL` or `ARCLINK_SHARE_REQUEST_BROKER_URL` is
  configured together with `CODE_SHARE_REQUEST_BROKER_TOKEN_FILE` or
  `ARCLINK_SHARE_REQUEST_BROKER_TOKEN_FILE`, writable Workspace/Vault items
  expose a brokered `Request Share` action that posts to `/share/request` using
  ArcLink share-grant semantics. The payload includes the owner deployment id
  from `ARCLINK_DEPLOYMENT_ID` or `state/arclink-web-access.json`, and the route
  sends the token only as the `X-ArcLink-Share-Request-Broker-Token` broker
  header. Without a configured broker URL, token file, and owner deployment
  identity, share requests fail closed before any external call. Linked roots
  never expose the action.
- Linked accepts file saves and folder creation inside accepted shared folders
  while keeping the Linked root itself system-managed. File reads, previews,
  repository discovery, git status, and git diff are allowed; sharing and git
  mutations from Linked are rejected. Duplicate from Linked can still write a
  new owned copy into Workspace or Vault without granting reshare.
- Text, Markdown, PDF, image, audio, and video previews can open in tabs and
  full-screen preview mode when browser-supported.

## Check

```bash
python3 -m py_compile plugins/hermes-agent/code/dashboard/plugin_api.py
node --check plugins/hermes-agent/code/dashboard/dist/index.js
```
