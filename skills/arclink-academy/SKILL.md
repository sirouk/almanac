---
name: arclink-academy
description: Use when Academy Mode is active, when the Captain asks an Agent to become a subject-matter specialist, or when the Agent needs to gather, compress, propose, and maintain Academy training resources for weekly continuing education.
---

# ArcLink Academy

Use this skill when the Captain opens Academy Mode or asks you to become a trained subject-matter specialist.

Academy Mode is a living training workflow, not a one-shot role label. Your job is to work with the Captain, gather lawful source candidates, compress what matters, propose resources back to ArcLink for Academy Trainer review, and prepare a replaceable Academy knowledge section that can accompany SOUL without overwriting personal memory.

## Operating Contract

- Treat the Captain as the authority for role, depth, allowed sources, boundaries, and weekly refresh expectations.
- Keep asking clarifying questions until the role, subject matter, outcomes, source lanes, and exclusions are clear.
- Do not store secrets, credentials, raw private data, paywalled material, DRM-protected material, or content the Captain is not allowed to retain.
- Do not claim you are fully trained until ArcLink records Trainer review, graduation proof, and the apply lane updates the Agent.
- Keep training output replaceable: Academy material belongs in a dedicated Academy section and should be safe to refresh or swap if the Captain changes the role.
- Prefer brokered ArcLink retrieval and proposal tools over raw filesystem rummaging.

## Turn Flow

1. Confirm the role and specialist identity the Captain wants.
2. Confirm subject matter, depth, boundaries, and examples of good work.
3. Confirm allowed source lanes: Captain-provided docs, vault/Notion, web articles, scholarly/standards, repositories, video transcripts, community discussion, and approved tools/skills.
4. Search for already-graduated Academy specialists before shaping a new track:

```json
{"tool":"academy.search-graduates","arguments":{"query":"<role/topic>", "limit":5}}
```

Use reusable central/public-lane graduates when they fit, and use same-Captain
graduates as private acceleration only for that Captain. Do not copy another
Captain's private strategy, notes, or protected resources into a public lane.

5. Search and fetch through governed tools first:

```json
{"tool":"knowledge.search-and-fetch","arguments":{"query":"<topic>", "search_limit":3, "fetch_limit":2}}
{"tool":"vault.search-and-fetch","arguments":{"query":"<topic>", "search_limit":3, "fetch_limit":2}}
{"tool":"notion.search-and-fetch","arguments":{"query":"<topic>", "search_limit":3, "fetch_limit":2}}
```

6. For each strong source, submit a compressed proposal:

```json
{
  "tool": "academy.propose-resource",
  "arguments": {
    "title": "Short source title",
    "origin_url": "https://example.test/source",
    "lane_id": "web_article",
    "summary": "Compressed derived notes, not raw content.",
    "relevance": {
      "role_fit": "Why this matters for the Agent's specialist role.",
      "weekly_refresh": "What should be checked weekly.",
      "limits": "Known caveats or boundaries."
    },
    "citations": ["https://example.test/source"]
  }
}
```

7. Tell the Captain what you gathered, what you rejected, what needs Trainer review, and what you still need.
8. When the Captain is satisfied, ask them to graduate or exit Academy Mode through Raven. Do not self-graduate.

## Source Proposal Rules

Good proposals include:

- short title
- source URL, repository, canonical identifier, or clear offline reference
- source lane id
- compressed derived summary
- why it matters for the requested specialist role
- what should be revisited weekly
- citations or source ids
- limitations, freshness risk, and licensing/permission notes

Allowed lane ids:

- `video_transcript`
- `reddit_discussion`
- `wikimedia`
- `github_repository`
- `scholarly_standard`
- `web_article`
- `skill_tool_catalog`
- `organization_private`

## Continuing Education

Weekly Academy refresh should:

- revisit approved source lanes
- detect changed, stale, superseded, removed, or tombstoned sources
- dedupe repeated resources
- preserve citations and source metadata
- rebuild compact lesson cards and update recommendations
- notify the Captain of meaningful changes
- keep the Academy section replaceable and current without rewriting unrelated SOUL or personal memory

## Response Shape

When reporting progress to the Captain, use this shape:

- what I understand the specialist role to be
- sources proposed for Trainer review
- sources rejected or deferred, with reasons
- weekly refresh plan
- open questions
- whether the Captain should continue steering, graduate, or exit
