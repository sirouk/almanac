# CANON-20 — Sharing & Fleet Folder

## PIECE
This piece owns three Python modules that together implement the Captain **fleet** layer
of ArcLink: the fleet host registry + deterministic placement, the periodic fleet probe
worker, and the read-write git-synced **Fleet shared folder**.
- `python/arclink_fleet.py` (723 lines) — fleet host registry CRUD (`register_fleet_host`,
  `update_fleet_host`, `list_fleet_hosts`), capacity/ASU accounting, host placement
  (`place_deployment`/`remove_placement`), eligibility/strategy logic, observed-load reconcile,
  and inventory/host orphan detection.
- `python/arclink_fleet_inventory_worker.py` (547 lines) — the periodic Sovereign probe worker:
  SSH-driven `liveness`/`capacity`/`inventory` probes, health-state transitions, capacity/ASU
  ingestion, probe-history retention, operator notifications.
- `python/arclink_fleet_share.py` (893 lines) — the Captain fleet shared folder: a git bare-hub +
  per-agent working-copy sync engine (`sync_member`, `sync_local_working_copy`), control-plane
  membership reconcile (`reconcile_fleet_share_membership`/`reconcile_all_fleet_shares`),
  control-plane CRUD over `arclink_fleet_shares`/`arclink_fleet_share_members`, and a CLI
  (`reconcile`/`sync`/`sync-local`).

**SCOPE CORRECTION (code wins).** The prior research doc `research/ground-truth/10-sharing-fleet-folder.md`
(its "Primary owning files" list, lines 6-21) treats this piece as the **share-grant /
Linked-resources / claim-nonce broker** subsystem. That subsystem lives in
`python/arclink_api_auth.py` + `python/arclink_hosted_api.py` (CANON-02), **not** in any of my
three files. Verified: `grep -n "pod_comms|share_grant|create_user_share|claim_nonce"` over all
three owned files returns **NONE**. My "sharing" is exclusively the **git Fleet folder**
(`arclink_fleet_share.py`), an entirely different mechanism from `arclink_share_grants`. The two
seams the task asked me to "name" (pod_comms grants → CANON-12, share-request broker route →
CANON-02) are therefore **absent from my code**; I document below where they actually originate.

The three files do NOT exist anywhere else; all three are tracked (`git ls-files`). I claim no
additional files (the adjacent `arclink_fleet_enrollment.py` is CANON-08, not mine).

## INPUT CONTRACT (code-verified)

### arclink_fleet.py (registry + placement)
- `register_fleet_host(conn, *, hostname, region="", tags=None, capacity_slots=10, host_id="", metadata=None)`
  (arclink_fleet.py:158). Requires non-empty `hostname` (lowercased; else `ArcLinkFleetError`,
  :169-170). `capacity_slots < 1` rejected (:186-187). `tags`/`metadata` run through
  `reject_secret_material` (:172-175, via `_reject_secrets`). Hostname is the upsert key
  (UNIQUE LOWER(hostname), control.py:2465). Caller: `arclink_inventory.py:174`.
- `update_fleet_host(conn, *, host_id, status=None, drain=None, observed_load=None, capacity_slots=None)`
  (:251). `status` must be in `FLEET_HOST_STATUSES={active,degraded,offline}` (:266-267);
  `observed_load < 0` rejected (:274-275); `capacity_slots < 1` rejected (:279-280). Unknown
  host_id → `ArcLinkFleetError` (:261-262).
- `place_deployment(conn, *, deployment_id, region="", required_tags=None)` (:518). Non-empty
  `deployment_id` required (:526-528); `required_tags` secret-scanned (:529). Idempotent: an
  existing active placement is returned as-is (:535-542). Caller: `arclink_sovereign_worker.py:1133`.
- `remove_placement(conn, *, deployment_id)` (:615); `get_deployment_placement` (:639);
  `list_fleet_hosts(conn, *, status="")` (:300); `fleet_capacity_summary(conn)` (:346);
  `reconcile_fleet_observed_loads(conn, *, host_id="")` (:388);
  `reconcile_fleet_inventory_orphans(conn)` (:457). These take only a connection + keyword filters.
- Pure helpers (host dict in → bool/int/str out, no validation beyond type-coercion):
  `host_is_placement_eligible` (:129), `host_available_placement_units` (:147),
  `fleet_host_ssh_endpoint` (:61), `fleet_host_ssh_user` (:81),
  `host_is_control_plane_reserve` (:94), `control_host_max_arcpod_slots` (:86).

### arclink_fleet_inventory_worker.py (probe worker)
- `process_due_hosts(conn, *, runner=None, now_iso="", cadences=None, force=False, notify=True, retention_per_host_kind=DEFAULT_RETENTION)`
  (:469). Default `runner` = `SshProbeRunner` built from env (:481-485). `cadences` merges over
  `DEFAULT_CADENCES={liveness:60,capacity:300,inventory:900}` (:480). No auth — this is a
  trusted-control-node worker invoked by compose (`fleet-inventory-worker` job, compose.yaml:1076)
  or `arclink_inventory.py:1201` with `force=True`.
- `record_host_probe(conn, *, host, kind, result, now_iso="", notify=True)` (:392). `kind` must be
  in `PROBE_KINDS` (`_clean_kind`, :50-54); `host["host_id"]` required (:402-404).
- `SshProbeRunner.__call__(host, kind)` (:171) — reads `host["ssh_host"|"hostname"]`,
  `host["ssh_user"]` (default `arclink`), runs `ssh ... -- arclink-fleet-probe-wrapper <kind>`.
- `probe_due` (:156), `prune_host_probes` (:442), `main(argv)` CLI (:525): `--once --force --json
  --notify --retention-per-host-kind`.

### arclink_fleet_share.py (git Fleet folder)
- `ensure_fleet_share(conn, *, owner_user_id, hub_ref="", folder_label="Fleet", access_mode="read-write", commit=True)`
  (:384). Non-empty owner required (:393-395); owner **must** exist in `arclink_users` else
  `KeyError(owner)` (:396-397). UNIQUE per owner (schema control.py:1094). Resolved hub defaults to
  `default_hub_ref(owner)` (:400). Caller: `arclink_sovereign_worker.py:913`.
- `add_fleet_share_member(conn, *, owner_user_id, deployment_id, working_path, role="member", commit=True)`
  (:463). Non-empty `deployment_id` required (:474-475). UNIQUE (share_id, deployment_id) → upsert
  to `active` (:483-495).
- `remove_fleet_share_member(conn, *, deployment_id, share_id="", commit=True)` (:519) — empty
  deployment is a silent no-op returning 0 (:531-533).
- `reconcile_fleet_share_membership(conn, *, owner_user_id, working_path_for=None, commit=True)`
  (:607); `reconcile_all_fleet_shares(conn, ...)` (:775); `run_fleet_share_cycle(conn, ...)` (:793).
- Git engine (injectable `runner`, default `SubprocessGitRunner`): `ensure_hub_repo(runner, hub_ref)`
  (:188), `ensure_member_working_copy(runner, *, hub_ref, working_path, branch="main")` (:233),
  `sync_member(runner, *, working_path, hub_ref, branch="main", deployment_id="", author_name, author_email, message="")`
  (:266), `sync_local_working_copy(runner=None, *, hub_ref="", working_path="", deployment_id="", ...)`
  (:719) — **env-driven, no control DB**, the in-pod entry point.
- All git refs/paths pass `_assert_safe_git_arg` (:123): empty → error, leading `-` → error
  (option-injection guard), embedded `\x00`/`\n`/`\r` → error.
- CLI `main(argv)` (:863): subcommands `reconcile [--user --all --interval]`,
  `sync [--user --no-reconcile --interval]`, `sync-local [--interval]`.

## OUTPUT CONTRACT (code-verified)

### DB writes
- `arclink_fleet_hosts` — INSERT on first register (:238-246); UPDATE region/capacity/tags/metadata
  on re-register (:228); `observed_load` ± on place/remove (:594-597, :632-634); status/health on
  probe (worker :289-298, :318-321); load repair (:419-422); capacity on probe (:356-363).
- `arclink_deployment_placements` — INSERT active placement (:577-583), UNIQUE one-active-per-deployment
  index (control.py:2497) → `IntegrityError` caught → returns existing (:584-593); status→removed (:627-630).
- `arclink_fleet_host_probes` — INSERT per probe (:407-423), pruned to retention (:445-462).
- `arclink_inventory_machines` — UPDATE status/connectivity/asu on probe (worker :300-303, :323-325,
  :356-389) — **note: cross-table write into a CANON-10 table**.
- `arclink_fleet_shares` — INSERT/UPDATE (:402-421); status flips `removed`→`active` on re-ensure (:405).
- `arclink_fleet_share_members` — INSERT/upsert active (:484-505); status→removed (:540-547);
  sync result fields (`last_sync_*`) (:563-570).
- Audit/event rows: `fleet_share_created` audit (:422-431), `fleet_share_member_joined` event
  (:506-513), `placement_assigned` event (:598-605), `fleet_host_probed` audit (:428-437),
  orphan-detected audits (:445-454, :488-508). All via CANON-01 `append_arclink_audit`/`append_arclink_event`.
- `notification_outbox` — operator notifications on host state transition (:263-270 via CANON-01
  `queue_notification`).

### Filesystem writes (git Fleet folder)
- Bare hub repo `git init --bare -b main <hub_path>` for local hub refs only (:204-205).
- Working copy clone/init at `working_path` (:253, :259); corrupt `.git` quarantined to
  `<name>.corrupt[-N]` then re-cloned (:143-152, :251).
- Default fleet layout: dirs `Projects/Research/Repos/Agents_KB/Agents_Skills/Agents_Plugins`
  each with a `README.md` (`FLEET_LAYOUT_READMES`, :47-54; `ensure_default_fleet_layout`, :211-230) —
  **additive, never overwrites** (existence-guarded, :223/:227).
- git side effects: `add -A`, `commit`, `fetch`, `rebase origin/main`, `push HEAD:main` (:294-345).

### Return shapes
- `FleetShareSyncResult(deployment_id, status∈{synced,conflict,error}, head_commit, committed,
  pushed, pulled, detail)` (:155-163).
- `ProbeResult(ok, payload, error, latency_ms)` (:33-38).
- `place_deployment` → placement row dict (`placement_id, deployment_id, host_id, status, placed_at`).
- `fleet_capacity_summary` → aggregate dict with per-host ASU/headroom (:355-385).

### Wire (subprocess argv)
- `["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=accept-new", (UserKnownHostsFile?), (-i key?),
  "<user>@<host>","--","arclink-fleet-probe-wrapper","<kind>"]` (worker :179-184).
- `["git", *args]` via `SubprocessGitRunner.run` (fleet_share.py:101-116, :119-120).

## TOUCH POINTS

### Env vars (read directly in my files)
- `arclink_fleet.py`: `ARCLINK_CONTROL_HOST_MAX_ARCPOD_SLOTS` (:22, default 2),
  `ARCLINK_FLEET_PLACEMENT_STRATEGY` (:720, `headroom`|`standard_unit`, default `headroom`).
- `arclink_fleet_inventory_worker.py`: `ARCLINK_FLEET_PROBED_MAX_CAPACITY_SLOTS` (:85, default 64),
  `ARCLINK_DOCKER_MODE` (:118), `ARCLINK_FLEET_SSH_KEY_PATH` (:482),
  `ARCLINK_FLEET_SSH_KNOWN_HOSTS_FILE` (:483), `ARCLINK_FLEET_PROBE_TIMEOUT_SECONDS` (:484),
  `ARCLINK_FLEET_PROBE_RETENTION` (:531).
- `arclink_fleet_share.py`: `ARCLINK_FLEET_SHARE_HUB_URL` (:179, supports `{user}` template),
  `ARCLINK_FLEET_SHARE_HUB_ROOT` (:184, default `/arcdata/captains`),
  `ARCLINK_FLEET_SHARED_ROOT` (:739), `ARCLINK_DEPLOYMENT_ID`/`DRIVE_OWNER_DEPLOYMENT_ID`/
  `ARCLINK_OWNER_DEPLOYMENT_ID` (:742-744), `ARCLINK_STATE_ROOT_BASE` (:603).

### DB tables (schema cites in arclink_control.py)
- `arclink_fleet_shares` (1092-1102, UNIQUE owner_user_id, CHECK status active/paused/removed),
  `arclink_fleet_share_members` (1104-1122, UNIQUE share_id+deployment_id),
  `arclink_fleet_hosts` (2349-2364, UNIQUE LOWER(hostname)),
  `arclink_deployment_placements` (2369-2376, UNIQUE one active per deployment idx 2497),
  `arclink_fleet_host_probes` (2440-2449). Cross-table reads/writes:
  `arclink_inventory_machines`, `arclink_deployments`, `arclink_users` (CANON-01/08/10).

### Files/paths
- Hub: `<ARCLINK_FLEET_SHARE_HUB_ROOT>/<user>/fleet-shared.git` (:185).
- Working copy: `<state_root>/fleet-shared` (state-root key `fleet_shared`,
  provisioning.py:420); container `/fleet-shared` (`CONTAINER_FLEET_SHARED_DIR`).
- Container hub bind `/fleet-share-hub.git` (`CONTAINER_FLEET_SHARE_HUB_DIR`).
- Linked manifest `.arclink-linked-resources.json` — **NOT** written here (CANON-02).

### Sockets/ports/subprocess/external services
- `ssh` to fleet hosts (port via probe wrapper, not here), `git` subprocess. No listening sockets.
- External: SSH key + known_hosts for remote git hub (provisioned out of band, :201-208).

### Secrets handling
- `register_fleet_host` rejects secret material in tags/metadata (:172-175).
- Probe worker redacts: `_redact_json_value` masks `*token/secret/password/api_key/credential/
  authorization*` keys (:57-73), `redact_secret_material`/`redact_then_truncate` on fingerprint &
  errors (:387, :406, :511, :542). `machine_fingerprint` redacted before store (:387).
- Fleet-share git uses the worker SSH identity; no secrets stored in DB by these files.

### Locks/concurrency
- `place_deployment` uses `BEGIN IMMEDIATE` write-lock + `IntegrityError` fallback on the
  one-active-placement unique index (:531-593).
- Fleet-share sync has **no lock**: multi-writer convergence is via git fetch+rebase+retry loop
  (:309-355); `process_due_fleet_share_syncs` dedupes hub init per pass via `hub_seen` set (:674,690).

## CODE-PATH TRACE

### Trace A — a fleet-share *grant* (the actual git folder lifecycle, end-to-end)
1. **Provision-time hub creation.** `arclink_sovereign_worker.py:793` calls
   `_ensure_deployment_fleet_share_hub` (:909) → `ensure_fleet_share(conn, owner_user_id=user_id)`
   (fleet_share.py:384). Owner verified in `arclink_users` (:396); row INSERTed into
   `arclink_fleet_shares` with `hub_ref = default_hub_ref(owner)` (:400, :413-421); audit
   `fleet_share_created` (:422). Then `ensure_hub_repo(SubprocessGitRunner(), hub_ref)`
   (sovereign:916 → fleet_share.py:188) `git init --bare` for a local hub (:204-205).
2. **Membership reconcile (control-node, DB-only).** Compose job `fleet-share-reconcile`
   (compose.yaml:1082-1094) runs `python3 python/arclink_fleet_share.py reconcile --all` every 120s
   → `main` (:863) → `_run_once` (:851-853) → `reconcile_all_fleet_shares` (:775) →
   `reconcile_fleet_share_membership` (:607). Active deployments
   (`active/provisioning/provisioning_ready/running`, :585) become `active` members via
   `add_fleet_share_member` (:640); working path resolved by
   `default_working_path_for_deployment` reading `metadata.state_roots.fleet_shared` (:593-604).
   Torn-down deployments deregistered (:649-651). **Hub never touched** (:616-618 docstring; only
   member rows mutated).
3. **In-pod git sync (the cross-machine grant materialization).** Per-agent compose job
   `fleet-share-sync` (provisioning.py:1327-1334) runs
   `docker-job-loop.sh fleet-share-sync 120 python3 python/arclink_fleet_share.py sync-local` →
   CLI `sync-local` → `sync_local_working_copy()` (:719). Reads `ARCLINK_FLEET_SHARE_HUB_URL` +
   `ARCLINK_FLEET_SHARED_ROOT` (:738-739); rejects unresolved `{user}` template (:751-754);
   `ensure_member_working_copy` clones/repairs (:755 → :233); `sync_member` (:756 → :266):
   `add -A` (:294) → commit if dirty (:298-307) → for ≤2 attempts: fetch (:310) → rebase
   `origin/main` (:324) → push `HEAD:main` (:345). Conflict → `rebase --abort` + status `conflict`,
   local edit preserved (:325-333). Returns `FleetShareSyncResult`.
4. **Result printed as JSON** by `_run_once` (:842-848). The co-located path
   `process_due_fleet_share_syncs` (:657) additionally writes `last_sync_*` back to the member row
   via `record_fleet_share_sync` (:706-713).

### Trace B — a fleet host probe (worker → state transition → notify)
1. Compose `fleet-inventory-worker` (compose.yaml:1076) runs the module `--once --json --notify`
   every 30s → `main` (:525) → `process_due_hosts` (:469).
2. `_host_rows` joins `arclink_fleet_hosts` ⨝ `arclink_inventory_machines` (:202-212), normalizes
   ssh endpoint via `fleet_host_ssh_endpoint` (arclink_fleet.py:61), flags docker-local-starter (:223).
3. For each host×kind, `probe_due` checks cadence (:489). `SshProbeRunner.__call__` (:171) runs
   `ssh ... arclink-fleet-probe-wrapper <kind>`; parses JSON (:194-199).
4. `record_host_probe` (:392) INSERTs probe row (:407), then `liveness` → `_apply_liveness_state`
   (:424): ok → host `active`/`last_health_state='active'` (:289-298), machine `ready`;
   fail → escalation by consecutive-failure count (≥10 offline/unreachable, ≥3 degraded, else
   probing_failed, :308-321). `capacity`/`inventory` → `_apply_capacity_or_inventory` (:339):
   `compute_asu(hardware)` (asu.py:42) + `current_load` (asu.py:64) written to machine.
5. State transition fires `_notify_transition` (:255) → `queue_notification` (control.py:8055)
   into `notification_outbox`.
6. `prune_host_probes` keeps `retention_per_host_kind` newest per (host,kind) (:442-466).

## CROSS-PIECE CONTRACTS (both ends verified)

1. **→ CANON-24/25 (compose job runner).** Producer: compose.yaml:1091 & provisioning.py:1329 emit
   argv `[..., "python3", "python/arclink_fleet_share.py", "<verb>"]`; `bin/docker-job-loop.sh`
   takes `JOB_NAME INTERVAL` then `shift 2` (:9-11) and execs the remainder. Consumer: my CLI
   `main`/`_run_once` (fleet_share.py:863, :841). Contract = exact subcommand strings
   `reconcile --all` / `sync-local`. **BOTH-ENDS-VERIFIED: yes.**

2. **← CANON-08 (sovereign worker → ensure_fleet_share / ensure_hub_repo).** Producer:
   `arclink_sovereign_worker.py:913,916` calls `ensure_fleet_share(conn, owner_user_id=user_id)` and
   `ensure_hub_repo(SubprocessGitRunner(), hub_ref)`. Consumer: my functions at fleet_share.py:384,188.
   Contract = `owner_user_id` (a row in `arclink_users`) + returned dict carrying `hub_ref`.
   **BOTH-ENDS-VERIFIED: yes** (sovereign reads `share.get("hub_ref")` at :914; I return it at :412).

3. **← CANON-08 (sovereign worker → place_deployment / remove_placement).** Producer:
   `arclink_sovereign_worker.py:1133,887,1395`. Consumer: arclink_fleet.py:518,615. Contract =
   `deployment_id` in, placement dict out with key `host_id` (sovereign reads `placement["host_id"]`
   at :1189,:1301,:1492 and `_host_for_placement` at :1974). **BOTH-ENDS-VERIFIED: yes.**

4. **← CANON-10 (inventory → register_fleet_host / process_due_hosts).** Producer:
   `arclink_inventory.py:174` calls `register_fleet_host(...)` and reads `host["host_id"]` (:181);
   `arclink_inventory.py:1201-1203` imports + calls `process_due_hosts(conn, force=True, notify=...)`.
   Consumer: arclink_fleet.py:158, worker:469. **BOTH-ENDS-VERIFIED: yes.**

5. **→ CANON-31/24 (probe worker → arclink-fleet-probe-wrapper over SSH).** Producer: worker emits
   argv `... -- arclink-fleet-probe-wrapper <kind>` (:184). Consumer: `bin/arclink-fleet-probe-wrapper`
   emits JSON with keys `ok,kind,admitting,hostname,ssh_port,observed_at` + (capacity/inventory)
   `hardware_summary{vcpu_cores,ram_gib,disk_gib,docker_version,docker_compose_version}` +
   (inventory) `machine_fingerprint` (wrapper:53-71). Worker reads exactly those keys
   (`payload.get("ok")` :199, `hardware_summary`/`capacity_slots`/`machine_fingerprint` worker:349-387).
   **BOTH-ENDS-VERIFIED: yes** (key-by-key match).

6. **→ CANON-10 (worker → compute_asu / current_load).** Producer: worker:367-368 passes
   `hardware` (dict) to `compute_asu` and `machine_id` to `current_load`. Consumer: arclink_asu.py:42
   (`compute_asu(hardware_summary)`→int) and :64 (`current_load(machine_id, conn)`→float). Worker
   casts both to float at :377-378. **BOTH-ENDS-VERIFIED: yes.**

7. **→ CANON-01 (audit/event/notification sinks).** `append_arclink_audit`(control.py:4649),
   `append_arclink_event`(:3870), `queue_notification`(:8055). My call sites supply keyword args
   matching each signature; `queue_notification(extra=...)` keys flow into `notification_outbox.extra_json`.
   **BOTH-ENDS-VERIFIED: yes** (signatures read at the cited lines).

8. **→ CANON-19/03 (Drive/Code "Fleet" root env).** Producer: provisioning.py:1342-1344,1623-1625
   set `ARCLINK_FLEET_SHARED_ROOT`/`DRIVE_FLEET_SHARED_ROOT`/`CODE_FLEET_SHARED_ROOT` =
   `/fleet-shared`. Consumer of `ARCLINK_FLEET_SHARED_ROOT` here: `sync_local_working_copy` (:739).
   The Drive/Code plugin consumption of `*_FLEET_SHARED_ROOT` is CANON-30 (not my code).
   **BOTH-ENDS-VERIFIED: partial** — I verified the producer and my own consumption of
   `ARCLINK_FLEET_SHARED_ROOT`; the Drive/Code plugin's read of `DRIVE/CODE_FLEET_SHARED_ROOT` is in
   CANON-30 and out of my scope (flagged for Codex).

9. **NON-SEAM — pod_comms grants (CANON-12) & share-request broker route (CANON-02).** The task
   asked me to name these. **They do NOT cross any of my files.** `pod_comms`, `arclink_share_grants`,
   `create_user_share_grant_*`, `claim_share_nonce_*`, `X-ArcLink-Share-Request-Broker-Token` —
   none appear in my three files (verified by grep). They originate in `arclink_api_auth.py` /
   `arclink_hosted_api.py` / `arclink_pod_comms.py`. **BOTH-ENDS-VERIFIED: N/A (no seam in my code).**

## CODE vs COMMENT/DOC/NAME DRIFT

1. **`fleet-share-reconcile` control-node job DOES exist (prior doc overclaim, now reversed).**
   `research/ground-truth/10-sharing-fleet-folder.md` §D.1 (lines 248-254) states the control-node
   compose job "does NOT exist" and that `reconcile --all` has "no scheduler/service wiring
   anywhere." **Refuted by code:** `compose.yaml:1082-1094` defines service `fleet-share-reconcile`
   running `python3 python/arclink_fleet_share.py reconcile --all` every 120s. The prior doc was
   correct on 2026-05-30 but is now stale; the job was added afterward. **CODE WINS.**

2. **Prior doc's owning-files list is wrong for this piece (scope drift).** §"Primary owning files"
   lists `arclink_api_auth.py`, `arclink_hosted_api.py`, `arclink_control.py`, `arclink_provisioning.py`,
   `arclink_executor.py`, `arclink_sovereign_worker.py`, `arclink_mcp_server.py`, `arclink_public_bots.py`,
   plus plugin files — **none of which are CANON-20 files.** The CANON-20 trio (`arclink_fleet.py`,
   `arclink_fleet_inventory_worker.py`, `arclink_fleet_share.py`) is barely the subject of that doc
   (only §A "Fleet shared folder" covers `arclink_fleet_share.py`; the host-registry and probe-worker
   modules are entirely uncovered there). The doc conflates the git Fleet folder with the share-grant
   subsystem.

3. **`paused` fleet-share status is dead (schema/validator only).** Schema CHECK allows `paused`
   (control.py:1098), validator `ARCLINK_FLEET_SHARE_STATUSES` includes it (control.py:3179), but
   **no code path in fleet_share.py sets `paused`** (verified grep). `ensure_fleet_share` only sets
   `active` and flips `removed`→`active` (:405); members only `active`/`removed`. Prior doc §D.4
   already noted this — confirmed.

4. **`pending` member status is dead.** Schema allows `pending` (control.py:1111) but
   `add_fleet_share_member` always inserts `'active'` (:502); the `pending` lifecycle is never used.

5. **Module name vs scope.** `arclink_fleet.py` docstring says "fleet host registry and
   deterministic placement" (:2) — accurate; but the file ALSO owns inventory/host orphan auditing
   (`reconcile_fleet_inventory_orphans`, :457) which the docstring omits. Minor name/coverage drift.

6. **Comment "args are constructed internally, never from user text" (fleet_share.py:103)** is
   load-bearing and true for control-plane callers, but `sync_local_working_copy` reads `hub_ref`
   from `ARCLINK_FLEET_SHARE_HUB_URL` (env), which is operator-controlled, not literally code —
   `_assert_safe_git_arg` is the actual guard (option-injection only; it does NOT validate the URL
   scheme/host). See RISKS.

## ADVERSARIAL SELF-CHECK
1. **"`fleet-share-reconcile` runs reconcile --all on the control node."** I read compose.yaml:1091
   directly. Falsifier: if `docker-job-loop.sh` rejected/altered the verb, or the service is never
   `up`'d in the real deploy. The argv is literal; loop execs `shift 2` remainder verbatim (verified).
   I did NOT verify the service is actually enabled in every deploy profile.
2. **"No pod_comms/share-grant code in my files."** Verified by grep returning NONE across all three.
   Falsifier: an indirect import that re-exports those symbols — I checked imports (only
   `arclink_boundary`, `arclink_control`, `arclink_asu`, `arclink_fleet`); none pull share-grant code.
3. **"Probe wrapper keys match worker reads exactly."** I read both ends. Falsifier: a key the
   worker reads that the wrapper omits (e.g. `observed_load` — wrapper does NOT emit it for SSH
   hosts; only the docker-local-starter synthetic probe sets it, worker:148). For real SSH capacity
   probes `observed_load` falls back to `_active_placement_count` (worker:354) — so a missing key is
   handled, not a break. Confirmed safe.
4. **"sync_member never clobbers a peer's writes."** I traced rebase→abort→`conflict`. Falsifier: a
   force-push or `rebase --skip`. No `--force`/`-f` push anywhere; push is plain `HEAD:main` (:345).
   But a non-fast-forward AFTER successful rebase, looped twice then `error` — I did NOT prove the
   2-attempt bound always converges under heavy contention (it may report `error` spuriously).
5. **"`compute_asu` returns int, cast to float — no precision loss."** True; but `compute_asu` can
   raise `ArcLinkASUError` (asu.py:58) if `vcpu<=0`. `_apply_capacity_or_inventory` does NOT wrap
   that call in try/except (worker:367) — an asu error would propagate out of `record_host_probe`
   and abort the whole probe pass for that host. Possible fail-open-to-crash; flagged as a risk.

## OPEN FOR CODEX FEDERATION
1. Confirm whether `fleet-share-reconcile` (compose.yaml:1082) is actually started in the production
   deploy lane (deploy.sh / `docker compose up` profile), or only defined. Prior doc claimed the job
   did not exist; I proved it is defined. Is it *enabled*?
2. The Drive/Code plugin end of the `Fleet` writable root (`DRIVE/CODE_FLEET_SHARED_ROOT`) lives in
   CANON-30 — confirm the plugin actually treats `/fleet-shared` as read-write and surfaces conflicts.
3. `sync_member`'s 2-attempt rebase/push loop (fleet_share.py:309-355): does this converge under N
   concurrent writers, or can it return `status="error"` while the hub is healthy (lost update vs
   surfaced error)? Worth an independent concurrency model check.
4. `_apply_capacity_or_inventory` calls `compute_asu` un-guarded (worker:367); does a malformed
   `hardware_summary` from a compromised/buggy probe wrapper crash the worker pass for all hosts?
5. Verify there is no other scheduler (systemd timer) ALSO running fleet-share sync/reconcile that
   could race the compose jobs.

## RISKS (severity-ranked, code-cited)
- **MEDIUM — Fleet hub durability single-point-of-failure.** The hub is one bare repo
   (`default_hub_ref`, fleet_share.py:171-185); losing the hub host loses the entire Fleet folder.
   No replication/backup in code. `ensure_hub_repo` returns `True` for remote refs **without
   verifying reachability** (:198-200), so a misconfigured remote silently "succeeds" and every
   sync then soft-errors. Cite: fleet_share.py:188-208.
- **MEDIUM — `_assert_safe_git_arg` does not validate hub URL scheme/host.** It only blocks leading
   `-` and control chars (fleet_share.py:123-136). `ARCLINK_FLEET_SHARE_HUB_URL` is operator/env
   controlled and flows into `git clone`/`fetch`/`push` (sync_local_working_copy:738). A hostile env
   value (e.g. `ext::sh -c ...` is blocked by the `-` rule, but `ssh://attacker/...` is not) could
   redirect sync to an attacker repo. Trust boundary = whoever sets the env. Cite: fleet_share.py:738,123.
- **MEDIUM — `compute_asu` un-guarded in probe ingestion.** `_apply_capacity_or_inventory` (worker:367)
   calls `compute_asu(hardware)` which raises on `vcpu<=0` (asu.py:58); not wrapped, so a single bad
   capacity probe payload aborts `record_host_probe` (worker:427) → the whole `process_due_hosts`
   pass exits via the broad `except Exception` only at the per-probe call (worker:497-500 wraps the
   *runner* call, not `record_host_probe`). A poisoned probe JSON can break the pass. Cite:
   worker:367, :501.
- **LOW — Multi-writer sync has no advisory lock; relies on git rebase + 2 retries.** Under heavy
   concurrent writes the loop may exhaust retries and return `status="error"` even though the hub is
   healthy (lost-write surfaced as error). Conflicts are surfaced not clobbered (good), but the bound
   is fixed at 2. Cite: fleet_share.py:309-363.
- **LOW — Corrupt-working-copy quarantine can accumulate `.corrupt-N` dirs unbounded.**
   `_quarantine_corrupt_working_copy` never garbage-collects (fleet_share.py:143-152); repeated
   corruption fills the state volume. Cite: fleet_share.py:148-151.
- **LOW — `remove_fleet_share_member` empty-deployment silent no-op.** Returns 0 with no audit/log
   (fleet_share.py:531-533); a caller bug passing empty id is invisible. Cite: fleet_share.py:531.
- **INFO — `paused` and member-`pending` statuses are dead code in schema/validators** (no setter).
   Cite: control.py:1098,1111; fleet_share.py:405,502.
- **INFO — `process_due_fleet_share_syncs` is co-located only** (it runs git where the DB lives,
   fleet_share.py:657); the real cross-machine path is the per-pod `sync-local`, so the co-located
   helper only works for single-host deployments. Documented in docstring (:729-735). Cite:
   fleet_share.py:657, :719.

## VERDICT
This piece provably does its job. **Strengths (load-bearing, code-verified):**
(1) Placement is concurrency-safe — `BEGIN IMMEDIATE` + unique-index `IntegrityError` fallback make
double-placement impossible (fleet_share-host place_deployment:531-593). (2) The probe worker's
health FSM, redaction, and retention are real and exercised by 48 passing tests; secret material is
rejected at registry ingress and redacted at probe egress. (3) The Fleet git folder genuinely
implements multi-writer convergence with conflict-surfacing (never clobber): rebase-or-abort
(:325-333), quarantine-and-reclone instead of wedging (:251), and a hub that is never touched by
membership changes so removing any agent can't orphan the folder (:519-550). (4) The control-plane
reconcile / in-pod sync split is correct (DB-only on the control node, git only where the working
copy physically lives), and — contrary to the prior research doc — the control-node
`fleet-share-reconcile` compose job now exists. **Real weaknesses:** hub is a single point of
failure with no replication and no reachability check on remote refs; the hub URL guard is
option-injection-only (no scheme/host validation); and one un-guarded `compute_asu` call can crash a
probe pass. The biggest *documentation* failure is in the prior ground-truth doc, which mis-scopes
this piece as the share-grant subsystem (which lives in CANON-02/12, with zero code overlap here)
and asserts a control-node job "does not exist" that demonstrably does.
