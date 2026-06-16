# CANON-02 — Hosted API & Transport — ADVERSARIAL VERIFY

Verifier: independent Opus 4.8 skeptic. Method: re-opened every load-bearing
citation in the five tracked files plus the two adjacent ends needed to test the
both-ends-verified contracts (`arclink_mcp_server.py`, `arclink_entitlements.py`).
Counts re-derived by executing AST/`len()` on the live source. Default verdict on
uncertainty was refuted=true; only re-confirmed-in-code claims are marked false.

VERDICT (one line): The record is SUBSTANTIALLY TRUSTWORTHY — its structural
facts, auth model, and the two-end seams all re-confirm in code — but it contains
ONE materially overstated load-bearing claim ("OpenAPI byte-identity"), several
imprecise parentheticals, and it MISSED at least five real defects (broker legacy
SHA-256 acceptance, `enforce_secure_transport` scheme-blindness, rate-limit TOCTOU,
the `/auth/login` admin-gate footgun, the `ARCLINK_COOKIE_SECURE=false` no-op).

================================================================================
## A. CLAIM-BY-CLAIM RE-CONFIRMATIONS (independently re-read in code)
================================================================================

CONFIRMED (refuted=false):
- Route table counts. Executed AST: `len(_ROUTES)=71`, unique suffixes=69,
  `_PUBLIC_ROUTES=18`, `_CIDR_PROTECTED_ROUTES=18`, `_BROKER_AUTH_ROUTES=1`,
  `_JSON_OBJECT_ROUTES=38`; multi-method suffixes exactly `/admin/actions` and
  `/user/share-grants`. All handler keys distinct (71/71).
  (arclink_hosted_api.py:3754, :3829, :3850, :3871, :3875)
- Dispatch order: prefix-strip → OPTIONS preflight (404/405/204) → `_ROUTES.get`
  else 404 → body cap 413 → CIDR gate 403 → webhook/public rate-limit → JSON parse
  → resolve stripe → handler elif chain. (arclink_hosted_api.py:3945-4012)
- WSGI: CONTENT_LENGTH bad→400 invalid_content_length (:4290); body cap BEFORE
  read using declared length (:4299); reads exactly `length` bytes (:4308); folds
  HTTP_*+CONTENT_TYPE to lowercased dict (:4311-4317); REMOTE_ADDR passed (:4330).
- Stripe webhook fail-CLOSED: 503 `stripe_webhook_secret_unset` is the FIRST
  statement of `_handle_stripe_webhook` (:892-904). Bad-signature path raises
  `StripeWebhookError` → 400 (dispatch handler :4209-4216) so Stripe retries.
  CONFIRMED and slightly STRONGER than the record states (record never documented
  the 400 bad-sig path, which is also money-safe).
- Telegram webhook: 503 secret unset (:2894), 401 bad secret-token via
  `hmac.compare_digest` (:2900-2901), swallows send/edit exceptions → 200
  (:2944, :2966). Discord: 503 no public key (:3028), 200 {type:5} on duplicate
  (:3048-3049), 401 other ArcLinkDiscordError (:3050). All confirmed.
- Fleet enrollment callback: Bearer required, 401 missing/bad, 201 on success
  (:2037, :2050). Confirmed.
- Auth credential extraction: read-route header-or-cookie (api_auth:167-181),
  mutation cookie-only (:184-194), CSRF header-required (:197-202). Confirmed.
- Login rate limits: three buckets (:account/:ip/:account_ip) with limits
  login 10/50, admin_login 5/30, user_login 10/50 (:858-859, :899-900, :964-965);
  login_subject is audit-only, NOT a throttle key (docstring :455-458). Confirmed.
- Password: PBKDF2-SHA256, ARCLINK_PASSWORD_ITERATIONS=390_000 (:106), min len 12
  (:328); `verify_arclink_password` returns False on malformed and rejects
  iterations<100k (:343-351). Confirmed.
- Session/CSRF hashes: HMAC-SHA256-peppered `hmac_sha256_v1$...` stored
  (`_hash_session_token` :286), raw token returned once at login (:792, :836).
  User TTL 86400/24h (:769), admin 3600/1h (:799). INSERT into
  arclink_user_sessions (:781). Confirmed.
- Admin mutation path: authenticate → require_arclink_csrf → _admin_mutation_allowed
  (role∈{owner,admin,ops} :84, MFA only if totp_enabled :1054) → `confirm is not
  True` reject (:4880) → 30/60s admin + 12/60s target rate limits → 202
  (api_auth:4877-4901). Confirmed.
- Broker route authenticates ONLY on X-ArcLink-Share-Request-Broker-Token header
  (:1741), no session/CSRF, not CIDR-protected; verifier
  `_authenticate_share_request_broker` (api_auth:2448) checks deployment status,
  enabled flag, `_verify_proof_token_hash` (:2477). Confirmed.
- CORS: emitted only when cors_origin set; ACAC:true (:599); wildcard `*` rejected
  (:372-375); cookie_secure default = not local-http origin (:196). Confirmed.
- `_redact_url_for_error` strips /bot<token>, userinfo, and token|secret|key|
  password|auth query keys (arclink_http.py:24-41). Confirmed.
- MCP rpc seam: BOTH ENDS re-read. Server emits
  `{"content":[{"type":"text","text":json.dumps(result)}],"structuredContent":result}`
  (arclink_mcp_server.py:1837-1838) and sets `mcp-session-id` (:1679); client reads
  `result.structuredContent` (rpc_client:70) / `content[*].text` (:73-87) and
  `mcp-session-id` response header (:36). MATCH. Confirmed both-ends-verified.
- Stripe contract BOTH ENDS re-read: producer passes
  `process_stripe_webhook(conn,payload=,signature=,secret=)` and reads
  `.event_id/.event_type/.user_id/.entitlement_state/.replayed`
  (hosted_api:906-916); consumer signature `(conn,*,payload,signature,secret)`
  (entitlements.py:508-514) and dataclass fields (entitlements.py:157-161) MATCH
  exactly. `verify_stripe_webhook` (adapters:156, owned HERE) is the verifier the
  consumer calls (:515). Replay dedup exists via `_record_webhook_event`
  (entitlements.py:527-537). This contract is MORE verified than the record's
  "partial".
- No alternate route table / second WSGI entry: grep over python/ shows only
  arclink_hosted_api.py defines `route_arclink_hosted_api`,
  `make_arclink_hosted_api_wsgi`, `_CIDR_PROTECTED_ROUTES`. OPEN item #5 resolves
  negative. Confirmed.
- Drift notes the record raised are accurate: stale "12 hours mirrors the
  dashboard session TTL" comment at api_auth:94-95 vs 24h real user TTL; legacy
  sha256_legacy verification + silent rehash (:1009-1013, :1038-1042);
  `_handle_adapter_mode` redundant local re-import.

================================================================================
## B. REFUTATIONS — claims that are WRONG or overstated
================================================================================

REFUTED-1 (load-bearing, MEDIUM): "OpenAPI parity ... asserts byte-identity";
  "byte_identical True"; VERDICT calls it "CI-guarded byte-identical".
  CODE: tests/test_arclink_hosted_api.py:5505-5507 compares
  `json.dumps(spec, sort_keys=True) == json.dumps(static_spec, sort_keys=True)`.
  This is CANONICALIZED-JSON equality, NOT byte-identity of the file. I executed:
  canonical-json equal = True, but `raw_file_bytes == canonical_served_bytes` =
  False. So the checked-in JSON is NOT byte-identical to what is served; the test
  permits whitespace/key-ordering divergence. The security conclusion (a route
  added without regenerating fails the structural check) still holds, but the
  record's specific phrasing "byte-identity / byte-identical True" is FALSE.

REFUTED-2 (imprecise, INFO): "`enforce_secure_transport` runs FIRST (:79)".
  CODE: arclink_http.py:77 the payload-conflict `ValueError` check runs BEFORE
  `enforce_secure_transport` at :79. enforce_secure_transport runs before any
  network I/O (true in spirit) but is NOT the first statement. Self-contradictory
  in the record (it cites :77 for the ValueError on the same line).

REFUTED-3 (imprecise, INFO): "_CIDR_PROTECTED_ROUTES (18, all `admin_*` +
  admin_login/admin_logout)". CODE: one of the 18 is `session_revoke`
  (handler key, route POST /admin/sessions/revoke), which is NOT named `admin_*`.
  The parenthetical "all admin_*" is wrong; it is "all admin_* PLUS session_revoke".

REFUTED-4 (overstated, INFO): contract #7 says http_request importers are
  "11+ modules". CODE: `grep -rln http_request python/` = 10 files; 9 import
  arclink_http. Count overstated (minor).

NOT REFUTED but RE-SCOPED: contracts #2 and #5 are labelled "partial"/"yes"
  appropriately; #2 is actually fully both-ends-verifiable now (see A). No refute.

================================================================================
## C. NEW GAPS — defects NEITHER the record NOR prior docs mention
================================================================================

GAP-1 (MEDIUM): Broker proof tokens ALSO accept LEGACY plain SHA-256.
  `_verify_proof_token_hash` (api_auth:248-257) accepts both HMAC-peppered and
  legacy `_hash_token` (plain SHA-256) digests. The legacy-hash config path
  `_share_request_broker_config` (:2442-2444) returns `{"enabled":True,
  "token_hash":legacy_hash}`. The record's legacy-SHA256 risk only covers
  session/CSRF hashes; it never notes the broker token surface. Worse than the
  session case: broker tokens are NOT rotated on re-auth, so a stolen plain-SHA256
  broker token_hash from a DB row is forgeable indefinitely (the public-agent
  broker route has NO session, NO CIDR — only this header).

GAP-2 (LOW/SSRF-adjacent): `enforce_secure_transport` is scheme-blind beyond
  plaintext http. CODE arclink_http.py:59 `if scheme != "http": return` — it ONLY
  refuses non-loopback `http://`. I executed it: `file:///etc/passwd`,
  `ftp://...`, `gopher://...`, and scheme-less `//host` all PASS (not refused);
  only `http://evil.com` is refused. The urllib fallback (`urllib.request.urlopen`,
  :117) honors `file://`/`ftp://`. So the "secure transport" guard does NOT
  prevent local-file-read / alternate-scheme SSRF if any caller passes an
  attacker-influenced URL. Severity depends on caller URL provenance (most pass
  fixed provider URLs), but the helper is the shared outbound transport for the
  whole repo and is named/contracted more strictly than it behaves.

GAP-3 (LOW): Rate-limit TOCTOU. `check_arclink_rate_limit` (api_auth:408 SELECT
  COUNT → :425 INSERT) and `_check_login_rate_limits` (:481 SELECT → :497 INSERT)
  do check-then-insert with NO BEGIN IMMEDIATE / row lock. Concurrent requests for
  the same subject can each read count<limit before any insert and all pass,
  exceeding the cap. Mitigated by the default single-threaded `wsgiref` server
  (requests serialized) AND per-request fresh connections, but the record itself
  notes the app is meant to run "behind a stronger process manager" (:4364) and
  opens a connection per request — a multi-worker deployment exposes this race.
  Neither record nor prior docs mention it.

GAP-4 (LOW): `/auth/login` silently gates admin login on backend-allowed IP, and
  that gate inherits the empty-REMOTE_ADDR footgun. CODE hosted_api:4031-4038:
  `allow_admin=_backend_client_allowed(cfg, login_client_ip)` where
  login_client_ip = `_remote_ip_from_headers(...)` which falls back to
  "127.0.0.1" when REMOTE_ADDR is empty and no x-real-ip (:635). So on any
  deployment that doesn't set REMOTE_ADDR, the generic `/auth/login` would treat
  the caller as loopback and ENABLE admin login from arbitrary origins. The record
  documents the CIDR-gate footgun (risk #1) but never connects it to the
  `/auth/login` admin-enable path, and never documents that `/auth/login`
  downgrades to user-only off-backend at all (absent from INPUT/OUTPUT contract).

GAP-5 (INFO config footgun): `ARCLINK_COOKIE_SECURE` only disables Secure when the
  value is exactly `"0"`. CODE hosted_api:193-194 `cookie_secure = (raw != "0")`.
  An operator setting `ARCLINK_COOKIE_SECURE=false` (or `no`/`off`) gets
  cookie_secure=True (because "false" != "0"). Counter-intuitive; not flagged.

GAP-6 (INFO/availability): `verify_stripe_webhook` mishandles multi-signature
  headers. CODE adapters.py:160-163 builds `parts[key]=value` in a loop, so for a
  Stripe header carrying multiple `v1=` signatures (which Stripe sends during
  webhook-secret rotation), ONLY THE LAST v1 survives the dict overwrite. Stripe's
  official verifier checks ALL v1 signatures. During a secret rotation a legitimate
  event whose matching signature is not last will FAIL verification → 400 → Stripe
  retries → operator-visible breakage. Not a forgery hole, but a real divergence
  from Stripe semantics on a money path. This code is owned HERE (record's
  contract #2 says the Stripe adapter mechanics are owned in CANON-02).

================================================================================
## D. SEAM MISMATCH CHECK (both-ends contracts attacked)
================================================================================
- #1 CANON-01 IP predicates: call site verified ((str ip,str cidrs)->bool); body
  in CANON-01. The record's "partial" is honest. NOTE: `_remote_ip_from_headers`
  can hand a SPOOFABLE string to the predicate (x-real-ip / XFF), so the seam is
  only as strong as the producer's IP resolution — see GAP-4 and record risk #1.
- #2 CANON-07 Stripe: NO mismatch — keys, signature, dataclass fields all match
  (re-read both ends). UPGRADE the record's "partial" to full.
- #5 CANON-18 MCP: NO mismatch — header name + structuredContent/content shape
  match both ends. Confirmed.
- Fleet callback seam (record didn't list): `_handle_fleet_enrollment_callback`
  forwards UNVALIDATED `x-real-ip`/`x-forwarded-for` as `source_ip` into
  `consume_fleet_enrollment` (hosted_api:2046) on a PUBLIC, non-CIDR route.
  Whatever the consumer (fleet CANON) does with source_ip can be spoofed by any
  caller. Flag for the fleet piece.

================================================================================
## E. RISK SEVERITY CALIBRATION
================================================================================
- Record risk #1 (empty REMOTE_ADDR → x-real-ip trusted → CIDR bypass): MEDIUM is
  fair, but UNDERSTATED — the simpler attack is empty REMOTE_ADDR + NO headers →
  `direct` defaults to "127.0.0.1" → treated as loopback → CIDR gate passes AND
  `/auth/login` admin-enable flips on (GAP-4). Default `wsgiref` always sets
  REMOTE_ADDR, so exposure is real only behind a proxy/ASGI shim that drops it.
- Record risk #2 (dev pepper when ARCLINK_BASE_DOMAIN unset): CONFIRMED at
  api_auth:271-283. MEDIUM fair. Note `example.test` is explicitly whitelisted as
  non-production too (:278), widening the "dev pepper" surface slightly.
- Record risk #3 (legacy sha256 sessions): LOW fair for sessions — but the SAME
  legacy acceptance silently extends to BROKER proof tokens which do NOT self-heal
  on re-auth (GAP-1). Consider broker case MEDIUM.
- Record INFO (webhook swallow→200) and (opaque errors): confirmed, fair.

================================================================================
## F. OVERALL
================================================================================
The CANON-02 record is honest and largely accurate: every structural count, the
layered auth model, the fail-closed money path, and the two cross-piece seams I
could reach both ends of (Stripe, MCP) re-confirm in code. It is safe to rely on
for architecture. BUT do not treat it as complete: the "OpenAPI byte-identity"
phrasing is factually wrong (it is canonical-JSON equality), and it missed a
cluster of real defects — broker legacy-SHA256 acceptance, the scheme-blind
"secure" transport guard, the rate-limit TOCTOU, the `/auth/login` admin-enable
footgun, the `ARCLINK_COOKIE_SECURE=false` no-op, and the Stripe multi-signature
rotation bug. None of these overturn the "this piece does its job" verdict, but
GAP-1 (broker token) and GAP-6 (Stripe rotation) are money/trust-path relevant and
belong in the RISKS register.
