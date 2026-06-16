# CANON-07 — Billing & Entitlements — ADVERSARIAL VERIFICATION

Verifier: independent Opus 4.8 skeptic. Method: re-opened every load-bearing
citation in `python/arclink_entitlements.py`, `python/arclink_adapters.py`, plus
both ends of every cross-piece seam (`arclink_hosted_api.py`,
`arclink_control.py`, `arclink_api_auth.py`, `arclink_onboarding.py`).

## HEADLINE VERDICT

The record is **mostly accurate on the happy path and on its named risks, but its
central load-bearing claim is FALSE.** CANON-07 does NOT execute "all inside ONE
transaction" for the highest-volume real path (web `checkout.session.completed`
with an onboarding session). A premature `conn.commit()` fires mid-webhook via an
un-overridden default deep in the CANON-04 onboarding-sync seam — the exact seam
the record marked "PARTIAL (consumer body not opened here)". The record's
ADVERSARIAL SELF-CHECK #5 explicitly claimed "no premature commit" after checking
only the email-merge path; it never opened the onboarding path. This breaks the
atomicity invariant on which the VERDICT, RISK calibration, and replay-safety
argument all rest. **NEW HIGH-severity gap.**

## REFUTATIONS / CONFIRMATIONS (load-bearing claims)

### REFUTED — "all inside ONE transaction / single-transaction commit boundary"
Record repeats this at lines 26, 98, 219, 290-299, 367, 406-412 and leans the
entire VERDICT on it. It is FALSE for `checkout.session.completed` + onboarding.
- entitlements.py:744 calls `sync_arclink_onboarding_after_entitlement(conn, ...,
  commit=False)`.
- onboarding.py:807 `_active_session_or_error(conn, session_id)` is called with NO
  commit override.
- onboarding.py:337 `_active_session_or_error` calls
  `expire_stale_arclink_onboarding_sessions(conn)` with the DEFAULT `commit=True`
  (onboarding.py:271).
- onboarding.py:324-325 `if commit: conn.commit()` — fires UNCONDITIONALLY (not
  gated on rows expired).
Net: on every first delivery of a web checkout webhook that carries an
`arclink_onboarding_session_id` and reaches an active session, the in-flight
webhook `BEGIN` (entitlements.py:526) is COMMITTED at onboarding.py:325 — AFTER
the entitlement write (entitlements.py:724-740) and gate advance (:741) but BEFORE
the inference-allowance (:752), the `stripe_webhook_processed` event (:763), and
`_mark_webhook_processed` (:789). sqlite3 then auto-opens a fresh implicit txn for
:752-789, committed separately at :790. Two commits, not one.
Consequence: a failure anywhere in :752-789 triggers `except Exception` →
`conn.rollback()` (entitlements.py:800-801) which can only undo the SECOND txn. The
entitlement write from the FIRST txn is already durable, while the webhook row is
left at `received`, then UPSERTed to `failed` (entitlements.py:803). On Stripe
retry the `failed`→`received` reset reprocesses (entitlements.py:446-461),
re-running the entitlement write. No double-charge (gate advance + allowance are
idempotent), but the "atomic, fail-closed rollback-and-mark-failed" guarantee in
the VERDICT is not what the code does.

### REFUTED — record's ADVERSARIAL SELF-CHECK #5 "no premature commit"
Record line 328-333 claims it "verified `_arclink_commit(conn, commit=False)` is
honored ... no premature commit." That check covered ONLY
`merge_arclink_user_identity_by_email` (control.py:3765,3829 — genuinely honors
commit=False, confirmed). It did NOT cover the onboarding path, which DOES commit
prematurely (above). The generalization is false.

### NEW GAP (HIGH) — entitlement write survives a failed/looping webhook
Same mechanism. Because the premature commit persists the entitlement BEFORE the
webhook row is marked `processed`, a terminal-or-missing onboarding session leaves
a paying user `paid` with the webhook event stuck in a `failed`→retry loop:
- onboarding.py:340 raises `ArcLinkOnboardingError` if the session is terminal
  (statuses: payment_cancelled/payment_expired/payment_failed/completed/abandoned/
  expired, onboarding.py:34-43). Note onboarding.py:337 `expire_stale...` will
  TTL-terminalize a still-active session in the SAME call that then rejects it.
- onboarding.py:331-332 raises `KeyError` if the session row is absent.
The premature commit at onboarding.py:325 fires BEFORE either raise (line 337
precedes line 338/340). So the entitlement is committed, then the webhook aborts.
This is unanticipated by the record AND by prior docs.

### REFUTED (minor) — "errors surface as 400"
Record CODE-PATH TRACE step 18 (lines 228-229) says re-raised errors surface as
"400 (StripeWebhookError) or 400 (generic Exception)". Incomplete: a `KeyError`
(reachable via the missing-onboarding-session path above, and via control-plane
`raise KeyError(...)` such as grant_arclink_refuel_credit control.py:4421) is caught
by hosted_api.py:4243 `except KeyError` → **404 not_found**, not 400. ValueError
subclasses (ArcLinkEntitlementError) do fall to the generic 400 (hosted_api.py:4246-
4253) — that part is correct. Both are non-2xx so Stripe still retries, but the
"all 400" statement is inaccurate.

### NEW GAP (MEDIUM) — `mirror_status="none"` crashes the subscription mirror write
The record verified the mirror status set MATCHES the schema CHECK, but missed the
fallback that can emit an out-of-set value:
- entitlements.py:62 `_stripe_subscription_mirror_status` returns
  `candidate if candidate in SUBSCRIPTION_MIRROR_STATUSES else entitlement_state`.
- `entitlement_state` comes from `_entitlement_for_stripe_event`, whose DEFAULT
  return is `"none"` (entitlements.py:413).
- `"none"` is in `ARCLINK_ENTITLEMENT_STATES` (control.py:3171) but NOT in
  `ARCLINK_SUBSCRIPTION_STATUSES` (control.py:3195-3206) and NOT in the
  `arclink_subscriptions.status` CHECK (control.py:1013).
- `upsert_arclink_subscription_mirror` validates via
  `_validate_arclink_status(status, ARCLINK_SUBSCRIPTION_STATUSES, ...)`
  (control.py:4710) which RAISES ValueError for `"none"` (control.py:3253-3254).
Reachable: a `customer.subscription.updated` (in
ENTITLEMENT_MUTATING_STRIPE_EVENTS, entitlements.py:142-152) with a `sub_...` id
(so `subscription_id` truthy, entitlements.py:707) and an `obj.status` that is
blank/absent or an unrecognized Stripe status (Stripe statuses are a superset; a
missing `status` key yields `candidate=""` → not in mirror set → fallback to
`entitlement_state="none"`). Result: ValueError → rollback → 400 → permanent
retry. Fail-closed, but a real availability defect neither the record nor prior
docs name.

### CONFIRMED — raw-body invariant (CANON-02 seam)
`stripe_webhook` absent from `_JSON_OBJECT_ROUTES` (hosted_api.py:3875-3899; only
`telegram_webhook` is a webhook in that set). Dispatch passes raw `body`
(hosted_api.py:4023 → `_handle_stripe_webhook(conn, body, ...)`), and
`process_stripe_webhook(payload=raw_body, ...)` (hosted_api.py:906-908). HMAC is
computed over `f"{stamp}.{payload}"` (adapters.py:151) on that raw str. Both ends
verified. TRUE.

### CONFIRMED — unset-secret 503 fail-closed (CANON-02)
hosted_api.py:892-904 returns 503 `stripe_webhook_secret_unset` when
`config.stripe_webhook_secret` blank. TRUE. (Ordering nit: the webhook rate-limit
at hosted_api.py:3993-4000 runs BEFORE this 503, contrary to the record's trace
step-1 ordering — cosmetic, not a defect.)

### CONFIRMED — HMAC verify (constant-time, tolerance, parse)
adapters.py:157-176: blank-secret raise (:157-158), `t` int parse (:165-167), 300s
tolerance `abs(now-t)>tol` (:168-169), `hmac.compare_digest` (:171), JSON-object
check (:174-175). TRUE.

### CONFIRMED — multi-`v1` rotation not handled (RISK MEDIUM)
adapters.py:159-163 builds `parts` dict keyed by `v1`; duplicate `v1=` keys
overwrite, so only the LAST survives, and :170-171 compares against that single
value. During Stripe secret rotation two `v1=` are sent; if the matching one is
not last, verification fails → 400/retry. TRUE.

### CONFIRMED — refuel-CHECKOUT grant lacks idempotency guard (RISK-1)
`grant_arclink_refuel_credit` (control.py:4397-4468) mints `_arclink_id("refuel")`
and INSERTs unconditionally (control.py:4436-4456); no `(source_kind,source_id)`
pre-check, PK is `credit_id` only (control.py:1020-1032), no UNIQUE. Contrast the
allowance path's `existing` guard (control.py:4317-4331). TRUE. The record's
single-transaction mitigation argument is itself UNDERMINED by the premature-commit
finding above — but note the refuel branch (entitlements.py:572-650) does NOT call
the onboarding sync, so its own grant+apply+mark stay in one txn (entitlements.py:
598,616,641,642). So RISK-1's "normal replay is non-doubling" holds for the refuel
branch specifically; the atomicity break is on the SUBSCRIPTION/checkout-with-
onboarding branch. Severity MEDIUM is acceptable.

### CONFIRMED — entitlement branch has no ownership assertion (RISK MEDIUM)
entitlements.py:724-740 writes entitlement from metadata-derived `user_id` with no
`_assert_*` (unlike refuel at :583). Gated only by HMAC. TRUE. Nuance the record
missed: when `stripe_customer_email` is present, the user_id is first re-resolved
through `merge_arclink_user_identity_by_email` (entitlements.py:674-688), whose
winner is chosen by email (control.py:3728-3739), so an attacker-supplied
`arclink_user_id` can be OVERRIDDEN by the email-based winner — which both narrows
(email mismatch can't target an arbitrary victim) and widens (a shared/typo email
could repoint rows) the blast radius. Secret-gated, MEDIUM stands.

### CONFIRMED — refuel apply skips BEGIN IMMEDIATE inside webhook (RISK LOW)
control.py:4526-4528 `own_txn = not conn.in_transaction`; IMMEDIATE only when
own_txn. Inside the webhook txn own_txn=False → no escalation, and the except-block
rollback (control.py:4634-4635) is also skipped (own_txn=False), deferring to the
webhook's outer handler. Optimistic `rowcount!=1` guards at control.py:4581-4582,
4614-4615. TRUE.

### CONFIRMED — `refuel_paid` synthetic state (DRIFT #1)
`entitlement_state="refuel_paid"` (entitlements.py:647) is not in
`ARCLINK_ENTITLEMENT_STATES` (control.py:3171). Returned only as a result marker;
never written to `arclink_users`. TRUE.

### CONFIRMED — reconciliation seam (CANON-02 read)
`ReconciliationDrift(kind,user_id,detail)` (entitlements.py:30-33) consumed as
`{kind,user_id,detail}` at api_auth.py:4856 under
`authenticate_arclink_admin_session` (api_auth.py:4852). Both ends verified. TRUE.

### CONFIRMED — control-plane seams (entitlement write / gate advance / mirror)
- set_arclink_user_entitlement validates against ARCLINK_ENTITLEMENT_STATES
  (control.py:3844). TRUE.
- advance_arclink_entitlement_gates_for_user returns list[str] of advanced
  deployment ids (control.py:3965-3985), idempotent per-deployment gate
  (control.py:3942-3943 status guard). TRUE.
- upsert_arclink_subscription_mirror status CHECK (control.py:4710 + schema
  control.py:1013). TRUE — but see the `"none"` fallback gap above.

### CITATION DRIFT (non-fatal)
Record cites `arclink_subscriptions` CREATE at "~4714" — ACTUAL schema is
control.py:1008-1018 (4714 is the INSERT inside the mirror UPSERT function). The
described CHECK content is accurate. Minor; flagged for hygiene.

## SEAM SUMMARY (both-ends re-checked)
| Seam | Record verdict | My re-check |
|---|---|---|
| CANON-02 webhook in/out | YES | CONFIRMED |
| CANON-02 raw-body | YES | CONFIRMED |
| CANON-02 reconciliation | YES | CONFIRMED |
| CANON-01 entitlement write | YES | CONFIRMED |
| CANON-01 gate advance | YES | CONFIRMED |
| CANON-01 sub mirror | YES | CONFIRMED shape; `"none"` fallback escapes CHECK (NEW MEDIUM) |
| CANON-01 identity merge | YES | CONFIRMED (commit=False honored) |
| CANON-01 refuel grant/apply | YES | CONFIRMED (grant lacks idempotency, known) |
| CANON-01 allowance | YES | CONFIRMED (idempotency guard present) |
| **CANON-04 onboarding sync** | **PARTIAL (not opened)** | **OPENED → premature commit + entitlement-survives-failure (NEW HIGH); KeyError→404 path** |

## OVERALL
Record is a competent, largely-correct audit of the named risks and the seam
shapes, and its happy-path trace checks out. BUT it is **not fully trustworthy**:
its central atomicity claim is false on the most common real path, it cleared a
"no premature commit" self-check it never actually performed on the implicated
path, and it left the CANON-04 seam unopened — exactly where the worst defect
lives. Two NEW gaps (HIGH premature-commit/atomicity break + entitlement-survives-
failure; MEDIUM `mirror_status="none"` crash) and one inaccuracy (errors are not
uniformly 400; KeyError→404). Confirmed risks: 6 of the record's named risks
re-verified true.
