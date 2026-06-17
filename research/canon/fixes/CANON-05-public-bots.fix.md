<<<CODEX-FIX-START CANON-05>>>
## CANON-05 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: python/arclink_api_auth.py, python/arclink_discord.py, python/arclink_hosted_api.py, python/arclink_public_bot_commands.py, python/arclink_public_bots.py, python/arclink_telegram.py, tests/test_arclink_api_auth.py, tests/test_arclink_discord.py, tests/test_arclink_hosted_api.py, tests/test_arclink_public_bots.py, tests/test_arclink_telegram.py
TESTS: 6 files run, all pass; py_compile on 6 touched Python modules passes

### Fixed (severity — what — path:line)
- HIGH — `/credentials` no longer reveals raw dashboard secrets into unsafe public contexts; Telegram requires private chat metadata, Discord guild interactions are allowed only through ephemeral-capable responses with `flags:64`. `python/arclink_public_bots.py:3670`, `python/arclink_public_bots.py:3768`, `python/arclink_public_bots.py:7647`, `python/arclink_telegram.py:1523`, `python/arclink_discord.py:481`
- MEDIUM — public-bot direct-checkout URL tokens are now consumed once with a conditional metadata update before issuing claim cookies/opening checkout. `python/arclink_hosted_api.py:810`, `python/arclink_hosted_api.py:880`
- MEDIUM — Discord interactions marked `failed`, plus stale `received` rows, can be retried instead of being permanently treated as duplicates. `python/arclink_discord.py:281`
- MEDIUM — Operator Telegram path now has an identity-scoped rate limit before Operator Raven dispatch. `python/arclink_telegram.py:1335`
- LOW — Telegram reply send failures now return 502 for retry, and failed credential reveals reopen the handoff instead of leaving `revealed_at` committed. `python/arclink_hosted_api.py:3002`, `python/arclink_hosted_api.py:3078`
- LOW — Telegram entities are clamped/dropped after send-message truncation so Telegram does not reject overrun offsets. `python/arclink_telegram.py:216`
- LOW — shared rate-limit helper now wraps count+insert in `BEGIN IMMEDIATE` when it owns the commit, closing the normal TOCTOU window. `python/arclink_api_auth.py:407`
- LOW — Telegram command-scope cache is bounded; Docker command discovery fallback failures are logged. `python/arclink_telegram.py:812`, `python/arclink_public_bot_commands.py:146`
- INFO — Discord empty content now has a generic fallback, Discord sentinel-key docstring drift is corrected, and public-agent-turn now emits additive `display_name`. `python/arclink_discord.py:236`, `python/arclink_discord.py:497`, `python/arclink_public_bots.py:3947`

### Skipped (risk-accepted / standing / out-of-scope — why)
- Telegram shared-secret-only auth boundary: Telegram provides the configured webhook secret as the platform auth rail; existing code already fails closed on unset/mismatch. Stronger per-update signatures need an external ingress/threat-model decision.
- PG-HERMES live `telegram_menu_commands(max_commands)` signature and inner gateway bridge prompt grammar: canon marks these proof-gated / CANON-12 scope, not settleable from this checkout.
- Telegram >4000-character truncation itself: retained as the existing bounded transport behavior; the rejection-causing entity-offset bug around truncation was fixed.

### NEEDS-DECISION (ambiguous; left for human)
- None.

### Cross-piece edits made (if any) + tests added
- Cross-piece edits: `python/arclink_hosted_api.py` for checkout-token consumption and Telegram send-failure handling; `python/arclink_api_auth.py` for atomic rate-limit reservation.
- Tests added/updated in `tests/test_arclink_public_bots.py`, `tests/test_arclink_discord.py`, `tests/test_arclink_telegram.py`, `tests/test_arclink_hosted_api.py`, and `tests/test_arclink_api_auth.py`; also ran `tests/test_arclink_public_bot_commands.py`.
<<<CODEX-FIX-END CANON-05>>>
