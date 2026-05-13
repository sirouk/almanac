# ArcLink Sovereign Control Node

The Sovereign Control Node is the paid self-serve ArcLink control plane. It is
the path for a dedicated control host: users arrive through the website,
Telegram, or Discord, answer onboarding questions, complete Stripe checkout,
and receive a separate ArcLink pod deployed onto the fleet.

## Deploy Path

Use:

```bash
./deploy.sh control install
./deploy.sh control ports
./deploy.sh control health
```

The control path delegates to Docker Compose, but it does not mean
"Shared Host Docker." It starts the hosted product boundary:

- `control-web`: the Next.js ArcLink website, onboarding, user dashboard, and
  admin dashboard.
- `control-api`: the hosted `/api/v1` WSGI API over ArcLink's existing Python
  contracts.
- `control-provisioner`: the Sovereign worker loop that claims paid
  `provisioning_ready` deployments and applies them to fleet hosts. It is
  enabled by default in Control Node mode; live mutation still requires a real
  `ARCLINK_EXECUTOR_ADAPTER` and provider credentials.
- `control-action-worker`: the admin-action consumer for restart, DNS/key,
  Stripe, and entitlement actions queued from the admin dashboard.
- `arclink-mcp`, `qmd-mcp`, `notion-webhook`, job loops, Redis/Postgres, and
  Nextcloud as the local control-node substrate.

The app runtime stays Dockerized in this mode. Host-level work is limited to
bootstrap and ingress duties such as Docker Compose, optional Tailscale
Funnel/Serve publication, and SSH key handoff for fleet workers.

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

   Telegram must be registered with `callback_query` allowed updates so Raven's
   inline buttons can deliver taps back to the control API. The deploy flow
   writes `TELEGRAM_WEBHOOK_URL` to the public Telegram endpoint and public bot
   registration refreshes both commands and webhook allowed updates. Production
   Telegram webhooks must also use `TELEGRAM_WEBHOOK_SECRET`; the hosted API
   rejects webhook updates when the secret-token header is absent or wrong.

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
     active placement per deployment. Placement and provider mutations are
     guarded by durable idempotency records so retries replay matching work
     instead of double-applying side effects.

5. **Provisioning intent**
   - `python/arclink_provisioning.py` renders the per-user pod intent:
     dashboard, Hermes gateway/dashboard, QMD, vault watch, memory synth,
     Nextcloud, dashboard-native Drive/Code/Terminal plugins, notification delivery, health watch, managed
     context install, DNS records, Traefik labels, and secret references.
   - It rejects plaintext secret material. Secrets must be references or
     materialized files.

6. **Ingress**
   - `./deploy.sh control install` asks for `domain` or `tailscale`.
   - New deployments reserve a random readable prefix such as
     `orbital-beacon-7xq2`. The pool uses generic hard-SF/frontier language,
     not show-specific proper nouns, and the control DB enforces
     case-insensitive uniqueness.
   - In `domain` mode, `python/arclink_ingress.py` computes Cloudflare DNS
     records and Traefik labels for:
     - `u-<prefix>.<base-domain>`
     - `files-<prefix>.<base-domain>`
     - `code-<prefix>.<base-domain>`
     - `hermes-<prefix>.<base-domain>`
   - In `tailscale` mode, Cloudflare DNS is skipped. The control host is
     published with Tailscale Funnel on `ARCLINK_TAILSCALE_HTTPS_PORT`, default
     `443`. Control-plane callbacks stay path-based under the worker Tailscale
     FQDN, while published per-pod Helm/Hermes URLs use a stable tailnet HTTPS
     port such as `https://worker.tailnet.ts.net:8443/` so Hermes can run at
     the root path. `subdomain` can be selected only for environments that
     really provide resolvable/certified sub-subdomains under the Tailscale
     name.
   - Each pod reserves a per-deployment Notion callback URL and webhook secret
     reference. Domain mode renders
     `https://u-<prefix>.<base-domain>/notion/webhook`. Tailscale path mode
     renders `https://<worker-tailnet-name>/u/<prefix>/notion/webhook`.

7. **Execution and health**
   - `python/arclink_sovereign_worker.py` is the control-node worker. It:
     claims paid deployments, registers an optional starter local host, places
     the deployment onto a fleet host, renders the pod intent, applies
     Cloudflare DNS only in domain mode, applies Docker Compose locally or over
     SSH, records service health, and writes audited timeline events.
   - `python/arclink_executor.py` is the executor boundary for Docker Compose,
     domain/Tailscale ingress, Chutes key lifecycle, Stripe actions, and rollback.
     In live mode it materializes compose/env/secret files under the deployment
     root, supports local and SSH Docker Compose runners, uses the Cloudflare
     API for domain-mode DNS upserts, and skips DNS in Tailscale mode.
   - `python/arclink_action_worker.py` consumes queued admin actions.
   - `control-api` exposes admin health, DNS drift, reconciliation, actions,
     payments, bots, security, and scale-operation views.

   Cancellation is handled as an explicit teardown lifecycle. The worker stops
   Compose, removes managed DNS where applicable, revokes provider artifacts
   when configured, releases placement and port reservations, cleans
   materialized secret files, and records audit events before marking the
   deployment `torn_down`. Compose volumes are preserved unless teardown
   metadata explicitly requests removal.

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
- `ARCLINK_FOUNDERS_PRICE_ID`
- `ARCLINK_SOVEREIGN_PRICE_ID`
- `ARCLINK_SCALE_PRICE_ID`
- `ARCLINK_FIRST_AGENT_PRICE_ID`
- `ARCLINK_SOVEREIGN_AGENT_EXPANSION_PRICE_ID`
- `ARCLINK_SCALE_AGENT_EXPANSION_PRICE_ID`
- `ARCLINK_ADDITIONAL_AGENT_PRICE_ID`
- `ARCLINK_FOUNDERS_MONTHLY_CENTS=14900`
- `ARCLINK_SOVEREIGN_MONTHLY_CENTS=19900`
- `ARCLINK_SCALE_MONTHLY_CENTS=27500`
- `ARCLINK_SOVEREIGN_AGENT_EXPANSION_MONTHLY_CENTS=9900`
- `ARCLINK_SCALE_AGENT_EXPANSION_MONTHLY_CENTS=7900`
- `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ZONE_ID` for `domain` ingress mode.
- `CHUTES_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_BOT_USERNAME`
- `TELEGRAM_WEBHOOK_SECRET`
- `DISCORD_BOT_TOKEN`
- `DISCORD_APP_ID`
- `DISCORD_PUBLIC_KEY`
- `ARCLINK_SESSION_HASH_PEPPER` with
  `ARCLINK_SESSION_HASH_PEPPER_REQUIRED=1` for production session and CSRF
  token hashes.
- `ARCLINK_BACKEND_ALLOWED_CIDRS`, narrowed to the reverse-proxy, Docker
  private network, or tailnet source ranges that should reach admin/control
  API routes.
- `ARCLINK_CONTROL_PROVISIONER_ENABLED=1`
- `ARCLINK_CONTROL_DEPLOYMENT_STYLE=single-machine`, `hetzner`, or
  `akamai-linode`; `deploy.sh control install` asks this before ingress so the
  operator records whether the control node is a starter single-host setup or
  a remote worker-fleet setup. Single-machine defaults toward local execution
  and starter host registration; Hetzner and Akamai Linode default toward SSH
  worker placement.
- `ARCLINK_EXECUTOR_ADAPTER=ssh` for remote fleet hosts, or `local` for a
  starter single-host deployment.
- `ARCLINK_INGRESS_MODE=domain` or `tailscale`.
- `ARCLINK_EDGE_TARGET`, usually a load-balancer or ingress hostname that every
  per-user subdomain CNAME points at in `domain` mode.
- `ARCLINK_TAILSCALE_DNS_NAME` for `tailscale` mode.
- For SSH fleet execution, put the worker-host SSH key material and
  `known_hosts` entries under `arclink-priv/secrets/ssh/`. `deploy.sh control
  install` generates/reuses `id_ed25519`, prints `id_ed25519.pub`, and asks the
  operator to confirm it was added to the starter/fleet node. When the current
  machine is registered as the starter worker, deploy can create/repair the
  `arclink` Unix user, install the key into `authorized_keys`, prepare the
  deployment state root, add Docker group access if available, and smoke-test
  `ssh -i ... arclink@localhost true`. The directory is mounted into
  `control-provisioner` through the container-visible
  `/home/arclink/arclink/arclink-priv/secrets/ssh/` path so SSH can persist
  `known_hosts`.

## Current Boundary

The control node starts the hosted API, web control center, and provisioner loop
from `deploy.sh control`. The worker-host path now exists for local and SSH
Docker Compose execution, with Cloudflare DNS upserts in domain mode,
Tailscale-safe DNS skipping in Tailscale mode, per-deployment Notion callback
intent, secret-file materialization and cleanup, durable operation
idempotency, and audited teardown. Live proof is still gated by real provider
credentials, registered fleet capacity, SSH reachability to worker hosts,
ingress publication, customer Notion connection proof, and service health
checks against the deployed pods.
