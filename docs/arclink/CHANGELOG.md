# ArcLink Changelog

## Foundation (2026-05-01)

Initial ArcLink foundation landed as an additive layer on the Almanac substrate.
All work is no-secret testable; no live provider credentials are required.

### Modules Delivered

- **arclink_product.py**: `ARCLINK_*` / `ALMANAC_*` config resolution with
  blank-safe precedence and conflict diagnostics.
- **arclink_chutes.py**: Chutes catalog client with direct API key and bearer
  auth support; fake no-secret adapter for tests.
- **arclink_adapters.py**: Fake/live adapter registry for Stripe, Cloudflare,
  Chutes, and bot providers.
- **arclink_entitlements.py**: Stripe webhook verification, entitlement state
  machine (none/paid/comp/cancelled), subscription mirror, atomic transaction
  ownership, idempotent replay, admin comp with audit.
- **arclink_onboarding.py**: Durable public onboarding sessions and funnel
  events for web, Telegram, and Discord; fake Stripe checkout; entitlement-gated
  provisioning readiness.
- **arclink_ingress.py**: Deterministic hostname generation, DNS drift detection,
  Traefik label rendering.
- **arclink_access.py**: Dedicated per-deployment Nextcloud isolation model,
  Cloudflare Access TCP SSH strategy guard.
- **arclink_provisioning.py**: Dry-run provisioning renderer producing Docker
  Compose, DNS, Traefik, state-root, health placeholder, and secret-reference
  intent; job state machine with retry and rollback planning.
- **arclink_executor.py**: Fail-closed mutating boundary for Docker Compose,
  Cloudflare DNS/Access, Chutes key lifecycle, Stripe actions, and rollback;
  strict idempotency-key replay; secret-free results.
- **arclink_dashboard.py**: User dashboard (profile, entitlement, deployments,
  health, billing, bot contact, model hints) and admin dashboard (funnel,
  subscriptions, deployments, health, DNS drift, provisioning, audit, actions);
  queued admin action intent with secret rejection.
- **arclink_api_auth.py**: Hashed user/admin sessions, CSRF tokens, rate-limit
  hooks, MFA-ready admin gates, safe error shaping.
- **arclink_hosted_api.py**: Production WSGI app with `/api/v1` route dispatch,
  cookie/header session transport, CORS, request-ID propagation, Stripe webhook
  skip for no-secret environments.
- **arclink_product_surface.py**: Local stdlib WSGI prototype with onboarding
  workflow, user/admin dashboards, JSON API routes, ArcLink brand styling.
- **arclink_public_bots.py**: Telegram and Discord public onboarding bot
  conversation skeletons sharing the same session contract as web.

### Schema

18 `arclink_*` tables added to `almanac_control.py`:

- `arclink_users`, `arclink_deployments`, `arclink_subscriptions`
- `arclink_stripe_webhooks`, `arclink_onboarding_sessions`,
  `arclink_onboarding_events`
- `arclink_provisioning_jobs`, `arclink_service_health`,
  `arclink_timeline_events`
- `arclink_action_intents`, `arclink_audit`, `arclink_rate_limits`
- `arclink_admin_sessions`, `arclink_user_sessions`
- And supporting indexes and partial unique constraints.

### Key Design Decisions

- **Additive**: ArcLink namespaces (`ARCLINK_*`, `arclink_*`) sit alongside
  Almanac; no existing paths are renamed or broken.
- **No-secret first**: All unit/regression tests run without live credentials.
  Fake adapters default everywhere.
- **Dry-run before live**: Provisioning renders intent records before any
  container, DNS, or provider mutation. The executor is fail-closed by default.
- **Entitlement separation**: User profile upserts never implicitly mutate
  entitlement state. Entitlement changes require explicit writers.
- **Secret references**: `secret://...` references throughout; plaintext
  rejection enforced in provisioning, executor, dashboard, and admin actions.

### Known Gaps

- No production live execution adapters (Docker, Cloudflare, Chutes, Stripe).
- No production frontend dashboard (Next.js/Tailwind planned).
- No live Telegram/Discord public bot clients.
- No live E2E test suite with real credentials.
- TOTP/MFA is schema-ready but not code-verified against real TOTP providers.
