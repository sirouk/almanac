# Codebase Map

## Root Entrypoints

| Path | Role |
| --- | --- |
| `deploy.sh` | Thin wrapper for canonical install, upgrade, Docker, health, enrollment, Notion, and maintenance flows. |
| `bin/deploy.sh` | Main baremetal deploy and host lifecycle implementation. |
| `bin/arclink-docker.sh` | Docker install, upgrade, reconcile, health, Tailnet publication, deployment repair, and dashboard mount repair. |
| `bin/install-arclink-plugins.sh` | Copies and enables ArcLink Hermes plugins and default hooks for agent homes. |
| `compose.yaml` | Shared Docker Compose runtime substrate. |
| `Dockerfile` | Application image with Python, Node, Docker CLI, Hermes/qmd/runtime support, git, and shell tooling. |
| `ralphie.sh` | Ralphie phase runner. |
| `test.sh` | Full preflight plus heavier install smoke. |
| `IMPLEMENTATION_PLAN.md` | Active backlog and validation floor for this mission. |
| `AGENTS.md` | Repository operating guide for coding and deployment agents. |

## Major Directories

| Directory | Responsibility |
| --- | --- |
| `plugins/hermes-agent/` | ArcLink-owned Hermes plugins. The workspace plugin mission belongs primarily here. |
| `plugins/hermes-agent/arclink-drive/` | Native Drive plugin for Vault and Workspace file management. |
| `plugins/hermes-agent/arclink-code/` | Native Code plugin for workspace editing and git Source Control. |
| `plugins/hermes-agent/arclink-terminal/` | Native Terminal plugin with managed-pty persistent sessions. |
| `plugins/hermes-agent/arclink-managed-context/` | ArcLink managed-context plugin installed alongside workspace plugins. |
| `bin/` | Deploy, Docker, health, onboarding, qmd, PDF, Nextcloud, service, plugin install, and runtime wrappers. |
| `python/` | Control plane, provisioning, Docker supervisor, dashboards, hosted API, onboarding, ingress, product, diagnostics, proof runner, and adapters. |
| `tests/` | Focused regression coverage for plugins, Docker/provisioning, deploy behavior, health, onboarding, product surfaces, and services. |
| `web/` | Next.js product/admin dashboard and browser tests; supporting surface and proof-harness pattern, not the native plugin implementation path. |
| `config/` | Public examples, schemas, model providers, and component pins. |
| `docs/` | Operator docs, architecture/runbooks, Docker notes, proof templates, and product documentation. |
| `research/` | Ralphie planning, stack, coverage, steering, and handoff artifacts. |
| `consensus/` | Phase gate records. |
| `systemd/` | Baremetal service/user unit templates. |
| `compose/` | Supplemental Compose assets. |
| `templates/` | Public templates used to seed private state. |

## Stack Shape

ArcLink is primarily a Python and shell control-plane repository with a
Docker Compose runtime and native Hermes dashboard plugins. The Next.js app is
an important product/admin surface, but the active Drive, Code, and Terminal
mission belongs in the Hermes plugin directories and ArcLink runtime wrappers.

## Workspace Plugin Architecture

| Plugin | Backend | Frontend | Current status |
| --- | --- | --- | --- |
| Drive | `plugins/hermes-agent/arclink-drive/dashboard/plugin_api.py` | `plugins/hermes-agent/arclink-drive/dashboard/dist/index.js`, `style.css` | Native file manager with Vault/Workspace roots, confined file ops, metadata, trash/restore, disabled sharing flags, and browser-proof backlog marked complete. Remaining work is commit/deploy handoff. |
| Code | `plugins/hermes-agent/arclink-code/dashboard/plugin_api.py` | `plugins/hermes-agent/arclink-code/dashboard/dist/index.js`, `style.css` | Native workbench with Explorer/tabs, editor, search, diff, confined file ops, theme controls, and Source Control. Remaining work is commit/deploy handoff. |
| Terminal | `plugins/hermes-agent/arclink-terminal/dashboard/plugin_api.py` | `plugins/hermes-agent/arclink-terminal/dashboard/dist/index.js`, `style.css` | Managed-pty backend with persisted session metadata, bounded scrollback, polling output, input, grouping/reorder controls, and close confirmation. Remaining work is commit/deploy handoff. |
| Managed Context | `plugins/hermes-agent/arclink-managed-context/` | No dashboard tab | Injects ArcLink context and bootstrap behavior for agent turns. |

## Drive Surfaces

| File | Current role | Build implication |
| --- | --- | --- |
| `arclink-drive/dashboard/manifest.json` | Registers `/drive`, icon, JS, CSS, and API entry. | Keep stable unless metadata changes are required. |
| `arclink-drive/dashboard/plugin_api.py` | Root descriptors, local/WebDAV status, path safety, metadata, upload, new file/folder, copy/duplicate, move/rename, favorite, trash/restore, batch results, preview/download. | Preserve capability truth, root confinement, symlink safety, partial failures, and conflict handling while documenting shipped behavior. |
| `arclink-drive/dashboard/dist/index.js` | Hermes SDK React UI for root selection, browsing, preview/details, upload, selection, batch actions, context menus, confirmations, and drag moves. | Keep proof and docs aligned with the actual browser workflow. |
| `arclink-drive/dashboard/dist/style.css` | Scoped dark responsive file-manager styling. | Preserve mobile/desktop fit and avoid nested-card clutter. |
| `arclink-drive/README.md` | Plugin behavior and limits. | Update to match shipped behavior and known limits only. |

## Code Surfaces

| File | Current role | Build implication |
| --- | --- | --- |
| `arclink-code/dashboard/manifest.json` | Registers `/code`, icon, JS, CSS, and API entry. | Keep stable unless metadata changes are required. |
| `arclink-code/dashboard/plugin_api.py` | Workspace root, file list/open/save, mkdir, search, repo discovery, git status, diff, stage, unstage, discard, commit, ignore, pull, push, rename, move, duplicate, trash, and restore. | Preserve root confinement, allowlists, confirmations, hash checks, redaction, and manual-save default. |
| `arclink-code/dashboard/dist/index.js` | Hermes SDK React UI for Explorer/editor/Search/Source Control, diff view, tabs/dirty state, status bar, theme toggle, and confirmations. | Keep docs honest about native editor behavior and Monaco not being shipped unless proven. |
| `arclink-code/dashboard/dist/style.css` | Scoped editor/workspace styling with dark/light support. | Preserve responsive VS Code-like layout during final cleanup. |
| `arclink-code/README.md` | Plugin behavior and limits. | Update after final review if shipped behavior changed. |

## Terminal Surfaces

| File | Current role | Build implication |
| --- | --- | --- |
| `arclink-terminal/dashboard/manifest.json` | Registers `/terminal`, icon, JS, CSS, and API entry. | Keep stable. |
| `arclink-terminal/dashboard/plugin_api.py` | Managed-pty session status, create/list/read/input/rename/close, atomic state, bounded scrollback, root guard, redacted errors, and limits. | Preserve runtime boundary, redaction, cleanup, and polling contracts. |
| `arclink-terminal/dashboard/dist/index.js` | Session list, terminal pane, input, polling reconnect, rename/folder/reorder controls, and close confirmation. | Keep proof notes portable and avoid raw scrollback in artifacts. |
| `arclink-terminal/dashboard/dist/style.css` | Scoped responsive terminal session styling. | Keep mobile fit and non-overlap. |
| `arclink-terminal/README.md` | Managed-pty backend documentation and tmux future path. | Update only if runtime backend or proof status changes. |

## Runtime And Install Wiring

| File | Responsibility | Mission relevance |
| --- | --- | --- |
| `bin/install-arclink-plugins.sh` | Copies default plugins, excludes local caches, prunes legacy plugin aliases, and preserves unknown plugin config while enabling defaults. | Keeps plugin delivery reliable and cache-free. |
| `bin/arclink-docker.sh` | Docker operational wrapper, Tailnet publication, dashboard compose repair, service recreation, and Docker health paths. | Required for truthful URL publication and final deployment handoff. |
| `python/arclink_provisioning.py` | Renders deployment env, volumes, services, labels, and access URLs. | Emits dashboard, Vault, and Workspace runtime signals. |
| `python/arclink_docker_agent_supervisor.py` | Docker-mode user-agent reconciliation and plugin installation. | Ensures refreshed Docker agents receive workspace plugins. |
| `python/arclink_live_runner.py` | Credential-gated live proof orchestration, including workspace browser proof runners. | Source for final proof result reporting, not a substitute for portable notes. |
| `bin/refresh-agent-install.sh` | Baremetal refresh path for existing agents. | Must keep dashboard/plugin env aligned. |

## Test Homes

| Test/check | Role |
| --- | --- |
| `tests/test_arclink_plugins.py` | Primary plugin install/API/UI-contract regression coverage for Drive, Code, Terminal, and managed context. |
| `tests/test_arclink_docker.py` | Docker wrapper, deployment repair, Tailnet publication, and dashboard mount coverage. |
| `tests/test_arclink_provisioning.py` | Deployment render assertions for dashboard, Vault, Workspace, and service intent. |
| `tests/test_arclink_live_runner.py` | Workspace proof runner planning, redaction, TLS URL enforcement, and browser-runner wiring. |
| `tests/test_deploy_regressions.py` | Deploy and shell behavior regressions. |
| `web/tests/browser/` | Product browser harness patterns that can inform proof workflows. |

## Architecture Assumptions

- Workspace behavior belongs in ArcLink Hermes plugins, not Hermes core.
- Plugin APIs must return capability flags that the UI honors.
- API responses and UI errors must be redacted and secret-free.
- File operations must remain confined to approved roots and reject traversal or
  symlink escape.
- Risky operations require deliberate confirmation.
- WebDAV/Nextcloud sharing must remain disabled until a real adapter and tests
  exist.
- Code remains manual-save by default.
- Terminal execution must stay within the deployment/user boundary with bounded
  scrollback and state.
- Proof notes and final docs must not include local host paths, command
  transcripts, raw terminal scrollback, private state, or secrets.

## BUILD Handoff Boundary

The BUILD phase should work from the remaining unchecked items in
`IMPLEMENTATION_PLAN.md` and
`research/RALPHIE_ARCLINK_PLUGIN_WORKSPACES_STEERING.md`. Planning artifacts
should not be treated as a substitute for scoped commit curation, optional
deployment, final health/browser proof freshness checks, or release reporting.
