# CANON-20 — Sharing & Fleet Folder — RECONCILED (both-model truth)

Adjudicator: Claude Opus 4.8 (1M) FINAL ADJUDICATOR, ArcLink two-model Federation.
Method: every disputed point and every Codex new-finding was re-opened against the
actual code (Read/grep/sed). Code wins over comment, name, or prior claim.

- Claude record:           research/canon/sections/CANON-20-sharing-fleet-folder.md
- Claude adversarial verify: research/canon/verify/CANON-20-sharing-fleet-folder.verify.md
- Codex (GPT-5.5 xhigh):    research/canon/codex/CANON-20-sharing-fleet-folder.codex.md

## SIGN-OFFS
- **Codex SIGN-OFF:** OBJECT(4) — ratifies the record + verifier, requires 4 refinements
  (1 mislabeled seam + 3 missed operational defects). All four re-verified TRUE below.
- **FEDERATION SIGN-OFF:** **BOTH-MODEL-AGREED.** Every material point reconciles to a
  single code-grounded truth. The two "residual disagreements" the verifier listed are
  not disagreements between the models — both models (and the adjudicator) agree the code
  says producer-subset+fallback and first-party-reachable; they were record-vs-verifier
  framing corrections that Codex also adopted. No point is unsettleable from code.

---

## RESOLUTION TABLE (point | winner | deciding cite)

| Point | Winner | Deciding cite (adjudicator-opened) |
|---|---|---|
| Probe-wrapper seam is "key-by-key match" | **codex+verifier** (NOT key-by-key; producer-subset + consumer-fallback) | worker reads `payload.get("capacity_slots")`/`("observed_load")` at arclink_fleet_inventory_worker.py:352,354; shipped wrapper emits only ok/kind/admitting/hostname/ssh_port/observed_at + hardware_summary(+fingerprint) at bin/arclink-fleet-probe-wrapper:53-71 — neither top-level key present. Reads resolve via `or <fallback>`. |
| compute_asu crash trigger surface | **codex+verifier** (first-party reachable, not adversarial-only) | wrapper vcpu = `getconf _NPROCESSORS_ONLN \|\| nproc \|\| printf '0'` (bin/arclink-fleet-probe-wrapper:77) → emits `vcpu_cores: 0` (:63) on a degraded host; compute_asu raises on `vcpu<=0` (arclink_asu.py:57-58); record_host_probe is OUTSIDE the runner try (worker:497-501). |
| compute_asu MEDIUM risk itself is real | **both** | arclink_fleet_inventory_worker.py:367 (unguarded call), :501 (outside try); asu.py:57-58. |
| Hub SPOF + remote-ref no reachability check | **both** (record + codex CONFIRM) | arclink_fleet_share.py:188-208 (`ensure_hub_repo` returns True for `://`/`@` refs at :198-200 without proof; local hub is one bare path). |
| Hub-URL guard is option-injection-only | **both** | `_assert_safe_git_arg` rejects empty/leading-`-`/control-chars only (arclink_fleet_share.py:123-136); env `ARCLINK_FLEET_SHARE_HUB_URL` flows to clone/fetch/push (:738-755). |
| `.corrupt` quarantine orphans un-pushed edits (data-availability, not just disk leak) | **codex+verifier** | `_quarantine_corrupt_working_copy` renames aside (arclink_fleet_share.py:143-152); `ensure_member_working_copy` then re-clones with no reintegration/notification (:251-263). |
| fleet-share-reconcile job EXISTS (prior doc stale) | **both** | compose.yaml:1082-1094 defines the service running `... fleet_share.py reconcile --all` every 120s. |
| fleet-share-reconcile is STARTED in prod (Claude OPEN #1 answered) | **codex** | deploy.sh:11637 `run_arclink_docker up` → arclink-docker.sh:3373-3376 `compose up -d --no-build "$@"` (no service args); compose.yaml:1082 service has no profile gate → started by default. |
| sync convergence: no lock, 2-attempt bound can return `error` on healthy hub | **both** | arclink_fleet_share.py:309-363 (loop `range(2)`, no advisory lock, terminal `status="error"` at :356-362; conflicts surfaced not clobbered at :325-333). |
| empty-deployment member-removal silent no-op | **both** | arclink_fleet_share.py:531-533. |
| probe-transaction split (notify commits before audit) | **both** | queue_notification `conn.commit()` at arclink_control.py:8071; reached via `_notify_transition` (worker:263) ← `_apply_liveness_state` (:305/:328) at worker:425, BEFORE audit (:428, commit=False) and final commit (:438). |
| register_fleet_host SELECT-then-INSERT TOCTOU (no IntegrityError fallback) | **both** | arclink_fleet.py:189-192 (SELECT), :238-247 (unguarded INSERT+commit), no try/except; UNIQUE LOWER(hostname) idx control.py:2465. Asymmetric vs place_deployment. |
| remove_placement has no write-lock (concurrent double-decrement) | **verifier** (codex silent, no objection) | arclink_fleet.py:620-635: no BEGIN IMMEDIATE; reads active row then `observed_load = MAX(0, observed_load - 1)`. (INFO; single-writer worker + reconcile self-heal.) |
| `arclink_share_grants` is NOT CANON-20 (scope correction) | **both** (record asserted, codex REFUTE-ratifies) | grep of `pod_comms\|share_grant\|create_user_share\|claim_nonce\|arclink_share_grants` across all three CANON-20 files → GREP_EXIT=1 (no match). Producer: arclink_api_auth.py:3278,3369; consumer: arclink_pod_comms.py:95,206. |
| `ARCLINK_FLEET_SHARED_ROOT` seam: Drive/Code plugins DO read fleet root as writable (upgrade record's "partial") | **codex** | drive plugin_api.py:843-848 builds the "fleet" root descriptor; code plugin_api.py:605 exposes "fleet" with `writable_capabilities`. Record consumer side confirmed at arclink_fleet_share.py:739. Seam now BOTH-ENDS-VERIFIED. |
| Placement concurrency strength (BEGIN IMMEDIATE + unique-idx IntegrityError fallback) | **both** | arclink_fleet.py:531-608; partial UNIQUE idx control.py:2497-2499. Reproduced by verifier; ratified by codex. |
| Reconcile/sync split (DB-only control node; git in-pod) | **both** | arclink_fleet_share.py:607-654 (reconcile, no git), :719-765 (sync-local git); provisioning.py:1327-1334. |
| Dead `paused`/member-`pending` statuses (schema only, no setter) | **both** | control.py:1098,1111; only `active`/`removed` set at arclink_fleet_share.py:405,502. |

---

## CODEX NEW FINDINGS — CONFIRMED vs REJECTED

### CONFIRMED (re-verified true → net-new federation risks)

1. **MEDIUM — unchecked Fleet working path → `git add -A` stages/exfiltrates the whole tree.**
   `sync_local_working_copy` takes `working_path` from `ARCLINK_FLEET_SHARED_ROOT`
   (arclink_fleet_share.py:739) with no containment/allowlist check; `sync_member` then runs
   `git add -A` over that path (:294) and pushes to the hub. A wrong/hostile runtime env value
   commits whatever directory it names to the per-Captain hub. Distinct from the existing
   hub-URL MEDIUM (that redirects the *remote*; this exfiltrates the *wrong local dir*); same
   pod-env trust boundary. Cite: arclink_fleet_share.py:283-294,738-755.

2. **LOW — fleet-share CRUD TOCTOU.** `ensure_fleet_share` (SELECT via get_fleet_share_for_user
   :398, INSERT :414-421) and `add_fleet_share_member` (SELECT :479, INSERT :497-505) are
   SELECT-then-INSERT with no IntegrityError fallback against UNIQUE owner / UNIQUE
   (share_id,deployment_id). Same asymmetry class as G3. Cite: arclink_fleet_share.py:398-420,
   479-505; control.py:1092-1122.

3. **LOW — Docker health required-service list omits both CANON-20 jobs.**
   `DOCKER_REQUIRED_RUNNING_SERVICES` (arclink-docker.sh:26-49) excludes `fleet-inventory-worker`
   and `fleet-share-reconcile`; the health loop only checks that list (:719-727). Either job can
   be stopped while `health` still passes its required-service gate. Cite: arclink-docker.sh:26-49,
   712-727; compose.yaml:1065-1094.

### REJECTED
None. All three Codex new-findings hold in code.

---

## SEVERITY CHANGES (only where code supports it)

| Risk | From | To | Cite |
|---|---|---|---|
| `compute_asu` un-guarded probe crash — trigger reachability | adversarial/"compromised-or-buggy wrapper" framing (MEDIUM) | first-party-reachable on a degraded host (MEDIUM — severity unchanged, framing corrected) | bin/arclink-fleet-probe-wrapper:77,63; arclink_asu.py:57-58; worker:367,501 |
| `.corrupt` quarantine | LOW (disk-fill leak only) | MEDIUM (silent loss of un-pushed local edits — data-availability) | arclink_fleet_share.py:143-152,251-263 |

(No numeric severity change for compute_asu — both models keep MEDIUM; only the stated trigger
surface is corrected. The `.corrupt` finding gains a second, higher-severity facet: the LOW
disk-leak remains, plus a new MEDIUM data-availability facet.)

---

## STANDING DISAGREEMENTS
None. Every material point reconciles to one code-grounded truth. The verifier's two
"residual disagreements" were record-vs-verifier framing corrections (key-by-key →
subset+fallback; adversarial → first-party-reachable); Codex independently reached the same
conclusions, and the adjudicator confirmed both from code. There is no inter-model conflict
left to preserve.

---

## NET-NET BOTH-MODEL VERDICT
This piece provably does its job and the federation agrees on its truth. **Load-bearing
strengths (code-verified by all three passes):** placement is concurrency-safe
(BEGIN IMMEDIATE + unique-active-placement IntegrityError fallback, arclink_fleet.py:531-608);
the probe-worker health FSM + redaction + retention are real (48 passing tests); the Fleet git
folder is a genuine multi-writer convergence engine that surfaces conflicts instead of
clobbering (rebase-or-abort arclink_fleet_share.py:325-333) with a hub never mutated by
membership; the control-reconcile / in-pod-sync split is correct; and — contrary to the stale
prior doc — `fleet-share-reconcile` both EXISTS and STARTS in the default prod `compose up`
lane. **Reconciled weaknesses (the signed risk set):** hub SPOF with no replication and no
reachability check on remote refs (MEDIUM); hub-URL guard is option-injection-only (MEDIUM);
**unchecked Fleet working path → `git add -A` whole-tree exfiltration (MEDIUM, net-new)**;
`compute_asu` un-guarded → first-party-reachable probe-pass crash on a degraded host (MEDIUM);
**`.corrupt` quarantine silently orphans un-pushed edits (MEDIUM data-availability, up from LOW)**;
plus LOWs (2-attempt sync bound, fleet-share CRUD TOCTOU, register_fleet_host TOCTOU,
probe-transaction split, Docker-health omits CANON-20 jobs, empty-deployment no-op) and INFO
(remove_placement no lock, dead paused/pending statuses, co-located sync helper). The biggest
*documentation* failure remains the prior ground-truth doc mis-scoping this piece as the
share-grant subsystem (zero code overlap — share_grants is CANON-02/12) and asserting a
control-node job "does not exist" that demonstrably does and runs in prod.

**FEDERATION SIGN-OFF: BOTH-MODEL-AGREED.**
