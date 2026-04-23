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

Read the bootstrap token from `HERMES_HOME/secrets/almanac-bootstrap-token`;
never paste it into chat.

Common calls:

```json
{"tool":"notion.search","arguments":{"token":"<bootstrap token>","query":"Chutes Unicorn","limit":5,"rerank":false}}
{"tool":"notion.fetch","arguments":{"token":"<bootstrap token>","target_id":"<page-or-database-id-or-url>"}}
{"tool":"notion.query","arguments":{"token":"<bootstrap token>","target_id":"<database-or-data-source-id-or-url>","query":{"filter":{"property":"Status","status":{"equals":"In Progress"}}},"limit":25}}
{"tool":"notion.search-and-fetch","arguments":{"token":"<bootstrap token>","query":"Chutes Unicorn","search_limit":5,"fetch_limit":2,"body_char_limit":4000,"rerank":false}}
```

Call budget:

- If the user asks a simple knowledge question by title or phrase, use
  `notion.search-and-fetch` once and answer from the fetched body.
- If the user gives an exact page/database URL or id, skip search and call
  `notion.fetch` once.
- If the user asks for assignments, status, due dates, or rows in a shared
  database, call `notion.query` once.
- Only fall back to separate `notion.search` then up to 3 `notion.fetch` calls
  when you need more control than `notion.search-and-fetch` provides.

## Default Split

- `search` for broad knowledge discovery over indexed shared Notion content, including extractable Notion-hosted PDF/text attachments on indexed pages
- `fetch` for the live body of one exact page or the live schema of one exact database/data source
- `query` for live structured state in a shared Notion database or data source

Use that split literally:

- knowledge question -> `search`
- "read this exact page" -> `fetch`
- "what is assigned / due / in progress" -> `query`
- a page `fetch` also returns live attachment refs for files currently attached there

This split exists because search is qmd-backed, while `fetch` and `query` are
live Notion reads.

## Budget

- start with one `search`
- fetch at most 3 exact pages before summarizing
- do not fetch every search hit
- if the user gives an exact URL or page id, skip search and `fetch` directly

## Staleness Model

- `search` is qmd-backed and near-real-time only when public Notion webhook ingress is configured and verified
- with the verified webhook live, edits normally reach indexed search on the minutes-scale after Almanac batches and de-duplicates the event
- without the verified webhook, `search` relies on the 4-hour Curator full sweep and may be up to four hours behind live Notion edits
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
script reads the bootstrap token from `HERMES_HOME`:

```bash
scripts/curate-notion.sh search "Chutes Unicorn"
scripts/curate-notion.sh search --rerank "Chutes Unicorn"
scripts/curate-notion.sh fetch "https://www.notion.so/...page-id..."
scripts/curate-notion.sh query "<database-or-data-source-id-or-url>" '{"filter":{"property":"Status","status":{"equals":"In Progress"}}}'
```

Add `--json` for raw structured output. Add `--rerank` to `search` when quality matters more than latency.

## Result Interpretation

- zero `search` hits can mean no indexed match or that backfill has not caught up yet
- a direct `fetch` can still succeed when `search` is thin
- `query` results are live and may differ from indexed search results on very recent changes
