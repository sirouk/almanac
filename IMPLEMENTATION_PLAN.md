# Implementation Plan: ArcLink User Journey And Gap Atlas

## Current Status

Ralphie completed this documentation mission on 2026-05-20. The checklist below
is the audit plan it used, not a fresh list of unstarted work. The generated
handoff artifacts are:

- `USER_JOURNEY.md`: the source-grounded full ArcLink journey and vision atlas.
- `GAPS.md`: the implementation-planning gap register.
- `research/COVERAGE_MATRIX.md`: the journey-joint to source/test map.
- `research/BUILD_COMPLETION_NOTES.md`: the handoff and validation boundary.

Follow-up review found that the focused Ralphie validation was too narrow: the
selected 582-test pass cannot be treated as broad release validation because a
full `python3 -m pytest -q tests` run on 2026-05-20 reported 197 failed,
1012 passed, and 6 skipped. That release-confidence hole is now tracked as
`GAP-025`; close it before calling this checkout broadly regression-clean.

## Goal

Produce two source-grounded root documents:

- `USER_JOURNEY.md`: the complete ArcLink journey story across public entry,
  Raven, billing, provisioning, Control Node, Shared Host, ArcPods, dashboards,
  Hermes, knowledge, workspace plugins, sharing, providers/refuel, admin,
  operations, recovery, and isolation boundaries.
- `GAPS.md`: the hard gap atlas comparing that story against repository code,
  tests, docs, service units, config, and scripts.

The journey may describe the intended product contract, but every unproven
live/external behavior must be marked proof-gated and carried into `GAPS.md`.
The gap register must be adversarial: disprove claims before accepting them.

## Hard Constraints

- [ ] Do not read `arclink-priv/`, user homes, secret files, deploy keys,
  OAuth stores, bot tokens, `.env` values, or live credentials.
- [ ] Do not run live external or host-mutating flows: no deploy/install/
  upgrade, Docker up/down/reconcile, Stripe, Chutes, Telegram, Discord,
  Notion, Cloudflare, Tailscale, SSH fleet mutation, or host mutation.
- [ ] Treat `research/PRODUCT_REALITY_MATRIX.md` as a claim set to disprove,
  not as truth. Current local counts are 101 `real`, 15 `proof-gated`, and
  5 `policy-question`; none are accepted until source and tests are rechecked.
- [ ] Use fresh evidence with file references, preferably `path:line`.
- [ ] Do not quote secrets or local private paths into public docs.
- [ ] Keep this mission documentation-first. Only make code/test fixes later
  if validation reveals a scoped documentation blocker or hygiene failure.
- [ ] Use mixed Codex and Claude review in the Build phase. Codex drives the
  main pass; Claude must independently review the claim ledger, the finished
  `USER_JOURNEY.md`, and the finished `GAPS.md`. If either engine is
  unavailable or unhealthy, stop instead of silently shipping a single-engine
  atlas.

## Planning Inputs Already Located

- Required steering: `AGENTS.md` and
  `research/RALPHIE_ARCLINK_USER_JOURNEY_AND_GAPS_STEERING.md`.
- Existing stubs: `USER_JOURNEY.md` and `GAPS.md`.
- Matrix and prior claims: `research/PRODUCT_REALITY_MATRIX.md`,
  `research/seed-user-journey-draft.md`, `research/seed-gaps-draft.md`,
  `research/RALPHIE_ARCLINK_PRODUCT_REALITY_AND_JOURNEY_STEERING.md`,
  `research/RALPHIE_FINAL_FORM_GAPS_STEERING.md`,
  `research/RALPHIE_ARCLINK_ECOSYSTEM_GAP_REPAIR_STEERING.md`,
  `research/RALPHIE_ARCPOD_CAPTAIN_CONSOLE_STEERING.md`,
  `research/RALPHIE_ARCLINK_PLUGIN_WORKSPACES_STEERING.md`, and live-proof /
  billing / scale steering under `research/RALPHIE_*`.
- Operator docs and runbooks: `README.md`, `docs/arclink/*runbook.md`,
  `docs/arclink/sovereign-control-node.md`,
  `docs/arclink/raven-public-bot.md`, `docs/arclink/data-safety.md`,
  `docs/arclink/llm-router.md`, `docs/arclink/backup-restore.md`,
  `docs/arclink/ingress-plan.md`, and live evidence docs.
- Control surfaces: `deploy.sh`, `bin/deploy.sh`, `compose.yaml`,
  `systemd/`, `bin/health.sh`, `bin/docker-health.sh`,
  `bin/arclink-live-proof`, `bin/component-upgrade.sh`, and `config/pins.json`.
- Product code surfaces: `python/arclink_hosted_api.py`,
  `python/arclink_api_auth.py`, `python/arclink_dashboard.py`,
  `python/arclink_public_bots.py`, Telegram/Discord adapters, onboarding,
  entitlement, provisioning, executor, fleet, worker, provider, LLM router,
  MCP, memory, Notion, SSOT, action worker, notification, access, and evidence
  modules.
- Web and plugin surfaces: `web/src/**`, `web/tests/**`,
  `plugins/hermes-agent/arclink-managed-context/**`,
  `plugins/hermes-agent/drive/**`, `plugins/hermes-agent/code/**`, and
  `plugins/hermes-agent/terminal/**`.
- Regression proof surfaces: `tests/test_arclink_*.py`,
  `tests/test_*notion*.py`, `tests/test_*memory*.py`,
  `tests/test_deploy_regressions.py`, and browser tests under `web/tests`.

## Target Document Shape

### `USER_JOURNEY.md`

- [ ] Open with scope, vocabulary, evidence rules, and proof-gated language.
- [ ] Define actors: Raven, Captain, Agent, Crew, ArcPod/Pod, Operator.
- [ ] Cover public website entry, returning visitor, mobile/desktop,
  Telegram, Discord, linked channels, and Raven first contact.
- [ ] Cover onboarding answers, plan choice, checkout opening, entitlement
  gate, post-checkout polling, failed/cancelled checkout, and post-payment
  handoff.
- [ ] Cover provisioning: readiness transition, placement, single-machine,
  remote fleet, domain/Tailscale ingress, DNS/Traefik, worker apply, rollback,
  teardown, health, and notification.
- [ ] Cover credential handoff: generation, one-time reveal boundary,
  copy/store guidance, acknowledgement, post-ack hiding, rotation/reissue, and
  dashboard entry.
- [ ] Cover user dashboard: account, deployments, service health, billing,
  provider state, communications, credentials, workspace readiness, recovery,
  unavailable states, and links into Hermes/Drive/Code/Terminal.
- [ ] Cover Hermes and agents: Curator, user-agent homes, ArcPod Hermes homes,
  gateway run mode, private channels, Telegram `/start`, Discord retry,
  dashboard plugins, skills, provider/model choice, and safe refresh.
- [ ] Cover knowledge: vault, qmd, PDF sidecars, Notion indexed markdown,
  SSOT broker, webhook/batcher, memory synthesis, recall stubs, daily plate,
  governed managed context, retrieval tools, and Almanac lineage terminology.
- [ ] Cover workspace: Drive, Code, Terminal, roots, root guards, linked
  resources, read-only projections, accepted shares, no reshare,
  copy/duplicate into owned space, audit, revoke, and disabled browser
  share-link UI where unimplemented.
- [ ] Cover provider/refuel: Chutes, LLM router, OAuth/connect posture,
  budgets, usage, warning/exhaustion, refuel credits, and proof gates.
- [ ] Cover admin/operator: one operator, admin dashboard, action worker,
  Shared Host, Docker Shared Host, Sovereign Control Node, systemd/Compose
  services, health checks, release state, deploy keys, pins, component
  upgrades, live proof, backups, enrollment reset, org profile, and
  notification delivery.
- [ ] Cover security and isolation as a first-class journey, not an appendix:
  users must not read, infer, mutate, route to, or share another user's private
  deployment, channels, dashboard, provider state, Notion/SSOT data, files,
  Stripe state, or Hermes resources.

### `GAPS.md`

- [ ] Define status taxonomy exactly: `gap`, `partial`, `proof-gated`,
  `policy-question`, `test-gap`, `doc-gap`, `ux-gap`, `ops-gap`,
  `security-risk`, and `real`.
- [ ] Define severity taxonomy exactly: P0 trust/security/payment/
  provisioning, P1 core journey, P2 degraded/confusing behavior, P3 polish or
  future scale.
- [ ] Add one row per non-real finding with id, severity, status, journey
  joint, expected behavior, actual evidence, source references, missing
  proof/tests, user impact, owner/surface, and recommended next repair.
- [ ] Add `Not Gaps / Already Real` for important checked surfaces that have
  source plus local test evidence.
- [ ] Add `Proof Gates` with exact authorized proof runs or credentials needed
  before proof-gated claims move to `real`.
- [ ] Add `Policy Questions` for product, security, pricing, sharing, provider,
  retention, and ops choices code cannot decide.
- [ ] Add `Test Plan` mapping every code-owned gap to focused local checks.

## Phase Checklist

### Phase 1 - Evidence Method And Claim Ledger

- [ ] Confirm the mixed-engine review path before drafting root docs: Codex
  owner, Claude reviewer, shared claim ledger, and explicit disagreement notes.
- [ ] Give every matrix, seed, and new audit claim a stable id:
  `J-*` for journey joints, `G-*` for gaps, `R-*` for already-real checks, and
  `P-*` for proof gates.
- [ ] Build a source ledger while auditing. Each claim needs at least one code,
  doc, config, unit, or test reference; `real` claims need implementation plus
  local test evidence unless the source itself is the product contract.
- [ ] Record contradictions between docs, steering, product matrix, code, and
  tests as gaps instead of smoothing them over.
- [ ] Treat seed drafts as input only. Reuse no row unless source evidence
  independently supports it.

### Phase 2 - Product Matrix Disproof

- [ ] Re-audit every row in `research/PRODUCT_REALITY_MATRIX.md`.
- [ ] For each `real` row, verify the cited source still exists and proves the
  full end-to-end claim. Demote to `partial`, `test-gap`, `doc-gap`,
  `proof-gated`, or `gap` when evidence is thin or local-only.
- [ ] For each `proof-gated` row, decide whether local code is otherwise real,
  then add the exact live proof gate to `GAPS.md`.
- [ ] For each `policy-question` row, decide whether the question blocks
  journey copy, UI controls, operations, pricing, security, or tests.
- [ ] Actively search for net-new gaps the matrix missed, especially at
  handoffs between surfaces.

### Phase 3 - Source Audit By Surface

- [ ] Public web and onboarding: `web/src/app/page.tsx`,
  `web/src/app/onboarding/page.tsx`, checkout pages, `web/src/lib/api.ts`,
  `python/arclink_hosted_api.py`, `python/arclink_onboarding.py`,
  `python/arclink_onboarding_flow.py`, and web smoke/browser tests.
- [ ] Raven and public bots: `python/arclink_public_bots.py`,
  `python/arclink_telegram.py`, `python/arclink_discord.py`,
  `python/arclink_notification_delivery.py`, bot docs, and bot tests.
- [ ] Billing, entitlements, renewals, refuel, and providers:
  `python/arclink_entitlements.py`, `python/arclink_chutes*.py`,
  `python/arclink_llm_router.py`, `python/arclink_api_auth.py`,
  `python/arclink_hosted_api.py`, Stripe docs, and provider tests.
- [ ] Provisioning and deployment: `python/arclink_provisioning.py`,
  `python/arclink_sovereign_worker.py`, `python/arclink_executor.py`,
  `python/arclink_fleet*.py`, `python/arclink_ingress.py`, `compose.yaml`,
  `deploy.sh`, `bin/deploy.sh`, runbooks, and provisioning/fleet tests.
- [ ] Shared Host and agent install: bootstrap/install/refresh scripts,
  `systemd/`, `python/arclink_enrollment_provisioner.py`, dashboard auth
  proxy, Hermes hook/plugin installers, and agent service tests.
- [ ] Knowledge and memory: `python/arclink_mcp_server.py`,
  `python/arclink_control.py`, `python/arclink_memory_synthesizer.py`,
  `python/arclink_notion_*.py`, `python/arclink_ssot_batcher.py`,
  qmd/PDF/vault scripts, and notion/memory/MCP tests.
- [ ] Workspace and sharing: Drive/Code/Terminal plugins, managed-context
  plugin, share-grant APIs, linked-resource projection code, plugin tests, and
  browser checks.
- [ ] Admin and operations: `python/arclink_dashboard.py`,
  `python/arclink_action_worker.py`, `python/arclink_api_auth.py`,
  `bin/health.sh`, `bin/docker-health.sh`, `bin/arclink-live-proof`,
  component pin scripts, operations runbooks, and admin/ops tests.
- [ ] Security boundaries: access/auth/session/CSRF code, dashboard auth
  proxy, secret regex/redaction, plaintext-secret validators, path confinement,
  root guards, user/admin scoping, and public hygiene tests.

### Phase 4 - Journey Assembly

- [ ] Write each `USER_JOURNEY.md` section as a path through real surfaces:
  trigger, actor, system state, happy path, choice points, alternate path,
  error/retry path, access boundary, and handoff.
- [ ] Keep Captain-facing vocabulary distinct from Operator-facing vocabulary.
- [ ] Mark proof-gated live behavior inline without derailing the human story.
- [ ] For each journey section, link to the relevant gap ids and proof gates.
- [ ] Ensure every required surface in
  `research/COVERAGE_MATRIX.md` appears in the journey.

### Phase 5 - Gap Atlas Assembly

- [ ] Convert every missing, partial, weakly tested, confusing, risky, or
  externally unproven joint into a gap row.
- [ ] Capture Codex/Claude disagreement as a gap, policy question, or proof
  gate when the source does not resolve it.
- [ ] Separate `proof-gated` from `policy-question`: proof gates require
  credentials or authorized live runs; policy questions require an operator or
  product decision.
- [ ] Add `test-gap` rows when code appears present but no focused local
  regression proves the behavior.
- [ ] Add `doc-gap` rows when docs overclaim, underclaim, or contradict code.
- [ ] Add `security-risk` rows for any possible cross-user, secret, payment,
  route, or authority-boundary weakness.
- [ ] Add `Not Gaps / Already Real` only when implementation and proof are both
  strong enough.

### Phase 6 - Proof Gates To Name Explicitly

- [ ] Live Stripe checkout, webhook delivery, subscription renewal/failure,
  billing portal, refuel checkout, and refund/cancel actions.
- [ ] Live Telegram and Discord webhook registration, command sync, button
  delivery, channel linking, selected-agent chat, and handoff retry.
- [ ] Live Control Node provisioning of an ArcPod, including worker execution,
  health, rollback, teardown, and dashboard reachability.
- [ ] Live Cloudflare DNS/Access/Traefik and live Tailscale Serve/Funnel/cert
  ingress.
- [ ] Live Chutes OAuth, inference, usage sync, key lifecycle, per-key
  utilization, account creation, balance/credit application, and LLM router
  relay.
- [ ] Live Notion shared-root permission proof, webhook callback, page/database
  reads, SSOT writes, and user-owned integration/OAuth if that lane is kept.
- [ ] Live Hermes dashboard landing, Drive/Code/Terminal TLS browser proof,
  qmd retrieval, memory refresh, and agent gateway response.
- [ ] Backup/restore proof for control DB, per-deployment state, user-agent
  homes, GitHub backup repos, and disaster recovery.

### Phase 7 - Policy Questions To Extract

- [ ] Is per-user Chutes OAuth canonical, operator-metered router canonical, or
  both with explicit plan boundaries?
- [ ] What should Raven/dashboard do when provider usage hits warning or
  exhaustion: notify, refuel, fallback, suspend, or operator handoff?
- [ ] Should users self-service provider changes, or should provider mutation
  stay behind secure handoff/operator config?
- [ ] Should browser Drive/Code share-link creation stay disabled until an
  ArcLink share broker or Nextcloud-backed adapter is live-proven?
- [ ] Which Notion lane is canonical for paid users: brokered shared root,
  user-owned OAuth, email-share-assisted integration, or multiple lanes?
- [ ] What cross-agent or peer-awareness memory is allowed without leaking
  private context?
- [ ] Which migration/reprovision actions may Captains initiate themselves
  versus Operator-only audited actions?
- [ ] What exact retention, purge, refund, reissue, and recovery policies are
  externally promised beyond local metadata?

### Phase 8 - Validation Commands

Run only local, no-secret checks unless the operator later authorizes more:

```bash
git diff --check
python3 tests/test_public_repo_hygiene.py
python3 tests/test_documentation_truths.py
python3 tests/test_arclink_product_config.py
python3 tests/test_arclink_hosted_api.py
python3 tests/test_arclink_api_auth.py
python3 tests/test_arclink_entitlements.py
python3 tests/test_arclink_public_bots.py
python3 tests/test_arclink_telegram.py
python3 tests/test_arclink_discord.py
python3 tests/test_arclink_provisioning.py
python3 tests/test_arclink_sovereign_worker.py
python3 tests/test_arclink_executor.py
python3 tests/test_arclink_docker.py
python3 tests/test_arclink_ingress.py
python3 tests/test_arclink_mcp_schemas.py
python3 tests/test_arclink_plugins.py
python3 tests/test_arclink_notion_knowledge.py
python3 tests/test_notion_ssot.py
python3 tests/test_arclink_ssot_batcher.py
python3 tests/test_memory_synthesizer.py
python3 tests/test_arclink_memory_sync.py
python3 tests/test_arclink_action_worker.py
python3 tests/test_arclink_notification_delivery.py
python3 tests/test_arclink_live_runner.py
python3 tests/test_arclink_e2e_fake.py
bash -n deploy.sh bin/*.sh test.sh
cd web && npm test && npm run lint && npm run build
```

Browser proof is local-mocked unless credentials and a running safe local web
server are explicitly prepared:

```bash
cd web && npm run test:browser
```

Do not run these without later explicit authorization:

```bash
./deploy.sh install
./deploy.sh upgrade
./deploy.sh docker install
./deploy.sh docker upgrade
./deploy.sh control install
./deploy.sh control upgrade
bin/arclink-live-proof --live --json
bin/arclink-live-proof --journey workspace --live --json
```

## Done Means

- [ ] `IMPLEMENTATION_PLAN.md` and `research/COVERAGE_MATRIX.md` point the
  Build phase at every required journey surface and source family.
- [ ] `USER_JOURNEY.md` is rewritten from fresh source evidence and covers all
  required surfaces, handoffs, retry/error paths, and isolation boundaries.
- [ ] `GAPS.md` contains the status/severity taxonomy, gap register, not-gaps
  section, proof gates, policy questions, and test plan.
- [ ] Every `real` claim in `GAPS.md` has source plus test evidence, or is
  clearly a documented product contract rather than an implementation claim.
- [ ] Every `proof-gated` claim names the exact live credential or authorized
  proof run needed.
- [ ] Every `policy-question` is phrased as a decision the operator/product
  owner can answer.
- [ ] Validation commands are run or explicitly marked not run with reason.
