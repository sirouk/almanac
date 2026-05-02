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

## Professional Finish Gate

Do not call ArcLink finished because a phase says `done`. Treat the final form
as a launchable operating system for private AI deployments. A slice is only
complete when the code, tests, docs, UI behavior, and operator story all agree.

Required finish behavior:

- Every primary user path has a real implementation path: web onboarding,
  Telegram onboarding, Discord onboarding, checkout handoff, entitlement,
  provisioning intent, dashboard visibility, service links, billing portal,
  and support or recovery guidance.
- Every primary admin path has a real implementation path: funnel visibility,
  user lookup, payment state, queue state, DNS/provider drift, service health,
  audit, guarded actions, release status, and incident recovery guidance.
- Fake adapters are visibly labeled as fake/local wherever they appear in UI,
  tests, docs, or runbooks. Live claims require live proof.
- Browser/mobile claims require browser evidence. Use Playwright or an
  equivalent browser check for desktop and narrow mobile views, including text
  overflow and route smoke coverage.
- Backend claims require deterministic tests, safe error shapes, auth/audit
  coverage, and no-secret fake adapter coverage before any live-gated work.
- Live external work must stay behind explicit E2E switches and documented
  credentials. A missing key is an external blocker, not a reason to skip the
  fake/live boundary.
- Documentation must be a truth layer. If code says one thing and docs say
  another, fix the mismatch before committing.
- Each completed production item must name the proof: commit, files changed,
  focused tests, browser checks when relevant, and remaining live blockers.

Quality bar:

- Prefer small, composable modules over broad rewrites.
- Preserve Almanac's working orchestration surfaces while renaming and
  streamlining public ArcLink surfaces.
- Keep public UI and bot copy direct, operator-grade, and brand aligned.
- Keep admin UI dense, useful, and action-oriented. Avoid decorative panels
  that do not help operate the system.
- No plaintext secrets, no local absolute path leakage, no overclaimed uptime,
  no live-service promises without a verified live run.

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

- [x] Production 1: Hosted API exposes a coherent versioned contract for
  onboarding, checkout, entitlement, provisioning, user dashboard, admin
  dashboard, health, audit, DNS drift, provider state, webhooks, and operator
  actions, with fake adapters defaulting safely.
- [x] Production 2: Every mutating API route has explicit auth, role checks,
  CSRF or webhook signature validation, structured audit logging, and negative
  tests that prove unauthorized users cannot mutate state.
- [x] Production 3: Stripe boundary supports checkout, webhook ingestion,
  subscription state, billing portal, refunds or admin notes, failed payment
  state, and Stripe-vs-local reconciliation with fake tests.
- [x] Production 4: Cloudflare boundary supports hostname reservation,
  DNS record creation, propagation/drift checks, teardown, retry safety, and
  fake tests.
- [x] Production 5: Docker Compose executor can render, validate, start, stop,
  restart, inspect, and teardown per-user stacks with resource limits, health
  checks, volume isolation, and dry-run/fake coverage.
- [x] Production 6: Chutes default provider flow includes owner-side key
  lifecycle, per-deployment key state, model catalog/default selection,
  inference smoke path, failure reporting, and fake tests.
- [x] Production 7: Telegram and Discord onboarding flows share the same state
  machine as web onboarding, preserve parity, validate payloads, and have live
  adapters behind explicit secret gates.
- [x] Production 8: User dashboard is responsive and production-useful:
  billing, deployment state, service links, health, model/provider state, vault
  status, memory/qmd freshness, bot status, support, and security/session
  controls.
- [x] Production 9: Admin dashboard is responsive and operator-useful:
  18-tab layout (overview, users, deployments, onboarding, health, provisioning,
  dns, payments, infrastructure, bots, security, releases, audit, events,
  actions, sessions, provider, reconciliation) wired to all hosted API admin
  endpoints via api.ts. Queue-action and revoke-session forms with CSRF.
  Sidebar + mobile tab layout. StatusBadge and ErrorAlert shared components.
- [x] Production 10: Web UI passes professional product checks: ArcLink brand
  system, mobile layouts, no overlapping text, no placeholder claims of live
  services, accessible forms, clear empty/error/loading states, and route-level
  smoke tests. Browser proof: `cd web && npm run test:browser` completed
  with 41 passed and 3 desktop-only skips on 2026-05-02.
- [x] Production 11: E2E harness proves the fake full journey: web signup,
  onboarding answers, checkout simulation, entitlement activation,
  provisioning request, service health visibility, admin audit, and user
  dashboard state. Proof: `python3 tests/test_arclink_e2e_fake.py` -> 6 tests
  passed on 2026-05-02.
- [ ] [external] Production 12: Live E2E harness exists and is secret-gated
  with Stripe, Cloudflare, Chutes, Telegram, Discord, and read-only Docker
  checks. It must be expanded/executed as the same real-provider journey once
  external accounts and credentials exist. Current scaffold proof:
  `python3 tests/test_arclink_e2e_live.py` skips cleanly when
  `ARCLINK_E2E_LIVE` is unset. Blocked: all external credentials and a
  deliberate credentialed live run.
- [x] Production 13: Deployment assets exist for the selected host: env
  example, secret checklist, Docker/Traefik or chosen ingress plan, backup and
  restore notes, health checks, restart procedure, and release/rollback steps.
  Proof: `config/env.example`, `docs/arclink/secret-checklist.md`,
  `docs/arclink/ingress-plan.md`, `docs/arclink/backup-restore.md`,
  `docs/arclink/operations-runbook.md` (sections 7-9: health, restart, release).
- [x] Production 14: Observability is real enough to operate: structured
  events, health snapshots, queue/deployment status, admin-facing audit, drift
  detectors, and documented alert candidates. Proof:
  `docs/arclink/alert-candidates.md` (critical/warning/info signals), admin
  dashboard infrastructure/events/audit/reconciliation tabs (P9), structured
  JSON logs via `ARCLINK_LOG_LEVEL`.
- [x] Production 15: Data safety is explicit: per-user isolation, volume
  layout, backup plan, teardown safeguards, destructive-action confirmations,
  and no secret values in logs, docs, tests, or generated artifacts. Proof:
  `docs/arclink/data-safety.md` (isolation, volumes, teardown safeguards,
  secret leak prevention), `_reject_secret_material()` across boundaries,
  `tests/test_public_repo_hygiene.py` secret scan.
- [x] Production 16: Documentation matches the live code and does not overclaim
  live functionality; every remaining live blocker is named with the exact
  credential/account required. Proof: all docs audited against code on
  2026-05-02, `docs/arclink/live-e2e-secrets-needed.md` names every blocker,
  no live claims without live proof in shipped docs.

## Current Next Objective Queue

This queue supersedes broad "Production 1-16 gaps" language for the next Ralphie
loop. Complete these in order, one coherent slice per build cycle, with tests
and docs. Do not mark the project done while any non-external item remains.

1. Respect the landed checkpoint:
   - Production 1-11 and 13-16 are complete for the no-secret foundation.
   - Do not rebuild hosted API, auth, Stripe, Cloudflare, Docker executor,
     Chutes, Telegram, Discord, user dashboard, admin dashboard, or browser
     product-proof slices unless a regression is proven by a failing test.
   - Live provider proof remains deferred to Production 12 and requires real
     credentials.
2. Prove the Journey (Production 11 complete, Production 12 externally blocked):
   - Keep the no-secret fake E2E harness passing for web signup, onboarding
     answers, checkout simulation, entitlement activation, provisioning
     request, service health visibility, admin audit, and user dashboard state.
   - Keep the secret-gated live E2E scaffold honest: it must skip cleanly until
     Stripe, Cloudflare, Chutes, Telegram, Discord, and Docker live credentials
     exist, and it must not be marked live-proven until a credentialed run
     succeeds.
3. Operations foundation (Production 13-16) is complete:
   - Deployment assets, env examples, runbooks, backup/restore, health checks,
     restart/release/rollback procedures are documented.
   - Observability and admin-facing drift/audit visibility are documented.
   - Data-safety documentation and destructive-action safeguards are documented.
   - Documentation truth pass must stay honest: no live claim without live proof.
4. Keep the proof ledger current:
   - Each completed production item must update this checklist and name the
     proof command, commit, and remaining external blockers.
5. New landed host-readiness checkpoint:
   - Gaps A-C are complete for the no-secret foundation in commit `a9ea651`:
     host readiness CLI, provider diagnostics CLI, and injectable Docker
     executor runner.
   - Gap D/E no-secret scaffolding is landed in commit `2e6fa98`: live journey
     model, deployment evidence ledger, live E2E wiring, and evidence template.
   - Operator/admin snapshot is landed in commit `007b6cb`: host readiness,
     provider diagnostics, live journey blockers, and evidence status.
   - Next Ralphie work should target live-proof orchestration: credential
     validation, dry-run/live runner, and redacted evidence artifacts, not
     rebuilding Gaps A-E scaffolds.

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
