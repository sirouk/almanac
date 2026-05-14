# Dependency Research

## Scope

This document records public dependency and runtime signals relevant to the
ArcPod Captain Console mission. It does not assert live account capability for
Stripe, Telegram, Discord, Chutes, Notion, Cloudflare, Tailscale, Hetzner,
Linode, Docker host mutation, or production deploy flows.

## Stack Components

| Component | Evidence | Mission relevance | Decision |
| --- | --- | --- | --- |
| Python 3.11+ | `python/*.py`, `tests/test_*.py`, `requirements-dev.txt`, `config/pins.json` | Control DB, hosted API, auth, onboarding, workers, provisioning, fleet, comms, recipes, Wrapped, bots, MCP | Primary implementation surface. |
| SQLite | `python/arclink_control.py` and callers | Users, deployments, onboarding sessions, placements, share grants, audit, notifications, new mission tables | Use `ensure_schema`, existing migration helpers, constraints, indexes, drift checks, and DB tests. |
| Bash | `deploy.sh`, `bin/*.sh`, `test.sh` | Control inventory menu, Docker config defaults, scheduler wrappers, health checks | Keep canonical scripts; run syntax checks when touched. |
| Docker Compose | `compose.yaml`, `Dockerfile`, Docker tests | Control Node runtime, provider job/scheduler lanes, Wrapped service if added | Static/fake tests locally; no live Docker mutation without authorization. |
| Next.js / React / TypeScript | `web/package.json`, `web/src/*` | Web onboarding, dashboard rename/retitle, Comms Console, Crew Training, Wrapped history | Use existing App Router structure and web tests. |
| Public bot adapters | `python/arclink_public_bots.py`, `python/arclink_telegram.py`, `python/arclink_discord.py` | Agent identity prompts, slash commands, Crew Training, Wrapped frequency | Local parser/signature tests only unless command sync is authorized. |
| Hermes runtime/plugins | `config/pins.json`, `plugins/hermes-agent`, `hooks/hermes-agent` | Managed identity context, SOUL overlay, dashboard plugins | Use ArcLink plugin/hook layer; do not edit Hermes core. |
| qmd and memory synthesis | qmd scripts, `python/arclink_memory_synthesizer.py` | Wrapped inputs and Crew Training unsafe-output guard reuse | Preserve retrieval semantics and prompt-injection boundaries. |
| Notification outbox | `python/arclink_notification_delivery.py`, control DB | Comms delivery and Wrapped reports | Reuse existing delivery rail instead of adding direct bot sends. |
| Stripe/Chutes/Hetzner/Linode | Existing adapters plus current inventory provider modules | Checkout metadata, recipe generation, cloud inventory | Fake/injected clients in tests; fail closed without credentials. |

## Version Snapshot

| Lane | Public signal | Planning note |
| --- | --- | --- |
| Python | `config/pins.json`: preferred `3.12`, `3.11`; minimum `3.11` | New code must remain Python 3.11 compatible. |
| Node | `config/pins.json`: Node major `22`; Docker build uses Node 22 | Preserve current runtime line. |
| Next.js | `web/package.json`: `next` `^15.3.2` | App Router web lane. |
| React | `web/package.json`: `react` and `react-dom` `^19.1.0` | Preserve current UI assumptions. |
| TypeScript | `web/package.json`: `typescript` `^5.8.0` | Needed for web/API client changes. |
| Playwright | `web/package.json`: `@playwright/test` `^1.59.1`; Python dev requirements also include Playwright | Use for browser proof after web behavior changes. |
| qmd | `config/pins.json`: `@tobilu/qmd` `2.1.0` | Keep retrieval semantics stable. |
| Hermes | pinned `hermes-agent` runtime/docs commit | Do not drift runtime/docs or edit core. |
| Service images | Nextcloud 31, Postgres 16, Redis 7, Traefik v3 | Preserve Compose compatibility. |

## Alternatives Compared

| Decision area | Preferred path | Alternatives | Reason |
| --- | --- | --- | --- |
| Mission sequencing | Steering wave order | Security-audit-first or all-at-once | Vocabulary/schema and onboarding are prerequisites for later ArcPod surfaces. |
| Agent identity storage | Add `agent_title` and per-deployment identity fields in SQLite | Store only in metadata JSON or localStorage | Queryable schema supports provisioning, dashboard, bots, audit, and tests. |
| Vocabulary migration | User-facing copy migration with backend technical names preserved | Rename modules/tables/env vars | Avoids breaking operator/runtime contracts while fixing Captain-facing language. |
| Fleet inventory | Extend existing fleet/deploy code with ASU and provider wrappers | New fleet service or external scheduler | Existing placement and deploy scripts already own this boundary. |
| Hetzner/Linode integration | Small fail-closed Python wrappers with fake HTTP tests | Vendor SDKs or live calls in tests | Keeps dependencies small and avoids credential/live mutation requirements. |
| Pod migration | New migration module called by existing action worker/executor boundaries | Manual runbook or direct deploy-script surgery | Needed for idempotency, rollback, audit, and regression coverage. |
| Pod comms | Control DB broker plus MCP tools and notification outbox | Direct agent-to-agent channel messages | Central broker supports share-grant authorization and operator audit. |
| Crew Training recipe generation | Existing provider boundary with deterministic fallback | Hard require live Chutes | Keeps local tests and no-secret BUILD possible. |
| ArcLink Wrapped delivery | Existing notification outbox and dashboard history | Direct bot sends or email service | Reuses delivery, redaction, quiet-hours, and audit rails. |

## External Integration Posture

| Integration | Local-test posture | Live-proof posture |
| --- | --- | --- |
| SQLite control DB | Temporary DBs and migration tests | No private runtime DB reads. |
| Stripe | Mock checkout/metadata tests | Live checkout/webhook/payment proof blocked. |
| Telegram/Discord | Local command parser, webhook signature, and message-shape tests | Webhook registration, command sync, and delivery blocked. |
| Chutes | Fake recipe generation and unsafe-output rejection tests | Live inference/OAuth/key operations blocked. |
| Hetzner/Linode | Fake HTTP clients and missing-token fail-closed tests | Cloud list/provision/delete blocked. |
| Docker/Cloudflare/Tailscale | Static Compose checks, fake runners, local command shims | Host/network mutation blocked. |
| Notion | Local/mock tests for cache and error handling | Workspace mutation blocked. |

## Dependency Risks

- New provider modules must not introduce a heavy dependency chain; `requests` is already available through dev requirements and is sufficient if HTTP is needed.
- Web/API/bot changes must preserve backward compatibility for existing onboarding sessions lacking Agent Name or Agent Title until first contact.
- SOUL overlay logic must remain additive and avoid memory/session rewrites.
- Migration implementation will likely need shell/rsync/executor boundaries that are easy to fake in tests and safe under no-secret constraints.
- Wrapped reports must redact before rendering and must distinguish interesting insight from private narrative that should not appear in Operator views.

## Validation Dependencies

Minimum Wave 0 and Wave 1 validation after relevant edits:

```bash
python3 -m py_compile python/arclink_control.py python/arclink_onboarding.py python/arclink_public_bots.py python/arclink_api_auth.py python/arclink_hosted_api.py
python3 tests/test_arclink_schema.py
python3 tests/test_arclink_control_db.py
python3 tests/test_arclink_onboarding.py
python3 tests/test_arclink_public_bots.py
python3 tests/test_arclink_provisioning.py
python3 tests/test_arclink_hosted_api.py
python3 tests/test_arclink_api_auth.py
cd web && npm test && npm run lint
```

If shell files change:

```bash
bash -n deploy.sh bin/*.sh test.sh
```

If browser-critical web behavior changes:

```bash
cd web && npm run test:browser
```
