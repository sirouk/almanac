# Codebase Map

## Scope

This map covers public repository files relevant to the ArcLink Sovereign audit
remediation. It excludes private state, live credentials, user Hermes homes,
dependency folders, caches, generated logs, and production service state.

## Top-Level Entrypoints

| Path | Role |
| --- | --- |
| `AGENTS.md` | Repository operating guide, canonical command map, safety rules, and deployment posture. |
| `deploy.sh` | Thin wrapper around the canonical deploy menu. Do not run live install/upgrade without explicit authorization. |
| `bin/deploy.sh` | Shared Host install, upgrade, health, deploy-key, enrollment, and repair orchestration. |
| `bin/arclink-docker.sh` | Shared Host Docker and Sovereign Control Node Docker orchestration. |
| `compose.yaml` | Compose service topology, env contracts, network boundaries, and Docker socket mounts. |
| `Dockerfile` | Shared app image for Python, Node, Hermes/qmd support, Docker CLI, and container user policy. |
| `bin/arclink-ctl` | Operator CLI for control DB, onboarding, org profile, and admin operations. |
| `bin/arclink-live-proof` | Credential-gated live proof runner. Blocked unless explicitly authorized. |
| `ralphie.sh` | Ralphie phase orchestration script. |
| `test.sh` | Heavy preflight/install smoke. Use only after focused validation when scope justifies it. |
| `IMPLEMENTATION_PLAN.md` | BUILD handoff plan. |

## Major Directories

| Directory | Responsibility |
| --- | --- |
| `python/` | Control DB, hosted API, auth/session/CSRF, onboarding, provisioning, action worker, executor, fleet, ingress, entitlements, evidence, public bots, Notion/SSOT, memory synthesis, dashboard, diagnostics, and live proof. |
| `tests/` | Focused Python regression tests for public ArcLink code. |
| `bin/` | Deploy, Docker, bootstrap, health, qmd, PDF, backup, service, runtime, and live-proof wrappers. |
| `web/` | Next.js App Router product/admin/onboarding UI, API client, Node tests, and Playwright checks. |
| `plugins/hermes-agent/` | ArcLink-owned Hermes plugins such as managed context, Drive, Code, and Terminal. |
| `hooks/hermes-agent/` | ArcLink Hermes hooks such as Telegram `/start`. |
| `systemd/` | User service and timer templates. |
| `config/` | Runtime pins, provider defaults, environment examples, schemas, and public example configuration. |
| `docs/` | API, Docker, org profile, managed memory, data-safety, and operations documentation. |
| `research/` | Ralphie steering, audit verification, research, coverage, dependency, stack, and completion artifacts. |
| `consensus/` | Phase gate records and current BUILD authorization/blocker notes. |

## Runtime Lanes

| Lane | Shape | Primary files |
| --- | --- | --- |
| Shared Host | Service user, nested private state, systemd units, Curator, qmd, Notion, Nextcloud, and per-user agents | `bin/deploy.sh`, `bin/bootstrap-*.sh`, `bin/install-*-services.sh`, `python/arclink_enrollment_provisioner.py` |
| Shared Host Docker | Compose substrate plus Docker agent supervisor | `compose.yaml`, `Dockerfile`, `bin/arclink-docker.sh`, `python/arclink_docker_agent_supervisor.py` |
| Sovereign Control Node | Hosted API/web, Stripe entitlement, provisioning, action queue, ingress, public bots, fleet, evidence, and admin dashboard | `python/arclink_hosted_api.py`, `python/arclink_api_auth.py`, `python/arclink_provisioning.py`, `python/arclink_action_worker.py`, `python/arclink_sovereign_worker.py` |
| Public Bot Gateways | Telegram/Discord webhook and command handling | `python/arclink_telegram.py`, `python/arclink_discord.py`, `python/arclink_public_bot_commands.py`, `python/arclink_hosted_api.py` |
| Agent Runtime | Hermes homes, plugins, hooks, skills, qmd tools, gateways, and dashboard plugins | `bin/install-agent-user-services.sh`, `bin/install-deployment-hermes-home.sh`, `plugins/hermes-agent/*`, `hooks/hermes-agent/*` |

## Wave 1 Hotspots

| Audit area | Inspect first | Expected authority |
| --- | --- | --- |
| `CR-1` Telegram webhook secret | `python/arclink_hosted_api.py`, `python/arclink_telegram.py`, Telegram/hosted API tests | Webhook registration and inbound request handling require the configured Telegram secret. |
| `CR-2` container user/socket scope | `Dockerfile`, `compose.yaml`, Docker/loopback/deploy tests | App containers run non-root; Docker socket mounts are scoped and justified. |
| `CR-6`, `LOW-1` auth-before-CSRF | `python/arclink_api_auth.py`, `python/arclink_hosted_api.py`, auth/hosted API tests | Session authentication precedes CSRF validation and revocation/mutation. |
| `CR-7` Discord replay/timestamp | `python/arclink_discord.py`, `python/arclink_hosted_api.py`, Discord tests | Timestamp tolerance and interaction idempotency are enforced before dispatch. |
| `CR-8`, `ME-4` body caps and JSON errors | `python/arclink_hosted_api.py`, hosted API tests | Oversized bodies return 413 before parsing; malformed JSON returns canonical 400. |
| `HI-5`, `HI-6` CORS/preflight routing | `python/arclink_hosted_api.py`, hosted API tests | Early errors carry CORS headers and `OPTIONS` requests are route-checked with accurate `Allow`. |
| `CR-9` backend CIDR boundary | `python/arclink_hosted_api.py`, `python/arclink_control.py`, loopback hardening tests | Admin/control/backend routes enforce configured CIDRs or the env contract is removed. |
| `CR-11` peppered token hashes | `python/arclink_api_auth.py`, `python/arclink_control.py`, auth/control DB tests | Session and CSRF hashes use server-side HMAC pepper with compatibility reads where needed. |
| `HI-1`, `ME-12`, `ME-13`, `LOW-8`, `LOW-9` secrets | `python/arclink_secrets_regex.py`, provisioning/executor/evidence/memory/hosted API call sites | Secret detection is centralized and redaction happens before truncation. |
| `HI-4`, `HI-7`, `ME-2`, `ME-3` auth/rate limits | Hosted API/auth/public bot modules and tests | Browser/API credential extraction is split, webhooks are rate-limited, and user-facing auth errors are generic. |

## Later-Wave Hotspots

| Theme | Primary files |
| --- | --- |
| Provider side effects and idempotency: `CR-3`, `CR-10`, `HI-2`, `HI-10`, `HI-11`, `HI-13`, `HI-15`, `HI-16`, `HI-17`, `ME-6` | `python/arclink_executor.py`, `python/arclink_chutes_live.py`, `python/arclink_entitlements.py`, executor/live-runner tests |
| Action worker races/readiness/errors: `CR-5`, `HI-12`, `ME-8`, `ME-16`, `ME-17`, `ME-18`, `LOW-11` | `python/arclink_action_worker.py`, hosted API/admin tests |
| Teardown, DNS, fleet, ports, and secret cleanup: `CR-4`, `HI-8`, `HI-9`, `HI-14`, `ME-7`, `ME-9`, `ME-10`, `LOW-6`, `LOW-7`, `LOW-13` | `python/arclink_sovereign_worker.py`, `python/arclink_executor.py`, `python/arclink_fleet.py`, ingress/provisioning tests |
| Schema, statuses, TTL, identity merge: `HI-3`, `HI-18`, `HI-19`, `HI-20`, `HI-21`, `HI-22`, `HI-23`, `HI-24`, `HI-25`, `ME-26`, `LOW-10`, `LOW-16`, `LOW-17`, `LOW-18`, `LOW-19` | `python/arclink_control.py`, auth/onboarding/control DB tests |
| API/web response shapes and runtime contracts: `ME-1`, `ME-5`, `ME-19`, `ME-20`, `ME-21`, `ME-22`, `LOW-2`, `LOW-3`, `LOW-4`, `LOW-5`, `LOW-14`, `LOW-22`, `LOW-23` | `python/arclink_hosted_api.py`, `web/`, web tests |
| Memory, evidence, and timestamps: `ME-14`, `LOW-12`, `LOW-15` | `python/arclink_memory_synthesizer.py`, `python/arclink_evidence.py`, memory/evidence tests |
| Deploy/qmd/systemd/git/proof hardening: `ME-15`, `ME-23`, `ME-24`, `ME-27`, `ME-28`, `LOW-20`, `LOW-21`, `LOW-24` | `bin/deploy.sh`, qmd scripts, `systemd/`, deploy regression tests |

## Existing Focused Tests

| Surface | Tests |
| --- | --- |
| Hosted API/auth/session/CSRF/CORS | `tests/test_arclink_hosted_api.py`, `tests/test_arclink_api_auth.py` |
| Telegram/Discord webhooks | `tests/test_arclink_telegram.py`, `tests/test_arclink_discord.py` |
| Admin actions and dashboard | `tests/test_arclink_admin_actions.py`, `tests/test_arclink_action_worker.py`, `tests/test_arclink_dashboard.py` |
| Executor/provider boundaries | `tests/test_arclink_executor.py`, `tests/test_arclink_live_runner.py`, Chutes/adapter tests |
| Provisioning/fleet/teardown | `tests/test_arclink_provisioning.py`, `tests/test_arclink_sovereign_worker.py`, `tests/test_arclink_fleet.py`, ingress tests |
| Memory and evidence | `tests/test_memory_synthesizer.py`, `tests/test_arclink_evidence.py` |
| Docker/deploy/runtime hardening | `tests/test_arclink_docker.py`, `tests/test_deploy_regressions.py`, `tests/test_loopback_service_hardening.py`, health tests |
| Web/API client | `web/tests/test_api_client.mjs`, `web/tests/test_page_smoke.mjs`, `web/tests/browser/product-checks.spec.ts` |

## Architecture Assumptions

- Repair ArcLink public code in place; do not patch Hermes core.
- Keep Shared Host, Shared Host Docker, and Sovereign Control Node paths
  distinct.
- Prefer existing helpers, migrations, transaction patterns, and fake-client
  tests over new infrastructure.
- Treat provider, deploy, Docker host, public bot, and production proof flows
  as blocked until explicitly authorized.
- Treat current dirty-tree changes as user-owned and work with them.
