# Research Summary

<confidence>94</confidence>

## Scope

This PLAN pass inspected the public ArcLink repository structure, the ArcPod
Captain Console steering document, current Wave 3 migration surfaces, existing
tests, runbook updates, and the required planning artifacts.

No private state, live secrets, user Hermes homes, deploy keys, production
services, provider accounts, payment flows, public bot command registration, or
Hermes core were inspected.

## Active Mission

The active BUILD backlog is Wave 3 from:

`research/RALPHIE_ARCPOD_CAPTAIN_CONSOLE_STEERING.md`

The user-provided goals document supersedes the older bootstrap line about
starting with the Sovereign audit Wave 1 repairs. Historical audit files remain
background only. Waves 0 through 2 are treated as landed at commit `b32e1da`
unless BUILD discovers a direct regression that blocks Wave 3.

## Current Worktree Findings

| Area | Finding |
| --- | --- |
| Control schema | `python/arclink_control.py` now contains an `arclink_pod_migrations` table with source/target placement ids, source/target host ids, target machine id, source/target state roots, capture directory, manifest JSON, rollback metadata, verification JSON, target metadata, retention/GC timestamps, status checks, indexes, and drift checks. |
| Migration module | `python/arclink_pod_migration.py` is present in the dirty tree. It plans migrations, captures source state with relative file digests, materializes target state, applies through the executor, verifies health through an injectable verifier, rolls back on failure, records audit/events, supports idempotent replay, handles dry-run planning, and exposes GC. |
| Admin action wiring | `python/arclink_dashboard.py` includes `reprovision` in `ARCLINK_EXECUTABLE_ADMIN_ACTION_TYPES` when executor readiness passes. `python/arclink_action_worker.py` imports `migrate_pod` and dispatches `reprovision` to operation kind `pod_migration`. |
| Tests | `tests/test_arclink_pod_migration.py` exists with coverage for capture/materialization/success replay, rollback replay, GC, and dry-run. `tests/test_arclink_action_worker.py`, `tests/test_arclink_admin_actions.py`, and `tests/test_arclink_schema.py` contain Wave 3 additions. |
| Docs/config | `config/arclink.env.example`, `config/env.example`, `docs/arclink/control-node-production-runbook.md`, and `docs/arclink/operations-runbook.md` contain Operator-only migration and GC notes. |
| Captain migration | No Captain-facing migration route was identified. This matches the required default posture: `ARCLINK_CAPTAIN_MIGRATION_ENABLED=0` and Operator-only initial rollout. |
| Remaining proof | Candidate implementation is present but must be validated as a coherent BUILD patch. This PLAN pass did not run the validation floor. |

## Runtime Stack Summary

ArcLink is a Python-led control platform with SQLite control state, Bash
operator entrypoints, Docker Compose runtime lanes, ArcLink-owned Hermes
plugins/hooks, and a Next.js product/admin surface. Wave 3 should stay on the
existing Python control-plane, executor, provisioning, fleet, action-worker,
and schema rails.

## Implementation Path Comparison

| Path | Strengths | Weaknesses | Decision |
| --- | --- | --- | --- |
| Dedicated `arclink_pod_migration.py` orchestrator reusing provisioning, fleet, executor, operation idempotency, audit, and action-worker rails | Keeps capture, rollback, replay, and GC testable; matches current candidate worktree; avoids deploy-script or Hermes-core surgery | Requires careful validation of transaction boundaries and portable manifests | Selected. |
| Fold migration into `arclink_sovereign_worker.py` | Reuses nearby apply and health conventions | Expands the provisioning worker into a migration engine and makes replay/rollback tests harder | Rejected. |
| Add one opaque executor-level migration operation | Centralizes host operations | Hides DB state transitions, capture manifests, placement changes, and audit from the control plane | Rejected. |
| Manual runbook only | Lowest immediate code change | Does not satisfy Wave 3 or remove `pending_not_implemented` for `reprovision` | Rejected. |

## Build Assumptions

- Current source and focused tests are ground truth where historical docs
  disagree.
- The dirty worktree contains user or prior generated changes and must not be
  reverted during BUILD.
- Wave 3 remains Operator-only at launch. Captain-initiated migration stays
  disabled by default behind `ARCLINK_CAPTAIN_MIGRATION_ENABLED=0`.
- Local tests should use temporary control DBs, fake executors, and temporary
  state trees; they must not read private state or real user homes.
- Migration manifests may store relative paths, sizes, modes, boundaries, and
  digests, but not file contents or secret values.

## Risks

- Current capture uses local filesystem copy semantics. Live SSH/rsync transfer
  remains proof-gated and should not be inferred from fake/local tests.
- State capture must not leak secret values through manifests, audit, errors,
  or action-worker results.
- Rollback must leave exactly one active placement and must not delete source
  artifacts before the retention window.
- Idempotency must reject changed intent for the same migration id while
  returning prior terminal results for true replay.
- GC must only act on succeeded migrations past retention and must not touch
  failed, rolled-back, cancelled, or recent migrations.

## Verdict

PLAN is ready for Wave 3 BUILD handoff. The BUILD phase should validate the
candidate Wave 3 patch, tighten any gaps found by the focused tests, and avoid
live/private proof unless the operator explicitly authorizes a named flow.
