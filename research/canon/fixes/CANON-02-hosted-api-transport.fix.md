<<<CODEX-FIX-START CANON-02>>>
## CANON-02 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: python/arclink_api_auth.py, python/arclink_hosted_api.py, python/arclink_http.py, tests/test_arclink_api_auth.py, tests/test_arclink_hosted_api.py, tests/test_arclink_http.py
TESTS: 7 files run, all pass; py_compile and git diff --check pass
### Fixed (severity — what — path:line)
- MEDIUM — broker share-request auth now rejects legacy plain SHA-256 proof-token hashes while preserving legacy proof-token compatibility for non-broker flows — `python/arclink_api_auth.py:249`, `python/arclink_api_auth.py:2502`.
- MEDIUM — empty `REMOTE_ADDR` no longer falls back to attacker-controlled `X-Real-IP` or loopback for CIDR/admin-login decisions — `python/arclink_hosted_api.py:644`, `python/arclink_hosted_api.py:4460`.
- LOW — login rate-limit buckets now wrap SELECT→INSERT in `BEGIN IMMEDIATE`, closing the remaining throttle TOCTOU path — `python/arclink_api_auth.py:493`.
- LOW — WSGI negative `CONTENT_LENGTH` is rejected before body read, and non-UTF-8 bodies return structured JSON 400 — `python/arclink_hosted_api.py:4410`, `python/arclink_hosted_api.py:4428`.
- LOW — `enforce_secure_transport` now rejects non-HTTPS alternate schemes and schemeless URLs, allowing only HTTPS or loopback HTTP — `python/arclink_http.py:56`.
- INFO — `ARCLINK_COOKIE_SECURE=false/no/off` now actually disables Secure cookies — `python/arclink_hosted_api.py:399`.
- INFO — JSON parse/status errors now redact URL labels before raising — `python/arclink_http.py:134`.
- INFO/availability — Stripe multi-`v1` verification was already fixed in the current tree and re-verified — `python/arclink_adapters.py:160`.
### Skipped (risk-accepted / standing / out-of-scope — why)
- None.
### NEEDS-DECISION (ambiguous; left for human)
- MEDIUM — `ARCLINK_BASE_DOMAIN` unset still permits the documented dev pepper fallback unless `ARCLINK_SESSION_HASH_PEPPER_REQUIRED=1`; making unset domain fail closed changes local/dev direct-use behavior, while canonical deploy lanes already set/generate the pepper and required flag.
- MEDIUM — trusted proxy without `X-Forwarded-For` still collapses to the proxy IP; fixing this cleanly needs a separate proxy-vs-admin-CIDR contract because current `ARCLINK_BACKEND_ALLOWED_CIDRS` represents both direct allowed clients and trusted peers.
### Cross-piece edits made (if any) + tests added
- Cross-piece edits: none.
- Tests added/adjusted in `tests/test_arclink_hosted_api.py`, `tests/test_arclink_api_auth.py`, and `tests/test_arclink_http.py`.
<<<CODEX-FIX-END CANON-02>>>
