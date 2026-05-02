# Coverage Matrix

| Goal / success criterion | Existing coverage | Plan coverage | Remaining gap / risk | Validation |
| --- | --- | --- | --- | --- |
| Transform Almanac into ArcLink identity | `python/arclink_product.py`, ArcLink docs, additive `arclink_*` tables | Continue staged identity work after contracts settle | Broad rename could break mature Almanac paths | Product config tests, docs review, public hygiene |
| Preserve legacy compatibility | Env alias behavior and existing deploy paths | Keep `ALMANAC_*` compatibility where needed | Future env additions could skip alias rules | Product config and deploy regression tests |
| Preserve Hermes/qmd/memory | Runtime pins, qmd scripts, managed-context plugin, memory synth, tests | Provisioning intent keeps these lanes in every deployment plan | Renderer/executor drift could omit a lane | qmd/plugin/memory tests plus provisioning/executor assertions |
| Chutes-first inference | Chutes defaults, catalog parser, fake key manager | Catalog refresh and live key manager behind E2E gate | Live key lifecycle unverified | Chutes tests now; live E2E later |
| Stripe entitlement gate | Webhook verifier, entitlement handler, subscription mirror, gate advancement, billing portal, reconciliation | Landed (P3). Live checkout/webhook delivery deferred to P12. | Live credentials needed for E2E | Entitlement and onboarding tests; live E2E later |
| Public onboarding | Durable web/Telegram/Discord sessions, fake checkout, funnel events, shared state machine | Landed (P7). Website and public bot adapters share one contract. | Live HTTP transport for bots absent | Onboarding, product surface, public bot, adapter tests |
| Cloudflare DNS/subdomains | Fake Cloudflare client, desired DNS persistence, drift events, DNS allowlist | Landed (P4). Live adapter through E2E flag. | Token/zone unavailable for unit tests | Ingress/executor tests; live E2E later |
| Traefik ingress | Host planner and role label renderer with golden coverage | Render per-service host routing for deployments | Runtime Traefik smoke not live | Golden fixture, provisioning tests, later Compose smoke |
| Obscure deployment prefixes | Prefix reservation, generator, denylist, collision retry | Use in onboarding/provisioning | Product policy may change | Schema and onboarding tests |
| Nextcloud/files | Existing Nextcloud and dedicated isolation decision | Render isolated Nextcloud plus DB/Redis services | Resource cost may grow | Access and provisioning tests |
| code-server | Existing code-server scripts/access helpers | Route by host in provisioning intent | Proxy/websocket smoke deferred | Access tests; browser smoke later |
| SSH/TUI | Cloudflare Access TCP strategy guard | Implement tunnel/access records later | No live tunnel yet | Raw SSH-over-HTTP rejection tests |
| Website surface | Next.js 15 + Tailwind 4 web app with landing, login, onboarding, user/admin dashboard views (~1,593 lines) | Landed (P8-10). Brand system applied, browser proof passing. | API wiring uses mock data until live deployment | Web app build/test, browser E2E |
| Public Telegram/Discord bots | Shared state machine, runtime adapters with fake-mode fallback | Landed (P7). Live HTTP transport when tokens present. | Live bot tokens absent | Adapter tests (11 tests); live bot E2E later |
| User dashboard | Dashboard read model, Next.js user dashboard page | Landed (P8). Wire to hosted API for live data. | Views use mock data | Dashboard/product surface tests, web app build |
| Admin dashboard | Admin read model, Next.js admin page wired to all hosted API admin endpoints (18 tabs, queue-action, revoke-session forms) | LANDED (P9). | Complete for no-secret foundation | Admin/dashboard/executor tests, web app build |
| Docker Compose executor | Render, validate, start/stop/restart/inspect/teardown with resource limits, health checks, volume isolation | Landed (P5). Live execution behind operator flag. | No real Docker mutation enabled | Executor tests; live E2E later |
| API/auth boundary | Hosted WSGI API (1,078 lines), sessions, CSRF, rate limits, OpenAPI, 39 route tests | Landed (P1-2). Extend as dashboard integration requires. | Not yet deployed behind production identity provider | API/auth tests, hosted API tests |
| Live executor boundary | Fail-closed executor types, fake resolver/adapters, replay guards | Landed (P5-6). Add live adapters behind E2E gates. | No real Docker/provider mutation enabled | Executor tests; live E2E later |
| Health/fleet operations | Health scripts, health-watch, service health table | Dashboard reads service snapshots and failures | Fleet observability stack deferred | Health and dashboard tests |
| Per-tenant isolation | Docker user homes and dedicated Nextcloud decision | Dedicated state roots in provisioning plan | Quota/backup/resource policy not complete | Access/provisioning/rollback tests |
| No live secrets in unit tests | Fakes/fixtures and hygiene tests | Keep all live paths opt-in | SDK calls could leak into CI if unguarded | Public hygiene and no-secret suites |
| SQLite-first with Postgres path | Stable text IDs and helper validation | Keep schema portable | SQLite-specific assumptions can creep in | Schema tests and migration review |
| Honest E2E docs | `docs/arclink/live-e2e-secrets-needed.md` | Update as live adapters land | Unit success could be mistaken for live readiness | Documentation truth checks |
| Host readiness tooling (Gap A) | LANDED. `arclink_host_readiness.py` (213 lines), 14 tests | Executable checks for Docker, Docker Compose subcommand, ports, state root, env, secrets, ingress, CLI | No-secret readiness complete | Host readiness tests |
| Live readiness diagnostics (Gap C) | LANDED. `arclink_diagnostics.py` (140 lines), 11 tests | Secret-safe diagnostics for Stripe, Cloudflare, Chutes, Telegram, Discord, Docker, CLI | No-secret diagnostics complete; live connectivity deferred | Redaction and missing-credential tests |
| Live-gated Docker executor (Gap B) | LANDED. Injectable DockerRunner, FakeDockerRunner, DryRunStep, 20 tests | Live flags, state root, secret resolver required; rollback safeguards | No-secret runner boundary complete; real Docker mutation deferred | Executor live-gate tests |
| Full live E2E expansion (Gap D) | Scaffold skips cleanly without credentials | Expand to full signup-to-agent journey when credentials present | Remains skipped until credentials exist | Live E2E harness with credential gates |

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
| `tests/test_arclink_executor.py` | Live-gate refusal, secret resolver contracts, injectable DockerRunner, FakeDockerRunner, DryRunStep planning, fake apply result shape, digest mismatch rejection, provider idempotency, secret-material guards, Compose dependency validation. |
| `tests/test_arclink_diagnostics.py` | Stripe/Cloudflare/Chutes/Telegram/Discord/Docker credential presence checks, secret value redaction, machine-readable output, no-op without live flag. |
| `tests/test_arclink_host_readiness.py` | Docker/Compose binary detection, state root existence/writability, env var presence, secret env redaction, ingress strategy detection, machine-readable output, readiness failure without Docker. |
| `tests/test_arclink_product_surface.py` | Local WSGI first screen, fake checkout flow, user/admin dashboard rendering, queued admin actions, no DNS mutation, mobile overflow guards, favicon route. |
| `tests/test_arclink_public_bots.py` | Telegram/Discord public bot conversation-state contract, fake checkout, unsupported channel rejection, metadata secret rejection. |
| `tests/test_arclink_telegram.py` | Telegram runtime adapter fake-mode turns, message dispatch, long-poll stub, token-absent fallback. |
| `tests/test_arclink_discord.py` | Discord runtime adapter fake-mode interactions, slash command dispatch, signature verification stub, token-absent fallback. |
| `tests/test_arclink_hosted_api.py` | Hosted API route dispatch (39 tests), session auth, CSRF, safe errors, request-ID, CORS, webhooks, health, provider state, reconciliation, billing portal. |
| `tests/test_arclink_e2e_fake.py` | Full fake journey: signup, onboarding, checkout, webhook, entitlement, provisioning, health, dashboard, audit, admin actions. |
| `tests/test_arclink_e2e_live.py` | Secret-gated live E2E scaffold: Stripe, Cloudflare, Chutes, Telegram, Discord, Docker checks (skips without credentials). |
| `tests/test_public_repo_hygiene.py` | Tracked and untracked text hygiene, binary skip behavior, provider-name context. |
| `web/tests/test_api_client.mjs` | API client module unit tests. |
| `web/tests/test_page_smoke.mjs` | Page route smoke tests. |

## Production Grade Steering Coverage (Production 1-16)

| Production item | Current state | Gap |
| --- | --- | --- |
| P1: Coherent versioned hosted API | LANDED. Hosted API (1,078 lines), 39 route tests, OpenAPI 3.1, rate-limit headers. | Complete. |
| P2: Auth/CSRF/audit on every mutating route | LANDED. CSRF/auth gates, negative tests. | Complete. |
| P3: Stripe boundary | LANDED. Fake checkout/webhook/entitlement/drift, billing portal, reconciliation. | Live proof deferred to P12. |
| P4: Cloudflare boundary | LANDED. Fake DNS client, drift, hostname planning, propagation, teardown. | Live proof deferred to P12. |
| P5: Docker Compose executor | LANDED. Render, validate, start/stop/restart/inspect/teardown, resource limits, health checks. | Live execution deferred to P12. |
| P6: Chutes provider flow | LANDED. Owner key lifecycle, per-deployment key state, model catalog, inference smoke. | Live proof deferred to P12. |
| P7: Telegram/Discord onboarding parity | LANDED. Shared state machine, runtime adapters, fake mode, payload validation. | Live HTTP transport deferred. |
| P8: User dashboard | LANDED. Responsive layout, mock data panels. | Wire to hosted API for live data. |
| P9: Admin dashboard | LANDED. 18-tab admin page wired to hosted API. Queue-action and revoke-session forms with CSRF. | Complete. |
| P10: Web UI product checks | LANDED. Playwright suite (41 tests), brand system, mobile/desktop viewports, accessible forms, loading/empty/error states, fake-adapter labeling. | Complete. |
| P11: Fake E2E harness | LANDED. 6 tests covering full journey. | Complete. |
| P12: Live E2E harness | SCAFFOLDED. Secret-gated, skips cleanly without credentials. | Externally blocked: all live credentials and a deliberate credentialed run. |
| P13: Deployment assets | LANDED. env.example, secret-checklist, ingress-plan, backup-restore, operations-runbook. | Complete. |
| P14: Observability | LANDED. Structured events, alert-candidates doc, admin dashboard surfaces. | Complete. |
| P15: Data safety | LANDED. data-safety doc, teardown safeguards, secret rejection, hygiene scan. | Complete. |
| P16: Documentation truth | LANDED. All docs audited, live-e2e-secrets-needed updated, no overclaims. | Complete. |

## Final Form Gaps (from steering)

| Gap | Description | Status | Blocker |
| --- | --- | --- | --- |
| Gap A | Executable host bootstrap/check script | LANDED. `arclink_host_readiness.py` (213 lines), 14 tests. | No-secret readiness complete. |
| Gap B | Live-gated Docker executor deepening | LANDED. Injectable DockerRunner, FakeDockerRunner, DryRunStep. 20 tests. | Real Docker mutation still requires credentials and deliberate live flag. |
| Gap C | Live-readiness diagnostics for all providers | LANDED. `arclink_diagnostics.py` (140 lines), 11 tests. | Live connectivity still deferred. |
| Gap D | Full live E2E journey expansion | Not started | External credentials |
| Gap E | Real deployment evidence recording | Not started | External credentials |

## Coverage Verdict

Coverage is sufficient for the no-secret foundation. 190 ArcLink Python test functions
across 21 test files (plus 4 hygiene, 2 web tests, and 41 browser product checks)
cover P1-11, P13-P16, and Gaps A-C. P12 remains externally blocked.

Gaps A-C are landed. Gaps D-E remain externally blocked until credentials
are supplied.
