# Document Phase Status

Generated: 2026-05-08 (Ralphie document phase: final product-reality alignment)

Updated: 2026-05-10 (Raven selected-agent bridge contract alignment)

Updated: 2026-05-14 (ArcLink Wrapped runbook alignment)

## 2026-05-14 ArcLink Wrapped Documentation Update

The current implementation plan and recent build notes show Wave 6 ArcLink
Wrapped implemented locally across core generation, scheduler/delivery, hosted
API routes, dashboard tabs, pure Raven cadence handling, OpenAPI, and focused
tests. This document pass updated project-facing documentation for the
operational runbook gap without adding live-proof claims.

### Files Updated

| File | Change | Rationale |
| --- | --- | --- |
| `docs/arclink/operations-runbook.md` | Added ArcLink Wrapped ownership, read/write assumptions, cadence limits, scheduler/delivery runbook, aggregate Operator boundary, and troubleshooting notes | The canonical operations runbook did not yet describe the new `arclink-wrapped` service, `captain-wrapped` delivery rail, or admin privacy boundary |
| `docs/arclink/control-node-production-runbook.md` | Tightened the Wrapped cadence-handler wording so the inline command and allowed cadences render unambiguously | The production runbook already covered Wrapped behavior; this keeps the existing note mechanically clear |
| `README.md` | Added `docs/arclink/wrapped.md` to the detailed ArcLink documentation index | The new canonical Wrapped doc was classified in `docs/DOC_STATUS.md` but was not visible from the top-level doc list |
| `docs/arclink/document-phase-status.md` | Added this dated status note | Keeps the document-phase handoff current after the Wrapped documentation pass |

### Docs Inspected

| File | Verdict |
| --- | --- |
| `AGENTS.md` | Still aligned on no-secret handling, deploy-mode boundaries, and Raven/Captain/Operator vocabulary |
| `IMPLEMENTATION_PLAN.md` | Current plan names Wrapped read-only assumptions, scheduler/delivery constraints, aggregate-only Operator views, and closeout gates |
| `research/BUILD_COMPLETION_NOTES.md` | Records the Wrapped core, scheduler/delivery, API/dashboard/bot slices, validation, and skipped live gates |
| `docs/arclink/wrapped.md` | Already documents the single owner module, scheduler service, delivery rail, API/dashboard/bot surfaces, proof commands, and novelty-score formula |
| `docs/API_REFERENCE.md` | Lists the new user/admin Wrapped routes |
| `docs/openapi/arclink-v1.openapi.json` | Includes the Wrapped route catalog generated from hosted API descriptions |
| `docs/arclink/architecture.md` | Names `arclink_wrapped.py` and the user/admin Wrapped route boundaries |
| `docs/arclink/control-node-production-runbook.md` | Already includes the production Wrapped service, delivery, privacy, and proof-gate notes |
| `docs/DOC_STATUS.md` | Already classifies `docs/arclink/wrapped.md` as canonical |

### Open Questions And Risks

- Live Telegram/Discord delivery, public bot command registration,
  production deploy/upgrade, Docker install/upgrade, and external
  credential-dependent proof remain operator-gated.
- The document pass did not claim terminal Wave 6 or Mission Closeout
  completion; it only reconciled current project-facing docs for the Wrapped
  behavior already implemented locally.
- Operator Wrapped surfaces must remain aggregate-only. Any future admin route
  that exposes report text, Markdown, or raw ledger snippets would require a
  privacy review and doc update.

Docs are clear enough to proceed with the current Wrapped handoff. Canonical
docs now describe ownership, assumptions, runbook behavior, and privacy
boundaries without local operator identity, private paths, secrets, command
transcripts, or machine-only evidence.

## 2026-05-10 Raven Bridge Contract Update

The current product matrix now counts 101 `real`, 0 `partial`, 0 `gap`, 15
`proof-gated`, and 5 `policy-question` rows. Raven direct-agent chat scope is
no longer an open policy row: slash commands remain Raven controls, while
onboarded-user freeform Telegram/Discord messages queue selected-agent turns
through `notification-delivery` and return the agent reply to the same linked
channel.

### Files Updated

| File | Change | Rationale |
| --- | --- | --- |
| `research/PRODUCT_REALITY_MATRIX.md` | Reclassified Raven direct-agent public chat from `policy-question` to `real` and updated the evidence/action language | The live code, tests, docs, and deployed proof now implement Raven-mediated selected-agent freeform chat |
| `research/COVERAGE_MATRIX.md` | Updated row totals and Raven validation coverage | The coverage map still described the older control-only policy |
| `research/RESEARCH_SUMMARY.md` | Removed Raven chat scope from the remaining policy-question list | The operator chose the behavior and it is implemented/tested |
| `research/BUILD_COMPLETION_NOTES.md` | Added this change as the latest build note | Future agents should not resurrect the old control-only assumption |

### Open Questions And Risks

- Browser right-click Drive/Code share-link enablement, canonical Chutes
  OAuth/provider path, threshold continuation copy, self-service provider
  changes, and scoped peer-awareness remain product-policy rows.
- Live Stripe, Telegram, Discord, Chutes, Notion, Cloudflare, Tailscale,
  and production-provider mutation proof remain credential-gated.

## 2026-05-09 Documentation Update

At that time, the implementation plan and product matrix counted 100 `real`, 0
`partial`, 0 `gap`, 15 `proof-gated`, and 6 `policy-question` rows. This pass
updated the project-facing runbooks for the new Chutes secret-reference live
adapter, Chutes OAuth/connect fake callback boundary, provider-specific
external live-proof journey, and Notion shared-root no-secret proof harness.

### Files Updated

| File | Change | Rationale |
| --- | --- | --- |
| `docs/arclink/live-e2e-secrets-needed.md` | Added `--journey external` usage, opt-in `ARCLINK_PROOF_*` behavior, provider-specific environment rows, Chutes OAuth/usage/key/account/transfer proof gates, and Notion shared-root SSOT proof variables | The live-proof docs previously covered hosted and workspace proof, but not the new provider-specific external proof journey |
| `docs/arclink/operations-runbook.md` | Added `python/arclink_chutes_live.py` and `python/arclink_chutes_oauth.py` ownership, OAuth/account-creation rationale, mutation gates, external proof command, and the expanded live journey/evidence runbook | Operators need the current access boundary: secret refs only, fake-tested OAuth/callbacks, no silent Chutes account creation, and live mutation proof only with explicit authorization |
| `docs/arclink/document-phase-status.md` | Added this dated status note | Keeps the document-phase handoff current without rewriting historical audit context |

### Docs Inspected

| File | Verdict |
| --- | --- |
| `AGENTS.md` | Still aligned on no-secret handling, Notion SSOT broker ownership, Chutes provider defaults, and live-proof gating |
| `README.md` | Already names Chutes-first provider defaults, Notion SSOT, and live-proof orchestration at a product level |
| `IMPLEMENTATION_PLAN.md` | Active handoff now points at the 2026-05-09 proof/build spec and marks the Chutes, Notion, Raven, and browser-share continuation tasks complete or gated |
| `research/RALPHIE_END_TO_END_PROOF_AND_BUILD_SPEC_20260509.md` | New steering source for Chutes proof, external proof orchestration, and remaining operator decisions |
| `research/PRODUCT_REALITY_MATRIX.md` | Reconciled to the then-current Chutes proof rows, Raven chat-scope policy row, Notion proof harness row, and 100/15/6 totals |
| `research/BUILD_COMPLETION_NOTES.md` | Records the no-secret Chutes live adapter, OAuth callback, Notion harness, and validation results |
| `docs/API_REFERENCE.md` | Current hosted API docs still describe sanitized provider state and local provider-budget credit posture; no route catalog change was needed |
| `docs/arclink/raven-public-bot.md` | Updated to state that active Telegram chats move Raven controls behind `/raven`, expose active-agent slash commands in the per-chat menu, and queue selected-agent turns back to the linked channel |
| `docs/arclink/notion-human-guide.md` | Already states shared-root membership is canonical and user-owned OAuth/email-only sharing are non-default proof-gated lanes |

### Open Questions And Risks

- Live Stripe, Telegram, Discord, Chutes, Notion, Cloudflare, Tailscale,
  Docker, host deploy/upgrade, and deployed dashboard proof remain
  credential-gated.
- Raven direct-agent public chat scope, browser right-click share-link
  enablement, canonical Chutes OAuth/provider path, threshold continuation
  copy, self-service provider changes, and scoped peer-awareness remain product
  policy questions.
- Chutes account registration, API-key CRUD, token revoke, and balance transfer
  require explicit authorization and secret references before any live mutation
  proof. Current docs describe fake-tested boundaries, not completed live
  provider proof.

Docs are clear enough to proceed: project-facing runbooks now describe the
current local implementation, ownership boundaries, proof gates, and rationale
without local operator identity, private paths, secrets, or command
transcripts.

## Documentation Audit

Project-facing ArcLink documentation has been checked against the current
Ralphie product-reality matrix, implementation plan, operator-policy addendum,
recent build notes, and the closest README/AGENTS/docs artifacts. This pass
focused on the final no-secret behaviors that changed after the earlier
share-approval audit: single-operator ownership, Chutes provider isolation,
failed-renewal suspension and warning cadence, local provider-budget credits,
living linked-resource projections, recipient copy/duplicate, Raven display
name customization, shared-root Notion SSOT membership, and managed-context
memory cherrypicks.

No live-proof claims, local operator identity, private paths, secrets, command
transcripts, or machine-only evidence were added.

## Files Updated

| File | Change | Rationale |
| --- | --- | --- |
| `docs/API_REFERENCE.md` | Clarified that local provider-budget credit accounting is separate from live purchase/provider-balance proof, and that threshold continuation copy/provider-change policy remains gated | The previous wording could imply refill accounting was still wholly undecided even though local credit accounting is now implemented |
| `docs/arclink/architecture.md` | Corrected Drive/Code `Linked` root behavior to allow copy/duplicate into owned roots, and replaced stale user-dashboard-live-data wording with the current wired routes plus the intentionally deferred share-management UI | The final matrix marks recipient copy/duplicate and user dashboard read wiring as real, while broader share create/approve/accept/revoke dashboard UI remains incomplete |
| `docs/arclink/operations-runbook.md` | Added the single active owner rule, clarified owner recovery versus second-owner creation, tightened linked-resource copy/duplicate wording, and documented the Chutes provider access boundary, failed-renewal lifecycle, local budget thresholds, local provider-budget credit helpers, raw-token avoidance, and per-user account/OAuth fallback | The matrix now marks these behaviors as local public-repo contracts, but the runbook still focused on earlier share-approval and fake-key lifecycle wording |
| `plugins/hermes-agent/drive/README.md` and `plugins/hermes-agent/code/README.md` | Replaced stale browser-sharing decision wording with the current gate: right-click share UI stays off until a live ArcLink browser broker or approved Nextcloud-backed adapter is enabled | The operator decision now exists; the remaining issue is implementation/proof of the browser sharing backend, not an unanswered model choice |
| `research/PRODUCT_REALITY_MATRIX.md` | Reworded the browser right-click sharing row so the remaining blocker is backend enablement/proof, not choosing the sharing model again | The operator decision now names ArcLink grants backed by living shared roots as canonical, with Nextcloud/WebDAV/OCS preferred where safely enabled |
| `docs/arclink/document-phase-status.md` | Replaced the earlier share-approval-only audit with this final product-reality documentation status | The previous status still treated recipient copy/duplicate as undecided and did not reflect the later provider, billing, ownership, and memory reconciliation work |

## Docs Inspected

| File | Verdict |
| --- | --- |
| `AGENTS.md` | Canonical operating guide remains aligned with deploy-mode boundaries, private-state safety, and agent runtime ownership |
| `README.md` | Top-level product/deploy overview already describes the current local behavior and live-proof gates |
| `IMPLEMENTATION_PLAN.md` | Active handoff plan shows no remaining partial/gap rows and keeps live/policy gates explicit |
| `research/PRODUCT_REALITY_MATRIX.md` | Current matrix totals remain 98 real, 0 partial, 0 gap, 12 proof-gated, and 4 policy-question; browser sharing wording now reflects the answered operator model and remaining backend gate |
| `docs/DOC_STATUS.md` | Classification remains valid; this status file is historical and canonical docs own current operating truth |
| `docs/API_REFERENCE.md` | Lists credential, share-grant, linked-resource, billing lifecycle, sanitized Chutes provider-state routes, local provider-budget credit posture, and remaining continuation-policy gates |
| `docs/openapi/arclink-v1.openapi.json` | Already includes the current hosted API route catalog |
| `docs/arclink/architecture.md` | Reflects credential/share routes, current user dashboard API wiring, and Drive/Code `Linked` root boundaries |
| `docs/arclink/first-day-user-guide.md` | Already describes credential acknowledgement and read-only linked resources for users |
| `docs/arclink/raven-public-bot.md` | Documents `/raven` active Telegram controls, `/raven_name`, `/link_channel`, `/connect_notion`, share approval callbacks, command-scope conflict alerts, upgrade-rail guidance, and Raven-mediated selected-agent chat |
| `docs/arclink/notion-human-guide.md` | Already names shared-root membership as the canonical SSOT sharing model and keeps user-owned OAuth/email-share paths non-default |
| `plugins/hermes-agent/drive/README.md` and `plugins/hermes-agent/code/README.md` | Document `Linked` root discovery, read-only behavior, no reshare, owned copy/duplicate from linked content, and the disabled browser share-link gate |
| `plugins/hermes-agent/arclink-managed-context/README.md` | Already documents recall budget tiers and sibling conversational-memory boundaries |
| `docs/arclink/control-node-production-runbook.md` and `docs/arclink/sovereign-control-node.md` | Already document deployment-style selection and keep live production proof credential-gated |

## Open Questions And Risks

- Live Stripe, Chutes, Telegram, Discord, Notion, Cloudflare, Tailscale, Docker
  install/upgrade, and production host proof remain credential-gated.
- Browser right-click Drive/Code share creation remains disabled until a live
  ArcLink broker or approved Nextcloud-backed adapter exists.
- Chutes threshold continuation copy and self-service provider-change UI remain
  product-policy questions; current docs keep those surfaces disabled or
  labeled as policy-gated.
- Scoped agent self-model or multi-agent peer-awareness cards remain a
  product-policy question unless a future audited, no-transcript-leak path is
  built with tests.

## Validation

- Documentation truth checks passed after this pass.
- Public repo hygiene passed after shipped docs used generic
  provider-budget-credit wording instead of speculative add-on product copy.
- Markdown/diff whitespace hygiene passed.
- Stale-phrase search found no remaining current-doc or active-matrix claims
  that recipient copy/duplicate is still undecided, browser sharing is waiting
  on an operator model choice, or user dashboard data wiring is deferred.

## Transition Readiness

- Documentation work is complete for the current no-secret product-reality
  repair: current canonical docs describe the implemented local behavior,
  disabled or deferred browser sharing surfaces, and live-proof boundaries.
- No additional project-facing documentation change is required before terminal
  handoff unless later code changes alter the product matrix, route catalog,
  billing/provider contract, dashboard wiring, or plugin behavior.
- The remaining proof-gated and product-policy rows are not documentation
  blockers. They stay disabled, labeled, or credential-gated until explicit
  authorization or product policy exists.
- This document phase does not authorize live Stripe, provider, bot, Notion,
  ingress, Docker install/upgrade, or host deploy/upgrade operations.

## Verdict

Docs are clear enough to proceed with the Ralphie handoff. The canonical docs
now describe the current no-secret implementation and rationale without
claiming unproved live external behavior.
