# Dependency Research

## Current Stack Components

| Component | Evidence | Current role | ArcLink decision |
| --- | --- | --- | --- |
| Python 3.11+ / 3.12 preferred | `config/pins.json`, `python/`, `tests/` | Control plane, workers, adapters, provisioning, local product surface, tests | Keep as the primary implementation layer. |
| Bash | `bin/`, `deploy.sh` | Host/Docker orchestration, health, bootstrap, service repair | Keep for deploy operations; wrap carefully rather than rewrite immediately. |
| Docker Compose | `compose.yaml`, Docker scripts/tests | Container-first runtime and supervisor target | Use as ArcLink MVP provisioning substrate. |
| SQLite | `python/almanac_control.py` | Current control-plane database | Extend for ArcLink now; keep portable for Postgres. |
| Postgres 16 | `compose.yaml`, `config/pins.json` | Nextcloud database today | Keep for Nextcloud; evaluate ArcLink SaaS state migration later. |
| Redis 7 | `compose.yaml`, `config/pins.json` | Nextcloud cache today | Keep; later use for jobs/pubsub/rate limits if needed. |
| Hermes agent | `config/pins.json`, runtime scripts, plugins | Agent runtime, skills, chat gateways, dashboard, cron | Preserve and surface as product value. |
| qmd 2.1.0 | `config/pins.json`, qmd scripts | Retrieval/indexing MCP | Preserve. |
| Nextcloud 31 Apache | `compose.yaml`, pins | File/vault UI | Keep; MVP should use dedicated per-deployment instances. |
| code-server 4.116.0 | Pins, access tests | Browser IDE | Keep and route by host. |
| Telegram/Discord SDK lanes | Runtime adapters (`arclink_telegram.py`, `arclink_discord.py`), adapter tests | Bot onboarding and agent chat with fake-mode dispatch | Adapters landed; add live HTTP transport when tokens present. |
| Notion API | SSOT modules/tests | Optional shared Notion rails | Preserve as guarded optional integration. |
| Node 22 | `Dockerfile`, pins | qmd install, Hermes web build, Next.js dashboard runtime | Keep. |
| Chutes | `config/model-providers.yaml`, `python/arclink_chutes.py` | Primary OpenAI-compatible inference lane | Keep Chutes-first; fake key manager until live lifecycle is verified. |
| Stripe | `python/arclink_adapters.py`, `python/arclink_entitlements.py` | Payment, checkout, entitlement gate | Fake boundary landed (P3); live adapter behind E2E config. |
| Cloudflare + Traefik | `python/arclink_ingress.py`, `python/arclink_access.py`, `python/arclink_executor.py` | DNS, tunnel/access strategy, host routing | Fake boundary landed (P4); defer live mutation to E2E slice. |
| Python WSGI stdlib surface | `python/arclink_product_surface.py` | Local no-secret onboarding/dashboard/API prototype | Keep as contract probe; not production UI. |
| Python API/auth helpers | `python/arclink_api_auth.py` (887 lines) | User/admin session, CSRF, rate-limit, MFA-ready, scoped read, queued mutation boundary | Landed (P1-2). Extend as needed. |
| Hosted WSGI API | `python/arclink_hosted_api.py` (1,078 lines) | Production API boundary with route dispatch, session transport, CORS, OpenAPI | Landed (P1-2). |
| Next.js 15 + Tailwind 4 | `web/package.json`, 9 source files (~1,593 lines), 2 web tests | Production web app: landing, login, onboarding, user/admin dashboards | Wire to hosted API (P8-10). |

## Repository Signals

| Signal | Finding | Interpretation |
| --- | ---: | --- |
| Python files | 142 | Primary implementation and regression-test surface. |
| Shell scripts | 79 | Operational/deploy substrate remains significant. |
| Markdown files | 63+ | Planning, docs, skills, and operating guides are extensive. |
| Compose files | 2 | Docker-first path exists and should be evolved. |
| `requirements-dev.txt` | Present | Python test/dev dependencies are explicit. |
| `web/package.json` | Present | Next.js 15 + Tailwind 4 production web app foundation. |
| Hermes hooks/plugins/skills | Present | Hermes integration is a core product asset. |

## Path Comparison

| Path | Benefits | Costs/Risks | Verdict |
| --- | --- | --- | --- |
| Evolve Docker/Python control plane | Preserves all working surfaces; keeps no-secret tests practical. | Requires careful compatibility and staged rebrand. | Chosen. |
| Python API boundary next | Keeps business logic tested; serves web/bot/dashboard clients. | Hosted production auth/RBAC hardening continues. | Continuing. |
| Next.js/Tailwind app (landed) | Dashboard foundation exists for all views. | Must wire to hosted API; avoid duplicating business logic. | Continuing. |
| Separate SaaS shell | Cleaner product boundary later. | Duplicates semantics prematurely. | Defer. |
| Scheduler-first rewrite | Better scheduling semantics. | Premature complexity. | Reject for MVP. |

## Dependency Alternatives

| Decision area | Preferred | Alternative | Reasoning |
| --- | --- | --- | --- |
| ArcLink state DB | SQLite-first with Postgres-compatible shape | Immediate Postgres migration | Existing tests are SQLite-based; migrate after contracts stabilize. |
| Provisioning jobs | DB-backed state machine first | Redis queue first | Durable idempotency before async scaling. |
| Ingress | Traefik host-per-service routing | Path prefixes | Dedicated hosts safer for Nextcloud/code-server. |
| Files UI | Dedicated Nextcloud per deployment | Shared Nextcloud | Stronger single-user SaaS isolation. |
| SSH/TUI | Cloudflare Access/Tunnel TCP | Raw SSH over HTTP | HTTP cannot provide per-subdomain SSH. |
| Dashboard frontend | Next.js 15 + Tailwind 4 | Python templates | Web app foundation landed; wire to API. |
| Chutes key isolation | Per-deployment secret references | Shared global key | Per-deployment aligns with control/security goals. |
| Live provider execution | Fake adapters plus E2E/live flag | Always-on live SDK calls | Tests must remain no-secret and deterministic. |

## Compatibility Rules

- Prefer `ARCLINK_*` for new product-facing configuration.
- Preserve `ALMANAC_*` aliases where migration safety requires them.
- Treat blank ArcLink values as unset.
- Never include secret values in diagnostics, docs, test fixtures, or logs.
- Store JSON payloads as text and validate in helpers rather than depending on SQLite JSON1.
- Use stable string IDs and explicit unique indexes for commercial records.
- Keep public onboarding state separate from private deployment credentials.

## Validation Requirements

- No-secret tests must cover all contract surfaces.
- Product-surface acceptance should include desktop and narrow mobile browser smoke.
- Executor tests must prove live mutation is disabled by default.
- Live credentials belong in E2E documentation and local secrets only.
- The next BUILD phase targets Production 9-10 (admin dashboard, brand/UI) followed by 11-16.
