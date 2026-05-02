# Codebase Map

## Root Entrypoints

| Path | Role |
| --- | --- |
| `deploy.sh` | Thin operator wrapper around canonical deploy, upgrade, Docker, health, enrollment, Notion, and maintenance flows in `bin/deploy.sh`. |
| `test.sh` | Full preflight/install smoke entrypoint; heavier than focused no-secret tests. |
| `compose.yaml` | Docker-first Almanac runtime and ArcLink MVP substrate (16 services, 4 profiles). |
| `Dockerfile` | App image: node:22-bookworm-slim base with Python 3, Docker CLI, qmd, uv, Hermes runtime, and tini. |
| `init.sh` | Bootstrap/enrollment script for local and remote agent installation. |
| `README.md` | Operator-facing architecture and usage documentation. |
| `AGENTS.md` | Operational guardrails for deploy, onboarding, runtime, secrets, and tests. |
| `IMPLEMENTATION_PLAN.md` | ArcLink next-pass BUILD handoff plan. |
| `requirements-dev.txt` | Dev dependencies: jsonschema, pyflakes, ruff. |

## Major Directories

| Directory | Role |
| --- | --- |
| `bin/` | 78 executables: deploy, Docker, health, onboarding, qmd, PDF, Nextcloud, code-server, backup, vault, CI, and runtime scripts. |
| `python/` | 45 modules: control plane, 13 ArcLink modules, onboarding, MCP server, Notion SSOT, memory synthesis, health, notification delivery, Docker supervisor, provider logic, and CLI. |
| `config/` | Env examples, component pins, model providers, schemas (org-profile, pins), and example manifests. |
| `compose/` | Supplemental Compose assets (nextcloud-compose.yml). |
| `systemd/user/` | Baremetal service-user units retained for existing Almanac installs. |
| `plugins/hermes-agent/` | Hermes plugins including managed context and bootstrap-token injection. |
| `hooks/hermes-agent/` | Hermes hooks including Telegram `/start` behavior. |
| `skills/` | 11 Almanac skills: qmd, Notion, SSOT, resources, vaults, first contact, upgrades, vault reconciler, PDF export. |
| `docs/` | Operator docs, Docker docs, ArcLink foundation docs, brand system, brand kit PDF, and live E2E prerequisites. |
| `research/` | Planning, steering, completion, and discovery artifacts. |
| `tests/` | 85 test files with 495 test functions: no-secret regression tests for Almanac and ArcLink surfaces. |
| `consensus/` | Gate outputs for plan, build, lint, test, and document blockers. |
| `specs/` | Project contract definitions for research and implementation artifacts. |
| `templates/` | Configuration templates. |
| `.github/` | GitHub workflows and issue templates. |

## Docker Runtime Shape

Docker mode is the preferred ArcLink MVP path. `compose.yaml` defines the
shared runtime and jobs:

| Service / lane | Role |
| --- | --- |
| `postgres` | Nextcloud database today; future candidate for ArcLink SaaS state. |
| `redis` | Nextcloud cache today; future candidate for jobs, pubsub, and rate limiting. |
| `nextcloud` | File/vault UI. |
| `almanac-mcp` | Almanac/ArcLink control-plane HTTP MCP server (port 8282). |
| `qmd-mcp` | qmd retrieval daemon (port 8181). |
| `notion-webhook` | Notion webhook receiver (port 8283). |
| `vault-watch` | File-change watcher that triggers qmd/PDF/memory maintenance. |
| `agent-supervisor` | Docker-mode reconciler for per-agent services. |
| `ssot-batcher` | Notion SSOT write/event processor. |
| `notification-delivery` | Outbound notification worker. |
| `health-watch` | Periodic health worker. |
| `curator-refresh` | Periodic Curator/operator action worker. |
| `qmd-refresh`, `pdf-ingest`, `memory-synth`, `hermes-docs-sync` | Knowledge and memory maintenance jobs. |
| Optional profiles | `build` (image build), `quarto` (rendering), `backup` (GitHub backup), `curator` (gateway, onboarding workers). |

## ArcLink Modules (14 files, ~8,300 lines)

| Module | Lines | Responsibility |
| --- | --- | --- |
| `python/arclink_product.py` | 122 | Product config helpers, `ARCLINK_*` precedence, legacy alias fallback, diagnostics, and Chutes defaults. |
| `python/arclink_chutes.py` | 145 | Chutes model catalog parsing, capability validation, auth-header helpers, and fake key manager. |
| `python/arclink_adapters.py` | 143 | Fake Stripe checkout/webhook helpers, fake Cloudflare DNS client, hostname planning, and Traefik labels. |
| `python/arclink_entitlements.py` | 378 | Stripe webhook processing, event idempotency, subscription mirror, entitlement state, and gate advancement. |
| `python/arclink_onboarding.py` | 597 | Public web/Telegram/Discord sessions, funnel events, fake checkout, channel handoff, and provisioning readiness. |
| `python/arclink_public_bots.py` | 192 | Deterministic public Telegram/Discord onboarding turn handling over the shared session contract. |
| `python/arclink_product_surface.py` | 730 | Local stdlib WSGI onboarding, fake checkout, user dashboard, admin dashboard, API, and queued-action prototype. |
| `python/arclink_ingress.py` | 121 | Desired DNS records, drift events, and Traefik role label rendering. |
| `python/arclink_access.py` | 49 | Dedicated Nextcloud isolation decision and Cloudflare Access TCP SSH guard. |
| `python/arclink_provisioning.py` | 695 | Dry-run provisioning intent, state roots, Compose service plan, DNS/Traefik/access intent, health placeholders, job events, and rollback planning. |
| `python/arclink_dashboard.py` | 919 | User/admin read models and queued, audited admin action intent contracts. |
| `python/arclink_api_auth.py` | 706 | Initial no-secret API/auth boundary with user/admin sessions, CSRF, rate limits, MFA-ready admin factors, scoped reads, and queued admin mutations. |
| `python/arclink_executor.py` | 890 | Fail-closed executor request/result types, secret resolver contracts, fake provider behavior, replay guards, DNS validation, and Compose dependency validation. |
| `python/arclink_hosted_api.py` | 522 | Production hosted WSGI API boundary with route dispatch, cookie/header session transport, CORS, request-ID propagation, structured logging, and safe error shaping over existing ArcLink contracts. |

## Core Control Plane

| Module | Lines | Responsibility |
| --- | --- | --- |
| `python/almanac_control.py` | 15,397 | Control-plane DB: schema, helpers, audit/events, DNS, service health, provisioning jobs, onboarding tables, action intents, 18 `arclink_*` tables, and 25 ArcLink-specific functions. |
| `python/almanac_mcp_server.py` | 2,277 | MCP server for tools/resources exposed to Hermes and external clients. |
| `python/almanac_ctl.py` | 2,897 | CLI control interface. |
| `python/almanac_onboarding_flow.py` | 2,440 | Onboarding state machine. |

## Foundation Gate Surfaces

The current BUILD handoff begins by confirming these no-secret regression
surfaces before expanding hosted API, frontend, or live-adapter scope:

| File | Contract to preserve |
| --- | --- |
| `python/arclink_api_auth.py` | `start_public_onboarding_api()` rejects unsupported channels before writing rate-limit rows. |
| `python/arclink_api_auth.py` | `revoke_arclink_session()` rejects missing user/admin session ids before mutation or audit, and rejects blank or unknown session kinds. |
| `python/arclink_dashboard.py` | Admin dashboard security counts exclude expired and revoked user/admin sessions. |
| `python/arclink_product_surface.py` | Generic exception responses use safe copy and avoid rendering raw internal exception details. |
| `python/arclink_public_bots.py` | Public bot turns share onboarding rate-limit protection and the public onboarding session contract. |
| `python/arclink_hosted_api.py` | `route_arclink_hosted_api()` returns safe generic errors for unexpected exceptions, propagates request IDs, and enforces session/CSRF gates on admin mutation routes. |

## ArcLink Schema (18 tables)

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

## ArcLink Test Coverage (15 test files, 57+ test functions)

| Test file | Covered surface |
| --- | --- |
| `tests/test_arclink_product_config.py` | Product defaults, env precedence, blank fallback, legacy compatibility. |
| `tests/test_arclink_schema.py` | ArcLink tables, onboarding tables, prefix reservation/generation, audit/events, subscriptions, service health, provisioning helpers, drift checks. |
| `tests/test_arclink_chutes_and_adapters.py` | Chutes catalog validation, fake key references, fake Stripe sessions/webhooks, fake Cloudflare drift, Traefik labels. |
| `tests/test_arclink_entitlements.py` | Stripe signature rejection, paid gate lift, invoice mapping, replay behavior, allowlists, manual comp, atomic rollback, transaction ownership, entitlement preservation. |
| `tests/test_arclink_onboarding.py` | Public sessions, duplicate prevention, fake checkout, checkout cancellation/expiry, entitlement-gated readiness, channel handoff, secret rejection. |
| `tests/test_arclink_ingress.py` | DNS persistence/drift and Traefik golden labels. |
| `tests/test_arclink_access.py` | Dedicated Nextcloud decision and SSH-over-HTTP rejection. |
| `tests/test_arclink_provisioning.py` | Dry-run service/DNS/access intent, entitlement visibility, no-secret validation, retry after secret repair, rollback planning. |
| `tests/test_arclink_admin_actions.py` | Reason-required queued actions, idempotency, audit rows, secret-safe metadata, no live side effects. |
| `tests/test_arclink_dashboard.py` | User dashboard summary and admin dashboard operational/failure projections. |
| `tests/test_arclink_api_auth.py` | User/admin sessions, token hashing, scoped reads, public onboarding APIs, rate limits, CSRF checks, MFA-ready admin mutations, and secret masking. |
| `tests/test_arclink_executor.py` | Live-gate refusal, secret resolver contracts, fake apply result shape, digest mismatch rejection, provider idempotency, secret-material guards, Compose dependency validation. |
| `tests/test_arclink_product_surface.py` | Local WSGI first screen, fake checkout flow, user/admin dashboard rendering, queued admin actions, no DNS mutation, mobile overflow guards, favicon route. |
| `tests/test_arclink_public_bots.py` | Telegram/Discord public bot conversation-state contract, fake checkout, unsupported channel rejection, metadata secret rejection. |
| `tests/test_arclink_hosted_api.py` | Hosted API route dispatch, public onboarding without session auth, user/admin dashboard auth gates, admin action CSRF enforcement, safe error shapes, request-ID propagation, CORS, session cookies, session revocation, and Stripe webhook skip without secret. |
| `tests/test_public_repo_hygiene.py` | Tracked and untracked text hygiene, binary skip behavior, provider-name context. |

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
- The local Python WSGI product surface is a prototype and contract probe, not
  the production dashboard.
- No external web framework is used yet; the production API boundary will
  require adding one (likely FastAPI or Starlette).
