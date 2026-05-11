# ArcLink Creative Team Brief

This brief is the creative source of truth for ArcLink's public-facing story, Raven's voice, and the early user journey. It intentionally separates the product mythology from raw implementation details so the first experience feels guided, not technical.

## Implementation Status Note

Use this brief as the target creative direction. The Raven onboarding copy,
button-led prelaunch flow, pricing language, web hero, web onboarding, public
Telegram/Discord bot state machine, Stripe checkout handoff, and Sovereign
Control Node path are implemented as local public-repo behavior in the current
`arclink` branch. Where those paths touch Stripe, Telegram, Discord, Notion,
Chutes, Cloudflare, Tailscale, Docker, or a production host, live external
proof remains gated by the operations runbooks and explicit operator
authorization.

Some broader infrastructure items in the scope below are live foundations or planned expansion surfaces rather than fully customer-facing production features today: multi-host global fleet scheduling, wildcard Cloudflare production routing, Prometheus/Loki/Grafana operations surfaces, per-service public hostnames, SSH bastion, and large-scale canary release management. Keep them in the creative map, but avoid promising them as generally available until the product dashboard and operations runbooks mark them live.

## Naming And Metaphor Stack

| Layer | Name | Role |
| --- | --- | --- |
| The product | ArcLink | Private AI infrastructure, productized. The thing the customer buys. |
| The metaphor | Onboarding ArcLink | Internal and Raven voice framing. Keep the public promise simple: Agent onboard ArcLink, or Agents onboard ArcLink. |
| The cohort | Founders | Early operators who shape the launch. Use the product SKU name when pricing requires it; do not explain external lore in public or operator-facing docs. |
| The guide | Raven | Public-facing bot/persona. First contact, onboarding, launch liaison, control-panel guide. Telegram username: `@arclink_bot`. Bio: `ARCLINK CURATOR`. |
| The agent runtime | Hermes | The agentic harness inside each pod: memory, skills, tools, reasoning loop. Each pod ships with a private Hermes. |
| The retrieval rail | qmd vault | Vault index/retrieval over the user's files. |
| The model rail | Chutes-first | SOTA inference default; BYOK lanes for Codex, Claude, and other providers preserved. |
| The unit | Agent / Crew member | One Hermes instance plus its surrounding services. Limited 100 Founders is $149/month for Sovereign-equivalent access. Sovereign is $199/month: Agent onboard ArcLink. Scale is $275/month: Agents onboard ArcLink with Federation. Agentic Expansion adds agents for $99/month on Sovereign or $79/month on Scale. |

Voice rule:

> I'm Raven. I bring ArcLink online around you.

Not:

> Use `/start`, `/agents`, `/connect_notion`...

Raven is the competent operator on comms when the lights come on. She is not a mascot and not a help menu.

## What ArcLink Delivers

ArcLink gives a customer private AI infrastructure without asking them to manage infrastructure.

Onboarding surfaces share the same state machine:

- Web onboarding in Next.js and Tailwind
- Public Telegram bot through Raven
- Public Discord bot through Raven
- Stripe Checkout, where email is collected securely instead of in chat

Per-pod services:

- Hermes agent runtime and Hermes dashboard
- qmd vault index/retrieval
- Vault watcher
- Memory synthesis and hot memory stubs through managed context
- Skills lane for installable and upgradeable agent capabilities
- Nextcloud files UI for vault/files
- Code dashboard plugin
- Private bot gateway for the user's agent
- Brokered Notion SSOT preparation, webhook/indexing rails, and
  dashboard-secret handling; live workspace verification stays proof-gated
- Private GitHub backup for Hermes home and configuration snapshots
- Unified per-pod dashboard intent wrapping the core activities; live runtime
  access stays proof-gated until an authorized proof run

Per-pod hostname target:

- `u-<prefix>.arclink.online` - unified dashboard
- `hermes-<prefix>.arclink.online` - Hermes
- Future: `mcp-<prefix>.arclink.online`

Prefixes should be obscure and non-enumerable, for example `arc-7k9m2p`.

Sovereign Control Node scope:

- ArcLink Hosted API for onboarding, checkout, entitlement, provisioning, dashboard, admin, health, audit, DNS drift, provider state, webhooks, billing portal, and bot webhooks
- Public Raven Telegram and Discord adapters
- Next.js web app for marketing, onboarding, user dashboard, and admin
- SQLite-first local path with Postgres expansion path
- Redis for jobs, pub/sub, rate limits, and cache paths
- Traefik ingress with domain/Tailscale/Cloudflare routing modes
- Provisioning workers, model-catalog worker, Stripe webhook worker, DNS drift
  worker, and local provider-key control boundaries; live provider key creation
  and utilization proof stay gated
- Admin/operator dashboard scope: overview, users, deployments, onboarding, health, provisioning, DNS, payments, infrastructure, bots, security, releases, audit, events, actions, sessions, provider, reconciliation

Pricing:

- Limited 100 Founders: $149/month
- Sovereign: $199/month
- Scale: $275/month
- Agentic Expansion: $99/month on Sovereign, $79/month on Scale
- Stripe collects email at checkout
- Development/fake-adapter environments must clearly say no live charges

## Web Hero

Nav:

```text
ARCLINK | Sign In | Take Me Aboard
```

Hero headline:

```text
I'm Raven.
I'll bring your agent aboard ArcLink.
```

Hero body:

```text
Give me a name, a mission, and a cleared Stripe handoff. I will bring your agent aboard ArcLink. Sovereign is Agent onboard ArcLink for $199/month. Scale is Agents onboard ArcLink with Federation for $275/month.
```

Hero CTAs:

```text
Onboard Agent
Open Dashboard
```

Feature grid:

```text
Hermes Agent - I give each operator a private assistant with memory, skills, and room to grow.
SOTA Model Rails - I start on Chutes and keep BYOK lanes open for the frontier models you trust.
qmd Retrieval - I keep the vault searchable so agents can pull the right context fast.
Managed Memory - I keep lightweight memory stubs hot so the agent stays oriented.
Files & Code - I wire in Drive and Code so your agent has hands, not just words.
Health & Ops - I watch DNS, billing, provisioning, and services so the launch path stays visible.
```

Footer:

```text
© {year} ArcLink. Agents onboard ArcLink.
```

## Web Onboarding

The web onboarding page is a single card with Raven's avatar at the top.

Start step heading:

```text
Choose ArcLink Onboarding
```

Start body:

```text
I can take you from a few answers to agent onboard ArcLink with memory, files, code workspace, model access, and dashboard visibility already wired up.
```

Package CTAs:

```text
Founders - $149/month
Sovereign / Scale
Sovereign - $199/month
Scale - $275/month
```

Loading:

```text
Opening...
```

Questions heading:

```text
Name The Agent
```

Field:

```text
Display Name
```

Placeholder:

```text
Your name or org
```

Helper:

```text
{Plan Name} is on deck at {Plan Price}. {Plan Summary} Agentic Expansion is $99/month on Sovereign and $79/month on Scale.
```

CTA:

```text
Save & Continue
```

Loading:

```text
Saving...
```

Checkout heading:

```text
Onboard Agent - $149/month
Onboard Agent - $199/month
Onboard Agents - $275/month
```

Checkout body:

```text
I will hand you to Stripe, watch for confirmation, then move your ArcLink onboarding into the launch queue.
```

CTA:

```text
Onboard Agent - $149/month
Onboard Agent - $199/month
Onboard Agents - $275/month
```

Loading:

```text
Preparing...
```

Done heading:

```text
Stripe Link Ready
```

Done body:

```text
I have your checkout link ready.
```

CTA:

```text
Complete The Hire
```

Fallback:

```text
Onboarding complete. I am preparing your deployment.
```

Fallback CTA:

```text
Open Dashboard →
```

Checkout return pages:

```text
/checkout/success?session={session_id} clears local onboarding resume state and offers Open Dashboard or Add Another Agent.
/checkout/cancel?session={session_id} preserves the onboarding resume path and offers Resume Onboarding or Back Home.
```

Development-only chip:

```text
Fake adapters active in development. No live charges.
```

## Public Raven Bot

Telegram and Discord use the same state machine and should preserve the same conversational intent.

### Start

Triggered by `/start`, empty message, `start`, or `restart`.

```text
Raven here. ArcLink is in range.

I bring private agents online with memory, files, code workspace, model access, and dashboard visibility. No bot-building. No server chores.

Tap Take Me Aboard to pick Founders, Sovereign, or Scale. Tap Update Name and just tell me what to call you.
```

Buttons:

```text
Take Me Aboard
Update Name
```

### Help - Prelaunch

```text
Comms are open.

I will keep this simple until your first agent is live. I can help you pick Sovereign or Scale, open checkout, or read the board.

After launch, I reveal the working controls: your crew, Notion, private backups, channel pairing, files, code, and health.
```

Buttons:

```text
Take Me Aboard
Update Name
```

### Unknown / Loose Message - Prelaunch

```text
I'm Raven, and I'm online.

No command map needed yet. I can bring you aboard, help choose the first path, or check where your launch stands. Once your agent is awake, I will reveal the deeper controls in a cleaner checklist.
```

Buttons:

```text
Take Me Aboard
Update Name
```

### Email Attempted In Chat

```text
I do not need your email in chat. Stripe handles that securely at checkout. Tap Update Name and tell me what to call you.
```

### Package Prompt

Triggered by `Take Me Aboard`, `/packages`, or `/name <Your Name>` after the
name is captured.

```text
Welcome aboard, {Name}.

Choose your ArcLink onboarding lane.

Limited 100 Founders is $149/month: Sovereign-equivalent access for the first 100 aboard.
Sovereign is $199/month. Scale is $275/month.

Agentic Expansion after launch starts at $79/month on Scale and $99/month on Sovereign.
```

Buttons:

```text
Founders - $149/month
Sovereign / Scale
```

### Standard Package Prompt

Triggered by `Sovereign / Scale` or `/packages standard`.

```text
Welcome aboard, {Name}.

Choose how many agents to onboard ArcLink.

Sovereign is $199/month: Agent onboard ArcLink.
Scale is $275/month: Agents onboard ArcLink with Federation.
```

Buttons:

```text
Sovereign - $199/month
Scale - $275/month
```

### Plan Selected

Triggered by `/plan sovereign` or `/plan scale`. `starter` and `operator` are accepted only as backward-compatible aliases and must not appear in public copy.

```text
Sovereign is locked.

Agent onboard ArcLink for $199/month. Stripe handles the handoff, then I move onboarding into the launch queue and report back here.
```

Buttons:

```text
Hire Sovereign - $199/month
Change Package
```

### Checkout

Triggered by `/checkout`.

```text
Checkout is ready. Complete the Stripe handoff here; when payment clears, I move your first ArcLink agent into the launch queue.
```

Buttons:

```text
Hire Founders - $149/month
Check Status
```

### Status

```text
I checked the board. Session `{session_id}` is `{status}`. Launch step: `{current_step}`.
Active agent: {agent_label}.
```

Buttons:

```text
Show My Crew
Hire Founders
```

## Postlaunch Raven Bot

### Help - Postlaunch

```text
Control panel is open.

Your first agent is aboard, so I can show more of the machinery now. Use the buttons for the common work. If this is an active Telegram chat, use `/raven agents`, `/raven status`, `/raven connect_notion`, `/raven config_backup`, `/raven link_channel`, or `/raven cancel` for ArcLink controls. Bare slash commands belong to the agent at the helm.

Pick one lane and I will keep the steps tight.
```

Buttons:

```text
Show My Crew
Wire Notion
Set Up Backup
```

### Crew Roster

Triggered by `/agents` before the active Telegram command scope is refreshed,
or by `/raven agents` after the active agent owns the bare Telegram slash
namespace.

```text
Your ArcLink crew

I keep this roster personal. Every agent here has its own pod, memory rail, tool lane, vault access, and system health tied back to your account.

- {Agent Label}: active
- {Agent Label}: {status}
```

Dynamic buttons:

```text
Take Helm: {Agent Label}
Add Agent
```

### No Agent Yet

```text
I do not see your first agent yet. Choose Founders for $149/month, Sovereign for $199/month, or Scale for $275/month. Once an agent is active, Agentic Expansion adds agents for $99/month on Sovereign or $79/month on Scale.
```

Button:

```text
Take Me Aboard
```

### Switch Agent

Triggered by `/agent-<slug>`.

```text
Done. I have {Agent Label} on the rail now. Notion, backup, and status workflows will target that agent until you switch again.
```

Buttons:

```text
Show My Crew
Check Status
```

### Agent Not Found

```text
I do not see that agent on your ArcLink roster. Open `/agents` and use the buttons I build for your account.
```

Button:

```text
Show My Crew
```

### Add Agent

Triggered by `/add-agent`.

```text
Agentic Expansion for your {plan} plan is {$price}/month. Clear the Stripe handoff and I will move the new agent into the launch queue with the rest of your crew.
```

Buttons:

```text
Hire Agent - {$price}/month
Back To My Crew
```

### Link Channel

Triggered by `/link_channel` or `/link-channel`; `/pair_channel` and `/pair-channel` remain backward-compatible aliases.

```text
Pairing lane open.

On the other channel, tell Raven: `/link-channel {code}`

This code expires in 10 minutes. If your agent is already online, the other channel gets the same ArcLink identity, crew, tools, vault, Notion lane, and status. The chat session stays separate; ArcLink links both channels to the same agent account.
```

Buttons:

```text
Show My Crew
Check Status
```

### Connect Notion

Triggered by `/connect_notion`.

```text
Good. Let's wire Notion into your ArcLink pod.

I need this callback URL in the Notion webhook/subscription setup:
{callback_url}

Then share the page or database with the ArcLink integration. Keep tokens out of chat; when I need a secret, use the secure dashboard field.

Reply `ready` when Notion sends the verification handshake, or `cancel` and I will close this lane.
```

Ready confirmed:

```text
Good. I recorded Notion as ready for this pod. If the webhook still says verification is not configured, open the dashboard Notion panel so ArcLink can arm the verification-token install window.
```

Waiting:

```text
Reply `ready` after Notion sends the verification handshake, or `cancel` to close the Notion workflow.
```

### Private Backup

Triggered by `/config_backup`.

```text
I am opening the private backup lane.

Create or choose a private GitHub repository for this pod's Hermes home and configuration snapshots. Send me `owner/repo` and I will pin the request to this deployment.

Example: `{example}`

Use a dedicated deploy key for this pod. Do not reuse the ArcLink upstream key or the arclink-priv backup key.
```

Invalid input:

```text
Send the private GitHub repository as `owner/repo`, or reply `cancel` to close backup setup.
```

Recorded:

```text
Recorded `{owner/repo}` for this pod's private backup workflow.

Keep the repository private. ArcLink will use a dedicated pod deploy key with write access; when the key is prepared, add it here:
https://github.com/{owner/repo}/settings/keys

I also wrote this to the deployment event stream so the admin dashboard can track it.
```

### Cancel

Triggered by `/cancel`.

```text
I closed that lane.

Nothing is lost. When you are ready, I can bring you back to the launch path or show the next clean step.
```

Buttons:

```text
Take Me Aboard
Check Status
```

### Guard Rails

Entitlement pending:

```text
I have your pod reserved, but billing has not cleared yet. Send `checkout` and I will reopen the handoff.
```

Provisioning failed:

```text
I found your pod, but provisioning needs operator attention before I can safely run this workflow.
```

Other status:

```text
I found your pod in `{status}`. I can continue once it reaches active.
```

Workflow attempted before any pod exists:

```text
I can run that lane once your first agent is awake aboard ArcLink. Send `/start` and I will get you aboard, or finish checkout if your launch is already moving.
```

## Command And Button Inventory

Registered public Telegram commands before an active Telegram chat receives its
per-chat active-agent scope:

| Command | Description |
| --- | --- |
| `/start` | Begin your ArcLink launch path |
| `/help` | Open the ArcLink action palette |
| `/status` | Check onboarding or pod status |
| `/name <display_name>` | Name your ArcLink workspace |
| `/plan <sovereign\|operator\|scale>` | Choose sovereign, operator, or scale |
| `/checkout` | Hire your first ArcLink agent |
| `/agents` | Open your ArcLink crew manifest |
| `/raven_name` | Set Raven's ArcLink-message display name for this channel or account |
| `/connect_notion` | Connect Notion to your live pod |
| `/config_backup` | Configure private pod backup |
| `/link_channel` | Link Telegram and Discord to the same ArcLink account |
| `/cancel` | Close the active setup workflow |

In active Telegram chats, the visible command menu changes to one Raven
control command, normally `/raven`, plus the active agent's current Hermes
commands. Use `/raven agents`, `/raven status`, `/raven connect_notion`,
`/raven config_backup`, `/raven link_channel`, or `/raven cancel` for ArcLink
controls there. Bare slash commands belong to the active agent. Discord keeps
global slash commands and uses `/agent <message-or-command>` for active-agent
commands.

Hidden/account-state actions:

| Action | Description |
| --- | --- |
| `/add-agent` | Hire Agentic Expansion for the active account |
| `/agent-<slug>` | Switch active agent |

Discord commands mirror the same set and include a top-level `/arclink message:<text>` for freeform conversation. Discord plan selection uses choices for Limited 100 Founders, Sovereign, and Scale.

Canonical button labels:

```text
Take Me Aboard
Update Name
Founders - $149/month
Sovereign / Scale
Sovereign - $199/month
Scale - $275/month
Hire Founders - $149/month
Hire Sovereign - $199/month
Hire Scale - $275/month
Change Package
Show My Crew
Take Helm: {Agent Label}
Add Agent
Hire Additional Agent
Back To My Crew
Wire Notion
Set Up Backup
Complete The Hire
Onboard Agent
Open Dashboard
```

## Brand And Voice North Star

Visual system:

- Jet Black `#080808`
- Carbon `#0F0F0E`
- Soft White `#E7E6E6`
- Signal Orange `#FB5005`
- State-only accents: Electric Blue `#2075FE`, Neon Green `#1AC153`
- Type: Space Grotesk for display; Satoshi or Inter for UI/body
- Imagery: dark, abstract, private-infrastructure visuals with orange connection paths
- Avoid stock photos, generic AI imagery, purple gradients, and decorative gradient effects

Voice:

- Clear
- Direct
- Confident
- Short
- Outcome-focused
- Human
- Operator language, not marketer language
- No buzzwords
- No hype
- No emoji unless the user opts in

Posture:

```text
Premium control room, not marketing decoration.
Dense but calm.
Orange = action.
Blue and green = state.
```

The first experience must feel like:

> I just met the guide who can actually get this thing launched.

Not:

> I opened a bot and got a slash-command help menu.

The ship metaphor should stay internal. Public copy should prefer the simple purchase promise: Agent onboard ArcLink, or Agents onboard ArcLink.

Founder-tier framing belongs in launch and founder communications only. Keep
public product copy focused on what the user receives: ArcLink brings their
agent online, connects the knowledge rails, and keeps control surfaces scoped
to their account.
