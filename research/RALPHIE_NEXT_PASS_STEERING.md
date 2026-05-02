# Ralphie Steering: Next ArcLink Delivery Pass

Use this file as the first practical backlog after commit `9e50eeb`. The
foundation is strong, but the next pass must move from documented readiness to
executable host readiness and live-gated deployment proof.

## Do Not Rebuild

Do not rebuild these slices unless a focused test fails:

- Hosted API/auth/rate-limit/OpenAPI contracts.
- Stripe/Cloudflare/Docker/Chutes fake boundaries.
- Telegram/Discord fake onboarding parity.
- User/admin dashboard API wiring.
- Browser product proof.
- Fake E2E journey harness.
- P13-P16 documentation assets.

## Next Build Order

### 1. Host Readiness And Bootstrap

Add executable, no-secret host readiness tooling.

Required:

- A command or script that checks Docker, Docker Compose, available ports,
  writable ArcLink state root, expected env vars, and Traefik/Cloudflare
  strategy without mutating live providers.
- A machine-readable readiness result that the admin dashboard or operator can
  consume later.
- Tests for missing Docker, missing state root, missing env, and safe redaction.
- Documentation linking the readiness command from the operations runbook.

### 2. Live Readiness Diagnostics

Add a secret-safe diagnostic layer for external providers.

Required:

- Stripe, Cloudflare, Chutes, Telegram, Discord, and host Docker diagnostics.
- Missing credential names are reported; credential values are never returned.
- Diagnostics are no-op/read-only unless an explicit live E2E flag is set.
- Tests prove redaction and missing-credential behavior.

### 3. Live-Gated Docker Executor Path

Improve the executor toward real deployment without enabling mutation by
default.

Required:

- Explicit live flags and idempotency key.
- State root and secret resolver required before any Docker mutation.
- Dry-run output remains secret-free.
- Real Docker commands are isolated behind an injectable runner for tests.
- Rollback/teardown refuses destructive volume deletes without explicit
  destructive confirmation.

### 4. Full Live E2E Expansion

Keep skipped without credentials, but make the harness ready for real proof.

Required:

- One path that can run website onboarding -> checkout -> webhook/entitlement ->
  provisioning -> DNS/health -> user/admin dashboard verification.
- Provider checks can remain separate, but the final live proof must be one
  customer journey.
- Clearly documented env names and setup steps in
  `docs/arclink/live-e2e-secrets-needed.md`.

## Validation Floor

Every pass must run:

```bash
git diff --check
PYTHONPATH=python python3 tests/test_public_repo_hygiene.py
PYTHONPATH=python python3 tests/test_arclink_e2e_fake.py
PYTHONPATH=python python3 tests/test_arclink_e2e_live.py
```

Run additional focused tests for touched modules. Browser claims still require
Playwright evidence.

## Live Credential Ask

When Ralphie reaches a live-blocked step, pause only that live proof and name
the exact missing account/key. Keep no-secret implementation moving around it.
