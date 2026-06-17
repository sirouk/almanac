<<<DECIDED CANON-05>>>
# CANON-05 — Public Bots (Telegram/Discord) — FINAL ADJUDICATED DECISIONS

- Piece: CANON-05 — Public Bots (Telegram/Discord)
- Owned files: `python/arclink_public_bots.py`, `python/arclink_telegram.py`, `python/arclink_discord.py`, `python/arclink_public_bot_commands.py`
- Adjudicator: Opus 4.8 final (DECISION mode). Method: re-opened every fix cite myself (sed/rg), ran the owned-file test suite.
- Codex proposal: `research/canon/decisions/CANON-05-public-bots.codex.md` — recommends a NO-OP (no operator decision deferred).
- Deferred-decision source of truth: the `## CANON-05` block of `research/canon/NEEDS_DECISION.md` reads exactly `- None.`
- Repair status (from `research/canon/fixes/CANON-05-public-bots.fix.md`): `9 fixed / 3 skipped / 0 needs-decision`, committed `c5cec97`.

---

## VERDICT SUMMARY

**[NO OPERATOR DECISION DEFERRED — agree-codex]**

CANON-05 has **zero** deferred operator calls. Codex is right, and I reached the same conclusion independently before reading its proposal: the ledger lists `None`, the fix report records `NEEDS-DECISION: None`, and — critically — I re-opened the code and confirmed that every formerly-operator-sensitive defect the federation surfaced is now a *landed fail-closed repair*, not an open question. There is nothing here for the operator to choose. Inventing a schema/contract/threat-model call would be noise.

I did NOT take Codex's word for it. The risk in a "nothing to decide" verdict is that a real decision is hiding inside a "skipped" item or a "proof-gated" standing item. I checked all three skip reasons and both standing items; none is a CANON-05 product fork. Evidence below.

---

## INDEPENDENT VERIFICATION — every formerly-sensitive item is a landed fix, not a decision

The reconciled record (`research/canon/reconciled/CANON-05-public-bots.reconciled.md`) raised five net-new risks that *could* have become operator decisions (threat-model severity calls, a session-claim contract). I re-opened each in code to confirm the repair campaign closed them fail-closed, so none escalates to a deferred call:

| Federation risk (reconciled) | Where it could have been a decision | Code reality now (re-opened) | Verdict |
|---|---|---|---|
| HIGH `/credentials` leaks dashboard password into non-DM/non-ephemeral channel | "what is the acceptable reveal surface?" — a threat-model call | `_credential_delivery_is_private` gates reveal; non-private/non-ephemeral returns `credentials_private_channel_required` and never materializes the secret (`arclink_public_bots.py:3670-3683,3768-3775`); metadata is real (`telegram_chat_type` `arclink_telegram.py:1525`; `discord_chat_type`/`discord_ephemeral_supported` `arclink_discord.py:485-486`); Discord adds `flags:64` ephemeral on non-DM credential reveals (`arclink_discord.py:497-498`). FAILS CLOSED. | LANDED — no decision |
| MEDIUM direct-checkout URL token re-arms session-claim | "is the token bearer-reusable by design?" — a session-claim contract call | `_consume_public_bot_checkout_token` is an atomic compare-and-swap UPDATE (`WHERE ... metadata_json = ?`, `rowcount != 1` → rollback), removes the per-plan verifier and stamps `public_bot_checkout_consumed_at` BEFORE any claim cookie issues, on BOTH the `{open,paid}` redirect and the fresh-checkout path (`arclink_hosted_api.py:822-865,880,908`). Token is now genuinely single-use. | LANDED — no decision |
| MEDIUM Discord post-reservation failure permanently non-retryable | "accept stuck deferred-ack?" — a severity call | `_reserve_discord_interaction` resurrects `failed` rows and stale `received` rows past `DISCORD_INTERACTION_RECEIVED_RETRY_SECONDS` instead of rejecting as duplicate (`arclink_discord.py:281-308`). Retryable. | LANDED — no decision |
| MEDIUM operator path bypasses per-identity rate limit | "should operator turns be rate-limited?" — a policy call | `_handle_operator_telegram_update` now calls `check_arclink_rate_limit(scope="operator:telegram", subject=telegram:<id>, ...)` and raises before Operator Raven dispatch (`arclink_telegram.py:1335-1342`). Identity-scoped, fail-closed. | LANDED — no decision |
| LOW cluster (swallowed Telegram send, pre-truncation entity overrun, count-then-insert TOCTOU) | severity calls | Send failures return 502 for Telegram retry + reopen credential handoff (`arclink_hosted_api.py:3002,3078`); entities clamped/dropped after truncation (`arclink_telegram.py:216`); rate-limit helper wraps count+insert in `BEGIN IMMEDIATE` when it owns the commit (`arclink_api_auth.py:407-440`). | LANDED — no decision |

Tests: ran `tests/test_arclink_public_bots.py`, `tests/test_arclink_discord.py`, `tests/test_arclink_telegram.py`, `tests/test_arclink_api_auth.py`, `tests/test_arclink_public_bot_commands.py` → **100 passed** (the only owned/touched modules; the cross-piece `test_arclink_hosted_api.py` is the campaign's responsibility and is recorded green in the fix report).

---

## THE THREE "SKIPPED" ITEMS ARE NOT OPERATOR DECISIONS — confirmed

1. **Telegram shared-secret-only webhook auth.** The configured `X-Telegram-Bot-Api-Secret-Token` IS Telegram's own auth rail, and the code already fails closed on unset/mismatch with 401/503 (`arclink_hosted_api.py:2889-2901`). Stronger per-update signatures are not a thing Telegram offers; any hardening here is an *external ingress/threat-model* contract owned by CANON-02's proxy/header trust model, not a CANON-05 product fork. Correctly skipped.

2. **PG-HERMES live `telegram_menu_commands(max_commands)` signature + inner gateway bridge prompt grammar.** Proof-gated (no pinned Hermes source in this checkout) and CANON-12 scope respectively. These are scope boundaries, not unresolved conflicts. Correctly skipped.

3. **>4000-char Telegram truncation itself.** Retained existing bounded-transport behavior; the rejection-causing entity-offset bug *around* truncation was fixed. No contract change. Correctly skipped.

None of the three is a schema/contract/threat-model call the operator must make *for CANON-05*. The one that touches a real cross-piece contract (Telegram auth) is explicitly handed to CANON-02, which is where it belongs.

---

## STANDING PROOF-GATED ITEMS ARE SCOPE BOUNDARIES, NOT FORKS

The reconciled record's two "proof-gated, not disputed" items — the live Hermes `telegram_menu_commands` shape and the inner gateway bridge grammar — are both already owned elsewhere (PG-HERMES live-proof gate; CANON-12). They are NAMED live-proof gates and cross-piece scope boundaries, exactly as the symphony's "every step has a NAMED live-proof gate" prescribes. They do not become operator decisions.

---

## SYMPHONY ANCHOR

`docs/arclink/sovereign-control-node-symphony.md` — the public-bots law: **"Telegram and Discord own message delivery constraints; ArcLink owns command registration, channel binding, role authorization, fallback copy, and retry state"** plus the cross-cutting safety rail **"Rate limits and replay resistance for onboarding, login, pairing, checkout, webhook, bot command, share request, provider, and admin paths."** And the campaign-wide invariant **"every step ... FAILS CLOSED ... preserve state by default + leave redacted evidence."**

The landed CANON-05 code now satisfies all of this: ArcLink owns retry state (Discord resurrection, Telegram 502-for-retry), replay resistance is enforced on the checkout and bot-command paths (single-use token, identity-scoped operator rate limit, atomic rate-limit reservation), the credential reveal fails closed onto private/ephemeral surfaces, and credential reveals leave a redacted `public_bot:dashboard_credential_revealed` event (metadata records only `credential_kind`, never the secret — `arclink_public_bots.py:3713-3720`). The code already moved to where the symphony points; the operator has nothing left to steer.

---

## FINAL PLAN

**No action required.** Ratify the repair campaign's CANON-05 outcome as-is. Do not open an operator decision for this piece. Close CANON-05 as `0 needs-decision` and let the two standing proof-gated items ride their existing gates (PG-HERMES live-proof; CANON-12).

- Effort: low (verification-only; zero new code).
- Blast radius: none. This is a confirmation that no change is owed, not a change.

<<<DECIDED CANON-05>>>
