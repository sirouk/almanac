# Coverage Matrix

## Wave Goal Coverage

| Goal / criterion | Current PLAN coverage | BUILD proof required |
| --- | --- | --- |
| Scope to Waves 4-6 | `IMPLEMENTATION_PLAN.md`, this matrix, and research summary now target Wave 4, Wave 5, and Wave 6 only | Completion notes cite Wave 4-6 items, not Wave 3 or older audit backlog. |
| Do not retouch Waves 0-3 | Plan treats Waves 0-3 as landed unless a direct regression blocks later waves | Diff review shows no unrelated vocabulary/onboarding/fleet/migration churn. |
| Wave 4 broker | Plan calls for `python/arclink_pod_comms.py` | Tests prove send/list/deliver/redact, rate limit, notifications, and audit events. |
| Wave 4 authorization | Plan requires same-Captain default allow and cross-Captain active `pod_comms` share grant | Tests prove non-Crew send refusal, accepted grant allow, expired/revoked/pending grant refusal. |
| Wave 4 attachments | Plan requires share-grant projection references only | Tests prove no raw file body/content is stored in message rows. |
| Wave 4 MCP tools | Plan lists `pod_comms.list`, `pod_comms.send`, `pod_comms.share-file` | MCP schema and dispatch tests prove caller scoping and authorization. |
| Wave 4 dashboards/API | Plan adds user/admin comms routes and tabs | API/auth tests prove Captain scope and admin CIDR/session scope; web tests prove tabs render read-only rows. |
| Wave 5 recipe lifecycle | Plan calls for active-row archive/replace semantics | Tests prove one active recipe per Captain and previous active row archived. |
| Wave 5 generation fallback | Plan requires provider-backed generation plus deterministic fallback | Tests prove unsafe output rejection, two retries, and fallback when Chutes unavailable. |
| Wave 5 SOUL overlay | Plan requires additive identity-context overlay only | Tests prove memory/session files are untouched and overlay includes preset/capacity/role/mission/treatment/title. |
| Wave 5 bot/web flows | Plan covers `/train-crew`, `/whats-changed`, and web questionnaire | Handler/API/browser tests prove capture, review, confirm, and diff behavior without live command registration. |
| Wave 6 report generation | Plan calls for `python/arclink_wrapped.py` | Tests prove report reads fixtures from events/audit/comms/memory/session/vault deltas and emits at least five non-standard stats. |
| Wave 6 novelty score | Plan requires documented formula | Tests verify deterministic formula; docs explain inputs and bounds. |
| Wave 6 frequency | Plan uses `wrapped_frequency` daily/weekly/monthly | API/bot tests reject more frequent than daily and persist selected frequency. |
| Wave 6 scheduler | Plan requires job-loop or service integration | Static/shell tests prove wrapper/service command; unit tests prove due-captain selection and retry next cycle. |
| Wave 6 delivery/privacy | Plan requires redaction, quiet hours, notification outbox, Captain narrative, Operator aggregate-only view | Tests prove secret redaction, quiet-hour deferral, `target_kind='captain-wrapped'`, and admin response omits narrative. |
| Docs/OpenAPI | Plan requires update after behavior is true | OpenAPI and runbooks contain new routes/sections matching tests. |
| Constraints | Build gate blocks private/live/Hermes core changes | Completion notes list skipped live gates and no private-state access. |

## Required Artifact Coverage

| Artifact | PLAN status |
| --- | --- |
| `research/RESEARCH_SUMMARY.md` | Wave 4-6 summary with `<confidence>`, current findings, path comparison, assumptions, risks, and verdict. |
| `research/CODEBASE_MAP.md` | Wave 4-6 map of directories, entrypoints, architecture assumptions, and source surfaces. |
| `research/DEPENDENCY_RESEARCH.md` | Stack components, alternatives, integration posture, risks, and validation dependencies for Waves 4-6. |
| `research/COVERAGE_MATRIX.md` | Goal-to-proof matrix for every Wave 4-6 requirement. |
| `research/STACK_SNAPSHOT.md` | Ranked stack hypotheses with deterministic confidence score and alternatives. |
| `IMPLEMENTATION_PLAN.md` | Project-specific Wave 4-6 implementation plan with validation criteria and actionable tasks. |
| `consensus/build_gate.md` | Updated no-secret Wave 4-6 build gate and blockers. |

## Focused Test Coverage

| Test file | Required proof |
| --- | --- |
| `tests/test_arclink_pod_comms.py` | Send/list, same-Captain allow, cross-Captain grant gate, rate limit, notification, audit, redaction, attachments by reference. |
| `tests/test_arclink_mcp_schemas.py` or MCP server tests | `pod_comms.*` schemas and dispatch scoping. |
| `tests/test_arclink_crew_recipes.py` | Recipe generation/fallback, unsafe-output rejection, active/archive lifecycle, overlay shape, operator-on-behalf audit. |
| `tests/test_arclink_wrapped.py` | Report generation, novelty score, five stats, redaction, frequency due logic, retry behavior, aggregate admin view. |
| `tests/test_arclink_api_auth.py` | User/admin comms, Crew Training, Wrapped/frequency auth, CSRF, and scope checks. |
| `tests/test_arclink_hosted_api.py` | Route wiring, OpenAPI route behavior, CIDR/session boundaries. |
| `tests/test_arclink_public_bots.py` | `/train-crew`, `/whats-changed`, `/wrapped-frequency` command handling without live bot mutation. |
| `tests/test_arclink_dashboard.py` | Dashboard snapshots include comms, recipes, wrapped history/aggregate state. |
| `tests/test_arclink_notification_delivery.py` | New target kinds do not break delivery polling and respect quiet-hour/defer semantics where implemented. |
| `tests/test_arclink_schema.py` | Existing Wave 4-6 schema remains idempotent; any new columns/indexes/drift checks are covered. |
| `web/tests/test_api_client.mjs` | API helper methods for new routes. |
| `web/tests/test_page_smoke.mjs` and browser tests | New tabs/questionnaire/history render without overlap and preserve dashboard navigation. |

## Completion Rules

BUILD can claim Waves 4-6 complete only when each wave is implemented locally
with focused tests or explicitly deferred with:

- checklist item;
- risk if left unresolved;
- current fail-closed or disabled behavior;
- exact operator action or policy decision needed;
- focused tests preserving the interim boundary.

Do not route to terminal done while any Wave 4, 5, or 6 item remains unresolved
or lacks a project-specific deferral.
