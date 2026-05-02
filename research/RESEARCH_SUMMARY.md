# Research Summary

<confidence>96</confidence>

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

Production 1-9 of the 16-item steering checklist are landed and checked:
- P1-2: Hosted API contract with versioned routes, OpenAPI, auth/CSRF/audit.
- P3-6: Stripe, Cloudflare, Docker executor, and Chutes fake boundaries.
- P7: Telegram/Discord onboarding parity with shared state machine.
- P8: User dashboard with responsive layout and mock data.
- P9: Admin dashboard wired to all hosted API admin endpoints (18 tabs).

Production 10-16 remain:
- P10: Web UI brand system, mobile layouts, empty/error/loading states.
- P11: Unified fake E2E journey harness.
- P12: Secret-gated live E2E harness (blocked on credentials).
- P13-15: Deployment assets, observability, data safety.
- P16: Documentation truth pass.

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

BUILD should proceed with Production 10-16. The immediate priority is:
1. P10: Brand system, mobile/responsive checks, empty/error/loading states.
2. P11: Fake E2E full journey harness.
3. P12-16: Live E2E, deploy assets, observability, data safety, docs truth.

All 160 ArcLink tests passing. No live secrets required to continue.

## Remaining Risks

- Live Chutes key lifecycle unverified until account-backed testing.
- Stripe/Cloudflare live paths require real credentials and E2E evidence.
- Telegram/Discord live HTTP transport not yet implemented.
- API/auth boundary is not yet deployed behind production identity provider.
- Dedicated Nextcloud per deployment may become resource-heavy at scale.
- Admin dashboard is wired to API; user dashboard mock data wiring remains.

## Reference Topics For Live Work

Live adapter implementation should verify against official provider docs for
Chutes, Stripe webhooks, Cloudflare Tunnel/Access, Docker Compose secrets,
Traefik Docker labels, Next.js App Router, and Tailwind responsive design.
