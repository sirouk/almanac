# Document Phase Status

Generated: 2026-05-08 (Ralphie document phase: final product-reality alignment)

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
| `docs/arclink/raven-public-bot.md` | Already documents `/raven_name`, `/link_channel`, `/connect_notion`, share approval callbacks, and upgrade-rail guidance |
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
