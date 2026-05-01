# Coverage Matrix

| Goal / Success Criterion | Existing Coverage | Plan Coverage | Remaining Gap / Risk | Validation |
| --- | --- | --- | --- | --- |
| Transform Almanac into ArcLink identity | `python/arclink_product.py`; ArcLink docs; additive `arclink_*` schema | Continue staged rename after backend/executor contracts | Cosmetic rename could break mature Almanac paths | Product config tests, public hygiene tests, docs review |
| `ARCLINK_*` / `ALMANAC_*` compatibility | Precedence and blank fallback tests | Maintain for every new env key | Future env additions could skip alias rules | Env precedence and conflict diagnostic tests |
| Preserve Hermes/qmd/memory | Existing runtime pins, qmd scripts, managed-context plugin, memory synth, tests | Provisioning renderer keeps these lanes in every deployment plan; executor must consume same plan | Renderer/executor drift could omit a maintenance lane | Existing plugin/qmd/memory tests plus render/executor assertions |
| Chutes-first inference | Chutes defaults, catalog parser, capability validation, fake key manager | Add catalog refresh and real key manager behind executor/E2E boundary | Live Chutes auth/key lifecycle unverified | Fixture catalog tests; live E2E when credentials exist |
| Stripe self-serve entitlement | Webhook verifier, entitlement handler, idempotent processed events, subscription mirror, gate advancement, invoice success mapping, unsupported event allowlist, atomic failure rollback, nested invoice parent compatibility, caller-transaction rejection, profile-only entitlement preservation | Keep explicit entitlement writers for webhooks and reasoned admin support actions; live checkout adapter later | Live Stripe delivery and hosted checkout callback behavior are unverified | Entitlement suite, live E2E later |
| Public onboarding | Durable web/Telegram/Discord sessions, active-session uniqueness, fake checkout, funnel events, channel handoff, no-secret metadata guard, returning-user entitlement preservation | Keep as shared contract for future website and public bots | Public bot/web delivery and hosted checkout redirects are not implemented | Onboarding tests plus live E2E later |
| Cloudflare DNS and subdomains | Fake Cloudflare client, desired DNS persistence, drift events, DNS type allowlist | Add live adapter through executor and E2E flag | Live token/zone unavailable | DNS drift tests, executor fake tests, live E2E later |
| Traefik ingress | Host planner and role label renderer with golden coverage | Provisioning renderer emits per-deployment labels/config; executor should materialize them | Runtime Traefik service/execution not yet live | Golden render tests, local Compose smoke later |
| Obscure deployment prefixes | Prefix reservation, generator, denylist, collision retry | Use generator in public onboarding/session creation | Prefix policy may need product tuning | Schema and prefix tests |
| Nextcloud/files | Existing Nextcloud plus dedicated-per-deployment ArcLink decision | Render isolated Nextcloud plus dedicated DB/Redis services | Dedicated instances increase resource use | Isolation decision test, render tests, access tests |
| code-server | Existing code-server scripts and access helpers | Route by host in provisioning renderer | Websocket/proxy behavior needs browser smoke later | Access tests, browser smoke later |
| SSH/TUI | Cloudflare Access TCP strategy guard | Implement tunnel/access records after provisioning executor contract | No live tunnel yet | Raw SSH-over-HTTP rejection tests, live E2E later |
| Website onboarding | Durable backend session contract exists; no web app yet | Add web API/frontend after executor and auth contracts are explicit | Empty dashboard risk if UI starts too early | Session/API contract tests, Playwright smoke when app exists |
| Telegram/Discord onboarding | Mature Almanac state machine/workers/tests plus ArcLink public session contract | Add public bot integration after live callback/identity contract | Public bot handoff must stay distinct from private agent bot | Conversation-state and session-contract regression tests |
| User dashboard | `python/arclink_dashboard.py` returns profile, entitlement, deployments, access URLs, billing, bot contact, model state, qmd/memory freshness, service health, and events | Build Next.js views on top of read model later | Browser app, session auth, and embedding/deep-link behavior missing | Dashboard read-model tests now; Playwright later |
| Admin dashboard | `python/arclink_dashboard.py` returns funnel, subscriptions, deployments, health, drift, jobs, audit, action intents, and failures | Build admin UI, RBAC, and executor-backed action workflows later | Sensitive actions need strict auth, reason, audit, and executor gating | Admin/dashboard tests now; RBAC/action endpoint tests later |
| Admin actions | Queued `arclink_action_intents` require reason/idempotency and reject plaintext secrets | Future executor consumes only queued audited intent | Executor could mutate without audit if boundary is bypassed | Admin action tests, future executor tests |
| Live executor boundary | `python/arclink_executor.py` defines explicit request/result dataclasses, default fail-closed live gating, fake resolver, file materialization contract, fake Docker/provider/edge/rollback behavior, digest/operation replay guards, DNS type validation, and Compose dependency validation | Add audited action-consumer loop and live adapters behind E2E gates | No real Docker/provider execution is enabled; live mutations remain E2E-only | Executor tests, compile checks, public hygiene |
| Health/fleet operations | Health scripts, health-watch, service health table | Provisioning records service snapshots and timeline; dashboard reads failures | Fleet observability stack deferred | Health tests, service-health render/snapshot tests |
| Per-tenant isolation | Docker user homes exist; ArcLink access decision pins dedicated Nextcloud | Dedicated state roots per deployment in provisioning | Backup/quota/resource policy not yet implemented | Render tests, isolation tests, rollback tests |
| No live secrets in unit tests | ArcLink tests use fakes/fixtures; public hygiene covers tracked and untracked text files | Continue fake clients for onboarding, billing, provisioning, ingress, dashboard, executor | Live SDK calls could leak into CI if not guarded | Public hygiene and no-secret tests |
| SQLite-first with Postgres path | `arclink_*` schema uses stable text ids and helper validation | Maintain schema portability | SQLite-only behavior can creep in | Idempotent migration tests, schema review |
| Honest E2E docs | `docs/arclink/live-e2e-secrets-needed.md` exists | Keep updated as live adapters land | Passing unit tests may be mistaken for live readiness | Documentation truth checks and E2E checklist |

## Current ArcLink Test Coverage

| Test file | Covered surface |
| --- | --- |
| `tests/test_arclink_product_config.py` | Product defaults, env precedence, blank fallback, legacy compatibility. |
| `tests/test_arclink_schema.py` | ArcLink tables, onboarding tables, prefix reservation/generation, audit/events, subscriptions, service health, provisioning helpers, drift checks. |
| `tests/test_arclink_chutes_and_adapters.py` | Chutes catalog validation, fake key references, fake Stripe sessions/webhooks, fake Cloudflare drift, Traefik labels. |
| `tests/test_arclink_entitlements.py` | Stripe signature rejection, paid gate lift, invoice success mapping, failed/received replay, failed-payment audit, unsupported signed-event allowlist, manual comp reason, atomic failure rollback, caller-owned transaction rejection, nested invoice compatibility, profile-only paid/comp preservation. |
| `tests/test_arclink_onboarding.py` | Public sessions, duplicate active-session prevention, fake checkout, cancelled/expired checkout, entitlement-gated provisioning readiness, channel handoff, secret rejection, returning-user entitlement preservation during prepare/resume. |
| `tests/test_arclink_ingress.py` | DNS persistence/drift and Traefik golden labels. |
| `tests/test_arclink_access.py` | Dedicated Nextcloud decision and SSH-over-HTTP rejection. |
| `tests/test_arclink_provisioning.py` | Dry-run service/DNS/access intent, entitlement visibility, no-secret validation, retry after secret repair, rollback planning. |
| `tests/test_arclink_admin_actions.py` | Reason-required queued actions, idempotency, audit rows, secret-safe metadata, no live side effects. |
| `tests/test_arclink_dashboard.py` | User dashboard summary and admin dashboard operational/failure projections. |
| `tests/test_arclink_executor.py` | Executor live-gate refusal, secret resolver contracts, fake apply result shape, digest mismatch rejection, fake provider/edge idempotency, and no secret-material leakage. |
| `tests/test_public_repo_hygiene.py` | Tracked and untracked text hygiene, binary PDF skip, provider-name context. |

## Active Coverage Gap

No active no-secret executor coverage gap remains for the completed
lint-risk and replay/dependency repair. Existing focused tests cover applied
Compose replay without secret rematerialization, zero fake failure limits,
rollback destructive-action rejection, DNS type rejection, operation-digest
replay checks, strict Chutes replay, and missing Compose dependency rejection.

Remaining coverage gaps are live/E2E only: real Docker Compose execution,
Cloudflare DNS/Tunnel/Access mutation, Chutes key lifecycle, Stripe live
actions, hosted dashboard/API action wiring, and public bot/website delivery.

## Coverage Verdict

Coverage is ready to progress from lint to document. Live provider execution,
host provisioning execution, and Next.js dashboard implementation still require
separate E2E-gated slices.
