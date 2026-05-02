# Research Summary

<confidence>96</confidence>
<!-- refreshed: 2026-05-02 plan phase -->

## Goal

Transform ArcLink into ArcLink: a Chutes-first, self-serve, paid,
single-user AI deployment SaaS with web, Telegram, and Discord onboarding;
Stripe entitlement gates; Cloudflare/Traefik host routing; responsive
user/admin dashboards; and preserved Hermes, qmd, vault, managed memory,
Notion, Nextcloud, code-server, bot, and health robustness.

## Current Finding

ArcLink is already being built as a staged evolution of the existing
Docker/Python/Bash ArcLink control plane. The repository now contains the
ArcLink commercial/control-plane modules, fake/live provider boundaries,
host-readiness and diagnostics tooling, fleet/action/rollout operations spine,
Next.js dashboard shell, and extensive no-secret regression coverage.

Observed implementation signals:

- 25 `python/arclink*.py` modules covering product config, Chutes, Stripe and
  Cloudflare adapters, entitlements, onboarding, hosted API/auth, dashboards,
  provisioning, executor, diagnostics, host readiness, fleet, action worker,
  rollout, live journey, evidence, and bot adapters.
- 27 `tests/test_arclink*.py` files covering the ArcLink Python surfaces.
- `web/` contains a Next.js 15 + Tailwind 4 app with landing, login,
  onboarding, user dashboard, admin dashboard, shared UI, API client, smoke
  tests, and browser product checks.
- `compose.yaml`, `Dockerfile`, `deploy.sh`, `bin/`, Hermes plugins/hooks, qmd
  jobs, Nextcloud, memory synthesis, and systemd units remain the operational
  substrate to preserve.

## Production Coverage Status

The non-external ArcLink foundation is present for Production 1-11 and
Production 13-16:

- Hosted API contract, auth/CSRF/audit, provider fake boundaries, Docker
  executor planning, Chutes model/key abstractions, Telegram/Discord onboarding
  parity, user/admin dashboard read models, fake full-journey E2E, deployment
  docs, observability, data safety, and documentation truth are represented in
  code/tests/docs.
- Production 12 remains the only live-proof blocker. The live E2E harness,
  live proof runner, readiness checks, diagnostics, ordered journey model, and
  redacted evidence ledger exist, but credentialed execution is externally
  blocked.

## Implementation Path Comparison

| Path | Strengths | Weaknesses | Decision |
| --- | --- | --- | --- |
| Evolve existing Docker/Python ArcLink control plane | Preserves working Hermes/qmd/memory/deploy behavior, keeps no-secret tests deterministic, and avoids premature orchestration churn. | Requires staged naming and compatibility discipline. | Selected. |
| Build a separate SaaS shell around ArcLink | Cleaner commercial boundary later. | Duplicates auth, provisioning, health, and entitlement state before contracts settle. | Defer. |
| Replatform to Kubernetes/Nomad | Better long-term scheduling primitives. | Too heavy before live demand and provider proof exist. | Reject for MVP. |

## Key Assumptions

- Docker Compose is the first customer-deployment target.
- Python remains the business-logic and hosted-API layer.
- Next.js/Tailwind is the production dashboard layer and consumes API
  contracts instead of duplicating business rules.
- SQLite stays first for ArcLink commercial state, with schema choices kept
  portable for a later Postgres path.
- `ARCLINK_*` configuration takes precedence while `ARCLINK_*` compatibility is
  preserved where existing runtime paths depend on it.
- Fake adapters are the default for unit and fake E2E tests.
- Live provider execution requires explicit live flags and real credentials.

## BUILD Handoff

The plan phase is ready for BUILD handoff, but the actionable BUILD queue is
credential-limited: all non-external production slices identified in
`research/RALPHIE_PRODUCTION_GRADE_STEERING.md` are represented in current
code/tests/docs. The next real build action is credentialed live proof through
the existing live runner once external accounts are available.

## Remaining Risks

- Stripe, Cloudflare, Chutes, Telegram, Discord, and production-host live proof
  are unverified until credentials and accounts are supplied.
- The Python hosted API has not yet been deployed behind a final production
  identity/edge configuration.
- Dedicated Nextcloud per deployment is strong isolation for MVP but may become
  resource-heavy at scale.
- Broad public rebrand from ArcLink to ArcLink must avoid breaking preserved
  ArcLink deploy/runtime contracts.
