# ArcLink Implementation Plan

## Goal

Transform the inherited shared-host foundation into ArcLink: a Chutes-first, self-serve, paid,
single-user AI deployment SaaS with web, Telegram, and Discord onboarding;
Stripe entitlement gates; domain-or-Tailscale ingress; responsive
user/admin dashboards; and preserved Hermes, qmd, vault, managed memory,
Notion, Nextcloud, code-server, bot, and health robustness.

## Controlling Definition Of Done

`research/RALPHIE_PRODUCTION_GRADE_STEERING.md` is the hard backlog source.
ArcLink is launch-ready only when Production 1-16 are complete or explicitly
blocked by named external credentials/accounts. The current codebase has
non-external coverage for Production 1-11 and 13-16. Production 12 has the
secret-gated live harness but still needs a credentialed run.

## Chosen Architecture

Selected path: evolve the existing Docker/Python/Bash ArcLink control plane
into ArcLink with additive `arclink_*` modules.

Why this path:

- It preserves working Hermes, qmd, managed memory, vault, Notion, Nextcloud,
  code-server, bot, deploy, and health surfaces.
- It keeps fake/no-secret tests deterministic while live integrations are
  credential-gated.
- It lets the Next.js dashboard consume a stable hosted API instead of owning
  business rules.

Rejected/deferred paths:

- Separate SaaS wrapper around ArcLink: viable later, but duplicates auth,
  provisioning, entitlement, and health semantics before contracts settle.
- Kubernetes/Nomad rewrite: useful only after real scale pressure appears;
  too much operational complexity for the MVP.

## Current Implementation State

- Python is the primary control-plane layer with ArcLink modules for product
  config, Chutes, provider adapters, entitlements, onboarding, API/auth,
  hosted API, dashboards, provisioning, executor, diagnostics, host readiness,
  fleet, action worker, rollout, live journey, evidence, live runner, and bot
  adapters.
- Docker Compose remains the first runtime/deployment substrate.
- SQLite remains the first ArcLink commercial-state database, with Postgres
  kept as an evolution path.
- Next.js 15 + Tailwind 4 is the production dashboard shell.
- Fake adapters default for Stripe, Cloudflare/domain ingress, Tailscale
  ingress, Chutes, Telegram, Discord, and Docker executor tests.
- Live execution is behind explicit flags, credential checks, and redacted
  evidence output.

## Validation Criteria

PLAN is complete when:

- Required research artifacts are project-specific, portable, and current.
- No fallback placeholder marker exists.
- BUILD can proceed without live secrets for non-external work.
- Live blockers are named by exact credential/account category.
- Implementation tasks are actionable and testable.

BUILD is complete for a slice when:

- Focused Python tests for touched ArcLink modules pass.
- Web lint/smoke/browser checks pass for UI changes.
- `git diff --check` is clean.
- Docs and coverage artifacts do not overclaim live behavior.
- Secret values are absent from code, logs, docs, tests, and generated
  artifacts.

## Actionable BUILD Tasks

### Track 1: Preserve The Landed No-Secret Foundation

Status: complete for current planning scope.

Keep these surfaces green and avoid rebuilding them unless tests prove a
regression:

- Production 1-2: hosted API, auth, CSRF, audit, OpenAPI.
- Production 3-6: Stripe, Cloudflare/domain ingress, Tailscale ingress, Docker executor, Chutes fake/live
  boundaries.
- Production 7: web/Telegram/Discord shared onboarding state machine.
- Production 8-10: user dashboard, admin dashboard, brand/browser product
  checks.
- Production 11: fake full-journey E2E.
- Production 13-16: deployment docs, observability, data safety,
  documentation truth.

### Track 2: Live Proof Execution

Status: externally blocked.

Use the existing readiness/diagnostics/live-proof stack when credentials are
available:

1. Populate local/private live configuration for Stripe, Chutes, Telegram,
   Discord, the production host, and either Cloudflare domain ingress or
   Tailscale ingress.
2. Run host readiness and provider diagnostics in live mode.
3. Run the live proof runner first as a dry run, then with explicit live
   execution enabled.
4. Record redacted evidence with no secret values.
5. Update docs and steering only after a successful credentialed run.

Acceptance:

- Live runner reports all required credentials present by name.
- Live journey executes against real providers without destructive surprises.
- Evidence ledger is redacted and portable.
- Any failed live step records the precise blocker and leaves local state
  recoverable.

### Track 3: Post-Live Hardening

Status: future after credentialed proof.

1. Deploy the hosted API behind the final production identity/edge strategy.
2. Verify live dashboard data flows for user and admin surfaces.
3. Prove backup/restore and teardown on the selected host.
4. Reassess per-deployment Nextcloud resource cost with real usage data.
5. Decide whether SQLite should remain sufficient or move ArcLink SaaS state
   toward Postgres.

## External Live Proof Checklist

- [ ] [external] Stripe production account, API keys, webhook secret,
  product/price IDs, and portal config.
- [ ] [external] Domain-mode ingress: Cloudflare zone for `arclink.online` and
  scoped DNS/tunnel token.
- [ ] [external] Tailscale-mode ingress: Tailscale node login, MagicDNS/HTTPS
  certificate readiness, and Funnel/Serve approval for the selected host.
- [ ] [external] Chutes production account/key strategy for live inference and
  per-deployment credential proof.
- [ ] [external] Telegram public onboarding bot token.
- [ ] [external] Discord application credentials and bot token.
- [ ] [external] Final production host credentials if the current test host is
  not the launch host.

## Validation Floor

For planning/document-only changes:

```bash
git diff --check
```

Also confirm the fallback placeholder marker is absent before handoff.

For ArcLink backend changes, add the focused touched test files and compile
touched modules:

```bash
PYTHONPATH=python python3 tests/test_arclink_<surface>.py
python3 -m py_compile python/arclink_<surface>.py
```

For web changes:

```bash
cd web && npm run lint && npm run test
cd web && npm run test:browser
```

## BUILD Handoff

The BUILD handoff is ready for the non-external scope. The repository already
contains the no-secret implementation foundation, scale-operations spine, and
live-proof orchestration path. The only current blocker is external
credentialed proof for Production 12.

Retry guard: do not treat the missing credentialed live proof as a repairable
BUILD implementation gap. Re-enter BUILD only if a no-secret regression appears
or if the required Stripe, Chutes, Telegram, Discord, production host, and
selected ingress-mode credentials are supplied for the explicit live run. See
`consensus/build_gate.md` for the local blocker gate.
