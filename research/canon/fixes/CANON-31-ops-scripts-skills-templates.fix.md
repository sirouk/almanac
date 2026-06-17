<<<CODEX-FIX-START CANON-31>>>
## CANON-31 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: bin/deploy.sh, bin/notion-page-pdf-export.py, bin/pdf-ingest.py, bin/qmd-daemon.sh, bin/qmd-refresh.sh, bin/tailscale-nextcloud-serve.sh, bin/vault-watch.sh, skills/arclink-first-contact/scripts/run-first-contact.sh, skills/arclink-notion-knowledge/scripts/curate-notion.sh, skills/arclink-vaults/scripts/curate-vaults.sh, tests/test_arclink_first_contact.py, tests/test_arclink_vaults_skill.py, tests/test_deploy_regressions.py, tests/test_loopback_service_hardening.py, tests/test_notion_transfer.py, tests/test_pdf_ingest_env.py, tests/test_vault_watch_regressions.py
TESTS: 8 full test files pass; selected CANON-31 deploy/first-contact tests pass; bash -n, py_compile with PYTHONPYCACHEPREFIX, and git diff --check pass. Full tests/test_arclink_first_contact.py blocked by sandbox socket PermissionError; full tests/test_deploy_regressions.py fails before CANON-31 checks on unrelated Discord expectation.
### Fixed (severity — what — path:line)
- MEDIUM — retired Tailscale Serve flag no longer runs the teardown script during install/upgrade; direct serve script now leaves existing config untouched — bin/deploy.sh:396, bin/deploy.sh:5577, bin/deploy.sh:5717, bin/tailscale-nextcloud-serve.sh:235
- MEDIUM — qmd-daemon now exits when either qmd or the TCP forwarder exits — bin/qmd-daemon.sh:83
- MEDIUM — vault-watch no longer treats unreadable/corrupt PDF manifests as “had PDF” — bin/vault-watch.sh:78
- LOW — qmd config force-flag rewrite now uses same-directory temp + mv, not truncate-write — bin/qmd-refresh.sh:40
- LOW — qmd embed timeout/failure now returns nonzero after text index update and still records pending state — bin/qmd-refresh.sh:116, bin/qmd-refresh.sh:140
- LOW — bootstrap-token payloads use --json-args-file/stdin or temp files instead of token-bearing RPC argv — run-first-contact.sh:105, curate-vaults.sh:62, curate-notion.sh:79
- LOW — first-contact validates MCP-fetched managed-memory payload before writing stubs — run-first-contact.sh:69, run-first-contact.sh:150
- LOW — pdf-ingest missing env now exits with a clear error instead of KeyError traceback — bin/pdf-ingest.py:21
- LOW — Notion PDF export no longer silently overwrites same-slug pages in one run — bin/notion-page-pdf-export.py:139
### Skipped (risk-accepted / standing / out-of-scope — why)
- hermes_cli.config.save_config atomicity — STANDING DISAGREEMENT; external pinned Hermes package not vendored here.
- S6 fleet-probe-wrapper producer-subset fallback — tolerant-by-design INFO, no behavior defect to repair in CANON-31.
- Skill→MCP executed-tool count and ssot-batcher adjacent-piece label — canon/spec corrections, not code defects.
- Endpoint embedding provider fallback to local — left unchanged because current code explicitly preserves vector search under pinned qmd lacking endpoint support; changing default behavior is a public config decision.
### NEEDS-DECISION (ambiguous; left for human)
- Whether to fully remove/rename ENABLE_TAILSCALE_SERVE and the related install prompts/agent tailnet URL assumptions. I stopped the active teardown path, but broader config-contract migration has wider blast radius.
### Cross-piece edits made (if any) + tests added
- Cross-piece edit: bin/deploy.sh to stop install/upgrade from invoking the retired CANON-31 Tailscale script.
- Tests adjusted/added in existing files for qmd refresh, qmd daemon liveness, vault-watch corrupt manifest, token argv avoidance, first-contact validation, PDF ingest env errors, Notion PDF slug collisions, and retired Tailscale Serve behavior.
<<<CODEX-FIX-END CANON-31>>>
