# Research Summary

<confidence>91</confidence>

## Scope

This PLAN pass inspected the public ArcLink repository structure, current
planning artifacts, ArcPod Captain Console steering sections for Waves 4-6,
schema foundations, API/dashboard/MCP patterns, tests, runbooks, Compose job
loops, and vocabulary canon.

No private state, live secrets, user Hermes homes, deploy keys, production
services, provider accounts, payment flows, public bot command registration, or
Hermes core were inspected or mutated.

## Active Mission

The active BUILD backlog is now Waves 4-6 from:

`research/RALPHIE_ARCPOD_CAPTAIN_CONSOLE_STEERING.md`

The user-provided goals document supersedes the bootstrap line about restarting
the older Sovereign audit backlog. `research/RALPHIE_SOVEREIGN_AUDIT_VERIFICATION_20260511.md`
is historical/background only for this mission. Waves 0-3 are treated as landed
and should not be re-touched unless a direct regression blocks Waves 4-6.

## Current Findings

| Area | Finding |
| --- | --- |
| Schema foundations | `arclink_pod_messages`, `arclink_crew_recipes`, `arclink_wrapped_reports`, `arclink_users.wrapped_frequency`, Captain role/mission/treatment columns, SOUL overlay placeholders, status constants, indexes, and drift checks are already present. |
| Wave 4 behavior | `python/arclink_pod_comms.py`, MCP `pod_comms.*` tools, user/admin comms API routes, Comms dashboard tabs, and `tests/test_arclink_pod_comms.py` are absent. Share grants currently allow only `drive` and `code`; `pod_comms` is not allowed. |
| Wave 5 behavior | `python/arclink_crew_recipes.py`, `templates/CREW_RECIPE.md.tmpl`, web `/train-crew`, dashboard Crew Training UI, public bot `/train-crew` and `/whats-changed`, and `tests/test_arclink_crew_recipes.py` are absent. The SOUL template has additive placeholders ready. |
| Wave 6 behavior | `python/arclink_wrapped.py`, Wrapped scheduler/job wrapper, dashboard history tab, frequency update route/command, Wrapped docs, and `tests/test_arclink_wrapped.py` are absent. Compose already has reusable `docker-job-loop.sh` patterns. |
| Existing rails | Rate limits, audit/events, notification outbox, share grants, MCP tool registration, hosted API auth, CIDR-gated admin routes, Chutes boundary models/fakes, memory-synth unsafe-output rejection, and evidence redaction already exist and should be reused. |
| Web stack | Next.js/React dashboard and admin pages are monolithic page components with local tab state and API helper calls in `web/src/lib/api.ts`. New tabs should follow that pattern before any frontend refactor. |

## Implementation Path Comparison

| Decision | Path A | Path B | Decision |
| --- | --- | --- | --- |
| Wave 4 comms broker | Dedicated `python/arclink_pod_comms.py` with DB, rate-limit, share-grant, audit, and notification helpers | Inline comms SQL in MCP/API handlers | Choose Path A. It keeps trust-boundary and tests centralized. |
| Wave 4 attachments | Reuse share-grant projection metadata and store only references in `attachments_json` | Copy raw file contents or paths into message rows | Choose share-grant projection only. Raw file transfer violates the stated boundary. |
| Wave 5 recipe generation | Dedicated `python/arclink_crew_recipes.py` with injectable/fake Chutes client and deterministic fallback | Web/bot handlers generate overlays directly | Choose dedicated module. It centralizes unsafe-output rejection and archive/activate semantics. |
| Wave 5 overlay write | Store recipe row and identity-context overlay for next managed-context refresh | Rewrite memory, sessions, or Hermes core prompts | Choose additive overlay only. Memory/session mutation is explicitly out of scope. |
| Wave 6 scheduler | Add `arclink-wrapped` service using existing `docker-job-loop.sh` | Piggyback silently inside health-watch | Prefer explicit service unless BUILD finds a strong reason to integrate into an existing loop. It is easier to test, document, and operate. |
| Wave 6 data access | Read control DB plus bounded read-only per-deployment state roots through existing deployment metadata | Scan live user homes or private runtime paths ad hoc | Choose metadata-bounded reads only. No uid crossing or private-state rummaging. |

## Build Assumptions

- Current source and focused tests are ground truth where historical docs
  disagree.
- Schema foundations from prior waves are usable; new columns should be added
  only when a concrete Wave 4-6 behavior requires them.
- `arclink_share_grants` remains the attachment/security projection model.
- Chutes-backed Crew Recipe generation must be injectable/fake-tested locally;
  no live inference proof is required for BUILD.
- Wrapped reports may compute from deterministic local fixtures; live Hermes
  session proof remains operator-gated.
- Captain-facing copy uses ArcPod / Pod / Agent / Captain / Crew / Raven /
  Comms. Backend/operator code can keep deployment/user naming.

## Risks

- Cross-Captain comms must fail closed unless an active `pod_comms`
  share-grant exists.
- Comms rate limiting must happen before expensive writes or notification
  fanout.
- Crew Recipe generation must reject unsafe model output and fall back
  deterministically after bounded retries.
- Identity-context overlay writes must not wipe memory, sessions, or unrelated
  org-profile overlays.
- Wrapped must redact secrets before rendering and must not expose Captain
  narrative in Operator views.
- Quiet-hours behavior for Wrapped depends on existing user/profile data; if a
  precise source is unavailable, BUILD should document and test the selected
  fail-closed or default behavior.

## Verdict

PLAN is ready for BUILD handoff for Waves 4-6 in order: Pod-to-Pod Comms,
Crew Training, then ArcLink Wrapped. The existing build gate was stale Wave 3
content and has been replaced with a no-secret Wave 4-6 gate.
