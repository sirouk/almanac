<<<CODEX-VERDICT-START CANON-10>>>
## CANON-10 — Codex (GPT-5.5 xhigh) ratification
SIGN-OFF: OBJECT(3)
ONE-LINE VERDICT: ASU math and seam map ratify, but the original record only survives with the verifier's HIGH disk-parse correction plus additional fail-open/replay refinements.

### Adjudication (each: CONFIRM/REFUTE/REFINE + path:line)
- CONFIRM §A.7 / HIGH: `parse_probe_output` skips normal `df -BG` device rows at `python/arclink_inventory.py:404`; disk parsing only happens in the later `else` at `python/arclink_inventory.py:410-416`, so `/dev/*` and `overlay` rows yield `disk_gib=0`, feeding `compute_asu`'s disk floor at `python/arclink_asu.py:61` and blocking `standard_unit` placement at `python/arclink_fleet.py:143` and `python/arclink_fleet.py:700-701`.
- CONFIRM §A.7 / MEDIUM: cloud create provisions before inventory persistence (`python/arclink_inventory.py:770-778`) and the exception path only marks idempotency failed (`python/arclink_inventory.py:833-841`), with no compensating `client.remove_server`; post-provision secret rejection is reachable through `register_fleet_host` tags/metadata checks at `python/arclink_fleet.py:172-175`.
- REFINE MEDIUM Hetzner unit risk: code asymmetry is real, but code does not prove "raw MB"; Hetzner raw-copies `server_type.memory/disk` into GiB-named fields at `python/arclink_inventory_hetzner.py:114-117`, while Linode divides MB by 1024 at `python/arclink_inventory_linode.py:103-116`. Keep as unnormalized/untested capacity risk, not a proven live-unit bug.
- CONFIRM MEDIUM SSH TOFU: probe uses `StrictHostKeyChecking=accept-new` by default at `python/arclink_inventory.py:439-442`; `UserKnownHostsFile` is optional, env-fed only at `python/arclink_inventory.py:1192-1198`.
- CONFIRM ASU seam: inventory writes `asu_capacity/asu_consumed` at `python/arclink_inventory.py:476-492`; fleet reads linked machine rows and computes `asu_available` at `python/arclink_fleet.py:314-337`, then selects/gates candidates at `python/arclink_fleet.py:544-560` and `python/arclink_fleet.py:647-660`.
- REFINE cloud-create capacity claim: create omits `asu_capacity`, so `register_inventory_machine` defaults it to 0 (`python/arclink_inventory.py:152`, `python/arclink_inventory.py:807-822`); under `standard_unit`, the linked host is unschedulable until a probe writes nonzero ASU.
- CONFIRM idempotency seam shape: create calls replay/reserve/complete/fail at `python/arclink_inventory.py:746-767` and `python/arclink_inventory.py:824-841`; CANON-01 marks `failed` and `succeeded` terminal at `python/arclink_control.py:3208` and returns replay for terminal rows at `python/arclink_control.py:3345-3348`.
- REFINE dashboard seam: `list_inventory_machines` normally overwrites `asu_consumed` from `current_load`, but silently falls back to stored `asu_consumed` on `ArcLinkASUError` at `python/arclink_inventory.py:317-321`; dashboard consumes that value at `python/arclink_dashboard.py:604-617`.
- CONFIRM open current-load concern: empty `machine_host_link` returns stored `asu_consumed` at `python/arclink_asu.py:72-74`; placement-critical fleet rows use linked host joins instead (`python/arclink_fleet.py:314-337`).
- CONFIRM resource-map drift: `arclink_resource_map.py` builds access rail strings only (`python/arclink_resource_map.py:23-61`, `python/arclink_resource_map.py:93-111`), consumed by onboarding/control at `python/arclink_onboarding_completion.py:204-229` and `python/arclink_control.py:17700-17719`; it is not inventory/ASU logic.
- CONFIRM no §B/§C CANON-10 entries in consolidated Section 5; the summary-table Hetzner live-unit item remains unresolved by code-only evidence.

### New findings both Claude passes missed (severity + path:line)
- MEDIUM: successful SSH with malformed parse/ASU data is fail-open stale. Only runner exceptions/nonzero returns mark `degraded` (`python/arclink_inventory.py:448-471`); `parse_probe_output` and `compute_asu` run outside that guard at `python/arclink_inventory.py:472-473`, before the ready/degraded update at `python/arclink_inventory.py:476-492`, so bad stdout can leave an old `ready` row and old ASU in place.
- MEDIUM: failed create/remove idempotency replays as a bare success-shaped object. `fail_arclink_operation_idempotency` stores default `{}` result (`python/arclink_control.py:3430-3431`), `failed` is terminal (`python/arclink_control.py:3208`), create checks replay before existing-machine recovery (`python/arclink_inventory.py:746-753`), and `_idempotent_replay_result` returns only decoded result plus `replay=True` (`python/arclink_inventory.py:567-570`).
- LOW: `register_inventory_machine` is not atomic with fleet-host creation. It calls `register_fleet_host` first (`python/arclink_inventory.py:173-182`), and that function commits (`python/arclink_fleet.py:238-248`) before later inventory JSON serialization can fail at `python/arclink_inventory.py:245-249`, leaving a fleet host with no inventory machine.

### Claude citations re-confirmed or corrected
- Re-confirmed: `compute_asu` scarcest-resource math and zero-disk behavior at `python/arclink_asu.py:53-61`; `current_load` active placement count at `python/arclink_asu.py:75-83`.
- Re-confirmed: provider/status allowlists match schema checks (`python/arclink_inventory.py:53-69` ↔ `python/arclink_control.py:1413-1423`).
- Re-confirmed: provider adapter key shape matches ASU consumer (`python/arclink_inventory_hetzner.py:114-117`, `python/arclink_inventory_linode.py:113-116` ↔ `python/arclink_asu.py:53-55`).
- Corrected: original `df -BG` "max integer-G second field" claim is false for normal device rows; code skips those rows at `python/arclink_inventory.py:404`.

### Residual disagreement with the Claude half (for final reconciliation)
- No disagreement with the verifier on the HIGH disk bug or orphaned VM. I object to the original record's "fail-closed lifecycle" framing and add the stale-ready parse failure plus failed-idempotency replay defects.
- Hetzner live units cannot be ratified under the binding method from repository code alone; keep the code asymmetry risk open until a live API sample or fixture-backed contract is executed.
<<<CODEX-VERDICT-END CANON-10>>>
