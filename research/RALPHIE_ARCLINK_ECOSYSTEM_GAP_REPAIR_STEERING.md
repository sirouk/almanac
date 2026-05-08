# Ralphie Steering: ArcLink Ecosystem Gap Repair

## Current Mission

Ralphie must repair the verified ArcLink ecosystem gaps from the May 2026 full
repository audit. This is an end-to-end hardening mission across Shared Host,
Shared Host Docker, Sovereign Control Node, hosted web/API, public/private
onboarding, Hermes runtime plugins, qmd/Notion/SSOT knowledge rails, docs,
validation, and operator journeys.

This file is a mission backlog, not a speculative wishlist. Each item below
comes from static repository inspection with concrete code references. Ralphie
should treat code and tests as truth when docs disagree, then update docs and
tests to make the new truth durable.

## Operating Guardrails

- Read `AGENTS.md` before changing deploy, onboarding, service, runtime, or
  knowledge code.
- Do not read `arclink-priv/`, user homes, secret files, live token files, or
  private runtime state unless a focused fix requires a specific non-secret
  path and the operator explicitly authorizes it.
- Do not print, log, commit, or quote secrets. Avoid argv/env exposure of
  bootstrap tokens, API keys, bot tokens, OAuth data, deploy keys, and `.env`
  contents.
- Do not edit Hermes core. Use ArcLink wrappers, plugins, hooks, generated
  config, services, or docs.
- Do not run `./deploy.sh upgrade`, `./deploy.sh install`, live Stripe,
  Cloudflare, Tailscale, Telegram, Discord, or host-mutating production flows
  unless the operator explicitly asks during this mission.
- Prefer narrow, tested fixes over broad rewrites. Add regression tests for
  every boundary or journey gap that can be tested locally.
- If a finding has multiple plausible fixes, first encode the failing behavior
  as a regression test or a small local proof, then implement the smallest
  code path that makes the product contract true.
- Follow the Mandate of Inquiry: curiosity over closure. A gap is not
  "solved" by choosing the first plausible implementation. Before filling any
  logic, config, service, library, documentation, or journey hole, Ralphie must
  record the three most distinct possibilities that could fit, what data/code
  has not yet been inspected, and whether the operator needs to define product
  intent before implementation.
- Never convert an unverified external/tool/data claim into product truth. If
  a fact cannot be verified locally without secrets or live credentials, mark
  it as proof-gated or ask a concrete operator question instead of inventing a
  confident answer.
- Preserve transparency of inference in handoffs: when a repair depends on an
  inference, name the evidence, the remaining unknown, and the reason the chosen
  path is safer than the alternatives.
- Keep `ralphie.sh` changes separate from ArcLink product changes if commits
  are later requested. This mission already updated `ralphie.sh` from
  `https://github.com/sirouk/ralphie` at upstream commit
  `e3ab437af694aef4281ad8d5338aedd740b448a3`.

## Mission Success Criteria

- All high-risk data, secret, auth, retrieval, and destructive-operation
  boundary gaps are fixed or explicitly disabled with honest docs and tests.
- Hosted web onboarding has a coherent account identity, checkout, resume,
  login, dashboard, and status journey.
- Admin actions either execute real modeled operations through a deployed
  worker path or are hidden/marked unavailable until executable.
- Docker and bare-metal health checks prove the surfaces users/operators
  actually depend on, not only a subset of containers.
- Shared Host, Docker, and Sovereign Control Node docs agree with code and
  clearly mark canonical, historical, speculative, and proof-gated material.
- User and operator journeys are mapped start-to-finish for every public and
  private surface Ralphie touches, including success, denial, cancel, retry,
  skip, disabled, dry-run, pending, failed, and proof-gated paths.
- Regression tests cover the repaired behavior. Validation commands are run
  and recorded in Ralphie's final handoff.

## Phase Strategy

Ralphie should not try to land all repairs in one giant patch. Use slices:

1. Security and trust boundaries.
2. Hosted web/API identity and checkout journey.
3. Control-plane execution, provisioning, fleet, rollout, and admin action
   truthfulness.
4. Shared Host and Docker operational health parity.
5. Onboarding journey failure handling and secret cleanup.
6. Knowledge freshness, cleanup safety, and resource skill correctness.
7. Documentation status, runbooks, and validation coverage.

Within each slice, do this loop:

1. Confirm the current behavior in code/tests.
2. For each detected hole, write the possibility set: at least three distinct
   plausible fixes or product interpretations when three exist, plus the
   unknowns that would change the choice.
3. Invite operator choice by marking a concrete blocked question when the vector
   space is product/policy-owned rather than code-owned.
4. Add or adjust focused regression coverage where practical.
5. Implement the fix without widening scope.
6. Run the narrow validation floor.
7. Update the closest docs only after behavior exists.

## Priority 0: Immediate Security And Trust Boundary Repairs

- [x] Constrain dashboard file plugin roots by default.
  - Problem: generated dashboard units set `HERMES_HOME` but not
    `CODE_WORKSPACE_ROOT`, `DRIVE_WORKSPACE_ROOT`, or `TERMINAL_WORKSPACE_ROOT`
    in `bin/install-agent-user-services.sh`.
  - Problem: Code defaults workspace root to `$HOME` in
    `plugins/hermes-agent/code/dashboard/plugin_api.py`.
  - Problem: Drive includes `$HOME` as a candidate workspace root in
    `plugins/hermes-agent/drive/dashboard/plugin_api.py`.
  - Expected fix: default Drive/Code/Terminal roots to approved vault/workspace
    roots only; exclude `.env`, `.ssh`, `HERMES_HOME/secrets`, bootstrap token
    files, and private runtime state even if a custom root is configured.
  - Tests: prove secret-like files are not listable, previewable, downloadable,
    editable, searchable, or reachable through traversal/symlink paths.

- [x] Bind bare-metal qmd to loopback by default.
  - Problem: `systemd/user/arclink-qmd-mcp.service` runs `bin/qmd-daemon.sh`
    without env overrides, and `qmd-daemon.sh` defaults public host to
    `0.0.0.0`.
  - Expected fix: bare-metal service defaults must expose qmd only on loopback
    unless a deliberate operator config enables wider binding.
  - Tests: unit/static tests for generated service or daemon defaults; health
    should fail on unsafe public bind.

- [x] Scope `notion.fetch` and `notion.query` to configured shared/indexed
  Notion roots.
  - Problem: `notion.search` is qmd-index scoped, but exact live reads in
    `arclink_control.py` can return any page/database/data-source available to
    the integration token.
  - Expected fix: exact fetch/query should deny out-of-root resources or require
    an explicit privileged operation with audit and docs.
  - Tests: mock an accessible-but-unindexed Notion page/database and assert
    agent-facing tools refuse it.

- [x] Close SSOT destructive payload bypasses.
  - Problem: operation names like archive/delete/trash are rejected, but
    `operation: update` forwards arbitrary payloads to Notion PATCH; helper
    code can use `in_trash`.
  - Expected fix: shape-validate SSOT update payloads; reject `archived`,
    `in_trash`, delete/trash/archive fields, destructive block moves, or other
    destructive Notion mutations unless routed through an explicit approval
    rail.
  - Tests: SSOT preflight/write rejects update payloads that trash/archive or
    delete content.

- [x] Prevent Docker dashboard backend bypass.
  - Problem: Docker agent dashboard backend starts on `0.0.0.0` inside the
    Compose network while the auth proxy is only the public gate.
  - Expected fix: bind the backend to a network boundary that only the proxy can
    reach, add auth at backend, or isolate per-agent networks so sibling
    containers cannot bypass the proxy.
  - Tests: static/unit tests for Docker supervisor command generation and docs.

- [x] Stop exposing agent bootstrap tokens through process argv.
  - Problem: helper scripts pass tokens through `python3 - "$TOKEN"` or
    `--json-args "$payload"`.
  - Expected fix: use temp args files, stdin, or file descriptor patterns like
    `bin/user-agent-refresh.sh`.
  - Tests: script/static tests reject bootstrap-token argv patterns.

- [x] Fail closed on generated index cleanup paths.
  - Problem: PDF ingest and Notion index cleanup unlink/move DB-stored absolute
    paths without revalidating they live under generated roots.
  - Expected fix: before unlink/move, resolve and assert path is under the
    expected generated markdown root.
  - Tests: malicious/corrupt DB path outside generated root is refused.

- [x] Sanitize team-resource manifest slugs before destructive git reset.
  - Problem: `bin/clone-team-resources.sh` trusts private manifest slugs as path
    segments before `git reset --hard`.
  - Expected fix: reject absolute paths, `..`, empty slugs, shell metacharacter
    confusion, and path traversal.
  - Tests: reject path-traversal slugs.

## Priority 1: Hosted Web/API Identity, Checkout, And Dashboard Journey

- [x] Repair the browser session and CSRF contract.
  - Problem: `web/src/lib/api.ts` reads session and CSRF values from
    `document.cookie`, but hosted API sets session cookies as `HttpOnly`.
  - Problem: the client regex grabs the first user/admin cookie and sends
    generic headers; backend trusts headers before kind-specific cookies.
  - Expected fix: choose one coherent browser contract:
    - cookie-only server extraction plus a non-HttpOnly CSRF token, or
    - explicit login response token storage with security tradeoffs documented.
  - Tests: real client tests with `HttpOnly` semantics; dual user/admin session
    tests; route-kind scoping.

- [x] Make web onboarding collect or receive a usable account identity.
  - Problem: the web flow sends only channel, local browser identity, plan id,
    and display name; user login later requires email/password.
  - Expected fix: collect email before checkout, rely on Stripe customer email
    and surface next steps honestly, or provide magic/status auth that does not
    require unknown credentials.
  - Tests: web onboarding creates a user that can reach status/login flow after
    entitlement.

- [x] Make checkout success and cancel pages reflect backend truth.
  - Problem: success/cancel pages are static; success says Stripe confirmation
    received before webhook confirmation; cancel does not call backend cancel.
  - Problem: leaving for Stripe clears local resume state, so cancel resume link
    cannot restore the flow.
  - Expected fix: success page polls/verifies backend checkout/entitlement
    status; cancel page preserves/resolves session and calls cancellation or
    resume APIs.
  - Tests: cancel resumes an open checkout; success displays pending until
    webhook state is paid.

- [x] Add CORS headers to auth/error responses, not only successful route
  handling.
  - Problem: successful hosted API responses append CORS, but common auth/error
    returns can bypass that append.
  - Tests: 401/403/500-safe errors include expected CORS where origin is
    allowed.

- [x] Filter user provider state by authenticated user.
  - Problem: `read_provider_state_api` authenticates the caller but selects
    non-cancelled deployments without filtering to session user.
  - Expected fix: user route sees only that user's deployments; admin route can
    see all.
  - Tests: two users, one route, no cross-user deployment leakage.

- [x] Fix admin dashboard API shape mismatches.
  - Problem: service health returns `checked_at`, UI reads `last_check_at`.
  - Problem: audit returns `action`, UI reads `action_type`.
  - Problem: reconciliation returns `reconciliation` and `drift_count`, UI reads
    `drift` or `summary`.
  - Expected fix: align UI and tests with API shape or normalize API response.
  - Tests: browser mocks should use real API shape; drift must visibly render.

- [x] Add admin auth loading guard.
  - Problem: admin shell renders before auth state is known, unlike user
    dashboard.
  - Expected fix: show loading/redirect gate until auth-gated data resolves.

- [x] Remove unconditional "fake adapters/no live charges" web copy or gate it
  on actual fake adapter mode.
  - Problem: onboarding always says fake adapters are active even when live
    Stripe is configured.
  - Tests: fake mode and live mode render different, truthful notices.

## Priority 2: Control-Plane Execution Truthfulness

- [x] Wire a deployed action-worker consumer or disable/hide queued admin
  actions until executable.
  - Problem: admin UI queues actions and API stores them, but no public
    compose/systemd/bin entrypoint runs `process_arclink_action_batch`.
  - Expected fix: add a service/job loop with health/status, or make queue-only
    actions clearly unavailable.
  - Tests: queued action transitions through worker processing.

- [x] Replace no-op "applied" action branches with real operations or honest
  pending/unavailable states.
  - Problem: action types such as `comp`, `reprovision`, `rollout`, `suspend`,
    `unsuspend`, `force_resynth`, and `rotate_bot_key` return local success
    notes without invoking their modeled modules.
  - Expected fix: call real domain functions where safe; otherwise mark as
    unsupported with explicit UI/docs.
  - Tests: action branch produces durable expected state or unsupported state.

- [x] Make `control-provisioner` disabled state unmistakable.
  - Problem: Compose always starts the service, default env disables the worker,
    worker exits 0, and job-loop records ok.
  - Expected fix: health/admin UI distinguish "running but disabled" from
    "actively provisioning"; docs explain required env to enable.
  - Tests: disabled worker is not reported as provisioning healthy/active.

- [x] Distinguish dry-run provisioning success from applied deployment success.
  - Problem: dry-run planner writes successful-looking service health and a
    succeeded job though nothing was applied.
  - Expected fix: use explicit status/type labels such as
    `planning_succeeded`, `dry_run_succeeded`, and never imply live service
    readiness.
  - Tests: user/admin dashboards render dry-run state honestly.

- [x] Expose coherent fleet and rollout mutation journeys.
  - Problem: fleet and rollout state models exist, but product surface is mostly
    observational. Rollout admin action is a no-op.
  - Expected fix: add CLI/API/admin routes for create/apply/advance/rollback, or
    document that these are internal models only.
  - Tests: lifecycle operations mutate durable rows and dashboard reflects them.

- [x] Make live proof/evidence status evidence-backed.
  - Problem: operator snapshot reports readiness-like labels from env/diagnostic
    state rather than durable proof artifacts. Hosted live proof can return
    "ready pending execution" and still exit success.
  - Expected fix: store/read proof results, distinguish skipped/pending/passed,
    and avoid success exits for unexecuted live proof unless explicitly
    dry-run.
  - Tests: no credentials means skipped/pending; real runner result required for
    passed.

## Priority 3: Shared Host And Docker Operational Gaps

- [x] Normalize upstream branch defaults and docs.
  - Problem: AGENTS says production tracks `main`; README says clone `arclink`;
    deploy defaults to `arclink` in places; upgrade refuses non-main.
  - Expected fix: choose the actual production contract and make README,
    AGENTS, `bin/common.sh`, `bin/deploy.sh`, tests, and examples agree.
  - Tests: fresh install config defaults to the same branch upgrade accepts.

- [x] Add missing bare-metal dependencies.
  - Problem: health uses `ss` but bootstrap omits `iproute2`; pins use `jq` but
    bootstrap omits `jq`.
  - Expected fix: add packages and regression coverage.

- [x] Make Nextcloud enablement consistent when compose runtime is unavailable.
  - Problem: install can disable/skip Nextcloud if compose runtime is missing,
    but restart/wait paths still act on `ENABLE_NEXTCLOUD=1`.
  - Expected fix: carry effective enablement state through install/restart/health.
  - Tests: compose-missing path skips gracefully without later failure.

- [x] Preserve discovered nondefault config in component upgrade and pin notify
  paths.
  - Problem: some paths fall back to default `/home/arclink` config assumptions.
  - Tests: custom service user/repo/private path remains intact.

- [x] Make health DB probes fail on Python probe failures.
  - Problem: some health checks ignore Python failures before parsing stdout.
  - Expected fix: propagate probe failure to health failure count.

- [x] Quote or escape generated systemd root unit paths.
  - Problem: generated root unit `Environment=` and `ExecStart=` paths are
    unquoted. Defaults are safe, custom paths are not.
  - Tests: paths with spaces/specifier-like characters are rendered safely or
    rejected explicitly.

- [x] Expand Docker health to cover operator-facing ingress and recurring jobs.
  - Problem: `control-ingress` publishes web port but is not required by Docker
    health. Recurring jobs write status files that health does not inspect.
  - Expected fix: require ingress reachability and inspect job-loop status for
    ssot, notifications, qmd-refresh, pdf-ingest, memory-synth, docs sync, and
    curator-refresh.

- [x] Repair Docker Nextcloud access sync.
  - Problem: Docker defaults Nextcloud enabled, but access helper expects
    Podman/Podman Compose while Docker image installs Docker CLI.
  - Expected fix: use Docker Compose service access in Docker mode or disable
    that path honestly.

- [x] Make Docker release state represent dirty/mixed revisions.
  - Problem: Docker upgrade records only `git rev-parse HEAD`; some services
    bind-mount live checkout while others use baked image.
  - Expected fix: record dirty state and image/repo revision split; avoid mixed
    revision surprises or document them clearly.

- [x] Reduce Docker agent supervisor over-serialization and excessive refresh.
  - Problem: one loop handles provisioning, refresh, cron, gateway, dashboard,
    proxy; cron tick can run a full user-agent refresh every 60 seconds.
  - Expected fix: separate cadence or skip expensive refresh unless needed.

- [x] Document and reduce Docker socket/private-state trust boundary.
  - Problem: docs call out one socket-mounted service, but Compose mounts the
    socket into several services and secrets enter container env.
  - Expected fix: document the full trusted-host model and reduce mounts/env
    where practical.

## Priority 4: Private Curator And Public Bot Onboarding Journeys

- [x] Surface early auto-provision failures to the onboarding user.
  - Problem: some `_run_one()` failures update bootstrap/operator state but not
    `onboarding_sessions.provision_error`, leaving the user waiting.
  - Tests: simulated Unix/init/access failure updates session and queues user
    visible status.

- [x] Stop sending generated dashboard passwords to operator notification
  channels unless explicitly documented as credential channels.
  - Expected fix: send one-time ack flow only to the user, or redact operator
    copy and include recovery instructions.

- [x] Delete staged onboarding secrets when a session is denied.
  - Problem: cancel-before-provision cleans secrets, denial only marks state.
  - Tests: bot/provider staged secrets removed on denial.

- [x] Make backup skip durable.
  - Problem: chat flow records backup skipped, but completed-session backfill
    can re-prompt skipped users.
  - Tests: skipped users are not re-prompted unless they ask.

- [x] Add completion-ack recovery path.
  - Problem: follow-up links and Discord agent DM handoff wait on "I recorded
    this safely"; no-ack can stall the expected completion journey.
  - Expected fix: visible retry/recovery command or operator trace.

- [x] Make public `/cancel` cancel open public onboarding/checkout sessions, not
  only active sub-workflows.
  - Tests: no active workflow plus open checkout is cancelled or resumed
    explicitly.

- [x] Clarify or deepen public backup and Notion commands.
  - Problem: public `/connect_notion` and `/config_backup` record metadata, but
    do not perform the private Curator-grade verification/key setup.
  - Expected fix: either implement full public path or label them as preparation
    steps with next actions.

- [x] Validate API-key provider credentials earlier where possible.
  - Problem: API-key provider auth accepts any non-empty string; failure happens
    later.
  - Expected fix: add provider-specific smoke validation where safe, or make
    "format accepted, runtime validation pending" explicit.

## Priority 5: Knowledge Freshness And Generated Content Safety

- [x] Redact PDF vision pipeline endpoint from generated markdown frontmatter.
  - Problem: pipeline signature includes endpoint and model; endpoint may contain
    credentials in URL/userinfo/query.
  - Expected fix: hash or redact endpoint before writing sidecars.
  - Tests: endpoint secrets never appear in generated markdown.

- [x] Use full-source hashes for memory synthesis freshness.
  - Problem: signatures use names, sizes, and integer mtimes, so same-size
    same-second rewrites can leave stale cards.
  - Tests: same size and same mtime content rewrite refreshes card.

- [x] Hash PDFs before fast-path skipping or otherwise detect same-size
  same-second rewrites.
  - Tests: overwritten PDF with same length and integer mtime updates sidecar.

- [x] Add a DB claim/lock around SSOT batcher event processing.
  - Problem: parallel/manual invocations can duplicate nudges/reindex work.
  - Tests: concurrent processors do not process the same pending event twice.

- [x] Correct resources skill stale text and fallback URL.
  - Problem: skill still says "Raven/operator" and defaults a setup installer to
    `raw.githubusercontent.com/example/arclink`.
  - Expected fix: public text and fallback URL must be real or explicitly
    unavailable.

## Priority 6: Documentation And Product Expectation Repair

- [x] Add a doc status map.
  - Mark canonical, historical, speculative, proof-gated, and stale docs.
  - At minimum classify `AGENTS.md`, `README.md`, `docs/docker.md`,
    `docs/API_REFERENCE.md`, `docs/org-profile.md`, plugin READMEs,
    `IMPLEMENTATION_PLAN.md`, `research/*`, and creative/product briefs.

- [x] Update `AGENTS.md` to include Sovereign Control Node commands and current
  product/deploy shape, or explicitly scope it to Shared Host only.

- [x] Update terminal docs for actual SSE plus polling fallback behavior.
  - Old docs still describe Terminal as polling-only/no true streaming.

- [x] Fix Stripe webhook table names and webhook misconfiguration docs.
  - Code uses `arclink_webhook_events`; stale docs say
    `arclink_stripe_webhooks`.
  - Code returns 503 when `STRIPE_WEBHOOK_SECRET` is unset; stale docs claim a
    skipped response.

- [x] Fix product DB table count docs or avoid exact table counts.
  - Docs say 22 `arclink_*` tables; code has more.

- [x] Fix config alias wording.
  - Public docs say `ARCLINK_*` overrides legacy `ARCLINK_*`, which appears
    self-contradictory and not backed by a populated alias map.

- [x] Rewrite data-safety docs to distinguish Shared Host, Shared Host Docker,
  and Sovereign Control Node state models.
  - Current docs overstate `/srv/arclink/{deployment_id}` and named volume
    assumptions while code uses `/arcdata/deployments` for product pods and
    `/home/arclink/arclink-priv` for shared host.

- [x] Add first-day user guide.
  - Cover where to talk to the agent, dashboard access, Drive, Code, Terminal,
    vault/qmd, Notion/SSOT, backup, retry/contact, and expected failures.

- [x] Add Control Node production runbook.
  - Cover credentials, Stripe/Cloudflare/Tailscale/bot webhooks, enablement
    flags, provisioner, action worker, evidence capture, rollback, and known
    fake/dry-run states.

- [x] Add Notion human guide.
  - Distinguish shared SSOT, indexed Notion knowledge, personal Notion MCP,
    verification/claim pages, PDF/export fallback, and destructive boundaries.

- [x] Update Docker security docs for socket mounts, container user, env secret
  exposure, private-state mounts, auth proxy bypass risks, and trusted-host
  assumptions.

## Priority 7: Dependency And Validation Coverage

- [x] Add `jq` and `iproute2` to bare-metal bootstrap dependencies and tests.

- [x] Align local validation docs with actual live E2E dependencies.
  - `pytest` is documented but not in `requirements-dev.txt`.
  - Live Stripe E2E needs `stripe` when `STRIPE_SECRET_KEY` is set.

- [x] Add web/Playwright validation to top-level docs or preflight strategy.
  - `web/package.json` has lint/test/browser scripts, but top-level validation
    and README local prereqs do not cover Node/Playwright setup.

- [x] Document live-proof Node/Playwright setup.
  - `arclink_live_runner.py` generates a Playwright proof under `web/`; docs
    should say `cd web && npm ci` and browser install requirements when needed.

## Journey Map Ralphie Must Preserve Or Repair

### Shared Host Operator Journey

Operator clones repo, configures private state and deploy key, runs
`./deploy.sh install`, uses Curator to approve users, runs health, upgrades
with `./deploy.sh upgrade`, and expects services, agents, qmd, Notion,
Nextcloud, backups, and release state to align. Repairs must preserve canonical
scripts and avoid manual host surgery.

### Private Curator User Journey

User DMs Curator, answers identity/purpose/Unix/bot/provider questions,
operator approves, user provides bot token/provider auth, root provisioner
creates Unix/Hermes services, user records dashboard credentials, backup/Notion
SSH rails continue, agent bot contacts user. Repairs must make failure,
denial, skip, retry, and completion states visible and recoverable.

### Public Web Purchase Journey

Visitor chooses plan, names agent/org, checks out with Stripe, returns to web,
receives or creates account identity, watches provisioning status, logs into
dashboard, sees billing/provisioning/services/bots/model/memory/security, and
reaches agent surfaces. Repairs must remove static or misleading states and
make webhook/pending/paid/cancelled states explicit.

### Public Telegram/Discord Purchase Journey

User starts with Raven/public bot, creates/resumes public onboarding, checks
out, receives paid ping, optionally configures backup/Notion, checks status,
and gets private agent handoff. Repairs must align `/cancel`, backup, Notion,
status, and paid ping behavior with user expectations.

### Admin/Operator Control Journey

Admin logs in, sees accurate dashboards, queues actions, observes worker
execution, controls provisioning/fleet/rollout, watches service health and
evidence, and can recover from drift. Repairs must remove fake success states,
wire real workers, and make disabled/dry-run/proof-gated states obvious.

### Agent Knowledge Journey

Agent uses `knowledge.*`, `vault.*`, `notion.*`, `ssot.*`, managed memory, and
notifications. Repairs must keep retrieval scoped, freshness correct,
destructive writes gated, and generated content secret-free.

## Validation Floor

Ralphie should select the narrowest relevant validation per slice, then run a
broader pass before final handoff.

General:

```bash
git diff --check
bash -n deploy.sh bin/*.sh test.sh
```

Python touched modules:

```bash
python3 -m py_compile <touched python files>
python3 tests/<nearest focused test>.py
```

Likely focused tests:

```bash
python3 tests/test_arclink_plugins.py
python3 tests/test_arclink_agent_user_services.py
python3 tests/test_arclink_onboarding_prompts.py
python3 tests/test_arclink_enrollment_provisioner_regressions.py
python3 tests/test_arclink_onboarding_cancel.py
python3 tests/test_arclink_hosted_api.py
python3 tests/test_arclink_provisioning.py
python3 tests/test_arclink_executor.py
python3 tests/test_arclink_rollout.py
python3 tests/test_arclink_docker.py
python3 tests/test_deploy_regressions.py
python3 tests/test_health_regressions.py
python3 tests/test_memory_synthesizer.py
python3 tests/test_arclink_ssot_batcher.py
```

Web touched files:

```bash
cd web
npm test
npm run lint
npm run test:browser
```

Only run heavy `./test.sh`, live proof, Docker install/upgrade, or host upgrade
when the current slice warrants it and the operator has explicitly accepted
the blast radius.

## Final Handoff Expectations

Ralphie's final report must include:

- Files changed, grouped by slice.
- Security boundaries repaired and tests proving them.
- User journeys repaired and remaining intentional limitations.
- Validation commands run and results.
- Any skipped tests with concrete reason.
- Remaining open questions that require operator policy, not inference.
