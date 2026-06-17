# Post-campaign full-suite test status (honest)

After all 32 pieces were repaired and committed, a **full 128-file suite scan**
(`for f in tests/test_*.py; do python3 $f; done`, `TERMINAL_DISABLE_TMUX=1`,
`ARCLINK_FLEET_WORKER_CONFIG=/tmp/none`) was run as the final CI-style gate.

**121 / 128 green. 7 reds**, categorized below. These slipped the *per-batch* broad
gates because those gates ran a curated subset, not the whole suite — so
**cumulative, cross-piece** interactions (250+ fixes applied across 32 pieces) only
surface at full-integration level. They are documented here for merge review and a
focused follow-up; none invalidate the per-piece repairs, but the branch is **not
fully green** and should not be merged until these are resolved or accepted.

## Pre-existing (NOT introduced by this campaign)
- **`test_deploy_regressions.py`** — fails at the pre-campaign baseline `63a42c8`
  (Discord `interaction.response.send_message` ephemeral assertion). Predates the
  branch entirely.

## Likely pre-existing / environment (needs confirmation)
- **`test_hermes_runtime_pin_regressions.py`** — "unexpected hermes-agent pin:
  042c1d6bb054…". `config/pins.json` matches the committed pin (bumped in the
  pre-campaign commit `7ac94d3`); the test appears to hardcode a stale expected pin.
- **`test_arclink_user_agent_refresh.py`** — shell `bin/user-agent-refresh.sh`
  exits rc=1; likely host/env-dependent (not reproduced as a code defect yet).

## Cumulative cross-piece regressions — REAL, need a follow-up fix pass
These are correctness/security regressions from cumulative fixes; each was green at
its own piece's batch commit but broke at integration:
1. **`test_arclink_entitlements.py::test_checkout_onboarding_sync_does_not_commit_before_webhook_processed`**
   — the CANON-07 webhook atomicity is violated at integration: a forced webhook
   failure leaves `entitlement_state='paid'` (committed) instead of rolling back.
   Suspect: a mid-webhook `conn.commit()` reintroduced by a later batch's shared
   control.py / notification path.
2. **`test_arclink_onboarding.py::test_public_onboarding_rejects_modern_provider_keys_and_unbounded_steps`**
   — `display_name_hint="sk-ant-api…"` is NOT rejected (CANON-04 hint secret-scan not
   firing at integration).
3. **`test_arclink_provisioning.py::test_secret_validator_fails_job_and_same_idempotency_key_can_resume_after_fix`**
   — a plaintext secret in `metadata.llm_router_api_key_ref` raises an UNCAUGHT
   `ValueError` instead of being caught and failing the job gracefully.
4. **`test_arclink_hosted_api.py::test_public_bot_checkout_button_redirects_to_stripe`**
   — replay redirect returns 403 `invalid_proof` instead of the expected redirect.

## Root-cause note
The per-batch gates were intentionally narrow (curated affected tests) to keep the
campaign moving; the trade-off is that integration-level regressions from interacting
fixes (esp. the shared `arclink_control.py` secret-rejection + commit helpers, touched
by CANON-01 and CANON-23) were not caught until this full-suite scan. The correct
follow-up is a single integration pass that runs the full suite and resolves the 4
cross-piece reds at their shared root (control.py secret/commit helpers + the
api_auth/onboarding cancel refactor), then re-runs the whole suite to green.
