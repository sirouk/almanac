# ArcLink Architecture

ArcLink is a self-serve AI deployment SaaS built as an additive layer on top of
the Almanac shared-host substrate. This document describes the current module
map, data flow, and integration boundaries.

## Module Map

```text
arclink_product.py          Config resolution, ARCLINK_*/ALMANAC_* precedence
arclink_chutes.py           Chutes catalog client, model discovery
arclink_adapters.py         Fake/live adapter registry (Stripe, Cloudflare, Chutes, bots)
arclink_entitlements.py     Stripe webhook verification, entitlement state machine, comp helpers
arclink_onboarding.py       Public onboarding sessions and funnel events (web, Telegram, Discord)
arclink_ingress.py          Hostname generation, DNS drift detection, Traefik label intent
arclink_access.py           Nextcloud isolation model, SSH access strategy guards
arclink_provisioning.py     Dry-run provisioning renderer, job state, rollback planning
arclink_executor.py         Guarded mutating boundary (Docker, Cloudflare, Chutes, Stripe, rollback)
arclink_dashboard.py        User/admin dashboard read models, queued admin action intent
arclink_api_auth.py         Hashed session/CSRF tokens, rate limits, MFA-ready admin gates
arclink_hosted_api.py       Production WSGI app, /api/v1 route dispatch, CORS, cookie transport
arclink_product_surface.py  Local no-secret WSGI prototype for development/contract testing
arclink_public_bots.py      Telegram/Discord public onboarding bot conversation skeletons
```

All modules live under `python/` and import from `almanac_control.py` for
database access (18 `arclink_*` tables in the shared SQLite/Postgres schema).

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
                ▼
         Dashboard reads (user / admin)
         Admin action intents (queued, audited)
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
| `POST /admin/sessions/revoke` | Admin + CSRF | Revoke admin session |

## Integration Boundaries

### Almanac Substrate (existing, unchanged)

ArcLink reuses Almanac's Docker Compose orchestration, Hermes runtime, qmd
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

## Isolation Model

- **Compute**: dedicated Docker Compose project per deployment.
- **Storage**: dedicated Nextcloud instance, DB, and Redis per deployment.
- **Network**: Traefik labels with per-deployment hostnames.
- **SSH**: Cloudflare Access TCP only; no raw SSH over HTTP.
- **Secrets**: per-deployment secret references; no shared credentials.

## Current Limitations

- Executor is fail-closed; no production live adapters are shipped yet.
- Frontend dashboard (Next.js/Tailwind) is planned but not implemented.
- Public bots are conversation skeletons, not running clients.
- Live E2E testing requires credentials listed in
  `docs/arclink/live-e2e-secrets-needed.md`.
