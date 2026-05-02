# Coverage Matrix
<!-- refreshed: 2026-05-02 plan phase -->

## Goal Coverage

| Goal / criterion | Current coverage | Remaining gap / risk | Validation surface |
| --- | --- | --- | --- |
| Transform ArcLink into ArcLink | Additive `arclink_*` modules, ArcLink docs, web app, product config/env precedence | Broad public rebrand must not break ArcLink runtime compatibility | Product config tests, docs truth checks, hygiene scan |
| Preserve ArcLink services/tests | Existing `bin/`, `python/arclink_*`, systemd units, Compose services, focused tests | Future ArcLink refactors could drift from deploy scripts | ArcLink regression tests and deploy/health checks |
| Chutes-first provider | `arclink_chutes.py`, model provider config, fake key lifecycle, diagnostics | Live account/key lifecycle unverified | Chutes/provider tests; live E2E when credentials exist |
| Stripe checkout/entitlement | Fake checkout/webhook, subscription mirror, entitlement gates, reconciliation, billing portal contract | Live Stripe proof blocked | Entitlement/API/fake E2E tests; live E2E later |
| Cloudflare DNS/subdomains | Prefix reservation, DNS intent, fake Cloudflare, drift, Traefik labels, diagnostics | Live DNS/tunnel proof blocked | Ingress/executor tests; live E2E later |
| Docker Compose provisioning | Dry-run plan, fake runner, resource/health/dependency validation, live gate | Real host mutation blocked until deliberate live run | Executor/provisioning/host-readiness tests |
| Web onboarding | Next.js onboarding route plus hosted API/session contracts | Final live deployment identity/edge not proven | Web smoke, API/auth, fake E2E |
| Telegram/Discord onboarding | Shared public bot state machine, fake-mode adapters, runtime adapter tests | Live transport blocked by bot credentials | Bot/adapter tests; live E2E later |
| User dashboard | Dashboard read model and web user dashboard route | Live production data wiring/deployment proof pending | Dashboard/API/web tests |
| Admin dashboard | Admin read model, web admin route, operator snapshot, scale operations view, guarded actions | Live production auth/edge proof pending | Dashboard/API/web tests |
| Health and observability | Service health tables, health-watch, diagnostics, operator snapshot, alert docs | External alerting not yet configured | Health/dashboard/diagnostics tests, runbooks |
| Fleet/scale operations | Fleet registry, placement, action worker, rollout/rollback model | Multi-host live proof still future | Fleet/action/rollout/API tests |
| Data safety | Isolation docs, state-root planning, teardown safeguards, secret material rejection | Live backup/restore proof depends on host/account access | Data-safety docs, hygiene tests, executor tests |
| Documentation truth | ArcLink docs, live-secret prerequisites, completion/status docs | Must stay synced after every build slice | Documentation truth tests and review |

## Production Grade Steering Coverage

| Production item | Status | Evidence | Remaining blocker |
| --- | --- | --- | --- |
| P1 Hosted API contract | Covered | `python/arclink_hosted_api.py`, OpenAPI docs/tests | None non-external. |
| P2 Mutating route auth/CSRF/audit | Covered | `python/arclink_api_auth.py`, hosted API negative tests | None non-external. |
| P3 Stripe boundary | Covered for fake/no-secret | Entitlement/adapters/fake E2E tests | Live Stripe credentials. |
| P4 Cloudflare boundary | Covered for fake/no-secret | Ingress/executor/fake Cloudflare tests | Live Cloudflare zone/token. |
| P5 Docker Compose executor | Covered for dry-run/fake/live-gated boundary | `arclink_executor.py`, provisioning tests | Production host and deliberate live flag. |
| P6 Chutes provider flow | Covered for catalog/fake/no-secret | Chutes tests, diagnostics | Live Chutes account/key strategy. |
| P7 Telegram/Discord parity | Covered for shared contract/fake mode | Public bot and adapter tests | Live bot credentials. |
| P8 User dashboard | Covered for no-secret UI/read model | Dashboard/API/web surfaces | Live deployment data proof. |
| P9 Admin dashboard | Covered for no-secret UI/read model | Admin route, operator/scale snapshots, action forms | Production identity/edge proof. |
| P10 Web UI quality | Covered by web app and product checks | Brand docs, web tests, Playwright checks | Must be rerun after UI edits. |
| P11 Fake E2E journey | Covered | `tests/test_arclink_e2e_fake.py` | None non-external. |
| P12 Live E2E harness | Scaffolded, not live-proven | Live journey, live runner, evidence ledger, secret-gated tests | Stripe, Cloudflare, Chutes, Telegram, Discord, host credentials. |
| P13 Deployment assets | Covered | Env example, secret checklist, ingress/backup/runbook docs | Final host-specific values. |
| P14 Observability | Covered for current stack | Events, health snapshots, diagnostics, alert docs, admin views | External alerting setup future. |
| P15 Data safety | Covered for current stack | Data-safety docs, secret guards, isolation planning | Live backup/restore proof. |
| P16 Documentation truth | Covered | Live blockers named; docs avoid live overclaiming | Must remain enforced. |

## Test Coverage Map

| Test family | Covered surface |
| --- | --- |
| `tests/test_arclink_product_config.py` | Product defaults, env precedence, legacy compatibility. |
| `tests/test_arclink_schema.py` | `arclink_*` schema, prefixes, audit/events, subscriptions, health, provisioning helpers. |
| `tests/test_arclink_chutes_and_adapters.py` | Chutes catalog, fake key references, fake Stripe, fake Cloudflare, Traefik labels. |
| `tests/test_arclink_entitlements.py` | Stripe signatures, webhooks, subscriptions, entitlement gates, comp/reconciliation/atomicity. |
| `tests/test_arclink_onboarding.py` | Public sessions, fake checkout, entitlement readiness, channel handoff, secret rejection. |
| `tests/test_arclink_ingress.py` / `tests/test_arclink_access.py` | DNS/Traefik/access planning and raw SSH-over-HTTP rejection. |
| `tests/test_arclink_provisioning.py` / `tests/test_arclink_executor.py` | Deployment intent, dry-run/fake execution, live gates, replay/digest/dependency guards. |
| `tests/test_arclink_api_auth.py` / `tests/test_arclink_hosted_api.py` | Sessions, CSRF, rate limits, scopes, hosted routes, webhooks, safe errors, operator snapshots. |
| `tests/test_arclink_dashboard.py` / `tests/test_arclink_product_surface.py` | User/admin read models and local WSGI product probe. |
| `tests/test_arclink_public_bots.py`, `tests/test_arclink_telegram.py`, `tests/test_arclink_discord.py` | Shared bot state machine and fake/live adapter boundaries. |
| `tests/test_arclink_host_readiness.py` / `tests/test_arclink_diagnostics.py` | Host checks and secret-safe provider diagnostics. |
| `tests/test_arclink_fleet.py`, `tests/test_arclink_action_worker.py`, `tests/test_arclink_rollout.py` | Fleet placement, queued action execution, rollout/rollback state. |
| `tests/test_arclink_live_journey.py`, `tests/test_arclink_evidence.py`, `tests/test_arclink_live_runner.py` | Ordered live proof, redacted evidence, dry-run/live runner states. |
| `tests/test_arclink_e2e_fake.py` / `tests/test_arclink_e2e_live.py` | Full fake journey and secret-gated live scaffold. |
| `web/tests/` | API client smoke, page smoke, and browser product checks. |

## Coverage Verdict

Coverage is sufficient for BUILD handoff. All non-external work currently
named by the Production 1-16 steering is represented by code, docs, and tests.
The only remaining incomplete production item is the credentialed execution
portion of P12, which is externally blocked by live provider accounts,
credentials, and production-host access.
