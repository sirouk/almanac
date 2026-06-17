# CANON-13 — Pod Migration — ADVERSARIAL VERIFY

Verifier: independent Opus 4.8 adversarial skeptic.
Target: `python/arclink_pod_migration.py` (1275 lines, re-read in full).
Record under test: `research/canon/sections/CANON-13-pod-migration.md`.
Method: every load-bearing claim re-opened at path:line; both ends of every
both-ends-verified seam re-read; unhappy paths and silent no-ops hunted.

## VERDICT (one line)
TRUSTWORTHY WITH CORRECTIONS. The record's architecture, seams, and three named
weaknesses (concurrency, fail-open verifier, symlink loss) are real and
code-confirmed. But the record contains one material FACTUAL ERROR about the GC
cleanup guard that makes the GC path sound safer than it is, mis-states the
CANON-14 result-check guard, and omits several genuine gaps. Net: the document is
usable but needs the GC correction landed and three new gaps added.

---

## REFUTATIONS / CONFIRMATIONS (claim-by-claim)

### R1 — REFUTED (factual error): GC does NOT have the `.migrations` guard the record attributes to it
Record OUTPUT-CONTRACT lines 126-127: "`_cleanup_rolled_back_capture` (`:839`) and
GC (`:1256-1258`): `shutil.rmtree` of the capture dir, guarded by `.migrations`
being in path parts (`:844-845`)." Record RISKS lines 417-423 repeats: GC `rmtree`s
"if `.migrations` is anywhere in `path.parts` (`:844-845`, `:1254-1258`)".

CODE: `garbage_collect_pod_migrations` lines 1254-1258 does:
```
capture_dir = Path(str(row.get("capture_dir") or ""))
if remove_artifacts and capture_dir.exists():
    shutil.rmtree(capture_dir)
```
There is NO `.migrations`-membership check, NO `_validate_capture_paths`, NO
`_absolute_path` guard, NO filesystem-root guard. The `.migrations` guard lives
ONLY in `_cleanup_rolled_back_capture` line 844 (`if ".migrations" not in
path.parts`), which is the ROLLBACK path, not GC. The record conflates the two.
Consequence: the GC path is strictly LESS guarded than the record claims — it
`rmtree`s whatever string is in `capture_dir` (even `/`, even an empty-becomes-`.`
path is blocked only by `.exists()`). Exploit requires DB row tampering (capture_dir
is written + validated at plan time), so still bounded, but the record's "guarded by
`.migrations`" wording is wrong. Cite: `python/arclink_pod_migration.py:1254-1258`
vs `:844-845`.

### R2 — PARTIALLY REFUTED: CANON-14 result guard is mis-stated
Record CODE-PATH-TRACE step 15 (lines 233-234) and CROSS-PIECE #4: "action worker
checks `result.status == "succeeded"` else raises `ArcLinkActionWorkerError`
(`:1179-1180`)." Actual code `python/arclink_action_worker.py:1179`:
```
if str(result.get("status") or "") != "succeeded" and not (dry_run and str(result.get("status") or "") == "planned"):
    raise ArcLinkActionWorkerError(...)
```
The guard ALSO accepts `status == "planned"` when `dry_run` is true. The record's
flat "checks succeeded else raises" omits the dry-run branch. Not a safety bug, but
the seam description is incomplete; a dry-run migration legitimately returns a
non-`succeeded` status that the worker accepts.

### R3 — CONFIRMED: HIGH concurrency risk is real, but topology context is missing (severity defensible, exposure understated AND overstated in different ways)
Record RISKS "HIGH — No mutual exclusion": `reserve_arclink_operation_idempotency`
only treats TERMINAL statuses as replay. CONFIRMED in code:
`python/arclink_control.py:3329` `result["replay"] = status in TERMINAL`, and
`ARCLINK_OPERATION_IDEMPOTENCY_TERMINAL_STATUSES = {"succeeded", "failed"}`
(`:3208`). A concurrent `running` row → `replay=False` → both proceed past
`migrate_pod:1013-1017`. No `BEGIN IMMEDIATE` / row lock in `arclink_pod_migration.py`.

BUT two corrections the record missed, in opposite directions:
(a) MITIGATION the record never states: the only caller is the action worker, which
    runs a SINGLE worker loop (`arclink_action_worker.py:2395-2418`, one `worker_id`,
    one connection) processing actions SERIALLY via `process_arclink_action_batch`
    (`:666-676` for-loop) and claiming each action under `BEGIN IMMEDIATE`
    (`_claim_next_queued_action:456`). In the shipped single-worker topology,
    migrations are serialized in practice — so the HIGH is a latent code gap, not a
    live exploit, and the record should say so.
(b) BROADER exposure the record never states: the idempotency key is
    `arclink:migration:<migration_id>` and migration_id is derived from `action_id`
    (`arclink_action_worker.py:1156`). TWO DISTINCT reprovision actions for the SAME
    deployment produce DIFFERENT migration_ids → DIFFERENT operation_keys →
    idempotency gives ZERO protection. There is no lock on `arclink_pod_migrations`
    or on the deployment placement. So the real concurrency surface is "two distinct
    migration actions for one deployment," which is WORSE than the record's
    "same operation_key" framing and which idempotency cannot cover by design.
Net: HIGH severity stands; the record's analysis is narrower than the actual gap.

### R4 — CONFIRMED: MEDIUM fail-open verifier, and arguably UNDER-calibrated
Record RISKS "MEDIUM — `_default_verifier` is fail-open on empty health"
(`:563-572`). CONFIRMED: empty rows → `blockers={}` → `healthy=True` (line 572).
I additionally verified the upstream claim the record only asserts in OPEN #3:
`executor.docker_compose_apply` (`python/arclink_executor.py:890-947`) does NOT
write ANY `arclink_service_health` row — it runs `docker compose up -d` and returns
`status="applied"`. So on the migration path nothing seeds health before
verification, making fail-open the DEFAULT outcome, not an edge. Worse:
`verification["docker_status"] = docker_result.status` (`:1155`) is CAPTURED but
NEVER compared to `"applied"` — a non-applied/degraded docker result does not by
itself fail the migration; only `verification["healthy"]` gates success (`:1156`).
The MEDIUM is defensible-to-low-end-of-HIGH. Confirmed real.

### R5 — CONFIRMED: symlink data loss (MEDIUM)
`_copy_capture` lines 441-444 unlink every symlink in the staged tree; manifest omits
them (`:447-458`); `_materialize_capture` (`:462-466`) copies the symlink-free tree.
CONFIRMED. Note the helper path is identical because the helper imports the SAME
`_copy_capture`/`_materialize_capture` (`arclink_migration_capture_helper.py:22-27`),
so the loss is uniform across in-process and Docker modes. Real.

### R6 — CONFIRMED: DRIFT #1 (`ARCLINK_CAPTAIN_MIGRATION_ENABLED` is doc-only)
`rg` over `python/` finds ZERO reads of `ARCLINK_CAPTAIN_MIGRATION_ENABLED`; it
appears only in `docs/` and `research/`. CONFIRMED. The real gate is the double
opt-in (`:990-995`) plus single-caller-is-operator-action. Record correct.

### R7 — CONFIRMED: double opt-in gate placement
`_require_root_capture_opt_in` (`:103-112`) + `_migration_capture_helper_config(...,
require_for_docker=True)` (`:130-134`) run at `:994-995`, BEFORE `plan_pod_migration`
and BEFORE the `stop` at `:1118`, and ONLY when not dry-run AND not terminal-existing
(`:990-993`). CONFIRMED. The terminal-skip short-circuits to a replay result at
`:1016-1017` with no mutation, so the skip is safe. Record correct.

### R8 — CONFIRMED + EXTENDED: executor seam (CANON-11)
`DockerComposeLifecycleRequest.action` restricted to `{stop,restart,inspect,teardown}`
at `python/arclink_executor.py:952`; this module only sends `stop|restart|teardown`.
Lifecycle file validation `env == <config>/arclink.env`, `compose == <config>/
compose.yaml` at `:1843-1846`; this module's `_deployment_lifecycle_files` (`:583-589`)
and `_intent_lifecycle_files` (`:592-599`) build exactly those. CONFIRMED both ends.

### R9 — CONFIRMED with nuance: provisioning seam (CANON-08)
`render_arclink_state_roots` returns `{"root": ...}` (`python/arclink_provisioning.py:407`);
`render_arclink_provisioning_intent` returns `state_roots` (`:1711`) and `secret_refs`
(`:1713`). NUANCE the record missed: `secret_refs.llm_router_api_key` is present ONLY
when NOT direct-chutes — `_render_secret_refs` (`:650-665`) emits EITHER
`chutes_api_key` (direct_chutes) OR `llm_router_api_key`, never both. In direct-chutes
mode `_ensure_llm_router_key_for_intent` reads `.get("llm_router_api_key")` → "" →
returns None at `:738` (silent skip). The read is null-safe so no crash, but the
record's "intent's `secret_refs.llm_router_api_key`" presented as always-present is
incomplete. Confirmed safe, seam description incomplete.

### R10 — CONFIRMED: capture-helper wire seam keys (CANON-12)
Producer body keys: `deployment_id, prefix, migration_id, source_state_root,
target_state_root, capture_dir` (`_migration_capture_helper_payload:469-478`) +
`operation` (`:498`). Consumer reads exactly those in `_validate_request`
(`arclink_migration_capture_helper.py:115-126`). Auth header constant
`MIGRATION_CAPTURE_HELPER_TOKEN_HEADER` imported FROM this module by the helper
(`:23`), compared with `hmac.compare_digest` (`:57`). Producer sends none of the
rejected `args/cmd/command` keys. Success `{"ok":True,"result":...}` (`:276`) read at
producer `:523-531`. CONFIRMED both ends. (Replay/static-token concern is CANON-12's;
out of scope here — see N4.)

---

## NEW GAPS (neither record nor prior docs mention)

### G1 — MEDIUM: GC `rmtree` has NO path-shape guard at all (see R1)
`garbage_collect_pod_migrations:1254-1258` `rmtree`s the stored `capture_dir` with
only an `.exists()` check — no `.migrations` membership, no `_absolute_path`, no
filesystem-root rejection, no re-validation. The rollback cleanup (`:839-852`) has
all three guards; GC has none. The record claimed GC shared the `.migrations` guard
(R1), so this is an UNGUARDED-rmtree gap the record actively hid.

### G2 — LOW/INFO: dry-run-then-live with same migration_id hard-errors (intent digest footgun)
`_operation_intent` embeds `dry_run` (`:409`), so a dry-run reserve writes an
intent_digest different from the live reserve's. A subsequent live `migrate_pod` with
the SAME migration_id hits `_require_matching_operation_intent`
(`arclink_control.py:3294-3296`) → raises "already bound to another intent." The
action worker avoids this by deriving distinct ids from distinct action_ids, but an
operator passing an explicit `metadata.migration_id` for both a dry-run and a live run
gets a hard, opaque failure rather than a clean transition. Usability footgun, not a
safety hole. Cite: `:1005`, `:409`, `arclink_control.py:3325/3294`.

### G3 — LOW: `docker_status` captured but never gates success
`verification["docker_status"] = docker_result.status` (`:1155`) is recorded into the
verification blob but is NEVER compared against `"applied"`. Success is decided solely
by `verification["healthy"]` (`:1156`), which the default verifier derives from health
rows that apply never wrote (R4). So a docker apply that returned a non-`"applied"`
status would not, on its own, fail the migration. Cite: `:1155-1156` +
`arclink_executor.py:933`.

### G4 — INFO: GC runs every worker iteration with `remove_artifacts=True` and no
per-row safety re-check
`run_pod_migration_gc` (`arclink_action_worker.py:2298-2299`) calls GC with defaults
every loop tick (`:2408`). Combined with G1, GC is a recurring unguarded-`rmtree`
driver. Bounded today by the plan-time validation of `capture_dir`, but there is no
defense-in-depth at GC time.

### G5 — INFO: `_rollback_lifecycle` only restarts source when `source_stopped` is True
Confirmed the record's self-check #3: if `stop` (`:1118`) raises, `source_stopped`
stays False and the rollback skips the restart (`:639`). A `stop` that partially
mutated host state before raising would leave the source down with no restart attempt.
The record flagged this at "medium confidence"; I confirm the code path
(`:1116-1127`, `:639-653`). Real but low-likelihood.

---

## SEAM MISMATCHES
- CANON-08 seam: `secret_refs.llm_router_api_key` is conditionally ABSENT
  (direct-chutes mode); record presents it as always-present. Null-safe, no crash.
  Cite: `arclink_provisioning.py:657-665` vs `arclink_pod_migration.py:736-738`.
- CANON-14 seam: result guard accepts `planned` in dry-run, not only `succeeded`
  (R2). Cite: `arclink_action_worker.py:1179`.
- No producer/consumer BYTE mismatch found on the capture-helper wire seam (R10) —
  that seam is sound.

## NOTES / OUT-OF-SCOPE
- N4: capture helper uses a static shared token with no nonce/timestamp/replay
  window (`arclink_migration_capture_helper.py:54-57`); replayable by anyone who can
  reach 127.0.0.1:8914 with the token. This is CANON-12's contract, not this
  record's, so it is not charged against CANON-13. The record's "airtight" wording
  refers to key-shape matching, which holds.

## RISK RE-CALIBRATION SUMMARY
- HIGH (concurrency): KEEP. Add single-worker mitigation note + broader
  distinct-action exposure (R3).
- MEDIUM (fail-open verifier): KEEP, lean toward upper bound; apply never seeds
  health and docker_status is ignored (R4, G3).
- MEDIUM (capture cleanup guard): RE-STATE. The record's premise (GC shares the
  `.migrations` guard) is FALSE; GC has NO guard (R1/G1). Severity of the underlying
  rmtree exposure is bounded by plan-time validation, so MEDIUM still fits, but the
  CITED MECHANISM in the record is wrong and must be corrected.
- MEDIUM (symlink loss): KEEP (R5).
- LOW (metadata_json raw json.dumps at :903): KEEP, confirmed `json.dumps(...,
  sort_keys=True)` bypasses `_json_dumps`/`reject_secret_material`.
- LOW (rollback best-effort): KEEP (G5).

## OVERALL
The record is substantially correct and its three headline weaknesses are real and
reproducible in code. It is downgraded from "airtight" because of ONE concrete
factual error (R1/G1: the GC `.migrations` guard does not exist) plus an inaccurate
CANON-14 guard description (R2) and an incomplete CANON-08 seam description (R9). With
the GC correction and the five new gaps folded in, the record is trustworthy.
