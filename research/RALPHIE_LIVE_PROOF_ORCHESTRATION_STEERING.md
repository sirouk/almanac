# Ralphie Steering: Live Proof Orchestration

Use this file after commit `007b6cb`.

ArcLink has the no-secret foundation, operator snapshot, fake journey, live
journey model, evidence ledger, readiness checks, and provider diagnostics.
The remaining final-form gap is not another dashboard rebuild. The remaining
work is a professional, no-secret live-proof orchestration layer that makes the
credentialed launch run boring, repeatable, and evidence-producing when the
operator supplies real accounts.

## Do Not Rebuild

Do not rebuild completed slices unless a focused test fails:

- Hosted API/auth/rate-limit/OpenAPI contracts.
- Stripe, Cloudflare, Docker, Chutes, Telegram, Discord fake boundaries.
- Telegram/Discord/web onboarding parity.
- User/admin dashboards and existing 18 admin tabs.
- Operator snapshot route/UI from `007b6cb`.
- Browser product proof and fake E2E harness.
- Host readiness, provider diagnostics, live journey, and evidence modules.

## Required BUILD Output

The next BUILD must produce product code and tests. Docs-only work is not
enough.

Target the smallest coherent slice that lets an operator run:

1. a secret-safe credential/env validation pass,
2. a dry-run live-proof plan,
3. a credential-gated live-proof execution path,
4. a redacted evidence ledger written to a predictable artifact path,
5. a clear machine-readable exit status and summary.

Suggested ownership, unless existing files clearly own it better:

- `python/arclink_live_runner.py` or equivalent orchestration module.
- `bin/arclink-live-proof` or equivalent CLI wrapper.
- focused tests such as `tests/test_arclink_live_runner.py`.
- small updates to `docs/arclink/live-e2e-secrets-needed.md`,
  `docs/arclink/live-e2e-evidence-template.md`, or operations docs only after
  code/tests exist.

## Behavioral Requirements

- Default mode is dry-run/no-secret. It must not touch live providers unless
  `ARCLINK_E2E_LIVE=1` and all required credentials for the chosen step exist.
- Missing credentials are reported by environment variable name only.
- Secret values, tokens, API keys, webhook secrets, and bot tokens must never be
  printed, logged, returned, or written to evidence artifacts.
- The runner must compose existing primitives instead of duplicating them:
  `run_readiness`, `run_diagnostics`, `build_journey`, `evaluate_journey`, and
  `EvidenceLedger`.
- Evidence must distinguish:
  - `blocked_missing_credentials`
  - `dry_run_ready`
  - `live_ready_pending_execution`
  - `live_executed`
- A run with no credentials should pass as a dry-run validation and produce a
  useful blocked summary, not fail noisily.
- A run with all fake env values and live disabled should prove redaction and
  planning behavior without calling providers.
- Live execution must require injected runners/adapters or explicit live flags;
  tests should use fakes.

## Acceptance Tests

At minimum, add or update tests that prove:

- no-secret dry-run returns a blocked summary with exact missing env names;
- all returned/written artifacts redact secret-looking values;
- credential-present dry-run marks the plan ready but does not claim live proof;
- injected fake runners can produce a passing evidence ledger;
- CLI exits `0` for dry-run readiness and non-zero only for true execution
  failure or invalid input.

## Validation Floor

Every pass must run:

```bash
git diff --check
PYTHONPATH=python python3 tests/test_arclink_live_runner.py
PYTHONPATH=python python3 tests/test_arclink_e2e_live.py
PYTHONPATH=python python3 tests/test_arclink_evidence.py
PYTHONPATH=python python3 tests/test_arclink_live_journey.py
PYTHONPATH=python python3 tests/test_arclink_host_readiness.py
PYTHONPATH=python python3 tests/test_arclink_diagnostics.py
PYTHONPATH=python python3 tests/test_public_repo_hygiene.py
python3 -m py_compile python/almanac_control.py python/arclink_*.py
```

Run broader hosted API, dashboard, web, or browser checks only if the pass
touches those surfaces.

## External Blockers

Do not mark final form complete until a real credentialed run has been executed
and evidence is captured for:

- Stripe checkout and webhook.
- Cloudflare DNS/hostname.
- Chutes inference/key path.
- Telegram onboarding.
- Discord onboarding.
- Docker/host deployment health.
- User dashboard and admin operator verification.

If credentials are absent, leave the live run blocked and name the exact missing
key/account in the output.
