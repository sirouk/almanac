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
- Linked resources use the first existing directory from `CODE_LINKED_ROOT`,
  `ARCLINK_LINKED_RESOURCES_ROOT`, or `$HERMES_HOME/linked`.

## Behavior

- Workspace, Vault, and Linked are browsable as sibling roots when available.
- Search is inline above the tree.
- File clicks open a rotating preview tab; double-click pins a tab.
- Saves are explicit and protected by disk-hash conflict checks.
- Source control is allowlisted to repo-confined `git` operations.
- Right-click share-link creation is not exposed from Code until a live
  ArcLink browser broker or approved Nextcloud-backed adapter is enabled.
  Agents can use the governed ArcLink MCP `shares.request` rail for named
  Vault/Workspace paths when that path is appropriate.
- Linked is read-only: file reads, previews, repository discovery, git status,
  and git diff are allowed; saves, sharing, and git mutations are rejected.
  Duplicate from Linked writes a new owned copy into Workspace or Vault and does
  not grant resharing on the original linked resource.
- Text, Markdown, PDF, image, audio, and video previews can open in tabs and
  full-screen preview mode when browser-supported.

## Check

```bash
python3 -m py_compile plugins/hermes-agent/code/dashboard/plugin_api.py
node --check plugins/hermes-agent/code/dashboard/dist/index.js
```
