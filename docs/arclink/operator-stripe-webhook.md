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

## Common Mistakes

- Using the Stripe API secret key instead of the webhook signing secret.
- Creating the destination in live mode while ArcLink is configured with test
  keys, or the reverse.
- Sending to `/webhooks/stripe` without the `/api/v1` prefix on the public
  control node.
- Selecting connected-account events for a normal ArcLink account setup.
- Forgetting to re-run `./deploy.sh control install` or `./deploy.sh control
  health` after changing the private config.
