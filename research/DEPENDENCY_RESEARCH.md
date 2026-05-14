# Dependency Research

## Scope

This document records stack and dependency signals relevant to Wave 3: 1:1 Pod
Migration. It does not assert live capability for Stripe, Telegram, Discord,
Chutes, Notion, Cloudflare, Tailscale, Hetzner, Linode, Docker host mutation,
or production deploy flows.

## Stack Components

| Component | Evidence | Wave 3 use | Decision |
| --- | --- | --- | --- |
| Python 3.11+ | `python/*.py`, `tests/test_*.py`, `requirements-dev.txt`, runtime compatibility expectations | Migration orchestrator, schema updates, action dispatch, fake verifiers, GC helpers, tests | Primary implementation surface. |
| SQLite | `python/arclink_control.py` | Migration rows, placements, idempotency, audit/events, DNS rows, service health | Use `ensure_schema`, constants, indexes, and drift checks. |
| Bash | `deploy.sh`, `bin/*.sh` | Optional migration GC wrapper or operator command only if BUILD requires it | Avoid shell changes unless runtime integration requires them. |
| Docker Compose | `compose.yaml`, `Dockerfile`, executor apply/lifecycle | Target materialization and service health through existing executor rail | Use fake runner in tests; live Docker mutation remains blocked. |
| Executor adapters | `python/arclink_executor.py` | Compose lifecycle/apply, DNS apply, rollback apply, fake idempotency digest checks | Reuse; do not add host mutation paths outside executor abstractions. |
| Provisioning renderer | `python/arclink_provisioning.py` | Re-render target intent and state roots | Reuse to avoid divergent deployment config. |
| Fleet placement | `python/arclink_fleet.py`, placement tables | Source/target placement selection and load updates | Reuse existing placement model and preserve one-active-placement invariant. |
| Hosted API/auth | `python/arclink_api_auth.py`, `python/arclink_hosted_api.py` | Existing admin action route and optional Captain-gated route | Admin path is required; Captain path stays disabled by default. |
| Next.js web | `web/package.json`, `web/src/app` | Admin/Captain surfaces if a route is exposed | No Captain button for initial Operator-only rollout. |
| Docs/OpenAPI | `docs/arclink/*.md`, `docs/openapi/arclink-v1.openapi.json` | Migration runbooks and route contract | Update only after behavior exists or when a route contract changes. |

## Version Snapshot

| Lane | Public signal | Planning note |
| --- | --- | --- |
| Python | Dev requirements and runtime code target modern Python; compatibility should remain Python 3.11+ | New Wave 3 code should stay Python 3.11 compatible. |
| Node/web | Web uses Next.js 15, React 19, TypeScript 5, ESLint, Node tests, and Playwright | Wave 3 does not require web changes unless adding a disabled Captain route/button. |
| qmd/Hermes | qmd and Hermes are pinned runtime components | Migration must preserve qmd/memory/Hermes home state, not modify core runtime. |
| Compose images | Compose defines app, API, web, qmd, Nextcloud, Postgres, Redis, and related services | Migration applies existing rendered services, not new infrastructure. |

## Alternatives Compared

| Decision area | Preferred path | Alternatives | Reason |
| --- | --- | --- | --- |
| Orchestration | Dedicated Python migration module | Shell runbook or sovereign worker-only implementation | Keeps DB state, file manifests, rollback, and idempotency testable. |
| State transfer | Standard-library traversal/copy in local tests plus executor-compatible live boundary | Direct unstructured `rsync` calls embedded through business logic | Injection keeps no-secret BUILD deterministic and avoids leaking credentials through command surfaces. |
| Idempotency | Existing operation idempotency helpers plus migration row replay | Action-intent-only replay | Migration has multiple sub-operations and needs durable replay independent of queue retries. |
| Placement update | Control-plane placement rows with atomic source/target status transitions | Trust Compose target alone | Placement is the fleet source of truth and must rollback safely. |
| Verification | Injectable verifier mirroring sovereign worker health expectations | Always run live health checks | Local tests can prove rollback paths without live infrastructure. |
| GC | Migration helper with optional job-loop/service wrapper later | Manual cleanup docs only | Steering requires tested garbage collection after retention. |

## External Integration Posture

| Integration | Local BUILD posture | Live posture |
| --- | --- | --- |
| SQLite control DB | Temporary DBs and schema tests | No private runtime DB reads. |
| Filesystem state | Temporary test trees for representative vault, memory, sessions, configs, Hermes home, and secret-reference boundaries | No private state or user home reads. |
| Docker/Compose | Fake executor and command shims | Host/container mutation blocked. |
| SSH/rsync | Fake transport or executor-compatible seam | Live host transfer blocked unless explicitly authorized. |
| Cloudflare/Tailscale DNS | Existing fake DNS/executor paths and DB row assertions | Live DNS/network mutation blocked. |
| Telegram/Discord bot env | Secret refs and redacted metadata only | No public bot mutation or token reads. |
| Hetzner/Linode | Inventory provider tests remain fake/no-token | Live list/provision/delete/probe blocked. |

## Dependency Risks

- No new heavy transfer dependency is needed for the local proof; standard
  library file traversal plus existing executor seams is enough.
- File digest manifests must remain bounded and secret-free while proving
  integrity.
- Target materialization must reuse provisioning rendering rather than forking
  deployment config generation.
- GC must be conservative and only act on succeeded migrations past retention.
- Docs and OpenAPI must not promise Captain self-service while the default flag
  keeps migration disabled.

## Validation Dependencies

Minimum Wave 3 validation after BUILD hardening:

```bash
git diff --check
python3 -m py_compile python/arclink_pod_migration.py python/arclink_action_worker.py python/arclink_dashboard.py python/arclink_api_auth.py python/arclink_hosted_api.py python/arclink_sovereign_worker.py python/arclink_executor.py
python3 tests/test_arclink_pod_migration.py
python3 tests/test_arclink_action_worker.py
python3 tests/test_arclink_admin_actions.py
python3 tests/test_arclink_sovereign_worker.py
python3 tests/test_arclink_executor.py
python3 tests/test_arclink_schema.py
```

If shell or Compose files change:

```bash
bash -n deploy.sh bin/*.sh test.sh
```
