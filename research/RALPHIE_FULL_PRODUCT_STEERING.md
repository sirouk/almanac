# Ralphie Steering: Full ArcLink Product Surface

Use this as the active steering source after the completed backend foundation.

## Product North Star

ArcLink is a Chutes-first, self-serve, single-user private AI infrastructure
product evolved from Almanac. The product must feel premium, operational,
transparent about its technology, and easy for a non-operator to use.

Users should be able to enter from:

- a website form and workflow,
- a Telegram public onboarding bot conversation,
- a Discord public onboarding bot conversation.

They should eventually receive a private ArcLink deployment with Hermes, qmd,
vault/memory services, Nextcloud/files, code-server, dashboard links, bot
connectivity, and clear skill-growth education. The UI should surface the
technology with confidence: Hermes, qmd, Chutes, memory stubs, vaults, skills,
health, deployments, and access links are product strengths.

## Current State

Already present:

- ArcLink product/config helpers.
- ArcLink schema and helpers in `python/almanac_control.py`.
- Chutes catalog/fake key contracts.
- Stripe entitlement and public onboarding contracts.
- DNS/Traefik/access planning contracts.
- Dry-run provisioning intent.
- User/admin dashboard read models and queued admin action contracts.
- Fail-closed executor and fake Docker/provider/edge/rollback adapters.
- Brand kit and brand system docs.

Not present yet:

- Next.js/Tailwind website and dashboards.
- HTTP API/session/RBAC layer for user/admin surfaces.
- Public Telegram/Discord bot runtime adapters.
- Live Stripe checkout/webhook E2E.
- Live Cloudflare DNS/Tunnel/Access mutation.
- Live Chutes key lifecycle.
- Hetzner host provisioning.
- Real browser/mobile/Playwright validation.

## Active Next Slice

Build the no-secret product surface foundation before live mutations:

1. Add a web/API surface that can run locally without secrets.
2. Add a public website onboarding flow backed by the existing onboarding
   session contract.
3. Add responsive user dashboard views backed by `arclink_dashboard` read
   models.
4. Add responsive admin dashboard views backed by admin read models and queued
   action-intent contracts.
5. Add Telegram and Discord adapter skeletons that use the same onboarding
   session state machine as the website.
6. Add deterministic fixtures and tests for local operation.
7. Keep docs and live-E2E requirements accurate.

Prefer Next.js 15 + Tailwind for the product surface, matching the project
direction, unless repo constraints force a smaller first step. If adding a
frontend package, keep it minimal, scriptable, and testable. Do not make a
marketing-only landing page: the first screen should be the usable ArcLink
experience.

## Brand Requirements

Use `docs/arclink/brand-system.md` and the brand kit. The product should feel
like a premium dark operational control room:

- Jet Black `#080808`, Carbon `#0F0F0E`, Soft White `#E7E6E6`.
- Signal Orange `#FB5005` for primary actions and system energy.
- Blue/green only for state and feedback.
- Avoid generic AI purple/blue gradients, beige themes, or decorative noise.
- Use dense, scannable operational layouts for dashboards.
- Keep mobile views practical: overview, alerts, user search, action queue,
  deployment state, and access links.

## Safety Gates

Do not execute live external mutations in this slice:

- No real Docker Compose host changes.
- No real Cloudflare mutation.
- No real Chutes key creation/rotation/revoke.
- No real Stripe refunds/cancel/portal mutation.
- No real Telegram/Discord send/webhook mutation unless a fake/local adapter is
  explicitly selected.
- No Hetzner provisioning.

Live work must require explicit E2E/operator configuration and should update
`docs/arclink/live-e2e-secrets-needed.md`.

## Required Validation Shape

At minimum, keep existing no-secret checks green:

```bash
python3 tests/test_arclink_product_config.py
python3 tests/test_arclink_schema.py
python3 tests/test_arclink_chutes_and_adapters.py
python3 tests/test_arclink_entitlements.py
python3 tests/test_arclink_onboarding.py
python3 tests/test_arclink_ingress.py
python3 tests/test_arclink_access.py
python3 tests/test_arclink_provisioning.py
python3 tests/test_arclink_admin_actions.py
python3 tests/test_arclink_dashboard.py
python3 tests/test_arclink_executor.py
python3 tests/test_public_repo_hygiene.py
python3 -m py_compile python/almanac_control.py python/arclink_*.py
git diff --check
```

If adding a frontend, also add the repo-appropriate install/build/test commands
and document them in the completion notes. If a dev server can run locally,
verify the key views with browser automation or screenshot checks before
calling the UI complete.

## Credentials Needed For Later Live E2E

Do not block no-secret product-surface work on these, but keep asking for them
when the live phase arrives:

- Cloudflare zone id and DNS-edit token for `arclink.online`.
- Hetzner API token or operator access.
- Stripe test publishable key, secret key, webhook secret, and price id.
- Chutes owner/account key for per-deployment key lifecycle.
- Telegram public onboarding bot token.
- Discord app id/public key/bot token/guild/test channel.
- Optional Notion, Codex, Claude/OAuth details for real user flows.
