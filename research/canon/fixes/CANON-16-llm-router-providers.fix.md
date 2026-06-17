<<<CODEX-FIX-START CANON-16>>>
## CANON-16 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: python/arclink_llm_router.py, python/arclink_chutes.py, python/arclink_chutes_oauth.py, tests/test_arclink_llm_router.py, tests/test_arclink_chutes_and_adapters.py, tests/test_arclink_chutes_oauth.py
TESTS: 5 files run, all pass; py_compile pass; git diff --check pass
### Fixed (severity — what — path:line)
- MEDIUM — key-specific/global default-model allowlist bypass and routed-model/fallback egress allowlist escape closed — python/arclink_llm_router.py:648, python/arclink_llm_router.py:1122
- LOW/MEDIUM — chunked/no-Content-Length body buffering now rejects before buffering past cap — python/arclink_llm_router.py:488
- MEDIUM/LOW — reservation/concurrency and rate-limit TOCTOU narrowed with one BEGIN IMMEDIATE covering checks, rate inserts, and reservation insert — python/arclink_llm_router.py:854, python/arclink_llm_router.py:1146
- MEDIUM — settlement exceptions no longer leak permanent reserved rows; Chutes settlement is savepoint-isolated and reservation release still runs — python/arclink_llm_router.py:1472
- LOW — external Chutes usage idempotency race now catches duplicate event IntegrityError and returns idempotent recorded=False without double-counting — python/arclink_chutes.py:916
- INFO — `limit_enforced` now reports false for unlimited budget lane — python/arclink_chutes.py:108
- INFO — OAuth callback consumes state on CSRF mismatch — python/arclink_chutes_oauth.py:324
### Skipped (risk-accepted / standing / out-of-scope — why)
- GAP-031 no live Chutes relay proof — canon labels this as open live-proof coverage, not a local code defect to settle here.
### NEEDS-DECISION (ambiguous; left for human)
- Budget fail-open provenance for `observe_only_unlimited` — lane is deliberate for the Operator Pod; changing router acceptance requires a product/provenance rule for configurable operator identities.
- Mid-stream error SSE after valid chunks — changing partial-stream wire shape could break clients; needs an explicit contract decision.
### Cross-piece edits made (if any) + tests added
- Cross-piece edits made: none.
- Tests added/adjusted in CANON-16 suites for chunk body cap, allowlist egress/default bypasses, settlement cleanup, Chutes idempotency race, unlimited public budget posture, and OAuth CSRF state consumption.
<<<CODEX-FIX-END CANON-16>>>
