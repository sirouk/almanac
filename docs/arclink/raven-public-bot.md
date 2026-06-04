# Raven Public Bot

Raven is the guide to ArcLink and Curator of the Console. Raven should introduce herself in first person and invite the Captain to onboard a Hermes Agent into an ArcPod, not recite a product catalog. The Captain should feel like a capable console guide has opened a private channel and is ready to bring a Hermes Agent online.

The voice should feel like a clear, fast, technically proud launch guide: calm under pressure and excited to get the user's agent online. Keep the ArcLink story original; do not imitate show dialogue, quote protected material, or imply the product is affiliated with any show.

## Story Rails

- Raven is the guide.
- ArcLink is the agentic harness.
- Agents occupy ArcPods.
- The customer chooses a mission path.
- Checkout hires the first Hermes Agent and moves onboarding into the launch queue.
- Status checks are concrete status views, not theatrical filler.
- Notion and backup are setup lanes for the active account. Notion setup stays
  behind the credential handoff: Raven can record the setup intent only after
  the user stores and acknowledges the secure completion bundle for the Hermes
  Dashboard.
- After onboarding, Raven remains the public control conduit, but the active
  Hermes Agent owns the normal slash namespace wherever the platform can support it.
  The first normal post-onboarding message in a linked channel explains that
  normal messages now route to the active Hermes Agent. After that, normal messages
  are queued as selected-agent turns and Raven brings the Hermes Agent's reply back
  to the same linked Telegram or Discord channel.
- Public selected-agent turns default to final-message delivery. The bridge is
  a short-lived synthetic gateway rather than a long-running Hermes platform
  adapter, so `ARCLINK_PUBLIC_AGENT_BRIDGE_STREAMING=1` is an operator opt-in
  only after that runtime path has been validated.
- In active Telegram chats, Raven refreshes a per-chat command scope with one
  Raven control command, normally `/raven`, plus the active Hermes Agent's current
  Hermes command menu. Bare slash commands such as `/agents`, `/status`,
  `/model`, `/provider`, and `/reload_mcp` belong to the active Hermes Agent when
  they appear in that Hermes command inventory. Raven control actions move
  behind `/raven`, for example `/raven agents`, `/raven status`,
  `/raven credentials`, `/raven connect_notion`, `/raven config_backup`, and
  `/raven link_channel`.
- If a future plugin, skill, or Hermes upgrade collides with `/raven`, ArcLink
  chooses a fallback Raven control command such as `/arclink` or
  `/arclink_control` and queues an operator alert after command refresh. Direct
  `/update` remains suppressed from active Hermes Agent command menus and routes to
  ArcLink's managed upgrade rail.
- Discord global slash commands cannot be per-user Hermes command menus.
  Discord keeps the registered Raven controls and exposes `/agent
  <message-or-command>` as the active Hermes Agent slash bridge. The Hermes Dashboard
  remains the direct dashboard path for the richest Hermes Agent surface.

## Voice Rules

- Prefer first person: "I'm Raven", "I can", "I will", "I found", "I need".
- Explain what ArcLink does through action, not inventory.
- Keep the mythic language grounded in concrete next steps.
- Never make the user decode roleplay before they can act.
- Keep pricing clear: Limited 100 Founders is $149/month, Sovereign is $199/month, Scale is $275/month, Sovereign Agentic Expansion is $99/month, and Scale Agentic Expansion is $79/month.
- Buttons should feel exciting while saying exactly what will happen.

Strong:

> I'm Raven. Give me a Hermes Agent name and a mission tier, and I will bring your ArcPod online: ArcLink skills, Drive, Code, Terminal, model rails, memory, and health checks already wired in.

Weak:

> ArcLink is a private agentic harness with inference, memory, tools, vault, and deployment health.

## Default Offer

- Limited 100 Founders: $149/month for single-ArcPod access for the first 100 Captains.
- Sovereign: $199/month: one Hermes Agent onboard ArcLink.
- Scale: $275/month: three Hermes Agents onboard ArcLink with Federation.
- Agentic Expansion: $99/month per additional Sovereign agent, or $79/month per additional Scale agent.
- Stripe Checkout collects customer email. Chat onboarding should not ask for email.
- Chutes remains the baked-in primary inference rail unless the user brings another provider.

## Account-Aware Commands

Configured Operator Telegram identities are intercepted before Captain
onboarding. When Telegram is the primary operator channel, the configured
`OPERATOR_NOTIFY_CHANNEL_ID` plus `ARCLINK_OPERATOR_TELEGRAM_USER_IDS` must
match the incoming Telegram update. When the operator enables both Telegram and
Discord but makes another channel primary, private Telegram DMs from the
allowed operator user IDs still route to Operator Raven, while group chats stay
on the safe Captain/public contract. `/start`, `/help`, `/raven`,
`/raven_name`, and free-form text show the Operator Raven bridge instead of
checkout copy.
The Operator Telegram command set is the registered
`ARCLINK_OPERATOR_TELEGRAM_COMMANDS` in `arclink_telegram.py`:
`/operator_status`, `/agents`, `/fleet_list`, `/worker_probe`, `/user_lookup`,
`/pod_repair`, `/upgrade_check`, `/upgrade`, `/pin_upgrade`, `/rollout`,
`/action_status`, `/academy_status`, `/billing_status`, `/backup_status`, and
`/workspace_status`. These dispatch through
`dispatch_operator_raven_command` in `arclink_operator_raven.py`. Read commands
(`operator_status`, `fleet_list`, `user_lookup`, `academy_status`,
`academy_roster`, `upgrade_check`, `upgrade_policy`, `action_status`,
`billing_status`, `backup_status`, `workspace_status`, and `worker_probe`,
which is dry-run only) never mutate. The mutating commands (`pod_repair`,
`rollout`, `upgrade`/host
upgrade, `pin_upgrade`) are NOT read-only: they use a four-mode contract where
`--dry-run` previews, no-dry-run without an operator actor fails closed, and
no-dry-run with the operator actor but no second confirmation fails closed. A
real queued intent requires the operator actor plus `confirm` or the configured
operator approval code (`strip_operator_approval_code`, constant-time compare),
and live execution still honors `ARCLINK_EXECUTOR_ADAPTER` (fake adapter =
record-only). Live
delivery of these surfaces is proof-gated behind `PG-BOTS`; per-action live
effect rolls up to the relevant proof gate (for example rollout is
`PG-UPGRADE`/`PG-HERMES`). For the authoritative operator action matrix and the
trust-boundary (GAP-019) rules see `docs/arclink/operations-runbook.md`.
Non-operator Telegram users continue through the Captain public bot contract.
During public bot registration, ArcLink also writes chat-scoped Telegram
command menus for configured operator Telegram chats so the Operator sees the
operator command set rather than only the Captain menu.

Registered public commands before the active Telegram per-chat scope takes
over:

- `/start`
- `/help`
- `/status`
- `/name`
- `/plan`
- `/checkout`
- `/agents`
- `/agent <message-or-command>` sends a message or slash command to the active
  agent. Use this when a platform command menu does not expose the specific
  Hermes command you want.
- `/raven_name` sets Raven's ArcLink-message display name for the current
  channel or, after account linking, the whole account. The preference changes
  Raven's name in ArcLink-rendered bot messages; Telegram and Discord platform
  profile names remain controlled by their bot registrations.
- `/connect_notion` opens the brokered shared-root Notion SSOT preparation lane
  after credential handoff acknowledgement. It does not verify Notion, install
  secrets, accept tokens in chat, or claim user-owned OAuth.
- `/config_backup`
- `/link_channel`
- `/upgrade_hermes`
- `/cancel`
- `/raven <control>` is the active Telegram Raven control namespace. Use
  `/raven agents`, `/raven status`, `/raven credentials`, `/raven
  connect_notion`, `/raven config_backup`, `/raven link_channel`, `/raven
  upgrade_hermes`, or `/raven cancel`.

Hidden/account-state actions:

- `/pair-channel` and `/pair_channel` remain backward-compatible aliases for `/link-channel` and `/link_channel`.
- `/add-agent` is accepted only after the account has an active first deployment. It is surfaced as an `/agents` button, not as a global registered command.
- `/agent-{slug}` switches the active Hermes Agent target for the account. It is surfaced as an `/agents` manifest button, not as a global registered command.
- `/share-approve {grant_id}`, `/share-deny {grant_id}`, and `/share-accept {grant_id}` are backward-compatible owner/recipient actions for Drive/Code share grants (grant ids match `share_[0-9a-f]{32}`). Owner approve/deny moves the grant from `pending_owner_approval` to `approved`/`denied`; recipient accept claims an approved grant. Active Telegram approval buttons use `/raven approve {grant_id}`, `/raven deny {grant_id}`, and `/raven accept {grant_id}` so they cannot collide with the active Hermes Agent's slash namespace. Raven only honors the owner forms from a public channel linked to the share owner.
- `/share-claim {nonce}` (also `/share_claim` and `/arclink_share_accept`, nonce matching `asn_[0-9a-f]{48}`) claims an ephemeral share invite for the recipient. Share links expire 12 hours after they are created and can only be claimed once.
- `/upgrade-hermes` remains accepted as the Discord-friendly alias for `/upgrade_hermes`, and `/update` is intercepted too. Neither path runs direct `hermes update`; Raven points users to ArcLink-managed upgrade rails.
- `/raven-name` remains accepted as the Discord-friendly alias for
  `/raven_name`.

## Post-Launch Account Actions

After an account has a ready ArcPod, Raven owns a set of post-launch Captain
commands beyond the registered pre-launch menu. They are implemented in
`arclink_public_bots.py` and each maps to `/raven <verb>` in active Telegram
chats so they survive the active Hermes Agent owning the bare slash namespace.
This doc scopes to the command surface; the workflows themselves live in their
own subsystem docs.

- `/train-crew` (Crew Training) opens the multi-step Crew Recipe workflow
  (role, mission, treatment, preset, capacity, review). It applies an additive
  SOUL.md overlay through `apply_crew_recipe`; memories and sessions are not
  rewritten.
- `/academy` (Academy Mode) opens one-Agent-at-a-time specialist training
  (select Agent, Major, focus, sources, then sticky Academy Mode). Graduation
  stages the specialist corpus locally and explicitly states that live
  provider/Hermes proof is still required before calling the Agent graduated
  (`PG-HERMES`).
- `/retire-agent` retires an Agent behind a typed-name confirmation
  (`/confirm-retire-agent` / `/cancel-retire-agent`) and is audited.
- `/refuel` (also `/top-up`, `/credits`) quotes an ArcPod Fuel top-up. Refuel is
  local budget accounting only until live provider proof; live checkout is
  `PG-STRIPE` and live provider-balance application is `PG-PROVIDER`.
- `/wrapped-frequency` sets the ArcLink Wrapped delivery cadence for the account.
- `/rename-agent` and `/retitle-agent` update an Agent's manifest name and title.

## Button Strategy

Raven should prefer buttons over typed pseudo-actions whenever the platform supports them. Labels should be vivid, but each one must still explain the action:

- `Take Me Aboard` opens direct Founders and Scale checkout choices.
- `Founders $149/mo` opens Limited 100 Founders checkout through Stripe.
- `Scale $275/mo` opens Scale checkout through Stripe.
- `Sovereign - $199/month` chooses the Sovereign path quickly.
- `Scale - $275/month` chooses the Scale path quickly.
- `Hire Founders - $149/month`, `Hire Sovereign - $199/month`, or `Hire Scale - $275/month` opens package checkout. The checkout handoff should be a single-step message with only the checkout button; Raven reports back automatically after Stripe and provisioning events.
- `Show My Crew` opens the account-aware `/agents` roster.
- `Link Channel` opens the `/link-channel` pairing-code lane.
- `Add Agent` opens Agentic Expansion checkout after the first deployment exists.
- `Open Hermes Dashboard` opens the active Hermes Agent's dashboard.
- `Take Helm: {agent}` remains a legacy switch label only where old clients still render it; new copy should prefer `Switch Hermes Agent: {agent}`.
- `Check Status` returns status for onboarding or the active Hermes Agent.
- `Update Name` asks for the user's preferred manifest name.
- `Back To My Crew` returns to the Hermes Agent roster.
- Share approval notifications use `Approve` and `Deny` buttons. Approving lets the recipient accept Drive/Code shared folders as writable resources under `Linked`; denying leaves the share closed.

Telegram uses inline keyboard buttons. Discord uses message components. The default public command catalog remains intentionally small because global slash commands cannot reflect each individual account state. Once a Telegram chat has an active ArcLink deployment, Raven refreshes that chat's Telegram command scope with one Raven control command plus the current Hermes command menu from the active Hermes Agent, such as `/agents`, `/status`, `/help`, `/model`, `/provider`, `/reload_mcp`, `/reload_skills`, `/usage`, and `/stop`. This scope is refreshed after public bot command registration during control install/upgrade, and Telegram webhook handling also refreshes the active chat scope when the user interacts. The refresh writes the observed active Hermes Agent command names into session metadata and queues an operator notification when it sees a legacy Raven-name collision, a hard Raven control collision, a policy-suppressed command such as `/update`, or hidden commands caused by Telegram's command-menu cap.

Raven buttons in active Telegram chats are rewritten to the Raven namespace so taps continue to reach Raven even when the bare slash command belongs to the active Hermes Agent. For example, `Show My Crew` becomes `/raven agents` and `Check Status` becomes `/raven status`.

Telegram webhook registration must include `callback_query` in `allowed_updates`; otherwise inline buttons render but Telegram never delivers taps to ArcLink. `deploy.sh control install|upgrade` registers the public webhook at `/api/v1/webhooks/telegram` and refreshes command buttons so Raven can acknowledge taps and send the next turn.

## Asset Slots

Drop the Raven profile and card artwork into:

- `web/public/brand/raven/raven_pfp.webp`
- `web/public/brand/raven/raven_card.webp`
- `web/public/brand/raven/raven_hero.webp`

If source files arrive as JPG or PNG, keep a copy with the original extension and export optimized WebP names for the web and bot setup workflows.
