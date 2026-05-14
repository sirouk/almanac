# Research Summary

<confidence>92</confidence>

## Scope

This PLAN pass inspected the public ArcLink repository structure, current
planning artifacts, the Wave 5 Crew Training section of the ArcPod Captain
Console steering document, schema foundations, provider/safety rails,
managed-context identity projection, hosted API patterns, public bot command
handling, dashboard code, focused tests, docs, and OpenAPI location.

No private state, live secrets, user Hermes homes, deploy keys, production
services, payment/provider mutations, live bot command registration, live
Chutes inference, live deploys, or Hermes core were inspected or mutated.

## Active Mission

The active BUILD backlog is Wave 5 only: Crew Training.

The user-provided Project Goals Document supersedes the bootstrap objective
that references the older Sovereign audit backlog. The older audit document is
background only for this run. Waves 0-4 are treated as landed and should not be
re-touched unless a direct regression blocks Crew Training.

Authoritative Wave 5 detail lives in:

`research/RALPHIE_ARCPOD_CAPTAIN_CONSOLE_STEERING.md`

## Current Findings

| Area | Finding |
| --- | --- |
| Schema foundation | `arclink_crew_recipes` exists with active/archive statuses and a unique active recipe index per Captain. `arclink_users` already has `captain_role`, `captain_mission`, and `captain_treatment`. |
| SOUL template | `templates/SOUL.md.tmpl` already has additive Crew Recipe placeholders for preset, capacity, Captain role, mission, treatment, and Agent title. |
| Wave 4 state | Pod-to-Pod Comms is present in source and tests. It is not part of this BUILD scope except as an existing adjacent surface. |
| Wave 5 missing behavior | `python/arclink_crew_recipes.py`, `templates/CREW_RECIPE.md.tmpl`, Crew Training API routes, dashboard questionnaire, public bot `/train-crew` and `/whats-changed`, and `tests/test_arclink_crew_recipes.py` are absent. |
| Provider boundary | Chutes boundary and fake inference client patterns exist. Crew Training should use injectable generation and deterministic fallback; live Chutes is not required for BUILD. |
| Safety boundary | `arclink_memory_synthesizer` defines unsafe-output patterns and `_card_has_unsafe_output`. Crew Training should reuse or extract that boundary for URLs, shell commands, and jailbreak patterns. |
| Identity projection | `python/arclink_provisioning.py` writes `state/arclink-identity-context.json` for existing Hermes homes. Crew Training should extend this projection with additive recipe overlay fields and never touch memories or sessions. |
| API/web pattern | `python/arclink_hosted_api.py` uses explicit `_handle_*` functions, `_ROUTES`, `_JSON_OBJECT_ROUTES`, CSRF checks for mutations, and generated OpenAPI. `web/src/lib/api.ts` centralizes API helpers. |
| Public bot pattern | `python/arclink_public_bots.py` keeps command handling local and testable without live Telegram or Discord mutation. `/train-crew` should use the same pure handler style. |

## Implementation Path Comparison

| Decision | Path A | Path B | Selected path |
| --- | --- | --- | --- |
| Crew Recipe core | Dedicated `python/arclink_crew_recipes.py` with preview, regenerate, confirm/apply, archive, diff, and injectable generation | Generate recipes directly in hosted API, web, and bot handlers | Path A. It centralizes lifecycle, unsafe-output rejection, fallback, audit, and tests. |
| Provider use | Use Chutes through an injectable boundary and deterministic preset-only fallback | Require live Chutes credentials for all Crew Training runs | Path A. BUILD must pass without live credentials, and the UI must truthfully label fallback mode. |
| Unsafe output handling | Reuse or extract the memory-synth unsafe-output patterns | Trust model output after parsing | Path A. The steering requires rejection of URLs, shell commands, and jailbreak text before SOUL overlay. |
| SOUL application | Additive overlay through identity-context projection and managed-context refresh | Rewrite memory, sessions, Hermes core prompts, or gateway process state | Path A. Crew Training is persona overlay only and must not restart Hermes. |
| Web shape | Add a focused Crew Training questionnaire route or dashboard panel using current API helper patterns | Refactor the dashboard architecture first | Path A. The dashboard is monolithic today; BUILD should keep the addition scoped. |
| Bot state | Store questionnaire progress in existing public bot onboarding/session metadata until confirmed | Add a new live bot service or mutate command registration | Path A. Local handler tests can prove the flow without external bot mutation. |

## Build Assumptions

- Current source is ground truth where historical planning docs disagree.
- Wave 5 does not need new schema unless implementation discovers a concrete
  deliverable that cannot fit the existing tables and columns.
- The active recipe row is the durable source of truth; identity-context files
  are projections for managed-context injection.
- Deterministic fallback output must be useful and visibly labeled as fallback
  or dry-run mode.
- Operator-on-behalf application is allowed only through an audited admin path.
- Captain-facing copy uses ArcPod, Pod, Agent, Captain, Crew, Raven, and Crew
  Training. Backend/internal code can keep user/deployment naming.

## Risks

- Accidentally planning or implementing Wave 6 would violate this run's scope.
- Recipe generation must not leak or require Chutes secret material; tests
  should use fake clients and secret references only.
- Unsafe model output must be rejected before it can become a SOUL overlay.
- Identity-context writes must preserve unrelated existing keys and must not
  write to memory/session locations.
- Web and bot flows need truthful fallback copy so Captains do not mistake
  deterministic fallback for live provider output.
- Public bot tests should avoid live command registration and external
  delivery.

## Verdict

PLAN is ready for Wave 5 BUILD handoff after the required artifacts in this
pass are updated. No blocker requires `consensus/build_gate.md` to stop BUILD,
but the gate is narrowed to Wave 5 and explicitly keeps private/live actions
blocked.
