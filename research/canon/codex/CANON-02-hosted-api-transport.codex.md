<<<CODEX-VERDICT-START CANON-02>>>
## CANON-02 — Codex (GPT-5.5 xhigh) ratification
SIGN-OFF: OBJECT(3)
ONE-LINE VERDICT: Core CANON-02 is ratified, but the consolidated record needs three refinements: importer-count wording, proxy/topology wording, and two WSGI malformed-body lows.

### Adjudication (each: CONFIRM/REFUTE/REFINE + path:line)
- REFINE §A2: OpenAPI parity is canonical JSON equality, not byte identity: test canonicalizes both specs before compare (`tests/test_arclink_hosted_api.py:5505-5507`); spec is generated from `_ROUTES` (`python/arclink_hosted_api.py:3689-3694`).
- REFINE §A2: route counts confirmed by execution: 71 `_ROUTES`, 69 suffixes, public=18, CIDR=18, broker=1, JSON=38; `session_revoke` is CIDR-protected but not an `admin_*` key (`python/arclink_hosted_api.py:3754-3826`, `:3829-3875`).
- REFINE §A2: `http_request` appears in 10 `python/*.py` files only because `python/arclink_http.py:66` defines it; actual `from arclink_http import http_request` consumers are 9, e.g. `python/arclink_rpc_client.py:8`.
- CONFIRM §A2: Stripe seam is fully both-ends-verifiable: hosted API passes raw body/signature/secret (`python/arclink_hosted_api.py:905-908`), entitlement consumer matches that signature and result dataclass (`python/arclink_entitlements.py:155-161`, `:508-515`).
- CONFIRM §B24: CIDR predicates fail closed on malformed IPs/ports and support IPv4/IPv6 through `ipaddress`; malformed IP/CIDR returns false/continues (`python/arclink_control.py:7604-7625`).
- REFINE §B24: no second in-repo route table found; WSGI passes `REMOTE_ADDR` into the sole dispatcher (`python/arclink_hosted_api.py:3921`, `:4321-4330`), but external process-manager/proxy behavior remains topology-unproven.
- CONFIRM MEDIUM: empty `REMOTE_ADDR` falls back to `x-real-ip` or `127.0.0.1`, affecting CIDR routes and generic `/auth/login` admin enablement (`python/arclink_hosted_api.py:635-648`, `:3979-3988`, `:4031-4038`).
- REFINE MEDIUM: dev pepper fallback is real in code (`python/arclink_api_auth.py:271-283`), but canonical Docker/deploy lanes set/generate pepper and require it (`compose.yaml:77-78`, `bin/deploy.sh:8467-8468`, `bin/docker-entrypoint.sh:666-670`).
- CONFIRM MEDIUM: broker proof tokens accept legacy plain SHA-256 and do not self-heal; token-only broker auth checks that hash (`python/arclink_api_auth.py:248-257`, `:2438-2444`, `:2477`; route header at `python/arclink_hosted_api.py:1739-1742`).
- CONFIRM: no CANON-02 HIGH risk is present in the consolidated register.

### New findings both Claude passes missed (severity + path:line)
- LOW: negative `CONTENT_LENGTH` bypasses the WSGI pre-read cap because only `length > body_limit` rejects; `read(-1)` can consume the whole body before later routing rejects it (`python/arclink_hosted_api.py:4289-4308`).
- LOW: non-UTF-8 WSGI bodies raise `UnicodeDecodeError` outside hosted API error mapping, producing an unstructured 500 path instead of JSON 400 (`python/arclink_hosted_api.py:4308`, error handling starts only after dispatch at `:4173`).
- INFO: URL redaction is transport-error-only; MCP clients pass raw URLs into parse/status errors (`python/arclink_http.py:140`, `python/arclink_rpc_client.py:29-35`, `python/arclink_mcp_server.py:693-700`).

### Claude citations re-confirmed or corrected
- Reconfirmed dispatch order, per-route CIDR/rate-limit/JSON handling, and single handler chain (`python/arclink_hosted_api.py:3944-4011`, `:4012-4163`).
- Reconfirmed cookie/CSRF contract: server emits non-HttpOnly CSRF cookie and web echoes `X-ArcLink-CSRF-Token` with credentials included (`python/arclink_hosted_api.py:463-469`; `web/src/lib/api.ts:29-38`).
- Reconfirmed Stripe/Telegram/Discord fail-closed or acknowledged webhook behavior (`python/arclink_hosted_api.py:892-908`, `:2889-2901`, `:3027-3050`).
- Reconfirmed MCP client/server shape: `mcp-session-id`, `structuredContent`, and text content agree (`python/arclink_rpc_client.py:21-36`, `:69-87`; `python/arclink_mcp_server.py:1673-1680`, `:1835-1839`).
- Reconfirmed verifier lows: scheme-blind `enforce_secure_transport` (`python/arclink_http.py:56-63`), rate-limit TOCTOU (`python/arclink_api_auth.py:408-428`, `:481-501`), and Stripe last-`v1` signature overwrite (`python/arclink_adapters.py:159-172`).

### Residual disagreement with the Claude half (for final reconciliation)
- Keep the verifier’s byte-identity refutation and change “10 importers” to “10 files mention, 9 importers.”
- Add the two WSGI malformed-body lows to CANON-02.
- Treat `REMOTE_ADDR` risk as broader than “empty only”: trusted-proxy-without-XFF also collapses the gate to proxy IP (`python/arclink_hosted_api.py:635-641`; Next rewrite has no code-level XFF assertion at `web/next.config.ts:7-12`).
<<<CODEX-VERDICT-END CANON-02>>>
