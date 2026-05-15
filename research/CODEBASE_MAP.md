# Codebase Map

## Scope

This map covers the public repository areas relevant to the audit verification
gate, Wave 6 ArcLink Wrapped, and the Mission Closeout sweep. It excludes
private state, live credentials, dependency folders, logs, generated browser
artifacts, production service state, and Hermes core.

## Planning Entrypoints

| Path | Role |
| --- | --- |
| `IMPLEMENTATION_PLAN.md` | BUILD handoff plan for audit-gate verification, Wave 6, and closeout. |
| `research/RALPHIE_ARCPOD_CAPTAIN_CONSOLE_STEERING.md` | Product steering for Waves 0-6; Wave 6 section is the Wrapped feature reference. |
| `research/RALPHIE_SOVEREIGN_AUDIT_VERIFICATION_20260511.md` | Historical audit verification and Wave 1 trust-boundary checklist; use as a regression gate, not as proof of current gaps. |
| `research/BUILD_COMPLETION_NOTES.md` | Prior wave and audit-closure validation record; must receive final six-wave completion notes after BUILD. |
| `docs/arclink/vocabulary.md` | Captain/operator vocabulary boundary for all user-facing closeout sweeps. |
| `docs/API_REFERENCE.md` and `docs/openapi/arclink-v1.openapi.json` | Hosted API contract to update after Wrapped behavior lands. |

## Directory Map

| Directory | Responsibility |
| --- | --- |
| `python/` | Control DB, hosted API, auth/session/CSRF, dashboard read models, public bots, notification delivery, provisioning, inventory, migration, Comms, Crew Training, and the new Wrapped module. |
| `bin/` | Canonical deploy/control scripts and Docker job-loop runners. Wrapped scheduler should add a small runner here if needed. |
| `compose.yaml` | Shared Host Docker and Sovereign validation services. Wrapped should use a named job-loop service with no Docker socket. |
| `tests/` | Focused Python regressions for security gates, Wrapped generation, cadence, delivery, API/auth, bots, dashboard snapshots, docs/OpenAPI parity, and closeout surfaces. |
| `web/` | Next.js Captain dashboard and Operator dashboard. Wrapped needs API helpers, Captain tab/history, frequency control, and Operator aggregate-only panel. |
| `docs/` | Canonical docs, API reference, OpenAPI spec, architecture and status maps. Closeout reconciles these after behavior is true. |
| `research/` | Planning, steering, audit, and completion artifacts. |
| `consensus/` | Build gate records for no-secret BUILD boundaries and blocked live/private flows. |

## Existing Architecture Rails

| Rail | Files / patterns |
| --- | --- |
| Schema and drift checks | `python/arclink_control.py`, `tests/test_arclink_schema.py` |
| Audit/events | `append_arclink_audit`, `append_arclink_event` in `python/arclink_control.py` |
| Hosted API routing | `_handle_*`, route tables, body caps, CORS, CIDR gate, and OpenAPI metadata in `python/arclink_hosted_api.py` |
| Auth and sessions | `python/arclink_api_auth.py`; HMAC session/CSRF hashes and CSRF-gated mutations |
| Dashboard read models | `python/arclink_dashboard.py` |
| Public bots | `python/arclink_public_bots.py`, `python/arclink_public_bot_commands.py`, `python/arclink_telegram.py`, `python/arclink_discord.py` |
| Notification delivery | `notification_outbox` helpers in `python/arclink_control.py` and worker in `python/arclink_notification_delivery.py` |
| Secret redaction | `python/arclink_evidence.py`, `python/arclink_secrets_regex.py` |
| Docker scheduling | `bin/docker-job-loop.sh`, existing job services in `compose.yaml` |
| Memory synthesis | `python/arclink_memory_synthesizer.py`, `memory_synthesis_cards` table |
| Pod Comms | `python/arclink_pod_comms.py`, `/user/comms`, `/admin/comms`, MCP Comms tools |
| Crew Training | `python/arclink_crew_recipes.py`, `/user/crew-recipe`, dashboard Crew tab, public bot `/train-crew` |

## Wave 0-5 Current Source State

| Surface | Current source signal |
| --- | --- |
| Vocabulary | `docs/arclink/vocabulary.md` exists and names ArcPod, Pod, Captain, Crew, Raven, Comms, Crew Training, and ArcLink Wrapped. |
| Onboarding identity | Web, public bots, schema, Stripe metadata, dashboard rename/retitle, and identity projection include Agent Name and Agent Title. |
| Inventory/ASU | Inventory modules for manual/Hetzner/Linode and ASU tests exist; `deploy.sh control inventory` is referenced by regressions. |
| Pod migration | `python/arclink_pod_migration.py` and tests exist. |
| Pod Comms | `python/arclink_pod_comms.py`, dashboard/admin Comms panels, OpenAPI, and tests exist. |
| Crew Training | `python/arclink_crew_recipes.py`, template, API/auth routes, dashboard Crew tab, public bot commands, OpenAPI, and tests exist. |

## Wave 6 Source Surfaces

| Surface | Current state | BUILD target |
| --- | --- | --- |
| Wrapped module | Present core | `python/arclink_wrapped.py` now owns report generation, scoring, rendering, persistence, cadence helpers, delivery enqueue, scheduler, and operator aggregate helpers. |
| Wrapped schema | Present | Reuse `arclink_wrapped_reports` and `arclink_users.wrapped_frequency`; add columns only if a required deliverable cannot fit existing schema. |
| Data collectors | Present core | Scoped collectors cover events, audit, same-Captain Comms, memory cards, injected read-only session counts, and injected vault-reconciler deltas. |
| Novelty score | Present | `wrapped_novelty_v1` is documented and reports expose at least five non-standard stats. |
| Redaction | Existing helpers | Redact all rendered text and ledger snippets before storage, dashboard display, or notification enqueue. |
| Cadence | Present core | Helper validates and audits `daily`, `weekly`, `monthly`; hourly/cron/arbitrary intervals are rejected. |
| Scheduler | Present Docker/core | Named `arclink-wrapped` job-loop service and `bin/arclink-wrapped.sh` runner are wired without Docker socket access. |
| Delivery | Present core | Queues `notification_outbox` with `target_kind='captain-wrapped'`, resolves Captain channel, delays through supported quiet-hours windows, retries failed reports, and emits aggregate operator failure notifications. |
| Hosted API | Missing | Add user history/frequency routes and admin aggregate routes with existing auth/CSRF/CIDR patterns. |
| Public bot | Missing | Add `/wrapped-frequency daily|weekly|monthly` and optional `/wrapped` status/history summary without live command mutation. |
| Web dashboard | Missing | Add Captain "Wrapped" tab with history and frequency selector; add Operator aggregate-only status panel. |
| Docs/OpenAPI | Missing | Reconcile docs and generated/spec OpenAPI after behavior lands. |

## Architecture Assumptions

- ArcLink Wrapped is read-only over Captain state except for inserting/updating
  Wrapped report rows and notification/audit/status rows.
- It must never read arbitrary user homes or private state. Tests should use
  temporary state roots and injected scanner functions.
- It must not modify Hermes core, sessions, memories, vault content, provider
  accounts, payments, or deployment state.
- Operator/admin surfaces may expose only aggregate Wrapped status, score,
  cadence, timestamps, and error state.
- Captain-facing narrative and dashboard copy follow the vocabulary canon.
- Scheduler work should reuse `docker-job-loop.sh` rather than adding a new
  scheduler dependency.
