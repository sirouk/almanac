# CANON-20 — Sharing & Fleet Folder — ADVERSARIAL VERIFY

Verifier: independent Opus 4.8 skeptic. Method: re-opened all three files
(`python/arclink_fleet.py` 723L, `python/arclink_fleet_inventory_worker.py` 547L,
`python/arclink_fleet_share.py` 893L) plus every external cite, ran the 48 tests,
and reproduced two risk claims with live Python against an in-memory schema.

## OVERALL VERDICT: TRUSTWORTHY (with 4 new gaps + 1 overstated seam)

The record is unusually careful and its load-bearing claims survived re-verification.
Line citations are accurate (spot-checked ~30, all matched). The scope correction
(this piece is the git Fleet folder, NOT the share-grant broker) is correct and
verified. The placement concurrency-safety strength claim is REAL (reproduced). The
`compute_asu` crash risk is REAL (reproduced). I found NO false strength claims.

However I am downgrading the record from "fully trustworthy" to "trustworthy with
caveats" because of: (1) one OVERSTATED both-ends-verified seam, (2) the
`compute_asu` risk is characterized as adversarial-only when the SHIPPED wrapper can
trigger it legitimately, and (3) four real gaps neither the record nor prior docs name.

---

## CONFIRMATIONS (independently re-verified in code)

- **Line counts** 723/547/893 — exact (`wc -l`).
- **Schema cites** all accurate: `arclink_fleet_shares` UNIQUE owner_user_id +
  CHECK(active/paused/removed) (control.py:1092-1102); members UNIQUE(share_id,
  deployment_id) + CHECK(pending/active/removed) (1104-1122); fleet_hosts CHECK
  status (2349-2364); placements CHECK + partial UNIQUE idx
  `idx_arclink_deployment_placements_one_active` (2497); probes CHECK kind (2440-2449);
  UNIQUE LOWER(hostname) idx at control.py:2465-2466.
- **CROSS-PIECE #1 (compose job runner)** — TRUE. compose.yaml:1076 (inventory),
  :1091 (`reconcile --all`), provisioning.py:1329 (`sync-local`); docker-job-loop.sh
  `JOB_NAME=$1; INTERVAL=$2; shift 2` (:9-11) execs remainder. Verb strings literal.
- **CROSS-PIECE #2 (sovereign → ensure_fleet_share/ensure_hub_repo)** — TRUE.
  sovereign:913 `ensure_fleet_share(conn, owner_user_id=user_id)`, :914 reads
  `share.get("hub_ref")`, :916 `ensure_hub_repo(...)`. ensure_fleet_share returns the
  full row (incl hub_ref) via get_fleet_share_for_user at fleet_share.py:412/434.
- **CROSS-PIECE #3/#4 (sovereign place/remove; inventory register/process)** — TRUE.
  sovereign:1133 place_deployment, :887/:1395 remove_placement, :1140 _host_for_placement
  reads `placement` (host resolved separately). inventory.py:174 register_fleet_host then
  reads `host["host_id"]` at :181; inventory.py:1203 process_due_hosts(force=True).
- **CROSS-PIECE #5 (probe wrapper keys)** — keys the worker reads (`ok`, `hardware_summary`,
  `machine_fingerprint`) ARE emitted by bin/arclink-fleet-probe-wrapper:53-71. See
  OVERSTATEMENT below re "key-by-key" — `capacity_slots`/`observed_load` are NOT emitted.
- **CROSS-PIECE #6 (compute_asu/current_load)** — TRUE. asu.py:42 compute_asu→int,
  asu.py:64 current_load(machine_id, conn)→float; worker:367-368, cast to float :377-378.
- **CROSS-PIECE #7 (audit/event/notification sinks)** — TRUE. queue_notification def at
  control.py:8055 with exactly (target_kind,target_id,channel_kind,message,extra); worker
  :263-270 supplies those kwargs; append_arclink_audit @4649, append_arclink_event @3870.
- **DRIFT #1 (fleet-share-reconcile now exists)** — TRUE. Job defined compose.yaml:1082-1091;
  `git log -S` shows the share machinery landed 2026-05-31, after the prior doc's 2026-05-30
  snapshot. Prior doc "does not exist" is genuinely stale.
- **Placement concurrency strength** — REPRODUCED. Clean in-memory: place_deployment twice
  for same deployment is idempotent (same placement_id), observed_load increments exactly
  once (=1); BEGIN IMMEDIATE + UNIQUE partial index + IntegrityError fallback (fleet.py:531-593).
  Double-remove safe (second returns None, observed_load floors at 0 via MAX(0,...)).
- **48 tests pass** (10 worker + 12 share + 26 fleet = 48). Confirmed.
- **Dead statuses** `paused` (schema 1098, no setter) and member `pending` (schema 1111,
  add_fleet_share_member always inserts 'active' @502) — confirmed dead. Accurate.
- **compute_asu crash risk** — REPRODUCED. A capacity probe with
  `hardware_summary.vcpu_cores=0` raises ArcLinkASUError out of record_host_probe and
  aborts process_due_hosts (record_host_probe at worker:501 is OUTSIDE the try/except that
  only wraps the runner call at :497-500). Risk is real and correctly cited.

---

## REFUTATIONS / OVERSTATEMENTS

### R1 — CROSS-PIECE #5 "key-by-key match: yes" is OVERSTATED (partial refute)
The record marks the probe-wrapper seam "BOTH-ENDS-VERIFIED: yes (key-by-key match)".
But the worker reads `payload.get("capacity_slots")` (worker:352) and
`payload.get("observed_load")` (worker:354), and the SHIPPED SSH wrapper emits NEITHER
top-level key (bin/arclink-fleet-probe-wrapper:53-71 emits only ok/kind/admitting/hostname/
ssh_port/observed_at + hardware_summary + machine_fingerprint). Those reads resolve only via
`.get(...) or <fallback>` chains. It is NOT a key-by-key match; it is a producer-subset +
consumer-fallback contract. Handled (no break), but the record's characterization is wrong.
The record's own self-check #3 actually contradicts the body's "key-by-key" claim (it
admits `observed_load` is not emitted) — internal inconsistency. CODE WINS: subset+fallback.

### R2 — `compute_asu` risk mis-scoped as adversarial-only (severity OK, framing wrong)
The record (RISK + OPEN-FOR-CODEX #4) frames the un-guarded compute_asu as a
"compromised/buggy probe wrapper" / "poisoned probe JSON" problem. But the SHIPPED wrapper
computes `vcpu` as `getconf _NPROCESSORS_ONLN || nproc || 0` (wrapper:77) and emits
`vcpu_cores: 0` if BOTH detectors fail — a benign, non-adversarial host condition (minimal
container, missing coreutils, restricted /proc). So the worker-killing crash is reachable
from a legitimate first-party wrapper on a degraded host, not just an attacker. MEDIUM
severity is still appropriate, but "compromised/buggy" understates reachability. Not a full
refute of the risk (the risk is real) — a refute of its stated trigger surface.

---

## NEW GAPS (neither the record nor prior docs name these)

### G1 — MEDIUM: corrupt-copy quarantine SILENTLY ORPHANS un-pushed local edits
`ensure_member_working_copy` quarantines a corrupt `.git` working copy to a `.corrupt[-N]`
SIBLING dir then re-clones from the hub (fleet_share.py:251-263). The quarantined dir is
NEVER referenced again — not re-merged, not surfaced, not GC'd. Any local Fleet-folder edits
that had NOT yet been pushed at corruption time are permanently dropped from the live working
copy (they survive on disk in `.corrupt` but no code path or notification ever reintegrates or
mentions them). The record lists `.corrupt` only as a LOW "disk fills up" leak (RISK) and
misses the DATA-AVAILABILITY/silent-loss angle. Since the Fleet folder is read-write and
agent-edited (the whole point), this is the more important defect. Cite: fleet_share.py:251-263,
143-152.

### G2 — LOW: `queue_notification`'s internal commit splits the probe transaction (non-atomic)
`queue_notification` calls `conn.commit()` internally (control.py:8071). It is invoked
mid-`record_host_probe` via `_notify_transition` (worker:263) ← `_apply_liveness_state`
(worker:305/328), which runs at worker:425 — i.e. AFTER the probe-row INSERT (worker:407)
and host-status UPDATE but BEFORE the `fleet_host_probed` audit (worker:428) and the function's
own `conn.commit()` (worker:438). So on any state-transition probe, the probe row + state
transition + notification get durably committed while the audit row is still pending; a crash
between the notify-commit and line 438 leaves a committed transition with NO audit row. The
record's Trace B and OUTPUT CONTRACT present these writes as one clean per-probe commit and
never flag the mid-transaction flush. Cite: control.py:8071, worker:425,438.

### G3 — LOW: `register_fleet_host` SELECT-then-INSERT has an UNHANDLED IntegrityError (TOCTOU)
Unlike `place_deployment` (which carefully catches IntegrityError on its UNIQUE partial index),
`register_fleet_host` does a `SELECT ... WHERE LOWER(hostname)=?` (fleet.py:189) then an
unguarded INSERT (fleet.py:238-248) with NO try/except. Two concurrent registrations of the
same hostname (case-insensitive) both miss the SELECT and the second INSERT raises an uncaught
`sqlite3.IntegrityError` against `idx_arclink_fleet_hosts_hostname` (REPRODUCED). The record
praises place_deployment's IntegrityError fallback but never notes that the sibling registry
write lacks the same guard. Single-writer in practice (inventory worker), so LOW, but it is an
asymmetric concurrency hole the record's concurrency section (lines 173-177) omits. Cite:
fleet.py:189,238-248; control.py:2465.

### G4 — INFO: `remove_placement` has no write-lock; concurrent removes can double-decrement load
`remove_placement` (fleet.py:615-636) reads the active placement then UPDATEs status + does
`observed_load = MAX(0, observed_load - 1)` with NO BEGIN IMMEDIATE. Two truly-concurrent
removers of the SAME placement both read the active row before either commits and both
decrement load (MAX(0,...) only floors at 0, doesn't prevent over-decrement against other
placements on the host). The record's concurrency section calls out place_deployment's lock
but is silent on remove_placement having none. Low impact (single-writer worker, and
`reconcile_fleet_observed_loads` self-heals load drift), so INFO. Cite: fleet.py:615-636,
388-433.

---

## SEAM MISMATCHES
- Probe-wrapper seam (#5): worker consumes top-level `capacity_slots`/`observed_load` that the
  SSH wrapper never produces — producer subset, consumer fallback. Not a break; mislabeled as
  "key-by-key". (R1)

## CONFIRMED RISKS (record's RISK section, re-checked): 7
All seven of the record's listed risks reproduced or re-confirmed in code (hub SPOF + no
reachability check on remote refs @188-208; hub-URL guard option-injection-only @123,738;
compute_asu un-guarded @367 [reproduced]; 2-attempt sync bound @309-363; .corrupt accumulation
@143-152; empty-deployment silent no-op @531-533; dead paused/pending statuses). I ADD that the
compute_asu trigger is broader than stated (R2) and that .corrupt also silently loses data (G1).

## RESIDUAL DISAGREEMENTS
- Record says probe seam is "key-by-key match: yes"; I say "producer subset + consumer fallback"
  (handled, but not key-by-key).
- Record frames compute_asu crash as adversarial/poisoned input; I say a shipped wrapper on a
  degraded host triggers it (vcpu detection → 0).
