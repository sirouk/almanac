# Mission Status

Updated: 2026-05-27

## Document Phase Handoff

Status: complete for the unattended local repair run. No unconditional `LOCAL`
gap remains after `GAP-034-E`; the remaining queue is live proof, policy
decision, or residual-risk acceptance unless a future authorized proof window
or operator decision exposes a concrete source defect.

What changed:

- `IMPLEMENTATION_PLAN.md`: marked the documentation/handoff slice complete,
  checked off the local document-phase tasks, and recorded the focused
  documentation/hygiene/inventory validation commands.
- `mission_status.md`: added this handoff entry so the newest status does not
  point future agents back into speculative local work.
- `research/BUILD_COMPLETION_NOTES.md`: records the same document-phase gap
  slice, files changed, validation commands, and remaining external gates.

Validation:

- `python3 tests/test_documentation_truths.py` passed: 10 documentation truth
  tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'docker_authority_inventory_matches_compose_boundary or docker_docs_cover_socket' --maxfail=5`
  passed: 2 passed, 62 deselected.
- `git diff --check` passed.

Remaining: live proof gates remain for production, Stripe, bots, ingress,
workspace/Hermes, Notion, backup/restore, provider behavior, worker lifecycle,
rolling upgrades, and Academy live/provider/workspace proof. Policy decisions
remain for provider self-service, Request Share adapter, Captain migration,
provider dashboard changes, Discord Curator authority, broader Operator Raven
mutation, and Academy source governance. `GAP-019` remains a trusted-host
residual-risk handoff.

## GAP-034-E Academy Weekly Review And Graduation Gate

Status: the local weekly Academy Continuing Education persistence and
graduation-readiness slice is implemented and tested. This reduces
`GAP-034` without closing it; live source acquisition, ASR/transcription,
provider generation, hosted weekly scheduling, real vault/qmd/Hermes-home/
SOUL/skill writes, trained-Agent workspace proof, and source-governance policy
remain open.

What changed:

- `python/arclink_academy_trainer.py`: extended the continuing-education
  artifact into a weekly review with state counts for unchanged, changed,
  stale, superseded, removed, tombstoned/deleted, and review-needed sources;
  added unsafe observed-source payload rejection and a local graduation gate
  that fails closed as `blocked_by_live_proof` without `PG-PROVIDER` and
  `PG-HERMES` evidence.
- `python/arclink_crew_recipes.py`: added
  `stage_crew_academy_weekly_review(...)`, persists the weekly/gate summary on
  the active Crew Recipe `academy_training` overlay, and records secret-free
  audit/event metadata with review and blocked-source counts.
- `python/arclink_dashboard.py`, `python/arclink_operator_raven.py`, and
  `web/src/app/dashboard/page.tsx`: surface weekly review, evaluation,
  graduation, next-review, blocked-source, and proof-gate status without
  claiming the Agent was trained or updated.
- `tests/test_arclink_academy_trainer.py`,
  `tests/test_arclink_crew_recipes.py`,
  `tests/test_arclink_dashboard.py`, and
  `tests/test_arclink_operator_raven.py`: cover the weekly artifact, unsafe
  observed-source refusals, no-write persistence, audit/event metadata, and
  dashboard/Raven projections.

Validation:

- Pre-edit reproduction:
  `python3 -m pytest -q tests/test_arclink_academy_trainer.py::test_weekly_continuing_education_review_classifies_changes_and_keeps_no_write_boundary tests/test_arclink_academy_trainer.py::test_academy_graduation_gate_blocks_without_live_provider_and_workspace_proof tests/test_arclink_crew_recipes.py::test_academy_weekly_review_persists_on_active_recipe_without_workspace_writes tests/test_arclink_dashboard.py::test_dashboard_exposes_academy_weekly_and_graduation_status --maxfail=1`
  failed because the four focused tests were not present.
- Focused tests passed with 4 tests.
- Adjacent tests passed:
  `python3 -m pytest -q tests/test_arclink_academy_trainer.py tests/test_arclink_crew_recipes.py tests/test_arclink_dashboard.py tests/test_arclink_operator_raven.py --maxfail=1`.
- Compile and web validation passed:
  `python3 -m py_compile python/arclink_academy_trainer.py python/arclink_crew_recipes.py python/arclink_dashboard.py python/arclink_operator_raven.py`
  `cd web && npm test`, and `cd web && npm run lint`.
- Broad local Python validation passed:
  `python3 -m pytest -q tests` with 1353 passed, 6 skipped, and 97 warnings.

Remaining: `GAP-034` is now a policy/proof handoff in this plan. Add more
local Academy code only when source governance decisions or authorized proof
produce a concrete source defect.

## GAP-034-D Academy No-Write Apply Preview

Status: the local Academy application-worker preview boundary is implemented
and tested. This reduces `GAP-034` without closing it; real Agent application
writes, weekly persistence, evaluation/graduation, live source acquisition,
ASR/transcription, provider generation, workspace proof, and source-governance
policy remain open.

What changed:

- `python/arclink_academy_trainer.py`: added typed
  `AcademyApplicationPreviewRequest` and
  `AcademyApplicationPreviewResult` helpers. They validate a staged Academy
  manifest/application-plan reference against the active Crew Recipe status,
  require `local_only=true`, `no_write=true`, `writes_enabled=false`, and keep
  `PG-PROVIDER`/`PG-HERMES` visible.
- `python/arclink_crew_recipes.py`: exposes compact staged application-plan
  and target-Agent references through the public Academy status without raw
  source content.
- `python/arclink_action_worker.py`: wires `academy_apply_preview` as a local
  control-DB action that records audit, event, and operation-link metadata
  without calling an executor or filesystem write path.
- `python/arclink_dashboard.py`: marks the admin action as queueable only
  through the no-write local worker contract and keeps real Agent application
  proof-gated.
- `tests/test_arclink_academy_trainer.py`,
  `tests/test_arclink_action_worker.py`, and
  `tests/test_arclink_admin_actions.py`: prove successful no-write preview
  recording and fail-closed rejection for write-enabled, workspace/path,
  secret-looking, and mismatched requests.

Validation:

- Pre-edit reproduction:
  a focused in-memory admin queue probe rejected `academy_apply_preview` as an
  unsupported action type.
- Focused tests passed:
  `python3 tests/test_arclink_academy_trainer.py`,
  `python3 tests/test_arclink_action_worker.py`, and
  `python3 tests/test_arclink_admin_actions.py`.
- Adjacent tests and compile passed:
  `python3 tests/test_arclink_crew_recipes.py`,
  `python3 tests/test_arclink_dashboard.py`,
  `python3 tests/test_arclink_operator_raven.py`, and
  `python3 -m py_compile python/arclink_academy_trainer.py python/arclink_crew_recipes.py python/arclink_action_worker.py python/arclink_dashboard.py python/arclink_operator_raven.py`.

Remaining: `GAP-034` still has local product work for weekly Academy
persistence and evaluation/graduation. Real vault/qmd/Hermes-home/SOUL/skill
application writes and trained-Agent workspace behavior remain `PG-HERMES`
gated, and live acquisition/generation/transcription remains
`PG-PROVIDER`/policy gated.

## GAP-034-C Academy Fake Acquisition Adapters

Status: the local Academy acquisition slice is implemented and tested. This
reduces `GAP-034` without closing it; live source crawling, ASR/transcription,
provider generation, workspace application, source-governance policy, weekly
persistence, application-worker writes, and graduation proof remain open.

What changed:

- `python/arclink_academy_trainer.py`: added
  `AcademyAcquisitionRequest`, `AcademyAcquisitionResult`,
  `AcademyAcquisitionReport`, and `acquire_fake_academy_sources(...)`. The
  helper accepts local fixture records only, preserves `no_network` and
  `no_write`, enforces required lane metadata, and returns compact
  accepted/rejected/proof-gated counts without raw source dumps.
- `tests/test_arclink_academy_trainer.py`: now covers fake acquisition
  fixtures for video transcript, Reddit discussion, Wikimedia, GitHub,
  scholarly/standards, web article, skill/tool catalog, and
  organization-private lanes. It also proves fail-closed rejection for disabled
  lanes, unsupported lanes, requested live actions, missing license/permission,
  unsafe raw storage, deleted Reddit content without tombstones, unreviewed
  public skills, duplicate source IDs, and secret-looking fixture content.
- `tests/test_arclink_crew_recipes.py` and `tests/test_arclink_dashboard.py`:
  align their Academy fixtures with the now-enforced required lane metadata.
- `GAPS.md`, `IMPLEMENTATION_PLAN.md`, `USER_JOURNEY.md`,
  `docs/arclink/academy-trainer.md`,
  `docs/arclink/sovereign-control-node-symphony.md`, and this status file
  record the local repair without claiming live-trained Agent proof.

Validation:

- Broad local gate checked first:
  `python3 -m pytest -q tests` with 1342 passed, 6 skipped, 97 warnings in
  65.43s.
- Pre-edit reproduction:
  `python3 tests/test_arclink_academy_trainer.py` passed the old 6 tests, and
  a focused local probe failed with missing `AcademyAcquisitionRequest`,
  `AcademyAcquisitionResult`, and `acquire_fake_academy_sources`.
- Focused tests passed:
  `python3 tests/test_arclink_academy_trainer.py`,
  `python3 tests/test_arclink_crew_recipes.py`,
  `python3 tests/test_arclink_dashboard.py`, and
  `python3 tests/test_arclink_operator_raven.py`.
- Compile check passed:
  `python3 -m py_compile python/arclink_academy_trainer.py python/arclink_crew_recipes.py python/arclink_dashboard.py python/arclink_operator_raven.py`.
- Post-slice broad suite passed:
  `python3 -m pytest -q tests` with 1344 passed, 6 skipped, 97 warnings in
  65.95s.

Remaining: `GAP-034` still has local product work for no-write-to-applied
application-worker boundaries, weekly persistence, and evaluation/graduation
flows. Live source acquisition, provider-assisted synthesis, ASR/transcription,
workspace proof, qmd/vault/Hermes-home writes, deploy/install/upgrade, Docker
lifecycle, SSH, public bots, and host mutation were not run.

## GAP-033-A Cross-Surface Product Finish Contract

Status: the local cross-surface experience gate is implemented and tested.
`GAP-033` remains open for authorized live `PG-BOTS`, `PG-HERMES`, and
`PG-PROD` proof.

What changed:

- `python/arclink_surface_contract.py`: adds the shared local copy contract for
  audience vocabulary, blocked/proof-gated next actions, proof-gate honesty,
  chat markdown balance, secret-looking value refusal, and raw traceback
  refusal.
- `tests/test_arclink_surface_contract.py`: renders or reads real local
  surfaces for Captain Raven happy/blocked paths, Operator Raven status,
  dashboard provisioning readiness, product surface home, Drive/Code/Terminal
  plugin status, and no-lifecycle deploy readiness copy.
- `python/arclink_product.py`, `python/arclink_public_bots.py`, and
  `python/arclink_product_surface.py`: repair the contract failures found by
  the new gate, replacing stale Captain-facing deployment/user/operator and
  lower-case Agent/Pod wording with ArcPod, Pod, Agent, Captain, Raven, and
  ArcLink support copy.
- `GAPS.md`, `USER_JOURNEY.md`,
  `docs/arclink/sovereign-control-node-symphony.md`,
  `research/COVERAGE_MATRIX.md`, and `IMPLEMENTATION_PLAN.md`: record the
  local source truth without claiming live chat, browser, workspace, deploy, or
  production proof.

Validation:

- Reproduced the missing local gate first:
  `python3 tests/test_arclink_surface_contract.py` failed because the file did
  not exist.
- Focused tests passed:
  `python3 tests/test_arclink_surface_contract.py`,
  `python3 tests/test_arclink_public_bots.py`,
  `python3 tests/test_arclink_product_surface.py`,
  `python3 tests/test_arclink_operator_raven.py`,
  `python3 tests/test_arclink_dashboard.py`, and
  `python3 tests/test_arclink_plugins.py`.
- Compile and web smoke passed:
  `python3 -m py_compile python/arclink_surface_contract.py python/arclink_product.py python/arclink_public_bots.py python/arclink_product_surface.py`
  and `cd web && npm test`.
- Broad no-secret Python suite passed:
  `python3 -m pytest -q tests` with 1342 passed, 6 skipped, 97 warnings in
  65.36s.

Remaining: run authorized representative bot, browser, and workspace proof.
No deploy/install/upgrade, Docker lifecycle, Stripe, provider, public-bot live
delivery, Notion, Cloudflare, Tailscale, SSH fleet, or host mutation was run.

## GAP-031-A Streaming-Safe Router Fallback

Status: the local LLM Router fallback slice is implemented and tested.
`GAP-031` remains open only for authorized live `PG-PROVIDER` overload proof
and any source defects that proof reveals.

What changed:

- `python/arclink_llm_router.py`: adds sanitized fallback attempt audit events,
  pre-streaming fallback retries, explicit no-replay metadata after a stream has
  started, usage/reservation metadata for requested/primary/final models, and
  fallback-aware reservation plus final-model pricing settlement when catalog
  prices are available.
- `python/arclink_control.py`: adds metadata columns for router usage and
  budget reservation rows.
- `tests/test_arclink_llm_router.py`: adds local reproductions for cost-different
  fallback pricing, sanitized attempt audit, and pre-stream fallback metadata.
- `docs/arclink/llm-router.md`, `GAPS.md`, `USER_JOURNEY.md`,
  `docs/arclink/sovereign-control-node-symphony.md`, and
  `IMPLEMENTATION_PLAN.md`: record the local source truth without claiming live
  provider proof.

Validation:

- Baseline reproduction passed before the new tests:
  `python3 tests/test_arclink_llm_router.py` with 18 tests.
- New failure reproduced: the added `GAP-031-A` cases failed on missing router
  metadata columns before the source patch.
- Focused router validation passed after the patch:
  `python3 tests/test_arclink_llm_router.py` with 20 tests.
- Broad no-secret Python suite passed:
  `python3 -m pytest -q tests` with 1340 passed, 6 skipped, 97 warnings.

Remaining: run authorized `PG-PROVIDER` overload proof with redacted evidence.
No live provider calls, deploy/install/upgrade, Docker lifecycle, bots,
payment, SSH, or host mutation were run.

## GAP-034-B Academy Review/Status Integration

Status: the local Academy foundation now has review-only Crew Training,
dashboard, and Operator Raven integration. This does not close `GAP-034`; it
keeps source acquisition, provider generation, workspace application, and data
governance proof gated.

What changed:

- `python/arclink_academy_trainer.py`: added compact Academy review-status
  summaries with source counts, quality summary, application/refresh status,
  next actions, proof gates, and no raw corpus export.
- `python/arclink_crew_recipes.py`: added `stage_crew_academy_review(...)` and
  `crew_academy_status(...)` so a local no-write Academy review can be
  persisted on the active Crew Recipe overlay with audit/event rows.
- `python/arclink_dashboard.py`, `python/arclink_api_auth.py`, and
  `web/src/app/dashboard/page.tsx`: expose Academy Training status in the user
  dashboard, Crew Recipe API, and Crew Training panel.
- `python/arclink_operator_raven.py`: adds read-only Academy status visibility
  through user lookup and `/academy_status <user>` without queueing actions.
- `GAPS.md`, `USER_JOURNEY.md`, Academy/Sovereign docs,
  `research/COVERAGE_MATRIX.md`, and `IMPLEMENTATION_PLAN.md` record the local
  integration while keeping live/policy gates open.

Validation:

- Focused Python tests passed:
  `python3 tests/test_arclink_academy_trainer.py`,
  `python3 tests/test_arclink_crew_recipes.py`,
  `python3 tests/test_arclink_dashboard.py`, and
  `python3 tests/test_arclink_operator_raven.py`.
- Adjacent API/web checks passed:
  `python3 tests/test_arclink_api_auth.py`,
  `python3 tests/test_arclink_hosted_api.py`, `node web/tests/test_page_smoke.mjs`,
  `cd web && npm test -- --runInBand`, `cd web && npm run lint`, and
  `cd web && npm run build`.
- Local browser proof passed: `cd web && npm run test:browser` with 55 passed
  and 3 skipped.
- Compile check passed:
  `python3 -m py_compile python/arclink_academy_trainer.py python/arclink_crew_recipes.py python/arclink_dashboard.py python/arclink_api_auth.py python/arclink_operator_raven.py`.
- Broad no-secret Python suite passed:
  `python3 -m pytest -q tests` with 1338 passed, 6 skipped, 89 warnings.

Remaining: add no-write-to-applied worker boundaries, weekly persistence, and
evaluation/graduation flows only if
`GAP-034` remains the sharpest local row. Live crawling, ASR/transcription,
provider generation, workspace application, qmd/vault/Hermes-home writes,
deploy/install/upgrade, Docker lifecycle, SSH, public bots, and host mutation
were not run.

## GAP-034-A Academy Local Foundation

Status: the first local Academy Trainer slice is implemented and tested. This
does not close `GAP-034`; it creates the safe no-network/no-write foundation
for later product integration and authorized proof.

What changed:

- `python/arclink_academy_trainer.py`: added typed Academy source-lane,
  source, corpus manifest, quality, curriculum, evaluation, application-plan,
  and continuing-education schemas.
- The default Academy registry now names video transcripts, Reddit discussion,
  Wikimedia, GitHub repositories, scholarly/standards sources, web articles,
  skill/tool catalogs, and organization-private material with authorization,
  permission, raw-storage, deletion/tombstone, fake-fixture, and live-proof
  boundaries.
- Local policy validation fails closed for disabled lanes, missing
  license/permission metadata, raw-storage violations, secret-looking metadata,
  unreviewed public skills, deletion/tombstone violations, and live crawling,
  ASR/transcription, or provider-generation requests.
- Fake local sources now produce deterministic corpus manifests, content
  hashes, citation maps, quality records, lesson cards, curriculum/evaluation
  records, no-write SOUL/vault/qmd/memory/skill application plans, and
  continuing-education refresh gates.
- `config/academy-source-lanes.example.json`,
  `tests/test_arclink_academy_trainer.py`, `GAPS.md`, `USER_JOURNEY.md`,
  `docs/arclink/academy-trainer.md`,
  `docs/arclink/sovereign-control-node-symphony.md`,
  `research/COVERAGE_MATRIX.md`, and `IMPLEMENTATION_PLAN.md` record the local
  slice while keeping live and policy gates open.

Validation:

- Pre-edit reproduction: `python3 tests/test_arclink_academy_trainer.py`
  failed because the test/module did not exist.
- Focused Academy validation now passes:
  `python3 tests/test_arclink_academy_trainer.py`.
- Adjacent/focused checks passed:
  `python3 -m py_compile python/arclink_academy_trainer.py`,
  `python3 -m json.tool config/academy-source-lanes.example.json`,
  `python3 tests/test_arclink_crew_recipes.py`,
  `python3 tests/test_memory_synthesizer.py`,
  `python3 tests/test_arclink_mcp_schemas.py`,
  `python3 tests/test_arclink_plugins.py`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check`.
- Broad no-secret Python suite passed:
  `python3 -m pytest -q tests` with 1334 passed, 6 skipped, 89 warnings.

Remaining: connect Academy artifacts into Crew Training, dashboard/Raven, and
review/persistence flows; then run authorized source acquisition,
provider/transcription, and trained-Agent workspace proof before claiming Crew
members are fully Academy-trained. No live proof, deploy/install/upgrade,
Docker lifecycle, systemd, credentialed service, private-state read, SSH,
provider, public bot, Cloudflare, Tailscale, qmd mutation, vault write, or host
mutation was run.

## GAP-030-A Provisioning Readiness Surfaces

Status: the local worker-readiness surface slice is implemented and tested.
This does not close `GAP-030`; it reduces the row to live
`PG-FLEET`/`PG-PROVISION` proof for the chosen worker path.

What changed:

- `python/arclink_dashboard.py`: added
  `control_node_provisioning_readiness(conn, env=...)` and exposed it through
  the admin dashboard read model and scale operations snapshot.
- `python/arclink_operator_raven.py`: Operator Raven `status` now uses the
  shared readiness helper instead of an inline calculation.
- `web/src/app/admin/page.tsx`: admin overview/operator surfaces now render
  provisioning readiness separately from control-plane health and
  action-worker readiness.
- `tests/test_arclink_admin_actions.py`, `tests/test_arclink_dashboard.py`,
  `tests/test_arclink_operator_raven.py`, and `web/tests/test_page_smoke.mjs`:
  prove control-plane-only, blocked no-worker, local-ready, pending-SSH,
  remote-ready, dashboard, Raven, and web copy behavior without live probes.
- `GAPS.md`, `USER_JOURNEY.md`,
  `docs/arclink/sovereign-control-node-symphony.md`,
  `IMPLEMENTATION_PLAN.md`, and `research/BUILD_COMPLETION_NOTES.md`: recorded
  the local slice without claiming live worker proof.

Validation:

- `python3 -m pytest -q tests` passed before the slice:
  1312 passed, 6 skipped, 89 warnings.
- Focused post-slice validation passed:
  `python3 tests/test_arclink_admin_actions.py`,
  `python3 tests/test_arclink_dashboard.py`,
  `python3 tests/test_arclink_operator_raven.py`,
  `python3 -m py_compile python/arclink_dashboard.py python/arclink_operator_raven.py`,
  `(cd web && npm test)`, `(cd web && npm run lint)`, and
  `(cd web && npm run build)`.
- Documentation/hygiene checks passed: `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check`.
- `python3 -m pytest -q tests` passed after the slice:
  1313 passed, 6 skipped, 89 warnings.

Remaining: run authorized `PG-FLEET`/`PG-PROVISION` with a real worker path
before claiming live ArcPod provisioning readiness. No live proof, Docker
lifecycle, deploy/install/upgrade, systemd, credentialed service, private-state
read, SSH, provider, public bot, Cloudflare, Tailscale, or host mutation was
run.

## GAP-029-A Operator Raven Minimal Console

Status: the first local Operator Raven slice is implemented and tested. This
does not close `GAP-029`; it reduces the row from "no shared Operator Raven
command/action layer" to "first read-only/dry-run layer exists."

What changed:

- `python/arclink_operator_raven.py`: new shared parser/dispatcher for
  `status`, `fleet list`, `worker probe --dry-run`, `user lookup`,
  `pod repair --dry-run`, and injected `upgrade check`.
- `python/arclink_curator_onboarding.py`: Telegram operator command menu and
  command routing now include the shared Operator Raven commands while keeping
  existing operator-channel and approval-code checks.
- `python/arclink_curator_discord_onboarding.py`: Discord operator slash/text
  commands now use the shared Operator Raven layer while keeping the configured
  operator-channel gate.
- `tests/test_arclink_operator_raven.py`: proves command parsing, secret-free
  output, no action queueing for dry-run commands, upgrade-check injection, and
  chat adapter authorization boundaries.
- `GAPS.md`, `research/COVERAGE_MATRIX.md`, `IMPLEMENTATION_PLAN.md`, and
  `research/BUILD_COMPLETION_NOTES.md`: recorded the local slice without
  claiming full Operator Raven, live proof, or policy closure.

Validation:

- `python3 tests/test_arclink_operator_raven.py` passed: 5 tests.
- `python3 -m py_compile python/arclink_operator_raven.py python/arclink_curator_onboarding.py python/arclink_curator_discord_onboarding.py` passed.
- `python3 tests/test_arclink_curator_onboarding_regressions.py` passed: 10 tests.
- `python3 tests/test_arclink_enrollment_provisioner_regressions.py` passed: 26 tests.
- `python3 tests/test_arclink_admin_actions.py` passed: 8 tests.
- `python3 tests/test_arclink_fleet.py` passed: 18 tests.
- `python3 tests/test_arclink_upgrade_notifications.py` passed: 9 tests.
- `python3 tests/test_documentation_truths.py` passed: 10 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1312 passed, 6 skipped, 89 warnings.

Remaining: `GAP-029` still needs broader audited action-worker/broker-backed
commands, confirmation policy, runbook coverage, live bot proof where
applicable, and the `GAP-027` Discord authority decision before broad chat
mutation can ship. The next local slice is `GAP-030` readiness surfacing unless
the operator chooses to continue widening Operator Raven read-only coverage
first.

No live proof, Docker lifecycle, deploy/install/upgrade, systemd, credentialed
service, private-state read, or host mutation was run.

## Deployment Mode Viability Audit

Status: the non-Control-Node modes were checked from source. Shared Host Mode
and Shared Host Docker Mode are still viable, first-class paths in code and
docs. `bin/deploy.sh` dispatches all three command families:

- Sovereign Control Node: `./deploy.sh control ...`
- Shared Host: direct commands such as `./deploy.sh install`, `upgrade`,
  `health`, enrollment, Curator setup, and component upgrade commands
- Shared Host Docker: `./deploy.sh docker ...`

Ground truth: Shared Host has active install/upgrade/health code,
systemd-service installers, Curator bootstrap, enrolled-agent realignment, and
the host-mutating `test.sh` / `bin/ci-install-smoke.sh` smoke path. Shared Host
Docker has an actively maintained Compose/supervisor path and extensive Docker
regression coverage. The missing register item was proof ownership, not code
viability.

Handoff edit:

- `README.md`: front-loaded the introduction, lore intro, three-mode breakdown,
  install trace, and day-two management commands so the mode story starts with
  Sovereign Control Node and then distinguishes Shared Host and Shared Host
  Docker.
- `bin/deploy.sh`: clarified the top-level interactive mode menu and made the
  Sovereign Control Node and Shared Host Docker submenus match Shared Host by
  offering Back as well as Exit.
- `tests/test_deploy_regressions.py`: extended menu regression coverage for
  the clearer mode split and submenu return behavior.
- `GAPS.md`: added `GAP-028` and `PG-SHARED-HOST` for fresh Shared Host
  install/enrollment smoke proof.
- `USER_JOURNEY.md`: stated that Shared Host is maintained but currently
  host-proof gated.
- `research/COVERAGE_MATRIX.md`: mapped `GAP-028` to `J-15`, `J-18`, and
  `J-27`.
- `docs/arclink/local-validation.md`: named `./test.sh` /
  `bin/ci-install-smoke.sh` as the `PG-SHARED-HOST` proof path.
- `IMPLEMENTATION_PLAN.md`: routed `GAP-028` to an authorized host-smoke
  window.
- `mission_status.md` and `research/BUILD_COMPLETION_NOTES.md`: recorded this
  audit.

Validation:

- `python3 tests/test_documentation_truths.py` passed: 10 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `bash -n deploy.sh bin/deploy.sh` passed.
- Gap/proof cross-reference check passed: `PG-SHARED-HOST` now has `GAP-028`
  as its owning row, and every `GAP-028` journey joint is represented in the
  coverage matrix.
- `python3 tests/test_deploy_regressions.py` passed: 115 tests.
- `python3 tests/test_health_regressions.py` passed: 20 tests.
- `python3 tests/test_arclink_docker.py` passed: 56 tests.
- `git diff --check` passed.

No live proof, Docker lifecycle, deploy/install/upgrade, systemd, credentialed
service, private-state read, or host mutation was run.

## Journey/Gaps Atlas Consistency Repair

Status: the current `USER_JOURNEY.md`, `GAPS.md`,
`research/COVERAGE_MATRIX.md`, and Ralphie steering paths were rechecked
against source evidence. A full Ralphie atlas restart is not needed. The atlas
is coherent, but two missing explicit handoffs were repaired:

- `GAP-026` now owns `PG-UPGRADE`, which was present in the proof-gate table
  and coverage matrix but had no structured gap row.
- `GAP-027` now records the Discord Curator operator-action authority decision:
  either accept configured operator-channel membership as the approval factor,
  or add second-factor/role allowlist/nonce parity with matching tests.

Handoff edits:

- `GAPS.md`: added `GAP-026` and `GAP-027`, updated planning guidance, policy
  questions, and test-plan handoffs.
- `USER_JOURNEY.md`: added the live upgrade proof callout and the Curator
  operator-authority boundary.
- `research/COVERAGE_MATRIX.md`: linked `GAP-026` and `GAP-027` to the owning
  journey joints.
- `docs/arclink/operations-runbook.md`: named the current Discord
  operator-channel authority model and its unresolved policy boundary.
- `IMPLEMENTATION_PLAN.md`: refreshed the queue so the new rows are routed to
  live proof and policy decision, not unattended local repair.

Validation:

- `python3 tests/test_documentation_truths.py` passed: 10 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- Gap/proof cross-reference check passed: `PG-UPGRADE` now has `GAP-026` as
  its owning row, and `GAP-026`/`GAP-027` are referenced by the journey,
  coverage matrix, plan, and mission status.
- `git diff --check` passed.

No live proof, Docker lifecycle, deploy/install/upgrade, systemd, credentialed
service, private-state read, or host mutation was run.

## Ralphie Plan Refresh: Required-Read Recheck

Status: the required planning inputs were re-read and the current `GAPS.md`
queue remains empty for unattended `LOCAL` repairs. `GAP-025` was checked first
and has not regressed: `python3 -m pytest -q tests` passed with 1305 passed,
6 skipped, and 81 warnings in 64.03s. `GAP-019` remains a P0 trusted-host
residual-risk gate, not a fake-closable local task.

Handoff edit:

- `IMPLEMENTATION_PLAN.md`: refreshed the update marker, current broad-suite
  result, completed planning checklist item, and external-gate routing.

Validation:

- `python3 -m pytest -q tests` passed: 1305 passed, 6 skipped, 81 warnings.
- `python3 tests/test_documentation_truths.py` passed: 10 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'docker_authority_inventory_matches_compose_boundary or docker_docs_cover_socket' --maxfail=5`
  passed: 2 passed, 62 deselected.
- `git diff --check` passed.

Remaining gates after the current atlas repair: authorized live proof for `GAP-001`,
`GAP-002`, `GAP-003`, `GAP-004`, `GAP-005`, `GAP-007`, `GAP-013`,
`GAP-015`, `GAP-018`, `GAP-020`, `GAP-021`, `GAP-022`, `GAP-023`, and
`GAP-026`;
operator/product decisions for `GAP-006`, `GAP-014`, `GAP-017`, and
`GAP-024`, plus Discord Curator operator-action policy for `GAP-027`; and
`GAP-019` residual-risk acceptance, stronger isolation design, or authorized
live alert integration. No live proof, Docker lifecycle, deploy/install/upgrade,
systemd, credentialed service, private-state read, or host mutation was run.

## Ralphie Document Phase: Source Truth Handoff After Lint Repair

Status: document phase is complete for the current unattended pass. The only
new local blocker found during the lint phase was repaired in
`python/arclink_rejection_incidents.py`; `GAP-025` remains locally closed by
the broad no-secret Python suite, and the current `GAPS.md` queue has no
bounded unattended `LOCAL` row.

Handoff edits:

- `IMPLEMENTATION_PLAN.md`: refreshed the current repair status after the lint
  repair and kept the queue routed to external proof, policy, and residual-risk
  handoffs.
- `mission_status.md`: added this document-phase closeout.
- `research/BUILD_COMPLETION_NOTES.md`: added the matching resumable handoff
  note.
- `GAPS.md`: inspected and left unchanged for this document phase because no
  row's source/test/proof status changed beyond the already-recorded
  `GAP-025` lint repair evidence.
- `USER_JOURNEY.md`: inspected and left unchanged because the user journey did
  not change.

Validation:

- `python3 tests/test_documentation_truths.py` passed: 10 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'docker_authority_inventory_matches_compose_boundary or docker_docs_cover_socket' --maxfail=5`
  passed: 2 passed, 62 deselected.
- `git diff --check` passed.

Remaining gates are external handoffs, not unattended local blockers:
`GAP-001`, `GAP-002`, `GAP-003`, `GAP-004`, `GAP-005`, `GAP-007`,
`GAP-013`, `GAP-015`, `GAP-018`, `GAP-020`, `GAP-021`, `GAP-022`, and
`GAP-023` need authorized live proof; `GAP-006`, `GAP-014`, `GAP-017`, and
`GAP-024` need operator/product policy decisions; `GAP-019` needs
residual-risk acceptance, stronger isolation, or authorized live alert
integration. No live proof, Docker lifecycle, deploy/install/upgrade, systemd,
credentialed service, private-state read, or host mutation was run.

## Ralphie Lint Phase: Adversarial Buildout Review

Status: one unattended local blocker was found and repaired before the slice
advanced. The broad no-secret Python suite initially failed because
`agent-process-helper` rejected a symlinked Docker agent home root but did not
write the expected redacted rejection incident when only `ARCLINK_PRIV_DIR` was
configured. `python/arclink_rejection_incidents.py` now accepts any configured
safe private-state root and still rejects disagreement between multiple roots.

The lint pass also rejected a stale generated stack snapshot that classified
ArcLink as primarily Node.js. `research/STACK_SNAPSHOT.md` is restored to the
actual Python control plane, shell orchestration, and Docker Compose stack
shape.

Validation:

- `python3 -m pytest -q tests/test_arclink_docker.py::test_agent_helpers_reject_symlinked_home_root_before_root_work --maxfail=1`
  passed: 1 passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_helpers_reject_symlinked_home_root_before_root_work or agent_process_helper_records_redacted_rejection_incident_before_subprocess or agent_process_helper_rejects_configured_root_mismatch' --maxfail=5`
  passed: 3 passed, 61 deselected.
- `python3 -m py_compile python/arclink_rejection_incidents.py python/arclink_agent_process_helper.py` passed.
- `python3 tests/test_documentation_truths.py` passed: 10 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `python3 -m compileall -q python plugins/hermes-agent/arclink-managed-context plugins/hermes-agent/code/dashboard plugins/hermes-agent/drive/dashboard` passed.
- `npm test`, `npm run lint`, and `npm run build` passed in `web/`.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1305 passed, 6 skipped, and
  81 warnings in 64.08s.

No live proof, Docker lifecycle, deploy/install/upgrade, systemd, credentialed
service, private-state read, or host mutation was run. Remaining open rows are
external proof, policy decision, or residual-risk handoff items, not
unattended local blockers.

## Ralphie Plan Phase Build-Gate Repair: Explicit Plan Contract

Status: plan gate contract repaired. `GAP-025` was rechecked first and the
broad no-secret Python suite still passed, so no regression-driven local repair
was selected. The current `GAPS.md` queue still has no bounded unattended
`LOCAL` row; remaining work is live proof, policy decisions, or `GAP-019`
residual-risk handling.

Handoff edits:

- `IMPLEMENTATION_PLAN.md`: added explicit `Goal` and
  `Acceptance Criteria/Validation` sections, kept the current queue buckets,
  and preserved concrete owner surface, files, reproduction command, and
  success criteria for the documentation/handoff slice.
- `mission_status.md`: recorded this build-gate repair note.
- `research/BUILD_COMPLETION_NOTES.md`: recorded the same retry evidence and
  remaining gates.

Validation:

- `python3 -m pytest -q tests` passed: 1305 passed, 6 skipped, and
  81 warnings in 64.67s.
- `python3 tests/test_documentation_truths.py` passed: 10 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'docker_authority_inventory_matches_compose_boundary or docker_docs_cover_socket' --maxfail=5`
  passed: 2 passed, 62 deselected.
- `git diff --check` passed.

No live proof, Docker lifecycle, deploy/install/upgrade, systemd, credentialed
service, private-state read, or host mutation was run.

## Ralphie Document Phase Retry 2 Closeout: External Gates Handoff Confirmed

Status: document phase is complete for the current unattended pass. The
`GAPS.md` queue still has no bounded unattended `LOCAL` repair row. `GAP-025`
remains locally closed while the broad no-secret Python suite stays green, and
`GAP-019` remains open as a trusted-host residual-risk gate instead of a
fake-closed local task.

Handoff edits:

- `IMPLEMENTATION_PLAN.md`: marked the document-phase closeout tasks complete
  and routed the plan to external handoffs.
- `mission_status.md`: added this closeout entry.
- `research/BUILD_COMPLETION_NOTES.md`: added the document-phase note with
  files, commands, and remaining gates.
- `GAPS.md`: unchanged in this closeout because no row's source, test, or proof
  status changed after the existing `GAP-019` residual-risk reroute.
- `USER_JOURNEY.md`: unchanged because the user journey did not change.

Document closeout validation:

- `python3 tests/test_documentation_truths.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'docker_authority_inventory_matches_compose_boundary or docker_docs_cover_socket' --maxfail=5`
  passed: 2 passed, 62 deselected.
- `git diff --check` passed.

Remaining gates are external handoffs, not unattended local blockers:
`GAP-001`, `GAP-002`, `GAP-003`, `GAP-004`, `GAP-005`, `GAP-007`,
`GAP-013`, `GAP-015`, `GAP-018`, `GAP-020`, `GAP-021`, `GAP-022`, and
`GAP-023` need authorized live proof; `GAP-006`, `GAP-014`, `GAP-017`, and
`GAP-024` need operator/product policy decisions; `GAP-019` needs
residual-risk acceptance, stronger isolation, or authorized live alert
integration. No live proof, Docker lifecycle, deploy/install/upgrade, systemd,
credentialed service, private-state read, or host mutation was run.

## Ralphie Plan Retry 2: Empty Local Queue Route Confirmed

Status: plan retry re-read the required ArcLink steering, journey, gaps,
implementation plan, and coverage docs. The current `GAPS.md` queue still has
no bounded unattended `LOCAL` repair row. `GAP-025` remains `real` unless the
broad no-secret Python suite regresses, and `GAP-019` remains open as a P0
trusted-host residual-risk gate rather than a fake-closable local task.

The next phase route is `document`: refresh or confirm the operator handoff
artifacts, then rerun the focused documentation/hygiene/inventory validation.
No deploy/install/upgrade, Docker lifecycle, systemd, live proof, credentialed
external service, private-state read, or host mutation is planned for this
unattended pass.

Retry 2 validation:

- `python3 -m pytest -q tests` passed: 1305 passed, 6 skipped, and
  81 warnings in 64.30s.
- `python3 tests/test_documentation_truths.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'docker_authority_inventory_matches_compose_boundary or docker_docs_cover_socket' --maxfail=5`
  passed: 2 passed, 62 deselected in 0.05s.
- `git diff --check` passed.

## Ralphie Document Phase: External Gates And GAP-019 Residual-Risk Handoff

Status: the unattended local repair queue is empty. `GAP-025` remains locally
closed by the current broad no-secret Python suite recheck (`1305 passed,
6 skipped, 81 warnings in 63.85s`), and no live proof, policy decision, or
residual-risk acceptance was performed in this document phase.
`GAP-019` stays open as a trusted-host Docker socket/root boundary; the current
source inventory identifies residual authority that needs an operator
residual-risk decision, an explicitly authorized stronger isolation design, or
authorized live alert integration rather than an already-scoped unattended
helper split.

Handoff edits:

- `GAPS.md`: updated only `GAP-019` next-repair routing to remove the stale
  implication that a named local command-specific helper split remains.
- `IMPLEMENTATION_PLAN.md`: marked the document-phase checklist complete and
  kept `LOCAL` empty while preserving the live-proof, policy, and residual-risk
  buckets.
- `research/BUILD_COMPLETION_NOTES.md`: added this handoff slice with files,
  commands, and remaining gates.
- `USER_JOURNEY.md`: intentionally unchanged because the user journey did not
  change.

Document-phase validation:

- `python3 -m pytest -q tests` passed: 1305 passed, 6 skipped, and
  81 warnings in 63.85s.
- `python3 tests/test_documentation_truths.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'docker_authority_inventory_matches_compose_boundary or docker_docs_cover_socket' --maxfail=5`
  passed: 2 passed, 62 deselected in 0.05s.
- `git diff --check` passed.

Remaining gates are external handoffs, not unattended local blockers:
`GAP-001`, `GAP-002`, `GAP-003`, `GAP-004`, `GAP-005`, `GAP-007`,
`GAP-013`, `GAP-015`, `GAP-018`, `GAP-020`, `GAP-021`, `GAP-022`, and
`GAP-023` need authorized live proof; `GAP-006`, `GAP-014`, `GAP-017`, and
`GAP-024` need operator/product policy decisions before proof or code claims;
`GAP-019` needs residual-risk acceptance, stronger isolation, or authorized
alert integration. This pass did not run Docker lifecycle/mutation, systemd,
deploy/install/upgrade, live services, credentials, private-state reads, or
host mutation.

## Ralphie Dream Buildout: GAP-019-BD Remaining Broker/Helper Rejection Incidents

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-BD` reduces the Docker/root
trusted-host boundary without closing the residual-risk decision. The remaining
high-authority lanes now record redacted rejected-request incidents for
validation failures: `deployment-exec-broker`,
`migration-capture-helper`, `agent-user-helper`,
`agent-supervisor-broker`, and `operator-upgrade-broker`.

Incident rows are written only under scoped safe roots:
`ARCLINK_STATE_ROOT_BASE/_broker-incidents/deployment-exec-broker/rejections.jsonl`,
`ARCLINK_STATE_ROOT_BASE/_helper-incidents/migration-capture-helper/rejections.jsonl`,
`ARCLINK_DOCKER_AGENT_HOME_ROOT/.helper-incidents/agent-user-helper/rejections.jsonl`,
`ARCLINK_DOCKER_CONTAINER_PRIV_DIR/state/docker/agent-supervisor-broker/rejections.jsonl`,
and
`ARCLINK_DOCKER_HOST_PRIV_DIR/state/docker/operator-upgrade-broker/rejections.jsonl`.
Rows include service/event, trusted-host acknowledgement state, error class,
sanitized reason/message, and safe identifiers when available. They omit raw
request bodies, command arrays, process args, payload values, private paths,
tokens, chat ids, user ids, message text, secret-looking values, and stack
traces. Unsafe incident roots do not fall back elsewhere.

Current local evidence for this slice:

- `python3 -m py_compile python/arclink_rejection_incidents.py python/arclink_deployment_exec_broker.py python/arclink_migration_capture_helper.py python/arclink_agent_user_helper.py python/arclink_agent_supervisor_broker.py python/arclink_operator_upgrade_broker.py`
  passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k remaining_high_authority_services_record_redacted_rejection_incidents --maxfail=1`
  passed: 1 passed.
- `python3 -m json.tool config/docker-authority-inventory.json` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'remaining_high_authority_services_record_redacted_rejection_incidents or docker_authority_inventory_matches_compose_boundary' --maxfail=2`
  passed: 2 passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'remaining_high_authority_services_record_redacted_rejection_incidents or deployment_exec_broker or migration_capture_helper or agent_user_helper or agent_supervisor_broker or operator_upgrade_broker or docker_authority_inventory or docker_docs_cover_socket or compose_defines_full_stack_services' --maxfail=10`
  passed: 23 passed.
- `python3 -m pytest -q tests/test_arclink_executor.py -k deployment_exec_broker --maxfail=5`
  passed: 3 passed.
- `python3 -m pytest -q tests/test_arclink_pod_migration.py -k migration_capture_helper --maxfail=5`
  passed: 2 passed.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20`
  passed: 64 passed.
- `python3 tests/test_documentation_truths.py` passed: 10 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1305 passed, 6 skipped, and
  81 warnings in 64.22s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, private-state reads, or host mutation. `GAP-019`
remains open for stronger helper/broker isolation, alert integration, or an
operator residual-risk decision for the trusted-host Docker socket/root
boundary.

## Ralphie Dream Buildout: GAP-019-BC Gateway Exec Broker Rejection Incidents

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-BC` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `gateway-exec-broker` now records redacted
rejected-request incidents at
`ARCLINK_STATE_ROOT_BASE/_broker-incidents/gateway-exec-broker/rejections.jsonl`
when the configured deployment state root is absolute, non-root, existing, and
non-symlinked. Rows include safe deployment id and generated project name when
available, trusted-host acknowledgement state, error class, and sanitized
reason/message; they omit raw request bodies, bridge payload values, bot
tokens, chat ids, user ids, message text, process args, rendered config paths,
private paths, and stack traces.

Pre-repair reproduction used a temp deployment state root and an unsafe raw
`cmd` request. Before the repair, `run_gateway_exec_request()` returned
`gateway exec broker does not accept raw commands` and no
`_broker-incidents/gateway-exec-broker/rejections.jsonl` file existed. After
adding the focused regression, the old code failed because rejected gateway
broker requests did not create a deployment-state incident log.

Current local evidence for this slice:

- `python3 -m pytest -q tests/test_arclink_notification_delivery.py -k 'gateway_exec_broker_records_redacted_rejection_incident_before_subprocess' --maxfail=1`
  passed: 1 passed, 23 deselected.
- `python3 -m pytest -q tests/test_arclink_notification_delivery.py -k 'gateway_exec_broker_records_redacted_rejection_incident_before_subprocess or gateway_exec_broker_rejects_raw_commands_and_builds_vetted_exec or gateway_exec_broker_rejects_symlinked_compose_fallback_config_before_docker or public_agent_bridge_command_validator or public_agent_gateway_turn_uses_gateway_exec_broker_when_configured or public_agent_bridge_worker_uses_gateway_exec_broker_request_jobs' --maxfail=10`
  passed: 6 passed, 18 deselected.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null` and
  `python3 -m pytest -q tests/test_arclink_docker.py -k 'gateway_exec_broker or docker_authority_inventory or docker_docs_cover_socket' --maxfail=10`
  passed: 4 passed, 59 deselected.
- `python3 -m py_compile python/arclink_gateway_exec_broker.py python/arclink_notification_delivery.py`
  passed.
- `python3 -m pytest -q tests/test_arclink_notification_delivery.py tests/test_arclink_public_bots.py tests/test_arclink_telegram.py tests/test_arclink_discord.py tests/test_arclink_docker.py --maxfail=20`
  passed: 147 passed.
- `python3 tests/test_documentation_truths.py`, `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1304 passed, 6 skipped, and
  81 warnings in 63.51s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, private-state reads, or host mutation. `GAP-019`
remains open for stronger helper/broker isolation, alert integration, or an
operator residual-risk decision for the trusted-host Docker socket/root
boundary.

## Ralphie Dream Buildout: GAP-019-BB Agent Process Helper Rejection Incidents

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-BB` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `agent-process-helper` now records redacted
rejected-request incidents at
`state/docker/agent-process-helper/rejections.jsonl` when the configured
private root is safe. The incident rows include only safe metadata such as
operation, safe agent id when present, trusted-host acknowledgement state, error
class, and sanitized reason/message; they omit raw request bodies, env values,
process args, private paths, tokens, and stack traces.

Pre-repair reproduction used a temp private state root and an unsafe raw
`cmd` request. Before the repair, `run_agent_process_helper_request()` returned
`agent process helper does not accept raw commands` and no
`rejections.jsonl` file existed. After adding the focused regression, the old
code failed because rejected helper requests did not create a private-state
incident log.

Current local evidence for this slice:

- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_process_helper_records_redacted_rejection_incident_before_subprocess' --maxfail=1`
  passed: 1 passed, 62 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_process_helper_records_redacted_rejection_incident_before_subprocess or agent_process_helper_rejects_raw_commands_and_runs_allowlisted_agent_ops or agent_process_helper_rejects_unapproved_agent_env_keys_before_subprocess or agent_process_helper_rejects_unsafe_dashboard_backend_host_before_subprocess or agent_process_helper_rejects_configured_root_mismatch or agent_process_helper_rejects_symlinked_configured_roots_before_work or agent_process_helper_rejects_symlink_escaped_log_directory or agent_process_helper_does_not_log_or_argv_env_values or docker_authority_inventory or docker_docs_cover_socket' --maxfail=10`
  passed: 10 passed, 53 deselected.
- `python3 -m py_compile python/arclink_agent_process_helper.py python/arclink_docker_agent_supervisor.py`
  passed.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_enrollment_provisioner_regressions.py tests/test_arclink_agent_user_services.py --maxfail=20`
  passed: 93 passed.
- `python3 tests/test_documentation_truths.py`, `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1303 passed, 6 skipped, and
  81 warnings in 63.59s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, private-state reads, or host mutation. `GAP-019`
remains open for stronger helper/broker isolation, alert integration, or an
operator residual-risk decision for the trusted-host Docker socket/root
boundary.

## Ralphie Dream Buildout: GAP-019-BA Agent User Helper Assignment-File Preflight

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-BA` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `agent-user-helper` now validates
`.arclink-user-ids.json` and `.arclink-user-ids.json.tmp` under the Docker
agent-home root as canonical non-symlink regular-or-missing files before
uid/gid assignment reads or writes, account commands, agent-home directory
creation, or recursive chown. Assignment writes use an exclusive no-follow temp
file create before `os.replace`.

Pre-repair reproduction used a temp Docker agent-home root with
`.arclink-user-ids.json.tmp` symlinked to a file outside the home root. Before
the repair, the helper returned success, modified the outside file, created the
agent home, and reached fake root account/ownership commands. After adding the
focused regression, the old code failed with `tmp-symlink` returning a success
payload.

Current local evidence for this slice:

- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_user_helper_rejects_symlinked_uid_assignment_files_before_root_work' --maxfail=1`
  passed: 1 passed, 61 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_user_helper_rejects_symlinked_uid_assignment_files_before_root_work or agent_user_helper_rejects_raw_commands_and_unscoped_paths or agent_user_helper_requires_trusted_absolute_root_executables or agent_user_helper_rejects_configured_home_root_mismatch or agent_helpers_reject_symlink_escaped_agent_paths or agent_helpers_reject_symlinked_home_root_before_root_work or agent_user_helper_root_boundary_uses_explicit_minimum_capabilities or docker_authority_inventory or docker_docs_cover_socket' --maxfail=10`
  passed: 9 passed, 53 deselected.
- `python3 -m py_compile python/arclink_agent_user_helper.py python/arclink_docker_agent_supervisor.py`
  passed.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_enrollment_provisioner_regressions.py tests/test_arclink_agent_user_services.py --maxfail=20`
  passed: 92 passed.
- `python3 tests/test_documentation_truths.py`, `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1302 passed, 6 skipped, and
  81 warnings in 64.00s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, private-state reads, or host mutation. `GAP-019`
remains open for stronger helper/broker isolation, alert integration, or an
operator residual-risk decision for the trusted-host Docker socket/root
boundary.

## Ralphie Dream Buildout: GAP-019-AZ Agent Supervisor Broker Private Bind-Root Preflight

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-AZ` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `agent-supervisor-broker` now validates
`ARCLINK_DOCKER_HOST_PRIV_DIR` and `ARCLINK_DOCKER_CONTAINER_PRIV_DIR` as
canonical ArcLink private bind roots before proxy config hashing, Docker CLI
lookup, container inspect, `docker run -v`, or a successful dashboard proxy
broker response.

Pre-repair reproduction first showed the focused AZ selector had no coverage.
After adding the regression, the broker failed the new contract before source
repair; the unsafe bind-root cases are now rejected with a redacted broker
error and the test fails if Docker lookup or subprocess dispatch is reached.

Current local evidence for this slice:

- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_supervisor_broker_rejects_unsafe_private_bind_roots_before_dashboard_proxy' --maxfail=1`
  passed: 1 passed, 60 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_supervisor_broker_rejects_unsafe_private_bind_roots or agent_supervisor_broker_rejects_raw_commands_and_builds_dashboard_proxy or agent_supervisor_broker_rejects_unsafe_dashboard_backend_host or agent_supervisor_broker_rejects_unsafe_docker_binary or docker_authority_inventory or docker_docs_cover_socket' --maxfail=10`
  passed: 6 passed, 55 deselected.
- `python3 -m py_compile python/arclink_agent_supervisor_broker.py python/arclink_docker_agent_supervisor.py`
  passed.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_dashboard.py tests/test_arclink_plugins.py --maxfail=20`
  passed: 107 passed.
- `python3 tests/test_documentation_truths.py`, `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1301 passed, 6 skipped, and
  81 warnings in 63.88s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, private-state reads, or host mutation. `GAP-019`
remains open for stronger helper/broker isolation, alert integration, or an
operator residual-risk decision for the trusted-host Docker socket/root
boundary.

## Ralphie Dream Buildout: GAP-019-AY Gateway Exec Broker Fallback Config-File Preflight

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-AY` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `gateway-exec-broker` now validates the Compose
fallback deployment root, config directory, `config/arclink.env`, and
`config/compose.yaml`: roots must be non-symlink directories, and config files
must be non-symlink regular readable files before fallback command dispatch or
a successful public Agent gateway broker response.

Pre-repair reproduction used a local probe against `_build_gateway_exec_command`.
Before the repair, `arcdep_test/config/arclink.env` and
`arcdep_test/config/compose.yaml` symlinked into another state-root deployment
config reached `docker compose exec` command construction and printed
`UNSAFE_ALLOWED`.

Current local evidence for this slice:

- `python3 -m pytest -q tests/test_arclink_notification_delivery.py -k 'gateway_exec_broker_rejects_symlinked_compose_fallback_config_before_docker' --maxfail=1`
  passed: 1 passed, 22 deselected.
- `python3 -m pytest -q tests/test_arclink_notification_delivery.py -k 'gateway_exec_broker or public_agent_bridge_command_validator' --maxfail=10`
  passed: 5 passed, 18 deselected.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null` and
  `python3 -m pytest -q tests/test_arclink_docker.py -k 'gateway_exec_broker or docker_authority_inventory' --maxfail=10`
  passed: 3 passed, 57 deselected.
- `python3 -m py_compile python/arclink_gateway_exec_broker.py python/arclink_notification_delivery.py`
  passed.
- `python3 -m pytest -q tests/test_arclink_notification_delivery.py tests/test_arclink_docker.py tests/test_arclink_public_bots.py tests/test_arclink_telegram.py tests/test_arclink_discord.py --maxfail=20`
  passed: 143 passed.
- `python3 tests/test_documentation_truths.py`, `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1300 passed, 6 skipped, and
  81 warnings in 63.86s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, private-state reads, or host mutation. `GAP-019`
remains open for stronger helper/broker isolation, alert integration, or an
operator residual-risk decision for the trusted-host Docker socket/root
boundary.

## Ralphie Dream Buildout: GAP-019-AX Deployment Exec Broker Config-File Preflight

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-AX` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `deployment-exec-broker` now validates the original
request paths for the rendered deployment root, config root,
`config/arclink.env`, and `config/compose.yaml`: roots must be non-symlink
directories, and config files must be non-symlink regular readable files before
Docker CLI lookup, runner construction, or Compose subprocess dispatch.

Pre-repair reproduction added the symlinked rendered-config regression. Before
the repair, a request for `dep-one/config/arclink.env` and
`dep-one/config/compose.yaml` symlinked into `dep-one-steered/config` reached
the broker's Docker CLI lookup and failed the test with `Docker CLI lookup must
not run for symlinked deployment config files`.

Current local evidence for this slice:

- Initial focused selector confirmed missing coverage: 39 deselected.
- `python3 -m pytest -q tests/test_arclink_executor.py -k 'deployment_exec_broker_rejects_symlinked_compose_config_files_before_docker' --maxfail=1`
  failed before repair, then passed: 1 passed, 39 deselected.
- `python3 -m pytest -q tests/test_arclink_executor.py -k 'deployment_exec_broker' --maxfail=10`
  passed: 3 passed, 37 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'deployment_exec_broker or docker_authority_inventory' --maxfail=10`
  passed: 3 passed, 57 deselected.
- `python3 -m py_compile python/arclink_deployment_exec_broker.py python/arclink_executor.py`
  passed.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`
  passed.
- `python3 -m pytest -q tests/test_arclink_executor.py tests/test_arclink_docker.py tests/test_arclink_provisioning.py tests/test_arclink_sovereign_worker.py --maxfail=20`
  passed: 133 passed.
- `python3 tests/test_documentation_truths.py`, `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1299 passed, 6 skipped, and
  81 warnings in 63.66s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, private-state reads, or host mutation. `GAP-019`
remains open for stronger helper/broker isolation, alert integration, or an
operator residual-risk decision for the trusted-host Docker socket/root
boundary.

## Ralphie Dream Buildout: GAP-019-AW Operator Upgrade Broker Upstream Deploy-Key Path Confinement

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-AW` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `operator-upgrade-broker` now confines non-empty
request-supplied `ARCLINK_UPSTREAM_DEPLOY_KEY_PATH` and
`ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE` values to absolute non-symlink paths under
`ARCLINK_DOCKER_HOST_PRIV_DIR` before child env construction, private operator
logs, `_run_logged_command`, or `subprocess.run`.

Pre-repair reproduction added the upstream path-steering regression. Before the
repair, a temp queued upgrade request with an outside
`ARCLINK_UPSTREAM_DEPLOY_KEY_PATH` returned success and reached the mocked
subprocess path: `outside upstream deploy key: {'returncode': 0}`.

Current local evidence for this slice:

- Initial focused selector confirmed missing coverage: 59 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'operator_upgrade_broker_rejects_unscoped_upstream_deploy_key_paths_before_log_or_subprocess' --maxfail=1`
  failed before repair, then passed: 1 passed, 59 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'operator_upgrade_broker and not live' --maxfail=10`
  passed: 6 passed, 54 deselected.
- `python3 -m py_compile python/arclink_operator_upgrade_broker.py` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'operator_upgrade_broker or docker_authority_inventory_matches_compose_boundary' --maxfail=10`
  passed: 7 passed, 53 deselected.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`
  passed.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_deploy_regressions.py tests/test_arclink_enrollment_provisioner_regressions.py --maxfail=20`
  passed: 203 passed.
- `python3 tests/test_documentation_truths.py`, `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1298 passed, 6 skipped, and
  81 warnings in 64.39s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, private-state reads, or host mutation. `GAP-019`
remains open for stronger helper/broker isolation, alert integration, or an
operator residual-risk decision for the trusted-host Docker socket/root
boundary.

## Ralphie Dream Buildout: GAP-019-AV Operator Upgrade Broker Fixed Script Target Preflight

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-AV` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `operator-upgrade-broker` now preflights the fixed
repo script targets for queued Docker-mode operator upgrades: `deploy.sh` and
`bin/component-upgrade.sh` must be exact non-symlink regular readable files
with executable bits before private operator logs, `_run_logged_command`, or
`subprocess.run`.

Pre-repair reproduction used a temp repo with `deploy.sh` symlinked to another
repo file. Before the repair, the broker returned success, resolved the symlink
target into the mocked subprocess call, and created the private operator log.
The focused regression then failed with `symlinked deploy.sh: {'returncode': 0}`.

Current local evidence for this slice:

- `python3 -m pytest -q tests/test_arclink_docker.py -k 'operator_upgrade_broker_rejects_symlinked_or_non_executable_repo_scripts_before_subprocess' --maxfail=1`
  passed: 1 passed, 58 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'operator_upgrade_broker and not live' --maxfail=10`
  passed: 5 passed, 54 deselected.
- `python3 -m py_compile python/arclink_operator_upgrade_broker.py` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'operator_upgrade_broker or docker_authority_inventory_matches_compose_boundary' --maxfail=10`
  passed: 6 passed, 53 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_enrollment_provisioner_regressions.py --maxfail=20`
  passed: 85 passed.
- `python3 tests/test_documentation_truths.py`, `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1297 passed, 6 skipped, and
  81 warnings in 63.76s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, private-state reads, or host mutation. `GAP-019`
remains open for stronger helper/broker isolation, alert integration, or an
operator residual-risk decision for the trusted-host Docker socket/root
boundary.

## Ralphie Dream Buildout: GAP-019-AU Process Helper Fixed Command Target Preflight

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-AU` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `agent-process-helper` now preflights fixed repo
command targets for install, identity, refresh, cron, gateway, and dashboard
operations before helper log creation or subprocess dispatch. Missing,
symlinked, directory, unreadable, or non-executable shell targets fail closed;
the identity setup Python target must be a canonical, readable repo-child file.

Pre-repair reproduction used a temp repo with no `bin/user-agent-refresh.sh`.
Before the repair, `agent-process-helper` returned success, reached the mocked
`subprocess.run` path, and created a helper log for the missing target.

Current local evidence for this slice:

- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_process_helper_rejects_symlinked_or_missing_repo_command_targets_before_subprocess' --maxfail=1`
  passed: 1 passed, 57 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_process_helper and not live' --maxfail=10`
  passed: 10 passed, 48 deselected.
- `python3 -m py_compile python/arclink_agent_process_helper.py` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  58 passed.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_enrollment_provisioner_regressions.py --maxfail=20`
  passed: 84 passed.
- `python3 tests/test_documentation_truths.py`, `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1296 passed, 6 skipped, and
  81 warnings in 63.38s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, private-state reads, or host mutation. `GAP-019`
remains open for stronger helper/broker isolation, alert integration, or an
operator residual-risk decision for the trusted-host Docker socket/root
boundary.

## Ralphie Dream Buildout: GAP-014-C Hosted Request Share Broker

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-014` is further reduced but not closed. Drive and Code now send
deployment-scoped broker payloads to `/api/v1/user/share-grants/broker`; the
hosted broker accepts them without a browser session only when
`X-ArcLink-Share-Request-Broker-Token` matches the owner deployment's stored
token hash. Control-node provisioning mounts the broker token as an ArcPod
runtime secret, and the sovereign worker stores only the hash in deployment
metadata.

Pre-repair reproduction added the hosted API broker regression and it failed
with `404` for `/api/v1/user/share-grants/broker`, while the browser
`POST /user/share-grants` route still rejected token-only requests with `401`.

Current local evidence for this slice:

- `python3 -m pytest -q tests/test_arclink_hosted_api.py -k 'share_grant_broker or share_grants' --maxfail=10`
  passed: 3 passed, 84 deselected.
- `python3 -m pytest -q tests/test_arclink_plugins.py -k 'share_request_broker_auth or drive_code_share_request_broker_contract or share_link_creation or linked_root' --maxfail=10`
  passed: 2 passed, 33 deselected.
- `python3 -m pytest -q tests/test_arclink_provisioning.py tests/test_arclink_sovereign_worker.py -k 'dry_run_renders_full_service_dns_access_intent or fake_sovereign_worker_applies_ready_deployment' --maxfail=10`
  passed: 2 passed, 31 deselected.
- `python3 -m pytest -q tests/test_arclink_hosted_api.py tests/test_arclink_plugins.py tests/test_arclink_provisioning.py tests/test_arclink_sovereign_worker.py --maxfail=20`
  passed: 155 passed.
- `python3 tests/test_documentation_truths.py`, `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1295 passed, 6 skipped, and
  81 warnings in 63.99s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, private-state reads, or host mutation. `GAP-014`
remains open for production workspace/browser proof, live Telegram/Discord
delivery and callbacks, live audit/revoke proof from the browser path, and any
operator decision to add or replace this with a Nextcloud-backed adapter.

## Ralphie Dream Buildout: GAP-014-B Authenticated Drive/Code Request Share Handoff

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-014` is further reduced but not closed. Drive and Code no longer enable
`share_request` from a broker URL alone. Writable Vault/Workspace roots expose
`Request Share` only when a share-request broker URL and broker-token file are
configured, and dispatch sends that token only as the
`X-ArcLink-Share-Request-Broker-Token` header. Status and route responses do
not return broker auth material.

Pre-repair reproduction used the focused plugin selector after adding the
broker-auth regression. Before the source repair, Drive reported
`share_request.enabled=true` with only `ARCLINK_SHARE_REQUEST_BROKER_URL`
configured, proving URL-only broker enablement.

Current local evidence for this slice:

- `python3 -m pytest -q tests/test_arclink_plugins.py -k 'share_request_broker_auth or drive_code_share_request_broker_contract or share_link_creation or linked_root' --maxfail=10`
  passed: 2 passed, 33 deselected.
- `python3 -m pytest -q tests/test_arclink_plugins.py --maxfail=20` passed:
  35 passed.
- `python3 -m py_compile plugins/hermes-agent/drive/dashboard/plugin_api.py plugins/hermes-agent/code/dashboard/plugin_api.py`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1294 passed, 6 skipped, and
  81 warnings in 63.55s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, private-state reads, or host mutation. `GAP-014`
remains open for the production browser broker/adapter implementation, live
Telegram/Discord delivery proof, audit/revoke proof from the browser path, and
the operator decision between native ArcLink broker and approved
Nextcloud-backed adapter.

## Ralphie Dream Buildout: GAP-014-A Drive/Code Request Share Contract

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-014` is reduced but not closed. Drive and Code now expose a local
fail-closed `Request Share` browser contract: status reports a
`share_request` capability disabled by default, writable Vault/Workspace roots
enable it only when an explicit share-request broker URL is configured,
`/share/request` rejects missing recipients, `Linked` roots, sensitive paths,
and unconfigured brokers before dispatch, and the browser bundles continue to
omit direct "Generate share link" / "Create share link" wording.

Pre-repair reproduction used a focused local module probe and the new pytest
selector. Before the repair, Drive status had no `share_request` capability and
the focused regression failed on missing `share_request` status state.

Current local evidence for this slice:

- `python3 -m pytest -q tests/test_arclink_plugins.py -k 'drive_code_share_request_broker_contract or share_link_creation or linked_root' --maxfail=10`
  passed: 2 passed, 33 deselected.
- `python3 -m pytest -q tests/test_arclink_hosted_api.py -k 'share_grant' --maxfail=10`
  passed: 4 passed, 82 deselected.
- `python3 -m pytest -q tests/test_arclink_plugins.py tests/test_arclink_hosted_api.py tests/test_arclink_dashboard.py tests/test_arclink_mcp_schemas.py --maxfail=20`
  passed: 143 passed.
- `node --test web/tests/test_api_client.mjs --test-name-pattern 'share'`
  passed: 49 tests.
- `node --test web/tests/test_page_smoke.mjs --test-name-pattern 'share|Linked'`
  passed: 26 tests.
- `python3 -m py_compile plugins/hermes-agent/drive/dashboard/plugin_api.py plugins/hermes-agent/code/dashboard/plugin_api.py`,
  `node --check` for the Drive and Code dashboard bundles,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1294 passed, 6 skipped, and
  81 warnings in 63.93s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, private-state reads, or host mutation. `GAP-014`
remains open for authenticated browser broker/adapter implementation, live
Telegram/Discord delivery proof, audit/revoke proof from the browser path, and
the operator decision between native ArcLink broker and approved
Nextcloud-backed adapter.

## Ralphie Dream Buildout: GAP-019-AT Process Helper Configured-Root Symlink Rejection

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-AT` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `agent-process-helper` now rejects symlinked
configured or requested repo, private-state, state, and runtime roots,
including `ARCLINK_REPO_DIR`, `ARCLINK_PRIV_DIR`,
`ARCLINK_DOCKER_CONTAINER_PRIV_DIR`, request `state_dir`, and `RUNTIME_DIR`,
before helper log creation, cwd/command/runtime lookup, `subprocess.run`, or
`subprocess.Popen`.

Pre-repair reproduction used temp symlinked configured roots. Before the
repair, `agent-process-helper` returned success, reached the mocked
`subprocess.run` path, and created
`state/docker/agent-process-helper/agent-a-refresh.log` through the symlinked
private root target.

Current local evidence for this slice:

- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_process_helper_rejects_symlinked_configured_roots_before_work or docker_authority_inventory' --maxfail=5`
  passed: 2 passed, 55 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_process_helper_rejects_symlinked_configured_roots_before_work or agent_helpers_reject_symlinked_home_root or agent_helpers_reject_symlink_escaped_agent_paths or agent_process_helper_rejects_symlink_escaped_log_directory or configured_root_mismatch or docker_authority_inventory' --maxfail=10`
  passed: 6 passed, 51 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  57 passed in 0.84s.
- `python3 -m py_compile python/arclink_agent_process_helper.py`,
  `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1293 passed, 6 skipped, and
  81 warnings in 63.81s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, private-state reads, or host mutation. `GAP-019`
remains open for writeable Docker socket broker authority, root helper
authority, stronger isolation, live alert integration, or operator residual-risk
acceptance.

## Ralphie Dream Buildout: GAP-019-AS Agent Home Root Symlink Rejection

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-AS` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `agent-user-helper` and `agent-process-helper` now
reject symlinked configured or requested Docker agent-home roots, including
`ARCLINK_DOCKER_AGENT_HOME_ROOT`, before uid/gid assignment writes, ownership
repair, helper log creation, or subprocess execution.

Pre-repair reproduction used a temp
`ARCLINK_DOCKER_AGENT_HOME_ROOT -> escaped-users` symlink. Before the repair,
`agent-user-helper` returned success, reached three mocked root account/chown
commands, and wrote `.arclink-user-ids.json` through the escaped root;
`agent-process-helper` returned success, reached the mocked subprocess path,
and created helper logs.

Current local evidence for this slice:

- `python3 -m pytest -q tests/test_arclink_docker.py -k 'symlinked_home_root or docker_authority_inventory' --maxfail=5`
  passed: 2 passed, 54 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_helpers_reject_symlinked_home_root or agent_helpers_reject_symlink_escaped_agent_paths or agent_process_helper_rejects_symlink_escaped_log_directory or configured_root_mismatch or docker_authority_inventory' --maxfail=10`
  passed: 5 passed, 51 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  56 passed in 0.87s.
- `python3 -m py_compile python/arclink_agent_user_helper.py python/arclink_agent_process_helper.py`,
  `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `bash -n deploy.sh bin/*.sh test.sh`, `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1292 passed, 6 skipped, and
  81 warnings in 63.10s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, private-state reads, or host mutation. `GAP-019`
remains open for writeable Docker socket broker authority, root helper
authority, stronger isolation, live alert integration, or operator residual-risk
acceptance.

## Ralphie Dream Buildout: GAP-019-AR Dashboard Backend Host Confinement

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-AR` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `agent-process-helper` and
`agent-supervisor-broker` now reject unsafe dashboard backend host values before
dashboard process or proxy subprocess construction. Accepted values are
loopback or Docker-internal/private/link-local IPs; wildcard, globally
routable, multicast, malformed, and non-IP values fail closed.

Pre-repair source inspection showed the root process helper accepted the
dashboard backend host as a single line before `subprocess.Popen`, while the
dashboard broker accepted any parsable IP before constructing the auth-proxy
sidecar target.

Current local evidence for this slice:

- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_process_helper_rejects_unsafe_dashboard_backend_host_before_subprocess or agent_supervisor_broker_rejects_unsafe_dashboard_backend_host' --maxfail=1`
  passed: 2 passed, 53 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'dashboard_backend_host or agent_process_helper or agent_supervisor_broker or docker_authority_inventory' --maxfail=10`
  passed: 13 passed, 42 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_enrollment_provisioner_regressions.py tests/test_deploy_regressions.py`
  passed: 198 passed in 6.68s.
- `python3 -m py_compile python/arclink_agent_process_helper.py python/arclink_agent_supervisor_broker.py`,
  `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  and `bash -n deploy.sh bin/*.sh test.sh` passed.
- `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1291 passed, 6 skipped, and
  81 warnings in 63.48s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, private-state reads, or host mutation. `GAP-019`
remains open for writeable Docker socket broker authority, root helper
authority, stronger isolation, live alert integration, or operator residual-risk
acceptance.

## Ralphie Dream Buildout: GAP-019-AQ Provisioner Child Env Allowlist

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-AQ` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `agent-supervisor` now starts the enrollment
provisioner child from an explicit allowlist instead of `os.environ.copy()`.
The child keeps Docker mode/path config, runtime roots, service URLs, and
helper/broker values needed for Docker enrollment and queued operator actions,
while unrelated payment, provider, bot, ingress, memory-synthesis, session,
fleet, Python path, and Git/SSH steering env keys are not forwarded.

Pre-repair reproduction showed the gap directly: the planned focused selector
returned only `52 deselected`, and source inspection showed
`python/arclink_docker_agent_supervisor.py:run_provisioner` building the child
env from `os.environ.copy()`.

Current local evidence for this slice:

- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_supervisor_provisioner_child_env_is_allowlisted' --maxfail=1`
  passed: 1 passed, 52 deselected.
- `python3 -m py_compile python/arclink_docker_agent_supervisor.py`,
  `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  and `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_supervisor_provisioner_child_env_is_allowlisted or docker_authority_inventory_matches_compose_boundary' --maxfail=1`
  passed: 2 passed, 51 deselected.
- `python3 tests/test_arclink_docker.py` passed all 53 Docker regression tests.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_enrollment_provisioner_regressions.py tests/test_deploy_regressions.py`
  passed: 196 passed in 6.64s.
- `bash -n deploy.sh bin/*.sh test.sh` and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1289 passed, 6 skipped, and
  81 warnings in 63.99s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, private-state reads, or host mutation. `GAP-019`
remains open for writeable Docker socket broker authority, root helper
authority, stronger isolation, live alert integration, or operator residual-risk
acceptance. `agent-supervisor` still has private config/state/vault mounts for
Docker agent reconciliation; this slice only narrows the provisioner child env.

## Ralphie Dream Buildout: GAP-019-AP Direct-Run Listener Defaults

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-AP` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. The seven high-authority Docker broker/helper
modules now bind `127.0.0.1` by default when run directly; Compose remains the
explicit source-owned `0.0.0.0` opt-in for internal request-network
reachability, and healthchecks stay loopback-local.

Pre-repair reproduction showed the gap directly: the planned focused selector
returned only `51 deselected`, and a direct module probe showed
`deployment-exec-broker`, `migration-capture-helper`, `agent-user-helper`,
`agent-process-helper`, `agent-supervisor-broker`, `operator-upgrade-broker`,
and `gateway-exec-broker` all reported `DEFAULT_HOST == "0.0.0.0"` outside
Compose.

Current local evidence for this slice:

- `python3 -m pytest -q tests/test_arclink_docker.py -k 'high_authority_helpers_default_to_loopback_outside_compose' --maxfail=1`
  passed: 1 passed, 51 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'high_authority_helpers_default_to_loopback_outside_compose or docker_authority_inventory_matches_compose_boundary' --maxfail=1`
  passed: 2 passed, 50 deselected.
- `python3 -m py_compile` for the seven broker/helper modules and
  `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`
  passed.
- `python3 tests/test_arclink_docker.py` passed all 52 Docker regression tests.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_deploy_regressions.py tests/test_health_regressions.py`
  passed: 189 passed in 6.63s.
- `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, `bash -n deploy.sh bin/*.sh test.sh`,
  and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1288 passed, 6 skipped, and
  81 warnings in 63.51s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, private-state reads, or host mutation. `GAP-019`
remains open for writeable Docker socket broker authority, root helper
authority, stronger isolation, live alert integration, or operator residual-risk
acceptance.

## Ralphie Dream Buildout: GAP-019-AO Process Helper Log Directory Symlink Paths

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-AO` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `agent-process-helper` now rejects symlink-escaped
`state/docker/agent-process-helper` log directories and helper log files before
opening logs, `subprocess.run`, or `subprocess.Popen`.

Pre-repair reproduction showed the gap directly: a no-secret temp-dir probe
created `state/docker/agent-process-helper -> <tmp>/escaped-logs`; `run_once`
returned success, wrote `agent-test-refresh.log` under the escaped directory,
and reached mocked `subprocess.run`, while `ensure_processes` wrote
`agent-test-gateway.log` under the escaped directory and reached mocked
`subprocess.Popen`. The focused regression then failed before repair with a
successful helper response pointing at the escaped log path.

Current local evidence for this slice:

- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_process_helper_rejects_symlink_escaped_log_directory' --maxfail=1`
  passed: 1 passed, 50 deselected.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 -m py_compile python/arclink_agent_process_helper.py`, and
  `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_process_helper_rejects_symlink_escaped_log_directory or docker_authority_inventory' --maxfail=1`
  passed: 2 passed, 49 deselected.
- `python3 tests/test_arclink_docker.py` passed all 51 Docker regression tests.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_enrollment_provisioner_regressions.py tests/test_arclink_action_worker.py`
  passed: 114 passed in 2.57s.
- `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, `bash -n deploy.sh bin/*.sh test.sh`,
  and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1287 passed, 6 skipped, and
  81 warnings in 63.35s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, private-state reads, or host mutation. `GAP-019`
remains open for writeable Docker socket broker authority, root helper
authority, stronger isolation, live alert integration, or operator residual-risk
acceptance.

## Ralphie Dream Buildout: GAP-019-AN Root Agent Helper Symlink Paths

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-AN` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `agent-user-helper` and `agent-process-helper` now
reject symlink-escaped agent home, Hermes home, and workspace paths before root
filesystem work, helper log creation, `subprocess.run`, or
`subprocess.Popen`.

Pre-repair reproduction showed the gap directly: a no-secret temp-dir probe
created `state/docker/users/alex -> <tmp>/escaped/alex`; `agent-user-helper`
accepted the request and targeted the escaped path for chown, while
`agent-process-helper` reached the mocked subprocess path. The focused
regression then failed before repair because the helper returned the escaped
target as a successful home.

Current local evidence for this slice:

- `python3 -m py_compile python/arclink_agent_user_helper.py python/arclink_agent_process_helper.py`
  passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_helpers_reject_symlink_escaped_agent_paths' --maxfail=1`
  passed: 1 passed, 49 deselected.
- `python3 tests/test_arclink_docker.py` passed all 50 Docker regression tests.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_helpers_reject_symlink_escaped_agent_paths or docker_authority_inventory' --maxfail=1`
  passed: 2 passed, 48 deselected.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, `bash -n deploy.sh bin/*.sh test.sh`,
  and `git diff --check` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_enrollment_provisioner_regressions.py tests/test_arclink_action_worker.py`
  passed: 113 passed in 2.51s.
- `python3 -m pytest -q tests` passed: 1286 passed, 6 skipped, and
  81 warnings in 63.69s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, private-state reads, or host mutation. `GAP-019`
remains open for writeable Docker socket broker authority, root helper
authority, stronger isolation, live alert integration, or operator residual-risk
acceptance.

## Ralphie Dream Buildout: GAP-019-AM Process Helper Env Boundary

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-AM` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `agent-process-helper` now rejects dynamic-loader
`LD_*`, Python path/startup, shell startup, Git/SSH command-steering, and
secret-looking process env keys before helper logs, `subprocess.run`, or
`subprocess.Popen`; `agent-supervisor` strips known ArcLink helper tokens and
fails closed on the same unapproved non-token key family before helper payload
construction.

Pre-repair reproduction showed the gap directly: a no-secret local probe sent
`LD_PRELOAD` in an `ensure_processes` request, and the helper accepted it,
reached the mocked `Popen`, and forwarded `LD_PRELOAD` in the process env.
After adding the focused regression, the pre-repair pytest signal was:
`LD_PRELOAD was not rejected before run_once subprocess`.

Current local evidence for this slice:

- `python3 -m py_compile python/arclink_agent_process_helper.py python/arclink_docker_agent_supervisor.py`
  passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_process_helper_rejects_unapproved_agent_env or docker_agent_supervisor_rejects_unapproved_agent_process_env or docker_authority_inventory' --maxfail=1`
  passed: 3 passed, 46 deselected.
- `python3 tests/test_arclink_docker.py` passed all 49 Docker regression tests.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  49 passed.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and
  `bash -n deploy.sh bin/*.sh test.sh` passed.
- `python3 -m pytest -q tests` passed: 1285 passed, 6 skipped, and
  81 warnings in 63.57s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, private-state reads, or host mutation. `GAP-019`
remains open for writeable Docker socket broker authority, root helper
authority, stronger isolation, live alert integration, or operator residual-risk
acceptance.

## Ralphie Dream Buildout: GAP-012 Product Matrix Truth Guard

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-012` is now locally closed. The product reality matrix has a local
documentation truth guard that parses claim rows, verifies declared status
totals, rejects unknown statuses, requires source/proof anchors for rows marked
`real`, and preserves live-proof or operator/product-decision language for
gated rows.

Pre-repair reproduction showed the gap directly:
`python3 -m pytest -q tests/test_documentation_truths.py -k product_matrix --maxfail=1`
reported `7 deselected` because no product-matrix truth test existed.

Current local evidence for this slice:

- `python3 -m pytest -q tests/test_documentation_truths.py -k product_matrix --maxfail=1`
  passed: 3 passed, 7 deselected.
- `python3 tests/test_documentation_truths.py` passed all 10 documentation
  truth checks.
- `python3 -m pytest -q tests/test_documentation_truths.py` passed: 10 passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1283 passed, 6 skipped, and
  81 warnings in 63.69s.

This pass did not run deploy/install/upgrade, Docker lifecycle/mutation,
systemd, live provider APIs, payment/bot/Notion services, SSH fleet mutation,
private-state reads, or host mutation. The product matrix is now locally
guarded, but it is still not live launch certification; `PG-PROD`,
`PG-STRIPE`, `PG-BOTS`, `PG-PROVISION`, `PG-PROVIDER`, `PG-HERMES`,
`PG-NOTION`, `PG-BACKUP`, and policy rows remain open until their separate
authorized proof or decision windows.

## Ralphie Dream Buildout: GAP-021-A Local Cloud Fleet Lifecycle Harness

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-021-A` has reduced the cloud-fleet proof gap with a no-secret fake-provider
lifecycle harness. `GAP-021` remains proof-gated for real Hetzner/Linode APIs,
SSH wait, worker join, health, drain/remove, and destroy evidence.

Pre-repair reproduction showed the Linode lifecycle cluster was missing:
`python3 -m pytest -q tests/test_arclink_inventory_linode.py -k 'remove or destroy or lifecycle' --maxfail=1`
reported `3 deselected`.

Current local evidence for this slice:

- `python3 -m py_compile python/arclink_inventory.py python/arclink_inventory_hetzner.py python/arclink_inventory_linode.py python/arclink_fleet_inventory_worker.py python/arclink_fleet.py`
  passed.
- `python3 -m pytest -q tests/test_arclink_inventory_linode.py -k 'remove or destroy or lifecycle' --maxfail=1`
  passed: 1 passed, 3 deselected.
- `python3 -m pytest -q tests/test_arclink_inventory_hetzner.py tests/test_arclink_inventory_linode.py tests/test_arclink_fleet_inventory_worker.py -k 'cloud or lifecycle or probe or drain or remove or destroy' --maxfail=20`
  passed: 7 passed, 5 deselected.
- `python3 -m pytest -q tests/test_arclink_inventory_hetzner.py tests/test_arclink_inventory_linode.py tests/test_arclink_inventory.py tests/test_arclink_fleet_inventory_worker.py --maxfail=20`
  passed: 14 passed.
- `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1280 passed, 6 skipped, and
  81 warnings in 63.38s.

This pass did not run deploy/install/upgrade, Docker lifecycle/mutation,
systemd, live provider APIs, payment/bot/Notion services, SSH fleet mutation,
private-state reads, or host mutation.

## Ralphie Dream Buildout: GAP-019-AL Trusted-Host Acceptance Gate

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-AL` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. The seven high-authority broker/helper services now
fail closed unless private Docker config explicitly sets
`ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED=accepted`.

This pass reproduced the missing boundary with a no-secret local probe: before
the repair, `deployment-exec-broker`, `migration-capture-helper`,
`agent-user-helper`, `agent-process-helper`, `agent-supervisor-broker`,
`operator-upgrade-broker`, and `gateway-exec-broker` all reported
`acceptance_gate=missing`. After the repair, the same probe reported
`acceptance_gate=present` for all seven.

Current local evidence for this slice:

- `python3 -m py_compile python/arclink_boundary.py python/arclink_agent_supervisor_broker.py python/arclink_deployment_exec_broker.py python/arclink_gateway_exec_broker.py python/arclink_operator_upgrade_broker.py python/arclink_agent_user_helper.py python/arclink_agent_process_helper.py python/arclink_migration_capture_helper.py`
  passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'trusted_host or authority_inventory or compose or docker_config or docker_docs' --maxfail=10`
  passed: 14 passed, 33 deselected.
- `python3 -m pytest -q tests/test_arclink_executor.py -k deployment_exec_broker --maxfail=5`,
  `python3 -m pytest -q tests/test_arclink_pod_migration.py -k migration_capture_helper --maxfail=5`,
  and `python3 -m pytest -q tests/test_arclink_notification_delivery.py -k gateway_exec_broker --maxfail=5`
  passed.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  47 passed.
- `python3 -m pytest -q tests` passed: 1278 passed, 6 skipped, and
  81 warnings in 63.01s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, private-state reads, or host mutation. `GAP-019`
remains open for writeable Docker socket broker authority, root helper
authority, stronger isolation, live alert integration, or operator residual-risk
acceptance. The new gate is only a fail-closed acknowledgement boundary and
does not close `GAP-001`, `PG-UPGRADE`, `PG-PROVISION`, `PG-BOTS`,
`PG-HERMES`, or any credentialed live proof gate.

## Ralphie Dream Buildout: GAP-019-AK Broker/Helper Compose Network Scoping

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-AK` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. The tokened Docker/root brokers and helpers no
longer sit on the shared default Compose network. Each request lane is now an
internal network shared only with its legitimate caller services, while
`agent-process-helper` and `operator-upgrade-broker` keep single-service egress
networks for outbound runtime/provider and upgrade-fetch work.

This pass reproduced the missing boundary with a no-secret local probe: before
the repair, all seven high-authority services reported
`networks=default-only`. After the repair, the same probe reported
`networks=scoped` for `deployment-exec-broker`,
`migration-capture-helper`, `agent-user-helper`, `agent-process-helper`,
`agent-supervisor-broker`, `operator-upgrade-broker`, and
`gateway-exec-broker`.

Current local evidence for this slice:

- `python3 -m py_compile python/arclink_agent_supervisor_broker.py python/arclink_deployment_exec_broker.py python/arclink_gateway_exec_broker.py python/arclink_operator_upgrade_broker.py python/arclink_agent_user_helper.py python/arclink_agent_process_helper.py python/arclink_migration_capture_helper.py`
  passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'compose or authority_inventory or broker_network or helper_network or docker_docs' --maxfail=10`
  passed: 11 passed, 34 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20`
  passed: 45 passed.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`, `python3 tests/test_public_repo_hygiene.py`,
  and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1276 passed, 6 skipped, and
  81 warnings in 63.47s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, private-state reads, or host mutation. `GAP-019`
remains open for writeable Docker socket broker authority, root helper
authority, stronger isolation, live alert integration, or operator residual-risk
acceptance.

## Ralphie Dream Buildout: GAP-019-AJ Agent Process Helper Desired-Signature Restart

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-AJ` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `agent-process-helper` now hashes the validated
gateway/dashboard setpriv command, Hermes-home cwd, and process env contract;
when the desired signature changes under the same `agent_id:kind`, it stops
the stale process group before starting the replacement. Identical desired
specs do not churn.

This pass reproduced the missing boundary with a no-secret local probe: before
the repair, changing a dashboard backend port from `8100` to `8200` left the
old process running and reported no restart. After the repair, the same probe
reported one stopped process, one replacement start, and the new command port
`8200`.

Current local evidence for this slice:

- Pre-repair reproduction returned `second_started=[]`, `popen_count=1`,
  `terminated_count=0`, and `last_command_port=8100`.
- Post-repair reproduction returned `second_started=["agent-test:dashboard"]`,
  `second_stopped=["agent-test:dashboard"]`, `popen_count=2`,
  `terminated_count=1`, and `last_command_port=8200`.
- `python3 -m py_compile python/arclink_agent_process_helper.py` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_process_helper or authority_inventory or compose or docker_docs' --maxfail=10`
  passed: 14 passed, 30 deselected.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`, and
  `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1275 passed, 6 skipped, and
  81 warnings in 63.38s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, private-state reads, or host mutation. `GAP-019`
remains open for writeable Docker socket broker authority, root helper
authority, stronger isolation, live alert integration, or operator residual-risk
acceptance.

## Ralphie Dream Buildout: GAP-019-AI Operator Upgrade Broker Docker CLI Lookup Hardening

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-AI` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `operator-upgrade-broker` now validates any
preserved `ARCLINK_DOCKER_BINARY` before passing it to queued Docker-mode
operator upgrade or pin-upgrade child subprocesses.

This pass reproduced the missing boundary with a no-secret local probe: before
the repair, `ARCLINK_DOCKER_BINARY=/bin/bash` reached an allowlisted
`deploy.sh docker upgrade` child env and returned success. After the repair,
the same probe failed closed before `subprocess.run`, with no captured child
command.

Current local evidence for this slice:

- Pre-repair reproduction returned `ok=True`, command
  `deploy.sh docker upgrade`, and child `ARCLINK_DOCKER_BINARY=/bin/bash`.
- Post-repair reproduction returned `ok=False`, no captured command, and no
  child `ARCLINK_DOCKER_BINARY`.
- `python3 -m py_compile python/arclink_operator_upgrade_broker.py` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'operator_upgrade_broker or authority_inventory or compose' --maxfail=10`
  passed: 12 passed, 31 deselected.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`, and
  `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1274 passed, 6 skipped, and
  81 warnings in 63.24s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, private-state reads, or host mutation. `GAP-019`
remains open for writeable Docker socket broker authority, root helper
authority, stronger isolation, live alert integration, or operator residual-risk
acceptance.

## Ralphie Dream Buildout: GAP-019-AH Gateway Exec Broker Docker CLI Lookup Hardening

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-AH` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `gateway-exec-broker` now requires Docker discovery
and gateway exec to use a trusted Docker CLI path and fails closed when
`ARCLINK_DOCKER_BINARY` or `PATH` would resolve to an unsafe, missing,
non-executable, or non-Docker value.

This pass reproduced the missing boundary with a no-secret local probe: before
the repair, a temporary PATH-first fake `docker` was invoked for both
`docker ps` discovery and `docker exec`, and the broker returned success. After
the repair, the same probe fails closed with `gateway exec broker Docker CLI
path is not trusted` and no fake Docker calls.

Current local evidence for this slice:

- Pre-repair reproduction returned `ok=True` and two fake `docker` calls.
- Post-repair reproduction returned `ok=False`, `fake_docker_calls=[]`.
- `python3 -m py_compile python/arclink_gateway_exec_broker.py python/arclink_notification_delivery.py`
  passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'gateway_exec_broker or authority_inventory or compose' --maxfail=5`
  passed: 10 passed, 32 deselected.
- `python3 -m pytest -q tests/test_arclink_notification_delivery.py -k 'gateway_exec_broker or public_agent_bridge' --maxfail=10`
  passed: 8 passed, 14 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  42 tests.
- `python3 -m pytest -q tests/test_arclink_notification_delivery.py --maxfail=20`
  passed: 22 tests.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`, and
  `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1273 passed, 6 skipped, and
  81 warnings in 63.24s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, or host mutation. `GAP-019` remains open for
writeable Docker socket broker authority, root helper authority, stronger
isolation, live alert integration, or operator residual-risk acceptance.

## Ralphie Dream Buildout: GAP-019-AG Deployment Exec Broker Docker CLI Lookup Hardening

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-AG` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `deployment-exec-broker` now requires
`ARCLINK_DOCKER_BINARY` to resolve to `docker` or a trusted absolute Docker CLI
path and fails closed before deployment Compose subprocesses when the
configured value is unsafe, missing, non-executable, or not a Docker CLI path.

This pass reproduced the missing boundary with a no-secret local probe: before
the repair, `ARCLINK_DOCKER_BINARY=bash` produced a successful
`bash compose ... ps --format json` command. After the repair, the same probe
fails closed with no subprocess calls.

Current local evidence for this slice:

- Pre-repair reproduction returned `executables=['bash']`.
- Post-repair reproduction returned `ok=False` and `executables=[]`.
- `python3 -m py_compile python/arclink_deployment_exec_broker.py python/arclink_executor.py` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'deployment_exec_broker or authority_inventory or compose' --maxfail=5`
  passed: 10 passed, 31 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  41 tests.
- `python3 -m pytest -q tests/test_arclink_executor.py --maxfail=20` passed:
  39 tests.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1272 passed, 6 skipped, and
  81 warnings in 63.92s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, or host mutation. `GAP-019` remains open for
writeable Docker socket broker authority, root helper authority, stronger
isolation, live alert integration, or operator residual-risk acceptance.

## Ralphie Dream Buildout: GAP-019-AF Agent Supervisor Broker Docker CLI Lookup Hardening

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-AF` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `agent-supervisor-broker` now requires
`ARCLINK_DOCKER_BINARY` to resolve to `docker` or a trusted absolute Docker CLI
path and fails closed before dashboard network/proxy subprocesses when the
configured value is unsafe, missing, non-executable, or not a Docker CLI path.

This pass reproduced the missing boundary with a no-secret local probe: before
the repair, `ARCLINK_DOCKER_BINARY=bash` produced successful dashboard network
commands whose executable was `bash`. After the repair, the same probe fails
closed with no subprocess calls.

Current local evidence for this slice:

- Pre-repair reproduction returned `executables=['bash', 'bash']`.
- Post-repair reproduction returned `ok=False` and `executables=[]`.
- `python3 -m py_compile python/arclink_agent_supervisor_broker.py` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_supervisor_broker or authority_inventory or compose' --maxfail=5`
  passed: 11 passed, 29 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  40 tests.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1271 passed, 6 skipped, and
  81 warnings in 63.26s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, or host mutation. `GAP-019` remains open for
writeable Docker socket broker authority, root helper authority, stronger
isolation, live alert integration, or operator residual-risk acceptance.

## Ralphie Dream Buildout: GAP-019-AE Agent User Helper Root Executable Lookup Hardening

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-AE` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `agent-user-helper` now invokes
`/usr/sbin/groupadd`, `/usr/sbin/useradd`, and `/usr/bin/chown` by absolute
trusted path and fails closed if any required executable is unavailable before
uid/gid assignment writes, directory creation, account commands, or recursive
ownership repair.

This pass reproduced the missing boundary with a no-secret local probe: before
the repair, the helper dispatched `groupadd`, `useradd`, and `chown` as bare
command names. After the repair, the same probe dispatched the trusted absolute
paths.

Current local evidence for this slice:

- Pre-repair reproduction returned `['groupadd', 'useradd', 'chown']`.
- Post-repair reproduction returned
  `['/usr/sbin/groupadd', '/usr/sbin/useradd', '/usr/bin/chown']`.
- `python3 -m py_compile python/arclink_agent_user_helper.py` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_user_helper or authority_inventory or compose' --maxfail=5`
  passed: 13 passed, 26 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  39 tests.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1270 passed, 6 skipped, and
  81 warnings in 63.07s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, or host mutation. `GAP-019` remains open for
writeable Docker socket broker authority, root helper authority, stronger
isolation, live alert integration, or operator residual-risk acceptance.

## Ralphie Dream Buildout: GAP-019-AD Agent Process Helper Pre-Drop Lookup Hardening

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-AD` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `agent-process-helper` now rejects request `PATH`
values that differ from `SAFE_PATH`, invokes `/usr/bin/setpriv` by absolute
path, and fails identity setup closed unless the pinned runtime venv Python
exists under `RUNTIME_DIR`.

This pass reproduced the missing boundary with a no-secret local probe: before
the repair, the helper accepted a malicious request `PATH`, invoked bare
`setpriv`, and passed that path to the child process before privilege drop.
After the repair, the same request fails closed before any subprocess call.

Current local evidence for this slice:

- Pre-repair reproduction returned `accepted_caller_path=True`, first
  executable `setpriv`, and child `PATH=/tmp/.../malicious-bin`.
- Post-repair reproduction returned `accepted_caller_path=False`, no
  subprocess executable, and
  `agent process helper env PATH must match the safe helper PATH`.
- `python3 -m py_compile python/arclink_agent_process_helper.py python/arclink_docker_agent_supervisor.py`
  passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_process_helper or authority_inventory or compose'`
  passed: 12 passed, 26 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  38 tests.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1269 passed, 6 skipped, and
  81 warnings in 62.86s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, or host mutation. `GAP-019` remains open for
writeable Docker socket broker authority, root helper authority, stronger
isolation, live alert integration, or operator residual-risk acceptance.

## Ralphie Dream Buildout: GAP-019-AC Migration Capture Helper Env And State-Root Confinement

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-AC` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `migration-capture-helper` no longer inherits broad
`*arclink-env`; it receives only `ARCLINK_STATE_ROOT_BASE` plus helper
token/listener env, keeps no Docker socket, and still runs as root with
`cap_drop: ALL` for approved Pod migration file work.

This pass reproduced the missing boundary with no-secret local probes: before
the repair, the helper inherited broad app env and accepted a source state root
outside the configured `ARCLINK_STATE_ROOT_BASE` when its basename matched the
deployment root. After the repair, outside-base source, target, and staging
paths fail closed before `_copy_capture` or `_materialize_capture` can run.

Current local evidence for this slice:

- Pre-repair Compose/source probe returned broad env inheritance and no helper
  use of configured `ARCLINK_STATE_ROOT_BASE`.
- Pre-repair helper probe returned
  `{'outside_source_accepted': True, 'payload': {'file_count': 1}}`.
- Post-repair helper probe returned
  `{'outside_source_accepted': False, 'payload': 'migration capture helper source root must stay under the configured state-root base'}`.
- `python3 -m py_compile python/arclink_migration_capture_helper.py python/arclink_pod_migration.py`
  passed.
- `python3 -m pytest -q tests/test_arclink_pod_migration.py -k 'migration_capture_helper or capture_requires_helper or unscoped_source_root'`
  passed: 4 passed, 7 deselected.
- `python3 -m pytest -q tests/test_arclink_action_worker.py -k 'migration_capture_helper or reprovision_non_dry_run'`
  passed: 2 passed, 35 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'migration_capture_helper or authority_inventory or compose' --maxfail=5`
  passed: 9 passed, 29 deselected.
- `python3 -m pytest -q tests/test_arclink_pod_migration.py --maxfail=20`
  passed: 11 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  38 tests.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1269 passed, 6 skipped, and 81 warnings
  in 63.45s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, or host mutation. `GAP-019` remains open for
writeable Docker socket broker authority, root helper authority over deployment
bind mounts, stronger isolation, live alert integration, or operator
residual-risk acceptance.

## Ralphie Dream Buildout: GAP-019-AB Operator Upgrade Broker Env And Mount Narrowing

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-AB` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `operator-upgrade-broker` no longer inherits broad
`*arclink-env`, no longer mounts broad canonical private config/state or
`arclink-priv/secrets/container`, and no longer passes its full process env to
allowlisted upgrade subprocesses. It keeps the writeable Docker socket and
writable host repo bind needed for queued Docker-mode upgrades; that host repo
bind can still reach nested private state and remains trusted-host residual
risk.

This pass reproduced the missing boundary with a no-secret local source probe:
before the repair, `operator-upgrade-broker` inherited broad app env, mounted
broad private config/state/secrets, and used `os.environ.copy()` for upgrade
subprocess env. After the repair, those surfaces are absent, canonical
operator log paths are mapped to the host private bind, and the child env is an
explicit allowlist.

Current local evidence for this slice:

- Pre-repair source probe failed with broad env, broad private mounts, and
  child-process full-env inheritance present.
- Post-repair source probe returned
  `{'inherits_broad_arclink_env': False, 'inherits_control_secret_env': False, 'mounts_private_config': False, 'mounts_private_state': False, 'mounts_global_container_secrets': False, 'has_writable_host_repo_bind': True, 'has_docker_socket': True, 'has_cap_drop_all': True, 'operator_env_copies_process_env': False, 'operator_env_has_child_allowlist': True}`.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'operator_upgrade_broker or authority_inventory or compose' --maxfail=5`
  passed: 10 passed, 27 deselected.
- `python3 -m pytest -q tests/test_arclink_enrollment_provisioner_regressions.py -k 'operator_upgrade_broker or host_upgrade or pin_upgrade' --maxfail=5`
  passed: 6 passed, 20 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  37 tests.
- `python3 -m pytest -q tests/test_arclink_enrollment_provisioner_regressions.py --maxfail=20`
  passed: 26 tests.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1267 passed, 6 skipped, and 81 warnings
  in 63.35s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, or host mutation. `GAP-019` remains open for
writeable Docker socket broker authority, writable host checkout/private-state
reachability, root helper authority, stronger isolation, live alert
integration, or operator residual-risk acceptance.

## Ralphie Dream Buildout: GAP-019-Z Agent Supervisor Broker Service Env And Private Mount Narrowing

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-Z` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `agent-supervisor-broker` no longer inherits broad
`*arclink-env` service values and no longer mounts broad
`arclink-priv/config`, `arclink-priv/state`, or
`arclink-priv/secrets/container`. It keeps only Docker binary/image, repo path,
host/container private path metadata, broker token/listener env, and the
writeable Docker socket needed for allowlisted dashboard network/proxy sidecars.

This pass reproduced the missing boundary with a no-secret local Compose probe:
before the repair, `agent-supervisor-broker` inherited broad `*arclink-env` and
mounted broad private config/state/secrets. After the repair, those env and
mount surfaces are absent while the Docker socket remains an explicit
trusted-host boundary.

Current local evidence for this slice:

- Pre-repair Compose probe failed with broad env plus private config/state and
  global container-secrets mounts present.
- Post-repair Compose probe returned
  `{'inherits_broad_arclink_env': False, 'mounts_global_container_secrets': False, 'mounts_private_config': False, 'mounts_private_state': False, 'has_docker_socket': True, 'has_cap_drop_all': True}`.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_supervisor_broker or authority_inventory or compose'`
  passed: 7 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  35 tests.
- `python3 tests/test_arclink_docker.py` passed: 35 script tests.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`
  passed.
- `python3 tests/test_documentation_truths.py` passed: 7 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1265 passed, 6 skipped, and 81 warnings
  in 62.94s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, or host mutation. `GAP-019` remains open for
writeable Docker socket broker authority, root helper authority, stronger
isolation, live alert integration, or operator residual-risk acceptance.

## Ralphie Dream Buildout: GAP-019-Y Gateway Exec Broker Service Env And Private Mount Narrowing

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-Y` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `gateway-exec-broker` no longer inherits broad
`*arclink-env` service values and no longer mounts broad
`arclink-priv/config`, `arclink-priv/state`, or
`arclink-priv/secrets/container`. It keeps only `ARCLINK_STATE_ROOT_BASE`,
broker token/listener env, the deployment state-root bind needed for rendered
Compose fallback files, and the writeable Docker socket needed for allowlisted
public-Agent `hermes-gateway` exec.

This pass reproduced the missing boundary with a no-secret local Compose probe:
before the repair, `gateway-exec-broker` inherited broad `*arclink-env` and
mounted broad private config/state/secrets. After the repair, those env and
mount surfaces are absent while the deployment state-root bind and Docker
socket remain explicit trusted-host boundaries.

Current local evidence for this slice:

- Pre-repair Compose probe failed with broad env plus private config/state and
  global container-secrets mounts present.
- Post-repair Compose probe returned
  `{'inherits_broad_arclink_env': False, 'mounts_global_container_secrets': False, 'mounts_private_config': False, 'mounts_private_state': False, 'mounts_state_root_base': True, 'has_docker_socket': True}`.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'gateway_exec_broker or authority_inventory or compose'`
  passed: 5 tests.
- `python3 -m pytest -q tests/test_arclink_notification_delivery.py -k 'gateway_exec_broker or public_agent_bridge'`
  passed: 8 tests.
- `python3 tests/test_arclink_docker.py` passed: 33 script tests.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  34 tests.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`
  passed.
- `python3 tests/test_documentation_truths.py` passed: 7 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1264 passed, 6 skipped, and 81 warnings
  in 62.92s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, or host mutation. `GAP-019` remains open for
writeable Docker socket broker authority, root helper authority, stronger
isolation, live alert integration, or operator residual-risk acceptance.

## Ralphie Dream Buildout: GAP-019-X Process Helper Service Env And Secret Mount Narrowing

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-X` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `agent-process-helper` no longer inherits broad
`*arclink-env` service values and no longer mounts the global
`arclink-priv/secrets/container` directory. It keeps explicit non-secret Docker
mode/path validation env, its token/listener keys, and the config, state,
vault, and read-only repo mounts required by the allowlisted agent commands.

This pass reproduced the missing boundary with a no-secret local Compose probe:
before the repair, `agent-process-helper` inherited broad `*arclink-env`,
mounted global container secrets, and kept the read-only repo mount. After the
repair, broad env inheritance and the global secret mount are both absent while
the read-only repo mount remains.

Current local evidence for this slice:

- Pre-repair Compose probe returned
  `{'inherits_broad_arclink_env': True, 'mounts_global_container_secrets': True, 'has_read_only_repo_mount': True}`.
- Post-repair Compose probe returned
  `{'inherits_broad_arclink_env': False, 'mounts_global_container_secrets': False, 'has_read_only_repo_mount': True}`.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'authority_inventory or compose or agent_process_helper'`
  passed: 7 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  33 tests.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`
  passed.
- `python3 tests/test_documentation_truths.py` passed: 7 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1263 passed, 6 skipped, and 81 warnings
  in 63.01s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, or host mutation. `GAP-019` remains open for root
helper authority, writeable socket brokers, stronger isolation, live alert
integration, or operator residual-risk acceptance.

## Ralphie Dream Buildout: GAP-019-W Process Helper Control-Token Env Rejection

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-W` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `agent-process-helper` now rejects ArcLink
broker/helper/control token env keys, including future `ARCLINK_*_TOKEN` names,
before `subprocess.run` or `subprocess.Popen`; `agent-supervisor` keeps its
aligned process-env filter before helper dispatch.

This pass reproduced the missing boundary with a no-secret local helper probe:
before the repair, `ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN` was forwarded into a
fake gateway process env. After the repair, the same request returns
`ok: False` and never reaches `Popen`.

Current local evidence for this slice:

- Pre-repair helper probe returned `ok: True` and `token_forwarded: True`.
- Post-repair helper probe returned `ok: False`, `popen_called: False`, and
  `agent process helper env must not include ArcLink control token keys`.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_process_helper or process_helper or docker_agent_supervisor_does_not_forward_helper_tokens'`
  passed: 5 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  32 tests.
- `python3 -m py_compile python/arclink_agent_process_helper.py python/arclink_docker_agent_supervisor.py`
  passed.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`
  passed.
- `python3 tests/test_documentation_truths.py` passed: 7 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1262 passed, 6 skipped, and 81 warnings
  in 63.36s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade,
live services, credentials, or host mutation. `GAP-019` remains open for root
helper authority, writeable socket brokers, stronger isolation, live alert
integration, or operator residual-risk acceptance.

## Ralphie Dream Buildout: GAP-019-V Static Control Ingress Routes

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-V` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `control-ingress` now uses Traefik's file provider
with `config/traefik-control.yaml` for `/notion/webhook`, `/v1`, `/api`, and
`/`, and no longer enables Docker provider discovery or mounts
`/var/run/docker.sock`.

This pass reproduced the missing boundary with a no-secret local Compose probe,
then patched `compose.yaml`, `config/traefik-control.yaml`, the Docker authority
inventory, Docker regression tests, Docker/security runbooks, `GAPS.md`,
`USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and
`research/BUILD_COMPLETION_NOTES.md`.

Current local evidence for this slice:

- Pre-repair probe found `control-ingress` enabled Traefik Docker provider
  discovery and mounted `/var/run/docker.sock:ro`.
- Post-repair probe showed `control-ingress` uses the static Traefik file
  provider and has no Docker socket mount.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_compose_defines_full_stack_services tests/test_arclink_docker.py::test_docker_authority_inventory_matches_compose_boundary --maxfail=1`
  passed: 2 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_control_ingress_uses_static_traefik_config_without_docker_socket tests/test_arclink_docker.py::test_control_ingress_static_routes_cover_control_api_web_llm_and_notion --maxfail=1`
  passed: 2 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  32 tests.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`
  passed.
- `python3 tests/test_documentation_truths.py` passed: 7 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1262 passed, 6 skipped, and 81 warnings
  in 63.09s.

This pass did not run Docker lifecycle/mutation, systemd, deploy/install/upgrade, live services,
or host mutation. `GAP-019` remains open for root helper authority, writeable
socket brokers, stronger isolation, live alert integration, or operator
residual-risk acceptance.

## Ralphie Dream Buildout: GAP-019-U Operator Upgrade Broker Split

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-U` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `agent-supervisor-broker` is now limited to
dashboard network/proxy sidecar operations and no longer mounts the host repo.
Queued Docker-mode operator upgrades now route through
`operator-upgrade-broker`, which owns the explicit writable host repo exception
and the allowlisted `run_operator_upgrade`/`run_pin_upgrade` request contract.
`GAP-019` remains open for root helper authority, writeable socket brokers,
stronger isolation, or operator residual-risk acceptance.

This pass reproduced the missing boundary with a no-secret local Compose probe,
then patched `compose.yaml`, Docker/runtime token bootstrap, Python broker and
provisioner code, Docker authority inventory/schema coverage, Docker and
enrollment regression tests, runbooks, `GAPS.md`, `USER_JOURNEY.md`,
`IMPLEMENTATION_PLAN.md`, and `research/BUILD_COMPLETION_NOTES.md`.

Current local evidence for this slice:

- Pre-repair probe found `agent-supervisor-broker` owned both dashboard sidecar
  Docker operations and queued operator upgrades while mounting the host repo
  writable.
- Post-repair probe shows `agent-supervisor-broker` has no upgrade functions
  and no `ARCLINK_DOCKER_HOST_REPO_DIR` bind; `operator-upgrade-broker` owns
  the upgrade functions and writable host repo bind.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_compose_defines_full_stack_services tests/test_arclink_docker.py::test_docker_authority_inventory_matches_compose_boundary --maxfail=1`
  passed: 2 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_operator_upgrade_broker_runs_allowlisted_operator_upgrade tests/test_arclink_docker.py::test_operator_upgrade_broker_rejects_raw_or_unsafe_requests tests/test_arclink_docker.py::test_agent_supervisor_broker_rejects_raw_commands_and_builds_dashboard_proxy --maxfail=1`
  passed: 3 tests.
- `python3 -m pytest -q tests/test_arclink_enrollment_provisioner_regressions.py::test_run_host_upgrade_routes_to_operator_upgrade_broker_in_docker_mode tests/test_arclink_enrollment_provisioner_regressions.py::test_run_host_upgrade_fails_closed_without_operator_upgrade_broker_token_in_docker_mode tests/test_arclink_enrollment_provisioner_regressions.py::test_run_pin_upgrade_action_uses_operator_upgrade_broker_in_docker_mode --maxfail=1`
  passed: 3 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_enrollment_provisioner_regressions.py --maxfail=20`
  passed: 56 tests.
- `python3 -m py_compile python/arclink_agent_supervisor_broker.py python/arclink_enrollment_provisioner.py python/arclink_operator_upgrade_broker.py python/arclink_docker_agent_supervisor.py` passed.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null` passed.
- `python3 tests/test_documentation_truths.py` passed: 7 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1260 passed, 6 skipped, and 81 warnings
  in 63.74s.

This pass did not run Docker, systemd, deploy/install/upgrade, live services,
or host mutation.

## Ralphie Dream Buildout: GAP-019-S Helper Configured-Root Confinement

Status: `GAP-025` broad local Python validation remains locally closed, and
`GAP-019-S` has reduced the Docker/root trusted-host boundary without closing
the residual-risk decision. `agent-user-helper` now rejects configured
`ARCLINK_DOCKER_AGENT_HOME_ROOT` mismatches before uid/gid assignment writes,
directory creation, account commands, or recursive ownership repair.
`agent-process-helper` now rejects configured Docker agent-home, repo,
private-state, state, and runtime root mismatches before helper log creation,
`subprocess.run`, or `subprocess.Popen`.

This pass reproduced the missing fail-closed behavior with a no-secret local
command using temporary directories and fake subprocess/user lookup hooks, then
patched the two helpers, Docker authority inventory, Docker regression tests,
runbooks, `GAPS.md`, `USER_JOURNEY.md`, and `IMPLEMENTATION_PLAN.md`.
`GAP-019` remains open for explicit root helper authority, writeable socket
broker residual risk, stronger isolation, or operator residual-risk acceptance.

Current local evidence for this slice:

- `python3 -m pytest -q tests/test_arclink_docker.py::test_agent_user_helper_rejects_configured_home_root_mismatch tests/test_arclink_docker.py::test_agent_process_helper_rejects_configured_root_mismatch --maxfail=1`
  passed: 2 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_agent_user_helper_rejects_configured_home_root_mismatch tests/test_arclink_docker.py::test_agent_process_helper_rejects_configured_root_mismatch tests/test_arclink_docker.py::test_agent_user_helper_rejects_raw_commands_and_unscoped_paths tests/test_arclink_docker.py::test_agent_process_helper_rejects_raw_commands_and_runs_allowlisted_agent_ops tests/test_arclink_docker.py::test_docker_agent_supervisor_delegates_process_launch_to_process_helper tests/test_arclink_docker.py::test_docker_authority_inventory_matches_compose_boundary --maxfail=1`
  passed: 6 tests.
- `python3 -m py_compile python/arclink_agent_user_helper.py python/arclink_agent_process_helper.py`
  passed.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed:
  30 tests.
- `python3 tests/test_documentation_truths.py` passed: 7 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1260 passed, 6 skipped, and 81 warnings
  in 63.01s.

This pass did not run Docker, systemd, deploy/install/upgrade, live services,
or host mutation.

## Ralphie Dream Buildout: GAP-019-R Agent Process Helper Env Exposure Hardening

Status: public documentation handoff is complete as a source-grounded planning
artifact, `GAP-025` broad local Python validation is locally closed by source
and test evidence, `GAP-011` and `GAP-008` remain locally closed, the local
`GAP-007` Notion state ambiguity is repaired, `GAP-018-A` admin readiness truth
is repaired, `GAP-019-A` through `GAP-019-R` have reduced the Docker/root
trusted-host boundary without closing the residual-risk decision, and
`GAP-016`, `GAP-009`, and `GAP-010` are now locally closed. `GAP-013` is
locally reduced by a Raven-to-dashboard backup pending-status handoff, a
CSRF-gated dashboard/API staged public-key request rail, and a fail-closed
dashboard/API/action-worker write-check boundary. The dashboard now also
surfaces the staged public key, GitHub deploy-key settings link, and
fail-closed write-check action without claiming backup activation or restore.
`GAP-020` now has local no-secret restore-smoke artifact coverage. `GAP-015-A`
adds a Captain dashboard/API share approval inbox for pending owner approval,
waiting-on-owner, and recipient acceptance states, and `GAP-015-B` now adds a
local authenticated retry-notification rail for the currently waiting Raven
share prompt. `GAP-019-N` removes the root boundary from
`control-action-worker` by routing Docker-mode Pod migration capture and
materialization through a tokened root `migration-capture-helper`.
`GAP-019-O` now removes direct user/home setup from `agent-supervisor` by
routing Docker-mode user/home setup through a tokened root `agent-user-helper`.
`GAP-019-P` now removes explicit root and setpriv process launching from
`agent-supervisor` by routing Docker-mode install, identity refresh,
user-agent refresh, cron, gateway, and dashboard process execution through a
tokened root `agent-process-helper`. `GAP-019-Q` now narrows
`agent-user-helper` from Docker's default Linux capability set to `cap_drop:
ALL` with only `CHOWN`, `DAC_OVERRIDE`, and `FOWNER` added back for validated
Docker agent-home writes and ownership repair. `GAP-019-R` now keeps validated
agent process env values out of setpriv argv and `agent-process-helper`
startup logs, and strips supervisor broker/helper tokens before per-agent
process specs are sent to the helper.
Live proof, host mutation, and remaining policy gates are still open.

This pass followed the active plan, reproduced that `agent-process-helper`
wrote a fake token-like env assignment into its startup log through the
reconstructed setpriv command, then changed the helper, supervisor, inventory,
Docker authority tests, runbooks, and gap/journey docs together. The helper
still rejects raw command fields, accepts only typed process operations,
validates canonical Docker agent-home/Hermes-home/workspace paths and
uid/gid/env context, and keeps `GAP-019` open for helper root authority plus
remaining broker/root residual risk.
This pass did not run Docker, systemd, deploy/install/upgrade, live services,
or host mutation.

Current local evidence includes the `GAP-019-R` focused redaction/filtering
tests passing, the affected Docker owner suite passing, documentation
truth/hygiene checks passing, compile checks for the touched helper/supervisor
modules, and the broad `python3 -m pytest -q tests` result recorded as 1258
passed, 6 skipped, and 81 warnings in 62.66s after this env exposure
hardening.
This pass did not run live deploy, install, upgrade, Docker mutation, Stripe,
Telegram, Discord, Notion, provider, Cloudflare, Tailscale, SSH fleet, or
production-host mutation.

## Repairs Applied

- `python/arclink_agent_process_helper.py`,
  `python/arclink_docker_agent_supervisor.py`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`,
  Docker/security docs, `GAPS.md`, `USER_JOURNEY.md`,
  `IMPLEMENTATION_PLAN.md`, and `research/BUILD_COMPLETION_NOTES.md`:
  repaired `GAP-019-R` locally by passing validated process env through
  subprocess `env=` instead of encoding env assignments into setpriv argv,
  omitting env values from process-helper startup command logs, and stripping
  supervisor broker/helper tokens from per-agent process specs before helper
  dispatch.
- `compose.yaml`, `config/docker-authority-inventory.json`,
  `tests/test_arclink_docker.py`, Docker/security docs, `GAPS.md`,
  `USER_JOURNEY.md`, and `IMPLEMENTATION_PLAN.md`: repaired `GAP-019-Q`
  locally by changing `agent-user-helper` from Docker's default Linux
  capabilities to `cap_drop: ALL` with only `CHOWN`, `DAC_OVERRIDE`, and
  `FOWNER` added back. The inventory now records the exact add-back boundary,
  and tests fail if Compose drifts back to default capabilities or overclaims
  `all_dropped` while `cap_add` is present.
- `python/arclink_agent_process_helper.py`,
  `python/arclink_docker_agent_supervisor.py`, `compose.yaml`,
  `bin/arclink-docker.sh`, `bin/docker-entrypoint.sh`, `bin/deploy.sh`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`,
  `tests/test_deploy_regressions.py`, Docker/security docs, `GAPS.md`,
  `USER_JOURNEY.md`, and `IMPLEMENTATION_PLAN.md`: repaired `GAP-019-P`
  locally by moving Docker-mode setpriv process execution and
  gateway/dashboard process handles out of `agent-supervisor` and into a
  tokened `agent-process-helper` that rejects raw commands, validates typed
  agent context, and fails closed without helper URL/token.
- `python/arclink_agent_user_helper.py`,
  `python/arclink_docker_agent_supervisor.py`, `compose.yaml`,
  `bin/arclink-docker.sh`, `bin/docker-entrypoint.sh`, `bin/deploy.sh`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`,
  Docker/security docs, `GAPS.md`, `USER_JOURNEY.md`, and
  `IMPLEMENTATION_PLAN.md`: repaired `GAP-019-O` locally by moving Docker-mode
  user/home setup out of the root `agent-supervisor` and into a tokened
  `agent-user-helper` that rejects raw commands, validates canonical
  agent-home/Hermes-home/workspace paths, and fails closed without helper
  URL/token.
- `python/arclink_pod_migration.py`,
  `python/arclink_migration_capture_helper.py`, `compose.yaml`,
  `bin/arclink-docker.sh`, `bin/docker-entrypoint.sh`, `bin/deploy.sh`,
  `config/docker-authority-inventory.json`,
  `tests/test_arclink_pod_migration.py`,
  `tests/test_arclink_action_worker.py`, `tests/test_arclink_docker.py`,
  Docker/security docs, `GAPS.md`, `USER_JOURNEY.md`, and
  `IMPLEMENTATION_PLAN.md`: repaired `GAP-019-N` locally by moving Docker-mode
  Pod migration file capture/materialization out of the root
  `control-action-worker` and into a tokened `migration-capture-helper` that
  rejects raw commands, validates deployment-scoped paths, and keeps non-dry-run
  capture fail-closed without helper URL/token and root-capture opt-in.
- `python/arclink_api_auth.py`, `python/arclink_hosted_api.py`,
  `docs/openapi/arclink-v1.openapi.json`, `web/src/lib/api.ts`,
  `web/src/app/dashboard/page.tsx`, `tests/test_arclink_hosted_api.py`,
  `web/tests/test_api_client.mjs`, `web/tests/test_page_smoke.mjs`, share
  docs, `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and
  `research/BUILD_COMPLETION_NOTES.md`: repaired `GAP-015-B` locally by adding
  an authenticated retry-notification rail that only queues local
  `notification_outbox` rows for the currently waiting share prompt, fails
  closed without linked public channels, and keeps live Telegram/Discord
  delivery under `PG-BOTS`.
- `tests/test_arclink_telegram.py` and `tests/test_arclink_discord.py`:
  repaired stale fake-adapter expectations so Telegram/Discord match Raven's
  current direct package checkout onboarding flow.
- `tests/test_deploy_regressions.py`: repaired a stale Notion SSOT setup prompt
  expectation so it matches the current Raven vocabulary contract.
- `python/arclink_hosted_api.py`, `docs/openapi/arclink-v1.openapi.json`, and
  `tests/test_arclink_hosted_api.py`: closed `GAP-008` locally by requiring
  `claim_token` and `cancel_token` in dynamic/static OpenAPI and testing both.
- `docs/arclink/foundation.md`, `docs/arclink/foundation-runbook.md`, and
  `tests/test_documentation_truths.py`: closed `GAP-011` locally by aligning
  foundation wording with current Control Node boundaries and adding a stale
  prototype wording guard.
- `tests/test_arclink_auto_provision.py`, `tests/test_nextcloud_user_access.py`,
  `tests/test_arclink_notification_delivery.py`,
  `tests/test_arclink_pin_upgrade_detector.py`, and
  `tests/test_arclink_enrollment_provisioner_regressions.py`: repaired
  broad-suite test isolation leaks around shared `subprocess` and `pwd`
  monkeypatches.
- `tests/test_arclink_sovereign_worker.py`: updated stale Raven handoff
  assertions to match current `Agent #... online` and `Helm:` copy.
- `python/arclink_dashboard.py`, `web/src/app/dashboard/page.tsx`,
  `web/src/components/ui.tsx`, `web/tests/browser/product-checks.spec.ts`, and
  `tests/test_arclink_dashboard.py`: repaired `GAP-007` locally so Notion setup
  reports `local_metadata_verified` instead of bare `verified` while live
  shared-root/workspace proof remains `proof_gated`.
- `compose.yaml`, `tests/test_arclink_docker.py`, `docs/docker.md`,
  `docs/arclink/data-safety.md`, and `docs/arclink/operations-runbook.md`:
  repaired the first local `GAP-019` hardening slice by dropping Linux
  capabilities from non-root Docker-socket services, statically guarding the
  socket/root allowlist, and keeping writeable Docker socket access documented
  as host-root-equivalent.
- `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`,
  `docs/docker.md`, `docs/arclink/data-safety.md`,
  `docs/arclink/operations-runbook.md`, and `USER_JOURNEY.md`: repaired
  `GAP-019-B1` by recording every Docker socket/root service with authority
  class, read/write socket mode, explicit-root status, proxy/broker candidate
  status, monitoring/runbook anchor, and residual policy state; Docker tests now
  fail closed when Compose and the authority inventory drift.
- `python/arclink_action_worker.py`, `tests/test_arclink_action_worker.py`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`,
  and Docker/security docs: repaired `GAP-019-B2` locally by rejecting generic
  Docker socket proxy as a closure claim, recording per-service broker/no-go
  decisions and monitoring controls, and making restart lifecycle path
  overrides fail closed unless
  `ARCLINK_ACTION_WORKER_ALLOW_LIFECYCLE_PATH_OVERRIDES=1` is set.
- `python/arclink_dashboard.py`, `python/arclink_product_surface.py`,
  `web/src/app/admin/page.tsx`, `tests/test_arclink_admin_actions.py`,
  `tests/test_arclink_product_surface.py`, `web/tests/browser/product-checks.spec.ts`,
  `web/tests/test_page_smoke.mjs`, and admin runbooks: repaired `GAP-018-A`
  locally by exposing the support/readiness matrix for restart, reprovision,
  DNS repair, Chutes key rotation, refund, cancel, comp, and pending actions,
  including operation kind, required adapter, proof boundary, local contract,
  and fail-closed reason.
- `python/arclink_notification_delivery.py`,
  `tests/test_arclink_notification_delivery.py`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`,
  and Docker/security docs: repaired `GAP-019-C` locally for the
  public-Agent bridge path by rejecting detached bridge jobs whose Docker
  command is outside the generated `hermes-gateway` allowlist or whose Compose
  fallback files escape `ARCLINK_STATE_ROOT_BASE`.
- `compose.yaml`, `config/docker-authority-inventory.json`,
  `tests/test_arclink_docker.py`, Docker/security docs, `GAPS.md`,
  `USER_JOURNEY.md`, and `IMPLEMENTATION_PLAN.md`: repaired `GAP-019-D`
  locally by removing the Docker socket mount and socket group from
  `curator-refresh` and recording that queued Docker-mode upgrade execution
  remains in the trusted-host enrollment provisioner path.
- `python/arclink_executor.py`, `tests/test_arclink_executor.py`,
  `tests/test_arclink_sovereign_worker.py`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`,
  Docker/security docs, `GAPS.md`, `USER_JOURNEY.md`, and
  `IMPLEMENTATION_PLAN.md`: repaired `GAP-019-E` locally by rejecting unsafe
  live Docker executor deployment ids, mismatched apply project names, and
  env/compose paths outside `ARCLINK_STATE_ROOT_BASE` before Docker runner
  dispatch.
- `python/arclink_executor.py`, `python/arclink_deployment_exec_broker.py`,
  `python/arclink_sovereign_worker.py`, `compose.yaml`,
  `bin/docker-entrypoint.sh`, `bin/arclink-docker.sh`, `bin/deploy.sh`,
  `config/docker-authority-inventory.json`, executor/sovereign/Docker/deploy
  tests, Docker/security docs, `GAPS.md`, `USER_JOURNEY.md`, and
  `IMPLEMENTATION_PLAN.md`: repaired `GAP-019-G` locally by moving local
  deployment Compose execution from `control-provisioner` to
  `deployment-exec-broker` and removing the provisioner's Docker socket.
- `python/arclink_executor.py`, `compose.yaml`,
  `config/docker-authority-inventory.json`,
  `tests/test_arclink_action_worker.py`, `tests/test_arclink_executor.py`,
  `tests/test_arclink_docker.py`, Docker/security docs, `GAPS.md`,
  `USER_JOURNEY.md`, and `IMPLEMENTATION_PLAN.md`: repaired `GAP-019-H`
  locally by removing direct Docker socket authority from
  `control-action-worker` and requiring the deployment exec broker for
  Docker-mode local action lifecycle/apply work.
- `python/arclink_docker_agent_supervisor.py`,
  `python/arclink_agent_supervisor_broker.py`, `compose.yaml`,
  `bin/docker-entrypoint.sh`, `bin/arclink-docker.sh`, `bin/deploy.sh`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`,
  Docker/security docs, `GAPS.md`, `USER_JOURNEY.md`, and
  `IMPLEMENTATION_PLAN.md`: repaired `GAP-019-I` locally by removing direct
  Docker socket authority from `agent-supervisor` and requiring the agent
  supervisor broker for Docker-mode dashboard network/proxy sidecar work.
- `python/arclink_enrollment_provisioner.py`,
  `python/arclink_agent_supervisor_broker.py`, `compose.yaml`,
  `config/docker-authority-inventory.json`,
  `tests/test_arclink_enrollment_provisioner_regressions.py`,
  `tests/test_arclink_docker.py`, Docker/security docs, `GAPS.md`,
  `USER_JOURNEY.md`, and `IMPLEMENTATION_PLAN.md`: repaired `GAP-019-J`
  locally by routing Docker-mode queued host upgrades and pinned-component
  upgrade apply/final-upgrade calls through the agent supervisor broker,
  rejecting raw command fields, validating private operator-action log
  confinement, and keeping the broker socket plus host checkout mount residual
  risk visible.
- `python/arclink_pod_migration.py`, `python/arclink_action_worker.py`,
  `compose.yaml`, `config/docker-authority-inventory.json`,
  `tests/test_arclink_pod_migration.py`, `tests/test_arclink_action_worker.py`,
  `tests/test_arclink_docker.py`, Docker/security docs, `GAPS.md`,
  `USER_JOURNEY.md`, and `IMPLEMENTATION_PLAN.md`: repaired `GAP-019-K`
  locally by making non-dry-run Pod migration capture require explicit
root-capture opt-in, preserving dry-run planning without that window, and
validating capture paths before root file copy.
- `python/arclink_docker_agent_supervisor.py`,
  `config/docker-authority-inventory.json`, `tests/test_arclink_docker.py`,
  Docker/security docs, `GAPS.md`, `USER_JOURNEY.md`, and
  `IMPLEMENTATION_PLAN.md`: repaired `GAP-019-L` locally by rejecting unsafe
  active-agent metadata, non-canonical Docker agent homes, unsafe Hermes homes,
  workspace/log/process keys, agent process env keys, and command arguments
  before root user-management, broker requests, or subprocess launch.
- `web/src/app/onboarding/page.tsx`,
  `web/src/app/checkout/success/page.tsx`,
  `web/src/app/checkout/cancel/page.tsx`, `web/tests/test_page_smoke.mjs`,
  `web/tests/browser/product-checks.spec.ts`, `GAPS.md`, `USER_JOURNEY.md`,
  and `IMPLEMENTATION_PLAN.md`: repaired `GAP-009` locally by keeping browser
  claim/cancel proof tokens out of durable `localStorage`, using
  session-scoped proof storage for checkout success/cancel, and testing
  placement plus cleanup with static and fake-browser coverage.
- `web/src/app/onboarding/page.tsx`, `web/tests/test_page_smoke.mjs`,
  `web/tests/browser/product-checks.spec.ts`, `GAPS.md`, `USER_JOURNEY.md`,
  and `IMPLEMENTATION_PLAN.md`: repaired `GAP-010` locally by removing the
  stale Telegram/Discord continuation promise from web-only onboarding,
  showing an explicit unlinked-platform notice for `?channel=telegram|discord`,
  and testing that the start payload remains `channel: "web"` until a real
  platform identity is linked.
- `python/arclink_dashboard.py`, `web/src/app/dashboard/page.tsx`,
  `web/src/components/ui.tsx`, `tests/test_arclink_public_bots.py`,
  `tests/test_arclink_dashboard.py`, `tests/test_arclink_hosted_api.py`,
  `web/tests/test_page_smoke.mjs`, `GAPS.md`, `USER_JOURNEY.md`, and
  `IMPLEMENTATION_PLAN.md`: reduced `GAP-013` locally by projecting Raven's
  backup-prep metadata into the user dashboard as `pending_key_setup`, while
  keeping deploy-key setup pending, backup inactive, and restore proof
  `proof_gated`.
- `web/src/app/dashboard/page.tsx`, `web/src/lib/api.ts`,
  `web/src/components/ui.tsx`, `web/tests/test_page_smoke.mjs`,
  `web/tests/test_api_client.mjs`, `GAPS.md`, `USER_JOURNEY.md`,
  `IMPLEMENTATION_PLAN.md`, and `research/BUILD_COMPLETION_NOTES.md`: closed
  `GAP-013-C` locally by exposing the staged backup deploy-key and write-check
  API routes in the dashboard, showing the staged public key and GitHub
  settings URL, and keeping backup activation/restore proof visibly gated.
- `bin/arclink-restore-smoke.sh`, `tests/test_backup_git_regressions.py`,
  `tests/test_agent_backup_regressions.py`,
  `docs/arclink/backup-restore.md`, `GAPS.md`, `USER_JOURNEY.md`,
  `IMPLEMENTATION_PLAN.md`, and `research/BUILD_COMPLETION_NOTES.md`: reduced
  `GAP-020` locally by adding a no-secret restore-smoke helper and tests for
  shared and agent-home backup artifacts while keeping live disaster recovery
  proof under `PG-BACKUP`.
- `IMPLEMENTATION_PLAN.md`, `research/RESEARCH_SUMMARY.md`, and
  `research/STACK_SNAPSHOT.md`: refreshed this handoff after rechecking
  `GAP-025` and then completing the focused `GAP-019-L` build slice.
- `IMPLEMENTATION_PLAN.md`: updated the active repair queue, marked newly
  validated clusters complete, recorded `GAP-019-A`, `GAP-019-B1`, and
  `GAP-019-B2` as repaired, and selected `GAP-018-A` as the next bounded local
  slice.
- `GAPS.md` and `research/COVERAGE_MATRIX.md`: recorded `GAP-008` as locally
  closed, recorded `GAP-011` and `GAP-025` as locally closed, recorded the
  `GAP-019` local hardening slice, and preserved live proof/policy gates.
- `research/BUILD_COMPLETION_NOTES.md`: added the repair note and validation
  result for this slice.
- `USER_JOURNEY.md`: kept the full ArcLink experience story, added a one-page
  journey synopsis, added a fast handoff and terminal closeout rule for future
  agents, added a reviewer acceptance checklist, preserved proof-gated live
  language, and named the model-provider router context.
- `GAPS.md`: kept the original 24 source-grounded gap rows, added an operator decision
  summary, added an ordered implementation-planning ladder, added a P0/P1 launch
  decision ledger, added terminal closeout guidance, and preserved
  proof/policy/test closure rules. A follow-up audit added `GAP-025` after the
  initial broad Python suite failure that was later repaired.
- `research/BUILD_COMPLETION_NOTES.md`: recorded the document handoff,
  inspected artifacts, validation commands, retry repair, and remaining gates.
- `mission_status.md`: replaced the stale lint-phase status with this document
  handoff status.

## Retry 5 Repair

The previous document attempt reached GO/no-gap review outcomes, but the
handoff and consensus scores were below the configured 92-point phase
threshold. This retry did not widen product claims or run live proof; it made
the handoff more explicit so the next agent can see reading order, acceptance
criteria, planning order, launch-decision closure type, terminal document-phase
closure rules, and remaining operator-gated proof/policy work without
inference.

## Local Validation

- Focused GAP-019-R source probe reproduced that `agent-process-helper` wrote
  a fake token-like env value to `state/docker/agent-process-helper/*.log`
  through the reconstructed setpriv command.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_agent_process_helper_does_not_log_or_argv_env_values tests/test_arclink_docker.py::test_docker_agent_supervisor_does_not_forward_helper_tokens_to_agent_processes --maxfail=1`
  passed after the `GAP-019-R` redaction/filtering repair: 2 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_agent_process_helper_does_not_log_or_argv_env_values tests/test_arclink_docker.py::test_docker_agent_supervisor_does_not_forward_helper_tokens_to_agent_processes tests/test_arclink_docker.py::test_docker_authority_inventory_matches_compose_boundary --maxfail=1`
  passed after the `GAP-019-R` inventory update: 3 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_agent_process_helper_rejects_raw_commands_and_runs_allowlisted_agent_ops tests/test_arclink_docker.py::test_docker_agent_supervisor_delegates_process_launch_to_process_helper tests/test_arclink_docker.py::test_docker_agent_supervisor_replaces_user_systemd_units --maxfail=1`
  passed after the `GAP-019-R` existing contract recheck: 3 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed
  after the `GAP-019-R` authority update: 28 tests.
- `python3 -m py_compile python/arclink_agent_process_helper.py python/arclink_docker_agent_supervisor.py`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed
  after the `GAP-019-R` repair.
- `python3 -m pytest -q tests` passed after the `GAP-019-R` repair: 1258
  passed, 6 skipped, 81 warnings in 62.66s.
- Focused GAP-019-Q source probe reproduced that `agent-user-helper` was an
  explicit root helper with no Docker socket but default Linux capabilities in
  Compose and the authority inventory.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_agent_user_helper_root_boundary_uses_explicit_minimum_capabilities tests/test_arclink_docker.py::test_docker_authority_inventory_matches_compose_boundary --maxfail=1`
  passed after the `GAP-019-Q` capability/inventory repair: 2 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_agent_user_helper_rejects_raw_commands_and_unscoped_paths tests/test_arclink_docker.py::test_docker_agent_supervisor_requires_user_helper_before_root_user_ops tests/test_arclink_docker.py::test_compose_defines_full_stack_services --maxfail=1`
  passed after the `GAP-019-Q` helper delegation recheck: 3 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed
  after the `GAP-019-Q` authority update: 26 tests.
- `python3 -m py_compile python/arclink_agent_user_helper.py python/arclink_docker_agent_supervisor.py`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed
  after the `GAP-019-Q` repair.
- `python3 -m pytest -q tests` passed after the `GAP-019-Q` repair: 1256
  passed, 6 skipped, 81 warnings in 63.05s.
- Focused GAP-019-P source probe reproduced that `agent-supervisor` still
  declared root, owned setpriv/subprocess process launch, and had no dedicated
  `agent-process-helper`.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_agent_process_helper_rejects_raw_commands_and_runs_allowlisted_agent_ops tests/test_arclink_docker.py::test_docker_agent_supervisor_delegates_process_launch_to_process_helper --maxfail=1`
  passed after the `GAP-019-P` process-helper split: 2 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed
  after the `GAP-019-P` process-helper split: 25 tests.
- `python3 -m pytest -q tests/test_deploy_regressions.py::test_control_docker_bootstrap_seeds_session_hash_pepper_and_gateway_broker_token --maxfail=1`
  passed after the `GAP-019-P` token/bootstrap update: 1 test.
- `python3 -m py_compile python/arclink_docker_agent_supervisor.py python/arclink_agent_process_helper.py`,
  `bash -n deploy.sh bin/*.sh test.sh`, `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed
  after the `GAP-019-P` repair.
- `python3 -m pytest -q tests` passed after the `GAP-019-P` repair: 1255
  passed, 6 skipped, 81 warnings in 62.87s.
- Focused GAP-019-O source probe reproduced that `agent-supervisor` still owned
  direct user/home setup and no dedicated `agent-user-helper` existed.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_agent_user_helper_rejects_raw_commands_and_unscoped_paths tests/test_arclink_docker.py::test_docker_agent_supervisor_rejects_unsafe_metadata_before_root_ops tests/test_arclink_docker.py::test_docker_agent_supervisor_requires_user_helper_before_root_user_ops tests/test_arclink_docker.py::test_docker_agent_supervisor_replaces_user_systemd_units tests/test_arclink_docker.py::test_docker_authority_inventory_matches_compose_boundary --maxfail=1`
  passed after the `GAP-019-O` helper/setpriv split: 5 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed
  after the `GAP-019-O` helper split: 23 tests.
- `python3 -m pytest -q tests/test_deploy_regressions.py::test_control_docker_bootstrap_seeds_session_hash_pepper_and_gateway_broker_token --maxfail=1`
  passed after the `GAP-019-O` token/bootstrap update: 1 test.
- `python3 -m py_compile python/arclink_docker_agent_supervisor.py python/arclink_agent_user_helper.py`,
  `bash -n deploy.sh bin/*.sh test.sh`, `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed
  after the `GAP-019-O` repair.
- `python3 -m pytest -q tests` passed after the `GAP-019-O` repair: 1253
  passed, 6 skipped, 81 warnings in 63.00s.
- `python3 -m pytest -q tests/test_arclink_pod_migration.py::test_migration_capture_requires_helper_in_docker_mode tests/test_arclink_pod_migration.py::test_migration_capture_uses_helper_when_configured tests/test_arclink_pod_migration.py::test_migration_capture_helper_rejects_raw_commands_and_unscoped_paths tests/test_arclink_action_worker.py::test_reprovision_non_dry_run_requires_migration_capture_helper_in_docker_mode --maxfail=1` passed after the `GAP-019-N` source repair: 4 tests.
- `python3 -m pytest -q tests/test_arclink_action_worker.py tests/test_arclink_pod_migration.py tests/test_arclink_docker.py --maxfail=20` passed after the `GAP-019-N` boundary/inventory/docs update: 68 tests.
- `python3 -m py_compile python/arclink_pod_migration.py python/arclink_migration_capture_helper.py python/arclink_action_worker.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `python3 tests/test_documentation_truths.py` passed.
- `python3 -m pytest -q tests` passed after the `GAP-019-N` repair: 1251 passed, 6 skipped, 81 warnings in 63.42s.
- `python3 -m pytest -q tests/test_arclink_hosted_api.py::test_user_share_grant_retry_notification_requires_session_csrf_and_scopes_participants tests/test_arclink_hosted_api.py::test_user_share_grant_retry_notification_queues_after_public_channel_link --maxfail=1` passed after the `GAP-015-B` retry repair: 2 tests.
- `python3 -m pytest -q tests/test_arclink_hosted_api.py::test_user_share_grants_create_approved_accepted_linked_resources tests/test_arclink_hosted_api.py::test_user_share_grants_inbox_requires_session_and_scopes_owner_recipient tests/test_arclink_hosted_api.py::test_openapi_spec_matches_static_copy --maxfail=1` passed after the `GAP-015-B` route/OpenAPI update: 3 tests.
- `cd web && node --test tests/test_api_client.mjs tests/test_page_smoke.mjs` passed after the `GAP-015-B` web client/dashboard update: 75 tests.
- `python3 -m pytest -q tests/test_arclink_hosted_api.py tests/test_arclink_dashboard.py --maxfail=20` passed after the `GAP-015-B` repair: 97 tests.
- `cd web && npm run lint` passed after the `GAP-015-B` web update.
- `python3 -m pytest -q tests` passed after the `GAP-015-B` repair: 1247 passed, 6 skipped, 81 warnings.
- `python3 -m pytest -q tests/test_arclink_public_bots.py tests/test_arclink_telegram.py tests/test_arclink_discord.py --maxfail=20` passed after the public-bot adapter repair.
- `python3 -m pytest -q tests/test_arclink_onboarding_notion.py tests/test_arclink_ctl_notion.py tests/test_notion_ssot.py tests/test_arclink_notion_knowledge.py tests/test_arclink_notion_webhook.py tests/test_arclink_ssot_batcher.py tests/test_arclink_notion_skill_text.py --maxfail=20` passed.
- `python3 -m pytest -q tests/test_arclink_plugins.py --maxfail=20` passed.
- `python3 -m pytest -q tests/test_deploy_regressions.py tests/test_health_regressions.py --maxfail=20` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `python3 -m pytest -q tests/test_arclink_repo_sync.py tests/test_backup_git_regressions.py tests/test_agent_backup_regressions.py tests/test_vault_bootstrap_layout.py tests/test_vault_watch_regressions.py tests/test_vault_symlink_regressions.py --maxfail=20` passed.
- `python3 -m pytest -q tests/test_arclink_hosted_api.py --maxfail=20` passed.
- `git diff --check` passed.
- `python3 tests/test_documentation_truths.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m pytest -q tests/test_arclink_auto_provision.py tests/test_arclink_context_telemetry.py tests/test_arclink_ctl_notion.py tests/test_arclink_memory_sync.py tests/test_arclink_onboarding_notion.py --maxfail=20` passed: 40 tests.
- `python3 -m pytest -q tests/test_nextcloud_user_access.py tests/test_arclink_notification_delivery.py tests/test_arclink_pin_upgrade_detector.py --maxfail=20` passed: 35 tests.
- `python3 -m pytest -q tests/test_arclink_notification_delivery.py tests/test_arclink_pins.py tests/test_arclink_plugins.py --maxfail=20` passed: 65 tests.
- `python3 -m pytest -q tests/test_arclink_sovereign_worker.py --maxfail=20`
  passed: 19 tests.
- `python3 tests/test_arclink_dashboard.py` passed after the `GAP-007` local
  state-machine repair.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed after
  the `GAP-019` local hardening slice: 16 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed after
  the `GAP-019-B1` authority inventory slice: 17 tests.
- `python3 -m pytest -q tests` passed before the `GAP-019-B2` patch: 1212
  passed, 6 skipped.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_action_worker.py tests/test_arclink_executor.py --maxfail=20`
  passed after the `GAP-019-B2` broker review/action-worker guard: 84 tests.
- `python3 -m pytest -q tests` passed after the `GAP-019-B2` repair: 1214
  passed, 6 skipped.
- `python3 -m pytest -q tests/test_arclink_admin_actions.py tests/test_arclink_product_surface.py tests/test_arclink_dashboard.py tests/test_arclink_action_worker.py tests/test_arclink_executor.py --maxfail=20`
  passed after the `GAP-018-A` readiness matrix repair: 87 tests.
- `cd web && npm test` passed after the `GAP-018-A` UI update: 69 web tests.
- `cd web && npm run lint` passed after the `GAP-018-A` UI update.
- `python3 -m pytest -q tests` passed after the `GAP-018-A` repair: 1215
  passed, 6 skipped.
- `python3 tests/test_arclink_notification_delivery.py` passed after the
  `GAP-019-C` public-Agent bridge guard: 18 notification-delivery regressions.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_notification_delivery.py --maxfail=20`
  passed after the `GAP-019-C` inventory/docs guard: 36 tests.
- `python3 -m pytest -q tests` passed after the `GAP-019-C` repair: 1217
  passed, 6 skipped.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed after
  the `GAP-019-D` socket removal: 17 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_enrollment_provisioner_regressions.py --maxfail=20`
  passed after the `GAP-019-D` routing/inventory check: 41 tests.
- `python3 tests/test_documentation_truths.py` passed after the `GAP-019-D`
  docs update: 7 tests.
- `git diff --check` passed after the `GAP-019-D` repair.
- `python3 -m pytest -q tests` passed after the `GAP-019-D` repair: 1217
  passed, 6 skipped.
- `python3 -m pytest -q tests/test_arclink_executor.py tests/test_arclink_sovereign_worker.py tests/test_arclink_docker.py --maxfail=20`
  passed after the `GAP-019-E` executor preflight: 73 tests.
- `python3 -m pytest -q tests/test_arclink_action_worker.py tests/test_arclink_pod_migration.py --maxfail=20`
  passed after the `GAP-019-E` adjacent executor check: 38 tests.
- `python3 -m pytest -q tests` passed after the `GAP-019-E` repair: 1220
  passed, 6 skipped.
- `python3 -m pytest -q tests/test_arclink_notification_delivery.py tests/test_arclink_docker.py --maxfail=20`
  passed after the `GAP-019-F` gateway exec broker split: 39 tests.
- `python3 -m pytest -q tests/test_deploy_regressions.py --maxfail=20`
  passed after the `GAP-019-F` Docker runtime config update: 117 tests.
- `python3 -m pytest -q tests` passed after the `GAP-019-F` repair: 1223
  passed, 6 skipped.
- `python3 -m pytest -q tests/test_arclink_executor.py tests/test_arclink_sovereign_worker.py tests/test_arclink_docker.py --maxfail=20`
  passed after the `GAP-019-G` deployment exec broker split: 75 tests.
- `python3 -m pytest -q tests/test_deploy_regressions.py --maxfail=20`
  passed after the `GAP-019-G` Docker runtime token update: 117 tests.
- `python3 -m pytest -q tests/test_arclink_action_worker.py tests/test_arclink_pod_migration.py tests/test_arclink_docker.py --maxfail=20`
  passed as the `GAP-019-H` baseline: 55 tests.
- `python3 -m pytest -q tests/test_arclink_action_worker.py tests/test_arclink_pod_migration.py tests/test_arclink_docker.py tests/test_arclink_executor.py --maxfail=20`
  passed after the `GAP-019-H` action-worker socket removal: 95 tests.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`
  passed after the `GAP-019-H` inventory update.
- `python3 tests/test_documentation_truths.py` passed after the `GAP-019-H`
  docs update: 7 tests.
- `git diff --check` passed after the `GAP-019-H` repair.
- `python3 -m pytest -q tests` passed after the `GAP-019-H` repair: 1226
  passed, 6 skipped.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_agent_user_services.py tests/test_arclink_enrollment_provisioner_regressions.py --maxfail=20`
  passed as the `GAP-019-I` baseline: 45 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed
  after the `GAP-019-I` agent supervisor broker split: 18 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_agent_user_services.py tests/test_arclink_enrollment_provisioner_regressions.py --maxfail=20`
  passed after the `GAP-019-I` agent supervisor broker split: 46 tests.
- `python3 -m pytest -q tests/test_deploy_regressions.py::test_control_docker_bootstrap_seeds_session_hash_pepper_and_gateway_broker_token`
  passed after the `GAP-019-I` Docker runtime token update.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`, and `git diff --check` passed
  after the `GAP-019-I` docs/inventory update.
- `python3 -m pytest -q tests` passed after the `GAP-019-I` repair: 1227
  passed, 6 skipped.
- `python3 -m pytest -q tests/test_arclink_enrollment_provisioner_regressions.py::test_run_host_upgrade_routes_to_docker_upgrade_in_docker_mode tests/test_arclink_docker.py::test_docker_component_upgrade_apply_loads_upstream_env_from_docker_config tests/test_arclink_docker.py::test_compose_defines_full_stack_services --maxfail=20`
  passed as the `GAP-019-J` baseline: 3 tests.
- `python3 -m pytest -q tests/test_arclink_enrollment_provisioner_regressions.py::test_run_host_upgrade_routes_to_docker_upgrade_in_docker_mode tests/test_arclink_enrollment_provisioner_regressions.py::test_run_host_upgrade_fails_closed_without_broker_token_in_docker_mode tests/test_arclink_enrollment_provisioner_regressions.py::test_run_pin_upgrade_action_uses_agent_supervisor_broker_in_docker_mode tests/test_arclink_docker.py::test_compose_defines_full_stack_services tests/test_arclink_docker.py::test_docker_authority_inventory_matches_compose_boundary tests/test_arclink_docker.py::test_agent_supervisor_broker_runs_allowlisted_operator_upgrade tests/test_arclink_docker.py::test_agent_supervisor_broker_rejects_raw_or_unsafe_operator_upgrade_requests --maxfail=20`
  passed after the `GAP-019-J` broker routing repair: 7 tests.
- `python3 -m py_compile python/arclink_enrollment_provisioner.py python/arclink_agent_supervisor_broker.py` passed.
- `python3 -m pytest -q tests/test_arclink_enrollment_provisioner_regressions.py tests/test_arclink_docker.py --maxfail=20`
  passed after the `GAP-019-J` repair: 46 tests.
- `python3 -m pytest -q tests/test_arclink_action_worker.py tests/test_arclink_pod_migration.py tests/test_arclink_docker.py::test_docker_authority_inventory_matches_compose_boundary --maxfail=20`
  passed as the `GAP-019-K` baseline: 40 tests.
- Focused GAP-019-K root-capture probe failed before the repair with
  `MISSING: non-dry-run Pod migration capture ran without explicit root-capture
  opt-in`.
- `python3 -m pytest -q tests/test_arclink_pod_migration.py tests/test_arclink_action_worker.py tests/test_arclink_docker.py::test_docker_authority_inventory_matches_compose_boundary --maxfail=20`
  passed after the `GAP-019-K` repair: 43 tests.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`, and `git diff --check` passed
  after the `GAP-019-K` docs/inventory update.
- `python3 -m py_compile python/arclink_pod_migration.py python/arclink_action_worker.py`
  passed after the `GAP-019-K` source update.
- `python3 -m pytest -q tests` passed after the `GAP-019-K` repair: 1234
  passed, 6 skipped.
- `python3 -m pytest -q tests` passed during the `GAP-019-L` plan refresh:
  1234 passed, 6 skipped.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_agent_user_services.py tests/test_arclink_enrollment_provisioner_regressions.py --maxfail=20`
  passed as the current `GAP-019-L` owner-family baseline: 50 tests.
- Focused GAP-019-L metadata probe failed before the repair because unsafe
  `unix_user` reached monkeypatched `id`, `useradd`, and recursive `chown`
  command construction instead of failing closed.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_docker_agent_supervisor_rejects_unsafe_metadata_before_root_ops`
  passed after the `GAP-019-L` repair: 1 test.
- `python3 -m pytest -q tests/test_arclink_docker.py tests/test_arclink_agent_user_services.py tests/test_arclink_enrollment_provisioner_regressions.py --maxfail=20`
  passed after the `GAP-019-L` repair: 51 tests.
- `python3 -m pytest -q tests` passed after the `GAP-019-L` repair: 1235
  passed, 6 skipped.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_docker_authority_inventory_matches_compose_boundary tests/test_arclink_docker.py::test_docker_docs_cover_socket_and_private_state_boundaries --maxfail=20`
  passed after the `GAP-019-M` incident-control ledger repair: 2 tests.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed
  after the `GAP-019-M` repair: 21 tests.
- `python3 -m pytest -q tests/test_arclink_plugins.py tests/test_arclink_mcp_schemas.py --maxfail=20`
  passed as the next `GAP-016` baseline: 45 tests.
- `python3 -m pytest -q tests/test_arclink_mcp_schemas.py::test_agent_share_request_tool_creates_scoped_pending_grant tests/test_arclink_plugins.py::test_arclink_drive_and_code_expose_read_only_linked_root --maxfail=20`
  passed during the `GAP-016` plan refresh: 2 tests.
- `python3 -m pytest -q tests/test_arclink_plugins.py tests/test_arclink_mcp_schemas.py --maxfail=20`
  passed during the `GAP-016` plan refresh: 45 tests.
- `git diff --check`, `python3 tests/test_public_repo_hygiene.py`, and
  `python3 tests/test_documentation_truths.py` passed after the `GAP-016`
  handoff artifact refresh.
- `python3 -m pytest -q tests` passed during the `GAP-016` plan refresh:
  1235 passed, 6 skipped, 81 warnings in 62.91s.
- GAP-009 reproduction command failed before the patch because `claimToken` and
  `cancelToken` touched the `localStorage` resume restore/persist paths.
- `cd web && npm test` passed after the `GAP-009` repair: 70 tests.
- `cd web && npm run lint` passed after the `GAP-009` repair.
- `cd web && npx playwright test tests/browser/product-checks.spec.ts --grep "Onboarding flow"`
  passed after the `GAP-009` repair: 6 desktop/mobile fake-API checks.
- `python3 -m pytest -q tests` passed after the `GAP-009` repair: 1235
  passed, 6 skipped, 81 warnings in 62.54s.
- GAP-010 reproduction command passed before the patch because the web page
  still promised Telegram/Discord continuation while the start payload stayed
  `channel: "web"`.
- Post-repair GAP-010 source assertion passed after stale continuation copy was
  removed and the unlinked-platform notice was added.
- `cd web && npm test` passed after the `GAP-010` repair: 71 tests.
- `cd web && npm run lint` passed after the `GAP-010` repair.
- `cd web && npx playwright test tests/browser/product-checks.spec.ts --grep "Onboarding flow"`
  passed after the `GAP-010` repair: 8 desktop/mobile fake-API checks.
- GAP-013 static reproduction passed: Raven records pending backup status while
  the dashboard has no matching status surface.
- Post-repair GAP-013 source assertion passed after the dashboard began
  exposing `config_backup_public_status` as `pending_key_setup` without a live
  restore claim.
- `python3 -m pytest -q tests/test_arclink_public_bots.py::test_public_bot_config_backup_collects_private_repo_without_secret_leakage tests/test_arclink_dashboard.py::test_user_dashboard_projects_raven_backup_pending_key_setup tests/test_arclink_hosted_api.py::test_user_dashboard_requires_session_auth --maxfail=1`
  passed after the `GAP-013` repair: 3 tests.
- `python3 -m pytest -q tests/test_arclink_public_bots.py tests/test_arclink_dashboard.py tests/test_arclink_hosted_api.py --maxfail=20`
  passed after the `GAP-013` repair: 124 tests.
- `cd web && npm test` and `cd web && npm run lint` passed after the
  `GAP-013` dashboard UI repair.
- `python3 -m pytest -q tests` passed after the `GAP-013` repair: 1236
  passed, 6 skipped, 81 warnings in 63.45s.
- `python3 -m pytest -q tests` passed after the `GAP-010` repair and final
  evidence updates: 1235 passed, 6 skipped, 81 warnings in 62.56s.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and touched-file
  `git diff --check` passed after the `GAP-019-M` docs/inventory update.
- `python3 -m pytest -q tests` passed after the `GAP-019-M` repair: 1235
  passed, 6 skipped.
- `python3 -m pytest -q tests` passed after the `GAP-019-J` repair: 1231
  passed, 6 skipped.
- `python3 -m pytest -q tests` passed after the `GAP-007` repair: 1211
  passed, 6 skipped.
- `python3 -m pytest -q tests` passed after the `GAP-019` repair: 1211 passed,
  6 skipped.
- Targeted scan of the latest handoff section and root handoff docs found no
  absolute local path, private-key marker, obvious token prefix, or
  live-proof-passed overclaim.
- Root handoff docs cover the required journey surfaces, including provider
  inference/router and refuel, with no live-proof upgrade.
- GAP-019-AA reproduction showed `deployment-exec-broker` inherited broad
  `*arclink-env` before the patch and no longer inherits it after the patch,
  while preserving the deployment state-root bind, writeable Docker socket, and
  `cap_drop: ALL`.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'deployment_exec_broker or authority_inventory or compose'`
  passed after the `GAP-019-AA` repair: 7 passed, 29 deselected.
- `python3 -m pytest -q tests/test_arclink_executor.py -k 'deployment_exec_broker or local_executor_uses_deployment_exec_broker'`
  passed after the `GAP-019-AA` repair: 2 passed, 37 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py --maxfail=20` passed
  after the `GAP-019-AA` repair: 36 passed.
- `python3 -m pytest -q tests/test_arclink_executor.py --maxfail=20` passed
  after the `GAP-019-AA` repair: 39 passed.
- `python3 -m json.tool config/docker-authority-inventory.json >/dev/null`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`, and `git diff --check` passed
  after the `GAP-019-AA` docs/inventory update.
- `python3 -m pytest -q tests` passed after the `GAP-019-AA` repair: 1266
  passed, 6 skipped, 81 warnings in 63.58s.

## Current Proof Boundary

Local broad Python validation is green in this checkout, but production live
proof remains explicitly unclaimed. The outstanding live gates stay in
`GAPS.md` as `PG-PROD`, `PG-STRIPE`, `PG-BOTS`, `PG-PROVISION`, `PG-FLEET`,
`PG-INGRESS`, `PG-PROVIDER`, `PG-NOTION`, `PG-HERMES`, `PG-BACKUP`, and
`PG-UPGRADE`. The Sovereign Control Node symphony pass added `GAP-029`
through `GAP-033` for full-service Operator Raven, worker readiness, router
fallback, rolling ArcPod/Hermes updates, and cross-surface experience proof;
the local Control Node install repairs now collect operator Raven channel
intent, router model/fallback policy, and prevent workerless installs from
looking product-ready by disabling provisioning until a starter worker is
selected or a remote worker smoke test passes. The router now has local
non-streaming fallback retries for configured retryable upstream failures, and
Control Node install/reconfigure/worker registration prints provisioning
readiness; streaming fallback, dashboard/Operator Raven readiness surfacing,
and live provider/worker proof remain open.
`GAP-016`, `GAP-009`, and `GAP-010` are locally closed, and
`GAP-019-N` through `GAP-019-R` are locally repaired as migration-capture,
agent-user, agent-process, agent-user-helper capability, and process-helper env
exposure hardening slices, `GAP-019-X` through `GAP-019-AB` are locally
repaired as service-env/private-mount narrowing slices for the process helper,
gateway broker, dashboard broker, deployment broker, and operator-upgrade
broker, and `GAP-019-AE` is locally repaired as agent-user-helper root
executable lookup hardening. `GAP-019` remains open for remaining broker/root
helper residual risk, stronger isolation, runtime alert integration, or
operator residual-risk acceptance. `GAP-013` now has a local Raven/dashboard
pending status handoff and fail-closed write-check boundary, while restore
proof remains `PG-BACKUP`.

## 2026-05-27 GAP-032-A ArcPod Rollout Dry-Run Planner

Scope: local Sovereign Control Node rolling-update planning only. This pass
adds a source-owned dry-run planner without running deploy, Docker, SSH,
provider, bot, host, or live proof commands.

Files changed:

- `python/arclink_rollout.py`: added `plan_arcpod_update_rollout(...)`, which
  selects active ArcPod candidates, validates batch-size policy, blocks missing
  state-root metadata and unhealthy service rows, preserves rollback/state-root
  requirements, and exposes pending health/smoke proof fields without creating
  rollout rows or action intents.
- `python/arclink_dashboard.py`: exposes the dry-run plan through scale
  operations when a rollout target version is supplied.
- `python/arclink_operator_raven.py`: adds a dry-run-only `/rollout_plan`
  command and keeps chat output path-free and secret-free.
- `tests/test_arclink_rollout.py`, `tests/test_arclink_dashboard.py`, and
  `tests/test_arclink_operator_raven.py`: cover deterministic batching,
  blocked preflights, batch limits, no mutation, dashboard surfacing, and
  Operator Raven dry-run behavior.
- `GAPS.md`, `USER_JOURNEY.md`,
  `docs/arclink/sovereign-control-node-symphony.md`,
  `IMPLEMENTATION_PLAN.md`, and this status file: record the local repair
  without claiming rolling-update execution or live proof.

Validation:

- Reproduction before repair: importing `arclink_rollout.py` and asserting
  `plan_arcpod_update_rollout` existed failed with `AssertionError: missing
  plan_arcpod_update_rollout dry-run helper`.
- `python3 tests/test_arclink_rollout.py` passed: 13 tests.
- `python3 tests/test_arclink_dashboard.py` passed: 12 tests.
- `python3 tests/test_arclink_operator_raven.py` passed: 6 tests.
- `python3 tests/test_arclink_admin_actions.py` passed: 9 tests.
- Targeted hosted API scale-operations test passed:
  `test_admin_scale_operations_requires_auth_and_returns_snapshot`.
- `python3 -m py_compile python/arclink_rollout.py python/arclink_dashboard.py python/arclink_operator_raven.py`
  passed.
- `python3 tests/test_documentation_truths.py` passed: 10 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1319 passed, 6 skipped, 89 warnings
  in 64.33s.

Residual risk:

- `GAP-032` remains open for worker-backed typed execution, bounded batch
  apply, real backup freshness enforcement, per-Pod health/smoke collection,
  rollback/repair execution, and authorized `PG-UPGRADE`/`PG-HERMES` proof.

## 2026-05-27 GAP-032-B Local Typed Rollout Jobs

Scope: local Sovereign Control Node rollout job materialization. No
deploy/install/upgrade, Docker, systemd, SSH, provider, Stripe, bot,
Cloudflare, Tailscale, host mutation, or live proof command was run.

Files changed:

- `python/arclink_rollout.py`: added
  `materialize_arcpod_update_rollout_job(...)`, which validates a ready
  dry-run plan, creates deterministic per-Pod planned rollout rows, preserves
  batch order, rollback/state-root metadata, pending health/smoke proof fields,
  backup-freshness placeholders, proof gates, and idempotent replay behavior.
- `python/arclink_action_worker.py`: dispatches `rollout` by rerunning the
  local planner, refusing blocked/empty preflight plans, materializing the
  typed local job, linking `arcpod_update_rollout`, and returning secret-free
  metadata without calling executor side-effect methods.
- `python/arclink_dashboard.py`, `web/src/app/admin/page.tsx`, and product
  surface/web tests: moved `rollout` from unwired pending action to locally
  modeled action while keeping `PG-UPGRADE/PG-HERMES` live proof copy visible.
- `GAPS.md`, `USER_JOURNEY.md`,
  `docs/arclink/sovereign-control-node-symphony.md`,
  `IMPLEMENTATION_PLAN.md`, and this status file: record the local repair
  without claiming bounded refresh/apply execution or live rolling updates.

Validation:

- Reproduction before repair: `python3 tests/test_arclink_action_worker.py`
  passed because no rollout worker coverage existed; after adding the new tests,
  `python3 tests/test_arclink_rollout.py` failed with missing
  `materialize_arcpod_update_rollout_job`.
- `python3 tests/test_arclink_rollout.py` passed: 16 tests.
- `python3 tests/test_arclink_action_worker.py` passed: 39 tests.
- `python3 tests/test_arclink_admin_actions.py` passed: 9 tests.
- `python3 tests/test_arclink_dashboard.py` passed: 12 tests.
- `python3 tests/test_arclink_operator_raven.py` passed: 6 tests.
- `python3 tests/test_arclink_upgrade_notifications.py` passed: 9 tests.
- `python3 tests/test_arclink_pin_upgrade_detector.py` passed: 10 tests.
- `python3 tests/test_arclink_hosted_api.py` passed: 81 tests.
- `python3 tests/test_arclink_product_surface.py` passed: 5 tests.
- `python3 -m py_compile python/arclink_rollout.py python/arclink_action_worker.py python/arclink_dashboard.py python/arclink_operator_raven.py`
  passed.
- `python3 tests/test_documentation_truths.py` passed: 10 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `cd web && npm test` passed: 75 tests.
- `cd web && npm run lint` passed.
- `cd web && npm run build` passed.
- `cd web && npx playwright test tests/browser/product-checks.spec.ts --grep "Admin"`
  passed on rerun: 7 passed, 1 skipped. The first attempt overlapped with
  `npm run build` and the Playwright web server failed startup with
  `Unexpected end of JSON input`.
- `python3 -m pytest -q tests` passed: 1325 passed, 6 skipped, 89 warnings in
  64.55s.

Residual risk:

- `GAP-032` still needs bounded per-Pod refresh/apply execution, backup
  freshness enforcement beyond the dry-run placeholder, real health/smoke
  collection, rollback/repair execution, and authorized `PG-UPGRADE`/
  `PG-HERMES` proof.

## 2026-05-27 GAP-032-C Bounded Local Rollout Execution

Scope: reduced `GAP-032` from local job materialization to a bounded
fake/local batch execution recorder. No deploy/install/upgrade, Docker,
systemd, SSH, provider, Stripe, bot, Cloudflare, Tailscale, host mutation, or
live proof command was run.

Files changed:

- `python/arclink_rollout.py`: added
  `execute_arcpod_update_rollout_batch(...)`. It requires an explicit
  fake/local `record_only=true` executor contract, prevalidates fake results
  before row mutation, records intended refresh/apply steps, transitions
  rollout rows through `in_progress` to `completed` or `failed`, preserves
  proof gates, health/smoke placeholders, backup placeholders, repair hints,
  stop-on-failure behavior, and idempotent completed-batch replay.
- `python/arclink_action_worker.py`: keeps normal `rollout` actions as local
  materialization, and only records one batch when `execute_local_batch` or
  `execute_batch` metadata is explicit and the selected executor adapter is
  fake/local.
- `python/arclink_dashboard.py`, `python/arclink_operator_raven.py`, and
  `web/src/app/admin/page.tsx`: expose truthful local rollout execution state
  while keeping live `PG-UPGRADE`/`PG-HERMES` proof pending.
- `GAPS.md`, `USER_JOURNEY.md`,
  `docs/arclink/sovereign-control-node-symphony.md`,
  `IMPLEMENTATION_PLAN.md`, and this status file: record that local fake
  execution exists without claiming real refresh/apply or live rolling updates.

Validation:

- Reproduction before repair:
  `PYTHONPATH=python python3 - <<'PY' ... hasattr(arclink_rollout, 'execute_arcpod_update_rollout_batch') ... PY`
  failed with `AssertionError: missing execute_arcpod_update_rollout_batch local execution helper`.
- Focused tests passed:
  `python3 tests/test_arclink_rollout.py` (19 tests),
  `python3 tests/test_arclink_action_worker.py` (40 tests),
  `python3 tests/test_arclink_admin_actions.py` (9 tests),
  `python3 tests/test_arclink_dashboard.py` (12 tests),
  `python3 tests/test_arclink_operator_raven.py` (6 tests),
  `python3 tests/test_arclink_upgrade_notifications.py` (9 tests),
  `python3 tests/test_arclink_pin_upgrade_detector.py` (10 tests), and
  `python3 tests/test_arclink_product_surface.py` (5 tests).
- Compile/docs/hygiene/web checks passed:
  `python3 -m py_compile python/arclink_rollout.py python/arclink_action_worker.py python/arclink_dashboard.py python/arclink_operator_raven.py`,
  `python3 tests/test_documentation_truths.py`,
  `python3 tests/test_public_repo_hygiene.py`,
  `git diff --check`, `cd web && npm test`, `cd web && npm run lint`,
  `cd web && npm run build`, and
  `cd web && npx playwright test tests/browser/product-checks.spec.ts --grep "Admin"`
  with 7 passed and 1 skipped.
- Broad suite passed: `python3 -m pytest -q tests` with 1329 passed, 6 skipped,
  89 warnings in 65.23s.

Residual risk:

- `GAP-032` remains open for authorized real refresh/apply execution, backup
  freshness enforcement beyond local placeholders, real per-Pod health/smoke
  collection, rollback/repair execution, and redacted `PG-UPGRADE`/
  `PG-HERMES` proof.
- The next unattended local queue row is `GAP-034-A` Academy schema and
  source-lane registry.
