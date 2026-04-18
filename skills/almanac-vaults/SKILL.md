---
name: almanac-vaults
description: Use to inspect the active Almanac vault catalog, curate subscribed vs default vaults, inspect the canonical managed-memory payload, and trigger subscription refresh without changing qmd retrieval access.
---

# Almanac Vaults

Use this skill when an enrolled user wants to manage Almanac vault subscriptions and understand which vaults are represented in the agent's managed-memory routing stubs.

## Contract

- all approved users may retrieve from any active vault through qmd
- subscriptions only affect managed-memory awareness and Curator push behavior
- active vaults come from valid `.vault` files in the shared vault tree
- missing or malformed `.vault` files fail safe and should be surfaced as warnings
- the canonical managed-memory payload comes from `agents.managed-memory`, not from hand-editing local memory files

## Command surface

Use the skill script:

```bash
scripts/curate-vaults.sh curate
```

Subcommands:

```bash
scripts/curate-vaults.sh list
scripts/curate-vaults.sh refresh
scripts/curate-vaults.sh stubs
scripts/curate-vaults.sh subscribe <vault-name>
scripts/curate-vaults.sh unsubscribe <vault-name>
scripts/curate-vaults.sh --json curate
```

What they do:

- `list` — show the current vault catalog with subscribed/default markers
- `refresh` — run `vaults.refresh` for the current agent
- `stubs` — fetch the canonical managed-memory payload (`agents.managed-memory`)
- `subscribe` / `unsubscribe` — change one vault subscription via `vaults.subscribe`
- `curate` — show the unified view: catalog, active subscriptions, managed-memory keys, and the trigger rail used to keep stubs in sync

Markers:

- `+` subscribed now
- `·` default vault that exists in the catalog but is not currently subscribed
- `-` explicitly unsubscribed / not in the active stub-aware set

## Environment

The script expects the same user-agent environment used by the existing Almanac rails:

- `ALMANAC_MCP_URL` — defaults to `http://127.0.0.1:${ALMANAC_MCP_PORT:-8282}/mcp`
- `ALMANAC_BOOTSTRAP_TOKEN_FILE` or `ALMANAC_BOOTSTRAP_TOKEN_PATH`
- `HERMES_HOME` — defaults to the user-agent Hermes home

By default it reads the bootstrap token from:

```text
$HERMES_HOME/secrets/almanac-bootstrap-token
```

## Trigger model

This skill is about curation and inspection, but it should explain the sync rail clearly:

- `vaults.subscribe` queues a curator `brief-fanout` event for the targeted agent
- vault catalog diffs from Curator refresh queue `brief-fanout` for all active user agents
- Curator fanout publishes a fresh canonical managed-memory payload per agent
- the user-agent refresh rail materializes that payload locally into:
  - `$HERMES_HOME/state/almanac-vault-reconciler.json`
  - `$HERMES_HOME/memories/almanac-managed-stubs.md`
  - `$HERMES_HOME/memories/MEMORY.md`

That means this skill should not invent a second state system.

## Guardrails

- stay within the current user's `HERMES_HOME` plus the shared Almanac control plane; do not browse other users' home directories or central deployment config files
- do not edit `.vault` files unless the user explicitly asks
- do not treat qmd access as revoked when a user unsubscribes from a vault
- if a vault listed in memory no longer exists in the catalog, treat that as drift and refresh before answering
- do not hand-edit `MEMORY.md`; use the canonical payload + refresh rail
- use qmd for deep retrieval, and the vault subscription rail for ambient-awareness / stub management

## Recommended usage

When the user asks things like:

- "what vaults am I subscribed to?"
- "which vaults are in my managed memory?"
- "unsubscribe me from Teams"
- "refresh my Almanac vault context"
- "why did Curator notify me about this vault?"

Run the script first, then explain the result using the catalog + managed payload + trigger rail.
