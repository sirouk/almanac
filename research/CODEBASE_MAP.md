# Codebase Map

## Scope

This map covers public repository files only. Private state, generated runtime
state, user homes, dependency folders, build output, logs, caches, secret
material, and live environment values were not inspected.

## Source Composition

| Signal | Count / evidence | Planning implication |
| --- | ---: | --- |
| Python files | 172 | Main behavior surface for control plane, API, bots, provisioning, knowledge, memory, Chutes, live proof, and plugin APIs. |
| Python regression tests | 101 | Focused tests exist for most high-risk surfaces; add tests near touched behavior. |
| Shell/script entrypoints | 82 | Host lifecycle, Docker, health, service, qmd, PDF, backup, and upgrade behavior are product behavior. |
| Markdown files | 103 | Docs and research artifacts must stay aligned with repaired behavior. |
| systemd unit/timer/path files | 29 | Bare-metal runtime behavior remains supported and must stay in validation scope. |
| Web TypeScript/JavaScript files | 17 | Hosted onboarding, checkout, login, user dashboard, admin dashboard, and browser proof need web validation. |
| Public JSON/YAML files | 22 | Compose, pins, package manifests, OpenAPI/config, and fixtures define runtime assumptions. |

## Root Entrypoints

| Path | Role |
| --- | --- |
| `deploy.sh` | Thin wrapper around the canonical deploy menu and named host flows. |
| `bin/deploy.sh` | Bare-metal install, upgrade, health, enrollment, Notion, deploy-key, repair, and operator menu implementation. |
| `bin/arclink-docker.sh` | Shared Host Docker install, upgrade, reconfigure, reconcile, health, logs, ports, teardown, pins, and smoke orchestration. |
| `compose.yaml` | Shared services, hosted Control Node, recurring jobs, qmd/MCP, Notion webhook, web/API, and agent supervisor topology. |
| `Dockerfile` | Container image for Node, Python, qmd, Docker CLI, pinned Hermes runtime, and built web assets. |
| `bin/arclink-ctl` | Operator CLI for control-plane DB, org profile, onboarding recovery, upgrade checks, and admin operations. |
| `bin/arclink-live-proof` | Credential-gated live proof runner. |
| `test.sh` | Heavy validation wrapper for preflight plus install smoke. |
| `IMPLEMENTATION_PLAN.md` | Active BUILD handoff. |
| `AGENTS.md` | Operating guide and safety constraints for coding agents. |

## Major Directories

| Directory | Responsibility |
| --- | --- |
| `bin/` | Deploy, Docker, bootstrap, service install, health, qmd, PDF, Nextcloud, backups, plugin install, live proof, and runtime wrappers. |
| `python/` | Control DB, hosted API, auth, onboarding, provisioning, public bots, action worker, MCP, Notion/SSOT, memory, diagnostics, fleet, rollout, ingress, and dashboard plugin APIs. |
| `web/` | Next.js App Router site, onboarding, checkout, login, user dashboard, admin dashboard, API client, Node tests, and Playwright tests. |
| `plugins/hermes-agent/` | ArcLink-owned Hermes plugins: managed context, Drive, Code, and Terminal. |
| `hooks/hermes-agent/` | Hermes hooks, including Telegram `/start` handling. |
| `skills/` | ArcLink skills for first contact, qmd/Notion/SSOT, resources, vaults, upgrades, and PDF export. |
| `systemd/` | Bare-metal user service, timer, and path templates. |
| `compose/` | Supplemental Compose assets. |
| `config/` | Pins, model providers, env examples, org-profile examples, and public schemas/examples. |
| `docs/` | Architecture, API, Docker, operations, product, security, and user/operator runbooks. |
| `tests/` | Focused Python regression tests for host lifecycle, Docker, onboarding, hosted API, provisioning, plugins, qmd, Notion, SSOT, memory, docs, and hygiene. |
| `research/` | Ralphie steering, product matrix, stack, dependency, coverage, and handoff artifacts. |
| `consensus/` | Phase gate and build-gate records. |
| `templates/` | Public templates used to seed private state. |

## Runtime Lanes

| Lane | Shape | Primary files |
| --- | --- | --- |
| Shared Host | Service user, private nested state, systemd services, Curator, qmd, Notion, Nextcloud, and per-user agent services | `bin/deploy.sh`, `bin/bootstrap-*.sh`, `bin/install-*-services.sh`, `bin/refresh-agent-install.sh`, `python/arclink_enrollment_provisioner.py`, `systemd/user/*` |
| Shared Host Docker | Compose substrate plus Docker agent supervisor and persistent Docker agent homes | `compose.yaml`, `Dockerfile`, `bin/arclink-docker.sh`, `bin/docker-*.sh`, `python/arclink_docker_agent_supervisor.py` |
| Sovereign Control Node | Hosted web/API, Stripe entitlement, provisioning, action queue, ingress, public bots, fleet, rollout, evidence, and dashboards | `python/arclink_hosted_api.py`, `python/arclink_api_auth.py`, `python/arclink_onboarding.py`, `python/arclink_provisioning.py`, `python/arclink_public_bots.py`, `python/arclink_action_worker.py`, `web/src/*` |
| Agent Runtime | Hermes homes, ArcLink plugins, hooks, skills, managed context, Drive, Code, Terminal, qmd tools, and gateways | `bin/install-agent-user-services.sh`, `bin/install-deployment-hermes-home.sh`, `bin/install-arclink-plugins.sh`, `plugins/hermes-agent/*`, `hooks/hermes-agent/*` |
| Knowledge Rails | qmd vault/PDF/Notion retrieval, SSOT broker, Notion webhook, memory synthesis, and managed recall stubs | `python/arclink_mcp_server.py`, `python/arclink_control.py`, `python/arclink_notion_*.py`, `python/arclink_memory_synthesizer.py`, `bin/qmd-*.sh`, `bin/memory-synth.sh` |

Almanac note: treat Almanac as knowledge-store lineage or planning vocabulary
only. The public product identity remains ArcLink unless a later policy
decision introduces a scoped Almanac label.

## Journey Entrypoints

| Surface | Evidence | Architecture assumption |
| --- | --- | --- |
| Website entry and onboarding | `web/src/app/page.tsx`, `web/src/app/onboarding/page.tsx`, `python/arclink_hosted_api.py` | The browser starts public onboarding and must reflect backend truth. |
| Checkout success/cancel | `web/src/app/checkout/success/page.tsx`, `web/src/app/checkout/cancel/page.tsx`, `python/arclink_onboarding.py` | Completion must be state driven, not just URL driven. |
| User dashboard | `web/src/app/dashboard/page.tsx`, `python/arclink_api_auth.py`, `python/arclink_dashboard.py` | Users may see only their own deployments, health, billing, provider state, links, credentials, channels, and shares. |
| Admin dashboard | `web/src/app/admin/page.tsx`, `python/arclink_api_auth.py`, `python/arclink_dashboard.py` | Admin views must distinguish executable, disabled, pending, failed, dry-run, and proof-gated operations. |
| Telegram public bot | `python/arclink_telegram.py`, `python/arclink_public_bots.py` | Telegram updates are normalized into the shared Raven/public bot engine. |
| Discord public bot | `python/arclink_discord.py`, `python/arclink_public_bots.py` | Discord messages/interactions use the same public bot engine. |
| Private Curator onboarding | `python/arclink_curator_onboarding.py`, `python/arclink_curator_discord_onboarding.py`, `python/arclink_onboarding_flow.py` | Operator-led Shared Host onboarding remains separate from paid public onboarding. |
| Control/provisioning | `python/arclink_provisioning.py`, `python/arclink_sovereign_worker.py`, `python/arclink_executor.py` | Deployment proceeds through modeled entitlement and worker/executor boundaries. |
| Agent dashboard plugins | `plugins/hermes-agent/drive`, `plugins/hermes-agent/code`, `plugins/hermes-agent/terminal` | Plugin roots must stay contained and read-only linked resources must not become writeable or reshareable. |

## Docker Service Map

`compose.yaml` defines services for Postgres, Redis, Nextcloud, ArcLink MCP,
qmd MCP, Notion webhook, control API, control web, control ingress, control
provisioner, vault watch, agent supervisor, SSOT batcher, notification
delivery, health watch, curator refresh, qmd refresh, PDF ingest, memory
synthesis, Hermes docs sync, Quarto render, backup, and Curator gateways.

## Hotspots For BUILD

| Surface | Files to inspect first | Current posture |
| --- | --- | --- |
| Product defaults and pricing | `python/arclink_product.py`, `compose.yaml`, `config/env.example`, `web/src/app/onboarding/page.tsx` | Price and entitlement rows are currently classified `real`; preserve tests when touched. |
| Auth, sessions, dashboard isolation | `python/arclink_api_auth.py`, `python/arclink_hosted_api.py`, `web/src/lib/api.ts`, dashboard pages | High-risk user isolation must be preserved across all user/admin routes. |
| Public Raven bot | `python/arclink_public_bots.py`, `python/arclink_telegram.py`, `python/arclink_discord.py` | Agent inventory, switching, labels, channel linking, upgrade guidance, and per-user/per-channel Raven message-display customization have local coverage; Telegram/Discord platform profile mutation remains outside public claims. |
| Knowledge and memory | `python/arclink_mcp_server.py`, `python/arclink_control.py`, `python/arclink_memory_synthesizer.py`, managed-context plugin | qmd/SSOT/recall stubs are real; shared-root SSOT membership is now canonical; optional conversational-memory sibling boundaries are documented; peer-awareness remains policy-gated. |
| Drive sharing | `python/arclink_api_auth.py`, Drive/Code plugins, dashboard page | Grants, owner approval, read-only `Linked` roots, living projection/revoke cleanup, agent-facing `shares.request`, and browser proof exist; copied snapshots no longer satisfy the product promise, so BUILD must preserve linked resources and keep browser sharing disabled until a live broker or approved Nextcloud/WebDAV/OCS adapter exists. |
| Chutes and billing | `python/arclink_chutes.py`, `python/arclink_entitlements.py`, `python/arclink_api_auth.py` | Local fail-closed boundaries, usage ingestion, Refuel Pod local credits, failed-renewal lifecycle metadata, and per-user Chutes account/OAuth fallback are current local truth; live key management and live utilization remain proof-gated. |
| Chutes live adapter continuation | `python/arclink_chutes.py`, `python/arclink_chutes_live.py`, `python/arclink_chutes_oauth.py` | Official registration assist, personal usage/billing endpoints, API-key CRUD, balance transfer, OAuth scopes, token introspection, and OAuth connect/callback now have secret-reference or fake coverage; live calls require explicit proof flags and secret references. |
| Raven chat scope | `python/arclink_public_bots.py`, `python/arclink_notification_delivery.py`, `python/arclink_telegram.py`, `python/arclink_discord.py`, Raven docs/tests | Current truth is slash-command control plus selected-agent freeform bridging for onboarded users; `notification-delivery` executes the selected deployment's Hermes gateway container and returns the agent reply to the same linked channel. |
| Browser share-link broker | `python/arclink_api_auth.py`, Drive/Code plugins, dashboard page | Existing linked-resource grants are real; browser right-click link creation should stay disabled until an ArcLink broker or approved Nextcloud/WebDAV/OCS adapter is implemented and tested. |
| Live proof orchestration | `python/arclink_live_runner.py`, `python/arclink_evidence.py`, `bin/arclink-live-proof`, docs | Extend provider-specific proof as opt-in, redacted, scratch-account oriented checks; never make live proof a default no-secret validation dependency. |
| Operator setup and ingress | `bin/deploy.sh`, `compose.yaml`, `python/arclink_ingress.py`, docs | Setup choice UX, singleton operator ownership, and Cloudflare/Tailscale fake gates exist; live ingress proof remains gated. |
| Upgrades | `config/pins.json`, `bin/deploy.sh`, `python/arclink_pin_upgrade_check.py`, public bot commands | ArcLink rails are current truth; do not expose direct unmanaged Hermes upgrades. |

## Tests To Reach First

| Surface | Focused tests |
| --- | --- |
| Hosted API, auth, dashboards | `tests/test_arclink_hosted_api.py`, `tests/test_arclink_api_auth.py`, `tests/test_arclink_dashboard.py` |
| Onboarding, checkout, entitlement, provisioning | `tests/test_arclink_onboarding.py`, `tests/test_arclink_onboarding_cancel.py`, `tests/test_arclink_entitlements.py`, `tests/test_arclink_provisioning.py` |
| Raven, Telegram, Discord | `tests/test_arclink_public_bots.py`, `tests/test_arclink_telegram.py`, `tests/test_arclink_discord.py` |
| Drive, Code, Terminal, managed context | `tests/test_arclink_plugins.py`, `tests/test_arclink_agent_user_services.py`, `tests/test_arclink_user_agent_refresh.py` |
| qmd, Notion, SSOT, memory | `tests/test_arclink_mcp_schemas.py`, `tests/test_arclink_mcp_http_compat.py`, `tests/test_arclink_notion_knowledge.py`, `tests/test_notion_ssot.py`, `tests/test_arclink_ssot_batcher.py`, `tests/test_memory_synthesizer.py`, `tests/test_arclink_memory_sync.py` |
| Docker, deploy, health, ingress, actions | `tests/test_arclink_docker.py`, `tests/test_deploy_regressions.py`, `tests/test_health_regressions.py`, `tests/test_arclink_ingress.py`, `tests/test_arclink_action_worker.py` |
| Web | `web/tests/test_api_client.mjs`, `web/tests/test_page_smoke.mjs`, `web/tests/browser/product-checks.spec.ts` |

## Architecture Assumptions

- Public repo code and tests define local truth; live provider behavior is
  proof-gated until authorized.
- Docs must follow repaired behavior, not lead it.
- Shared Host, Shared Host Docker, and Sovereign Control Node should remain
  distinct lanes with aligned contracts.
- ArcLink must use wrappers, plugins, hooks, generated config, service units,
  public bots, hosted API, and dashboards instead of editing Hermes core.
- User isolation is a hard boundary across dashboards, provider state,
  deployment health, billing, channels, shares, Notion, vaults, credentials,
  and agent inventories.
