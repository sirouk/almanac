# Ralphie Stripe Allowlist Steering Archive

This file is historical context from a completed Stripe allowlist and hygiene
repair. It is not an active steering source.

Completed scope:

- Unsupported signed Stripe events are idempotently recorded without mutating
  user entitlement state.
- `invoice.payment_succeeded` and `invoice.paid` with paid invoice status map to
  ArcLink entitlement `paid`.
- Public hygiene covers ArcLink source, docs, tests, fixtures, prompts, and
  research while skipping the brand kit PDF.

Current active BUILD target:

- Stripe webhook transaction atomicity.
- Source of truth:
  `research/RALPHIE_STRIPE_ATOMICITY_STEERING.md`.

Do not use this archive to choose a current BUILD target.
