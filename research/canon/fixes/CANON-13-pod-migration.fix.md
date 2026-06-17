<<<CODEX-FIX-START CANON-13>>>
## CANON-13 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: python/arclink_pod_migration.py, tests/test_arclink_pod_migration.py, tests/test_arclink_action_worker.py
TESTS: 3 test files + py_compile run, all pass (`test_arclink_pod_migration.py`, `test_arclink_action_worker.py`, `test_arclink_schema.py`)
### Fixed (severity — what — path:line)
- HIGH — Added deployment-level active live migration exclusion plus same-ID running reentry guard, preventing concurrent split placements and double stop/capture. `python/arclink_pod_migration.py:236`, `python/arclink_pod_migration.py:368`, `python/arclink_pod_migration.py:970`
- HIGH — Default verifier now fails closed on missing/stale health and Docker apply status now gates success. `python/arclink_pod_migration.py:640`, `python/arclink_pod_migration.py:1043`, `python/arclink_pod_migration.py:1334`
- MEDIUM — Existing planned rows and post-capture execution recheck target host active/drain state. `python/arclink_pod_migration.py:378`, `python/arclink_pod_migration.py:998`, `python/arclink_pod_migration.py:1317`
- MEDIUM — GC revalidates stored `capture_dir` with the same capture-path validator before `rmtree`. `python/arclink_pod_migration.py:1439`
- MEDIUM — Symlinks are preserved in capture/materialize and represented in the manifest instead of silently unlinked. `python/arclink_pod_migration.py:507`
- MEDIUM — Materialization clears the target root before copying staged state, removing stale target contamination. `python/arclink_pod_migration.py:538`
- MEDIUM — Migration success and idempotency completion now commit atomically; service-health upsert is inline/no mid-success commit. `python/arclink_pod_migration.py:952`, `python/arclink_pod_migration.py:1055`, `python/arclink_pod_migration.py:1357`
- LOW — Invalid `ARCLINK_MIGRATION_GC_DAYS` is parsed before host mutation. `python/arclink_pod_migration.py:1030`, `python/arclink_pod_migration.py:1185`
- LOW — Success metadata write now uses the secret-rejecting serializer. `python/arclink_pod_migration.py:1102`
### Skipped (risk-accepted / standing / out-of-scope — why)
- GAP-019 trusted-host/root-equivalence and CANON-12 helper/broker boundary items were not changed; canon marks those as risk-accepted or out of CANON-13 scope.
- Helper timeout floor left unchanged; not a clear defect, and changing operator timeout semantics is not a safe quick win.
### NEEDS-DECISION (ambiguous; left for human)
- True target-host-scoped health verification needs a DB/wire contract change because `arclink_service_health` has no host/migration column. I fixed empty/stale fail-open by requiring fresh post-start health, but did not alter schema.
- Dry-run-to-live reuse of the same `migration_id` still needs a contract decision; fixing it cleanly changes idempotency-key semantics and dry-run planned-row promotion.
- Rollback lifecycle best-effort semantics left unchanged; changing `rolled_back` vs `failed` behavior on teardown/restart failure is a public status contract decision.
### Cross-piece edits made (if any) + tests added
- No cross-piece production code edits.
- Adjusted adjacent caller regression `tests/test_arclink_action_worker.py:1104` to seed fresh health for reprovision under the stricter verifier.
- Added CANON-13 regressions for fresh-health verification, default fail-closed rollback, active migration exclusion, running reentry, target recheck, guarded GC, early GC-days parsing, and atomic success/idempotency completion. `tests/test_arclink_pod_migration.py:604`
<<<CODEX-FIX-END CANON-13>>>
