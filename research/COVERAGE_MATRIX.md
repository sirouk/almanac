# Coverage Matrix

## Wave 3 Goal Coverage

| Goal / criterion | Current PLAN coverage | BUILD proof required |
| --- | --- | --- |
| Use ArcPod steering Wave 3 as authority | `IMPLEMENTATION_PLAN.md`, this matrix, and the research summary scope to `## Wave 3: 1:1 Pod Migration` | Completion notes cite Wave 3 items, not older Sovereign audit or Waves 4-6. |
| Do not retouch Waves 0-2 | Plan treats them as landed unless a direct regression blocks migration | Diff review shows no unrelated vocabulary, onboarding, or inventory churn. |
| Add `python/arclink_pod_migration.py` | Candidate module exists in the dirty tree | Tests and review confirm planning, capture, target materialization, verification, rollback, audit, replay, dry-run, and GC. |
| Extend migration schema | Candidate schema includes source/target placements, hosts, roots, manifests, verification, retention, GC, indexes, and drift checks | Schema tests pass from a fresh DB and protect status/relationship drift. |
| Wire admin `reprovision` | Candidate dashboard/action-worker wiring exists | Admin actions/readiness tests show `reprovision` executable when probes pass, linked to `pod_migration`, and fail-closed otherwise. |
| Preserve state-capture boundaries | Research names vault, memory, sessions, configs, secrets refs, DNS rows, placement, bot env, and Hermes home | Migration tests use representative temporary state and assert manifests contain relative paths/digests, not contents or secret values. |
| Gate Captain migration | Plan requires `ARCLINK_CAPTAIN_MIGRATION_ENABLED=0` default off | No Captain route/button ships, or route tests prove disabled-by-default CSRF/session behavior if BUILD adds one. |
| Idempotent replay | Plan uses operation key `arclink:migration:<migration_id>` and existing idempotency helpers | Tests show same migration id/key replays prior result and changed inputs under the same key fail. |
| Rollback on verification failure | Candidate module marks rollback and restores source placement | Tests assert rollback metadata, audit/events, placement state, and worker result. |
| Migration GC | Candidate helper exposes retention-based GC | Tests cover succeeded-expired rows and refuse failed, rolled-back, cancelled, and recent rows. |
| Docs/OpenAPI | Runbooks already have candidate Operator-only notes; OpenAPI only changes if a route changes | Docs match behavior after tests pass; no Captain self-service promise while flag is off. |
| Respect constraints | Build gate blocks private/live/Hermes core changes | Completion notes list skipped live gates and no private-state access. |

## Required Artifact Coverage

| Artifact | PLAN status |
| --- | --- |
| `research/RESEARCH_SUMMARY.md` | Wave 3-only summary with `<confidence>`, current findings, path comparison, assumptions, risks, and verdict. |
| `research/CODEBASE_MAP.md` | Wave 3 map of directories, entrypoints, architecture assumptions, and current handoff surfaces. |
| `research/DEPENDENCY_RESEARCH.md` | Stack components, alternatives, integration posture, risks, and validation dependencies for migration. |
| `research/COVERAGE_MATRIX.md` | Goal-to-proof matrix for every Wave 3 requirement. |
| `research/STACK_SNAPSHOT.md` | Ranked stack hypotheses with deterministic confidence score and alternatives. |
| `IMPLEMENTATION_PLAN.md` | Project-specific Wave 3 implementation plan with validation criteria and actionable tasks. |
| `consensus/build_gate.md` | Existing no-secret BUILD gate remains applicable; no new blocker gate is required. |

## Focused Test Coverage

| Test file | Required Wave 3 proof |
| --- | --- |
| `tests/test_arclink_pod_migration.py` | Capture manifest/digests, target materialization, verification success, rollback on failure, idempotent replay, dry-run, and GC. |
| `tests/test_arclink_action_worker.py` | `reprovision` dispatch, action-operation link, dry-run result, safe failure, legacy unsupported action behavior, and redacted errors. |
| `tests/test_arclink_admin_actions.py` | `reprovision` executable readiness when executor probes pass; queue policy remains fail-closed when executor disabled. |
| `tests/test_arclink_sovereign_worker.py` | Shared apply/health behavior still works after any helper extraction or reuse. |
| `tests/test_arclink_executor.py` | Any new transfer/lifecycle/rollback executor behavior has fake idempotency coverage. |
| `tests/test_arclink_schema.py` | Migration table shape, status constants, indexes, drift checks, and idempotent schema migration. |
| `tests/test_arclink_fleet.py` | Placement swap/remove/load behavior if new fleet helpers are added. |
| `tests/test_arclink_api_auth.py` and `tests/test_arclink_hosted_api.py` | Captain migration route disabled by default if BUILD adds a route. |

## Completion Rules

BUILD can claim Wave 3 complete only when every Wave 3 checklist item is
implemented locally with focused tests or explicitly deferred with:

- checklist item;
- risk if left unresolved;
- current fail-closed or disabled behavior;
- exact operator action or policy decision needed;
- focused tests preserving the interim boundary.

Do not route to terminal done while any Wave 3 item remains unresolved or lacks
a project-specific deferral.
