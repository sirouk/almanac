<<<CODEX-FIX-START CANON-25>>>
## CANON-25 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: bin/arclink-docker.sh, bin/docker-job-loop.sh, compose/nextcloud-compose.yml, tests/test_arclink_docker.py, tests/test_nextcloud_regressions.py
TESTS: 5 Python files + bash syntax/whitespace checks run, all pass

### Fixed (severity — what — path:line)
- MEDIUM — redaction now covers `ARCLINK_*_TOKEN`/suffix secrets and `Authorization: Bearer` without leaking the bearer token — `bin/docker-job-loop.sh:44`
- MEDIUM — job status producer now emits `job_name`/`exit_code` aliases while preserving `job`/`returncode` — `bin/docker-job-loop.sh:83`
- LOW — job status writes now use temp file + fsync + atomic replace for both running and final status — `bin/docker-job-loop.sh:94`, `bin/docker-job-loop.sh:135`
- MEDIUM — `control health` now requires all 7 broker/helper containers running and probes each `/health` endpoint directly — `bin/arclink-docker.sh:26`, `bin/arclink-docker.sh:746`
- LOW — `health()` no longer swallows tailnet publish / service-health refresh failures; failed tailnet publication records unavailable and returns nonzero — `bin/arclink-docker.sh:763`, `bin/arclink-docker.sh:1064`
- LOW — standalone Nextcloud Redis now has a healthcheck and `app` waits for healthy db+redis — `compose/nextcloud-compose.yml:22`

### Skipped (risk-accepted / standing / out-of-scope — why)
- GAP-019 socket/root authority and operator-upgrade writable host-repo bind — explicit trusted-host/root-equivalence residual surface, codified in current tests/docs.
- Trusted-host gate default empty / no auto-`accepted` injection — deliberate explicit operator opt-in; changing it would weaken the risk-acceptance boundary.
- Queue-root validation asymmetry — not reproduced in current tree; host runner already enforces `root.relative_to(state_root)` at `python/arclink_operator_upgrade_host_runner.py:97`.
- Docker-entrypoint hard-required password seeding under read-only split mounts — CANON-24-owned file and already has pre-existing edits in this worktree; no CANON-25 patch made.

### NEEDS-DECISION (ambiguous; left for human)
- `agent-process-helper-egress-net` remains non-internal: current tests require it for “outbound-only runtime work”; safely fixing listener exposure likely needs a design change, not a one-line compose edit.
- `docker-job-loop.sh` still does not exit on child failure: making recurring jobs crash on poll failure changes restart cadence across many services.
- `health()` still repairs Nextcloud data permissions as a side effect; removing that mutating repair could change live recovery behavior.
- Embedded and standalone Nextcloud still share default host port `18080`; changing the standalone default is a public/default contract decision.

### Cross-piece edits made (if any) + tests added
- No cross-piece code edits made.
- Tests added/adjusted in `tests/test_arclink_docker.py` and `tests/test_nextcloud_regressions.py`.
- Verification passed: `bash -n deploy.sh bin/*.sh test.sh`; `python3 tests/test_arclink_docker.py`; `python3 tests/test_docker_health_regressions.py`; `python3 tests/test_nextcloud_regressions.py`; `python3 tests/test_nextcloud_user_access.py`; `python3 tests/test_nextcloud_secret_rotation.py`; `git diff --check` on touched files.
<<<CODEX-FIX-END CANON-25>>>
