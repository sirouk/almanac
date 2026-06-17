<<<CODEX-FIX-START CANON-29>>>
## CANON-29 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: tests/test_arclink_chutes_and_adapters.py, tests/test_arclink_docker.py, tests/test_arclink_executor.py, tests/test_arclink_fleet.py, tests/test_arclink_hosted_api.py, tests/test_deploy_regressions.py, tests/test_documentation_truths.py, tests/test_arclink_operator_raven.py, tests/test_arclink_notification_delivery.py
TESTS: 9 files run, all pass; AST direct-runner scan reports 0 missing; git diff --check pass
### Fixed (severity — what — path:line)
- HIGH — wired the remaining current-tree orphan tests into direct runners — tests/test_arclink_chutes_and_adapters.py:783; tests/test_arclink_docker.py:8240,8254; tests/test_arclink_fleet.py:606,607; tests/test_arclink_hosted_api.py:6496; tests/test_deploy_regressions.py:4544,4545.
- HIGH — made the J-19 share-grant broker proof run under the real `python3 tests/test_*.py` CI contract — tests/test_arclink_hosted_api.py:6496.
- MEDIUM — added a corpus guard that fails when module-level `test_*` functions are not wired into direct runners — tests/test_documentation_truths.py:342.
- MEDIUM — made systemd unit verification skip only when the host `systemd-analyze` cannot initialize unit paths, instead of failing on that host condition — tests/test_deploy_regressions.py:4125.
- MEDIUM — added direct upgrade-policy coverage for catalog ordering, grouping, aliases, read-only summaries, and unknown-component fail-closed behavior — tests/test_arclink_operator_raven.py:322.
- MEDIUM — added direct rejection-incident coverage for safe path creation, metadata redaction, 0600-ish permissions, relative/symlink root rejection, and symlink-leaf no-follow behavior — tests/test_arclink_notification_delivery.py:1806.
- LOW — removed stale hardcoded success counts from touched runners — tests/test_arclink_chutes_and_adapters.py:789; tests/test_arclink_docker.py:8290; tests/test_arclink_executor.py:2550; tests/test_arclink_fleet.py:625.
### Skipped (risk-accepted / standing / out-of-scope — why)
- GAP-019 trusted-host/root-equivalence design: not changed; only its fail-closed regression tests were wired into runners.
- Playwright browser CI seam: skipped as CANON-03/CANON-28-owned workflow/web scope, not CANON-29 test-corpus code.
- Loopback socket tests: skipped as deliberate hermetic local harness behavior, not a correctness/security defect.
- Executor/deploy “red in real CI” conclusion: left as the canon’s standing host-conditional disagreement; current `test_arclink_executor.py` and `test_deploy_regressions.py` both pass here.
### NEEDS-DECISION (ambiguous; left for human)
- Literal dedicated new `tests/test_arclink_upgrade_policy.py` / `tests/test_arclink_rejection_incidents.py` files could not be created because the `tests/` directory is not writable in this workspace. I added direct behavioral coverage inside existing runnable files instead.
### Cross-piece edits made (if any) + tests added
- No production or cross-piece code edits. Added test functions in existing files: direct-runner AST guard, direct `arclink_upgrade_policy` coverage, and direct `arclink_rejection_incidents` coverage.
<<<CODEX-FIX-END CANON-29>>>
