# Dependency Research

## Scope

This document uses public dependency manifests, runtime pins, service
definitions, and tests only. It does not assert live account capabilities for
Stripe, Telegram, Discord, Chutes, Notion, Cloudflare, Tailscale, Docker
install/upgrade, or production deploy flows.

PLAN conclusion: ArcLink should be treated as a multi-runtime product platform.
Dependency decisions must preserve the existing Bash, Python, Next.js,
Docker/systemd, Hermes plugin, qmd, Notion/SSOT, and SQLite boundaries instead
of collapsing the project into a single web-app or single-service stack.

## Stack Components

| Component | Evidence | Role | BUILD decision |
| --- | --- | --- | --- |
| Bash | `deploy.sh`, `bin/*.sh`, `test.sh` | Host lifecycle, Docker wrapper, bootstrap, health, qmd/PDF jobs, service installation, upgrades | Keep canonical host mutations in scripts; validate with shell syntax and focused tests. |
| Python 3 | `python/*.py`, `bin/*.py`, `tests/test_*.py` | Control DB, hosted API, auth, onboarding, provisioning, public bots, action worker, MCP, Notion/SSOT, memory, diagnostics, plugin APIs | Primary behavior-fix surface. |
| SQLite | `python/arclink_control.py` and callers | Durable control-plane state for users, deployments, sessions, subscriptions, events, actions, health, shares, pairing, and provisioning | Preserve migrations and DB tests for state transitions. |
| Docker Compose | `compose.yaml`, `Dockerfile`, `bin/arclink-docker.sh` | Shared Host Docker and hosted Control Node substrate | Preserve boundary clarity; do not run install/upgrade without authorization. |
| systemd | `systemd/user/*`, install scripts | Bare-metal user services, timers, and paths | Preserve loopback/default safety, env generation, and service health. |
| Next.js App Router | `web/package.json`, `web/src/app/*` | Hosted website, onboarding, checkout, login, user dashboard, admin dashboard | Repair journey truth in place. |
| React and TypeScript | `web/src/**/*.tsx`, web tests | Browser UI and validation | Preserve existing component and test setup. |
| Tailwind CSS | `web/package.json`, `web/src/app/globals.css` | Web styling system | Keep dashboard UX work inside the current Tailwind setup. |
| Hermes runtime | `config/pins.json`, install/refresh scripts | Agent runtime, gateways, dashboard host, skills, cron | Do not edit Hermes core; use ArcLink plugin/hook/config surfaces. |
| ArcLink Hermes plugins | `plugins/hermes-agent/*` | Managed context, Drive, Code, Terminal | Preserve root containment, secret exclusions, and read-only linked roots. |
| qmd | `config/pins.json`, `bin/qmd-*.sh`, `python/arclink_mcp_server.py` | Retrieval over vault, PDF sidecars, and shared Notion markdown | Preserve loopback/default scope and collection freshness. |
| Notion and SSOT | `python/arclink_notion_*.py`, `python/arclink_ssot_batcher.py`, SSOT skills | Shared Notion indexing and brokered writes | Preserve scoped exact reads and destructive-payload rejection. |
| Memory synthesis | `python/arclink_memory_synthesizer.py`, managed-context plugin | Bounded awareness cards and recall-stub injection | Preserve source scoping, local fallback, trust/conflict metadata, and retrieval guidance. |
| Nextcloud | Compose service and access helpers | Shared file service and possible future sharing adapter | Do not imply cross-user Drive sharing until grants/UI/projection are complete. |
| Stripe | Hosted API, onboarding, entitlement tests | Checkout and entitlement source of record | Use local/fake tests; live checkout/webhook proof requires authorization. |
| Telegram and Discord | `python/arclink_telegram.py`, `python/arclink_discord.py`, public bot engine | Public Raven and private Curator channels | Use adapter tests; live registration/delivery is gated. |
| Chutes | `config/model-providers.yaml`, `python/arclink_chutes.py`, provider auth/provisioning | Default OpenAI-compatible model provider | Keep fail-closed local boundary; live key management and usage proof are gated. |
| Cloudflare and Tailscale | Ingress/provisioning modules, docs, live proof runner | Domain and tailnet routing | Fake/static tests only unless operator authorizes live proof. |
| Playwright | `web/package.json`, `web/tests/browser` | Browser proof for hosted/dashboard flows | Run for touched web surfaces when dependencies and browsers are available. |

## Version And Pin Snapshot

| Lane | Current public signal | Planning note |
| --- | --- | --- |
| Next.js | `web/package.json`: `next` `^15.3.2` | Keep the App Router project. |
| React | `react` and `react-dom` `^19.1.0` | Preserve React 19 assumptions. |
| TypeScript | `typescript` `^5.8.0` | Web validation uses TypeScript and ESLint 9. |
| Tailwind | `tailwindcss` and `@tailwindcss/postcss` `^4.1.0` | Keep current styling pipeline. |
| Playwright | `@playwright/test` `^1.59.1` | Browser proof needs installed browsers. |
| Python validation | `requirements-dev.txt`: `jsonschema`, `PyYAML`, `pyflakes`, `ruff` | Local validation should not require live provider SDKs unless specifically needed. |
| Hermes runtime/docs | `config/pins.json`: pinned `hermes-agent` commit for runtime and docs | Upgrades must go through ArcLink pins and upgrade rails. |
| qmd | `config/pins.json`: `@tobilu/qmd` `2.1.0` | Retrieval semantics are pinned. |
| Node runtime | `config/pins.json`: Node major `22` | Patch selection is resolved by bootstrap tooling. |
| Python runtime | `config/pins.json`: preferred `3.12`, `3.11`; minimum `3.11` | Keep code compatible with Python 3.11+. |
| Nextcloud/Postgres/Redis | Nextcloud `31-apache`, Postgres `16-alpine`, Redis `7-alpine` | Docker health and secrets handling must preserve these service assumptions. |
| Chutes default model | `config/model-providers.yaml`: `moonshotai/Kimi-K2.6-TEE` | Keep pricing/provider copy aligned with model provider config. |

## Alternatives Compared

| Decision area | Preferred path | Alternatives | Reason |
| --- | --- | --- | --- |
| Product repair | Repair current Bash, Python, web, plugin, Compose, and systemd surfaces | New hosted app rewrite; docs-only repair | Current product spans host, agents, qmd, Notion, public bots, and dashboards. |
| Channel linking | Keep `/link-channel` and platform-safe aliases over pairing codes | Account-password login in chat; separate per-channel accounts | Pairing code model exists and avoids chat credential handling. |
| Drive sharing | Living ArcLink grants backed by live linked resources; prefer Nextcloud/WebDAV/OCS where enabled, otherwise keep browser sharing disabled | Copied projections; public Nextcloud links; unmanaged filesystem copies | Operator policy rejects copied snapshots as the completed product promise. |
| Notion setup | Brokered shared-root membership with scoped claims | User OAuth/integration token; page shared to integration/control identity | Operator policy makes shared-root membership canonical; other models remain research/proof-gated alternatives. |
| Chutes credentials | Per-user Chutes credentials; if per-key metering is unproved, use a separate per-user Chutes account/OAuth session | Shared key with attribution; provider disabled until supplied | Operator policy requires an isolated fallback instead of assuming operator-account per-key metering. |
| Memory | Keep ArcLink governed qmd/SSOT recall stubs; document optional conversational-memory siblings | Replace managed context with generic chat memory | ArcLink's product contract is governed knowledge routing, not unconstrained chat capture. |
| Renewal failure | Immediate provider suspension, immediate and daily Raven notices, day-7 account/data-removal warning, and day-14 audited purge queue | Infer purge from billing defaults; keep only dashboard labels | Operator policy now defines the cadence; BUILD must implement it locally before public claims. |
| One-operator mode | Enforce exactly one operator or make multi-admin mechanics internal-only/subordinate to singleton policy | Let docs and code diverge | Operator policy now defines the singleton operator model. |

## External Integration Posture

| Integration | Local-test posture | Live-proof posture |
| --- | --- | --- |
| Stripe | Fake clients and webhook payload tests can prove local entitlement transitions | Live checkout/webhook requires explicit authorization and credentials. |
| Telegram/Discord | Adapter tests can prove command routing, catalogs, channel linking, and copy | Live command registration, webhooks, or delivery proof is gated. |
| Chutes | Fake utilization/key-management tests and fail-closed boundaries can be local | Per-key usage, key creation, rotation, removal, and spend/refuel proof are gated. |
| Notion | Broker, scoped exact reads, SSOT payload validation, indexing tests can be local | Live workspace/page permissions and user OAuth models are gated and partly policy-owned. |
| Cloudflare/Tailscale | Fake clients, static ingress tests, and docs/health assertions can be local | Live domain/tailnet verification is gated. |
| Docker/host deploy | Static Docker, shell, health, and Compose tests can be local | Install/upgrade, production smoke, and restart are gated. |

## Dependency Risks

- Docker services mount trusted host resources in some modes; docs, health, and
  tests must not hide that boundary.
- Web validation needs Node dependencies and Playwright browsers.
- Live provider SDKs or credentials should not become a default local test
  requirement.
- qmd, Hermes, Nextcloud, Postgres, Redis, Node, and Python are pinned or
  version-resolved components; upgrade claims must go through ArcLink rails.
- Chutes Refuel Pod is now an approved product direction, but it still needs
  local SKU/config/provider-budget credit accounting plus live purchase and
  live provider-balance proof before public copy can claim purchasability.
- Private manifests and generated database paths can influence destructive
  operations; BUILD must preserve path validation before reset, unlink, move,
  or cleanup behavior.

## Current Proof And Policy Targets

The dependency stack is sufficiently identified for BUILD. The pre-policy
matrix now has no `partial` or `gap` rows after the 2026-05-08 policy
reclassification pass. BUILD should preserve the local implementation rows and
focus remaining work on proof and policy boundaries:

- Live Stripe checkout/webhook, live Hermes dashboard landing, live Notion
  permission models, live Cloudflare/Tailscale checks, live Chutes key/usage
  operations, and live Refuel Pod purchase/provider-balance proof remain
  proof-gated.
- Scoped agent self-model or peer-awareness cards remain policy-gated.
- Browser right-click Drive/Code share-link creation remains disabled until a
  live ArcLink broker or approved Nextcloud/WebDAV/OCS adapter exists.
- Chutes threshold continuation copy and self-service provider changes remain
  policy-gated.

## Validation Dependencies

Use the narrowest relevant checks during BUILD:

```bash
git diff --check
bash -n deploy.sh bin/*.sh test.sh
python3 -m py_compile <touched python files>
python3 tests/<nearest focused test>.py
```

For web changes:

```bash
cd web
npm test
npm run lint
npm run test:browser
```

Current MCP validation surfaces are `tests/test_arclink_mcp_schemas.py` and
`tests/test_arclink_mcp_http_compat.py` unless BUILD adds a more specific
server suite.
