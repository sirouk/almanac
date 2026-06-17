# CANON-05 — Public Bots (Telegram/Discord) — RECONCILED (both-model truth)

- Piece: CANON-05 — Public Bots (Telegram/Discord)
- Owned files: `python/arclink_public_bots.py`, `python/arclink_telegram.py`, `python/arclink_discord.py`, `python/arclink_public_bot_commands.py`
- Codex (GPT-5.5 xhigh) SIGN-OFF: **OBJECT(3)** — "missed a HIGH secret-exposure path and a MEDIUM direct-checkout replay/session-claim path; rest mostly code-true."
- Claude record SIGN-OFF: piece passes; one mischaracterization (Discord sentinel), one overclaimed seam (`display_name`), missed Discord retry-poison (added by Claude adversarial verify as GAP-A).
- **FEDERATION SIGN-OFF: BOTH-MODEL-AGREED.** Every material point reconciled to a single code-grounded truth below. No standing disagreement remains after re-opening the code; the Codex OBJECT items are accepted as net-new federation risks.

Adjudicator: Opus 4.8 final. Method: re-opened every disputed cite myself (Read/sed); code wins over comment/name/prior claim.

---

## RESOLUTION TABLE (disputed + REFINE/REFUTE + new-finding points)

| # | Point | Winner | Deciding cite (re-opened by adjudicator) |
|---|-------|--------|------------------------------------------|
| 1 | "Discord test-sentinel keys are rejected" — is there sentinel/blocklist logic? | both (codex+claude-verify) | `arclink_discord.py:239` is only `DISCORD_PUBLIC_KEY_RE.fullmatch(...)`; "sentinel" appears solely in the docstring `:235-237`. Protection is cryptographic fail-closed (`:243-246`), not a blocklist. Record wording is docstring-drift. |
| 2 | `public-agent-turn` extra seam: is `display_name` producer-emitted? | both (codex+claude-verify) | Producer `_queue_public_agent_turn` writes `agent_label`/`raven_display_name`/`prefix` only (`arclink_public_bots.py:3919-3951`); never `display_name`. Consumer falls back `extra.get("display_name") or extra.get("agent_label")` (`arclink_notification_delivery.py:682`). Record's CONTRACT #1 "both-ends-verified: yes" for `display_name` overclaimed. |
| 3 | Is `prefix` a consumer-required-but-producer-omitted key (record OPEN-#1 worry)? | claude-verify / codex | Producer DOES emit `prefix` (`arclink_public_bots.py:3921`). Worry refuted; seam sound. |
| 4 | `telegram_update_json_list` — written by any producer? | both | No producer in the four owned files writes it; consumer can synthesize it (`arclink_notification_delivery.py:1543-1593`, reads at `:690`). Consumer-only, benign (optional-with-skip). |
| 5 | Operator path bypasses per-identity rate limit (record MEDIUM). | both | `handle_telegram_update` returns `operator_result` at `arclink_telegram.py:1472-1473` BEFORE `handle_arclink_public_bot_turn` (`:1485`), whose first action is `_check_public_bot_rate_limit` (`arclink_public_bots.py:7144`). No rate-limit call in operator path. |
| 6 | Residual operator bound = webhook IP bucket; is it per-operator? (claude-verify GAP-B refine) | claude-verify / codex | `_check_webhook_rate_limit` subject = `ip:{client_ip}`, scope `webhook:{provider}` (`arclink_hosted_api.py:674-682`). Telegram delivers all webhooks from its own IPs → one shared global Telegram bucket, not per-operator. Refines the MEDIUM. |
| 7 | Operator approval/`--confirm` gate fail-closed (record marked CONTRACT #5 "partial"). | both (upgrade to verified) | Configured-code path blocks → `operator_raven_code_required` (`arclink_telegram.py:1308-1320`); appends `--confirm` only with code (`:1322`). No-code path still blocked unless literal confirm token present: `_require_operator_confirmation` keys off `command.confirmed` (`arclink_operator_raven.py:412-419`), `_CONFIRM_TOKENS` (`:230`), `MUTATING_COMMANDS` (`:225`). No fail-open. |
| 8 | Discord retry-poison: failed interaction is permanently dropped (claude-verify GAP-A; Codex CONFIRM). | both | Reserve INSERT+commit at `arclink_discord.py:280` BEFORE processing (`:558`); on exception row marked `failed` not deleted (`:570`), re-raised; retry collides on PK → "duplicate" (`:281`); hosted API maps duplicate → HTTP 200 `{type:5}` deferred, no followup (`arclink_hosted_api.py:3048-3049`). `_reserve_discord_interaction` rejects ANY existing event_id regardless of status. |
| 9 | Rate-limit fail-closed AND non-atomic count-then-insert (claude-verify GAP-C). | both | `check_arclink_rate_limit` SELECT COUNT then separate INSERT, no row lock (`arclink_api_auth.py:408-430`); raises before insert when `count >= limit`. Fail-closed but TOCTOU window exists for multi-connection. |
| 10 | Telegram truncation suffix `"…"` vs ASCII `"..."`. | both (codex+claude-verify) | `arclink_telegram.py:224` uses `text[:3997] + "..."` (three ASCII dots). Record self-cite of `"…"` is minor drift. |
| 11 | Drift ledger (operator=20, public=33, legacy strip≈53, bridge-file misattribution). | both | `ARCLINK_OPERATOR_TELEGRAM_COMMANDS` 20 entries, `operator_fleet` not `fleet_list` (`arclink_telegram.py:149-170`); `ARCLINK_PUBLIC_BOT_ACTIONS` 33 (`arclink_public_bots.py:342-713`); legacy strip ≈53 (`arclink_telegram.py:91-148`); `public-agent-turn` consumed by `arclink_notification_delivery.py` not the inner bridge. Record's "~55" within "~" tolerance. |

CONFIRM items where all three already agreed (one-line ratifications, not re-disputed): channel set `{telegram,discord}` + identity required + rate-limit-first + turn dataclass (`arclink_public_bots.py:78,730-760,7125-7144`); Telegram webhook authn 401/503 (`arclink_hosted_api.py:2889-2901`); Discord order timestamp→Ed25519→reserve and response type 4/7 (`arclink_discord.py:230-258,469-485,551-556`); Telegram-only-shared-secret boundary MEDIUM (`arclink_hosted_api.py:2889-2901`); LOW cluster (truncation/entities-pre-truncation/docker-fallback-swallow/process-local cache) — all ratified, code matches.

---

## CODEX NEW FINDINGS — CONFIRMED vs REJECTED

### CONFIRMED (net-new federation risks)

- **HIGH — `/credentials` reveals the dashboard password into the public channel with no DM/ephemeral guard.**
  Re-verified: `_credentials_reply` builds the raw secret into both `reply` and `telegram_reply` text and into `Copy Password` / `copy_text=raw_secret` buttons (`arclink_public_bots.py:3705-3750`). The credential command dispatch passes only channel/identity/session/deployment — no chat-type input (`arclink_public_bots.py:7608-7622`). Telegram sends to `chat_id` unconditionally (`arclink_hosted_api.py:2980-2984`). The Discord response `data` dict carries only `content`(+`components`) with **no `flags:64` (EPHEMERAL)** (`arclink_discord.py:469-471`). So in a group chat / non-DM Discord channel the first reveal IS the leak; the record's "revealed once then removed" framing is incomplete because removal only affects *future* responses. This becomes a net-new HIGH federation risk.

- **MEDIUM — direct-checkout URL token is a reusable bearer that re-arms the browser-claim/session-claim path.**
  Re-verified the full chain: `_public_bot_checkout_token_valid` only digest-compares; the URL `token` is never marked single-use (`arclink_hosted_api.py:799-807`). On `checkout_state in {open,paid}` and matching plan, the redirect re-issues a FRESH `browser_claim_proof_hash` cookie every call (`arclink_hosted_api.py:835-843` → `_issue_onboarding_claim_cookie:573-589`). The claim API then mints a full authenticated user session from that proof (`arclink_api_auth.py:4996` `create_arclink_user_session`). The claim *proof* is single-use+bounded-replay (`:5001-5004`), but because the URL token re-mints a new proof on each redirect, anyone holding the public-bot checkout URL can re-arm and re-claim → account session. The both-ends token contract (record CONTRACT #4) is true but not sufficient. Net-new MEDIUM.

- **LOW — Telegram reply send failure is swallowed; webhook returns 200 so Telegram never retries.**
  Re-verified: send wrapped in try/except that only logs a warning (`arclink_hosted_api.py:2963-2967` injected, `:2980-2984` live), then the handler returns 200 (`:3001-3013`). State changes made before send (e.g. credential `revealed_at` UPDATE committed at `arclink_public_bots.py:3684-3701`) persist even when the user sees no reply and gets no retry. Net-new LOW (and it compounds the HIGH: a credential can be marked revealed while the reply silently failed). Same fail-silent class Claude-verify flagged as GAP-D (entity-offset overrun on truncation) and GAP-E (narrow empty-content guard).

### REJECTED
- None. All three Codex OBJECT findings hold in code.

---

## CLAUDE ADVERSARIAL-VERIFY NEW GAPS — disposition
- **GAP-A (Discord retry-poison)** → CONFIRMED, promoted to MEDIUM federation risk (row 8). Codex independently CONFIRMED the same.
- **GAP-B (shared IP bucket)** → CONFIRMED as a refinement of the operator MEDIUM (row 6).
- **GAP-C (count-then-insert TOCTOU)** → CONFIRMED LOW (row 9).
- **GAP-D (entities not re-clamped on truncation)** → CONFIRMED LOW: entities computed pre-truncation (`arclink_telegram.py:1519-1524`), text truncated at send (`:224`); offsets can overrun → Telegram may reject the whole message. Net-new LOW.
- **GAP-E (Discord empty-content guard is narrower than stated invariant)** → CONFIRMED INFO: substitution only on `action=="agent_message_queued"` (`arclink_discord.py:463-468`); no current action proven to ship empty content elsewhere.

---

## SEVERITY CHANGES (only where code supports)

| Risk | From | To | Cite |
|------|------|----|------|
| `/credentials` reveal into public channel (no DM/ephemeral guard) | (absent / masked by "revealed once then removed") | HIGH | `arclink_discord.py:469-471`, `arclink_public_bots.py:3705-3750`, `arclink_hosted_api.py:2980-2984` |
| Reusable direct-checkout URL token re-arms session-claim | (record: "both-ends-verified", no risk) | MEDIUM | `arclink_hosted_api.py:799-807,835-843`, `arclink_api_auth.py:4996-5004` |
| Discord post-reservation failure non-retryable (GAP-A) | (absent in record verdict) | MEDIUM | `arclink_discord.py:556-570`, `arclink_hosted_api.py:3048-3049` |
| Telegram reply send swallowed → no retry | (absent) | LOW | `arclink_hosted_api.py:2963-2967,2980-2984,3001-3013` |
| Telegram entities not re-clamped on truncation (GAP-D) | (absent) | LOW | `arclink_telegram.py:1519-1524,224` |
| CONTRACT #5 operator confirm/approval gate | partial (deferred to CANON-14) | VERIFIED fail-closed | `arclink_telegram.py:1305-1322`, `arclink_operator_raven.py:225-230,412-419` |
| Record CONTRACT #1 `display_name` "both-ends-verified" | yes | corrected to consumer-only-with-fallback | `arclink_public_bots.py:3919-3951`, `arclink_notification_delivery.py:682` |

Unchanged: operator per-identity rate-limit bypass stays MEDIUM (refined by shared IP bucket); Telegram single-shared-secret boundary stays MEDIUM; the LOW/INFO cluster stays as recorded.

---

## STANDING DISAGREEMENTS
None. Every material point reconciled to one code-grounded truth. Two items remain *proof-gated, not disputed* (both models agree they cannot be closed from this checkout): the live Hermes `telegram_menu_commands(max_commands)` signature/return shape (PG-HERMES; no pinned Hermes source present — `arclink_telegram.py:482-485`, `arclink_public_bot_commands.py:149-153`), and the inner gateway bridge prompt grammar (owned by CANON-12). These are scope boundaries, not unresolved conflicts.

---

## FINAL BOTH-MODEL VERDICT
CANON-05 provably implements a complete channel-neutral public-bot turn engine with a single authoritative routing law, two transports with genuine fail-closed authn (Telegram shared-secret header + Discord Ed25519, the "sentinel rejection" being cryptographic not a blocklist), idempotent Discord dedupe, fail-closed 20/900 rate limiting, a fail-closed operator confirm/approval gate, and a both-ends-verified async selected-agent bridge (correcting `display_name` to consumer-only-with-fallback). The federation adds **five net-new risks the original record missed**: HIGH `/credentials` leaks the dashboard password into non-DM/non-ephemeral channels (the first reveal is the leak); MEDIUM reusable direct-checkout URL token re-arms the browser/session-claim path; MEDIUM Discord post-reservation failures are permanently non-retryable (stuck deferred ack); LOW swallowed Telegram send leaves committed state with no reply/retry; LOW pre-truncation entity offsets can reject long replies. Codex signed OBJECT(3); after re-opening every cite the adjudicator confirms all three Codex findings plus Claude-verify's GAP-A/B/C/D and upgrades CONTRACT #5 to verified. **FEDERATION SIGN-OFF: BOTH-MODEL-AGREED.**

---

<!-- CANON-REPAIR-STATUS:START -->
## Repair status

> Refreshed from [`research/canon/fixes/CANON-05-public-bots.fix.md`](../fixes/CANON-05-public-bots.fix.md) (tracked). The audit findings above remain the adjudicated spec; this block records the repair campaign state for this piece.

- Status: `c5cec97` committed.
- Summary: 9 fixed / 3 skipped / 0 needs-decision.
- Tests: 6 files run, all pass; py_compile on 6 touched Python modules passes
- Representative fixes:
  - HIGH — `/credentials` no longer reveals raw dashboard secrets into unsafe public contexts; Telegram requires private chat metadata, Discord guild interactions are allowed only through ephemeral-capable responses with `flags:64`. `python/arclink_public_bots.py:3670`, `python/arclink_public_bots.py:3768`, `python/arclink_public_bots.py:7647`, `python/arclink_telegram.py:1523`, `python/arclink_discord.py:481`
  - MEDIUM — public-bot direct-checkout URL tokens are now consumed once with a conditional metadata update before issuing claim cookies/opening checkout. `python/arclink_hosted_api.py:810`, `python/arclink_hosted_api.py:880`
  - MEDIUM — Discord interactions marked `failed`, plus stale `received` rows, can be retried instead of being permanently treated as duplicates. `python/arclink_discord.py:281`
<!-- CANON-REPAIR-STATUS:END -->
