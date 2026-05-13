# ArcLink Live E2E Secrets Needed

**Status:** The credentialed live run is externally blocked. No live E2E journey
has been proven. The live proof orchestration runner
(`python/arclink_live_runner.py`) composes host readiness, provider diagnostics,
journey model, and evidence ledger into a single dry-run or live proof pass.
Run `bin/arclink-live-proof` (dry-run by default) or
`bin/arclink-live-proof --live` when credentials are supplied. Use
`bin/arclink-live-proof --journey workspace` to plan the native Drive, Code, and
Terminal TLS proof without running it, or
`bin/arclink-live-proof --journey workspace --live` to run the gated Docker
upgrade, Docker health, and desktop/mobile browser proof steps against a real
HTTPS Hermes dashboard. Use
`bin/arclink-live-proof --journey external` to plan provider-specific proof
rows, or `bin/arclink-live-proof --journey external --live --json` only after
the operator explicitly authorizes the named provider rows and supplies the
required secret references or live credentials. The fake E2E harness
(`tests/test_arclink_e2e_fake.py`) passes without credentials. Provider live
checks in `tests/test_arclink_e2e_live.py` skip cleanly when credentials are
absent. The ordered journey model (`python/arclink_live_journey.py`) and
evidence ledger (`python/arclink_evidence.py`) are scaffolded and tested without
secrets.

## Local Setup For Live Proof

Install no-secret Python validation dependencies first:

```bash
python3 -m pip install -r requirements-dev.txt
```

When running Stripe live checks with `STRIPE_SECRET_KEY`, install Stripe's
Python package in the local environment:

```bash
python3 -m pip install stripe
```

Workspace browser proof is generated under `web/` and needs Node plus
Playwright:

```bash
cd web
npm ci
npx playwright install --with-deps chromium
cd ..
```

`bin/arclink-live-proof --journey workspace --live --json` should be run only
after those web dependencies are present and
`ARCLINK_WORKSPACE_PROOF_TLS_URL` plus `ARCLINK_WORKSPACE_PROOF_AUTH` are
supplied through environment.

## Journey Env Vars

| Var | Required For | Purpose |
|-----|-------------|---------|
| `ARCLINK_E2E_LIVE` | All steps | Master gate for live E2E |
| `STRIPE_SECRET_KEY` | Checkout, webhook | Stripe test-mode key (sk_test_*) |
| `STRIPE_WEBHOOK_SECRET` | Webhook delivery | Stripe webhook signature |
| `ARCLINK_INGRESS_MODE` | Ingress selection | `domain` or `tailscale` |
| `CLOUDFLARE_API_TOKEN_REF` or `CLOUDFLARE_API_TOKEN` | Domain ingress DNS health | Scoped zone DNS token; prefer `secret://` ref |
| `CLOUDFLARE_ZONE_ID` | Domain ingress DNS health | Target zone ID |
| `ARCLINK_TAILSCALE_DNS_NAME` | Tailscale ingress health | Control or worker node FQDN |
| `ARCLINK_E2E_DOCKER` | Docker check | Opt-in for Docker access |
| `CHUTES_API_KEY` | Key provisioning | Chutes owner key |
| `TELEGRAM_BOT_TOKEN` | Bot check | Telegram bot token |
| `DISCORD_BOT_TOKEN` | Bot check | Discord bot token |

## Workspace Plugin TLS Proof Env Vars

| Var | Required For | Purpose |
|-----|-------------|---------|
| `ARCLINK_E2E_LIVE` | All workspace proof steps | Master gate for live proof |
| `ARCLINK_E2E_DOCKER` | Docker upgrade/reconcile and health | Opt-in for Docker access |
| `ARCLINK_WORKSPACE_PROOF_TLS_URL` | Drive, Code, Terminal browser proof | HTTPS Hermes dashboard URL |
| `ARCLINK_WORKSPACE_PROOF_AUTH` | Drive, Code, Terminal browser proof | Session/auth material supplied outside tracked files |

`ARCLINK_WORKSPACE_PROOF_AUTH` is read only from the process environment. The
browser runner accepts `Cookie:NAME=VALUE`, `Bearer ...`, `bearer:TOKEN`, or a
raw bearer token. Values are passed to the browser process through environment
only and are not written to evidence.

Optional workspace proof timeouts:

| Var | Default | Purpose |
|-----|---------|---------|
| `ARCLINK_WORKSPACE_PROOF_DOCKER_TIMEOUT_SECONDS` | 2700 | Docker upgrade/reconcile timeout |
| `ARCLINK_WORKSPACE_PROOF_HEALTH_TIMEOUT_SECONDS` | 900 | Docker health timeout |
| `ARCLINK_WORKSPACE_PROOF_BROWSER_TIMEOUT_SECONDS` | 300 | Per desktop/mobile browser proof timeout |

## External Proof Env Vars

The external journey is opt-in per provider row. If no `ARCLINK_PROOF_*` flag
is set, dry-run planning reports all missing provider proof gates. If one or
more proof flags are set, ArcLink requires only the environment for those named
rows and skips unrelated provider rows.

| Var | Required For | Purpose |
|-----|-------------|---------|
| `ARCLINK_E2E_LIVE` | All external rows | Master gate for live external proof |
| `ARCLINK_PROOF_STRIPE` | Stripe checkout/webhook | Enables the Stripe proof row |
| `STRIPE_SECRET_KEY` | Stripe checkout/webhook | Stripe test-mode or authorized live key |
| `STRIPE_WEBHOOK_SECRET` | Stripe checkout/webhook | Stripe webhook signature secret |
| `ARCLINK_PROOF_TELEGRAM` | Telegram Raven delivery | Enables live Telegram delivery/button proof |
| `TELEGRAM_BOT_TOKEN` | Telegram Raven delivery | Public Raven bot token |
| `ARCLINK_PROOF_DISCORD` | Discord Raven delivery | Enables live Discord delivery/button proof |
| `DISCORD_BOT_TOKEN` | Discord Raven delivery | Public Raven bot token |
| `DISCORD_APP_ID` | Discord Raven delivery | Discord application id |
| `ARCLINK_PROOF_HERMES_DASHBOARD` | Hermes dashboard landing | Enables deployed dashboard landing proof |
| `ARCLINK_HERMES_DASHBOARD_URL` | Hermes dashboard landing | HTTPS Hermes dashboard URL |
| `ARCLINK_HERMES_DASHBOARD_AUTH` | Hermes dashboard landing | Session/auth material supplied outside tracked files |
| `ARCLINK_PROOF_CHUTES_OAUTH` | Chutes OAuth connect | Enables OAuth connect/callback proof |
| `ARCLINK_CHUTES_OAUTH_CLIENT_ID` | Chutes OAuth connect | Chutes OAuth client id |
| `ARCLINK_CHUTES_OAUTH_CLIENT_SECRET_REF` | Chutes OAuth connect | Secret reference for the Chutes OAuth client secret |
| `ARCLINK_CHUTES_OAUTH_REDIRECT_URI` | Chutes OAuth connect | HTTPS callback URI registered for ArcLink |
| `ARCLINK_PROOF_CHUTES_USAGE` | Chutes usage/billing | Enables personal usage, quota, discount, and billing read proof |
| `ARCLINK_CHUTES_CREDENTIAL_REF` | Chutes usage/key/transfer rows | Secret reference for the authorized Chutes credential |
| `ARCLINK_PROOF_CHUTES_KEY_CRUD` | Chutes API key CRUD | Enables key create/list/delete proof |
| `ARCLINK_CHUTES_ALLOW_MUTATION` | Chutes key/transfer rows | Explicit mutation authorization gate |
| `ARCLINK_PROOF_CHUTES_ACCOUNT_REGISTRATION` | Chutes account registration | Enables official registration-token/hotkey proof |
| `ARCLINK_CHUTES_REGISTRATION_TOKEN_REF` | Chutes account registration | Secret reference for the registration token |
| `ARCLINK_CHUTES_HOTKEY_REF` | Chutes account registration | Secret reference for the hotkey proof material |
| `ARCLINK_CHUTES_COLDKEY_PUBLIC` | Chutes account registration | Public coldkey identifier |
| `ARCLINK_PROOF_CHUTES_BALANCE_TRANSFER` | Chutes balance transfer | Enables direct provider balance-transfer proof |
| `ARCLINK_CHUTES_TRANSFER_RECIPIENT_USER_ID` | Chutes balance transfer | Recipient Chutes user id for the authorized transfer |
| `ARCLINK_CHUTES_TRANSFER_AMOUNT` | Chutes balance transfer | Authorized transfer amount |
| `ARCLINK_PROOF_NOTION_SSOT` | Notion shared-root SSOT | Enables shared-root readability and brokered write proof |
| `ARCLINK_SSOT_NOTION_ROOT_PAGE_ID` | Notion shared-root SSOT | Shared root page id |
| `ARCLINK_SSOT_NOTION_TOKEN` | Notion shared-root SSOT | Notion integration token supplied outside tracked files |
| `ARCLINK_PROOF_CLOUDFLARE` | Cloudflare ingress | Enables zone/DNS proof |
| `CLOUDFLARE_API_TOKEN_REF` or `CLOUDFLARE_API_TOKEN` | Cloudflare ingress | Scoped zone DNS token; prefer `secret://` ref |
| `CLOUDFLARE_ZONE_ID` | Cloudflare ingress | Target zone id |
| `ARCLINK_PROOF_TAILSCALE` | Tailscale ingress | Enables Serve/certificate proof |
| `ARCLINK_TAILSCALE_DNS_NAME` | Tailscale ingress | Tailnet DNS name to verify |

Chutes account registration and balance transfer are mutation-sensitive. Keep
them disabled unless the operator explicitly authorizes that exact proof row
with scratch or approved live accounts. Chutes account creation remains an
assisted/proof-gated flow; ArcLink must not use browser/TLS impersonation or
challenge-bypass tooling to obtain registration proof.

## Evidence

After a live run, the evidence ledger JSON can be saved using the template at
`docs/arclink/live-e2e-evidence-template.md`.

## Credential Details

Initial development can proceed without live secrets. Real end-to-end deployment testing will need:

- Domain mode: Cloudflare API token scoped to DNS edit/read for the test
  customer domain and the zone id if auto-discovery is not implemented yet.
- Tailscale mode: a logged-in Tailscale node, MagicDNS/HTTPS certificate
  readiness, and tailnet operator approval for any Serve/Funnel prompts.
- Hetzner API token or SSH access to the target server.
- Stripe secret key, webhook signing secret, product/price ids, and customer portal config.
- Chutes owner/admin API key or secret references capable of the authorized
  proof row: OAuth connect, personal usage reads, API-key CRUD, official
  registration-token/hotkey proof, or balance transfer.
- Telegram public onboarding bot token.
- Discord public onboarding bot token/application credentials.
- OpenAI Codex OAuth/device-flow configuration if live BYOK verification is required.
- Anthropic/Claude OAuth/PKCE configuration if live BYOK verification is required.
- Notion integration token and webhook verification secret if shared Notion remains enabled.
- For Sovereign customer Notion, a per-deployment Notion integration token,
  webhook secret/verification flow, and a live callback route for the selected
  deployment ingress mode.

Never paste these into tracked files. Provide them through local `.env`, secret manager, or an interactive deploy prompt.

The local foundation tests in `docs/arclink/foundation.md` use fake clients and
fixture catalog data. Passing them does not prove live Stripe, Cloudflare,
Tailscale, Chutes, Telegram, Discord, Notion, or host provisioning access.

The provisioning dry-run renderer records Docker, DNS, Traefik, state-root, and
access intent without live secrets. A live E2E still needs a deployment host
that can execute the rendered Compose plan, bind the resulting services through
Traefik, publish either Cloudflare domain-mode records or Tailscale-mode routes,
and verify the health placeholders against real containers.

The executor boundary can be tested without live secrets because mutating calls
fail closed by default and fake adapters consume rendered intent. A live E2E
must explicitly enable the executor, provide production Docker, Stripe, Chutes,
rollback, and selected ingress-mode adapters, and inject a secret resolver that
materializes only `secret://...` references to `/run/secrets/...` files.

Executor adapter credential checklist:

- Docker Compose apply: deployment host shell access, Docker context access,
  writable per-deployment state root, and a secret resolver that writes only
  `/run/secrets/*` files.
- Local starter fleet apply: an idempotent ArcLink fleet SSH key, a target
  Unix user such as `arclink`, the public key installed in that user's
  `authorized_keys`, Docker access for that user, a writable state root such as
  `/arcdata/deployments`, and a passing `ssh -i <fleet-key> arclink@localhost
  true` smoke test when localhost is registered as the first worker.
- Domain ingress apply: Cloudflare zone id or discoverable zone name plus a
  scoped API token that can read and edit DNS records for the test domain.
- Domain SSH apply: Cloudflare Access/Tunnel account id, tunnel credentials,
  Access policy configuration, and a scoped API token that can manage tunnels
  and Access applications for the test domain.
- Tailscale ingress apply: host Tailscale CLI access, logged-in node state,
  selected HTTPS port, selected Notion path, and tailnet approval for
  Serve/Funnel publication.
- Chutes key apply: owner/admin Chutes credential capable of creating,
  rotating, and revoking per-deployment API keys while storing returned key
  material only in the configured secret manager.
- Stripe action apply: Stripe secret key, customer/subscription ids, refund or
  portal configuration as appropriate, and signed webhook delivery for the
  resulting state transitions.
- Rollback apply: the same host/provider credentials used by the failed apply,
  with operator confirmation that customer vault, Nextcloud, memory, qmd, and
  workspace state roots are preserved.

The public onboarding contract can be tested without live secrets through fake
Stripe checkout sessions, durable `arclink_onboarding_*` rows, the local
`python/arclink_product_surface.py` web/API surface, and deterministic
Telegram/Discord bot conversation skeletons in `python/arclink_public_bots.py`,
and runtime adapters in `python/arclink_telegram.py` and
`python/arclink_discord.py` (fake mode when tokens are absent).
A live E2E still needs Stripe checkout session creation against real
product/price ids, signed checkout completion webhooks, hosted success/cancel
URLs, and real Telegram/Discord public onboarding bot clients. Public bot ids
and user/channel ids may be persisted as hints; private user-agent bot tokens
must stay in the secret manager or private deployment state.

Dashboard/admin contracts can be tested without live secrets through read-model
helpers, local product-surface pages, local JSON routes, and queued
`arclink_action_intents` rows. The hosted API boundary
(`python/arclink_hosted_api.py`) provides route dispatch, session/cookie
transport, CORS, request-ID propagation, and safe error shaping over these
contracts, but a live E2E still needs a production reverse proxy, TLS
termination, identity provider integration, RBAC policy enforcement, and
explicit action-to-executor wiring before restart, reprovision, DNS repair, key
rotation, refund, cancel, comp, or rollout controls can mutate real services or
providers.

Provisioning secret resolution is intentionally split by image support. Stock
images that support file-backed credentials, including Postgres and Nextcloud,
must receive Compose secret mounts through their documented `_FILE`
environment variables. Images or app commands without `_FILE` support, such as
custom ArcLink app tokens, require an
explicit resolver step that materializes the mounted secret file or a
`secret://` reference at container start. This keeps dry-run output secret-free
while avoiding plaintext environment values in executable Compose intent.
