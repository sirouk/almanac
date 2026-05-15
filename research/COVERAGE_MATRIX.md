# Coverage Matrix

## Mission Coverage

| Goal / criterion | PLAN coverage | BUILD proof required |
| --- | --- | --- |
| Resolve audit Wave 1 posture | Phase 0 verifies current source against the trust-boundary audit items before Wrapped work | Focused audit/security tests pass; any regression is fixed with a new/updated regression. |
| Ignore fiction items | Plan explicitly excludes `ME-11` and `ME-25` except as regression awareness | Completion notes state they were not backlogged as source gaps. |
| Land ArcLink Wrapped | Plan adds `python/arclink_wrapped.py`, scheduler, delivery, API, bot, dashboard, docs, and tests | `tests/test_arclink_wrapped.py` and dependent suites pass. |
| Deterministic report generation | Plan requires `generate_wrapped_report(conn, user_id, period, period_start, period_end)` | Tests seed events/audit/Comms/memory/session/vault fixtures and assert stable output. |
| At least five non-standard stats | Plan requires a documented stats set and scoring formula | Tests assert five or more named non-standard statistics for a rich period and graceful sparse output. |
| Novelty score | Plan defines a deterministic formula and docs page | Tests assert score inputs, score bounds, stable score, and prior-period deltas. |
| Redaction | Plan reuses `arclink_evidence.redact_value`/shared redaction before render/store/delivery | Tests seed token-like strings and assert no secret-shaped text reaches `ledger_json`, text, markdown, or outbox. |
| Cadence | Plan exposes daily/weekly/monthly only and rejects more frequent settings | API and bot tests cover valid/invalid frequencies, default daily, and mutation audit. |
| Scheduler | Plan adds a named job-loop integration | Compose/deploy regression asserts service/runner exists and has no Docker socket; scheduler tests assert due/skip/retry behavior. |
| Failed report retry | Plan keeps failed reports eligible next cycle | Wrapped tests assert failed rows do not permanently suppress later generation. |
| Persistent failure notification | Plan queues operator notification after threshold | Wrapped/notification tests assert safe operator row with no Captain narrative. |
| Captain delivery | Plan queues `notification_outbox` with `target_kind='captain-wrapped'` | Notification tests assert target/channel/extra shape and retry fields. |
| Quiet hours | Plan computes delayed `next_attempt_at` where quiet-hours data is supported | Tests cover inside/outside quiet window and conservative unsupported fallback. |
| Captain dashboard | Plan adds Wrapped tab/history/frequency selector | Web unit/smoke/browser tests assert tab rendering, history, no overflow, and frequency mutation. |
| Operator privacy | Plan adds aggregate-only admin status | API/dashboard tests assert no narrative, markdown, snippets, or raw ledger in admin response. |
| Public bot command | Plan adds `/wrapped-frequency daily|weekly|monthly` | Public bot tests prove command parsing and rejection without live bot mutation. |
| Vocabulary closeout | Plan sweeps required Captain-facing surfaces | Grep/regression assertions prove stale user-facing phrases are removed or intentionally backend-only. |
| Onboarding identity verification | Plan re-verifies web, Telegram, and Discord Agent Name/Title flows | Existing or added tests prove input acceptance and flow to deployment row and SOUL/identity projection. |
| Cross-wave schema usage | Plan verifies five Wave 0 tables are written and read by owning waves | Tests or source assertions cover inventory, Comms, migration, Crew Recipes, and Wrapped. |
| Docs/OpenAPI reconciliation | Plan updates docs after behavior is true | API reference, architecture, doc status, and OpenAPI list all final Wave 0-6 routes/surfaces. |
| Steering-doc reconciliation | Plan updates steering status or closing commit/status section | Steering doc no longer implies landed waves are open without context. |
| Completion notes | Plan requires a comprehensive six-wave entry | `research/BUILD_COMPLETION_NOTES.md` lists files changed per wave, schema deltas, env vars, validation, skipped live gates, and residual risks. |
| Broad validation | Plan includes Python, shell, web, lint, build, browser checks | Completion notes record pass/fail/skip with rationale for unavailable live gates. |

## Required Artifact Coverage

| Artifact | PLAN status |
| --- | --- |
| `research/RESEARCH_SUMMARY.md` | Updated with `<confidence>`, mission reconciliation, findings, path comparison, assumptions, risks, and verdict. |
| `research/CODEBASE_MAP.md` | Updated with current directory map, architecture rails, Wave 0-5 source state, and Wave 6 target surfaces. |
| `research/DEPENDENCY_RESEARCH.md` | Updated with stack components, alternatives, external integration posture, risks, and validation dependencies. |
| `research/COVERAGE_MATRIX.md` | Updated with audit gate, Wave 6, and Mission Closeout proof matrix. |
| `research/STACK_SNAPSHOT.md` | Updated with ranked stack hypotheses, deterministic confidence score, and alternatives. |
| `IMPLEMENTATION_PLAN.md` | Rewritten as project-specific audit-gate plus Wave 6 and closeout plan. |
| `consensus/build_gate.md` | Updated from stale Wave 5 gate to no-secret Wave 6/closeout BUILD gate. |

## Focused Test Coverage Targets

| Test file | Required proof |
| --- | --- |
| `tests/test_arclink_wrapped.py` | Report generation, source scoping, stats, novelty score, redaction, persistence, due cadence, failed retry, operator failure notification, admin aggregate privacy. |
| `tests/test_arclink_notification_delivery.py` | `captain-wrapped` outbox target handling, retry fields, quiet-hours delay semantics, and safe failure text. |
| `tests/test_arclink_dashboard.py` | User snapshot/history/frequency and admin aggregate-only Wrapped fields. |
| `tests/test_arclink_hosted_api.py` | User Wrapped history/frequency routes, admin aggregate route, auth/CSRF/CIDR/body handling, OpenAPI route entries. |
| `tests/test_arclink_api_auth.py` | Frequency validation, user scope, admin privacy, mutation audit. |
| `tests/test_arclink_public_bots.py` | `/wrapped-frequency` command and invalid cadence rejection without live command registration. |
| `tests/test_arclink_schema.py` | Existing Wrapped schema and any added columns/checks/drift probes. |
| `tests/test_deploy_regressions.py` or Docker-focused suite | Compose/job-loop runner presence, no Docker socket for Wrapped service, shell syntax coverage. |
| `web/tests/test_api_client.mjs` | Wrapped API client helpers. |
| `web/tests/test_page_smoke.mjs` | Dashboard/Admin Wrapped tab smoke. |
| `web/tests/browser/product-checks.spec.ts` | Captain Wrapped tab/frequency interaction and closeout vocabulary/onboarding proof. |

## Completion Rules

BUILD can claim complete only when:

- audit Wave 1 verification passes or regressions are fixed;
- ArcLink Wrapped is locally implemented with focused tests;
- all seven Mission Closeout items are satisfied or explicitly deferred with
  operator-facing rationale;
- broad local validation is recorded;
- live/private/provider/deploy gates remain blocked unless separately
  authorized.

Do not route to terminal done while any Wrapped or Mission Closeout item remains
unresolved or lacks a project-specific deferral.
