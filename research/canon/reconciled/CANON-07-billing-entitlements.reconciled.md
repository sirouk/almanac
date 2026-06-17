# CANON-07 — Billing & Entitlements — FEDERATION RECONCILIATION

Final adjudicator: Claude Opus 4.8 (1M) — re-opened every disputed citation in
`python/arclink_entitlements.py`, `python/arclink_onboarding.py`,
`python/arclink_control.py`, `python/arclink_hosted_api.py`. Code wins over any
prior claim.

## SIGN-OFF HEADER
- **Codex (GPT-5.5 xhigh) sign-off:** OBJECT(4) — HMAC/replay basics real; verifier
  correct that checkout+onboarding breaks atomicity; +4 code-path refinements/findings.
- **Federation sign-off (this file):** **BOTH-MODEL-AGREED.** Every material point
  reconciled to one code-grounded truth. No standing disagreements — Codex states
  "no disagreement with the verifier's HIGH/MEDIUM conclusions," and my independent
  re-open of the code confirms each. Residual items are severity *upgrades* both
  models accept, not contested points.

## RESOLUTION TABLE (disputed / refined / new points)

| Point | Winner | Deciding cite |
|---|---|---|
| "all inside ONE transaction" atomicity claim | **claude-verifier + codex** (record REFUTED) | `arclink_entitlements.py:526,744`; `arclink_onboarding.py:807,337,271,324-325` — `expire_stale...` default `commit=True` fires `conn.commit()` mid-webhook |
| Record self-check #5 "no premature commit" generalization | **claude-verifier** (false) | Verified only `merge_arclink_user_identity_by_email` honors commit=False (`arclink_control.py:3765`); onboarding path commits (`arclink_onboarding.py:325`) |
| Entitlement write survives a failed/looping webhook | **claude-verifier + codex** | Premature commit `arclink_onboarding.py:325` precedes terminal raise `:339-340` and missing-row `KeyError` `:331-332`; entitlement durable from `entitlements.py:724-740` |
| "errors surface as 400" (trace step 18) | **claude-verifier + codex** (record REFUTED, minor) | `KeyError`→404 `arclink_hosted_api.py:4243-4245`; `ArcLinkOnboardingError`→400 `:4230-4242`; generic→400 `:4246-4253`. KeyError reachable: `arclink_onboarding.py:331-332`, `arclink_control.py:4421` |
| `mirror_status="none"` crashes mirror write (NEW MEDIUM) | **claude-verifier + codex** | `_entitlement_for_stripe_event` default `"none"` `entitlements.py:413`; fallback `entitlements.py:62`; not in `ARCLINK_SUBSCRIPTION_STATUSES` `control.py:3195-3206`; CHECK `control.py:1013`; raise `control.py:3253-3254` via `:4710` |
| Forged-metadata risk scope (REFINE) | **codex + claude-verifier** | Email-present → candidate metadata user_id becomes merge candidate `entitlements.py:673-688`; email-chosen winner repoints loser rows `control.py:3728-3739,3752-3753,3771-3787` |
| `received`-replay: hypothetical vs real crash-window (REFINE→upgrade) | **codex** | Premature commit persists row at `status='received'` (`entitlements.py:527` insert, processed-mark only at `:789`); redelivery short-circuits `:544-552` → 200 `hosted_api.py:932-937` |
| Refuel grant lacks `(source_kind,source_id)` idempotency guard (RISK-1) | **both** (CONFIRM) | `grant_arclink_refuel_credit` unconditional INSERT `control.py:4436-4456`, PK `credit_id` only `control.py:1020-1032`; contrast allowance guard `control.py:4317-4331` |
| RISK-1 single-txn "non-doubling" still holds for refuel branch | **both** (CONFIRM) | Refuel branch does NOT call onboarding sync; grant+apply+mark in one txn `entitlements.py:598,616,641,642` |
| Multi-`v1` rotation not handled (MEDIUM) | **both** (CONFIRM) | dict keyed by `v1`, last wins `adapters.py:159-163,171` |
| Entitlement branch no ownership assertion (MEDIUM) | **both** (CONFIRM) | `entitlements.py:724-740` no `_assert_*`, only HMAC gate |
| `refuel_paid` synthetic state | **both** (CONFIRM) | `entitlements.py:647` not in `ARCLINK_ENTITLEMENT_STATES` `control.py:3171` |
| raw-body invariant (CANON-02) | **both** (CONFIRM) | absent from `_JSON_OBJECT_ROUTES` `hosted_api.py:3875-3899`; raw `body` passed `:4023,906-908`; HMAC over `f"{t}.{payload}"` `adapters.py:151` |
| unset-secret 503 fail-closed | **both** (CONFIRM) | `hosted_api.py:892-904` |
| schema-cite drift `arclink_subscriptions` "~4714" | **claude-verifier + codex** | DDL actually `control.py:1008-1018`; `:4714` is the INSERT inside the mirror UPSERT |

## CODEX NEW FINDINGS — CONFIRMED vs REJECTED

### CONFIRMED (net-new federation risks)
1. **HIGH — durable `received` strand (crash window).** A crash/kill between the
   premature onboarding commit (`arclink_onboarding.py:325`) and the final
   `_mark_webhook_processed`+commit (`entitlements.py:789-790`) leaves the webhook
   row durably at `status='received'`. Redelivery hits the `received` short-circuit
   (`entitlements.py:544-552`) → `replayed=True` → HTTP 200 (`hosted_api.py:932-937`)
   → Stripe stops retrying → the event is NEVER reprocessed (allowance, processed
   mark, paid ping all skipped). This FALSIFIES the record's mitigation that "on
   crash the BEGIN was uncommitted so no `received` row persists" — the premature
   commit makes it persist. Net-new HIGH.
2. **MEDIUM — no payment verification on checkout/refuel.** `grep` over
   `arclink_entitlements.py` finds ZERO reads of `payment_status`, `amount_total`,
   or `amount_paid`. `checkout.session.completed` maps unconditionally to `"paid"`
   (`entitlements.py:401-402`); the refuel branch grants from metadata `credit_cents`
   checking only `>0` and a present `deployment_id` (`entitlements.py:575-580,598-616`).
   A legitimately-signed `checkout.session.completed` with `payment_status` in
   `{unpaid, no_payment_required}` (async payment methods) grants entitlement/credit
   before settlement. Real correctness gap, HMAC-gated, MEDIUM.
3. **LOW — failed-retry suppresses first-success pings.** A successful retry of a
   prior `failed` event returns `replayed = not inserted = True`
   (`entitlements.py:446-461,796`); `_handle_stripe_webhook` gates pings on
   `not result.replayed` (`hosted_api.py:916,921`), so the first successful paid/
   non-current ping is suppressed. CONFIRMED LOW.
4. **LOW — reconciliation detector over-counts "live" deployments.** Drift detector
   excludes only 3 statuses (`entitlement_required`, `teardown_complete`,
   `cancelled`; `entitlements.py:77,92,116`) while `ARCLINK_DEPLOYMENT_STATUSES`
   (`control.py:3181-3194`) includes `reserved`, `provisioning_failed`,
   `teardown_requested`, `teardown_running`, `teardown_failed`, `torn_down`. The
   allowance path uses a fuller 7-status exclusion (`control.py:4286-4293`). The
   detector therefore treats torn-down/failed/reserved deployments as live → false
   `deployment_without_subscription` / owed-service drift. CONFIRMED LOW.

### REJECTED
- None. All four Codex new findings re-verified true in code.

## SEVERITY CHANGES (code-supported only)

| Risk | From | To | Cite |
|---|---|---|---|
| Atomicity break on checkout+onboarding (was implicit "atomic" strength) | (record: STRENGTH) | **HIGH** | `arclink_onboarding.py:324-325,337,807`; `entitlements.py:526,744,789-790` |
| `received` replay silent-drop | LOW (record) | **HIGH** (durable crash-window via premature commit) | `arclink_onboarding.py:325`; `entitlements.py:527,544-552,789` |
| `mirror_status="none"` crash | (unnamed in record) | **MEDIUM** (new) | `entitlements.py:62,413`; `control.py:3253-3254,4710` |
| No payment-field verification | (unnamed in record) | **MEDIUM** (new) | `entitlements.py:399-403,575-616` (no `payment_status`/`amount_total` read) |
| Reconciliation over-broad "live" | (unnamed in record) | **LOW** (new) | `entitlements.py:77,92,116` vs `control.py:4286-4293` |
| Refuel grant idempotency guard (RISK-1) | MEDIUM | **MEDIUM** (unchanged — single-txn holds for refuel branch only) | `entitlements.py:598-642`; `control.py:4436-4456` |
| Forged-metadata entitlement write | MEDIUM | **MEDIUM** (unchanged; scope REFINED to include merge-repoint) | `entitlements.py:724-740`; `control.py:3752-3787` |
| Multi-`v1` rotation | MEDIUM | **MEDIUM** (unchanged) | `adapters.py:159-163,171` |

## STANDING DISAGREEMENTS
None. Both models agree on every material point after code re-open. The federation
sign-off is BOTH-MODEL-AGREED.

## FINAL BOTH-MODEL VERDICT
CANON-07's cryptographic and replay-ledger core is real and correct: HMAC over the
exact raw body, `(provider,event_id)` idempotency ledger, constrained entitlement
vocabulary, fail-closed 503 on unset secret. **But the record's central
"all-inside-ONE-transaction / atomic fail-closed" claim is FALSE on the highest-volume
real path** (web `checkout.session.completed` carrying an onboarding session): an
un-overridden `commit=True` default deep in the CANON-04 onboarding seam
(`arclink_onboarding.py:271,324-325` reached via `_active_session_or_error:337`)
fires `conn.commit()` mid-webhook, splitting the txn in two. This (a) makes the
entitlement write durable before the webhook is marked processed, so a later failure
loops while the user is already `paid`; (b) creates a HIGH durable-`received`
crash-window that silently drops redeliveries; and (c) maps cleanly onto a non-uniform
error surface (KeyError→404, not the record's "all 400"). Net new federation risks:
HIGH atomicity break, HIGH durable-`received` strand, MEDIUM `mirror_status="none"`
crash, MEDIUM no-payment-verification, LOW ping-suppression, LOW reconciliation
over-count. Six of the record's originally-named risks re-verified TRUE. The
subsystem is source-complete and its crypto core is proven; the atomicity and
payment-verification gaps are genuine, fixable code defects — the single highest-value
fix is to thread `commit=False` through `_active_session_or_error` →
`expire_stale_arclink_onboarding_sessions` so the webhook txn stays atomic.

---

<!-- CANON-REPAIR-STATUS:START -->
## Repair status

> Refreshed from [`research/canon/fixes/CANON-07-billing-entitlements.fix.md`](../fixes/CANON-07-billing-entitlements.fix.md) (tracked). The audit findings above remain the adjudicated spec; this block records the repair campaign state for this piece.

- Status: `c5cec97` committed.
- Summary: 8 fixed / 3 skipped / 1 needs-decision.
- Tests: 6 files run, all pass; py_compile pass
- Representative fixes:
  - HIGH — durable `received` webhook rows now reprocess instead of returning replayed 200/no-op. `python/arclink_entitlements.py:617`
  - MEDIUM — checkout/refuel payment verification now requires `payment_status=paid`; refuel also requires positive retail cents and sufficient Stripe amount. `python/arclink_entitlements.py:416`, `python/arclink_entitlements.py:647`, `python/arclink_entitlements.py:746`
  - MEDIUM — subscription mirror no longer crashes on `status='none'`; unknown statuses map to valid non-active `incomplete`. `python/arclink_entitlements.py:52`
- Needs decision:
  - Full forged-metadata policy when neither Stripe customer nor subscription is locally bound. This patch blocks known local ownership conflicts without changing the wider first-binding contract for signed Stripe checkout/subscription events.
<!-- CANON-REPAIR-STATUS:END -->
