# CANON-05 — Public Bots — ADVERSARIAL VERIFY

Verifier: independent Opus 4.8 skeptic. Method: every load-bearing claim re-opened at
path:line; cross-piece contracts attacked at both ends; unhappy paths and retry/error
paths traced; one executable proof built. Code wins over comments/docstrings/prior docs.

## SUMMARY VERDICT
The record is **largely trustworthy and unusually careful** — its drift findings (operator
20-vs-12, public 33-vs-27, legacy strip-list, bridge-file misattribution) are all
independently CONFIRMED in code, its rate-limit and fail-closed authn claims hold, and its
both-ends contract checks (#3 Telegram secret, #4 direct-checkout token) are exact. BUT it
contains one **incorrect security characterization** ("Discord sentinel keys are rejected"
— there is no sentinel logic; the protection is purely cryptographic), one **overclaimed
both-ends key** (`display_name` is never emitted by the producer), and it **MISSES a real
fail-silent gap**: a Discord interaction that fails AFTER reservation poisons its own retry
and is permanently dropped. Net: trust the drift ledger and the contracts; correct the
Discord-sentinel wording; add the retry-poison gap to the risk register.

---

## REFUTATIONS / CONFIRMATIONS (load-bearing claims)

### REFUTED-AS-MISCHARACTERIZED
1. **"Test-sentinel public keys are rejected" (record line 60, cites arclink_discord.py:239).**
   REFUTED as stated. `arclink_discord.py:239` is `if not DISCORD_PUBLIC_KEY_RE.fullmatch(...)`
   — a generic 64-hex regex check. There is NO sentinel/blocklist logic anywhere in the file;
   `grep -ni sentinel python/arclink_discord.py` matches ONLY the docstring at line 236 (a
   CLAIM). A 64-hex test/sentinel key PASSES the regex and `is_live` (`:214`). The real
   security property is cryptographic: a forged key cannot verify a Discord-signed message, so
   a wrong key rejects ALL traffic (fail-closed by rejecting everything), not because sentinels
   are blocklisted. The record's OPEN-item #4 question is therefore answerable: yes, a 64-hex
   non-Discord key passes `is_live` but breaks all real traffic — no auth bypass, but the
   record's framing of explicit "sentinel rejection" is docstring-drift. CODE WINS.

2. **CONTRACT #1 "BOTH-ENDS-VERIFIED: yes" for the public-agent-turn extra_json,
   incl. `display_name` (record line 79 / consumer arclink_notification_delivery.py:682).**
   PARTIALLY REFUTED. The producer `_queue_public_agent_turn` (arclink_public_bots.py:3919-3951)
   writes `agent_label` and `raven_display_name` but NEVER `display_name`. The consumer reads
   `extra.get("display_name") or extra.get("agent_label")` (`:682`) — it only works because of
   the `agent_label` fallback. The record lists the producer keys correctly (no `display_name`)
   yet asserts the `display_name` key as both-ends-verified; the producer end does not emit it.
   Benign (fallback covers it) but the seam is asymmetric and the "verified" label is loose.

### CONFIRMED (independently re-confirmed in code)
3. **Operator path bypasses per-identity rate limit (record line 66/110, MEDIUM).** CONFIRMED.
   `handle_telegram_update` returns `operator_result` at arclink_telegram.py:1472-1473 BEFORE
   `handle_arclink_public_bot_turn` (`:1485`), whose first action is `_check_public_bot_rate_limit`
   (arclink_public_bots.py:7144). No `check_arclink_rate_limit` call exists in
   `_handle_operator_telegram_update`. Added nuance below (shared IP bucket).
4. **Rate limit is fail-closed 20/900 (record line 17/68).** CONFIRMED.
   `ARCLINK_PUBLIC_BOT_TURN_LIMIT=20`, `..._RATE_WINDOW_SECONDS=900` (arclink_public_bots.py:95-96);
   `check_arclink_rate_limit` raises `ArcLinkRateLimitError` when `count >= limit` BEFORE insert
   (arclink_api_auth.py:418). (TOCTOU note below.)
5. **CONTRACT #3 Telegram webhook secret both-ends.** CONFIRMED. Consumer
   `hmac.compare_digest(supplied, config.telegram_webhook_secret)` → 401 on mismatch, 503 when
   unset (arclink_hosted_api.py:2889-2901). Producer sets the same secret on `setWebhook`
   (record cite, not re-disputed). Sound.
6. **CONTRACT #4 direct-checkout token both-ends.** CONFIRMED EXACTLY. Producer
   `_direct_checkout_token_digest = sha256(token).hexdigest()` (arclink_public_bots.py:1433-1434),
   stored under `public_bot_checkout_verifiers` (`:1455`). Consumer re-hashes supplied token and
   `hmac.compare_digest`s (arclink_hosted_api.py:799-807). Plans `{founders, scale}` match
   producer `ARCLINK_PUBLIC_BOT_DIRECT_CHECKOUT_PLANS` (`:91`). Route key
   `("GET","/onboarding/public-bot-checkout")` (arclink_hosted_api.py:3758) matches the
   `/api/v1`-prefixed path constant (`:92`). Sound.
7. **CONTRACT #5 operator confirm/approval-code gate is fail-closed.** CONFIRMED (I went
   further than the record, which deferred this to CANON-14). Re-read the gate that LIVES in
   this piece (arclink_telegram.py:1305-1322) plus `strip_operator_approval_code`
   (arclink_operator_raven.py:327-346), `operator_approval_code` (`:312-324`),
   `operator_raven_command_is_mutating` (`:301-306`, MUTATING_COMMANDS `:225`), and
   `parse_operator_raven_command` (`:241-280`). When a code is configured, the verified last
   token is stripped and `--confirm` appended → mutation. When no code is configured, mutation
   still requires the literal `confirm` token in the text (parser sets `confirmed`,
   `_require_operator_confirmation` blocks otherwise). The button path `_handle_upgrade_apply`
   consumes a single-use nonce as structured confirmation (`:1507-1515`). No fail-open found.
   My initial suspicion that "no code configured ⇒ unconfirmed mutation" is REFUTED by the
   parser-level `confirmed` requirement. This STRENGTHENS the record.
8. **Drift #1 operator catalog = 20 (not 12).** CONFIRMED. `ARCLINK_OPERATOR_TELEGRAM_COMMANDS`
   has exactly 20 dict entries (arclink_telegram.py:149-170), `operator_fleet` present, no
   `fleet_list`. CODE WINS.
9. **Drift #2 public actions = 33.** CONFIRMED via AST count of `ArcLinkPublicBotAction(` in the
   `ARCLINK_PUBLIC_BOT_ACTIONS` tuple (arclink_public_bots.py:342): exactly 33 keys incl.
   share_create/approve/deny/accept, add_agent, retire_agent.
10. **Drift #3 legacy strip list.** CONFIRMED ~53 entries in
    `ARCLINK_TELEGRAM_LEGACY_RAVEN_COMMAND_NAMES` (arclink_telegram.py:91-148) — record's "~55"
    is within tolerance (it uses "~").
11. **Drift #4 bridge-file misattribution.** CONFIRMED. `telegram_update_json_list` /
    `public-agent-turn` consumer is arclink_notification_delivery.py (`_public_agent_gateway_payload`
    :638, reads extra at :650/655/682/689); arclink_public_bots.py never references the inner bridge.
12. **Drift #7 truncation real, undocumented.** CONFIRMED. `telegram_send_message` truncates
    `len(text) > 4000` to `text[:3997] + "..."` (arclink_telegram.py:224). NOTE: the record
    quotes the suffix as `"…"` (ellipsis char); the code uses three ASCII dots `"..."` — a
    minor self-citation drift in the record.
13. **Discord dedupe = (provider,event_id) PK + IntegrityError.** CONFIRMED. Schema PK
    (arclink_control.py:988); INSERT+commit then catch `sqlite3.IntegrityError` →
    "duplicate Discord interaction" (arclink_discord.py:271-282). Reservation occurs AFTER
    timestamp+signature checks (`:551-556`), so unauthenticated requests cannot poison the table.
14. **`_clean_channel` rejects web; identity required.** CONFIRMED.
    `ARCLINK_PUBLIC_BOT_CHANNELS = {telegram, discord}` (arclink_public_bots.py:78);
    `_clean_channel` raises otherwise (`:750-754`); `_clean_identity` raises on empty (`:757-761`).
15. **`run_telegram_polling` hard-fails without token (self-check #3).** CONFIRMED. Raises
    `ArcLinkTelegramError` unless a transport is injected (arclink_telegram.py:1721-1725).
16. **11 non-text Telegram message kinds.** CONFIRMED (`_telegram_message_kind` :1018-1041,
    `_telegram_fallback_text_for_kind` :1044-1058). `parse_telegram_update` returns None when no
    chat_id or no text (`:1102`); `telegram_native_callback` set when data lacks `arclink:` (`:1071`).
17. **72 owned tests pass.** CONFIRMED — ran the four suites; 72 passed.

---

## NEW GAPS (neither the record nor priors mention)

### GAP-A (MEDIUM) — Failed Discord interaction poisons its own retry → permanent drop
`_reserve_discord_interaction` INSERTs+commits the dedupe row (status 'received') BEFORE
`handle_discord_interaction` runs (arclink_discord.py:556). If processing raises a
non-`ArcLinkDiscordError` (e.g. turn-engine/DB/model-timeout error), the row is UPDATEd to
status='failed' (`:570`) but NOT deleted, and the exception propagates. Discord retries the
SAME interaction id; the retry's reservation hits the PK row and raises "duplicate Discord
interaction" (`:281`) — `_reserve_discord_interaction` rejects ANY existing event_id
regardless of `status`, so 'failed' rows are never retryable. At the hosted-API layer the
retry's "duplicate" maps to HTTP 200 `{type:5}` (deferred ack, arclink_hosted_api.py:3048-3049)
with no followup ever sent. Net: a transient first-delivery failure produces a permanent
"thinking…" with no reply and no operator-visible error. PROVEN with an executable
reproduction (reserve → mark failed → retry → "duplicate Discord interaction -> never
reprocessed"). Same class also strands rows stuck in 'received' if the process crashes between
reservation-commit and processing.

### GAP-B (LOW) — Webhook IP rate-limit bucket is shared across ALL Telegram traffic
The record states operators are "IP/secret-rate-limited" by `_check_webhook_rate_limit`. I
read its body (arclink_hosted_api.py:663-682): subject is `ip:{client_ip}`. Because Telegram
delivers every webhook from Telegram's own server IPs, ALL Telegram users (operators + Captains)
share one IP bucket under scope `webhook:telegram`. So (a) the operator bound is effectively a
shared global Telegram bucket, not a per-operator bound, and (b) a flood from any single
Telegram source can exhaust the shared bucket and 429 legitimate users. This refines the
record's MEDIUM operator-rate-limit risk: the only per-operator-ish bound is weaker than the
record implies.

### GAP-C (LOW) — Rate-limit is COUNT-then-INSERT (non-atomic TOCTOU)
`check_arclink_rate_limit` SELECT COUNTs then (separately) INSERTs (arclink_api_auth.py:408-428)
with no row lock between. Two concurrent turns for the same subject can both read count=19 and
both pass before either inserts. Under SQLite single-writer serialization the window is small
but real for multi-connection deployments; the record asserts "fail-closed rate limiting"
without noting the read/write is not atomic.

### GAP-D (LOW) — Telegram entities not re-clamped on truncation
When `telegram_send_message` truncates text >4000 → `text[:3997]+"..."` (arclink_telegram.py:224)
but `entities` were computed against the FULL text (computed in handle_telegram_update via
`telegram_markdown_to_entities`, :1523), entity offsets can point past the truncated end.
Telegram's API rejects out-of-range entities, so a long Raven reply with code spans could fail
to send entirely (not just lose the tail). Neither record nor priors flag this interaction.

### GAP-E (INFO) — Discord type-4 empty content possible off the agent-queued path
`handle_discord_interaction` only substitutes empty content ("Sent to your active Hermes
Agent.") when `action=="agent_message_queued"` (arclink_discord.py:463-468). Any other action
returning an empty `turn.reply` ships `data={"content":""}` on a type-4 response, which Discord
rejects. No current action is proven to do this, so INFO not MEDIUM, but the guard is narrower
than the stated invariant "Discord interaction callbacks cannot have empty content."

---

## SEAM MISMATCHES
- **`telegram_update_json_list`**: consumer reads it (arclink_notification_delivery.py:690); NO
  producer file writes it (`grep` across all four target files = zero). Optional-with-skip, so
  benign, but it is a genuine consumer-only key. The record's self-check #2 flagged it as
  unresolved; now CONFIRMED unwritten.
- **`display_name`**: consumer reads `extra.get("display_name")` (`:682`); producer never writes
  it (writes `agent_label`). Fallback covers it; the record's CONTRACT #1 "both-ends-verified"
  for that key is overclaimed.
- **`prefix`**: producer DOES write it (arclink_public_bots.py:3921); the record's OPEN-item #1
  worry that `prefix` might be a consumer-required-but-producer-omitted key is REFUTED — it is
  emitted. Consumer threads it via `_run_public_agent_gateway_turn(prefix=...)`.

## RISK SEVERITY RE-CALIBRATION
- Record's MEDIUM "operator skips per-identity limit": KEEP MEDIUM, but note the only residual
  bound (webhook IP bucket) is shared-global (GAP-B), so it is weaker than "operators are
  IP-rate-limited" suggests.
- NEW: GAP-A (Discord retry-poison) merits MEDIUM — silent permanent message loss on any
  transient failure, user-visible as a stuck deferred response.
- Record's "Discord sentinel rejection" should be reworded to "cryptographic rejection of any
  non-Discord key" — the security holds but the mechanism described does not exist.

## RESIDUAL DISAGREEMENTS
- The record's VERDICT calls the Discord dedupe simply "idempotent ... via a PK/IntegrityError"
  — true for the happy/duplicate path, but it omits that the same mechanism makes failed
  interactions non-retryable (GAP-A). The dedupe is idempotent-but-not-recoverable.
- CONTRACT #5 was marked "partial / not re-read line-by-line"; I re-read it and it is sound
  (fail-closed), so that contract can be upgraded to verified for the confirm/approval-code
  semantics that live in this piece.
