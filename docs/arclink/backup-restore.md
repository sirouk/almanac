# ArcLink Backup and Restore

## What to Back Up

| Data | Location | Method |
|------|----------|--------|
| Control database | `ARCLINK_DB_PATH` (SQLite) | File copy or `sqlite3 .backup` |
| Per-deployment state roots | `/srv/arclink/{deployment_id}/` | File copy or rsync |
| Per-deployment Nextcloud data | Nextcloud volume in Compose stack | Docker volume export |
| Per-deployment Postgres data | Postgres volume in Compose stack | `pg_dump` or volume export |
| Vault files | `VAULT_DIR` | Git backup (existing `BACKUP_GIT_*` config) |
| Configuration | `config/*.env`, `config/*.yaml` | Git backup (exclude secrets) |

## Backup Schedule

| Frequency | Target |
|-----------|--------|
| Continuous | Vault via git auto-commit (existing ArcLink behavior) |
| Daily | SQLite control database snapshot |
| Daily | Per-deployment Postgres dumps |
| Weekly | Full state root rsync |

## SQLite Backup

```bash
# Online backup (safe while API is running)
sqlite3 "$ARCLINK_DB_PATH" ".backup /path/to/backup/arclink-control-$(date +%Y%m%d).sqlite3"
```

The SQLite WAL mode allows concurrent reads during backup. Do not copy the
`.sqlite3` file directly while the API is running; use `.backup` instead.

## Per-Deployment Volume Backup

```bash
# Export a named Docker volume
docker run --rm -v arclink_deployment_postgres:/data -v /backup:/backup \
  alpine tar czf /backup/postgres-$(date +%Y%m%d).tar.gz -C /data .
```

## Restore Procedure

### Control Database

1. Stop the hosted API.
2. Replace the SQLite file with the backup copy.
3. Start the hosted API.
4. Verify via `GET /api/v1/health`.

### Per-Deployment Stack

1. Stop the deployment Compose stack.
2. Restore volumes from backup.
3. Start the Compose stack.
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

## Testing Backups

Periodically restore a backup to a staging environment and verify:
- API health check passes
- Admin dashboard loads deployment list
- At least one deployment stack starts and passes health checks
