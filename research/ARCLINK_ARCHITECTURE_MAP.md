# ArcLink Architecture Map For ArcLink Transformation

Source: public ArcLink repository snapshot prepared on 2026-05-01. Use the
repository history as the source of truth for exact commit provenance.

## Core Mental Model

ArcLink is a shared-host operating layer for Hermes agents. The current product shape is operator-led: one Curator agent owns onboarding, operator approval, notifications, upgrades, and user lane repair. Each enrolled user receives an isolated Hermes lane backed by a host Unix user or a Docker-supervised equivalent. The system is deliberately not a chatbot wrapper; it is a control plane for durable agent identity, context, file memory, Notion rails, provider auth, bot gateways, health, backup, and access surfaces.

ArcLink should preserve the operating strength and remove friction. The new product shape is self-serve, single-user deployment: website form, Telegram bot, or Discord bot starts onboarding; Stripe payment and/or entitlement gates provisioning; ArcLink creates one isolated user deployment with obscure subdomains, a unified dashboard, files, code workspace, Hermes, managed memory, and bot conversation surfaces.

## Existing Deployment Paths

ArcLink already has two supported paths.

- Baremetal path: `./deploy.sh install`, `./deploy.sh upgrade`, `./deploy.sh health`. Uses Debian/Ubuntu systemd, host Unix accounts, systemd user services, Tailscale Serve/Funnel, Curator, and operator-managed upgrades.
- Docker path: `./deploy.sh docker install`, `./deploy.sh docker upgrade`, `./deploy.sh docker health`, `./deploy.sh docker enrollment-*`. Uses Docker Compose for shared services and `agent-supervisor` for enrolled user agents instead of per-user systemd.

ArcLink should start from the Docker path, not from the baremetal path. Docker mode already has most of the services ArcLink needs and is easier to turn into a SaaS provisioning engine.

## Existing Docker Services

From `compose.yaml` and `docs/docker.md`, the current first-class Docker stack includes:

- `postgres`: Nextcloud database.
- `redis`: Nextcloud cache and likely useful for future queue/pubsub work.
- `nextcloud`: shared vault UI mounted from `arclink-priv/vault`.
- `arclink-mcp`: control-plane MCP server over HTTP.
- `qmd-mcp`: qmd retrieval MCP.
- `notion-webhook`: Notion event receiver.
- `vault-watch`: inotify-driven vault watcher for PDF ingest/qmd refresh/memory synth triggers.
- `agent-supervisor`: Docker-mode replacement for per-user systemd services. It reconciles gateway, Hermes dashboard, dashboard proxy, cron tick, refresh, and code-server workspace processes from DB state.
- `ssot-batcher`: recurring Notion SSOT batch processing.
- `notification-delivery`: notification outbox delivery.
- `health-watch`: recurring health check container.
- `curator-refresh`: periodic Curator/control-plane refresh and queued operator upgrades.
- `qmd-refresh`: periodic qmd refresh.
- `pdf-ingest`: PDF extraction to generated markdown sidecars.
- `memory-synth`: recurring semantic recall card synthesis.
- `hermes-docs-sync`: syncs Hermes docs into the vault.
- `quarto-render`: optional Quarto rendering profile.
- `backup`: optional GitHub backup profile.
- `curator-gateway`, `curator-onboarding`, `curator-discord-onboarding`: optional Curator profile services.

ArcLink must keep this breadth. A first SaaS version can centralize some jobs later, but the MVP should not silently drop qmd, memory synth, Notion, health, code-server, Nextcloud, or agent supervisor functionality.

## Persistent State

Current deployed layout is rooted around `arclink-priv/`:

- `config/docker.env` or `config/arclink.env`: runtime configuration and generated secrets.
- `vault/`: durable shared file memory.
- `state/arclink-control.sqlite3`: SQLite control-plane DB.
- `state/agents/`: per-agent manifests and managed-memory payloads.
- `state/docker/users/`: Docker-mode user homes.
- `state/curator/hermes-home/`: Curator HERMES_HOME.
- `state/nextcloud/`: Nextcloud state.
- `state/notion-index/markdown/`: indexed Notion markdown.
- `state/pdf-ingest/markdown/`: generated PDF sidecars.
- `state/runtime/hermes-venv/` and `state/runtime/hermes-agent-src/`: pinned Hermes runtime.

ArcLink should introduce a new root such as `/arcdata` on production hosts and keep per-tenant state physically separated:

- `/arcdata/control/`: ArcLink owner/global control plane, DB, Redis, logs, Stripe/Cloudflare/job state.
- `/arcdata/deployments/<deployment_id>/`: per-user deployment data.
- `/arcdata/deployments/<deployment_id>/vault/`: user vault.
- `/arcdata/deployments/<deployment_id>/hermes-home/`: user Hermes identity and sessions.
- `/arcdata/deployments/<deployment_id>/nextcloud/`: per-user Nextcloud state if using dedicated Nextcloud per user; otherwise per-user Nextcloud data in a shared instance.
- `/arcdata/deployments/<deployment_id>/qmd/`: qmd cache/index if isolated per user.
- `/arcdata/deployments/<deployment_id>/logs/`: user service logs.

## Control DB Surfaces

`python/arclink_control.py` owns the SQLite schema and control-plane logic. Important existing tables:

- `settings`: key/value runtime settings.
- `bootstrap_requests`: approval/provisioning requests, including auto-provision status and retry metadata.
- `bootstrap_tokens`: agent MCP bootstrap tokens.
- `rate_limits`: simple rate limit observations.
- `agents`: active/archived agent registry with `agent_id`, `unix_user`, `hermes_home`, channels, model preset/string, manifest path, status.
- `agent_identity`: human/agent identity, Notion verification status, write mode.
- `vaults`, `vault_definitions`, `agent_vault_subscriptions`: vault discovery and per-agent subscription graph.
- `pin_upgrade_notifications`: component upgrade watch state.
- `notification_outbox`: notifications to Curator/user agents/operators.
- `operator_actions`: queued operator actions such as upgrades, pin applies, remote SSH key install.
- `onboarding_sessions`: Telegram/Discord onboarding state machine and answers.
- `onboarding_update_failures`: failed update tracking.
- `ssot_access_audit` and `ssot_pending_writes`: Notion write guardrails.
- `notion_identity_claims`, `notion_identity_overrides`, `notion_index_documents`, `notion_retrieval_audit`: Notion identity, index, and audit state.
- `memory_synthesis_cards`: synthesized recall cards keyed by source.

ArcLink should add SaaS tables rather than stuffing commercial state into these existing tables:

- `arclink_users`: product account identity.
- `arclink_deployments`: one or more deployments per account; stores obscure prefix, service hostnames, status, plan, active model/provider, region/node.
- `arclink_subscriptions`: Stripe subscription mirror and entitlement state.
- `arclink_provisioning_jobs`: job queue state with idempotency keys and rollback markers.
- `arclink_dns_records`: Cloudflare/wildcard/subdomain state and drift detection.
- `arclink_admins`: separate admin identities, never mixed with product users.
- `arclink_audit_log`: append-only admin action audit.
- `arclink_service_health`: latest health snapshots by deployment/service.
- `arclink_events`: onboarding/payment/provisioning/activity event stream for dashboard/admin views.

## Onboarding Flow Today

`python/arclink_onboarding_flow.py` implements the Curator onboarding state machine. Notable states:

- `awaiting-name`: collect human display name.
- `awaiting-profile-match`: optional org-profile matching.
- `awaiting-unix-user`: choose private host username.
- `awaiting-purpose`: short agent mission.
- `awaiting-bot-platform`: Telegram/Discord, currently matches onboarding channel.
- `awaiting-bot-name`: name private agent bot.
- `awaiting-model-preset`: choose Chutes, Claude Opus, OpenAI Codex, or org-provided model.
- `awaiting-model-id`: choose exact model id.
- `awaiting-thinking-level`: choose reasoning effort. Chutes appends `:THINKING` when enabled/supported.
- `awaiting-operator-approval`: current friction point to remove for paid self-serve default.
- `awaiting-bot-token`: user creates Telegram/Discord bot and pastes token.
- `awaiting-provider-credential`: BYOK/API key flow.
- `awaiting-provider-browser-auth`: Codex device/OAuth browser auth flow.
- `provision-pending`: active provisioning.
- `awaiting-agent-backup-*`: optional private Hermes-home backup repo.
- `awaiting-notion-*`: optional self-serve Notion identity verification.
- `completed`, `denied`.

ArcLink should preserve the power but alter the default path:

- Website form can create the same `onboarding_session` abstraction.
- Telegram and Discord public bots should share the same state machine.
- Payment replaces operator approval for ordinary self-serve plans.
- Admin/support can still manually approve, comp, reprovision, suspend, or override.
- Chutes should be the recommended/default provider through ArcLink-managed per-deployment keys.
- BYOK Codex/Claude should remain optional power-user lanes.

## Provisioning Flow Today

`python/arclink_enrollment_provisioner.py` drives provisioning.

Key path:

1. Auto-provision request appears in `bootstrap_requests`.
2. `_run_one` claims the request with `mark_auto_provision_started`.
3. `_ensure_runtime_user_ready` creates/repairs the Unix or Docker-mode user home.
4. `_grant_auto_provision_access` prepares access and token grants.
5. `issue_auto_provision_token` creates a bootstrap token.
6. `bin/init.sh agent` registers the agent and seeds Hermes home.
7. `_provision_user_access_surfaces` runs `install-agent-user-services.sh`, creates dashboard/code access state, syncs Nextcloud access, and starts/supervises web surfaces.
8. `_seed_user_provider` runs `arclink_headless_hermes_setup.py` with staged provider credentials.
9. `_configure_user_telegram_gateway` or `_configure_user_discord_gateway` writes bot token/env, updates agent channels, refreshes managed memory, and sends completion bundle.
10. `_refresh_user_agent_memory` materializes `HERMES_HOME/state/arclink-vault-reconciler.json` for the managed-context plugin.
11. Optional backup and Notion verification phases follow.

ArcLink should keep this idempotent/retryable structure but route it through SaaS jobs with payment and DNS prerequisites. Every provisioning step must be resumable and rollback-aware.

## Agent Access Surfaces Today

`python/arclink_agent_access.py` and `bin/run-agent-code-server.sh` create access state and run per-agent web surfaces.

Existing access includes:

- Hermes dashboard local URL and basic-auth proxy.
- code-server workspace with generated password.
- Optional Tailscale Serve HTTPS publishing.
- Nextcloud access synced through `arclink_nextcloud_access.py`.
- Remote SSH key onboarding via operator actions and Tailscale-only restrictions.

ArcLink destination surfaces:

- Unified dashboard: `u-<prefix>.arclink.online`.
- Nextcloud/files: prefer `files-<prefix>.arclink.online` because Nextcloud is fragile under path prefixes.
- code-server: prefer `code-<prefix>.arclink.online` because VS Code websocket/proxy routes are simpler on a host.
- Hermes dashboard/API: prefer `hermes-<prefix>.arclink.online`, optionally embedded by the unified dashboard.
- Bot conversations: Telegram and Discord public onboarding bots, then private agent bot/channel handoff.
- SSH/TUI: raw SSH cannot be routed by HTTP reverse proxies or Traefik HostSNI unless wrapped in TLS. Use an SSH bastion (`ssh.arclink.online`) keyed by username/deployment or a TLS-wrapped SSH approach later. Cloudflare orange-cloud does not proxy arbitrary SSH unless using a product like Spectrum or Tunnel/Access.

## Managed Context And Memory

The `plugins/hermes-agent/arclink-managed-context` plugin is central and should be preserved/rebranded carefully.

It:

- Reads `HERMES_HOME/state/arclink-vault-reconciler.json`.
- Injects compact refreshed context via Hermes `pre_llm_call` hook.
- Surfaces local model runtime so stale prompts/config do not win.
- Surfaces `[managed:vault-landmarks]`, `[managed:recall-stubs]`, `[managed:notion-landmarks]`, `[managed:today-plate]`.
- Injects tool recipes for MCP rails.
- Injects agent bootstrap token into protected tool calls in `pre_tool_call`.
- Emits JSONL telemetry at `HERMES_HOME/state/arclink-context-telemetry.jsonl`.

Memory synthesis lives in `python/arclink_memory_synthesizer.py`, with cards stored in `memory_synthesis_cards`. It scans vault and Notion sources, hashes source signatures, calls an OpenAI-compatible model, normalizes cards, and writes status.

ArcLink must keep hot-swappable memory stubs. The user-facing language should teach this as a future-proof skills and memory harness: users buy an agentic workspace now, then grow skills over time.

## Provider/Auth Surfaces

`config/model-providers.yaml` currently defaults to:

- Chutes: `moonshotai/Kimi-K2.6-TEE`, with `zai-org/GLM-5.1-TEE` and `model-router` recommended.
- Claude Opus: `claude-opus-4-7`.
- OpenAI Codex: `gpt-5.5`.

`python/arclink_onboarding_provider_auth.py` supports provider setup, Chutes thinking mode handling, Codex device auth, Anthropic PKCE, and API key normalization.

ArcLink should make model defaults centrally managed by environment/config and refreshed by an agentic model-catalog job. Chutes should be default and ArcLink-managed; BYOK Codex/Claude remains available.

## Health And Upgrade Surfaces

Existing health/upgrade surfaces:

- `./deploy.sh health` and `./deploy.sh docker health`.
- `bin/docker-health.sh` validates Compose services, HTTP endpoints, database, qmd, Redis/Postgres, Docker agent MCP auth, managed context/SOUL presence.
- `health-watch` recurring job.
- `pin_upgrade_notifications` and component upgrade commands.
- `./deploy.sh upgrade` and Docker upgrade paths use configured upstream and record release state.

ArcLink admin dashboard must surface these, not reinvent blind charts. Health should be deployment-level and fleet-level.

## Rebrand Notes

ArcLink rebrand must be systematic and staged:

- Public product strings, docs, bot copy, dashboard labels, service realms, URLs, env examples, tests.
- Paths and persisted state names for new installs should be ArcLink-native.
- Legacy `ARCLINK_*` env vars may need compatibility aliases during migration, but new public docs/config should prefer `ARCLINK_*`.
- Python module/script names can be migrated gradually if tests and imports are updated atomically. Avoid halfway states where UI says ArcLink but service files, messages, and dashboard still say ArcLink.
- Existing tests intentionally assert current names; update tests with the rebrand rather than weakening coverage.

## First Transformation Principle

Do not throw away ArcLink. ArcLink is ArcLink sharpened into a self-serve SaaS deployment product with first-class user and admin dashboards, payment/DNS orchestration, Chutes-first inference, and scalable operations.
