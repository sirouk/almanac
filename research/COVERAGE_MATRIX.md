# Coverage Matrix: ArcLink User Journey And Gap Atlas

This matrix is the audit/source map for root `USER_JOURNEY.md` and `GAPS.md`.
It preserves every journey joint, maps each joint to source areas and local
proof anchors, and points to canonical gap/proof IDs. It does not own taxonomy,
severity, policy questions, or proof-gate definitions; those live in `GAPS.md`.

ID conventions:

- `J-##`: journey joint in this matrix.
- `GAP-###`: finding in `GAPS.md`.
- `PG-*`: proof gate in `GAPS.md`.

## Surface Matrix

| ID | Journey joint | Source areas to audit | Local proof anchors | Atlas section | Gap/proof IDs |
| --- | --- | --- | --- | --- | --- |
| `J-01` | Public website, returning visitor, mobile/desktop entry | `web/src/app/page.tsx`, `web/src/components/marketing/**`, `web/src/app/layout.tsx`, `README.md`, brand/docs surfaces | `web/tests/test_page_smoke.mjs`, `web/tests/browser/product-checks.spec.ts`, `tests/test_arclink_product_config.py` | Public Entry | `GAP-001`, `GAP-010`, `PG-PROD`, `PG-BOTS` |
| `J-02` | Web onboarding, answers, plan choice, checkout open/cancel/success | `web/src/app/onboarding/page.tsx`, checkout pages, `web/src/lib/api.ts`, `python/arclink_hosted_api.py`, `python/arclink_api_auth.py`, `python/arclink_onboarding.py` | `tests/test_arclink_hosted_api.py`, `tests/test_arclink_onboarding.py`, `tests/test_arclink_onboarding_cancel.py`, web smoke/browser tests | Public Entry, Recovery Atlas | `GAP-001`, `GAP-008`, `GAP-009`, `GAP-010`, `PG-STRIPE` |
| `J-03` | Raven first contact and public Telegram/Discord onboarding | `python/arclink_public_bots.py`, `python/arclink_telegram.py`, `python/arclink_discord.py`, `docs/arclink/raven-public-bot.md`, public onboarding steering | `tests/test_arclink_public_bots.py`, `tests/test_arclink_public_bot_commands.py`, `tests/test_arclink_telegram.py`, `tests/test_arclink_discord.py`, `tests/test_arclink_first_contact.py` | Public Entry, Raven Onboarding And Control | `GAP-001`, `GAP-003`, `GAP-010`, `GAP-013`, `GAP-023`, `GAP-025`, `PG-BOTS` |
| `J-04` | Channel linking, selected Agent, public-agent chat, command conflicts | `python/arclink_public_bots.py`, `python/arclink_public_bot_commands.py`, `python/arclink_notification_delivery.py`, Telegram/Discord adapters, `AGENTS.md` command namespace guidance | Public bot, Telegram, Discord, notification-delivery, hosted API tests | Raven Onboarding And Control | `GAP-003`, `GAP-023`, `PG-BOTS` |
| `J-05` | Plans, pricing, Limited 100 Founders, Sovereign, Scale, additional Agents | `python/arclink_product.py`, `config/model-providers.yaml`, `web/src/components/marketing/marketing-home.tsx`, onboarding/web/API code, product config tests | `tests/test_arclink_product_config.py`, web smoke/browser tests, onboarding tests | Public Entry, Billing | `GAP-002`, `GAP-012`, `PG-STRIPE` |
| `J-06` | Stripe entitlement gate, checkout, renewal, suspension, purge warnings | `python/arclink_entitlements.py`, `python/arclink_chutes.py`, `python/arclink_hosted_api.py`, `python/arclink_api_auth.py`, Stripe runbooks | `tests/test_arclink_entitlements.py`, `tests/test_arclink_hosted_api.py`, `tests/test_arclink_chutes_and_adapters.py` | Billing, Recovery Atlas | `GAP-001`, `GAP-002`, `PG-STRIPE` |
| `J-07` | Refuel credits and provider continuation near threshold | `python/arclink_entitlements.py`, `python/arclink_chutes.py`, `python/arclink_chutes_live.py`, `python/arclink_api_auth.py`, dashboard/provider UI | Entitlements, hosted API, Chutes adapter, browser provider-state tests | Billing | `GAP-002`, `GAP-006`, `PG-STRIPE`, `PG-PROVIDER` |
| `J-08` | Provider/model choice, Chutes, OAuth, LLM router | `config/model-providers.yaml`, `python/arclink_model_providers.py`, `python/arclink_chutes*.py`, `python/arclink_llm_router.py`, `docs/arclink/llm-router.md` | `tests/test_model_providers.py`, `tests/test_arclink_chutes_and_adapters.py`, `tests/test_arclink_chutes_oauth.py`, `tests/test_arclink_llm_router.py` | Billing, Hermes And Agents | `GAP-006`, `GAP-022`, `GAP-024`, `PG-PROVIDER` |
| `J-09` | Entitlement-to-provisioning transition and ArcPod apply | `python/arclink_provisioning.py`, `python/arclink_sovereign_worker.py`, `python/arclink_executor.py`, `compose.yaml`, Control Node docs | `tests/test_arclink_provisioning.py`, `tests/test_arclink_sovereign_worker.py`, `tests/test_arclink_executor.py`, `tests/test_arclink_e2e_fake.py` | Provisioning And Deployment, Recovery Atlas | `GAP-001`, `GAP-004`, `GAP-018`, `PG-PROVISION` |
| `J-10` | Fleet placement, ASU, single-machine, remote fleet, Hetzner, Linode | `python/arclink_fleet.py`, `python/arclink_fleet_inventory_worker.py`, inventory provider modules, `bin/deploy.sh`, fleet runbook | `tests/test_arclink_fleet.py`, `tests/test_arclink_fleet_inventory_worker.py`, `tests/test_arclink_inventory*.py`, `tests/test_arclink_asu.py` | Provisioning And Deployment | `GAP-004`, `GAP-017`, `GAP-021`, `PG-FLEET` |
| `J-11` | Ingress: domain, DNS, Traefik, Cloudflare, Tailscale | `python/arclink_ingress.py`, `python/arclink_provisioning.py`, `compose.yaml`, `docs/arclink/ingress-plan.md`, operations runbook | `tests/test_arclink_ingress.py`, `tests/fixtures/arclink_traefik_labels.golden.json`, Chutes adapter ingress tests | Provisioning And Deployment | `GAP-004`, `GAP-018`, `PG-INGRESS` |
| `J-12` | Credential handoff, one-time reveal boundary, ack/hide/reissue | `python/arclink_api_auth.py`, `python/arclink_sovereign_worker.py`, `web/src/app/dashboard/page.tsx`, first-day/security docs | `tests/test_arclink_hosted_api.py`, `tests/test_arclink_sovereign_worker.py`, browser credential tests, secret regex tests | Credential Handoff, Recovery Atlas | `PG-PROD` |
| `J-13` | User dashboard account, deployments, health, provider, billing, recovery | `python/arclink_dashboard.py`, `python/arclink_api_auth.py`, `python/arclink_hosted_api.py`, `web/src/app/dashboard/page.tsx` | `tests/test_arclink_dashboard.py`, `tests/test_arclink_hosted_api.py`, web smoke/browser tests | Credential Handoff, User Dashboard | `GAP-001`, `GAP-005`, `GAP-013`, `GAP-015`, `GAP-024`, `PG-HERMES` |
| `J-14` | Admin dashboard, exactly one operator, queued actions, audit | `python/arclink_api_auth.py`, `python/arclink_dashboard.py`, `python/arclink_action_worker.py`, `web/src/app/admin/page.tsx`, admin runbooks | `tests/test_arclink_api_auth.py`, `tests/test_arclink_admin_actions.py`, `tests/test_arclink_action_worker.py`, browser/admin tests | User Dashboard, Admin And Operator Journey | `GAP-017`, `GAP-018`, `PG-PROVISION` |
| `J-15` | Shared Host baremetal install/upgrade/health/enrollment reset | `deploy.sh`, `bin/deploy.sh`, bootstrap/install scripts, `bin/health.sh`, `systemd/**`, `README.md`, operations docs | `tests/test_deploy_regressions.py`, `tests/test_health_regressions.py`, agent service/enrollment tests, `bash -n` | Admin And Operator Journey | `GAP-011`, `GAP-025`, `PG-UPGRADE` |
| `J-16` | Shared Host Docker substrate and agent supervisor | `compose.yaml`, `bin/arclink-docker.sh`, `bin/docker-agent-supervisor.sh`, `bin/docker-health.sh`, Docker docs | `tests/test_arclink_docker.py`, `tests/test_deploy_regressions.py`, Docker health tests | Admin And Operator Journey | `GAP-019`, `PG-UPGRADE` |
| `J-17` | Sovereign Control Node install/upgrade/backup/reset | `bin/deploy.sh` control commands, `compose.yaml`, `docs/arclink/sovereign-control-node.md`, production runbook | `tests/test_arclink_docker.py`, `tests/test_arclink_host_readiness.py`, deploy/control tests, live runner dry-run tests | Provisioning And Deployment, Admin And Operator Journey | `GAP-001`, `GAP-004`, `GAP-011`, `GAP-017`, `GAP-018`, `GAP-019`, `PG-PROD`, `PG-PROVISION`, `PG-UPGRADE` |
| `J-18` | Hermes homes, Curator, user-agent refresh, gateways, `/start`, Discord retry | agent install/refresh scripts, `python/arclink_enrollment_provisioner.py`, hooks, public bot handoff code, `AGENTS.md` | `tests/test_arclink_agent_user_services.py`, `tests/test_arclink_enrollment_provisioner_regressions.py`, onboarding prompt/completion tests | Raven Onboarding And Control, Hermes And Agents | `GAP-001`, `GAP-003`, `GAP-005`, `GAP-025`, `PG-BOTS`, `PG-HERMES` |
| `J-19` | Dashboard plugins: Drive, Code, Terminal | `plugins/hermes-agent/drive/**`, `plugins/hermes-agent/code/**`, `plugins/hermes-agent/terminal/**`, installer/provisioning scripts, workspace steering | `tests/test_arclink_plugins.py`, browser product checks, workspace live-runner dry-run checks | Hermes And Agents, Workspace | `GAP-001`, `GAP-005`, `GAP-014`, `GAP-025`, `PG-HERMES` |
| `J-20` | Sharing, linked resources, no reshare, copy/duplicate, audit/revoke | `python/arclink_api_auth.py`, `python/arclink_mcp_server.py`, Drive/Code linked-root code, public bot approvals | `tests/test_arclink_hosted_api.py`, `tests/test_arclink_mcp_schemas.py`, `tests/test_arclink_plugins.py`, public bot tests | Workspace, Pod Comms, Recovery Atlas | `GAP-014`, `GAP-015`, `GAP-016`, `PG-BOTS` |
| `J-21` | Vault, qmd, PDF sidecars, retrieval MCP tools | `python/arclink_mcp_server.py`, `bin/qmd-*.sh`, `bin/pdf-ingest.*`, `bin/vault-watch.sh`, README/docs | `tests/test_arclink_mcp_schemas.py`, `tests/test_arclink_qmd_skill.py`, `tests/test_retrieval_journey_replay.py`, PDF/vault tests | Knowledge, Notion, SSOT, Memory | `GAP-025`, `PG-HERMES` |
| `J-22` | Notion indexed markdown, SSOT broker, webhook/batcher | `python/arclink_notion_ssot.py`, `python/arclink_notion_webhook.py`, `python/arclink_ssot_batcher.py`, `python/arclink_control.py`, Notion docs | `tests/test_notion_ssot.py`, `tests/test_arclink_notion_knowledge.py`, `tests/test_arclink_notion_webhook.py`, `tests/test_arclink_ssot_batcher.py`, `tests/test_arclink_notion_skill_text.py` | Knowledge, Notion, SSOT, Memory | `GAP-007`, `GAP-025`, `PG-NOTION` |
| `J-23` | Memory synthesis, recall stubs, daily plate, managed context | `python/arclink_memory_synthesizer.py`, `python/arclink_control.py`, managed-context plugin, memory scripts | `tests/test_memory_synthesizer.py`, `tests/test_arclink_memory_sync.py`, `tests/test_arclink_plugins.py` | Knowledge, Notion, SSOT, Memory | `PG-HERMES` |
| `J-24` | Pod comms, Crew Training, ArcLink Wrapped, Captain console | `python/arclink_pod_comms.py`, `python/arclink_crew_recipes.py`, `python/arclink_wrapped.py`, dashboard/admin UI, Captain Console steering | `tests/test_arclink_pod_comms.py`, `tests/test_arclink_crew_recipes.py`, `tests/test_arclink_wrapped.py`, notification/browser tests | Raven Onboarding And Control, User Dashboard, Pod Comms | `GAP-003`, `GAP-015`, `GAP-022`, `GAP-023`, `PG-BOTS`, `PG-PROVIDER` |
| `J-25` | Upgrades, component pins, release state, deploy keys | `bin/deploy.sh`, `bin/component-upgrade.sh`, `bin/pins.sh`, `python/arclink_pin_upgrade_check.py`, `config/pins.json`, upgrade docs | `tests/test_arclink_pin_upgrade_detector.py`, `tests/test_arclink_upgrade_notifications.py`, `tests/test_deploy_regressions.py` | Hermes And Agents, Admin And Operator Journey | `PG-UPGRADE` |
| `J-26` | Backups, restore, enrollment reset, org profile, repo sync | backup scripts, `docs/arclink/backup-restore.md`, org profile scripts/docs, enrollment reset paths, repo sync code | `tests/test_agent_backup_regressions.py`, backup/git tests, org profile tests, enrollment reset/purge tests | Admin And Operator Journey, Recovery Atlas | `GAP-013`, `GAP-020`, `GAP-025`, `PG-BACKUP` |
| `J-27` | Health, diagnostics, live proof, evidence ledger | `bin/health.sh`, `bin/docker-health.sh`, `python/arclink_diagnostics.py`, `python/arclink_live_runner.py`, `python/arclink_evidence.py`, live evidence docs | `tests/test_health_regressions.py`, `tests/test_arclink_diagnostics.py`, `tests/test_arclink_live_runner.py`, `tests/test_arclink_evidence.py`, fake/live E2E tests | Admin And Operator Journey, Recovery Atlas | `GAP-001`, `GAP-005`, `GAP-012`, `GAP-020`, `GAP-025`, `PG-PROD`, `PG-HERMES`, `PG-BACKUP` |
| `J-28` | Security, isolation, auth, CSRF, secret/path safety | `python/arclink_api_auth.py`, `python/arclink_access.py`, `python/arclink_agent_access.py`, `python/arclink_boundary.py`, dashboard proxy, secret regex, plugin root guards | `tests/test_arclink_api_auth.py`, `tests/test_arclink_access.py`, `tests/test_arclink_agent_access.py`, `tests/test_arclink_agent_mcp_auth.py`, `tests/test_arclink_secrets_regex.py`, plugin/hosted API tests | Security And Isolation Contract | `GAP-009`, `GAP-019`, `GAP-025` |

## Cross-Cutting Claim Checks

| Check | Must verify |
| --- | --- |
| Product matrix disproof | Every row in `research/PRODUCT_REALITY_MATRIX.md` is rechecked against implementation and tests; no row is copied as truth. |
| Seed draft discipline | `research/seed-user-journey-draft.md` and `research/seed-gaps-draft.md` are inputs only; contradictory evidence wins. |
| Mixed-engine review | Codex drives the main pass and Claude independently reviews the claim ledger and root docs; unresolved disagreement becomes a gap, proof gate, or policy question. |
| Vocabulary split | Captain-facing surfaces use Raven, ArcPod/Pod, Agent, Captain, Crew; Operator stays admin/deploy/runbook-facing. |
| Proof-gated honesty | Live/external behavior is not upgraded to `real` without authorized live proof and redacted evidence. |
| Broad validation honesty | Focused passing suites are not described as broad release validation while `GAP-025` full-suite failures remain open. |
| Handoff integrity | Each boundary between web, bot, payment, provisioning, dashboard, Hermes, provider, and notification gets a journey step and gap check. |
| Isolation | Each user/admin/provider/share/channel/filesystem route is checked for cross-user read/write/route leakage. |
| Recovery | Failure, retry, unavailable, cancellation, teardown, rollback, reset, reissue, and restore paths are covered, not just happy paths. |

## Canonical References

| Contract | Owner |
| --- | --- |
| Narrative happy paths, choices, dead ends, handoffs | `USER_JOURNEY.md` |
| Status labels, severities, gap IDs, policy questions, proof gates | `GAPS.md` |
| Journey joint IDs and source/test coverage | `research/COVERAGE_MATRIX.md` |
| Broader product claim set to re-audit, not trust blindly | `research/PRODUCT_REALITY_MATRIX.md` |

## Validation Command Map

| Area | Local commands for atlas validation |
| --- | --- |
| Docs/hygiene | `git diff --check`; `python3 tests/test_public_repo_hygiene.py`; `python3 tests/test_documentation_truths.py` |
| Web/UI | `cd web && npm test && npm run lint && npm run build`; `cd web && npm run test:browser` when local browser dependencies are installed |
| Public API/auth/dashboard | `python3 tests/test_arclink_hosted_api.py`; `python3 tests/test_arclink_api_auth.py`; `python3 tests/test_arclink_dashboard.py` |
| Billing/provider/router | `python3 tests/test_arclink_entitlements.py`; `python3 tests/test_arclink_chutes_and_adapters.py`; `python3 tests/test_arclink_chutes_oauth.py`; `python3 tests/test_arclink_llm_router.py` |
| Bots/notifications | `python3 tests/test_arclink_public_bots.py`; `python3 tests/test_arclink_public_bot_commands.py`; `python3 tests/test_arclink_telegram.py`; `python3 tests/test_arclink_discord.py`; `python3 tests/test_arclink_notification_delivery.py` |
| Provisioning/fleet/ingress | `python3 tests/test_arclink_provisioning.py`; `python3 tests/test_arclink_sovereign_worker.py`; `python3 tests/test_arclink_executor.py`; `python3 tests/test_arclink_fleet.py`; `python3 tests/test_arclink_ingress.py`; `python3 tests/test_arclink_docker.py` |
| Agent/Hermes install | `python3 tests/test_arclink_agent_user_services.py`; `python3 tests/test_arclink_enrollment_provisioner_regressions.py`; `python3 tests/test_arclink_plugins.py` |
| Knowledge/Notion/memory | `python3 tests/test_arclink_mcp_schemas.py`; `python3 tests/test_arclink_notion_knowledge.py`; `python3 tests/test_notion_ssot.py`; `python3 tests/test_arclink_ssot_batcher.py`; `python3 tests/test_memory_synthesizer.py`; `python3 tests/test_arclink_memory_sync.py` |
| Operations/live-proof dry run | `python3 tests/test_arclink_action_worker.py`; `python3 tests/test_arclink_live_runner.py`; `python3 tests/test_arclink_e2e_fake.py`; `bash -n deploy.sh bin/*.sh test.sh` |

Live commands stay out of this mission unless the operator later authorizes a
separate proof window.
