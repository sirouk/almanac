# ArcLink Sovereign Audit Ground Truth And Ralphie Remediation Brief

Date: 2026-05-11

Scope: public checkout at repository root. This pass checked source code only.
It did not inspect `arclink-priv`, user Hermes homes, live secrets, live Stripe,
live Chutes, Cloudflare, Notion, or production host state.

Verdict summary:

- Critical: 11 FACT, 0 PARTIAL, 0 FICTION
- High: 23 FACT, 2 PARTIAL, 0 FICTION
- Medium: 24 FACT, 2 PARTIAL, 2 FICTION
- Low: 21 FACT, 3 PARTIAL, 0 FICTION
- Total: 79 FACT, 7 PARTIAL, 2 FICTION

The audit is mostly ground truth. The pure fiction/outdated items are:

- ME-11: `validate_no_plaintext_secrets` already runs after the Nextcloud
  trusted-domain mutation in the current checkout.
- ME-25: `.dockerignore` exists and excludes `arclink-priv/`, `.git`,
  `.ralphie`, cache/output folders, and local env files.

Partial/overstated items are still worth attention, but Ralphie should not
copy the original wording blindly:

- HI-12: backend queues `reprovision`/`rollout` into a pending-not-implemented
  branch, but the current dashboard readiness marks them disabled rather than
  executable.
- HI-25: duplicate web onboarding sessions by email are possible, but the repo
  already has a case-insensitive unique email index and later onboarding code
  does attempt to reuse an existing user by email.
- ME-15: the workspace containment bypass is for SSH/machine mode; shell mode
  is bounded and the audit's "SSH/TUI" wording is too broad.
- ME-26: handoff/share tables store `secret_ref`, not raw plaintext; the real
  problem is no TTL/one-time-use and repeated on-demand reveal.
- LOW-8: `_safe_error` truncates before secret rejection. The exact "secrets
  past byte 500 leak" wording is wrong, but the redaction/truncation order is
  still brittle and should be replaced by unified redaction.
- LOW-10: recovery does not re-render a full provisioning intent; it recomputes
  access URLs instead of using cached handoff metadata.
- LOW-18: `arclink_evidence_runs` uses empty-string timestamp sentinels, not
  nullable timestamp columns. The data-contract concern remains.

## 2026-05-12 Closure Revisit

The committed source was revisited against this verification report after the
local audit-remediation checkpoint. Result:

- All 79 FACT findings have local source-level remediation or have been
  verified as corrected/outdated by source review. The remediated risk surfaces
  are covered by focused regression tests and broad local preflight.
- All 7 actionable PARTIAL findings have been handled according to the corrected
  scope in this report.
- The 2 FICTION/outdated findings, `ME-11` and `ME-25`, remain
  regression-awareness items only.
- No live Stripe, Chutes, Cloudflare, Tailscale, Telegram, Discord, Notion,
  remote Docker host, deploy, upgrade, Docker install/upgrade, payment-flow, or
  public-bot mutation proof was run. Those remain explicit operator-authorized
  live validation gates, not unresolved source-remediation gaps.
- The revisit found one remaining local artifact mismatch: the browser product
  fixture still mocked `comp` as pending even though backend readiness exposes
  `comp` as executable when executor probes pass. That fixture has been aligned
  with the backend readiness contract.

Current local closure posture: no known FACT/actionable PARTIAL source gaps
remain in this report. Future regressions should be tracked against the IDs
below and re-opened in `IMPLEMENTATION_PLAN.md` with source evidence.

### 2026-05-12 Three-Pass Follow-Up

A subsequent three-pass source, journey, and deployment-runtime audit found and
fixed additional local congruence gaps around the same closure boundary:

- Admin action form now reports the union of pending/proof-gated and disabled
  actions instead of hiding probe-disabled actions behind fallback semantics.
- Browser API client tests now match the HttpOnly-cookie plus CSRF contract and
  cover the missing onboarding/share/admin snapshot routes.
- Hosted API WSGI 405 status text and browser CORS allowed headers were
  tightened.
- `detect_github_repo` now defaults generated GitHub branch references to the
  configured `arclink` upstream lane instead of `main`.
- Docker build context hygiene now excludes generated web dependencies/builds
  and SQLite runtime state.
- Fake E2E admin/user mutations now exercise browser cookies plus CSRF.

The follow-up validation passed focused Sovereign tests, web lint/build,
Playwright browser checks, shell syntax checks, and `./bin/ci-preflight.sh`.
Live/provider/deploy proofs remain operator-gated.

## Critical

| ID | Verdict | Ground truth | Fix direction |
| --- | --- | --- | --- |
| CR-1 | FACT | `python/arclink_hosted_api.py::_handle_telegram_webhook` parses and dispatches Telegram updates with no `X-Telegram-Bot-Api-Secret-Token` check. `TelegramConfig` and `telegram_set_webhook` have no webhook secret lane. | Add `TELEGRAM_WEBHOOK_SECRET`, set it during webhook registration, verify with `hmac.compare_digest`, return 503 if configured webhook handling lacks a secret and 401 on mismatch. |
| CR-2 | FACT | `Dockerfile` creates an `arclink` user but never switches to it. Compose mounts `/var/run/docker.sock` read-write in five app services: `control-provisioner`, `control-action-worker`, `agent-supervisor`, `notification-delivery`, and `curator-refresh`. | Run containers as non-root, give Docker socket access only to services that need it, prefer read-only where possible, and add tests that assert service user/socket policy. |
| CR-3 | FACT | `ArcLinkExecutor.chutes_key_apply` and `stripe_action_apply` return `status="applied"` on live branches without calling `ChutesLiveAdapter` or `LiveStripeClient`. | Wire real provider calls and forward idempotency keys; make unavailable live adapters fail closed. |
| CR-4 | FACT | `process_sovereign_batch` only handles `provisioning_ready` and retryable `provisioning_failed`. DNS teardown, placement removal, and compose teardown helpers exist but are not wired into a cancellation lifecycle. | Add `teardown_requested`/`torn_down` flow, stop compose, remove DNS, revoke Chutes artifacts, release placement/ports, and gate destructive volume wipe behind explicit audit metadata. |
| CR-5 | FACT | `arclink_action_worker` does `SELECT queued LIMIT 1` then later `UPDATE status='running'` with no compare-and-swap. Its `_db_connect` bypasses hardened `connect_db` pragmas. | Use `connect_db`, claim with `BEGIN IMMEDIATE` plus CAS update, add `worker_id` and `claimed_at`, and skip when `rowcount != 1`. |
| CR-6 | FACT | `_handle_logout` validates CSRF and revokes by session id but never authenticates the session token first. `_handle_session_revoke` has the right auth-before-CSRF pattern. | Authenticate user/admin session before CSRF and revoke. |
| CR-7 | FACT | Discord Ed25519 verification checks signature over `timestamp + body` but has no timestamp tolerance and no interaction-id replay table. | Enforce a 5-minute timestamp window and persist processed interaction ids. |
| CR-8 | FACT | WSGI routing reads `Content-Length` bytes directly from `wsgi.input` with no cap. | Add global body cap and route overrides, returning 413 with CORS before JSON parsing. |
| CR-9 | FACT | `ARCLINK_BACKEND_ALLOWED_CIDRS` exists and `backend_client_allowed()` exists, but hosted API does not import or enforce it. | Add middleware for admin/control routes or remove the env contract and document host-network-only enforcement. |
| CR-10 | FACT | Refuel credit application selects active credits and updates by `credit_id` only, with no immediate transaction or remaining-balance guard. | Use `BEGIN IMMEDIATE` and guarded updates on expected `remaining_cents`; retry/refuse on concurrent change. |
| CR-11 | FACT | `_hash_token` is plain SHA-256 for session and CSRF token hashes. | Move to HMAC-SHA256 with a server-side pepper, add migration/back-compat reads, and test old/new sessions. |

## High

| ID | Verdict | Ground truth | Fix direction |
| --- | --- | --- | --- |
| HI-1 | FACT | Secret regexes are fragmented. Provisioning misses Anthropic/OpenAI project/service keys, AWS keys, PEM blocks, JWTs, Chutes prefixes, Discord tokens, and GitLab tokens. | Create `python/arclink_secrets_regex.py` and import it from provisioning, executor redactors, evidence, memory synthesis, Chutes, and hosted logging. |
| HI-2 | FACT | No per-operation idempotency table exists. Live compose/DNS/Stripe/Chutes paths do not persist intent digests or provider replay state. | Add `arclink_operation_idempotency` keyed by operation kind and idempotency key. |
| HI-3 | FACT | Email merge query has no `ORDER BY` or `LIMIT`; it repoints only deployments and onboarding sessions and does not disable the orphan. | Deterministic winner, update all owning tables, mark loser merged, audit. |
| HI-4 | FACT | `extract_arclink_session_credentials` accepts header/bearer credentials before cookies even for browser CSRF routes. | Split browser cookie-only extraction from API/header extraction. |
| HI-5 | FACT | Early unknown-route 404 returns before CORS headers are appended. | Attach CORS to all early returns. |
| HI-6 | FACT | `OPTIONS` returns 204 for any path. | Route-check preflights and emit `Allow`. |
| HI-7 | FACT | Stripe, Telegram, and Discord webhook handlers do not call `check_arclink_rate_limit`. | Add provider/IP scoped rate limits before expensive verification. |
| HI-8 | FACT | Docker secret material is written under materialization roots and rsynced to remote fleet hosts, with no cleanup after successful compose. SSH key path/mode/owner are not validated. | Clean local/remote secret files after up, use atomic writes, and validate SSH key file ownership/mode/no symlink. |
| HI-9 | FACT | Tailnet port allocation scans all deployments regardless of status, so cancelled deployments keep blocking ports. | Filter live statuses or use a lease table with `released_at`. |
| HI-10 | FACT | `place_deployment` checks for active placement then inserts with no unique active-placement index or transaction. | Add partial unique index and `BEGIN IMMEDIATE`; catch `IntegrityError` as already placed. |
| HI-11 | FACT | `_apply_deployment` renders and applies without rechecking entitlement readiness or user row under transaction at commit time. | Re-fetch and hard-fail if execution is no longer ready or user row is gone. |
| HI-12 | PARTIAL | Worker accepts `reprovision` and `rollout` and returns `pending_not_implemented`; current dashboard readiness marks them disabled. | Either wire them for real or remove them from queueable backend action types. |
| HI-13 | FACT | Action side effects happen before final event/audit/status commit, so an external mutation can succeed while audit/status rollback. | Record attempt/audit before side effect, then update result after. |
| HI-14 | FACT | DNS drift dashboard reads `dns_drift` events without joining deployment status. | Filter cancelled/torn-down deployments or add suppression state. |
| HI-15 | FACT | `dns_repair` action expects metadata DNS records, but the UI sends no metadata. | Server-side derive desired records from deployment and DNS tables when metadata is empty. |
| HI-16 | FACT | Refund/cancel rely on missing metadata customer refs; comp is not idempotent on target. | Resolve Stripe customer server-side and make comp idempotent. |
| HI-17 | FACT | Live proof returns exit code 0 for blocked/missing-credential and pending-unexecuted live states. | Return non-zero for requested live proof that did not run and persist evidence status. |
| HI-18 | FACT | `connect_db` enables foreign keys, but schema has no `FOREIGN KEY`, `REFERENCES`, or `CHECK` constraints; drift checks cover only a few relationships. | Add high-value FK constraints on new/rebuilt tables and expand drift checks. |
| HI-19 | FACT | Deployment/subscription statuses are free-form and there are no SQL `CHECK` constraints. | Centralize status constants and validate every writer; add CHECKs where feasible. |
| HI-20 | FACT | Drift logic treats only `active`, `trialing`, and `paid` as subscription coverage, so `past_due` can produce noisy deployment-without-subscription drift. | Split owed-service states from orphan states. |
| HI-21 | FACT | `revoke_arclink_session(commit=False)` stages mutation with no transaction assertion; callers currently use default `commit=True`. | Assert explicit transaction or remove ambiguous option. |
| HI-22 | FACT | Credential handoffs/share grants have no expiry; reveal can resolve `raw_secret` repeatedly until removed. | Add TTL, expiry job, and one-time/reissue semantics for revealable secrets. |
| HI-23 | FACT | Onboarding sessions have no expiry/GC, so stuck active identities can block re-entry. | Add `expires_at` or stale-session expiry invoked from a batch path. |
| HI-24 | FACT | `upsert_arclink_user` overwrites status on conflict while other fields use blank guards. | Preserve suspended/merged statuses unless an explicit privileged transition occurs. |
| HI-25 | PARTIAL | Web channel identity is a browser UUID, so duplicate active sessions by email can occur. But the schema already has a unique lower-email index and later onboarding tries to reuse existing users by email. | Add fail-loud existing-email UX at onboarding start/resume and tests around duplicate active sessions. |

## Medium

| ID | Verdict | Ground truth | Fix direction |
| --- | --- | --- | --- |
| ME-1 | FACT | Backend returns `{reconciliation, drift_count}` while web and Playwright fixtures accept/mock inverse shapes. | Canonicalize shape and fixtures. |
| ME-2 | FACT | Login/session failures reveal too much state, including password-not-configured and session mismatch/not-active distinctions. | Collapse user-facing errors; log structured private detail. |
| ME-3 | FACT | Session kind relies on generated id prefixes by convention; `_authenticate_session` does not enforce prefix for requested kind. | Assert `usess_`/`asess_` at extraction/auth. |
| ME-4 | FACT | Malformed/non-object JSON returns `{}` and produces downstream field errors. | Raise a body parse error and map to 400 `invalid_json`. |
| ME-5 | FACT | Hosted API main constructs one SQLite connection for the app. This is safe only for single-thread WSGI. | Document single-thread contract or switch to per-request connections. |
| ME-6 | FACT | Concurrent Stripe webhook duplicate insert can race and return an error before the first transaction commits. | Treat unique conflicts as replay/pending and return 200. |
| ME-7 | FACT | Provisioning uses `nextcloud_{deployment_id}` as a Postgres DB name while safe segments allow dots and dashes. | Normalize or validate DB-safe deployment ids. |
| ME-8 | FACT | Worker re-syncs dashboard password hash every apply tick even when the secret already existed. | Only hash/set on newly generated secret. |
| ME-9 | FACT | Compose status parser keys by service name, not project, and transport failures are downgraded to starting. | Filter by project and fail/mark degraded honestly on transport errors. |
| ME-10 | FACT | DNS rows are marked provisioned regardless of provider result/record id. | Mark only records with verified provider ids/success. |
| ME-11 | FICTION | Current code mutates Nextcloud trusted domains before building the final intent and then calls `validate_no_plaintext_secrets` immediately before return. | Do not backlog this except to keep a regression test. |
| ME-12 | FACT | `_safe_command_error` redacts only narrow keyword-adjacent patterns. | Use unified secret redactor before truncation. |
| ME-13 | FACT | Memory synthesizer redaction is keyword-only and misses standalone key shapes/PEMs/JWTs. | Use unified redactor on snippets and outputs. |
| ME-14 | FACT | Memory synthesis prompt embeds vault snippets into a free-form user prompt without strong untrusted-source sentinels. | Add untrusted-source framing and output rejection for imperatives/URLs. |
| ME-15 | PARTIAL | Shell mode is workspace-bounded. SSH/machine mode intentionally allows broader paths except sensitive guards. | Document the permission model or make machine mode opt-in/allowlisted. |
| ME-16 | FACT | Admin action readiness is a hard-coded capability list plus env string, not real executor/socket/worker/secret probes. | Report executable empty when disabled and add probes/heartbeat. |
| ME-17 | FACT | `queue_admin_action_api` has no rate limit. | Rate-limit by admin and target. |
| ME-18 | FACT | Action worker calls `ensure_schema` on every loop through `_db_connect`. | Initialize once and reuse hardened connections. |
| ME-19 | FACT | Browser CORS allow-list includes `Authorization` even though browser auth uses cookies. | Remove unless a specific API route needs it. |
| ME-20 | FACT | Cookie `Secure` defaults true, which breaks plain HTTP localhost/browser dev unless env override is set. | Dev-mode default or explicit documented local override. |
| ME-21 | FACT | Checkout cancel page does not call the backend cancel endpoint despite `cancelOnboarding` API existing. | Best-effort cancel on mount when session/cancel token exist. |
| ME-22 | FACT | Admin secondary fetch effect is not gated on dashboard auth/data resolution. | Gate on `data !== null`. |
| ME-23 | FACT | `bin/deploy.sh::detect_github_repo` defaults branch to `main`, while production guidance tracks `arclink`. | Default to `${ARCLINK_UPSTREAM_BRANCH:-arclink}`. |
| ME-24 | FACT | Agent user unit `Environment=` lines are unquoted. | Reuse systemd quote helper. |
| ME-25 | FICTION | `.dockerignore` exists and excludes private state, git metadata, local env, `.ralphie`, caches, and generated output. | Keep as regression guard only. |
| ME-26 | PARTIAL | Tables store `secret_ref`, not raw plaintext. On-demand reveal returns raw secret repeatedly while handoff remains available. | TTL, one-time reveal, and explicit documentation. |
| ME-27 | FACT | Live Notion root validation falls back to parent-walk API calls for unindexed pages without a cache. | Cache parent-walk decisions and bound MCP calls. |
| ME-28 | FACT | Single-port qmd branch does not pass `--host 127.0.0.1`; proxy branch does. | Always pass loopback host. |

## Low

| ID | Verdict | Ground truth | Fix direction |
| --- | --- | --- | --- |
| LOW-1 | FACT | User portal link route calls CSRF before API auth, a fail-closed version of the logout anti-pattern. | Auth then CSRF consistently. |
| LOW-2 | FACT | User provisioning status allows a missing requested deployment id to fall through instead of returning a clean not-found. | Return 404/empty explicit not-found for requested deployment. |
| LOW-3 | FACT | Health route uses the shared hosted API connection. | Use per-request connection if WSGI becomes threaded. |
| LOW-4 | FACT | Stripe misconfig response includes `status: misconfigured` while most errors use `error`. | Normalize envelope while preserving 503. |
| LOW-5 | FACT | CSRF cookie uses `SameSite=Lax`, not `Strict`. | Consider Strict where flows permit it. |
| LOW-6 | FACT | Secret materializer chmods files but not parent directory at write time. | Chmod parent root and assert private permissions. |
| LOW-7 | FACT | Secret materializer writes directly to basename; parallel attempts can overwrite/torn-write. | Atomic temp+rename and per-file lock. |
| LOW-8 | PARTIAL | The function truncates before secret rejection, so the exact "past byte 500 leak" wording is wrong; boundary partial-secret leakage and inconsistent redaction remain possible. | Redact full string first, then truncate. |
| LOW-9 | FACT | Secret path detection uses `_SECRET_KEY_RE.search(path)`, causing broad false positives. | Match path segments or structured keys. |
| LOW-10 | PARTIAL | Recovery recomputes access URLs rather than full intent; it still does not prefer cached handoff metadata. | Use cached metadata when available. |
| LOW-11 | FACT | Redacted action-worker errors collapse to one generic string. | Add safe error classes/codes without secret detail. |
| LOW-12 | FACT | Evidence ledger serializes unset timestamps as `0.0`. | Use `null` or omit unset timestamps. |
| LOW-13 | FACT | DNS record upsert resets status to `desired` on conflict. | Preserve `provisioned` when desired tuple is unchanged. |
| LOW-14 | FACT | Operator snapshot hard-codes `template_ready: True`. | Compute from actual templates/readiness. |
| LOW-15 | FACT | Timestamp formats mix `+00:00` and `Z` helpers across modules. | Normalize before string comparisons and converge helpers. |
| LOW-16 | FACT | Several hot lookups lack targeted indexes, including user Stripe customer, webhook status alone, audit action, provisioning requested time, and event type. | Add measured indexes with migration tests. |
| LOW-17 | FACT | TOTP factors lack a unique active-per-admin partial index. | Add partial unique index. |
| LOW-18 | PARTIAL | Evidence runs use empty strings for timestamps, not nullable timestamp columns. The empty-sentinel contract is still weak. | Use nullable columns or explicit state fields. |
| LOW-19 | FACT | `_ensure_column` commits each migration individually instead of a wrapped migration transaction. | Group compatible migrations transactionally. |
| LOW-20 | FACT | Notion 409 is treated as retryable. | Reclassify unless a specific Notion conflict retry case is proven. |
| LOW-21 | FACT | Vault repo sync git invocations do not set `protocol.ext.allow=never` or `protocol.file.allow=never`. | Add defense-in-depth git config flags. |
| LOW-22 | FACT | Action UI clears `actionType` to an empty string after submit. | Reset to first valid executable action. |
| LOW-23 | FACT | Web audit table reads `a.action || a.action_type`, while tests mock `action_type`. | Canonicalize API shape and test fixture. |
| LOW-24 | FACT | Live runner proof-env collection has a global opt-in behavior across steps. | Make opt-in semantics explicit per journey/step. |

## Cross-Cutting Themes

1. Secret detection and redaction must become one shared module. This closes
   HI-1, ME-12, ME-13, LOW-8, LOW-9, and improves executor/evidence safety.
2. Idempotency needs durable per-operation state, not fake in-memory maps or
   coarse job ids only. This closes HI-2 and supports CR-3/CR-4/HI-13.
3. Status strings need central constants and validation. This closes HI-19 and
   reduces drift/cancel/noise bugs.
4. Cancellation/teardown is a missing lifecycle, not a one-line fix. This
   closes CR-4, HI-9, HI-14, and related DNS/fleet/secret cleanup.
5. Webhook trust boundaries are inconsistent. Telegram has no secret,
   Discord lacks replay tolerance, and all webhook routes lack rate limits.
6. SQLite hardening is inconsistent. All workers should use `connect_db`, and
   claim/update paths need `BEGIN IMMEDIATE` plus CAS.
7. Web/API shape contracts are loose. Remove defensive frontend fallbacks after
   canonicalizing backend responses and fixtures.

## Ralphie Remediation Order

Ralphie should treat this file as the active backlog and should not route to
terminal `done` while any FACT or actionable PARTIAL item remains unresolved or
explicitly deferred with operator-facing rationale.

Wave 1 - trust boundary and secret safety:

- CR-1 Telegram webhook secret registration and verification.
- CR-2 non-root Docker runtime and Docker socket scoping.
- CR-6 logout/session revoke auth-before-CSRF.
- CR-7 Discord replay/timestamp tolerance plus interaction idempotency.
- CR-8 hosted API body cap.
- CR-9 CIDR middleware or contract removal.
- CR-11 peppered session/CSRF token hashes.
- HI-1, ME-12, ME-13, LOW-8, LOW-9 unified secret regex/redaction module.
- HI-7 webhook rate limits and ME-2/ME-3/ME-4 auth/body error cleanup.

Wave 2 - side effects, idempotency, and races:

- CR-3 real live Stripe/Chutes action execution.
- CR-5 atomic action claim and hardened worker DB connection.
- CR-10 atomic refuel credit application.
- HI-2 durable operation idempotency table.
- HI-10 atomic placement uniqueness.
- HI-11 entitlement recheck before apply.
- HI-13 audit-before-side-effect action execution.
- HI-15/HI-16 server-derived DNS/Stripe metadata.
- HI-17 honest live-proof exit/status.

Wave 3 - cancellation lifecycle and cleanup:

- CR-4 teardown rail from requested/cancelled to torn down.
- HI-8 secret cleanup on local and remote executor paths.
- HI-9 port release.
- HI-14 cancelled/torn-down DNS drift filtering.
- ME-9/ME-10 honest compose/DNS status handling.
- LOW-13 DNS upsert status preservation.

Wave 4 - schema, TTL, and drift hygiene:

- HI-3 deterministic email merge.
- HI-18 high-value foreign keys and expanded drift checks.
- HI-19 central status constants and writer validation.
- HI-20 past_due drift classification.
- HI-21 explicit transaction contract for staged revocations.
- HI-22/ME-26 handoff/share TTL and one-time reveal.
- HI-23 onboarding stale-session expiry.
- HI-24 status-preserving user upserts.
- HI-25 duplicate-email onboarding UX/test.
- LOW-16/LOW-17/LOW-18/LOW-19 schema/index cleanup.

Wave 5 - web, deployment, and operational honesty:

- ME-1 and LOW-23 canonical API/fixture response shapes.
- ME-16 action readiness probes.
- ME-17 admin action rate limiting.
- ME-18 action worker initialization.
- ME-19 CORS header reduction.
- ME-20 local-dev cookie behavior.
- ME-21 checkout cancel backend call.
- ME-22 admin fetch gating.
- ME-23 default deploy branch.
- ME-24 systemd `Environment=` quoting.
- ME-27 Notion parent-walk cache.
- ME-28 qmd loopback binding.
- Remaining low cleanup.

## Validation Floor

Ralphie should add or update focused tests with each patch set. Minimum checks
before calling a wave complete:

```bash
python3 tests/test_arclink_api_auth.py
python3 tests/test_arclink_admin_actions.py
python3 tests/test_arclink_action_worker.py
python3 tests/test_arclink_dashboard.py
python3 tests/test_arclink_entitlements.py
python3 tests/test_arclink_executor.py
python3 tests/test_arclink_fleet.py
python3 tests/test_arclink_ingress.py
python3 tests/test_arclink_live_runner.py
python3 tests/test_arclink_provisioning.py
python3 tests/test_deploy_regressions.py
bash -n deploy.sh bin/*.sh test.sh ralphie.sh
```

When web files change:

```bash
cd web
npm run lint
npm test
npm run build
```

When shell service/unit generation changes, include the relevant focused tests
from `tests/test_arclink_agent_user_services.py`, `tests/test_health_regressions.py`,
and `tests/test_deploy_regressions.py`.

## Guardrails

- Do not inspect or commit `arclink-priv/`, live secrets, user Hermes homes, or
  external account data unless the operator explicitly asks.
- Do not run live deploys, upgrades, Stripe/Chutes/Cloudflare mutations, or
  public bot mutations as part of this remediation unless explicitly requested.
- Do not paper over no-op live paths with UI labels. Fix the provider mutation
  or fail closed.
- Prefer narrowly scoped commits by wave or sub-wave.
- Every security/trust-boundary fix should include regression coverage.
