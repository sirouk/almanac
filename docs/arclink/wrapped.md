# ArcLink Wrapped

ArcLink Wrapped produces a period report for one Captain from scoped ArcLink
control-plane activity. Generation is read-only over Captain state except for
writing the `arclink_wrapped_reports` row and later notification delivery rows.

## Ownership

`python/arclink_wrapped.py` is the single implementation owner for Wrapped
scoring, scoped reads, redacted rendering, report persistence, cadence mutation,
delivery enqueue, scheduler execution, and aggregate Operator views. API,
dashboard, bot, notification, and Compose code should call into this module
rather than reimplementing Wrapped SQL or privacy decisions.

Inputs are limited to the Captain's own users, Pods, same-Captain Comms,
audits, events, read-only Hermes session counts supplied by the caller, vault
reconciler deltas supplied by the caller, and scoped memory synthesis cards.
Rendered text and persisted ledger excerpts are redacted before storage.

Wrapped must not mutate Captain sessions, memory files, vault content,
providers, payments, deployments, bot registrations, or Hermes core. Cadence
changes are the only Captain preference mutation and are limited to `daily`,
`weekly`, and `monthly`.

## Runtime

`daily` is the default cadence. `weekly` and `monthly` are allowed; anything
more frequent than daily is rejected.

The Docker scheduler is the named `arclink-wrapped` job-loop service. It runs
`bin/arclink-wrapped.sh` through `bin/docker-job-loop.sh`, generates due
daily/weekly/monthly reports, retries failed reports on the next eligible
cycle, and queues persistent failures to the Operator without Captain
narrative. The service does not need the Docker socket.

`list_due_wrapped_captains` only enqueues a Captain when there is something
worth wrapping. A Captain is considered for the current period when no report
exists yet, or when the latest report for that period is `failed` (a retry).
For the missing-report case, an eligibility signal gate (`_has_wrapped_signal`)
must also pass: the Captain must have at least one active Pod and at least one
real signal — a scoped event, audit action, same-Captain Pod Comms message, or
memory synthesis card — in the period. A bare deployment row is inventory, not a
signal, so fresh onboarding or add-Pod activity alone never produces an empty
report. The active Pod set excludes the Operator's in-stack agent
(`_is_operator_deployment`: `deployment_id == "operator"` or a deployment whose
metadata marks `operator_agent`) and excludes terminal deployments
(`cancelled`, `teardown_complete`, `torn_down`).

Each generation runs inside the scheduler's per-Captain try/except. On failure
the scheduler records a `failed` report row for the period (`INSERT OR REPLACE`,
keyed by Captain and period) and increments a per-period failure attempt count.
When attempts reach the persistent-failure threshold (3), it queues a single
`notification_outbox` row with `target_kind='operator'` and
`channel_kind='tui-only'`. That operator notice carries only the Captain id and
period for triage — never any Captain narrative, report text, Markdown, or
ledger.

Captain delivery uses `notification_outbox` rows with
`target_kind='captain-wrapped'`. Rows resolve to the Captain's known
Telegram/Discord home channel (read from `arclink_onboarding_sessions`, with the
identity normalized to a `tg:` or `discord:` target) when available, carry only
safe metadata in `extra_json`, and set `next_attempt_at` after supported
quiet-hours windows such as `22:00-08:00`. When no eligible home channel is
known, no outbox row is queued; instead the report's `delivery_channel` is set
to `unavailable` so the report is not lost or silently retried as if delivery
were pending. Actual delivery over Telegram/Discord is proof-gated behind
PG-BOTS (see the Runbook below); scoring, enqueue, and the `unavailable`
outcome are all implemented and tested locally.

`python/arclink_notification_delivery.py` owns final delivery of queued
`captain-wrapped` rows and marks the matching report delivered only after the
outbox row is successfully delivered.

The hosted API exposes Captain history and cadence through `GET /user/wrapped`
and `POST /user/wrapped-frequency`. The Captain dashboard Wrapped tab renders
the redacted plain-text/Markdown report history and daily/weekly/monthly
selector. `/wrapped-frequency daily|weekly|monthly` gives Raven the same pure
handler path without mutating live platform command registrations during build
validation.

Operators can read `GET /admin/wrapped` and the admin dashboard Wrapped tab.
Those surfaces show aggregate status, due count, failure count, latest score,
and Captain id only; they do not include report text, Markdown, or raw ledger
snippets.

## Runbook

For local proof after Wrapped changes, run the focused suites before broader
control-node validation:

```bash
python3 -m py_compile python/arclink_wrapped.py python/arclink_notification_delivery.py python/arclink_hosted_api.py python/arclink_api_auth.py python/arclink_dashboard.py python/arclink_public_bots.py
python3 tests/test_arclink_wrapped.py
python3 tests/test_arclink_notification_delivery.py
python3 tests/test_arclink_hosted_api.py
python3 tests/test_arclink_dashboard.py
python3 tests/test_arclink_public_bots.py
bash -n deploy.sh bin/*.sh test.sh
```

For Docker-mode proof, verify the named service is present and inspect it
through the canonical Docker control path:

```bash
./deploy.sh control ps
./deploy.sh control logs arclink-wrapped
./deploy.sh control health
```

Live Telegram/Discord delivery is proof-gated behind PG-BOTS, and production
deploy/upgrade remains operator-gated. Build validation should exercise pure
handler/API paths and outbox rows without mutating live command menus or
webhooks.

## Novelty Score

The first implementation uses `wrapped_novelty_v1`:

```text
score = min(100, round(
    10 * unique_event_types
  + 8 * unique_audit_actions
  + 12 * unique_same_captain_comms_pairs
  + 6 * memory_card_count
  + 2 * hermes_turn_count
  + 3 * vault_change_count
  + 10 * completion_ratio
  + min(12, quiet_build_index * 4),
  2,
))
```

The score favors variety across trust-boundary-safe signals over raw volume.
Admin and Operator views must use aggregate score/status data only; Captain
narrative, Markdown, and raw ledger snippets stay Captain-scoped.
