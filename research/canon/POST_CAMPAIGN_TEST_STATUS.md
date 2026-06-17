# Post-campaign full-suite test status (honest)

After all 32 pieces were repaired and committed, a **full 128-file suite scan**
(`for f in tests/test_*.py; do python3 $f; done`, `TERMINAL_DISABLE_TMUX=1`,
`ARCLINK_FLEET_WORKER_CONFIG=/tmp/none`) was run as the final CI-style gate.

The first post-campaign sweep was **121 / 128 green. 7 reds**. A Phase 0
follow-up then fixed the 4 real cumulative cross-piece reds and re-ran the same
128-file sweep:

Phase 0 fixed the 4 cross-piece reds (→ 125/128); a Phase 0 follow-up then cleared
the 2 test-only residuals that were in scope (→ **127/128**):

**127 / 128 green. 1 red remains** — the single genuinely pre-existing failure that
predates this branch. The 4 integration regressions that blocked the repair campaign,
plus both in-scope test-residuals, are now green.

## Pre-existing (NOT introduced by this campaign) — still red, out of scope
- **`test_deploy_regressions.py`** — fails at the pre-campaign baseline `63a42c8`
  (Discord `interaction.response.send_message` ephemeral assertion). Predates the
  branch entirely; not a CANON finding or a campaign regression. Left for a separate
  pre-existing-bug task.

## Resolved in the Phase 0 follow-up
- **`test_arclink_user_agent_refresh.py`** — was a CAMPAIGN-introduced harness break:
  CANON-01's refactor added `from arclink_boundary import …` to `arclink_control.py`,
  but the test's temp-repo copy list never got `arclink_boundary.py` (or its
  `arclink_secrets_regex` dep). FIXED: copy list updated (all 3 fixture blocks).
- **`test_hermes_runtime_pin_regressions.py`** — stale since pre-campaign `7ac94d3`
  bumped the hermes-agent pin `3c231eb…`→`042c1d6…` without updating the test's
  hardcoded `PINNED_REF`. FIXED: `PINNED_REF` updated to the committed pin.

## Cumulative cross-piece regressions — RESOLVED in Phase 0
These were correctness/security regressions from cumulative fixes; each was green at
its own piece's batch commit but broke at integration. They now pass:
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
by CANON-01 and CANON-23) were not caught until the full-suite scan. Phase 0 fixed
the shared roots: webhook transaction leakage from onboarding expiry cleanup,
onboarding modern secret/step validation, provisioning job-level secret failure
handling, and hosted public-bot checkout replay idempotence. The full sweep now
has only the 3 residual non-Phase0 reds listed above.
