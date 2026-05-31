# Ground Truth: Operator Raven, Operator Agent, Action Worker, Rollout, Upgrade Broker

Date: 2026-05-30. Branch: arclink. Source of truth = code, not docs.

Subsystem files:
- `python/arclink_operator_raven.py` — operator command surface (read previews + real action queueing)
- `python/arclink_operator_agent.py` — the operator's single in-stack Hermes identity + free-form turn bridge
- `python/arclink_operator_upgrade_broker.py` — Docker-mode operator upgrade broker HTTP service
- `python/arclink_action_worker.py` — admin/operator action intent consumer (executor dispatch)
- `python/arclink_rollout.py` — rollout model + ArcPod update rollout planner/materializer/batch executor
- `python/arclink_pin_upgrade_check.py` — hourly pinned-component upstream upgrade detector
- Wiring: `python/arclink_telegram.py`, `python/arclink_curator_onboarding.py`, `python/arclink_curator_discord_onboarding.py`, `python/arclink_control.py` (operator_actions table + drain), `python/arclink_enrollment_provisioner.py` (root maintenance loop), `python/arclink_dashboard.py` (action support matrix)

---

## HEADLINE: GAP-029 read-only/dry-run claim is STALE. Operator Raven QUEUES REAL ACTIONS today.

The symphony doc (`sovereign-control-node-symphony.md` lines 193-198) still says Operator Raven is "a first local read-only/dry-run Operator Raven command layer for status, fleet list, worker probe dry-run, user lookup, pod repair dry-run, and injected upgrade check." That is wrong as of this code.

`arclink_operator_raven.py` module docstring (lines 1-18) and `MUTATING_COMMANDS = frozenset({"pod_repair", "rollout", "host_upgrade", "pin_upgrade"})` (line 141) define a three-mode contract for mutating commands:
1. `--dry-run` -> preview, changes nothing (historical behavior).
2. no `--dry-run` and no operator `actor_id` -> **fail closed** (read-only refusal via `_require_operator_actor`, lines 298-307).
3. no `--dry-run` WITH an operator `actor_id` -> **QUEUE a real, audited intent** that the action worker / enrollment provisioner executes asynchronously.

Tests confirm real queueing: `tests/test_arclink_operator_raven.py::test_operator_raven_pod_repair_queues_real_intent_with_actor` (asserts `mutation_performed is True`, rows in `arclink_action_intents`), `::test_operator_raven_host_and_pin_upgrade_queue_operator_actions` (rows in `operator_actions`), and dry-run/actorless tests asserting nothing is queued.

---

## (a) What is actually implemented today

### Operator Raven command surface (`arclink_operator_raven.py`)

Entry points: `parse_operator_raven_command`, `operator_raven_command_requested`, `operator_raven_command_is_mutating`, `dispatch_operator_raven_command(conn, text, *, env, upgrade_check_runner, actor_id, idempotency_key)`. Output dict always has `handled`, `command`, `mutation_performed`, `message` (run through `_redact_text`, lines 1390-1398, which redacts secret-ish `key=value` lines).

Canonical command names (after alias normalization via `_COMMAND_ALIASES`, lines 47-136) and their handlers (dispatch table lines 268-282):

READ-ONLY commands (never mutate):
- `status` (`_handle_status`) — provisioning readiness, fleet active/total, user/deployment/rollout status counts, admin-action queueable count + executor adapter, queued/running operator action counts. Lists the act/next command hints and the live-proof gates `PG-PROD, PG-BOTS, PG-PROVIDER, PG-PROVISION, PG-UPGRADE`.
- `agents` (`_handle_agents`) — Captain ArcPods + the single Operator Hermes + legacy `agents` table count. Operator vs captain split via `_deployment_is_operator` (metadata `operator_agent` flag or deployment_id == "operator").
- `fleet_list` (`_handle_fleet_list`) — `list_fleet_hosts` from `arclink_fleet`.
- `worker_probe` (`_handle_worker_probe`) — **DRY-RUN ONLY in this slice** (lines 475-478 refuse non-dry-run). No SSH/Docker/health probe is ever run.
- `user_lookup` (`_handle_user_lookup`) — user search across `arclink_users` + per-user deployments + academy summary.
- `academy_status` (`_handle_academy_status`) — read-only academy training status via `crew_academy_status`. Always appends PG-PROVIDER/PG-HERMES gating note. No queue.
- `academy_roster` (`_handle_academy_roster`) — fleet-wide/scoped academy roster (graduates / in-academy / enrolled) via `arclink_academy_programs`. No queue; PG-PROVIDER/PG-HERMES gated.
- `upgrade_check` (`_handle_upgrade_check`) — fail-closed unless an `upgrade_check_runner` callable is injected (lines 746-752). Telegram injects `_local_operator_upgrade_check_runner`.
- `action_status` (`_handle_action_status`) — reads recent `arclink_action_intents` (admin action intents) AND `operator_actions` rows. Optional positional arg filters by `action_id`.

MUTATING commands (queue real audited intents when actor present):
- `pod_repair` (`_handle_pod_repair`, lines 637-734) — actions `restart`, `reprovision`, `dns_repair` (`_POD_REPAIR_ACTIONS`). Checks `admin_action_execution_readiness` `action_support` for `queueable`. If queueable, calls `queue_arclink_admin_action` (into `arclink_action_intents`) with `metadata={"source":"operator_raven", "actor_id":..., "requested_by":...}` and an idempotency key from `_action_idempotency_key`. Blocks with a per-action proof gate message (PG-PROVISION/PG-INGRESS) if not queueable. `mutation_performed` is True only if not already queued (idempotent replay returns existing).
- `rollout` (`_handle_rollout`, lines 880-1011) — parses `<target-version> [--batch-size N] [--execute|--execute-batch]`. Calls `plan_arcpod_update_rollout` (dry-run plan, no side effects). On `--dry-run` prints batch plan. On real run: requires actor, requires plan status != blocked, requires `action_support["rollout"]["queueable"]`, then `queue_arclink_admin_action(action_type="rollout", target_kind="system", target_id="arcpod-fleet", metadata={...target_version, batch_size, execute_local_batch})`.
- `host_upgrade` (`_handle_host_upgrade`, lines 772-818) — aliases include `/upgrade`, `/update`, `/self_upgrade`, `/apply_upgrade`, `/control_upgrade`. Does NOT use the executor adapter; calls `request_operator_action(conn, action_kind="upgrade", request_source="operator-raven")` into the `operator_actions` table. The **root maintenance loop / enrollment provisioner** drains it through the upgrade broker (see below). `mutation_performed` = `created`.
- `pin_upgrade` (`_handle_pin_upgrade`, lines 821-877) — components `PIN_UPGRADE_COMPONENTS = (hermes, qmd, nextcloud, postgres, redis, nvm, node)` (line 145). Calls `request_operator_action(action_kind="pin-upgrade", requested_target=component, dedupe_by_target=True)`.

Operator approval code: `operator_approval_code(env)` reads `ARCLINK_OPERATOR_TELEGRAM_APPROVAL_CODE` or `ARCLINK_OPERATOR_APPROVAL_CODE` (`_APPROVAL_CODE_KEYS`, line 216). `strip_operator_approval_code(text, code)` does a constant-time `hmac.compare_digest` on the trailing token, then strips it. Telegram calls this only for mutating commands (`arclink_telegram.py` lines 1129-1143); a missing/wrong code returns "Operator code required for this action."

### Operator's single Hermes agent (`arclink_operator_agent.py`)

The operator gets exactly ONE Hermes agent — a first-class control-stack Compose service, NOT a tenant ArcPod and NOT a legacy shared-host install. Module is control-DB only (queues + resolves; never runs Docker/SSH).

- Settings keys: `operator_agent_deployment_id`, `operator_agent_user_id`, `operator_agent_runtime`.
- Reserved ids: `DEFAULT_OPERATOR_AGENT_DEPLOYMENT_ID="operator"`, `DEFAULT_OPERATOR_AGENT_PREFIX="operator-helm"`, `DEFAULT_OPERATOR_AGENT_USER_ID="operator"`, `DEFAULT_OPERATOR_AGENT_RUNTIME="control-stack"`.
- `ensure_operator_agent_user` (comped account, `entitlement_state="comp"`), `ensure_operator_agent_deployment` (idempotent; refuses to create a SECOND operator agent — one-agent invariant), `ensure_operator_agent` (CLI `ensure`). Deployment metadata stamps `operator_agent=True`, `not_arcpod=True`, `bundle_agent_count=1`, `provisioning_mode="control-stack"`.
- `assert_single_operator_agent` enforces the invariant (raises if >1).
- Ready statuses: `OPERATOR_AGENT_READY_STATUSES = {"active", "first_contacted"}`.
- `operator_conversation_routable(conn)` / `operator_agent_is_ready`.
- **Outer Operator Hermes arcpod bridge IS present**: `enqueue_operator_agent_turn` (lines 198-266) routes a free-form operator message to the in-stack Hermes gateway through the existing `public-agent-turn` notification worker, stamped with `operator_turn=True` and `source_kind="operator_chat"`. Telegram wires this via `_route_operator_free_form_to_agent` (`arclink_telegram.py` lines 1191-1224): when `operator_conversation_routable`, free-form operator text (that is not a Raven command) is queued to the one Hermes agent; the gateway-bridge worker replies asynchronously. If not routable, falls back to the Raven control intro.
- CLI: `python3 arclink_operator_agent.py ensure --require-enabled` (no-op unless `ARCLINK_OPERATOR_AGENT_ENABLED` truthy) and `status`. Runtime setup handled by `bin/install-operator-hermes-home.sh` + Control Node Compose services.

### Action worker (`arclink_action_worker.py`)

Consumes `arclink_action_intents` rows (the queue Operator Raven `pod_repair`/`rollout` write to). NOT the `operator_actions` table (that is drained by the provisioner). Key surface:
- `process_next_arclink_action`, `process_arclink_action_batch`, `_claim_next_queued_action` (atomic `BEGIN IMMEDIATE` claim), `recover_stale_actions` (running > 1h back to queued), `run_pod_migration_gc`, `list_action_attempts`.
- `_EXECUTOR_ACTIONS = {restart, reprovision, dns_repair, rotate_chutes_key, refund, cancel, comp, backup_write_check}` (line 57).
- `_dispatch_action` routes by `action_type` (lines 818-1258): `restart` -> `docker_compose_lifecycle`; `dns_repair` -> `cloudflare_dns_apply`; `rotate_chutes_key` -> `chutes_key_apply`; `refund`/`cancel` -> `stripe_action_apply`; `comp` -> `comp_arclink_subscription`; `backup_write_check` -> fail-closed record (PG-BACKUP); `academy_apply_preview` / `academy_apply` -> academy staging (live writes need `ARCLINK_ACADEMY_APPLY_LIVE` + PG-HERMES); `reprovision` -> `migrate_pod` (pod migration); `rollout` -> `plan_arcpod_update_rollout` + `materialize_arcpod_update_rollout_job` + optional `execute_arcpod_update_rollout_batch`.
- Executor selection: `_select_action_executor` routes deployment-targeted actions to the deployment's active placement host (`arclink_deployment_placements` JOIN `arclink_fleet_hosts`); `ARCLINK_EXECUTOR_ADAPTER` must be `fake|local|ssh`. SSH/local builds a `SovereignSecretResolver`.
- `main()` loop honors `ARCLINK_EXECUTOR_ADAPTER`; `disabled/off/none` -> prints pending count and exits 0. Runs `recover_stale_actions` + `process_arclink_action_batch` + `run_pod_migration_gc` each interval.
- Tables written: `arclink_action_attempts`, `arclink_action_intents`, plus events/audit via `append_arclink_event`/`append_arclink_audit` with actor `system:action_worker`.

### Rollout (`arclink_rollout.py`)

Two layers:
1. Legacy generic rollout model: `create_rollout`, `advance_rollout_wave`, `pause_rollout`, `fail_rollout`, `rollback_rollout`, `get_rollout`, `list_rollouts`, `rollout_version_drift` over `arclink_rollouts`. Statuses `ROLLOUT_STATUSES = {planned, in_progress, paused, completed, failed, rolled_back}`. Rollback plans must include `preserve_state_roots` (raises otherwise).
2. ArcPod update rollout (GAP-032 work):
   - `plan_arcpod_update_rollout` (lines 254-431) — **pure no-side-effect dry-run planner**. Selects `active` deployments excluding the operator agent (`NOT LIKE '%"operator_agent"%'`). Per candidate: current vs target version, required state roots (`ARCPOD_UPDATE_REQUIRED_STATE_ROOTS = root, config, state, vault, hermes_home`), service health blockers (`ARCPOD_UPDATE_HEALTHY_STATUSES`), rollback plan, pending health-smoke (`ARCPOD_UPDATE_SMOKE_CHECKS`, 8 checks). Batches ready candidates (`ARCPOD_UPDATE_DEFAULT_BATCH_SIZE=1`, max 25). Returns `execution.enabled=False`, `mutation_performed=False`, `proof_gate=ARCPOD_UPDATE_PROOF_GATE="PG-UPGRADE/PG-HERMES"`, `live_proof_required=True`.
   - `materialize_arcpod_update_rollout_job` (lines 434-620) — **local typed job transition only**. Materializes a ready dry-run plan into deterministic per-Pod `arclink_rollouts` rows (one per deployment) grouped under a `rollout_group_id` (`rltgrp_<hash>`). Idempotency: same key bound to a different plan shape is rejected. No deploy scripts, Docker, SSH, or provider calls. `live_mutation_performed=False`, `local_mutation_performed = created_rollout_count > 0`.
   - `execute_arcpod_update_rollout_batch` (lines 623-834) — **record-only fake/local batch state machine**. Requires an explicit executor contract `{adapter in (fake,local), record_only=True}` (`_validate_rollout_executor_contract`). Transitions one batch `planned -> in_progress -> completed|failed`, records intended refresh steps (`_recorded_rollout_execution_steps`), pending health-smoke placeholders, repair hints, stop-on-failure. `commands_run=[]`, `live_mutation_performed=False`, `local_mutation_performed=True`. NEVER invokes deploy/Docker/systemd/SSH/provider/live health.

### Operator upgrade broker (`arclink_operator_upgrade_broker.py`)

Dedicated Docker-mode HTTP service (`SERVICE_NAME="operator-upgrade-broker"`, `ThreadingHTTPServer`, default `127.0.0.1:8917`). Owns the Docker socket + writable host checkout for allowlisted upgrade commands; **rejects raw command input** (`_reject_raw_commands` rejects `args`/`cmd`/`command` keys).
- Routes: `GET /health` (503 if token unconfigured), `POST /v1/operator-upgrade` (bearer header `X-ArcLink-Operator-Upgrade-Broker-Token`, constant-time compare).
- Operations: `run_operator_upgrade` (runs `deploy.sh upgrade`) and `run_pin_upgrade` (runs `bin/component-upgrade.sh <component> apply <flag> <target> --skip-upgrade` per item, then `deploy.sh upgrade`).
- Allowlisted pin components: `ALLOWED_PIN_COMPONENTS = {hermes-agent, qmd, nextcloud, postgres, redis, nvm, node}`. Pin upgrade kinds -> flags: `PIN_UPGRADE_FLAGS = {git-commit:--ref, git-tag:--tag, container-image:--tag, npm:--version, nvm-version:--version, release-asset:--version}`.
- Hardening (`require_docker_trusted_host_risk_accepted`, `require_trusted_docker_binary`): fixed repo-script validation (`_require_operator_repo_script` rejects symlinks/non-regular/non-exec), private operator log path confinement to `state/operator-actions`, upstream deploy-key path confinement to private state, single-line env validation. Rejections recorded as incidents via `record_rejection_incident` with reason codes (`_rejection_reason`/`_rejection_message`). Maps to GAP-019-J/AB/AI/AV/AW.
- Called from `arclink_control.py` `_operator_upgrade_broker_request` (default URL `http://operator-upgrade-broker:8917`), driven by `_run_brokered_host_upgrade` / `_run_pin_upgrade_action`, which the provisioner's `_run_pending_operator_actions` invokes when in Docker mode (`ARCLINK_COMPONENT_UPGRADE_MODE=docker`).

### Pin upgrade detector (`arclink_pin_upgrade_check.py`)

Hourly detector (via `arclink-curator-refresh.timer`, also `./deploy.sh pin-upgrade-notify`). `MANAGED_COMPONENTS = (hermes-agent, hermes-docs, nvm, node, qmd, nextcloud, postgres, redis)`. For each: runs `bin/component-upgrade.sh <c> check`, compares to `config/pins.json` pin, maintains throttle state in `pin_upgrade_notifications` table (one digest per release target, default `notify_limit_per_release=1`). For git-commit pins, throttles on the release-version label (e.g. `v0.11.0`) not the raw commit. Builds one rolled-up digest, registers an Install-button action token (`register_pin_upgrade_action`), and queues an operator notification. The digest's chat action paths reference `/upgrade` and `/pin_upgrade <component>` — directly tying the detector to Operator Raven mutating commands.

### Two distinct queues (important nuance)

- `arclink_action_intents` (+ `arclink_action_attempts`) — drained by `arclink_action_worker.py`. Operator Raven `pod_repair` and `rollout` write here (via `queue_arclink_admin_action`), as do admin dashboard/API actions.
- `operator_actions` table — drained by the enrollment provisioner's root maintenance loop (`_run_pending_operator_actions`, `arclink_enrollment_provisioner.py:2246`, invoked from line 3265). Operator Raven `host_upgrade` (`upgrade`) and `pin_upgrade` (`pin-upgrade`) write here via `request_operator_action`. Lifecycle helpers: `request_operator_action`, `mark_operator_action_running`, `finish_operator_action` (status completed/failed/dismissed), `get_pending_operator_action`, `get_active_operator_action`, `_fail_stale_running_operator_actions`. Schema: `arclink_control.py:760` (id, action_kind, requested_target, requested_by, request_source, status, note, created_at, started_at, finished_at, log_path).

---

## (b) Proof-gated / fake-adapter / local-only

- Operator Raven mutating commands queue intents but live mutation stays gated by `ARCLINK_EXECUTOR_ADAPTER` (`fake` = record-only) and per-action proof gates: PG-PROVISION (restart/reprovision), PG-INGRESS (dns_repair), PG-UPGRADE/PG-HERMES (rollout), PG-PROVIDER (chutes), PG-STRIPE (refund/cancel), PG-BACKUP (backup_write_check).
- ArcPod rollout: planner is pure-dry-run; materializer is local-typed-rows only; batch executor is record-only fake/local. NO real per-Pod refresh/apply/health exists. `proof_gate=PG-UPGRADE/PG-HERMES`, `live_proof_required=True` everywhere. This is exactly the residue of GAP-032.
- `worker_probe`: dry-run-only in this slice (no live SSH/Docker/health probe at all).
- `upgrade_check`: fail-closed unless a runner is injected.
- Academy actions: `academy_apply` live Agent-home writes require `ARCLINK_ACADEMY_APPLY_LIVE=1` AND PG-HERMES; otherwise recorded fail-closed.
- Operator upgrade broker live host upgrades require Docker mode + `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED=accepted` + broker token + reachable Docker/host repo. The broker is the trusted-host residual-risk escalation boundary.
- Operator agent free-form bridge depends on a routable in-stack Hermes (live gateway). Source enqueues; live reply requires the gateway-bridge worker + Hermes runtime (PG-HERMES territory).
- Pin upgrade detector upstream checks hit GitHub raw/`component-upgrade.sh check` over network; failures degrade gracefully (transient -> preserve throttle).

---

## (c) Canonical vocabulary (exact names)

Modules/services: `operator-upgrade-broker` (service name, port 8917), `control-operator-hermes-gateway`, `control-operator-hermes-dashboard`, `control-operator-hermes-setup`, `control-operator-qmd-mcp`, `agent-supervisor` (Compose services in `bin/arclink-docker.sh`).

Tables: `operator_actions`, `arclink_action_intents`, `arclink_action_attempts`, `arclink_rollouts`, `pin_upgrade_notifications`, `arclink_deployment_placements`, `arclink_fleet_hosts`, `arclink_service_health`, `arclink_deployments`, `arclink_users`.

Operator Raven commands (canonical): `status`, `agents`, `fleet_list`, `worker_probe`, `user_lookup`, `pod_repair`, `upgrade_check`, `host_upgrade`, `pin_upgrade`, `rollout`, `action_status`, `academy_status`, `academy_roster`. Mutating set: `pod_repair`, `rollout`, `host_upgrade`, `pin_upgrade`.

Action kinds (`operator_actions`): `upgrade`, `pin-upgrade`, `send-discord-agent-dm`. Action intent types (`arclink_action_intents`): `restart`, `reprovision`, `dns_repair`, `rotate_chutes_key`, `refund`, `cancel`, `comp`, `backup_write_check`, `rollout`, `academy_apply_preview`, `academy_apply`.

Operation kinds: `docker_compose_lifecycle`, `cloudflare_dns_apply`, `chutes_key_apply`, `stripe_action_apply`, `control_db_comp`, `pod_migration`, `arcpod_update_rollout`, `arcpod_update_rollout_batch`, `backup_git_write_check`.

Constants: `MUTATING_COMMANDS`, `PIN_UPGRADE_COMPONENTS`, `_POD_REPAIR_ACTIONS`, `ARCPOD_UPDATE_PROOF_GATE`, `ARCPOD_UPDATE_REQUIRED_STATE_ROOTS`, `ARCPOD_UPDATE_SMOKE_CHECKS`, `ALLOWED_PIN_COMPONENTS`, `PIN_UPGRADE_FLAGS`, `OPERATOR_AGENT_READY_STATUSES`, `DEFAULT_OPERATOR_AGENT_*`.

Env vars: `ARCLINK_EXECUTOR_ADAPTER`, `ARCLINK_OPERATOR_TELEGRAM_APPROVAL_CODE`, `ARCLINK_OPERATOR_APPROVAL_CODE`, `ARCLINK_OPERATOR_AGENT_ENABLED`, `ARCLINK_OPERATOR_UPGRADE_BROKER_URL`, `ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN`, `ARCLINK_OPERATOR_UPGRADE_BROKER_HOST/PORT`, `ARCLINK_ROLLOUT_BATCH_SIZE`, `ARCLINK_ROLLOUT_MAX_BATCH_SIZE`, `ARCLINK_ROLLOUT_TARGET_VERSION`, `ARCLINK_COMPONENT_UPGRADE_MODE`, `ARCLINK_ACADEMY_APPLY_LIVE`, `ARCLINK_ACTION_WORKER_ALLOW_LIFECYCLE_PATH_OVERRIDES`.

CLIs/scripts: `python3 arclink_operator_agent.py ensure|status`, `python3 arclink_action_worker.py`, `python3 arclink_operator_upgrade_broker.py`, `python3 arclink_pin_upgrade_check.py`, `./deploy.sh upgrade`, `./deploy.sh pin-upgrade-notify`, `bin/component-upgrade.sh`, `bin/install-operator-hermes-home.sh`.

---

## (d) Undocumented / newer than docs

- Operator Raven QUEUES REAL ACTIONS with a three-mode (dry-run / fail-closed / queue) contract — directly contradicts symphony's "read-only/dry-run" framing. UNDOCUMENTED in all three backing docs.
- Operator approval code second-factor for mutating Raven commands (`operator_approval_code` / `strip_operator_approval_code`) — only `operations-runbook.md` mentions the env vars for `/approve`/`/deny`/`/upgrade`, not the full mutating-command requirement.
- The operator's single in-stack Hermes agent identity (`arclink_operator_agent.py`, one-agent invariant, control-stack runtime) — NOT documented in the three target docs.
- Outer Operator Hermes free-form chat bridge (`enqueue_operator_agent_turn` + `operator_turn` -> `public-agent-turn` worker) — UNDOCUMENTED.
- `rollout` admin action is now `worker_support: "wired"` and queueable; ArcPod rollout planner/materializer/record-only batch executor exist. Both runbooks still list rollout as pending/disabled.
- `academy_apply_preview` / `academy_apply` action types and the `academy_status` / `academy_roster` Raven commands — UNDOCUMENTED in these docs.
- `worker_probe` Raven command (dry-run-only) — not in runbooks.
- Extensive alias surface (`/upgrade`, `/update`, `/self_upgrade`, `/arcpod_rollout`, `/crew`, etc.).

---

## (e) Per-doc staleness verdicts

### docs/arclink/sovereign-control-node-symphony.md — HEAVY (the intended dream shape, now lagging code)
- Lines 193-198: "first local read-only/dry-run Operator Raven command layer ... It does not yet have a single full-service Operator Raven control plane. That is GAP-029." -> CODE NOW QUEUES REAL ACTIONS (`pod_repair`, `rollout`, `host_upgrade`, `pin_upgrade`) gated by operator identity + approval code + executor adapter + proof gates. Correction: Raven has a real-but-fenced mutation layer; GAP-029 residue is breadth/policy unification, not "read-only".
- Lines 194-196 enumerate only status/fleet/worker-probe-dry-run/user-lookup/pod-repair-dry-run/injected-upgrade-check. Missing: `agents`, `action_status`, `academy_status`, `academy_roster`, real `pod_repair`/`rollout`/`host_upgrade`/`pin_upgrade` queueing.
- Lines 632-641 (Hermes/ArcPod updates): describes the dry-run planner + local materialization + one record-only batch as current — this part is ACCURATE and matches `arclink_rollout.py`. Keep, but note GAP-032 residue = real refresh/apply + live multi-Pod proof only.
- Does not mention the operator's single in-stack Hermes agent or the free-form bridge at all.

### docs/arclink/operations-runbook.md — LIGHT-to-HEAVY (good broker/action coverage, stale matrix + missing Raven mutation)
- Admin action readiness matrix (lines 142-149): MISSING the `rollout` row, which is now `wired`/queueable in `arclink_dashboard.ARCLINK_ADMIN_ACTION_SUPPORT`. Add `rollout | arcpod_update_rollout | action worker (fake/local record-only batch) | PG-UPGRADE/PG-HERMES`.
- Operator upgrade broker coverage (lines 418, 599-638, 801-853) is ACCURATE and current (service name, operations `run_operator_upgrade`/`run_pin_upgrade`, GAP-019 hardening, allowlists, private-log confinement).
- Approval code (lines 85-93) mentions `/approve`/`/deny`/`/upgrade` but does NOT state that ALL Operator Raven mutating commands (`pod_repair`, `rollout`, `pin_upgrade`, `host_upgrade`) require the code on the originating channel. Expand.
- Scale Operations section (1218-1260) lists modules `arclink_action_worker.py` + `arclink_rollout.py` but does NOT mention Operator Raven as a mutation entry point or the `operator_actions` queue / root maintenance drain. Missing the two-queue distinction.
- No mention of the operator single Hermes agent or the free-form chat bridge.

### docs/arclink/control-node-production-runbook.md — HEAVY (stale action matrix, no Raven mutation/agent)
- Admin action matrix (lines 91-98) + lines 100-102: explicitly states "Pending actions such as rollout, suspend, unsuspend, force resynth, and bot-key rotation stay visible as disabled entries with fail-closed reasons until worker dispatch and policy are implemented." -> `rollout` is NO LONGER pending; it is `wired` and queueable (with record-only batch execution). Move `rollout` out of the pending list and into the queueable matrix with operation kind `arcpod_update_rollout` and gate PG-UPGRADE/PG-HERMES.
- Operator Pod Migration section (121-149) is accurate for `reprovision`.
- No mention of Operator Raven as a real action-queueing surface, the operator approval code, the single operator Hermes agent, or the free-form bridge. The doc only references `arclink_action_worker.py` consuming queued admin actions (line 127 of sovereign-control-node.md; production runbook line 117).

### docs/arclink/sovereign-control-node.md — LIGHT (narrow operator coverage)
- Line 127: "`python/arclink_action_worker.py` consumes queued admin actions." True but thin; no Operator Raven, no operator_actions queue, no rollout, no operator agent. Add a short Operator Raven + operator-agent subsection or cross-link.

---

## (f) GAP status (true current state)

- GAP-029 (Operator Raven not yet a full-service chat-native control plane): PARTIALLY CLOSED. Raven now queues real, audited, identity-gated, approval-code-gated mutations (`pod_repair`, `rollout`, `host_upgrade`, `pin_upgrade`) plus a broad read surface and an outer operator-Hermes free-form bridge. Residue: breadth (fleet drain/admit/rotate, billing refuel, security views from chat), unified Raven/action policy, and authorized live proof. The doc's "read-only/dry-run" wording for GAP-029 is factually stale.
- GAP-032 (no Control Node rolling-update orchestrator across all ArcPods): STILL OPEN but with a substantial local skeleton. Planner (`plan_arcpod_update_rollout`), local materializer (`materialize_arcpod_update_rollout_job`), and a record-only fake/local batch executor (`execute_arcpod_update_rollout_batch`) all exist and are queueable end-to-end through Operator Raven + action worker. Missing = real per-Pod refresh/apply execution + live multi-Pod health/smoke proof (PG-UPGRADE/PG-HERMES). The dry-run planner is no longer the only thing; the materializer + record-only batch executor are also implemented (symphony 632-641 already reflects this; the runbooks do not).
- GAP-030 (product readiness reachable without live proof) and GAP-031 (router live provider proof) and GAP-033 (cross-surface live proof) are adjacent gates referenced by Raven status output but owned by other subsystems.
- GAP-019-J/AB/AI/AV/AW: operator-upgrade-broker hardening boundaries — IMPLEMENTED and accurately documented in operations-runbook.md.

Note: `research/RALPHIE_ARCLINK_ECOSYSTEM_GAP_REPAIR_STEERING.md` does not enumerate GAP-029/GAP-032 by id; those ids live in `docs/arclink/sovereign-control-node-symphony.md` (lines 36-43).
