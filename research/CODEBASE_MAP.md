# Codebase Map

Freshness checkpoint: reviewed for the ArcLink ecosystem gap repair PLAN
handoff on 2026-05-08 using public repository files only.

## Root Entrypoints

| Path | Role |
| --- | --- |
| `deploy.sh` | Thin wrapper for the canonical deploy menu and named host flows. |
| `bin/deploy.sh` | Bare-metal install, upgrade, health, service repair, enrollment, Notion, deploy-key, and operator menu implementation. |
| `bin/arclink-docker.sh` | Docker install, upgrade, reconfigure, reconcile, health, logs, ports, teardown, pins, and live-smoke orchestration. |
| `compose.yaml` | Shared Host Docker service topology for control API/web, qmd, MCP, jobs, Curator, Nextcloud, and agent supervision. |
| `Dockerfile` | Docker image build for Python, Node, qmd, Docker CLI, pinned Hermes runtime, and web assets. |
| `bin/arclink-ctl` | Operator CLI for control-plane DB, org profile, onboarding recovery, upgrade checks, and product/admin operations. |
| `bin/arclink-live-proof` | Credential-gated live proof runner entrypoint. |
| `ralphie.sh` | Ralphie phase runner. |
| `test.sh` | Heavy preflight plus sudo install smoke. |
| `IMPLEMENTATION_PLAN.md` | BUILD handoff plan for the active ecosystem gap repair mission. |
| `AGENTS.md` | Operator and coding-agent operating guide. |

## Major Directories

| Directory | Responsibility |
| --- | --- |
| `bin/` | Deploy, Docker, health, bootstrap, qmd, PDF, Nextcloud, service, backup, plugin install, proof, and runtime wrappers. |
| `python/` | Control plane, hosted API, auth, product/onboarding, provisioning, Docker supervisor, action worker, MCP, Notion/SSOT, memory, evidence, diagnostics, fleet, rollout, and ingress modules. |
| `web/` | Next.js hosted web app, onboarding, checkout, login, user dashboard, admin dashboard, API client, Node tests, and Playwright tests. |
| `plugins/hermes-agent/` | ArcLink-owned Hermes plugins: managed context, Drive, Code, and Terminal. |
| `hooks/hermes-agent/` | Hermes hooks, including ArcLink Telegram `/start` behavior. |
| `skills/` | ArcLink skills for qmd, Notion, SSOT, vaults, resources, upgrade orchestration, first contact, and PDF export. |
| `systemd/` | Bare-metal user service and timer templates. |
| `compose/` | Supplemental Compose assets. |
| `config/` | Public env examples, pins, model provider defaults, org-profile schemas/examples, and team-resource examples. |
| `docs/` | Operator docs, architecture, Docker, API, product/security/runbooks, evidence templates, and docs needing status classification. |
| `tests/` | Focused Python regression coverage for host lifecycle, Docker, onboarding, hosted API, provisioning, plugins, qmd, Notion, SSOT, memory, and docs. |
| `research/` | Ralphie research, steering, coverage, stack, and handoff artifacts. |
| `consensus/` | Phase gate records and build-gate status. |
| `templates/` | Public templates used to seed private state. |

## Runtime Lanes

| Lane | Shape | Primary files |
| --- | --- | --- |
| Shared Host | Public repo plus private state, systemd services, service user, per-user Unix accounts, Curator, qmd, Notion, Nextcloud, and user-agent services | `bin/deploy.sh`, `bin/bootstrap-*.sh`, `bin/install-*-services.sh`, `bin/refresh-agent-install.sh`, `python/arclink_enrollment_provisioner.py`, `systemd/user/*` |
| Shared Host Docker | Compose services plus Docker agent supervisor and persistent Docker user homes | `compose.yaml`, `Dockerfile`, `bin/arclink-docker.sh`, `bin/docker-*.sh`, `python/arclink_docker_agent_supervisor.py` |
| Sovereign Control Node / Hosted Product | Hosted web/API, Stripe entitlement, provisioning, action queue, control provisioner, ingress, fleet, rollout, and evidence | `python/arclink_hosted_api.py`, `python/arclink_product.py`, `python/arclink_onboarding.py`, `python/arclink_provisioning.py`, `python/arclink_action_worker.py`, `python/arclink_fleet.py`, `python/arclink_rollout.py`, `web/src/*` |

## Docker Service Map

`compose.yaml` defines these service-level surfaces: `postgres`, `redis`,
`nextcloud`, `arclink-mcp`, `qmd-mcp`, `notion-webhook`, `control-api`,
`control-web`, `control-ingress`, `control-provisioner`, `vault-watch`,
`agent-supervisor`, `ssot-batcher`, `notification-delivery`, `health-watch`,
`curator-refresh`, `qmd-refresh`, `pdf-ingest`, `memory-synth`,
`hermes-docs-sync`, `quarto-render`, `backup`, `curator-gateway`,
`curator-onboarding`, `curator-discord-onboarding`, and legacy `arclink-qmd`
compatibility.

## Completed Baseline Hotspots

| Surface | Files to preserve | Assumption |
| --- | --- | --- |
| Dashboard file roots | `bin/install-agent-user-services.sh`, `bin/refresh-agent-install.sh`, `plugins/hermes-agent/*/dashboard/plugin_api.py` | Drive, Code, and Terminal must deny secrets, private runtime state, traversal, and symlink escapes. |
| qmd bind address | `systemd/user/arclink-qmd-mcp.service`, `bin/qmd-daemon.sh`, `bin/health.sh`, `bin/docker-health.sh` | Bare-metal qmd binds loopback by default unless deliberately widened. |
| Notion exact reads | `python/arclink_control.py`, `python/arclink_mcp_server.py`, Notion skills | Agent-facing exact reads stay scoped to configured shared/indexed roots or privileged audited operations. |
| SSOT writes | `python/arclink_notion_ssot.py`, `python/arclink_ssot_batcher.py` | Destructive Notion mutations are rejected or routed through explicit approval rails. |
| Docker dashboard boundary | `compose.yaml`, `python/arclink_provisioning.py`, `python/arclink_docker_agent_supervisor.py`, `bin/run-hermes-dashboard-proxy.sh` | Dashboard backends must not be reachable around the auth proxy. |
| Token argv exposure | `bin/*.sh`, `python/arclink_docker_agent_supervisor.py` | Bootstrap tokens should pass through files, stdin, or descriptors, not process argv. |
| Generated cleanup | `bin/pdf-ingest.py`, `python/arclink_notion_webhook.py` | Cleanup revalidates generated-root containment before unlink/move. |
| Team resources | `bin/clone-team-resources.sh`, `skills/arclink-resources/SKILL.md` | Manifest slugs are sanitized before destructive git operations. |
| Onboarding recovery | `python/arclink_curator_onboarding.py`, `python/arclink_curator_discord_onboarding.py`, `python/arclink_public_bots.py`, `python/arclink_onboarding_completion.py`, `python/arclink_onboarding_provider_auth.py` | Failure, denial, skip, retry, cancel, provider validation, and credential handling stay visible, durable, and recoverable. |

## Remaining BUILD Hotspots

| Slice | Files to inspect first | Focus |
| --- | --- | --- |
| Verification and release review | `IMPLEMENTATION_PLAN.md`, `research/RALPHIE_ARCLINK_ECOSYSTEM_GAP_REPAIR_STEERING.md`, `README.md`, `AGENTS.md`, `docs/DOC_STATUS.md`, `docs/docker.md`, `docs/API_REFERENCE.md`, `docs/arclink/*`, `web/package.json`, `test.sh`, `bin/ci-preflight.sh` | Confirm the checked docs/validation slice matches behavior, run the focused validation floor, and mark proof-gated/live claims honestly. |

## Architecture Assumptions

- This map is based on public repository files only.
- Private state, live user homes, token files, deploy keys, OAuth data, bot
  tokens, and production `.env` values are intentionally out of scope.
- BUILD should treat code and focused tests as truth when docs disagree, then
  update docs after behavior is corrected.
- Shared Host, Docker, and Sovereign Control Node boundaries should stay
  distinct; parity means aligned contracts, defaults, health, and docs.
