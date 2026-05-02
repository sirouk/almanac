---
name: arclink-notion-mcp
description: Optional personal/operator helper for cases where a user's own Notion workspace is already connected through the official Notion MCP; not part of ArcLink's default shared Notion contract.
---

# ArcLink Notion MCP

Use this skill only after the user-owned Notion MCP connection is already live.

This is optional personal/operator tooling. It is not the core ArcLink-wide
Notion retrieval path for every enrolled agent.

This skill is for the user's own Notion workspace reached through Notion's
hosted MCP, not the shared ArcLink SSOT and not the default shared ArcLink
workspace-search lane. Use it only for a separately connected user-owned
workspace with its own access model.

## Preconditions

- if the Notion MCP is not connected yet, use `arclink-ssot-connect` first
- if the task is about the shared organizational Notion space, use
  `arclink-ssot` instead
- shared organizational writes and attribution do not go through this lane;
  they stay on ArcLink's centralized brokered rail

## Official References

- Notion MCP quickstart:
  `https://developers.notion.com/docs/get-started-with-mcp`
- Hosted Notion MCP endpoint:
  `https://mcp.notion.com/mcp`

## Working Style

- verify the Notion MCP is reachable before leaning on it
- prefer search-first, fetch-second retrieval for workspace documentation
- prefer narrow reads first: search by exact title or codename, then inspect
  one target page or database
- when writing, keep the scope tight and match the user's requested surface
- confirm before archive, delete, or broad multi-page edits

## Tool Naming

The official hosted Notion MCP exposes `notion-search` and `notion-fetch`.

In OpenAI MCP clients, those may appear as:

- `search`
- `fetch`

Treat those as the same search/fetch pair. Use the names your current client
actually exposes.

## Lane Routing

Use this routing rule consistently:

1. use the user-owned Notion MCP only for that separately connected personal
   workspace: broad documentation discovery, current activity pages, meeting
   notes, working docs, and user-generated workspace content inside that lane
2. use `arclink-ssot` / `ssot.read` when the task is governed shared
   organizational state such as owner-scoped rows, brokered updates, approvals,
   or the operator-managed SSOT database and pages
3. if the question spans both lanes, search/fetch the user-owned Notion lane
   first for discovery, then use `ssot.read` only for the governed slice and
   say clearly that the answer combines both surfaces

## Retrieval Strategy

For documentation and knowledge work, use this default loop:

1. search for candidate pages or databases
2. skim the hit list first
3. fetch only the best 1-3 candidates
4. answer from the fetched content, not from titles alone

Search is the candidate-finding step. Fetch is the full-body or schema-reading
step. Do not fetch every search hit.

Per-turn budget unless the user explicitly asks for a wider sweep:

- at most 2 search calls before refining the query
- at most 3 fetches before summarizing or asking to go deeper
- prefer tightening the query over widening the fan-out

### Search First

Use search when you are trying to find where the knowledge lives.

Good first searches:

- exact page title
- codename, project name, or internal term
- short natural-language concept query when the exact title is unknown
- people, meeting, or team names plus a recency hint when looking for current
  activity or user-generated content

Prefer one focused search over many parallel broad searches. If the first query
is weak, tighten it before spraying more searches.

### Fetch Second

Use fetch when you already have a promising page, database, or data source URL
or ID and need the actual content.

- fetch pages to read the body
- fetch databases to inspect their structure and embedded data sources
- if the database response exposes `collection://...` data source URLs, fetch
  the relevant data source for schema-level detail

Do not answer substantive questions from search metadata alone when a fetch is
cheap and the page body matters.

## Access and Freshness Failure Modes

Interpret thin or zero results carefully.

- thin or zero search results may mean the current user does not have access to
  the page, not that the content does not exist
- very recent edits or newly created pages may not surface immediately in search
- if the user provides an exact URL or ID, fetch directly instead of assuming
  the search index is current

When results are unexpectedly thin, say so plainly:

- "I may not have access to that page in your Notion workspace."
- "This may be too recent to be searchable yet; if you have the URL, I can
  fetch it directly."

## Fast Paths

For a question like "what is Example Unicorn?":

1. search for `Example Unicorn`
2. fetch the top page hit
3. only widen the search if the fetched page is clearly wrong

For a request like "find the docs about release cutover":

1. search once with the phrase
2. fetch the top 2-3 relevant hits
3. summarize across those fetched pages

For structured database work:

1. fetch the database first to understand what it is
2. if your client exposes richer database query tools, use them after you know
   which database or data source you are targeting
3. otherwise keep the workflow page-oriented and fetch only the specific rows
   or pages you need

## Rate and Scope Discipline

- Notion MCP has tighter limits on search than on fetch; avoid shotgun search
  loops or large parallel batches
- search is for discovery, fetch is for reading
- if you already know the exact page URL or ID, skip search and fetch directly
- if the user wants broad workspace documentation retrieval, this lane is the
  right tool
- if the task is the shared organizational SSOT with brokered ownership and
  approvals, this is the wrong lane
- do not treat a successful connection check as proof that retrieval quality,
  freshness, or ranking are perfect

## ArcLink-Specific Rails

- treat the user-owned Notion MCP and the shared ArcLink SSOT as separate lanes
- if the task mixes both, name which one you are reading from or writing to
- use qmd / ArcLink vault retrieval for shared private vault context
- use the user-owned Notion MCP for that user's personal or workspace-specific
  Notion tasks
- use the shared SSOT broker for governed organizational state, not for broad
  full-workspace documentation discovery

## Guardrails

- do not ask the user to reveal secrets that the MCP/OAuth flow can handle
- do not silently copy organizational SSOT data into a private Notion space
- do not assume every Notion page is writable just because the MCP is connected
- do not fetch every search hit when titles already show obvious irrelevance
- do not use the shared SSOT broker as a substitute for full-workspace Notion
  search
- do not conclude "no such page" when the more honest answer is "I may not have
  access" or "the index may not have caught up yet"
- if the Notion MCP response conflicts with ArcLink SSOT context, surface the
  distinction instead of guessing
