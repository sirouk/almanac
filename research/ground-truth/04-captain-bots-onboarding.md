# Ground Truth 04 — Public Captain Bots, Raven Public Flows, Telegram/Discord, Onboarding, Checkout

Date: 2026-05-30. Branch: `arclink`. Source of truth = the code below, read in full.

Owning code files:
- `python/arclink_public_bots.py` (7063 lines) — the Raven public-bot turn engine: command parsing, routing law, onboarding/checkout copy, channel pairing, selected-agent bridge, Crew Training, Academy Mode entry, share approvals/claims, credentials handoff, retire-agent, refuel, agent identity/rename, Raven display name. Canonical entrypoint `handle_arclink_public_bot_turn`.
- `python/arclink_telegram.py` (1559 lines) — Telegram transport + webhook glue + per-chat command-scope planning + Operator Raven Telegram interception.
- `python/arclink_discord.py` (588 lines) — Discord interaction handler, Ed25519 signature verify, interaction dedupe, slash-command parsing, component buttons.
- `python/arclink_public_bot_commands.py` (406 lines) — deploy-time registration of public + operator commands, webhook ensure, active per-chat command-scope refresh (reads running gateway containers).
- `python/arclink_onboarding.py` (903 lines) — the ArcLink-style public onboarding session/state machine + tables (`arclink_onboarding_sessions`, `arclink_onboarding_events`).
- `python/arclink_onboarding_flow.py` (2548 lines) — the OLDER Curator/Raven "Almanac" intake flow (state-machine prompts, model preset selection, Unix-user provisioning, org-profile matching). Distinct system from `arclink_onboarding.py`.
- `python/arclink_onboarding_completion.py` (575 lines) — completion-bundle message builder (password handoff, scrub-on-ack, followup links, remote CLI wrapper) for the OLD flow.
- `python/arclink_onboarding_provider_auth.py` (520 lines) — provider auth specs + Codex device-code + Anthropic Claude-Code PKCE OAuth + Chutes/generic API-key setup (used by the OLD flow).

IMPORTANT structural fact (undocumented split): there are **two parallel onboarding code paths**:
1. The NEW ArcLink public-bot path: `arclink_public_bots.py` + `arclink_onboarding.py`. Button-led, Stripe-checkout-first, `arclink_onboarding_sessions` table, statuses `started/collecting/checkout_open/payment_pending/paid/provisioning_ready/first_contacted/...`. This is what the Captain docs describe.
2. The OLD Curator/Raven "Almanac" path: `arclink_onboarding_flow.py` + `_completion.py` + `_provider_auth.py`. Free-text intake (name → Unix user → purpose → bot platform → bot name → model preset → model id → thinking level → provider credential), operator approval, `request_bootstrap`/`approve_request`, `save_onboarding_session`/`agents`/`agent_identity` tables. Still present, imported, and active for the legacy curator-channel/host-Unix-user onboarding (`/start`, `/status`, `/cancel`, `/verify-notion`, `/setup-backup`, `/retry-contact`, `/ssh-key`). It owns provider OAuth (Codex device flow, Claude-Code PKCE), org-profile match prompts, remote Hermes wrapper setup, and the credential-scrub completion bundle. None of the three target docs describe this second system; it is effectively undocumented in the Captain-facing docs.

---

## A. What is actually implemented today (local-real behavior)

### A1. Telegram transport & webhook (`arclink_telegram.py`)
- Full Bot API client: `telegram_send_message`, `telegram_answer_callback_query`, `telegram_edit_message_text`, `telegram_edit_message_reply_markup`, `telegram_send_chat_action`, `telegram_set_message_reaction`, `telegram_get_me`, `telegram_set_my_commands`, `telegram_get_my_commands`, `telegram_get_updates`, `telegram_set_webhook`.
- `TelegramConfig.from_env` reads `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`, `TELEGRAM_WEBHOOK_URL`, `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_API_BASE`. `is_live` = token present. `validate_live_readiness` requires token+username (+secret if webhook URL set).
- `ensure_arclink_public_telegram_webhook` raises if token or `TELEGRAM_WEBHOOK_SECRET` missing; sets `allowed_updates = ("message", "edited_message", "callback_query")`.
- `handle_telegram_update` is the webhook entry: parses update → Operator interception → `handle_arclink_public_bot_turn` → refreshes per-chat command scope. `parse_telegram_update` carries the raw update JSON (`telegram_update_json`), detects native (non-`arclink:`) callback data, and handles 10 non-text message kinds (photo/video/audio/voice/document/sticker/venue/location/contact/poll) with `[Telegram …]` fallback text.
- Two transports: `LiveTelegramTransport` (urllib to real API) and `FakeTelegramTransport` (in-memory, `enqueue_update`). `run_telegram_polling` is long-polling; **fake mode (no token) requires an injected `FakeTelegramTransport`** or it raises. On `agent_message_queued` it sends a `👀` reaction + typing action before the (usually empty) reply.

### A2. Per-chat command-scope planning (`arclink_telegram.py` + `_commands.py`)
- `arclink_public_bot_telegram_active_command_plan` builds the conflict-free active-chat menu: one Raven control command (preferred order `("raven","arclink","arclink_control")`, last-resort `arclink_ops0..9` then `arclink_ops`) + the active Hermes Agent's command inventory. Legacy Raven names (`ARCLINK_TELEGRAM_LEGACY_RAVEN_COMMAND_NAMES`: agent, agents, cancel, checkout, commands, config_backup, connect_notion, credentials, help, link_channel, name, pair_channel, plan, raven_name, start, status, upgrade_hermes) are stripped from the agent set; `update` is policy-suppressed (`ARCLINK_TELEGRAM_POLICY_SUPPRESSED_AGENT_COMMANDS`).
- Hermes command inventory comes from `_load_hermes_telegram_menu_commands`, which imports `hermes_cli.commands` from a discovered `hermes-agent-src` dir; falls back to `ARCLINK_TELEGRAM_AGENT_FALLBACK_COMMANDS` (33 entries: new, topic, retry, undo, title, branch, compress, rollback, stop, approve, deny, goal, profile, sethome, resume, model, provider, personality, footer, yolo, reasoning, fast, voice, curator, kanban, reload_mcp, reload_skills, restart, usage, insights, debug).
- `refresh_arclink_public_telegram_chat_commands` registers the scope per chat with an in-process cache `_TELEGRAM_CHAT_COMMAND_SCOPE_CACHE`; forced on `switch_agent`.
- `_commands.py:refresh_active_telegram_command_scopes` re-derives per-agent commands by `docker exec`-ing into the running gateway container (`arclink-<deployment>-hermes-gateway-1`, calling `hermes_cli.commands.telegram_menu_commands`), writes scope metadata into `arclink_onboarding_sessions.metadata_json`, and queues an operator drift notification on legacy/hard/suppressed/hidden collisions.

### A3. Operator Raven Telegram interception (`arclink_telegram.py`)
- `_handle_operator_telegram_update` fires BEFORE Captain flow when sender is an allowed operator (`ARCLINK_OPERATOR_TELEGRAM_USER_IDS` + platform/chat checks). Operator commands list `ARCLINK_OPERATOR_TELEGRAM_COMMANDS`: operator_status, agents, fleet_list, worker_probe, user_lookup, pod_repair, upgrade_check, upgrade, pin_upgrade, rollout, action_status, academy_status.
- Read commands dispatch via `dispatch_operator_raven_command` (from `arclink_operator_raven`). Mutating commands require an operator approval code (`strip_operator_approval_code`). Free-form operator text is queued to the operator's one Hermes agent via `_route_operator_free_form_to_agent` → `enqueue_operator_agent_turn` (from `arclink_operator_agent`); falls back to `_operator_raven_intro_reply` if no live operator agent. Live execution honors `ARCLINK_EXECUTOR_ADAPTER` (fake = record-only).

### A4. Discord transport & webhook (`arclink_discord.py`)
- `DiscordConfig.from_env`: `DISCORD_BOT_TOKEN`, `DISCORD_APP_ID`, `DISCORD_PUBLIC_KEY` (must be 64-hex), `DISCORD_TEST_GUILD_ID`, `DISCORD_WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS`. `is_live` requires token+app_id+valid public key.
- `verify_discord_signature` uses Ed25519 (`nacl.signing.VerifyKey`); test sentinels are rejected so an unset config can never become an unauthenticated webhook. `_validate_discord_timestamp` rejects stale (>tolerance, default 300s).
- `_reserve_discord_interaction` dedupes interactions into `arclink_webhook_events` (provider `discord`, unique event_id → `sqlite3.IntegrityError` → "duplicate Discord interaction"). `handle_discord_webhook_request` validates timestamp+signature, reserves, dispatches, marks processed/failed.
- `parse_discord_interaction` handles type 1 PING (PONG), type 2 APPLICATION_COMMAND (slash; maps named options for `email`/`name`/`plan`/`refuel`/`top-up`/`pair-channel`/`link-channel`/`raven-name` into the shared text grammar), type 3 MESSAGE_COMPONENT (button custom_id, strips `arclink:` prefix), and gateway `content` fallback. Component responses for `credentials_stored` return type 7 UPDATE_MESSAGE to scrub the credential message; normal returns type 4.
- `register_arclink_public_discord_commands` PUTs `arclink_public_bot_discord_application_commands()` (guild-scoped if `DISCORD_TEST_GUILD_ID`, else global). `LiveDiscordTransport`/`FakeDiscordTransport` exist.

### A5. The Raven turn engine `handle_arclink_public_bot_turn` (routing law)
Order of dispatch (all reads through `_deployment_context`):
1. Rate limit (`_check_public_bot_rate_limit`: `ARCLINK_PUBLIC_BOT_TURN_LIMIT=20` per `ARCLINK_PUBLIC_BOT_RATE_WINDOW_SECONDS=900`).
2. `_raven_control_rewrite` rewrites `/raven <verb>` (and `/arclink`, `/arclink_control`, `/arclink_ops\d{0,2}`) into the underlying `/command`. Sets `raven_control_requested`.
3. **Bare-slash routing to the active Agent**: if message starts with `/`, the channel has a ready deployment, and the command name is in the active agent command inventory (`_agent_command_names_from_context`), it is queued to the Agent via `_aboard_freeform_reply(source_kind="agent_command")`. `update` is intercepted to `_upgrade_hermes_reply` (ArcLink-managed upgrade rail).
4. Then explicit Raven-owned commands in order: `/raven_name`, help, learn, status, agents, retire-agent (+confirm/cancel workflow), train-crew, academy, whats-changed, rename-agent, retitle-agent, wrapped-frequency, refuel, **active-workflow handler (retire branch)**, agent switch (`/agent <name>` / `/agent-<slug>`), pair/link-channel, add-agent, upgrade-hermes, share-approve/deny/accept, share-claim (nonce), cancel, credentials (+target), credentials-stored, connect_notion, **active-workflow handler (general)**, config_backup.
5. **Aboard routing law** (the key UX rule): once a ready deployment exists, all remaining branches would re-trigger onboarding copy, so non-Raven messages route to the Agent via `_aboard_freeform_reply`. `/start`/`restart`/launch commands map to `_help_reply`. The first non-slash message in a linked channel claims a one-time bridge intro (`_claim_agent_bridge_intro`, event `public_bot:agent_bridge_intro_sent`).
6. Pre-launch onboarding fallbacks: empty/`/start` → greeting + package prompt; `/email` refusal; agent-identity/name/title capture; `/packages` / `/packages standard`; bare `/name` listening lane; `/name X`; `/plan founders|sovereign|scale`; `/checkout`; default "I read you" prompt.

### A6. First-contact / Captain greeting
- Greeting copy is built in `_package_prompt_reply` / `handle_arclink_public_bot_turn`: "`{raven} on the line, Captain.`" or "`Captain {name}, {raven} on the line.`". Raven display name resolved by `_raven_display_name` (channel-scope then user-scope from `arclink_public_bot_identity`, default "Raven").
- Pre-launch package prompt offers Founders Offer ($149/mo) + 3X Scale Plan ($275/mo) by default, or Sovereign ($199) + Scale via `/packages standard`. Direct-checkout buttons (`_ensure_direct_checkout_buttons`) mint per-plan tokens stored as `public_bot_checkout_verifiers` (SHA-256 digests) and build URLs to `/api/v1/onboarding/public-bot-checkout`.

### A7. Channel linking / pairing (`_pair_channel_reply`, `_create_pair_channel_code`)
- `/pair-channel`, `/pair_channel`, `/link-channel`, `/link_channel`, `pair`, `link` all map to one flow. Bare command mints a 6-char code (`PAIR_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"`, `PAIR_CODE_TTL_SECONDS=600`) into `arclink_channel_pairing_codes`, status `open`. Code with arg claims: validates `^[A-Z0-9]{6}$`, checks expiry, same-channel, account mismatch (different `user_id`/`deployment_id`), then `handoff_arclink_onboarding_channel` and sets `claimed`/superseded states. Mirrors `active_deployment_id` and paired-from/to metadata both ways. Records `public_bot:pair_channel_claimed` event.

### A8. Selected-agent command surfaces / helm switching
- `_agent_switch_request`: `/agent`, `/agent <name>`, `/agent-<slug>` (regex `ARCLINK_PUBLIC_BOT_AGENT_SWITCH_RE`) are Raven-owned hard switches, never relayed to Hermes. `_switch_agent_reply` matches against `_deployments_for_user`, requires ready status, stores `active_deployment_id`/`active_agent_label` in session metadata.
- `_agents_reply` (`/agents`) renders the Crew roster with per-agent buttons + Train My Crew / Academy / Credentials / Add Agent.
- Active-chat button rewriting: `_active_raven_callback_command` rewrites e.g. `Show My Crew`→`/raven agents`, `Check Status`→`/raven status` (so taps survive the Agent owning bare slash). `arclink_public_bot_turn_telegram_reply_markup` rewrites only when status is ready; emits `copy_text` buttons (Telegram copy_text) for credentials.

### A9. Crew Training (`/train-crew`)
- `_crew_training_start_reply` → multi-step workflow stored in session metadata under `public_bot_workflow` (`crew_training_role` → mission → treatment → preset → capacity → review). Choices: `CREW_TREATMENT_CHOICES` (captain/peer/coach), `CREW_PRESET_CHOICES` (Frontier/Concourse/Salvage/Vanguard), `CREW_CAPACITY_CHOICES` (sales/marketing/development/life coaching/companionship). Preview via `preview_crew_recipe`, apply via `apply_crew_recipe` (from `arclink_crew_recipes`). Confirm/regenerate/cancel. Applies an additive SOUL.md overlay; "Memories and sessions were not rewritten."

### A10. Academy entry (`/academy`)
- `_academy_training_start_reply`: one-Agent-at-a-time. `all`/`crew` → agent-select list. Named arg → `_academy_major_prompt`. Workflow steps: `academy_training_select_agent` → `choose_major` → `focus` → `sources` → `academy_training_mode_open`. Programs come from `arclink_academy_programs` (`seed_default_academy_programs`, `list_academy_programs`, `get_academy_program`). Opens via `enroll_academy_trainee` + `open_academy_mode`; persists deployment academy status (`_persist_academy_deployment_status`). Captain steering recorded (`focus`, `outside_sources`, `allowed_source_lanes`, weekly review). Tells the Agent to use the `arclink-academy` skill. `graduate` stages the specialist corpus (`stage_crew_academy_agent_training`); cancel/exit ends mode without graduating (`end_academy_mode`). Graduation explicitly states "Live provider/Hermes proof is still required before calling the Agent graduated."
- `_academy_training_walk_prompt`/`walk` path is a legacy crew-walk (train/skip per agent) reachable internally; primary entry is the single-agent flow.

### A11. Share approvals & claims
- `/share-approve <grant>`, `/share-deny <grant>`, `/share-accept <grant>` (`ARCLINK_PUBLIC_BOT_SHARE_ACTION_RE`, grant id `share_[0-9a-f]{32}`) → `_share_grant_action_reply`. Owner approve/deny against `arclink_share_grants` (status `pending_owner_approval`→`approved`/`denied`); recipient accept via `accept_share_grant_for_recipient`. On approve, `queue_share_grant_recipient_notification`. Drive/Code → "read/write Linked resource"; others → "read-only". Audited (`append_arclink_audit`, events `public_bot:share_grant_*`).
- `/arclink_share_accept|share-claim|share_claim <nonce>` (`asn_[0-9a-f]{48}`) → `_share_claim_reply` via `claim_share_nonce_for_recipient`. "Share links expire 12 hours after they are created and can only be claimed once."
- Active-chat buttons rewrite to `/raven approve|deny|accept <grant>`.

### A12. Credentials / entitlement-recovery copy
- `_credentials_reply` reveals dashboard username+password once, from `arclink_credential_handoffs` via `_resolve_revealable_credential_secret`. Refuses if removed/expired/revealed/not-materialized ("I will not invent it"). Emits Telegram `code` entities + copy_text buttons + "I Stored It" (`/credentials-stored`). `_credentials_stored_reply` marks handoff `removed`, audited (`credential_handoff_acknowledged`).
- Entitlement-recovery copy (`_deployment_not_ready_reply`): `entitlement_required`→"Stripe has not cleared the handoff yet - send `checkout`"; `provisioning_failed`→check `/status`; else "I will move when it reaches active." `_need_finished_onboarding_reply` gates all post-launch lanes pre-launch.

### A13. Onboarding state machine (`arclink_onboarding.py`)
- Tables `arclink_onboarding_sessions` + `arclink_onboarding_events`. Channels web/telegram/discord. Statuses: active set `{started, collecting, checkout_open, payment_pending, paid, provisioning_ready, first_contacted}`, terminal set `{payment_cancelled, payment_expired, payment_failed, completed, abandoned, expired}`. 24h TTL (`ARCLINK_ONBOARDING_SESSION_TTL_SECONDS`). `create_or_resume`, `answer_..._question`, `prepare_..._deployment` (reserves `arclink_deployments` with status `entitlement_required`; Scale → 3 deployments via `_plan_agent_count`), `open_..._checkout` (Stripe `create_checkout_session` with metadata), checkout terminal markers, `sync_..._after_entitlement` (advances entitlement gate → `provisioning_ready`), `handoff_..._channel`, `record_..._first_agent_contact`. `_reject_secret_material` blocks any secret-looking values from being stored. Six default Crew profiles (`ARCLINK_DEFAULT_AGENT_PROFILES`: Atlas, Vela, Forge, Lyra, Nova, Sable with themes/accents).

### A14. Checkout / pricing
- Pricing constants in `arclink_public_bots.py`: `FOUNDERS_MONTHLY_DOLLARS=149`, `SOVEREIGN_MONTHLY_DOLLARS=199`, `SCALE_MONTHLY_DOLLARS=275`, `SOVEREIGN_AGENT_EXPANSION_MONTHLY_DOLLARS=99`, `SCALE_AGENT_EXPANSION_MONTHLY_DOLLARS=79`. Plans `{founders, sovereign, scale}` + aliases (starter/founder/limited→founders, operator→sovereign). Direct-checkout plans = `("founders","scale")`. `/checkout` and `/plan` open `_open_first_agent_checkout_turn`. Add-agent (Agentic Expansion) requires configured expansion Stripe price (`sovereign_agent_expansion_price_id`/`scale_agent_expansion_price_id`), checks fleet capacity (`_fleet_capacity_block`). Refuel (`/refuel`, `/top-up`, `/credits`) quotes via `quote_arclink_refuel_topup`.

### A15. Deploy-time registration (`_commands.py`)
- `register_public_bot_commands`: registers public Telegram commands (default + all_private_chats scopes), operator command scopes, ensures webhook, refreshes active per-chat scopes; registers Discord commands. Resilient (per-platform try/except). `main()` is the CLI invoked by `deploy.sh control install|upgrade`.

---

## B. Proof-gated / fake-adapter / local-only behavior

- **`PG-BOTS`** governs ALL live Telegram/Discord delivery, command-menu writes, button callbacks, and the selected-agent bridge. Without tokens, both adapters run in fake mode (`FakeTelegramTransport`, `FakeDiscordTransport`); no network. Live transports require real tokens/keys. This is the dominant gate for this whole subsystem.
- **Selected-agent bridge delivery is asynchronous and proof-gated.** `_aboard_freeform_reply` only `queue_notification(target_kind="public-agent-turn", channel_kind=channel)` + appends `public_bot:agent_turn_queued`. The actual Agent reply is delivered by a separate gateway-bridge worker (out of this subsystem). The webhook returns near-empty text. Streaming is opt-in only: `ARCLINK_PUBLIC_AGENT_BRIDGE_STREAMING=1` (operator opt-in after runtime validation).
- **Per-agent active command scope** depends on `docker exec` into a running `arclink-<deployment>-hermes-gateway-1` container (`_agent_commands_from_gateway_container`). Without a live container it falls back to the static 33-command fallback list. This is effectively gated on a live Hermes pod (`PG-HERMES`).
- **Notion connect (`/connect_notion`)** is "preparation only": records setup intent + callback URL, does NOT verify Notion, install secrets, accept tokens, or support user OAuth. Live verification stays on the dashboard/operator rail and is proof-gated (`PG-NOTION`).
- **Config backup (`/config_backup`)** records the private repo only and explicitly says it does not mint/install/verify the deploy key. Activation/write-check/restore are `PG-BACKUP` (see GAP-013).
- **Upgrade Hermes (`/upgrade-hermes`, `/update`)** never runs a direct `hermes update`; routes to ArcLink-managed upgrade rails (`PG-UPGRADE`/`PG-HERMES`).
- **Academy graduation** stages a plan locally; "Live provider/Hermes proof is still required before calling the Agent graduated" (`PG-HERMES`).
- **Stripe checkout** uses an injected `stripe_client`; fake adapter default for tests. Live checkout/entitlement is `PG-STRIPE`.
- **Provider OAuth in the OLD flow** (`_provider_auth.py`): Codex device-code and Anthropic Claude-Code PKCE make real HTTP calls to OpenAI/Anthropic; these are live external paths used only in the legacy curator flow, gated behind operator approval + provisioning.
- **Share notification delivery to owner/recipient** is local-queued (`notification_outbox`); actual Telegram/Discord delivery + callback proof is `PG-BOTS` (GAP-014/GAP-015).

---

## C. Canonical vocabulary (exact names from code)

Entrypoints: `handle_arclink_public_bot_turn`, `handle_telegram_update`, `handle_discord_interaction`, `handle_discord_webhook_request`, `register_public_bot_commands`, `run_telegram_polling`.

Dataclasses: `ArcLinkPublicBotTurn`, `ArcLinkPublicBotButton`, `ArcLinkPublicBotAction`, `TelegramConfig`, `DiscordConfig`, `ProviderSetupSpec`, `IncomingMessage`/`OutboundMessage`/`BotIdentity` (old flow).

Tables (all in `arclink_control.py`): `arclink_onboarding_sessions`, `arclink_onboarding_events`, `arclink_public_bot_identity` (Raven display name, scope_kind channel/user), `arclink_channel_pairing_codes`, `arclink_share_grants`, `arclink_credential_handoffs`, `arclink_webhook_events` (Discord dedupe), `arclink_deployments`. Old flow: `agents`, `agent_identity`, `onboarding sessions` via `save_onboarding_session`/`refresh_jobs`.

Hosted API routes: `POST /api/v1/webhooks/telegram` → `telegram_webhook`; `POST /api/v1/webhooks/discord` → `discord_webhook`; `GET /api/v1/onboarding/public-bot-checkout` → `public_bot_onboarding_checkout`. Direct-checkout path constant `ARCLINK_PUBLIC_BOT_DIRECT_CHECKOUT_PATH = "/api/v1/onboarding/public-bot-checkout"`.

Commands (registered set, `ARCLINK_PUBLIC_BOT_ACTIONS`): start, help, status, credentials, name, agent_name, agent_title, agent_identity, rename_agent, retitle_agent, wrapped_frequency, plan, checkout, agents, learn, train_crew, academy, whats_changed, refuel, agent, raven_name, connect_notion, config_backup, pair_channel, link_channel, upgrade_hermes, cancel.

Operator Telegram commands: operator_status, agents, fleet_list, worker_probe, user_lookup, pod_repair, upgrade_check, upgrade, pin_upgrade, rollout, action_status, academy_status.

Turn actions (sample): `agent_message_queued`, `switch_agent`, `pair_channel_code`/`pair_channel_claimed`, `share_grant_approved`/`denied`/`accepted`, `share_claim_accepted`, `credentials_revealed`/`credentials_stored`, `crew_training_applied`, `academy_mode_opened`, `prompt_package`, `prompt_checkout`, `show_help`/`show_status`/`show_agents`.

Env vars: `TELEGRAM_BOT_TOKEN`/`_USERNAME`/`_WEBHOOK_URL`/`_WEBHOOK_SECRET`/`_API_BASE`; `DISCORD_BOT_TOKEN`/`_APP_ID`/`_PUBLIC_KEY`/`_TEST_GUILD_ID`/`_WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS`; `OPERATOR_NOTIFY_CHANNEL_PLATFORM`/`_ID`, `ARCLINK_OPERATOR_TELEGRAM_USER_IDS`, `ARCLINK_CURATOR_CHANNELS`, `ARCLINK_PUBLIC_AGENT_BRIDGE_STREAMING`, `ARCLINK_EXECUTOR_ADAPTER`.

Default Raven name: `ARCLINK_PUBLIC_BOT_DEFAULT_RAVEN_NAME = "Raven"`. Ready statuses: `{active, first_contacted}`.

---

## D. Undocumented / newer-than-docs code

1. **The entire OLD curator/Almanac onboarding system** (`arclink_onboarding_flow.py`, `_completion.py`, `_provider_auth.py`) is undocumented in the three Captain docs. It owns: model preset selection (Org-provided/Chutes/Opus/Codex), Unix-user provisioning, org-profile identity matching, provider OAuth (Codex device + Claude-Code PKCE), remote Hermes wrapper (`hermes-<org>-remote-<user>`), `/ssh-key` install, the scrub-on-ack completion password bundle, `/verify-notion`, `/retry-contact`.
2. **Operator Raven Telegram bridge** (`_handle_operator_telegram_update`, free-form → operator Hermes agent) is only lightly noted in raven-public-bot.md; the full command set (12 commands incl. `pin_upgrade`, `rollout`, `action_status`, `academy_status`) and the operator-approval-code mutating gate are newer than the docs.
3. **Academy Mode multi-step flow** (select agent → major → focus → sources → open mode → graduate, with `arclink-academy` skill handoff and `arclink_academy_programs` seeding) is far more developed than any doc. CREATIVE_BRIEF and first-day-user-guide do not mention Academy at all.
4. **Retire-agent workflow** (`/retire-agent`, typed-name confirmation, `_retire_agent_deployment`, cancel pending turns) — undocumented in all three docs.
5. **Refuel / Wrapped frequency / rename-agent / retitle-agent / agent-identity** commands — not in first-day-user-guide; partially in raven-public-bot.md.
6. **Direct-checkout token flow** (`public_bot_checkout_verifiers`, `/api/v1/onboarding/public-bot-checkout`) and per-plan tokenized buttons — undocumented.
7. **3X Scale Plan / Founders Offer** are the live default package-prompt buttons; standard Sovereign/Scale is behind `/packages standard`. Pricing is Founders **$149**, Sovereign **$199**, Scale **$275** (code), but CREATIVE_BRIEF "Package Prompt" example copy still omits/garbles Sovereign vs the live default lanes.
8. **Telegram message-reaction (👀) + typing ack** on queued agent turns, and rich-message kind fallbacks — undocumented.
9. **`/share-accept` and nonce-claim (`asn_…`)** path — raven-public-bot.md documents approve/deny but not accept/claim.

---

## E. Per-doc staleness verdicts

### `docs/arclink/raven-public-bot.md` — staleness: light
Mostly accurate and current on the Raven public-bot contract (active command scope, `/raven` namespace, fallback `/arclink`/`/arclink_control`, callback_query requirement, operator interception). Corrections needed:
- Operator command list is incomplete/slightly off vs code: doc lists `/operator_fleet`, `/rollout_plan <target> --dry-run`; code registers `fleet_list`, `rollout`, plus `pin_upgrade`, `action_status`, `academy_status`, `upgrade`. (`/operator_fleet` appears in the intro-reply copy but is not in `ARCLINK_OPERATOR_TELEGRAM_COMMANDS`.) Reconcile to the real registered set.
- Pricing line says Founders $149 / Sovereign $199 / Scale $275 / expansions $99/$79 — matches code. Keep.
- Does not mention `/share-accept`/nonce-claim, retire-agent, refuel, academy, crew-training, wrapped-frequency, rename/retitle — add a pointer (this doc scopes to commands, so at least list them as account-state actions).
- Mentions `/raven upgrade_hermes` — code maps `/raven upgrade` and `/raven update` to `/upgrade_hermes`; fine.

### `docs/arclink/first-day-user-guide.md` — staleness: heavy
Describes the OLD curator flow (Curator persona, `/retry-contact`, Discord cold-DM confirmation code, Telegram "press Start", remote wrapper, `/verify-notion`) — which is accurate for `arclink_onboarding_flow.py` but **disjoint from the NEW ArcLink Raven public-bot path** the other docs describe. Corrections:
- Reconcile the two onboarding systems: state which path a first-day Captain actually lands in (Stripe-checkout Raven path vs curator host-Unix path). As written it reads as the only path and omits credentials handoff via `/credentials`, `/agents`, Crew Training, Academy, channel pairing entirely.
- Says "Curator" not "Raven" in places; code/brief use "Raven". Align persona name.
- Backup section matches GAP-013 reality (private repo only, durable skip). Notion section matches. Keep those.
- No mention of Crew Training, Academy Mode, retire-agent, refuel, share inbox — add at least pointers.

### `docs/arclink/CREATIVE_BRIEF.md` — staleness: light-to-heavy (copy drift)
Naming/metaphor stack, pricing table, and feature grid are current and match code constants. But the "Public Raven Bot" sample copy blocks have drifted from live strings:
- "Package Prompt" sample lists "Founders is $149/mo … Scale is $275/mo" but omits the live default Sovereign lane behavior and the exact live header "`{raven} on the line, Captain.`" / "`Captain {name}, {raven} on the line.`"; live default prompt buttons are "Founders Offer $149/mo" + "3X Scale Plan $275/mo" (not "Founders $149/mo"/"Scale $275/mo").
- "Help - Postlaunch" and "Help - Prelaunch" sample copy is close but not verbatim to `_help_reply` ("Bridge is open." / "Comms are open."). Mark as creative target vs live string.
- "Plan Selected" sample uses Sovereign; live `/plan` produces founders/sovereign/scale variants — fine as illustrative.
- The brief omits Academy Mode, Crew Training depth, retire-agent, refuel, channel pairing nuance, share accept/claim. As the creative SoT it should at least acknowledge Academy and Crew Training as shipped surfaces (they are heavily implemented).
- "Implementation Status Note" correctly marks live external paths as proof-gated — accurate and should stay.

### `docs/arclink/sovereign-control-node-symphony.md` (skim) — relevant sections accurate
The "Captains And Public Raven" and "Sharing" sections match code intent and correctly state the remaining live work is `PG-BOTS`/`PG-HERMES` and GAP-014/015/016. "Operator Raven And Control" correctly marks the read-only/dry-run slice (GAP-029). This is the truest doc for ground-truth alignment; treat it as the dream-shape reference. One nuance: it says "The current Captain side is comparatively strong" — accurate, but it understates that the legacy curator onboarding flow also still exists in parallel.

---

## F. True current status of GAP-* this subsystem touches

- **GAP-013** (Raven backup prep stops before key setup): status **partial / ux-gap / ops-gap**. Public `/config_backup` records repo as `repo_recorded_pending_key_setup` only; dashboard projects `pending_key_setup`, exposes deploy-key settings URL, can stage a key via CSRF-gated route returning only public key. Live GitHub write/activation/restore remain `PG-BACKUP`. Code confirms (`_config_backup_reply`, `config_backup_repo` workflow).
- **GAP-014** (browser share requests need live broker/adapter proof): proof-gated; local broker/plugin/API contracts present, live workspace + `PG-BOTS` proof outstanding.
- **GAP-015** (share approval can silently wait if owner has no linked public channel): status **proof-gated**. Local dashboard share inbox + `POST /user/share-grants/retry-notification` + no-channel recovery hints exist; queues one `notification_outbox` row after channel link. Live Telegram/Discord delivery + callback proof remains `PG-BOTS`. Raven side (`_share_grant_action_reply`, `queue_share_grant_recipient_notification`) is the local-real half.
- **GAP-016** (Linked copy/duplicate policy): status **real / locally closed**. MCP/plugin/docs aligned. Raven share replies use the same "read/write Linked resource" / "cannot be reshared" language.
- **GAP-029** (Operator Raven not yet full-service control plane): status **open / first slice exists**. Read-only/dry-run operator command layer present (`_handle_operator_telegram_update`, `dispatch_operator_raven_command`, 12 registered commands, free-form → operator Hermes agent). Mutations gated by operator approval code + `ARCLINK_EXECUTOR_ADAPTER` (fake = record-only). Full control plane remains product buildout.
- **GAP-033** (cross-surface experience finish gate needs live proof): status **open / local quality gate exists**. `arclink_surface_contract.py` enforces Captain/Operator Raven copy quality locally; live `PG-BOTS`/`PG-HERMES`/browser proof outstanding.
- **PG-BOTS** (proof gate, not a GAP): Telegram/Discord webhooks, command menus, buttons, delivery, selected-agent bridge — all live external proof for this subsystem rolls up here. Remains unexecuted/authorized-only.
- **PG-HERMES**: live per-agent command-menu discovery (docker-exec into gateway) and academy graduation proof.
- **PG-NOTION / PG-BACKUP / PG-STRIPE / PG-UPGRADE**: touched by `/connect_notion`, `/config_backup`, checkout, `/upgrade-hermes` respectively.

No GAP in this subsystem is falsely "closed": the source-level Captain flows are strong and tested, but every live-delivery and live-verification path is honestly behind a PG gate.
