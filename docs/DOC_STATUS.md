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
| `AGENTS.md` | Canonical | First-read operator and coding-agent guide for the Sovereign Control Node, fleet ArcPods, and retired legacy-mode boundaries. |
| `README.md` | Canonical | Top-level product, deploy-mode, and validation entrypoint. |
| `docs/docker.md` | Canonical | Retired Shared Host Docker notice plus Control Node Docker-substrate boundary. |
| `docs/API_REFERENCE.md` | Canonical | Hosted API route and config reference; OpenAPI remains in `docs/openapi/`. |
| `docs/org-profile.md` | Canonical | Organization profile ingestion and private-state source guidance. |
| `docs/arclink/architecture.md` | Canonical | Current module map and integration boundaries; its route table cross-links `docs/API_REFERENCE.md` and `docs/openapi/arclink-v1.openapi.json` as the authoritative route catalog. |
| `docs/arclink/public-agent-gateway.md` | Canonical | Public Agent gateway and trusted-host broker/helper security boundary; cross-links `operations-runbook.md` GAP-019 entries as the authoritative trust-boundary source. |
| `docs/arclink/brand-system.md` | Canonical | Brand palette, typography, and voice; matches the product-surface CSS. |
| `docs/arclink/professional-finish-gate.md` | Canonical | Cross-surface finish-gate guidance naming the executable `arclink_surface_contract.py` linter and its taxonomy. |
| `docs/arclink/foundation.md` | Canonical | Behavior notes for no-secret foundation and proof-gated execution boundaries. |
| `docs/arclink/foundation-runbook.md` | Canonical | Repair and validation runbook for foundation behavior. |
| `docs/arclink/operations-runbook.md` | Canonical | Operator runbook for hosted/control operations and workspace plugins. |
| `docs/arclink/llm-router.md` | Canonical | Source-level Control Node LLM Router behavior, ownership, config, policy, and proof boundary. |
| `docs/arclink/data-safety.md` | Canonical | State, secret, and teardown safety across Control Node ArcPods and legacy migration state. |
| `docs/arclink/vocabulary.md` | Canonical | User-facing ArcPod/Captain/Crew/Raven vocabulary and Operator/backend boundary rules. |
| `docs/arclink/wrapped.md` | Canonical | ArcLink Wrapped ownership, privacy boundary, scheduler/delivery behavior, and novelty-score rationale. |
| `docs/arclink/first-day-user-guide.md` | Canonical | First-day customer/operator-user guide. |
| `docs/arclink/control-node-production-runbook.md` | Proof-gated | Production Control Node checklist; live claims require credentials and evidence. |
| `docs/arclink/notion-human-guide.md` | Canonical | Human-facing Notion, SSOT, indexing, and destructive-boundary guide. |
| `docs/arclink/live-e2e-secrets-needed.md` | Proof-gated | Live proof prerequisites and Node/Playwright setup. |
| `docs/arclink/live-e2e-evidence-template.md` | Proof-gated | Evidence capture template for credentialed live runs. |
| `docs/arclink/operator-stripe-webhook.md` | Canonical | Stripe event destination setup. |
| `docs/arclink/sovereign-control-node.md` | Canonical | Sovereign Control Node product overview and deploy path. |
| `docs/arclink/academy-trainer.md` | Canonical | Academy training subsystem (sticky Mode, central corpus, continuing education, and the PG-HERMES-gated Academy SOUL apply path). |
| `docs/arclink/raven-public-bot.md` | Canonical | Raven public-bot persona, voice, and onboarding story rails. |
| `docs/arclink/fleet-cli.md` | Canonical | `./deploy.sh control ...` Operator CLI surface, subcommands, and JSON/exit-code contract. |
| `docs/arclink/fleet-operator-runbook.md` | Canonical | Source-level Sovereign fleet operations; live host/provider proofs require Operator authorization and cross-link `operations-runbook.md` GAP-019 entries. |
| `docs/arclink/ingress-plan.md` | Canonical | Ingress modes (Cloudflare/Traefik `domain` and Tailscale path mode); live DNS apply remains proof-gated. |
| `docs/arclink/backup-restore.md` | Canonical | Backup/restore targets and methods; live GitHub write/activation/restore recoverability remain proof-gated. |
| `docs/arclink/alert-candidates.md` | Canonical | The shipped `arclink_health_watch` alerting rail plus candidate signals that have real state tables but no in-repo emitter yet. |
| `docs/arclink/local-validation.md` | Canonical | No-secret, web, and proof-gated local validation procedures. |
| `docs/arclink/secret-checklist.md` | Proof-gated | Secrets required for live deployment; live behavior requires these credentials before it can be claimed. |
| `plugins/hermes-agent/*/README.md` | Canonical | Plugin-local behavior, install notes, and validation checks. |
| `IMPLEMENTATION_PLAN.md` | Historical | Build backlog/status, not an operating runbook. |
| `research/CONTRACT_AUDIT_20260510.md` | Historical | No-secret contract audit snapshot after the Raven selected-agent bridge repair. Useful evidence, but canonical docs/tests own current behavior. |
| `research/RALPHIE_ARCLINK_ECOSYSTEM_GAP_REPAIR_STEERING.md` | Historical | Steering backlog and audit-derived rationale. |
| `research/*` | Historical | Research and phase notes unless a specific file says otherwise. |
| `docs/arclink/CREATIVE_BRIEF.md` | Speculative | Product voice and public copy direction; verify against implemented web/bot behavior before treating as shipped. |
| `docs/arclink/sovereign-control-node-symphony.md` | Proof-gated | Vision plus post-repair evidence/governance ledger. It names source-real and proof-gated seams, but `architecture.md`, `GAPS.md`, CANON, and focused tests remain the operating truth before treating any claim as shipped. |
| `FUTURE_SHARED_ARCLINK.md` | Speculative | North-star cross-sovereign-node sharing vision; today only single-control-plane share grants, Linked resources, the claim-nonce/share-request brokers, and the git fleet shared folder are built. The keypair/mesh/cross-node layer is unbuilt. |
| `docs/arclink/CHANGELOG.md` | Historical | Phase changelog. Useful context, but nearby canonical docs own current behavior. |
| `docs/arclink/document-phase-status.md` | Historical | Documentation phase audit status. |

## Stale Queue

No tracked doc is intentionally left in `Stale` status after the post-repair
refresh. Historical and proof-gated docs may still describe older phases or
future ambition; if a future audit finds stale operating guidance, add it to the
map with `Stale` status until the same change repairs or retires it.

## Maintenance Rule

When adding a new public doc, classify it here in the same change. If a doc is
kept only as background, mark it historical or speculative rather than quietly
letting it compete with canonical guidance.
