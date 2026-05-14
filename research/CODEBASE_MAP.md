# Codebase Map

## Scope

This map covers public repository areas relevant to the ArcPod Captain Console
mission. It excludes private state, live credentials, user Hermes homes,
dependency folders, caches, logs, and production service state.

## Top-Level Entrypoints

| Path | Role |
| --- | --- |
| `AGENTS.md` | Repository operating guide, canonical commands, safety rules, deployment posture, and vocabulary recap target. |
| `deploy.sh` | Thin wrapper around the canonical deploy menu. Control inventory subcommands should surface through this entrypoint. |
| `bin/deploy.sh` | Shared Host and Control Node install/upgrade/health/control-menu orchestration. Add control inventory menu and argv aliases here. |
| `bin/arclink-docker.sh` | Shared Host Docker and Control Node Docker orchestration. Preserve live mutation gates. |
| `compose.yaml` | Compose service topology and env contracts. Wrapped scheduler/service changes land here if Wave 6 chooses a service. |
| `Dockerfile` | Shared app image for Python, Node, Hermes/qmd support, and Docker CLI. |
| `bin/arclink-ctl` | Operator CLI for control DB, onboarding, org profile, and admin operations. |
| `test.sh` | Heavy preflight/install smoke. Prefer focused tests first. |
| `IMPLEMENTATION_PLAN.md` | BUILD handoff plan for the active ArcPod mission. |

## Major Directories

| Directory | Responsibility |
| --- | --- |
| `python/` | Control DB, hosted API, auth/session/CSRF, onboarding, provisioning, action worker, executor, fleet, ingress, entitlements, evidence, public bots, MCP, Notion/SSOT, memory synthesis, dashboard, diagnostics, and notifications. |
| `tests/` | Focused Python regression tests for control, onboarding, bots, hosted API, auth, provisioning, fleet, Docker, dashboard, MCP, notification, and runtime contracts. |
| `bin/` | Deploy, Docker, bootstrap, health, qmd, PDF, backup, service, runtime, and live-proof wrappers. |
| `web/` | Next.js App Router product, onboarding, dashboard, admin UI, API client, Node tests, and Playwright checks. |
| `plugins/hermes-agent/` | ArcLink-owned Hermes plugins including managed context, Drive, Code, and Terminal. |
| `hooks/hermes-agent/` | ArcLink Hermes hooks, including Telegram `/start`. |
| `templates/` | Rendered operational templates. `templates/SOUL.md.tmpl` is the Wave 0 SOUL overlay target. |
| `systemd/` | User service and timer templates. |
| `config/` | Runtime pins, provider defaults, environment examples, schemas, and public example configuration. |
| `docs/arclink/` | Product, operator, Raven, first-day, control-node, and runbook documentation. Vocabulary canon belongs here. |
| `research/` | Ralphie steering, research, coverage, dependency, stack, and completion artifacts. |
| `consensus/` | Phase gate records and blocked-operation notes. |

## Runtime Lanes

| Lane | Shape | Primary files |
| --- | --- | --- |
| Shared Host | Service user, nested private state, systemd units, Curator, qmd, Notion, Nextcloud, and per-user agents | `bin/deploy.sh`, `bin/bootstrap-*.sh`, `bin/install-*-services.sh`, `python/arclink_enrollment_provisioner.py` |
| Shared Host Docker | Compose substrate plus Docker agent supervisor | `compose.yaml`, `Dockerfile`, `bin/arclink-docker.sh`, `python/arclink_docker_agent_supervisor.py` |
| Sovereign Control Node | Hosted API/web, Stripe entitlement, provisioning, action queue, ingress, public bots, fleet, evidence, and admin dashboard | `python/arclink_hosted_api.py`, `python/arclink_api_auth.py`, `python/arclink_provisioning.py`, `python/arclink_action_worker.py`, `python/arclink_sovereign_worker.py` |
| Public Bot Gateways | Telegram/Discord webhook and command handling for Raven and onboarding | `python/arclink_telegram.py`, `python/arclink_discord.py`, `python/arclink_public_bots.py`, `python/arclink_public_bot_commands.py` |
| Agent Runtime | Hermes homes, plugins, hooks, skills, qmd tools, gateways, and dashboard plugins | `bin/install-agent-user-services.sh`, `bin/install-deployment-hermes-home.sh`, `plugins/hermes-agent/*`, `hooks/hermes-agent/*` |

## Wave Hotspots

| Wave | Main files to inspect/change | Architecture assumptions |
| --- | --- | --- |
| Wave 0 vocabulary/schema/SOUL | `docs/arclink/vocabulary.md`, docs status index if present, `AGENTS.md`, selected `docs/arclink/*.md`, `python/arclink_control.py`, `templates/SOUL.md.tmpl`, schema tests | Captain-facing terms change; backend table/module/env names stay technical. Apply migrations through `ensure_schema`. |
| Wave 1 onboarding identity | `web/src/app/onboarding/page.tsx`, `web/src/lib/api*`, `python/arclink_onboarding.py`, `python/arclink_public_bots.py`, `python/arclink_discord.py`, `python/arclink_public_bot_commands.py`, `python/arclink_api_auth.py`, `python/arclink_hosted_api.py`, provisioning and public bot tests | Agent Name and Agent Title are required inputs; reject secret-shaped material; preserve Captain display-name capture. |
| Wave 2 fleet inventory/ASU | `bin/deploy.sh`, `python/arclink_fleet.py`, `python/arclink_inventory.py`, `python/arclink_asu.py`, `python/arclink_inventory_hetzner.py`, `python/arclink_inventory_linode.py`, dashboard snapshot, deploy/fleet/provider tests | Manual mode works without cloud credentials; Hetzner/Linode fail closed without tokens; `headroom` remains default placement. |
| Wave 3 Pod migration | new `python/arclink_pod_migration.py`, `python/arclink_action_worker.py`, `python/arclink_sovereign_worker.py`, executor/provisioning/fleet modules, migration tests | Migration is idempotent, rollback-safe, and uses existing operation/audit/placement contracts. |
| Wave 4 pod comms | new `python/arclink_pod_comms.py`, `python/arclink_mcp_server.py`, `python/arclink_api_auth.py`, `python/arclink_hosted_api.py`, web dashboard/admin pages, notification tests | Same-Captain Crew comms allowed; cross-Captain comms require share grants; attachments use share projections. |
| Wave 5 Crew Training | new recipe module, `templates/CREW_RECIPE.md.tmpl`, `templates/SOUL.md.tmpl`, managed-context identity overlay path, hosted API, public bots, web dashboard | Writes active Crew Recipe and additive SOUL overlay; memories and sessions are untouched. |
| Wave 6 ArcLink Wrapped | new `python/arclink_wrapped.py`, notification delivery, Compose/job loop, hosted API, dashboard/admin UI, docs | Reports use existing ledgers/outbox, redact secrets, and default to daily with weekly/monthly options. |

## Existing Focused Tests

| Surface | Existing tests to extend |
| --- | --- |
| Schema/control DB | `tests/test_arclink_schema.py`, `tests/test_arclink_control_db.py` |
| Onboarding/provisioning | `tests/test_arclink_onboarding.py`, `tests/test_arclink_provisioning.py`, `tests/test_onboarding_completion_messages.py` |
| Public bots | `tests/test_arclink_public_bots.py`, `tests/test_arclink_telegram.py`, `tests/test_arclink_discord.py` |
| Hosted API/auth/dashboard | `tests/test_arclink_hosted_api.py`, `tests/test_arclink_api_auth.py`, `tests/test_arclink_dashboard.py` |
| Fleet/deploy/Docker | `tests/test_arclink_fleet.py`, `tests/test_deploy_regressions.py`, `tests/test_arclink_docker.py` |
| MCP/plugins | `tests/test_arclink_mcp_schemas.py`, `tests/test_arclink_plugins.py` |
| Notifications | `tests/test_arclink_notification_delivery.py` |
| Web | `web/tests/test_api_client.mjs`, `web/tests/test_page_smoke.mjs`, `web/tests/browser/product-checks.spec.ts` |

## Architecture Assumptions

- Keep Shared Host, Shared Host Docker, and Sovereign Control Node paths distinct.
- Do not patch Hermes core; use ArcLink wrappers, hooks, plugins, generated config, and service units.
- Prefer existing migration helpers, audit helpers, notification outbox, operation idempotency, fleet placement, hosted API/auth, and dashboard patterns.
- Keep cloud providers, public bot command sync, deploys/upgrades, live payment flows, and production proof gated until explicitly authorized.
- Treat public docs as editable only after behavior is implemented or a project-specific deferral is recorded.
