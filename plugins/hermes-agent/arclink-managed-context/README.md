# arclink-managed-context

Hermes plugin shipped by ArcLink.

Purpose:
- read the locally applied ArcLink plugin-managed state from `HERMES_HOME/state/arclink-vault-reconciler.json`
- inject compact refreshed context into relevant future turns via the `pre_llm_call` hook
- inject a compact `[local:model-runtime]` section based on Hermes's actual current-turn model argument, so stale session prompts or config defaults do not win after setup/model switches
- surface `[managed:vault-landmarks]` as a compact top-level vault map, including plain qmd-indexed folders that are not `.vault` subscription lanes
- surface `[managed:recall-stubs]` as compact retrieval-lane awareness cards without treating those cards as answer evidence
- surface `[managed:notion-landmarks]` as a compact local-index map of shared Notion areas without treating it as live structured state
- surface `[managed:today-plate]` as the compact owned/assigned work snapshot without forcing a live Notion read
- avoid mutating Hermes core or depending on live built-in `MEMORY.md` prompt rebuilds

Design notes:
- uses only stdlib
- does not persist anything to session DB
- keeps context ephemeral and attached to the current user turn
- injects on first turn, on revision change, and on ArcLink-relevant prompts
- injects on model-runtime changes and once when a gateway restart resumes an already-active session
- injects compact per-turn tool recipes for clear SSOT/Notion actions instead of asking the agent to read repo Python
- honors `ARCLINK_MANAGED_CONTEXT_RECALL_BUDGET=low|mid|high`; `low` trims recall-heavy sections but keeps qmd/Notion routing and recall-stub safety guardrails
- writes JSONL injection telemetry under `HERMES_HOME/state/arclink-context-telemetry.jsonl`; summarize it with `bin/arclink-context-telemetry`

Optional conversational-memory siblings:
- operators may install a separate Hermes conversational-memory plugin when
  they want chat-fact or preference recall; that plugin is a sibling, not a
  replacement for ArcLink managed context
- sibling memory plugins must stay inside the same enrolled user's Hermes home
  and must not read another user's vault, linked resources, session DB rows, or
  private state
- sibling memory plugins must not write shared Notion/SSOT state directly;
  shared changes still go through brokered `ssot.write`/ArcLink MCP rails and
  their approval, verification, and destructive-operation guards
- sibling memory plugins must not auto-capture every Hermes turn into ArcLink
  governed memory or managed recall stubs unless an operator-approved policy and
  isolation tests exist
- recall produced by a sibling plugin is only conversational context; vault,
  PDF, shared Notion, and SSOT answers still need retrieval through
  `knowledge.search-and-fetch`, `vault.search-and-fetch`,
  `notion.search-and-fetch`, `notion.fetch`, or `ssot.read`
