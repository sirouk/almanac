# ArcLink Alert Candidates

Structured events and health checks that should trigger alerts in a production
monitoring pipeline.

## Critical (Immediate Action)

| Signal | Source | Condition |
|--------|--------|-----------|
| API health degraded | `GET /api/v1/health` returns 503 | DB unreachable or background service down |
| Stripe webhook processing failed | `arclink_stripe_webhooks.status = 'failed'` | Entitlement not applied; customer may be blocked |
| Provisioning job failed | `arclink_provisioning_jobs.status = 'failed'` | Deployment not started; customer waiting |
| Service unhealthy | `arclink_service_health.status != 'healthy'` | Container crash or resource exhaustion |

## Warning (Investigate Within Hours)

| Signal | Source | Condition |
|--------|--------|-----------|
| DNS drift detected | `reconcile_arclink_dns()` returns non-empty drift | Records may not match expected state |
| Reconciliation drift | `detect_stripe_reconciliation_drift()` returns items | Local and Stripe state diverged |
| Rate limit exhaustion | 429 responses on admin/user login | Possible abuse or misconfigured client |
| Queued actions stale | `arclink_action_intents.status = 'queued'` older than 1 hour | Executor not processing queue |
| Webhook events unprocessed | `arclink_stripe_webhooks.status = 'received'` older than 15 min | Processing delay or handler error |

## Informational (Dashboard Visibility)

| Signal | Source | Purpose |
|--------|--------|---------|
| Onboarding funnel drop-off | `arclink_onboarding_events` | Conversion optimization |
| Deployment count growth | `arclink_deployments` | Capacity planning |
| Audit log volume | `arclink_audit_log` | Operational activity tracking |
| Failed job retry count | `arclink_provisioning_jobs.attempt_count > 2` | Persistent infrastructure issues |

## Implementation Notes

- The hosted API emits structured JSON logs via `ARCLINK_LOG_LEVEL`.
- All state transitions are recorded in `arclink_audit_log` and
  `arclink_timeline_events` tables.
- Health snapshots are surfaced in the admin dashboard "infrastructure" tab.
- Queue and deployment status are visible in admin dashboard "queued_actions"
  and "deployments" tabs.
- Alert integration is external: pipe structured logs or poll admin API endpoints
  into PagerDuty, OpsGenie, Slack webhooks, or similar.
