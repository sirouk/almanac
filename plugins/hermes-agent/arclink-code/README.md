# ArcLink Code

ArcLink Code is a Hermes dashboard plugin that presents a native code workspace
inside Hermes without patching Hermes core dashboard code.

## Ownership

- Plugin package: `plugins/hermes-agent/arclink-code/`
- Dashboard API: `plugins/hermes-agent/arclink-code/dashboard/plugin_api.py`
- Dashboard assets: `plugins/hermes-agent/arclink-code/dashboard/dist/`
- Default install path: `bin/install-arclink-plugins.sh`

Hermes owns the plugin host. ArcLink owns the workspace root policy, editor
contract, source-control operations, UI assets, and secret redaction.

## Workspace

- Uses `ARCLINK_CODE_WORKSPACE_ROOT` when set.
- Falls back to the current user's home directory.
- Exposes `~/ArcLink` as the natural vault path when present.
- Keeps code-server/OpenVSCode-style access as an optional "Full IDE" link when
  `$HERMES_HOME/state/arclink-web-access.json` contains a code URL.

In Docker provisioning, the workspace is mounted at `/workspace` and exported
as `ARCLINK_CODE_WORKSPACE_ROOT`.

## Current Behavior

- `/status` returns workspace root, optional full-IDE URL, editor mode, and
  capability flags without returning credentials.
- `/items` browses folders under the workspace root.
- `/file` opens bounded text-like files and returns language hints plus a
  SHA-256 file hash.
- `/save` writes text atomically and rejects stale writes when the expected hash
  no longer matches the file on disk.
- `/mkdir` creates folders under the workspace root.
- `/search` performs bounded workspace search over file names and safe text
  snippets.
- `/ops/rename`, `/ops/move`, `/ops/duplicate`, `/ops/trash`, `/trash`, and
  `/ops/restore` provide confined file operations. Trash uses private Hermes
  state and requires explicit confirmation.
- `/repos` scans a bounded workspace depth for git repositories.
- `/git/status` reports branch plus staged, unstaged, and untracked changes.
- `/git/stage`, `/git/unstage`, `/git/discard`, `/git/commit`,
  `/git/ignore`, `/git/pull`, and `/git/push` perform allowlisted git
  operations. Discard, pull, and push require explicit confirmation.

## Assumptions

- Editing is manual-save by default. Auto-save is not enabled by this plugin.
- File operations must remain confined to the workspace root.
- Source-control operations must stay allowlisted and repo-root confined.
- Destructive operations belong behind UI confirmation and backend confirmation
  flags where applicable.
- The plugin status contract must not expose tokens, passwords, deploy keys,
  OAuth material, or raw `.env` values.

## Runbook

After changing Code behavior:

```bash
python3 -m py_compile plugins/hermes-agent/arclink-code/dashboard/plugin_api.py
python3 tests/test_arclink_plugins.py
node --check plugins/hermes-agent/arclink-code/dashboard/dist/index.js
git diff --check
```

## Boundaries

The shipped editor shell is native and lightweight. It does not bundle Monaco
today: the current rationale is to keep the native Hermes plugin CSP and asset
path simple until a vendored Monaco bundle is proven inside the plugin host.
Full code-server remains a separate top-level IDE surface rather than an
embedded component.
