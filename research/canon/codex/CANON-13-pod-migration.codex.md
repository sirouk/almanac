<<<CODEX-VERDICT-START CANON-13>>>
## CANON-13 — Codex (GPT-5.5 xhigh) ratification
SIGN-OFF: OBJECT(7)
ONE-LINE VERDICT: The piece is directionally correct, but ratification needs sharper risk scope: default verification is effectively non-verifying in production, GC is less guarded than both Claude passes fully state, and several stale-state/data-fidelity gaps remain.

### Adjudication (each: CONFIRM/REFUTE/REFINE + path:line)
- REFINE A9 / GC: verifier correctly refutes the record’s GC guard claim: GC does `Path(...).exists()` then `shutil.rmtree(capture_dir)` with no `.migrations`, absolute/root, or re-validation guard. `python/arclink_pod_migration.py:1254-1258`
- REFINE A9 nuance: rollback cleanup also does not have “all three” guards; it only checks `".migrations" in path.parts`. The earlier live path validates capture shape before mutation, but `_cleanup_rolled_back_capture` itself is not root/absolute/revalidate guarded. `python/arclink_pod_migration.py:839-845`, `python/arclink_pod_migration.py:1018-1019`
- CONFIRM B30 / same-key concurrency: `reserve_arclink_operation_idempotency` sets replay only for terminal `succeeded|failed`; an existing `running` row returns `replay=False`, so `migrate_pod` proceeds. `python/arclink_control.py:3207-3208`, `python/arclink_control.py:3314-3330`, `python/arclink_pod_migration.py:1006-1017`
- REFINE B30 scope: the shipped worker loop is serial in one process, but this is topology, not a migration lock; distinct reprovision actions derive distinct migration IDs/keys and bypass idempotency entirely. `python/arclink_action_worker.py:666-676`, `python/arclink_action_worker.py:1154-1157`, `compose.yaml:732-764`
- REFINE HIGH concurrency risk: two distinct concurrent migrations can leave placement state split because success only removes the row’s original source placement and activates that row’s target; it does not deactivate other active placements for the deployment. `python/arclink_pod_migration.py:867-885`
- REFINE C50 / fail-open severity: raise to HIGH when default verifier is used. Action worker passes no verifier, `docker_compose_apply` only returns `status="applied"`, and success gates only on `verification["healthy"]`; `docker_status` is recorded but ignored. `python/arclink_action_worker.py:1169-1178`, `python/arclink_executor.py:890-947`, `python/arclink_pod_migration.py:1154-1156`
- CONFIRM fail-open mechanism: empty health rows produce `blockers={}` and `healthy=True`. `python/arclink_pod_migration.py:563-572`
- CONFIRM symlink loss: capture copies symlinks, then unlinks every symlink before manifest/materialize; helper imports the same functions, so Docker helper behavior matches. `python/arclink_pod_migration.py:430-448`, `python/arclink_pod_migration.py:462-466`, `python/arclink_migration_capture_helper.py:22-27`
- CONFIRM CANON-12 seam: producer posts `/v1/migration-capture` with the shared token header and exact body keys; helper validates those keys and returns `{ok,result}`. `python/arclink_pod_migration.py:497-531`, `python/arclink_migration_capture_helper.py:115-126`, `python/arclink_migration_capture_helper.py:252-278`
- CONFIRM CANON-08 seam refinement: `llm_router_api_key` is absent in direct-chutes mode; migration handles absence by returning early. `python/arclink_provisioning.py:650-665`, `python/arclink_pod_migration.py:736-739`
- CONFIRM CANON-11 seam: lifecycle/apply request shapes match executor validation and action allowlist. `python/arclink_pod_migration.py:583-599`, `python/arclink_executor.py:343-350`, `python/arclink_executor.py:949-953`, `python/arclink_executor.py:1835-1846`
- REFINE CANON-14 seam: worker accepts `status=="planned"` for dry-run, not only `succeeded`. `python/arclink_action_worker.py:1166-1180`
- CONFIRM LOW secret-serializer drift: success metadata uses raw `json.dumps`, bypassing `_json_dumps`/`reject_secret_material`. `python/arclink_pod_migration.py:73-74`, `python/arclink_pod_migration.py:887-903`, `python/arclink_boundary.py:65-73`
- CONFIRM rollback best-effort: rollback lifecycle swallows teardown/restart exceptions into metadata. `python/arclink_pod_migration.py:610-654`
- CONFIRM dry-run/live same-ID footgun: `dry_run` is part of the idempotency intent, so reusing the same migration ID across dry-run and live binds a different digest and errors. `python/arclink_pod_migration.py:400-410`, `python/arclink_control.py:3294-3296`

### New findings both Claude passes missed (severity + path:line)
- HIGH: default verifier also trusts stale pre-migration health, not just empty health; `arclink_service_health` is keyed only by deployment/service, verifier ignores `checked_at` and target host, and production caller injects no verifier. `python/arclink_control.py:1224-1230`, `python/arclink_pod_migration.py:563-572`, `python/arclink_action_worker.py:1169-1178`
- MEDIUM: existing planned migration rows bypass target availability re-check; target `active && !drain` is checked only when creating a new row, while existing rows return before that validation. `python/arclink_pod_migration.py:324-344`, `python/arclink_pod_migration.py:1136-1147`
- MEDIUM: materialization overlays the target root with `dirs_exist_ok=True` and never clears stale target files, so a prior failed/partial target root can contaminate the migrated pod. `python/arclink_pod_migration.py:462-466`
- MEDIUM: success is not atomic with idempotency completion; `_mark_success` commits before `complete_arclink_operation_idempotency`, and `upsert_arclink_service_health` commits mid-success. Crash/exception can leave migration `succeeded` with operation idempotency still `running` or later failed. `python/arclink_pod_migration.py:925-954`, `python/arclink_control.py:4674-4695`, `python/arclink_pod_migration.py:1188-1196`
- LOW: invalid `ARCLINK_MIGRATION_GC_DAYS` raises after target apply and verification, sending an otherwise-applied migration into rollback. `python/arclink_pod_migration.py:1177-1179`, `python/arclink_pod_migration.py:1198-1215`

### Claude citations re-confirmed or corrected
- Re-confirmed schema/status contract for `arclink_pod_migrations`. `python/arclink_control.py:1451-1474`
- Re-confirmed no `ARCLINK_CAPTAIN_MIGRATION_ENABLED` code gate in the migration path; real live gate is root opt-in plus Docker helper requirement. `python/arclink_pod_migration.py:990-995`
- Corrected record/verifier wording: GC has no guard; rollback cleanup has only a `.migrations` membership guard, with stronger validation occurring earlier in the live path. `python/arclink_pod_migration.py:160-185`, `python/arclink_pod_migration.py:839-845`, `python/arclink_pod_migration.py:1254-1258`
- Re-confirmed helper timeout clamp and static helper request shape. `python/arclink_pod_migration.py:493-510`

### Residual disagreement with the Claude half (for final reconciliation)
- I would classify the default verifier as HIGH in the production action-worker path, not MEDIUM, because no injected verifier is supplied and stale/empty health both pass. `python/arclink_action_worker.py:1169-1178`, `python/arclink_pod_migration.py:563-572`
- The final CANON text should not say rollback cleanup has root/absolute/revalidation guards; only the pre-mutation validation path does. `python/arclink_pod_migration.py:160-185`, `python/arclink_pod_migration.py:839-845`
<<<CODEX-VERDICT-END CANON-13>>>
