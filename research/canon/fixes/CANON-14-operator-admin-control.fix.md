<<<CODEX-FIX-START CANON-14>>>
## CANON-14 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: python/arclink_action_worker.py, python/arclink_control.py, python/arclink_curator_discord_onboarding.py, python/arclink_curator_onboarding.py, python/arclink_enrollment_provisioner.py, python/arclink_operator_raven.py, tests/test_arclink_action_worker.py, tests/test_arclink_operator_raven.py
TESTS: 8 files run: 7 pass / 1 NEEDS-REVIEW; targeted new action-worker regressions pass; py_compile pass
### Fixed (severity — what — path:line)
- MEDIUM — stale action recovery now fails terminally after an attempt cap and marks running attempts failed instead of re-queueing forever — python/arclink_action_worker.py:2314
- MEDIUM — operator_actions enqueue now uses `BEGIN IMMEDIATE`; host-upgrade dedupe is source-aware; running claim is guarded by status/staleness — python/arclink_control.py:8423, python/arclink_control.py:8744
- MEDIUM — provisioner consumers now honor failed operator-action claims before live side effects — python/arclink_enrollment_provisioner.py:2358
- MEDIUM — dismissed/silenced pin-upgrade notifications no longer count as active queueable targets — python/arclink_control.py:9779
- LOW — executor selection failure now records a failed attempt/event instead of leaving a claimed running row without an attempt — python/arclink_action_worker.py:722
- LOW — Operator Raven button nonce consume now burns under a transaction with a conditional update, closing double-consume race — python/arclink_operator_raven.py:1382
- LOW — Telegram/Discord callback paths now reject direct mutating Operator Raven commands; one-tap nonce commands remain allowed — python/arclink_curator_onboarding.py:831, python/arclink_curator_discord_onboarding.py:1130
- LOW/INFO — Operator Raven redaction now handles colon/JSON/bare secret forms; action-worker safe error recording no longer re-crashes on redacted secret-ish keys — python/arclink_operator_raven.py:2439, python/arclink_action_worker.py:83
- INFO — host-upgrade dedupe no longer silently attaches an operator-raven request to an active non-operator source row — python/arclink_control.py:8333
### Skipped (risk-accepted / standing / out-of-scope — why)
- academy_apply symlink-ancestor containment — skipped per binding policy for CANON-14 standing threat-model disagreement; code fact is real, but the canon marks the severity/precondition judgment as unresolved.
- ctl token persistence to env files — not changed; canon frames it as broad CANON-27/shared operational attack surface with existing 0600 handling, not a narrow CANON-14 quick fix.
### NEEDS-DECISION (ambiguous; left for human)
- tests/test_arclink_action_worker.py still fails at `test_academy_apply_action_materializes_local_hermes_home_when_authorized`: current code fails closed because PG-PROVIDER live review is not complete. I did not rewrite that CANON-17/Academy expectation in this CANON-14 repair.
### Cross-piece edits made (if any) + tests added
- Cross-piece edits: python/arclink_control.py, python/arclink_enrollment_provisioner.py, python/arclink_curator_onboarding.py, python/arclink_curator_discord_onboarding.py.
- Tests added/adjusted: operator action source dedupe + claim guard, silenced pin payload filtering, callback mutating-command guard assertions, redaction coverage, executor-selection failure attempt recording, stale recovery terminal cap.
- Passing files: tests/test_arclink_operator_raven.py, tests/test_arclink_admin_actions.py, tests/test_arclink_operator_agent.py, tests/test_arclink_control_db.py, tests/test_arclink_enrollment_provisioner_regressions.py, tests/test_arclink_curator_onboarding_regressions.py, tests/test_remote_ssh_key_onboarding.py.
<<<CODEX-FIX-END CANON-14>>>
