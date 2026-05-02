# Ralphie Steering: Next ArcLink Delivery Pass

Use this file as the first backlog source after the completed foundation slice.
The previous `done` phase means the no-secret foundation cycle passed; it does
not mean ArcLink is complete.

## Start Here

Begin with a fresh PLAN phase and convert the remaining ArcLink work into a
specific implementation plan. Do not repeat the already-completed foundation
slice except where a small repair is required to support the next phase.

Important landed checkpoint:

- Commit `019f75d` on branch `arclink` completed Production 1-2: versioned
  hosted API routes, OpenAPI 3.1 contract, checked-in static spec, rate-limit
  headers, WSGI 503 status mapping, and auth/CSRF/audit negative coverage.
- Do not route the next BUILD back to P1/P2 except for a tiny verified
  correction, such as adding explicit `429` response documentation where the
  OpenAPI text still implies rate limit belongs under `401`.
- The next substantive BUILD must begin at the first unproven gap in
  Production 3-16. Audit before editing; if an item is already implemented and
  tested, update the checklist/docs and move forward.

The next pass must move ArcLink from local helper/prototype contracts toward a
real deployable product surface while keeping all live external mutations
explicitly gated.

## Active Build Order

### 1. Production Web App

Provider Boundary Truth Audit is complete for the no-secret/fake layer. Stripe,
Cloudflare, Docker executor, and Chutes should not be rebuilt unless a failing
test proves a regression. Live proof remains deferred to the secret-gated E2E
harness.

Professional bar:

- Build the product surface as an operating console, not a placeholder demo.
- Start from the existing `/web` app and `python/arclink_product_surface.py`,
  then decide whether to deepen the Next.js API wiring, Python-rendered
  fallback, or both. Do not leave two divergent product truths.
- The user dashboard must expose real API-backed state for onboarding,
  entitlement, deployment, service health, provider/model state, billing, and
  sessions. Empty, loading, degraded, and fake/local states must be explicit.
- The admin dashboard must expose real API-backed state for onboarding funnel,
  users, payments, queue, Cloudflare/DNS drift, provider state, service health,
  audit, and guarded actions.
- The web flow, Telegram adapter, and Discord adapter must share one
  onboarding contract. Any copy or state transition added to one surface must
  be reflected in the shared tests.
- Browser/mobile verification is required. Capture desktop and narrow mobile
  evidence with Playwright or an equivalent browser check before marking
  Production 10 complete.
- Do not call the UI production-ready if it only compiles. It must be usable
  as a real operator surface with honest fake/live labels.

Required capabilities:

- Wire the existing Next.js user dashboard to the hosted `/api/v1` user
  endpoints.
- Wire the existing Next.js admin dashboard to `/api/v1/admin/*` endpoints.
- Keep fake adapter state visibly labeled; do not claim live provisioning.
- Preserve website, Telegram, and Discord onboarding parity through the shared
  API/state shape.
- Apply `docs/arclink/brand-system.md` as an acceptance gate, not decoration.

Acceptance:

- Local dev server or static preview runs.
- Desktop and narrow mobile workflows are verified with Playwright or an
  equivalent browser check.
- Text does not overflow buttons/cards/panels.
- The UI does not claim live provisioning if only fake adapters are active.

### 2. Public Bot Runtime Adapters

Add Telegram and Discord runtime adapters only after they share the same
public onboarding contract as the web flow.

Required capabilities:

- Fake/local adapters for no-secret tests.
- Telegram SDK adapter gated by explicit env.
- Discord SDK adapter gated by explicit env.
- Shared onboarding state machine, rate limits, checkout handoff, and safe
  response copy.
- No live send/webhook mutation in normal unit tests.

### 3. Live-Gated Provisioning Executor

Keep fake adapters as the default. Add live mutation only behind an explicit
operator/E2E switch and documented credentials.

Required live-gated paths:

- Docker Compose materialization from rendered per-deployment intent.
- Per-deployment roots under `/arcdata/deployments/<deployment_id>/`.
- Unprivileged containers, per-deployment networks, resource limits,
  healthchecks, rollback, and idempotent resume.
- Cloudflare DNS/Tunnel/Access mutation with scoped credentials.
- Traefik routing for dashboard, files, code, Hermes, and bot/API surfaces.
- SSH/TUI via a bastion or Cloudflare Access/Tunnel; do not claim raw SSH
  per-subdomain routing through HTTP/TLS SNI.
- Chutes per-deployment key lifecycle with secret references only.
- Stripe test checkout/webhook/customer/subscription/portal E2E.
- Telegram and Discord public bot live E2E.

## Validation Floor

Before any pass gate can call a slice complete, run the focused tests for the
touched layer plus these no-secret checks when relevant:

```bash
python3 tests/test_arclink_api_auth.py
python3 tests/test_arclink_product_surface.py
python3 tests/test_arclink_public_bots.py
python3 tests/test_arclink_dashboard.py
python3 tests/test_arclink_admin_actions.py
python3 tests/test_arclink_onboarding.py
python3 tests/test_arclink_entitlements.py
python3 tests/test_arclink_provisioning.py
python3 tests/test_arclink_executor.py
python3 tests/test_public_repo_hygiene.py
python3 -m py_compile python/almanac_control.py python/arclink_*.py
git diff --check
```

If a frontend package is added, also run and document its install/build/test
commands. Browser/mobile claims require real browser evidence.

## Live E2E Gates

Keep moving on no-secret implementation without credentials. When a task needs
live proof, pause that specific live mutation and record the needed key in
`docs/arclink/live-e2e-secrets-needed.md`.

Needed later:

- Cloudflare zone id and DNS-edit token for `arclink.online`.
- Hetzner API token or operator SSH access to the selected test node.
- Stripe test publishable key, secret key, webhook secret, and price id.
- Chutes owner/account key for per-deployment key lifecycle.
- Telegram public onboarding bot token.
- Discord app id, public key, bot token, guild id, and test channel id.
- Optional Notion, Codex, Claude/OAuth test credentials.

## Do Not Drift

- Do not claim ArcLink is production-ready until live E2E proves it.
- Do not remove or flatten Hermes, qmd, vault watch, memory synthesis, managed
  context, Nextcloud, code-server, health watch, provider auth, or bot rails.
- Do not create plaintext secrets in tests, docs, logs, or rendered outputs.
- Do not let admin mutation routes bypass auth, CSRF, idempotency, reason, or
  audit.
- Do not finish a UI slice without mobile/browser evidence.
