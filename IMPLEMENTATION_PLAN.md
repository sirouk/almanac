# ArcLink Sovereign Audit Implementation Plan

## Goal

Resolve the verified ArcLink Sovereign Control Node audit backlog documented in
`research/RALPHIE_SOVEREIGN_AUDIT_VERIFICATION_20260511.md`, starting with Wave
1 security and trust-boundary repairs.

BUILD must not claim terminal completion while any FACT or actionable PARTIAL
finding remains unresolved or lacks an explicit operator-facing deferral with
risk, current fail-closed behavior, required operator action, and preserving
tests.

## Constraints

- Do not touch `arclink-priv`, live secrets, user Hermes homes, deploy keys,
  production services, external provider accounts, payment flows, or Hermes
  core.
- Do not run live deploys, upgrades, Docker install/upgrade flows, public bot
  mutations, live Stripe/Chutes/Notion/Cloudflare/Tailscale proof,
  domain-or-Tailscale ingress proof, or credential-dependent checks without
  explicit authorization for the named flow.
- Use existing ArcLink Python, Bash, SQLite, Docker Compose, and Next/web
  structures.
- Preserve the dirty worktree. Treat existing modified files as user-owned or
  prior generated work unless the operator says otherwise.
- Treat `ME-11` and `ME-25` as FICTION/outdated regression-awareness items, not
  active remediation defects.
- Treat PARTIAL items according to the corrected ground-truth wording in the
  audit verification file.
- Do not use browser/TLS impersonation, `curl_cffi`, or unofficial provider
  registration bypasses.

## PLAN Retry Checkpoint

This PLAN pass repaired the prior handoff inconsistency: Wave 1, later BUILD
phases, and validation tasks are not marked complete in this plan. Existing
dirty-tree code changes and historical completion notes may provide clues, but
they do not close checklist items. BUILD entry is Phase 0 inventory followed by
Phase 1 Wave 1 verification/repair.

## 2026-05-12 Revisit Checkpoint

The post-commit revisit rechecked the audit verification report against the
current committed source. The runtime and test fixes for Phases 0-5 are present
locally; the remaining gap was stale checklist state plus a browser fixture that
still mocked `comp` as pending even though backend readiness exposes it as an
executable modeled action when probes pass. This plan now reflects the local
closure state. Live/provider/deploy proof remains explicitly operator-gated and
was not run.

Follow-up: a three-pass source, user-journey, and deployment-runtime sweep found
additional local congruence gaps in tests/UI/deploy packaging rather than new
provider-live requirements. Those were fixed and covered in the current working
tree; see `research/BUILD_COMPLETION_NOTES.md`.

## Selected Path

Use wave-ordered verification and repair in the current public worktree.

1. Verify each audit ID directly in source and focused tests before editing,
   because broad local modifications already exist.
2. Patch only missing or regressed public ArcLink behavior.
3. Add or update focused regression tests for each changed trust boundary.
4. Record fixed IDs, tests run, skipped live gates, and remaining risks in
   completion notes after validation.
5. Continue to later waves only after Wave 1 is locally proven.

## Alternatives Compared

| Path | Strengths | Weaknesses | Decision |
| --- | --- | --- | --- |
| Wave-ordered verification and repair of the current worktree | Preserves existing edits, follows the audit's risk order, keeps patches small, and starts with no-secret security boundaries | Requires careful source/test review to avoid double-fixing partial work | Selected. |
| Clean reimplementation of Wave 1 from audit text | Simple mental model | High risk of overwriting user/prior changes and duplicating existing fixes | Rejected. |
| Documentation-only triage | Low runtime risk | Does not resolve verified behavior defects | Rejected for FACT/actionable PARTIAL items. |
| Broad release smoke before focused review | Useful after local slices pass | Too noisy for precise security regressions and may require host state | Deferred. |
| Live provider/deploy proof during BUILD | Strongest end-to-end confidence | Blocked by no-secret/no-live-mutation constraints | Requires explicit operator authorization. |

## Validation Criteria

Wave 1 can be handed off as complete only when source and focused tests show:

- Telegram webhook registration and request handling require a configured
  secret and fail closed when missing or mismatched.
- App containers run non-root, and Docker socket access is scoped to justified
  services.
- Logout/session and portal-link mutations authenticate before CSRF-sensitive
  actions.
- Discord webhook handling enforces timestamp tolerance and interaction replay
  idempotency.
- Hosted API request bodies are capped before JSON parsing, and malformed JSON
  returns canonical `invalid_json`.
- Hosted API early errors consistently carry CORS headers, and `OPTIONS`
  preflights are route-checked with an accurate `Allow` response.
- Admin/control/backend routes enforce configured CIDR boundaries or the env
  contract is explicitly removed with tests and docs.
- Session and CSRF token hashes use HMAC-SHA256 with a server-side pepper and
  compatibility reads where required.
- Secret detection/redaction is centralized, covers audit-listed key shapes,
  and redacts before truncation.
- Webhook rate limits, browser/API credential separation, generic auth errors,
  and session-kind enforcement have focused coverage.

Terminal audit completion additionally requires every later FACT and
actionable PARTIAL item to be fixed or explicitly deferred.

## BUILD Tasks

All BUILD checkboxes are intentionally open at PLAN handoff. The current
worktree may contain candidate fixes or prior local verification notes, but
BUILD must re-verify source behavior and focused tests before marking any
audit ID or validation item complete.

### Phase 0 - Preserve And Inventory

- [x] Review `git status --short` before each patch slice.
- [x] Read the active audit verification section for the slice before changing
  code.
- [x] Confirm whether current source already closes the targeted audit IDs.
- [x] Keep unrelated dirty-tree edits intact.
- [x] Keep `ME-11` and `ME-25` out of active remediation unless a regression is
  discovered.

### Phase 1 - Wave 1 Trust Boundaries

- [x] `CR-1`: Verify or implement Telegram webhook secret registration and
  request verification with fail-closed behavior.
- [x] `CR-2`: Verify or implement non-root Docker runtime and scoped Docker
  socket mounts, with service-level justification.
- [x] `CR-6` and `LOW-1`: Verify or implement auth-before-CSRF ordering for
  logout/session and portal-link mutations.
- [x] `CR-7`: Verify or implement Discord timestamp tolerance and interaction
  idempotency.
- [x] `CR-8` and `ME-4`: Verify or implement hosted API body caps and canonical
  invalid JSON handling.
- [x] `HI-5` and `HI-6`: Verify or implement CORS on early hosted API returns
  and route-checked `OPTIONS` handling with accurate `Allow` headers.
- [x] `CR-9`: Verify or implement backend CIDR enforcement, or remove the env
  contract with documentation and tests.
- [x] `CR-11`: Verify or implement peppered session/CSRF token hashes with
  migration-compatible reads.
- [x] `HI-1`, `ME-12`, `ME-13`, `LOW-8`, and `LOW-9`: Verify or implement the
  unified secret detection/redaction module and update required callers.
- [x] `HI-4`, `HI-7`, `ME-2`, and `ME-3`: Verify or implement browser/API auth
  extraction, webhook rate limits, generic auth errors, and session kind
  enforcement.

### Phase 2 - Side Effects, Idempotency, And Races

- [x] `CR-3`: Make live Stripe/Chutes action paths execute real adapters or
  fail closed honestly.
- [x] `CR-5`: Make action-worker claims atomic with hardened DB connections.
- [x] `CR-10`: Make refuel credit application transactional and guarded.
- [x] `HI-2`: Add durable operation idempotency keyed by operation kind and
  idempotency key.
- [x] `HI-10`: Add atomic active-placement uniqueness.
- [x] `HI-11`: Recheck entitlement and user state before apply.
- [x] `HI-12`: Either wire `reprovision`/`rollout` for real execution or remove
  them from queueable backend action types while preserving disabled dashboard
  readiness.
- [x] `HI-13`: Record attempt/audit before external side effects and update
  result afterward.
- [x] `HI-15` and `HI-16`: Derive DNS/Stripe metadata server-side and make
  comp/cancel idempotent.
- [x] `HI-17`: Make requested live proof fail non-zero when it cannot actually
  run and persist honest evidence status.
- [x] `ME-6`: Treat concurrent Stripe webhook duplicate inserts as
  replay/pending and return 200 rather than surfacing transient races.
- [x] `ME-8`: Update dashboard password hash only when a secret is newly
  generated, not on every apply tick.
- [x] `LOW-11`: Add safe action-worker error classes/codes without exposing
  secret detail.

### Phase 3 - Cancellation And Cleanup

- [x] `CR-4`: Implement teardown lifecycle from requested/cancelled to torn
  down.
- [x] `HI-8`: Clean local/remote secret material after successful compose and
  validate SSH key path ownership/mode/no-symlink.
- [x] `HI-9`: Release or filter ports for inactive deployments.
- [x] `HI-14`: Suppress cancelled/torn-down deployments from DNS drift views.
- [x] `ME-7`: Normalize or reject deployment IDs before using them in
  Nextcloud/Postgres database names.
- [x] `ME-9` and `ME-10`: Make compose/DNS status parsing project-aware and
  honest about transport/provider failures.
- [x] `LOW-6` and `LOW-7`: Chmod secret materializer parent directories, assert
  private permissions, and use atomic temp+rename with per-file locking.
- [x] `LOW-13`: Preserve provisioned DNS row status when the desired tuple is
  unchanged.

### Phase 4 - Schema, TTL, Identity, And Drift

- [x] `HI-3`: Make email merge deterministic, complete, and auditable.
- [x] `HI-18` and `HI-19`: Add high-value foreign keys/checks or centralized
  status validation where feasible.
- [x] `HI-20`: Split owed-service subscription states from orphan drift states.
- [x] `HI-21`: Remove or assert the staged revocation transaction contract.
- [x] `HI-22` and `ME-26`: Add TTL and one-time/reissue semantics for revealable
  handoff/share secrets.
- [x] `HI-23`: Expire stale onboarding sessions through a batch path.
- [x] `HI-24`: Preserve suspended/merged user statuses unless explicitly
  transitioned.
- [x] `HI-25`: Add fail-loud duplicate-email onboarding behavior by corrected
  partial scope.
- [x] `ME-14`: Frame memory-synthesis vault snippets as untrusted source text
  and reject imperative/URL-shaped prompt-injection output.
- [x] `LOW-10`: Prefer cached handoff metadata during recovery when available.
- [x] `LOW-12`: Stop serializing unset evidence timestamps as `0.0`; use
  `null`, omission, or an explicit state field.
- [x] `LOW-15`: Normalize `+00:00` and `Z` timestamp helpers before string
  comparisons and converge call sites.
- [x] `LOW-16`, `LOW-17`, `LOW-18`, and `LOW-19`: Add targeted indexes,
  active-factor uniqueness, stronger evidence timestamp contract, and safer
  grouped migrations.

### Phase 5 - Web, Runtime, And Operational Honesty

- [x] `ME-1` and `LOW-23`: Canonicalize backend/web response shapes and
  fixtures.
- [x] `ME-5` and `LOW-3`: Document the hosted API single-thread SQLite
  connection contract or switch health and request paths to per-request
  connections if threaded WSGI remains supported.
- [x] `LOW-2`: Return a clean 404 or explicit empty not-found result when user
  provisioning status is requested for a missing deployment ID.
- [x] `ME-16` and `ME-17`: Add real action readiness probes and admin action
  rate limits.
- [x] `ME-18`: Initialize action-worker schema/connection handling without
  repeated per-loop migration work.
- [x] `ME-19` and `ME-20`: Tighten CORS headers and document or adjust local
  cookie behavior.
- [x] `ME-21` and `ME-22`: Wire checkout cancel to backend and gate admin
  secondary fetches.
- [x] `ME-23` and `ME-24`: Default deploy branch to `arclink` and quote systemd
  environment values.
- [x] `ME-15`: Document SSH/machine executor permission boundaries or make
  broader machine-path access opt-in/allowlisted.
- [x] `ME-27` and `ME-28`: Cache Notion parent-walk decisions and always bind
  single-port qmd to loopback.
- [x] `LOW-4`, `LOW-5`, `LOW-14`, `LOW-20`, `LOW-21`, `LOW-22`, and `LOW-24`:
  Normalize misconfig envelopes, consider Strict CSRF cookies where safe,
  compute operator template readiness from actual state, reclassify Notion
  conflicts, harden git protocol usage, reset UI action type to a valid value,
  and make live proof env opt-ins explicit per step.

### Phase 6 - Completion Notes And Validation

- [x] Update `research/BUILD_COMPLETION_NOTES.md` after each BUILD slice.
- [x] Run focused validation for touched files.
- [x] Run broad local release validation only after focused slices pass.
- [x] Keep live provider, public bot, Docker host, and production deploy proof
  gated behind explicit operator authorization; no such live proof was run in
  the local audit-remediation pass.

## Wave 1 Validation Floor

Run touched subsets plus:

```bash
git diff --check
python3 -m py_compile python/arclink_hosted_api.py python/arclink_api_auth.py python/arclink_telegram.py python/arclink_discord.py python/arclink_secrets_regex.py
python3 tests/test_arclink_api_auth.py
python3 tests/test_arclink_hosted_api.py
python3 tests/test_arclink_telegram.py
python3 tests/test_arclink_discord.py
python3 tests/test_arclink_secrets_regex.py
python3 tests/test_arclink_docker.py
python3 tests/test_loopback_service_hardening.py
```

If shell files change:

```bash
bash -n deploy.sh bin/*.sh test.sh ralphie.sh
```

If web files change:

```bash
cd web
npm test
npm run lint
npm run build
```
