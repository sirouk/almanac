# ArcLink Documentation Status Map

This map classifies tracked documentation by how it should be used during
implementation. When docs and code disagree, treat code and focused regression
tests as truth, then update the closest canonical doc.

## Status Labels

| Status | Meaning |
| --- | --- |
| Canonical | Current operator or developer guidance. Keep in sync with code and tests. |
| Proof-gated | Describes live or production behavior that still requires external credentials, host access, or browser proof before it can be claimed complete. |
| Historical | Records prior implementation phases or audit context. Useful background, not current operating truth. |
| Speculative | Product, creative, or architecture direction that may describe intent before implementation. |
| Stale | Known to contain outdated claims. Do not rely on it until repaired or reclassified. |

## Current Map

| Path | Status | Notes |
| --- | --- | --- |
| `AGENTS.md` | Canonical | First-read operator and coding-agent guide for Shared Host, Shared Host Docker, and Sovereign Control Node boundaries. |
| `README.md` | Canonical | Top-level product, deploy-mode, and validation entrypoint. |
| `docs/docker.md` | Canonical | Shared Host Docker operations and trusted-host Docker boundary. |
| `docs/API_REFERENCE.md` | Canonical | Hosted API route and config reference; OpenAPI remains in `docs/openapi/`. |
| `docs/org-profile.md` | Canonical | Organization profile ingestion and private-state source guidance. |
| `docs/arclink/architecture.md` | Canonical | Current module map, route catalog, and integration boundaries. |
| `docs/arclink/foundation.md` | Canonical | Behavior notes for no-secret foundation and proof-gated execution boundaries. |
| `docs/arclink/foundation-runbook.md` | Canonical | Repair and validation runbook for foundation behavior. |
| `docs/arclink/operations-runbook.md` | Canonical | Operator runbook for hosted/control operations and workspace plugins. |
| `docs/arclink/data-safety.md` | Canonical | State, secret, and teardown safety across Shared Host, Docker, and Control Node modes. |
| `docs/arclink/vocabulary.md` | Canonical | User-facing ArcPod/Captain/Crew/Raven vocabulary and Operator/backend boundary rules. |
| `docs/arclink/wrapped.md` | Canonical | ArcLink Wrapped ownership, privacy boundary, scheduler/delivery behavior, and novelty-score rationale. |
| `docs/arclink/first-day-user-guide.md` | Canonical | First-day customer/operator-user guide. |
| `docs/arclink/control-node-production-runbook.md` | Proof-gated | Production Control Node checklist; live claims require credentials and evidence. |
| `docs/arclink/notion-human-guide.md` | Canonical | Human-facing Notion, SSOT, indexing, and destructive-boundary guide. |
| `docs/arclink/live-e2e-secrets-needed.md` | Proof-gated | Live proof prerequisites and Node/Playwright setup. |
| `docs/arclink/live-e2e-evidence-template.md` | Proof-gated | Evidence capture template for credentialed live runs. |
| `docs/arclink/operator-stripe-webhook.md` | Canonical | Stripe event destination setup. |
| `plugins/hermes-agent/*/README.md` | Canonical | Plugin-local behavior, install notes, and validation checks. |
| `IMPLEMENTATION_PLAN.md` | Historical | Ralphie build backlog/status, not an operating runbook. |
| `research/CONTRACT_AUDIT_20260510.md` | Historical | No-secret contract audit snapshot after the Raven selected-agent bridge repair. Useful evidence, but canonical docs/tests own current behavior. |
| `research/RALPHIE_ARCLINK_ECOSYSTEM_GAP_REPAIR_STEERING.md` | Historical | Steering backlog and audit-derived rationale. |
| `research/*` | Historical | Research and phase notes unless a specific file says otherwise. |
| `docs/arclink/CREATIVE_BRIEF.md` | Speculative | Product voice and public copy direction; verify against implemented web/bot behavior before treating as shipped. |
| `docs/arclink/CHANGELOG.md` | Historical | Phase changelog. Useful context, but nearby canonical docs own current behavior. |
| `docs/arclink/document-phase-status.md` | Historical | Documentation phase audit status. |

## Stale Queue

No tracked doc is intentionally left in `Stale` status after the May 2026
documentation repair pass. If future audits find stale guidance, add it to the
map with `Stale` status until the same change repairs or retires it.

## Maintenance Rule

When adding a new public doc, classify it here in the same change. If a doc is
kept only as background, mark it historical or speculative rather than quietly
letting it compete with canonical guidance.
