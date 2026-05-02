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
| `ARCLINK_DEFAULT_PRICE_ID` | `price_arclink_starter` | Default Stripe price |

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

**Fake mode:** Default. Records and intent are persisted to SQLite but no
provider API calls are made. Drift reconciliation reports local-only state.

**Domain live mode:** Enabled when both `CLOUDFLARE_API_TOKEN` and
`CLOUDFLARE_ZONE_ID` are set. Creates real DNS records. Teardown deletes records
from Cloudflare.

**Tailscale live mode:** `deploy.sh control install` keeps the control node
Dockerized, then uses the host Tailscale CLI as the network edge. It publishes
the web/API/Notion routes on the selected HTTPS port and does not require
Cloudflare DNS credentials.

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

**Module:** `python/arclink_chutes.py`

**Operations:**
| Function | Purpose |
|----------|---------|
| `parse_chutes_models(payload)` | Parse model catalog from Chutes API |
| `validate_default_chutes_model(...)` | Confirm selected default is valid |

**Key lifecycle (executor-managed):**
- Create: `_fake_chutes_key_id(deployment_id, secret_ref, generation)` in fake mode.
- Rotate: new generation increments the key ID.
- Revoke: teardown removes key state for the deployment.
- Per-deployment key state tracked in `arclink_chutes_keys` table.

**Env vars (live mode):**
| Var | Purpose |
|-----|---------|
| `CHUTES_API_KEY` | Owner key for model catalog and key management |

**Fake mode:** Default. Model catalog uses a built-in fixture. Key operations
write to SQLite only.

**Troubleshooting:**
- Model catalog empty: check `CHUTES_API_KEY` is set for live catalog fetch.
- Key creation fails: verify the deployment has an active entitlement.

## 5. Stripe Boundary

**Module:** `python/arclink_entitlements.py`

**Operations:**
| Function | Purpose |
|----------|---------|
| `process_stripe_webhook(conn, event, ...)` | Ingest and apply webhook events |
| `detect_stripe_reconciliation_drift(conn)` | Compare local vs Stripe state |

**Webhook processing flow:**
1. Record raw event in `arclink_stripe_webhooks`.
2. Extract user/subscription/onboarding IDs from event + metadata.
3. Map event type to entitlement transition.
4. Apply entitlement change and mark processed.
5. On failure: mark replayable with error detail.

**Env vars:**
| Var | Purpose |
|-----|---------|
| `STRIPE_SECRET_KEY` | Live API calls (portal links, subscription reads) |
| `STRIPE_WEBHOOK_SECRET` | Signature verification on incoming webhooks |

**Billing portal:** User requests via `POST /api/v1/user/portal`. Requires
active user session + CSRF. Fake mode returns a placeholder URL.

**Reconciliation:** `detect_stripe_reconciliation_drift` compares local
entitlement/subscription records against what Stripe reports. Drift items
surfaced via `GET /api/v1/admin/reconciliation`.

**Troubleshooting:**
- Webhook signature fails: verify `STRIPE_WEBHOOK_SECRET` matches the endpoint
  secret in the Stripe dashboard, not the API key.
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

**Modules:** `python/arclink_live_journey.py`, `python/arclink_evidence.py`

Run the ordered live journey (requires credentials):

```bash
ARCLINK_E2E_LIVE=1 PYTHONPATH=python python3 -m pytest tests/test_arclink_e2e_live.py -v
```

Without credentials, all steps skip cleanly. Evidence template at
`docs/arclink/live-e2e-evidence-template.md`.

---

## General Operational Notes

- **All boundaries fake by default.** No live calls unless env vars are set.
- **No secrets in logs.** Structured events redact sensitive fields.
- **Idempotency.** Provisioning, rollback, and admin actions use stable keys.
- **Audit trail.** All mutations write to `arclink_audit_log` table.
- **Tests.** Run `python3 tests/test_arclink_*.py` to verify all boundaries.
