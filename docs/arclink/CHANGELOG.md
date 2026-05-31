# ArcLink Changelog

## Ground-Truth Documentation Alignment (2026-05-30)

Documentation-only alignment pass reconciling project-facing docs against the
canonical `research/ARCLINK_GROUND_TRUTH_BRIEF.md`. No code, schema, or live
behavior changed; no live-proof claims were added.

- **Module map**: rebuilt the `python/arclink_*.py` inventory to the current 84
  modules, adding the previously undocumented public Agent gateway / exec-broker
  / pod-comms / agent-supervisor family, `arclink_operator_raven` /
  `arclink_operator_agent`, the Academy modules, `arclink_memory_synthesizer`,
  `arclink_fleet_share`, and `arclink_pod_migration`.
- **Tables**: corrected the stale "23 tables" figure to 44 `arclink_*` tables
  plus 9 non-prefixed `academy_*` tables: the original Academy mode/proposal
  rows and the central corpus rows (`academy_sources`,
  `academy_corpus_specialists`, `academy_specialist_sources`,
  `academy_source_provenance`, `academy_specialist_subscriptions`). Schema
  remains idempotent `ensure_schema()` (not a versioned migration ledger).
- **Operator Raven**: corrected the stale "read-only/dry-run" framing (GAP-029);
  it queues real, audited, identity- and approval-code-gated mutations
  (`pod_repair`, `rollout`, `host_upgrade`, `pin_upgrade`) plus a single in-stack
  operator Hermes agent with a free-form bridge. `rollout` is wired/queueable
  (GAP-032), not "pending/disabled".
- **New doc**: added `docs/arclink/public-agent-gateway.md` for the public Agent
  gateway and trusted-host broker/helper family (per-turn `docker exec` via
  `gateway-exec-broker`; service/port/header/socket table; GAP-019 invariants).
- **Fleet shared folder** (2026-05-29): documented `arclink_fleet_share`
  (per-Captain bare git hub, multi-writer rebase, conflict-surfacing-not-clobber)
  as the writable **Fleet** root in Drive/Code and in the data-safety story.
- **Backup/restore**: corrected state-root/volume paths to
  `/arcdata/deployments/{id}` (`config/vault/state/nextcloud/published/`) and
  documented the two backup scripts, two-phase `configure-agent-backup.sh`
  pending->verify->activate, per-user key separation, public-repo refusal, and
  the `deployment-exec-broker` lifecycle owner (GAP-013 / PG-BACKUP kept).
- **Alert candidates**: replaced the external-pager framing with the in-product
  rail (health-watch edge-triggered notifications -> `notification_outbox` ->
  operator channel, deploy-window suppression, `arclink_service_health`).
- **Finish gate**: the professional finish-gate doc now names the executable gate
  `python/arclink_surface_contract.py` + `tests/test_arclink_surface_contract.py`
  (audience/channel/state taxonomy, Captain-vocabulary lint, secret/traceback
  refusal, blocked-copy "next action" rule). GAP-033 remains open / proof-gated.
- **Academy follow-up**: reconciled this pass with the later Academy corpus/apply
  code: the central SME corpus is cross-Captain and deduplicated, weekly CE uses
  real trainee/central sources before fixture fallback, and authorized
  `academy_apply` materializes the replaceable Academy SOUL section plus a
  private receipt. Mode-end and weekly CE still do not auto-write Agent files;
  vault/qmd/skill deltas remain future/proof-gated.

Proof gates stay named in copy; GAP-019 stays acknowledged-only and not
tenant-safe. Source-level work for the active DoD is complete; remaining work is
operator-authorized live/proof.

## Native Hermes Workspace Plugins (2026-05-05)

- **Drive**: `plugins/hermes-agent/drive/` is now documented as
  the Hermes dashboard file manager. It supports local vault and
  sanitized Nextcloud WebDAV backends, bounded preview/download/upload, folder
  creation, rename/move, local trash, and local restore. WebDAV
  credentials stay server-side in the plugin API.
- **Code**: `plugins/hermes-agent/code/` is now documented as
  the native Hermes code workspace. It uses the deployment workspace root,
  opens bounded text files, guards saves with expected SHA-256 hashes, scans
  bounded git repositories, and exposes allowlisted source-control operations
  with confirmation-gated discard.
- **Terminal**: `plugins/hermes-agent/terminal/` now exposes a
  managed-pty persistent-session backend with stable session IDs, persisted
  metadata, bounded scrollback, same-origin SSE output streaming, bounded
  polling fallback, input, reload reconnect, rename/folder/reorder controls,
  confirmation-gated close, and an unrestricted-root startup guard.
  tmux-backed persistence remains future work.
- **Workspace proof**: `bin/arclink-live-proof --journey workspace --live`
  now runs Docker upgrade/reconcile, Docker health, and TLS desktop/mobile
  browser proof for Drive, Code, and Terminal through the native Hermes
  dashboard plugin routes. The browser proof records redacted evidence and
  sanitized screenshot references; it does not prove the broader hosted
  customer journey.
- **Installer and Docker repair**: `bin/install-arclink-plugins.sh` installs
  Drive, Code, Terminal, and managed context by default and removes legacy
  dashboard plugin aliases. Docker reconcile/health repairs Hermes dashboard
  mounts, reruns the managed plugin installer for deployment stacks, recreates
  `hermes-dashboard`, and can publish per-deployment Hermes/files/code tailnet
  HTTPS app URLs in Tailscale path mode.

Rationale: ArcLink-specific workspace behavior stays in ArcLink-owned plugins,
wrappers, and generated deployment config instead of patching Hermes core.
Status and runbook contracts stay no-secret and capability-driven.

## Foundation (2026-05-01)

Initial ArcLink foundation landed as an additive layer on the shared-host substrate.
All work is no-secret testable; no live provider credentials are required.

### Modules Delivered

- **arclink_product.py**: `ARCLINK_*` / `ARCLINK_*` config resolution with
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
  cookie/header session transport, CORS, request-ID propagation, and
  fail-closed Stripe webhook handling that returns 503 when
  `STRIPE_WEBHOOK_SECRET` is unset.
- **arclink_product_surface.py**: Local stdlib WSGI prototype with onboarding
  workflow, user/admin dashboards, JSON API routes, ArcLink brand styling.
- **arclink_public_bots.py**: Telegram and Discord public onboarding bot
  conversation skeletons sharing the same session contract as web.
- **arclink_telegram.py**: Telegram runtime adapter with long-polling bot
  runner, update parsing, and shared turn handler dispatch; fake mode when
  `TELEGRAM_BOT_TOKEN` is absent.
- **arclink_discord.py**: Discord runtime adapter with interaction handling,
  slash commands, signature verification stub, and shared turn handler
  dispatch; fake mode when `DISCORD_BOT_TOKEN` is absent.

### Web App Foundation

Next.js 15 + Tailwind 4 web app landed in `web/` (~1,375 lines, 8 source files):

- Landing page with hero, feature grid, and navigation.
- Multi-step onboarding workflow UI.
- User dashboard with deployment health, access links, and service status.
- Admin dashboard with system overview, user management, and operations.
- API client stub for hosted API boundary (`/api/v1`).
- Views use static/mock data; wiring to the hosted API is the next step.

### Schema

ArcLink-owned `arclink_*` tables are managed by `arclink_control.py`:

- `arclink_users`, `arclink_webhook_events`, `arclink_deployments`,
  `arclink_subscriptions`
- `arclink_provisioning_jobs`, `arclink_dns_records`, `arclink_admins`,
  `arclink_user_sessions`, `arclink_admin_sessions`
- `arclink_admin_roles`, `arclink_admin_totp_factors`,
  `arclink_audit_log`, `arclink_service_health`, `arclink_events`
- `arclink_model_catalog`, `arclink_onboarding_sessions`,
  `arclink_onboarding_events`, `arclink_action_intents`
- `arclink_fleet_hosts`, `arclink_deployment_placements`,
  `arclink_action_attempts`, `arclink_rollouts`
- And supporting indexes and partial unique constraints.

### Key Design Decisions

- **Additive**: ArcLink namespaces (`ARCLINK_*`, `arclink_*`) sit alongside
  ArcLink; no existing paths are renamed or broken.
- **No-secret first**: All unit/regression tests run without live credentials.
  Fake adapters default everywhere.
- **Dry-run before live**: Provisioning renders intent records before any
  container, DNS, or provider mutation. The executor is fail-closed by default.
- **Entitlement separation**: User profile upserts never implicitly mutate
  entitlement state. Entitlement changes require explicit writers.
- **Secret references**: `secret://...` references throughout; plaintext
  rejection enforced in provisioning, executor, dashboard, and admin actions.

### Entitlements Enhancements

- Reconciliation drift detection for subscription/entitlement consistency.
- Targeted comp: deployment-scoped comp without mutating user-level entitlement.
- Profile-only upsert preservation: `upsert_arclink_user()` no longer resets
  entitlement state during profile-only updates for returning users.

## Admin Dashboard and API Wiring (2026-05-02)

- **Production 9**: Admin dashboard fully wired to hosted API with 18 tabs
  (overview, users, deployments, onboarding, health, provisioning, dns,
  payments, infrastructure, bots, security, releases, audit, events, actions,
  sessions, provider, reconciliation). Queue-action and revoke-session forms
  with CSRF. Sidebar + mobile tab layout. StatusBadge and ErrorAlert shared
  components.

## Browser Product Proof (2026-05-02)

- **Production 10**: Playwright suite covering `/`, `/login`, `/onboarding`,
  `/dashboard`, and `/admin` across desktop/mobile viewports with deterministic
  API mocks. ArcLink brand system applied (Jet Black, Carbon, Soft White,
  Signal Orange, Space Grotesk). Accessible forms, loading/empty/error states,
  mobile overflow checks, fake-adapter labeling. 41 tests passed, 3
  desktop-only skips.

## E2E Journey Harnesses (2026-05-02)

- **Production 11**: Fake E2E harness in `tests/test_arclink_e2e_fake.py` (6
  tests). Proves full journey: web signup, onboarding answers, checkout
  simulation, Stripe webhook, entitlement activation, provisioning request,
  service health visibility, user dashboard state, admin audit, admin actions.
  All fake adapters, no live credentials.

- **Production 12**: Live E2E scaffold in `tests/test_arclink_e2e_live.py`
  with secret-gated Stripe, Cloudflare, Chutes, Telegram, Discord, and
  read-only Docker checks. All skip cleanly when live flags/credentials are
  absent. Full live journey proof remains blocked on external credentials.

## Operations, Safety, and Documentation (2026-05-02)

- **Production 13**: Deployment assets landed: `config/env.example` (all
  ArcLink env vars with comments), `docs/arclink/secret-checklist.md` (secret
  inventory and handling rules), `docs/arclink/ingress-plan.md` (DNS layout,
  Cloudflare, Traefik, SSH, drift, teardown), `docs/arclink/backup-restore.md`
  (backup targets, schedule, restore procedures, disaster recovery, retention).
  Operations runbook updated with health check polling, restart/recovery, and
  release/rollback sections.

- **Production 14**: Observability documented in
  `docs/arclink/alert-candidates.md` with critical (API health, webhook
  failure, provisioning failure, service unhealthy), warning (DNS drift,
  reconciliation drift, rate limits, stale queues), and informational
  (onboarding funnel, deployment growth, audit volume) alert signals. Admin
  dashboard already wires health snapshots, queue status, deployment status,
  DNS drift, and event visibility from P9.

- **Production 15**: Data safety documented in `docs/arclink/data-safety.md`
  covering per-user isolation model, volume layout, secret storage rules,
  backup plan references, teardown safeguards (admin confirmation, audit
  logging, state root preservation, volume preservation, separate DNS
  teardown, destructive delete gating), and secret leak prevention
  (`_reject_secret_material()` across boundaries, hygiene test scans).

- **Production 16**: Documentation truth pass completed. All docs audited
  against live code modules and test coverage. No claims of live customer
  provisioning. Every live blocker named with exact credential/account in
  `docs/arclink/live-e2e-secrets-needed.md`. Foundation runbook, operations
  runbook, and architecture docs aligned with current module map.

## Provider Boundary Progress (2026-05-02)

Incremental Production 3-6 work: resource limits, healthchecks, and expanded
fake adapter coverage.

### Provisioning (Production 5)

- `arclink_provisioning.py` now renders per-service `deploy.resources.limits`
  (memory and CPU) for all 13 Compose services via `ARCLINK_DEFAULT_RESOURCE_LIMITS`.
- Healthchecks added for data/web services: `nextcloud-db` (pg_isready),
  `nextcloud-redis` (redis-cli ping), and `nextcloud` (curl status.php).
- `_service()` helper accepts optional `deploy` and `healthcheck` dicts.
- New test: `test_rendered_services_include_resource_limits_and_healthchecks`
  verifies every service has limits, data services have healthchecks, app-only
  services do not, and all volumes stay under the deployment root.

### Stripe Boundary (Production 3)

- `FakeStripeClient.create_portal_session()` tested: unique session IDs,
  customer/return-URL round-trip.
- Admin refund and cancel action types tested with audited notes, metadata
  storage, and plaintext-secret rejection.

### Cloudflare Boundary (Production 4)

- Fake Cloudflare propagation check tested: provision records, verify zero
  drift, teardown, verify drift returns.

### Chutes Provider (Production 6)

- Catalog refresh test: simulates model list update, validates new model passes
  `validate_default_chutes_model`.

### Known Gaps

- No production live execution adapters (Docker, Cloudflare, Chutes, Stripe).
- Web app foundation exists but views use mock data; API wiring needed.
- Telegram/Discord runtime adapters exist with fake-mode dispatch; live HTTP
  transport (polling/gateway) not yet implemented.
- Live E2E scaffold exists but full live proof is blocked on real credentials
  and a deliberate credentialed run (P12).
- TOTP/MFA is schema-ready but not code-verified against real TOTP providers.

## Scale Operations Spine (2026-05-02)

- **Fleet registry and placement**: `python/arclink_fleet.py` adds host
  registration, active/degraded/offline status, drain flags, capacity slots,
  observed load, region/tag filtering, deterministic placement by headroom, and
  placement removal.
- **Action worker bridge**: `python/arclink_action_worker.py` consumes queued
  admin action intents, records attempts, dispatches supported actions through
  the fake/live-gated executor or safe local transitions, writes audit/event
  rows, redacts executor errors, and recovers stale running actions.
- **Rollout records**: `python/arclink_rollout.py` adds durable rollout state,
  canary wave advancement, pause/fail/rollback transitions, version drift
  visibility, and rollback validation requiring `preserve_state_roots`.
- **Operator visibility**: `GET /api/v1/admin/scale-operations` and
  `build_scale_operations_snapshot()` expose fleet capacity, placements, stale
  actions, recent action attempts, active rollouts, and last executor result
  behind admin auth. The admin web view renders the same scale-operations
  snapshot.
- **Schema**: Added `arclink_fleet_hosts`,
  `arclink_deployment_placements`, `arclink_action_attempts`, and
  `arclink_rollouts`.

Rationale: scale behavior stays inside the existing ArcLink control plane and
executor gate until live proof demonstrates the need for a separate queue or
scheduler.

## Deterministic Web Linting (2026-05-02)

- `web/eslint.config.mjs` uses ESLint flat config with Next core-web-vitals and
  TypeScript rules.
- `web/package.json` pins `npm run lint` to source/config files with
  `--max-warnings=0`.
- `web/package-lock.json` is refreshed so web lint/install behavior is
  reproducible for future agents and CI.
