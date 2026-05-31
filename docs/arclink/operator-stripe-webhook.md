# ArcLink Operator Stripe Webhook Setup

Use this when installing a Sovereign Control Node and configuring Stripe from
the Dashboard event-destination flow.

## Destination

In Stripe Dashboard, open **Developers -> Event destinations -> Create event
destination**.

Choose:

- **Events from:** Your account
- **API version:** Keep the dashboard default shown for the account. For the
  current ArcLink sandbox this is `2026-04-22.dahlia`.
- **Events:** Selected events, not All events
- **Destination type:** Webhook endpoint
- **Endpoint URL:** `https://<control-host>/api/v1/webhooks/stripe`

For a Tailscale control node:

```text
https://<node-name>.<tailnet>.ts.net/api/v1/webhooks/stripe
```

## Required Events

Select exactly the events ArcLink mutates entitlements from:

```text
checkout.session.completed
customer.subscription.created
customer.subscription.updated
customer.subscription.deleted
invoice.payment_succeeded
invoice.paid
invoice.payment_failed
```

Do not choose **All events** unless debugging with a throwaway endpoint. ArcLink
records unsupported signed events safely, but selecting only the required events
keeps noise, replay volume, and operational ambiguity down.

This list is the exact `ENTITLEMENT_MUTATING_STRIPE_EVENTS` set in
`arclink_entitlements.py` (`process_stripe_webhook`). Any other signed event is
recorded and marked `processed` as a no-op; only these seven mutate entitlement
or fuel.

## How the Endpoint Processes Events

A few behaviors are worth knowing before you verify, all in
`process_stripe_webhook` (`arclink_entitlements.py`):

- **Idempotency / replay.** Every event is recorded in `arclink_webhook_events`,
  keyed by `(provider, event_id)`. A duplicate of an already-`processed` or
  `received` event short-circuits and returns `replayed=true` (no re-mutation).
  A row left in `failed` or `received` from a prior crash is reset to `received`
  and reprocessed, so a failed delivery is safely retryable. A row in an
  unexpected status refuses to reprocess. This is safe to rely on: Stripe's
  at-least-once delivery will not double-apply entitlements.
- **Email-driven user merge.** When an event carries a Stripe customer email,
  `merge_arclink_user_identity_by_email(...)` may repoint local rows onto a
  canonical `user_id` and emit a `stripe_user_merged` event before the
  entitlement write. A checkout started anonymously can therefore land on the
  account that owns that email.
- **Refuel checkout shares this endpoint.** A `checkout.session.completed` with
  `mode=payment` and metadata `arclink_purchase_kind=inference_refuel` (raised by
  `POST /api/v1/user/refuel-checkout`) is also processed here. It grants an
  `arclink_refuel_credits` ledger entry and replenishes ArcPod Fuel after an
  account-ownership match check. Its webhook result reports a synthetic
  `entitlement_state="refuel_paid"` marker; that is NOT a stored entitlement
  state.
- **Subscription invoices replenish fuel too.** `invoice.payment_succeeded` /
  `invoice.paid` for a `paid` account also grant per-ArcPod monthly fuel
  (`apply_subscription_inference_allowance`, idempotent per invoice + ArcPod)
  through the same refuel ledger.

Honest scope: refuel and subscription-allowance application is **local budget
accounting only** (it stamps
`local_budget_accounting_only_until_live_chutes_proof`) — it never moves a real
Chutes balance. Live provider-balance application is proof-gated behind
PG-PROVIDER, distinct from the PG-STRIPE webhook proof.

## Signing Secret

After creating the destination, reveal the endpoint signing secret in Stripe.
It starts with `whsec_`.

Store that value only in the private host config:

```bash
./deploy.sh control reconfigure
```

When prompted, paste it into **Stripe webhook secret**. Do not put it in
README, Git, tickets, screenshots, or public docs.

The install path writes it to:

```text
arclink-priv/config/docker.env
```

### Fail-closed when the secret is unset

The webhook handler refuses to run without a signing secret. If
`STRIPE_WEBHOOK_SECRET` is unset, `POST /api/v1/webhooks/stripe` returns
`503` with `{"error": "stripe_webhook_secret_unset"}` instead of a `2xx`
(`arclink_hosted_api.py`, `_handle_stripe_webhook`). This is deliberate
money-safety: a `2xx` tells Stripe to stop retrying, which would silently
accept payments while crediting no entitlement. Returning `503` keeps Stripe
retrying (up to ~3 days) and forces an operator to notice the misconfiguration.
This signature check and fail-closed behavior are implemented and tested
locally with a shared webhook secret; live Stripe-signed webhook delivery is
proof-gated behind PG-STRIPE.

## Verification

Run:

```bash
./deploy.sh control health
curl -fsS https://<control-host>/api/v1/health
```

Then complete a test checkout through ArcLink onboarding. Confirm Stripe events
arrived and processed:

```bash
sqlite3 arclink-priv/state/arclink-control.sqlite3 \
  "SELECT event_type,status,processed_at FROM arclink_webhook_events WHERE provider='stripe' ORDER BY received_at DESC LIMIT 10;"
```

Expected result: the checkout completion and subsequent subscription or invoice
events show `processed`, and the linked ArcLink user entitlement becomes `paid`.
Once entitlement is `paid` (or `comp`), the user's ArcPods clear the provisioning
gate (`arclink_deployment_can_provision`). A redelivered event reappears with the
same `event_id` and returns `replayed=true` rather than re-applying — that is
expected, not a duplicate-credit bug.

## Common Mistakes

- Using the Stripe API secret key instead of the webhook signing secret.
- Creating the destination in live mode while ArcLink is configured with test
  keys, or the reverse.
- Sending to `/webhooks/stripe` without the `/api/v1` prefix on the public
  control node.
- Selecting connected-account events for a normal ArcLink account setup.
- Forgetting to re-run `./deploy.sh control install` or `./deploy.sh control
  health` after changing the private config.

## Related

- Route definition, auth, CORS, and rate limits for `/api/v1/webhooks/stripe`:
  `docs/API_REFERENCE.md` and `docs/openapi/arclink-v1.openapi.json` (the route
  catalog SSOT — do not duplicate it here).
- Trust-boundary and Docker-socket/root-service posture (GAP-019):
  `docs/arclink/operations-runbook.md` (authoritative).
- Gap taxonomy and proof-gate status (PG-STRIPE, PG-PROVIDER): `GAPS.md`.
