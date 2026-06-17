<<<CODEX-FIX-START CANON-15>>>
## CANON-15 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: config/docker-authority-inventory.json, python/arclink_control.py, python/arclink_enrollment_provisioner.py, python/arclink_operator_upgrade_broker.py, python/arclink_operator_upgrade_host_runner.py, python/arclink_pin_upgrade_check.py, tests/test_arclink_docker.py, tests/test_arclink_enrollment_provisioner_regressions.py, tests/test_arclink_pin_upgrade_detector.py
TESTS: 5 test files run, all pass; py_compile/json/diff checks pass
### Fixed (severity — what — path:line)
- HIGH — poison/dangling symlink/invalid pending file no longer wedges the host runner; bad files are result-recorded when possible and quarantined. `python/arclink_operator_upgrade_host_runner.py:403`
- MEDIUM — queue root override is confined under private state. `python/arclink_operator_upgrade_host_runner.py:90`
- MEDIUM — nonce replay TOCTOU and cross-restart replay closed with locked check-record plus persistent nonce store. `python/arclink_operator_upgrade_broker.py:678`, `python/arclink_operator_upgrade_broker.py:779`
- MEDIUM — non-Docker pin-upgrade component allowlist added before command construction. `python/arclink_enrollment_provisioner.py:100`, `python/arclink_enrollment_provisioner.py:443`
- MEDIUM — provisioner broker decode/HTTP error escapes normalized. `python/arclink_enrollment_provisioner.py:347`
- MEDIUM — provisioner/broker timeout seam aligned by signing `timeout_seconds` and extending HTTP wait. `python/arclink_enrollment_provisioner.py:315`
- MEDIUM — stale/ghost host-runner execution blocked with request expiry validation. `python/arclink_operator_upgrade_host_runner.py:176`, `python/arclink_operator_upgrade_host_runner.py:336`
- LOW — dismissed pin upgrade action no longer remains active/listable. `python/arclink_control.py:9726`
- LOW — authority inventory prose updated to remove stale Docker-socket/egress claims. `config/docker-authority-inventory.json:157`, `config/docker-authority-inventory.json:2269`
- LOW — hermes-docs-only install item maps to executable parent. `python/arclink_pin_upgrade_check.py:648`
- LOW — malformed poll interval is parsed before queue write and defaults safely. `python/arclink_operator_upgrade_broker.py:304`
- LOW — detector runs are single-flight and malformed `pins.json` becomes structured failure. `python/arclink_pin_upgrade_check.py:109`, `python/arclink_pin_upgrade_check.py:720`
- LOW — queue `results/` and `processed/` retention added; consumed results are unlinked. `python/arclink_operator_upgrade_host_runner.py:441`, `python/arclink_operator_upgrade_broker.py:362`
- INFO — schema_version, returncode, and `container_priv_dir` validation tightened. `python/arclink_operator_upgrade_host_runner.py:190`, `python/arclink_operator_upgrade_broker.py:370`
### Skipped (risk-accepted / standing / out-of-scope — why)
- GAP-019 trusted-host/root-equivalence and writable-checkout/private-state authority left unchanged; canon marks this risk-accepted/out of scope.
- Broker `0.0.0.0` binding left unchanged because compose `internal:true` containment is explicitly accepted.
- `upgrade_policy` hermes/hermes-agent naming drift left unchanged because reconciled canon says no literal `hermes` reaches broker `install_items`.
### NEEDS-DECISION (ambiguous; left for human)
- NONE
### Cross-piece edits made (if any) + tests added
- Cross-piece edits: `python/arclink_enrollment_provisioner.py`, `python/arclink_control.py`, `config/docker-authority-inventory.json`.
- Tests added/adjusted in `tests/test_arclink_docker.py`, `tests/test_arclink_enrollment_provisioner_regressions.py`, and `tests/test_arclink_pin_upgrade_detector.py`.
<<<CODEX-FIX-END CANON-15>>>
