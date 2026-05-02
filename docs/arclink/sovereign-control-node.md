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
- `control-provisioner`: the disabled-by-default Sovereign worker loop that
  claims paid `provisioning_ready` deployments and applies them to fleet hosts
  when `ARCLINK_CONTROL_PROVISIONER_ENABLED=1`.
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
   - `python/arclink_sovereign_worker.py` is the control-node worker. It:
     claims paid deployments, registers an optional starter local host, places
     the deployment onto a fleet host, renders the pod intent, applies
     Cloudflare DNS, applies Docker Compose locally or over SSH, records service
     health, and writes audited timeline events.
   - `python/arclink_executor.py` is the executor boundary for Docker Compose,
     Cloudflare DNS/access, Chutes key lifecycle, Stripe actions, and rollback.
     In live mode it materializes compose/env/secret files under the deployment
     root, supports local and SSH Docker Compose runners, and uses the
     Cloudflare API for DNS upserts.
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
- `ARCLINK_CONTROL_PROVISIONER_ENABLED=1`
- `ARCLINK_EXECUTOR_ADAPTER=ssh` for remote fleet hosts, or `local` for a
  starter single-host deployment.
- `ARCLINK_EDGE_TARGET`, usually a load-balancer or ingress hostname that every
  per-user subdomain CNAME points at.
- For SSH fleet execution, put the worker-host SSH key material and
  `known_hosts` entries under `arclink-priv/secrets/ssh/`; that directory is
  mounted read-only into `control-provisioner`.

## Current Boundary

The control node starts the hosted API, web control center, and provisioner loop
from `deploy.sh control`. The worker-host path now exists for local and SSH
Docker Compose execution, with Cloudflare DNS upserts and secret-file
materialization. Live proof is still gated by real provider credentials,
registered fleet capacity, SSH reachability to worker hosts, and service health
checks against the deployed pods.
