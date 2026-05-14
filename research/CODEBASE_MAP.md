# Codebase Map

## Scope

This map covers public repository areas relevant to Wave 5 Crew Training. It
excludes private state, live credentials, user Hermes homes, dependency
folders, caches, logs, production service state, and Hermes core.

## Planning Entrypoints

| Path | Role |
| --- | --- |
| `IMPLEMENTATION_PLAN.md` | BUILD handoff plan for Wave 5 only. |
| `research/RALPHIE_ARCPOD_CAPTAIN_CONSOLE_STEERING.md` | Authoritative Wave 5 behavior spec. |
| `docs/arclink/vocabulary.md` | Captain/operator vocabulary boundary. |
| `research/RESEARCH_SUMMARY.md` | Current PLAN findings and assumptions. |
| `research/COVERAGE_MATRIX.md` | Goal-to-proof matrix for Wave 5. |
| `research/STACK_SNAPSHOT.md` | Deterministic stack hypothesis and alternatives. |
| `consensus/build_gate.md` | No-secret Wave 5 build consent and blocked live/private flows. |

## Directory Map

| Directory | Responsibility |
| --- | --- |
| `python/` | Control DB, hosted API, auth/session/CSRF, dashboard snapshots, public bots, Chutes boundary, memory synthesis safety, provisioning projection, and the new Crew Recipe module. |
| `tests/` | Focused Python regressions for recipe lifecycle, API/auth, provisioning projection, public bot flow, dashboard data, and schema drift. |
| `web/` | Next.js Captain dashboard and Operator/admin dashboard. Crew Training should be added using existing API helper and page patterns. |
| `templates/` | `SOUL.md.tmpl` contains existing additive placeholders; `CREW_RECIPE.md.tmpl` must be added. |
| `docs/arclink/` | Operations and control-node production runbooks. Add Crew Training sections after behavior is true. |
| `docs/openapi/` | API contract. Add Crew Training routes after hosted API behavior exists. |
| `research/` | Planning, steering, and completion artifacts. |
| `consensus/` | Build gate records and blocked-flow notes. |

## Existing Architecture Rails

| Rail | Files / patterns |
| --- | --- |
| Schema, constants, drift checks | `python/arclink_control.py`, `tests/test_arclink_schema.py` |
| User and deployment projection | `python/arclink_provisioning.py` |
| Audit and events | `append_arclink_audit`, `append_arclink_event` in `python/arclink_control.py` |
| Hosted API routing | `_handle_*`, `_ROUTES`, `_JSON_OBJECT_ROUTES`, and OpenAPI generation in `python/arclink_hosted_api.py` |
| Auth, sessions, CSRF | `python/arclink_api_auth.py` |
| Captain dashboard API snapshots | `python/arclink_dashboard.py`, `read_user_dashboard_api` |
| Public bot command handling | `python/arclink_public_bots.py`, `python/arclink_public_bot_commands.py` |
| Chutes boundary and fakes | `python/arclink_chutes.py`, `python/arclink_chutes_live.py` |
| Unsafe generated-output rejection | `UNSAFE_OUTPUT_PATTERNS` and `_card_has_unsafe_output` in `python/arclink_memory_synthesizer.py` |
| Secret redaction | `python/arclink_secrets_regex.py`, `python/arclink_evidence.py` |
| Managed-context injection | `plugins/hermes-agent/arclink-managed-context/`, identity state file loading |
| Web API helpers | `web/src/lib/api.ts` |
| Dashboard UI | `web/src/app/dashboard/page.tsx`, `web/src/app/admin/page.tsx` |

## Wave 5 Source Surfaces

| Surface | Current state | BUILD target |
| --- | --- | --- |
| Recipe module | Missing | Add `python/arclink_crew_recipes.py` for validate, preview, regenerate, confirm/apply, archive, list current/prior, diff, and audit. |
| Prompt template | Missing | Add `templates/CREW_RECIPE.md.tmpl` with role, mission, treatment, preset, capacity, Pod count, and Agent identity inputs. |
| Schema | Present | Reuse `arclink_crew_recipes` and Captain fields. Add no columns unless a deliverable genuinely requires one with tests. |
| Active/archive lifecycle | Schema-ready only | One active recipe per Captain; confirming archives the previous active row and writes the new active row. |
| Unsafe-output boundary | Present in memory synthesis | Reuse or extract a shared helper to reject URLs, shell commands, and jailbreak patterns; retry twice before fallback. |
| Provider boundary | Chutes boundary and fake inference exist | Generate through an injectable Chutes-style client when allowed; otherwise deterministic preset-only fallback. |
| SOUL overlay | Template placeholders present | Apply recipe fields to every Pod in the Captain's Crew through identity-context projection while preserving existing state keys. |
| Hosted API | Crew Training routes missing | Add user preview/regenerate/confirm/current/diff routes and optional audited admin-on-behalf route. |
| Web dashboard | No Crew Training questionnaire | Add Captain Crew Training questionnaire/review/regenerate/confirm UI and admin-on-behalf entry only if scoped and audited. |
| Public bot | `/train-crew` and `/whats-changed` missing | Add pure handler flow that stores questionnaire state, shows review, confirms recipe, and reports current vs prior recipe. |
| Docs/OpenAPI | Crew Training routes not documented | Update after behavior and tests are true. |

## Architecture Assumptions

- Do not modify Hermes core; use ArcLink wrappers, plugins, generated config,
  service units, and identity-context overlays.
- Keep Crew Training as an additive SOUL overlay. Memories and sessions are
  never rewritten.
- Keep provider access behind existing Chutes and secret-reference boundaries.
- Keep BUILD local and no-secret: fake clients, temporary DBs, temporary
  identity-context fixtures, and no live bot/provider/payment/deploy actions.
- Prefer one tested Python service module over duplicating business logic in
  web, bot, and hosted API handlers.
