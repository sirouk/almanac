# CANON-03 — Web App & Product Surface — RECONCILED (Federation truth)

Adjudicator: Claude Opus 4.8 (final, two-model Federation). Method: prove-not-guess — every
disputed point re-opened in code at path:line; code wins over name/comment/prior claim.

- **Codex (GPT-5.5 xhigh) SIGN-OFF:** OBJECT(4) — record substantively sound; needs count
  corrections, URL-risk refinement, one extra WSGI body-cap defect.
- **Federation SIGN-OFF:** BOTH-MODEL-AGREED. Every material point reconciles to one code-grounded
  truth. The previously "standing" XFF/admin-CIDR item is reconciled: it is a CONFIRMED
  conditional risk (the dependency is real in code; the deploy-time XFF behavior is the unproven
  variable, which is itself the finding — not a disagreement between models).

---

## RESOLUTION TABLE (disputed / changed / new — deciding cite is MINE)

| Point | Winner | Deciding cite (re-opened) |
|---|---|---|
| Client route count: record "all 50 paths" is stale | codex | api.ts has 57 `request(...)` call sites (`web/src/lib/api.ts:43-199`; grep=57); all resolve in `_ROUTES` (`arclink_hosted_api.py:3754-3826`). "50" undercounts. |
| Dashboard parallel mount: 11 vs 10 | both (claude-verify + codex) | `dashboard/page.tsx:935-1004` `Promise.all` holds exactly 10 `api.*` calls (userDashboard, userBilling, userProvisioning, userCredentials, userLinkedResources, userShareGrants, userComms, userProviderState, userCrewRecipe, userAcademy). Record "11" wrong. |
| Non-UTF-8 POST body escapes catch-all | both (claude-verify + codex) | `.decode("utf-8")` at `product_surface.py:789` is OUTSIDE the only try/except (which wraps the int() at `:778-781`); `UnicodeDecodeError` propagates out of `app()`. |
| "...traceback leaked to browser body" qualifier | codex | Not proven by ArcLink code — depends on the hosting WSGI server's error renderer; ArcLink emits nothing. Claude-verify's GAP#1 overstated the leak; the *escape-the-catch-all* core is true. |
| Server-URL-as-href: scope is broader than 2 sites | codex | Beyond onboarding/success, dashboard also renders state URLs to href: `dashboard/page.tsx:507-515`, `:2185-2186`, `:2342-2345`, `:2822-2835`. Record cited only 2; risk surface is wider. |
| `javascript:` href execution in the React app | codex | React 19.2.5 `sanitizeURL` rewrites any `javascript:` URL to a throw-expr before `setAttribute` for href (`react-dom-client.production.js:1411-1416, 13004-13006`; `isJavaScriptProtocol` at :1410). So React pages = open-redirect/non-http-nav trust, NOT direct `javascript:` exec. |
| `javascript:` in product_surface (Python) HTML | claude-verify | `html.escape` on hrefs (`product_surface.py:398, 470`) does NOT neutralize `javascript:` scheme — no React sanitizer on server-rendered HTML. (Currently server-generated URLs only → INFO.) |
| GET-with-query routes resolve (not 404) | both | WSGI splits PATH_INFO/QUERY_STRING; dispatcher keys only `route_path` (`arclink_hosted_api.py:3941-3965, 4272-4276`). Record self-doubt closed in record's favor. |
| product_surface column seam: "partial" → fully verified | both (claude-verify + codex) | Read columns (email_hint, current_step, checkout_url, user_id, selected_plan_id, channel_identity, …) all in `ensure_schema` (`arclink_control.py:1309-1331`; `product_surface.py:397-417`). Upgrade CC#8 to BOTH-ENDS-VERIFIED. |
| `resolve_env` precedence / empty alias map / no prod `legacy_key` | both | `arclink_product.py:12, 42-66`; `legacy_key` passed only in tests (`tests/test_arclink_product_config.py:92, 108`). |
| CIDR denial → 403; admin page only handles 401 | both (claude-verify + codex) | 403 at `arclink_hosted_api.py:3986-3988`; admin page special-cases only 401 (`admin/page.tsx:160-164`), 403 → generic "Failed to load admin data." |
| Claude-verify GAP#2 premise: admin gets cookies via `/auth/login` from non-allowlisted IP | neither (refined by me) | FALSE. `/auth/login`→key `login` passes `allow_admin=_backend_client_allowed(...)` (`arclink_hosted_api.py:4030-4039`); with `allow_admin=False` the admin branch is skipped and admin-only emails raise `Invalid ArcLink credentials` (`arclink_api_auth.py:903-922, 943`). Admin login IS IP-gated. The 403-UX gap is still real, but its trigger is narrower (valid admin session that later hits a CIDR-protected route returning 403). |
| Admin-CIDR effectiveness depends on Next forwarding XFF | both (claude-verify + codex) | `_remote_ip_from_headers` trusts XFF only when direct peer is backend-allowed; loopback is backend-allowed (`arclink_hosted_api.py:624-648`). Next rewrites to loopback (`web/next.config.ts:3-14`). No XFF ⇒ direct=127.0.0.1 ⇒ `allow_admin=True` for all + CIDR routes pass for all. CONFIRMED conditional defect. |
| GTB next-action seam cite path | codex | File is `research/ARCLINK_GROUND_TRUTH_BRIEF.md` (confirmed present), not repo root; minor cite hygiene. |

---

## CODEX NEW FINDINGS — CONFIRMED vs REJECTED

**CONFIRMED (net-new federation risk):**
- **LOW — Negative `CONTENT_LENGTH` bypasses the 64KB body cap.** `length=int("-1")=-1`; guard is
  only `length > MAX` (`product_surface.py:782`) so `-1` is not rejected; `read(length)` with
  `length=-1` is truthy and calls `read(-1)` (`product_surface.py:789`), reading the full WSGI
  body unbounded, then dispatches instead of returning 413. Confirmed in code. Severity LOW:
  loopback no-secret prototype, no production caller (DoS-only on a local fixture).

**No Codex new findings rejected.** (Codex's single new finding holds.)

### Claude-verify new gaps — federation disposition
- **CONFIRMED — Non-UTF-8 POST body escapes the catch-all** (`product_surface.py:789` outside
  try/except), with Codex's qualifier applied: the *unhandled `UnicodeDecodeError`* is real; the
  "raw traceback rendered to the browser" is server-dependent and NOT proven by ArcLink code.
  Net severity LOW (prototype, no prod caller).
- **CONFIRMED-with-narrowing — Admin 403 UX gap** (`admin/page.tsx:160-164`): real generic-error
  mishandling of 403. Its premise sentence ("admin authenticates from non-allowlisted IP via
  `/auth/login` and receives admin cookies") is REJECTED — `/auth/login` admin auth is itself
  IP-gated (`arclink_hosted_api.py:4037`; `arclink_api_auth.py:903`). Keep LOW.
- **CONFIRMED — XFF/admin-CIDR dependency** (see resolution table). MEDIUM as a conditional
  control-effectiveness risk; the unproven variable is deploy-time Next proxy XFF behavior.

---

## SEVERITY CHANGES (only where code supports)

| Risk | From | To | Cite |
|---|---|---|---|
| Client-renders-server-URL-as-href | MEDIUM (`javascript:`/open-redirect, 2 sites) | MEDIUM (open-redirect / non-http external-nav trust; React blocks `javascript:`; broader surface) | `react-dom-client.production.js:1411-1416`; `dashboard/page.tsx:507-515, 2185, 2342, 2822` |
| product_surface catch-all hides errors | MEDIUM | MEDIUM (unchanged) + add CONFIRMED LOW corner: non-UTF-8 body + negative CONTENT_LENGTH escape it | `product_surface.py:782, 789` |
| Admin CIDR allowlist effectiveness | (record: OPEN-FOR-CODEX, unrated) | MEDIUM (conditional, XFF-dependent) | `arclink_hosted_api.py:624-648, 3979-3988`; `next.config.ts:3-14` |
| Negative CONTENT_LENGTH body-cap bypass | (absent) | LOW (net-new) | `product_surface.py:782, 789` |

No severity was raised without code support; no over-stated severity in the record survived
(the record's `javascript:`-flavored MEDIUM is re-scoped, not dropped — it stays MEDIUM as
open-redirect/external-nav trust, and remains literally true for product_surface's non-React HTML).

---

## STANDING DISAGREEMENTS

None. Every material point reconciled to one code-grounded truth. The XFF/admin-CIDR item is not a
model-vs-model disagreement — both models agree the in-code dependency is real; the only unknown is
deployment-time Next proxy XFF forwarding, which is the finding itself (a CONFIRMED conditional
risk to verify at deploy), not an unsettleable code dispute.

---

## FINAL BOTH-MODEL VERDICT

CANON-03 is a thin, well-bounded React client over the CANON-02 API, plus a self-contained loopback
Python prototype (FakeStripe default, `127.0.0.1:8088`, fixture seed — **prototype, not production**,
zero production callers) and a real executable copy/secret linter. All security-relevant seams hold
producer-and-consumer (CSRF cookie/header, login session-kind, onboarding browser tokens,
adapter-mode flag, Next-rewrite↔prefix, product_surface column contract). Corrections applied:
client route count is 57 call sites (not "50"); dashboard mounts 10 endpoints (not 11); the
server-URL-as-href risk is open-redirect/external-nav trust (React neutralizes `javascript:`, but
product_surface's `html.escape` does not) across a wider set of sites; the product_surface catch-all
is escaped by both a non-UTF-8 body and a negative `CONTENT_LENGTH` (net-new LOW); the admin CIDR
allowlist is effective only if the Next proxy forwards XFF (MEDIUM, conditional); and the admin page
mishandles 403 (LOW, narrower trigger than first claimed, since `/auth/login` admin auth is itself
IP-gated). **FEDERATION: BOTH-MODEL-AGREED.**
