# ArcLink Academy

The Academy turns an ArcPod Agent from "a SOUL.md that *claims* a specialty"
into a genuinely prepared specialist with a curated corpus, role curriculum,
selected skills, knowledge indexes, memory stubs, evaluation, and a continuing
education rhythm. It is not a one-shot "pick a role" preview.

## The Model: a Skill -> a Sticky Mode -> Commit -> Forward-Maintain

The Academy is a **Hermes skill bundle every ArcPod Agent ships with**
(`arclink-academy`, installed from `skills/arclink-academy/SKILL.md`) with two
faces. Note: `arclink-academy` ships as an installed *skill* (named in the
deployment Hermes-home skill list in `arclink_headless_hermes_setup.py` and in
`bin/install-arclink-skills.sh`/`bin/init.sh`/`bin/deploy.sh`), **not** as a
native `plugins/hermes-agent/` plugin -- the native plugins are `arclink-drive`,
`arclink-code`, `arclink-terminal`, and `arclink-managed-context`. Treat the
skill as "named and shipped; live plugin/runtime presence unverified
(`PG-HERMES`)."

1. **Academy Mode (interactive, Captain-controlled).** The Captain (or the Agent)
   opens it from a **button or `/academy`**. This flips the Agent into a
   **sticky Academy Mode** -- a session that **does not end until the Captain
   ends it**. It is not a single turn. Inside the mode, an **LLM Trainer** and the
   **Captain** co-curate: the Trainer proposes a topic map, pulls and ranks
   sources from the governed lanes the Captain authorizes, drafts a curriculum,
   lesson cards, a SOUL overlay, and skill picks; the Captain steers role, depth,
   focus, and which lanes are allowed. **Today this curation is deterministic
   builders + lane-valid local fixtures** (`curate_academy_trainee` /
   `_compose_trainee_corpus`); the live "LLM Trainer" routed through the central
   ArcLink router is **proof-gated behind `PG-PROVIDER`** and not yet wired into
   the Academy path. Everything in the mode is **staged/draft -- no live
   SOUL/skill writes**.

2. **Forward-maintenance (autonomous, scheduled).** Once a graduate exists, the
   weekly `control-academy-ce` job keeps its review fresh on a weekly cadence: it
   classifies each watched source (`unchanged/changed/stale/superseded/removed/
   tombstoned`) and **produces a no-write weekly continuing-education review**
   (`run_academy_forward_maintenance` returns `no_write=True`,
   `writes_enabled=False`, `mutation_performed=False`). It does **not**
   self-maintain SOUL.md or skills: any SOUL/skill deltas apply **only** through
   the proof-gated apply path (`stage_academy_apply`, `PG-HERMES`). The scheduler
   records intent and arms the next review; it never writes to the Agent.

**Commit ("everything put in its place").** When the **Captain ends the mode**,
the staged plan is applied: the learning is written into the Agent
**additively** -- SOUL overlay section, vault `Academy/{role}/` curriculum, qmd
index, memory seeds, approved skills -- and the trainee becomes a **graduate**
with weekly forward-maintenance armed. Real Agent writes are gated behind
`PG-HERMES`; live source acquisition and provider curation behind `PG-PROVIDER`.
This is `GAP-034`: its source-level sub-items A-E landed locally (no-write,
no-network), and it remains OPEN only for externally-gated work -- live source
acquisition per lane (`PG-PROVIDER`), live Trainer synthesis (`PG-PROVIDER`), real
Agent writes (`PG-HERMES`), and source-governance policy. See `GAPS.md` for the
authoritative gap taxonomy.

## The Captain Experience

1. **Browse the Academy.** A gallery of specialist **Majors** (Programs) -- e.g.
   *Systems-Practice Engineer*, *Research Analyst*, *Community Insight
   Specialist*, *Standards & Compliance Reader*, *Domain Tutor* -- and a list of
   existing **graduates** (already-trained Agents ready to adopt). Each Major
   card shows its topic map, the source lanes it draws from, and quality posture.
2. **Choose.** *Adopt a graduate* (clone a ready specialist's Major + staged
   corpus into a chosen Agent -- the fast path) **or** *enroll a new Trainee*
   (name it, pick a Major, set depth, authorize source lanes).
3. **Enter Academy Mode** (sticky). Raven gathers the Captain's role, subject,
   depth, boundaries, outside resources, and weekly refresh expectations one
   turn at a time, then opens the selected Agent's sticky mode. The Agent uses
   the `arclink-academy` skill to search approved rails and submit compressed
   resource proposals through `academy.propose-resource`.
4. **End the mode** when satisfied -> Trainer deep dive -> canon/apply. Closing
   the mode queues the Academy Trainer to review, dedupe, enrich, and compress
   gathered resources. Only after that review and the proof-gated apply path is
   the replaceable Academy section written to the Agent.

## Lifecycle State Machine

```
BROWSE majors / graduates
  -> ADOPT graduate   OR   ENROLL trainee
  -> ACADEMY MODE (sticky; LLM Trainer + Captain curate)  --- stays open until the Captain ends it
        corpus assembly -> curriculum -> lesson cards -> evaluation   (staged, no-write)
  -> CAPTAIN ENDS MODE -> TRAINER DEEP DIVE (dedupe, enrich, compress, review)
  -> graduation/apply gate (PG-PROVIDER + PG-HERMES)
  -> COMMIT: apply replaceable Academy section additively (SOUL overlay, vault, qmd, memory, skills)
  -> GRADUATE (durable) -> FORWARD-MAINTAIN (weekly continuing education) --- loops
```

The fail-closed posture is structural: the local layer never emits
"graduated/trained" content writes; it stages and records intent, and the
control-plane mode/graduate state is real while the Agent-mutating apply waits
on proof.

## Entities And Data Model

Control-plane scaffolding (now built, no-write):

- **Program / Major** -- `academy_programs` table; managed by
  `python/arclink_academy_programs.py` (`list_academy_programs`,
  `upsert_academy_program`, `seed_default_academy_programs`). A Major is **pure
  data**: `label`, `topic_map`, `source_lanes` (refs into the governed lane
  registry), `role_template` (SOUL overlay text), `boundaries`, `default_depth`
  (`survey`/`working`/`deep`), `quality_floor`, `required_skills`. **New trainee
  types are rows, not code.**
- **Trainee** -- `academy_trainees` table; binds a Major to an Agent
  (`deployment_id`) plus the Captain's steer (`enroll_academy_trainee`). Trainee
  id `atrn_<hex>`. Status (`TRAINEE_STATUSES`):
  `enrolled` -> `in_academy` -> `graduated` (`archived`). A **per-account quota**
  caps non-archived trainees at `DEFAULT_MAX_TRAINEES_PER_USER=50` (override
  `ARCLINK_ACADEMY_MAX_TRAINEES_PER_USER`), enforced by `_enforce_trainee_quota`
  on enroll/adopt.
- **Academy Mode session** -- `academy_mode_sessions` table; the **sticky** mode
  (`open_academy_mode`, `academy_mode_status`, `end_academy_mode`). Statuses
  `MODE_SESSION_STATUSES=("open","closed","cancelled")`. A partial unique index
  (`idx_academy_mode_sessions_open_trainee WHERE status='open'`) guarantees one
  open session per trainee; the mode closes only when the Captain ends it. Closed
  and cancelled sessions are pruned to the most recent
  `MODE_SESSION_RETENTION_PER_TRAINEE=25` per trainee (`_prune_mode_sessions`);
  open sessions are never pruned.
- **Resource proposal** -- `academy_resource_proposals` table; the Agent ->
  ArcLink handoff for source candidates discovered during Academy Mode
  (`record_academy_resource_proposal`, MCP tool `academy.propose-resource`).
  Proposal id `aprop_<sha256[:16]>` over `trainee|origin_url-or-title`. Submits
  **only source metadata/citations/derived notes -- never raw crawled content**.
  Status enum `('proposed','review_pending','accepted','rejected','deduped')`. A
  partial unique index (`idx_academy_resource_proposals_trainee_origin WHERE
  origin_url != ''`) deduplicates per `(trainee_id, origin_url)`; an
  `ON CONFLICT` path stamps the duplicate `deduped`. Requires an **open** Academy
  Mode for the deployment; absent-mode submissions and secret-looking material
  are rejected.
- **Graduate** -- a trainee with `status='graduated'`; `browse_academy_graduates`
  is the gallery; `academy_graduate_card` is a **redacted owner-safe projection**
  (withholds `user_id`/`deployment_id`/`agent_id`, private Captain steer, and
  staging pointers); `adopt_academy_graduate` clones one onto another Agent,
  **owner-scoped** (source graduate must belong to the target Captain --
  cross-tenant adoption is a future consented helper, not this clone).

### Central shared specialist corpus (cross-captain, deduplicated)

The per-trainee tables above are the **intake** layer. The Academy's core promise --
*centralized, deduplicated subject-matter-experts whose resources any captain and
crew can reuse* -- lives in five **central** tables in `arclink_control.py`,
populated by `python/arclink_academy_programs.py`:

- **`academy_sources`** -- the **globally-deduplicated** canonical source registry.
  `source_uid` = `sha256(canonical_url)` (URL normalized: lowercased host, stripped
  fragment/tracking params, trimmed slash) or `sha256(specialist|title)` for offline
  sources. Holds **derived notes only, never raw content**; the same source proposed
  by any number of captains collapses to one row (`_canonical_url` + a unique index
  on `canonical_url`). "Review once, store once, reuse everywhere."
- **`academy_corpus_specialists`** -- the **deduplicated SME registry**.
  `specialist_uid` = `sha256(program_id|normalized-topic)`, so all captains training
  the same Major+topic resolve to **one shared specialist**. Carries the
  **replaceable `compressed_soul_capsule`** (the knowledge section that accompanies
  the SOUL) and `capsule_version`.
- **`academy_specialist_sources`** -- junction (specialist <- canonical sources).
- **`academy_source_provenance`** -- **consent + revocation + audit**: the only place
  a central source is tied to a contributing tenant (`share_consent`,
  `redaction_applied`, `revoked_at`). Never exposed cross-tenant.
- **`academy_specialist_subscriptions`** -- which trainees consume a central
  specialist; drives weekly fan-out and the central-vs-trainee staleness check.

**Promotion (`promote_proposals_to_central`, Trainer step at graduation).** Sharing
is **opt-out** (Captain policy): every proposal on a **public lane** (all governed
lanes *except* `organization_private`; `share_eligible_source_lanes`) that passes the
secret-screen (`reject_secret_material`) and the raw-content screen
(`_looks_like_raw_content`) is promoted as `redacted_public` -- **unless** the Captain
set `steer['share']` to a private value. `organization_private` and any
secret/raw-looking material are **never** promoted; they stay per-tenant. Promotion
copies a **whitelist only** (title, canonical_url, lane, derived notes, citations) --
never the Captain's steer, identity, or raw content. `captain_count` is the distinct
consenting-contributor count.

**Reuse (`subscribe_trainee_to_specialist`, called on enroll).** When a Captain
enrolls in a Major that already has a shared specialist, the new trainee
**auto-subscribes** and `_resolve_trainee_sources` feeds the inherited central sources
into its corpus -- so Captain B reuses Captain A's curated, deduped corpus instead of
re-gathering. `academy_specialist_public_card` / `list_central_specialists` expose a
**redacted gallery** (role, topic, per-lane source counts, freshness, capsule version,
captain count) with **no contributor identity**, mirroring `academy_graduate_card`.

**Replaceable capsule (`refresh_specialist_capsule`).** The Trainer composes the
specialist's `compressed_soul_capsule` from its redacted central sources (role +
topic + per-source derived notes + citations), versioned and **idempotent**
(`only_if_changed` skips no-op weekly churn). The weekly `control-academy-ce` job
refreshes capsules and **queues a Captain notification** per graduate
(`queue_notification`, channel `academy`).

**Trainer deep dive (`run_academy_trainer_review`).** At graduation (after
promotion) and on demand, the Academy Trainer reviews the specialist's central
corpus, records per-source verdicts + a review summary on the specialist
`enrichment_json`, stamps `trainer_review_json` on the contributing proposals, and
refreshes the capsule. It is **deterministic by default**
(`DeterministicAcademyTrainer`, no network); the **live** Trainer -- the *same
inference model* used for the Agent, routed through `arclink_llm_router` -- is an
**injectable client** (`client=`, `live = True`) consulted ONLY under `PG-PROVIDER`
authorization (`live_authorized`), and **fails closed** to the deterministic engine
on any error or missing authorization. The mode-end `trainer_deep_dive_status`
stays `queued_for_review` because that field tracks the *live* deep dive; the
deterministic review that ran is recorded as `central_trainer_reviewed` /
`central_trainer_engine`.

**Replaceable SOUL section (render/apply, `PG-HERMES`).** `arclink_org_profile`
provides `BEGIN/END_ACADEMY_MARKER` + `render_academy_overlay` /
`merge_academy_overlay` / `remove_academy_overlay` -- a **separate marker pair** from
the org-profile overlay, so the Academy capsule renders as a self-contained,
swappable section that never touches the human SOUL body or the org-profile block.
`stage_academy_apply` stages the rendered `academy_soul_section` for the PG-HERMES
Hermes-home installer to merge additively; the control plane writes nothing itself.

**Cross-OPERATOR sharing gate.** Within one ArcLink instance the `redacted_public`
corpus is shared across the operator's captains/crew. A future cross-*operator*
marketplace read/promotion is gated behind **`PG-CONSENT`**
(`ACADEMY_CROSS_TENANT_PROOF_GATE`).

Curation/training entities (defined, proof-gated execution) live in
`python/arclink_academy_trainer.py`: `SourceLanePolicy`, `AcademySource`,
`QualityRecord`, `CurriculumRecord`, `EvaluationGate`, `CorpusManifest`,
`AgentApplicationPlan`, `ContinuingEducationPlan`, and the no-write
`academy_apply_preview` action-worker boundary.

## Surfaces To Prepare (full inventory)

Delivering the complete experience touches these surfaces. P-tags map to the
phased plan below.

- **Data model** (P0, done): `academy_programs`, `academy_trainees`,
  `academy_mode_sessions` in `arclink_control.py`; lifecycle in
  `arclink_academy_programs.py`.
- **The Academy skill** (P0/P3): an `arclink-academy` Hermes **skill** bundled
  into every ArcPod home (`skills/arclink-academy/SKILL.md`, installed via
  `bin/install-arclink-skills.sh` / `bin/init.sh` / deployment Hermes-home install,
  named in the skill list in `arclink_headless_hermes_setup.py`) that teaches the
  Agent how to run Academy Mode and which brokered tools to use; the
  `arclink-managed-context` plugin surfaces "Academy Mode active." It is a skill,
  not a native `plugins/hermes-agent/` plugin; its live runtime presence inside a
  Hermes container is unverified (`PG-HERMES`).
- **Sticky mode state** (P0, done): open/status/end, one-open-per-trainee,
  Captain-ends-only semantics.
- **Captain chat surface** (P1, done): `/academy` in `arclink_public_bots.py`
  now selects one Agent at a time, gathers Captain steering over multiple turns,
  opens the real sticky `academy_mode_sessions` record, accepts more steering
  notes while open, and lets the Captain `graduate` or `cancel` at any time.
  Closing the mode queues Trainer deep dive; it does not claim canon.
- **Dashboard surface** (P1, done): the **Academy** tab in
  `web/src/app/dashboard/page.tsx` -- browse Majors + graduates, enroll a
  Trainee, enter/close (graduate or cancel) the sticky mode, and adopt a
  graduate. Backed by the `api.*Academy*` client methods.
- **Operator Raven** (P1, done): read-only `academy_roster` command in
  `arclink_operator_raven.py` (fleet-wide or per-user graduates + in-academy +
  enrolled), alongside the existing per-user `academy_status`.
- **Hosted API** (P1, done): the six owner-scoped Academy routes (`GET /user/academy`,
  `GET /user/academy/mode-status`, `POST /user/academy/{enroll,mode-open,mode-end,adopt}`)
  -- CSRF on mutations, no secrets. See the route catalog in
  `docs/API_REFERENCE.md` and `docs/openapi/arclink-v1.openapi.json` (authoritative)
  rather than re-enumerating here.
- **Resource proposal rail** (P1, done): Agents in Academy Mode use the
  `arclink-academy` skill and `academy.propose-resource` MCP tool to submit
  compressed source candidates back to ArcLink. Proposals are central,
  dedupable, secret-checked, and queued for Trainer review; raw content is not
  stored through this handoff.
- **LLM Trainer curation engine** (P1): `curate_academy_trainee` /
  `_compose_trainee_corpus` compose the governed corpus + application plan +
  review, and `end_academy_mode` curates on graduation. Uses lane-valid local
  fixtures today; live router synthesis stays `PG-PROVIDER` gated.
- **Live source lanes** (P2, `PG-PROVIDER`, per-lane policy): real adapters
  behind the existing `acquire_*` boundary, one lane at a time.
- **Commit / apply** (P3, done, `PG-HERMES` gated): the `academy_apply` action in
  `arclink_action_worker.py` (`stage_academy_apply`) stages the additive SOUL /
  vault / qmd / skills application plan. It is fail-closed: record-only adapters
  stage, live adapters without `ARCLINK_ACADEMY_APPLY_LIVE` fail closed, and
  authorized runs hand off to the deployment Hermes-home seam.
- **Forward-maintenance scheduler** (P4, done): the weekly `control-academy-ce`
  compose job runs `arclink_academy_scheduler.py` (`run_academy_forward_maintenance`),
  a no-write weekly continuing-education review per graduate; live lane sweeps +
  delta application stay `PG-PROVIDER`/`PG-HERMES` gated.
- **Tests/docs** (every phase): `tests/test_arclink_academy_programs.py`,
  `tests/test_arclink_academy_scheduler.py`, the action-worker + hosted-API +
  operator-raven + web suites, this doc, and the symphony.

## Source Lanes

The Academy uses multiple lanes so no Agent learns a domain from one brittle
view. All lanes are a **governed registry** today
(`default_source_lane_registry`, `arclink_academy_trainer.py`) with full policy
(authorization, license/permission, raw-storage, deletion/tombstone, quality
weight, required metadata) and **fake fixtures only** -- live acquisition is OFF
until wired per phase P2.

| Lane (`lane_id`) | Use | Live wiring | Gate |
| --- | --- | --- | --- |
| `video_transcript` | Lectures, talks, demos; lawful transcripts; labeled ASR | YouTube/caption API + ASR | `PG-PROVIDER` |
| `reddit_discussion` | Practitioner vocabulary, pain, edge cases (raw never stored unless policy allows) | Reddit OAuth API | `PG-PROVIDER`/`PG-BOTS` |
| `wikimedia` | Topic map, vocabulary, references, revisions | MediaWiki API | `PG-PROVIDER` |
| `github_repository` | Architecture, tests, examples (cite, don't copy) | GitHub API/clone + license review | `PG-HERMES` |
| `scholarly_standard` | arXiv/OpenAlex/Semantic Scholar/Crossref, standards, whitepapers | Scholarly APIs (metadata-first) | `PG-PROVIDER` |
| `web_article` | Blogs, docs, postmortems, threads | Web search + snapshot | `PG-PROVIDER` |
| `skill_tool_catalog` | Role skills/MCP/tool recipes (approved-only) | Skill/MCP registry + review workflow | `PG-HERMES` |
| `organization_private` | Captain/operator-supplied docs (scrubbed) | Authorized ingestion + governance | `PG-HERMES` |

Each stored item carries: source URL/origin, retrieval timestamp,
license/permission status, content hash, extractor identity, quality score,
freshness policy, deletion/tombstone policy, allowed storage class
(metadata-only / derived-summary / raw-snapshot), and which Agents/Captains may
use it. Never bypass paywalls, DRM, private content, robots/API policies, or
deletion requirements; never store secret/private user data in reusable corpora.

## Corpus Repository And Archive

Private-state layout (`arclink-priv/state/academy/`): `sources/<id>/{source,
snapshot, license, quality, tombstone}.json`, `topics/<id>/{topic-map,
curriculum, resource-manifest, evaluation}.json`, `roles/<id>/{skill-map,
soul-overlay, continuing-education}.json`, `lesson-cards/<topic>/<card>.md`,
`indexes/{qmd,vector,citations}/`. Per-Agent vault namespace:
`Vault/Academy/<role>/{README, Curriculum, Source_Map, Lesson_Cards/,
Practice_Tasks/, Evaluation/, Skills/, Continuing_Education/}`.

## Imparting Learning (the real write-path)

Commit wires the staged `AgentApplicationPlan` into the existing deployment
Hermes-home chain (`bin/install-deployment-hermes-home.sh`), **additively**:

- **SOUL.md**: render the role/expertise/boundaries overlay into a marked
  Academy subsection (`arclink_org_profile`/`arclink_headless_hermes_setup` SOUL
  render); never overwrite the human-authored body or personal memory.
- **Skills**: add approved role skills via `bin/install-arclink-skills.sh` /
  bundled-skills sync; never remove existing skills.
- **qmd**: `bin/qmd-refresh.sh` re-indexes the vault after files land.
- **Vault**: write only under `Academy/<role>/` (additive namespace).
- **Memory**: seed `arclink_memory_synthesizer` candidates; its dedup path keeps
  personal memory intact.
- **Managed context**: surface the active Major through the managed-context
  plugin.

Mechanically this is a new `academy_apply` action (parallel to the no-write
`academy_apply_preview`) with `writes_enabled=True` + executor dispatch
(`bin/refresh-agent-install.sh`-style), idempotent and audited through the
action worker. `PG-HERMES` gated.

## Continuing Education / Forward-Maintenance

A weekly Academy job, not an afterthought. Cycle: re-run source searches; refresh
watched sources; classify `unchanged/changed/stale/superseded/removed/tombstoned`
(`build_continuing_education_plan`); tombstone disallowed/deleted material;
preserve allowed high-value archived material; promote stronger material; rebuild
lesson cards/indexes/memory stubs; re-run evaluations; produce a Captain/Operator
report; push SOUL/skill deltas **only** when the gate says `ready`.
`removed`/`tombstoned` sources hard-block the Agent update; reviews are
content-stripped and secret-free; every cycle is audited. Scheduling reuses the
existing cron/loop infra (P4).

## Evaluation And Graduation

Graduation gates (`academy_evaluation_gate` / `academy_graduation_gate`): can
explain the domain map and limits; retrieve-and-cite before specialized advice;
choose the right ArcLink/Hermes/MCP skills; refuse unsafe/out-of-scope actions;
complete representative scenario tasks; distinguish durable doctrine from fresh
results; tell the Captain what it knows, does not know, and where it will look
next. Evaluation produces scored artifacts reviewable by Operator Raven,
dashboard, and CLI. The local layer returns `blocked_by_live_proof` until
`PG-PROVIDER` + `PG-HERMES` evidence exists.

## Governance And Proof

- Do not bypass platform terms, paywalls, DRM, private content, robots/API
  policies, or deletion requirements.
- Do not store secret or private user data in reusable corpora.
- Do not make a public model-training claim from material licensed only for
  transient reading or private use.
- Do not let unreviewed public skills execute privileged tools.
- Every lesson card points back to source metadata; nothing becomes an
  untraceable fact.
- A role is not "trained" until acquisition, quality scoring, curriculum,
  equipping, and evaluation all pass under the named proof gates.

## Current Slice And Phased Plan

**Shipped (P0, local, no-write, no proof gate):**

- `academy_programs` / `academy_trainees` / `academy_mode_sessions` tables
  (`arclink_control.py`) and the lifecycle module `arclink_academy_programs.py`:
  a seeded catalog of Majors, enroll-trainee, the **sticky Academy Mode**
  (open/status/end, one-open-per-trainee, Captain-ends-only), graduate gallery,
  and graduate adoption. Commit at mode-end records intent + arms
  forward-maintenance; it performs **no** Agent SOUL/skills/qmd/vault writes
  (`mutation_performed=False`). Covered by
  `tests/test_arclink_academy_programs.py`.
- The pre-existing governed source-lane registry, fake acquisition, quality
  scoring, curriculum/evaluation/graduation gates, no-write application plan, and
  weekly continuing-education classification in `arclink_academy_trainer.py`.

**Phased plan to the real deal:**

- **P0 (done)** -- experience scaffolding as data + sticky mode (no gate).
- **P1 (done)** -- curation engine composes corpus/plan/review locally and
  on graduation (`curate_academy_trainee`); **hosted API**, **dashboard Academy
  tab**, **Operator Raven `academy_roster`**, and the **Captain in-chat sticky-mode
  `/academy` flow** are built and tested. The `/academy` chat flow
  (`_handle_academy_training_workflow` / `_academy_open_mode_reply` in
  `arclink_public_bots.py`) selects one Agent, gathers steer over multiple turns,
  opens the **real** sticky `academy_mode_sessions` record via
  `enroll_academy_trainee` + `open_academy_mode`, and graduates/cancels via
  `end_academy_mode`. *Remaining:* live LLM-Trainer synthesis via the central
  router, proof-gated behind `PG-PROVIDER`.
- **P2 (`PG-PROVIDER`, per-lane policy)** -- live source acquisition, one lane at
  a time (lowest-risk first: `wikimedia` -> `github` -> `scholarly` -> `web` ->
  `video`+ASR -> `reddit` -> `skills` -> `organization_private`).
- **P3 (done, code path; `PG-HERMES` gated)** -- the `academy_apply` action
  (`stage_academy_apply`) stages the additive SOUL overlay/vault/qmd/skills plan
  and is fail-closed: record-only adapters stage, live adapters without
  `ARCLINK_ACADEMY_APPLY_LIVE` fail closed, authorized runs hand off to the
  deployment Hermes-home seam. The live write itself awaits an authorized
  `PG-HERMES` proof window.
- **P4 (done, no-write; live sweep `PG-PROVIDER` gated)** -- the weekly
  `control-academy-ce` compose job runs `arclink_academy_scheduler.py`'s no-write
  continuing-education review per graduate.

Reuse summary: the **central LLM router** powers Trainer synthesis (P1-P2, live
remaining); the **action worker** powers preview -> apply and weekly delta
application (P3-P4); the **`control-academy-ce` docker job** powers the weekly
cycle (P4). No new orchestration engine is introduced, and every phase keeps
fail-closed validation, content/secret stripping, additive-only writes, and the
named proof gates.
