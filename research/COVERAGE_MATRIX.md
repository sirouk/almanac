# Coverage Matrix

## Goal Coverage

| Goal / criterion | Planning coverage | BUILD proof required |
| --- | --- | --- |
| Use ArcPod Captain Console steering as active backlog | `IMPLEMENTATION_PLAN.md`, this matrix, and research summary name `research/RALPHIE_ARCPOD_CAPTAIN_CONSOLE_STEERING.md` as authority | BUILD should update from source truth and not rely on older Sovereign audit plan state. |
| Start with Wave 0 and Wave 1 | Plan tasks begin with vocabulary/schema/SOUL, then onboarding Agent Name and Agent Title | Focused schema, onboarding, public bot, provisioning, API/auth, and web tests. |
| Apply vocabulary canon | Wave 0 maps Captain/Crew/ArcPod/Pod/Raven/Operator surfaces | Docs and user-facing copy checks prove Captain-facing terms changed while operator/backend terms stayed technical. |
| Add schema foundations | Wave 0 lists user/deployment/session columns and new inventory, comms, migration, recipes, and Wrapped tables | `ensure_schema` migration tests plus drift/status validation. |
| Fix onboarding identity | Wave 1 covers web, Telegram, Discord, Stripe metadata, provisioning, dashboard rename/retitle | Required inputs, persisted resume state, metadata propagation, deployment identity rows, bot commands, and audit tests. |
| Add control inventory and ASU placement | Wave 2 covers deploy menu, provider modules, manual registration, ASU, placement strategy, dashboard; candidate implementation is present in the dirty tree | Fake-provider tests, ASU unit tests, deploy regression tests, fleet placement tests, and shell syntax checks. |
| Wire real 1:1 Pod migration | Wave 3 covers migration capture, target apply, health verify, rollback, idempotency, and `reprovision` wiring | New migration tests plus worker/executor/provisioning/fleet tests. |
| Add Pod comms and Comms Console | Wave 4 covers DB broker, MCP tools, share grants, rate limit, Captain and Operator views | Pod comms, MCP, hosted API/auth, dashboard, and web tests. |
| Add Crew Training | Wave 5 covers questionnaire, provider/fallback recipe generation, active recipe row, additive SOUL overlay | Crew recipe tests, unsafe-output tests, public bot/web flow, provisioning/managed-context tests. |
| Add ArcLink Wrapped | Wave 6 covers scheduler, reports, novelty stats, delivery outbox, dashboard history, frequency settings | Wrapped, notification, dashboard, hosted API, and web tests. |
| Respect constraints | Build gate records no private-state, no Hermes core, no live deploy/provider/payment/bot mutation without authorization | Diff review and completion notes list skipped live gates. |
| Compare implementation paths | Research summary, dependency research, stack snapshot, and implementation plan compare alternatives | Update notes if BUILD changes path. |

## Wave Coverage

| Wave | Required behavior | Primary files | Required focused tests |
| --- | --- | --- | --- |
| 0 | Canonical vocabulary doc, docs copy pass, schema columns/tables, drift checks, additive SOUL template vars | `AGENTS.md`, `docs/arclink/*.md`, `python/arclink_control.py`, `templates/SOUL.md.tmpl` | `tests/test_arclink_schema.py`, `tests/test_arclink_control_db.py`, provisioning/public bot/docs tests as added. |
| 1 | Agent Name and Agent Title captured on web/bots, propagated through onboarding and provisioning, mutable after onboarding | `web/src/app/onboarding/page.tsx`, API client, `python/arclink_onboarding.py`, `python/arclink_public_bots.py`, `python/arclink_discord.py`, `python/arclink_public_bot_commands.py`, `python/arclink_api_auth.py`, `python/arclink_hosted_api.py` | `tests/test_arclink_onboarding.py`, `tests/test_arclink_public_bots.py`, `tests/test_arclink_hosted_api.py`, `tests/test_arclink_api_auth.py`, `tests/test_arclink_provisioning.py`, `tests/test_arclink_telegram.py`, `tests/test_arclink_discord.py`, `web` tests. |
| 2 | Inventory submenu, manual/Hetzner/Linode registration, probes, ASU, fair placement, dashboard inventory | `bin/deploy.sh`, `python/arclink_fleet.py`, `python/arclink_inventory.py`, `python/arclink_asu.py`, provider modules, dashboard modules | `tests/test_arclink_fleet.py`, ASU/provider tests, `tests/test_deploy_regressions.py`, shell syntax. |
| 3 | Idempotent Pod migration with capture/restore/verify/rollback and real `reprovision` action | new `python/arclink_pod_migration.py`, worker, executor, provisioning, fleet | new migration tests, `tests/test_arclink_action_worker.py`, `tests/test_arclink_sovereign_worker.py`, `tests/test_arclink_executor.py`. |
| 4 | Pod comms broker, MCP tools, share-grant gated cross-Captain messages, Comms Console | new `python/arclink_pod_comms.py`, `python/arclink_mcp_server.py`, auth/hosted API, web dashboard/admin | new pod comms tests, MCP tests, API/auth/dashboard tests, web tests. |
| 5 | Crew Training questionnaire, active Crew Recipe, additive SOUL overlay, no memory/session rewrites | new recipe module, `templates/CREW_RECIPE.md.tmpl`, `templates/SOUL.md.tmpl`, public bots, hosted API, dashboard | new crew recipe tests, provisioning/API/auth/public bot tests, web tests. |
| 6 | Wrapped report generation, scheduler, five non-standard stats, delivery via notification outbox, dashboard history | new `python/arclink_wrapped.py`, notification delivery, Compose/job wrapper, hosted API, dashboard/admin | new Wrapped tests, notification/dashboard/API/web tests. |

## Required Artifact Coverage

| Required artifact | Status |
| --- | --- |
| `research/RESEARCH_SUMMARY.md` | Updated with confidence, active ArcPod backlog, repository findings, path comparison, assumptions, risks, and verdict. |
| `research/CODEBASE_MAP.md` | Maps directories, entrypoints, runtime lanes, wave hotspots, tests, and architecture assumptions. |
| `research/DEPENDENCY_RESEARCH.md` | Documents stack components, pins, alternatives, integration posture, risks, and validation dependencies. |
| `research/COVERAGE_MATRIX.md` | Maps goals, waves, artifacts, validation, and completion rules against the ArcPod mission. |
| `research/STACK_SNAPSHOT.md` | Provides ranked stack hypotheses, deterministic confidence score, and alternatives. |
| `IMPLEMENTATION_PLAN.md` | Replaced the prior Sovereign audit plan with the ArcPod Captain Console wave plan. |
| `consensus/build_gate.md` | Updated to allow no-secret BUILD for the ArcPod mission and list blocked live/private operations. |

## Completion Rules

BUILD can claim a wave complete only when every in-scope item is repaired
locally with focused tests or explicitly deferred with:

- wave and checklist item;
- risk if left unresolved;
- current fail-closed or disabled behavior;
- exact operator action or policy decision needed;
- focused tests preserving the interim boundary.

Do not claim terminal completion while any ArcPod Captain Console wave item is
unresolved or lacks a project-specific deferral.
