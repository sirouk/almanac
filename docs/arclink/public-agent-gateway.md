# ArcLink Public Agent Gateway, Trusted-Host Brokers & Pod Comms

**Status: Canonical (security-sensitive boundary).** This document is the canonical home
for three tightly-coupled subsystems that were previously absent from
`docs/arclink/architecture.md`:

1. **Public Agent Gateway** — the boundary process that replays a public Telegram/Discord
   turn through a Hermes Agent's own native gateway pipeline inside its ArcPod container.
2. **Trusted-Host Brokers & Helpers** — the seven high-authority Compose services
   (ports 8911–8917) that own the Docker socket and root authority on the Control Node host.
3. **Pod Comms** — Agent-to-Agent messaging over `arclink_pod_messages`.

Honesty boundary, stated up front and non-negotiable: **the entire broker/helper family is
risk-accepted under GAP-019, not tenant-safe.** Each socket broker holds a writeable Docker
socket; each root helper runs as root. GAP-019 is **OPEN — acknowledged residual risk only.**
The command path is narrowed (raw-command rejection, HMAC tokens, internal networks, trusted
Docker-binary pins, path/symlink validation, redacted rejection incidents) but a compromise of
any one of these processes is a host compromise. The whole family refuses to start unless
`ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED=accepted`.

**Cross-links (do not duplicate here):**
- **Trust boundary (authoritative):** the `GAP-019-*` entries in
  [`operations-runbook.md`](operations-runbook.md) are the canonical, current source for the
  trusted-host boundary. This doc summarizes the consolidated service map; the runbook owns the
  per-sub-item ledger.
- **Route catalog:** [`docs/API_REFERENCE.md`](../API_REFERENCE.md) and
  [`docs/openapi/arclink-v1.openapi.json`](../openapi/arclink-v1.openapi.json) own the hosted
  API route table (`GET /user/comms`, `GET /admin/comms`).
- **Gap taxonomy:** [`GAPS.md`](../../GAPS.md) owns the GAP-* ledger (GAP-019, GAP-023, GAP-029).

---

## 1. Public Agent Gateway

**Module:** `python/arclink_public_agent_bridge.py`
**Per-turn invocation:** `gateway-exec-broker` (`arclink_gateway_exec_broker.py`) does a single
`docker exec` of the bridge into the target Hermes gateway container.

### 1.1 What it is

The bridge is a **short-lived boundary process run inside a Hermes Agent's gateway container**.
ArcLink's public Raven bot owns the Telegram/Discord webhooks, so a Captain's message to their
selected Agent does not arrive natively at the Agent's gateway. The bridge closes that gap: it
reads a JSON payload from stdin and **replays the public turn through Hermes' own native gateway
pipeline** so the turn behaves like a native active-Agent channel message (sessions, slash
commands, typing, reactions, interim messages, delivery formatting, plugin hooks) rather than a
quiet, Raven-mediated CLI call.

`main()` reads the payload (`_payload_from_stdin`), runs `_run`, and prints a single-line JSON
result. Success is three-valued: `confirmed` means the bridge observed real platform message ids
and sets `delivered: true`; `unknown` means Hermes processed the turn but ArcLink did not capture
a platform ack and must not mark the outbox row delivered; `failed` means the send/edit failed.
Failure prints `{"ok": false, "error": ...}` (error truncated to 500 chars), exit 1. It adds the
Hermes runtime source dir to `sys.path` from `HERMES_AGENT_SRC` or
`RUNTIME_DIR/hermes-agent-src` (default runtime root `/opt/arclink/runtime`).

It dispatches on `payload["platform"]`, which must be `telegram` or `discord`; any other value
raises "public agent gateway bridge does not support platform ...".

### 1.2 Telegram — native-handler replay

`_run_telegram` builds a real `telegram.Bot`, loads `gateway.config.load_gateway_config()`,
forces the Telegram `PlatformConfig` on with a synthetic `HomeChannel`, constructs a Hermes
`GatewayRunner`, creates the native Telegram adapter, and wires `runner._handle_message`, the
session store, the busy-session handler, and a `SessionSource`.

- When `payload["telegram_update_json"]` is present, it rebuilds the PTB `Update` and dispatches
  it to Hermes' **own native adapter handlers** (`_try_replay_native_telegram_update`):
  `_handle_command` / `_handle_text_message` for text, `_handle_location_message` for
  location/venue, `_handle_media_message` for photo/video/audio/voice/document/sticker, and
  `_handle_callback_query` for inline callbacks.
- Non-Raven inline callbacks preserve raw update JSON and a callback-family marker for `ea`,
  `mp`, `sc`, and `cl`. `ea:` (exec-approval) is bridged to a **durable approval mapping on
  disk** (see §1.5); the other families are replay/audit metadata until the
  `durable_callback_replay_proof` gate lands. Raven's own callbacks use the `arclink:`
  namespace and are handled by Raven ingress, not by the bridge.
- If no raw update is present, the bridge falls back to a synthetic `MessageEvent`
  (`MessageType.COMMAND` for `/`-prefixed text, else `MessageType.TEXT`).

### 1.3 Discord — REST shims (NOT native parity)

`_run_discord` is **deliberately not native parity.** There is no long-lived `discord.py`
adapter, no attachment/voice/thread/member objects. Instead it uses a minimal `_DiscordRest`
(aiohttp) client against `https://discord.com/api/v10`, monkeypatches the adapter's `send`,
`edit_message`, `send_typing`, and `stop_typing` to REST shims, plus a `_DiscordRawMessage` shim
implementing `add_reaction`/`remove_reaction`, then dispatches a single synthetic `MessageEvent`
(TEXT or COMMAND). Outbound sends can carry components, embeds, and attachment metadata with
default-deny mentions, but Telegram is still closer to native because raw updates replay through
Hermes' real handlers; Discord remains **message/slash + REST shims**, not a full `discord.py`
object graph. Any doc describing the public Discord Agent surface must state this asymmetry.

### 1.4 Streaming — default ON (GAP-023)

`_public_bridge_streaming_enabled()` reads `ARCLINK_PUBLIC_AGENT_BRIDGE_STREAMING` and is
**ON by default** (only the standard false values turn it off). When enabled,
`_enable_public_bridge_gateway_defaults` forces Hermes `streaming.enabled = True` and, when no
transport is set, `streaming.transport = "edit"` for public-bridge turns, and sets
`HERMES_TOOL_PROGRESS_MODE=all`. It **intentionally does not enable `show_reasoning`** — Captains
get typing/progress/streamed deltas, never the Agent's internal reasoning.

> **Captain experience (Raven lore voice).** When you message your Agent on the line, the reply
> streams back live — you see it think out loud in motion, Captain, not a silent pause and a
> wall of text. Tap once and the deck lights up.

GAP-023 is tracked in [`GAPS.md`](../../GAPS.md): selected-Agent streaming is **opt-in at the
product level** — the historic framing was "streaming opt-in" — but the bridge knob itself
defaults on; the operator can disable it per-home with the env knob.

### 1.5 Durable exec-approval state (Telegram `ea:` callbacks)

For Telegram, the bridge persists per-session YOLO state and exec-approval mappings under
`HERMES_HOME/state/arclink-public-bridge/` (`BRIDGE_STATE_DIRNAME = "arclink-public-bridge"`),
in `sessions/` and `approvals/<platform>/` subtrees. **Session keys and chat ids are hashed
(sha256, first 32 hex) before they are written — no raw chat id ever lands on disk.** A daemon
watcher thread polls the mapping file and resolves the gateway approval through
`tools.approval.resolve_gateway_approval`, so a Captain's "approve / deny" tap on an exec-approval
button survives across the short-lived bridge invocation. Before exit, the bridge drains Hermes
adapter background/batch tasks (`_drain_bridge_adapter_tasks`) so debounced batches are not
cancelled mid-flight.

### 1.6 Per-turn `docker exec` via the gateway exec broker

The `notification-delivery` worker does **not** shell into the deployment container directly
(GAP-019-F moved that socket authority out of the worker). Instead it calls `gateway-exec-broker`
(`POST /v1/public-agent-bridge`, header `X-ArcLink-Gateway-Exec-Token`). The broker:

- **Rejects raw command input** (`cmd`/`command` keys → "gateway exec broker does not accept raw
  commands") and reconstructs the only allowed command itself:
  `docker exec -i <container> <PUBLIC_AGENT_BRIDGE_PYTHON> <PUBLIC_AGENT_BRIDGE_SCRIPT>`, where
  the constants come from `arclink_notification_delivery`
  (`/opt/arclink/runtime/hermes-venv/bin/python3` and
  `/home/arclink/arclink/python/arclink_public_agent_bridge.py`).
- Operates in two modes:
  - **Deployment mode** — validates `deployment_id`/`prefix`, derives the Compose project name,
    requires it to match the expected project and the regex
    `PUBLIC_AGENT_BRIDGE_PROJECT_RE = ^arclink(?:-[a-z0-9][a-z0-9_-]{0,80})?$`, targets service
    `hermes-gateway`, and falls back to `docker compose ... exec -T` if no running container is
    found.
  - **Operator-stack mode** — project must equal `ARCLINK_CONTROL_COMPOSE_PROJECT` (default
    `arclink`); targets service `control-operator-hermes-gateway` (the Operator's single in-stack
    Hermes Agent's gateway).
- Validates the payload (`_validate_payload`): platform ∈ {telegram, discord}; requires
  `bot_token`, `chat_id`, `user_id`, `text`; `text` ≤ 8000 chars; timeout clamped to 30..86400
  seconds (default 240).
- Pins the Docker binary to a trusted CLI via `require_trusted_docker_binary` /
  `TRUSTED_DOCKER_BINARY_PATHS`, and re-validates the final command through
  `delivery._validate_public_agent_bridge_cmd`.

### 1.7 Delivery evidence, leases, and cold-start posture

The bridge is intentionally still a **fresh per-turn process**. The daemon, prefork pool, and
warm sidecar designs were rejected because they break the control-side durability handoff and
the release lock-step property: the worker that writes `notification_outbox.delivered_at` runs
on the Control Node, while the Hermes send happens inside the ArcPod container.

Current production contract:

- Telegram wraps the Hermes adapter's send/edit/media/approval methods and records returned
  `SendResult.message_id` / split-message ids.
- Discord's REST shims record returned Discord message ids from sends and edits.
- `gateway-exec-broker` preserves the bridge result in its HTTP response; it no longer reduces a
  clean subprocess exit to `{ok:true}`.
- `notification-delivery` only calls `mark_notification_delivered` when the normalized result is
  `delivered=true` with at least one message id. An `unknown` result is held as
  `PROCESSED_UNCONFIRMED_BY_PUBLIC_AGENT_BRIDGE` with a long reconciliation retry instead of
  immediately sending a duplicate turn.
- Detached bridge workers record their PID in the outbox row. The notification worker re-arms
  stale leased rows when that recorded worker is gone, closing the old long silent-stall window
  without bypassing `_claim_notification_for_delivery`.
- Retry backoff now includes deterministic per-row jitter so correlated delivery failures do not
  retry in lock-step.

Latency work stays on the cold-spawn path. `ensure_shared_hermes_runtime` runs a deploy-time
`compileall` warmup (`ARCLINK_HERMES_COMPILEALL_ENABLED=1` by default) so fresh bridge processes
can reuse bytecode. Future safe layers are single-platform config starvation and a root-owned
Telegram `getMe` cache, both default-off until live proof.

### 1.8 Proof-gated and degraded paths

- **Live delivery is PG-PUBLIC-AGENT-DELIVERY / PG-BOTS / PG-HERMES.** The D5 delivery-evidence
  contract is locally regression-tested, but real Telegram/Discord proof still requires a live
  `hermes-gateway` (or `control-operator-hermes-gateway`) container, a real bot token, and the
  Hermes runtime under `/opt/arclink/runtime`. Durable callback replay, broader Discord
  media/components, free-text Gateway ingress, and Hermes browser/workspace behavior remain live
  proof-gated.
- **Degraded quiet fallback is fail-closed.** The `hermes chat -Q` text-only path
  (`ARCLINK_PUBLIC_AGENT_QUIET_FALLBACK`, in `arclink_notification_delivery`) is off by default;
  re-enabling it is an explicit operator opt-in because it hides bridge failures.

---

## 2. Trusted-Host Brokers & Helpers (GAP-019 family)

### 2.1 The invariant (read this first)

**GAP-019 is OPEN — acknowledged residual risk only. This family is risk-accepted, NOT
tenant-safe.** Each of the three socket brokers (`gateway-exec-broker`, `deployment-exec-broker`,
`agent-supervisor-broker`) holds a **writeable Docker socket**, and each root helper
(`migration-capture-helper`, `agent-user-helper`, `agent-process-helper`,
`operator-upgrade-broker`) **runs as root**. The command path is narrowed, but the underlying
authority is unchanged. The whole family is Docker-mode + trusted-host gated:
`ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED` must equal exactly `accepted`
(`require_docker_trusted_host_risk_accepted` from `arclink_boundary`, GAP-019-AL) or each service
**refuses to start AND every request fails closed.** See [`operations-runbook.md`](operations-runbook.md)
GAP-019 entries for the authoritative sub-item ledger.

### 2.2 Service / port / token / header / socket / root map

All seven high-authority services are defined in `compose.yaml` and inventoried in
`config/docker-authority-inventory.json`. Verified against code (ports, `SERVICE_NAME`, token env,
header constants) and `compose.yaml` (caps):

| Service | Module | Port | Token env | Header | Docker socket | Root |
| --- | --- | --- | --- | --- | --- | --- |
| `gateway-exec-broker` | `arclink_gateway_exec_broker` | 8911 | `ARCLINK_GATEWAY_EXEC_BROKER_TOKEN` | `X-ArcLink-Gateway-Exec-Token` | yes | no |
| `deployment-exec-broker` | `arclink_deployment_exec_broker` | 8912 | `ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN` | (`executor.DEPLOYMENT_EXEC_BROKER_TOKEN_HEADER`) | yes | no |
| `agent-supervisor-broker` | `arclink_agent_supervisor_broker` | 8913 | `ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN` | `X-ArcLink-Agent-Supervisor-Broker-Token` | yes | no |
| `migration-capture-helper` | `arclink_migration_capture_helper` | 8914 | `ARCLINK_MIGRATION_CAPTURE_HELPER_TOKEN` | `X-ArcLink-Migration-Capture-Helper-Token` | no | yes |
| `agent-user-helper` | `arclink_agent_user_helper` | 8915 | `ARCLINK_AGENT_USER_HELPER_TOKEN` | `X-ArcLink-Agent-User-Helper-Token` | no | yes (caps: `CHOWN`, `DAC_OVERRIDE`, `FOWNER`) |
| `agent-process-helper` | `arclink_agent_process_helper` | 8916 | `ARCLINK_AGENT_PROCESS_HELPER_TOKEN` | `X-ArcLink-Agent-Process-Helper-Token` | no | yes (setpriv) |
| `operator-upgrade-broker` | `arclink_operator_upgrade_broker` | 8917 | `ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN` | `X-ArcLink-Operator-Upgrade-Broker-Token` | no | yes |

### 2.3 Trust-boundary controls enforced in code

Every broker/helper applies the same defense pattern. None of these makes the family tenant-safe;
they narrow the blast radius of the accepted risk.

1. **No raw commands.** Each service rejects `cmd`/`command`/`args` keys and reconstructs the only
   allowed command/args locally (gateway broker: the bridge `docker exec`; deployment broker:
   `up -d --remove-orphans` / `ps [--all] --format json` / `down --remove-orphans [--volumes]`;
   supervisor broker: dashboard network/proxy lifecycle; process helper: fixed allowlisted repo
   children; user helper: `ensure_user_home` only).
2. **HMAC token gate** per request via `hmac.compare_digest` against the per-service token env.
3. **Per-service internal Compose network** (GAP-019-AK) so only legitimate callers can reach the
   listener.
4. **Trusted Docker-binary pin** (GAP-019-AF/AG/AH): the three socket brokers pin to
   `TRUSTED_DOCKER_BINARY_PATHS` and reject PATH-injected or non-Docker binaries.
5. **Path/symlink validation.** Config and bind roots are validated as absolute, non-symlink,
   canonical, and confined (e.g. the deployment broker's `_validate_deployment_config_paths`
   under `ARCLINK_STATE_ROOT_BASE` default `/arcdata/deployments`; the supervisor broker's
   `_require_private_bind_root` pinned to the canonical `arclink-priv` path
   `/home/arclink/arclink/arclink-priv`).
6. **Default bind `127.0.0.1`** for direct runs (GAP-019-AP); Compose is the explicit opt-in to
   `0.0.0.0` for internal request-network reachability.
7. **Redacted rejection incidents** (GAP-019-BB/BC/BD): JSONL with no raw bodies, tokens, chat
   ids, message text, private paths, or stack traces — see §2.5.

### 2.4 Per-service detail

- **`gateway-exec-broker` (8911, Docker socket, non-root).** Owns per-turn `docker exec` of the
  public-agent bridge — see §1.6. Caller: `notification-delivery` worker.
- **`deployment-exec-broker` (8912, Docker socket, non-root).** Owns deployment-scoped Compose
  ops for the local executor/provisioner/action-worker. `ALLOWED_OPERATIONS = {compose_up,
  compose_ps, compose_down}`, executed through `executor.SubprocessDockerComposeRunner`. (Also
  cross-linked from [`backup-restore.md`](backup-restore.md) for the Docker lifecycle.)
- **`agent-supervisor-broker` (8913, Docker socket, non-root).** Owns the dashboard
  network/proxy sidecar lifecycle: `ensure_dashboard_network` (creates an `--internal` Docker
  network `arclink-agent-dashboard-<agent>` and returns a validated loopback/private/link-local
  backend host — never wildcard/multicast/global), `ensure_dashboard_proxy` (runs the
  `arclink-agent-dashboard-proxy-<agent>` sidecar executing
  `python/arclink_dashboard_auth_proxy.py`), and `remove_dashboard_proxy`.
- **`migration-capture-helper` (8914, root, no socket).** Root helper for migration
  capture/materialize. Live migration capture is double-gated
  (`ARCLINK_ACTION_WORKER_ALLOW_ROOT_MIGRATION_CAPTURE=1` + helper); see pod-migration coverage.
- **`agent-user-helper` (8915, root + caps, no socket).** Sole op `ensure_user_home`. Allocates a
  deterministic uid/gid in the managed range `[20000, 60000)` (`AGENT_UID_MIN=20000`,
  `AGENT_UID_SPAN=40000`), persisted in `.arclink-user-ids.json` (canonical, O_EXCL+O_NOFOLLOW),
  pins `groupadd`/`useradd`/`chown` to trusted absolute paths, and creates the container Unix
  home (`HERMES_HOME_SUFFIX = .local/share/arclink-agent/hermes-home`) with recursive chown.
- **`agent-process-helper` (8916, root setpriv, no socket).** Owns the **setpriv privilege-drop
  process boundary** for Docker-mode agent commands. Ops `run_once` (kinds
  `install`/`identity`/`refresh`/`cron`), `ensure_processes` (long-lived `gateway`/`dashboard`),
  `terminate_all`. Drops privileges via
  `/usr/bin/setpriv --reuid --regid --clear-groups --no-new-privs --inh-caps=-all
  --ambient-caps=-all --bounding-set=-all`, pins PATH to `SAFE_PATH`, blocks ArcLink control-token
  keys and any `ARCLINK_*_TOKEN` plus `LD_*`/`PYTHONPATH`/`GIT_SSH*`/secret-suffix keys, and
  passes env via subprocess `env=` rather than setpriv argv so logs do not leak env (GAP-019-R).
- **`operator-upgrade-broker` (8917, root, no socket).** Docker-mode operator host-upgrade broker;
  live host upgrades require Docker mode + `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED=accepted`
  (PG-UPGRADE).

The **Docker agent supervisor** (`arclink_docker_agent_supervisor.py`) is the root reconciliation
loop that drives the helper/broker family but **holds no Docker socket itself**. It reads active
`role='user'` agents, ensures the container Unix user/home via `agent-user-helper`, runs
install/identity/refresh/cron and the long-lived gateway/dashboard processes via
`agent-process-helper`, ensures the dashboard network/proxy via `agent-supervisor-broker`, and
runs the provisioner with a **narrowed child env** (`provisioner_child_env`, GAP-019-AQ).

### 2.5 Redacted rejection incidents

**Module:** `python/arclink_rejection_incidents.py`. The shared JSONL logger used by every
broker/helper. Path resolvers fail closed unless the configured state/priv/home root is absolute,
existing, non-symlink, and canonical. `safe_metadata` only admits keys/values matching
`^[A-Za-z0-9_.:-]{1,160}$` (plus bools/ints). Rows carry timestamp, service, event,
`trusted_host_acknowledged`, error class, reason, message, and narrow safe metadata only —
**no raw payloads, tokens, chat ids, message text, private paths, or stack traces.** Files are
opened `O_APPEND|O_CREAT|O_NOFOLLOW|O_CLOEXEC`, mode `0600`. Reason codes are coarse
(`raw_command_rejected`, `project_name_mismatch`, `unsupported_platform`,
`command_not_allowlisted`, `operation_not_allowlisted`, `compose_config_rejected`, etc.).

> **Operator note (precise/auditable voice).** Rejection incidents are local redacted JSONL only
> (under each service's state/priv/home root). There is **no operator-visible aggregate incident
> read model** — `arclink_evidence_runs` exists but is unwired. Do not assume a dashboard surfaces
> these; inspect the per-service `rejections.jsonl` files on the host.

---

## 3. Pod Comms (Agent-to-Agent messaging)

**Module:** `python/arclink_pod_comms.py`. **Table:** `arclink_pod_messages`.
**Resource kind:** `pod_comms` (`POD_COMMS_RESOURCE_KIND`).

### 3.1 Isolation model

`send_pod_message` requires distinct sender and recipient deployments, each linked to a Captain
`user_id`:

- **Same-Captain (intra-Crew) sends are allowed** outright.
- **Cross-Captain sends require an active, accepted `pod_comms` share grant**
  (`find_active_pod_comms_grant` against `arclink_share_grants`, enforced by
  `_require_send_allowed`). The `pod_comms` kind is a first-class share-resource kind
  (`arclink_api_auth.ARCLINK_SHARE_RESOURCE_KINDS = {drive, code, pod_comms, notion}`); its root
  must be `pod_comms`.

Limits: body ≤ 8000 chars (`POD_MESSAGE_MAX_BODY_CHARS`), ≤ 10 attachments
(`POD_MESSAGE_MAX_ATTACHMENTS`), rate limited 60/60s (`check_arclink_rate_limit`, scope
`pod_comms:<deployment>`). **Attachments are share-grant projection references only**
(`_validate_attachment_refs`) — raw files are never embedded in a message body. On send the
module writes the message row (`status='queued'`), an audit row (`pod_message_sent`), an event,
and queues a `pod-message` channel-kind notification to the recipient Agent.

Message statuses (table CHECK constraint, `arclink_control.py`): `queued`, `delivered`, `failed`,
`redacted` (default `queued`).

### 3.2 Entry points

- **MCP tools** (`python/arclink_mcp_server.py`): `pod_comms.list`, `pod_comms.send`,
  `pod_comms.share-file`.
- **Hosted API** (route table owned by [`API_REFERENCE.md`](../API_REFERENCE.md)):
  `GET /user/comms` (Captain-scoped inbox/outbox with message narratives) and `GET /admin/comms`
  (Operator metadata only — message bodies and attachments are withheld).
- Read helpers: `list_pod_messages` (deployment/user scoped, inbox/outbox/all),
  `list_all_pod_messages` (operator).

### 3.3 What is real vs unwired

- **Real (implemented and tested locally):** send + store + list, the same-Captain / cross-Captain
  grant gate, attachment-as-projection-ref validation, rate limiting, audit/event/notification
  enqueue.
- **UNWIRED — no production callers:** cross-Pod **delivery** and operator **redaction**.
  `send_pod_message` enqueues a `pod-message` channel-kind notification, but the
  `notification-delivery` worker only resolves `discord` / `telegram` / `tui-only` channels — it
  does not deliver a `pod-message` to a recipient Agent. `mark_pod_message_delivered` and
  `redact_pod_message` are implemented and tested but have **no production callers** outside the
  module/tests. So Pod Comms is **send+store+list real; cross-Pod delivery and operator redaction
  are local-only / proof-gated.**

> **Captain experience (Raven lore voice).** Your Agents can pass word to one another on the line,
> Captain — within your own Crew freely, and across to another Captain's deck only once a sharing
> grant is signed and accepted. Files never ride raw in the message; only a sealed reference to a
> shared resource crosses.

> **Operator note (precise/auditable voice).** `GET /admin/comms` returns metadata only (no
> bodies/attachments). Operator redaction (`redact_pod_message`) exists in code but is not wired to
> any route or worker today — do not document it as an operator action.

---

## 4. Gap and proof-gate summary

| Item | Status | Gate |
| --- | --- | --- |
| Trusted-host broker/helper family (Docker socket + root) | OPEN, acknowledged-only — **not tenant-safe** | GAP-019; `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED=accepted` |
| Public bridge delivery evidence | Source-real + local regression-tested | PG-PUBLIC-AGENT-DELIVERY for live Telegram/Discord |
| Public bridge live Telegram/Discord delivery | Proof-gated | PG-BOTS / PG-HERMES |
| Public bridge streaming default-on | Real (env knob) | GAP-023 (`ARCLINK_PUBLIC_AGENT_BRIDGE_STREAMING`) |
| Bridge cold-start daemon/pool/sidecar | Rejected | cold-spawn only; compileall warmup landed |
| Discord native parity | Not built (text/slash + REST shims) | PG-BOTS |
| Operator-stack bridge target (`control-operator-hermes-gateway`) | Real path | part of GAP-029 operator chat bridge |
| Pod Comms send/store/list | Real (local) | — |
| Pod Comms cross-Pod delivery + operator redaction | Unwired (no production callers) | local-only / proof-gated |
| Operator host upgrade via `operator-upgrade-broker` | Risk-accepted | GAP-019; PG-UPGRADE |
| Live migration capture via `migration-capture-helper` | Proof-gated (double-gated) | `ARCLINK_ACTION_WORKER_ALLOW_ROOT_MIGRATION_CAPTURE=1` |

For the authoritative trust-boundary detail, see the `GAP-019-*` entries in
[`operations-runbook.md`](operations-runbook.md). For the GAP-* taxonomy, see
[`GAPS.md`](../../GAPS.md). For the hosted route catalog, see
[`API_REFERENCE.md`](../API_REFERENCE.md) and [`docs/openapi/`](../openapi/arclink-v1.openapi.json).
