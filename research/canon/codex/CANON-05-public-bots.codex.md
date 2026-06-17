<<<CODEX-VERDICT-START CANON-05>>>
## CANON-05 — Codex (GPT-5.5 xhigh) ratification
SIGN-OFF: OBJECT(3)
ONE-LINE VERDICT: Claude’s record is mostly code-true, but it missed a HIGH secret-exposure path and a MEDIUM direct-checkout replay/session-claim path.

### Adjudication (each: CONFIRM/REFUTE/REFINE + path:line)
- CONFIRM core piece contract: the channel set is only `{telegram, discord}`, identity is required, public turns rate-limit first, and the turn dataclass matches the record. `python/arclink_public_bots.py:78`, `python/arclink_public_bots.py:730-747`, `python/arclink_public_bots.py:750-760`, `python/arclink_public_bots.py:7125-7144`
- CONFIRM public action table = 33 actions including add/retire/share variants. `python/arclink_public_bots.py:342-713`
- CONFIRM Telegram webhook auth/input/output: shared secret rejects unset/mismatch, parser strips `arclink:` callbacks and falls back for rich messages, result dict shape matches. `python/arclink_hosted_api.py:2889-2901`, `python/arclink_telegram.py:1061-1103`, `python/arclink_telegram.py:1525-1536`
- CONFIRM Discord auth/dedupe/output: timestamp then Ed25519 then reserve, response type 4/7 shape matches, duplicate maps to deferred 200. `python/arclink_discord.py:230-258`, `python/arclink_discord.py:271-283`, `python/arclink_discord.py:469-485`, `python/arclink_discord.py:551-556`, `python/arclink_hosted_api.py:3047-3049`
- REFINE public-agent-turn seam: producer emits `agent_label`, `raven_display_name`, `prefix`, Telegram/Discord metadata; consumer tolerates consumer-only `display_name` via `agent_label` fallback and can synthesize `telegram_update_json_list` itself. `python/arclink_public_bots.py:3919-3959`, `python/arclink_notification_delivery.py:650-690`, `python/arclink_notification_delivery.py:1543-1545`, `python/arclink_notification_delivery.py:1552-1593`
- CONFIRM MEDIUM operator per-identity rate-limit gap: operator result returns before `handle_arclink_public_bot_turn`; only webhook IP bucket remains, not operator identity. `python/arclink_telegram.py:1471-1485`, `python/arclink_public_bots.py:7142-7144`, `python/arclink_hosted_api.py:663-681`
- CONFIRM MEDIUM Telegram shared-secret boundary: no per-update signature; Telegram path accepts solely `X-Telegram-Bot-Api-Secret-Token` compare. `python/arclink_hosted_api.py:2889-2901`
- CONFIRM MEDIUM Discord retry poison: reserve commits before processing, failure marks row `failed`, retry hits PK duplicate and hosted API returns type 5 with no reprocess. `python/arclink_discord.py:271-295`, `python/arclink_discord.py:556-570`, `python/arclink_hosted_api.py:3047-3049`
- REFUTE “Discord sentinel-key rejection”: code only checks 64-hex regex then VerifyKey; the sentinel claim is comment drift. `python/arclink_discord.py:235-247`
- CONFIRM operator approval gate fail-closed: mutating commands are detected, transport requires/strips approval code and appends `--confirm`, parser removes confirm tokens, command handlers require confirmation. `python/arclink_telegram.py:1305-1322`, `python/arclink_operator_raven.py:225-230`, `python/arclink_operator_raven.py:255-260`, `python/arclink_operator_raven.py:412-419`
- CONFIRM LOW risk cluster: lossy Telegram truncation, entities computed before send truncation, command-scope fallback swallows docker/helper errors, cache is process-local set, rate-limit is count-then-insert. `python/arclink_telegram.py:50`, `python/arclink_telegram.py:224-234`, `python/arclink_telegram.py:1519-1524`, `python/arclink_public_bot_commands.py:166-173`, `python/arclink_api_auth.py:408-430`

### New findings both Claude passes missed (severity + path:line)
- HIGH — `/credentials` can reveal the dashboard password into the inbound Telegram chat or non-ephemeral Discord interaction with no private-chat/DM guard. The raw secret is placed in reply text and copy button; the command path does not receive/check chat type; Telegram sends to `chat_id`, and Discord response data has content/components but no `flags`. `python/arclink_public_bots.py:3678-3714`, `python/arclink_public_bots.py:3740-3750`, `python/arclink_public_bots.py:7608-7622`, `python/arclink_telegram.py:1525-1528`, `python/arclink_hosted_api.py:2980-2984`, `python/arclink_discord.py:469-485`
- MEDIUM — public-bot direct-checkout URL tokens are reusable bearers that can mint fresh browser-claim cookies after checkout is open/paid. Producer stores only verifier hashes; redirect reissues a claim cookie on existing open/paid checkout; claim API then creates a user session from that proof. `python/arclink_public_bots.py:1427-1455`, `python/arclink_hosted_api.py:799-807`, `python/arclink_hosted_api.py:832-843`, `python/arclink_hosted_api.py:559-589`, `python/arclink_api_auth.py:4967-5004`
- LOW — Telegram reply send failures are logged and swallowed, then the webhook still returns 200; state changes made before send can leave the user with no visible reply and no Telegram retry. `python/arclink_hosted_api.py:2963-2967`, `python/arclink_hosted_api.py:2980-2984`, `python/arclink_hosted_api.py:3001-3010`

### Claude citations re-confirmed or corrected
- Reconfirmed: 20 operator Telegram commands and no `fleet_list`; code registers `operator_fleet`. `python/arclink_telegram.py:149-170`
- Reconfirmed/corrected: legacy Raven strip list is 53 entries, not the older-doc 18 and not exactly 55. `python/arclink_telegram.py:91-148`
- Corrected: Telegram truncation suffix is ASCII `"..."`, not a Unicode ellipsis. `python/arclink_telegram.py:224`
- Corrected: `display_name` is not producer-emitted for public-agent turns; consumer falls back to `agent_label`. `python/arclink_public_bots.py:3919-3927`, `python/arclink_notification_delivery.py:682`
- Consumer-side Hermes menu contract remains only partially verified here: ArcLink imports/calls `telegram_menu_commands(max_commands=...)`, but no pinned Hermes source was present in this checkout to re-open. `python/arclink_telegram.py:482-485`, `python/arclink_public_bot_commands.py:149-153`

### Residual disagreement with the Claude half (for final reconciliation)
- Add the HIGH credentials-in-public-channel finding to the risk register; the record’s “credentials revealed once then removed” framing is incomplete because the first reveal can be the leak. `python/arclink_public_bots.py:3710-3714`, `python/arclink_discord.py:469-485`
- Add the reusable direct-checkout-token/session-claim replay finding; the both-ends token contract is true but not sufficient. `python/arclink_hosted_api.py:832-843`, `python/arclink_api_auth.py:4967-5004`
- Keep verifier’s Discord dedupe correction: it is idempotent for duplicates but non-recoverable after post-reservation failure. `python/arclink_discord.py:556-570`, `python/arclink_hosted_api.py:3047-3049`
<<<CODEX-VERDICT-END CANON-05>>>
