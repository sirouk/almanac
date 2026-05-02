# Coverage Matrix

| Goal / success criterion | Existing coverage | Plan coverage | Remaining gap / risk | Validation |
| --- | --- | --- | --- | --- |
| Transform Almanac into ArcLink identity | `python/arclink_product.py`, ArcLink docs, additive `arclink_*` tables | Continue staged identity work after contracts settle | Broad rename could break mature Almanac paths | Product config tests, docs review, public hygiene |
| Preserve legacy compatibility | Env alias behavior and existing deploy paths | Keep `ALMANAC_*` compatibility where needed | Future env additions could skip alias rules | Product config and deploy regression tests |
| Preserve Hermes/qmd/memory | Runtime pins, qmd scripts, managed-context plugin, memory synth, tests | Provisioning intent keeps these lanes in every deployment plan | Renderer/executor drift could omit a lane | qmd/plugin/memory tests plus provisioning/executor assertions |
| Chutes-first inference | Chutes defaults, catalog parser, fake key manager | Add catalog refresh and live key manager behind E2E gate | Live key lifecycle unverified | Chutes tests now; live E2E later |
| Stripe entitlement gate | Webhook verifier, entitlement handler, subscription mirror, gate advancement | Keep entitlement mutation explicit and idempotent | Live checkout/webhook delivery unverified | Entitlement and onboarding tests; live E2E later |
| Public onboarding | Durable web/Telegram/Discord sessions, fake checkout, funnel events | Website and public bot adapters share one contract | Hosted redirects and live clients absent | Onboarding, product surface, public bot tests |
| Cloudflare DNS/subdomains | Fake Cloudflare client, desired DNS persistence, drift events, DNS allowlist | Add live adapter through executor and E2E flag | Token/zone unavailable for unit tests | Ingress/executor tests; live E2E later |
| Traefik ingress | Host planner and role label renderer with golden coverage | Render per-service host routing for deployments | Runtime Traefik smoke not live | Golden fixture, provisioning tests, later Compose smoke |
| Obscure deployment prefixes | Prefix reservation, generator, denylist, collision retry | Use in onboarding/provisioning | Product policy may change | Schema and onboarding tests |
| Nextcloud/files | Existing Nextcloud and dedicated isolation decision | Render isolated Nextcloud plus DB/Redis services | Resource cost may grow | Access and provisioning tests |
| code-server | Existing code-server scripts/access helpers | Route by host in provisioning intent | Proxy/websocket smoke deferred | Access tests; browser smoke later |
| SSH/TUI | Cloudflare Access TCP strategy guard | Implement tunnel/access records later | No live tunnel yet | Raw SSH-over-HTTP rejection tests |
| Website surface | Local WSGI prototype plus Next.js 15 + Tailwind 4 web app with landing, login, onboarding, user/admin dashboard views (~1,593 lines across 9 source files) | Wire web app to hosted API; extend views with real data flow | Web app views are static/mock; not yet consuming live API | Product surface tests, web app build/test, future browser E2E |
| Public Telegram/Discord bots | Deterministic turn handler plus runtime adapters (`arclink_telegram.py`, `arclink_discord.py`) with fake-mode fallback, long-polling (Telegram) and interaction handling (Discord) | Runtime adapters landed with fake transport; live HTTP transport when tokens present | Live bot tokens absent in unit tests; live HTTP polling/gateway not yet implemented | Public bot tests, Telegram/Discord adapter tests (11 tests); live bot E2E later |
| User dashboard | Dashboard read model, local user view, and Next.js user dashboard page | Wire Next.js view to hosted API user endpoints | Views exist but use mock data; live API integration needed | Dashboard/product surface tests, web app build |
| Admin dashboard | Admin read model, local admin view, and Next.js admin dashboard page | Wire Next.js view to hosted API admin endpoints | Views exist but use mock data; live API integration needed | Admin/dashboard/executor tests, web app build |
| Active session counts | Admin dashboard security counts enforce active/unrevoked/unexpired filtering | Preserve before broader hosted API work | Future dashboard query changes could overcount expired or revoked sessions | Dashboard regression test |
| Admin actions | Queued action intents require reason/idempotency and reject secrets | Future worker consumes only audited intent | Executor could bypass audit if not enforced | Admin action and executor tests |
| API/auth boundary | User/admin sessions, CSRF checks, rate limits, MFA-ready admin factors, scoped reads, queued mutation helpers, provider state reads, reconciliation drift API, and hosted WSGI API (1,078 lines) with route dispatch, session transport, CORS, request-ID, safe errors, health, billing portal, and Telegram/Discord webhook routes | Extend hosted API with versioned path prefix and rate-limit headers before frontend/live actions | Hosted layer exists but not yet deployed behind production identity provider | API/auth tests, hosted API tests (39 tests), public hygiene, future browser/API E2E |
| Public onboarding invalid-input mutation | `start_public_onboarding_api()` validates channel and identity before rate limiting | Preserve this guard before hosted API work | Future transport routes could bypass the shared validator path | API/auth regression plus focused acceptance probe |
| Session revocation guard | Revocation helper validates `user`/`admin` kinds and rejects missing target sessions before mutation or audit | Preserve before broader hosted API work | Future revocation paths could reintroduce success-shaped missing-session responses | API/auth regression test for missing user and admin sessions |
| Product-surface generic errors | Domain errors are intentionally user-facing; generic handler uses safe copy | Preserve safe generic responses while keeping domain errors useful | Raw exception text could leak implementation detail if future handlers bypass the guard | Product-surface regression test |
| Public bot rate limiting | Public bot skeleton shares onboarding session storage and rate-limit rails | Preserve shared rate limiting while adding live clients later | Live bot entrypoints could bypass website/API throttling | Public bot regression test |
| Live executor boundary | Fail-closed executor types, fake resolver/adapters, replay guards | Add live adapters behind explicit E2E gates | No real Docker/provider mutation enabled | Executor tests; live E2E later |
| Health/fleet operations | Health scripts, health-watch, service health table | Dashboard reads service snapshots and failures | Fleet observability stack deferred | Health and dashboard tests |
| Per-tenant isolation | Docker user homes and dedicated Nextcloud decision | Dedicated state roots in provisioning plan | Quota/backup/resource policy not complete | Access/provisioning/rollback tests |
| No live secrets in unit tests | Fakes/fixtures and hygiene tests | Keep all live paths opt-in | SDK calls could leak into CI if unguarded | Public hygiene and no-secret suites |
| SQLite-first with Postgres path | Stable text IDs and helper validation | Keep schema portable | SQLite-specific assumptions can creep in | Schema tests and migration review |
| Honest E2E docs | `docs/arclink/live-e2e-secrets-needed.md` | Update as live adapters land | Unit success could be mistaken for live readiness | Documentation truth checks |

## Current ArcLink Test Coverage

| Test file | Covered surface |
| --- | --- |
| `tests/test_arclink_product_config.py` | Product defaults, env precedence, blank fallback, legacy compatibility. |
| `tests/test_arclink_schema.py` | ArcLink tables, onboarding tables, prefix reservation/generation, audit/events, subscriptions, service health, provisioning helpers, drift checks. |
| `tests/test_arclink_chutes_and_adapters.py` | Chutes catalog validation, fake key references, fake Stripe sessions/webhooks, fake Cloudflare drift, Traefik labels. |
| `tests/test_arclink_entitlements.py` | Stripe signature rejection, paid gate lift, invoice mapping, replay behavior, allowlists, manual comp, atomic rollback, transaction ownership, entitlement preservation. |
| `tests/test_arclink_onboarding.py` | Public sessions, duplicate prevention, fake checkout, checkout cancellation/expiry, entitlement-gated readiness, channel handoff, secret rejection. |
| `tests/test_arclink_ingress.py` | DNS persistence/drift and Traefik golden labels. |
| `tests/test_arclink_access.py` | Dedicated Nextcloud decision and SSH-over-HTTP rejection. |
| `tests/test_arclink_provisioning.py` | Dry-run service/DNS/access intent, entitlement visibility, no-secret validation, retry after secret repair, rollback planning. |
| `tests/test_arclink_admin_actions.py` | Reason-required queued actions, idempotency, audit rows, secret-safe metadata, no live side effects. |
| `tests/test_arclink_dashboard.py` | User dashboard summary and admin dashboard operational/failure projections. |
| `tests/test_arclink_api_auth.py` | User/admin sessions, token hashing, scoped reads, public onboarding APIs, rate limits, CSRF checks, MFA-ready admin mutations, and secret masking. |
| `tests/test_arclink_executor.py` | Live-gate refusal, secret resolver contracts, fake apply result shape, digest mismatch rejection, provider idempotency, secret-material guards, Compose dependency validation. |
| `tests/test_arclink_product_surface.py` | Local WSGI first screen, fake checkout flow, user/admin dashboard rendering, queued admin actions, no DNS mutation, mobile overflow guards, favicon route. |
| `tests/test_arclink_public_bots.py` | Telegram/Discord public bot conversation-state contract, fake checkout, unsupported channel rejection, metadata secret rejection. |
| `tests/test_arclink_telegram.py` | Telegram runtime adapter fake-mode turns, message dispatch, long-poll stub, token-absent fallback. |
| `tests/test_arclink_discord.py` | Discord runtime adapter fake-mode interactions, slash command dispatch, signature verification stub, token-absent fallback. |
| `tests/test_public_repo_hygiene.py` | Tracked and untracked text hygiene, binary skip behavior, provider-name context. |
| `web/tests/test_api_client.mjs` | API client module unit tests. |
| `web/tests/test_page_smoke.mjs` | Page route smoke tests. |

## Production Grade Steering Coverage (Production 1-16)

| Production item | Current state | Gap |
| --- | --- | --- |
| P1: Coherent versioned hosted API | Hosted API exists (1,078 lines), 39 route tests, health/provider-state/reconciliation/billing-portal/telegram/discord webhook routes, provider and executor boundaries hardened, OpenAPI 3.1 spec generated and served, rate-limit headers on limited routes | Remaining: WSGI 503 status text fix, route-table-vs-spec coverage test |
| P2: Auth/CSRF/audit on every mutating route | Admin mutation routes have CSRF/auth gates; negative tests exist | Need systematic negative-test sweep for all mutating routes |
| P3: Stripe boundary | Fake checkout/webhook/entitlement/drift exists | Billing portal link, refund/admin notes, failed payment state, reconciliation report |
| P4: Cloudflare boundary | Fake DNS client, drift events, hostname planning | Propagation checks, teardown, retry safety tests |
| P5: Docker Compose executor | Dry-run renderer, fail-closed executor, rollback planning | Start/stop/restart/inspect/teardown live-gated paths, resource limits, health checks |
| P6: Chutes provider flow | Catalog parser, fake key manager, default model | Owner key lifecycle, per-deployment key state, inference smoke, failure reporting |
| P7: Telegram/Discord onboarding parity | Shared state machine, runtime adapters with fake mode | Live HTTP transport, payload validation coverage |
| P8: User dashboard | Read model exists, Next.js view with mock data | Wire to hosted API, add all required panels |
| P9: Admin dashboard | Read model exists, Next.js view with mock data | Wire to hosted API, add operational panels, guarded actions |
| P10: Web UI product checks | Brand system applied, mobile overflow guards | Browser E2E smoke, empty/error/loading states, accessibility |
| P11: Fake E2E harness | Individual contract tests exist | Unified fake journey harness not yet built |
| P12: Live E2E harness | Not started | Blocked: live credentials |
| P13: Deployment assets | docs/arclink/live-e2e-secrets-needed.md exists | env example, ingress plan, backup notes, runbook, rollback steps |
| P14: Observability | Structured events, health snapshots, audit log | Alert candidates, queue/deployment status dashboard reads |
| P15: Data safety | Per-user isolation decision, secret guards in tests | Volume layout doc, backup plan, teardown safeguards, destructive confirmations |
| P16: Documentation truth | Docs exist but may overclaim | Audit all docs against live code, name every live blocker |

## Active Gaps

- The hosted API/auth boundary exists but is not yet deployed behind a
  production identity provider or reverse proxy.
- Next.js 15 + Tailwind 4 web app foundation exists but views use mock/static
  data; wiring to the hosted API is the next step.
- Telegram/Discord runtime adapters exist with fake-mode dispatch but live
  HTTP transport (polling/gateway) is not yet implemented.
- Live Docker, Stripe, Cloudflare, Chutes, Notion/OAuth, and hosted dashboard
  E2E are not implemented.
- Production browser E2E tests should be added now that the Next.js frontend
  exists.
- Unified fake E2E journey harness (Production 11) is not yet built.
- Deployment/operations assets (Production 13-15) are incomplete.

## Coverage Verdict

Coverage is sufficient for BUILD to continue. 147 ArcLink test functions across
17 test files (plus 4 hygiene and 2 web tests) cover the no-secret foundation. The controlling definition of done
is `research/RALPHIE_PRODUCTION_GRADE_STEERING.md` (Production 1-16). All 16
items are unchecked. No item requires live credentials to begin; 6 external
items are blocked on credentials for live proof only. BUILD should proceed
through Production 1-2 (API contract hardening), then 3-7 (provider
boundaries), then 8-10 (dashboards), then 11-16 (E2E, deploy, ops, docs).
