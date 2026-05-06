# Document Phase Status

Generated: 2026-05-05 (updated after native Hermes workspace plugin slice)

## Documentation Audit

Project-facing ArcLink documentation has been refreshed against the current
codebase state: the SaaS foundation, Docker deployment wrapper, native Hermes
workspace plugins, public bot copy, and no-secret regression tests. Counts are
intentionally omitted here because this file is a status artifact; use the
repository and tests as source of truth when exact line/function counts matter.

### Files Updated (This Pass)

| File | Change | Rationale |
| --- | --- | --- |
| `docs/arclink/architecture.md` | Added native Hermes workspace plugin architecture, default installer behavior, Docker mount repair, tailnet app URL persistence, and current limitations | Drive, Code, and Terminal now ship through ArcLink plugins rather than Hermes core changes |
| `docs/arclink/foundation.md` | Added provisioning mount/access URL behavior and workspace plugin foundation notes | Operators and future agents need to know where Drive/Code/Terminal roots and plugin boundaries come from |
| `docs/arclink/foundation-runbook.md` | Added assumptions, ownership, current behavior, checks, and risks for workspace plugins and Docker repair paths | The runbook needed reproducible validation commands and explicit implemented-vs-scaffolded boundaries |
| `docs/arclink/operations-runbook.md` | Added Tailscale port-base env var and a Native Hermes Workspace Plugins runbook section | Docker health/reconcile now repairs dashboard mounts, refreshes plugins, publishes tailnet apps, and refreshes service health |
| `docs/docker.md` | Added Docker-mode workspace plugin mounts, repair behavior, and tailnet publication notes | Docker operators need the same plugin assumptions in the Docker deployment guide |
| `README.md` | Removed a local checkout-path example, added canonical shared-host layout, and noted default Hermes workspace plugins for enrolled users | The top-level operator guide should stay reproducible and reflect the current user-facing workspace surface |
| `docs/arclink/raven-public-bot.md` | Aligned Raven copy around onboarding agents into ArcLink instead of vessel-heavy public language | Public bot docs needed to match the current product promise and status wording |
| `docs/arclink/CREATIVE_BRIEF.md` | Updated pricing/offer copy, public CTA labels, and workspace wording around ArcLink Drive/Code | Brand and product-copy source notes needed to match the current surface and avoid stale pricing |
| `docs/arclink/brand-system.md` | Reframed the product promise around private AI agents and workflows | Brand rails needed to match the current public copy direction |
| `docs/arclink/professional-finish-gate.md` | Updated finish-gate wording from visible systems to visible workflows | The gate should evaluate the current product language consistently |
| `docs/arclink/CHANGELOG.md` | Added a Native Hermes Workspace Plugins entry with current behavior and rationale | Project-facing release history was stale after the plugin slice |
| `plugins/hermes-agent/arclink-drive/README.md` | Expanded ownership, backend, behavior, assumptions, runbook, and boundaries | The plugin is now project-facing documentation for Drive maintainers |
| `plugins/hermes-agent/arclink-code/README.md` | Expanded ownership, workspace, editor/git behavior, assumptions, runbook, and boundaries | The Code plugin now has source-control behavior and hash-guarded save semantics to document |
| `plugins/hermes-agent/arclink-terminal/README.md` | Updated for the managed-pty backend, polling limitation, root guard, and future tmux path | The Terminal tab now has tested persistent sessions but still needs TLS proof |
| `research/RALPHIE_ARCLINK_PLUGIN_WORKSPACES_STEERING.md` | Updated the active steering current-state notes for Terminal managed-pty sessions, default plugin install set, and repaired deploy-readiness checklist | Future Ralphie runs should not restart from stale Tailnet, installer, or Terminal assumptions |
| `research/ARCLINK_ARCHITECTURE_MAP.md` | Removed local workspace provenance from the source note | Research markdown should stay reproducible outside this checkout |
| `docs/arclink/document-phase-status.md` | Refreshed this audit status and risks | Prior status described the scale-operations/web-lint pass |

### Files Updated (Prior Passes)

| File | Change | Rationale |
| --- | --- | --- |
| `docs/arclink/CHANGELOG.md` | P9 admin dashboard, P10 browser proof, P11 fake E2E, P12 live scaffold | Earlier landed work |
| `research/COVERAGE_MATRIX.md` | P11 LANDED, P12 SCAFFOLDED, refreshed metrics | P11 complete; P12 externally blocked |
| `docs/arclink/architecture.md` | Updated Current Limitations for P9-P12 status | Was stale on admin dashboard and E2E |
| `docs/arclink/foundation-runbook.md` | Added E2E test commands to runbook validation | E2E tests now exist |
| `IMPLEMENTATION_PLAN.md` | P13-16 marked COMPLETE in BUILD Tasks | Items landed |

### Additional Files Reviewed (No Changes Needed)

| File | Verdict |
| --- | --- |
| `docs/arclink/secret-checklist.md` | Current. Secret inventory, handling rules, verification command. |
| `docs/arclink/ingress-plan.md` | Current. Domain/Tailscale ingress, DNS layout, Traefik, SSH, drift, teardown. |
| `docs/arclink/backup-restore.md` | Current. Backup targets, schedule, restore, DR, retention. |
| `docs/arclink/alert-candidates.md` | Current. Critical/warning/info alert signals with sources. |
| `docs/arclink/data-safety.md` | Current. Isolation, volumes, secrets, teardown safeguards. |
| `docs/arclink/live-e2e-secrets-needed.md` | Current. All credential blockers named. |
| `config/env.example` | Current. All ArcLink env vars with comments. |

## Open Questions

- Live Docker Compose execution remains unverified until operator-gated host
  credentials are available.
- Production 12 is not live-proven yet; the scaffold is ready, but the full
  live journey needs credentials and an explicit credentialed run.
- External credential sets remain absent (Stripe, Chutes, Telegram, Discord,
  host, and the selected Cloudflare-domain or Tailscale ingress mode).
- The action worker has code-level batch and stale-recovery entrypoints, but no
  documented production service/timer unit is live yet.
- ArcLink Terminal has managed-pty persistent sessions with bounded polling
  output. True streaming and tmux backend validation remain future work; the
  workspace Docker/TLS proof runner has passed desktop and mobile checks for
  Drive, Code, and Terminal.
- ArcLink Drive and Code are first-generation native plugins. They are useful
  local/WebDAV workspace surfaces, but broad Google Drive and VS Code parity
  remains future work.

## Risks

- Documentation correctness depends on the no-secret suite continuing to pass.
  If tests diverge from docs, the foundation-runbook validation
  section lists the exact commands to reconfirm.
- Provisioning resource limits and healthchecks are rendered in Compose intent
  but have not been validated against a live Docker Compose execution yet
  (blocked on external credentials).
- Scale operations placement is intentionally deterministic and capacity-based,
  not a replacement for an external scheduler. Live worker automation should
  keep the same executor gates and secret rejection rules.
- Docker tailnet app publication depends on the host Tailscale CLI and tailnet
  policy. The runbook documents that absence of the CLI skips publication while
  health continues.
- WebDAV delete behavior is provider-direct, unlike local Drive delete which is
  recoverable through `.arclink-trash`; UI confirmations must preserve that
  distinction.

## Verdict

Project-facing docs are clear enough to proceed with no-secret development and
operator rehearsal. Production 12 remains externally blocked by credentials and
a deliberate live run. Workspace plugin docs now describe current Drive/Code
behavior, Terminal's managed-pty boundary, Docker repair/runbook steps, the
completed workspace Docker/TLS proof, and the reason ArcLink keeps this
behavior in plugins rather than Hermes core. All updated artifacts are
reproducible and free of local context: no operator names, live hostnames,
tokens, or copied `.env` values.
