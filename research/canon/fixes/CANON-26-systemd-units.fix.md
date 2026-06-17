<<<CODEX-FIX-START CANON-26>>>
## CANON-26 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: bin/install-agent-ssh-key.sh, bin/install-agent-user-services.sh, bin/install-system-services.sh, bin/install-user-services.sh, python/arclink_onboarding_flow.py, tests/test_arclink_agent_user_services.py, tests/test_arclink_enrollment_provisioner_regressions.py, tests/test_install_agent_ssh_key.py, tests/test_install_user_services_regressions.py, tests/test_remote_ssh_key_onboarding.py
TESTS: 5 Python test files run, all pass; bash -n on 4 touched shell scripts passed; py_compile for python/arclink_onboarding_flow.py passed
### Fixed (severity — what — path:line)
- HIGH — access-state parsing now fails closed before dashboard/proxy render: validates JSON object plus 1-65535 backend/proxy ports, sets `enable_access_surfaces=1` only after successful parse. `bin/install-agent-user-services.sh:305`
- MEDIUM — agent unit directive injection now rejects raw unit fields in the parent shell before heredocs render, including `AGENT_ID`, paths, activation triggers, ports, and dashboard env values. `bin/install-agent-user-services.sh:39`, `bin/install-agent-user-services.sh:66`, `bin/install-agent-user-services.sh:369`
- HIGH — SSH public key newline injection is blocked in the root installer with explicit multiline rejection and `[[:blank:]]` separators instead of `[[:space:]]`. `bin/install-agent-ssh-key.sh:56`, `bin/install-agent-ssh-key.sh:61`
- HIGH — onboarding-side SSH public key validator no longer accepts embedded newlines before queueing root key-install actions. `python/arclink_onboarding_flow.py:76`
- LOW — `ARCLINK_AGENT_REMOTE_SSH_FROM` now rejects empty, quote, CR, and LF values before interpolating `from="..."`. `bin/install-agent-ssh-key.sh:77`
- LOW — service-user enable/restart/start operations now run per unit, collect failures, continue reconciliation, and exit nonzero at the end if any operation failed. `bin/install-user-services.sh:30`, `bin/install-user-services.sh:53`, `bin/install-user-services.sh:164`
- LOW — root system-service start no longer does separate `ActiveState` check before `start`; systemd handles idempotent/serialized start directly. `bin/install-system-services.sh:110`
### Skipped (risk-accepted / standing / out-of-scope — why)
- STANDING — Hermes gateway CLI compatibility and native Hermes gateway unit-name completeness remain external CANON-30 questions; not settled from this repo.
- OUT-OF-SCOPE/DELIBERATE — legacy/dead unit cleanup for `arclink-pdf-ingest-watch.service` and `arclink-user-agent-code.service` left unchanged; canon identifies them as compatibility/legacy surfaces, not safe unilateral removals.
- RISK-ACCEPTED/INFO — `Environment=HOME=/root` in root-gated system units left unchanged; current script requires root and existing tests assert the contract.
### NEEDS-DECISION (ambiguous; left for human)
- NONE
### Cross-piece edits made (if any) + tests added
- Cross-piece edit: `python/arclink_onboarding_flow.py` SSH key regex tightened to match the root installer; regression added in `tests/test_remote_ssh_key_onboarding.py`.
- Test-only cross-piece edit: `tests/test_arclink_enrollment_provisioner_regressions.py` updated for the root system-service TOCTOU fix.
- Added regressions for invalid access-state fail-closed, systemd directive injection rejection, multiline SSH key rejection, unsafe `from=` rejection, and collected systemctl failures.
<<<CODEX-FIX-END CANON-26>>>
