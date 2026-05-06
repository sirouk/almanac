# Ralphie Steering: ArcLink Native Workspace Plugins

Status: active Ralphie mission, bring-home backlog.

Use this file as the controlling backlog for the next Ralphie run. This mission
supersedes the older scale-operations and credentialed live-proof loops for the
current operator focus. Production live proof remains externally blocked by
credentials; do not chase that blocker during this mission.

Ralphie must not route to terminal `done` while any unchecked task in this file
or `IMPLEMENTATION_PLAN.md` remains. Keep future work that should block `done`
as unchecked Markdown checklist items, not prose-only notes.

## Machine-Readable Bring-Home Backlog

- [x] Slice 1: Install `ArcLink Drive`, `ArcLink Code`, and `ArcLink Terminal`
  as native Hermes dashboard plugins with redacted status contracts.
- [x] Slice 2A: Harden Drive root-aware APIs, upload conflicts, batch
  partial-failure surfacing, and symlink-escape pruning.
- [x] Repair deploy-readiness risks before live proof:
  - [x] Persist Tailnet app URLs only after successful `tailscale serve`, or
    record explicit unavailable status.
  - [x] Add regression coverage for failed Tailnet publication.
  - [x] Harden plugin YAML updates so comments and unknown nested config
    survive plugin install/enable work.
  - [x] Exclude `__pycache__/`, `*.pyc`, and generated local caches from
    plugin installation copies.
- [x] Complete Drive final UX and TLS browser proof:
  - [x] Vault and Workspace root switching is visible and tested.
  - [x] Breadcrumbs, list/grid, sorting, multi-select, details/preview, context
    menus, upload, new folder/file, rename, move, duplicate/copy, favorite,
    trash, restore, and batch actions work in the browser.
  - [x] Risky Drive actions use deliberate in-app confirmations.
  - [x] Sharing is disabled or backed by a real tested adapter.
  - [x] Desktop and mobile browser proof passes over TLS.
- [x] Complete Code VS Code foundation:
  - [x] Nested Explorer tree, icons, tabs, dirty markers, context menus, and
    safe file operations.
  - [x] Search panel, status bar, richer Source Control actions,
    `.gitignore`, pull, push, conflict reporting, and last git result.
  - [x] Source Control changed-file clicks open a bounded backend diff view.
  - [x] Monaco is shipped after asset/CSP proof or documented as blocked with
    a hardened native editor.
  - [x] Dark/light theme and explicit auto-save opt-in warning.
  - [x] Desktop and mobile browser proof passes over TLS.
- [x] Complete Terminal persistent sessions:
  - [x] tmux-backed or documented managed-pty backend with stable session IDs.
  - [x] Session metadata, lifecycle states, bounded scrollback, bounded polling
    output, input, reload reconnect, rename, folders/groups, reorder, and
    close/kill confirmation.
  - [x] Resource limits and redacted backend errors.
  - [x] Desktop and mobile browser proof passes over TLS.
- [x] Complete integration proof:
  - [x] Focused Python, shell, JavaScript, web, and browser checks pass.
  - [x] Docker upgrade/reconcile passes.
  - [x] Docker health passes.
  - [x] TLS browser proof exercises real Drive, Code, and Terminal workflows.
- [x] Complete handoff:
  - [x] Docs match shipped behavior and do not overclaim.
  - [x] Broad dirty worktree is curated into scoped commits.
  - [x] Private state, caches, secrets, and command transcripts are absent from
    commits.
  - [x] Final report names release/health/browser proof and residual risks.

## Mission

Build ArcLink's native Hermes dashboard workspace suite:

- `ArcLink Drive`: a Google Drive-grade file manager for agent knowledge and
  workspaces.
- `ArcLink Code`: a VS Code-grade code workspace and source-control surface.
- `ArcLink Terminal`: persistent terminal sessions inside the Hermes
  dashboard.

The result must feel native to Hermes, fit inside the Hermes dashboard on real
desktop and mobile viewports, and remain implemented through ArcLink plugins,
wrappers, services, and generated config rather than Hermes core edits.

## Current State

Known landed foundation:

- `arclink-drive` and `arclink-code` Hermes dashboard plugins exist under
  `plugins/hermes-agent/`.
- `arclink-terminal` now uses a documented managed-pty backend with stable
  session IDs, persisted metadata, bounded scrollback, polling output, input,
  rename/folder/reorder controls, close confirmation, and an unrestricted-root
  startup guard.
- `arclink-managed-context`, `arclink-drive`, `arclink-code`, and
  `arclink-terminal` are installed by the ArcLink plugin installer for
  refreshed agents.
- `bin/arclink-live-proof --journey workspace --live` now has default
  credential-gated executors for Docker upgrade/reconcile, Docker health, and
  Playwright desktop/mobile proof of the native Drive, Code, and Terminal
  dashboard routes.
- Docker deployment mounts the vault and workspace into the Hermes dashboard
  container.
- Docker health/reconcile records Tailnet app URLs only after all per-deployment
  app publications succeed; failures store explicit unavailable metadata instead
  of stale app URLs.
- The plugin installer preserves unknown plugin config sections, prunes legacy
  aliases, and excludes generated Python/cache artifacts while copying plugin
  directories.
- Workspace TLS browser proof is checked complete for Drive, Code, and
  Terminal desktop/mobile routes in the active backlog.
- Drive currently supports local-vault listing, search, favorites, upload,
  rename, move, trash, restore, preview, download, right-click actions, and
  confirmed drag moves.
- Code currently supports native file listing/editing, manual save with hash
  conflict protection, bounded search, backend diff, confined file operations,
  repo scanning, source-control groups, stage/unstage, discard, commit,
  `.gitignore`, pull, push, status reporting, theme controls, and an
  Explorer/Search/Source Control split.

Known remaining handoff work:

- Portable proof notes and sanitized screenshot references are recorded in
  `research/BUILD_COMPLETION_NOTES.md` from the passing workspace proof.
- Docs now describe shipped behavior without overclaiming Nextcloud sharing,
  Monaco parity, tmux persistence, or streaming terminal transport.
- The broad dirty worktree still needs scoped commit curation without reverting
  unrelated user work.

Content status from the active checklist:

- Drive final UX and desktop/mobile TLS browser proof are checked complete.
- Code VS Code foundation and desktop/mobile TLS browser proof are checked
  complete.
- Terminal managed-pty persistent sessions and desktop/mobile TLS browser proof
  are checked complete.
- Docker upgrade/reconcile, Docker health, and integrated TLS browser proof are
  checked complete.

## Non-Negotiable Rules

- Do not modify Hermes core dashboard code to make ArcLink behavior work.
- Preserve Hermes plugin boundaries and use:
  - `plugins/hermes-agent/arclink-drive/`
  - `plugins/hermes-agent/arclink-code/`
  - `plugins/hermes-agent/arclink-terminal/`
  - `bin/install-arclink-plugins.sh`
  - ArcLink Docker/provisioning wrappers and tests as needed.
- Keep the UI native to the Hermes dashboard: same broad visual language,
  compact density, dashboard-safe spacing, no marketing layout, no oversized
  hero treatment, no nested-card clutter.
- Default theme is dark. Code must also offer a one-click light theme option.
- Every viewport must fit without incoherent overlap. Test desktop and mobile.
- Risky actions require deliberate confirmation:
  - delete/trash
  - destructive discard
  - drag/drop moves
  - terminal close/kill
  - overwrite
  - pull/rebase/push if it can alter remote/local state
- Prefer trash/restore over irreversible delete where possible.
- Never expose tokens, secrets, deploy keys, OAuth credentials, bot tokens, or
  `.env` values in plugin UI, logs, docs, tests, API responses, or terminal
  state.
- All file operations must remain confined to allowed roots.
- Do not follow symlinks out of allowed roots.
- Do not run arbitrary backend shell commands except through the Terminal
  session boundary, and make the terminal runtime explicit and auditable.
- Do not auto-save editor content by default.
- Do not claim Nextcloud sharing is complete until the backend has a real
  implementation or a clearly gated adapter.

## Shared Product Foundation

Before deeply expanding each plugin, create or consolidate shared patterns
where they reduce real duplication:

- Hermes-native dark UI tokens for plugin pages.
- Responsive two/three-pane layout primitives that fit the Hermes dashboard.
- File/folder icons and filetype badges.
- Context menu primitive.
- Confirmation modal primitive that can require:
  - simple accept/cancel
  - exact-name typing
  - destructive action text such as `delete` or `discard`
- Drag/drop affordance pattern with visible target states and post-drop
  confirmation.
- Keyboard support:
  - Escape closes menus/dialogs.
  - Enter confirms safe focused actions.
  - Delete/Backspace initiate risky action confirmation, not immediate action.
  - Cmd/Ctrl+S saves Code only when a file is dirty.
- Toast/status region for failures and successful actions.
- Explicit loading/empty/error states.
- API error detail that is helpful but redacted.

Only add shared abstractions when they make the plugin work easier and safer.
Do not create a large design system detour before shipping product behavior.

## ArcLink Drive Target

Goal: provide a Google Drive-like experience for both agent knowledge and code
workspace files.

### Roots And Navigation

Drive must show separate first-class parents:

- `Vault`: the deployment/user knowledge vault.
- `Workspace`: the code workspace mounted for ArcLink Code.

Expected behavior:

- Root picker or sidebar shows both parents.
- Breadcrumbs show `Drive / Vault / ...` or `Drive / Workspace / ...`.
- Users can search within the selected root and later across both roots.
- Users can browse list and grid views.
- Sorting by name, type, modified, size.
- Folders before files unless the selected sort explicitly says otherwise.
- Details panel for selected item(s).
- Preview panel for common text/markdown/code files and common media where safe.
- Starred/favorites view.
- Recent activity view when metadata is available.
- Trash view for local-vault local deletes.

### File Management

Required file operations:

- Upload via file picker.
- Upload via browser drag/drop.
- New folder.
- New text/markdown file where backend supports it.
- Rename.
- Move.
- Copy or duplicate.
- Star/unstar.
- Download.
- Trash/delete with double confirmation for destructive paths.
- Restore from trash.
- Multi-select and batch actions.
- Right-click context menu on files, folders, background, and selected group.
- Drag/drop files/folders into folders with confirmation after drop.
- Drag/drop into empty folder background with confirmation.
- Conflict handling for overwrite/duplicate names.

### Future Sharing

Build with the future Nextcloud sharing surface in mind:

- Model share intent at the UI/API contract level without leaking secrets.
- Leave a clean adapter boundary for WebDAV/OCS sharing APIs.
- Future share targets should support:
  - private link
  - user/group share if Nextcloud users/groups exist
  - expiration
  - permission level
  - revoke
  - show existing shares
- If sharing is not implemented in the current slice, display no fake share
  claims. Use disabled/gated UI only if it makes the future contract clearer.

### Drive Backend Expectations

- Continue supporting local-vault backend.
- Preserve Nextcloud/WebDAV compatibility where already present.
- Add Workspace root support with equivalent root confinement.
- Keep metadata in Hermes/ArcLink state files with atomic writes.
- Bound preview sizes.
- Keep search bounded and non-blocking.
- Return capability flags from `/status`.

## ArcLink Code Target

Goal: provide a VS Code-like experience inside the Hermes dashboard, not just a
file textarea.

### Workbench Layout

Required UI shape:

- Left activity bar or segmented navigation with:
  - Explorer
  - Search
  - Source Control
  - Terminal link/panel when Terminal plugin exists
- Explorer tree with nested folders, collapse/expand, file icons, and selected
  state.
- Editor area with tabs.
- Status bar with current file, dirty state, language, branch/repo when known.
- File menu or compact command menu for common actions.
- Dark theme by default.
- Light theme toggle.
- Auto Save option must be opt-in and must show a warning before enabling.

### File Operations

Required Code file operations:

- New file.
- New folder.
- Rename.
- Move.
- Copy/duplicate.
- Delete/trash with confirmation.
- Drag/drop in Explorer with confirmation.
- Right-click context menu for file, folder, editor tab, and empty Explorer
  background.
- Open file in editor tab.
- Close tab.
- Dirty tab marker.
- Save.
- Save As when applicable.
- Revert file with confirmation.
- Detect external disk changes and avoid silent overwrite.

### Editor

Preferred path:

- Use Monaco Editor if it can be bundled into the plugin without breaking
  Hermes dashboard loading, CSP, or asset routing.

Fallback path:

- Keep a hardened native textarea editor while documenting why Monaco could not
  ship in the current slice.

Editor requirements:

- Manual save by default.
- Cmd/Ctrl+S save.
- Line numbers if Monaco or a safe local implementation supports it.
- Syntax highlighting if Monaco or another safe local package supports it.
- Large-file guard and binary-file guard.
- No auto-save by default.
- Optional auto-save with warning and obvious enabled state.

### Source Control

Required VS Code-like Source Control behavior:

- Open and close repositories under the workspace.
- Show repository list/tree.
- Show current branch.
- Show changed files grouped by:
  - staged
  - unstaged changes
  - untracked
  - conflicts
- Clicking a changed file opens a diff view, not only the current file.
- Stage file.
- Stage all.
- Unstage file.
- Unstage all.
- Discard file with confirmation.
- Discard all with stronger confirmation.
- Add untracked file/folder to `.gitignore`.
- Commit staged changes with message.
- Pull with confirmation and conflict reporting.
- Push with confirmation and remote/error reporting.
- Refresh status.
- Show last git command result.
- Keep git commands allowlisted and root-confined.

Future source-control stretch:

- Branch switch/create.
- Git log.
- Inline diff hunks.
- Stage selected hunks.
- Merge/rebase conflict helper.

## ArcLink Terminal Target

Goal: provide persistent, revisit-able terminal sessions inside the Hermes
dashboard.

### Product Shape

Required layout:

- Left session list.
- New session button.
- Session folders or groups.
- Rename session.
- Reorder sessions by drag/drop.
- Move sessions into folders by drag/drop with confirmation.
- Close/kill session with confirmation.
- Main terminal pane.
- Deep scrollback.
- Streaming output.
- Clear indication of running/exited/error state.
- Current working directory and shell shown in session details.
- Reconnect to an existing session after dashboard reload.

### Persistence

Terminal sessions should persist across dashboard refreshes and service restarts
where the selected backend permits it.

Preferred backend:

- Use a per-deployment tmux server inside the deployment/Hermes dashboard
  service boundary or an ArcLink-managed companion service.

Requirements:

- Sessions are named and mapped to stable IDs.
- Scrollback is captured to bounded state/log files.
- Session metadata is stored atomically in ArcLink/Hermes state.
- Input and output stream over a dashboard-safe channel.
- If Hermes plugin APIs cannot support WebSockets, implement a robust fallback
  using bounded polling/SSE plus POSTed input, and document the tradeoff.
- Terminal runs from the workspace root by default.
- Terminal never starts as host root unless the deployment model explicitly and
  safely scopes it. Prefer the deployment/user context.

### Terminal Backend Safety

- Explicit command execution boundary.
- No secret rendering in status/debug endpoints.
- Redacted logs for backend errors.
- Resource controls where possible:
  - max sessions
  - bounded scrollback
  - idle timeout policy, if any
  - session cleanup controls
- Clear lifecycle states:
  - starting
  - running
  - exited
  - failed
  - detached

## Expected File-Level Outputs

Ralphie should prefer existing local ownership boundaries:

- `plugins/hermes-agent/arclink-drive/dashboard/plugin_api.py`
- `plugins/hermes-agent/arclink-drive/dashboard/dist/index.js`
- `plugins/hermes-agent/arclink-drive/dashboard/dist/style.css`
- `plugins/hermes-agent/arclink-code/dashboard/plugin_api.py`
- `plugins/hermes-agent/arclink-code/dashboard/dist/index.js`
- `plugins/hermes-agent/arclink-code/dashboard/dist/style.css`
- `plugins/hermes-agent/arclink-terminal/`
- `bin/install-arclink-plugins.sh`
- `bin/refresh-agent-install.sh`
- `bin/install-agent-user-services.sh`
- `python/arclink_provisioning.py`
- `bin/arclink-docker.sh`
- `tests/test_arclink_plugins.py`
- `tests/test_arclink_agent_user_services.py`
- `tests/test_arclink_docker.py`
- `tests/test_deploy_regressions.py`
- browser tests if the Hermes plugin dashboard has a local test harness

Do not scatter plugin behavior into unrelated SaaS landing-page code.

## Suggested Build Order

### Slice 1: Contracts And Shared UX Foundations

- Update plugin API contracts for Drive roots, Code source-control/diff needs,
  and Terminal sessions.
- Add `arclink-terminal` plugin scaffold and default installer wiring.
- Add focused tests proving all three plugins install and expose safe status.
- Create shared confirmation/context-menu/file-icon patterns only if useful.

Acceptance:

- All three plugins are installed by default.
- Hermes shows `ArcLink Drive`, `ArcLink Code`, and `ArcLink Terminal`.
- Status APIs are redacted and capability-driven.
- Focused plugin install/API tests pass.

### Slice 2: Drive Google Drive Foundation

- Add Vault and Workspace roots.
- Add breadcrumbs, list/grid, multi-select, details, sort, and batch actions.
- Harden drag/drop, context menus, trash, restore, rename, move, duplicate.
- Keep future share adapter cleanly represented but do not fake sharing.

Acceptance:

- Browser can manage files in Vault and Workspace roots.
- Risky Drive actions require confirmation.
- Mobile and desktop screenshots show no overlap.

### Slice 3: Code VS Code Foundation

- Add nested Explorer tree and tabs.
- Add rename/move/delete/duplicate/context menus.
- Add diff view for source-control changed files.
- Add `.gitignore`, pull, push, and richer repo open/close behavior.
- Evaluate Monaco; ship it if feasible, otherwise record the blocker and keep
  native editor solid.
- Add dark/light theme toggle and explicit auto-save opt-in warning.

Acceptance:

- Browser can edit files without auto-save.
- Source Control can inspect diffs and perform common git actions safely.
- Risky Code actions require confirmation.

### Slice 4: Terminal Persistent Sessions

- Implement persistent terminal backend and plugin UI.
- Prefer tmux-backed sessions; fallback only with documented reason.
- Add session list, new, rename, close, reorder, folders, scrollback, streaming.
- Add tests for session metadata, lifecycle, and redaction.

Acceptance:

- Terminal sessions survive dashboard reload.
- Output streams and scrollback remains available.
- Close/kill requires confirmation.

### Slice 5: Integration Polish And Live Proof

- Run Docker upgrade.
- Run Docker health.
- Run live browser smoke over TLS for all three plugins.
- Capture screenshots for desktop and mobile.
- Update docs only after the behavior exists.

## Validation Floor

Always run after touching plugin code:

```bash
python3 -m py_compile \
  plugins/hermes-agent/arclink-drive/dashboard/plugin_api.py \
  plugins/hermes-agent/arclink-code/dashboard/plugin_api.py
python3 tests/test_arclink_plugins.py
node --check plugins/hermes-agent/arclink-drive/dashboard/dist/index.js
node --check plugins/hermes-agent/arclink-code/dashboard/dist/index.js
git diff --check
```

When `arclink-terminal` exists, add:

```bash
python3 -m py_compile plugins/hermes-agent/arclink-terminal/dashboard/plugin_api.py
node --check plugins/hermes-agent/arclink-terminal/dashboard/dist/index.js
```

When installer/provisioning changes:

```bash
bash -n deploy.sh bin/*.sh test.sh
python3 tests/test_arclink_agent_user_services.py
python3 tests/test_arclink_docker.py
python3 tests/test_deploy_regressions.py
```

When UI changes are meaningful:

```bash
./deploy.sh docker upgrade
./deploy.sh docker health
```

Then run browser proof over TLS for:

- `/drive`
- `/code`
- `/terminal`

Browser proof must exercise real interactions, not just page load:

- Drive upload, rename, drag move, trash/restore, root switch.
- Code open file, edit without auto-save, save, view diff, stage/unstage.
- Terminal create session, stream output, reload page, revisit session,
  rename, close with confirmation.

Keep proof notes portable: summarize outcomes, route names, and screenshots
captured; do not paste command logs, host-specific paths, shell timing output,
local usernames, secrets, or raw terminal scrollback.

## Done Means

This mission is done only when:

- ArcLink Drive, Code, and Terminal are present as Hermes dashboard plugins.
- All three are installed and enabled for refreshed agents by default.
- All three fit visually and functionally inside Hermes dashboard.
- Drive exposes Vault and Workspace as separate browsable parents.
- Drive file management is Google Drive-like for the supported local backend.
- Code provides a credible VS Code-like Explorer, editor, and Source Control.
- Terminal provides persistent, revisit-able sessions with scrollback.
- Risky actions are confirmation-gated.
- Default theme is dark; Code can switch to light.
- Tests cover the API/installer/lifecycle behavior.
- Docker health passes after deployment.
- Live browser proof over TLS passes for all three plugins.

## Explicit Non-Goals For This Mission

- Do not solve Production 12 credentialed live proof.
- Do not rebuild the public SaaS landing page.
- Do not redesign Hermes core.
- Do not add fake sharing claims.
- Do not require public internet exposure beyond intended Tailscale/TLS paths.
- Do not commit private state, secrets, terminal logs with secrets, or live
  credentials.
