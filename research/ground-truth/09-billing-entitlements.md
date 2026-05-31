# Ground Truth: Billing, Entitlements, Stripe, Refuel, Drift, Plans

Date: 2026-05-30. Branch: arclink. Source of truth = code, not docs.

Scope: entitlement state machine, plan/expansion pricing, refuel credits,
subscription inference allowance, drift detection + targeted comp, what gates
provisioning, and the Fake-Stripe-default vs PG-STRIPE boundary.

Primary code:
- `python/arclink_entitlements.py` (webhook processing, reconciliation drift)
- `python/arclink_control.py` (entitlement state, refuel ledger, allowances,
  plan pricing, comp, subscription mirror, schema/constants)
- `python/arclink_adapters.py` (FakeStripeClient / LiveStripeClient,
  `verify_stripe_webhook`, `resolve_stripe_client`)
- `python/arclink_hosted_api.py` (`/webhooks/stripe`, `/user/billing`,
  `/user/portal`, `/user/refuel-checkout`, `/admin/reconciliation` routing,
  non-current billing ping)
- `python/arclink_api_auth.py` (`read_user_billing_api`,
  `create_user_portal_link_api`, `create_user_refuel_checkout_api`,
  `open_public_onboarding_checkout_api`, `read_admin_reconciliation_api`)
- `python/arclink_chutes.py` (`renewal_lifecycle_for_billing_state`,
  CURRENT/NONCURRENT billing state sets)
- `python/arclink_action_worker.py` (operator `comp` + `refund`/`cancel`
  `stripe_action_apply`)
- `python/arclink_dashboard.py` (billing/entitlement aggregation into dashboard)

---

## (a) What is actually implemented today (local-real)

### Entitlement state machine
- Canonical states: `ARCLINK_ENTITLEMENT_STATES = {"none","paid","comp","past_due","cancelled"}`
  (`arclink_control.py:2779`). Stored on `arclink_users.entitlement_state`,
  with `entitlement_updated_at`.
- `set_arclink_user_entitlement(...)` validates against that set and upserts the
  user row if missing (`arclink_control.py:3443`).
- `_entitlement_for_stripe_event(event_type, obj)` maps Stripe events ->
  entitlement (`arclink_entitlements.py:399`):
  - `checkout.session.completed` -> `paid`
  - `invoice.payment_succeeded` / `invoice.paid` with `status=="paid"` -> `paid`
  - `invoice.payment_failed` -> `past_due`
  - subscription `status` active/trialing -> `paid`; past_due/unpaid ->
    `past_due`; canceled/cancelled/incomplete_expired -> `cancelled`; else `none`.
- `comp` is NOT set by Stripe; it is set by `comp_arclink_subscription(...)`
  (`arclink_control.py:3596`) — account-level comp sets `entitlement_state="comp"`;
  deployment-scoped comp writes an audit row (`action="comp_subscription"`,
  `target_kind="deployment"`) and lifts only that deployment's gate without
  changing the user-level entitlement.

### What gates provisioning (THE gate)
- `arclink_deployment_can_provision(conn, deployment_id=...)` returns True only
  when `arclink_deployment_entitlement_state(...)` is in `{"paid","comp"}`
  (`arclink_control.py:3535`).
- `arclink_deployment_entitlement_state(...)` (`:3517`) returns `"comp"` if an
  audit row with `action='comp_subscription'` targeting the user OR the
  deployment exists (`_arclink_comp_audit_exists`, `:3500`); otherwise the
  user's `entitlement_state`.
- Deployments are created in status `entitlement_required`. The gate advances:
  - `advance_arclink_entitlement_gate(...)` (`:3539`) flips a single deployment
    `entitlement_required -> provisioning_ready` and emits event
    `entitlement_gate_lifted`.
  - `advance_arclink_entitlement_gates_for_user(...)` (`:3573`) does this for all
    of a user's `entitlement_required` deployments. The Stripe webhook calls this
    after writing the entitlement.
- Provisioning intent build (`arclink_provisioning.py:1275-1354`) re-checks
  `arclink_deployment_can_provision` and sets `blocked_reason="entitlement_required"`
  when not executable. So entitlement gating is enforced at BOTH gate-advance and
  intent-build time.

### Stripe webhook processing (`process_stripe_webhook`, `arclink_entitlements.py:508`)
- Verifies signature via `verify_stripe_webhook(payload, signature, secret)`.
- Requires `event.id` and `event.type`; requires a connection NOT already in a
  transaction; opens an explicit `BEGIN`.
- Idempotency/replay via `arclink_webhook_events` (PK `(provider,event_id)`):
  - `_record_webhook_event` inserts `('stripe', event_id, event_type, ...)`.
  - Already `processed` or `received` -> rollback + return `replayed=True`.
  - Prior `failed`/`received` -> row is reset to `received` and reprocessed
    (replayable).
  - Unknown prior status -> raises (refuses to reprocess).
- Only `ENTITLEMENT_MUTATING_STRIPE_EVENTS` mutate (`:142`):
  `checkout.session.completed`, `customer.subscription.created/updated/deleted`,
  `invoice.payment_failed`, `invoice.payment_succeeded`, `invoice.paid`.
  Other signed events are recorded and marked `processed` (no-op).
- User id resolution: metadata keys `arclink_user_id`/`user_id`,
  `client_reference_id`, and nested `subscription_details` /
  `parent.subscription_details` metadata (`_all_metadata_sources`); falls back to
  `_stripe_user_id_from_local_state` (lookup by subscription id then customer id).
- Email-driven identity merge: `merge_arclink_user_identity_by_email(...)` is
  invoked when Stripe carries a customer email, repointing rows onto a canonical
  user_id and emitting `stripe_user_merged`.
- Subscription mirror: when a `sub_...` id is present, upserts
  `arclink_subscriptions` keyed `subscription_id="stripe:<sub_id>"` via
  `upsert_arclink_subscription_mirror` with a status validated against
  `ARCLINK_SUBSCRIPTION_STATUSES`.
- Writes entitlement (`upsert_arclink_user` if email present, else
  `set_arclink_user_entitlement`), then advances gates for the user.
- On `checkout.session.completed` with an onboarding session id, calls
  `sync_arclink_onboarding_after_entitlement(...)`.
- Emits `stripe_webhook_processed` event; for `past_due`/`cancelled` also writes
  audit `payment_entitlement_blocked` (actor `stripe`).
- Marks the webhook row `processed`, commits. On any exception inside the
  replayable window, marks the row `failed` (replayable) and re-raises.

### Refuel credits (ledger) — local "fair credit" accounting
- Table `arclink_refuel_credits` (`arclink_control.py:1020`): `credit_id`,
  `user_id`, `deployment_id`, `source_kind`, `source_id`, `credit_cents`,
  `remaining_cents`, `status` (`active`/`exhausted`/`revoked` —
  `ARCLINK_REFUEL_CREDIT_STATUSES`), `metadata_json`, timestamps.
- `grant_arclink_refuel_credit(...)` (`:4005`) inserts an `active` credit and
  writes audit `refuel_credit_granted`. Default `credit_cents` from
  `refuel_credit_sku_config()` = 2500 (sku `arclink-arcpod-fuel`, usd).
- `arclink_refuel_credit_balance(...)` (`:4079`) sums remaining cents for active
  credits (optionally scoped to a deployment); `accounting_model="fair_credit_local_ledger"`.
- `apply_arclink_refuel_credit_to_chutes_budget(...)` (`:4110`) consumes credits
  FIFO under `BEGIN IMMEDIATE` with optimistic row guards, then increments the
  deployment's `metadata.chutes.refuel_applied_credit_cents` and
  `metadata.chutes.monthly_budget_cents`. It stamps
  `refuel_provider_balance_application="local_budget_accounting_only_until_live_chutes_proof"`
  and writes audit `refuel_credit_applied`. This is LOCAL BUDGET ACCOUNTING ONLY
  — it never mutates a real Chutes balance.

### Refuel checkout (Stripe `mode=payment`)
- `create_user_refuel_checkout_api(...)` (`arclink_api_auth.py:1610`): authn user
  session, resolve target deployment (`_user_refuel_deployment`, picks newest
  non-torn-down if none given), reject `entitlement_required`/`teardown_complete`/
  `cancelled` deployments, quote via `quote_arclink_refuel_topup`, build a
  `mode=payment` checkout with metadata
  `arclink_purchase_kind="inference_refuel"`, `arclink_user_id`,
  `arclink_deployment_id`, `retail_cents`, `credit_cents`, `provider_credit_bps`,
  `sku_id`. Returns `checkout_url`, `quote`, and full `pricing` options.
- Webhook side (`process_stripe_webhook`, `:572`): when
  `checkout.session.completed` AND `purchase_kind=="inference_refuel"`:
  - requires deployment id + positive `credit_cents`;
  - `_assert_refuel_checkout_account(...)` enforces customer / client_reference /
    account / ArcPod ownership match (rejects cross-account customers);
  - `grant_arclink_refuel_credit(source_kind="stripe_checkout")` then
    `apply_arclink_refuel_credit_to_chutes_budget`; emits
    `stripe_refuel_checkout_processed`; returns
    `entitlement_state="refuel_paid"` (a synthetic result marker, NOT a stored
    entitlement state).

### Subscription inference allowance (monthly plan fuel)
- `apply_subscription_inference_allowance(...)` (`arclink_control.py:3870`):
  on `invoice.payment_succeeded`/`invoice.paid` with entitlement `paid`, grants
  per-deployment fuel. Groups the user's active deployments by plan id (from
  `metadata.selected_plan_id`/`plan_id`, normalized), divides the plan's monthly
  allowance evenly across deployments of that plan, and is idempotent per
  `(user, deployment, source_kind='stripe_subscription_renewal', source_id=invoice:deployment)`.
  Applies through the same refuel ledger + local budget accounting. Emits
  `stripe_subscription_inference_allowance_applied`.
- `subscription_inference_allowance_config(...)` (`:3824`): allowance =
  `ARCLINK_SUBSCRIPTION_INFERENCE_CREDIT_BPS` (default 2000 bps = 20%) of plan
  retail, overridable per-plan via env.

### Plan / expansion pricing (`arclink_control.py:3800`)
`ARCLINK_PLAN_RETAIL_CENTS` (cents):
- `founders` 14900, `sovereign` 19900, `scale` 27500,
- `sovereign_agent_expansion` 9900, `scale_agent_expansion` 7900.
`normalize_arclink_plan_id(...)` (`:3809`) folds aliases: starter/founder/
limited/limited_100_founders -> `founders`; `agent_expansion_scale*` /
`scale_agent_expansion*` -> `scale_agent_expansion`; `agent_expansion*` /
`sovereign_agent_expansion*` -> `sovereign_agent_expansion`; `scale*` ->
`scale`; default -> `sovereign`.

### Refuel top-up pricing model (`refuel_topup_config` / `quote_arclink_refuel_topup`, `:3708`/`:3756`)
- Default amount options cents `[1000,2500,5000,10000]`; custom range
  `[500..50000]`; `provider_credit_bps` default 7000 (70% to provider credit,
  30% gross margin). Quote returns `provider_credit_cents`, `gross_margin_cents`,
  reference model input/output cents-per-million, and estimated million in/out
  pairs. Env-overridable via `ARCLINK_REFUEL_*` vars.

### Drift detection (TWO distinct systems — do not conflate)
1. Stripe reconciliation drift — `detect_stripe_reconciliation_drift(conn)`
   (`arclink_entitlements.py:65`), returns `ReconciliationDrift(kind,user_id,detail)`:
   - `subscription_without_deployment`: active/trialing/paid sub, no live deployment.
   - `deployment_without_subscription`: live deployment, no coverage sub AND not comp.
   - `deployment_subscription_owed_service`: live deployment whose only sub is in
     `past_due`/`unpaid` and not comp.
   Exposed read-only at `GET /admin/reconciliation` via
   `read_admin_reconciliation_api` (`arclink_api_auth.py:4624`).
2. Schema/relationship drift — `arclink_drift_checks(conn)` (`arclink_control.py:4406`)
   and DNS drift (`/admin/dns-drift`). These are structural, NOT billing, and are
   a separate concern.

### Targeted comp (free service grant)
- `comp_arclink_subscription(...)` (`arclink_control.py:3596`): requires a reason;
  idempotent against existing `comp_subscription` audit; account-level sets
  `entitlement_state="comp"` and advances all gates; deployment-level lifts only
  that deployment and leaves user entitlement untouched.
- Operator path: `arclink_action_worker.py:924` `action_type=="comp"` resolves
  the user (target user, or deployment owner) and calls `comp_arclink_subscription`
  with `operation_kind="control_db_comp"`. This is the "audited local entitlement
  comp through the control DB, not an external provider mutation"
  (`arclink_dashboard.py:106`).

### Failed-renewal lifecycle (local policy)
- `renewal_lifecycle_for_billing_state(state)` (`arclink_chutes.py:532`):
  - CURRENT states `{paid, comp}` -> provider access `allowed`.
  - NONCURRENT `{past_due, unpaid, cancelled, none}` -> provider access
    `suspended` immediately, daily reminders, day-7 account/data removal warning,
    day-14 audited purge queue. Surfaced in `/user/billing` as `renewal_lifecycle`.
- Hosted webhook handler queues a Raven ping: `paid` -> originating-channel ping;
  non-`paid` -> `_queue_billing_noncurrent_ping` (`arclink_hosted_api.py:800`)
  with an "Open billing" button. Failures never crash the webhook.

### Billing read surface (`read_user_billing_api`, `arclink_api_auth.py:1539`)
- Returns `entitlement`, `subscriptions` (deduped from deployment billing),
  and `renewal_lifecycle`. Portal link via `create_user_portal_link_api`
  (`:1560`) requires a stored `stripe_customer_id` (else `no_stripe_customer`).

---

## (b) Proof-gated / fake-adapter / local-only

- Stripe client default is FAKE: `resolve_stripe_client(env)` returns a
  `LiveStripeClient` ONLY when `STRIPE_SECRET_KEY` is set; otherwise
  `FakeStripeClient` (`arclink_adapters.py:139`). FakeStripeClient mints
  `cs_test_*` / `bps_test_*` ids and `https://stripe.test/...` URLs.
- `verify_stripe_webhook` (`arclink_adapters.py:156`) implements Stripe's HMAC-
  SHA256 `t=,v1=` scheme with 300s tolerance and recomputes via the in-repo
  `sign_stripe_webhook`. It is real signature verification, but the same module
  signs and verifies, so unit/local tests use a shared `STRIPE_WEBHOOK_SECRET`.
  Live Stripe-signed webhook proof is PG-STRIPE.
- Refuel/allowance provider application is LOCAL BUDGET ACCOUNTING ONLY:
  every applied result and `refuel_credit_sku_config` stamps
  `local_budget_accounting_only_until_live_chutes_proof` and
  `live_purchase: "proof_gated"` (`arclink_control.py:3678`,`:4211`,`:4252`).
  No real Chutes balance is ever moved. (PG-PROVIDER / live Chutes proof.)
- Operator `refund`/`cancel` -> `executor.stripe_action_apply` is gated; live
  mutation is PG-STRIPE (`docs/arclink/operations-runbook.md:148`,
  `control-node-production-runbook.md:97`).
- Webhook misconfig fail-closed: if `STRIPE_WEBHOOK_SECRET` is unset, the hosted
  handler returns 503 `stripe_webhook_secret_unset` so Stripe retries — it never
  silently accepts unsigned payments (`arclink_hosted_api.py:677`).

---

## (c) Canonical vocabulary (exact names from code)

Modules: `arclink_entitlements`, `arclink_control`, `arclink_adapters`,
`arclink_chutes`, `arclink_hosted_api`, `arclink_api_auth`,
`arclink_action_worker`, `arclink_dashboard`, `arclink_provisioning`.

Tables: `arclink_users` (entitlement_state, entitlement_updated_at,
stripe_customer_id), `arclink_subscriptions`, `arclink_refuel_credits`,
`arclink_webhook_events`, `arclink_deployments`, `arclink_audit_log`,
`arclink_events`.

Constants/sets: `ARCLINK_ENTITLEMENT_STATES`, `ARCLINK_SUBSCRIPTION_STATUSES`,
`ARCLINK_REFUEL_CREDIT_STATUSES`, `ARCLINK_DEPLOYMENT_STATUSES`,
`ENTITLEMENT_MUTATING_STRIPE_EVENTS`, `SUBSCRIPTION_COVERAGE_STATUSES`,
`SUBSCRIPTION_OWED_SERVICE_STATUSES`, `SUBSCRIPTION_MIRROR_STATUSES`,
`ARCLINK_PLAN_RETAIL_CENTS`, `CURRENT_BILLING_STATES`, `NONCURRENT_BILLING_STATES`.

Key functions: `process_stripe_webhook`, `detect_stripe_reconciliation_drift`,
`_entitlement_for_stripe_event`, `set_arclink_user_entitlement`,
`advance_arclink_entitlement_gate(s)_for_user`,
`arclink_deployment_can_provision`, `comp_arclink_subscription`,
`grant_arclink_refuel_credit`, `apply_arclink_refuel_credit_to_chutes_budget`,
`apply_subscription_inference_allowance`, `quote_arclink_refuel_topup`,
`refuel_topup_config`, `subscription_inference_allowance_config`,
`normalize_arclink_plan_id`, `upsert_arclink_subscription_mirror`,
`merge_arclink_user_identity_by_email`, `renewal_lifecycle_for_billing_state`,
`resolve_stripe_client`, `verify_stripe_webhook`.

Routes: `POST /api/v1/webhooks/stripe` (`stripe_webhook`),
`GET /api/v1/user/billing` (`user_billing`),
`POST /api/v1/user/portal` (`user_portal_link`),
`POST /api/v1/user/refuel-checkout` (`user_refuel_checkout`),
`GET /api/v1/admin/reconciliation` (`admin_reconciliation`),
plus public onboarding checkout routes (`open_public_onboarding_checkout_api`).

Event/audit names: `stripe_webhook_processed`, `stripe_user_merged`,
`stripe_refuel_checkout_processed`, `stripe_subscription_inference_allowance_applied`,
`entitlement_gate_lifted`, `payment_entitlement_blocked`,
`refuel_credit_granted`, `refuel_credit_applied`, `comp_subscription`.

Source-kinds: `stripe_checkout`, `stripe_subscription_renewal`, `manual`.

Env vars: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`,
`ARCLINK_REFUEL_SKU_ID`, `ARCLINK_REFUEL_CREDIT_CENTS`, `ARCLINK_REFUEL_CURRENCY`,
`ARCLINK_REFUEL_TOPUP_AMOUNTS_CENTS`, `ARCLINK_REFUEL_TOPUP_MIN_CENTS`,
`ARCLINK_REFUEL_TOPUP_MAX_CENTS`, `ARCLINK_REFUEL_PROVIDER_CREDIT_BPS`,
`ARCLINK_REFUEL_STRIPE_PRODUCT_ID`, `ARCLINK_SUBSCRIPTION_INFERENCE_CREDIT_BPS`,
`ARCLINK_<PLAN>_MONTHLY_INFERENCE_CREDIT_CENTS`,
`ARCLINK_WEBHOOK_RATE_LIMIT_STRIPE`.

---

## (d) Undocumented / newer than the docs

- `apply_subscription_inference_allowance` (monthly plan fuel replenishment via
  the refuel ledger, idempotent per invoice+deployment, plan-share split) — only
  lightly noted in API_REFERENCE (one sentence). The plan-share division logic,
  20%-bps default, per-plan env overrides, and `stripe_subscription_renewal`
  source-kind are undocumented.
- `ARCLINK_PLAN_RETAIL_CENTS` exact numbers and `normalize_arclink_plan_id`
  alias folding (including `agent_expansion` -> sovereign/scale expansion) are
  not in any prose doc.
- The synthetic `entitlement_state="refuel_paid"` returned by the webhook for
  refuel checkouts (NOT a stored state) is undocumented and easy to misread.
- Email identity merge during webhook (`merge_arclink_user_identity_by_email`,
  `stripe_user_merged`) is undocumented in the Stripe webhook runbook.
- Nested metadata sourcing (`subscription_details`, `parent.subscription_details`)
  and `_stripe_user_id_from_local_state` fallback (resolve user by sub/customer
  id when metadata is absent) are undocumented.
- Webhook-secret-unset -> 503 fail-closed behavior is in code/API_REFERENCE-ish
  but not the operator webhook runbook.
- Deployment-scoped comp (lift one ArcPod's gate without changing user
  entitlement) is undocumented; docs imply comp is account-level only.
- Refuel top-up pricing economics (70% provider-credit bps, gross margin,
  reference token pricing, estimated pairs) are undocumented in prose.

---

## (e) Per-doc staleness verdicts

### `docs/arclink/operator-stripe-webhook.md` — LIGHT staleness
- Required events list (7) matches `ENTITLEMENT_MUTATING_STRIPE_EVENTS` exactly. Good.
- Endpoint path `/api/v1/webhooks/stripe`, `whsec_` secret, and the verification
  SQL against `arclink_webhook_events` are accurate.
- Corrections needed:
  - Add that an unset `STRIPE_WEBHOOK_SECRET` causes the handler to return 503
    (`stripe_webhook_secret_unset`) so Stripe retries (fail-closed), rather than
    silently dropping events.
  - Note idempotency/replay semantics: duplicate events return `replayed`, and a
    prior `failed`/`received` row is reprocessed.
  - Note that refuel `checkout.session.completed` (mode=payment,
    `purchase_kind=inference_refuel`) flows through the same endpoint and credits
    fuel; subscription invoices also replenish fuel.
  - Mention email-driven user merge can reassign the entitlement to a canonical
    user_id.

### `docs/arclink/data-safety.md` (entitlement parts) — MISSING COVERAGE
- The doc contains essentially NO entitlement/refuel/Stripe content; the only
  match is one unrelated "reconciliation" sentence about child-process env
  hardening (`:281`).
- This subsystem's data-safety story (no secret material in
  `arclink_refuel_credits`/`arclink_subscriptions`/`arclink_webhook_events`
  beyond Stripe ids + raw event payload; entitlement audit trail; comp audit;
  fair-credit local ledger) is undocumented here. Either add an entitlement/
  billing data-safety section or explicitly scope the doc to exclude it.

### `docs/API_REFERENCE.md` (billing routes) — FRESH (light)
- `/user/billing`, `/user/portal`, `/user/refuel-checkout`,
  `/admin/reconciliation` rows and the `renewal_lifecycle` / day-7 / day-14
  description are accurate.
- The refuel paragraph (`:253-258`) correctly states mode=payment, account-match
  gating, and idempotent invoice replenishment.
- Corrections needed (minor):
  - Note that the refuel webhook result reports a synthetic `refuel_paid`
    marker, not a stored entitlement state.
  - Optionally name the plan-share split and `stripe_subscription_renewal`
    source-kind for the monthly fuel replenishment.

### `docs/arclink/sovereign-control-node-symphony.md` (Billing/Entitlements/Refuel
section, `:643-657`) — ACCURATE as a dream-shape, with one honest nuance
- The bullets (Stripe feeds entitlement; entitlement gates provisioning; refuel
  explicit/auditable; expansion prices; Raven sees state) all map to real code.
- "Local entitlement logic is strong, but live Stripe proof remains `PG-STRIPE`"
  is correct: webhook idempotency, gating, comp, refuel ledger, reconciliation
  are all local-real; only LIVE Stripe checkout/webhook proof is gated.
- Nuance to keep honest: refuel/allowance "provider continuation" is
  local-budget-accounting-only (`local_budget_accounting_only_until_live_chutes_proof`)
  — the dream's "provider continuation" is not yet a real provider-balance move
  (PG-PROVIDER), distinct from PG-STRIPE.

---

## (f) True current status of GAP-* this subsystem touches

(From `research/COVERAGE_MATRIX.md` J-05/J-06/J-07 and `seed-gaps-draft.md`.)

- `PG-STRIPE` — OPEN (proof-gated). Local entitlement gate, webhook idempotency/
  replay, signature verification scheme, comp, reconciliation, refuel/allowance
  ledger are all implemented and tested locally with FakeStripeClient + shared
  webhook secret. What remains is a credentialed LIVE Stripe checkout + signed
  webhook proof run. (`LIVE-STRIPE-001`, `LIVE-STRIPE-002` are the seed-gap
  expressions of the same.)
- `REFUEL-LIVE-002` / `PG-PROVIDER` — OPEN (proof-gated). Refuel SKU path,
  quoting, credit grant, and ledger application are local-real, but live
  purchase + real Chutes provider-balance application are unproven
  (`local_budget_accounting_only_until_live_chutes_proof`).
- `GAP-001` (Stripe entitlement gate / checkout / renewal / suspension) —
  source-complete locally; live proof rolls into PG-STRIPE.
- `GAP-002` (plans/pricing + entitlement gate) — source-complete:
  `ARCLINK_PLAN_RETAIL_CENTS`, alias normalization, expansion prices present.
- `GAP-006` / `GAP-031` (refuel credits / provider continuation near threshold) —
  refuel ledger + threshold lifecycle (`renewal_lifecycle_for_billing_state`)
  present; provider continuation copy/policy and live provider proof remain gated.

Net: the billing/entitlement subsystem is source-complete and locally proven;
the only true open items are the LIVE Stripe proof (PG-STRIPE) and the LIVE
Chutes provider-balance proof for refuel/allowance application (PG-PROVIDER).
