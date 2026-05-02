# Ralphie Steering: Next ArcLink Delivery Pass

Use this file as the controlling backlog after commit `a9ea651`.

The no-secret foundation is strong and should not be rebuilt. Gaps A-C are
landed for host readiness, provider diagnostics, and the injectable Docker
executor runner. The next work is to finish as much of Gap D/E as possible
without live credentials, while keeping live provider mutation blocked until an
operator supplies real accounts and keys.

## Do Not Rebuild

Do not rebuild these slices unless a focused test fails:

- Hosted API/auth/rate-limit/OpenAPI contracts.
- Stripe/Cloudflare/Docker/Chutes fake boundaries.
- Telegram/Discord fake onboarding parity.
- User/admin dashboard API wiring.
- Browser product proof.
- Fake E2E journey harness.
- P13-P16 documentation assets.
- Host readiness CLI, provider diagnostics CLI, and injectable Docker runner
  added in `a9ea651`.

## Next Build Order

## Non-Negotiable BUILD Output

The next BUILD phase must produce product code and tests. A docs-only or
test-only build is not acceptable.

Expected file-level outputs unless an existing file clearly owns the concern:

- New or updated live journey module, preferably `python/arclink_live_journey.py`,
  with secret-redacted step/evidence dataclasses and skip/blocker modeling.
- New or updated evidence module, preferably `python/arclink_evidence.py`, for
  deterministic deployment evidence recording.
- Focused tests, preferably `tests/test_arclink_live_journey.py` and
  `tests/test_arclink_evidence.py`.
- An expanded `tests/test_arclink_e2e_live.py` that uses the ordered journey
  model while still skipping cleanly without credentials.
- A live evidence template under `docs/arclink/`, such as
  `docs/arclink/live-e2e-evidence-template.md`.
- Operations-runbook links for the readiness and diagnostics CLIs added in
  `a9ea651`.

Do not let BUILD pass with only `IMPLEMENTATION_PLAN.md` or `research/*.md`
changes.

### 1. Full Live E2E Journey Expansion (Gap D)

Expand the live E2E harness from separate provider smoke checks into one
credential-gated customer journey.

Required:

- Keep `tests/test_arclink_e2e_live.py` skipped unless `ARCLINK_E2E_LIVE=1`
  and required credentials are present.
- Add one ordered journey path:
  website signup/onboarding -> Stripe checkout/webhook entitlement ->
  provisioning intent -> Docker executor dry-run/live handoff -> Cloudflare
  DNS/readiness -> user dashboard verification -> admin health/audit view.
- Keep provider smoke checks if useful, but the final proof must be a single
  journey object with step names, prerequisites, safe skip reasons, and
  evidence fields.
- Do not print or persist secret values. Evidence may name env var names and
  provider account IDs only if they are non-secret.
- Add tests that prove the live journey skips cleanly without credentials and
  that fake/no-secret evidence stays machine-readable.

### 2. Deployment Evidence Ledger (Gap E)

Create a safe evidence format before live credentials exist.

Required:

- Add a small evidence recorder or schema for live deployment proof. It should
  capture step name, status, timestamps, URLs/hostnames, health summaries,
  commit hash, and redacted provider identifiers.
- Include a template under `docs/arclink/` for the future credentialed live run.
- Add tests proving evidence output is deterministic and secret-redacted.
- Document that real deployment evidence remains externally blocked until the
  operator supplies Stripe, Cloudflare, Chutes, Telegram, Discord, and live host
  credentials.

### 3. Readiness/Diagnostics Operator Integration

Wire the new host readiness and provider diagnostics into operator-facing
surfaces without claiming live proof.

Required:

- Link the readiness and diagnostics CLI commands from the operations runbook.
- If a hosted API/admin endpoint already exists for infrastructure/provider
  state, add read-only adapters for readiness/diagnostic snapshots there.
- If the UI already has matching admin panels, surface "not configured",
  "ready", and "live proof blocked" states without exposing secret values.
- Add focused tests only for touched API/UI code. Do not rebuild dashboards.

### 4. Live Credential Handoff

When Ralphie reaches a credential-blocked operation, pause only that live
operation and name the exact missing key/account.

External blockers:

- Stripe secret key, webhook secret, product/price IDs.
- Cloudflare zone ID and scoped DNS token for `arclink.online`.
- Chutes owner/admin key.
- Telegram bot token.
- Discord app ID, public key, bot token, guild/channel.
- Final production host credentials or provider API token beyond existing SSH.

## Validation Floor

Every pass must run:

```bash
git diff --check
PYTHONPATH=python python3 tests/test_public_repo_hygiene.py
PYTHONPATH=python python3 tests/test_arclink_e2e_fake.py
PYTHONPATH=python python3 tests/test_arclink_e2e_live.py
PYTHONPATH=python python3 tests/test_arclink_host_readiness.py
PYTHONPATH=python python3 tests/test_arclink_diagnostics.py
PYTHONPATH=python python3 tests/test_arclink_executor.py
```

Run additional focused tests for touched modules. Browser/UI claims still
require Playwright evidence.
