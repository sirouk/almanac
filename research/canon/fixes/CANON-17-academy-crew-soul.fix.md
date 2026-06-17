<<<CODEX-FIX-START CANON-17>>>
## CANON-17 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: compose.yaml, docs/arclink/academy-trainer.md, docs/arclink/sovereign-control-node-symphony.md, python/arclink_academy_programs.py, python/arclink_academy_scheduler.py, python/arclink_academy_trainer.py, python/arclink_crew_recipes.py, tests/test_arclink_academy_programs.py, tests/test_arclink_academy_scheduler.py, tests/test_arclink_crew_recipes.py, tests/test_deploy_regressions.py
TESTS: 5 test files run, all pass; py_compile pass; git diff --check pass
### Fixed (severity — what — path:line)
- HIGH — Academy live defaults are now opt-in: CE crawl defaults false in code, compose exports `ARCLINK_ACADEMY_CE_LIVE_CRAWL:-0`, and live Trainer compose default is `:-0` — python/arclink_academy_scheduler.py:722, compose.yaml:97
- HIGH — DNS rebinding TOCTOU closed by carrying the validated public DNS address into pinned HTTP/HTTPS connections instead of reconnecting by hostname — python/arclink_academy_scheduler.py:76, python/arclink_academy_scheduler.py:199, python/arclink_academy_scheduler.py:275
- MEDIUM — Proposal SELECT/INSERT race now catches `sqlite3.IntegrityError` and returns/updates the race-winner as deduped — python/arclink_academy_programs.py:770, python/arclink_academy_programs.py:842
- MEDIUM — `academy_apply` now enforces PG-PROVIDER before live writes; PG-HERMES alone fails closed until the Trainer capsule has `live_reviewed` proof — python/arclink_academy_programs.py:3015, python/arclink_academy_programs.py:3026
- MEDIUM — Latent `Sequence` `NameError` fixed by importing it — python/arclink_crew_recipes.py:11
- LOW — Source-lane registry load failure now fails closed instead of accepting lanes unvalidated — python/arclink_academy_programs.py:3162
- LOW — Crawl limit `0` no longer disables the per-trainee bound — python/arclink_academy_scheduler.py:737
- LOW — robots.txt 5xx/other non-404 failures now block instead of fail open — python/arclink_academy_scheduler.py:374
- LOW — Live Trainer failure now records a redacted event/notification instead of only hiding in enrichment JSON — python/arclink_academy_programs.py:2371
- LOW — subscription inheritance failures remain best-effort but now surface a redacted event — python/arclink_academy_programs.py:453
- LOW — crawl blocked/failed observations now feed CE review gates as blocked/review-required — python/arclink_academy_scheduler.py:791, python/arclink_academy_trainer.py:1211
- INFO — crawl observation IDs include `source_uid` and observation insert is conflict-tolerant — python/arclink_academy_scheduler.py:519, python/arclink_academy_scheduler.py:556
### Skipped (risk-accepted / standing / out-of-scope — why)
- Apply materialization breadth was not reduced: SOUL/vault/qmd/skill/state writes are confirmed intended behavior behind apply gates; changing that would remove product functionality rather than fix a bug.
- Producer-only CANON-16 router seam was not changed; the canon labels consumer proof as outside CANON-17.
- Marker-field semantics were not changed; producer/consumer literals already match and the canon says there is no break.
### NEEDS-DECISION (ambiguous; left for human)
- NONE
### Cross-piece edits made (if any) + tests added
- Cross-piece: compose defaults and deploy regression test updated; Academy docs aligned with opt-in live behavior.
- Added regression coverage for live defaults, DNS pin handoff, robots fail-closed, crawl limit bounds, proposal race recovery, PG-PROVIDER apply enforcement, live Trainer failure visibility, source-lane fail-closed, subscription-failure surfacing, and `Sequence` type-hint resolution.
<<<CODEX-FIX-END CANON-17>>>
