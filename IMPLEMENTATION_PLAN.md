# ArcLink Dream Buildout Implementation Plan

Updated: 2026-05-27, Ralphie active queue rebuild and `GAP-029-A` local
Operator Raven slice.

This plan is the current build queue after re-reading `AGENTS.md`,
`research/RALPHIE_ARCLINK_DREAM_BUILDOUT_STEERING.md`,
`docs/arclink/sovereign-control-node-symphony.md`, `USER_JOURNEY.md`,
`GAPS.md`, the prior `IMPLEMENTATION_PLAN.md`, and
`research/COVERAGE_MATRIX.md`.

No live external or host-mutating commands are planned for this unattended
pass. Do not run deploy/install/upgrade, Docker lifecycle, systemd, Stripe,
public bot, provider, Notion, Cloudflare, Tailscale, SSH fleet, live proof, or
live host mutation commands without a separate explicit operator proof window.

## Current Decision

`GAP-025` was checked first and has not regressed. The broad no-secret Python
suite passed in this pass:

```bash
python3 -m pytest -q tests
```

Initial planning result: `1307 passed, 6 skipped, 89 warnings in 64.45s`.
After the `GAP-029-A` source/test slice, the broad suite passed again with
`1312 passed, 6 skipped, 89 warnings in 63.77s`.

Because `GAP-025` is still clean, this pass did not restart broad-suite triage.
The first local Sovereign Control Node slice was `GAP-029-A`: a read-only and
dry-run Operator Raven command layer with worker-readiness facts from
`GAP-030` pulled into status output only.

## Completed Atlas Work

- [x] Read the required planning inputs for this pass.
- [x] Rebuilt the current queue from `GAPS.md`.
- [x] Checked `GAP-025` before selecting another row.
- [x] Confirmed broad no-secret local Python validation is green.
- [x] Preserved the unattended no-live/no-host-mutation boundary.
- [x] Kept proof, policy, and residual-risk rows open instead of fake-closing
  them with local tests.
- [x] Kept `GAP-019` open as trusted-host residual risk.
- [x] Preserved the earlier atlas expansion: `GAP-026` through `GAP-033`,
  the Sovereign Control Node symphony, Control Node worker-readiness prompts,
  router fallback setup, and the three-mode deployment map.
- [x] Selected a bounded first local build slice with owner surface, files,
  focused reproduction command, tests, and success criteria.
- [x] Implemented the `GAP-029-A` minimal Operator Raven console slice.
- [x] Reran focused operator-adjacent tests and the broad no-secret Python
  suite after source/test edits.

## Current Queue

### LOCAL

These rows have unattended local work available now. Rows may still retain
separate live-proof or policy gates after the local slice lands.

| Row | Local repair boundary | First local owner surface |
| --- | --- | --- |
| `GAP-029` | First read-only/dry-run slice exists; full-service Operator Raven still needs broader audited action coverage and policy. | Expand from `status`, `fleet list`, `worker probe --dry-run`, `user lookup`, `pod repair --dry-run`, and injected `upgrade check` only after chat authority/confirmation policy is explicit. |
| `GAP-030` | Worker readiness is partial outside installer output. Surface readiness in admin/API/dashboard and Operator Raven status. | Fleet capacity summary, provisioning readiness read model, admin/dashboard copy. |
| `GAP-031` | Router fallback is partial. Streaming semantics, failed-attempt audit, and cost-different reservation behavior remain local design/code work. | LLM router, provider-state read model, router docs/tests. |
| `GAP-032` | Rolling ArcPod/Hermes update orchestration does not exist. Start with job model and dry-run planner. | Control Node upgrade orchestration, action worker, refresh/apply rails. |
| `GAP-033` | Cross-surface experience finish gate is not enforced. Add shared style contract and representative local fixtures. | Public bots, dashboard, plugins, CLI/TUI copy tests. |
| `GAP-034` | Academy Trainer is unbuilt. Start with fake-source local schemas for source lanes, archive manifests, curriculum, SOUL/vault/skill application, continuing education, and evaluation. | Future Academy Trainer modules, Crew Training, memory synthesis, qmd/vault, managed context, dashboard/Raven copy. |

Conditional local rows:

- `GAP-025`: reopen only if `python3 -m pytest -q tests` regresses.
- `GAP-019`: create a new local row only after the operator authorizes a
  concrete stronger-isolation design; otherwise it stays residual risk.
- `GAP-006`, `GAP-014`, `GAP-017`, `GAP-024`, `GAP-027`: become local code/doc
  work only after the needed product/security policy decision is recorded.
- Any live-proof row: demote to local repair only when an authorized proof
  produces a concrete source/test/doc defect.

### LIVE_PROOF

These rows need authorized credentials, live platforms, external services, or a
host-mutating proof window. They are not blockers for the unattended local
slice except where their local fail-closed behavior regresses.

| Row | Boundary | Handoff |
| --- | --- | --- |
| `GAP-001` | Full paid production journey. | Run `PG-PROD` with authorized scratch/prod credentials and a redacted evidence ledger. |
| `GAP-002` | Stripe checkout, portal, webhook, cancellation, and refuel. | Run `PG-STRIPE`; record event ids, entitlement rows, and replay behavior without secrets. |
| `GAP-003` | Telegram and Discord Raven delivery. | Run Telegram and Discord proof rows separately. |
| `GAP-004` | Domain/Tailscale ingress and fleet apply. | Run one domain-mode and one Tailscale-mode scratch deployment with teardown evidence. |
| `GAP-005` | Hermes/Drive/Code/Terminal workspace browser proof. | Run `bin/arclink-live-proof --journey workspace --live --json` in an authorized window. |
| `GAP-006` | Provider behavior after policy decision. | Run bounded provider proof rows after self-service policy is decided. |
| `GAP-007` | Notion shared-root, brokered write, webhook, dashboard proof. | Run `PG-NOTION` with authorized Notion credentials. |
| `GAP-013` | Backup GitHub write, activation, and restore. | Run authorized `PG-BACKUP`. |
| `GAP-014` | Production browser share journey after policy decision. | Run workspace and `PG-BOTS` share proof. |
| `GAP-015` | Share prompt delivery, callbacks, retry-after-link. | Run authorized `PG-BOTS` for Telegram and Discord. |
| `GAP-018` | Admin action live side effects. | Run the smallest safe action subset under authorized proof. |
| `GAP-020` | Staging disaster recovery. | Run authorized `PG-BACKUP` restore proof and preserve dated evidence. |
| `GAP-021` | Cloud provider worker lifecycle. | Run one scratch lifecycle per provider with create, SSH wait, join, probe, drain/remove, destroy. |
| `GAP-022` | Crew Training live generation. | Run bounded provider generation proof. |
| `GAP-023` | Public selected-agent streaming. | Keep final-message copy until streaming proof passes. |
| `GAP-026` | Live shared-host, Docker, Control Node, and component-pin upgrades. | Run the smallest authorized `PG-UPGRADE` slice for the target mode. |
| `GAP-028` | Shared Host fresh install/enrollment smoke. | Run `PG-SHARED-HOST` on a supported disposable Linux/systemd host. |
| `GAP-030` | Worker readiness proof after local status surfaces exist. | Run `PG-FLEET`/`PG-PROVISION` for the chosen worker path. |
| `GAP-031` | Provider overload/fallback behavior. | Run `PG-PROVIDER` without raw prompt/completion leakage. |
| `GAP-032` | Rolling multi-pod upgrade proof. | Run `PG-UPGRADE` plus selected `PG-HERMES` smoke after the orchestrator exists. |
| `GAP-033` | Chat/browser/workspace finish proof. | Run representative `PG-BOTS`, `PG-HERMES`, and product browser checks. |
| `GAP-034` | Academy live/provider generation and trained-Agent workspace proof. | Run bounded `PG-PROVIDER` generation/transcription proof and selected `PG-HERMES` workspace proof after local Academy pipeline exists. |

### POLICY_DECISION

These rows need an operator/product/security decision before code should
pretend the behavior is settled.

| Row | Boundary | Decision needed |
| --- | --- | --- |
| `GAP-006` | Provider self-service/account lifecycle. | Operator-managed secure handoff versus user self-service, then proof. |
| `GAP-014` | Browser `Request Share` production adapter. | Native ArcLink broker versus approved Nextcloud-backed adapter. |
| `GAP-017` | Captain-initiated Pod migration. | Operator-only forever versus Captain request/approval path. |
| `GAP-024` | Provider changes in dashboard/Raven. | Self-service or operator-only, with unambiguous copy. |
| `GAP-027` | Discord Curator operator-action authority. | Accept operator-channel membership or add second factor, role allowlist, or nonce parity. |
| `GAP-029` | Operator Raven action scope. | Curated read-only/dry-run first; broader mutation requires explicit chat authority and confirmation policy. |
| `GAP-030` | Workerless install outcome. | Hard-fail or control-plane-only blocked status. Current local work must support both copy paths. |
| `GAP-031` | Router fallback scope and visibility. | Product-wide, plan-scoped, Captain-scoped, or incident-only fallback. |
| `GAP-032` | Rolling update execution policy. | Batch size, health gate, halt threshold, rollback, maintenance window. |
| `GAP-034` | Academy source governance. | Enabled source lanes, raw archive permissions, Reddit deletion compliance, video transcript authorization, derived lesson-card retention, and public skill review policy. |

### RESIDUAL_RISK_ACCEPTANCE

| Row | Boundary | Handoff |
| --- | --- | --- |
| `GAP-019` | Docker socket/root services remain a P0 trusted-host boundary after local hardening through `GAP-019-BD`. | Operator must accept the residual risk, authorize a stronger isolation design, or authorize live alert integration for the source-owned incident signals. |

## Bounded First Slice

Working name: `GAP-029` Operator Raven minimal console.

Status: completed locally in this pass as `GAP-029-A`; `GAP-029` remains open
for broader operator actions, policy, live proof, and runbook coverage.

Goal:

Build the smallest safe, source-owned Operator Raven command/action layer for
Sovereign Control Node operations without opening live mutation. The first
slice is read-only or dry-run only: `status`, `fleet list`,
`worker probe --dry-run`, `user lookup`, `pod repair --dry-run`, and
`upgrade check` with a test-injected local runner. Destructive, credential,
payment, backup restore, live deploy, live Docker, SSH, and provider actions
stay out of scope.

Owner surface and files to inspect/change:

- Add or change `python/arclink_operator_raven.py` for the shared schema,
  parser, authorization checks, redacted renderers, and command dispatch.
- Wire Telegram operator commands in `python/arclink_curator_onboarding.py`
  without weakening existing operator approval-code behavior.
- Wire Discord operator commands/components in
  `python/arclink_curator_discord_onboarding.py` while preserving the
  unresolved `GAP-027` policy boundary.
- Reuse read models from `python/arclink_dashboard.py`,
  `python/arclink_fleet.py`, `python/arclink_ctl.py`,
  `python/arclink_control.py`, and `python/arclink_action_worker.py` instead
  of duplicating state logic.
- Add focused coverage in `tests/test_arclink_operator_raven.py`.
- Extend only the necessary existing tests:
  `tests/test_arclink_curator_onboarding_regressions.py`,
  `tests/test_arclink_enrollment_provisioner_regressions.py`,
  `tests/test_arclink_admin_actions.py`,
  `tests/test_arclink_fleet.py`, and
  `tests/test_arclink_upgrade_notifications.py`.

Focused reproduction command:

```bash
python3 tests/test_arclink_operator_raven.py
```

The first build step should add failing tests for the command schema and
authorization boundary, then implement until this command passes. The tests
must use fake/local DB state and injected runners only; they must not call git
remotes, Docker, systemd, SSH, Stripe, bots, providers, or live deploy paths.

Implementation tasks:

- [x] Define the internal Operator Raven command schema with stable action
  names, accepted parameters, safety class, proof boundary, and output redaction
  contract.
- [x] Implement `status` as a compact aggregate of control health facts,
  provisioning readiness, action readiness, provider/router state labels, and
  proof-gate reminders, without claiming live proof.
- [x] Implement `fleet list` and `worker probe --dry-run` from local fleet
  inventory/readiness data; real SSH/provider probes remain proof-gated.
- [x] Implement `user lookup` as an operator-scoped read model that avoids
  exposing secrets and raw credentials.
- [x] Implement `pod repair --dry-run` as a plan/readiness response only; it
  must not queue an action or mutate deployment state in this slice.
- [x] Implement `upgrade check` behind an injected local runner for tests; do
  not run live git/network checks during unattended validation.
- [x] Wire Telegram and Discord adapters to the shared schema with role/channel
  checks and existing approval-code/channel behavior preserved.
- [x] Update docs or comments only where needed to keep `GAP-029` honest:
  first slice local, broad operator mutation still policy/proof-gated.

Focused tests for the first build slice:

```bash
python3 tests/test_arclink_operator_raven.py
python3 tests/test_arclink_curator_onboarding_regressions.py
python3 tests/test_arclink_enrollment_provisioner_regressions.py
python3 tests/test_arclink_admin_actions.py
python3 tests/test_arclink_fleet.py
python3 tests/test_arclink_upgrade_notifications.py
python3 tests/test_documentation_truths.py
python3 tests/test_public_repo_hygiene.py
git diff --check
```

Current results:

- `python3 tests/test_arclink_operator_raven.py` passed: 5 tests.
- `python3 -m py_compile python/arclink_operator_raven.py python/arclink_curator_onboarding.py python/arclink_curator_discord_onboarding.py` passed.
- `python3 tests/test_arclink_curator_onboarding_regressions.py` passed: 10 tests.
- `python3 tests/test_arclink_enrollment_provisioner_regressions.py` passed: 26 tests.
- `python3 tests/test_arclink_admin_actions.py` passed: 8 tests.
- `python3 tests/test_arclink_fleet.py` passed: 18 tests.
- `python3 tests/test_arclink_upgrade_notifications.py` passed: 9 tests.
- `python3 tests/test_documentation_truths.py` passed: 10 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.
- `python3 -m pytest -q tests` passed: 1312 passed, 6 skipped, 89 warnings.

Broaden after source/test edits:

```bash
python3 -m pytest -q tests
```

Success criteria:

- `GAP-029` has a real local vertical slice instead of only product copy.
- Unauthorized Telegram/Discord operator requests are refused before dispatch.
- Authorized Operator Raven outputs are compact, secret-free, and explicit
  about live-proof and policy boundaries.
- The first slice performs only read-only or dry-run work.
- `worker probe`, `pod repair`, and `upgrade check` cannot mutate host,
  deployment, Docker, systemd, SSH, provider, Stripe, or bot state during
  unattended tests.
- `GAP-027` remains open unless the operator makes the Discord authority
  decision.
- `GAP-030` readiness facts may be surfaced, but live worker proof remains
  `PG-FLEET`/`PG-PROVISION`.
- Focused tests and the broad no-secret Python suite pass after implementation.

## Next Local Slice

Working name: `GAP-030` readiness surfaces.

Boundary:

This is local read-model/UI work only. It may read fake/local control-plane
DB rows, fleet inventory rows, and injected environment values. It must not
run SSH, Docker, deploy/install/upgrade, systemd, provider, Stripe, bot,
Tailscale, Cloudflare, or live proof commands. It must keep live worker
verification under `PG-FLEET`/`PG-PROVISION`.

Owner surface and files to inspect/change:

- `python/arclink_dashboard.py`: promote the provisioning readiness summary
  into the admin read model alongside fleet capacity and action readiness.
  Inspect `read_arclink_admin_dashboard()`, `build_scale_operations_snapshot()`,
  `admin_action_execution_readiness()`, and existing use of
  `fleet_capacity_summary()`.
- `python/arclink_api_auth.py` or `python/arclink_hosted_api.py`: expose the
  same read-only status through the authenticated admin/API boundary if the
  existing dashboard route does not already carry it. Inspect
  `read_admin_dashboard_api()` and the admin dashboard route handling before
  adding any new route.
- `python/arclink_operator_raven.py`: replace the inline provisioning-status
  calculation in `_handle_status()` with the shared readiness helper once the
  dashboard helper exists, so Operator Raven and admin dashboard use the same
  wording and fail-closed states.
- `python/arclink_fleet.py`: reuse `fleet_capacity_summary()` and
  `list_fleet_hosts()`; do not add a second fleet-capacity algorithm unless the
  existing helper cannot represent pending-SSH/local/remote states.
- `web/src/app/admin/page.tsx`: render ready versus blocked/control-plane-only
  without implying live worker proof. Inspect the overview bridge metrics,
  `AdminTriageBoard`, and the existing action-readiness matrix before adding a
  new panel.
- `tests/test_arclink_admin_actions.py`, `tests/test_arclink_dashboard.py`, and
  `tests/test_arclink_operator_raven.py`: add no-worker, pending-SSH,
  local-worker, and remote-worker cases against fake/local DB state and
  injected env only.
- `web/tests/test_page_smoke.mjs`: add a static web assertion that the admin
  page labels provisioning readiness separately from general control-plane
  health and action-worker readiness.

Focused reproduction command:

```bash
python3 tests/test_arclink_admin_actions.py
```

Concrete first build step:

1. Add a failing local test in `tests/test_arclink_admin_actions.py` for a new
   shared helper such as `control_node_provisioning_readiness(conn, env=...)`.
   The first fixture should use an empty in-memory control DB and
   `ARCLINK_CONTROL_PROVISIONER_ENABLED=0`, expecting
   `state == "control_plane_only"`, `ready_to_provision == False`, zero
   eligible workers, and a next action that tells the operator to register and
   smoke-test a worker.
2. Add the local/remote positive fixtures after the blocked fixture: register
   active fleet hosts with headroom through `arclink_fleet.register_fleet_host()`
   and assert `state == "ready_to_provision"` only when the provisioner flag is
   enabled and at least one non-drained active host has available slots.
3. Add a pending-SSH fixture with `ARCLINK_EXECUTOR_ADAPTER=ssh` but missing or
   non-allowlisted SSH key/host settings, expecting the readiness state to stay
   blocked with a precise `pending_ssh` reason and no attempt to run SSH.
4. Thread the helper into `read_arclink_admin_dashboard()` as
   `provisioning_readiness`, into `build_scale_operations_snapshot()` if that
   view already carries fleet/provisioner status, and into Operator Raven
   `status` output.
5. Render the same state in `web/src/app/admin/page.tsx` as an operations
   signal distinct from "control plane up" and from the action readiness
   matrix.

Current implementation tasks:

- [ ] Add the `control_node_provisioning_readiness(conn, env=...)` local helper
  and blocked no-worker fixture.
- [ ] Add local/remote worker-ready fixtures using fake in-memory fleet rows.
- [ ] Add pending-SSH blocked fixture with injected env only and no SSH call.
- [ ] Thread the shared helper into admin dashboard/API and Operator Raven
  status output.
- [ ] Render the provisioning readiness state in the admin page separately
  from control-plane health and action-worker readiness.
- [ ] Run the focused `GAP-030` test set and broaden with the no-secret Python
  suite after source/test edits.

Focused tests for this slice:

```bash
python3 tests/test_arclink_admin_actions.py
python3 tests/test_arclink_dashboard.py
python3 tests/test_arclink_operator_raven.py
(cd web && npm test)
python3 tests/test_documentation_truths.py
python3 tests/test_public_repo_hygiene.py
git diff --check
```

Broaden after source/test edits:

```bash
python3 -m pytest -q tests
```

Success criteria:

- Admin/dashboard/API status cannot confuse "control plane is up" with "ready
  to provision ArcPods."
- No-worker and pending-SSH states fail closed with a clear next action.
- Local/remote worker-ready states name eligible workers and available slots.
- Operator Raven `status` and the admin dashboard report the same readiness
  state and proof-gate caveat.
- Live worker proof remains `PG-FLEET`/`PG-PROVISION`; no SSH, Docker, deploy,
  or provider command runs in unattended tests.

## Remaining Handoffs

After the `GAP-029` local slice, the queue still contains local work for
`GAP-030`, `GAP-031`, `GAP-032`, and `GAP-033`; live-proof handoffs for
`GAP-001`, `GAP-002`, `GAP-003`, `GAP-004`, `GAP-005`, `GAP-006`, `GAP-007`,
`GAP-013`, `GAP-014`, `GAP-015`, `GAP-018`, `GAP-020`, `GAP-021`, `GAP-022`,
`GAP-023`, `GAP-026`, `GAP-028`, `GAP-030`, `GAP-031`, `GAP-032`, and
`GAP-033`; policy decisions for `GAP-006`, `GAP-014`, `GAP-017`, `GAP-024`,
`GAP-027`, `GAP-029`, `GAP-030`, `GAP-031`, and `GAP-032`; and the `GAP-019`
residual-risk decision.

Do not move any of those rows to `real` from this plan alone.
