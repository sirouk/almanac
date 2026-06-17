<<<CODEX-FIX-START CANON-04>>>
## CANON-04 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: python/arclink_onboarding.py, python/arclink_entitlements.py, python/arclink_api_auth.py, tests/test_arclink_onboarding.py, tests/test_arclink_entitlements.py, tests/test_arclink_api_auth.py
TESTS: 9 test files run + py_compile, all pass

### Fixed (severity — what — path:line)
- HIGH — broadened public onboarding secret rejection for Anthropic/OpenAI/Chutes/AWS key shapes and centralized scan for mutable public text/metadata writes — `python/arclink_onboarding.py:120`, `python/arclink_onboarding.py:392`
- HIGH — removed entitlement-sync dependency on active-session lookup and stopped stale-expiry from committing inside caller-owned webhook transactions — `python/arclink_onboarding.py:355`, `python/arclink_onboarding.py:844`
- HIGH — kept onboarding entitlement sync atomic by making the deployment gate update part of the same final sync commit — `python/arclink_onboarding.py:851`
- MEDIUM — made ignored `sync_arclink_onboarding_after_entitlement(False)` observable via `stripe_onboarding_sync_skipped` event — `python/arclink_entitlements.py:744`
- MEDIUM — blocked late cancel from regressing paid/provisioning/first-contact sessions — `python/arclink_onboarding.py:65`, `python/arclink_onboarding.py:787`, `python/arclink_api_auth.py:5051`
- MEDIUM — added terminal guard before first-agent contact so expired/terminal sessions cannot resurrect to active — `python/arclink_onboarding.py:928`
- LOW — bounded and secret-scanned public `question_key` before storing/reflection as `current_step` — `python/arclink_onboarding.py:200`, `python/arclink_onboarding.py:563`

### Skipped (risk-accepted / standing / out-of-scope — why)
- OLD provider-auth live HTTP to OpenAI/Anthropic: intentional provider OAuth/device-auth behavior; abuse controls live in CANON-06, not a safe CANON-04-local removal.
- Chutes “OAuth” drift: code is correctly API-key per canon; this is brief/doc naming drift, not a code repair.
- Expire-on-read perf concern and IN-placeholder cosmetic issue: not correctness/security defects, and canon marks the placeholder order harmless.

### NEEDS-DECISION (ambiguous; left for human)
- NEW onboarding never transitions to `completed`: changing `first_contacted` to terminal `completed` is a public state-contract/index behavior change.
- OLD completion plaintext shared password in chat: current scrub-on-ack handoff is a deliberate UX/security tradeoff; replacing it needs product flow decision.
- `prepare_arclink_onboarding_deployment` committing deployment rows before Stripe checkout: safe fix requires checkout/reservation ordering redesign, not a surgical patch.

### Cross-piece edits made (if any) + tests added
- Cross-piece: `python/arclink_entitlements.py` now checks onboarding sync result and emits an observable event on skip.
- Cross-piece: `python/arclink_api_auth.py` now uses the onboarding immutable cancel-status set.
- Tests added: onboarding secret/current-step, expired paid checkout sync, terminal first-contact guard, webhook sync atomicity, sync-skip event, and paid-session cancel regression.
<<<CODEX-FIX-END CANON-04>>>
