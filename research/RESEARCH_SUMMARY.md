# Research Summary

<confidence>86</confidence>

## Scope

This PLAN pass inspected the public ArcLink repository, the fleet enrollment
steering document, the verified Sovereign audit closure brief, existing fleet
and inventory source, the action and provisioning workers, deploy/control CLI
dispatch, Compose runtime services, focused tests, and operator docs.

No private state, live secrets, deploy keys, user Hermes homes, production
services, payment/provider mutations, real cloud-provider calls, public bot
registration, remote SSH, or Hermes core were inspected or changed.

## Mission Reconciliation

The active mission is ArcLink Sovereign Fleet enterprise-grade worker
enrollment and placement. The live backlog is this repository's
`IMPLEMENTATION_PLAN.md`, rewritten by this PLAN pass from
`research/RALPHIE_ARCLINK_FLEET_ENROLLMENT_STEERING.md` and the user-provided
goals.

The older Sovereign audit verification file remains useful context, but its
closure revisit says the verified FACT and actionable PARTIAL source gaps were
locally remediated by the prior pass. For this mission, the audit file is a
regression-safety reference, not the primary backlog. The primary backlog is
the fleet gap chain:

- static day-2 action-worker routing;
- missing attested worker enrollment;
- missing periodic probe daemon and health summary;
- incomplete scriptable CLI automation;
- stub-only cloud-provider provisioning.

## Current Source Findings

| Area | Current source signal | Planning consequence |
| --- | --- | --- |
| Fleet registry | `python/arclink_fleet.py` registers hosts, lists capacity, maintains active placements, filters unhealthy/draining/saturated hosts, and has an idempotent active-placement uniqueness path. | Keep and harden. Add region-tier priority and orphan reconciliation instead of replacing the registry. |
| Inventory registry | `python/arclink_inventory.py` registers manual/local/cloud-discovered machines, probes over SSH, computes ASU, links to `arclink_fleet_hosts` through `machine_host_link`, and exposes a local CLI. | Extend with enrollment identity fields, JSON output, health summary, and daemon probe history. |
| Schema and drift | `python/arclink_control.py` already creates `arclink_inventory_machines`, `arclink_fleet_hosts`, `arclink_deployment_placements`, active-placement uniqueness, and relationship drift checks. | Additive migrations only. Preserve both registry tables and formalize the 1:1 invariant. |
| Provisioning worker | `python/arclink_sovereign_worker.py` already performs per-placement host lookup and has `_executor_for_host` for per-host SSH/local/fake executor selection. | Factor that helper into `python/arclink_executor.py` for reuse by the action worker. |
| Action worker | `python/arclink_action_worker.py` still builds one executor from env, using `ARCLINK_ACTION_WORKER_SSH_HOST` / `ARCLINK_LOCAL_FLEET_SSH_HOST` for SSH mode. | Phase 1 is the load-bearing fix: resolve deployment placement per action and cache per-host executors. |
| Control CLI | `bin/deploy.sh control fleet-key`, interactive `register-worker`, and `inventory list|probe|add|drain|remove|set-strategy` exist. | Extend `bin/deploy.sh`; do not introduce a new CLI binary. |
| Cloud providers | `arclink_inventory_hetzner.py` and `arclink_inventory_linode.py` exist, but current `inventory add hetzner|linode` lists servers only. | Build idempotent create/bootstrap/remove workflows later in Phase 6. |
| Runtime stack | Docker Compose has `control-provisioner` and `control-action-worker` job-loop services. Docker socket mounts are intentionally scoped for trusted operator services. | Add the inventory worker as another job-loop service and test its socket and secret posture. |
| Tests | Focused suites exist for fleet, inventory providers, action worker, executor, sovereign worker, schema, hosted API, dashboard, and deploy regressions. | Add `test_arclink_fleet_inventory_worker.py` and `test_arclink_fleet_enrollment.py`; expand existing suites where behavior changes. |

## Implementation Path Comparison

| Decision | Path A | Path B | Selected path |
| --- | --- | --- | --- |
| Action routing | Resolve the active deployment placement in the action worker and construct a per-host executor using a shared helper | Keep static env host and ask operators to run one action worker per host | Path A. Static routing is the verified multi-worker breakage. |
| Executor helper | Move/factor `_executor_for_host` into `python/arclink_executor.py` with minimal compatibility wrappers | Duplicate SSH executor construction in the action worker | Path A. One helper keeps SSH key validation, allowlists, fake/local/ssh modes, and secret materialization consistent. |
| Enrollment trust | HMAC-bound, single-use, TTL enrollment tokens plus machine fingerprint attestation | SSH key-only registration | Path A. SSH key-only does not meet zero-trust or audit requirements. |
| Registry model | Formalize `arclink_inventory_machines` for machine identity and `arclink_fleet_hosts` for placement target | Collapse both tables into one fleet table | Path A. Current code and tests already depend on both tables; collapse would be a migration risk. |
| Probing model | Control-plane pull via SSH/probe wrapper with three cadences | Worker-pushed heartbeat agent | Path A. Pull preserves the current low-footprint worker model and operator-owned trust roots. |
| CLI surface | Extend `bin/deploy.sh control ...` and document JSON/exit-code contracts | Add a new fleet CLI | Path A. `deploy.sh control` is the canonical operator surface. |
| Cloud provisioning | Idempotent Hetzner/Linode create, cloud-init/bootstrap, callback enrollment, then provider-aware remove | Manual-only provisioning forever | Path A for v1 providers; manual remains supported for backward compatibility. |
| Live proof | Operator-authorized two-host proof recorded as evidence | CI-driven real cloud/SSH proof | Path A. CI must not depend on live credentials or mutate real hosts. |

## Build Assumptions

- Current source is ground truth where historical research files disagree.
- Existing single-host installs must keep working without operator action.
- Fleet operations are operator-only. Captain-facing surfaces expose only
  coarse ArcPod health, never host IDs, fleet topology, SSH coordinates, or
  provider metadata.
- New schema is additive and idempotent; migrations must run twice cleanly.
- Enrollment tokens, fingerprints, SSH coordinates, cloud credentials, and
  provider billing references must be redacted in logs and tests.
- Hetzner and Linode live workflows remain fake-adapter tested until the
  operator explicitly authorizes live proof.
- The Docker/socket posture remains intentionally trusted for the provisioner
  and action worker; this mission should not broaden socket access.

## Risks

- Factoring `_executor_for_host` touches provisioning and action-worker
  trust-boundary code. Regression tests must prove fake/local/ssh behavior and
  legacy env fallback.
- Region-tier placement can alter host selection. It should be added after
  preserving current deterministic headroom/ASU behavior with tests.
- HMAC enrollment needs a durable control-plane signing secret. Missing secret
  behavior must fail closed without printing token material.
- Periodic probing can create noisy operator notifications if thresholds or
  recovery rules are wrong. Start with deterministic fake-runner tests.
- Cloud-provider provisioning has cost and deletion risk. BUILD should stop at
  fake/idempotency tests unless Phase 7 is explicitly authorized.

## Verdict

PLAN is ready for BUILD handoff. The first BUILD steps should land Phase 0
schema/reconciler work and Phase 1 action-worker routing before expanding into
enrollment, daemon, CLI, and cloud-provider workflows. No live/private blocker
prevents local BUILD work, but Phase 7 live proof remains operator-gated.
