<<<CODEX-PHASE1-START W3FIX>>>
## W3FIX (CANON-07 D1 review hardening) — Codex test report
### Tests changed (and why each used the shortcut)
- Updated `test_stripe_webhook_merges_users_when_email_matches_existing_account`: it was seeding `arcusr_fresh_web` and its deployment directly, then depending on `metadata.arclink_user_id` / `client_reference_id` to originate checkout ownership. The test now creates the fresh web user through `create_or_resume_arclink_onboarding_session` and `open_arclink_onboarding_checkout` with `FakeStripeClient`, sends `checkout.session.completed` with `obj.id == opened["checkout_session_id"]`, and leaves `metadata` empty so ownership resolves from local checkout state before the email merge.
- Verified `test_checkout_session_completed_rejects_unpaid_subscription_checkout` already exercises the reordered paid-check path and still passes without needing local owner resolution.
### New regression added + wired
- Added and wired `test_checkout_session_completed_rejects_existing_user_metadata_without_local_checkout`.
- It creates an existing local user, sends a paid `checkout.session.completed` with `metadata.arclink_user_id` naming that user but no local onboarding checkout/session, and asserts `ArcLinkEntitlementError`, `entitlement_state == "none"`, blank `stripe_customer_id`, no subscription mirror, and failed webhook status.
### Results
- `TERMINAL_DISABLE_TMUX=1 ARCLINK_FLEET_WORKER_CONFIG=/tmp/none python3 tests/test_arclink_entitlements.py` - PASS, all 40 entitlement tests.
- `TERMINAL_DISABLE_TMUX=1 ARCLINK_FLEET_WORKER_CONFIG=/tmp/none python3 tests/test_documentation_truths.py` - PASS, all documentation truth tests.
<<<CODEX-PHASE1-END W3FIX>>>
