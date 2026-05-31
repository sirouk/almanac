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
API clients but are not preferred for browser CSRF routes. The internal
Drive/Code share-request broker route is separate: it uses a deployment-scoped
`X-ArcLink-Share-Request-Broker-Token` header and derives the owner from the
token-bound deployment instead of accepting browser session cookies.

### Headers

| Header | Purpose |
|--------|---------|
| `X-ArcLink-Session-Id` | Session identifier (fallback if cookies unavailable) |
| `X-ArcLink-Session-Token` | Session secret |
| `X-ArcLink-CSRF-Token` | CSRF token for POST mutations |
| `X-ArcLink-Share-Request-Broker-Token` | Deployment-scoped internal Drive/Code Request Share broker token |
| `X-ArcLink-Request-Id` | Client-supplied request ID (echoed in response; auto-generated if absent) |

## Rate Limiting

Rate limits are enforced per-scope using a sliding window stored in the `rate_limits` SQLite table.

| Scope | Limit | Window |
|-------|-------|--------|
| `login` | 10 requests | 900s (15 min) |
| `admin_login` | 5 requests | 900s (15 min) |
| `user_login` | 10 requests | 900s (15 min) |
| `onboarding_claim` | 5 requests | 900s (15 min) |
| `onboarding:{channel}` | 5 requests | 900s (15 min) |
| `webhook:stripe` | `ARCLINK_WEBHOOK_RATE_LIMIT_STRIPE` | `ARCLINK_WEBHOOK_RATE_LIMIT_WINDOW_SECONDS` |
| `webhook:telegram` | `ARCLINK_WEBHOOK_RATE_LIMIT_TELEGRAM` | `ARCLINK_WEBHOOK_RATE_LIMIT_WINDOW_SECONDS` |
| `webhook:discord` | `ARCLINK_WEBHOOK_RATE_LIMIT_DISCORD` | `ARCLINK_WEBHOOK_RATE_LIMIT_WINDOW_SECONDS` |

The login scopes (`login`, `user_login`, `admin_login`) and `onboarding_claim` are
hard-coded in `arclink_api_auth.py`; the per-channel `onboarding:{channel}` scope is
shared by public onboarding start and by public-bot turns (the public-bot turn limit
and window come from `ARCLINK_PUBLIC_BOT_TURN_LIMIT` /
`ARCLINK_PUBLIC_BOT_RATE_WINDOW_SECONDS`). Webhook scopes are subject-keyed by
proxy-resolved client IP (`ip:<client_ip>`).

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
| GET | `/onboarding/status` | Read the current onboarding-session status (status, entitlement state, plan, checkout state, and any provisioned ArcPod access) for the browser checkout-return page |
| POST | `/onboarding/claim-session` | Exchange a paid onboarding `session_id` plus browser `claim_token` for a user session; mints the user session cookies on `201` and is rate-limited under the `onboarding_claim` scope (public route, gated by the claim token rather than session CSRF) |
| POST | `/onboarding/cancel` | Cancel an in-progress onboarding session; gated by `session_id` plus a browser `cancel_token` (public route) |
| GET | `/adapter-mode` | Report fake-adapter posture for the browser: `{fake_mode, fake_stripe}` (true when no live Stripe key is configured or `ARCLINK_FAKE_MODE`/`ARCLINK_FAKE_ADAPTERS` is set) |
| POST | `/webhooks/stripe` | Stripe webhook receiver |
| POST | `/webhooks/telegram` | Telegram Bot API webhook; requires `X-Telegram-Bot-Api-Secret-Token` matching `TELEGRAM_WEBHOOK_SECRET` |
| POST | `/webhooks/discord` | Discord interaction webhook; verifies signature timestamp tolerance and interaction replay |
| POST | `/fleet/enrollment/callback` | Worker fleet enrollment attestation callback; requires bearer enrollment token |
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
| POST | `/user/refuel-checkout` | Create a Stripe Checkout payment link for ArcPod Refueling (CSRF) |
| GET | `/user/provisioning` | Deployment provisioning status |
| GET | `/user/credentials` | Pending credential handoff metadata; masked refs only |
| POST | `/user/credentials/acknowledge` | Confirm credential storage and remove future handoff visibility (CSRF) |
| POST | `/user/agent-identity` | Rename or retitle a user's Agent (CSRF) |
| POST | `/user/backup-deploy-key` | Stage the private-backup deploy key and return only the public key/status (CSRF) |
| POST | `/user/backup-write-check` | Record the private-backup GitHub write-check boundary; unattended local checks fail closed without activation (CSRF) |
| GET | `/user/wrapped` | Captain ArcLink Wrapped history with redacted plain-text and Markdown renders |
| POST | `/user/wrapped-frequency` | Set ArcLink Wrapped cadence to daily, weekly, or monthly (CSRF) |
| GET | `/user/crew-recipe` | Read the active Crew Recipe, prior archived recipe, and "what changed" summary |
| POST | `/user/crew-recipe/preview` | Preview or regenerate a Crew Recipe without applying it (CSRF) |
| POST | `/user/crew-recipe/apply` | Confirm Crew Training and apply the additive SOUL overlay (CSRF) |
| GET | `/user/academy` | Read the Captain's Academy view: available Majors, enrolled Trainees, per-account quota, and graduate gallery |
| GET | `/user/academy/mode-status` | Read sticky Academy Mode status for a Trainee (`trainee_id` query); reports whether a session is open |
| POST | `/user/academy/enroll` | Enroll a Trainee into a Major (`program_id`, `name`, `depth`) within the per-account quota (CSRF) |
| POST | `/user/academy/mode-open` | Open a sticky Academy Mode session for a Trainee (idempotent; one open session per Trainee) (CSRF) |
| POST | `/user/academy/mode-end` | Close the open Academy Mode session, optionally graduating the Trainee; mode-end itself returns `mutation_performed=false` and writes no Agent files. The separate queued `academy_apply` action is the PG-HERMES-gated Agent write path; today it materializes the marker-bounded Academy SOUL section and a private apply receipt when authorized. (CSRF) |
| POST | `/user/academy/adopt` | Adopt a redacted graduate card from the owner-scoped gallery into a new Trainee (`source_trainee_id`, `name`) (CSRF) |
| GET | `/user/share-grants` | Share approval inbox for the authenticated owner or recipient, including pending owner approval, recipient acceptance waits, and no-channel recovery state |
| POST | `/user/share-grants` | Request a Drive/Code share grant (CSRF). Drive/Code folder shares default to read/write access in the recipient's Linked root. Same-account agent-to-agent shares require `owner_deployment_id` plus a different `recipient_deployment_id` and auto-accept into the target agent's Linked root. |
| POST | `/user/share-grants/broker` | Internal Drive/Code Request Share broker route. Requires `X-ArcLink-Share-Request-Broker-Token`; derives the owner from the token-bound `owner_deployment_id` and does not accept browser session cookies as a substitute. With `share_mode="claim_nonce"` (the default for Drive/Code right-click Share) it mints a single-use, 12-hour ephemeral nonce instead of resolving a recipient up front, returning `{nonce, accept_command, copy_text, expires_at, expires_in_hours}`. |
| POST | `/user/share-grants/approve` | Owner-approve a pending share grant (CSRF) |
| POST | `/user/share-grants/deny` | Owner-deny a pending share grant (CSRF) |
| POST | `/user/share-grants/accept` | Recipient accepts an approved share grant (CSRF) |
| POST | `/user/share-grants/claim` | Recipient claims a share by its ephemeral nonce (CSRF). The Raven equivalent is `/arclink_share_accept <nonce>`. The single-use nonce is consumed and the resource is materialized into the recipient's Linked root. |
| POST | `/user/share-grants/nonce/revoke` | Owner revokes a minted-but-unclaimed ephemeral share nonce by `nonce_id` (CSRF); idempotent, and a claimed/expired nonce is not revocable. |
| POST | `/user/share-grants/revoke` | Owner revokes a share grant and removes accepted linked-resource visibility (CSRF) |
| POST | `/user/share-grants/retry-notification` | Retry queueing the current owner-approval or recipient-acceptance Raven prompt to the local notification outbox; returns `queued=false` with recovery guidance when no linked public channel exists (CSRF) |
| GET | `/user/linked-resources` | Accepted linked resources for the authenticated user |
| GET | `/user/provider-state` | Provider adapter state, including sanitized Chutes budget, credential, billing-suspension boundary, and LLM router usage/quota |

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
| GET | `/admin/provider-state` | Provider adapter state, including sanitized Chutes budget and LLM router usage summaries |
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
| `ARCLINK_BACKUP_KEY_STAGING_DIR` | (none) | Server-side private directory for per-deployment backup deploy-key staging; required before `/user/backup-deploy-key` can mint a key |
| `ARCLINK_SESSION_HASH_PEPPER` | dev fallback | HMAC pepper for session and CSRF token hashes |
| `ARCLINK_SESSION_HASH_PEPPER_REQUIRED` | `1` | Require a configured pepper before issuing sessions |
| `ARCLINK_BACKEND_ALLOWED_CIDRS` | (none) | CIDR allow-list for admin/control routes |
| `ARCLINK_FLEET_ENROLLMENT_SECRET` | (none) | HMAC root for single-use fleet enrollment token minting and callback verification |
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

ArcPod Refueling uses Stripe Checkout `mode=payment` through
`POST /api/v1/user/refuel-checkout`. The Stripe webhook adds model fuel only
when the Checkout customer, `client_reference_id`, Captain account, and target
ArcPod match. Paid monthly subscription invoices also replenish included ArcPod
fuel through the same credit ledger; duplicate `invoice.payment_succeeded` /
`invoice.paid` events are idempotent per invoice and ArcPod.

For a matched refuel payment the webhook result carries a synthetic
`entitlement_state="refuel_paid"` marker. This is a transient response label, not
a stored entitlement state — the persisted entitlement states remain
`none|paid|comp|past_due|cancelled`. The refuel/allowance ledger is local budget
accounting only and is stamped
`local_budget_accounting_only_until_live_chutes_proof`; it never moves a real
Chutes provider balance. Live Chutes provider-balance application is proof-gated
(PG-PROVIDER), and live Stripe checkout/portal/webhook delivery is proof-gated
(PG-STRIPE). The Stripe webhook is fail-closed: when `STRIPE_WEBHOOK_SECRET` is
unset it returns `503` so Stripe keeps retrying.

The provider-state payload includes sanitized ArcLink LLM Router consumption
when router rows exist: request/status counts, stream counts, token totals,
estimated/actual cents, open reservation cents, credential counts, and the
current budget/quota view. It does not return raw router keys, central Chutes
credentials, secret refs, prompts, or completions.

## LLM Router

The Control Node LLM router is exposed separately from the hosted `/api/v1`
surface:

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/v1/models` | `Authorization: Bearer <ArcLink router key>` | Return the model allowlist for the ArcPod key |
| POST | `/v1/chat/completions` | `Authorization: Bearer <ArcLink router key>` | Relay OpenAI-compatible streaming or non-streaming chat completions through Chutes |

Router failures use OpenAI-style error objects. Auth failures return `401`,
billing/budget/quota boundary failures return `402`, request/rate/concurrency
limits return `400` or `429`, and missing router DB/upstream credential
configuration returns `503`. Live Chutes proof is disabled unless the operator
explicitly sets `ARCLINK_LLM_ROUTER_LIVE_CHUTES_PROOF=1` together with the
bounded live-proof model, credential, and max-cents variables documented in
`docs/arclink/llm-router.md`.

The router refreshes the Chutes model catalog into `arclink_model_catalog`,
stores per-million input/output pricing, and resolves deprecated, unavailable,
or older same-family model requests to the current upstream model when
auto-promotion is enabled. The ArcPod key can keep requesting the Captain's
configured model id while billing and usage rows record the resolved upstream
model.

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
listing, and share status until full share creation, approval,
acceptance, and revocation UI is built.
Same-account multi-agent shares use the same API surface but are deployment
scoped: the source deployment provides Vault/Workspace, the target deployment
receives a Linked projection, and no owner-notification approval loop
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
- **Session storage**: `arclink_user_sessions` and `arclink_admin_sessions` tables
  in the same DB; only token/CSRF hashes are stored, no external session store
- **Rate limit storage**: `rate_limits` table; no Redis dependency
- **Stripe client**: Defaults to `FakeStripeClient` when no live key configured
- **Bot adapters**: Telegram/Discord webhooks use fake-mode adapters by default

## Related Documents

This reference plus `docs/openapi/arclink-v1.openapi.json` are the canonical
route catalog; `docs/openapi/arclink-v1.openapi.json` is byte-identical to the
spec generated by `build_arclink_openapi_spec()` and is regenerated on any
`_ROUTES` change. For other concerns, cross-reference rather than duplicate:

- **Trust boundary / Docker-socket brokers (GAP-019)**: see the GAP-019 entries in
  `docs/arclink/operations-runbook.md` (authoritative source).
- **Gap and proof-gate taxonomy (GAP-* / PG-*)**: see `GAPS.md`.
- **LLM Router live-proof variables**: see `docs/arclink/llm-router.md`.
