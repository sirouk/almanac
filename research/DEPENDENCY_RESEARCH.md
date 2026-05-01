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
| Telegram/Discord SDK lanes | Onboarding modules/tests | Bot onboarding and agent chat | Preserve; adapt public entrypoints to ArcLink sessions. |
| Notion API | SSOT modules/tests | Optional shared Notion rails | Preserve as guarded optional integration. |
| Node 22 | `Dockerfile`, pins | qmd install, Hermes web build, future dashboard runtime | Keep; add dashboard app later. |
| Chutes | `config/model-providers.yaml`, `python/arclink_chutes.py` | Primary OpenAI-compatible inference lane | Keep Chutes-first; fake key manager until live lifecycle is verified. |
| Stripe | `python/arclink_adapters.py`, `python/arclink_entitlements.py` | Payment, checkout, entitlement gate | Keep fake/no-secret unit surface; add live adapter behind E2E config. |
| Cloudflare + Traefik | `python/arclink_ingress.py`, `python/arclink_access.py`, `python/arclink_executor.py` | DNS, tunnel/access strategy, host routing | Keep host-per-service plan; defer live mutation to executor/E2E slice. |
| Python WSGI stdlib surface | `python/arclink_product_surface.py` | Local no-secret onboarding/dashboard/API prototype | Keep short-term as a contract probe; do not treat as production UI. |
| Python API/auth helpers | `python/arclink_api_auth.py` | Initial no-secret user/admin session, CSRF, rate-limit, MFA-ready, scoped read, and queued mutation boundary | Keep and harden before production frontend or live actions. |
| Next.js + Tailwind | Goals context; no app manifest yet | Future responsive user/admin dashboards | Defer until API/auth/RBAC and action contracts are ready. |

## Repository Signals

| Signal | Finding | Interpretation |
| --- | ---: | --- |
| Python files | 134 | Primary implementation and regression-test surface. |
| Shell scripts | 75 | Operational/deploy substrate remains significant. |
| Markdown files | 63 | Planning, docs, skills, and operating guides are extensive. |
| Compose files | 2 | Docker-first path exists and should be evolved. |
| `requirements-dev.txt` | Present | Python test/dev dependencies are explicit. |
| `package.json` | Absent | No production dashboard app exists yet. |
| Hermes hooks/plugins/skills | Present | Hermes integration is a core product asset. |

## Path Comparison

| Path | Benefits | Costs/Risks | Verdict |
| --- | --- | --- | --- |
| Evolve Docker/Python control plane | Preserves working Hermes/qmd/memory/health/onboarding; keeps no-secret tests practical. | Requires careful compatibility and staged rebrand. | Choose. |
| Python API boundary next | Keeps business logic in the existing tested language and can serve web/bot/dashboard clients. | Initial no-secret helpers exist; hosted production auth, routing, CSRF, rate-limit storage, and RBAC hardening remain. | Continue. |
| Immediate Next.js/Tailwind app | Matches eventual dashboard goal and supports polished UI. | Risk of duplicating auth, billing, provisioning, and admin action logic before API contracts exist. | Defer. |
| Separate SaaS shell around Almanac | Cleaner product boundary later. | Duplicates state, audit, billing, health, and provisioning semantics too early. | Defer. |
| Scheduler-first rewrite | Better long-term scheduling semantics. | Premature complexity; weaker no-secret local loop. | Reject for MVP. |

## Dependency Alternatives

| Decision area | Preferred | Alternative | Reasoning |
| --- | --- | --- | --- |
| ArcLink state DB | SQLite-first helpers with Postgres-compatible shape | Immediate Postgres migration | Existing tests and helpers are SQLite-based; migrate after contracts stabilize. |
| Provisioning jobs | DB-backed state machine first | Redis queue first | Payments/DNS/provisioning need durable idempotency before async scaling. |
| Ingress | Traefik host-per-service routing | Path prefixes through one host | Nextcloud/code-server are safer behind dedicated hosts. |
| Files UI | Dedicated Nextcloud per deployment | Shared Nextcloud | Dedicated instances are heavier but stronger for single-user SaaS isolation. |
| SSH/TUI | Cloudflare Access/Tunnel TCP | Raw SSH over HTTP | HTTP routing cannot honestly provide per-subdomain SSH without a TCP tunnel/access design. |
| Product surface now | Python WSGI prototype over read models | Immediate production frontend | Current priority is no-secret contract proving. |
| Production API/auth | Python API boundary, likely ASGI | Put business logic in frontend route handlers | Keeping contracts in Python avoids duplicating entitlement, provisioning, audit, and executor semantics. The current helper module proves the no-secret contract but is not a hosted service yet. |
| Dashboard frontend later | Next.js/Tailwind | Long-term server-rendered Python templates | Requirements call for responsive user/admin apps; current Python surface should remain replaceable. |
| Chutes key isolation | Per-deployment secret references and eventual live keys | Shared global Chutes key | Per-deployment references align with control/security goals. |
| Live provider execution | Fake adapters plus E2E/live flag | Always-on live SDK calls | Unit tests and local development must remain no-secret and deterministic. |

## Compatibility Rules

- Prefer `ARCLINK_*` for new product-facing configuration.
- Preserve `ALMANAC_*` aliases where migration safety requires them.
- Treat blank ArcLink values as unset.
- Never include secret values in diagnostics, docs, test fixtures, or logs.
- Store JSON payloads as text and validate behavior in helpers rather than
  depending on SQLite JSON1.
- Use stable string IDs and explicit unique indexes for commercial records.
- Keep public onboarding state separate from private deployment bot-token and
  provider-token state.

## Validation Requirements

- The immediate BUILD gate must first repair unsupported public onboarding
  channels so they raise before writing `rate_limits` rows.
- The immediate BUILD gate must rerun the focused dashboard, API/auth, product
  surface, public bot, public hygiene, compile, ruff, and diff checks before
  broader hosted API work resumes.
- The gate must preserve the current session-revocation, active-session-count,
  safe generic error, and public-bot rate-limit contracts.
- No-secret tests must cover product config, schema idempotency, Chutes catalog
  parsing, Stripe webhook idempotency/retry/allowlists/transaction ownership,
  onboarding sessions/checkout, DNS drift, Traefik labels, access strategy,
  provisioning dry-runs, dashboard projections, admin action intents, product
  surface routes, public bot turns, executor replay guards, and public hygiene.
- Product-surface acceptance should include desktop and narrow mobile browser
  smoke for the home, onboarding, user dashboard, and admin dashboard.
- Executor tests must prove live mutation is disabled by default and secrets
  materialize only through resolver contracts.
- Live credentials belong in E2E documentation and local secrets only.
- Chutes, Stripe, Cloudflare, Telegram, Discord, Notion, OAuth, and host
  provisioning behavior must not be marked complete until tested live.
