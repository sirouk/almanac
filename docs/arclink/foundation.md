# ArcLink Foundation Notes

ArcLink foundation code is intentionally additive. Existing ArcLink deploy,
onboarding, Hermes, qmd, vault, memory, Notion, and service-health paths remain
under their current names while new SaaS-facing primitives use `ARCLINK_*`
configuration and `arclink_*` database tables.

Operational assumptions, ownership boundaries, and validation steps live in
`docs/arclink/foundation-runbook.md`.

## Config

New product configuration uses `python/arclink_product.py`.

- Non-empty `ARCLINK_*` values override legacy `ARCLINK_*` aliases.
- Blank `ARCLINK_*` values are ignored, so partially rendered env files do not
  erase working legacy config.
- Conflict diagnostics name only the variables involved and do not print the
  values, because future values may include sensitive domains or secret refs.

The default provider is Chutes, with:

```text
ARCLINK_PRIMARY_PROVIDER=chutes
ARCLINK_CHUTES_BASE_URL=https://llm.chutes.ai/v1
ARCLINK_CHUTES_DEFAULT_MODEL=moonshotai/Kimi-K2.6-TEE
ARCLINK_MODEL_REASONING_DEFAULT=medium
```

## Schema

ArcLink commercial and SaaS records are separate from existing ArcLink
operational rows. Links to existing operational state are stored as stable text
ids such as `agent_id`, `session_id`, and `bootstrap_request_id`; helper drift
checks report missing linked rows instead of hiding divergence behind hard
foreign-key failures.

The first schema slice is SQLite-compatible and keeps JSON as validated text so
the same contracts can migrate to Postgres later.

User profile upserts and entitlement writes are separate on purpose.
`upsert_arclink_user()` treats omitted `entitlement_state` as "do not mutate
entitlement" for existing rows, while new rows still default to `none`.
Entitlement changes should use `set_arclink_user_entitlement()`, signed Stripe
webhook processing, or reasoned admin comp helpers. This prevents public
onboarding resume or profile-only updates from clearing a returning paid or
comped customer.

## Chutes Auth Caveat

The catalog client supports direct `X-API-Key` and bearer headers for tests and
future live validation. ArcLink should not claim live inference or live
per-deployment key lifecycle support until the production Chutes account path
confirms the correct auth header and owner key-management API.

The current Chutes key manager is a fake no-secret adapter. It returns secret
references such as `secret://arclink/chutes/<deployment_id>`, not plaintext
keys.

## Access Isolation

ArcLink MVP isolation model:
`ARCLINK_NEXTCLOUD_ISOLATION_MODEL=dedicated_per_deployment`.

Provisioning work must plan a dedicated Nextcloud instance and data volume for
each deployment. A shared Nextcloud instance remains a future optimization only
if access-isolation tests prove it is simpler and at least as safe.

ArcLink SSH access strategy:
`ARCLINK_SSH_ACCESS_STRATEGY=cloudflare_access_tcp`.

The SaaS surface may advertise Cloudflare Access TCP SSH hints after the tunnel
exists. It must not advertise raw SSH over HTTP or path-prefix HTTP routing as
an SSH transport.

## Provisioning Dry Runs

`python/arclink_provisioning.py` renders the first no-secret ArcLink
provisioning contract. It does not start containers. It turns a deployment row
into Compose, DNS, Traefik, state-root, service-health placeholder, and access
intent so dashboard/admin code and the guarded executor boundary can build
against stable records before production host execution is wired in.

The renderer deliberately keeps Docker Compose as the MVP substrate instead of
introducing a second scheduler. That preserves the current Hermes, qmd, vault
watch, memory synthesis, Nextcloud, code-server, health, notification, bot
gateway, and managed-context rails while making per-deployment intent explicit.

Dry-run output uses dedicated per-deployment host roots derived from deployment
id and prefix. Service environment values use container-internal mount targets
for `HERMES_HOME`, `VAULT_DIR`, qmd state, and memory state; host paths remain
under `state_roots` and service volume sources.

Nextcloud dry-run intent uses a dedicated app container plus dedicated
`nextcloud-db` and `nextcloud-redis` services for each deployment. This keeps
the MVP isolation contract explicit in Compose and avoids depending on a shared
database or cache before cross-tenant isolation is proven.

Chutes, Stripe, Cloudflare, bot, Notion, code-server, and Nextcloud
credentials are represented only by `secret://...` references. The provisioning
validator rejects plaintext-looking secret values in rendered output and marks
the provisioning job failed so the same idempotency key can be resumed after
the metadata is repaired. This keeps Docker dry-run output safe to persist for
admin and dashboard inspection.

Secret runtime resolution prefers native file-based image contracts where they
exist. Postgres and Nextcloud receive Compose secrets through their documented
`*_FILE` environment variables. Images and app commands without compatible file
env support, such as code-server's password and ArcLink app provider tokens,
stay behind explicit resolver metadata until live execution installs a wrapper
or secret materialization step. This keeps the dry-run contract executable for
stock images without leaking plaintext into persisted Compose intent.

Entitlement-gated deployments may still render dry-run intent for admin
visibility, but `execution.ready` stays false and no
`provisioning_ready_for_execution` event is recorded until paid or comped.
Manual comps require an audit reason. A user-level comp lifts every blocked
deployment for that user; a deployment-targeted comp lifts only that deployment
and leaves the user's global entitlement unchanged.

Stripe webhook rows are idempotent after `processed`. Rows left in `failed` or
`received` may be replayed explicitly with the same Stripe event id after the
payload or handler issue is corrected. Webhook processing owns its database
transaction and rejects caller-owned active transactions so a failed handler
cannot partially commit entitlement, subscription, audit, or deployment state.
Signed unsupported Stripe events are recorded as processed but do not mutate
entitlements.

Rollback support is currently split between planning and a guarded executor
contract. A failed execution job can produce an idempotent rollback plan that
stops rendered services, removes unhealthy containers, preserves state roots,
and leaves secret references for manual review. Executing that plan still
requires the explicit live/E2E executor gate and production adapter wiring.

## Executor Boundary

`python/arclink_executor.py` defines the current mutating boundary for Docker
Compose, Cloudflare DNS, Cloudflare Access, Chutes key lifecycle, Stripe
actions, and rollback application. The default executor is disabled:
mutating methods raise unless `ArcLinkExecutorConfig.live_enabled` is set.

The executor consumes rendered intent and returns secret-free result objects.
Compose secrets must use `secret://...` references and materialize only to
`/run/secrets/...` targets through an injected resolver. Fake test resolvers can
prove the contract without exposing plaintext secret values in returned data.

Fake executor replays are intentionally strict. Docker Compose idempotency keys
are bound to the rendered intent digest, while Cloudflare DNS, Cloudflare
Access, Chutes key lifecycle, and rollback idempotency keys are bound to stable
operation digests derived from their request inputs. Reusing a key with changed
records, access plans, Chutes actions, Chutes secret refs, rollback plans, or
Compose intent raises before returning a stored result.

The fake Compose path also validates the dependency graph before apply. Services
may use list-style or object-style `depends_on`, but every dependency must refer
to a service in the rendered intent. This keeps dry-run executor behavior close
to the dependency validation real Docker Compose would perform.

This is not a production live execution implementation yet. The shipped
boundary verifies the fail-closed behavior, idempotency metadata, secret
materialization rules, Compose dependency validation, DNS record type allowlist,
Cloudflare Access TCP guard, supported Chutes actions, supported Stripe actions,
and rollback state-root preservation requirement. Real Docker, Cloudflare,
Chutes, Stripe, and rollback adapters remain E2E work.

## Public Onboarding Contract

`python/arclink_onboarding.py` defines the current no-secret contract shared by
future website, Telegram, and Discord entrypoints. It stores durable public
onboarding sessions in `arclink_onboarding_sessions` and funnel events in
`arclink_onboarding_events`.

The session contract tracks channel, channel identity hint, current step,
status, customer identity hints, selected plan/model, linked ArcLink user and
deployment ids, checkout state, and Stripe checkout ids/URLs. It deliberately
does not store private user-agent bot tokens, model provider keys, webhook
secrets, or raw API credentials. Telegram and Discord ids are public channel
hints only.

Only one active session may exist for a channel identity. Re-entering from web,
Telegram, or Discord resumes the active row. Cancelled, expired, failed, or
completed rows are terminal and allow a later fresh session.

Preparing or resuming a public onboarding deployment may update profile hints
and deployment linkage, but it must not pass an implicit entitlement reset. A
returning paid or comped user remains entitled until an explicit entitlement
writer changes that state.

Checkout creation uses a fake Stripe adapter for unit tests. Fake checkout
session ids and URLs are deterministic from the onboarding idempotency key and
require no live Stripe secret. A successful Stripe checkout webhook still has
to pass through the existing signed entitlement processor; only after that gate
lifts the linked deployment does the onboarding session move to
`provisioning_ready`. Cancelled and expired checkout helpers leave the
deployment blocked at `entitlement_required` and record funnel events.

## Product Surface, Dashboard, And Admin Contracts

`python/arclink_product_surface.py` serves the current local no-secret ArcLink
product surface. It is a small stdlib WSGI app for development and contract
testing, not the production web stack. A developer can run it without provider
secrets:

```bash
python3 python/arclink_product_surface.py
```

The first screen is the usable onboarding workflow. It can start or resume a
web onboarding session, collect customer hints, open deterministic fake Stripe
checkout, and show the linked entitlement/provisioning state. The same module
also exposes JSON read routes for local API tests.

The local UI follows the ArcLink brand boundary from
`docs/arclink/brand-system.md`: jet/carbon surfaces, signal-orange primary
actions, restrained status colors, and dense operational layouts. The
rationale for this Python-rendered prototype is to keep the API/read-model
boundary clean while avoiding a premature frontend framework before auth, RBAC,
and production routing are designed.

`python/arclink_dashboard.py` defines the API-first dashboard contract consumed
by the local surface. `python/arclink_api_auth.py` wraps those read models with
hashed user/admin sessions, CSRF checks, explicit header/cookie credential
extraction, rate-limit hooks, MFA-ready admin gates, and safe error shapes.

`python/arclink_hosted_api.py` wraps the existing ArcLink helper contracts into
a production-oriented WSGI application with route dispatch under `/api/v1`,
cookie/header session transport, CORS, request-ID propagation, structured
logging, safe error shaping, and Stripe webhook skip for no-secret environments.
`HostedApiConfig` resolves runtime settings from `ARCLINK_BASE_DOMAIN`,
`ARCLINK_CORS_ORIGIN`, `ARCLINK_COOKIE_DOMAIN`, `ARCLINK_COOKIE_SECURE`,
`STRIPE_WEBHOOK_SECRET`, `ARCLINK_LOG_LEVEL`, and `ARCLINK_DEFAULT_PRICE_ID`.
The hosted API is the intended production boundary; the local product surface
remains a no-secret prototype.

User dashboard reads summarize ArcLink-owned rows for a customer: profile,
entitlement, deployments, access URLs, subscription mirror state, onboarding bot
contact status, selected model hints, qmd and memory freshness placeholders,
service health, and recent deployment events. Raw metadata columns and provider
secrets are intentionally not exposed.

Admin dashboard reads summarize operational state for support and runbook use:
onboarding funnel counts, subscription mirrors, deployments, service health,
DNS drift events, provisioning jobs, queued action intents, audit rows, and
recent failures. Filters are SQLite-compatible and limited to channel, status,
deployment id, user id, and a lower-bound timestamp.

Admin actions are queued intent, not live side effects. Supported action types
include restart, reprovision, suspend/unsuspend, force resynthesis, bot or
Chutes key rotation, DNS repair, refund/comp/cancel, and rollout. Each request
must include an admin id, target, reason, and idempotency key; the helper writes
an audit row and stores safe metadata only. Plaintext-looking secret material is
rejected before the action intent is persisted.

`python/arclink_public_bots.py` defines Telegram and Discord public onboarding
bot adapter skeletons. They share the same onboarding session rows and fake
checkout semantics as the website surface. They intentionally store public
channel identity only and reject private bot-token-shaped or provider-token
material in metadata. They do not run live Telegram or Discord clients yet.

## Telegram And Discord Runtime Adapters

`python/arclink_telegram.py` provides a long-polling bot runner that connects
Telegram messages to the shared public bot turn handler from
`arclink_public_bots.py`. It requires `TELEGRAM_BOT_TOKEN` to start live
polling. When the token is absent, it operates in fake mode with no network
calls, allowing unit tests to exercise message dispatch and turn logic without
live credentials.

`python/arclink_discord.py` provides an interaction handler for Discord slash
commands and messages, also connecting to the shared public bot turn handler.
It requires `DISCORD_BOT_TOKEN` to start. When the token is absent, it
operates in fake mode. Discord signature verification is stubbed for unit
tests.

Both adapters share the same `arclink_onboarding_sessions` rows and onboarding
contract as the website surface. They do not duplicate billing, entitlement, or
provisioning logic. Private user-agent bot tokens remain outside these public
onboarding adapters.

## Local Checks

No live secrets are required for these foundation checks:

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
python3 tests/test_public_repo_hygiene.py
python3 -m py_compile python/arclink_control.py python/arclink_*.py
bash -n deploy.sh bin/*.sh test.sh
git diff --check
```
