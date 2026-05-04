# ArcLink Live E2E Evidence Template

Template for recording live journey evidence. Fill in after a credentialed run.

## Run Metadata

| Field | Value |
|-------|-------|
| Run ID | `run_<hash>` |
| Commit | `<short hash>` |
| Date | YYYY-MM-DD HH:MM UTC |
| Operator | (redacted) |
| Environment | production / staging |

## Journey Steps

| # | Step | Status | Duration (ms) | Notes |
|---|------|--------|---------------|-------|
| 1 | web_onboarding_start | pending | - | |
| 2 | web_onboarding_checkout | pending | - | Requires STRIPE_SECRET_KEY |
| 3 | stripe_webhook_delivery | pending | - | Requires STRIPE_WEBHOOK_SECRET |
| 4 | entitlement_activation | pending | - | |
| 5 | provisioning_request | pending | - | |
| 6 | dns_health_check | pending | - | Requires CLOUDFLARE_API_TOKEN, CLOUDFLARE_ZONE_ID |
| 7 | docker_deployment_check | pending | - | Requires ARCLINK_E2E_DOCKER |
| 8 | chutes_key_provisioning | pending | - | Requires CHUTES_API_KEY |
| 9 | user_dashboard_verification | pending | - | |
| 10 | admin_dashboard_verification | pending | - | |
| 11 | telegram_bot_check | pending | - | Requires TELEGRAM_BOT_TOKEN |
| 12 | discord_bot_check | pending | - | Requires DISCORD_BOT_TOKEN |

## Evidence JSON

Run `bin/arclink-live-proof --live --json` and paste the evidence JSON here after
a live run, or copy the artifact from the `evidence/` directory:

```json
{
  "run_id": "",
  "started_at": 0,
  "finished_at": 0,
  "commit_hash": "",
  "records": [],
  "duration_ms": 0
}
```

## Credentials Used (names only, never values)

- [ ] ARCLINK_E2E_LIVE
- [ ] STRIPE_SECRET_KEY (test mode: sk_test_*)
- [ ] STRIPE_WEBHOOK_SECRET
- [ ] CLOUDFLARE_API_TOKEN
- [ ] CLOUDFLARE_ZONE_ID
- [ ] CHUTES_API_KEY
- [ ] ARCLINK_E2E_DOCKER
- [ ] TELEGRAM_BOT_TOKEN
- [ ] DISCORD_BOT_TOKEN

## Notes

Record any anomalies, timing issues, or provider-specific observations here.
