<<<CODEX-VERDICT-START CANON-06>>>
## CANON-06 — Codex (GPT-5.5 xhigh) ratification
SIGN-OFF: OBJECT(3)
ONE-LINE VERDICT: Record is materially trustworthy, but its “mutations are double-gated” claim is overbroad: direct Discord approval paths mutate without the configured approval-code rail.

### Adjudication (each: CONFIRM/REFUTE/REFINE + path:line)
- CONFIRM MEDIUM: Discord seen-message dedupe grows `settings` monotonically; insert key is `curator_discord_onboarding_seen_message:<id>` and I found no deleter/TTL reader for that prefix. `python/arclink_curator_discord_onboarding.py:190-204`
- CONFIRM MEDIUM: upgrade Dismiss writes dead key `arclink_upgrade_last_dismissed_sha`; real suppression reads/writes `arclink_upgrade_last_notified_sha`. `python/arclink_curator_onboarding.py:973-977`, `python/arclink_curator_discord_onboarding.py:270-273`, `python/arclink_ctl.py:1821-1878`
- REFINE core security claim: Operator Raven mutating commands are actor+confirmation gated, but direct Discord `/approve`/`/deny`/SSOT actions run after channel/allowlist only, with no approval-code check. `python/arclink_operator_raven.py:400-418`, `python/arclink_curator_discord_onboarding.py:206-253`, `python/arclink_curator_discord_onboarding.py:600-623`, `python/arclink_curator_discord_onboarding.py:973-992`
- CONFIRM Telegram approval-code rail: typed `/approve`/`/deny` uses `hmac.compare_digest`; callbacks with a configured code force typed approval for approve/deny/install. `python/arclink_curator_onboarding.py:279-303`, `python/arclink_curator_onboarding.py:874-904`
- CONFIRM GAP-029 Telegram gate seam: Curator passes the same 7 args consumed by hosted Telegram gate helper. `python/arclink_curator_onboarding.py:231-248`, `python/arclink_telegram.py:1144-1205`
- CONFIRM onboarding flow seam: workers construct `IncomingMessage`; consumer returns `OutboundMessage` fields the workers read. `python/arclink_onboarding_flow.py:137-155`, `python/arclink_curator_onboarding.py:1098-1119`, `python/arclink_curator_discord_onboarding.py:364-383`
- CONFIRM ownership checks: Telegram/Discord backup, Notion, and completion callbacks compare stored `sender_id` and `chat_id` before acting. `python/arclink_curator_onboarding.py:531-541`, `python/arclink_curator_onboarding.py:644-655`, `python/arclink_curator_onboarding.py:739-750`, `python/arclink_curator_discord_onboarding.py:1001-1010`, `python/arclink_curator_discord_onboarding.py:1039-1045`, `python/arclink_curator_discord_onboarding.py:1066-1078`
- CONFIRM Telegram poison-pill behavior with caveat: success or failure-limit advances offset; failure below limit breaks without advancing; if failure-record DB write itself raises, outer loop swallows and retries. `python/arclink_curator_onboarding.py:1171-1216`, `python/arclink_curator_onboarding.py:1244-1252`
- CONFIRM token interlock in canonical launcher: gateway exits when onboarding owns all bot channels; otherwise filtered gateway home strips onboarding-owned tokens and guarded re-export skips them. `bin/curator-gateway.sh:27-38`, `bin/curator-gateway.sh:72-123`, `bin/curator-gateway.sh:130-159`, `bin/common.sh:741-774`
- REFINE open seam 7: consumer is now verified. `register-curator` parses `--channels-json` via `json.loads`, `register_agent` normalizes/persists it, and `curator-refresh` runs repo sync, vault reload, Notion reindex, fanout, upgrade notify, pin detector, and refresh-job note. `python/arclink_ctl.py:1438-1477`, `python/arclink_control.py:11726-11765`, `python/arclink_control.py:11802-11816`, `python/arclink_ctl.py:2655-2683`
- REFUTE verifier’s double-`.lower()` refutation target as record-only INFO: there is one `.lower()` in `_telegram_command_token`; `_user_command_requested` then only `lstrip`/`replace`. `python/arclink_curator_onboarding.py:124-125`, `python/arclink_curator_onboarding.py:310-316`
- REFINE verifier B2: `_send_replies` does silently swallow component sends, fetch failures, and non-origin sends, but same-origin non-component `channel.send` errors propagate. `python/arclink_curator_discord_onboarding.py:401-419`, `python/arclink_curator_discord_onboarding.py:421-441`
- CONFIRM verifier B1/B3: Discord claims message id before processing; malformed upgrade action can leave `result_text` unset and fail closed through broad callback exception handling. `python/arclink_curator_discord_onboarding.py:927-947`, `python/arclink_curator_onboarding.py:973-996`, `python/arclink_curator_onboarding.py:1039-1058`

### New findings both Claude passes missed (severity + path:line)
- MEDIUM: Configured operator approval code is not enforced on direct Discord approval/deny paths. Text and slash commands reach `_run_operator_action`, which approves onboarding, bootstrap requests, and SSOT writes; component `arclink:ssot:` also reaches it. Gate is channel/allowlist only. `python/arclink_curator_discord_onboarding.py:466-555`, `python/arclink_curator_discord_onboarding.py:600-623`, `python/arclink_curator_discord_onboarding.py:973-992`, `python/arclink_curator_discord_onboarding.py:206-253`

### Claude citations re-confirmed or corrected
- Re-confirmed: live systemd-managed surface, not dead legacy: launchers and bootstrap enable/restart units. `bin/arclink-curator-onboarding.sh:9-10`, `bin/arclink-curator-discord-onboarding.sh:9-10`, `bin/bootstrap-curator.sh:1029-1055`
- Re-confirmed: Telegram operator catalog is 23 commands. `python/arclink_curator_onboarding.py:83-107`
- Corrected: `process_update` is keyword-only, not positional. `python/arclink_curator_onboarding.py:1122`
- Corrected: TUI launcher is `exec env HERMES_HOME=... "$HERMES_BIN" "$@"`, not literal `exec hermes "$@"`. `bin/curator-tui.sh:21-33`

### Residual disagreement with the Claude half (for final reconciliation)
- Do not ratify the blanket “mutating operator commands are double-gated” wording for CANON-06. It holds for Operator Raven and Telegram approval paths, but not for direct Discord approve/deny/SSOT actions. The piece stands with that refinement.
<<<CODEX-VERDICT-END CANON-06>>>
