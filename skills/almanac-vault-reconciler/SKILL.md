---
name: almanac-vault-reconciler
description: Use when an agent needs to keep compact managed memories aligned with an Almanac vault behind qmd, run an initial reconciliation, or explain/repair the first-flight + refresh + Curator-triggered sync rails.
---

# Almanac Vault Reconciler

Use this skill when the user wants an agent to treat a shared markdown vault plus qmd as the long-term knowledge layer while keeping only a small, managed memory stub inside the agent.

This skill is for ongoing maintenance, not full-content ingestion.

It does not turn every note or PDF into built-in agent memory.

If the user is asking a normal vault-backed knowledge question rather than diagnosing memory drift, use `almanac-qmd-mcp` first instead of searching the repo or walking the sync rails.

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

## Warm reload reality

Today, Almanac can refresh the managed stubs on disk immediately, and the preferred no-core-code path is to let the shipped `almanac-managed-context` Hermes plugin inject refreshed local Almanac context into future turns.

Important distinctions:

- `user-agent-refresh.sh` rewrites the local files correctly
- Hermes built-in `MEMORY.md` is still loaded into a frozen prompt snapshot for the session
- the `almanac-managed-context` plugin avoids mutating that built-in snapshot by injecting ephemeral Almanac context through Hermes's plugin hook system on future turns

So if the user asks why the newest managed stub text is not visible in the built-in memory block of an already-active chat, do not misdiagnose the Almanac rail as broken.

The right interpretation is usually:

- disk refresh succeeded
- built-in `MEMORY.md` remains a session snapshot
- the plugin-injected Almanac context is the warm path for future turns without touching Hermes core
- restart or `/reset` is only a fallback if the plugin is not loaded yet or the issue is in Hermes plugin discovery itself

## Preferred non-invasive warm-reload design

If the user specifically wants warm reload without editing Hermes core, prefer this design:

1. Almanac publishes a stable `managed_memory_revision` with the canonical payload
2. `user-agent-refresh.sh` writes the local stubs and records the applied revision under the user's `HERMES_HOME/state`
3. the shipped `almanac-managed-context` plugin reads that local state on `pre_llm_call`
4. the plugin injects compact refreshed Almanac context into the current user turn when:
   - the session is new,
   - the managed revision changed,
   - or the user asks an Almanac-relevant question

Important details:

- the revision should be content-based, not `updated_at`
- use the canonical managed entry content as the source for the revision
- treat the activation-trigger file as a wake signal, not the source of truth
- use the local structured reconciler state under `HERMES_HOME/state`, not raw `MEMORY.md`, as the plugin's source
- keep the plugin context compact so it is cheaper than reloading the built-in system prompt on every turn

This preserves prompt-cache stability better than mutating built-in memory, because the plugin context is injected into the current user turn rather than the frozen system prompt.

## Scope decision

With the shipped plugin path, Almanac does not need Hermes core edits to achieve practical next-turn warm reload.

So when investigating this class of issue:

- repair Almanac first if the payload, trigger, timer, local state file, or local stub writes are wrong
- verify the plugin is installed under `HERMES_HOME/plugins/almanac-managed-context`
- verify the plugin's local state source under `HERMES_HOME/state/almanac-vault-reconciler.json`
- only consider Hermes core changes if the user explicitly wants built-in `MEMORY.md` hot-reload semantics instead of the non-invasive plugin path
- keep gateway restart as the fallback, not the first resort

## Guardrails

- prefer qmd through MCP over direct filesystem reads when it is available
- for user-agent runs on a shared host, do not inspect central deployment secrets such as `almanac.env` or source `bin/common.sh`
- do not browse other users' home directories
- do not rely on vague reassurance; point to the actual state files and rails
- do not store note bodies or PDF bodies in built-in memory
- do not patch Hermes code for this unless the task is explicitly about adding warm-reload support after verifying the Almanac rail is already correct
