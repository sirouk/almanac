# Coverage Matrix

## Mission Goal Coverage

| Goal / criterion | Current coverage | Remaining BUILD gap | Validation surface |
| --- | --- | --- | --- |
| Keep work out of Hermes core | Workspace surfaces live under `plugins/hermes-agent/` and install through ArcLink wrappers. | Ensure final diff does not patch Hermes core. | Diff review, focused plugin tests. |
| Stack identification | Stack snapshot ranks Python/shell ArcLink control plane plus native Hermes dashboard plugins as primary, with Docker Compose and Node/Next as supporting stacks. | Preserve this architecture during BUILD; do not redirect the mission into the web app or Hermes core. | Stack snapshot review, diff review. |
| Default plugin installation | Installer enables Drive, Code, Terminal, and managed-context by default. | Keep config preservation and cache excludes green. | `tests/test_arclink_plugins.py`, shell syntax checks. |
| Drive root model | API exposes `Vault` and `Workspace` root descriptors and local-root capabilities. | Keep docs and proof notes aligned with actual root behavior. | API tests, browser proof notes. |
| Drive local file management | Listing, search, upload, mkdir, rename, move, favorite, trash, restore, new-file, copy, duplicate, preview, download, batch API paths, and browser workflow backlog are represented as complete in the controlling plan. | Keep final report tied to recorded proof and avoid overclaiming sharing. | Plugin tests, JS syntax check, proof notes. |
| Drive safety | Traversal and symlink-escape handling exist for local roots; sharing capability is false. | Recheck final docs/UI language so disabled sharing is not presented as complete. | Plugin tests, docs review. |
| Drive partial failures | Batch API returns per-item results and browser bundle contains failure-message handling. | Preserve this behavior during final cleanup. | UI contract tests and proof notes. |
| Code workspace/editor | API lists workspace files, opens/saves bounded text with hash conflict protection, searches, and provides confined rename/move/duplicate/trash/restore operations. Browser bundle includes nested Explorer, tabs/dirty state, filetype markers, context menus, manual-save warning, and theme toggle. | Keep Monaco claims honest and preserve manual-save default in docs. | Plugin tests, JS syntax, proof notes. |
| Code Source Control | Repo discovery, status, diff, stage, unstage, discard, commit, `.gitignore`, pull, and push exist with git CLI allowlists and confirmation flags for risky actions. Browser bundle includes stage-all, unstage-all, discard-all, pull, push, refresh, and last git result controls. | Final report should name tested git flows and residual risk without exposing repository-specific private paths. | Git fixture tests, proof notes. |
| Code VS Code parity honesty | Current native editor keeps Monaco unbundled and documents the asset/CSP caution rather than claiming full VS Code parity. | Keep docs/UI honest about native editor scope. | Monaco blocker note, docs review. |
| Terminal tab | Managed-pty API, JS, CSS, persisted metadata, bounded scrollback, input, polling reconnect, resource limits, and focused tests exist. | Keep polling limitation documented and proof notes free of raw scrollback. | Terminal API tests, JS syntax, proof notes. |
| Terminal safety | Runtime blocks unrestricted root by default, resolves cwd under the workspace root, bounds scrollback/input, and redacts backend errors. | Preserve runtime boundary during final docs and commit curation. | Unit tests, runtime review. |
| Docker dashboard mounts | Docker/provisioning emit dashboard env and mount Vault/Workspace into Hermes dashboard. | If deploying, rerun canonical upgrade/health after pushing the scoped commit. | Docker tests, Docker health. |
| Domain/Tailnet ingress contract | Docker wrapper has Tailnet publication path and unavailable-status handling. | Final report should distinguish successful publication from unavailable status. | Docker tests, proof notes. |
| Documentation truthfulness | Documentation alignment is marked complete in the active backlog for shipped Drive, Code, Terminal, Docker/TLS proof, and known limits. | Preserve truthfulness during commit curation and rerun review if docs change again. | Docs review against tests/proof. |
| Commit/deploy hygiene | Public/private split exists; installer excludes generated caches. | Curate broad dirty tree into scoped commits and omit private/generated artifacts, including plugin bytecode caches. | `git status`, `git diff --check`, hygiene tests. |

## Focused Test Coverage Map

| Test / check | Covered now | Add or verify during BUILD |
| --- | --- | --- |
| `tests/test_arclink_plugins.py` | Plugin install, sanitized statuses, Drive roots/ops/safety, Code search/diff/file ops/git additions, and Terminal persistent sessions/root guard/browser contracts. | Rerun if plugin code or docs examples change. |
| `tests/test_arclink_docker.py` | Docker structure, dashboard root repair, publication behavior. | Keep Tailnet unavailable-status and dashboard mount behavior covered. |
| `tests/test_arclink_provisioning.py` | Deployment render includes dashboard, Vault, Workspace, and code-server intent. | Add terminal runtime env/service intent only if the backend requires it. |
| `tests/test_arclink_live_runner.py` | Workspace proof runner planning, redaction, TLS-only URL enforcement, and native plugin route runner wiring. | Rerun if proof orchestration changes. |
| `tests/test_deploy_regressions.py` | Broad deploy behavior regressions. | Run when shell/deploy glue changes. |
| `python3 -m py_compile ...plugin_api.py` | Syntax validation available for plugin APIs. | Run after every plugin backend edit. |
| `node --check .../dist/index.js` | Syntax validation available for plugin frontend bundles. | Run after every plugin frontend edit. |
| `bash -n deploy.sh bin/*.sh test.sh ralphie.sh` | Shell syntax validation. | Run after installer/Docker/deploy changes. |
| Web checks | Next.js tests/lint/build/browser scripts exist. | Run if product surface or browser proof harness changes. |
| Docker health | Canonical Docker health command exists. | Must pass before final deployed handoff. |
| TLS browser proof | Workspace proof runner covers Drive, Code, and Terminal desktop/mobile routes. | Keep final notes portable and rerun if relevant code changes after the proof. |

## Active Risks

| Area | Risk | BUILD handling |
| --- | --- | --- |
| Worktree hygiene | Many files are modified or untracked. | Preserve user edits, inspect before editing shared files, curate commits by scope. |
| Generated artifacts | Plugin directories can accumulate bytecode and local caches. | Keep installer excludes and omit caches from commits. |
| Drive docs | Sharing can be misunderstood as complete because Nextcloud/WebDAV exists elsewhere. | State disabled/gated sharing plainly until a real adapter exists. |
| Code parity | Native Code is credible but not full VS Code/Monaco. | Use VS Code-like language carefully and document the native editor limit. |
| Terminal backend | Managed-pty persistent sessions are implemented and tested. | Keep tmux as a future option unless Docker/baremetal paths install and prove it. |
| Terminal proof artifacts | Terminal output can contain sensitive user data. | Summarize outcomes only; do not copy raw scrollback. |
| Live deployment | Docker/TLS proof can become stale if runtime or code changes after proof. | Rerun the relevant proof path before final deployed handoff. |

## Coverage Verdict

Planning coverage is sufficient for BUILD handoff. Final mission completion
remains blocked by unchecked commit-hygiene, optional deployment, and
final-report items in `IMPLEMENTATION_PLAN.md` and
`research/RALPHIE_ARCLINK_PLUGIN_WORKSPACES_STEERING.md`.

No planning-only blocker is currently identified. If the final handoff cannot
rerun required health/proof because the target runtime, credentials, routing, or
TLS endpoint is unavailable, record that blocker in `consensus/build_gate.md` or
the final proof notes without checking off affected handoff tasks.
