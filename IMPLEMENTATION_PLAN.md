# ArcLink Dream Buildout Implementation Plan

Updated: 2026-05-27, active plan after rereading `AGENTS.md`,
`research/RALPHIE_ARCLINK_DREAM_BUILDOUT_STEERING.md`,
`docs/arclink/sovereign-control-node-symphony.md`,
`docs/arclink/academy-trainer.md`, `USER_JOURNEY.md`, `GAPS.md`, the prior
`IMPLEMENTATION_PLAN.md`, and `research/COVERAGE_MATRIX.md`.

This is an unattended local repair pass. Do not run deploy/install/upgrade,
Docker lifecycle, systemd, Stripe, public bot, provider, Notion, Cloudflare,
Tailscale, SSH fleet, live proof, or host-mutating commands without a separate
explicit operator proof window.

## Current Decision

`GAP-025` was checked first and has not regressed.

```bash
python3 -m pytest -q tests
```

Result during this planning pass: `1353 passed, 6 skipped, 97 warnings in
78.19s`. Keep `GAP-025` closed unless that uncapped no-secret local suite
regresses after a future source/test slice.

The highest-severity Control Node rows before secondary Shared Host work are:

- `GAP-029`: first read-only/dry-run Operator Raven slice exists. Further
  chat mutation is blocked by operator chat authority and confirmation policy.
- `GAP-030`: local worker-readiness surfacing exists. Closure is live
  `PG-FLEET`/`PG-PROVISION`.
- `GAP-031`: local router fallback semantics exist. Closure is live
  `PG-PROVIDER`.
- `GAP-032`: local dry-run/materialized/fake rollout rows exist. Real
  refresh/apply is proof-window work.
- `GAP-033`: local cross-surface contract exists. Closure is browser/chat/
  workspace proof.
- `GAP-034`: local Academy schema, fake acquisition, review/status,
  no-write apply preview, and weekly Continuing Education persistence exist.
  Remaining closure is source-governance policy plus live/provider/workspace
  proof.

Therefore there is no unconditional unattended `LOCAL` queue row in this plan
after `GAP-034-E`. The documentation/handoff pass is complete and keeps the
external gates explicit without inventing speculative code work. Live source
acquisition, provider generation, ASR/transcription, vault/qmd writes,
Hermes-home writes, workspace writes, bot delivery, deploy, Docker, SSH, and
host mutation remain outside this unattended run.

## Completed Atlas Work

- [x] Read the required planning inputs for this pass.
- [x] Rebuilt the current queue from `GAPS.md`.
- [x] Checked `GAP-025` with the broad no-secret Python suite before selecting
  another row.
- [x] Preserved the unattended no-live/no-host-mutation boundary.
- [x] Kept proof, policy, and residual-risk rows open instead of fake-closing
  them with local tests.
- [x] Kept `GAP-019` open as trusted-host residual risk.
- [x] Preserved completed local build slices:
  `GAP-029-A` Operator Raven read-only/dry-run console,
  `GAP-030-A` provisioning-readiness surfacing,
  `GAP-031-A` streaming-safe router fallback semantics,
  `GAP-032-A` ArcPod rollout dry-run planner,
  `GAP-032-B` typed local rollout job materialization,
  `GAP-032-C` bounded fake/local batch execution recording,
  `GAP-033-A` cross-surface product finish contract,
  `GAP-034-A` Academy schema/source-lane foundation,
  `GAP-034-B` Academy review/status integration,
  `GAP-034-C` Academy fake acquisition adapter contract,
  `GAP-034-D` Academy no-write action-worker preview, and
  `GAP-034-E` Academy weekly Continuing Education persistence plus local
  evaluation/graduation readiness.
- [x] Selected the next bounded build step with owner surface, files,
  focused reproduction command, tests, local/live/policy boundaries, and
  success criteria.

## Current Queue

Rows can appear in more than one bucket when closure requires both a policy
decision and live proof. Only `LOCAL` rows are blockers for this unattended
buildout pass.

### LOCAL

Rows with unattended local code/test/doc work available now:

| Row | Priority | Local repair boundary | Live/policy boundary |
| --- | --- | --- | --- |
| none | - | No unconditional unattended local row remains after `GAP-034-E`. | Continue through proof, policy, and residual-risk handoffs until one produces a concrete source defect. |

Conditional local rows:

- `GAP-025`: reopen only if `python3 -m pytest -q tests` regresses.
- `GAP-029`: broaden only after the operator chat authority/confirmation
  policy is explicit.
- `GAP-030`: local work is complete unless live worker proof exposes a source
  defect.
- `GAP-031`: local work is complete unless live provider proof exposes a
  source defect.
- `GAP-032`: local fake execution is complete; real refresh/apply needs an
  authorized proof window or an explicit source defect from proof.
- `GAP-034`: Captain-facing local `/academy` selection and per-Agent staging
  are now wired. Further local code should still wait for source-governance
  decisions, authorized proof, or a concrete source defect; do not imply live
  source acquisition or graduated trained-Agent workspace application until
  the proof gates close.
- Any live-proof row: demote to local repair only when an authorized proof
  produces a concrete source/test/doc defect.

### LIVE_PROOF

These rows require authorized credentials, live platforms, external services,
or a host-mutating proof window. They are handoffs, not blockers for this
unattended local slice.

| Row | Boundary | Handoff |
| --- | --- | --- |
| `GAP-001` | Full paid production journey. | Run `PG-PROD` with authorized scratch/prod credentials and a redacted evidence ledger. |
| `GAP-002` | Stripe checkout, portal, webhook, cancellation, and refuel. | Run `PG-STRIPE`; record event ids, entitlement rows, and replay behavior without secrets. |
| `GAP-003` | Telegram and Discord Raven delivery. | Run Telegram and Discord proof rows separately. |
| `GAP-004` | Domain/Tailscale ingress and fleet apply. | Run one domain-mode and one Tailscale-mode scratch deployment with teardown evidence. |
| `GAP-005` | Hermes/Drive/Code/Terminal workspace browser proof. | Run `bin/arclink-live-proof --journey workspace --live --json` in an authorized proof window. |
| `GAP-006` | Provider behavior after policy decision. | Run bounded provider proof rows after self-service policy is decided. |
| `GAP-007` | Notion shared-root, brokered write, webhook, dashboard proof. | Run `PG-NOTION` with authorized Notion credentials. |
| `GAP-013` | Backup GitHub write, activation, and restore. | Run authorized `PG-BACKUP`. |
| `GAP-014` | Production browser share journey after policy decision. | Run workspace and `PG-BOTS` share proof. |
| `GAP-015` | Share prompt delivery, callbacks, retry-after-link. | Run authorized `PG-BOTS` for Telegram and Discord. |
| `GAP-018` | Admin action live side effects. | Run the smallest safe action subset under authorized proof. |
| `GAP-020` | Staging disaster recovery. | Run authorized `PG-BACKUP` restore proof and preserve dated evidence. |
| `GAP-021` | Cloud provider worker lifecycle. | Run one scratch lifecycle per provider with create, SSH wait, join, probe, drain/remove, and destroy. |
| `GAP-022` | Crew Training live generation. | Run bounded provider generation proof. |
| `GAP-023` | Public selected-agent streaming. | Keep final-message copy until streaming proof passes. |
| `GAP-026` | Live shared-host, Docker, Control Node, and component-pin upgrades. | Run the smallest authorized `PG-UPGRADE` slice for the target mode. |
| `GAP-028` | Shared Host fresh install/enrollment smoke. | Run `PG-SHARED-HOST` on a supported disposable Linux/systemd host. |
| `GAP-030` | Worker readiness proof after local status surfaces exist. | Run `PG-FLEET`/`PG-PROVISION` for the chosen worker path. |
| `GAP-031` | Provider overload/fallback behavior. | Run `PG-PROVIDER` without raw prompt/completion leakage. |
| `GAP-032` | Rolling multi-pod upgrade proof. | Run `PG-UPGRADE` plus selected `PG-HERMES` smoke after real refresh/apply is authorized. |
| `GAP-033` | Chat/browser/workspace finish proof. | Run representative `PG-BOTS`, `PG-HERMES`, and product browser checks after local style gates exist. |
| `GAP-034` | Academy live/provider generation and trained-Agent workspace proof. | Run bounded provider generation/transcription proof and selected `PG-HERMES` workspace proof after policy allows the source lanes. |

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
| `GAP-029` | Operator Raven action scope. | Broader mutation requires explicit chat authority and confirmation policy. |
| `GAP-034` | Academy source governance. | Enabled source lanes, raw archive permissions, Reddit deletion compliance, video transcript authorization, derived lesson-card retention, public skill review, and automatic apply policy. |

### RESIDUAL_RISK_ACCEPTANCE

| Row | Boundary | Handoff |
| --- | --- | --- |
| `GAP-019` | Docker socket/root services remain a P0 trusted-host boundary after local hardening through `GAP-019-BD`. | Operator must accept the residual risk, authorize a stronger isolation design, or authorize live alert integration for the source-owned incident signals. |

## Active Slice

Slice: documentation and operator handoff confirmation for the empty
unattended `LOCAL` queue.

Status: complete as of 2026-05-27. This was the next build step because
`GAPS.md` did not expose an immediate unconditional local repair row after
`GAP-034-E`. The slice updated handoff/status artifacts only, did not change
source behavior, did not claim live proof, and did not start any host/external
mutation.

Goal:

Make the current handoff unambiguous: `GAP-025` remains locally green,
`GAP-029` is policy-gated before broader chat mutation, `GAP-030` through
`GAP-033` are proof-gated after local repair slices, `GAP-034` is policy/proof
gated after the local Academy slices, and `GAP-019` remains residual risk.

Owner surface:

Public planning and handoff docs: gap register, user journey atlas, coverage
matrix, implementation plan, mission status, and build completion notes. No
private state, no secrets, and no runtime host surfaces.

Files to inspect/change:

- Inspect: `GAPS.md`, `USER_JOURNEY.md`, `research/COVERAGE_MATRIX.md`,
  `mission_status.md`, and `research/BUILD_COMPLETION_NOTES.md`.
- Change only if stale: `IMPLEMENTATION_PLAN.md`, `mission_status.md`, and
  `research/BUILD_COMPLETION_NOTES.md`.
- Leave unchanged unless source truth changes: `GAPS.md`, `USER_JOURNEY.md`,
  `docs/arclink/academy-trainer.md`,
  `docs/arclink/sovereign-control-node-symphony.md`, and
  `research/COVERAGE_MATRIX.md`.

Focused reproduction command:

```bash
python3 tests/test_documentation_truths.py
python3 tests/test_public_repo_hygiene.py
python3 -m pytest -q tests/test_arclink_docker.py -k 'docker_authority_inventory_matches_compose_boundary or docker_docs_cover_socket' --maxfail=5
git diff --check
```

Broad validation already run for `GAP-025` in this plan:

```bash
python3 -m pytest -q tests
```

Completed implementation tasks:

- [x] Confirm no stale active local slice remains in `IMPLEMENTATION_PLAN.md`.
- [x] Confirm `mission_status.md` and `research/BUILD_COMPLETION_NOTES.md`
  name the same external handoffs and broad-suite result, or update them if
  they are stale.
- [x] Run the focused documentation/hygiene/inventory validation commands.
- [x] Leave `GAPS.md` and `USER_JOURNEY.md` unchanged unless a concrete source,
  test, proof, or policy status changed.
- [x] Report the remaining live-proof, policy, and residual-risk gates without
  listing them as reviewer local gaps.

Validation completed for this document phase:

- `python3 tests/test_documentation_truths.py` passed: 10 documentation truth
  tests.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m pytest -q tests/test_arclink_docker.py -k 'docker_authority_inventory_matches_compose_boundary or docker_docs_cover_socket' --maxfail=5`
  passed: 2 passed, 62 deselected.
- `git diff --check` passed.

Local/live/policy boundary for this slice:

- Local: public documentation consistency, gap queue classification, handoff
  freshness, broad-suite result recording, and no-secret hygiene.
- Live: no Stripe, bots, provider, Notion, Cloudflare, Tailscale, SSH, Docker,
  deploy/install/upgrade, systemd, workspace proof, live proof, or host
  mutation.
- Policy: no operator decisions are made here. `GAP-006`, `GAP-014`,
  `GAP-017`, `GAP-024`, `GAP-027`, `GAP-029`, and `GAP-034` remain explicit
  policy handoffs.
- Residual risk: `GAP-019` remains open unless the operator accepts the
  trusted-host boundary, authorizes stronger isolation, or authorizes live
  alert integration.

Success criteria:

- The plan has no unchecked speculative code task when `LOCAL` is empty.
- Every non-real row in `GAPS.md` is routed to `LIVE_PROOF`,
  `POLICY_DECISION`, or `RESIDUAL_RISK_ACCEPTANCE`, with conditional local
  demotion only after proof/policy exposes a source defect.
- `GAP-029` is not treated as unattended local chat-mutation work until the
  chat authority/confirmation policy is explicit.
- `GAP-025` remains closed by the current broad no-secret suite result.
- The focused documentation/hygiene commands pass.
- No live external or host-mutating command is planned or run.

## Next Handoffs

After `GAP-034-E`, the remaining queue is proof, policy, or residual-risk
handoff unless a future proof run or explicit operator decision demotes a row
into a concrete source defect. Route forward through document/status handoff;
do not start a speculative local Academy, Operator Raven, worker, router,
rollout, or Shared Host slice from this plan alone.

Live-proof handoffs remain for `GAP-001`, `GAP-002`, `GAP-003`, `GAP-004`,
`GAP-005`, `GAP-006`, `GAP-007`, `GAP-013`, `GAP-014`, `GAP-015`, `GAP-018`,
`GAP-020`, `GAP-021`, `GAP-022`, `GAP-023`, `GAP-026`, `GAP-028`, `GAP-030`,
`GAP-031`, `GAP-032`, `GAP-033`, and `GAP-034`. Policy decisions remain for
`GAP-006`, `GAP-014`, `GAP-017`, `GAP-024`, `GAP-027`, `GAP-029`, and
`GAP-034`. `GAP-019` remains the explicit residual-risk handoff.

Do not move any of those rows to `real` from this plan alone.
