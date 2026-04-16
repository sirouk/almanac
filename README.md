# Almanac

`Almanac` is the public infrastructure repo for a shared-host Hermes agent
harness.

It provisions:

- one operator-owned Curator Hermes agent
- one isolated Hermes user agent per enrolled Unix user on the host
- a shared qmd-backed knowledge plane over the Almanac vault
- an `almanac-mcp` control plane for enrollment, subscriptions, notifications,
  and SSOT refresh work

Recommended service user: `almanac`

Stack:

- Nextcloud with PostgreSQL for browser access, uploads, and folder management over Tailscale
- PDF ingestion that converts uploaded PDFs into generated Markdown sidecars for search
- A host filesystem watcher that notices vault changes no matter whether they came from Nextcloud or direct disk edits
- Hermes Agent + qmd for local retrieval/search
- `almanac-mcp`, Notion webhook intake, and SSOT batching as the shared control plane
- one Curator Hermes agent for the operator plus one isolated Hermes agent per enrolled user
- GitHub private repo for history/backup via `almanac-priv`
- Quarto as an optional publish layer

## Deployment Model

Almanac is shared-host in v1.

- the operator runs `deploy.sh` to stand up shared services and the Curator
- the Curator runs under the operator service user and always has a local TUI
  recovery path
- each enrolled user gets their own Unix account, `HERMES_HOME`, and
  user systemd instance
- user enrollment is gated by Curator approval over the Almanac control plane
- user agents retrieve knowledge through qmd MCP and `almanac-mcp`, not by
  direct access to the shared vault or Curator state

## Roles

- Operator: deploys Almanac, owns the Curator, approves or denies enrollments,
  and retains TUI godmode
- Curator: Almanac's own Hermes agent; gates onboarding, refreshes vault
  definitions, manages notifications, and fans out managed-memory updates
- User agent: one per enrolled user on the same host
- Enrolled user: SSHes to the host as their own Unix user and runs `init.sh agent`

## Component Roles

- Shared vault: the authoritative markdown tree on disk
- Nextcloud: browser access to that same shared vault over Tailscale
- Vault watcher: watches the shared vault on disk and triggers reconciliation/index refresh in the right order
- PDF ingestion: converts PDFs found in the shared vault into generated Markdown for qmd before refresh
- Hermes + qmd: read-oriented retrieval/search surface for agents and shells across authored notes and generated PDF Markdown
- Curator: operator-owned Hermes agent that gates enrollment, refreshes vault definitions, and owns token lifecycle
- `almanac-mcp`: bootstrap, enrollment, subscriptions, notification outbox, and shared SQLite state
- GitHub: backup/history for `almanac-priv`, not live collaboration
- Quarto: optional human-facing published output, not required for collaboration

## Repo Split

The intended deployment shape is a nested private repo:

```text
/home/almanac/
  almanac/                 # public repo: scripts, units, compose, templates
    almanac-priv/          # private nested repo: vault, config, private content
```

`almanac-priv` is where the private state lives:

```text
/home/almanac/almanac/almanac-priv/
  config/
    almanac.env
  vault/
  quarto/
  published/
  state/
    nextcloud/
    pdf-ingest/
    runtime/
```

The outer `almanac` repo ignores `almanac-priv/`, and the inner `almanac-priv`
repo is the thing you back up to GitHub. Runtime-heavy directories stay ignored
via its own `.gitignore`.

## Installer

The main entrypoint is the interactive deploy script:

```bash
/path/to/almanac/deploy.sh
```

It opens a small menu with modes for install/update, config-only, health, and
remove/teardown. When a deployed `almanac.env` is found, remove/teardown offers
to use it automatically so you do not have to re-enter the paths.

Install/update asks for:

- whether to use `almanac` as the service user, defaulting to `almanac`
- service user and home
- public repo path
- private repo path
- whether to initialize the public repo if it isn't already a git repo
- Tailscale/Nextcloud domain and port, with Tailscale auto-detected when available
- whether to enable the tailnet-only Tailscale HTTPS proxy for Nextcloud
- which local user should be allowed to manage Tailscale Serve after install
- whether to wipe existing Nextcloud state for a clean reinstall when prior state is detected
- Nextcloud admin username/password
- GitHub private remote for `almanac-priv`
- Git author name/email
- whether to enable Quarto
- whether to initialize `almanac-priv` as a git repo

It asks first, then uses `sudo` inline only for the steps that need root.

## Quick Start

From the repo root:

```bash
./deploy.sh
```

Useful direct modes:

```bash
./deploy.sh install
./deploy.sh curator-setup
./deploy.sh agent-payload
./deploy.sh write-config
./deploy.sh health
./deploy.sh remove
./init.sh agent
./init.sh update
./bin/almanac-ctl user prepare <unix-user>
```

## Operator Runbook

### 1. Deploy the shared host

Clone the repo onto the host, then run:

```bash
./deploy.sh install
```

That flow stands up the shared infrastructure, writes `almanac-priv`, installs
the shared systemd services, and then launches Curator onboarding.

Curator setup includes:

- Hermes setup under the operator service user
- seeded model presets for Codex, Opus, and Chutes failover
- optional Discord and Telegram gateway setup
- mandatory local TUI access
- operator notification channel setup and validation

If shared infra is already installed and you just need to repair or reconfigure
Curator, run:

```bash
./deploy.sh curator-setup
```

That flow is intended to be idempotent: it should repair Curator state without
duplicating manifests or blindly overwriting a working operator channel.

### 2. Verify health

After install or repair:

```bash
./deploy.sh health
```

This checks the shared services, Curator registration and refresh state, qmd,
vault warnings, notification delivery, and enrolled-agent service health.

### 3. Use the recovery surfaces

Curator is meant to stay operable even if chat gateways break.

- Curator TUI: `./bin/curator-tui.sh`
- Operator CLI: `./bin/almanac-ctl`
- Curator repair: `./deploy.sh curator-setup`

Typical operator commands:

```bash
./bin/almanac-ctl request list
./bin/almanac-ctl request approve <request-id>
./bin/almanac-ctl request deny <request-id>
./bin/almanac-ctl token list
./bin/almanac-ctl token revoke <agent-id-or-token-id>
./bin/almanac-ctl token reinstate <token-id>
./bin/almanac-ctl agent list
./bin/almanac-ctl agent show <agent-id>
sudo ./bin/almanac-ctl agent deenroll <agent-id>
./bin/almanac-ctl vault list
./bin/almanac-ctl vault reload-defs
./bin/almanac-ctl vault refresh <vault-name>
./bin/almanac-ctl channel reconfigure operator
```

## Enrolling a User

User onboarding is a two-part flow: operator prep first, then user enrollment.

### 1. Prepare the Unix account

Run this as root on the host:

```bash
sudo ./bin/almanac-ctl user prepare <unix-user>
```

That helper:

- creates the Unix account when needed
- enables linger
- prepares per-user Almanac directories
- starts the user's systemd context when possible

It also prints the remaining operator-managed steps outside Almanac:

- authorize the user's SSH key
- ensure Tailscale SSH or ACL policy permits host login
- confirm any tailnet identity mapping or host-access policy needed for that
  user

### 2. Give the user host access

The user must be able to SSH into the Almanac host as their own Unix account.
In v1, that is what local TUI access means.

### 3. Give the user the enrollment command

If the repo is public, the user can enroll with the curl-friendly bootstrap:

```bash
curl -fsSL https://raw.githubusercontent.com/sirouk/almanac/master/init.sh | bash -s -- agent
```

That top-level `init.sh` clones or updates the repo into
`~/.cache/almanac-init/repo` and then runs the real enrollment flow.

If the repo is private or already cloned on the host, the equivalent local
command is:

```bash
./init.sh agent
```

### 4. What the user flow does

`init.sh agent`:

1. submits an unauthenticated but tailnet-scoped `bootstrap.request`
2. waits for operator approval
3. installs Hermes if needed
4. runs explicit `hermes setup`
5. optionally runs `hermes gateway setup` for Discord or Telegram
6. registers the user agent with `almanac-mcp`
7. installs the default Almanac skills
8. registers `almanac-mcp`, qmd MCP, and Chutes KB MCP when configured
9. runs first contact, resolves default `.vault` subscriptions, and installs
   exactly one 4-hour user refresh timer

The operator can approve from:

- the dedicated operator notification channel
- Curator TUI
- `./bin/almanac-ctl request approve <request-id>`

## Public Repo Bootstrap

The curl entrypoint is the repo-root [init.sh](./init.sh). It is designed to be
safe to publish because it only bootstraps the checked-out repo and then
delegates to [bin/init.sh](./bin/init.sh).

Useful overrides for remote bootstrap:

```bash
ALMANAC_INIT_REPO_URL=https://github.com/sirouk/almanac.git
ALMANAC_MCP_URL=http://127.0.0.1:8282/mcp
ALMANAC_QMD_URL=http://127.0.0.1:8181/mcp
CHUTES_MCP_URL=https://example.invalid/mcp
```

For a typical shared-host enrollment, the defaults are correct because the user
is already logged into the Almanac host and talks to the local control plane.

After `install`, the script prints a short operator guide that tells you:

- where the authoritative vault lives on disk
- where Nextcloud is listening and, when enabled, its tailnet-only Tailscale HTTPS URL
- which Nextcloud admin user was configured and where the password is stored
- which shared vault mount appears inside Nextcloud
- how to point Hermes at qmd
- a copy-and-paste agent payload with the qmd MCP URL, same-host local skill paths, GitHub skill paths, the raw `SKILL.md` URLs, and the recurring 4-hour vault-memory reconciliation instructions
- how to enable GitHub backup pushes
- where Quarto reads from and writes to

If you just want it to write the private config and scaffold without changing
the system yet:

```bash
/path/to/almanac/deploy.sh write-config
```

## Manual Components

- [bootstrap-system.sh](./bin/bootstrap-system.sh): root/system setup
- [bootstrap-userland.sh](./bin/bootstrap-userland.sh): install Hermes, qmd, and private repo scaffolding
- [bootstrap-curator.sh](./bin/bootstrap-curator.sh): Curator bootstrap and repair flow
- [install-user-services.sh](./bin/install-user-services.sh): install systemd user units
- [install-agent-user-services.sh](./bin/install-agent-user-services.sh): install per-user agent refresh/gateway units
- [almanac-ctl](./bin/almanac-ctl): operator CLI for users, tokens, vaults, requests, and channel repair
- [init.sh](./init.sh): curl-friendly user enrollment/update entrypoint
- [user-agent-refresh.sh](./bin/user-agent-refresh.sh): 4-hour user-agent subscription, managed-memory, and notification refresh
- [curator-tui.sh](./bin/curator-tui.sh): Curator TUI recovery surface
- [health.sh](./bin/health.sh): quick status for qmd, timers, backup, and Nextcloud
- [vault-watch.sh](./bin/vault-watch.sh): host filesystem watcher for the shared vault
- [pdf-ingest.sh](./bin/pdf-ingest.sh): reconcile PDFs into generated Markdown and refresh qmd when needed

## Private Repo Workflow

The public `almanac` repo should not contain private content.

- commit infrastructure changes in the outer `almanac` repo
- commit vault content and `config/almanac.env` in the inner `almanac-priv` repo

Example:

```bash
git -C /home/almanac/almanac/almanac-priv status
git -C /home/almanac/almanac/almanac-priv add config/almanac.env vault
git -C /home/almanac/almanac/almanac-priv commit -m "Update Almanac state"
```

## After Install

1. Run `./deploy.sh health` to confirm qmd, timers, and Nextcloud state.
2. Treat `/home/almanac/almanac/almanac-priv/vault` as the source-of-truth vault path on disk.
3. Use Nextcloud with the admin account stored in `almanac-priv/config/almanac.env`; the shared vault appears there as `/Vault`.
4. Drop markdown or PDFs into the shared vault and let the host watcher reconcile and refresh qmd automatically.
5. Point Hermes at `http://127.0.0.1:8181/mcp` using [hermes-qmd-config.yaml](./docs/hermes-qmd-config.yaml).
6. Set `BACKUP_GIT_REMOTE` in `almanac-priv/config/almanac.env` if you want backup pushes to GitHub.
7. Enroll users with `sudo ./bin/almanac-ctl user prepare <unix-user>` and then hand them the `curl ... init.sh | bash -s -- agent` command once the repo is public.
8. Use Quarto only if you want a published human-facing site.

## Client Setup

### Nextcloud

- use it as the browser surface for the shared vault
- the installer configures Nextcloud against PostgreSQL and writes the initial admin credentials into `almanac-priv/config/almanac.env`
- Almanac disables the stock Nextcloud skeleton/demo files so fresh user homes start empty
- Almanac exposes the same host vault path that qmd indexes as a global Nextcloud mount at `/Vault`
- uploads in the browser land on the same host-mounted vault path that exists on disk outside the container
- PDF uploads into that shared vault are reconciled by the host watcher plus the periodic ingest timer and converted into generated Markdown for retrieval
- by default the app listens on the configured local port
- if enabled during install, Almanac configures `tailscale serve` so the app stays bound to `127.0.0.1` while HTTPS access is available to tailnet devices only
- public internet exposure does not happen unless you separately turn on Tailscale Funnel or place another internet-facing proxy in front of it

### Hermes + qmd

- qmd serves retrieval locally over MCP HTTP
- qmd keeps the authored vault collection and a second generated-PDF collection in the same index
- `almanac-vault-watch.service` watches the shared vault on disk and runs PDF reconciliation before qmd update
- `almanac-qmd-update.timer` remains enabled as a periodic backstop and embedding pass
- Hermes should point at `http://127.0.0.1:8181/mcp`
- the included snippet in [hermes-qmd-config.yaml](./docs/hermes-qmd-config.yaml) is the starting point
- when Tailscale Serve is enabled, deploy also prints the tailnet MCP URL for remote agents
- the matching skill lives at `skills/almanac-qmd-mcp/SKILL.md`
- the recurring memory-maintenance skill lives at `skills/almanac-vault-reconciler/SKILL.md`
- user enrollment also installs `almanac-first-contact`, `almanac-vaults`, and `almanac-ssot`
- first contact registers `almanac-mcp`, qmd MCP, and Chutes KB MCP when configured, then resolves default `.vault` subscriptions
- if `sirouk/almanac` is public, remote host users can bootstrap with the raw `init.sh` URL
- if `sirouk/almanac` is still private, users should enroll from a local clone on the host

## Vault Semantics

- vault definitions live in YAML `.vault` files at vault roots
- discovery is recursive under the shared vault tree
- nested vault roots are invalid in v1 and show up as health warnings
- all approved users may retrieve from any vault through qmd
- subscriptions only control managed memory and Curator push behavior
- malformed or missing `.vault` files fail safe as non-default vaults and warn in health output

## Updates and Lifecycle

- shared-host repair or upgrade: `./deploy.sh install`
- Curator-only repair: `./deploy.sh curator-setup`
- user-agent update from the user's account: `./init.sh update`
- token revocation: `./bin/almanac-ctl token revoke <target>`
- de-enroll a user agent: `sudo ./bin/almanac-ctl agent deenroll <agent-id>`

De-enrollment revokes the token, stops and disables the per-user services, and
archives the agent state under:

```text
almanac-priv/state/archived-agents/<agent_id>/<timestamp>/
```

Re-enrollment requires fresh operator approval and a fresh token.

### GitHub

- the outer `almanac` repo holds infrastructure only
- the inner `almanac-priv` repo holds vault content and `config/almanac.env`
- backup/history belongs in `almanac-priv`

### Quarto

- optional
- use it when you want a published site or rendered output for people
- it is not part of the collaboration path for editing the vault

## Suggested Access Pattern

- keep the authoritative vault on the server
- expose Nextcloud on Tailscale for browser access to that same vault
- let the host watcher notice changes from either Nextcloud or direct disk edits and keep qmd fresh
- let Almanac reconcile PDFs from that vault into generated Markdown for qmd before refresh
- point Hermes to qmd over local MCP HTTP
- back up `almanac-priv` to a private GitHub repo
