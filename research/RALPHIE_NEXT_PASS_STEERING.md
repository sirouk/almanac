# Ralphie Steering: Next ArcLink Delivery Pass

Use this file as the controlling backlog after commit `007b6cb`.

The current next objective is controlled by
`research/RALPHIE_LIVE_PROOF_ORCHESTRATION_STEERING.md`.

Gaps A-C are landed. Gap D/E no-secret scaffolding is landed: ordered live
journey model, deployment evidence ledger, live E2E harness wiring, evidence
template, runbook links, and the operator/admin snapshot are landed. The
credentialed live run remains externally blocked. The next non-external work is
the live-proof orchestration layer: secret-safe env validation, dry-run plan,
credential-gated execution, and redacted evidence artifact output.

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
- Operator snapshot route/UI from `007b6cb`.

## Non-Negotiable BUILD Output

The next BUILD phase must produce product code and tests. A docs-only or
test-only build is not acceptable. Follow
`RALPHIE_LIVE_PROOF_ORCHESTRATION_STEERING.md`.

Expected file-level outputs unless existing files clearly own the concern:

- `python/arclink_live_runner.py` or equivalent orchestration module.
- `bin/arclink-live-proof` or equivalent CLI wrapper.
- Focused tests proving no-secret dry-run, redaction, credential-gated live
  execution, injected fake runners, evidence artifact output, and exit codes.
- Update docs only after the code/tests exist.

Do not let BUILD pass with only `IMPLEMENTATION_PLAN.md` or `research/*.md`
changes.

## Next Build Order

### 1. Live-Proof Runner Model

Add a small orchestration layer that combines:

- `arclink_host_readiness.run_readiness()`.
- `arclink_diagnostics.run_diagnostics()`.
- `arclink_live_journey.build_journey()` and `evaluate_journey()`.
- `arclink_evidence.EvidenceLedger`.

The runner must never include secret values. Missing credential names are OK.

### 2. CLI And Artifact Output

Expose the runner through an operator CLI that can:

- run no-secret dry-run validation by default;
- write a redacted JSON evidence artifact to a predictable path;
- require `ARCLINK_E2E_LIVE=1` plus credentials for live execution;
- return clear exit codes.

### 3. Focused Tests

Add focused tests proving:

- dry-run blocked summaries are useful;
- all artifacts redact secret-looking values;
- credential-present dry-run does not claim live proof;
- injected fake step runners can produce a passing ledger;
- invalid input or failed live execution returns non-zero.

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
