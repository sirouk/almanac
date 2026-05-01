# Ralphie Repair Steering Archive

This file is historical context from an earlier lint HOLD. It is not an active
steering source.

Completed scope:

- Blank Stripe webhook secrets fail closed.
- Failed Stripe webhook rows can be replayed after repair.
- Provisioning retry timestamps and stale errors are cleared correctly.
- Provisioning dry-run intent preserves host/container path boundaries.
- Dedicated per-deployment Nextcloud DB/Redis services are rendered in intent.

Current active BUILD target:

- Stripe webhook transaction atomicity.
- Source of truth:
  `research/RALPHIE_STRIPE_ATOMICITY_STEERING.md`.

Do not use this archive to choose a current BUILD target.
