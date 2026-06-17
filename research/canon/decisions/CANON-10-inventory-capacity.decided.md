# CANON-10 — Inventory & Capacity — DECIDED (final federation adjudication)

- Piece: CANON-10 (Cloud Inventory & Capacity)
- Codex proposal: `research/canon/decisions/CANON-10-inventory-capacity.codex.md`
- Adjudicator: Claude Opus 4.8 (1M) — DECISION mode, independent-then-converged.
- Method: every cited line re-opened with rg/sed and, where decisive, executed against
  live Python. Symphony is intent; code is reality; the plan moves code toward the
  symphony while failing closed.
- Outcome: **2 decisions — both `refine` (Codex direction right, scope/mechanism
  tightened to ground in the real columns and the existing fingerprint contract).**
  No standing product fork.

---

## DECISION 1 — Existing fleet hostname re-registration must not silently clobber capacity

**[VERDICT: refine]** — Codex is right that the default must fail closed, but its
"prove same host identity" clause must be grounded in mechanisms that actually exist in
the code, and the *fleet-host layer itself cannot prove identity* — so the fix belongs
at two distinct seams, not one.

### The question (from NEEDS_DECISION.md)
> Hostname-collision capacity clobber across reused fleet hostnames — fixing safely needs
> a public contract decision on whether re-registering an existing hostname is allowed to
> update fleet-host capacity.

### Independent reasoning (code re-opened)
- `register_fleet_host` matches an existing row by `LOWER(hostname)` ALONE
  (`python/arclink_fleet.py:189-193`) and then mutates `region`/`capacity_slots`/`tags`/
  `metadata` (`:212-223`). The schema enforces hostname uniqueness
  (`python/arclink_control.py:2531-2534`, `idx_arclink_fleet_hosts_hostname`).
- **Critical fact Codex's framing understates:** `arclink_fleet_hosts` has *no identity
  column at all* — only `host_id` (PK) and `hostname` (unique). No `machine_fingerprint`,
  no `provider_resource_id` (`python/arclink_control.py:2425-2440`). So
  `register_fleet_host` **cannot** "prove the same host identity" from its own inputs.
  Identity lives one layer up:
  - `register_inventory_machine` upserts by `(provider, provider_resource_id|hostname)`
    and carries `machine_host_link → host_id` (`python/arclink_inventory.py:196-210`).
  - The enrollment path **already** enforces identity: a fingerprint mismatch raises
    `"machine fingerprint mismatch; explicit re-attest required"`
    (`python/arclink_fleet_enrollment.py:647-649`) *before* it ever calls
    `register_inventory_machine`.
- So the real defect is narrower and the real fix is two-seam:
  1. **Fleet layer (the clobber site):** `register_fleet_host` should not mutate a
     *materially different* `capacity_slots` (or region) on a hostname-only match unless
     the caller passes the matching `host_id` (proving it is operating on the row it owns)
     or an explicit `replace=True`/operator-confirmed flow. Default = idempotent return of
     the existing row when fields match; **fail closed** (`ArcLinkFleetError` +
     `fleet_hostname_collision_blocked` audit, capacity untouched) when a bare hostname
     re-register tries to change capacity it cannot prove it owns.
  2. **Inventory layer (where identity exists):** the cloud-create / enrollment / manual
     re-register call sites should pass the resolved `host_id` (when
     `machine_host_link` is already bound) so the legitimate same-host refresh is allowed,
     and rely on the existing fingerprint gate for new-host adoption.
- The fix campaign already added the `image_sync_*` carryover guard
  (`python/arclink_fleet.py:196-211`) for a *related* preservation concern; the capacity
  guard is the missing sibling. This is consistent precedent: re-register must
  **preserve** the prior worker's placement-critical truth, not silently overwrite it.

### Where I agree / differ from Codex
- **Agree:** default must be idempotent-not-mutating; collision without proof must fail
  closed, audit `fleet_hostname_collision_blocked`, and leave capacity untouched; an
  explicit operator replace/adopt flow (drain → remove → adopt, with dry-run + reason +
  audit + post-probe) is the sanctioned override. Effort **med**.
- **Refine (mechanism):** Codex says "update only when `host_id` matches, linked inventory
  identity matches, or operator-confirmed replace." Correct in spirit, but
  `register_fleet_host` has **no** `linked inventory identity` to check — that proof must
  be supplied by the *caller* (`register_inventory_machine` passing `host_id`, or
  enrollment having already passed the fingerprint gate). So scope the guard to:
  *"mutate a hostname-matched row's capacity/region only when the call supplies the
  matching `host_id` or `replace=True`; otherwise return-if-unchanged or raise."* This is
  a smaller, more honest surface than "prove host identity inside `register_fleet_host`,"
  which the table cannot support.
- **Refine (blast radius):** the deploy worker registration snippets
  (`tests/test_deploy_regressions.py:2260,2363,2731` assert `register_fleet_host(` is
  emitted) re-register by hostname on every install. Those must thread `host_id` or pass
  `replace=True` once, or they will start tripping the new guard on routine idempotent
  re-installs. This is the main compatibility cost and must be in the same change set.

### FINAL PLAN
1. In `register_fleet_host` (`python/arclink_fleet.py:189-223`): on an existing
   hostname-only match, gate the capacity/region mutation. Add params `host_id` (already
   present, `:165`) and a new `replace: bool = False`. Logic:
   - If incoming `capacity_slots`/`region` are unchanged → idempotent return of the
     existing row (unchanged behavior, no audit noise).
   - If they differ AND (`host_id` is supplied and equals `existing["host_id"]`) OR
     `replace=True` → apply the update (the caller proved ownership / operator-confirmed).
   - If they differ and neither proof is present → raise `ArcLinkFleetError`, write an
     `append_arclink_audit(action="fleet_hostname_collision_blocked", ...)` with the old
     vs proposed capacity, and **leave the row untouched** (fail closed, state preserved).
   - Keep the existing `image_sync_*` carryover and the `IntegrityError` race re-entry.
2. Thread the proof through callers in `python/arclink_inventory.py`: when
   `machine_host_link` is already bound, pass that `host_id` into the
   `register_fleet_host` call (`:184-194`) so a legitimate same-machine capacity refresh
   is allowed without `replace`.
3. Add an explicit operator `replace`/`adopt` affordance (CLI flag on
   `arclink-inventory` register and the operator action) that sets `replace=True` only
   after the drain/remove/adopt confirmation — keep this in the operator lane.
4. Update the deploy worker registration snippets to thread `host_id`/`replace` so
   routine re-install stays idempotent.
5. Tests: hostname-collision-with-different-capacity blocks + audits + preserves old
   capacity; same-`host_id` refresh succeeds; `replace=True` succeeds; image-sync
   carryover still holds; idempotent unchanged re-register is silent.

### Symphony anchor (quoted)
- **Fleet, Provisioning, Ingress, And Recovery** (`:962-964`): *"Fleet hosts are
  registered with hostname, SSH endpoint, user, region, tags, **capacity**, state root,
  and health/probe evidence."* — capacity is registered host truth and a placement input;
  it must not be rewritten by an unproven hostname collision.
- **Fleet, Provisioning, Ingress, And Recovery** (`:969`): *"Rollback preserves state by
  default and only deletes volumes with explicit destructive metadata and confirmation."*
  — re-register must default to preserving prior worker truth; a destructive replace
  needs explicit operator confirmation.
- **North Star** (`:116`): *"Operators own the universe: hosts, secrets, **fleet,
  policy**, upgrades, backups..."* — re-registering/replacing a fleet host's capacity is
  an operator policy act, not an implicit side effect of name reuse.

**Effort: med. Blast radius:** `python/arclink_fleet.py`,
`python/arclink_inventory.py` register call sites, deploy worker registration snippets,
operator CLI/action + docs, and tests around fleet re-register / image-sync preservation /
hostname collision. Fails closed; preserves state by default.

---

## DECISION 2 — Zero ASU is a valid blocking state, but zero observed hardware and unlinked load must not be authoritative

**[VERDICT: refine]** — Codex's split is exactly right and well-grounded; I converge on
it, refining only *where* the guard lands and clarifying that `compute_asu`'s math
contract must NOT change (it is tested), so the fix is at the **ready writers** and the
**read model**, not the arithmetic.

### The question (from NEEDS_DECISION.md)
> `compute_asu` zero RAM/disk global behavior and stale unlinked `asu_consumed` — left
> unchanged because current contracts explicitly allow zero-capacity summaries and
> placement-critical rows use linked hosts.

### Independent reasoning (code re-opened + executed)
- **Zero ASU is a deliberate, tested contract.** Executed:
  `compute_asu({vcpu:4,ram:0,disk:100})=0`, `compute_asu({vcpu:4,ram:16,disk:0})=0`,
  `compute_asu({vcpu:4,ram:16,disk:100})=3`. And `tests/test_arclink_asu.py:41` asserts
  `compute_asu({...disk_gib:20})==0` ("tiny disk is unusable"). So **do not** make zero
  ASU globally illegal — pending/not-yet-probed/too-small workers legitimately read 0 and
  are correctly rejected by the placement gate
  (`asu_available >= 1` at `python/arclink_fleet.py:142-143`).
- **The unsafe case is different:** a successful probe whose parse *dropped* RAM or disk
  yields `ram_gib=0`/`disk_gib=0` → `compute_asu` returns 0 (does not raise) → the ready
  writer stamps `status='ready', asu_capacity=0`
  (`python/arclink_inventory.py:522-538`; worker twin
  `python/arclink_fleet_inventory_worker.py:391-411`). That is *bad hardware proof
  published as a ready zero-capacity row*, indistinguishable downstream from a legitimate
  too-small worker. The fix campaign's N1 repair degrades on parse/ASU *exceptions*
  (`python/arclink_inventory.py:517-521`) but zero-from-zero-hardware does NOT raise, so
  it slips through to `ready`.
- **Stale unlinked `asu_consumed`:** `current_load` returns the stored column verbatim
  when `machine_host_link` is empty (`python/arclink_asu.py:72-74`), and
  `list_inventory_machines` falls back to the stored value on `ArcLinkASUError`
  (`python/arclink_inventory.py:363-366`, the `except` branch). Placement itself is safe —
  it reads the *linked* inventory row over the FK join
  (`python/arclink_fleet.py:314-337`) — but the dashboard/API read model
  (`python/arclink_dashboard.py:604-617`) can display false capacity pressure from a stale
  unlinked value. That violates same-truth-across-surfaces.

### Where I agree / differ from Codex
- **Agree (fully):** keep zero-capacity summaries as the fail-closed blocked state;
  require positive observed RAM/disk before a probe path marks a machine `ready`; stop
  treating an empty `machine_host_link` as authoritative load; surface `load_source` and
  `asu_consumed=0` for unlinked rows; preserve any prior nonzero value in metadata/audit
  during an idempotent migration; placement stays governed by linked-host truth.
- **Refine (where the guard lands):** Codex says "add strict observed-hardware validation
  in ready writers such as `probe_inventory_machine` and `arclink_fleet_inventory_worker`."
  Endorsed, and I pin it precisely: the check must sit *between* `compute_asu` and the
  `status='ready'` UPDATE, in **both** writers (`python/arclink_inventory.py:516-538` and
  `python/arclink_fleet_inventory_worker.py:391-411`), as a `ram_gib <= 0 or disk_gib <= 0`
  → mark `degraded` (reuse the existing `_mark_probe_degraded` /
  `connectivity_summary={"ok":False,"error":"incomplete hardware probe"}` path) instead of
  publishing `ready` with `asu_capacity=0`. **Do not** touch `compute_asu`'s return
  contract — the math stays, the *ready-gating* is what changes. This keeps the
  too-small-but-real worker correctly at `0` while the malformed-probe worker degrades.
- **Refine (unlinked load — read-model, not a raise):** prefer the non-raising path Codex
  also offers — `current_load` returns `0.0` for an unlinked machine and the serializer
  tags `load_source="unlinked"` (vs `"linked"`/`"stored"`), rather than raising
  internally. Raising would force the `list_inventory_machines` fallback to re-publish the
  stale value (`:363-366`), which is the very bug. Returning 0 + a `load_source` marker
  gives every surface the same honest "unlinked → load unknown/zero" truth and preserves
  the old value only in metadata/audit.

### FINAL PLAN
1. **Ready-writer hardware gate (both writers).** Before the `status='ready'` UPDATE in
   `probe_inventory_machine` (`python/arclink_inventory.py:516-538`) and in the worker
   apply path (`python/arclink_fleet_inventory_worker.py:391-411`): if parsed
   `ram_gib <= 0` or `disk_gib <= 0`, call the existing degrade path (`_mark_probe_degraded`
   / degraded UPDATE with `connectivity_summary={"ok":False,"error":"incomplete hardware
   probe; ram/disk not observed"}`) and raise `ArcLinkInventoryError` — do NOT write
   `ready` with zero capacity. Leave `compute_asu` math untouched (pending / too-small /
   not-yet-probed paths keep returning 0 and are blocked by the placement gate).
2. **Unlinked load is non-authoritative.** Change `current_load`
   (`python/arclink_asu.py:72-74`) to return `0.0` when `machine_host_link` is empty, and
   change `list_inventory_machines` (`python/arclink_inventory.py:360-366`) to annotate
   each row with `load_source` (`"linked"` when the FK COUNT ran, `"unlinked"` when no
   link, `"stored"` only on the ASU-error fallback). Dashboard/API serialization
   (`python/arclink_dashboard.py:604-617`) surfaces `load_source` so a "blocked / unlinked"
   reason is the same in Raven, dashboard, CLP, and API.
3. **State-preserving migration.** Idempotent backfill: for any unlinked row with a stored
   `asu_consumed > 0`, copy the value into `metadata.legacy_asu_consumed` + an audit row
   before the read model starts reporting 0, so nothing is silently destroyed.
4. Tests: zero-RAM/zero-disk probe → `degraded`, not `ready`; too-small-but-valid worker
   still → `ready` with `asu_capacity=0` (keeps `test_arclink_asu.py:41` contract);
   unlinked machine reports `asu_consumed=0` + `load_source=unlinked`; linked machine
   reports the COUNT; dashboard serialization carries `load_source`.

### Symphony anchor (quoted)
- **Fleet, Provisioning, Ingress, And Recovery** (`:964`): *"Placement rejects unhealthy,
  drained, or insufficient-capacity workers."* — zero ASU as a blocked state is correct;
  but a malformed-probe worker must be *unhealthy/degraded*, not a `ready` zero-capacity
  row that lies about why it can't take work.
- **Whole-System Traversal** (`:152-153`): *"Operator Raven, admin dashboard, CLI,
  diagnostics, live proof, and evidence rails show the same system truth."* — a stale
  unlinked `asu_consumed` shown as real capacity pressure breaks same-truth-across-
  surfaces; `load_source` makes the read model honest everywhere.
- **Observability, SLOs, Capacity, And Scale** (`:1108-1109`): *"Health is layered:
  ... queue health, **fleet capacity**, ArcPod health..."* — fleet capacity must reflect
  observed hardware truth, not a zero stamped over a dropped probe field.

**Effort: med. Blast radius:** `python/arclink_asu.py`, `python/arclink_inventory.py`
(ready writer + list serialization), `python/arclink_fleet_inventory_worker.py`,
dashboard/API inventory serialization, an idempotent metadata/audit migration for stale
unlinked values, and focused ASU/inventory/fleet/dashboard tests. Fails closed; preserves
state by default (old value retained in metadata/audit, not deleted). `compute_asu`'s
tested math contract is explicitly unchanged.

---

## STANDING DISAGREEMENTS (genuine product forks for the operator)

None. Both decisions converge on a single recommended plan. (The piece's only
un-ratifiable item — Hetzner live memory/disk units — is an *evidence gap* recorded in the
reconciled record's Standing Disagreements, not a deferred operator decision in this
ledger; it is not in scope for CANON-10's NEEDS_DECISION items and is resolved by a live
API sample / fixture-backed contract, not an operator policy call.)
