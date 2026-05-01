# ArcLink Implementation Plan

## Goal

Transform Almanac into ArcLink: a Chutes-first, self-serve, paid, single-user
AI deployment SaaS with website, Telegram, and Discord onboarding; isolated
Docker deployments; Stripe entitlement gating; Cloudflare/Traefik host routing;
responsive user/admin dashboards; and preserved Hermes/qmd/vault/memory/Notion
service robustness.

## Current Status

The ArcLink foundation is additive and partially implemented.

- Product/config helpers exist in `python/arclink_product.py`.
- ArcLink SaaS schema and helpers exist in `python/almanac_control.py`.
- Chutes catalog validation and fake key management exist in
  `python/arclink_chutes.py`.
- Stripe, Cloudflare, hostname, and Traefik fakes exist in
  `python/arclink_adapters.py`.
- Stripe entitlement processing exists in `python/arclink_entitlements.py`.
- Public web/Telegram/Discord onboarding session and fake checkout contracts
  exist in `python/arclink_onboarding.py`.
- DNS persistence/drift and Traefik role labels exist in
  `python/arclink_ingress.py`.
- Nextcloud isolation and SSH access guards exist in `python/arclink_access.py`.
- Dry-run provisioning intent exists in `python/arclink_provisioning.py`.
- User/admin dashboard read models and queued admin action contracts exist in
  `python/arclink_dashboard.py`.
- Live executor request/result boundaries and no-secret resolver contracts
  exist in `python/arclink_executor.py`.
- No-secret tests cover product config, schema, Chutes/adapters, entitlements,
  public onboarding, ingress, access, provisioning, dashboard/admin contracts,
  executor contracts, model providers, docs, and public hygiene.

ArcLink is not ready for live provisioning. The current code records and
validates provisioning intent and has no-secret fake executor adapters; it
does not execute live containers, create live DNS records, mint live Chutes
keys, execute queued admin actions, serve a frontend, authenticate dashboard
sessions, or complete live public payment/bot/dashboard flows.

## Chosen Path

Choose staged evolution of the existing Docker/Python control plane.

Path A: evolve Docker Compose, Python/Bash, Hermes, qmd, memory, Nextcloud,
code-server, and bot onboarding into ArcLink. This is selected because it
preserves the working substrate and keeps no-secret tests practical.

Path B: build a clean SaaS shell and call Almanac as a black-box provisioner.
This remains a later boundary option, but it duplicates state, audit, health,
and provisioning too early.

Path C: rewrite around Kubernetes or Nomad now. This is premature until Docker
node density, multi-host scheduling, or operator load becomes the bottleneck.

## Non-Negotiable Constraints

- Preserve existing Almanac services and focused tests.
- Do not require live secrets for unit tests.
- Prefer Docker-first ArcLink evolution.
- Keep `ALMANAC_*` compatibility where needed; prefer `ARCLINK_*` for new
  product surfaces.
- Do not advertise raw SSH-over-HTTP or fragile path-prefix routing.
- Keep Hermes, qmd, managed memory, vault watch, Notion guardrails, bot
  gateways, health watch, Nextcloud, and code-server in the product foundation.
- Keep public onboarding state separate from private user-agent bot tokens and
  provider credentials.

## Validation Criteria

PLAN is ready for BUILD when:

- Required research artifacts exist and are project-specific.
- This plan is project-specific and contains no fallback placeholder marker.
- The next BUILD slice can proceed without live secrets.
- Live blockers are documented as E2E prerequisites, not unit-test blockers.

The ArcLink foundation remains valid when:

- Entitlement mutation is explicit and profile-only updates preserve existing
  entitlement state.
- Per-deployment dry-run provisioning renders Compose/env/DNS/Traefik/access
  intent without secret values.
- Rendered services include Hermes, qmd, memory, vault watch, Nextcloud,
  code-server, bot gateway, managed context, health, and notification lanes.
- Per-deployment state roots match the dedicated Nextcloud isolation decision.
- Chutes credentials are represented by secret references only.
- Stripe webhook processing stays signature-first, idempotent, replayable for
  failed rows, transaction-owned, and safe around caller-owned transactions.
- Public onboarding advances to provisioning readiness only through the Stripe
  entitlement gate.
- `arclink_provisioning_jobs` supports idempotent start/resume/fail/rollback
  transitions.
- Timeline events and service-health placeholders are recorded for admin and
  dashboard use.
- Dashboard/admin read models stay secret-free, and admin action requests are
  queued, reasoned, idempotent, and audited before any future executor acts.
- Fake executor idempotency rejects explicit Docker Compose key reuse when the
  rendered intent digest changes.
- Existing ArcLink no-secret tests and touched-module compile checks pass.

## Completed Foundation

### Phase 1: Product Identity And Compatibility

Status: no-secret scaffold present.

- Add `ARCLINK_*` product helpers with legacy `ALMANAC_*` fallback.
- Make non-empty ArcLink values take precedence.
- Treat blank ArcLink values as unset.
- Keep diagnostics key-only and secret-safe.

Validation: `tests/test_arclink_product_config.py`.

### Phase 2: ArcLink SaaS Schema

Status: no-secret scaffold present.

- Add `arclink_users`, deployments, subscriptions, provisioning jobs, DNS
  records, admins, audit, events, service health, model catalog, webhook event,
  public onboarding, and action-intent tables.
- Add helpers for prefix reservation/generation, audit/events, subscriptions,
  service health, provisioning jobs, entitlement state, and drift checks.
- Keep schema SQLite-compatible with stable text ids.

Validation: `tests/test_arclink_schema.py`.

### Phase 3: Chutes-First Provider Layer

Status: no-secret scaffold present.

- Parse and validate Chutes model catalog fixtures.
- Support required-capability validation for the configured default model.
- Provide a fake key manager that returns secret references, not plaintext keys.
- Keep live auth/key lifecycle as an E2E prerequisite.

Validation: `tests/test_arclink_chutes_and_adapters.py`.

### Phase 4: Entitlement Gate

Status: no-secret scaffold present.

- Verify Stripe webhooks and fail closed on blank secrets.
- Deduplicate processed webhook event ids.
- Allow explicit replay of `failed` and `received` webhook rows while keeping
  `processed` rows idempotent.
- Mirror subscription state, including current nested invoice parent payloads.
- Update user entitlement state for supported mutating events.
- Advance deployments out of `entitlement_required` only when paid or comped.
- Require reasoned audit rows for admin comps and blocked payment states.
- Ignore unsupported signed Stripe event types without mutating entitlement
  state.
- Keep supported webhook handling atomic and reject caller-owned active
  transactions without rolling back caller work.
- Preserve existing `paid` and `comp` entitlements during profile-only user
  upserts and onboarding prepare/resume paths.

Validation: `tests/test_arclink_entitlements.py`,
`tests/test_arclink_onboarding.py`.

### Phase 5: DNS, Ingress, And Access Planning

Status: no-secret scaffold present.

- Generate obscure deployment prefixes with denylist and collision retry.
- Persist desired DNS records and record Cloudflare drift events.
- Render Traefik labels for dashboard, files, code, and Hermes hosts.
- Pin MVP Nextcloud isolation to dedicated per-deployment instances.
- Pin SSH strategy to Cloudflare Access/Tunnel TCP and reject raw
  SSH-over-HTTP.

Validation: `tests/test_arclink_ingress.py`, `tests/test_arclink_access.py`,
and the Traefik golden fixture.

### Phase 6: Provisioning Orchestration

Status: no-secret dry-run scaffold present.

- Add dry-run rendering and provisioning job state transitions.
- Wrap dry-run attempts in deterministic idempotency keys and explicit
  resume/fail behavior.
- Render per-deployment state roots, env/config, Compose service intent, DNS,
  Traefik, access-link intent, health placeholders, and timeline events.
- Reject plaintext-looking Chutes, Stripe, Cloudflare, Telegram, Discord, and
  Notion values in dry-run output.
- Render dedicated `nextcloud-db` and `nextcloud-redis` services, volumes, and
  `nextcloud` dependencies.
- Add planning-only rollback for failed execution jobs.

Validation: `tests/test_arclink_provisioning.py`.

### Phase 7: Public Onboarding Contracts

Status: no-secret scaffold present.

- Add public onboarding session records for web, Telegram, and Discord.
- Record funnel events for started, question answered, checkout opened,
  payment success/failure/cancel/expire, provisioning requested, first agent
  contact, and channel handoff.
- Add deterministic fake Stripe checkout creation behind the adapter boundary.
- Connect successful checkout completion to existing entitlement and
  provisioning gates without executing live containers.
- Keep public onboarding bot state separate from private user-agent bot state.
- Reject private bot-token-shaped and provider-token-shaped values from public
  onboarding metadata.

Validation: `tests/test_arclink_onboarding.py`.

### Phase 8: Dashboard And Admin Contracts

Status: no-secret backend contract present.

- Add user dashboard read models for deployment status, access links, billing,
  bot contact state, model/provider state, memory/qmd freshness, service
  health, and recent events.
- Add admin read models for onboarding funnel, subscriptions, deployments,
  service health, DNS drift, provisioning jobs, audit log, queued action
  intents, and recent failures.
- Add reason-required admin action contracts for restart, reprovision, suspend,
  force resynth, rotate keys, DNS repair, refund/comp/cancel, and rollout.
- Keep actions queued/audited and no-secret; do not execute live provider or
  host mutations from this slice.

Validation: `tests/test_arclink_admin_actions.py`,
`tests/test_arclink_dashboard.py`.

## Completed Build Slice: Executor Replay/Dependency Consistency Repair

The executor lint-risk repair is complete: Docker replay avoids secret
rematerialization, zero fake failure limits fail closed, rollback delete
detection is explicit, and DNS record types are allowlisted. The follow-up
replay/dependency consistency repair is also complete: fake provider, edge,
Chutes, and rollback replays are bound to stable operation digests, strict
Chutes replay rejects action or secret-ref drift, and fake Compose rejects
missing service dependencies before apply.

Status: executor request/result types, fake Docker/provider/edge/rollback
adapters, secret resolver contracts, intent-digest mismatch rejection, and the
lint-risk and replay/dependency repairs exist. The next slices are documentation
reconciliation and separately gated live adapter work.

### Task 1: Fake Adapter Replay Consistency

- Bind fake Cloudflare DNS, Cloudflare Access, Chutes key, and rollback
  idempotency keys to a stable operation digest derived from their request
  inputs.
- If an explicit or derived idempotency key is reused with changed inputs, raise
  `ArcLinkExecutorError` before returning a stored result.
- Make Chutes replay especially strict: it must never return the current
  request's `action` or `secret_ref` with a previously stored key result.
  Reject mismatched replay inputs, and for identical replay return the stored
  action and stored secret reference.
- Add focused regressions for DNS record changes, access app/SSH plan changes,
  Chutes action/secret-ref changes, and rollback plan/action/health changes.

### Task 2: Compose Dependency Validation

- Make `_compose_service_start_order` reject `depends_on` entries that reference
  services missing from the rendered compose intent.
- Raise `ArcLinkExecutorError` with the service and missing dependency names in
  the message.
- Add a regression proving fake compose execution cannot pass a dependency graph
  that real Docker Compose would reject.

### Task 3: Refresh Completion Notes And Gate

- `research/BUILD_COMPLETION_NOTES.md` records the repair and focused
  validation.
- Build and test gates accepted the replay/dependency regressions.
- Do not enable real Docker, Cloudflare, Chutes, Stripe, or host mutation in
  this repair.

### Task 4: Focused Validation

No-secret checks for the touched surface:

```bash
python3 tests/test_arclink_executor.py
python3 tests/test_arclink_provisioning.py
python3 tests/test_public_repo_hygiene.py
python3 -m py_compile python/arclink_executor.py python/arclink_provisioning.py
python3 -m ruff check python/arclink_executor.py tests/test_arclink_executor.py
git diff --check
```

## Completed Executor Foundation

The previous executor slices made live execution possible to test safely
through fake adapters, without turning it on by default.

### Task 1: Executor Types And Gating

- Add an `arclink_executor` module or similarly scoped executor package.
- Define executor request/result dataclasses for `docker_compose_apply`,
  `cloudflare_dns_apply`, `cloudflare_access_apply`, `chutes_key_apply`,
  `stripe_action_apply`, and `rollback_apply`.
- Require an explicit E2E/live flag for any adapter that mutates a host or
  provider.
- Add tests proving executor calls fail closed when the flag is absent.

### Task 2: Secret Resolver Contract

- Define a resolver interface for `secret://` references.
- Support a fake resolver for unit tests and a file-materialization contract
  for `/run/secrets/*`.
- Validate that resolved values are never written to dashboard views, audit
  metadata, provisioning job metadata, events, or test snapshots.
- Add tests for missing secret, invalid ref, and successful fake resolution.

### Task 3: Docker Compose Execution Adapter

Status: no-secret fake adapter contract present.

- Consume `render_arclink_provisioning_intent()` output without re-rendering
  service semantics in the executor.
- Plan project name, env file, compose file, volumes, secrets, labels, and
  service start order from the intent.
- Add fake adapter tests for idempotent start/resume and failed partial apply.
- Keep real `docker compose` invocation behind the E2E/live flag.

### Task 4: Provider And Edge Execution Adapters

Status: no-secret fake adapter contract present.

- Add fake Cloudflare DNS/Tunnel/Access mutation based on rendered DNS/access
  intent.
- Add fake Chutes key create/rotate/revoke lifecycle that returns secret
  references only.
- Keep Stripe refund/cancel/portal live actions as queued admin-action
  executor candidates, not direct dashboard mutations.
- Document live credentials required for each adapter in the E2E docs.

### Task 5: Rollback Executor Contract

Status: no-secret fake adapter contract present.

- Extend rollback planning into a fakeable executor contract.
- Rollback should stop/remove unhealthy rendered services, preserve state
  roots, leave secret refs for review, and append audit/events.
- Add tests proving rollback is idempotent and does not delete vault or
  customer state roots.

### Completed Validation Envelope

Run no-secret checks for the touched surface:

```bash
python3 tests/test_arclink_product_config.py
python3 tests/test_arclink_schema.py
python3 tests/test_arclink_chutes_and_adapters.py
python3 tests/test_arclink_entitlements.py
python3 tests/test_arclink_onboarding.py
python3 tests/test_arclink_ingress.py
python3 tests/test_arclink_access.py
python3 tests/test_arclink_provisioning.py
python3 tests/test_arclink_admin_actions.py
python3 tests/test_arclink_dashboard.py
python3 tests/test_public_repo_hygiene.py
python3 -m py_compile python/almanac_control.py python/arclink_*.py
git diff --check
```

## Later Phases

### Phase 9: Live Provisioning Execution

- Enable real Docker Compose execution only in an operator-controlled E2E
  environment.
- Create/update per-deployment Compose projects from rendered intent.
- Apply Cloudflare DNS/tunnel/access records through live adapters.
- Mint/rotate/revoke Chutes keys through the verified production account path.
- Add rollback execution for failed partial deployment.

### Phase 10: Public Website And User Dashboard

- Add Next.js 15 + Tailwind app after executor, auth, and API contracts exist.
- Build responsive views for overview, files, code, Hermes, memory, skills,
  model, billing, security, support, and diagnostics.
- Prefer deep links where iframe embedding is brittle.
- Add Playwright coverage once the app exists.

### Phase 11: Admin Dashboard

- Build admin views for onboarding, payments, health, infrastructure, bots,
  security/abuse, releases, logs, audit trail, and operations.
- Implement sensitive actions through queued audited jobs and executor workers.
- Add RBAC/session controls and tests before exposing action endpoints.

### Phase 12: Live E2E

- Keep `docs/arclink/live-e2e-secrets-needed.md` current.
- Run live E2E only after credentials and infrastructure exist: website or bot
  onboarding, Stripe test payment, provisioning execution, DNS and ingress,
  dashboard login, bot conversation, file upload and qmd retrieval, memory
  refresh, code-server, Hermes dashboard, and admin health/action views.

## Blockers And Risks

- Dashboard/admin frontend routes, RBAC, browser session auth, and action
  executors are not implemented yet.
- Live Stripe checkout/webhook delivery, Cloudflare DNS/tunnel mutation,
  Chutes key lifecycle, public bot credentials, Notion, OAuth, dashboards, and
  deployment-host execution remain E2E prerequisites.
- Dedicated Nextcloud per deployment may become resource-heavy; keep the shared
  Nextcloud alternative deferred until isolation and resource pressure are both
  measured.
