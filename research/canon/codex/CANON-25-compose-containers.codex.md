<<<CODEX-VERDICT-START CANON-25>>>
## CANON-25 — Codex (GPT-5.5 xhigh) ratification
SIGN-OFF: OBJECT(2)
ONE-LINE VERDICT: Core compose topology is ratifiable, but the verifier’s redaction/egress corrections stand and I add two health/status robustness defects.

### Adjudication (each: CONFIRM/REFUTE/REFINE + path:line)
- CONFIRM risk: the 3 Docker-socket holders are host-root-equivalent on compromise: `deployment-exec-broker`, `agent-supervisor-broker`, `gateway-exec-broker` mount `/var/run/docker.sock` rw at `compose.yaml:666`, `compose.yaml:832`, `compose.yaml:1017`.
- CONFIRM risk: 4 services run as container root: `migration-capture-helper`, `operator-upgrade-broker`, `agent-user-helper`, `agent-process-helper` at `compose.yaml:679`, `compose.yaml:847`, `compose.yaml:885`, `compose.yaml:918`.
- CONFIRM risk: redaction is fail-open for ArcLink token names. The regex requires the keyword at a word boundary, so `ARCLINK_*_TOKEN` misses; status keeps `output_tail` at `bin/docker-job-loop.sh:72`, `bin/docker-job-loop.sh:88`, with token envs at `compose.yaml:655`, `compose.yaml:685`, `compose.yaml:824`, `compose.yaml:863`, `compose.yaml:896`, `compose.yaml:929`, `compose.yaml:1006`.
- CONFIRM risk: `agent-process-helper` is root, binds `0.0.0.0:8916`, and is also on non-internal `agent-process-helper-egress-net`: `compose.yaml:918`, `compose.yaml:930`, `compose.yaml:942-944`, `compose.yaml:1177`; server binds env host/port at `python/arclink_agent_process_helper.py:931-945`.
- CONFIRM risk: `operator-upgrade-broker` mounts the live host repo writable while root: `compose.yaml:847`, `compose.yaml:869`.
- CONFIRM risk: `docker-job-loop.sh` swallows child failures into JSON and never exits nonzero to the supervisor: `bin/docker-job-loop.sh:132-136`, `bin/docker-job-loop.sh:141-144`.
- REFUTE §5.B42 auto-accept concern: tracked code does not synthesize `accepted`; compose defaults empty, entrypoint writes the incoming value, and bootstrap seeds empty: `compose.yaml:654`, `bin/docker-entrypoint.sh:355`, `bin/docker-entrypoint.sh:470`, `bin/arclink-docker.sh:286`; gate requires literal `accepted` at `python/arclink_boundary.py:80-97`.
- REFUTE §5.B42 strict job-status-key concern as of this tree: `docker-health` falls back from `job_name/exit_code` to `job/returncode`, and dashboard reads only status/timestamps/interval: `bin/docker-health.sh:250-252`, `python/arclink_dashboard.py:457-491`.
- REFINE §5.B42 broker-net client claim: not “single peer”; compose attaches multiple clients to several internal nets, e.g. deployment exec broker/provisioner/action-worker at `compose.yaml:669`, `compose.yaml:730`, `compose.yaml:774`, and gateway/operator nets include operator Hermes/dashboard plus workers at `compose.yaml:390-391`, `compose.yaml:430-431`, `compose.yaml:987-992`, `compose.yaml:1050-1052`.
- CONFIRM seam: operator-upgrade is queue-based, not socket-based; compose passes queue dir at `compose.yaml:862`, broker writes pending/results at `python/arclink_operator_upgrade_broker.py:312-360`, runner drains pending/results/processed at `python/arclink_operator_upgrade_host_runner.py:367-414`.
- REFINE seam: queue-root validation is asymmetric; broker enforces private-state containment, runner only absolute path: `python/arclink_operator_upgrade_broker.py:276-288`, `python/arclink_operator_upgrade_host_runner.py:87-92`.
- CONFIRM seam: control-api port wiring matches compose to hosted API: `compose.yaml:73`, `compose.yaml:550-561`, `python/arclink_hosted_api.py:4371-4376`.
- CONFIRM seam drift: producer writes `job/returncode`, consumer first reads `job_name/exit_code` but survives via fallback: `bin/docker-job-loop.sh:81-90`, `bin/docker-health.sh:250-252`.

### New findings both Claude passes missed (severity + path:line)
- MEDIUM: `./deploy.sh control health` omits direct liveness checks for all 7 broker/helper services. Required-running list excludes them, explicit probes check only core HTTP/qmd/redis/postgres/health-watch, and in-container health checks recurring jobs only; a post-start broker crash can be missed until a job happens to fail. `bin/arclink-docker.sh:26-49`, `bin/arclink-docker.sh:729-746`, `bin/docker-health.sh:217-229`.
- LOW: job status writes are non-atomic direct `write_text` calls; a crash during write can leave transient/corrupt JSON, which health treats as invalid status rather than recovering from a last-good file. `bin/docker-job-loop.sh:90`, `bin/docker-job-loop.sh:113`, `bin/docker-health.sh:245-249`.

### Claude citations re-confirmed or corrected
- Re-confirmed topology: 51 services, 1 named volume, 9 networks from compose structure: `compose.yaml:246`, `compose.yaml:1158-1177`.
- Re-confirmed all high-authority startup gates call `require_docker_trusted_host_risk_accepted(..., SystemExit)`: e.g. `python/arclink_deployment_exec_broker.py:312`, `python/arclink_gateway_exec_broker.py:378`, `python/arclink_agent_process_helper.py:945`; literal gate at `python/arclink_boundary.py:80-97`.
- Corrected original record: `POSTGRES_PASSWORD` and `NEXTCLOUD_ADMIN_PASSWORD` are seeded/repaired through `docker-entrypoint.sh`, not `arclink-docker.sh:271-285`: `bin/docker-entrypoint.sh:343-361`, `bin/docker-entrypoint.sh:655-665`.
- Re-confirmed Nextcloud topology split: embedded stack defaults protocol to `http` and no separate data mount; standalone defaults `https` and mounts `${NEXTCLOUD_DATA_DIR}`: `compose.yaml:297-305`, `compose/nextcloud-compose.yml:40-44`.
- Re-confirmed docker-only main compose wrapper: `bin/arclink-docker.sh:117-124`; podman-compatible compose helpers are not used by this path.

### Residual disagreement with the Claude half (for final reconciliation)
- No disagreement with the verifier’s main corrections. Disagreement remains with the original auditor record where it framed redaction as a clean strength, claimed blanket internal-net containment for all `0.0.0.0` helpers, and misattributed hard-required password seeding.
<<<CODEX-VERDICT-END CANON-25>>>
