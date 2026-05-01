# Dependency Research

## Current Stack Components

| Component | Evidence | Current Role | ArcLink Decision |
| --- | --- | --- | --- |
| Python 3.11+ / 3.12 preferred | `config/pins.json`, `python/`, `tests/` | Control plane, workers, adapters, provisioning, tests | Keep as first implementation layer. |
| Bash | `bin/`, `deploy.sh` | Host/Docker orchestration, health, bootstrap, service repair | Keep for deploy operations; wrap rather than rewrite initially. |
| Docker Compose | `compose.yaml`, Docker scripts/tests | Container-first runtime and supervisor target | Use as ArcLink MVP provisioning substrate; keep live execution behind the executor/E2E gate. |
| SQLite | `python/almanac_control.py` | Current control-plane database | Extend for ArcLink now; keep schema portable for Postgres. |
| Postgres 16 | `compose.yaml`, `config/pins.json` | Nextcloud database today | Render per-deployment Nextcloud DB service; evaluate SaaS state migration later. |
| Redis 7 | `compose.yaml`, `config/pins.json` | Nextcloud cache today | Render per-deployment Nextcloud Redis service; later use for jobs/pubsub/rate limiting. |
| Hermes agent | `config/pins.json`, runtime scripts, plugins | Agent runtime, skills, chat gateways, dashboard, cron | Preserve and surface as a product strength. |
| qmd 2.1.0 | `config/pins.json`, qmd scripts | Retrieval/indexing MCP | Preserve. |
| Nextcloud 31 Apache | `compose.yaml`, pins | File/vault UI | Keep with dedicated per-deployment isolation for MVP. |
| code-server 4.116.0 | pins and access tests | Browser IDE | Keep and route by host. |
| Telegram/Discord SDK surfaces | onboarding modules/tests | Bot onboarding and agent lanes | Preserve; adapt public entrypoints to ArcLink sessions. |
| Notion API | SSOT modules/tests | Optional shared Notion rails | Preserve as guarded optional integration. |
| Node 22 | `Dockerfile`, pins | qmd install, Hermes web build, future dashboard runtime | Keep; add Next.js app later. |
| Chutes | `config/model-providers.yaml`, `python/arclink_chutes.py` | Primary OpenAI-compatible inference lane | Keep Chutes-first; use fake key manager until live lifecycle is verified. |
| Stripe | `python/arclink_adapters.py`, `python/arclink_entitlements.py`, `python/arclink_onboarding.py` | Payment, checkout, entitlement gate | Keep fake/no-secret unit surface; live adapter behind E2E config. |
| Cloudflare + Traefik | ingress/adapters/access/provisioning modules | DNS, tunnels/access, host routing | Keep host-per-service plan; live mutation deferred to executor slice. |
| Next.js 15 App Router + Tailwind CSS | Product preference; no manifest yet | Future responsive user/admin dashboards | Defer until executor, API, auth, and RBAC contracts are clearer. |

## Repository Signals

| Signal | Finding | Interpretation |
| --- | ---: | --- |
| Python files | 128 | Primary implementation and test surface. |
| Shell scripts | 79 | Operational/deploy substrate remains significant. |
| systemd units | 29 | Baremetal compatibility is still first-class. |
| Docker/Compose files | 3 | Docker-first path exists and should be evolved. |
| Config manifests | 13 | Pins, provider catalog, schemas, Compose, and env examples are centralized. |
| Hermes hooks/plugins/skills | 21 | Hermes integration is a core product asset, not incidental. |
| `package.json` | 0 | No dashboard app exists yet; Node is runtime/tooling support today. |

## External Source Checks

Official documentation checked during PLAN on 2026-05-01 supports the current
dependency decisions:

| Dependency | Source | Planning Implication |
| --- | --- | --- |
| Chutes | https://docs.chutes.ai/ and https://chutes.ai/ | ArcLink should keep Chutes-first config centralized and avoid claiming live per-deployment key lifecycle until the production account path is verified. |
| Stripe webhooks | https://docs.stripe.com/webhooks/signature and https://docs.stripe.com/webhooks | Verification depends on raw request body, signature header, and endpoint secret; blank secrets must fail closed. |
| Cloudflare Tunnel/Access | https://developers.cloudflare.com/tunnel/ and https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/use-cases/ssh/ | Tunnel and Access support SSH/TCP-style access; SSH should use Cloudflare Access/Tunnel, not HTTP path routing. |
| Traefik Docker labels | https://doc.traefik.io/traefik/reference/routing-configuration/other-providers/docker/ | Docker labels support `Host(...)` rules and explicit service ports, matching ArcLink host-per-service routing. |
| Docker Compose secrets | https://docs.docker.com/reference/compose-file/secrets/ and https://docs.docker.com/engine/swarm/secrets/ | Compose secrets and image-supported `_FILE` environment variables fit the no-plaintext provisioning intent. |
| Next.js App Router | https://nextjs.org/docs/app | Appropriate future dashboard framework, but no dashboard app should start before API/auth/executor contracts are stable enough to avoid throwaway UI. |
| Tailwind responsive design | https://tailwindcss.com/docs/responsive-design | Matches the responsive-dashboard requirement once the dashboard phase begins. |

## Missing Or Deferred Dependencies

| Dependency | Status | Research Decision |
| --- | --- | --- |
| Next.js 15 + Tailwind app | No app exists | Defer until provisioning executor, dashboard API, auth, and RBAC contracts are settled. |
| Stripe live SDK | Fake client and manual verifier exist | Keep fake unit surface; add official SDK/live adapter only behind explicit E2E config. |
| Cloudflare live SDK/API adapter | Fake DNS client exists | Keep fake unit surface; implement live adapter after token/zone E2E is available. |
| Traefik runtime integration | Label rendering exists | Add local Compose smoke before live customer execution. |
| Chutes owner key lifecycle | Fake key manager exists | Do not claim key create/revoke until account-backed API behavior is verified. |
| Secret resolver | Fake and file-materializing resolver contracts exist in `python/arclink_executor.py` | Complete replay and validation repairs before adding a production secret backend. |
| Prometheus/Loki/Grafana | Not present | Optional later for fleet observability; current service-health tables are enough for MVP control contracts. |
| Kubernetes/Nomad | Not present | Defer until Docker node density or multi-host scheduling becomes the bottleneck. |

## Implementation Path Comparison

| Path | Description | Benefits | Costs/Risks | Verdict |
| --- | --- | --- | --- | --- |
| A. Evolve Docker/Python control plane | Add ArcLink SaaS tables, provisioning renderer, adapters, onboarding/session contracts, read models, executor boundaries, and dashboards around current Docker mode. | Preserves working Hermes/qmd/memory/health/onboarding and focused tests. | Requires careful compatibility and staged rebrand. | Choose. |
| B. New SaaS shell around Almanac | Build clean web/API app and call Almanac as a provisioner. | Cleaner product boundary later. | Duplicates state, audit, health, billing, and provisioning too early. | Defer. |
| C. Scheduler-first rewrite | Move to Kubernetes/Nomad immediately. | Better long-term scheduling semantics. | Premature complexity; weaker local no-secret loop. | Reject for MVP. |

## Dependency Alternatives

| Decision Area | Preferred | Alternative | Reasoning |
| --- | --- | --- | --- |
| ArcLink state DB | SQLite-first helpers with Postgres-compatible shape | Immediate Postgres migration | Existing tests and helpers are SQLite-based; schema can migrate after contracts stabilize. |
| Provisioning jobs | DB-backed state machine first, Redis queue later | Cron-only polling | Payments/DNS/provisioning need durable idempotency before async scaling; executor replay semantics must be unambiguous first. |
| Ingress | Traefik host-per-service routing | Path prefixes through one host | Nextcloud/code-server are safer and simpler behind dedicated hosts. |
| Files UI | Dedicated Nextcloud per deployment | Shared Nextcloud | Dedicated instances are heavier but stronger for single-user SaaS isolation. |
| SSH/TUI | Cloudflare Access/Tunnel TCP | Raw SSH over HTTP | HTTP routing cannot honestly provide per-subdomain SSH without a real TCP tunnel/access design. |
| Dashboard frontend | Next.js 15 + Tailwind after backend contracts | Server-rendered Python templates now | Requirements call for responsive user/admin apps; current backend contracts should feed a future app. |
| Chutes key isolation | Per-deployment secret reference and eventual live key | Shared global Chutes key | Per-deployment references align with control/security goals; live API needs verification. |
| Live provider execution | Fake adapters plus E2E/live flag | Always-on live SDK calls | Unit tests and local development must remain no-secret and deterministic. |

## Compatibility Rules

- Prefer `ARCLINK_*` for new product-facing configuration.
- Preserve `ALMANAC_*` aliases where migration safety requires them.
- Treat blank `ARCLINK_*` values as unset.
- Never include secret values in diagnostics, docs, test fixtures, or logs.
- Store JSON payloads as text and validate behavior in helpers rather than
  relying on SQLite JSON1.
- Use stable string IDs and explicit unique indexes for new commercial records.
- Keep public onboarding state separate from private deployment bot-token and
  provider-token state.

## Validation Requirements

- No-secret tests must cover product config, schema idempotency, Chutes catalog
  parsing, Stripe webhook idempotency/retry/allowlists/transaction ownership,
  public onboarding sessions/checkout, DNS drift, Traefik labels, access
  strategy, provisioning dry-runs, dashboard projections, and admin action
  intent.
- Executor tests should prove live mutation is disabled by default, secrets
  materialize only through resolver contracts, fake adapters receive the exact
  Docker, Cloudflare, Chutes, Stripe, and rollback calls expected from
  rendered intent, explicit Docker idempotency-key reuse cannot mask a changed
  intent digest, applied replays do not rematerialize secrets, fake failure
  limits are deterministic, rollback delete detection is explicit, and DNS
  record types are allowlisted.
- Live credentials belong in E2E documentation and local secrets only.
- Chutes, Stripe, Cloudflare, Telegram, Discord, Notion, and host provisioning
  live behavior must not be marked complete until exercised with real
  credentials.
- Any provisioning executor must prove it preserves Hermes, qmd, memory, vault,
  Nextcloud, code-server, bot gateway, health, managed context, and
  notification services.
