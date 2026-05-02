# Ralphie Steering: Next ArcLink Delivery Pass

Use this file as the controlling backlog after commit `6c70a68`.

The current next objective is controlled by
`research/RALPHIE_SCALE_OPERATIONS_STEERING.md`.

Gaps A-C are landed. Gap D/E no-secret scaffolding is landed: ordered live
journey model, deployment evidence ledger, live E2E harness wiring, evidence
template, runbook links, the operator/admin snapshot, and the live-proof
orchestration runner are landed. The credentialed live run remains externally
blocked. The next non-external work is the scale operations spine: fleet
registry, placement policy, queued admin action worker/executor bridge, rollout
waves, rollback records, stale-queue recovery, and admin/API visibility.

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
- Live proof runner/CLI from `6c70a68`.

## Non-Negotiable BUILD Output

The next BUILD phase must produce product code and tests. A docs-only or
test-only build is not acceptable. Follow
`RALPHIE_LIVE_PROOF_ORCHESTRATION_STEERING.md`.

Expected file-level outputs unless existing files clearly own the concern:

- `python/arclink_fleet.py` or equivalent fleet/placement module.
- `python/arclink_action_worker.py` or equivalent action-intent executor bridge.
- Additive schema helpers for fleet hosts, placement, action attempts, and
  rollout/release records if needed.
- Focused tests proving placement, action execution, retries, redaction,
  rollout/rollback safety, and admin/API visibility.
- Update docs only after the code/tests exist.

Do not let BUILD pass with only `IMPLEMENTATION_PLAN.md` or `research/*.md`
changes.

## Next Build Order

### 1. Fleet And Placement Model

Add host registry and placement helpers that can scale ArcLink beyond one
hand-managed machine:

- host identity, region/tags, status, drain flag, capacity, and observed load;
- deterministic placement policy that prefers healthy non-draining hosts with
  enough CPU/RAM/disk headroom;
- admin read-model summary of capacity, saturation, and deployment placement.

### 2. Action Worker/Executor Bridge

Consume queued admin actions and execute them through fake/live-gated adapters:

- restart/reprovision/dns_repair use Docker/Cloudflare/provisioning intents;
- rotate_chutes_key uses only `secret://` references;
- refund/cancel/comp route through Stripe fake action or safe entitlement state;
- rollout creates durable canary wave records and links rollback plans.

Every action must require idempotency, persist attempts/results, update status,
write audit/events, and avoid plaintext secret material.

### 3. Stale Queue And Rollout Safety

Add focused tests proving:

- stale running actions can be retried or failed deterministically;
- rollouts advance in waves and can pause/rollback;
- rollback plans preserve vault, Nextcloud, qmd, memory, Hermes, and workspace
  state roots.

### 4. Admin/API Visibility

Expose enough read-model data for operators to see fleet hosts, placement,
action attempts, stale queued actions, rollout waves, and last executor result.
Do not claim live provider proof until a credential-backed run exists.

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
