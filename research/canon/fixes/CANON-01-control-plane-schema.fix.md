<<<CODEX-FIX-START CANON-01>>>
## CANON-01 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: python/arclink_control.py, python/arclink_llm_router.py, python/arclink_wrapped.py, python/arclink_chutes.py, python/arclink_secrets_regex.py, tests/test_arclink_control_db.py, tests/test_arclink_llm_router.py, tests/test_arclink_wrapped.py, tests/test_arclink_chutes_and_adapters.py, tests/test_arclink_secrets_regex.py
TESTS: 16 files run, all pass; py_compile pass; git diff --check pass
### Fixed (severity — what — path:line)
- MEDIUM — unguarded `Config.from_env` integer casts now default with warnings instead of crashing — `python/arclink_control.py:161`, `python/arclink_control.py:471`
- MEDIUM — config-file parser now preserves multi-token values, handles `export KEY=value`, caches env-file reads, and fails loudly for missing explicit configs while preserving `/dev/null` sentinel — `python/arclink_control.py:347`
- MEDIUM — event and notification helper JSON now rejects plaintext secret material before persistence — `python/arclink_control.py:3310`, `python/arclink_control.py:8179`
- MEDIUM — raw event/outbox bypasses now use secret-rejecting encoders: LLM router events/notices, Wrapped notification extras, Chutes usage JSON — `python/arclink_llm_router.py:680`, `python/arclink_wrapped.py:138`, `python/arclink_chutes.py:460`
- MEDIUM — `connect_db` no longer performs an SSOT expiry write/commit when nothing is due — `python/arclink_control.py:6116`
- LOW — legacy onboarding token migration no longer writes to an arbitrary DB-stored path; uncontained paths migrate to the canonical secret root — `python/arclink_control.py:7124`, `python/arclink_control.py:7192`
- LOW/INFO — journal-mode PRAGMA now reads effective mode and warns on lock/fallback/mismatch instead of silently swallowing — `python/arclink_control.py:620`
- INFO — `Config.model_presets` is now shallow mutation-resistant via `MappingProxyType` — `python/arclink_control.py:600`
- LOW — secret-key path predicate no longer false-positives on status/counter/metric/id fields such as `credential_handoff_status`, `prompt_tokens`, `token_estimate` — `python/arclink_secrets_regex.py:49`, `python/arclink_secrets_regex.py:95`
### Skipped (risk-accepted / standing / out-of-scope — why)
- Org-profile’s 5 extra control-DB tables: reconciled as a schema-authority/documentation scope correction, not a runtime defect to remove.
- Rowdict importer count, event-reader cite corrections, and 79-owned-plus-`sqlite_sequence` table count: evidence/doc corrections only; canon files are immutable per instruction.
- GAP-019 trusted-host/root-equivalence and Docker trust gate behavior: explicitly risk-accepted/out of scope.
### NEEDS-DECISION (ambiguous; left for human)
- NONE
### Cross-piece edits made (if any) + tests added
- Cross-piece edits: `python/arclink_llm_router.py`, `python/arclink_wrapped.py`, `python/arclink_chutes.py`, `python/arclink_secrets_regex.py`.
- Tests added/updated: control config/JSON/expiry/migration regressions in `tests/test_arclink_control_db.py`; raw-bypass secret regressions in `tests/test_arclink_llm_router.py`, `tests/test_arclink_wrapped.py`, `tests/test_arclink_chutes_and_adapters.py`; predicate false-positive coverage in `tests/test_arclink_secrets_regex.py`.
<<<CODEX-FIX-END CANON-01>>>
