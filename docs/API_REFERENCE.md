# ArcLink Hosted API Reference

- Version: v1
- Prefix: `/api/v1`
- Transport: WSGI (Python), JSON request/response
- Auth: Cookie-based session (HttpOnly, Secure, SameSite=Lax) + CSRF header on mutations

## Authentication

Sessions are issued via `/auth/admin/login` and `/auth/user/login`. Credentials are delivered as cookies (`arclink_{kind}_session_id`, `arclink_{kind}_session_token`, `arclink_{kind}_csrf`). Mutations require `X-ArcLink-CSRF-Token` header matching the session.

### Headers

| Header | Purpose |
|--------|---------|
| `X-ArcLink-Session-Id` | Session identifier (fallback if cookies unavailable) |
| `X-ArcLink-Session-Token` | Session secret |
| `X-ArcLink-CSRF-Token` | CSRF token for POST mutations |
| `X-ArcLink-Request-Id` | Client-supplied request ID (echoed in response; auto-generated if absent) |

## Rate Limiting

Rate limits are enforced per-scope using a sliding window stored in the `rate_limits` SQLite table.

| Scope | Limit | Window |
|-------|-------|--------|
| `admin_login` | 5 requests | 15 min |
| `user_login` | 10 requests | 15 min |
| `onboarding:{channel}` | 5 requests | 15 min |
| `public_bot:{channel}` | via `check_arclink_rate_limit` | configurable |

When exceeded, the API returns `429` with `{"error": "ArcLink rate limit exceeded"}`, `Retry-After`, and `X-RateLimit-*` headers.

## CORS

Configured via `ARCLINK_CORS_ORIGIN` env var. Preflight (`OPTIONS`) returns 204 with:
- `Access-Control-Allow-Methods: GET, POST, OPTIONS`
- `Access-Control-Allow-Credentials: true`
- `Access-Control-Max-Age: 86400`

## Routes

### Public (no session required)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/onboarding/start` | Begin onboarding flow |
| POST | `/onboarding/answer` | Answer onboarding question |
| POST | `/onboarding/checkout` | Open Stripe checkout |
| POST | `/webhooks/stripe` | Stripe webhook receiver |
| POST | `/webhooks/telegram` | Telegram Bot API webhook |
| POST | `/webhooks/discord` | Discord interaction webhook |
| POST | `/auth/admin/login` | Create admin session |
| POST | `/auth/user/login` | Create user session |
| GET | `/health` | Liveness check (DB connectivity) |

### User (session_kind=user)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/user/logout` | Revoke user session (CSRF) |
| GET | `/user/dashboard` | User deployment overview |
| GET | `/user/billing` | Billing/entitlement status |
| POST | `/user/portal` | Create Stripe portal link (CSRF) |
| GET | `/user/provisioning` | Deployment provisioning status |
| GET | `/user/provider-state` | Provider adapter state |

### Admin (session_kind=admin)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/admin/logout` | Revoke admin session (CSRF) |
| GET | `/admin/dashboard` | Platform overview (filters: channel, status, deployment_id, user_id, since) |
| GET | `/admin/service-health` | Service health (filters: deployment_id, status, since) |
| GET | `/admin/provisioning-jobs` | Provisioning jobs (filters: deployment_id, status, since) |
| GET | `/admin/dns-drift` | DNS drift observations (filters: deployment_id, since) |
| GET | `/admin/audit` | Audit log (filters: deployment_id, since) |
| GET | `/admin/events` | Event log (filters: deployment_id, since) |
| GET | `/admin/actions` | Queued actions (filters: deployment_id, status, since) |
| POST | `/admin/actions` | Queue admin action (CSRF) |
| GET | `/admin/reconciliation` | Reconciliation drift summary |
| GET | `/admin/operator-snapshot` | Operator snapshot (host readiness, diagnostics, journey blockers, evidence status) |
| GET | `/admin/provider-state` | Provider adapter state |
| POST | `/admin/sessions/revoke` | Revoke any session (CSRF) |

## Error Responses

All errors return JSON with `error` and `request_id` fields:

```json
{"error": "not_found", "request_id": "req_abc123"}
```

| Status | Meaning |
|--------|---------|
| 400 | Bad request / generic error |
| 401 | Auth failure |
| 429 | Rate limit exceeded |
| 404 | Route not found |
| 503 | Health check degraded (DB unreachable) |

## Configuration (Environment Variables)

| Variable | Default | Purpose |
|----------|---------|---------|
| `ARCLINK_CORS_ORIGIN` | (none) | Allowed CORS origin |
| `ARCLINK_COOKIE_DOMAIN` | (none) | Cookie Domain attribute |
| `ARCLINK_COOKIE_SECURE` | `1` | Set Secure flag on cookies |
| `STRIPE_WEBHOOK_SECRET` | (none) | Stripe signature verification |
| `ARCLINK_LOG_LEVEL` | `INFO` | Logging verbosity |
| `ARCLINK_DEFAULT_PRICE_ID` | `price_arclink_starter` | Backward-compatible first-agent Stripe price |
| `ARCLINK_FIRST_AGENT_PRICE_ID` | `price_arclink_starter` | First Raven agent Stripe price ($35/month target) |
| `ARCLINK_ADDITIONAL_AGENT_PRICE_ID` | `price_arclink_additional_agent` | Additional Raven agent Stripe price ($15/month target) |

## Web Client Integration

The Next.js admin dashboard (`web/src/app/admin/page.tsx`) is wired to the hosted API via `web/src/lib/api.ts`. All admin endpoints are consumed:

| Admin Tab | API Endpoint | Method |
|-----------|-------------|--------|
| overview, users, deployments, onboarding, payments, infrastructure, bots, security, releases, sessions | `/admin/dashboard` | GET |
| health | `/admin/service-health` | GET |
| provisioning | `/admin/provisioning-jobs` | GET |
| dns | `/admin/dns-drift` | GET |
| audit | `/admin/audit` | GET |
| events | `/admin/events` | GET |
| actions (read) | `/admin/actions` | GET |
| actions (queue) | `/admin/actions` | POST |
| provider | `/admin/provider-state` | GET |
| reconciliation | `/admin/reconciliation` | GET |
| operator | `/admin/operator-snapshot` | GET |
| sessions (revoke) | `/admin/sessions/revoke` | POST |

The user dashboard (`web/src/app/dashboard/page.tsx`) consumes `/user/dashboard`, `/user/billing`, `/user/provisioning`, and `/user/provider-state`.

## Assumptions and Ownership

- **Owner**: ArcLink control-plane team
- **Database**: Single SQLite file (Postgres path planned but not active)
- **Session storage**: `sessions` table in same DB; no external session store
- **Rate limit storage**: `rate_limits` table; no Redis dependency
- **Stripe client**: Defaults to `FakeStripeClient` when no live key configured
- **Bot adapters**: Telegram/Discord webhooks use fake-mode adapters by default
