# CANON-06 — Curator Onboarding — RECONCILED (Federation both-model truth)

- Piece: CANON-06 (Curator Onboarding)
- Codex (GPT-5.5 xhigh) sign-off: **OBJECT(3)** — one material refinement: the record's blanket "mutations are double-gated" is overbroad.
- Final adjudicator: Claude Opus 4.8 (1M), code re-opened independently for every disputed point.
- Federation sign-off: **BOTH-MODEL-AGREED** — every material point reconciles to one code-grounded truth once the record's "double-gated" wording is narrowed. No standing disagreements remain.

Method: for each REFUTE/REFINE/new-finding I re-opened the cited code. Code wins over comments/names/prior claims.

---

## RESOLUTION TABLE (disputed + new-finding points)

| Point | Winner | Deciding cite |
|---|---|---|
| **Record's "mutating operator commands are double-gated (allowlist + hmac.compare_digest)" is overbroad** — direct Discord approve/deny/SSOT have NO approval-code rail | **codex** | Discord `/approve`/`/deny` slash → `_run_operator_action` after `_ensure_operator_channel` only: `arclink_curator_discord_onboarding.py:600-608,610-619`; text path `:539-556`; `_ensure_operator_channel` does channel-id + allowlist only `:281-305`; `_run_operator_action` (onb/req/ssot mutate, no code) `:206-253`; only approval-code use in the whole Discord file is for Raven commands `:310-323` (grep: 47-50,316-317 are the sole `approval_code` refs) |
| Telegram typed `/approve`/`/deny` DOES enforce the code (asymmetry is real) | **both** (record+codex agree) | `_handle_operator_command:411` → `_operator_approval_tail` → `hmac.compare_digest` `:287`; aborts on mismatch `:412-413` |
| Telegram `arclink:` callback approve/deny/install forces typed code when configured | **both** | `:874` `if _operator_approval_code() and action in {approve,deny,install}` → "Use the typed operator command with the approval code" `:898-904` |
| Discord `arclink:ssot:`/`arclink:upgrade:`/`arclink:pin-upgrade:` component buttons also mutate without code | **codex** | `on_interaction:973-993` → `_ensure_operator_channel` then `_run_operator_action(scope=...)`, no approval_code |
| Verifier A6 / record INFO "double `.lower()` at :312" is wrong | **both** (verifier refuted record, codex ratified refutation) | single `.lower()` inside `_telegram_command_token:124-125`; `_user_command_requested:310-316` then only `.lstrip("/")`/`.replace("-","_")` |
| Verifier B1 — Discord claim-before-process permanently drops on handler exception | **both** (codex CONFIRM) | `on_message:927` claims+commits seen-row before `:929-947` handlers, no try/except; `_claim_discord_message_once:190-204` |
| Verifier B2 — `_send_replies` swallows ALL send errors (overbroad as stated) | **codex** (REFINE) | `_send_replies:385-441`: component sends `:402-410` and non-origin sends `:421-441` ARE swallowed, but same-origin interaction-response `:394-399` and same-origin non-component `channel.send` `:419` PROPAGATE |
| Verifier B3 — malformed upgrade-action callback raises UnboundLocalError, caught fail-closed | **both** (codex CONFIRM) | `_handle_operator_callback:973-996` leaves `result_text`/`replacement_text` unset for unknown action → `:1039`/`:1046` raise → broad `except :1051` compact-error alert |
| Seam 7 (`register-curator`/`curator-refresh` consumer) | **codex** (closed what record left open) | `register_curator:1438-1477` parses `--channels-json` via `json.loads:1472` → `register_agent`; record honestly marked it UNREAD (`section :91`) — not a false claim, just an open the record did not close |
| MEDIUM dead `arclink_upgrade_last_dismissed_sha` (written, never read) | **both** | writers `arclink_curator_onboarding.py:975`, `arclink_curator_discord_onboarding.py:272`; live key `arclink_upgrade_last_notified_sha` read `arclink_ctl.py:1821-1878`; zero readers of dismissed key |
| MEDIUM unbounded `settings` growth via `curator_discord_onboarding_seen_message:<id>` | **both** | `arclink_curator_discord_onboarding.py:190-204` raw `INSERT OR IGNORE`, no deleter/TTL for that prefix |
| GAP-029 Telegram gate unification (seam 3) both-ends-verified | **both** | producer `_operator_sender_allowed:231-248` → 7 kwargs consumed by `arclink_telegram.py:1144-1205`; same helper is hosted-API webhook gate |
| Operator Raven mutating commands actor+confirm gated (the part of "double-gate" that IS true) | **both** | `_require_operator_actor`/`_require_operator_confirmation` `arclink_operator_raven.py:400-418`; Discord/Telegram Raven paths strip+confirm code `discord:310-323`, `telegram:345-356` |
| Ownership checks on completion/backup/Notion callbacks | **both** | `discord:1001-1010,1039-1045`; `telegram:531-541,644-655,739-750` compare stored `sender_id`+`chat_id` |
| Telegram poison-pill bounded; failure-write-raises hot-loop self-check | **both** | advance only on success `:1212-1214` or limit `:1185-1188`, else `break` no-advance; raise inside `with` propagates to swallowing outer loop `:1247-1252` |
| Token de-confliction interlock holds in canonical launcher | **both** | `curator-gateway.sh:27-38,72-123,130-159`; `common.sh:741-774` |
| `process_update` keyword-only; TUI launcher `exec env HERMES_HOME=...` | **codex+verifier** (record prose imprecise, behavior matches) | `arclink_curator_onboarding.py:1122`; `curator-tui.sh:21-33` |

---

## CODEX NEW-FINDINGS — CONFIRMED vs REJECTED

### CONFIRMED (net-new federation risk)
1. **MEDIUM — Configured operator approval code is NOT enforced on direct Discord approve/deny/SSOT paths.** Re-verified: the only `approval_code` enforcement in `arclink_curator_discord_onboarding.py` is inside `_operator_raven_response` for Raven commands (`:310-323`). Direct approvals — `/approve`/`/deny` slash (`:600-619`), operator-channel text (`:539-556`), and `arclink:ssot:`/`arclink:upgrade:`/`arclink:pin-upgrade:` components (`:973-993`) — reach `_run_operator_action` (`:206-253`) after channel-id + allowlist only (`_ensure_operator_channel:281-305`). They mutate onboarding sessions, bootstrap requests, and SSOT pending writes. The Telegram side enforces the code on the equivalent typed (`:411`/`:287`) and callback (`:874-904`) paths, so this is a genuine Telegram-vs-Discord asymmetry, not a global design choice. **CONFIRMED → net-new MEDIUM.**

### Codex adjudications ratified (CONFIRM items, one-line each)
- Dead dismiss key, settings growth, GAP-029 seam, onboarding-flow seam, ownership checks, poison-pill, token interlock, 23-command Telegram catalog, live-systemd-surface, B1/B3 — all re-confirmed against the same code the record/verifier cited; no daylight.

### Codex REFINE items accepted as the truer reading
- B2 narrowed: same-origin interaction-response and same-origin non-component `channel.send` propagate; only component sends and non-origin sends are swallowed (`:385-441`). The verifier's "wraps every send" was overbroad.
- Seam 7 closed by Codex (`register_curator:1472` `json.loads`); record's "unread" was honest, not wrong.

### REJECTED
- None. No Codex finding failed re-verification.

---

## SEVERITY CHANGES

| Risk | From | To | Cite |
|---|---|---|---|
| Discord operator approve/deny/SSOT runs without the configured approval code (Codex new finding) | (absent in record) | **MEDIUM** (net-new) | `arclink_curator_discord_onboarding.py:206-253,539-556,600-619,973-993`; only Raven path enforces code `:310-323` |
| Verifier B2 "silent reply swallow" | LOW (record/verifier framing as blanket) | **LOW (scoped)** — applies to component + non-origin sends only; same-origin direct sends propagate | `arclink_curator_discord_onboarding.py:394-399,419` (propagate) vs `:402-410,421-441` (swallow) |

All other severities (two MEDIUMs, the LOWs, INFOs) stand unchanged — code supports them as written.

---

## CORRECTION TO RECORD WORDING (the one material change)

The record's VERDICT point 2 and the RISKS framing — "mutating operator commands are double-gated (allowlist + `hmac.compare_digest` approval code) and fail closed" — must be narrowed to:

> Mutating operator commands are double-gated **on the Telegram surface and for Operator Raven commands on both surfaces** (allowlist + approval-code / actor+confirm). **Direct Discord `/approve`/`/deny`/SSOT and the `arclink:upgrade|pin-upgrade|ssot` component buttons are gated by channel-id + allowlist only — the configured approval code is not enforced there.**

This is the single point Codex objected to (OBJECT(3)), and the code at `arclink_curator_discord_onboarding.py:206-253,600-619,973-993` proves it. With this narrowing applied, the record and Codex agree.

---

## STANDING DISAGREEMENTS
None. Every material point reconciled to one code-grounded truth. (Seam 7 was the only honestly-open item in the record; Codex closed it from `arclink_ctl.py:1438-1477` — now verified.)

---

## FINAL BOTH-MODEL VERDICT
CANON-06 **provably does its job** as a transport + gating shell around CANON-04's onboarding engine, with these federation-settled truths:
- Load-bearing strengths the record claimed are real and code-verified: GAP-029 Telegram gate unification, ownership checks on user callbacks, bounded Telegram poison-pill ledger, token de-confliction interlock, Operator Raven actor+confirm gate.
- The two MEDIUM record findings (dead `arclink_upgrade_last_dismissed_sha`, unbounded `settings` seen-message growth) are independently re-confirmed by all three passes.
- **Net-new MEDIUM (Codex):** the approval-code second factor is a Telegram-only / Raven-only rail; direct Discord approve/deny/SSOT (slash, text, and component buttons) mutate after channel+allowlist alone. The record's "double-gated" claim is corrected to be surface-specific.
- Verifier additions B1 (Discord claim-before-process silent drop) and B3 (fail-closed UnboundLocalError dead branch) stand; B2 is accepted in its Codex-narrowed (scoped) form.
- The record's INFO "double `.lower()`" claim is refuted (does not exist in code).

Federation sign-off: **BOTH-MODEL-AGREED** (record's "double-gated" wording narrowed per the Discord asymmetry; no residual disputes).
