# Ralphie Steering: Full ArcLink Delivery Program

Use this as the controlling backlog after the responsive repair is accepted.
Do not stop at the local WSGI prototype. The prototype is only a contract probe
and no-secret smoke surface.

## Mission

Transform ArcLink into ArcLink end to end:

- Chutes-first, self-serve, paid, single-user AI infrastructure.
- Entry through website workflow, Telegram public onboarding bot, or Discord
  public onboarding bot.
- Stripe entitlement gates provisioning.
- Per-user deployment with obscure ArcLink hostnames, Docker isolation,
  Hermes, qmd, vault watch, managed memory stubs, Nextcloud/files,
  code-server, Hermes dashboard, bot handoff, health checks, logs, and upgrade
  rails.
- Responsive user dashboard and responsive owner/admin dashboard.
- Cloudflare, Hetzner, Stripe, Chutes, Telegram, Discord, Notion, Codex, and
  Claude live behavior proven only through explicit E2E configuration and
  recorded evidence.
- Brand system applied throughout public copy, dashboards, bot messages, docs,
  config examples, tests, and new ArcLink-native surfaces.

## Non-Negotiable Product Direction

- Preserve ArcLink's proven orchestration. Do not throw away Hermes, qmd,
  managed context, memory synthesis, vault watch, Notion rails, health watch,
  agent supervisor, Nextcloud, code-server, Telegram/Discord onboarding, or
  provider auth.
- New public/product surfaces must say ArcLink, not ArcLink. Legacy
  `ARCLINK_*` compatibility may remain only as aliases for existing installs.
- Chutes is the default inference path. The default base URL is
  `https://llm.chutes.ai/v1`; the default model is
  `moonshotai/Kimi-K2.6-TEE` until the model catalog refresh path proves a
  better current default.
- BYOK/OpenAI Codex and Anthropic Claude remain power-user lanes. Keep their
  auth flows compatible with the existing ArcLink provider-auth machinery.
- Surface the technology tastefully. Hermes, qmd, memory stubs, vaults,
  Chutes, skills, health, and private infrastructure are product strengths.
- The first screen of the website/app must be usable onboarding, not a
  marketing-only landing page.
- Mobile is not optional. Public onboarding, user dashboard, and admin overview
  must work at narrow mobile widths without horizontal overflow or clunky
  embedded tools.

## Delivery Ladder

### 1. Finish Phase 9 Acceptance

The responsive repair for `python/arclink_product_surface.py` has recorded
browser evidence. The active Phase 9 acceptance work is to
reconcile stale handoff docs and add a minimal `/favicon.ico` response so future
browser gates do not treat a harmless 404 as a console failure.

Acceptance:

- No page-level horizontal overflow at narrow mobile widths on home,
  onboarding session, user dashboard, and admin dashboard.
- Desktop path still works.
- `/favicon.ico` does not 404.
- Admin actions remain reason-required, queued, audited, secret-free, and do
  not mutate DNS/provider state.
- Existing no-secret tests and compile checks pass.

### 2. Production API And Auth Boundary

Build the real backend boundary that the production dashboards and bots will
consume. Prefer reusing the Python control-plane modules and adding the least
new machinery that fits the repo. If choosing FastAPI or another framework,
document the decision and keep it testable.

Required capabilities:

- User sessions and dashboard auth.
- Separate admin auth with roles, short-lived sessions, and TOTP-ready schema.
- CSRF/rate-limit/session protections where applicable.
- Public onboarding API shared by website, Telegram, and Discord.
- Billing/subscription read APIs and Stripe webhook endpoints.
- Deployment/provisioning read APIs.
- Queued admin action APIs with reason-required mutation, append-only audit,
  idempotency, and fake executor default.
- Secret reveal APIs are masked by default and require reason/audit.
- Health/log/read-model APIs remain secret-free unless explicitly protected.

### 3. Production Frontend

Add the production ArcLink web app after the API/auth contracts are stable.
Expected stack: Next.js 15 + Tailwind, unless a better fit is justified before
implementation.

Required surfaces:

- Public start workflow backed by the shared onboarding contract.
- User dashboard: deployment health, launch links, bot setup, files, code,
  Hermes, memory, skills, model, billing, security, support.
- Admin dashboard: overview, onboarding funnel, users/deployments, payments,
  infrastructure, bots, security/abuse, releases/maintenance, logs/audit.
- Brand kit applied from `docs/arclink/brand-system.md`.
- Use host/deep-link fallbacks for Nextcloud, code-server, and Hermes if iframe
  embedding is brittle.
- Playwright or equivalent browser coverage for desktop and mobile workflows.

### 4. Live-Gated Provisioning Executor

Do not enable live mutation by default. Add live adapters behind explicit
operator/E2E configuration and keep fake adapters as default.

Required live-gated paths:

- Docker Compose materialization from rendered per-deployment intent.
- Per-deployment state roots under `/arcdata/deployments/<deployment_id>/`.
- Unprivileged containers, per-deployment networks, resource limits, health
  checks, rollback, and idempotent resume.
- Cloudflare DNS/wildcard/Tunnel/Access mutation through scoped credentials.
- Traefik routing for dashboard, files, code, Hermes, and bot/API surfaces.
- SSH/TUI via bastion or Cloudflare Access/Tunnel. Do not claim raw SSH
  per-subdomain routing.
- Chutes per-deployment key lifecycle with secret references only.
- Stripe test checkout/webhook/customer/subscription/portal integration.
- Telegram and Discord public bot live adapters.
- Private agent bot handoff.

### 5. Real E2E And Operations

When credentials are available, run real E2E instead of faking success.

Required evidence:

- Website onboarding to Stripe test checkout to provisioning job.
- Telegram onboarding to checkout/provisioning.
- Discord onboarding to checkout/provisioning.
- Cloudflare hostname resolves and routes to the right services.
- Docker stack boots and passes health checks.
- Chutes inference works through the selected auth/header path.
- Hermes can answer through the private bot lane.
- qmd retrieval sees uploaded vault content.
- Memory synth updates and managed context receives hot stubs.
- Nextcloud/files and code-server are reachable.
- User dashboard shows accurate state.
- Admin dashboard shows funnel, payments, health, jobs, logs, DNS drift, and
  queued actions.
- Admin restart/resynth/DNS repair actions are audited and execute only through
  the guarded executor.

### 6. Scale And Maintenance

After single-node Hetzner MVP works:

- Add node inventory and deployment placement.
- Add host metrics, disk quotas, backup status, queue depth, and deployment
  density to admin.
- Add image/version inventory, canary rollout, maintenance mode, rollback, and
  announcement delivery.
- Add model catalog refresh for Chutes/OpenAI/Anthropic defaults and reasoning
  levels.
- Keep Kubernetes/Nomad deferred until Docker/node agents become the measured
  bottleneck.

## Testing Discipline

- No-secret unit/regression tests must never require live provider credentials.
- Every live-capable adapter needs fake tests plus live E2E documentation.
- Browser claims require real browser checks on desktop and mobile.
- Do not mark a live integration complete unless a real credential-backed E2E
  pass is recorded in docs.
- `git diff --check`, relevant Python compile checks, focused tests, and public
  repo hygiene must pass before each gate.

## Required Credential Ask List

Keep no-secret work moving, but ask for these before live E2E:

- Cloudflare zone id and DNS/edit token for `arclink.online`.
- Hetzner API token or operator SSH access to the selected test node.
- Stripe test publishable key, secret key, webhook secret, and price id.
- Chutes owner/admin key capable of per-deployment key lifecycle.
- Telegram public onboarding bot token.
- Discord app id, public key, bot token, guild id, and test channel id.
- Optional Notion test workspace/token.
- Optional Codex and Claude OAuth/BYOK test accounts.

## Do Not Do

- Do not collapse the product into only a WSGI demo.
- Do not remove existing ArcLink services to simplify the plan.
- Do not use path-prefix routing for Nextcloud/code-server unless tested.
- Do not expose raw SSH through HTTP/Traefik HostSNI as if it works.
- Do not place plaintext provider/customer secrets in tests, docs, logs, or
  rendered dry-run output.
- Do not call fake/live behavior complete without the matching evidence.
