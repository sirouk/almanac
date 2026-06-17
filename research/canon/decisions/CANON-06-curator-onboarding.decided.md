# CANON-06 — Curator Onboarding — DECIDED (final adjudication)

- Piece: CANON-06 (Curator Onboarding) — Telegram/Discord operator + Captain onboarding transport shell over CANON-04.
- Adjudicator: Claude Opus 4.8 (1M), DECISION mode. Code re-opened independently for every call below.
- Codex proposal under review: `research/canon/decisions/CANON-06-curator-onboarding.codex.md`.
- North star: `docs/arclink/sovereign-control-node-symphony.md` (sections "Operator Raven And Control" :202, "Identity, Access, And Session Governance" :1005).
- Code reality re-grounded against working tree at `python/arclink_curator_discord_onboarding.py` and `python/arclink_telegram.py` — NOT against the (now-stale) reconciled snapshot.

> Provenance note that changes the shape of this decision set: the ledger
> (`NEEDS_DECISION.md` CANON-06) lists exactly **one** deferred item — the LOW Discord
> operator-DM no-allowlist. The federation reconciled file additionally elevated a
> "net-new MEDIUM" (direct Discord `/approve`/`/deny`/SSOT/component buttons mutate
> without the configured approval code). **I re-opened the code and that MEDIUM is no
> longer true in the working tree.** It has since been fixed. So this adjudication
> decides the one live item and records the MEDIUM as *resolved-by-code*, not as an
> open operator call. (See "Resolved since reconcile" at the end.)

---

## DECISION 1 — Discord operator DM allowed without explicit user/role allowlist

[VERDICT] **refine** (Codex's direction is right; its prescription over-rotates against the symphony's own text, an existing deliberate test contract, and Telegram parity).

### The question
`_operator_discord_subject_allowed(subject, *, guild)` (`python/arclink_curator_discord_onboarding.py:273-294`) returns `True, ""` for **any** sender when no `ARCLINK_OPERATOR_DISCORD_USER_IDS`/`ROLE_IDS` is configured **and** `guild is None` (a DM). It fails closed for guild channels with no allowlist (`:288-293`). Should the no-allowlist DM lane be closed, and if so, how?

### My independent reasoning (code re-grounded)
The DM lane only opens under three stacked preconditions, all enforced upstream in `_ensure_operator_channel` (`:413-437`) and `_handle_operator_channel_message` (`:586-593`):
1. Discord is an enabled operator surface (`_operator_discord_enabled()`), AND
2. `_operator_channel_id()` (`:250-265`) is non-empty — i.e. either `ARCLINK_OPERATOR_DISCORD_CHANNEL_ID` is explicitly set, OR Discord is the *primary* and `operator_notify_channel_id` supplies it, AND
3. the interaction/message channel id **exactly equals** that configured operator channel id (`:423-428`, `:587-588`).

So the residual surface is narrow: a **deliberately configured** Discord DM channel id, no allowlist, and any human who can post in that exact 1:1 DM. In Discord a 1:1 DM channel has exactly two members (the bot + one user; `intents.default()` at `:223-226` does not enable group-DM/members privileged intents), so in practice only that one human can post. That is why DISSECT/the section ranked it **LOW**, and I agree it is LOW, not MEDIUM.

But the symphony bar is cross-surface identity parity, and here the comparison to Telegram is decisive. Telegram's no-allowlist fallback (`operator_telegram_sender_allowed`, `python/arclink_telegram.py:1226-1233`) returns True only when `platform=="telegram" AND configured_chat AND chat==configured_chat AND kind=="private" AND chat==sender`. Because a Telegram private chat's `chat_id` **equals** the user id, that fallback effectively **pins identity** to the configured operator's own private chat — `chat==sender` is an identity bind, not just a channel bind. The Discord DM branch has **no equivalent identity pin**: a Discord DM channel id is opaque and is not equal to the user id, so the code binds *channel* but never *who*. That is the real, symphony-relevant gap — not "DM is allowed," but "Discord trusts channel where Telegram trusts channel-AND-identity."

### Where I agree with Codex, and where I differ
- **Agree (direction):** current Discord posture is below the symphony bar; it must converge with Telegram's posture so "the same action cannot be made safer or more dangerous merely by choosing chat instead of dashboard."
- **Differ (prescription):** Codex says *require* an allowlist for DM operator control (remove `guild is None -> True` entirely, mandate `ARCLINK_OPERATOR_DISCORD_USER_IDS`). I reject that as over-rotation on three independent grounds:
  1. **Symphony text contradicts it.** "Operator Raven And Control" (`:286-294`) describes the *intended* design as fenced "by the existing Discord user/role allowlist ... which fails closed **for guild channels** with no allowlist." The symphony scopes the allowlist mandate to guild channels and is deliberately silent on (permissive of) the solo-DM case. Codex's own anchor does not say "DM requires allowlist."
  2. **A deliberate existing test contract contradicts it.** `tests/test_arclink_operator_raven.py:1098` asserts `expect("guild is None" in discord_text, "Discord operator DMs should remain available when no guild allowlist is configured")`. This is an intentional product contract, not an accident. Codex's plan would have to delete this assertion; I would keep its intent.
  3. **It breaks Telegram parity in the WRONG direction.** Telegram does NOT require an allowlist for the solo operator's own private DM. It pins identity via `chat==sender==configured_chat`. True parity is to give Discord the *same identity pin*, not to make Discord *stricter* than Telegram. Codex's plan makes the two surfaces asymmetric again, just inverted.

### FINAL PLAN
Keep the no-allowlist Discord DM lane open (preserve solo-operator UX, honor symphony `:286-294` and the `:1098` test intent), but **close the actual identity gap** so Discord matches Telegram's `chat==sender` posture and **fails closed when the DM channel was not deliberately configured**. Concretely, in `python/arclink_curator_discord_onboarding.py`:

1. **Tighten the `guild is None` branch** of `_operator_discord_subject_allowed` to trust the DM **only when the operator DM channel id was set EXPLICITLY** via `ARCLINK_OPERATOR_DISCORD_CHANNEL_ID` — i.e. the operator's deliberate, identity-equivalent binding for that 1:1 channel — and to fail closed otherwise. The silent primary-default path (`operator_notify_platform == "discord"` reusing `operator_notify_channel_id`, `:262-264`) should NOT auto-open a no-allowlist DM operator surface; it must require either the explicit channel id or an allowlist. This mirrors Telegram, where the no-allowlist fallback only fires on the *configured* private channel, never an inferred one. Mechanically: thread an `explicit_dm_channel: bool` (true iff `os.environ`/`config_env_value` `ARCLINK_OPERATOR_DISCORD_CHANNEL_ID` is non-empty) into `_operator_discord_subject_allowed`, and in the `guild is None` branch return `True` iff `explicit_dm_channel`, else return the existing guild-style fail-closed message adapted for DMs ("set ARCLINK_OPERATOR_DISCORD_CHANNEL_ID explicitly, or add a user/role allowlist").
2. **Leave the allowlisted and guild paths exactly as they are** — they already fail closed correctly.
3. **Bootstrap/CLI:** in `bin/bootstrap-curator.sh` (Discord operator-channel setup) and any `arclink-ctl channel reconfigure operator` flow, when Discord-as-secondary is chosen, prompt for `ARCLINK_OPERATOR_DISCORD_CHANNEL_ID` explicitly and recommend (do not force) `ARCLINK_OPERATOR_DISCORD_USER_IDS`. Persist via the existing `set_config_value` rail.
4. **Tests:** update `tests/test_arclink_operator_raven.py:1095-1098` so the source-grep contract asserts the *narrowed* truth: no-allowlist DM operator control is allowed **only when the explicit operator DM channel id is configured**, and an inferred/primary-default DM with no allowlist is rejected. Add a behavioral case to `tests/test_arclink_curator_onboarding_regressions.py` (alongside the existing `:831` "operator private DM opens onboarding" case) covering: (a) explicit DM channel, no allowlist → allowed; (b) primary-default DM channel, no allowlist → rejected; (c) allowlisted DM → allowed regardless. (Note: the workspace `tests/` write constraint from CANON-29 may force the behavioral assertions into an existing runnable file; the source-grep update in `test_arclink_operator_raven.py` is the load-bearing contract change.)
5. **Live-proof gate + evidence:** if a live Discord bot token is available, validate the configured operator channel with the smallest safe call and record **redacted** evidence under **PG-BOTS** (no token, no channel id in plaintext). If validation cannot run, fail closed (per Secrets section `:1056-1057`). No DB schema change; no onboarding-state migration; preserve all existing state.

### Symphony anchor (quoted)
- "Operator Raven And Control" (`docs/arclink/sovereign-control-node-symphony.md:291-294`): *"Discord-as-secondary keys its operator channel off `ARCLINK_OPERATOR_DISCORD_CHANNEL_ID` and stays fenced by the existing Discord user/role allowlist ... which fails closed for guild channels with no allowlist."* — my plan makes the *explicitly configured DM channel id* the identity bind, exactly the primitive this line names, while keeping guild fail-closed intact.
- "Identity, Access, And Session Governance" (`:1025-1027`): *"Rate limits, replay protection, nonce/confirmation, channel allowlists, and reason capture should be consistent enough that the same action cannot be made safer or more dangerous merely by choosing chat instead of dashboard."* — closing the Discord-vs-Telegram identity-pin asymmetry is precisely this convergence.

### Effort / blast-radius
**low** (Codex estimated med; my narrower refinement is smaller). Touches: one helper in the Discord adapter (`_operator_discord_subject_allowed` + one bool thread-through), the bootstrap/ctl operator-channel prompt, and two focused tests. No DB schema, no Captain-onboarding state migration, no change to the allowlisted or guild paths, no change to outbound notifications. Blast radius is confined to *inbound no-allowlist Discord DM operator control with a non-explicitly-configured channel* — a configuration that the symphony's own intended design (`:291`) already expects to be explicit, so few-to-no real operators are in that exact state.

---

## Resolved since reconcile (not an open operator decision)

**Discord approve/deny/SSOT/component approval-code asymmetry — RESOLVED IN CODE.**
The reconciled federation file (`research/canon/reconciled/CANON-06-...md`) elevated a "net-new MEDIUM": that direct Discord `/approve`/`/deny`, operator-channel text, and `arclink:upgrade|pin-upgrade|ssot` component buttons mutate without enforcing the configured approval code, unlike Telegram. Re-opening the current working tree, that is **no longer true**:
- Text `/approve`/`/deny`: `_discord_operator_action_tail` enforces the code and fails closed (`python/arclink_curator_discord_onboarding.py:124-135`, called at `:673-677`).
- Slash `/approve`/`/deny`: `_discord_operator_code_ok(operator_code)` fails closed (`:113-115`, enforced `:738-741`, `:755-757`).
- `/retry-contact`: `_discord_operator_code_ok` / `_discord_retry_contact_target` enforce the code (`:831-833`, `:137-147`).
- Component buttons: `_discord_component_requires_operator_code` gates `ssot:approve/deny` and `upgrade|pin-upgrade:dismiss/install`, failing closed (`:148-159`, enforced in `on_interaction` `:1163-1165`).
The approval-code second factor is now symmetric Telegram↔Discord. No operator decision is required here; the reconciled snapshot is simply stale on this point. (This is exactly why the brief says re-open the code: the symphony is intent, the code is reality.)

**Two MEDIUM hygiene findings (dead `arclink_upgrade_last_dismissed_sha`, unbounded `settings` seen-message growth)** were NOT in the deferred ledger for CANON-06 and are repair-campaign items, not operator design forks. They should be fixed as plain hygiene (read or remove the dead dismiss key; add a TTL/sweep for `curator_discord_onboarding_seen_message:*`) — note the section already shows a `_prune_discord_seen_messages` sweeper now exists at `:299-318`, so the growth MEDIUM is partially mitigated in the working tree. Neither needs an operator call.

---

## STANDING DISAGREEMENTS
None that require an operator product fork. Decision 1 is a clear refine with a single converged plan; the one item Codex and I differ on (require-allowlist vs pin-to-explicit-channel) resolves cleanly in favor of the explicit-channel pin because the symphony text, the existing test contract, and Telegram parity all point the same way.
