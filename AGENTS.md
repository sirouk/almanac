# Almanac Agent Operating Guide

This file is the first-read map for coding agents working in this repository.
It exists so future agents notice the operational handles before improvising.

Almanac is not just a library checkout. It is the public half of a live
shared-host system for Hermes agents, with a private nested state repo,
systemd services, per-user Unix accounts, chat gateways, qmd retrieval, Notion
SSOT rails, and deploy keys.

## Prime Directives

- Read this file before changing deploy, onboarding, service, or runtime code.
- Prefer the canonical scripts in this repo over manual host surgery.
- Do not modify core Hermes just to make Almanac behavior work. Use Almanac
  wrappers, plugins, hooks, generated config, and service units.
- Do not print, log, commit, or quote secrets. Tokens, API keys, OAuth
  credentials, deploy keys, and `.env` values belong in private state only.
- Assume the working tree may contain user edits. Never revert changes you did
  not make unless the operator explicitly asks.
- Use `rg`/`rg --files` for discovery.
- Use `apply_patch` for manual file edits.
- Keep code changes scoped to the behavioral surface requested.
- For host upgrades, use `./deploy.sh upgrade`. Do not manually rsync into the
  deployed tree unless debugging the deploy script itself.

## Canonical Host Layout

Default deployed layout:

```text
/home/almanac/
  almanac/                         public repo: scripts, units, templates
    almanac-priv/                  private nested repo/state; ignored by public git
      config/almanac.env           live config
      vault/                       shared vault
      published/                   rendered/published output
      quarto/                      Quarto source/project state
      state/
        almanac-control.sqlite3    control-plane DB
        almanac-release.json       deployed release state
        agents/                    enrolled agent state
        archived-agents/           enrollment-reset archives
        curator/hermes-home/       Curator HERMES_HOME
        nextcloud/                 Nextcloud container state
        notion-index/markdown/     indexed shared Notion markdown
        pdf-ingest/markdown/       generated PDF sidecar markdown
        runtime/hermes-venv/       shared Hermes runtime
```

Per enrolled user:

```text
/home/<user>/
  .local/share/almanac-agent/hermes-home/   private user-agent HERMES_HOME
  .config/systemd/user/                     user-level Almanac units
  Almanac -> <shared vault>                 convenience symlink
```

Do not guess `~/.hermes` for enrolled agents. Almanac agents normally use:

```text
/home/<user>/.local/share/almanac-agent/hermes-home
```

The operator checkout may include `.almanac-operator.env`, which points at the
deployed user, public repo, private repo, and live config. It is a discovery
hint, not a file to publish or stuff with secrets.

## Canonical Commands

From the repo root:

```bash
./deploy.sh                         # interactive menu
./deploy.sh install                 # install/repair from this checkout
./deploy.sh upgrade                 # upgrade deployed host from configured upstream
./deploy.sh health                  # full host health check
./deploy.sh curator-setup           # repair Curator only
./deploy.sh notion-ssot             # configure shared Notion SSOT
./deploy.sh enrollment-status
./deploy.sh enrollment-trace --unix-user <user>
./deploy.sh enrollment-align
./deploy.sh enrollment-reset
./deploy.sh rotate-nextcloud-secrets
./bin/almanac-ctl upgrade check
```

`deploy.sh` is a thin wrapper around `bin/deploy.sh`.

Use `./deploy.sh upgrade` when the user asks to upgrade the live system. It:

1. Reads the deployed config.
2. Fetches `ALMANAC_UPSTREAM_REPO_URL#ALMANAC_UPSTREAM_BRANCH`.
3. Uses the configured Almanac upstream deploy key when enabled.
4. Syncs the public deployed repo.
5. Preserves and seeds `almanac-priv`.
6. Runs system bootstrap and userland bootstrap.
7. Repairs Curator.
8. Realigns active enrolled agents.
9. Restarts shared services.
10. Records `state/almanac-release.json`.
11. Runs strict health.
12. Runs `bin/live-agent-tool-smoke.sh` when present.

If you just committed local changes and need them included in an upgrade,
make sure they are pushed to the configured upstream first. `upgrade` consumes
the remote, not unpushed local commits.

## Deploy Keys

Almanac has multiple deploy-key lanes. Do not conflate them.

- Almanac upstream deploy key: read/write key for the public `almanac` repo.
  Used by `./deploy.sh upgrade` and operator/agent code pushes when enabled.
- `almanac-priv` backup deploy key: read/write key for the private state
  backup repo.
- Per-user agent backup deploy key: read/write key for a user's private
  Hermes-home backup repo.

Relevant config:

```text
ALMANAC_UPSTREAM_REPO_URL
ALMANAC_UPSTREAM_BRANCH
ALMANAC_UPSTREAM_DEPLOY_KEY_ENABLED
ALMANAC_UPSTREAM_DEPLOY_KEY_USER
ALMANAC_UPSTREAM_DEPLOY_KEY_PATH
ALMANAC_UPSTREAM_KNOWN_HOSTS_FILE
```

`bin/deploy.sh` can generate the upstream key, print the public key, configure
the repo `core.sshCommand`, verify `git ls-remote`, and verify write access
with a dry-run push. In GitHub deploy key settings, upstream code keys need
`Allow write access`.

The operational question is usually not "does a deploy key exist?" but:

- Is upstream deploy-key support enabled in live config?
- Is the remote SSH URL correct?
- Does the key owner exist on this host?
- Has the public key been added to GitHub with write access?
- Has the commit to deploy been pushed to `ALMANAC_UPSTREAM_REPO_URL`?

## Services

System units installed under `/etc/systemd/system`:

```text
almanac-enrollment-provision.service
almanac-enrollment-provision.timer
almanac-notion-claim-poll.service
almanac-notion-claim-poll.timer
```

Main service-user units installed for the Almanac service user:

```text
almanac-mcp.service
almanac-notion-webhook.service
almanac-ssot-batcher.timer
almanac-notification-delivery.timer
almanac-curator-refresh.timer
almanac-qmd-mcp.service
almanac-qmd-update.timer
almanac-vault-watch.service
almanac-github-backup.timer
almanac-hermes-docs-sync.timer
almanac-pdf-ingest.timer
almanac-quarto-render.timer
almanac-nextcloud.service
almanac-curator-onboarding.service
almanac-curator-discord-onboarding.service
almanac-curator-gateway.service
```

Whether Curator uses onboarding services or `almanac-curator-gateway.service`
depends on:

```text
ALMANAC_CURATOR_CHANNELS
ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED
ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED
```

Per enrolled user:

```text
almanac-user-agent-refresh.service
almanac-user-agent-refresh.timer
almanac-user-agent-activate.path
almanac-user-agent-gateway.service
almanac-user-agent-dashboard.service
almanac-user-agent-dashboard-proxy.service
almanac-user-agent-code.service
almanac-user-agent-backup.service
almanac-user-agent-backup.timer
```

When checking a user service, use that user's systemd bus:

```bash
uid="$(id -u <user>)"
sudo runuser -u <user> -- env \
  XDG_RUNTIME_DIR="/run/user/$uid" \
  DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" \
  systemctl --user status almanac-user-agent-gateway.service --no-pager
```

The gateway service name is `almanac-user-agent-gateway.service`, not
`almanac-agent-gateway.service`.

## Verification Playbooks

After any deploy or service repair:

```bash
./deploy.sh health
systemctl --failed --no-legend --plain
```

Check service-user failed units:

```bash
uid="$(id -u almanac)"
sudo runuser -u almanac -- env \
  XDG_RUNTIME_DIR="/run/user/$uid" \
  DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" \
  systemctl --user --failed --no-legend --plain
```

Check enrolled users similarly. Discover users with:

```bash
./bin/almanac-ctl agent list
```

Check deployed commit:

```bash
sudo runuser -u almanac -- env HOME=/home/almanac \
  git -C /home/almanac/almanac rev-parse --short HEAD
```

Check release state:

```bash
sudo runuser -u almanac -- env HOME=/home/almanac \
  python3 -m json.tool /home/almanac/almanac/almanac-priv/state/almanac-release.json
```

Check agent gateway defaults for a user:

```bash
hh="/home/<user>/.local/share/almanac-agent/hermes-home"
sudo test -f "$hh/hooks/almanac-telegram-start/handler.py"
sudo test -f "$hh/plugins/almanac-managed-context/plugin.yaml"
sudo grep -E '^(TELEGRAM_REACTIONS|DISCORD_REACTIONS)=true$' "$hh/.env"
```

Old Podman healthcheck transient units may appear as failed user units for
the service user after container lifecycle changes. If current containers are
healthy and the failed units are stale `/usr/bin/podman healthcheck run ...`
transients, clear them with:

```bash
uid="$(id -u almanac)"
sudo runuser -u almanac -- env \
  XDG_RUNTIME_DIR="/run/user/$uid" \
  DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" \
  systemctl --user reset-failed
```

Then recheck failed units. Do not ignore active service failures.

## Onboarding Model

Users normally begin in a Discord or Telegram DM with Curator. The flow:

1. Curator asks for agent purpose, Unix username, bot name, provider, model,
   and reasoning level.
2. Operator approves the session.
3. Almanac creates the Unix user, enables linger, provisions the Hermes home,
   and installs per-user services.
4. Curator asks the user for a bot token for the new user-agent bot, not
   Curator's bot.
5. Almanac writes gateway config and starts the user gateway.
6. Optional Notion identity, backup, and remote SSH setup continue after that.

Provider lanes currently include:

- Org-provided via `ALMANAC_ORG_PROVIDER_ENABLED=1`,
  `ALMANAC_ORG_PROVIDER_PRESET`, `ALMANAC_ORG_PROVIDER_MODEL_ID`, and
  `ALMANAC_ORG_PROVIDER_SECRET`. When present, it is the first onboarding
  option and auto-stages the org credential after the user's bot token.
- Chutes via OpenAI-compatible endpoint `https://llm.chutes.ai/v1`.
- Claude Opus via Claude Code OAuth, not Anthropic API keys.
- OpenAI Codex via Codex sign-in/device flow.

Discord user-agent onboarding should stay simple and explicit:

```text
Install Link
Discord setup steps:
Go to https://discord.com/developers/applications and click New Application.
Name the app [agent name] or any bot name you prefer.
Open the app's Bot page.
Turn Message Content Intent on.
Open the app's Installation page.
Copy Install Link by clicking the copy button.
Paste the link into a new tab and visit the link.
Choose Add to My Apps so the bot can DM you.
Optionally visit the link again to Add to Server.
Return to the Bot page, click Reset Token, copy the bot token, and paste that token here.
```

Telegram user-agent onboarding uses BotFather and the token printed for the
new agent bot. Curator must reject Curator's own token.

## Agent Gateway Defaults

New and refreshed agents should get these defaults from the outset:

- Telegram `/start` support through Almanac's Hermes hook, not core Hermes.
- `almanac-managed-context` plugin installed and enabled.
- `TELEGRAM_REACTIONS=true`.
- `DISCORD_REACTIONS=true`.
- Gateway run with Hermes `gateway run --replace`.
- Home-channel env repaired from enrollment state when available.

The Telegram `/start` behavior lives here:

```text
hooks/hermes-agent/almanac-telegram-start/HOOK.yaml
hooks/hermes-agent/almanac-telegram-start/handler.py
bin/install-almanac-plugins.sh
```

The managed context plugin lives here:

```text
plugins/hermes-agent/almanac-managed-context/
```

Per-user installation and refresh paths:

```text
bin/install-agent-user-services.sh
bin/refresh-agent-install.sh
python/almanac_enrollment_provisioner.py
```

Regression coverage to update when touching this area:

```text
tests/test_almanac_agent_user_services.py
tests/test_almanac_plugins.py
tests/test_almanac_enrollment_provisioner_regressions.py
tests/test_almanac_onboarding_prompts.py
tests/test_deploy_regressions.py
```

## Knowledge And MCP Rails

Almanac gives agents higher-level MCP tools so they do not rummage through
raw files or raw Notion APIs first.

Prefer:

```text
knowledge.search-and-fetch
vault.search-and-fetch
vault.fetch
notion.search-and-fetch
notion.fetch
ssot.read
ssot.write
ssot.status
```

qmd collections:

```text
vault             authored vault markdown/text
vault-pdf-ingest  generated PDF markdown sidecars
notion-shared     indexed shared Notion pages
```

qmd indexes text-like files directly:

```text
*.md, *.markdown, *.mdx, *.txt, *.text
```

PDF files are converted into generated markdown under
`state/pdf-ingest/markdown`, then indexed via the `vault-pdf-ingest`
collection.

Shared Notion writes must go through the SSOT broker. Destructive operations
such as archive/delete/trash are intentionally rejected or require approval
rails; do not bypass this with raw Notion access.

## Config And Runtime

Important defaults and paths are defined in `bin/common.sh`.

Core config:

```text
ALMANAC_CONFIG_FILE
ALMANAC_USER
ALMANAC_REPO_DIR
ALMANAC_PRIV_DIR
VAULT_DIR
STATE_DIR
RUNTIME_DIR
ALMANAC_DB_PATH
ALMANAC_RELEASE_STATE_FILE
ALMANAC_CURATOR_HERMES_HOME
```

Ports:

```text
QMD_MCP_PORT                    default 8181
ALMANAC_MCP_HOST                default 127.0.0.1
ALMANAC_MCP_PORT                default 8282
ALMANAC_NOTION_WEBHOOK_HOST     default 127.0.0.1
ALMANAC_NOTION_WEBHOOK_PORT     default 8283
NEXTCLOUD_PORT                  default 18080
```

Runtime pin:

```text
ALMANAC_HERMES_AGENT_REF
ALMANAC_HERMES_DOCS_REF
```

Hermes docs sync is pinned to the runtime ref by default so agent-facing docs
do not drift ahead of the installed runtime.

## Tests And Checks

Useful focused tests:

```bash
python3 tests/test_almanac_agent_user_services.py
python3 tests/test_almanac_plugins.py
python3 tests/test_almanac_enrollment_provisioner_regressions.py
python3 tests/test_almanac_onboarding_prompts.py
python3 tests/test_deploy_regressions.py
python3 tests/test_health_regressions.py
```

Preflight:

```bash
./bin/ci-preflight.sh
```

Full smoke:

```bash
./test.sh
```

`./test.sh` runs preflight and then a sudo install smoke. It is heavier than
focused unit/regression tests.

When changing shell scripts, run at least:

```bash
bash -n deploy.sh bin/*.sh test.sh
```

When changing Python modules, run the nearest tests and a compile check for
the touched modules.

## Editing Hotspots

Deploy and host lifecycle:

```text
deploy.sh
bin/deploy.sh
bin/bootstrap-system.sh
bin/bootstrap-userland.sh
bin/bootstrap-curator.sh
bin/install-system-services.sh
bin/install-user-services.sh
bin/health.sh
```

Enrollment and onboarding:

```text
python/almanac_onboarding_flow.py
python/almanac_curator_onboarding.py
python/almanac_curator_discord_onboarding.py
python/almanac_enrollment_provisioner.py
bin/almanac-enrollment-provision.sh
```

Agent install/repair:

```text
bin/install-agent-user-services.sh
bin/refresh-agent-install.sh
bin/user-agent-refresh.sh
bin/activate-agent.sh
```

Control plane and MCP:

```text
python/almanac_control.py
python/almanac_ctl.py
python/almanac_mcp_server.py
bin/almanac-ctl
bin/almanac-mcp-server.sh
```

Knowledge, vault, qmd, PDFs, docs:

```text
bin/vault-watch.sh
bin/qmd-refresh.sh
bin/qmd-daemon.sh
bin/pdf-ingest.sh
bin/pdf-ingest.py
bin/sync-hermes-docs-into-vault.sh
bin/vault-repo-sync.sh
```

Notion:

```text
python/almanac_notion_ssot.py
python/almanac_notion_webhook.py
python/almanac_ssot_batcher.py
bin/almanac-notion-webhook.sh
bin/almanac-ssot-batcher.sh
```

Notifications:

```text
python/almanac_notification_delivery.py
bin/almanac-notification-delivery.sh
```

## Safety Notes

- The public repo ignores `almanac-priv/`. Do not add private state to public
  commits.
- Do not read private user `HERMES_HOME` secret files unless the operator asks
  for a specific recovery/debug action.
- Do not pass tokens in Almanac MCP tool calls. The Almanac plugin injects the
  bootstrap token where appropriate.
- Do not store Discord bot tokens, Telegram bot tokens, Chutes keys, Notion
  tokens, OAuth credentials, or sudo credentials in docs.
- Use `./deploy.sh enrollment-reset` for deliberate cleanup. Avoid ad hoc
  deleting users, state rows, or home directories.
- Repo sync inside the vault is intentionally destructive for real `.git`
  checkouts: it fetches, resets hard to `origin/<current-branch>`, and cleans
  untracked non-ignored files.
- Almanac services are loopback/tailnet-first. Do not open public listeners
  unless the specific Tailscale Serve/Funnel path is intended.

## When Something Fails

Start with:

```bash
./deploy.sh health
systemctl --failed --no-legend --plain
./deploy.sh enrollment-status
```

For a stuck onboarding/provisioning session:

```bash
./deploy.sh enrollment-trace --unix-user <user>
./deploy.sh enrollment-trace --session-id <session-id>
./deploy.sh enrollment-trace --request-id <request-id>
./bin/almanac-ctl provision list
./bin/almanac-ctl provision retry <request-id>
```

For Curator:

```bash
./bin/curator-tui.sh
./deploy.sh curator-setup
```

For upgrade drift:

```bash
./bin/almanac-ctl upgrade check
./deploy.sh upgrade
```

For a user gateway:

```bash
uid="$(id -u <user>)"
sudo runuser -u <user> -- env \
  XDG_RUNTIME_DIR="/run/user/$uid" \
  DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" \
  systemctl --user status almanac-user-agent-gateway.service -n 80 --no-pager
```

Then inspect the user's actual Hermes home:

```text
/home/<user>/.local/share/almanac-agent/hermes-home
```

## Documentation To Keep In Sync

When behavior changes, update the closest docs/tests:

- `README.md` for operator-facing product and architecture docs.
- `AGENTS.md` for coding-agent operational handles.
- `docs/curator-onboarding-transcript-notes.md` for transcript-derived
  onboarding observations.
- Focused regression tests under `tests/`.

If `AGENTS.md` and code disagree, trust the code, fix the doc, and add or
adjust a test if the behavior is important.
