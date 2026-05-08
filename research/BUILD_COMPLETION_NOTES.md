# Build Completion Notes

## 2026-05-08 Ralphie BUILD Verification Pass

Scope: executed the active `IMPLEMENTATION_PLAN.md` BUILD verification tasks
after confirming no unchecked backlog items remained in the plan or steering
file.

Rationale:

- Fixed the web validation failures found during verification instead of
  weakening release checks. Next.js 15 requires `useSearchParams()` users to be
  under `Suspense` during static prerender, so checkout success/cancel now keep
  their existing client behavior inside small Suspense-wrapped content
  components.
- Kept fake-adapter copy truthful by showing it only when the backend reports
  fake mode, and made Playwright deterministic by mocking `adapter-mode` only
  in tests that assert fake-mode UI. Live-mode pages still avoid unconditional
  fake-adapter claims.
- Updated the mocked browser onboarding flow to provide the email now required
  for post-checkout login/status identity.
- Closed the post-review documentation hold by removing stale language that
  described Stripe webhook handling as a no-secret skip. Canonical docs now
  consistently say that an unset `STRIPE_WEBHOOK_SECRET` returns
  `stripe_webhook_secret_unset` with status 503 so Stripe retries.

Documentation surface accounted for:

- `AGENTS.md`, `README.md`, and `docs/DOC_STATUS.md` now frame Shared Host,
  Shared Host Docker, Sovereign Control Node, and canonical/historical/proof-
  gated documentation status.
- `docs/arclink/foundation.md`, `foundation-runbook.md`,
  `operations-runbook.md`, and `control-node-production-runbook.md` now align
  hosted API, action-worker, Stripe webhook, executor, and proof-gated
  production claims.
- `docs/arclink/data-safety.md`, `docs/docker.md`,
  `docs/arclink/local-validation.md`, `docs/arclink/live-e2e-secrets-needed.md`,
  and the live evidence template now describe trust boundaries, Docker socket
  and private-state exposure, validation setup, and credential-gated proof
  limits.
- `docs/arclink/first-day-user-guide.md` and
  `docs/arclink/notion-human-guide.md` cover the customer/operator first-day
  journey, dashboard expectations, Notion SSOT boundaries, and recovery paths.
- `docs/arclink/architecture.md`, `docs/openapi/arclink-v1.openapi.json`,
  `docs/API_REFERENCE.md`, `docs/arclink/CHANGELOG.md`, and the research maps
  were updated to reflect the repaired web/API, Docker, onboarding, knowledge,
  and control-plane surfaces.

Verification run:

- `git diff --check` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `python3 -m py_compile` for touched Python files passed.
- Focused Python suites from the plan passed:
  `test_arclink_plugins.py`, `test_arclink_agent_user_services.py`,
  `test_loopback_service_hardening.py`, `test_arclink_hosted_api.py`,
  `test_arclink_api_auth.py`, `test_arclink_dashboard.py`,
  `test_arclink_action_worker.py`, `test_arclink_admin_actions.py`,
  `test_arclink_provisioning.py`, `test_arclink_sovereign_worker.py`,
  `test_arclink_fleet.py`, `test_arclink_rollout.py`,
  `test_arclink_evidence.py`, `test_arclink_live_runner.py`,
  `test_arclink_docker.py`, `test_deploy_regressions.py`,
  `test_health_regressions.py`,
  `test_arclink_curator_onboarding_regressions.py`,
  `test_arclink_public_bots.py`, `test_pdf_ingest_env.py`,
  `test_memory_synthesizer.py`, `test_arclink_ssot_batcher.py`, and
  `test_documentation_truths.py`.
- Web checks passed: `npm test`, `npm run lint`, `npm run build`, and
  `npm run test:browser` with 41 passed and 3 desktop-skipped mobile-layout
  tests.

Known risks:

- Heavy/live checks were not run: `./test.sh`, live deploy/install/upgrade,
  Docker install/upgrade, Stripe, Cloudflare, Tailscale, Telegram, Discord,
  Notion, provider credential smoke, and public bot mutation flows remain
  proof-gated unless the operator explicitly authorizes them.
- The worktree is intentionally broad from the Ralphie repair mission and still
  needs commit curation before deployment.

## 2026-05-08 Ralphie Slice 5 Onboarding Recovery Build

Scope: closed the remaining Slice 5 onboarding recovery items from
`IMPLEMENTATION_PLAN.md`.

Rationale:

- Used the existing completion receipt and Discord contact retry rails rather
  than adding another handoff channel. `/retry-contact` now gives users and
  operators a visible recovery path that reuses the stored confirmation code.
- Labeled public `/connect_notion` and `/config_backup` as preparation lanes
  because the public bot does not perform Curator-grade Notion verification or
  deploy-key setup. The commands now record pending status and point to the
  dashboard/operator rail for completion.
- For API-key providers, recorded `runtime_pending` validation after checking
  that a credential is present. A live smoke call was not added because the
  onboarding path has no existing side-effect-free provider check and live
  calls may be quota/network dependent.

Verification run:

- `python3 tests/test_arclink_curator_onboarding_regressions.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_arclink_onboarding_prompts.py` passed.
- `python3 -m py_compile` for touched onboarding/public-bot modules and tests
  passed.

Known risks:

- This pass did not run live Discord, Telegram, GitHub deploy-key, Notion, or
  provider credential smoke checks. Those remain credential-gated live proof
  surfaces.
- Full BUILD is not complete; Slice 6 knowledge freshness and Slice 7 docs and
  validation items remain open.

## 2026-05-08 Ralphie Shared Host Nextcloud Effective Enablement Build

Scope: advanced Slice 4 / Priority 3 by closing the Nextcloud effective
enablement gap from `IMPLEMENTATION_PLAN.md`.

Rationale:

- Added a shared `nextcloud_effectively_enabled` predicate instead of letting
  install, restart, wait, rotation, and health each interpret raw
  `ENABLE_NEXTCLOUD` differently.
- Treated Docker mode as compose-only, while bare-metal can use either Podman
  or Compose. This matches the existing `nextcloud-up.sh` runtime split and
  avoids starting or waiting on a disabled service when no runtime is present.
- Kept `ENABLE_NEXTCLOUD=1` in persisted config as the operator's intent rather
  than silently rewriting config when the runtime is temporarily unavailable.

Verification run:

- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `python3 tests/test_install_user_services_regressions.py` passed.
- `python3 tests/test_nextcloud_regressions.py` passed.
- `python3 tests/test_health_regressions.py` passed.
- `python3 tests/test_deploy_regressions.py` passed.
- `python3 -m py_compile tests/test_install_user_services_regressions.py
  tests/test_health_regressions.py tests/test_deploy_regressions.py` passed.
- `git diff --check` passed.

Known risks:

- This pass did not run live install/upgrade, mutate systemd units, or start a
  real Nextcloud runtime. Remaining Slice 4 Docker operation items are still
  open.

## 2026-05-08 Priority 0 Security Boundary Repair Slice

Scope: closed the remaining local Priority 0 security boundary items from the
Ralphie ecosystem gap plan.

Rationale:

- Isolated Docker dashboard backends with per-agent internal Docker networks
  instead of trying to rely on the default Compose network plus a public-facing
  auth proxy. The proxy remains the only host-loopback published surface.
- Staged auto-provision bootstrap tokens into the per-agent bootstrap-token file
  before invoking `init.sh`, avoiding raw token handoff through the
  provisioning subprocess environment while preserving `init.sh` compatibility.
- Added generated-root guards before PDF and Notion index cleanup unlinks so a
  corrupted DB path cannot delete outside generated markdown roots.
- Rejected unsafe team-resource slugs before any checkout path construction or
  destructive git reset path can be reached.

Files changed:

- `python/arclink_docker_agent_supervisor.py` and `docs/docker.md`
- `python/arclink_enrollment_provisioner.py` and `bin/init.sh`
- `bin/pdf-ingest.py` and `python/arclink_control.py`
- `bin/clone-team-resources.sh`
- Focused tests under `tests/`

Verification run:

- `python3 tests/test_pdf_ingest_env.py` passed.
- `python3 tests/test_arclink_docker.py` passed.
- `python3 tests/test_arclink_auto_provision.py` passed.
- `python3 tests/test_arclink_repo_sync.py` passed.
- `python3 tests/test_arclink_notion_knowledge.py` passed.
- `git diff --check` passed.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `python3 -m py_compile` for touched Python modules and tests passed.

Known risks:

- This slice did not address the hosted web/API identity and checkout backlog;
  those remain the next unchecked Priority 1 items.

## 2026-05-06 Workspace Proof Screenshot And Documentation Handoff

Scope: completed the portable proof-note and documentation handoff tasks for
the native Drive, Code, and Terminal Hermes dashboard plugins.

Rationale:

- Added sanitized screenshot capture to the repeatable
  `bin/arclink-live-proof --journey workspace --live` path instead of keeping
  one-off manual screenshots outside the evidence contract.
- Kept screenshot artifacts under ignored `evidence/workspace-screenshots/`
  and recorded only relative paths in redacted evidence. The screenshot
  sanitizer masks file names, paths, editor text, terminal scrollback, facts,
  and free-form inputs before capture.
- Updated docs to claim only shipped behavior: Drive and Code are
  first-generation native plugins; Code is not Monaco/VS Code parity; Terminal
  is managed-pty with bounded polling, not tmux or true streaming; workspace
  Docker/TLS proof is complete and separate from the broader hosted customer
  live journey.

Files changed:

- `python/arclink_live_runner.py` - records sanitized screenshot references in
  browser proof evidence, masks sensitive UI regions before screenshot capture,
  and reopens Terminal after reload so the screenshot proves the native plugin
  route.
- `tests/test_arclink_live_runner.py` - covers screenshot evidence and runner
  script generation.
- `docs/arclink/architecture.md`, `docs/arclink/foundation.md`,
  `docs/arclink/foundation-runbook.md`,
  `docs/arclink/document-phase-status.md`,
  `docs/arclink/CHANGELOG.md`, and
  `docs/arclink/live-e2e-evidence-template.md` - aligned workspace plugin
  claims with shipped behavior and completed workspace Docker/TLS proof.
- `IMPLEMENTATION_PLAN.md` and
  `research/RALPHIE_ARCLINK_PLUGIN_WORKSPACES_STEERING.md` - marked proof-note
  and documentation handoff items complete while leaving commit curation and
  optional deploy handoff open.

Verification run:

- `PYTHONDONTWRITEBYTECODE=1 python3 tests/test_arclink_live_runner.py`
  passed.
- `python3 -m py_compile python/arclink_live_runner.py tests/test_arclink_live_runner.py`
  passed.
- Generated workspace Playwright proof script passed `node --check` via a
  temporary file.
- `./bin/arclink-live-proof --journey workspace --live --json` passed with
  `passed=8`; evidence: `evidence/run_82ace4c10b45.json`.
- The passing live proof covered `deploy.sh docker upgrade`, `deploy.sh docker
  health`, Drive desktop/mobile TLS proof, Code desktop/mobile TLS proof, and
  Terminal desktop/mobile TLS proof.
- Sanitized screenshot references from the passing proof:
  `../evidence/workspace-screenshots/drive-desktop-1778044624358.png`,
  `../evidence/workspace-screenshots/drive-mobile-1778044625589.png`,
  `../evidence/workspace-screenshots/code-desktop-1778044627199.png`,
  `../evidence/workspace-screenshots/code-mobile-1778044628422.png`,
  `../evidence/workspace-screenshots/terminal-desktop-1778044632221.png`,
  `../evidence/workspace-screenshots/terminal-mobile-1778044635510.png`.

Known risks:

- BUILD handoff is still not fully complete because the broad dirty worktree
  has not been curated into scoped commits.
- Production 12 hosted customer proof remains blocked on separate hosted
  credentials; the workspace Docker/TLS proof does not prove Stripe,
  Cloudflare, Chutes, Telegram, or Discord live paths.
- Host readiness in the workspace proof result still reports missing hosted
  provider env vars. Those are unrelated to the completed `workspace` journey
  but remain blockers for the broader hosted journey.

## 2026-05-06 Workspace TLS Proof Bring-Home Pass

Scope: completed the credentialed Docker/TLS proof loop for the native Drive,
Code, and Terminal Hermes dashboard plugins on the target Docker deployment.

Rationale:

- Kept proof execution in `bin/arclink-live-proof --journey workspace --live`
  instead of a one-off transcript so the result remains repeatable and
  redacted.
- Activated Hermes dashboard plugins through their native dashboard links
  instead of assuming direct `/drive`, `/code`, or `/terminal` navigation will
  bypass the dashboard shell. The live Hermes build redirects direct plugin
  routes back through `/sessions` until the native sidebar route is selected.
- Kept the Terminal root guard intact for baremetal/host use and set the
  explicit Docker dashboard allowance only in generated deployment
  `hermes-dashboard` compose repair, where the terminal process is confined to
  the deployment container and `/workspace` mount.

Files changed:

- `python/arclink_live_runner.py` - fixed workspace browser proof script
  placement for Node module resolution, added native dashboard plugin
  navigation for desktop/mobile, and waited for plugin-specific controls before
  running API assertions.
- `plugins/hermes-agent/arclink-terminal/dashboard/dist/index.js` - registered
  Terminal through the same Hermes plugin registry used by Drive and Code.
- `bin/arclink-docker.sh` - repaired generated deployment dashboard compose
  files with `ARCLINK_TERMINAL_ALLOW_ROOT=1` for the Docker container boundary.
- `tests/test_arclink_live_runner.py`, `tests/test_arclink_plugins.py`, and
  `tests/test_arclink_docker.py` - covered the runner script location,
  dashboard navigation contract, Terminal registration API, and Docker
  dashboard env repair.
- `.gitignore` - ignored interrupted local workspace-proof temp directories.
- `IMPLEMENTATION_PLAN.md` and
  `research/RALPHIE_ARCLINK_PLUGIN_WORKSPACES_STEERING.md` - marked the
  completed Docker/TLS proof items.

Verification run:

- `./bin/arclink-live-proof --journey workspace --live --json` passed with
  `passed=8`; evidence: `evidence/run_d4513a2ba89b.json`.
- The passing live proof covered `deploy.sh docker upgrade`, `deploy.sh docker
  health`, Drive desktop/mobile TLS proof, Code desktop/mobile TLS proof, and
  Terminal desktop/mobile TLS proof.
- `PYTHONDONTWRITEBYTECODE=1 python3 tests/test_arclink_live_runner.py`
  passed.
- `PYTHONDONTWRITEBYTECODE=1 python3 tests/test_arclink_plugins.py` passed.
- `PYTHONDONTWRITEBYTECODE=1 python3 tests/test_arclink_docker.py` passed.
- `node --check plugins/hermes-agent/arclink-terminal/dashboard/dist/index.js`
  passed.
- `bash -n bin/arclink-docker.sh` passed.
- `git diff --check` passed.

Known risks:

- BUILD handoff is still not fully complete because screenshot capture, commit
  curation, and final deploy-ready documentation/hygiene remain open plan
  items.
- The live runner host-readiness section still reports missing hosted-provider
  env vars for the broader hosted journey; those are unrelated to the
  completed `workspace` journey but should not be mistaken for hosted journey
  proof.

## 2026-05-06 Workspace TLS Proof Executor Slice

Scope: advanced the credential-gated live-proof journey for the native Hermes
workspace plugins from a canonical runner target to default live executors for
Docker upgrade/reconcile, Docker health, and Drive/Code/Terminal desktop/mobile
TLS browser proof.

Rationale:

- Extended the existing `arclink-live-proof` runner instead of creating a
  one-off browser transcript because the current mission needs repeatable,
  redacted proof artifacts before checkboxes can be closed.
- Kept the hosted onboarding/provider journey as the default and added
  `--journey workspace` so workspace proof can be planned without requiring
  Stripe, Chutes, Telegram, or Discord credentials.
- Required `ARCLINK_WORKSPACE_PROOF_TLS_URL` and
  `ARCLINK_WORKSPACE_PROOF_AUTH` by name only; the live runner still does not
  print or persist auth material.
- Added real default runners only for `--journey workspace --live`, keeping the
  broader hosted journey pending until its separate provider runners exist.
- Used Playwright through the existing web dependency set instead of a one-off
  HTTP-only probe, because the plan requires browser proof over the real TLS
  dashboard routes.

Files changed:

- `python/arclink_live_journey.py` - split hosted and workspace proof journeys,
  adding Docker health/reconcile plus Drive, Code, and Terminal desktop/mobile
  TLS proof steps.
- `python/arclink_live_runner.py` - added the `--journey hosted|workspace|all`
  selector, selected default workspace live runners when no fake runners are
  injected, ran the Docker commands, and executed redacted Playwright proof
  steps for `/drive`, `/code`, and `/terminal`.
- `python/arclink_evidence.py` - added workspace proof auth to the explicit
  redaction set.
- `tests/test_arclink_live_journey.py` and
  `tests/test_arclink_live_runner.py` - covered workspace journey structure,
  missing-env reporting, dry-run behavior, fake live runners, and proof auth
  redaction.
- `docs/arclink/live-e2e-secrets-needed.md` and
  `docs/arclink/live-e2e-evidence-template.md` - documented the workspace proof
  env vars, auth formats, execution commands, timeouts, and evidence rows.

Verification run:

- `python3 -m py_compile python/arclink_live_runner.py tests/test_arclink_live_runner.py` passed.
- `python3 tests/test_arclink_live_runner.py` passed.
- `python3 tests/test_arclink_live_journey.py` passed.
- `python3 -m py_compile plugins/hermes-agent/arclink-drive/dashboard/plugin_api.py plugins/hermes-agent/arclink-code/dashboard/plugin_api.py plugins/hermes-agent/arclink-terminal/dashboard/plugin_api.py` passed.
- `node --check` passed for the Drive, Code, and Terminal dashboard bundles.
- `python3 tests/test_arclink_plugins.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh ralphie.sh` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `bin/arclink-live-proof --journey workspace --json` passed with
  `blocked_missing_credentials` and missing env names only.
- `node --check` passed for the generated workspace Playwright proof script.
- `git diff --check` passed.

Known risks:

- BUILD remains incomplete: the executor path is implemented and locally
  tested, but the actual live Docker upgrade/reconcile, Docker health, and
  Drive/Code/Terminal desktop/mobile TLS browser proof still need a target
  deployment and credentials.

## 2026-05-06 Integration Validation Pass

Scope: executed the deterministic integration checks available without a
credentialed live TLS dashboard or deployment upgrade target.

Rationale:

- Kept live Docker upgrade, Docker health, and TLS browser proof open because
  those require an explicit target deployment and credentialed dashboard access.
- Used the existing validation floor and web browser checks rather than adding
  a new proof harness for native Hermes plugins.

Files changed:

- `IMPLEMENTATION_PLAN.md` - marked the focused integration-check item complete.
- `research/RALPHIE_ARCLINK_PLUGIN_WORKSPACES_STEERING.md` - mirrored the
  focused integration-check completion.
- `research/BUILD_COMPLETION_NOTES.md` - recorded this validation pass and the
  remaining live-proof blocker.

Verification run:

- `python3 -m py_compile plugins/hermes-agent/arclink-drive/dashboard/plugin_api.py plugins/hermes-agent/arclink-code/dashboard/plugin_api.py plugins/hermes-agent/arclink-terminal/dashboard/plugin_api.py` passed.
- `node --check` passed for Drive, Code, and Terminal dashboard bundles.
- `python3 tests/test_arclink_plugins.py` passed.
- `bash -n deploy.sh bin/*.sh test.sh ralphie.sh` passed.
- `python3 tests/test_arclink_agent_user_services.py` passed.
- `python3 tests/test_arclink_docker.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_deploy_regressions.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 tests/test_health_regressions.py` passed.
- `git diff --check` passed.
- `npm --prefix web test` passed.
- `npm --prefix web run lint` passed.
- `npm --prefix web run build` passed.
- `npm --prefix web run test:browser` passed with 41 passing and 3 skipped
  desktop-inapplicable mobile-layout cases.

Known risks:

- BUILD is not complete: Docker upgrade/reconcile, Docker health, and real TLS
  browser proof for Drive, Code, and Terminal remain open.
- The current proof did not exercise a live Hermes dashboard plugin host.

## 2026-05-06 Code Nested Explorer Slice

Scope: advanced the Code VS Code foundation by replacing the flat Explorer
surface with a bounded nested tree contract, context-menu file operations, and
tab dirty markers while keeping existing confined backend operations.

Rationale:

- Added a native `/tree` plugin API instead of introducing a separate workspace
  app because the Hermes dashboard plugin already owns the Code surface.
- Kept the tree bounded and symlink-pruned so Explorer navigation stays within
  the configured workspace root and does not surface out-of-root symlink
  targets.

Files changed:

- `plugins/hermes-agent/arclink-code/dashboard/plugin_api.py` - added bounded
  `/tree`, advertised nested Explorer capability, and skipped symlink entries
  in workspace listings.
- `plugins/hermes-agent/arclink-code/dashboard/dist/index.js` - added nested
  Explorer rendering, right-click context menu actions, drag/drop move
  confirmation on tree folders, and tab dirty marker updates.
- `plugins/hermes-agent/arclink-code/dashboard/dist/style.css` - styled nested
  Explorer nodes and the context menu.
- `tests/test_arclink_plugins.py` - covered `/tree`, symlink pruning, nested
  Explorer bundle controls, context menus, and dirty-tab markers.
- `IMPLEMENTATION_PLAN.md` and
  `research/RALPHIE_ARCLINK_PLUGIN_WORKSPACES_STEERING.md` - marked only the
  validated nested Explorer task complete while leaving TLS proof open.

Verification run:

- `python3 -m py_compile plugins/hermes-agent/arclink-code/dashboard/plugin_api.py` passed.
- `node --check plugins/hermes-agent/arclink-code/dashboard/dist/index.js` passed.
- `python3 tests/test_arclink_plugins.py` passed.

Known risks:

- Code desktop/mobile TLS browser proof remains open.
- The nested tree is intentionally bounded to depth 3 in the UI and depth 4 in
  the backend; deeper folders remain reachable through folder navigation and
  search.

## 2026-05-06 Terminal Managed Pty Slice

Scope: advanced the Terminal persistent-session slice by replacing the scaffold
with a documented ArcLink-managed pty backend, bounded polling dashboard UI, and
focused lifecycle tests.

Rationale:

- Chose the managed-pty fallback instead of requiring tmux in this slice because
  the Docker and baremetal runtime paths do not yet install and validate tmux as
  a shared dependency.
- Used bounded polling rather than WebSockets/SSE because the current Hermes
  plugin host path already supports simple dashboard API calls and this keeps
  reconnect behavior testable without a new transport rail.
- Added an unrestricted-root startup guard so terminal sessions run only inside
  the deployment/user runtime boundary unless an explicit diagnostics override
  is set.

Files changed:

- `plugins/hermes-agent/arclink-terminal/dashboard/plugin_api.py` - added
  managed-pty session create/list/read/input/rename/close endpoints, atomic
  session state, bounded scrollback, root guard, and redacted backend errors.
- `plugins/hermes-agent/arclink-terminal/dashboard/dist/index.js` - added the
  Terminal session list, new session, input, polling refresh, rename, folder,
  reorder, and close confirmation UI.
- `plugins/hermes-agent/arclink-terminal/dashboard/dist/style.css` - added
  responsive session, terminal pane, input, error, and confirmation styles.
- `plugins/hermes-agent/arclink-terminal/README.md` - documented the
  managed-pty backend, polling limitation, root guard, and future tmux path.
- `tests/test_arclink_plugins.py` - covered Terminal create/revisit/input,
  rename/folder/reorder, close confirmation, scrollback bounds, traversal
  rejection, redaction, root guard, and browser bundle controls.
- `IMPLEMENTATION_PLAN.md` and
  `research/RALPHIE_ARCLINK_PLUGIN_WORKSPACES_STEERING.md` - marked only the
  validated Terminal managed-pty tasks complete while leaving TLS proof open.

Verification run:

- `python3 -m py_compile plugins/hermes-agent/arclink-drive/dashboard/plugin_api.py plugins/hermes-agent/arclink-code/dashboard/plugin_api.py plugins/hermes-agent/arclink-terminal/dashboard/plugin_api.py` passed.
- `node --check plugins/hermes-agent/arclink-terminal/dashboard/dist/index.js`
  passed.
- `python3 tests/test_arclink_plugins.py` passed.

Known risks:

- Terminal desktop/mobile TLS browser proof remains open.
- The current transport is bounded polling, not true streaming.
- tmux is still a future backend option; Docker/baremetal install validation
  has not been added for tmux.

## 2026-05-05 Code Source Control Diff Slice

Scope: advanced the Code VS Code foundation by adding a bounded backend diff
contract and a browser diff view for Source Control changed-file clicks.

Rationale:

- Kept the diff implementation inside the native ArcLink Code plugin API and
  dashboard bundle instead of introducing a separate app or Hermes core patch.
- Used allowlisted `git diff`/`git show` reads plus existing workspace/repo path
  confinement so Source Control can inspect staged, unstaged, and untracked
  text changes without shelling out through an unrestricted terminal surface.
- Left Monaco evaluation for the dedicated editor task; this slice only needed
  a source-control diff view.

Files changed:

- `plugins/hermes-agent/arclink-code/dashboard/plugin_api.py` - added
  `/git/diff` with size bounds, text-file guards, and repo-confined file
  resolution.
- `plugins/hermes-agent/arclink-code/dashboard/dist/index.js` - changed Source
  Control changed-file clicks to fetch and render a before/after diff view.
- `plugins/hermes-agent/arclink-code/dashboard/dist/style.css` - added
  responsive diff-pane styling.
- `tests/test_arclink_plugins.py` - covered working-tree, staged, untracked,
  and traversal-rejected diff behavior plus the browser bundle contract.
- `IMPLEMENTATION_PLAN.md` and
  `research/RALPHIE_ARCLINK_PLUGIN_WORKSPACES_STEERING.md` - marked only the
  validated diff-view task complete.

Verification run:

- `python3 -m py_compile plugins/hermes-agent/arclink-drive/dashboard/plugin_api.py plugins/hermes-agent/arclink-code/dashboard/plugin_api.py plugins/hermes-agent/arclink-terminal/dashboard/plugin_api.py` passed.
- `node --check plugins/hermes-agent/arclink-code/dashboard/dist/index.js` passed.
- `python3 tests/test_arclink_plugins.py` passed.

Known risks:

- Drive TLS proof remains externally blocked by lack of a credentialed TLS
  dashboard target in this environment.
- Code still needs nested Explorer operations, Search/status bar, richer git
  actions, theme/auto-save controls, Monaco decision, and live browser proof.

## 2026-05-05 Deploy Baseline And Drive Trash UX Slice

Scope: executed the highest-priority deploy-readiness validation from the
native workspace plugin plan, repaired the README canonical shared-host layout
contract, and advanced Drive browser UX with root-aware breadcrumbs plus a
Trash/Restore view backed by the existing Drive APIs.

Rationale:

- Restored `/home/arclink/` in the README shared-host layout blocks instead of
  weakening the Docker regression that protects operator documentation.
- Kept Drive work in the native Hermes plugin's plain JavaScript bundle and
  existing Python API boundary; no Hermes core or separate Next.js workspace app
  changes were needed for this slice.
- Left sharing disabled because there is still no real Nextcloud/WebDAV share
  adapter with tests.

Files changed:

- `README.md` - restored the canonical `/home/arclink/` root in Shared Host
  layout examples.
- `plugins/hermes-agent/arclink-drive/dashboard/dist/index.js` - added
  root-labeled `Drive / Vault|Workspace` breadcrumbs, a Trash mode, restore
  actions, selected trash restore, and disabled upload/drop affordances while
  viewing trash.
- `tests/test_arclink_plugins.py` - added a focused browser bundle contract
  check for Drive roots, breadcrumbs, Trash, and Restore controls.
- `IMPLEMENTATION_PLAN.md` and
  `research/RALPHIE_ARCLINK_PLUGIN_WORKSPACES_STEERING.md` - marked only the
  validated deploy-readiness and Drive root/sharing checklist items complete.

Verification run:

- `python3 -m py_compile plugins/hermes-agent/arclink-drive/dashboard/plugin_api.py plugins/hermes-agent/arclink-code/dashboard/plugin_api.py plugins/hermes-agent/arclink-terminal/dashboard/plugin_api.py` passed.
- `node --check plugins/hermes-agent/arclink-drive/dashboard/dist/index.js && node --check plugins/hermes-agent/arclink-code/dashboard/dist/index.js && node --check plugins/hermes-agent/arclink-terminal/dashboard/dist/index.js` passed.
- `bash -n deploy.sh bin/*.sh test.sh ralphie.sh` passed.
- `python3 tests/test_arclink_plugins.py` passed.
- `python3 tests/test_arclink_agent_user_services.py` passed.
- `python3 tests/test_arclink_docker.py` failed first on the README layout root, then passed after the README repair.
- `python3 tests/test_deploy_regressions.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 tests/test_health_regressions.py` passed.
- `git diff --check` passed.

Known risks:

- Drive still needs full desktop/mobile TLS browser proof before Slice 2B is
  complete.
- The new Trash/Restore coverage is a static bundle contract plus existing
  backend tests, not a real browser interaction test.
- Code VS Code foundation, Terminal persistent sessions, Docker/TLS integration
  proof, commit curation, and deploy handoff remain open.

## 2026-05-05 Native Workspace Plugin Slice 1

Scope: completed the first build slice for native Hermes dashboard workspaces
by adding the `arclink-terminal` plugin scaffold, enabling it by default, and
standardizing sanitized `/status` contracts across Drive, Code, and Terminal.

Rationale:

- Kept the implementation inside ArcLink dashboard plugins and the existing
  installer instead of patching Hermes core.
- Shipped Terminal as an honest scaffold: it reserves the dashboard tab and
  reports backend capability discovery, but leaves persistent sessions disabled
  until the Slice 4 tmux or managed-pty backend is implemented.
- Exposed capability flags through status payloads so the UI and tests can
  distinguish available file/code surfaces from deferred terminal persistence
  without leaking tokens, passwords, credentials, or private keys.

Files changed:

- `plugins/hermes-agent/arclink-terminal/` - new dashboard plugin scaffold.
- `plugins/hermes-agent/arclink-drive/dashboard/plugin_api.py` - status
  contract metadata.
- `plugins/hermes-agent/arclink-code/dashboard/plugin_api.py` - status
  contract metadata.
- `bin/install-arclink-plugins.sh` - default Terminal plugin install/enable.
- `tests/test_arclink_plugins.py` - install and sanitized status coverage.
- `README.md` and `AGENTS.md` - default plugin surface documentation.

Verification run:

- `python3 -m py_compile plugins/hermes-agent/arclink-drive/dashboard/plugin_api.py plugins/hermes-agent/arclink-code/dashboard/plugin_api.py plugins/hermes-agent/arclink-terminal/dashboard/plugin_api.py` passed.
- `node --check` passed for Drive, Code, and Terminal dashboard `dist/index.js`.
- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `python3 tests/test_arclink_plugins.py` passed.
- `python3 tests/test_arclink_agent_user_services.py` passed.
- `python3 tests/test_arclink_docker.py` passed.
- `python3 tests/test_deploy_regressions.py` passed.
- `git diff --check` passed.

Known risks:

- Terminal persistence, streaming, scrollback, reload reconnect, grouping, and
  confirmation-gated close/kill remain Slice 4 implementation work.
- Live TLS browser proof remains dependent on an accessible deployed dashboard.

## 2026-05-02 Build Attempt 2 Handoff Repair

Scope: repaired the Attempt 2 BUILD handoff artifacts so machine checks can
distinguish the completed no-secret build slice from the remaining external
P12 live-proof gate.

Files changed:

- `IMPLEMENTATION_PLAN.md` -- clarified that the scale-operations spine and
  live-proof runner already satisfy the current no-secret BUILD scope, and that
  credentialed P12 proof is not a repairable implementation gap without the
  named external credentials.
- `research/BUILD_COMPLETION_NOTES.md` -- added this retry record so the build
  phase has an explicit tracked mutation and a current verification trail.

Rationale:

- Preserved the existing implementation modules and tests because the codebase
  already contains `arclink_fleet.py`, `arclink_action_worker.py`,
  `arclink_rollout.py`, `arclink_live_runner.py`, and their focused tests.
- Recorded the external blocker as Stripe, Cloudflare, Chutes, Telegram,
  Discord, and production host credentials rather than weakening the live gate
  or claiming live proof from fake/no-secret tests.
- Kept the retry to status artifacts because no failing acceptance test or
  missing product-code artifact was identified.

Verification run:

- `git diff --check` passed.
- Exact uppercase fallback-sentinel search across plan, research, docs, Python,
  tests, and config returned no matches.
- `PYTHONPATH=python python3 tests/test_arclink_live_runner.py` passed.
- `PYTHONPATH=python python3 tests/test_arclink_e2e_live.py` passed with the
  expected six credential/live-gated skips.
- `PYTHONPATH=python python3 tests/test_arclink_evidence.py` passed.
- `PYTHONPATH=python python3 tests/test_arclink_live_journey.py` passed.
- `PYTHONPATH=python python3 tests/test_arclink_host_readiness.py` passed.
- `PYTHONPATH=python python3 tests/test_arclink_diagnostics.py` passed.
- `PYTHONPATH=python python3 tests/test_public_repo_hygiene.py` passed.
- `PYTHONPATH=python python3 tests/test_arclink_fleet.py` passed.
- `PYTHONPATH=python python3 tests/test_arclink_action_worker.py` passed.
- `PYTHONPATH=python python3 tests/test_arclink_rollout.py` passed.
- `PYTHONPATH=python python3 tests/test_arclink_hosted_api.py` passed.
- `PYTHONPATH=python python3 tests/test_arclink_dashboard.py` passed.
- `python3 -m py_compile python/arclink_control.py python/arclink_*.py`
  passed.

Known risks:

- Production 12 remains unproven against live providers until the explicit
  credentialed live run is supplied and executed.

## 2026-05-02 Build Retry Validation Closure

Scope: re-ran the active BUILD gate from `IMPLEMENTATION_PLAN.md` after the
Attempt 2 retry guidance. No implementation repair was required: the plan's
remaining actionable BUILD work is limited to externally credentialed live
proof, and the no-secret validation floor passes.

Rationale:

- Preserved the existing scale-operations, operator snapshot, and live-proof
  orchestration work instead of rebuilding completed slices without a failing
  acceptance check.
- Kept the phase artifact to implementation notes only because the retry found
  no missing product-code artifact and no regression in the required no-secret
  checks.
- Continued to treat credentialed P12 live execution as blocked by named
  external accounts and secrets.

Verification run:

- `git diff --check` passed.
- `PYTHONPATH=python python3 tests/test_arclink_live_runner.py` passed.
- `PYTHONPATH=python python3 tests/test_arclink_e2e_live.py` passed with the
  expected six credential/live-gated skips.
- `PYTHONPATH=python python3 tests/test_arclink_evidence.py` passed.
- `PYTHONPATH=python python3 tests/test_arclink_live_journey.py` passed.
- `PYTHONPATH=python python3 tests/test_arclink_host_readiness.py` passed.
- `PYTHONPATH=python python3 tests/test_arclink_diagnostics.py` passed.
- `PYTHONPATH=python python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m py_compile python/arclink_control.py python/arclink_*.py`
  passed.

Known risks:

- Credentialed live proof still requires real Stripe, Cloudflare, Chutes,
  Telegram, Discord, and production host credentials before P12 can be declared
  proven live.

## 2026-05-02 Hosted API Contract Expansion

Scope: expanded the hosted API boundary and API/auth layer with health,
provider state, reconciliation, billing portal, and Telegram/Discord webhook
routes, plus corresponding test coverage.

Rationale:

- Added `GET /health` as a public liveness check (DB reachable = ok/degraded)
  so load balancers and monitoring can probe the API without auth.
- Added `GET /user/provider-state` and `GET /admin/provider-state` to surface
  current provider, default model, and per-deployment model assignments through
  the session-authenticated API boundary.
- Added `GET /admin/reconciliation` to expose Stripe-vs-local entitlement drift
  through the admin session gate, consuming the existing
  `detect_stripe_reconciliation_drift` helper.
- Added `POST /webhooks/telegram` and `POST /webhooks/discord` routes to the
  hosted router, delegating to the existing runtime adapter handlers with
  proper error shaping.
- Removed redundant `_rowdict` wrappers from `arclink_api_auth.py` and
  `arclink_dashboard.py`, using the shared `rowdict` from `arclink_boundary`.

Files changed:

- `python/arclink_hosted_api.py` (733 -> 777 lines) -- new routes and handlers.
- `python/arclink_api_auth.py` (813 -> 862 lines) -- `read_provider_state_api`,
  `read_admin_reconciliation_api`, removed `_rowdict`.
- `python/arclink_dashboard.py` -- removed `_rowdict`.
- `tests/test_arclink_hosted_api.py` (26 -> 30 test functions) -- health,
  provider state, reconciliation, billing portal tests.
- Research docs updated to reflect new line counts, test counts, and P1 gap
  narrowing.

Known risks:

- Hosted API is still not deployed behind a production reverse proxy or
  identity provider.
- Provider state read exposes deployment model assignments; access control is
  session-scoped but not deployment-scoped.
- Reconciliation drift detection depends on local DB state; live Stripe API
  comparison remains E2E-gated.

## 2026-05-02 Remove Redundant _rowdict Wrappers

Scope: removed private `_rowdict` wrapper functions from `arclink_api_auth.py`
and `arclink_dashboard.py`, replacing all call sites with the shared `rowdict`
helper already imported from `arclink_boundary`.

Rationale:

- Both modules had identical `_rowdict(row)` one-liners that delegated to the
  shared `rowdict` from `arclink_boundary`. The indirection added no value and
  obscured the actual dependency.
- The shared `rowdict` is the canonical row-to-dict helper across the codebase;
  using it directly makes the ownership and contract clearer.

Files changed:

- `python/arclink_api_auth.py` - removed `_rowdict` definition (3 lines),
  replaced 5 call sites with `rowdict`.
- `python/arclink_dashboard.py` - removed `_rowdict` definition (3 lines),
  replaced 6 call sites with `rowdict`.

Known risks:

- None. Pure rename with no behavioral change; `rowdict` was already the
  underlying implementation.

## 2026-05-01 Active Lint-Repair Gate Build

Scope: completed the current BUILD gate from `IMPLEMENTATION_PLAN.md` and
`research/RALPHIE_LINT_BLOCKER_REPAIR_STEERING.md` without adding hosted
request signing, production frontend work, live bot clients, or provider/host
mutation.

Rationale:

- Validated public onboarding channel and identity through the shared
  onboarding validator before rate limiting so invalid channels fail without
  writing `rate_limits`.
- Kept the repair inside the existing Python dashboard, API/auth, product
  surface, and public-bot helper boundaries because those are the accepted
  no-secret contracts for this build slice.
- Preserved domain-specific `ArcLinkApiAuthError` and
  `ArcLinkDashboardError` responses while keeping the generic product-surface
  exception path user-safe.
- Reused the shared onboarding rate-limit helper for public bot turns instead
  of adding Telegram or Discord client behavior in this pass.

Verification run:

- The invalid-channel acceptance probe printed
  `ArcLinkOnboardingError unsupported ArcLink onboarding channel: email` and
  `0`.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_product_surface.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m py_compile python/arclink_control.py python/arclink_*.py`
  passed.
- `python3 -m ruff check python/arclink_dashboard.py python/arclink_api_auth.py python/arclink_product_surface.py python/arclink_public_bots.py tests/test_arclink_dashboard.py tests/test_arclink_api_auth.py tests/test_arclink_product_surface.py tests/test_arclink_public_bots.py`
  passed.
- `git diff --check` passed.

Known risks:

- The API/auth/RBAC layer is still a no-secret helper contract, not hosted
  production identity.
- The product surface remains a stdlib WSGI prototype.
- Live Stripe, Cloudflare, Chutes, Telegram, Discord, Notion, OAuth, and host
  execution remain E2E-gated.

## 2026-05-01 Production Dashboard Contract Build

Scope: advanced the Production Dashboard plan without introducing a frontend
toolchain by making the user/admin dashboard read models explicitly enumerate
the production sections the future web app must render.

Rationale:

- Extended the existing Python dashboard/API contracts instead of adding
  Next.js/Tailwind in this slice, because this checkout has no frontend
  toolchain yet and the implementation plan says the production web app should
  follow stable API/auth contracts.
- Added user dashboard section contracts for deployment health, access links,
  bot setup, files, code, Hermes, qmd/memory freshness, skills, model, billing,
  security, and support.
- Added admin dashboard section contracts for onboarding, users, deployments,
  payments, infrastructure, bots, security/abuse, releases/maintenance,
  logs/events, audit, and queued actions.
- Kept the local WSGI product surface as a no-secret prototype that displays
  those sections, with live provider mutation still gated.

Verification run:

- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_product_surface.py` passed.
- `python3 tests/test_arclink_admin_actions.py` passed.
- `python3 tests/test_arclink_onboarding.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m py_compile python/arclink_control.py python/arclink_*.py`
  passed.
- `python3 -m ruff check python/arclink_dashboard.py python/arclink_product_surface.py tests/test_arclink_dashboard.py tests/test_arclink_product_surface.py`
  passed.
- `git diff --check` passed.

Known risks:

- This is still not the production Next.js/Tailwind dashboard.
- Browser workflow coverage for the final frontend remains a follow-up.
- Live Stripe, Cloudflare, Chutes, Telegram, Discord, Notion, and host
  execution paths remain E2E-gated.

## 2026-05-01 Product Surface Lint-Blocker Repair

Scope: closed the immediate BUILD gate for the local no-secret ArcLink product
surface without expanding production dashboard, RBAC, live adapter, or host
mutation work.

Rationale:

- Added a tiny inline SVG favicon response in the existing stdlib WSGI surface
  instead of introducing static asset plumbing or a frontend framework, because
  the route only needs to stop browser smoke from reporting a harmless 404.
- Reconciled coverage notes with the accepted responsive browser-smoke evidence:
  narrow mobile around 390px and desktop around 1440px for `/`,
  `/onboarding/onb_surface_fixture`, `/user`, and `/admin`, with no page-level
  horizontal overflow.
- Kept the WSGI product surface documented as a replaceable prototype.

Verification run:

- `python3 tests/test_arclink_product_surface.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_arclink_onboarding.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_admin_actions.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_arclink_schema.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m py_compile python/arclink_control.py python/arclink_*.py`
  passed.
- `python3 -m ruff check python/arclink_product_surface.py python/arclink_public_bots.py tests/test_arclink_product_surface.py tests/test_arclink_public_bots.py`
  passed.
- Favicon smoke returned `200 image/svg+xml`.
- `git diff --check` passed.

Known risks:

- Production browser automation still belongs with the future production
  frontend.
- Production API/auth/RBAC, live provider adapters, and host execution remain
  gated follow-up work.

## 2026-05-01 API/Auth Boundary Build

Scope: completed the next no-secret ArcLink API/auth boundary slice without
introducing a production web framework or live provider mutation.

Rationale:

- Added Python helper APIs instead of introducing FastAPI/Next.js routing in
  this pass, because the current repo patterns already expose ArcLink behavior
  through tested Python boundaries and the plan calls for API/auth contracts to
  stabilize before the production dashboard.
- Stored user/admin session tokens and CSRF tokens only as hashes, with
  explicit rate-limit hooks for public onboarding and MFA-ready admin mutation
  gating.
- Kept TOTP enrollment secret material as `secret://` references and masked
  those references in read output, leaving real TOTP code verification for the
  production auth provider/E2E phase.

Verification run:

- `python3 tests/test_arclink_schema.py` passed.
- `python3 tests/test_arclink_api_auth.py` passed.
- `python3 tests/test_arclink_onboarding.py` passed.
- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_admin_actions.py` passed.
- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_arclink_product_surface.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m py_compile python/arclink_control.py python/arclink_*.py` passed.
- `git diff --check` passed.

Known risks:

- This is still a helper/API contract layer, not hosted production browser
  authentication, OAuth, or a deployed HTTP API.
- TOTP is schema- and gate-ready, but real one-time-code validation remains a
  production auth/E2E follow-up.
- Live Stripe, Cloudflare, Chutes, Telegram, Discord, Notion, and host
  execution paths remain gated.

## 2026-05-01 Product Surface Foundation Build

Scope: completed the first Phase 9 no-secret ArcLink product-surface slice
without enabling real Docker, Cloudflare, Chutes, Stripe, Telegram, Discord, or
host mutation.

Rationale:

- Added a small stdlib Python WSGI surface instead of introducing Next.js now,
  because the current acceptance criteria need a runnable no-secret product
  workflow and clean API/read-model boundaries before production auth, RBAC,
  routing, and frontend build tooling are selected.
- Rendered the first screen as the usable onboarding workflow rather than a
  marketing-only page, with fake checkout, user dashboard, admin dashboard, and
  queued admin-action routes backed by existing `arclink_*` helpers.
- Added deterministic Telegram/Discord public bot adapter skeletons that share
  the same onboarding session semantics as web onboarding and keep public bot
  state separate from private user-agent bot tokens.

Verification run:

- `python3 tests/test_arclink_product_surface.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.
- `python3 tests/test_arclink_onboarding.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_admin_actions.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m py_compile python/arclink_control.py python/arclink_*.py` passed.
- `python3 -m ruff check python/arclink_product_surface.py python/arclink_public_bots.py tests/test_arclink_product_surface.py tests/test_arclink_public_bots.py` passed.
- `git diff --check` passed.

Known risks:

- The local WSGI product surface is a replaceable prototype, not the production
  Next.js/Tailwind dashboard.
- Browser session auth, RBAC, CSRF/rate limits, hosted routes, real Telegram
  and Discord clients, live Stripe checkout/webhooks, live provider/edge
  adapters, and action executors remain E2E-gated follow-ups.

## 2026-05-01 Executor Replay/Dependency Consistency Repair Build

Scope: completed the active `IMPLEMENTATION_PLAN.md` executor
replay/dependency consistency repair without enabling real Docker, Cloudflare,
Chutes, Stripe, or host mutation.

Rationale:

- Added stable operation-digest checks for fake Cloudflare DNS, Cloudflare
  Access, Chutes key lifecycle, and rollback idempotency keys so key reuse with
  changed inputs is rejected before stored results are returned.
- Kept Chutes replay strict by returning stored action and stored secret
  reference only for identical replay, and rejecting action or secret-ref drift.
- Made fake Docker Compose planning reject `depends_on` references to missing
  rendered services, matching the dependency validation real Compose would
  enforce.

Verification run:

- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m py_compile python/arclink_executor.py python/arclink_provisioning.py` passed.
- `python3 -m ruff check python/arclink_executor.py tests/test_arclink_executor.py` passed.
- `git diff --check` passed.

Known risks:

- Real Docker Compose execution, Cloudflare mutation, Chutes key lifecycle,
  Stripe live actions, dashboard/API wiring, and public bot onboarding remain
  E2E-gated follow-ups.

## 2026-05-01 Executor Lint-Risk Repair Build

Scope: completed the active `IMPLEMENTATION_PLAN.md` executor lint-risk repair
without enabling real Docker, Cloudflare, Chutes, Stripe, or host mutation.

Rationale:

- Returned stored fake Docker Compose `applied` replay state before resolving
  current secret material, while keeping rendered-intent digest checks ahead
  of replay.
- Rejected `fake_fail_after_services <= 0` with `ArcLinkExecutorError` so the
  fake adapter cannot accidentally apply a service for a zero limit.
- Replaced rollback destructive-delete detection with an explicit helper and
  covered state-root and vault-delete action variants.
- Added a Cloudflare DNS record type allowlist for `A`, `AAAA`, `CNAME`, and
  `TXT` before fake/live apply.

Verification run:

- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m py_compile python/arclink_executor.py python/arclink_provisioning.py` passed.
- `git diff --check` passed.

Known risks:

- Real Docker Compose execution, Cloudflare mutation, Chutes key lifecycle,
  Stripe live actions, dashboard/API wiring, and public bot onboarding remain
  E2E-gated follow-ups.

## 2026-05-01 Executor Idempotency Digest Repair Build

Scope: completed the `IMPLEMENTATION_PLAN.md` executor digest repair without
enabling real Docker, Cloudflare, Chutes, Stripe, or host mutation.

Rationale:

- Stored the rendered `intent_digest` in fake Docker Compose run state so
  explicit idempotency keys are bound to the provisioning intent they first
  applied or partially applied.
- Rejected explicit Docker Compose idempotency-key reuse when the rendered
  intent digest changes, instead of treating the request as a replay or stale
  partial resume.
- Kept implicit idempotency based on the digest unchanged, so callers that do
  not provide an explicit key still get digest-scoped fake runs.

Verification run:

- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m py_compile python/arclink_executor.py python/arclink_provisioning.py` passed.
- `git diff --check` passed.

Known risks:

- Real Docker Compose execution, Cloudflare mutation, Chutes key lifecycle,
  Stripe live actions, dashboard/API wiring, and public bot onboarding remain
  E2E-gated follow-ups.

## 2026-05-01 Provider, Edge, And Rollback Fake Executor Build

Scope: completed Tasks 4 and 5 from `IMPLEMENTATION_PLAN.md` without enabling
real Cloudflare, Chutes, Stripe, Docker, or host mutation.

Rationale:

- Extended the existing `arclink_executor` module instead of introducing a
  second provider executor package, so all mutating boundaries still share the
  same explicit live/E2E gate and secret-free result objects.
- Kept Cloudflare DNS/Access and Chutes lifecycle behavior fake and stateful by
  idempotency key, which lets unit tests prove create/rotate/revoke, replay,
  and access-policy planning without live provider credentials.
- Made rollback execution consume a plan, stop rendered services, remove only
  unhealthy service markers, preserve customer state roots, and leave
  `secret://` references for review. The fake result exposes appendable audit
  event names but does not mutate the control-plane database from the adapter.

Verification run:

- `python3 tests/test_arclink_product_config.py` passed.
- `python3 tests/test_arclink_schema.py` passed.
- `python3 tests/test_arclink_chutes_and_adapters.py` passed.
- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_arclink_onboarding.py` passed.
- `python3 tests/test_arclink_ingress.py` passed.
- `python3 tests/test_arclink_access.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_arclink_admin_actions.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m py_compile python/arclink_control.py python/arclink_*.py` passed.
- `python3 -m ruff check python/arclink_executor.py tests/test_arclink_executor.py` passed.
- `git diff --check` passed.

Known risks:

- Real Cloudflare DNS/tunnel/access mutation, Chutes key lifecycle, Docker
  rollback effects, Stripe live admin actions, and hosted dashboard/API action
  wiring remain E2E-only follow-ups.

## 2026-05-01 Docker Compose Fake Executor Build

Scope: completed Task 3 from `IMPLEMENTATION_PLAN.md` without enabling real
Docker Compose mutation.

Rationale:

- Extended the existing `arclink_executor` boundary instead of adding a second
  compose runner, so execution continues to consume the dry-run provisioning
  intent as the single source of service, volume, label, and secret semantics.
- Kept the fake adapter stateful by idempotency key, which lets tests exercise
  partial failure, resume, and replay behavior without writing compose files or
  starting containers.
- Planned env file, compose file, project name, volumes, labels, and service
  start order from rendered intent, while secret materialization still returns
  only `/run/secrets/*` targets.

Verification run:

- `python3 tests/test_arclink_product_config.py` passed.
- `python3 tests/test_arclink_schema.py` passed.
- `python3 tests/test_arclink_chutes_and_adapters.py` passed.
- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_arclink_onboarding.py` passed.
- `python3 tests/test_arclink_ingress.py` passed.
- `python3 tests/test_arclink_access.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_arclink_admin_actions.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m py_compile python/arclink_control.py python/arclink_*.py` passed.
- `python3 -m ruff check python/arclink_executor.py tests/test_arclink_executor.py` passed.
- `git diff --check` passed.

Known risks:

- Real `docker compose` invocation remains an E2E-only follow-up. Provider and
  edge mutation adapters, rollback execution, and hosted dashboard/API flows
  remain pending.

## 2026-05-01 Live Executor Boundary Build

Scope: completed the first live-executor boundary slice from
`IMPLEMENTATION_PLAN.md` without enabling live host or provider mutation.

Rationale:

- Added a dedicated `arclink_executor` module instead of putting execution
  state into the dry-run provisioning renderer. The renderer remains the
  source of service/DNS/access intent; the executor consumes that intent.
- Made every mutating executor operation fail closed unless an explicit
  live/E2E flag is present. Unit tests can still exercise the boundary with a
  fake adapter name and fake secret resolver.
- Added resolver contracts that materialize `secret://` references to
  `/run/secrets/*` paths while keeping plaintext secret values inside resolver
  internals and out of returned results.

Verification run:

- `python3 tests/test_arclink_product_config.py` passed.
- `python3 tests/test_arclink_schema.py` passed.
- `python3 tests/test_arclink_chutes_and_adapters.py` passed.
- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_arclink_onboarding.py` passed.
- `python3 tests/test_arclink_ingress.py` passed.
- `python3 tests/test_arclink_access.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_arclink_admin_actions.py` passed.
- `python3 tests/test_arclink_dashboard.py` passed.
- `python3 tests/test_arclink_executor.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m py_compile python/arclink_control.py python/arclink_*.py` passed.
- `git diff --check` passed.

Known risks:

- Docker Compose execution, Cloudflare mutation, Chutes key lifecycle, Stripe
  actions, and rollback execution are still fakeable contracts only; real
  mutation remains an E2E-only follow-up.

## 2026-05-01 Entitlement Preservation Repair Build

Scope: completed the active entitlement preservation repair from
`IMPLEMENTATION_PLAN.md` without requiring live secrets.

Rationale:

- Made `upsert_arclink_user()` treat omitted `entitlement_state` as a
  profile-only update instead of an implicit write to `none`. This preserves
  the existing helper API for profile fields while keeping
  `set_arclink_user_entitlement()`, Stripe webhooks, and admin comp helpers as
  explicit entitlement writers.
- Kept new users defaulting to `none` on insert, with an empty
  `entitlement_updated_at` when no entitlement mutation was requested.
- Updated public onboarding deployment preparation to avoid passing an
  implicit `none`, so returning paid or comped users keep entitlement state and
  timestamp while onboarding resumes.

Verification run:

- `python3 tests/test_arclink_schema.py` passed.
- `python3 tests/test_arclink_onboarding.py` passed.
- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `python3 -m py_compile python/arclink_control.py python/arclink_onboarding.py python/arclink_entitlements.py` passed.
- `git diff --check` passed.

Known risks:

- Live Stripe checkout/webhook delivery, Cloudflare, Chutes key lifecycle,
  public bot credentials, Notion, dashboards, and deployment-host execution
  remain E2E prerequisites.

## 2026-05-01 Public Onboarding Contract Build

Scope: completed the Phase 7 no-secret public onboarding contract from
`IMPLEMENTATION_PLAN.md`.

Rationale:

- Added durable `arclink_onboarding_sessions` and
  `arclink_onboarding_events` rows instead of binding website/bot state to the
  private ArcLink user-agent onboarding tables. Public Telegram and Discord ids
  are channel hints, not private deployment bot credentials.
- Kept Stripe checkout behind the existing fake adapter boundary with
  deterministic idempotency-key session ids, instead of adding a live Stripe SDK
  dependency before E2E secrets and hosted callback URLs exist.
- Connected checkout success through the existing signed entitlement webhook
  and deployment gate. Onboarding observes the lifted gate and records funnel
  events; it does not grant provisioning directly.

Verification run:

- `python3 -m py_compile python/arclink_control.py python/arclink_adapters.py python/arclink_entitlements.py python/arclink_onboarding.py python/arclink_provisioning.py` passed.
- `python3 tests/test_arclink_product_config.py` passed.
- `python3 tests/test_arclink_schema.py` passed.
- `python3 tests/test_arclink_chutes_and_adapters.py` passed.
- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_arclink_onboarding.py` passed.
- `python3 tests/test_arclink_ingress.py` passed.
- `python3 tests/test_arclink_access.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_model_providers.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.

Known risks:

- Live Stripe checkout creation, hosted success/cancel URLs, public Telegram
  and Discord bot delivery, Cloudflare, Chutes key lifecycle, and deployment
  execution remain E2E prerequisites.

## 2026-05-01 Stripe Webhook Transaction Ownership Guard Build

Scope: completed the Stripe webhook transaction ownership guard from
`IMPLEMENTATION_PLAN.md` without requiring live secrets.

Rationale:

- Rejected caller-owned active SQLite transactions before starting the Stripe
  webhook transaction instead of attempting nested transaction/savepoint
  ownership. The handler's existing atomicity contract is simpler when it owns
  the whole webhook transaction.
- Kept replayable failure marking unchanged for handler-owned transactions, so
  supported webhook failures still roll back entitlement side effects and can
  be replayed.

Verification run:

- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 -m py_compile python/arclink_entitlements.py python/arclink_control.py tests/test_arclink_entitlements.py` passed.
- `python3 -m ruff check python/arclink_entitlements.py python/arclink_control.py tests/test_arclink_entitlements.py` passed.
- `python3 -m pyflakes python/arclink_entitlements.py python/arclink_control.py tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.

Known risks:

- Live Stripe delivery, checkout orchestration, Cloudflare, Chutes key
  lifecycle, bot credentials, Notion, and deployment-host execution remain E2E
  prerequisites.

## 2026-05-01 Stripe Invoice Parent Compatibility Build

Scope: completed the current Stripe invoice compatibility repair from
`IMPLEMENTATION_PLAN.md` without live secrets.

Rationale:

- Extended the existing Stripe payload extraction helpers instead of adding a
  Stripe SDK dependency or a second invoice parser. The current code only needs
  stable, no-secret extraction from verified webhook JSON.
- Preserved legacy top-level metadata, top-level subscription id, and
  `parent.subscription` behavior while adding the current
  `parent.subscription_details` shape.

Verification run:

- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 -m py_compile python/arclink_entitlements.py python/arclink_control.py tests/test_arclink_entitlements.py` passed.
- `python3 -m ruff check python/arclink_entitlements.py python/arclink_control.py tests/test_arclink_entitlements.py` passed.
- `python3 -m pyflakes python/arclink_entitlements.py python/arclink_control.py tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.

Known risks:

- Live Stripe delivery, checkout orchestration, Cloudflare, Chutes key
  lifecycle, bot credentials, Notion, and deployment-host execution remain E2E
  prerequisites.

## 2026-05-01 Stripe Webhook Atomicity Build

Scope: completed the Stripe webhook atomicity repair from
`IMPLEMENTATION_PLAN.md` without requiring live secrets.

Rationale:

- Kept the existing SQLite/Python control-plane helpers and added opt-in
  `commit=False` paths instead of introducing a new transaction abstraction.
  This preserves public helper auto-commit behavior while letting Stripe
  webhook handling defer all entitlement side effects to one transaction.
- Kept failed webhook attempts replayable by rolling back partial entitlement
  work first, then recording the webhook row as `failed` in a separate minimal
  marker write.

Verification run:

- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_arclink_schema.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_arclink_ingress.py` passed.
- `python3 tests/test_arclink_access.py` passed.
- `python3 -m py_compile python/arclink_entitlements.py python/arclink_control.py tests/test_arclink_entitlements.py` passed.
- `python3 -m ruff check python/arclink_entitlements.py python/arclink_control.py tests/test_arclink_entitlements.py` passed.
- `python3 -m pyflakes python/arclink_entitlements.py python/arclink_control.py tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_public_repo_hygiene.py` passed.
- `git diff --check` passed.

Known risks:

- Live Stripe delivery, checkout orchestration, Cloudflare, Chutes key
  lifecycle, bot credentials, Notion, and deployment-host execution remain E2E
  prerequisites.

## 2026-05-01 Build Retry

Scope: completed the lint-held entitlement, Tailscale timeout, and provisioning
secret-resolution build slice from `IMPLEMENTATION_PLAN.md` without requiring
live secrets.

Rationale:

- Kept the existing Docker/Python control-plane path instead of adding a new
  SaaS shell because the current plan prioritizes no-secret provisioning
  contracts and regression coverage.
- Preserved global manual comp behavior as a support override, and added
  regression coverage proving it advances all entitlement-gated deployments for
  the user.
- Kept targeted deployment comp as a deployment-scoped override that does not
  mutate the user's global entitlement state or unblock unrelated deployments.
- Kept Compose `_FILE` secrets for stock images where supported, with explicit
  resolver-required fallbacks for application tokens before live execution.

Verification run:

- `python3 tests/test_arclink_entitlements.py` passed.
- `python3 tests/test_arclink_provisioning.py` passed.
- `python3 tests/test_deploy_regressions.py` passed.

Known risks:

- Live Stripe, Cloudflare, Chutes key lifecycle, bot credentials, Notion, and
  deployment-host execution remain E2E prerequisites.
- The current build validates rendered provisioning intent only; it does not
  start live per-deployment containers.

## 2026-05-05 Drive Slice 2 Hardening Build

Scope: advanced the Slice 2 ArcLink Drive Google Drive foundation tasks from
`IMPLEMENTATION_PLAN.md`, focused on root safety, upload conflict policy, batch
partial-failure surfacing, and focused plugin regression coverage.

Rationale:

- Kept uploads reject-by-default for existing local filenames so drag/drop and
  file-picker uploads cannot silently overwrite user files.
- Added explicit `keep-both` as the only local upload conflict alternative,
  reusing the existing copy/duplicate conflict naming behavior instead of
  adding a replace path without overwrite confirmation UI.
- Rejected WebDAV `keep-both` because there is no tested adapter that can prove
  a non-overwriting remote destination name; WebDAV reject mode uses
  `If-None-Match: *` to avoid silent remote overwrite.

Verification run:

- `python3 -m py_compile plugins/hermes-agent/arclink-drive/dashboard/plugin_api.py` passed.
- `python3 tests/test_arclink_plugins.py` passed.
- `node --check plugins/hermes-agent/arclink-drive/dashboard/dist/index.js` passed.
- `git diff --check` passed.

Known risks:

- Browser runtime proof against a live Hermes dashboard was not available in
  this build pass, so mobile layout and interactive Drive proof remain runtime
  verification items.
- The repository already contained broad unrelated dirty and untracked changes;
  this pass stayed scoped to Drive API/UI, focused plugin tests, and these
  implementation notes.

## 2026-05-05 Drive Slice 2 Attempt 2 Root Boundary Repair

Scope: repaired the consensus-held Drive Slice 2 blocker by enforcing root
boundary checks while constructing local list and search items.

Rationale:

- Kept direct symlink-escape requests as explicit 403 errors, preserving the
  existing path safety contract.
- Pruned symlink-escaped children from list and search traversal before item
  metadata is built, so local Drive views do not expose size, modified time, or
  type information for files outside the selected root.
- Added focused regression coverage for both symlinked files and symlinked
  folders that point outside the vault.

Verification run:

- `python3 -m py_compile plugins/hermes-agent/arclink-drive/dashboard/plugin_api.py` passed.
- `python3 tests/test_arclink_plugins.py` passed.
- `node --check plugins/hermes-agent/arclink-drive/dashboard/dist/index.js` passed.
- `git diff --check` passed.

Known risks:

- Browser runtime proof against a live Hermes dashboard remains a test-phase
  item; this retry only repaired the local API boundary blocker.

## 2026-05-05 Drive Slice 2 Browser Batch And Confirmation Build

Scope: advanced the remaining Drive browser UX tasks from
`IMPLEMENTATION_PLAN.md`, focused on selected-item batch operations, partial
failure surfacing, and deliberate confirmation gates.

Rationale:

- Kept the work inside the native Hermes dashboard plugin bundle instead of
  introducing an external Drive app or Hermes core changes.
- Added a small Drive-local confirmation dialog rather than a broad shared UI
  framework detour; the immediate blocker was risky Drive actions, not a full
  cross-plugin component system.
- Used the existing `/batch` API contract for restore, copy, and move so the UI
  can report per-item failures without implying all-or-nothing success.

Verification run:

- `python3 -m py_compile plugins/hermes-agent/arclink-drive/dashboard/plugin_api.py plugins/hermes-agent/arclink-code/dashboard/plugin_api.py plugins/hermes-agent/arclink-terminal/dashboard/plugin_api.py` passed.
- `python3 tests/test_arclink_plugins.py` passed.
- `node --check plugins/hermes-agent/arclink-drive/dashboard/dist/index.js` passed.
- `node --check plugins/hermes-agent/arclink-code/dashboard/dist/index.js` passed.
- `node --check plugins/hermes-agent/arclink-terminal/dashboard/dist/index.js` passed.
- `git diff --check` passed.

Known risks:

- Live TLS desktop/mobile browser proof was not available in this build pass.
- Rename, new-file, and folder-path entry still use native prompt dialogs; the
  deliberate in-app confirmation work in this slice covers overwrite conflict,
  move, trash, and selected trash flows.

## 2026-05-06 Workspace Plugin Handoff Validation

Scope: completed the final handoff lane for the native ArcLink Drive, Code, and
Terminal workspace plugin mission without running a live deploy.

Rationale:

- Kept the native workspace suite in Hermes dashboard plugins and ArcLink
  wrappers rather than adding a separate workspace application or patching
  Hermes core.
- Preserved managed-pty terminal persistence as the tested backend and kept
  streaming transport documented as future work because the proven dashboard
  host path uses bounded polling.
- Treated deployment as an operator-owned next step; this pass curated commits
  and validation without pushing or running `./deploy.sh upgrade`.

Verification run:

- Plugin Python compile, plugin JavaScript syntax checks, shell syntax checks,
  and `git diff --check` passed.
- Focused Python suites for plugins, deploy, Docker, provisioning, dashboards,
  live runner/journey, health, bot delivery, public bots, sovereign worker,
  Chutes/adapters, run-agent-code-server, and agent user services passed.
- Web unit smoke, lint, production build, and Playwright browser tests passed;
  the browser run reported 41 passing checks with 3 expected desktop skips for
  mobile-only layout assertions.

Known risks:

- This handoff did not push commits or run the canonical live host upgrade.
- Live release state and Docker health remain the previously recorded proof
  status until an operator requests deployment.

## 2026-05-08 Ralphie P0 Notion And SSOT Boundary Build

Scope: advanced the highest-priority unchecked security boundary items from
`IMPLEMENTATION_PLAN.md`: exact live Notion reads and destructive SSOT update
payloads.

Rationale:

- Scoped `notion.fetch` and `notion.query` inside the existing Notion index
  root model instead of adding a separate privileged-read mode. Exact reads now
  allow configured roots, active indexed pages, and parent-walk-proven children;
  out-of-root live reads are denied and audited.
- Rejected destructive SSOT fields at payload validation time rather than
  inventing an approval rail in this pass. The public broker already rejects
  archive/delete/trash operations, and no explicit destructive approval model
  exists yet.

Verification run:

- `python3 -m py_compile python/arclink_control.py` passed.
- `python3 tests/test_arclink_notion_knowledge.py` passed.
- `python3 tests/test_ssot_broker.py` passed.

Known risks:

- A future operator-approved destructive Notion rail would need a distinct
  policy, audit, and UI flow; this build intentionally fails closed.

## 2026-05-08 Ralphie Shared Host Health Probe Build

Scope: advanced Slice 4 / Priority 3 by closing the health DB probe failure
gap from `IMPLEMENTATION_PLAN.md`.

Rationale:

- Kept health behavior in `bin/health.sh` instead of adding a separate
  diagnostic runner. The existing shell health surface is what install,
  upgrade, and operators already use.
- Treated Python probe command failures as hard health failures even outside
  strict mode, while preserving structured `WARN`, `FAIL`, and `OK` output for
  expected degraded states.

Verification run:

- `bash -n bin/health.sh tests/test_health_regressions.py` passed.
- `python3 tests/test_health_regressions.py` passed.
- `python3 tests/test_deploy_regressions.py` passed.

Known risks:

- This pass did not run live `./deploy.sh health` or mutate the host. Remaining
  Slice 4 Docker/operations tasks still need dedicated implementation or
  validation before BUILD can be declared complete.

## 2026-05-08 Ralphie Shared Host Root Unit Build

Scope: advanced Slice 4 / Priority 3 Shared Host operations by verifying the
completed upstream-branch and bare-metal dependency fixes, then repairing root
systemd unit path rendering for custom config/repo paths.

Rationale:

- Kept the production upstream contract on `main`, matching the existing
  upgrade guard, config examples, and deploy regressions instead of widening
  production upgrades to arbitrary branches.
- Added/verified `jq` and `iproute2` in bare-metal bootstrap because existing
  pins and health commands depend on those host tools.
- Rendered root units with systemd-native quoting and specifier escaping rather
  than shell wrapping. Newline/carriage-return and dollar-sign paths are
  rejected because they cannot be made legible or portable in generated unit
  files.

Verification run:

- `bash -n deploy.sh bin/*.sh test.sh` passed.
- `python3 tests/test_deploy_regressions.py` passed.
- `python3 tests/test_arclink_enrollment_provisioner_regressions.py` passed.
- `git diff --check` passed.

Known risks:

- This pass did not run live install/upgrade or touch `/etc/systemd/system`.
- Remaining Slice 4 items around Nextcloud enablement, Docker health, Docker
  release state, and Docker trust boundaries are still open.

## 2026-05-08 Ralphie Onboarding Recovery Build

Scope: advanced Slice 5 / Priority 4 by closing local no-secret onboarding
recovery gaps for Curator auto-provision, operator notifications, denied
sessions, backup skip, and public bot cancel.

Rationale:

- Surfaced auto-provision failures through the existing Curator session state
  instead of introducing a second retry tracker. `onboarding_sessions` already
  drives `/status`, so durable `provision_error` plus one user notification is
  the narrowest recoverable path.
- Redacted generated dashboard passwords from operator notifications by
  default and kept user credential delivery in the existing completion bundle,
  with an explicit opt-in env for credential-bearing operator channels.
- Treated backup `skip` as durable user intent for the completed-session
  backfill, while preserving `/setup-backup` as the user-initiated recovery
  path.
- Made public `/cancel` close active onboarding/checkout state instead of only
  sub-workflow metadata; live deployments are not cancelled from public chat.

Verification run:

- `python3 -m py_compile python/arclink_control.py python/arclink_enrollment_provisioner.py python/arclink_onboarding.py python/arclink_public_bots.py python/arclink_onboarding_flow.py` passed.
- `python3 tests/test_arclink_enrollment_provisioner_regressions.py` passed.
- `python3 tests/test_arclink_onboarding_prompts.py` passed.
- `python3 tests/test_arclink_public_bots.py` passed.

Known risks:

- Completion acknowledgement retry/recovery and public Notion/backup command
  depth remain open Slice 5 work.
- This pass did not run live bot, Stripe, host provisioning, or deployment
  flows.

## 2026-05-08 Ralphie Knowledge Freshness Build

Scope: completed Slice 6 / Priority 5 knowledge freshness and generated
content safety gaps for PDF ingest, memory synthesis, SSOT event batching, and
the ArcLink resources skill.

Rationale:

- Hashed the resolved PDF vision endpoint inside the pipeline signature instead
  of writing the URL into generated markdown. This preserves change detection
  without leaking endpoint userinfo, query values, or private hostnames.
- Moved PDF ingest fast-path checks behind source SHA-256 comparison so
  same-size, same-second PDF rewrites regenerate sidecars.
- Replaced memory synthesis file freshness fingerprints with content hashes for
  scanned source files while keeping raw hashes out of model prompts.
- Added DB row claims for Notion webhook batch processing. Pending events move
  to `processing` with a claim id before work starts; stale processing claims
  can be reclaimed after a lease.
- Removed the unsafe GitHub raw fallback installer URL from the resources skill
  and replaced stale Raven wording with current ArcLink/Curator wording.

Verification run:

- `python3 tests/test_pdf_ingest_env.py` passed.
- `python3 tests/test_memory_synthesizer.py` passed.
- `python3 tests/test_arclink_ssot_batcher.py` passed.
- `python3 tests/test_arclink_resources_skill.py` passed.
- `python3 -m py_compile bin/pdf-ingest.py python/arclink_memory_synthesizer.py python/arclink_control.py python/arclink_ssot_batcher.py` passed.
- `bash -n skills/arclink-resources/scripts/show-resources.sh deploy.sh bin/*.sh test.sh` passed.
- `git diff --check` passed.

Known risks:

- This pass did not run live Notion webhook ingestion, live qmd reindexing,
  PDF vision model calls, or live memory synthesis LLM calls.
- Slice 7 documentation and validation coverage remains open before the full
  Ralphie BUILD can be declared complete.
