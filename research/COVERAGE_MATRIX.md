# Coverage Matrix

## Wave 5 Goal Coverage

| Goal / criterion | PLAN coverage | BUILD proof required |
| --- | --- | --- |
| Scope to Wave 5 only | `IMPLEMENTATION_PLAN.md`, research artifacts, and build gate now target Crew Training only | Completion notes cite Wave 5 and list no Wave 6 work unless explicitly deferred as out of scope. |
| Do not re-touch Waves 0-4 | Plan treats Waves 0-4 as landed unless a direct regression blocks Crew Training | Diff review shows no unrelated vocabulary, onboarding, fleet, migration, or Comms churn. |
| Capture Captain inputs | Plan requires role, mission, treatment, preset, and capacity capture | API, bot, and web tests prove values persist to `arclink_users` and preview state. |
| Preset/capacity validation | Plan defines allowed presets and capacities from steering | `tests/test_arclink_crew_recipes.py` rejects unsupported values and normalizes valid values. |
| Provider-backed generation | Plan uses Chutes-compatible injectable generation | Tests prove fake provider path is called when boundary allows inference. |
| Deterministic fallback | Plan requires fallback when no credential/client or generation fails | Tests prove truthful fallback mode and stable preset-only overlay with no live Chutes. |
| Unsafe-output rejection | Plan requires URL, shell-command, and jailbreak rejection with two retries | Tests prove unsafe outputs are rejected, retry count is bounded, and fallback happens after failures. |
| Active recipe lifecycle | Plan requires one active row per Captain and archive of prior active recipe | Tests prove previous active row is archived and only one active recipe remains. |
| Operator-on-behalf audit | Plan includes audited admin application path | API/auth tests prove admin-only access, audit action, actor id, and Captain target scope. |
| Additive SOUL overlay | Plan applies recipe through identity-context projection | Provisioning/recipe tests prove existing keys are preserved and memory/session paths are untouched. |
| Whole Crew application | Plan applies overlay to every Pod owned by the Captain | Tests seed multiple deployments and assert each local identity context receives overlay or records a safe skipped projection reason. |
| Public bot `/train-crew` | Plan adds pure handler questionnaire flow | `tests/test_arclink_public_bots.py` proves step capture, review, regenerate, confirm, and fallback labels without live command registration. |
| Public bot `/whats-changed` | Plan adds current vs prior recipe summary | Tests prove empty, first-recipe, and prior-vs-current responses. |
| Web questionnaire | Plan adds dashboard Crew Training flow | Web tests prove API helpers and page rendering; browser proof walks questionnaire, regenerate, and confirm. |
| Hosted API and OpenAPI | Plan adds user/admin Crew Training routes and docs | Hosted API tests prove route wiring, JSON body handling, CSRF, auth scopes, and generated OpenAPI entries. |
| Runbooks | Plan updates operations and control-node production runbooks after behavior is true | Docs contain Crew Training operation, fallback, no-live-provider, and no-Hermes-restart notes. |
| Constraints | Build gate blocks private/live/Hermes core changes | Completion notes list skipped live gates and confirm no private-state access. |

## Required Artifact Coverage

| Artifact | PLAN status |
| --- | --- |
| `research/RESEARCH_SUMMARY.md` | Wave 5 summary with `<confidence>`, findings, path comparison, assumptions, risks, and verdict. |
| `research/CODEBASE_MAP.md` | Wave 5 map of directories, entrypoints, architecture rails, and source surfaces. |
| `research/DEPENDENCY_RESEARCH.md` | Stack components, alternatives, integration posture, risks, and validation dependencies for Crew Training. |
| `research/COVERAGE_MATRIX.md` | Goal-to-proof matrix for every Wave 5 requirement. |
| `research/STACK_SNAPSHOT.md` | Ranked stack hypotheses with deterministic confidence score and alternatives. |
| `IMPLEMENTATION_PLAN.md` | Project-specific Wave 5 implementation plan with validation criteria and actionable tasks. |
| `consensus/build_gate.md` | No-secret Wave 5 build gate and blocked live/private flows. |

## Focused Test Coverage

| Test file | Required proof |
| --- | --- |
| `tests/test_arclink_crew_recipes.py` | Validation, generation/fallback, unsafe-output rejection, active/archive lifecycle, overlay shape, whole-Crew projection, no memory/session writes, operator-on-behalf audit. |
| `tests/test_arclink_provisioning.py` | Identity-context projection preserves existing fields and includes Crew Recipe overlay fields. |
| `tests/test_arclink_hosted_api.py` | Route wiring, OpenAPI behavior, request/response shape, fallback labeling, and admin/user boundaries. |
| `tests/test_arclink_api_auth.py` | Session auth, CSRF, user scope, admin-on-behalf scope, and forbidden cross-Captain writes. |
| `tests/test_arclink_public_bots.py` | `/train-crew` and `/whats-changed` command handling without live Telegram or Discord mutation. |
| `tests/test_arclink_dashboard.py` | Dashboard snapshots include current recipe, prior recipe summary, and Crew Training readiness. |
| `tests/test_arclink_schema.py` | Existing Crew Recipe schema remains idempotent; any schema delta has drift checks. |
| `web/tests/test_api_client.mjs` | API helper methods for Crew Training routes. |
| `web/tests/test_page_smoke.mjs` | Dashboard route renders with Crew Training UI. |
| Browser test | Questionnaire end-to-end with preview, regenerate, confirm, persistence, and identity-context update without Hermes restart. |

## Completion Rules

BUILD can claim Wave 5 complete only when Crew Training is implemented locally
with focused tests, docs/OpenAPI alignment, and validation notes. Any deferral
must include:

- checklist item;
- risk if left unresolved;
- current fail-closed or disabled behavior;
- exact operator action or policy decision needed;
- focused tests preserving the interim boundary.

Do not route to terminal done while any Wave 5 item remains unresolved or
lacks a project-specific deferral.
