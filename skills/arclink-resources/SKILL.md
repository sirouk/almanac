---
name: arclink-resources
description: Use when an enrolled user asks for /arclink-resources, ArcLink links, dashboard/code workspace URLs, Nextcloud login, the remote helper, backup setup, SSH setup, or where the shared vault lives from their own agent lane.
---

# ArcLink Resources

Use this skill when the user asks for their ArcLink resources, links, workspace, dashboard, Nextcloud login, remote helper, backup setup, or shared vault location.

The `arclink-managed-context` plugin can answer `/arclink-resources` directly from local state. If you need a human-readable fallback, run:

```bash
scripts/show-resources.sh
```

## Contract

- read only the current user's local ArcLink state under `$HERMES_HOME/state`
- never print passwords, tokens, deploy keys, bootstrap tokens, or raw secret files
- use the current user's home alias as the vault home base: `~/ArcLink`
- in VS Code and shell-facing explanations, prefer `/home/<user>/ArcLink` over central service-user paths such as `/home/arclink/...`
- explain that the shared Vault and control rails are already wired into the agent by default

## Expected Response Shape

When answering the user, include the useful links and omit credentials:

- Web access: Hermes dashboard, dashboard username, Nextcloud login username, code workspace, workspace root, and ArcLink vault path
- Host helper: `~/.local/bin/arclink-agent-hermes`
- Backups: `~/.local/bin/arclink-agent-configure-backup` and the warning not to reuse shared deploy keys
- Shared ArcLink links: Nextcloud Vault access, shared Notion SSOT, Notion webhook note, and the local `~/ArcLink` vault path
- Optional remote agent CLI: the curl installer command, `/ssh-key <public key>` callback, generated wrapper name, and SSH target when the local state has a tailnet host and Unix user

## Guardrails

- do not ask the user to paste or reveal their shared password
- do not claim the password is unknown in a way that encourages recovery in chat; say credentials are intentionally omitted and access reset goes through Curator/operator
- do not inspect other users' home directories
- do not read central deployment secrets such as `arclink.env`, `.arclink-operator.env`, or backup key material from a user-agent session
- if a path points at the shared vault, translate it to the user-visible `~/ArcLink` alias whenever possible
