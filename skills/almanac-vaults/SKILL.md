---
name: almanac-vaults
description: Use to inspect the active Almanac vault catalog, curate subscribed vs default vaults, inspect the canonical managed-memory payload that feeds plugin context, and trigger subscription refresh without changing qmd retrieval access.
---

# Almanac Vaults

Use this skill when an enrolled user wants to manage Almanac vault subscriptions and understand which vaults are represented in the agent's plugin-managed routing context.

## Hermes Recipe Card

Preferred agent path: call the `almanac-mcp` MCP tools directly. Do not use
`scripts/curate-vaults.sh` from a Hermes turn unless MCP transport itself is
broken and you are debugging the harness.

The `almanac-managed-context` plugin injects local auth into Almanac MCP calls
before dispatch. Leave `token` out of normal Hermes tool calls.

Common calls:

```json
{"tool":"catalog.vaults","arguments":{}}
{"tool":"vaults.refresh","arguments":{}}
{"tool":"agents.managed-memory","arguments":{}}
{"tool":"vaults.subscribe","arguments":{"vault_name":"Teams","subscribed":false}}
```

Decision tree:

- “What vaults am I subscribed to?” -> call `catalog.vaults` once.
- “Refresh my context” -> call `vaults.refresh`, then
  `agents.managed-memory` only if you need to inspect the canonical payload.
- “Which rails do I know about?” -> call `agents.managed-memory`.
- “Subscribe/unsubscribe me” -> call `vaults.subscribe` once with
  `subscribed:true` or `false`, then explain that Curator fanout refreshes the
  local plugin-managed context.
- For deep content retrieval, use `almanac-qmd-mcp`; vault subscriptions shape
  ambient awareness and push behavior, not qmd access.

## Contract

- all approved users may retrieve from any active vault through qmd
- subscriptions only affect plugin-managed awareness and Curator push behavior
- active vaults come from valid `.vault` files in the shared vault tree
- plain folders without `.vault` metadata are allowed; they are still qmd-indexed but do not become subscription lanes
- malformed or nested `.vault` files fail safe and should be surfaced as warnings
- `.vault` edits reload through the vault watcher; moved `.vault` directories may settle on the next hourly Curator refresh
- the canonical managed-memory payload comes from `agents.managed-memory`, not from hand-editing local memory files

## Human CLI Fallback

These wrappers are for humans and operator debugging, not the preferred Hermes
agent path. They exercise the same MCP rails while resolving local auth from
the installed Hermes home:

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
- `curate` — show the unified view: catalog, active subscriptions, plugin-context keys, and the trigger rail used to keep context in sync

Markers:

- `+` subscribed now
- `·` default vault that exists in the catalog but is not currently subscribed
- `-` explicitly unsubscribed / not in the active stub-aware set

## Environment

The script expects the same user-agent environment used by the existing Almanac rails:

- `ALMANAC_MCP_URL` — defaults to `http://127.0.0.1:${ALMANAC_MCP_PORT:-8282}/mcp`
- `ALMANAC_BOOTSTRAP_TOKEN_FILE` or `ALMANAC_BOOTSTRAP_TOKEN_PATH`
- `HERMES_HOME` — defaults to the user-agent Hermes home

## Trigger model

This skill is about curation and inspection, but it should explain the sync rail clearly:

- `vaults.subscribe` queues a curator `brief-fanout` event for the targeted agent
- vault catalog diffs from Curator refresh queue `brief-fanout` for all active user agents
- Curator fanout publishes a fresh canonical managed-memory payload per agent
- the user-agent refresh rail materializes that payload locally into plugin state:
  - `$HERMES_HOME/state/almanac-vault-reconciler.json`

That means this skill should not invent a second state system.

## Guardrails

- stay within the current user's `HERMES_HOME` plus the shared Almanac control plane; do not browse other users' home directories or central deployment config files
- do not edit `.vault` files unless the user explicitly asks
- do not treat qmd access as revoked when a user unsubscribes from a vault
- if a vault listed in memory no longer exists in the catalog, treat that as drift and refresh before answering
- do not hand-edit `MEMORY.md`; use the canonical payload + refresh rail
- use qmd for deep retrieval, and the vault subscription rail for plugin-managed ambient-awareness state

## Recommended usage

When the user asks things like:

- "what vaults am I subscribed to?"
- "which vaults are in my managed context?"
- "unsubscribe me from Teams"
- "refresh my Almanac vault context"
- "why did Curator notify me about this vault?"

Use the MCP recipe card first, then explain the result using the catalog,
managed payload, and trigger rail.
