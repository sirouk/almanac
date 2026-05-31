# Ground Truth 06 — Academy Programs/Trainer, Crew Recipes, SOUL Projection

Date mapped: 2026-05-30. Branch: `arclink`. Source of truth = code, not docs.

Owning code:
- `python/arclink_academy_programs.py` — control-plane lifecycle (Majors, Trainees, sticky Mode, gallery, adopt, curation staging, central corpus, apply staging, continuing-education builder).
- `python/arclink_academy_trainer.py` — no-network/no-write Academy schemas + fail-closed planning helpers (lane registry, sources, corpus, plans, gates, review status, application-preview boundary).
- `python/arclink_crew_recipes.py` — Crew Recipes + the SOUL overlay + Academy-status overlay onto the active recipe + per-Agent academy artifact builder.
- `python/arclink_academy_scheduler.py` — weekly forward-maintenance job (`run_academy_forward_maintenance`, CLI `main`).
- Tables in `python/arclink_control.py` (lines ~1490–1585).
- Action worker wiring `python/arclink_action_worker.py` (`academy_apply_preview`, `academy_apply`, and PG-HERMES authorized SOUL-overlay materialization).
- MCP rail `python/arclink_mcp_server.py` (`academy.propose-resource` ~86/344/2079).
- Chat flow `python/arclink_public_bots.py` (`/academy`, `_handle_academy_training_workflow` ~5405).
- SOUL/identity projection `python/arclink_provisioning.py` (`project_arclink_deployment_identity_context` ~222).

Backing doc judged: `docs/arclink/academy-trainer.md`. Skimmed: `docs/arclink/sovereign-control-node-symphony.md` (Academy section, lines ~409–509).

---

## A. What is actually implemented today (local-real)

### Academy as a per-ArcPod skill + sticky Academy Mode
- The Academy is modeled as a sticky **mode experience**, not a one-shot preview. Opened by button or `/academy`; stays open until the Captain ends it. This is real in the DB and the chat flow.
- `open_academy_mode(conn, *, trainee_id, opened_by, opened_via="command")` is **idempotent**: an already-open session is returned (`created=False`). On insert it flips the trainee to `status='in_academy', mode_open=1`. Race-safe: a partial unique index (`idx_academy_mode_sessions_open_trainee WHERE status='open'`) guarantees one open session per trainee; an `IntegrityError` rollback returns the race winner's session.
- `academy_mode_status(conn, *, trainee_id)` returns `{trainee, mode_open, session, program}`.
- `active_academy_mode_for_deployment(conn, *, deployment_id)` resolves the open session + trainee + program for one deployment (used to gate resource proposals).
- `update_academy_trainee_steer(...)` merges Captain steering into the trainee while the mode is open (control-plane only; never touches Agent SOUL/skills/qmd/vault). Sanitizes keys/values, caps `captain_notes` at the last 50.

### Majors / Programs (pure data)
- `academy_programs` table; new trainee TYPES are rows, not code.
- Seeded catalog `_default_programs()` ships **5 Majors** with canonical `program_id`s: `systems_practice_engineer`, `research_analyst`, `community_insight_specialist`, `standards_compliance_reader`, `domain_tutor`. Each carries `label`, `summary`, `topic_map`, `source_lanes`, `role_template` (SOUL overlay text), `boundaries`, `default_depth`, `quality_floor`, `required_skills`.
- `seed_default_academy_programs(conn)` is idempotent with a **read-only fast path** (`_program_row_matches_default`) — only writes/commits when a default drifts. Returns catalog size (5).
- `upsert_academy_program`, `get_academy_program`, `list_academy_programs(include_archived=False)`. `PROGRAM_DEPTHS=("survey","working","deep")`.
- Lane names in a Major are validated against `arclink_academy_trainer.default_source_lane_registry` (`_validate_source_lanes`); unknown lanes raise. Secret material in summary/topic_map/role_template/boundaries is rejected via `arclink_boundary.reject_secret_material`.

### Trainees
- `academy_trainees` table; `enroll_academy_trainee(...)` binds a Major to a `deployment_id` + Captain steer. Trainee id = `"atrn_" + secrets.token_hex(8)`.
- `TRAINEE_STATUSES=("enrolled","in_academy","graduated","archived")`. Lifecycle: `enrolled -> in_academy` (open mode) `-> graduated` (end-graduate) or back to `enrolled` (end-cancel).
- Per-account quota: `_enforce_trainee_quota` counts non-archived trainees; default cap `DEFAULT_MAX_TRAINEES_PER_USER=50`, override env `ARCLINK_ACADEMY_MAX_TRAINEES_PER_USER`.

### Graduate gallery + adopt
- `browse_academy_graduates(conn, *, user_id=None)` returns `{graduates, programs}`, each graduate enriched with `program_label` + `source_lanes`.
- `academy_graduate_card(graduate)` is a **redacted owner-safe projection** exposing only `_GRADUATE_CARD_FIELDS` (trainee_id, name, status, depth, program_id, program_label, source_lanes, forward_maintained, graduated_at). It **withholds** `user_id/deployment_id/agent_id`, private Captain steer, and internal staging pointers.
- `adopt_academy_graduate(...)` clones a graduate's Major + staged manifest/plan ids into a **new graduated** trainee (`adopted_from_trainee_id` recorded). Owner-scoped: source graduate must belong to target user (cross-tenant marketplace is explicitly a future separate consented helper, not this clone).

### End-of-mode commit (no-write; mutation_performed=False)
- `end_academy_mode(conn, *, session_id, actor, graduate=True, ...)`:
  - On graduate: if no staged plan/manifest yet, it calls `curate_academy_trainee(commit=False)` inside the same atomic txn ("everything put in its place"); marks trainee `graduated`, `forward_maintained=1`, records `staged_manifest_id`/`staged_plan_id`/`graduated_at`.
  - On cancel: trainee returns to `enrolled`, session `cancelled`.
  - Writes a rich `commit_summary` with defaulted keys: `graduated`, `manifest_id`, `resource_proposal_count`, `trainer_deep_dive_status` (`queued_for_review`), `canon_status` (`not_canon_until_trainer_deep_dive_and_apply`), `agent_write_status` (`blocked_until_trainer_review_and_pg_hermes`), `apply_status` (`deep_dive_queued`), `apply_proof_gates` (`PG-PROVIDER`,`PG-HERMES`), `forward_maintenance` (`weekly continuing education armed`).
  - **Return always carries `mutation_performed=False, workspace_mutation_performed=False`.** No Agent SOUL/skills/qmd/vault write happens here.
  - Curation errors are caught, redacted (`arclink_secrets_regex.redact_then_truncate`), and recorded in summary — mode-end never crashes.
- `_prune_mode_sessions` bounds closed/cancelled session growth at `MODE_SESSION_RETENTION_PER_TRAINEE=25` per trainee (open sessions never pruned; the session being finalized is protected via `keep_session_id`).

### Curation staging (no-write application plans)
- `curate_academy_trainee(...)` and `_compose_trainee_corpus(...)` compose the governed corpus + application plan + review via `build_academy_corpus` / `build_agent_application_plan` / `build_academy_review_status`. Stages `staged_manifest_id`/`staged_plan_id` on the trainee. Returns `mutation_performed=False, workspace_mutation_performed=False`.
- **Stable-id design (load-bearing):** manifest_id/plan_id derive from a STABLE per-trainee timestamp (`created_at`/`enrolled_at`), not wall-clock — so the same (trainee, Major-state) always produces the same staged ids. A Major edit after graduation changes content -> changes id -> apply fail-closes.
- When `sources` not supplied, lane-valid local fixtures are built by `_fixture_sources_for_program` (uses `_LANE_REQUIRED_META` per-lane metadata + `fake_academy_source`). Live acquisition replaces fixtures behind `PG-PROVIDER`.

### academy_apply (fail-closed apply; PG-HERMES)
- `stage_academy_apply(...)` recomputes the corpus/plan, extracts additive intent counts (`soul_overlay_sections`, `approved_skill_intents`, `qmd_memory_seed_intents`, `vault_file_intents`), and computes `status`/`writes_enabled` via **fail-closed gates**:
  - trainee must be `graduated` with mode closed (else raises);
  - must carry persisted `staged_manifest_id`/`staged_plan_id` (Captain-approved contract) — else `not_staged`;
  - recomputed ids must match staged ids (`contract_fresh`) — else `stale_requires_regraduation`;
  - target/owner consistency (deployment/user) enforced;
  - live adapter (`local`/`ssh`/`live`) + `live_authorized` (PG-HERMES) + review ready -> `handoff_to_hermes_home` (`writes_enabled=True`);
  - live adapter without authorization -> `failed_closed`; record-only adapter -> `staged`. All non-handoff statuses keep `writes_enabled=False`.
- The staged result carries `mutation_performed=False, workspace_mutation_performed=False, filesystem_mutation_performed=False`. The action worker is the materialization seam: when `writes_enabled=True`, target is a deployment, and `academy_soul_section` is present, `_materialize_academy_apply` merges the marker-bounded Academy section into `<hermes_home>/SOUL.md`, writes `<hermes_home>/state/arclink-academy-apply.json` with mode 0600, updates `academy_specialist_subscriptions.last_applied_capsule_version`, and returns `status="applied_hermes_home"`, `mutation_performed=True`, `applied_paths=["SOUL.md","state/arclink-academy-apply.json"]`.
- This path materializes the replaceable SOUL capsule and receipt only. Vault/qmd/skill file deltas remain staged/planned intents until a future proof-gated installer path implements them.
- `operation_kind="academy_agent_apply"`. Constant `ACADEMY_APPLY_PROOF_GATES=("PG-PROVIDER","PG-HERMES")`.

### Central shared specialist corpus
- Central tables now back the reusable Academy promise: `academy_sources`, `academy_corpus_specialists`, `academy_specialist_sources`, `academy_source_provenance`, and `academy_specialist_subscriptions`.
- `promote_proposals_to_central(...)` promotes only public-lane, public-safe derived summaries into a deduplicated source registry. `organization_private`, secret-looking material, and raw-content-looking material are never promoted.
- Existing central sources preserve the first accepted title/derived notes/content hash/lane; later Captains can add provenance and citations but cannot overwrite the canonical shared body.
- `refresh_specialist_capsule(...)` builds the versioned `compressed_soul_capsule`; `run_academy_trainer_review(...)` stores deterministic review/enrichment; `academy_continuing_education(...)` now resolves real trainee/central sources first and only falls back to fixtures when no real source exists.
- `academy_specialist_subscriptions` records which trainees consume a shared specialist and the last capsule version applied to their Hermes home.

### Resource proposal rail (Agent -> ArcLink handoff)
- `record_academy_resource_proposal(...)` requires an OPEN Academy Mode for the deployment. Submits only source metadata/citations/derived notes (no raw crawled content). Dedup id = `"aprop_" + sha256(trainee|url-or-title)[:16]`; ON CONFLICT(trainee_id, origin_url) sets status `deduped`. Table `academy_resource_proposals`, status enum `('proposed','review_pending','accepted','rejected','deduped')`. Exposed as MCP tool `academy.propose-resource` (`arclink_mcp_server.py`), which rejects an absent open mode + secrets.

### Continuing education (weekly forward-maintenance; no-write)
- `academy_continuing_education(...)` builds the weekly plan via `build_continuing_education_plan`, classifying each source into `unchanged/changed/stale/superseded/removed/tombstoned`. Returns `mutation_performed=False`.
- `arclink_academy_scheduler.run_academy_forward_maintenance(...)`: iterates `graduated` + `forward_maintained` trainees, runs the no-write CE review per trainee, writes `academy_forward_maintenance_recorded` event+audit rows, reports `eligible/processed/deferred_to_next_run/errors`. CLI `main(--db --limit --once --json)`. `limit<=0` = unbounded. Constant `DEFAULT_FORWARD_MAINTENANCE_LIMIT=200`, env `ARCLINK_ACADEMY_CE_LIMIT`.

### Trainer schemas + gates (`arclink_academy_trainer.py`)
- Lane registry `default_source_lane_registry()` ships **8 lanes**: `video_transcript`, `reddit_discussion`, `wikimedia`, `github_repository`, `scholarly_standard`, `web_article`, `skill_tool_catalog`, `organization_private`. All `fake_fixture_supported=True`, `live_actions_enabled=False`. Each carries full policy + `required_metadata` + `quality_weight`.
- Dataclasses: `SourceLanePolicy`, `AcademySource`, `AcademyAcquisitionRequest/Report/Result`, `QualityRecord`, `CurriculumRecord`, `EvaluationGate`, `CorpusManifest`, `AgentApplicationPlan`, `ContinuingEducationPlan`, `AcademyApplicationPreviewRequest/Result`.
- `validate_academy_sources` fails closed for: disabled/unsupported lanes, no fake-fixture contract, `live_actions_enabled`, non-`local_fixture` acquisition_mode, requested live-action flags, missing license/permission, unsupported/over-permissive storage policy, reddit deletion/tombstone violations, unreviewed public skills, secret-looking material.
- `build_academy_corpus` -> `CorpusManifest` (manifest_id `academy-<sha[:16]>`); `score_academy_source` deterministic (base `52 + lane.quality_weight`, +citation/positive-flag bumps, negative penalties, clamp 0–100, accepted if `>= min_source_score`).
- Gates: `academy_evaluation_gate` (`ready_for_review`/`live_proof_pending`/`blocked_by_policy`/`blocked_by_quality`); `academy_graduation_gate` (returns `blocked_by_live_proof` until PG-PROVIDER+PG-HERMES evidence; **never** returns trained/graduated/applied).
- `build_agent_application_plan` -> `AgentApplicationPlan` (`no_write=True`, `writes_enabled=False`) with SOUL overlay sections (`academy-expertise`, `academy-boundaries`), vault intents under `Academy/<role>/`, qmd memory seeds, approved skill intents (only `skill_tool_catalog` lane w/ `review_status=approved`).
- `build_academy_review_status` -> compact status summary (the artifact dashboards/Raven/Crew-overlay read). Keeps `proof_gates`, `local_only/no_network/no_write/writes_enabled=False/live_proof_required=True`.
- Application-preview worker boundary: `build_academy_application_preview_request/result`. Hard-rejects raw-content/filesystem keys (`ACADEMY_APPLICATION_PREVIEW_FORBIDDEN_KEYS`), live/write flags (`ACADEMY_APPLICATION_PREVIEW_LIVE_FLAGS`), absolute paths/traversal/workspace value terms. `operation_kind="academy_application_preview"`, `executor_called=False`.

### Crew Recipes + SOUL overlay (`arclink_crew_recipes.py`)
- Presets `ALLOWED_CREW_PRESETS = {frontier:Frontier, concourse:Concourse, salvage:Salvage, vanguard:Vanguard}`; capacities `sales/marketing/development/life coaching/companionship` with per-capacity Agent title pools (`CAPACITY_AGENT_TITLES`).
- `deterministic_crew_recipe(...)` builds the `recipe_text` + `soul_overlay` (crew_preset, crew_capacity, captain_role/mission/treatment, applied_at, crew_recipe_text). This is the always-available local SOUL projection.
- `preview_crew_recipe` / `apply_crew_recipe`: provider path is **injectable + proof-gated**. `OpenAICompatibleCrewRecipeProvider` calls an operator-configured OpenAI-compatible endpoint; default chosen by `default_crew_recipe_provider(env)` (env: `ARCLINK_CREW_RECIPE_ENDPOINT`/`ARCLINK_LLM_ROUTER_URL`/`OPENAI_BASE_URL`, key, model). `_provider_context` gates live generation via `evaluate_chutes_deployment_boundary` (billing/entitlement) — falls back to deterministic preset-only overlay when not allowed. Provider output passes `UNSAFE_OUTPUT_PATTERNS` boundary; up to `MAX_PROVIDER_ATTEMPTS=3`.
- `apply_crew_recipe` archives the prior active recipe, inserts the new `arclink_crew_recipes` row (status `active`), writes per-deployment agent_name/agent_title/personality/theme into `arclink_deployments.metadata_json`, updates `arclink_users` captain fields, audits, then **projects identity** for every deployment via `project_arclink_deployment_identity_context(source="crew_training")`.
- `whats_changed` diffs current vs prior recipe (preset/capacity/role/mission/treatment).

### Crew Recipe SOUL overlay carries the Academy status
- Academy status is stored as an `academy_training` sub-key on the active recipe's `soul_overlay_json`:
  - `stage_crew_academy_review` / `stage_crew_academy_weekly_review` persist a review-only status (`mutation_performed=True, workspace_mutation_performed=False`).
  - `build_crew_academy_artifacts_for_agent` builds governed local Academy artifacts for ONE Captain-owned Agent (3 fixture sources: org_private crew brief, wikimedia source map, approved skill_tool_catalog skill).
  - `stage_crew_academy_agent_training` / `skip_crew_academy_agent_training` -> `_persist_academy_agent_status` writes a per-Agent status into the recipe overlay (`_academy_rollup_status`) AND into `arclink_deployments.metadata_json["academy_training"]`, then calls `project_arclink_deployment_identity_context(source="academy_training")`.
- **SOUL/identity projection** (`project_arclink_deployment_identity_context`): writes a managed-context identity state file (under `<hermes_home>/state/`), only when the deployment metadata points at a local Hermes home that already exists (else `status="skipped"`, reason `state_roots_missing`/`local_hermes_home_missing`). Projects `academy_*` fields (status, summary, role_title, manifest_id, source_count, graduation_status) + crew recipe overlay fields. Remote fleet projection is deliberately deferred to a worker/migration transport — this is local-only.

---

## B. Proof-gated / fake-adapter / local-only

- **Live source acquisition is OFF.** All 8 lanes are fake-fixture only; `acquire_fake_academy_sources` is explicitly "not a live fetcher" and accepts only local fixture rows. Live acquisition is `PG-PROVIDER` per lane (P2). `validate_academy_sources` rejects any non-`local_fixture` acquisition mode or live-action flag.
- **LLM Trainer synthesis is fake/deterministic.** `curate_academy_trainee` uses lane-valid local fixtures; live router synthesis stays `PG-PROVIDER`. (The doc calls this "LLM Trainer", but no live router call exists in the Academy path today — it is deterministic builders + fixtures.)
- **Mode-end/curation/CE do not write Agent files.** `end_academy_mode`, `curate_academy_trainee`, and weekly CE remain no-write with respect to the Agent.
- **`academy_apply` SOUL materialization is real but PG-HERMES-gated.** `writes_enabled` requires BOTH a live executor adapter (`local`/`ssh`/`live`) AND `ARCLINK_ACADEMY_APPLY_LIVE` (`live_authorized`) AND review readiness. Default executor (fake/record-only) -> `staged`, no write. Authorized action-worker runs materialize the marker-bounded Academy SOUL section plus a private receipt; they do not yet write vault/qmd/skill deltas.
- **Crew Recipe live generation** is `PG-PROVIDER`/billing gated; default is the deterministic preset-only overlay.
- **Continuing-education observed sources** are not swept live — the scheduler passes `observed_sources=None`; live sweeps are reserved (`_ = dict(env or {})  # reserved for future PG-PROVIDER observed-source wiring`).
- **Forward-maintenance does NOT auto-apply SOUL/skills.** The scheduler only records a no-write review. Authorized `academy_apply` can materialize the Academy SOUL overlay/receipt; vault/qmd/skill deltas remain planned/proof-gated.

---

## C. Canonical vocabulary (real names from code)

Tables: `academy_programs`, `academy_trainees`, `academy_mode_sessions`, `academy_resource_proposals`, `academy_sources`, `academy_corpus_specialists`, `academy_specialist_sources`, `academy_source_provenance`, `academy_specialist_subscriptions`, `arclink_crew_recipes`. Indexes: `idx_academy_trainees_user_status`, `idx_academy_mode_sessions_open_trainee` (partial, `WHERE status='open'`), `idx_academy_resource_proposals_trainee_status`, `idx_academy_resource_proposals_trainee_origin` (partial, `WHERE origin_url != ''`), central-source/provenance/specialist subscription indexes in `ensure_schema()`.

Id prefixes: trainee `atrn_`, session `asess_`, proposal `aprop_`, recipe `crew_`, manifest `academy-<sha[:16]>`, plan `academy-plan-<sha[:16]>`, CE refresh `academy-refresh-<sha[:16]>`, weekly review `academy-weekly-<sha[:16]>`, lesson card `lesson-<slug>`.

Programs/Majors: `systems_practice_engineer`, `research_analyst`, `community_insight_specialist`, `standards_compliance_reader`, `domain_tutor`.

Source lanes: `video_transcript`, `reddit_discussion`, `wikimedia`, `github_repository`, `scholarly_standard`, `web_article`, `skill_tool_catalog`, `organization_private`.

Status/enum: `TRAINEE_STATUSES`, `MODE_SESSION_STATUSES=("open","closed","cancelled")`, `PROGRAM_DEPTHS=("survey","working","deep")`, `ALLOWED_STORAGE_POLICIES={metadata_only,derived_summary,raw_snapshot}`, `PASSING_GATE_STATUSES={ready_for_review,live_proof_pending}`, `ACADEMY_WEEKLY_STATE_KEYS`.

Key functions: `open_academy_mode`, `end_academy_mode`, `academy_mode_status`, `active_academy_mode_for_deployment`, `enroll_academy_trainee`, `adopt_academy_graduate`, `browse_academy_graduates`, `academy_graduate_card`, `curate_academy_trainee`, `stage_academy_apply`, `academy_continuing_education`, `record_academy_resource_proposal`, `update_academy_trainee_steer`, `seed_default_academy_programs`, `upsert_academy_program`. Trainer: `default_source_lane_registry`, `build_academy_corpus`, `build_agent_application_plan`, `build_continuing_education_plan`, `academy_evaluation_gate`, `academy_graduation_gate`, `build_academy_review_status`, `build_academy_application_preview_request/result`. Crew: `deterministic_crew_recipe`, `preview_crew_recipe`, `apply_crew_recipe`, `stage_crew_academy_review`, `stage_crew_academy_weekly_review`, `stage_crew_academy_agent_training`, `build_crew_academy_artifacts_for_agent`, `whats_changed`. Provisioning: `project_arclink_deployment_identity_context`.

Actions: `academy_apply_preview`, `academy_apply` (action worker). MCP tool: `academy.propose-resource`. Events/audit: `crew_academy_review_staged`, `crew_academy_agent_training_staged`, `academy_agent_apply_recorded`, `academy_forward_maintenance_recorded`, `crew_recipe_applied`/`crew_recipe_applied_by_operator`. Constants: `ACADEMY_APPLY_PROOF_GATES`, `ACADEMY_LIVE_PROOF_GATES`, `ACADEMY_APPLICATION_PREVIEW_PROOF_GATES` (all `("PG-PROVIDER","PG-HERMES")`). Env: `ARCLINK_ACADEMY_MAX_TRAINEES_PER_USER`, `ARCLINK_ACADEMY_APPLY_LIVE`, `ARCLINK_ACADEMY_CE_LIMIT`, `ARCLINK_CREW_RECIPE_*`. Scheduler job: `control-academy-ce` (compose), CLI `arclink_academy_scheduler.py`. SOUL overlay helpers: `render_academy_overlay`, `merge_academy_overlay`, `remove_academy_overlay` in `arclink_org_profile.py`.

---

## D. Undocumented or newer than the docs

1. **`academy_resource_proposals` table + `record_academy_resource_proposal` + the `academy.propose-resource` MCP tool** exist and are wired, but the entity is **not in the doc's "Entities And Data Model" section** (only mentioned in prose under "Resource proposal rail"). The table, its unique dedupe index, the status enum, and the `'deduped'` ON CONFLICT path deserve first-class documentation.
2. **`adopt_academy_graduate` cross-tenant restriction + `academy_graduate_card` redaction** — the owner-scoped clone and the redacted public card field set are real and security-relevant; the doc only says "adopt a graduate" without the redaction contract.
3. **`stage_academy_apply` stale-contract fail-closed status `stale_requires_regraduation`** and the stable-id-vs-recompute mechanism is real, security-load-bearing, and not described in the doc (doc only says "fail-closed" generically).
4. **Per-account trainee quota** (`DEFAULT_MAX_TRAINEES_PER_USER=50`, env override) is undocumented.
5. **Mode-session retention pruning** (`MODE_SESSION_RETENTION_PER_TRAINEE=25`) is undocumented.
6. **The `/academy` chat flow now uses the new sticky-mode primitives** (`enroll_academy_trainee`, `open_academy_mode`, `end_academy_mode`, `get_open_academy_mode`) — see `_academy_open_mode_reply` / `_handle_academy_training_workflow` in `arclink_public_bots.py`. This contradicts the doc's stale "Remaining" note (see staleness below).
7. **Crew Recipe `academy_training` overlay carries both a single-review shape (`stage_crew_academy_review`) and a per-Agent rollup shape (`_academy_rollup_status` with `agents[]`, `trained_agent_count`, etc.)** — two distinct overlay schemas; doc does not distinguish them.
8. **`commit_summary` defaulted keys** on `end_academy_mode` (`trainer_deep_dive_status`, `canon_status`, `agent_write_status`, `apply_status`, `apply_note`) form a precise canon-not-claimed contract worth documenting verbatim.

---

## E. Per-doc staleness verdicts

### `docs/arclink/academy-trainer.md` — staleness: LIGHT (mostly accurate; current docs should preserve these corrections)
This doc is unusually well-aligned with code. The current documentation pass
folds in the concrete corrections below:
1. **Skill name mismatch.** Doc says the skill is `arclink-academy`. MEMORY lists native plugins as `arclink-drive`, `arclink-code`, `arclink-terminal`, `arclink-managed-context` — no `arclink-academy` plugin directory was found under `plugins/hermes-agent/`. The "skill" is referenced in install/SOUL prose (`arclink_control.py` ~17069) and the chat flow, but verify whether a real `arclink-academy` Hermes plugin ships or whether it is currently only prose guidance. Flag as "skill named, plugin presence unverified."
2. **STALE "Remaining" claim under P1.** Doc line ~275: *"the Captain in-chat browse/adopt/enroll/mode flow (the legacy crew-recipe `/academy` chat flow is untouched)"* is now FALSE. The `/academy` flow in `arclink_public_bots.py` (`_handle_academy_training_workflow`, `_academy_open_mode_reply`) selects one Agent, gathers steer, and opens the REAL sticky `academy_mode_sessions` record via `enroll_academy_trainee` + `open_academy_mode`, and graduates/cancels via `end_academy_mode`. Correct this to "done (in-chat sticky-mode flow shipped)."
3. **Forward-maintenance boundary.** The scheduler is **no-write** and never applies SOUL/skill deltas itself. The current authorized `academy_apply` path materializes only the marker-bounded Academy SOUL section plus a receipt; vault/qmd/skill deltas remain planned/proof-gated.
4. **`academy_resource_proposals` table absent from the Entities section.** Add it (table, dedupe index, status enum, `academy.propose-resource` rail) as a first-class entity.
5. **"LLM Trainer (routed through the central ArcLink router)"** (lines ~17–19) implies a live router call exists. Today curation is deterministic builders + lane-valid fixtures; live router synthesis is still `PG-PROVIDER` remaining. Keep but mark explicitly proof-gated.
6. **Add quota + retention guardrails** (`ARCLINK_ACADEMY_MAX_TRAINEES_PER_USER` = 50, mode-session retention = 25) to the data-model section.
7. **Lane gate table:** `github_repository` and `skill_tool_catalog` and `organization_private` show `live_proof_boundary` referencing `PG-HERMES` in code; the doc table's Gate column matches. Minor: doc shows `reddit_discussion` gate as `PG-PROVIDER`/`PG-BOTS`; code's `live_proof_boundary` text says "PG-PROVIDER/PG-BOTS" — consistent.

### `docs/arclink/sovereign-control-node-symphony.md` (Academy section ~409–509) — staleness: LIGHT
1. Keep the no-write weekly scheduler boundary explicit and describe `academy_apply` as the PG-HERMES-gated SOUL-overlay materialization path, not as broad self-maintaining skills/qmd/vault automation.
2. The section accurately marks live acquisition/provider/workspace/governance as `GAP-034` remaining and the control-plane scaffolding as P0 done — this is correct vs code.
3. Mentions `academy_apply_preview` action-worker boundary (line ~483) — correct; could also name the `academy_apply` (P3) action which is also wired in `arclink_action_worker.py`.
4. The "Captains enter this lane with `/academy` ... open a real sticky Academy Mode" (lines ~495–499) is **accurate** and is the correct version — note the academy-trainer.md "Remaining" note contradicts this same symphony claim, so fix academy-trainer.md to match.

---

## F. GAP-034 true status

GAP-034 = "Academy Trainer subject-matter corpus / continuing education / source-lane governance / graduation proof."

- **Not in the active steering DoD.** `research/RALPHIE_ARCLINK_ECOSYSTEM_GAP_REPAIR_STEERING.md` contains **no** GAP-034 reference. GAP-034 belongs to the PRIOR completed mission; its remaining work is policy/proof handoff, not new local code.
- **Sub-gaps A–E all landed** (`research/BUILD_COMPLETION_NOTES.md`, `mission_status.md`): GAP-034-A (schema/local foundation), B (review/status integration), C (fake acquisition adapters), D (no-write apply preview), E (weekly review + graduation gate). `mission_status.md` states: "the local weekly Academy Continuing Education persistence and graduation gate are implemented ... this reduces GAP-034 without closing it."
- **True current status: source-level work COMPLETE; GAP-034 remains OPEN only for externally-gated items** — live source acquisition per lane (`PG-PROVIDER`), ASR/transcription, live LLM-Trainer router synthesis (`PG-PROVIDER`), real Agent SOUL/skills/qmd/vault writes (`PG-HERMES` apply window), and source-governance policy decisions. No further local Academy code is expected unless a governance decision or authorized proof window opens. `COVERAGE_MATRIX.md` maps GAP-034 to journeys J-21, J-23, J-24 alongside `PG-PROVIDER`/`PG-HERMES`.

Other GAPs this subsystem touches (per `COVERAGE_MATRIX.md` J-24): `GAP-003`, `GAP-015`, `GAP-022` (live recipe/SOUL generation = provider proof), `GAP-023`, `GAP-031`, `GAP-033`, plus proof gates `PG-BOTS`/`PG-PROVIDER`/`PG-HERMES`.

---

## G. Test coverage (for reference)
- `tests/test_arclink_academy_programs.py` (20 test functions), `tests/test_arclink_academy_trainer.py` (12), `tests/test_arclink_academy_scheduler.py` (3), plus `tests/test_arclink_crew_recipes.py` for the Crew Recipe + overlay paths.
