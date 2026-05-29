# ArcLink Data Safety

## State Models By Mode

ArcLink has one public operating mode. Legacy Shared Host state may still exist
on old hosts or in migration tests, but it is not the product install lane.

| Mode | State Model | Notes |
| --- | --- | --- |
| Sovereign Control Node | Dockerized product control plane with per-ArcPod state roots, Compose projects, and secret references rendered from control-plane rows. Current ArcPod state defaults are under the configured deployment state root, commonly `/arcdata/deployments`. | Paid self-serve control surface; provisioning and admin action workers are enabled by default, but live provider/account mutation still fails closed unless the operator configures the executor and external credentials. |
| Legacy Shared Host State | Public repo plus nested private state under `/home/arclink/arclink/arclink-priv/`; legacy enrolled-user Hermes homes may exist under `/home/<user>/.local/share/arclink-agent/hermes-home`. | Retired public install lane. Keep for migration, archival recovery, and host-side Operator workbench development only. |

Do not apply a legacy path to the Control Node or an ArcPod without checking
generated config and control-plane metadata.

## Per-Deployment Isolation

ArcPods are rendered as isolated Docker Compose stacks with:

- **Dedicated Postgres database** per deployment where the rendered pod uses one.
- **Dedicated Nextcloud instance** per deployment.
- **Dedicated Redis cache** per deployment where required.
- **Isolated state root** under the configured deployment state root.
- **Isolated Docker volumes** namespaced by Compose project name.

The access model is enforced by `arclink_access.py`, which pins the
`cloudflare_access_tcp` domain SSH strategy, `tailscale_direct_ssh` Tailscale
SSH strategy, and `nextcloud_dedicated` isolation model.

## Captain And Agent Access

ArcLink intentionally gives each Captain and Agent broad access to their own
ArcPod home, vault, workspace, and dashboard tools. This should feel like SSH
into that Captain's isolated Agent environment, not like a narrow file picker.
The boundary is not "hide the Captain's own files"; the boundary is "do not
expose the operator control plane, another Captain, or legacy host secrets."

Dashboard Drive, Code, and Terminal plugins therefore allow normal Captain-owned
files, including ordinary `.env` files inside the Captain's own Vault/Workspace,
while blocking control-plane/private-state env files, Hermes bootstrap tokens,
ArcLink secrets directories, private SSH material, and other users'
ArcPod roots. Terminal sessions run with a scrubbed allowlist environment
instead of inheriting operator/service secrets from the dashboard process.

Accepted ArcLink shares are mounted as a separate Linked root in Drive and
Code. Linked resources are scoped to the accepted file or directory, are
read-only from the receiver's share root, cannot be reshared from that root,
and may be copied into the receiver's own Vault/Workspace only through the
receiver's normal user boundary.

## Volume Layout

```text
<deployment-state-root>/{deployment_id}/
  vault/              # User vault files
  state/              # Runtime state, qmd indexes, memory synthesis
  nextcloud/          # Nextcloud data (if not using Docker volumes)
  published/          # Quarto/published output
  config/             # Per-deployment configuration
```

ArcPod Docker volumes follow the naming convention:
- `arclink-{deployment_id}_postgres_data`
- `arclink-{deployment_id}_nextcloud_data`
- `arclink-{deployment_id}_redis_data`

## Secret Storage

- Per-deployment secrets use `secret://...` references in database rows.
- Compose secrets are mounted at `/run/secrets/{name}` inside containers.
- Images supporting `_FILE` env vars (Postgres, Nextcloud) read from mounted files.
- No plaintext secret values in database, logs, API responses, or Compose intent.
- Legacy host secrets belong in private `arclink-priv/` config/state, not
  public docs or git history.
- Docker socket writers are trusted-host services. In Docker mode,
  non-root socket services drop all Linux capabilities and receive only the
  host Docker socket group. This reduces container process privileges but does
  not make writeable Docker socket access tenant-safe. `agent-supervisor` no
  longer declares an explicit root user for Docker agent process supervision.
  Container-local user/home setup now goes through `agent-user-helper`, and
  setpriv-based install, refresh, cron, gateway, and dashboard process
  execution now goes through `agent-process-helper`; both helpers are tokened
  root helpers with no Docker socket. The `migration-capture-helper`
  intentionally runs as root so Pod migration captures can read/write
  root-owned deployment bind mounts during an approved migration window.
  `GAP-019-AC` keeps that helper off broad `*arclink-env` and confines
  source, target, and staging paths under `ARCLINK_STATE_ROOT_BASE` before root
  file work starts. `GAP-019-AM` also keeps `agent-process-helper` request env
  fail-closed for dynamic-loader, Python path/startup, shell startup, Git/SSH
  command-steering, and secret-looking `*_TOKEN`, `*_SECRET`, `*_PASSWORD`, or
  `*_KEY` keys before root-reconstructed agent subprocesses. `GAP-019-AN`
  makes both root agent helpers reject symlink-escaped agent home, Hermes home,
  and workspace paths before root filesystem work, helper logs, or
  subprocesses. `GAP-019-AO` makes `agent-process-helper` reject symlinked
  helper log directories before opening logs or starting subprocesses. These
  root services must stay inside the private host boundary. `control-action-worker` no longer
  mounts the Docker socket and no
  longer runs as root in Docker mode; its local Docker lifecycle/apply calls
  must go through `deployment-exec-broker`, and its Pod migration file copy work
  must go through `migration-capture-helper`. `agent-supervisor` also no longer
  mounts the Docker socket; dashboard network and dashboard auth-proxy sidecar
  calls must go through `agent-supervisor-broker`, while queued Docker-mode
  operator upgrades must go through `operator-upgrade-broker`. The reviewed authority inventory is
  `config/docker-authority-inventory.json`; any new socket mount, explicit root
  service, or changed writer boundary must update that inventory and the Docker
  runbook before it can be treated as intentional. The `GAP-019-B2` review in
  that inventory rejects a generic Docker socket proxy as a closure claim; only
  command-specific brokers with deployment-scoped validation, or an explicit
  operator residual-risk decision, can narrow the remaining direct-socket
  boundary. `GAP-019-C` adds one local guard: detached public-Agent bridge jobs
  in `notification-delivery` now reject any command outside the generated
  `hermes-gateway` bridge exec allowlist and confine Compose fallback files to
  `ARCLINK_STATE_ROOT_BASE`. `GAP-019-F` moves that public-Agent gateway exec
  authority out of `notification-delivery`: the notification worker now sends a
  bounded deployment-scoped request to `gateway-exec-broker`, and only the
  broker mounts the writeable Docker socket for `hermes-gateway` exec. This
  reduces one direct public-bot delivery authority surface, but it does not make
  the remaining broker socket tenant-safe. `GAP-019-Y` narrows that broker's
  ambient data boundary: `gateway-exec-broker` no longer inherits broad
  `*arclink-env` values and no longer mounts broad private config/state or
  `arclink-priv/secrets/container`; it keeps only broker token/listener env,
  `ARCLINK_STATE_ROOT_BASE`, optional `ARCLINK_DOCKER_BINARY`, the deployment
  state-root bind, and the Docker socket. `GAP-019-AH` makes the same broker
  reject unsafe, missing, non-executable, non-Docker, or PATH-injected Docker
  CLI configuration before subprocesses run. `GAP-019-AY` makes the broker's
  Compose fallback fail closed unless fallback `config/arclink.env` and
  `config/compose.yaml` are exact non-symlink regular readable files under the
  deployment state-root config directory.
  CLI values before running-container discovery or gateway exec subprocesses
  run. `GAP-019-Z` applies the same reduction to
  `agent-supervisor-broker`: the dashboard sidecar broker no longer inherits
  broad app env and no longer mounts broad private config/state/secrets, while
  keeping only Docker binary/image, repo path, host/container private path
  metadata, broker token/listener env, and the Docker socket. `GAP-019-AZ`
  treats those host/container private path values as untrusted sidecar bind
  roots: relative paths, `/`, colon-bearing Docker volume specs,
  newline/carriage-return/NUL-bearing values, dot/dotdot components, and
  non-canonical ArcLink private roots fail closed before Docker lookup or
  dashboard auth-proxy `docker run -v` construction. `GAP-019-D` removes
  `curator-refresh` from the writeable Docker socket set because its source
  path handles refresh and detection work, while queued Docker-mode upgrade
  execution is routed through the enrollment provisioner path. `GAP-019-E`
  adds local executor preflight: live local/SSH Docker apply and lifecycle
  requests reject unsafe deployment IDs, mismatched apply project names, and
  env/compose files outside the configured `ARCLINK_STATE_ROOT_BASE`
  deployment config root before Docker runner dispatch. `GAP-019-G` moves the
  Docker-mode local executor socket authority out of `control-provisioner`:
  the provisioner no longer mounts the socket and instead sends a bounded
  operation request to `deployment-exec-broker`, which rejects raw commands and
  reconstructs allowlisted Compose `up`, `ps`, and `down` operations itself.
  The broker's direct writeable Docker socket remains trusted-host authority
  until stronger isolation or an operator residual-risk decision replaces it.
  `GAP-019-AG` makes the same broker reject unsafe, missing, non-executable,
  or non-Docker `ARCLINK_DOCKER_BINARY` values before deployment Compose
  subprocesses run. `GAP-019-AX` makes the rendered deployment config files
  themselves fail closed when the deployment root, config root,
  `config/arclink.env`, or `config/compose.yaml` is symlinked, missing,
  non-regular, or unreadable before Docker CLI lookup or Compose subprocess
  dispatch.
  `GAP-019-H` removes the Docker socket and socket group from
  `control-action-worker`; Docker-mode local executors fail closed without the
  deployment exec broker URL and token. This narrows action-worker lifecycle
  authority. `GAP-019-K` narrows the capture path further: non-dry-run Pod
  migration capture fails closed unless
  `ARCLINK_ACTION_WORKER_ALLOW_ROOT_MIGRATION_CAPTURE=1` is set for an
  operator-controlled migration window, and source/target/capture paths must be
  deployment-scoped ArcLink state roots before any root file copy starts.
  `GAP-019-N` removes the root boundary from `control-action-worker` by adding
  `migration-capture-helper`; Docker-mode capture/materialization fails closed
  without helper URL/token, and the helper rejects raw commands before
  reconstructing allowlisted `capture` or `materialize` file-copy operations.
  `GAP-019-AC` narrows the helper's ambient data boundary by preserving only
  `ARCLINK_STATE_ROOT_BASE` plus helper token/listener env and by rejecting
  paths outside the configured state-root base before copy/materialize work.
  The helper's deployment-bind-mount root authority remains trusted-host risk
  until stronger isolation or an operator residual-risk decision replaces it.
  `GAP-019-O` removes direct user/home setup from `agent-supervisor` by adding
  `agent-user-helper`; Docker-mode user/home setup fails closed without helper
  URL/token, and the helper rejects raw commands before validating agent id,
  Unix user, Docker agent-home root, agent home, Hermes home, and workspace
  path for a single `ensure_user_home` operation. The helper's Docker-agent-home
  root authority remains trusted-host risk until stronger isolation or an
  operator residual-risk decision replaces it. `GAP-019-Q` narrows that helper's
  Compose capability boundary by dropping Docker's default Linux capabilities
  and adding back only `CHOWN`, `DAC_OVERRIDE`, and `FOWNER` for canonical
  bind-mount writes and ownership repair; this is hardening, not closure of the
  root-helper residual risk. `GAP-019-AE` also pins the helper's
  account/ownership commands to `/usr/sbin/groupadd`, `/usr/sbin/useradd`, and
  `/usr/bin/chown`, and fails closed before uid/gid assignment writes,
  directory creation, account commands, or recursive ownership repair if any
  trusted executable is unavailable.
  `GAP-019-I` removes
  the Docker socket and socket group from `agent-supervisor`; dashboard
  network/proxy sidecar operations now fail closed without the agent supervisor
  broker URL and token. This removes the root+socket combination from the
  supervisor, but the broker's writeable socket, the agent-user-helper root
  boundary, and the agent-process-helper root boundary remain open for stronger
  isolation or operator residual-risk decisions. `GAP-019-J`
  routes queued Docker-mode operator
  upgrades and pinned-component upgrade apply/final-upgrade execution through
  `operator-upgrade-broker`: the enrollment provisioner fails closed without
  broker URL/token, sends no raw command fields, and the broker reconstructs only
  allowlisted upgrade commands while confining logs to private
  `state/operator-actions`. This narrows the supervisor command path, but the
  broker's writeable socket and live host checkout mount remain trusted-host
  authority. `GAP-019-AB` narrows that broker's ambient data exposure by
  removing broad `*arclink-env` inheritance, broad canonical private
  config/state mounts, and the `arclink-priv/secrets/container` mount, and by
  replacing full process env inheritance with a child-process env allowlist for
  upgrade subprocesses. The writable host checkout can still reach nested
  private state needed for real upgrades, so the broker remains a trusted-host
  boundary. `GAP-019-AI` narrows the same broker's executable lookup by
  preserving `ARCLINK_DOCKER_BINARY` for upgrade subprocesses only after it
  resolves to a trusted absolute Docker CLI path; unsafe, missing,
  non-executable, non-Docker, relative, or PATH-injected values fail closed.
  `GAP-019-AW` confines the same broker's request-supplied upstream deploy-key
  metadata: non-empty `ARCLINK_UPSTREAM_DEPLOY_KEY_PATH` and
  `ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE` values must be absolute non-symlink paths
  under `ARCLINK_DOCKER_HOST_PRIV_DIR` before child env construction, private
  operator logs, or upgrade subprocesses.
  `GAP-019-L` validates the `agent-supervisor`
  delegation path: active-agent metadata, Unix user names, canonical Docker
  agent homes, Hermes homes, workspace paths, supervisor log/process keys, and
  agent process env keys are validated before helper, broker, or process-helper
  requests. `GAP-019-P` moves setpriv process execution into
  `agent-process-helper`, whose root authority remains trusted-host risk.
  `GAP-019-R` narrows that process-helper exposure by passing validated env
  through subprocess `env=`, keeping env assignments out of setpriv argv and
  helper startup logs, and stripping supervisor broker/helper tokens before
  per-agent process specs reach the helper. It is env exposure hardening, not a
  closure of the root-helper residual risk. `GAP-019-W` adds the helper-side
  fail-closed check for that boundary by rejecting ArcLink broker/helper/control
  token env keys before log creation or subprocess execution. `GAP-019-AM`
  rejects dynamic-loader, Python path/startup, shell startup, Git/SSH
  command-steering, and secret-looking process env keys at the same helper
  boundary before logs or subprocesses; `agent-supervisor` fails closed on that
  unapproved non-token key family before helper payload construction.
  `GAP-019-AD` closes the helper's caller-controlled lookup slice by rejecting
  request `PATH` values that differ from `SAFE_PATH`, invoking
  `/usr/bin/setpriv` by absolute path, and failing identity setup closed
  without the pinned runtime venv Python. `GAP-019-AJ` adds desired-process
  signature tracking for
  long-running gateway/dashboard handles: changed validated command, cwd, or
  env contracts stop the stale process group before replacement, identical
  specs do not churn, and shutdown escalates from SIGTERM to SIGKILL before
  failing closed. `GAP-019-X`
  reduces the helper's ambient service exposure in Compose by removing broad
  `*arclink-env` inheritance and the `arclink-priv/secrets/container` mount
  from `agent-process-helper`; the helper keeps only explicit non-secret
  Docker mode/path validation env plus token/listener keys at service startup.
  `GAP-019-AK` removes default network reachability from the tokened
  broker/helper services. Their request lanes now use internal Compose
  networks shared only with legitimate callers; `agent-process-helper` and
  `operator-upgrade-broker` keep separate single-service egress networks for
  outbound runtime or upgrade work without making their helper APIs reachable
  from the default network.
  `GAP-019-AL` makes the same seven services fail closed unless private Docker
  config explicitly sets
  `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED=accepted`. The gate is checked
  before HTTP listener bind and direct helper/broker request work for
  `deployment-exec-broker`, `migration-capture-helper`, `agent-user-helper`,
  `agent-process-helper`, `agent-supervisor-broker`,
  `operator-upgrade-broker`, and `gateway-exec-broker`. This records the
  trusted-host acknowledgement boundary; it does not make the socket/root
  surfaces tenant-safe, close `GAP-019`, or close live proof gates such as
  `GAP-001`, `PG-UPGRADE`, `PG-PROVISION`, `PG-BOTS`, or `PG-HERMES`.
  `GAP-019-AP` makes direct/local execution of those same broker/helper modules
  bind `127.0.0.1` by default. Compose remains the explicit source-owned
  `0.0.0.0` opt-in for internal request networks, and container healthchecks
  stay on `127.0.0.1`. `--host` and service-specific `ARCLINK_*_HOST`
  overrides still work, so broad listener exposure is intentional instead of a
  direct-run default.
  `GAP-019-AQ` narrows the `agent-supervisor` provisioner child env allowlist:
  the enrollment provisioner child no longer inherits the supervisor's full
  `os.environ.copy()` payload. It keeps Docker mode/path config, runtime roots,
  service URLs, and helper/broker values needed for Docker enrollment and
  queued operator actions, but not unrelated payment, provider, bot, ingress,
  memory-synthesis, session, fleet, Python path, or Git/SSH steering env keys.
  The supervisor still has private config/state/vault mounts for Docker agent
  reconciliation, so this is child-process env hardening only.
  `GAP-019-AR` narrows the dashboard backend host boundary for
  `agent-process-helper` and `agent-supervisor-broker`: dashboard backend host
  values must be loopback or Docker-internal IPs. Wildcard, globally routable,
  multicast, malformed, or non-IP values fail before helper log creation,
  `subprocess.Popen`, Docker CLI lookup, or dashboard auth-proxy sidecar
  construction. This is dashboard process/proxy routing hardening only; both
  residual trusted-host boundaries remain open.
  `GAP-019-AS` narrows the configured Docker agent-home root boundary for
  `agent-user-helper` and `agent-process-helper`: the configured or requested
  agent-home root, including `ARCLINK_DOCKER_AGENT_HOME_ROOT`, must not be a
  symlink or include symlink components before uid/gid assignment writes,
  ownership repair, helper log creation, or subprocess execution. This is
  agent-home root path hardening only; both root helpers remain trusted-host
  residual risk.
  `GAP-019-BA` narrows the `agent-user-helper` assignment persistence path:
  `.arclink-user-ids.json` and `.arclink-user-ids.json.tmp` must be canonical
  non-symlink regular-or-missing children of the Docker agent-home root before
  uid/gid assignments are read or written. Symlinked, directory, or non-regular
  assignment paths fail before assignment writes, account commands, agent-home
  directory creation, or recursive chown.
  `GAP-019-AT` narrows the process-helper configured-root boundary:
  configured or requested repo, private-state, state, and runtime roots,
  including `ARCLINK_REPO_DIR`, `ARCLINK_PRIV_DIR`,
  `ARCLINK_DOCKER_CONTAINER_PRIV_DIR`, request `state_dir`, and `RUNTIME_DIR`,
  must not include symlink components before helper logs, cwd/command/runtime
  lookup, or subprocess execution. This is process-helper path hardening only;
  the root helper remains trusted-host residual risk.
  `GAP-019-AU` narrows the same root helper's fixed command target boundary:
  `bin/install-agent-user-services.sh`, `bin/hermes-shell.sh`,
  `bin/user-agent-refresh.sh`, and
  `python/arclink_headless_hermes_setup.py` must be canonical repo-child
  command targets, regular readable files, and shell targets must be
  executable before helper logs or subprocess execution. This is command target
  hardening only; the root helper remains trusted-host residual risk.
  `GAP-019-Y` applies the same principle to `gateway-exec-broker`, preserving
  only the optional Docker binary selection, deployment state-root bind needed
  for rendered Compose fallback files, and removing broad private
  config/state/secrets mounts from the public Agent gateway exec broker.
  `GAP-019-AH` then hardens that broker's executable lookup so unsafe Docker
  CLI configuration fails closed before subprocesses run. `GAP-019-AY` then
  hardens the broker's rendered fallback file boundary: symlinked, missing,
  non-regular, unreadable, or directory `config/arclink.env` and
  `config/compose.yaml` files fail closed before fallback dispatch.
  `GAP-019-AA` applies the minimal service env rule
  to `deployment-exec-broker`, preserving only broker token/listener settings,
  `ARCLINK_STATE_ROOT_BASE`, optional Docker binary, the deployment state-root
  bind, and the writeable Docker socket needed for allowlisted deployment
  Compose operations. `GAP-019-AG` then hardens that broker's executable
  lookup: unsafe, missing, non-executable, or non-Docker
  `ARCLINK_DOCKER_BINARY` values fail closed before deployment Compose
  subprocesses run. `GAP-019-AX` then hardens the rendered config-file
  boundary: symlink-steered, missing, non-regular, or unreadable
  `config/arclink.env` and `config/compose.yaml` files fail closed before
  Docker CLI lookup or Compose subprocess dispatch. `GAP-019-Z` applies that principle to
  `agent-supervisor-broker`, preserving only the Docker path/image metadata and
  broker token/listener env needed for dashboard sidecar reconstruction while
  removing broad private config/state/secrets mounts from the dashboard broker.
  `GAP-019-AF` then hardens that broker's executable lookup: unsafe, missing,
  non-executable, or non-Docker `ARCLINK_DOCKER_BINARY` values fail closed
  before dashboard network/proxy subprocesses run.
  `GAP-019-AZ` hardens the sidecar private bind root itself: unsafe
  `ARCLINK_DOCKER_HOST_PRIV_DIR` or `ARCLINK_DOCKER_CONTAINER_PRIV_DIR` values
  fail before Docker lookup, config hashing, or `docker run -v` dispatch.
  `GAP-019-U` splits queued
  Docker-mode operator upgrades out of `agent-supervisor-broker` and into
  `operator-upgrade-broker`; the enrollment provisioner now fails closed
  without `ARCLINK_OPERATOR_UPGRADE_BROKER_URL` and token, the dashboard broker
  no longer accepts upgrade operation kinds, and the writable host repo
  exception belongs only to the operator-upgrade broker. `GAP-019-AV` makes
  that broker reject missing, symlinked, directory, unreadable, or
  non-executable fixed `deploy.sh` and `bin/component-upgrade.sh` targets before
  private operator logs or upgrade subprocesses. `GAP-019-AW` also rejects
  relative, out-of-private-state, or symlink-steered upstream deploy-key and
  known-hosts paths before child env construction, private operator logs, or
  upgrade subprocesses. `GAP-019-S` narrows both helper
  request-path boundaries: `agent-user-helper` rejects configured Docker
  agent-home root mismatches before root filesystem/account work, and
  `agent-process-helper` rejects configured Docker agent-home, repo,
  private-state, state, and runtime root mismatches before helper logs or
  subprocess execution. `GAP-019-AN` adds symlink escape checks for the same
  agent home, Hermes home, and workspace paths before uid/gid assignment,
  account commands, recursive chown, helper logs, or subprocess execution.
  `GAP-019-AS` adds the configured-root symlink check: symlinked
  configured/requested agent-home roots fail before either helper writes under
  the Docker agent-home tree, opens helper logs, or starts subprocesses.
  `GAP-019-BA` adds the assignment-file check for `agent-user-helper`:
  symlinked, directory, or non-regular `.arclink-user-ids.json` and
  `.arclink-user-ids.json.tmp` paths fail before the root helper can persist
  uid/gid assignments or continue to account/home setup.
  `GAP-019-AT` adds the process-helper configured-root symlink check:
  symlinked configured/requested repo, private-state, state, and runtime roots
  fail before helper logs, cwd/command/runtime lookup, or subprocess
  execution.
  `GAP-019-AU` adds fixed repo command target checks: missing, symlinked,
  directory, unreadable, or non-executable command targets fail before helper
  logs or subprocess execution.
  `GAP-019-AO` adds the matching process-helper log confinement check:
  symlinked `state/docker/agent-process-helper` directories or helper log files
  fail before log open or subprocess execution.
  `GAP-019-BB` adds a redacted process-helper rejection incident stream at
  `state/docker/agent-process-helper/rejections.jsonl` when the configured
  private root is safe. It records only safe metadata and sanitized reason
  codes; raw request bodies, process args, env values, private paths, tokens,
  and stack traces are not written.
  `GAP-019-BC` adds a redacted `gateway-exec-broker` rejection incident stream
  at
  `ARCLINK_STATE_ROOT_BASE/_broker-incidents/gateway-exec-broker/rejections.jsonl`
  when the configured deployment state root is absolute, non-root, existing,
  and non-symlinked. It records only safe deployment/project metadata,
  trusted-host acknowledgement state, error class, and sanitized reason codes;
  raw request bodies, bridge payload values, bot tokens, chat ids, user ids,
  message text, process args, rendered config paths, private paths, and stack
  traces are not written.
  `GAP-019-BD` extends redacted rejected-request incident streams to the
  remaining local high-authority lanes: `deployment-exec-broker`,
  `migration-capture-helper`, `agent-user-helper`,
  `agent-supervisor-broker`, and `operator-upgrade-broker`. The incident rows
  are written only under scoped state roots or the dashboard broker's narrow
  incident mount, and include safe metadata such as service, event,
  trusted-host acknowledgement state, error class, reason, operation, safe
  deployment/migration/agent ids, or item counts. They do not write raw request
  bodies, command arrays, process args, payload values, private paths, tokens,
  chat ids, user ids, message text, or stack traces. Unsafe incident roots do
  not fall back to another path.
  This is path-confinement hardening, not a closure of
  either helper's residual root authority. `GAP-019-T` narrows live-checkout
  write access by making `agent-supervisor`, `agent-process-helper`, and
  `curator-refresh` use read-only host repo binds for script reads;
  `operator-upgrade-broker` remains the explicit writable host repo exception
  for allowlisted queued Docker-mode operator upgrades, and that exception
  remains trusted-host residual risk.
  `GAP-019-V` removes the read-only Docker provider discovery boundary from
  `control-ingress`. Control Node ingress now loads static Traefik routes from
  `config/traefik-control.yaml` for `/notion/webhook`, `/v1`, `/api`, and `/`,
  so the service no longer needs `/var/run/docker.sock`.
  `GAP-019-M` adds incident controls to the same authority inventory:
  remaining writeable socket brokers and explicit root helpers must name
  monitored signals, status/log/audit locations, triage steps, fail closed
  actions, and the operator escalation boundary. Treat rejected raw commands,
  escaped paths, unsafe agent metadata, process-helper `rejections.jsonl` rows,
  gateway-exec broker `_broker-incidents/gateway-exec-broker/rejections.jsonl`
  rows, missing helper tokens, and missing root-capture opt-in as trusted-host
  boundary incidents until the metadata is repaired or the operator records a
  residual-risk decision.

## Knowledge And Memory Rails

Agents should use ArcLink MCP tools before raw rummaging:
`knowledge.search-and-fetch`, `vault.search-and-fetch`, `vault.fetch`,
`notion.search-and-fetch`, `notion.fetch`, `ssot.read`, `ssot.write`, and
`ssot.status`.

The vault qmd rail is limited to vault-owned collections such as `vault` and
`vault-pdf-ingest`. Notion content is exposed through the Notion-specific
indexed rail and live Notion fetch paths, with live reads falling back to the
indexed markdown cache when the API cannot prove the page. PDF sidecar metadata
must not leak generated host paths across API boundaries.

`arclink-managed-context` injects compact awareness sections and
`[managed:recall-stubs]` into Hermes turns. These stubs are routing hints, not
evidence. They tell the agent which rail to fetch from before citing,
answering, or changing state. Dynamic managed context is not written into
Hermes `MEMORY.md`.

Almanac is the knowledge-store lineage/rail inside ArcLink. ArcLink is the
current product identity.

## Backup Plan

See `docs/arclink/backup-restore.md` for the full backup and restore procedure.

- **Control database:** Daily SQLite `.backup` snapshots, 30-day retention.
- **Per-deployment Postgres:** Daily `pg_dump`, 30-day retention.
- **Vault files:** Continuous git auto-commit backup.
- **State roots:** Weekly rsync, 90-day retention.

## Teardown Safeguards

Destructive operations are allowed only through scoped, audited control rails.
The product goal is to avoid tying the agent's hands while still making
dangerous writes reversible, attributable, and policy-aware. Gating levels:

1. **Admin confirmation required.** Teardown actions via
   `POST /api/v1/admin/actions` require an admin session with mutation role,
   CSRF token, reason, and idempotency key.

2. **Audit logging.** All teardown intents are recorded in `arclink_audit_log`
   with actor, reason, target, and timestamp before execution.

3. **State root preservation.** The executor's rollback contract requires
   `preserve_state_roots` in the plan. Rollback rejects action names that
   imply deleting customer state roots or vault data.

4. **Volume preservation by default.** `docker compose down` (without `-v`)
   preserves data volumes. Volume deletion requires explicit `destructive: true`
   flag in the rollback plan.

5. **DNS teardown is separate.** DNS record removal is a distinct admin action,
   not bundled with container teardown.

6. **Destructive state deletes are separately gated.** The executor's
   `_is_destructive_state_delete` check prevents accidental data loss.

7. **SSOT destructive writes stay brokered.** Notion archive/delete/trash
   behavior should go through `ssot.write` so ArcLink can apply page scope,
   ownership verification, approval/undo policy, audit records, and user
   notifications. Raw live Notion access is for reads and exact fetches, not
   bypassing the broker.

## Secret Leak Prevention

- `_reject_secret_material()` is called on all dashboard read-model outputs
  and admin action metadata before write.
- Structured events redact sensitive fields.
- API error responses use generic safe error strings, never raw tracebacks.
- Tests verify no secret patterns appear in logs, docs, or generated artifacts
  (see `tests/test_public_repo_hygiene.py`).
