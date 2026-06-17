# CANON-13 — Pod Migration

## PIECE
This piece is ArcLink's 1:1 ArcPod migration orchestrator. It owns exactly one
tracked module: `python/arclink_pod_migration.py` (1275 lines). It plans and
executes a deployment move from a source fleet host/state-root to a target
host/state-root (or a redeploy-in-place), keeping all migration state in the
control plane (`arclink_pod_migrations`) while routing every host mutation
through the injectable `ArcLinkExecutor` (CANON-11) and every file capture either
through an in-process copy (`_copy_capture`/`_materialize_capture`) or, in Docker
mode, through the migration-capture helper (CANON-12). The public surface is three
functions: `plan_pod_migration` (writes the `planned` row), `migrate_pod`
(reserve idempotency -> stop source -> capture -> render target intent -> ensure
LLM router key -> materialize -> `docker_compose_apply` -> verify -> success or
rollback), and `garbage_collect_pod_migrations` (deletes expired capture dirs of
succeeded migrations). The only first-party caller is the action worker
(`python/arclink_action_worker.py`) via the operator `reprovision` action
(CANON-14); the migration-capture helper (CANON-12) imports `_copy_capture` and
`_materialize_capture` from this module, so the capture code is literally shared,
not reimplemented. No CLI entrypoint exists in this module (no `if __name__ ==
"__main__"`), and the file `python/arclink_pod_migration.py` listed in scope
exists and is fully covered here. A clearly-adjacent test file
`tests/test_arclink_pod_migration.py` exists but belongs to CANON-29.

## INPUT CONTRACT (code-verified)

`plan_pod_migration(conn, *, deployment_id, target_machine_id="", migration_id="",
reason="", dry_run=False)` — `python/arclink_pod_migration.py:308`.
- `deployment_id`: required non-empty after `.strip()` else raises
  `ArcLinkPodMigrationError` (`:317-319`). Must exist in `arclink_deployments`
  (`_load_deployment`, `:188-192`).
- `migration_id`: optional; if blank a new `mig_<24 hex>` id is minted
  (`_migration_id`, `:61-62`, `:320`). If a row already exists for that id, it is
  returned as-is but only after asserting it is bound to the same
  `deployment_id` (`:326-327`) and not bound to a conflicting non-empty target
  (`:328-331`) — idempotent replay of planning.
- `target_machine_id`: `""`/`"current"` (case-insensitive) means redeploy in
  place on the source host (`_resolve_target_host`, `:224-226`). Otherwise
  resolved first as a non-`removed` `arclink_inventory_machines.machine_id`
  (whose `machine_host_link` must be non-empty, `:236-240`), else as a
  `arclink_fleet_hosts.host_id` (`:242-244`), else raises (`:245`).
- `reason`, `target_machine_id`: passed through `_reject_secrets` (
  `reject_secret_material`, `:322`, `:69-70`); secret-shaped material raises.
- Target host must be `status == "active"` and `drain == 0` else raises
  "target host is not available" (`:343-344`).
- Caller authority: not enforced here. `plan_pod_migration` trusts its caller;
  authorization is the action worker's job (CANON-14).

`migrate_pod(conn, *, executor, deployment_id, target_machine_id="",
migration_id="", reason="", dry_run=False, env=None, verifier=None,
retention_days=None)` — `:976`.
- `executor`: an `ArcLinkExecutor` (CANON-11); its `docker_compose_lifecycle`,
  `docker_compose_apply`, `docker_compose_dry_run` are invoked. Injectable; tests
  pass a fake adapter.
- `env`: `Mapping[str,str]|None`; falls back to `os.environ` everywhere
  (`_truthy`/config helpers). Gates read from it: `ROOT_CAPTURE_OPT_IN_ENV`,
  capture-helper URL/token, `ARCLINK_DOCKER_MODE`, `ARCLINK_MIGRATION_GC_DAYS`,
  `ARCLINK_SECRET_STORE_DIR`, router default-model vars, helper timeout.
- `verifier`: optional `Callable[(conn, migration_row, intent)] ->
  Mapping|bool`; defaults to `_default_verifier` (`:558`). Return normalized by
  `_normalize_verification` (`:575`); `healthy` is coerced to bool.
- `retention_days`: optional int; if `None`, `ARCLINK_MIGRATION_GC_DAYS` or
  `DEFAULT_GC_DAYS=7` (`:1177-1179`).
- **Double opt-in gate for live (non-dry-run, non-terminal) runs** (`:990-995`):
  `_require_root_capture_opt_in(env)` requires
  `ARCLINK_ACTION_WORKER_ALLOW_ROOT_MIGRATION_CAPTURE` truthy (`:103-112`), then
  `_migration_capture_helper_config(env, require_for_docker=True)` requires a
  configured helper when `ARCLINK_DOCKER_MODE` is truthy (`:130-134`). Dry-run
  requires neither (gate is inside `if not dry_run`).

`garbage_collect_pod_migrations(conn, *, retention_days=None, now=None,
remove_artifacts=True)` — `:1228`. No auth; selects only `succeeded` rows with a
set `source_retention_until` and unset `source_garbage_collected_at`.

## OUTPUT CONTRACT (code-verified)

DB writes (all to the control SQLite passed in as `conn`):
- `arclink_pod_migrations` INSERT of a full `planned` row in `plan_pod_migration`
  (`:368-395`) — columns enumerated match the schema at
  `python/arclink_control.py:1451-1474` (PRIMARY KEY `migration_id`; `status` CHECK
  IN `planned|running|succeeded|failed|rolled_back|cancelled`). `operation_idempotency_key`
  is fixed to `arclink:migration:<migration_id>` (`:389`).
- Status transitions on that table: `-> running` (`:1089-1092`), `-> succeeded`
  with `capture_manifest_json`, `verification_json`, `source_retention_until`,
  `completed_at` (`_mark_success`, `:905-924`), `-> rolled_back` with
  `verification_json`, `rollback_metadata_json`, `error`,
  `source_garbage_collected_at` (set only when capture cleanup removed/missing),
  `completed_at` (`_mark_rollback`, `:796-817`). Dry-run only writes
  `verification_json` (`:1049-1056`) and never leaves `planned`.
- `arclink_deployment_placements`: a `removed` target placement is pre-created for
  cross-host moves with `removed_at='migration_target_pending'`
  (`_ensure_removed_target_placement`, `:293-299`). On success the source
  placement flips `active->removed` and target `removed->active` (`:869-877`); on
  rollback target flips to `removed` and source back to `active` (`:787-795`).
- `arclink_fleet_hosts.observed_load`: on cross-host success, source decremented
  `MAX(0, observed_load-1)` and target incremented (`:878-885`).
- `arclink_deployments.metadata_json`: on success, `state_roots`,
  `state_root_base`, and a `pod_migration` block (migration_id/target_host_id/
  completed_at) are merged in (`:887-904`). Serialized with `json.dumps(...,
  sort_keys=True)` (`:903`) — NOT through the `_reject_secrets`-bearing
  `_json_dumps`; relies on upstream intent being secret-ref-only.
- `arclink_service_health`: on success, `upsert_arclink_service_health(...,
  service_name="pod-migration", status="healthy", ...)` (`:925-931`).
- `arclink_operation_idempotency` (via control helpers): `reserve` status
  `running` (`:1006-1012`), then `complete` (dry-run `:1079`, success `:1189`) or
  `fail` (verification-fail `:1167`, exception `:1217`).
- Events (`append_arclink_event`, subject_kind="deployment"):
  `pod_migration_dry_run_planned` (`:1057`), `pod_migration_started` (`:1093`),
  `pod_migration_completed` (`:932`), `pod_migration_rolled_back` (`:818`),
  `pod_migration_gc_completed` (`:1264`).
- Audit (`append_arclink_audit`, actor_id `system:pod_migration`):
  `pod_migration_dry_run_planned` (`:1065`), `pod_migration_started` (`:1101`),
  `pod_migration_completed` (`:940`), `pod_migration_rolled_back` (`:826`).

Filesystem side-effects (in-process, non-helper path):
- `_copy_capture` (`:430`): `shutil.copytree(source_root, capture_dir/source-root,
  symlinks=True)`, then **deletes every symlink in the staged tree** (`:442-444`)
  and builds a per-file manifest `{path, boundary, size, mode, sha256}` over real
  files only (`:447-458`). Returns `{"files":[...], "file_count":N}`.
- `_materialize_capture` (`:462`): `copytree(capture_dir/source-root, target_root,
  dirs_exist_ok=True, symlinks=True)`.
- `_router_key_value` (`:693`): writes a per-deployment LLM router secret file
  under `ARCLINK_SECRET_STORE_DIR/<deployment_id>/<sha256(ref)>.secret` with an
  `flock`-guarded read-or-create, `0o700` dir / `0o600` file, atomic
  `os.replace` (`:695-719`).
- `_cleanup_rolled_back_capture` (`:839`) and GC (`:1256-1258`): `shutil.rmtree`
  of the capture dir, guarded by `.migrations` being in path parts (`:844-845`).

Wire output (Docker mode): HTTP POST to the capture helper (see CROSS-PIECE).

Return values: `migrate_pod` returns `_result_from_row(...)` (`:958`) — a dict
with `migration_id, deployment_id, status, operation_kind="pod_migration",
operation_idempotency_key, source/target_placement_id, source/target_host_id,
idempotent_replay`, plus `dry_run` and (dry-run) `docker_dry_run`. On an
unexpected exception it re-raises after rollback + fail (`:1225`).

## TOUCH POINTS

Env vars (all via `env or os.environ`):
- `ARCLINK_ACTION_WORKER_ALLOW_ROOT_MIGRATION_CAPTURE` (`:48`, gate `:103-112`).
- `ARCLINK_MIGRATION_CAPTURE_HELPER_URL` / `_TOKEN` (`:49-50`, `:121-122`); both
  required together or both absent (`:124-128`); required in Docker mode when
  `require_for_docker` (`:130-134`).
- `ARCLINK_MIGRATION_CAPTURE_HELPER_TIMEOUT_SECONDS` (default 300, `:494`).
- `ARCLINK_DOCKER_MODE` (truthy => helper required, `:130`).
- `ARCLINK_MIGRATION_GC_DAYS` (default 7, `:1179`).
- `ARCLINK_STATE_ROOT_BASE` (fallback base, `:256`, `:267`).
- `ARCLINK_SECRET_STORE_DIR` (router secret store; if unset, router-key ensure is
  skipped, `:682-686`, `:744-745`).
- `ARCLINK_LLM_ROUTER_DEFAULT_MODEL` / `ARCLINK_CHUTES_DEFAULT_MODEL` (allowed
  model for router key, `:748-752`).
- **Drift:** `ARCLINK_CAPTAIN_MIGRATION_ENABLED` is NOT read anywhere in this
  module (or any `python/` file); see DRIFT.

DB tables read/written: `arclink_deployments` (r/w), `arclink_deployment_placements`
(r/w), `arclink_fleet_hosts` (r/w), `arclink_inventory_machines` (r),
`arclink_pod_migrations` (r/w; schema `python/arclink_control.py:1451-1474`),
`arclink_service_health` (r in verifier `:563-566`, w via upsert),
`arclink_operation_idempotency` (via control helpers),
`arclink_llm_router_keys` (w via `ensure_llm_router_key`,
`python/arclink_control.py:6749`).

Files/paths: capture dir `<target_base>/.migrations/<migration_id>/`
(`:360`); staged tree `.../source-root`; secret store
`<ARCLINK_SECRET_STORE_DIR>/<deployment_id>/<sha256>.secret` + `.lock`.

Sockets/ports: outbound HTTP only — `urllib.request` POST to
`<helper_url>/v1/migration-capture` (`:499-507`). Helper default port 8914 lives
in CANON-12. No listening socket here.

Locks: `fcntl.flock(LOCK_EX)` on the router-secret `.lock` file (`:701-702`).
**No lock around the migration row itself** — concurrency is governed only by the
idempotency `reserve` INSERT OR IGNORE (see RISKS/ADVERSARIAL).

External services / subprocess: none directly. All Docker exec is delegated to
the executor; the only network egress is the capture-helper POST.

Secrets handling: `reject_secret_material` on plan inputs (`:322`);
`redact_then_truncate` on helper error strings (`:517`, `:521`); router raw key
never logged, written `0o600`. The success-path `metadata_json` write uses raw
`json.dumps` (`:903`) bypassing the secret-rejecting `_json_dumps`.

## CODE-PATH TRACE (live cross-host migration, happy path)

1. Action worker `reprovision` builds `operation_key=arclink:migration:<id>`,
   merges `metadata.env` over `env`, calls
   `migrate_pod(conn, executor=..., deployment_id=target_id,
   target_machine_id=metadata.target_machine_id or "current", migration_id, reason,
   dry_run, env)` — `python/arclink_action_worker.py:1157-1178`.
2. `migrate_pod`: not dry-run and no terminal existing row ->
   `_require_root_capture_opt_in(env)` (`:994`) then
   `_migration_capture_helper_config(env, require_for_docker=True)` (`:995`).
3. `plan_pod_migration` loads deployment (`:334`), active placement (`:335`,
   `_active_placement` `:195`), source host (`:336`), resolves source roots from
   `metadata.state_roots` or renders fresh (`_metadata_roots` `:248-262`),
   resolves target host (`:338-342`), validates target active/undrained
   (`:343-344`), renders target roots at target base (`:346-350`), pre-creates a
   `removed` target placement (`:353-359`), computes capture dir (`:360`), INSERTs
   the `planned` row (`:368-395`), commits, returns the row.
4. Back in `migrate_pod`: `reserve_arclink_operation_idempotency(kind=pod_migration,
   key=operation_key, intent=_operation_intent(row,dry_run), status="running")`
   (`:1006-1012`). If `replay` true (terminal prior op) -> return replay result
   (`:1013-1015`).
5. `_validate_capture_paths(conn, row)` (`:1019`, body `:160-185`): asserts source
   & target root names equal the deployment-scoped expected root name, capture dir
   ends with `<migration_id>`, sits under `<target_parent>/.migrations/`, and is
   not inside either root.
6. Row `-> running` (`:1089`), `pod_migration_started` event+audit (`:1093-1110`),
   commit.
7. `executor.docker_compose_lifecycle(action="stop", env_file=<src
   root>/config/arclink.env, compose_file=<src root>/config/compose.yaml,
   key=...:stop-source)` (`:1117-1126`); `source_stopped=True`.
8. `capture_manifest = _capture_files(conn, row, env)` (`:1129`): in Docker mode
   posts to the helper (`_run_migration_capture_helper("capture")` `:481-531`);
   else `_copy_capture` (`:430`). Manifest persisted (`:1130-1134`), commit.
9. Reload deployment + target host, `target_intent = _render_target_intent(...)`
   (`:1138-1144` -> `render_arclink_provisioning_intent` in
   `python/arclink_provisioning.py:1424`).
10. `_ensure_llm_router_key_for_intent` (`:1145`): reads
    `intent.secret_refs.llm_router_api_key`, reads/creates the router secret file,
    calls `ensure_llm_router_key` (`python/arclink_control.py:6731`).
11. `_materialize_files(conn, row, target_root=target_intent.state_roots.root, env)`
    (`:1146`): helper `materialize` op or `_materialize_capture`.
12. `docker_result = executor.docker_compose_apply(DockerComposeApplyRequest(
    deployment_id, intent=target_intent, key=...:compose-target))` (`:1147-1153`).
13. `verification = _normalize_verification((verifier or _default_verifier)(conn,
    row, target_intent))`; `verification["docker_status"]=docker_result.status`
    (`:1154-1155`).
14. healthy -> `_mark_success` flips placements + observed_load, merges deployment
    metadata, marks row `succeeded`, upserts `pod-migration` health, emits
    events/audit (`:1180-1187`); then `complete_arclink_operation_idempotency`
    (`:1189-1196`); returns success result.
15. action worker checks `result.status == "succeeded"` else raises
    `ArcLinkActionWorkerError` (`python/arclink_action_worker.py:1179-1180`).

Unhappy fork (step 13 unhealthy): `_rollback_lifecycle` tears down target (if
distinct host) and restarts source (`:1158-1164`, body `:610-654`); `_mark_rollback`
re-activates source placement, removes target placement, marks row `rolled_back`,
cleans capture dir (`:1165`); `fail_arclink_operation_idempotency` (`:1167-1174`);
returns failed-row result (status `rolled_back`).

## CROSS-PIECE CONTRACTS (both ends verified)

1. **-> CANON-12 (migration-capture helper), wire seam, BOTH ENDS VERIFIED: YES.**
   Producer `_run_migration_capture_helper` POSTs JSON to
   `<url>/v1/migration-capture` with header
   `X-ArcLink-Migration-Capture-Helper-Token: <token>` and body
   `{deployment_id, prefix, migration_id, source_state_root, target_state_root,
   capture_dir, operation}` (`:497-507`, payload builder `:469-478`). Consumer
   `MigrationCaptureHelperHandler.do_POST` requires path `/v1/migration-capture`
   (`python/arclink_migration_capture_helper.py:253`), authorizes via
   `hmac.compare_digest(expected, supplied)` on the SAME header constant imported
   from this module (`:54-57`, `:22-27`), reads body keys
   `operation, deployment_id, prefix, migration_id, source_state_root,
   target_state_root, capture_dir` (`_validate_request` `:115-126`). On success
   returns `{"ok": True, "result": {...}}` (`:276`); on failure
   `{"ok": False, "error": ...}` (status 400/401/413, `:257-278`). Producer
   requires `payload.get("ok") is True` and reads `payload["result"]`
   (`:523-531`). Keys match exactly. **Note:** the helper imports `_copy_capture`
   and `_materialize_capture` straight from THIS module
   (`python/arclink_migration_capture_helper.py:22-27`), so capture/materialize
   behavior is identical to the in-process path by construction. The materialize
   reply `{"status":"materialized"}` is ignored by `_materialize_files`.

2. **-> CANON-08 (provisioning), in-process call, BOTH ENDS VERIFIED: YES.**
   `render_arclink_state_roots` (`python/arclink_provisioning.py:399`) returns a
   dict with key `root` consumed at `:157`, `:166-169` (expected-root-name check),
   `:253`, `:894`. `render_arclink_provisioning_intent`
   (`python/arclink_provisioning.py:1424`) returns an intent dict whose
   `state_roots` (`:1711`) and `secret_refs.llm_router_api_key` (`:1505-1511`,
   `:1713`) keys this module reads at `:736-737` and `:1146`
   (`target_intent["state_roots"]["root"]`). The intent's `state_roots` and
   `compose` are then handed verbatim to `executor.docker_compose_apply`.

3. **-> CANON-11 (executor), dataclass request seam, BOTH ENDS VERIFIED: YES.**
   `DockerComposeLifecycleRequest(deployment_id, action, env_file, compose_file,
   idempotency_key, remove_volumes)` constructed here matches the frozen dataclass
   `python/arclink_executor.py:343-350`; executor restricts `action` to
   `stop|restart|inspect|teardown` (`:951-953`) — this module only sends
   `stop|restart|teardown`. Executor's lifecycle path validates that env/compose
   files equal `<config>/arclink.env` and `<config>/compose.yaml`
   (`:1843-1846`); this module's `_deployment_lifecycle_files` builds exactly
   `<source_state_root>/config/arclink.env` and `.../compose.yaml`
   (`:583-589`), and `_plan_docker_compose_apply` derives the same names from
   `state_roots` (`:1943-1944`) — paths align. `DockerComposeApplyResult.status`
   read at `:1155`; `DryRunStep.{operation,project_name,services,compose_file,
   env_file}` read at `:1041-1045` matches `python/arclink_executor.py:834-840`.

4. **-> CANON-14 (action worker), call+result seam, BOTH ENDS VERIFIED: YES.**
   Caller `python/arclink_action_worker.py:1169-1178` passes
   `deployment_id=target_id`, `target_machine_id` defaulting to `"current"`,
   `migration_id` derived from `action_id` when unset, `env` = process env
   overlaid with `metadata.env`. It reads `result["status"]` (`:1179`) — emitted
   by `_result_from_row` (`:962`). `operation_key` it computes
   (`arclink:migration:<migration_id>`, `:1157`) equals the key
   `plan_pod_migration` stores (`:389`). Match verified.

5. **-> CANON-01 (control plane), idempotency/audit seam, BOTH ENDS VERIFIED:
   YES.** `reserve_arclink_operation_idempotency` returns a dict with `replay`
   (`python/arclink_control.py:3329`) read at `:1013`; `complete`/`fail`
   signatures (`:3352`, `:3397`) match call sites. `ensure_llm_router_key`
   signature (`:6731-6740`) matches the keyword call at `:753-761`.

## CODE vs COMMENT/DOC/NAME DRIFT

1. **`ARCLINK_CAPTAIN_MIGRATION_ENABLED` is doc-only, not code.** Prior doc
   `research/ground-truth/02-provisioning-fleet-ingress.md:282-284` says
   "Captain-initiated migration is policy-disabled by default
   (`ARCLINK_CAPTAIN_MIGRATION_ENABLED=0`...)". This module never reads that var;
   `grep` finds it only in `docs/arclink/control-node-production-runbook.md:244`
   and `docs/arclink/operations-runbook.md:133`. The real code gate that blocks
   Captain self-service is the double opt-in (`:990-995`) plus the fact that the
   only caller is the operator `reprovision` action — there is no env flag in this
   piece. CODE WINS: the doc overstates a code-level toggle that does not exist
   here.

2. **Prior doc says rollback "reactivates source placement" — true, but also
   removes the target placement and the doc omits the observed_load move and the
   capture-dir cleanup.** `_mark_rollback` additionally sets the target placement
   `removed` (`:787-791`) and `_cleanup_rolled_back_capture` deletes the capture
   tree (`:776`, `:839-852`). Doc `02-...:275` is incomplete, not wrong.

3. **Module docstring says "File capture is deliberately small and injectable"
   (`:5-7`).** Capture is injectable only via the env-selected helper, not via a
   function parameter; there is no `capture_fn` argument. The verifier IS
   injectable (`verifier=` param). Minor name/intent drift: "injectable" refers to
   environment routing, not a DI seam.

4. **`_default_verifier` docstring-free name implies a generic check; it only
   inspects `arclink_service_health` for `failed|unhealthy|missing`**
   (`:563-572`). A deployment with zero health rows is reported `healthy=True`
   (empty `blockers`) — verified at `:572` (`not blockers`). Name does not reveal
   this fail-open-on-empty behavior.

5. **Success path uses `json.dumps(metadata, sort_keys=True)` (`:903`) while every
   other serialization uses `_json_dumps` (which calls `reject_secret_material`).**
   The name `_json_dumps` implies a single safe serializer; one write bypasses it.
   Not necessarily a bug (metadata is intent-derived, secret-ref only) but a
   naming/consistency drift worth noting.

## ADVERSARIAL SELF-CHECK

1. **Claim: the double opt-in is enforced before any host mutation.** Falsifier:
   a path where capture/stop runs without the opt-in. The gate at `:990-995`
   runs before `plan_pod_migration` and before the `stop` at `:1118`. BUT it is
   skipped when `existing` is already terminal (`succeeded|failed|rolled_back|
   cancelled`, `:992`) — in that case `migrate_pod` short-circuits to a replay
   result at `:1016-1017` without mutation, so the skip is safe. I am fairly
   confident, but a crafted `migration_id` colliding with a foreign terminal row
   could change which branch runs (see RISK).

2. **Claim: capture-helper seam keys match exactly.** Falsifier: a key the
   consumer requires that the producer omits. Producer omits nothing the consumer
   reads, but the producer never sends `args/cmd/command` (good — consumer rejects
   those, `:116-117`). I verified both ends; high confidence.

3. **Claim: rollback always restarts the source.** Falsifier: a path where
   `source_stopped` is False at rollback. If `stop` (`:1118`) throws,
   `source_stopped` stays False and `_rollback_lifecycle` skips the restart
   (`:639`). That is arguably correct (source never stopped) but means a partial
   stop that raised after side effects would not be restarted. Medium confidence
   this is intended.

4. **Claim: idempotency reserve prevents concurrent double-apply.** Falsifier: two
   `migrate_pod` calls racing past `reserve`. `reserve` uses INSERT OR IGNORE then
   reads back the row; the loser sees an existing `running` row but `replay` is
   only true for TERMINAL statuses (`:3329`), so a concurrent `running` row yields
   `replay=False` and BOTH proceed. There is no row-level lock. I believe this is
   a real concurrency gap (see RISK); flagged for Codex.

5. **Claim: `metadata_json` write at `:903` cannot leak secrets.** Falsifier: a
   provisioning intent that places a raw secret into `state_roots`. `state_roots`
   are filesystem paths from `render_arclink_state_roots`; unlikely to contain
   secrets, but this write bypasses `reject_secret_material`. Low-to-medium
   confidence it is fully safe.

## OPEN FOR CODEX FEDERATION

1. Concurrency: confirm whether two simultaneous `migrate_pod` invocations with
   the same `operation_key` but a `running` (non-terminal) idempotency row can
   both proceed past `reserve` (`:1006-1017`, control `:3314-3330`) and both run
   `stop`+capture. Is there any outer lock in the action worker (CANON-14) that
   serializes a given `operation_idempotency_key`?

2. Foreign-terminal collision: if an operator-supplied `migration_id` (or the
   `action_id`-derived id at `arclink_action_worker.py:1156`) collides with an
   existing terminal `arclink_pod_migrations` row for a DIFFERENT deployment,
   `plan_pod_migration` raises (`:326-327`) — but the terminal-skip at
   `migrate_pod:990-992` reads `existing.status` BEFORE `plan` re-binds. Trace
   whether the deployment-binding check actually fires first. (`migrate_pod` reads
   `existing` via `_migration_row` at `:989` then calls `plan_pod_migration` at
   `:996`, which re-checks binding — so the opt-in-skip uses the foreign row's
   status. Worth an independent read.)

3. Fail-open verifier: confirm `_default_verifier` returning `healthy=True` for a
   deployment with zero `arclink_service_health` rows (`:563-572`) is acceptable —
   i.e. that the target apply always seeds health rows before verification (it
   does not in this module; the executor/`_record_service_status_after_compose`
   lives in CANON-08's sovereign worker, NOT in the migration path).

4. Secret-bypass write at `:903` vs the `_json_dumps` discipline used elsewhere.

## RISKS (severity-ranked, code-cited)

- **HIGH — No mutual exclusion for concurrent migrations of the same deployment.**
  `reserve_arclink_operation_idempotency` only treats TERMINAL statuses as replay
  (`python/arclink_control.py:3329`); a concurrent `running` row returns
  `replay=False`, so two `migrate_pod` calls can both pass `:1013-1017` and both
  `stop` the source + capture concurrently (`:1118`, `:1129`). No row lock or
  `BEGIN IMMEDIATE` is taken in this module. `python/arclink_pod_migration.py:1006-1017`.

- **MEDIUM — `_default_verifier` is fail-open on empty health.** A target with no
  `arclink_service_health` rows is reported healthy (`not blockers` ->
  `healthy=True`), so a migration can be marked `succeeded` even if the target
  never registered service health. `python/arclink_pod_migration.py:563-572`.

- **MEDIUM — Capture cleanup only guarded by `.migrations` membership.**
  `_cleanup_rolled_back_capture` and GC `rmtree` a directory if `.migrations` is
  anywhere in `path.parts` (`:844-845`, `:1254-1258`); GC does NOT re-run
  `_validate_capture_paths`, so a stored `capture_dir` value (set at plan time and
  validated then) is trusted at GC time. If a row's `capture_dir` were ever
  altered to another `.migrations`-containing path, `rmtree` would follow it.
  `python/arclink_pod_migration.py:839-852`, `:1254-1258`.

- **MEDIUM — Symlinks in source state are silently dropped from the capture.**
  `_copy_capture` unlinks every symlink in the staged tree (`:442-444`), so
  migrated pods lose symlinks (and the manifest omits them). Materialize then
  copies a symlink-free tree. This is data loss on migration if the deployment
  relied on symlinks. `python/arclink_pod_migration.py:441-448`.

- **LOW — Success-path `metadata_json` write bypasses secret rejection.** Uses raw
  `json.dumps` instead of `_json_dumps`/`reject_secret_material`.
  `python/arclink_pod_migration.py:903`.

- **LOW — Rollback best-effort, errors swallowed into metadata.**
  `_rollback_lifecycle` catches all exceptions and records
  `{"status":"failed","error_type":...}` (`:637-638`, `:652-653`); a failed source
  restart is recorded but the migration still ends `rolled_back`, potentially
  leaving the source pod stopped. `python/arclink_pod_migration.py:610-654`.

- **INFO — Helper timeout floor.** `urlopen(..., timeout=max(5, timeout))`
  (`:509`) clamps below 5s; large captures rely on the 300s default.
  `python/arclink_pod_migration.py:494`, `:509`.

## VERDICT

This piece provably does its job for the single-operator, single-migration case:
it plans a deployment-scoped, idempotency-keyed migration; double-gates live
capture (root opt-in + Docker-mode helper); stops the source, captures with a
sha256 manifest and boundary tagging, renders a target provisioning intent,
ensures the per-deployment LLM router key, materializes, applies via the executor,
verifies service health, and on failure rolls back both the host lifecycle and the
control-plane placements while cleaning the capture dir. The capture wire seam to
CANON-12 is airtight because the helper imports this module's own copy/materialize
functions, and the executor and provisioning seams are dataclass/dict contracts I
verified at both ends. Load-bearing strengths: deployment-scoped path validation
(`_validate_capture_paths`), atomic flock'd router-secret write, terminal-status
idempotent replay, full audit/event trail. Real weaknesses: (1) no mutual
exclusion for concurrent same-deployment migrations — the idempotency reserve does
not block a concurrent `running` op; (2) the default verifier is fail-open on a
target that registered zero health rows; (3) symlinks are silently stripped from
captured state, which is a quiet data-fidelity loss; and (4) the prior ground-truth
doc's `ARCLINK_CAPTAIN_MIGRATION_ENABLED` gate is documentation only — no such
env check exists in this code. The happy path is well-built; the concurrency and
fail-open-verifier edges are where this piece is weakest.
