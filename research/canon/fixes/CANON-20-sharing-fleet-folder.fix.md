<<<CODEX-FIX-START CANON-20>>>
## CANON-20 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: bin/arclink-docker.sh, python/arclink_fleet.py, python/arclink_fleet_inventory_worker.py, python/arclink_fleet_share.py, tests/test_arclink_docker.py, tests/test_arclink_fleet.py, tests/test_arclink_fleet_inventory_worker.py, tests/test_arclink_fleet_share.py
TESTS: 6 test files pass + syntax checks pass; 1 adjacent discovered file NEEDS-REVIEW (`python3 tests/test_arclink_fleet_join.py` fails only with host config bleed-through; rerun with `ARCLINK_FLEET_WORKER_CONFIG=/tmp/arclink-nonexistent-fleet-worker.env` passes)

### Fixed (severity — what — path:line)
- MEDIUM — guarded invalid ASU probe ingestion so degraded `vcpu_cores:0` does not abort the probe pass. `python/arclink_fleet_inventory_worker.py:368`
- LOW — kept liveness transition notifications in the probe transaction by passing `commit=False`. `python/arclink_fleet_inventory_worker.py:263`
- MEDIUM — made corrupt working-copy recovery restore unsynced files into the live tree and a visible recovery folder. `python/arclink_fleet_share.py:159`, `python/arclink_fleet_share.py:294`
- MEDIUM — added remote hub reachability check instead of trusting remote refs blindly. `python/arclink_fleet_share.py:225`
- MEDIUM — rejected git remote-helper syntax and overbroad env-driven Fleet working roots before `git add -A`. `python/arclink_fleet_share.py:125`, `python/arclink_fleet_share.py:445`, `python/arclink_fleet_share.py:897`
- LOW — added IntegrityError fallbacks for fleet share and member insert races. `python/arclink_fleet_share.py:519`, `python/arclink_fleet_share.py:618`
- LOW — changed empty deployment member removal from silent no-op to explicit error. `python/arclink_fleet_share.py:672`
- LOW — added IntegrityError fallback for `register_fleet_host` hostname races. `python/arclink_fleet.py:240`
- INFO — added `BEGIN IMMEDIATE` around placement removal to prevent concurrent double-decrement. `python/arclink_fleet.py:640`
- LOW — required `fleet-inventory-worker` and `fleet-share-reconcile` in Docker control health. `bin/arclink-docker.sh:26`

### Skipped (risk-accepted / standing / out-of-scope — why)
- Hub replication/backup SPOF: not a surgical code repair; remote reachability is fixed, but replication needs an ops/product durability design.
- `arclink_share_grants`: canon says this is not CANON-20, so left untouched.

### NEEDS-DECISION (ambiguous; left for human)
- Full hub URL host/scheme allowlist: production supports operator-provided remote SSH hubs; I only blocked git remote-helper command syntax.
- Distributed fleet-share sync locking / bounded retry policy: a true cross-machine lock requires hub/broker design, not a local retry tweak.
- Dead `paused` / member `pending` statuses: removing or activating them changes schema/API contract.

### Cross-piece edits made (if any) + tests added
- Cross-piece edit: `bin/arclink-docker.sh` required-service list for CANON-20 jobs.
- Added/adjusted regressions in `tests/test_arclink_fleet_share.py`, `tests/test_arclink_fleet.py`, `tests/test_arclink_fleet_inventory_worker.py`, and `tests/test_arclink_docker.py`.
<<<CODEX-FIX-END CANON-20>>>
