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

Hosted user sessions expose credential handoff state through
`GET /api/v1/user/credentials` and acknowledge storage through
`POST /api/v1/user/credentials/acknowledge`. These responses use masked secret
references only; acknowledgement hides the handoff from future user API reads
and records audit/event rows.

The reconciler invokes `bin/sync-dashboard-user-passwords.py` inside the
provisioner context so it can read deployment state roots and update hashes.

**Linked resources:** Cross-user Drive/Code sharing is modeled as read-only
share grants. A user session creates a pending grant for a recipient, Raven
queues an owner approval notification when the owner has a linked Telegram or
Discord channel, and the owner can approve or deny it with button callbacks.
Active Telegram buttons use `/raven approve {grant_id}` and `/raven deny
{grant_id}` so they cannot collide with the active agent's slash namespace;
the backward-compatible `/share-approve {grant_id}` and `/share-deny
{grant_id}` forms remain owner-scoped. The recipient accepts an approved grant with their own user
session, and accepted resources are listed at
`GET /api/v1/user/linked-resources`. Drive and Code expose a read-only `Linked`
root when `ARCLINK_LINKED_RESOURCES_ROOT` or the plugin fallback projection
exists. Accepted grants create living linked-resource projections backed by a
manifest, owner revoke removes the projection and manifest entry, and Drive/Code
allow recipient copy/duplicate into the recipient's own Vault or Workspace
without allowing reshare from the `Linked` source. Right-click browser
share-link UI remains disabled until a live ArcLink browser broker or approved
Nextcloud-backed adapter exists, and live bot delivery proof remains
credential-gated.

If the owner has no linked Telegram or Discord channel, share creation still
persists the grant as `pending_owner_approval`, but no Raven notification is
queued. The API response reports `owner_notification.queued=false` with a
reason of `no_public_channel` when no public channel exists, or
`unsupported_public_channel` when stored channel metadata is not a usable
Telegram or Discord target. Operators should treat either as a waiting state,
not a delivery failure: link or repair the owner's public channel and request
the share again, or have the owner approve or deny the pending grant through
their authenticated hosted API session.

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
| `CLOUDFLARE_API_TOKEN` | Scoped API token for zone writes |
| `CLOUDFLARE_ZONE_ID` | Target zone |

**Tailscale-mode env vars:**
| Var | Purpose |
|-----|---------|
| `ARCLINK_TAILSCALE_DNS_NAME` | Control or worker node FQDN |
| `ARCLINK_TAILSCALE_HTTPS_PORT` | Funnel/Serve HTTPS port, default `443` |
| `ARCLINK_TAILSCALE_NOTION_PATH` | Public Notion webhook path |
| `ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY` | `path` by default; `subdomain` only when proven |
| `ARCLINK_TAILNET_SERVICE_PORT_BASE` | First HTTPS port for per-deployment Hermes/files/code tailnet apps in Tailscale path mode |

**Fake mode:** Default. Records and intent are persisted to SQLite but no
provider API calls are made. Drift reconciliation reports local-only state.

**Domain live mode:** Enabled when both `CLOUDFLARE_API_TOKEN` and
`CLOUDFLARE_ZONE_ID` are set. Creates real DNS records. Teardown deletes records
from Cloudflare.

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

**Rollback:**
- `_plan_rollback_apply(plan)` generates a rollback intent.
- Destructive state deletes (`_is_destructive_state_delete`) are separately
  gated and audit-logged.
- Unhealthy services are identified via `_rollback_unhealthy_services`.
- Idempotent: same execution key returns the same plan without re-execution.

**Troubleshooting:**
- Render fails: check the deployment intent has all required service blocks.
- Start fails: verify Docker socket access and that the project name is unique.
- Secret ref rejected: ensure values use `file:/run/secrets/...` or env-file
  patterns, never raw key material.

## 4. Chutes Provider

**Modules:** `python/arclink_chutes.py`, `python/arclink_chutes_live.py`,
`python/arclink_chutes_oauth.py`

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
- Rollback never deletes volumes without explicit `destructive: true` flag.
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
`python/arclink_rollout.py`, `python/arclink_dashboard.py`

Scale operations cover fleet capacity, deployment placement, queued admin
action execution, rollout waves, and operator visibility. The design is
SQLite-first and fake-by-default so operators can inspect and rehearse the
workflow without live provider credentials.

**Ownership:**

| Area | Owner module | Notes |
| --- | --- | --- |
| Fleet hosts | `arclink_fleet.py` | Hostname, region, tags, capacity slots, drain flag, status |
| Placement | `arclink_fleet.py` | Active placement is one row per deployment; load increments on placement |
| Admin action execution | `arclink_action_worker.py` | Claims queued intents, records attempts, dispatches to executor/local transitions |
| Rollouts | `arclink_rollout.py` | Version tag, wave count, current wave, pause/fail/rollback state |
| Operator read model | `arclink_dashboard.py` | `build_scale_operations_snapshot()` powers the admin API route |

**Assumptions:**

- The executor remains fake unless `ArcLinkExecutorConfig.live_enabled` is set
  by the operator path.
- Action metadata, fleet metadata, rollout waves, and rollback plans must be
  secret-free. Secret-looking material is rejected before persistence.
- Rollback plans for rollouts must include `preserve_state_roots`; state roots
  and vault data are not disposable rollout artifacts.
- Placement is deterministic and capacity-based, not a general scheduler.

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
4. Keep rollout rollback plans state-preserving; destructive cleanup remains a
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

Use the canonical Docker path rather than editing generated Compose by hand:

```bash
./deploy.sh docker reconcile
./deploy.sh docker health
```

**Tailscale path-mode app publishing:**

When `ARCLINK_INGRESS_MODE=tailscale` and
`ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY=path`, Docker health/reconcile
assigns stable tailnet HTTPS ports starting at
`ARCLINK_TAILNET_SERVICE_PORT_BASE` for per-deployment Helm/Hermes. It stores
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
