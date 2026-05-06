# Dependency Research

## Stack Components

| Component | Repository evidence | Mission role | Decision |
| --- | --- | --- | --- |
| Hermes dashboard plugin host | Drive, Code, and Terminal `dashboard/manifest.json` files | Native dashboard tab registration, asset loading, and API mounting | Required boundary; do not patch Hermes core. |
| Python plugin APIs | `dashboard/plugin_api.py` in each workspace plugin | Drive file operations, Code workspace/git operations, Terminal session lifecycle | Keep and harden in place. |
| FastAPI-style router layer | Optional FastAPI imports with lightweight fallbacks in plugin APIs | Runtime route integration plus deterministic no-secret tests | Preserve fallback shims. |
| Plain JavaScript bundles | `dashboard/dist/index.js` in each workspace plugin | Hermes SDK React UI for native dashboard tabs | Continue for this mission; add heavier bundling only after proof. |
| Scoped CSS bundles | `dashboard/dist/style.css` in each workspace plugin | Responsive dashboard-safe UI | Extend locally without broad design-system detours. |
| Plugin installer | `bin/install-arclink-plugins.sh` | Copies/enables ArcLink plugins, preserves config, excludes generated caches | Canonical delivery path. |
| Docker Compose runtime | `compose.yaml`, `Dockerfile`, Docker wrapper, provisioning renderer | Runtime substrate for dashboard, Vault, Workspace, qmd, Nextcloud, code-server, health | Required for deploy-ready handoff and any final upgrade. |
| Provisioning renderer | `python/arclink_provisioning.py` | Emits deployment env, volumes, services, labels, access URLs | Extend only for real runtime needs. |
| Workspace proof runner | `python/arclink_live_runner.py`, `python/arclink_live_journey.py`, `tests/test_arclink_live_runner.py` | Credential-gated Docker/TLS proof orchestration for Drive, Code, and Terminal | Use for final proof reporting, with portable notes kept separate from transcripts. |
| Git CLI | Code plugin backend | Allowlisted Source Control operations | Keep with root confinement, confirmations, timeouts, and redaction. |
| Managed pty | Terminal backend | Persistent session IDs, shell process lifecycle, scrollback capture, input, reload revisit | Selected current backend because it is implemented, dependency-light, and tested. |
| tmux | Terminal backend candidate | Stronger detached persistence and capture semantics | Future candidate; do not require until Docker and baremetal install paths prove it. |
| Polling transport | Terminal dashboard/API path | Reconnectable bounded output and POSTed input | Selected current transport because it fits existing plugin API calls. |
| WebSocket/SSE | Terminal transport candidate | Lower-latency streaming output | Future candidate after Hermes plugin host proof. |
| Monaco Editor | Optional Code editor dependency | Rich editor foundation | Do not treat as required; ship only after vendored asset, worker, and CSP proof inside Hermes. |
| code-server | Pinned external IDE image | Optional full IDE link | Adapter only, not native Code completion proof. |
| Nextcloud/WebDAV | Compose service plus Drive WebDAV profile | File browser backend and future sharing adapter | Capability-gated; do not fake sharing. |
| Next.js product app | `web/package.json`, `web/src`, web tests | Product/admin app and browser harness patterns | Supporting surface, not the selected workspace implementation path. |
| Playwright | Web package browser test script and workspace proof runner | Desktop/mobile browser proof automation | Use for proof freshness when plugin, Docker, provisioning, or runner code changes. |
| qmd | Pins and retrieval scripts | Vault knowledge indexing rail | Preserve while changing Drive/Workspace behavior. |
| Tailnet/domain ingress | Docker wrapper, provisioning access URLs, health/proof rails | TLS route publication and browser proof entrypoints | Publish URLs only after successful route setup. |

## Version And Runtime Signals

| Component | Current signal | Planning implication |
| --- | --- | --- |
| Hermes agent | Pinned by component config | Do not rely on unproven dashboard host behavior; stay in plugin APIs/assets. |
| Python | Plugin APIs and most tests are plain Python | Run compile checks and focused tests after backend edits. |
| Node.js | Dockerfile starts from Node 22; web app has Next/React tooling | Needed for web app, Hermes dashboard assets, JS syntax checks, and proof tooling. |
| React | Hermes provides dashboard runtime; web app uses React 19 | Avoid introducing duplicate plugin-side React build complexity unless proven necessary. |
| Next.js | Product app uses Next 15 | Support product/admin and browser harnesses only. |
| code-server | Pinned external image in provisioning | Useful external IDE link; not native Code parity. |
| Nextcloud | Pinned service family in Compose/provisioning | Future share adapter must be real and tested before enabled. |
| qmd | Pinned npm package | Preserve retrieval and vault indexing rails. |

## Alternatives Compared

| Decision area | Preferred | Alternative | Reasoning |
| --- | --- | --- | --- |
| Workspace surface | Existing Hermes dashboard plugins | Separate Next.js workspace app | Native tabs are the mission; a separate app misses the requirement. |
| Drive root model | Explicit `Vault` and `Workspace` roots | Single merged virtual root | Separate roots are safer, clearer, and already represented in API status. |
| Drive sharing | Disabled until real adapter | Stub share buttons or synthetic links | Fake sharing is explicitly prohibited. |
| Code editor | Harden current native editor; add Monaco only after proof | Build directly on Monaco now | Monaco workers/assets/CSP may fail inside the plugin host; the current native editor can satisfy manual-save proof without adding that risk. |
| Code Source Control | Allowlisted git CLI actions | Arbitrary git command endpoint | Allowlisting keeps shell escape, path scope, timeout, and confirmation behavior auditable. |
| Terminal backend | Managed pty now; tmux later if proven | Require tmux immediately | Managed pty is implemented and tested; tmux requires deployment dependency work before it can be mandatory. |
| Terminal transport | Bounded polling now; streaming later if proven | Synchronous command endpoints | Persistent Terminal needs input/output/reconnect semantics. Polling is acceptable and documented for this slice. |
| Runtime changes | ArcLink Docker/provisioning wrappers | Hermes core patches | Wrappers preserve upgrade compatibility and mission constraints. |

## Source Composition Signals

Counts exclude private state, dependency folders, build output, bytecode caches,
and test caches. They are repository-composition signals, not a full language
line-count audit.

| Source kind | Count | Planning implication |
| --- | ---: | --- |
| Python | 167 | Primary control plane, plugin API, provisioning, proof runner, and test implementation language. |
| Shell | 80 | Canonical deploy, Docker, health, plugin install, and service orchestration layer. |
| JavaScript | 4 | Three active plugin bundles plus the web service worker; plugin JS is intentionally direct. |
| TypeScript | 6 | Next.js config/lib and Playwright typing/config. |
| TSX | 10 | Next.js product/admin pages and React components. |
| CSS | 4 | Scoped plugin CSS plus web global styling. |
| YAML | 12 | Plugin metadata, config schemas/examples, Compose, and service metadata. |
| JSON | 12 | Package manifests, pins, schemas, fixtures, and plugin/dashboard metadata. |

## Dependency Risks

- Monaco may require vendored workers/assets and CSP allowances not available
  to dashboard plugins.
- WebSocket/SSE terminal streaming is unproven in the Hermes plugin host.
- Managed pty persistence is sufficient for revisit-after-reload, but not the
  same as tmux survival across all process restarts.
- WebDAV file capability does not imply Nextcloud share capability.
- Git pull, push, discard, and discard-all need strict allowlists, timeouts,
  path checks, confirmations, and redacted errors.
- Deployment proof depends on runtime availability, TLS routing, Tailnet or
  domain publication, and credentials.
- The worktree is broad; BUILD must not mix generated caches, private state, or
  unrelated edits into commits.

## BUILD Dependency Decision

No new mandatory dependency should be introduced for the handoff phase unless a
focused proof demonstrates it inside the Hermes dashboard plugin host and
Docker/baremetal delivery paths. Monaco, tmux, WebSocket/SSE transport, and
Nextcloud sharing remain optional candidates until proven by code, tests, and
browser proof.

## Validation Requirements

Run after workspace plugin code changes:

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

Run when installer, Docker, provisioning, or deploy glue changes:

```bash
bash -n deploy.sh bin/*.sh test.sh ralphie.sh
python3 tests/test_arclink_agent_user_services.py
python3 tests/test_arclink_docker.py
python3 tests/test_arclink_provisioning.py
python3 tests/test_deploy_regressions.py
```

Before final mission handoff, verify the recorded Docker/TLS proof artifacts
are still current. Rerun Docker health or browser proof if plugin, installer,
Docker, provisioning, proof-runner, documentation, or runtime state changed
after the last passing proof.
