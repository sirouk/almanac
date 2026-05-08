# Coverage Matrix

## Goal Coverage Against BUILD Backlog

| Goal / criterion | Current coverage | Remaining BUILD gap | Validation surface |
| --- | --- | --- | --- |
| High-risk dashboard, qmd, Notion, SSOT, token, generated cleanup, and path traversal boundaries | Slices 1 security items are checked in the plan and steering file | Preserve fail-closed behavior whenever plugin, install, qmd, Notion, PDF, or resource-sync code is touched | `tests/test_arclink_plugins.py`, `tests/test_arclink_agent_user_services.py`, `tests/test_loopback_service_hardening.py`, `tests/test_arclink_notion_knowledge.py`, `tests/test_notion_ssot.py`, `tests/test_ssot_broker.py`, `tests/test_pdf_ingest_env.py` |
| Hosted web onboarding, checkout, auth, login, status, dashboard, and admin views | Slice 2 hosted web/API items are checked | Preserve HttpOnly/CSRF, user/admin scoping, fake/live copy, checkout truth, and API shape handling while extending journeys | `tests/test_arclink_api_auth.py`, `tests/test_arclink_hosted_api.py`, `tests/test_arclink_dashboard.py`, `web/tests/test_api_client.mjs`, `web/tests/browser/product-checks.spec.ts` |
| Admin/provisioning surfaces are truthful | Slice 3 control-plane truthfulness items are checked | Preserve unavailable/dry-run/pending/applied/proof state distinctions | `tests/test_arclink_action_worker.py`, `tests/test_arclink_admin_actions.py`, `tests/test_arclink_provisioning.py`, `tests/test_arclink_sovereign_worker.py`, `tests/test_arclink_fleet.py`, `tests/test_arclink_rollout.py`, `tests/test_arclink_evidence.py`, `tests/test_arclink_live_runner.py` |
| Shared Host, Docker, and Control Node operations have matching docs, defaults, health, and dependency coverage | Slice 4 Shared Host and Docker operational parity items are checked | Preserve branch default, dependency, health, release-state, Nextcloud, path quoting, and Docker trust-boundary repairs while updating docs | `tests/test_arclink_docker.py`, `tests/test_deploy_regressions.py`, `tests/test_health_regressions.py`, shell syntax checks |
| Private Curator onboarding failure/cancel/skip/retry paths are visible and recoverable | Slice 5 private onboarding items are checked | Preserve failure surfacing, credential-channel policy, denial cleanup, durable backup skip, completion-ack retry, and provider validation | `tests/test_arclink_curator_onboarding_regressions.py`, `tests/test_arclink_enrollment_provisioner_regressions.py`, `tests/test_onboarding_completion_messages.py`, provider-auth tests |
| Public bot onboarding failure/cancel/skip/retry paths are visible and recoverable | Slice 5 public bot onboarding items are checked | Preserve public `/cancel` semantics, backup and Notion command clarity, API-key provider validation, and fake/live-safe behavior | `tests/test_arclink_public_bots.py`, `tests/test_arclink_telegram.py`, `tests/test_arclink_discord.py`, `tests/test_arclink_onboarding_prompts.py` |
| Knowledge freshness and generated markdown safety match `AGENTS.md` | Slice 6 knowledge freshness and generated content safety items are checked | Preserve endpoint redaction, full-source hashing, PDF rewrite detection, SSOT claim/lock, resource skill text, and generated-root containment whenever knowledge code is touched | `tests/test_pdf_ingest_env.py`, `tests/test_memory_synthesizer.py`, `tests/test_arclink_ssot_batcher.py`, `tests/test_arclink_resources_skill.py`, `tests/test_arclink_notion_webhook.py` |
| Docs classify canonical versus stale/speculative/proof-gated material | Slice 7 documentation tasks are checked in the active plan and steering file | BUILD review must confirm docs still match behavior in the dirty worktree and keep live/proof-gated claims explicit | `tests/test_documentation_truths.py`, public hygiene checks, docs review |
| Validation is run and summarized | Validation floor and web/live-proof prerequisites are documented in the plan | BUILD must run the relevant no-secret checks and summarize skipped proof-gated checks with concrete reasons | `git diff --check`, `bash -n`, focused Python tests, `npm test`, `npm run lint`, `npm run test:browser` when applicable |

## Slice Coverage

| Slice | Current status | Exit criteria |
| --- | --- | --- |
| 1. Security and trust boundaries | Completed baseline gate | Relevant tests rerun whenever touched; no secret/path/retrieval/destructive boundary regression. |
| 2. Hosted web/API journey | Completed baseline gate | Browser contract remains coherent; success/cancel/status reflect backend state; user/admin scopes are enforced. |
| 3. Control-plane truthfulness | Completed baseline gate | Admin actions, provisioner, fleet, rollout, and evidence remain truthful about disabled, pending, dry-run, applied, failed, skipped, and proof-gated states. |
| 4. Shared Host and Docker operations | Completed baseline gate | Bare-metal and Docker docs/defaults/health agree with code; no live upgrade without operator consent. |
| 5. Onboarding recovery | Completed baseline gate | Failure, denial, skip, retry, cancel, provider validation, and credential handling remain visible, durable, and recoverable. |
| 6. Knowledge freshness and cleanup | Completed baseline gate | Generated content remains secret-free; freshness uses content hashes; PDF rewrites are detected; SSOT processing is claim-locked. |
| 7. Docs and validation | Completed baseline gate; needs BUILD verification | Canonical/stale/speculative/proof-gated docs remain marked; validation prerequisites and skip conditions match actual checks. |

## Required Artifact Coverage

| Required artifact | Coverage status |
| --- | --- |
| `research/RESEARCH_SUMMARY.md` | Summarizes objective, repository findings, path comparison, current state, assumptions, risks, and PLAN verdict with `<confidence>`. |
| `research/CODEBASE_MAP.md` | Maps root entrypoints, major directories, runtime lanes, Docker services, completed hotspots, remaining hotspots, and architecture assumptions. |
| `research/DEPENDENCY_RESEARCH.md` | Documents stack components, alternatives, source composition, dependency risks, and validation dependencies. |
| `research/COVERAGE_MATRIX.md` | Maps goals and slices to current coverage, remaining BUILD gaps, and validation surfaces. |
| `research/STACK_SNAPSHOT.md` | Provides ranked stack hypotheses, deterministic confidence score, source signals, and alternatives. |
| `IMPLEMENTATION_PLAN.md` | Defines goal, non-negotiables, selected architecture, validation criteria, actionable slices, and BUILD handoff order. |
| `consensus/build_gate.md` | Allows no-secret BUILD work; names proof-gated flows; no planning-only blocker is identified. |

## Coverage Verdict

Planning coverage is sufficient for BUILD handoff. The BUILD phase should not
claim completion until every unchecked item in `IMPLEMENTATION_PLAN.md` and
`research/RALPHIE_ARCLINK_ECOSYSTEM_GAP_REPAIR_STEERING.md` is fixed with
tests/docs or explicitly marked blocked with a concrete operator-policy
question.

No planning artifact contains a fallback placeholder marker. No open checkbox
task markers remain in the active implementation plan or steering backlog after
this PLAN pass.
