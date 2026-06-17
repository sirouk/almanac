<<<CODEX-FIX-START CANON-07>>>
## CANON-07 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: python/arclink_adapters.py, python/arclink_control.py, python/arclink_entitlements.py, python/arclink_hosted_api.py, tests/test_arclink_e2e_fake.py, tests/test_arclink_entitlements.py, tests/test_arclink_hosted_api.py, tests/test_arclink_onboarding.py
TESTS: 6 files run, all pass; py_compile pass

### Fixed (severity — what — path:line)
- HIGH — durable `received` webhook rows now reprocess instead of returning replayed 200/no-op. `python/arclink_entitlements.py:617`
- MEDIUM — checkout/refuel payment verification now requires `payment_status=paid`; refuel also requires positive retail cents and sufficient Stripe amount. `python/arclink_entitlements.py:416`, `python/arclink_entitlements.py:647`, `python/arclink_entitlements.py:746`
- MEDIUM — subscription mirror no longer crashes on `status='none'`; unknown statuses map to valid non-active `incomplete`. `python/arclink_entitlements.py:52`
- MEDIUM — multi-`v1` Stripe signature rotation now accepts any matching `v1`, not only the last one. `python/arclink_adapters.py:156`
- MEDIUM — refuel credit grants now guard duplicate `(user, deployment, source_kind, source_id)` inserts. `python/arclink_control.py:4435`
- MEDIUM — entitlement webhook now rejects locally conflicting Stripe customer/subscription ownership and mismatched client references. `python/arclink_entitlements.py:433`, `python/arclink_entitlements.py:794`
- LOW — reconciliation drift now counts only live/provisioning deployment statuses. `python/arclink_entitlements.py:76`, `python/arclink_entitlements.py:95`, `python/arclink_entitlements.py:118`
- LOW — successful retry of a failed paid webhook now queues the paid ping; `refuel_paid` is no longer treated as non-current billing. `python/arclink_hosted_api.py:965`

### Skipped (risk-accepted / standing / out-of-scope — why)
- HIGH atomicity premature commit: no new edit; current tree already has `expire_stale_arclink_onboarding_sessions(..., commit=not conn.in_transaction)` and non-throwing entitlement sync handling. Verified at `python/arclink_onboarding.py:356`, `python/arclink_onboarding.py:844`.
- Raw-body Stripe seam and unset-secret 503 were confirmed already correct; no code change.
- KeyError→404 vs 400 is an error-surface citation correction, not a 2xx fail-open; no code change.

### NEEDS-DECISION (ambiguous; left for human)
- Full forged-metadata policy when neither Stripe customer nor subscription is locally bound. This patch blocks known local ownership conflicts without changing the wider first-binding contract for signed Stripe checkout/subscription events.

### Cross-piece edits made (if any) + tests added
- Cross-piece code edits: `python/arclink_control.py` for refuel source idempotency; `python/arclink_hosted_api.py` for retry ping/refuel synthetic-state handling.
- Tests added/updated in `tests/test_arclink_entitlements.py`, `tests/test_arclink_hosted_api.py`, `tests/test_arclink_onboarding.py`, and `tests/test_arclink_e2e_fake.py`.
- Ran: `python3 tests/test_arclink_entitlements.py`; `python3 tests/test_arclink_control_db.py`; `python3 tests/test_arclink_onboarding.py`; `python3 tests/test_arclink_chutes_and_adapters.py`; `python3 tests/test_arclink_e2e_fake.py`; `python3 tests/test_arclink_hosted_api.py`; `python3 -m py_compile ...`.
<<<CODEX-FIX-END CANON-07>>>
