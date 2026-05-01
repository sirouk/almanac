# Build Completion Notes

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
- `python3 -m py_compile python/almanac_control.py python/arclink_*.py` passed.
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
- `python3 -m py_compile python/almanac_control.py python/arclink_*.py` passed.
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
- `python3 -m py_compile python/almanac_control.py python/arclink_*.py` passed.
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
- `python3 -m py_compile python/almanac_control.py python/arclink_onboarding.py python/arclink_entitlements.py` passed.
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
  private Almanac user-agent onboarding tables. Public Telegram and Discord ids
  are channel hints, not private deployment bot credentials.
- Kept Stripe checkout behind the existing fake adapter boundary with
  deterministic idempotency-key session ids, instead of adding a live Stripe SDK
  dependency before E2E secrets and hosted callback URLs exist.
- Connected checkout success through the existing signed entitlement webhook
  and deployment gate. Onboarding observes the lifted gate and records funnel
  events; it does not grant provisioning directly.

Verification run:

- `python3 -m py_compile python/almanac_control.py python/arclink_adapters.py python/arclink_entitlements.py python/arclink_onboarding.py python/arclink_provisioning.py` passed.
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
- `python3 -m py_compile python/arclink_entitlements.py python/almanac_control.py tests/test_arclink_entitlements.py` passed.
- `python3 -m ruff check python/arclink_entitlements.py python/almanac_control.py tests/test_arclink_entitlements.py` passed.
- `python3 -m pyflakes python/arclink_entitlements.py python/almanac_control.py tests/test_arclink_entitlements.py` passed.
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
- `python3 -m py_compile python/arclink_entitlements.py python/almanac_control.py tests/test_arclink_entitlements.py` passed.
- `python3 -m ruff check python/arclink_entitlements.py python/almanac_control.py tests/test_arclink_entitlements.py` passed.
- `python3 -m pyflakes python/arclink_entitlements.py python/almanac_control.py tests/test_arclink_entitlements.py` passed.
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
- `python3 -m py_compile python/arclink_entitlements.py python/almanac_control.py tests/test_arclink_entitlements.py` passed.
- `python3 -m ruff check python/arclink_entitlements.py python/almanac_control.py tests/test_arclink_entitlements.py` passed.
- `python3 -m pyflakes python/arclink_entitlements.py python/almanac_control.py tests/test_arclink_entitlements.py` passed.
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
