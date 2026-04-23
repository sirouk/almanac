---
name: almanac-ssot
description: Use to connect an enrolled user agent to a shared Notion SSOT workspace with read, insert, and update rails while refusing archive/delete by default.
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
{"tool":"ssot.write","arguments":{"operation":"append","target_id":"<page-id-or-url>","payload":{"children":[{"type":"paragraph","paragraph":{"rich_text":[{"type":"text","text":{"content":"Awesome alternatives include marshmallows and roasted chestnuts."}}]}}]}}}
{"tool":"ssot.write","arguments":{"operation":"update","target_id":"<page-id-or-url>","payload":{"properties":{"Status":{"status":{"name":"In Progress"}}}}}}
{"tool":"ssot.pending","arguments":{"status":"pending","limit":10}}
{"tool":"ssot.status","arguments":{"pending_id":"ssotw_..."}}
```

Decision tree:

- For live scoped organizational state, call `ssot.read` once before answering.
- For append/update/insert, call `ssot.write` once; never archive or delete.
- Set `read_after:true` only when the user asks you to verify the live state
  immediately after an applied write.
- If `ssot.write` returns `final_state:"applied"` or `applied:true`, tell the
  user it was written and summarize the target.
- If it returns `final_state:"queued"`, `queued:true`, or `approval_required:true`,
  report the `pending_id`, owner/scope reason, and that approval is required.
- For “did it land?” follow-ups, call `ssot.status` with the `pending_id` when
  known; otherwise call `ssot.pending` with status `applied`, `pending`,
  `denied`, or `expired` as needed.

## Default Rails

- allow read / insert / update
- do not archive
- do not delete
- shared reads are filtered to the current user's owned / assigned records
- shared writes require a verified Notion identity before they can apply
- when the shared database exposes `Changed By`, Almanac stamps the verified
  human there automatically on every shared write
- Curator's self-serve verification claims live in a shared workspace database,
  so treat the claim metadata there as operator-visible workspace scaffolding,
  not as a secret channel
- if ownership is unclear, require approval before writing
- treat SSOT awareness as on-by-default for enrolled user agents
- prefer converging on current organizational state over inventing local shadow state

## Ownership Resolution

1. explicit `Owner` or `Assignee`
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

- Curator pushes a shared Notion digest into managed memory on the normal
  fanout cycle
- prefer webhook-driven refreshes when the operator has configured and verified the public Notion webhook
- with the verified webhook live, treat shared Notion changes as minutes-scale after Almanac batches and de-duplicates the event
- without the verified webhook, tolerate delayed updates by using the 4-hour Curator full-sweep fallback
- expect Almanac to batch and de-duplicate webhook-driven refresh work
- treat managed-memory SSOT summaries as ambient orientation and `ssot.read`
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
- when the task is structured shared organizational state with filters such as
  owner, status, due date, or assignee, prefer scoped structured reads over
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
