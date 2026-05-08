# ArcLink Architecture

ArcLink is a self-serve AI deployment SaaS built as an additive layer on top of
the shared-host substrate. This document describes the current module
map, data flow, and integration boundaries.

## Module Map

```text
arclink_product.py          Config resolution, ARCLINK_*/ARCLINK_* precedence
arclink_chutes.py           Chutes catalog client, model discovery
arclink_adapters.py         Fake/live adapter registry (Stripe, ingress, Chutes, bots)
arclink_entitlements.py     Stripe webhook verification, entitlement state machine, comp helpers
arclink_onboarding.py       Public onboarding sessions and funnel events (web, Telegram, Discord)
arclink_ingress.py          Hostname generation, DNS drift detection, Traefik label intent
arclink_access.py           Nextcloud isolation model, SSH access strategy guards
arclink_provisioning.py     Dry-run provisioning renderer, job state, rollback planning
arclink_executor.py         Guarded mutating boundary (Docker, ingress, Chutes, Stripe, rollback)
arclink_fleet.py            Fleet host registry, deterministic placement, capacity summaries
arclink_action_worker.py    Queued admin action execution, attempts, stale recovery
arclink_rollout.py          Durable rollout waves, pause/fail/rollback records, version drift
arclink_dashboard.py        User/admin dashboard read models, queued admin action intent
arclink_api_auth.py         Hashed session/CSRF tokens, rate limits, MFA-ready admin gates
arclink_hosted_api.py       Production WSGI app, /api/v1 route dispatch, CORS, cookie transport
arclink_product_surface.py  Local no-secret WSGI prototype for development/contract testing
arclink_public_bots.py      Telegram/Discord public onboarding bot conversation skeletons
arclink_telegram.py         Telegram runtime adapter, long-polling bot runner, fake mode
arclink_discord.py          Discord runtime adapter, interaction handler, fake mode
arclink_boundary.py         Shared rowdict helper for API/dashboard boundary
arclink_host_readiness.py   Pre-deployment host checks (Docker, env, ports, state root)
arclink_diagnostics.py      Secret-safe provider credential diagnostics
arclink_live_runner.py      Live proof runner orchestrating readiness, diagnostics, journey, evidence
arclink_live_journey.py     Ordered live E2E journey steps (credential-gated)
arclink_evidence.py         Evidence collection and template helpers for live proof
plugins/hermes-agent/
  arclink-managed-context/  Managed agent context and ArcLink MCP bootstrap injection
  drive/            Hermes dashboard file manager for vault/workspace access
  code/             Hermes dashboard native code workspace and git surface
  terminal/         Managed-pty persistent-session terminal surface
```

Python modules live under `python/` and import from `arclink_control.py` for
database access through ArcLink-owned `arclink_*` tables in the shared
SQLite/Postgres schema.
Hermes dashboard plugins live under `plugins/hermes-agent/` and are installed
into each target Hermes home by ArcLink wrapper scripts.

## Data Flow

```text
Customer ──► Public Onboarding (web / Telegram / Discord)
                │
                ▼
         arclink_onboarding_sessions
         arclink_onboarding_events
                │
                ▼
         Stripe Checkout (fake in dev, live in production)
                │
                ▼
         Stripe Webhook ──► arclink_entitlements
                │               │
                ▼               ▼
         arclink_users      arclink_subscriptions
         (entitlement)      (mirror)
                │
                ▼
         arclink_provisioning (dry-run intent)
                │
                ├── Docker Compose services
                ├── Domain/Tailscale ingress and SSH intent
                ├── Chutes key lifecycle intent
                ├── Traefik labels and ingress
                ├── State roots, workspace mounts, and secret references
                ├── Dashboard plugin environment for Drive, Code, Terminal
                └── Service-health placeholders
                │
                ▼
         arclink_executor (guarded, fail-closed)
                │
                ├── Docker Compose apply
                ├── Domain/Tailscale ingress apply
                ├── Chutes key create / rotate / revoke
                ├── Stripe refund / cancel / portal
                └── Rollback apply
                │
                ├── Fleet placement (`arclink_fleet`)
                ├── Queued admin action attempts (`arclink_action_worker`)
                └── Release waves / rollback records (`arclink_rollout`)
                │
                ▼
         Dashboard reads (user / admin)
         Admin action intents (queued, audited)
         Scale operations snapshot (admin only)
```

## Hosted API Routes

The production API boundary is `arclink_hosted_api.py`, dispatching under
`/api/v1`:

| Route | Auth | Purpose |
| --- | --- | --- |
| `POST /onboarding/start` | None | Start or resume public onboarding |
| `POST /onboarding/answer` | None | Record onboarding answer |
| `POST /onboarding/checkout` | None | Create Stripe checkout session |
| `POST /webhooks/stripe` | Stripe signature | Entitlement webhook processing |
| `POST /webhooks/telegram` | None | Telegram Bot API webhook |
| `POST /webhooks/discord` | None | Discord interaction webhook |
| `POST /auth/admin/login` | None | Admin session creation, sets cookies |
| `POST /auth/user/login` | None | User session creation, sets cookies |
| `POST /auth/user/logout` | User + CSRF | Revoke user session |
| `POST /auth/admin/logout` | Admin + CSRF | Revoke admin session |
| `GET /user/dashboard` | User session | User dashboard read |
| `GET /user/billing` | User session | Billing/entitlement status |
| `POST /user/portal` | User + CSRF | Create Stripe portal link |
| `GET /user/provisioning` | User session | Deployment provisioning status |
| `GET /user/provider-state` | User session | Provider adapter state |
| `GET /admin/dashboard` | Admin session | Admin dashboard read |
| `GET /admin/service-health` | Admin session | Service health |
| `GET /admin/provisioning-jobs` | Admin session | Provisioning jobs |
| `GET /admin/dns-drift` | Admin session | DNS drift observations |
| `GET /admin/audit` | Admin session | Audit log |
| `GET /admin/events` | Admin session | Event log |
| `GET /admin/actions` | Admin session | Queued actions |
| `POST /admin/actions` | Admin + CSRF | Queue admin action intent |
| `GET /admin/reconciliation` | Admin session | Reconciliation drift summary |
| `GET /admin/provider-state` | Admin session | Provider adapter state |
| `GET /admin/operator-snapshot` | Admin session | Host readiness, diagnostics, journey blockers |
| `GET /admin/scale-operations` | Admin session | Fleet, placement, action-worker, rollout snapshot |
| `POST /admin/sessions/revoke` | Admin + CSRF | Revoke any session |
| `GET /health` | None | Liveness check (DB connectivity) |
| `GET /openapi.json` | None | OpenAPI 3.1 spec |

## Integration Boundaries

### ArcLink Substrate (existing, unchanged)

ArcLink reuses the shared-host Docker Compose orchestration, Hermes runtime, qmd
retrieval, vault watching, memory synthesis, Nextcloud, dashboard plugins, Curator,
notification delivery, and health monitoring. These services run inside
per-deployment containers rendered by the ArcLink provisioning layer.

### Hermes Workspace Plugins

ArcLink adds dashboard workspaces through Hermes plugins rather than Hermes
core patches:

- `drive` owns the native file-manager surface. It prefers a mounted
  local vault, can use sanitized Nextcloud WebDAV access state when available,
  and exposes browse, bounded preview, download, upload, folder creation,
  rename, move, trash, and restore contracts. The local backend keeps
  trash recoverable under `.drive-trash`; WebDAV delete is direct provider
  delete and must remain UI-confirmed.
- `code` owns the native code workspace. It uses
  `CODE_WORKSPACE_ROOT`, guards text saves with a SHA-256 expected hash,
  scans bounded workspace depth for git repositories, and exposes source
  control status, stage, unstage, confirmed discard, and commit operations. It
  remains a lightweight native editor, not a full Monaco/VS Code workbench.
- `terminal` owns the native terminal surface. It uses a managed pty backend
  with stable session ids, persisted metadata,
  bounded scrollback, same-origin SSE output streaming with polling fallback,
  input, rename/folder/reorder controls, confirmation-gated close, sanitized
  errors, and an unrestricted-root startup guard. It is not tmux-backed.

`bin/install-arclink-plugins.sh` installs Drive, Code, Terminal, and managed
context by default, removes legacy dashboard plugin aliases, and enables the
plugins in the target Hermes config. Docker reconcile/health paths repair
Hermes dashboard mounts and rerun the managed plugin installer for existing
deployment stacks before recreating `hermes-dashboard`.

The rationale is to keep ArcLink-specific workspace behavior additive and
replaceable. Hermes owns the dashboard plugin host; ArcLink owns the plugin
files, allowed-root policy, secret redaction, and Docker mount wiring.

### External Providers (gated behind executor)

- **Stripe**: checkout, webhooks, subscription lifecycle, refunds, portal.
- **Ingress**: Cloudflare DNS/Access in domain mode; Tailscale publication and
  direct SSH in Tailscale mode.
- **Chutes**: per-deployment API key lifecycle, model catalog.
- **Telegram/Discord**: public onboarding bot clients (skeleton only today).

All provider interactions use fake adapters by default. Live adapters require
explicit `live_enabled=True` and injected credentials.

### Secret Handling

- Secrets are represented as `secret://arclink/<scope>/<id>` references.
- Compose secrets resolve to `/run/secrets/...` file targets.
- Stock images use `_FILE` environment variables where supported.
- Plaintext secret values are rejected in persisted intent and executor results.
- Dashboard and API responses never include raw secret material.

## Scale Operations Spine

ArcLink now has a SQLite-first operator spine for growth beyond one manually
managed deployment:

- `arclink_fleet.py` owns fleet host registration, health/drain status,
  capacity slots, observed load, and deterministic placement. Placement prefers
  active, non-draining hosts with the most headroom and breaks ties by hostname.
- `arclink_action_worker.py` owns execution of queued admin actions. It records
  attempts, updates intent status, writes events/audit rows, redacts executor
  errors, and can return stale running actions to the queue.
- `arclink_rollout.py` owns durable rollout records. Rollouts advance in
  canary waves, can pause/fail/rollback, and rollback plans must include
  `preserve_state_roots`.
- `build_scale_operations_snapshot()` and
  `GET /api/v1/admin/scale-operations` expose fleet capacity, placements,
  stale queued/running actions, recent worker attempts, active rollouts, and
  the last executor result behind admin session auth.

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
- Admin dashboard is wired to all hosted API admin endpoints; user dashboard
  live data wiring is deferred.
- Scale operations are durable and API-visible, but no long-running production
  worker service unit is documented as live yet. Operators should treat worker
  execution as a controlled runbook step until live host orchestration lands.
- Public bots have runtime adapters with fake-mode fallback; live HTTP
  transport requires bot tokens.
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
  host, and selected Cloudflare-domain or Tailscale ingress mode). Production
  12 live journey is blocked on these.
