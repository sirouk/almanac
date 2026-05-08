# Plugin-Managed Context Example

This is a fictionalized example of the local managed-context state an ArcLink
agent can receive. Do not use production vault names, usernames, file paths, or
Notion page titles in public examples or regression fixtures.

Dynamic ArcLink context belongs in plugin-managed state and is hot-injected by
`arclink-managed-context`. It should not be written into Hermes `MEMORY.md`.

## Example State

```json
{
  "active_subscriptions": [
    "Agent_Knowledge",
    "Projects",
    "Repos",
    "Research"
  ],
  "agent_id": "agent-example",
  "has_recall_stubs": true,
  "has_today_plate": true,
  "managed_memory_revision": "rev-example",
  "managed_payload_cache_key": "cache-example",
  "today_plate_item_count": 0,
  "updated_at": "2026-04-29T19:06:23+00:00"
}
```

## Example Recall Stubs

```text
Retrieval memory stubs:
- Treat these as awareness cards, not facts to answer from. Use MCP retrieval for the depth before citing or changing anything.
- Default broad question path: knowledge.search-and-fetch with a specific natural-language query.
- Vault/PDF/file path: vault.search-and-fetch; include vault-pdf-ingest for PDF-derived markdown.
- Shared Notion path: notion.search-and-fetch for documentation/notes; notion.query only for one exact live structured database target.
- User-visible vault root for file references: /home/example/ArcLink
Subscribed awareness lanes:
- Agent_Knowledge: category=knowledge, owner=organization. Ask vault.search-and-fetch for depth; current lane root is ~/ArcLink/Agent_Knowledge.
- Projects: category=workspace, owner=organization. Ask vault.search-and-fetch for depth; current lane root is ~/ArcLink/Projects.
- Repos: category=inventory, owner=organization. Ask vault.search-and-fetch for depth; current lane root is ~/ArcLink/Repos.
- Research: category=research, owner=organization. Ask vault.search-and-fetch for depth; current lane root is ~/ArcLink/Research.
Recent hot-reload signals:
- 2026-04-29T19:05:58+00:00 Repos changed via vault-watch; 12 path(s): sample-sdk/README.md, sample-sdk/src/client.py ... (+10 more). Use search-and-fetch for current contents; this stub only tells you where to look.
- 2026-04-29T19:04:52+00:00 Projects changed via vault-watch; 3 path(s): README.md, roadmap.md, design/overview.md. Use search-and-fetch for current contents; this stub only tells you where to look.
Semantic synthesis cards:
- Compact recall hints only: use retrieval tools for evidence, exact text, citations, or state changes.
- [vault:Creator Studio] Fictional episode assets, publishing notes, and lightweight planning tables for a sample creator workflow. Domains: creator, business. Workflows: content planning, production review, publishing cadence. Content: videos, images, tables, notes. Topics: episode production, thumbnails. Entities: Creator Studio. Search hints: Creator Studio episode plan; pilot cut thumbnail. Sources to fetch: Episodes/pilot-cut.mp4, Episodes/thumbnail.png, content-calendar.csv. Confidence: medium.
- [vault:Research Annex] Fictional research PDFs and notes for retrieval tests. Domains: research. Workflows: literature review. Content: PDFs, notes. Topics: research, protocols. Entities: Research Annex. Search hints: Research Annex; archive note alpha. Sources to fetch: archive_note_alpha.pdf. Confidence: medium.
Quality rule: if recall feels thin, say which rail was searched and retry once with narrower nouns, owner names, file titles, or source lane.
```

## Example Landmark Stub

```text
[managed:vault-landmarks]
Vault landmarks:
- Compact map only: names, folders, and filenames are recall cues, not evidence. Use knowledge.search-and-fetch or vault.search-and-fetch for content before answering.
- Coverage: ... top-level folder(s) under /home/example/ArcLink; .vault subscription lanes and plain qmd-indexed folders both count.
- Research Annex: plain-folder. PDFs: archive_note_alpha.pdf, archive_note_beta.pdf
```

The important behavior is that plain qmd-indexed top-level folders are visible
as ambient routing hints even when they are not `.vault` subscription lanes.
Agents still need retrieval before citing or acting.

## Example Notion Stub

```text
Shared Notion digest:
- Current SSOT shape: page-scoped. ArcLink cannot build a structured database digest from this target yet.
- Read routing: use knowledge.search-and-fetch or notion.search-and-fetch for indexed shared Notion/vault context; use notion.fetch when an exact page URL or id is known. ssot.read page reads require verified Notion ownership and a scoped target.
- Write routing: use ssot.write for permitted brokered updates on in-scope user work.
- If a brokered action is denied, explain it as a verification, scope, or allowed-operation limit; do not describe that as the skill being missing or the rail disappearing.
- Verification: not started yet. Brokered ssot.read page reads and shared writes remain gated until the user verifies their Notion identity.
```
