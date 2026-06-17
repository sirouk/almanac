# CANON-07 — Billing & Entitlements

## PIECE
CANON-07 owns the **billing logic and entitlement state machine** of ArcLink. It
covers exactly two tracked files:
- `python/arclink_entitlements.py` (809 lines) — the Stripe webhook processor
  (`process_stripe_webhook`), entitlement-state inference from Stripe events
  (`_entitlement_for_stripe_event`), webhook idempotency/replay ledger
  (`_record_webhook_event` / `_mark_webhook_processed` /
  `_mark_webhook_failed_replayable`), the refuel-checkout account-ownership guard
  (`_assert_refuel_checkout_account`), Stripe-object field extraction helpers
  (user-id / subscription-id / deployment-id / purchase-kind / metadata), and the
  read-only reconciliation drift detector (`detect_stripe_reconciliation_drift`).
- `python/arclink_adapters.py` (374 lines) — the Stripe client adapters
  (`FakeStripeClient`, `LiveStripeClient`, `resolve_stripe_client`), the
  in-repo HMAC webhook signer/verifier (`sign_stripe_webhook` /
  `verify_stripe_webhook`), plus a co-resident Cloudflare DNS fake and
  Traefik/host-naming helpers that are NOT billing (they belong logically with
  CANON-09 ingress / CANON-25 topology but live in this file).

It does NOT own: the entitlement *storage* primitives (`set_arclink_user_entitlement`,
`upsert_arclink_user`, gate advance, comp, refuel-ledger writes, subscription
mirror) — those live in `arclink_control.py` (CANON-01). It does NOT own the HTTP
route, header parsing, rate-limit, or the 503-on-unset-secret guard — those live
in `arclink_hosted_api.py` (CANON-02). CANON-07 is the *brain* that maps a signed
Stripe payload to a sequence of control-plane mutations inside one DB transaction.

## INPUT CONTRACT (code-verified)

### `process_stripe_webhook(conn, *, payload, signature, secret) -> StripeWebhookResult`
(`python/arclink_entitlements.py:508`)
- `conn`: `sqlite3.Connection`. MUST NOT be in a transaction — guarded:
  `if conn.in_transaction: raise ArcLinkEntitlementError(...)` (`:520-521`). The
  function opens its own `conn.execute("BEGIN")` (`:526`).
- `payload`: `str` — the **raw HTTP body bytes decoded to str**. Verified that the
  caller does NOT JSON-parse it first: `stripe_webhook` is absent from
  `_JSON_OBJECT_ROUTES` (`arclink_hosted_api.py:3875-3899`), and the handler
  passes `body` (raw) not `parsed_body` (`arclink_hosted_api.py:4023`,
  `:885-908`). This is required because HMAC is computed over the exact bytes.
- `signature`: `str` — the `Stripe-Signature` header value, format
  `t=<unix>,v1=<hex>` (Stripe scheme). Caller reads it via
  `_api_header(headers, "stripe-signature")` (`arclink_hosted_api.py:905`).
- `secret`: `str` — the webhook signing secret (`whsec_...`). Caller passes
  `config.stripe_webhook_secret` (`arclink_hosted_api.py:907`), sourced from env
  `STRIPE_WEBHOOK_SECRET` (`arclink_hosted_api.py:198`).
- Only callable from `_handle_stripe_webhook` (`arclink_hosted_api.py:906`) after
  the unset-secret 503 guard (`:892-904`). No auth token; the HMAC signature IS
  the authentication.

### `verify_stripe_webhook(payload, signature, secret, *, tolerance_seconds=300) -> dict`
(`python/arclink_adapters.py:156`)
- Raises `StripeWebhookError` if: secret blank (`:157-158`); `t=` missing or
  non-int (`:164-167`); `abs(now - t) > 300s` (`:168-169`); `v1` HMAC mismatch via
  `hmac.compare_digest` (`:171-172`); payload not a JSON object (`:174-175`).
- Returns the parsed event dict on success (`:173-176`).

### `detect_stripe_reconciliation_drift(conn) -> list[ReconciliationDrift]`
(`python/arclink_entitlements.py:65`)
- `conn`: read-only SELECTs only; no writes, no transaction. Pure detector.
- Caller: `read_admin_reconciliation_api` (`arclink_api_auth.py:4853`), admin-gated.

### `resolve_stripe_client(env=None) -> FakeStripeClient | LiveStripeClient`
(`python/arclink_adapters.py:139`)
- Reads `STRIPE_SECRET_KEY` from `env` arg or `os.environ` (`:142-143`). Non-blank
  → `LiveStripeClient`; blank → `FakeStripeClient` (`:144-146`). DEFAULT IS FAKE.

### Stripe-object field helpers (all take `obj: Mapping`, return str/int)
- `_stripe_user_id` (`:208`) — RAISES `ArcLinkEntitlementError` if no id found.
- `_stripe_user_id_or_empty` (`:224`) — swallows that error, returns "".
- `_stripe_user_id_from_local_state` (`:231`) — DB fallback by sub-id then customer-id.
- `_stripe_subscription_id` (`:269`), `_stripe_deployment_id` (`:298`),
  `_stripe_purchase_kind` (`:310`), `_stripe_onboarding_session_id` (`:286`),
  `_stripe_metadata_positive_int` (`:322`), `_stripe_customer_email` (`:390`).

## OUTPUT CONTRACT (code-verified)

### `StripeWebhookResult` (frozen dataclass, `:155-162`)
Fields: `event_id`, `event_type`, `user_id`, `entitlement_state`, `replayed: bool`,
`advanced_deployments: tuple[str,...]`. Consumed by `_handle_stripe_webhook`
(`arclink_hosted_api.py:909-937`): logs the fields, gates pings on
`not replayed and entitlement_state == "paid"` (paid ping, `:916`) vs non-paid
(`:921`), and returns JSON `{status, event_id, event_type, replayed}` with HTTP 200
(`:932-937`).

Return paths of `process_stripe_webhook`:
1. **Replay (already processed/received)**: rollback, return
   `replayed=True`, empty `user_id`/`entitlement_state` (`:534-552`).
2. **Unknown prior status**: rollback + raise `ArcLinkEntitlementError` (`:553-557`)
   — refuses to reprocess a row in an unrecognized state.
3. **Non-mutating signed event**: mark `processed`, commit, return empty result
   with `replayed=not inserted` (`:560-569`).
4. **Refuel checkout** (`checkout.session.completed` + `purchase_kind=="inference_refuel"`):
   returns `entitlement_state="refuel_paid"` (SYNTHETIC — never stored), and
   `advanced_deployments=(deployment_id,)` (`:572-650`).
5. **Subscription/invoice/checkout entitlement path**: writes entitlement, returns
   inferred `entitlement_state`, `advanced_deployments=advanced` (`:652-798`).

### Side-effects / DB writes (all inside one `BEGIN`…`commit`):
- `arclink_webhook_events`: INSERT or replay-reset via `_record_webhook_event`
  (`:426-461`); final UPDATE to `processed` via `_mark_webhook_processed`
  (`:471-478`); on exception within the replayable window, UPSERT to `failed`
  via `_mark_webhook_failed_replayable` (`:491-505`, commits independently `:505`).
- Refuel branch: `upsert_arclink_user` (if customer id), `grant_arclink_refuel_credit`
  (`source_kind="stripe_checkout"`), `apply_arclink_refuel_credit_to_chutes_budget`,
  `append_arclink_event("stripe_refuel_checkout_processed", subject_kind="deployment")`
  (`:591-640`).
- Entitlement branch: optional `merge_arclink_user_identity_by_email` +
  `append_arclink_event("stripe_user_merged")` (`:672-705`);
  `upsert_arclink_subscription_mirror` when a `sub_...` id present (`:707-723`);
  `upsert_arclink_user` (email present) or `set_arclink_user_entitlement` (`:724-740`);
  `advance_arclink_entitlement_gates_for_user` (`:741`);
  `sync_arclink_onboarding_after_entitlement` on checkout w/ onboarding session
  (`:742-750`); `apply_subscription_inference_allowance` on paid invoice (`:751-762`);
  `append_arclink_event("stripe_webhook_processed", subject_kind="user")` (`:763-777`);
  `append_arclink_audit("payment_entitlement_blocked")` when state ∈ {past_due,
  cancelled} (`:778-788`).

### `detect_stripe_reconciliation_drift` output
List of `ReconciliationDrift(kind, user_id, detail)` (`:30-33`) with kinds
`subscription_without_deployment` (`:82-86`), `deployment_without_subscription`
(`:106-110`), `deployment_subscription_owed_service` (`:130-138`).

### Adapter outputs (`arclink_adapters.py`)
- `FakeStripeClient.create_checkout_session` returns dict with `id` (`cs_test_*`),
  `url` (`https://stripe.test/checkout/...`), `mode`, `metadata`,
  `subscription_data`/`payment_intent_data` mirror, `client_reference_id`
  (`:22-57`). Deterministic id from idempotency-key sha256[:18] (`:36-38`).
- `LiveStripeClient.create_checkout_session` returns `{id, url}` only (`:128`).
- `sign_stripe_webhook` returns `t=<stamp>,v1=<hex>` (`:149-153`).

## TOUCH POINTS

### Env vars
- `STRIPE_SECRET_KEY` — read in `resolve_stripe_client` (`arclink_adapters.py:143`);
  presence flips Fake→Live. Also gates `LiveStripeClient.__init__` (`:72-76`).
- `STRIPE_WEBHOOK_SECRET` — consumed by CANON-02 into `config.stripe_webhook_secret`
  (`arclink_hosted_api.py:198`), passed to `process_stripe_webhook`; CANON-07 never
  reads env directly for it.
- Refuel/allowance env (read in `arclink_control.py`, CANON-01, not here):
  `ARCLINK_REFUEL_SKU_ID`, `ARCLINK_REFUEL_CREDIT_CENTS`, `ARCLINK_REFUEL_CURRENCY`
  (`arclink_control.py:4066-4068`), `ARCLINK_SUBSCRIPTION_INFERENCE_CREDIT_BPS`
  (default 2000, `:4220-4221`), per-plan `ARCLINK_<PLAN>_MONTHLY_INFERENCE_CREDIT_CENTS`
  (`:4231-4241`).
- `ARCLINK_WEBHOOK_RATE_LIMIT_STRIPE` — CANON-02 rate-limit, not CANON-07
  (`arclink_hosted_api.py:233`).

### DB tables (r/w) — schema cites in `arclink_control.py`
- `arclink_webhook_events` (PK `(provider,event_id)`, cols `event_type, received_at,
  processed_at, status DEFAULT 'received', payload_json`) — schema
  `arclink_control.py:980-989`. **R/W** here (`entitlements.py:426-505`).
- `arclink_subscriptions` (PK `subscription_id`, status CHECK against the 10-status
  set) — schema `arclink_control.py:~4714` (CREATE) / column CHECK includes
  `active,trialing,paid,past_due,unpaid,canceled,cancelled,incomplete,incomplete_expired,paused`.
  **Written** via `upsert_arclink_subscription_mirror` (control). **Read** in the
  drift detector (`entitlements.py:71-73,113-115,119-121`).
- `arclink_users` (cols `entitlement_state, entitlement_updated_at, stripe_customer_id`)
  — **Read** in `_stripe_user_id_from_local_state` (`:254-262`),
  `_assert_refuel_checkout_account` (`:348-372`), drift detector (`:99-102,124-127`).
- `arclink_deployments` — **Read** in drift detector and refuel-account guard
  (`:375-387`); status set `entitlement_required/teardown_complete/cancelled`
  is the "not-live" exclusion (`:77,92,116`).
- `arclink_refuel_credits` (status CHECK `active/exhausted/revoked`) — schema
  `arclink_control.py:~4439`; written via control funcs.
- `arclink_events`, `arclink_audit_log` — append-only via control helpers.

### External services / secrets handling
- Stripe API via `LiveStripeClient._stripe_module` (deferred `import stripe`,
  sets `stripe.api_key`, `arclink_adapters.py:78-81`). Key never logged.
- HMAC secret used only in `hmac.new(...)` (`:152`) and `compare_digest` (`:171`).
- Cloudflare fake + Traefik label/hostname builders co-resident (`:179-374`) —
  no secrets, pure functions.

### Locks / concurrency
- `process_stripe_webhook` runs under `BEGIN` (deferred) (`:526`).
- `apply_arclink_refuel_credit_to_chutes_budget` uses `BEGIN IMMEDIATE` ONLY when
  it owns the txn (`own_txn = not conn.in_transaction`, `arclink_control.py:4526-4528`);
  inside the webhook it is called with `commit=False` and the txn already open, so
  it does NOT escalate to IMMEDIATE — it relies on the webhook's deferred BEGIN +
  optimistic row guards (`rowcount != 1` → raise, `:4581-4582,4614-4615`).

## CODE-PATH TRACE (entitlement: paid subscription invoice)
1. `_handle_stripe_webhook` checks `config.stripe_webhook_secret`; if unset → 503
   `stripe_webhook_secret_unset` (`arclink_hosted_api.py:892-904`). FAIL-CLOSED.
2. Reads `Stripe-Signature` header (`:905`), calls `process_stripe_webhook(conn,
   payload=raw_body, signature=sig, secret=...)` (`:906-908`).
3. `verify_stripe_webhook` recomputes HMAC over `f"{t}.{payload}"`, checks 300s
   tolerance + `compare_digest`, returns parsed event dict
   (`arclink_adapters.py:156-176`).
4. `event_id`/`event_type` extracted + required (`entitlements.py:516-519`);
   `conn.in_transaction` guard (`:520`); `conn.execute("BEGIN")` (`:526`).
5. `_record_webhook_event` INSERTs `('stripe', event_id, ...)`; on
   `IntegrityError` it reads prior `status` and, if `failed`/`received`, resets the
   row to `received` (replayable) (`:436-461`). Returns `(inserted, status)`.
6. `failure_is_replayable=True` set after the replay branches (`:558`).
7. `event_type in ENTITLEMENT_MUTATING_STRIPE_EVENTS`? (`:560`,
   set at `:142-152`). For `invoice.payment_succeeded` → yes.
8. Not refuel (`_stripe_purchase_kind != "inference_refuel"`), so:
   `subscription_id = _stripe_subscription_id(obj)` (`:652`),
   `user_id` resolved via metadata then DB fallback (`:654-661`); raise if empty
   (`:662-663`).
9. `entitlement_state = _entitlement_for_stripe_event("invoice.payment_succeeded",
   obj)` → `"paid"` iff `obj.status=="paid"` (`entitlements.py:403-404`).
10. Email present → `merge_arclink_user_identity_by_email(commit=False)` repoints
    rows, returns canonical `user_id` + `merged_user_ids` (`:672-688`;
    `arclink_control.py:3707-3832`).
11. `sub_...` id → `upsert_arclink_subscription_mirror(status=mirror_status, ...)`
    (`:707-723`).
12. Email present → `upsert_arclink_user(..., entitlement_state="paid")` else
    `set_arclink_user_entitlement` (`:724-740`).
13. `advance_arclink_entitlement_gates_for_user` flips every
    `entitlement_required` deployment for the user to `provisioning_ready`, emits
    `entitlement_gate_lifted` per deployment (`:741`;
    `arclink_control.py:3965-3985`,`3931-3962`).
14. paid invoice → `apply_subscription_inference_allowance` grants per-deployment
    plan-share fuel, idempotent on
    `(user, deployment, 'stripe_subscription_renewal', invoice:deployment)`
    (`:751-762`; `arclink_control.py:4262-4395`).
15. `append_arclink_event("stripe_webhook_processed")` (`:763-777`);
    `_mark_webhook_processed(commit=False)` (`:789`); `conn.commit()` (`:790`).
16. Returns `StripeWebhookResult(... entitlement_state="paid",
    advanced_deployments=advanced)` (`:791-798`).
17. Back in `_handle_stripe_webhook`: `not replayed and "paid"` →
    `_queue_paid_ping` (wrapped in try/except, never crashes webhook,
    `arclink_hosted_api.py:916-920`); returns HTTP 200 (`:932-937`).
18. On ANY exception after step 6: rollback if in txn, then
    `_mark_webhook_failed_replayable` (own commit), re-raise (`:799-809`). The
    re-raised error surfaces in CANON-02's dispatch as 400 (StripeWebhookError) or
    400 (generic Exception, `arclink_hosted_api.py:4209-4216,4246-4253`) — both
    non-2xx, so Stripe retries.

## CROSS-PIECE CONTRACTS (both ends verified)

| Adjacent piece | Contract (exact shape) | Producer cite | Consumer cite | Both ends |
|---|---|---|---|---|
| CANON-02 (hosted API → webhook) | `process_stripe_webhook(conn, payload=RAW body str, signature=Stripe-Signature, secret=STRIPE_WEBHOOK_SECRET)` → `StripeWebhookResult(event_id,event_type,user_id,entitlement_state,replayed,advanced_deployments)` | `arclink_entitlements.py:508,155-162` | `arclink_hosted_api.py:906-908,909-937` | YES |
| CANON-02 (raw-body invariant) | webhook route NOT JSON-pre-parsed; raw `body` passed | `arclink_entitlements.py:515` (verify over raw) | `arclink_hosted_api.py:3875-3899` (route absent) + `:4009,4023` | YES |
| CANON-02 (reconciliation read) | `ReconciliationDrift(kind,user_id,detail)` → `{kind,user_id,detail}` | `arclink_entitlements.py:30-33,82-138` | `arclink_api_auth.py:4853,4856` | YES |
| CANON-01 (entitlement write) | `set_arclink_user_entitlement(user_id, entitlement_state∈ARCLINK_ENTITLEMENT_STATES, stripe_customer_id, commit=False)` | `arclink_entitlements.py:734-740` | `arclink_control.py:3835-3867` (validates set `:3844`) | YES |
| CANON-01 (gate advance) | `advance_arclink_entitlement_gates_for_user(user_id, commit=False)` → `list[str]` of advanced deployment ids | `arclink_entitlements.py:741` | `arclink_control.py:3965-3985` | YES |
| CANON-01 (subscription mirror) | `upsert_arclink_subscription_mirror(subscription_id="stripe:<sub>", status∈ARCLINK_SUBSCRIPTION_STATUSES, ...)` | `arclink_entitlements.py:713-723` | `arclink_control.py:4698-4739` (CHECK `:4710`) | YES |
| CANON-01 (identity merge) | `merge_arclink_user_identity_by_email(...)` → dict w/ `user_id` + `merged_user_ids` | `arclink_entitlements.py:674-689` | `arclink_control.py:3707-3832` (`:3767,3831`) | YES |
| CANON-01 (refuel grant/apply) | `grant_arclink_refuel_credit(source_kind="stripe_checkout", credit_cents>0, commit=False)` then `apply_arclink_refuel_credit_to_chutes_budget(requested_cents, commit=False)` | `arclink_entitlements.py:598-624` | `arclink_control.py:4397-4468,4502-4647` | YES |
| CANON-01 (allowance) | `apply_subscription_inference_allowance(user_id,stripe_event_id,invoice_id,subscription_id,commit=False)` | `arclink_entitlements.py:753-762` | `arclink_control.py:4262-4395` | YES |
| CANON-04 (onboarding sync) | `sync_arclink_onboarding_after_entitlement(session_id, checkout_session_id, stripe_customer_id, commit=False)` | `arclink_entitlements.py:744-750` | `arclink_onboarding.py` (import `:22`) | PARTIAL (producer verified; consumer body not opened here — CANON-04 owns) |
| CANON-16/01 (refuel→budget) | refuel application mutates `metadata.chutes.monthly_budget_cents` (LOCAL only) | `arclink_control.py:4601-4604` | provider continuation PG-PROVIDER, unverified | NO (proof-gated) |
| Stripe (external, self-signed) | HMAC `t=,v1=` recomputed by same module that signs | `arclink_adapters.py:149-153` (sign) | `:156-176` (verify) | YES (but same key both ends — see DRIFT) |

## CODE vs COMMENT/DOC/NAME DRIFT
1. **`entitlement_state="refuel_paid"` is SYNTHETIC, not a stored state.** The
   return field name implies an entitlement state, but `refuel_paid` is NOT in
   `ARCLINK_ENTITLEMENT_STATES = {"none","paid","comp","past_due","cancelled"}`
   (`arclink_control.py:3171`); it is only a result marker
   (`entitlements.py:647`). Any consumer that pattern-matches `entitlement_state`
   would mis-handle it. Prior doc (`09-billing-entitlements.md:139-140`) flags
   this correctly — code agrees with the doc's warning.
2. **Prior doc line-number drift.** `09-billing-entitlements.md` cites
   `_entitlement_for_stripe_event` at `:399` (correct), `process_stripe_webhook`
   at `:508` (correct), but cites control-plane functions at stale offsets:
   `set_arclink_user_entitlement` doc says `:3443` — ACTUAL `:3835`;
   `comp_arclink_subscription` doc says `:3596` — ACTUAL `:3988`;
   `arclink_deployment_can_provision` doc says `:3535` — ACTUAL `:3927`;
   `advance_arclink_entitlement_gate` doc `:3539` — ACTUAL `:3931`;
   `grant_arclink_refuel_credit` doc `:4005` — ACTUAL `:4397`;
   `apply_subscription_inference_allowance` doc `:3870` — ACTUAL `:4262`;
   `ARCLINK_ENTITLEMENT_STATES` doc `:2779` — ACTUAL `:3171`. The *semantics*
   the doc describes are accurate; only the offsets are stale (file grew).
3. **"verify_stripe_webhook ... `:156`" — doc says `:156` for verify and `:139`
   for resolve.** Both correct. But the doc's claim that
   `_entitlement_for_stripe_event` returns `cancelled` for `incomplete_expired`
   is accurate (`entitlements.py:411`); the doc omits that plain `incomplete`
   (not `incomplete_expired`) falls through to `none` (`:413`).
4. **Comment says BEGIN IMMEDIATE for refuel application** — the prior doc
   (`09:115`) states refuel "consumes credits FIFO under `BEGIN IMMEDIATE`". TRUE
   only when called standalone; inside the webhook the txn is already open so the
   `BEGIN IMMEDIATE` is skipped (`arclink_control.py:4526-4528`). The doc overstates
   isolation for the webhook path.
5. **`LiveStripeClient` docstring** "delegates to the stripe SDK" — accurate, but
   the live path is entirely UNTESTED in-repo (deferred import, no fixture).
   Name/docstring promise live behavior that is proof-gated (PG-STRIPE).
6. **Adapter file name vs content.** `arclink_adapters.py` is assigned to CANON-07
   for billing, but >50% of it (`:179-374`) is Cloudflare DNS + Traefik/hostname
   helpers with zero billing relevance — a packaging drift, not a logic bug.

## ADVERSARIAL SELF-CHECK
1. **Replay safety of the `failed`→`received` reset for refuel credits.**
   `_record_webhook_event` resets a prior `failed` OR `received` row to `received`
   and reprocesses (`:446-461`). `grant_arclink_refuel_credit` mints a fresh
   `credit_id` and INSERTs UNCONDITIONALLY — no `(source_kind,source_id)` guard, no
   UNIQUE constraint (schema PK is `credit_id` only) (`arclink_control.py:4436-4456`),
   UNLIKE the allowance path which checks `existing` (`:4317-4331`). CLAIM (revised
   after tracing): a double-grant is NOT reachable via normal replay because the
   grant, the apply, and `_mark_webhook_processed` are in the SAME `BEGIN`
   transaction (`entitlements.py:526,598,616,641,642`). If the txn commits, the row
   is `processed` and a replay returns early (`:535-543`) BEFORE the refuel branch.
   If the txn rolls back, the credit grant rolled back too, so the `failed`-row
   replay performs the FIRST successful grant, not a duplicate. FALSIFIER: the ONLY
   double-grant window is if processing succeeds and commits the credit, but the
   commit of the `processed` status mark is somehow separated — it is NOT (single
   `conn.commit()` at `:642`). So the residual risk is lower than first feared, BUT
   the missing idempotency guard is still a latent footgun if any future caller
   commits the grant in a separate txn from the status mark. **Still the most
   important thing to cross-check.** (See RISK-1, downgraded to MEDIUM.)
2. **`prior status == 'received'` returns `replayed=True` and does nothing.** A row
   stuck in `received` (e.g. a crash between INSERT-commit-false and final mark,
   but the BEGIN means INSERT is uncommitted on crash, so it should never persist
   as `received`). CLAIM: a persisted `received` only arises from the explicit
   reset path or a non-mutating event that committed `processed`. FALSIFIER: if
   any path commits a `received` row without reaching `processed`, all future
   deliveries are silently dropped as replays. I traced no such path, but the
   `_record_webhook_event(commit=True)` default (`:422,433`) is reachable if some
   other caller uses it standalone.
3. **HMAC same-key sign+verify.** `sign_stripe_webhook` and `verify_stripe_webhook`
   share the module and the secret. CLAIM: real Stripe signs with the same
   `whsec_`, so live verification works. FALSIFIER: Stripe's real scheme may
   include the `t.` payload exactly as implemented (`f"{t}.{payload}"`,
   `:151`) — this MATCHES Stripe's documented `signed_payload = timestamp + "." +
   body`, so it should verify live, but no live signature fixture exists in-repo to
   prove byte-equality (PG-STRIPE).
4. **User-id resolution order.** `_stripe_user_id_or_empty` then DB fallback
   (`:654-661`). CLAIM: metadata wins over DB lookup. FALSIFIER: if metadata
   carries a stale/wrong `arclink_user_id` (attacker-supplied in a refuel checkout
   they don't own), the account guard `_assert_refuel_checkout_account` is the only
   defense — and it only runs on the REFUEL branch (`:583`), NOT the
   subscription/entitlement branch. A forged metadata user_id on a *signed*
   subscription event would write entitlement to an arbitrary user. The signature
   gate means only Stripe (or someone with the webhook secret) can do this, so the
   blast radius is limited to misconfigured Stripe metadata, not external attackers.
5. **Email merge inside the webhook txn.** Merge does direct multi-table
   `UPDATE ... WHERE user_id IN (...)` (`arclink_control.py:3783-3797`) with
   `commit=False`. CLAIM: it stays inside the webhook BEGIN and rolls back on
   failure. FALSIFIER: if merge internally committed, a later failure would leave a
   half-merged state. I verified `_arclink_commit(conn, commit=False)` is honored
   (`:3765,3829`) — no premature commit.

## OPEN FOR CODEX FEDERATION
1. **Refuel-checkout double-grant on replay (RISK-1, MEDIUM).** I argue the
   single-transaction design (grant + apply + status-mark all under one
   `BEGIN`/`commit`, `entitlements.py:526,642`) makes a normal replay non-doubling:
   a committed refuel is `processed` (replay short-circuits `:535-543`), a
   rolled-back one is the first real grant. Independently confirm there is NO path
   that commits the credit grant in a transaction SEPARATE from the
   `_mark_webhook_processed`, and confirm `grant_arclink_refuel_credit` truly lacks
   any `(source_kind,source_id)` uniqueness guard/constraint
   (`arclink_control.py:4436-4456`). If the single-txn invariant holds, this drops
   from money-loss to latent-footgun.
2. **Forged-metadata entitlement write on the subscription branch.** Verify that no
   account-ownership assertion gates the non-refuel entitlement write
   (`entitlements.py:724-740`) — only signature verification stands between
   attacker-influenced `arclink_user_id` metadata and an entitlement mutation.
   Assess real-world reachability given Stripe controls metadata.
3. **`received`-status silent-drop.** Independently confirm there is no code path
   that persists an `arclink_webhook_events` row in `received` without advancing it
   to `processed`/`failed`, which would silently swallow all future redeliveries
   of that event id.
4. **Live HMAC byte-equality with Stripe.** Confirm `f"{t}.{payload}"`
   (`arclink_adapters.py:151`) matches Stripe's real `signed_payload` for chunked /
   multi-`v1` signatures (Stripe can send multiple `v1=` for rotated secrets; this
   code parses only the LAST `v1` into a single key, `:160-163`).

## RISKS (severity-ranked, code-cited)
- **MEDIUM — Refuel-checkout credit grant lacks idempotency guard.**
  `grant_arclink_refuel_credit(source_kind="stripe_checkout", source_id=obj.id or
  event_id)` (`arclink_entitlements.py:598-615`) mints a fresh `credit_id` and
  INSERTs with NO `(source_kind,source_id)` pre-existence check and no UNIQUE
  constraint (`arclink_control.py:4436-4456`; PK is `credit_id` only), unlike the
  allowance path (`:4317-4331`). NORMAL replay does NOT double-grant because grant +
  apply + `_mark_webhook_processed` share one transaction (`entitlements.py:526,642`):
  a committed event is `processed` (replay short-circuits at `:535-543`), a
  rolled-back event re-grants for the first time. Residual risk: a latent footgun if
  any future code commits the grant separately from the status mark, plus no
  defense against a redelivery whose `event.id` differs but represents the same
  Stripe checkout (Stripe uses a stable event id, so low). Recommend a
  `(user,deployment,'stripe_checkout',source_id)` existence check mirroring the
  allowance guard for defense-in-depth.
- **MEDIUM — Entitlement branch has no account-ownership assertion.** Unlike the
  refuel branch's `_assert_refuel_checkout_account` (`:583`), the
  subscription/invoice path (`:724-740`) trusts metadata `arclink_user_id`
  directly. Gated only by the webhook HMAC; a Stripe-side metadata misconfiguration
  (or webhook-secret leak) writes entitlement to an arbitrary user_id.
- **MEDIUM — Multiple-`v1` signatures not handled.** `verify_stripe_webhook`
  parses the signature into a dict keyed by `v1`, so only the LAST `v1=` survives
  (`arclink_adapters.py:159-163,171`). During Stripe secret rotation Stripe sends
  two `v1=` values; if the matching one is not last, verification fails and the
  webhook 400s/retries (fail-closed, not money-loss, but availability).
- **LOW — `received` replay returns success silently.** A redelivery of an
  in-flight event returns `replayed=True` with empty `user_id` (`:544-552`); the
  caller emits HTTP 200, so Stripe stops retrying. If the original processing later
  failed-and-rolled-back (leaving no `received` row, since BEGIN was uncommitted)
  this is moot — but any standalone `_record_webhook_event(commit=True)` use could
  strand a `received` row.
- **LOW — Refuel application skips `BEGIN IMMEDIATE` inside webhook.** Relies on the
  webhook's deferred `BEGIN` + optimistic `rowcount` guards
  (`arclink_control.py:4526-4528,4581-4582`). Under concurrent webhook + operator
  refuel on the same deployment, SQLite deferred locking + the rowcount guard
  raises rather than corrupts — safe but surfaces as a webhook 400/retry.
- **INFO — `arclink_adapters.py` mixes billing + DNS/Traefik.** `:179-374` are
  non-billing; packaging drift only.
- **INFO — Live Stripe path entirely proof-gated (PG-STRIPE).** `LiveStripeClient`
  (`arclink_adapters.py:66-136`) has no in-repo test; default is FakeStripeClient.

## VERDICT
CANON-07 **provably does its core job** for the local-real path: it verifies a
Stripe HMAC over the exact raw body (`verify_stripe_webhook`), enforces a real
idempotency/replay ledger keyed on `(provider,event_id)`, maps Stripe events to a
constrained entitlement vocabulary, writes entitlement + advances provisioning
gates + mirrors subscriptions + grants fuel — all inside ONE transaction with
fail-closed rollback-and-mark-`failed` on error. Both ends of every control-plane
and hosted-API seam were opened and verified to match (shapes, status sets, return
keys). Load-bearing strengths: the raw-body invariant (route correctly excluded
from JSON pre-parse), the unset-secret 503 fail-closed (CANON-02), the
constant-time `compare_digest`, the allowance idempotency guard, the
single-transaction commit boundary, and the optimistic-row-guard refuel ledger.
Real weaknesses: (1) the refuel-CHECKOUT grant has NO `(source_kind,source_id)`
idempotency guard — mitigated to MEDIUM by the single-transaction design that makes
normal replays non-doubling, but a latent footgun; (2) the entitlement (non-refuel)
branch trusts metadata user-id with no ownership assertion (MEDIUM, secret-gated);
(3) multi-`v1` rotation signatures are not parsed (MEDIUM availability during
rotation); (4) the live Stripe adapter and live Chutes provider-balance application
remain entirely proof-gated (PG-STRIPE / PG-PROVIDER). The subsystem is
source-complete and locally proven; the residual risks are genuine, fixable
defense-in-depth gaps, not merely proof-gates.
