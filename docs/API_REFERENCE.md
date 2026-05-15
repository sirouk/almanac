# ArcLink Hosted API Reference

- Version: v1
- Prefix: `/api/v1`
- Transport: WSGI (Python), JSON request/response
- Auth: Cookie-based session + CSRF header on mutations

## Authentication

Sessions are issued via `/auth/login`, which resolves whether the supplied
credentials belong to a user or admin account and sets the matching session
cookies. Legacy `/auth/admin/login` and `/auth/user/login` routes remain for
API compatibility. Login routes require email plus password and return generic
auth errors to callers. Credentials are delivered as cookies
(`arclink_{kind}_session_id`, `arclink_{kind}_session_token`,
`arclink_{kind}_csrf`). The session id/token cookies are `HttpOnly`; the CSRF
cookie is readable by the browser so the web client can echo it in
`X-ArcLink-CSRF-Token` for mutations.

Session and CSRF token hashes use HMAC-SHA256. Production deployments should
set `ARCLINK_SESSION_HASH_PEPPER` and
`ARCLINK_SESSION_HASH_PEPPER_REQUIRED=1`; development falls back to a fixed
dev pepper when the required flag is not set.

Browser routes use cookie credentials. Header credentials remain available for
API clients but are not preferred for browser CSRF routes.

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
| `login` | 10 requests | 15 min |
| `admin_login` | 5 requests | 15 min |
| `user_login` | 10 requests | 15 min |
| `onboarding:{channel}` | 5 requests | 15 min |
| `public_bot:{channel}` | via `check_arclink_rate_limit` | configurable |
| `webhook:stripe` | `ARCLINK_WEBHOOK_RATE_LIMIT_STRIPE` | `ARCLINK_WEBHOOK_RATE_LIMIT_WINDOW_SECONDS` |
| `webhook:telegram` | `ARCLINK_WEBHOOK_RATE_LIMIT_TELEGRAM` | `ARCLINK_WEBHOOK_RATE_LIMIT_WINDOW_SECONDS` |
| `webhook:discord` | `ARCLINK_WEBHOOK_RATE_LIMIT_DISCORD` | `ARCLINK_WEBHOOK_RATE_LIMIT_WINDOW_SECONDS` |

When exceeded, the API returns `429` with `{"error": "ArcLink rate limit exceeded"}`, `Retry-After`, and `X-RateLimit-*` headers.

## CORS

Configured via `ARCLINK_CORS_ORIGIN` env var. Preflight (`OPTIONS`) is
route-checked: unknown paths return `404`, unsupported requested methods return
`405`, and valid preflights return `204` with an `Allow` header for the
matched route plus:

- `Access-Control-Allow-Credentials: true`
- `Access-Control-Max-Age: 86400`

Early errors, including route misses, body-size failures, and CIDR denials,
carry CORS headers when CORS is configured.

## Request Bodies

The hosted API caps request bodies before JSON parsing. General JSON routes
default to `ARCLINK_HOSTED_API_MAX_BODY_BYTES=1048576`; webhook routes default
to `ARCLINK_HOSTED_API_WEBHOOK_MAX_BODY_BYTES=2097152`. Over-limit requests
return `413` with `body_too_large`. Malformed JSON returns `400` with
`invalid_json`.

## Network Boundary

Admin and backend-control routes are protected by
`ARCLINK_BACKEND_ALLOWED_CIDRS`. Control Node Compose defaults this to the
Docker private range, and operators should narrow it to the actual reverse
proxy or tailnet source ranges for production. Public onboarding, webhooks,
health, and OpenAPI routes remain outside this CIDR gate.

## Routes

### Public (no session required)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/onboarding/start` | Begin onboarding flow |
| POST | `/onboarding/answer` | Answer onboarding question |
| POST | `/onboarding/checkout` | Open Stripe checkout |
| GET | `/onboarding/public-bot-checkout` | Redirect a signed public-bot checkout button to Stripe |
| POST | `/webhooks/stripe` | Stripe webhook receiver |
| POST | `/webhooks/telegram` | Telegram Bot API webhook; requires `X-Telegram-Bot-Api-Secret-Token` matching `TELEGRAM_WEBHOOK_SECRET` |
| POST | `/webhooks/discord` | Discord interaction webhook; verifies signature timestamp tolerance and interaction replay |
| POST | `/auth/login` | Create a user or admin session based on credentials |
| POST | `/auth/admin/login` | Legacy route to create admin session |
| POST | `/auth/user/login` | Legacy route to create user session with email plus the user-scoped dashboard password |
| GET | `/health` | Liveness check (DB connectivity) |
| GET | `/openapi.json` | OpenAPI 3.1 spec (machine-readable route catalog) |

### User (session_kind=user)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/user/logout` | Revoke user session (CSRF) |
| GET | `/user/dashboard` | User deployment overview |
| GET | `/user/comms` | Captain-scoped Pod Comms inbox/outbox with message narratives |
| GET | `/user/billing` | Billing/entitlement status plus the local renewal lifecycle gate |
| POST | `/user/portal` | Create Stripe portal link (CSRF) |
| GET | `/user/provisioning` | Deployment provisioning status |
| GET | `/user/credentials` | Pending credential handoff metadata; masked refs only |
| POST | `/user/credentials/acknowledge` | Confirm credential storage and remove future handoff visibility (CSRF) |
| POST | `/user/agent-identity` | Rename or retitle a user's Agent (CSRF) |
| GET | `/user/wrapped` | Captain ArcLink Wrapped history with redacted plain-text and Markdown renders |
| POST | `/user/wrapped-frequency` | Set ArcLink Wrapped cadence to daily, weekly, or monthly (CSRF) |
| GET | `/user/crew-recipe` | Read the active Crew Recipe, prior archived recipe, and "what changed" summary |
| POST | `/user/crew-recipe/preview` | Preview or regenerate a Crew Recipe without applying it (CSRF) |
| POST | `/user/crew-recipe/apply` | Confirm Crew Training and apply the additive SOUL overlay (CSRF) |
| POST | `/user/share-grants` | Request a read-only Drive/Code share grant (CSRF). Same-account agent-to-agent shares require `owner_deployment_id` plus a different `recipient_deployment_id` and auto-accept into the target agent's Linked root. |
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
| GET | `/admin/comms` | Operator Pod Comms metadata only; message narratives and attachments are withheld |
| GET | `/admin/wrapped` | Aggregate ArcLink Wrapped status and scores only; Captain narratives are withheld |
| GET | `/admin/service-health` | Service health (filters: deployment_id, status, since) |
| GET | `/admin/provisioning-jobs` | Provisioning jobs (filters: deployment_id, status, since) |
| GET | `/admin/dns-drift` | DNS drift observations (filters: deployment_id, since) |
| GET | `/admin/audit` | Audit log (filters: deployment_id, since) |
| GET | `/admin/events` | Event log (filters: deployment_id, since) |
| GET | `/admin/actions` | Queued actions (filters: deployment_id, status, since) |
| POST | `/admin/actions` | Queue admin action (CSRF) |
| POST | `/admin/crew-recipe/apply` | Apply Crew Training on a Captain's behalf with admin mutation auth, CIDR/CSRF protection, and audit logging |
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
| `ARCLINK_COOKIE_SECURE` | auto | Set Secure flag on cookies; defaults off only for plain HTTP localhost origins |
| `ARCLINK_COOKIE_SAMESITE` | `Strict` | Session and CSRF cookie SameSite value |
| `ARCLINK_SESSION_HASH_PEPPER` | dev fallback | HMAC pepper for session and CSRF token hashes |
| `ARCLINK_SESSION_HASH_PEPPER_REQUIRED` | `1` | Require a configured pepper before issuing sessions |
| `ARCLINK_BACKEND_ALLOWED_CIDRS` | (none) | CIDR allow-list for admin/control routes |
| `ARCLINK_HOSTED_API_MAX_BODY_BYTES` | `1048576` | General request body cap |
| `ARCLINK_HOSTED_API_WEBHOOK_MAX_BODY_BYTES` | `2097152` | Webhook request body cap |
| `ARCLINK_CREW_RECIPE_FALLBACK_MODEL` | (none) | Optional Chutes-compatible model id used for Crew Recipe generation when the existing scoped Chutes boundary allows inference |
| `ARCLINK_WEBHOOK_RATE_LIMIT_WINDOW_SECONDS` | `60` | Webhook rate-limit window |
| `ARCLINK_WEBHOOK_RATE_LIMIT_DEFAULT` | `60` | Default webhook requests per window |
| `TELEGRAM_WEBHOOK_SECRET` | (none) | Telegram webhook secret-token verification; webhook handling fails closed when unset |
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
| crew training on behalf | `/admin/crew-recipe/apply` | POST |
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
`/user/linked-resources`. Its Crew Training tab consumes
`/user/crew-recipe`, `/user/crew-recipe/preview`, and
`/user/crew-recipe/apply`. The web API client also exposes
`/user/share-grants/deny` and `/user/share-grants/revoke` for owner-scoped
share closure flows. The hosted API and OpenAPI catalog define share create,
approve, deny, accept, revoke, and linked-resource reads; the current Next.js
dashboard intentionally wires only credential acknowledgement, linked-resource
listing, and read-only share status until full share creation, approval,
acceptance, and revocation UI is built.
Same-account multi-agent shares use the same API surface but are deployment
scoped: the source deployment provides Vault/Workspace, the target deployment
receives a read-only Linked projection, and no owner-notification approval loop
is needed because the authenticated user owns both agents.

Pod Comms uses the same share-grant table for trust boundaries. Messages
between Pods owned by the same Captain are allowed by default. Cross-Captain
messages require an accepted, unexpired `pod_comms` grant; file references are
separate Drive/Code share grants and are stored as attachment references rather
than raw file content. The Captain route returns narratives for that Captain's
inbox/outbox, while the Operator route returns only routing/status metadata.

Crew Training uses the existing user session and CSRF boundary for Captain
preview/apply calls. Applying a recipe archives the previous active
`arclink_crew_recipes` row, writes the Captain role, mission, and treatment on
`arclink_users`, emits audit/event rows, and projects an additive SOUL overlay
into local Pod identity context files when those homes are available. It does
not rewrite memory or session files and does not restart Hermes gateways.
Provider-backed recipe generation is allowed only through the existing scoped
Chutes boundary; otherwise the API returns a deterministic preset-only recipe
with an explicit fallback reason. Provider output containing unsafe URL,
command, or instruction-override patterns is rejected before fallback.

## Assumptions and Ownership

- **Owner**: ArcLink control-plane team
- **Database**: Single SQLite file (Postgres path planned but not active)
- **Session storage**: `sessions` table in same DB; no external session store
- **Rate limit storage**: `rate_limits` table; no Redis dependency
- **Stripe client**: Defaults to `FakeStripeClient` when no live key configured
- **Bot adapters**: Telegram/Discord webhooks use fake-mode adapters by default
