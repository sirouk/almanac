# Coverage Matrix

## Goal Coverage

| Goal / criterion | Planning coverage | BUILD proof required |
| --- | --- | --- |
| Use the 2026-05-11 audit verification file as active backlog | `IMPLEMENTATION_PLAN.md` and this matrix name `research/RALPHIE_SOVEREIGN_AUDIT_VERIFICATION_20260511.md` as authority | Keep every FACT/actionable PARTIAL open until fixed or explicitly deferred. |
| Start with Wave 1 security and trust-boundary repairs | Wave 1 is the first BUILD checkpoint | Source review plus focused tests for webhook, container, hosted API, auth/session, and secret-redaction boundaries. |
| Ignore FICTION items as active remediation | `ME-11` and `ME-25` are identified as regression-awareness only | Do not spend BUILD effort unless a regression is found. |
| Treat PARTIAL items by corrected scope | Plan requires corrected audit wording | Each PARTIAL fix/deferral must name the corrected scope. |
| No private state or Hermes core edits | Build gate blocks private-state reads and Hermes core changes | Diff review must show only public ArcLink surfaces. |
| No unauthorized live mutation | Build gate blocks deploys, provider proof, bot mutation, Docker host mutation, and production flows | Completion notes must list skipped live gates. |
| Compare implementation paths | Research summary, dependency research, stack snapshot, and implementation plan compare viable paths | BUILD should update notes if the selected path changes. |

## 2026-05-12 Closure Status

The post-commit revisit found no remaining FACT or actionable PARTIAL source
gaps in the current local tree. The only active correction was aligning the web
browser fixture with backend action-readiness behavior for `comp`.

A later three-pass follow-up tightened additional local congruence gaps in the
same boundary: admin action disabled-state rendering, browser API client
route/auth-shape tests, hosted API CORS and WSGI 405 status text, deploy branch
defaults, Docker build-context excludes, and fake E2E browser-cookie mutation
coverage.

Live/provider/deploy proof remains intentionally outside local source closure:
no live Stripe, Chutes, Cloudflare, Tailscale, Telegram, Discord, Notion, remote
Docker host, deploy, upgrade, Docker install/upgrade, payment-flow, or public-bot
mutation proof was run without explicit operator authorization.

## Wave 1 Coverage

| Audit IDs | Target behavior | Primary files | Required focused tests |
| --- | --- | --- | --- |
| `CR-1` | Telegram webhook registration and request handling require a secret; missing config fails closed | `python/arclink_telegram.py`, `python/arclink_hosted_api.py` | Telegram and hosted API tests. |
| `CR-2` | Containers run non-root and Docker socket access is limited to justified services | `Dockerfile`, `compose.yaml` | Docker/loopback/deploy regression tests. |
| `CR-6`, `LOW-1` | Browser session routes authenticate before CSRF-sensitive mutation | `python/arclink_api_auth.py`, `python/arclink_hosted_api.py` | Auth and hosted API tests. |
| `CR-7` | Discord webhooks enforce timestamp tolerance and interaction replay/idempotency | `python/arclink_discord.py`, `python/arclink_hosted_api.py` | Discord tests. |
| `CR-8`, `ME-4` | Request body caps and invalid JSON errors are enforced before downstream field handling | `python/arclink_hosted_api.py` | Hosted API tests. |
| `HI-5`, `HI-6` | Early hosted API returns receive CORS headers and `OPTIONS` preflights are route-checked with accurate `Allow` headers | `python/arclink_hosted_api.py` | Hosted API CORS/preflight tests. |
| `CR-9` | Backend/admin/control routes enforce configured CIDR boundary or remove the env contract | `python/arclink_hosted_api.py`, `python/arclink_control.py` | Hosted API and loopback hardening tests. |
| `CR-11` | Session and CSRF token hashes use server-side pepper with back-compat reads | `python/arclink_api_auth.py`, `python/arclink_control.py` | Auth/control DB tests. |
| `HI-1`, `ME-12`, `ME-13`, `LOW-8`, `LOW-9` | Secret detection/redaction is centralized and redacts before truncation | `python/arclink_secrets_regex.py` and importers | Secret regex plus provisioning, executor, memory, and evidence tests as touched. |
| `HI-4`, `ME-2`, `ME-3` | Browser auth extraction, user-facing errors, and session kind checks are canonical | Auth/hosted API modules | Auth and hosted API tests. |
| `HI-7` | Stripe, Telegram, and Discord webhooks rate-limit before expensive verification/dispatch | `python/arclink_hosted_api.py`, rate-limit helpers | Hosted API, Telegram, and Discord tests. |

## Later Wave Coverage

| Wave | Theme | Representative IDs |
| --- | --- | --- |
| Wave 2 | Provider side effects, operation idempotency, worker races, credits, placement, entitlement rechecks, audit-before-side-effect, live-proof honesty, queueable action truth, Stripe webhook replay, dashboard secret hash churn, and safe worker errors | `CR-3`, `CR-5`, `CR-10`, `HI-2`, `HI-10`, `HI-11`, `HI-12`, `HI-13`, `HI-15`, `HI-16`, `HI-17`, `ME-6`, `ME-8`, `LOW-11` |
| Wave 3 | Cancellation/teardown, secret cleanup, port release, DNS drift filtering, compose/DNS status honesty, DB-safe deployment IDs, atomic secret materialization, and DNS upsert preservation | `CR-4`, `HI-8`, `HI-9`, `HI-14`, `ME-7`, `ME-9`, `ME-10`, `LOW-6`, `LOW-7`, `LOW-13` |
| Wave 4 | Identity merge, schema/status constraints, TTL/one-time reveal, onboarding expiry, status-preserving upserts, memory prompt boundaries, recovery metadata, evidence timestamps, timestamp normalization, indexes, and migrations | `HI-3`, `HI-18`, `HI-19`, `HI-20`, `HI-21`, `HI-22`, `HI-23`, `HI-24`, `HI-25`, `ME-14`, `ME-26`, `LOW-10`, `LOW-12`, `LOW-15`, `LOW-16`, `LOW-17`, `LOW-18`, `LOW-19` |
| Wave 5 | Web/API shapes, hosted API connection contract, readiness, rate limits, executor permission model, CORS/cookies, checkout/admin UI, deploy/systemd/qmd/git hardening, Notion cache/conflict handling, live proof opt-ins, and operator snapshot truth | `ME-1`, `ME-5`, `ME-15`, `ME-16`, `ME-17`, `ME-18`, `ME-19`, `ME-20`, `ME-21`, `ME-22`, `ME-23`, `ME-24`, `ME-27`, `ME-28`, `LOW-2`, `LOW-3`, `LOW-4`, `LOW-5`, `LOW-14`, `LOW-20`, `LOW-21`, `LOW-22`, `LOW-23`, `LOW-24` |

## Required Artifact Coverage

| Required artifact | Status |
| --- | --- |
| `research/RESEARCH_SUMMARY.md` | Updated with confidence, active backlog, repository finding, path comparison, assumptions, risks, and verdict. |
| `research/CODEBASE_MAP.md` | Maps directories, entrypoints, runtime lanes, Wave 1 hotspots, later hotspots, tests, and architecture assumptions. |
| `research/DEPENDENCY_RESEARCH.md` | Documents stack components, pins, alternatives, integration posture, risks, and validation dependencies. |
| `research/COVERAGE_MATRIX.md` | Maps goals, Wave 1 coverage, later waves, artifact coverage, and completion rules. |
| `research/STACK_SNAPSHOT.md` | Provides ranked stack hypotheses, deterministic confidence score, and alternatives. |
| `IMPLEMENTATION_PLAN.md` | Provides goal, constraints, retry checkpoint, selected path, validation criteria, and completed local source-remediation checklist with live proof gates explicitly operator-gated. |
| `consensus/build_gate.md` | Records no-secret BUILD permission and blocked live/private operations. |

## Completion Rules

BUILD can claim a wave or slice complete only when every in-scope item is
repaired locally with focused tests or explicitly deferred with:

- audit ID;
- risk if left unresolved;
- current fail-closed or disabled behavior;
- required operator action or policy decision;
- focused tests preserving the interim boundary.

Terminal audit completion is not reached while any FACT or actionable PARTIAL
finding remains unresolved or undeferred. As of the 2026-05-12 closure revisit,
the local source-remediation backlog is closed; live/operator-authorized proof
remains a separate gate.
