# Ralphie Steering: ArcLink Final Form Gap Closure

Use this as the first backlog source after the hosted API boundary slice. The
previous `done` means the hosted API checkpoint passed; it does not mean
ArcLink is in final product form.

## Final Form Definition

ArcLink is final only when a real user can:

1. Open the ArcLink website on the production domain.
2. Start onboarding from the website, Telegram, or Discord.
3. Complete Stripe checkout in test/live mode as configured.
4. Trigger a guarded provisioning job.
5. Receive a unique ArcLink deployment hostname.
6. Open the user dashboard, files, code editor, Hermes surface, bot setup, and
   health views from that deployment.
7. Talk to a working private agent backed by Hermes, qmd, vault/memory stubs,
   Chutes default inference, and the selected BYOK/provider options.
8. Let an owner/admin see the full global operations dashboard and execute
   audited operational actions.

Until that journey passes real E2E with recorded evidence, do not call ArcLink
complete.

## Mandatory Local Completion Checklist

Ralphie must treat this checklist as the terminal guard. Do not route to `done`
while any non-external item remains unchecked. Mark an item `[x]` only in the
same commit that implements the item and records its acceptance evidence.

- [ ] Gap 1A: Add dedicated web test coverage for the Next.js app, including
  API client tests and smoke coverage for `/`, `/onboarding`, `/dashboard`, and
  `/admin`.
- [ ] Gap 1B: Add browser/mobile verification for the web app and record the
  evidence without claiming live provisioning.
- [ ] Gap 2A: Wire the website onboarding workflow to the hosted API contract
  with fake checkout handoff and regression coverage.
- [ ] Gap 2B: Prove web/Telegram/Discord onboarding parity through shared
  fixtures and no-secret tests.
- [ ] Gap 3A: Add Telegram runtime adapter skeleton with fake tests and
  explicit env-gated live startup.
- [ ] Gap 3B: Add Discord runtime adapter skeleton with fake tests and
  explicit env-gated live startup.
- [ ] Gap 4A: Complete Stripe fake/live adapter boundary for checkout,
  webhook replay, entitlement transition, portal link, and reconciliation
  drift tests.
- [ ] Gap 5A: Complete Cloudflare fake/live adapter boundary for hostname
  creation, verification, repair, removal, and DNS drift reporting.
- [ ] Gap 6A: Complete Docker Compose executor boundary for render, live-gated
  apply, health, rollback, idempotent resume, and teardown.
- [ ] Gap 7A: Complete Chutes default provider/key lifecycle boundary with
  fake tests, live-gated inference proof path, and secret-reference-only
  outputs.
- [ ] Gap 8A: Add deploy/runbook assets for the Hetzner or `s1396` full-stack
  control-plane deployment behind the production domain.
- [ ] Gap 9A: Add an E2E harness that can run the full signup-to-agent journey
  in fake mode and switches to live mode only when credentials are present.
- [ ] Gap 10A: Expand the admin dashboard/control plane to cover payments,
  infrastructure, bots, security/abuse, releases, maintenance, logs, audit,
  and queued live-gated controls.
- [ ] Gap 10B: Ensure every admin mutation remains guarded by auth, CSRF, role,
  reason, idempotency, and append-only audit tests.

## External Live E2E Checklist

These items require real accounts or credentials. Keep them visible, but do not
block no-secret commits on them. When credentials become available, remove the
`[external]` tag for the relevant item and complete it with real E2E evidence.

- [ ] [external] Live Stripe checkout/webhook/customer/subscription/portal E2E.
- [ ] [external] Live Cloudflare hostname/Tunnel/Access E2E.
- [ ] [external] Live Docker provisioning on the selected Hetzner or `s1396`
  node.
- [ ] [external] Live Chutes inference and per-deployment key lifecycle E2E.
- [ ] [external] Live Telegram onboarding bot E2E.
- [ ] [external] Live Discord onboarding bot E2E.
- [ ] [external] Live full signup-to-agent journey with dashboard, Hermes,
  qmd retrieval, memory synth, Nextcloud/files, and code-server access.

## Gap 1: Production Next.js/Tailwind App

Build the production web app that consumes `python/arclink_hosted_api.py`.

Required:

- Next.js 15 + Tailwind unless a smaller repo-fit is justified in the plan.
- First screen is the usable ArcLink onboarding workflow, not a marketing-only
  landing page.
- Brand kit from `docs/arclink/brand-system.md`: jet black/carbon, soft white,
  signal orange, blue/green for state only, no generic purple AI gloss.
- Responsive public onboarding, user dashboard, and admin dashboard.
- No horizontal overflow at narrow mobile widths.
- Browser evidence for desktop and mobile.

Acceptance:

- Local dev server runs.
- Build/test commands are documented and pass.
- Browser checks cover public onboarding, user dashboard, and admin overview.
- UI never claims live provisioning when fake adapters are active.

## Gap 2: Live Website Onboarding Workflow

Wire the website workflow into the hosted API and Stripe entitlement path.

Required:

- Start onboarding through the hosted API.
- Answer required onboarding questions through the shared state machine.
- Open Stripe checkout through fake adapter by default and live adapter only
  when explicit Stripe config is present.
- Display provisioning readiness and next steps without leaking internals.
- Preserve web/Telegram/Discord parity.

Acceptance:

- Website onboarding creates the same session shape as Telegram/Discord.
- Invalid channels and malformed payloads fail before rate-limit writes.
- Checkout handoff is tested in fake mode.
- Live Stripe E2E is documented as blocked until credentials are present.

## Gap 3: Telegram And Discord Runtime Bot Deployment

Add real runtime adapters while preserving fake/local tests.

Required:

- Telegram SDK runtime adapter behind explicit env.
- Discord SDK/runtime adapter behind explicit env.
- Shared onboarding state, rate limits, copy, checkout handoff, and safe error
  shapes with the hosted API.
- Webhook/polling mode documented for the production domain.
- No live sends in unit tests.

Acceptance:

- Fake Telegram and Discord tests pass without secrets.
- Runtime adapter refuses to start without required env.
- Live bot E2E instructions are explicit and secret-safe.

## Gap 4: Live Stripe Checkout/Webhook Provisioning E2E

Turn Stripe from fake adapter coverage into a real gated test path.

Required:

- Stripe checkout session creation with configured price ids.
- Webhook signature verification.
- Subscription/customer/invoice event handling.
- Entitlement state drives provisioning readiness.
- Customer portal link when configured.
- Replay/idempotency tests for webhooks.

Acceptance:

- Fake tests remain no-secret.
- Stripe test-mode E2E runs only when test keys and webhook secret are present.
- Drift detector reports subscription-active-without-deployment and
  deployment-active-without-subscription cases.

## Gap 5: Cloudflare DNS/Subdomain Automation

Implement and prove hostname orchestration.

Required:

- Per-deployment obscure hostname allocation.
- Cloudflare DNS mutation through scoped token only.
- Cloudflare Tunnel or Access path if selected.
- DNS drift detection and repair action.
- Avoid fragile path-prefix routing for Nextcloud/code-server unless tested.
- Prefer service hostnames or safe deep links when embedding is brittle.

Acceptance:

- Fake Cloudflare tests remain default.
- Live DNS E2E creates, verifies, repairs, and removes a test hostname.
- Admin dashboard surfaces DNS state and drift.

## Gap 6: Docker Compose Provisioning Executor

Make provisioning actually create an ArcLink instance under live-gated control.

Required:

- Rendered per-deployment Compose project.
- State roots under `/arcdata/deployments/<deployment_id>/`.
- Unprivileged containers.
- Per-deployment networks.
- Resource limits and health checks.
- Rollback and idempotent resume.
- Services: Hermes, qmd, vault watch, memory synthesis, managed context,
  Nextcloud/files, code-server, dashboard/API, bot handoff, health/logs.

Acceptance:

- Dry-run renderer remains secret-safe.
- Live executor refuses to run without explicit operator/E2E switch.
- Test deployment boots, reports health, and can be torn down cleanly.

## Gap 7: Chutes Per-Deployment Key Lifecycle

Make Chutes the default inference provider without sharing plaintext keys.

Required:

- Central Chutes owner/admin credential loaded only from live secret env.
- Per-deployment secret reference creation, rotation, and revocation where the
  Chutes account/API supports it.
- Fallback documented if Chutes key lifecycle must be manually provisioned.
- Default endpoint `https://llm.chutes.ai/v1`.
- Default model `moonshotai/Kimi-K2.6-TEE` until catalog refresh proves a newer
  preferred default.
- Provider model catalog refresh job for Chutes/OpenAI/Anthropic defaults.

Acceptance:

- Fake Chutes tests remain no-secret.
- Live Chutes inference E2E proves the selected auth/header path.
- No plaintext Chutes key appears in git, logs, docs, or rendered output.

## Gap 8: Hetzner-Hosted Full Stack Behind Domain

Run the product on the always-on host or a selected Hetzner node.

Required:

- Production compose/control-plane deployment.
- Traefik or justified alternative for HTTPS/routing.
- Cloudflare DNS points to the correct entrypoint.
- Persistent data directories and backup plan.
- Health checks, logs, restart policy, and operator runbook.
- Firewall/ports documented.

Acceptance:

- Public production URL resolves.
- Hosted API and web app are reachable over HTTPS.
- Admin and user surfaces require auth.
- Health endpoints are wired into admin visibility.

## Gap 9: Full Signup To Usable Agent E2E

Prove the money path as a user, without shortcuts.

Required:

- Website signup path.
- Telegram signup path.
- Discord signup path.
- Stripe checkout.
- Provisioning job.
- Cloudflare hostname.
- Docker stack boot.
- User dashboard.
- Private bot handoff.
- Hermes response.
- qmd retrieval from uploaded vault content.
- Memory synth update and managed-context stub visibility.
- Nextcloud/files and code-server access.

Acceptance:

- Recorded E2E notes include exact date, environment, test user, and non-secret
  evidence.
- Failures are tracked as defects, not waved away.
- No fake adapter is used in a claimed live E2E pass.

## Gap 10: Production Admin Dashboard With Live Controls

Move the admin surface from read-model contracts to operational control plane.

Required:

- Overview: users, MRR/test revenue, signup funnel, failed payments,
  provisioning queue, unhealthy deployments, host CPU/RAM/disk, DNS drift.
- Onboarding funnel by web/Telegram/Discord.
- Users/deployments detail pages.
- Payments and Stripe reconciliation.
- Infrastructure health: nodes, Traefik, Cloudflare, DB, queues, backups.
- Bots: webhook health, active onboarding sessions, failures, rate limits.
- Security/abuse: failed admin auth, suspicious resource use, SSH/TUI events.
- Releases/maintenance: image versions, canary rollout, maintenance mode,
  rollback, announcements.
- Live controls: restart service, restart stack, force resynth, DNS repair,
  reprovision, suspend/restore, all through reason, CSRF, idempotency, RBAC,
  and audit.

Acceptance:

- Fake executor tests cover every action.
- Live action E2E is gated and recorded.
- Audit log includes who, what, when, target, reason, request id, and result.
- No unauthenticated or unaudited admin mutation route exists.

## Required Accounts And Secrets

Do not put these in git. Store live values only in a root-owned env file or
secrets manager. Use fake adapters until these exist.

### Cloudflare

- Zone id for `arclink.online`.
- DNS edit API token scoped to the zone.
- Account id if using Tunnels or Zero Trust Access.
- Tunnel token or Access configuration if selected.
- Confirm `arclink.online` is managed by Cloudflare nameservers.

Suggested env names:

- `CLOUDFLARE_ZONE_ID`
- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_TUNNEL_TOKEN`

### Hetzner

- Hetzner API token for the project.
- Decision: use current `s1396` host or create a new production/test node.
- SSH key/public key to install on new nodes if provisioning via API.
- Desired region/server type/volume size/firewall policy.

Suggested env names:

- `HETZNER_API_TOKEN`
- `ARCLINK_HETZNER_SERVER_TYPE`
- `ARCLINK_HETZNER_LOCATION`
- `ARCLINK_HETZNER_SSH_KEY_NAME`

### Stripe

- Stripe test publishable key.
- Stripe test secret key.
- Webhook signing secret.
- Product/price ids for the first ArcLink plan.
- Customer portal enabled or portal configuration id.
- Success and cancel URLs for the production domain.

Suggested env names:

- `STRIPE_PUBLISHABLE_KEY`
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `ARCLINK_STRIPE_PRICE_STARTER`
- `ARCLINK_STRIPE_PRICE_PRO`
- `ARCLINK_STRIPE_PORTAL_CONFIG_ID`

### Chutes

- Chutes owner/account API key for `https://llm.chutes.ai/v1`.
- Confirmation whether the account supports programmatic per-deployment key
  creation/rotation/revocation.
- If not supported, define the manual key issuance process.

Suggested env names:

- `CHUTES_API_KEY`
- `CHUTES_BASE_URL`
- `ARCLINK_CHUTES_DEFAULT_MODEL`

### Telegram

- Public onboarding bot token from BotFather.
- Bot username.
- Webhook URL decision for the production domain.
- Optional test chat id for E2E.

Suggested env names:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_BOT_USERNAME`
- `TELEGRAM_TEST_CHAT_ID`

### Discord

- Application id.
- Public key.
- Bot token.
- Client secret if OAuth is used.
- Test guild id.
- Test channel id.
- Interaction/webhook endpoint decision.

Suggested env names:

- `DISCORD_APP_ID`
- `DISCORD_PUBLIC_KEY`
- `DISCORD_BOT_TOKEN`
- `DISCORD_CLIENT_SECRET`
- `DISCORD_TEST_GUILD_ID`
- `DISCORD_TEST_CHANNEL_ID`

### Optional Provider And Knowledge Integrations

- Notion test workspace/token.
- OpenAI/Codex BYOK or OAuth test account details.
- Anthropic/Claude BYOK or OAuth test account details.
- SMTP or transactional email provider if email/passwordless auth is selected.

## Ralphie Operating Rules

- Keep building no-secret work while credentials are missing.
- When a live gate is reached, add the missing credential to
  `docs/arclink/live-e2e-secrets-needed.md` and continue with fake coverage.
- Never mark live behavior complete without a real recorded E2E pass.
- Every final-form gap must either be implemented, explicitly live-blocked by a
  named missing credential, or tracked as a defect.
