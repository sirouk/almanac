# ArcLink Data Safety

## Per-User Isolation

Each ArcLink deployment runs as an isolated Docker Compose stack with:

- **Dedicated Postgres database** per deployment (not shared across users)
- **Dedicated Nextcloud instance** per deployment
- **Dedicated Redis cache** per deployment
- **Isolated state root** at `/srv/arclink/{deployment_id}/`
- **Isolated Docker volumes** namespaced by Compose project name

The isolation model is enforced by `arclink_access.py` which pins the
`cloudflare_access_tcp` domain SSH strategy, `tailscale_direct_ssh` Tailscale
SSH strategy, and `nextcloud_dedicated` isolation model.

## Volume Layout

```
/srv/arclink/{deployment_id}/
  vault/              # User vault files
  state/              # Runtime state, qmd indexes, memory synthesis
  nextcloud/          # Nextcloud data (if not using Docker volumes)
  published/          # Quarto/published output
  config/             # Per-deployment configuration
```

Docker volumes follow the naming convention:
- `arclink-{deployment_id}_postgres_data`
- `arclink-{deployment_id}_nextcloud_data`
- `arclink-{deployment_id}_redis_data`

## Secret Storage

- Per-deployment secrets use `secret://...` references in database rows.
- Compose secrets are mounted at `/run/secrets/{name}` inside containers.
- Images supporting `_FILE` env vars (Postgres, Nextcloud) read from mounted files.
- code-server uses an explicit entrypoint resolver for password injection.
- No plaintext secret values in database, logs, API responses, or Compose intent.

## Backup Plan

See `docs/arclink/backup-restore.md` for the full backup and restore procedure.

- **Control database:** Daily SQLite `.backup` snapshots, 30-day retention.
- **Per-deployment Postgres:** Daily `pg_dump`, 30-day retention.
- **Vault files:** Continuous git auto-commit backup.
- **State roots:** Weekly rsync, 90-day retention.

## Teardown Safeguards

Destructive operations are gated at multiple levels:

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

## Secret Leak Prevention

- `_reject_secret_material()` is called on all dashboard read-model outputs
  and admin action metadata before write.
- Structured events redact sensitive fields.
- API error responses use generic safe error strings, never raw tracebacks.
- Tests verify no secret patterns appear in logs, docs, or generated artifacts
  (see `tests/test_public_repo_hygiene.py`).
