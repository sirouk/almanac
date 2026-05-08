# Sovereign Control Node Production Runbook

This runbook is proof-gated. It describes the production path, but a live
Control Node is not complete until credentialed health and evidence runs pass.

## Scope

Sovereign Control Node mode is the Dockerized paid self-serve control plane:
public web/API onboarding, Telegram/Discord public bot webhooks, Stripe
checkout/webhooks, domain-or-Tailscale ingress intent, fleet placement,
provisioning jobs, user/admin dashboards, and action/evidence views.

Use:

```bash
./deploy.sh control install
./deploy.sh control health
./deploy.sh control logs [SERVICE]
./deploy.sh control ps
./deploy.sh control upgrade
./deploy.sh control reconfigure
```

Shared Host commands such as `./deploy.sh install` are the operator-led
systemd/shared-user path. Shared Host Docker commands such as
`./deploy.sh docker install` validate the shared-host substrate, not paid
Sovereign pods.

## Credential Checklist

Keep all values in private state, local environment, an interactive prompt, or a
secret manager. Never commit them.

| Area | Required Material |
| --- | --- |
| Stripe | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, product/price ids, portal configuration |
| Domain ingress | Cloudflare zone id or discoverable zone plus scoped DNS/API token |
| Tailscale ingress | Logged-in node, MagicDNS/HTTPS readiness, Serve/Funnel approval where used |
| Public Telegram | Public onboarding bot token and webhook registration |
| Public Discord | Discord bot token/application credentials and interaction endpoint |
| Model provider | Owner/admin API key for per-deployment key lifecycle |
| Fleet host | Docker access, SSH/fleet key where remote execution is enabled, writable state root |
| Notion | Shared integration token, webhook verification secret if Notion callbacks are enabled |

## Install And Configuration

1. Run `./deploy.sh control install`.
2. Choose deployment style: `single-machine` for one starter host, `hetzner`
   for registered Hetzner workers, or `akamai-linode` for registered Akamai
   Linode workers. The single-machine style defaults the executor toward the
   local worker path and starter host registration; hosted-fleet styles default
   toward SSH worker placement.
3. Choose ingress mode: `domain` or `tailscale`.
4. Choose provider adapter mode: `fake` for validation or explicit live mode
   only when credentials and operator approval are present.
5. Configure Stripe price ids and webhook secret.
6. Configure public bot webhook URLs through the generated control host.
7. Run `./deploy.sh control health`.

If a value changes, use `./deploy.sh control reconfigure` and then rerun health.

## Workers And Mutations

`control-provisioner` is disabled by default unless the explicit executor and
provider gates are enabled. Queued admin actions are durable intent; they do not
prove that live Docker, Stripe, Cloudflare, Tailscale, model-provider, Discord,
Telegram, or Notion mutations happened.

Before enabling live mutation paths, verify:

- `ARCLINK_EXECUTOR_ADAPTER` and live/E2E enablement are deliberate.
- The provisioner can reach Docker/fleet hosts and private state.
- Action worker results are recorded and visible in admin evidence/audit views.
- Rollback plans preserve state roots and do not delete vault, Nextcloud,
  memory, qmd, or workspace data by default.

## Stripe Webhook

Create a selected-event Stripe destination at:

```text
https://<control-host>/api/v1/webhooks/stripe
```

Use the endpoint signing secret as `STRIPE_WEBHOOK_SECRET`. If the secret is
unset, the hosted API returns a misconfigured error and 503 so Stripe retries;
it does not silently accept or skip the event.

Webhook rows are stored in `arclink_webhook_events`.

## Evidence Capture

No production claim is complete without evidence:

```bash
bin/arclink-live-proof --live --json
bin/arclink-live-proof --journey workspace --live --json
```

The workspace proof requires the web dependencies under `web/`, a real HTTPS
Hermes dashboard URL, and auth material supplied only through environment. Save
redacted evidence using `docs/arclink/live-e2e-evidence-template.md`.

## Rollback

Use rollback only from recorded deployment/provisioning state. A safe rollback
plan preserves state roots, stops or restarts unhealthy services, and keeps
secret references for manual review. Volume deletion, state-root deletion, DNS
teardown, and provider revocation require separate explicit operator approval
and audit records.

## Known Proof-Gated States

- Fake Stripe/Cloudflare/model-provider/bot adapters prove contract behavior only.
- Dry-run provisioning proves rendered intent, not live container health.
- Queued admin actions prove operator intent, not provider mutation.
- Passing unit tests does not prove live Stripe, ingress, model-provider, bots,
  Notion, fleet host access, or customer dashboard TLS.
