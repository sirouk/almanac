---
name: almanac-resources
description: Use when an enrolled user asks for /almanac-resources, Almanac links, dashboard/code workspace URLs, Nextcloud login, the remote helper, backup setup, SSH setup, or where the shared vault lives from their own agent lane.
---

# Almanac Resources

Use this skill when the user asks for their Almanac resources, links, workspace, dashboard, Nextcloud login, remote helper, backup setup, or shared vault location.

The `almanac-managed-context` plugin can answer `/almanac-resources` directly from local state. If you need a human-readable fallback, run:

```bash
scripts/show-resources.sh
```

## Contract

- read only the current user's local Almanac state under `$HERMES_HOME/state`
- never print passwords, tokens, deploy keys, bootstrap tokens, or raw secret files
- use the current user's home alias as the vault home base: `~/Almanac`
- in VS Code and shell-facing explanations, prefer `/home/<user>/Almanac` over central service-user paths such as `/home/almanac/...`
- explain that the shared Vault and control rails are already wired into the agent by default

## Expected Response Shape

When answering the user, include the useful links and omit credentials:

- Web access: Hermes dashboard, dashboard username, Nextcloud login username, code workspace, workspace root, and Almanac vault path
- Host helper: `~/.local/bin/almanac-agent-hermes`
- Backups: `~/.local/bin/almanac-agent-configure-backup` and the warning not to reuse shared deploy keys
- Shared Almanac links: Nextcloud Vault access, shared Notion SSOT, Notion webhook note, and the local `~/Almanac` vault path
- Optional remote agent CLI: the curl installer command, `/ssh-key <public key>` callback, generated wrapper name, and SSH target when the local state has a tailnet host and Unix user

## Guardrails

- do not ask the user to paste or reveal their shared password
- do not claim the password is unknown in a way that encourages recovery in chat; say credentials are intentionally omitted and access reset goes through Curator/operator
- do not inspect other users' home directories
- do not read central deployment secrets such as `almanac.env`, `.almanac-operator.env`, or backup key material from a user-agent session
- if a path points at the shared vault, translate it to the user-visible `~/Almanac` alias whenever possible
