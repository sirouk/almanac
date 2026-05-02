# Research Summary

<confidence>95</confidence>

## Goal

Transform Almanac into ArcLink: a Chutes-first, self-serve, paid,
single-user AI deployment SaaS with website, Telegram, and Discord onboarding;
Stripe entitlement gates; Cloudflare/Traefik host routing; responsive
user/admin dashboards; and preserved Hermes, qmd, vault, managed memory,
Notion, Nextcloud, code-server, bot, and health robustness.

## Finding

ArcLink should continue as a staged evolution of the existing Almanac
control plane, not as a rewrite. The repository already contains the substrate
needed for the foundation: Docker Compose, Python control-plane modules, Bash
deploy and health scripts, Hermes/qmd/vault/memory rails, Nextcloud,
code-server, Telegram and Discord onboarding foundations, Notion SSOT, service
health, and focused no-secret tests.

ArcLink-specific foundation code is present in additive modules:

- Product identity and config helpers.
- SaaS schema and helper rows in the existing control-plane database.
- Chutes catalog validation and fake key references.
- Fakeable Stripe, Cloudflare, Traefik, and Chutes adapter contracts.
- Stripe entitlement processing.
- Public web/Telegram/Discord onboarding sessions.
- DNS, ingress, access, provisioning, dashboard, admin-action, executor,
  API/auth, product-surface, and public-bot contracts.

The code is not a live SaaS yet. It records and validates intent, exposes
secret-free read/action contracts, and proves behavior through fake adapters.
It does not yet execute live customer Docker deployments, create live DNS or
Cloudflare Access records, mint live Chutes keys, operate live Stripe checkout
or refunds, host production dashboard sessions, or run production public bot
clients.

## Implementation Path Comparison

Path A: evolve the Docker/Python Almanac control plane into ArcLink.

This is the selected path. It preserves Hermes, qmd, memory, vault, Notion,
Nextcloud, code-server, health, bot, and deployment behavior while keeping unit
tests deterministic and no-secret.

Path B: build a separate SaaS shell and treat Almanac as a black-box
provisioner.

This remains viable later, but it would duplicate billing, audit, health,
provisioning, and state semantics before the backend contract is stable.

Path C: rewrite around Kubernetes or Nomad now.

This is premature for the MVP. Docker Compose plus a clear executor boundary is
the safer path until multi-host scheduling pressure is real.

Path D: build the production dashboard first.

This should wait. The repository needs a production API/auth/RBAC boundary
before a Next.js/Tailwind dashboard can safely own user and admin workflows.

## Key Assumptions

- Docker mode is the first ArcLink provisioning target.
- Baremetal/systemd remains a compatibility and operator lane.
- New commercial state belongs in `arclink_*` tables with stable text IDs.
- `ARCLINK_*` values take precedence over non-empty legacy aliases where both
  exist; blank ArcLink values are treated as unset.
- Unit tests must not require live Stripe, Cloudflare, Chutes, Telegram,
  Discord, Notion, OAuth, or host credentials.
- Public website, Telegram, and Discord onboarding should share one durable
  backend session contract.
- Dashboard and admin surfaces should consume backend read/action contracts,
  not duplicate billing/provisioning logic.
- The local Python WSGI product surface is a prototype and contract probe, not
  the final production dashboard architecture.

## Build Readiness

The plan is ready for BUILD handoff. All previously identified lint repairs
(invalid public onboarding channel, session revocation, active session counts,
safe generic errors, public bot rate limiting) are completed and passing.

Current state:
- 130 ArcLink test functions across 18 test files (+ 1 hygiene test that flags
  "Chutes" in docs context; cosmetic, not blocking).
- 16 ArcLink Python modules (7,094 lines).
- Hosted API boundary exists with route dispatch, session transport, CORS,
  request-ID, safe errors, and Stripe webhook skip.
- Next.js 15 + Tailwind 4 web app foundation with landing page, onboarding,
  login, user dashboard, and admin dashboard views (~1,375 lines across 8
  source files), plus 1 web test file.
- Telegram runtime adapter landed (`arclink_telegram.py`, 219 lines) with
  fake-mode long-polling, update parsing, and shared turn handler dispatch.
- Discord runtime adapter landed (`arclink_discord.py`, 255 lines) with
  fake-mode interaction handling, slash commands, signature verification stub,
  and shared turn handler dispatch.
- Entitlements module at 435 lines with reconciliation drift detection,
  targeted comp, and profile-only upsert preservation.
- API/auth module at 853 lines; hosted API at 667 lines.

BUILD should continue with:

1. Harden the hosted API boundary with remaining contract coverage and
   production deployment config.
2. Wire the Next.js web app to the hosted API for real data flow.
3. Add live HTTP transport to Telegram/Discord adapters when tokens present.
4. Add live-gated Docker/Cloudflare/Stripe/Chutes executor paths.
5. Run live E2E with real credentials when available.

## Remaining Risks

- Live Chutes key lifecycle is unverified until account-backed behavior is
  tested.
- Stripe and Cloudflare live paths require real credentials and E2E evidence.
- Telegram/Discord runtime adapters exist with fake-mode dispatch but live
  HTTP transport is not yet implemented.
- The API/auth slice is a no-secret backend contract, not a hosted production
  identity system.
- Dedicated Nextcloud per deployment is safer for isolation but may become
  resource-heavy.
- A broad Almanac-to-ArcLink rename could destabilize mature paths if attempted
  before execution and API boundaries settle.

## Reference Topics For Live Work

Live adapter implementation should verify current behavior against official
provider documentation for Chutes, Stripe webhooks, Cloudflare Tunnel/Access,
Docker Compose secrets, Traefik Docker labels, Next.js App Router, and Tailwind
responsive design before enabling production mutations.
