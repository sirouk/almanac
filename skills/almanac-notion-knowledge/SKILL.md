---
name: almanac-notion-knowledge
description: Use for shared Almanac Notion knowledge retrieval through the default shared notion.search / notion.fetch / notion.query rail.
---

# Almanac Notion Knowledge

Use this skill for the shared Almanac Notion knowledge rail that every
enrolled agent can use.

This is not the governed `ssot.read` / `ssot.write` lane and it is not the
optional user-owned Notion MCP lane.

## Hermes Recipe Card

Preferred agent path: call the `almanac-mcp` MCP tools directly. Do not use
`scripts/curate-notion.sh` from a Hermes turn unless MCP transport itself is
broken and you are debugging the harness.

The `almanac-managed-context` plugin injects local auth into Almanac MCP calls
before dispatch. Leave `token` out of normal Hermes tool calls.

Common calls:

```json
{"tool":"knowledge.search-and-fetch","arguments":{"query":"Example Unicorn","search_limit":5,"vault_fetch_limit":1,"notion_fetch_limit":2,"body_char_limit":6000}}
{"tool":"notion.search","arguments":{"query":"Example Unicorn","limit":5,"rerank":false}}
{"tool":"notion.fetch","arguments":{"target_id":"<page-or-database-id-or-url>"}}
{"tool":"notion.query","arguments":{"target_id":"<database-or-data-source-id-or-url>","query":{"filter":{"property":"Status","status":{"equals":"In Progress"}}},"limit":25}}
{"tool":"notion.search-and-fetch","arguments":{"query":"Example Unicorn","search_limit":5,"fetch_limit":2,"body_char_limit":4000,"rerank":false}}
```

Call budget:

- If the user asks a simple knowledge question by title or phrase and did not
  clearly say it lives in Notion, use `knowledge.search-and-fetch` once so vault
  files/PDFs and shared Notion are checked together.
- If the user clearly says the answer is in shared Notion, use
  `notion.search-and-fetch` once and answer from the fetched body.
- If the user gives an exact page/database URL or id, skip search and call
  `notion.fetch` once.
- If the user asks what's on their plate, what to focus on today, or what is
  assigned to them, start from `[managed:today-plate]` when it is injected. If
  that snapshot is missing or thin, make one bounded `knowledge.search-and-fetch`
  or `notion.search-and-fetch` call against the user's own phrasing before
  trying live database queries.
- If the user gives an exact database/data-source target, or explicitly asks
  for a live refresh of a structured database view, call `notion.query` once.
  Do not fan out `notion.query` across discovered databases in a chat turn.
- Only fall back to separate `notion.search` then up to 3 `notion.fetch` calls
  when you need more control than `notion.search-and-fetch` provides.

## Default Split

- `search` for broad knowledge discovery over indexed shared Notion content, including extractable Notion-hosted PDF/text attachments on indexed pages
- `fetch` for the live body of one exact page or the live schema of one exact database/data source
- `query` for live structured state in a shared Notion database or data source
- `knowledge.search-and-fetch` for source-agnostic discovery across both vault/PDF and shared Notion when the user does not name the source

Use that split literally:

- knowledge question -> `search`
- "read this exact page" -> `fetch`
- "what's on my plate / what should I focus on today" -> managed
  `[today-plate]`, then one qmd-backed `knowledge.search-and-fetch` if needed
- "query this database for due / in progress rows" -> one targeted `query`
- a page `fetch` also returns live attachment refs for files currently attached there

This split exists because search is qmd-backed, while `fetch` and `query` are
live Notion reads.

## Budget

- start with one `search`
- fetch at most 3 exact pages before summarizing
- run at most 1 live `query` unless the user gave multiple exact database
  targets
- do not fetch every search hit
- if the user gives an exact URL or page id, skip search and `fetch` directly

## Staleness Model

- `search` is qmd-backed and near-real-time only when public Notion webhook ingress is configured and verified
- with the verified webhook live, edits normally reach indexed search within seconds after Almanac batches and de-duplicates the event (sub-second debounced kick + 1 minute timer fallback)
- without the verified webhook, `search` relies on the 1-hour Curator full sweep (configurable via ALMANAC_NOTION_INDEX_FULL_SWEEP_INTERVAL_SECONDS) and may be up to that interval behind live Notion edits
- `fetch` and `query` are live Notion reads
- if a user says they just changed a page, prefer `fetch`
- if a user asks about newly attached files, prefer `fetch` first for live attachment refs; indexed search covers extractable Notion-hosted PDFs and text-like attachments after the webhook or sweep reindexes the page

## Guardrails

- for shared organizational writes or approvals, switch to `almanac-ssot`
- do not treat `query` as semantic search
- do not treat `search` metadata alone as enough when the page body matters
- anything under the configured shared Notion index roots is shared-agent readable;
  do not assume private per-user filtering on this rail
- do not use the optional personal Notion MCP lane unless the user explicitly wants their separate personal workspace

## Human CLI Fallback

These wrappers are for humans and operator debugging, not the preferred Hermes
agent path. They exist so a shell user can exercise the same MCP rail while the
wrapper resolves local auth from the installed Hermes home:

```bash
scripts/curate-notion.sh search "Example Unicorn"
scripts/curate-notion.sh search --rerank "Example Unicorn"
scripts/curate-notion.sh fetch "https://www.notion.so/...page-id..."
scripts/curate-notion.sh query "<database-or-data-source-id-or-url>" '{"filter":{"property":"Status","status":{"equals":"In Progress"}}}'
```

Add `--json` for raw structured output. Add `--rerank` to `search` when quality matters more than latency.

## Result Interpretation

- zero `search` hits can mean no indexed match or that backfill has not caught up yet
- a direct `fetch` can still succeed when `search` is thin
- `query` results are live and may differ from indexed search results on very recent changes
