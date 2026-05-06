# Document Phase Status

Generated: 2026-05-06 (alignment audit: API routes, module map, Terminal
streaming, stale metrics)

## Documentation Audit

Project-facing ArcLink documentation has been audited and corrected against the
current codebase state: Python control-plane modules, test coverage, web
surfaces, native Hermes workspace plugins, hosted API route table, and
architecture module map. This pass focused on closing gaps between landed code
and documentation rather than adding brittle inventory counts.

### Files Updated (This Pass)

| File | Change | Rationale |
| --- | --- | --- |
| `docs/API_REFERENCE.md` | Added missing `GET /openapi.json` (public) and `GET /admin/scale-operations` (admin) routes; added scale-operations to the web client integration table | These routes exist in the hosted API `_ROUTES` dict but were absent from the reference doc |
| `docs/arclink/architecture.md` | Added 6 missing modules to the module map (`arclink_boundary`, `arclink_host_readiness`, `arclink_diagnostics`, `arclink_live_runner`, `arclink_live_journey`, `arclink_evidence`); updated arclink-terminal description from "scaffolded only" to managed-pty persistent sessions with same-origin SSE streaming and polling fallback; expanded the route table from representative rows to the canonical hosted API route catalog matching `_ROUTES` in `arclink_hosted_api.py`; fixed stale route paths (`/admin/login` -> `/auth/admin/login`, `/stripe/webhook` -> `/webhooks/stripe`) | Module map and route table were incomplete and had path discrepancies vs. the actual code |
| `docs/arclink/document-phase-status.md` | Replaced prior status with this current audit | Prior status described the workspace plugin pass, not the current alignment audit |
| `PROMPT_document.md` and `ralphie.sh` | Strengthened the document phase prompt so it self-directs from repo context and avoids interactive "what should I document?" stalls | Ralphie document attempt 1 produced no artifact; future document phases should inspect plan/backlog/docs and either update docs or record why they are current |
| `plugins/hermes-agent/arclink-terminal/README.md` | Updated Terminal transport notes for same-origin SSE streaming with polling fallback | Terminal now matches the desired persistent, kept-current dashboard session behavior more closely |
| `tests/test_arclink_plugins.py` | Updated Terminal status/UI assertions for `streaming_output`, SSE mode, and polling fallback | Tests now lock the streaming terminal contract instead of the old polling-only contract |

### Files Updated (Prior Passes)

| File | Change | Rationale |
| --- | --- | --- |
| `docs/arclink/architecture.md` | Native Hermes workspace plugin architecture, installer, Docker repair, tailnet, limitations | Plugin workspace pass |
| `docs/arclink/foundation.md` | Provisioning mount/access URL behavior, workspace plugin notes | Plugin workspace pass |
| `docs/arclink/foundation-runbook.md` | Workspace plugin assumptions, ownership, checks, risks | Plugin workspace pass |
| `docs/arclink/operations-runbook.md` | Tailscale port-base env var, Native Hermes Workspace Plugins section | Plugin workspace pass |
| `docs/arclink/CHANGELOG.md` | P9-P12, P13-P16, scale operations, web lint, workspace plugin entries | All landed work |
| Plugin READMEs (Drive, Code, Terminal) | Ownership, behavior, assumptions, runbook, boundaries | Plugin workspace pass |
| `docs/docker.md` | Docker-mode plugin mounts, repair, tailnet publication | Plugin workspace pass |

### Files Reviewed (No Changes Needed)

| File | Verdict |
| --- | --- |
| `docs/arclink/CHANGELOG.md` | Current. Native Hermes Workspace Plugins entry is the latest; no new features since. |
| `docs/arclink/operations-runbook.md` | Current. All 14 sections match landed modules. |
| `docs/arclink/foundation.md` | Current. Workspace plugin, executor, provisioning, bot adapter notes match code. |
| `docs/arclink/foundation-runbook.md` | Current. Validation commands match test file list. |
| `docs/arclink/secret-checklist.md` | Current. Secret inventory and handling rules. |
| `docs/arclink/ingress-plan.md` | Current. Domain/Tailscale ingress, DNS layout, Traefik, SSH, drift, teardown. |
| `docs/arclink/backup-restore.md` | Current. Backup targets, schedule, restore, DR, retention. |
| `docs/arclink/alert-candidates.md` | Current. Critical/warning/info alert signals with sources. |
| `docs/arclink/data-safety.md` | Current. Isolation, volumes, secrets, teardown safeguards. |
| `docs/arclink/live-e2e-secrets-needed.md` | Current. All credential blockers named. |
| `docs/arclink/live-e2e-evidence-template.md` | Current. Evidence collection template. |
| `config/env.example` | Current. All ArcLink env vars with comments. |
| `docs/arclink/brand-system.md` | Current. Product promise wording matches. |
| `docs/arclink/CREATIVE_BRIEF.md` | Current. Pricing/offer copy matches. |
| `docs/arclink/professional-finish-gate.md` | Current. Finish-gate wording matches. |

## Open Questions

- Live Docker Compose execution remains unverified until operator-gated host
  credentials are available.
- Production 12 is not live-proven yet; the scaffold is ready, but the full
  live journey needs credentials and an explicit credentialed run.
- External credential sets remain absent (Stripe, Chutes, Telegram, Discord,
  host, and the selected Cloudflare-domain or Tailscale ingress mode).
- The action worker has code-level batch and stale-recovery entrypoints, but no
  documented production service/timer unit is live yet.
- ArcLink Terminal has managed-pty persistent sessions with same-origin SSE
  output streaming and bounded polling fallback. tmux backend validation
  remains future work.

## Risks

- Documentation correctness depends on the no-secret suite continuing to pass.
  If tests diverge from docs, the foundation-runbook validation section lists
  the exact commands to reconfirm.
- Provisioning resource limits and healthchecks are rendered in Compose intent
  but have not been validated against a live Docker Compose execution yet
  (blocked on external credentials).
- Scale operations placement is intentionally deterministic and capacity-based,
  not a replacement for an external scheduler.
- Docker tailnet app publication depends on the host Tailscale CLI and tailnet
  policy.
- WebDAV delete behavior is provider-direct, unlike local Drive delete which is
  recoverable through `.arclink-trash`.

## Verdict

Project-facing docs are aligned with the current codebase. The API reference
now includes the hosted OpenAPI and scale-operations routes that were missing.
The architecture module map now lists all modules relevant to ArcLink SaaS
behavior including host readiness, diagnostics, live proof, evidence, and
boundary helpers. The gaps were completeness and accuracy in existing artifacts,
plus Terminal transport language after the SSE upgrade. Production 12 remains
externally blocked.
