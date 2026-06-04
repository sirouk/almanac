# ArcLink Sovereign Control Node

The Sovereign Control Node is the paid self-serve ArcLink control plane. It is
the path for a dedicated control host: users arrive through the website,
Telegram, or Discord, answer onboarding questions, complete Stripe checkout,
and receive a separate ArcLink pod deployed onto the fleet.

This is the concise shipped-state trace. Use
`sovereign-control-node-symphony.md` for the full dream/evidence score and
`control-node-production-runbook.md` for operator procedure.

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
- `control-llm-router`: the dedicated ASGI service for OpenAI-compatible
  ArcPod inference through ArcLink. Compose and ArcPod provisioning default to
  router mode locally; live Chutes proof remains operator-gated before claiming
  real upstream provider proof.
- `arclink-mcp`, `qmd-mcp`, `notion-webhook`, job loops, Redis/Postgres, and
  Nextcloud as the local control-node substrate.

The app runtime stays Dockerized in this mode. Host-level work is limited to
bootstrap and ingress duties such as Docker Compose, optional Tailscale
Funnel/Serve publication, and SSH key handoff for fleet workers.

The inherited public Shared Host and Shared Host Docker modes are retired.
Do not use `./deploy.sh docker ...` as an operator-facing install lane. The
Control Node still uses Docker Compose internally, and ArcPods remain Docker
deployments across registered fleet workers.

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
   - `python/arclink_provisioning.py` renders the per-ArcPod intent:
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
   - In `domain` mode, `python/arclink_ingress.py` provisions Cloudflare DNS
     records and Traefik routers for **only two** host roles
     (`ARCLINK_HOST_ROLES = ("dashboard", "hermes")` in `arclink_ingress.py`):
     - `u-<prefix>.<base-domain>` (the `dashboard` role)
     - `hermes-<prefix>.<base-domain>` (the `hermes` role)
   - `arclink_hostnames` (in `python/arclink_adapters.py`) still computes
     `files-<prefix>` and `code-<prefix>` hostnames, but Files and Code are
     **dashboard plugin routes served under the `u-` dashboard**, not standalone
     subdomains: `desired_arclink_dns_records` filters to `ARCLINK_HOST_ROLES`,
     so they receive **no DNS record and no Traefik router**. (Per-Captain
     subdomains for Files/Code would require wildcard DNS that is not provisioned
     today.) Cross-reference `docs/arclink/ingress-plan.md` for the authoritative
     ingress host table.
   - In `tailscale` mode, Cloudflare DNS is skipped. The control host is
     published with Tailscale Funnel on `ARCLINK_TAILSCALE_HTTPS_PORT`, default
     `443`. Control-plane callbacks stay path-based under the worker Tailscale
     FQDN, while published per-pod Hermes Dashboard URLs use a stable tailnet HTTPS
     port such as `https://worker.tailnet.ts.net:8443/` so Hermes can run at
     the root path. Tailscale mode is path-based; use `domain` ingress with
     wildcard DNS when ArcPods need per-Captain subdomains.
   - Each pod reserves a per-deployment Notion callback URL and webhook secret
     reference. Domain mode renders
     `https://u-<prefix>.<base-domain>/notion/webhook`. Tailscale path mode
     renders `https://<worker-tailnet-name>/u/<prefix>/notion/webhook`.

7. **Execution and health**
   - `python/arclink_sovereign_worker.py` is the control-node worker
     (`control-provisioner`, `process_sovereign_batch`). It:
     claims paid deployments, registers an optional starter local host, places
     the deployment onto a fleet host, renders the pod intent, applies
     Cloudflare DNS only in domain mode, applies Docker Compose locally or over
     SSH, records service health, and writes audited timeline events.
   - **Operator-arcpod exclusion.** The apply selection explicitly skips
     deployments whose metadata carries `"operator_agent"` (the Operator's own
     single in-stack Hermes agent, see "Operator Control" below). Those are
     provisioned outside the fleet batch, never placed on a fleet host.
   - **Mid-apply entitlement re-check.** Each apply step re-validates through
     `_reload_apply_ready_deployment`, which re-asserts that the deployment is
     still `provisioning`, the owning user still exists, and
     `arclink_deployment_can_provision` still permits it. If the entitlement is
     revoked mid-apply, the worker fails closed rather than finishing a pod the
     Captain no longer owns.
   - **Tailnet port allocator (tailscale path mode only).**
     `_ensure_tailnet_service_ports` allocates a per-deployment `hermes` tailnet
     HTTPS port from `ARCLINK_TAILNET_SERVICE_PORT_BASE` (default `8443`),
     skipping ports already held by other live deployments, and records/releases
     them in deployment metadata. Domain mode does not use this allocator.
   - **Handoff health gate.** When
     `ARCLINK_SOVEREIGN_HANDOFF_REQUIRES_HEALTHY_SERVICES` is set (default `1`),
     the worker maps `docker compose ps` state to
     `healthy|unhealthy|starting|failed|missing` and refuses to emit
     `user_handoff_ready` if any service is `failed`, `unhealthy`, or `missing` —
     the apply fails instead of handing a Captain a broken pod. The `fake`
     executor adapter marks every service `healthy`, so this gate is exercised
     only against the `local`/`ssh` adapters (proof-gated behind
     `PG-FLEET`/`PG-PROVISION`).
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

8. **LLM routing**
   - `python/arclink_llm_router.py` is the Control Node provider boundary for
     ArcPod inference. The `control-llm-router` ASGI service is wired and each
     ArcPod's default base URL points at it. Hermes sees an OpenAI-compatible
     `/v1` provider; the router verifies a per-deployment ArcLink key, enforces
     Chutes billing and budget policy, relays with the central server-side
     Chutes credential, and records sanitized usage. The live Chutes inference
     relay itself is proof-gated (GAP-031, PG-PROVIDER) — the wiring is real, the
     live upstream transaction is not yet proven.
   - The current source-level router does not store raw prompts or completions.
     Raw router keys are one-time materialization secrets; only hashes and
     metadata are stored in the control database.
   - Control Node Compose and ArcPod provisioning are router-first. Direct
     Chutes remains only behind `ARCLINK_ALLOW_DIRECT_CHUTES_IN_ARCPODS=1`, and
     live router proof is not claimed without the explicit live-proof gate. See
     `docs/arclink/llm-router.md`.

9. **Handoff**
   - The user dashboard reads `/api/v1/user/dashboard`,
     `/api/v1/user/billing`, `/api/v1/user/provisioning`, and
     `/api/v1/user/comms`.
   - The admin dashboard reads `/api/v1/admin/*`, including CIDR-gated
     `/api/v1/admin/comms` metadata for Pod Comms without Captain narratives.
   - When the pod is healthy, ArcLink returns the user's dashboard/files/code/
     Hermes URLs and keeps the deployment visible in admin operations.

## Operator Control

The Operator governs the fleet from the admin dashboard, the chat-native
**Operator Raven** console (`python/arclink_operator_raven.py`), and a single
in-stack **operator Hermes agent** (`python/arclink_operator_agent.py`).

- **Operator Raven queues real, audited, identity-gated actions** — it is not
  read-only or dry-run-only. Mutating commands (`pod_repair`, `rollout`,
  `host_upgrade`, detector-token `pin_upgrade`, `upgrade_sweep`,
  `fleet_drain`, `fleet_resume`) use a four-mode contract: `--dry-run`
  previews and changes nothing; no `--dry-run` with no operator actor fails
  closed; no `--dry-run` with an operator actor but no second confirmation
  fails closed; no `--dry-run` with actor plus `confirm` or the configured
  operator approval code queues a real intent or applies a modeled local
  fleet-state mutation. Approval codes
  (`ARCLINK_OPERATOR_TELEGRAM_APPROVAL_CODE` or
  `ARCLINK_OPERATOR_APPROVAL_CODE`) are verified with a constant-time compare.
  Read commands (`status`, `agents`, `fleet_list`, `worker_probe` (dry-run
  only), `user_lookup`, `academy_status`, `academy_roster`, `upgrade_check`,
  `upgrade_policy`, `action_status`) never mutate. `/upgrade_policy
  [component]` explains source-owned upgrade posture only. `/pin_upgrade
  <component>` refuses unless an active detector payload with concrete target
  pins exists, and `/upgrade_sweep` queues pending stateless detector payloads
  while holding Postgres/Redis/Nextcloud behind `--include-stateful`. Raven only
  *queues* live intents; live mutation stays gated by `ARCLINK_EXECUTOR_ADAPTER`
  and the per-action proof gates (e.g. PG-PROVISION, PG-INGRESS, PG-UPGRADE,
  PG-HERMES). Fleet drain/resume is placement-only control-state mutation: it
  does not SSH into workers, stop services, change firewalls, or touch port 22
  from chat. This corrects the stale "read-only Operator Raven" framing
  (GAP-029, partially closed).
- **Two queues.** Operator Raven writes admin/operator intents to
  `arclink_action_intents` (drained by `python/arclink_action_worker.py`) and to
  `operator_actions` (drained by the enrollment-provisioner root maintenance
  loop). `action_status` reads recent rows from both.
- **One operator Hermes agent.** The Operator gets exactly ONE in-stack Hermes
  identity, reserved by `ensure_operator_agent_deployment` with the
  `control-stack` runtime and a `"operator_agent"` metadata marker. The
  one-agent invariant is enforced (`assert_single_operator_agent` refuses a
  second). `enqueue_operator_agent_turn` bridges a free-form operator chat
  message to that agent through the notification worker. Because of the
  `"operator_agent"` marker, the sovereign worker excludes this deployment from
  fleet apply (see "Execution and health" above).
- ArcPod rollout (`rollout` / `arcpod_update_rollout`) is `wired`/queueable in
  `ARCLINK_ADMIN_ACTION_SUPPORT`; the planner, local materializer, and
  record-only batch executor are implemented and tested locally, but real
  per-Pod refresh/apply with live multi-Pod health remains proof-gated
  (GAP-032, PG-UPGRADE/PG-HERMES). See
  `docs/arclink/operations-runbook.md` for the operator action-readiness rows
  and the authoritative GAP-019 trust-boundary entries, and `GAPS.md` for the
  gap taxonomy.

## Pod Comms

Control Node Comms uses `python/arclink_pod_comms.py`. Same-Captain Pods may
message by default; cross-Captain Pod Comms requires an accepted, unexpired
`pod_comms` share grant. Send + store + list over `arclink_pod_messages` are
implemented and tested locally; messages are rate-limited per sender deployment
and audited as `pod_message_sent`. Attachments are Drive/Code share-grant
projection references only, not raw files. Cross-Pod **delivery** and operator
redaction (`mark_pod_message_delivered` / `redact_pod_message`,
`pod_message_delivered` / `pod_message_redacted` audit events) are defined but
currently unwired (no production caller), so do not assume live delivery
without a live gateway runtime (PG-BOTS/PG-HERMES).

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
- `CLOUDFLARE_API_TOKEN_REF` (preferred) or `CLOUDFLARE_API_TOKEN`, plus
  `CLOUDFLARE_ZONE_ID`, for `domain` ingress mode.
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
- `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED=accepted`, written only after the
  operator accepts the `GAP-019` trusted-host prompt for this private Control
  Node host. This gates the Docker/root-adjacent broker/helper services used by
  local provisioning, upgrade, gateway, migration-capture, and agent process
  actions so a new install fails early with a plain decision instead of later
  unhealthy broker containers.
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
