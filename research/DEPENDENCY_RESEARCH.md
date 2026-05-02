# Dependency Research
<!-- refreshed: 2026-05-02 plan phase -->

## Stack Components

| Component | Repository evidence | Current ArcLink role | Decision |
| --- | --- | --- | --- |
| Python | `python/`, `tests/`, `requirements-dev.txt` | Hosted API, auth, onboarding, entitlements, provider adapters, provisioning, executor, dashboards read models, diagnostics, fleet, rollout, live proof | Keep as primary business/control-plane layer. |
| Bash | `deploy.sh`, `bin/`, `test.sh` | Bootstrap, deploy, health, Docker operations, job wrappers, operator flows | Preserve; wrap rather than rewrite. |
| Docker Compose | `compose.yaml`, Docker health/deploy scripts, executor tests | MVP runtime and per-deployment provisioning target | Keep as first deployment substrate. |
| SQLite | `python/almanac_control.py`, schema tests | Almanac and ArcLink control-plane state | Keep first; maintain Postgres-compatible schema habits. |
| Postgres | `compose.yaml`, pins/config | Nextcloud database today; possible future ArcLink SaaS state | Keep as service dependency; defer SaaS migration. |
| Redis | `compose.yaml`, pins/config | Nextcloud cache today; possible jobs/pubsub/rate-limit layer | Keep as available secondary service. |
| Hermes | runtime pins, plugins, hooks, skills, gateway scripts | Agent runtime, skills, managed context, chat gateways, dashboard/cron behavior | Preserve and expose as a core product strength. |
| qmd | qmd daemon/update scripts, qmd skill, tests | Vault/PDF/Notion retrieval MCP | Preserve. |
| Nextcloud | Compose service, docs/tests | User file/vault surface | Keep with per-deployment isolation for MVP. |
| code-server | pins/config/access tests | Browser IDE surface | Keep with host-per-service routing. |
| Chutes | `config/model-providers.yaml`, `python/arclink_chutes.py` | Primary OpenAI-compatible inference provider | Keep Chutes-first with model catalog/default centralization. |
| Stripe | `python/arclink_adapters.py`, `python/arclink_entitlements.py` | Checkout, subscription mirror, entitlement gate, billing portal/reconciliation | Fake boundary complete; live proof credential-gated. |
| Cloudflare | `python/arclink_ingress.py`, `python/arclink_access.py`, `python/arclink_executor.py` | Hostname reservation, DNS/drift, tunnel/access strategy | Fake/planning boundary complete; live proof credential-gated. |
| Traefik | ingress docs, executor/label rendering tests | Host-per-service HTTP routing plan | Keep; avoid fragile path-prefix routing. |
| Telegram/Discord | `python/arclink_telegram.py`, `python/arclink_discord.py`, public bot tests | Public onboarding channels sharing web onboarding state | Keep fake mode by default; live mode behind token gates. |
| Next.js 15 | `web/package.json`, `web/src/app`, tests | Production web app for public, user, and admin surfaces | Keep; consume Python hosted API. |
| Tailwind 4 | `web/package.json`, `web/src/app/globals.css` | ArcLink brand-aligned UI system | Keep with brand quality gate. |
| Playwright | `web/package.json`, `web/tests/browser` | Browser/mobile product proof | Keep for UI quality gate. |

## Alternatives Compared

| Decision area | Preferred | Alternative | Reasoning |
| --- | --- | --- | --- |
| Product evolution | Add ArcLink modules beside Almanac | Full rename/rewrite first | Additive approach preserves working deploy/runtime behavior. |
| Deployment substrate | Docker Compose | Kubernetes/Nomad | Compose is enough for MVP and is already supported. |
| State database | SQLite-first | Immediate Postgres migration | Existing tests and helpers are SQLite-based; migrate after contracts stabilize. |
| Async jobs | Durable DB-backed state machine first | Redis queue first | Idempotency and audit matter before throughput scaling. |
| Ingress | Host-per-service Traefik/Cloudflare routing | Path prefixes | Nextcloud/code-server and SSH/TUI surfaces should not depend on brittle path prefixes. |
| SSH/TUI | Bastion or Cloudflare Access/Tunnel TCP | Raw SSH through HTTP/Traefik | Raw SSH cannot be safely routed as HTTP by subdomain. |
| Files UI | Dedicated Nextcloud per deployment | Shared multi-tenant Nextcloud | Dedicated instances are simpler and safer for MVP isolation. |
| Inference provider | Chutes-first with BYOK/OAuth lanes retained | Provider-neutral first | Chutes is a product requirement; central config preserves future flexibility. |
| Provider calls in tests | Fake adapters and secret-gated live harness | Always-on live SDK calls | Unit and fake E2E tests must not need secrets or mutate real services. |
| Dashboard | Next.js/Tailwind consuming hosted API | Python templates | The web app exists and can stay UI-only while Python owns contracts. |

## Compatibility Rules

- Prefer `ARCLINK_*` for new product-facing configuration.
- Preserve `ALMANAC_*` aliases where existing deployment or runtime paths need
  migration safety.
- Treat blank env values as unset.
- Store secret values only in private state or live environment; diagnostics and
  tests may report credential names, never credential values.
- Keep commercial records in `arclink_*` tables with stable string IDs and
  explicit indexes.
- Keep JSON payloads portable by validating in helpers rather than assuming
  SQLite JSON extensions.
- Keep public onboarding data separate from deployment credentials.

## External Dependency Boundaries

| Provider | No-secret boundary | Live blocker |
| --- | --- | --- |
| Stripe | Fake checkout/webhook, entitlement mirror, reconciliation, billing portal contract | API keys, webhook secret, product/price IDs. |
| Cloudflare | Fake DNS client, hostname planning, drift/teardown contracts | Zone ID/token and final DNS/tunnel strategy. |
| Chutes | Model catalog helpers, fake key lifecycle, inference smoke contract | Production account/key strategy and per-deployment key proof. |
| Telegram | Fake-mode adapter and shared onboarding state machine | Public bot token and live transport proof. |
| Discord | Fake-mode adapter and shared onboarding state machine | Application credentials, bot token, live transport proof. |
| Docker/host | Dry-run executor, fake runner, readiness checks | Final production host access and deliberate live execution flag. |

## Validation Requirements

- Python contract changes should run focused `tests/test_arclink*.py` files and
  compile touched modules.
- Web changes should run web smoke, lint/type checks, and Playwright browser
  checks when layout or copy changes.
- Executor/provider changes must prove live mutation is disabled by default.
- Docs must not claim live proof until credentialed live evidence exists.
