# ArcLink Architecture

ArcLink is a Sovereign Control Node: one control plane that provisions, governs,
bills, and operates many isolated AI agent runtimes (ArcPods). A Captain talks
to the public Raven bot persona over Telegram/Discord, pays via Stripe, and
receives one or more ArcPods — each an isolated Docker Compose stack running a
Hermes Agent. The Operator governs the fleet from an admin dashboard, the
chat-native Operator Raven console, and a single in-stack operator Hermes agent.
This document describes the current module map, data flow, and integration
boundaries.

Honesty note: this doc separates what is implemented and tested locally from
what is proof-gated (named `PG-*`) and what is policy/risk-accepted (GAP-019).
No capability below should be read as live-proven unless it says so.

## Module Map

There are **87** `python/arclink_*.py` modules (including helpers and legacy
intake modules). They are grouped below by subsystem. Plugins live under
`plugins/hermes-agent/`, not `python/` (see the Hermes Workspace Plugins
section). The schema mechanism is a single idempotent `ensure_schema()` with
`CREATE TABLE IF NOT EXISTS` plus a few `*__new` rebuild migrations — there is
**no version ledger or numbered migration**; it is create-if-absent plus
rebuild-when-needed (idempotent, not reversible/versioned).

### Control plane core / API / schema

```text
arclink_control.py          Schema (ensure_schema), Config, env loading, all table DDL, events/notifications/settings/rate-limit/IP-guard helpers, entitlement/refuel/plan logic, managed-memory payload, recall stubs, Notion index/SSOT broker, today-plate
arclink_hosted_api.py       Production WSGI app, _ROUTES dispatch (/api/v1), CORS, cookies, webhooks, OpenAPI generation
arclink_api_auth.py         Sessions/CSRF/password hashing, rate limits, login/logout, admin RBAC+MFA, provider-state reads, reconciliation API, all share-grant/claim-nonce/Linked-resource lifecycle
arclink_dashboard.py        build_operator_snapshot, build_scale_operations_snapshot, control_node_provisioning_readiness (GAP-030), backup write-check read model, ARCLINK_ADMIN_ACTION_SUPPORT matrix
arclink_boundary.py         rowdict + json-safe helpers, reject_secret_material, require_docker_trusted_host_risk_accepted (GAP-019 gate)
arclink_secrets_regex.py    Redaction (redact_then_truncate)
arclink_http.py             HTTP transport helper
arclink_rpc_client.py       RPC client helper
arclink_ctl.py              CLI helper
arclink_product.py          Local no-secret WSGI prototype config (NOT production)
arclink_product_surface.py  Local no-secret WSGI prototype surface (NOT production; production surface is Next.js web/ + hosted API)
arclink_surface_contract.py Executable cross-surface finish-gate linter (GAP-033)
```

### LLM router / providers

```text
arclink_llm_router.py       FastAPI ASGI router (control-llm-router, 8090): /health, /v1/models, /v1/chat/completions, policy/reservation/relay/settlement, fallback cascade
arclink_chutes.py           Chutes catalog parse, deployment boundary, usage ingestion, fake key/inference
arclink_chutes_live.py      Chutes account/usage/key/OAuth-introspect adapter (TEST-ONLY, UNWIRED)
arclink_chutes_oauth.py     Chutes PKCE OAuth helpers (TEST-ONLY, UNWIRED, fake exchanger)
arclink_adapters.py         Stripe (Fake/Live), Cloudflare, Traefik/Tailscale rendering helpers
arclink_model_providers.py  Provider preset helpers
```

### Captain public bots / onboarding

```text
arclink_public_bots.py             Raven turn engine (handle_arclink_public_bot_turn): commands, routing law, onboarding/checkout copy, channel pairing, selected-agent bridge, Crew Training, Academy Mode, share approvals/claims, credentials, retire-agent, refuel
arclink_telegram.py                Telegram transport + webhook + per-chat command scope + operator interception, native callback metadata, outbound long-text split batching
arclink_discord.py                 Discord interaction/Gateway message handler, Ed25519 verify, dedupe, slash/component parsing, safe component/embed/attachment sends
arclink_public_bot_commands.py     Deploy-time command registration + webhook ensure + scope refresh
arclink_onboarding.py              NEW ArcLink public-bot onboarding state machine (arclink_onboarding_sessions/_events)
arclink_onboarding_flow.py         OLD Curator/"Almanac" intake flow (Unix-user provisioning) — present and active
arclink_onboarding_completion.py   OLD Curator completion bundle — present and active
arclink_onboarding_provider_auth.py OLD Curator provider OAuth (Codex/Anthropic) — present and active
arclink_curator_onboarding.py      Curator-channel onboarding wiring
arclink_curator_discord_onboarding.py Curator Discord onboarding wiring
```

### Operator Raven / operator control

```text
arclink_operator_raven.py          Operator command surface (read previews + real action queueing)
arclink_operator_agent.py          Operator's single in-stack Hermes identity + free-form turn bridge
arclink_operator_upgrade_broker.py Docker-mode operator upgrade broker (operator-upgrade-broker, 8917)
arclink_operator_upgrade_host_runner.py Host-side queue runner for authenticated operator upgrade jobs
arclink_action_worker.py           Admin/operator action-intent consumer (arclink_action_intents)
arclink_rollout.py                 Rollout model + ArcPod-update planner/materializer/record-only batch
arclink_pin_upgrade_check.py       Hourly pinned-component upstream upgrade detector
arclink_upgrade_policy.py          Source-owned dependency and ArcPod rollout policy catalog
```

### Academy / Crew / SOUL

```text
arclink_academy_programs.py  Academy lifecycle (Majors, Trainees, sticky Mode, gallery, adopt, central corpus, apply staging, continuing-education)
arclink_academy_trainer.py   No-network/no-write Academy schemas + fail-closed planning (lanes, corpus, gates, review, application-preview boundary)
arclink_academy_scheduler.py Weekly forward-maintenance job (control-academy-ce)
arclink_crew_recipes.py      Crew Recipes + SOUL overlay + Academy-status overlay + per-Agent artifacts
```

### Hermes workspace / dashboard sidecar

```text
arclink_dashboard_auth_proxy.py  Signed-session reverse proxy in front of the Hermes dashboard (HS256 JWT-shaped cookie, NOT Basic Auth; mount-prefix rewriting; managed-lifecycle 409 intercept)
arclink_nextcloud_access.py      Provisioning-side occ user sync (gated by ENABLE_NEXTCLOUD)
arclink_headless_hermes_setup.py Headless Hermes home setup helper
arclink_skill_enablement.py      Per-Agent approved-skill enablement, guarded fleet-shared skill discovery, /reload_skills receipt rail
```

### Public Agent gateway / exec-broker / pod-comms / supervisor family

```text
arclink_public_agent_bridge.py      Short-lived boundary process run INSIDE a Hermes gateway container; replays a public Telegram/Discord turn through Hermes' own native gateway pipeline
arclink_gateway_exec_broker.py      Trusted-host broker (8911) owning Docker-exec authority for Raven-mediated public-channel Agent replies
arclink_deployment_exec_broker.py   Trusted-host broker (8912) owning the Docker socket for deployment-scoped Compose ops (compose_up/ps/down)
arclink_agent_supervisor_broker.py  Trusted-host broker (8913) owning the Docker socket for the dashboard network/proxy sidecar lifecycle
arclink_docker_agent_supervisor.py  Root reconciliation loop (no Docker socket) driving the helper family
arclink_agent_process_helper.py     Root helper (8916) owning the setpriv privilege-drop process boundary
arclink_agent_user_helper.py        Root helper (8915) owning container Unix user/home creation + chown
arclink_migration_capture_helper.py Root helper (8914) for migration capture/materialize
arclink_pod_comms.py                Agent-to-Agent messaging over arclink_pod_messages
arclink_rejection_incidents.py      Shared redacted JSONL incident logger for every broker/helper
```

### Provisioning / fleet / ingress / migration

```text
arclink_sovereign_worker.py        Sovereign fleet ArcPod loop (control-provisioner): place -> render -> apply -> teardown
arclink_enrollment_provisioner.py  Legacy/starter single-machine onboarding loop + root maintenance loop draining operator_actions
arclink_provisioning.py            Provisioning intent render, compose generation, state roots, identity projection
arclink_fleet.py                   Fleet host registry + placement strategy
arclink_fleet_enrollment.py        Enrollment-token mint/consume + hash-chained audit
arclink_fleet_inventory_worker.py  Periodic liveness/capacity/inventory probe worker (incl. docker-local-starter no-SSH probe)
arclink_inventory.py               Inventory machines registry
arclink_inventory_hetzner.py       Hetzner cloud provisioning
arclink_inventory_linode.py        Linode cloud provisioning
arclink_asu.py                     ASU capacity computation
arclink_ingress.py                 DNS records + Cloudflare/Traefik/Tailscale ingress
arclink_pod_migration.py           The only real capture+materialize+verify+rollback path (reprovision action)
arclink_host_readiness.py          No-mutation host preflight checks
arclink_executor.py                Injectable fail-closed Docker Compose + provider-mutation orchestration boundary (Subprocess/Ssh/Brokered/Fake runners)
```

### Billing / entitlements

```text
arclink_entitlements.py     Stripe webhook processing + reconciliation drift
```

(Entitlement state, refuel ledger, plan pricing, comp, and the subscription
mirror live in `arclink_control.py`; Stripe clients live in `arclink_adapters.py`.)

### Sharing / fleet folder

```text
arclink_fleet_share.py      Fleet shared-folder git-sync engine + control-plane CRUD + CLI
```

(Share grants, claim nonces, and Linked-resource projection live in
`arclink_api_auth.py`.)

### Backup / lifecycle / wrapped

```text
arclink_wrapped.py          ArcLink Wrapped scoring/render/cadence/scheduler/delivery
```

(Backup scripts live in `bin/`; `arclink_executor.py` and
`arclink_pod_migration.py` cover the lifecycle.)

### Knowledge / memory / Notion / MCP

```text
arclink_memory_synthesizer.py Memory synthesis card builder (memory-synth job)
arclink_org_profile.py        Org-profile validate/apply/doctor
arclink_org_profile_builder.py Org-profile builder
arclink_skill_enablement.py   Per-agent approved-skill enablement helper
arclink_notion_ssot.py        Notion API client + SSOT handshake + no-secret proof harness (PG-NOTION)
arclink_notion_webhook.py     Notion webhook receiver + verification-token arming
arclink_ssot_batcher.py       Notion-event batcher worker
arclink_mcp_server.py         ArcLink control-plane MCP server (all agent-facing tools)
arclink_resource_map.py       Shared/managed resource-rail line composition
```

### Diagnostics / health / evidence / notifications

```text
arclink_diagnostics.py           Secret-safe presence-only provider checks
arclink_live_journey.py          4 journey catalogs (hosted/external/workspace/all)
arclink_live_runner.py           Live-proof orchestration (bin/arclink-live-proof), workspace runners
arclink_evidence.py              Redaction + evidence ledger + arclink_evidence_runs DAL (UNWIRED)
arclink_health_watch.py          Edge-triggered operator health notifications
arclink_notification_delivery.py Notification-outbox delivery worker + Hermes bridge dispatch
```

### Misc / helpers

```text
arclink_access.py        Access helpers
arclink_agent_access.py  Agent access helpers
```

### Hermes Dashboard plugins (under `plugins/hermes-agent/`)

```text
plugins/hermes-agent/
  arclink-theme/             No-tab ArcLink dashboard theme plugin
  arclink-managed-context/   Managed agent context, recall budget tiers, ArcLink MCP bootstrap injection
  drive/                     Hermes Dashboard file manager (Workspace/Fleet/Linked roots; vault alias is compatibility-only)
  code/                      Hermes Dashboard native code workspace and git surface
  terminal/                  Managed-pty / tmux-pty persistent-session terminal surface
```

Python modules live under `python/` and import from `arclink_control.py` for
database access through the ArcLink-owned `arclink_*` tables in the shared
SQLite/Postgres schema.
Hermes Dashboard plugins live under `plugins/hermes-agent/` and are installed
into each target Hermes home by ArcLink wrapper scripts.

## Data Flow

The NEW (production) Captain path runs through Raven Stripe checkout. An OLD
Curator/"Almanac" host-Unix-user intake flow (`arclink_onboarding_flow` +
`_completion` + `_provider_auth`) is also present and active; the NEW Raven path
is the Captain-facing production path.

```text
Captain ──► Raven (Telegram / Discord) / web onboarding
                │
                ▼
         arclink_onboarding_sessions
         arclink_onboarding_events
                │
                ▼
         Stripe Checkout (fake adapter by default; live = PG-STRIPE)
                │
                ▼
         Stripe Webhook ──► arclink_entitlements
                │               │
                ├──────────────►├── arclink_subscriptions (mirror)
                ▼               └── arclink_webhook_events (idempotent replay)
         arclink_users
         (entitlement: none|paid|comp|past_due|cancelled)
         arclink_refuel_credits (FIFO fuel ledger; LOCAL budget accounting only)
                │
                │  provisioning gate: arclink_deployment_can_provision (paid|comp)
                ▼
         arclink_provisioning (dry-run intent render)
                │
                ├── Docker Compose services (incl. control-llm-router)
                ├── Domain/Tailscale ingress + SSH intent (arclink_dns_records)
                ├── Chutes/router key lifecycle (arclink_llm_router_keys)
                ├── Traefik labels and ingress
                ├── State roots, workspace mounts, and secret references
                ├── Dashboard plugin env for Drive, Code, Terminal
                └── Service-health placeholders (arclink_service_health)
                │
                ▼
         arclink_sovereign_worker (control-provisioner: place->render->apply->teardown)
         arclink_executor (guarded, fail-closed; Subprocess/Ssh/Brokered/Fake)
                │
                ├── Docker Compose apply / lifecycle (stop|restart|inspect|teardown)
                ├── Domain/Tailscale ingress apply (live DNS = PG-INGRESS)
                ├── Chutes key create / rotate / revoke (live relay = PG-PROVIDER)
                ├── Stripe refund / cancel / portal (live = PG-STRIPE)
                └── Pod migration capture/materialize/verify/rollback (reprovision)
                │
                ├── Fleet placement (arclink_fleet, arclink_deployment_placements)
                ├── Queued admin/operator action intents (arclink_action_worker
                │     drains arclink_action_intents; the enrollment-provisioner
                │     root loop drains operator_actions)
                └── ArcPod-update rollout waves (arclink_rollout / arclink_rollouts)
                │
                ▼
         Runtime ArcPod (Hermes Agent)
                │
                ├── LLM router relay + sanitized usage (arclink_llm_usage_events,
                │     arclink_llm_budget_reservations, arclink_model_catalog)
                ├── Crew Training / SOUL overlay (arclink_crew_recipes)
                ├── Academy Mode (academy_* tables — NOT arclink_-prefixed)
                ├── Sharing: share grants / claim nonces / Linked resources /
                │     Fleet shared folder (arclink_share_grants,
                │     arclink_share_claim_nonces, arclink_fleet_shares,
                │     arclink_fleet_share_members)
                ├── Pod Comms — Agent-to-Agent messaging (arclink_pod_messages)
                └── ArcLink Wrapped reports (arclink_wrapped_reports)
                │
                ▼
         Dashboard reads (Captain / admin)
         Admin + Operator Raven action intents (queued, audited, approval-gated)
         Scale operations snapshot (admin only)
```

The control plane uses **45** `arclink_*` tables plus **10** non-prefixed
`academy_*` tables: `academy_programs`, `academy_trainees`,
`academy_mode_sessions`, `academy_resource_proposals`, `academy_sources`,
`academy_corpus_specialists`, `academy_specialist_sources`,
`academy_source_provenance`, `academy_specialist_subscriptions`, and
`academy_source_crawl_observations`. The
remaining live-schema tables are legacy/substrate (e.g. `rate_limits`,
`notification_outbox`, `operator_actions`). `arclink_evidence_runs` is now
written by the live runner when `ARCLINK_DB_PATH` is configured, and the operator
snapshot reads both the latest run and an evidence-governance rollup across the
required `hosted`, `workspace`, `external`, and `router` journeys. This is
source/local-real governance, not live production proof; `GAP-001` remains open
until the required credentialed journeys pass and their redacted evidence is
stored.

## Hosted API Boundary

The production API boundary is `arclink_hosted_api.py`, a WSGI app dispatching
all routes from a single `_ROUTES` table under the prefix `/api/v1`. The route
catalog is large and changes frequently, so it is **not duplicated here** — the
authoritative, always-current catalog is:

- `docs/API_REFERENCE.md` — the human-readable route table (auth, CORS, body
  caps, rate limits, env vars, prices, broker token).
- `docs/openapi/arclink-v1.openapi.json` — the machine-readable OpenAPI 3.1 spec,
  generated from `_ROUTES` by `build_arclink_openapi_spec()` and kept
  content-equivalent to code by a canonical JSON parity test (regenerate on any
  `_ROUTES` change).

At a high level the boundary exposes these route families:

| Family | Auth boundary | Purpose |
| --- | --- | --- |
| Public onboarding (`/onboarding/*`) | None / signed public-bot token | Start/answer/checkout/status/claim/cancel and the public-bot direct-checkout redirect |
| Webhooks (`/webhooks/{stripe,telegram,discord}`) | Provider signature / secret-token | Stripe entitlement webhook, Telegram secret-token header, Discord Ed25519 |
| Fleet enrollment (`/fleet/enrollment/callback`) | Bearer enrollment token | Worker enrollment attestation callback |
| Auth (`/auth/*`) | None to mint; CSRF to revoke | User/admin login (CIDR-gated admin) + logout |
| Captain session (`/user/*`) | User session + CSRF on mutations | Dashboard, billing, portal, refuel-checkout, provisioning, credentials, wrapped, crew-recipe, academy, share-grants, linked-resources, provider-state, Pod Comms |
| Admin session (`/admin/*`) | Admin session + CIDR + CSRF on mutations | Dashboard, service-health, provisioning-jobs, dns-drift, audit, events, actions, reconciliation, provider-state, operator-snapshot, scale-operations, wrapped, Pod Comms |
| Service (`/health`, `/openapi.json`, `/adapter-mode`) | None | Liveness, OpenAPI spec, adapter-mode flags |

Auth, session/CSRF (double-submit), HMAC-peppered token hashing, admin RBAC +
TOTP-MFA gates, the CIDR gate on all admin routes, rate limits, body caps, CORS,
and the deployment-scoped `X-ArcLink-Share-Request-Broker-Token` scheme are
documented with exact values in `docs/API_REFERENCE.md`.

The LLM router (`GET /v1/models`, `POST /v1/chat/completions`) is served by
`arclink_llm_router.py`, NOT by this WSGI `_ROUTES` table; OpenAPI documents both.

## Integration Boundaries

### ArcLink Substrate

ArcLink reuses Docker Compose orchestration, Hermes runtime, qmd retrieval,
vault watching, memory synthesis, Nextcloud, dashboard plugins, Raven bridges,
notification delivery, and health monitoring. These services run inside the
Control Node and per-deployment containers rendered by the provisioning layer.

### Hermes Workspace Plugins

ArcLink adds dashboard workspaces through Hermes plugins rather than Hermes
core patches:

- `drive` owns the native file-manager surface. It prefers a mounted
  local vault, can use sanitized Nextcloud WebDAV access state when available,
  and exposes browse, bounded preview, download, upload, folder creation,
  rename, move, trash, and restore contracts for writable roots. It also exposes
  a `Linked` root when the linked-resource projection exists. Accepted shared
  folders can be listed, searched, previewed, downloaded, uploaded to, renamed,
  moved, deleted, restored, and copied or duplicated into an owned Vault or
  Workspace destination while the Linked root itself stays system-managed.
  Linked resources cannot be reshared from the plugin.
  The local backend keeps trash recoverable under `.drive-trash`; WebDAV delete
  is direct provider delete and must remain UI-confirmed.
- `code` owns the native code workspace. It uses
  `CODE_WORKSPACE_ROOT`, guards text saves with a SHA-256 expected hash,
  scans bounded workspace depth for git repositories, and exposes source
  control status, stage, unstage, confirmed discard, and commit operations on
  writable Workspace/Fleet roots. Its `Linked` root allows file reads, saves
  inside accepted shared folders, previews, duplicate/copy into owned roots,
  repository discovery, git status, and git diff, while rejecting reshare and
  git mutations. It remains a
  lightweight native editor, not a full Monaco/VS Code workbench.
- `terminal` owns the native terminal surface. It uses a managed pty backend
  with stable session ids, persisted metadata,
  bounded scrollback, same-origin SSE output streaming with polling fallback,
  input, rename/folder/reorder controls, confirmation-gated close, sanitized
  errors, and an unrestricted-root startup guard. It is not tmux-backed.

`bin/install-arclink-plugins.sh` installs Drive, Code, Terminal, and managed
context by default, removes legacy dashboard plugin aliases, and enables the
plugins in the target Hermes config. It also removes Drive, Code, and Terminal
from `dashboard.hidden_plugins` so a stale user-hidden state cannot suppress
the left-sidebar entries after refresh. Docker reconcile/health paths repair
Hermes Dashboard mounts and rerun the managed plugin installer for existing
deployment stacks before recreating `hermes-dashboard`.

The rationale is to keep ArcLink-specific workspace behavior additive and
replaceable. Hermes owns the dashboard plugin host; ArcLink owns the plugin
files, allowed-root policy, secret redaction, and Docker mount wiring.

### LLM Router

`python/arclink_llm_router.py` is the source-level Control Node router for
OpenAI-compatible ArcPod inference. It exposes `GET /v1/models` and
`POST /v1/chat/completions`, verifies a per-deployment ArcLink router key,
enforces billing, budget, model, body-size, rate, and concurrency policy, relays
to Chutes with the central server-side credential, streams responses without
buffering completions, and records sanitized usage without prompts or
completions.

The router also refreshes the Chutes model catalog into
`arclink_model_catalog`, stores provider pricing, and resolves old/deprecated
same-family requests to the current active upstream model when auto-promotion is
enabled. That gives the Control Node one fleet-wide place to move Captains from
Kimi K2.6 to Kimi K2.7-style replacements without rewriting every ArcPod first.

The router is separate from the WSGI hosted API and is not part of the
`/api/v1` route catalog. Current source behavior is documented in
`docs/arclink/llm-router.md`. Compose service wiring and ArcPod provisioning
defaults are source-level behavior; live Chutes proof remains explicitly
operator-gated.

### External Providers (gated behind executor)

- **Stripe**: checkout, webhooks, subscription lifecycle, refunds, portal.
- **Ingress**: Cloudflare DNS/Access in domain mode; Tailscale publication and
  direct SSH in Tailscale mode.
- **Chutes**: model catalog, direct-provider compatibility, and the upstream
  provider behind the ArcLink LLM Router. The `arclink_chutes_live` and
  `arclink_chutes_oauth` adapters exist but are **TEST-ONLY and UNWIRED**; the
  `per_user_chutes_account_oauth` lane is a posture/label only.
- **Telegram/Discord**: not a skeleton — `arclink_public_bots.py` is a full Raven
  turn engine (`handle_arclink_public_bot_turn`) covering commands, routing law,
  onboarding/checkout, channel pairing, the selected-agent bridge, Crew Training,
  Academy Mode, share approve/deny/accept/claim, credentials, retire-agent, and
  refuel. Telegram preserves native update JSON plus callback family metadata and
  splits outbound long text into bounded batches. Discord supports interaction
  webhooks, a local Gateway free-text handler, components, embeds, and attachment
  metadata with default-deny mentions. The Telegram/Discord transports run in
  fake mode without tokens; ALL live delivery (webhooks, command menus, buttons,
  Gateway free text, media/components, the selected-agent bridge) is proof-gated
  behind PG-BOTS (and PG-HERMES for per-agent scope).

All provider interactions use fake adapters by default. Live adapters require
explicit `live_enabled=True` and injected credentials, and remain proof-gated
behind the relevant `PG-*` gate until operator-authorized live proof exists.

### Secret Handling

- Secrets are represented as `secret://arclink/<scope>/<id>` references.
- Compose secrets resolve to `/run/secrets/...` file targets.
- Stock images use `_FILE` environment variables where supported.
- Plaintext secret values are rejected in persisted intent and executor results.
- Dashboard and API responses never include raw secret material.

### Public Agent Gateway

When a Captain talks to one of their Agents over a public channel, Raven bridges
the turn into the Agent's own Hermes gateway pipeline:

- `arclink_public_agent_bridge.py` is a short-lived boundary process run INSIDE a
  Hermes gateway container. It replays a public Telegram raw update through
  Hermes' own native gateway handlers (Discord goes through REST shims, not native
  parity), maintains a durable `ea:` exec-approval mapping on disk, carries
  callback-family metadata for `ea`/`mp`/`sc`/`cl`, supports Discord
  component/embed/attachment metadata on outbound sends, and streams by default.
  Selected-agent bridge delivery is async; streaming is opt-in via
  `ARCLINK_PUBLIC_AGENT_BRIDGE_STREAMING=1` (GAP-023).
- The per-turn `docker exec` into the gateway container is mediated by the
  `gateway-exec-broker` (see Trusted-Host Brokers below) — Raven never holds
  Docker authority directly.

Real bridge delivery requires a live gateway container, a bot token, and a Hermes
runtime, and is proof-gated behind PG-BOTS / PG-HERMES.

The full bridge/broker design (per-turn invocation, native-handler replay, the
durable `ea:` exec-approval mapping, callback-family replay proof boundary, and
the complete service/port/header/socket table) lives in
`docs/arclink/public-agent-gateway.md`; the sections below are a summary that
cross-links to it rather than duplicating it.

### Trusted-Host Brokers & Helpers

The Docker-socket and root-privileged authority needed for provisioning, the
public-agent bridge, the dashboard sidecar, migration capture, and host upgrades
is factored into seven single-purpose trusted-host services. Each rejects raw
commands, requires an HMAC token, runs on an internal network, validates
paths/symlinks, pins trusted Docker binaries where applicable, and emits redacted
rejection incidents (`arclink_rejection_incidents.py`). The whole family is
Docker-mode + trusted-host gated and only starts when
`ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED=accepted`.

| Service | Module | Port | Token env | Docker socket | Root |
| --- | --- | --- | --- | --- | --- |
| gateway-exec-broker | `arclink_gateway_exec_broker` | 8911 | `ARCLINK_GATEWAY_EXEC_BROKER_TOKEN` | yes | no |
| deployment-exec-broker | `arclink_deployment_exec_broker` | 8912 | `ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN` | yes | no |
| agent-supervisor-broker | `arclink_agent_supervisor_broker` | 8913 | `ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN` | yes | no |
| migration-capture-helper | `arclink_migration_capture_helper` | 8914 | `ARCLINK_MIGRATION_CAPTURE_HELPER_TOKEN` | no | yes |
| agent-user-helper | `arclink_agent_user_helper` | 8915 | `ARCLINK_AGENT_USER_HELPER_TOKEN` | no | yes (caps) |
| agent-process-helper | `arclink_agent_process_helper` | 8916 | `ARCLINK_AGENT_PROCESS_HELPER_TOKEN` | no | yes (setpriv) |
| operator-upgrade-broker | `arclink_operator_upgrade_broker` | 8917 | `ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN` | no | yes |

`arclink_docker_agent_supervisor.py` is a root reconciliation loop that holds NO
Docker socket and drives the helper family.

This is a **policy/risk-accepted (not tenant-safe)** boundary: each socket broker
still owns a writeable Docker socket and each root helper still runs as root.
**GAP-019 is OPEN and acknowledged-only.** The authoritative trust-boundary
inventory and operator guidance live in the GAP-019 entries of
`docs/arclink/operations-runbook.md`; the full broker/helper design (including the
per-service `X-ArcLink-*` header map) lives in
`docs/arclink/public-agent-gateway.md`. This section is a summary, not a
replacement for either.

### Pod Comms

`arclink_pod_comms.py` provides Agent-to-Agent messaging over
`arclink_pod_messages`, surfaced at `GET /user/comms` and `GET /admin/comms`
(and the `pod_comms.*` MCP tools). Same-Captain messaging is allowed; cross-
Captain messaging requires an accepted `pod_comms` share grant. Attachments are
projection references only. Cross-Pod **delivery** and operator redaction
(`mark_pod_message_delivered` / `redact_pod_message`) have no production callers
yet — the store/list rails are local-real but live delivery is unwired.

## Scale Operations Spine

ArcLink now has a SQLite-first operator spine for growth beyond one manually
managed deployment:

- `arclink_fleet.py` owns fleet host registration, health/drain status,
  capacity slots, observed load, and deterministic placement. Placement prefers
  active, non-draining hosts with the most headroom and breaks ties by hostname.
  Inventory machines and fleet hosts stay separate registries; orphan
  reconciliation audits missing links but does not repair or delete rows.
- `arclink_action_worker.py` owns execution of queued admin actions. It records
  attempts, resolves a deployment target to its latest active placement,
  constructs or reuses the selected host executor, updates intent status,
  writes events/audit rows with routing metadata, redacts executor errors,
  links each dispatched executor operation in `arclink_action_operation_links`,
  and can return stale running actions to the queue.
- `arclink_executor.py` owns the shared `fake`, `local`, and `ssh` executor
  construction used by the provisioner and action worker. SSH execution is
  explicitly gated by machine-mode enablement, host allow-listing, and private
  key file permission checks.
- `arclink_rollout.py` owns durable rollout records. Rollouts advance in
  canary waves, can pause/fail/rollback, and rollback plans must include
  `preserve_state_roots`.
- `build_scale_operations_snapshot()` and
  `GET /api/v1/admin/scale-operations` expose fleet capacity, placements,
  stale queued/running actions, recent worker attempts, active rollouts, and
  the last executor result behind admin session auth.
- Two distinct action queues feed the spine: `arclink_action_intents` (drained
  by `arclink_action_worker`) and `operator_actions` (a substrate table drained
  by the `arclink_enrollment_provisioner` root maintenance loop). The chat-native
  `arclink_operator_raven` console queues real, audited, identity-gated,
  approval-code-gated mutations through these queues; the Operator also gets a
  single in-stack Hermes agent (`arclink_operator_agent`, one-agent invariant)
  with a free-form chat bridge. Live mutation effect is gated by
  `ARCLINK_EXECUTOR_ADAPTER` and the relevant `PG-*` gate; the ArcPod-update
  rollout path is `wired`/queueable in `ARCLINK_ADMIN_ACTION_SUPPORT` but has no
  real per-Pod refresh/apply yet (GAP-032, PG-UPGRADE/PG-HERMES).

The rationale is to keep operational ownership inside the existing ArcLink
control plane until credentialed live proof shows a need for an external queue
or scheduler. The worker still respects the executor's fake-by-default,
live-gated behavior.

## Isolation Model

- **Compute**: dedicated Docker Compose project per deployment.
- **Storage**: dedicated Nextcloud instance, DB, and Redis per deployment.
- **Network**: Traefik labels with per-deployment hostnames or Tailscale path
  routes. In Tailscale path mode, Docker health can publish per-deployment
  Hermes, files, and code apps on stable tailnet HTTPS ports and persist those
  URLs in deployment metadata.
- **SSH**: Cloudflare Access TCP in domain mode or direct Tailscale SSH in
  Tailscale mode; no raw SSH over HTTP.
- **Secrets**: per-deployment secret references; no shared credentials.

## Current Limitations

- Executor is fail-closed; no production live adapters are shipped yet.
- Admin dashboard is wired to all hosted API admin endpoints. User dashboard
  wiring covers dashboard, billing, provisioning, credentials, linked-resource,
  and provider-state reads, plus credential acknowledgement; broader share
  create/approve/accept/revoke UI remains intentionally deferred.
- Scale operations are durable and API-visible, but no long-running production
  worker service unit is documented as live yet. Operators should treat worker
  execution as a controlled runbook step until live host orchestration lands.
- Public bots are a full Raven turn engine, not a skeleton. The Telegram/Discord
  transports run in fake mode without tokens; live HTTP transport, webhooks,
  command menus, buttons, Gateway free text, Discord media/components, Telegram
  long-text batching, callback replay, and the selected-agent bridge are
  proof-gated behind PG-BOTS (and PG-HERMES for per-agent command scope).
- Drive and Code are functional first-generation Hermes plugins, but
  not yet broad Google Drive or VS Code replacements. Terminal has a
  managed-pty persistent-session backend with same-origin SSE output streaming
  and bounded polling fallback. The
  workspace Docker/TLS proof runner has passed desktop and mobile checks for
  Drive, Code, and Terminal; this is separate from the broader hosted customer
  live journey.
- Live E2E scaffold exists (`tests/test_arclink_e2e_live.py`) with
  Stripe, selected ingress mode, Chutes, Telegram, Discord, and read-only Docker checks,
  but full live proof skips until credentials and explicit live flags are
  available. See `docs/arclink/live-e2e-secrets-needed.md`.
- External credential sets remain absent (Stripe, Chutes, Telegram, Discord,
  host, and selected Cloudflare-domain or Tailscale ingress mode). The live
  hosted customer journey is proof-gated (PG-PROD) and blocked on these; no live
  external transaction has been proven.
- Operator Raven is NOT read-only/dry-run: it queues real, audited,
  identity-gated, approval-code-gated mutations (`pod_repair`, `rollout`,
  `host_upgrade`, `pin_upgrade`) alongside a broad read surface, with live
  effect still gated by `ARCLINK_EXECUTOR_ADAPTER` and the relevant `PG-*` gate.
- `arclink_evidence_runs` is implemented, tested, written by the live runner when
  `ARCLINK_DB_PATH` is configured, and read by the operator snapshot for latest
  run plus governance status. This improves reconciliation discipline but does
  not by itself close PG-PROD or prove any live journey.
