# Ralphie Dependency/Lint Steering Archive

This file is historical context from a completed dependency/lint repair pass.
It is not an active steering source.

Completed scope:

- `requirements-dev.txt` declares focused dev/lint dependencies.
- Public hygiene scans tracked and untracked text while skipping binary assets.
- Tailscale Serve/Funnel timeout behavior was repaired and validated.
- Targeted and global comp entitlement behavior was repaired and validated.
- Provisioning dry-run secret handling was made explicit for stock images and
  resolver-required custom tokens.

Current active BUILD target:

- Stripe webhook transaction atomicity.
- Source of truth:
  `research/RALPHIE_STRIPE_ATOMICITY_STEERING.md`.

Do not use this archive to choose a current BUILD target.
