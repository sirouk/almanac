# ArcLink Hosted API Reference

- Version: v1
- Prefix: `/api/v1`
- Transport: WSGI (Python), JSON request/response
- Auth: Cookie-based session (HttpOnly, Secure, SameSite=Lax) + CSRF header on mutations

## Authentication

Sessions are issued via `/auth/admin/login` and `/auth/user/login`. Both routes require email plus password. Credentials are delivered as cookies (`arclink_{kind}_session_id`, `arclink_{kind}_session_token`, `arclink_{kind}_csrf`). Mutations require `X-ArcLink-CSRF-Token` header matching the session.

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
| POST | `/auth/user/login` | Create user session with email plus dashboard password |
| GET | `/health` | Liveness check (DB connectivity) |
| GET | `/openapi.json` | OpenAPI 3.1 spec (machine-readable route catalog) |

### User (session_kind=user)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/user/logout` | Revoke user session (CSRF) |
| GET | `/user/dashboard` | User deployment overview |
| GET | `/user/billing` | Billing/entitlement status plus the local renewal lifecycle gate |
| POST | `/user/portal` | Create Stripe portal link (CSRF) |
| GET | `/user/provisioning` | Deployment provisioning status |
| GET | `/user/credentials` | Pending credential handoff metadata; masked refs only |
| POST | `/user/credentials/acknowledge` | Confirm credential storage and remove future handoff visibility (CSRF) |
| POST | `/user/share-grants` | Request a read-only Drive/Code share grant (CSRF) |
| POST | `/user/share-grants/approve` | Owner-approve a pending share grant (CSRF) |
| POST | `/user/share-grants/deny` | Owner-deny a pending share grant (CSRF) |
| POST | `/user/share-grants/accept` | Recipient accepts an approved share grant (CSRF) |
| POST | `/user/share-grants/revoke` | Owner revokes a share grant and removes accepted linked-resource visibility (CSRF) |
| GET | `/user/linked-resources` | Accepted linked resources for the authenticated user |
| GET | `/user/provider-state` | Provider adapter state, including sanitized Chutes budget, credential, and billing-suspension boundary |

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
| GET | `/admin/provider-state` | Provider adapter state, including sanitized Chutes budget summaries |
| GET | `/admin/scale-operations` | Fleet capacity, placements, stale actions, rollouts, last executor result |
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
| `ARCLINK_DEFAULT_PRICE_ID` | `price_arclink_founders` | Limited 100 Founders Stripe price |
| `ARCLINK_FOUNDERS_PRICE_ID` | `price_arclink_founders` | Limited 100 Founders Stripe price ($149/month target) |
| `ARCLINK_SOVEREIGN_PRICE_ID` | `price_arclink_sovereign` | Sovereign Stripe price ($199/month target) |
| `ARCLINK_SCALE_PRICE_ID` | `price_arclink_scale` | Scale Stripe price ($275/month target) |
| `ARCLINK_FIRST_AGENT_PRICE_ID` | `price_arclink_founders` | Legacy first-agent alias for Limited 100 Founders |
| `ARCLINK_SOVEREIGN_AGENT_EXPANSION_PRICE_ID` | `price_arclink_sovereign_agent_expansion` | Sovereign Agentic Expansion Stripe price ($99/month target) |
| `ARCLINK_SCALE_AGENT_EXPANSION_PRICE_ID` | `price_arclink_scale_agent_expansion` | Scale Agentic Expansion Stripe price ($79/month target) |
| `ARCLINK_ADDITIONAL_AGENT_PRICE_ID` | `price_arclink_sovereign_agent_expansion` | Legacy alias for Sovereign Agentic Expansion |
| `ARCLINK_FOUNDERS_MONTHLY_CENTS` | `14900` | Limited 100 Founders public price label |
| `ARCLINK_SOVEREIGN_MONTHLY_CENTS` | `19900` | Sovereign public price label |
| `ARCLINK_SCALE_MONTHLY_CENTS` | `27500` | Scale public price label |
| `ARCLINK_FIRST_AGENT_MONTHLY_CENTS` | `14900` | Legacy first-agent monthly price alias |
| `ARCLINK_SOVEREIGN_AGENT_EXPANSION_MONTHLY_CENTS` | `9900` | Sovereign Agentic Expansion public price label |
| `ARCLINK_SCALE_AGENT_EXPANSION_MONTHLY_CENTS` | `7900` | Scale Agentic Expansion public price label |
| `ARCLINK_ADDITIONAL_AGENT_MONTHLY_CENTS` | `9900` | Legacy additional-agent monthly price alias |

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
| scale-operations | `/admin/scale-operations` | GET |
| sessions (revoke) | `/admin/sessions/revoke` | POST |

`/user/billing` includes `renewal_lifecycle`, which fails provider access
closed for non-current billing states. Non-current renewals now use the
approved lifecycle contract: immediate notice followed by daily reminders,
provider access suspended immediately, a day-7 account/data removal warning,
and day-14 audited purge queue metadata.
`/user/provider-state` and `/admin/provider-state` expose the same sanitized
boundary for Chutes deployments without returning key material. The Chutes
credential lifecycle is explicit: inference is disabled until a scoped
per-user or per-deployment `secret://` reference and budget are present;
operator-shared keys are rejected as user isolation, per-user Chutes account
OAuth is the fallback when per-key metering is unavailable, local
provider-budget credit accounting stays separate from live
purchase/provider-balance proof, and threshold continuation guidance remains
policy-gated until public continuation copy and self-service provider-change
policy exists.

The user dashboard (`web/src/app/dashboard/page.tsx`) consumes
`/user/dashboard`, `/user/billing`, `/user/provisioning`, `/user/provider-state`,
`/user/credentials`, `/user/credentials/acknowledge`, and
`/user/linked-resources`. The web API client also exposes
`/user/share-grants/deny` and `/user/share-grants/revoke` for owner-scoped
share closure flows. The hosted API and OpenAPI catalog define share create,
approve, deny, accept, revoke, and linked-resource reads; the current Next.js
dashboard intentionally wires only credential acknowledgement, linked-resource
listing, and read-only share status until full share creation, approval,
acceptance, and revocation UI is built.

## Assumptions and Ownership

- **Owner**: ArcLink control-plane team
- **Database**: Single SQLite file (Postgres path planned but not active)
- **Session storage**: `sessions` table in same DB; no external session store
- **Rate limit storage**: `rate_limits` table; no Redis dependency
- **Stripe client**: Defaults to `FakeStripeClient` when no live key configured
- **Bot adapters**: Telegram/Discord webhooks use fake-mode adapters by default
