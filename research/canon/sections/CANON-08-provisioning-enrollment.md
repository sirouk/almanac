# CANON-08 — Provisioning & Enrollment

## PIECE
CANON-08 is the **provisioning engine + enrollment plane**: it turns a paid, entitlement-cleared
deployment into a rendered ArcPod compose intent, places & applies it, admits remote fleet
machines via signed enrollment tokens, runs no-mutation host preflight, and dispatches confirmed
operator host-mutation actions (upgrade / pin-upgrade) over an HMAC-signed broker rail. It owns
exactly seven tracked files:

- `python/arclink_provisioning.py` (1953 lines) — the **intent renderer**: `render_arclink_provisioning_intent`
  (the canonical per-deployment compose+env+DNS+traefik+secret-refs intent), `render_arclink_state_roots`,
  `render_arclink_provisioning_dry_run` (job-tracked `docker_dry_run`), `plan_arclink_provisioning_rollback`
  (planning-only `docker_rollback_plan`, NO host mutation), `validate_no_plaintext_secrets`, identity-context projection.
- `python/arclink_enrollment_provisioner.py` (3352 lines) — the **headless single-machine onboarding loop**
  AND the **DISSECT P2 operator-action dispatcher**: signs+POSTs `run_operator_upgrade`/`run_pin_upgrade`
  to the operator-upgrade-broker (CANON-15) in Docker mode (`_operator_upgrade_broker_request`,
  `:297-349`), or runs `deploy.sh`/`component-upgrade.sh` bare-metal. CLI `main()` (`:3330`).
- `python/arclink_fleet_enrollment.py` (993 lines) — fleet enrollment tokens (`arcfleet_v1.<id>.<nonce>.<sig>`
  HMAC-SHA256), worker attestation (`consume_fleet_enrollment`), the prev-hash audit chain, re-attest, secret rotation.
- `python/arclink_host_readiness.py` (214 lines) — no-mutation host preflight (docker/compose/ports/state-root/env/secret-presence/ingress). CLI `arclink-host-readiness`.
- `python/arclink_sovereign_worker.py` (2536 lines) — the Sovereign fleet ArcPod loop (`control-provisioner`): claims `provisioning_ready` deployments, places them, renders intent, applies via the injectable executor, runs teardown.
- `python/arclink_access.py` (57 lines) — pure SSH-access-record builder (`build_arclink_ssh_access_record`); the source of the two SSH strategy constants.
- `python/arclink_agent_access.py` (563 lines) — per-agent web-access state (port allocation, atomic state file, tailscale serve publish/clear, `wait_for_http` health probe, `ensure_web_runtime`).

All seven listed files exist and are tracked. No clearly-belonging file was found missing. NOTE: the
prior research doc `research/ground-truth/02-provisioning-fleet-ingress.md` and DISSECT.md P2 are CLAIMS
cross-checked below; several were refuted (see DRIFT).

## INPUT CONTRACT (code-verified)

### arclink_provisioning.py
- `render_arclink_provisioning_intent(conn, *, deployment_id, base_domain="", edge_target="", state_root_base="/arcdata/deployments", ingress_mode="", tailscale_dns_name="", tailscale_host_strategy="", tailscale_notion_path="", env=None) -> dict` (`:1424-1436`). Loads `arclink_deployments` (`_load_deployment`, raises `KeyError` if missing, `:195-199`) + `arclink_users` (`:202-204`). `ingress_mode` cleaned by `_clean_ingress_mode` → only `{domain,tailscale}` (`:702-708`); `tailscale_host_strategy` cleaned to `path` only — `subdomain` rejected (`_clean_tailscale_strategy`, `:709-719`). Callers: `arclink_sovereign_worker._apply_deployment` (`:1149,:1169`), dry-run/migration.
- `render_arclink_state_roots(*, deployment_id, prefix, state_root_base="/arcdata/deployments") -> dict[str,str]` (`:399-422`) — pure path builder; `_safe_segment` raises on empty (`:98-102`).
- `render_arclink_provisioning_dry_run(conn, *, deployment_id, …, idempotency_key="", env=None)` (`:1808`) — job-keyed `docker_dry_run`; default key `arclink:provisioning:dry-run:<deployment_id>` (`:1822`).
- `plan_arclink_provisioning_rollback(conn, *, deployment_id, failed_job_id, idempotency_key="")` (`:1911`) — requires the named job exist AND be `failed` (`:1922-1925`), else `KeyError`/`ArcLinkProvisioningError`.
- `validate_no_plaintext_secrets(value, *, path="$")` (`:1398`) — recurses dict/list; uses `arclink_secrets_regex` predicates; raises `ArcLinkSecretReferenceError`.

### arclink_enrollment_provisioner.py (dispatcher)
- `_operator_upgrade_broker_request(operation, payload, *, timeout_seconds=7200) -> dict` (`:297-302`). `operation` is literally `"run_operator_upgrade"` (`:378`) or `"run_pin_upgrade"` (`:465`). `payload` = `{"log_path": str, "upstream": {…}}` (`_brokered_operator_payload`, `:352-356`); pin adds `install_items` (`:462-463`). Raises `RuntimeError` before any I/O if url OR token is falsy (`:305-309`).
- `_run_pending_operator_actions(conn, cfg)` (`:2322`) — pops `get_pending_operator_action(action_kind="upgrade")`; **confirmed-source gate**: `_operator_action_has_confirmed_source` requires `request_source.lower() in {"operator-raven"}` (`:2292-2297`), else `_fail_unconfirmed_operator_action` (`:2334-2337`).
- `_run_pending_pin_upgrade_actions(conn, cfg)` (`:2440`) — pops `action_kind="pin-upgrade"` with `reclaim_stale_running_seconds=0` (`:2448`); same confirmed-source gate (`:2451-2453`); `token=requested_target`; `get_pin_upgrade_action_payload(conn, token)` → `None` fails the action (`:2457-2470`).
- Only callers of `_operator_upgrade_broker_request` are the two in-file sites (`:377`, `:465`), both passing dict payloads and the default timeout. CLI `main()` is the unguarded top of the call stack (`:3330-3348`, no try/except).

### arclink_fleet_enrollment.py
- `mint_fleet_enrollment(conn, *, created_by_user_id, ttl_seconds=3600, secret="", enrollment_id="", now_iso="") -> dict` (`:156`). Secret resolved from arg or `ARCLINK_FLEET_ENROLLMENT_SECRET` (`_resolve_secret`, `:56-63`), raises if blank. Token = `arcfleet_v1.<flenr_…>.<b64url nonce>.<b64url HMAC-SHA256>` (`:169`).
- `consume_fleet_enrollment(conn, *, token, payload, secret="", actor="worker-bootstrap", source_ip="")` (`:525`). `_require_pending_enrollment` (`:92-124`): parses token (`:82-89`), `hmac.compare_digest` on sig (`:101`) AND on `token_hash` (`:110`), lazily flips expired pending → `expired` (`:115-121`), rejects non-`pending` (`:122-123`). Then validates **every** body field with bounded regexes: fingerprint `_FINGERPRINT_RE` `[A-Za-z0-9_.:=+/@-]{16,256}` (`:35,:332-336`), hostname `_HOST_VALUE_RE` (`:37,:339-347`), WireGuard pubkey/cidr/interface/endpoint/firewall, ssh-user, fleet-share abs paths/public key, provider ∈ `{local,manual,hetzner,linode}` (`:595`), capacity bounded by `ARCLINK_FLEET_ENROLLMENT_MAX_CAPACITY_SLOTS` default 64 (`:430-439`).
- `reattest_inventory_machine`, `revoke_fleet_enrollment`, `expire_pending_fleet_enrollments`, `record_fleet_enrollment_secret_rotation`, `verify_fleet_audit_chain`, `append_fleet_audit_chain_entry` (event ∈ 8-value allowlist, `:485`).

### arclink_host_readiness.py
- `run_readiness(*, state_root=None, ports=None, env=None, docker_binary="docker", compose_runner=None, skip_ports=False) -> ReadinessResult` (`:164`). Injectable `compose_runner` for tests. `ready = all(c.ok for c in checks if not c.name.startswith("secret_"))` (`:183`) — **secret-presence checks are excluded from the roll-up**.

### arclink_sovereign_worker.py
- `process_sovereign_batch(conn, *, worker, executor=None) -> list[dict]` (`:467`). `worker` from `load_worker_config(cfg, env=None)` (`:245`). Disabled short-circuits (`:473-474`). Apply selection **excludes** `metadata_json LIKE '%"operator_agent"%'` (`:565`).
- `process_sovereign_deployment`, `process_sovereign_teardown`, `_apply_deployment`, `_teardown_deployment` — internal; executor is the injectable `ArcLinkExecutor` (CANON-11).

### arclink_access.py / arclink_agent_access.py
- `build_arclink_ssh_access_record(*, username, hostname, strategy="cloudflare_access_tcp") -> SshAccessRecord` (`:28`). Rejects `raw_http`/`ssh_over_http` (`:37-38`), http(s) hostnames (`:39-40`), unknown strategies (`:41-42`), empty user/host (`:43-44`).
- `ensure_access_state(conn, cfg, *, agent_id, unix_user, hermes_home, uid) -> dict` (`:454`) — allocates/preserves dashboard backend+proxy ports avoiding `_used_ports`/`_listening_ports`; writes 0600 state file owned by the agent uid/gid.

## OUTPUT CONTRACT (code-verified)

### Intent renderer (`render_arclink_provisioning_intent`, return `:1701-1782`)
Returns a dict: `deployment{…}`, `state_roots`, `environment` (the big `deployment_env` map of ~80 `ARCLINK_*`/`HERMES_*`/`NEXTCLOUD_*`/`QMD_*` keys, **secret values only as `*_REF`/`*_FILE`**, `:1559-1675`), `secret_refs`, `compose{services,secrets,networks}`, `runtime_resolution`, `dns` (role→{hostname,record_type,target,proxied}), `traefik{labels}`, `access{urls,ssh}`, `integrations.notion`, `execution{ready,blocked_reason,entitlement_state,…}`. **`validate_no_plaintext_secrets(intent)` is the final gate before return (`:1781`)** — raises `ArcLinkSecretReferenceError` if any path that requires a secret-ref carries plaintext, or any value contains secret material. No DB write, no host mutation.
- `render_arclink_provisioning_dry_run`: writes `arclink_provisioning_jobs` (status walks `queued→running→succeeded`), `_record_health_placeholders` upserts `arclink_service_health` for all `ARCLINK_PROVISIONING_SERVICE_NAMES` (`:1785-1794`), timeline events `provisioning_rendered`/`provisioning_ready_for_execution`. Returns `{job_id, intent}`. Failure path transitions job → `failed` only if not terminal (`:1896-1908`), then re-raises.
- `plan_arclink_provisioning_rollback`: writes `arclink_provisioning_jobs` (`docker_rollback_plan`) with fixed action tuple `(stop_rendered_services, remove_unhealthy_containers, preserve_state_roots, leave_secret_refs_for_manual_review)` + `rollback_requested` event. **Performs NO host mutation** (`:1934-1953`).

### Dispatcher wire output (`_operator_upgrade_broker_request`)
HTTP `POST broker_url + "/v1/operator-upgrade"` (`:322`). Body = `json.dumps({**payload,"operation":operation}, sort_keys=True).encode()` — the EXACT bytes hashed at `:315` and sent at `:323`. Five headers (`:324-330`): `Content-Type`, `X-ArcLink-Operator-Upgrade-Broker-Token`, `-Timestamp` (`str(int(time.time()))`), `-Nonce` (`secrets.token_urlsafe(18)`), `-Signature` (`hmac-sha256(token, f"{timestamp}\n{nonce}\n{body_hash}")`). Read timeout `max(30,int(timeout_seconds))` default 7200 (`:334`). Returns `data["result"]` (dict) requiring `data["ok"] is True` (`:344-349`). Callers coerce `int(result.get("returncode"))` default 2 → `subprocess.CompletedProcess` (`:383-387`, `:468-472`). On `RuntimeError`: `_brokered_operator_failure` writes a refusal line to `log_path` and returns rc=2 (`:359-371`). Outer dispatcher: rc 0 → `finish_operator_action(status="completed")`; else `failed` + operator notification with `_tail_text` (`:2368-2427`).

### Fleet enrollment writes (`consume_fleet_enrollment`)
`register_inventory_machine` (status `pending`, `connectivity.ok=False`, `status=awaiting_control_probe`, `:651-668`); then UPDATE `arclink_inventory_machines` set `enrollment_id/machine_fingerprint/attested_at/last_probed_at` (`:670-677`); linked `arclink_fleet_hosts` set `degraded, drain=1, last_health_state='awaiting_control_probe'` (`:680-688`); UPDATE enrollment → `consumed` **guarded by `rowcount != 1` → raise** (`:689-698`, TOCTOU-safe); two audit-chain entries (`enrolled`, `verified`) + `audit_trail_chain`/`audit_ref` backlinks (`:699-740`); `append_arclink_audit` + `conn.commit()` (`:741-759`). Returns a public dict (no secret material, no token).

## TOUCH POINTS
- **Env (dispatch):** `ARCLINK_OPERATOR_UPGRADE_BROKER_URL` default `http://operator-upgrade-broker:8917` `.strip().rstrip("/")` (`enrollment:289-290`); `ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN` `.strip()` (`:293-294`); `ARCLINK_DOCKER_MODE` via `_docker_mode()` accepts `{1,true,yes}` (`:763-764`); `ARCLINK_UPSTREAM_DEPLOY_KEY_USER` straight from `os.environ` (`:283`); `ARCLINK_UPSTREAM_REPO_URL/BRANCH/DEPLOY_KEY_ENABLED/DEPLOY_KEY_PATH/KNOWN_HOSTS_FILE` via `cfg` (`:277-281`).
- **Env (fleet):** `ARCLINK_FLEET_ENROLLMENT_SECRET` (token HMAC, `:59`), `ARCLINK_FLEET_AUDIT_CHAIN_SECRET` falling back to enrollment secret (`:442-447`), `ARCLINK_FLEET_ENROLLMENT_MAX_CAPACITY_SLOTS` (`:436`), `ARCLINK_DB_PATH` (CLI).
- **Env (worker):** `ARCLINK_CONTROL_PROVISIONER_ENABLED`, `ARCLINK_INGRESS_MODE`, `ARCLINK_BASE_DOMAIN`, `ARCLINK_TAILSCALE_DNS_NAME`, `ARCLINK_EDGE_TARGET`, `ARCLINK_STATE_ROOT_BASE`, `CLOUDFLARE_ZONE_ID`, `ARCLINK_EXECUTOR_ADAPTER` (default `disabled`), `ARCLINK_CONTROL_PROVISIONER_BATCH_SIZE`, `ARCLINK_SOVEREIGN_PROVISION_MAX_ATTEMPTS`, `ARCLINK_SOVEREIGN_RUNNING_STALE_SECONDS`, `ARCLINK_REGISTER_LOCAL_FLEET_HOST`, `ARCLINK_LOCAL_FLEET_*`, `ARCLINK_SECRET_STORE_DIR`, `ARCLINK_SOVEREIGN_HANDOFF_REQUIRES_HEALTHY_SERVICES` (default 1), `ARCLINK_SOVEREIGN_HANDOFF_REQUIRES_HERMES_HOME_READY` (default 1) (`worker:245-282,1260,1271`).
- **Env (readiness):** required `ARCLINK_PRODUCT_NAME/BASE_DOMAIN/PRIMARY_PROVIDER` (`:22-26`); optional-secret presence-only `STRIPE_*/CLOUDFLARE_*/CHUTES_API_KEY/TELEGRAM_BOT_TOKEN/DISCORD_*` (`:28-38`); `ARCLINK_STATE_ROOT` default `/arcdata` (`:42,:114`).
- **Env (agent_access):** `ARCLINK_DOCKER_MODE` accepts `{1,true,yes,on}` (`:143` — note the extra `on` vs the dispatcher's set), `ARCLINK_DOCKER_HOST_PORT_PROBE_HOSTS`, `PATH` (`shutil_which`).
- **DB tables:** r/w `operator_actions` (schema `control.py:760-772`, incl. `request_source` `:765`), `arclink_provisioning_jobs` (`:1124-1136`), `arclink_service_health` (`:1224`), `arclink_inventory_machines` (`:1413-1435`), `arclink_fleet_enrollments` (`:2429-2439`), `arclink_fleet_audit_chain` (`:2450-2459`), `arclink_fleet_hosts`, `arclink_deployment_placements` (`:2369`), `arclink_dns_records` (`:1138`), `arclink_deployments`, `arclink_users`, `agents` (agent_access `:91-99`).
- **Sockets/ports:** dispatcher → plaintext `http://operator-upgrade-broker:8917`; readiness binds `0.0.0.0:{80,443,8080}` (`:107`); agent_access probes `host.docker.internal:<port>` and runs `ss`/`lsof`/`docker ps` (`:121,:150,:188`).
- **Subprocess argv:** readiness `[docker,compose,version]` (`:84-85`); agent_access `tailscale serve …`, `tailscale status --json`, `ss -ltnH`, `lsof`, `docker ps`, `uv pip install`, `npm ci/run build`; bare-metal dispatcher `deploy.sh`/`bin/component-upgrade.sh` (only when NOT docker-mode). **No subprocess on the Docker brokered path.**
- **Crypto/secrets:** `hmac.new(...sha256)` — dispatch signature (`enrollment:316`), fleet token sig (`fleet:73`), token hash (`fleet:78`), audit-chain (`fleet:471`). `secrets.token_urlsafe`/`token_bytes`/`token_hex` for nonces/ids. `hmac.compare_digest` used for ALL fleet sig/hash/fingerprint compares (`fleet:101,110,648,889,901`). Secret-store materialization in `SovereignSecretResolver` (worker `:122`).
- **Locks:** `fcntl` imported in worker (`:12`) for the file lock; SQLite `BEGIN IMMEDIATE` in placement (CANON-20 `arclink_fleet.place_deployment`). Atomic file writes via `os.replace`/`tempfile.mkstemp` (access `:52-66`, provisioning `:207-221`).
- **External services:** operator-upgrade-broker (CANON-15), Cloudflare DNS / Docker Compose via executor (CANON-11), tailscale CLI, Hermes runtime (uv/npm).

## CODE-PATH TRACE — confirmed operator upgrade, Docker mode (the P2 dispatch)
1. `main()` (`enrollment:3330`) → no try/except → `_run_pending_operator_actions(conn, cfg)` (`:3348`).
2. `_fail_stale_running_operator_actions(action_kind="upgrade", stale_seconds=1800)` reaps rows stuck `running` past `auto_provision_stale_before_iso` (`:2323-2329`, `:613-652`).
3. `get_pending_operator_action(action_kind="upgrade")`; `None` → delegate to pin loop & return (`:2330-2333`).
4. **Confirmed-source gate:** `_operator_action_has_confirmed_source(action)` requires `request_source=="operator-raven"` (`:2334`, `:2295-2297`). Fail → `_fail_unconfirmed_operator_action` marks `failed` + operator notice (`:2300-2319`), then pin loop, return.
5. `mark_operator_action_running(action_id, note, log_path=upgrade-{id}.log)` — row → `running` BEFORE the call (`:2342-2347`).
6. `_run_host_upgrade(cfg, log_path)` (`:2366`); `_docker_mode()` true (`:391`) → `_run_brokered_host_upgrade` (`:392`).
7. `_run_brokered_host_upgrade`: `args=["operator-upgrade-broker","run_operator_upgrade"]`; `_operator_upgrade_broker_request("run_operator_upgrade", _brokered_operator_payload(cfg, log_path))` (`:375-380`).
8. `_operator_upgrade_broker_request`: read url+token (`:303-304`); falsy → `RuntimeError` pre-I/O (`:305-309`). `body=dict(payload); body["operation"]=…; body_bytes=json.dumps(sort_keys=True).encode()` (`:310-312`). `timestamp/nonce/body_hash` (`:313-315`). `signature=hmac.new(token, f"{ts}\n{nonce}\n{hash}", sha256)` (`:316-320`). Build POST, `urlopen(timeout=max(30,7200))`, parse JSON (`:321-335`).
9. Error handling: `HTTPError` → parse error JSON / `{"error":str(exc)}` → `RuntimeError` (`:336-341`); `(OSError,TimeoutError,URLError,JSONDecodeError)` → `RuntimeError` truncated 220 (`:342-343`). Require `ok is True` (`:344`) and dict `result` (`:346-348`). Return `result`.
10. Back in `_run_brokered_host_upgrade`: `RuntimeError` → `_brokered_operator_failure` (rc 2, logged) (`:381-382`); else `int(result.get("returncode"))` default 2 → `CompletedProcess` (`:383-387`).
11. Outer dispatcher: rc 0 → `finish_operator_action(status="completed")` + `note_refresh_job(ok)` + operator notice (`:2368-2394`); else `finish_operator_action(status="failed")` + `queue_notification` with `_tail_text` and `operator_upgrade_action_extra` (`:2396-2427`).

## CROSS-PIECE CONTRACTS (both ends verified)

1. **Dispatcher → operator-upgrade-broker (CANON-15).** SEAM: HMAC-signed POST `/v1/operator-upgrade`.
   Signed string client `f"{timestamp}\n{nonce}\n{body_hash}"` (`enrollment:318`) vs broker rebuild
   `f"{timestamp}\n{nonce}\n{body_hash}"` over `sha256(raw_body)` (`broker:707-711`); HMAC key both
   read `ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN` (client `:294`, broker `_broker_token`/`:687`); four
   header names byte-match (client `:99,326-329`, broker `:41-44,688-693`); broker enforces
   `compare_digest` on token (`broker:689`) + signature (`:713`), 300s TTL (`:701`), nonce regex
   `[A-Za-z0-9_.~+/=-]{16,160}` (`:703`, client `token_urlsafe(18)` ⊂ alphabet, 24 chars ∈ range),
   single-use nonce (`:705,715`), `MAX_REQUEST_BYTES=16384` (`:36,742`), operation allowlist
   `{run_operator_upgrade,run_pin_upgrade}` (`:642-650`). Response `{"ok":true,"result":dict}` (`broker:757`)
   matches client gate (`enrollment:344-348`). **BOTH-ENDS-VERIFIED: yes.**
2. **Pin install_items: control.py (CANON-01) → dispatcher → broker (CANON-15).** Producer
   `get_pin_upgrade_action_payload` re-normalizes each item to `{component,kind,field,current,target,throttle_target}`,
   returns `None` if any item fails (`control:9550-9576`). Dispatcher reads ONLY `payload.get("install_items")`
   and forwards verbatim (`enrollment:458,462-463`). Broker `_normalized_pin_upgrade_item` re-validates
   `component ∈ ALLOWED_PIN_COMPONENTS` + `SAFE_COMPONENT_RE` and DROPS field/current/throttle_target
   (`broker:265-273`). **BOTH-ENDS-VERIFIED: yes.** (See RISK: non-Docker arg builder does NOT enforce the allowlist.)
3. **Fleet enrollment: hosted_api (CANON-02) → consume_fleet_enrollment.** Producer
   `_handle_fleet_enrollment_callback` reads Bearer token + passes the parsed JSON body as `payload` and
   `config.fleet_enrollment_secret` (`hosted_api:2035-2047`). Consumer reads `body["machine_fingerprint"]`/`["hostname"]`
   etc. (`fleet:536-600`); `ArcLinkFleetEnrollmentError` → HTTP 401 (`hosted_api:2048-2049`); success → 201
   `{"worker": result}` (`:2050`). OpenAPI marks `hostname`+`machine_fingerprint` required (`:3185`).
   **BOTH-ENDS-VERIFIED: yes.**
4. **Intent renderer → executor (CANON-11) & ingress/adapters (CANON-02/09).** `_apply_deployment`
   passes `intent["dns"]`, `intent` (compose) into `CloudflareDnsApplyRequest`/`DockerComposeApplyRequest`
   (`worker:1210-1243`). `render_arclink_provisioning_intent` consumes `desired_arclink_ingress_records`
   + `render_traefik_dynamic_labels` (CANON-09 `ingress:46,235`) and `arclink_hostnames`/`arclink_access_urls`
   (CANON-02 `adapters:228,270,241`). DNS dict shape role→{hostname,record_type,target,proxied} (`:1744-1752`).
   **BOTH-ENDS-VERIFIED: producer side fully read; executor request construction verified at worker call sites.**
5. **build_arclink_ssh_access_record (this piece) → intent.** `render_arclink_provisioning_intent` calls it
   (`:1696-1700`) and embeds `{strategy,username,hostname,command_hint}` into `access.ssh` (`:1756-1761`).
   Self-contained within CANON-08. **BOTH-ENDS-VERIFIED: yes.**
6. **operator_actions confirmed-source: operator-raven (CANON-14) → dispatcher.** Producer writes
   `request_source` (control.py schema `:765`); only `"operator-raven"` is honored (`enrollment:2292`).
   Consumer end verified; producer end (CANON-14) named, not re-opened here. **BOTH-ENDS-VERIFIED: consumer yes, producer named.**

## CODE vs COMMENT/DOC/NAME DRIFT
- **Prior doc handoff gate** (`02-…:90`) claims the health gate blocks on `failed|unhealthy|missing`. CODE
  ALSO blocks on `starting` (`worker:1264`). DRIFT — prior doc understates the gate.
- **Prior doc omits second handoff gate.** `ARCLINK_SOVEREIGN_HANDOFF_REQUIRES_HERMES_HOME_READY`
  (default 1) raises if hermes-home is not ready (`worker:1271-1293`). Not in the prior doc’s apply step list.
- **`_docker_mode` truthy-set inconsistency.** `enrollment:764` accepts `{1,true,yes}`; `agent_access:143`
  accepts `{1,true,yes,on}`. Same env var, different parse. Cosmetic but a real divergence — a value of
  `on` toggles agent_access but not the dispatcher.
- **DISSECT P2 anchor drift (confirmed, no behavioral gap).** The prompt's `_run_operator_upgrade_action`
  does not exist; the real path is `_run_host_upgrade` → `_run_brokered_host_upgrade` (`enrollment:390-392`).
- **DISSECT P2 "everything becomes returncode-2" is FALSE for one branch.** `response.read().decode("utf-8")`
  (`enrollment:335`) can raise `UnicodeDecodeError` (a `ValueError`, NOT in the `:342` except tuple, not
  `RuntimeError`), so a non-UTF-8 success body propagates out of `main()` (`:3348`) and strands the action
  in `running` (marked at `:2342`/`:2474`). Reachable only from a non-UTF-8 responder; the in-repo broker
  always emits UTF-8. Verified: the function's only broad-catch tuple at `:342` excludes `UnicodeDecodeError`.
- **Docstring vs scope (host_readiness).** Module docstring says it validates readiness “without mutating
  live providers” — TRUE (no mutation). But the GAP-030 *provisioning-readiness state model* is NOT here; it
  lives in `arclink_dashboard.py` (out of scope). The name `host_readiness` does not imply GAP-030 surfacing.
- **`render_arclink_provisioning_intent` still computes `files-`/`code-` hostnames** (`:1595-1596`,
  `arclink_hostnames`) that get NO DNS record (only `dashboard`+`hermes` roles do, per CANON-09). Name implies
  four subdomains; only two are provisioned. Matches prior doc §11 note.

## ADVERSARIAL SELF-CHECK (least-sure claims)
1. **"validate_no_plaintext_secrets is a complete gate."** I verified it runs at `:1781` and the predicate
   logic, but `contains_secret_material`/`is_secret_ref` live in CANON-23 (`arclink_secrets_regex`). If those
   regexes have a gap, a real secret could pass. FALSIFIER: a deployment metadata value that is real secret
   material but slips both `path_requires_secret_ref` and `contains_secret_material`.
2. **"Enrollment consume is TOCTOU-safe via rowcount==1."** The `UPDATE … WHERE status='pending'` +
   `rowcount != 1 → raise` (`fleet:689-698`) is the guard, but the whole flow runs in one SQLite connection;
   two concurrent control callbacks on the same token would serialize on SQLite write locks. FALSIFIER: a
   second connection consuming the same token between `_require_pending_enrollment` and the UPDATE — would the
   second see `pending`? Needs a concurrency test; SQLite default isolation likely prevents it but I did not prove it.
3. **"Confirmed-source gate cannot be bypassed."** Only `request_source=="operator-raven"` passes
   (`:2292-2297`). FALSIFIER: any other writer of `operator_actions` with `request_source='operator-raven'`
   (e.g. a direct DB insert path in CANON-14) would be honored — I did not enumerate every producer of that row.
4. **"Worker apply is idempotent / restart-safe."** `_reload_apply_ready_deployment` is called ~8× and asserts
   status still `provisioning` + entitlement still valid. FALSIFIER: a crash between `docker_compose_apply`
   (`:1237`) and `finish job`/`succeeded` could leave compose applied but job `running` → stale-recovery flips it
   `failed` and re-applies; I did not prove the executor apply itself is idempotent (that's CANON-11).
5. **"Plaintext http:// is fine (GAP-019)."** The bearer token + body travel unencrypted (`enrollment:322,326`).
   I accept the Docker-internal trust boundary, but I did not verify the broker is never bound to a routable
   interface in any compose profile (that's CANON-25).

## OPEN FOR CODEX FEDERATION
- Re-verify the `UnicodeDecodeError`-escape consequence chain (`enrollment:335→3348`, stranded `running` row)
  independently — the DISSECT adjudication ruled codex correct; confirm it still holds on this file revision.
- Confirm the non-Docker `_pin_upgrade_command_args` (`enrollment:421-448`) accepts ANY non-empty `component`
  (validates only `kind`), so component-allowlisting is enforced ONLY by the Docker broker — i.e. bare-metal
  pin upgrades have a weaker component gate. Severity?
- Enumerate ALL writers of `operator_actions.request_source` across the repo and confirm `operator-raven` is
  only ever set by genuinely-confirmed Operator Raven paths (CANON-14) — the gate's strength depends entirely on that.
- Prove/refute the enrollment-consume concurrency claim (#2 above) under two simultaneous callbacks.

## RISKS (severity-ranked, code-cited)
- **[MEDIUM]** Non-Docker pin-upgrade component allowlist is absent. `_pin_upgrade_command_args` validates only
  `kind` (via `_pin_upgrade_apply_flag`) and accepts any non-empty `component`/`target`, feeding it to
  `bin/component-upgrade.sh` argv (`enrollment:421-448`). The `ALLOWED_PIN_COMPONENTS` allowlist exists only in
  the Docker broker (`broker:267-268`). `[python/arclink_enrollment_provisioner.py:429-448; python/arclink_operator_upgrade_broker.py:267-268]`
- **[LOW]** Uncaught `UnicodeDecodeError` on the success-decode path escapes the RuntimeError contract, crashes
  the run, strands the `operator_actions` row in `running`. Reachable only from a non-UTF-8 responder.
  `[python/arclink_enrollment_provisioner.py:335,342,381,466,2342,2474,3348]`
- **[LOW]** Plaintext `http://` transport: broker bearer token + body (log paths, repo URL, deploy-key path)
  unencrypted; HMAC gives integrity/replay only, not confidentiality. Accepted under GAP-019 Docker-internal model.
  `[python/arclink_enrollment_provisioner.py:322,326]`
- **[LOW]** Broker URL is env-controlled with only `strip/rstrip`, no scheme/host allowlist; benign inside the
  trust boundary, no defense if env is tampered. `[python/arclink_enrollment_provisioner.py:289-290]`
- **[LOW]** `_docker_mode` truthy-set divergence: dispatcher `{1,true,yes}` vs agent_access `{1,true,yes,on}`;
  a value of `on` toggles one but not the other. `[python/arclink_enrollment_provisioner.py:764; python/arclink_agent_access.py:143]`
- **[INFO]** Readiness `ready` roll-up excludes secret-presence checks (`:183`), so a host with all required
  secrets absent can still report `ready=true` — by design (presence-only, never values) but worth flagging.
  `[python/arclink_host_readiness.py:183]`
- **[INFO]** Client trusts local clock for the signed timestamp; broker rejects skew >300s. Same Docker host ⇒
  skew ~0, but >5min drift fails every request closed. `[python/arclink_enrollment_provisioner.py:313; python/arclink_operator_upgrade_broker.py:701]`
- **[INFO]** `validate_no_plaintext_secrets` correctness fully depends on CANON-23 regexes; a regex gap is a
  secret-leak surface. `[python/arclink_provisioning.py:1398-1421,1781]`

## VERDICT
**Provably YES — this piece does its job, with two genuine weaknesses.** The intent renderer
(`render_arclink_provisioning_intent`) deterministically produces a fully secret-ref'd compose/env/DNS/traefik
intent and **fails closed** through `validate_no_plaintext_secrets` before returning (`:1781`). The fleet
enrollment plane is cryptographically sound: HMAC-SHA256 tokens with `compare_digest` on both signature and
stored hash, lazy-expiry, a `rowcount==1`-guarded single-use consume, and an HMAC prev-hash audit chain that
queues a P0 on tamper (`fleet:101-124,648-698,475-522,904-912`). The dispatcher's HMAC signing is byte-for-byte
compatible with the operator-upgrade-broker (every header, the signed-string format, body-hash-over-raw-bytes,
nonce alphabet, TTL, operation allowlist — all verified at both ends), missing url/token fails before any I/O,
and the **confirmed-source gate** (`request_source=="operator-raven"`) plus stale-running reaper give real
defense-in-depth for host mutation. Load-bearing strengths: fail-closed secret validation, double handoff
health gates (`worker:1260,1271`), mid-apply entitlement re-checks (`_reload_apply_ready_deployment` ×8),
operator-arcpod exclusion (`worker:565`), and bounded input validation on every enrollment field. Real
weaknesses: (1) the non-Docker pin-upgrade path lacks the component allowlist the Docker broker enforces
(MEDIUM); (2) a non-UTF-8 success body escapes the returncode-2 contract and strands a `running` row (LOW,
low reachability). The plaintext-http transport is an accepted Docker-internal trust assumption, not a code
defect. Sovereign-worker live execution remains operator-/proof-gated (PG-FLEET/PG-PROVISION), as the prior
ground-truth records.
