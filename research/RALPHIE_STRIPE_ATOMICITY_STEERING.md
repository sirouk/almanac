# Ralphie Steering: Stripe Webhook Atomicity

## Mission

Fix ArcLink Stripe webhook processing so entitlement mutations are atomic before
live Stripe E2E work begins.

## Current Risk

`python/arclink_entitlements.py` records the webhook row and then calls helper
functions that may commit independently while processing supported Stripe
events. A handler failure after subscription, user entitlement, deployment gate,
audit, or event mutation can leave partial ArcLink state applied while the
webhook row is marked failed and replayable.

This is acceptable for a foundation sketch, but not acceptable before live
payment testing.

## Required Behavior

- Signature verification must still happen before any database write.
- Invalid signatures must still leave no webhook rows.
- New supported Stripe events must process in one transaction covering:
  - webhook receive/reset row
  - subscription mirror changes
  - user entitlement changes
  - deployment gate advancement
  - timeline event rows
  - payment-block audit rows
  - final webhook processed mark
- If supported-event processing fails after any planned mutation, no partial
  subscription, entitlement, deployment, audit, or timeline mutation should
  remain.
- The failed webhook row should remain replayable in a predictable state.
- Processed events must remain idempotent.
- Existing helper APIs in `python/almanac_control.py` should keep their public
  semantics unless tests are updated intentionally. Prefer adding `commit=False`
  or internal no-commit variants for webhook use instead of breaking unrelated
  callers.

## Lint-Hold Follow-Up: Current Stripe Invoice Shape

After the atomicity build, lint uncovered a separate real compatibility defect
that must be repaired before progressing past lint/document:

- Current Stripe invoice objects can put subscription metadata under
  `parent.subscription_details.metadata`.
- Current Stripe invoice objects can put the subscription id under
  `parent.subscription_details.subscription`.
- `python/arclink_entitlements.py` currently only reads top-level
  `subscription_details` metadata and legacy `parent.subscription`, so
  `invoice.payment_succeeded` / `invoice.paid` events with the current nested
  shape fail to find `arclink_user_id` and `sub_*`.

Required repair:

- Add a helper that safely returns `obj["parent"]["subscription_details"]` when
  present and shaped as a mapping.
- Make `_stripe_user_id` read user metadata from both top-level
  `subscription_details.metadata` and current
  `parent.subscription_details.metadata`.
- Make `_stripe_subscription_id` read the current
  `parent.subscription_details.subscription` value when it starts with `sub_`.
- Preserve the existing legacy/top-level extraction behavior.
- Add a no-secret regression in `tests/test_arclink_entitlements.py` using an
  `invoice.payment_succeeded` or `invoice.paid` fixture shaped like:

```python
{
    "id": "in_123",
    "parent": {
        "type": "subscription_details",
        "subscription_details": {
            "subscription": "sub_nested",
            "metadata": {"arclink_user_id": "user_1"},
        },
    },
    "status": "paid",
    "customer": "cus_1",
}
```

The regression must prove the event sets entitlement to `paid`, advances a
matching deployment to `provisioning_ready`, mirrors subscription `sub_nested`,
and remains idempotent on replay.

## Lint-Hold Follow-Up: Transaction Ownership Guard

After the invoice-parent compatibility build, lint uncovered a separate
transaction ownership defect that must be repaired before progressing:

- `process_stripe_webhook()` starts with `conn.execute("BEGIN")`.
- If the caller already has an open transaction, SQLite raises
  `OperationalError: cannot start a transaction within a transaction`.
- The broad `except` then sees `conn.in_transaction` and calls `conn.rollback()`,
  which rolls back the caller-owned pending work. Lint reproduced this by
  inserting an outer `arclink_users` row before calling the webhook handler; the
  row disappeared.

Required repair:

- Add a guard before the webhook handler attempts `BEGIN`, or add explicit
  transaction ownership tracking so the handler only rolls back a transaction it
  successfully opened.
- The preferred simple behavior is to reject active caller transactions with a
  clear `ArcLinkEntitlementError` before writing any webhook rows.
- Do not record a webhook row, mutate subscriptions, mutate entitlement state, or
  roll back caller-owned work when the connection already has an active
  transaction.
- Preserve the existing handler-owned transaction atomicity behavior for normal
  calls.
- Add a no-secret regression in `tests/test_arclink_entitlements.py` that opens a
  caller-owned transaction/pending row, invokes `process_stripe_webhook()` with a
  valid signed payload, catches the expected error, and asserts:
  - the caller-owned pending row still exists;
  - `conn.in_transaction` is still true so the caller can decide to commit or
    roll back;
  - no `arclink_webhook_events` row was written for the rejected event.

## Regression Test

Add a focused regression in `tests/test_arclink_entitlements.py` that injects a
failure after entitlement-related work has begun. The test should prove:

- the webhook row is failed or otherwise replayable as designed;
- the user's pre-event entitlement state is unchanged;
- matching deployment gates remain unchanged;
- no subscription mirror, audit, or timeline rows from the failed attempt
  remain;
- replaying a valid payload still processes cleanly.

Keep the test no-secret and in the repo's current standalone assertion style.

## Validation

Run at minimum:

```bash
python3 tests/test_arclink_entitlements.py
python3 -m py_compile python/arclink_entitlements.py python/almanac_control.py tests/test_arclink_entitlements.py
python3 -m pyflakes python/arclink_entitlements.py python/almanac_control.py tests/test_arclink_entitlements.py
python3 -m ruff check python/arclink_entitlements.py python/almanac_control.py tests/test_arclink_entitlements.py
git diff --check
git diff --cached --check
```

Do not touch live Stripe, Cloudflare, Chutes, Telegram, Discord, Notion, or
host provisioning. Do not add secrets or plaintext credentials.
