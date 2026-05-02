# ArcLink Architecture

ArcLink is a self-serve AI deployment SaaS built as an additive layer on top of
the ArcLink shared-host substrate. This document describes the current module
map, data flow, and integration boundaries.

## Module Map

```text
arclink_product.py          Config resolution, ARCLINK_*/ARCLINK_* precedence
arclink_chutes.py           Chutes catalog client, model discovery
arclink_adapters.py         Fake/live adapter registry (Stripe, Cloudflare, Chutes, bots)
arclink_entitlements.py     Stripe webhook verification, entitlement state machine, comp helpers
arclink_onboarding.py       Public onboarding sessions and funnel events (web, Telegram, Discord)
arclink_ingress.py          Hostname generation, DNS drift detection, Traefik label intent
arclink_access.py           Nextcloud isolation model, SSH access strategy guards
arclink_provisioning.py     Dry-run provisioning renderer, job state, rollback planning
arclink_executor.py         Guarded mutating boundary (Docker, Cloudflare, Chutes, Stripe, rollback)
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
```

All modules live under `python/` and import from `arclink_control.py` for
database access (22 `arclink_*` tables in the shared SQLite/Postgres schema).

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
                ├── Cloudflare DNS / Access intent
                ├── Chutes key lifecycle intent
                ├── Traefik labels and ingress
                ├── State roots and secret references
                └── Service-health placeholders
                │
                ▼
         arclink_executor (guarded, fail-closed)
                │
                ├── Docker Compose apply
                ├── Cloudflare DNS / Access apply
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
| `POST /admin/login` | None | Admin session creation, sets cookies |
| `POST /stripe/webhook` | Stripe signature | Entitlement webhook processing |
| `GET /user/dashboard` | Session | User dashboard read |
| `GET /admin/dashboard` | Admin session | Admin dashboard read |
| `POST /admin/actions` | Admin + CSRF | Queue admin action intent |
| `GET /admin/scale-operations` | Admin session | Fleet, placement, action-worker, rollout snapshot |
| `POST /admin/sessions/revoke` | Admin + CSRF | Revoke admin session |

## Integration Boundaries

### ArcLink Substrate (existing, unchanged)

ArcLink reuses ArcLink's Docker Compose orchestration, Hermes runtime, qmd
retrieval, vault watching, memory synthesis, Nextcloud, code-server, Curator,
notification delivery, and health monitoring. These services run inside
per-deployment containers rendered by the ArcLink provisioning layer.

### External Providers (gated behind executor)

- **Stripe**: checkout, webhooks, subscription lifecycle, refunds, portal.
- **Cloudflare**: DNS records, tunnels, Access policies for TCP SSH.
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
- **Network**: Traefik labels with per-deployment hostnames.
- **SSH**: Cloudflare Access TCP only; no raw SSH over HTTP.
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
- Live E2E scaffold exists (`tests/test_arclink_e2e_live.py`) with
  Stripe, Cloudflare, Chutes, Telegram, Discord, and read-only Docker checks,
  but full live proof skips until credentials and explicit live flags are
  available. See `docs/arclink/live-e2e-secrets-needed.md`.
- All 6 external credential sets remain absent (Stripe, Cloudflare, Chutes,
  Telegram, Discord, host). Production 12 live journey is blocked on these.
