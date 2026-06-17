# CANON-10 — Cloud Inventory & Capacity — ADVERSARIAL VERIFICATION

Verifier: independent Opus 4.8 skeptic. Method: re-opened all five tracked files plus
every adjacent seam end (arclink_fleet.py, arclink_control.py idempotency helpers,
arclink_boundary.reject_secret_material, arclink_fleet_enrollment.py,
arclink_fleet_inventory_worker.py, arclink_dashboard.py, onboarding_*). Ran live Python
against `parse_probe_output` with realistic `df -BG` stdout. Did NOT trust the record's
citations.

VERDICT: **PARTIALLY TRUSTWORTHY — one HIGH-severity capacity-correctness defect that the
record materially mis-diagnosed and mis-rated, plus one un-traced orphaned-VM failure
path. The seam contracts and ASU math are sound. The record is honest and well-cited on
most claims, but its single most important real-world correctness conclusion (disk parse)
is wrong.**

---

## REFUTED / DOWNGRADED CLAIMS

### R1 — REFUTED (severity escalation + wrong cause): `parse_probe_output` disk parse "picks the max integer-G second field" is FALSE on real `df -BG` output; real boxes get disk_gib=0.
Record OUTPUT CONTRACT line 137: "Disk parsing ... picks the max integer-GiB second field
of a `df -BG` line ending in `G`; a value like `120G` -> 120". Record RISKS rates this
**LOW** ("a malformed line yields disk_gib=0 (fail-closed)").

CODE: `arclink_inventory.py:404` — `elif line.startswith("/dev/") or line.startswith("overlay") or line.startswith("Filesystem"): continue`.
Real `df -BG /` output has the device in the FIRST column (`/dev/sda1`, `/dev/root`,
`overlay` for `/var/lib/docker`). Every such line is SKIPPED by the `continue`, so the
size line is never reached by the `else` branch at `:410-416`.

PROOF (executed):
- Normal output `\n/dev/sda1  160G  20G  140G  13% /\n` -> `disk_gib=0` -> `compute_asu` = 0.
- Even the docker mount `overlay 200G ... /var/lib/docker` -> skipped -> `disk_gib=0`.
- The ONLY input that reaches the size-parse branch is a df line whose device name
  WRAPPED to its own line (long LVM names), and then the parser reads field index 1 of the
  continuation line = the **Used** column, not the size: input
  `/dev/mapper/very-long-name\n   160G  20G  140G  13% /` -> `disk_gib=20` (WRONG — it
  grabbed Used, not Size).

Impact: disk is the binding scarce resource in `compute_asu` (`arclink_asu.py:61`,
floor(disk/30)). On a real probed box `disk_gib=0` forces `asu_capacity=0`, so the host can
NEVER receive placements under `ARCLINK_FLEET_PLACEMENT_STRATEGY=standard_unit`
(`arclink_fleet.py:143`,701 gate `asu_available < 1`). This is the happy path on real
hardware, not an edge case. There is NO test that feeds raw `df -BG` stdout through
`parse_probe_output` — every test (`tests/test_arclink_inventory.py:27`,
`test_arclink_inventory_hetzner.py:88`, `test_arclink_inventory_linode.py:88`) injects a
pre-built `hardware_summary` dict and bypasses the parser. Re-rated **HIGH**. Record's
"fail-closed, but" framing understates: it is a silent always-zero capacity for the entire
SSH-probe path (`probe_inventory_machine`, the `arclink-inventory probe` CLI), AND the
worker path when it falls back to live `compute_asu(hardware)`
(`arclink_fleet_inventory_worker.py:367`).

NOTE the worker has a safety net the SSH-probe path lacks: `compute_asu(hardware) if
hardware else float(capacity_slots)` (`:367`) — but `hardware` from a probe is a non-empty
dict `{vcpu_cores, ram_gib, disk_gib:0, ...}`, so the truthiness guard does NOT trigger;
the worker still computes ASU from disk_gib=0. The fallback only saves the case where
hardware is entirely absent.

### R2 — REFUTED (gap the record missed): orphaned cloud VM on post-provision failure; no compensating `remove_server`.
Record CODE-PATH TRACE (create) steps 7–11 and seam #4 describe the happy path. The
unhappy path is un-traced. In `create_cloud_inventory_machine`, `_call_provider_create`
(`:770`) provisions a real billable VM. If ANYTHING after that raises before completion —
`register_inventory_machine` (`:807`) which nests `register_fleet_host` (`arclink_fleet.py:173-175`
`_reject_secrets(tags)/_reject_secrets(metadata)`) AND `_safe_json(metadata)`
(`arclink_inventory.py:214`,249 -> `reject_secret_material`) — the `except Exception` at
`:833-842` ONLY calls `fail_arclink_operation_idempotency` and re-raises. It NEVER calls
`client.remove_server(resource_id, destroy=True)`. The VM is left running at the provider,
billed, with no inventory row. Trigger is reachable: the metadata passed to
`register_inventory_machine` at `:820` embeds `provider_intent` (`:783`) which contains the
operator-supplied `tags` verbatim; a tag value matching the secret-material regex (e.g. a
key-shaped string) makes both `_reject_secrets` and `_safe_json` raise post-provision.
Severity **MEDIUM** (cost + drift; requires a secret-shaped tag or any provider/DB error in
the post-provision window). Neither the record nor prior docs mention this.

### R3 — DOWNGRADED claim accuracy: OUTPUT CONTRACT "asu_consumed overwritten by current_load" (seam #9) is true but the silent-swallow is undocumented.
Record seam #9 (dashboard) line 311: "Producer returns full row dicts with `asu_consumed`
overwritten by `current_load`." CONFIRMED at `arclink_inventory.py:319`. BUT the record omits
that the overwrite is wrapped in `except ArcLinkASUError: item["asu_consumed"] = float(...)`
(`:320-321`) — a silent fallback to the stored column. Not a refutation of the seam, but the
"overwritten by current_load" contract is conditional, not absolute. INFO.

---

## CONFIRMED CLAIMS (independently re-verified in code)

- **compute_asu math** (`arclink_asu.py:61`): `max(0, int(min(floor(vcpu/vpp), floor(ram/rpp),
  floor(disk/dpp))))`. Scarcest-resource. CONFIRMED. Env tunables + `<=0`/non-numeric raise
  (`:22-24`). CONFIRMED.
- **`_number` PRESENT-but-non-numeric raises immediately** (does NOT fall through to next
  key) — `arclink_asu.py:35-38`. CONFIRMED. Record INPUT CONTRACT line 33 is correct.
- **RAM=0/disk=0 do not raise, force result 0** (`arclink_asu.py:59-61`). CONFIRMED. Record LOW.
- **Seam #1 (adapter -> compute_asu)**: producer keys `vcpu_cores/ram_gib/disk_gib`
  (`*_hetzner.py:115-117`, `*_linode.py:114-116`) == consumer first-choice keys
  (`arclink_asu.py:53-55`). BOTH ENDS CONFIRMED.
- **Seam #2 (parse_probe_output -> compute_asu)**: producer keys `arclink_inventory.py:418-420`
  == `arclink_asu.py:53-55`. Key match CONFIRMED. (But producer's disk_gib value is broken — R1.)
- **Seam #3 (asu columns -> arclink_fleet placement, OUT/CANON-08)**: producer writes REAL
  cols (`arclink_inventory.py:479-486`); consumer SELECTs `asu_capacity, asu_consumed`
  (`arclink_fleet.py:316`), recomputes `asu_available` (`:337`), gates at `:143` and `:701`.
  BOTH ENDS CONFIRMED. Record line numbers accurate.
- **Seam #4 (register_inventory_machine -> register_fleet_host, OUT/CANON-08)**: call site
  `arclink_inventory.py:173-182` keyword set matches `register_fleet_host` signature
  (`arclink_fleet.py:158-167`). Signature CONFIRMED. **Caveat:** register_fleet_host runs
  `_reject_secrets` on tags/metadata (`:173-175`) — a raise-after-provision vector (see R2);
  the record's "both-ends-verified" does not note this side effect.
- **Seam #5 (idempotency, CANON-01)**: `reserve` sets `result["replay"]` from terminal-status
  check (`arclink_control.py:3329`); `replay` returns None for non-terminal (`:3345-3346`);
  `_require_matching_operation_intent` raises on digest mismatch (`:3294-3296`). This piece
  reads `reserved.get("replay")` (`:766`,883) and `replay is not None` (`:752`). BOTH ENDS
  CONFIRMED. Record citations accurate.
- **Seam #6 (consume_fleet_enrollment -> register_inventory_machine, IN/CANON-08)**:
  `arclink_fleet_enrollment.py:650-668` keyword set is a subset of this piece's signature
  (`arclink_inventory.py:142-161`). CONFIRMED.
- **Seam #7 (fleet_inventory_worker, IN/CANON-20)**: `compute_asu(hardware) if hardware else
  float(capacity_slots)` + `current_load` then writes same REAL cols
  (`arclink_fleet_inventory_worker.py:367-377`). CONFIRMED — but see R1 note: the `if
  hardware` guard does NOT protect against disk_gib=0 because hardware is a non-empty dict.
- **Seam #8 (resource_map -> onboarding/control)**: consumers
  `arclink_onboarding_completion.py:209-227`, `arclink_onboarding_flow.py:913-924`,
  `arclink_control.py:17549`,17700-17719 — keyword args match the pure builders. CONFIRMED.
- **Seam #9 (dashboard -> list_inventory_machines)**: consumer reads the 11 keys at
  `arclink_dashboard.py:606-616`; producer returns full row dicts (`arclink_inventory.py:317-322`).
  CONFIRMED (with R3 caveat).
- **Provider allowlist** `{local,manual,hetzner,linode}` (`arclink_inventory.py:55`) ==
  schema CHECK (`arclink_control.py:1415`). CONFIRMED.
- **Status allowlist** `{pending,ready,draining,degraded,removed}` (`arclink_inventory.py:69`)
  == schema CHECK (`arclink_control.py:1421`). CONFIRMED.
- **probe fail-closed**: OSError/SubprocessError (`:448-459`) and non-zero returncode
  (`:460-471`) both set status='degraded', redact error, commit, raise. CONFIRMED.
- **SSH TOFU** `StrictHostKeyChecking=accept-new` (`arclink_inventory.py:440`). CONFIRMED. MEDIUM.
- **remove requires destroy=True AND draining/removed unless force** (`:859-862`). CONFIRMED.
- **set-strategy is a DB no-op** (`:1287-1291`). CONFIRMED.
- **resource_map is side-effect-free** (only `Path(...)` construction at
  `arclink_resource_map.py:84`, no I/O). CONFIRMED.
- **Token double-redaction** (`*_hetzner.py:49,51`, `*_linode.py:49,51`). CONFIRMED.

---

## NEW GAPS (neither record nor prior docs mention)

### G1 — HIGH: disk-parse `continue` skips device lines -> disk_gib always 0 on real `df -BG` -> asu_capacity 0 -> host never schedulable under standard_unit. Untested. (`arclink_inventory.py:404` vs `:410-416`). See R1. This is the headline defect.

### G2 — MEDIUM: orphaned billable cloud VM on post-provision exception; no compensating remove_server in the `except` (`arclink_inventory.py:833-842`). See R2.

### G3 — LOW: `current_load` returns float, but `probe_inventory_machine` passes
`observed_load=int(consumed)` to `update_fleet_host` (`arclink_inventory.py:494`). Fractional
load (impossible today since COUNT is integral, but `asu_consumed` column is REAL and the
unlinked branch returns it verbatim) would be silently truncated toward zero, under-reporting
load and over-reporting available capacity. Fail-OPEN direction (over-schedules).

### G4 — LOW: `register_inventory_machine` upsert match is `provider = ? AND
((provider_resource_id != '' AND provider_resource_id = ?) OR LOWER(hostname) = ?)`
(`arclink_inventory.py:188`). A manual machine (empty resource_id) and a later cloud machine
sharing the same hostname under a DIFFERENT provider are distinct rows (provider scoped), but
a manual re-register that reuses a hostname already linked to a fleet host will re-call
`register_fleet_host` (capacity_slots given) which, finding the host by hostname
(`arclink_fleet.py:189-193`), MUTATES capacity_slots/region/tags of the existing fleet host
out from under the original machine. No guard that the hostname-matched fleet host belongs to
THIS machine. Cross-machine capacity clobber via hostname collision.

### G5 — INFO: `_existing_cloud_machine` short-circuit (`:755-757`) and the
`replay`/`reserve` race are NOT in a transaction spanning the provider call. Two concurrent
`create` with the same hostname but DIFFERENT idempotency keys both pass `replay=None`
(different keys), both pass `_existing_cloud_machine=None`, both `reserve` (different keys),
both call `provision_server` -> two VMs, then both `register_inventory_machine` upsert onto
the SAME hostname row (second overwrites first's resource_id) -> one orphan VM. TOCTOU on
hostname; idempotency only de-dups by key, not by hostname.

---

## SEAM MISMATCHES
None of the 9 declared seams has a key/shape mismatch — all verified at both ends. The
problems are (a) a value-correctness bug INSIDE the parse_probe_output producer (disk_gib),
not a key mismatch (R1/G1), and (b) un-traced failure/concurrency paths (R2/G2, G4, G5). The
record's "both-ends-verified" key-level claims hold.

---

## RISK RE-CALIBRATION
- df -BG disk parse: record **LOW** -> should be **HIGH** (always-zero capacity on real
  probe output; untested; mis-diagnosed cause).
- Orphaned VM on post-provision failure: **MEDIUM** (new; record absent).
- Hetzner unit asymmetry: record **MEDIUM** — agree it is unverified against live API; the
  fixture (`test_arclink_inventory_hetzner.py:51` `memory:16,disk:160`) only proves the code
  treats them as GiB, not that the API emits GiB. Honest open item; keep MEDIUM.
- SSH TOFU: **MEDIUM** — agree.
- RAM=0 -> 0 ASU: **LOW** — agree.
- Stale asu_consumed for unlinked machines: **LOW** — agree.

## BOTTOM LINE
Core ASU arithmetic, sole-writer discipline, idempotency wiring, redaction, and all nine
cross-piece key contracts are real and re-confirmed. The record is well-cited and honest in
its self-checks. But it shipped a wrong load-bearing conclusion: it claims `parse_probe_output`
extracts disk size from `df -BG`, when the code's own `continue` at line 404 guarantees
disk_gib=0 on real output, collapsing capacity to 0 — and it rated this LOW. Add the
un-traced orphaned-VM and hostname-TOCTOU paths and the record is trustworthy as a map but
must NOT be relied on for the "capacity is computed correctly end-to-end" claim.
