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

- 17 ArcLink Python modules (7,877 lines).
- 19 test files + 4 hygiene + 2 web tests + 1 browser suite =
  166 ArcLink tests plus 41 browser product checks passing.
- Next.js 15 + Tailwind 4 web app (~1,593 lines, 9 source files) with Playwright browser proof.
- Hosted API boundary (1,078 lines) with versioned routes, OpenAPI 3.1,
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
  Cloudflare, Chutes, Telegram, Discord, and read-only Docker checks. It skips
  cleanly when credentials or explicit live flags are absent; full live journey
  proof remains blocked on external accounts and credentials.
  `tests/test_arclink_e2e_live.py`.

Do not rebuild P1-11 unless a regression is proven by a failing test. Treat P12
as scaffolded but externally blocked until real credentials are supplied and a
credentialed run proves the live path.

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

## BUILD Tasks (Remaining: Production 13-16)

### Phase 3: Brand and UI Polish (Production 10) -- COMPLETE

**Production 10: Web UI Product Checks -- COMPLETE**

- Apply ArcLink brand system fully: Jet Black `#080808`, Carbon `#0F0F0E`,
  Soft White `#E7E6E6`, Signal Orange `#FB5005`.
- Space Grotesk headlines, Satoshi/Inter body text.
- No overlapping text at narrow mobile widths (verify with browser checks).
- No placeholder claims of live services when fake adapters are active.
- Clear empty/error/loading states on every view.
- Accessible forms (labels, focus states, keyboard navigation).
- Route-level smoke tests for `/`, `/login`, `/onboarding`, `/dashboard`,
  `/admin`.
- Repeatable browser checks for desktop and narrow mobile viewports using
  deterministic mocked API responses.
- Screenshot or equivalent browser artifacts written to an ignored directory
  with regeneration instructions.

Validation:

```bash
python3 tests/test_arclink_dashboard.py
python3 tests/test_arclink_hosted_api.py
cd web && npx tsc --noEmit && node --test tests/test_page_smoke.mjs
# add and run a browser proof script in this phase, for example:
# npm run test:browser
```

### Phase 4: E2E Journey (Production 11 complete, Production 12 scaffolded)

**Production 11: Fake E2E Harness**

- Build unified fake E2E test that proves the full journey: web signup,
  onboarding answers, checkout simulation, entitlement activation,
  provisioning request, service health visibility, admin audit, and user
  dashboard state.
- All using fake adapters, no live credentials required.
- Test file: `tests/test_arclink_e2e_fake.py`.

**Production 12: Live E2E Harness**

- Build secret-gated live E2E harness: `tests/test_arclink_e2e_live.py`.
- Include read-only or non-destructive live checks for Stripe, Cloudflare,
  Chutes, Telegram, Discord, and Docker readiness.
- Expand to the same journey against real providers once the external
  credentials and account fixtures exist.
- Gate on presence of each credential; skip gracefully when absent.
- Never leak secrets or make destructive calls accidentally.
- Blocked: all external credentials (see External Live Proof Checklist).

Validation:

```bash
python3 tests/test_arclink_e2e_fake.py
# Live E2E only when credentials present:
# ARCLINK_E2E_LIVE=1 ARCLINK_E2E_DOCKER=1 python3 tests/test_arclink_e2e_live.py
```

### Phase 5: Operations and Documentation (Production 13-16)

**Production 13: Deployment Assets**

- Create `config/env.example` with all required/optional variables.
- Create `docs/arclink/secret-checklist.md`.
- Document Docker/Traefik ingress plan in `docs/arclink/ingress-plan.md`.
- Document backup/restore in `docs/arclink/backup-restore.md`.
- Document health checks, restart, release/rollback in
  `docs/arclink/operations-runbook.md`.

**Production 14: Observability**

- Verify structured events cover all key state transitions.
- Wire health snapshots into admin dashboard reads (if not done in P9).
- Add queue/deployment status visibility to admin dashboard.
- Document alert candidates in `docs/arclink/alert-candidates.md`.

**Production 15: Data Safety**

- Document per-user isolation and volume layout in
  `docs/arclink/data-safety.md`.
- Document backup plan and schedule.
- Add teardown safeguards (confirmation required, audit logged).
- Add destructive-action confirmations for admin operations.
- Verify no secret values in logs, docs, tests, or generated artifacts.

**Production 16: Documentation Truth**

- Audit all documentation against live code.
- Remove or qualify any claims of live functionality not yet proven.
- Name every remaining live blocker with the exact credential/account required.
- Update `docs/arclink/live-e2e-secrets-needed.md`.

Validation:

```bash
python3 -m pytest tests/test_arclink_*.py tests/test_public_repo_hygiene.py -q
cd web && npm test && npm run build
python3 -m py_compile python/almanac_control.py python/arclink_*.py
```

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

## BUILD Handoff

BUILD may begin with no live secrets. Work through Production 10-16 in order.
Each phase should end with passing tests before proceeding. Keep fake adapters
as defaults. Keep live mutation behind explicit E2E gates. Do not call ArcLink
complete while any Production item remains unchecked without a named external
blocker.
