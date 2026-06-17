<<<CODEX-FIX-START CANON-06>>>
## CANON-06 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: python/arclink_curator_discord_onboarding.py, python/arclink_curator_onboarding.py, tests/test_arclink_curator_onboarding_regressions.py
TESTS: 2 test files + py_compile run, all pass
### Fixed (severity — what — path:line)
- MEDIUM — Enforced configured operator approval code on direct Discord operator mutations: text `/approve`/`/deny`/`/retry-contact`, slash `/approve`/`/deny`/`/retry-contact`, and mutating `arclink:ssot|upgrade|pin-upgrade` component callbacks now fail closed when the code is missing/wrong. `python/arclink_curator_discord_onboarding.py:100`
- MEDIUM — Bounded Discord seen-message settings rows with TTL, stale-processing cleanup, and max-row pruning; claims now use `processing` then mark `processed`. `python/arclink_curator_discord_onboarding.py:56`
- MEDIUM — Replaced dead `arclink_upgrade_last_dismissed_sha` writes with live `arclink_upgrade_last_notified_sha` updates on upgrade dismiss. `python/arclink_curator_onboarding.py:978`, `python/arclink_curator_discord_onboarding.py:404`
- LOW — Discord message handling now releases the seen-message claim and notifies/logs on handler failure instead of permanently dropping the message. `python/arclink_curator_discord_onboarding.py:1076`
- LOW — Discord reply-send failures now propagate instead of being swallowed after onboarding state advances. `python/arclink_curator_discord_onboarding.py:517`
- LOW — Telegram failure-ledger write failures now stop the worker instead of being swallowed into an endless retry loop. `python/arclink_curator_onboarding.py:1187`
- LOW — Telegram operator failure-notification send errors are now logged to stderr instead of silently disappearing. `python/arclink_curator_onboarding.py:217`
- INFO — Malformed Telegram upgrade callback actions now return a specific fail-closed error instead of falling through to an unbound local. `python/arclink_curator_onboarding.py:1000`
### Skipped (risk-accepted / standing / out-of-scope — why)
- INFO — Refuted double-`.lower()` claim: no current defect to fix.
- INFO — `has_curator_non_telegram_gateway_channels` naming drift left unchanged; it is a compatibility shell alias and renaming/removing it is not a safe quick win.
### NEEDS-DECISION (ambiguous; left for human)
- LOW — Discord operator DM allowed without explicit allowlist when the configured operator channel is a DM. This may be intentional DM-channel-as-operator identity behavior, so I left it unchanged.
### Cross-piece edits made (if any) + tests added
- No cross-piece production edits. Added CANON-06 regressions to `tests/test_arclink_curator_onboarding_regressions.py`.
- Ran: `python3 -m py_compile python/arclink_curator_onboarding.py python/arclink_curator_discord_onboarding.py tests/test_arclink_curator_onboarding_regressions.py`; `python3 tests/test_arclink_curator_onboarding_regressions.py`; `python3 tests/test_bootstrap_curator_regressions.py`.
<<<CODEX-FIX-END CANON-06>>>
