# CANON-13 — Pod Migration — RECONCILED (both-model truth)

Module under reconciliation: `python/arclink_pod_migration.py` (1275 lines).
Adjudicator: Claude Opus 4.8 (final), code re-opened independently per disputed point.
Inputs reconciled:
- Claude record:   `research/canon/sections/CANON-13-pod-migration.md`
- Claude verify:   `research/canon/verify/CANON-13-pod-migration.verify.md`
- Codex verdict:   `research/canon/codex/CANON-13-pod-migration.codex.md`

## SIGN-OFF HEADER
- Codex sign-off: **OBJECT(7)** (directionally correct; objects on risk scope — verifier non-verifying in prod, GC less guarded than stated, stale-state/data-fidelity gaps).
- Federation sign-off: **AGREED-WITH-STANDING-DISAGREEMENTS** — every material point reconciled to one code-grounded truth and all five Codex new findings adjudicated; the only residual item is a *wording-precision* standing note about the rollback-cleanup guard (both models actually agree on the code; they disagree on how a prior sentence was phrased). No factual conflict remains unresolved.

Method note: I did not trust either model's cite. Every REFUTE/REFINE/new-finding below was re-opened with Read at the exact path:line and decided by what the code does. Code beats name/comment/prior claim.

---

## RESOLUTION TABLE (disputed + refined points)

| Point | Winner | Deciding cite (my own read) |
|---|---|---|
| R1/G1 — GC `rmtree` has the `.migrations` guard (record's claim) | **claude-verify + codex** (record WRONG) | GC `:1254-1258` = `Path(...).exists()` then `shutil.rmtree` only; the `.migrations` guard exists ONLY in `_cleanup_rolled_back_capture` `:844`. Record's OUTPUT `:126-127` and RISK `:417-423` conflate them. |
| R2 — CANON-14 guard is "succeeded else raises" | **claude-verify + codex** (record incomplete) | `arclink_action_worker.py:1179` also accepts `status=="planned"` when `dry_run`. Record's flat phrasing omits the dry-run branch. |
| B30 — same-key concurrency: `running` row → both proceed | **both (agree)** | `arclink_control.py:3207-3208,3345-3348`; `replay` only for terminal; `migrate_pod:1013-1017` proceeds on non-terminal. No row lock in module. |
| R3(a) — single-worker serial mitigation (record omitted) | **claude-verify + codex** (add to record) | `arclink_action_worker.py:652-676` serial batch loop; `:456` claims under `BEGIN IMMEDIATE`; GC at `:2408` single worker_id. Live exploit is latent, not active. |
| R3(b)/B30-scope — distinct actions → distinct migration_ids → idempotency gives ZERO protection | **claude-verify + codex** (broader than record) | `arclink_action_worker.py:1154-1157` mints `mig_<sha256(action_id)>`; two reprovision actions = two keys = no shared idempotency. |
| Placement-split on concurrent distinct migrations (Codex REFINE) | **codex** | `_mark_success:869-885` flips only the row's OWN source/target placement; never deactivates other active placements for the deployment. |
| C50 / fail-open verifier severity MEDIUM vs HIGH | **codex (HIGH in prod path)** | Worker injects no verifier `:1169-1178`; `docker_compose_apply` writes NO health, returns `status="applied"` `executor.py:929-947`; `_default_verifier:563-572` reads `WHERE deployment_id`; `docker_status` recorded but never gated `:1155-1156`. Default verifier is effectively non-verifying. |
| Fail-open mechanism: empty health → healthy | **both (agree)** | `:567-572` `blockers={}` → `healthy=True`. |
| Symlink loss uniform across in-proc + Docker | **both (agree)** | `_copy_capture:441-448` unlinks symlinks; `_materialize_capture:462-466`; helper imports same fns `arclink_migration_capture_helper.py:22-27`. |
| CANON-12 wire seam keys match | **both (agree)** | producer `:497-531` / consumer `arclink_migration_capture_helper.py:115-126,252-278`. |
| CANON-08 `llm_router_api_key` conditionally absent (direct-chutes) | **both (agree)** | `arclink_provisioning.py:650-665` EITHER/OR; `_ensure_llm_router_key_for_intent:736-739` null-safe early return. Record presented as always-present (incomplete, not wrong). |
| CANON-11 executor request shapes/allowlist | **both (agree)** | `:583-599` vs `executor.py:343-350,949-953,1835-1846`. |
| Dry-run/live same-id intent-digest footgun | **both (agree)** | `_operation_intent:400-410` embeds `dry_run`; `arclink_control.py:3294-3296` raises on digest mismatch. |
| LOW raw-`json.dumps` metadata bypass | **both (agree)** | `:903` `json.dumps(...,sort_keys=True)` vs `_json_dumps`/`reject_secret_material` `boundary.py:65-73`. |
| Rollback best-effort swallows errors | **both (agree)** | `_rollback_lifecycle:637-638,652-653`. |
| G5 — rollback restarts source only if `source_stopped` | **both (agree)** | `:639`; `source_stopped` set True only at `:1127` after `stop` returns; `stop` raising at `:1118` skips restart. |
| Captain env-var gate is code | **both (agree, doc WRONG)** | zero reads of `ARCLINK_CAPTAIN_MIGRATION_ENABLED` in `python/`; only `docs/`+`research/`. Real gate = double opt-in `:990-995` + operator-only caller. |

---

## CODEX NEW FINDINGS — CONFIRMED vs REJECTED

All five re-opened in code; all CONFIRMED. Net-new federation risks:

1. **CONFIRMED — HIGH: default verifier trusts STALE pre-migration health, not just empty.**
   `arclink_service_health` PRIMARY KEY is `(deployment_id, service_name)` (`arclink_control.py:1230`); no host or migration column. `_default_verifier` queries `WHERE deployment_id = ?` and ignores `checked_at` and target host (`:563-572`). The production caller injects no verifier (`arclink_action_worker.py:1169-1178`), and apply seeds no fresh health (`executor.py:929-947`). So pre-existing healthy rows from the SOURCE pod survive into verification of the NEW target. This is a distinct mechanism from the record's "empty health" framing and is the stronger statement of why the verifier is non-verifying in prod.

2. **CONFIRMED — MEDIUM: existing planned rows bypass target availability re-check.**
   `plan_pod_migration` returns an existing row at `:332` BEFORE the `active && !drain` check at `:343-344`; `migrate_pod` then re-renders intent and applies at `:1136-1147` without re-validating. Window: target drained between plan and migrate. Real, bounded by the plan-time check.

3. **CONFIRMED — MEDIUM: materialize overlays target root, never clears stale files.**
   `_materialize_capture:462-466` uses `copytree(..., dirs_exist_ok=True)`; no pre-clear. A prior failed/partial target root can contaminate the migrated pod (most acute for redeploy-in-place where the root pre-exists).

4. **CONFIRMED — MEDIUM: success not atomic with idempotency completion.**
   `_mark_success` commits at `:954`; `upsert_arclink_service_health` itself commits at `arclink_control.py:4695` (mid-success); `complete_arclink_operation_idempotency` commits separately at `:3393` (called at `:1189`). A crash between leaves migration `succeeded` with idempotency still `running` (non-terminal → next reserve gives `replay=False` → re-execution possible).

5. **CONFIRMED — LOW: invalid `ARCLINK_MIGRATION_GC_DAYS` rolls back an applied migration.**
   `int(str(...))` at `:1177-1179` runs INSIDE the try AFTER apply (`:1147`) and verification (`:1154`); a non-int env value raises `ValueError`, caught at `:1198`, dragging an otherwise-applied migration into rollback.

REJECTED: none. (No Codex new finding failed re-verification.)

---

## SEVERITY CHANGES (code-supported only)

| Risk | From | To | Deciding cite |
|---|---|---|---|
| Fail-open verifier (prod action-worker path) | MEDIUM | **HIGH** | No verifier injected `arclink_action_worker.py:1169-1178`; apply writes no health, returns `status="applied"` `executor.py:929-947`; `_default_verifier` reads only `(deployment_id)` rows `:563-572`; `docker_status` ungated `:1155-1156`. In prod the default verifier is effectively non-verifying — promotes from edge to default outcome. |
| "Capture cleanup guarded by `.migrations`" (record framing) | MEDIUM (mis-cited mechanism) | **MEDIUM (mechanism corrected)** | Severity unchanged; the CITED MECHANISM is wrong — GC has NO guard (`:1254-1258`); only rollback cleanup checks `.migrations` membership (`:844`). Underlying rmtree exposure stays MEDIUM, bounded by plan-time `_validate_capture_paths` (`:160-185`) writing/validating `capture_dir`. |

Net-new severities introduced by Codex findings: one HIGH (stale-health, reinforces the verifier HIGH), three MEDIUM (availability bypass, materialize overlay, non-atomic success), one LOW (GC_DAYS).

All other record severities stand as-is: HIGH concurrency (KEEP, with single-worker mitigation + distinct-action broadening); MEDIUM symlink loss (KEEP); LOW metadata raw-dumps (KEEP); LOW rollback best-effort (KEEP); INFO helper-timeout floor (KEEP).

---

## STANDING DISAGREEMENTS

1. **Rollback-cleanup guard wording (precision-only, no code conflict).**
   - Claude view (verify G1): the rollback cleanup `_cleanup_rolled_back_capture` "has all three guards" (`.migrations` + `_absolute_path` + root-rejection) which GC lacks.
   - Codex view: rollback cleanup has ONLY the `.migrations`-membership guard (`:839-845`); the absolute/root/revalidation strength lives in the PRE-MUTATION path `_validate_capture_paths` (`:160-185`, invoked at `:1018-1019`), not in the cleanup function itself.
   - My code read: **Codex is right on the literal code.** `_cleanup_rolled_back_capture:839-852` contains exactly one shape guard — `if ".migrations" not in path.parts` (`:844`). The stronger guards are in `_validate_capture_paths`, a different function run before mutation. The verify pass overstated the cleanup function's own guards.
   - Why "standing" rather than a clean win: this is not a factual dispute about behavior — both passes agree GC is unguarded and that strong validation happens earlier in the live path. It is a wording correction the final CANON text must adopt (do NOT say rollback cleanup is root/absolute/revalidate-guarded; say only the pre-mutation validation path is). Recorded so the signed line cannot be mis-cited later.

No other point is unsettleable from code; everything else reconciled to a single winner above.

---

## FINAL BOTH-MODEL VERDICT

CANON-13 provably does its core job for the single-operator, single-migration happy path: deployment-scoped, idempotency-keyed plan; double-gated live capture (root opt-in + Docker helper); stop-source → sha256/boundary capture → render target intent → ensure per-deployment LLM router key → materialize → executor apply → verify → success-or-rollback with placement/observed_load bookkeeping and a full audit/event trail. The CANON-08/11/12/14 and control-plane seams are dataclass/dict/wire contracts verified at both ends.

The reconciled weakness set (code-grounded, both models agreed):
- **HIGH — production verification is effectively non-verifying.** Default verifier reads `(deployment_id)`-keyed health that apply never seeds, accepts both empty AND stale source health as `healthy`, and ignores the captured `docker_status`. Severity raised MEDIUM→HIGH for the shipped (no-injected-verifier) path.
- **HIGH — no mutual exclusion for concurrent migrations.** Idempotency only blocks terminal-status replays; two distinct reprovision actions for one deployment use distinct keys and share no lock; success only flips the row's own placement, so concurrent runs can split placement state. Latent today because the action worker runs a single serial loop under `BEGIN IMMEDIATE`.
- **MEDIUM — GC `rmtree` is UNGUARDED** (`.exists()` only); the record's "`.migrations`-guarded GC" claim is a factual error, corrected here. Bounded by plan-time `capture_dir` validation.
- **MEDIUM — symlink data loss**, **MEDIUM — existing-row availability bypass**, **MEDIUM — materialize overlay never clears stale target files**, **MEDIUM — success/idempotency non-atomicity**.
- **LOW** — raw-`json.dumps` metadata bypass, rollback best-effort error-swallow, invalid `ARCLINK_MIGRATION_GC_DAYS` rolls back an applied migration. **INFO** — helper timeout floor.
- **DOC DRIFT** — `ARCLINK_CAPTAIN_MIGRATION_ENABLED` is documentation-only; no such code gate exists. Real gate = double opt-in + operator-only caller.

Federation status: **AGREED-WITH-STANDING-DISAGREEMENTS** — one wording-precision standing note (rollback-cleanup guard phrasing); zero unresolved factual conflicts. This is the line both models sign.

---

<!-- CANON-REPAIR-STATUS:START -->
## Repair status

> Refreshed from [`research/canon/fixes/CANON-13-pod-migration.fix.md`](../fixes/CANON-13-pod-migration.fix.md) (tracked). The audit findings above remain the adjudicated spec; this block records the repair campaign state for this piece.

- Status: `c5cec97` committed.
- Summary: 9 fixed / 2 skipped / 3 needs-decision.
- Tests: 3 test files + py_compile run, all pass (`test_arclink_pod_migration.py`, `test_arclink_action_worker.py`, `test_arclink_schema.py`)
- Representative fixes:
  - HIGH — Added deployment-level active live migration exclusion plus same-ID running reentry guard, preventing concurrent split placements and double stop/capture. `python/arclink_pod_migration.py:236`, `python/arclink_pod_migration.py:368`, `python/arclink_pod_migration.py:970`
  - HIGH — Default verifier now fails closed on missing/stale health and Docker apply status now gates success. `python/arclink_pod_migration.py:640`, `python/arclink_pod_migration.py:1043`, `python/arclink_pod_migration.py:1334`
  - MEDIUM — Existing planned rows and post-capture execution recheck target host active/drain state. `python/arclink_pod_migration.py:378`, `python/arclink_pod_migration.py:998`, `python/arclink_pod_migration.py:1317`
- Needs decision:
  - True target-host-scoped health verification needs a DB/wire contract change because `arclink_service_health` has no host/migration column. I fixed empty/stale fail-open by requiring fresh post-start health, but did not alter schema.
  - Dry-run-to-live reuse of the same `migration_id` still needs a contract decision; fixing it cleanly changes idempotency-key semantics and dry-run planned-row promotion.
  - Rollback lifecycle best-effort semantics left unchanged; changing `rolled_back` vs `failed` behavior on teardown/restart failure is a public status contract decision.
<!-- CANON-REPAIR-STATUS:END -->
