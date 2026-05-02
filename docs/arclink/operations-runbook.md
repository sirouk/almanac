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

## 2. Ingress / DNS (Cloudflare)

**Module:** `python/arclink_ingress.py`

**Operations:**
| Function | Purpose |
|----------|---------|
| `desired_arclink_dns_records(prefix, base_domain, target)` | Compute expected DNS shape |
| `provision_arclink_dns(...)` | Create/update records (fake default) |
| `reconcile_arclink_dns(...)` | Detect drift between desired and actual |
| `teardown_arclink_dns(...)` | Remove records for a deployment |
| `render_traefik_dynamic_labels(...)` | Generate Traefik Docker labels |

**Env vars (live mode):**
| Var | Purpose |
|-----|---------|
| `CLOUDFLARE_API_TOKEN` | Scoped API token for zone writes |
| `CLOUDFLARE_ZONE_ID` | Target zone |

**Fake mode:** Default. Records are persisted to SQLite but no Cloudflare API
calls are made. Drift reconciliation reports local-only state.

**Live mode:** Enabled when both `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ZONE_ID`
are set. Creates real DNS records. Teardown deletes records from Cloudflare.

**Drift detection:**
```python
from arclink_ingress import reconcile_arclink_dns
drift = reconcile_arclink_dns(conn, deployment_id=..., raw_cloudflare=...)
# drift.missing, drift.extra, drift.mismatched
```

**Troubleshooting:**
- Drift false positives: ensure the raw Cloudflare export is current.
- Provision fails: check token scope includes `Zone:DNS:Edit` for the zone.

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

---

## General Operational Notes

- **All boundaries fake by default.** No live calls unless env vars are set.
- **No secrets in logs.** Structured events redact sensitive fields.
- **Idempotency.** Provisioning, rollback, and admin actions use stable keys.
- **Audit trail.** All mutations write to `arclink_audit_log` table.
- **Tests.** Run `python3 tests/test_arclink_*.py` to verify all boundaries.
