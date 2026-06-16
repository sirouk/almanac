# CANON-19 — Hermes Workspace & Dashboard

## PIECE
This piece is the **read-model + provisioning surface for the Hermes workspace and the ArcLink dashboards**. It owns exactly five tracked files:
- `python/arclink_dashboard.py` (2411 lines) — the user dashboard read model (`read_arclink_user_dashboard`), the admin dashboard read model (`read_arclink_admin_dashboard`), admin-action queueing (`queue_arclink_admin_action`), operator/scale aggregation (`build_operator_snapshot`, `build_scale_operations_snapshot`, `control_node_provisioning_readiness`, `admin_action_execution_readiness`), per-deployment URL derivation (`_deployment_urls`), and the backup-deploy-key staging rail (`request_arclink_backup_deploy_key`, `record/request_arclink_backup_write_check*`).
- `python/arclink_dashboard_auth_proxy.py` (1394 lines) — a standalone, threaded, HS256 signed-session reverse proxy that fronts a local-only Hermes dashboard backend; CSRF gate, mount-prefix rewriting, backend session-token scraping, managed-lifecycle 409 intercept, crew-switcher/deeplink injection, login-throttle.
- `python/arclink_nextcloud_access.py` (264 lines) — provisioning-side `occ`-shelling helper to create/reset/delete a Nextcloud user in group `arclink-users`, gated entirely behind `ENABLE_NEXTCLOUD=1`.
- `python/arclink_headless_hermes_setup.py` (686 lines) — headless seeder for a per-agent `HERMES_HOME`: seeds the provider runtime (codex/anthropic/custom/api-key), writes `SOUL.md`, identity-context JSON, prefill messages, and toggles ArcLink skills/plugins in `config.yaml`.
- `python/arclink_skill_enablement.py` (313 lines) — per-agent application of Trainer-approved skill-enablement intents into one `HERMES_HOME/config.yaml` via targeted line surgery (no YAML re-dump).

The dashboard read models are pure read-only aggregators (over the control SQLite DB) consumed by the hosted API / product surface / Operator Raven; the auth proxy is a separate runtime process; nextcloud/headless/skill modules are provisioning-time lanes. There is NO web/HTML rendering of the dashboard in this piece beyond the auth-proxy login form — the dashboard SPA is the Hermes backend (CANON-30 plugins) and the Next.js app (CANON-03).

## INPUT CONTRACT (code-verified)

### arclink_dashboard.py
- `read_arclink_user_dashboard(conn, *, user_id, deployment_id="", recent_limit=10)` — `arclink_dashboard.py:1678`. Raises `KeyError(user_id)` if no `arclink_users` row (`:1685-1687`). `deployment_id` optionally narrows the deployment filter (`:1690-1692`). Caller: `arclink_api_auth.py:1181,1671,1844` (user session-gated) and `arclink_product_surface.py:458,735`.
- `read_arclink_admin_dashboard(conn, *, channel="", status="", deployment_id="", user_id="", since="", recent_limit=25)` — `:1825`. All filters lowered/stripped (`:1836-1842`); `recent_limit` clamped to 1..100 by `_limit` (`:786-787`). Caller: `arclink_api_auth.py:1650,4536,4548` (admin session-gated), `arclink_product_surface.py:560,737`.
- `queue_arclink_admin_action(conn, *, admin_id, action_type, target_kind, target_id, reason, idempotency_key, metadata=None, action_id="")` — `:2321`. Validation: non-blank admin (`:2339`); `action_type` must be in `ARCLINK_ADMIN_ACTION_TYPES` (`:2341`); worker support must equal `"wired"` (`:2343`) — i.e. the four `pending_not_implemented` types (suspend/unsuspend/force_resynth/rotate_bot_key) raise; `target_kind` in `ARCLINK_ADMIN_TARGET_KINDS` and non-blank `target_id` (`:2345`); per-action `target_kinds` allowlist (`:2347-2352`); non-blank reason (`:2353`); non-blank idempotency key (`:2355`). `metadata` is passed through `_safe_json` which calls `reject_secret_material` (`:2357,777-778`). Caller: `arclink_api_auth.py:4891` (admin session + CSRF + `confirm is True` + two rate limits at `:4880-4890`); also `arclink_operator_raven.py:1126,1856`.
- `request_arclink_backup_deploy_key(conn, *, user_id, deployment_id, key_staging_dir)` — `:1196`. Asserts deployment belongs to user (`:1217-1218`); requires a recorded private repo in session metadata (`:1220-1222`); stages an ed25519 key via `ssh-keygen` only if not already present (`:1226-1230`). Caller: `arclink_api_auth.py:1283` (user session + CSRF + ownership recheck at `:1277-1282`).
- `request_arclink_backup_write_check(conn, *, user_id, deployment_id)` — `:1361`. Ownership check (`:1377-1378`); always records `failed_closed` (delegates to `record_arclink_backup_write_check_failed_closed`, `:1379-1383`). Caller: `arclink_api_auth.py:1312`.
- `build_operator_snapshot(*, env=None, skip_ports=True, docker_binary="docker")` — `:526`. Read-only; no DB. Caller: `arclink_hosted_api.py:2062` (admin session-gated).
- `build_scale_operations_snapshot(conn, *, stale_action_threshold_seconds=3600, rollout_target_version="", rollout_batch_size=None)` — `:591`. Caller: `arclink_hosted_api.py:2073` (admin session-gated).
- `control_node_provisioning_readiness(conn, *, env=None)` — `:305`. Read-only fleet eligibility model. Callers: `arclink_dashboard.py:702,2309`, `arclink_operator_raven.py:450`.
- `admin_action_execution_readiness(env=None)` — `:258`. Probes executor adapter + optional action-worker liveness file + ssh probes. Callers: `:701,2311`, `arclink_operator_raven.py:444`.

### arclink_dashboard_auth_proxy.py
- CLI `parse_args()` (`:1365`): `--listen-host` (default 127.0.0.1), `--listen-port` (required), `--target` (required), `--access-file` (default ""), `--realm` (default "Hermes"), `--no-auth` flag. `main()` (`:1376`) builds a `ProxyHandler` subclass with class attrs and serves forever via `ThreadingHTTPServer`.
- Per-request inputs: `Cookie`, `Authorization`, `Origin`/`Referer`/`Host`, `X-Forwarded-Prefix`/`X-Forwarded-Prefixes`, request body (size-capped). Login POST body parsed as JSON or form (`_handle_login_post`, `:1045`).
- Access file (`load_access`, `:173`) is the trust input: keys `username`, `password`, `session_secret`, `sso_session_secret`, `sso_subject`, `sso_cookie_domain`, `deployment_id`, `prefix`, `crew_dashboards`, `dashboard_auth_revoked_before`, `dashboard_session_revoked_before`, `dashboard_sso_revoked_before`. Unreadable/malformed → `{}` (fail-closed: no username/password → 401).

### arclink_nextcloud_access.py
- `sync_nextcloud_user_access(cfg, *, username, password, display_name="")` — `:174`. `cfg` is `arclink_control.Config`. Validates username via `safe_slug` (`:153-157`, raises `ValueError` if blank), password non-blank + no `\n`/`\r` (`:160-166`). Returns `{enabled:False,...}` if `ENABLE_NEXTCLOUD!=1` (`:181-182`). Caller: `arclink_enrollment_provisioner.py:1065,1124`.
- `delete_nextcloud_user_access(cfg, *, username)` — `:231`. Caller: `arclink_ctl.py:1121`.

### arclink_headless_hermes_setup.py
- `main()` (`:634`): argparse `--provider-spec-json`, `--secret-path`, `--bot-name`, `--agent-title`, `--unix-user`, `--user-name`, `--identity-only`, `--prefill-only` (SUPPRESS, aliased to identity-only at `:651`). Always seeds identity first (`:650`); when not identity-only, requires both `--provider-spec-json` and `--secret-path` (`:665-666`). Caller: `arclink_enrollment_provisioner.py:1397,1573`, `bin/refresh-agent-install.sh:535,557`, `bin/install-deployment-hermes-home.sh:218,248`, `arclink_agent_process_helper.py:654`.
- Provider dispatch (`:669-677`): `openai-codex` → `_seed_openai_codex`; `anthropic` → `_seed_anthropic`; `is_custom` truthy → `_seed_custom_provider`; else `_seed_api_key_provider`. Each `raise SystemExit` on incomplete spec/secret.

### arclink_skill_enablement.py
- `apply_skill_enablement(hermes_home)` — `:220`. Reads `state/arclink-academy-approved-skills.json` (`:224`, must be a JSON list of objects with `skill_id`/`source_id`; unsafe ids with `/ \ ..` rejected, `:210-212`), parses `config.yaml` `skills.disabled`/`external_dirs` without a YAML lib (`:92`), removes only discoverable approved skills from `disabled` (`:264-269`). Returns a receipt dict.
- `main(argv=None)` — `:275`. `--hermes-home` (default `$HERMES_HOME`). Skips (status `skipped`) if unset or not a dir (`:283-290`). Caller: `bin/user-agent-refresh.sh:177` (systemd `arclink-user-agent-refresh.timer`, `OnUnitActiveSec=4h` per `bin/install-agent-user-services.sh:317`, plus a `.path` activation-trigger watcher at `:340-349`).

## OUTPUT CONTRACT (code-verified)

### Dashboard read models (pure dicts, no DB writes)
- `read_arclink_user_dashboard` returns `{sections, user, entitlement, wrapped, share_inbox, academy_training, deployments[]}` (`:1797-1814`). Each deployment card carries `access.urls`, `billing`, `bot_contact`, `model`, `notion_setup`, `backup_setup`, `academy_training`, `freshness`, `sections[]`, `service_health[]`, `recent_events[]` (`:1764-1795`). Model credential state is `secret_ref_pending` by default (`:1741`) and only enriched for the `chutes` provider via `evaluate_chutes_deployment_boundary(...).to_public()` (`:1743-1763`) — no secret values, only state names. SECRET-SAFE.
- `read_arclink_admin_dashboard` returns `{filters, sections, onboarding_funnel, users, subscriptions, deployments, service_health, dns_drift, provisioning_jobs, provisioning_readiness, action_intents, action_execution_readiness, wrapped, events, audit_rows, audit, recent_failures, active_sessions}` (`:2299-2318`). Users include `stripe_customer_id` (`:2179`) — a customer id, not a card/secret.

### Side-effecting outputs (DB writes / files / subprocess)
- `queue_arclink_admin_action`: idempotent INSERT into `arclink_action_intents` with status `queued` (`:2376-2395`), an audit row `admin_action:<type>` (`:2396-2405`), backfills `audit_id` (`:2406-2409`), `conn.commit()` (`:2410`). Idempotency-key reuse with a different (admin/type/target) tuple raises (`:2365-2371`); same tuple returns the existing row (`:2372`). **PRODUCER for the action worker (CANON-14).**
- `request_arclink_backup_deploy_key`: `BEGIN IMMEDIATE` if not already in a txn (`:1207-1209`), `ssh-keygen -t ed25519` into `<key_staging_dir>/<sha256(deployment)[:24]>/arclink-agent-backup-ed25519{,.pub}` with `0o600`/`0o644` (`:1090-1112`), UPDATE `arclink_deployments.metadata_json` (`:1243-1250`), audit `backup_deploy_key_staged` (`:1251-1265`), commit. Returns `_deployment_backup_setup(...)` (no private key, only public + `private_key_storage:"server_side_only"`).
- `record_arclink_backup_write_check_failed_closed`: UPDATE metadata to `backup_github_write_check:"failed_closed"`, `backup_activation:"not_active"` (`:1306-1323`), audit + event `backup_write_check_failed_closed` (`:1325-1351`). **Always records failed_closed; never runs git.**
- `build_scale_operations_snapshot` calls `plan_arcpod_update_rollout` (CANON-14 dry-run planner) with `mode:"dry_run"`; on `ArcLinkRolloutError` returns a `status:"blocked"` plan (`:711-741`). Read-only (no rows materialized here).

### Auth proxy outputs
- On valid login (`_handle_login_post`, `:1080-1090`): 303 to `next_path`, clears all session cookies, sets SSO cookie (if configured) and the scoped session cookie. Cookie attrs `HttpOnly; Path=<mount or />; SameSite=Lax; Secure` (`:725-735`). Session token is HS256-JWT-shaped, audience `hermes-dashboard`, 12h TTL, random `nonce` per token (`:585-607`).
- Proxy responses (`_proxy`, `:1164`): forwards to backend, strips hop-by-hop + `authorization`/`cookie`/`X-Hermes-Session-Token` inbound (`:1207-1211`), forces `Accept-Encoding: identity` to backend (`:1215`), injects scraped `X-Hermes-Session-Token` only after the signed-session gate (`:1221-1223`). Rewrites HTML/CSS/JSON only when status 200, GET, no content-encoding, content-type matches, and content-length ≤ rewrite buffer (`:1251-1261`).
- 403 `"Cross-origin dashboard mutation rejected.\n"` on CSRF failure (`:1180-1181`). 409 `{"arclink_managed":true,...}` for managed-lifecycle endpoints when enabled (`:1183-1200`). 413 on oversized body/response (`:996-1000,1324-1325`). 502 on backend OSError (`:1291-1299`).

### Nextcloud / headless / skill outputs
- `sync_nextcloud_user_access`: shells `php /var/www/html/occ user:add|user:resetpassword` as uid `33:33` in container, password via `OC_PASS` env (never argv, never logged) (`:200-219`). Returns `{enabled,synced,username,display_name,created,group}`.
- `_seed_arclink_identity`: atomically writes `HERMES_HOME/SOUL.md`, `state/arclink-identity-context.json`, `state/arclink-prefill-messages.json` (`:482,517-520,563`), and edits Hermes `config.yaml` via `save_config`: removes ArcLink skills from `skills.disabled`/`platform_disabled` (`:570-584`), removes `arclink-managed-context` from `plugins.disabled` (`:586-591`), sets `prefill_messages_file` and `agent.prefill_messages_file` (`:593-599`). Prints the identity paths as JSON.
- `apply_skill_enablement`: atomically rewrites `config.yaml` removing exact `skills.disabled` items (line surgery, `:118-148`), writes receipt to `state/arclink-skill-enablement-applied.json` (`:302-305`). `effective_at:"next_session"`. Fail-closed: missing skill stays `disabled` and is reported `missing` (`:255-256`).

## TOUCH POINTS

### Env vars read
- Dashboard: `ARCLINK_EXECUTOR_ADAPTER`, `ARCLINK_ADMIN_ACTION_REQUIRE_WORKER_READY`, `ARCLINK_EXECUTOR_MACHINE_MODE_ENABLED`/`ARCLINK_ACTION_WORKER_SSH_ENABLED`, `ARCLINK_ACTION_WORKER_SSH_HOST`/`ARCLINK_LOCAL_FLEET_SSH_HOST`, `ARCLINK_EXECUTOR_MACHINE_HOST_ALLOWLIST`/`ARCLINK_ACTION_WORKER_SSH_HOST_ALLOWLIST`, `ARCLINK_FLEET_SSH_KEY_PATH`, `ARCLINK_CONTROL_PROVISIONER_ENABLED`, `ARCLINK_DOCKER_JOB_STATUS_DIR`/`STATE_DIR`/`ARCLINK_STATE_DIR`/`ARCLINK_PRIV_DIR`, `ARCLINK_LIVE_EVIDENCE_TEMPLATE`, `ARCLINK_ROLLOUT_TARGET_VERSION`/`ARCLINK_UPGRADE_TARGET_VERSION`, `ARCLINK_FLEET_PLACEMENT_STRATEGY`, and the `_deployment_urls` ingress/tailscale env set (`ARCLINK_INGRESS_MODE`, `ARCLINK_TAILSCALE_DNS_NAME`, `ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY`, `:797-805`), plus the Notion webhook URL env (`ARCLINK_NOTION_WEBHOOK_PUBLIC_URL`, `ARCLINK_TAILSCALE_*`, `:914-942`).
- Auth proxy: `ARCLINK_DASHBOARD_MANAGED_LIFECYCLE_CONTROLS` (`:416-417`), `ARCLINK_DASHBOARD_PROXY_LOGIN_FAILURE_LIMIT`/`_WINDOW_SECONDS` (`:358-373`), `ARCLINK_DASHBOARD_PROXY_MAX_LOGIN_BODY_BYTES`/`_MAX_REQUEST_BODY_BYTES`/`_REWRITE_BUFFER_BYTES` (`:965-987`).
- Nextcloud: `ENABLE_NEXTCLOUD` (`config_env_value`, `:19-20`), `ARCLINK_NEXTCLOUD_CONTAINER_NAME`, `ARCLINK_NAME`, `ARCLINK_DOCKER_MODE` (`:23-31`).
- Headless: `HERMES_HOME`, `ARCLINK_PREFIX`, `ARCLINK_DEPLOYMENT_ID`, `ARCLINK_HERMES_URL`/`ARCLINK_DASHBOARD_URL`, `ARCLINK_FILES_URL`, `ARCLINK_CODE_URL`, `ARCLINK_NOTION_CALLBACK_URL`, `ARCLINK_NOTION_ROOT_URL`/`ARCLINK_SSOT_NOTION_*`, `ARCLINK_ORG_*` (via `config_env_value`), and the org-skill-library env set `ARCLINK_SHARED_SKILLS_DIR`, `ARCLINK_AGENT_VAULT_DIR`/`VAULT_DIR`, `ARCLINK_FLEET_SHARED_ROOT`/`DRIVE_FLEET_SHARED_ROOT`/`CODE_FLEET_SHARED_ROOT`, `HOME` (`:125-146`).
- Skill enablement: `HERMES_HOME` only.

### DB tables (read unless noted; schema in arclink_control.py)
- `arclink_users` (`control.py:991`-area; read at `dashboard.py:1685,2183,2194`).
- `arclink_deployments` (`control.py:991`; read `1693,1212,1290,1372`; **UPDATE metadata_json** at `1243-1250,1318-1323`).
- `arclink_onboarding_sessions` (`control.py:1309`; read `946,1568,1617`), `arclink_onboarding_events` (read `1589`).
- `arclink_service_health` (`control.py:1224`; read `1525,1963,2154`).
- `arclink_events` (read `1548,2014,2043`), `arclink_audit_log` (read `2070`; **append** via `append_arclink_audit`).
- `arclink_subscriptions` (read `1704,1932`), `arclink_share_grants` (`control.py:1052`; read `1639`).
- `arclink_action_intents` (`control.py:1371`; read `624,2104,2222`,`2359-2360`; **INSERT/UPDATE** `2376-2409`).
- `arclink_action_attempts` (`control.py:2381`; read `653`), `arclink_deployment_placements` (`control.py:2369`; read `666`), `arclink_rollouts` (`control.py:2395`; read `673`).
- `arclink_provisioning_jobs`, `arclink_user_sessions`, `arclink_admin_sessions`, `arclink_admins`, `rate_limits`, `notion_index_documents` (read for counts, `dashboard.py:1985,2196-2222,898`).

### Files / paths
- Backup key staging dir `<key_staging_dir>/<sha256(dep)[:24]>/arclink-agent-backup-ed25519{,.pub}` (`dashboard.py:1081-1087`).
- Action-worker liveness file `<status_dir>/control-action-worker.json` (`dashboard.py:457`).
- Evidence template `docs/arclink/live-e2e-evidence-template.md` (`dashboard.py:576`).
- Access file `HERMES_HOME/state/arclink-web-access.json` (proxy + producers).
- Headless writes `HERMES_HOME/SOUL.md`, `state/arclink-identity-context.json`, `state/arclink-prefill-messages.json`, `config.yaml`.
- Skill enablement reads `state/arclink-academy-approved-skills.json`, edits `config.yaml`, writes `state/arclink-skill-enablement-applied.json`.

### Sockets/ports/subprocess
- Auth proxy binds `--listen-host:--listen-port` (3210 default via launcher), connects to `--target` backend (13210 default) via `http.client.HTTPConnection` (`:1138,1231`). Launcher `bin/run-hermes-dashboard-proxy.sh:162-174` starts `hermes dashboard --insecure --no-open` on backend then runs the proxy.
- Nextcloud: `docker/podman exec -u 33:33 <container> php /var/www/html/occ ...` (or `runuser`+`podman-compose exec`) (`nextcloud_access.py:66-101,134-146`); preflight `docker/podman compose version` (`:41-61`).
- `ssh-keygen -q -t ed25519 -N "" -C ... -f ...` (`dashboard.py:1095-1100`).

### Secrets handling
- All read models pass user/admin payloads through `reject_secret_material`/`json_dumps_safe` only on **write** paths (`queue_arclink_admin_action` metadata at `:2357`); read paths emit only state names/ids. Backup public key validated by regex + secret-reject (`:1050-1058`).
- Nextcloud password via `OC_PASS` env, validated no-newline, never argv/logged.
- Auth proxy never persists the access-file secret; session/SSO secrets HMAC-only; `_token_secret` falls back to `sha256(realm\0user\0password)` when `session_secret` blank (`:86-98`).

## CODE-PATH TRACE (user dashboard, end-to-end)
1. `arclink_api_auth.py:1181` authenticates a user session and calls `read_arclink_user_dashboard(conn, user_id=target_user)`.
2. `dashboard.py:1685` fetches the `arclink_users` row (KeyError if absent).
3. `:1693-1701` selects this user's `arclink_deployments` (optionally one).
4. `:1715-1717` loads wrapped reports and `crew_academy_status` (CANON-17 seam).
5. Per deployment: `_service_health` (`:1720`→`:1524`), `_deployment_onboarding` (`:1721`→`:1567`), parse `metadata_json` (`:1722`).
6. `_deployment_urls(prefix, base_domain, metadata)` (`:1724`→`:790`) derives access URLs — calls `arclink_access_urls` (CANON-02 adapter) for tailscale/domain ingress, or returns stored `metadata.access_urls` filtered to `https://` (`:831-847`).
7. `_deployment_notion_setup` (`:1725`→`:959`) reads session metadata + `get_setting` Notion tokens (existence only) + `_notion_index_available` (`:897`).
8. `_deployment_backup_setup` (`:1726`→`:1115`) projects backup state from deployment metadata (no writes).
9. Chutes branch (`:1743-1763`) calls `evaluate_chutes_deployment_boundary(...).to_public()` (CANON-16 seam) for credential/budget state names.
10. `_user_dashboard_sections` (`:1783`→`:1387`) assembles the 16 named sections; `plugin_links` derive Drive/Code/Terminal URLs from `urls` (`:1402-1410`).
11. Returns the assembled dict to api_auth → `ArcLinkApiResponse(200, payload)` (`api_auth.py:1181`). No DB mutation anywhere in this path.

## CROSS-PIECE CONTRACTS (both ends verified)

1. **Dashboard read models → Hosted API / api_auth (CANON-02).** Contract: plain JSON-serializable dicts. Producer `dashboard.py:1797-1814,2299-2318`; consumer `api_auth.py:1181,1650` wraps verbatim in `ArcLinkApiResponse`. BOTH-ENDS-VERIFIED **yes**.

2. **`queue_arclink_admin_action` → action worker (CANON-14).** Contract: a row in `arclink_action_intents` with `status='queued'`, `action_type`, `target_kind/id`, `metadata_json`, `idempotency_key`, `audit_id`. Producer INSERT `dashboard.py:2376-2409`; consumer `arclink_action_worker.py:461` selects `FROM arclink_action_intents` and `:2251` selects `status='running'`. BOTH-ENDS-VERIFIED **yes** (same table/columns/status enum).

3. **`queue_arclink_admin_action` caller gate (CANON-02/CANON-14 Raven).** Contract: admin session + CSRF + `confirm is True` + rate limits. Consumer-of-producer at `api_auth.py:4880-4901`; Operator Raven at `operator_raven.py:1124-1126,1854-1856` passes its own admin_id. BOTH-ENDS-VERIFIED **yes**.

4. **`build_operator_snapshot` → host readiness/diagnostics/journey/evidence (CANON-23/CANON-08).** Contract: dict from `run_readiness().to_dict()`, `run_diagnostics().to_dict()`, `build_journey()` step objects (`.name`, `.required_env`). Producer-side imports `dashboard.py:537-539`; consumer `hosted_api.py:2062`. BOTH-ENDS-VERIFIED **partial** — verified `build_operator_snapshot` consumes `step.required_env`/`step.name` (`:548-550`) and `.to_dict()`; the exact internal shapes of readiness/diagnostics belong to CANON-23 and were not re-opened here.

5. **`_deployment_urls` → `arclink_access_urls` (CANON-02 adapters).** Contract: `arclink_access_urls(prefix, base_domain, ingress_mode, tailscale_dns_name, tailscale_host_strategy, tailnet_service_ports)` returns a `{role: https-url}` dict including `dashboard/files/code/hermes`. Producer-side call `dashboard.py:821,840,869`; the `{"dashboard","files","code","hermes"} <= set(...)` guard at `:838,855` proves the consumer expects those exact keys. BOTH-ENDS-VERIFIED **partial** — the key set is asserted in this file; the adapter body lives in CANON-02.

6. **Auth proxy ← access file producer (`arclink_agent_access.py` / `arclink_sovereign_worker.py` / `install-deployment-hermes-home.sh`).** Contract: JSON with `username`, `password`, `session_secret`, optional `crew_dashboards`/`sso_*`/`dashboard_*_revoked_before`. Producer `arclink_agent_access.py:517-552` writes `username/password/session_secret/auth_scheme:"signed-session"` + revoked-before keys; `arclink_sovereign_worker.py:1787` injects `crew_dashboards`. Consumer `auth_proxy.load_access:173-193` reads exactly these keys. BOTH-ENDS-VERIFIED **yes for username/password/session_secret/crew_dashboards/revoked-before**; **NO producer in this repo writes `sso_session_secret`/`sso_subject`** (grep returns only the proxy consumer) → SSO path is dormant by default (see DRIFT).

7. **Headless setup ← enrollment provisioner (CANON-08).** Contract: argv `--provider-spec-json <json> --secret-path <file> --bot-name --agent-title --unix-user --user-name`, JSON stdout. Producer `arclink_enrollment_provisioner.py:1404-1423`; consumer `headless_hermes_setup.main:634-682`. Provisioner reads stdout as JSON (`provisioner.py:1432`). BOTH-ENDS-VERIFIED **yes**.

8. **Skill enablement ← Academy approved-skills file (CANON-17) and refresh lane (CANON-31).** Contract: `state/arclink-academy-approved-skills.json` is a JSON list of `{skill_id|source_id, ...}`. Consumer `skill_enablement.py:189-217`. Invoked by `bin/user-agent-refresh.sh:177`. BOTH-ENDS-VERIFIED **partial** — consumer shape verified; the writer of `arclink-academy-approved-skills.json` (Academy mirror) is CANON-17 and not opened here.

9. **Nextcloud access ← enrollment provisioner / ctl (CANON-08/CANON-14).** Contract: `sync_nextcloud_user_access(cfg, username=, password=, display_name=)`. Producer `enrollment_provisioner.py:1065,1124`; `delete_…` from `ctl.py:1121`. BOTH-ENDS-VERIFIED **yes**.

10. **Backup deploy-key staging → backup scripts (CANON-22).** Contract: metadata keys `backup_deploy_key_public`, `backup_deploy_key_private_ref` (`server_state:agent-backup-deploy-key:<digest>`), `backup_github_write_check`, `backup_activation`. Producer `dashboard.py:1231-1242`. Consumer = `bin/backup-*` (CANON-22), not opened here. BOTH-ENDS-VERIFIED **no** (producer-only; the script that reads the private ref is in CANON-22).

## CODE vs COMMENT/DOC/NAME DRIFT
1. **SSO cookie path is dormant.** The proxy implements a full `arclink_dash_sso` HS256 SSO cookie (`:609-619,674-693`), but no producer in this repo writes `sso_session_secret`/`sso_subject` into the access file (`rg` shows only the consumer). So `_make_sso_token` returns `""` (`:612-613`) and `_valid_sso_cookie` always returns False in practice. The signed single-session cookie is the only live auth. Prior doc 07 does not mention the SSO path at all (it predates it) — INFO-level drift, code is newer than the doc.
2. **`request_arclink_backup_write_check` name implies a check; it only records failed_closed.** It never invokes git — it unconditionally calls `record_arclink_backup_write_check_failed_closed` (`:1379-1383`). Name vs body drift; the comment-level `local_contract` (`:115`) is honest about it but the function name is misleading.
3. **Prior doc 07 scoped this subsystem to plugins + auth_proxy + nextcloud_access only.** It never covers `arclink_dashboard.py` (the read models), `arclink_headless_hermes_setup.py`, or `arclink_skill_enablement.py` — those are this CANON-19 piece's core and were undocumented by the prior ground-truth. Coverage gap, not a contradiction.
4. **Doc 07 says auth proxy cookie is "HttpOnly; SameSite=Lax; Secure".** Verified true (`:727`), but it omits that the cookie `Path` is the mount-prefix (`_cookie_path`, `:768-769`), not always `/`. Minor.
5. **Doc 07: "`--no-auth` flag exists to disable auth while keeping the response helpers."** Verified (`:1372,1385,696-697`). Accurate.
6. **Skill-enablement docstring says it is "invoked by `bin/user-agent-refresh.sh`, which runs every 4h and on curator refresh signals" (`:7-9`).** Verified: `bin/user-agent-refresh.sh:177` calls it; timer `OnUnitActiveSec=4h` (`install-agent-user-services.sh:317`) plus an activation `.path` watcher (`:340-349`). Accurate.
7. **`ARCLINK_USER_DASHBOARD_SECTIONS` (16 entries, `:181`) vs `_user_dashboard_sections` (16 built sections).** The top-level `sections` list (`:1798`) is derived from the constant tuple, while card-level `sections` come from `_user_dashboard_sections`; both list the same 16 — no drift, but the two are independently maintained (fragile).

## ADVERSARIAL SELF-CHECK
1. **"SSO is dead by default."** Falsified if any provisioning writer (outside this repo's grep, e.g. a hosted operator-only deploy template) injects `sso_session_secret`. I only grepped `python/` and `bin/`; a config template or external orchestrator could set it. Confidence: medium.
2. **"`queue_arclink_admin_action` is the sole producer for `arclink_action_intents`."** Falsified by any other INSERT into that table (Raven/rollout). I confirmed Raven calls `queue_arclink_admin_action` (not a raw INSERT) at `operator_raven.py:1126`, but `arclink_rollout.py`/`action_worker.py` may INSERT directly. I did not exhaustively grep all INSERTs. Confidence: medium.
3. **"Backup write-check never runs git."** Falsified if a different module (CANON-22 backup scripts via the action worker `backup_write_check` operation) performs the real git write-check and writes `verified`. The dashboard path here only records failed_closed; the worker-side live path is out of this piece. Confidence: high for this file, low for the whole system.
4. **"Read models never write the DB."** `read_arclink_user_dashboard`/`read_arclink_admin_dashboard` issue only SELECTs (verified by inspection), but `request_arclink_backup_deploy_key`/`queue_arclink_admin_action` (also in this file) do write. The claim holds only for the two `read_*` functions. Confidence: high.
5. **"`_deployment_urls` only ever emits https URLs."** The stored-urls filter requires `startswith("https://")` (`:836,854`), but the tailscale/domain branches build `f"https://{host}/u/{prefix}"` from env-derived `host` — a malicious `ARCLINK_TAILSCALE_DNS_NAME` could inject. Operator-controlled env, but worth noting. Confidence: medium.

## OPEN FOR CODEX FEDERATION
1. Confirm whether ANY producer (repo, hosted infra template, or operator runbook) writes `sso_session_secret`/`sso_subject` into `arclink-web-access.json`. If none, the entire SSO cookie machinery in the proxy is unreachable and should be flagged dead/aspirational.
2. Verify the action-worker consumer end of seam #2: does the worker correctly interpret every `action_type` this module allows (e.g. `academy_apply`, `rollout`, `backup_write_check`) and the `metadata_json` shape it queued? Cross-check `arclink_action_worker.py` dispatch table vs `ARCLINK_ADMIN_ACTION_SUPPORT.operation_kind`.
3. Verify seam #10: which CANON-22 backup script reads `backup_deploy_key_private_ref` (`server_state:agent-backup-deploy-key:<digest>`) and how the private key is materialized from the `server_state:` reference, and whether `backup_activation:"active"` can ever be set (this module forces `not_active` unless `github_write_check=="verified"`, `:1141-1142`).
4. Independently confirm the auth proxy's backend-token scraping (`window.__HERMES_SESSION_TOKEN__`, `:56,1158`) matches what the Hermes dashboard backend actually emits in its index HTML (Hermes upstream, CANON-30 territory).
5. Confirm `apply_skill_enablement`'s YAML line-surgery (`remove_skills_from_disabled`, `:118`) is robust against flow-style lists / tab indentation — it explicitly only handles block-style under `skills:` and otherwise fails closed; verify no real `config.yaml` uses flow style.

## RISKS (severity-ranked, code-cited)
- **MEDIUM** — Auth proxy `_token_secret` fallback derives the signing key from `sha256(realm\0username\0password)` when `session_secret` is blank (`auth_proxy.py:90-98`). If an access file is written without `session_secret`, dashboard session tokens are forgeable by anyone who learns the (already-sensitive) password; security depends on producers always setting `session_secret`. The producer does (`arclink_agent_access.py:480`), but a hand-written/legacy access file would silently downgrade.
- **MEDIUM** — `request_arclink_backup_deploy_key` runs `ssh-keygen` and writes a private key to `key_staging_dir` (`dashboard.py:1090-1112`) on a user-session-gated API call (`api_auth.py:1283`). The private key persists on disk under operator control; rotation/cleanup is not in this module. A stale staging dir leaks an unused deploy key.
- **MEDIUM** — `build_scale_operations_snapshot` reads `os.environ` directly for `ARCLINK_ROLLOUT_TARGET_VERSION`/`ARCLINK_FLEET_PLACEMENT_STRATEGY` (`dashboard.py:705,748`) even though it accepts a `conn`; the admin snapshot is not env-injectable, so test/staging env can leak into an admin read model. Low blast radius (read-only), but inconsistent with the env-injected `build_operator_snapshot`.
- **LOW** — `read_arclink_admin_dashboard` exposes `stripe_customer_id` (`dashboard.py:2179`) in the admin users list. Not a secret, but a PII/identifier surface; relies entirely on the admin-session gate at the caller (`api_auth.py:1650`).
- **LOW** — Auth proxy login throttle is **process-local** (`_LOGIN_FAILURES` module dict, `:66`); with multiple proxy processes or a restart, the failure budget resets. Mitigated by per-deployment isolation but not a shared store.
- **LOW** — `_deployment_urls` and `_control_notion_webhook_public_url` build URLs from operator env (`ARCLINK_TAILSCALE_DNS_NAME` etc., `:798,926-942`); a bad env value flows into dashboard `access.urls` and the SOUL/identity prefill. Operator-trust boundary, not user-controllable.
- **INFO** — SSO cookie path (`auth_proxy.py:609-619,674-693`) is effectively dead code given no in-repo producer writes the SSO secret.
- **INFO** — `_action_worker_liveness_probe` trusts a JSON status file's `finished_at`/`interval_seconds` (`dashboard.py:457-491`); a stale or spoofed file flips `queueable`. The file is operator-written, so trust-boundary-internal.

## VERDICT
This piece **provably does its job** as a read-model + provisioning surface. Load-bearing strengths, all code-verified: (1) the two dashboard read models are strictly SELECT-only and secret-safe — they emit credential *state names*, never values, and only enrich the Chutes provider via a public-boundary projection; (2) `queue_arclink_admin_action` is a correct idempotent producer for the action-worker contract with full validation (wired-only, target-kind allowlist, reason+key required, audit row) and BOTH ends of that seam match on table/columns/status; (3) the auth proxy is a genuine HS256 signed-session boundary with HttpOnly/Secure cookies, Origin/Referer CSRF, login throttling, fail-closed access loading, and a managed-lifecycle 409 intercept; (4) the headless seeder and skill-enablement lane are atomic-write, fail-closed, and never overwrite local Hermes skills (line-surgery only). Real weaknesses: the SSO cookie subsystem is dormant (no producer writes its secret), `request_arclink_backup_write_check` is misnamed (records failed_closed, never checks), the backup deploy-key private material persists on disk with no rotation in this module, and `build_scale_operations_snapshot` leaks process env into an admin read model. The dominant open item remains live `PG-HERMES` proof of the actual Hermes dashboard browser experience, which is outside this piece's read-model/proxy scope.

## COVERAGE NOTE
At the boundary, this piece owns: the dashboard *read models* and admin-action *queueing*, the auth *proxy process*, the *occ*-shelling Nextcloud user lane, the headless *HERMES_HOME seeder*, and the *skill-enablement applier*. Deliberately left to adjacent pieces: the action-worker *execution* of queued intents (CANON-14), the live *rollout planner* internals (CANON-14), `arclink_access_urls`/`ArcLinkApiResponse` transport (CANON-02), the Chutes boundary evaluator (CANON-16), `crew_academy_status` / approved-skills *writer* (CANON-17), the Hermes dashboard SPA + plugins behind the proxy (CANON-30), the Nextcloud *compose topology* (CANON-25), backup *script* consumers of the staged deploy key (CANON-22), and the access-file *writers'* full schema (CANON-08/CANON-14).
