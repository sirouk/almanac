<<<CODEX-FIX-START CANON-18>>>
## CANON-18 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: python/arclink_control.py, python/arclink_memory_synthesizer.py, python/arclink_notion_webhook.py, tests/test_arclink_notion_webhook.py, tests/test_arclink_ssot_batcher.py, tests/test_memory_synthesizer.py
TESTS: 10 full/adjacent suites pass + py_compile pass; selected non-socket webhook tests pass. Full `test_arclink_notion_webhook.py` blocked by sandbox socket `PermissionError`; `test_arclink_ctl_notion.py` still fails existing readonly DB fixture path.
### Fixed (severity — what — path:line)
- MEDIUM — Notion verification-token check/set is now serialized under `BEGIN IMMEDIATE`, preventing concurrent armed POSTs from both storing and last-writer winning. `python/arclink_notion_webhook.py:220`
- MEDIUM — Notion reindex consumer now takes/releases a DB-backed lease before live sync, so overlapping timer/webhook runs return `busy` instead of double-syncing the same queue. `python/arclink_control.py:15058`
- LOW — `ARCLINK_MEMORY_SYNTH_MAX_CONTENT_HASH_BYTES=0` no longer disables the content hash cap; hash reads also stop if a file grows past the cap while reading. `python/arclink_memory_synthesizer.py:329`
- LOW/INFO — Webhook batcher kick failures are no longer fully silent, and the stale Popen destructor comment was corrected. `python/arclink_notion_webhook.py:35`
### Skipped (risk-accepted / standing / out-of-scope — why)
- qmd MCP protocol compatibility remains skipped as STANDING: the pinned `@tobilu/qmd` binary is external and cannot be ratified from in-repo code.
- `authorized_live` Notion proof mode live-read behavior left unchanged: it is explicitly selected live proof behavior, not a hidden default mutation path.
- MCP HTTP-200 JSON-RPC error transport left unchanged: canon records this as intentional streamable-http compatibility.
### NEEDS-DECISION (ambiguous; left for human)
- Initial Notion verification-token first-caller authenticity under public Funnel is still a workflow contract problem. The race is fixed, but fully preventing arbitrary first POSTs requires a product decision such as a nonce-bearing webhook URL or gating signed events on operator confirmation.
- Webhook `/health` remains pre-auth because `tests/test_loopback_service_hardening.py` explicitly asserts that contract; changing it would affect health/monitoring behavior.
### Cross-piece edits made (if any) + tests added
- Cross-piece edit: `python/arclink_control.py` for the reindex consumer lease.
- Tests added: concurrent token store regression, reindex lease overlap regression, zero hash-cap regression.
<<<CODEX-FIX-END CANON-18>>>
