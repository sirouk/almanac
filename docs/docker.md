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
per-deployment Hermes, files, and code surfaces on stable tailnet HTTPS ports
starting at `ARCLINK_TAILNET_SERVICE_PORT_BASE`. If the host Tailscale CLI is
missing, publication is skipped and health continues; deployment metadata remains
the source of truth after successful publication.

## Privilege Boundary

Docker mode intentionally mounts `/var/run/docker.sock` into the
`agent-supervisor` container. That supervisor is the Docker-mode replacement for
per-user systemd units, so it needs Docker API access to create, update, and
remove per-agent gateway, dashboard proxy, cron, and workspace containers. User
dashboard backends are bound to agent-specific internal Docker network
addresses; only the dashboard auth-proxy sidecar is published to host loopback.

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
services that need Docker API access for routing or lifecycle management:

| Service | Purpose | Why it needs the Docker socket |
| --- | --- | --- |
| `control-ingress` | Traefik HTTP ingress | Read-only Docker provider discovery for `control-web`, `control-api`, and the Notion webhook |
| `control-provisioner` | Sovereign fleet provisioner | Creates and manages deployment containers when `ARCLINK_EXECUTOR_ADAPTER=local` |
| `agent-supervisor` | Per-agent container lifecycle | Reconciles agent containers, dashboard proxies, and Hermes agent runtimes |
| `curator-refresh` | Operator maintenance loop | Runs queued Docker-mode upgrades and Compose repair commands from Curator/operator actions |

The lifecycle services also bind-mount the live repository checkout and
`arclink-priv/` for config, state, and secrets access. `control-ingress` uses a
read-only socket mount and does not receive `arclink-priv/`.

**Implications:**

- Any process with writeable Docker socket access has host-root-equivalent capabilities.
  `control-provisioner`, `agent-supervisor`, and `curator-refresh` are trusted
  equivalents of the host operator.
- `control-ingress` has read-only socket access for route discovery, but it is
  still part of the trusted host boundary and must remain loopback-first.
- Secrets enter container env via `docker.env` passthrough. They are not baked
  into the image, but environment values are still visible to sufficiently
  privileged container/Docker inspectors. Keep `docker.env` private and rotate
  via `./deploy.sh docker rotate-nextcloud-secrets`.
- Bind-mounted `arclink-priv/` state (DB, secrets, agent homes) is shared
  mutable state between host and containers.
- Per-agent containers created by the supervisor run on the shared Docker
  network (`arclink_default`) with agent-specific isolated dashboard networks.
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
- Keep `docker.env` readable only by the operator and the Docker runtime.
- Rotate secrets before any durable shared deployment.

## Notes

- Secrets belong in mounted runtime config, not in the image.
- Tailscale ingress is optional and remains an integration choice outside the
  default local Docker stack.
- Drive, Code, and Terminal are exposed as authenticated Hermes
  dashboard plugin routes, not separate sidecar IDE ports.
- The Docker app image installs Hermes and qmd from `config/pins.json`.
