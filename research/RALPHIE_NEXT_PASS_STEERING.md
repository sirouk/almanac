# Ralphie Steering: Next ArcLink Delivery Pass

Use this file as the controlling backlog after commit `2e6fa98`.

Gaps A-C are landed. Gap D/E no-secret scaffolding is landed: ordered live
journey model, deployment evidence ledger, live E2E harness wiring, evidence
template, and runbook links. The credentialed live run remains externally
blocked, but operator/admin integration of the new readiness, diagnostics, and
evidence surfaces is not blocked.

## Do Not Rebuild

Do not rebuild these slices unless a focused test fails:

- Hosted API/auth/rate-limit/OpenAPI contracts.
- Stripe/Cloudflare/Docker/Chutes fake boundaries.
- Telegram/Discord fake onboarding parity.
- User/admin dashboard API wiring.
- Browser product proof.
- Fake E2E journey harness.
- Host readiness CLI, provider diagnostics CLI, injectable Docker runner.
- Live journey/evidence modules, focused tests, and evidence template from
  `2e6fa98`.

## Non-Negotiable BUILD Output

The next BUILD phase must produce product code and tests. A docs-only or
test-only build is not acceptable.

Expected file-level outputs unless existing files clearly own the concern:

- Read-only hosted API/admin route(s) or dashboard read-model helpers that
  expose host readiness, provider diagnostics, and live-evidence status without
  secret values.
- Admin dashboard/API tests proving authenticated admins can view these
  snapshots and unauthenticated users cannot.
- If the Next.js admin UI already has a matching provider/health/release panel,
  surface "not configured", "ready", and "live proof blocked" states there with
  focused tests. Do not rebuild the whole dashboard.
- Update docs only after the code/tests exist.

Do not let BUILD pass with only `IMPLEMENTATION_PLAN.md` or `research/*.md`
changes.

## Next Build Order

### 1. Operator Snapshot Model

Add a small read-only snapshot that combines:

- `arclink_host_readiness.run_readiness()` summary.
- `arclink_diagnostics.run_diagnostics()` summary.
- `arclink_live_journey.build_journey()` credential/blocker status.
- Latest evidence-template status: "template ready", "credentialed evidence
  missing", "live proof blocked".

The snapshot must never include secret values. Missing credential names are OK.

### 2. Hosted API/Admin Integration

Wire the snapshot into the existing hosted API/admin boundary if possible.

Required:

- Admin-only read route or existing admin dashboard payload field.
- Safe unauthenticated/unauthorized failure behavior.
- JSON shape suitable for the admin dashboard.
- Tests in existing hosted API/dashboard test files or a focused new test.

### 3. UI/Read-Model Surface

If the current dashboard read model or Next.js admin page has a natural
provider/health/evidence panel, surface the new statuses:

- Host readiness: ready/not ready/check details.
- Provider diagnostics: configured/missing by credential name only.
- Live proof: blocked until credentials; evidence template ready.

Keep UI changes small and brand-consistent. Browser claims require Playwright.

### 4. Live Credential Handoff

When a credential-blocked operation is reached, pause only that live operation
and name the exact missing key/account. Do not mark final form complete until a
credential-backed live run exists.

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
PYTHONPATH=python python3 tests/test_arclink_evidence.py
PYTHONPATH=python python3 tests/test_arclink_live_journey.py
```

Run additional focused tests for touched API, dashboard, or web modules.
