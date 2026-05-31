# ArcLink Alert Candidates

Structured events and health checks that are alert-worthy. ArcLink ships **one
in-product alerting rail today** — `arclink_health_watch` edge-triggered operator
notifications that flow through `notification_outbox` to the operator channel (see
[In-product alerting rail](#in-product-alerting-rail-implemented-today)). Every
other signal below is a **candidate**: the underlying state table is real and
queryable, but there is **no in-repo emitter** that polls it and pushes to an
external pager. Treat the tables in this doc as the inputs an external integration
would consume, not as proof that an alert fires today.

Honesty split (per the ground-truth brief): the health-watch rail is
**implemented and tested locally**; live bot delivery of operator notifications is
**proof-gated (PG-BOTS)**; the poll-based Stripe/provisioning/DNS/reconciliation
alerts are **aspirational** — no module emits them to a pager in this repo.

## Critical (Immediate Action)

| Signal | Source | Condition | Emitter today |
|--------|--------|-----------|---------------|
| Aggregate health failing | `arclink_health_watch` parses `bin/health.sh` `Summary: N ok, N warn, N fail` | One or more `[fail]` checks (DB unreachable, background service down) | **`arclink_health_watch`** queues an `operator` notification (edge-triggered) |
| API health degraded | `GET /api/v1/health` returns 503 | DB unreachable or background service down | aspirational (health-watch covers this indirectly via `bin/health.sh`) |
| Stripe webhook processing failed | `arclink_webhook_events.status = 'failed'` | Entitlement not applied; customer may be blocked | aspirational (no poller emits to a pager) |
| Provisioning job failed | `arclink_provisioning_jobs.status = 'failed'` | Deployment not started; customer waiting | aspirational (no poller emits to a pager) |
| Service unhealthy | `arclink_service_health.status != 'healthy'` | Container crash or resource exhaustion | aspirational; table is written by `arclink_sovereign_worker` / `arclink_provisioning` / `arclink_pod_migration`, **not** by `arclink_health_watch` |

## Warning (Investigate Within Hours)

All Warning-tier signals are **aspirational candidates** — the named state tables
and helpers are real and queryable, but no in-repo module polls them and pushes an
alert today.

| Signal | Source | Condition |
|--------|--------|-----------|
| DNS drift detected | `reconcile_arclink_dns()` returns non-empty drift | Records may not match expected state |
| Reconciliation drift | `detect_stripe_reconciliation_drift()` returns items | Local and Stripe state diverged |
| Rate limit exhaustion | 429 responses on admin/user login | Possible abuse or misconfigured client |
| Queued actions stale | `arclink_action_intents.status = 'queued'` older than 1 hour | Executor not processing queue |
| Webhook events unprocessed | `arclink_webhook_events.status = 'received'` older than 15 min | Processing delay or handler error |

## Informational (Dashboard Visibility)

| Signal | Source | Purpose |
|--------|--------|---------|
| Onboarding funnel drop-off | `arclink_onboarding_events` | Conversion optimization |
| Deployment count growth | `arclink_deployments` | Capacity planning |
| Audit log volume | `arclink_audit_log` | Operational activity tracking |
| Failed job retry count | `arclink_provisioning_jobs.attempt_count > 2` | Persistent infrastructure issues |

## In-product alerting rail (implemented today)

This is the one alerting path that actually fires in ArcLink. It is
**implemented and tested locally**; live operator delivery over Telegram/Discord
is **proof-gated (PG-BOTS)**.

```
bin/health.sh  ──►  arclink_health_watch  ──►  notification_outbox  ──►  operator channel
                    (edge-triggered)          (target_kind="operator")    (arclink_notification_delivery)
```

### Health watch — `python/arclink_health_watch.py`

- Entry point `bin/health-watch.sh`; runs as the `arclink-health-watch`
  systemd service + timer (`OnActiveSec=5m`, `OnUnitActiveSec=15m`).
- `run_once(cfg, ...)` runs the health command
  (`ARCLINK_HEALTH_WATCH_HEALTH_CMD`, default `bin/health.sh`) and parses the
  `Summary: N ok, N warn, N fail` line plus `[fail]`/`[warn]` lines.
- **Deploy-window suppression:** when `active_deploy_operation(cfg)` is in
  progress, `run_once` returns status `skipped` with `deploy_operation_active:
  True` and queues nothing — so an in-flight `./deploy.sh` does not page the
  operator about expected transient failures.
- **Edge-triggered notify:** it computes a `_failure_fingerprint` (sha256[:16] of
  status/returncode/summary/problem-lines) and only queues an `operator`
  notification when the status is `fail`/`warn` **and** the fingerprint changed
  vs. the last stored one. It queues a separate recovery message when the status
  returns to `ok`. State persists in the `settings` table under
  `arclink_health_watch_last_status` / `_last_fingerprint` / `_last_summary` /
  `_last_notified_at`. Warnings only alert when `--notify-warnings`
  (`ARCLINK_HEALTH_WATCH_NOTIFY_WARNINGS`) is set.
- Problem lines are clipped (max 12 lines / 2200 chars) with a
  "run ./deploy.sh health" pointer; no secrets or paths beyond `bin/health.sh`
  output are emitted.

### Operator channel — `notification_outbox` + delivery worker

- `arclink_health_watch` calls `queue_notification(target_kind="operator", ...)`.
  The operator target resolves from `cfg.operator_notify_platform` /
  `operator_notify_channel_id` (default channel_kind **`tui-only`**, default
  target id `operator`).
- `python/arclink_notification_delivery.py` (entry
  `bin/arclink-notification-delivery.sh`; `arclink-notification-delivery` systemd
  service + timer, `OnUnitActiveSec=5s`) drains undelivered rows. For
  `target_kind="operator"` it dispatches by channel_kind:
  - **`tui-only`** — no external delivery; the row is marked delivered but stays
    readable via the `notifications.list` surface (this is the default).
  - **`telegram`** / **`discord`** — live bot delivery, **proof-gated (PG-BOTS)**
    (fake adapters when tokens are absent).
- `notification_outbox` carries six `target_kind` values total (`operator`,
  `curator`, `user-agent`, `public-bot-user`, `captain-wrapped`,
  `public-agent-turn`); only `operator` is in scope for this doc.

### What this rail does NOT cover

- `arclink_service_health` rows are written by the provisioning/sovereign/migration
  paths, not by health-watch — there is no emitter that turns an unhealthy
  per-service row into an operator notification.
- Bot-delivery errors land in `notification_outbox.delivery_error`; **no operator
  alert is raised from a failed delivery** today.
- There is **no shared operator-visible incident/evidence read model**. The
  `arclink_evidence_runs` table and its DAL are implemented and tested but
  **unwired** — the live-proof runner writes only `evidence/<run_id>.json`
  on disk; nothing reads the table. Do not assume evidence/health history is
  surfaced to the operator. See `docs/arclink/live-e2e-evidence-template.md`.
- Broker/helper command **rejections** are logged to redacted JSONL
  (`arclink_rejection_incidents.py`, `rejections.jsonl`), not to this rail. The
  trusted-host risk boundary itself (GAP-019) is documented authoritatively in
  `docs/arclink/operations-runbook.md`.

## Implementation Notes

- The hosted API emits structured JSON logs via `ARCLINK_LOG_LEVEL`.
- State transitions are recorded in `arclink_audit_log` and `arclink_events`
  (there is no `arclink_timeline_events` table).
- Health snapshots are surfaced in the admin dashboard "infrastructure" tab.
- Queue and deployment status are visible in admin dashboard "queued_actions"
  and "deployments" tabs.
- **External pager integration is not built.** PagerDuty/OpsGenie/Slack-webhook
  fan-out would consume the tables above (or the admin API — see
  `docs/API_REFERENCE.md` and `docs/openapi/arclink-v1.openapi.json`), but no
  in-repo module performs that fan-out today. The only shipped alerting is the
  in-product health-watch → operator rail described above.
- For the gap taxonomy behind the proof gates referenced here, see `GAPS.md`.
