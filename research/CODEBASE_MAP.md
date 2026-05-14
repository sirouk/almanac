# Codebase Map

## Scope

This map covers public repository areas relevant to Wave 3: 1:1 Pod Migration.
It excludes private state, live credentials, user Hermes homes, dependency
folders, caches, logs, production service state, and Hermes core.

## Planning Entrypoints

| Path | Role |
| --- | --- |
| `IMPLEMENTATION_PLAN.md` | BUILD handoff plan for Wave 3 only. |
| `research/RALPHIE_ARCPOD_CAPTAIN_CONSOLE_STEERING.md` | Authoritative Wave 3 backlog under `## Wave 3: 1:1 Pod Migration`. |
| `research/RESEARCH_SUMMARY.md` | Current PLAN summary and assumptions. |
| `research/COVERAGE_MATRIX.md` | Goal-to-proof matrix for BUILD validation. |
| `research/STACK_SNAPSHOT.md` | Deterministic stack hypothesis and alternatives. |

## Runtime Directories

| Directory | Responsibility |
| --- | --- |
| `python/` | Control DB, hosted API, auth/session/CSRF, provisioning, executor, fleet placement, action worker, migration orchestration, dashboard, bots, ingress, notifications, MCP, and memory modules. |
| `tests/` | Focused regression tests for schema, migration, admin actions, action worker, executor, fleet, hosted API, and adjacent behavior. |
| `bin/` | Canonical deploy/control scripts and job wrappers. Wave 3 should touch shell only for a real GC job-loop integration or operator command. |
| `docs/arclink/` | Operator and production runbooks. Wave 3 migration docs belong here after behavior is true. |
| `docs/openapi/` | API contract. Update only if BUILD adds a new route or request/response schema. |
| `config/` | Public example env and model/provider config. Wave 3 uses migration defaults here. |
| `compose.yaml` | Docker service topology. Add migration GC service integration only if BUILD chooses a service-level loop. |
| `web/` | Next.js product/admin UI. Wave 3 should not expose Captain migration while the default flag is off. |
| `research/` | Planning and completion artifacts. |
| `consensus/` | Build gate and prior plan-gate records. |

## Wave 3 Source Surfaces

| Surface | Current candidate state | BUILD handoff target |
| --- | --- | --- |
| Migration schema | `arclink_pod_migrations` exists with placement links, hosts, roots, manifests, rollback/verification metadata, retention/GC fields, indexes, statuses, and drift checks. | Validate schema migration from empty and existing DBs; ensure status/relationship drift tests cover invalid and missing references. |
| Migration module | `python/arclink_pod_migration.py` implements planning, capture, materialization, verification, rollback, replay, dry-run, audit/events, and GC. | Run focused tests, inspect secret redaction, confirm portable manifests, and harden any uncovered edge cases. |
| Admin `reprovision` | Dashboard readiness and action worker now model `reprovision` as executable when executor probes pass. | Verify readiness, queuing, action-operation linking, dry-run, success, and safe failure. |
| Captain migration | No exposed Captain route was identified. | Keep disabled by default. Add a gated route only if required, with CSRF/session tests and no visible button until policy is decided. |
| State capture | Candidate module captures the source root into a migration staging directory and records relative path, boundary, size, mode, and digest. | Verify vault, memory, sessions, configs, secret-reference boundaries, bot env metadata, DNS rows, placement, and Hermes home are represented without secret contents. |
| Target materialization | Candidate module renders target provisioning intent and applies through the executor fake/local/SSH abstraction. | Confirm it does not fork provisioning logic and does not add live host mutation outside executor rails. |
| Rollback | Candidate module restores source placement and removes target placement on failed verification. | Validate one-active-placement invariant, audit/event emission, and idempotent replay of rolled-back rows. |
| GC | Candidate module marks expired successful migrations and removes staging artifacts when requested. | Validate recent, failed, rolled-back, cancelled, and succeeded-expired cases. |

## Relevant Existing Patterns

| Pattern | Files |
| --- | --- |
| Schema migrations, constants, indexes, drift checks | `python/arclink_control.py`, `tests/test_arclink_schema.py` |
| Operation idempotency | `python/arclink_control.py`, executor and migration tests |
| Admin action queue and readiness | `python/arclink_dashboard.py`, `python/arclink_api_auth.py`, `python/arclink_hosted_api.py`, `tests/test_arclink_admin_actions.py` |
| Action worker dispatch | `python/arclink_action_worker.py`, `tests/test_arclink_action_worker.py` |
| Fake/local/SSH executor split | `python/arclink_executor.py`, `tests/test_arclink_executor.py` |
| Provisioning intent rendering | `python/arclink_provisioning.py`, `tests/test_arclink_provisioning.py` |
| Fleet placement and host load | `python/arclink_fleet.py`, `tests/test_arclink_fleet.py` |
| Compose apply and health conventions | `python/arclink_sovereign_worker.py`, `tests/test_arclink_sovereign_worker.py` |

## Architecture Assumptions

- Do not modify Hermes core; migration works through ArcLink wrappers,
  provisioning renders, plugins, hooks, generated config, service units, and
  executor operations.
- Keep Shared Host, Shared Host Docker, and Sovereign Control Node concepts
  distinct. Wave 3 targets Sovereign Control Node Pod migration.
- Use relative paths in manifests and docs so artifacts remain portable.
- Store secret references and file digests, not secret values.
- Prefer fake executor and temporary-directory tests over live deploy proof.
