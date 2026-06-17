# CANON-06 — Curator Onboarding — ADVERSARIAL VERIFICATION

Verifier: independent Opus 4.8 skeptic. Method: re-opened every target file and each
cited consumer/producer; verified load-bearing claims at path:line; attacked both-ends
seams, fail-closed claims, auth/TOCTOU/concurrency, and severity calibration.

VERDICT (one line): The record is **substantially trustworthy**. Its five cross-piece
seams that I could check are genuinely both-ends-verified, its two MEDIUM findings
(dead `arclink_upgrade_last_dismissed_sha`, unbounded `settings` growth) are real and I
independently re-confirmed them, and its core security claims (unified GAP-029 gate,
double-gated mutations, ownership checks, bounded poison-pill) hold in code. I found
**one inaccurate INFO claim** (the "double `.lower()`"), **two genuine new gaps** the
record missed (Discord claim-before-process drop, silent reply-send swallow), and a
handful of minor citation imprecisions. None overturn the verdict.

---

## A. REFUTATIONS / CONFIRMATIONS OF LOAD-BEARING CLAIMS

### A1. CONFIRMED — `arclink_upgrade_last_dismissed_sha` is written but never read (drift #1, MEDIUM risk)
Re-grepped the whole tree. Writers: `python/arclink_curator_onboarding.py:975`,
`python/arclink_curator_discord_onboarding.py:272`. Readers: ZERO (`grep -rn
last_dismissed` over `python/` plus `*.sh/*.ts/*.tsx/*.js` is empty except the two
writers; no dynamic-key construction `_dismissed_sha` either). The live suppression key
is `arclink_upgrade_last_notified_sha`, read at `arclink_ctl.py:1822` and written at
`:1878`. DISSECT.md independently agrees (its disagreement #5 and INFO line). The user
copy "Dismissed ArcLink update notice for …" (`curator_onboarding.py:976`) overstates the
effect. **NOT REFUTED — record is correct.**

### A2. CONFIRMED — `settings` unbounded growth via `curator_discord_onboarding_seen_message:<id>` (MEDIUM)
`grep -rn seen_message python/` finds exactly one producer (`:194`) and NO deleter. The
codebase has sweepers for other tables (`prune_host_probes`, `_prune_operator_button_nonces`,
`_prune_login_failures`) but none touch `settings` rows keyed by that prefix. Every distinct
Discord message id persists forever (`:196-204`, raw `INSERT OR IGNORE INTO settings`).
**NOT REFUTED — record is correct.**

### A3. CONFIRMED — GAP-029 gate unification (seam 3) is real and both-ends-verified
Producer `_operator_sender_allowed` (`curator_onboarding.py:240-248`) passes the exact 7
kwargs that `operator_telegram_sender_allowed` declares (`arclink_telegram.py:1144-1153`:
`chat_id, sender_id, chat_type, notify_platform, notify_channel_id, operator_user_ids,
operator_channels`). The hosted-API webhook gate `_operator_telegram_sender_allowed`
(`:1196-1205`) calls the SAME helper. Same Telegram update → same verdict. **NOT REFUTED.**

### A4. CONFIRMED — mutation double-gate + fail-closed (VERDICT point 2)
Verified the defense-in-depth the record relies on actually lives in CANON-14:
`dispatch_operator_raven_command` enforces `_require_operator_actor` (fail-closed if no
`actor_id`, `arclink_operator_raven.py:400-401`) AND `_require_operator_confirmation`
(requires `command.confirmed`, `:412-418`) for every `MUTATING_COMMANDS` member
(`:225`). So even the one-tap button path (which bypasses `strip_operator_approval_code`)
cannot mutate without the server-minted `confirm` token in the command, and the sender was
already validated by `_operator_sender_allowed` (`curator_onboarding.py:809`) before the
actor is derived (`:828`). Exception handlers at `:372-373` and `:840-841` send a
"failed closed" message rather than crashing the loop. **NOT REFUTED.**

### A5. CONFIRMED — seams 1, 2, 4, 5 both-ends-verified
- Seam 1: `IncomingMessage` (`arclink_onboarding_flow.py:138-145`) / `OutboundMessage`
  (`:148-155`) field sets match exactly what the workers build and read back
  (`curator_onboarding.py:1100-1108,1112-1118`; `discord:374-381,393-439`). VERIFIED.
- Seam 2: `completion_scrubbed_text_for_session(conn, cfg, session)` (`:526`),
  `completion_followup_text_for_session` (`:540`), `completion_followup_discord_components`
  (`:145`), `ensure_discord_agent_dm_confirmation_code(conn, session)` (`:172`) — call
  shapes at `curator_onboarding.py:549,584` and `discord:1078,1110-1114` match. VERIFIED.
- Seam 4: `dispatch_operator_raven_command(conn, text, *, env, upgrade_check_runner,
  actor_id, idempotency_key)` (`:349-357`) returns a dict with `message`+`buttons`
  (`:1480-1483`); call sites pass the agreed subset. VERIFIED.
- Seam 5: `settings` schema `arclink_control.py:598`, `onboarding_update_failures` `:827`,
  `bootstrap_requests` `:604`; the Discord raw INSERT writes the `(key,value,updated_at)`
  tuple the `settings` schema requires (`discord:198-202`). VERIFIED.
- Seam 6: `has_curator_non_telegram_gateway_channels` is a 1-line alias of
  `has_curator_non_onboarding_gateway_channels` (`common.sh:761-763`), exactly as drift #4
  states. `bootstrap-curator.sh:1032-1055` enables/disables the four units keyed on the
  `has_curator_*` predicates. VERIFIED.
- Seam 7: record honestly marks consumer-side `arclink_ctl.py internal curator-refresh` as
  UNREAD ("BOTH ENDS VERIFIED: no"). Honest gap; not a false claim.

### A6. REFUTED (INFO) — "`_telegram_command_token` calls `.lower()` twice in `_user_command_requested`" is INACCURATE
Record RISK/INFO line (`:119`) claims a redundant double `.lower()` at
`curator_onboarding.py:312`. The actual line is
`command = _telegram_command_token(parts[0] if parts else "").lstrip("/")`. There is ONE
`.lower()` (inside `_telegram_command_token`, `:125`) followed by `.lstrip("/")` and then
`.replace("-", "_")` (`:315`) — NOT a second `.lower()`. The described redundancy does not
exist in code. Harmless either way, but the specific INFO claim is wrong. **REFUTED.**

### A7. CONFIRMED — poison-pill ledger is bounded; record's self-check #5 fragility is real
`run_once` advances the offset only on per-update success (`:1212-1214`) or after hitting
`onboarding_update_failure_limit` (`:1185-1188`); otherwise it `break`s without advancing
(`:1198,:1210`) → bounded retry, no silent skip of a good update. The record's own
falsifier holds: if `record_onboarding_update_failure` raises inside the `with` at
`:1182-1188`, it propagates out of `run_once` to the outer loop, which swallows it
(`:1247-1252`) without advancing → infinite hot-loop on a DB-unwritable update (LOW,
disk-full only). **NOT REFUTED — record correctly self-identified this.**

### A8. CONFIRMED — gateway/onboarding token de-confliction interlock holds
Walked the booleans. `ARCLINK_CURATOR_CHANNELS=telegram` + telegram onboarding on →
`has_curator_non_onboarding_gateway_channels` returns 1 (false) → gateway `exit 0`
(`curator-gateway.sh:28-31`), so no double-bind. With a second non-onboarding channel,
the gateway runs but `has_curator_telegram_onboarding` unsets the token (`:117-118`) and the
re-export block at `:130` is skipped (its guard is `! has_curator_telegram_onboarding`). The
record's residual (manual gateway start with tokens in process env) is a real but
out-of-band caveat, correctly flagged as not source-provable (self-check #3). **NOT REFUTED.**

### A9. CONFIRMED — command counts and persona drift
`TELEGRAM_OPERATOR_COMMANDS` has exactly 23 entries (`:84-106`, counted). Discord registers
26 `_ensure_operator_channel`-gated slash handlers (grep count) — "comparably large" is fair.
argparse description says "Raven, Curator of the Console" (`:116`) while slash copy says
"Curator" (`discord:558`); same bot, cosmetic. **NOT REFUTED.**

---

## B. NEW GAPS THE RECORD AND PRIOR DOCS BOTH MISSED

### B1. NEW (LOW) — Discord claim-before-process permanently drops a message on any handler exception
`_claim_discord_message_once` (`discord:190-204`) commits the seen-row and returns True
BEFORE the message is handled. `on_message` (`:920-947`) then runs
`_handle_operator_channel_message` / `_process_discord_input` / `_send_replies` with NO
surrounding try/except. discord.py gateway events are push-once (no offset redelivery on
RESUME), so any transient exception mid-handler (DB blip, flow error) drops that onboarding
message forever — it is already marked seen and will be skipped on every retry. This is a
fail-shut silent drop the record's MEDIUM "growth" finding overlooks (it analyzed the row's
persistence, not its claim-ordering). Asymmetry vs the Telegram side, which records a
failure ledger and retries.

### B2. NEW (LOW) — Discord `_send_replies` swallows all channel-send errors silently
`_send_replies` (`discord:385-441`) wraps every `discord_send_message` / `channel.send`
in `except Exception: pass`/`continue` (`:409-410,429-430,436-441`). Because
`process_onboarding_message` advances/persists onboarding state in CANON-04 BEFORE these
sends, a failed delivery leaves the session moved forward with the user never seeing the
prompt — a state/UX desync with no log and no retry. The record notes the Telegram
`notify_operator_worker_failure` swallow (LOW) but not this Discord user-reply swallow.

### B3. NEW (INFO) — `scope=="upgrade"` callback with an unrecognized action raises UnboundLocalError (caught, fail-closed)
In `_handle_operator_callback` (`:973-996`), if `scope=="upgrade"` and `action` is none of
`{dismiss, install, preview}`, neither `result_text` nor `replacement_text` is assigned, so
`:1039`/`:1046` raise `UnboundLocalError`, caught by the broad `except` at `:1051` →
compact-error alert. Latent bug, fails closed, not exploitable. Custom_id is operator-minted
so reachability is near-zero, but it is a real dead-branch hole neither doc lists.

---

## C. SEAM MISMATCHES
None that break a contract. The only seam the record itself leaves unverified is seam 7
(`arclink_ctl.py internal curator-refresh` / `register-curator` consumer side), which it
honestly marks "BOTH ENDS VERIFIED: no". I did not close it either (adjacent CANON-31/14).
OPEN-FOR-CODEX #3 (does `register-curator --channels-json` round-trip the `tui-only`-prefixed
list at `bootstrap-curator.sh:884-894`) remains genuinely open.

## D. SEVERITY CALIBRATION
- MEDIUM dead-dismiss and MEDIUM settings-growth: agree.
- LOW "Operator DM allow-without-allowlist on Discord" (`discord:182-183`): arguably even
  slightly conservative — a DM channel id is unique to one bot↔user pair, so the
  no-allowlist DM branch is reachable only by that single peer (and only if the operator
  channel id is itself a DM channel id). LOW is fair; not refuting.
- The two NEW gaps (B1, B2) are LOW: real silent-drop paths, bounded by transient-failure
  reachability and the Docker-mode trust boundary.

## E. CITATION IMPRECISIONS (non-load-bearing)
- `process_update` is keyword-only `def process_update(*, cfg, ...)` (`:1122`), not the
  positional `(cfg, bot_token, curator_bot_id, update: dict)` the record's prose implies.
- `curator-tui.sh:33` is `exec env HERMES_HOME=… "$HERMES_BIN" "$@"`, not literally
  `exec hermes "$@"` — behavior matches the claim.

## OVERALL
Trustworthy. One INFO claim refuted (A6, the phantom double-`.lower()`), two genuine new
LOW gaps added (B1 claim-before-process drop, B2 silent reply swallow), one INFO dead-branch
(B3). The record's load-bearing security and seam claims survived independent re-verification.
