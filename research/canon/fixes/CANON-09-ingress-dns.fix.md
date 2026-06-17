<<<CODEX-FIX-START CANON-09>>>
## CANON-09 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: python/arclink_ingress.py, python/arclink_action_worker.py, python/arclink_executor.py, tests/test_arclink_ingress.py, tests/test_arclink_action_worker.py, tests/test_arclink_executor.py
TESTS: 4 pass / 2 environment-blocked. Passed: `tests/test_arclink_ingress.py`, `tests/test_arclink_action_worker.py`, `tests/test_arclink_provisioning.py`, `tests/test_arclink_admin_actions.py`, plus `py_compile` and targeted executor teardown regression. Blocked: full `tests/test_arclink_executor.py` and `tests/test_arclink_sovereign_worker.py` hit pre-existing `/arcdata/...` permission errors after/before the touched paths.

### Fixed (severity — what — path:line)
- MEDIUM — `dns_repair` now persists validated DNS rows before Cloudflare apply, then marks provisioned rows and backfills provider IDs after success. `python/arclink_action_worker.py:236`, `python/arclink_action_worker.py:889`, `python/arclink_action_worker.py:911`; `python/arclink_ingress.py:191`
- MEDIUM — DNS teardown/provision status marking is now hostname-scoped, so partial teardown no longer bulk-clobbers every deployment DNS row. `python/arclink_ingress.py:153`, `python/arclink_ingress.py:219`
- LOW — live Cloudflare teardown now returns only actually deleted/found records, not every attempted hostname. `python/arclink_executor.py:1036`, `python/arclink_executor.py:2572`
- LOW — test-only DNS provisioning no longer retries deterministic/programming exceptions; retry is limited to transient I/O-style failures. `python/arclink_ingress.py:282`
- INFO — dead `teardown_arclink_dns` compatibility helper now targets only dashboard/hermes host roles, not files/code. `python/arclink_ingress.py:253`
- INFO — empty DNS persist is now a true no-op and does not commit an outer caller transaction. `python/arclink_ingress.py:63`
- MEDIUM doc-trust — dead compatibility DNS helper docstrings now explicitly point to the executor seam as the production path. `python/arclink_ingress.py:125`, `python/arclink_ingress.py:261`, `python/arclink_ingress.py:278`

### Skipped (risk-accepted / standing / out-of-scope — why)
- None as risk-accepted for CANON-09. The trusted-host/GAP-019 and compose-internal broker exceptions do not apply to this piece.

### NEEDS-DECISION (ambiguous; left for human)
- Torn-down-row/global DNS unique-index collision: left unchanged because the normal path is gated by CANON-08 prefix reservation, and changing the index/delete semantics is a schema/contract decision. `python/arclink_control.py:2077`
- Persisted `proxied` drift: left unchanged because fixing it needs a DB schema and live drift contract change, not a surgical CANON-09 patch. `python/arclink_ingress.py:74`
- Public unused `tailscale_dns_name` / `tailscale_host_strategy` args on `desired_arclink_ingress_records`: left unchanged because removing or repurposing them is a public signature decision. `python/arclink_ingress.py:46`
- Non-empty internal commits in DNS helpers remain; removing them would change caller transaction semantics outside the narrow empty-record no-op.

### Cross-piece edits made (if any) + tests added
- Cross-piece edit: `python/arclink_action_worker.py` for `dns_repair` DB tracking/backfill.
- Cross-piece edit: `python/arclink_executor.py` for honest live Cloudflare teardown result reporting.
- Tests added/adjusted in `tests/test_arclink_ingress.py`, `tests/test_arclink_action_worker.py`, and `tests/test_arclink_executor.py`.
<<<CODEX-FIX-END CANON-09>>>
