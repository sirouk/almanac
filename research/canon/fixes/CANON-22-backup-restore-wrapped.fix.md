<<<CODEX-FIX-START CANON-22>>>
## CANON-22 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: bin/arclink-restore-smoke.sh, bin/backup-agent-home.sh, bin/backup-to-github.sh, bin/common.sh, bin/configure-agent-backup.sh, python/arclink_wrapped.py, tests/test_agent_backup_regressions.py, tests/test_arclink_wrapped.py, tests/test_backup_git_regressions.py
TESTS: 3 test files + shell syntax + py_compile run, all pass
### Fixed (severity — what — path:line)
- HIGH — Wrapped no longer mints duplicate generated reports after enqueue failure; it retries the committed report, backs off failed retries, and emits the persistent operator notice only once — python/arclink_wrapped.py:47, python/arclink_wrapped.py:1102, python/arclink_wrapped.py:1057, python/arclink_wrapped.py:1174
- MEDIUM — Wrapped eligibility now counts injected Hermes session/turn activity instead of skipping session-only Captains — python/arclink_wrapped.py:435, python/arclink_wrapped.py:1204
- MEDIUM — 404/non-public-or-missing GitHub visibility now requires git read-access proof before backup proceeds on both shared and agent-home lanes — bin/common.sh:1416, bin/backup-agent-home.sh:203, bin/backup-to-github.sh:131
- MEDIUM — control-plane backup visibility refuses overrideable GitHub API bases unless the explicit test flag is set — bin/common.sh:1336
- LOW/MEDIUM — backup SSH known_hosts is no longer silent TOFU by default; github.com is pinned from GitHub’s published SSH fingerprints, and ssh-keyscan requires explicit opt-in — bin/common.sh:1474, bin/common.sh:1486, bin/common.sh:1521 (source: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints)
- LOW — agent-home restore-smoke now rejects symlinks that escape the restore tree or target excluded secrets/logs content — bin/arclink-restore-smoke.sh:180, bin/arclink-restore-smoke.sh:254
- LOW — configure-agent-backup verify no longer aborts when best-effort legacy systemd daemon-reload is denied — bin/configure-agent-backup.sh:257
### Skipped (risk-accepted / standing / out-of-scope — why)
- CANON-22 operator pin auto-push row: code-true but reconciled as CANON-15-owned, so not changed here.
- captain-wrapped claim/lease double-send risk: reconciled as CANON-23 delivery-loop-owned, so not changed here.
- `extra_json.render_kind` dead metadata: harmless producer-only outbox metadata; removing it would be wire-contract churn, not a correctness fix.
### NEEDS-DECISION (ambiguous; left for human)
- Quiet-hours local/DST semantics: current code is UTC-only; a real local-time fix needs a timezone/config contract.
- Backup reconcile single-writer locking: adding in-script flock/state locks would change the current timer/cron ownership model and needs an operator state-path decision.
### Cross-piece edits made (if any) + tests added
- Cross-piece: bin/common.sh is CANON-24 shared deploy helper code, edited minimally because CANON-22 backup scripts consume it.
- Tests added/extended in tests/test_arclink_wrapped.py, tests/test_backup_git_regressions.py, and tests/test_agent_backup_regressions.py for duplicate Wrapped retries, session-only eligibility, 404 read-access proof, API-base refusal, host-key pinning, and restore symlink screening.
<<<CODEX-FIX-END CANON-22>>>
