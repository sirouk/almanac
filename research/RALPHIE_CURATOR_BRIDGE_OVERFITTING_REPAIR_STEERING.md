# Ralphie Steering: Curator Bridge & Hermes Agent Overfitting Repair

## Current Mission

Replace the static, pull-on-demand, silent-fallback architecture that today
governs the ArcLink curator bridge for Telegram and Discord and the Hermes
agent slash-command surface. The destination is a manifest-driven,
push-on-change, fail-loud system in which a Hermes plugin upgrade is
immediately effective on `/slash` commands across every platform, no canned
fallback ever lies to a user about agent state, and the dispatch fabric is
unified across Telegram and Discord.

This file is a mission backlog, not a speculative wishlist. Every item below
is anchored to specific code with file:line references. Ralphie should treat
the code and tests as truth when docs disagree, then update docs and tests to
make the new truth durable.

## Operating Guardrails

- Read `AGENTS.md` before changing deploy, onboarding, service, runtime, or
  knowledge code.
- Do not read `arclink-priv/`, user homes, secret files, live token files, or
  private runtime state unless a focused fix requires a specific non-secret
  path and the operator explicitly authorizes it.
- Do not print, log, commit, or quote secrets. Avoid argv/env exposure of
  bootstrap tokens, API keys, bot tokens, OAuth data, deploy keys, and `.env`
  contents.
- Do not edit Hermes core. Use ArcLink wrappers, plugins, hooks, generated
  config, services, or docs.
- Do not run `./deploy.sh upgrade`, `./deploy.sh install`, live Stripe,
  Cloudflare, Tailscale, Telegram, Discord, or host-mutating production flows
  unless the operator explicitly asks during this mission.
- **No fallbacks.** Every existing `except Exception → return default`, every
  hardcoded canned response, every opt-in degraded knob is in scope for
  removal. Replace each with structured error events surfaced to the
  operator dashboard and, where user-facing, honest "agent is updating,
  retry in N seconds" messaging.
- **No overfitting.** Slash commands, argument shapes, and platform scopes
  live in YAML manifests merged from curator + plugins. New plugin command =
  manifest entry = automatic registration on every platform with zero edits
  to `arclink_public_bots.py`.
- **Plugin upgrades MUST be immediately effective.** Pull-on-demand is
  forbidden; lifecycle events drive push-based re-registration with both
  Telegram (`setMyCommands` per scope) and Discord (`PUT /applications/{app}/
  commands`).
- Prefer narrow, tested fixes over broad rewrites. Add regression tests for
  every removed fallback and every newly enforced contract before deleting
  the old path.
- Follow the Mandate of Inquiry: curiosity over closure. Before filling any
  logic hole, name three plausible designs, the data still unread, and the
  operator decisions outstanding.
- Never convert an unverified external/tool/data claim into product truth.
- Preserve transparency of inference in handoffs.

## Mission Success Criteria

- The four `plugins/hermes-agent/*` plugins (`drive`, `code`, `terminal`,
  `arclink-managed-context`) can advertise commands via YAML manifest, and
  adding or removing a command in a plugin manifest causes the Telegram
  menu and the Discord application commands to update without any code
  change in `python/arclink_public_bots.py` or
  `python/arclink_discord.py`.
- Plugin install/upgrade/uninstall emits a lifecycle event; the control
  plane reacts within seconds by re-registering commands on every connected
  platform. The operator dashboard surfaces the diff per deployment.
- Every fallback path listed in the inventory is gone:
  - `ARCLINK_TELEGRAM_AGENT_FALLBACK_COMMANDS`
  - `ARCLINK_PUBLIC_AGENT_QUIET_FALLBACK`
  - `_telegram_fallback_text_for_kind`
  - `"Sent to your active agent."` canned Discord string
  - `{"type": 1}` PONG ACK fallback for unmapped Discord interaction types
  - Hardcoded `streaming.transport = "edit"` in the bridge
  - `arclink_ops0..9` auto-generated raven-name conflict resolution
- Every silent `except Exception` in the bot/bridge/notification path
  either propagates or emits a structured failure event to a new
  `arclink_bot_failures` (or extended telemetry) surface visible on the
  operator dashboard.
- A `BotEvent` boundary dataclass normalizes Telegram updates and Discord
  interactions; the dispatcher operates on the unified type and no longer
  branches on `platform == "telegram"` / `"discord"` for command parsing.
- Bridge stdin payload carries an explicit `schema_version` with capability
  negotiation; mismatched versions raise a hard error and alert.
- Regression tests cover every removed fallback and every new manifest path.

## Phase Strategy

Seven slices, ordered to minimize blast radius. Earlier slices stand alone;
later slices depend on the data shapes earlier ones introduce.

1. **Telemetry and visibility foundation** — additive only. Wires structured
   failure events so we can rip out fallbacks safely.
2. **Fallback rip-out** — deletion-only. Every item shrinks the codebase and
   makes the system honest. No new abstractions required.
3. **Command manifest schema** — additive only. Defines the YAML shape and
   the loader/validator. Parallel to existing dispatch.
4. **Manifest-driven menus** — replaces `ARCLINK_PUBLIC_BOT_ACTIONS` as
   runtime source of truth for both platforms.
5. **Push-on-change command sync** — plugin lifecycle events trigger
   immediate re-registration. This is the slice that finally makes plugin
   upgrades "immediately effective."
6. **`BotEvent` boundary** — unifies Telegram + Discord dispatch behind a
   single normalized event type.
7. **Bridge payload v2** — versioned schema with capability negotiation;
   deletes the hardcoded `streaming.transport = "edit"`.

Within each slice, do this loop:

1. Confirm the current behavior in code and tests.
2. For each detected hole, write the possibility set: at least three
   distinct plausible fixes when three exist, plus the unknowns that would
   change the choice.
3. Invite operator choice on the blocked questions at the end of this doc
   before implementing in slices that depend on them.
4. Add focused regression coverage that pins the current (overfit / falling-
   back) behavior, so the deletion is a real fix and not a silent regression.
5. Implement the change without widening scope.
6. Run the narrow validation floor.
7. Update the closest docs only after behavior exists.

## Surface Inventory (Mapping Reference)

Anchor points for everything below.

- **Ingress (control plane):**
  - `python/arclink_telegram.py` (1068 lines) — webhook, transport,
    command-scope refresh.
  - `python/arclink_discord.py` (580 lines) — interaction parser, transport.
  - `python/arclink_public_bots.py` — `ARCLINK_PUBLIC_BOT_ACTIONS` static
    tuple at line 167; central dispatcher
    `handle_arclink_public_bot_turn` at line 2976; raven-control rewrite
    at line 397.
  - `python/arclink_public_bot_commands.py` — Telegram menu loader
    integration with `hermes_cli.commands.telegram_menu_commands`.
  - `python/arclink_curator_onboarding.py`,
    `python/arclink_curator_discord_onboarding.py`,
    `python/arclink_onboarding_flow.py` — curator-side onboarding flows.
- **Bridge (per-deployment):**
  - `python/arclink_public_agent_bridge.py` (456 lines) — runs inside the
    customer's Hermes container via `docker exec -i`, fed JSON over stdin.
  - `python/arclink_notification_delivery.py` —
    `_run_public_agent_gateway_turn` at line 404,
    `_public_agent_quiet_fallback_enabled` at line 475,
    `_deliver_public_agent_turn` at line 543.
- **Hermes plugin layer (per-deployment):**
  - `plugins/hermes-agent/drive/plugin.yaml` (manifest only, no commands)
  - `plugins/hermes-agent/code/plugin.yaml` (manifest only, no commands)
  - `plugins/hermes-agent/terminal/plugin.yaml` (manifest only, no commands)
  - `plugins/hermes-agent/arclink-managed-context/` (1786 lines in
    `__init__.py`; registers `pre_llm_call`, `pre_tool_call`, and the
    `start` command via `ctx.register_hook` / `ctx.register_command`).
- **Webhook routes:** `/api/v1/webhooks/telegram` and
  `/api/v1/webhooks/discord` (registered in `arclink_hosted_api.py`).

## Fresh Pass: 2026-05-12 Ground Truth Updates

This section records the second-pass audit against the current checkout
(`arclink` branch at `71a151a`). It supersedes stale line numbers above
where the code moved.

- **Native Hermes is already more dynamic than the ArcLink public bridge.**
  The pinned Hermes gateway source under
  `arclink-priv/state/hermes-docs-src/gateway/platforms/telegram.py:1086-1105`
  derives Telegram menus from `hermes_cli.commands.telegram_menu_commands`.
  Discord does the same for built-ins and plugin commands in
  `arclink-priv/state/hermes-docs-src/gateway/platforms/discord.py:2928-3026`
  using `COMMAND_REGISTRY` and `_iter_plugin_command_entries`. ArcLink must
  not edit Hermes core; it should consume or mirror this registry contract
  through an ArcLink-owned manifest/sync layer.
- **ArcLink's public Raven bridge still bypasses that dynamic contract.**
  The curator commands are still hand-authored in
  `python/arclink_public_bots.py:167-317`, rendered by
  `arclink_public_bot_telegram_commands` at line 735 and
  `arclink_public_bot_discord_application_commands` at line 742, then parsed
  by hand-coded Discord branches in `python/arclink_discord.py:328-337`.
  This is the core overfitting defect.
- **Telegram has a partial pull path, but it fails into fiction.**
  `python/arclink_telegram.py:350-393` tries to import Hermes command data,
  catches `Exception`, then returns `ARCLINK_TELEGRAM_AGENT_FALLBACK_COMMANDS`
  with source `"fallback"`. That must become a hard, visible command-sync
  failure; never replace an unknown live menu with a static old menu.
- **Discord has no public-bridge equivalent of Hermes plugin auto-sync.**
  Hermes native Discord can auto-register plugin commands, but ArcLink's
  hosted Discord webhook still exposes only the static public bot command
  payload. Plugin command changes therefore cannot be immediately effective
  for the public Raven bridge until Slice 4/5 land.
- **Raven control-name collision handling still invents command names.**
  `python/arclink_public_bots.py:143` accepts `/arclink_ops\d{0,2}` and
  `python/arclink_telegram.py:450-465` auto-selects `arclink_ops0..9` when
  `raven`, `arclink`, and `arclink_control` collide with agent commands.
  This violates the no-fallback rule; collisions should block sync and alert
  the operator with exact conflicts.
- **Bridge and delivery failures still have degraded-success paths.**
  `python/arclink_discord.py:438` emits `"Sent to your active agent."` for an
  empty async payload, `python/arclink_discord.py:544` PONG-ACKs unknown
  interaction types, and `python/arclink_notification_delivery.py:475-575`
  retains `ARCLINK_PUBLIC_AGENT_QUIET_FALLBACK` plus a `hermes chat -Q`
  degraded path. These are priority deletion targets before any UX polish.
- **The dashboard plugin layer has adjacent fallback language.**
  `plugins/hermes-agent/terminal/dashboard/plugin_api.py:651` returns a
  `"fallback": "polling"` response, and the dashboard plugin APIs contain
  broad exception-to-empty-result patterns. These are not the Raven bridge's
  slash-command contract, but they should be audited in a follow-on
  dashboard-plugin honesty pass because the operator's "no fallbacks" rule
  applies there too.
- **The existing `drive`, `code`, and `terminal` Hermes plugins are
  dashboard UI plugins, not command plugins.** Their `plugin.yaml` files
  intentionally declare `provides_commands: []`. Treat them as dashboard
  capability manifests unless the operator chooses to add explicit commands
  such as `/drive`, `/code`, or `/terminal`.

### Fresh-Pass Implementation Bias

Start implementation with a small no-fallback hardening PR before the full
manifest migration:

1. Add command-sync telemetry and last-error state.
2. Replace the Telegram fallback menu with "retain previous live platform
   menu, record sync failure, alert operator." Do not return a synthetic
   replacement list.
3. Remove the Discord canned success string and unknown-interaction PONG
   fallback.
4. Remove `ARCLINK_PUBLIC_AGENT_QUIET_FALLBACK` and the `hermes chat -Q`
   degraded path.
5. Then land the manifest schema and push-on-change worker.

This order makes the system honest immediately while preserving the larger
architecture migration path.

## Fallback & Overfitting Inventory

Each entry is a target for deletion in Slice 2 or replacement in Slice 4.

| # | Location | Anti-pattern |
|---|----------|--------------|
| F1 | `python/arclink_telegram.py:42-74` | `ARCLINK_TELEGRAM_AGENT_FALLBACK_COMMANDS` — 31-entry static menu shown when Hermes load fails. Lies about what works. |
| F2 | `python/arclink_telegram.py:385-393` | Broad `except Exception` returns the F1 fallback list with `logger.debug` only. Silent. |
| F3 | `python/arclink_telegram.py:754-767` | `_telegram_fallback_text_for_kind` emits `[Telegram photo]`/`[Telegram video]` placeholders, stripping media context the agent needs. |
| F4 | `python/arclink_telegram.py:886` | `setMyCommands` failure swallowed; no operator alert. |
| F5 | `python/arclink_telegram.py:1067-1068` | Update-processing failure swallowed in polling loop. |
| F6 | `python/arclink_telegram.py:78` + `:450-465` | Raven-name candidate list + `arclink_ops0..9` auto-numbered fallback. |
| F7 | `python/arclink_discord.py:237` | `verify_discord_signature` returns `False` on any exception; no logging. |
| F8 | `python/arclink_discord.py:328-342` | Hand-coded `if name == "email"/"name"/"plan"/...` Discord slash parser. New commands fall through to `/start`. |
| F9 | `python/arclink_discord.py:438` | Canned `"Sent to your active agent."` masks empty payload. |
| F10 | `python/arclink_discord.py:539-544` | `{"type": 1}` PONG ACK fallback for unmapped interaction types. |
| F11 | `python/arclink_public_agent_bridge.py:103-104` | Hardcoded `streaming.transport = "edit"`. |
| F12 | `python/arclink_public_agent_bridge.py:105-106` | Bridge gateway-defaults helper swallows exceptions silently. |
| F13 | `python/arclink_public_agent_bridge.py:188`, `:212` | Raw-Telegram-update replay swallows parse failures and falls back to a synthetic `MessageEvent` that strips media. |
| F14 | `python/arclink_notification_delivery.py:475-489` | `ARCLINK_PUBLIC_AGENT_QUIET_FALLBACK` env knob — docstring itself admits this hides bridge failures. |
| F15 | `python/arclink_notification_delivery.py:563-575` | `hermes chat -Q` degraded delivery path used by F14. |
| F16 | `python/arclink_public_bots.py:167-317` | `ARCLINK_PUBLIC_BOT_ACTIONS` static tuple — every new command requires a code change. |
| F17 | `python/arclink_public_bots.py:143` | `ARCLINK_PUBLIC_BOT_RAVEN_CONTROL_FALLBACK_RE = re.compile(r"^/arclink_ops\d{0,2}$")` — auto-generated control name regex. |
| F18 | `python/arclink_public_bot_commands.py:83`, `:125`, `:281`, `:289` | Broad excepts swallow command-registration failures across platforms. |
| F19 | `python/arclink_telegram.py:37` | `ARCLINK_TELEGRAM_COMMAND_LIMIT = 100` — module constant, not tunable. |

## Priority 1: Telemetry & Visibility Foundation

Additive slice. No behavior change for the happy path. Required before any
fallback removal so deletions surface real failures to operators.

- [ ] Add `arclink_bot_telemetry.py` with `emit_bot_failure(stage, platform,
      deployment_id, error_kind, detail, severity)` and a corresponding
      SQLite table (or extension of existing failure-event surface).
  - Problem: 19+ silent `except Exception` blocks across
    `arclink_telegram.py`, `arclink_discord.py`,
    `arclink_public_agent_bridge.py`, `arclink_public_bot_commands.py`, and
    `arclink_notification_delivery.py` swallow failures with `logger.debug`
    or `logger.warning` only.
  - Expected fix: every existing broad-except site wires a telemetry emit
    before deciding what to do next. Severity tiers: `transient`,
    `deployment-down`, `contract-mismatch`, `signature-failure`,
    `silent-degradation-detected`.
  - Tests: unit-test that simulating a failure emits exactly one row with
    the right `stage` and `severity`.
  - Tests: dashboard renders the row with unack badge.

- [ ] Persist `last_command_sync` per `(deployment_id, platform)` —
      timestamp, manifest hash, command count, and last error.
  - Problem: `arclink_telegram.py:886` swallows `setMyCommands` errors.
    Operators have no idea whether the live menu matches the deployment's
    intended state.
  - Expected fix: new table `arclink_bot_command_sync_state`. Every menu
    refresh writes a row; dashboard renders staleness and last-error.
  - Tests: failure → row present with error string; success → hash matches
    computed manifest hash.

- [ ] Classify bridge contract failures.
  - Problem: `_run_public_agent_gateway_turn` returns `(False, error_str)`;
    every caller treats failure identically.
  - Expected fix: `BridgeFailure` enum: `container_unreachable`,
    `schema_mismatch`, `auth_rejected`, `runtime_exception`,
    `timeout`. Each tier maps to a dashboard severity and a user-facing
    message template.
  - Tests: each enum value round-trips from bridge stdout to dashboard row.

- [ ] Operator dashboard surface: "Bot Health" tab.
  - Per deployment: live command-sync state per platform; recent
    `arclink_bot_failures` rows with severity filter; "force re-sync"
    affordance.
  - Tests: web test that renders the tab with seeded failure rows.

## Priority 2: Fallback Rip-Out

Deletion-only. Each item is a self-contained PR that shrinks the codebase.
Slice 1 must be in flight first so failures don't disappear.

- [ ] Delete `ARCLINK_TELEGRAM_AGENT_FALLBACK_COMMANDS` (F1, F2).
  - Problem: `arclink_telegram.py:42-74` and `:393` substitute a static
    31-entry menu when Hermes can't be loaded.
  - Expected fix: on load failure, return an empty list and emit a
    `contract-mismatch` telemetry row. The Telegram scope refresh skips
    this deployment until the next successful load; dashboard shows
    "menu stale, last refresh failed at {ts}".
  - Tests: simulate load failure → empty list returned + telemetry row
    fired + scope refresh skipped (existing scope retained, not replaced).
  - Acceptance: `grep -n "ARCLINK_TELEGRAM_AGENT_FALLBACK_COMMANDS" python/`
    returns no hits.

- [ ] Delete `ARCLINK_PUBLIC_AGENT_QUIET_FALLBACK` and the `hermes chat -Q`
      degraded path (F14, F15).
  - Problem: `arclink_notification_delivery.py:475-489` admits in its own
    docstring that this knob hides bridge failures. The degraded path
    strips streaming, reactions, command handling, and platform formatting.
  - Expected fix: remove the env knob, `_public_agent_quiet_fallback_enabled`,
    and the `hermes chat -Q` fallback branch at line 576. Bridge failure
    returns the structured error to the caller, which uses
    `_deliver_public_bot_user` to send an honest "agent is updating, retry
    in N seconds" message with a deep link to the deployment status.
  - Tests: simulate bridge failure → `hermes chat -Q` is never invoked +
    user receives the structured message + telemetry row at severity
    `deployment-down`.
  - Acceptance: `grep -n "ARCLINK_PUBLIC_AGENT_QUIET_FALLBACK" python/`
    returns no hits and `grep -n "hermes chat -Q" python/` returns no hits.

- [ ] Delete `_telegram_fallback_text_for_kind` placeholder strings (F3).
  - Problem: `arclink_telegram.py:754-767` replaces missing captions with
    `[Telegram photo]` / `[Telegram video]` etc., stripping the media
    context the agent needs.
  - Expected fix: surface `media_kind` and `has_caption: false` through the
    `BotEvent` (Slice 6); let the agent decide whether to ask for context.
    Until Slice 6 lands, leave the text empty and add a `media_kind` field
    to the existing event dict.
  - Tests: a photo with no caption produces an event with
    `media_kind="photo"`, `text=""`, and no placeholder.

- [ ] Delete the canned `"Sent to your active agent."` Discord string (F9).
  - Problem: `arclink_discord.py:438` emits this when payload content is
    empty, masking a real delivery state.
  - Expected fix: refactor the Discord interaction handling to always defer
    (`type: 5` DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE) when the bridge work is
    async, and to use Discord followup messages with real content once the
    bridge returns. No canned content string.
  - Tests: empty bridge reply → DEFERRED response + followup with the
    actual bridge content; no occurrence of the canned string.
  - Acceptance: `grep -n "Sent to your active agent" python/` returns no
    hits.

- [ ] Delete the `{"type": 1}` PONG ACK fallback (F10).
  - Problem: `arclink_discord.py:544` silently ACKs any interaction type
    not explicitly handled, masking protocol drift.
  - Expected fix: raise `ArcLinkDiscordError("unhandled interaction
    type={itype}")`, emit a `contract-mismatch` telemetry row, let the
    webhook return 4xx. Discord retries once and then drops; the dashboard
    will show the failure.
  - Tests: unknown interaction type → exception raised + telemetry row.

- [ ] Delete the hardcoded `streaming.transport = "edit"` in the bridge
      (F11, F12).
  - Problem: `arclink_public_agent_bridge.py:103-104` pins transport mode
    regardless of plugin or operator config; `:105-106` swallows the
    `setattr` exception.
  - Expected fix: leave `streaming.transport` empty if unset and let Hermes
    pick its own default. If a deployment wants a specific transport, set
    it via plugin config or the deployment's gateway config, not the
    bridge. Remove the broad except.
  - Tests: bridge invocation with no transport-override env leaves
    `streaming.transport` at Hermes' default.

- [ ] Delete the raven-control auto-generated `arclink_ops0..9` fallback
      (F6, F17).
  - Problem: `arclink_public_bots.py:131` and `arclink_telegram.py:454-463`
    auto-generate ugly fallback names when the candidate list collides
    with agent commands.
  - Expected fix: collision detection still runs, but on collision raise a
    hard error to the operator dashboard with the conflict list and the
    operator's options. Require the operator to pick a name via the
    dashboard or `/raven-name` command.
  - Tests: induce collision → no auto-generated name + dashboard alert
    fires.

- [ ] Replace broad excepts in `arclink_public_bot_commands.py:83, 125, 281,
      289` with classified failures (F18).
  - Problem: command-registration failures across platforms are swallowed
    to "keep registering other platforms" — the comment is explicit about
    the trade-off.
  - Expected fix: keep the keep-going semantics but emit a telemetry row
    per failure with `severity=deployment-down` and the failing platform.
  - Tests: simulate a registration failure → other platforms continue +
    telemetry row fired per failure.

- [ ] Replace `ARCLINK_TELEGRAM_COMMAND_LIMIT = 100` constant (F19) with a
      tunable read from config.
  - Expected fix: read from `ARCLINK_TELEGRAM_COMMAND_LIMIT` env or config
    file, default 100, validated 1-100 (Telegram API ceiling).

## Priority 3: Command Manifest Schema

Additive. Defines the YAML shape and the loader. No runtime path swaps yet.

- [ ] Define `arclink_command_manifest.py` with dataclasses:
      `CommandArgument`, `CommandManifestEntry`, `CommandManifest`.
  - Schema (YAML):
    ```yaml
    schema_version: 1
    commands:
      - name: status
        descriptions:
          en: "Check onboarding or pod status"
        platforms: [telegram, discord]
        scopes:
          telegram: [all_private_chats, all_group_chats]
          discord: [dm, guild]
        handler: arclink.public_bots.handle_status
        args:
          - name: detail
            type: choice
            choices: [brief, full]
            required: false
        owner: curator       # or "plugin:arclink-managed-context"
        version: 1
        precedence: 100      # higher wins on collision
    ```
  - Functions: `load_manifest(path) -> CommandManifest`,
    `merge_manifests(*manifests) -> CommandManifest`,
    `validate(manifest) -> list[ManifestError]`,
    `manifest_hash(manifest) -> str`.
  - Tests: round-trip YAML; conflict detection (two manifests claim
    `name=status` with `owner` differing) honors `precedence` and reports
    the loser; validation rejects unknown `type`, empty descriptions,
    invalid scope.

- [ ] Migrate `ARCLINK_PUBLIC_BOT_ACTIONS` to
      `config/arclink_curator_commands.yaml`.
  - Expected fix: write a one-time migration script that produces the
    curator manifest from the existing tuple. Both sources coexist during
    Slice 3; consistency test asserts they're equivalent.
  - Tests: parity test — rendering the manifest produces the same Telegram
    menu list and Discord application commands as the live tuple.

- [ ] Extend `plugins/hermes-agent/*/plugin.yaml` to allow full command
      definitions or a `commands_file` reference.
  - Today's `provides_commands: [start]` becomes:
    ```yaml
    provides_commands:
      - name: start
        descriptions: { en: "Open the ArcLink action palette" }
        platforms: [telegram, discord]
        scopes: { telegram: [all_private_chats], discord: [dm] }
        handler: arclink_managed_context.start
        owner: "plugin:arclink-managed-context"
        precedence: 50
    ```
  - Backwards-compatible: a bare string list still parses as
    name-only entries, but a `contract-mismatch` telemetry row fires
    asking the plugin to upgrade. (This is not a fallback; it's an explicit
    migration warning surfaced to operators.)
  - Tests: legacy `[start]` list parses; full inline entries parse;
    `commands_file` reference resolves relative to plugin dir.

## Priority 4: Manifest-Driven Menus

Swap the runtime source of truth.

- [ ] Telegram menu generation reads the merged manifest.
  - Problem: `arclink_telegram.py:396` `arclink_public_bot_telegram_agent_
    commands` and `arclink_public_bots.py:723` `arclink_public_bot_
    telegram_commands` both rebuild menus from
    `ARCLINK_PUBLIC_BOT_ACTIONS`.
  - Expected fix: both functions accept a `CommandManifest`, default to the
    merged manifest loaded from
    `config/arclink_curator_commands.yaml` + all installed plugin manifests
    for that deployment. The Hermes-agent menu loader becomes a plugin
    manifest source itself.
  - Tests: add a synthetic plugin manifest with a new command; assert it
    appears in the generated Telegram menu list with the correct scope.

- [ ] Discord application commands generation reads the merged manifest.
  - Problem: `arclink_public_bots.py:736`
    `arclink_public_bot_discord_application_commands` reads from
    `ARCLINK_PUBLIC_BOT_ACTIONS`.
  - Expected fix: rewrite to consume the merged manifest. Argument types
    map: `string→3`, `choice→3+choices[]`, `integer→4`, `boolean→5`,
    `user→6`, `channel→7`.
  - Tests: same plugin manifest → command appears in Discord registration
    payload with options.

- [ ] Discord interaction parser reads the merged manifest.
  - Problem: `arclink_discord.py:328-342` hardcodes
    `if name == "email"/"name"/"plan"/"pair-channel"/"link-channel"/
    "raven-name"` branches.
  - Expected fix: parse interactions by looking up the command in the
    manifest and using its `args[]` schema to drive option extraction. The
    parser returns `(command_name, args_dict, raw_text)`.
  - Tests: feed an interaction for a new plugin command; assert the
    dispatcher routes correctly with the expected args dict and no code
    change in `arclink_discord.py`.

- [ ] Delete `ARCLINK_PUBLIC_BOT_ACTIONS`.
  - Acceptance: `grep -n "ARCLINK_PUBLIC_BOT_ACTIONS" python/` returns no
    hits.
  - The tuple at `arclink_public_bots.py:155-317` is removed in favor of
    `config/arclink_curator_commands.yaml`.

## Priority 5: Push-on-Change Command Sync

This is the slice that finally makes plugin upgrades immediately effective.

- [ ] Add `arclink_plugin_lifecycle.py` with `PluginLifecycleEvent` enum
      (`installed`, `upgraded`, `uninstalled`, `manifest_changed`) and a
      durable queue (`arclink_plugin_events` table).
  - Problem: today there is no signal when a plugin changes; menu refresh
    is pulled on the next webhook (and often falls back silently).
  - Expected fix: `deploy.sh` plugin operations emit lifecycle events; the
    dashboard plugin manager emits events; the bridge inside the deployment
    container can emit events back through the agent-control plane.
  - Tests: each emission path writes the expected row with deployment_id,
    plugin name, version, manifest hash, and event kind.

- [ ] Command-sync worker drains the queue and re-registers immediately.
  - Worker reads the merged manifest, computes the platform-specific
    payload, and calls:
    - Telegram: `setMyCommands` per scope (`default`, `all_private_chats`,
      `all_group_chats`, `all_chat_administrators`).
    - Discord: `PUT /applications/{app_id}/commands` (global) and/or
      `PUT /applications/{app_id}/guilds/{guild_id}/commands` (guild) —
      see open question 2.
  - Hash-based idempotency: skip re-registration if `manifest_hash` matches
    `last_command_sync_state.manifest_hash` for that
    `(deployment_id, platform, scope)`.
  - Tests: simulate a plugin install with a fake transport; assert the
    transport receives the expected commands list and the sync state row
    updates.

- [ ] Dashboard "Bot Health" tab gains command diff view and force-resync.
  - Per deployment: rendered diff between "manifest expects" and
    "platform reports" command lists. A `Re-sync` button enqueues a
    manifest-changed event.
  - Tests: web test that injects a divergence and renders the diff.

- [ ] Document the contract in `docs/AGENT_PLUGIN_LIFECYCLE.md`.
  - When is a plugin "installed" vs "available"? What user action triggers
    a re-sync? What's the SLA between event and live menu update?

## Priority 6: `BotEvent` Boundary

Unify Telegram and Discord dispatch.

- [ ] Define `arclink_bot_event.py` with `BotEvent` dataclass:
  ```python
  @dataclass(frozen=True)
  class BotMedia:
      kind: Literal["photo", "video", "audio", "document", "voice", "sticker"]
      file_id: str
      mime_type: str | None
      size_bytes: int | None
      original_caption: str | None

  @dataclass(frozen=True)
  class BotEvent:
      platform: Literal["telegram", "discord"]
      deployment_id: str
      channel_id: str
      user_id: str
      chat_type: Literal["dm", "group", "supergroup", "channel"]
      command: str | None         # parsed slash command name, no "/"
      args: dict[str, Any]        # parsed args per manifest schema
      text: str                   # raw text for freeform messages
      media: tuple[BotMedia, ...]
      message_id: str | None
      reply_to_message_id: str | None
      display_name: str
      received_at: str            # ISO-8601 UTC
      raw: Mapping[str, Any]      # original platform payload, frozen
  ```
- [ ] `parse_telegram_update` produces `BotEvent`.
- [ ] `parse_discord_interaction` produces `BotEvent`.
- [ ] `handle_arclink_public_bot_turn` operates on `BotEvent` only.
- [ ] Bridge payload is computed from `BotEvent` only; the bridge stops
      receiving raw Telegram update JSON and instead receives a versioned
      `BotEvent` (this dovetails with Slice 7).
- [ ] Delete `_telegram_fallback_text_for_kind` callers (already deleted in
      Slice 2; this slice closes the last reference path).
- Tests: round-trip a Telegram update and a Discord interaction through
  the parsers and assert structural equality of the produced `BotEvent`s
  for matching scenarios (same command, same args, same media kind).

## Priority 7: Bridge Payload v2 + Capability Negotiation

- [ ] Define bridge payload v2 (stdin):
  ```json
  {
    "schema_version": 2,
    "bot_event": { ... },
    "deployment": { "id": "...", "prefix": "..." },
    "auth": { "bot_token": "...", "scoped_secret": "..." },
    "capabilities_requested": {
      "streaming": true,
      "media_passthrough": true,
      "reactions": true,
      "edit_transport": "auto"
    }
  }
  ```
- [ ] Define bridge response v2 (stdout):
  ```json
  {
    "schema_version": 2,
    "ok": true,
    "accepted_capabilities": ["streaming", "reactions"],
    "rejected_capabilities": [
      { "name": "media_passthrough", "reason": "hermes_version<X.Y" }
    ],
    "outcome": "delivered",
    "reply_id": "...",
    "errors": []
  }
  ```
- [ ] Negotiation rule: if response `schema_version != requested`, control
      plane raises `BridgeFailure.schema_mismatch`, alerts the dashboard,
      and surfaces an honest "agent needs upgrade" message to the user.
      No silent downgrade to v1.
- [ ] Bridge default for `streaming.transport` becomes `auto`; Hermes picks
      based on the runtime. Operator config can override; the bridge never
      hardcodes a value.
- [ ] Tests: v1 client + v2 bridge → response carries v2 schema_version,
      control plane treats it as schema_mismatch and alerts.
      v2 client + v1 bridge → control plane treats v1 response as
      schema_mismatch and alerts. v2 ↔ v2 succeeds with capability
      negotiation reflected in telemetry.

## Validation Floor

For each slice, before declaring it landed:

- **Unit:** every new module has direct unit coverage. Every deleted
  fallback has a regression test that previously asserted the fallback
  fired and now asserts it does not.
- **Integration:** the slash command path is exercised end-to-end with the
  fake Telegram + Discord transports, including a path where a synthetic
  plugin manifest adds a new command.
- **Telemetry:** every failure mode that the slice introduces or surfaces
  is asserted to emit exactly one `arclink_bot_failures` row at the
  expected severity.
- **Dashboard:** for slices 1, 5, and 7 — a web test asserts the relevant
  surface renders the new state.
- **Live proof gate (Slice 5 onwards):** `bin/arclink-live-proof` gains a
  `plugin-upgrade-roundtrip` scenario that installs a synthetic plugin,
  asserts the new command appears in both Telegram's `getMyCommands`
  result and Discord's `GET /applications/{app}/commands` payload within
  N seconds.

## Open Questions (Blocked by Operator)

These need operator answers before the dependent slices ship.

1. **Plugin trust boundary.** Should the merged command manifest pull from
   a vetted plugin registry (curator-curated allowlist), or only from
   plugins the operator has explicitly installed on a deployment, with
   no global registry? Affects security model and Slice 5's lifecycle
   event source.

2. **Discord scope strategy.** Global slash commands cache for ~1 hour
   client-side. Guild-scoped commands update instantly but require knowing
   the guild ahead of time. For push-on-change to actually be immediate,
   do we standardize on guild-scoped registration (per known guild), or
   accept up to 1-hour propagation for global commands? A mixed strategy
   is possible: curator commands global, plugin commands guild-scoped per
   linked guild.

3. **Bridge payload migration.** Is a hard cutover acceptable (all
   deployment containers must be upgraded to the v2 bridge before slice 7
   lands), or do we need a dual-support window where v1 and v2 coexist?
   "No fallbacks" suggests hard cutover with a coordinated upgrade wave.

4. **Command verb precedence.** Curator today owns `/plan`, `/agents`,
   `/credentials`, etc. If a plugin manifest declares the same `name`,
   who wins? Options: (a) curator always wins, plugin entry refused at
   manifest-merge time with a `contract-mismatch` event; (b) explicit
   `precedence` field with higher number wins and lower is hidden with a
   visible-to-operator note; (c) namespace plugin commands under
   `/plugin-name.command` to prevent collisions entirely.

5. **Telemetry retention.** New `arclink_bot_failures` table — retention
   horizon? Bot tokens and channel IDs may be sensitive even when scrubbed
   from the `detail` field. Suggested default: 30 days raw rows, then
   aggregated counts kept indefinitely.

6. **Manifest live-reload.** When `config/arclink_curator_commands.yaml`
   changes on disk, should the control plane hot-reload (watch the file)
   or require a deliberate `systemctl reload arclink-hosted-api`? Hot-
   reload is more "immediately effective"; reload-on-signal is more
   auditable.

7. **Vestigial plugins.** `plugins/hermes-agent/drive`,
   `plugins/hermes-agent/code`, and `plugins/hermes-agent/terminal` are
   manifest-only with no command/hook registration. Do we (a) wire them
   with real commands as part of this mission, (b) leave them as
   dashboard-UI-only plugins and remove their `plugin.yaml` provides_*
   fields, or (c) delete them entirely from the four-plugin set documented
   in `MEMORY.md`?
