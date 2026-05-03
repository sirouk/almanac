# ArcLink Creative Team Brief

This brief is the creative source of truth for ArcLink's public-facing story, Raven's voice, and the early user journey. It intentionally separates the product mythology from raw implementation details so the first experience feels guided, not technical.

## Implementation Status Note

Use this brief as the target creative direction. The Raven onboarding copy, button-led prelaunch flow, pricing language, web hero, web onboarding, public Telegram/Discord bot state machine, Stripe checkout handoff, and Sovereign Control Node path are implemented in the current `arclink` branch.

Some broader infrastructure items in the scope below are live foundations or planned expansion surfaces rather than fully customer-facing production features today: multi-host global fleet scheduling, wildcard Cloudflare production routing, Prometheus/Loki/Grafana operations surfaces, per-service public hostnames, SSH bastion, and large-scale canary release management. Keep them in the creative map, but avoid promising them as generally available until the product dashboard and operations runbooks mark them live.

## Naming And Metaphor Stack

| Layer | Name | Role |
| --- | --- | --- |
| The product | ArcLink | Private AI infrastructure, productized. The thing the customer buys. |
| The metaphor | The Ship / The Vessel | Internal and Raven voice framing. Each customer gets their own ArcLink vessel brought online around them. |
| The cohort | The 100 | First 100 sovereigns aboard. Founder-tier mythology: early operators who shaped the hull. |
| The guide | Raven | Public-facing bot/persona. First contact, onboarding, launch liaison, control-panel guide. Telegram username: `@arclink_bot`. Bio: `ARCLINK CURATOR`. |
| The agent runtime | Hermes | The agentic harness inside each pod: memory, skills, tools, reasoning loop. Each pod ships with a private Hermes. |
| The retrieval rail | qmd vault | Vault index/retrieval over the user's files. |
| The model rail | Chutes-first | SOTA inference default; BYOK lanes for Codex, Claude, and other providers preserved. |
| The unit | Pod / Agent / Crew member | One Hermes instance plus its surrounding services. First pod $35/month; additional pods $15/month. |

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
- code-server browser IDE
- Private bot gateway for the user's agent
- Notion integration with webhook verification and dashboard-secret handling
- Private GitHub backup for Hermes home and configuration snapshots
- Unified per-pod dashboard wrapping the core activities

Per-pod hostname target:

- `u-<prefix>.arclink.online` — unified dashboard
- `files-<prefix>.arclink.online` — Nextcloud
- `code-<prefix>.arclink.online` — code-server
- `hermes-<prefix>.arclink.online` — Hermes
- Future: `mcp-<prefix>.arclink.online`

Prefixes should be obscure and non-enumerable, for example `arc-7k9m2p`.

Sovereign Control Node scope:

- ArcLink Hosted API for onboarding, checkout, entitlement, provisioning, dashboard, admin, health, audit, DNS drift, provider state, webhooks, billing portal, and bot webhooks
- Public Raven Telegram and Discord adapters
- Next.js web app for marketing, onboarding, user dashboard, and admin
- SQLite-first local path with Postgres expansion path
- Redis for jobs, pub/sub, rate limits, and cache paths
- Traefik ingress with domain/Tailscale/Cloudflare routing modes
- Provisioning workers, model-catalog worker, Stripe webhook worker, DNS drift worker, and provider-key control
- Admin/operator dashboard scope: overview, users, deployments, onboarding, health, provisioning, DNS, payments, infrastructure, bots, security, releases, audit, events, actions, sessions, provider, reconciliation

Pricing:

- First agent: $35/month
- Each additional agent: $15/month
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
I'll bring ArcLink online.
```

Hero body:

```text
Give me a name, a mission, and a cleared Stripe handoff. I will turn that into your private ArcLink vessel: weapons-grade agents, SOTA inference rails, memory, retrieval, files, code tools, bot channels, and live deployment health. First agent $35/month.
```

Hero CTAs:

```text
Hire My First Agent
Open Dashboard
```

Feature grid:

```text
Hermes Agent — I give each pod a private assistant with memory, skills, and room to grow.
SOTA Model Rails — I start on Chutes and keep BYOK lanes open for the frontier models you trust.
qmd Retrieval — I keep the vault searchable so agents can pull the right context fast.
Managed Memory — I keep lightweight memory stubs hot so the vessel stays oriented.
Files & Code — I wire in Nextcloud and browser VS Code so your pod has hands, not just words.
Health & Ops — I watch DNS, billing, provisioning, and services so the launch path stays visible.
```

Footer:

```text
© {year} ArcLink. Private AI Infrastructure.
```

## Web Onboarding

The web onboarding page is a single card with Raven's avatar at the top.

Start step heading:

```text
I'm Raven
```

Start body:

```text
I can take you from a few answers to a private ArcLink vessel with a weapons-grade agent, SOTA model rails, memory, tools, and deployment health. Stripe collects email securely at checkout.
```

Start CTA:

```text
Take Me Aboard
```

Loading:

```text
Opening...
```

Questions heading:

```text
Name On The Hatch
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
Starter puts your first ArcLink agent aboard for $35/month. After launch, I can add more agents for $15/month each.
```

CTA:

```text
Paint The Hatch
```

Loading:

```text
Saving...
```

Checkout heading:

```text
Hire My First Agent
```

Checkout body:

```text
I will hand you to Stripe, watch for confirmation, then move your first ArcLink agent from idea to launch queue.
```

CTA:

```text
Hire My First Agent - $35/mo
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

Development-only chip:

```text
Fake adapters active in development. No live charges.
```

## Public Raven Bot

Telegram and Discord use the same state machine and should preserve the same conversational intent.

### Start

Triggered by `/start`, empty message, `start`, or `restart`.

```text
I'm Raven. ArcLink is in range.

I was built for the moment right before a system comes alive. Give me a name and a mission tier, and I will bring a private ArcLink vessel online around you: weapons-grade agents, SOTA model rails, memory, tools, files, and deployment health already wired into the hull.

Stripe collects your email securely at checkout. Send `/name Your Name` and I will put your name on the hatch.
```

Buttons:

```text
Plot Starter Course
Open Comms
```

### Help — Prelaunch

```text
Comms are open.

I will keep this simple until your pod is live. Right now I can bring you aboard, help choose a path, open the secure Stripe handoff, or check where launch stands.

After your first agent is awake, I will hand you the real control panel: Notion, private backups, agent switching, vault access, and deeper system controls in a clean checklist.
```

Buttons:

```text
Take Me Aboard
Plot Starter Course
Run Systems Check
```

### Unknown / Loose Message — Prelaunch

```text
I'm Raven, and I'm online.

No command map needed yet. I can bring you aboard, help choose the first path, or check where your launch stands. Once your agent is awake, I will reveal the deeper controls in a cleaner checklist.
```

Buttons:

```text
Take Me Aboard
Plot Starter Course
Run Systems Check
```

### Email Attempted In Chat

```text
I do not need your email in chat. Stripe handles that securely at checkout. Send `/name Your Name` and I will put your name on the hatch.
```

### Name Captured

Triggered by `/name <Your Name>`.

```text
Name painted on the hatch. Now pick the path. Starter gets your first ArcLink agent aboard for $35/month; after that, I can add more agents for $15/month each.
```

Buttons:

```text
Starter Path - $35/mo
Operator Path
Scale Path
```

### Plan Selected

Triggered by `/plan starter`, `/plan operator`, or `/plan scale`.

```text
Course locked. When you tap Hire My First Agent, Stripe takes the payment handoff and I start moving your pod from idea to launch queue.
```

Buttons:

```text
Hire My First Agent - $35/mo
Change Course
```

### Checkout

Triggered by `/checkout`.

```text
Checkout is ready. Complete the Stripe handoff here; when payment clears, I move your first ArcLink agent into the launch queue.
```

Buttons:

```text
Hire My First Agent
Run Systems Check
```

### Status

```text
I checked the board. Session `{session_id}` is `{status}`. Launch step: `{current_step}`.
Active agent: {agent_label}.
```

Buttons:

```text
Show My Crew
Hire My First Agent
```

## Postlaunch Raven Bot

### Help — Postlaunch

```text
Control panel is open.

Your first agent is aboard, so I can show more of the machinery now. Use the buttons for the common work. If you prefer typed controls, I understand: `/agents`, `/status`, `/connect_notion`, `/config_backup`, and `/cancel`.

Pick one lane and I will keep the steps tight.
```

Buttons:

```text
Show My Crew
Wire Notion
Set Up Backup
```

### Crew Roster

Triggered by `/agents`.

```text
Your ArcLink crew

I keep this roster personal. Every agent here has its own pod, memory rail, tool lane, vault access, and system health tied back to your account.

- {Agent Label}: active
- {Agent Label}: {status}
```

Dynamic buttons:

```text
Take Helm: {Agent Label}
Add Another Agent - $15/mo
```

### No Agent Yet

```text
I do not see your first agent yet. Give me the word and I will put one aboard ArcLink for $35/month. Once that pod is active, we can build a whole crew at $15/month each.
```

Button:

```text
Take Me Aboard
```

### Switch Agent

Triggered by `/agent-<slug>`.

```text
Done. I have {Agent Label} on the rail now. Notion, backup, and system workflows will target that agent until you switch again.
```

Buttons:

```text
Show My Crew
Run Systems Check
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
I have another bay open. Hire the additional agent for $15/month through Stripe, and I will move the new pod into the launch queue.
```

Buttons:

```text
Hire Additional Agent
Back To My Crew
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
Run Systems Check
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

Registered public Telegram commands:

| Command | Description |
| --- | --- |
| `/start` | Begin your ArcLink launch path |
| `/help` | Open the ArcLink action palette |
| `/status` | Check onboarding or pod status |
| `/name <display_name>` | Name your ArcLink workspace |
| `/plan <starter\|operator\|scale>` | Choose starter, operator, or scale |
| `/checkout` | Hire your first ArcLink agent |
| `/agents` | Open your ArcLink crew manifest |
| `/connect_notion` | Connect Notion to your live pod |
| `/config_backup` | Configure private pod backup |
| `/cancel` | Close the active setup workflow |

Hidden/account-state actions:

| Action | Description |
| --- | --- |
| `/add-agent` | Hire an additional agent for $15/month |
| `/agent-<slug>` | Switch active agent |

Discord commands mirror the same set and include a top-level `/arclink message:<text>` for freeform conversation. Discord plan selection uses choices for Starter, Operator, and Scale.

Canonical button labels:

```text
Take Me Aboard
Plot Starter Course
Open Comms
Run Systems Check
Starter Path - $35/mo
Operator Path
Scale Path
Hire My First Agent - $35/mo
Hire My First Agent
Change Course
Show My Crew
Take Helm: {Agent Label}
Add Another Agent - $15/mo
Hire Additional Agent
Back To My Crew
Wire Notion
Set Up Backup
Complete The Hire
Paint The Hatch
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

The ship metaphor should be used sparingly: vessel, hatch, hull, aboard, course, helm, crew, bay, comms, on the rail, in range. Use these as Raven's natural vocabulary, never as costume.

The 100 is founder-tier framing for the first 100 sovereigns aboard. Reserve it for launch comms, founder comms, and a future founder-cohort surface. It is not currently wired into the bot or web copy.
