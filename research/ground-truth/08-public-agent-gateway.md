# Ground Truth 08 — Public Agent Gateway / Bridge / Exec Brokers / Pod Comms / Supervisor

Date captured: 2026-05-30. Branch: `arclink`. This record maps the current
code-level ground truth for the public-Agent gateway bridge, the family of
trusted-host Docker exec brokers/helpers (GAP-019 family), Pod Comms, and the
Docker-mode agent supervisor. This subsystem is almost entirely absent from the
canonical `docs/arclink/architecture.md`; its only deep documentation lives in
`docs/arclink/operations-runbook.md` (GAP-019 entries) and three `research/`
notes that are point-in-time (2026-05-11) and predate later hardening.

---

## 1. What is actually implemented today

### 1.1 Public Agent Gateway Bridge (`python/arclink_public_agent_bridge.py`)

A short-lived **boundary process** run *inside* a deployment's Hermes gateway
container. It reads a JSON payload from stdin and replays a public
Telegram/Discord turn through Hermes' own gateway pipeline so the turn behaves
like a native active-agent channel message (sessions, slash commands, typing,
reactions, interim messages, delivery formatting, plugin hooks) rather than a
Raven-mediated quiet CLI call.

Real, implemented behavior:

- `main()` reads payload from stdin (`_payload_from_stdin`), runs `_run`, and
  prints a single-line JSON result `{"ok": true, "delivered": true}` or
  `{"ok": false, "error": ...}` (truncated to 500 chars). Exit 0/1.
- Adds the Hermes runtime source dir to `sys.path` from `HERMES_AGENT_SRC` or
  `RUNTIME_DIR/hermes-agent-src` (default `/opt/arclink/runtime`)
  (`_runtime_source_dir`, `_add_runtime_paths`).
- Dispatches on `payload["platform"]` ∈ {`telegram`, `discord`}; any other
  platform raises "public agent gateway bridge does not support platform ...".
- **Telegram** (`_run_telegram`): builds a real PTB `telegram.Bot`, loads
  `gateway.config.load_gateway_config()`, forces the Telegram `PlatformConfig`
  on with a synthetic `HomeChannel`, constructs a Hermes `GatewayRunner`, creates
  the native Telegram adapter, wires `runner._handle_message`, session store,
  busy-session handler, and a `SessionSource`.
  - If `payload["telegram_update_json"]` is present, it rebuilds the PTB
    `Update` and dispatches it to Hermes' **own native adapter handlers**
    (`_try_replay_native_telegram_update`): `_handle_command` /
    `_handle_text_message` for text, `_handle_location_message` for
    location/venue, `_handle_media_message` for photo/video/audio/voice/
    document/sticker, `_handle_callback_query` for inline callbacks.
  - Non-Raven inline callbacks with `data` prefix `ea:` (exec-approval) are
    bridged to a **durable approval mapping** on disk; Raven callbacks use the
    `arclink:` namespace and are handled by ingress, not here.
  - If no raw update is present, it falls back to a synthetic `MessageEvent`
    (`MessageType.COMMAND` for `/`-prefixed text, else `MessageType.TEXT`).
- **Discord** (`_run_discord`): there is no native long-lived discord.py
  adapter here. It uses a minimal `_DiscordRest` (aiohttp) client against
  `https://discord.com/api/v10`, monkeypatches the adapter's `send`,
  `edit_message`, `send_typing`, `stop_typing` to REST shims, and a
  `_DiscordRawMessage` shim implementing `add_reaction`/`remove_reaction`. Then
  dispatches a single synthetic `MessageEvent` (TEXT or COMMAND).
- **Streaming**: `_public_bridge_streaming_enabled()` (env
  `ARCLINK_PUBLIC_AGENT_BRIDGE_STREAMING`, default on) forces Hermes
  `streaming.enabled = True` and `transport = "edit"` for public bridge turns
  (`_enable_public_bridge_gateway_defaults`), and sets
  `HERMES_TOOL_PROGRESS_MODE=all`. It deliberately does **not** enable
  `show_reasoning`.
- **Durable exec-approval state** (Telegram): bridge persists per-session YOLO
  state and approval mappings under
  `HERMES_HOME/state/arclink-public-bridge/` (`sessions/`, `approvals/`). It
  hashes session keys/chat ids (sha256, 32 hex) before writing — no raw chat id
  on disk. A daemon watcher thread polls the mapping file and resolves the
  gateway approval (`tools.approval.resolve_gateway_approval`).
- Drains Hermes adapter background/batch tasks before exit
  (`_drain_bridge_adapter_tasks`) so debounced batches are not cancelled.

### 1.2 Gateway Exec Broker (`python/arclink_gateway_exec_broker.py`)

A narrow trusted-host HTTP broker that owns Docker exec authority for
Raven-mediated public-channel Agent replies. `SERVICE_NAME = "gateway-exec-broker"`,
default `127.0.0.1:8911`, env `ARCLINK_GATEWAY_EXEC_BROKER_{HOST,PORT,TOKEN}`.
Token header: `X-ArcLink-Gateway-Exec-Token` (from
`arclink_notification_delivery.GATEWAY_EXEC_BROKER_TOKEN_HEADER`).

- Routes: `GET /health`, `POST /v1/public-agent-bridge`. Max request 65536
  bytes. Auth via `hmac.compare_digest` against
  `ARCLINK_GATEWAY_EXEC_BROKER_TOKEN`.
- `require_docker_trusted_host_risk_accepted` gates both `main()` (SystemExit)
  and every request (ValueError). Refuses to start without the broker token.
- `_build_gateway_exec_command` **rejects raw command input** (`cmd`/`command`
  keys → "does not accept raw commands"). It reconstructs the only allowed
  command itself: `docker exec -i <container> <PUBLIC_AGENT_BRIDGE_PYTHON>
  <PUBLIC_AGENT_BRIDGE_SCRIPT>` where those constants come from
  `arclink_notification_delivery` (`/opt/arclink/runtime/hermes-venv/bin/python3`
  and `/home/arclink/arclink/python/arclink_public_agent_bridge.py`).
  - Two modes: **deployment mode** (validates `deployment_id`/`prefix`, derives
    `_compose_project_name`, requires `project_name == expected_project` and
    matches `PUBLIC_AGENT_BRIDGE_PROJECT_RE = ^arclink(?:-[a-z0-9][a-z0-9_-]{0,80})?$`,
    targets service `hermes-gateway`, with a `docker compose ... exec -T`
    fallback if no running container is found); and **operator_stack mode**
    (project must equal `ARCLINK_CONTROL_COMPOSE_PROJECT` default `arclink`,
    targets service `control-operator-hermes-gateway`).
  - Final command is re-validated by
    `delivery._validate_public_agent_bridge_cmd`.
  - Payload validated by `_validate_payload`: platform ∈ {telegram, discord};
    requires `bot_token`, `chat_id`, `user_id`, `text`; text ≤ 8000 chars.
    Timeout clamped 30..86400 (default 240).
- `_docker_binary` pins to a trusted Docker CLI via
  `require_trusted_docker_binary` / `TRUSTED_DOCKER_BINARY_PATHS`.
- On rejection, `_record_rejection_incident` writes a redacted JSONL row to
  `state_root_rejection_path("gateway-exec-broker")` =
  `ARCLINK_STATE_ROOT_BASE/_broker-incidents/gateway-exec-broker/rejections.jsonl`
  with reason codes (`raw_command_rejected`, `project_name_mismatch`,
  `unsupported_platform`, `command_not_allowlisted`, etc.). No raw payloads,
  tokens, chat ids, or message text.

The caller is the `notification-delivery` worker (GAP-019-F moved this socket
authority out of the worker into the broker).

### 1.3 Deployment Exec Broker (`python/arclink_deployment_exec_broker.py`)

Trusted-host broker owning the Docker socket for **deployment-scoped Compose
operations** on behalf of the local Control Node executor / provisioner / action
worker. `SERVICE_NAME = "deployment-exec-broker"`, default `127.0.0.1:8912`,
env `ARCLINK_DEPLOYMENT_EXEC_BROKER_{HOST,PORT,TOKEN}`. Token header:
`executor.DEPLOYMENT_EXEC_BROKER_TOKEN_HEADER`.

- Routes: `GET /health`, `POST /v1/docker-compose`. Max request 16384 bytes.
- `ALLOWED_OPERATIONS = {compose_up, compose_ps, compose_down}`. Rejects raw
  `args`/`cmd`/`command`. Rebuilds the args itself:
  `up -d --remove-orphans`, `ps [--all] --format json`,
  `down --remove-orphans [--volumes]`.
- Validates `deployment_id`, `project_name` (must equal expected), and that
  `env_file`/`compose_file` are absolute, share a parent (raw + normalized),
  are non-symlink dirs/regular-readable files under `ARCLINK_STATE_ROOT_BASE`
  (default `/arcdata/deployments`) via
  `executor._validate_deployment_config_paths` and local lstat checks.
- Executes through `executor.SubprocessDockerComposeRunner`.
- Same redacted rejection-incident pattern (state-root path), reasons like
  `operation_not_allowlisted`, `compose_config_rejected`, `project_name_rejected`.

### 1.4 Agent Supervisor Broker (`python/arclink_agent_supervisor_broker.py`)

Trusted-host broker that owns the Docker socket for the **dashboard
network/proxy sidecar** lifecycle on behalf of the Docker-mode agent supervisor
(which itself runs as root but holds no Docker socket).
`SERVICE_NAME = "agent-supervisor-broker"`, default `127.0.0.1:8913`,
env `ARCLINK_AGENT_SUPERVISOR_BROKER_{HOST,PORT,TOKEN}`. Token header:
`X-ArcLink-Agent-Supervisor-Broker-Token`.

- Routes: `GET /health`, `POST /v1/agent-supervisor`. Max 16384 bytes.
- Operations (rebuilt locally, raw commands rejected):
  - `ensure_dashboard_network` — creates an `--internal` Docker network
    `arclink-agent-dashboard-<agent>` and attaches the supervisor container,
    returning a validated backend host IP (`_require_backend_host`: loopback /
    private / link-local only, never wildcard/multicast/global).
  - `ensure_dashboard_proxy` — runs the dashboard auth-proxy sidecar
    `arclink-agent-dashboard-proxy-<agent>` (`docker run -d --rm --pull never`,
    publishes `127.0.0.1:<proxy_port>`, binds host→container private dir,
    config-hash label for idempotence) executing
    `python/arclink_dashboard_auth_proxy.py` with realm `Hermes`.
  - `remove_dashboard_proxy` — `docker rm -f` the proxy container.
- Validates private bind roots (`_require_private_bind_root`: must be canonical
  ArcLink `arclink-priv` path, container root pinned to
  `/home/arclink/arclink/arclink-priv`), agent ids, container names, ports.
- Redacted rejection incidents to `private_state_rejection_path(...)` under the
  container private dir.

### 1.5 Docker Agent Supervisor (`python/arclink_docker_agent_supervisor.py`)

The reconciliation loop (`main()`), running as root but **without a Docker
socket**. It polls active agents and drives the helper/broker family:

- `active_agents(cfg)` reads `agents` joined to `agent_identity` and
  `arclink_deployments` for active `role='user'` agents.
- Per agent it: validates context (`validated_agent_context`), ensures the
  container Unix user/home via `agent-user-helper`
  (`ensure_container_user` → `agent_user_helper_request`), repairs the ArcLink
  MCP bootstrap token, installs assets / runs identity / refresh / cron via
  `agent-process-helper` (`run_agent_once` → `agent_process_helper_request`),
  computes desired gateway/dashboard process specs (`desired_specs`), and
  ensures dashboard network + proxy via `agent-supervisor-broker`.
- `ensure_agent_processes` / `terminate_agent_processes` reconcile the long-lived
  gateway/dashboard processes in the process helper.
- `run_provisioner` runs `bin/arclink-enrollment-provision.sh` with a **narrowed
  child env** (`provisioner_child_env`, GAP-019-AQ): only Docker mode/path
  config, runtime roots, service URLs, and helper/broker URLs+tokens
  (`PROVISIONER_ALLOWED_PARENT_ENV_KEYS`).
- Broker/helper request helpers: `agent_supervisor_broker_request` (8913,
  15s timeout), `agent_user_helper_request` (8915, 15s),
  `agent_process_helper_request` (8916, default 3700s timeout via
  `ARCLINK_AGENT_PROCESS_HELPER_REQUEST_TIMEOUT_SECONDS`). Default broker URLs:
  `http://agent-supervisor-broker:8913`, etc.

### 1.6 Agent Process Helper (`python/arclink_agent_process_helper.py`)

Root-scoped HTTP helper that owns the **setpriv privilege-drop process
boundary** for Docker-mode agent commands. `SERVICE_NAME = "agent-process-helper"`,
default `127.0.0.1:8916`, env `ARCLINK_AGENT_PROCESS_HELPER_{HOST,PORT,TOKEN}`.
Token header: `X-ArcLink-Agent-Process-Helper-Token`. No Docker socket.

- Routes: `GET /health`, `POST /v1/agent-process`. Max 32768 bytes.
- Operations: `run_once` (kinds `install`/`identity`/`refresh`/`cron`),
  `ensure_processes` (long-lived kinds `gateway`/`dashboard`), `terminate_all`.
  Raw commands rejected at every level.
- Rebuilds allowlisted command targets only — fixed repo children
  (`bin/install-agent-user-services.sh`, `python/arclink_headless_hermes_setup.py`,
  `bin/user-agent-refresh.sh`, `bin/hermes-shell.sh`) re-validated as
  non-symlink, regular, readable/executable files.
- Drops privileges via `/usr/bin/setpriv --reuid --regid --clear-groups
  --no-new-privs --inh-caps=-all --ambient-caps=-all --bounding-set=-all`.
- Heavy env validation (`_require_env`): rejects ArcLink control-token keys
  (`AGENT_PROCESS_ENV_BLOCKLIST` plus any `ARCLINK_*_TOKEN`), rejects unapproved
  keys (`LD_*`, `PYTHONPATH`, `GIT_SSH*`, `BASH_ENV`, secret suffixes
  `_TOKEN/_SECRET/_PASSWORD/_KEY`), requires canonical HOME/USER/HERMES_HOME/
  workspace/uid/gid values, pins PATH to `SAFE_PATH`. Passes env via
  subprocess `env=` (not setpriv argv) so logs don't leak env (GAP-019-R).
- In-process registry `PROCESSES`/`PROCESS_SIGNATURES` with signature-based
  reconciliation; SIGTERM→SIGKILL termination via process groups.
- Redacted rejection incidents to
  `private_state_rejection_path("agent-process-helper", env_names=(ARCLINK_PRIV_DIR, ARCLINK_DOCKER_CONTAINER_PRIV_DIR))`
  → `state/docker/agent-process-helper/rejections.jsonl`.

### 1.7 Agent User Helper (`python/arclink_agent_user_helper.py`)

Root-scoped helper owning container-local **Unix user/home creation and chown**.
`SERVICE_NAME = "agent-user-helper"`, default `127.0.0.1:8915`,
env `ARCLINK_AGENT_USER_HELPER_{HOST,PORT,TOKEN}`. Token header:
`X-ArcLink-Agent-User-Helper-Token`. No Docker socket.

- Routes: `GET /health`, `POST /v1/agent-user`. Max 16384. Only op:
  `ensure_user_home`. Raw commands rejected.
- Allocates a deterministic uid/gid in the managed range
  `[20000, 60000)` (`AGENT_UID_MIN=20000`, `AGENT_UID_SPAN=40000`), persisted in
  `.arclink-user-ids.json` under the agent home root (canonical non-symlink
  regular-or-missing file; O_EXCL+O_NOFOLLOW write).
- Pins `groupadd`→`/usr/sbin/groupadd`, `useradd`→`/usr/sbin/useradd`,
  `chown`→`/usr/bin/chown` (`TRUSTED_ROOT_EXECUTABLES`); preflights before use.
- Creates `.config/systemd/user`, `.local/share/arclink-agent`,
  `.local/state/arclink-agent`, hermes home (`HERMES_HOME_SUFFIX =
  .local/share/arclink-agent/hermes-home`), workspace; recursive chown.
- Redacted rejection incidents to `agent_home_root_rejection_path(...)` =
  `<home-root>/.helper-incidents/agent-user-helper/rejections.jsonl`.

### 1.8 Pod Comms (`python/arclink_pod_comms.py`)

Cross/intra-Captain Agent-to-Agent messaging over the `arclink_pod_messages`
table. Resource kind `pod_comms` (`POD_COMMS_RESOURCE_KIND`).

- `send_pod_message`: requires distinct sender/recipient deployments (each
  linked to a Captain `user_id`). **Same-Captain** sends are allowed; **cross-
  Captain** sends require an active accepted `pod_comms` share grant
  (`find_active_pod_comms_grant` against `arclink_share_grants`,
  `_require_send_allowed`). Body ≤ 8000 chars (`POD_MESSAGE_MAX_BODY_CHARS`),
  ≤ 10 attachments (`POD_MESSAGE_MAX_ATTACHMENTS`), rate limited 60/60s
  (`check_arclink_rate_limit`, scope `pod_comms:<deployment>`). Attachments are
  **share-grant projection references only** (`_validate_attachment_refs`) —
  raw files are never embedded. Writes the message row (`status='queued'`),
  audit (`pod_message_sent`), event, and queues a `pod-message` channel-kind
  notification to the recipient agent.
- `list_pod_messages` (deployment/user scoped, inbox/outbox/all),
  `list_all_pod_messages` (operator), `mark_pod_message_delivered`,
  `redact_pod_message` (operator redaction → body cleared, status `redacted`).
- Statuses: `queued`, `delivered`, `failed`, `redacted`
  (table CHECK constraint, `arclink_control.py:1445`).
- Entry points: Hermes MCP tools `pod_comms.list`, `pod_comms.send`,
  `pod_comms.share-file` (`python/arclink_mcp_server.py`); hosted API
  `GET /user/comms` (own-user scoped) and `GET /admin/comms` (operator,
  body/attachments stripped). Share-grant kind `pod_comms` is registered in
  `arclink_api_auth.ARCLINK_SHARE_RESOURCE_KINDS`.

### 1.9 Rejection Incidents (`python/arclink_rejection_incidents.py`)

Shared redacted JSONL incident logger used by every broker/helper. Path
resolvers fail closed unless the configured state/priv/home root is absolute,
existing, non-symlink, canonical. `safe_metadata` only admits keys/values
matching `^[A-Za-z0-9_.:-]{1,160}$` (plus bools/ints). Rows carry timestamp,
service, event, `trusted_host_acknowledged`, error_class, reason, message, and
narrow safe metadata. O_APPEND|O_CREAT|O_NOFOLLOW|O_CLOEXEC, mode 0600.

### 1.10 Hermes Gateway Setup wrapper (`bin/arclink-hermes-gateway-setup.sh`)

Wraps `hermes gateway setup` so ArcLink-managed systemd persistence wins: it
monkeypatches `hermes_cli.gateway.prompt_yes_no` and
`install_linux_gateway_from_setup` to **skip Hermes-native service install/start
prompts** ("ArcLink manages gateway persistence with its own systemd units").
Falls back (exit 86) to plain `hermes gateway setup` if Hermes internals can't be
imported.

---

## 2. Compose wiring & trust boundary (the real GAP-019 shape)

All seven high-authority services live in `compose.yaml` and are inventoried in
`config/docker-authority-inventory.json` (services: `deployment-exec-broker`,
`migration-capture-helper`, `agent-user-helper`, `agent-process-helper`,
`agent-supervisor-broker`, `operator-upgrade-broker`, `gateway-exec-broker`).

Port/header/socket map (from code + compose):

| Service | Module | Port | Token env | Header | Docker socket | Root |
| --- | --- | --- | --- | --- | --- | --- |
| gateway-exec-broker | arclink_gateway_exec_broker.py | 8911 | ARCLINK_GATEWAY_EXEC_BROKER_TOKEN | X-ArcLink-Gateway-Exec-Token | yes | no |
| deployment-exec-broker | arclink_deployment_exec_broker.py | 8912 | ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN | (executor.*) | yes | no |
| agent-supervisor-broker | arclink_agent_supervisor_broker.py | 8913 | ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN | X-ArcLink-Agent-Supervisor-Broker-Token | yes | no |
| migration-capture-helper | (sep. subsystem) | 8914 | ARCLINK_MIGRATION_CAPTURE_HELPER_TOKEN | — | no | yes |
| agent-user-helper | arclink_agent_user_helper.py | 8915 | ARCLINK_AGENT_USER_HELPER_TOKEN | X-ArcLink-Agent-User-Helper-Token | no | yes (caps: CHOWN,DAC_OVERRIDE,FOWNER) |
| agent-process-helper | arclink_agent_process_helper.py | 8916 | ARCLINK_AGENT_PROCESS_HELPER_TOKEN | X-ArcLink-Agent-Process-Helper-Token | no | yes (setpriv) |
| operator-upgrade-broker | (sep. subsystem) | 8917 | ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN | — | no | yes |

Trust boundary invariants enforced in code:

1. **No raw commands**: every broker/helper rejects `cmd`/`command`/`args` keys
   and reconstructs the only allowed command/args locally.
2. **HMAC token gate** per request (`hmac.compare_digest`), plus per-service
   internal Compose network (`*-broker-net` / `*-net`, GAP-019-AK) so only
   legitimate callers can reach the listener.
3. **Trusted-host acknowledgement gate** (GAP-019-AL):
   `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED` must equal exactly `accepted`
   (`require_docker_trusted_host_risk_accepted` from `arclink_boundary`) or the
   service refuses to start AND every request fails closed.
4. **Trusted Docker binary** (GAP-019-AF/AG/AH): the three socket brokers pin to
   `TRUSTED_DOCKER_BINARY_PATHS` and reject PATH-injected/non-Docker binaries.
5. **Default bind `127.0.0.1`** for direct runs (GAP-019-AP); Compose is the
   explicit opt-in to `0.0.0.0` for internal request-network reachability.
6. **Redacted rejection incidents** (GAP-019-BB/BC/BD) — JSONL, no raw bodies /
   tokens / chat ids / message text / private paths / stack traces.

The honest residual risk: each socket broker still holds direct writeable Docker
socket access, and each root helper still has root authority. The command path
is narrowed but **not tenant-safe** — `GAP-019` remains OPEN, acknowledged-only.

---

## 3. Proof-gated / fake-adapter / local-only behavior

- **Whole subsystem is Docker-mode + trusted-host gated.** None of the seven
  brokers/helpers will even start unless
  `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED=accepted`. This is risk acceptance,
  not proof.
- **The public bridge is unit-tested only against a fake Hermes runtime.** Real
  delivery requires a live deployment `hermes-gateway` (or
  `control-operator-hermes-gateway`) container, a real bot token, and the Hermes
  runtime at `/opt/arclink/runtime/hermes-agent-src`. Live Telegram/Discord and
  Hermes behavior is gated by `PG-BOTS` / `PG-HERMES` (operations-runbook).
- **`ARCLINK_PUBLIC_AGENT_QUIET_FALLBACK`** — the degraded `hermes chat -Q`
  text-only path is fail-closed by default; only an operator opt-in re-enables it
  (`arclink_notification_delivery.py`).
- **Pod Comms delivery is not wired end-to-end.** `send_pod_message` queues a
  `pod-message` channel_kind notification, but the notification-delivery worker
  only resolves `discord`/`telegram`/`tui-only` channels
  (`arclink_notification_delivery.py:282`). `mark_pod_message_delivered` and
  `redact_pod_message` have **no production callers** outside the module/tests —
  they are implemented but not yet driven by any worker/route. So Pod Comms is
  send+store+list real, but cross-Pod *delivery* and operator redaction are
  local-only / proof-gated.
- **Discord bridge is not native parity.** No long-lived discord.py adapter, no
  attachments/voice/thread/member objects; only text/slash + REST send/edit/
  typing/reaction shims (see Parity audit). Telegram is closer because raw
  updates replay through native handlers.
- **Live agent supervisor reconciliation** (user creation, setpriv processes,
  dashboard sidecars) is Docker-mode-only and exercises real root authority on a
  trusted host; unit tests inject fakes.

---

## 4. Canonical vocabulary (exact names from code)

- Modules: `arclink_public_agent_bridge`, `arclink_gateway_exec_broker`,
  `arclink_deployment_exec_broker`, `arclink_agent_supervisor_broker`,
  `arclink_docker_agent_supervisor`, `arclink_agent_process_helper`,
  `arclink_agent_user_helper`, `arclink_pod_comms`,
  `arclink_rejection_incidents`, `arclink_dashboard_auth_proxy` (proxy target).
- Services: `gateway-exec-broker`, `deployment-exec-broker`,
  `agent-supervisor-broker`, `agent-user-helper`, `agent-process-helper`
  (+ adjacent `migration-capture-helper`, `operator-upgrade-broker`),
  `hermes-gateway` (per-deployment target container),
  `control-operator-hermes-gateway` (operator-stack target),
  `notification-delivery` (caller).
- Broker routes: `POST /v1/public-agent-bridge`, `POST /v1/docker-compose`,
  `POST /v1/agent-supervisor`, `POST /v1/agent-user`, `POST /v1/agent-process`,
  `GET /health` (all).
- Hosted API routes: `GET /api/v1/user/comms` (route key `user_comms`),
  `GET /api/v1/admin/comms` (route key `admin_comms`).
- MCP tools: `pod_comms.list`, `pod_comms.send`, `pod_comms.share-file`.
- Tables: `arclink_pod_messages` (statuses queued/delivered/failed/redacted),
  `arclink_share_grants` (resource_kind `pod_comms`).
- Process kinds: run-once `install`/`identity`/`refresh`/`cron`; long-lived
  `gateway`/`dashboard`. Process key format `<agent_id>:<kind>`.
- Supervisor broker operations: `ensure_dashboard_network`,
  `ensure_dashboard_proxy`, `remove_dashboard_proxy`. Deployment broker
  operations: `compose_up`, `compose_ps`, `compose_down`.
- Key constants/regex: `PUBLIC_AGENT_BRIDGE_PROJECT_RE
  (^arclink(?:-[a-z0-9][a-z0-9_-]{0,80})?$)`, `PUBLIC_AGENT_BRIDGE_PYTHON`,
  `PUBLIC_AGENT_BRIDGE_SCRIPT`, `GATEWAY_EXEC_BROKER_TOKEN_HEADER`,
  `HERMES_HOME_SUFFIX = .local/share/arclink-agent/hermes-home`,
  `AGENT_UID_MIN=20000`/`AGENT_UID_SPAN=40000`, `CONTAINER_PRIVATE_ROOT =
  /home/arclink/arclink/arclink-priv`, dashboard network
  `arclink-agent-dashboard-<agent>`, proxy container
  `arclink-agent-dashboard-proxy-<agent>`.
- Env knobs: `ARCLINK_PUBLIC_AGENT_BRIDGE_STREAMING`,
  `ARCLINK_PUBLIC_AGENT_QUIET_FALLBACK`,
  `ARCLINK_PUBLIC_AGENT_LIVE_TRIGGER[_RUNNER|_WORKERS|_MAX_PENDING]`,
  `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED`,
  `ARCLINK_AGENT_PROCESS_HELPER_REQUEST_TIMEOUT_SECONDS`,
  `ARCLINK_DOCKER_AGENT_HOME_ROOT`, `ARCLINK_DOCKER_HOST_PRIV_DIR`,
  `ARCLINK_DOCKER_CONTAINER_PRIV_DIR`.

---

## 5. Undocumented / newer than the docs

- **`GET /user/comms` and `GET /admin/comms` are missing from
  `docs/arclink/architecture.md`'s hosted-API route table** (lines 105-147).
  They exist in code (`arclink_hosted_api.py` route map `/user/comms`,
  `/admin/comms`).
- **Pod Comms is entirely absent from architecture.md** (table, isolation model,
  MCP tools, share-grant kind `pod_comms`). It only appears as a share grant in
  the sovereign symphony's sharing section, not as Agent-to-Agent messaging.
- **The entire broker/helper/supervisor family is absent from architecture.md.**
  architecture.md mentions "notification delivery" and "Raven bridges" in one
  sentence (line 154) but names none of these services, ports, tokens, or the
  trusted-host boundary. The only canonical home is operations-runbook.md's
  GAP-019 entries (which do not give the consolidated service/port/header map).
- **`operator_stack` mode of the gateway broker** (targeting
  `control-operator-hermes-gateway`) is not described in the three research
  notes — they only describe per-deployment `hermes-gateway`. This is newer than
  those 2026-05-11 docs.
- **Durable exec-approval bridging for Telegram `ea:` callbacks** (on-disk
  approval mappings + watcher thread + YOLO session persistence) is implemented
  in `arclink_public_agent_bridge.py` but not mentioned in any research note.
- **GAP-019 sub-tasks AF..BD** (trusted Docker binary pin, config-file boundary,
  private-bind-root validation, backend-host class, rejection incidents,
  internal networks, trusted-host ack gate, 127.0.0.1 default bind) are all
  newer than the three research notes and are only captured in the runbook.

---

## 6. Per-doc staleness verdicts

### `docs/arclink/architecture.md` — HEAVY (missing-coverage)
Does not document this subsystem at all. Required additions:
- A "Public Agent Gateway" section: bridge process, event-mux design, the
  per-turn `docker exec` shape, and the warm-bridge target.
- A "Trusted-Host Brokers & Helpers" section with the service/port/token/header/
  socket/root table from §2 and the GAP-019 trust-boundary invariants.
- A "Pod Comms" entry in the module map, isolation model, and the route table
  (`GET /user/comms`, `GET /admin/comms`), plus the `pod_comms` MCP tools and
  share-grant kind.
- Module-map rows for the eight modules in §4.

### `research/PUBLIC_AGENT_GATEWAY_PARITY_AND_SCALE_AUDIT.md` — LIGHT/HEAVY
Status line is 2026-05-11. Still broadly accurate on parity/scale gaps. Stale:
- Cites old line numbers in `arclink_public_agent_bridge.py` (e.g. `:78`, `:157`,
  `:227`, `:293`, `:354`) that no longer match the current file (now 784 lines
  with reorganized functions). Line references should be replaced with function
  names (`_public_bridge_streaming_enabled`, `_run_discord`, `_DiscordRawMessage`,
  etc.).
- Cites `arclink_public_bots.py:1717` / `arclink_notification_delivery.py:348/464`
  — verify and refresh these.
- Does not mention the gateway-exec-broker indirection (the worker no longer
  shells directly; it calls `gateway-exec-broker`, GAP-019-F). Update the "shells
  into the deployment container" claim to "asks `gateway-exec-broker` to run the
  bridge `docker exec`."
- The warm-bridge "next build" remains unbuilt (accurate as a target).

### `research/PUBLIC_AGENT_GATEWAY_PERFORMANCE_PLAN.md` — LIGHT
2026-05-11. Backpressure contract and durable-outbox/claim-lease description
still match intent. Stale:
- "the worker currently shells into the deployment's `hermes-gateway` container
  and starts `arclink_public_agent_bridge.py`" should note the broker hop
  (`gateway-exec-broker`) introduced after this note.
- Warm-bridge target (§"Target Load-Balanced Shape" / "Next Build Task") is still
  unbuilt — accurate as forward-looking.

### `research/PUBLIC_AGENT_NATIVE_EVENT_MUX_DESIGN.md` — LIGHT
2026-05-11. The "first slice" (Telegram raw-update replay through native
handlers) is accurate and matches `_try_replay_native_telegram_update`. The
remaining mux build (warm deployment bridge, native Discord edge, ABI guardrails)
is still future work. Add: the durable exec-approval `ea:` callback bridging now
exists for Telegram; and the gateway-exec-broker is the current command hop.

### `docs/arclink/sovereign-control-node-symphony.md` — LIGHT (dream-shape doc)
Only touches this subsystem via `GAP-019` (line 405: "root/Docker authority risk
is already tracked by GAP-019") and Pod Comms appears only as sharing, not as
Agent messaging. As the intended dream shape it is not wrong, but it under-states
that the broker/helper split (the GAP-019 mitigation) is already substantially
implemented in code. A pointer to the GAP-019 family and Pod Comms messaging
would align it.

### `docs/arclink/operations-runbook.md` — FRESH (authoritative for GAP-019)
The GAP-019-* entries (lines ~409-770) are the accurate, current source for the
trust boundary. They match the code. This is the right place; architecture.md
should cross-link here rather than duplicate.

---

## 7. GAP status touched by this subsystem (true current status)

- **`GAP-019` (root/Docker authority): OPEN — acknowledged residual risk only.**
  The command path is narrowed via seven command-specific brokers/helpers with
  raw-command rejection, HMAC tokens, internal networks, trusted Docker-binary
  pins, path/symlink validation, and redacted rejection incidents. But each
  socket broker still owns a writeable Docker socket and each root helper still
  runs as root, so it is **not tenant-safe**. Gated behind
  `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED=accepted` (GAP-019-AL).
- **GAP-019 sub-tasks implemented in this subsystem's code (DONE):** `-C`, `-F`,
  `-Y`, `-AH`, `-AY`, `-BC` (gateway broker); `-G`, `-H`, `-E`, `-AA`, `-AG`,
  `-AX`, `-BD` (deployment broker); `-I`, `-Z`, `-AF`, `-AZ`, `-AR`, `-BD`
  (agent-supervisor broker); `-O`, `-Q`, `-AE`, `-BA`, `-AN`, `-AS`, `-BD`
  (agent-user-helper); `-P`, `-R`, `-W`, `-AM`, `-AD`, `-AJ`, `-AT`, `-AU`,
  `-AO`, `-BB`, `-AR` (agent-process-helper); `-AK`, `-AL`, `-AP` (cross-cutting
  Compose/network/bind-host). `-AQ` (provisioner child-env narrowing) is in
  `arclink_docker_agent_supervisor.provisioner_child_env`. `-B2` is the
  recorded decision rejecting a generic socket proxy.
- **`GAP-029` (Operator Raven full-service control plane): OPEN/partial** — not
  owned here, but the gateway broker's `operator_stack` mode and the
  `control-operator-hermes-gateway` target are part of the operator chat bridge.
- **Live proof gates referenced as separate and still pending:** `GAP-001`,
  `PG-UPGRADE`, `PG-PROVISION`, `PG-BOTS`, `PG-HERMES`, `GAP-022` (SOUL/Crew
  generation). These do not block source-level implementation but gate live
  Telegram/Discord/Hermes/provision proof.

---

## 8. Owning code files

- `python/arclink_public_agent_bridge.py`
- `python/arclink_gateway_exec_broker.py`
- `python/arclink_deployment_exec_broker.py`
- `python/arclink_agent_supervisor_broker.py`
- `python/arclink_docker_agent_supervisor.py`
- `python/arclink_agent_process_helper.py`
- `python/arclink_agent_user_helper.py`
- `python/arclink_pod_comms.py`
- `python/arclink_rejection_incidents.py`
- `bin/arclink-hermes-gateway-setup.sh`
- Callers/peers: `python/arclink_notification_delivery.py` (bridge command
  constants + broker client), `python/arclink_mcp_server.py` (pod_comms tools),
  `python/arclink_hosted_api.py` (`/user/comms`, `/admin/comms`),
  `python/arclink_api_auth.py` (`pod_comms` share-grant kind),
  `python/arclink_control.py` (`arclink_pod_messages` schema),
  `compose.yaml` (service definitions), `config/docker-authority-inventory.json`.
