# Stack Snapshot

- snapshot_date: 2026-05-06
- project_type: existing ArcLink host/runtime repository
- primary_stack_hypothesis: Python and shell ArcLink control plane with native Hermes dashboard plugins
- deterministic_confidence_score: 94/100
- confidence: high

## Deterministic Scoring Method

Scores are based on repository-local evidence only:

- 35 points for source-file volume and location.
- 25 points for executable entrypoints and runtime ownership.
- 20 points for manifests, pins, and dependency declarations.
- 20 points for focused tests covering that stack.

Generated dependency folders, build output, bytecode caches, private state,
tool transcripts, and local proof debris are excluded from the source-count
signal.

## Source Composition Signals

| Source kind | Count | Evidence signal |
| --- | ---: | --- |
| Python | 167 | Primary plugin API, control plane, provisioning, Docker supervisor, live proof, onboarding, MCP, and tests. |
| Shell | 80 | Canonical deploy, Docker, health, service, plugin install, qmd, Nextcloud, and runtime orchestration. |
| JavaScript | 4 | Three hand-authored Hermes dashboard plugin bundles plus the web service worker. |
| TypeScript | 6 | Next.js app config, API client, and Playwright/browser tooling. |
| TSX | 10 | Next.js product/admin/onboarding pages and shared UI. |
| CSS | 4 | Three scoped workspace plugin stylesheets plus global web styling. |
| YAML | 12 | Compose, plugin metadata, schemas/examples, and service/config rails. |
| JSON | 12 | Package manifests, pins, schemas, fixtures, and plugin/dashboard metadata. |

## Ranked Stack Hypotheses

| Rank | Stack hypothesis | Score | Evidence | Decision |
| ---: | --- | ---: | --- | --- |
| 1 | Python + shell ArcLink control plane with Hermes dashboard plugin APIs | 94 | `python/`, `bin/`, `deploy.sh`, workspace `dashboard/plugin_api.py` files, focused Python tests, installer/deploy scripts. | Primary stack for BUILD. |
| 2 | Docker Compose self-hosted runtime | 86 | `compose.yaml`, `Dockerfile`, `bin/arclink-docker.sh`, provisioning renderer, Docker health and provisioning tests. | Required deployment substrate and proof target. |
| 3 | Native Hermes dashboard plugin frontend assets | 80 | Workspace plugin manifests, plain JS bundles, scoped CSS, Hermes plugin installer, UI contract tests. | Required UI delivery path for Drive, Code, and Terminal. |
| 4 | Next.js product/admin web app | 61 | `web/package.json`, `web/src`, Next 15, React 19, Playwright scripts. | Supporting product surface, not the selected workspace-plugin implementation path. |
| 5 | External workspace tools: Nextcloud, code-server, qmd | 54 | Component pins, Compose services, Dockerfile installs, wrappers, docs. | Optional/supporting adapters; not substitutes for native plugins. |
| 6 | Hermes core patching | 5 | Hermes is consumed as a pinned runtime dependency. | Rejected by mission constraints. |

## Primary Runtime Stack

ArcLink is best understood as a Python/shell-managed shared-host system:

- Python owns control-plane behavior, plugin APIs, provisioning, MCP surfaces,
  onboarding, live proof orchestration, hosted API helpers, and tests.
- Shell owns host lifecycle, Docker lifecycle, health, service installation,
  plugin installation, qmd/PDF/Nextcloud wrappers, and upgrade flows.
- Docker Compose supplies the self-hosted deployment substrate.
- Hermes is a pinned upstream runtime and plugin host. ArcLink extends it
  through plugins and wrappers, not core patches.
- Node is present for Docker image base/runtime convenience, qmd installation,
  Hermes web build support, the Next.js product app, and JavaScript plugin
  asset validation.

## Workspace Plugin Stack

| Plugin | Backend | Frontend | Runtime dependency stance |
| --- | --- | --- | --- |
| ArcLink Drive | Python plugin API with local root and WebDAV-aware status paths. | Plain JavaScript Hermes dashboard bundle plus scoped CSS. | No new mandatory frontend framework. Nextcloud sharing remains capability-gated until real adapter proof exists. |
| ArcLink Code | Python plugin API with confined file operations and allowlisted git CLI calls. | Plain JavaScript workbench bundle plus scoped CSS. | Monaco is not mandatory until vendored worker/asset/CSP proof succeeds inside Hermes. |
| ArcLink Terminal | Python managed-pty backend with persisted metadata and bounded scrollback. | Plain JavaScript session UI plus scoped CSS. | Managed pty is the shipped path. tmux and streaming transports remain future candidates. |

## Alternatives Compared

| Alternative | Benefits | Cost / risk | Current decision |
| --- | --- | --- | --- |
| Continue existing native Hermes plugins | Directly satisfies the mission, preserves Hermes core boundary, and uses existing tests/installer/proof rails. | Requires careful dirty-worktree curation and proof freshness checks. | Selected. |
| Build a separate Next.js workspace app | Better app-shell control and conventional frontend tooling. | Misses the native Hermes dashboard-plugin requirement and duplicates runtime concerns. | Rejected for this mission. |
| Depend on external tools as primary UX | Nextcloud, code-server, and terminal links are mature. | Would fake the requested native Drive/Code/Terminal completion. | Keep as optional adapters only. |
| Patch Hermes core | Could expose host capabilities quickly. | Violates constraints and increases runtime upgrade debt. | Rejected. |

## Confidence Notes

The score is high because the repository has strong, repeated evidence for the
selected architecture: plugin manifests, Python APIs, JS/CSS assets, installer
wiring, Docker/provisioning glue, and focused tests all point at the same
native Hermes plugin path. The residual uncertainty is operational rather than
architectural: final BUILD must keep proof current, omit generated caches, and
curate commits without mixing unrelated dirty worktree changes.
