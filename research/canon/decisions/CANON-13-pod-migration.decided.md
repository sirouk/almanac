# CANON-13 — Pod Migration — DECIDED (final adjudication)

Adjudicator: Claude Opus 4.8 (final), DECISION mode.
Federation peer proposal: `research/canon/decisions/CANON-13-pod-migration.codex.md` (GPT-5.5 xhigh).
Module under decision: `python/arclink_pod_migration.py` (1461 lines, post-repair `c5cec97`).
North Star: `docs/arclink/sovereign-control-node-symphony.md`.

Method note: I re-opened the *current* code (not the pre-repair audit snapshot) at each
cite. The repair campaign already landed real changes that shift the baseline for all
three decisions, so I anchor to what the code does **today**:
- `_default_verifier` now requires **fresh** health (`checked_at >= migration.updated_at`)
  and treats zero rows as `missing` → fail-closed (`python/arclink_pod_migration.py:640-669`).
- A `_apply_docker_status_gate` now forces `healthy=False` unless `docker_compose_apply`
  returned `applied` (`:1043-1052`, wired `:1335`).
- GC now **re-runs** `_validate_capture_paths` and `.resolve(strict=False)` before any
  `rmtree` (`:1439-1443`) — the audit's "unguarded GC rmtree" is already fixed.
- `arclink_pod_migrations` already carries a `target_host_metadata_json` column and the
  status CHECK already includes `failed` (`python/arclink_control.py:1538,1543`).
- The `pod-migration` health row the migration writes is **self-attested**: status is
  hardcoded `'healthy'`, keyed `(deployment_id, service_name)` with no host column
  (`_record_pod_migration_health`, `:952-967`; schema `python/arclink_control.py:1300-1307`).

That last point is the live crux of Decision 1 and survives the repair.

---

## DECISION 1 — Target-host-scoped health verification — [VERDICT: refine]

### The question
`arclink_service_health` has PK `(deployment_id, service_name)` with no host/migration
column. After the repair, the verifier checks freshness and the apply status, but does the
system actually *prove the target host's services came up healthy* before promoting the
migration to `succeeded`? If not, what schema/wire contract closes that without unbounded
blast radius?

### My independent reasoning (grounded in current code)
The repair closed the *stale/empty fail-open* but did **not** close the underlying gap:
no real per-target-service health probe ever runs in the migration path.

1. The only health the migration itself writes is `_record_pod_migration_health` at
   migration-start (`:1126`), which hardcodes `status='healthy'` for service
   `pod-migration` (`:952-967`). This is a **self-attestation**, not evidence the target
   host is up. Because it is written at start with `checked_at=now`, it always passes the
   verifier's freshness test by construction.
2. Real per-service health is only ever written by provisioning's
   `_record_health_placeholders` — and those rows are status `dry_run_planned` with
   `note: "planning only — not yet applied"` (`python/arclink_provisioning.py:1785-1793`).
   The sovereign-worker post-apply health write is **not** invoked from the migration path;
   the migration calls `executor.docker_compose_apply` directly (`:1327-1333`), which
   returns `status="applied"` without seeding service health.
3. So today's verifier gate reduces to: "compose apply returned `applied`" (real, via
   `_apply_docker_status_gate`) **plus** "the migration's own self-attested healthy row is
   fresh" (circular). It never reads a *target-host* service probe because none exists, and
   the `(deployment_id, service_name)` key cannot even distinguish source-host health from
   target-host health.

This violates the symphony's layered-health intent: health must be **observed**, not
asserted. The right shape is (a) actually run a health/compose-ps probe against the target
after apply, and (b) store that evidence scoped to the target host + migration so the same
truth is replayable on dashboard/API/Raven.

### Where I agree / differ from Codex
- **Agree** with Codex's core: add first-class scoped health evidence and make the verifier
  require fresh **target-host** checks, fail closed on missing/stale/wrong-host/unhealthy.
  Codex correctly identifies that the PK ambiguity is the root and that detail-JSON-only
  host metadata is unenforceable. Agreed.
- **Refine the sequencing and the load-bearing piece.** Codex frames the new
  `arclink_service_health_checks` table as the headline. In the *current* code the headline
  gap is that **no real probe runs at all** — the verifier has nothing real to read. So the
  load-bearing change is the **executor health/compose-ps wire after `docker_compose_apply`**
  that produces real per-service status for the target. The new append-only table is the
  durable, same-truth evidence store for that probe; it is necessary but secondary to the
  probe existing. Build the probe + scoped evidence together; do not ship the table without
  the probe (that would just relocate the self-attestation).
- **Refine the key set.** Codex's proposed key
  `(deployment_id, service_name, host_id, placement_id, migration_id, operation_idempotency_key, project_name, checked_at)`
  is more than the verifier needs and couples the evidence table to migration internals.
  Minimal enforceable contract: append-only `arclink_service_health_checks` keyed by an
  autoincrement/uuid `check_id`, with columns `deployment_id, service_name, host_id,
  migration_id, status, checked_at, detail_json`. The verifier query becomes
  `WHERE deployment_id=? AND host_id=? AND migration_id=? AND checked_at >= <started_at>`.
  That is the smallest set that proves "this migration's target host reported these services
  healthy after this run." Keep the legacy summary `arclink_service_health` untouched
  (back-compat) and have the migration verifier read the new scoped table.
- **Replace, not augment, the self-attestation.** Once real target-host checks exist, the
  hardcoded `status='healthy'` self-attestation in `_record_pod_migration_health` should be
  demoted to a *marker* (`status='verifying'` at start, updated from the real probe) so it
  can never stand in for reality. Otherwise the circular pass remains.

### FINAL PLAN
1. **Schema (migration-aware, additive):** add append-only
   `arclink_service_health_checks(check_id PK, deployment_id, service_name, host_id,
   migration_id, status, checked_at, detail_json)` in `ensure_schema()` via
   `CREATE TABLE IF NOT EXISTS` (matches the existing single-`ensure_schema` mechanism;
   `python/arclink_control.py:1066-1099` contract). No rebuild of `arclink_service_health`.
2. **Executor wire:** after `docker_compose_apply` succeeds, run a target health/compose-ps
   step (extend the executor's existing apply-result `service_health` plan path already
   present at `python/arclink_executor.py:3000`) and have `migrate_pod` write one
   `arclink_service_health_checks` row per service with `host_id=row["target_host_id"]`,
   `migration_id=row["migration_id"]`, `commit=False` inside the migration transaction.
3. **Verifier:** change `_default_verifier` to query the scoped table filtered by target
   `host_id` + `migration_id` + freshness; missing, stale, wrong-host, or
   `failed|unhealthy|missing` → `healthy=False` → rollback. Keep the `_apply_docker_status_gate`
   as the first gate.
4. **Demote self-attestation:** `_record_pod_migration_health` writes `status='verifying'`
   at start; promote to `healthy` only from the real probe on success.
5. **Same-truth surfaces:** expose the scoped checks (read-only) to dashboard/API/Raven so a
   browser and a chat show the identical evidence the verifier used.
6. **Live gate:** lands behind `PG-FLEET` / `PG-PROVISION` (real target apply + probe). Local
   proof: fake-executor test that injects unhealthy/stale/wrong-host checks and asserts
   rollback; schema test against an old-state fixture (table absent → created, no data loss).

### Symphony anchor (quoted)
- Observability, SLOs, Capacity, And Scale: *"Health is layered: control process health,
  API/web health, ... fleet capacity, ArcPod health, workspace health, backup freshness,
  qmd/memory freshness, and proof status."* (`:1107-1110`)
- Configuration, Schema, And Migration: *"Database schema changes are migration-aware,
  idempotent, reversible where practical, and tested against old-state fixtures."*
  (`:1078-1079`)
- Whole-System Traversal: *"If any step cannot say what surface owns it, what state it reads,
  what state it writes, and how it fails closed, the symphony is not complete."* (`:160-161`)

### Effort + blast radius
**high.** Touches `arclink_control` schema/helpers, executor health wire (extends an existing
seam), `arclink_pod_migration` verifier + health-record, dashboard/API/Raven health reads,
schema/old-fixture tests, plus `PG-FLEET`/`PG-PROVISION` live proof. This is the right large
investment; it converts an asserted gate into an observed one.

---

## DECISION 2 — Dry-run-to-live reuse of one `migration_id` — [VERDICT: agree-codex (refined)]

### The question
Today one idempotency key `arclink:migration:<migration_id>` covers both dry-run and live,
and `_operation_intent` embeds `dry_run` in the intent digest (`:467-476`). After a dry-run
completes, a live run with the same id produces a different intent digest and is rejected by
the idempotency layer. Should the same `migration_id` be promotable dry-run → live, and how?

### My independent reasoning (grounded in current code)
- `_operation_intent(row, dry_run=...)` puts `"dry_run": bool(dry_run)` into the digested
  intent (`:476`); `reserve_arclink_operation_idempotency` raises on a digest mismatch for
  the same `(operation_kind, idempotency_key)`. So a dry-run then a live run on one id is a
  **footgun**: the live run errors out on intent mismatch rather than executing — confusing,
  and it strands the operator who naturally re-runs the same id "for real."
- The action worker already keys both phases off one `operation_key`
  (`arclink:migration:<migration_id>`, `python/arclink_action_worker.py:1229`) and already
  tolerates `dry_run && status=='planned'` as success (`:1251`). The dry-run does **not**
  leave `planned` for a live run (it stays planned), so there is a clean promotion point.
- Removing `dry_run` from the digest (the naive fix) is **wrong**: it would let a dry-run
  reservation satisfy a live run, i.e. replay a dry-run as if it were a live-safe apply. The
  digest must keep the phase. Therefore the keys must be phase-scoped.

This is genuinely a contract choice, but one option is clearly better, so I do not punt it to
a fork.

### Where I agree / differ from Codex
- **Agree** fully with Codex's recommendation and its two rejections (don't strip `dry_run`
  from the digest; don't force a brand-new live id that splits evidence across two truths).
  Phase-scoped keys `arclink:migration:<id>:dry-run` and `arclink:migration:<id>:live`, plus
  an explicit `promote_dry_run=true` and a matching planned target/intent digest before a
  planned dry-run row may transition to live `running`, is the right shape and ties plan,
  dry-run proof, live execution, audit, and rollback under one stable migration identity.
- **Refine one detail:** the stored `operation_idempotency_key` on the `planned` row
  (`:452`) is currently the bare `arclink:migration:<id>`. To avoid two sources of truth,
  derive the phase key deterministically at `reserve` time (`<stored_key>:dry-run` /
  `<stored_key>:live`) rather than storing the phase in the row — the planned row stays
  phase-agnostic and a single planned row legitimately supports both a dry-run proof and a
  later promoted live run. Keep `_operation_intent`'s `dry_run` field (so the two digests
  stay distinct and a dry-run can never satisfy live).
- **Refine the upgrade error:** old planned rows that already burned the bare key on a
  dry-run must not silently dual-purpose. On encountering a legacy `arclink:migration:<id>`
  reservation, fail closed with a clear "rerun dry-run or mint a new migration id" message
  (Codex's residual-risk handling — adopt it verbatim).

### FINAL PLAN
1. In `migrate_pod`, compute the reservation key as `f"{operation_key}:dry-run"` when
   `dry_run` else `f"{operation_key}:live"` (operation_key from `:1203`). Keep
   `_operation_intent` embedding `dry_run`.
2. Gate the planned→live transition on `metadata.promote_dry_run == true` **and** an
   equality check that the live intent's target/digest matches the planned row's
   target_host/state_roots; mismatch → fail closed.
3. Preserve dry-run evidence: keep writing dry-run `verification_json`/`docker_dry_run`
   (`:1238-1283`) and, on promotion, do not overwrite it — store live verification in the
   normal fields. The single migration row now carries both proofs.
4. Action worker: pass `promote_dry_run` through `metadata`; keep the existing
   `dry_run && planned` success tolerance (`:1251`).
5. Legacy-row guard + migration test: dry-run then promoted live on one id succeeds with two
   distinct idempotency rows; live without promotion after dry-run fails closed with the
   upgrade message.

### Symphony anchor (quoted)
- Whole-System Traversal: *"Every step should have a local source owner, a local regression
  or dry-run proof where possible, and a named live proof gate where external systems are
  required."* (`:158-160`)
- API, Webhook, And Extension Contracts: *"Action-worker contracts that define actor, action,
  target, reason, status, audit, dry-run, confirmation, retry, timeout, and rollback fields."*
  (`:1148-1149`)

### Effort + blast radius
**medium.** Touches migration idempotency-key derivation + intent, the planned→live promotion
guard, action-worker reprovision metadata (`python/arclink_action_worker.py:1223-1258`),
audit/action links, and pod-migration/action-worker tests. No schema change required (the
existing row already holds the bare key and can carry both phase reservations in
`arclink_operation_idempotency`).

---

## DECISION 3 — Rollback lifecycle terminal status — [VERDICT: agree-codex]

### The question
`_rollback_lifecycle` catches target-teardown and source-restart failures into metadata
(`:734-735` and the source-restart block) and `_mark_rollback` **always** writes
`status='rolled_back'` (`:896`). Is `rolled_back` the right terminal status when a required
rollback step (target teardown / source restart) actually failed?

### My independent reasoning (grounded in current code)
- On the unhealthy fork, `_rollback_lifecycle` runs teardown of the target (cross-host) and
  restart of the source, wrapping each in `try/except` and recording
  `{"status":"failed","error_type":...}` into `metadata` (`:734-735`). `_mark_rollback` then
  unconditionally sets `status='rolled_back'` regardless of whether those lifecycle steps
  succeeded (`:889-914`).
- Concretely: if the source restart fails, the pod is left **stopped** but the migration
  reads `rolled_back` — a false system truth. The symphony is explicit that rollback
  preserves state by default and that ArcLink must never fail silently. A `rolled_back`
  status on a stopped source is a silent failure dressed as a clean recovery.
- The status CHECK already permits `failed` (`python/arclink_control.py:1538`), so using
  `failed` for the genuinely-failed-rollback case costs **no new public enum** and no
  API/web/bot compatibility break. That is decisive: it fails closed with operator-visible
  evidence at zero contract cost.

### Where I agree / differ from Codex
- **Agree** with Codex in full: reserve `rolled_back` for proven-clean rollback (required
  steps succeeded or were no-ops); on target-teardown failure or required source-restart
  failure, set `status='failed'`, emit `pod_migration_rollback_failed`, record redacted
  lifecycle metadata (`rollback_outcome`), mark pod-migration health failed, and **preserve
  the capture directory** for repair (do not GC it — capture is the repair material).
- **Agree** with Codex's rejection of a new `rollback_failed` enum as the first contract:
  larger surface cost than warranted. `failed` + structured
  `rollback_metadata_json.rollback_outcome` is the safer first move.
- **One reinforcement (not a disagreement):** the current `_mark_rollback` sets
  `source_garbage_collected_at` when capture cleanup removed/missing (`:909`). On the
  `failed` (rollback-incomplete) path, **skip** capture cleanup entirely and leave
  `source_garbage_collected_at=''` so the capture survives for the repair operator —
  consistent with "preserve state by default." Codex implies this ("preserves the capture
  directory for repair"); make it explicit in the plan.

### FINAL PLAN
1. `_rollback_lifecycle` returns a structured outcome already; thread a boolean
   `rollback_clean` (true iff every attempted required step's `status` is `applied`/no-op).
2. In `_mark_rollback`, branch on `rollback_clean`:
   - clean → `status='rolled_back'` (current behavior), capture cleanup allowed.
   - not clean → `status='failed'`, **no** capture cleanup, `source_garbage_collected_at=''`,
     write `rollback_metadata_json.rollback_outcome='incomplete'` with the redacted lifecycle
     detail, emit `pod_migration_rollback_failed` event+audit, and upsert pod-migration
     health `status='failed'`.
3. Surfaces (dashboard/API/Raven) render `failed` with the `rollback_outcome` reason so a
   "source restored but target cleanup failed" vs "source still down" case is operator-legible
   without reading raw metadata — add a one-line human reason field.
4. Tests: fake executor where source restart raises → assert `status='failed'`,
   `rollback_failed` event present, capture dir preserved; clean rollback → `status='rolled_back'`.

### Symphony anchor (quoted)
- Fleet, Provisioning, Ingress, And Recovery: *"Rollback preserves state by default and only
  deletes volumes with explicit destructive metadata and confirmation."* (`:969-970`)
- Notifications, Incidents, And Evidence: *"ArcLink should never fail silently. Every
  important background path should have an owner-visible state, a retry or repair path, and
  evidence that can be shared without secrets."* (`:979-981`)

### Effort + blast radius
**medium.** Touches `_rollback_lifecycle`/`_mark_rollback` in `arclink_pod_migration`,
action-worker status expectations, dashboard/API/Raven status rendering, pod-migration health
write, and rollback tests. No schema change (`failed` already in the CHECK; reason lives in
existing `rollback_metadata_json`).

---

## CROSS-DECISION NOTES

- All three plans **fail closed** and add **operator-visible evidence**, satisfying the
  Notifications/Incidents/Evidence and Whole-System-Traversal contracts.
- Decisions 2 and 3 require **no schema change** and are the lower-risk pair; ship them first.
  Decision 1 is the high-investment durable fix and should land behind its named live gate.
- None of these alter the operator/Captain boundary: migration stays operator-initiated
  (double opt-in + operator-only `reprovision` caller); the Captain owns the Pod outcome, not
  host-mutation policy.
- The decisions are mutually compatible: Decision 1's scoped health checks are exactly the
  real evidence Decision 3's `failed`-path health-failed write should reference, and
  Decision 2's phase-scoped keys keep the dry-run proof that feeds Decision 1's verifier.

## STANDING DISAGREEMENTS (genuine operator forks)
None of the three is a true product fork — for each, symphony + code point to a single best
plan, so I am giving the operator a recommendation, not a menu. The one judgment the operator
may still want to confirm is recorded in the manifest: whether Decision 1's full
target-host-scoped evidence table is worth its high blast radius **now** versus shipping
Decisions 2+3 first and gating Decision 1 behind `PG-FLEET`/`PG-PROVISION` (my recommended
sequencing). That is a *timing* call, not a direction conflict.
