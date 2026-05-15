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

Captain delivery uses `notification_outbox` rows with
`target_kind='captain-wrapped'`. Rows resolve to the Captain's known
Telegram/Discord home channel when available, carry only safe metadata in
`extra_json`, and set `next_attempt_at` after supported quiet-hours windows
such as `22:00-08:00`.

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
./deploy.sh docker ps
./deploy.sh docker logs arclink-wrapped
./deploy.sh docker health
```

Live Telegram/Discord delivery and production deploy/upgrade remain
operator-gated. Build validation should exercise pure handler/API paths and
outbox rows without mutating live command menus or webhooks.

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
