<<<CODEX-FIX-START CANON-03>>>
## CANON-03 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: python/arclink_product_surface.py, tests/test_arclink_product_surface.py, web/package.json, web/public/sw.js, web/src/app/admin/page.tsx, web/src/app/checkout/success/page.tsx, web/src/app/dashboard/page.tsx, web/src/app/onboarding/page.tsx, web/src/lib/api.ts, web/tests/test_page_smoke.mjs, web/tests/test_safe_url.mjs
TESTS: 6 pass; `npm run build` blocked by restricted network fetching Google Font `Space Grotesk`

### Fixed (severity — what — path:line)
- MEDIUM — server-supplied web hrefs now pass through an `http`/`https` navigation allowlist before render/use: `web/src/lib/api.ts:9`, `web/src/app/onboarding/page.tsx:208`, `web/src/app/onboarding/page.tsx:497`, `web/src/app/checkout/success/page.tsx:51`, `web/src/app/checkout/success/page.tsx:267`, `web/src/app/dashboard/page.tsx:500`, `web/src/app/dashboard/page.tsx:2341`, `web/src/app/dashboard/page.tsx:2834`.
- LOW — product_surface negative `CONTENT_LENGTH` no longer reaches `read(-1)`, and invalid UTF-8 no longer escapes WSGI as an unhandled exception: `python/arclink_product_surface.py:793`, `python/arclink_product_surface.py:807`.
- INFO — product_surface server-rendered href attributes now reject non-http schemes before `html.escape`: `python/arclink_product_surface.py:148`, `python/arclink_product_surface.py:407`, `python/arclink_product_surface.py:482`.
- LOW — admin page now distinguishes 403 CIDR/allowlist denials from generic admin load failure: `web/src/app/admin/page.tsx:163`.
- LOW — service worker no longer pre-caches `/dashboard` or `/admin`, and cache version bumped so old cached auth shells are cleared: `web/public/sw.js:1`.

### Skipped (risk-accepted / standing / out-of-scope — why)
- `product_surface` blanket generic catch-all remains: canon labels this surface prototype/not production, and existing tests intentionally preserve secret-free generic errors instead of exposing internal exception text.

### NEEDS-DECISION (ambiguous; left for human)
- Admin CIDR allowlist XFF dependency remains: fixing it likely requires replacing the Next rewrite with a controlled proxy or proving Next standalone forwarding in live deployment. That is a transport-contract change wider than CANON-03 page code.
- Host-level allowlisting for dynamic ArcPod/fleet dashboard URLs remains policy-sensitive. This patch blocks non-http schemes; constraining arbitrary `https://` hosts needs deployment/domain policy for custom domains, worker URLs, and Tailscale/WireGuard lanes.

### Cross-piece edits made (if any) + tests added
- No runtime cross-piece edits.
- Added `web/tests/test_safe_url.mjs`; adjusted `web/tests/test_page_smoke.mjs` and `tests/test_arclink_product_surface.py`.
- Passed: `python3 tests/test_arclink_product_surface.py`, `python3 tests/test_arclink_product_config.py`, `python3 tests/test_arclink_surface_contract.py`, `cd web && npm test`, `cd web && npm run lint`, `cd web && npx tsc --noEmit --pretty false`.
- `cd web && npm run build` failed only because Next could not fetch `Space Grotesk` from Google Fonts in the restricted network.
<<<CODEX-FIX-END CANON-03>>>
