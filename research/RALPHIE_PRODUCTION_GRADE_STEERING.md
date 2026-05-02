# Ralphie Production Grade Steering

This is the controlling definition of done for ArcLink beyond normal phase
completion. ArcLink is not complete when a single feature slice passes. ArcLink
is complete when the product can be deployed, operated, observed, recovered,
sold, and used end to end with confidence.

Use this file as a hard backlog source. Do not route to `done` while any
non-external item below remains unchecked. If an item requires live credentials
or an account that does not exist yet, leave it unchecked and mark the precise
external blocker in the run documentation.

## Product Standard

ArcLink must feel like premium private AI infrastructure. The product should be
quietly powerful, direct, secure, and operationally honest. The technology is a
feature: Hermes, qmd, Chutes, vaults, memory stubs, skills, Nextcloud,
code-server, dashboards, bots, and provisioning health should be surfaced with
confidence and taste.

## Brand Quality Gate

The UI and copy must follow `docs/arclink/brand-system.md` and the source brand
kit in `docs/arclink/brand/ArcLink Brandkit.pdf`.

- Visual system: Jet Black `#080808`, Carbon `#0F0F0E`, Soft White `#E7E6E6`,
  Signal Orange `#FB5005`, with Electric Blue `#2075FE` and Neon Green
  `#1AC153` only for status and feedback.
- Typography: Space Grotesk for display/headlines and Satoshi or Inter for UI
  and body copy.
- Interface posture: premium control room, not marketing decoration. Use dark
  precise surfaces, compact system-first icons, clear status, visible
  technology, and direct operator workflows.
- Imagery: abstract private-infrastructure/system visuals with orange
  connection paths. Avoid stock photos, generic AI art, generic purple
  gradients, broad decorative gradients, and vague atmosphere.
- Voice: clear, direct, confident, short, outcome-focused, and human. Avoid
  hype, buzzwords, overcomplication, and robotic wording.
- Product checks: desktop and mobile layouts must avoid overlapping text,
  inaccessible controls, hidden primary actions, placeholder claims, and
  unsupported live-service promises.

## Mandatory Production Checklist

- [ ] Production 1: Hosted API exposes a coherent versioned contract for
  onboarding, checkout, entitlement, provisioning, user dashboard, admin
  dashboard, health, audit, DNS drift, provider state, webhooks, and operator
  actions, with fake adapters defaulting safely.
- [ ] Production 2: Every mutating API route has explicit auth, role checks,
  CSRF or webhook signature validation, structured audit logging, and negative
  tests that prove unauthorized users cannot mutate state.
- [ ] Production 3: Stripe boundary supports checkout, webhook ingestion,
  subscription state, billing portal, refunds or admin notes, failed payment
  state, and Stripe-vs-local reconciliation with fake tests.
- [ ] Production 4: Cloudflare boundary supports hostname reservation,
  DNS record creation, propagation/drift checks, teardown, retry safety, and
  fake tests.
- [ ] Production 5: Docker Compose executor can render, validate, start, stop,
  restart, inspect, and teardown per-user stacks with resource limits, health
  checks, volume isolation, and dry-run/fake coverage.
- [ ] Production 6: Chutes default provider flow includes owner-side key
  lifecycle, per-deployment key state, model catalog/default selection,
  inference smoke path, failure reporting, and fake tests.
- [ ] Production 7: Telegram and Discord onboarding flows share the same state
  machine as web onboarding, preserve parity, validate payloads, and have live
  adapters behind explicit secret gates.
- [ ] Production 8: User dashboard is responsive and production-useful:
  billing, deployment state, service links, health, model/provider state, vault
  status, memory/qmd freshness, bot status, support, and security/session
  controls.
- [ ] Production 9: Admin dashboard is responsive and operator-useful:
  onboarding funnel, users, payments, provisioning queue, service health, host
  health, Cloudflare/DNS drift, bot state, provider state, audit trail, logs or
  log links, and guarded admin actions.
- [ ] Production 10: Web UI passes professional product checks: ArcLink brand
  system, mobile layouts, no overlapping text, no placeholder claims of live
  services, accessible forms, clear empty/error/loading states, and route-level
  smoke tests.
- [ ] Production 11: E2E harness proves the fake full journey: web signup,
  onboarding answers, checkout simulation, entitlement activation,
  provisioning request, service health visibility, admin audit, and user
  dashboard state.
- [ ] Production 12: Live E2E harness exists and is secret-gated so it can run
  the same journey against real Stripe, Cloudflare, Chutes, Telegram, Discord,
  and Docker without leaking secrets or making destructive calls accidentally.
- [ ] Production 13: Deployment assets exist for the selected host: env
  example, secret checklist, Docker/Traefik or chosen ingress plan, backup and
  restore notes, health checks, restart procedure, and release/rollback steps.
- [ ] Production 14: Observability is real enough to operate: structured
  events, health snapshots, queue/deployment status, admin-facing audit, drift
  detectors, and documented alert candidates.
- [ ] Production 15: Data safety is explicit: per-user isolation, volume
  layout, backup plan, teardown safeguards, destructive-action confirmations,
  and no secret values in logs, docs, tests, or generated artifacts.
- [ ] Production 16: Documentation matches the live code and does not overclaim
  live functionality; every remaining live blocker is named with the exact
  credential/account required.

## Current Next Objective Queue

This queue supersedes broad "Production 1-16 gaps" language for the next Ralphie
loop. Complete these in order, one coherent slice per build cycle, with tests
and docs. Do not mark the project done while any non-external item remains.

1. API contract truth:
   - Add a machine-readable OpenAPI 3.1 contract for `/api/v1`.
   - Prefer generating it from, or testing it against, the canonical
     `arclink_hosted_api._ROUTES` table.
   - Expose `GET /api/v1/openapi.json` without secrets and commit a static copy
     at `docs/openapi/arclink-v1.openapi.json`.
   - Add tests proving every `_ROUTES` entry is represented in the spec and the
     served JSON matches the checked-in contract.
2. Rate-limit transport:
   - Add `Retry-After`, `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and
     `X-RateLimit-Reset` headers on rate-limited public onboarding and login
     responses.
   - Add negative route tests that force 429/401 rate-limit behavior and assert
     the headers are present without leaking subjects or secrets.
3. Hosted API correctness:
   - Fix WSGI status text for degraded health so status code 503 maps to
     `503 Service Unavailable`, not the fallback `503 OK`.
   - Add a focused WSGI test for degraded health status text.
4. Operational docs for landed boundaries:
   - Add concise runbooks for API, ingress/DNS, Docker executor, Chutes, Stripe,
     and rollback behavior. Keep claims fake/live accurate.
5. Then proceed to Production 7-16:
   - Bot parity and live adapter gates.
   - User/admin dashboards wired to the hosted API.
   - Fake E2E full journey.
   - Secret-gated live E2E harness.
   - Deployment assets, observability, data safety, and documentation truth.

Current live blockers remain external: Stripe, Cloudflare, Chutes, Telegram,
Discord, and final production-host credentials. Fake/live boundaries and tests
are not blocked by those credentials.

## External Live Proof Checklist

- [ ] [external] Production Stripe account, API keys, webhook secret, product
  and price IDs are available for live checkout and webhook proof.
- [ ] [external] Production Cloudflare zone and scoped API token are available
  for live DNS or tunnel proof.
- [ ] [external] Production Chutes account/key strategy is available for live
  inference and per-deployment credential proof.
- [ ] [external] Telegram bot token is available for live onboarding proof.
- [ ] [external] Discord application/bot token is available for live onboarding
  proof.
- [ ] [external] Final Hetzner or selected production host credentials are
  available if the current test host is not the launch host.

## Operating Rules

1. Prefer fake adapters and deterministic tests until live credentials exist.
2. Never commit live secrets, local absolute paths, or tool transcripts.
3. Preserve Almanac's proven orchestration and health machinery unless replacing
   it with a clearly better, tested production path.
4. When a feature cannot be completed without credentials, ship the fake/live
   boundary, tests, docs, and admin visibility first.
5. Keep the branch healthy: after each substantial production slice, run the
   relevant Python tests, web tests, and TypeScript checks before committing.
