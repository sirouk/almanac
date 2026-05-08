# Research Summary

<confidence>94</confidence>

## Objective

Prepare BUILD handoff for the ArcLink ecosystem gap repair mission. The mission
is to close verified May 2026 gaps across Shared Host, Shared Host Docker,
Sovereign Control Node, hosted web/API, private and public onboarding, Hermes
runtime plugins, qmd/Notion/SSOT knowledge rails, documentation, validation,
and operator/user journeys.

The controlling backlog remains
`research/RALPHIE_ARCLINK_ECOSYSTEM_GAP_REPAIR_STEERING.md`. BUILD must not
route to terminal `done` while unchecked tasks remain in that steering file or
`IMPLEMENTATION_PLAN.md`.

## Repository Findings

ArcLink is a multi-runtime platform, not a single library or web app:

- Bash wrappers own deploy, Docker, bootstrap, health, service installation,
  qmd/PDF jobs, backup, upgrade, and runtime orchestration.
- Python modules own the control plane, hosted API, browser/API auth,
  onboarding, provisioning, Docker supervisor, action worker, MCP tools,
  Notion/SSOT rails, memory synthesis, evidence, fleet, rollout, diagnostics,
  and dashboard plugin APIs.
- Docker Compose and systemd define the Shared Host Docker and bare-metal
  Shared Host topologies.
- The Next.js app owns the hosted onboarding, checkout, login, dashboard, and
  admin UI surfaces.
- ArcLink-owned Hermes plugins, hooks, generated config, and skills provide
  runtime behavior without modifying Hermes core.
- qmd, PDF ingest, Notion indexing, SSOT writes, memory synthesis, and resource
  skills form the knowledge rails whose freshness and generated-content safety
  gates are now completed baseline behavior to preserve.

Repository composition verified during this PLAN pass from public repo files:
54 first-party `python/arclink_*.py` modules, 99 Python test files, 82 shell
scripts, 29 systemd units, 36 web source/test/config TS/TSX/MJS/JS files, 24
`arclink_*` control DB table definitions, 4 Hermes plugins, 11 skills, and 26
Compose services.

## Implementation Path Comparison

| Path | Strengths | Weaknesses | Decision |
| --- | --- | --- | --- |
| Slice repairs through existing ArcLink wrappers, Python modules, web app, plugins, Compose, systemd units, and focused tests | Matches repository boundaries, preserves operator workflows, avoids Hermes core edits, and lets high-risk gates remain testable | Requires careful sequencing across many surfaces | Selected |
| Disable or mark unsafe/unimplemented surfaces unavailable until a real provider, worker, or policy path exists | Prevents misleading product claims and avoids credential-dependent guesses | Leaves some journeys blocked until operator policy is defined | Acceptable for policy-owned or unsafe operations |
| Rebuild as a new hosted control app first | Could simplify one browser journey | Leaves deploy, Docker, agent runtime, qmd, Notion, and Shared Host gaps open | Rejected |
| Patch Hermes core or rely on private-state workarounds | Might hide a local symptom quickly | Violates constraints and creates upgrade debt | Rejected |
| Documentation-only reconciliation | Low code risk | Does not close verified behavior gaps | Rejected except for explicitly blocked policy-only items |

## Current State

Slices 1 through 6 are completed baseline gates in the active plan:

- Security and trust boundaries.
- Hosted web/API identity, checkout, and dashboard.
- Control-plane execution truthfulness.
- Shared Host and Docker operational parity.
- Private Curator and public bot onboarding recovery.
- Knowledge freshness and generated content safety.

Slice 7 / Priority 6 documentation and validation coverage is also checked in
the active plan and steering file:

- Documentation status, first-day/operator runbooks, Docker/data-safety truth,
  and validation dependency clarity.

Current backlog state after this PLAN pass: no open checkbox task markers remain in
`IMPLEMENTATION_PLAN.md` or
`research/RALPHIE_ARCLINK_ECOSYSTEM_GAP_REPAIR_STEERING.md`. BUILD should
therefore proceed as a verification and review handoff: preserve the completed
gates, run focused validation, repair any newly discovered regressions, and
keep proof-gated/live flows blocked unless the operator explicitly authorizes
them.

## Assumptions

- Public repo code, tests, docs, wrappers, generated config, systemd units,
  Compose services, web/API code, hooks, plugins, and skills are in scope.
- Private state, user homes, tokens, deploy keys, OAuth credentials, bot
  tokens, live `.env` values, live deploys, production payment flows, public bot
  mutations, and external credential-dependent proof are out of scope unless
  the operator explicitly authorizes them during BUILD.
- Shared Host, Docker, and Sovereign Control Node should remain distinct while
  their contracts, defaults, health checks, and docs become aligned.
- Behavior must be fixed before docs; docs should mark unproved or policy-owned
  areas as proof-gated or blocked instead of inventing product truth.

## Planning Verdict

PLAN is ready for BUILD handoff. Required artifacts are project-specific and
portable, the implementation plan contains no fallback placeholder marker, and
no planning-only blocker was identified.

## Remaining Risks

- The worktree already contains many modified files; BUILD must avoid reverting
  unrelated edits and keep any later commit scoped.
- Public bot mutation, live Stripe, Cloudflare, Tailscale, Docker
  install/upgrade, and host deploy/upgrade checks remain proof-gated unless the
  operator authorizes them.
- Documentation and validation claims still need BUILD review against the dirty
  worktree before release completion is declared.
- Live-proof and credential-dependent validation choices may require operator
  policy; those should become explicit blocked questions rather than inferred
  behavior.
