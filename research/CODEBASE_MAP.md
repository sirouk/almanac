# Codebase Map

## Scope

This map covers public repository areas relevant to ArcPod Captain Console
Waves 4-6. It excludes private state, live credentials, user Hermes homes,
dependency folders, caches, logs, production service state, and Hermes core.

## Planning Entrypoints

| Path | Role |
| --- | --- |
| `IMPLEMENTATION_PLAN.md` | BUILD handoff plan for Waves 4-6 only. |
| `research/RALPHIE_ARCPOD_CAPTAIN_CONSOLE_STEERING.md` | Authoritative Wave 4, Wave 5, and Wave 6 behavior spec. |
| `docs/arclink/vocabulary.md` | Captain/operator vocabulary boundary. |
| `research/RESEARCH_SUMMARY.md` | Current PLAN summary and assumptions. |
| `research/COVERAGE_MATRIX.md` | Goal-to-proof matrix for BUILD validation. |
| `research/STACK_SNAPSHOT.md` | Deterministic stack hypothesis and alternatives. |
| `consensus/build_gate.md` | No-secret build consent and blocked live/private flows. |

## Runtime Directories

| Directory | Responsibility for Waves 4-6 |
| --- | --- |
| `python/` | Control DB, hosted API, auth/session/CSRF, dashboard snapshots, MCP server, public bots, notifications, Chutes boundary, memory synthesis safety, evidence redaction, and new Wave modules. |
| `tests/` | Focused Python regressions. New tests should cover pod comms, crew recipes, and wrapped. |
| `web/` | Next.js Captain dashboard and Operator/admin dashboard. Add Comms, Crew Training, and Wrapped tabs/routes using existing API helper patterns. |
| `bin/` | Canonical wrappers and job loops. Wave 6 scheduler should reuse `docker-job-loop.sh` or a nearby job wrapper pattern. |
| `compose.yaml` | Docker service topology. Wave 6 likely adds an `arclink-wrapped` job service. |
| `templates/` | `SOUL.md.tmpl` already has additive Crew Recipe placeholders; add `CREW_RECIPE.md.tmpl`. |
| `docs/arclink/` | Operations and production runbooks; add Comms, Crew Training, and Wrapped sections after behavior is true. |
| `docs/openapi/` | API contract. Add user/admin comms, Crew Training, and Wrapped/frequency routes as implemented. |
| `research/` | Planning and completion artifacts. |
| `consensus/` | Build gate records. |

## Existing Architecture Rails

| Rail | Files / patterns |
| --- | --- |
| Schema, constants, drift checks | `python/arclink_control.py`, `tests/test_arclink_schema.py` |
| Rate limiting | `check_arclink_rate_limit` in API/auth/control paths |
| Audit and events | `append_arclink_audit`, `append_arclink_event` |
| Notification outbox | `queue_notification`, `notification_outbox`, `python/arclink_notification_delivery.py` |
| Share grants | `python/arclink_api_auth.py`, `shares.request` in `python/arclink_mcp_server.py` |
| MCP tool registration | `TOOLS`, `TOOL_SCHEMAS`, and dispatch handlers in `python/arclink_mcp_server.py` |
| Hosted API | `_handle_*` functions, `ROUTES`, and generated OpenAPI in `python/arclink_hosted_api.py` |
| Captain dashboard | `web/src/app/dashboard/page.tsx`, `web/src/lib/api.ts` |
| Admin dashboard | `web/src/app/admin/page.tsx`, admin read handlers |
| Public bot commands | `python/arclink_public_bots.py`, `python/arclink_public_bot_commands.py`, Telegram/Discord adapters |
| Chutes boundary | `python/arclink_chutes.py` fake/live-safe boundary objects |
| Unsafe generated output rejection | `python/arclink_memory_synthesizer.py` unsafe-output patterns |
| Redaction | `python/arclink_evidence.py::redact_value`, `python/arclink_secrets_regex.py` |
| Managed SOUL overlay | `templates/SOUL.md.tmpl`, identity context writes in provisioning/org-profile paths |

## Wave 4 Source Surfaces

| Surface | Current state | BUILD target |
| --- | --- | --- |
| Pod comms broker | Schema exists; module absent | Add `python/arclink_pod_comms.py` with send/list/redact/deliver helpers. |
| Share grant kind | `drive` and `code` only | Add `pod_comms` for active cross-Captain comms grants. |
| MCP tools | No `pod_comms.*` tools | Add `pod_comms.list`, `pod_comms.send`, and `pod_comms.share-file`. |
| API routes | No `/user/comms` or `/admin/comms` | Add Captain-scoped and CIDR/admin-scoped read APIs. |
| UI | No Comms tab | Add read-only Comms tab to Captain and Operator dashboards. |
| Tests | New file absent | Add `tests/test_arclink_pod_comms.py` plus MCP/API/dashboard coverage. |

## Wave 5 Source Surfaces

| Surface | Current state | BUILD target |
| --- | --- | --- |
| Recipe module | Absent | Add `python/arclink_crew_recipes.py` for generate/preview/apply/archive/diff. |
| Prompt template | Absent | Add `templates/CREW_RECIPE.md.tmpl`. |
| SOUL overlay | Placeholders present | Write additive overlay through identity-context refresh path without touching memory/sessions. |
| Public bots | Agent identity commands exist; Crew Training commands absent | Add `/train-crew` and `/whats-changed` flow without live command registration. |
| Web | Dashboard exists; no questionnaire | Add `/train-crew` or dashboard questionnaire path using existing API helper. |
| Tests | New file absent | Add `tests/test_arclink_crew_recipes.py` and adjacent API/bot tests. |

## Wave 6 Source Surfaces

| Surface | Current state | BUILD target |
| --- | --- | --- |
| Wrapped module | Absent | Add `python/arclink_wrapped.py` with deterministic report generation and redaction. |
| Frequency preference | Schema exists | Add API/dashboard/bot update flows; reject anything more frequent than daily. |
| Scheduler | Job-loop pattern exists; Wrapped job absent | Add service or job-loop integration with daily/weekly/monthly gating. |
| Delivery | Notification outbox exists | Queue `target_kind='captain-wrapped'`, respecting quiet hours where available. |
| UI | No Wrapped tab | Add Captain history tab and Operator aggregate-only status view. |
| Docs | Wrapped doc absent | Add formula and operational docs after behavior exists. |
| Tests | New file absent | Add `tests/test_arclink_wrapped.py` and notification/API/dashboard coverage. |

## Architecture Assumptions

- Do not modify Hermes core; use ArcLink wrappers, plugins, hooks, generated
  config, service units, and identity-context overlays.
- Keep Shared Host, Shared Host Docker, and Sovereign Control Node concepts
  distinct. Waves 4-6 target the paid Control Node/Captain Console surface.
- Use relative paths and sanitized identifiers in markdown artifacts.
- Store secret references and derived statistics, not secret values.
- Prefer small Python modules with injectable dependencies over embedding
  business logic directly in web, bot, or MCP handlers.
