---
name: almanac-ssot
description: Use to connect an enrolled user agent to a shared Notion SSOT workspace with read, insert, page/database creation, and update rails while refusing archive/delete by default.
---

# Almanac SSOT

Use this skill when the task is about the shared organizational source of truth
that Almanac agents converge around.

The SSOT in Almanac is a shared Notion workspace. Curator and the enrolled
user agents operate from one common deployment, but each user agent still acts
on behalf of one user. Use this skill to stay aware of the organization,
current work, and user-scoped responsibilities without treating the SSOT as a
free-for-all edit surface.

## Hermes Recipe Card

Preferred agent path: call the `almanac-mcp` MCP tools directly. Do not inspect
repo Python source, run `python3 - <<'PY'` heredocs, or use internal functions
to enqueue writes from a normal Hermes turn.

The `almanac-managed-context` plugin injects local auth into Almanac MCP calls
before dispatch. Leave `token` out of normal Hermes tool calls.

Common calls:

```json
{"tool":"ssot.read","arguments":{"target_id":"<optional-page-or-database-id-or-url>","query":{},"include_markdown":false}}
{"tool":"ssot.write","arguments":{"operation":"insert","payload":{"title":"Daily note","properties":{"Owner":{"people":[{"id":"<verified-caller-notion-user-id>"}]}},"children":[{"type":"paragraph","paragraph":{"rich_text":[{"type":"text","text":{"content":"Live note body."}}]}}]}}}
{"tool":"ssot.write","arguments":{"operation":"create_page","payload":{"title":"Project Notes","children":[{"type":"bulleted_list_item","bulleted_list_item":{"rich_text":[{"type":"text","text":{"content":"First shared note."}}]}}]}}}
{"tool":"ssot.write","arguments":{"operation":"create_database","payload":{"title":"Org To-Dos","properties":{"Task":{"title":{}},"Status":{"select":{"options":[{"name":"Not started"},{"name":"In progress"},{"name":"Done"}]}},"Assignee":{"people":{}},"Priority":{"select":{"options":[{"name":"High"},{"name":"Medium"},{"name":"Low"}]}}}}}}
{"tool":"ssot.write","arguments":{"operation":"append","target_id":"<page-id-or-url>","payload":{"children":[{"type":"paragraph","paragraph":{"rich_text":[{"type":"text","text":{"content":"Awesome alternatives include marshmallows and roasted chestnuts."}}]}}]}}}
{"tool":"ssot.write","arguments":{"operation":"update","target_id":"<page-id-or-url>","payload":{"properties":{"Status":{"status":{"name":"In Progress"}}}}}}
{"tool":"ssot.pending","arguments":{"status":"pending","limit":10}}
{"tool":"ssot.status","arguments":{"pending_id":"ssotw_..."}}
```

Decision tree:

- For live scoped organizational state, call `ssot.read` once before answering.
- For shared pages, lists, task tables, or org-wide databases, call
  `ssot.write` with `operation:"create_page"` or
  `operation:"create_database"` so Almanac creates it under the shared root
  page and it inherits org access. Do not use a personal/user Notion MCP for
  shared SSOT creation; user-OAuth workspace-level creation can land in that
  user's Private section.
- For short append/update/insert work, call `ssot.write` once; never archive or delete.
- For long new pages, create the page first with a compact title/intro/source
  block, then append the body in small chunks of roughly 10-20 Notion blocks.
  Never send more than 100 child blocks in one call, and do not keep retrying
  one huge insert if it times out.
- For `insert`, assign the verified caller in any people-typed column the
  database exposes (`Owner`, `Assignee`, `DRI`, `Lead`, `Reviewer`, or
  whatever the workspace named it). Property names are treated as opaque
  ownership channels: assigning a different user in any of them triggers
  the broker's approval requirement.
- Set `read_after:true` only when the user asks you to verify the live state
  immediately after an applied write.
- If `ssot.write` returns `final_state:"applied"` or `applied:true`, tell the
  user it was written, summarize the target, and surface `page_url` / `url`
  when the response includes it.
- If it returns `final_state:"queued"`, `queued:true`, or `approval_required:true`,
  report the `pending_id`, owner/scope reason, and that approval is required.
- For “did it land?” follow-ups, call `ssot.status` with the `pending_id` when
  known; otherwise call `ssot.pending` with status `applied`, `pending`,
  `denied`, or `expired` as needed.

## Default Rails

- allow read / insert / create_page / create_database / update
- do not archive
- do not delete
- shared reads are filtered to records where the verified caller appears in
  any people-typed column on the database (regardless of column name)
- shared writes require a verified Notion identity before they can apply
- shared page and database creation is parented under the configured shared
  root page or an explicit target page; payload-level parents are rejected to
  avoid private workspace-level creations
- shared page and append payloads are bounded to Notion's 100 child-block
  request limit and reject malformed block objects before hitting the API
- when the shared database exposes `Changed By`, Almanac stamps the verified
  human there automatically on every shared write (`Changed By` is provenance
  only, never an ownership channel)
- Curator's self-serve verification claims live in a shared workspace database,
  so treat the claim metadata there as operator-visible workspace scaffolding,
  not as a secret channel
- if ownership is unclear, require approval before writing
- treat SSOT awareness as on-by-default for enrolled user agents
- prefer converging on current organizational state over inventing local shadow state

## Ownership Resolution

1. the first people-typed column on the page that lists a principal — opaque
   to the column name (`Owner`, `Assignee`, `DRI`, `Lead`, `Reviewer`, etc.);
   the `Changed By` provenance column is excluded
2. `created_by`
3. for plain pages, the user's own last human edit or this same agent's prior brokered write history
4. otherwise ask for approval

## Orientation

- you are operating inside a Curator-managed Almanac deployment shared by the organization
- the user attached to this agent is your primary working principal
- use SSOT to understand what is happening across the organization, then help your user orient, plan, and act inside that context
- do not assume you should write everywhere just because you can read broadly
- when SSOT and vault material overlap, use SSOT for live organizational state and qmd/vault retrieval for deeper background context

## Refresh Model

- Curator pushes a shared Notion digest into plugin-managed context on the normal
  fanout cycle
- prefer webhook-driven refreshes when the operator has configured and verified the public Notion webhook
- with the verified webhook live, treat shared Notion changes as minutes-scale after Almanac batches and de-duplicates the event
- without the verified webhook, tolerate delayed updates by using the 1-hour Curator full-sweep fallback (configurable via ALMANAC_NOTION_INDEX_FULL_SWEEP_INTERVAL_SECONDS)
- expect Almanac to batch and de-duplicate webhook-driven refresh work
- treat plugin-managed SSOT summaries as ambient orientation and `ssot.read`
  as the depth rail when the user needs specifics

## Guardrails

- use the brokered `ssot.read` rail for shared Notion lookups rather than
  trying to reach the shared workspace directly
- treat `ssot.read` as the governed shared-SSOT lane, not as a broad
  full-workspace documentation search tool
- if the user explicitly wants wide retrieval across a separately connected
  personal Notion workspace and that MCP lane is live, hand that work to
  `almanac-notion-mcp`; do not present that lane as the default shared Almanac
  workspace-search path
- when the task maps to a structured column on the database (any people-typed
  ownership column by any name, status/state/priority, due/last-edited dates,
  or any other filterable field), prefer scoped structured reads over
  page-by-page exploration
- if an answer needs both the shared SSOT and the user's own Notion MCP lane,
  name both sources instead of collapsing them together silently
- write only on behalf of the user who owns the agent
- do not silently cross-edit records owned by another user
- do not fall back to "please touch the page again" when the page is already in the user's edit lane or this agent has already written there through the broker
- prefer append-only page notes when the user wants to add context to a shared
  page without taking ownership of existing text
- do not claim that native Notion history will show the human directly; it
  shows the Almanac integration while the row-level attribution lives in
  `Changed By` plus Almanac's local audit
- do not inspect other users' home directories or central deployment config to
  infer ownership; use the SSOT metadata and Almanac rails already exposed to
  this agent
- if a requested action would archive or delete content, stop and ask first
- if the requested change appears to touch another user's records, ask for approval instead of guessing; Almanac can now queue that approval instead of dropping the request
