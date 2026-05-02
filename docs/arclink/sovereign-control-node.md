# ArcLink Sovereign Control Node

The Sovereign Control Node is the paid self-serve ArcLink control plane. It is
the path for a machine like `s1396`: users arrive through the website, Telegram,
or Discord, answer onboarding questions, complete Stripe checkout, and receive a
separate ArcLink pod deployed onto the fleet.

## Deploy Path

Use:

```bash
./deploy.sh control install
./deploy.sh control ports
./deploy.sh control health
```

The control path delegates to the Docker substrate, but it does not mean
"Shared Host Docker." It starts the hosted product boundary:

- `control-web`: the Next.js ArcLink website, onboarding, user dashboard, and
  admin dashboard.
- `control-api`: the hosted `/api/v1` WSGI API over ArcLink's existing Python
  contracts.
- `arclink-mcp`, `qmd-mcp`, `notion-webhook`, job loops, Redis/Postgres, and
  Nextcloud as the local control-node substrate.

The inherited containerized Shared Host path remains available at:

```bash
./deploy.sh docker install
```

That path is for operator-led shared-host validation and the containerized
Curator/enrollment substrate, not for the paid Sovereign control surface.

## End-To-End Logic Trace

1. **Entry channel**
   - Web: `POST /api/v1/onboarding/start`
   - Telegram: `POST /api/v1/webhooks/telegram`
   - Discord: `POST /api/v1/webhooks/discord`

2. **Public onboarding**
   - `python/arclink_hosted_api.py` routes to `arclink_api_auth.py`.
   - `python/arclink_public_bots.py`, `arclink_telegram.py`, and
     `arclink_discord.py` keep the shared bot experience consistent.
   - Users do not bring their own bot token for the first deployment. ArcLink's
     public bot collects the minimum answers and opens checkout.

3. **Billing gate**
   - `open_public_onboarding_checkout_api()` creates the Stripe Checkout
     session.
   - `POST /api/v1/webhooks/stripe` verifies the Stripe signature and calls
     `process_stripe_webhook()`.
   - Paid entitlement advances the deployment from `entitlement_required` to
     `provisioning_ready`.

4. **Fleet placement**
   - `python/arclink_fleet.py` records worker hosts, observed load, capacity
     slots, status, region, and tags.
   - Placement chooses an active host with the most headroom and records one
     active placement per deployment.

5. **Provisioning intent**
   - `python/arclink_provisioning.py` renders the per-user pod intent:
     dashboard, Hermes gateway/dashboard, QMD, vault watch, memory synth,
     Nextcloud, code-server, notification delivery, health watch, managed
     context install, DNS records, Traefik labels, and secret references.
   - It rejects plaintext secret material. Secrets must be references or
     materialized files.

6. **Ingress**
   - `python/arclink_ingress.py` computes the Cloudflare DNS records and
     Traefik labels for:
     - `u-<prefix>.<base-domain>`
     - `files-<prefix>.<base-domain>`
     - `code-<prefix>.<base-domain>`
     - `hermes-<prefix>.<base-domain>`

7. **Execution and health**
   - `python/arclink_executor.py` is the executor boundary for Docker Compose,
     Cloudflare DNS/access, Chutes key lifecycle, Stripe actions, and rollback.
   - `python/arclink_action_worker.py` consumes queued admin actions.
   - `control-api` exposes admin health, DNS drift, reconciliation, actions,
     payments, bots, security, and scale-operation views.

8. **Handoff**
   - The user dashboard reads `/api/v1/user/dashboard`,
     `/api/v1/user/billing`, and `/api/v1/user/provisioning`.
   - The admin dashboard reads `/api/v1/admin/*`.
   - When the pod is healthy, ArcLink returns the user's dashboard/files/code/
     Hermes URLs and keeps the deployment visible in admin operations.

## Required Live Credentials

The control node can boot without these, but live E2E remains gated until they
are present in `arclink-priv/config/docker.env`:

- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `ARCLINK_DEFAULT_PRICE_ID`
- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ZONE_ID`
- `CHUTES_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_BOT_USERNAME`
- `DISCORD_BOT_TOKEN`
- `DISCORD_APP_ID`
- `DISCORD_PUBLIC_KEY`

## Current Boundary

The control node now starts the hosted API and web control center from
`deploy.sh control`. The remaining live-provider work is not a UI/menu problem:
it is the hardened worker-host executor path that turns `provisioning_ready`
deployments into applied remote Docker Compose stacks with Cloudflare records and
post-apply health proof. That path must stay secret-safe and idempotent.
