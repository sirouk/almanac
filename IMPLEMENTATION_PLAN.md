# ArcLink Implementation Plan

## Goal

Transform Almanac into ArcLink: a Chutes-first, self-serve, paid,
single-user AI deployment SaaS with website, Telegram, and Discord onboarding;
Stripe entitlement gates; Cloudflare/Traefik host routing; responsive
user/admin dashboards; and preserved Hermes, qmd, vault, managed memory,
Notion, Nextcloud, code-server, bot, and health robustness.

## Current Status

ArcLink is scaffolded inside the existing Almanac repository with 16 Python
modules (7,094 lines), 18 test files (130 test functions), 1 hygiene test, and
a Next.js 15 + Tailwind 4 web app (~1,375 lines across 8 source files, plus 1
web test).

The foundation includes: `arclink_*` state (18 tables), product helpers,
fakeable provider adapters, entitlement gates (with reconciliation drift,
targeted comp, profile-only upsert preservation), public onboarding contracts,
ingress/access/provisioning intent, dashboard read models, queued admin-action
contracts, API/auth helpers (853 lines), executor boundaries, a local
product-surface prototype, public bot turn handlers, Telegram/Discord runtime
adapters with fake-mode dispatch, and a hosted API boundary (667 lines).

The hosted API boundary (`python/arclink_hosted_api.py`) wraps ArcLink
contracts into a production-oriented WSGI application with route dispatch under
`/api/v1`, cookie/header session transport, CORS, request-ID propagation,
structured logging, safe error shaping, and Stripe webhook skip.

The Next.js web app (`web/`) provides landing page, login, onboarding workflow,
user dashboard, and admin dashboard views using the ArcLink brand system. Views
currently use static/mock data and need wiring to the hosted API.

This is not live SaaS provisioning yet. The code records intent and proves
no-secret behavior. It does not create live infrastructure, mutate live provider
accounts, or run hosted public bots.

## Active Next Pass

Ralphie's previous `done` state means the no-secret foundation cycle passed; it
does not mean ArcLink is complete. The next run should start from
`research/RALPHIE_NEXT_PASS_STEERING.md` and turn the remaining delivery ladder
into a fresh PLAN/BUILD cycle.

After the hosted API boundary checkpoint, use
`research/RALPHIE_FINAL_FORM_GAPS_STEERING.md` as the controlling backlog for
the final product gaps. Every remaining layer must either be implemented with
tests, blocked by a named missing live credential, or tracked as a defect.

Priority order:

1. Build the production API/auth boundary over the existing Python ArcLink
   contracts.
2. Add the real ArcLink web app after the API boundary is stable, defaulting to
   Next.js/Tailwind unless a smaller repo-fit is justified.
3. Add live HTTP transport to the landed Telegram and Discord runtime adapters
   when bot tokens are present.
4. Add live-gated Docker/Cloudflare/Stripe/Chutes/bot executor paths with fake
   adapters remaining default.
5. Run live E2E only when explicit credentials are present and record the proof.

Do not repeat completed foundation work except for narrow repairs required by
the next layer. Do not call the product complete while live provisioning,
production frontend, hosted auth, public bot runtimes, and real E2E evidence
remain absent.

## Chosen Architecture

Use staged evolution of the existing Docker/Python/Bash Almanac control plane.

Selected path:

- Docker Compose first for MVP customer deployment units.
- Python first for control-plane, API/auth, billing, provisioning, dashboard
  read models, and executor boundaries.
- Bash retained for host operations and canonical deploy/health flows.
- SQLite first with Postgres-compatible schema choices.
- Chutes first through central config and per-deployment secret references.
- Stripe, Cloudflare, Traefik, Chutes, Telegram, Discord, Notion, and OAuth
  live paths behind fakeable adapters and explicit E2E gates.
- Next.js/Tailwind later for the production dashboard after the no-secret
  API/auth/RBAC boundary is hardened for hosted use.

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

The ArcLink foundation remains valid when:

- `ARCLINK_*` product config preserves legacy compatibility where needed.
- ArcLink commercial state lives in `arclink_*` tables with stable text IDs.
- Entitlements mutate only through verified Stripe events or reasoned admin
  helpers.
- Public onboarding advances to provisioning readiness only through the
  entitlement gate.
- Provisioning dry-runs render services, DNS, Traefik, access, state roots,
  timeline events, and service-health placeholders without plaintext secrets.
- Rendered service plans preserve Hermes, qmd, memory, vault watch, Nextcloud,
  code-server, bot gateway, managed context, health, and notifications.
- Admin actions are reason-required, queued, idempotent, audited, and
  secret-safe.
- Executor live mutation fails closed by default.
- Unit tests remain no-secret.

## BUILD Tasks

### 0. Active Lint Repair: Invalid Public Onboarding Channel

Status: completed in the repository. This was the first BUILD step and
repaired the no-secret lint gate before adding any hosted routes, frontend
shell, or live provider mutation.

- Change `start_public_onboarding_api()` so it validates/cleans `channel` and
  `channel_identity` through the shared onboarding validator path before calling
  `check_arclink_rate_limit()`.
- Unsupported public onboarding channels such as `email` must raise without
  writing to `rate_limits`.
- Add a focused regression in `tests/test_arclink_api_auth.py` proving rejected
  public onboarding channels leave `rate_limits` unchanged.
- Confirm `revoke_arclink_session()` rejects missing user/admin session ids
  before mutation or audit and still rejects blank or unknown session kinds.
- Confirm admin dashboard active session counts include only active,
  unrevoked, unexpired user/admin sessions.
- Confirm product-surface generic errors do not render raw exception text into
  HTML or JSON while domain errors remain intentionally user-facing.
- Confirm public bot turns share the onboarding rate-limit rail and still use
  the shared public onboarding session contract.
- Keep this step as validation and small repair only; do not add live Telegram,
  Discord, Stripe, Cloudflare, Chutes, or Docker mutation.

Acceptance probe:

```bash
python3 - <<'PY'
import sqlite3, sys
from pathlib import Path

sys.path.insert(0, str(Path("python").resolve()))
import almanac_control as control
import arclink_api_auth as api

conn = sqlite3.connect(":memory:")
conn.row_factory = sqlite3.Row
control.ensure_schema(conn)
try:
    api.start_public_onboarding_api(conn, channel="email", channel_identity="bad@example.test")
except Exception as exc:
    print(type(exc).__name__, str(exc))
print(conn.execute("SELECT COUNT(*) AS n FROM rate_limits").fetchone()["n"])
PY
```

The last printed line must be `0`.

Validation:

```bash
python3 tests/test_arclink_dashboard.py
python3 tests/test_arclink_api_auth.py
python3 tests/test_arclink_product_surface.py
python3 tests/test_arclink_public_bots.py
python3 tests/test_public_repo_hygiene.py
python3 -m py_compile python/almanac_control.py python/arclink_*.py
python3 -m ruff check python/arclink_dashboard.py python/arclink_api_auth.py python/arclink_product_surface.py python/arclink_public_bots.py tests/test_arclink_dashboard.py tests/test_arclink_api_auth.py tests/test_arclink_product_surface.py tests/test_arclink_public_bots.py
git diff --check
```

### 1. Hosted API/Auth Hardening

Status: initial hosted layer landed in `python/arclink_hosted_api.py` with
route dispatch, session/cookie transport, CORS, request-ID, safe errors, and
Stripe webhook skip. Remaining work hardens and extends this boundary.

- Keep user/admin session records storing token hashes only.
- Keep admin roles, MFA-ready factors, CSRF checks, and rate-limit hooks.
- Extend hosted routes with remaining contract coverage: user billing/provisioning
  reads, provisioning job status, admin provisioning/DNS/service-health reads.
- Keep shared public onboarding APIs for website, Telegram, and Discord.
- Keep `HostedApiConfig` runtime resolution from `ARCLINK_BASE_DOMAIN`,
  `ARCLINK_CORS_ORIGIN`, `ARCLINK_COOKIE_DOMAIN`, `ARCLINK_COOKIE_SECURE`,
  `STRIPE_WEBHOOK_SECRET`, `ARCLINK_LOG_LEVEL`, and `ARCLINK_DEFAULT_PRICE_ID`.
- Keep user billing/provisioning/dashboard read APIs over existing helpers.
- Keep admin read APIs for onboarding, payments, deployments, DNS drift,
  service health, audit, logs/events, provisioning jobs, and queued actions.
- Keep queued admin mutation APIs reason-required and idempotency-keyed.
- Keep secret reads masked by default and audited before any future reveal flow.

Validation:

```bash
python3 tests/test_arclink_onboarding.py
python3 tests/test_arclink_entitlements.py
python3 tests/test_arclink_dashboard.py
python3 tests/test_arclink_admin_actions.py
python3 tests/test_arclink_api_auth.py
python3 tests/test_arclink_executor.py
python3 tests/test_public_repo_hygiene.py
python3 -m py_compile python/almanac_control.py python/arclink_*.py
git diff --check
```

### 2. Production Dashboard

Status: Next.js 15 + Tailwind 4 web app foundation landed in `web/` with
landing page, onboarding workflow, user dashboard, and admin dashboard views.
Views use static/mock data; wiring to the hosted API is the next step.

- Wire onboarding page to hosted API public onboarding endpoints.
- Wire user dashboard to hosted API user session/billing/deployment reads.
- Wire admin dashboard to hosted API admin reads and queued action mutations.
- Add real authentication flow (login/session creation via hosted API).
- Extend user dashboard with deployment health, access links, bot setup,
  files, code, Hermes, qmd/memory freshness, skills, model, billing,
  security, and support views.
- Extend admin dashboard with onboarding funnel, users, deployments, payments,
  infrastructure, bots, security/abuse, releases/maintenance, logs, audit,
  and queued admin actions.
- Prefer deep links for Nextcloud, code-server, and Hermes until embedding is
  proven safe and reliable.

Validation:

```bash
python3 tests/test_arclink_dashboard.py
python3 tests/test_arclink_admin_actions.py
python3 tests/test_arclink_onboarding.py
python3 tests/test_public_repo_hygiene.py
git diff --check
```

Add browser coverage for desktop and narrow mobile workflows when the frontend
exists.

### 3. Live-Gated Provisioning Executor

- Enable real Docker Compose execution only in an operator-controlled E2E
  environment.
- Materialize per-deployment Compose projects from rendered intent.
- Apply Cloudflare DNS and Access/Tunnel records through live adapters.
- Mint, rotate, and revoke Chutes keys only after account-backed behavior is
  verified.
- Keep fake adapters as the default for unit tests and local development.
- Add rollback execution for failed partial deployment.

Validation:

```bash
python3 tests/test_arclink_provisioning.py
python3 tests/test_arclink_executor.py
python3 tests/test_arclink_ingress.py
python3 tests/test_arclink_access.py
python3 tests/test_public_repo_hygiene.py
python3 -m py_compile python/almanac_control.py python/arclink_*.py
git diff --check
```

Live E2E must use real credentials and must not be collapsed into unit tests.

### 4. Real E2E And Operations

- Keep `docs/arclink/live-e2e-secrets-needed.md` current.
- Test website or bot onboarding, Stripe test payment, entitlement gate,
  provisioning execution, DNS/ingress, dashboard login, agent bot contact,
  file upload, qmd retrieval, memory refresh, code-server, Hermes dashboard,
  and admin health/action flows.
- Record honest evidence for Chutes inference, private agent bot handoff,
  dashboard accuracy, queued action execution, and DNS drift repair.
- Add fleet operations for node inventory, placement, disk quotas, backup
  status, queue depth, deployment density, host metrics, rollout, rollback,
  maintenance mode, and announcements.

### 5. Product Surface Stewardship

- Keep the local WSGI surface as a no-secret prototype and contract smoke,
  even after production frontend work starts.
- Preserve fake checkout, fake provider behavior, queued-only admin actions,
  favicon route, and narrow-mobile/desktop overflow guard coverage.
- Do not let the prototype become the production authentication, billing, or
  live-operation boundary.

Validation:

```bash
python3 tests/test_arclink_product_surface.py
python3 tests/test_arclink_public_bots.py
python3 tests/test_arclink_dashboard.py
python3 tests/test_public_repo_hygiene.py
git diff --check
```

## Blockers And Risks

- The API/auth/RBAC boundary is an initial no-secret helper layer, not a hosted
  production identity system.
- Next.js web app exists (including login page) but views use mock data; API wiring is needed.
- Telegram/Discord runtime adapters exist with fake-mode dispatch; live HTTP
  transport not yet implemented.
- 1 hygiene test fails (provider name in docs context); cosmetic, not blocking.
- Live Stripe, Cloudflare, Chutes, Telegram, Discord, Notion, OAuth, and host
  execution require real credentials and E2E verification.
- Dedicated Nextcloud per deployment may become resource-heavy.
- The broad rebrand should remain staged until runtime and API boundaries are
  stable.

## BUILD Handoff

BUILD may begin with no live secrets. Start by rerunning the foundation gate
confirmation, then harden the API/auth boundary toward a hosted service. Keep
the local product surface as a replaceable prototype, and keep live provider
mutation plus live deployment execution behind explicit E2E gates.
