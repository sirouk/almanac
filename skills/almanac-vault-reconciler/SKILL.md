---
name: almanac-vault-reconciler
description: Use when an agent needs to keep compact managed memories aligned with an Almanac vault behind qmd, run an initial reconciliation, or explain/repair the first-flight + refresh + Curator-triggered sync rails.
---

# Almanac Vault Reconciler

Use this skill when the user wants an agent to treat a shared markdown vault plus qmd as the long-term knowledge layer while keeping only a small, managed memory stub inside the agent.

This skill is for ongoing maintenance, not full-content ingestion.

It does not turn every note or PDF into built-in agent memory.

## Core contract

The vault is the source of truth.

qmd is the deep retrieval layer over that vault.

Built-in memory should hold only compact routing hints, not note bodies or large knowledge dumps.

Managed memory entries must use these prefixes exactly:

- `[managed:almanac-skill-ref]`
- `[managed:vault-ref]`
- `[managed:qmd-ref]`
- `[managed:vault-topology]`

Only touch memories with those prefixes.

## Existing Almanac sync rails

Do not invent a second state machine when Almanac already has the right rails.

There are three intended triggers:

1. first flight
   - `activate-agent.sh` runs `almanac-first-contact`
   - first-contact runs `vaults.refresh`, fetches `agents.managed-memory`, and materializes the initial stubs

2. scheduled refresh
   - `almanac-user-agent-refresh.timer` runs every 4 hours
   - `user-agent-refresh.sh` refreshes subscriptions, rewrites local managed stubs, and drains recent notifications

3. Curator-driven sync
   - curator refresh and subscription changes enqueue curator `brief-fanout`
   - Curator fanout publishes canonical managed-memory payloads per agent
   - the activation-trigger rail can cause `almanac-user-agent-refresh.service` to run immediately for affected agents

## Simplest state model

Keep state minimal and local to the user agent:

- `$HERMES_HOME/state/almanac-vault-reconciler.json`
- `$HERMES_HOME/memories/almanac-managed-stubs.md`
- `$HERMES_HOME/memories/MEMORY.md`
- `$HERMES_HOME/state/almanac-recent-events.json`

The shared control plane may also publish:

- `$ALMANAC_AGENTS_STATE_DIR/<agent-id>/managed-memory.json`
- `$STATE_DIR/activation-triggers/<agent-id>.json`

That is enough. Do not build an additional ad hoc memory ledger.

## Use this skill to

- discover the active shared vault that qmd is indexing
- explain or repair managed memory drift
- verify that first-flight seeding ran correctly
- verify that the 4-hour refresh rail exists and is writing local stubs
- verify that Curator-triggered fanout is publishing managed-memory payloads and signaling the agent refresh rail
- create or repair one recurring 4-hour reconciliation job only when the platform actually needs it

## Managed payload meaning

The canonical payload should teach future sessions:

- which Almanac skills are active defaults
- where the shared vault lives conceptually
- that qmd is the deeper retrieval layer and should be queried first for vault-relevant questions
- which vaults are currently subscribed/default/unsubscribed at a compact level

## Recommended workflow

When the user says memory is stale or asks how Almanac sync works, do this in order:

1. verify first-contact state files exist
2. verify the current managed-memory payload via `agents.managed-memory`
3. verify the local stub files under the current user's `HERMES_HOME`
4. verify the 4-hour refresh rail (`user-agent-refresh`) is healthy
5. verify Curator fanout / activation-trigger behavior when relevant
6. report drift and repair the Almanac-side rail, not Hermes internals

## Guardrails

- prefer qmd through MCP over direct filesystem reads when it is available
- for user-agent runs on a shared host, do not inspect central deployment secrets such as `almanac.env` or source `bin/common.sh`
- do not browse other users' home directories
- do not rely on vague reassurance; point to the actual state files and rails
- do not store note bodies or PDF bodies in built-in memory
- do not patch Hermes code for this; use Almanac skills, settings, timers, payloads, and MCP rails
