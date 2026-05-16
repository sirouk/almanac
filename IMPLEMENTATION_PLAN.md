# Implementation Plan: ArcLink Sovereign Fleet Enrollment And Placement

Authoritative steering reference:
`research/RALPHIE_ARCLINK_FLEET_ENROLLMENT_STEERING.md`

## Goal

Land enterprise-grade ArcLink Sovereign worker enrollment and placement while
preserving existing single-host installs. The system must support attested
worker registration, placement-aware day-2 action routing, periodic inventory
health, scriptable operator CLI output, region-aware placement, idempotent
Hetzner/Linode provisioning workflows, and an operator-gated two-host proof.

The verified Sovereign audit file remains a regression reference. Its closure
revisit says the verified FACT/actionable PARTIAL source gaps were remediated,
so BUILD should run the relevant trust-boundary tests early and patch only new
regressions. Do not re-open fiction/outdated audit items `ME-11` or `ME-25`.

## Non-Goals And Boundaries

- Do not touch `arclink-priv`, live secrets, deploy keys, production services,
  payment/provider mutations, public bot command registration, Docker
  install/upgrade/reconfigure, domain-or-Tailscale ingress live mutation, live
  non-loopback SSH, real cloud-provider calls, or Hermes core without explicit
  operator authorization.
- Do not introduce a new CLI binary. Extend `bin/deploy.sh control ...`.
- Do not collapse `arclink_inventory_machines` and `arclink_fleet_hosts`.
- Do not expose host IDs, SSH coordinates, provider metadata, or fleet topology
  to Captain-facing surfaces.
- Do not claim fleet readiness without Phase 7 live two-host proof.

## Selected Implementation Path

| Decision | Selected path | Rejected or deferred alternatives |
| --- | --- | --- |
| Day-2 routing | Resolve deployment placement per action and construct/cache a host-specific executor | Static env host per worker is the current defect; worker-side router is deferred. |
| Executor reuse | Factor `_executor_for_host` from `arclink_sovereign_worker.py` into `arclink_executor.py` | Copy/paste SSH runner construction into the action worker. |
| Registry model | Formalize inventory machine vs fleet host separation and add reconciler warnings | Table collapse is rejected as high-risk migration churn. |
| Enrollment | HMAC-bound single-use TTL token plus fingerprint attestation | SSH key-only registration and long-lived bearer tokens are rejected. |
| Probing | Control-plane pull via SSH probe wrapper | Worker-pushed heartbeat agent is deferred. |
| Scheduling | Docker job-loop service for inventory worker | New scheduler dependency or host cron. |
| CLI | Harden existing `deploy.sh control` commands with JSON modes and documented exit codes | New CLI binary. |
| Cloud v1 | Hetzner and Linode fake-tested create/bootstrap/remove workflows | AWS/GCP/Azure/DigitalOcean deferred. |
| Live proof | Operator-authorized two-host evidence run | CI-driven live host/provider proof rejected. |

## Audit Regression Gate

Before touching fleet code, run or inspect the focused trust-boundary tests most
likely to catch regressions from the verified audit closure:

- `python3 tests/test_arclink_telegram.py`
- `python3 tests/test_arclink_discord.py`
- `python3 tests/test_arclink_hosted_api.py`
- `python3 tests/test_arclink_api_auth.py`
- `python3 tests/test_arclink_secrets_regex.py`
- `python3 tests/test_arclink_docker.py`

If one fails because of current source, fix that regression with a focused test
before continuing. Do not rewrite closed audit work blindly.

## Phase 0: Schema Additions And Orphan Reconciler

Tasks:

- Add idempotent columns to `arclink_inventory_machines`: `enrollment_id`,
  `machine_fingerprint`, `attested_at`, `audit_trail_chain`, and
  `provider_billing_ref`.
- Add idempotent columns to `arclink_fleet_hosts`: `region_tier`,
  `placement_priority`, and `last_health_state`.
- Add tables for `arclink_fleet_enrollments`,
  `arclink_fleet_host_probes`, and `arclink_fleet_audit_chain`.
- Add indexes for enrollment status/expiry, probe host/kind/time, audit-chain
  inventory/time, and region-tier placement lookup.
- Add status constants and drift checks for new tables and statuses.
- Add a reconciler that detects inventory rows with missing host links and
  fleet hosts with no non-removed inventory row. It should write audit warnings
  and return structured drift, not destructively repair by default.
- Preserve existing `register_fleet_host`, `register_inventory_machine`, and
  `place_deployment` behavior.

Validation:

- `python3 tests/test_arclink_schema.py`
- `python3 tests/test_arclink_fleet.py`
- `python3 tests/test_arclink_inventory.py`
- targeted migration test proving `ensure_schema` runs twice.

## Phase 1: Action-Worker Placement Routing

Tasks:

- Factor the provisioning worker's `_executor_for_host` logic into a public
  helper in `python/arclink_executor.py`.
- Keep compatibility wrappers or imports so `python/arclink_sovereign_worker.py`
  behavior remains unchanged.
- Teach `python/arclink_action_worker.py` to resolve the active placement for
  deployment-scoped actions before executing side effects.
- Look up the host row and build a per-host executor using the shared helper.
- Cache executors by `(host_id, adapter)` for the worker process.
- Preserve the existing `_executor_from_env` path when no placement exists.
- Emit `arclink_audit_log` metadata for every action attempt with resolved
  `host_id`, `adapter`, and fallback reason when applicable.

Validation:

- `python3 tests/test_arclink_action_worker.py`
- `python3 tests/test_arclink_executor.py`
- `python3 tests/test_arclink_sovereign_worker.py`
- new two-fake-host routing test: place deployment on host B, queue restart,
  assert host B SSH coordinates are used.

## Phase 2: Enrollment Mint, Callback API, And Audit Chain

Tasks:

- Implement enrollment token minting with 256-bit one-time token material,
  HMAC-SHA256 token hash at rest, TTL default no longer than 30 minutes, and
  cleartext returned exactly once.
- Add `deploy.sh control enrollment mint|list|revoke` plumbing to the shared
  Python boundary.
- Add callback handling that validates the token, consumes it atomically,
  captures hostname/outbound IP/SSH port/OS fields, binds
  `machine_fingerprint`, writes `attested_at`, and creates or links inventory
  and fleet host rows.
- Reject expired, revoked, reused, malformed, or fingerprint-mismatched
  callbacks fail-closed.
- Implement `arclink_fleet_audit_chain` helpers for root and transition
  entries, plus a chain verification helper used by health.
- Use `arclink_evidence.redact_value` / shared redaction for all token and
  fingerprint-adjacent errors.

Validation:

- new `python3 tests/test_arclink_fleet_enrollment.py`
- hosted API tests if callback is exposed through `python/arclink_hosted_api.py`
- schema and audit-chain tamper tests.

## Phase 3: Worker Bootstrap And Probe Wrapper

Tasks:

- Add `bin/arclink-fleet-join.sh` as an idempotent worker bootstrap script for
  supported Linux distributions.
- Add `bin/arclink-fleet-probe-wrapper` that allowlists only `liveness`,
  `capacity`, and `inventory` style probes and emits JSON.
- Ensure bootstrap failure leaves the worker non-admitting and does not leave a
  trusted key installed after failed callback.
- Avoid putting tokens in committed docs, logs, argv examples with real values,
  or persistent files.
- Document bootstrap usage in the operator runbook after behavior is true.

Validation:

- `bash -n deploy.sh bin/*.sh test.sh`
- `shellcheck bin/arclink-fleet-join.sh bin/arclink-fleet-probe-wrapper`
- deploy regression tests for script presence and fail-closed patterns.

## Phase 4: Inventory Worker Daemon And Health Derivation

Tasks:

- Add `python/arclink_fleet_inventory_worker.py`.
- Add an `arclink-fleet-inventory` Compose job-loop service with no unnecessary
  Docker socket or secret mounts.
- Implement liveness, capacity, and inventory cadences independently.
- Record probe rows in `arclink_fleet_host_probes`, with redacted payloads and
  retention pruning.
- Derive states: three liveness failures to degraded, ten to unreachable,
  first success after degraded/unreachable back to active.
- Update `last_health_state`, `last_seen_at`-equivalent data, ASU/load, and
  linked inventory/fleet rows consistently.
- Queue operator notifications for unreachable hosts, audit-chain failure, and
  capacity thresholds.
- Build fleet health summary helper with host counts, probe SLI, capacity,
  region coverage, audit-chain status, and orphan drift.

Validation:

- new `python3 tests/test_arclink_fleet_inventory_worker.py`
- `python3 tests/test_arclink_inventory.py`
- `python3 tests/test_arclink_dashboard.py` if dashboard health is exposed.
- Compose/deploy regression for service wiring and socket posture.

## Phase 5: CLI Surface Hardening

Tasks:

- Add `--json` to every scriptable fleet/inventory/enrollment command.
- Add documented exit codes: 0 success, 1 generic error, 2 invalid argv, 3 not
  found, 4 conflict, 5 unauthorized.
- Add non-interactive `register-worker` flags:
  `--hostname`, `--ssh-host`, `--ssh-user`, `--region`, `--capacity-slots`,
  `--tags-json`, `--metadata-json`, `--no-smoke-test`, and `--json`.
- Add `fleet-key --rotate` with backup/confirmation flow.
- Add `inventory health|rotate-key|re-attest|probe-all`, while preserving
  existing `list|probe|add|drain|remove|set-strategy` forms.
- Wire `set-strategy` into placement behavior where not already consumed and
  add region-tier priority.
- Write `docs/arclink/fleet-cli.md` and
  `docs/arclink/fleet-operator-runbook.md`.

Validation:

- `python3 tests/test_deploy_regressions.py`
- `python3 tests/test_arclink_fleet.py`
- CLI JSON parse tests in `tests/test_arclink_inventory.py` or a new CLI suite.
- docs/OpenAPI updates only after runtime/API behavior is true.

## Phase 6: Cloud-Provider Provisioning

Tasks:

- Extend Hetzner and Linode inventory modules with fakeable create, wait,
  bootstrap, discover, and delete operations.
- Use ArcLink operation idempotency keys to prevent duplicate machine creation.
- Add provider billing/resource references to inventory rows.
- On create: provision machine, wait for SSH, mint enrollment, bootstrap via
  cloud-init or controlled SSH, register callback, and admit host.
- On remove: drain first, require no active placements, remove inventory/fleet
  rows or mark removed/offline, then release provider resource.
- Region-tier placement should prefer primary/secondary/dr in documented order
  and exclude degraded/unreachable hosts from new placements.
- Keep all real provider calls disabled in tests and fail closed without
  credentials.

Validation:

- `python3 tests/test_arclink_inventory_hetzner.py`
- `python3 tests/test_arclink_inventory_linode.py`
- fake idempotency and teardown tests.

## Phase 7: Operator-Gated Live Two-Host Proof

Tasks:

- Write a two-host live proof runbook under `research/` before execution.
- Stop and request explicit operator authorization for the named live flow.
- If authorized, run the proof with real timestamps and host IDs, redact
  secrets, capture evidence, and record failures honestly.
- Update `research/BUILD_COMPLETION_NOTES.md`.
- Update `mission_status.md` if present, or create it, with no claim of fleet
  readiness unless live proof succeeded.

Validation:

- Evidence file in `research/` with redacted timestamps, host IDs, commands
  summarized, and health/smoke result.
- No Phase 7 action runs without explicit authorization.

## Validation Floor

Per touched Python surface:

```bash
python3 -m py_compile python/arclink_control.py python/arclink_fleet.py python/arclink_inventory.py python/arclink_executor.py python/arclink_sovereign_worker.py python/arclink_action_worker.py
python3 tests/test_arclink_fleet.py
python3 tests/test_arclink_inventory.py
python3 tests/test_arclink_action_worker.py
python3 tests/test_arclink_executor.py
python3 tests/test_arclink_sovereign_worker.py
python3 tests/test_arclink_schema.py
```

As new phases land:

```bash
python3 tests/test_arclink_fleet_enrollment.py
python3 tests/test_arclink_fleet_inventory_worker.py
python3 tests/test_arclink_inventory_hetzner.py
python3 tests/test_arclink_inventory_linode.py
python3 tests/test_deploy_regressions.py
```

For shell changes:

```bash
bash -n deploy.sh bin/*.sh test.sh
shellcheck bin/arclink-fleet-join.sh bin/arclink-fleet-probe-wrapper bin/deploy.sh
```

For web/dashboard changes:

```bash
cd web
npm test
npm run lint
npm run build
npm run test:browser
```

Before final completion:

```bash
git diff --check
./bin/ci-preflight.sh
```

Live host-mutating, real-cloud-provider, payment, public-bot mutation, Notion,
Cloudflare/Tailscale, deploy, upgrade, and non-loopback SSH proof remain
operator-gated.

## Required Completion Notes

`research/BUILD_COMPLETION_NOTES.md` must record:

- phases completed and files changed;
- schema changes and migration proof;
- new/changed CLI commands and exit-code docs;
- focused validation commands and results;
- broad validation commands and results;
- live/provider/deploy gates skipped or authorized;
- residual risks and explicit deferrals.

## Explicit Deferrals

- Worker-pushed heartbeat agent.
- Auto-migration of active Pods on host degradation.
- GPU-aware placement constraints beyond recording inventory data.
- DigitalOcean, AWS, GCP, and Azure provider workflows.
- Separate probe key and deploy key.
- TPM/Secure Boot hardware attestation.
- Captain-visible fleet topology.
- CI-driven live host or provider proof.
