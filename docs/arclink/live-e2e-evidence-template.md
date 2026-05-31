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
| 6 | dns_health_check **or** tailscale_ingress_health_check | pending | - | Cloudflare ingress: `dns_health_check`, requires CLOUDFLARE_API_TOKEN_REF or CLOUDFLARE_API_TOKEN plus CLOUDFLARE_ZONE_ID. When `ARCLINK_INGRESS_MODE=tailscale`, this step becomes `tailscale_ingress_health_check`, requires ARCLINK_TAILSCALE_DNS_NAME instead. |
| 7 | docker_deployment_check | pending | - | Requires ARCLINK_E2E_DOCKER |
| 8 | chutes_key_provisioning | pending | - | Requires CHUTES_API_KEY |
| 9 | user_dashboard_verification | pending | - | |
| 10 | admin_dashboard_verification | pending | - | |
| 11 | telegram_bot_check | pending | - | Requires TELEGRAM_BOT_TOKEN |
| 12 | discord_bot_check | pending | - | Requires DISCORD_BOT_TOKEN |

Step 6 is resolved from the deployment's ingress mode (`arclink_live_journey._hosted_ingress_step`):
Cloudflare deployments emit `dns_health_check`; deployments with `ARCLINK_INGRESS_MODE=tailscale`
emit `tailscale_ingress_health_check` (verifies Tailscale Serve/Funnel/certificate and service health,
gated on `ARCLINK_TAILSCALE_DNS_NAME`). Record whichever step your run actually produced.

## Evidence JSON

Run `bin/arclink-live-proof --live --json` and paste the evidence JSON here after
a live hosted run, or use `bin/arclink-live-proof --journey workspace --live
--json` for native Drive, Code, and Terminal TLS proof. The workspace live run
executes `deploy.sh control upgrade`, `deploy.sh control health`, then
Playwright desktop/mobile browser checks for the native Drive, Code, and Terminal plugin
routes. Browser proof records redacted JSON plus sanitized screenshot
references under `evidence/workspace-screenshots/`; do not paste raw command
output, terminal scrollback, local filesystem paths, or credential values. Copy
the artifact from the `evidence/` directory:

```json
{
  "run_id": "",
  "status": "",
  "started_at": 0,
  "finished_at": 0,
  "commit_hash": "",
  "records": [],
  "duration_ms": 0
}
```

The ledger always serializes a `status` field. `run_live_proof` only populates it when a run is
requested live (`--live`) but blocked, stamping the overall runner status —
`blocked_missing_credentials` (required env absent) or `blocked_no_registered_runner` (live
requested but no runner registered, including every external-journey row). For `dry_run_ready` and
`live_executed` runs the field is an empty string and per-step outcomes live in `records`.

Evidence is currently **file-only**: `run_live_proof` writes `evidence/<run_id>.json` and never
calls `store_evidence_run`. The `arclink_evidence_runs` table (and its
`store_evidence_run`/`get_evidence_run`/`list_evidence_runs`/`latest_evidence_status` DAL in
`python/arclink_evidence.py`) is implemented and tested but **unwired** — no dashboard, hosted API,
or Operator Raven surface reads it. Do not treat this artifact as operator-visible persisted state;
attach the JSON file itself to the run record.

## Credentials Used (names only, never values)

- [ ] ARCLINK_E2E_LIVE
- [ ] STRIPE_SECRET_KEY (test mode: sk_test_*)
- [ ] STRIPE_WEBHOOK_SECRET
- [ ] CLOUDFLARE_API_TOKEN_REF or CLOUDFLARE_API_TOKEN (Cloudflare ingress only)
- [ ] CLOUDFLARE_ZONE_ID (Cloudflare ingress only)
- [ ] ARCLINK_TAILSCALE_DNS_NAME (Tailscale ingress only, ARCLINK_INGRESS_MODE=tailscale)
- [ ] CHUTES_API_KEY
- [ ] ARCLINK_E2E_DOCKER
- [ ] TELEGRAM_BOT_TOKEN
- [ ] DISCORD_BOT_TOKEN
- [ ] ARCLINK_WORKSPACE_PROOF_TLS_URL
- [ ] ARCLINK_WORKSPACE_PROOF_AUTH

## Workspace Plugin Proof Steps

| # | Step | Status | Duration (ms) | Notes |
|---|------|--------|---------------|-------|
| 1 | workspace_control_upgrade | pending | - | Requires ARCLINK_E2E_DOCKER |
| 2 | workspace_control_health | pending | - | Requires ARCLINK_E2E_DOCKER |
| 3 | drive_tls_desktop_proof | pending | - | Requires TLS dashboard access |
| 4 | drive_tls_mobile_proof | pending | - | Requires TLS dashboard access |
| 5 | code_tls_desktop_proof | pending | - | Requires TLS dashboard access |
| 6 | code_tls_mobile_proof | pending | - | Requires TLS dashboard access |
| 7 | terminal_tls_desktop_proof | pending | - | Requires TLS dashboard access |
| 8 | terminal_tls_mobile_proof | pending | - | Requires TLS dashboard access |

## Notes

Record any anomalies, timing issues, or provider-specific observations here.
Keep command output, raw terminal scrollback, local host paths, and credential
values out of this file. Screenshot references should be relative artifact
paths only.
