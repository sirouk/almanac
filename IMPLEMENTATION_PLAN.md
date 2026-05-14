# Wave 3 Implementation Plan: 1:1 Pod Migration

## Goal

Land Wave 3 from `research/RALPHIE_ARCPOD_CAPTAIN_CONSOLE_STEERING.md`: an
Operator-initiated 1:1 Pod migration path that captures a Captain's Pod state,
materializes it on a target placement or redeploys in place, verifies health,
rolls back safely on failure, records audit/idempotency data, garbage-collects
retained source-state artifacts after the retention window, and wires admin
`reprovision` to real migration behavior.

Waves 0 through 2 are treated as landed at commit `b32e1da` and must not be
re-touched unless a direct regression blocks Wave 3. Waves 4 through 6 remain
future work.

## Constraints

- Do not touch `arclink-priv`, live secrets, user Hermes homes, deploy keys,
  production services, external provider accounts, payment/provider mutations,
  public bot command registration, or Hermes core.
- Do not run live deploys, upgrades, Docker install/upgrade flows, Stripe,
  Chutes, Notion, Cloudflare, Tailscale, Hetzner, Linode, Telegram, or Discord
  proof without explicit authorization for the named flow.
- Use existing Python, Bash, SQLite, Compose, Next/web, executor, provisioning,
  fleet, action-worker, and operation-idempotency rails.
- Keep Captain-initiated migration disabled by default behind
  `ARCLINK_CAPTAIN_MIGRATION_ENABLED=0`; initial rollout is Operator-only.
- Store file digests, relative paths, metadata, and secret references; never
  store or print secret values.

## Selected Path

| Path | Strengths | Weaknesses | Decision |
| --- | --- | --- | --- |
| Dedicated `python/arclink_pod_migration.py` orchestrator using existing control DB, provisioning, fleet, executor, operation idempotency, and audit rails | Best fit for tested replay, rollback, capture manifests, GC, and admin action wiring; matches the current candidate worktree | Requires careful transaction and validation review | Selected. |
| Fold migration into `python/arclink_sovereign_worker.py` | Reuses nearby apply and health code | Blurs provisioning and migration ownership and makes focused tests harder | Rejected. |
| Opaque executor-only migration operation | Centralizes host actions | Hides migration state, manifests, audit, placement transitions, and rollback decisions from the control plane | Rejected. |
| Manual runbook only | Least code | Does not satisfy Wave 3 or remove `pending_not_implemented` for `reprovision` | Rejected. |

## Current Candidate State

The dirty worktree already contains a candidate Wave 3 implementation:

- `python/arclink_pod_migration.py`;
- `tests/test_arclink_pod_migration.py`;
- schema/index/drift additions in `python/arclink_control.py`;
- `reprovision` executable readiness and action-worker dispatch;
- config examples for `ARCLINK_CAPTAIN_MIGRATION_ENABLED=0` and
  `ARCLINK_MIGRATION_GC_DAYS=7`;
- Operator-only migration runbook notes.

BUILD should treat these as unverified candidate changes, preserve unrelated
dirty worktree edits, and validate/harden before declaring Wave 3 complete.

## Validation Criteria

Wave 3 BUILD is complete only when:

- migration planning, capture, target materialization, health verification,
  rollback, audit/event recording, idempotent replay, dry-run, and GC pass
  focused tests;
- `arclink_pod_migrations` schema/status/drift coverage includes source/target
  placement links, host links, file digest manifests, rollback metadata,
  verification metadata, retention timestamps, and GC timestamps;
- admin `reprovision` is executable through the existing admin action queue and
  action worker, with redeploy-in-place semantics when the target is blank or
  `current`;
- Captain migration remains disabled by default and documented as Operator-only;
- docs and OpenAPI match actual behavior;
- completion notes list validation commands, skipped live gates, skipped
  private-state proof, residual risks, and any explicit deferrals.

## Actionable Tasks

1. Validate candidate schema
   - Run schema tests from a fresh in-memory DB.
   - Confirm migration statuses are exported and drift checks catch invalid
     status, missing deployment, missing source placement, and missing target
     placement where required.
   - Confirm indexes support deployment/status lookup and GC lookup.

2. Validate migration module behavior
   - Review `plan_pod_migration` for stable migration ids, target host/machine
     resolution, current-host redeploy semantics, and no secret leakage in
     target/reason metadata.
   - Verify capture manifests use relative paths, size, mode, boundary kind,
     and SHA-256 digest only.
   - Verify materialization reuses provisioning intent rendering and applies
     through `ArcLinkExecutor`.
   - Verify dry-run does not mutate files or placements.

3. Validate rollback and idempotency
   - Ensure failed verification restores the source placement, leaves target
     placement removed, records rollback metadata, and emits rollback audit/event
     rows.
   - Ensure successful migration removes source placement, activates target
     placement, updates deployment state roots, and emits completion audit/event
     rows.
   - Ensure replay returns the prior terminal result and changed target intent
     under the same migration id fails.

4. Validate admin action wiring
   - Confirm `reprovision` is in `ARCLINK_EXECUTABLE_ADMIN_ACTION_TYPES` only
     under modeled executor readiness.
   - Confirm action worker links the admin action to operation kind
     `pod_migration`, dispatches `migrate_pod`, supports dry-run, and fails
     safely on non-succeeded non-dry-run results.
   - Keep unsupported legacy actions pending or disabled until separately wired.

5. Validate Captain gate and docs
   - Keep `ARCLINK_CAPTAIN_MIGRATION_ENABLED=0` in public examples.
   - Do not add a Captain dashboard migration button in this wave.
   - If BUILD adds a user route, add CSRF/session tests proving disabled-by-
     default behavior and update OpenAPI.
   - Keep runbook copy Operator-facing and avoid promising self-service
     migration.

6. Validate migration GC
   - Confirm default retention is 7 days through `ARCLINK_MIGRATION_GC_DAYS`.
   - Test succeeded-expired cleanup and non-cleanup for recent, failed,
     rolled-back, and cancelled migrations.
   - Add a job-loop/service wrapper only if current runtime patterns require
     scheduled GC in this wave.

7. Final review and handoff
   - Run the validation floor below.
   - Inspect diff scope for accidental Waves 0-2, Waves 4-6, private-state,
     public bot mutation, or Hermes-core churn.
   - Update completion notes with files changed, schema migrations, env vars,
     validation results, skipped live gates, and residual risks.

## Validation Floor

```bash
git diff --check
python3 -m py_compile python/arclink_pod_migration.py python/arclink_action_worker.py python/arclink_dashboard.py python/arclink_api_auth.py python/arclink_hosted_api.py python/arclink_sovereign_worker.py python/arclink_executor.py
python3 tests/test_arclink_pod_migration.py
python3 tests/test_arclink_action_worker.py
python3 tests/test_arclink_admin_actions.py
python3 tests/test_arclink_sovereign_worker.py
python3 tests/test_arclink_executor.py
python3 tests/test_arclink_schema.py
```

If shell or Compose files change:

```bash
bash -n deploy.sh bin/*.sh test.sh
```

## Completion Notes Required After BUILD

Final BUILD notes must include files changed, schema migrations, new env vars,
validation commands and results, skipped live gates, skipped private-state
proof, and any residual risks or explicit deferrals. Live infrastructure remains
unproven unless the operator separately authorizes named live proof.
