# Research Summary

<confidence>96</confidence>

## Scope

This PLAN pass inspected the public ArcLink repository structure, runtime
manifests, service topology, tests, steering files, and existing research
artifacts. It did not inspect private state, user homes, secret files, deploy
keys, OAuth material, bot tokens, `.env` values, or live provider accounts. It
also did not run live deploys, upgrades, payment flows, public bot mutations,
Docker install/upgrade flows, or external Chutes, Notion, Cloudflare, or
Tailscale proof.

The active BUILD sources are:

- `research/RALPHIE_ARCLINK_PRODUCT_REALITY_AND_JOURNEY_STEERING.md`
- `research/RALPHIE_ARCLINK_ECOSYSTEM_GAP_REPAIR_STEERING.md`
- `research/RALPHIE_MEMORY_SYSTEM_CHERRYPICK_STUDY.md`
- `research/RALPHIE_END_TO_END_PROOF_AND_BUILD_SPEC_20260509.md`
- `research/PRODUCT_REALITY_MATRIX.md`
- `research/OPERATOR_POLICY_DECISIONS_20260508.md`
- `consensus/build_gate.md`
- `IMPLEMENTATION_PLAN.md`

The ecosystem-gap steering file has its detailed checklist marked complete in
the current public artifact. Treat it as a hardening-preservation baseline:
future BUILD work must not reopen those security, host, Docker, qmd, Notion,
SSOT, token, generated cleanup, onboarding, docs, or validation boundaries.

## Current Product Reality

The product reality matrix currently contains 121 rows:

| Status | Count |
| --- | ---: |
| `real` | 101 |
| `partial` | 0 |
| `gap` | 0 |
| `proof-gated` | 15 |
| `policy-question` | 5 |

This is no longer the raw pre-decision snapshot. The 2026-05-08
operator-policy addendum has been reconciled into the product matrix for Raven
identity customization, shared-root SSOT membership, failed-renewal lifecycle,
living linked resources, recipient copy/duplicate, exactly-one-operator
behavior, Refuel Pod local credits, and the Chutes account/OAuth fallback.
The 2026-05-10 Raven bridge update reclassifies public-channel direct-agent
chat scope as implemented: slash commands remain Raven controls, and
onboarded-user freeform messages route to the selected agent through Raven.

Current `partial` rows: none. The 2026-05-09 Chutes proof packet is now
represented in the matrix: silent Chutes account creation is not a product
claim, browser-challenge bypass is rejected, and live OAuth/registration,
personal usage sync, and balance-transfer behavior stay proof-gated.

Highest-risk remaining BUILD work after this PLAN refresh:

- Preserve and extend user isolation across dashboard, provider, channel,
  share, health, credential, billing, Notion/SSOT, and linked-resource
  surfaces while adding tests for each touched path.
- Reconcile the 2026-05-09 Chutes proof packet: account creation is assisted
  or proof-gated rather than silently server-created; personal usage/billing
  endpoints are real; provider-side per-API-key spend remains unproven; Sign
  in with Chutes / per-user account connection is the recommended canonical
  path.
- Keep browser right-click Drive/Code share-link creation disabled until a live
  shared backend exists or the operator chooses to build an ArcLink broker in
  this repo.
- Keep live Stripe, Telegram, Discord, Chutes, Notion, Cloudflare, Tailscale,
  Docker install/upgrade, and host deploy/upgrade proof gated until explicitly
  authorized.
- Resolve the remaining product-policy questions: scoped agent self-model or
  peer-awareness cards, browser right-click sharing enablement, canonical
  Chutes OAuth/provider path, public Chutes threshold-continuation copy, and
  user self-service provider changes. Raven direct-agent chat scope is no
  longer a policy question: onboarded-user freeform messages route to the
  selected agent through Raven, while slash commands remain Raven controls.

## Stack Finding

ArcLink is a multi-runtime product platform, not a single Node.js app. The
current public signals show:

- Python control plane, hosted API, public bots, provisioning, MCP, Notion,
  memory synthesis, fleet, rollout, and plugin APIs.
- Bash deploy, Docker, bootstrap, health, qmd, PDF, service, backup, and
  upgrade wrappers.
- Next.js, React, TypeScript, and Tailwind hosted web/dashboard application.
- Docker Compose services and systemd units for Shared Host, Shared Host
  Docker, and Sovereign Control Node lanes.
- Pinned Hermes runtime, qmd retrieval, ArcLink Hermes plugins, hooks, and
  skills for agent behavior without Hermes core edits.

Public source composition used by this handoff:

| Signal | Count |
| --- | ---: |
| Python files | 172 |
| Python regression tests | 101 |
| Shell/script entrypoints | 82 |
| Markdown files | 103 |
| systemd unit/timer/path files | 29 |
| Web TypeScript/JavaScript files | 17 |
| Public JSON/YAML files | 22 |

## Implementation Path Comparison

| Path | Strengths | Weaknesses | Decision |
| --- | --- | --- | --- |
| Repair existing ArcLink Bash, Python, web, plugin, Compose, and systemd surfaces | Preserves operator workflows and current tests; respects Hermes-core boundary | Requires careful sequencing across many surfaces | Selected default |
| Fail closed or label unavailable until provider proof or policy exists | Prevents false claims and keeps no-secret work safe | Leaves product gaps visible until policy/live proof is available | Use for external or policy-owned claims |
| Rewrite as a new hosted web app first | Could simplify one browser journey | Does not repair Shared Host, Docker, agent runtime, qmd, Notion, public bot, or dashboard-plugin contracts | Rejected |
| Documentation-only repair | Low implementation risk | Violates the mission requirement to fix behavior before docs | Rejected except for explicitly proof-gated or policy-only decisions |

## Artifacts Updated

- `research/RESEARCH_SUMMARY.md`: current scope, confidence, stack finding,
  matrix summary, assumptions, and risks.
- `research/CODEBASE_MAP.md`: portable map of directories, entrypoints,
  runtime lanes, source composition, and architecture assumptions.
- `research/DEPENDENCY_RESEARCH.md`: stack components, versions, alternatives,
  dependency risks, and validation dependencies.
- `research/COVERAGE_MATRIX.md`: goal coverage, required artifact coverage,
  product matrix status semantics, and completion rules.
- `research/STACK_SNAPSHOT.md`: ArcLink-specific multi-runtime stack
  hypotheses, deterministic 96/100 confidence score, current component
  signals, and rejected single-stack alternatives.
- `research/PRODUCT_REALITY_MATRIX.md`: updated 121-row reality matrix for the
  2026-05-09 Chutes proof and Raven policy scope.
- `research/OPERATOR_POLICY_DECISIONS_20260508.md`: portable Chutes research
  wording without local audit-checkout paths.
- `research/RALPHIE_END_TO_END_PROOF_AND_BUILD_SPEC_20260509.md`: portable
  Chutes research wording without local audit-checkout paths.
- `IMPLEMENTATION_PLAN.md`: project-specific BUILD plan with validation
  criteria and actionable tasks.
- `consensus/build_gate.md`: no-secret build permission, blocked live flows,
  and operator-policy questions.

This refresh records the current post-policy matrix totals, corrects the stack
snapshot to ArcLink's multi-runtime architecture, updates public source-count
signals, and confirms there are no `partial` or `gap` rows.

It also removes local audit-checkout paths from Chutes research artifacts so
the handoff remains portable.

Retry repair note: the build gate now names exactly the 15 proof-gated rows
and exactly the six remaining policy-question rows from the matrix. Chutes
account-registration execution, Refuel transfer, and day-14 purge execution are
separate non-counted authorization/expansion confirmations. `IMPLEMENTATION_PLAN.md`
must remain the newest active handoff artifact after this research refresh so
BUILD does not loop on stale plan detection.

## Assumptions

- Public repository files are sufficient for PLAN-level stack and static
  product classification.
- Live provider capabilities require explicit operator authorization and cannot
  be inferred from local code.
- Code and focused tests should be treated as truth when docs disagree; docs
  should be updated after behavior is repaired.
- Shared Host, Shared Host Docker, and Sovereign Control Node are separate
  lanes that need aligned but not collapsed contracts.
- ArcLink behavior belongs in public repo wrappers, generated config, plugins,
  hooks, service units, hosted API, public bots, web dashboards, and tests, not
  in Hermes core.

## Remaining Blockers And Risks

- Live Stripe, Telegram, Discord, Chutes, Notion, Cloudflare, Tailscale,
  Docker install/upgrade, and host deploy/upgrade proof is blocked without
  operator authorization.
- Product policy is still required for five current matrix rows: scoped agent
  self-model or peer-awareness cards, browser right-click sharing enablement,
  canonical Chutes OAuth/provider path, self-service provider changes, and
  exact public threshold copy after Refuel Pod/provider-fallback rails exist.
- Remaining decisions should be handled in dependency order: first isolation
  and secrets, then billing/provider lifecycle, then sharing/knowledge, then
  admin role/action behavior, then Raven and trust-signal presentation.
- Existing local code has many repaired rows. BUILD must preserve those
  boundaries and run focused validation before declaring terminal completion.

## Verdict

PLAN is ready for no-secret BUILD handoff. Confidence is 96/100: repository
shape, runtime stack, active artifacts, matrix coverage, and validation surfaces
are clear; confidence is capped because live external proof and multiple
remaining operator-policy presentation/scope decisions remain intentionally
gated.
