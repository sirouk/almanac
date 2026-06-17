# CANON-02 — Hosted API & Transport — RECONCILED (both-model truth)

Adjudicator: Claude Opus 4.8 (1M) FINAL ADJUDICATOR, ArcLink two-model Federation.
Method: every DISPUTED point, every Codex REFUTE/REFINE/NEW-FINDING, and every
residual disagreement was re-opened in source by this adjudicator (Read on the
exact path:line). Code wins over comment/name/prior-claim. Codex CONFIRM items
where both models already agreed are ratified one-line, not re-derived.

- Codex (GPT-5.5 xhigh) SIGN-OFF: **OBJECT(3)** — core ratified; objected to (a)
  importer-count wording, (b) proxy/topology wording, (c) two WSGI malformed-body lows.
- Adjudicator FEDERATION SIGN-OFF: **BOTH-MODEL-AGREED** — every material point
  reconciled to one code-grounded truth; no standing disagreement survives.

All three of Codex's objections are CONFIRMED in code and ABSORBED into this
reconciled record, so OBJECT(3) collapses to agreement once applied.

================================================================================
## RESOLUTION TABLE (point | winner | deciding cite — re-read by adjudicator)
================================================================================

| Point | Winner | Deciding cite (adjudicator re-read) |
|---|---|---|
| OpenAPI parity is canonical-JSON equality, NOT byte-identity ("byte_identical True" is FALSE) | codex + claude-verifier | `tests/test_arclink_hosted_api.py:5505-5507` — `json.dumps(spec,sort_keys=True)==json.dumps(static_spec,sort_keys=True)` |
| Route counts: 71 `_ROUTES`, 69 suffixes, public=18, CIDR=18, broker=1, JSON=38 | both | `python/arclink_hosted_api.py:3850-3869` (CIDR set, 18 members), `:3871-3873`, `:3875+` |
| `_CIDR_PROTECTED_ROUTES` is "all admin_* PLUS `session_revoke`" (record's "all admin_*" parenthetical wrong) | codex + claude-verifier | `python/arclink_hosted_api.py:3865` — `session_revoke` is in the set, not named `admin_*` |
| `http_request` reach: 10 files mention, 9 real importers (record's "11+ modules" overstated) | codex + claude-verifier | record cite vs Codex grep; defining file is `python/arclink_http.py:66`, consumer e.g. `python/arclink_rpc_client.py:8` |
| `enforce_secure_transport` is NOT the literal first statement (ValueError check precedes it) | claude-verifier | `python/arclink_http.py:77` (ValueError) precedes `:79` (enforce). Runs before network I/O — true in spirit only |
| Stripe seam fully both-ends-verified (upgrade record's "partial" → full) | codex + claude-verifier | producer `python/arclink_hosted_api.py:906-916`; consumer `python/arclink_entitlements.py:155-161`,`:508-515` |
| MCP seam fully both-ends-verified | both | `python/arclink_rpc_client.py:21-36`,`:69-87`; `python/arclink_mcp_server.py:1673-1680`,`:1835-1839` |
| CIDR predicates fail closed on malformed IP/CIDR; IPv4/IPv6 via `ipaddress` (resolves OPEN #1) | codex | `python/arclink_control.py:7604-7625` — try/except ValueError → False, `ipaddress` types |
| Web client reads non-HttpOnly csrf cookie + echoes `X-ArcLink-CSRF-Token` w/ credentials (resolves OPEN #3) | codex | `web/src/lib/api.ts:31-32`,`:37` |
| `_remote_ip_from_headers` empty-REMOTE_ADDR → x-real-ip → "127.0.0.1" fallback (risk #1) | both | `python/arclink_hosted_api.py:635` |
| RISK BROADER than "empty only": trusted-proxy-WITHOUT-XFF also collapses gate to proxy IP | codex | `python/arclink_hosted_api.py:635-641` — `direct` returned when no XFF; proxy IP is `direct` when it's the peer |
| Dev pepper used when `ARCLINK_BASE_DOMAIN` unset (risk #2) — real in code; canonical deploy lanes set/require pepper | both (codex adds deploy context) | `python/arclink_api_auth.py:271-283`; deploy lanes `compose.yaml:77-78`,`bin/deploy.sh`,`bin/docker-entrypoint.sh` (claimed by Codex, not re-opened by adjudicator) |
| No HIGH risk present in CANON-02 register | both | full register review; no item rises to HIGH |

================================================================================
## CONFIRMED Codex new-findings (re-verified true → net-new federation risks)
================================================================================

- **LOW — Negative CONTENT_LENGTH bypasses the WSGI pre-read body cap.**
  `length = int(...)` (`python/arclink_hosted_api.py:4289`); cap is only
  `if length > body_limit` (`:4299`); a negative declared length passes the cap,
  then `wsgi.input.read(length)` (`:4308`) — `read(-1)` consumes the entire body
  before downstream routing rejects it. Re-read 4289-4308: CONFIRMED. (Default
  `wsgiref` clamps CONTENT_LENGTH, so live exposure is proxy/shim-dependent.)

- **LOW — Non-UTF-8 WSGI body raises UnicodeDecodeError outside error mapping → unstructured 500.**
  `body = environ["wsgi.input"].read(length).decode("utf-8") ...` (`:4308`) is
  outside the only surrounding `try` (4288-4290 catches `ValueError` for the
  CONTENT_LENGTH parse) and before the dispatcher's error mapping
  (`route_arclink_hosted_api` handler chain). A non-UTF-8 body throws before any
  JSON-400 path. Re-read 4288-4337: CONFIRMED — no except wraps the decode; the
  `try` at 4320 has only a `finally` (close conn).

- **INFO — URL redaction is transport-error-only; parse/status errors leak raw URL.**
  Transport failures redact (`python/arclink_http.py:102`,`:131`), but
  `parse_json_response` raises `RuntimeError(f"{label} returned invalid json: ...")`
  (`:139`) and `mcp_call` passes `label=url` (`python/arclink_rpc_client.py:29`),
  so a malformed/oversized MCP response surfaces the raw (unredacted) URL in the
  error. Re-read both: CONFIRMED. Distinct surface from the record's redaction claim.

(Codex also re-confirmed — not new — the two claude-verifier MEDIUM/LOW findings:
broker legacy SHA-256 acceptance `python/arclink_api_auth.py:248-257`,`:2442-2444`;
Stripe last-`v1` overwrite `python/arclink_adapters.py:159-172`,`:171`. Both
re-read by adjudicator and CONFIRMED — carried below as already-federation risks.)

================================================================================
## REJECTED Codex new-findings
================================================================================
(none — all three Codex new-findings re-verified true in code.)

================================================================================
## CARRIED claude-verifier findings re-ratified by adjudicator
================================================================================
- **MEDIUM — Broker proof tokens accept legacy plain SHA-256, no self-heal.**
  `_verify_proof_token_hash` (`python/arclink_api_auth.py:248-257`) falls through
  to `_hash_token` (plain SHA-256) for non-HMAC stored hashes; legacy config
  `_share_request_broker_config` returns `{"enabled":True,"token_hash":legacy_hash}`
  (`:2442-2444`). Broker route is header-only (no session, no CIDR)
  (`python/arclink_hosted_api.py:1739-1742`) and tokens are NOT rotated on
  re-auth → a stolen plain-SHA256 broker `token_hash` is forgeable indefinitely.
  Re-read: CONFIRMED. Codex CONFIRMS. Money/trust-path → keep MEDIUM.
- **INFO/availability — Stripe multi-signature header collapses to last `v1`.**
  `verify_stripe_webhook` builds `parts[key]=value` in a loop (`adapters.py:159-163`)
  so multiple `v1=` signatures overwrite to the last; check is only
  `parts.get("v1","")` (`:171`). Diverges from Stripe's "verify ALL v1" semantics;
  during webhook-secret rotation a legit event can 400 → retries. Re-read: CONFIRMED.
- **LOW — Rate-limit TOCTOU.** SELECT COUNT (`api_auth:408-415`) then INSERT
  (`:425`) with no row lock / BEGIN IMMEDIATE. Concurrent same-subject requests can
  all read count<limit and pass. Re-read: CONFIRMED. Mitigated by single-threaded
  wsgiref + per-request conn; real under multi-worker.
- **LOW — `/auth/login` admin-enable inherits the empty-REMOTE_ADDR footgun.**
  `allow_admin=_backend_client_allowed(cfg, login_client_ip)` with
  `login_client_ip=_remote_ip_from_headers(...)` (`hosted_api:4031-4038`) → on a
  deployment that drops REMOTE_ADDR (and no x-real-ip), `direct`→"127.0.0.1"
  (`:635`) → admin login enabled from arbitrary origins. Re-read: CONFIRMED.
- **INFO — `ARCLINK_COOKIE_SECURE=false` no-op.** `cookie_secure = (raw != "0")`
  (`hosted_api:193-194`); `"false"!="0"` → Secure stays True. Re-read: CONFIRMED.
- **GAP-2 — `enforce_secure_transport` scheme-blind (LOW/SSRF-adjacent).**
  `if scheme != "http": return` (`arclink_http.py:59`) refuses only non-loopback
  http://; file://, ftp://, gopher://, scheme-less //host all pass; urllib
  fallback honors file://. Re-read: CONFIRMED. Severity bounded by caller URL
  provenance (most pass fixed provider URLs).

================================================================================
## SEVERITY CHANGES (only where code supports — from → to, cited)
================================================================================
| Risk | From | To | Cite |
|---|---|---|---|
| Broker proof token legacy SHA-256 acceptance | (record: not listed; folded under LOW session-hash risk) | MEDIUM | `python/arclink_api_auth.py:248-257`,`:2442-2444`; `python/arclink_hosted_api.py:1739-1742` |
| OpenAPI "byte-identity" load-bearing claim | (record asserted as a strength) | corrected to canonical-JSON equality (claim de-rated, not a risk) | `tests/test_arclink_hosted_api.py:5505-5507` |
| CIDR-gate / `/auth/login` REMOTE_ADDR footgun | MEDIUM (empty-only framing) | MEDIUM (broadened: also trusted-proxy-without-XFF) | `python/arclink_hosted_api.py:635-641`,`:4031-4038` |

No risk is raised to HIGH; both models agree CANON-02 carries no HIGH item
(adjudicator concurs after full register re-read).

================================================================================
## STANDING DISAGREEMENTS
================================================================================
(none — every material point reconciled to a single code-grounded truth.)

================================================================================
## FINAL BOTH-MODEL VERDICT
================================================================================
CANON-02 provably does its job and is safe to rely on for architecture: a single
canonical `_ROUTES` table drives both dispatch and a CI-checked OpenAPI 3.1 spec
(canonical-JSON equality, NOT byte-identity — the record's "byte-identical"
phrasing is corrected); a layered, code-real auth model (anti-spoof IP
resolution, per-route session-vs-cookie extraction, double-submit CSRF confirmed
both ends at `web/src/lib/api.ts:31-32`, PBKDF2 390k passwords, HMAC-peppered
hashes, RBAC + conditional MFA, three-bucket login throttle, fail-closed 503/400
Stripe webhook); and disciplined transport (loopback-only plaintext refusal,
redacted transport-error logging). CIDR predicates fail closed on malformed input
(`arclink_control.py:7604-7625`), resolving the record's OPEN-FOR-CODEX #1.

Reconciled weaknesses (federation-accepted): broker legacy-SHA256 acceptance
(MEDIUM, no self-heal), the REMOTE_ADDR / `/auth/login` admin-enable
deployment-topology footgun (MEDIUM, broadened to trusted-proxy-without-XFF), the
scheme-blind "secure" transport guard, the rate-limit TOCTOU, the
`ARCLINK_COOKIE_SECURE=false` no-op, the Stripe multi-signature rotation bug
(INFO/availability), and Codex's two WSGI malformed-body lows (negative
CONTENT_LENGTH cap bypass; non-UTF-8 → unstructured 500) plus parse-error URL
leak (INFO). None overturn the "this piece does its job" verdict; GAP-1 (broker
token) and the Stripe rotation bug are the money/trust-path items for the RISKS
register.

FEDERATION SIGN-OFF: **BOTH-MODEL-AGREED.**

---

<!-- CANON-REPAIR-STATUS:START -->
## Repair status

> Refreshed from [`research/canon/fixes/CANON-02-hosted-api-transport.fix.md`](../fixes/CANON-02-hosted-api-transport.fix.md) (active untracked). The audit findings above remain the adjudicated spec; this block records the repair campaign state for this piece.

- Status: completed, active uncommitted repair workspace.
- Summary: 8 fixed / 0 skipped / 2 needs-decision.
- Tests: 7 files run, all pass; py_compile and git diff --check pass
- Representative fixes:
  - MEDIUM — broker share-request auth now rejects legacy plain SHA-256 proof-token hashes while preserving legacy proof-token compatibility for non-broker flows — `python/arclink_api_auth.py:249`, `python/arclink_api_auth.py:2502`.
  - MEDIUM — empty `REMOTE_ADDR` no longer falls back to attacker-controlled `X-Real-IP` or loopback for CIDR/admin-login decisions — `python/arclink_hosted_api.py:644`, `python/arclink_hosted_api.py:4460`.
  - LOW — login rate-limit buckets now wrap SELECT→INSERT in `BEGIN IMMEDIATE`, closing the remaining throttle TOCTOU path — `python/arclink_api_auth.py:493`.
- Needs decision:
  - MEDIUM — `ARCLINK_BASE_DOMAIN` unset still permits the documented dev pepper fallback unless `ARCLINK_SESSION_HASH_PEPPER_REQUIRED=1`; making unset domain fail closed changes local/dev direct-use behavior, while canonical deploy lanes already set/generate the pepper and required flag.
  - MEDIUM — trusted proxy without `X-Forwarded-For` still collapses to the proxy IP; fixing this cleanly needs a separate proxy-vs-admin-CIDR contract because current `ARCLINK_BACKEND_ALLOWED_CIDRS` represents both direct allowed clients and trusted peers.
<!-- CANON-REPAIR-STATUS:END -->
