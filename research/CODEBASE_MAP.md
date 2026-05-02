# Codebase Map
<!-- refreshed: 2026-05-02 plan phase -->

## Root Entrypoints

| Path | Role |
| --- | --- |
| `deploy.sh` | Thin wrapper around canonical deploy, install, upgrade, Docker, health, enrollment, Notion, and maintenance flows in `bin/deploy.sh`. |
| `ralphie.sh` | Ralphie phase runner entrypoint. |
| `test.sh` | Full preflight/install smoke; heavier than focused no-secret tests. |
| `compose.yaml` | Docker-first ArcLink/ArcLink runtime substrate. |
| `Dockerfile` | Application image with Python, Node, Docker CLI, qmd, Hermes runtime, and supporting tools. |
| `init.sh` | Local/remote bootstrap and enrollment helper. |
| `README.md` | Operator-facing product and architecture documentation. |
| `AGENTS.md` | Coding-agent and operations guardrails. |
| `IMPLEMENTATION_PLAN.md` | Current BUILD handoff plan. |

## Major Directories

| Directory | Role |
| --- | --- |
| `bin/` | Deploy, Docker, health, onboarding, qmd, PDF, Nextcloud, code-server, backup, vault, CI, runtime, and ArcLink live-proof scripts. |
| `python/` | ArcLink control plane plus ArcLink product/API/provider/provisioning/executor/fleet modules. |
| `tests/` | ArcLink and ArcLink no-secret regression tests, fake E2E, live-gated E2E scaffolds, and helpers. |
| `web/` | Next.js 15 + Tailwind 4 app with public, onboarding, user dashboard, admin dashboard, API client, and web tests. |
| `config/` | Env examples, model providers, pins, org-profile schemas/examples, and sample private manifests. |
| `docs/` | Operator docs, ArcLink architecture/runbooks/brand/data-safety/live-proof docs, and OpenAPI spec. |
| `research/` | Ralphie planning, steering, coverage, stack, and completion artifacts. |
| `consensus/` | Plan/build/lint/test/document gate outputs and blocker notes. |
| `systemd/user/` | Baremetal service-user units retained for ArcLink compatibility. |
| `plugins/hermes-agent/` | Hermes plugins including managed context/bootstrap-token injection. |
| `hooks/hermes-agent/` | Hermes hooks including Telegram `/start` behavior. |
| `skills/` | ArcLink-facing skills for qmd, vault, Notion, SSOT, resources, upgrades, first contact, and PDF export. |
| `compose/` | Supplemental Compose assets. |
| `templates/` | Public templates used to seed private state. |
| `specs/` | Project contract definitions. |

## Docker Runtime Shape

`compose.yaml` keeps the existing ArcLink shared runtime and is the preferred
ArcLink MVP substrate. Key lanes are:

| Lane | Services / files | Responsibility |
| --- | --- | --- |
| Data/cache | `postgres`, `redis` | Nextcloud database/cache now; future scale dependencies. |
| Files | `nextcloud` | User vault/files surface. |
| Control APIs | `arclink-mcp`, `notion-webhook`, qmd service | MCP, Notion webhook, and retrieval endpoints. |
| Agent/runtime | `agent-supervisor`, Curator profile services | Docker-mode user-agent reconciliation and chat gateways. |
| Knowledge jobs | `qmd-refresh`, `pdf-ingest`, `memory-synth`, `hermes-docs-sync`, `vault-watch` | qmd/PDF/memory/docs maintenance. |
| Operations jobs | `health-watch`, `curator-refresh`, `ssot-batcher`, `notification-delivery` | Health, operator actions, SSOT, notification delivery. |

## ArcLink Python Modules

| Module group | Files | Responsibility |
| --- | --- | --- |
| Product/config | `arclink_product.py`, `arclink_chutes.py` | Product env precedence, Chutes defaults/catalog/key abstractions. |
| Provider boundaries | `arclink_adapters.py`, `arclink_ingress.py`, `arclink_access.py` | Stripe/Cloudflare fakes, DNS/Traefik intent, SSH/TUI routing guardrails. |
| Commercial state | `arclink_entitlements.py`, `arclink_onboarding.py` | Stripe entitlement mirror, paid gate, public onboarding sessions and events. |
| API/auth | `arclink_api_auth.py`, `arclink_hosted_api.py`, `arclink_boundary.py` | Sessions, CSRF, rate limits, route dispatch, OpenAPI, safe errors, webhooks. |
| Dashboards | `arclink_dashboard.py`, `arclink_product_surface.py` | User/admin read models, local WSGI prototype, operator snapshots. |
| Provisioning/executor | `arclink_provisioning.py`, `arclink_executor.py` | Dry-run deployment intent, Compose planning, fake/live-gated execution. |
| Operations spine | `arclink_fleet.py`, `arclink_action_worker.py`, `arclink_rollout.py` | Fleet registry, placement, queued action execution, rollout/rollback records. |
| Live proof | `arclink_host_readiness.py`, `arclink_diagnostics.py`, `arclink_live_journey.py`, `arclink_evidence.py`, `arclink_live_runner.py` | Host readiness, provider diagnostics, ordered live journey, redacted evidence, CLI runner. |
| Bots | `arclink_public_bots.py`, `arclink_telegram.py`, `arclink_discord.py` | Shared onboarding state machine and fake/live bot adapters. |

## Web App

| File | Role |
| --- | --- |
| `web/src/app/page.tsx` | Public ArcLink landing route. |
| `web/src/app/login/page.tsx` | Login/session entry route. |
| `web/src/app/onboarding/page.tsx` | Web onboarding workflow. |
| `web/src/app/dashboard/page.tsx` | User dashboard route. |
| `web/src/app/admin/page.tsx` | Admin/operator dashboard route. |
| `web/src/app/layout.tsx` | Root metadata/layout. |
| `web/src/app/globals.css` | Tailwind 4 import and ArcLink design tokens. |
| `web/src/components/ui.tsx` | Shared UI primitives. |
| `web/src/lib/api.ts` | Hosted API client. |
| `web/tests/` | Node smoke/API tests and Playwright product checks. |

## Core ArcLink Substrate To Preserve

| Surface | Files |
| --- | --- |
| Control-plane DB/MCP | `python/arclink_control.py`, `python/arclink_mcp_server.py`, `bin/arclink-mcp-server.sh` |
| Onboarding/enrollment | `python/arclink_onboarding_flow.py`, `python/arclink_enrollment_provisioner.py`, Curator onboarding modules, enrollment scripts |
| Docker agent supervisor | `python/arclink_docker_agent_supervisor.py`, `bin/docker-agent-supervisor.sh` |
| Provider setup | `python/arclink_model_providers.py`, `python/arclink_onboarding_provider_auth.py` |
| qmd/vault/PDF/memory | `bin/qmd-daemon.sh`, `bin/qmd-refresh.sh`, `bin/vault-watch.sh`, `bin/pdf-ingest.py`, `python/arclink_memory_synthesizer.py` |
| Notion/SSOT | `python/arclink_notion_ssot.py`, `python/arclink_notion_webhook.py`, `python/arclink_ssot_batcher.py` |
| Health/notifications | `python/arclink_health_watch.py`, `python/arclink_notification_delivery.py`, `bin/health.sh`, Docker health scripts |

## Architecture Assumptions

- ArcLink behavior is additive beside ArcLink until live proof and compatibility
  are stable.
- Commercial state lives in `arclink_*` tables and references operational state
  by stable IDs.
- Provisioning must render deterministic intent before executing live actions.
- Fake adapters are default; live provider mutations require explicit live
  flags and credentials.
- Host-per-service routing is the accepted ingress model for Nextcloud,
  code-server, Hermes, dashboards, and support surfaces.
- Raw SSH is not routed through HTTP; use a bastion or Cloudflare Access/Tunnel
  TCP strategy.
- The Python hosted API owns business contracts; the Next.js app owns
  presentation and dashboard workflows.
- Unit tests and fake E2E tests must not require live secrets.
