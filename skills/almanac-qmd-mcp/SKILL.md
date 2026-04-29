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

- `$HERMES_HOME/state/almanac-vault-reconciler.json` for safe, agent-local plugin-managed Almanac routing state
- `$HERMES_HOME/state/almanac-recent-events.json` for recent Curator/SSOT nudges that may explain why the current session should restub or re-query qmd
- `~/Almanac` for the shared vault as the current user sees it in shell and VS Code
- `docs/hermes-qmd-config.yaml` for the default MCP client snippet
- `bin/qmd-daemon.sh` for how the qmd MCP server is started
- `bin/qmd-refresh.sh` for index refresh and embeddings
- `bin/health.sh` for the expected service and port state
- the installed local skill copies under `$HERMES_HOME/skills` when Hermes needs the shared skill text, not central secrets or private config

Typical deployed paths:

- user-visible vault root: `~/Almanac`
- public repo: the shared service deployment root from `ALMANAC_SHARED_REPO_DIR`
- local MCP endpoint: `http://127.0.0.1:8181/mcp`
- tailnet MCP endpoint: `https://<almanac-node>.<tailnet>/mcp`
- default qmd index name: `almanac`
- default qmd collection name: `vault`

On a shared-host user agent, the service-user deployment root is read-only shared infrastructure, not another enrolled user's workspace. Use `~/Almanac` when referring to vault files.

Do not read central deployment secrets such as `almanac.env`, `.almanac-operator.env`, or source `bin/common.sh` from a user-agent session.

## Answering vault-backed questions

When the user asks a question that could plausibly be answered by shared private documents, team notes, uploaded PDFs, internal terminology, company-specific plans, codenames, or a follow-up grounded in the current discussion, query qmd before you search the public web or answer from general model memory.

When Almanac MCP is available and the source is unclear, prefer `knowledge.search-and-fetch` first. It searches vault/PDF and shared Notion together, returns source-tagged buckets, and prevents wrong-lane misses. When the user clearly asks for vault/PDF/file knowledge, prefer `vault.search-and-fetch`. It wraps qmd search plus fetch and returns the fetched body as plain structured text, including `vault-pdf-ingest` by default. Results include `source_metadata` so you can tell whether a hit came from a normal vault file, a generated PDF sidecar, or a cloned Git repo with branch/commit/remote provenance. Keep it fast: do not request reranking, large result sets, or multiple fetched bodies unless the user explicitly asks for a broad literature review. Use raw qmd MCP (`query`, `get`, `multi_get`) for debugging, advanced retrieval control, or when the Almanac MCP bridge itself is unavailable.

## Fast path on a deployed Almanac host

If the agent is already running on the Almanac host and the task is topic lookup rather than Almanac debugging, do this exact sequence:

1. read the current user's local Almanac routing state first:
   - `$HERMES_HOME/state/almanac-vault-reconciler.json`
   - `$HERMES_HOME/state/almanac-recent-events.json` when recent drift or fresh uploads may matter
2. call Almanac MCP `knowledge.search-and-fetch` when the source is unclear, or `vault.search-and-fetch` when the user clearly asks for files/PDFs/vault content
3. if that brokered tool returns a stale MCP transport error such as `missing or invalid mcp-session-id`, retry the same brokered Almanac MCP tool once
4. if the retry still fails, stop and report that the Almanac knowledge rail needs operator repair; do not switch to raw `curl`/qmd protocol debugging in a normal user chat
5. only if the user is explicitly debugging Almanac itself, use `[managed:qmd-ref]` or the default local raw qmd rail `http://127.0.0.1:8181/mcp`
6. only if the qmd path itself fails, inspect `docs/hermes-qmd-config.yaml`
7. only if qmd still looks broken, inspect daemon/health files such as `bin/qmd-daemon.sh`, `bin/qmd-refresh.sh`, or `bin/health.sh`

Do not start with repo-wide searches for the topic, for `qmd`, for `/mcp`, or for generic deployment clues when the question is just asking for vault-backed knowledge.

Subscriptions do not gate qmd retrieval. They only affect ambient-awareness stubs and Curator push behavior.

## Vault layout and freshness

Do not assume the vault follows a fixed `Projects/`, `Research/`, or `Repos/`
taxonomy. Those are seeded conventions only. The `vault` qmd collection is
rooted at the shared vault root and indexes text-like files anywhere underneath
it. Plain folders without `.vault` metadata are searchable through qmd; `.vault`
only defines subscription and notification lanes.

When users move or rename vault content, treat qmd source paths as mutable.
An old exact file path or qmd URI can go stale, but the index self-heals after
`vault-watch` or the scheduled qmd refresh runs. Search by content/title again
instead of insisting on the old path. PDFs follow the same model through
`vault-pdf-ingest`: the source PDF stays in the vault, while generated markdown
sidecars are cleaned up and recreated by the ingest rail.

Cloned Git repositories are discovered anywhere under the vault as real `.git`
checkouts with an `origin` remote. `Repos/` is a default library convention, not
the only place repo sync looks.

So:

1. use qmd for deep retrieval
2. use `almanac-vaults` for subscription / catalog work
3. use `almanac-vault-reconciler` when the stub layer or sync rail is in doubt

For a simple knowledge question like "what is Example Lattice?" on a deployed host, the first retrieval call should usually be `knowledge.search-and-fetch`, not a raw file search. If the user says "in the vault" or "in the PDF", narrow to `vault.search-and-fetch`.

## Minimal working qmd MCP recipe

The local qmd server speaks MCP over JSON-RPC 2.0. Prefer Almanac MCP `vault.search-and-fetch` for ordinary agent answers; raw qmd is an operator/debugging fallback, not the normal chat path. If you need to call raw qmd directly, use this sequence instead of guessing the protocol:

1. initialize the session
2. capture the `mcp-session-id` response header from `initialize`
3. send `notifications/initialized` with that same `mcp-session-id`
4. optionally call `tools/list` with that same `mcp-session-id` to confirm the live tool surface
5. call the `query` tool with that same `mcp-session-id` for retrieval

Live qmd servers on this host expose at least these tool names:

- `query`
- `get`
- `multi_get`
- `status`

Minimum working retrieval example:

```http
POST http://127.0.0.1:8181/mcp
Content-Type: application/json
Accept: application/json, text/event-stream

{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"almanac-probe","version":"1.0"}}}
```

Capture the `mcp-session-id` response header from that `initialize` reply and send it on every later request:

```json
{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}
```

```json
{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
```

```json
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"query","arguments":{"searches":[{"type":"lex","query":"Example Lattice"}],"collections":["vault"],"intent":"Identify what Example Lattice refers to in Almanac","rerank":false,"limit":5}}}
```

Expected response shape:

```json
{"result":{"content":[{"type":"text","text":"..."}],"structuredContent":{"results":[...]}}}
```

This is the minimal transport example, not the only good search shape. qmd's own live instructions say to always provide `intent`, and for normal knowledge lookups the best results often come from combining `lex` and `vec` searches in the same call. Use `collections: ["vault", "vault-pdf-ingest"]` when PDF-derived markdown may matter. The required query arguments are:

- `searches`: one or more search objects such as `{"type":"lex","query":"Example Lattice"}`
- optional `collections`
- optional `intent`
- optional `limit`
- optional `rerank`
- optional `candidateLimit`
- optional `minScore`

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
- do not search the repo just to rediscover the qmd rail when `[managed:qmd-ref]`, `docs/hermes-qmd-config.yaml`, or the local default endpoint already give you the route
