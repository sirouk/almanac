# ArcLink Ecosystem Gap Repair Implementation Plan

## Goal

Repair the verified end-to-end ArcLink ecosystem gaps from the May 2026
repository audit across Shared Host, Shared Host Docker, Sovereign Control Node,
hosted web/API, onboarding, Hermes runtime plugins, qmd/Notion/SSOT knowledge
rails, documentation, validation, and user/operator journeys.

The controlling detailed backlog is
`research/RALPHIE_ARCLINK_ECOSYSTEM_GAP_REPAIR_STEERING.md`. BUILD must not
route to terminal `done` while unchecked tasks remain in that steering file or
in this implementation plan.

Freshness checkpoint (2026-05-08): this plan has been re-reviewed against the
active steering backlog. Repository composition verified from public repo files:
54 first-party `python/arclink_*.py` modules, 99 Python test files, 82 shell
scripts, 29 systemd units, 36 web source/test/config TS/TSX/MJS/JS files, 24
ArcLink-owned control DB table definitions, 4 Hermes plugins, 11 skills, and 26
Compose services. Slices 1 (security), 2
(hosted web/API), 3 (control-plane execution truthfulness), 4 (Shared Host and
Docker operational parity), 5 (private Curator and public bot onboarding), and
6 (knowledge freshness and generated content safety) are completed baseline
gates. Slice 7 documentation and validation tasks are now checked in this plan
and in the steering file. No open checkbox task markers remain in either active
backlog file after this PLAN pass. BUILD should treat remaining work as
verification, review, and any newly discovered follow-up rather than an
unchecked backlog.

## Non-Negotiables

- Do not read private state, user homes, secret files, token files, deploy keys,
  OAuth credentials, bot tokens, or live `.env` values.
- Do not edit Hermes core.
- Do not run live deploy/upgrade, production payment flows, public bot
  mutations, external credential-dependent proof, or live host-mutating flows
  unless the operator explicitly asks during BUILD.
- Fix behavior before docs.
- Add focused regression tests for security, boundary, and journey repairs.
- Keep Shared Host, Docker, and Sovereign Control Node boundaries explicit.
- Never expose secrets, local paths, raw credentials, raw terminal logs, or
  private state in logs, UI, docs, tests, API responses, proof notes, or commits.
- Apply the Mandate of Inquiry: curiosity over closure. For every meaningful
  logic/config/service/library/doc/journey gap, record distinct possibilities,
  inspect the unknowns, and ask a concrete operator-policy question when the
  product vector space is not defined by code.

## Selected Architecture

Use existing ArcLink public repo boundaries:

- Bash deploy, Docker, health, bootstrap, and service wrappers.
- Python control-plane, hosted API, onboarding, provisioning, MCP, worker,
  Notion/SSOT, health, evidence, fleet, and rollout modules.
- Docker Compose services, systemd units, and domain-or-Tailscale ingress
  intent for Sovereign Control Node surfaces.
- Next.js hosted web app for onboarding, checkout, login, user dashboard, and
  admin dashboard.
- ArcLink Hermes plugins, hooks, generated config, and skills.

Rejected paths:

- Hermes core patches.
- Private-state workarounds.
- Documentation-only repair.
- Replacing the multi-surface system with a new web app before closing host,
  Docker, onboarding, knowledge, and security gaps.

Implementation path comparison:

| Path | Use when | Decision |
| --- | --- | --- |
| Existing ArcLink slices across wrappers, Python modules, web/API, plugins, Compose, systemd units, and focused tests | The gap is in current public repo behavior or docs | Selected default BUILD path. |
| Hide or mark a surface unavailable until a real worker/provider path exists | The product would otherwise imply execution that does not happen | Acceptable for policy-dependent or unsafe operations. |
| New product/control app rewrite | Only after host, Docker, knowledge, onboarding, and boundary gaps are closed | Rejected for this mission. |

## Validation Criteria

Completion requires:

- Every unchecked item in this file and
  `research/RALPHIE_ARCLINK_ECOSYSTEM_GAP_REPAIR_STEERING.md` is either fixed
  with focused tests/docs or intentionally marked blocked with a concrete
  operator-policy question.
- High-risk auth, secret, dashboard, qmd, Notion, SSOT, Docker, token argv,
  generated cleanup, and path traversal boundaries fail closed.
- Hosted web onboarding, checkout, auth, login, status, dashboard, and admin
  views are coherent and truthful.
- Admin/provisioning surfaces stop implying execution that does not happen.
- Shared Host, Docker, and Control Node operations have aligned defaults,
  dependency coverage, docs, and health checks.
- Curator and public bot onboarding failure/cancel/skip/retry paths are visible
  and recoverable.
- Knowledge freshness and generated markdown safety match `AGENTS.md`.
- Docs classify canonical versus stale/speculative/proof-gated material.
- Every touched user/operator journey includes start, success, failure, cancel,
  retry, skip, disabled, dry-run, pending, and proof-gated states where that
  state can occur.
- Focused validation is run and summarized; skipped heavy/live checks name the
  concrete reason.

## BUILD Slices

### 1. Security And Trust Boundaries

- [x] Constrain Drive, Code, and Terminal dashboard roots by default in install,
  refresh, Docker, and plugin API paths.
- [x] Deny secret-like files, `.env`, `.ssh`, bootstrap tokens,
  `HERMES_HOME/secrets`, private runtime state, traversal, and symlink escapes
  for list, preview, download, edit, search, and terminal cwd operations.
- [x] Bind bare-metal qmd to loopback by default and make health fail on unsafe
  public binds.
- [x] Scope `notion.fetch` and `notion.query` exact reads to configured
  shared/indexed Notion roots or privileged audited operations.
- [x] Shape-validate SSOT update payloads and reject archive/trash/delete style
  destructive mutations unless routed through an explicit approval rail.
- [x] Close Docker dashboard backend auth-proxy bypass risk by binding,
  isolating, or authenticating the backend.
- [x] Remove agent bootstrap tokens from process argv patterns.
- [x] Revalidate generated-root containment before PDF/Notion index cleanup
  unlinks or moves DB-stored paths.
- [x] Sanitize team-resource manifest slugs before path construction and
  destructive git reset operations.
- [x] Add focused regression tests for each repaired boundary.

### 2. Hosted Web/API Identity, Checkout, And Dashboard

- [x] Choose and implement one browser session/CSRF contract that works with
  HttpOnly cookies and user/admin route scoping.
- [x] Ensure web onboarding collects or receives a usable account identity for
  status/login after entitlement.
- [x] Make checkout success poll or verify backend entitlement state before
  claiming completion.
- [x] Make checkout cancel preserve or resolve resume state and call backend
  cancellation/resume semantics.
- [x] Add CORS headers to allowed-origin auth and error responses.
- [x] Filter user provider state by authenticated user.
- [x] Fix admin dashboard API shape mismatches or normalize API responses.
- [x] Add admin auth loading/redirect guard.
- [x] Gate fake-adapter/no-live-charge copy on actual fake mode.
- [x] Add hosted API, web API client, and browser tests for the repaired
  journeys.

### 3. Control-Plane Execution Truthfulness

- [x] Wire a deployed action-worker consumer or hide/mark queued admin actions
  unavailable until executable.
- [x] Replace no-op "applied" branches with real domain operations or honest
  pending/unsupported states.
- [x] Make `control-provisioner` disabled state unmistakable in health/admin UI.
- [x] Distinguish dry-run planning success from applied deployment success.
- [x] Provide coherent fleet and rollout mutation journeys or document the
  models as internal/read-only.
- [x] Store and read live proof/evidence results; distinguish skipped, pending,
  failed, and passed states.
- [x] Add focused tests for action, provisioner, dry-run, rollout/fleet, and
  evidence semantics.

### 4. Shared Host And Docker Operational Parity

- [x] Normalize upstream branch defaults across README, AGENTS, common config,
  deploy logic, examples, and tests.
- [x] Add missing bare-metal dependencies such as `jq` and `iproute2` to
  bootstrap and tests.
- [x] Carry effective Nextcloud enablement through install, restart, wait, and
  health when Compose runtime is unavailable.
- [x] Preserve discovered nondefault config in component upgrade and pin
  notification paths.
- [x] Make health DB probes fail when Python probe commands fail.
- [x] Quote, escape, or reject unsafe generated systemd root unit paths.
- [x] Expand Docker health to cover operator-facing ingress and recurring job
  status files.
- [x] Repair Docker Nextcloud access sync or disable that path honestly.
- [x] Record Docker release state with dirty/mixed revision awareness.
- [x] Reduce Docker agent supervisor over-serialization and excessive refresh.
- [x] Document and reduce Docker socket/private-state trust boundaries.

### 5. Private Curator And Public Bot Onboarding

- [x] Surface early auto-provision failures to onboarding users and durable
  session state.
- [x] Stop sending generated dashboard passwords to operator notification
  channels unless those channels are explicitly documented as credential
  channels.
- [x] Delete staged onboarding secrets when a session is denied.
- [x] Make backup skip durable so skipped users are not re-prompted.
- [x] Add completion-ack retry/recovery path.
- [x] Make public `/cancel` cancel or explicitly resume open public onboarding
  and checkout sessions.
- [x] Clarify or deepen public backup and Notion command semantics.
- [x] Validate API-key provider credentials earlier where safe, or state that
  runtime validation is pending.
- [x] Add focused Curator, public bot, provider auth, and completion tests.

### 6. Knowledge Freshness And Generated Content Safety

- [x] Redact or hash PDF vision pipeline endpoint before writing generated
  markdown frontmatter.
- [x] Use full-source hashes for memory synthesis freshness.
- [x] Hash PDFs before fast-path skipping or otherwise detect same-size
  same-second rewrites.
- [x] Add DB claim/lock semantics around SSOT batcher event processing.
- [x] Correct resources skill stale text and unsafe fallback URL.
- [x] Add focused tests for endpoint redaction, content freshness, concurrent
  batch processing, and skill text.

### 7. Documentation And Validation Coverage

- [x] Add a doc status map that marks canonical, historical, speculative,
  proof-gated, and stale docs.
- [x] Update `AGENTS.md` for current Shared Host, Docker, and Sovereign Control
  Node shape or explicitly scope it.
- [x] Update terminal docs for actual streaming/polling behavior.
- [x] Fix Stripe webhook table names and unset-secret behavior docs.
- [x] Fix product DB table-count docs or remove exact counts.
- [x] Fix config alias wording.
- [x] Rewrite data-safety docs to distinguish Shared Host, Docker, and
  Sovereign Control Node state models.
- [x] Add a first-day user guide.
- [x] Add a Control Node production runbook.
- [x] Add a Notion human guide.
- [x] Update Docker security docs for socket mounts, container user, env secret
  exposure, private-state mounts, auth proxy bypass risks, and trusted-host
  assumptions.
- [x] Align local validation docs with actual Python, Node, Playwright, Stripe,
  and live proof dependencies.
- [x] Add web and Playwright validation to the top-level validation path or
  document why it stays web-local.
- [x] Document live-proof Node and Playwright setup, including credential-gated
  skip conditions.

## Validation Floor

Always run after touched-surface repairs:

```bash
git diff --check
bash -n deploy.sh bin/*.sh test.sh
python3 -m py_compile <touched python files>
python3 tests/<nearest focused test>.py
```

Likely focused tests by slice:

```bash
python3 tests/test_arclink_plugins.py
python3 tests/test_arclink_agent_user_services.py
python3 tests/test_loopback_service_hardening.py
python3 tests/test_arclink_hosted_api.py
python3 tests/test_arclink_api_auth.py
python3 tests/test_arclink_dashboard.py
python3 tests/test_arclink_action_worker.py
python3 tests/test_arclink_admin_actions.py
python3 tests/test_arclink_provisioning.py
python3 tests/test_arclink_sovereign_worker.py
python3 tests/test_arclink_fleet.py
python3 tests/test_arclink_rollout.py
python3 tests/test_arclink_evidence.py
python3 tests/test_arclink_live_runner.py
python3 tests/test_arclink_docker.py
python3 tests/test_deploy_regressions.py
python3 tests/test_health_regressions.py
python3 tests/test_arclink_curator_onboarding_regressions.py
python3 tests/test_arclink_public_bots.py
python3 tests/test_pdf_ingest_env.py
python3 tests/test_memory_synthesizer.py
python3 tests/test_arclink_ssot_batcher.py
python3 tests/test_documentation_truths.py
```

For web changes:

```bash
cd web
npm test
npm run lint
npm run test:browser
```

Do not run heavy `./test.sh`, Docker install/upgrade, live proof, public bot
mutations, Stripe/Cloudflare/Tailscale flows, or host upgrades unless the
operator explicitly authorizes them during BUILD.

## Build Handoff Order

1. Treat Slices 1 through 6 as completed baseline gates; do not regress them
   while working later slices.
2. Treat Slice 7 documentation and validation as completed baseline artifacts
   that still need focused review and validation before final release claims.
3. Before filling a gap, record the possibility set and unresolved unknowns in
   the relevant code comment, test, doc note, or handoff when they materially
   affect the implementation choice.
4. Add focused failing tests before code when the current behavior is risky.
5. Implement the narrowest behavior fix in existing ArcLink public code.
6. Run the narrow validation floor for the touched surface.
7. Update closest docs only after behavior is true.
8. Repeat through docs and validation while preserving completed onboarding
   recovery and knowledge freshness gates.
9. Record any policy-dependent choice as blocked with a concrete operator
   question instead of inventing a product answer.

## BUILD Verification Tasks

These are the concrete BUILD handoff actions now that the active backlog is
checked:

1. Review the dirty worktree by slice and confirm no unrelated user edits were
   reverted or folded into the wrong concern.
2. Run the validation floor for every touched surface, starting with
   `git diff --check`, `bash -n deploy.sh bin/*.sh test.sh`, focused Python
   tests for touched modules, and web validation for touched `web/` files.
3. Compare docs against behavior for Shared Host, Shared Host Docker,
   Sovereign Control Node, hosted web/API, onboarding, knowledge rails, and
   validation prerequisites.
4. If validation finds a regression, add or tighten the nearest focused test,
   fix behavior first, then update docs.
5. If live credentials, production deploys, public bot mutations, Stripe,
   Cloudflare, Tailscale, Docker install/upgrade, or host mutation are required
   to prove a claim, mark that claim proof-gated unless the operator explicitly
   authorizes the flow.
6. Only declare BUILD complete after validation results and any skipped
   proof-gated checks are summarized with concrete reasons.

## Prioritization And Escalation

BUILD should treat Slices 1 through 6 as release gates that must remain green
for the rest of the mission: high-risk secret, auth, retrieval, destructive
mutation, token, generated cleanup, path traversal, browser session/CSRF,
checkout, CORS, user scoping, admin dashboard, control-plane truthfulness,
Docker parity, onboarding recovery, knowledge freshness, generated markdown
safety, SSOT batch locking, and resource skill correctness are represented as
completed baseline gates in this plan and should be rerun whenever touched.

Proceed in numbered order from Slice 7 unless a failing test or shared module
dependency makes a later slice a prerequisite for the current repair. Keep each
BUILD pass scoped to one slice or one tightly related cross-slice cluster, then
run the nearest validation floor before moving on.

When a task requires an operator/product policy choice, BUILD must mark that
specific task blocked with a concrete question and continue with independent
no-secret work. Do not infer policy for live payments, public bot mutation,
production deploy/upgrade, external credentials, dashboard credential delivery,
or whether an admin action should execute for real versus remain unavailable.
