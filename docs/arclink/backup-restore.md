# ArcLink Backup and Restore

## What to Back Up

| Data | Location | Method |
|------|----------|--------|
| Control database | `ARCLINK_DB_PATH` (SQLite) | File copy or `sqlite3 .backup` |
| Control / `arclink-priv` tree (vault, state, config, published, quarto) | `ARCLINK_PRIV_DIR` (default `$ARCLINK_REPO_DIR/arclink-priv`) | `bin/backup-to-github.sh` (private git remote) |
| Per-deployment state roots | `ARCLINK_STATE_ROOT_BASE` (default `/arcdata/deployments/{deployment_id}`, with `config/`, `vault/`, `state/`, `state/nextcloud/`, `published/`) | File copy or rsync |
| Per-deployment Nextcloud data | `state/nextcloud/` under the deployment root | Docker volume / directory export |
| Per-deployment Postgres data | Named Compose volume `arclink-{deployment_id}_postgres_data` | `pg_dump` or volume export |
| Per-agent Hermes home (SOUL, config, memories, skills, plugins, sessions, curated state) | Enrolled Hermes home | `bin/backup-agent-home.sh` (per-user private git remote, secret-excluding) |

The `arclink-priv` tree and the per-agent Hermes home each have a dedicated,
secret-excluding backup script — see [Backup Scripts](#backup-scripts) below.
The state-root layout above is the same one validated by the executor; see
[`data-safety.md`](data-safety.md) for the authoritative volume layout and
GAP-019 trust-boundary inventory.

## Backup Schedule

| Frequency | Target |
|-----------|--------|
| Continuous | Vault via git auto-commit (existing ArcLink behavior) |
| Daily | SQLite control database snapshot |
| Daily | Per-deployment Postgres dumps |
| Weekly | Full state root rsync |

Of these, the `arclink-priv` git backup
([`bin/backup-to-github.sh`](#control--arclink-priv--binbackup-to-githubsh)) and the
per-agent Hermes-home cron backup (every 4 hours, once activated) are the
scheduled lanes that exist in code. The daily SQLite `.backup` and per-deployment
`pg_dump`/state-root rsync rows describe an **intended** schedule — there is no
control-DB `.backup` or `pg_dump` timer in the repo today. Run those steps
manually until a scheduler lands.

## SQLite Backup

```bash
# Online backup (safe while API is running)
sqlite3 "$ARCLINK_DB_PATH" ".backup /path/to/backup/arclink-control-$(date +%Y%m%d).sqlite3"
```

The SQLite WAL mode allows concurrent reads during backup. Do not copy the
`.sqlite3` file directly while the API is running; use `.backup` instead.

## Per-Deployment Volume Backup

ArcPod Postgres data lives in a per-deployment named Compose volume following the
convention `arclink-{deployment_id}_postgres_data`.

```bash
# Export a named Docker volume (substitute the real deployment id)
docker run --rm -v arclink-<deployment_id>_postgres_data:/data -v /backup:/backup \
  alpine tar czf /backup/postgres-$(date +%Y%m%d).tar.gz -C /data .
```

## Backup Scripts

ArcLink ships two purpose-built, secret-excluding backup scripts. Both refuse
public GitHub repositories and use SSH deploy keys that are kept out of the
backup commit.

### Control / `arclink-priv` — `bin/backup-to-github.sh`

Backs up the control tree at `ARCLINK_PRIV_DIR` (default
`$ARCLINK_REPO_DIR/arclink-priv`, containing `vault/`, `state/`, `published/`,
`config/`, `quarto/`) to a private git remote.

- Commits to branch `BACKUP_GIT_BRANCH` (default `main`) as
  `ArcLink Backup <arclink@localhost>`.
- **Excludes the backup deploy key, its `.pub`, and the known-hosts file** from
  the commit when they live under the priv dir, plus nested `.git`
  repos/submodules and gitignored top-level entries.
- When `BACKUP_GIT_REMOTE` is set it calls `require_private_github_backup_remote`
  (refuses public repos), pins SSH transport via
  `BACKUP_GIT_DEPLOY_KEY_PATH` (default
  `$ARCLINK_HOME/.ssh/arclink-backup-ed25519`) with
  `StrictHostKeyChecking=yes` and a pinned known-hosts file, then reconciles and
  pushes.
- **Branch reconciliation:** fast-forwards when behind; refuses on a divergence
  that shares a merge-base; when the remote has unrelated history it first
  archives it to `archive/{branch}-pre-align-{ts}-{remote_short}` then aligns
  with `--force-with-lease`. Steady state is a single-writer timer doing a normal
  non-force push.

### Per-agent Hermes home — `bin/backup-agent-home.sh` + `bin/configure-agent-backup.sh`

Backs up one enrolled Captain Agent's Hermes home to a **separate per-user**
private git remote. This is a distinct key from the `arclink-priv` backup key and
the ArcLink upstream code-push key.

The activation flow is **two-phase (pending → verify → activate)**, which is the
real `GAP-013` boundary:

1. **Prepare.** `bin/configure-agent-backup.sh <hermes-home> --remote git@github.com:owner/private-repo.git`
   verifies the remote is a private GitHub SSH remote (via the GitHub API,
   refusing public repos), mints a per-user ed25519 deploy key
   (default `$HOME/.ssh/arclink-agent-backup-ed25519`), writes a **pending** state
   file (`state/arclink-agent-backup.pending.env`), and prints the public key. It
   does **not** activate. The operator must install that public key on the private
   repo with write access.
2. **Verify + activate.** Re-run with `--verify`. This runs `verify_backup_git_access`
   — a real `git ls-remote` read check and a `git push --dry-run` write check (no
   real push or branch is created) — then promotes pending → active state
   (`state/arclink-agent-backup.env`), installs the Hermes cron backup job (every
   4 hours), disables the legacy `arclink-user-agent-backup.timer`, and runs the
   backup once.

The snapshot itself (`bin/backup-agent-home.sh`) is **curated and secret-excluding**:
it copies `SOUL.md`, `config.yaml`, `memories`, `skills`, `plugins`, `cron`, four
curated `state/arclink-*.json` files, and `sessions/` (default on,
`AGENT_BACKUP_INCLUDE_SESSIONS=1`), writes a `MANIFEST.json`, and commits as
`ArcLink Agent Backup <arclink-agent@localhost>`. **Secrets and logs are never
copied.** Until an authorized `PG-BACKUP` runner completes the live GitHub
write + activation + restore, the chat/dashboard surfaces can only reach
`pending_key_setup`, and the unattended write check stays `failed_closed`. See
[GAPS.md](../../GAPS.md) for GAP-013.

### Docker lifecycle authority

Stopping, restarting, or tearing down an ArcPod Compose stack does **not** go
through a bare `docker compose` call in Docker mode. The executor
(`python/arclink_executor.py`) validates the project name (`arclink-{deployment_id}`),
the env file (`config/arclink.env`), and the compose file (`config/compose.yaml`)
under the state-root base, then drives the operation through the
`deployment-exec-broker` (header `X-ArcLink-Deployment-Exec-Broker-Token`), which
allowlists only `compose_up` / `compose_ps` / `compose_down`. This is a
GAP-019 trust-boundary surface; see
[`operations-runbook.md`](operations-runbook.md) for the authoritative broker/helper
inventory. Volume deletion on teardown is opt-in (gated by
`metadata.teardown.remove_volumes`); the default teardown preserves volumes.

## Restore Procedure

### Control Database

1. Stop the hosted API.
2. Replace the SQLite file with the backup copy.
3. Start the hosted API.
4. Verify via `GET /api/v1/health`.

### Per-Deployment Stack

1. Stop the ArcPod Compose stack. In Docker mode this runs through the executor +
   `deployment-exec-broker` path (path/project validation, allowlisted
   `compose_down`), not a bare `docker compose down`.
2. Restore volumes from backup (e.g. `arclink-{deployment_id}_postgres_data`) and
   the deployment state roots.
3. Start the Compose stack (executor + broker `compose_up`).
4. Verify service health via admin dashboard.

### Full Disaster Recovery

1. Provision a new host with Docker and Traefik.
2. Restore the control database.
3. Restore per-deployment state roots and volumes.
4. Re-run DNS provisioning to point to the new host IP.
5. Start all deployment Compose stacks.
6. Verify health and DNS resolution.

## Retention

- Keep daily backups for 30 days.
- Keep weekly backups for 90 days.
- Vault git history provides indefinite file-level recovery.

## Local Restore Smoke

Before claiming a backup artifact is usable, run the no-secret local restore
smoke against a local clone, snapshot directory, tar archive, or SQLite backup
file. The smoke restores into a temporary or provided directory, checks the
restored shape without printing file contents, refuses remote GitHub/SSH
sources, and does not start Docker, systemd, deploy, or live services.

```bash
bin/arclink-restore-smoke.sh \
  --kind shared \
  --source /path/to/local/arclink-priv-backup \
  --restore-dir /tmp/arclink-shared-restore-smoke \
  --json

bin/arclink-restore-smoke.sh \
  --kind agent-home \
  --source /path/to/local/agent-home-backup \
  --restore-dir /tmp/arclink-agent-restore-smoke \
  --json
```

The smoke runs named structural checks per kind. For `--kind shared` it
recognizes `config/`, `vault/`, `state/`, `published/`, or `quarto/` content (or a
SQLite backup) and runs a read-only `PRAGMA quick_check` on every `.sqlite3`/`.db`
file; SQLite backup files are only valid for `--kind shared`. For
`--kind agent-home` it requires a `MANIFEST.json` object, **rejects any `secrets/`
or `logs/` directory**, and requires at least one curated Hermes-home path. It
also rejects nested `.git` metadata and unsafe tar member paths.

This is only a local artifact contract — it proves backup artifact *shape*, not
*recoverability* (`GAP-020`). `PG-BACKUP` still requires an authorized staging
restore of the control database, at least one ArcPod state stack, dashboard/API
health, and deployment service health before production backup recoverability can
be claimed.

## Testing Backups

Periodically restore a backup to a staging environment and verify:
- API health check passes
- Admin dashboard loads deployment list
- At least one deployment stack starts and passes health checks
