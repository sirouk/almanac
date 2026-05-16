# Codebase Map

## Scope

This map covers the public repository surfaces relevant to ArcLink Sovereign
Fleet enrollment, placement, inventory health, CLI hardening, and cloud
provisioning. It excludes private state, live credentials, generated runtime
state, dependency folders, logs, production service state, and Hermes core.

## Planning Entrypoints

| Path | Role |
| --- | --- |
| `IMPLEMENTATION_PLAN.md` | BUILD handoff plan for the eight fleet phases. |
| `research/RALPHIE_ARCLINK_FLEET_ENROLLMENT_STEERING.md` | Authoritative steering reference for this mission. |
| `research/RALPHIE_SOVEREIGN_AUDIT_VERIFICATION_20260511.md` | Historical audit verification and closure context; use for regression awareness. |
| `docs/arclink/vocabulary.md` | Vocabulary split: operator surfaces stay technical; Captain surfaces use ArcPod/Pod/Agent/Captain/Crew/Raven. |
| `docs/arclink/control-node-production-runbook.md` | Existing Sovereign Control Node operator runbook to extend or cross-link. |
| `docs/arclink/sovereign-control-node.md` | Architecture/operator docs for the Control Node. |
| `docs/API_REFERENCE.md` and `docs/openapi/arclink-v1.openapi.json` | API docs if enrollment callback or dashboard health APIs are exposed. |

## Directory Map

| Directory | Responsibility |
| --- | --- |
| `python/` | Control DB, fleet registry, inventory registry, executor adapters, provisioning worker, action worker, hosted API, dashboard snapshots, evidence/redaction, notification delivery, provider clients, and tests' Python targets. |
| `bin/` | Canonical operator/deploy/control shell surface. New fleet subcommands and thin daemon/bootstrap runners belong here. |
| `compose.yaml` | Dockerized Sovereign Control Node services and job-loop workers. Add the inventory worker here when Phase 4 lands. |
| `tests/` | Focused no-secret regression suites. Existing fleet/action/executor/inventory suites should be expanded; new enrollment and inventory-worker tests are required. |
| `docs/` | Operator runbooks, API reference, OpenAPI, architecture docs, vocabulary canon, and status docs. |
| `web/` | Next.js operator/Captain dashboard. Fleet detail remains operator-only; Captain visibility must remain coarse. |
| `research/` | Ralphie steering, research artifacts, completion notes, live-proof evidence notes. |
| `consensus/` | BUILD gate and blocked-flow rationale. |

## Fleet Architecture Rails

| Rail | Current files / patterns | Notes |
| --- | --- | --- |
| Schema | `python/arclink_control.py` | Owns `arclink_inventory_machines`, `arclink_fleet_hosts`, `arclink_deployment_placements`, audit tables, indexes, drift checks, and status constants. |
| Fleet placement | `python/arclink_fleet.py` | Registers hosts, updates drain/status/load, lists capacity, chooses placements, removes placements, reconciles observed load. |
| Inventory | `python/arclink_inventory.py` | Registers/probes/drains/removes machines, computes ASU, links machines to fleet hosts, exposes a CLI used by `deploy.sh`. |
| Provider clients | `python/arclink_inventory_hetzner.py`, `python/arclink_inventory_linode.py` | Current provider path lists resources; create/bootstrap/delete orchestration is still open. |
| Executor adapters | `python/arclink_executor.py` | Docker Compose local/SSH runners, fake runner, secret resolvers, live-adapter fail-closed behavior. |
| Provisioning worker | `python/arclink_sovereign_worker.py` | Already performs placement-aware provisioning and contains `_executor_for_host`, the helper to factor for action-worker reuse. |
| Action worker | `python/arclink_action_worker.py` | Claims admin/day-2 action intents and currently builds one env-derived executor for the whole worker. |
| Hosted API and dashboard | `python/arclink_hosted_api.py`, `python/arclink_dashboard.py` | Existing operator scale snapshot and admin surfaces; Phase 4/5 may add fleet health summary surfaces. |
| Audit/events | `append_arclink_audit`, `append_arclink_event` in `python/arclink_control.py` | Fleet transitions and action routing must write structured audit entries. |
| Notification rail | `notification_outbox`, `python/arclink_notification_delivery.py` | Use for unreachable hosts, audit-chain failures, token expiry, and capacity warnings. |
| Secret redaction | `python/arclink_evidence.py`, `python/arclink_secrets_regex.py` | Reuse for enrollment token and provider/SSH error safety. |
| Docker job-loop | `bin/docker-job-loop.sh`, existing Compose services | Use for `arclink_fleet_inventory_worker.py`; do not add a separate scheduler dependency. |

## Existing CLI Entrypoints

| Command | Current state | BUILD target |
| --- | --- | --- |
| `deploy.sh control fleet-key` | Generates/prints the fleet SSH public key path and guidance. | Add `--rotate` with safe backup and operator confirmation workflow. |
| `deploy.sh control register-worker` | Interactive TTY-only remote worker registration; stores SSH metadata in fleet host metadata. | Add non-interactive flags and `--json`; keep interactive default. |
| `deploy.sh control inventory list` | Calls `python/arclink_inventory.py list` and prints prose/table output. | Add `--json` and filtering. |
| `deploy.sh control inventory probe` | Calls SSH probe for one target. | Add `--all` / `probe-all` and structured result output. |
| `deploy.sh control inventory add manual` | Interactive manual registration. | Preserve and make scriptable as needed. |
| `deploy.sh control inventory add hetzner|linode` | Lists existing provider resources when token exists. | Create/bootstrap/register/delete idempotently in Phase 6. |
| `deploy.sh control inventory drain|remove` | Drains or removes a machine with placement guards. | Add `--json`, `--filter`, `--force` only where documented. |
| `deploy.sh control inventory set-strategy` | Persists `ARCLINK_FLEET_PLACEMENT_STRATEGY`. | Ensure placement consumes strategy and add region-tier logic. |

## Missing BUILD Surfaces

| Surface | Target files |
| --- | --- |
| Enrollment schema and helpers | `python/arclink_control.py`, new or existing fleet module, `tests/test_arclink_fleet_enrollment.py` |
| Enrollment callback API | `python/arclink_hosted_api.py` or a narrow control API route, API docs/tests |
| Fleet audit chain | `python/arclink_control.py`, fleet/enrollment helpers, inventory health tests |
| Probe history and worker daemon | `python/arclink_fleet_inventory_worker.py`, `compose.yaml`, `tests/test_arclink_fleet_inventory_worker.py` |
| Bootstrap and probe wrapper scripts | `bin/arclink-fleet-join.sh`, `bin/arclink-fleet-probe-wrapper`, shell/deploy tests |
| CLI JSON and new subcommands | `bin/deploy.sh`, `python/arclink_inventory.py`, docs and deploy regression tests |
| Cloud create/bootstrap/delete | Provider client modules, inventory CLI, fake-provider tests |
| Operator runbook | `docs/arclink/fleet-operator-runbook.md`, control-node docs |
| Live proof notes | `research/` evidence note generated only after operator-authorized Phase 7 |

## Architecture Assumptions

- `arclink_inventory_machines` is machine identity, hardware, provider, and lifecycle state.
- `arclink_fleet_hosts` is placement capacity, region, drain, and executor metadata.
- The one-to-one relationship is represented by `machine_host_link` and should be checked by a reconciler rather than collapsed.
- New behavior must keep the legacy static env executor path for single-host installs with no active placement row.
- Pull-based probing over SSH is the v1 worker-health model.
- New fleet automation must not require live credentials or real remote hosts in CI.
