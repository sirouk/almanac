# Coverage Matrix

## Mission Coverage

| Goal / criterion | PLAN coverage | BUILD proof required |
| --- | --- | --- |
| Preserve existing single-host behavior | Phase 1 keeps the env-derived executor fallback when no placement row exists | Existing action-worker SSH/local/fake tests pass; new routing tests prove fallback remains. |
| Formalize two registry tables | Phase 0 keeps `arclink_inventory_machines` and `arclink_fleet_hosts` separate with a 1:1 reconciler | Schema tests cover new columns/tables and orphan drift warnings. |
| Add additive idempotent schema | Phase 0 lists enrollment, probe, audit-chain, and health fields as additive migrations | `ensure_schema` runs twice cleanly; drift checks include new relationships/statuses. |
| Detect orphan inventory/host rows | Phase 0 adds reconciler and audit warnings | Tests seed inventory-only and host-only rows and assert warnings without destructive repair. |
| Fix day-2 action routing | Phase 1 resolves placement per deployment-scoped action and uses host-specific executor | Two-host fake test proves restart/teardown-style actions route to placed host and write audit metadata. |
| Reuse executor construction | Phase 1 factors `_executor_for_host` into `python/arclink_executor.py` | Sovereign worker and action worker tests cover fake/local/ssh helper behavior and key validation. |
| HMAC-bound enrollment tokens | Phase 2 adds token mint/list/revoke and callback consumption | Enrollment tests cover TTL, single use, revoke, expired token, HMAC verification, no cleartext at rest. |
| Machine fingerprint attestation | Phase 2 binds callback to immutable fingerprint and attestation timestamp | Tests cover first attestation, mismatch rejection, and explicit re-attest path. |
| Audit-chain integrity | Phase 2 writes root and transition entries with prev/entry hashes | Health tests verify intact chain and tamper detection with P0 notification row. |
| Bootstrap worker safely | Phase 3 adds idempotent join script and probe wrapper | Shell syntax/shellcheck plus fake command tests prove supported OS checks, fail-closed behavior, wrapper verb allowlist, and JSON output. |
| Periodic probing daemon | Phase 4 adds `arclink_fleet_inventory_worker.py` and Compose job-loop service | Worker tests cover liveness/capacity/inventory cadences, state transitions, retention pruning, and no live SSH dependency. |
| Health summary surface | Phase 4/5 adds `inventory health --json` and optional dashboard helper | Tests assert host counts, capacity, SLI, region coverage, audit-chain status, and no tenant topology leakage. |
| JSON CLI automation | Phase 5 adds `--json` to scriptable inventory/enrollment/fleet commands | Deploy and inventory CLI tests parse JSON and verify documented exit codes. |
| Non-interactive `register-worker` | Phase 5 adds flags for hostname, SSH target, region, capacity, tags, and smoke toggle | Tests call non-interactive path without TTY and assert it routes through the same registration boundary. |
| New control subcommands | Phase 5 adds `enrollment mint|list|revoke` and `inventory health|rotate-key|re-attest|probe-all` | Deploy regression tests assert dispatch, help text, JSON support, and fail-closed invalid argv. |
| Placement strategy consumed | Phase 5/6 ensures `set-strategy` affects placement | Fleet tests prove headroom and standard-unit strategy selection; region-tier preference tests preserve fallback order. |
| Hetzner/Linode provisioning | Phase 6 adds idempotent create/bootstrap/register/remove workflows | Fake-provider tests cover create resume, duplicate prevention, bootstrap failure, drain/remove, and provider reference persistence. |
| Region-tier placement | Phase 6 adds `region_tier`/priority filtering | Placement tests prove primary/secondary/dr preference, degraded exclusion, and explicit DR override. |
| Operator notifications | Phases 2/4/6 enqueue safe notifications for expiry, unreachable, tamper, and capacity | Notification tests assert no tokens, fingerprints, or provider secrets in payloads. |
| Operator runbook | Phase 5/6 writes `docs/arclink/fleet-operator-runbook.md` and CLI docs | Docs list mint, bootstrap, probe, drain, remove, key rotation, audit verification, and DR. |
| Live two-host proof | Phase 7 is explicitly operator-gated | Research evidence file and completion notes are created only after authorization and real run. |
| Mission status honesty | Phase 7 requires status update only after live proof | `mission_status.md` is updated if present or created with honest blocked/proven state. |
| No private/live mutation in CI | All phases use fake runners/providers until Phase 7 | Test suite has no live credential dependency; blocked flows remain documented in `consensus/build_gate.md`. |

## Required Artifact Coverage

| Artifact | PLAN status |
| --- | --- |
| `research/RESEARCH_SUMMARY.md` | Updated with `<confidence>`, source findings, path comparison, assumptions, risks, and verdict. |
| `research/CODEBASE_MAP.md` | Updated with fleet directories, entrypoints, architecture rails, current CLI surfaces, and missing BUILD surfaces. |
| `research/DEPENDENCY_RESEARCH.md` | Updated with stack components, alternatives, external posture, dependency risks, and validation dependencies. |
| `research/COVERAGE_MATRIX.md` | Updated with goal-to-proof coverage for all eight fleet phases. |
| `research/STACK_SNAPSHOT.md` | Updated with ranked stack hypotheses, deterministic confidence score, and alternatives. |
| `IMPLEMENTATION_PLAN.md` | Rewritten as a project-specific eight-phase fleet plan; no fallback marker remains. |
| `consensus/build_gate.md` | Updated to authorize no-secret local BUILD for fleet phases and block live/private actions. |

## Focused Test Coverage Targets

| Test file | Required proof |
| --- | --- |
| `tests/test_arclink_fleet.py` | New schema fields, strategy consumption, region-tier placement, orphan reconciler, active placement compatibility. |
| `tests/test_arclink_inventory.py` | JSON listing/filtering, health summary inputs, probe result mapping, drain/remove behavior, no secret leakage. |
| `tests/test_arclink_action_worker.py` | Placement-aware routing, executor cache, resolved host audit metadata, legacy env fallback, stale claim behavior unchanged. |
| `tests/test_arclink_executor.py` | Shared host executor helper for fake/local/ssh, SSH key validation, allowlist enforcement, redacted errors. |
| `tests/test_arclink_sovereign_worker.py` | Provisioning worker compatibility after helper factoring. |
| `tests/test_arclink_fleet_enrollment.py` | Enrollment mint/list/revoke/callback, HMAC hashing, TTL, single use, fingerprint attestation, audit-chain root. |
| `tests/test_arclink_fleet_inventory_worker.py` | Probe cadences, thresholds, recovery, retention pruning, notification enqueue, fake runner behavior. |
| `tests/test_arclink_inventory_hetzner.py` | Fake Hetzner create/bootstrap/register/remove idempotency. |
| `tests/test_arclink_inventory_linode.py` | Fake Linode create/bootstrap/register/remove idempotency. |
| `tests/test_deploy_regressions.py` | `bin/deploy.sh` dispatch/help/aliases, JSON flags, non-interactive registration, new subcommands, bootstrap script references. |
| `tests/test_arclink_schema.py` | Additive migrations, indexes, CHECK/status validation, relationship drift checks. |
| `tests/test_arclink_hosted_api.py` | Enrollment callback route and any fleet-health admin API route, body caps and auth boundaries. |
| `tests/test_arclink_dashboard.py` | Operator aggregate fleet health, Captain topology non-disclosure. |

## Completion Rules

BUILD can claim complete only when:

- Phases 0-6 are implemented or explicitly deferred with operator-facing
  rationale tied to a blocked live/provider decision;
- Phase 1 action-worker placement routing is implemented, tested, and not
  deferred;
- fiction/outdated audit items are not reintroduced as backlog;
- focused validation passes for every touched surface;
- broad local validation is recorded in completion notes;
- Phase 7 live proof is either completed with evidence or honestly marked
  operator-gated in `mission_status.md` and completion notes.

Do not route to terminal done while a phase task remains unresolved without a
specific deferral and residual-risk note.
