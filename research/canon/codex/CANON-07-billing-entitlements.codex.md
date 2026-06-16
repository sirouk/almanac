<<<CODEX-VERDICT-START CANON-07>>>
## CANON-07 — Codex (GPT-5.5 xhigh) ratification
SIGN-OFF: OBJECT(4)
ONE-LINE VERDICT: HMAC/replay basics are real, but the verifier is right: checkout-onboarding breaks atomicity, and I found four additional code-path refinements.

### Adjudication (each: CONFIRM/REFUTE/REFINE + path:line)
- CONFIRM — raw-body Stripe seam: `/webhooks/stripe` routes to `stripe_webhook`, is absent from `_JSON_OBJECT_ROUTES`, and passes raw `body` into `process_stripe_webhook`; HMAC signs/verifies `f"{t}.{payload}"`. `python/arclink_hosted_api.py:3760,3875-3914,4009,4022-4023`; `python/arclink_adapters.py:149-176`.
- CONFIRM — unset webhook secret fails closed with 503 before processing. `python/arclink_hosted_api.py:892-907`.
- CONFIRM — §A5 atomicity refutation: webhook opens `BEGIN`, writes entitlement/gates, then `sync_arclink_onboarding_after_entitlement(commit=False)` calls `_active_session_or_error`, which calls `expire_stale_arclink_onboarding_sessions()` with default `commit=True`; that commits mid-webhook. `python/arclink_entitlements.py:526,724-744`; `python/arclink_onboarding.py:271,324-337,807`.
- CONFIRM — not all webhook errors are 400: `KeyError` is caught as 404; `ArcLinkOnboardingError` is 400. `python/arclink_hosted_api.py:4230-4245`; missing onboarding row raises `KeyError`. `python/arclink_onboarding.py:329-332`.
- CONFIRM — CANON-04 sync seam is unsafe: terminal sessions raise after the commit-capable stale-expiry call, and a `False` return is ignored by CANON-07. `python/arclink_onboarding.py:336-340,807-811`; `python/arclink_entitlements.py:742-750`.
- CONFIRM — refuel grant has no `(source_kind,source_id)` idempotency guard or UNIQUE constraint; current refuel branch still keeps grant/apply/processed mark in one transaction, so ordinary replay does not double-grant unless that boundary is broken later. `python/arclink_control.py:1020-1032,4436-4456`; `python/arclink_entitlements.py:598-642`.
- REFINE — forged metadata risk is broader than “writes entitlement”: with email present, metadata `arclink_user_id` becomes `candidate_user_id`, and the merge can repoint deployments/subscriptions/refuels/sessions from that candidate to the email winner. `python/arclink_entitlements.py:654-688,724-740`; `python/arclink_control.py:3722-3739,3770-3787`.
- CONFIRM — multi-`v1` Stripe signatures are not rotation-safe: parser stores signature parts in a dict, so duplicate `v1=` values overwrite and only the last is compared. `python/arclink_adapters.py:159-163,170-171`.
- CONFIRM — subscription mirror `status='none'` crash: unrecognized subscription status falls through to entitlement `"none"`, then mirror validation rejects it. `python/arclink_entitlements.py:52-62,399-413,707-723`; `python/arclink_control.py:3195-3206,3251-3255,4710`.
- CONFIRM — `refuel_paid` is synthetic result state, not a stored entitlement state. `python/arclink_entitlements.py:643-649`; `python/arclink_control.py:3171`.
- REFINE — `received` replay is not only hypothetical: the premature onboarding commit can persist the webhook row as `received`; redelivery then returns `replayed=True` and CANON-02 returns 200. `python/arclink_entitlements.py:527-545`; `python/arclink_onboarding.py:324-337`; `python/arclink_hosted_api.py:932-937`.

### New findings both Claude passes missed (severity + path:line)
- HIGH — crash/kill window after the premature onboarding commit can strand a durable `arclink_webhook_events.status='received'`; later Stripe delivery is acknowledged as replay and never reprocesses. `python/arclink_entitlements.py:527-545`; `python/arclink_onboarding.py:324-337`; `python/arclink_hosted_api.py:932-937`.
- MEDIUM — any signed `checkout.session.completed` maps to `paid` without checking `payment_status`, `amount_total`, or object `status`; the refuel branch similarly grants from metadata credit fields without checking payment/amount fields. `python/arclink_entitlements.py:399-403,572-616`.
- LOW — successful retry of a prior `failed` webhook returns `replayed=True`, so hosted API suppresses first-success paid/noncurrent pings. `python/arclink_entitlements.py:446-461,791-798`; `python/arclink_hosted_api.py:916-921`.
- LOW — reconciliation detector treats `torn_down`, `teardown_requested`, `teardown_running`, `teardown_failed`, `provisioning_failed`, and `reserved` as live because it excludes only three statuses; this creates false drift results. `python/arclink_entitlements.py:73-78,90-97,113-117`; contrast fuller exclusion in `python/arclink_control.py:4286-4293`.

### Claude citations re-confirmed or corrected
- Re-confirmed core CANON-07 files and seams: `StripeWebhookResult`, mutating event set, replay ledger, refuel path, entitlement path, reconciliation output, and adapter HMAC all match the cited code. `python/arclink_entitlements.py:142-162,416-505,508-809`; `python/arclink_adapters.py:139-176`.
- Corrected schema citation: `arclink_subscriptions` DDL is at `python/arclink_control.py:1008-1018`, not the mirror UPSERT region near `:4714`.
- Corrected transaction claim: control helpers mostly honor `commit=False`, but onboarding’s `_active_session_or_error` does not pass it through. `python/arclink_control.py:3765,3829,3866,3983-3985`; `python/arclink_onboarding.py:336-337`.

### Residual disagreement with the Claude half (for final reconciliation)
- No disagreement with the verifier’s HIGH/MEDIUM conclusions. I would upgrade the old “received replay” LOW from hypothetical to a real crash-window consequence of S1, and add the checkout-completed payment-field blind spot to CANON-07’s medium-risk set.
<<<CODEX-VERDICT-END CANON-07>>>
