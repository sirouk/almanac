# CANON-03 — Web App & Product Surface — ADVERSARIAL VERIFY

Auditor: independent skeptic. Method: re-opened every cited file, re-derived load-bearing
claims at path:line, traced both ends of each cross-piece seam, hunted unhappy paths.

Overall verdict: **RECORD IS TRUSTWORTHY (with corrections).** The structural claims, all
six security-relevant seams, and the "prototype, not production" finding are independently
re-confirmed in code. I found NO load-bearing refutation. I did find: (a) one factual miscount
(10 vs 11 mount endpoints), (b) several record self-doubts that are actually verifiable and
resolve in the record's favor, and (c) THREE gaps neither the record nor prior docs mention —
the most important being a non-UTF-8 POST body that escapes the product_surface catch-all, and
the admin page mishandling the 403 CIDR-denial status.

---

## A. CLAIM-BY-CLAIM RE-VERIFICATION

### Confirmed (re-read at path:line)

- **Single funnel / no rogue fetch.** `rg "fetch("/"XMLHttpRequest|EventSource|sendBeacon|WebSocket"`
  over `web/src` returns ONLY `web/src/lib/api.ts:34`. Confirmed (record §15, self-check #2).
- **CSRF-only client credential.** api.ts:31 reads `arclink_${kind}_csrf`, sets header
  `X-ArcLink-CSRF-Token` (api.ts:32). Producer hosted_api.py:463-472 sets `arclink_{kind}_csrf`
  **non-HttpOnly** (csrf_flags) while session_id/session_token are HttpOnly. Server reads
  `x-arclink-csrf-token` (api_auth.py:101, 199). Names match EXACTLY. Test test_api_client.mjs:414-417
  asserts no Session-Id / Authorization header, CSRF present. BOTH ENDS VERIFIED. (record CC#1)
- **Onboarding-start 201 payload.** Producer api_auth.py:1101-1105 returns
  `{session, browser_claim_token, browser_cancel_token}`; consumer onboarding/page.tsx:178-184
  reads those three keys on status===201. BOTH ENDS VERIFIED. (record CC#3)
- **Login session-kind redirect.** Producer api_auth.py:920-921/939-940 returns 201
  `{session, session_kind, role}`; consumer login/page.tsx:23-25 routes on session_kind. BOTH
  ENDS VERIFIED. (record CC#4)
- **adapter-mode flag.** Producer hosted_api.py:2345-2349 returns `{fake_mode, fake_stripe}`;
  consumer onboarding/page.tsx:79 reads fake_mode. BOTH ENDS VERIFIED. Note: producer actually
  returns TWO keys (`fake_mode` AND `fake_stripe`); record cited only `fake_mode` (the consumed
  one) — accurate. (record CC#5)
- **Next rewrite ↔ hosted prefix.** next.config.ts:3,10-11 rewrites `/api/v1/:path*` →
  `${ARCLINK_API_INTERNAL_URL||http://127.0.0.1:8900}/api/v1/:path*`. HOSTED_API_PREFIX="/api/v1"
  (hosted_api.py:167); dispatcher strips it (hosted_api.py:3945-3947). api.ts:1 default
  API_BASE="/api/v1". BOTH ENDS VERIFIED. (record CC#6)
- **All ~50 api.ts paths exist in `_ROUTES`.** I extracted every `request(...)` path from api.ts
  and diffed against `_ROUTES` (hosted_api.py:3754-3826). Every client path (incl. dynamic
  `/auth/${kind}/logout` → user/admin, `adminDashboard?qs`, `checkoutStatus?session_id=...`)
  maps to a route key. `_ROUTES` is a SUPERSET (it also has webhooks, refuel-checkout, broker/
  claim/nonce share routes, public-bot-checkout, openapi — not called by the web client). No
  client path is missing server-side. BOTH ENDS VERIFIED. (record CC#2)
- **product_surface column contract.** Columns read by direct SQL (email_hint, display_name_hint,
  selected_model_id, current_step, checkout_url, user_id, selected_plan_id, channel_identity) ALL
  exist in `ensure_schema` arclink_control.py:1309+. Record marked CC#8 "partial / not re-proven";
  I re-proved it — UPGRADE to both-ends-verified. (record CC#8, OPEN-FOR-CODEX #3)
- **resolve_env precedence.** product.py:56-66 — present-nonempty key wins; else nonempty legacy;
  else default(source="default"). conflict=True only on primary-key branch when legacy differs
  (product.py:62). ARCLINK_ENV_ALIASES={} (product.py:12). Confirmed (record §23, DRIFT#5, INFO).
- **launch_phrase.** product.py:138-146 lowercase/strip, map → phrase, fallback
  "Tracking your launch." Confirmed.
- **surface_contract_issues checks.** surface_contract.py:96-140 — empty, length, secret patterns
  (L16-26), traceback (L28-32), chat backtick/HTML, captain forbidden (L120-123), required/proof/
  forbidden terms, blocked-needs-next-action (L136-140). assert raises AssertionError (L145-151).
  Confirmed (record §31).
- **product_surface WSGI body cap.** MAX_PRODUCT_SURFACE_BODY_BYTES=64*1024 (L46); 413 when
  CONTENT_LENGTH exceeds (L782-787). Confirmed.
- **FakeStripe default / loopback / fixture seed.** stripe default FakeStripeClient (L653, 826);
  CLI binds 127.0.0.1:8088 (L818-819, 827-828); seed writes full fixture (L70-134). Confirmed.
- **next.config output standalone; manifest; layout; sw.js.** output:"standalone" (next.config.ts:6);
  manifest name "ArcLink", start_url "/", display standalone, theme #080808, Favicon.png 512
  maskable + Arclink-share.png (manifest.ts:4-26); metadataBase default https://arclink.online
  (layout.tsx:21); sw.js bypasses /api/ (sw.js:32), network-first cache fallback to "/" (sw.js:34-42),
  pre-caches /dashboard /admin /onboarding (sw.js:3-6). Confirmed (record §43-45, DRIFT#7).
- **Line-count / cite drifts (record DRIFT 1-4).** Re-confirmed: product_surface.py is 834 lines,
  main() at L815; checkout copy "your Hermes Agent Dashboard moves into the launch queue"
  (L435); nav is Onboarding/Captain Dashboard/Admin/API (L305-308); _ADMIN_ACTION_LABELS at
  L508-521 (12 labels). All record drift corrections are accurate.
- **"prototype, not production" verdict.** `git grep` for production callers of
  `arclink_product_surface` / `make_arclink_product_surface_app` outside the module + tests
  returns ZERO. Only references are docs, research, and a docstring in hosted_api.py:8 ("remains
  a local..."). NO Dockerfile/sh/yml/bin entrypoint launches main(). CONFIRMED in code.
  (record VERDICT, OPEN-FOR-CODEX #4)

### Record self-doubts that RESOLVE (record under-claimed; not refutations, but corrections)

- **Self-check #1 / OPEN-FOR-CODEX #1 (GET-with-query routing).** Record said "did not execute
  the dispatcher." VERIFIED IN CODE: the dispatcher takes `path` and `query` as SEPARATE args;
  `route_key = _ROUTES.get((clean_method, route_path))` where route_path is derived only from
  `path` (hosted_api.py:3941-3947, 3965). At the WSGI layer PATH_INFO/QUERY_STRING are split
  (hosted_api.py:4274-4275). So `?session_id=`, `?trainee_id=`, `?qs` GET routes RESOLVE — they
  do NOT 404. CONCERN CLOSED in record's favor.
- **DRIFT #6 (globals.css tokens).** Record "did not open globals.css line-by-line." VERIFIED:
  globals.css:4-11 `@theme` defines --color-jet/carbon/soft-white/signal-orange/electric-blue/
  neon-green/surface/border + font tokens. Every token used by ui.tsx / success page (neon-green,
  signal-orange, surface, border, jet, carbon, soft-white) IS defined. CONCERN CLOSED.

### Numeric REFUTATION (minor, factual)

- **REFUTED — "Loads 11 endpoints in parallel on mount" (record §18, dashboard/page.tsx:935-1004).**
  The mount `Promise.all` contains exactly **10** api calls (userDashboard, userBilling,
  userProvisioning, userCredentials, userLinkedResources, userShareGrants, userComms,
  userProviderState, userCrewRecipe, userAcademy). Counted via grep over 935-1010. The "11" is
  off by one. Low severity, but it is a factual miscount in the record.

---

## B. CROSS-PIECE SEAM ATTACKS

Attacked every both-ends-verified seam. Result: all six security-relevant seams hold. The route
table is a clean superset. No client path is orphaned server-side; no server route the client
calls is missing. The only seam the record marked "partial" (CC#8 column existence) I upgraded to
fully verified.

### NEW seam concern (record missed): CIDR admin protection depends on Next proxy forwarding XFF

- **MEDIUM — Admin CIDR protection effectiveness is unverified at the CANON-03 proxy seam.**
  Admin routes are CIDR-gated (`_CIDR_PROTECTED_ROUTES`, hosted_api.py:3850-3869) and return
  **403** on denial (hosted_api.py:3986-3988). The CANON-03 web client reaches the API only via
  the next.config.ts rewrite to `http://127.0.0.1:8900` — i.e. the hosted API's DIRECT peer is
  loopback. `_backend_client_allowed` returns True for loopback (hosted_api.py:646-647), and
  `_remote_ip_from_headers` only substitutes the real client IP when `X-Forwarded-For` is present
  AND the direct peer is trusted (hosted_api.py:624-641). The CIDR allowlist therefore protects
  admin routes ONLY IF the Next.js standalone rewrite proxy forwards the original client's
  `X-Forwarded-For`. Nothing in any CANON-03 file (next.config.ts, deploy notes) establishes that
  Next rewrites forward XFF; Next.js rewrites are not guaranteed to add client-XFF. If they do
  not, `forwarded=""`, `direct=127.0.0.1` → loopback → allowed → **CIDR check passes for every
  public client** and the admin allowlist is silently neutered. The producer side (CANON-02) is
  correctly fail-safe given XFF; the missing proof is on the CANON-03 proxy side. The record
  flagged the CIDR routes (OPEN-FOR-CODEX #2) but never connected the loopback-proxy interaction.
  Severity MEDIUM because the whole admin-allowlist control hinges on an unproven proxy behavior.

---

## C. NEW GAPS (neither record nor prior docs mention)

1. **LOW/MEDIUM — Non-UTF-8 POST body escapes the product_surface catch-all → unhandled 500 /
   traceback leak.** The blanket `except Exception: return _generic_error_response(route)` lives
   INSIDE `handle_arclink_product_surface_request` (product_surface.py:762-763). But the WSGI
   wrapper decodes the body BEFORE calling the handler:
   `body = environ["wsgi.input"].read(length).decode("utf-8")` (product_surface.py:789), and the
   only try/except in `app()` wraps the CONTENT_LENGTH int() conversion (L778-781), NOT the decode.
   A POST with a non-UTF-8 byte raises `UnicodeDecodeError` that propagates out of `app()` to the
   WSGI server → 500 with a Python traceback. This is exactly the "raw traceback leaked into
   rendered text" failure the surface_contract linter (surface_contract.py:28-32) and the catch-all
   exist to prevent — and it bypasses both. The record's MEDIUM "catch-all hides errors" risk
   actually UNDER-states this corner: not all errors are even caught. Severity capped at LOW/MEDIUM
   only because product_surface is a loopback no-secret prototype with no production caller.

2. **LOW — Admin web page mishandles the 403 CIDR-denial status.** CIDR denial returns **403**
   (hosted_api.py:3986). The admin page only special-cases 401 → `router.push("/login")`
   (admin/page.tsx:162); a 403 falls through to `else setError("Failed to load admin data.")`
   (admin/page.tsx:163). An admin who authenticates successfully (via the NON-CIDR-gated
   `/auth/login`, route key `login`, which is not in `_CIDR_PROTECTED_ROUTES`) from a
   non-allowlisted IP receives admin cookies, lands on `/admin`, then sees a generic "Failed to
   load admin data." with no signal that IP allowlisting is the cause and no recovery path. Silent,
   misleading failure mode. The record left this as OPEN-FOR-CODEX #2 without assessing the actual
   browser-visible behavior; the behavior is a generic error with no 403 handling.

3. **INFO — `html.escape` in href context does not block `javascript:` scheme.** product_surface
   renders `<a href="{escape(session['checkout_url'])}">` (product_surface.py:398) and user-dashboard
   access links `<a href="{escape(str(link.get('url')))}">` (product_surface.py:470). `html.escape`
   neutralizes `" & < >` but NOT a `javascript:`/`data:` scheme. In the prototype these URLs are
   server-generated (Stripe `checkout.url`, dashboard access links), so not currently attacker-
   controlled — INFO only, and it mirrors the record's web-app MEDIUM #2. Worth noting the record's
   secrets-handling line ("escapes user data with html.escape throughout") implies safety that does
   not extend to URL-scheme attributes.

---

## D. RISK SEVERITY RE-CALIBRATION

- Record MEDIUM "client trusts server-supplied checkout_url as href" — **CONFIRMED & well-calibrated.**
  Traced: `checkout_url` = `checkout.get("url")` straight from the Stripe client
  (arclink_onboarding.py:689), stored unvalidated, returned in payload, rendered as
  `<a href={checkoutUrl}>` (onboarding/page.tsx:488-489) and success-page
  `<a href={urls.hermes||urls.dashboard}>` (checkout/success/page.tsx:269-278). The server-side
  `_safe_stripe_redirect_url` (hosted_api.py:775-786) sanitizes ONLY the success_url/cancel_url
  INPUTS to Stripe, NOT the returned checkout_url. The record's exact caveat holds. Keep MEDIUM.
- Record MEDIUM "catch-all hides errors" — **CONFIRMED**, and see NEW GAP #1 (it under-states:
  the decode error isn't even caught).
- Record LOW "sw pre-caches /admin /dashboard" — confirmed harmless (skeleton only, /api bypassed).
- Record INFO "ARCLINK_ENV_ALIASES empty" / "fixture secret:// placeholder" — confirmed.
- No over-stated severities found.

---

## E. RESIDUAL DISAGREEMENTS

1. The "11 endpoints" miscount (it is 10). Minor but factual.
2. CC#8 should be promoted from "partial" to fully both-ends-verified (column existence proven in
   ensure_schema arclink_control.py:1309+).
3. Self-check #1 / OPEN-FOR-CODEX #1 is resolvable in code (query is split at WSGI layer; routes
   resolve) — the record's lingering doubt is unnecessary.

## VERDICT
The record is accurate and its security analysis is sound. Every both-ends-verified seam holds on
re-inspection; the headline risks (server-URL-as-href, blanket catch-all, prototype posture) are
real and correctly calibrated. Corrections: one numeric miscount (10 not 11 mount endpoints), and
three previously-unlisted gaps — the non-UTF-8 body escaping the catch-all (NEW GAP #1, the
sharpest), the admin page's silent 403 mishandling (NEW GAP #2), and the unproven Next-proxy XFF
forwarding that the admin CIDR allowlist silently depends on (SEAM, MEDIUM). None of these
overturn the record; they harden it. TRUSTWORTHY.
