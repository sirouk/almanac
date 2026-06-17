<<<CODEX-VERDICT-START CANON-03>>>
## CANON-03 — Codex (GPT-5.5 xhigh) ratification
SIGN-OFF: OBJECT(4)
ONE-LINE VERDICT: Record is substantively sound, but needs count corrections, URL-risk refinement, and one extra WSGI body-cap defect.

### Adjudication (each: CONFIRM/REFUTE/REFINE + path:line)
- CONFIRM — single browser API funnel: only `fetch` is in `web/src/lib/api.ts:34`; CSRF cookie/header names match hosted producer/consumer (`web/src/lib/api.ts:31-32`, `arclink_hosted_api.py:463-470`, `arclink_api_auth.py:197-201`).
- REFINE — route seam holds, but “all 50 paths” is stale: current `api.ts` has 57 request call sites / 56 expanded unique client paths, all present in `_ROUTES` (`web/src/lib/api.ts:43-199`, `arclink_hosted_api.py:3754-3826`).
- CONFIRM — query-bearing client routes resolve because WSGI splits `PATH_INFO`/`QUERY_STRING` and dispatcher keys only `route_path` (`arclink_hosted_api.py:3941-3965`, `arclink_hosted_api.py:4272-4276`).
- CONFIRM — product_surface direct SQL column seam is both-ends verified: read columns include onboarding `email_hint/current_step/checkout_url/user_id` and schema defines them (`arclink_product_surface.py:397-417`, `arclink_control.py:1309-1331`).
- CONFIRM — `resolve_env` precedence is ARCLINK key, then explicit legacy key, then default; alias map is empty, so ALMANAC-style aliases are vapor unless a caller passes `legacy_key` (`arclink_product.py:12`, `arclink_product.py:42-66`, `arclink_product.py:149-153`).
- CONFIRM — no production `legacy_key` callsite found; only tests pass it (`tests/test_arclink_product_config.py:92`, `tests/test_arclink_product_config.py:108`).
- CONFIRM — dashboard mount count correction: it loads 10 endpoints, not 11 (`web/src/app/dashboard/page.tsx:935-1004`).
- CONFIRM — product_surface blanket catch-all hides handler failures as generic 400 and does not log details (`arclink_product_surface.py:656-763`).
- REFINE — non-UTF-8 POST body escapes that catch-all because decode happens before handler call; confirmed unhandled `UnicodeDecodeError`, but “traceback leaked to browser body” is not proven by ArcLink code (`arclink_product_surface.py:778-790`).
- REFINE — server-supplied URL risk is broader than cited: onboarding, success, dashboard service links, GitHub settings, and billing portal all render API/state URLs to `href` without an app allowlist (`web/src/app/onboarding/page.tsx:488-490`, `web/src/app/checkout/success/page.tsx:268-277`, `web/src/app/dashboard/page.tsx:507-515`, `web/src/app/dashboard/page.tsx:2185-2186`, `web/src/app/dashboard/page.tsx:2342-2345`, `web/src/app/dashboard/page.tsx:2822-2835`).
- REFINE — `javascript:` specifically is blocked by installed React’s URL sanitizer, so this is open-redirect/non-http-scheme trust, not direct React `javascript:` execution (`web/node_modules/react-dom/cjs/react-dom-client.production.js:1410-1415`, `web/node_modules/react-dom/cjs/react-dom-client.production.js:12989-13005`).
- CONFIRM — admin CIDR protection depends on unproven Next proxy XFF forwarding: Next rewrites to loopback (`web/next.config.ts:3-11`); hosted API trusts loopback and substitutes XFF only if present (`arclink_hosted_api.py:624-648`, `arclink_hosted_api.py:3979-3988`).
- CONFIRM — admin 403 UX is generic: hosted API returns 403 on CIDR denial, but admin page special-cases only 401 (`arclink_hosted_api.py:3986-3988`, `web/src/app/admin/page.tsx:159-164`).
- CONFIRM — SW risk is low: `/dashboard` and `/admin` shells are pre-cached, while `/api/` is bypassed (`web/public/sw.js:2-6`, `web/public/sw.js:28-42`).
- CONFIRM — web CI seam exists: install-smoke runs web lint, node tests, and build (`.github/workflows/install-smoke.yml:62-67`; `web/package.json:5-11`).
- REFINE — GTB next-action seam cite path is `research/ARCLINK_GROUND_TRUTH_BRIEF.md`, not repo root; alternation matches the code regex terms (`research/ARCLINK_GROUND_TRUTH_BRIEF.md:81-83`, `python/arclink_surface_contract.py:41-43`).

### New findings both Claude passes missed (severity + path:line)
- LOW — negative `CONTENT_LENGTH` bypasses the product_surface body cap: only `length > MAX` is rejected, so `read(-1)` can read an over-limit WSGI body and dispatch instead of 413 (`arclink_product_surface.py:778-790`).

### Claude citations re-confirmed or corrected
- Re-confirmed CSRF seam, login session-kind redirect, onboarding-start payload, adapter-mode flag, Next rewrite/prefix, surface contract linter, manifest/layout/PWA/SW behavior (`web/src/lib/api.ts:18-40`, `arclink_api_auth.py:1101-1105`, `web/src/app/login/page.tsx:22-24`, `arclink_hosted_api.py:2345-2349`, `web/src/app/manifest.ts:3-26`, `web/src/components/pwa-register.tsx:7-10`).
- Corrected stale counts: client route count is 56 expanded unique paths, dashboard parallel mount calls are 10, not 11 (`web/src/lib/api.ts:43-199`, `web/src/app/dashboard/page.tsx:935-1004`).
- Re-confirmed prototype posture from executable defaults: local host/port defaults and FakeStripe app construction (`arclink_product_surface.py:817-828`).

### Residual disagreement with the Claude half (for final reconciliation)
- The record should not say “all 50 api.ts paths”; use “all current client paths, 56 expanded unique, resolve server-side.”
- The URL risk should drop the unqualified `javascript:` claim for React-rendered hrefs, but keep MEDIUM for server-chosen external navigation and non-React product_surface hrefs.
- The XFF/admin-CIDR issue remains unratified until the deployed Next proxy behavior is proven, not inferred.
<<<CODEX-VERDICT-END CANON-03>>>
