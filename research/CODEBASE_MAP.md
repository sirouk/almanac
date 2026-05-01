# Codebase Map

## Root Entrypoints

| Path | Role |
| --- | --- |
| `deploy.sh` | Thin operator wrapper around the canonical deploy, upgrade, Docker, health, enrollment, Notion, and maintenance flows. |
| `test.sh` | Full preflight/install smoke entrypoint; heavier than focused no-secret tests. |
| `compose.yaml` | Docker-first Almanac runtime and ArcLink MVP substrate. |
| `Dockerfile` | App image with Python, Node, Docker CLI, qmd, uv, and Hermes runtime setup. |
| `README.md` | Operator-facing architecture and usage documentation. |
| `AGENTS.md` | Operational guardrails for deploy, onboarding, runtime, secrets, and tests. |
| `IMPLEMENTATION_PLAN.md` | ArcLink BUILD handoff plan. |

## Major Directories

| Directory | Role |
| --- | --- |
| `bin/` | Deploy, Docker, health, onboarding, qmd, PDF, Nextcloud, code-server, backup, vault, and runtime scripts. |
| `python/` | Control plane, ArcLink modules, onboarding, MCP server, Notion SSOT, memory synthesis, health, notification delivery, Docker supervisor, and provider logic. |
| `config/` | Env examples, component pins, model providers, schemas, and example manifests. |
| `compose/` | Supplemental Compose assets. |
| `systemd/user/` | Baremetal service-user units retained for existing Almanac installs. |
| `plugins/hermes-agent/` | Hermes plugins, including managed context and bootstrap-token injection. |
| `hooks/hermes-agent/` | Hermes hooks, including Telegram `/start` behavior. |
| `skills/` | Almanac skills for qmd, Notion, SSOT, resources, vaults, first contact, and upgrades. |
| `docs/` | Operator docs, Docker docs, ArcLink foundation docs, brand notes, and live E2E prerequisites. |
| `research/` | Planning, steering, completion, and discovery artifacts. |
| `tests/` | Focused no-secret regression tests for Almanac and ArcLink surfaces. |
| `consensus/` | Gate outputs for plan, build, lint, test, and document blockers. |

## Docker Runtime Shape

Docker mode is the preferred ArcLink MVP path. `compose.yaml` defines the
shared runtime and jobs:

| Service / lane | Role |
| --- | --- |
| `postgres` | Nextcloud database today; future candidate for ArcLink SaaS state. |
| `redis` | Nextcloud cache today; future candidate for jobs, pubsub, and rate limiting. |
| `nextcloud` | File/vault UI. |
| `almanac-mcp` | Almanac/ArcLink control-plane HTTP MCP server. |
| `qmd-mcp` | qmd retrieval daemon. |
| `notion-webhook` | Notion webhook receiver. |
| `vault-watch` | File-change watcher that triggers qmd/PDF/memory maintenance. |
| `agent-supervisor` | Docker-mode reconciler for per-agent services. |
| `ssot-batcher` | Notion SSOT write/event processor. |
| `notification-delivery` | Outbound notification worker. |
| `health-watch` | Periodic health worker. |
| `curator-refresh` | Periodic Curator/operator action worker. |
| `qmd-refresh`, `pdf-ingest`, `memory-synth`, `hermes-docs-sync` | Knowledge and memory maintenance jobs. |
| Optional profiles | Quarto, backup, Curator gateway, and onboarding workers. |

## ArcLink Modules

| Module | Responsibility |
| --- | --- |
| `python/arclink_product.py` | Product config helpers, `ARCLINK_*` precedence, legacy alias fallback, diagnostics, and Chutes defaults. |
| `python/arclink_chutes.py` | Chutes model catalog parsing, capability validation, auth-header helpers, and fake key manager. |
| `python/arclink_adapters.py` | Fake Stripe checkout/webhook helpers, fake Cloudflare DNS client, hostname planning, and Traefik labels. |
| `python/arclink_entitlements.py` | Stripe webhook processing, event idempotency, subscription mirror, entitlement state, and gate advancement. |
| `python/arclink_onboarding.py` | Public web/Telegram/Discord sessions, funnel events, fake checkout, channel handoff, and provisioning readiness. |
| `python/arclink_public_bots.py` | Deterministic public Telegram/Discord onboarding turn handling over the shared session contract. |
| `python/arclink_product_surface.py` | Local stdlib WSGI onboarding, fake checkout, user dashboard, admin dashboard, API, and queued-action prototype. |
| `python/arclink_ingress.py` | Desired DNS records, drift events, and Traefik role label rendering. |
| `python/arclink_access.py` | Dedicated Nextcloud isolation decision and Cloudflare Access TCP SSH guard. |
| `python/arclink_provisioning.py` | Dry-run provisioning intent, state roots, Compose service plan, DNS/Traefik/access intent, health placeholders, job events, and rollback planning. |
| `python/arclink_dashboard.py` | User/admin read models and queued, audited admin action intent contracts. |
| `python/arclink_api_auth.py` | Initial no-secret API/auth boundary with user/admin sessions, CSRF, rate limits, MFA-ready admin factors, scoped reads, and queued admin mutations. |
| `python/arclink_executor.py` | Fail-closed executor request/result types, secret resolver contracts, fake provider behavior, replay guards, DNS validation, and Compose dependency validation. |
| `python/almanac_control.py` | Existing control-plane DB plus ArcLink schema, helpers, audit/events, DNS, service health, provisioning jobs, onboarding tables, and action intents. |

## Foundation Gate Surfaces

The current BUILD handoff begins by confirming these no-secret regression
surfaces before expanding hosted API, frontend, or live-adapter scope:

| File | Contract to preserve |
| --- | --- |
| `python/arclink_api_auth.py` | `start_public_onboarding_api()` must reject unsupported channels before writing rate-limit rows. |
| `python/arclink_api_auth.py` | `revoke_arclink_session()` rejects missing user/admin session ids before mutation or audit, and rejects blank or unknown session kinds before mutation or audit. |
| `python/arclink_dashboard.py` | Admin dashboard security counts exclude expired and revoked user/admin sessions. |
| `python/arclink_product_surface.py` | Generic exception responses use safe copy and avoid rendering raw internal exception details. |
| `python/arclink_public_bots.py` | Public bot turns share onboarding rate-limit protection and the public onboarding session contract. |

## ArcLink Schema

The current ArcLink commercial/control tables are:

- `arclink_users`
- `arclink_webhook_events`
- `arclink_deployments`
- `arclink_subscriptions`
- `arclink_provisioning_jobs`
- `arclink_dns_records`
- `arclink_admins`
- `arclink_user_sessions`
- `arclink_admin_sessions`
- `arclink_admin_roles`
- `arclink_admin_totp_factors`
- `arclink_audit_log`
- `arclink_service_health`
- `arclink_events`
- `arclink_model_catalog`
- `arclink_onboarding_sessions`
- `arclink_onboarding_events`
- `arclink_action_intents`

## Almanac Substrate To Preserve

| Surface | Files |
| --- | --- |
| Control-plane MCP | `python/almanac_mcp_server.py`, `bin/almanac-mcp-server.sh` |
| Onboarding state machine | `python/almanac_onboarding_flow.py` |
| Telegram/Discord Curator workers | `python/almanac_curator_onboarding.py`, `python/almanac_curator_discord_onboarding.py` |
| Enrollment provisioning | `python/almanac_enrollment_provisioner.py`, `bin/almanac-enrollment-provision.sh` |
| Docker agent supervisor | `python/almanac_docker_agent_supervisor.py`, `bin/docker-agent-supervisor.sh` |
| Provider setup | `python/almanac_model_providers.py`, `python/almanac_onboarding_provider_auth.py` |
| Memory synthesis | `python/almanac_memory_synthesizer.py`, `bin/memory-synth.sh` |
| qmd/vault/PDF | `bin/qmd-daemon.sh`, `bin/qmd-refresh.sh`, `bin/vault-watch.sh`, `bin/pdf-ingest.py`, `bin/pdf-ingest.sh` |
| Notion guardrails | `python/almanac_notion_ssot.py`, `python/almanac_notion_webhook.py`, `python/almanac_ssot_batcher.py` |
| Notifications/health | `python/almanac_notification_delivery.py`, `python/almanac_health_watch.py`, `bin/health.sh`, `bin/docker-health.sh` |

## Architecture Assumptions

- Add ArcLink SaaS behavior beside Almanac behavior first; broad rename later.
- Keep ArcLink state in `arclink_*` tables and link to operational state by
  stable IDs.
- Render provisioning intent before executing deployment actions.
- Keep unit tests no-secret through fakes and fixtures.
- Use dedicated per-deployment state roots and dedicated Nextcloud instances
  for the MVP.
- Use host-per-service routing for dashboard, files, code, and Hermes.
- Use Cloudflare Access/Tunnel for SSH/TUI access; reject raw SSH-over-HTTP.
- Build production API/auth before production frontend and live provider
  mutation.
- Build production frontend and live provider mutation only after the
  no-secret API/auth boundary is hardened for hosted use.
