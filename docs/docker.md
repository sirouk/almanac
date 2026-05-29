# Retired Shared Host Docker Mode

The public `./deploy.sh docker ...` Shared Host Docker control center is retired.

ArcLink still uses Docker Compose as the Sovereign Control Node substrate and
places ArcPods as Docker deployments on registered fleet workers. Operators
should reach that substrate only through the Control Node commands:

```bash
./deploy.sh control install
./deploy.sh control upgrade
./deploy.sh control health
./deploy.sh control ps
./deploy.sh control ports
./deploy.sh control logs [SERVICE]
```

Fleet expansion and ArcPod placement now belong to:

```bash
./deploy.sh control fleet-key
./deploy.sh control register-worker
./deploy.sh control inventory list
./deploy.sh control inventory health --json
./deploy.sh control inventory probe-all --json
```

The old Docker helper and Compose files remain in the repository because the
Control Node uses them internally and because migration/tests still validate
trusted-host boundaries. They are not a public product mode.

If a runbook still tells an operator to use `./deploy.sh docker ...`, update it
to the equivalent `./deploy.sh control ...` command or to a Control Node fleet
inventory/provisioning action.

## Internal Socket And Private-State Boundaries

`control-ingress` now uses a static Traefik file-provider config at
`config/traefik-control.yaml`; it is intentionally not listed as a Docker socket
writer. `control-provisioner` no longer mounts the Docker socket.
`control-action-worker` no longer mounts the Docker socket and
`control-action-worker` no longer runs as root. `notification-delivery` also no
longer mounts the Docker socket, `curator-refresh` no longer mounts the Docker
socket, `control-ingress` no longer mounts the Docker socket, and the
`health-watch` service does not mount the Docker socket. Writeable Docker socket
access has host-root-equivalent capabilities. Non-root socket services drop all
Linux capabilities. `ARCLINK_DOCKER_SOCKET_GID` keeps group ownership explicit
for the shared ArcLink app image as the `arclink` Unix user. Recurring jobs
write job status files rather than relying on broad logs.

`notification-delivery` also no longer mounts the Docker socket.
`curator-refresh` no longer mounts the Docker socket. writeable Docker socket access has host-root-equivalent capabilities. recurring job status files remain the operational audit trail.
Non-root socket services drop all Linux capabilities.

| Service | Boundary |
| --- | --- |
| `deployment-exec-broker` | Tokened broker for deployment-scoped Compose work. |
| `migration-capture-helper` | Root helper for approved migration capture only; `migration-capture-helper` intentionally runs as root. |
| `agent-user-helper` | Tokened root helper for `ensure_user_home` and ownership repair. |
| `agent-process-helper` | Tokened process helper using `ARCLINK_AGENT_PROCESS_HELPER_TOKEN`. |
| `gateway-exec-broker` | Tokened gateway bridge constrained to deployment state and Compose config. |

Additional retained hardening anchors:

- `GAP-019-X`: helpers avoid broad `*arclink-env` inheritance and broad
  `arclink-priv/secrets/container` mounts.
- `GAP-019-AJ`: desired-process signature changes use controlled `SIGTERM` and
  `SIGKILL` escalation.
- `GAP-019-AM`: child env validation rejects `LD_*` and secret-looking values.
- `GAP-019-Z`: `agent-supervisor-broker` avoids broad private config/state/secrets.
- `GAP-019-AZ`: `ARCLINK_DOCKER_HOST_PRIV_DIR` private bind roots are validated.
- `GAP-019-BA`: `.arclink-user-ids.json.tmp` writes use exclusive no-follow.
- `GAP-019-BB`: rejection logs use `rejections.jsonl` without raw request bodies.
- `GAP-019-BC`: gateway rejects are written under
  `_broker-incidents/gateway-exec-broker/rejections.jsonl`.
- `GAP-019-BD`: helper rejects include
  `_helper-incidents/migration-capture-helper/rejections.jsonl`.

## Internal Authority Inventory Anchors

`config/docker-authority-inventory.json` remains the source-owned inventory for
trusted-host Compose authority. Keep these GAP anchors visible while retiring
the public Docker mode:

- `GAP-019-M`: incident controls for high-authority helper failures fail closed.
- `GAP-019-B2`: no generic Docker socket proxy is exposed.
- `GAP-019-Q`: `agent-user-helper` keeps only required capabilities such as
  `CHOWN`, `DAC_OVERRIDE`, and `FOWNER`.
- `GAP-019-R`: helper startup logs and process argv must stay secret-safe.
- `GAP-019-T`: broker/helper mounts keep the read-only host repo boundary unless
  a specifically audited operator path requires otherwise.
- `GAP-019-U`, `GAP-019-AB`, `GAP-019-AI`, `GAP-019-AV`, `GAP-019-AW`:
  `operator-upgrade-broker` reconstructs allowlisted `deploy.sh` and component
  upgrade actions, uses a child-process env allowlist, validates Docker CLI
  paths, writes private logs, and scopes `ARCLINK_UPSTREAM_DEPLOY_KEY_PATH`.
- `GAP-019-V`: `control-ingress` uses static Traefik config from
  `config/traefik-control.yaml`.
- `GAP-019-Y`, `GAP-019-AH`, `GAP-019-AY`, `GAP-019-BC`:
  `gateway-exec-broker` is confined to deployment state-root lookups, validates
  Docker CLI paths, accepts only deployment config such as `config/arclink.env`,
  and records `_broker-incidents/gateway-exec-broker/rejections.jsonl`.
- `GAP-019-AA`, `GAP-019-AG`, `GAP-019-BD`:
  `deployment-exec-broker` keeps a minimal service env, validates Docker CLI
  paths, and shares rejection monitoring with `agent-supervisor-broker`,
  `agent-user-helper`, and `operator-upgrade-broker/rejections.jsonl`.
- `GAP-019-AC`: `migration-capture-helper` confines approved migration work
  under `ARCLINK_STATE_ROOT_BASE`.
- `GAP-019-AF`: `agent-supervisor-broker` validates Docker CLI use.
- `GAP-019-AK`: high-authority helpers stay off the internal Compose default network unless explicitly needed.
- `GAP-019-AL`: `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED=accepted`
  is required before trusted-host broker/helper work runs.
- `GAP-019-AP`: externally exposed services bind deliberately; loopback
  defaults use `127.0.0.1` and public binds such as `0.0.0.0` require intent.
- `GAP-019-AQ`: provisioner child processes use an env allowlist.
- `GAP-019-AR`: dashboard backend host forwarding is explicit.
- `GAP-019-AS`: agent-home root paths reject symlink escapes.
- `GAP-019-AT`: repo and runtime paths reject symlink escapes.
- `GAP-019-AU`: command target validation protects helpers such as
  `hermes-shell.sh`.
