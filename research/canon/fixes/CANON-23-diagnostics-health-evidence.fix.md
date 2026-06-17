<<<CODEX-FIX-START CANON-23>>>
## CANON-23 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: python/arclink_control.py, python/arclink_dashboard.py, python/arclink_diagnostics.py, python/arclink_evidence.py, python/arclink_health_watch.py, python/arclink_live_journey.py, python/arclink_live_runner.py, python/arclink_notification_delivery.py, tests/test_arclink_control_db.py, tests/test_arclink_dashboard.py, tests/test_arclink_diagnostics.py, tests/test_arclink_evidence.py, tests/test_arclink_live_runner.py, tests/test_arclink_notification_delivery.py, tests/test_health_watch.py
TESTS: 9 targeted test files + py_compile + git diff --check run, all pass
### Fixed (severity — what — path:line)
- HIGH — notification delivery errors now increment attempts, set `last_attempt_at`/`next_attempt_at`, and fetch only due rows before `LIMIT` — python/arclink_control.py:9585, python/arclink_control.py:9591, python/arclink_control.py:9618
- HIGH — public-agent fast-path no longer lets a future retry row block later due rows — python/arclink_notification_delivery.py:1730
- HIGH — evidence redaction now uses the shared ArcLink secret regex engine instead of a narrower local pattern set — python/arclink_evidence.py:20, python/arclink_evidence.py:62
- HIGH — health-watch notifications redact problem output before clipping/dispatch — python/arclink_health_watch.py:102
- MEDIUM — qmd pending-embeddings markers from the future now fail closed with clock-sync detail instead of clamping to healthy age 0 — python/arclink_diagnostics.py:175
- MEDIUM — live proof no longer mutates global `os.environ`; journey credential checks accept the explicit env mapping — python/arclink_live_journey.py:58, python/arclink_live_journey.py:341, python/arclink_live_runner.py:672, python/arclink_live_runner.py:710
- MEDIUM — live runner dry-run readiness now exits nonzero when required readiness/diagnostic checks fail, while preserving missing-credential dry-run behavior — python/arclink_live_runner.py:760
- MEDIUM — evidence artifact write failures no longer crash the CLI; they produce a failed result/exit code — python/arclink_live_runner.py:740
- MEDIUM — live proof stores evidence runs in the control DB when `ARCLINK_DB_PATH` is configured — python/arclink_live_runner.py:753, python/arclink_live_runner.py:799
- MEDIUM — operator dashboard now reads latest evidence status from the control DB instead of exposing only template state — python/arclink_dashboard.py:536, python/arclink_dashboard.py:584
- MEDIUM — detached public-agent bridge command validation now allows only generated Hermes gateway service names, not arbitrary names containing `hermes-gateway` — python/arclink_notification_delivery.py:479
- LOW — detached public-agent bridge job files are unlinked when worker spawn fails or exits immediately — python/arclink_notification_delivery.py:1079, python/arclink_notification_delivery.py:1288
- INFO — workspace browser proof temp scripts fall back to `/tmp` when `web/` is not writable, and router proof fallback allowlist matches the exercised model — python/arclink_live_runner.py:475, python/arclink_live_runner.py:568
### Skipped (risk-accepted / standing / out-of-scope — why)
- Broker binding and trusted-host/root-equivalence items were left unchanged as GAP-019/risk-accepted or compose-contained per CANON-23 policy.
- Prototype/non-production, GAP-031 live Chutes relay, and live-container/external-pinned-binary/live-API standing disagreements were not changed.
- Current-tree already-fixed items verified but not reworked: pod-message atomic enqueue, dashboard `_REF` env alternate handling, and detached bridge bot-token strip/hydrate.
### NEEDS-DECISION (ambiguous; left for human)
- `run_diagnostics(live=...)` still documents future real provider connectivity; implementing actual live provider checks would change external-provider semantics and needs product/threat-model decision.
### Cross-piece edits made (if any) + tests added
- Cross-piece shared edits: python/arclink_control.py notification retry helpers; python/arclink_dashboard.py operator evidence read surface.
- Tests added/adjusted in the listed CANON-23 test files for redaction, health-watch redaction, qmd future markers, live-runner exit/artifact/DB/env behavior, notification backoff/due fetch, public-agent bridge validation/cleanup, and dashboard evidence status.
<<<CODEX-FIX-END CANON-23>>>
