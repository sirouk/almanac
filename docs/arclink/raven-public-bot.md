# Raven Public Bot

Raven is the public ArcLink launch liaison. Raven offers ArcLink as the system: agents aboard a SOTA agentic harness at the user's fingertips without making them leave the couch. In product terms, that means private agent deployments, model rails, memory, tools, files, workflow setup, and deployment health without making the user manage infrastructure.

The voice should feel like a cyberpunk systems engineer: clear, fast, technically proud, and calm under pressure. The broad inspiration is a brilliant field engineer who can read a broken system under stress and still get people home. Do not imitate show dialogue or quote protected material.

## Default Offer

- First Raven agent: $35/month.
- Additional Raven agents: $15/month each.
- Stripe Checkout collects customer email. Chat onboarding should not ask for email.
- Chutes remains the baked-in primary inference rail unless the user brings another provider.

## Account-Aware Commands

Registered public commands:

- `/start`
- `/help`
- `/status`
- `/name`
- `/plan`
- `/checkout`
- `/agents`
- `/connect_notion`
- `/config_backup`
- `/cancel`

Hidden/account-state actions:

- `/add-agent` is accepted only after the account has an active first deployment. It is surfaced as an `/agents` button, not as a global registered command.
- `/agent-{slug}` switches the active agent target for the account. It is surfaced as an `/agents` roster button, not as a global registered command.

## Button Strategy

Raven should prefer buttons over typed pseudo-actions whenever the platform supports them:

- Plan selection buttons.
- Hire Agent checkout button.
- Agent roster buttons.
- Add Agent checkout button.
- Status and workflow return buttons.

Telegram uses inline keyboard buttons. Discord uses message components. The command catalog remains intentionally small because global slash commands cannot reflect each individual account state.

Telegram webhook registration must include `callback_query` in `allowed_updates`; otherwise inline buttons render but Telegram never delivers taps to ArcLink. `deploy.sh control install|upgrade` registers the public webhook at `/api/v1/webhooks/telegram` and refreshes command buttons so Raven can acknowledge taps and send the next turn.

## Asset Slots

Drop the Raven profile and card artwork into:

- `web/public/brand/raven/raven_pfp.webp`
- `web/public/brand/raven/raven_card.webp`
- `web/public/brand/raven/raven_hero.webp`

If source files arrive as JPG or PNG, keep a copy with the original extension and export optimized WebP names for the web and bot setup workflows.
