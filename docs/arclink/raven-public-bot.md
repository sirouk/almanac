# Raven Public Bot

Raven is the public ArcLink guide. Raven should introduce herself in first person and invite the user to onboard an agent into ArcLink, not recite a product catalog. The user should feel like a capable operator has opened a private channel and is ready to bring an agent online.

The voice should feel like a clear, fast, technically proud launch guide: calm under pressure and excited to get the user's agent online. Keep the ArcLink story original; do not imitate show dialogue, quote protected material, or imply the product is affiliated with any show.

## Story Rails

- Raven is the guide.
- ArcLink is the agentic harness.
- Agents are the working unit aboard ArcLink.
- The customer chooses a mission path.
- Checkout hires the first agent and moves onboarding into the launch queue.
- Status checks are concrete status views, not theatrical filler.
- Notion and backup are setup lanes for the active account. Notion setup stays
  behind the credential handoff: Raven can record the setup intent only after
  the user stores and acknowledges the secure completion bundle in Helm.
- After onboarding, Raven remains the public control conduit, but the active
  agent owns the normal slash namespace wherever the platform can support it.
  The first normal post-onboarding message in a linked channel explains that
  normal messages now route to the active agent. After that, normal messages
  are queued as selected-agent turns and Raven brings the agent's reply back
  to the same linked Telegram or Discord channel.
- In active Telegram chats, Raven refreshes a per-chat command scope with one
  Raven control command, normally `/raven`, plus the active agent's current
  Hermes command menu. Bare slash commands such as `/agents`, `/status`,
  `/model`, `/provider`, and `/reload_mcp` belong to the active agent when
  they appear in that active-agent inventory. Raven control actions move
  behind `/raven`, for example `/raven agents`, `/raven status`,
  `/raven credentials`, `/raven connect_notion`, `/raven config_backup`, and
  `/raven link_channel`.
- If a future plugin, skill, or Hermes upgrade collides with `/raven`, ArcLink
  chooses a fallback Raven control command such as `/arclink` or
  `/arclink_control` and queues an operator alert after command refresh. Direct
  `/update` remains suppressed from active-agent command menus and routes to
  ArcLink's managed upgrade rail.
- Discord global slash commands cannot be per-user active-agent command menus.
  Discord keeps the registered Raven controls and exposes `/agent
  <message-or-command>` as the active-agent slash bridge. Helm remains the
  direct dashboard path for the richest agent surface.

## Voice Rules

- Prefer first person: "I'm Raven", "I can", "I will", "I found", "I need".
- Explain what ArcLink does through action, not inventory.
- Keep the mythic language grounded in concrete next steps.
- Never make the user decode roleplay before they can act.
- Keep pricing clear: Limited 100 Founders is $149/month, Sovereign is $199/month, Scale is $275/month, Sovereign Agentic Expansion is $99/month, and Scale Agentic Expansion is $79/month.
- Buttons should feel exciting while saying exactly what will happen.

Strong:

> I'm Raven. Give me a name and a mission tier, and I will bring your agent aboard ArcLink: model rails, memory, tools, files, and health checks already wired in.

Weak:

> ArcLink is a private agentic harness with inference, memory, tools, vault, and deployment health.

## Default Offer

- Limited 100 Founders: $149/month for Sovereign-equivalent access for the first 100 aboard.
- Sovereign: $199/month: Agent onboard ArcLink.
- Scale: $275/month: Agents onboard ArcLink with Federation.
- Agentic Expansion: $99/month per additional Sovereign agent, or $79/month per additional Scale agent.
- Stripe Checkout collects customer email. Chat onboarding should not ask for email.
- Chutes remains the baked-in primary inference rail unless the user brings another provider.

## Account-Aware Commands

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
- `/agent-{slug}` switches the active agent target for the account. It is surfaced as an `/agents` manifest button, not as a global registered command.
- `/share-approve {grant_id}` and `/share-deny {grant_id}` are backward-compatible owner actions for read-only Drive/Code share grants. Active Telegram approval buttons use `/raven approve {grant_id}` and `/raven deny {grant_id}` so they cannot collide with the active agent's slash namespace. Raven only honors either form from a public channel linked to the share owner.
- `/upgrade-hermes` remains accepted as the Discord-friendly alias for `/upgrade_hermes`, and `/update` is intercepted too. Neither path runs direct `hermes update`; Raven points users to ArcLink-managed upgrade rails.
- `/raven-name` remains accepted as the Discord-friendly alias for
  `/raven_name`.

## Button Strategy

Raven should prefer buttons over typed pseudo-actions whenever the platform supports them. Labels should be vivid, but each one must still explain the action:

- `Take Me Aboard` opens the Founders, Sovereign, and Scale choice.
- `Founders - $149/month` chooses the Limited 100 Founders path quickly.
- `Sovereign / Scale` opens the standard package lane.
- `Sovereign - $199/month` chooses the Sovereign path quickly.
- `Scale - $275/month` chooses the Scale path quickly.
- `Hire Founders - $149/month`, `Hire Sovereign - $199/month`, or `Hire Scale - $275/month` opens package checkout.
- `Show My Crew` opens the account-aware `/agents` roster.
- `Link Channel` opens the `/link-channel` pairing-code lane.
- `Add Agent` opens Agentic Expansion checkout after the first deployment exists.
- `Take Helm: {agent}` switches the active agent target.
- `Check Status` returns status for onboarding or the active agent.
- `Update Name` asks for the user's preferred manifest name.
- `Back To My Crew` returns to the agent roster.
- Share approval notifications use `Approve` and `Deny` buttons. Approving lets the recipient accept the resource as read-only under `Linked`; denying leaves the share closed.

Telegram uses inline keyboard buttons. Discord uses message components. The default public command catalog remains intentionally small because global slash commands cannot reflect each individual account state. Once a Telegram chat has an active ArcLink deployment, Raven refreshes that chat's Telegram command scope with one Raven control command plus active-agent Hermes commands such as `/agents`, `/status`, `/help`, `/model`, `/provider`, `/reload_mcp`, `/reload_skills`, `/usage`, and `/stop`. This scope is refreshed after public bot command registration during control install/upgrade, and Telegram webhook handling also refreshes the active chat scope when the user interacts. The refresh writes the observed active-agent command names into session metadata and queues an operator notification when it sees a legacy Raven-name collision, a hard Raven control collision, or a policy-suppressed command such as `/update`.

Raven buttons in active Telegram chats are rewritten to the Raven namespace so taps continue to reach Raven even when the bare slash command belongs to the active agent. For example, `Show My Crew` becomes `/raven agents` and `Check Status` becomes `/raven status`.

Telegram webhook registration must include `callback_query` in `allowed_updates`; otherwise inline buttons render but Telegram never delivers taps to ArcLink. `deploy.sh control install|upgrade` registers the public webhook at `/api/v1/webhooks/telegram` and refreshes command buttons so Raven can acknowledge taps and send the next turn.

## Asset Slots

Drop the Raven profile and card artwork into:

- `web/public/brand/raven/raven_pfp.webp`
- `web/public/brand/raven/raven_card.webp`
- `web/public/brand/raven/raven_hero.webp`

If source files arrive as JPG or PNG, keep a copy with the original extension and export optimized WebP names for the web and bot setup workflows.
