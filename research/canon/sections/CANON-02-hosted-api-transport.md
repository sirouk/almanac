# CANON-02 — Hosted API & Transport

## PIECE
This piece is ArcLink's hosted HTTP boundary and its low-level transport
helpers. It owns five tracked files:

- `python/arclink_hosted_api.py` (4,381 lines) — the WSGI app, the canonical
  `_ROUTES` dispatch table (`python/arclink_hosted_api.py:3754`), per-route
  handlers, CORS, cookie/session transport, body caps, webhook ingress
  (Stripe/Telegram/Discord/fleet-enrollment), OpenAPI 3.1 generation
  (`build_arclink_openapi_spec`, `:3689`), and the `wsgiref` `main()` server.
- `python/arclink_api_auth.py` (5,065 lines) — session/CSRF/password hashing,
  rate limiting, login/logout, admin RBAC+MFA gates, the share-request broker
  auth scheme, and the `*_api` read/mutation handlers the hosted API calls.
- `python/arclink_http.py` (147 lines) — `HttpResponse`, `http_request`
  (httpx-with-urllib-fallback), `enforce_secure_transport`, URL redaction,
  JSON parse helpers. The shared outbound-HTTP transport for the whole repo.
- `python/arclink_rpc_client.py` (136 lines) — a standalone CLI `mcp_call`
  client that speaks Streamable-HTTP MCP (initialize → notifications/initialized
  → tools/call) to an arclink-mcp server.
- `python/arclink_adapters.py` (374 lines) — `FakeStripeClient`/`LiveStripeClient`
  + `resolve_stripe_client`, Stripe webhook sign/verify, `FakeCloudflareClient`,
  and pure hostname/URL/Traefik-label builders.

The hosted API is the production HTTP boundary; the prototype
`arclink_product_surface.py` (CANON-03) is the no-secret smoke tool. All routes
serve under prefix `HOSTED_API_PREFIX = "/api/v1"` (`:167`).

## INPUT CONTRACT (code-verified)

### WSGI / route entry
- `route_arclink_hosted_api(conn, *, method, path, headers, body="", query=None, config=None, stripe_client=None, remote_addr="")` (`python/arclink_hosted_api.py:3921`) — the single dispatch entry. Returns `(status:int, payload:dict, headers:list[tuple[str,str]])`. Anyone may call; auth is per-route, not pre-dispatch.
- `make_arclink_hosted_api_wsgi(conn=None, *, config=None, stripe_client=None, db_config=None, connect=None)` (`:4259`) — builds the WSGI `app(environ, start_response)`. Reads `CONTENT_LENGTH` (bad → 400 `invalid_content_length`, `:4290`), enforces the per-route body cap BEFORE reading the body (`:4299`), reads `wsgi.input` exactly `length` bytes (`:4308`), folds `HTTP_*` + `CONTENT_TYPE` into a lowercased header dict (`:4311`).
- `main()` (`:4361`) serves with `wsgiref.simple_server.make_server` on `ARCLINK_API_HOST` (default `127.0.0.1`) / `ARCLINK_API_PORT` (default `8900`) (`:4371`).

### Route table (71 `_ROUTES` entries, 69 unique suffixes; verified by executing `len(_ROUTES)`)
Two suffixes carry two methods: `/user/share-grants` (GET+POST) and `/admin/actions` (GET+POST). Membership sets (`:3829`–`:3914`): `_PUBLIC_ROUTES` (18), `_CIDR_PROTECTED_ROUTES` (18, all `admin_*` + `admin_login`/`admin_logout`), `_BROKER_AUTH_ROUTES` (1: `user_share_grant_broker_create`), `_JSON_OBJECT_ROUTES` (38, the bodies parsed as JSON objects).

Dispatch order per request (`:3938`–`:4009`): build request_id → uppercase method → `rstrip("/")` path → strip `/api/v1` prefix → `OPTIONS` preflight (`:3951`, 404 unknown path / 405 wrong method / 204 valid) → `_ROUTES.get((method,path))` else 404 (`:3966`) → body cap (`:3973`, 413 `body_too_large`) → CIDR gate if `_CIDR_PROTECTED_ROUTES` (`:3979`, 403) → webhook/public-route rate limit (`:3993`/`:4001`) → JSON body parse if `_JSON_OBJECT_ROUTES` (`:4009`) → resolve Stripe client (`:4010`) → big `elif` handler chain (`:4012`–`:4163`).

### Auth credential inputs (api_auth)
- `extract_arclink_session_credentials(headers, *, session_kind)` (`python/arclink_api_auth.py:167`) — accepts header `X-ArcLink-Session-Id` OR cookie `arclink_{kind}_session_id`; token from bearer OR `X-ArcLink-Session-Token` OR cookie. Used by **read** routes. Raises `ArcLinkApiAuthError` if either is missing (`:179`).
- `extract_arclink_browser_session_credentials(headers, *, session_kind)` (`:184`) — **cookie-only**. Used by **mutation** routes.
- `extract_arclink_csrf_token(headers, *, session_kind)` (`:197`) — requires header `X-ArcLink-CSRF-Token`, else raises.
- Login bodies validated in `create_arclink_*_login_session_api` (`:839`,`:880`,`:946`): `email` lower-stripped (required), `password` (PBKDF2-verified), caller-supplied `login_subject` kept only as **audit** metadata (NEVER a throttle key, `:455`).

### Outbound transport input (`arclink_http.http_request`)
`http_request(url, *, method="GET", headers=None, json_payload=None, form_payload=None, content=None, timeout=20, allow_loopback_http=True)` (`python/arclink_http.py:66`). At most one of json/form/content (`:77` raises `ValueError`). `enforce_secure_transport` runs FIRST (`:79`).

## OUTPUT CONTRACT (code-verified)
- All handlers return `(status, dict_payload, headers)`. `_json_response` (`:422`) always sets `Content-Type: application/json`, echoes `X-ArcLink-Request-Id` when present.
- WSGI serializes `json.dumps(payload, sort_keys=True)` (`:4335`); empty payload → empty body. Status text via `_status_text` (`:4342`): maps 200/201/202/303/204/400/401/403/404/405/413/429/500/503; unknown → `f"{code} OK"`.
- **Login** routes set 3 `Set-Cookie` per kind (`_session_cookies`, `:450`): `arclink_{kind}_session_id` + `_session_token` (both `HttpOnly`), `arclink_{kind}_csrf` (NON-HttpOnly, so JS can echo it). Flags (`_cookie_flags`, `:437`): `Path=/; SameSite=<cookie_samesite>`, `HttpOnly` (except csrf), `Secure` unless local-HTTP origin, optional `Domain`. Login returns **201** (`create_arclink_*_login_session_api` payload status, `:877`,`:982`).
- Generic `/auth/login` (`_handle_login`, `:1121`) additionally CLEARS the alternate-kind cookies (`:1144`) so a user→admin switch can't leave stale cookies.
- **Logout** (`_handle_logout`, `:1150`) authenticates, requires CSRF, revokes the session, clears cookies; user logout also calls `revoke_user_dashboard_access` (`:1173`).
- `admin_action` returns **202** with `{"action": ...}` (`python/arclink_api_auth.py:4901`). `fleet_enrollment_callback` returns **201** `{"worker": ...}` (`:2050`).
- **Webhooks**: `stripe_webhook` returns 200 `{status:"processed",event_id,event_type,replayed}` on success (`:932`); **503 `stripe_webhook_secret_unset`** if `STRIPE_WEBHOOK_SECRET` unset (money-safety: Stripe keeps retrying, `:900`). `telegram_webhook` 200 with `{ok,action,sent,edited,...}` (`:3001`), 503 if secret unset (`:2894`), 401 on bad secret-token (`:2901`). `discord_webhook` returns the interaction response dict (`:3057`), 503 if no public key (`:3028`), 401 on bad signature, 200 `{type:5}` on duplicate (`:3049`).
- **DB side-effects**: session INSERTs into `arclink_user_sessions`/`arclink_admin_sessions` (`:781`,`:814`); rate-limit INSERTs into `rate_limits` (`:425`,`:497`); `revoke_arclink_session` UPDATE status + `append_arclink_audit` (`:4922`); webhook entitlement writes delegated to `process_stripe_webhook` (CANON-07); paid/non-current Raven pings via `queue_notification` into the notification outbox (`:992`,`:1050`) + `append_arclink_event` markers (`:1001`); onboarding claim-cookie writes `browser_claim_proof_hash` into `arclink_onboarding_sessions.metadata_json` (`:584`).
- **Outbound**: `http_request` returns `HttpResponse(status_code, text, headers)` with lowercased header keys (`python/arclink_http.py:103`,`:118`,`:128`); on transport error raises `RuntimeError` with a **redacted** URL (`:102`,`:131`).
- `resolve_stripe_client(env)` (`python/arclink_adapters.py:139`) → `LiveStripeClient` iff `STRIPE_SECRET_KEY` non-blank, else `FakeStripeClient`. Fake `create_checkout_session` returns a `cs_test_*` id and a `https://stripe.test/...` URL (`:54`).
- `mcp_call(url, tool_name, arguments)` (`python/arclink_rpc_client.py:11`) returns the tool's `structuredContent` dict when present (`:71`), else `{content, text}` from `content` text chunks (`:84`), else `{}`.

## TOUCH POINTS

### Env vars (HostedApiConfig, `:182`–`:292`, + module reads)
`ARCLINK_CORS_ORIGIN` (`:189`; wildcard `*` ignored because credentialed CORS, `:374`), `ARCLINK_COOKIE_DOMAIN`/`ARCLINK_COOKIE_SAMESITE`/`ARCLINK_COOKIE_SECURE` (`:190`–`:197`), `STRIPE_WEBHOOK_SECRET`/`TELEGRAM_WEBHOOK_SECRET` (`:198`–`:199`), `ARCLINK_LOG_LEVEL` (`:200`), `ARCLINK_HOSTED_API_MAX_BODY_BYTES` (default 1 MiB, `:201`), `ARCLINK_HOSTED_API_WEBHOOK_MAX_BODY_BYTES` (default 2 MiB, `:208`), `ARCLINK_BACKEND_ALLOWED_CIDRS` (`:215`), `ARCLINK_FLEET_ENROLLMENT_SECRET` (`:216`), `ARCLINK_WEBHOOK_RATE_LIMIT_{WINDOW_SECONDS,DEFAULT,STRIPE,TELEGRAM,DISCORD}` (`:217`–`:251`), `ARCLINK_PUBLIC_ROUTE_RATE_LIMIT_WINDOW_SECONDS`/`ARCLINK_PUBLIC_ACADEMY_OBSERVATORY_RATE_LIMIT` (default 120)/`ARCLINK_FLEET_ENROLLMENT_CALLBACK_RATE_LIMIT` (default 30) (`:252`–`:272`), price IDs `ARCLINK_{FOUNDERS,DEFAULT,SOVEREIGN,SCALE,…}_PRICE_ID` (`:273`–`:292`), `ARCLINK_CONFIG_FILE` (merged via `_load_hosted_api_env`, `:295`), `ARCLINK_API_HOST`/`ARCLINK_API_PORT` (`:4371`), `ARCLINK_FAKE_MODE`/`ARCLINK_FAKE_ADAPTERS` (`:2345`), `ARCLINK_PUBLIC_AGENT_LIVE_TRIGGER*` (`:2565`,`:2581`,`:2617`). api_auth reads `ARCLINK_SESSION_HASH_PEPPER`, `ARCLINK_SESSION_HASH_PEPPER_REQUIRED`, `ARCLINK_BASE_DOMAIN` (`python/arclink_api_auth.py:271`–`:283`). adapters reads `STRIPE_SECRET_KEY` (`python/arclink_adapters.py:143`).

### DB tables (r/w)
`arclink_user_sessions`, `arclink_admin_sessions` (w INSERT/UPDATE, r SELECT) — schema in CANON-01; `rate_limits` (non-prefixed substrate, r/w, `python/arclink_api_auth.py:408`,`:425`); `arclink_admins`/`arclink_admin_roles`/`arclink_admin_totp_factors` (r for RBAC/MFA, `:1048`); `arclink_onboarding_sessions` (r/w metadata, `:574`); `arclink_users` (r entitlement_state, `:2135`); `arclink_deployments` (r broker config + share, `:2413`); `arclink_events` (w markers, `:1001`); `arclink_service_health` (r, `:2179`); `academy_sources`/`academy_corpus_specialists`/`academy_*` (r aggregate-only, `:2369`+).

### Sockets / ports / external services
WSGI listens `127.0.0.1:8900` default (`:4371`). Outbound HTTP via `http_request` to Stripe (live), Telegram Bot API, Discord, fleet-enrollment callback, MCP servers. `_public_agent_live_trigger_can_run_locally` probes `/var/run/docker.sock` existence (`:2586`).

### Secrets handling
Session tokens/CSRF: only HMAC-SHA256-peppered HASHES stored (`_hash_session_token`, `python/arclink_api_auth.py:286`); raw tokens returned once at login. Passwords PBKDF2-SHA256 390k iters, min len 12 (`:326`). Broker token: only `_hash_proof_token` HMAC stored (`:260`,`:2426`). `arclink_http._redact_url_for_error` strips `/bot<token>`, userinfo, and `token|secret|key|password|auth` query keys before logging (`python/arclink_http.py:24`). Error text scrubbed via `redact_then_truncate` (`:144`).

## CODE-PATH TRACE (admin queue-action mutation, end to end)
1. WSGI `app` receives `POST /api/v1/admin/actions`; reads `CONTENT_LENGTH`, body-cap check (`python/arclink_hosted_api.py:4299`), reads body, folds headers (`:4311`), calls `route_arclink_hosted_api` (`:4321`).
2. Dispatch: prefix-strip → `route_key="admin_action"` (`:3965`); body cap re-checked (`:3973`).
3. `admin_action ∈ _CIDR_PROTECTED_ROUTES` → `_remote_ip_from_headers` (`:3980`) → `_backend_client_allowed` (loopback or in `ARCLINK_BACKEND_ALLOWED_CIDRS`, `:644`). X-Forwarded-For honored only when the DIRECT peer is already allowed (`:637`) — anti-spoof. Deny → 403 (`:3987`).
4. `admin_action ∈ _JSON_OBJECT_ROUTES` → `_json_body` parses (bad JSON / non-object → `HostedApiBodyError(400,"invalid_json")`, `:411`).
5. `_handle_admin_action` (`:1220`): `extract_arclink_browser_session_credentials(..., "admin")` (cookie-only, `:1227`) + `extract_arclink_csrf_token` (`:1228`).
6. `queue_admin_action_api` (`python/arclink_api_auth.py:4863`): `authenticate_arclink_admin_session` (`:4877`, prefix-check `asess_`, `_require_active_time`, hash compare, legacy-rehash) → `require_arclink_csrf` (`:4878`) → `_admin_mutation_allowed` (role ∈ {owner,admin,ops} + MFA if `totp_enabled`, `:4879`) → `confirm is not True` rejects (`:4880`) → two rate limits (`admin_action:admin` 30/60s, `admin_action:target` 12/60s, `:4883`) → `queue_arclink_admin_action` (CANON-14) → **202** `{"action":...}`.
7. Back in dispatch: success log (`:4166`), `_response_with_cors` appends CORS headers iff `ARCLINK_CORS_ORIGIN` set (`:604`).
8. WSGI serializes `json.dumps(payload, sort_keys=True)`, `start_response(_status_text(202)="202 Accepted")` (`:4336`).

## CROSS-PIECE CONTRACTS (both ends verified)

1. **→ CANON-01 (control)**: hosted_api imports `is_ip_in_cidrs`, `is_loopback_ip`, `queue_notification`, `append_arclink_event`, `connect_db`, `Config.from_env`, `parse_utc_iso`, `utc_now*` (`python/arclink_hosted_api.py:34`). `_backend_client_allowed` calls `is_loopback_ip`/`is_ip_in_cidrs` with the resolved IP string + CIDR string (`:646`). Producer-of-IP is this piece; consumer is CANON-01. Contract = `(str ip, str cidrs) -> bool`. BOTH-ENDS-VERIFIED: **partial** — call site verified here; the predicate body lives in CANON-01 (claimed, not re-read).

2. **→ CANON-07 (entitlements/billing)**: `_handle_stripe_webhook` calls `process_stripe_webhook(conn, payload=raw_body, signature=sig, secret=...)` (`:906`) and reads `StripeWebhookResult` fields `.event_type/.event_id/.user_id/.entitlement_state/.replayed` (`:910`,`:916`). The Stripe adapter mechanics (`verify_stripe_webhook`, `python/arclink_adapters.py:156`) are owned HERE; the entitlement state machine is CANON-07. Contract = raw body string + `Stripe-Signature` header → `StripeWebhookResult` dataclass. BOTH-ENDS-VERIFIED: **partial** — producer/keys verified here; consumer body in CANON-07.

3. **→ CANON-04 (onboarding)**: hosted_api imports `start_public_onboarding_api`, `answer_public_onboarding_api`, `open_public_onboarding_checkout_api` (live in api_auth, `:84`), which wrap `arclink_onboarding` (`python/arclink_api_auth.py:40`). `_handle_public_onboarding_*` forward body keys `channel/channel_identity/email/plan_id/model_id/session_id` (`:724`,`:743`). BOTH-ENDS-VERIFIED: **yes** within this piece's wrappers; the deepest onboarding logic is CANON-04.

4. **→ CANON-12 / CANON-20 (share broker)**: `user_share_grant_broker_create` authenticates ONLY on header `X-ArcLink-Share-Request-Broker-Token` (`:1741`) via `_authenticate_share_request_broker` (`python/arclink_api_auth.py:2448`); token verified against `arclink_deployments.metadata_json.share_request_broker.token_hash` using `_verify_proof_token_hash` (`:2477`). The broker-side that mints/holds the raw token is the public-agent broker (CANON-12); `set_deployment_share_request_broker_token_hash` (`:2403`) is the writer. Contract = HMAC-peppered `hmac_sha256_v1$<digest>` stored, raw token in header. BOTH-ENDS-VERIFIED: **partial** — verifier+writer verified here; the broker producer that sends the header is CANON-12.

5. **→ CANON-18 (MCP server)**: `arclink_rpc_client.mcp_call` POSTs `initialize`/`notifications/initialized`/`tools/call` and reads `mcp-session-id` response header (`python/arclink_rpc_client.py:36`,`:701`-equiv) + `result.structuredContent` (`:71`) / `result.content[*].text` (`:79`). The MCP server (`python/arclink_mcp_server.py:1835`) emits exactly `{"result":{"content":[{"type":"text","text":...}],"structuredContent":result}}` and sets `mcp-session-id` (`:1679`). BOTH-ENDS-VERIFIED: **yes** — producer (`arclink_mcp_server.py:1835`,`:1679`) and consumer (`arclink_rpc_client.py:36`,`:71`,`:79`) match on header name and `structuredContent`/`content` shape.

6. **→ CANON-03 / web (CORS + cookie transport)**: web client sends cookies + `X-ArcLink-CSRF-Token` header; server emits the non-HttpOnly `arclink_{kind}_csrf` cookie (`:469`) and `Access-Control-Allow-Credentials: true` only when origin configured (`:599`). Allowed headers limited to `Content-Type, X-ArcLink-CSRF-Token, X-ArcLink-Request-Id` (`:172`). BOTH-ENDS-VERIFIED: **partial** — server side fully verified; the web fetch wrapper (CANON-03) not opened here.

7. **→ all outbound HTTP callers (telegram/discord/onboarding-provider-auth/inventory/notification-delivery/mcp/memory)**: every one imports `http_request` from `arclink_http` (verified by `rg`: 11+ modules). Contract = `enforce_secure_transport` refuses non-loopback `http://` (`python/arclink_http.py:56`) and `HttpResponse` with lowercased headers. BOTH-ENDS-VERIFIED: **partial** — producer (this module) verified; each consumer is its own CANON piece.

## CODE vs COMMENT/DOC/NAME DRIFT
- **Prior doc 01-control-core-api.md drift (route count)**: it claims "69 `_ROUTES` entries / 67 unique suffixes" (line 105 of that doc). REAL today: **71 entries, 69 unique suffixes** (`len(_ROUTES)`=71). Two routes were added since: `("GET","/academy/observatory")→public_academy_observatory` (`python/arclink_hosted_api.py:3759`) and `("POST","/user/academy/adopt-specialist")→user_academy_specialist_adopt` (`:3791`). CODE WINS.
- **Prior doc drift (`_PUBLIC_ROUTES` count)**: prior doc's public list omits `public_academy_observatory` (now public, `:3834`). REAL `_PUBLIC_ROUTES`=18.
- **Prior doc drift (login rate-limit shape)**: prior doc says flat scopes `login→10/900s`, `admin_login→5/900s`. REAL: `_check_login_rate_limits` (`python/arclink_api_auth.py:445`) uses THREE buckets per attempt — `:account`, `:ip`, `:account_ip` — with `account_limit`/`ip_limit` pairs: login 10/50, admin_login 5/30, user_login 10/50 (`:858`,`:899`,`:964`). The caller-supplied `login_subject` is explicitly NOT a throttle key (`:455`). The prior doc's single-number summary is stale; the bucketed model is stronger than documented.
- **Prior doc drift (admin TTL comment)**: prior doc flags a "12 hours mirrors dashboard TTL" comment vs 24h real user TTL. The stale comment is now at `python/arclink_api_auth.py:95` and refers to the **share-claim-nonce** TTL (`ARCLINK_SHARE_CLAIM_NONCE_TTL_SECONDS = 12h`, `:96`), not the session TTL. User session TTL is still **86400s/24h** (`:769`), admin **3600s/1h** (`:799`). The "12 hours mirrors the dashboard session TTL" wording is itself drift — the actual user session is 24h, so the nonce does NOT mirror it.
- **Name vs body — `verify_arclink_password`**: returns `False` (not raise) on any malformed hash, and silently rejects iterations < 100k (`:350`) — a real defensive floor not implied by the name.
- **`_handle_adapter_mode` re-imports** `resolve_stripe_client`/`FakeStripeClient` locally (`:2342`) despite the module-level import at `:31` — redundant but harmless.
- **Telegram webhook is JSON-parsed; Stripe/Discord are not**: `telegram_webhook ∈ _JSON_OBJECT_ROUTES` but `stripe_webhook`/`discord_webhook` are NOT (verified). This is correct (Stripe/Discord need the RAW body for signature verification; Telegram verifies a secret-token header instead) but is a non-obvious asymmetry a reader could miss.

## ADVERSARIAL SELF-CHECK
1. **"`route_arclink_hosted_api` does no pre-dispatch session auth; each handler self-authenticates."** Verified the dispatch only does CIDR + rate-limit + body-parse before the handler `elif` chain; the broker route reaches its handler with zero session cookies and authenticates purely on the broker header. Falsifier: a centralized auth middleware I missed wrapping the handler chain — I read `:3979`–`:4163` and saw none.
2. **CIDR anti-spoof correctness.** `_remote_ip_from_headers` trusts `X-Forwarded-For` only if `_backend_client_allowed(direct)` (`:637`). If a real reverse proxy is in `ARCLINK_BACKEND_ALLOWED_CIDRS`, a public client's spoofed XFF is ignored. Falsifier: if `remote_addr` is empty AND `x-real-ip` is attacker-controlled, `direct` defaults to that header (`:635`) — a proxy that doesn't set REMOTE_ADDR but forwards `X-Real-IP` could let `direct` be spoofed. This is an unverified deployment-topology risk (see RISKS).
3. **OpenAPI parity is enforced.** `test_openapi_spec_matches_static_copy` (`tests/test_arclink_hosted_api.py:5496`) asserts byte-identity; I independently confirmed `byte_identical True`. Falsifier: a route added without regenerating the JSON would fail that test — so parity is CI-guarded, not just currently-true.
4. **Stripe webhook fail-CLOSED on missing secret (503 not 200).** Verified `:892`–`:904`. Falsifier: if any earlier branch returned 200 before the secret check — but the secret check is the first statement in `_handle_stripe_webhook`.
5. **`_session_hash_pepper` fails closed on production domains.** Verified `:271`–`:283`: raises unless pepper set OR domain is localhost/.test. Falsifier: a base domain that is empty string → `production_domain=False` → dev pepper used. So an UNSET `ARCLINK_BASE_DOMAIN` in prod silently uses the dev pepper (see RISKS).

## OPEN FOR CODEX FEDERATION
- Confirm `is_ip_in_cidrs` / `is_loopback_ip` (CANON-01) treat IPv6, embedded ports, and malformed strings safely — the CIDR gate's whole security depends on them, and I did not open their bodies.
- Confirm `process_stripe_webhook` (CANON-07) actually rejects replayed/forged events and that `StripeWebhookResult.replayed` is set truthfully (the paid-ping idempotency at `:916` trusts it).
- Confirm the web client (CANON-03) reads the non-HttpOnly `arclink_{kind}_csrf` cookie and echoes it as `X-ArcLink-CSRF-Token` — the double-submit pattern only works if the client does this; I verified only the server half.
- Independent check of risk #2/#5: does any shipped deployment topology leave `REMOTE_ADDR` empty (so `x-real-ip` becomes the trusted `direct`), or run a production domain with `ARCLINK_BASE_DOMAIN` unset and no pepper?
- Verify there is no second route table or alternate WSGI entry elsewhere that bypasses `_CIDR_PROTECTED_ROUTES`.

## RISKS (severity-ranked, code-cited)
- **MEDIUM** — `_remote_ip_from_headers` falls back to attacker-influenceable `x-real-ip` when `remote_addr` is empty (`python/arclink_hosted_api.py:635`); combined with `_backend_client_allowed(direct)` (`:637`), a proxy that forwards `X-Real-IP` but drops REMOTE_ADDR could let `direct` be a spoofed loopback/allowed IP, defeating the CIDR gate. Mitigation depends on deployment always setting REMOTE_ADDR. Not provable in-code.
- **MEDIUM** — Dev session-hash pepper used when `ARCLINK_BASE_DOMAIN` is unset/blank (`python/arclink_api_auth.py:275`–`:283`): blank domain → `production_domain=False` → fixed `"arclink-dev-session-hash-pepper"`. A production deploy that forgets `ARCLINK_BASE_DOMAIN` (and `ARCLINK_SESSION_HASH_PEPPER`/`*_REQUIRED`) silently runs with a publicly-known pepper. Forgeable session/CSRF hashes if an attacker also reads the DB.
- **LOW** — Legacy `sha256_legacy` session/CSRF hashes are still VERIFIED and silently auto-rehashed to HMAC on next auth (`python/arclink_api_auth.py:295`,`:1009`,`:1038`). Back-compat is intentional but means a stolen plain-SHA256 hash from an old DB row is usable until first re-auth.
- **LOW** — `make_arclink_hosted_api_wsgi` opens a fresh `connect_db` per request when no shared `conn` is passed (`python/arclink_hosted_api.py:4319`) and closes it in `finally` (`:4333`); under high QPS this is connection-churn, though correct.
- **INFO** — `_handle_telegram_webhook`/`_handle_discord_webhook` swallow transport-send exceptions and still return 200 (`:2944`,`:2966`,`:3047`) so the provider won't retry forever; durable outbox is the recovery path. Correct by design but a silent-failure surface.
- **INFO** — Generic error mapping returns opaque `"Request blocked…"` / `"unauthorized"` for most exceptions (`:4208`,`:4253`) — good for not leaking internals, but makes some 400s indistinguishable from real validation errors for clients.

## VERDICT
This piece provably does its job. The hosted API is a clean, code-verified
boundary: a single canonical `_ROUTES` table drives both dispatch AND an
OpenAPI 3.1 spec that is CI-guarded byte-identical to the checked-in JSON
(`tests/test_arclink_hosted_api.py:5496`, independently reconfirmed). The auth
model is real and layered — CIDR gate (anti-spoof XFF), per-route session vs
browser-cookie extraction, double-submit CSRF, PBKDF2 passwords (390k iters,
min-12), HMAC-peppered session/CSRF/broker hashes with legacy back-compat,
admin RBAC + conditional MFA, three-bucket login throttling that ignores
caller-asserted subjects, and a deliberate fail-CLOSED Stripe webhook (503 on
unset secret). The transport helpers are disciplined: `enforce_secure_transport`
refuses non-loopback plaintext, and outbound URLs are redacted before logging.
Stripe is fake-by-default via `resolve_stripe_client`; the MCP rpc seam matches
the server byte-for-byte.

Load-bearing strengths: route/OpenAPI parity test, fail-closed money path,
anti-spoof IP resolution, hash-only secret storage. Real weaknesses: the CIDR
gate and the session pepper both have a deployment-topology footgun (empty
`REMOTE_ADDR` / unset `ARCLINK_BASE_DOMAIN`) that the code cannot self-defend
against, and legacy plain-SHA256 hash acceptance remains a small residual
surface. The deepest billing, onboarding, broker-producer, and CIDR-predicate
bodies live in adjacent CANON pieces (07/04/12/01) and are flagged for Codex.
