# ArcLink Foundation Runbook

This runbook describes the current ArcLink foundation behavior. It is written
for project operators and implementation agents, not for live customer
operations.

## Current Boundary

ArcLink is currently an additive foundation on top of the shared-host substrate. New product
surfaces use `ARCLINK_*` configuration, `arclink_*` database tables, and
`python/arclink_*.py` helpers while existing deploy, onboarding,
Hermes, qmd, vault, memory, Notion, and health paths keep their current names.

The current provisioning layer records and validates intent. Public onboarding
has no-secret durable session and checkout contracts. A guarded executor
boundary exists for Docker Compose, domain/Tailscale ingress, model-provider, Stripe, and
rollback operations, but it fails closed unless live/E2E execution is explicitly
enabled. ArcLink now ships a local no-secret Python product surface over the
onboarding, user-dashboard, admin-dashboard, and queued-action contracts. It is
for development and contract testing, not production hosting. ArcLink still
does not ship production adapters that execute customer deployment containers,
create live DNS records, mint live model provider keys, run live public bots,
authenticate dashboard sessions, or run a live automated admin-action worker.
The checked-in action worker can consume queued intents through the guarded
executor boundary for local/fake validation and explicit operator-driven runs.

## Assumptions

- Docker Compose remains the MVP deployment substrate.
- The existing shared-host Docker path is the operational base for ArcLink work.
- Unit and regression tests must not require live Stripe, Cloudflare, Tailscale,
  model provider, Telegram, Discord, Notion, or host provisioning secrets.
- Secret material is represented by `secret://...` references or Compose
  secret file targets, never plaintext values in persisted intent.
- Public onboarding stores channel/customer/checkout hints only. It must not
  store private deployment bot tokens, provider keys, webhook secrets, or raw
  credentials.
- Paid or comped entitlement is required before provisioning intent is marked
  ready for execution.
- Profile-only user updates must not mutate entitlement state. Entitlement
  changes belong to explicit entitlement writers: signed Stripe webhook
  processing, `set_arclink_user_entitlement()`, or reasoned admin comp helpers.
- Stripe entitlement webhook processing owns its database transaction. Callers
  must pass a connection without an active transaction.
- Manual comp actions are admin-owned and must include an audit reason.
- Dashboard read models are projections over existing ArcLink tables. They must
  not expose raw metadata columns, plaintext secrets, or provider credentials.
- Admin dashboard actions are queued audited intent first. They require an admin
  id, target, reason, idempotency key, and secret-free metadata before the
  action worker may claim them.
- The action worker is guarded by the executor configuration. Fake/no-secret
  runs are valid for contract testing; live provider or Docker side effects
  require an explicit live-enabled operator path and live adapters.
- Mutating executor methods must fail closed unless a live/E2E enable flag is
  deliberately supplied by the caller.
- Executor idempotency keys are replay keys for identical inputs only. Reusing
  a key with changed rendered Compose intent, DNS records, Access plans, Chutes
  action or secret ref, or rollback plan must fail before returning stored
  results.
- Executor results must not include plaintext secret material. Compose secrets
  resolve from `secret://...` references to `/run/secrets/...` targets through
  an injected resolver.
- Rendered Compose services must not reference missing `depends_on` services.
- Dedicated per-deployment Nextcloud services are the MVP isolation model.
- SSH access is advertised through Cloudflare Access TCP hints in domain mode or
  direct Tailscale SSH hints in Tailscale mode, not raw SSH over HTTP or
  path-prefix routing.
- ArcLink workspace UX belongs in Hermes dashboard plugins, not Hermes core
  patches. Plugin status APIs must stay capability-driven and secret-free.
- `Terminal` provides managed-pty sessions inside the configured
  deployment/user boundary. It uses same-origin SSE output streaming with a
  bounded polling fallback and confirmation-gated close; it is not unrestricted
  host-root shell access or tmux persistence.

## Rationale

The foundation keeps ArcLink additive so the project can reuse the
working host substrate instead of duplicating deploy, runtime, retrieval,
memory, notification, and repair behavior too early. `ARCLINK_*` names and
`arclink_*` tables give product work a clear namespace while preserving
compatibility with explicit legacy aliases such as `ARC_*` where helpers
provide them.

Provisioning is dry-run first because the risky parts are contracts, not Docker
syntax: entitlement gating, deterministic retries, host/container path
separation, DNS intent, ingress labels, access hints, and secret-reference
handling all need stable records before a live executor can safely start or
roll back containers.

Dedicated per-deployment Nextcloud services are the default because isolation is
easier to reason about than shared app/database/cache tenancy during MVP work.
Cloudflare Access TCP-style SSH hints are pinned for domain mode because raw SSH
cannot be routed safely through HTTP path prefixes or ordinary Traefik HTTP host
rules. Tailscale mode uses direct SSH to the tailnet host.

## Ownership

ArcLink owns:

- Product identity and compatibility helpers in `python/arclink_product.py`.
- SaaS state rows under the `arclink_*` table namespace in
  `python/arclink_control.py`.
- Stripe entitlement interpretation in `python/arclink_entitlements.py`.
- Hostname, DNS drift, and Traefik intent in `python/arclink_ingress.py` and
  `python/arclink_adapters.py`.
- Nextcloud isolation and SSH access strategy guards in
  `python/arclink_access.py`.
- No-secret provisioning intent, job state, health placeholders, timeline
  events, secret-reference validation, and rollback planning in
  `python/arclink_provisioning.py`.
- Hermes dashboard plugin installation, default enablement, and legacy alias
  cleanup in `bin/install-arclink-plugins.sh`.
- ArcLink workspace plugin APIs and UI assets under
  `plugins/hermes-agent/drive/`,
  `plugins/hermes-agent/code/`, and
  `plugins/hermes-agent/terminal/`.
- Docker plugin mount repair, managed plugin refresh, per-deployment tailnet app
  publication, and deployment service-health refresh in `bin/arclink-docker.sh`.
- Guarded mutating executor contracts and secret materialization rules in
  `python/arclink_executor.py`.
- Public website, Telegram, and Discord onboarding session contracts in
  `python/arclink_onboarding.py`.
- User/admin dashboard read models and queued admin action intent in
  `python/arclink_dashboard.py`.
- Queued admin action execution, attempt rows, stale-action recovery, and
  pending-not-implemented status handling in `python/arclink_action_worker.py`.
- Local no-secret website/API views in `python/arclink_product_surface.py`.
- Public Telegram/Discord bot conversation skeletons in
  `python/arclink_public_bots.py`.
- Telegram runtime adapter in `python/arclink_telegram.py`.
- Discord runtime adapter in `python/arclink_discord.py`.

ArcLink continues to own the live shared-host substrate: deploy/install/upgrade
scripts, Docker orchestration wrappers, Hermes runtime installation, qmd,
vault, memory synthesis, Notion SSOT, notifications, Curator, and user-agent
refresh/gateway rails.

## Current Behavior

Configuration:

- Non-empty `ARCLINK_*` values override explicit legacy aliases such as
  `ARC_*` when a helper call or future alias map provides one.
- Blank `ARCLINK_*` values are ignored so generated env files do not erase
  working legacy settings.
- Conflict diagnostics name only variable keys and do not print values.

Entitlements:

- Stripe webhook verification rejects blank secrets before signature parsing.
- Processed webhook event ids are idempotent and replay without duplicating
  audit or timeline events.
- Rows left in `failed` or `received` can be replayed with the same event id
  after payload or handler repair.
- Entitlement webhook processing starts and commits its own transaction. If
  entitlement work fails after the event is accepted, user entitlement,
  subscription mirror, deployment status, audit, and timeline side effects roll
  back together, and the webhook row is left `failed` for replay.
- Caller-owned active transactions are rejected and left open for the caller to
  commit or roll back.
- Signed unsupported events are marked `processed` but do not mutate entitlement
  state, subscription mirrors, audit rows, or timeline events.
- Supported payment events mirror subscription state, update the user
  entitlement, and advance matching deployments out of `entitlement_required`
  only when entitlement is `paid` or `comp`.
- Payment-blocking states write audit rows.
- `upsert_arclink_user()` defaults a newly inserted user to `none` when no
  entitlement is supplied, but preserves an existing row's `entitlement_state`
  and `entitlement_updated_at` during profile-only updates.
- Admin comps require a reason. A user-level comp sets the user entitlement to
  `comp` and lifts every blocked deployment for that user. A deployment-targeted
  comp only lifts the named deployment, records a deployment-scoped audit row,
  and leaves the user's global entitlement state unchanged.

Provisioning dry run:

- A deterministic provisioning job is created or resumed from the idempotency
  key.
- Failed jobs can be returned to `queued`; stale `started_at`, `finished_at`,
  and `error` values are cleared before the next attempt.
- Intent renders host state roots separately from container runtime paths.
- Intent renders dashboard, Hermes gateway/dashboard, qmd, vault watch, memory
  synthesis, dedicated Nextcloud DB/Redis/app services, dashboard-native Code,
  notification delivery, health watch, and managed-context installation.
- Hermes dashboard receives the deployment vault and code workspace mounts.
  The rendered environment sets `VAULT_DIR`, `DRIVE_ROOT`, and
  `CODE_WORKSPACE_ROOT` so Drive and Code operate
  inside deployment-owned roots.
- Access URL metadata is rendered for dashboard, files, code, and Hermes. In
  Tailscale path mode, a per-service tailnet HTTPS port may override the Hermes
  path URL while files and code stay under the authenticated user dashboard at
  `/u/<prefix>/drive` and `/u/<prefix>/code`.
- Nextcloud overwrite settings are applied only when the files URL is a
  root-level HTTPS host or host:port. Path-prefixed URLs are not written as
  Nextcloud canonical overwrite hosts.
- Nextcloud and Postgres use file-backed secret environment variables through
  Compose secrets.
- App/provider tokens remain resolver-required references until live execution
  supplies a safe materialization step.
- Service-health placeholders and timeline events are recorded for admin and
  dashboard surfaces to consume later.
- Dry-run intent may be visible for unpaid deployments, but execution readiness
  remains false and no `provisioning_ready_for_execution` event is recorded.
- Failed provisioning jobs can be retried with the same idempotency key after
  metadata repair. The retry returns the job to `queued`, clears stale
  timestamps and error text, and increments the attempt count when it starts
  again.
- Cancelled provisioning jobs are terminal and cannot be resumed.
- Rollback planning is idempotent and only allowed for failed jobs. The plan
  records the intended actions `stop_rendered_services`,
  `remove_unhealthy_containers`, `preserve_state_roots`, and
  `leave_secret_refs_for_manual_review`; it does not execute rollback actions.

Executor boundary:

- Docker Compose, ingress, model-provider key, Stripe
  action, and rollback apply calls raise `ArcLinkLiveExecutionRequired` by
  default.
- The testable fake path sets `ArcLinkExecutorConfig.live_enabled=True` and
  adapter name `fake`; production callers must provide their own explicit
  live/E2E enablement and adapters.
- Compose execution consumes rendered provisioning intent and reports project
  name, service names, host volume sources, and secret target paths without
  returning secret values.
- Explicit fake Compose idempotency keys are bound to the rendered intent
  digest. Reusing a key after changing services, environment, volumes, labels,
  secrets, or other rendered intent fails before resume or replay.
- Successful fake Compose replays return stored applied state without
  rematerializing secrets.
- Fake Compose planning rejects dependency cycles, invalid `depends_on` shapes,
  and dependencies that point to missing services.
- Compose secret specs must use `secret://...` references and `/run/secrets/...`
  targets. Missing, empty, or malformed secret references fail before a result
  is returned.
- Fake Docker failure injection requires a positive service limit; zero or
  negative limits fail closed.
- Domain-mode DNS execution allows only `A`, `AAAA`, `CNAME`, and `TXT` records.
  Other record types fail before fake or future live apply.
- SSH execution rejects raw HTTP strategies and accepts only
  `cloudflare_access_tcp` or `tailscale_direct_ssh`.
- Model-provider key actions are limited to `create`, `rotate`, and `revoke`.
- Fake Cloudflare DNS, Cloudflare Access, Tailscale ingress, Chutes key lifecycle, and rollback
  replays store an operation digest. Reusing an idempotency key with changed
  inputs fails instead of returning stale provider, edge, key, or rollback
  results.
- Fake Chutes replay returns the stored action and stored `secret://` reference
  only for identical replay. Action drift or secret-ref drift is rejected.
- Stripe actions are limited to `refund`, `cancel`, and `portal`.
- Rollback execution requires `preserve_state_roots` in the plan before it can
  return an applied result.
- Rollback execution rejects action names that imply deleting customer state
  roots or vault data.

Public onboarding:

- Web, Telegram, and Discord entrypoints create or resume durable
  `arclink_onboarding_sessions` rows.
- A partial unique index prevents duplicate active sessions for the same public
  channel identity. Terminal payment or completion states allow a new session
  later.
- Funnel events are append-only rows in `arclink_onboarding_events`: started,
  question answered, checkout opened, payment success/failure/cancel/expire,
  provisioning requested, first agent contact, and channel handoff.
- Checkout creation uses a deterministic fake Stripe client in no-secret tests.
  It stores Stripe checkout ids and URLs, not Stripe secret keys.
- Checkout completion does not grant provisioning directly. The signed Stripe
  entitlement webhook updates the user entitlement and advances the linked
  deployment gate first; onboarding then marks the session
  `provisioning_ready`.
- Preparing or resuming onboarding for a returning user updates profile and
  deployment hints without passing an implicit `none` entitlement. Existing
  `paid` and `comp` entitlement rows remain unchanged unless an explicit
  entitlement writer changes them.
- Cancelled and expired checkout helpers leave the linked deployment at
  `entitlement_required` and record funnel events for admin conversion views.
- Telegram and Discord identifiers are public channel hints. Private
  user-agent bot tokens remain outside public onboarding rows.

Local product surface:

- `python3 python/arclink_product_surface.py` starts a local stdlib WSGI app
  without live secrets and seeds a deterministic fixture deployment unless
  `--no-seed` is supplied.
- The first screen is the usable onboarding workflow, not a marketing-only
  page. It starts web sessions, records answers, opens fake checkout, and links
  to user/admin read models.
- The local surface also exposes JSON routes for onboarding sessions, user
  dashboard reads, admin dashboard reads, and queued admin actions.
- The surface follows the ArcLink brand system and remains a replaceable
  prototype; production frontend stack, auth, RBAC, CSRF, rate limits, and live
  action execution are later gates.

API/auth boundary:

- `python/arclink_api_auth.py` stores user/admin session tokens and CSRF tokens
  as hashes only.
- Public onboarding API helpers share the same durable onboarding session rows
  and rate-limit rail as the website and public bot skeletons.
- Hosted route work must extract session credentials from explicit
  `X-ArcLink-Session-Id` plus bearer token headers or the matching
  `arclink_user_*`/`arclink_admin_*` cookies; unsupported session kinds fail
  before database reads or writes.
- Admin mutation helpers require an active admin session, CSRF token, elevated
  role, MFA-ready state when configured, reason, and idempotency key.
- API error shaping keeps domain-specific `ArcLinkApiAuthError` copy visible
  while replacing unexpected exception details with generic user-safe text.

Hosted API boundary:

- `python/arclink_hosted_api.py` wraps existing ArcLink helper contracts into a
  hosted WSGI application with route dispatch under `/api/v1`.
- `HostedApiConfig` resolves runtime configuration from environment variables:
  `ARCLINK_BASE_DOMAIN`, `ARCLINK_CORS_ORIGIN`, `ARCLINK_COOKIE_DOMAIN`,
  `ARCLINK_COOKIE_SECURE`, `STRIPE_WEBHOOK_SECRET`, `ARCLINK_LOG_LEVEL`,
  `ARCLINK_DEFAULT_PRICE_ID`, `ARCLINK_FIRST_AGENT_PRICE_ID`, and
  `ARCLINK_ADDITIONAL_AGENT_PRICE_ID`.
- Public onboarding routes (`/onboarding/start`, `/onboarding/answer`,
  `/onboarding/checkout`), login routes, and the Stripe webhook endpoint require
  no existing session. Admin and user login still require the stored password
  for that principal and are rate-limited.
- User dashboard and admin dashboard reads require session credentials via
  `Authorization` bearer token and `X-ArcLink-Session-Id` header.
- Admin mutation routes (`/admin/actions`, `/admin/sessions/revoke`) require
  admin session authentication plus CSRF token via `X-ArcLink-CSRF-Token`.
- Admin login sets `HttpOnly`, `SameSite=Lax` session cookies with optional
  `Secure` and `Domain` flags from config. Session revocation clears cookies
  when the revoked session matches the caller.
- CORS preflight (`OPTIONS`) and response headers are emitted only when
  `ARCLINK_CORS_ORIGIN` is configured.
- Every response includes an `X-ArcLink-Request-Id` header, either echoed from
  the client or generated server-side.
- `ArcLinkApiAuthError` maps to 401, `StripeWebhookError` maps to 400, and
  unexpected exceptions map to 400 with the generic safe error string. No raw
  tracebacks or internal details are returned.
- The Stripe webhook route rejects live webhook delivery with status 503 and a
  `stripe_webhook_secret_unset` error when `STRIPE_WEBHOOK_SECRET` is not
  configured, so Stripe retries instead of ArcLink silently accepting an event
  it cannot verify.
- `make_arclink_hosted_api_wsgi()` returns a standard WSGI app suitable for
  `wsgiref`, gunicorn, or other WSGI servers.
- The hosted API is the production boundary. The local product surface
  (`arclink_product_surface.py`) remains a no-secret prototype and contract
  smoke tool.

Telegram and Discord runtime adapters:

- `python/arclink_telegram.py` runs a long-polling loop when
  `TELEGRAM_BOT_TOKEN` is set. It dispatches incoming messages to the shared
  public bot turn handler and records onboarding session state in the same
  `arclink_onboarding_sessions` rows used by web and Discord.
- `python/arclink_discord.py` handles slash commands and messages when
  `DISCORD_BOT_TOKEN` is set. It verifies interaction signatures (stubbed in
  tests), dispatches to the shared turn handler, and shares the same
  onboarding session contract.
- Both adapters fall back to fake mode (no network) when their token is absent,
  keeping unit tests no-secret and deterministic.
- Neither adapter stores private user-agent bot tokens or provider credentials
  in public onboarding rows.

Public bot skeletons:

- `python/arclink_public_bots.py` provides deterministic Telegram and Discord
  conversation turns over the same public onboarding session contract.
- Supported turns collect name, plan, status, account-aware agent roster actions,
  and fake checkout. Stripe Checkout collects email; chat onboarding does not.
  The module does not run live bot clients or store private user-agent bot tokens.

Dashboard and admin contracts:

- User dashboard reads return customer profile, entitlement, deployment,
  access-link, billing, bot-contact, model, qmd/memory freshness, service
  health, and recent-event summaries from ArcLink-owned rows.
- User dashboard output omits raw metadata columns and rejects known plaintext
  secret shapes from the contract surface.
- Admin dashboard reads return onboarding funnel aggregates, subscription
  mirrors, deployments, service health, DNS drift, provisioning jobs, queued
  action intents, audit rows, and recent failures.
- Admin dashboard filters are intentionally simple and SQLite-compatible:
  channel, status, deployment id, user id, and `since`.
- Admin actions are represented as `arclink_action_intents` rows and start with
  status `queued`.
- `python/arclink_action_worker.py` claims the oldest queued intent, records an
  `arclink_action_attempts` row, dispatches supported actions through the
  guarded executor, and writes audit/event rows for success, failure, or
  unsupported paths.
- Executor-backed worker actions currently include restart, DNS repair, Chutes
  key rotation, refund, and cancel. They are fake/no-secret unless the caller
  deliberately supplies a live-enabled executor and live adapters.
- Other accepted admin action types, including comp, reprovision, rollout,
  suspend, unsuspend, force resynthesis, and bot-key rotation, are honest
  pending-not-implemented paths in the worker rather than no-op applied
  successes.
- Admin actions require an admin id, supported action type, supported target,
  reason, and idempotency key.
- Reusing an idempotency key for the same action returns the existing intent
  without duplicating audit rows. Reusing it for a different request is
  rejected.
- Action metadata may contain `secret://...` references, but plaintext-looking
  secret material is rejected before any action intent or audit row is written.

Native Hermes workspace plugins:

- Refreshed agents install `drive`, `code`,
  `terminal`, and `arclink-managed-context` by default.
- The installer removes legacy dashboard aliases `arclink-code-space` and
  `arclink-knowledge-vault` before enabling the current plugin names.
- Drive status reports backend availability, mount, username, URL, local root,
  and capability flags without returning WebDAV passwords or access-state
  secrets.
- Drive local backend operations are confined to the selected vault root and
  reject path traversal. Local deletes move files into `.arclink-trash` and can
  be restored while the original path is free.
- Code status reports workspace root, optional full-IDE URL, editor mode, and
  capability flags without returning credentials. Saves are manual and hash
  guarded so stale tabs cannot silently overwrite disk changes.
- Code git operations are root-confined to discovered repositories under the
  workspace. Destructive discard requires explicit confirmation.
- Terminal status reports the managed-pty backend when the workspace root,
  shell, and non-root runtime boundary are available, while returning sanitized
  workspace/state labels. Sessions have persisted metadata, bounded scrollback,
  same-origin SSE output streaming, bounded polling fallback, reload reconnect,
  rename, folder/grouping, reorder controls, and confirmation-gated close.

### Entitlement Repair

Use entitlement repair only after confirming the customer, deployment, and
Stripe event identity through project-owned admin records. Do not edit
`arclink_users`, `arclink_subscriptions`, or `arclink_deployments` by hand when
an existing helper can express the action.

For a replayable Stripe failure, repair the payload or handler condition, then
reprocess the same Stripe event id. Expected result:

- The webhook row moves from `failed` or `received` to `processed`.
- Entitlement side effects commit once.
- Replaying a `processed` event returns a replay result without duplicating
  events.

For a manual credit, call the comp helper with an actor id and a reason. Use a
deployment id only for one-off deployment credits; omit it only when the user
should have global comp entitlement.

For a profile correction, use `upsert_arclink_user()` without
`entitlement_state`. Supplying `entitlement_state` is an intentional
entitlement mutation and should be reviewed like a billing/support action.

### Provisioning Repair

Use the dry-run renderer as the first repair surface. If rendering fails due to
plaintext-looking secret material or stale metadata, fix the deployment metadata
to contain only `secret://...` references or Compose secret file targets, then
rerun the same idempotency key.

If executor replay fails because an idempotency key was reused with changed
inputs, choose one of two explicit paths:

- Reuse the original request inputs when the operator intended an idempotent
  replay or resume.
- Issue a new idempotency key when the operator intentionally changed the
  Compose intent, DNS records, Access plan, model-provider operation, or
  rollback plan.

If fake Compose rejects a missing dependency, fix the rendered service graph
before retrying. Do not work around the error by dropping `depends_on`; it is
the early signal that the dry-run intent no longer matches an executable
Compose project.

If a future live execution job fails, create a rollback plan before changing
state roots or secret references. The current executor contract requires
rollback plans to preserve state roots; production rollback adapters still need
separate E2E validation before they mutate real services.

### Admin Action Repair

Use queued admin actions to record operator intent, then process them only
through the action worker or an explicitly reviewed operator procedure. Do not
perform a live provider mutation just because an `arclink_action_intents` row
exists.

If an operator retries the same request, reuse the original idempotency key.
Expected result:

- The original action id is returned.
- No duplicate audit row is created.
- The worker records an attempt when it claims the action.
- Supported fake/executor-backed actions finish as succeeded or failed.
- Accepted but unwired actions finish with a pending-not-implemented failure
  note instead of pretending to apply.
- Stale running actions can be returned to queued with
  `recover_stale_actions()` after the configured threshold.

If the requested metadata includes a secret, store only a `secret://...`
reference. Plain API keys, webhook secrets, bot tokens, OAuth credentials, or
passwords do not belong in dashboard action metadata.

## Runbook

After changing ArcLink foundation behavior, run the focused no-secret checks:

```bash
python3 -m pip install -r requirements-dev.txt
python3 tests/test_arclink_product_config.py
python3 tests/test_arclink_schema.py
python3 tests/test_arclink_chutes_and_adapters.py
python3 tests/test_arclink_entitlements.py
python3 tests/test_arclink_onboarding.py
python3 tests/test_arclink_ingress.py
python3 tests/test_arclink_access.py
python3 tests/test_arclink_provisioning.py
python3 tests/test_arclink_executor.py
python3 tests/test_arclink_admin_actions.py
python3 tests/test_arclink_dashboard.py
python3 tests/test_arclink_api_auth.py
python3 tests/test_arclink_product_surface.py
python3 tests/test_arclink_public_bots.py
python3 tests/test_arclink_hosted_api.py
python3 tests/test_arclink_telegram.py
python3 tests/test_arclink_discord.py
python3 tests/test_model_providers.py
python3 tests/test_arclink_e2e_fake.py
python3 tests/test_public_repo_hygiene.py
# Live E2E (only when credentials present):
# ARCLINK_E2E_LIVE=1 ARCLINK_E2E_DOCKER=1 python3 tests/test_arclink_e2e_live.py
python3 -m py_compile python/arclink_control.py python/arclink_*.py
git diff --check
```

When touching shell deploy or Tailscale wrapper behavior, also run:

```bash
bash -n deploy.sh bin/*.sh test.sh
python3 tests/test_deploy_regressions.py
```

When touching Hermes workspace plugins or their Docker mount wiring, also run:

```bash
python3 -m py_compile \
  plugins/hermes-agent/drive/dashboard/plugin_api.py \
  plugins/hermes-agent/code/dashboard/plugin_api.py \
  plugins/hermes-agent/terminal/dashboard/plugin_api.py
python3 tests/test_arclink_plugins.py
python3 tests/test_arclink_docker.py
node --check plugins/hermes-agent/drive/dashboard/dist/index.js
node --check plugins/hermes-agent/code/dashboard/dist/index.js
node --check plugins/hermes-agent/terminal/dashboard/dist/index.js
```

Before promoting ArcLink beyond foundation work, confirm these are still true:

- Documentation does not claim production live customer provisioning is shipped.
- Provisioning output contains only secret references or secret file targets.
- Executor docs keep the explicit live/E2E gate and secret-free result contract.
- Executor docs keep strict replay semantics: idempotency keys are valid only
  for identical inputs, and changed operations need new keys.
- Compose docs keep missing dependency rejection as a pre-apply guard.
- Entitlement and provisioning retry docs preserve idempotency and transaction
  ownership expectations.
- Dashboard/admin docs preserve the distinction between read models, queued
  action intent, and future live executors.
- Workspace docs preserve the distinction between current Drive/Code plugin
  capabilities, Terminal managed-pty sessions, completed workspace Docker/TLS
  proof, and the separate hosted customer live-proof gate.
- New public docs contain no local machine paths, operator names, live hostnames,
  tokens, or copied `.env` values.
- New tests can run without live secrets.

## Open Risks

- Live provisioning execution still needs production Docker, selected ingress,
  model-provider, Stripe, secret-provider, and rollback adapters wired behind
  the explicit live/E2E gate. The current live E2E scaffold is not a completed
  live customer journey until credentials are supplied and the run succeeds.
- Cloudflare DNS/tunnel or Tailscale publication changes are represented as
  desired intent and fake drift checks only.
- Live model provider key lifecycle is not implemented; the current key manager
  is a fake no-secret adapter.
- The local product surface is not the production hosted UI. Production
  routing, identity-provider integration, browser-session hardening, RBAC
  policy, action execution, and frontend framework work still need explicit
  implementation.
- Drive and Code are first-generation native plugin surfaces. They have
  bounded no-secret API contracts, but broader Google Drive and VS Code parity
  remains future work.
- Terminal is managed-pty shell access inside the configured
  deployment/user boundary, with same-origin SSE output streaming, bounded
  polling fallback, bounded scrollback, and confirmation-gated lifecycle
  controls. It is not an unrestricted host-root shell or tmux-backed
  persistence.
