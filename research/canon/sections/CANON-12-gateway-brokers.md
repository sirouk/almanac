# CANON-12 — Public Agent Gateway & Brokers

## PIECE
This piece is ArcLink's **trusted-host privilege boundary**: a public-Agent
gateway bridge plus a family of narrow HTTP brokers/helpers that each own one
high-authority capability (Docker socket, root user-management, root setpriv,
root file copy) so that the callers (notification-delivery worker, executor,
action worker, Docker agent supervisor) never hold that authority directly. It
owns exactly ten tracked files:
- `python/arclink_gateway_exec_broker.py` (port 8911) — Docker-exec authority for
  Raven-mediated public Telegram/Discord Agent replies.
- `python/arclink_deployment_exec_broker.py` (8912) — Docker socket for
  deployment-scoped Compose `up/ps/down`.
- `python/arclink_agent_supervisor_broker.py` (8913) — Docker socket for the
  per-agent dashboard isolation network + auth-proxy sidecar lifecycle.
- `python/arclink_migration_capture_helper.py` (8914) — root file copy for Pod
  migration capture/materialize (no Docker socket).
- `python/arclink_agent_user_helper.py` (8915) — root `useradd`/`groupadd`/`chown`
  for container-local agent users (no Docker socket).
- `python/arclink_agent_process_helper.py` (8916) — root `setpriv` privilege-drop
  process boundary for agent gateway/dashboard/install processes (no Docker
  socket).
- `python/arclink_docker_agent_supervisor.py` — the **consumer** reconciliation
  loop (runs as root, holds no Docker socket) that drives 8913/8915/8916.
- `python/arclink_public_agent_bridge.py` — the short-lived boundary process run
  *inside* a deployment's Hermes gateway container, replaying a public bot turn
  through Hermes' native gateway pipeline.
- `python/arclink_pod_comms.py` — cross/intra-Captain Agent-to-Agent messaging
  over `arclink_pod_messages` gated by `pod_comms` share grants.
- `python/arclink_rejection_incidents.py` — shared redacted-JSONL incident logger
  used by every broker/helper.
The operator-upgrade-broker (8917) is referenced as a sibling but is owned by
CANON-15. Two test files (`tests/test_arclink_pod_comms.py`,
`tests/test_arclink_public_agent_bridge.py`) belong to CANON-29.

GAP-019 risk-acceptance is enforced **in code**, not just policy: every broker
and helper calls `require_docker_trusted_host_risk_accepted(...)` both at
`main()` start (`error_cls=SystemExit`) and on every request
(`error_cls=ValueError`), refusing to run unless
`ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED=accepted`
(`arclink_boundary.py:80-97`). This was verified per-file (cites in TOUCH POINTS).

## INPUT CONTRACT (code-verified)

### gateway-exec-broker (8911)
- HTTP `POST /v1/public-agent-bridge`, JSON object, `Content-Length` in `(0,
  65536]` (`arclink_gateway_exec_broker.py:336,346`). Auth header
  `X-ArcLink-Gateway-Exec-Token` compared via `hmac.compare_digest` against
  `ARCLINK_GATEWAY_EXEC_BROKER_TOKEN` (`:51-54,339`). `GET /health` returns 503
  if token unset (`:330-333`).
- Body validated by `_build_gateway_exec_command` (`:196-284`). Presence of
  `cmd` or `command` → reject "does not accept raw commands" (`:197-198`).
  Two modes: **operator_stack=True** (project must equal
  `ARCLINK_CONTROL_COMPOSE_PROJECT||"arclink"`, service
  `control-operator-hermes-gateway`, `:199-226`); **deployment mode**
  (`deployment_id`/`prefix` safe segments via `DEPLOYMENT_SEGMENT_RE`
  `^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$`, `project_name == _compose_project_name`,
  must match `PUBLIC_AGENT_BRIDGE_PROJECT_RE`, service `hermes-gateway` with a
  `docker compose ... exec -T` fallback, `:227-284`).
- `_validate_payload` (`:173-193`): `platform∈{telegram,discord}`, requires
  non-empty `bot_token`, `chat_id`, `user_id`, `text`; `len(text)<=8000`.
  `timeout_seconds` clamped `[30,86400]` default 240 (`:57-62`).

### deployment-exec-broker (8912)
- `POST /v1/docker-compose`, JSON object, `Content-Length` in `(0,16384]`
  (`:270,280`). Auth `executor.DEPLOYMENT_EXEC_BROKER_TOKEN_HEADER`
  (`X-ArcLink-Deployment-Exec-Broker-Token`) via `hmac.compare_digest`
  (`:96-99`).
- `_validate_request` (`:117-156`): rejects `args`/`cmd`/`command`;
  `operation∈{compose_up,compose_ps,compose_down}`; `deployment_id` /
  `project_name` via `executor._require_safe_deployment_id` /
  `_require_compose_project_name(require_expected=True)`; `env_file`/`compose_file`
  must be absolute, share a parent (checked twice: raw and normalized), pass
  `executor._validate_deployment_config_paths`, and lstat as non-symlink
  dir/dir/regular-readable/regular-readable.

### agent-supervisor-broker (8913)
- `POST /v1/agent-supervisor`, `(0,16384]` (`:481,491`). Auth
  `X-ArcLink-Agent-Supervisor-Broker-Token` (`:459-462`).
- `operation∈{ensure_dashboard_network,ensure_dashboard_proxy,
  remove_dashboard_proxy}` (`:438-444`). Each rejects raw commands (`:146-148`),
  validates `agent_id` (`SAFE_SEGMENT_RE`), `supervisor_container`/`container_name`
  (`SAFE_CONTAINER_RE`), and requires the supplied `network`/`container_name` to
  equal the value derived from `agent_id` (`:159-161,270-275,353-354`).
  `backend_host` must be loopback/private/link-local IP, never
  wildcard/multicast/global (`_require_backend_host`, `:96-110`). Ports validated
  `[1,65535]` (`:86-93`). `access_file` must stay under
  `ARCLINK_DOCKER_CONTAINER_PRIV_DIR` (`:232-242`).

### migration-capture-helper (8914)
- `POST /v1/migration-capture`, `(0,16384]` (`:253,263`). Auth
  `MIGRATION_CAPTURE_HELPER_TOKEN_HEADER` (`X-ArcLink-Migration-Capture-Helper-Token`)
  (`:54-57`). `_validate_request` (`:115-158`): rejects raw commands;
  `operation∈{capture,materialize}`; `deployment_id`/`prefix` via
  `SAFE_IDENTIFIER_RE`; `migration_id` via `SAFE_MIGRATION_ID_RE`
  (`^mig_...`); the three roots must be absolute, under
  `ARCLINK_STATE_ROOT_BASE`, name-equal to the expected deployment root from
  `render_arclink_state_roots`; `capture_dir` must be `.migrations/<mig_id>`
  under the target base and **not** inside source or target root.

### agent-user-helper (8915)
- `POST /v1/agent-user`, `(0,16384]` (`:561,571`). Auth
  `X-ArcLink-Agent-User-Helper-Token` (`:63-66`). Only
  `operation=ensure_user_home` (`:37,412`). `_validate_request` (`:408-422`):
  rejects raw commands; `agent_id` via `SAFE_AGENT_ID_RE`; `unix_user` via
  `SAFE_UNIX_USER_RE` (`^[a-z_][a-z0-9_-]{0,30}$`); `home_root` must equal
  configured `ARCLINK_DOCKER_AGENT_HOME_ROOT`, with `home`, `hermes_home`,
  `workspace` forced to canonical children (each compared against the literal
  expected path AND its non-symlink resolution).

### agent-process-helper (8916)
- `POST /v1/agent-process`, `(0,32768]` (`:906,916`). Auth
  `X-ArcLink-Agent-Process-Helper-Token` (`:92-95`).
  `operation∈{run_once,ensure_processes,terminate_all}` (`:878-884`). `run_once`
  kinds `install/identity/refresh/cron`; `ensure_processes` kinds
  `gateway/dashboard`. `_validate_common` (`:385-434`) re-validates agent id,
  unix user, configured roots, uid/gid (numeric `[1,2147483647]`), and `env`
  (`_require_env`, `:334-370`): every key matches `^[A-Z][A-Z0-9_]*$`, no NUL,
  blocks any `ARCLINK_*_TOKEN`/blocklist key, blocks `LD_*`,
  `PYTHONPATH/PYTHONHOME/...`, `GIT_SSH*`, `SSH_*`, and any
  `_TOKEN/_SECRET/_PASSWORD/_KEY` suffix; requires the exact
  HOME/USER/HERMES_HOME/workspace/uid/gid values, pins PATH to `SAFE_PATH`.

### pod_comms (library, not HTTP)
- `send_pod_message(conn, *, sender_deployment_id, recipient_deployment_id, body,
  attachments=None, actor_id="")` (`:229`). Callers:
  `arclink_mcp_server._send_agent_pod_comms` (`:1112`). Requires distinct
  Captain-linked deployments; cross-Captain requires active `pod_comms` grant.
- `list_pod_messages` / `list_all_pod_messages` / `mark_pod_message_delivered` /
  `redact_pod_message`. Hosted-API consumers: `arclink_hosted_api.py:1696,1967`.

### public_agent_bridge (stdin process)
- `main()` reads a JSON dict from stdin (`_payload_from_stdin`, `:32-39`),
  dispatches on `platform∈{telegram,discord}` (`:781-790`). Required fields per
  platform via `_required` (`:71-75`): telegram needs `bot_token,chat_id,text`;
  discord needs `bot_token,channel_id,user_id,text`. Output is a single JSON line
  on stdout.

### docker_agent_supervisor (consumer loop)
- `main()` (`:825`): no request input; reads DB via `active_agents`, env via
  `Config.from_env`. Drives the brokers/helpers as an HTTP client.

## OUTPUT CONTRACT (code-verified)
- **All brokers/helpers** respond JSON: success `{"ok":true}` (gateway-exec) or
  `{"ok":true,"result":{...}}` (others); failure `{"ok":false,"error":<str>}`
  with HTTP 400/401/404/413/503 (e.g. `arclink_deployment_exec_broker.py:291-296`).
- **gateway-exec-broker** side effect: spawns `subprocess.run([docker, exec/-T,
  ...bridge...], input=json.dumps(payload))` (`:295-302`), returns
  `(True,"")` only if the last stdout line parses to `{"ok":true}` (`:311-317`).
- **deployment-exec-broker** side effect: `executor.SubprocessDockerComposeRunner.run`
  against the Docker socket (`:239-247`).
- **agent-supervisor-broker** side effects: `docker network create --internal`,
  `network connect`, `docker run -d --rm --pull never` of the auth-proxy sidecar,
  `docker rm -f` (`:171,175-188,306-339,355-360`). Returns
  `{"network","backend_host"}` / `{"container","changed"}` / `{"container",
  "removed"}`.
- **migration-capture-helper** side effect: `_copy_capture` / `_materialize_capture`
  (root file copy, `:226-230`).
- **agent-user-helper** side effects: `groupadd/useradd/chown -R`, mkdir of
  `.config/systemd/user`, `.local/share|state/arclink-agent`, hermes home,
  workspace; writes/reads `.arclink-user-ids.json` (O_EXCL+O_NOFOLLOW, mode
  0600, `:287-298,435-453`). Returns `{uid,gid,home,hermes_home,workspace}`.
- **agent-process-helper** side effects: `setpriv ...` subprocess for run-once;
  long-lived `subprocess.Popen(start_new_session=True)` registered in
  module-global `PROCESSES`/`PROCESS_SIGNATURES`; SIGTERM→SIGKILL teardown via
  `os.killpg` (`:687-700,837-857,782-798`). Writes per-process log files under
  `<state>/docker/agent-process-helper/`.
- **pod_comms** writes: INSERT into `arclink_pod_messages` (status `queued`),
  `append_arclink_audit` (`pod_message_sent`), `append_arclink_event`,
  `queue_notification(channel_kind="pod-message")`; single `conn.commit()` at
  `:306`. Returns `{ok, message, notification_id}`.
- **rejection_incidents** writes one redacted JSONL row per rejection
  (O_APPEND|O_CREAT|O_NOFOLLOW|O_CLOEXEC, 0600, `:151-161`); silently no-ops if
  path resolves unsafe / unset (`:138-139,160-161`).

## TOUCH POINTS
- **GAP-019 gate (every broker/helper)**:
  `require_docker_trusted_host_risk_accepted` —
  gateway-exec `:289,378`; deployment-exec `:233,312`; agent-supervisor
  `:434,523`; migration-capture `:224,295`; agent-user `:529,603`;
  agent-process `:873,945`. Env `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED`
  (boundary `:19,82`).
- **Trusted docker binary** (only the 3 socket-mounting services):
  `require_trusted_docker_binary` against `TRUSTED_DOCKER_BINARY_PATHS`
  (`/usr/bin/docker`,`/usr/local/bin/docker`,`/bin/docker`,`/snap/bin/docker`,
  boundary `:21-26,107-133`). gateway-exec `:65-71`; deployment-exec `:44-50`;
  agent-supervisor `:46-52`. Env `ARCLINK_DOCKER_BINARY`.
- **Env vars (ports/tokens/hosts)**: `ARCLINK_<SVC>_{HOST,PORT,TOKEN}` for each;
  code default host `127.0.0.1` but compose overrides `HOST: 0.0.0.0`
  (compose.yaml:656,686,825,897,930,1007). Default ports 8911-8916. Tokens
  required at startup (`SystemExit` if blank, e.g. `:380`).
- **DB tables (pod_comms)**: reads/writes `arclink_pod_messages`
  (`arclink_control.py:1437-1449`, status CHECK
  `queued/delivered/failed/redacted`); reads `arclink_share_grants`
  (`:1052-1069`); reads `arclink_deployments`; rate via `rate_limits`
  (`arclink_api_auth.py:425-428`).
- **Docker socket**: only deployment-exec (compose.yaml:666), agent-supervisor
  (:832), gateway-exec (:1017) mount `/var/run/docker.sock`. migration-capture,
  agent-user, agent-process explicitly do NOT (compose comments :676-678,
  :915-917).
- **Networks**: each broker on a dedicated `*-broker-net`/`*-helper-net` marked
  `internal: true` (compose.yaml:1163-1176); the lone egress path is
  `agent-process-helper-egress-net` (NOT internal, :1177) for spawned agent
  processes.
- **Subprocess argv**: `setpriv --reuid --regid --clear-groups --no-new-privs
  --inh-caps=-all --ambient-caps=-all --bounding-set=-all`
  (agent-process `:444-457`); `useradd --uid --gid --home-dir --shell /bin/bash
  --create-home` (agent-user `:387-402`); pinned `SETPRIV_BIN=/usr/bin/setpriv`,
  `TRUSTED_ROOT_EXECUTABLES` `/usr/sbin/{groupadd,useradd}`,`/usr/bin/chown`.
- **Locks**: `ASSIGNMENTS_LOCK` (agent-user `:41,342`); `PROCESS_LOCK`
  (agent-process `:71,826,863`).
- **Secrets handling**: bot tokens passed to bridge via **stdin**
  (`subprocess.run(..., input=json.dumps(payload))`, gateway-exec `:297`) so
  they never appear in argv; rejection incidents never log payloads/tokens/text
  (only `safe_metadata`, `rejection_incidents.py:111-125`).

## CODE-PATH TRACE (gateway-exec end-to-end, public Telegram turn)
1. notification-delivery builds payload `_public_agent_gateway_payload`
   (`arclink_notification_delivery.py:644-696`) → dict with
   `platform,bot_token,chat_id,channel_id,user_id,text,message_id,...`.
2. `_run_public_agent_gateway_turn` (`:699-745`) wraps it in
   `_gateway_exec_broker_request` →
   `{deployment_id,prefix,project_name,payload,timeout_seconds}` (`:334-348`).
3. `_run_gateway_exec_broker_request` (`:365-407`) POSTs to
   `${ARCLINK_GATEWAY_EXEC_BROKER_URL}/v1/public-agent-bridge` with header
   `X-ArcLink-Gateway-Exec-Token`.
4. Broker `do_POST` (`gateway_exec_broker.py:335-361`) checks path, auth,
   size, JSON-dict; calls `run_gateway_exec_request`.
5. `run_gateway_exec_request` (`:287-317`) gates GAP-019, then
   `_build_gateway_exec_command` (`:196-284`) rejects raw cmd, validates
   project/segment, resolves the running `hermes-gateway` container via
   `delivery._deployment_service_container`, re-validates with
   `delivery._validate_public_agent_bridge_cmd`, returns
   `[docker, exec, -i, <container>, <python3>, <bridge.py>]`.
6. `subprocess.run(cmd, input=json.dumps(payload))` (`:295-302`) execs the
   bridge inside the container; bridge stdin → `_payload_from_stdin`
   (`public_agent_bridge.py:32-39`) → `_run_telegram` (`:372-462`) replays the
   turn through Hermes' native adapter.
7. Bridge prints `{"ok":true,"delivered":true}`; broker parses last stdout line
   (`:311-317`) and returns `{"ok":true}` HTTP 200; delivery marks the
   notification delivered.

## CROSS-PIECE CONTRACTS (both ends verified)

1. **gateway-exec broker payload** — adjacent: CANON-23
   (notification_delivery). Producer `_public_agent_gateway_payload`
   (`arclink_notification_delivery.py:674-685`) emits
   `platform,bot_token,chat_id,user_id,text`; consumer `_validate_payload`
   (`gateway_exec_broker.py:177-188`) reads exactly those. Wrapper keys
   `deployment_id,prefix,project_name,payload,timeout_seconds` produced at
   `:342-348`, consumed at `:227-238`. **BOTH-ENDS-VERIFIED: yes.**

2. **gateway-exec broker token header** — adjacent: CANON-23. Producer header
   constant `GATEWAY_EXEC_BROKER_TOKEN_HEADER="X-ArcLink-Gateway-Exec-Token"`
   (`notification_delivery.py:301`) is the SAME symbol the broker imports for
   `_is_authorized` (`gateway_exec_broker.py:53`). **BOTH-ENDS-VERIFIED: yes.**

3. **deployment-exec broker body** — adjacent: CANON-11 (executor). Producer
   `BrokeredDockerComposeRunner.run` body
   `{deployment_id,operation,project_name,env_file,compose_file,remove_volumes,
   include_all}` (`arclink_executor.py:796-804`); consumer `_validate_request`
   reads each (`deployment_exec_broker.py:120-155`). Header
   `DEPLOYMENT_EXEC_BROKER_TOKEN_HEADER` shared symbol (executor `:45`, broker
   `:98`). **BOTH-ENDS-VERIFIED: yes.**

4. **migration-capture helper body** — adjacent: CANON-13 (pod_migration).
   Producer `_migration_capture_helper_payload`
   (`arclink_pod_migration.py:469-479`) emits
   `deployment_id,prefix,migration_id,source_state_root,target_state_root,
   capture_dir` + `operation`; consumer `_validate_request`
   (`migration_capture_helper.py:115-158`) reads exactly those. Header
   `MIGRATION_CAPTURE_HELPER_TOKEN_HEADER` shared symbol (pod_migration `:51`,
   helper `:23`). **BOTH-ENDS-VERIFIED: yes.**

5. **agent-supervisor broker body** — adjacent: this piece's own consumer
   (`docker_agent_supervisor.py`). Producer `agent_supervisor_broker_request`
   wraps `{**payload,"operation"}` and POSTs `/v1/agent-supervisor`
   (`:334-370`); for `ensure_dashboard_proxy` payload keys
   `agent_id,network,backend_host,backend_port,proxy_port,container_name,
   access_file` (`:482-492`) match the broker reads (`broker:265-281`).
   Header `AGENT_SUPERVISOR_BROKER_TOKEN_HEADER` defined identically in both
   (supervisor `:52`, broker `:35`). **BOTH-ENDS-VERIFIED: yes.**

6. **agent-user helper body** — adjacent: own consumer. Producer
   `ensure_container_user` → `agent_user_helper_request("ensure_user_home",
   {agent_id,unix_user,home_root,home,hermes_home,workspace})`
   (`docker_agent_supervisor.py:583-592`); consumer reads same
   (`agent_user_helper.py:414-421`). Result `{uid,gid}` consumed back at
   supervisor `:595`. **BOTH-ENDS-VERIFIED: yes.**

7. **agent-process helper body** — adjacent: own consumer. Producer
   `agent_process_context` builds the full ctx dict incl. validated `env`
   (`docker_agent_supervisor.py:649-673`) and
   `agent_process_helper_request(operation, payload)` (`:411-447`); consumer
   `_validate_common` re-validates every field independently
   (`agent_process_helper.py:385-434`). Header symbol identical (supervisor
   `:54`, helper `:34`). Note the supervisor pre-filters env
   (`_agent_process_env` strips control tokens, `:291-300`) AND the helper
   re-rejects them — defense in depth. **BOTH-ENDS-VERIFIED: yes.**

8. **bridge stdin payload** — adjacent: gateway-exec broker / notification
   delivery. Producer (broker) feeds `json.dumps(payload)` to bridge stdin
   (`gateway_exec_broker.py:297`); consumer bridge `_payload_from_stdin` +
   `_required(payload,key)` (`public_agent_bridge.py:32-39,71-75,375-380`).
   Keys `bot_token,chat_id,user_id,text` match. **BOTH-ENDS-VERIFIED: yes.**

9. **pod_comms → notification queue** — adjacent: CANON-23. Producer
   `send_pod_message` → `queue_notification(channel_kind="pod-message",
   extra={message_id,sender_deployment_id,...})` (`pod_comms.py:308-321`);
   consumed by the notification-delivery worker (CANON-23). **BOTH-ENDS-
   VERIFIED: partial** — verified the producer call shape and that
   `queue_notification` exists (`arclink_control.py:8055`); did not trace the
   delivery worker's read of `channel_kind="pod-message"` (CANON-23 territory).

10. **pod_comms → share_grants** — adjacent: CANON-20 (sharing). Consumer
    `find_active_pod_comms_grant` reads `arclink_share_grants` columns
    `resource_kind,owner_user_id,recipient_user_id,status,revoked_at,
    expires_at,accepted_at,created_at,metadata_json` (`pod_comms.py:92-110`);
    schema producer `arclink_control.py:1052-1069` defines all of them.
    **BOTH-ENDS-VERIFIED: yes.**

## CODE vs COMMENT/DOC/NAME DRIFT
- **Listen host docstring vs deployment**: every broker's code default is
  `DEFAULT_HOST="127.0.0.1"` (e.g. `gateway_exec_broker.py:32`) but compose
  forces `ARCLINK_*_HOST: 0.0.0.0` (compose.yaml:1007 etc.). The "loopback"
  mental model is wrong in production; isolation is provided by per-broker
  `internal: true` networks + token auth, not by the 127.0.0.1 default. Code
  (compose) wins.
- **agent-process-helper `do_POST` size check ordering vs others**: in
  agent-process-helper the body is parsed and passed to
  `run_agent_process_helper_request` which itself re-checks `isinstance(dict)`
  (`:874-875`), whereas the other brokers reject non-dict in `do_POST` before
  dispatch. Functionally equivalent (helper raises ValueError → 400) but the
  symmetry implied by the shared handler shape is not exact. Not a bug.
- **Prior doc 08 claim "uid/gid range [20000,60000)"**: code constant is
  `AGENT_UID_MIN=20000`, `AGENT_UID_SPAN=40000` → range `[20000,60000)`
  (`agent_user_helper.py:38-39,197`). Prior doc is **correct**; recorded here
  only because the doc's parenthetical phrasing could be misread.
- **Prior doc 08 is otherwise accurate** for this piece on ports, headers,
  routes, max-bytes, operations, rejection paths, and docker.sock posture —
  re-verified line by line; no refutations.
- **`_compose_project_name` duplication**: the regex/normalizer lives in
  `notification_delivery.py:321-323` and the gateway-exec broker imports it from
  `delivery` (`:86,229`), but the broker ALSO has its own
  `DEPLOYMENT_SEGMENT_RE` (`:34`) that is stricter (`[A-Za-z0-9_-]`, no `.`).
  Two different "safe segment" definitions coexist; not contradictory but a
  maintenance smell.

## ADVERSARIAL SELF-CHECK
1. **Claim: bot tokens never reach argv.** Verified gateway-exec passes payload
   via stdin (`:297`). Falsifier: if any deployment-mode fallback put the token
   on the command line — checked `_build_gateway_exec_command`, it does not; the
   command is fixed `[docker,exec,-i,container,python3,bridge.py]`. Residual
   doubt: the bridge process inside the container then sets
   `os.environ["TELEGRAM_BOT_TOKEN"]=bot_token` (`public_agent_bridge.py:382`),
   so the token IS in that container process env (expected, but worth a GPT-5.5
   look at container-env exposure).
2. **Claim: agent-process-helper env filtering is fail-closed.** `_require_env`
   rejects unknown control/secret keys but **passes through** any other
   `^[A-Z][A-Z0-9_]*$` key the caller sends. Falsifier: a caller (the
   supervisor) could inject an arbitrary non-secret env var. Mitigated because
   the supervisor's `_agent_process_env` is the only producer and itself
   constrains keys, but the helper trusts the request's env shape beyond the
   10 pinned keys. Worth scrutiny.
3. **Claim: `0.0.0.0` binding is safe.** Rests entirely on the compose
   `internal: true` network + the assumption no other container is attached to a
   broker's net. I verified the network declarations but did NOT enumerate every
   service's `networks:` list to prove no extra attachment. A mis-wired future
   service on `gateway-exec-broker-net` would reach the broker (still needs the
   token). MEDIUM-confidence.
4. **Claim: gateway-exec `_validate_public_agent_bridge_cmd` re-validation is
   load-bearing.** The broker builds the command itself, then re-validates it.
   If both the builder and validator share the same blind spot the re-check is
   theater. They are independent functions but both authored together; an
   adversary controlling neither can't reach them anyway (token-gated).
5. **Claim: pod_comms cross-Captain gate cannot be bypassed.** Same-Captain
   sends skip the grant check (`_require_send_allowed` returns None when
   `sender_user==recipient_user`, `:131-133`). Falsifier: if two distinct
   Captains' deployments were ever assigned the same `user_id`, the gate opens.
   Depends on user_id uniqueness invariant owned by CANON-01/CANON-08.

## OPEN FOR CODEX FEDERATION
- Confirm the notification-delivery worker actually consumes
  `channel_kind="pod-message"` and does not re-broadcast pod bodies to a public
  channel (seam #9 partial). [CANON-23]
- Independently audit whether `_validate_public_agent_bridge_cmd`'s two exact
  argv shapes (len 6 / len 13) can be satisfied by any attacker-influenced
  `deployment_id`/`prefix` producing a container or project name that passes
  `PUBLIC_AGENT_BRIDGE_PROJECT_RE` but points at a non-deployment container.
- Verify no compose service other than the documented single client is attached
  to each `*-broker-net`/`*-helper-net` (proves the `0.0.0.0` bind is contained).
  [CANON-25]
- Cross-check that `Config.from_env` in `docker_agent_supervisor.main()` yields
  the exact `repo_dir`/`private_dir`/`state_dir` the agent-process-helper expects
  as `configured` paths (a mismatch would fail-closed but break all agent
  processes). [CANON-01]
- Scrutinize agent-process-helper module-global `PROCESSES` registry under
  ThreadingHTTPServer concurrency: `PROCESS_LOCK` guards mutation, but
  `_ensure_processes` and `_terminate_all` both iterate; confirm no TOCTOU on a
  Popen handle removed by a concurrent `terminate_all`.

## RISKS (severity-ranked, code-cited)
- **MEDIUM** — Brokers bind `0.0.0.0` in production (compose.yaml:1007,832,666,
  …) while code/docstrings imply loopback. Security rests on `internal: true`
  network isolation + token; any future co-attached container on a broker net
  gets network reach (still token-gated). `arclink_gateway_exec_broker.py:32`.
- **MEDIUM** — agent-process-helper passes through arbitrary uppercase env keys
  not on its block/unapproved lists; only the supervisor producer constrains the
  set. A compromised supervisor could set unexpected (non-secret) env on
  root-spawned-then-dropped processes. `arclink_agent_process_helper.py:337-349`.
- **LOW** — Same-Captain pod_comms sends bypass the share-grant gate entirely
  (`arclink_pod_comms.py:131-133`); correctness depends on `user_id` uniqueness
  across Captains (owned elsewhere).
- **LOW** — gateway-exec broker's `run_gateway_exec_request` returns the raw
  subprocess failure tail (last stderr/stdout line, ANSI-stripped, ≤220 chars)
  to the HTTP caller (`:307-310`); low risk of internal detail leakage to the
  delivery worker (a trusted peer), but it is not a generic message.
- **LOW** — `record_rejection_incident` silently no-ops on any OSError or unsafe
  path (`rejection_incidents.py:138-139,160-161`); a misconfigured state root
  means rejections are dropped, not surfaced. Observability gap, not a breach.
- **INFO** — pod_comms rate-limit row is inserted (`commit=False`) before the
  message INSERT in the same transaction (`pod_comms.py:246-306`); a later
  validation failure rolls back the rate-limit row too (correct), but the
  ordering means the limit is consumed only on otherwise-valid sends.

## VERDICT
This piece **provably does its job**: it is a genuine, code-enforced privilege
boundary, not a naming convention. Each broker/helper (1) refuses to start or
serve without the GAP-019 acknowledgement env, (2) authenticates every request
with constant-time token comparison, (3) rejects raw command input and
reconstructs only an allowlisted command/operation locally, (4) validates every
identifier/path/port/IP against strict regexes and canonical-child checks, and
(5) emits redacted rejection incidents that never carry secrets. The
docker.sock split (only 3 of 6 services hold it; the root supervisor holds
none) and the stdin-only secret path for bot tokens are real, verified
strengths. All seven inbound HTTP/CLI seams have matching producer/consumer
keys and shared header symbols (both-ends verified). Load-bearing weaknesses are
operational rather than logical: the production `0.0.0.0` bind depends on
network-isolation correctness that lives in compose (CANON-25), the
agent-process-helper trusts the env *shape* beyond its pinned keys, and one
pod_comms seam (delivery of `pod-message` notifications) terminates in CANON-23
and was only partially traced here.
