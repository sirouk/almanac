# ArcLink Notion Human Guide

ArcLink has more than one Notion lane. Use the lane that matches the work.

## Shared SSOT

Shared organization pages and databases should be created and edited through
the SSOT broker. The brokered tools are:

- `ssot.read` — caller-scoped read of the shared SSOT database (rows where the
  verified caller appears in any people-typed column).
- `ssot.preflight` — check whether a write would apply immediately, queue for
  user approval, or fail, before attempting it.
- `ssot.write` — apply an `insert`/`update`/`append`/`create_page`/
  `create_database` write through the broker.
- `ssot.pending` — list the caller's own queued or recently decided writes.
- `ssot.status` — check one previously queued write by `pending_id`.
- `ssot.approve` / `ssot.deny` — resolve one of the caller's own queued writes
  after the user explicitly approves or declines it in chat.

The broker keeps writes under the configured ArcLink shared/root parent and
rejects destructive archive/delete/trash style changes. Out-of-scope writes do
not fail silently: they queue for explicit user approval, and applied
`create_page`/`create_database` writes promote the new url/id back as a receipt.
Use this lane for team notes, operating profile content, shared databases, and
agent-visible source-of-truth pages.

The Notion API client is data-source-aware (Notion API version `2026-03-11`):
shared databases are queried through their first data source, with a legacy
`databases/{id}/query` fallback, and new databases are created with an
`initial_data_source`. Agents do not need to know this — it is handled inside
the broker — but it is why a shared database must live under a page (the
SSOT root) rather than at the workspace top level.

Live external Notion mutation is proof-gated (PG-NOTION). The no-secret proof
harness defaults to `proof_mode="fake"`; an operator must explicitly choose
`authorized_live` (with `allow_live_mutation`) before any write preflight
touches a real Notion workspace.

SSOT sharing uses shared-root membership as the canonical model. If a user or
agent should see shared SSOT content, add them to the Notion shared root or to
the workspace/teamspace that owns that root, then verify access through the
brokered setup/status rail. Drive linked-resource grants do not imply Notion or
SSOT share grants.

User-owned OAuth, private integration tokens, and email-share-only workflows are
non-default research/proof alternatives. Do not use them for organization pages
that must inherit ArcLink shared-root permissions.

## Indexed Notion Knowledge

Indexed shared Notion pages are synchronized into the `notion-shared` qmd
collection. The recommended first move for a broad question — one that could
live in vault files, ingested PDFs, cloned docs, or shared Notion pages — is the
unified, source-agnostic rail:

- `knowledge.search-and-fetch` — searches and fetches across both the vault/PDF
  and the shared Notion rails in one bounded call (`knowledge.search` is the
  discovery-only variant).

When the lane is already known, prefer the precise tools:

- `notion.search-and-fetch` — search the indexed Notion rail and fetch bounded
  live page bodies for the top matches.
- `notion.fetch` — fetch a live page/database/data-source body by exact id or
  URL.
- `notion.query` — run a live structured query against a specific shared
  database/data source.

Exact live reads are scoped to configured shared/indexed roots. If a page is
available to a Notion token but outside the ArcLink root/index scope, agent
tools should refuse it rather than treating broad integration access as
permission.

### How shared Notion stays current

The `notion-shared` index is kept fresh by an operator-managed rail on the host,
not by the agent. A Notion change propagates through:

```
Notion webhook -> ssot batcher (sub-second nudge + 1-minute timer) -> qmd reindex
```

The receiver (`/notion/webhook`, loopback only) verifies each signed event,
stores it, and kicks the batcher worker (`arclink-ssot-batcher.service`) on a
~1-second debounce in addition to the standing 1-minute timer. The batcher
re-fetches page markdown and updates the `notion-shared` qmd collection, so new
pages, database rows, edits, and deletions under the SSOT root reach the index
within seconds.

The webhook verification token is **operator-armed**, which matters on a shared
multi-user host. An operator must first arm an install window
(`arm_verification_token_install`); the first handshake then stores the
verification token only if armed and not already set, otherwise the receiver
returns 409 Conflict (already installed) or 412 Precondition Failed (not armed).
An operator can `reset_verification_token` to rotate it. Agents never see or set
this token — it is operator infrastructure that the indexed rail depends on.

## Personal Notion MCP

Personal Notion OAuth or MCP access is separate from shared SSOT. It is a
non-default personal lane for a user's private workspace, not the way ArcLink
shares organization records that must inherit the ArcLink shared root
permissions.

If content should become shared, move or recreate it under the ArcLink shared
parent through `ssot.write`.

## Verification And Claim Pages

Curator onboarding verification pages are a special case. Current internal
Notion connection APIs cannot reliably invite a specific user to a private page
programmatically, so the verification parent must already have suitable Notion
permissions until a user-OAuth claim lane exists.

## PDFs And Export Fallback

PDFs in Notion may be indexed through generated markdown sidecars when they are
extractable and reachable by the configured integration. For important PDFs,
placing the file in the ArcLink vault gives the PDF ingest pipeline a clearer
source path and freshness contract.

If Notion sync is delayed or a file is not extractable, export or copy the
relevant text into a shared page or vault markdown file.

## Destructive Boundaries

Do not ask an agent to bypass SSOT with raw Notion delete, trash, archive, or
permission changes. If cleanup is needed, ask for an approved operator action
and keep the target page/database id, reason, and backup expectation explicit.
