# Shared Host Docker Deployment

This is the Docker Compose path for local and portable Shared Host ArcLink
deployments. It is separate from the host/systemd Shared Host install path and
from the Sovereign Control Node installer at `./deploy.sh control install`.

## Prerequisites

- Docker with `docker compose`.
- The repository checkout.
- No Podman requirement for Shared Host Docker mode.

## Bootstrap

```bash
./deploy.sh docker reconfigure
```

Bootstrap creates `arclink-priv/`, seeds the vault template, writes
`arclink-priv/config/docker.env` when missing, and creates persisted state
directories for Nextcloud, qmd, PDF ingest, Notion index markdown, and job
status.

The wrapper passes `arclink-priv/config/docker.env` to Docker Compose as its
env file after bootstrap. Existing config is preserved by default; set
`ARCLINK_DOCKER_REWRITE_CONFIG=1` only when you intentionally want bootstrap
to regenerate the default Docker config.

`./deploy.sh docker ...` is the operator-facing control path. It delegates to
`bin/arclink-docker.sh` for the Docker-specific mechanics.

Fresh Docker config uses generated local secrets for Postgres and the Nextcloud
admin user. Rotate them deliberately before any durable shared deployment.
Raw `docker compose up` without the wrapper intentionally fails until those
secret values exist.

## Ports

`bin/arclink-docker.sh` assigns host ports during bootstrap and persists them in
`arclink-priv/config/docker.env`. It tries the standard ArcLink ports first:

```text
QMD_MCP_PORT=8181
ARCLINK_MCP_PORT=8282
ARCLINK_NOTION_WEBHOOK_PORT=8283
NEXTCLOUD_PORT=18080
ARCLINK_API_PORT=8900
ARCLINK_WEB_PORT=3000
```

If any of those ports are already occupied, the wrapper chooses the next
available coherent Docker block, starting with:

```text
QMD_MCP_PORT=18181
ARCLINK_MCP_PORT=18282
ARCLINK_NOTION_WEBHOOK_PORT=18283
NEXTCLOUD_PORT=28080
ARCLINK_API_PORT=18900
ARCLINK_WEB_PORT=13000
```

The chosen block is also recorded in
`arclink-priv/state/docker/ports.json`. Set `ARCLINK_DOCKER_AUTO_PORTS=0` only
when you want fixed ports and prefer a startup failure over automatic reassignment.

Show the current assignment with:

```bash
./deploy.sh docker ports
```

## Start

```bash
./deploy.sh docker install
```

The default stack starts the hosted control API/web services plus ArcLink MCP,
qmd MCP, Notion webhook, Nextcloud, Postgres, Redis, vault watching, recurring
job containers, memory synthesis, and the Docker agent supervisor. The
supervisor replaces the Shared Host per-user systemd units for enrolled agents:
it reconciles refresh, Hermes gateway, dashboard, authenticated dashboard proxy,
cron tick, and dashboard-native plugin surfaces from the control-plane state.

The `memory-synth` job mirrors the Shared Host `arclink-memory-synth.timer`: it
uses the configured `ARCLINK_MEMORY_SYNTH_*` values, or falls back to
`PDF_VISION_*`, to build cached semantic recall cards for managed-context
hot injection without putting LLM summarization on the chat path. The same
generalized vault and Notion synthesis behavior is used in Docker and Shared Host,
including bounded media/data inventories, symlink boundary checks, and shallow
repo handling. Vault changes can request a non-blocking synthesis pass in both
modes, and full-source hashes keep move/rename/delete freshness separate from
the compact prompt sample; the recurring `memory-synth` job remains the
backstop.

`install` and `upgrade` also apply the private operating profile when present,
record `state/arclink-release.json`, run Docker health, and run the same live
agent MCP tool smoke that the Shared Host upgrade path uses.

Agent web surfaces are published individually as they are reconciled. ArcLink
keeps the same access-state ports as Shared Host, but Docker mode does not reserve
the entire possible port range at Compose startup.

Docker deployment stacks also carry the native Hermes workspace plugin mounts.
`hermes-dashboard` receives the deployment Hermes home, vault, and code
workspace with `VAULT_DIR=/srv/vault`, `DRIVE_ROOT=/srv/vault`, and
`CODE_WORKSPACE_ROOT=/workspace`. Reconcile and health repair those
mounts for existing deployment Compose files, rerun the managed plugin installer,
and recreate `hermes-dashboard` so `Drive`, `Code`, and the
managed-pty `Terminal` tab stay visible without Hermes core patches.

When Tailscale path mode is selected, Docker reconcile/health can publish
per-deployment Helm/Hermes on stable root-mounted tailnet HTTPS ports starting
at `ARCLINK_TAILNET_SERVICE_PORT_BASE`; Drive, Code, and Terminal live under
that dashboard URL. If the host Tailscale CLI is missing, publication is skipped
and health continues; deployment metadata remains the source of truth after
successful publication.

## Privilege Boundary

Docker mode runs the shared ArcLink app image as the `arclink` Unix user, then
grants the small set of Docker-lifecycle services that still mount the host
Docker socket supplemental access to the host Docker socket group through
`ARCLINK_DOCKER_SOCKET_GID`. The bootstrap path records the host socket gid
when it can inspect `/var/run/docker.sock`; set it manually in
`arclink-priv/config/docker.env` if the host socket group changes.

The writeable Docker socket services remain trusted-host services. Non-root
socket services drop all Linux capabilities in Compose and receive only the
host Docker socket group through `ARCLINK_DOCKER_SOCKET_GID`; this reduces the
container process surface but does not make writeable Docker socket access
tenant-safe. The `agent-supervisor` container is the Docker-mode replacement
for per-user systemd units; it no longer mounts the Docker socket, no longer
declares an explicit root user, no longer builds `setpriv` commands, and no
longer performs user/home setup directly.
Container-local user creation, persistent numeric uid/gid assignment, and
agent-home ownership repair are delegated to `agent-user-helper`, a tokened
root helper that has no Docker socket and only mounts the Docker agent-home
root. It drops Docker's default Linux capabilities and adds back only `CHOWN`,
`DAC_OVERRIDE`, and `FOWNER` for canonical bind-mount writes and ownership
repair. It also invokes `/usr/sbin/groupadd`, `/usr/sbin/useradd`, and
`/usr/bin/chown` by absolute trusted path and fails closed if any required
account/ownership tool is unavailable.
Docker-mode install, identity refresh, user-agent refresh, cron, gateway, and
dashboard process execution are delegated to `agent-process-helper`, a tokened
root helper that has no Docker socket and reconstructs only allowlisted
`setpriv` command forms from typed agent context. `GAP-019-W` makes that
helper reject ArcLink control-token env keys before log creation or subprocess
execution. `GAP-019-AD` rejects caller-provided `PATH` values that differ from
the helper safe path, invokes `/usr/bin/setpriv` by absolute path, and fails
identity setup closed when the pinned runtime venv Python is absent.
`GAP-019-AJ` makes gateway/dashboard reconciliation compare the validated
desired command, Hermes-home working directory, and process env signature, so
dashboard backend changes or env drift stop the stale process group before a
replacement is started. Identical desired specs do not churn, and shutdown is
bounded with SIGTERM followed by SIGKILL before the helper fails closed.
`GAP-019-X` narrows the helper's service boundary further: it no
longer inherits the broad `*arclink-env` Compose anchor and no longer mounts
`arclink-priv/secrets/container`; it keeps only explicit non-secret Docker
mode/path validation env plus the token/listener keys and the config, state,
vault, and read-only repo mounts needed by the allowlisted agent commands.
`GAP-019-Y` applies the same ambient-data reduction to
`gateway-exec-broker`: the public-Agent gateway broker no longer inherits the
broad `*arclink-env` Compose anchor and no longer mounts broad private
config/state or `arclink-priv/secrets/container`; it keeps only
`ARCLINK_STATE_ROOT_BASE`, optional `ARCLINK_DOCKER_BINARY`, broker
token/listener env, the deployment state-root bind needed for rendered Compose
fallback files, and the writeable Docker socket.
`GAP-019-AH` hardens that broker's executable lookup: `ARCLINK_DOCKER_BINARY`
must resolve to a trusted Docker CLI path, and unsafe, missing,
non-executable, or PATH-injected values fail closed before running-container
discovery or gateway exec subprocesses run.
`GAP-019-AY` hardens the broker's Compose fallback path: when a running
`hermes-gateway` container is not found, fallback `config/arclink.env` and
`config/compose.yaml` targets must be exact non-symlink regular readable files
under the deployment state-root config directory before fallback dispatch.
`GAP-019-Z` applies the same narrowing to `agent-supervisor-broker`: the
dashboard sidecar broker no longer inherits broad `*arclink-env` values and no
longer mounts broad private config/state or `arclink-priv/secrets/container`;
it keeps only Docker binary/image, repo path, host/container private path
metadata, broker token/listener env, and the writeable Docker socket needed for
dashboard network/proxy sidecars.
`GAP-019-AF` hardens that broker's executable lookup: `ARCLINK_DOCKER_BINARY`
must resolve to a trusted Docker CLI path, and unsafe or missing configuration
fails closed before dashboard broker subprocesses run.
`GAP-019-AZ` hardens the same dashboard sidecar bind boundary:
`ARCLINK_DOCKER_HOST_PRIV_DIR` and `ARCLINK_DOCKER_CONTAINER_PRIV_DIR` must be
canonical ArcLink private roots and must not be relative, `/`, colon-bearing,
newline/carriage-return/NUL-bearing, dot/dotdot, or otherwise non-canonical
values before the broker hashes proxy config, looks up Docker, inspects a
container, or builds the sidecar `docker run -v` mount.
`GAP-019-T` mounts the host repo read-only in
`agent-process-helper`, `agent-supervisor`, and
`curator-refresh`; `GAP-019-U` moves the writable host repo exception for
allowlisted queued Docker-mode operator upgrades to `operator-upgrade-broker`,
and that exception remains trusted-host residual risk.
`GAP-019-AB` narrows that operator broker's ambient boundary: it no longer
inherits broad `*arclink-env`, no longer mounts broad canonical private
config/state or `arclink-priv/secrets/container`, and its allowlisted upgrade
subprocesses use a child-process env allowlist instead of inheriting the
broker's full process environment. The writable host repo bind still reaches
the nested private state needed for real upgrades and remains trusted-host
residual risk with the writeable Docker socket.
`GAP-019-AI` hardens that broker's child executable lookup:
`ARCLINK_DOCKER_BINARY` is preserved for upgrade subprocesses only after it
resolves to a trusted absolute Docker CLI path. Unsafe, missing,
non-executable, relative, non-Docker, or PATH-injected values fail closed before
`deploy.sh docker upgrade` or component upgrade child subprocesses run.
`GAP-019-AW` hardens request-supplied upstream deploy-key metadata in the same
broker: non-empty `ARCLINK_UPSTREAM_DEPLOY_KEY_PATH` and
`ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE` values must be absolute non-symlink paths
under `ARCLINK_DOCKER_HOST_PRIV_DIR` before child env construction, private
operator logs, or upgrade subprocesses.
`GAP-019-AK` scopes the tokened broker/helper request lanes onto internal Compose
networks instead of the shared default network. Each broker/helper is
reachable only from its legitimate caller network; `agent-process-helper` and
`operator-upgrade-broker` additionally get single-service egress networks for
agent gateway/provider runtime work and upgrade fetches without exposing their
HTTP helper APIs on the default network.
`GAP-019-AL` adds the explicit residual-risk acknowledgement gate for the same
seven high-authority services. `deployment-exec-broker`,
`migration-capture-helper`, `agent-user-helper`, `agent-process-helper`,
`agent-supervisor-broker`, `operator-upgrade-broker`, and
`gateway-exec-broker` receive
`ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED` through Compose and fail closed
unless the private Docker config sets the exact non-secret value `accepted`.
Missing, blank, false, or other values stop the broker/helper before its HTTP
listener is bound or direct request work begins. This is an operator
acknowledgement boundary only; it does not close `GAP-019` or make writeable
Docker socket/root helper authority tenant-safe, and it does not close
`GAP-001`, `PG-UPGRADE`, `PG-PROVISION`, `PG-BOTS`, `PG-HERMES`, or any live
production proof gate.
`GAP-019-AP` makes direct/local execution of those same high-authority
broker/helper modules bind `127.0.0.1` by default. Compose remains the explicit
source-owned opt-in to `0.0.0.0` for the internal request networks, and the
container healthchecks stay on `127.0.0.1`. `--host` and the service-specific
`ARCLINK_*_HOST` env values still override the default, so any broad bind is
intentional instead of inherited from a direct-run module default. This is
listener-default hardening only; the writeable Docker socket brokers and root
helpers remain trusted-host residual risk.
`GAP-019-AQ` narrows the `agent-supervisor` provisioner child env allowlist:
`run_provisioner` no longer starts from `os.environ.copy()`. The child keeps
Docker mode/path config, runtime roots, service URLs, and helper/broker values
needed for Docker enrollment and queued operator actions, but it does not
inherit unrelated payment, provider, bot, ingress, memory-synthesis, session,
fleet, Python path, or Git/SSH steering env keys. The supervisor service still
keeps private config/state/vault mounts for Docker agent reconciliation, so
this is child-process env hardening only and does not close `GAP-019`.
`GAP-019-AR` narrows the dashboard backend host boundary shared by
`agent-process-helper` and `agent-supervisor-broker`: wildcard, globally
routable, multicast, malformed, and non-IP backend hosts fail before the root
helper opens a dashboard log or starts `subprocess.Popen`, and before the
dashboard broker performs Docker CLI lookup or constructs the auth-proxy
sidecar. Loopback and Docker-internal backend IPs remain valid for the
agent-specific dashboard network design. This is dashboard process/proxy
routing hardening only; the helper and broker remain trusted-host residual
risk.
`GAP-019-AM` narrows the `agent-process-helper` request env boundary: the
helper rejects dynamic-loader `LD_*`, Python path/startup, shell startup,
Git/SSH command-steering, and secret-looking `*_TOKEN`, `*_SECRET`,
`*_PASSWORD`, or `*_KEY` process env keys before helper logs or subprocesses.
`agent-supervisor` strips known ArcLink helper tokens and fails closed on the
same unapproved non-token key family before constructing helper payloads. This
is env-injection hardening only; the root helper remains trusted-host residual
risk.
`GAP-019-AN` narrows both root agent helpers' path boundary: `agent-user-helper`
and `agent-process-helper` now compare lexical canonical child paths with the
resolved canonical target for the agent home, Hermes home, and workspace.
Pre-existing symlinks at those points fail closed before uid/gid assignment
writes, account commands, recursive chown, helper log creation,
`subprocess.run`, or `subprocess.Popen`. This is symlink path hardening only;
both helpers remain trusted-host residual root boundaries.
`GAP-019-AS` closes the matching configured-root symlink escape: a configured
or requested Docker agent-home root, including
`ARCLINK_DOCKER_AGENT_HOME_ROOT`, must not be a symlink or include symlink
components before `agent-user-helper` writes uid/gid assignments, creates
accounts, or runs chown, and before `agent-process-helper` opens helper logs or
starts agent subprocesses. This is agent-home root path hardening only; both
helpers remain trusted-host residual root boundaries.
`GAP-019-BA` narrows the `agent-user-helper` uid/gid assignment write boundary:
pre-existing `.arclink-user-ids.json` and `.arclink-user-ids.json.tmp` paths
under the Docker agent-home root must be missing or non-symlink regular files,
and the temp file is created with exclusive no-follow semantics before
`os.replace`. Symlinked, directory, or non-regular assignment paths fail before
assignment writes, account commands, agent-home directory creation, or
recursive chown. This is assignment-file hardening only; the helper remains a
trusted-host residual root boundary.
`GAP-019-AT` closes the process-helper side of that configured-root class:
configured or requested repo, private-state, state, and runtime roots,
including `ARCLINK_REPO_DIR`, `ARCLINK_PRIV_DIR`,
`ARCLINK_DOCKER_CONTAINER_PRIV_DIR`, request `state_dir`, and `RUNTIME_DIR`,
must not include symlink components before `agent-process-helper` opens helper
logs, uses those roots for cwd/command/interpreter lookup, or starts
subprocesses. This is process-helper path hardening only; the helper remains a
trusted-host residual root boundary.
`GAP-019-AU` adds fixed repo command target preflight inside
`agent-process-helper`: `bin/install-agent-user-services.sh`,
`bin/hermes-shell.sh`, `bin/user-agent-refresh.sh`, and
`python/arclink_headless_hermes_setup.py` must be canonical repo children,
regular readable files, and shell command targets must be executable before
helper logs or subprocesses are opened. This is command target hardening only;
the helper remains a trusted-host residual root boundary.
`GAP-019-AO` narrows the process helper's log path boundary: a pre-existing
`state/docker/agent-process-helper` symlink, or symlinked helper log file, fails
closed before log open, `subprocess.run`, or `subprocess.Popen`. Normal
non-symlink helper log directories under private state still work. This is log
path hardening only; `agent-process-helper` remains a trusted-host residual
root boundary.
`GAP-019-BB` adds a local rejection incident trail for the same helper:
rejected requests append one redacted row to
`state/docker/agent-process-helper/rejections.jsonl` only when the configured
private root is safe. The row records operation, safe agent id when available,
trusted-host acknowledgement state, error class, and a sanitized reason; it
does not write raw request bodies, process args, env values, private paths,
tokens, or stack traces. This is local incident evidence, not live alerting or
root-helper isolation.
`GAP-019-BC` adds the same local evidence pattern to `gateway-exec-broker`:
rejected public Agent broker requests append one redacted row to
`ARCLINK_STATE_ROOT_BASE/_broker-incidents/gateway-exec-broker/rejections.jsonl`
only when the configured deployment state root is absolute, non-root,
existing, and non-symlinked. Rows include safe deployment/project metadata,
trusted-host acknowledgement state, error class, and sanitized reason codes,
not raw request bodies, bridge payload values, bot tokens, chat ids, user ids,
message text, process args, rendered config paths, private paths, or stack
traces. Accepted broker requests do not append rejection incidents. This is
local incident evidence, not live alerting or Docker socket isolation.
`GAP-019-BD` extends that redacted incident pattern to the remaining local
high-authority lanes that can write a narrow durable log: `deployment-exec-broker`
and `migration-capture-helper` write under the configured deployment state
root, `agent-user-helper` writes under the configured Docker agent-home root,
`agent-supervisor-broker` writes under a narrow private-state incident mount,
and `operator-upgrade-broker` writes under the configured host private state.
Rows contain service/event, trusted-host acknowledgement state, error class,
sanitized reason/message, and safe identifiers such as operation or agent id
when available. They do not include raw request bodies, `cmd`/`command`/`args`
values, payload values, process args, private paths, tokens, chat ids, user ids,
message text, or stack traces. Unsafe or missing incident roots do not fall
back to another log path. This is still incident evidence, not live alerting or
tenant-safe Docker/root isolation.
Dashboard network and auth-proxy sidecar Docker operations are delegated to
`agent-supervisor-broker`, a non-root command-specific broker that validates
agent ids, ports, network/container names, and private-state access-file paths
before invoking Docker. User
dashboard backends are bound to agent-specific internal Docker network
addresses; only the dashboard auth-proxy sidecar is published to host loopback.
The `control-action-worker` no longer mounts the Docker socket and no longer
runs as root; it delegates local Docker lifecycle/apply operations to
`deployment-exec-broker` and Docker-mode Pod migration file
capture/materialization to `migration-capture-helper`. The
`GAP-019-AA` repair keeps `deployment-exec-broker` on minimal service env:
broker token/listener settings, `ARCLINK_STATE_ROOT_BASE`, optional Docker
binary, the deployment state-root bind, and the writeable Docker socket. It no
longer inherits broad `*arclink-env` app, billing, bot, provider, ingress,
fleet, session, or memory-synthesis values.
`control-action-worker` no longer runs as root in Docker mode. The
`migration-capture-helper` intentionally runs as root so it can read/write
root-owned deployment bind mounts during a bounded migration window, but it has
no Docker socket and accepts only tokened capture/materialize requests with
deployment-scoped paths. `GAP-019-AC` narrows that helper further: it no
longer inherits broad `*arclink-env`, keeps only
`ARCLINK_STATE_ROOT_BASE` plus helper token/listener env, and rejects source,
target, or staging paths outside the configured state-root base before file
work starts.

The reviewed socket/root authority inventory lives in
`config/docker-authority-inventory.json`. It records each socket or explicit
root service, its read/write authority, root boundary, `GAP-019-B2` broker
review, monitoring/runbook anchor, `GAP-019-M` incident controls, and residual
`GAP-019` policy state. Docker
regression tests compare that inventory with `compose.yaml`, so adding a new
socket mount, root service, changed writer boundary, proxy/broker decision, or
monitoring control requires updating the inventory and this runbook section in
the same patch.

The `GAP-019-B2` review records a conservative decision: a generic Docker
socket proxy is not enough to call the boundary closed. It still grants broad
container create, exec, network, volume, and image authority to any compromised
writer. The narrowing path is command-specific brokers that validate the
deployment id, project name, compose/env paths, and allowed action before
invoking Docker. Until those brokers exist, writeable socket services remain
trusted-host services and require an operator residual-risk decision.
`GAP-019-E` added source-level executor preflight for the local/SSH executor:
live Docker apply and lifecycle requests reject unsafe deployment IDs,
non-matching apply project names, and env/compose paths outside the configured
`ARCLINK_STATE_ROOT_BASE` deployment config root before Docker runner dispatch.
`GAP-019-G` moves the Docker-mode local executor socket authority out of
`control-provisioner`: the provisioner now sends deployment-scoped operation
requests to `deployment-exec-broker`, which rejects raw commands and
reconstructs the allowlisted Compose operation itself. The broker's socket is
still host-root-equivalent trusted-host authority.
`GAP-019-F` moves the public-Agent gateway exec path out of
`notification-delivery`: the notification worker now submits a bounded
deployment request to `gateway-exec-broker`, and only that broker mounts the
writeable Docker socket for `hermes-gateway` exec.
`GAP-019-AH` makes that broker fail closed before Docker discovery or exec when
`ARCLINK_DOCKER_BINARY` does not resolve to a trusted Docker CLI path.
`GAP-019-H` removes direct Docker socket access from `control-action-worker`:
local Docker lifecycle and reprovision Compose operations now require the
deployment exec broker when Docker mode is enabled.
`GAP-019-K` keeps that root capture path fail-closed by default: non-dry-run
Pod migration capture requires
`ARCLINK_ACTION_WORKER_ALLOW_ROOT_MIGRATION_CAPTURE=1`, and source, target, and
staging paths are validated as deployment-scoped ArcLink state roots before any
file copy starts.
`GAP-019-N` removes the remaining root boundary from `control-action-worker`:
Docker-mode capture/materialization now also requires
`ARCLINK_MIGRATION_CAPTURE_HELPER_URL` and
`ARCLINK_MIGRATION_CAPTURE_HELPER_TOKEN`. The tokened
`migration-capture-helper` rejects raw command fields, reconstructs only
`capture` or `materialize`, validates deployment id, prefix, migration id,
source root, target root, and `.migrations/<migration_id>` staging path, and
then performs the root file copy. The helper's residual root authority remains
trusted-host risk.
`GAP-019-I` removes direct Docker socket access from `agent-supervisor`: the
supervisor delegates dashboard network/proxy sidecar work to
`agent-supervisor-broker`; the broker's socket remains trusted-host authority.
`GAP-019-Z` narrows that broker's ambient data access: it no longer inherits
broad `*arclink-env` values and no longer mounts broad private config/state or
`arclink-priv/secrets/container`; it keeps only the explicit non-secret path
metadata, Docker image/binary settings, broker token/listener env, and writeable
Docker socket required for dashboard sidecar reconstruction.
`GAP-019-O` then moves container-local user/home setup out of
`agent-supervisor` and into `agent-user-helper`, which requires
`ARCLINK_AGENT_USER_HELPER_URL` and `ARCLINK_AGENT_USER_HELPER_TOKEN`, rejects
raw commands, accepts only `ensure_user_home`, and validates agent id, Unix
user, Docker agent-home root, agent home, Hermes home, and workspace path. The
helper's root authority remains trusted-host risk.
`GAP-019-P` moves setpriv agent process execution out of `agent-supervisor` and
into `agent-process-helper`, which requires `ARCLINK_AGENT_PROCESS_HELPER_URL`
and `ARCLINK_AGENT_PROCESS_HELPER_TOKEN`, rejects raw commands, accepts only
typed process operations, and validates agent context before reconstructing
allowlisted install, identity, refresh, cron, gateway, and dashboard commands.
`GAP-019-X` removes broad service env inheritance and the global container
secrets mount from that helper while preserving the explicit non-secret roots
used for request validation. The helper's root authority remains trusted-host
risk.
`GAP-019-AJ` adds desired-process signature tracking to that helper. A changed
gateway/dashboard command, Hermes-home cwd, dashboard backend port, or
validated env contract causes a bounded stop/restart; a process that cannot be
stopped after SIGTERM/SIGKILL fails closed before replacement.
`GAP-019-J` moves queued Docker-mode operator upgrades and pinned-component
upgrade apply/final-upgrade execution behind a tokened broker. `GAP-019-U`
splits that path into `operator-upgrade-broker`: the enrollment provisioner
now fails closed without that broker URL/token, sends no raw command fields,
and the broker reconstructs only `deploy.sh docker upgrade` or allowlisted
`component-upgrade.sh ... --skip-upgrade` commands with logs confined to
private `state/operator-actions`. `GAP-019-AB` then removes the broker's broad
app env and broad canonical private mounts and constrains child upgrade
subprocess env to basic runtime, Docker-mode path, optional Docker binary, and
request-supplied upstream metadata keys.
`GAP-019-L` adds a local metadata/path guard to the `agent-supervisor`
delegation path. Active-agent `agent_id`, `unix_user`, `hermes_home`, Docker
agent home, workspace, supervisor log/process keys, and agent process env keys
are validated before helper, broker, or process-helper requests.
`GAP-019-M` records incident controls for the remaining writeable socket
brokers and explicit root helpers. The inventory now names monitored signals,
status/log/audit locations, triage steps, fail closed actions, and the operator
escalation boundary for each residual authority row.
`GAP-019-AL` also lives in that inventory: every remaining writeable-socket
broker or explicit-root helper row records the
`ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED=accepted` startup/direct-request
gate and explicitly preserves the remaining `GAP-019` residual-risk decision.

Treat Docker mode as a trusted-host deployment. Do not expose the Docker socket
or the agent-supervisor service publicly, and do not publish raw dashboard
backend ports or the default Compose network. The shared HTTP services in
`compose.yaml` remain bound to `127.0.0.1` by default so external access can be
handled deliberately through the same access rails as Shared Host Mode.

Optional profiles are available for `curator`, `quarto`, and `backup`:

```bash
COMPOSE_PROFILES=curator ./deploy.sh docker install
```

`./deploy.sh docker install` asks the operator-facing Docker configuration
questions before the build/up step, then runs Curator setup interactively when a
terminal is available. That matches the Shared Host operator flow for organization
context, provider defaults, Nextcloud, backup, PDF vision, Curator model, chat
channels, and operator notifications while keeping host-systemd-only questions
out of Docker mode. If OpenAI Codex is selected as the org-wide provider, the
shared org credential is captured from the later Curator Codex sign-in instead
of using a separate first-questionnaire auth flow. It then starts
Curator-profile services when their configured credentials allow them to run.
For scripted base stack refreshes that should skip operator setup, set:

```bash
ARCLINK_DOCKER_SKIP_OPERATOR_CONFIG=1 ARCLINK_DOCKER_SKIP_CURATOR_SETUP=1 ./deploy.sh docker install
```

## Health

```bash
./deploy.sh docker health
./deploy.sh docker ps
```

Health validates the Compose file, required persisted directories, running
core services, operator-facing ingress, core HTTP/database endpoints, recurring
job status files, and Docker user-agent managed context/SOUL presence plus MCP
token validity/refresh status when the stack is up.

## Operator Command Parity

Docker mode keeps the same `deploy.sh` control-center vocabulary wherever the
operation has a container-native equivalent:

```bash
./deploy.sh docker notion-ssot
./deploy.sh docker enrollment-status
./deploy.sh docker enrollment-trace --unix-user <user>
./deploy.sh docker enrollment-align
./deploy.sh docker enrollment-reset --unix-user <user>
./deploy.sh docker curator-setup
./deploy.sh docker rotate-nextcloud-secrets
./deploy.sh docker agent-payload
./deploy.sh docker pins-show
./deploy.sh docker pins-check
./deploy.sh docker qmd-upgrade-check
./deploy.sh docker qmd-upgrade --version <version>
```

The Docker enrollment provisioner and self-serve Notion claim poller are run by
the `agent-supervisor` container instead of systemd timers. `enrollment-align`
restarts that supervisor and runs an immediate provisioner pass.

The same supervisor also owns per-agent install realignment in Docker mode: it
syncs skills/plugins/MCP entries, refreshes identity/SOUL, runs the local
managed-context refresh, and validates or repairs each agent's private ArcLink
MCP bootstrap token before starting gateways or agent web surfaces.

Pinned-component apply commands re-enter `./deploy.sh docker upgrade` after the
pin bump and load upstream push/deploy-key settings from the Docker runtime
config. The interactive `./deploy.sh` menu first chooses between Sovereign
Control Node Mode, Shared Host Mode, and Shared Host Docker Mode, then opens the
selected control center. The top-level default is Sovereign Control Node Mode so
new ArcLink SaaS hosts do not accidentally fall back into an operator-led path.

Host/systemd-only commands remain explicit Shared Host operations. `./deploy.sh
remove` tears down a host install; `./deploy.sh docker remove` is an alias for
Docker teardown and does not remove `arclink-priv/` bind-mounted state.

## Logs

```bash
./deploy.sh docker logs
./deploy.sh docker logs arclink-mcp
```

Recurring job status is written under:

```text
arclink-priv/state/docker/jobs/
```

## Stop And Teardown

```bash
./deploy.sh docker down
./deploy.sh docker teardown
```

`down` stops containers and keeps data. `teardown` also removes Compose named
volumes, but bind-mounted `arclink-priv/` state remains on disk.

## Docker Socket And Private-State Trust Boundaries

The Docker Compose stack intentionally mounts `/var/run/docker.sock` only into
services that need Docker API access for lifecycle management:

| Service | Purpose | Why it needs the Docker socket |
| --- | --- | --- |
| `deployment-exec-broker` | Local deployment executor broker | Executes allowlisted deployment Compose apply, inspect, and teardown operations for the local executor; `GAP-019-AA` keeps only minimal broker env plus the deployment state-root bind and Docker socket, `GAP-019-AG` rejects unsafe Docker CLI executable configuration before subprocesses, and `GAP-019-AX` rejects symlinked or non-regular rendered config files before Docker lookup or dispatch |
| `migration-capture-helper` | Pod migration capture helper | No Docker socket; intentionally runs as root to capture/materialize deployment state only from tokened, deployment-scoped Pod migration requests |
| `agent-user-helper` | Agent user/home helper | No Docker socket; intentionally runs as root with `cap_drop: ALL` plus only `CHOWN`, `DAC_OVERRIDE`, and `FOWNER` to create container-local Unix users, persist numeric uid/gid assignments, and repair canonical Docker agent-home ownership from tokened, validated requests whose home root matches configured `ARCLINK_DOCKER_AGENT_HOME_ROOT`; account and ownership tools are pinned to absolute paths, and symlinked configured/requested agent-home roots plus symlink-escaped agent home, Hermes home, or workspace paths fail before root mutation |
| `agent-process-helper` | Agent process helper | No Docker socket; intentionally runs as root to execute allowlisted setpriv agent install, refresh, cron, gateway, and dashboard process operations from tokened, validated requests; configured Docker agent-home, repo, private-state, state, and runtime roots are checked before logs or subprocesses, symlinked configured/requested repo/private-state/state/runtime roots, symlinked configured/requested agent-home roots, symlink-escaped agent home/Hermes/workspace paths, symlink-escaped helper log directories, and missing/symlinked/non-executable fixed repo command targets fail before logs or subprocesses, ArcLink control-token env keys, dynamic-loader/Python/shell/Git/SSH/secret-looking env keys, and caller-controlled PATH values are rejected, `/usr/bin/setpriv` is invoked by absolute path, identity setup fails closed without the pinned runtime venv Python, validated env is passed through subprocess env, not setpriv argv or startup logs, rejected requests append redacted local incidents to `state/docker/agent-process-helper/rejections.jsonl` when the configured private root is safe, and the host repo bind is read-only |
| `agent-supervisor-broker` | Agent dashboard network/proxy broker | Executes allowlisted dashboard network connect/create and dashboard auth-proxy sidecar run/remove operations for `agent-supervisor`; `GAP-019-Z` keeps only minimal broker env plus Docker path/image metadata and the Docker socket instead of broad private config/state/secrets mounts, `GAP-019-AF` rejects unsafe Docker CLI executable configuration before subprocesses, and `GAP-019-AZ` rejects unsafe host/container private bind roots before Docker lookup or sidecar `docker run -v` construction |
| `operator-upgrade-broker` | Operator upgrade broker | Executes allowlisted queued Docker-mode operator upgrades and component pin apply/final-upgrade operations; this is the explicit writable host repo exception for those upgrades; `GAP-019-AI` rejects unsafe Docker CLI executable configuration before upgrade child subprocesses |
| `gateway-exec-broker` | Public Agent gateway exec broker | Executes the selected deployment's Hermes gateway container for brokered Raven public-channel turns; `GAP-019-Y` keeps only minimal broker env, optional Docker binary selection, the deployment state-root bind, and the Docker socket instead of broad private config/state/secrets mounts, `GAP-019-AH` rejects unsafe Docker CLI executable configuration before subprocesses, and `GAP-019-AY` rejects unsafe Compose fallback config files before fallback dispatch |

The lifecycle services also bind-mount the live repository checkout and
`arclink-priv/` for config, state, and secrets access. `control-action-worker`
no longer runs as root and no longer mounts the Docker socket; action
lifecycle/apply calls go through `deployment-exec-broker`, and Pod migration
file capture/materialization goes through `migration-capture-helper` when
Docker mode is enabled. `agent-supervisor` no longer runs as root for agent
process supervision; user/home setup goes through `agent-user-helper`, agent
process execution goes through `agent-process-helper`, and agent dashboard
network/proxy calls go through `agent-supervisor-broker`. `GAP-019-R` narrows
the process-helper boundary by keeping validated env values out of setpriv argv
and `state/docker/agent-process-helper/*.log` startup command lines; the
supervisor also strips broker/helper tokens from per-agent process specs before
calling the helper. `GAP-019-W` also makes the helper itself reject ArcLink
control-token env keys, including future `ARCLINK_*_TOKEN` keys, before
one-shot or long-running agent subprocesses start. `GAP-019-AM` rejects
dynamic-loader `LD_*`, Python path/startup, shell startup, Git/SSH
command-steering, and secret-looking process env keys before helper logs or
subprocesses; the supervisor fails closed on the same unapproved non-token key
family before helper payload construction. `GAP-019-AD` removes the
caller-controlled executable lookup slice by requiring helper env `PATH` to
match `SAFE_PATH`, using absolute `/usr/bin/setpriv` for both one-shot and
long-running process launches, and failing identity setup before
`subprocess.run` if `RUNTIME_DIR/hermes-venv/bin/python3` is absent. `GAP-019-S` narrows both root helpers by rejecting
request-scoped root/path values that do not match configured Docker
agent-home, repo, private-state, state, or runtime roots before root filesystem
work, helper logs, or subprocess execution.
`GAP-019-AN` adds the symlink half of that path boundary: canonical agent home,
Hermes home, and workspace requests must resolve to their expected child target
under the validated Docker agent path, or the helpers fail closed before root
filesystem work, helper logs, or subprocess execution.
`GAP-019-AT` adds the process-helper configured-root symlink half: repo,
private-state, state, and runtime roots must not include symlink components
before helper logs, cwd/command/interpreter lookup, or process execution.
`GAP-019-AU` adds fixed repo command target preflight: the helper rejects
missing, symlinked, directory, unreadable, or non-executable command targets
such as `bin/hermes-shell.sh` before helper logs or process execution.
`GAP-019-AO` applies the same fail-closed rule to
`agent-process-helper` log confinement: `state/docker/agent-process-helper`
must be the canonical non-symlink helper log directory, and log files must
resolve to their exact canonical child path before the helper opens them or
starts one-shot or gateway/dashboard subprocesses.
`GAP-019-BB` adds the rejected-request evidence trail for that helper:
`state/docker/agent-process-helper/rejections.jsonl` contains only redacted
metadata rows for failed helper requests when the configured private root is
safe; accepted `run_once`, `ensure_processes`, and `terminate_all` requests do
not append rejection incidents.
`GAP-019-T` keeps the read-only host repo boundary by mounting the live host repo read-only for `agent-supervisor`,
`agent-process-helper`, and `curator-refresh`, which only need script reads for
refresh, detection, and typed process execution. `GAP-019-U` moves the
writable host repo bind and upgrade operation kinds to `operator-upgrade-broker`;
`agent-supervisor-broker` no longer mounts the host repo.
`GAP-019-V` removes the remaining read-only route-discovery socket boundary:
`control-ingress` now uses a static Traefik file-provider config at
`config/traefik-control.yaml`, no longer enables the Docker provider, no longer
mounts the Docker socket, and still does not receive `arclink-priv/`.
`curator-refresh` no longer mounts the Docker socket; source routes queued
Docker-mode operator upgrade execution through the enrollment provisioner path,
which now delegates Docker-mode upgrade execution to `operator-upgrade-broker`.
`notification-delivery` also no longer mounts the Docker socket; it
holds the public bot tokens needed to build the Hermes bridge payload and sends
only a bounded deployment-scoped request to `gateway-exec-broker`. `GAP-019-Y`
narrows that broker's service boundary so the broker does not receive broad
app env, `arclink-priv/config`, `arclink-priv/state`, or
`arclink-priv/secrets/container`; the broker keeps only the deployment
state-root bind needed to locate rendered Compose files when Docker container
lookup falls back to `docker compose exec`.
`GAP-019-Z` narrows `agent-supervisor-broker` the same way for dashboard
sidecar work: it keeps broker token/listener env, Docker binary/image, repo
path, host/container private path metadata, and the Docker socket, but does not
mount broad private config/state/secrets.
`GAP-019-AF` makes the same broker fail closed if `ARCLINK_DOCKER_BINARY`
points to `bash`, another non-Docker executable, an untrusted path, or a missing
Docker CLI before any dashboard network/proxy subprocess is invoked.
`GAP-019-AZ` also makes `ARCLINK_DOCKER_HOST_PRIV_DIR` and
`ARCLINK_DOCKER_CONTAINER_PRIV_DIR` fail closed when they are malformed Docker
volume specs, root/relative paths, dot/dotdot paths, or non-canonical private
roots before Docker CLI lookup or auth-proxy sidecar `docker run -v`
construction.
`GAP-019-AR` also makes that broker and the root `agent-process-helper` agree
on the dashboard backend host policy: the host must be loopback or
Docker-internal, not wildcard, globally routable, multicast, malformed, or a
non-IP value, before dashboard proxy or Hermes dashboard subprocess work
starts.
`control-provisioner` no longer mounts the Docker socket either; it writes the
rendered deployment files and calls `deployment-exec-broker` with a bounded
operation request when the local executor adapter is enabled.
`GAP-019-AG` makes that deployment broker fail closed if
`ARCLINK_DOCKER_BINARY` points to `bash`, another non-Docker executable, an
untrusted path, or a missing Docker CLI before any deployment Compose
subprocess is invoked.
`GAP-019-AK` then removes default network reachability from
`deployment-exec-broker`, `migration-capture-helper`, `agent-user-helper`,
`agent-process-helper`, `agent-supervisor-broker`,
`operator-upgrade-broker`, and `gateway-exec-broker`. Their request networks
are `internal: true` and include only the legitimate caller services; the
process helper and operator-upgrade broker keep separate single-service egress
networks because their allowlisted child work may need outbound provider or
upstream access.

`config/docker-authority-inventory.json` is the source-owned inventory for this
table. It is intentionally more detailed than the runbook table: it includes
authority class, Compose socket mode, explicit-root status, Linux capability
boundary, Compose network boundary, `GAP-019-B2` broker/proxy decision,
operation allowlist, runtime enforcement paths, monitoring anchor, and residual
policy state for each row.
Treat inventory drift as a security review trigger, not a formatting cleanup.

`GAP-019-B2` local review outcome:

| Service | B2 decision | Remaining gate |
| --- | --- | --- |
| `deployment-exec-broker` | Generic Docker socket proxy is no-go; `GAP-019-G` adds a deployment-scoped broker for local Compose `up`, `ps`, and `down` operations, and `control-provisioner` no longer mounts the socket. `GAP-019-AA` narrows the broker to minimal service env plus the deployment state-root bind and writeable Docker socket. `GAP-019-AG` rejects unsafe Docker CLI executable configuration before subprocesses. `GAP-019-AX` rejects symlinked deployment config roots and symlinked, missing, non-regular, or unreadable rendered config files before Docker lookup or dispatch. `GAP-019-AP` makes direct execution default to `127.0.0.1`; Compose explicitly sets `0.0.0.0` only for the internal request network. | Accept the broker as the residual trusted-host boundary, replace it with stronger isolation, or force SSH/fake-only policy. |
| `migration-capture-helper` | `GAP-019-N` removes root from `control-action-worker` by adding a tokened root helper for Pod migration `capture` and `materialize`; it rejects raw commands and validates deployment-scoped source, target, and staging paths. `GAP-019-AC` removes broad service env inheritance and confines source, target, and staging paths under `ARCLINK_STATE_ROOT_BASE`. `GAP-019-AP` makes direct execution default to `127.0.0.1`; Compose explicitly sets `0.0.0.0` only for the internal request network. | Accept the helper as the residual root boundary, replace it with stronger isolation, or disable non-dry-run Docker-mode Pod migration capture. |
| `agent-user-helper` | `GAP-019-O` moves container-local user/home setup out of `agent-supervisor`; `GAP-019-Q` removes Docker's default capability set and leaves only `CHOWN`, `DAC_OVERRIDE`, and `FOWNER` added back for the tokened root helper's validated filesystem work; `GAP-019-S` rejects configured Docker agent-home root mismatches before filesystem or account mutation; `GAP-019-AE` pins `groupadd`, `useradd`, and `chown` to trusted absolute paths and preflights them before helper mutation; `GAP-019-AN` rejects symlink-escaped agent home, Hermes home, and workspace paths before uid/gid assignment, account commands, or recursive chown; `GAP-019-AS` rejects symlinked configured/requested agent-home root paths before the same root work; `GAP-019-BA` rejects symlinked, directory, or non-regular `.arclink-user-ids.json` and `.arclink-user-ids.json.tmp` assignment paths before assignment writes or root account/home work. `GAP-019-AP` makes direct execution default to `127.0.0.1`; Compose explicitly sets `0.0.0.0` only for the internal request network. | Accept the helper as the residual root boundary, replace it with stronger isolation, or redesign Docker-mode agent user/home setup. |
| `agent-process-helper` | `GAP-019-P` moves setpriv agent command construction and gateway/dashboard process handles out of `agent-supervisor`; `GAP-019-R` keeps validated env values out of setpriv argv/startup logs and strips supervisor helper tokens before helper dispatch; `GAP-019-W` rejects ArcLink control-token env keys at the helper boundary; `GAP-019-AD` rejects caller-controlled `PATH`, uses absolute `/usr/bin/setpriv`, and removes the bare `python3` identity fallback; `GAP-019-S` rejects configured Docker agent-home, repo, private-state, state, and runtime root mismatches before logs or subprocess execution; `GAP-019-AN` rejects symlink-escaped agent home, Hermes home, and workspace paths before logs or subprocess execution; `GAP-019-AS` rejects symlinked configured/requested agent-home root paths before helper logs or subprocess execution; `GAP-019-AO` rejects symlink-escaped helper log directories before log open or subprocess execution; `GAP-019-AU` preflights fixed repo command targets such as `bin/hermes-shell.sh` before helper logs or subprocess execution; `GAP-019-BB` records redacted rejected-request incidents in private state without raw request bodies, env values, args, tokens, or private paths; `GAP-019-T` changes its live host repo bind to read-only. `GAP-019-AP` makes direct execution default to `127.0.0.1`; Compose explicitly sets `0.0.0.0` only for the internal request network. | Accept the helper as the residual root boundary, replace it with stronger isolation, or redesign Docker-mode agent process supervision. |
| `agent-supervisor-broker` | Generic proxy remains no-go; `GAP-019-I` adds a command-specific broker for dashboard network/proxy sidecar operations, `GAP-019-U` removes queued operator upgrade operations and the writable host repo bind from this broker, `GAP-019-Z` removes broad app env plus broad private config/state/secrets mounts, `GAP-019-AF` rejects unsafe Docker CLI executable configuration before subprocesses, and `GAP-019-AZ` rejects unsafe private bind roots before dashboard auth-proxy sidecar `docker run -v` construction. `GAP-019-AP` makes direct execution default to `127.0.0.1`; Compose explicitly sets `0.0.0.0` only for the internal request network. | Accept the broker as the residual trusted-host dashboard sidecar boundary or replace it with stronger isolation. |
| `operator-upgrade-broker` | Generic proxy remains no-go; `GAP-019-U` adds a dedicated command-specific broker for queued operator upgrades, private log-path confinement, and the explicit writable host repo exception. `GAP-019-AB` removes broad service env/private mounts and adds a child-process env allowlist. `GAP-019-AI` rejects unsafe Docker CLI executable configuration before upgrade child subprocesses. `GAP-019-AV` rejects unsafe fixed `deploy.sh` and `bin/component-upgrade.sh` script targets before private logs or subprocesses. `GAP-019-AW` confines non-empty upstream deploy-key and known-hosts child-env paths such as `ARCLINK_UPSTREAM_DEPLOY_KEY_PATH` under private state before logs or subprocesses. `GAP-019-AP` makes direct execution default to `127.0.0.1`; Compose explicitly sets `0.0.0.0` only for the internal request network. | Accept the broker as the residual trusted-host operator-upgrade boundary or replace it with stronger isolation. |
| `gateway-exec-broker` | Generic proxy remains no-go; `GAP-019-F` adds a deployment-scoped gateway-exec broker for `hermes-gateway`, and `notification-delivery` no longer mounts the socket. `GAP-019-Y` removes broad app env plus broad private config/state/secrets mounts while preserving the deployment state-root bind needed for Compose fallback. `GAP-019-AH` rejects unsafe Docker CLI executable configuration before discovery or exec subprocesses. `GAP-019-AY` rejects symlinked, missing, non-regular, unreadable, or directory `config/arclink.env` and `config/compose.yaml` fallback targets before fallback dispatch. `GAP-019-BC` records redacted rejected-request incidents under `_broker-incidents/gateway-exec-broker/rejections.jsonl` below the configured deployment state root. `GAP-019-AP` makes direct execution default to `127.0.0.1`; Compose explicitly sets `0.0.0.0` only for the internal request network. | Accept the broker as the residual trusted-host boundary or replace it with a stronger helper/isolation design. |

`GAP-019-V` removes `control-ingress` from the inventory table entirely. The
Traefik service now reads source-owned static routes from
`config/traefik-control.yaml` for `/notion/webhook`, `/v1`, `/api`, and `/`.
That route source is still checked by local tests, but it no longer needs Docker
provider metadata or a read-only Docker socket mount.

`GAP-019-D` removed `curator-refresh` from the writeable Docker socket set.
The service still refreshes vault definitions, Notion index work, fanout,
upgrade notifications, and pin-upgrade detection, but it no longer receives
the socket group or `/var/run/docker.sock`. Queued Docker-mode operator
upgrades remain in the trusted-host action path, but Docker-mode execution now
routes through `operator-upgrade-broker` rather than a raw supervisor
subprocess.

`GAP-019-E` local guard: `python/arclink_executor.py` validates live Docker
Compose apply/lifecycle requests before runner dispatch. Deployment IDs must be
safe path segments, apply project names must match the generated deployment
project, and env/compose files must resolve to the deployment's
`config/arclink.env` and `config/compose.yaml` under `ARCLINK_STATE_ROOT_BASE`.
Malformed requests fail with `ArcLinkExecutorError` before Docker is invoked.

`GAP-019-G` local broker: `deployment-exec-broker` is now the only
control-provisioning service with the writeable Docker socket. It requires
`ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN`, rejects raw `args`/`cmd`/`command`
fields, accepts only generated project names and `compose_up`, `compose_ps`, or
`compose_down` operation kinds, validates deployment config paths under
`ARCLINK_STATE_ROOT_BASE`, then reconstructs the Docker Compose command itself.
This removes direct Docker API authority from `control-provisioner`, but the
broker's socket access remains host-root-equivalent trusted-host authority.
`GAP-019-AA` narrows that broker's ambient configuration: it no longer inherits
broad `*arclink-env` values and keeps only minimal service env, the deployment
state-root bind for rendered Compose files, and the writeable Docker socket.
`GAP-019-AX` makes those rendered config inputs fail closed if the deployment
root, config root, `config/arclink.env`, or `config/compose.yaml` is
symlink-steered, missing, non-regular, or unreadable before Docker CLI lookup
or Compose subprocess dispatch.

`GAP-019-H` local delegation: `control-action-worker` no longer mounts
`/var/run/docker.sock` or receives the socket group. In Docker mode,
`control-action-worker` delegates the local lifecycle/apply path to
`deployment-exec-broker`.
`python/arclink_executor.py` refuses a local executor unless
`ARCLINK_DEPLOYMENT_EXEC_BROKER_URL` and
`ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN` are configured, so queued restart and
reprovision Docker lifecycle/apply calls route through
`deployment-exec-broker`.
`GAP-019-K` makes non-dry-run capture fail closed unless
`ARCLINK_ACTION_WORKER_ALLOW_ROOT_MIGRATION_CAPTURE=1` is set for an
operator-controlled migration window, and `python/arclink_pod_migration.py`
validates source, target, and capture directories before root file copying.
`GAP-019-N` removes the root boundary from `control-action-worker`: Docker-mode
Pod migration capture/materialization now fails closed without
`ARCLINK_MIGRATION_CAPTURE_HELPER_URL` and token. The
`migration-capture-helper` runs as root, drops Linux capabilities, has no
Docker socket, rejects raw command fields, accepts only `capture` and
`materialize`, and validates deployment id, prefix, migration id, source root,
target root, and `.migrations/<migration_id>` staging paths before copying.
`GAP-019-AC` narrows the same helper's service and path boundary: the Compose
service no longer inherits broad app env, and helper validation requires
source, target, and capture paths to stay under `ARCLINK_STATE_ROOT_BASE`
before `_copy_capture` or `_materialize_capture` can run.
That helper root boundary is still trusted-host authority and needs stronger
isolation or operator residual-risk acceptance.

`GAP-019-I` local broker: `agent-supervisor` no longer mounts
`/var/run/docker.sock` or receives the socket group. When dashboard access is
published, the supervisor calls `agent-supervisor-broker` with a bounded
operation kind, safe agent id, deterministic network/container names, Docker
network backend IP, loopback proxy port, and dashboard access-file path under
`ARCLINK_DOCKER_CONTAINER_PRIV_DIR`. The broker rejects raw `args`/`cmd`/
`command` fields and reconstructs the Docker network/proxy sidecar commands
itself. This removes the root+socket combination from the supervisor, but the
broker's socket access remains host-root-equivalent trusted-host authority.
`GAP-019-AF` narrows the same broker's executable lookup boundary:
`ARCLINK_DOCKER_BINARY` must be `docker` or a trusted absolute Docker CLI path;
unsafe, missing, non-executable, or non-Docker values fail before
`subprocess.run`.

`GAP-019-O` local helper: `agent-supervisor` no longer directly performs
container-local user/home setup. Docker-mode user/home setup now requires
`ARCLINK_AGENT_USER_HELPER_URL` and token. The `agent-user-helper` runs as root,
has no Docker socket, rejects raw command fields, accepts only
`ensure_user_home`, and validates `agent_id`, `unix_user`, Docker agent-home
root, agent home, Hermes home, and workspace path before creating paths,
persisting a numeric uid/gid assignment, or repairing ownership. The helper's
root authority over Docker agent homes remains trusted-host risk. `GAP-019-Q`
narrows the same helper's Compose capability boundary: Docker's default Linux
capability set is dropped, and only `CHOWN`, `DAC_OVERRIDE`, and `FOWNER` are
added back for bind-mount writes and `chown -R` under the validated Docker
agent-home root. This is least-capability hardening, not closure of the root
helper residual risk.
`GAP-019-S` adds configured-root confinement to the same helper: when
`ARCLINK_DOCKER_AGENT_HOME_ROOT` is configured, request `home_root` must match
it exactly after resolution before uid/gid assignment writes, directory
creation, account commands, or recursive ownership repair.
`GAP-019-AE` removes ambient `PATH` lookup from the same account/ownership
command path: the helper preflights `/usr/sbin/groupadd`,
`/usr/sbin/useradd`, and `/usr/bin/chown` before uid/gid assignment writes,
directory creation, account commands, or recursive ownership repair.
`GAP-019-BA` adds assignment-file preflight to the same root helper:
`.arclink-user-ids.json` and `.arclink-user-ids.json.tmp` under the Docker
agent-home root must be canonical non-symlink regular-or-missing files before
the helper reads or writes stable uid/gid assignments. A pre-existing symlink,
directory, or non-regular assignment path fails before root filesystem or
account work.
`GAP-019-AN` adds symlink escape rejection to the same path boundary: the
requested agent home, Hermes home, and workspace must remain both lexically
canonical and resolved to their expected canonical child target before uid/gid
assignment, account commands, directory creation, or recursive ownership
repair.

`GAP-019-P` local helper: `agent-supervisor` no longer directly builds
`setpriv` command arrays or owns gateway/dashboard process handles. Docker-mode
agent process execution now requires `ARCLINK_AGENT_PROCESS_HELPER_URL` and
token. The `agent-process-helper` runs as root, has no Docker socket, rejects
raw command fields, accepts only `run_once`, `ensure_processes`, and
`terminate_all`, and reconstructs only install, identity, refresh, cron,
gateway, and dashboard command forms after validating agent id, Unix user,
Docker agent-home root, agent home, Hermes home, workspace path, uid/gid, safe
env keys, absence of ArcLink control-token env keys, canonical env values, and
dashboard backend fields. The helper's root authority over Docker agent process
execution remains trusted-host risk.
`GAP-019-R` narrows that helper by passing the validated env through
subprocess `env=` instead of encoding env assignments in setpriv argv, keeping
startup command logs free of env values, and stripping supervisor helper/broker
tokens from per-agent process specs.
`GAP-019-W` makes the helper fail closed if a caller bypasses that supervisor
filter and submits ArcLink broker/helper/control token env keys; rejection
happens before log creation, `subprocess.run`, or `subprocess.Popen`.
`GAP-019-AN` applies the same symlink escape rejection to the process helper's
agent path context before helper log creation, one-shot `subprocess.run`, or
gateway/dashboard `subprocess.Popen`.
`GAP-019-AO` additionally rejects symlink-escaped
`state/docker/agent-process-helper` log directories before opening helper logs
or starting one-shot or long-running subprocesses.
`GAP-019-BB` records rejected helper requests in
`state/docker/agent-process-helper/rejections.jsonl` with redacted reason
codes and safe metadata only. Missing or unsafe configured private roots do not
fall back to another log location.
`GAP-019-BC` records rejected gateway broker requests in
`ARCLINK_STATE_ROOT_BASE/_broker-incidents/gateway-exec-broker/rejections.jsonl`
with redacted reason codes and safe deployment/project metadata only. Missing
or unsafe configured deployment state roots do not fall back to another log
location.
`GAP-019-BD` records equivalent redacted rejected-request incidents for the
deployment, migration-capture, agent-user, dashboard-sidecar, and
operator-upgrade lanes. The paths are:
`ARCLINK_STATE_ROOT_BASE/_broker-incidents/deployment-exec-broker/rejections.jsonl`,
`ARCLINK_STATE_ROOT_BASE/_helper-incidents/migration-capture-helper/rejections.jsonl`,
`ARCLINK_DOCKER_AGENT_HOME_ROOT/.helper-incidents/agent-user-helper/rejections.jsonl`,
`ARCLINK_DOCKER_CONTAINER_PRIV_DIR/state/docker/agent-supervisor-broker/rejections.jsonl`,
and
`ARCLINK_DOCKER_HOST_PRIV_DIR/state/docker/operator-upgrade-broker/rejections.jsonl`.
`GAP-019-AD` makes caller-controlled executable lookup fail closed at the same
boundary: request env `PATH` must match `SAFE_PATH`, `setpriv` is invoked as
`/usr/bin/setpriv`, and identity setup no longer falls back to bare `python3`
when the pinned runtime interpreter is absent.
`GAP-019-S` adds configured-root confinement to the same helper: when
configured, request `home_root`, `repo_dir`, `priv_dir`, `state_dir`, and
`runtime_dir` must match `ARCLINK_DOCKER_AGENT_HOME_ROOT`,
`ARCLINK_REPO_DIR`, `ARCLINK_PRIV_DIR` or
`ARCLINK_DOCKER_CONTAINER_PRIV_DIR`, the canonical private `state/` child, and
`RUNTIME_DIR` before any helper log is created or any `subprocess.run` or
`subprocess.Popen` call is made.
`GAP-019-AT` makes those process-helper repo, private-state, state, and runtime
roots fail closed if the configured or requested path includes symlink
components, so helper logs and command/interpreter paths cannot be redirected
through symlinked roots before `subprocess.run` or `subprocess.Popen`.
`GAP-019-AU` preflights the fixed repo command targets used by that helper.
Missing, symlinked, directory, unreadable, or non-executable
`bin/install-agent-user-services.sh`, `bin/hermes-shell.sh`,
`bin/user-agent-refresh.sh`, or unreadable/symlinked
`python/arclink_headless_hermes_setup.py` fails before helper logs or
subprocess execution.
`GAP-019-T` narrows the same process-helper surface by making its live host repo
bind read-only. The helper still executes validated root process operations,
but it no longer receives write access to the ArcLink checkout.

`GAP-019-J` local broker: queued Docker-mode operator upgrades and Docker
component-upgrade apply/final-upgrade calls now require
`ARCLINK_OPERATOR_UPGRADE_BROKER_URL` and token. The enrollment provisioner
delegates `run_operator_upgrade` and `run_pin_upgrade` requests to
`operator-upgrade-broker`; the broker rejects raw `args`/`cmd`/`command`
fields, reconstructs only `deploy.sh docker upgrade` or allowlisted
`component-upgrade.sh <component> apply <flag> <target> --skip-upgrade`
commands from `ARCLINK_DOCKER_HOST_REPO_DIR`, and confines logs to
`ARCLINK_DOCKER_CONTAINER_PRIV_DIR/state/operator-actions`. This removes raw
upgrade subprocess execution from the root supervisor path, but the broker's
writeable Docker socket and host checkout mount remain trusted-host authority.
That writable host checkout bind is now the explicit `GAP-019-U` exception;
agent process services and the dashboard broker do not receive writable host
repo binds.
`GAP-019-AB` narrows the same broker's ambient data path: it no longer inherits
broad `*arclink-env`, no longer mounts broad canonical private config/state or
`arclink-priv/secrets/container`, and `_operator_env` builds a child-process
env allowlist instead of copying the broker process env. The writable host repo
bind can still expose the nested `arclink-priv` needed for real upgrades, so
the broker remains a trusted-host boundary.
`GAP-019-AV` makes the broker preflight the fixed repo script targets before
opening private operator-action logs or dispatching subprocesses: `deploy.sh`
and `bin/component-upgrade.sh` must be exact non-symlink regular readable files
with executable bits. Missing, symlinked, directory, unreadable, or
non-executable targets fail closed.
`GAP-019-AW` confines request-supplied upstream deploy-key and known-hosts
paths before the same log/subprocess boundary: non-empty
`ARCLINK_UPSTREAM_DEPLOY_KEY_PATH` and
`ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE` values must stay under
`ARCLINK_DOCKER_HOST_PRIV_DIR` and must not be relative or symlink-steered.

`GAP-019-L` local guard: `agent-supervisor` validates active-agent
metadata before any helper, broker, or process-helper request. The
guard rejects unsafe `agent_id` and `unix_user` values,
requires Docker agent homes to resolve to
`ARCLINK_DOCKER_AGENT_HOME_ROOT/<unix_user>`, requires Hermes homes to be the
canonical `.local/share/arclink-agent/hermes-home` child, and keeps workspace,
log, process, and agent env keys inside their generated namespaces. This
prevents unsafe metadata from reaching `agent-user-helper`,
`agent-process-helper`, or dashboard/operator brokers.

`GAP-019-C` local guard: detached public Agent bridge jobs still validate their
stored work before execution. Legacy/direct jobs accept only the generated
`docker exec -i <deployment>-hermes-gateway-* ...arclink_public_agent_bridge.py`
form or the generated `docker compose ... exec -T hermes-gateway` form with
deployment config paths under `ARCLINK_STATE_ROOT_BASE`; brokered jobs contain
only the deployment-scoped gateway exec request. Rejected commands are recorded
as `public_agent_bridge_rejected_command` events in
`state/docker/jobs/public-agent-bridge.log` and as notification delivery
errors.

`GAP-019-F` local broker: `gateway-exec-broker` is now the only public-Agent
gateway exec service with the writeable Docker socket. It requires
`ARCLINK_GATEWAY_EXEC_BROKER_TOKEN`, rejects raw `cmd`/`command` fields, accepts
only safe deployment id/prefix path segments, generated project name, bounded
bridge payload, and timeout, then reconstructs and validates the
`hermes-gateway` Docker exec command itself. This removes direct Docker API authority from
`notification-delivery`, but the broker's socket access remains
host-root-equivalent trusted-host authority.
`GAP-019-Y` narrows that broker's ambient data access: the service no longer
inherits broad `*arclink-env` values and no longer mounts broad private
config/state or `arclink-priv/secrets/container`. It keeps the deployment
state-root bind for rendered Compose fallback files and the writeable Docker
socket for allowlisted gateway exec.
`GAP-019-AY` makes that broker fail closed on unsafe Compose fallback files:
symlinked, missing, non-regular, unreadable, or directory
`config/arclink.env` and `config/compose.yaml` targets are rejected before
fallback command dispatch.
`GAP-019-Z` narrows `agent-supervisor-broker` similarly: the service no longer
inherits broad `*arclink-env` values and no longer mounts broad private
config/state or `arclink-priv/secrets/container`. It keeps only Docker
binary/image, repo path, host/container private path metadata, broker
token/listener env, and the writeable Docker socket for dashboard sidecar work.
`GAP-019-AF` now preflights the configured Docker CLI path for that broker so
dashboard sidecar operations cannot be steered to a non-Docker executable.
`GAP-019-AZ` now preflights that broker's host/container private bind roots so
malformed `ARCLINK_DOCKER_HOST_PRIV_DIR` or
`ARCLINK_DOCKER_CONTAINER_PRIV_DIR` values cannot steer the dashboard sidecar
private-state `-v` mount before Docker lookup or sidecar dispatch.

`GAP-019-AG` now preflights the configured Docker CLI path for
`deployment-exec-broker` so deployment Compose operations cannot be steered to
a non-Docker executable. `GAP-019-AX` also preflights the rendered deployment
config files themselves so symlinked or non-regular `config/arclink.env` and
`config/compose.yaml` targets fail before Docker CLI lookup or Compose
subprocess dispatch.
`GAP-019-AI` now preflights the configured Docker CLI path for
`operator-upgrade-broker` so queued Docker-mode operator upgrades and
pinned-component apply/final-upgrade children cannot be steered to a non-Docker
executable.

`GAP-019-M` incident controls: the authority inventory is also the response
ledger for remaining residual services. For `deployment-exec-broker`,
`agent-supervisor-broker`, `operator-upgrade-broker`, and
`gateway-exec-broker`, watch broker healthchecks, container logs, rejected
raw-command/path events, service-health rows, operator action logs, and
public-Agent bridge logs. For `migration-capture-helper` and
`agent-user-helper`, watch helper healthchecks/logs, rejected raw-command/path
events, and root opt-in or helper-token failures. For `agent-supervisor`, watch
enrollment trace/status output and `state/docker/agent-supervisor/*.log`.
For `agent-process-helper`, also inspect the redacted
`state/docker/agent-process-helper/rejections.jsonl` incident stream before
retrying unsafe process-helper requests.
For `gateway-exec-broker`, inspect the redacted
`ARCLINK_STATE_ROOT_BASE/_broker-incidents/gateway-exec-broker/rejections.jsonl`
incident stream before retrying rejected public Agent broker requests.
These controls are intentionally fail closed: a rejected raw command, escaped
path, unsafe active-agent metadata row, missing helper token, or missing
root-capture opt-in should leave the affected action, deployment, dashboard, or
notification blocked until the source metadata is repaired or the operator
records a residual-risk decision.

**Implications:**

- Any process with writeable Docker socket access has host-root-equivalent capabilities.
  In short, writeable Docker socket access has host-root-equivalent capabilities.
  `deployment-exec-broker`, `agent-supervisor-broker`,
  `operator-upgrade-broker`, and `gateway-exec-broker` are trusted equivalents
  of the host operator for their bounded lifecycle jobs.
- `control-action-worker` no longer has direct writeable Docker socket access
  and no longer runs as root, but non-dry-run Docker-mode Pod migration capture
  remains fail-closed behind the root `migration-capture-helper`.
- `agent-supervisor` no longer has direct writeable Docker socket access and no
  longer owns root process execution. Container-local user/home setup is
  isolated to the root `agent-user-helper`, and setpriv-based agent process
  execution is isolated to the root `agent-process-helper`.
- `control-ingress` no longer mounts the Docker socket. It uses
  `config/traefik-control.yaml` for static Control Node routes and remains
  loopback-first.
- Non-root socket services drop all Linux capabilities. The remaining root
  containers, `migration-capture-helper`, `agent-user-helper`, and
  `agent-process-helper`, are explicitly root because migration file copy,
  per-agent user/home setup, and setpriv process execution still require those
  boundaries.
- Secrets enter container env via `docker.env` passthrough. They are not baked
  into the image, but environment values are still visible to sufficiently
  privileged container/Docker inspectors. Keep `docker.env` private and rotate
  via `./deploy.sh docker rotate-nextcloud-secrets`.
- Bind-mounted `arclink-priv/` state (DB, secrets, agent homes) is shared
  mutable state between host and containers.
- Per-agent dashboard sidecars created for the supervisor through the broker
  run on agent-specific isolated dashboard networks.
- The `health-watch` service does not mount the Docker socket; it runs health
  checks via network probes and DB reads only.
- Containers run as the image/runtime user selected by the Compose service.
  Do not treat container uid boundaries as a substitute for host trust while a
  service has Docker socket or private-state mounts.
- Dashboard backends must remain on agent-specific internal networks behind
  the dashboard auth proxy. Publishing a raw backend port bypasses the intended
  browser session gate.

**Reducing exposure:**

- Do not add Docker socket mounts to other services unless they require
  container lifecycle management.
- Do not treat a generic Docker socket proxy as tenant isolation. Use a
  command-specific broker with a small allowlist, or record the direct-socket
  residual risk in `config/docker-authority-inventory.json`.
- Keep `docker.env` readable only by the operator and the Docker runtime.
- Rotate secrets before any durable shared deployment.

## Notes

- Secrets belong in mounted runtime config, not in the image.
- Tailscale ingress is optional and remains an integration choice outside the
  default local Docker stack.
- Drive, Code, and Terminal are exposed as authenticated Hermes
  dashboard plugin routes, not separate sidecar IDE ports.
- The Docker app image installs Hermes and qmd from `config/pins.json`.
