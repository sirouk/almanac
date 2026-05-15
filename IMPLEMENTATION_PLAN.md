# Implementation Plan: Audit Gate, Wave 6 ArcLink Wrapped, Mission Closeout

## Goal

Complete the final ArcPod Captain Console run without touching private state or
live infrastructure:

1. Verify the previously remediated Sovereign audit Wave 1 trust-boundary items
   still pass in current source.
2. Land Wave 6 ArcLink Wrapped.
3. Complete the Mission Closeout sweep for Waves 0-6.

## Build Status

Waves 0-5 are treated as landed in current source. They should not be retouched
unless a direct regression blocks the audit gate, Wrapped, or closeout proof.

Final status for this run: Wave 6 and the closeout sweep are source-complete in
the current worktree. `research/BUILD_COMPLETION_NOTES.md` carries the
six-wave mission closeout ledger, and
`research/RALPHIE_ARCPOD_CAPTAIN_CONSOLE_STEERING.md` carries the landing-status
map. Remaining work after commit is operator-authorized live proof only.

The historical audit verification file remains a regression checklist. Its two
fiction/outdated items, `ME-11` and `ME-25`, must not become new backlog unless
current source contradicts their fiction verdict.

## Constraints

- Do not touch `arclink-priv`, live secrets, user Hermes homes, deploy keys,
  production services, payment/provider mutations, public bot command
  registration, live deploys/upgrades, Docker install/upgrade, or Hermes core.
- Keep Wrapped read-only over Captain state. It may write Wrapped report rows,
  notification rows, audit/events, and scheduler status, but must not mutate
  sessions, memory, vault content, providers, payments, or deployments.
- Use existing ArcLink architecture: Python, SQLite, hosted API, public bot
  handler patterns, `notification_outbox`, `docker-job-loop.sh`, Next.js
  dashboard, and canonical docs/OpenAPI.
- Preserve the Sovereign Control Node domain-or-Tailscale ingress contract; do
  not collapse paid pod ingress into Shared Host Docker validation paths.
- Captain-facing surfaces use ArcPod, Pod, Agent, Captain, Crew, Raven, Comms,
  Crew Training, and ArcLink Wrapped. Operator/backend surfaces keep technical
  vocabulary.
- Operator Wrapped views expose aggregate status/score only, never Captain
  narrative, markdown, report text, or raw ledger snippets.

## Selected Implementation Path

| Decision | Selected path | Rejected alternatives |
| --- | --- | --- |
| Audit backlog | Verification gate first; repair only actual current regressions | Blindly re-implement historical audit items already fixed in source. |
| Wrapped core | Add `python/arclink_wrapped.py` as the single source for scoring, rendering, persistence, cadence, and delivery enqueue | Duplicating Wrapped SQL/scoring in API, dashboard, bot, and scheduler handlers. |
| Scheduler | Add a named `arclink-wrapped` job-loop service and thin runner | Host cron, new queue infrastructure, or piggybacking on health-watch. |
| Data access | Scoped DB reads plus injectable read-only state/session scanners | Reading live user homes or private state during BUILD. |
| Storage | Store rendered text/markdown and stats in `ledger_json` first; add columns only if tests show the existing schema is insufficient | Premature schema churn. |
| Delivery | Queue `notification_outbox` with `target_kind='captain-wrapped'` and quiet-hours-aware `next_attempt_at` | Direct-send from scheduler or bypassing outbox retries. |
| Dashboard | Add Captain Wrapped tab and admin aggregate panel using current tab/API patterns | Dashboard rewrite. |
| Bot | Add pure `/wrapped-frequency` handler tests without live command registration | Mutating Telegram/Discord command menus during BUILD. |

## Validation Criteria

BUILD is complete only when:

- audit Wave 1 trust-boundary verification passes or any current regression is
  fixed with focused tests;
- `generate_wrapped_report(conn, user_id, period, period_start, period_end)`
  produces deterministic reports from scoped events, audit rows, Comms rows,
  read-only session counts, vault-reconciler deltas, and memory cards;
- the novelty-score formula is documented and tested;
- each rich report emits at least five non-standard statistics;
- both plain text and Markdown render forms are redacted before persistence,
  dashboard display, and delivery;
- per-Captain cadence supports only `daily`, `weekly`, and `monthly`, defaults
  to daily, and rejects anything more frequent;
- a named scheduler retries failed reports next cycle and emits operator
  notification for persistent failure;
- Captain delivery goes through `notification_outbox` with
  `target_kind='captain-wrapped'` and respects quiet hours;
- Captain dashboard "Wrapped" tab shows history and frequency controls;
- Operator dashboard/API shows aggregate Wrapped status/score only;
- public bot `/wrapped-frequency` works in pure handler tests;
- all seven Mission Closeout items are satisfied or explicitly deferred with
  operator-facing rationale;
- focused and broad local validation is recorded in completion notes.

## Actionable Tasks

### Phase 0 - Audit Wave 1 Verification Gate

1. Re-run focused tests covering the trust-boundary repairs:
   - Telegram webhook secret registration/verification.
   - Discord timestamp tolerance and interaction replay.
   - Hosted API body cap, invalid JSON, CORS on early errors, and CIDR gate.
   - Logout/session revoke auth-before-CSRF.
   - HMAC-peppered session/CSRF hashes and legacy migration.
   - Shared secret redaction and redact-before-truncate behavior.
   - Webhook/public bot/admin action rate limits.
   - Docker non-root and socket-scoping regression checks.
2. If any test fails because of current source behavior, fix that regression
   before Wrapped work.
3. Record `ME-11` and `ME-25` as fiction/outdated in completion notes, not as
   open implementation tasks.

### Phase 1 - Wrapped Core And Tests

1. Create `tests/test_arclink_wrapped.py`.
   - Seed users, deployments, events, audit rows, Comms messages, memory cards,
     session-count fixtures, job-status fixtures, and vault-reconciler fixture
     state.
   - Assert deterministic output, period scoping, Captain scoping, redaction,
     at least five non-standard stats, score stability, persistence, failed
     retry eligibility, and admin aggregate privacy.
2. Add `python/arclink_wrapped.py`.
   - Normalize periods and frequencies.
   - Resolve period windows for daily, weekly, and monthly.
   - Collect scoped ledger data for a Captain's deployments.
   - Read session counts and vault-reconciler deltas only through injectable,
     scoped read-only helpers.
   - Generate five or more non-standard stats from available signals.
   - Compute deterministic novelty score.
   - Render plain text and Markdown.
   - Redact all narrative/stat/ledger text before returning or storing.
   - Persist `arclink_wrapped_reports` rows using `ledger_json`.
3. Document the novelty formula in a new or existing ArcLink docs page.

### Phase 2 - Cadence, Scheduler, And Delivery

1. Add frequency helpers and API-auth mutations.
   - Default missing frequency to daily.
   - Accept only `daily`, `weekly`, `monthly`.
   - Reject hourly, cron, or arbitrary interval values.
   - Audit successful changes.
2. Add scheduler helpers.
   - Select due Captains by frequency and latest generated/delivered/failed
     report.
   - Regenerate failed reports on the next eligible cycle.
   - Track persistent failures and queue an operator notification without
     Captain narrative.
3. Add `bin/arclink-wrapped.sh` if needed.
   - Keep it a thin wrapper around the Python module.
   - Do not read private config beyond normal ArcLink public runtime config.
4. Add a named `arclink-wrapped` Compose job-loop service.
   - Use `bin/docker-job-loop.sh`.
   - Do not mount the Docker socket.
   - Add deploy/Docker regression coverage.
5. Queue `notification_outbox` rows for successful Captain reports.
   - Use `target_kind='captain-wrapped'`.
   - Include safe extra metadata for report id, period, score, and render kind.
   - Set `next_attempt_at` to respect supported quiet-hours windows.

### Phase 3 - Hosted API, Dashboard, And Bot

1. Add hosted API routes.
   - `GET /user/wrapped`
   - `POST /user/wrapped-frequency`
   - `GET /admin/wrapped`
   - Include OpenAPI metadata after behavior is implemented.
2. Add auth helpers in `python/arclink_api_auth.py`.
   - User routes are user-scoped and CSRF-gated for mutation.
   - Admin route is aggregate-only and CIDR/admin-session protected.
3. Extend `python/arclink_dashboard.py`.
   - User dashboard snapshot includes Wrapped history and current frequency.
   - Admin/operator snapshot includes aggregate counts, latest score/status,
     failure count, and due count only.
4. Extend `web/src/lib/api.ts`.
   - Add Wrapped history/frequency/admin helpers.
5. Extend `web/src/app/dashboard/page.tsx`.
   - Add "Wrapped" tab with history, text/Markdown display, and frequency
     selector.
   - Ensure mobile/desktop layout has stable dimensions and no text overflow.
6. Extend `web/src/app/admin/page.tsx`.
   - Add aggregate Wrapped view with no Captain narrative.
7. Extend `python/arclink_public_bots.py`.
   - Add `/wrapped-frequency daily|weekly|monthly`.
   - Reject invalid values and keep tests pure.

### Phase 4 - Mission Closeout Sweep

1. Vocabulary migration completeness.
   - Sweep `web/src/**`, `python/arclink_public_bots.py`,
     `python/arclink_onboarding*.py`,
     `python/arclink_onboarding_completion.py`,
     `docs/arclink/CREATIVE_BRIEF.md`,
     `docs/arclink/raven-public-bot.md`,
     `docs/arclink/first-day-user-guide.md`, `README.md`, and completion-bundle
     copy.
   - Keep backend/operator surfaces technical.
   - Add focused grep or string tests for stale Captain-facing language.
2. Original onboarding bug verification.
   - Confirm web, Telegram, and Discord Agent Name + Agent Title input capture
     and flow into deployment row and SOUL/identity projection.
   - Add or strengthen assertions where thin.
3. Cross-wave coherence.
   - Verify `arclink_inventory_machines`, `arclink_pod_messages`,
     `arclink_pod_migrations`, `arclink_crew_recipes`, and
     `arclink_wrapped_reports` are each written and read by their owning wave.
   - Check MCP tools, hosted API routes, `deploy.sh control inventory`, and
     dashboard tabs for collisions.
4. Doc reconciliation.
   - Update `docs/DOC_STATUS.md`, `docs/arclink/architecture.md`,
     `docs/API_REFERENCE.md`, and `docs/openapi/arclink-v1.openapi.json`.
   - Ensure every route added across Waves 0-6 appears in OpenAPI and API
     reference.
5. Steering-doc reconciliation.
   - Update `research/RALPHIE_ARCPOD_CAPTAIN_CONSOLE_STEERING.md` with a
     closing status section or accurate checkbox status for Waves 0-6.
6. Final completion notes.
   - Add a comprehensive `research/BUILD_COMPLETION_NOTES.md` entry summarizing
     all six waves, files changed per wave, schema deltas, env vars,
     validation run, skipped live gates, and residual risks.
7. Broad validation.
   - Run the per-wave validation floors plus web, shell, compile, and browser
     checks listed below.

## Validation Floor

Audit gate:

```bash
python3 tests/test_arclink_telegram.py
python3 tests/test_arclink_discord.py
python3 tests/test_arclink_hosted_api.py
python3 tests/test_arclink_api_auth.py
python3 tests/test_arclink_secrets_regex.py
python3 tests/test_arclink_docker.py
python3 tests/test_deploy_regressions.py
```

Wrapped focused:

```bash
git diff --check
python3 -m py_compile python/arclink_wrapped.py python/arclink_api_auth.py python/arclink_hosted_api.py python/arclink_dashboard.py python/arclink_public_bots.py python/arclink_notification_delivery.py
python3 tests/test_arclink_wrapped.py
python3 tests/test_arclink_notification_delivery.py
python3 tests/test_arclink_dashboard.py
python3 tests/test_arclink_hosted_api.py
python3 tests/test_arclink_api_auth.py
python3 tests/test_arclink_public_bots.py
python3 tests/test_arclink_schema.py
```

Closeout and broad validation:

```bash
bash -n deploy.sh bin/*.sh test.sh
cd web
npm test
npm run lint
npm run build
npm run test:browser
```

Compile every touched Python module before completion. Live Stripe, Chutes,
Cloudflare, Tailscale, Telegram, Discord, Notion, remote Docker host,
deploy/upgrade, Docker install/upgrade, payment-flow, public-bot mutation, and
production service restart proof remain explicitly operator-gated.
