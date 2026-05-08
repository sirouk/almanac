# Coverage Matrix

## Goal Coverage Against Active Mission

| Goal / criterion | Current coverage | Remaining BUILD work | Validation surface |
| --- | --- | --- | --- |
| Product claims classified as `real`, `partial`, `gap`, `proof-gated`, or `policy-question` | `research/PRODUCT_REALITY_MATRIX.md` has 114 classified rows with 98 real, 12 proof-gated, and 4 policy-question rows | Keep the matrix updated as behavior changes; do not claim done while proof/policy gates remain unresolved or unlabeled | Matrix review, focused tests, docs diff |
| Ecosystem hardening preserved | `research/RALPHIE_ARCLINK_ECOSYSTEM_GAP_REPAIR_STEERING.md` has detailed checklist items marked complete | Treat hardening items as invariants when touching dashboard plugins, qmd, Notion, SSOT, Docker, token, cleanup, auth, checkout, provisioning, health, docs, or validation | Existing plugin, qmd, Notion, SSOT, Docker/static, deploy, health, and docs tests |
| Website, Telegram, and Discord onboarding starts are truthful | Web routes and public bot adapters exist | Re-verify start, resume, cancel, checkout, failure, and no-secret fake-bot flows; keep live delivery/payment proof gated | Hosted API, public bot, Telegram, Discord, and web tests |
| Payment-gated deployment is enforced | Local entitlement/provisioning gate rows are mostly `real` | Preserve local gates and avoid claiming live Stripe truth without proof | Onboarding, entitlement, provisioning, hosted API tests; live proof only if authorized |
| Credential handoff is safe | API/dashboard rows classify reveal, copy/store guidance, ack, and post-ack hiding as `real` | Preserve no-raw-secret responses and channel notification safety | Hosted API/auth/dashboard/security tests |
| User/admin dashboard isolation is enforced | User-only dashboard, provider, health, billing, credentials, channels, linked resources, and admin all-system health have local evidence | Expand or rerun isolation tests when touching any route, dashboard panel, share, provider, or bot session | `tests/test_arclink_hosted_api.py`, `tests/test_arclink_api_auth.py`, `tests/test_arclink_dashboard.py`, browser tests |
| Raven is a truthful post-onboarding control conduit | Agent inventory, switching, labels, explicit channel identifiers, channel linking aliases, share approvals, upgrade guidance, and local Raven display-name preferences have local coverage | Preserve channel/account Raven display-name scoping, selected-agent labels, and platform-profile truthfulness | Public bot, Telegram, Discord tests |
| Knowledge, Almanac, qmd, Notion, SSOT, and memory are truthful | qmd collections, SSOT broker, shared-root SSOT membership, Notion index, recall stubs, trust/conflict metadata, local fallback, recall budgets, and optional conversational-memory sibling boundaries have local rows; Almanac is treated as knowledge-store lineage/planning vocabulary, not the top-level product | Preserve sibling-plugin boundaries and keep peer-awareness policy-gated until the operator defines the scope | qmd, MCP, Notion, SSOT, memory, managed-context tests |
| Drive sharing and linked resources are real or disabled | Share grants, owner approve/deny, no-reshare, agent-facing `shares.request`, read-only `Linked` roots, living projection/revoke cleanup, recipient copy/duplicate, and browser proof exist; Drive/Code right-click share-link creation is disabled | Preserve living linked-resource behavior; keep browser sharing disabled until a live ArcLink broker or approved Nextcloud/WebDAV/OCS adapter exists | Hosted API share tests, public bot tests, plugin tests, browser tests |
| Pricing, billing, and Chutes are truthful | Pricing, entitlement counts, Chutes isolated credential metadata, fail-closed local boundary, local usage ingestion, Refuel Pod local credits, failed-renewal lifecycle metadata, and explicit threshold-continuation gates exist | Preserve local credit and suspension semantics; keep live key-management/utilization/purchase proof gated | Product config, hosted API, Chutes adapter, billing, public bot tests |
| Operator setup, ingress, fleet, and admin UX are truthful | Deploy, Docker, Control Node, setup-style selector, singleton operator ownership, ingress, admin API, action truthfulness, and health surfaces exist | Preserve setup/action truth and finish Cloudflare/Tailscale proof only when authorized | Deploy/Docker/health/ingress/admin tests; live proof only if authorized |
| Upgrades are controlled through ArcLink | Pins, deploy rails, upgrade detector, and public upgrade command guidance are currently `real` | Preserve behavior if touched; no unmanaged Hermes upgrade exposure | Deploy regression, pin upgrade, public bot, docs tests |
| Focused validation is run and summarized | Validation floor is documented in the plan and dependency research | BUILD must run nearest no-secret checks and record skipped proof-gated checks with concrete reasons | `git diff --check`, shell syntax, Python tests, web tests, browser tests where applicable |

## Product-Reality Row Summary

These counts reflect the current matrix after the 2026-05-08 operator-policy
reclassification pass.

| Status | Count |
| --- | ---: |
| `real` | 98 |
| `partial` | 0 |
| `gap` | 0 |
| `proof-gated` | 12 |
| `policy-question` | 4 |

| Status | BUILD meaning |
| --- | --- |
| `real` | Static code/test evidence supports the claim; preserve with tests when touched. |
| `partial` | Some implementation exists, but the complete journey, UI, docs, validation, or live boundary remains incomplete. |
| `gap` | No current rows are classified this way; if a gap appears, repair or disable before completion. |
| `proof-gated` | The row needs live/external proof or credentials that are not authorized in no-secret BUILD. |
| `policy-question` | Code cannot decide the product/security answer; ask the operator and keep the surface disabled, partial, or labeled. |

Current `partial` row targets: none.

## Required Artifact Coverage

| Required artifact | Coverage status |
| --- | --- |
| `research/RESEARCH_SUMMARY.md` | Summarizes scope, confidence, stack finding, path comparison, assumptions, risks, and handoff verdict. |
| `research/CODEBASE_MAP.md` | Maps root entrypoints, directories, runtime lanes, product entrypoints, services, hotspots, tests, and assumptions. |
| `research/DEPENDENCY_RESEARCH.md` | Documents stack components, versions, alternatives, external proof posture, risks, and validation dependencies. |
| `research/COVERAGE_MATRIX.md` | Maps active goals to coverage, remaining work, validation surfaces, row semantics, and completion criteria. |
| `research/STACK_SNAPSHOT.md` | Provides ranked stack hypotheses, deterministic confidence score, evidence, and rejected alternatives. |
| `IMPLEMENTATION_PLAN.md` | Provides goal, constraints, selected architecture, validation criteria, and actionable BUILD tasks. |
| `consensus/build_gate.md` | Records no-secret BUILD permission, live-flow blockers, proof gates, and operator-policy questions. |

## Minimum BUILD Completion Contract

BUILD can claim terminal completion only when every active steering and plan
task has one of these outcomes:

| Outcome | Required evidence |
| --- | --- |
| Repaired locally | Behavior, focused tests, nearest docs/UI/API copy, and validation notes agree; matrix row moves to `real`. |
| Proof-gated | Visible surface is disabled, labeled, or fail-closed; exact external authorization or credential needed is named. |
| Policy-question | Visible claim is disabled, partial, or labeled; matrix and build gate name the operator decision needed. |

Live Stripe, Telegram, Discord, Chutes, Notion, Cloudflare, Tailscale, Docker
install/upgrade, and production host proof are not required unless explicitly
authorized. Public copy must not claim those flows are complete without proof.

## Readiness Notes

- No-secret BUILD work is allowed by `consensus/build_gate.md`.
- The stack snapshot classifies ArcLink as a multi-runtime platform rather
  than a single web-app classification and records a deterministic confidence
  score.
- The build gate now records the received 2026-05-08 operator-policy decisions,
  the remaining policy questions, and a proof-escalation path for live/external
  rows.
- `IMPLEMENTATION_PLAN.md` must be re-reviewed and modified after this and any
  later research/gate refresh so it remains the BUILD handoff anchor.
- The highest-risk remaining local task is preservation: keep user isolation,
  secret handling, linked-resource read-only behavior, singleton operator
  ownership, Chutes fail-closed state, and SSOT/qmd boundaries intact while
  running focused validation.
- If BUILD updates supporting research artifacts, update the closest
  implementation-plan rows in the same slice so the plan remains the handoff
  anchor.
