# ArcLink First-Day User Guide

This guide is for a person whose ArcLink agent has just been provisioned.

## Where To Talk

Use the chat channel where onboarding completed.

- Discord users should receive a direct message from the user-agent bot after
  Curator shows the confirmation code. If it does not arrive, DM Curator
  `/retry-contact`.
- Telegram users must open the shown agent bot handle and press Start. Telegram
  bots cannot cold-DM a user.
- Operators can retry Discord handoff with
  `./bin/arclink-ctl onboarding retry-contact <unixusername|discordname>`.

## Dashboard

The dashboard links are sent at completion and shown in the user dashboard.
Dashboard access is protected by ArcLink's generated web-access credential and
session proxy. Do not send dashboard passwords or session material in shared
channels.

When ArcLink presents credential handoff items, copy them into a password
manager and then acknowledge storage in the user session. After acknowledgement,
the user API hides that handoff from future responses; reissue requires an
operator rotation or recovery action.

The dashboard includes:

- **Drive:** browse and manage vault files inside the allowed vault/workspace
  root. Accepted linked resources appear under a read-only `Linked` root when
  the projection is available.
- **Code:** edit files and inspect git status inside the configured workspace.
  Linked resources are readable but not writable or reshareable.
- **Terminal:** managed pty sessions with bounded scrollback, same-origin SSE
  streaming, polling fallback, and confirmation-gated close.

If a workspace surface reports disabled or unavailable, treat that as a real
state. Ask the operator to run health/refresh instead of trying host paths.

## Vault And Knowledge

Your `~/ArcLink` alias points at the shared vault lane made available to your
agent. Markdown, text files, and PDF sidecar markdown become searchable through
ArcLink knowledge tools after indexing. PDF conversion may take a timer cycle.

Use these agent-facing tools first:

- `knowledge.search-and-fetch`
- `vault.search-and-fetch`
- `vault.fetch`
- `notion.search-and-fetch`
- `notion.fetch`
- `ssot.read`
- `ssot.write`

Do not ask the agent to browse private runtime directories, token files, or
other users' homes.

## Notion

Shared Notion writes go through the SSOT broker. This keeps org pages under the
configured shared root and blocks destructive archive/delete/trash style
requests unless an explicit approval rail exists.

Personal Notion OAuth/MCP access, if present, is separate from shared SSOT. Use
shared SSOT for organization pages and personal Notion only for personal
workspace material.

## Backups

ArcLink may offer a private Hermes-home backup setup after onboarding. If you
skip it, the skip is durable and you should not be repeatedly prompted. If you
use it, provide only a private GitHub repo; public repos are refused.

Vault and private runtime backups are operator-owned. Do not paste deploy keys,
tokens, or `.env` values into chat.

## Expected Recovery Paths

- No agent DM after Discord onboarding: use `/retry-contact`.
- Telegram agent has not greeted you: open the bot handle and press Start.
- Dashboard link fails: ask the operator to refresh the user agent and check
  health.
- Knowledge misses a new file: wait for the qmd/vault timer or ask for a
  refresh.
- Notion write is refused: move the content under an owned/shared page or ask
  for an approved SSOT path.
- Terminal disabled: root/unrestricted workspace guards may be active; ask for
  operator repair rather than bypassing the guard.
