# Research Summary

<confidence>97</confidence>

## Goal

Transform Almanac into ArcLink: a Chutes-first, self-serve, paid,
single-user AI deployment SaaS with website, Telegram, and Discord onboarding;
Stripe entitlement gates; Cloudflare/Traefik host routing; responsive
user/admin dashboards; and preserved Hermes, qmd, vault, managed memory,
Notion, Nextcloud, code-server, bot, and health robustness.

## Finding

ArcLink is a staged evolution of the Almanac Docker/Python/Bash control plane.
The repository contains 17 ArcLink Python modules (7,877 lines), 17 test files
(160 tests passing), a Next.js 15 + Tailwind 4 web app (~1,593 lines), and
comprehensive fake/live adapter boundaries for all external providers.

The non-live checklist is landed for P1-11 and P13-P16. Production 12 is
scaffolded but externally blocked on live credentials:
- P1-2: Hosted API contract with versioned routes, OpenAPI, auth/CSRF/audit.
- P3-6: Stripe, Cloudflare, Docker executor, and Chutes fake boundaries.
- P7: Telegram/Discord onboarding parity with shared state machine.
- P8: User dashboard with hosted-API layout, service links, bot/model/memory
  state, vault status, billing, provisioning, security, support, loading, and
  empty states.
- P9: Admin dashboard wired to all hosted API admin endpoints (18 tabs).
- P10: Browser product proof with Playwright suite (41 tests passing),
  brand system applied, mobile/desktop viewport checks, accessible forms,
  loading/empty/error states, fake-adapter labeling, deterministic API mocks.
- P11: Fake E2E journey harness (6 tests covering full signup-to-admin flow).
- P12: Live E2E scaffold (secret-gated, skips cleanly without credentials).
  Externally blocked until real credentials are supplied.
- P13: Deployment assets (env example, secret checklist, ingress plan, runbook).
- P14: Observability (structured events, alert candidates, admin dashboard).
- P15: Data safety (volume layout, backup plan, teardown safeguards, secret guards).
- P16: Documentation truth pass (all docs audited, no overclaims).

## Implementation Path Comparison

Path A (selected): Evolve Docker/Python Almanac control plane into ArcLink.
Preserves all working surfaces. Keeps tests deterministic and no-secret.

Path B: Separate SaaS shell around Almanac. Viable later but duplicates state
semantics prematurely.

Path C: Kubernetes/Nomad rewrite. Premature for MVP.

## Key Assumptions

- Docker Compose is the first ArcLink provisioning target.
- New commercial state in `arclink_*` tables with stable text IDs.
- `ARCLINK_*` env vars take precedence; blank values treated as unset.
- Unit tests never require live credentials.
- Web, Telegram, and Discord onboarding share one backend session contract.
- Dashboard surfaces consume backend read/action contracts via hosted API.
- Next.js app consumes the hosted Python API; no external Python web framework.

## Build Readiness

P1-11 and P13-P16 are complete for the no-secret ArcLink foundation. The
remaining work is P12 live proof, which is externally blocked until real
Stripe, Cloudflare, Chutes, Telegram, Discord, and host credentials are supplied.

168 ArcLink test functions + 41 browser product checks passing. No live secrets
required for any non-live landed item. The foundation-runbook
(`docs/arclink/foundation-runbook.md`) and professional finish gate in the
steering doc are aligned with the current state.

## Remaining Risks

- Live Chutes key lifecycle unverified until account-backed testing.
- Stripe/Cloudflare live paths require real credentials and E2E evidence.
- Telegram/Discord live HTTP transport not yet implemented.
- API/auth boundary is not yet deployed behind production identity provider.
- Dedicated Nextcloud per deployment may become resource-heavy at scale.

## Reference Topics For Live Work

Live adapter implementation should verify against official provider docs for
Chutes, Stripe webhooks, Cloudflare Tunnel/Access, Docker Compose secrets,
Traefik Docker labels, Next.js App Router, and Tailwind responsive design.
