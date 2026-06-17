# CANON-25 — Container Topology (Compose): FINAL ADJUDICATED DECISIONS

- **Piece:** CANON-25 — Container Topology (Compose)
- **Mode:** DECISION (operator calls deferred by the Codex repair campaign)
- **Adjudicator:** Claude Opus 4.8 (final), reconciling with Codex GPT-5.5 xhigh
- **Method:** Each decision re-grounded by re-opening the cited code (`sed -n`/`grep`) and
  the symphony north star, not by trusting either model's prior claim. Where the
  committed tree already moved past the reconciled record, that is noted — two of the
  reconciled record's residual findings (broker liveness probe NEW-1, redaction fail-open
  G1, non-atomic writes NEW-2, key drift #6) are **already repaired** in commit `7cf2565`
  and are NOT pending decisions. The four items below are the genuine deferrals.

---

## DECISION 1 — `agent-process-helper` egress exposure of its root command listener  [VERDICT: refine]

### The question
The root (`0:0`) `agent-process-helper` binds its HTTP command API to `0.0.0.0:8916`
(`compose.yaml:957`, `python/arclink_agent_process_helper.py:932` `ThreadingHTTPServer((host,port))`)
and attaches to the **non-internal** `agent-process-helper-egress-net`
(`compose.yaml:945,1178` — `agent-process-helper-egress-net: {}`, no `internal: true`).
The egress net exists to give spawned agent processes outbound internet for real runtime
work. The `internal: true` containment narrative therefore does not fully hold for this one
root helper. How do we keep egress without exposing the command surface, and fail closed?

### My independent reasoning (code-grounded)
The exposure today is **latent, not live**:
- The supervisor reaches the helper over the **internal** `agent-process-helper-net`
  (`compose.yaml:944`, supervisor attaches it `:991`), NOT over egress. The egress net is
  **single-member** — only `agent-process-helper` attaches (`tests/test_arclink_docker.py:853`,
  `:882`; runbook `GAP-019-AK` `operations-runbook.md:674-676` pins it single-service).
- Because no other container shares the egress bridge, the `0.0.0.0:8916` listener has **no
  reachable peer on that interface** right now. The risk is design fragility: one accidental
  attach to egress, or a Docker bridge-isolation gap, exposes the root command API to a lane
  whose purpose is open outbound traffic.

So the defect is real (the listener should not be bound on an interface whose job is the open
internet) but its current blast radius is "one compose edit away from live," not "live now."

Codex's end-state — move the command API off TCP onto a **Unix socket** on a narrow shared
volume mounted only into `agent-process-helper` and `agent-supervisor` — is the correct
symphony shape: the command lane becomes reachable only by the source-owned supervisor, the
egress net carries only spawned-process outbound traffic, and there is no inbound listener on
the egress interface at all. That fully severs command-surface from egress. It is also the
honest fix for "bounded broker/helper contracts." But it is HIGH effort: it rewrites the
helper transport, the supervisor client, the healthcheck (Unix-socket curl), the authority
inventory, and a dense set of Docker regression tests, for an exposure that is currently
latent. Binding to a fixed internal-net IP instead is brittle (Docker IPAM-dependent) — Codex
is right to reject it.

### Where I agree / differ from Codex
I agree the Unix socket is the right **destination**. I differ on sequencing and on treating
it as a single HIGH leap. The symphony wants every step to **fail closed** with a local proof
gate; we can get the fail-closed property far cheaper *first*, then land the socket as the
durable end-state. Specifically: the cheapest immediate fail-closed step is to **stop binding
the command listener on the egress interface** and keep it on the request-net interface only,
while keeping token auth. Since pinning a Docker-IPAM IP is brittle, the robust interim is to
bind `127.0.0.1` for health and gate the request lane so that a request arriving on the egress
interface source is rejected (source-net check) — but the clean, non-brittle version of "not
on egress" is exactly the Unix socket. So I refine to a **staged plan**: ship the test/policy
fail-closed guard now, ship the socket as the planned hardening.

### FINAL PLAN
1. **Now (low):** Add a fail-closed regression that *pins the single-member egress invariant as
   a hard gate* (it currently asserts membership; make a drift here fail the Docker suite and
   the authority-inventory check), and add a startup assertion in
   `python/arclink_agent_process_helper.py` that refuses to serve if its bind host is a
   non-loopback wildcard while the egress net is present unless an explicit
   `ARCLINK_AGENT_PROCESS_HELPER_ALLOW_WILDCARD_BIND=1` is set — so the exposed posture is
   opt-in and loud, not the default. This makes the latent exposure fail closed without a
   transport rewrite.
2. **Hardening (high):** Land Codex's Unix-socket transport. Replace
   `ARCLINK_AGENT_PROCESS_HELPER_URL=http://agent-process-helper:8916` with a Unix socket on a
   narrow runtime volume mounted only into `agent-process-helper` and `agent-supervisor`;
   remove the `0.0.0.0` listener at `compose.yaml:957`; healthcheck the socket (or a
   `127.0.0.1`-only health port); update `arclink_docker_agent_supervisor.py:412`,
   `arclink_agent_process_helper.py:932-944`, `compose.yaml`,
   `config/docker-authority-inventory.json`, and the Docker regression tests so a
   missing/unsafe socket means **no process action**.
3. **Live gate:** `PG-HERMES` proof that real agent process work (spawn + outbound runtime)
   still functions over the socket lane, with redacted evidence.

### Symphony anchor
`Pods, Isolation, And SOUL`: *"Terminal and process execution stay behind bounded broker/helper
contracts"* and *"Docker/root authority on the host is treated as a high-trust boundary until
stronger isolation is implemented."* (`sovereign-control-node-symphony.md:553-556`)

### Effort / blast-radius
Staged: step 1 **low** (test + opt-in bind guard); step 2 **high** (transport, supervisor
client, healthcheck, authority inventory, docs, ~6 Docker test assertions). Blast radius of the
socket step touches compose topology and the agent-process execution path; gated behind
`PG-HERMES`.

---

## DECISION 2 — `docker-job-loop.sh` exit-on-child-failure policy  [VERDICT: agree-codex]

### The question
`docker-job-loop.sh` runs `while true; do run_job_once; sleep; done`
(`bin/docker-job-loop.sh:177-180`); `run_job_once` (`:162-175`) captures the child rc into the
status JSON but the loop never exits, so `restart: unless-stopped` never trips and a
perpetually-failing recurring job stays "running" at the process level. Should child failure
crash the container?

### My independent reasoning (code-grounded)
These are **recurring pollers and repair loops**, not one-shot daemons — health-watch (300s),
notification delivery, fleet inventory, qmd, backup, ssot-batcher, etc., all wrap
`docker-job-loop.sh` (`compose.yaml` job declarations). A blanket `exit $rc` would convert
every transient child failure (a provider blip, a momentarily-locked DB) into a container
crash + Docker restart, changing retry cadence across the whole fleet and risking restart
storms that don't repair the underlying cause. That directly violates the symphony's
"retry or repair path" intent.

The committed tree already does the hard half correctly: `run_job_once` writes redacted,
atomic `status=fail`/`exit_code` evidence (`:84-90` dual keys, `os.replace` atomic), and the
campaign added direct broker liveness probes and the required-jobs/health coverage so a failing
job is **owner-visible**. So the contract the symphony actually demands — owner-visible state +
evidence — is met by continuing, NOT by crashing. Crashing would *lose* the running-state
distinction and hide job-specific policy inside supervisor behavior.

The one legitimate need for exit is a small set of jobs where a hard failure genuinely should
stop the loop (e.g. a fatal config error that will never self-heal). That is a per-job product
call, not a global default.

### Where I agree / differ from Codex
Full agreement. Codify the current default as `failure_policy=continue` (state+evidence first),
and add an explicit opt-in `--failure-policy continue|exit|exit-after=N` so the rare
must-exit job declares it in Compose and exits only **after** writing final redacted evidence.
The residual risk Codex names — a container showing "running" while work fails — is closed by
keeping the health/status consumer strict and complete, which the committed `docker-health.sh`
required-jobs coverage now does.

### FINAL PLAN
1. Keep `while true` continue as the default; do not globally `exit $rc`.
2. Add `--failure-policy continue|exit|exit-after=N` to `bin/docker-job-loop.sh` arg parsing
   (after the existing `<job> <interval>` positionals). `continue` is default and identical to
   today. `exit` exits with the child rc *after* `write_status` has flushed final evidence.
   `exit-after=N` exits only after N consecutive failures.
3. Any job that opts into `exit`/`exit-after` declares it in its `compose.yaml` `command:`
   array — the policy lives in the source-owned Compose declaration, not in supervisor magic.
4. Test: assert default failures remain `status=fail` with the loop alive, and that an
   `exit`-policy job writes final evidence before exiting. Add a coverage test that every
   active `docker-job-loop` service has a health/evidence consumer (closes the
   missed-status-coverage residual).

### Symphony anchor
`Notifications, Incidents, And Evidence`: *"Every important background path should have an
owner-visible state, a retry or repair path, and evidence that can be shared without secrets."*
(`sovereign-control-node-symphony.md:979-981`)

### Effort / blast-radius
**Med.** Touches `bin/docker-job-loop.sh` arg parse + loop, optional `compose.yaml` per-job
declarations, `bin/docker-health.sh` coverage, and tests. No change to the common-case cadence,
so low operational blast radius.

---

## DECISION 3 — `control health` silently repairing Nextcloud data permissions  [VERDICT: agree-codex]

### The question
`health()` calls `repair_running_nextcloud_data_dir` (`bin/arclink-docker.sh:753`) before
probing Nextcloud. That function `chown -R www-data`, `chmod 0770/0644`, and creates `.ncdata`
/`index.html` inside the running container (`:667-685`), suppressing errors with `|| true`.
A diagnostic command mutates runtime state and can mask drift. Keep, remove, or split?

### My independent reasoning (code-grounded)
A health command that **silently mutates** state violates same-truth diagnostics: it can turn a
genuine permission-drift fault green by repairing it mid-probe, so the operator never learns the
drift happened, and `health` ceases to be a faithful read of reality. The `|| true` error
suppression compounds this — a failed repair is invisible. This is the symphony's exact
anti-pattern: recoverability must be provable *without surprising the Captain or destroying
state*, and health must be honest.

But removing the repair outright would regress live recovery for the harmless, common case
(a container restart leaving `data/` owned wrong), which is a real operability win today. So the
right move is Codex's **split**: read-only health that fails closed with the exact repair
command, plus an explicit operator-owned repair action. This makes the operator the action
owner (symphony: operators own backups/recovery), preserves state by default, and leaves
evidence.

### Where I agree / differ from Codex
Full agreement on the split. One refinement: the install/upgrade lane *may* still call the
repair as a **clearly-labelled mutating pre-health step** (Codex allows this) — I want that to
be explicit and logged, not implicit, so the only place state is mutated is a named
install/upgrade/repair action, never `health`. Also: the read-only check must NOT use `|| true`
suppression — it must surface the actual owner/mode it found vs expected.

### FINAL PLAN
1. Replace the `health()` call at `bin/arclink-docker.sh:753` with a **read-only**
   `check_running_nextcloud_data_dir` that inspects `.ncdata`, `index.html`, owner, and mode and
   on mismatch prints `FAIL` with the exact remediation command and returns 1 (fail closed,
   no mutation, no `|| true` swallowing).
2. Add an explicit operator command `./deploy.sh control repair nextcloud-data` (routed in
   `deploy.sh`/`bin/arclink-docker.sh`) that runs the existing `repair_running_nextcloud_data_dir`
   body, supports a dry-run print of the chown/chmod it would do, and writes a redacted evidence
   record under private state.
3. Install/upgrade may invoke the repair as an explicit, logged pre-health step (clearly a
   mutating action), so live recovery for harmless drift is preserved — just no longer hidden
   inside a diagnostic.
4. Tests: health regression asserts no mutation occurs and that drift fails closed with the
   remediation copy; repair-command regression asserts the chown/chmod + evidence path.

### Symphony anchor
`Backup, Restore, And Data Lifecycle`: *"It must mean the Operator can prove recoverability
without surprising the Captain or destroying state."* (`sovereign-control-node-symphony.md:934-935`)

### Effort / blast-radius
**Med.** Touches `bin/arclink-docker.sh` (`health()` + new check + repair command), `deploy.sh`
command routing, runbook/docs, and health/Nextcloud regression tests. Operationally low risk:
recovery stays available, only its ownership and visibility change.

---

## DECISION 4 — embedded vs standalone Nextcloud sharing the `18080` host-port default  [VERDICT: refine]

### The question
The embedded Control Node `nextcloud` (`compose.yaml:290`) and the standalone legacy sidecar
(`compose/nextcloud-compose.yml:37`) both publish `127.0.0.1:${NEXTCLOUD_PORT:-18080}:80`. They
do not merely share a default — they read the **same env var** `NEXTCLOUD_PORT`, which
`bin/common.sh:456` sets to `18080` and exports via `with_nextcloud_compose_env`
(`:1602,1615`). If both ran on one host they would collide at bind time. Give the standalone its
own port?

### My independent reasoning (code-grounded)
Key code fact Codex's writeup under-states: the two stacks share the **same variable**, not just
the same default. So you cannot disambiguate one by setting `NEXTCLOUD_PORT` — that moves both.
The fix must introduce a **distinct key** for the standalone. There is a direct, established
precedent in-tree: the operator's own Nextcloud already uses a separate key
`ARCLINK_OPERATOR_NEXTCLOUD_PORT:-28081` (`compose.yaml:506`), seeded by bootstrap
(`bin/arclink-docker.sh:289`). That is exactly the shape Codex proposes.

The Control Node embedded `18080` is the canonical public lane and is test-pinned
(`tests/test_arclink_docker.py:531`), so it must stay stable. The standalone file is
legacy/Almanac-era migration tooling driven by `bin/nextcloud-up.sh`/`down.sh`/
`rotate-nextcloud-secrets.sh`/`bin/health.sh` and exercised in `bin/ci-install-smoke.sh:2578`.
Giving it its own source-owned default removes the silent same-host race while honoring any
already-explicit `NEXTCLOUD_PORT` an old operator set.

A pure-default change still fails late at bind time if both want their default simultaneously,
so the symphony's "reconfigure is safe for changing ports without silently deleting runtime
state" demands a **collision preflight** that fails closed with operator copy naming the exact
port to change — that is the part that makes this honest rather than just relocated.

### Where I agree / differ from Codex
Agree with the separate-key approach and the `18081` standalone default. I **refine** on two
points grounded in code: (1) because the two stacks share the *same variable* today, the change
must add `ARCLINK_STANDALONE_NEXTCLOUD_PORT` and switch `compose/nextcloud-compose.yml` +
`bin/common.sh` standalone export to read it, while the embedded stack keeps `NEXTCLOUD_PORT` —
this is a slightly larger touch than "give it a default" implies. (2) The collision preflight is
load-bearing, not optional: it is the only thing that turns a late bind error into a same-truth,
fail-closed operator message.

### FINAL PLAN
1. Embedded Control Node `nextcloud` keeps `${NEXTCLOUD_PORT:-18080}` (`compose.yaml:290`) —
   unchanged, test pin (`tests/test_arclink_docker.py:531`) preserved.
2. Standalone sidecar gets its own key: `compose/nextcloud-compose.yml:37` ->
   `127.0.0.1:${ARCLINK_STANDALONE_NEXTCLOUD_PORT:-18081}:80`. Update `bin/nextcloud-up.sh`
   (`:322,460`), `bin/nextcloud-down.sh`, `bin/rotate-nextcloud-secrets.sh`, `bin/health.sh`,
   and the `bin/common.sh` standalone export (`:456,1615`) to read the new key.
3. **Honor existing state:** if an operator has already explicitly set `NEXTCLOUD_PORT` for the
   standalone path, honor it (back-compat) — only the *unset default* moves to `18081`.
4. **Collision preflight (load-bearing):** `nextcloud-up.sh` and the embedded `health()`/install
   path fail closed if the chosen port is already owned by the other stack, with copy naming
   exactly which port to change. Follow the `ARCLINK_OPERATOR_NEXTCLOUD_PORT:-28081` precedent.
5. Tests: standalone compose pins `${ARCLINK_STANDALONE_NEXTCLOUD_PORT:-18081}`; a preflight
   regression asserts the collision message.

### Symphony anchor
`Configuration, Schema, And Migration`: *"Reconfigure is safe for changing ports, ingress mode,
provider defaults... without silently deleting runtime state."*
(`sovereign-control-node-symphony.md:1083-1085`)

### Effort / blast-radius
**Med.** Touches the standalone Nextcloud scripts, `compose/nextcloud-compose.yml`,
`bin/common.sh` defaults, deploy/runbook docs, and port regression tests. Embedded canonical
lane untouched; back-compat preserved for already-explicit configs.

---

## STANDING DISAGREEMENTS (genuine operator product forks)
None of the four require a contested product fork — all four converge to a single recommended
plan. The only sequencing fork is internal to Decision 1 (ship the low fail-closed guard now vs
wait for the high Unix-socket landing); both land the same end-state, so it is a scheduling
call, not a competing-truth disagreement.

## NOTE ON ALREADY-REPAIRED ITEMS (not pending decisions)
The reconciled record's NEW-1 (no broker liveness probe), G1 (redaction fail-open on
`ARCLINK_*_TOKEN`/`*_SECRET` and `Authorization: Bearer`), NEW-2 (non-atomic status writes), and
#6 (job-status key drift) are **already fixed** in committed `bin/docker-job-loop.sh` /
`bin/arclink-docker.sh` (commit `7cf2565`): redaction now uses `\b[A-Z0-9_.-]*` prefixes and
consumes the `Bearer/Basic` scheme word (`docker-job-loop.sh:43-46,71-78`); status writes are
atomic `os.replace` (`:90-108`); both `job`/`job_name` and `returncode`/`exit_code` are emitted
(`:84-88,127-128`); all 7 brokers/helpers now have direct liveness probes in `health()`
(`arclink-docker.sh:746-752`) and are in `DOCKER_REQUIRED_RUNNING_SERVICES` (`:26-52`). They are
recorded here only so the operator does not re-open settled work.
