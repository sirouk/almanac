# ArcLink Live E2E Secrets Needed

**Status:** The credentialed live run is externally blocked. No live E2E journey
has been proven. The fake E2E harness (`tests/test_arclink_e2e_fake.py`) passes
without credentials. Provider live checks in `tests/test_arclink_e2e_live.py`
skip cleanly when credentials are absent, while no-secret journey/evidence tests
still run. The ordered journey model
(`python/arclink_live_journey.py`) and evidence ledger
(`python/arclink_evidence.py`) are scaffolded and tested without secrets.

## Journey Env Vars

| Var | Required For | Purpose |
|-----|-------------|---------|
| `ARCLINK_E2E_LIVE` | All steps | Master gate for live E2E |
| `STRIPE_SECRET_KEY` | Checkout, webhook | Stripe test-mode key (sk_test_*) |
| `STRIPE_WEBHOOK_SECRET` | Webhook delivery | Stripe webhook signature |
| `CLOUDFLARE_API_TOKEN` | DNS health | Scoped zone DNS token |
| `CLOUDFLARE_ZONE_ID` | DNS health | Target zone ID |
| `ARCLINK_E2E_DOCKER` | Docker check | Opt-in for Docker access |
| `CHUTES_API_KEY` | Key provisioning | Chutes owner key |
| `TELEGRAM_BOT_TOKEN` | Bot check | Telegram bot token |
| `DISCORD_BOT_TOKEN` | Bot check | Discord bot token |

## Evidence

After a live run, the evidence ledger JSON can be saved using the template at
`docs/arclink/live-e2e-evidence-template.md`.

## Credential Details

Initial development can proceed without live secrets. Real end-to-end deployment testing will need:

- Cloudflare API token scoped to DNS edit/read for the test customer domain and
  the zone id if auto-discovery is not implemented yet.
- Hetzner API token or SSH access to the target server.
- Stripe secret key, webhook signing secret, product/price ids, and customer portal config.
- Chutes owner/admin API key or account credentials capable of creating/revoking per-deployment API keys.
- Telegram public onboarding bot token.
- Discord public onboarding bot token/application credentials.
- OpenAI Codex OAuth/device-flow configuration if live BYOK verification is required.
- Anthropic/Claude OAuth/PKCE configuration if live BYOK verification is required.
- Notion integration token and webhook verification secret if shared Notion remains enabled.

Never paste these into tracked files. Provide them through local `.env`, secret manager, or an interactive deploy prompt.

The local foundation tests in `docs/arclink/foundation.md` use fake clients and
fixture catalog data. Passing them does not prove live Stripe, Cloudflare,
Chutes, Telegram, Discord, Notion, or host provisioning access.

The provisioning dry-run renderer records Docker, DNS, Traefik, state-root, and
access intent without live secrets. A live E2E still needs a deployment host
that can execute the rendered Compose plan, bind the resulting services through
Traefik, create Cloudflare DNS/tunnel records, and verify the health placeholders
against real containers.

The executor boundary can be tested without live secrets because mutating calls
fail closed by default and fake adapters consume rendered intent. A live E2E
must explicitly enable the executor, provide production Docker/Cloudflare/
Chutes/Stripe/rollback adapters, and inject a secret resolver that materializes
only `secret://...` references to `/run/secrets/...` files.

Executor adapter credential checklist:

- Docker Compose apply: deployment host shell access, Docker context access,
  writable per-deployment state root, and a secret resolver that writes only
  `/run/secrets/*` files.
- Cloudflare DNS apply: zone id or discoverable zone name plus a scoped API
  token that can read and edit DNS records for the test domain.
- Cloudflare Access/Tunnel apply: account id, tunnel credentials, Access policy
  configuration, and a scoped API token that can manage tunnels and Access
  applications for the test domain.
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
code-server password injection and custom ArcLink app tokens, require an
explicit resolver step that materializes the mounted secret file or a
`secret://` reference at container start. This keeps dry-run output secret-free
while avoiding plaintext environment values in executable Compose intent.
