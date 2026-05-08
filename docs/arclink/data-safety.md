# ArcLink Data Safety

## State Models By Mode

ArcLink has three operating modes with different state boundaries.

| Mode | State Model | Notes |
| --- | --- | --- |
| Shared Host | Public repo plus nested private state under `/home/arclink/arclink/arclink-priv/`; enrolled users have private Hermes homes under `/home/<user>/.local/share/arclink-agent/hermes-home`. | Operator-led, systemd-backed, per-user Unix accounts. |
| Shared Host Docker | Same private state contract, bind-mounted into Compose from `arclink-priv/`; Docker agent homes live under `arclink-priv/state/docker/users/`. | Trusted-host containerization of the shared-host substrate. |
| Sovereign Control Node | Dockerized product control plane with per-deployment state roots, Compose projects, and secret references rendered from control-plane rows. Current product pod state defaults are under the configured deployment state root, commonly `/arcdata/deployments`. | Paid self-serve control surface; live mutation remains proof-gated unless explicitly enabled. |

Do not apply a path from one mode to another without checking the generated
config and control-plane metadata.

## Per-Deployment Isolation

Sovereign deployments are rendered as isolated Docker Compose stacks with:

- **Dedicated Postgres database** per deployment where the rendered pod uses one.
- **Dedicated Nextcloud instance** per deployment.
- **Dedicated Redis cache** per deployment where required.
- **Isolated state root** under the configured deployment state root.
- **Isolated Docker volumes** namespaced by Compose project name.

The access model is enforced by `arclink_access.py`, which pins the
`cloudflare_access_tcp` domain SSH strategy, `tailscale_direct_ssh` Tailscale
SSH strategy, and `nextcloud_dedicated` isolation model.

## Volume Layout

```text
<deployment-state-root>/{deployment_id}/
  vault/              # User vault files
  state/              # Runtime state, qmd indexes, memory synthesis
  nextcloud/          # Nextcloud data (if not using Docker volumes)
  published/          # Quarto/published output
  config/             # Per-deployment configuration
```

Sovereign pod Docker volumes follow the naming convention:
- `arclink-{deployment_id}_postgres_data`
- `arclink-{deployment_id}_nextcloud_data`
- `arclink-{deployment_id}_redis_data`

## Secret Storage

- Per-deployment secrets use `secret://...` references in database rows.
- Compose secrets are mounted at `/run/secrets/{name}` inside containers.
- Images supporting `_FILE` env vars (Postgres, Nextcloud) read from mounted files.
- No plaintext secret values in database, logs, API responses, or Compose intent.
- Shared Host and Shared Host Docker secrets belong in private `arclink-priv/`
  config/state, not public docs or git history.

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
