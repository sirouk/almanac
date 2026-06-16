# CANON-10 — Cloud Inventory & Capacity — RECONCILED (both-model truth)

- Piece: CANON-10 (Cloud Inventory & Capacity)
- Tracked files: `python/arclink_inventory.py`, `python/arclink_inventory_hetzner.py`,
  `python/arclink_inventory_linode.py`, `python/arclink_asu.py`,
  `python/arclink_resource_map.py`
- Codex (GPT-5.5 xhigh) SIGN-OFF: **OBJECT(3)** — "ASU math and seam map ratify, but the
  original record only survives with the verifier's HIGH disk-parse correction plus
  additional fail-open/replay refinements."
- Adjudicator: Claude Opus 4.8 (1M) final federation adjudicator.
- **FEDERATION SIGN-OFF: AGREED-WITH-STANDING-DISAGREEMENTS** (exactly one standing item:
  Hetzner live-unit correctness, un-ratifiable from repo code alone — see Standing
  Disagreements). Every other material point reconciled to one code-grounded truth.

Binding method note: every disputed point below was re-opened by the adjudicator with
Read/grep and, where decisive, executed against live Python. Code wins over names,
comments, and prior claims.

---

## RESOLUTION TABLE (point | winner | deciding cite)

| # | Point | Winner | Deciding cite (adjudicator-reopened) |
|---|-------|--------|--------------------------------------|
| 1 | `parse_probe_output` disk parse yields `disk_gib=0` on real `df -BG`, collapsing `compute_asu` to 0 (orig record said "picks max integer-G field"/LOW) | claude-verifier + codex | `arclink_inventory.py:404` (`continue` skips `/dev/`+`overlay`+`Filesystem`), size-`else` at `:410-416` never reached; executed: realistic stdout -> `disk_gib=0`, `compute_asu(...,env={})=0`; gate `arclink_fleet.py:143`,`:701` |
| 2 | Worker fallback does NOT mask the bug | claude-verifier + codex | `arclink_fleet_inventory_worker.py:367` `compute_asu(hardware) if hardware else ...`; probe `hardware` is non-empty dict (`arclink_inventory.py:417-423`) so guard passes -> ASU from disk_gib=0 |
| 3 | Orphaned billable VM on post-provision exception; no compensating `remove_server` | claude-verifier + codex | `arclink_inventory.py:833-842` except only `fail_*` + re-raise; provision at `:770`; trigger reachable: `register_fleet_host` `_reject_secrets` `arclink_fleet.py:173-175` (executed: raises `ArcLinkFleetError` on AWS-key-shaped tag); tag flows intent->metadata `arclink_inventory.py:743,782,820` |
| 4 | Hetzner mem/disk unit asymmetry is REAL but "raw MB" is NOT proven by code | both (Codex REFINE ratified) | `arclink_inventory_hetzner.py:116-117` raw copy vs `arclink_inventory_linode.py:115-116` `round(mb/1024,2)`; live unit un-ratifiable from repo (Standing) |
| 5 | SSH TOFU `StrictHostKeyChecking=accept-new` default | both (CONFIRM) | `arclink_inventory.py:440`; `UserKnownHostsFile` optional/env-fed `:441-442`,`:1196-1197` |
| 6 | ASU seam OUT to placement (CANON-08) verified both ends | both (CONFIRM) | producer `arclink_inventory.py:476-492`; consumer `arclink_fleet.py:314-337`, gate `:143`,`:700-701` |
| 7 | Cloud-create leaves `asu_capacity=0` (host unschedulable under standard_unit until a probe) | both (Codex REFINE ratified) | default `arclink_inventory.py:152`; create passes no asu_capacity `:807-822`; gate `arclink_fleet.py:143` |
| 8 | Idempotency seam shape (replay/reserve/complete/fail) verified | both (CONFIRM) | `arclink_inventory.py:746-767`,`:824-841`; terminal set `arclink_control.py:3208`; replay-for-terminal `:3345-3348` |
| 9 | Dashboard seam: `asu_consumed` overwrite is CONDITIONAL (silent fallback on `ArcLinkASUError`) | both (Codex REFINE / verifier R3 ratified) | `arclink_inventory.py:317-322` (try/except fallback at `:320-321`); consumer `arclink_dashboard.py:604-617` |
| 10 | `current_load` empty `machine_host_link` returns stored `asu_consumed`; placement rows use linked joins | both (CONFIRM) | `arclink_asu.py:72-74`; fleet uses linked join `arclink_fleet.py:314-337` |
| 11 | resource_map drift (access-rail strings, not inventory/ASU) | both (CONFIRM) | `arclink_resource_map.py:23-61`,`:93-111`; consumers onboarding/control `arclink_onboarding_completion.py:204-229`,`arclink_control.py:17700-17719` |
| 12 | provider/status allowlists == schema CHECK | both (CONFIRM) | `arclink_inventory.py:53-69` <-> `arclink_control.py:1413-1423` |
| 13 | adapter key shape == ASU consumer first-choice keys | both (CONFIRM) | `arclink_inventory_hetzner.py:114-117`,`arclink_inventory_linode.py:113-116` <-> `arclink_asu.py:53-55` |
| 14 | compute_asu scarcest-resource math + zero-disk/RAM behavior | both (CONFIRM) | `arclink_asu.py:53-61` (executed) |
| 15 | "fail-closed lifecycle" framing in original record is too strong | codex (object) | successful-SSH parse/ASU failures are fail-OPEN stale (see new-finding N1); record VERDICT overstated |

Codex CONFIRM items where both models already agreed (seams #1,#2,#5,#6,#8; allowlists;
token double-redaction; set-strategy DB no-op; remove requires destroy+draining/removed;
probe fail-closed on runner-exception/nonzero) are **ratified as-is** — independently
re-checked at the cited lines, no change.

---

## CODEX NEW FINDINGS — CONFIRMED vs REJECTED

### CONFIRMED (become net-new federation risks)

- **N1 — MEDIUM (CONFIRMED): stale-`ready` fail-open on successful SSH with bad
  parse/ASU.** `parse_probe_output` (`arclink_inventory.py:472`) and `compute_asu`
  (`:473`) and `current_load` (`:474`) run AFTER the degraded-marking blocks (`:448-471`)
  and are NOT wrapped in any try that marks the row degraded. A returncode-0 probe with
  garbage stdout raising `ArcLinkInventoryError`/`ArcLinkASUError` leaves the row's prior
  `status` (possibly `ready`) and prior ASU columns untouched. The degraded guard only
  covers runner OSError/SubprocessError and nonzero returncode. Decided: codex.
- **N2 — MEDIUM (CONFIRMED): failed create/remove idempotency replays as a bare
  success-shaped object.** `fail_arclink_operation_idempotency` is called with no
  `result=` (`arclink_inventory.py:835`) so it stores `result_json="{}"`
  (`arclink_control.py:3431`); `failed` is terminal (`:3208`). A retry with the same key +
  matching intent: `replay_arclink_operation_idempotency` returns the failed row with
  `replay=True` (`:3345-3348`); create checks replay (`arclink_inventory.py:752-753`)
  BEFORE `_existing_cloud_machine` recovery (`:755`), so `_idempotent_replay_result`
  -> `_operation_result` decodes `{}` -> returns `{"replay": True}` with NO `status`/`machine`.
  Affects both create and remove (remove reserve path `:883-884`). Decided: codex.
- **N3 — LOW (CONFIRMED): non-atomic fleet-host vs inventory-machine creation.**
  `register_fleet_host` commits the host INSERT (`arclink_fleet.py:247`) before
  `register_inventory_machine` later runs `_safe_json(hardware_summary)` /
  `_safe_json(connectivity_summary)` (`arclink_inventory.py:214-215`,`:245-246`), each of
  which runs `reject_secret_material` (`arclink_boundary.py:72`) and can raise — leaving a
  committed fleet host with no inventory machine row. (hardware/connectivity are NOT
  pre-checked by `register_fleet_host`, unlike tags/metadata.) Decided: codex.

### REJECTED
- None. All three Codex new findings re-verified true in code.

### Carried-forward verifier-only new findings (Codex did not address; adjudicator re-checked)
- **G3 — LOW (CONFIRMED):** `update_fleet_host(observed_load=int(consumed))`
  (`arclink_inventory.py:494`) truncates a REAL/fractional `asu_consumed` toward zero
  (fail-OPEN, over-schedules). Today COUNT is integral for linked rows, but the unlinked
  branch returns the REAL column verbatim (`arclink_asu.py:74`). Structurally valid.
- **G4 — LOW (CONFIRMED):** hostname-collision capacity clobber — a manual re-register
  reusing a hostname re-calls `register_fleet_host`, which matches the existing host by
  hostname and mutates capacity_slots/region/tags (`arclink_fleet.py:189-193`,`:212-223`)
  with no guard that the host belongs to THIS machine.
- **G5 — INFO (CONFIRMED structurally):** create TOCTOU — two concurrent creates with the
  same hostname but different idempotency keys both pass replay/`_existing_cloud_machine`,
  both `provision_server`, then upsert the same hostname row -> one orphan VM
  (`arclink_inventory.py:746-767`,`:807`). Idempotency de-dups by key, not hostname.

---

## SEVERITY CHANGES (applied only where code supports)

| Risk | From | To | Deciding cite |
|------|------|----|---------------|
| `df -BG` disk parse -> always-zero capacity on real probe | LOW (record) | **HIGH** | `arclink_inventory.py:404` + executed `compute_asu(...)=0`; gate `arclink_fleet.py:143`,`:701` |
| Orphaned billable cloud VM on post-provision exception | (absent in record) | **MEDIUM** (net-new) | `arclink_inventory.py:833-842`; reachable trigger `arclink_fleet.py:173-175` (executed raise) |
| Stale-`ready` fail-open on bad parse/ASU (N1) | (absent) | **MEDIUM** (net-new) | `arclink_inventory.py:472-474` outside degraded guard `:448-471` |
| Failed-idempotency bare replay (N2) | (absent) | **MEDIUM** (net-new) | `arclink_inventory.py:752-753`; `arclink_control.py:3431`,`:3345-3348` |
| Non-atomic fleet-host creation (N3) | (absent) | **LOW** (net-new) | `arclink_fleet.py:247` before `arclink_inventory.py:214-215`,`:245-246` |

Unchanged (ratified): Hetzner unit asymmetry MEDIUM; SSH TOFU MEDIUM; RAM=0/disk=0->0
ASU LOW; stale `asu_consumed` for unlinked machines LOW; per-instance GET cache INFO;
set-strategy DB no-op INFO.

---

## STANDING DISAGREEMENTS (un-settleable from code alone)

1. **Hetzner live memory/disk units.** Repo code only proves the *asymmetry*
   (`arclink_inventory_hetzner.py:116-117` raw copy vs `arclink_inventory_linode.py:115-116`
   `/1024`). It does NOT prove whether Hetzner's `server_type.memory`/`disk` are GiB (raw
   copy correct) or MB (~1024x over-count). Tests use fixtures
   (`test_arclink_inventory_hetzner.py`), not the live `/server_types` API. Per the binding
   "code wins / no live calls" method this cannot be ratified either way. Both models agree
   to keep it MEDIUM and OPEN. (Claude record assumed GiB/correct; verifier + Codex both
   declined to ratify the live unit. No model is wrong on code — this is a genuine
   evidence gap requiring a live API sample or fixture-backed contract.)

All other points reconciled to a single code-grounded truth.

---

## FINAL BOTH-MODEL VERDICT

CANON-10's core arithmetic is sound and re-confirmed by both models: `compute_asu`
computes a conservative scarcest-resource ASU (`arclink_asu.py:61`), the registry is the
sole writer of the capacity columns with allowlist/regex validation matching the schema
CHECKs, all nine declared cross-piece seams match key/shape at both ends, and tokens are
double-redacted. **But the piece must NOT be relied on for "capacity is computed correctly
end-to-end":** the `df -BG` parser yields `disk_gib=0` on real probe output
(`arclink_inventory.py:404`, executed), collapsing `asu_capacity` to 0 and making
SSH-probed hosts permanently unschedulable under `standard_unit` — a **HIGH** defect the
original record rated LOW and mis-diagnosed. Four further confirmed defects are net-new to
the federation: an orphaned billable VM on post-provision exception (**MEDIUM**), a
stale-`ready` fail-open on bad parse/ASU (**MEDIUM**), a failed-idempotency bare-replay
that masks failure and blocks recovery (**MEDIUM**), and a non-atomic fleet-host creation
(**LOW**) — plus carried verifier LOW/INFO items (G3/G4/G5). The original record's
"fail-closed lifecycle" framing is overstated; the lifecycle is fail-OPEN in the
successful-SSH-bad-data and failed-replay paths. One point (Hetzner live units) stands
genuinely un-ratifiable from repo code. Federation sign-off:
**AGREED-WITH-STANDING-DISAGREEMENTS.**
