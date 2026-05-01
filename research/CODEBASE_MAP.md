# Codebase Map

## Root Entrypoints

| Path | Role |
| --- | --- |
| `deploy.sh` | Thin operator wrapper around install, upgrade, health, Docker, Notion, enrollment, and maintenance flows. |
| `init.sh` | Initialization wrapper. |
| `test.sh` | Full preflight/install smoke entrypoint; heavier than focused no-secret tests. |
| `compose.yaml` | Docker-first Almanac runtime and ArcLink MVP substrate. |
| `Dockerfile` | App image with Python, Node, Docker CLI, qmd, uv, and Hermes runtime setup. |
| `AGENTS.md` | Operational guardrails for deploy, onboarding, runtime, secrets, and tests. |
| `README.md` | Current Almanac/ArcLink operator-facing architecture and usage docs. |
| `IMPLEMENTATION_PLAN.md` | ArcLink build handoff plan. |

## Major Directories

| Directory | Role |
| --- | --- |
| `bin/` | Deploy, Docker, health, onboarding, qmd, Nextcloud, code-server, backup, vault, and runtime scripts. |
| `python/` | Control plane, ArcLink modules, onboarding, MCP server, Notion SSOT, memory synthesis, health, notification delivery, Docker supervisor, and provider logic. |
| `config/` | Env examples, model providers, component pins, schemas, and example manifests. |
| `systemd/user/` | Baremetal service-user units retained for legacy/operator installs. |
| `compose/` | Supplemental Compose assets. |
| `plugins/hermes-agent/` | Hermes plugin code, including managed context and bootstrap-token injection. |
| `hooks/hermes-agent/` | Hermes hooks, including Telegram `/start` behavior. |
| `skills/` | Almanac-provided skills for qmd, Notion, SSOT, resources, vaults, first contact, and upgrades. |
| `docs/` | Operator docs plus ArcLink foundation, brand, and live E2E secret documentation. |
| `research/` | Planning, steering, and discovery artifacts. |
| `specs/` | Project contracts and acceptance notes. |
| `tests/` | Focused no-secret regression tests for Almanac and ArcLink surfaces. |
| `consensus/` | Build, lint, plan, test, and document gate outputs when blockers need explicit handoff. |

## Runtime Architecture

Docker mode in `compose.yaml` is the preferred ArcLink MVP substrate.

| Service / Lane | Role |
| --- | --- |
| `postgres` | Nextcloud database today; future candidate for ArcLink SaaS state after contracts stabilize. |
| `redis` | Nextcloud cache today; future candidate for jobs/pubsub/rate limits. |
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

Baremetal/systemd remains important for existing Almanac installs, but ArcLink
SaaS provisioning should target Docker first.

## ArcLink Modules

| Module | Current Responsibility |
| --- | --- |
| `python/arclink_product.py` | Product config helpers, `ARCLINK_*` precedence, legacy alias fallback, conflict diagnostics, Chutes defaults. |
| `python/arclink_chutes.py` | Chutes model catalog parsing, capability validation, direct or bearer auth header support, fake key manager. |
| `python/arclink_adapters.py` | Fake Stripe checkout client, Stripe webhook signing/verification, fake Cloudflare client, hostname planner, Traefik HTTP labels. |
| `python/arclink_entitlements.py` | Stripe webhook processing, event idempotency, subscription mirroring, user entitlement state, entitlement gate advancement, onboarding sync. |
| `python/arclink_onboarding.py` | Public web/Telegram/Discord onboarding sessions, funnel events, deterministic fake checkout, channel handoff, entitlement-gated provisioning readiness. |
| `python/arclink_ingress.py` | Desired DNS records, DNS persistence, Cloudflare drift events, Traefik role label rendering. |
| `python/arclink_access.py` | Dedicated per-deployment Nextcloud isolation decision and Cloudflare Access TCP SSH guard. |
| `python/arclink_provisioning.py` | Dry-run provisioning intent, state roots, Compose service plan, DNS/Traefik/access intent, health placeholders, job events, rollback planning. |
| `python/arclink_dashboard.py` | User/admin read models and queued, audited admin action intent contracts. |
| `python/arclink_executor.py` | Fail-closed executor request/result types, fake/file secret resolver contracts, fake Docker/provider/edge/rollback behavior, replay guards, DNS type validation, and Compose dependency validation. |
| `python/almanac_control.py` | Existing control-plane DB plus ArcLink schema, prefix generation, audit/events, subscriptions, provisioning jobs, onboarding tables, DNS, service health, action intents, and drift checks. |

## ArcLink Schema

`python/almanac_control.py` creates the current SaaS/control tables:

- `arclink_users`
- `arclink_webhook_events`
- `arclink_deployments`
- `arclink_subscriptions`
- `arclink_provisioning_jobs`
- `arclink_dns_records`
- `arclink_admins`
- `arclink_audit_log`
- `arclink_service_health`
- `arclink_events`
- `arclink_model_catalog`
- `arclink_onboarding_sessions`
- `arclink_onboarding_events`
- `arclink_action_intents`

## Current Build Gate State

The entitlement preservation gate is repaired. `upsert_arclink_user()` treats
`entitlement_state=None` as a profile-only update, while inserts without an
explicit entitlement still start at `none`. Normal entitlement mutation belongs
to `set_arclink_user_entitlement()`, signed Stripe webhook processing, or
reasoned admin helpers. `prepare_arclink_onboarding_deployment()` uses the
profile-only path and no longer clears returning entitled users.

The dashboard/admin contract slice is present. User/admin views project
ArcLink-owned rows without secret material, and admin actions queue audited
intent without live provider or host side effects.

The executor boundary is present. `python/arclink_executor.py` defines
fail-closed request/result types for Docker Compose, Cloudflare DNS,
Cloudflare Access, Chutes keys, Stripe actions, and rollback, plus fake and
file-materializing secret resolver contracts. It includes fake adapter
execution for Docker Compose planning/resume, Cloudflare DNS/Access, Chutes
create/rotate/revoke, Stripe action result shapes, and rollback preservation.

Completed executor repairs: fake Docker Compose run state is bound to rendered
`intent_digest`; explicit idempotency-key reuse with changed rendered intent is
rejected after both applied and partial-failure runs; applied Compose replay
does not rematerialize secrets; zero fake failure limits fail closed; rollback
destructive-delete detection is explicit; Cloudflare DNS record types are
allowlisted; fake provider/edge/rollback replay keys are bound to stable
operation digests; Chutes replay is strict; and missing Compose dependencies
are rejected before fake apply.

No live Docker, Cloudflare, Chutes, Stripe, or host mutation is enabled by this
foundation. Future live adapters remain E2E/operator-gated.

## Transaction Assumptions

- Existing `almanac_control.py` helper functions generally commit their own
  writes because they are shared by CLI, tests, and operational scripts.
- BUILD work that needs multi-step atomicity should add explicit no-commit
  paths, transaction-aware wrappers, or private helpers rather than silently
  changing broad helper semantics.
- `process_stripe_webhook()` owns its transaction, uses no-commit helper paths
  for supported Stripe side effects, and rejects caller-owned active
  transactions before starting its own `BEGIN`.

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

## Architecture Assumptions For BUILD

- Add ArcLink SaaS behavior beside Almanac behavior first; broad rename later.
- Keep ArcLink commercial state in `arclink_*` tables and link to existing
  operational rows by stable text ids.
- Render provisioning intent before executing deployment actions, and make
  executor adapters consume that intent instead of re-deriving service
  semantics.
- Keep unit tests no-secret by default through fake clients and fixtures.
- Use dedicated per-deployment state roots and dedicated Nextcloud instances
  for the MVP.
- Use host-per-service routing for dashboard, files, code, and Hermes; avoid
  path-prefix routing for Nextcloud/code-server.
- Use Cloudflare Access/Tunnel for SSH/TUI access; reject raw SSH-over-HTTP.
- Keep dashboard/admin API contracts secret-free; execute actions only through
  future workers that enforce idempotency, audit, and E2E/live flags.
