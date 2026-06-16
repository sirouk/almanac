# CANON-25 — Container Topology (Compose): ADVERSARIAL VERIFICATION

Verifier: independent Opus 4.8 skeptic. Method: re-opened every load-bearing line in
`compose.yaml`, `compose/nextcloud-compose.yml`, `bin/arclink-docker.sh`,
`bin/docker-job-loop.sh`, `bin/docker-health.sh`, `bin/docker-agent-supervisor.sh`,
`bin/nextcloud-up.sh`, `bin/nextcloud-down.sh`, plus the consumer ends in
`python/arclink_*` and `bin/docker-entrypoint.sh`. Citations re-read at path:line, not
trusted from the record.

## VERDICT: TRUSTWORTHY ON TOPOLOGY, BUT TWO LOAD-BEARING SECURITY CLAIMS ARE OVERSTATED

The record's *structural* claims (51 services, 9 networks, 1 volume, 3 socket holders,
4 root services, port wiring 8911-8917, trusted-host gate enforced in all 7 modules,
operator-upgrade queue contract) are CONFIRMED in code. But two of its highlighted
*strengths* are wrong or overbroad, and both live inside this piece's own files:

1. The "secret-redacted at two layers" strength FAILS for the exact `ARCLINK_*_TOKEN`
   / `ARCLINK_*_SECRET` names this compose file uses (regex `\b` anchor escape).
2. The "brokers/helpers bind 0.0.0.0 reachable only from the same `internal:true` net"
   containment claim is FALSE for `agent-process-helper`, which is also on a
   NON-internal egress net — and it is a root `0:0` helper.

Plus a wrong citation/trace on `:?` var seeding. These do not collapse the record but
they downgrade its "honest residual surface" verdict: there is more residual surface
than it claims.

---

## REFUTATIONS (claim → re-confirmed in code → verdict)

### R1 — REFUTED (overstated strength): redaction does NOT cover this file's own token names
Record OUTPUT CONTRACT (CANON-25 §OUTPUT, line 27), RISKS/secrets (line 39), and VERDICT
(line 95) present "job status output is secret-redacted at two layers" as a load-bearing
strength. The regex is `bin/docker-job-loop.sh:44,72`:
`(?i)(\b(?:token|api[_-]?key|password|...)[A-Z0-9_.-]*\b\s*[:=]\s*)(...)`.
The leading `\b` requires the secret keyword to START at a word boundary. Empirically
verified:
- `ARCLINK_GATEWAY_EXEC_BROKER_TOKEN=secretvalue123` → **NO MATCH, LEAKS**
- `ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN: secretvalue123` → **NO MATCH, LEAKS**
- `broker_token=secretvalue123` → **NO MATCH, LEAKS**
- `my_secret=hunter2` → **NO MATCH, LEAKS**
- `TOKEN=...` / `password: ...` → match (redacted)
Because the keyword is a SUFFIX preceded by `_` (a word char), there is no `\b`, so the
value escapes redaction. EVERY broker/helper token in this compose file is named
`ARCLINK_*_TOKEN` (compose.yaml:655,685,824,863,896,929,1006) and every secret is
`ARCLINK_*_SECRET`. A job that dumps its environment on failure (common: a script doing
`set -x` or `env`) writes those tokens UNREDACTED into
`$STATE_DIR/docker/jobs/<job>.json` `output_tail` (`bin/docker-job-loop.sh:88`, tail kept
to 4000 chars), which is then read by `bin/docker-health.sh:238-294` and surfaced. The
"two-layer redaction" is real but does NOT defend the secrets this piece actually holds.
Severity: MEDIUM (fail-open on the piece's own high-authority tokens).
Also: `Authorization: Bearer <secret>` mis-redacts — pattern 1 consumes `Authorization:`
and redacts the literal word `Bearer`, leaving the token exposed; pattern 2 cannot
re-match the already-consumed prefix. Verified empirically.

### R2 — REFUTED (false containment claim): agent-process-helper 0.0.0.0 is NOT internal-only
Record OUTPUT CONTRACT (line 26): "`agent-process-helper:8916` ... `0.0.0.0` here is
reachable only from the peer attached to the same `internal: true` net (`:1163-1175`)."
And VERDICT (line 95): "seven scoped `internal: true` request lanes."
Code: `agent-process-helper` attaches to TWO networks (compose.yaml:942-944):
`agent-process-helper-net` (internal, :1169-1170) AND `agent-process-helper-egress-net`,
which is declared `agent-process-helper-egress-net: {}` (compose.yaml:1177) — i.e.
**NOT internal**. The helper binds `0.0.0.0` via `ThreadingHTTPServer((host, port), ...)`
(`python/arclink_agent_process_helper.py:931-933`, host default
`ARCLINK_AGENT_PROCESS_HELPER_HOST=0.0.0.0` compose.yaml:930). So its 8916 listener is
bound on the non-internal egress interface too, not "only from the peer on the
internal:true net." No host port is published, so this is not host-exposed, but the
record's stated containment property is factually wrong for this service, and this is the
ONE service it is most wrong about because it is a `user:"0:0"` ROOT helper
(compose.yaml:918) with `cap_drop: ALL` but a writable `./arclink-priv/state` mount
(compose.yaml:934). The egress net (`{}` shares the default driver, non-internal) is
mentioned NOWHERE in the record (grep: "no mention of egress net"). Severity: MEDIUM.

### R3 — REFUTED (wrong citation + over-strong claim): `:?` var seeding
Record INPUT CONTRACT (line 19): "All `:?` vars are pre-seeded by `bootstrap()` in
`bin/arclink-docker.sh:271-285` ... so the `:?` guards effectively only fire if someone
deletes `docker.env`."
- `bin/arclink-docker.sh` `bootstrap()` lines 271-285 do NOT seed `POSTGRES_PASSWORD`
  (compose.yaml:244, hard `:?`) or `NEXTCLOUD_ADMIN_PASSWORD` (compose.yaml:294, hard
  `:?`). Grep of the entire `bootstrap()` function: those two names never appear. The
  cited line range is wrong for two of the hard-required vars.
- They are actually seeded in a DIFFERENT file: `bin/docker-entrypoint.sh:343-361`
  (`write_default_docker_config`, only when config absent or `ARCLINK_DOCKER_REWRITE_CONFIG=1`,
  guarded at :655) and "repaired" at :664-665. `bootstrap()` invokes this entrypoint at
  `bin/arclink-docker.sh:232`, but the record never traced into it and mis-attributes the
  seeding.
- "only fire if someone deletes docker.env" is over-strong: if `config_file_can_write` /
  `config_file_can_repair` returns false (entrypoint logs the read-only split-mount
  warning at :659), the passwords are NOT seeded and the `:?` guards DO fire with
  docker.env present. The record's own ADVERSARIAL SELF-CHECK #1 admits it "did not read
  docker-entrypoint.sh" — confirming the gap.
Severity: LOW (the substantive effect — normal install seeds them — holds; the citation
and the absolute "only if deleted" framing are wrong).

### R4 — CONFIRMED: 51 services / 9 networks / 1 volume
`python3 -c yaml.safe_load(compose.yaml)`: services=51, networks=9, volume=1
(`arclink-qmd`). Matches record. refuted=false.

### R5 — CONFIRMED: 3 docker.sock holders, exactly
`grep docker.sock compose.yaml` → lines 666 (deployment-exec-broker), 832
(agent-supervisor-broker), 1017 (gateway-exec-broker). No others. Matches record. The
operator-upgrade-broker references `ARCLINK_DOCKER_BINARY`/`_docker_binary()`
(`arclink_operator_upgrade_broker.py:101-105`) but its compose service has NO socket
mount, so it cannot reach a daemon in-container — consistent with the queue-not-socket
claim. refuted=false.

### R6 — CONFIRMED: 4 root (`user:"0:0"`) services
`grep 'user: "0:0"'` → 679 (migration-capture-helper), 847 (operator-upgrade-broker),
885 (agent-user-helper), 918 (agent-process-helper). Matches record RISK#2. refuted=false.

### R7 — CONFIRMED: trusted-host gate enforced at startup in all 7 modules with SystemExit
Each module main calls `require_docker_trusted_host_risk_accepted(service=..., error_cls=SystemExit)`:
deployment-exec-broker:312, agent-supervisor-broker:523, gateway-exec-broker:378,
operator-upgrade-broker:778, agent-process-helper:945, agent-user-helper:603,
migration-capture-helper:295. Literal compare to `"accepted"` after `.strip()` at
`arclink_boundary.py:80-97`, env value `DOCKER_TRUSTED_HOST_RISK_ACCEPTED_VALUE="accepted"`
(:20). Compose default empty (`${...:-}` at 654,684,823,860,895,928,1005) and bootstrap
seeds empty (`bin/arclink-docker.sh:286`). So with default env all 7 DO refuse to boot.
Record seam #5 CONFIRMED. refuted=false. (Note: each module ALSO calls the gate with
`error_cls=ValueError` on the request path — a defense-in-depth the record under-cites but
that strengthens, not weakens, its claim.)

### R8 — CONFIRMED: operator-upgrade queue contract both ends
Producer `arclink_operator_upgrade_broker.py:276-339` writes
`pending/<request_id>.json` (atomic, :295-299), reads `results/<request_id>.json` with
integer `returncode` (:357-360). Consumer `arclink_operator_upgrade_host_runner.py:87-92,
377-405` reads `pending`, writes `results`, moves to `processed`, parses integer
`returncode`. Both derive queue root from `ARCLINK_OPERATOR_UPGRADE_HOST_QUEUE_DIR`
(broker :277, runner :88). refuted=false. CAVEAT (see G4): the two ends apply DIFFERENT
validation to the env var — the record claimed symmetric derivation and missed the
asymmetry.

### R9 — CONFIRMED: control-api port seam, gateway port seam
`arclink_hosted_api.py:4372` reads `ARCLINK_API_PORT` (default 8900), serve_forever :4376.
`arclink_gateway_exec_broker.py:33 DEFAULT_PORT=8911`, :375 reads env. All DEFAULT_PORT
constants match compose `_PORT` literals (verified all 7). refuted=false.

### R10 — CONFIRMED: job-loop ↔ health key drift (record seam #6)
Producer writes `"job"` (docker-job-loop.sh:82) and `"returncode"` (:84). Consumer reads
`data.get("job_name") or data.get("job")` (docker-health.sh:250) and
`data.get("exit_code") if "exit_code" in data else data.get("returncode", 0)` (:252).
Drift is real; the `or`/`in` fallbacks keep it working. Record's "partial/NO" both-ends
verdict and MEDIUM severity are correct. refuted=false.

### R11 — CONFIRMED: every published host port is `127.0.0.1:` except control-ingress 2nd bind
Enumerated all `ports:` (yaml parse): nextcloud, arclink-mcp, qmd-mcp, operator-hermes-
dashboard, operator-nextcloud, notion-webhook, control-api, control-llm-router, and
control-ingress[0] all `127.0.0.1:`. Only control-ingress[1]
`${ARCLINK_CONTROL_PRIVATE_BIND_HOST:-127.0.0.1}:...` (compose.yaml:630) can be set
non-loopback. Matches record line 25. refuted=false.

### R12 — CONFIRMED: Nextcloud config split / data-dir divergence (record DRIFT#4)
Embedded `nextcloud` (compose.yaml:298-305) has NO `/var/www/html/data` mount and
`OVERWRITEPROTOCOL: ${NEXTCLOUD_OVERWRITEPROTOCOL:-http}` (:297, default **http**).
Standalone `compose/nextcloud-compose.yml:40` hard-codes `OVERWRITEPROTOCOL: https` and
mounts a separate `${NEXTCLOUD_DATA_DIR}:/var/www/html/data` (:44). Divergence real.
refuted=false.

### R13 — CONFIRMED: standalone files not wired into main stack
`nextcloud-up.sh`/`down.sh` invoked only from `bin/ci-install-smoke.sh:2561` and
`bin/deploy.sh:3613,5782` (non-Docker lanes), never from `compose.yaml` or
`arclink-docker.sh`. Record line 11 correct. refuted=false.

---

## NEW GAPS (neither record nor prior docs mention)

### G1 (MEDIUM) — Redaction `\b` escape leaks the piece's own broker/helper tokens
See R1. The record listed redaction as a STRENGTH; it is a fail-open for exactly the
`ARCLINK_*_TOKEN`/`ARCLINK_*_SECRET` env names used across compose.yaml:655-1006.
Cite: bin/docker-job-loop.sh:44,72 (regex) + compose.yaml:655,685,824,863,896,929,1006
(token names that escape).

### G2 (MEDIUM) — Root agent-process-helper has a non-internal egress network
See R2. `agent-process-helper-egress-net: {}` (compose.yaml:1177) is non-internal; the
root `0:0` helper (compose.yaml:918) binds 8916 on `0.0.0.0` across it. Outbound network
reachability for a root helper + listener exposed on a shared (non-internal) bridge is a
residual surface the record's containment narrative omits.
Cite: compose.yaml:918,930,942-944,1177; arclink_agent_process_helper.py:931-933.

### G3 (LOW) — Standalone Nextcloud `redis` has no healthcheck and `app` depends_on without condition
`compose/nextcloud-compose.yml`: only `db` has a healthcheck (:11); `redis` (:17-21) has
none; `app` uses list-form `depends_on: [db, redis]` (:26-28) with NO
`condition: service_healthy`. So `app` can start before db/redis are ready. The embedded
stack (compose.yaml:283-287) correctly gates on `service_healthy`. The up.sh wait loops
mask it, but the compose file itself is race-prone. Neither record nor docs note this.
Cite: compose/nextcloud-compose.yml:11,17-28.

### G4 (LOW) — Asymmetric queue-path validation between broker and host runner
Record seam #1 says both ends "compute the queue root from" the same env. They do, but
with DIFFERENT guards: broker `_host_runner_queue_root()` (arclink_operator_upgrade_broker.py:
277-288) REQUIRES `root.relative_to(host_state_root)` (must stay under priv/state);
host-runner `_queue_root()` (arclink_operator_upgrade_host_runner.py:87-92) only requires
`is_absolute()` — no containment check. The producer is stricter than the consumer. Not
exploitable through the normal compose wiring (env is fixed at compose.yaml:862), but the
record asserted symmetric derivation and missed the asymmetry it claimed to have verified
both ends of.
Cite: arclink_operator_upgrade_broker.py:284; arclink_operator_upgrade_host_runner.py:90.

### G5 (LOW) — `health()` is fail-open on tailnet publish + service-health refresh
`bin/arclink-docker.sh:747-748`: `docker_publish_tailnet_deployment_apps || true` and
`docker_refresh_deployment_service_health || true` — failures swallowed inside the health
command, so `./deploy.sh control health` can report "Docker health passed." (:749) even
when tailnet republish or deployment health refresh silently failed. Record's OUTPUT
CONTRACT for health only covers the FAIL_COUNT exit, not these swallowed side-effects.
Cite: bin/arclink-docker.sh:747-749.

### G6 (INFO) — `health()` mutates state (chown/chmod) as a side effect of a "health" check
`repair_running_nextcloud_data_dir` (bin/arclink-docker.sh:658-677, called from health
:737) execs into the running nextcloud container and `chown -R www-data` / `chmod`.
A read-only health probe performing writes is a least-surprise violation the record's
"health → prints [ok]/[warn]/[fail]" output contract does not surface.
Cite: bin/arclink-docker.sh:737,658-677.

### G7 (INFO) — Both Nextcloud stacks default to host port 18080
Embedded (compose.yaml:289) and standalone (compose/nextcloud-compose.yml:30) both bind
`127.0.0.1:${NEXTCLOUD_PORT:-18080}:80`. If both run on one host (Docker-mode stack +
a stray standalone invocation) they collide. The record separates the two topologies but
does not flag the shared default-port collision risk.
Cite: compose.yaml:289; compose/nextcloud-compose.yml:30.

---

## SEAM MISMATCHES (cross-piece)

- SEAM job-loop→health (CANON-23): producer key `job`/`returncode`
  (docker-job-loop.sh:82,84) vs consumer-first key `job_name`/`exit_code`
  (docker-health.sh:250,252). Mismatch papered over by `or`/`in` fallback. (record found
  this; re-confirmed.)
- SEAM operator-upgrade-broker→host-runner (CANON-15): record marked both-ends-verified
  "yes" — re-confirmed the pending/results/processed + integer returncode shape, but the
  env-var validation is asymmetric (G4); the "both ends verified symmetrically" framing
  is slightly stronger than the code supports.

## INTERNAL CONSISTENCY DEFECT (record self-inconsistency, INFO)
Record line 5 says "Defines **five YAML anchors**" then lists **six** anchor names in the
same parenthetical (`x-arclink-app, x-arclink-env, x-arclink-control-secret-env,
x-arclink-operator-env, x-arclink-job, x-nextcloud-db-env`). Actual file has 9 anchors
total: `&restart-unless-stopped, &healthcheck-fast, &healthcheck-http` (3 healthcheck/
restart — record correct) + `&arclink-app, &arclink-env, &arclink-control-secret-env,
&arclink-operator-env, &arclink-job, &nextcloud-db-env` (6, not 5). "Five" is an arithmetic
error. Cite: compose.yaml:3,4,8,13,18,149,165,232,241.

## RISK RE-CALIBRATION
- Record HIGH (3 socket holders, 4 root services): correctly calibrated. CONFIRMED.
- Record MEDIUM (writable host-repo bind 869, job-loop swallows exit codes, key drift):
  correctly calibrated.
- DOWNGRADE the record's "strength" framing of redaction (line 27/39/95) — it is a
  partial fail-open (G1), not a clean strength.
- ADD MEDIUM for agent-process-helper non-internal egress (G2) — the record's blanket
  "internal:true containment" was the basis for treating the unpublished 0.0.0.0 binds as
  safe; for this one root helper that basis is false.

## SUMMARY
Topology and wiring: trustworthy and code-confirmed. Two security strengths the record
leans on (two-layer secret redaction; internal-net containment of all broker binds) are
overstated and refuted in code for cases that involve THIS piece's own tokens and its one
root egress-connected helper. One input-contract citation (`:?` seeding at
arclink-docker.sh:271-285) is wrong — the seeding lives in docker-entrypoint.sh, which the
record admits it did not read. The record remains useful but its VERDICT's "honest
residual surface ... none contradict the stated contract" is itself too generous: the
redaction strength claim and the internal-net containment claim ARE contradicted by code.
