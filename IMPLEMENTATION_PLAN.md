# ArcLink Product-Reality And Journey Repair Plan

## Goal

Repair and validate the ArcLink product-reality and journey contract described
in `research/RALPHIE_ARCLINK_PRODUCT_REALITY_AND_JOURNEY_STEERING.md`, while
preserving the completed hardening baseline in
`research/RALPHIE_ARCLINK_ECOSYSTEM_GAP_REPAIR_STEERING.md`.

The BUILD handoff covers website onboarding, Telegram/Discord Raven flows,
paid deployment, credential handoff, Hermes dashboard access, qmd/Notion/SSOT
knowledge rails, managed-context memory stubs, memory-system cherrypicks,
channel linking, drive sharing, operator setup, billing, Chutes utilization,
upgrades, and user/admin dashboards.

The old native workspace plugin mission is historical context only. Do not
route to terminal `done` while unchecked active steering or plan tasks remain
unless each is fixed, proof-gated, or blocked on an explicit operator-policy
question.

## Current Baseline

`research/PRODUCT_REALITY_MATRIX.md` is the current truth matrix after the
2026-05-08 operator-policy reclassification pass:

| Status | Count |
| --- | ---: |
| `real` | 98 |
| `partial` | 0 |
| `gap` | 0 |
| `proof-gated` | 12 |
| `policy-question` | 4 |

The ecosystem-gap steering checklist is currently complete in public repo
inspection. Treat it as a preservation gate, not as permission to skip product
journey repairs.

Current `partial` rows that BUILD must resolve, disable, or keep explicitly
policy-gated before terminal completion: none.

The 2026-05-08 operator-policy addendum has been reconciled into the current
matrix and gate. Raven per-user/per-channel display-name customization, SSOT
shared-root membership, failed-renewal warning/purge cadence, living linked
resources, recipient copy/duplicate, exactly one operator, Refuel Pod local
credit accounting, and Chutes per-user account/OAuth fallback are local
implementation rows or explicit proof gates, not unanswered policy questions.
The remaining policy rows are scoped agent self-model or peer-awareness cards,
browser right-click Drive/Code share-link enablement, Chutes threshold
continuation copy, and user self-service provider changes.

PLAN freshness checkpoint: complete. This plan was reviewed and modified after
`research/RESEARCH_SUMMARY.md`, `research/CODEBASE_MAP.md`,
`research/DEPENDENCY_RESEARCH.md`, `research/COVERAGE_MATRIX.md`,
`research/STACK_SNAPSHOT.md`, `research/PRODUCT_REALITY_MATRIX.md`, and
`consensus/build_gate.md` were refreshed and rechecked in this PLAN pass. It
is the BUILD handoff anchor: if later PLAN work changes research or gate files,
re-review and update this plan afterward.

## Non-Negotiables

- Do not read private state, user homes, secret files, token files, deploy
  keys, OAuth material, bot tokens, or live `.env` values.
- Do not edit Hermes core.
- Do not run live deploy/upgrade, Docker install/upgrade, production payment
  flows, public bot mutations, live provider proof, or host-mutating flows
  unless the operator explicitly authorizes them during BUILD.
- Fix behavior before docs.
- Add focused regression tests for risky behavior.
- Keep Shared Host, Shared Host Docker, and Sovereign Control Node boundaries
  explicit.
- Never expose secrets, raw credentials, local machine paths, terminal
  transcripts, private state, or token values in logs, docs, tests, UI, API
  responses, or commits.

## Selected Architecture

Repair current ArcLink surfaces in place:

- Bash deploy, Docker, bootstrap, health, service, qmd/PDF, backup, and
  upgrade wrappers.
- Python control-plane, hosted API, auth, onboarding, provisioning, public bot,
  MCP, Notion/SSOT, memory, billing/provider, fleet, rollout, evidence, and
  worker modules.
- Next.js, React, TypeScript, and Tailwind hosted website, onboarding, checkout,
  login, user dashboard, and admin dashboard.
- Docker Compose services and systemd units.
- ArcLink Hermes plugins, hooks, generated config, and skills.

Rejected paths:

- Hermes core patches.
- Private-state workarounds.
- Documentation-only repair.
- Single-stack rewrite before product contracts are repaired.

## Validation Criteria

Completion requires:

- Every active steering/plan task is fixed, proof-gated, or policy-gated.
- Every product matrix row is `real`, `proof-gated`, or `policy-question` for
  terminal completion; `partial` rows may exist only during BUILD.
- Users cannot access another user's dashboard, provider state, deployment
  status, health, billing, agent roster, channel pairing, linked resources,
  Notion/SSOT state, vault resources, or credentials.
- Payment-gated deployment, agent expansion, channel linking, agent switching,
  credential handoff, Notion/SSOT setup, drive sharing, billing lifecycle,
  admin/user dashboards, and upgrade controls are truthful.
- Dashboard, qmd, Notion, SSOT, Docker, token, generated cleanup, and path
  traversal boundaries from the ecosystem hardening baseline remain closed or
  explicitly disabled.
- Focused validation is run and summarized; skipped live checks name the exact
  authorization or credential gate.

## Implementation Path Comparison

| Path | Use when | Decision |
| --- | --- | --- |
| Repair current ArcLink wrappers, Python modules, web/API, plugins, Compose, systemd, and tests | The gap is local repo behavior, UI, docs, or tests | Default BUILD path |
| Fail closed or label unavailable | The product would otherwise imply unproved execution, external proof, or unsettled policy | Required for proof-gated and policy-question rows |
| New product/control rewrite | Only after existing host, agent, qmd, Notion, public bot, and billing contracts are true | Rejected for this mission |

## BUILD Decision Order

Use this order when unchecked tasks compete:

1. Preserve user isolation, secret handling, path containment, token redaction,
   no-private-state inspection, and no Hermes core edits.
2. Repair local behavior that can be proven without live credentials, then add
   the nearest focused regression tests.
3. Keep external-provider, live-payment, public-bot, ingress, Docker
   install/upgrade, and host deploy/upgrade claims proof-gated until the
   operator explicitly authorizes that proof.
4. Keep remaining product-owned choices policy-gated until the operator
   answers them, with disabled, fail-closed, or clearly labeled surfaces.
5. Update docs and product copy only after behavior, proof gate, or policy gate
   status is true.

Remaining policy questions should be handled in this dependency order:
isolation and secrets; browser right-click sharing enablement; exact
threshold/provider-change presentation; scoped cross-agent
memory/peer-awareness. Answered operator-policy decisions should be preserved
or truthfully proof-gated, not re-asked.

## BUILD Tasks

### Current BUILD Handoff Actions

- [ ] Run the focused no-secret validation floor for the current diff and
  summarize results in `research/BUILD_COMPLETION_NOTES.md` before terminal
  BUILD completion.
- [ ] Keep all 12 proof-gated rows disabled, labeled, or fail-closed unless the
  operator explicitly authorizes a named live proof flow; update the matrix,
  gate, and completion notes after any authorized proof.
- [ ] Keep the 4 policy-question rows disabled, labeled, or fail-closed until
  the operator answers them: scoped agent peer-awareness, browser right-click
  sharing enablement, public Chutes threshold continuation copy, and
  self-service provider changes.
- [ ] Preserve the completed ecosystem hardening baseline when running
  validation or touching any code in a later BUILD slice.

### P0: Truth, Isolation, And Hardening Preservation

- [x] Reconcile active steering checkboxes with the matrix after each repair:
  fixed rows move to `real`; external rows stay `proof-gated`; product-owned
  rows stay `policy-question`.
- [x] Preserve completed ecosystem hardening when touching dashboard plugins,
  qmd, Notion, SSOT, Docker, token handling, generated cleanup, team-resource
  sync, auth, checkout, provisioning, health, docs, or validation.
- [x] Re-run nearest isolation tests when touching dashboard, API, provider,
  share, billing, credential, channel, Notion, or bot-session code.
- [x] Remove or demote any shipped copy that claims live payment, live bot,
  live Chutes, live Notion, live DNS/tailnet, Docker upgrade, or host upgrade
  proof without authorization.

### P1: Entry, Payment, Credentials, And Dashboard Access

- [x] Verify no-secret website, Telegram, and Discord onboarding start,
  resume, cancel, checkout, and failure states; repair any drift from the
  matrix.
- [x] Preserve local Stripe entitlement/provisioning gates and keep live
  checkout/webhook proof gated until authorized.
- [x] Preserve credential reveal, copy/store guidance, acknowledgement,
  post-ack hiding, and no-raw-secret API/dashboard behavior.
- [x] Keep direct Hermes dashboard links truthful: locally render scoped links;
  leave live dashboard landing proof-gated until a deployed runtime proof is
  authorized.

### P1: Raven, Channels, And Agent Control

- [x] Verify explicit channel identifiers flow from linked Telegram/Discord
  public bot state into agent handoff/routing without live bot mutation.
- [x] Preserve `/link-channel` and `/link_channel` as canonical aliases, with
  `/pair-channel` and `/pair_channel` backward-compatible.
- [x] Preserve selected-agent labels as the visible fallback and do not claim
  Raven bot-name customization until the approved per-user/per-channel
  behavior is implemented or truthfully disabled by platform limits.
- [x] Implement or truthfully gate the approved per-user/per-channel Raven
  bot-name customization promise while preserving selected-agent labels.

### P1: Knowledge, Notion, SSOT, And Memory

- [x] Preserve qmd vault/PDF/Notion collections, SSOT broker scope, destructive
  payload rejection, and managed recall-stub retrieval guidance.
- [x] Finish the Setup SSOT verification story with local fake proof where
  possible; keep live workspace/page permission proof gated.
- [x] Reclassify and implement the operator decision that SSOT sharing uses
  shared-root membership as the canonical model; demote user-owned OAuth/token
  and email-share-only models to non-default research/proof-gated alternatives.
- [x] Document optional conversational-memory plugins as sibling extensions
  that cannot bypass user isolation, brokered SSOT writes, or private-state
  boundaries.
- [x] Keep agent self-model and multi-agent peer-awareness cards
  policy-question unless a scoped, audited, no-transcript-leak path is built
  with tests.

### P1: Drive Sharing And Linked Resources

- [x] Implement or keep disabled Drive/Code right-click share-link creation
  for files and directories under allowed roots.
- [x] Add an agent-facing ArcLink Drive Sharing skill/tool for named
  files/directories, or keep public copy clear that no such tool exists.
- [x] Finish share projection, revoke behavior, audit visibility, and browser
  proof for read-only `Linked` resources.
- [x] Treat recipient copy/duplicate from accepted shares as approved product
  direction and preserve no-reshare on the live `Linked` grant until the local
  copy/duplicate action is implemented.
- [x] Replace copied-share completion claims with living linked-resource
  behavior. Prefer Nextcloud/WebDAV/OCS when enabled; otherwise keep browser
  right-click share disabled until a live ArcLink broker exists.
- [x] Add recipient copy/duplicate from accepted `Linked` resources into the
  recipient's own Vault or Workspace while preserving no-reshare on `Linked`.

### P1: Billing, Chutes, Renewal, And Refuel

- [x] Preserve pricing, entitlement counts, and expansion rules across web,
  bots, Compose defaults, docs, and tests.
- [x] Define the Chutes credential lifecycle: per-user key, per-user Chutes
  account, admin-managed adapter, shared metered key with attribution, or
  disabled until supplied.
- [x] Wire local usage ingestion and threshold states into the existing
  fail-closed Chutes boundary before claiming plan-budget enforcement.
- [x] Keep Raven/dashboard threshold guidance gated until exact public copy and
  provider-change presentation are decided, while implementing the approved
  Refuel Pod and Chutes fallback rails locally.
- [x] Keep live Refuel Pod purchase, live Chutes balance application, and live
  utilization proof disabled/proof-gated until authorized.
- [x] Treat failed-renewal warning cadence, day-7 removal wording, day-14 purge
  queue, and immediate suspension as approved implementation work.
- [x] Add local Refuel Pod SKU/config/credit accounting using the approved
  fair-credit model; keep live purchase and Chutes balance application
  proof-gated.
- [x] Implement the approved failed-renewal lifecycle: immediate provider
  suspension, immediate Raven notice, daily reminders, day-7 account/data
  removal warning, and day-14 audited purge queue.
- [x] Prefer per-user Chutes account/OAuth fallback when per-key metering is
  unavailable; keep per-key utilization proof gated until authorized Chutes
  account proof exists.

### P1: Operator Setup, Ingress, Admin, And UX

- [x] Verify operator setup choices for single machine, Hetzner, and Akamai
  Linode, and align docs/UI/defaults with what code can execute.
- [x] Verify domain-or-Tailscale ingress readiness gates with fake/static
  tests; keep live account/network proof gated.
- [x] Preserve current multi-admin truth without public exactly-one-operator
  overclaim until singleton enforcement or internal-only/subordinate
  multi-admin behavior is implemented.
- [x] Enforce exactly one operator or make current multi-admin mechanics
  internal-only/subordinate to a single-operator policy, with migration-safe
  tests.
- [x] Make admin actions truthful: either execute modeled operations through a
  worker path or present unsupported/disabled states.
- [x] Improve user and admin dashboard hierarchy, service status, billing
  state, agent inventory, knowledge/SSOT readiness, linked channels, recovery
  actions, and failure states while preserving Next.js and API contracts.

### P1: Upgrade Control

- [x] Preserve ArcLink-controlled Hermes/component upgrade rails, pin checks,
  and deploy/health ordering.
- [x] Keep `/upgrade-hermes` and `/upgrade_hermes` routed to non-mutating
  ArcLink-managed guidance unless an explicit authorized upgrade path is run.
- [x] Suppress or override unmanaged Hermes upgrade exposure in ArcLink-owned
  surfaces.

### P2: Docs, Matrix, And Completion Notes

- [x] Update docs only after behavior is repaired or explicitly
  proof/policy-gated.
- [x] Keep `research/PRODUCT_REALITY_MATRIX.md`,
  `consensus/build_gate.md`, and this plan synchronized after each BUILD
  slice.
- [x] Record focused validation and skipped live-proof reasons in completion
  notes before requesting final review.

## Validation Floor

Always run the narrowest relevant checks for touched files:

```bash
git diff --check
bash -n deploy.sh bin/*.sh test.sh
python3 -m py_compile <touched python files>
python3 tests/<nearest focused test>.py
```

Likely focused tests:

```bash
python3 tests/test_arclink_hosted_api.py
python3 tests/test_arclink_api_auth.py
python3 tests/test_arclink_public_bots.py
python3 tests/test_arclink_telegram.py
python3 tests/test_arclink_discord.py
python3 tests/test_arclink_dashboard.py
python3 tests/test_arclink_provisioning.py
python3 tests/test_arclink_plugins.py
python3 tests/test_arclink_mcp_schemas.py
python3 tests/test_arclink_mcp_http_compat.py
python3 tests/test_arclink_notion_knowledge.py
python3 tests/test_notion_ssot.py
python3 tests/test_memory_synthesizer.py
python3 tests/test_deploy_regressions.py
python3 tests/test_health_regressions.py
python3 tests/test_documentation_truths.py
```

For web changes:

```bash
cd web
npm test
npm run lint
npm run test:browser
```

Live Stripe, Telegram, Discord, Chutes, Notion, Cloudflare, Tailscale, Docker
install/upgrade, and host deploy/upgrade proof require explicit operator
authorization during BUILD.
