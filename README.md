# Almanac

`Almanac` is the public infrastructure repo for a shared-host Hermes agent
harness built around a set of Vaults: durable knowledge spaces for operators
and agents to train against, retrieve from, and keep in sync.

The tone of the project is intentional:

- the Vaults should feel like a training deck, not a random file dump
- Curator should feel like a steady guide: knowledgeable, clueful, and mostly
  on mission
- human-facing copy should nod at that world lightly without slipping into
  full roleplay
- operational instructions should stay concrete even when the framing has a
  little style

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
- Curator: Almanac's own Hermes agent; the operator-owned guide who gates
  onboarding, refreshes vault definitions, manages notifications, and fans out
  managed-memory updates
- User agent: one per enrolled user on the same host
- Enrolled user: starts with the public bootstrap handshake; Almanac provisions
  the host-side Unix user and agent after approval

## Component Roles

- Shared vault: the authoritative markdown tree on disk
- Vaults: the named training rooms inside that shared memory surface, each with
  its own purpose and subscription behavior
- Nextcloud: browser access to that same shared vault over Tailscale
- Vault watcher: watches the shared vault on disk and triggers reconciliation/index refresh in the right order
- PDF ingestion: converts PDFs found in the shared vault into generated Markdown for qmd before refresh
- Hermes + qmd: read-oriented retrieval/search surface for agents and shells across authored notes and generated PDF Markdown
- Curator: operator-owned Hermes agent that keeps people on the rails, handles
  enrollment, refreshes vault definitions, and owns token lifecycle
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

It opens a small menu with modes for:

- install or repair from the checkout you are currently running
- upgrade from the configured upstream repo and branch
- config-only writes
- Curator repair
- health
- remove/teardown

When a deployed `almanac.env` is found, remove/teardown offers to use it
automatically so you do not have to re-enter the paths.

Install or repair from the current checkout asks for:

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
./deploy.sh upgrade
./deploy.sh curator-setup
./deploy.sh agent-payload
./deploy.sh write-config
./deploy.sh health
./deploy.sh remove
./bin/almanac-ctl upgrade check
./init.sh agent
./init.sh update
sudo ./bin/almanac-ctl user prepare <unix-user>   # optional manual repair path
./bin/almanac-ctl provision list
```

## Operator Runbook

### 1. Deploy the shared host

Clone the repo onto the host, then run:

```bash
./deploy.sh install
```

That flow stands up the shared infrastructure, writes `almanac-priv`, installs
the shared systemd services, records the deployed release state, and then
launches Curator onboarding.

When you run deploy or health commands from a separate operator checkout, that
checkout also writes a local maintenance pointer at `.almanac-operator.env`.
It is not part of the live deploy and is ignored by git. It simply remembers
which deployed `almanac.env` that checkout should manage on later `health`,
`upgrade`, and `almanac-ctl` runs.

Run those operator-facing commands from the operator's own Unix account and
checkout, not by logging in as the service user. The wrappers are written to
use `sudo` inline and switch to the deployed service user when a step needs
root or service-user context. In practice, `deploy.sh`, `deploy.sh health`,
`deploy.sh curator-setup`, and `./bin/almanac-ctl ...` should normally be run
from the operator-maintained checkout, while direct login as the service user
is reserved for focused debugging or recovery.

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

When you enable Discord or Telegram for Curator, treat the user-facing gateway
as a separate surface from operator notifications:

- The operator notification channel only handles outbound operator notices. A
  Discord webhook or Telegram operator chat ID does not make Curator reachable
  to users.
- Discord user DMs require Curator's real Discord bot app, invited with the
  `bot` and `applications.commands` scopes. In the server where users discover
  Curator, grant at least View Channels, Send Messages, and Read Message
  History. Users can DM Curator once the bot shares a server with them. For a
  DM-first onboarding flow, keep Direct Messages enabled for server members and
  do not rely on a webhook-only install. If Curator needs to read ordinary
  guild messages beyond DMs, mentions, or interactions, enable Message Content
  intent in the Developer Portal.
- Telegram user DMs require Curator's BotFather bot token and public username.
  Each user must open a DM and press Start before Curator can reply. Telegram
  privacy mode only affects groups, so leave it on unless you explicitly want
  Curator to read ordinary group traffic.

### 2. Verify health

After install or repair:

```bash
./deploy.sh health
```

This checks the shared services, Curator registration and refresh state, qmd,
vault warnings, notification delivery, the root auto-provision timer, and
enrolled-agent service health.

### 2a. Upgrade the deployed host from upstream

When you want to roll the shared host forward from the tracked upstream repo and
branch in `almanac.env`, run:

```bash
./deploy.sh upgrade
```

That path does not use the local dev checkout as the live source of truth. It
fetches the configured upstream, syncs the deployed public repo, refreshes the
shared services, repairs Curator noninteractively, records the new release
state, and finishes with a strict health check.

The manual check command is:

```bash
./bin/almanac-ctl upgrade check
```

Curator also runs that check hourly from `almanac-curator-refresh.timer` and
nudges the operator when a new upstream commit appears. It also queues a user
agent nudge so enrolled agents can mention the pending shared-host update to
their users. The Curator maintenance skill for that flow is
`almanac-upgrade-orchestrator`.

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
./bin/almanac-ctl onboarding list
./bin/almanac-ctl onboarding show <session-id>
./bin/almanac-ctl onboarding approve <session-id>
./bin/almanac-ctl onboarding deny <session-id>
./bin/almanac-ctl provision list
./bin/almanac-ctl provision cancel <request-id>
./bin/almanac-ctl provision retry <request-id>
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

The operator control surface is the configured primary operator channel:

- Telegram: the operator chat handles notifications plus `/approve` / `/deny`
- Discord: the operator channel handles notifications plus `/approve` / `/deny`
- TUI / CLI remain the recovery path if chat access is unavailable

## Enrolling a User

User onboarding now starts with the public handshake, not with precreating a
Unix account.

If Curator onboarding is enabled on Telegram or Discord, a user can instead DM
Curator with `/start`, answer the step-by-step intake questions, wait for
operator approval, and then hand Curator the token for their own bot on that
same platform. Almanac will provision the Unix user on the host, wire that bot
into the user agent, and hand the conversation off to the user's own bot
instead of keeping Curator in the middle.

For Discord handoff, the user should also install the app from the Discord
Developer Portal Installation page or add it to a shared server so the final DM
path is reachable.

### 1. Give the user the enrollment command

If the repo is public, the user can enroll with the curl-friendly bootstrap:

```bash
curl -fsSL https://raw.githubusercontent.com/sirouk/almanac/main/init.sh \
  | ALMANAC_TARGET_HOST=almanac.your-tailnet.ts.net bash -s -- agent
```

Or, without relying on environment-variable placement in a pipe:

```bash
curl -fsSL https://raw.githubusercontent.com/sirouk/almanac/main/init.sh \
  | bash -s -- agent --target-host almanac.your-tailnet.ts.net
```

When run from a non-Linux client such as a Mac, that bootstrap now:

- requires the target Almanac hostname, either through `ALMANAC_TARGET_HOST`
  on the `bash` side of the pipe or via `--target-host`
- asks for the Unix username Almanac should provision on the host, defaulting
  to the current local username
- calls the public tailnet-scoped control-plane endpoint directly
  (`https://<host>/almanac-mcp`)
- submits `bootstrap.handshake` immediately without SSHing to the host first
- exits after printing the request id the operator should approve

That keeps the shared-host model intact: the actual Hermes install still
happens on the Almanac machine under the user's Unix account, but the approval
handshake no longer requires that account to exist ahead of time.

Approval creates the Unix account, enables linger, and kicks off host-side
agent provisioning automatically. SSH or Tailscale SSH is only needed later if
the user wants local TUI access on the host.

Do not write the command as `ALMANAC_TARGET_HOST=... curl ... | bash ...`.
That sets the variable for `curl`, not for `bash`, so the bootstrap process
will not see the target host.

If the repo is private or already cloned on the host, the equivalent local
command is:

```bash
./init.sh agent
```

### 2. Approve the request

The operator can approve from:

- the dedicated operator notification channel
- Curator TUI
- `./bin/almanac-ctl request approve <request-id>`

After approval, Almanac automatically:

1. creates the requested Unix user when needed
2. enables linger and starts the user's systemd context
3. runs the host-side `bin/init.sh agent` flow noninteractively as that user
4. registers the user agent, installs the refresh timer, and runs first
   contact on the host
5. provisions a safe default `tui-only` channel set; Discord or Telegram can
   still be configured later from Hermes once the user has host access

`sudo ./bin/almanac-ctl user prepare <unix-user>` still exists as a manual
repair path, but it is no longer the normal onboarding prerequisite.

### 3. What the user flow does

Remote public bootstrap:

1. calls the unauthenticated, tailnet-scoped `bootstrap.handshake`
2. receives a pending enrollment request id immediately
3. if the same user reruns enrollment from the same source while approval is
   still pending, reuses the existing pending request instead of minting a
   second token
4. stops there and waits for Curator/operator approval to provision the host
   user and agent automatically

Operator tools for that queue:

- `./bin/almanac-ctl provision list`
- `./bin/almanac-ctl provision cancel <request-id>`
- `./bin/almanac-ctl provision retry <request-id>`

Host-side `init.sh agent` when already running on the Almanac machine:

1. calls the unauthenticated, tailnet-scoped `bootstrap.handshake`
2. receives a pending bootstrap key immediately
3. if the same user reruns enrollment from the same source while approval is
   still pending, reuses the existing pending handshake instead of minting a
   second token
4. installs Hermes if needed
5. runs explicit `hermes setup`
6. optionally runs `hermes gateway setup` for Discord or Telegram
7. installs the default Almanac skills plus `almanac-mcp`, qmd MCP, and Chutes KB MCP when configured
8. installs exactly one 4-hour user refresh timer and the optional user gateway service
9. persists the pending key locally and tries activation once right away
10. waits asynchronously for operator approval; after approval, Almanac writes a
    per-agent activation trigger that wakes the user's local systemd path unit
    immediately, auto-registers the user agent, runs first contact, resolves
    default `.vault` subscriptions, and keeps bidirectional Almanac
    notifications flowing without waiting for the next 4-hour timer tick

## Public Repo Bootstrap

The curl entrypoint is the repo-root [init.sh](./init.sh). It is designed to be
safe to publish because it only bootstraps the checked-out repo and then
either submits the remote public handshake or, when already on the host,
delegates to [bin/init.sh](./bin/init.sh).

On non-Linux clients it uses the supplied target host, or prompts for one when
a TTY is available; otherwise it exits with a copy-paste usage hint. For remote
client enrollment it does not SSH to the host first. On the host itself it just
runs the local enrollment flow.

Useful overrides for remote bootstrap:

```bash
ALMANAC_INIT_REPO_URL=https://github.com/sirouk/almanac.git
ALMANAC_INIT_RAW_URL=https://raw.githubusercontent.com/sirouk/almanac/main/init.sh
ALMANAC_TARGET_HOST=almanac.your-tailnet.ts.net
ALMANAC_TARGET_USER=ian
ALMANAC_PUBLIC_MCP_URL=https://almanac.your-tailnet.ts.net/almanac-mcp
ALMANAC_PUBLIC_MCP_PATH=/almanac-mcp
ALMANAC_BOOTSTRAP_URL=https://almanac.your-tailnet.ts.net/almanac-mcp
ALMANAC_MCP_URL=http://127.0.0.1:8282/mcp
ALMANAC_QMD_URL=http://127.0.0.1:8181/mcp
CHUTES_MCP_URL=https://example.invalid/mcp
```

For a typical shared-host enrollment from a user laptop, the important inputs
are the target hostname, the requested Unix username, and the published
tailnet control-plane URL when you want to override the default
`/almanac-mcp` path.

The remote bootstrap entrypoint also accepts:

```bash
--target-host <hostname>
--target-user <unix-user>
--public-mcp-url <https-url>
--public-mcp-path </almanac-mcp>
```

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
- [bootstrap-userland.sh](./bin/bootstrap-userland.sh): install Hermes, qmd, and private repo scaffolding. The shared Hermes source and venv live under `ALMANAC_PRIV_DIR/state/runtime/` as `hermes-agent-src/` and `hermes-venv/`; managed services are expected to use that runtime rather than any unrelated install under `$HOME`.
- [bootstrap-curator.sh](./bin/bootstrap-curator.sh): Curator bootstrap and repair flow
- [install-system-services.sh](./bin/install-system-services.sh): install root-owned systemd units such as the enrollment provisioner timer
- [install-user-services.sh](./bin/install-user-services.sh): install systemd user units
- [install-agent-user-services.sh](./bin/install-agent-user-services.sh): install per-user agent refresh/gateway units
- [almanac-ctl](./bin/almanac-ctl): operator CLI for users, tokens, auto-provision requests, vaults, and channel repair
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
7. Enroll users by handing them the public `curl ... init.sh | bash -s -- agent` bootstrap once the repo is public; Almanac creates the host-side Unix user after approval.
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
- `almanac-mcp` serves the shared control plane locally on `http://127.0.0.1:8282/mcp`
- when Tailscale Serve is enabled, Almanac also publishes the control plane on `https://<tailnet-host>/almanac-mcp` for bootstrap handshakes
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
- vault changes queue Curator fanout so managed-memory stubs stay fresh across enrolled agents while qmd remains the deep-retrieval source of truth
- malformed or missing `.vault` files fail safe as non-default vaults and warn in health output

## Updates and Lifecycle

- shared-host repair from the current checkout: `./deploy.sh install`
- shared-host upgrade from configured upstream: `./deploy.sh upgrade`
- manual upstream check: `./bin/almanac-ctl upgrade check`
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
