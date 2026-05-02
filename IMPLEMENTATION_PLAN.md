# ArcLink Implementation Plan

## Goal

Transform Almanac into ArcLink: a Chutes-first, self-serve, paid,
single-user AI deployment SaaS with website, Telegram, and Discord onboarding;
Stripe entitlement gates; Cloudflare/Traefik host routing; responsive
user/admin dashboards; and preserved Hermes, qmd, vault, managed memory,
Notion, Nextcloud, code-server, bot, and health robustness.

## Controlling Definition of Done

`research/RALPHIE_PRODUCTION_GRADE_STEERING.md` defines Production 1-16 as the
mandatory completion checklist. ArcLink is complete when the product can be
deployed, operated, observed, recovered, sold, and used end to end with
confidence. All 16 items must be checked or explicitly blocked by a named
external credential.

## Current Status

- 18 ArcLink Python modules (7,478 lines at the last Ralphie snapshot).
- 17 test files (142 test functions) + 1 hygiene test + 2 web tests.
- Next.js 15 + Tailwind 4 web app (~1,593 lines, 9 source files).
- Hosted API boundary (777+ lines) with route dispatch, session/cookie
  transport, CORS, request-ID, safe errors, Telegram/Discord webhook routes.
- API/auth module (862 lines), dashboard module (937 lines).
- Telegram/Discord runtime adapters with fake-mode dispatch.
- Entitlements with drift detection, targeted comp, profile-only preservation.
- 18 `arclink_*` tables. Fake adapters default for all providers.

This is not live SaaS yet. The code records intent and proves no-secret
behavior.

## Chosen Architecture

Staged evolution of the existing Docker/Python/Bash Almanac control plane.

Selected path:

- Docker Compose first for MVP customer deployment units.
- Python first for control-plane, API/auth, billing, provisioning, dashboard
  read models, and executor boundaries.
- Bash retained for host operations and canonical deploy/health flows.
- SQLite first with Postgres-compatible schema choices.
- Chutes first through central config and per-deployment secret references.
- Stripe, Cloudflare, Traefik, Chutes, Telegram, Discord, Notion, and OAuth
  live paths behind fakeable adapters and explicit E2E gates.
- Next.js 15 + Tailwind 4 for the production dashboard consuming the hosted
  Python API boundary.

Rejected for MVP:

- Scheduler-first Kubernetes/Nomad rewrite.
- Raw SSH-over-HTTP or fragile path-prefix routing for Nextcloud/code-server.
- A standalone SaaS shell that duplicates Almanac state before contracts
  stabilize.

## Validation Criteria

PLAN is complete when:

- Required research artifacts are project-specific and portable.
- This plan contains no fallback placeholder marker.
- BUILD can proceed without live secrets.
- Live blockers are documented as E2E prerequisites.
- The next tasks are actionable and testable.

## BUILD Tasks (Production 1-16 Mapping)

### Phase 1: API Contract Hardening (Production 1-2)

**Production 1: Coherent Versioned Hosted API**

- Extend `arclink_hosted_api.py` with remaining contract routes: user
  billing/subscription reads, provisioning job status, service health reads,
  provider/model state, billing portal link generation, reconciliation
  summary, and admin DNS drift/provider state reads.
- Version all routes under `/api/v1`.
- Add a machine-readable OpenAPI 3.1 contract generated from or tested against
  the canonical route table, expose it as `GET /api/v1/openapi.json`, and store
  a checked-in copy at `docs/openapi/arclink-v1.openapi.json`.
- Add rate-limit response headers for limited public surfaces:
  `Retry-After`, `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and
  `X-RateLimit-Reset`.
- Fix the WSGI status mapping so `/api/v1/health` degraded responses return
  `503 Service Unavailable`, not a fallback `503 OK` reason phrase.
- Ensure fake adapters default safely for every route.
- Add route-level tests for each new endpoint.

**Production 2: Auth/CSRF/Audit on Every Mutating Route**

- Systematic audit: enumerate all mutating routes and verify each has auth,
  role check, CSRF validation (or webhook signature for webhooks), structured
  audit log entry, and at least one negative test proving unauthorized access
  fails.
- Add missing negative tests for any gaps found.
- Verify Stripe webhook signature validation path.

Validation:

```bash
python3 tests/test_arclink_hosted_api.py
python3 tests/test_arclink_api_auth.py
python3 tests/test_arclink_admin_actions.py
python3 tests/test_public_repo_hygiene.py
python3 -m py_compile python/almanac_control.py python/arclink_*.py
git diff --check
```

### Phase 2: Provider Boundaries (Production 3-6)

**Production 3: Stripe Boundary**

- Add billing portal link generation (fake default, live when configured).
- Add failed payment state tracking and admin notes on refund/cancel.
- Add Stripe-vs-local subscription reconciliation report.
- Keep fake tests no-secret; live E2E gated on `STRIPE_SECRET_KEY`.

**Production 4: Cloudflare Boundary**

- Add hostname reservation, DNS record creation, propagation/drift checks,
  teardown, and retry safety to the fake Cloudflare adapter.
- Add fake tests for each operation.
- Live E2E gated on `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ZONE_ID`.

**Production 5: Docker Compose Executor**

- Extend executor to render, validate, start, stop, restart, inspect, and
  teardown per-user stacks.
- Add resource limits, health checks, volume isolation to rendered Compose.
- Keep dry-run/fake coverage as default; live execution behind operator flag.

**Production 6: Chutes Provider Flow**

- Add owner-side key lifecycle contract (create, rotate, revoke).
- Add per-deployment key state tracking.
- Add inference smoke path (fake default).
- Add failure reporting and model catalog refresh.
- Live E2E gated on `CHUTES_API_KEY`.

Validation:

```bash
python3 tests/test_arclink_entitlements.py
python3 tests/test_arclink_chutes_and_adapters.py
python3 tests/test_arclink_executor.py
python3 tests/test_arclink_ingress.py
python3 tests/test_arclink_provisioning.py
python3 tests/test_public_repo_hygiene.py
python3 -m py_compile python/almanac_control.py python/arclink_*.py
git diff --check
```

### Phase 3: Bot Parity and Dashboards (Production 7-10)

**Production 7: Telegram/Discord Onboarding Parity**

- Verify web/Telegram/Discord onboarding creates identical session shapes.
- Add payload validation tests for each channel.
- Add live HTTP transport to adapters behind explicit token gates.
- Document webhook/polling mode for production domain.

**Production 8: User Dashboard**

- Wire Next.js user dashboard to hosted API user endpoints.
- Add panels: billing, deployment state, service links, health,
  model/provider state, vault status, memory/qmd freshness, bot status,
  support, and security/session controls.
- Responsive layout passing brand system checks.

**Production 9: Admin Dashboard**

- Wire Next.js admin dashboard to hosted API admin endpoints.
- Add panels: onboarding funnel, users, payments, provisioning queue,
  service health, host health, Cloudflare/DNS drift, bot state, provider
  state, audit trail, logs/log links, and guarded admin actions.
- Responsive layout passing brand system checks.

**Production 10: Web UI Product Checks**

- Apply ArcLink brand system (jet black, carbon, soft white, signal orange).
- Space Grotesk headlines, Satoshi/Inter body.
- No overlapping text at narrow mobile widths.
- No placeholder claims of live services when fake adapters are active.
- Clear empty/error/loading states on every view.
- Route-level smoke tests for `/`, `/login`, `/onboarding`, `/dashboard`,
  `/admin`.

Validation:

```bash
python3 tests/test_arclink_dashboard.py
python3 tests/test_arclink_onboarding.py
python3 tests/test_arclink_public_bots.py
python3 tests/test_arclink_telegram.py
python3 tests/test_arclink_discord.py
python3 tests/test_arclink_hosted_api.py
cd web && npm test && npm run build
python3 -m py_compile python/almanac_control.py python/arclink_*.py
git diff --check
```

### Phase 4: E2E, Deploy, and Operations (Production 11-16)

**Production 11: Fake E2E Harness**

- Build unified fake E2E test that proves the full journey: web signup,
  onboarding answers, checkout simulation, entitlement activation,
  provisioning request, service health visibility, admin audit, and user
  dashboard state.
- All using fake adapters, no live credentials required.

**Production 12: Live E2E Harness**

- Build secret-gated live E2E harness that runs the same journey against
  real Stripe, Cloudflare, Chutes, Telegram, Discord, and Docker.
- Gate on presence of each credential; skip gracefully when absent.
- Never leak secrets or make destructive calls accidentally.
- Blocked: all external credentials (see External Live Proof Checklist).

**Production 13: Deployment Assets**

- Create env example file with all required/optional variables.
- Create secret checklist document.
- Document Docker/Traefik ingress plan for production host.
- Document backup and restore procedures.
- Document health checks, restart procedure, and release/rollback steps.
- Blocked partially: Hetzner/host credentials for live verification.

**Production 14: Observability**

- Verify structured events cover all key state transitions.
- Wire health snapshots into admin dashboard reads.
- Add queue/deployment status visibility.
- Document alert candidates (unhealthy deployment, failed payment, DNS drift,
  provisioning failure, high error rate).

**Production 15: Data Safety**

- Document per-user isolation and volume layout.
- Document backup plan and schedule.
- Add teardown safeguards (confirmation required, audit logged).
- Add destructive-action confirmations for admin operations.
- Verify no secret values in logs, docs, tests, or generated artifacts.

**Production 16: Documentation Truth**

- Audit all documentation against live code.
- Remove or qualify any claims of live functionality that are not yet proven.
- Name every remaining live blocker with the exact credential/account required.
- Update `docs/arclink/live-e2e-secrets-needed.md`.

Validation:

```bash
python3 tests/test_arclink_*.py
python3 tests/test_public_repo_hygiene.py
cd web && npm test && npm run build
python3 -m py_compile python/almanac_control.py python/arclink_*.py
git diff --check
```

## External Live Proof Checklist (Blocked)

These require real accounts/credentials. Build fake/live boundaries first.

- [ ] [external] Stripe: API keys, webhook secret, product/price IDs.
- [ ] [external] Cloudflare: zone ID, scoped API token for `arclink.online`.
- [ ] [external] Chutes: account/key for live inference and per-deployment keys.
- [ ] [external] Telegram: bot token for live onboarding.
- [ ] [external] Discord: application/bot token for live onboarding.
- [ ] [external] Hetzner/host: production host credentials.

## Blockers And Risks

- The hosted API/auth boundary is not yet deployed behind a production identity
  provider or reverse proxy.
- Next.js web app views use mock data; API wiring is the immediate next step.
- Telegram/Discord adapters have fake-mode dispatch; live HTTP transport
  depends on bot tokens.
- 1 hygiene test fails (provider name in docs context); cosmetic, not blocking.
- Live Stripe, Cloudflare, Chutes, Telegram, Discord, Notion, OAuth, and host
  execution require real credentials and E2E verification.
- Dedicated Nextcloud per deployment may become resource-heavy at scale.

## BUILD Handoff

BUILD may begin with no live secrets. Work through Production 1-16 in phase
order. Each phase should end with passing tests before proceeding. Keep fake
adapters as defaults. Keep live mutation behind explicit E2E gates. Do not
call ArcLink complete while any Production item remains unchecked without a
named external blocker.
