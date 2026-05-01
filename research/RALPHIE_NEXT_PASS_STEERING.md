# Ralphie Steering: Next ArcLink Delivery Pass

Use this file as the first backlog source after the completed foundation slice.
The previous `done` phase means the no-secret foundation cycle passed; it does
not mean ArcLink is complete.

## Start Here

Begin with a fresh PLAN phase and convert the remaining ArcLink work into a
specific implementation plan. Do not repeat the already-completed foundation
slice except where a small repair is required to support the next phase.

The next pass must move ArcLink from local helper/prototype contracts toward a
real deployable product surface while keeping all live external mutations
explicitly gated.

## Active Build Order

### 1. Production API/Auth Boundary

Build the hosted backend boundary that production dashboards, public onboarding,
and bot adapters will consume.

Prefer the existing Python control-plane modules. If adding FastAPI, Starlette,
or another HTTP framework, document why it is the smallest clean fit and add
repeatable no-secret tests. Do not build a parallel state model when
`python/almanac_control.py` and the `python/arclink_*.py` helpers already
express the product contracts.

Required capabilities:

- Public onboarding API shared by website, Telegram, and Discord.
- User session transport with token hashes only.
- Admin session transport with role checks, CSRF protection, TOTP-ready schema,
  and reason-required mutations.
- Stripe webhook and billing read endpoints using fake/default adapters unless
  live E2E configuration is explicit.
- User deployment/dashboard read endpoints backed by current read models.
- Admin overview/funnel/users/payments/infrastructure/bots/security/releases
  read endpoints backed by current read models.
- Queued admin action endpoints that are idempotency-keyed, audited, and
  secret-safe.
- Masked secret-reference endpoints only; no plaintext secret reveal unless a
  future audited reason/reveal flow is explicitly designed and tested.

Acceptance:

- No unauthenticated admin action route.
- Invalid public onboarding channels fail before rate-limit writes.
- Session revoke and admin mutation failures happen before mutation or audit
  when preconditions are invalid.
- Safe error shapes do not leak raw exception text.

### 2. Production Web App

After the API boundary is stable, add the production ArcLink web app.

Default to Next.js 15 + Tailwind unless repo constraints make a smaller first
step clearly better. If adding a frontend package, keep it minimal,
scriptable, and documented.

Required surfaces:

- First screen is usable onboarding, not a marketing-only landing page.
- Website onboarding form/workflow uses the shared public onboarding API.
- User dashboard covers deployment health, launch links, bot setup, files,
  code, Hermes, qmd/memory freshness, skills, model, billing, security, and
  support.
- Admin dashboard covers overview, onboarding funnel, users/deployments,
  payments, infrastructure, bots, security/abuse, releases/maintenance, logs,
  audit, and queued actions.
- Brand tokens come from `docs/arclink/brand-system.md`: jet black/carbon,
  soft white, signal orange, blue/green for state only, no generic purple AI
  gloss.
- Mobile is mandatory. Public onboarding, user dashboard, and admin overview
  must work without horizontal overflow.
- Use direct host/deep-link fallbacks for Nextcloud, code-server, and Hermes
  until iframe embedding is proven reliable.

Acceptance:

- Local dev server or static preview runs.
- Desktop and narrow mobile workflows are verified with Playwright or an
  equivalent browser check.
- Text does not overflow buttons/cards/panels.
- The UI does not claim live provisioning if only fake adapters are active.

### 3. Public Bot Runtime Adapters

Add Telegram and Discord runtime adapters only after they share the same
public onboarding contract as the web flow.

Required capabilities:

- Fake/local adapters for no-secret tests.
- Telegram SDK adapter gated by explicit env.
- Discord SDK adapter gated by explicit env.
- Shared onboarding state machine, rate limits, checkout handoff, and safe
  response copy.
- No live send/webhook mutation in normal unit tests.

### 4. Live-Gated Provisioning Executor

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
