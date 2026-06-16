<<<CODEX-VERDICT-START CANON-28>>>
## CANON-28 — Codex (GPT-5.5 xhigh) ratification
SIGN-OFF: OBJECT(6)
ONE-LINE VERDICT: Core record ratifies: CI gates three direct lanes, but several seam/risk statements need precision corrections.

### Adjudication (each: CONFIRM/REFUTE/REFINE + path:line)
- CONFIRM — Python CI runs `tests/test_*.py` directly under bash, fails closed on zero files, and does not invoke pytest in the workflow command path. `.github/workflows/install-smoke.yml:31-40`
- CONFIRM — Web CI runs `npm run lint`, `npm test`, `npm run build`; package scripts resolve to ESLint, two node-test files, and Next build. `.github/workflows/install-smoke.yml:64-67`; `web/package.json:7-10`
- CONFIRM — Install smoke enters through `./test.sh`, runs preflight, then root `ci-install-smoke.sh`; the install script requires root and calls `bin/deploy.sh --apply-install`. `test.sh:12-14`; `bin/ci-install-smoke.sh:39-42,2498-2503`
- CONFIRM — Deploy seam consumes `ARCLINK_INSTALL_ANSWERS_FILE` and dispatches `--apply-install` / `--apply-remove`. `bin/deploy.sh:24,757-768`; `bin/ci-install-smoke.sh:2441-2447,2502-2503`
- REFINE — Live-agent smoke is `-x` guarded in install/upgrade deploy, but NOT in Docker producer. `bin/deploy.sh:5609-5612,5748-5751`; `bin/arclink-docker.sh:2692-2693`
- CONFIRM — Managed-context telemetry seam matches: producer writes `session_id` + `tool_token_injected: True` to `state/arclink-context-telemetry.jsonl`; consumer checks same path/keys. `plugins/hermes-agent/arclink-managed-context/__init__.py:1078-1079,1885-1890`; `bin/live-agent-tool-smoke.sh:163,312-315`
- CONFIRM — PDF status seam matches, but backend assertion is environment-coupled: preflight sets `PDF_INGEST_EXTRACTOR=auto` and asserts `pdftotext`; resolver prefers `docling` before `pdftotext`. `bin/ci-preflight.sh:250,262`; `bin/pdf-ingest.py:68-72,602-624`
- CONFIRM — Restore-smoke JSON/CLI contract matches tests. `bin/arclink-restore-smoke.sh:250-265`; `tests/test_agent_backup_regressions.py:347-364`; `tests/test_backup_git_regressions.py:390-406`
- CONFIRM — MEDIUM risk: no Python style/lint gate. `ruff`/`pyflakes` are pinned, while preflight only `py_compile`s three modules. `requirements-dev.txt:12-13`; `bin/ci-preflight.sh:197-203`
- REFINE — MEDIUM risk: current hole is not only “file lacks `__main__`”; direct-file CI cannot detect hand-list orphan tests. I re-found 10 orphaned module tests, e.g. definitions at `tests/test_arclink_docker.py:2953,4854`, `tests/test_arclink_executor.py:1550,1586`, `tests/test_arclink_fleet.py:165,192`, omitted from their `main()` runners. `.github/workflows/install-smoke.yml:38-40`; `tests/test_arclink_docker.py:7947-8018`; `tests/test_arclink_executor.py:2135-2185`; `tests/test_arclink_fleet.py:598-623`
- REFINE — MEDIUM risk: host mutation/sudo dependency confirmed; teardown failure is swallowed, but success path does assert service user/home removal. Failure-path trap still performs no post-teardown removal assertion. `bin/ci-install-smoke.sh:39-42,2441-2447,2481-2489,2595-2603`
- CONFIRM — LOW risks: stale `master` trigger, optional tool skip coverage loss, tailscale branch only conditional, tar symlink/member-type screening absent. `.github/workflows/install-smoke.yml:5-8`; `bin/ci-preflight.sh:208-211,457-460,541-544,748-751`; `test.sh:7-10`; `bin/arclink-restore-smoke.sh:104-114,132-134`
- REFINE — §5B #45: no tracked workflow command invokes pytest/coverage; 90m timeout exists, but sufficiency for cold Nextcloud+qmd is not statically provable in read-only audit. `.github/workflows/install-smoke.yml:31-40,64-67,71,78`
- CONFIRM — §5A/§5C contain no CANON-28-tagged disputed item to adjudicate.

### New findings both Claude passes missed (severity + path:line)
- LOW — `live-agent-tool-smoke.sh` does not open the control DB read-only; `sqlite3.connect(db_path)` can create a missing DB before the SELECT path fails. Use URI `mode=ro` if this is meant to be a non-mutating live proof. `bin/live-agent-tool-smoke.sh:102-123`; contrast `bin/arclink-restore-smoke.sh:162-164`
- LOW — `ci-preflight.sh` shell lint skips root `deploy.sh`; local validation documents `bash -n deploy.sh bin/*.sh test.sh`, but preflight only includes `test.sh` plus `bin/*.sh`. `bin/ci-preflight.sh:185-195`; `deploy.sh:1-5`; `docs/arclink/local-validation.md:21-24`
- INFO — Deploy treats provider-auth/provider-unavailable live-smoke skips as success because the smoke exits 0; this is explicit but fail-open for “live tool smoke passed” interpretation. `bin/live-agent-tool-smoke.sh:481-490`; `bin/deploy.sh:5609-5612,5748-5751`

### Claude citations re-confirmed or corrected
- Re-confirmed: workflow triggers/jobs, direct Python loop, web scripts, install smoke, preflight fixture paths, restore-smoke JSON shape, and telemetry key/path seam. `.github/workflows/install-smoke.yml:3-78`; `bin/ci-preflight.sh:954-967`
- Corrected: `ci-install-smoke` port defaults are at `bin/ci-install-smoke.sh:27-30`, not the record’s cited `:22-25`.
- Corrected: live smoke SELECTs from `agents`, but the DB connection is not read-only. `bin/live-agent-tool-smoke.sh:102-123`
- Corrected: `PROMPT_*.md` are not CI gates, but they are not globally inert docs; Ralphie maps and feeds them to engines as phase prompts. `ralphie.sh:68-72,9804-9811,6643-6658`
- Corrected: restore-smoke path traversal guard checks names only; it does not screen tar member type/symlink targets. `bin/arclink-restore-smoke.sh:104-114,132-134`

### Residual disagreement with the Claude half (for final reconciliation)
- No material rejection. Fold in the Docker non-`-x` seam, live-smoke DB mode correction, root `deploy.sh` lint gap, provider-skip fail-open note, and the teardown happy/failure-path nuance.
- §5B #45 remains only partially adjudicated: coverage and cold 90m sufficiency require a mutating/heavy CI run, outside this read-only pass. Static code confirms no pytest/coverage workflow command. `.github/workflows/install-smoke.yml:31-40,64-67,71,78`
<<<CODEX-VERDICT-END CANON-28>>>
