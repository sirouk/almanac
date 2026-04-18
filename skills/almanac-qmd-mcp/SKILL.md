---
name: almanac-qmd-mcp
description: Use when an agent needs to connect to an Almanac qmd index, configure or verify the local qmd MCP endpoint, or answer private/shared-vault questions by querying qmd on a host that runs Almanac.
---

# Almanac qmd MCP

Use this skill when the user wants an agent to work with the Almanac vault through qmd, either by:

- connecting to the local qmd MCP HTTP endpoint
- connecting to the tailnet-exposed qmd MCP endpoint from another machine
- configuring an MCP client such as Hermes
- answering questions that may depend on shared private vault knowledge
- verifying that qmd indexing or the MCP daemon is healthy
- falling back to direct `qmd` CLI access when MCP integration is not the best fit
- handing another agent a stable path for ongoing vault-memory reconciliation

## What to look for

Check these local files first:

- `$HERMES_HOME/state/almanac-vault-reconciler.json` and `$HERMES_HOME/memories/almanac-managed-stubs.md` for safe, agent-local Almanac routing state
- `$HERMES_HOME/state/almanac-recent-events.json` for recent Curator/SSOT nudges that may explain why the current session should restub or re-query qmd
- `docs/hermes-qmd-config.yaml` for the default MCP client snippet
- `bin/qmd-daemon.sh` for how the qmd MCP server is started
- `bin/qmd-refresh.sh` for index refresh and embeddings
- `bin/health.sh` for the expected service and port state
- `/home/almanac/almanac/skills/almanac-qmd-mcp` and `/home/almanac/almanac/skills/almanac-vault-reconciler` when Hermes is running on the same host as the deployed Almanac instance and needs the shared skill text, not central secrets or private config

Typical deployed paths:

- public repo: `/home/almanac/almanac`
- private repo: `/home/almanac/almanac/almanac-priv`
- local MCP endpoint: `http://127.0.0.1:8181/mcp`
- tailnet MCP endpoint: `https://<almanac-node>.<tailnet>/mcp`
- default qmd index name: `almanac`
- default qmd collection name: `vault`

On a shared-host user agent, `/home/almanac/almanac` is the service-user deployment root. Reading shared repo content there is expected. Treat it as read-only shared infrastructure, not as another enrolled user's workspace.

Do not read `/home/almanac/almanac/almanac-priv/config/almanac.env`, `.almanac-operator.env`, or source `bin/common.sh` from a user-agent session.

## Answering vault-backed questions

When the user asks a question that could plausibly be answered by shared private documents, team notes, uploaded PDFs, internal terminology, company-specific plans, codenames, or a follow-up grounded in the current discussion, query qmd before you search the public web or answer from general model memory.

Subscriptions do not gate qmd retrieval. They only affect ambient-awareness stubs and Curator push behavior.

So:

1. use qmd for deep retrieval
2. use `almanac-vaults` for subscription / catalog work
3. use `almanac-vault-reconciler` when the stub layer or sync rail is in doubt

## Pairing with the reconciler skill

If the user wants the agent to stay aligned with the vault over time, this skill should lead into `skills/almanac-vault-reconciler/SKILL.md`.

Expected handoff:

1. connect the agent to qmd over MCP
2. verify the MCP connection with the agent's MCP test path
3. run one vault-memory reconciliation immediately or confirm first-contact already did it
4. confirm one recurring 4-hour user refresh rail exists
5. confirm Curator-triggered fanout can signal the activation-trigger path when vault/catalog changes happen

## Guardrails

- treat the vault as the authoritative knowledge source and avoid writing to it unless the user explicitly asks
- prefer reading effective config over assuming defaults
- for a user-agent session on a shared host, never inspect central deployment secrets such as `almanac.env` or source `bin/common.sh`; use the already wired MCP endpoints and agent-local Almanac state instead
- do not hard-code Hermes-specific behavior when a generic MCP client path will do
- if both MCP and direct qmd CLI are viable, choose the lighter path for the user’s task
- prefer MCP and qmd over direct filesystem scraping when the vault is meant to stay read-oriented
- for private or shared-vault knowledge questions, prefer qmd before web search
- if qmd has relevant hits, do not ignore them and answer from the public web instead
