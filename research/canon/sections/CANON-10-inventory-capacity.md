# CANON-10 — Cloud Inventory & Capacity

## PIECE
This piece is the control-node **inventory registry** and **capacity arithmetic** for
ArcLink's fleet. It owns exactly five tracked files:
- `python/arclink_inventory.py` (1299 lines) — the registry CRUD + cloud lifecycle +
  SSH probe + `arclink-inventory` CLI; the only module that *writes*
  `arclink_inventory_machines`.
- `python/arclink_inventory_hetzner.py` (119 lines) — fail-closed Hetzner Cloud HTTP
  adapter; `HetznerInventoryProvider`.
- `python/arclink_inventory_linode.py` (118 lines) — fail-closed Linode HTTP adapter;
  `LinodeInventoryProvider`.
- `python/arclink_asu.py` (83 lines) — ArcPod Standard Unit (ASU) math: `compute_asu`
  (hardware -> pod count) and `current_load` (machine -> active placement count).
- `python/arclink_resource_map.py` (111 lines) — pure string builders for shared
  tailnet host + agent-facing "resource rail" lines. (Note: despite the file name this
  is NOT cloud-resource mapping; it maps *human/agent access URLs*. See DRIFT.)
Together they: take a provider's hardware summary, compute how many standard pods a box
fits (`compute_asu`), persist machine rows, and surface `asu_capacity`/`asu_consumed`
that the placement engine (CANON-08 `arclink_fleet.py`) consumes. The five files were
co-located by the prompt; `arclink_resource_map.py` is functionally adjacent to
onboarding/control, not to inventory, but is correctly listed and is claimed here.

## INPUT CONTRACT (code-verified)

### `arclink_asu.compute_asu(hardware_summary, env=None) -> int` (`arclink_asu.py:42`)
- `hardware_summary: Mapping[str, Any]`. `_number()` (`arclink_asu.py:28`) reads the
  first present, non-`None`/non-`""` key from each tuple:
  - vCPU: `("vcpu_cores", "vcpus", "cpu_count", "nproc")` (`arclink_asu.py:53`)
  - RAM: `("ram_gib", "memory_gib", "memory_total_gib")` (`arclink_asu.py:54`)
  - disk: `("disk_gib", "disk_total_gib", "root_disk_gib")` (`arclink_asu.py:55`)
  Missing -> `ArcLinkASUError("hardware summary missing <label>")` (`arclink_asu.py:39`).
  Non-numeric value -> `ArcLinkASUError("<label> must be numeric")` (`arclink_asu.py:38`).
- `env: Mapping[str,str] | None` defaults to `os.environ` (`arclink_asu.py:48`). Tunables
  `ARCLINK_ASU_VCPU_PER_POD` (1.0), `ARCLINK_ASU_RAM_PER_POD` (4.0),
  `ARCLINK_ASU_DISK_PER_POD` (30.0) via `_float_env` (`arclink_asu.py:15`,49-51);
  non-numeric or `<= 0` -> `ArcLinkASUError` (`arclink_asu.py:22-24`).
- Validation: `vcpu <= 0` raises (`arclink_asu.py:57`); `ram < 0 or disk < 0` raises
  (`arclink_asu.py:59`). RAM=0 or disk=0 do NOT raise but force result to 0 (floor of 0).
- Caller: anyone; no auth. Real callers `arclink_inventory.py:473`,
  `arclink_fleet_inventory_worker.py:367`.

### `arclink_asu.current_load(machine_id, conn) -> float` (`arclink_asu.py:64`)
- `machine_id: str` (stripped), `conn: sqlite3.Connection`. Unknown machine ->
  `ArcLinkASUError(f"unknown inventory machine: {machine_id}")` (`arclink_asu.py:71`).
- If `machine_host_link` empty: returns `asu_consumed` column verbatim
  (`arclink_asu.py:72-74`). Else returns COUNT of `arclink_deployment_placements` rows
  with `host_id = link AND status='active'` (`arclink_asu.py:75-83`).

### `arclink_inventory.register_inventory_machine(conn, *, provider, hostname, ...)` (`arclink_inventory.py:142`)
- `provider` -> `_clean_provider` allowlist `{local,manual,hetzner,linode}`
  (`arclink_inventory.py:55`); else raises.
- `hostname` REQUIRED, `_clean_host_value` lowercases, strips dots, rejects
  CR/LF/NUL and anything not matching `^[A-Za-z0-9][A-Za-z0-9_.:-]{0,254}$`
  (`arclink_inventory.py:42`,74-82).
- `status` -> `_clean_status` allowlist `{pending,ready,draining,degraded,removed}`
  (`arclink_inventory.py:69`).
- `region` -> `_clean_label` `^[A-Za-z0-9_.-]{0,96}$` (`arclink_inventory.py:44`,94).
- `ssh_host` -> `_clean_host_value` (optional). `ssh_user` -> `_SSH_USER_RE`
  `^[A-Za-z_][A-Za-z0-9_.-]{0,63}$` (`arclink_inventory.py:43`,85).
- `capacity_slots: int | None`. If `machine_host_link` empty AND `capacity_slots`
  given, auto-registers a fleet host with `max(1, int(capacity_slots))` (CANON-08 seam,
  `arclink_inventory.py:173-182`). NOTE: capacity_slots is a *slot* count, NOT ASU.
- `hardware_summary`/`connectivity_summary`/`tags`/`metadata` JSON-serialized via
  `_safe_json`/`json_dumps_safe` (`arclink_inventory.py:138`). Upsert keyed on
  `(provider, provider_resource_id|hostname)` (`arclink_inventory.py:184-193`).

### `create_cloud_inventory_machine(conn, *, provider, client, hostname, server_type, image, region, ...)` (`arclink_inventory.py:698`)
- `provider` -> `_clean_cloud_provider` (hetzner|linode only) (`arclink_inventory.py:60`).
- `hostname` lowercased+required (`:719-721`); `region` required (`:722-724`);
  `server_type` AND `image` required (`:725-728`). `capacity_slots` default 4, floored
  to `>=1` (`:729`). `client: Any` is an injected provider object (DI; the live one is
  built by `_cloud_provider_client`, `arclink_inventory.py:1041`).
- `bootstrap_runner: Callable | None` injected; `None` = operator-gated (no host
  mutation) (`:781`,785).

### `probe_inventory_machine(conn, *, key, fleet_key_path="", known_hosts_file="", runner=subprocess.run)` (`arclink_inventory.py:426`)
- `key` resolves via `get_inventory_machine` (machine_id OR hostname,
  `arclink_inventory.py:372-384`). `runner` injectable (defaults real
  `subprocess.run`). `fleet_key_path`/`known_hosts_file` from env at the CLI
  (`arclink_inventory.py:1196-1197`).

### `parse_probe_output(stdout) -> dict` (`arclink_inventory.py:387`)
- `stdout: str`. Line 0 MUST parse as int (nproc) else
  `ArcLinkInventoryError("probe output missing nproc result")` (`:392-394`); empty ->
  `ArcLinkInventoryError("empty probe output")` (`:390`).

### `arclink_resource_map` builders (all keyword-only, pure)
- `shared_tailnet_host(*, tailscale_serve_enabled: bool, tailscale_dns_name="", nextcloud_trusted_domain="") -> str` (`arclink_resource_map.py:8`).
- `shared_resource_lines(*, host, tailscale_serve_port="443", nextcloud_enabled, qmd_url, public_mcp_host, public_mcp_port, ...) -> list[str]` (`arclink_resource_map.py:23`).
- `managed_resource_lines(...)` / `managed_resource_ref(...) -> str` (`arclink_resource_map.py:64`,93).

### Hetzner/Linode provider constructors (`*_hetzner.py:19`, `*_linode.py:19`)
- `token` REQUIRED non-empty else `InventoryProviderError("<p> token missing")`
  (`*_hetzner.py:28-29`, `*_linode.py:28-29`). `base_url` defaults to the real API;
  `http_request_fn` injectable (DI for tests).

## OUTPUT CONTRACT (code-verified)

### `compute_asu` -> `int`
`max(0, int(min(floor(vcpu/vcpu_per_pod), floor(ram/ram_per_pod), floor(disk/disk_per_pod))))`
(`arclink_asu.py:61`). Binding capacity = the scarcest of the three resources.

### `register_inventory_machine` -> `dict` (full row)
Side effects: INSERT or UPDATE `arclink_inventory_machines` (`:196-252`); optional
`register_fleet_host` (`:174`); `append_arclink_audit(action="inventory_machine_registered")`
(`:253`); `conn.commit()` (`:262`). Returns the re-read row dict (`:263`).

### `probe_inventory_machine` -> `dict` (row)
Happy path UPDATE sets `status='ready'`, `asu_capacity=compute_asu(hardware)`,
`asu_consumed=current_load`, `hardware_summary_json`, `connectivity_summary_json={"ok":True,...}`,
`last_probed_at` (`:476-492`); if linked, `update_fleet_host(status='active',
observed_load=int(consumed))` (`:493-494`); audit `inventory_machine_probed` (`:495`).
**Unhappy paths (fail-closed):** OSError/SubprocessError OR non-zero returncode both
UPDATE `status='degraded'` + `connectivity_summary_json={"ok":False,"error":<redacted>}` +
`last_probed_at`, commit, then raise `ArcLinkInventoryError` (`:448-471`). Error text
passes `redact_then_truncate(...,240)`.

### `create_cloud_inventory_machine` -> `dict`
`{"status": <pending|degraded|existing>, "replay": bool, "machine": <row>}` (`:757`,823).
Side effects: durable idempotency rows
(`reserve/complete/fail_arclink_operation_idempotency`, kind
`inventory_<provider>_create`, `:731`,564); calls `client.provision_server(...)`
(`:770`,665-695); `register_inventory_machine(...)` (`:807`). On any exception:
`fail_arclink_operation_idempotency` then re-raise (`:833-842`).

### `remove_cloud_inventory_machine` -> `dict` (`:845`)
`{"status":"removed","replay":bool,"machine":<row>}`. Calls
`client.remove_server(resource_id, destroy=True)` (`:886`) then
`remove_inventory_machine` (`:887`). Requires `destroy=True` (`:859`) AND machine in
`{draining,removed}` unless `force` (`:861`). Idempotency kind
`inventory_<provider>_remove`.

### `parse_probe_output` -> dict
`{vcpu_cores:int, ram_gib:float, disk_gib:int, docker_version:str, docker_compose_version:str}`
(`:417-423`). Disk parsing is brittle: picks the max integer-GiB second field of a
`df -BG` line ending in `G` (`:411-416`); a value like `120G` -> 120 (no fractional).

### `fleet_inventory_health` -> dict (`:911`)
Aggregates `arclink_inventory_machines` by status, `arclink_fleet_hosts` by
state/region/health, `arclink_fleet_host_probes` totals, active capacity slots,
strategy from `ARCLINK_FLEET_PLACEMENT_STRATEGY`. Also EXPIRES pending enrollments and
verifies the fleet audit chain (delegated to CANON-08).

### Provider adapter `_server(row)` -> normalized dict
Both adapters emit the SAME shape (`*_hetzner.py:107-119`, `*_linode.py:106-118`):
`{provider, provider_resource_id, hostname, ssh_host, region, status,
hardware_summary:{vcpu_cores, ram_gib, disk_gib}}`. Hetzner takes `server_type`
cores/memory/disk raw (`*_hetzner.py:115-117`); Linode converts MB->GiB via
`round(mb/1024,2)` (`*_linode.py:104-105`,115-116). **WARNING:** Hetzner's
`server_type.memory`/`disk` are GiB/GB per the Hetzner API but the code copies them
without unit conversion (see ADVERSARIAL).

### `shared_resource_lines` / `managed_resource_ref`
Pure `list[str]` / `str` of rail lines; no side effects (`arclink_resource_map.py:37-61`,
99-111).

## TOUCH POINTS

### Env vars (read)
- `ARCLINK_ASU_VCPU_PER_POD`, `ARCLINK_ASU_RAM_PER_POD`, `ARCLINK_ASU_DISK_PER_POD`
  (`arclink_asu.py:49-51`).
- `ARCLINK_FLEET_PLACEMENT_STRATEGY` (`arclink_inventory.py:969`).
- `ARCLINK_FLEET_SSH_KEY_PATH`, `ARCLINK_FLEET_SSH_KNOWN_HOSTS_FILE`
  (`arclink_inventory.py:1196-1197`).
- `HETZNER_API_TOKEN`, `LINODE_API_TOKEN` (`arclink_inventory.py:1043`,1046-1048).
- `USER` (CLI re-attest actor default, `arclink_inventory.py:1166`).
- resource_map env is read by *callers* (onboarding/control), not by the module itself.

### DB tables
- `arclink_inventory_machines` — r/w. Schema `arclink_control.py:1413-1435`
  (`machine_id PK`, `provider CHECK IN (local,manual,hetzner,linode)`,
  `status CHECK IN (pending,ready,draining,degraded,removed)`, `asu_capacity REAL`,
  `asu_consumed REAL`, `hardware_summary_json`, `machine_host_link`, ...). This piece is
  the sole writer of capacity columns.
- `arclink_deployment_placements` — READ only here. Schema `arclink_control.py:2369-2376`
  (`status CHECK IN (active,removed)`). `current_load` + `remove_inventory_machine`
  COUNT active rows (`arclink_asu.py:75`, `arclink_inventory.py:530`).
- `arclink_fleet_hosts` — read in `fleet_inventory_health` (`:923`); writes are delegated
  to CANON-08 (`register_fleet_host`, `update_fleet_host`).
- `arclink_fleet_host_probes` — read-only aggregate (`:947`).
- `arclink_operation_idempotency` — via the reserve/complete/fail helpers (CANON-01).
- `arclink_audit` — via `append_arclink_audit`.

### Sockets / subprocess / external services
- SSH subprocess in `probe_inventory_machine`: argv
  `["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=accept-new", (UserKnownHostsFile?), (-i key?), "<user>@<host>","--","nproc; cat /proc/meminfo | head -3; df -BG / /var/lib/docker 2>/dev/null; docker --version; docker compose version"]`
  (`arclink_inventory.py:439-445`), `timeout=30`, `check=False`.
  `StrictHostKeyChecking=accept-new` = TOFU (see RISKS).
- HTTPS to `api.hetzner.cloud/v1` and `api.linode.com/v4` via `http_request`,
  `timeout=20`, `allow_loopback_http=False` (SSRF guard) (`*_hetzner.py:40-47`).

### Secrets handling
- Provider token sent as `Authorization: Bearer <token>` (`*_hetzner.py:43`). On HTTP
  error the body is `response.text.replace(self._token,"[REDACTED]")` then
  `redact_then_truncate` (`*_hetzner.py:51`). Exceptions caught and redacted (`:49`).
- `_redacted_mapping` redacts bootstrap result before persisting
  (`arclink_inventory.py:573-580`,797-800). On bootstrap failure NO detail is stored,
  only `"bootstrap failed; sensitive detail redacted"` (`:802-805`).

## CODE-PATH TRACE — cloud create end-to-end (`add hetzner --hostname ...`)
1. CLI `main` routes `add hetzner` -> `_cmd_add_cloud` (`arclink_inventory.py:1178-1179`).
2. `_cloud_provider_client("hetzner")` reads `HETZNER_API_TOKEN`, lazy-imports
   `HetznerInventoryProvider` (`:1041-1048`). Missing token -> constructor raises
   `InventoryProviderError("hetzner token missing")` -> printed, exit 1 (`:1055-1057`).
3. `create_cloud_inventory_machine(...)` validates provider/hostname/region/type/image
   (`:715-728`).
4. `replay_arclink_operation_idempotency(kind="inventory_hetzner_create", key)` — if a
   terminal row exists with matching intent digest, returns it with `replay=True`
   (`:746-753`; producer `arclink_control.py:3333`).
5. `_existing_cloud_machine` short-circuits if a non-removed machine with that hostname
   exists (`:755-757`).
6. `reserve_arclink_operation_idempotency(status="running")` — claims the slot; if it was
   already terminal, replay (`:759-767`).
7. `_call_provider_create("hetzner", client, ...)` -> `client.provision_server(name=,
   server_type=, image=, location=region, ssh_keys=)` (`:770`,675-684).
8. `HetznerInventoryProvider.provision_server` POSTs `/servers`, then `_server(...)`
   normalizes the response into the `{provider, ..., hardware_summary}` shape
   (`*_hetzner.py:66-82`,100-119).
9. Back in create: `resource_id = server["provider_resource_id"]`; metadata records
   bootstrap status (`operator_gated` when no runner) and the redacted intent
   (`:779-783`).
10. `register_inventory_machine(provider="hetzner", hostname, ssh_host=server.ssh_host,
    status="pending", hardware_summary=server["hardware_summary"],
    connectivity_summary={"ok":False,"status":"awaiting_fleet_probe"},
    capacity_slots=slots, metadata=...)` -> upserts the row, auto-registers a fleet host
    (capacity_slots), audits, commits (`:807-822`).
11. `complete_arclink_operation_idempotency(result=result, provider_refs={provider_resource_id})`
    marks the idempotency row succeeded (`:824-831`; consumer `arclink_control.py:3352`).
12. Returns `{"status":"pending","replay":False,"machine":<row>}`; CLI prints JSON
    (`:1080`).
Capacity is NOT computed here — `asu_capacity` stays 0 until a later
`probe_inventory_machine` or the fleet inventory worker runs `compute_asu`.

## CODE-PATH TRACE — probe -> capacity (the hardware-summary -> compute_asu -> decision arc)
1. `probe_inventory_machine(conn, key=...)` resolves the machine and SSH host/user
   (`:434-438`).
2. Runs the SSH probe (`:446-447`); failure paths mark `degraded` + raise (`:448-471`).
3. `parse_probe_output(completed.stdout)` -> `{vcpu_cores, ram_gib, disk_gib, ...}`
   (`:472`,387).
4. `asu_capacity = compute_asu(hardware)` (`:473`) — reads `vcpu_cores`/`ram_gib`/`disk_gib`
   (producer keys at `:417-419` exactly match consumer key tuples at
   `arclink_asu.py:53-55`).
5. `consumed = current_load(machine_id, conn)` -> active placement COUNT (`:474`,
   `arclink_asu.py:64`).
6. UPDATE row `status='ready', asu_capacity, asu_consumed` (`:476-492`).
7. CAPACITY DECISION (downstream, CANON-08): `arclink_fleet.list_fleet_hosts` joins the
   linked machine and reads `asu_capacity`/`asu_consumed` (`arclink_fleet.py:314-337`);
   `_host_has_capacity` / `_host_capacity` decide placement when
   `ARCLINK_FLEET_PLACEMENT_STRATEGY == "standard_unit"` using `asu_available`
   (`arclink_fleet.py:142-150`,700-701). **Seam to CANON-08 verified both ends.**

## CROSS-PIECE CONTRACTS (both ends verified)

1. **Provider adapter -> compute_asu (within piece, both ends).** Producer
   `_server.hardware_summary` keys `vcpu_cores`/`ram_gib`/`disk_gib`
   (`*_hetzner.py:114-118`, `*_linode.py:113-117`); consumer `_number` first-choice keys
   are exactly those (`arclink_asu.py:53-55`). BOTH-ENDS-VERIFIED: yes.

2. **parse_probe_output -> compute_asu (within piece, both ends).** Producer keys at
   `arclink_inventory.py:417-419`; consumer `arclink_asu.py:53-55`. Exact match.
   BOTH-ENDS-VERIFIED: yes.

3. **compute_asu/current_load -> arclink_fleet.py placement (CANON-08, OUT).** Producer
   writes `asu_capacity`/`asu_consumed` REAL columns
   (`arclink_inventory.py:479-486`); consumer reads them off the linked inventory row to
   compute `asu_available` and gate `standard_unit` placement
   (`arclink_fleet.py:316`,325,334,337). Contract = the two REAL columns + the
   `machine_host_link` FK join. BOTH-ENDS-VERIFIED: yes.

4. **register_inventory_machine -> register_fleet_host (CANON-08, OUT).** When
   `machine_host_link==""` and `capacity_slots` given, this piece calls
   `register_fleet_host(conn, hostname, region, capacity_slots=max(1,int(...)), tags,
   metadata)` and stores the returned `host_id` in `machine_host_link`
   (`arclink_inventory.py:173-182`). Consumer signature confirmed (CANON-08 doc §2; call
   site keys match). BOTH-ENDS-VERIFIED: yes (call site verified; full
   `register_fleet_host` body owned by CANON-08).

5. **create/remove_cloud -> idempotency helpers (CANON-01, OUT/IN).** This piece passes
   `operation_kind`, `idempotency_key`, `intent` dict; consumers
   `reserve/replay/complete/fail_arclink_operation_idempotency`
   (`arclink_control.py:3299`,3333,3352,3397) return dicts carrying `replay`/`reserved`.
   This piece reads `reserved.get("replay")` (`arclink_inventory.py:766`,883) and
   `replay is not None` (`:752`). BOTH-ENDS-VERIFIED: yes — `reserve` sets
   `result["replay"]` (`arclink_control.py:3329`); `replay` returns `None` for
   non-terminal (`:3346`).

6. **fleet_enrollment.consume_fleet_enrollment -> register_inventory_machine (CANON-08,
   IN).** Producer calls `register_inventory_machine(provider, hostname, ssh_host,
   ssh_user, region, status="pending", hardware_summary, connectivity_summary,
   capacity_slots, tags, metadata)` (`arclink_fleet_enrollment.py:651-668`). Keyword set
   is a subset of this piece's signature (`arclink_inventory.py:142-161`).
   BOTH-ENDS-VERIFIED: yes.

7. **fleet_inventory_worker -> compute_asu/current_load (CANON-20, IN).** Consumer
   `arclink_fleet_inventory_worker.py:367-368` calls `compute_asu(hardware)` (or falls
   back to `capacity_slots` when `hardware` empty) and `current_load(machine_id, conn)`,
   then writes the SAME `asu_capacity`/`asu_consumed` columns
   (`arclink_fleet_inventory_worker.py:371-377`). BOTH-ENDS-VERIFIED: yes.

8. **resource_map builders -> onboarding/control (CANON-04/CANON-01, OUT).** Producers
   `shared_tailnet_host`/`shared_resource_lines`/`managed_resource_ref`; consumers
   `arclink_onboarding_completion.py:204-229`, `arclink_onboarding_flow.py:913-924`,
   `arclink_control.py:17549`,17700-17719. Keyword args verified to match each signature.
   BOTH-ENDS-VERIFIED: yes (signatures match; producers are pure string builders).

9. **dashboard scale-ops -> list_inventory_machines (CANON-19, OUT).** Consumer reads
   `machine_id, provider, hostname, ssh_host, ssh_user, region, status, asu_capacity,
   asu_consumed, last_probed_at, machine_host_link` off each returned dict
   (`arclink_dashboard.py:604-617`). Producer returns full row dicts with
   `asu_consumed` overwritten by `current_load` (`arclink_inventory.py:317-322`).
   BOTH-ENDS-VERIFIED: yes.

## CODE vs COMMENT/DOC/NAME DRIFT

1. **File name `arclink_resource_map.py` is misleading.** The name implies cloud
   resource/inventory mapping; the body builds human/agent *access-URL rail lines*
   (`arclink_resource_map.py:23-61`). It has zero coupling to inventory machines or ASU.
   Code wins: it is an onboarding/access helper grouped here only by the prompt.

2. **Prior doc claim "auto-registers a fleet host" — TRUE but capacity unit nuance.**
   `research/ground-truth/02-provisioning-fleet-ingress.md:169` says register
   auto-registers a fleet host when `machine_host_link` empty + capacity_slots. Confirmed
   (`arclink_inventory.py:173-182`). Drift to flag: `capacity_slots` is a raw slot count,
   NOT ASU; ASU is computed only later by `compute_asu`. The two capacity notions
   coexist and `arclink_fleet.py` prefers the ASU-derived columns when an inventory row is
   linked (`arclink_fleet.py:324-337`).

3. **Prior doc "set-strategy CLI is informational only" — CONFIRMED.**
   `02-provisioning-fleet-ingress.md:393-396`. `set-strategy` only prints
   `ARCLINK_FLEET_PLACEMENT_STRATEGY=<v>` / JSON and never writes the DB
   (`arclink_inventory.py:1287-1291`); the strategy is read live from env at placement
   time (`arclink_fleet.py:720`) and at health (`arclink_inventory.py:969`). No drift —
   prior doc correct.

4. **Docstring "defaults are intentionally conservative: 1 vCPU, 4 GiB RAM, 30 GiB disk"
   matches code.** `arclink_asu.py:45-46` docstring vs `:49-51` defaults — consistent.
   No drift.

5. **Hetzner adapter comment "Fail-closed" is partially aspirational for units.** The
   adapter IS fail-closed on auth/HTTP errors (`*_hetzner.py:50-52`), but `_server`
   copies `server_type.memory`/`disk` straight into `ram_gib`/`disk_gib` with NO unit
   normalization (`*_hetzner.py:115-117`), unlike Linode which divides MB by 1024
   (`*_linode.py:104-105`). If the Hetzner API returns memory in GB (it does) this is
   fine; if a caller assumed MB parity with Linode it is wrong. Asymmetry is real and
   undocumented (see ADVERSARIAL #1).

6. **Prior doc §3 lists provider allowlist `{local, manual, hetzner, linode}` — CONFIRMED**
   (`arclink_inventory.py:55`). Schema CHECK matches (`arclink_control.py:1415`). No drift.

## ADVERSARIAL SELF-CHECK (least-sure claims)

1. **Hetzner memory units.** I claim Hetzner `server_type.memory` is already GiB so
   copying it raw into `ram_gib` is correct, while Linode `specs.memory` is MB and is
   divided by 1024. I verified the CODE asymmetry (`*_hetzner.py:115` vs `*_linode.py:104`)
   but did NOT hit the live Hetzner API. Falsifier: a real Hetzner `/server_types`
   response where `memory` is in MB would make `compute_asu` over-count by ~1024x. The
   tests (`test_arclink_inventory_hetzner.py`) use fixtures, not the live API.

2. **`current_load` semantics when `machine_host_link` empty.** I claim it returns the
   stored `asu_consumed` column verbatim (`arclink_asu.py:72-74`). For cloud-created
   machines the auto-fleet-host IS linked, so the COUNT path runs; but a manually
   registered machine with no host link and no placements returns whatever `asu_consumed`
   was last written (could be stale). Falsifier: a machine whose `asu_consumed` column was
   set high but has no link would report stale load.

3. **`disk_gib` parsing brittleness.** I claim `parse_probe_output` picks the max
   integer-G field from `df -BG` lines (`arclink_inventory.py:411-416`). I did not test
   every `df` output variant (e.g. mountpoints with spaces, `Use%` columns). Falsifier: a
   `df -BG` line whose 2nd field is not the size (locale/format differences) would yield a
   wrong disk figure, hence wrong ASU.

4. **Idempotency replay returns the FULL prior result.** `_idempotent_replay_result`
   loads `result_json` and sets `replay=True` (`arclink_inventory.py:567-570`,551-556).
   I assume `complete_arclink_operation_idempotency` stored the full
   `{status,replay,machine}` dict (`:828`). Verified the write at
   `arclink_control.py:3385`. Falsifier: if `_arclink_json` truncates large machine rows,
   a replay could return a partial machine.

5. **resource_map is genuinely side-effect-free.** I claim the three builders are pure.
   They construct `Path(workspace_root)/'ArcLink'` (`arclink_resource_map.py:84`) but
   never touch the filesystem. Falsifier: none found, but `Path` construction is the only
   non-string operation — confirmed no I/O.

## OPEN FOR CODEX FEDERATION
1. Confirm Hetzner Cloud `/server_types.memory` and `.disk` units against the live API
   contract — the raw copy into `ram_gib`/`disk_gib` (`arclink_inventory_hetzner.py:115-117`)
   has no normalization and diverges from Linode's MB->GiB conversion. This is the single
   highest-risk capacity-correctness claim.
2. Cross-check that `arclink_fleet.py` is the ONLY consumer that turns
   `asu_capacity`/`asu_consumed` into a placement decision, and that no path reads
   `asu_capacity` written by the cloud-create flow (which leaves it 0 until a probe).
3. Verify the `current_load` empty-`machine_host_link` branch can return stale
   `asu_consumed` and whether any production path relies on it for placement.
4. Confirm `StrictHostKeyChecking=accept-new` (TOFU) in `probe_inventory_machine`
   (`arclink_inventory.py:440`) is the intended fleet SSH posture vs a pinned known-hosts
   requirement.

## RISKS (severity-ranked, code-cited)

- **MEDIUM — Hetzner memory/disk unit asymmetry.** `arclink_inventory_hetzner.py:115-117`
  copies `server_type.{cores,memory,disk}` raw; `arclink_inventory_linode.py:104-105`
  divides MB by 1024. If Hetzner ever returns MB (or a caller assumes Linode parity),
  `compute_asu` mis-sizes the box. No normalization test exists.
- **MEDIUM — SSH TOFU in probe.** `arclink_inventory.py:440`
  `StrictHostKeyChecking=accept-new` trusts the first key seen for any inventory host;
  a MITM at first probe could intercept the `nproc/meminfo/df/docker` shell. Mitigated
  only if `ARCLINK_FLEET_SSH_KNOWN_HOSTS_FILE` is pre-seeded (optional,
  `arclink_inventory.py:441-442`).
- **LOW — Fragile `df -BG` disk parse.** `arclink_inventory.py:411-416` only matches
  integer-G fields and silently ignores parse errors (`except ValueError: pass`,
  `:415-416`), so a malformed line yields `disk_gib=0` -> ASU collapses to 0 (fail-closed,
  but a real box reports zero capacity).
- **LOW — `compute_asu` RAM=0/disk=0 returns 0 without erroring.** `arclink_asu.py:59-61`:
  only negatives raise; a probe that drops MemTotal (`ram_gib=0`) silently yields 0 ASU
  rather than flagging bad data.
- **LOW — Stale `asu_consumed` for unlinked machines.** `arclink_asu.py:72-74` returns the
  stored column when `machine_host_link` is empty; never reconciled against placements
  for such rows.
- **INFO — `_request` GET cache is per-instance and unbounded.** `*_hetzner.py:33`,37,55
  caches every GET keyed by method:path:payload for the provider object's lifetime; a
  `list_servers` after a `provision_server` could read a stale `/servers` GET if the same
  object were reused (CLI builds a fresh client per invocation, so low impact).
- **INFO — `set-strategy` is a no-op for DB state** (`arclink_inventory.py:1287-1291`);
  operators may believe it persists. Documented behavior in prior doc but a UX trap.

## VERDICT
This piece provably does its core job: it normalizes heterogeneous provider hardware
into a single `{vcpu_cores, ram_gib, disk_gib}` summary and computes a conservative,
scarcest-resource ASU (`arclink_asu.py:61`) that the placement engine consumes via two
REAL columns over a verified FK join (`arclink_fleet.py:316-337`). The registry CRUD is
input-validated (host/user/label regexes, status/provider allowlists matching the
schema CHECK constraints), and the cloud lifecycle is durably idempotent with
fail-closed error handling and secret redaction at every provider boundary. All nine
cross-piece seams were verified at both ends. **Load-bearing strengths:** scarcest-
resource ASU math; sole-writer discipline over capacity columns; fail-closed probe
(degrades on any SSH error); double-redaction of provider tokens; injectable
`client`/`runner`/`http_request_fn` making the live paths testable without secrets.
**Real weaknesses:** (1) the Hetzner-vs-Linode unit asymmetry is an un-normalized,
untested capacity-correctness hazard; (2) SSH TOFU is the default probe posture; (3) the
`df -BG` parser and RAM=0 case fail toward zero capacity silently rather than surfacing
bad-probe-data. The `arclink_resource_map.py` member is correctly claimed but is an
access-rail string builder mis-grouped under "inventory" by name only.
