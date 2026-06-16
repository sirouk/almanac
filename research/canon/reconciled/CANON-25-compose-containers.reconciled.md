# CANON-25 — Container Topology (Compose): FEDERATION RECONCILIATION

- **Piece:** CANON-25 — Container Topology (Compose)
- **Codex (GPT-5.5 xhigh) sign-off:** OBJECT(2) — core compose topology ratifiable; verifier's redaction/egress corrections stand; adds two health/status robustness defects.
- **Claude final adjudicator federation sign-off:** BOTH-MODEL-AGREED
- **Adjudicator method:** Every disputed point below was decided by re-opening the cited code (Read / rg / sed / empirical regex run), not by trusting either model's citation. Code wins over comment/name/prior claim.

This reconciliation merges the original Claude record, the Claude adversarial verify pass, and the Codex verdict. The verify pass had already corrected the original record on three points (R1 redaction, R2 egress, R3 seeding); Codex independently CONFIRMED those corrections and added two net-new findings. All material points reconcile to a single code-grounded truth.

---

## RESOLUTION TABLE (point | winner | deciding cite)

| # | Point | Winner | Deciding cite (re-opened by adjudicator) |
|---|-------|--------|------------------------------------------|
| 1 | Redaction regex fails open on this file's own `ARCLINK_*_TOKEN`/`ARCLINK_*_SECRET` names (leading `\b` escape) | both (verify+codex) | `bin/docker-job-loop.sh:44,72`; empirical run: `ARCLINK_GATEWAY_EXEC_BROKER_TOKEN=...`, `broker_token=...`, `my_secret=...` all UNREDACTED; only bare `TOKEN=`/`password:` match |
| 1b | `Authorization: Bearer <tok>` mis-redacts (pattern 1 consumes `Authorization:`, redacts the word `Bearer`, leaves token) | both (verify+codex) | `bin/docker-job-loop.sh:44`; empirical: `Authorization: Bearer tok_abc123` -> `Authorization: [REDACTED] tok_abc123` |
| 2 | `agent-process-helper` (root `0:0`, binds `0.0.0.0:8916`) is also on NON-internal `agent-process-helper-egress-net` -> not "internal-only" | both (verify+codex) | `compose.yaml:918,930,942-944`; `agent-process-helper-egress-net: {}` at `:1177` (no `internal: true`); `python/arclink_agent_process_helper.py:937-938` `ThreadingHTTPServer((host,port))`, host default `0.0.0.0` |
| 3 | `:?` hard-required `POSTGRES_PASSWORD`/`NEXTCLOUD_ADMIN_PASSWORD` are NOT seeded by `bootstrap()` at `arclink-docker.sh:271-285`; seeded in `docker-entrypoint.sh` instead; "only fires if docker.env deleted" is over-strong | both (verify+codex) | `bin/arclink-docker.sh:271-286` (only `ARCLINK_OPERATOR_NEXTCLOUD_*` passwords appear, not the two hard-`:?` ones); seeding at `bin/docker-entrypoint.sh:343-361`; repair guarded by `config_file_can_write`/`config_file_can_repair` at `:655,664-665` (read-only split mount -> not seeded -> `:?` fires with docker.env present) |
| 4 | Broker-net `0.0.0.0` binds reachable from "the peer" (singular) — imprecise; multiple clients attach each internal net | codex (REFINE) | `compose.yaml`: `deployment-exec-broker-net` members `:669,730,774`; `operator-upgrade-broker-net` `:390,430,872,992`; `gateway-exec-broker-net` `:391,431,1020,1052`. Containment to same-net peers holds; "single peer" wording does not |
| 5 | Operator-upgrade queue-root validation is ASYMMETRIC: broker enforces `relative_to(host_state_root)`, runner only `is_absolute()` | both (verify G4 + codex REFINE) | broker `python/arclink_operator_upgrade_broker.py:284` (`root.relative_to(host_state_root)`); runner `python/arclink_operator_upgrade_host_runner.py:90` (only `is_absolute()`) |
| 6 | Job-status key drift: producer writes `job`/`returncode`, consumer reads `job_name`/`exit_code` first, survives via `or`/`in` fallback | both (record+verify+codex) | producer `bin/docker-job-loop.sh:82,84`; consumer `bin/docker-health.sh:250,252` |
| 6b | No STRICT job-status-key consumer exists today (dashboard reads only status/timestamps/interval, never `job_name`) — drift is benign | codex (REFUTE of strict-consumer concern) | `python/arclink_dashboard.py:467-491` reads only `status`,`finished_at`,`started_at`,`interval_seconds` |
| 7 | Trusted-host gate enforced at startup in all 7 modules with `SystemExit`; compose default empty -> all 7 crash-loop on default install; nothing in tracked code auto-injects `accepted` | both (all three) | gates e.g. `arclink_deployment_exec_broker.py:312`, `arclink_gateway_exec_broker.py:378`, `arclink_agent_process_helper.py:945`; literal `"accepted"` `arclink_boundary.py:80-97`; compose empty default `compose.yaml:654`; entrypoint passes incoming value `docker-entrypoint.sh:355`; bootstrap seeds empty `arclink-docker.sh:286` |
| 8 | Topology: 51 services / 9 networks / 1 volume (`arclink-qmd`) | both (all three) | `python3 yaml.safe_load(compose.yaml)`: services=51, networks=9, volumes=1; networks block `compose.yaml:1161-1177` |
| 9 | Exactly 3 docker.sock holders (deployment/agent-supervisor/gateway) rw = host-root-equiv on compromise (GAP-019) | both (all three) | `compose.yaml:666,832,1017`; no other `docker.sock` mount in file |
| 10 | Exactly 4 root `user: "0:0"` services | both (all three) | `compose.yaml:679,847,885,918` |
| 11 | operator-upgrade-broker mounts live host repo writable while root (no `:ro`) | both (record+codex) | `compose.yaml:847,869` |
| 12 | `docker-job-loop.sh` swallows child exit code; loop never exits; `restart: unless-stopped` never trips | both (record+codex) | `bin/docker-job-loop.sh:130-136,141-144` (`run_job_once ... ; sleep ; done`, rc captured into JSON only) |
| 13 | Every published host port is `127.0.0.1:`-bound except control-ingress second (private-mesh) bind | both (record+verify) | `compose.yaml:289,316,325,418,505,541,561,597,628-630`; only `:630` `${ARCLINK_CONTROL_PRIVATE_BIND_HOST:-127.0.0.1}` is overridable |
| 14 | Nextcloud config split: embedded defaults `http`, no data mount; standalone hard `https`, mounts `${NEXTCLOUD_DATA_DIR}` | both (record+verify+codex) | `compose.yaml:297-305`; `compose/nextcloud-compose.yml:40,44` |
| 15 | control-api port seam, gateway port seam, all `DEFAULT_PORT` == compose `_PORT` | both (all three) | `compose.yaml:73,550-561` / `arclink_hosted_api.py:4371-4376`; `arclink_gateway_exec_broker.py:33` |
| 16 | operator-upgrade is queue-based not socket-based; broker has NO docker.sock | both (all three) | broker writes pending/results `arclink_operator_upgrade_broker.py:312-360`; runner drains `arclink_operator_upgrade_host_runner.py:367-414`; no sock mount on broker service `compose.yaml:842-872` |

---

## CODEX NEW-FINDINGS — CONFIRMED vs REJECTED

### CONFIRMED (re-verified true in code -> net-new federation risks)

- **NEW-1 (MEDIUM) — `./deploy.sh control health` has no direct liveness probe for any of the 7 broker/helper services.** `DOCKER_REQUIRED_RUNNING_SERVICES` (`bin/arclink-docker.sh:26-49`) lists none of the brokers/helpers. The explicit HTTP probes (`:729-746`) cover only arclink-mcp/notion-webhook/control-api/control-web/nextcloud/qmd/redis/postgres/health-watch. The in-container `required_jobs` list in `bin/docker-health.sh:217-229` is also broker-free. A post-start broker crash is therefore invisible to `control health` until a recurring job happens to fail. Re-verified at the exact cited lines.

- **NEW-2 (LOW) — job status writes are non-atomic.** `write_running_status` and `write_status` call `status_file.write_text(...)` directly with no temp+rename (`bin/docker-job-loop.sh:113` running, `:90`/final writer body). A crash mid-write leaves truncated JSON; `bin/docker-health.sh:245-249` treats unparseable JSON as `invalid_json` (no last-good fallback). Re-verified at the cited lines.

### Verify-pass new gaps independently re-checked (carried into the federation record)

- **G1 (MEDIUM) = Codex CONFIRM** — same as resolution #1/#1b; CONFIRMED.
- **G2 (MEDIUM) = Codex CONFIRM** — same as resolution #2; CONFIRMED.
- **G4 (LOW) = Codex REFINE** — same as resolution #5; CONFIRMED.
- **G3 (LOW) — standalone Nextcloud `redis` no healthcheck, `app` `depends_on` list-form (no `service_healthy`)** — re-verified `compose/nextcloud-compose.yml:11,17-28`; race-prone vs embedded stack which gates on `service_healthy`. CONFIRMED (Codex did not adjudicate it; adjudicator ratifies as a real LOW).
- **G5 (LOW) — `health()` fail-open on tailnet publish + service-health refresh** (`bin/arclink-docker.sh:747-748` `... || true` then prints "Docker health passed." `:749`). Re-verified. CONFIRMED.
- **G6 (INFO) — `health()` mutates state** (`repair_running_nextcloud_data_dir` chown/chmod called from health, `:737,658-677`). Re-verified `:737`. CONFIRMED (INFO).
- **G7 (INFO) — both Nextcloud stacks default host port 18080** (`compose.yaml:289`; `compose/nextcloud-compose.yml:30`) — collision if both run. CONFIRMED (INFO).

### REJECTED
None. No Codex or verify new-finding failed re-verification.

---

## SEVERITY CHANGES (code-supported only; from -> to)

| Risk | From | To | Cite |
|------|------|----|------|
| "Job status output secret-redacted at two layers" framed as a STRENGTH | STRENGTH | MEDIUM fail-open | `bin/docker-job-loop.sh:44,72` (empirical: `ARCLINK_*_TOKEN`/`*_SECRET`/`broker_token`/`my_secret` all leak; `Authorization: Bearer` mis-redacts) |
| "Seven scoped `internal:true` request lanes" containment framed as clean | clean containment | MEDIUM (one root helper egress-exposed) | `compose.yaml:944,1177` (`agent-process-helper-egress-net: {}` non-internal) + `arclink_agent_process_helper.py:937-938` (`0.0.0.0` bind) |
| `control health` broker-liveness coverage | (unstated in record) | new MEDIUM | `bin/arclink-docker.sh:26-49,729-746`; `bin/docker-health.sh:217-229` |
| Non-atomic status write | (unstated in record) | new LOW | `bin/docker-job-loop.sh:90,113`; `bin/docker-health.sh:245-249` |

All other record severities (HIGH 3-socket-holders, HIGH 4-root-services, MEDIUM writable-host-repo-bind, MEDIUM job-loop-swallows-exit, MEDIUM key-drift) are correctly calibrated and ratified unchanged.

---

## STANDING DISAGREEMENTS
None. Every material point reconciled to one code-grounded truth. The only divergences were the original record's three overstatements (redaction strength, blanket internal-net containment, `:?` seeding attribution), all of which the Claude verify pass had already caught and Codex independently confirmed in code. The Codex REFINE on "single peer" vs multi-client net membership is a precision tightening, not a contested point — adjudicator re-verified multiple clients attach each internal net while the containment property itself holds.

---

## FINAL BOTH-MODEL VERDICT

CANON-25's structural topology is fully ratified and code-confirmed: a single `arclink` Compose project, 51 services / 9 networks / 1 volume, exactly 3 writable docker.sock holders (host-root-equivalent, GAP-019), exactly 4 root `0:0` services, all published host ports loopback-bound except the deliberate private-mesh ingress bind, the trusted-host gate enforced with literal `"accepted"` in all 7 high-authority modules (default install leaves them crash-looping until explicit opt-in), and the operator-upgrade path provably queue-based (no socket).

The corrected residual surface, now signed by both models, is larger than the original record claimed: (1) the two-layer redaction is a fail-open for this piece's own `ARCLINK_*_TOKEN`/`*_SECRET` names and mis-handles `Authorization: Bearer` [MEDIUM]; (2) the root `agent-process-helper` is reachable on a non-internal egress bridge, breaking the blanket internal-net containment narrative [MEDIUM]; (3) the hard-required password `:?` seeding lives in `docker-entrypoint.sh`, not `bootstrap()`, and can legitimately fail to seed under read-only split mounts [LOW]; (4) `control health` has no direct broker liveness probe [MEDIUM]; (5) job-status writes are non-atomic [LOW]; plus the broker queue-root validation asymmetry, the fail-open health side-effects, and the standalone Nextcloud race/port-collision [LOW/INFO].

**FEDERATION SIGN-OFF: BOTH-MODEL-AGREED.**
