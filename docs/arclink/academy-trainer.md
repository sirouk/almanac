# ArcLink Academy

The Academy turns an ArcPod Agent from "a SOUL.md that *claims* a specialty"
into a genuinely prepared specialist with a curated corpus, role curriculum,
selected skills, knowledge indexes, memory stubs, evaluation, and a continuing
education rhythm. It is not a one-shot "pick a role" preview.

## The Model: a Skill -> a Sticky Mode -> Commit -> Forward-Maintain

The Academy is a **skill every ArcPod Agent ships with** (`arclink-academy`) with
two faces:

1. **Academy Mode (interactive, Captain-controlled).** The Captain (or the Agent)
   opens it from a **button or `/academy`**. This flips the Agent into a
   **sticky Academy Mode** -- a session that **does not end until the Captain
   ends it**. It is not a single turn. Inside the mode, an **LLM Trainer** (routed
   through the central ArcLink router) and the **Captain** co-curate: the Trainer
   proposes a topic map, pulls and ranks sources from the governed lanes the
   Captain authorizes, drafts a curriculum, lesson cards, a SOUL overlay, and
   skill picks; the Captain steers role, depth, focus, and which lanes are
   allowed. Everything in the mode is **staged/draft -- no live SOUL/skill
   writes**.

2. **Forward-maintenance (autonomous, scheduled).** Once a graduate exists, the
   same skill keeps it fresh on a weekly cadence: it routinely sweeps its lanes,
   refreshes the corpus, re-synthesizes lesson cards, re-evaluates, and
   **self-maintains its SOUL.md + skills** with deltas -- so graduates stay
   ready for Captains always.

**Commit ("everything put in its place").** When the **Captain ends the mode**,
the staged plan is applied: the learning is written into the Agent
**additively** -- SOUL overlay section, vault `Academy/{role}/` curriculum, qmd
index, memory seeds, approved skills -- and the trainee becomes a **graduate**
with weekly forward-maintenance armed. Real Agent writes are gated behind
`PG-HERMES`; live source acquisition and provider curation behind `PG-PROVIDER`
(`GAP-034`).

## The Captain Experience

1. **Browse the Academy.** A gallery of specialist **Majors** (Programs) -- e.g.
   *Systems-Practice Engineer*, *Research Analyst*, *Community Insight
   Specialist*, *Standards & Compliance Reader*, *Domain Tutor* -- and a list of
   existing **graduates** (already-trained Agents ready to adopt). Each Major
   card shows its topic map, the source lanes it draws from, and quality posture.
2. **Choose.** *Adopt a graduate* (clone a ready specialist's Major + staged
   corpus into a chosen Agent -- the fast path) **or** *enroll a new Trainee*
   (name it, pick a Major, set depth, authorize source lanes).
3. **Enter Academy Mode** (sticky). Curate with the Trainer; iterate as long as
   you want. Evaluate.
4. **End the mode** when satisfied -> commit -> the Agent arrives in the ArcPod
   knowing its Major. Weekly continuing education keeps it current.

## Lifecycle State Machine

```
BROWSE majors / graduates
  -> ADOPT graduate   OR   ENROLL trainee
  -> ACADEMY MODE (sticky; LLM Trainer + Captain curate)  --- stays open until the Captain ends it
        corpus assembly -> curriculum -> lesson cards -> evaluation   (staged, no-write)
  -> CAPTAIN ENDS MODE -> graduation gate (PG-PROVIDER + PG-HERMES)
  -> COMMIT: apply plan additively (SOUL overlay, vault, qmd, memory, skills)
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
  (`deployment_id`) plus the Captain's steer (`enroll_academy_trainee`). Status:
  `enrolled` -> `in_academy` -> `graduated` (`archived`).
- **Academy Mode session** -- `academy_mode_sessions` table; the **sticky** mode
  (`open_academy_mode`, `academy_mode_status`, `end_academy_mode`). A unique
  index guarantees one open session per trainee; the mode closes only when the
  Captain ends it.
- **Graduate** -- a trainee with `status='graduated'`; `browse_academy_graduates`
  is the gallery; `adopt_academy_graduate` clones one onto another Agent.

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
- **The Academy skill** (P0/P3): an `arclink-academy` Hermes skill bundled into
  every ArcPod home (`bin/install-arclink-skills.sh` / deployment Hermes-home
  install) that teaches the Agent how to run Academy Mode and which brokered
  tools to use; the managed-context plugin surfaces "Academy Mode active."
- **Sticky mode state** (P0, done): open/status/end, one-open-per-trainee,
  Captain-ends-only semantics.
- **Captain chat surface** (P1): `/academy` and the button in
  `arclink_public_bots.py` / Telegram + Discord adapters open the browse ->
  adopt/enroll -> mode flow; mode stays open across turns; an explicit
  "graduate / end Academy" control commits.
- **Dashboard surface** (P1): an Academy panel in `web/src/app/dashboard/` --
  browse Majors + graduates, enroll, the live mode session, evaluation status,
  next continuing-education time, and graduate adoption.
- **Operator Raven** (P1): read-only Academy/graduate roster + per-Agent mode
  status (extends the existing operator `academy_status`).
- **Hosted API** (P1): versioned routes for list-majors, enroll, mode
  open/status/end, browse-graduates, adopt -- owner/deployment scoped, CSRF on
  mutations, no secrets.
- **LLM Trainer curation engine** (P1, `PG-PROVIDER`): wire corpus ranking,
  curriculum, lesson-card synthesis, and evaluation design to
  `arclink_llm_router.py` (budget-reserved, audited).
- **Live source lanes** (P2, `PG-PROVIDER`, per-lane policy): real adapters
  behind the existing `acquire_*` boundary, one lane at a time.
- **Commit / apply** (P3, `PG-HERMES`): promote `academy_apply_preview` to a real
  `academy_apply` action that writes SOUL overlay / vault / qmd / memory /
  skills through the deployment Hermes-home seams.
- **Forward-maintenance scheduler** (P4): a weekly `academy-ce` job via
  `bin/install-agent-cron-jobs.sh` / `bin/docker-job-loop.sh` that sweeps lanes,
  rebuilds, re-evaluates, and pushes deltas only when the gate says `ready`.
- **Tests/docs** (every phase): `tests/test_arclink_academy_programs.py` (P0),
  surface contract, this doc, and the symphony.

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
- **P1 (`PG-PROVIDER`)** -- LLM Trainer curation via the central router; Captain
  chat/dashboard/Operator-Raven/API surfaces for browse/adopt/enroll/mode.
- **P2 (`PG-PROVIDER`, per-lane policy)** -- live source acquisition, one lane at
  a time (lowest-risk first: `wikimedia` -> `github` -> `scholarly` -> `web` ->
  `video`+ASR -> `reddit` -> `skills` -> `organization_private`).
- **P3 (`PG-HERMES`)** -- real commit: `academy_apply` writes SOUL
  overlay/vault/qmd/memory/skills through the deployment Hermes-home seams,
  additively.
- **P4** -- hosted weekly forward-maintenance via the existing cron/loop
  scheduler.

Reuse summary: the **central LLM router** powers Trainer synthesis (P1-P2); the
**action worker** powers preview -> apply and weekly delta application (P3-P4);
the **existing cron/loop scheduler** powers the weekly cycle (P4). No new
orchestration engine is introduced, and every phase keeps fail-closed
validation, content/secret stripping, additive-only writes, and the named proof
gates.
