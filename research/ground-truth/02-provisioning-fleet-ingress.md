# Ground Truth: Provisioning, Fleet, Inventory, Workers, Ingress, Pod Migration

Subsystem map as of 2026-05-30 (branch `arclink`). Source of truth is the code
in `python/`, not the docs. Citations are file paths under `/root/arclink`.

---

## 0. Two distinct provisioning paths (do not conflate)

There are **two separate provisioning loops** in this repo and the docs blur them:

1. **`python/arclink_enrollment_provisioner.py`** — the *headless single-machine
   onboarding* loop. Runs the bot/onboarding flow, creates a **Unix user**,
   installs **systemd user units** (`arclink-user-agent-gateway.service`,
   `arclink-user-agent-dashboard.service`, `arclink-user-agent-dashboard-proxy.service`,
   `arclink-user-agent-refresh.service`) via `bin/install-agent-user-services.sh`,
   seeds the provider secret, runs `bin/install-agent-ssh-key.sh`,
   `bin/configure-agent-backup.sh`, and consumes the **operator-action / pin-upgrade /
   broker** rails. This is the *legacy / starter / localhost* per-agent runtime.
   In `_docker_mode()` it delegates host mutation to a `docker-supervisor` service
   manager and to brokers (`operator-upgrade-broker:8917`). It is NOT the fleet
   ArcPod path.

2. **`python/arclink_sovereign_worker.py`** — the *Sovereign fleet ArcPod* loop
   (`control-provisioner`). Claims paid `provisioning_ready` deployments, places
   them on a fleet host, renders the per-ArcPod compose intent, applies via the
   injectable executor (local or SSH Docker Compose), and runs the teardown
   lifecycle. **This is "how ArcPods get placed/applied/torn-down today."**

The special focus questions below are answered against path (2) unless noted.

---

## 1. How an ArcPod gets placed / applied / rolled-back / torn-down today

Owner: `python/arclink_sovereign_worker.py`. Entry point `process_sovereign_batch()`
(CLI: `python python/arclink_sovereign_worker.py --once [--json]`).

### Batch loop (`process_sovereign_batch`)
1. If `ARCLINK_REGISTER_LOCAL_FLEET_HOST=1`, calls `register_fleet_host(...)` for
   the local machine (the "starter local host"); metadata carries
   `executor`, `ingress_mode`, `edge_target`, `state_root_base`, `ssh_host`, `ssh_user`.
2. `reconcile_fleet_observed_loads(conn)` — repairs host `observed_load` from
   active placement rows.
3. `recover_stale_sovereign_jobs(...)` — fails `running` apply jobs older than
   `ARCLINK_SOVEREIGN_RUNNING_STALE_SECONDS` (default 900) and re-marks the
   deployment `provisioning_failed`.
4. `recover_succeeded_sovereign_handoffs(...)` — for deployments whose apply job
   already `succeeded` but which never emitted `user_handoff_ready`, marks active
   and emits the handoff event + vessel-online notifications (idempotent backfill).
5. Selects **teardown** rows (deployments in `teardown_requested`, resource-bearing
   `cancelled`, or retryable `teardown_failed`) then **apply** rows
   (`provisioning_ready`, or `provisioning_failed` with a retryable failed job and
   `attempt_count < max_attempts`). Apply explicitly **excludes** deployments whose
   metadata contains `"operator_agent"` (the Operator's own arcpod is provisioned
   elsewhere). Batch size `ARCLINK_CONTROL_PROVISIONER_BATCH_SIZE` (default 5).

### Apply (`process_sovereign_deployment` -> `_apply_deployment`)
Job kind `sovereign_pod_apply`, idempotency key `arclink:sovereign:apply:<deployment_id>`.
Deployment moves `provisioning_ready -> provisioning -> active`. Steps, each
re-validating the deployment via `_reload_apply_ready_deployment` (which asserts
status is still `provisioning`, user still exists, and
`arclink_deployment_can_provision` still permits it — a guard against the
entitlement being revoked mid-apply):
1. `_ensure_tailnet_service_ports` (tailscale path mode only) — allocates a per-deployment
   `hermes` tailnet port from base `ARCLINK_TAILNET_SERVICE_PORT_BASE` (default 8443),
   avoiding ports used by other live deployments.
2. `place_deployment(...)` (from `arclink_fleet.py`) — one active placement per
   deployment.
3. `render_arclink_provisioning_intent(...)` (from `arclink_provisioning.py`).
4. `_persist_deployment_runtime_metadata` — caches `access_urls`, `state_roots`,
   `state_root_base` into deployment metadata.
5. `_ensure_share_request_broker_token_hash` — materializes the share-request broker
   token secret and stores its hash (`set_deployment_share_request_broker_token_hash`).
6. `_persist_dns_from_intent` -> `persist_arclink_dns_records` (status `desired`).
7. `_ensure_llm_router_key_registered` — generates/loads the per-deployment LLM
   router key (router-first mode) and registers it via `ensure_llm_router_key`.
8. DNS apply: **domain mode only** — `selected_executor.cloudflare_dns_apply(...)`
   then `_mark_dns_provisioned`. Tailscale mode records a `skipped`
   `CloudflareDnsApplyResult` (reason `cloudflare_dns_not_used_for_tailscale_ingress`).
9. `selected_executor.docker_compose_apply(...)` — applies the rendered compose.
10. `_sync_dashboard_password_hash_from_secret` — sets the user dashboard password
    from the generated secret unless it pre-existed (or is provided via env).
11. `_record_service_status_after_compose` — for the **fake** adapter marks all
    services `healthy`; for live adapters runs `docker compose ps --all --format json`
    and maps state/health to `healthy|unhealthy|starting|failed|missing`
    (`_docker_compose_row_status`; `managed-context-install` with exit 0 is treated
    `healthy`).
12. If `ARCLINK_SOVEREIGN_HANDOFF_REQUIRES_HEALTHY_SERVICES` (default `1`) and any
    service is `failed|unhealthy|missing`, raises and the apply fails (no handoff).
13. On success: job `succeeded`, deployment `active`, emits `sovereign_pod_applied`
    + `user_handoff_ready`, audit `sovereign_pod_apply`, and queues vessel-online
    notifications to the user's Telegram/Discord onboarding sessions.

### "Rollback" of provisioning (planning only)
`plan_arclink_provisioning_rollback(...)` in `arclink_provisioning.py` only writes
a **plan** job (`docker_rollback_plan`) with a fixed action tuple
(`stop_rendered_services`, `remove_unhealthy_containers`, `preserve_state_roots`,
`leave_secret_refs_for_manual_review`) and a `rollback_requested` timeline event.
**It performs no host mutation.** Real rollback-with-restore only exists in the
pod-migration path (see §6).

### Teardown (`process_sovereign_teardown` -> `_teardown_deployment`)
Job kind `sovereign_pod_teardown`, key `arclink:sovereign:teardown:<deployment_id>`.
Deployment moves to `teardown_running -> torn_down`. Steps:
- `docker_compose_lifecycle(action="teardown", remove_volumes=...)` — volumes
  preserved unless `metadata.teardown.remove_volumes is True`.
- DNS teardown **domain mode only** via `cloudflare_dns_teardown` + `mark_arclink_dns_torn_down`;
  tailscale just marks DNS torn-down with `skipped`.
- Chutes key revoke (`chutes_key_apply action="revoke"`) only if the executor can
  revoke (fake adapter, or a real `chutes_client` is injected); otherwise
  `skipped_no_chutes_client`. The constant `MISSING_CHUTES_CLIENT_ERROR` makes such
  failures retryable after an upgrade.
- `_cleanup_deployment_secret_store` — removes `<secret_store_dir>/<deployment_id>`
  with path-escape guards.
- `remove_placement`, `reconcile_fleet_observed_loads`, `_release_tailnet_service_ports`.

---

## 2. Fleet host registry + placement (`python/arclink_fleet.py`)

- `register_fleet_host` — upserts `arclink_fleet_hosts` (status default `active`,
  `drain=0`, `capacity_slots` default 10, `observed_load=0`). Rejects secret material
  in tags/metadata.
- `update_fleet_host` — status in `{active, degraded, offline}` (`FLEET_HOST_STATUSES`),
  drain, observed_load, capacity_slots.
- `list_fleet_hosts` — joins the **linked inventory machine** to surface
  `asu_capacity` / `asu_consumed` / `asu_available`; active-placement count overrides
  consumed.
- `place_deployment` — idempotent per deployment (returns existing active placement).
  Uses `BEGIN IMMEDIATE` when it owns the transaction. Strategy from
  `ARCLINK_FLEET_PLACEMENT_STRATEGY` env: `headroom` (default; most free
  `capacity_slots - observed_load`) or `standard_unit` (most `asu_available`). Filters
  out non-`active`, draining, saturated, region-mismatch, tag-mismatch hosts.
  `_placement_rejection_summary` yields the human reason
  (`unhealthy|draining|saturated|asu_saturated|region_mismatch|tag_mismatch|no active hosts registered`).
- `remove_placement`, `get_deployment_placement`.
- `reconcile_fleet_inventory_orphans` — audit-only orphan report between
  `arclink_inventory_machines` and `arclink_fleet_hosts` (never mutates either registry).
- Placement statuses `{active, removed}` (`PLACEMENT_STATUSES`).

---

## 3. Inventory + worker admission (`python/arclink_inventory.py`, `arclink_fleet_enrollment.py`)

### Worker admission: single-machine localhost vs remote fleet
- **Single-machine / starter (localhost):** the control machine registers itself as
  a fleet host when `ARCLINK_REGISTER_LOCAL_FLEET_HOST=1`
  (`arclink_sovereign_worker.load_worker_config` -> `register_local_host`). The
  fleet inventory worker has a special **`docker-local-starter` probe mode**: in
  `arclink_fleet_inventory_worker._host_rows`, a host is flagged
  `_arclink_docker_local_starter_probe` when `ARCLINK_DOCKER_MODE` is truthy AND the
  linked machine metadata `executor == "local"` AND `ssh_host` is in
  `LOCAL_SSH_HOST_ALIASES = {localhost, 127.0.0.1, ::1}`. That probe
  (`_docker_local_starter_probe`) admits the host **without SSH** (always `ok=True`,
  `admitting=True`, `probe_mode="docker-local-starter"`). This is the local-real
  admission path.
- **Remote fleet:** admission is enrollment-token based. Operator mints a token
  (`mint_fleet_enrollment`), the worker runs `bin/arclink-fleet-join.sh` (constant
  `FLEET_JOIN_SCRIPT = "bin/arclink-fleet-join.sh"`,
  `FLEET_PREREQ_LIBRARY = "bin/lib/ensure-prereqs.sh"`), and the control callback
  calls `consume_fleet_enrollment(...)` which registers/links the inventory machine,
  verifies fingerprint, and writes the **hash-chained audit trail**.

### `arclink_inventory.py`
- `register_inventory_machine` — upserts `arclink_inventory_machines`. Providers:
  `{local, manual, hetzner, linode}` (`_clean_provider`). Statuses:
  `{pending, ready, draining, degraded, removed}` (`_clean_status`). When
  `machine_host_link` is empty and `capacity_slots` given, auto-registers a fleet host.
- `probe_inventory_machine` — SSH probe (`nproc; meminfo; df; docker --version;
  docker compose version`), parses via `parse_probe_output`, computes ASU via
  `arclink_asu.compute_asu`, sets machine `ready`, updates linked fleet host
  `status=active, observed_load=consumed`. On failure marks machine `degraded`.
- `drain_inventory_machine` (sets host `drain=True`, machine `draining`),
  `remove_inventory_machine` (refuses if active placements exist; sets host
  `offline`+drain, machine `removed`).
- Cloud lifecycle: `create_cloud_inventory_machine` / `remove_cloud_inventory_machine`
  — `{hetzner, linode}` only (`CLOUD_INVENTORY_PROVIDERS`), durable idempotency via
  `reserve/complete/fail_arclink_operation_idempotency`, injectable `client` and
  `bootstrap_runner`. Provider clients lazy-loaded: `arclink_inventory_hetzner.HetznerInventoryProvider`,
  `arclink_inventory_linode.LinodeInventoryProvider`, tokens from `HETZNER_API_TOKEN`/`LINODE_API_TOKEN`.
- `fleet_inventory_health` — expires stale enrollments, verifies audit chain,
  aggregates inventory/host/region/health/probe/capacity counts and the active
  placement strategy.
- CLI `arclink-inventory`: `list`, `probe`, `probe-all`, `add {manual,hetzner,linode}`,
  `drain`, `remove [--destroy --force]`, `re-attest`, `health`, `set-strategy {headroom,standard_unit}`.

### `arclink_fleet_enrollment.py`
- Token format `arcfleet_v1.<enrollment_id>.<nonce>.<sig>` HMAC-SHA256 over
  `ARCLINK_FLEET_ENROLLMENT_SECRET`. `mint`/`list`/`revoke`/`rotate-secret`/`verify-audit-chain`
  CLI. Enrollment statuses `pending|consumed|expired|revoked`.
- `consume_fleet_enrollment` — registers the machine (`status="ready"`,
  provider in `{local, manual, hetzner, linode}`), records fingerprint, writes two
  audit-chain entries (`enrolled`, `verified`), marks token `consumed`. Fingerprint
  mismatch on an existing host requires explicit `reattest_inventory_machine`.
- `append_fleet_audit_chain_entry` — sha256 prev-hash chain over
  `arclink_fleet_audit_chain`; events `{enrolled, verified, activated, degraded,
  drained, resumed, removed, re-attested}`. `verify_fleet_audit_chain` recomputes and
  queues a **P0** operator notification on tamper.

---

## 4. Periodic probe worker (`python/arclink_fleet_inventory_worker.py`)

- CLI `arclink-fleet-inventory-worker --once [--force] [--notify] [--json]`.
- Probe kinds `("liveness", "capacity", "inventory")`, default cadences
  `{liveness:60, capacity:300, inventory:900}` seconds.
- `SshProbeRunner` runs `ssh ... -- arclink-fleet-probe-wrapper <kind>` (worker-local
  allowlisted wrapper) using `ARCLINK_FLEET_SSH_KEY_PATH` /
  `ARCLINK_FLEET_SSH_KNOWN_HOSTS_FILE`, timeout `ARCLINK_FLEET_PROBE_TIMEOUT_SECONDS`
  (default 20). The `docker-local-starter` host short-circuits to the no-SSH probe.
- Liveness state machine: >=3 consecutive failures -> `degraded`; >=10 -> `offline`/
  `unreachable`; recovery -> `active`. Transitions queue operator notifications
  (`P1` unreachable, `P2` degraded). Writes `arclink_fleet_host_probes`
  (retention default 1000/host/kind, env `ARCLINK_FLEET_PROBE_RETENTION`).
- Capacity/inventory probes update host `capacity_slots`/`observed_load` and linked
  machine `asu_capacity`/`asu_consumed`/`hardware_summary`. All probe payloads pass
  through `_redact_json_value` (redacts token/secret/password/api_key-ish keys).

---

## 5. Ingress: domain/Cloudflare/Traefik vs Tailscale (`python/arclink_ingress.py`, `arclink_provisioning.py`)

- Two modes only, validated by `_clean_ingress_mode`: `domain` | `tailscale`.
  Tailscale strategy is **fixed to `path`**; `subdomain` is explicitly rejected
  (`_clean_tailscale_strategy`) because Tailscale MagicDNS/Funnel can't do dynamic
  per-Captain subdomains.
- **Domain mode:** `desired_arclink_ingress_records` returns Cloudflare **CNAME,
  proxied** records, but only for `ARCLINK_HOST_ROLES = ("dashboard", "hermes")` —
  i.e. only `u-<prefix>` and `hermes-<prefix>` get DNS/Traefik routers.
  `arclink_hostnames` still computes `files-<prefix>` and `code-<prefix>` hostnames,
  but Files/Code are **dashboard plugin routes**, not standalone subdomains, and get
  no DNS record or Traefik router. Traefik labels via `render_traefik_dynamic_labels`
  -> `render_traefik_http_labels` (host-rule). Default ports
  `{dashboard:3000, files:80, code:8080, hermes:3210}`.
- **Tailscale path mode:** `desired_arclink_ingress_records` returns `{}` (no DNS).
  Traefik labels become host + `PathPrefix(/u/<prefix>/...)` with a StripPrefix
  middleware (`render_traefik_http_path_labels`). Hermes root + alias routers
  (`<prefix>-hermes-root` priority 10, `<prefix>-hermes` priority 100). The hermes
  service also gets a host-port `127.0.0.1:<tailnet_port>:3210`.
- DNS persistence/teardown all in `arclink_ingress.py`: `persist_arclink_dns_records`
  (upsert with `desired`/preserve-`provisioned` logic), `provision_arclink_dns`
  (live cloudflare upsert with retry), `reconcile_arclink_dns` (drift -> `dns_drift`
  events), `teardown_arclink_dns`, `mark_arclink_dns_torn_down`,
  `arclink_dns_records_for_teardown`. DnsDrift kinds `missing|changed`.
- SSH access strategy chosen in the intent (`arclink_provisioning`): tailscale ->
  `tailscale_direct_ssh` (`arc-<prefix>@<tailscale_dns_name>`); domain ->
  `cloudflare_access_tcp` (`ssh-<prefix>.<base_domain>`). Notion callback path differs
  per mode (`/notion/webhook` vs `/u/<prefix>/notion/webhook`).

---

## 6. Pod migration (`python/arclink_pod_migration.py`) — newer than most docs

Operation kind `pod_migration`, idempotency key `arclink:migration:<migration_id>`.
This is the only path that does real **capture + materialize + verify + rollback**.

- `plan_pod_migration` — resolves source active placement + target host (via
  `target_machine_id`: `""`/`current` = redeploy in place; else inventory machine id
  or fleet host id). Refuses non-`active`/draining targets. Pre-creates a `removed`
  target placement row for cross-host moves. Writes `arclink_pod_migrations` row.
- `migrate_pod` — for non-dry-run, requires **two opt-ins** before any capture:
  - `ARCLINK_ACTION_WORKER_ALLOW_ROOT_MIGRATION_CAPTURE=1` (`_require_root_capture_opt_in`)
  - in `ARCLINK_DOCKER_MODE`, a configured capture helper
    (`ARCLINK_MIGRATION_CAPTURE_HELPER_URL` + `..._TOKEN`, header
    `X-ArcLink-Migration-Capture-Helper-Token`, endpoint `/v1/migration-capture`).
  Dry-run path requires neither and just runs `docker_compose_dry_run` against the
  target intent and emits `pod_migration_dry_run_planned`.
  Live path: `stop` source compose -> capture (`_copy_capture` with per-file
  sha256 manifest + boundary tagging via `_boundary_for`, OR the helper) ->
  ensure target LLM router key -> materialize on target root -> `docker_compose_apply`
  target -> verify (`_default_verifier` checks `arclink_service_health` for
  failed/unhealthy/missing) -> on healthy `_mark_success` (flips placements, moves
  observed_load, writes `metadata.pod_migration`, retains capture until
  `ARCLINK_MIGRATION_GC_DAYS` default 7) -> on failure `_rollback_lifecycle`
  (teardown target, restart source) + `_mark_rollback` (reactivates source placement).
- `garbage_collect_pod_migrations` — removes expired successful capture dirs under
  `<state_root_base>/.migrations/<migration_id>/`.
- Strict capture-path validation (`_validate_capture_paths`): source/target roots
  must be deployment-scoped (`render_arclink_state_roots` name match) and the capture
  dir must live under `<target_base>/.migrations/` and never inside source/target roots.
- Captain-initiated migration is policy-disabled by default
  (`ARCLINK_CAPTAIN_MIGRATION_ENABLED=0`, per runbook); operators queue via the admin
  `reprovision` action -> `arclink_pod_migration.py`.

---

## 7. Host readiness (`python/arclink_host_readiness.py`) + GAP-030 surfacing

- `arclink_host_readiness.py` is the **no-mutation host preflight**: `check_docker`,
  `check_docker_compose` (actually runs `docker compose version`), `check_port_available`
  (default ports `80,443,8080`), `check_state_root` (writable, default `/arcdata`),
  `check_env_vars` (`ARCLINK_PRODUCT_NAME`, `ARCLINK_BASE_DOMAIN`,
  `ARCLINK_PRIMARY_PROVIDER`), `check_secret_env_presence` (presence-only, never values),
  `check_ingress_strategy` (cloudflare if token+zone else `traefik_local`). CLI
  `arclink-host-readiness`. Secret-presence checks are excluded from the `ready` roll-up.
- **GAP-030 readiness surfacing is NOT in this module.** The provisioning-readiness
  state model lives in `python/arclink_dashboard.py::control_node_provisioning_readiness`
  (added 2026-05-27, "GAP-030-A"). States:
  `control_plane_only`, `pending_ssh`, `ready_to_provision`, `blocked_no_worker`,
  `blocked_executor`. It is surfaced through the admin dashboard snapshot, scale-
  operations snapshot (`arclink_dashboard.py` line ~2290), Operator Raven `status`
  (`python/arclink_operator_raven.py`), and the admin web page
  (`web/src/app/admin/page.tsx` provisioning readiness panel).
- **GAP-030 true status: open as a live-proof gate only.** The local/admin-surface
  half is implemented and tested; what remains is authorized `PG-FLEET`/`PG-PROVISION`
  evidence for the chosen worker path (per `research/BUILD_COMPLETION_NOTES.md`
  2026-05-27 and `sovereign-control-node-symphony.md` lines 136-144).

---

## 8. Proof-gated / fake-adapter / local-only behavior

- **Executor adapter** defaults to `disabled` in `load_worker_config`
  (`ARCLINK_EXECUTOR_ADAPTER`). `fake` proves contract only (`docker_compose_apply`
  marks all services healthy; Chutes revoke always "works"). `local`/`ssh` are the
  real adapters (in `arclink_executor.py`, out of scope here but referenced).
- **DNS**: live Cloudflare only in domain mode with `CLOUDFLARE_ZONE_ID`/token;
  tailscale always skips. Fake/dry-run persists to SQLite only — no provider call.
- **Cloud inventory** (hetzner/linode) needs `HETZNER_API_TOKEN`/`LINODE_API_TOKEN`;
  no-secret tests use fake clients (parity only — not real APIs/SSH/join/destroy).
- **Migration live capture** is double-gated (`ARCLINK_ACTION_WORKER_ALLOW_ROOT_MIGRATION_CAPTURE`
  + docker-mode capture helper). Dry-run is local-safe.
- **docker-local-starter probe** is the only local-real worker admission with no SSH.
- **Handoff health gate** (`ARCLINK_SOVEREIGN_HANDOFF_REQUIRES_HEALTHY_SERVICES`, default 1)
  is bypassed by the fake adapter (always healthy).
- **Direct Chutes** only behind `ARCLINK_ALLOW_DIRECT_CHUTES_IN_ARCPODS=1`; default is
  router-first (`control-llm-router:8090`).

---

## 9. Canonical vocabulary (real names from code)

**Modules/CLIs:** `arclink_provisioning.py`, `arclink_sovereign_worker.py`
(`control-provisioner`), `arclink_enrollment_provisioner.py`, `arclink_fleet.py`,
`arclink_fleet_enrollment.py` (CLI `arclink-fleet-enrollment`),
`arclink_fleet_inventory_worker.py` (CLI `arclink-fleet-inventory-worker`),
`arclink_inventory.py` (CLI `arclink-inventory`), `arclink_ingress.py`,
`arclink_pod_migration.py`, `arclink_host_readiness.py` (CLI `arclink-host-readiness`).

**Tables:** `arclink_fleet_hosts`, `arclink_inventory_machines`,
`arclink_deployment_placements`, `arclink_fleet_enrollments`,
`arclink_fleet_audit_chain`, `arclink_fleet_host_probes`, `arclink_pod_migrations`,
`arclink_provisioning_jobs`, `arclink_dns_records`, `arclink_service_health`,
`arclink_deployments`.

**Job kinds:** `sovereign_pod_apply`, `sovereign_pod_teardown`, `docker_dry_run`,
`docker_rollback_plan`, `pod_migration`.

**Deployment statuses observed:** `provisioning_ready`, `provisioning`,
`provisioning_failed`, `active`, `teardown_requested`, `teardown_running`,
`teardown_failed`, `torn_down`, `teardown_complete`, `cancelled`.

**Provisioning service names (`ARCLINK_PROVISIONING_SERVICE_NAMES`):** dashboard,
hermes-gateway, hermes-dashboard, qmd-mcp, vault-watch, memory-synth, nextcloud-db,
nextcloud-redis, nextcloud, notion-webhook, notification-delivery, arclink-wrapped,
health-watch, fleet-share-sync, managed-context-install.

**Bin scripts:** `bin/arclink-fleet-join.sh`, `bin/lib/ensure-prereqs.sh`,
`bin/arclink-fleet-probe-wrapper` (worker-local), `bin/install-agent-user-services.sh`.

**Key env vars:** `ARCLINK_INGRESS_MODE`, `ARCLINK_TAILSCALE_DNS_NAME`,
`ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY` (path-only),
`ARCLINK_TAILNET_SERVICE_PORT_BASE` (8443), `ARCLINK_FLEET_PLACEMENT_STRATEGY`
(headroom|standard_unit), `ARCLINK_EXECUTOR_ADAPTER` (disabled|fake|local|ssh),
`ARCLINK_REGISTER_LOCAL_FLEET_HOST`, `ARCLINK_CONTROL_PROVISIONER_ENABLED`,
`ARCLINK_SOVEREIGN_RUNNING_STALE_SECONDS`, `ARCLINK_SOVEREIGN_PROVISION_MAX_ATTEMPTS`,
`ARCLINK_SOVEREIGN_HANDOFF_REQUIRES_HEALTHY_SERVICES`, `ARCLINK_FLEET_ENROLLMENT_SECRET`,
`ARCLINK_FLEET_SSH_KEY_PATH`, `ARCLINK_MIGRATION_GC_DAYS`,
`ARCLINK_ACTION_WORKER_ALLOW_ROOT_MIGRATION_CAPTURE`, `ARCLINK_MIGRATION_CAPTURE_HELPER_URL/_TOKEN`,
`ARCLINK_DOCKER_MODE`, `ARCLINK_ALLOW_DIRECT_CHUTES_IN_ARCPODS`,
`HETZNER_API_TOKEN`, `LINODE_API_TOKEN`.

---

## 10. Newer-than-docs / undocumented in code

1. **`fleet-share-sync` + `managed-context-install` services** are in
   `ARCLINK_PROVISIONING_SERVICE_NAMES` and the rendered compose
   (`arclink_provisioning.py`), incl. the `fleet-share-hub.git` bare-repo mount and
   `arclink_fleet_share.py sync-local` loop. The "fleet shared folder" design is in
   memory but not in these five docs.
2. **`docker-local-starter` no-SSH probe mode** (`arclink_fleet_inventory_worker.py`)
   — the actual mechanism by which single-machine localhost admits without SSH. Not
   named in fleet-cli.md or the runbook.
3. **`recover_succeeded_sovereign_handoffs`** idempotent handoff backfill — not in docs.
4. **Operator's own arcpod is excluded from the batch** (`"operator_agent"` metadata
   filter in `process_sovereign_batch`) — not in docs.
5. **Tailnet service-port allocator** (`_ensure_tailnet_service_ports`, base 8443) —
   the sovereign doc mentions `:8443` as an example but not the allocator/release logic.
6. **Mid-apply entitlement re-check** (`_reload_apply_ready_deployment` calls
   `arclink_deployment_can_provision` repeatedly) — a real guard not documented.
7. **`set-strategy` CLI is informational only** — `arclink_inventory.py` `set-strategy`
   prints the strategy but does NOT persist it; the strategy is read live from the
   `ARCLINK_FLEET_PLACEMENT_STRATEGY` env var each placement. Docs imply it changes
   behavior persistently.
8. **`reconcile_fleet_inventory_orphans`** audit-only orphan detector — undocumented.
9. **Migration capture boundary tagging** (`_boundary_for`: vault/memory/sessions/
   configs/hermes_home/secrets/state) — undocumented detail.
10. **`arclink_host_readiness.py` is not wired into GAP-030 readiness** — GAP-030
    surfacing is in `arclink_dashboard.py`, a different module than the readiness
    checker, which docs/coverage matrix list together under `J-17`.

---

## 11. Per-doc staleness verdicts

### `docs/arclink/fleet-cli.md` — LIGHT
Accurate for the operator CLI surface. Corrections:
- `set-strategy` is described as making placements prefer ASU; in code it only
  **prints** the value and is a no-op for persistence (strategy is env-driven at
  placement time). Clarify it sets the env var via deploy, not control DB state.
- Mentions `inventory rotate-key` / `fleet-key --rotate`; those live in `deploy.sh`,
  not in `arclink_inventory.py`/`arclink_fleet*.py` (the Python CLI has no rotate-key
  subcommand). Fine if scoped to deploy.sh but worth noting the boundary.

### `docs/arclink/fleet-operator-runbook.md` — FRESH (light)
Matches `consume_fleet_enrollment` / join-script admission, `--smoke-test` gating,
audit-chain health, drain-before-remove guard, cloud parity-test caveats. No code
contradictions found. Minor add: the **docker-local-starter** localhost admission
path (no SSH) is the single-machine equivalent and isn't mentioned here.

### `docs/arclink/ingress-plan.md` — FRESH (light)
Strongest doc. Domain table correctly lists only `u-{prefix}` and `hermes-{prefix}`
(matches `ARCLINK_HOST_ROLES`), tailscale path table matches `arclink_access_urls`,
Traefik/StripPrefix and SSH strategy all correct. Small note: it lists Files/Code as
dashboard plugin routes (correct), but elsewhere the codebase still computes
`files-`/`code-` hostnames (`arclink_hostnames`) that are unused for DNS — worth a
one-line note that those hostnames exist but aren't provisioned as subdomains.

### `docs/arclink/sovereign-control-node.md` — LIGHT-to-HEAVY (one concrete contradiction)
- **Contradiction:** §6 "Ingress" lists DNS records for **four** hosts
  `u-`, `files-`, `code-`, `hermes-`. Code only creates DNS/Traefik for
  `dashboard`(u-) and `hermes` (`desired_arclink_ingress_records` +
  `ARCLINK_HOST_ROLES`). Files/Code are not standalone subdomains. This directly
  contradicts ingress-plan.md and the code.
- Otherwise accurate on the worker loop, teardown lifecycle, router-first inference,
  idempotency, and credential gating. Add: handoff health gate, tailnet port
  allocator, operator-arcpod exclusion, mid-apply entitlement re-check.

### `docs/arclink/control-node-production-runbook.md` — FRESH (light)
Pod-migration section matches `arclink_pod_migration.py` precisely (capture dir,
GC days, idempotency key, rollback behavior, `reprovision` action,
`ARCLINK_CAPTAIN_MIGRATION_ENABLED=0`). Action support matrix and PG-* gates align.
Inventory/ASU section correct (note same `set-strategy` env-vs-persist nuance as
fleet-cli.md). No contradictions.

### `docs/arclink/sovereign-control-node-symphony.md` (dream shape) — aspirational, partially real
"Installation And Machine Admission" and "Fleet, Provisioning, Ingress, And Recovery"
honestly flag `GAP-030`/`PG-FLEET`/`PG-PROVISION`/`PG-INGRESS` as the remaining live
gates and that local source implements "much of this." Accurate framing. The dream's
"Placement rejects unhealthy/drained/insufficient-capacity" is fully real today
(`_filter_placement_candidates`). The dream's wildcard-subdomain domain ingress is NOT
implemented (only `u-`/`hermes-` get records; no wildcard cert/subdomain automation).

---

## 12. GAP status touched by this subsystem

- **GAP-030** (Control Node provisioning readiness): TRUE STATUS = local/admin
  surfacing implemented and tested (`control_node_provisioning_readiness` states +
  admin/Raven/web panels); **remains open only as a live proof gate**
  (`PG-FLEET`/`PG-PROVISION` for the chosen worker path).
- **PG-FLEET / PG-PROVISION / PG-INGRESS / PG-PROVIDER**: unchanged — fake/local-only
  here; live execution is operator-gated and unproven in-repo.
- **GAP-004 / GAP-017 / GAP-021** (fleet/ASU/placement, per COVERAGE_MATRIX J-10):
  source-complete locally; live remote-fleet behavior proof-gated.
- **GAP-019** (Docker trusted-host): gates the brokers/helpers used by the
  enrollment-provisioner and migration capture helper; acceptance flag
  `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED=accepted` (referenced, enforced elsewhere).
