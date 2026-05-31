# Ground Truth: Backup, Restore, Executor, Data Lifecycle, Wrapped, Customer Lifecycle

Date: 2026-05-30. Branch: arclink. Source-of-truth = code under `/root/arclink`.

This record covers the executor (Docker Compose apply/lifecycle/rollback, provider
mutations), the three backup lanes (control DB `arclink-priv`, per-agent Hermes home,
restore-smoke), Pod migration capture, ArcLink Wrapped, and the teardown / rollback /
volume-delete separation. `PG-BACKUP` is the live proof gate that nearly everything
here is still blocked behind.

---

## 1. What is actually implemented today (local-real)

### 1.1 Executor (`python/arclink_executor.py`, ~2497 lines)

The `ArcLinkExecutor` class is an injectable, fail-closed orchestration boundary for
Docker Compose and provider mutations. Real behavior:

- **Fail-closed by default.** Every mutating method calls `_require_live_enabled()`,
  which raises `ArcLinkLiveExecutionRequired` unless `ArcLinkExecutorConfig.live_enabled`
  is `True`. Config also carries `adapter_name` (`disabled` default, or `fake`/`local`/`ssh`),
  `state_root_base` (default `/arcdata/deployments`), and
  `allow_lifecycle_project_override`.
- **`docker_compose_apply(DockerComposeApplyRequest)`** -> `DockerComposeApplyResult`.
  Plans via `_plan_docker_compose_apply`, validates paths via
  `_validate_docker_compose_apply_plan` (this is the `GAP-019-E` preflight: safe
  deployment id, project name must equal `arclink-{id}`, env/compose files must be
  `config/arclink.env` and `config/compose.yaml` under the state-root base). Materializes
  secret files (0600, `/run/secrets/...` targets) and compose/env files (0600) via
  `_materialize_docker_compose_files`, then runs `("up","-d","--remove-orphans")`. On any
  exception it cleans up the materialized `secrets/` root and per-file secret copies.
- **`docker_compose_dry_run`** -> `DryRunStep` (secret-free plan, no `live_enabled` gate).
- **`docker_compose_lifecycle(DockerComposeLifecycleRequest)`** supports exactly four
  actions: `stop`, `restart`, `inspect`, `teardown`. Compose args map:
  `stop->("stop",)`, `restart->("restart",)`, `inspect->("ps","--format","json")`,
  `teardown->("down","--remove-orphans", [+"--volumes" iff request.remove_volumes])`.
  **Volume preservation is the default**: `--volumes` is only added when
  `remove_volumes=True`. After a teardown it cleans the `secrets/` root. Result metadata
  carries `preserve_volumes = not request.remove_volumes`.
- **`rollback_apply(RollbackApplyRequest)`** -> `RollbackApplyResult`. `_plan_rollback_apply`
  enforces the state-preservation contract: the plan MUST contain `preserve_state_roots`
  in `actions`, else raises "ArcLink rollback execution must preserve customer state roots";
  any action matching `_is_destructive_state_delete` (delete/deletion + state/root/roots/vault)
  raises "must not delete customer state roots or vault data". Result always has
  `preserve_state_roots=True`. Plans `stop_rendered_services` and
  `remove_unhealthy_containers` (unhealthy = service health status not in {healthy, starting}).
  Surfaces `protected_state_roots` (root, state, vault, linked_resources, hermes_home, qmd,
  memory, nextcloud, code_workspace) and `secret_refs_for_review`.
- **Provider mutations**: `cloudflare_dns_apply`, `cloudflare_dns_teardown`,
  `cloudflare_access_apply`, `chutes_key_apply` (create/rotate/revoke),
  `stripe_action_apply` (refund/cancel/portal). Live Cloudflare DNS talks to
  `https://api.cloudflare.com/client/v4` via `_cloudflare_request`. Chutes/Stripe live
  paths require injected `ChutesKeyClient` / `StripeActionClient` and use durable
  operation idempotency (`arclink_control.reserve/complete/fail/replay_arclink_operation_idempotency`).
- **DockerRunner implementations (real):**
  - `SubprocessDockerComposeRunner` — runs `docker compose` locally after files are materialized.
  - `SshDockerComposeRunner` — `mkdir`/`rsync -a --delete`/remote `docker compose`; enforces
    `_require_allowed_ssh_host` against an explicit allowlist; cleans up remote `secrets/`
    after `up`/`down`.
  - `BrokeredDockerComposeRunner` — POSTs to `{broker_url}/v1/docker-compose` with header
    `X-ArcLink-Deployment-Exec-Broker-Token`; only allowlists `compose_up`/`compose_ps`/
    `compose_down` via `_broker_operation_from_compose_args` (this is the `GAP-019-G`/`H`
    deployment-exec-broker path that replaced a direct socket mount).
- **`executor_for_fleet_host(...)`** is the factory: `fake` -> `FakeSecretResolver`; `local`
  -> Brokered runner if broker URL+token set (required when `ARCLINK_DOCKER_MODE`), else
  `SubprocessDockerComposeRunner`; `ssh` -> `SshDockerComposeRunner` gated on
  `ARCLINK_EXECUTOR_MACHINE_MODE_ENABLED=1` + host allowlist + validated SSH key.
- Atomic 0600 private writes via `_write_private_file_atomic` (flock + tmpfile + os.replace).
  Errors redacted via `arclink_secrets_regex.redact_then_truncate`.

### 1.2 Backup lane A — control DB / `arclink-priv` git backup (`bin/backup-to-github.sh`)

- Operates on `$ARCLINK_PRIV_DIR` (default `$ARCLINK_REPO_DIR/arclink-priv`; contains
  `vault/`, `state/`, `published/`, `config/`, `quarto/`). `require_real_layout` +
  `ensure_layout` first.
- Inits a git repo at `$ARCLINK_PRIV_DIR` on branch `$BACKUP_GIT_BRANCH` (default `main`).
- **Excludes the backup deploy key, its `.pub`, and the known-hosts file** from the commit
  if they live under the priv dir; excludes nested `.git` repos / submodules and
  gitignored top-level entries (`:(exclude)` pathspecs).
- Commits as `ArcLink Backup <arclink@localhost>` (`BACKUP_GIT_AUTHOR_NAME/EMAIL`).
- If `BACKUP_GIT_REMOTE` set: `require_private_github_backup_remote` (refuses public repos),
  `ensure_backup_git_origin_remote`, `prepare_backup_git_transport` (sets `GIT_SSH_COMMAND`
  with `BACKUP_GIT_DEPLOY_KEY_PATH` default `$ARCLINK_HOME/.ssh/arclink-backup-ed25519`,
  `StrictHostKeyChecking=yes`, pinned known-hosts), then
  `reconcile_backup_git_remote_branch` and push.
- **Branch reconciliation logic** (shared, duplicated verbatim in `backup-agent-home.sh`):
  fast-forwards when behind; refuses with an error when diverged (shared merge-base);
  when remote has unrelated history, archives it to
  `archive/{branch}-pre-align-{ts}-{remote_short}` then force-with-lease aligns. Steady
  state is a single-writer timer -> normal non-force push.
- Helper functions live in `bin/common.sh` (`prepare_backup_git_transport`,
  `require_private_github_backup_remote`, `ensure_backup_git_origin_remote`,
  `path_is_within_dir`, `path_relative_to_dir`).
- `bin/deploy.sh` prints the invocation hint (`sudo -iu $ARCLINK_USER ... backup-to-github.sh`)
  around line 3257.

### 1.3 Backup lane B — per-agent Hermes home backup (`bin/backup-agent-home.sh`, `bin/configure-agent-backup.sh`)

- **Two-phase activation gating (this is the real `GAP-013` boundary):**
  `configure-agent-backup.sh <hermes-home> --remote ... [--verify]`. First run writes a
  PENDING state file `state/arclink-agent-backup.pending.env`, mints a per-user ed25519
  deploy key (`$HOME/.ssh/arclink-agent-backup-ed25519`), and prints the public key. It does
  NOT activate. Re-run with `--verify` runs `verify_backup_git_access` (git `ls-remote` read
  check + `git push --dry-run` write check, no real push), promotes pending -> active state
  `state/arclink-agent-backup.env`, installs the Hermes cron job
  (`install-agent-cron-jobs.sh`, every 4 hours), disables the legacy
  `arclink-user-agent-backup.timer`, and runs the cron script once.
- **Public-repo refusal** in both scripts via `github_repo_visibility` (GitHub API
  `/repos/{owner_repo}`; `private`/`public`/`non-public-or-missing`/`error:*`). Non-default
  `AGENT_BACKUP_GITHUB_API_BASE` is refused unless `ARCLINK_AGENT_BACKUP_ALLOW_TEST_GITHUB_API_BASE=1`
  (tests only). Only `git@github.com:...` / `ssh://git@github.com/...` SSH remotes are supported.
- **Curated snapshot** (`backup-agent-home.sh` `copy_path`): `SOUL.md`, `config.yaml`,
  `memories`, `skills`, `plugins`, `cron`, four `state/arclink-*.json` files
  (identity-context, enrollment, prefill-messages, vault-reconciler), and `sessions/` iff
  `AGENT_BACKUP_INCLUDE_SESSIONS=1` (default 1). Writes `MANIFEST.json` (created_at,
  hermes_home, include_sessions, host, unix_user). Commits as
  `ArcLink Agent Backup <arclink-agent@localhost>`. **Secrets and logs are never copied.**
- Separate key: "do not reuse the ArcLink upstream code-push key or the shared arclink-priv
  backup key" is enforced by convention/docs and distinct default key paths.

### 1.4 Restore smoke (`bin/arclink-restore-smoke.sh`) — `GAP-020` artifact

- Local-only restore contract. `--kind shared|agent-home --source PATH [--restore-dir PATH] [--json]`.
- **Refuses remote sources** (`*://*`, `git@*`, `ssh://*`, `http(s)://*`): "clone or fetch
  live backups only in an authorized proof window". Never touches Docker/systemd/deploy/live.
- Source handling: a `.git` dir -> `git archive HEAD`; a plain dir -> tar snapshot excluding
  `.git`; a `*.tar/.tar.gz/.tgz` -> member path validation (rejects absolute / `..` paths)
  then extract; a `*.sqlite3/.db` -> only valid for `--kind shared`, copied into `state/`.
- Validations: `validate_no_nested_git` (rejects nested `.git`), non-empty tree,
  `validate_shared_restore` (recognizes config/vault/state/published/quarto or SQLite +
  runs `PRAGMA quick_check` read-only on each `.sqlite3/.db`), `validate_agent_home_restore`
  (requires `MANIFEST.json` object; **rejects `secrets/` and `logs/`**; requires >=1 curated
  Hermes path). Emits check names: `git_archive_head`, `directory_snapshot`, `tar_snapshot`,
  `sqlite_backup_file`, `no_nested_git_metadata`, `sqlite_quick_check`, `shared_layout`,
  `agent_manifest_json`, `agent_secret_exclusion`, `agent_curated_paths`.

### 1.5 Pod migration capture (`python/arclink_migration_capture_helper.py`, `python/arclink_pod_migration.py`)

- The capture helper is a tokened root HTTP service `migration-capture-helper`
  (`SERVICE_NAME`), default `127.0.0.1:8914`, header
  `X-ArcLink-Migration-Capture-Helper-Token` (`MIGRATION_CAPTURE_HELPER_TOKEN_HEADER`),
  routes `GET /health` and `POST /v1/migration-capture`. Allowlisted operations only:
  `capture`, `materialize` (`ALLOWED_OPERATIONS`). It **rejects raw commands** (`args`/`cmd`/`command`
  keys) and confines source/target/capture paths under `ARCLINK_STATE_ROOT_BASE`
  (`_require_under_configured_base`), requiring deployment-scoped root names via
  `render_arclink_state_roots`. Capture dir must be `{target_parent}/.migrations/{migration_id}`.
- Requires `require_docker_trusted_host_risk_accepted` (`GAP-019-AL`) and a configured token.
  Records redacted rejection incidents (`record_rejection_incident`, `GAP-019-BD`). This is
  the `GAP-019-N`/`AC`/`K` boundary: control-action-worker no longer does root capture itself.
- `arclink_pod_migration.py` owns queueing/idempotency/lifecycle. `_copy_capture` stages to
  `{capture_dir}/source-root`; `_materialize_capture` restores it. Rollback path
  (`_rollback_lifecycle`) calls `executor.docker_compose_lifecycle(action="teardown",
  remove_volumes=False)` on the target and restarts the source. GC removes capture dirs
  (must contain `.migrations`) and honors `source_retention_until` /
  `source_garbage_collected_at`.

### 1.6 ArcLink Wrapped (`python/arclink_wrapped.py`, ~1180 lines)

- Single owner for Wrapped scoring/reads/render/persist/cadence/enqueue/scheduler/admin.
- **Cadence**: `set_wrapped_frequency` writes `arclink_users.wrapped_frequency` (CHECK in
  {daily, weekly, monthly}), audits `wrapped_frequency_updated`. `daily` default; anything
  more frequent than daily is rejected (`normalize_wrapped_frequency`).
- **Scoping is read-only over Captain state** except writing `arclink_wrapped_reports` and
  `notification_outbox` rows. Reads scoped to one Captain + period: `arclink_events`,
  `arclink_audit_log`, `arclink_pod_messages` (same-Captain only), `memory_synthesis_cards`,
  injected `session_counter` (Hermes sessions/turns) and `vault_delta_reader`. **Operator
  deployments are excluded** (`_is_operator_deployment`); terminal deployments
  (`cancelled`, `teardown_complete`, `torn_down`) are excluded from the active set.
- **Privacy**: `_redact_text` / `_redact_any` redact secret material and token-like keys
  before any rendered text or persisted ledger; ledger `scoped_ledger` is redacted.
  `formula_version = "wrapped_novelty_v1"`; novelty score capped at 100.
- **Scheduler**: `run_wrapped_scheduler_once` -> `list_due_wrapped_captains` (active users,
  per-cadence period via `resolve_wrapped_period`; due if missing-with-signal or failed-retry).
  A bare deployment row is NOT a signal — `_has_wrapped_signal`/`_wrapped_signal_counts`
  require real events/audits/messages/memory cards. Generates, enqueues, and on exception
  records `_record_wrapped_failure` (status `failed`, `INSERT OR REPLACE`); at
  `_PERSISTENT_FAILURE_THRESHOLD = 3` it queues a `target_kind='operator'` `tui-only`
  notification with NO Captain narrative.
- **Delivery enqueue**: `enqueue_wrapped_report_notification` resolves the Captain's
  telegram/discord home channel from `arclink_onboarding_sessions` (`_captain_delivery_channel`,
  identity normalized to `tg:`/`discord:`), inserts `notification_outbox`
  `target_kind='captain-wrapped'` with `extra_json` carrying only safe metadata, and sets
  `next_attempt_at` via `next_attempt_after_quiet_hours` (parses `22:00-08:00`-style,
  default from `ARCLINK_ORG_QUIET_HOURS`). If no channel -> `delivery_channel='unavailable'`,
  returns 0.
- **Admin view** `wrapped_admin_aggregate`: status counts, last 10, average novelty, due/failed
  counts — aggregate only, no report text/markdown/ledger.
- **Docker service**: named `arclink-wrapped` job-loop (`python/arclink_provisioning.py:952`),
  `./bin/docker-job-loop.sh arclink-wrapped 300 ./bin/arclink-wrapped.sh --json`, 300s loop,
  limits 128M/0.25 CPU, vault+memory volumes, no Docker socket. Wrapper `bin/arclink-wrapped.sh`
  execs `python/arclink_wrapped.py`. Live operator container observed as
  `arclink-control-operator-arclink-wrapped-1` (`bin/deploy.sh:10743`).

### 1.7 Customer lifecycle (teardown / cancel / refund / backup write-check)

- **Action worker** (`python/arclink_action_worker.py`) `_EXECUTOR_ACTIONS` =
  `{restart, reprovision, dns_repair, rotate_chutes_key, refund, cancel, comp,
  backup_write_check}`. Note: **`teardown` and `rollback` are NOT action-worker action
  types** — admin actions can `restart` (maps to `docker_compose_lifecycle action="restart"`)
  but the action worker never calls teardown/volume-delete/rollback.
- **Teardown lives in the sovereign worker** (`python/arclink_sovereign_worker.py`):
  `docker_compose_lifecycle(action="teardown", remove_volumes=_teardown_removes_volumes(metadata))`.
  `_teardown_removes_volumes` returns True only when `metadata.teardown.remove_volumes is True`
  — i.e. **volume deletion requires explicit metadata; default teardown preserves volumes.**
  Teardown also calls `cloudflare_dns_teardown` (domain mode) and Chutes `revoke`.
- **refund/cancel** -> `stripe_action_apply`; target resolved from control DB
  (`_resolve_stripe_action`), `customer_ref = secret://arclink/stripe/customer/{user_id}`,
  refund requires a resolvable Stripe customer, cancel a resolvable subscription.
- **backup_write_check** is fail-closed: unattended local checks call
  `record_arclink_backup_write_check_failed_closed` and record
  `github_write_check: failed_closed` with reason `ARCLINK_BACKUP_FAILED_CLOSED_REASON`
  = "GitHub write verification requires an authorized PG-BACKUP runner; no live git command
  was run." Dashboard read model (`arclink_dashboard.py`) forces
  `backup_activation -> not_active` whenever `github_write_check != "verified"`.

---

## 2. Proof-gated / fake-adapter / local-only

- **Executor live mutation is fail-closed.** Default `live_enabled=False`,
  `adapter_name="disabled"`. The `fake` adapter (`FakeDockerRunner`, `FakeSecretResolver`,
  `_fake_*` methods) only records intents and replays idempotently; it never touches Docker,
  Cloudflare, Chutes, or Stripe. Unit/E2E default is fake.
- **Live Docker** requires `live_enabled=True` + non-fake adapter + injected `DockerRunner`,
  plus (Docker mode) the `deployment-exec-broker` URL/token or SSH machine-mode env.
- **Live Cloudflare/Chutes/Stripe** require real tokens/clients; all blocked behind
  `PG-PROVISION`/`PG-INGRESS`/live gates.
- **Per-agent backup activation is proof-gated by `PG-BACKUP`** (`GAP-013`): chat/dashboard
  can only reach `pending_key_setup` / `repo_recorded_pending_key_setup`; the unattended
  write check is `failed_closed`; activation cannot be claimed until an authorized
  `PG-BACKUP` runner does the live GitHub write + activation + restore proof.
- **Restore-smoke proves artifact shape only, NOT recoverability** (`GAP-020`). It explicitly
  refuses remote sources and never starts services. Staging/live restore of the control DB +
  >=1 ArcPod stack + dashboard/API/service health is still `PG-BACKUP`.
- **migration-capture-helper** root work requires `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED=accepted`
  (`GAP-019-AL`) and a token; it remains trusted-host residual risk (`GAP-019` open).
- **Wrapped live Telegram/Discord delivery** is operator-gated; build validation exercises
  pure handler/outbox paths only.

---

## 3. Canonical vocabulary (real names from code)

- Modules: `arclink_executor.py`, `arclink_wrapped.py`, `arclink_migration_capture_helper.py`,
  `arclink_pod_migration.py`, `arclink_action_worker.py`, `arclink_sovereign_worker.py`,
  `arclink_dashboard.py`, `arclink_provisioning.py`.
- Scripts: `bin/backup-to-github.sh`, `bin/backup-agent-home.sh`, `bin/configure-agent-backup.sh`,
  `bin/arclink-restore-smoke.sh`, `bin/arclink-wrapped.sh`, `bin/docker-job-loop.sh`,
  `bin/install-agent-cron-jobs.sh`.
- Executor classes/dataclasses: `ArcLinkExecutor`, `ArcLinkExecutorConfig`,
  `DockerComposeApplyRequest/Result`, `DockerComposeLifecycleRequest/Result`,
  `RollbackApplyRequest/Result`, `CloudflareDnsApplyRequest/Result`,
  `CloudflareDnsTeardownRequest/Result`, `CloudflareAccessApplyRequest/Result`,
  `ChutesKeyApplyRequest/Result`, `StripeActionApplyRequest/Result`, `DryRunStep`,
  `SubprocessDockerComposeRunner`, `SshDockerComposeRunner`, `BrokeredDockerComposeRunner`,
  `FakeDockerRunner`, `FakeSecretResolver`, `FileMaterializingSecretResolver`,
  `ResolvedSecretFile`. Errors: `ArcLinkExecutorError`, `ArcLinkLiveExecutionRequired`,
  `ArcLinkSecretResolutionError`.
- Executor methods: `docker_compose_apply`, `docker_compose_dry_run`,
  `docker_compose_lifecycle`, `rollback_apply`, `cloudflare_dns_apply`,
  `cloudflare_dns_teardown`, `cloudflare_access_apply`, `chutes_key_apply`,
  `stripe_action_apply`. Lifecycle actions: `stop`, `restart`, `inspect`, `teardown`.
- Tables: `arclink_wrapped_reports` (cols: report_id, user_id, period, period_start,
  period_end, status[pending/generated/delivered/failed], ledger_json, novelty_score,
  delivery_channel, created_at, delivered_at), `arclink_users.wrapped_frequency`,
  `notification_outbox` (`target_kind` `captain-wrapped` / `operator`),
  `arclink_pod_migrations` (capture_dir, source/target_state_root, source_retention_until,
  source_garbage_collected_at, rollback_metadata_json), `memory_synthesis_cards`,
  `arclink_onboarding_sessions`.
- Services: `arclink-wrapped`, `migration-capture-helper`, `deployment-exec-broker`.
- Tokens/headers: `X-ArcLink-Deployment-Exec-Broker-Token`,
  `X-ArcLink-Migration-Capture-Helper-Token`.
- Env: `ARCLINK_STATE_ROOT_BASE` (`/arcdata/deployments`),
  `ARCLINK_DEPLOYMENT_EXEC_BROKER_URL/TOKEN`, `ARCLINK_DOCKER_MODE`,
  `ARCLINK_EXECUTOR_ADAPTER`, `ARCLINK_EXECUTOR_MACHINE_MODE_ENABLED`,
  `ARCLINK_ACTION_WORKER_ALLOW_LIFECYCLE_PATH_OVERRIDES`,
  `ARCLINK_MIGRATION_CAPTURE_HELPER_TOKEN`, `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED`,
  `BACKUP_GIT_REMOTE/BRANCH/DEPLOY_KEY_PATH/KNOWN_HOSTS_FILE/AUTHOR_NAME/AUTHOR_EMAIL`,
  `AGENT_BACKUP_REMOTE/BRANCH/INCLUDE_SESSIONS/KEY_PATH/KNOWN_HOSTS_FILE/REPO_DIR`,
  `ARCLINK_ORG_QUIET_HOURS`.
- Constants: `wrapped_novelty_v1`, `ARCLINK_BACKUP_FAILED_CLOSED_REASON`,
  `_PERSISTENT_FAILURE_THRESHOLD=3`, `_TERMINAL_DEPLOYMENT_STATUSES`.

---

## 4. Undocumented / newer than the docs

- **`BrokeredDockerComposeRunner` + `deployment-exec-broker`** path (GAP-019-G/H) is the real
  local Docker authority today, but `docs/arclink/backup-restore.md` still shows a bare
  `docker compose down` mental model with no mention of the broker.
- **Restore-smoke check names and SQLite-only-for-shared rule** are richer than docs imply
  (10 named checks; `.sqlite3/.db` rejected for agent-home).
- **Two-phase pending/verify agent-backup activation** and the per-user key separation are not
  in `backup-restore.md` at all (only mentioned in `data-safety.md` plan bullet + GAP-013).
- **`archive/{branch}-pre-align-...` unrelated-history reconciliation** in both backup scripts
  is undocumented.
- **Wrapped operator persistent-failure notification at threshold 3**, the
  `_has_wrapped_signal` eligibility gate, operator-deployment exclusion, and terminal-status
  exclusion are not in `wrapped.md`.
- **Teardown lives in the sovereign worker, not the action worker**; `data-safety.md`'s
  teardown safeguards imply `POST /api/v1/admin/actions` performs teardown, but the action
  worker only does `restart`. Volume-delete is gated by `metadata.teardown.remove_volumes`,
  not a `destructive: true` flag (doc says "destructive: true").
- **`rollback_apply` is implemented in the executor but has no production caller wired** in
  the searched modules (pod migration uses `docker_compose_lifecycle teardown` for rollback,
  not `rollback_apply`). It appears scenario/test-facing today.
- **`cloudflare_access_apply` / `stripe_action_apply action="portal"`** exist but are
  peripheral to this subsystem's docs.

---

## 5. Per-doc staleness verdicts

### `docs/arclink/backup-restore.md` — HEAVY stale

- State-root path is wrong: doc says `/srv/arclink/{deployment_id}/`; code uses
  `ARCLINK_STATE_ROOT_BASE` default **`/arcdata/deployments/{deployment_id}`** with subdirs
  `config/`, `vault/`, `state/`, `nextcloud/`, `published/` (see `data-safety.md` Volume Layout,
  which is correct, and executor `_validate_deployment_config_paths`). Fix the table.
- Volume backup example uses volume name `arclink_deployment_postgres`; real convention is
  `arclink-{deployment_id}_postgres_data` (per `data-safety.md`).
- No mention of the **two real backup scripts** (`backup-to-github.sh` for control/priv,
  `backup-agent-home.sh` for Hermes home) or the **two-phase `configure-agent-backup.sh`
  pending->verify->activate** flow, the per-user deploy key separation, public-repo refusal,
  or the curated/secret-excluding snapshot. These should be the centerpiece.
- No mention of `deployment-exec-broker` for the Docker lifecycle; "Stop the deployment
  Compose stack" hides that the executor/broker path enforces path/project validation.
- Restore-smoke section is broadly correct and current (matches the script and GAP-020).
  Minor: enumerate the agent-home `secrets/`+`logs/` rejection and the shared SQLite
  `quick_check`/SQLite-only-for-shared rule.

### `docs/arclink/data-safety.md` — LIGHT stale (mostly accurate, one contradiction)

- Volume Layout, volume naming, secret storage, and the giant `GAP-019` helper/broker
  inventory are accurate and current; `migration-capture-helper` description matches code.
- **Teardown Safeguards #1 and #4 are partly wrong/aspirational.** #1 implies teardown runs
  via `POST /api/v1/admin/actions`; in code the action worker only supports `restart`
  (teardown is sovereign-worker-driven). #4 says volume deletion requires a `destructive: true`
  flag in the rollback plan; the actual gate is `metadata.teardown.remove_volumes is True`
  (`_teardown_removes_volumes`), and `docker compose down` default omits `--volumes`. #3/#6
  (rollback `preserve_state_roots`, `_is_destructive_state_delete`) are accurate.
- Backup Plan bullets (control DB daily `.backup`, per-deployment `pg_dump`, vault continuous,
  state roots weekly) describe an intended schedule; no scheduler/timer for control-DB
  `.backup` or `pg_dump` was found in code — these are aspirational like backup-restore.md.

### `docs/arclink/wrapped.md` — LIGHT stale (accurate, missing detail)

- Ownership, runtime (`arclink-wrapped` job-loop via `docker-job-loop.sh`, no socket),
  delivery (`captain-wrapped` outbox, quiet-hours), API routes `GET /user/wrapped` /
  `POST /user/wrapped-frequency` / `GET /admin/wrapped`, and the `wrapped_novelty_v1` formula
  all match code. Loop interval is 300s (doc doesn't state the interval — fine).
- Missing: the **eligibility signal gate** (`_has_wrapped_signal` — a bare deployment is not a
  signal), **operator-deployment and terminal-deployment exclusions**, the **persistent-failure
  operator notification at 3 attempts** (`tui-only`, no narrative), and the
  `delivery_channel='unavailable'` no-channel outcome. Add these for completeness.

### `docs/arclink/sovereign-control-node-symphony.md` (Backup/Restore/Data-Lifecycle section) — DREAM SHAPE

- The "Backup, Restore, And Data Lifecycle" section (lines ~689-712) is intent, and it
  correctly self-labels: "Local restore-smoke and backup tests provide a base. Staging/live
  restore proof is still `PG-BACKUP`." Code matches this honest framing.
- The dream list (control DB / per-ArcPod state / per-agent Hermes home backup with private
  repo activation only after read+dry-run write checks; reset/rollback/teardown/volume
  deletion as separate operations with separate confirmations) is **partially realized**:
  per-agent two-phase activation with read+dry-run write check is real; teardown vs
  volume-delete separation is real (metadata-gated); reset/restore drills with
  health/dashboard/workspace proof are NOT (still `PG-BACKUP`). No correction needed; it is
  the target, not a status claim.

---

## 6. GAP-* true current status

- **`GAP-013` (Raven backup prep stops before key setup/verification)** — PARTIAL, ux/ops-gap,
  proof-gated by `PG-BACKUP`. TRUE TODAY: public bot records intended repo and explicitly does
  not mint/install/verify the key; dashboard projects `pending_key_setup`, can stage a
  per-deployment key via CSRF-gated API (returns public key/status only); action worker +
  dashboard enforce a fail-closed write check (`github_write_check: failed_closed`,
  `backup_activation: not_active`, reason `ARCLINK_BACKUP_FAILED_CLOSED_REASON`). The CLI
  `configure-agent-backup.sh --verify` does real read+dry-run write checks for the *enrolled
  Hermes-home* lane. Live GitHub write/activation/restore proof remains open.
- **`GAP-020` (Backup/DR documented but not proofed)** — PARTIAL, proof-gated, ops-gap by
  `PG-BACKUP`. TRUE TODAY: `bin/arclink-restore-smoke.sh` exists and covers shared + agent-home
  local artifacts (remote-source refusal, no Docker/systemd, shared-layout + SQLite quick_check,
  agent-home `secrets/`+`logs/` rejection). Regression tests:
  `tests/test_backup_git_regressions.py`, `tests/test_agent_backup_regressions.py`. Staging
  restore ledger + restored health/dashboard/stack proof + live ArcPod restore remain open.
- **`GAP-019` (Docker socket/root authority)** — OPEN (P0 trusted-host). Touched here via
  `migration-capture-helper` (root, sub-gates -AL/-AC/-K/-N/-BD applied as hardening, not
  closure) and `deployment-exec-broker` (writeable socket, -G/-H/-E/-AG/-AX/-AA applied).
  Residual root/socket risk remains until operator residual-risk acceptance or stronger
  isolation.
- **`PG-BACKUP`** — the live proof gate covering control DB + per-ArcPod state + per-agent
  Hermes home backup recoverability. NOT satisfied; all "active/recoverable" claims blocked.

---

## 7. Owning code files

`python/arclink_executor.py`, `python/arclink_wrapped.py`,
`python/arclink_migration_capture_helper.py`, `python/arclink_pod_migration.py`,
`python/arclink_action_worker.py`, `python/arclink_sovereign_worker.py`,
`bin/backup-to-github.sh`, `bin/backup-agent-home.sh`, `bin/configure-agent-backup.sh`,
`bin/arclink-restore-smoke.sh`, `bin/arclink-wrapped.sh`, `bin/common.sh` (backup git helpers),
`python/arclink_provisioning.py` (arclink-wrapped service), `python/arclink_control.py`
(schema), `python/arclink_dashboard.py` (backup write-check read model).
