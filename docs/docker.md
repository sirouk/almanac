# Docker Deployment

This is the first-class Docker Compose path for local and portable Almanac
deployments. It is separate from the existing host/systemd install path.

## Prerequisites

- Docker with `docker compose`.
- The repository checkout.
- No Podman requirement for Docker mode.

## Bootstrap

```bash
./deploy.sh docker reconfigure
```

Bootstrap creates `almanac-priv/`, seeds the vault template, writes
`almanac-priv/config/docker.env` when missing, and creates persisted state
directories for Nextcloud, qmd, PDF ingest, Notion index markdown, and job
status.

The wrapper passes `almanac-priv/config/docker.env` to Docker Compose as its
env file after bootstrap. Existing config is preserved by default; set
`ALMANAC_DOCKER_REWRITE_CONFIG=1` only when you intentionally want bootstrap
to regenerate the default Docker config.

`./deploy.sh docker ...` is the operator-facing control path. It delegates to
`bin/almanac-docker.sh` for the Docker-specific mechanics.

Fresh Docker config uses generated local secrets for Postgres and the Nextcloud
admin user. Rotate them deliberately before any durable shared deployment.
Raw `docker compose up` without the wrapper intentionally fails until those
secret values exist.

## Ports

`bin/almanac-docker.sh` assigns host ports during bootstrap and persists them in
`almanac-priv/config/docker.env`. It tries the standard Almanac ports first:

```text
QMD_MCP_PORT=8181
ALMANAC_MCP_PORT=8282
ALMANAC_NOTION_WEBHOOK_PORT=8283
NEXTCLOUD_PORT=18080
```

If any of those ports are already occupied, the wrapper chooses the next
available coherent Docker block, starting with:

```text
QMD_MCP_PORT=18181
ALMANAC_MCP_PORT=18282
ALMANAC_NOTION_WEBHOOK_PORT=18283
NEXTCLOUD_PORT=28080
```

The chosen block is also recorded in
`almanac-priv/state/docker/ports.json`. Set `ALMANAC_DOCKER_AUTO_PORTS=0` only
when you want fixed ports and prefer a startup failure over automatic reassignment.

Show the current assignment with:

```bash
./deploy.sh docker ports
```

## Start

```bash
./deploy.sh docker install
```

The default stack starts Almanac MCP, qmd MCP, Notion webhook, Nextcloud,
Postgres, Redis, vault watching, recurring job containers, memory synthesis,
and the Docker agent supervisor. The supervisor replaces the baremetal per-user
systemd units for enrolled agents: it reconciles refresh, Hermes gateway,
dashboard, authenticated dashboard proxy, cron tick, and code-server workspace
processes from the control-plane state.

The `memory-synth` job mirrors the baremetal `almanac-memory-synth.timer`: it
uses the configured `ALMANAC_MEMORY_SYNTH_*` values, or falls back to
`PDF_VISION_*`, to build cached semantic recall cards for managed-context
hot injection without putting LLM summarization on the chat path.

`install` and `upgrade` also apply the private operating profile when present,
record `state/almanac-release.json`, run Docker health, and run the same live
agent MCP tool smoke that the baremetal upgrade path uses.

Agent web surfaces are published individually as they are reconciled. Almanac
keeps the same access-state ports as baremetal, but Docker mode does not reserve
the entire possible port range at Compose startup.

## Privilege Boundary

Docker mode intentionally mounts `/var/run/docker.sock` into the
`agent-supervisor` container. That supervisor is the Docker-mode replacement for
per-user systemd units, so it needs Docker API access to create, update, and
remove per-agent gateway, dashboard proxy, cron, and workspace containers.

Treat Docker mode as a trusted-host deployment. Do not expose the Docker socket
or the agent-supervisor service publicly. The shared HTTP services in
`compose.yaml` remain bound to `127.0.0.1` by default so external access can be
handled deliberately through the same access rails as baremetal.

Optional profiles are available for `curator`, `quarto`, and `backup`:

```bash
COMPOSE_PROFILES=curator ./deploy.sh docker install
```

## Health

```bash
./deploy.sh docker health
./deploy.sh docker ps
```

Health validates the Compose file, required persisted directories, running
core services, core HTTP/database endpoints, and Docker user-agent managed
context/SOUL presence plus MCP token validity/refresh status when the stack is
up.

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
managed-context refresh, and validates or repairs each agent's private Almanac
MCP bootstrap token before starting gateways or agent web surfaces.

Pinned-component apply commands re-enter `./deploy.sh docker upgrade` after the
pin bump, so a Docker operator does not accidentally fall back into the
baremetal upgrade path.

Host/systemd-only commands remain explicit baremetal operations. `./deploy.sh
remove` tears down a host install; `./deploy.sh docker remove` is an alias for
Docker teardown and does not remove `almanac-priv/` bind-mounted state.

## Logs

```bash
./deploy.sh docker logs
./deploy.sh docker logs almanac-mcp
```

Recurring job status is written under:

```text
almanac-priv/state/docker/jobs/
```

## Stop And Teardown

```bash
./deploy.sh docker down
./deploy.sh docker teardown
```

`down` stops containers and keeps data. `teardown` also removes Compose named
volumes, but bind-mounted `almanac-priv/` state remains on disk.

## Notes

- Secrets belong in mounted runtime config, not in the image.
- Tailscale ingress is optional and remains an integration choice outside the
  default local Docker stack.
- Agent code-server workspaces are launched by the Docker supervisor through the
  host Docker socket, using the same access-state ports and credentials as the
  baremetal path.
- The Docker app image installs Hermes and qmd from `config/pins.json`.
