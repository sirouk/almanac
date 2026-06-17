<<<CODEX-FIX-START CANON-28>>>
## CANON-28 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: .github/workflows/install-smoke.yml, bin/ci-preflight.sh, bin/live-agent-tool-smoke.sh, bin/arclink-restore-smoke.sh, bin/arclink-docker.sh, bin/ci-install-smoke.sh, tests/test_deploy_regressions.py, tests/test_arclink_docker.py, tests/test_backup_git_regressions.py
TESTS: passes: ruff fatal lint, bash -n, py_compile changed tests, test_backup_git_regressions.py, test_arclink_docker.py, targeted CANON-28 deploy-regression tests. Not clean: test_deploy_regressions.py fails before CANON-28 additions on an unrelated current-tree Discord assertion; ci-preflight is blocked by sandbox socket PermissionError during fake vision server bind.

### Fixed (severity — what — path:line)
- MEDIUM — added a real Python lint gate before the direct `tests/test_*.py` loop and removed stale `master` trigger — `.github/workflows/install-smoke.yml:5`
- LOW — root `deploy.sh` shim is now included in preflight `bash -n` — `bin/ci-preflight.sh:185`
- LOW — pdf-ingest preflight pins `PDF_INGEST_EXTRACTOR=pdftotext`, removing docling/path environment coupling — `bin/ci-preflight.sh:250`
- LOW — live-agent-tool-smoke opens the control DB read-only via SQLite URI `mode=ro` — `bin/live-agent-tool-smoke.sh:102`
- LOW — restore-smoke now validates tar member type/link targets before extraction and rejects symlink/hardlink escapes — `bin/arclink-restore-smoke.sh:104`
- LOW — Docker live-smoke producer is now executable-guarded like deploy producers — `bin/arclink-docker.sh:2712`
- MEDIUM — install-smoke failure-path teardown now reports lingering service user/home residue after best-effort removal — `bin/ci-install-smoke.sh:2449`

### Skipped (risk-accepted / standing / out-of-scope — why)
- install-smoke remains host-mutating/sudo/90m: this is the intentional heavy integration gate, not a surgical CANON-28 bug fix.
- preflight optional skips for `systemd-analyze` / `inotifywait`: making these hard requirements changes runner prerequisites and local dev behavior.
- Tailscale branch coverage and cold 90m Nextcloud/qmd sufficiency: requires live/logged-in or heavy mutating CI proof, not static code repair.

### NEEDS-DECISION (ambiguous; left for human)
- Orphaned test functions: enforcing a repository-wide self-executing test call-graph from CANON-28 would be a broad CANON-29 test-corpus contract change.
- Provider-auth/provider-unavailable live-smoke skip still exits 0: this is deliberate best-effort deploy behavior; making it fail closed could block upgrades on provider outages.
- Full ruff/pyflakes style enforcement: I added a passing fatal lint gate; strict full pyflakes/ruff currently flags existing cross-piece warnings and needs a broader cleanup decision.

### Cross-piece edits made (if any) + tests added
- Cross-piece: `bin/arclink-docker.sh` guard, with assertion in `tests/test_arclink_docker.py`.
- Cross-piece: restore-smoke tar safety, with regression in `tests/test_backup_git_regressions.py`.
- Added CANON-28 structural regressions to `tests/test_deploy_regressions.py` for workflow lint, preflight shell/pdf pins, live-smoke DB mode, and failure-path teardown reporting.
<<<CODEX-FIX-END CANON-28>>>
