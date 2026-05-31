# Ground Truth 01 — Control Plane Core, Schema, Hosted API, Dashboard, Auth

Mapped 2026-05-30 (branch `arclink`). Source of truth = the code below; docs
judged against it. No secrets, prompts, or operator identity reproduced.

Owning code files:
- `python/arclink_control.py` (18,740 lines) — schema (`ensure_schema`),
  `Config`, env loading, all `arclink_*` table DDL, helpers
  (`append_arclink_event`, `queue_notification`, `connect_db`,
  `is_ip_in_cidrs`, `is_loopback_ip`).
- `python/arclink_hosted_api.py` (3,696 lines) — WSGI app, `_ROUTES` dispatch,
  CORS, cookies, webhooks, OpenAPI generation.
- `python/arclink_api_auth.py` (4,841 lines) — session/CSRF/password hashing,
  rate limiting, login/logout, admin RBAC+MFA gates, all `*_api` read/mutation
  handlers the hosted API calls.
- `python/arclink_dashboard.py` (2,392 lines) — `build_operator_snapshot`,
  `build_scale_operations_snapshot`, `_deployment_urls`, dashboard read models.
- `python/arclink_boundary.py` (133 lines) — `rowdict`, `json_loads_safe`,
  `json_dumps_safe`, `reject_secret_material`, Docker-trust guards.

---

## 1. arclink_* TABLE INVENTORY — "23 tables" is WRONG; the real count is 44

Built the live schema via `ensure_schema(conn, Config.from_env())` and queried
`sqlite_master`. Authoritative result:

- **TOTAL tables in live schema: 72**
- **`arclink_*`-prefixed tables: 44**
- non-`arclink_`-prefixed (legacy/substrate) tables: 28

The "23 arclink_* tables" figure (carried in project MEMORY.md and loosely in
older notes) is **stale by ~2x**. No tracked doc states a numeric count, so
the only place to correct is the agent memory/internal notes; **architecture.md
and API_REFERENCE.md do not assert a table count** (good — leave it that way or
state 44 explicitly).

The 44 `arclink_*` tables (canonical names, alphabetical):

```
arclink_action_attempts          arclink_llm_budget_reservations
arclink_action_intents           arclink_llm_router_keys
arclink_action_operation_links   arclink_llm_usage_events
arclink_admin_roles              arclink_model_catalog
arclink_admin_sessions           arclink_onboarding_events
arclink_admin_totp_factors       arclink_onboarding_sessions
arclink_admins                   arclink_operation_idempotency
arclink_audit_log                arclink_pod_messages
arclink_channel_pairing_codes    arclink_pod_migrations
arclink_credential_handoffs      arclink_provisioning_jobs
arclink_crew_recipes             arclink_public_bot_identity
arclink_deployment_placements    arclink_refuel_credits
arclink_deployments              arclink_rollouts
arclink_dns_records              arclink_service_health
arclink_events                   arclink_share_claim_nonces
arclink_evidence_runs            arclink_share_grants
arclink_fleet_audit_chain        arclink_subscriptions
arclink_fleet_enrollments        arclink_user_sessions
arclink_fleet_host_probes        arclink_users
arclink_fleet_hosts              arclink_webhook_events
arclink_fleet_share_members      arclink_wrapped_reports
arclink_fleet_shares
arclink_inventory_machines
```

Important naming nuance: **Academy tables are NOT `arclink_`-prefixed.** They
are `academy_programs`, `academy_trainees`, `academy_mode_sessions`,
`academy_resource_proposals`. Likewise the rate-limit store is the non-prefixed
`rate_limits` substrate table (API_REFERENCE.md correctly says
`rate_limits`). So features clearly added by ArcLink (Academy, Crew, LLM
router, fleet, pod comms, evidence, rollouts) are split across both
`arclink_*` and unprefixed namespaces.

Notable newer `arclink_*` tables that the architecture.md data-flow diagram
never mentions: `arclink_share_grants`, `arclink_share_claim_nonces`,
`arclink_fleet_shares`, `arclink_fleet_share_members`, `arclink_crew_recipes`,
`arclink_wrapped_reports`, `arclink_pod_messages`, `arclink_pod_migrations`,
`arclink_llm_router_keys`, `arclink_llm_usage_events`,
`arclink_llm_budget_reservations`, `arclink_model_catalog`,
`arclink_refuel_credits`, `arclink_channel_pairing_codes`,
`arclink_public_bot_identity`, `arclink_action_intents`,
`arclink_action_attempts`, `arclink_action_operation_links`,
`arclink_operation_idempotency`, `arclink_fleet_enrollments`,
`arclink_fleet_host_probes`, `arclink_fleet_audit_chain`,
`arclink_evidence_runs`, `arclink_admin_roles`, `arclink_admin_totp_factors`,
`arclink_deployment_placements`, `arclink_inventory_machines`.

Schema mechanism: a single idempotent `ensure_schema()` with
`CREATE TABLE IF NOT EXISTS`. A few tables are migrated with `*__new` rebuild
patterns (`arclink_fleet_host_probes__new`, `arclink_rollouts__new`,
`notion_identity_claims__new`) — i.e. column-add migrations via table rebuild.
There is **no PRAGMA user_version / numbered migration ledger**; migration is
"create-if-absent + rebuild-when-needed." (The symphony doc's "migration-aware,
idempotent, reversible, tested against old-state fixtures" is partially real:
idempotent yes; reversible/versioned no.)

---

## 2. HOSTED API ROUTE TABLE — code vs docs vs OpenAPI

Canonical route source is `_ROUTES: dict[(method, path_suffix) -> route_key]`
in `arclink_hosted_api.py`. All paths are served under prefix `HOSTED_API_PREFIX
= "/api/v1"`.

- **`_ROUTES` entries: 69** across **67 unique path suffixes** (two paths carry
  both GET and POST: `/user/share-grants` and `/admin/actions`).
- The OpenAPI spec additionally documents the 2 LLM-router paths
  (`GET /v1/models`, `POST /v1/chat/completions`) which are served by
  `arclink_llm_router.py`, NOT by `_ROUTES`. OpenAPI total = **69 path objects**
  (67 hosted + 2 router).

### 2a. OpenAPI parity — PERFECT (verified programmatically)

`build_arclink_openapi_spec()` generates the spec from `_ROUTES` +
`_ROUTE_DESCRIPTIONS` + `_LLM_ROUTER_OPENAPI_PATHS`. Comparing the live
generated spec to the on-disk `docs/openapi/arclink-v1.openapi.json`:

```
paths only in CODE-generated spec: []
paths only in DISK json: []
FULL SPEC byte-identical: True
```

`docs/openapi/arclink-v1.openapi.json` is **byte-identical** to the code-
generated spec (openapi 3.1.0, info.version 1.0.0). **No staleness.** Any route
added to `_ROUTES` will only stay in sync if the JSON is regenerated; today it
matches. (There is/should be a parity test guarding this.)

### 2b. Full canonical route list (method, path, route_key)

Public (no session) — `_PUBLIC_ROUTES`:
```
POST /onboarding/start                public_onboarding_start
POST /onboarding/answer               public_onboarding_answer
POST /onboarding/checkout             public_onboarding_checkout
GET  /onboarding/public-bot-checkout  public_bot_onboarding_checkout
GET  /onboarding/status               onboarding_status
POST /onboarding/claim-session        onboarding_claim_session
POST /onboarding/cancel               onboarding_cancel
GET  /adapter-mode                    adapter_mode
POST /webhooks/stripe                 stripe_webhook
POST /webhooks/telegram               telegram_webhook
POST /webhooks/discord                discord_webhook
POST /fleet/enrollment/callback       fleet_enrollment_callback   (bearer enrollment token)
POST /auth/login                      login          (admin path only if caller IP is backend-allowed)
POST /auth/admin/login                admin_login
POST /auth/user/login                 user_login
GET  /health                          health
GET  /openapi.json                    openapi_spec
```

User session routes:
```
POST /auth/user/logout                user_logout (+CSRF)
GET  /user/dashboard                  user_dashboard
GET  /user/comms                      user_comms
GET  /user/billing                    user_billing
POST /user/portal                     user_portal_link (+CSRF)
POST /user/refuel-checkout            user_refuel_checkout (+CSRF)
GET  /user/provisioning               user_provisioning_status
GET  /user/credentials                user_credentials
POST /user/credentials/acknowledge    user_credential_ack (+CSRF)
POST /user/agent-identity             user_agent_identity (+CSRF)
POST /user/backup-deploy-key          user_backup_deploy_key (+CSRF)
POST /user/backup-write-check         user_backup_write_check (+CSRF)
GET  /user/wrapped                    user_wrapped
POST /user/wrapped-frequency          user_wrapped_frequency (+CSRF)
GET  /user/crew-recipe                user_crew_recipe
POST /user/crew-recipe/preview        user_crew_recipe_preview (+CSRF)
POST /user/crew-recipe/apply          user_crew_recipe_apply (+CSRF)
GET  /user/academy                    user_academy
GET  /user/academy/mode-status        user_academy_mode_status
POST /user/academy/enroll             user_academy_enroll (+CSRF)
POST /user/academy/mode-open          user_academy_mode_open (+CSRF)
POST /user/academy/mode-end           user_academy_mode_end (+CSRF)
POST /user/academy/adopt              user_academy_adopt (+CSRF)
GET  /user/share-grants               user_share_grants
POST /user/share-grants               user_share_grant_create (+CSRF)
POST /user/share-grants/broker        user_share_grant_broker_create (BROKER TOKEN, not session)
POST /user/share-grants/approve       user_share_grant_approve (+CSRF)
POST /user/share-grants/deny          user_share_grant_deny (+CSRF)
POST /user/share-grants/accept        user_share_grant_accept (+CSRF)
POST /user/share-grants/claim         user_share_grant_claim (+CSRF)
POST /user/share-grants/nonce/revoke  user_share_nonce_revoke (+CSRF)
POST /user/share-grants/revoke        user_share_grant_revoke (+CSRF)
POST /user/share-grants/retry-notification user_share_grant_retry_notification (+CSRF)
GET  /user/linked-resources           user_linked_resources
GET  /user/provider-state             user_provider_state
```

Admin session routes (all in `_CIDR_PROTECTED_ROUTES`):
```
POST /auth/admin/logout               admin_logout (+CSRF)
GET  /admin/dashboard                 admin_dashboard
GET  /admin/comms                     admin_comms
GET  /admin/service-health            admin_service_health
GET  /admin/provisioning-jobs         admin_provisioning_jobs
GET  /admin/dns-drift                 admin_dns_drift
GET  /admin/audit                     admin_audit
GET  /admin/events                    admin_events
GET  /admin/actions                   admin_queued_actions
POST /admin/actions                   admin_action (+CSRF)
POST /admin/crew-recipe/apply         admin_crew_recipe_apply (+CSRF, admin mutation role)
GET  /admin/reconciliation            admin_reconciliation
GET  /admin/provider-state            admin_provider_state
POST /admin/sessions/revoke           session_revoke (+CSRF)
GET  /admin/operator-snapshot         admin_operator_snapshot
GET  /admin/scale-operations          admin_scale_operations
GET  /admin/wrapped                   admin_wrapped
```

Note: `admin_login` and `admin_logout` are themselves CIDR-protected. The
"admin" account can also be reached via the generic `POST /auth/login`, but
`_handle_login` only allows admin resolution when `allow_admin` is true, which
is gated on `_backend_client_allowed(...)` of the (proxy-resolved) client IP —
so admin login over `/auth/login` is itself CIDR-gated even though `login`
sits in `_PUBLIC_ROUTES`.

### 2c. Route DOC STALENESS (specific gaps)

**`docs/API_REFERENCE.md`** is mostly current but MISSES 10 live routes:
- `GET /adapter-mode` (returns `{fake_mode, fake_stripe}` — public, undocumented)
- `GET /onboarding/status`, `POST /onboarding/claim-session`,
  `POST /onboarding/cancel` (public onboarding lifecycle — undocumented)
- All 6 Academy routes: `GET /user/academy`, `GET /user/academy/mode-status`,
  `POST /user/academy/enroll`, `POST /user/academy/mode-open`,
  `POST /user/academy/mode-end`, `POST /user/academy/adopt`.

**`docs/arclink/architecture.md`** route table ("## Hosted API Routes") is
HEAVILY stale — missing **27** routes including the entire Academy set, Crew
Recipe set (`/user/crew-recipe[/preview|/apply]`, `/admin/crew-recipe/apply`),
Pod Comms (`/user/comms`, `/admin/comms`), `/user/refuel-checkout`,
`/user/agent-identity`, `/user/backup-deploy-key`, `/user/backup-write-check`,
`/auth/login` (generic), `/fleet/enrollment/callback`, `/adapter-mode`,
onboarding status/claim/cancel, and share-grant `broker`/`claim`/`nonce/revoke`/
`revoke`/`retry-notification`. It also predates the broker-token security
scheme. **Fix:** regenerate the architecture route table from `_ROUTES`, or
delegate the route catalog entirely to API_REFERENCE/OpenAPI and keep
architecture.md to a prose pointer.

---

## 3. AUTH / SESSION / CSRF / RATE-LIMIT REALITY

### Sessions
- Two session tables: `arclink_user_sessions`, `arclink_admin_sessions`.
- Session IDs are prefixed and prefix-validated: user `usess_...`, admin
  `asess_...` (`_require_session_id_prefix`). IDs are `secrets.token_hex(16)`.
- Tokens: session token + CSRF token are `secrets.token_urlsafe(32)` with
  prefixes (`aus_`/`aas_` for tokens, `csrf_` for CSRF). Only HASHES are stored
  (`session_token_hash`, `csrf_token_hash`); raw values returned once at login.
- **Token hashing**: HMAC-SHA256 peppered (`ARCLINK_SESSION_HASH_ALGORITHM =
  "hmac_sha256_v1"`), stored as `hmac_sha256_v1$<digest>`. Legacy plain-SHA256
  (`sha256_legacy`) is still VERIFIED for back-compat and silently rehashed to
  HMAC on next auth. Pepper from `ARCLINK_SESSION_HASH_PEPPER`; production
  domains (or `ARCLINK_SESSION_HASH_PEPPER_REQUIRED=1`) FAIL CLOSED if unset;
  dev/`.test` domains fall back to a fixed dev pepper.
- **Session TTL**: user = **86400s (24h)**, admin = **3600s (1h)**
  (`create_arclink_user_session` / `create_arclink_admin_session` defaults).
  `_require_active_time` enforces status=='active', no `revoked_at`, and
  `expires_at > now`. NOTE: a code comment in api_auth (line ~92) claims "12
  hours mirrors the dashboard session TTL" but the actual user TTL is 24h —
  a minor in-code comment staleness, not a doc claim.
- Passwords: PBKDF2-SHA256, 390,000 iterations, min length 12
  (`ARCLINK_PASSWORD_ALGORITHM`, `ARCLINK_PASSWORD_ITERATIONS`).

### Credential transport (cookies + header fallback)
- Login sets 3 cookies per kind: `arclink_{kind}_session_id`,
  `arclink_{kind}_session_token` (both `HttpOnly`), `arclink_{kind}_csrf`
  (NON-HttpOnly so browser JS can echo it). Flags: `Path=/`,
  `SameSite=<ARCLINK_COOKIE_SAMESITE default Strict>`, `Secure` unless local
  HTTP origin, optional `Domain`.
- `extract_arclink_session_credentials` (reads) accepts header
  (`X-ArcLink-Session-Id`, bearer / `X-ArcLink-Session-Token`) OR cookies.
- `extract_arclink_browser_session_credentials` (mutations) is COOKIE-ONLY.
- CSRF is enforced via header `X-ArcLink-CSRF-Token`
  (`extract_arclink_csrf_token` + `require_arclink_csrf`) — double-submit
  pattern (cookie value echoed as header, verified against stored hash). All
  mutating routes in `_JSON_OBJECT_ROUTES` go through CSRF.

### CSRF set membership
`/auth/login`, `/auth/admin/login`, `/auth/user/login` do NOT require CSRF
(they mint sessions). Logout, portal, refuel, all share-grant mutations,
crew-recipe preview/apply, academy mutations, agent-identity, backup-key,
wrapped-frequency, admin actions, crew-recipe apply, session revoke,
onboarding claim/cancel are CSRF-gated.

### Rate limits (`check_arclink_rate_limit`, sliding window over `rate_limits`)
Scopes are stored as `arclink:<scope>`. Login scopes (HARD-CODED in code,
not env):
- `login` → 10 / 900s, `user_login` → 10 / 900s, `admin_login` → 5 / 900s.
- `onboarding_claim` → 5 / 900s.
- Webhook scopes `webhook:{stripe|telegram|discord}` → limit from
  `ARCLINK_WEBHOOK_RATE_LIMIT_{STRIPE|TELEGRAM|DISCORD}` (default 60),
  window `ARCLINK_WEBHOOK_RATE_LIMIT_WINDOW_SECONDS` (default 60), subject =
  `ip:<client_ip>` (proxy-resolved).
- 429 carries `Retry-After`, `X-RateLimit-Limit/Remaining/Reset`.
API_REFERENCE.md's rate table lists `login 15min`, `admin_login 5/15min`,
`user_login 10/15min`, `onboarding:{channel}`, `public_bot:{channel}` — the
login numbers are CORRECT; but the table's scope labels `onboarding:{channel}`
and `public_bot:{channel}` don't match the actual code scope strings
(`onboarding_claim`, and per-channel public-bot scopes live in the bot/
onboarding modules, not in this file). Minor: worth aligning scope names.

### Admin RBAC + MFA (real but gated)
- `arclink_admins` enforces **single active owner** policy
  (`upsert_arclink_admin` rejects a second active owner).
- `_admin_mutation_allowed` checks `arclink_admins.role` ∈
  `ARCLINK_ADMIN_MUTATION_ROLES` and, if `totp_enabled`, requires
  `mfa_verified_at` on the session. Tables `arclink_admin_roles`,
  `arclink_admin_totp_factors` back RBAC/MFA. **Login ignores client-asserted
  MFA** (`mfa_verified=False` hard-set in `_handle_admin_login` /
  `create_arclink_admin_login_session_api`) — matches the symphony "ignore
  client-asserted MFA" requirement.

### Network boundary
- `_CIDR_PROTECTED_ROUTES` (all admin routes + admin login/logout) require the
  client IP to be loopback or within `ARCLINK_BACKEND_ALLOWED_CIDRS`
  (`_backend_client_allowed`). Public onboarding, webhooks, health, openapi,
  adapter-mode stay outside the gate. Forwarded headers (`X-Forwarded-For`)
  are trusted ONLY when the direct peer is already backend-allowed
  (`_remote_ip_from_headers`) — anti-spoof.

### Webhook auth reality (per route_key)
- `stripe_webhook`: requires `STRIPE_WEBHOOK_SECRET`; if unset, returns **503**
  (not 200) so Stripe keeps retrying — deliberate money-safety. Verifies
  `Stripe-Signature` via `process_stripe_webhook`. Queues "payment cleared" /
  "billing non-current" Raven pings on first paid/non-paid transition.
- `telegram_webhook`: secret-token header verification, fails closed without
  `TELEGRAM_WEBHOOK_SECRET`.
- `discord_webhook`: Ed25519 signature verification.
- `fleet_enrollment_callback`: `Authorization: Bearer <token>` consumed by
  `consume_fleet_enrollment` against `ARCLINK_FLEET_ENROLLMENT_SECRET`.

### Share-request broker auth (distinct scheme)
`user_share_grant_broker_create` uses header
`X-ArcLink-Share-Request-Broker-Token` (deployment-scoped), NOT session
cookies. Only a HASH of the token is stored
(`hash_share_request_broker_token` = HMAC-peppered). OpenAPI declares this as
`shareRequestBrokerAuth`. Documented in API_REFERENCE; absent from
architecture.md.

---

## 4. WSGI / RESPONSE BOUNDARY DETAILS (current behavior)

- Entry: `route_arclink_hosted_api(...)` returns `(status, payload, headers)`;
  `make_arclink_hosted_api_wsgi(...)` wraps it; `main()` serves with
  `wsgiref.simple_server` on `ARCLINK_API_HOST` (default 127.0.0.1) /
  `ARCLINK_API_PORT` (default 8900).
- Request ID: `X-ArcLink-Request-Id` echoed, else `req_<hex>` generated.
- CORS: only emitted when `ARCLINK_CORS_ORIGIN` set; methods `GET, POST,
  OPTIONS`; `Allow-Credentials: true`; `Max-Age 86400`. OPTIONS preflight is
  route-checked (404 unknown path, 405 unsupported method, 204 valid). Early
  errors (404, 413, CIDR-deny, rate-limit, auth) also carry CORS.
- Body caps BEFORE parse: general `ARCLINK_HOSTED_API_MAX_BODY_BYTES`
  (default 1 MiB), webhooks `ARCLINK_HOSTED_API_WEBHOOK_MAX_BODY_BYTES`
  (default 2 MiB); over-limit → 413 `body_too_large`; bad JSON → 400
  `invalid_json`.
- Error mapping: `ArcLinkRateLimitError`→429, `ArcLinkApiAuthError`→401
  (generic `"unauthorized"`), `StripeWebhookError`→400,
  `ArcLinkAcademyProgramError`→400 (generic), `KeyError`→404, other→400
  (generic `"Request blocked. Check input and try again."`). All include
  `request_id`.
- `_status_text` maps a fixed set of status codes; note **303** (See Other,
  used by public-bot checkout redirect) is mapped, but **201** (login responses
  return 201 Created) and **202** are also mapped — these are real.

---

## 5. PROOF-GATED / FAKE-ADAPTER / LOCAL-ONLY (honest separation)

What is REAL & local today (no creds needed):
- Full route dispatch, session/CSRF/RBAC/MFA gates, rate limiting, CIDR gate,
  CORS, body caps, OpenAPI generation+parity, schema build, dashboard reads,
  operator/scale-operations snapshots, share-grant + nonce flows,
  crew-recipe/academy/wrapped reads & mutations, webhook signature verification
  logic, entitlement state transitions from a (fake) Stripe webhook,
  Raven-ping queuing into the local `notification_outbox`.

What is FAKE-ADAPTER by default:
- Stripe: `resolve_stripe_client(env)` → `FakeStripeClient` unless a live key
  is configured; `GET /adapter-mode` reports `fake_mode`/`fake_stripe`.
- Telegram/Discord: fake-mode adapters; live transport needs bot tokens.
- Chutes/provider and ingress: fake by default.

What is PROOF-GATED (needs live creds / host / browser, tracked as PG-*):
- `PG-STRIPE` (live checkout/webhook/portal/refuel), `PG-BOTS` (live
  Telegram/Discord transport), `PG-PROVIDER` (live Chutes / router relay,
  `ARCLINK_LLM_ROUTER_LIVE_CHUTES_PROOF=1`), `PG-HERMES` (workspace plugin live
  proof), `PG-PROD` (production Control Node proof). The LLM router routes
  `/v1/models` + `/v1/chat/completions` are source-level real but live Chutes
  relay is operator-gated.
- Scale-operations spine (fleet/placement/action-worker/rollout) is durable and
  API-visible but the long-running production worker service is NOT documented
  as live; treat worker execution as a runbook step.
- `arclink_executor` is fail-closed; no production live adapters shipped.

---

## 6. GAP-* / PG-* STATUS this subsystem touches

Source-level evidence:
- **GAP-019** (Docker trusted-host residual risk) — the ONLY GAP referenced in
  these core files: `arclink_boundary.require_docker_trusted_host_risk_accepted`
  fails closed unless `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED=accepted`.
  Status: implemented as an explicit acceptance gate (residual-risk control),
  not "fixed away" — it is a deliberate operator-acknowledged boundary.
- Control-stack product gaps named in the symphony "dream shape" doc:
  - **GAP-029, GAP-030, GAP-032, GAP-033** — broader Operator-Raven mutation
    policy, authorized live proof of chat/browser/workspace/upgrade surfaces,
    rolling migrations / compatibility fixtures. These are FORWARD product gaps;
    the hosted-API/admin/dashboard/action-worker FOUNDATIONS exist in source.
  - **GAP-027** — unified Operator-Raven/action policy + recovery/revocation UX
    (identity/session governance is strong in source: session/CSRF/auth tests,
    single-owner, rate limits, owner-scoped handoffs).
  - **GAP-014/015/016** — sharing live browser/bot proof and no-channel behavior
    (broker/plugin/API contracts exist locally; retry-notification rail exists).
- The hosted API does NOT carry any in-code `GAP-NNN` annotations beyond
  GAP-019; the GAP/PG identifiers above come from the symphony doc, not from
  code comments. Treat them as product-roadmap status, not code TODO markers.

---

## 7. UNDOCUMENTED / NEWER-THAN-DOCS (in code, missing from canonical docs)

1. `GET /adapter-mode` route — returns fake-mode state; in NO canonical doc.
2. Academy API surface (6 routes + `academy_*` tables + `arclink_crew_recipes`
   interplay) — present in code & OpenAPI, absent from API_REFERENCE.md route
   tables and architecture.md.
3. Onboarding lifecycle routes `status` / `claim-session` / `cancel` — in code
   & OpenAPI, absent from API_REFERENCE.md.
4. `arclink_fleet_enrollments` + `POST /fleet/enrollment/callback` (bearer
   attestation) — in API_REFERENCE.md but NOT in architecture.md route table.
5. Pod Comms (`arclink_pod_messages`, `arclink_pod_migrations`, `/user/comms`,
   `/admin/comms`) — in API_REFERENCE prose; absent from architecture.md.
6. LLM router tables (`arclink_llm_router_keys`, `arclink_llm_usage_events`,
   `arclink_llm_budget_reservations`, `arclink_model_catalog`) and the
   refuel-credit ledger (`arclink_refuel_credits`) — described in
   API_REFERENCE/llm-router docs, missing from architecture.md data-flow.
7. Legacy `sha256_legacy` session-hash back-compat + auto-rehash to
   `hmac_sha256_v1` — undocumented implementation detail (security-relevant).
8. The architecture.md module map omits several shipped modules referenced by
   the hosted API import block: `arclink_academy_programs`,
   `arclink_fleet_enrollment`, `arclink_notification_delivery`,
   `arclink_pod_comms`, `arclink_secrets_regex`, `arclink_adapters` mapping is
   present but academy/fleet-enrollment/pod-comms are not.

---

## 8. PER-DOC STALENESS VERDICTS

| Doc | Verdict | Corrections needed |
| --- | --- | --- |
| `docs/openapi/arclink-v1.openapi.json` | **Fresh** | Byte-identical to code-generated spec. Keep the parity test; regenerate on any `_ROUTES` change. |
| `docs/API_REFERENCE.md` | **Light staleness** | Add the 10 missing routes: `GET /adapter-mode`, onboarding `status`/`claim-session`/`cancel`, and all 6 Academy routes. Align rate-limit scope labels (`onboarding:{channel}`→`onboarding_claim`; public-bot scopes live elsewhere). Otherwise accurate (auth, CORS, body caps, env vars, prices, broker token all correct). |
| `docs/arclink/architecture.md` | **Heavy staleness (route table)** | The "## Hosted API Routes" table is missing 27 routes and predates Academy, Crew Recipe, Pod Comms, refuel, agent-identity, backup-key, fleet-enrollment, generic `/auth/login`, broker/claim/nonce/revoke/retry share routes. Module map omits academy/fleet-enrollment/pod-comms/notification-delivery modules. Data-flow diagram omits ~25 newer `arclink_*` tables. Recommend: replace the embedded route table with a pointer to API_REFERENCE/OpenAPI, refresh module map, and add LLM-router/refuel/share/academy lanes to the data-flow. |
| `docs/DOC_STATUS.md` | **Light staleness** | Lists `architecture.md` and `API_REFERENCE.md` as "Canonical / route catalog" — but architecture.md's catalog is materially incomplete. Either downgrade architecture.md's route-catalog claim or fix the table. Add `docs/arclink/sovereign-control-node-symphony.md` to the map (it is tracked on disk, 1,214 lines, clearly Speculative "dream shape" — currently UNLISTED). |
| `docs/arclink/sovereign-control-node-symphony.md` | **Speculative (intended)** | Correctly framed as the dream shape. Its claims "Current source has hosted API/admin/dashboard/action-worker foundations…" are accurate. Its migration section overclaims "reversible where practical, tested against old-state fixtures" — code is idempotent create-if-absent with `*__new` rebuilds and NO version ledger; soften to match. Add to DOC_STATUS as Speculative. |
| (project memory / internal notes) | **Stale fact** | "23 arclink_* tables" → real count is **44** (72 total). Update wherever that figure is carried. |

---

## 9. CANONICAL VOCABULARY (use these exact names)

Modules: `arclink_control`, `arclink_hosted_api`, `arclink_api_auth`,
`arclink_dashboard`, `arclink_boundary`.
Entry fns: `route_arclink_hosted_api`, `make_arclink_hosted_api_wsgi`,
`build_arclink_openapi_spec`, `ensure_schema`, `Config.from_env`,
`build_operator_snapshot`, `build_scale_operations_snapshot`.
Auth fns: `create_arclink_login_session_api`,
`create_arclink_admin_login_session_api`,
`create_arclink_user_login_session_api`, `authenticate_arclink_user_session`,
`authenticate_arclink_admin_session`, `require_arclink_csrf`,
`check_arclink_rate_limit`, `revoke_arclink_session`,
`extract_arclink_session_credentials`,
`extract_arclink_browser_session_credentials`, `extract_arclink_csrf_token`.
Route prefix `/api/v1` (`HOSTED_API_PREFIX`). Header names: `X-ArcLink-Session-Id`,
`X-ArcLink-Session-Token`, `X-ArcLink-CSRF-Token`,
`X-ArcLink-Share-Request-Broker-Token`, `X-ArcLink-Request-Id`.
Session prefixes: `usess_`/`asess_` (ids), tokens `aus_`/`aas_`/`csrf_`.
Hash algo IDs: `hmac_sha256_v1` (current), `sha256_legacy` (back-compat).
OpenAPI security schemes: `sessionAuth`, `routerBearerAuth`,
`shareRequestBrokerAuth`.
