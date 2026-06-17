<<<CODEX-FIX-START CANON-10>>>
## CANON-10 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: python/arclink_inventory.py, python/arclink_fleet.py, tests/test_arclink_inventory.py
TESTS: 9 discovered files run: 8 pass / 1 NEEDS-REVIEW. `tests/test_arclink_fleet_join.py` plain invocation failed from host `/etc/arclink/fleet-worker.env` overriding test env; rerun with `ARCLINK_FLEET_WORKER_CONFIG=/tmp/arclink-no-such-fleet-worker.env` passes. `py_compile` and `git diff --check` pass.
### Fixed (severity — what — path:line)
- HIGH — fixed `parse_probe_output` disk parsing for normal `/dev/*` and `overlay` `df -BG` rows, plus wrapped device-name rows; bad/missing MemTotal or disk now fails closed instead of returning zero capacity — `python/arclink_inventory.py:430`.
- MEDIUM — successful SSH probes with bad parse/ASU data now mark the machine `degraded` and raise instead of leaving stale `ready` capacity — `python/arclink_inventory.py:511`.
- MEDIUM — post-provision cloud create failures before inventory registration now attempt compensating `remove_server(..., destroy=True)` and persist failure details/provider refs — `python/arclink_inventory.py:818`, `python/arclink_inventory.py:885`.
- MEDIUM — failed create/remove idempotency no longer replays as bare `{"replay": true}`; failed rows raise and fail paths store failure-shaped results — `python/arclink_inventory.py:612`, `python/arclink_inventory.py:897`, `python/arclink_inventory.py:964`.
- LOW — inventory registration now validates JSON/secret-bearing payloads before fleet-host writes and commits fleet-host creation atomically with the inventory row — `python/arclink_inventory.py:173`, `python/arclink_inventory.py:183`, `python/arclink_fleet.py:158`.
- LOW — fractional `current_load` values sent to integer fleet `observed_load` now ceil instead of truncating fail-open — `python/arclink_inventory.py:511`, `python/arclink_inventory.py:538`.
### Skipped (risk-accepted / standing / out-of-scope — why)
- Hetzner live memory/disk units — standing disagreement; repo proves only adapter asymmetry, not live API units.
- SSH TOFU `StrictHostKeyChecking=accept-new` — NEEDS product/security decision for bootstrap posture; changing default would break first-contact fleet workflows.
- Create hostname TOCTOU — INFO, not a safe quick win; proper fix needs a hostname reservation/locking contract.
### NEEDS-DECISION (ambiguous; left for human)
- Hostname-collision capacity clobber across reused fleet hostnames — fixing safely needs a public contract decision on whether re-registering an existing hostname is allowed to update fleet-host capacity.
- `compute_asu` zero RAM/disk global behavior and stale unlinked `asu_consumed` — left unchanged because current contracts explicitly allow zero-capacity summaries and placement-critical rows use linked hosts.
### Cross-piece edits made (if any) + tests added
- Cross-piece: added optional `commit=True` parameter to `register_fleet_host`; default preserves existing callers, inventory uses `commit=False`.
- Added inventory regressions for real `df -BG`, wrapped `df`, bad successful probe degradation, fractional observed-load ceiling, no fleet-host commit on rejected registration, post-provision cleanup, and failed idempotency replay.
<<<CODEX-FIX-END CANON-10>>>
