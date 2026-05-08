# Ralphie Memory System Cherrypick Study

## Current ArcLink Memory Shape

ArcLink's current memory system is not a classic chat-memory plugin. It is a
governed, multi-rail awareness layer:

- `arclink-managed-context` reads
  `$HERMES_HOME/state/arclink-vault-reconciler.json` and hot-injects compact
  context through Hermes `pre_llm_call`.
- Managed sections include `qmd-ref`, `notion-ref`, `vault-topology`,
  `vault-landmarks`, `recall-stubs`, `notion-landmarks`, `notion-stub`, and
  `today-plate`.
- The plugin injects on first turn, revision/model-runtime changes, relevant
  prompts, relevant follow-ups, and selected tool-recipe matches.
- Dynamic managed context is intentionally not written into Hermes `MEMORY.md`;
  legacy managed entries are cleaned from `MEMORY.md`.
- `memory_synthesis_cards` stores synthesized source-linked awareness cards for
  vault and Notion sources. These are rendered into `[managed:recall-stubs]`.
- `[managed:recall-stubs]` tells the agent where to look. It is not evidence.
  The agent must use `knowledge.search-and-fetch`, `vault.search-and-fetch`,
  `notion.search-and-fetch`, `notion.fetch`, `ssot.read`, or `ssot.write` for
  depth and changes.

This is the right core for ArcLink because the product is governed knowledge,
not unconstrained conversational memory.

## Reference Systems Studied

The local Hermes docs snapshot includes reference memory plugins under
`arclink-priv/state/hermes-docs-src/plugins/memory/`. Treat that directory as a
read-only mirrored reference corpus only; do not inspect unrelated private state.

Reference families:

- ByteRover: hierarchical knowledge tree and tiered retrieval.
- Hindsight: graph/entity memory with `low|mid|high` recall budgets and
  context/tools/hybrid modes.
- Holographic: local SQLite facts with FTS, trust scoring, and contradiction
  actions.
- Honcho: cross-session user/AI peer modeling, separate context and dialectic
  cadences, conclusions.
- mem0: explicit profile/search/conclude conversational memory.
- OpenViking: filesystem-like knowledge hierarchy and tiered context loading.
- RetainDB: cloud memory with hybrid search, memory types, and shared file
  store.
- Supermemory: semantic long-term memory with profile recall, search/store/
  forget tools, session ingest, and container tags.

## What To Keep From ArcLink

Do not replace ArcLink managed context with these plugins. ArcLink has
load-bearing properties the references generally do not:

- brokered Notion/SSOT writes with verification and approval rails,
- qmd-backed retrieval over vault, PDF, and Notion collections,
- user-scoped today plate from structured Notion/task surfaces,
- hot-reload signals from vault-watch,
- governed source-of-truth posture where recall stubs route to evidence rather
  than becoming evidence,
- user/tenant isolation and private-state boundaries.

## Cherrypicks To Add To Ralphie's Plan

### 1. Trust And Contradiction Signals

Borrow from Holographic: memory cards should carry trust/confidence and a way
to surface source disagreement.

ArcLink already stores `card_json` and rendered `card_text`; it should evaluate
whether to add:

- normalized `trust_score`/`confidence` fields,
- provenance/source-count/source-freshness hints in card JSON,
- a contradiction/disagreement warning when multiple sources under the same
  entity/topic disagree,
- recall-stub wording that says "possible conflict" and tells the agent which
  rail to fetch before answering.

### 2. Recall Budget Tiers

Borrow from Hindsight/OpenViking: make memory context budget explicit.

ArcLink currently has per-section character caps and
`ARCLINK_MEMORY_SYNTH_CARDS_IN_CONTEXT`. Ralphie should evaluate:

- `ARCLINK_MANAGED_CONTEXT_RECALL_BUDGET=low|mid|high`,
- tiered card counts and section caps by budget,
- user/agent/operator visibility of which budget is active,
- tests proving low budget still keeps the routing rules and safety guardrails.

### 3. Cheap Layer / Expensive Layer Cadence

Borrow from Honcho: split cheap refresh from expensive synthesis.

ArcLink currently gates whole-context injection by first turn, revision change,
runtime change, relevance, follow-up, and recipe. Ralphie should evaluate:

- cheap layer: vault topology, landmarks, recent events, model runtime, basic
  retrieval recipes;
- expensive layer: today plate, Notion digest, semantic synthesis cards;
- independent revisions/cadences for each layer so a file rename does not
  require reinjecting every expensive semantic section on every relevant turn;
- telemetry that reports which layer injected and why.

### 4. Conversational Memory As Optional Sibling

Borrow the product lesson, not the whole implementation. mem0, Supermemory,
Honcho, RetainDB, Hindsight, etc. solve "remember chat facts/preferences." ArcLink
solves "route governed organizational knowledge." These can coexist.

Ralphie should document and, if low-risk, prepare an extension point:

- `arclink-managed-context` is complementary to conversational-memory plugins,
  not a replacement.
- Operators may stack a separate Hermes memory plugin when they want chat-fact
  memory, but it must not bypass ArcLink user isolation, SSOT write governance,
  or private-state boundaries.
- ArcLink should not auto-capture every turn into governed memory until there is
  an explicit product/security decision.

### 5. Local-Only Synthesis Fallback

Borrow the local-first idea from Hindsight/Holographic. Current memory synthesis
depends on an OpenAI-compatible endpoint/API key when enabled. Ralphie should
evaluate a local fallback:

- non-LLM/BM25/entity-summary awareness cards,
- no network dependency,
- lower-quality but safe routing hints,
- explicit status in health/admin/user dashboards.

### 6. Agent Self-Model And Multi-Agent Peer Awareness

Borrow cautiously from Honcho/RetainDB. ArcLink's multi-agent roadmap may need
agents to know their own recent actions and other linked agents' accepted shared
work, but this should be scoped and audited.

Ralphie should mark this as product-policy work unless an existing local path is
already present:

- per-agent action summary cards,
- accepted-share peer hints,
- no raw cross-agent transcript access,
- no private data leakage through peer memory.

## What Not To Borrow

- Do not add broad auto-capture of every Hermes turn into ArcLink memory without
  a product/security decision.
- Do not deduplicate or rewrite vault/Notion source truth as if recall cards are
  the source of truth.
- Do not add complex HRR/algebraic retrieval unless qmd/SSOT/vault structure
  demonstrably fails.
- Do not introduce a cloud memory provider as a required dependency for ArcLink
  managed context.

## Ralphie Success Criteria For This Addendum

- The active product reality matrix includes a memory-systems row that says
  what ArcLink does today and which cherrypicks are `real`, `gap`,
  `proof-gated`, or `policy-question`.
- Highest-ROI local repairs are implemented with tests if they fit the current
  build window.
- Any deferred memory pattern is documented as a deliberate product choice, not
  an accidental omission.

