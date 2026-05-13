# ArcLink Data Safety

## State Models By Mode

ArcLink has three operating modes with different state boundaries.

| Mode | State Model | Notes |
| --- | --- | --- |
| Shared Host | Public repo plus nested private state under `/home/arclink/arclink/arclink-priv/`; enrolled users have private Hermes homes under `/home/<user>/.local/share/arclink-agent/hermes-home`. | Operator-led, systemd-backed, per-user Unix accounts. |
| Shared Host Docker | Same private state contract, bind-mounted into Compose from `arclink-priv/`; Docker agent homes live under `arclink-priv/state/docker/users/`. | Trusted-host containerization of the shared-host substrate. |
| Sovereign Control Node | Dockerized product control plane with per-deployment state roots, Compose projects, and secret references rendered from control-plane rows. Current product pod state defaults are under the configured deployment state root, commonly `/arcdata/deployments`. | Paid self-serve control surface; provisioning and admin action workers are enabled by default, but live provider/account mutation still fails closed unless the operator configures the executor and external credentials. |

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

## User And Agent Access

ArcLink intentionally gives each enrolled user and agent broad access to their
own deployment home, vault, workspace, and dashboard tools. This should feel
like SSH into that user's isolated agent environment, not like a narrow file
picker. The boundary is not "hide the user's own files"; the boundary is "do
not expose the operator control plane, another user, or shared host secrets."

Dashboard Drive, Code, and Terminal plugins therefore allow normal user-owned
files, including ordinary `.env` files inside the user's own Vault/Workspace,
while blocking control-plane/private-state env files, Hermes bootstrap tokens,
ArcLink secrets directories, private SSH material, and other users'
deployment roots. Terminal sessions run with a scrubbed allowlist environment
instead of inheriting operator/service secrets from the dashboard process.

Accepted ArcLink shares are mounted as a separate Linked root in Drive and
Code. Linked resources are scoped to the accepted file or directory, are
read-only from the receiver's share root, cannot be reshared from that root,
and may be copied into the receiver's own Vault/Workspace only through the
receiver's normal user boundary.

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
- Docker socket writers are trusted-host services. In Docker mode,
  `agent-supervisor` intentionally runs as root inside its container so it can
  create per-agent Unix users and launch sibling runtime/proxy containers; it
  must stay inside the private host boundary.

## Knowledge And Memory Rails

Agents should use ArcLink MCP tools before raw rummaging:
`knowledge.search-and-fetch`, `vault.search-and-fetch`, `vault.fetch`,
`notion.search-and-fetch`, `notion.fetch`, `ssot.read`, `ssot.write`, and
`ssot.status`.

The vault qmd rail is limited to vault-owned collections such as `vault` and
`vault-pdf-ingest`. Notion content is exposed through the Notion-specific
indexed rail and live Notion fetch paths, with live reads falling back to the
indexed markdown cache when the API cannot prove the page. PDF sidecar metadata
must not leak generated host paths across API boundaries.

`arclink-managed-context` injects compact awareness sections and
`[managed:recall-stubs]` into Hermes turns. These stubs are routing hints, not
evidence. They tell the agent which rail to fetch from before citing,
answering, or changing state. Dynamic managed context is not written into
Hermes `MEMORY.md`.

Almanac is the knowledge-store lineage/rail inside ArcLink. ArcLink is the
current product identity.

## Backup Plan

See `docs/arclink/backup-restore.md` for the full backup and restore procedure.

- **Control database:** Daily SQLite `.backup` snapshots, 30-day retention.
- **Per-deployment Postgres:** Daily `pg_dump`, 30-day retention.
- **Vault files:** Continuous git auto-commit backup.
- **State roots:** Weekly rsync, 90-day retention.

## Teardown Safeguards

Destructive operations are allowed only through scoped, audited control rails.
The product goal is to avoid tying the agent's hands while still making
dangerous writes reversible, attributable, and policy-aware. Gating levels:

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

7. **SSOT destructive writes stay brokered.** Notion archive/delete/trash
   behavior should go through `ssot.write` so ArcLink can apply page scope,
   ownership verification, approval/undo policy, audit records, and user
   notifications. Raw live Notion access is for reads and exact fetches, not
   bypassing the broker.

## Secret Leak Prevention

- `_reject_secret_material()` is called on all dashboard read-model outputs
  and admin action metadata before write.
- Structured events redact sensitive fields.
- API error responses use generic safe error strings, never raw tracebacks.
- Tests verify no secret patterns appear in logs, docs, or generated artifacts
  (see `tests/test_public_repo_hygiene.py`).
