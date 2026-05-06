# ArcLink Native Workspace Plugin Implementation Plan

## Goal

Bring the native ArcLink Hermes workspace plugins home end to end:

- `ArcLink Drive`: Google Drive-like file management for Vault and Workspace roots.
- `ArcLink Code`: VS Code-like Explorer, editor, diff, and Source Control surface.
- `ArcLink Terminal`: persistent, revisit-able terminal sessions.

This is the controlling plan for the current Ralphie mission. Ralphie must not
route to terminal `done` while any unchecked item in this file or
`research/RALPHIE_ARCLINK_PLUGIN_WORKSPACES_STEERING.md` remains.

## Selected Architecture

Complete the existing native Hermes dashboard plugins backed by ArcLink Python
plugin APIs, plain JavaScript/CSS dashboard bundles, ArcLink install and
provisioning wrappers, Docker Compose runtime glue, and focused tests.

Rejected paths:

- Separate Next.js workspace app: useful for product/admin surfaces, but not a
  native Hermes dashboard plugin implementation.
- External-tool-first UX: Nextcloud, code-server, and terminal links may remain
  optional adapters, but they cannot replace native Drive, Code, and Terminal.
- Hermes core patches: explicitly outside the mission constraints.

## Current State

- [x] Slice 1: Plugin contracts, default installer wiring, and Terminal scaffold.
- [x] Slice 2A: Drive root/API hardening, upload conflict policy, partial batch
  failure surfacing, and symlink-escape pruning.
- [x] Deploy-readiness repairs for Tailnet URL persistence, plugin config
  preservation, and installer cache excludes are represented in the current
  worktree.
- [x] Code backend/API foundation now includes search, diff, git ignore,
  pull/push, confined file operations, theme controls, and targeted tests.
- [x] Slice 2B: Finish Drive browser proof.
- [x] Slice 3: Prove Code VS Code foundation over TLS.
- [x] Slice 4A: Implement managed-pty Terminal persistent sessions, polling
  transport, session UI, resource controls, root guard, and focused tests.
- [x] Workspace live-proof runner now has credential-gated default executors
  for Docker upgrade/reconcile, Docker health, and Drive/Code/Terminal
  desktop/mobile TLS browser proof.
- [x] Slice 5: Run Docker/TLS integration proof for Drive, Code, and Terminal.
- [x] Final hygiene, commit curation, optional deploy, and release handoff.

## Non-Negotiables

- Do not edit Hermes core.
- Keep behavior in ArcLink plugins, wrappers, generated config,
  Docker/service glue, and tests.
- Preserve deploy, onboarding, and domain-or-Tailscale ingress behavior.
- Keep all file and terminal operations confined to approved roots.
- Do not follow symlinks out of approved roots.
- Never expose tokens, `.env` values, deploy keys, OAuth credentials, bot
  tokens, private state, raw terminal logs, or host-local paths in UI, logs,
  docs, tests, API responses, proof notes, or commits.
- Do not fake Nextcloud sharing, VS Code parity, Terminal persistence, or live
  TLS proof.
- Default plugin UI theme is dark. Code must offer a one-click light theme.
- Risky actions must be confirmation-gated.

## Handoff Build Order

1. Stabilize the dirty worktree enough to isolate plugin, deploy, docs,
   proof-note, and Ralphie guidance edits without reverting unrelated changes.
2. Review the recorded Drive, Code, Terminal, Docker health, and TLS browser
   proof results for portability and freshness.
3. Preserve the existing portable proof notes and screenshot references without
   adding secrets, host-local paths, raw terminal scrollback, copied command
   transcripts, or private state.
4. Preserve docs so they match shipped behavior. Keep Nextcloud sharing,
   Monaco, tmux persistence, and streaming transport claims bounded to what is
   actually implemented and proven.
5. Rerun focused validation if any code, installer, Docker, provisioning, web,
   or proof-runner surface changes during handoff.
6. Curate scoped commits and prepare deploy-ready handoff.
7. If deploying, push the curated commits to the configured upstream branch and
   run the canonical host upgrade flow.

## Actionable BUILD Tasks

### 1. Verify Deploy-Readiness Baseline

- [x] Rerun focused Docker, deploy, plugin, shell, and hygiene tests for the
  current deploy-readiness changes.
- [x] Confirm Tailnet publication persists app URLs only after successful
  publication or records explicit unavailable status.
- [x] Confirm plugin installation preserves unknown config, comments, and
  future nested config while enabling ArcLink default plugins.
- [x] Confirm plugin install copies exclude `__pycache__/`, `*.pyc`, and other
  local generated caches.

### 2. Drive Finalization

- [x] Confirm Drive exposes `Vault` and `Workspace` as separate first-class
  parents in `/status`, API operations, and UI state.
- [x] Finish browser-visible breadcrumbs, root picker, list/grid view,
  sorting, multi-select, details/preview, context menus, upload, new
  folder/file, rename, move, duplicate/copy, favorite, trash, restore, and
  supported batch actions as one coherent desktop/mobile workflow.
- [x] Ensure partial batch failures are represented by API contracts and
  browser UI failure messaging.
- [x] Ensure destructive Drive actions use deliberate in-app confirmation.
- [x] Keep sharing disabled or clearly gated unless a real Nextcloud/WebDAV
  share adapter and tests are implemented.
- [x] Add or update focused tests for Drive API/UI contracts already present.
- [x] Add any missing Drive tests discovered while completing the final UX.
- [x] Run browser proof for Drive over TLS on desktop and mobile.

### 3. Code VS Code Foundation

- [x] Add a nested Explorer tree with filetype icons, tabs, dirty markers,
  rename, move, duplicate, delete/trash, context menus, and drag/drop
  confirmations.
- [x] Add Search panel and status bar.
- [x] Add diff endpoint/view so clicking a Source Control change opens a diff.
- [x] Add repo open/close controls, stage all, unstage all, discard all with
  strong confirmation, add to `.gitignore`, pull, push, conflict/error
  reporting, refresh, and last git result.
- [x] Evaluate Monaco. Ship a vendored Monaco bundle only if Hermes asset/CSP
  behavior works; otherwise document the blocker and harden the native editor.
- [x] Add dark/light theme toggle and explicit auto-save opt-in warning.
- [x] Add tests for Code file operations, git allowlists, diff behavior,
  confirmation gates, and root confinement.
- [x] Run browser proof for Code over TLS on desktop and mobile.

### 4. Terminal Persistent Sessions

- [x] Implement a persistent Terminal backend with stable session IDs,
  metadata, lifecycle states, workspace-root cwd, shell details, bounded
  scrollback, and atomic state writes.
- [x] Prove or add the Terminal runtime dependency path: install/use `tmux`
  in Docker and baremetal refresh paths, or make the ArcLink-managed pty
  fallback the documented tested backend.
- [x] Prefer tmux-backed sessions; if tmux is unavailable, implement and
  document an ArcLink-managed pty/session fallback.
- [x] Select a streaming/reconnect transport supported by the Hermes plugin
  host; if streaming is blocked, implement bounded polling and document the
  limitation.
- [x] Add dashboard UI with session list, new session, rename, folders/groups,
  reorder, move-to-folder, terminal pane, bounded polling output, input,
  reconnect after reload, and close/kill confirmation.
- [x] Add resource controls: max sessions, scrollback limit, redacted backend
  errors, and cleanup behavior.
- [x] Ensure Terminal never runs as unrestricted host root and stays in the
  deployment/user boundary.
- [x] Add tests for create/revisit/rename/close, scrollback bounds,
  unavailable backend, redaction, and reload reconnect.
- [x] Run browser proof for Terminal over TLS on desktop and mobile.

### 5. Integration And Proof

- [x] Run focused Python, shell, JavaScript, web, and browser checks for all
  touched surfaces.
- [x] Run the correct Docker upgrade/reconcile path for the target deployment.
- [x] Run Docker health and resolve any active failures.
- [x] Use browser automation over TLS to exercise Drive upload, rename,
  duplicate, drag move, trash/restore, and root switch.
- [x] Use browser automation over TLS to exercise Code open file, edit without
  auto-save, save, diff, stage/unstage, and commit-safe workflow.
- [x] Use browser automation over TLS to exercise Terminal create session,
  stream output, reload, revisit, rename, and close with confirmation.
- [x] Capture portable proof notes and screenshots without secrets, host-local
  paths, raw terminal scrollback, or copied command transcripts.
- [x] Update docs only after behavior exists and proof passes.

### 6. Commit And Deploy-Ready Handoff

- [x] Reconcile the broad dirty worktree into intentional commits without
  reverting user work.
- [x] Keep private state and generated caches, including plugin bytecode
  caches, out of commits.
- [x] Commit Ralphie guidance fixes separately from ArcLink product changes
  when both scopes are present.
- [x] Commit ArcLink product changes in scoped commits after tests pass.
- [x] Deployment was not requested for this build handoff; the canonical
  push-and-upgrade flow remains the next operator step if deployment is chosen.
- [x] Report final release, health, smoke/browser proof, and known residual
  risks without claiming a new live deploy.

Concrete handoff sequence:

1. Review `git status --short` and classify changes as Ralphie guidance,
   workspace plugin product code, deploy/provisioning/runtime glue,
   docs/proof notes, web/product surface, generated cache, or unrelated user
   work.
2. Remove generated bytecode/cache artifacts from the commit set without
   deleting user-owned source changes.
3. Rerun the validation floor for every classified code surface that remains
   staged for commit.
4. Stage and commit Ralphie guidance artifacts separately from ArcLink product
   code where both scopes are present.
5. Stage and commit workspace plugin, runtime glue, tests, and docs in
   reviewable scopes with no private state or local proof debris.
6. If deployment is requested, confirm the configured upstream branch is the
   production branch, push the commits, run `./deploy.sh upgrade`, then record
   release state, health, smoke, and browser proof results.

## Validation Floor

Run after touching workspace plugin code:

```bash
python3 -m py_compile \
  plugins/hermes-agent/arclink-drive/dashboard/plugin_api.py \
  plugins/hermes-agent/arclink-code/dashboard/plugin_api.py \
  plugins/hermes-agent/arclink-terminal/dashboard/plugin_api.py
python3 tests/test_arclink_plugins.py
node --check plugins/hermes-agent/arclink-drive/dashboard/dist/index.js
node --check plugins/hermes-agent/arclink-code/dashboard/dist/index.js
node --check plugins/hermes-agent/arclink-terminal/dashboard/dist/index.js
git diff --check
```

Run when installer, provisioning, Docker, or deploy code changes:

```bash
bash -n deploy.sh bin/*.sh test.sh ralphie.sh
python3 tests/test_arclink_agent_user_services.py
python3 tests/test_arclink_docker.py
python3 tests/test_arclink_provisioning.py
python3 tests/test_deploy_regressions.py
```

Run when web or product surface changes:

```bash
npm --prefix web test
npm --prefix web run lint
npm --prefix web run build
npm --prefix web run test:browser
```

For final live proof, run Docker upgrade/reconcile, Docker health, and TLS
browser proof for `/drive`, `/code`, and `/terminal` on desktop and mobile.

## Validation Criteria

PLAN is complete when:

- Required research artifacts are project-specific, portable, and current.
- No fallback placeholder marker exists.
- At least two implementation paths have been compared where uncertainty
  exists.
- BUILD can proceed without secrets for non-live implementation work.
- Live proof blockers, if any, are named precisely.
- Implementation tasks are actionable and testable.

Current PLAN status: complete for BUILD handoff. Remaining unchecked items are
BUILD/proof/handoff work, not planning blockers.

BUILD is complete only when:

- Every checkbox in this file and
  `research/RALPHIE_ARCLINK_PLUGIN_WORKSPACES_STEERING.md` is complete.
- Deterministic focused tests pass.
- Docker health passes on the target deployment.
- TLS browser proof demonstrates real Drive, Code, and Terminal workflows on
  desktop and mobile.
- Docs match shipped behavior and do not overclaim.
- Commits are scoped and contain no secrets, private state, generated caches,
  local paths, or command transcripts.
