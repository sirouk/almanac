# ArcLink Dream Buildout Implementation Plan

Updated: 2026-05-26, current unattended plan refresh after required-read
recheck.

This is the active plan after re-reading `AGENTS.md`,
`research/RALPHIE_ARCLINK_DREAM_BUILDOUT_STEERING.md`, `USER_JOURNEY.md`,
`GAPS.md`, the prior `IMPLEMENTATION_PLAN.md`, and
`research/COVERAGE_MATRIX.md`.

No live external or host-mutating commands are planned for this unattended
pass. Do not run deploy/install/upgrade, Docker up/down/reconcile, systemd,
Stripe, public bot, provider, Notion, Cloudflare, Tailscale, SSH, live proof,
or live host mutation commands without a separate explicit operator proof
window.

This plan preserves the earlier lint-phase repair record and adds the current
required-read recheck. `python/arclink_rejection_incidents.py` remains repaired
so `agent-process-helper` writes the expected redacted rejection incident when
the safe private root is provided as `ARCLINK_PRIV_DIR`, and the broad
no-secret Python suite is still green in this checkout.

## Goal

Keep the Ralphie dream buildout moving without confusing local repair work with
external gates. For this unattended pass, the goal is to re-triage current
`GAPS.md`, confirm whether `GAP-025` has regressed, select the highest-severity
bounded `LOCAL` repair if one exists, and otherwise route the remaining
live-proof, policy, and residual-risk work to explicit operator handoffs. This
plan intentionally does not claim live proof, run host-mutating commands, or
invent speculative local code work.

## Queue Decision

`GAP-025` was checked first and has not regressed. The broad no-secret Python
suite passed in this pass:

```bash
python3 -m pytest -q tests
```

Result: `1305 passed, 6 skipped, 81 warnings in 64.03s`.

There is no current bounded unattended `LOCAL` repair row in `GAPS.md`.
`GAP-019` remains the highest-severity non-real row, but its current `Next
repair` explicitly says no bounded unattended helper split is identified by
`config/docker-authority-inventory.json`. The remaining closure path is an
operator residual-risk decision, an explicitly authorized stronger isolation
design, or authorized live alert integration for the source-owned incident
signals.

Because the `LOCAL` queue is empty, the first slice is a documentation/handoff
slice, not a code repair. Do not invent speculative source work or claim live
proof locally.

## Completed Atlas Work

- [x] Read the required planning inputs.
- [x] Built the current queue from `GAPS.md`.
- [x] Checked `GAP-025` before selecting any other row.
- [x] Confirmed broad local no-secret Python validation is green.
- [x] Added explicit `Goal` and `Acceptance Criteria/Validation` sections for
  the build gate.
- [x] Preserved the unattended no-live/no-host-mutation boundary.
- [x] Kept live proof, policy, and residual-risk rows open instead of
  fake-closing them with local tests.
- [x] Kept `GAP-019` open as trusted-host residual risk.
- [x] Recorded the lint-phase source/test repair without changing live-proof,
  policy, or residual-risk gate status.
- [x] Refreshed the active plan after the current required-read pass without
  opening speculative local code work.
- [x] Confirmed `GAPS.md` and `USER_JOURNEY.md` need no document-phase content
  changes because no gap row status or user journey changed.

## Current Queue

### LOCAL

No current bounded unattended local repair row remains.

Conditional local triggers:

- `GAP-025`: reopen only if `python3 -m pytest -q tests` regresses.
- Any proof/policy/residual row: demote to a new `LOCAL` repair only after an
  authorized proof window, operator policy decision, or accepted isolation
  design exposes a concrete source/test/doc defect.

### LIVE_PROOF

| Row | Boundary | Handoff |
| --- | --- | --- |
| `GAP-001` | Full paid production journey. Local validation cannot close it. | Run `PG-PROD` with authorized scratch/prod credentials and a redacted evidence ledger. |
| `GAP-002` | Stripe checkout, portal, webhook, cancellation, and refuel are external proof. | Run `PG-STRIPE`; record event ids, entitlement rows, and replay behavior without secrets. |
| `GAP-003` | Telegram and Discord Raven delivery require live platform proof. | Run Telegram and Discord proof rows separately so one platform failure can be classified independently. |
| `GAP-004` | Domain/Tailscale ingress and fleet apply are live deployment proof. | Run one domain-mode and one Tailscale-mode scratch deployment with teardown evidence. |
| `GAP-005` | Hermes/Drive/Code/Terminal workspace is browser/live proof. | Run `bin/arclink-live-proof --journey workspace --live --json` in an authorized window. |
| `GAP-007` | Notion setup is fail-closed locally; live integration remains unproven. | Run `PG-NOTION` with authorized Notion credentials and preserve shared-root read/write/webhook/dashboard evidence. |
| `GAP-013` | Local backup prep exists; GitHub write, activation, and restore need proof. | Run authorized `PG-BACKUP` for backup activation and restore. |
| `GAP-015` | Share prompt delivery/retry requires live public bots. | Run authorized `PG-BOTS` for Telegram and Discord share approval callbacks and retry-after-link behavior. |
| `GAP-018` | Admin action readiness matrix is local; real side effects are live proof. | Run authorized live proof rows for the smallest safe action subset. |
| `GAP-020` | Local restore smoke exists; disaster recovery is not production-proven. | Run authorized `PG-BACKUP` staging restore proof and preserve dated evidence. |
| `GAP-021` | Fake provider lifecycle tests exist; cloud worker creation is external proof. | Run one scratch-worker lifecycle per provider with API, SSH wait, join, probe, drain/remove, and destroy evidence. |
| `GAP-022` | Deterministic fallback is local; live Crew Training generation is provider proof. | Run bounded live generation proof and keep fallback labels visible. |
| `GAP-023` | Public selected-agent final-message delivery remains the contract. Streaming is unvalidated. | Keep final-message copy until live streaming proof passes. |

### POLICY_DECISION

| Row | Boundary | Handoff |
| --- | --- | --- |
| `GAP-006` | Provider self-service/account lifecycle is product policy first, then provider proof. | Decide provider self-service/account policy before bounded provider live proof. |
| `GAP-014` | Browser `Request Share` has local fail-closed work, but production share completion and backend policy remain unsettled. | Decide native broker versus approved Nextcloud-backed adapter, then run production workspace plus `PG-BOTS` proof. |
| `GAP-017` | Captain-initiated Pod migration is disabled by policy. | Keep operator-only with explicit dashboard copy, or define a Captain request/approval path. |
| `GAP-024` | Provider changes are visible but not self-service. | Choose self-service or operator-only, then make dashboard and Raven copy unambiguous. |

### RESIDUAL_RISK_ACCEPTANCE

| Row | Boundary | Handoff |
| --- | --- | --- |
| `GAP-019` | Docker socket/root services remain a P0 trusted-host boundary after local hardening through `GAP-019-BD`. The current inventory names residual host-equivalent authority, not a concrete unattended repair. | Operator must accept the residual risk, authorize a stronger isolation design, or wire the source-owned incident signals into an authorized live alerting stack. If stronger isolation is chosen, split it into a new concrete source/test repair row before editing. |

## Bounded First Slice

Working name: external-gate and residual-risk handoff refresh.

Owner surface:

- Primary file to change: `IMPLEMENTATION_PLAN.md`.
- Source-of-truth inputs: `GAPS.md`, `USER_JOURNEY.md`,
  `research/COVERAGE_MATRIX.md`, and
  `research/RALPHIE_ARCLINK_DREAM_BUILDOUT_STEERING.md`.
- Handoff artifacts to inspect only if stale: `mission_status.md` and
  `research/BUILD_COMPLETION_NOTES.md`.
- Code owner surface: none for this unattended slice unless `GAP-025`
  regresses or an authorized proof/policy/risk decision creates a concrete
  local repair row.

Focused reproduction command:

```bash
python3 -m pytest -q tests
```

Success criteria:

- `GAP-025` remains backed by a current green broad local Python suite result.
- Every current non-real `GAPS.md` row is classified as `LIVE_PROOF`,
  `POLICY_DECISION`, or `RESIDUAL_RISK_ACCEPTANCE`.
- No live external or host-mutating command is planned or run.
- `GAP-019` remains open and routed to residual-risk acceptance, authorized
  stronger isolation design, or authorized live alert integration.
- The next operator/agent can move directly to an authorized proof, policy, or
  risk window without guessing which local repair to start.

## Current Tasks

- [x] Re-read the required planning inputs.
- [x] Rebuild the queue from current `GAPS.md`.
- [x] Recheck `GAP-025` with the broad no-secret Python suite.
- [x] Update this active implementation plan with the current queue, boundaries,
  tests, owner surface, and success criteria.
- [x] Refresh the document-phase handoff after the current broad-suite recheck.
- [ ] Operator proof window: run the `LIVE_PROOF` handoffs above with
  authorized credentials and redacted evidence.
- [ ] Operator/product decision window: resolve `GAP-006`, `GAP-014`,
  `GAP-017`, and `GAP-024`.
- [ ] Operator/security risk window: choose `GAP-019` residual-risk acceptance,
  stronger isolation design, or authorized live alert integration.
- [ ] Future local repair window: if any proof, policy, risk decision, or broad
  test run exposes a concrete source defect, add or demote it to a new
  `LOCAL` row and run the focused tests for that owner surface.

## Acceptance Criteria/Validation

Acceptance criteria for this unattended phase:

- [x] `GAP-025` is checked before selecting any other row.
- [x] Current `GAPS.md` non-real rows are classified into `LOCAL`,
  `LIVE_PROOF`, `POLICY_DECISION`, and `RESIDUAL_RISK_ACCEPTANCE`.
- [x] If the `LOCAL` queue is empty, the plan routes to documentation/handoff
  instead of speculative code work.
- [x] The bounded next step names an owner surface, files to inspect/change, a
  focused reproduction command, and success criteria.
- [x] No live external, deploy/install/upgrade, Docker lifecycle, systemd,
  credentialed service, private-state read, or host-mutating command is planned
  or run.
- [ ] Operator proof window completes the `LIVE_PROOF` rows with authorized
  credentials and redacted evidence.
- [ ] Operator/product window resolves `GAP-006`, `GAP-014`, `GAP-017`, and
  `GAP-024`.
- [ ] Operator/security window accepts `GAP-019` residual risk, authorizes a
  stronger isolation design, or authorizes live alert integration.

Run after this plan update:

```bash
python3 tests/test_documentation_truths.py
python3 tests/test_public_repo_hygiene.py
python3 -m pytest -q tests/test_arclink_docker.py -k 'docker_authority_inventory_matches_compose_boundary or docker_docs_cover_socket' --maxfail=5
git diff --check
```

Current results:

- `python3 tests/test_documentation_truths.py` passed: 10 tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'docker_authority_inventory_matches_compose_boundary or docker_docs_cover_socket' --maxfail=5`
  passed: 2 passed, 62 deselected.
- `python3 -m pytest -q tests/test_arclink_docker.py::test_agent_helpers_reject_symlinked_home_root_before_root_work --maxfail=1`
  passed: 1 passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'agent_helpers_reject_symlinked_home_root_before_root_work or agent_process_helper_records_redacted_rejection_incident_before_subprocess or agent_process_helper_rejects_configured_root_mismatch' --maxfail=5`
  passed: 3 passed, 61 deselected.
- `python3 -m py_compile python/arclink_rejection_incidents.py python/arclink_agent_process_helper.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `python3 -m compileall -q python plugins/hermes-agent/arclink-managed-context plugins/hermes-agent/code/dashboard plugins/hermes-agent/drive/dashboard` passed.
- `npm test`, `npm run lint`, and `npm run build` passed in `web/`.
- `git diff --check` passed.

Broad validation already completed for this pass:

```bash
python3 -m pytest -q tests
```

Result: `1305 passed, 6 skipped, 81 warnings in 64.03s`.

Broaden again only after a source/test change:

```bash
python3 -m pytest -q tests
```

If shell scripts are changed unexpectedly, also run:

```bash
bash -n deploy.sh bin/*.sh test.sh
```

## Remaining External Handoffs

Only external gates remain: authorized live proof for `GAP-001`, `GAP-002`,
`GAP-003`, `GAP-004`, `GAP-005`, `GAP-007`, `GAP-013`, `GAP-015`, `GAP-018`,
`GAP-020`, `GAP-021`, `GAP-022`, and `GAP-023`; operator/product policy for
`GAP-006`, `GAP-014`, `GAP-017`, and `GAP-024`; and `GAP-019`
residual-risk acceptance, stronger isolation design, or authorized live alert
integration.

`GAP-025` remains locally closed while the broad no-secret Python suite stays
green.
