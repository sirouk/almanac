# ArcLink Academy Trainer

This document describes the target system for turning Crew Training from a
character-and-role recipe into a reusable subject-matter training pipeline. It
is a product score, not a shipped claim. Current source has deterministic Crew
Recipe generation and SOUL overlay paths; the Academy Trainer described here is
a larger buildout that must be tracked through `GAPS.md` before it is called
real.

## Purpose

An ArcLink Agent should not become a subject-matter expert only because
`SOUL.md` says it has a specialty. The Academy should prepare each Crew member
with a curated corpus, a role-specific curriculum, selected skills, knowledge
indexes, memory stubs, evaluation tasks, and a continuing education rhythm.

The target experience is:

1. A Captain chooses or describes a role during Crew Training.
2. Academy Trainer expands that role into a topic map, competency ladder,
   source plan, safety policy, and evaluation rubric.
3. Academy Trainer gathers and scores sources from approved lanes.
4. It archives allowed source snapshots and creates durable lesson cards,
   citations, skill maps, and retrieval indexes.
5. It prepares the Agent's SOUL overlay, vault material, qmd collections,
   memory synthesis seeds, tool recipes, skills, and first-week training plan.
6. The Agent is deployed or refreshed only after a training gate proves the
   curriculum is coherent, current, licensed/allowed, and useful.
7. Weekly continuing education refreshes the corpus, preserves allowed
   high-value material, tombstones removed content where required, updates
   lesson cards, and re-runs evaluation tasks before pushing updates to the
   Agent.

## Source Lanes

Academy Trainer should use multiple source lanes so no Agent learns a domain
from a single brittle view.

### Video And Transcript Lane

Video can be an excellent training source when the transcript is reliable and
lawfully acquired.

- Search for high-quality lectures, tutorials, conference talks, interviews,
  demos, and walkthroughs.
- Prefer creator-provided transcripts, official caption tracks that the
  Operator is authorized to access, public course transcripts, or transcripts
  supplied by the Captain or organization.
- When no transcript is available and rights allow it, Academy Trainer may run
  an approved local/hosted ASR transcription skill and label the result as
  machine-transcribed.
- Capture video title, creator/channel, URL, published date, transcript source,
  transcript confidence, license/permission status, retrieval date, and content
  hash.
- Split transcripts into lessons, demonstrations, heuristics, vocabulary,
  mistakes-to-avoid, and follow-up resource links.
- Never bypass paywalls, DRM, private videos, platform restrictions, or creator
  permissions.

The official YouTube Data API can list caption tracks for a video and points to
caption download as the caption retrieval method, but caption retrieval requires
the right authorization and permissions. Academy Trainer should therefore treat
YouTube transcript ingestion as an authorized connector, not as a free-for-all
scrape.

### Reddit And Practitioner Discussion Lane

Reddit is useful for practitioner vocabulary, recurring pain, edge cases,
tooling opinions, and field-tested patterns. It is also user-generated content
with strict retention and deletion requirements.

- Use official Reddit Data API/OAuth access with a truthful User-Agent,
  rate-limit handling, and subreddit/listing pagination.
- Crawl only selected subreddits, posts, and comments that match the training
  topic and quality filters.
- Score threads by relevance, expert signal, recency, depth, moderation
  quality, accepted corrections, and cross-source agreement.
- Avoid treating upvotes as truth. Extract hypotheses, failure modes, common
  workflows, tool comparisons, and practical language for future research.
- Store raw Reddit content only when policy allows. If Reddit content or a user
  account is deleted, comply with deletion requirements and tombstone the raw
  archive.
- Preserve durable non-identifying lesson cards where allowed: summarized
  patterns, source URL, retrieval timestamp, and reason the lesson matters.
- Never train an Agent to quote or expose private user details.

### Wikipedia And Wikimedia Foundation Lane

Wikipedia is a strong baseline for topic overview, vocabulary, history,
references, adjacent concepts, and canonical disambiguation.

- Use Wikimedia/MediaWiki APIs for search and page retrieval.
- Pull article summaries, sections, references, categories, wikilinks,
  language links, and revision metadata.
- Treat Wikipedia as the map and bibliography, not the final authority.
- Use page references to seed scholarly, standards, docs, and primary-source
  lanes.
- Revisit page revisions during continuing education when the topic is active.

### GitHub And Systems Practice Lane

For technical or operational domains, real repositories reveal how subject
matter experts structure systems.

- Search GitHub by topic, stars, forks, recency, language, license, README
  content, organization/user, and archived status.
- Inspect README, docs, examples, tests, architecture notes, issues,
  discussions, release notes, and dependency manifests where permitted.
- Prefer repositories that are maintained, licensed, documented, tested, and
  used by real practitioners.
- Extract patterns: architecture, workflows, naming, errors, tests, examples,
  automation, safety boundaries, release habits, and tradeoffs.
- Avoid copying code into the Agent's vault unless the license and product
  policy allow it. Prefer explanatory lesson cards and citations.
- Capture repository owner/name, URL, commit or tag, license, topics, stars,
  last push, selected files, and hash/manifest.

### Scholarly, Standards, And Whitepaper Lane

Experts need state-of-the-art and foundational literature.

- Search arXiv, OpenAlex, Semantic Scholar, Crossref, PubMed where relevant,
  standards bodies, official whitepaper repositories, vendor research pages,
  and domain-specific libraries.
- Prefer primary papers, survey papers, benchmark papers, standards, official
  guidance, and well-cited implementation reports.
- Capture DOI/arXiv ID/OpenAlex/Semantic Scholar IDs, authors, title, venue,
  year, abstract, license/open-access status, citation signals, and retrieval
  date.
- Archive PDFs or full text only when allowed. Otherwise store metadata,
  abstract, citations, and a retrieval link.
- Convert papers into durable lesson cards: claims, methods, constraints,
  evidence, assumptions, open problems, and practical operator guidance.
- Mark speculative or contradicted findings so Agents do not treat early
  research as production truth.

### Web, Blog, Article, Newsletter, And Thread Lane

High-value practitioner knowledge often lives outside formal repositories.

- Use web search to discover blogs, articles, newsletters, documentation,
  forum threads, long-form posts, technical notes, and postmortems.
- Prefer sources with clear authorship, dated updates, reputation, examples,
  citations, and stable URLs.
- Capture allowed snapshots, excerpts, metadata, and source hashes.
- Score pages by authority, recency, specificity, evidence, and agreement with
  other lanes.
- Avoid thin SEO content, hallucinated content farms, scraped duplicates, and
  unauthored advice unless they are useful only as negative examples.

### Skill, MCP, Tool, And Template Lane

Academy should equip an Agent with the skills and tools that match the role.

- Search local ArcLink skills, bundled Hermes skills, organization-published
  skills, trusted public skill repositories, MCP servers, templates, and tool
  recipes.
- Score each candidate by relevance, license, maintenance, safety, testability,
  least-privilege fit, and overlap with existing ArcLink tools.
- Prefer short, precise skills that teach the Agent which brokered tool to use,
  what arguments are safe, and what proof to fetch before acting.
- Install or stage only approved skills. Unknown public skills should be
  reviewed and sandboxed before they influence an Agent.
- Keep role-specific skills in a reusable Academy catalog so future Agents can
  be prepared faster.

### Additional Lanes

Academy Trainer should also be able to use:

- official product/vendor documentation;
- standards and regulatory guidance;
- public datasets and benchmark leaderboards;
- patents and technical disclosures where relevant;
- open courseware, syllabi, lecture notes, and textbooks with allowed licenses;
- podcasts or interviews with authorized transcripts;
- organization-private documents supplied by the Captain/Operator;
- internal support tickets, incident reports, and postmortems when policy
  allows and private data is scrubbed.

## Corpus Repository And Archive

The Academy corpus must be reusable without becoming a copyright or privacy
dump.

Recommended private-state layout:

```text
arclink-priv/
  state/academy/
    sources/
      <source-id>/source.json
      <source-id>/snapshot.<ext>
      <source-id>/license.json
      <source-id>/quality.json
      <source-id>/tombstone.json
    topics/
      <topic-id>/topic-map.json
      <topic-id>/curriculum.json
      <topic-id>/resource-manifest.json
      <topic-id>/evaluation.json
    roles/
      <role-id>/skill-map.json
      <role-id>/soul-overlay.json
      <role-id>/continuing-education.json
    lesson-cards/
      <topic-id>/<card-id>.md
    indexes/
      qmd/
      vector/
      citations/
```

Recommended per-Agent vault layout:

```text
Vault/
  Academy/
    <agent-role>/
      README.md
      Curriculum.md
      Source_Map.md
      Lesson_Cards/
      Practice_Tasks/
      Evaluation/
      Skills/
      Continuing_Education/
```

Every stored item needs:

- source URL or origin;
- retrieval timestamp;
- license or permission status;
- content hash;
- extractor/transcriber identity;
- quality score;
- freshness policy;
- deletion/tombstone policy;
- whether raw content, derived summary, or metadata-only storage is allowed;
- which Agents, Captains, or organizations may use it.

## Training Pipeline

The Academy Trainer should produce an Agent that knows how to learn and how to
act, not merely an Agent with a large folder of text.

Pipeline:

1. Role intake: Captain goal, role, domain, level, constraints, tone, tools,
   risk posture, and expected deliverables.
2. Topic map: core concepts, subdomains, vocabulary, tools, workflows,
   failure modes, ethics/safety, and adjacent domains.
3. Source plan: lanes to use, source quotas, freshness needs, source authority
   rules, licenses, and forbidden sources.
4. Acquisition: fetch/search through approved connectors and rate-limited jobs.
5. Extraction: transcript cleanup, PDF parsing, HTML cleanup, repo doc
   extraction, thread summarization, and citation capture.
6. Quality scoring: source authority, recency, specificity, examples,
   cross-source agreement, contradiction flags, and bias/SEO/low-signal flags.
7. Curriculum: beginner-to-expert ladder, practical drills, tool drills,
   readings, demonstrations, and domain-specific checklists.
8. Synthesis: durable lesson cards, vocabulary, heuristics, red flags,
   decision trees, and "where to look next" maps.
9. Equipping: SOUL overlay, skill map, MCP recipes, vault folders, qmd indexes,
   memory synthesis seeds, and first-turn Raven/Agent briefing.
10. Evaluation: scenario tasks, retrieval tests, tool-choice tests, refusal
    tests, citation tests, and output-quality rubrics.
11. Deployment: apply to a new Pod or retrain an existing Agent while
    preserving historical memories/sessions unless the Captain explicitly
    resets them.
12. Audit: record what changed, what sources were used, what skills were
    installed, what evaluations passed, and what remains provisional.

## SOUL, Memory, Skills, And Vault Application

Academy output should touch multiple Agent layers:

- `SOUL.md`: update only the role, voice, expertise, operating heuristics,
  boundaries, and domain-specific behavior sections that need replacement.
- Memory: preserve personal/history memory unless the Captain requests a reset;
  add Academy lesson summaries as managed recall stubs and retrieval hints.
- Vault: install curriculum, source map, lesson cards, practice tasks,
  evaluations, and continuing education notes.
- qmd/vector indexes: index allowed material and derived lesson cards so tools
  can search before answering.
- Skills: install approved role skills and add compact tool recipes so the
  Agent uses the right tools first.
- Sessions: keep existing conversations intact, but add an Academy update note
  so future turns know when retraining happened.
- Dashboard: show training status, source lanes, evaluation results, next
  continuing education time, and blocked/licensing issues.

## Continuing Education

Continuing Education should be a weekly Academy job, not an afterthought.

The weekly cycle:

1. Re-run source searches for each active role/topic.
2. Refresh watched sources, repos, papers, docs, and threads.
3. Detect changed, removed, deleted, stale, contradicted, or superseded
   materials.
4. Tombstone raw content where deletion or license policy requires it.
5. Preserve allowed high-value archived material when it disappears from the
   web, marking it as archived and no longer live-fetchable.
6. Promote better new material over weaker old material while retaining
   historical context when it remains allowed and useful.
7. Rebuild lesson cards, source maps, qmd/vector indexes, memory stubs, skill
   recommendations, and practice tasks.
8. Run evaluation tasks and compare performance against the prior week.
9. Produce a concise Captain/Operator report: what changed, what improved, what
   was removed, what needs approval, and what the Agent now knows to do.
10. Push updates to the Agent only after policy, license, and evaluation gates
    pass.

The balance is important: do not lose knowledge simply because a page moved,
but also do not violate deletion, license, privacy, or platform rules. Archive
allowed material; tombstone disallowed or deleted material; preserve derived
non-identifying lessons only where policy permits.

## Evaluation And Graduation

Academy Training is complete only when the Agent can demonstrate useful
competence.

Graduation gates:

- Can explain the domain's core map and current limits.
- Can retrieve and cite Academy sources before giving specialized advice.
- Can choose the right ArcLink/Hermes/MCP skills for role tasks.
- Can refuse unsafe, unsupported, or out-of-scope actions.
- Can complete representative scenario tasks with concise next actions.
- Can distinguish durable doctrine from fresh web results and provisional
  research.
- Can tell the Captain what it knows, what it does not know, and where it will
  look next.

Evaluation should create scored artifacts that can be reviewed by Operator
Raven, dashboard, CLI, and future Ralphie runs.

## Governance And Proof

Academy Trainer must be governed as carefully as provisioning.

- Do not bypass platform terms, paywalls, DRM, private content, robots/API
  policies, or deletion requirements.
- Do not store secret or private user data in reusable Academy corpora.
- Do not make a public model-training claim from source material that is only
  licensed for transient reading or private use.
- Do not let unreviewed public skills execute privileged tools.
- Do not let Academy summaries become untraceable facts. Every lesson card
  should point back to source metadata.
- Do not call a role trained until source acquisition, quality scoring,
  curriculum generation, equipping, and evaluation have all passed.

The first implementation slice should be local and safe: define the Academy
manifest/schema, source-lane registry, quality scoring skeleton, vault layout,
SOUL overlay plan, continuing-education job model, and tests. Live provider
generation, external crawling at scale, transcription, and hosted continuing
education proof should stay gated until authorized.
