<<<CODEX-FIX-START CANON-08>>>
## CANON-08 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: python/arclink_agent_access.py, python/arclink_enrollment_provisioner.py, python/arclink_fleet_enrollment.py, python/arclink_inventory.py, python/arclink_sovereign_worker.py, tests/test_arclink_agent_access.py, tests/test_arclink_enrollment_provisioner_regressions.py, tests/test_arclink_fleet_enrollment.py, tests/test_arclink_sovereign_worker.py
TESTS: 8 full files pass; 2 full files env-blocked by sandbox permissions after/ before existing tests; added targeted tests pass; py_compile and git diff --check pass.
### Fixed (severity — what — path:line)
- MEDIUM — fleet consume now keeps inventory/fleet-host registration inside the consume transaction and rolls back on guard/post-register failure — python/arclink_fleet_enrollment.py:651, python/arclink_fleet_enrollment.py:691, python/arclink_fleet_enrollment.py:761
- MEDIUM — audit-chain verification now rejects unkeyed legacy hashes whenever an audit secret is configured, so full unkeyed re-forge no longer verifies cleanly — python/arclink_fleet_enrollment.py:896
- LOW — access-state ownership/chmod failures no longer silently degrade; chown failure raises after preserving 0600 best effort — python/arclink_agent_access.py:71
- LOW — `ARCLINK_DOCKER_MODE=on` now matches the shared Docker-mode truthy set — python/arclink_enrollment_provisioner.py:779
- INFO — Sovereign worker no longer skips deployments merely because metadata text contains `"operator_agent"`; it parses JSON and skips only `operator_agent: true` — python/arclink_sovereign_worker.py:467, python/arclink_sovereign_worker.py:555
### Skipped (risk-accepted / standing / out-of-scope — why)
- GAP-019 plaintext broker transport and env-controlled broker URL left unchanged: canon frames this as trusted Docker/internal-host boundary, not a local CANON-08 defect.
- Readiness secret-presence exclusion left unchanged: canon marks it by design; secret checks remain reported but excluded from `ready`.
- Non-Docker pin component allowlist needed no new edit: current tree already enforces `ALLOWED_PIN_COMPONENTS` at python/arclink_enrollment_provisioner.py:449.
- UnicodeDecodeError broker decode escape needed no new edit: current tree already catches `UnicodeDecodeError` at python/arclink_enrollment_provisioner.py:356.
### NEEDS-DECISION (ambiguous; left for human)
- `operator_actions.request_source == "operator-raven"` remains a string convention, not a hard capability boundary; hardening requires a cross-piece queue/auth contract decision.
- `host_readiness.check_ingress_strategy` still always returns ok; unclear whether it is intended as a status marker with local fallback or a hard preflight gate.
- Hosted API `source_ip` spoofability is audit-only and owned by the CANON-02 proxy/header trust model, so I did not patch it from CANON-08.
### Cross-piece edits made (if any) + tests added
- Cross-piece edit: python/arclink_inventory.py adds optional `commit=True`; CANON-08 consume passes `commit=False`.
- Tests added/adjusted: fleet consume rollback + legacy audit rejection; access-state chown failure; Docker-mode `on`; Sovereign operator-agent literal metadata regression.
<<<CODEX-FIX-END CANON-08>>>
