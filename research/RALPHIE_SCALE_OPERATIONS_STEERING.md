# Ralphie Steering: ArcLink Scale Operations Spine

This is the controlling next objective after commit `6c70a68`.

ArcLink is not finished simply because the no-secret foundation, dashboards,
live-proof runner, and documentation truth pass exist. The next non-external
gap is the operations spine that lets ArcLink scale beyond one hand-managed
host: fleet registration, placement, queued admin action execution, rollout
waves, rollback records, stale-queue recovery, and admin/API visibility.

Do not route to `done` while this file contains unchecked non-external work.
Only the credentialed live run remains externally blocked.

## Current Truth

Already landed:

- Hosted API, auth, CSRF, rate limits, OpenAPI, user/admin dashboards.
- Stripe, Cloudflare, Docker, Chutes, Telegram, and Discord fake/live-gated
  boundaries.
- Provisioning intent renderer with Docker, DNS, Traefik, state root, service
  health, retry, and rollback planning.
- Live-gated `ArcLinkExecutor` with fake adapters and dry-run/fail-closed
  behavior.
- Queued admin action intents in `arclink_action_intents` with reason,
  idempotency, metadata secret rejection, and audit logging.
- Host readiness, provider diagnostics, operator snapshot, live journey,
  evidence ledger, and `bin/arclink-live-proof`.

Important unfinished truth:

- `arclink_action_intents` are queued and visible, but no worker consumes them
  and binds them to `ArcLinkExecutor`.
- Fleet capacity and placement are not modeled. A future multi-host ArcLink
  cannot choose where a deployment belongs or know when a host is saturated.
- Rollout/canary/rollback are documented and partially represented by executor
  primitives, but there is no durable release plan/read model.
- Queue reconciliation exists as docs/alerts, but there is no executable stale
  action recovery model for admin actions.
- Admin surfaces can see queued actions and service health, but not fleet
  placement, rollout waves, action execution attempts, or executor results.

## Required BUILD Output

The next BUILD phase must add product code and tests. A docs-only build is not
acceptable.

Expected file-level outputs unless existing modules clearly own the concern:

- `python/arclink_fleet.py` or equivalent:
  - host registry helpers;
  - host capacity/resource model;
  - deterministic placement policy;
  - health/capacity summary helpers;
  - secret-free data structures and SQLite helpers.
- `python/arclink_action_worker.py` or equivalent:
  - consumes queued `arclink_action_intents`;
  - transitions intent status `queued -> running -> succeeded/failed`;
  - maps restart/reprovision/dns_repair/rotate_chutes_key/refund/cancel/comp/
    rollout to executor or documented no-op-safe fake adapter calls;
  - records audit/events and result metadata without secret material;
  - is idempotent across retries and safe after partial failures.
- Optional schema extension in `python/almanac_control.py`:
  - fleet hosts table;
  - deployment placement table or host assignment fields;
  - action execution attempt table if needed;
  - release/rollout table if needed.
- Admin/dashboard/API read-model extensions:
  - expose fleet host status, placement, action attempts, stale queued actions,
    rollout waves, and last executor result.
- Focused tests:
  - placement chooses healthy host with enough capacity;
  - placement rejects unhealthy/saturated hosts;
  - restart action calls Docker lifecycle through fake executor and marks
    intent succeeded;
  - DNS repair calls Cloudflare DNS fake executor from stored/rendered desired
    DNS;
  - rotate Chutes key uses only `secret://` references;
  - refund/cancel/comp are routed through Stripe fake action or explicit
    entitlement-safe local state transition;
  - rollout action plans canary waves, records progress, and can rollback
    without deleting state roots;
  - stale running actions are returned to queued or failed with audit/event
    evidence;
  - public hygiene and secret redaction still pass.
- Docs/runbooks updated only after code/tests land.

## Design Constraints

- Keep SQLite-first and Postgres-friendly. Use TEXT ids, ISO timestamps, JSON
  columns as text, and additive migrations.
- Keep all mutating provider paths fail-closed unless live execution is
  explicitly enabled. Tests should use fake adapters.
- Do not store plaintext secrets. Metadata may contain `secret://...` refs only.
- Preserve existing Almanac compatibility. Do not rename mature Almanac runtime
  paths unless the touched code is explicitly ArcLink public/product surface.
- Do not rebuild P1-11, P13-P16, live runner, brand system, or browser proof
  unless a focused test proves a regression.
- Prefer small modules that compose with existing helpers:
  `arclink_dashboard`, `arclink_provisioning`, `arclink_executor`,
  `arclink_api_auth`, and `almanac_control`.

## Suggested Build Order

1. Schema and model:
   - Add fleet host/resource tables and helpers.
   - Add action attempt/result or execution metadata structure.
   - Add release/rollout record helpers if needed.
2. Placement:
   - Implement deterministic host selection from capacity, health, tags/region,
     active deployment load, and operator drain flag.
3. Action worker:
   - Implement one `process_next_arclink_action()` entrypoint and a bounded
     `process_arclink_action_batch()` helper.
   - Inject `ArcLinkExecutor` and fake adapters in tests.
   - Persist status transitions, events, audit rows, and redacted result
     metadata.
4. Rollout and rollback:
   - Implement a no-secret release plan/wave model and rollback linkage.
   - Prove canary progression and rollback state-root preservation.
5. Admin/API visibility:
   - Extend read models/routes enough for operators to see host placement,
     stale actions, action attempts, and rollout state.
6. Validation:
   - Run focused tests first, then the standard validation floor.

## Validation Floor

Every pass must run:

```bash
git diff --check
PYTHONPATH=python python3 tests/test_public_repo_hygiene.py
PYTHONPATH=python python3 tests/test_arclink_admin_actions.py
PYTHONPATH=python python3 tests/test_arclink_executor.py
PYTHONPATH=python python3 tests/test_arclink_provisioning.py
PYTHONPATH=python python3 tests/test_arclink_dashboard.py
PYTHONPATH=python python3 tests/test_arclink_hosted_api.py
PYTHONPATH=python python3 tests/test_arclink_live_runner.py
python3 -m py_compile python/almanac_control.py python/arclink_*.py
```

Run any new focused tests for fleet/action-worker/rollout modules.

## External Blockers

Do not stop this build for these. They block only credentialed proof:

- Stripe secret key, webhook secret, product/price ids.
- Cloudflare zone id and DNS/API token.
- Chutes owner/admin key.
- Telegram bot token.
- Discord app id/public key/bot token/guild/channel.
- Final production host provider keys beyond existing SSH access.
