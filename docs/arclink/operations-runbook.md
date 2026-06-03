# ArcLink Operations Runbook

Concise operational reference for the landed ArcLink boundaries. All boundaries
default to fake adapters; live behavior requires explicit env vars.

## 1. Hosted API

**Module:** `python/arclink_hosted_api.py` (WSGI)

**Start (dev):**
```bash
python3 python/arclink_hosted_api.py   # starts on 127.0.0.1:8900
```

**Env vars:**
| Var | Default | Purpose |
|-----|---------|---------|
| `ARCLINK_CORS_ORIGIN` | (none) | Allowed origin for CORS |
| `ARCLINK_COOKIE_DOMAIN` | (none) | Cookie domain attribute |
| `ARCLINK_COOKIE_SECURE` | `1` | Set 0 for HTTP-only dev |
| `ARCLINK_LOG_LEVEL` | `INFO` | Structured log verbosity |
| `ARCLINK_DEFAULT_PRICE_ID` | `price_arclink_founders` | Limited 100 Founders Stripe price |
| `ARCLINK_FOUNDERS_PRICE_ID` | `price_arclink_founders` | Limited 100 Founders Stripe price ($149/month target) |
| `ARCLINK_SOVEREIGN_PRICE_ID` | `price_arclink_sovereign` | Sovereign Stripe price ($199/month target) |
| `ARCLINK_SCALE_PRICE_ID` | `price_arclink_scale` | Scale Stripe price ($275/month target) |
| `ARCLINK_FIRST_AGENT_PRICE_ID` | `price_arclink_founders` | Legacy first-agent alias for Limited 100 Founders |
| `ARCLINK_SOVEREIGN_AGENT_EXPANSION_PRICE_ID` | `price_arclink_sovereign_agent_expansion` | Sovereign Agentic Expansion Stripe price ($99/month target) |
| `ARCLINK_SCALE_AGENT_EXPANSION_PRICE_ID` | `price_arclink_scale_agent_expansion` | Scale Agentic Expansion Stripe price ($79/month target) |
| `ARCLINK_ADDITIONAL_AGENT_PRICE_ID` | `price_arclink_sovereign_agent_expansion` | Legacy alias for Sovereign Agentic Expansion |
| `ARCLINK_FOUNDERS_MONTHLY_CENTS` | `14900` | Limited 100 Founders public price label |
| `ARCLINK_SOVEREIGN_MONTHLY_CENTS` | `19900` | Sovereign public price label |
| `ARCLINK_SCALE_MONTHLY_CENTS` | `27500` | Scale public price label |
| `ARCLINK_FIRST_AGENT_MONTHLY_CENTS` | `14900` | Legacy first-agent monthly price alias |
| `ARCLINK_SOVEREIGN_AGENT_EXPANSION_MONTHLY_CENTS` | `9900` | Sovereign Agentic Expansion public price label |
| `ARCLINK_SCALE_AGENT_EXPANSION_MONTHLY_CENTS` | `7900` | Scale Agentic Expansion public price label |
| `ARCLINK_ADDITIONAL_AGENT_MONTHLY_CENTS` | `9900` | Legacy additional-agent monthly price alias |

**Health check:**
```bash
curl -s http://localhost:8900/api/v1/health | python3 -m json.tool
```
Returns `200` when healthy, `503 Service Unavailable` when degraded (DB
unreachable or background service unhealthy).

**Rate limits:** Per-scope sliding window (admin login: 5/15min, user login:
10/15min, onboarding: 5/15min per channel). 429 responses include
`Retry-After`, `X-RateLimit-Limit`, `X-RateLimit-Remaining`,
`X-RateLimit-Reset` headers.

**Admin password reset:** Admin login requires email plus password. To set or
rotate an operator password without printing it into logs, run:

```bash
./bin/arclink-ctl admin set-password admin@example.com --generate --write-password-file /path/to/private-admin-password.txt
```

The generated file is written with `0600` permissions. Use `--password-file`
for an existing private password file.

**Admin ownership:** ArcLink enforces one active `owner` admin. Additional
admin rows may exist only as subordinate roles such as `admin`, `ops`,
`support`, or `read_only`; creating a second active owner is rejected. Treat the
owner account as the operator of record for production decisions, live-proof
authorization, and destructive maintenance. Do not create a second owner for
coverage; rotate or recover the owner account, then add subordinate admin roles
only for delegated operations.

**User dashboard credentials:** Sovereign user login and the user's Hermes
dashboards use one user-scoped dashboard credential by default. New pods seed
the same username, normally the user's email, and the same user-scoped dashboard
password through Docker secrets, then store only the password hash in the
control DB. Existing pod passwords are reconciled without printing secrets
during Docker reconcile via:

```bash
./bin/arclink-docker.sh reconcile
```

Private Curator completion sends the generated dashboard password to the user
completion bundle, then scrubs that message after acknowledgement. Operator
notifications redact that password by default; only set
`ARCLINK_OPERATOR_NOTIFICATION_INCLUDE_CREDENTIALS=1` for an explicitly
credential-bearing private operator channel.

Telegram operator approvals can require a typed second factor by setting
`ARCLINK_OPERATOR_TELEGRAM_APPROVAL_CODE` or the shared
`ARCLINK_OPERATOR_APPROVAL_CODE`. When set, `/approve`, `/deny`, `/upgrade`,
and `/retry_contact` commands must include the code. Upgrade notification
buttons are preview-only; live upgrade and pinned-component mutation requires
the typed Operator Raven command with `confirm` or the configured code.

Every Operator Raven mutating command requires a verified operator channel
**and** an explicit second confirmation. `python/arclink_operator_raven.py`
defines `MUTATING_COMMANDS = {pod_repair, rollout, host_upgrade, pin_upgrade}`.
Operators should run `--dry-run` first, then append `confirm` when no approval
code is configured, for example `/upgrade confirm`. If
`ARCLINK_OPERATOR_TELEGRAM_APPROVAL_CODE` or `ARCLINK_OPERATOR_APPROVAL_CODE` is
configured, the Telegram and Discord adapters verify that trailing token with
constant-time `hmac.compare_digest`, strip it, and pass the shared confirmation
token into Operator Raven. A missing/wrong code fails closed with "Operator code
required for this action"; a missing `confirm`/code from a verified actor fails
closed and queues nothing. Read-only Operator Raven commands (`status`,
`agents`, `fleet_list`, `worker_probe`, `user_lookup`, `action_status`,
`upgrade_check`, `academy_status`, `academy_roster`) never require confirmation
and never mutate.

Discord Curator operator actions are gated by the configured operator channel;
when an operator approval code is configured, mutating Discord commands must
also include that code, same as Telegram. Keep the Discord operator channel
tightly permissioned.

Hosted user sessions expose credential handoff state through
`GET /api/v1/user/credentials` and acknowledge storage through
`POST /api/v1/user/credentials/acknowledge`. These responses use masked secret
references only; acknowledgement hides the handoff from future user API reads
and records audit/event rows.

The reconciler invokes `bin/sync-dashboard-user-passwords.py` inside the
provisioner context so it can read deployment state roots and update hashes.
Deployments rendered before the managed-lifecycle guard existed should be
reprovisioned or re-rendered before production use so
`ARCLINK_DASHBOARD_MANAGED_LIFECYCLE_CONTROLS=1` is present in the pod proxy
environment.

**Pod migration / reprovision:** The `reprovision` admin action is wired to the
Pod migration orchestrator. Initial rollout is Operator-only:
`ARCLINK_CAPTAIN_MIGRATION_ENABLED=0` stays the default and there is no
Captain-facing migration route in this wave.

Queue a redeploy-in-place by targeting the deployment and setting
`metadata.target_machine_id=current`. Queue a host move by setting
`metadata.target_machine_id` to a fleet host id or an inventory machine id with
`machine_host_link` populated. The migration captures source state into
`<state_root_base>/.migrations/<migration_id>/`, records file digests in
`arclink_pod_migrations.capture_manifest_json`, materializes the target state
root, applies Compose through the configured executor, verifies service health,
and updates source/target placement rows.

Rollback is automatic on failed verification: the source placement is restored
to `active`, the pending target placement is left `removed`, target Compose is
torn down for host moves, source Compose is restarted, the migration row is
marked `rolled_back`, and `pod_migration_rolled_back` is emitted. Idempotent
replay uses `arclink:migration:<migration_id>`; the same migration id with a
different target is rejected.

Successful migration captures are retained for
`ARCLINK_MIGRATION_GC_DAYS` days, default `7`. The GC helper
`garbage_collect_pod_migrations(conn, ...)` marks expired successful migrations
with `source_garbage_collected_at` after removing their staging artifacts; the
deployed control action-worker loop invokes that helper after each batch.

**Admin action readiness:** The admin dashboard renders the source-owned
support matrix from `python/arclink_dashboard.py`. A row is queueable only when
the action has worker dispatch and executor probes are ready; otherwise the row
stays disabled with a fail-closed reason. The local matrix currently maps:

| Action | Operation kind | Required adapter | Proof boundary |
| --- | --- | --- | --- |
| `restart` | `docker_compose_lifecycle` | `ARCLINK_EXECUTOR_ADAPTER=fake|local|ssh` | `PG-PROVISION` |
| `reprovision` | `pod_migration` | `ARCLINK_EXECUTOR_ADAPTER=fake|local|ssh` | `PG-PROVISION` |
| `dns_repair` | `cloudflare_dns_apply` | Executor plus live DNS credentials for mutation | `PG-INGRESS` |
| `rotate_chutes_key` | `chutes_key_apply` | Executor plus Chutes key client for mutation | `PG-PROVIDER` |
| `refund` / `cancel` | `stripe_action_apply` | Executor plus Stripe action client for mutation | `PG-STRIPE` |
| `comp` | `control_db_comp` | Action worker with control DB access | `LOCAL-CONTROL-DB` |
| `rollout` | `arcpod_update_rollout` | Action worker with control DB access; explicit `fake`/`local` record-only execution contract for bounded batch execution | `PG-UPGRADE/PG-HERMES` |

The `rollout` row is `worker_support="wired"` in
`python/arclink_dashboard.py` (`ARCLINK_ADMIN_ACTION_SUPPORT`) and queueable
today: it stages audited local ArcPod-update rollout rows from a ready dry-run
preflight plan and can record one bounded `fake`/`local` batch. Live per-Pod
refresh/apply and multi-Pod health/smoke proof remain gated behind
`PG-UPGRADE/PG-HERMES` (`GAP-032`). Earlier runbook wording that listed
`rollout` as "pending/disabled" is stale.

This matrix is local readiness, not live evidence. Fake adapter results prove
contract behavior only; local/SSH adapter results count as live mutation proof
only when the recorded executor result is live, succeeded, and tied to the
matching proof gate.

**Linked resources:** Cross-user Drive/Code sharing is modeled as share grants
whose accepted folders are writable from the recipient's Linked root. A user
session creates a pending grant for a recipient, Raven
queues an owner approval notification when the owner has a linked Telegram or
Discord channel, and the owner can approve or deny it with button callbacks.
Active Telegram buttons use `/raven approve {grant_id}` and `/raven deny
{grant_id}` so they cannot collide with the active agent's slash namespace;
the backward-compatible `/share-approve {grant_id}` and `/share-deny
{grant_id}` forms remain owner-scoped. The recipient accepts an approved grant with their own user
session, and accepted resources are listed at
`GET /api/v1/user/linked-resources`. Drive and Code expose a `Linked` root when
`ARCLINK_LINKED_RESOURCES_ROOT` or the plugin fallback projection exists.
Accepted grants create living linked-resource projections backed by a manifest,
owner revoke removes the projection and manifest entry, and Drive/Code allow
recipient writes inside accepted shared folders plus copy/duplicate into the
recipient's own Vault or Workspace without allowing reshare from the `Linked`
source. Linked git mutations remain blocked. Direct right-click browser
share-link generation remains disabled. Drive and Code can expose a brokered
`Share` action only when `ARCLINK_SHARE_REQUEST_BROKER_URL` or the
plugin-specific broker URL is configured together with
`ARCLINK_SHARE_REQUEST_BROKER_TOKEN_FILE` or the matching plugin-specific token
file and an owner deployment identity. Control-node provisioning points the
plugins at the hosted `/api/v1/user/share-grants/broker` route, mounts the
broker token as an ArcPod runtime secret, and stores only the token hash in the
deployment metadata. The local plugin route rejects `Linked` roots and sensitive
paths before dispatching to that broker, sends the token only as the
`X-ArcLink-Share-Request-Broker-Token` broker header, and the hosted broker
derives the owner from the token-bound `owner_deployment_id`.
Production workspace/browser proof, live bot delivery, and any approved
Nextcloud-backed adapter remain credential- or policy-gated.

**Ephemeral share nonces (right-click Share):** The Drive/Code right-click
`Share` action sends `share_mode="claim_nonce"` to the broker, which mints a
single-use, 12-hour nonce (`asn_…`) in `arclink_share_claim_nonces` instead of
naming a recipient up front. Minting *is* the owner's approval. The plugin shows
a copyable block — `A share request is available for review by Raven:` followed
by `/arclink_share_accept <nonce>` — and tells the user it expires in 12 hours.
The owner hands that to anyone on ArcLink; their Raven (or `POST
/api/v1/user/share-grants/claim`) consumes the nonce and materializes a
Linked resource. Only the HMAC hash of the nonce is stored; expiry is
enforced on read (status flips to `expired`) and swept in batch by
`expire_revealable_user_material`; a claimed/expired/unknown nonce fails with a
single generic "invalid or has expired" message so nonce state is not leaked. The
new Raven command `/arclink_share_accept <nonce>` is dispatched in
`python/arclink_public_bots.py` alongside the existing `/share-accept`
button-callback path. An owner can **revoke** a minted-but-unclaimed nonce inside
the 12h window via `POST /api/v1/user/share-grants/nonce/revoke` (CSRF), which
flips it to `revoked` so it can no longer be claimed. Nonce hashing uses the
session pepper, so rotating `ARCLINK_SESSION_HASH_PEPPER` invalidates any
in-flight nonces (acceptable given the 12h TTL).

**Fleet shared folder:** Every agent across a Captain's fleet can use one
read-write shared folder, synced across machines, backed by git
(`python/arclink_fleet_share.py`). The canonical content lives in a
Captain-scoped *bare hub* repo (`ARCLINK_FLEET_SHARE_HUB_URL` with `{user}`, or
per-Captain under `ARCLINK_FLEET_SHARE_HUB_ROOT`, default
`/arcdata/captains/{user}/fleet-shared.git`) that is independent of any single
agent, so the Captain can remove any agent — even the first — without orphaning
the folder. Each active agent gets a read-write working clone at
`ARCLINK_FLEET_SHARED_ROOT` (provisioned at `<state_root>/fleet-shared`,
mounted at `/fleet-shared`) that the Drive/Code `Fleet` root surfaces.
Sync is **two-tier**, because each agent's working copy lives on the agent's own
host/pod (not on the control node): (1) the control plane runs membership
convergence on a schedule — the `fleet-share-reconcile` compose job
(`python3 python/arclink_fleet_share.py reconcile --all`, every 120s) enrols
newly-active agents and deregisters torn-down ones (hub untouched, so removing
any agent is safe); (2) each generated agent compose includes a
`fleet-share-sync` job loop (`python3 python/arclink_fleet_share.py sync-local`,
every 120s), with `ARCLINK_FLEET_SHARE_HUB_URL` resolved for that Captain and a
local hub bind-mounted at `/fleet-share-hub.git` when the hub is a filesystem
path. That job commits local edits, `git pull --rebase`, and pushes. Concurrent
conflicting edits are surfaced as `last_sync_status='conflict'` and the local
edit is preserved (the rebase is aborted, never clobbered; git's own
`.git/index.lock` serializes concurrent git ops). A working copy whose `.git` is
corrupted is quarantined aside and re-cloned on the next sync rather than
wedging. The git transport is injectable (`SubprocessGitRunner` by default) so
the engine is unit-tested without live hosts. `run_fleet_share_cycle` (CLI
`sync`) is the co-located/single-host convenience that reconciles + syncs in one
process. **Durability boundary:** the hub is a single bare repo; host it on
durable/replicated storage (or a git host via `ARCLINK_FLEET_SHARE_HUB_URL`) —
losing the hub host loses the folder. Cross-host hub transport credentials (SSH
keys/known_hosts or HTTPS credentials) remain infra-gated when a remote git hub
is configured.

If the owner has no linked Telegram or Discord channel, share creation still
persists the grant as `pending_owner_approval`, but no Raven notification is
queued. The API response reports `owner_notification.queued=false` with a
reason of `no_public_channel` when no public channel exists, or
`unsupported_public_channel` when stored channel metadata is not a usable
Telegram or Discord target. `GET /user/share-grants` and the Captain dashboard
now expose the same durable waiting state for owners and recipients, including
dashboard approve/deny/accept actions and a local recovery hint to use the
dashboard or link a public channel. Authenticated grant participants can also
call `POST /user/share-grants/retry-notification` to retry the currently
waiting owner or recipient prompt. That retry only writes a local
`notification_outbox` row when the waiting target already has a linked Telegram
or Discord identity; it returns `queued=false` with the same recovery hint when
no linked channel exists. Operators should treat missing public-bot delivery as
a waiting state, not a delivery failure, until `PG-BOTS` proves live delivery.

**Pod Comms:** Pod-to-Pod messages are brokered by
`python/arclink_pod_comms.py` and stored in `arclink_pod_messages`. Same-Captain
Crew messages are allowed by default. Cross-Captain messages require an
accepted, unexpired `arclink_share_grants` row with `resource_kind='pod_comms'`;
pending, approved-but-unaccepted, revoked, and expired grants fail closed.
Messages rate-limit at 60 per minute per sender deployment and queue
`notification_outbox` rows to the recipient `user-agent` with
`channel_kind='pod-message'`. Attachments must be accepted share-grant
references; raw files and file bodies do not belong in the message row.
Captains read narratives at `GET /api/v1/user/comms`. Operators read metadata
only at CIDR-gated `GET /api/v1/admin/comms`.

**ArcLink Wrapped:** Captain period reports are owned by
`python/arclink_wrapped.py`. That module owns cadence validation, scoped reads,
novelty scoring, redaction, report persistence, scheduler execution, delivery
enqueue, and aggregate Operator reads. API routes, dashboard code, public bot
handlers, and notification delivery must call into that module instead of
duplicating Wrapped SQL or privacy decisions.

Wrapped generation is read-only over Captain state. It may read the Captain's
own Pods, same-Captain Comms, audit/event rows, scoped memory cards, and
caller-supplied read-only Hermes session and vault-reconciler summaries. It may
write `arclink_wrapped_reports`, `notification_outbox`, and audit/event rows
for cadence changes or failures. It must not mutate sessions, memory files,
vault content, providers, payments, deployments, bot registrations, or Hermes
core.

Cadence is limited to `daily`, `weekly`, and `monthly`; missing cadence defaults
to `daily`, and anything more frequent than daily is rejected. Captain-facing
routes are `GET /api/v1/user/wrapped` and CSRF-gated
`POST /api/v1/user/wrapped-frequency`. Raven's `/wrapped-frequency` handler
accepts `daily`, `weekly`, or `monthly` and uses the same mutation path without
requiring live command registration during local validation.

The Docker scheduler is the named `arclink-wrapped` job-loop service running
`bin/arclink-wrapped.sh`. It retries failed reports on the next eligible cycle
and queues persistent failures as Operator notifications without report
narrative. The service does not require the Docker socket. Captain delivery is
queued through `notification_outbox` with `target_kind='captain-wrapped'`;
`python/arclink_notification_delivery.py` owns final delivery and marks the
matching report delivered after the outbox row succeeds. Supported quiet-hours
windows use `HH:MM-HH:MM`; unsupported free-form quiet-hours text is treated as
no delay.

Operators can inspect aggregate status at `GET /api/v1/admin/wrapped` and in
the admin dashboard Wrapped tab. These surfaces expose report counts, due
counts, failure counts, latest scores, and Captain ids only. They must not
include Captain report text, Markdown, or raw ledger snippets.

**Wrapped troubleshooting:**
- Missing reports: check `arclink-wrapped` is present in the Docker control
  stack and that active users have no existing successful report for the due
  period.
- Persistent failures: inspect failed `arclink_wrapped_reports` rows and
  Operator notification rows; failure metadata must stay redacted.
- Delivery not marked delivered: check the matching `captain-wrapped`
  `notification_outbox` row, public channel metadata, and notification delivery
  logs before re-running the scheduler.
- Operator view includes narrative: treat that as a privacy regression and
  repair the aggregate read model before exposing the admin route.

**OpenAPI contract:** `GET /api/v1/openapi.json` (no auth). Static copy at
`docs/openapi/arclink-v1.openapi.json`.

**Troubleshooting:**
- 503 on health: check SQLite DB path and file permissions.
- CORS errors: ensure `ARCLINK_CORS_ORIGIN` matches the dashboard origin exactly.
- Cookie issues: verify `ARCLINK_COOKIE_DOMAIN` matches the request domain;
  set `ARCLINK_COOKIE_SECURE=0` for plain HTTP dev.

## 2. Ingress / DNS

**Module:** `python/arclink_ingress.py`

**Operations:**
| Function | Purpose |
|----------|---------|
| `desired_arclink_ingress_records(...)` | Compute expected domain-mode DNS records or empty Tailscale DNS intent |
| `provision_arclink_dns(...)` | Create/update Cloudflare records in domain mode (fake default) |
| `reconcile_arclink_dns(...)` | Detect domain-mode drift between desired and actual |
| `teardown_arclink_dns(...)` | Remove Cloudflare records for a deployment |
| `render_traefik_dynamic_labels(...)` | Generate host or path-based Traefik Docker labels |

**Common env vars:**
| Var | Purpose |
|-----|---------|
| `ARCLINK_INGRESS_MODE` | `domain` or `tailscale` |
| `ARCLINK_BASE_DOMAIN` | Root domain in domain mode; fallback host in Tailscale mode |
| `ARCLINK_EDGE_TARGET` | CNAME target in domain mode |

**Domain-mode env vars:**
| Var | Purpose |
|-----|---------|
| `CLOUDFLARE_API_TOKEN_REF` or `CLOUDFLARE_API_TOKEN` | Scoped API token for zone writes; prefer the `secret://` ref form |
| `CLOUDFLARE_ZONE_ID` | Target zone |

**Tailscale-mode env vars:**
| Var | Purpose |
|-----|---------|
| `ARCLINK_TAILSCALE_DNS_NAME` | Control or worker node FQDN |
| `ARCLINK_TAILSCALE_HTTPS_PORT` | Funnel/Serve HTTPS port, default `443` |
| `ARCLINK_TAILSCALE_NOTION_PATH` | Public Notion webhook path |
| `ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY` | `path`; Tailscale MagicDNS/Funnel does not provide ArcLink's dynamic per-Captain wildcard subdomains |
| `ARCLINK_TAILNET_SERVICE_PORT_BASE` | First HTTPS port for per-deployment Hermes/files/code tailnet apps in Tailscale path mode |

**Production private-mesh env vars:**
| Var | Purpose |
|-----|---------|
| `ARCLINK_PRIVATE_DNS_NAME` | Preferred Control Node private mesh/WireGuard DNS or IP for remote ArcPods |
| `ARCLINK_CONTROL_PRIVATE_BASE_URL` | Preferred private-mesh base URL remote ArcPods use for Control Node API and inference router access; install/reconfigure auto-generates a WireGuard URL when unset |
| `ARCLINK_WIREGUARD_CONTROL_URL` | WireGuard-specific alias for `ARCLINK_CONTROL_PRIVATE_BASE_URL` |
| `ARCLINK_PRIVATE_MESH_CONTROL_URL` | Generic private-mesh alias for `ARCLINK_CONTROL_PRIVATE_BASE_URL` |
| `ARCLINK_CONTROL_PRIVATE_BIND_HOST` | Host/IP the Control Node ingress publishes on for private mesh traffic; defaults to the WireGuard control tunnel IP when WireGuard is enabled |
| `ARCLINK_CONTROL_PRIVATE_HTTP_PORT` | Host port for private mesh control ingress; defaults to the Control web port when WireGuard is enabled |
| `ARCLINK_WIREGUARD_ENABLED` | Enables Control Node WireGuard readiness during install/reconfigure, default `1` |
| `ARCLINK_WIREGUARD_INTERFACE` | Control/worker WireGuard interface name, default `wg-arclink` |
| `ARCLINK_WIREGUARD_NETWORK_CIDR` | Fleet tunnel subnet, default `10.44.0.0/24` |
| `ARCLINK_WIREGUARD_CONTROL_IP` | Control Node tunnel IP, default `10.44.0.1` |
| `ARCLINK_WIREGUARD_PORT` | Control Node WireGuard UDP port, default `51820` |
| `ARCLINK_WIREGUARD_ACTIVATE` | Enables control interface activation during install/reconfigure, default `1` |
| `ARCLINK_WIREGUARD_CONTROL_PUBLIC_KEY` | Control Node public key generated from private state |
| `ARCLINK_WIREGUARD_CONTROL_ENDPOINT` | Worker peer endpoint in `host:port` form |

**Fake mode:** Default. Records and intent are persisted to SQLite but no
provider API calls are made. Drift reconciliation reports local-only state.

**Domain live mode:** Enabled when `CLOUDFLARE_ZONE_ID` is set with either
`CLOUDFLARE_API_TOKEN_REF` or the legacy `CLOUDFLARE_API_TOKEN` env value.
Creates real DNS records. Teardown deletes records from Cloudflare.

**Tailscale live mode:** `deploy.sh control install` keeps the control node
Dockerized, then uses the host Tailscale CLI as the network edge. It publishes
the web/API/Notion routes on the selected HTTPS port and does not require
Cloudflare DNS credentials. In Tailscale path mode, Docker health/reconcile can
also publish each deployment's Hermes, files, and code surfaces on stable
tailnet HTTPS ports and persist those URLs into deployment metadata.

**Drift detection:**
```python
from arclink_ingress import reconcile_arclink_dns
drift = reconcile_arclink_dns(conn, deployment_id=..., raw_cloudflare=...)
# drift.missing, drift.extra, drift.mismatched
```

**Troubleshooting:**
- Drift false positives: ensure the raw Cloudflare export is current.
- Provision fails: check token scope includes `Zone:DNS:Edit` for the zone.
- Tailscale route absent: confirm the host is logged in to Tailscale and any
  Funnel/Serve approval URL was accepted by a tailnet admin.

## 3. Docker Compose Executor

**Module:** `python/arclink_executor.py`

**Core operations:**
| Operation | Effect |
|-----------|--------|
| `render` | Generate Compose YAML for a deployment |
| `validate` | Schema-check a rendered Compose file |
| `start` / `stop` / `restart` | Lifecycle control per-user stack |
| `inspect` | Status/health of running services |
| `teardown` | Remove containers, networks (volumes preserved by default) |

**Safety:**
- All operations require a valid deployment ID and execution key.
- Secret references (`secret_ref`) must point to file-env paths, never inline
  values. `_require_secret_ref` rejects plaintext.
- Dry-run / fake mode is default. Real Docker calls require the operator
  `ARCLINK_EXECUTOR_LIVE=1` flag.
- Resource limits, health checks, and volume isolation are part of the rendered
  Compose template.
- Docker-mode services with the host Docker socket are trusted-host services.
  Non-root socket services drop Linux capabilities. `control-action-worker` no
  longer runs as root and no longer mounts the Docker socket; local
  lifecycle/apply work routes through `deployment-exec-broker`, and Pod
  migration capture/materialization routes through the root
  `migration-capture-helper`. `agent-supervisor` no longer runs as root and no
  longer mounts the Docker socket; user/home work routes through
  `agent-user-helper`, process execution routes through `agent-process-helper`,
  dashboard network/proxy work routes through `agent-supervisor-broker`, and
  queued Docker-mode operator upgrades route through `operator-upgrade-broker`.
  `config/docker-authority-inventory.json` is the static authority inventory
  for socket/root services; update it with any new Docker socket mount,
  explicit root service, proxy/broker decision, or monitoring/runbook anchor.
- `GAP-019-B2` is recorded in that inventory. A generic Docker socket proxy is
  not accepted as a closure claim; use command-specific brokers with narrow
  operation allowlists, or keep the service classified as accepted
  trusted-host residual risk. Restart lifecycle metadata path overrides fail
  closed unless an operator sets
  `ARCLINK_ACTION_WORKER_ALLOW_LIFECYCLE_PATH_OVERRIDES=1` for an emergency
  maintenance window.
- `GAP-019-AQ` narrows the `agent-supervisor` provisioner child env allowlist.
  `run_provisioner` no longer passes the supervisor's full process environment
  to `arclink-enrollment-provision.sh`; the child keeps Docker mode/path
  config, runtime roots, service URLs, and helper/broker values needed for
  Docker enrollment and queued operator actions, but not unrelated payment,
  provider, bot, ingress, memory-synthesis, session, fleet, Python path, or
  Git/SSH steering env keys. The supervisor service still needs private
  config/state/vault mounts for reconciliation, so this is not a `GAP-019`
  closure.
- `GAP-019-C` adds a local guard for the public-Agent bridge path:
  `notification-delivery` detached bridge jobs may only execute the generated
  `hermes-gateway` bridge command, and Compose fallback files must stay under
  `ARCLINK_STATE_ROOT_BASE`. Rejected bridge commands are incidents to review,
  not retry noise.
- `GAP-019-F` moves the public-Agent gateway exec socket authority out of
  `notification-delivery`. The notification worker now calls
  `gateway-exec-broker` with a bounded deployment id, prefix, generated project
  name, bridge payload, and timeout; the broker rejects raw commands and
  reconstructs the `hermes-gateway` Docker exec command itself. The broker's
  direct socket remains trusted-host authority.
- `GAP-019-Y` narrows the `gateway-exec-broker` service boundary. The broker no
  longer inherits broad `*arclink-env` values and no longer mounts
  `arclink-priv/config`, `arclink-priv/state`, or
  `arclink-priv/secrets/container`; it keeps only `ARCLINK_STATE_ROOT_BASE`,
  optional `ARCLINK_DOCKER_BINARY`, broker token/listener env, the deployment
  state-root bind needed for rendered Compose fallback files, and the writeable
  Docker socket. This reduces ambient private data exposure; it does not make
  the broker's socket authority tenant-safe.
- `GAP-019-AH` narrows the same `gateway-exec-broker` executable lookup. The
  broker now requires `ARCLINK_DOCKER_BINARY` to resolve to a trusted Docker
  CLI path and rejects missing, unsafe, non-executable, non-Docker, or
  PATH-injected values before running-container discovery or gateway exec
  subprocesses are invoked.
- `GAP-019-AY` narrows the same broker's Compose fallback file boundary. If no
  running `hermes-gateway` container is found, fallback `config/arclink.env`
  and `config/compose.yaml` must be exact non-symlink regular readable files
  under the deployment state-root config directory before fallback dispatch.
- `GAP-019-Z` narrows the `agent-supervisor-broker` service boundary. The broker
  no longer inherits broad `*arclink-env` values and no longer mounts
  `arclink-priv/config`, `arclink-priv/state`, or
  `arclink-priv/secrets/container`; it keeps only Docker binary/image, repo
  path, host/container private path metadata, broker token/listener env, and the
  writeable Docker socket for dashboard network/proxy sidecars. This reduces
  ambient private data exposure; it does not make the broker's socket authority
  tenant-safe.
- `GAP-019-AF` narrows the same `agent-supervisor-broker` executable lookup.
  The broker now requires `ARCLINK_DOCKER_BINARY` to resolve to a trusted Docker
  CLI path and rejects missing, unsafe, non-executable, or non-Docker values
  before any dashboard network/proxy subprocess is invoked.
- `GAP-019-AZ` narrows the same dashboard broker's private bind-root boundary.
  `ARCLINK_DOCKER_HOST_PRIV_DIR` and `ARCLINK_DOCKER_CONTAINER_PRIV_DIR` must
  be canonical ArcLink private roots and must not be relative, `/`,
  colon-bearing, newline/carriage-return/NUL-bearing, dot/dotdot, or
  non-canonical values before Docker lookup or dashboard auth-proxy
  `docker run -v` construction.
- `GAP-019-AR` narrows the dashboard backend host boundary shared by
  `agent-supervisor-broker` and `agent-process-helper`. Dashboard backend host
  values must be loopback or Docker-internal/private/link-local IPs; wildcard,
  globally routable, multicast, malformed, or non-IP values fail closed before
  dashboard proxy sidecar or dashboard process subprocess construction.
- `GAP-019-D` removes the Docker socket and socket group from
  `curator-refresh`. The refresh loop still handles vault/Notion/fanout and
  upgrade notification detection; queued Docker-mode upgrade execution remains
  in the enrollment provisioner path and is still trusted-host work until a
  broker or helper split lands.
- `GAP-019-E` adds local executor preflight. Live local/SSH Docker apply and
  lifecycle requests now reject unsafe deployment IDs, mismatched apply project
  names, and env/compose files outside the configured
  `ARCLINK_STATE_ROOT_BASE` deployment config root before Docker runner
  dispatch.
- `GAP-019-G` moves local deployment executor socket authority out of
  `control-provisioner`. The provisioner no longer mounts the Docker socket in
  Docker mode; it sends a bounded deployment id, generated project name,
  operation kind, env file, and compose file request to
  `deployment-exec-broker`. The broker rejects raw commands and reconstructs
  the allowed Compose `up`, `ps`, or `down` operation. This narrows the command
  path but does not make the broker's direct writeable Docker socket access
  tenant-safe.
- `GAP-019-AA` narrows `deployment-exec-broker` to minimal service env. The
  broker no longer inherits broad `*arclink-env` values; it keeps only broker
  token/listener settings, `ARCLINK_STATE_ROOT_BASE`, optional Docker binary,
  the deployment state-root bind, and the writeable Docker socket needed for
  allowlisted deployment Compose operations.
- `GAP-019-AG` narrows the same `deployment-exec-broker` executable lookup.
  The broker now requires `ARCLINK_DOCKER_BINARY` to resolve to a trusted Docker
  CLI path and rejects missing, unsafe, non-executable, or non-Docker values
  before any deployment Compose subprocess is invoked.
- `GAP-019-AX` narrows the same broker's rendered config-file boundary. The
  requested deployment root and config root must be non-symlink directories,
  and `config/arclink.env` plus `config/compose.yaml` must be non-symlink
  regular readable files before Docker CLI lookup, runner construction, or
  Compose subprocess dispatch.
- `GAP-019-H` removes direct Docker socket authority from
  `control-action-worker`. Docker-mode local lifecycle/apply calls now require
  `ARCLINK_DEPLOYMENT_EXEC_BROKER_URL` and token and route through
  `deployment-exec-broker`.
- `GAP-019-K` makes that root capture path fail closed by default. Non-dry-run
  Pod migration capture requires
  `ARCLINK_ACTION_WORKER_ALLOW_ROOT_MIGRATION_CAPTURE=1` for an
  operator-controlled migration window, and the migration code validates the
  source state root, target state root, and `.migrations/<migration_id>` staging
  directory as deployment-scoped ArcLink paths before root file copying starts.
  This is an opt-in gate, not proof that live migration is safe.
- `GAP-019-N` removes the root boundary from `control-action-worker`.
  Docker-mode Pod migration capture/materialization now requires
  `ARCLINK_MIGRATION_CAPTURE_HELPER_URL` and
  `ARCLINK_MIGRATION_CAPTURE_HELPER_TOKEN`; the tokened
  `migration-capture-helper` rejects raw command fields, reconstructs only
  `capture` and `materialize`, validates deployment id, prefix, migration id,
  source root, target root, and `.migrations/<migration_id>` staging path, and
  then performs the root file copy. The helper still has trusted-host root
  authority over deployment bind mounts during an approved migration window.
- `GAP-019-AC` narrows that `migration-capture-helper` boundary. The Compose
  service no longer inherits broad `*arclink-env`; it keeps only
  `ARCLINK_STATE_ROOT_BASE` and helper token/listener env, and helper request
  validation rejects source, target, or capture paths outside the configured
  state-root base before root copy or materialize work can start.
- `GAP-019-I` removes direct Docker socket authority from `agent-supervisor`.
  Dashboard network and auth-proxy sidecar operations now require
  `ARCLINK_AGENT_SUPERVISOR_BROKER_URL` and token and route through
  `agent-supervisor-broker`. The broker rejects raw commands and validates
  safe agent ids, deterministic network/container names, ports, backend IPs,
  and access-file confinement. The broker's socket remains trusted-host
  residual risk.
- `GAP-019-Z` narrows that dashboard broker's Compose service boundary. It no
  longer receives broad app env or broad private config/state/secrets mounts,
  while preserving the explicit path/image metadata and broker token/listener env
  required to reconstruct dashboard sidecar commands.
- `GAP-019-AF` makes that dashboard broker fail closed before subprocess
  execution when `ARCLINK_DOCKER_BINARY` is not a trusted Docker CLI path. Treat
  such a rejection as a broker boundary incident, not a reason to rerun the
  request with a raw command.
- `GAP-019-AZ` makes that dashboard broker fail closed before Docker lookup or
  sidecar dispatch when the host/container private bind roots are malformed
  Docker volume specs, relative/root paths, dot/dotdot paths, or non-canonical
  ArcLink private roots.
- `GAP-019-AR` makes that dashboard broker and the root process helper fail
  closed on unsafe dashboard backend host values. The accepted backend host
  class is loopback or Docker-internal/private/link-local IP only; reject
  wildcard, globally routable, multicast, malformed, or non-IP values as
  boundary incidents before any dashboard proxy or dashboard process subprocess
  exists.
- `GAP-019-AG` makes the deployment broker fail closed before subprocess
  execution when `ARCLINK_DOCKER_BINARY` is not a trusted Docker CLI path. Treat
  such a rejection as a deployment broker boundary incident, not a reason to run
  manual `docker compose` from caller-provided paths.
- `GAP-019-AX` makes the deployment broker fail closed before Docker CLI lookup
  when rendered deployment config files are symlinked, missing, non-regular, or
  unreadable. Treat this as a deployment broker boundary incident and rebuild
  the deployment render rather than following or repairing the symlink target.
- `GAP-019-AH` makes the gateway broker fail closed before subprocess execution
  when `ARCLINK_DOCKER_BINARY` is not a trusted Docker CLI path. Treat such a
  rejection as a public Agent gateway broker boundary incident, not a reason to
  replay raw bridge commands outside the broker contract.
- `GAP-019-AY` makes the gateway broker fail closed before Compose fallback
  dispatch when rendered fallback config files are symlinked, missing,
  non-regular, unreadable, or directories. Treat this as a public Agent gateway
  broker boundary incident and rebuild the deployment render rather than
  following or repairing the symlink target.
- `GAP-019-BC` records gateway broker rejected-request incidents under
  `ARCLINK_STATE_ROOT_BASE/_broker-incidents/gateway-exec-broker/rejections.jsonl`
  when the deployment state root is absolute, non-root, existing, and
  non-symlinked. Rows contain only safe deployment/project metadata,
  trusted-host acknowledgement state, error class, and sanitized reason codes.
  Treat raw-command, project-name mismatch, unsupported-platform, and
  trusted-host acknowledgement failures as public Agent gateway broker boundary
  incidents; do not retry them with raw Docker commands or caller-supplied
  payloads.
- `GAP-019-BD` records the same kind of redacted rejected-request incidents for
  `deployment-exec-broker`, `migration-capture-helper`, `agent-user-helper`,
  `agent-supervisor-broker`, and `operator-upgrade-broker`. Review those JSONL
  rows before retrying failed Docker lifecycle, migration, user-home,
  dashboard-sidecar, or operator-upgrade work. The rows intentionally omit raw
  request bodies, command arrays, private paths, payload values, tokens, chat
  ids, user ids, message text, and stack traces.
- `GAP-019-AI` makes the operator upgrade broker fail closed before child
  subprocess execution when `ARCLINK_DOCKER_BINARY` is not a trusted Docker CLI
  path. Treat such a rejection as an operator-upgrade broker boundary incident,
  not a reason to rerun queued upgrades with a raw command or caller-provided
  executable path.
- `GAP-019-AV` makes the operator upgrade broker fail closed before private
  operator log creation or child subprocess execution when the configured host
  repo's fixed `deploy.sh` or `bin/component-upgrade.sh` target is missing,
  symlinked, a directory, unreadable, or non-executable. Treat that as a
  checkout-integrity incident, not a reason to point the broker at another
  script path.
- `GAP-019-AW` makes the operator upgrade broker fail closed before child env
  construction, private operator log creation, or child subprocess execution
  when request-supplied `ARCLINK_UPSTREAM_DEPLOY_KEY_PATH` or
  `ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE` is relative, outside
  `ARCLINK_DOCKER_HOST_PRIV_DIR`, or symlink-steered. Treat that as an upstream
  deploy-key path boundary incident, not a reason to rerun the queued upgrade
  with caller-provided key paths.
- `GAP-019-AK` keeps tokened broker/helper HTTP APIs off the default Compose
  network. The deployment, migration, agent-user, agent-process, dashboard
  broker, operator-upgrade broker, and gateway broker request lanes use
  internal Compose networks shared only with their legitimate callers. The
  process helper and operator-upgrade broker also have single-service egress
  networks for outbound runtime or upgrade work; do not attach additional
  services to those networks without updating `config/docker-authority-inventory.json`.
- `GAP-019-AL` adds the trusted-host acknowledgement gate for those seven
  high-authority services. `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED` must be
  set to the exact value `accepted` in private Docker config before
  `deployment-exec-broker`, `migration-capture-helper`, `agent-user-helper`,
  `agent-process-helper`, `agent-supervisor-broker`,
  `operator-upgrade-broker`, or `gateway-exec-broker` will bind an HTTP
  listener or process direct helper/broker requests. Missing, blank, false, or
  other values are fail-closed trusted-host boundary incidents, not transient
  startup failures. This acknowledges residual risk only; `GAP-019` remains
  open until stronger isolation or an operator acceptance decision replaces it,
  and live proof gates such as `GAP-001`, `PG-UPGRADE`, `PG-PROVISION`,
  `PG-BOTS`, and `PG-HERMES` remain separate.
- `GAP-019-AP` makes direct/local execution of those same high-authority
  broker/helper modules bind `127.0.0.1` by default. Compose is the explicit
  source-owned opt-in to `0.0.0.0` for internal request-network reachability,
  and healthchecks stay on `127.0.0.1`. `--host` and service-specific
  `ARCLINK_*_HOST` values still override the default, so broad binds are
  intentional and reviewable instead of inherited from direct-run defaults.
- `GAP-019-O` moves container-local user/home setup out of
  `agent-supervisor`. Docker-mode user/home setup now requires
  `ARCLINK_AGENT_USER_HELPER_URL` and token and routes through
  `agent-user-helper`. The helper runs as root, has no Docker socket, rejects
  raw command fields, accepts only `ensure_user_home`, and validates agent id,
  Unix user, Docker agent-home root, agent home, Hermes home, and workspace
  path before creating paths, persisting a numeric uid/gid assignment, or
  repairing ownership. The helper's root authority remains trusted-host
  residual risk.
- `GAP-019-Q` narrows the same `agent-user-helper` root boundary in Compose.
  The service drops Docker's default Linux capability set and adds back only
  `CHOWN`, `DAC_OVERRIDE`, and `FOWNER` for canonical Docker agent-home
  bind-mount writes and ownership repair. Any capability drift in Compose or
  `config/docker-authority-inventory.json` is a boundary change, not routine
  formatting.
- `GAP-019-AE` narrows the same helper's executable lookup boundary.
  `agent-user-helper` pins `groupadd`, `useradd`, and `chown` to
  `/usr/sbin/groupadd`, `/usr/sbin/useradd`, and `/usr/bin/chown`, and
  preflights those paths before uid/gid assignment writes, directory creation,
  account commands, or recursive ownership repair.
- `GAP-019-BA` narrows the same helper's assignment-file boundary.
  `.arclink-user-ids.json` and `.arclink-user-ids.json.tmp` under the Docker
  agent-home root must be canonical non-symlink regular-or-missing files before
  uid/gid assignment reads or writes. Symlinked, directory, or non-regular
  assignment paths fail closed before assignment writes, account commands,
  agent-home directory creation, or recursive chown.
- `GAP-019-AN` narrows both root agent helpers' symlink path boundary.
  `agent-user-helper` rejects symlink-escaped agent home, Hermes home, and
  workspace paths before trusted executable preflight, uid/gid assignment,
  directory creation, account commands, or recursive chown.
  `agent-process-helper` rejects the same symlink-escaped path class before
  helper log creation, `subprocess.run`, or `subprocess.Popen`.
- `GAP-019-AS` narrows the configured Docker agent-home root path boundary.
  `agent-user-helper` and `agent-process-helper` reject symlinked
  configured/requested agent-home roots, including
  `ARCLINK_DOCKER_AGENT_HOME_ROOT`, before uid/gid assignment writes,
  ownership repair, helper log creation, `subprocess.run`, or
  `subprocess.Popen`.
- `GAP-019-AT` narrows the process-helper configured-root path boundary.
  `agent-process-helper` rejects symlinked configured/requested repo,
  private-state, state, and runtime roots, including `ARCLINK_REPO_DIR`,
  `ARCLINK_PRIV_DIR`, `ARCLINK_DOCKER_CONTAINER_PRIV_DIR`, request
  `state_dir`, and `RUNTIME_DIR`, before helper log creation,
  `subprocess.run`, or `subprocess.Popen`.
- `GAP-019-AU` narrows the process-helper fixed command target boundary.
  `agent-process-helper` rejects missing, symlinked, directory, unreadable, or
  non-executable repo command targets, including `bin/hermes-shell.sh`, before
  helper log creation, `subprocess.run`, or `subprocess.Popen`.
- `GAP-019-AO` narrows the process-helper log path boundary. A pre-existing
  `state/docker/agent-process-helper` symlink, symlinked ancestor under
  `state/docker`, or helper log file symlink fails before log open,
  `subprocess.run`, or `subprocess.Popen`.
- `GAP-019-BB` adds redacted process-helper rejection incidents. Rejected
  requests append one JSONL row to
  `state/docker/agent-process-helper/rejections.jsonl` when the configured
  private root is safe. Rows include safe metadata such as operation, safe
  agent id when present, trusted-host acknowledgement state, error class, and
  sanitized reason, but not raw request bodies, env values, args, private
  paths, tokens, or stack traces.
- `GAP-019-BC` adds redacted gateway broker rejection incidents. Rejected
  requests append one JSONL row to
  `ARCLINK_STATE_ROOT_BASE/_broker-incidents/gateway-exec-broker/rejections.jsonl`
  when the configured deployment state root is safe. Rows include safe
  deployment id and generated project name when available, trusted-host
  acknowledgement state, error class, and sanitized reason, but not raw request
  bodies, bridge payload values, bot tokens, chat ids, user ids, message text,
  process args, rendered config paths, private paths, or stack traces.
- `GAP-019-BD` extends redacted rejected-request JSONL rows to
  `deployment-exec-broker`, `migration-capture-helper`, `agent-user-helper`,
  `agent-supervisor-broker`, and `operator-upgrade-broker` using only their
  already-scoped state roots or a narrow dashboard-broker incident mount.
  Missing, unsafe, or symlinked incident roots fail closed without fallback
  logging elsewhere.
- `GAP-019-P` moves setpriv-based Docker agent process execution out of
  `agent-supervisor`. Docker-mode install, identity refresh, user-agent
  refresh, cron, gateway, and dashboard process execution now requires
  `ARCLINK_AGENT_PROCESS_HELPER_URL` and token and routes through
  `agent-process-helper`. The helper runs as root, has no Docker socket,
  rejects raw command fields, accepts only `run_once`, `ensure_processes`, and
  `terminate_all`, and validates agent id, Unix user, Docker agent-home root,
  agent home, Hermes home, workspace path, uid/gid, safe env keys, canonical
  env values, and dashboard backend fields before reconstructing allowlisted
  commands. The helper's root authority remains trusted-host residual risk.
- `GAP-019-R` narrows the `agent-process-helper` env exposure path. The helper
  now passes validated env through subprocess `env=` instead of encoding env
  assignments into setpriv argv, and startup command lines in
  `state/docker/agent-process-helper/*.log` no longer contain env values. The
  supervisor also strips broker/helper tokens from per-agent process specs
  before dispatch. This is env exposure hardening, not removal of the helper's
  root process-runner authority.
- `GAP-019-W` adds the helper-side fail-closed half of that boundary:
  `agent-process-helper` rejects ArcLink broker/helper/control token env keys,
  including future `ARCLINK_*_TOKEN` names, before log creation,
  `subprocess.run`, or `subprocess.Popen`.
- `GAP-019-AM` closes the next process-helper env injection slice:
  `agent-process-helper` now rejects dynamic-loader `LD_*`, Python
  path/startup, shell startup, Git/SSH command-steering, and secret-looking
  `*_TOKEN`, `*_SECRET`, `*_PASSWORD`, or `*_KEY` process env keys before log
  creation, `subprocess.run`, or `subprocess.Popen`. `agent-supervisor` strips
  known ArcLink helper tokens and fails closed on the same unapproved non-token
  key family before building helper payloads.
- `GAP-019-AD` closes the process-helper caller-controlled executable lookup
  slice: request `PATH` must match the helper `SAFE_PATH`, one-shot and
  long-running agent launches call `/usr/bin/setpriv` by absolute path, and
  identity setup fails closed before `subprocess.run` if the pinned runtime
  venv Python is absent.
- `GAP-019-AJ` hardens process-helper reconciliation for long-running gateway
  and dashboard processes. The helper now tracks a desired signature for the
  validated setpriv command, Hermes-home cwd, and process env contract. If that
  signature changes under the same `agent_id:kind` key, the stale process group
  is stopped before replacement; identical desired specs are left running.
  Shutdown is bounded: SIGTERM, wait, SIGKILL, wait, then fail closed before
  starting a duplicate replacement.
- `GAP-019-AR` also applies at the process-helper dashboard boundary:
  dashboard backend host values are parsed as IP addresses and must be
  loopback or Docker-internal/private/link-local before helper log creation,
  desired-process signature calculation, or `subprocess.Popen`.
- `GAP-019-X` narrows the root helper service boundary in Compose:
  `agent-process-helper` no longer inherits broad `*arclink-env` values and no
  longer mounts `arclink-priv/secrets/container`. It keeps explicit non-secret
  Docker mode/path validation env, its token/listener keys, and the config,
  state, vault, and read-only repo mounts needed by allowlisted agent commands.
  This reduces ambient secret exposure; it does not remove the helper's root
  process-runner authority.
- `GAP-019-S` narrows root-helper request path authority. `agent-user-helper`
  now rejects configured `ARCLINK_DOCKER_AGENT_HOME_ROOT` mismatches before
  uid/gid assignment writes, directory creation, account commands, or
  recursive ownership repair. `agent-process-helper` now rejects configured
  Docker agent-home, repo, private-state, state, and runtime root mismatches
  before helper log creation, `subprocess.run`, or `subprocess.Popen`. This is
  request-path confinement, not removal of either helper's residual root
  authority.
- `GAP-019-AN` adds the symlink-escape check to that confinement: canonical
  agent home, Hermes home, and workspace paths must resolve to their expected
  child targets, not to pre-existing symlink targets outside the Docker agent
  path.
- `GAP-019-AS` adds the configured-root symlink check to that confinement:
  configured/requested Docker agent-home roots must not be symlinks or include
  symlink components before either root helper performs filesystem, log, or
  process work.
- `GAP-019-AT` adds the process-helper configured-root symlink check to that
  confinement: configured/requested repo, private-state, state, and runtime
  roots must not be symlinks or include symlink components before helper log
  creation or process execution.
- `GAP-019-AU` adds fixed repo command target checks to that confinement:
  missing, symlinked, directory, unreadable, or non-executable fixed command
  targets fail before helper log creation or process execution.
- `GAP-019-AO` adds the same confinement to process-helper logs: the helper log
  directory and log file must resolve to their exact canonical private-state
  children before any log is opened or process execution starts.
- `GAP-019-T` narrows live-checkout write access. `agent-supervisor`,
  `agent-process-helper`, and `curator-refresh` now use read-only host repo
  binds because they only need ArcLink script reads for refresh, detection, and
  typed process execution. `GAP-019-U` moves the explicit writable host repo
  exception for allowlisted queued Docker-mode operator upgrades to
  `operator-upgrade-broker`, and that exception stays trusted-host residual
  risk.
- `GAP-019-J` routes queued Docker-mode operator upgrades and
  component-upgrade apply/final-upgrade execution through
  `operator-upgrade-broker`. The enrollment provisioner fails closed without
  `ARCLINK_OPERATOR_UPGRADE_BROKER_URL` and token. The broker rejects raw
  command fields, reconstructs only `deploy.sh upgrade` or allowlisted
  `component-upgrade.sh ... --skip-upgrade` commands from the configured host
  repo, and confines logs to private `state/operator-actions`. The broker's
  socket and live host checkout mount remain trusted-host residual risk.
- `GAP-019-AB` narrows the same operator broker's service and subprocess env
  boundary. It no longer inherits broad `*arclink-env`, no longer mounts broad
  canonical private config/state or `arclink-priv/secrets/container`, and its
  allowlisted upgrade subprocesses use a child-process env allowlist instead
  of inheriting the broker's full environment. The writable host checkout bind
  can still reach nested private state for real upgrades and remains residual
  trusted-host authority with the Docker socket.
- `GAP-019-AI` narrows the same operator broker's executable lookup. Any
  preserved `ARCLINK_DOCKER_BINARY` value must resolve to a trusted absolute
  Docker CLI path before `deploy.sh upgrade` or allowlisted
  component-upgrade children are invoked; unsafe, missing, non-executable,
  non-Docker, relative, or PATH-injected values fail closed before
  `subprocess.run`.
- `GAP-019-AV` narrows the same operator broker's fixed script target
  boundary. The configured host repo's `deploy.sh` and
  `bin/component-upgrade.sh` must be exact non-symlink regular readable files
  with executable bits before private operator logs or subprocesses are
  created.
- `GAP-019-AW` narrows the same operator broker's upstream deploy-key path
  boundary. Non-empty `ARCLINK_UPSTREAM_DEPLOY_KEY_PATH` and
  `ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE` values must be absolute non-symlink
  paths under `ARCLINK_DOCKER_HOST_PRIV_DIR` before child env construction,
  private operator logs, or subprocesses are created.
- `GAP-019-U` splits queued upgrade execution out of
  `agent-supervisor-broker`. That dashboard broker no longer accepts
  `run_operator_upgrade` or `run_pin_upgrade` and no longer mounts the live
  host repo; `operator-upgrade-broker` owns those operation kinds and the
  writable host repo exception.
- `GAP-019-V` removes the read-only Docker provider discovery boundary from
  `control-ingress`. Control Node ingress now uses static Traefik file-provider
  routes from `config/traefik-control.yaml` for `/notion/webhook`, `/v1`,
  `/api`, and `/`; the service no longer mounts `/var/run/docker.sock`.
- `GAP-019-L` validates Docker-mode `agent-supervisor` active-agent metadata
  before helper, broker, or process-helper requests. Unsafe `agent_id`, `unix_user`,
  `hermes_home`, Docker agent home, workspace path, supervisor log/process key,
  or agent process env key values are rejected before any delegated root or
  broker operation.
- `GAP-019-M` records incident controls in
  `config/docker-authority-inventory.json` for the remaining writeable socket
  brokers and explicit root helpers. Each residual row must name monitored
  signals, status/log/audit locations, triage steps, fail closed actions, and
  the operator escalation boundary. A raw command rejection, escaped path,
  unsafe active-agent metadata row, missing broker/helper token, process-helper
  `rejections.jsonl` row, or root-capture request without opt-in is a boundary
  incident, not routine retry noise.

**Rollback:**
- `_plan_rollback_apply(plan)` generates a rollback intent.
- Destructive state deletes (`_is_destructive_state_delete`) are separately
  gated and audit-logged.
- Unhealthy services are identified via `_rollback_unhealthy_services`.
- Idempotent: same execution key returns the same plan without re-execution.

**Troubleshooting:**
- Render fails: check the deployment intent has all required service blocks.
- Start fails: verify Docker socket access, that the project name is unique,
  and that the deployment root, env file, and compose file are under
  `ARCLINK_STATE_ROOT_BASE`.
- Secret ref rejected: ensure values use `file:/run/secrets/...` or env-file
  patterns, never raw key material.

## 4. Chutes Provider

**Modules:** `python/arclink_chutes.py`, `python/arclink_chutes_live.py`,
`python/arclink_chutes_oauth.py`, `python/arclink_llm_router.py`

**Operations:**
| Function | Purpose |
|----------|---------|
| `parse_chutes_models(payload)` | Parse model catalog from Chutes API |
| `validate_default_chutes_model(...)` | Confirm selected default is valid |
| `ChutesLiveAdapter` | Secret-reference boundary for model, account, usage, quota, discount, price override, API-key, OAuth-scope, token-introspection, and balance-transfer API shapes |
| `start_chutes_oauth_connect(...)` | Build a PKCE Chutes OAuth connect plan with state, CSRF, user/session scope, and public scope display |
| `complete_chutes_oauth_callback(...)` | Complete a scoped OAuth callback and store returned token material behind secret references |

**Key lifecycle (executor-managed):**
- Create: `_fake_chutes_key_id(deployment_id, secret_ref, generation)` in fake mode.
- Rotate: new generation increments the key ID.
- Revoke: teardown removes key state for the deployment.
- Per-deployment key state tracked in `arclink_chutes_keys` table.

**Router boundary:** The source-level ArcLink LLM Router moves production
inference toward a central Control Node service instead of mounting the central
Chutes key into ArcPods. It verifies a per-deployment ArcLink router key,
enforces billing/budget/model/rate/concurrency checks, reserves budget before
forwarding, relays streaming or non-streaming chat completions to Chutes, and
records sanitized usage rows without prompts or completions. The router is
documented in `docs/arclink/llm-router.md`. Control Node Compose wiring and
ArcPod provider defaults are router-first locally; direct Chutes remains only
behind `ARCLINK_ALLOW_DIRECT_CHUTES_IN_ARCPODS=1`. Live Chutes proof is still
operator-gated.

**Access boundary:** Local provider evaluation fails closed unless all of these
are true: billing is current, a scoped per-user or per-deployment `secret://`
reference exists, the secret reference contains the user or deployment scope,
and the configured monthly budget has remaining capacity. An operator-level
`CHUTES_API_KEY` is useful for model/provider administration, but it is not
accepted as customer isolation for inference. If per-key metering is explicitly
unavailable and no scoped secret is present, the deployment is marked as
requiring a per-user Chutes account/OAuth lane before inference. User-facing
dashboards and public bots must never collect raw provider tokens; route
provider credentials through the scoped secret handoff/secret-reference path.

**OAuth and account boundary:** Chutes OAuth/connect is locally modeled and
fake-tested, but live delegated inference and token revocation are proof-gated.
The connect plan uses PKCE, binds state to the user and session, validates CSRF,
stores access/refresh token material only behind generated `secret://`
references, and returns public connection metadata without raw token values.
The recommended product path is per-user Chutes provider account connection
when the operator chooses that policy; until then OAuth, usage sync, API-key
CRUD, registration assist, and balance transfer remain disabled or explicitly
proof-gated. ArcLink must not claim silent server-side Chutes provider account
creation or use browser/TLS challenge-bypass tooling; official
registration-token, hotkey/coldkey, and funding requirements are treated as
assisted or operator-authorized proof work.

**Billing and budget:** Non-current billing states suspend provider access
immediately. User and admin provider-state responses expose the local lifecycle:
immediate notice, daily reminders, day-7 account/data-removal warning metadata,
and day-14 audited purge queue metadata. Usage ingestion updates local
deployment budget counters and blocks inference at the hard limit. Local
provider-budget credit helpers record a fair-credit ledger and can apply credit
to the deployment's local Chutes provider budget; live purchase handling and
direct provider balance application remain proof-gated.

**Env vars (live mode):**
| Var | Purpose |
|-----|---------|
| `CHUTES_API_KEY` | Owner key for model catalog and key management |
| `ARCLINK_LLM_ROUTER_CHUTES_API_KEY` | Central Chutes credential used only by the Control Node LLM router |
| `ARCLINK_LLM_ROUTER_DEFAULT_MODEL` | Default model string; may be a provider-side fallback CSV when the provider supports it |
| `ARCLINK_LLM_ROUTER_ALLOWED_MODELS` | Router-level allowlist for model strings accepted from ArcPods |
| `ARCLINK_LLM_ROUTER_FALLBACK_MODELS` | Router-owned fallback models attempted after retryable provider errors |
| `ARCLINK_LLM_ROUTER_FALLBACK_STATUS_CODES` | Provider status codes, default `429,500,502,503,504`, that trigger fallback while candidates remain |
| `ARCLINK_LLM_ROUTER_REFRESH_MODEL_CATALOG_ON_STARTUP` | Refresh Chutes `/models` into the Control Node catalog on router startup |
| `ARCLINK_LLM_ROUTER_MODEL_AUTO_PROMOTE` | Route older, deprecated, or unavailable same-family model requests to the latest active model |
| `ARCLINK_LLM_ROUTER_MODEL_REPLACEMENTS` | Emergency `old-model=new-model` overrides for fleet-wide model moves |
| `ARCLINK_CHUTES_DEFAULT_MONTHLY_BUDGET_CENTS` | Local monthly provider budget before any applied credit |
| `ARCLINK_CHUTES_WARNING_THRESHOLD_PERCENT` | Warning threshold for local budget status |
| `ARCLINK_CHUTES_HARD_LIMIT_PERCENT` | Hard stop threshold for local budget status |
| `ARCLINK_CHUTES_PER_KEY_METERING_AVAILABLE` | Set false/unavailable to require the per-user account/OAuth fallback |
| `ARCLINK_REFUEL_SKU_ID` | Local provider-budget credit SKU id |
| `ARCLINK_REFUEL_CREDIT_CENTS` | Default local provider-budget credit amount |
| `ARCLINK_REFUEL_CURRENCY` | Local credit currency, default `usd` |

**External proof gates:** The provider-specific live proof path is
`bin/arclink-live-proof --journey external --live --json`. Each Chutes provider
proof row requires its own `ARCLINK_PROOF_CHUTES_*` flag and the matching
secret references or live credential variables documented in
`docs/arclink/live-e2e-secrets-needed.md`. API-key creation/deletion and
balance transfer additionally require `ARCLINK_CHUTES_ALLOW_MUTATION`; without
that gate, mutation methods fail closed.

**Fake mode:** Default. Model catalog uses a built-in fixture. Key operations
write to SQLite only, live-adapter fixtures return redacted Chutes provider
payloads, OAuth callbacks use fake exchangers, and budget/credit accounting is
local state only.

**Troubleshooting:**
- Model catalog empty: check `CHUTES_API_KEY` is set for live catalog fetch.
- Key creation fails: verify the deployment has an active entitlement.
- Provider state says `billing_suspended`: restore billing before rotating or
  reissuing provider credentials.
- Provider state says `operator_shared_key_rejected`: configure a scoped
  per-user or per-deployment secret reference, or use the per-user account/OAuth
  fallback when per-key metering is not available.
- OAuth callback rejected: check the callback user/session, state, CSRF token,
  callback expiry, and TLS redirect URI before assuming provider failure.
- Balance transfer returns `fake_not_executed` or a proof-gated error: this is
  expected until an authorized live transfer row is enabled.

## 5. Stripe Boundary

**Module:** `python/arclink_entitlements.py`

Operator dashboard setup instructions live in
`docs/arclink/operator-stripe-webhook.md`. Use that guide when creating the
Stripe Dashboard event destination during install.

**Operations:**
| Function | Purpose |
|----------|---------|
| `process_stripe_webhook(conn, event, ...)` | Ingest and apply webhook events |
| `detect_stripe_reconciliation_drift(conn)` | Compare local vs Stripe state |

**Webhook processing flow:**
1. Record raw event in `arclink_webhook_events`.
2. Extract user/subscription/onboarding IDs from event + metadata.
3. Map event type to entitlement transition.
4. Apply entitlement change and mark processed.
5. On failure: mark replayable with error detail.

**Env vars:**
| Var | Purpose |
|-----|---------|
| `STRIPE_SECRET_KEY` | Live API calls (portal links, subscription reads) |
| `STRIPE_WEBHOOK_SECRET` | Signature verification on incoming webhooks |
| `ARCLINK_REFUEL_STRIPE_PRODUCT_ID` | Optional reusable Stripe Product id for ArcPod Refueling; when absent Checkout uses inline product data |
| `ARCLINK_REFUEL_STRIPE_PRODUCT_NAME` | Stripe product display name; default `ArcPod Refueling` |
| `ARCLINK_REFUEL_TOPUP_AMOUNTS_CENTS` | Comma-separated Raven refueling packages; default `1000,2500,5000,10000` |
| `ARCLINK_REFUEL_TOPUP_MIN_CENTS` / `ARCLINK_REFUEL_TOPUP_MAX_CENTS` | Custom amount bounds; defaults `$5` to `$500` |
| `ARCLINK_REFUEL_PROVIDER_CREDIT_BPS` | Portion of retail dollars converted into metered provider budget; default `7000` (70%) |
| `ARCLINK_SUBSCRIPTION_INFERENCE_CREDIT_BPS` | Portion of plan retail replenished as included inference budget on paid monthly invoices; default `2000` (20%) |
| `ARCLINK_FOUNDERS_MONTHLY_INFERENCE_CREDIT_CENTS` / `ARCLINK_SOVEREIGN_MONTHLY_INFERENCE_CREDIT_CENTS` / `ARCLINK_SCALE_MONTHLY_INFERENCE_CREDIT_CENTS` | Optional plan-specific included inference-budget overrides |
| `ARCLINK_SOVEREIGN_AGENT_EXPANSION_MONTHLY_INFERENCE_CREDIT_CENTS` / `ARCLINK_SCALE_AGENT_EXPANSION_MONTHLY_INFERENCE_CREDIT_CENTS` | Optional extra-Agent included inference-budget overrides |

**Stripe Dashboard event destination:**
- Destination URL: `https://<control-host>/api/v1/webhooks/stripe`.
- Events from: `Your account`.
- Event selection: `Selected events`, not `All events`.
- Required events: `checkout.session.completed`,
  `customer.subscription.created`, `customer.subscription.updated`,
  `customer.subscription.deleted`, `invoice.payment_succeeded`,
  `invoice.paid`, and `invoice.payment_failed`.
- Signing secret: copy the endpoint `whsec_...` value into
  `STRIPE_WEBHOOK_SECRET` through `./deploy.sh control reconfigure`.

**Billing portal:** User requests via `POST /api/v1/user/portal`. Requires
active user session + CSRF. Fake mode returns a placeholder URL.

**ArcPod Refueling:** Raven exposes `/refuel`, `/top-up`, and `/credits` after
an Agent is live. A bare command shows the fuel package table and buttons.
`/refuel 25` opens a Stripe Checkout session in `payment` mode for a one-time
ArcPod fuel purchase. The default packages are:

| Retail paid by Captain | ArcPod model fuel added | Default gross margin before Stripe/platform costs |
|------------------------|---------------------------------|---------------------------------------------------|
| `$10` | `$7` | `$3` |
| `$25` | `$17.50` | `$7.50` |
| `$50` | `$35` | `$15` |
| `$100` | `$70` | `$30` |

The router spends model fuel at the selected model's current catalog price. If
Chutes reprices a model or a Captain changes model, token capacity changes
automatically because metering is catalog-driven. The Stripe webhook
branch for `checkout.session.completed` with metadata
`arclink_purchase_kind=inference_refuel` grants an `arclink_refuel_credits`
row and applies it to the owning ArcPod's fuel tank only after the
Checkout customer, `client_reference_id`, Captain account, and target ArcPod
match. Subscription entitlement state is not changed by refuel purchases.

Raven low-fuel pings are automatic: when router usage crosses the configured
warning threshold, the Control Node queues a `public-bot-user` notification with
a **Refuel ArcPod** button. The notification is deduped per fuel tank and is
queued off the Agent response path.

**Monthly included inference budget:** Paid subscription invoices replenish
inference budget through the same credit ledger. By default ArcLink converts
20% of plan retail into included provider budget each month: Founders `$29.80`,
Sovereign `$39.80`, Scale `$55.00`, Sovereign extra Agent `$19.80`, and Scale
extra Agent `$15.80`. `invoice.payment_succeeded` and `invoice.paid` are
idempotent per invoice and ArcPod (`<invoice_id>:<deployment_id>`), so Stripe's
duplicate/alias events do not double-credit. If a Captain has multiple active
ArcPods on the same plan, the plan allowance is split across those Pods.

**Reconciliation:** `detect_stripe_reconciliation_drift` compares local
entitlement/subscription records against what Stripe reports. Drift items
surfaced via `GET /api/v1/admin/reconciliation`.

**Troubleshooting:**
- Webhook signature fails: verify `STRIPE_WEBHOOK_SECRET` matches the endpoint
  secret in the Stripe dashboard, not the API key.
- Webhook secret unset: the hosted API returns 503 with
  `stripe_webhook_secret_unset` so Stripe retries. Configure the endpoint
  signing secret with `./deploy.sh control reconfigure`; do not replace it with
  the Stripe API key.
- Drift detected: review the specific drift items; most are timing issues that
  resolve on the next webhook delivery.
- Portal link 500: check `STRIPE_SECRET_KEY` is set and valid.

## 6. Rollback Behavior

**Scope:** Executor-level rollback for failed or unhealthy deployments.

**Trigger:** A provisioning job fails execution, or admin requests rollback via
`POST /api/v1/admin/actions` with action `rollback`.

**Flow:**
1. Executor generates rollback plan from current deployment state.
2. Plan identifies unhealthy services and destructive vs. non-destructive steps.
3. Non-destructive steps (stop, restart) execute immediately.
4. Destructive steps (volume delete, DNS teardown) require explicit admin
   confirmation and are audit-logged before execution.
5. Same idempotency key prevents duplicate rollback execution.

**Admin action pattern:**
```
POST /api/v1/admin/actions
{
  "action": "rollback",
  "deployment_id": "...",
  "reason": "...",
  "csrf_token": "..."
}
```
Requires admin session with mutation role.

**Safety:**
- Rollback never deletes volumes implicitly. Compose volume deletion is gated by
  `metadata.teardown.remove_volumes` (default off; volumes are preserved), and
  destructive state-root/vault deletes are separately gated by
  `_is_destructive_state_delete` and audit-logged. There is no `destructive:true`
  flag in the executor.
- All rollback intents are audit-logged with operator, reason, and timestamp.
- Failed rollback is idempotent: retry with same key resumes, not restarts.

## 7. Health Checks

**API health:** `GET /api/v1/health` returns `200` when healthy, `503` when
degraded (DB unreachable or background service unhealthy).

```bash
curl -sf http://localhost:8900/api/v1/health || echo "UNHEALTHY"
```

**Per-deployment service health:** Provisioned Compose stacks include Docker
health checks for each service. Health status is recorded in
`arclink_service_health` rows and surfaced in the admin dashboard.

```bash
# Check all containers in a deployment stack
docker compose -p arclink-{deployment_id} ps --format json | python3 -m json.tool
```

**Monitoring pattern:**
1. Poll `/api/v1/health` from an external monitor (e.g., UptimeRobot, Healthchecks.io).
2. Admin dashboard shows per-deployment service health under the "service_health" tab.
3. Structured events log health transitions for alerting pipelines.
4. For Docker trusted-host services, also watch `arclink_action_attempts`,
   `arclink_audit_log`, `notification_outbox.delivery_error`,
   `arclink-priv/state/docker/jobs/*.json`, and
   `arclink-priv/state/docker/agent-supervisor/*.log` for failed or unexpected
   socket-backed lifecycle work. Treat
   `public_agent_bridge_rejected_command` in
   `arclink-priv/state/docker/jobs/public-agent-bridge.log` as a trusted-host
   command-path incident.
5. Use the `GAP-019-M` incident controls in
   `config/docker-authority-inventory.json` to map each residual Docker/root
   service to its signals, status/log/audit locations, fail closed action, and
   escalation boundary before retrying or opening any operator maintenance
   window.
   For `agent-process-helper`, check the redacted
   `arclink-priv/state/docker/agent-process-helper/rejections.jsonl` stream
   alongside normal helper logs.
   For `gateway-exec-broker`, check the redacted
   `ARCLINK_STATE_ROOT_BASE/_broker-incidents/gateway-exec-broker/rejections.jsonl`
   stream alongside `public-agent-bridge.log` and notification delivery errors.
6. If a high-authority broker/helper exits with a `GAP-019` trusted-host
   acceptance error, verify the operator has intentionally set
   `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED=accepted` in private Docker
   config after reviewing the residual-risk row. Do not work around the gate
   with ad hoc container edits.
7. If a broker/helper is run directly for diagnostics, expect its listener to
   default to `127.0.0.1`. A direct `0.0.0.0` bind should come only from an
   explicit `--host` or service-specific `ARCLINK_*_HOST` override; Compose
   already owns the internal-network `0.0.0.0` opt-in.

## 8. Restart and Recovery

**API restart:**
```bash
# If running directly
pkill -f arclink_hosted_api.py && python3 python/arclink_hosted_api.py &

# If running via systemd
systemctl restart arclink-api
```

**Per-deployment stack restart:**
```bash
docker compose -p arclink-{deployment_id} restart
```

**Single service restart:**
```bash
docker compose -p arclink-{deployment_id} restart {service_name}
```

**Admin-initiated restart:** `POST /api/v1/admin/actions` with
`action: "restart"` and a target deployment. This queues an intent; the
executor acts on it when live execution is enabled.

## 9. Release and Rollback

**Release flow:**
1. Build and tag new images.
2. Update Compose intent for target deployments.
3. Roll out one deployment at a time.
4. Verify health after each rollout.
5. If healthy, proceed to next deployment.

**Rollback flow:**
1. Admin submits rollback via `POST /api/v1/admin/actions` with
   `action: "rollback"` and a target deployment.
2. Executor generates rollback plan identifying unhealthy services.
3. Non-destructive steps (stop, restart) execute immediately.
4. Destructive steps (volume delete, DNS teardown) require explicit admin
   confirmation and are audit-logged.
5. Rollback preserves state roots and vault data by default.

**Manual rollback:**
```bash
# Stop current stack
docker compose -p arclink-{deployment_id} down

# Restore previous image tags in the Compose file
# Restart
docker compose -p arclink-{deployment_id} up -d
```

## 10. Scale Operations

**Modules:** `python/arclink_fleet.py`, `python/arclink_action_worker.py`,
`python/arclink_rollout.py`, `python/arclink_dashboard.py`,
`python/arclink_operator_raven.py`, `python/arclink_operator_agent.py`,
`python/arclink_enrollment_provisioner.py`

Scale operations cover fleet capacity, deployment placement, queued admin
action execution, rollout waves, and operator visibility. The design is
SQLite-first and fake-by-default so operators can inspect and rehearse the
workflow without live provider credentials.

**Two action queues:** ArcLink drains two distinct queues, not one. Keep them
separate when reasoning about which worker executes an action:

| Queue table | Drained by | Operator Raven writers | Other writers |
| --- | --- | --- | --- |
| `arclink_action_intents` (+ `arclink_action_attempts`) | `python/arclink_action_worker.py` | `pod_repair`, `rollout` (via `queue_arclink_admin_action`) | Admin dashboard/API actions |
| `operator_actions` | enrollment-provisioner root maintenance loop (`_run_pending_operator_actions` in `python/arclink_enrollment_provisioner.py`) | `host_upgrade` → `action_kind="upgrade"`, `pin_upgrade` → `action_kind="pin-upgrade"` (via `request_operator_action`) | Operator notification Preview-button tokens; live mutation still requires a typed Operator Raven `confirm` or approval code |

The action worker consumes `arclink_action_intents`
(`restart`, `reprovision`, `dns_repair`, `rotate_chutes_key`, `refund`,
`cancel`, `comp`, `backup_write_check`, `rollout`,
`academy_apply_preview`/`academy_apply`). The root maintenance loop consumes
`operator_actions` and, in Docker mode
(`ARCLINK_COMPONENT_UPGRADE_MODE=docker`), routes `upgrade`/`pin-upgrade` work
through `operator-upgrade-broker` (see the executor section's `GAP-019-J`
entry). `action_status` in Operator Raven reads both tables.

**Operator Raven as a real mutation entry point:** Operator Raven
(`python/arclink_operator_raven.py`) is not read-only/dry-run. Mutating commands
(`pod_repair`, `rollout`, `host_upgrade`, `pin_upgrade`) use a four-mode
contract: `--dry-run` previews and changes nothing; no `--dry-run` with no
operator actor fails closed; no `--dry-run` with an operator actor but no
`confirm`/approval code fails closed; no `--dry-run` with actor plus confirmation
queues a real, audited, idempotent intent into the matching queue above. Live mutation stays
gated by `ARCLINK_EXECUTOR_ADAPTER` (`fake` = record-only) plus the per-action
proof gate (`PG-PROVISION` restart/reprovision, `PG-INGRESS` dns_repair,
`PG-UPGRADE/PG-HERMES` rollout, `PG-PROVIDER` chutes, `PG-STRIPE` refund/cancel,
`PG-BACKUP` backup_write_check). Read commands (`status`, `agents`,
`fleet_list`, `worker_probe` dry-run only, `user_lookup`, `action_status`,
`upgrade_check`, `academy_status`, `academy_roster`) never mutate. The residual
of `GAP-029` is breadth and unified policy plus authorized live proof, not a
read-only limitation.

**Operator Hermes agent and free-form bridge:** The operator gets exactly one
in-stack Hermes agent (`python/arclink_operator_agent.py`,
`DEFAULT_OPERATOR_AGENT_DEPLOYMENT_ID="operator"`,
`DEFAULT_OPERATOR_AGENT_RUNTIME="control-stack"`). It is a first-class
Control Node Compose identity, not a tenant ArcPod; `assert_single_operator_agent`
enforces the one-agent invariant and `ensure_operator_agent_deployment` refuses
to create a second. Free-form operator chat (any message that is not a Raven
command) routes to that one agent via `enqueue_operator_agent_turn`, which
stamps `operator_turn` and delivers through the existing `public-agent-turn`
notification worker; the gateway-bridge worker replies asynchronously. This
module is control-DB-only (it queues and resolves; it never runs Docker or SSH)
and is `ARCLINK_OPERATOR_AGENT_ENABLED`-gated. A live reply depends on a routable
in-stack Hermes gateway (`PG-HERMES` territory). When no live operator agent
exists, the webhook falls back to the Raven control intro.

**Ownership:**

| Area | Owner module | Notes |
| --- | --- | --- |
| Inventory machines | `arclink_inventory.py` | Operator-owned machine records, provider metadata, ASU sizing, and the optional link to an admitted fleet host |
| Fleet hosts | `arclink_fleet.py` | Hostname, region, region tier, placement priority, tags, capacity slots, drain flag, status, and last health state |
| Fleet reconciliation | `arclink_fleet.py` | Reports inventory/host registry orphans and writes audit warnings without repairing or deleting rows |
| Placement | `arclink_fleet.py` | Active placement is one row per deployment; load increments on placement |
| Admin action execution | `arclink_action_worker.py` | Claims queued `arclink_action_intents`, resolves the deployment's active placement, records attempts, and dispatches to the selected host executor |
| Operator action execution | `arclink_enrollment_provisioner.py` | Root maintenance loop drains the `operator_actions` table (`host_upgrade`/`pin_upgrade`), routing Docker-mode upgrades through `operator-upgrade-broker` |
| Operator chat control | `arclink_operator_raven.py` | Queues real audited mutations (`pod_repair`, `rollout` -> `arclink_action_intents`; `host_upgrade`, `pin_upgrade` -> `operator_actions`) only after verified operator identity plus `confirm` or the operator approval code; broad read surface |
| Operator agent | `arclink_operator_agent.py` | One in-stack `control-stack` Hermes identity (one-agent invariant) plus a free-form chat bridge via the `public-agent-turn` worker |
| Rollouts | `arclink_rollout.py` | Generic rollout model (version tag, wave count, pause/fail/rollback) plus the ArcPod-update planner/materializer/record-only batch executor |
| Operator read model | `arclink_dashboard.py` | `build_scale_operations_snapshot()` powers the admin API route; `ARCLINK_ADMIN_ACTION_SUPPORT` owns the action-readiness matrix |

**Assumptions:**

- The executor remains fake unless `ArcLinkExecutorConfig.live_enabled` is set
  by the operator path.
- For deployment-targeted actions, the control DB is the routing source of
  truth. The action worker uses the deployment's latest active placement to
  construct a host-specific executor; if the action does not target a
  deployment, or no active placement exists, it falls back to the injected
  executor path.
- Remote fleet execution requires `ARCLINK_EXECUTOR_ADAPTER=ssh`,
  `ARCLINK_EXECUTOR_MACHINE_MODE_ENABLED=1`, an explicit
  `ARCLINK_EXECUTOR_MACHINE_HOST_ALLOWLIST`, and a non-symlink SSH key file
  that is not group/world accessible when `ARCLINK_FLEET_SSH_KEY_PATH` is set.
- Action metadata, fleet metadata, rollout waves, and rollback plans must be
  secret-free. Secret-looking material is rejected before persistence.
- Rollback plans for rollouts must include `preserve_state_roots`; state roots
  and vault data are not disposable rollout artifacts.
- Placement is deterministic and capacity-based, not a general scheduler.
- Inventory machines and fleet hosts are deliberately separate registries.
  Orphan reconciliation reports drift for operator review; it does not infer a
  repair, remove capacity, or rewrite machine links.

**Fleet schema foundations:**

The control schema includes proof-gated foundations for later fleet enrollment
and health automation:

- `arclink_inventory_machines.enrollment_id`, `machine_fingerprint`,
  `attested_at`, `audit_trail_chain`, and `provider_billing_ref`.
- `arclink_fleet_hosts.region_tier`, `placement_priority`, and
  `last_health_state`.
- `arclink_fleet_enrollments` for single-use enrollment-token state.
- `arclink_fleet_host_probes` for liveness, capacity, and inventory probe
  results.
- `arclink_fleet_audit_chain` for machine lifecycle audit-chain records.

These tables and columns are additive. Enrollment token mint/callback handling
and periodic probing are implemented; live two-host fleet proof remains
Operator proof-gated.

Remote worker addressing is private-mesh first. Control install/reconfigure
generates the Control Node WireGuard keypair in private state, records the
public key/endpoint, writes the control interface config, publishes a
WireGuard-bound private control URL, and opens only the configured WireGuard UDP
port when `ufw` or `firewalld` is already active.
Register production workers with a WireGuard/private-mesh `ssh_host` plus
`wireguard_private_ip`; ArcPods placed on those hosts render against the
selected worker's private tunnel address and derive control API/router URLs from
`ARCLINK_CONTROL_PRIVATE_BASE_URL` or `ARCLINK_WIREGUARD_CONTROL_URL` unless
explicit public control URLs are configured. Worker join appends the fleet SSH
key without replacing `authorized_keys`, changing `sshd_config`, or changing
port 22. Tailscale can remain an access overlay/domain alternative through
`tailscale_dns_name`, but it is not the preferred production dependency. Remote
ArcPods do not join the control-node Docker network and require a remote
`ARCLINK_FLEET_SHARE_HUB_URL` so the Captain shared folder does not split across
worker-local disks.

**Read scale state:**

```bash
curl -s -H "Cookie: arclink_admin_session=..." \
  http://localhost:8900/api/v1/admin/scale-operations | python3 -m json.tool
```

The response includes `fleet_capacity`, `placements`, `stale_actions`,
`recent_action_attempts`, `last_executor_result`, and `active_rollouts`.

**Process queued actions manually in a no-secret environment:**

```bash
PYTHONPATH=python python3 - <<'PY'
from arclink_control import Config, connect_db, ensure_schema
from arclink_action_worker import process_arclink_action_batch
from arclink_executor import ArcLinkExecutor, ArcLinkExecutorConfig

conn = connect_db(Config.from_env())
ensure_schema(conn)
executor = ArcLinkExecutor(ArcLinkExecutorConfig(live_enabled=False))
print(process_arclink_action_batch(conn, executor=executor, batch_size=10))
PY
```

**Recover stale running actions:**

```bash
PYTHONPATH=python python3 - <<'PY'
from arclink_control import Config, connect_db, ensure_schema
from arclink_action_worker import recover_stale_actions

conn = connect_db(Config.from_env())
ensure_schema(conn)
print(recover_stale_actions(conn, stale_threshold_seconds=3600))
PY
```

**Runbook checks before live worker automation:**

1. Confirm fleet hosts are registered with realistic `capacity_slots`.
2. Drain a host before planned maintenance; do not place new deployments there.
3. Verify `/api/v1/admin/scale-operations` shows stale actions and recent
   attempts before enabling any recurring worker.
4. For deployment restart/reprovision/teardown actions, confirm the deployment
   has exactly the expected active placement before starting a live worker.
5. Review fleet orphan audit rows as drift signals, not as automatic repair
   instructions.
6. Keep rollout rollback plans state-preserving; destructive cleanup remains a
   separately confirmed executor/admin action.

## 11. Host Readiness

**Module:** `python/arclink_host_readiness.py`

Run pre-deployment checks without mutating providers:

```bash
PYTHONPATH=python python3 -c "
import json
from arclink_host_readiness import run_readiness
result = run_readiness()
print(json.dumps(result.to_dict(), indent=2))
"
```

Checks Docker, Docker Compose, ports, writable state root, required env vars,
secret presence (names only), and ingress strategy. Returns machine-readable
JSON with pass/fail per check.

## 12. Provider Diagnostics

**Module:** `python/arclink_diagnostics.py`

Run secret-safe provider credential checks:

```bash
PYTHONPATH=python python3 -c "
import json
from arclink_diagnostics import run_diagnostics
result = run_diagnostics()
print(json.dumps(result.to_dict(), indent=2))
"
```

Reports which billing, ingress, model-provider (Chutes), bot, and Docker
credentials are present or missing. Credential values are never returned. Live
connectivity checks require `ARCLINK_E2E_LIVE=1`.

## 13. Live Journey and Evidence

**Modules:** `python/arclink_live_journey.py`, `python/arclink_live_runner.py`,
`python/arclink_evidence.py`

Plan or run the ordered live journeys:

```bash
bin/arclink-live-proof --json
bin/arclink-live-proof --journey workspace --live --json
bin/arclink-live-proof --journey external --live --json
ARCLINK_E2E_LIVE=1 PYTHONPATH=python python3 -m pytest tests/test_arclink_e2e_live.py -v
```

The hosted journey covers onboarding/provider readiness. The workspace journey
covers Docker upgrade/health plus Drive, Code, and Terminal browser proof. The
external journey covers named provider and live-service rows: Stripe,
Telegram, Discord, Hermes dashboard landing, Chutes provider OAuth, Chutes
provider usage, Chutes key CRUD, Chutes account registration, Chutes balance
transfer, Notion shared-root SSOT, Cloudflare, and Tailscale. Without
credentials, all steps skip or report missing environment names cleanly.
Evidence template at
`docs/arclink/live-e2e-evidence-template.md`.

## 14. Native Hermes Workspace Plugins

**Ownership:**

| Surface | Owner | Current status |
| --- | --- | --- |
| Drive | `plugins/hermes-agent/drive/` | Functional first-generation file manager |
| Code | `plugins/hermes-agent/code/` | Functional first-generation editor/git surface |
| Terminal | `plugins/hermes-agent/terminal/` | Managed-pty persistent sessions with same-origin SSE streaming and bounded polling fallback |
| Install/enable | `bin/install-arclink-plugins.sh` | Installs all default workspace plugins and prunes legacy aliases |
| Docker repair | `bin/arclink-docker.sh` | Repairs dashboard mounts and refreshes managed plugins |

**Assumptions:**

- Workspace plugins are additive Hermes dashboard plugins. Do not patch Hermes
  core for Drive, Code, or Terminal behavior.
- Plugin status contracts are capability-driven and secret-free. They may
  return access URLs, usernames, mount labels, roots, editor mode, and backend
  names; they must not return tokens, passwords, deploy keys, OAuth material, or
  raw `.env` values.
- Drive and Code are mounted into deployment-owned roots. In Docker
  deployments, Drive uses `/srv/vault` and Code uses `/workspace`.
- Terminal exposes managed shell access only behind the authenticated Hermes
  dashboard and keeps unrestricted root blocked unless explicitly allowed.

**Default install:**

```bash
bin/install-arclink-plugins.sh "$REPO_DIR" "$HERMES_HOME"
```

With no explicit plugin list, the installer enables:

```text
drive
code
terminal
arclink-theme
arclink-managed-context
```

It also removes legacy aliases from the Hermes home and plugin config:

```text
arclink-code-space
arclink-knowledge-vault
arclink-code
arclink-drive
arclink-terminal
```

**Docker repair and refresh:**

Docker reconcile and health call helper paths that:

1. Ensure deployed `hermes-dashboard` services mount the Hermes home, vault,
   and workspace.
2. Ensure `VAULT_DIR`, `DRIVE_ROOT`, and
   `CODE_WORKSPACE_ROOT` are present in the dashboard environment.
3. Re-run `managed-context-install` for each deployment stack that has that
   service.
4. Recreate `hermes-dashboard` so plugin changes are loaded.
5. Refresh `arclink_service_health` rows from `docker compose ps --format json`.

Use the canonical Control Node path rather than editing generated Compose by hand:

```bash
./deploy.sh control reconfigure
./deploy.sh control health
```

## Crew Training

Crew Training is a Captain-facing flow in the dashboard and Raven public bot
(`/train-crew`). It captures the Captain role, mission, treatment preference,
Crew preset, and Crew capacity, then previews a Crew Recipe before confirmation.

Confirmation writes one active `arclink_crew_recipes` row for the Captain,
archives any prior active row, writes an audit entry, and projects an additive
SOUL overlay into each local Pod identity context at
`state/arclink-identity-context.json` when that Hermes home exists. It does not
rewrite memories or sessions and does not restart the Hermes gateway. Remote or
unavailable local projection targets return a skipped reason for operator
review.

Live recipe generation uses the existing scoped provider boundary only when a
Captain/Pod has an allowed scoped secret reference and budget. Without that
credential boundary, Crew Training truthfully runs in deterministic fallback
mode: "Live recipe generation requires configured provider credentials. Using
preset-only overlay." Provider output containing URLs, shell commands, or
instruction override patterns is rejected and retried before falling back.

Focused checks:

```bash
python3 tests/test_arclink_crew_recipes.py
python3 tests/test_arclink_api_auth.py
python3 tests/test_arclink_hosted_api.py
python3 tests/test_arclink_public_bots.py
cd web && npm test && npm run lint && npm run build
```

**Tailscale path-mode app publishing:**

When `ARCLINK_INGRESS_MODE=tailscale` and
`ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY=path`, Docker health/reconcile
assigns stable tailnet HTTPS ports starting at
`ARCLINK_TAILNET_SERVICE_PORT_BASE` for per-deployment Hermes Dashboard access. It stores
those ports and root-mounted `access_urls` in deployment metadata, then calls
`tailscale serve --https=<port>` to publish the local dashboard proxy when the
host has the Tailscale CLI. Drive, Code, and Terminal are dashboard-native tabs
under that same root URL.

If the host lacks the Tailscale CLI, publishing is skipped with a warning and
health continues. The deployment metadata remains the source for the dashboard
URL read model when publishing succeeds.

**Focused checks:**

```bash
python3 -m py_compile \
  plugins/hermes-agent/drive/dashboard/plugin_api.py \
  plugins/hermes-agent/code/dashboard/plugin_api.py \
  plugins/hermes-agent/terminal/dashboard/plugin_api.py
python3 tests/test_arclink_plugins.py
python3 tests/test_arclink_docker.py
node --check plugins/hermes-agent/drive/dashboard/dist/index.js
node --check plugins/hermes-agent/code/dashboard/dist/index.js
node --check plugins/hermes-agent/terminal/dashboard/dist/index.js
```

---

## General Operational Notes

- **All boundaries fake by default.** No live calls unless env vars are set.
- **No secrets in logs.** Structured events redact sensitive fields.
- **Idempotency.** Provisioning, rollback, and admin actions use stable keys.
- **Audit trail.** All mutations write to `arclink_audit_log` table.
- **Tests.** Run `python3 tests/test_arclink_*.py` to verify all boundaries.
