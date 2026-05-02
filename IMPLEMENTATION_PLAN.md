# ArcLink Implementation Plan

## Goal

Transform Almanac into ArcLink: a Chutes-first, self-serve, paid,
single-user AI deployment SaaS with website, Telegram, and Discord onboarding;
Stripe entitlement gates; Cloudflare/Traefik host routing; responsive
user/admin dashboards; and preserved Hermes, qmd, vault, managed memory,
Notion, Nextcloud, code-server, bot, and health robustness.

## Controlling Definition of Done

`research/RALPHIE_PRODUCTION_GRADE_STEERING.md` defines Production 1-16 as the
mandatory completion checklist plus the Professional Finish Gate and Brand
Quality Gate. ArcLink is complete when the product can be deployed, operated,
observed, recovered, sold, and used end to end with confidence. All 16 items
must be checked or explicitly blocked by a named external credential.

Additional backlog sources:
- `research/RALPHIE_FINAL_FORM_GAPS_STEERING.md` defines Gaps A-E for
  executable host readiness, live-gated executor, provider diagnostics, live
  E2E expansion, and real deployment evidence.
- `research/RALPHIE_NEXT_PASS_STEERING.md` defines the concrete next build
  order for Gap D/E no-secret scaffolding, operator integration, and live-proof
  orchestration.
- `research/RALPHIE_LIVE_PROOF_ORCHESTRATION_STEERING.md` defines the current
  next Ralphie objective after commit `007b6cb`.

## Current Status

- 21 ArcLink Python modules (~8,811 lines).
- 23 test files + 4 hygiene + 2 web tests + 1 browser suite
  (234 ArcLink Python tests plus 41 browser product checks passing).
- Next.js 15 + Tailwind 4 web app (~1,593 lines, 9 source files) with Playwright browser proof.
- Hosted API boundary (1,098 lines) with versioned routes, OpenAPI 3.1,
  session transport, CORS, rate-limit headers, safe errors.
- API/auth module (887 lines), dashboard module (937 lines).
- Telegram/Discord runtime adapters with fake-mode dispatch.
- Entitlements (435 lines) with drift detection, targeted comp.
- 18 `arclink_*` tables. Fake adapters default for all providers.

### Landed Checkpoints

- **Production 1-2** (API contract): Landed at commit `019f75d`.
- **Production 3-6** (Provider boundaries): Stripe, Cloudflare, Docker executor,
  Chutes fake boundaries landed. Live proof deferred to P12.
- **Production 7** (Bot parity): Telegram/Discord shared state machine, runtime
  adapters with fake mode, payload validation.
- **Production 8** (User dashboard): Responsive hosted-API layout with billing,
  provisioning, service links, vault, bot, model, memory, security, support,
  loading, and empty states.
- **Production 9** (Admin dashboard): All 18 tabs wired to hosted API, admin
  actions form with all target kinds, session revocation, provider state,
  reconciliation drift, responsive layout. Landed at commit `8cd17a4`.
- **Production 10** (Browser product proof): Playwright suite covers `/`,
  `/login`, `/onboarding`, `/dashboard`, and `/admin` across desktop/mobile
  with deterministic API mocks, fake-adapter labeling, accessible forms,
  loading/empty/error states, mobile overflow checks, dashboard tab checks,
  and fake onboarding flow. Proof: `npm run test:browser` -> 41 passed,
  3 desktop-only skips on 2026-05-02.
- **Production 11** (Fake E2E): Full journey harness covering web signup,
  onboarding, checkout, Stripe webhook, entitlement, provisioning, service
  health, user dashboard, admin audit, and admin actions. 6 tests in
  `tests/test_arclink_e2e_fake.py`.
- **Production 12** (Live E2E): Secret-gated scaffold with Stripe,
  Cloudflare, Chutes, Telegram, Discord, and read-only Docker checks. Provider
  live checks skip cleanly when credentials or explicit live flags are absent;
  the no-secret journey/evidence tests still run. Full live journey proof
  remains blocked on external accounts and credentials. `tests/test_arclink_e2e_live.py`.
- **Production 13** (Deployment assets): `config/env.example`,
  `docs/arclink/secret-checklist.md`, `docs/arclink/ingress-plan.md`,
  `docs/arclink/backup-restore.md`, operations runbook updated with
  health/restart/rollback sections.
- **Production 14** (Observability): Structured events verified, admin
  dashboard already wires all observability surfaces,
  `docs/arclink/alert-candidates.md` created.
- **Production 15** (Data safety): `docs/arclink/data-safety.md` created.
  Teardown safeguards and secret rejection already implemented across all
  boundaries. No secrets found in tracked files.
- **Production 16** (Documentation truth): All docs audited against code.
  `docs/arclink/live-e2e-secrets-needed.md` updated with status header.
  No unproven live claims in shipped documentation.

Do not rebuild completed non-live slices (P1-11 and P13-P16) unless a regression
is proven by a failing test. Treat P12 as scaffolded but externally blocked
until real credentials are supplied and a credentialed run proves the live path.

## Chosen Architecture

Staged evolution of the existing Docker/Python/Bash Almanac control plane.

- Docker Compose first for MVP customer deployment units.
- Python first for control-plane, API, billing, provisioning, executor.
- Next.js 15 + Tailwind 4 for production dashboards consuming hosted API.
- SQLite first with Postgres-compatible schema choices.
- Fake adapters default; live paths behind explicit E2E gates.

## Validation Criteria

PLAN is complete when:

- Required research artifacts are project-specific and portable.
- This plan contains no fallback placeholder marker.
- BUILD can proceed without live secrets.
- Live blockers are documented as E2E prerequisites.
- The next tasks are actionable and testable.

### Gap A-C Delivery (Host Readiness, Diagnostics, Executor Runner)

- **Gap A** (Host readiness): `python/arclink_host_readiness.py` with Docker,
  Compose subcommand, port, state root, env var, secret presence, ingress
  strategy, and CLI checks. Machine-readable JSON output. 14 tests in
  `tests/test_arclink_host_readiness.py`.
- **Gap C** (Live readiness diagnostics): `python/arclink_diagnostics.py` with
  Stripe, Cloudflare, Chutes, Telegram, Discord, and Docker credential
  presence checks. Credential values are never returned. No-op without live
  flag. 11 tests in `tests/test_arclink_diagnostics.py`.
- **Gap B** (Live-gated executor): Injectable `DockerRunner` protocol and
  `FakeDockerRunner` for tests. `DryRunStep` for secret-free planning.
  Live Docker path requires runner. 20 tests (was 17) in
  `tests/test_arclink_executor.py`.

## BUILD Tasks: Next Pass (Operator Integration) -- COMPLETE

Plan refreshed: 2026-05-02 (plan-gate sync). Backlog sources consulted:
- `research/RALPHIE_PRODUCTION_GRADE_STEERING.md`
- `research/RALPHIE_FINAL_FORM_GAPS_STEERING.md`
- `research/RALPHIE_NEXT_PASS_STEERING.md`

The live journey model and deployment evidence ledger landed in commit
`2e6fa98`. The next build has non-external operator-integration work. BUILD
must expose host readiness, provider diagnostics, and live-evidence status to
admin/operator surfaces without leaking secret values.

### Task 1: Operator Snapshot Model -- COMPLETE

`build_operator_snapshot()` in `arclink_dashboard.py` aggregates host readiness,
provider diagnostics, live journey blockers, and evidence status. Returns
credential names only; never returns secret values.

### Task 2: Hosted API/Admin Integration -- COMPLETE

`GET /api/v1/admin/operator-snapshot` route in `arclink_hosted_api.py` with
admin auth gate. Tests in `test_arclink_hosted_api.py` cover auth enforcement
and payload shape (`host_readiness`, `provider_diagnostics` keys).

### Task 3: Admin UI/Read Model Surface -- COMPLETE

Next.js admin page (`web/src/app/admin/page.tsx`) renders Host Readiness and
Provider Diagnostics operator sections from the snapshot payload.

## BUILD Tasks: Next Pass (Live Proof Orchestration)

Plan refreshed: 2026-05-02 after commit `007b6cb`.

The next build must not rebuild completed dashboards or fake-provider
boundaries. It must add a professional live-proof orchestration layer that is
useful before credentials exist and ready to execute when credentials arrive.

Required outputs:

- Secret-safe credential/env validation for the full live journey.
- Dry-run live-proof plan that reports blocked steps by env var name only.
- Credential-gated execution path using injected runners/adapters for tests.
- Redacted evidence ledger artifact written to a predictable path.
- Operator CLI wrapper, focused tests, and docs updates after code lands.

Controlling steering:
`research/RALPHIE_LIVE_PROOF_ORCHESTRATION_STEERING.md`.

## Validation Floor

Every pass must run:

```bash
git diff --check
PYTHONPATH=python python3 tests/test_public_repo_hygiene.py
PYTHONPATH=python python3 tests/test_arclink_e2e_fake.py
PYTHONPATH=python python3 tests/test_arclink_e2e_live.py
PYTHONPATH=python python3 tests/test_arclink_evidence.py
PYTHONPATH=python python3 tests/test_arclink_live_journey.py
```

Run additional focused tests for touched modules. Browser claims still require
Playwright evidence.

## Historical Phases (Landed)

### Phase 1: API Contract Hardening (Production 1-2) -- COMPLETE

Hosted API with versioned `/api/v1` routes, OpenAPI 3.1, rate-limit headers,
auth/CSRF/audit on all mutating routes with negative tests.

### Phase 2: Provider Boundaries (Production 3-6) -- COMPLETE

Stripe, Cloudflare, Docker executor, Chutes fake boundaries with full
no-secret test coverage. Live proof deferred to P12.

### Phase 2.5: Bot Parity and User Dashboard (Production 7-8) -- COMPLETE

Telegram/Discord shared state machine and runtime adapters. User dashboard
with responsive hosted-API layout for billing, provisioning, services, vault,
bots, model/provider state, memory/qmd freshness, security, support, and empty
states.

### Phase 3: Admin Dashboard and Browser Proof (Production 9-10) -- COMPLETE

18-tab admin dashboard wired to hosted API. Playwright browser product proof
with 41 tests passing across desktop/mobile viewports.

### Phase 4: E2E Journey (Production 11-12) -- P11 COMPLETE, P12 SCAFFOLDED

Fake E2E journey harness (6 tests). Live E2E scaffold (secret-gated, skips
cleanly). Full live proof externally blocked.

### Phase 5: Operations and Documentation (Production 13-16) -- COMPLETE

Deployment assets, observability, data safety, and documentation truth all
landed and audited.

## External Live Proof Checklist (Blocked)

These require real accounts/credentials. Build fake/live boundaries first.

- [ ] [external] Stripe: API keys, webhook secret, product/price IDs.
- [ ] [external] Cloudflare: zone ID, scoped API token for `arclink.online`.
- [ ] [external] Chutes: account/key for live inference and per-deployment keys.
- [ ] [external] Telegram: bot token for live onboarding.
- [ ] [external] Discord: application/bot token for live onboarding.
- [ ] [external] Hetzner/host: production host credentials.

## Blockers And Risks

- Admin dashboard is wired to API; user dashboard live data wiring deferred.
- API/auth boundary not yet deployed behind production identity provider.
- Live provider proof requires real credentials and a deliberate live run (P12).
- Dedicated Nextcloud per deployment may become resource-heavy at scale.
- Host readiness tooling landed (Gap A); ops runbook link is part of the next
  operator-integration pass.
- Provider diagnostics landed (Gap C); live connectivity checks deferred.

## BUILD Handoff

P1-11 and P13-P16 are complete for the no-secret foundation. Gaps A-C are
landed for no-secret readiness: host readiness, provider diagnostics, and an
injectable Docker executor runner. Gap D/E no-secret scaffolding and operator
snapshot are landed. The remaining non-external work is live-proof
orchestration: a one-command dry-run/live runner, redacted evidence artifact
output, and credential handoff that can execute as soon as external accounts
exist. The credentialed live proof itself remains externally blocked.

P12 live proof and final Gap D/E evidence remain externally blocked until
credentials are supplied. The remaining blockers are documented in
`docs/arclink/live-e2e-secrets-needed.md` and the External Live Proof Checklist
above.
