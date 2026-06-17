<<<CODEX-FIX-START CANON-30>>>
## CANON-30 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: bin/install-arclink-plugins.sh, bin/sync-hermes-bundled-skills.sh, plugins/hermes-agent/arclink-managed-context/__init__.py, plugins/hermes-agent/code/dashboard/plugin_api.py, plugins/hermes-agent/drive/dashboard/plugin_api.py, plugins/hermes-agent/terminal/dashboard/plugin_api.py, tests/test_arclink_agent_user_services.py, tests/test_arclink_plugins.py
TESTS: 2 focused test files run, both pass; `bash -n deploy.sh bin/*.sh test.sh` pass; `py_compile` pass; `git diff --check` pass. Note: bare `python3 tests/test_arclink_plugins.py` hit sandbox tmux `Operation not permitted`; rerun with `TERMINAL_DISABLE_TMUX=1` passed.
### Fixed (severity — what — path:line)
- HIGH — managed-context now injects bootstrap tokens for `pod_comms.list/send/share-file` and `ssot.approve/deny`; `agents.register` remains excluded as registration-token flow — plugins/hermes-agent/arclink-managed-context/__init__.py:288
- MEDIUM — Code git 400 details now redact repo/workspace/home paths and `token/password/secret/key=` fragments before returning stderr/stdout — plugins/hermes-agent/code/dashboard/plugin_api.py:286, plugins/hermes-agent/code/dashboard/plugin_api.py:1141
- MEDIUM — bundled Hermes skills sync now fails closed when runtime skills source is missing, with explicit opt-out only for development no-op runs — bin/sync-hermes-bundled-skills.sh:34
- MEDIUM — plugin installer now writes a pre-mutation `config.yaml` backup before regex/line-surgery edits — bin/install-arclink-plugins.sh:53, bin/install-arclink-plugins.sh:660
- LOW — default plugin regression coverage now includes `arclink-crew` — tests/test_arclink_plugins.py:21
- LOW — token-injection regression coverage now exercises `pod_comms.*` and `ssot.approve/deny`, plus schema-level superset guard against MCP `AGENT_TOKEN_PROP` drift — tests/test_arclink_plugins.py:4193, tests/test_arclink_plugins.py:4351
- LOW — removed dead terminal SSH-target validator while preserving the compatibility `ssh` mode as a local machine shell — plugins/hermes-agent/terminal/dashboard/plugin_api.py:61, plugins/hermes-agent/terminal/dashboard/plugin_api.py:953
- LOW — Drive now applies the existing sensitive-path guard to an empty/root path, not only child paths — plugins/hermes-agent/drive/dashboard/plugin_api.py:1184
### Skipped (risk-accepted / standing / out-of-scope — why)
- `agents.register` token injection — skipped because reconciled spec says it uses `REGISTRATION_TOKEN_PROP`, not the managed-context agent-token seam.
- Code git timeout “15s not 30s” — fact correction only, no code defect.
- Code `stage/unstage/commit/gitignore` confirm-gating — reconciled as overbroad finding, not a defect; Linked mutation 403 remains the safety boundary.
- Crew empty/non-HTTPS silent drop — left unchanged because `/crew` output contract is HTTPS links only; returning disabled entries would change dashboard API/UI semantics.
- WebDAV dead surface — not a safe quick win; removal is broader API/maintenance cleanup beyond a surgical repair.
### NEEDS-DECISION (ambiguous; left for human)
- Full replacement of installer regex/indentation YAML edits with a comment-preserving YAML parser. I added backups, but parser replacement needs dependency/formatting policy because current tests intentionally preserve comments and future nested config.
- Full Drive denylist/TOCTOU redesign. I fixed the empty-root guard, but complete mitigation likely needs fd-anchored file operations or an allowlist policy that changes file-manager behavior.
### Cross-piece edits made (if any) + tests added
- Cross-piece test-only edit: tests/test_arclink_agent_user_services.py now creates a minimal fake Hermes runtime so the stricter bundled-skills sync contract is represented in fixtures.
- Added/extended tests for fail-closed bundled-skills sync, config backup creation, code git redaction, default `arclink-crew` install coverage, token injection for missed MCP tools, and MCP schema/token-superset drift.
<<<CODEX-FIX-END CANON-30>>>
