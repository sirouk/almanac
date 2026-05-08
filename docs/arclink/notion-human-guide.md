# ArcLink Notion Human Guide

ArcLink has more than one Notion lane. Use the lane that matches the work.

## Shared SSOT

Shared organization pages and databases should be created and edited through
the SSOT broker:

- `ssot.read`
- `ssot.write`
- `ssot.status`

The broker keeps writes under the configured ArcLink shared/root parent and
blocks destructive archive/delete/trash style changes unless an explicit
approval rail exists. Use this lane for team notes, operating profile content,
shared databases, and agent-visible source-of-truth pages.

## Indexed Notion Knowledge

Indexed shared Notion pages are synchronized into the `notion-shared` qmd
collection. Agents should search through:

- `notion.search-and-fetch`
- `notion.fetch`
- `knowledge.search-and-fetch`

Exact live reads are scoped to configured shared/indexed roots. If a page is
available to a Notion token but outside the ArcLink root/index scope, agent
tools should refuse it rather than treating broad integration access as
permission.

## Personal Notion MCP

Personal Notion OAuth or MCP access is separate from shared SSOT. Use personal
Notion for a user's private workspace, not for shared organization records that
must inherit the ArcLink shared root permissions.

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
