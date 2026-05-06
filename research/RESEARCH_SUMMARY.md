# Research Summary

<confidence>97</confidence>

## Objective

Prepare BUILD handoff for the active ArcLink native workspace plugin mission:

- `ArcLink Drive`: Google Drive-like file management for Vault and Workspace roots.
- `ArcLink Code`: VS Code-like Explorer, editor, diff, and Source Control surface.
- `ArcLink Terminal`: persistent, revisit-able terminal sessions inside Hermes.

All implementation must stay in ArcLink-owned Hermes plugins, wrappers,
generated config, Docker/service glue, and focused tests. Hermes core changes
remain out of scope.

## Current Finding

ArcLink already has the correct extension boundary for this mission. The active
workspace surfaces are native Hermes dashboard plugins under
`plugins/hermes-agent/`:

- `arclink-drive` registers the `/drive` dashboard tab and has a Python API,
  JavaScript dashboard bundle, scoped CSS, manifest, plugin metadata, and
  README. Its backend exposes Vault and Workspace roots, confined local file
  operations, upload conflict policy, copy/duplicate, trash/restore, favorites,
  bounded preview/search, root-keyed metadata, per-item batch results, and
  disabled sharing capability flags.
- `arclink-code` registers the `/code` dashboard tab and has a Python API,
  JavaScript dashboard bundle, scoped CSS, manifest, plugin metadata, and
  README. Its backend exposes workspace status, tree/list/open/save, hash-based
  conflicting-save protection, bounded search, repo discovery, git status,
  diff, stage, unstage, discard with explicit confirmation, commit,
  `.gitignore`, pull, push, and confined rename/move/duplicate/trash/restore
  operations. Its browser bundle contains the Explorer/Search/Source Control
  split, diff view, tabs/dirty state, status bar, theme toggle, and manual-save
  warning.
- `arclink-terminal` registers the `/terminal` dashboard tab and has a
  managed-pty backend with sanitized status, workspace-root cwd, shell/runtime
  availability, stable session IDs, persisted metadata, bounded scrollback,
  polling output, input, rename/folder/reorder controls, confirmation-gated
  close, and an unrestricted-root startup guard.
- `bin/install-arclink-plugins.sh` is the canonical delivery path for Hermes
  homes and is covered for default plugin enablement, legacy alias pruning,
  config preservation, and generated-cache exclusion.
- Docker/provisioning code carries dashboard, Vault, and Workspace runtime
  signals. The active backlog marks Docker/TLS proof, portable proof-note
  capture, and documentation alignment complete. The remaining BUILD handoff
  work is commit hygiene, optional deployment, and final release/health/proof
  reporting.
- The deterministic stack snapshot now ranks the Python/shell ArcLink control
  plane with native Hermes dashboard plugins as the primary stack at 94/100
  confidence. Node/Next is present as a supporting product/admin and browser
  proof surface, not the primary implementation path for this mission.

This is completion and handoff work on an existing architecture, not greenfield
discovery.

## Implementation Path Comparison

| Path | Strengths | Weaknesses | Decision |
| --- | --- | --- | --- |
| Complete existing native Hermes dashboard plugins | Directly satisfies the mission, preserves Hermes core, reuses current Python/JS/CSS surfaces, and works with current install/provisioning rails. | Requires careful proof, documentation, and commit curation across a broad dirty tree. | Selected. |
| Build a separate Next.js workspace app | Strong frontend tooling and full product-shell control. | Not native Hermes dashboard plugins and duplicates routing/runtime concerns. | Rejected for this mission. |
| Use external tools as the primary UX | Nextcloud, code-server, and terminal links are mature and fast to expose. | Fails native Drive/Code/Terminal goals and risks fake parity or fake sharing claims. | Keep only as optional links/adapters. |
| Patch Hermes dashboard core | Could expose missing host features quickly. | Violates constraints and creates upstream upgrade debt. | Rejected. |

## Uncertainty Comparison

| Area | Option A | Option B | Planning decision |
| --- | --- | --- | --- |
| Terminal backend | tmux-backed sessions | ArcLink-managed pty fallback | Managed pty is the selected shipped path for this slice because it is implemented and covered. Keep tmux as a future backend candidate only after Docker and baremetal install paths prove it. |
| Terminal transport | WebSocket/SSE streaming | Bounded polling with POSTed input | Bounded polling is the selected shipped path because the existing plugin API supports it without adding a streaming rail. |
| Code editor | Harden current native editor | Vendor Monaco | Do not claim Monaco parity. Ship the native editor unless Monaco workers/assets/CSP are proven inside the Hermes plugin host. |
| Drive sharing | Disabled/gated capability | Nextcloud/WebDAV share adapter | Keep sharing disabled until a real adapter and tests exist. Do not ship synthetic share links. |

## Assumptions

- Hermes dashboard plugin manifests continue to load `dashboard/plugin_api.py`,
  `dashboard/dist/index.js`, and `dashboard/dist/style.css`.
- Plain JavaScript/CSS bundles are acceptable for the current plugin mission.
- Vault and Workspace remain separate first-class Drive roots.
- Code remains manual-save by default. Auto-save, if added, must be explicit
  opt-in with visible warning.
- Terminal execution must stay inside the deployment/user boundary with bounded
  state, redacted errors, and explicit lifecycle controls.
- Portable proof notes can summarize outcomes without embedding screenshots,
  command transcripts, host-local paths, raw terminal scrollback, or secrets.

## Planning Verdict

The planning phase is ready for BUILD handoff. Required artifacts are
project-specific and portable, no fallback placeholder marker is present in the
implementation plan, and no planning-only blocker remains.

## Build Handoff

Proceed against the remaining unchecked handoff items in
`IMPLEMENTATION_PLAN.md` and
`research/RALPHIE_ARCLINK_PLUGIN_WORKSPACES_STEERING.md`:

1. Reconcile the broad dirty worktree into scoped commits without reverting
   unrelated user work.
2. Keep private state, generated caches, bytecode, secrets, and local proof
   debris out of commits.
3. Keep Ralphie guidance commits separate from ArcLink product commits where
   both scopes remain present.
4. If deploying, push to the configured upstream branch before the canonical
   `./deploy.sh upgrade` flow.
5. Report final release, health, smoke/browser proof, and residual risks.

## Remaining Risks

- The worktree is broad and dirty; BUILD must preserve unrelated edits and
  curate changes intentionally.
- The current workspace proof is only current while the plugin, Docker,
  provisioning, proof-runner, and docs surfaces remain unchanged after the
  recorded pass.
- Nextcloud sharing is not implemented and must remain disabled or genuinely
  adapter-backed.
- Monaco and streaming terminal transport remain optional future improvements,
  not current completion requirements.
- Git pull, push, discard, and discard-all need continued strict allowlists,
  confirmations, redaction, timeout handling, and proof notes.
- Proof artifacts and final reports must stay portable and secret-free.
