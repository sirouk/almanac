<<<CODEX-FIX-START CANON-11>>>
## CANON-11 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: python/arclink_executor.py, tests/test_arclink_executor.py
TESTS: 1 test file run, all pass (60/60); py_compile pass; git diff --check pass

### Fixed (severity — what — path:line)
- HIGH — wired production factory to inject `operation_conn` from `ARCLINK_DB_PATH`, with schema ensured. `python/arclink_executor.py:80`, `python/arclink_executor.py:158`
- HIGH — live Chutes/Stripe provider actions now fail closed if an injected client lacks durable operation idempotency DB. `python/arclink_executor.py:1217`, `python/arclink_executor.py:1342`
- MEDIUM — Cloudflare DNS upsert now serializes per zone/type/hostname with an advisory file lock around find-then-create/update. `python/arclink_executor.py:2563`, `python/arclink_executor.py:2603`
- MEDIUM — SSH `read_text_file`/`write_text_file` now require `allowed_root` and fail before SSH when omitted. `python/arclink_executor.py:684`, `python/arclink_executor.py:723`
- MEDIUM — local/broker compose apply now materializes only deployment-contained volume roots, not arbitrary absolute bind sources. `python/arclink_executor.py:2187`
- MEDIUM — live Cloudflare Access and rollback no longer report fake success; non-fake paths fail closed as unimplemented. `python/arclink_executor.py:1202`, `python/arclink_executor.py:1443`
- LOW — rendered `arclink.env`, `compose.yaml`, and `remote-prepare.json` now use atomic locked private writes. `python/arclink_executor.py:2003`, `python/arclink_executor.py:2020`, `python/arclink_executor.py:2028`
- LOW — duplicate compose secret targets are rejected before resolver materialization can alias/overwrite. `python/arclink_executor.py:1760`
- LOW — symlinked secret-root cleanup unlinks the symlink itself instead of walking the target. `python/arclink_executor.py:2143`

### Skipped (risk-accepted / standing / out-of-scope — why)
- GAP-019 trusted-host/root-equivalent Docker and remote bind-prepare residuals left unchanged; this is the risk-accepted trusted worker boundary.
- Lifecycle project override left unchanged; it is an explicit operator-gated config flag and paths remain deployment-contained.
- Broker `remove_volumes`/`include_all` harmless extra-key asymmetry left unchanged to avoid unnecessary CANON-12 wire-contract churn.

### NEEDS-DECISION (ambiguous; left for human)
- Live Chutes/Stripe admin clients are still not production-implemented/wired. Executor now requires durable DB before any injected client can run, but real Chutes key management and Stripe refund/cancel semantics need provider/product decisions.
- Generic ArcLink replay ledger for compose/lifecycle/DNS beyond the DNS lock needs a contract decision; current compose apply keys can be reused across legitimate deployment updates, so naive replay would break re-apply flows.
- SSH TOFU default (`StrictHostKeyChecking=accept-new`) left unchanged; tightening it would affect first-contact fleet bootstrap policy.

### Cross-piece edits made (if any) + tests added
- Cross-piece edits: none.
- Tests added/expanded in `tests/test_arclink_executor.py`; main now runs all 60 executor tests, including previously uncalled SSH helper coverage.
<<<CODEX-FIX-END CANON-11>>>
