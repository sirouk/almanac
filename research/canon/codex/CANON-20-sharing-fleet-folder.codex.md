<<<CODEX-VERDICT-START CANON-20>>>
## CANON-20 — Codex (GPT-5.5 xhigh) ratification
SIGN-OFF: OBJECT(4)
ONE-LINE VERDICT: Mostly ratified; verifier’s corrections stand, but CANON needs four refinements: one mislabeled seam plus three missed operational defects.

### Adjudication (each: CONFIRM/REFUTE/REFINE + path:line)
- CONFIRM CANON-20 MEDIUM hub SPOF/remote-noop: remote hub refs return `True` without reachability proof; local path is one bare repo path. `python/arclink_fleet_share.py:171-185,188-208`
- CONFIRM CANON-20 MEDIUM hub URL guard: `_assert_safe_git_arg` only rejects empty, leading `-`, and control chars; env hub ref feeds local sync. `python/arclink_fleet_share.py:123-136,738-755`
- REFINE CANON-20 MEDIUM compute crash: real and first-party reachable. Worker calls `compute_asu` unguarded; wrapper can emit `vcpu_cores: 0`; `compute_asu` raises; `record_host_probe` is outside the runner try. `python/arclink_fleet_inventory_worker.py:367,497-501`; `bin/arclink-fleet-probe-wrapper:62-77`; `python/arclink_asu.py:53-58`
- CONFIRM CANON-20 MEDIUM `.corrupt` data orphan: corrupt working copy is renamed aside, then a fresh clone/init is used; no reintegration path in that flow. `python/arclink_fleet_share.py:143-152,251-263`
- REFINE §A15 probe-wrapper seam: producer-subset+fallback, not key-by-key. Worker reads `capacity_slots`/`observed_load`; wrapper emits `hardware_summary`/`machine_fingerprint`; fallback handles the missing keys. `python/arclink_fleet_inventory_worker.py:349-354`; `bin/arclink-fleet-probe-wrapper:61-71`
- CONFIRM §B37 started-in-prod: `deploy.sh control install/upgrade` runs Docker `up` with no service args, and `arclink-docker.sh up` runs `compose up -d --no-build`; `fleet-share-reconcile` is a default compose service. `bin/deploy.sh:11635-11637`; `bin/arclink-docker.sh:3373-3376`; `compose.yaml:1082-1094`
- REFINE §B37 sync convergence: no advisory lock and only two fetch/rebase/push attempts; under sustained concurrent writers it can return `status="error"` on a healthy hub, while preserving local commits. `python/arclink_fleet_share.py:309-363`
- CONFIRM LOW no-op: empty `deployment_id` in member removal returns `0` silently. `python/arclink_fleet_share.py:531-533`
- CONFIRM LOW probe transaction split: transition notification commits before the later audit insert/commit. `python/arclink_fleet_inventory_worker.py:263-270,428-438`; `python/arclink_control.py:8055-8071`
- CONFIRM LOW registry TOCTOU: `register_fleet_host` SELECTs then INSERTs without `IntegrityError` fallback despite UNIQUE hostname index. `python/arclink_fleet.py:189-192,238-248`; `python/arclink_control.py:2465-2466`
- REFUTE Section-2 `arclink_share_grants` as CANON-20: grant producer is API auth and consumer is pod_comms; CANON-20 fleet files are not on that path. `python/arclink_api_auth.py:3367-3374,3504-3589`; `python/arclink_pod_comms.py:92-110`; `python/arclink_control.py:1052-1069`
- REFINE `ARCLINK_FLEET_SHARED_ROOT` seam: CANON-20 consumes it for sync-local, provisioning sets it, and Drive/Code CANON-30 plugins do read fleet roots as writable roots. `python/arclink_fleet_share.py:738-755`; `python/arclink_provisioning.py:1342-1344`; `plugins/hermes-agent/drive/dashboard/plugin_api.py:843-848,893-909`; `plugins/hermes-agent/code/dashboard/plugin_api.py:595-605,662-664`

### New findings both Claude passes missed (severity + path:line)
- MEDIUM unchecked Fleet working path: `ARCLINK_FLEET_SHARED_ROOT`/`working_path` has no containment check, then `git add -A` stages the whole tree. A bad runtime env can commit/exfiltrate the wrong directory to the hub. `python/arclink_fleet_share.py:283-294,738-755`
- LOW fleet-share CRUD TOCTOU: `ensure_fleet_share` and `add_fleet_share_member` are SELECT-then-INSERT without `IntegrityError` fallback against UNIQUE owner/member constraints. `python/arclink_fleet_share.py:398-420,479-505`; `python/arclink_control.py:1092-1122`
- LOW Docker health omits CANON-20 jobs: health required-service list excludes `fleet-inventory-worker` and `fleet-share-reconcile`, so either can be stopped while health still passes required-service checks. `bin/arclink-docker.sh:26-49,719-727`; `compose.yaml:1065-1094`

### Claude citations re-confirmed or corrected
- Re-confirmed core owned files and line counts: `arclink_fleet.py` 723L, `arclink_fleet_inventory_worker.py` 547L, `arclink_fleet_share.py` 893L.
- Re-confirmed placement strength: `BEGIN IMMEDIATE`, unique active-placement fallback, and single load increment are real. `python/arclink_fleet.py:531-608`; `python/arclink_control.py:2497-2499`
- Re-confirmed reconcile/sync split: control reconcile is DB-only; in-pod `sync-local` performs git sync where the working copy lives. `python/arclink_fleet_share.py:607-654,719-765`; `python/arclink_provisioning.py:1327-1334`
- Corrected consolidated seam graph: `arclink_share_grants` belongs to CANON-02/12/01, not CANON-20. `python/arclink_api_auth.py:3367-3374`; `python/arclink_pod_comms.py:92-110`; `python/arclink_control.py:1052-1069`

### Residual disagreement with the Claude half (for final reconciliation)
- No disagreement with the verifier on §A15 or the four CANON-20 MEDIUM risks.
- Final CANON should move the `arclink_share_grants` seam out of CANON-20 and add the three missed defects above.
<<<CODEX-VERDICT-END CANON-20>>>
