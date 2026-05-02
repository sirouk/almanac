# ArcLink Professional Finish Gate

ArcLink is not finished when a local phase reports `done`. ArcLink is finished
when it can be sold, deployed, observed, operated, recovered, and used end to
end with honest evidence.

## Product Finish

- A user can start from the website, Telegram, or Discord and enter the same
  onboarding state machine.
- Checkout, entitlement, provisioning intent, service visibility, support
  guidance, and billing portal state are all visible from the user dashboard.
- The user dashboard shows ArcLink's real technology without hiding it:
  Hermes, qmd, Chutes inference provider state, vaults, memory stubs, skills,
  Nextcloud, code-server, bots, service health, and deployment state.
- Fake/local adapters are labeled as fake/local. Live claims require live E2E
  proof.
- Mobile views prioritize status, alerts, search, and primary recovery
  actions.

## Admin Finish

- Operators can see onboarding funnel state, users, payments, provisioning
  queue, service health, host health, Cloudflare/DNS drift, bot state, provider
  state, audit, and guarded actions.
- Mutating actions require auth, role, CSRF or webhook signature, reason,
  idempotency, and audit.
- Reconciliation drift is visible: Stripe versus local entitlement, active DNS
  versus active deployments, provider state versus configured deployments, and
  healthy services versus billed users.

## Engineering Finish

- Focused deterministic tests exist for each changed layer.
- Browser claims are proven with Playwright or an equivalent browser check on
  desktop and narrow mobile viewports.
- Live external calls are gated behind explicit E2E switches and documented
  credentials.
- No plaintext secrets appear in code, docs, tests, logs, rendered compose, or
  generated specs.
- Documentation states what is real, what is fake/local, what is live-gated,
  and which external credentials remain blocked.

## Brand Finish

Use `docs/arclink/brand-system.md` and the source brand kit. ArcLink should
feel like premium private AI infrastructure: jet black, carbon, soft white,
signal orange, precise status blue/green, Space Grotesk, Inter or Satoshi,
minimal operational interfaces, direct operator language, and visible systems.

Do not use generic AI imagery, broad decorative gradients, vague marketing
copy, or placeholder dashboards.
