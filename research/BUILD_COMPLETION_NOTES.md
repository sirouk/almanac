# Build Completion Notes

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

- `python/arclink_api_auth.py` — removed `_rowdict` definition (3 lines),
  replaced 5 call sites with `rowdict`.
- `python/arclink_dashboard.py` — removed `_rowdict` definition (3 lines),
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
