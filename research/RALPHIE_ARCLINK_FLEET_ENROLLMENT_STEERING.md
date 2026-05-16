# Ralphie Steering: ArcLink Sovereign Fleet — Enterprise-Grade Worker Enrollment And Placement

## Mission Statement

ArcLink's Sovereign Control Node must operate a planet-scale fleet of worker
machines with the rigor expected of an enterprise system: cryptographic
identity, observable health, auditable lifecycle, idempotent operations,
graceful degradation, region-aware placement, and zero hand-rolled steps.
This mission lifts the existing fleet scaffolding (already present in
`deploy.sh`, `python/arclink_fleet.py`, `python/arclink_inventory.py`,
`python/arclink_sovereign_worker.py`, `python/arclink_executor.py`) into a
production-grade system that an operator can run worldwide and that an
auditor can sign off on.

The mission is **adapt and harden** the current implementation, not rewrite.
Most of the data model and shell-level surfaces exist. What is missing is
production-grade rigor: scriptable non-interactive flows, structured output,
periodic probing, placement-aware day-2 routing, cryptographically attested
enrollment, observability, compliance hooks, and end-to-end coherence between
the two existing host registries.

## Current Reality (as of `5d00a83`)

Implemented and load-bearing — keep, harden, do not rewrite:

- **`bin/deploy.sh control fleet-key`** (deploy.sh:8636-8751) — Ed25519
  keypair generation, idempotent, prints guidance. Production-grade.
- **`bin/deploy.sh control register-worker`** (deploy.sh:8936-9111) — registers
  a remote host via `python/arclink_fleet.py:register_fleet_host`. **Interactive
  TTY-only**; refuses non-TTY input.
- **`bin/deploy.sh control inventory list|probe|drain|remove`** (deploy.sh:9113-9213)
  — wraps `python/arclink_inventory.py`. `probe` actually SSHes to the host
  and detects hardware. `list`, `drain`, `remove` are scriptable.
- **`python/arclink_inventory.py:probe_inventory_machine`** (arclink_inventory.py:241-320)
  — real SSH probe, sets `status='ready'` or `'degraded'`, updates the linked
  fleet host.
- **`python/arclink_fleet.py:place_deployment`** — deterministic, capacity-aware,
  rejects draining/saturated/unhealthy hosts, atomic placement, fully tested
  in `tests/test_arclink_fleet.py`.
- **`python/arclink_sovereign_worker.py`** — runs as a compose service, picks
  per-host executor via `_executor_for_host` (arclink_sovereign_worker.py:997-1046),
  dispatches provisioning to the correct fleet host.
- **Schema** — `arclink_inventory_machines` (arclink_control.py:1304) and
  `arclink_fleet_hosts` (arclink_control.py:1910) coexist with a one-to-one
  link via `machine_host_link`. Both are populated by the registration paths.

Stub or partial — must finish for enterprise grade:

- **`bin/deploy.sh control register-worker`** is TTY-only. No non-interactive
  registration path.
- **`bin/deploy.sh control inventory add hetzner|linode`** lists existing
  cloud servers, does not provision new ones.
- **`bin/deploy.sh control inventory set-strategy`** persists the env var
  but no placement code consumes it.
- **No periodic probing daemon.** `probe` is on-demand only; `last_probed_at`
  drifts unbounded.
- **No `inventory health` summary command.** Fleet-wide health is not a
  first-class surface.
- **CLI output is human-prose**. No `--json` mode for automation.

Missing — must be added:

- **Placement-aware action worker.** `python/arclink_action_worker.py:858-910`
  reads a single static `ARCLINK_ACTION_WORKER_SSH_HOST` from env and uses it
  for every deployment-scoped action (restart, teardown, rollout, pause/resume,
  migration). Day-2 ops route to the wrong host on any multi-worker fleet.
  This is the load-bearing gap; nothing else matters without it.
- **Cryptographically attested enrollment.** No HMAC-bound enrollment tokens,
  no single-use semantics, no machine fingerprint attestation. SSH key alone
  is insufficient for enterprise trust.
- **Probe SLIs and degradation thresholds.** Status transitions are manual;
  no automatic `degraded → active` recovery, no threshold-based escalation.
- **Audit log integration for fleet lifecycle.** Host state transitions are
  not written to `arclink_audit_log` with operator attribution.
- **Operator observability surface.** No fleet-health dashboard tile, no
  metrics, no `notification_outbox` integration for fleet alerts.
- **Cloud provider provisioning.** Hetzner and Linode integrations list but
  do not create machines, bootstrap them, or take responsibility for billing
  attribution.
- **Multi-region placement preference.** `region` column exists; placement
  ignores it.
- **Disaster recovery for the control plane.** No documented playbook for
  re-enrolling all workers if the control plane DB is restored from backup.

## Architectural Principles

These principles are non-negotiable. Any task in this mission that conflicts
with one of these must be raised as a blocked product question, not silently
relaxed.

1. **Zero trust between control plane and workers.** Every probe, every
   deploy, every action is authenticated and authorized. SSH key compromise
   is bounded by per-action allowlists and audit log review.
2. **Idempotent everything.** Every CLI subcommand, every API route, every
   probe loop must be safely re-runnable. Idempotency keys for cloud-provider
   API calls. State transitions are no-ops when already in the target state.
3. **Observable by default.** Every host state transition, every probe
   attempt, every registration, drain, and removal writes a structured audit
   log entry. Fleet-wide health is a first-class operator surface.
4. **Backwards-compatible.** Existing single-host installs (the default
   today) must continue to work without operator action. Schema changes are
   additive. CLI changes preserve existing argv shapes.
5. **Fail closed.** Bootstrap script failure leaves the machine in a
   non-admitting state. Token validation failure rejects the enrollment.
   Probe wrapper rejects unknown verbs. Placement filter excludes any host
   not in `active` or `verified`.
6. **Operator-owned trust roots.** The operator owns the SSH key, the
   enrollment token mint authority, and the audit log. The control plane is
   the operator's tool, not a third-party service.
7. **Worldwide-capable.** UTC storage everywhere; render in operator
   timezone. Region-aware placement. Multi-region tagging. No assumption of
   single-AZ deployment.
8. **No live-credential dependency in CI.** All tests use fake adapters.
   Real-host proof is operator-authorized, recorded as evidence, never
   automated.

## Constraints

- Do not touch `arclink-priv`, live secrets, deploy keys, production
  services, payment/provider mutations, public bot command registration,
  Docker install/upgrade, or Hermes core.
- Do not run live `./deploy.sh control install`, `./deploy.sh upgrade`,
  cloud-provider provisioning calls, or remote SSH against non-local hosts
  unless the operator explicitly authorizes that step as live proof.
- Do not deprecate the existing `arclink_fleet_hosts` or
  `arclink_inventory_machines` tables. Both are referenced by production
  code paths. Formalize the separation of concerns instead.
- Do not introduce a new CLI binary. The canonical operator surface is
  `bin/deploy.sh control ...`. All new subcommands extend the existing
  dispatch.
- Operator-facing UX (CLI prose, dashboard text, error messages) uses
  Operator vocabulary. Captain-facing UX uses ArcPod / Pod / Agent / Captain
  / Crew / Raven per `docs/arclink/vocabulary.md`.
- Preserve secret redaction discipline. Tokens, keys, fingerprints, and
  cloud-provider credentials must never appear in argv, env exposure, logs,
  or commits. Reuse `arclink_evidence.redact_value`.
- All net-new schema is idempotent and additive. Migrations run twice
  without error.

## Schema Reconciliation

The two tables coexist intentionally and represent different concerns. This
mission formalizes the separation and adds the missing fields for
enterprise rigor.

| Concern | Table | Why this table |
|---|---|---|
| Physical / cloud machine identity, hardware, lifecycle, provider attribution | `arclink_inventory_machines` (arclink_control.py:1304) | Operator-facing inventory. Stable across host re-registration. |
| Placement target: capacity slot, load, drain flag, region, allowlist mapping | `arclink_fleet_hosts` (arclink_control.py:1910) | Provisioning-facing placement registry. Consumed by `place_deployment`. |

Invariant: every `arclink_fleet_hosts` row has exactly one corresponding
`arclink_inventory_machines` row, joined via `machine_host_link`. A new
reconciler enforces this at startup and on every probe cycle. Orphans on
either side surface as operator-visible drift, not silent corruption.

### Schema additions (idempotent, backwards-compatible)

`arclink_inventory_machines` extensions:
- `enrollment_id TEXT NOT NULL DEFAULT ''` — foreign key to
  `arclink_fleet_enrollments`.
- `machine_fingerprint TEXT NOT NULL DEFAULT ''` — captured at enrollment
  callback; immutable thereafter.
- `attested_at TEXT NOT NULL DEFAULT ''` — UTC ISO-8601 timestamp of the
  successful enrollment-callback handshake.
- `audit_trail_chain TEXT NOT NULL DEFAULT ''` — append-only hash chain of
  the host's state transitions; new entries reference the prior hash.
- `provider_billing_ref TEXT NOT NULL DEFAULT ''` — cloud-provider billing
  account / project identifier (operator-scoped, never tenant-exposed).

`arclink_fleet_hosts` extensions:
- `region_tier TEXT NOT NULL DEFAULT ''` — operator-assigned tier
  (`primary | secondary | dr`) for placement preference.
- `placement_priority INTEGER NOT NULL DEFAULT 0` — higher integer = preferred
  within a tier.
- `last_health_state TEXT NOT NULL DEFAULT ''` — `healthy | degraded |
  unreachable`; derived from probe history, not set manually.

New tables:

- `arclink_fleet_enrollments`
  - `enrollment_id TEXT PRIMARY KEY`
  - `token_hash TEXT NOT NULL` — HMAC-SHA256 of token under control-plane secret
  - `created_by_user_id TEXT NOT NULL`
  - `created_at TEXT NOT NULL`
  - `expires_at TEXT NOT NULL`
  - `consumed_at TEXT NOT NULL DEFAULT ''`
  - `redeemed_by_inventory_id TEXT NOT NULL DEFAULT ''`
  - `status TEXT NOT NULL` — `pending | consumed | expired | revoked`
  - `audit_ref TEXT NOT NULL DEFAULT ''`

- `arclink_fleet_host_probes`
  - `probe_id TEXT PRIMARY KEY`
  - `host_id TEXT NOT NULL`
  - `probed_at TEXT NOT NULL`
  - `kind TEXT NOT NULL` — `liveness | capacity | inventory`
  - `ok INTEGER NOT NULL` — 0 or 1
  - `latency_ms INTEGER NOT NULL DEFAULT 0`
  - `payload_json TEXT NOT NULL DEFAULT ''` — redacted before write
  - `error TEXT NOT NULL DEFAULT ''`
  - Rolling cap: prune to last 500 rows per `(host_id, kind)` on each
    daemon iteration.

- `arclink_fleet_audit_chain`
  - `entry_id TEXT PRIMARY KEY`
  - `inventory_id TEXT NOT NULL`
  - `event TEXT NOT NULL` — `enrolled | verified | activated | degraded |
    drained | resumed | removed | re-attested`
  - `actor TEXT NOT NULL` — operator user_id or `system`
  - `event_at TEXT NOT NULL`
  - `prev_hash TEXT NOT NULL DEFAULT ''`
  - `entry_hash TEXT NOT NULL` — SHA-256 of canonical entry encoding
  - `metadata_json TEXT NOT NULL DEFAULT ''`

## Identity And Trust

- **Trust anchor:** operator-minted SSH keypair on the control node, already
  produced by `ensure_control_fleet_ssh_key` (deploy.sh:8636). Single key
  for both probe and deploy paths (operator-locked decision from prior
  conversation). Key rotation runbook is part of this mission.
- **Enrollment artifact:** `arclink_fleet_enrollments` row + cleartext token
  (returned once at mint, hashed at rest). Token = 256 random bits, prefixed
  with `arclink-enroll-`. TTL ≤ 30 min, configurable. HMAC-bound to the
  control plane's internal signing key.
- **Worker identity:** at first successful enrollment callback, the worker
  is bound to `machine_fingerprint` derived from `/etc/machine-id` (or a
  generated UUID persisted to `/var/lib/arclink/host-fingerprint`). The
  fingerprint is immutable for the inventory row's lifetime. Re-enrollment
  with the same fingerprint requires explicit operator confirmation
  (`--re-attest` flag).
- **Authorized actions per identity:** the deploy SSH key is broad
  (docker compose + rsync). The probe wrapper script on the worker is a
  fixed allowlist of three verbs. Future evolution to a narrower probe key
  is captured in the deferred list, not blocked.
- **Audit chain:** every host state transition writes an
  `arclink_fleet_audit_chain` entry referencing the previous hash. Operator
  can re-verify chain integrity at any time. Chain root is the host's first
  enrollment event.

## Periodic Probing And Health

- **New compose service:** `arclink-fleet-inventory` — runs
  `python/arclink_fleet_inventory_worker.py` via `bin/docker-job-loop.sh`.
  Three independent cadences:
  - Liveness probe: 60s per host. `ssh -o BatchMode=yes host true`; on
    success update `last_seen_at` and reset failure counter.
  - Capacity probe: 5min per host. Invokes
    `arclink-fleet-probe-wrapper capacity`. Updates `observed_load`,
    `asu_consumed`, current docker container count.
  - Inventory probe: 15min per host. Invokes
    `arclink-fleet-probe-wrapper inventory`. Refreshes cpu/mem/disk/gpu/
    docker fields.
- **State derivation (no manual flag):** 3 consecutive liveness failures
  → `degraded`. 10 consecutive → `unreachable` and an operator notification
  via `notification_outbox`. First success after `degraded` → `active`.
- **Probe wrapper on worker:** `/usr/local/bin/arclink-fleet-probe-wrapper`,
  installed by `bin/arclink-fleet-join.sh`. Reads `$SSH_ORIGINAL_COMMAND`,
  rejects anything outside the three verbs, emits JSON.
- **Probe SLIs:** rolling 24h probe success rate per host and per fleet;
  operator dashboard tile reads from `arclink_fleet_host_probes`.
- **Pruning:** daemon prunes `arclink_fleet_host_probes` to last 500 rows
  per `(host_id, kind)` on each cycle. Retention is operator-configurable
  via env (`ARCLINK_FLEET_PROBE_RETENTION`).

## Action-Worker Placement Routing (Load-Bearing Fix)

The single most important code change in this mission.

- Factor `_executor_for_host(host_row, env, secret_resolver)` out of
  `python/arclink_sovereign_worker.py:997-1046` into
  `python/arclink_executor.py` as a public helper.
- In `python/arclink_action_worker.py:858-910`, for any action carrying a
  `deployment_id`:
  1. Read the active placement via `arclink_fleet.get_deployment_placement`.
  2. If a placement exists, look up the fleet host row, then call the
     factored `_executor_for_host` helper to build a per-host executor.
  3. Cache executors keyed by `(host_id, adapter)` to avoid rebuilding the
     SSH runner per action.
  4. If no placement (legacy single-host installs), fall back to the
     existing `ARCLINK_ACTION_WORKER_SSH_HOST` env path. Backwards-compatible.
- Emit an `arclink_audit_log` entry per action with the resolved
  `host_id` and `adapter` so operator can reconstruct which host ran which
  action.
- Regression test: register two fake hosts, place a deployment on host-B,
  queue a `restart` intent, assert the SSH coordinates used were host-B's.

## CLI Surface: `deploy.sh` Is Canonical

No new CLI binary. Every operator action goes through `bin/deploy.sh`,
which is already installed on every Sovereign Control Node. Existing
subcommands keep their argv shape. New subcommands extend the existing
dispatch table at `bin/deploy.sh:10454`.

### Existing surfaces — harden, do not rewrite

- `deploy.sh control fleet-key` — already works. Add `--rotate` flag for
  scheduled key rotation (generates a new keypair, preserves the old as
  `arclink-fleet.ed25519.bak.<timestamp>` until the operator confirms all
  workers have the new key, then archives the old).
- `deploy.sh control register-worker` — keep the interactive flow as the
  default. Add a fully non-interactive form:
  `deploy.sh control register-worker --hostname X --ssh-host Y --ssh-user Z
  [--region R] [--capacity-slots N] [--tags-json '{...}'] [--no-smoke-test]
  [--json]`. Both forms route through the same `register_fleet_host`
  Python boundary.
- `deploy.sh control inventory list` — already scriptable. Add `--json`
  output flag. Add `--filter state=active,region=eu-central` filtering.
- `deploy.sh control inventory probe <target>` — already SSHes for real.
  Add `--all` to force-probe every host; useful for operator validation.
- `deploy.sh control inventory drain <target>` — already works.
- `deploy.sh control inventory remove <target>` — already works.
- `deploy.sh control inventory set-strategy <headroom|standard_unit>` —
  persists env var today; this mission also wires it into
  `place_deployment` so the strategy actually selects.

### New subcommands

- `deploy.sh control enrollment mint [--ttl 30m] [--json]` — mints a new
  enrollment token bundle. Output: enrollment_id, expires_at, copy-paste
  one-liner for the worker. Token returned exactly once.
- `deploy.sh control enrollment list [--json]` — list pending and recent
  enrollments with status. Never reveals consumed tokens.
- `deploy.sh control enrollment revoke <enrollment_id>` — revoke a pending
  enrollment.
- `deploy.sh control inventory health [--json]` — fleet-wide health
  summary. Host counts by state, probe success rate, total capacity,
  consumed capacity, regions covered, audit chain integrity check.
- `deploy.sh control inventory rotate-key <target>` — rotate the
  authorized SSH key on a specific worker (operator runs after a key
  rotation event).
- `deploy.sh control inventory re-attest <target>` — force re-probing
  and re-attestation; useful after host recovery or migration.
- `deploy.sh control inventory probe-all [--json]` — operator-triggered
  immediate full probe of every host; equivalent to the daemon's
  inventory-cadence loop running now.

### CLI output contract

- Every new subcommand and every existing scriptable subcommand supports
  `--json`. JSON output is the contract for automation; prose output is
  for operator eyes.
- Exit codes: 0 success, 1 generic error, 2 invalid argv, 3 not found,
  4 conflict (e.g. remove with active placements), 5 unauthorized. All
  exit codes documented in `docs/arclink/fleet-cli.md`.
- Interactive prompts are TTY-gated; non-interactive forms must be
  callable from automation. `--json` implies non-interactive.

## Worker Bootstrap: `bin/arclink-fleet-join.sh`

Idempotent. Fail-closed. Single command after operator runs
`deploy.sh control enrollment mint`.

Steps:
1. Validate `ARCLINK_FLEET_TOKEN` and `ARCLINK_FLEET_CALLBACK_URL` are set.
2. Verify supported OS (Ubuntu 22.04+/Debian 12+/Rocky 9+ initially;
   expand list as proof lands). Detect via `/etc/os-release`.
3. Create `arclink` system user with restricted shell, no password.
4. **Auto-install prerequisites** (see Prerequisite Auto-Installation
   section below). The bootstrap script is responsible for ensuring
   Docker Engine, the Docker Compose plugin, rsync, jq, curl, and
   openssh-client are present. Operator may opt out via
   `--skip-prereq-install`, but the default for a one-command bootstrap
   is to install what's missing.
5. Add `arclink` to `docker` group; verify `docker info` succeeds.
6. Create `/arcdata` (or `$ARCLINK_STATE_ROOT`), owned by `arclink`,
   mode 0750.
7. Install probe wrapper at `/usr/local/bin/arclink-fleet-probe-wrapper`
   (mode 0755, root-owned).
8. Capture machine fingerprint (`/etc/machine-id` or generated UUID
   persisted to `/var/lib/arclink/host-fingerprint`, mode 0644).
9. Append the control-plane SSH public key to
   `~arclink/.ssh/authorized_keys` (mode 0600, `arclink`-owned).
10. POST to callback URL with bearer token. Payload:
    `{token, machine_fingerprint, hostname, outbound_ip, ssh_port,
    os_version, installed_prereqs}`. On 200, the callback returns the
    assigned `inventory_id` for the operator's records.
11. Emit structured JSON status to stdout including which prereqs were
    auto-installed vs already-present.

Failure handling: every step that errors backs out the partial state
(no SSH key in authorized_keys if the callback fails, no probe wrapper
installed if Docker is missing). The machine is in a known state at all
times.

`shellcheck` clean. `bash -n` clean.

## Prerequisite Auto-Installation

ArcLink must be installable end-to-end via a single command. The operator
should be able to point at a clean Ubuntu/Debian/Rocky machine and run one
script, and the system installs everything it needs — Docker, Compose,
shell utilities, Python deps — without manual intervention. This applies
to both the **control node install** (`deploy.sh control install` and the
existing `bin/install-arclink.sh` wrapper) and the **worker bootstrap**
(`bin/arclink-fleet-join.sh`).

### Scope

Required prerequisites for any ArcLink machine (control node or worker):

| Prereq | Detection | Install strategy |
|---|---|---|
| Docker Engine | `command -v docker && docker info` | `curl -fsSL https://get.docker.com \| sh` (idiomatic upstream, distro-agnostic). Verify post-install. |
| Docker Compose plugin | `docker compose version` | Installed by the `get.docker.com` script on supported distros; fall back to `apt-get install -y docker-compose-plugin` / `dnf install -y docker-compose-plugin` if absent. |
| `curl` | `command -v curl` | `apt-get install -y curl` / `dnf install -y curl`. |
| `jq` | `command -v jq` | `apt-get install -y jq` / `dnf install -y jq`. Used by deploy.sh in multiple places. |
| `rsync` | `command -v rsync` | `apt-get install -y rsync` / `dnf install -y rsync`. Required by `SshDockerComposeRunner` for state-root sync. |
| `openssh-client` | `command -v ssh` | `apt-get install -y openssh-client` / `dnf install -y openssh-clients`. |
| `python3` ≥ 3.10 | `python3 --version` | `apt-get install -y python3 python3-pip python3-venv`. Reject older majors with clear guidance. |
| Python packages (`PyYAML`, `jsonschema`, others used) | `python3 -c 'import ...'` | Existing pattern at `bin/deploy.sh:2473`: `pip install --upgrade --quiet ...`. |

Optional prerequisites installed on operator-opt-in:
- Tailscale (only if `ENABLE_TAILSCALE_SERVE=1` or operator chose
  Tailscale ingress). Existing flag: `ARCLINK_INSTALL_TAILSCALE`.
- Podman (alternative to Docker; existing flag:
  `ARCLINK_INSTALL_PODMAN`).
- Quarto (existing flag: `ENABLE_QUARTO`).

Not in scope (out of band, operator handles):
- Kernel upgrades, OS upgrades.
- Firewall rules beyond opening ports the operator explicitly chose.
- Cloud-provider host setup (handled by Phase 6 provisioning).

### Behaviour

- **Idempotent.** Every install step first detects whether the prereq is
  present and at the required version. Re-running the installer on a
  ready machine is a no-op.
- **OS detection.** Read `/etc/os-release` once at start; dispatch to the
  appropriate package manager (`apt-get` for Debian/Ubuntu, `dnf` for
  Rocky/RHEL/Fedora). Unsupported OS exits with a clear message and the
  list of OSes that are supported.
- **Privilege handling.** The bootstrap is intended to be run as root (or
  with `sudo`). If run as a non-root user and `sudo` is unavailable, exit
  with operator guidance. Never call `sudo` from within the script with
  hard-coded passwords; rely on existing operator privilege.
- **Pinned Docker.** Use the upstream `https://get.docker.com` installer.
  This is the same idiom recommended by Docker themselves and used by
  Kubernetes, HashiCorp, and most enterprise installers. Capture the
  installed version in `arclink_audit_log` for the control node and in
  the inventory row for workers.
- **Network availability.** Detect lack of network early (cannot reach
  `https://get.docker.com`); fail fast with operator guidance rather
  than producing a partial install.
- **Operator opt-out.** Both installers accept `--skip-prereq-install`
  (or env `ARCLINK_SKIP_PREREQ_INSTALL=1`). In that mode the installer
  *verifies* prereqs are present and exits with structured guidance if
  not, preserving the pre-mission behavior.
- **Audit.** Every auto-install action writes an audit-log entry with
  the package name and resolved version. On worker bootstrap, the
  enrollment callback payload includes `installed_prereqs[]` for control
  plane records.
- **Reproducibility.** A successful install run on the same machine
  produces the same final state. Distro/package versions captured in
  audit log enable post-hoc reconstruction.

### Code-organisation

This work touches two surfaces:

1. **Control node install** — extend `bin/deploy.sh` (specifically the
   region around line 8955 where the installer currently tells operators
   "install Docker yourself"). Add an `ensure_prereqs` helper that runs
   the table above. Wire it into `run_control_install_flow` and
   `run_docker_install_flow`. Default to auto-install; preserve the
   advisory text behind `--skip-prereq-install`.
2. **Worker bootstrap** — `bin/arclink-fleet-join.sh` (new in Phase 3)
   calls the same `ensure_prereqs` helper, either by sourcing a shared
   `bin/lib/ensure-prereqs.sh` library or by inlining the logic to keep
   the bootstrap script self-contained for cloud-init usage.

The shared library approach is preferred because Phase 6 cloud-provider
provisioning will also need to run this on freshly created machines.

### Validation

- `shellcheck` clean on the prereq helper and any new scripts.
- `bash -n` clean.
- Unit test: a `tests/test_deploy_prereqs.py` or shell-test harness that
  exercises the detection branches with `PATH` manipulation (no real
  network calls, no real installs).
- Operator runbook entry in `docs/arclink/fleet-operator-runbook.md`
  covering: how to bootstrap a fresh machine, how to opt out, how to
  verify prereqs after an install, how to view the install audit log.

### Why this is enterprise grade

- **One-command bootstrap** is the table-stakes UX for any enterprise
  platform. Kubernetes (`kubeadm`), HashiCorp Vault, Nomad, Consul, and
  every major cloud-init pattern install their prereqs without manual
  operator intervention.
- **Audit-logged**: every install action is reconstructable post-hoc.
- **Idempotent + reproducible**: re-runs are safe; final state is
  deterministic.
- **Opt-out preserved**: operators who run inside hardened images
  (golden AMIs, etc.) where prereqs are pre-installed get a
  verify-only path.

## Cloud Provider Provisioning

Two providers in scope: Hetzner Cloud and Linode. Out-of-scope for v1: AWS,
GCP, Azure (deferred until operator demand). DigitalOcean is on the
roadmap, not v1.

For each provider:

- **Provisioning workflow:**
  1. Operator runs
     `deploy.sh control inventory add hetzner --location nbg1 --type cpx21
     --tags-json '{...}'`.
  2. CLI calls the provider API with an idempotency key; provider creates
     a machine and returns its IP.
  3. CLI waits for the machine to be reachable on port 22.
  4. CLI runs `bin/arclink-fleet-join.sh` remotely via SSH using a
     one-time provisioning credential (provider-injected `cloud-init`
     bootstrap, never persisted).
  5. The join script consumes a freshly-minted enrollment token from the
     control plane, registers the inventory row, and admits the host.
- **Idempotency:** the provider API call uses a stable idempotency key
  derived from `(operator_id, hostname, cloud_provider_resource_tag)`.
  Re-running the same command finds the existing resource and resumes
  where it left off.
- **Billing attribution:** `provider_billing_ref` is captured at
  provisioning and surfaced in `inventory list` and `inventory health`.
- **Teardown:** `deploy.sh control inventory remove <target>` always
  drains first, then removes the inventory row and the linked fleet host
  row, then calls the provider API to release the machine. Confirmation
  prompt unless `--force`.

Existing `arclink_inventory_hetzner.py` and `arclink_inventory_linode.py`
client code is the foundation; this mission adds the missing create /
bootstrap / orchestrate paths.

## Observability And Operator Surface

- **Audit log:** every `arclink_fleet_audit_chain` entry is also written
  to `arclink_audit_log` for cross-feature queryability. Retention follows
  the existing audit log policy.
- **Operator dashboard:** new "Fleet" tab in the operator section of the
  hosted dashboard. Reads from a new `fleet_summary_payload` helper in
  `python/arclink_dashboard.py`. Shows: host count by state, recent
  enrollments, probe success rate, capacity utilization, audit-chain
  integrity. Operator-only; never tenant-visible.
- **Notifications:** `notification_outbox` rows for:
  - Host transitions to `degraded` after threshold.
  - Host transitions to `unreachable`.
  - Enrollment token TTL expiry without consumption (cleanup signal).
  - Audit-chain integrity failure (P0).
  - Capacity utilization crossing operator-configured thresholds.
- **Metrics:** structured-log lines suitable for ingestion by an external
  metrics pipeline. No new metrics backend is introduced; the log shape
  is the contract.
- **Runbook:** `docs/arclink/fleet-operator-runbook.md` covers: mint
  enrollment, register worker, probe failure investigation, drain/remove,
  key rotation, audit-chain re-verification, disaster recovery (control
  plane restore).

## Disaster Recovery

- **Control plane DB restored from backup:** workers do not need
  re-enrollment if their entry was in the backup. The control plane
  resumes probing on its next cycle.
- **Control plane DB lost entirely:** documented playbook in the
  operator runbook. Steps: re-mint a control SSH key, generate new
  enrollment tokens for each worker, run the bootstrap script on each
  worker pointing at the new control plane URL. Fingerprint mismatch
  surfaces as `re-attest required`; operator confirms via
  `inventory re-attest`.
- **Worker network partition:** liveness probes fail, host transitions
  to `degraded` then `unreachable`. Active pods continue on the worker
  (it has docker compose running locally). Placement filter routes new
  pods to other hosts. When the partition heals, the next successful
  probe restores `active`.
- **Worker hardware loss:** active pods are lost; the operator either
  triggers pod migration to surviving hosts (existing
  `python/arclink_pod_migration.py` machinery) or marks affected
  deployments for re-provisioning.

## Internationalization And Multi-Region

- All timestamps stored as UTC ISO-8601. Rendering uses the operator's
  timezone from `ARCLINK_ORG_TIMEZONE`.
- `region` and `region_tier` are first-class. Placement prefers same-region,
  same-tier hosts; falls back to `secondary`, then `dr`, then any healthy
  host. Placement filter never crosses `dr` tier unless explicitly
  allowed via env (`ARCLINK_FLEET_DR_PLACEMENT_ALLOWED=1`).
- Quiet-hours awareness is the Captain's concern; fleet probes never
  pause for quiet hours.
- Operator-facing prose is English-first. Vocabulary canon applies on
  Captain-facing surfaces only; operator surfaces stay technical.

## Phase Strategy

Eight phases. Phases 0-1 are prerequisites for everything else; phases
2-6 can interleave; phase 7 is operator-gated.

0. **Schema additions and reconcilers.** Land the new columns and tables.
   Add a startup reconciler that detects orphan rows and surfaces them as
   `arclink_audit_log` warnings. No behavior change yet.
1. **Action-worker placement routing.** Factor `_executor_for_host`,
   teach the action worker to read placements, add the regression test.
   This is the load-bearing change.
2. **Enrollment mint, callback API, audit chain.** Implement
   `mint_enrollment`, the callback route, the chain entries.
3. **Worker bootstrap script and probe wrapper.** Land
   `bin/arclink-fleet-join.sh` and the probe wrapper. Shellcheck clean.
4. **Inventory worker daemon.** New compose service, three probe
   cadences, state-derivation rules, pruning.
5. **`deploy.sh` surface hardening and new subcommands.** Non-interactive
   register-worker, `--json` outputs everywhere, `enrollment` subgroup,
   `inventory health` / `rotate-key` / `re-attest` / `probe-all`.
6. **Cloud-provider provisioning paths.** Hetzner and Linode end-to-end.
   Region-tier placement preference. Notification integration.
7. **Live two-host proof.** Operator-authorized. Recorded as evidence.
   Updates `mission_status.md` honestly.

Within each phase, the loop is: confirm current behavior in code and
tests, enumerate possibility set when ambiguous, add focused regression
coverage, implement, run the validation floor, update docs.

## Selected Implementation Path

| Decision | Selected path | Rejected alternatives |
| --- | --- | --- |
| CLI surface | Extend `bin/deploy.sh control ...` dispatch | New `arclink-ctl` binary (rejected: duplicates installed surface, confuses runbooks). |
| Two registry tables | Formalize separation: `arclink_inventory_machines` = machine identity; `arclink_fleet_hosts` = placement target; enforce 1:1 link | Collapse into one table (rejected: would force a migration on every existing install). |
| Trust anchor | One operator-minted SSH key, audit log for accountability | Two-key model with narrower probe restriction (deferred: operator chose simplicity; revisit if threat model changes). |
| Enrollment token | HMAC-bound, 256-bit, single-use, TTL ≤ 30 min | Long-lived bearer (rejected: blast radius), client TLS certs (deferred: cert mgmt complexity not yet warranted). |
| Probing direction | Pull from control plane via SSH | Push from worker via agent (rejected: agent install cost, breaks the zero-worker-footprint posture). |
| Placement strategy | Region-tier + headroom-aware, falls back through tiers | Random + retry (rejected: degrades worldwide UX), fixed-host (rejected: defeats fleet purpose). |
| Action-worker routing | Per-action placement lookup with per-host executor cache | Static env host (current behavior, rejected: incoherent past one host), worker-side router (rejected: requires worker agent). |
| Audit chain | Per-inventory append-only hash chain | Generic audit log only (rejected: insufficient for compliance integrity checks), external blockchain (rejected: gross overkill). |
| Cloud provisioning | Idempotency-keyed provider API + cloud-init bootstrap | Operator-only manual provisioning (deferred to v1 for non-Hetzner/Linode), agent-pulls-image (rejected: chicken-and-egg with enrollment). |
| Cadence model | Liveness 60s, capacity 5min, inventory 15min | Single 60s probe (rejected: noisy on heavy inventory), worker pushes (rejected, see above). |
| Backwards compatibility | Legacy single-host install continues to work with no operator action | Force migration to fleet model (rejected: blast radius on existing single-tenant installs). |

## Validation Criteria

The mission is `done` only when every item below is satisfied or
explicitly deferred with operator-facing rationale.

### Phase 0 — schema and reconciler
- New columns and tables exist; idempotent migration runs twice clean.
- Reconciler detects orphans on either side and emits audit-log warnings.
- Existing `register_fleet_host` and `place_deployment` callers all pass
  their existing test suites.

### Phase 1 — action worker
- `_executor_for_host` factored into `python/arclink_executor.py` as a
  documented public helper.
- Action worker reads placement for any deployment-scoped action and
  builds a per-host executor.
- Per-action audit log entries include resolved `host_id` and `adapter`.
- Regression test passes: two fake hosts, place on host-B, restart routes
  to host-B's SSH coordinates.
- Legacy path (no placement, static env host) still passes existing tests.

### Phase 2 — enrollment
- `mint_enrollment` produces a valid bundle; token verifiable; HMAC bound.
- Callback route consumes the token, rejects expired and re-used tokens,
  writes the inventory row in `enrolling` state with the
  machine_fingerprint.
- Audit chain root entry written; subsequent transitions extend the chain.
- Chain integrity check is callable via `inventory health` and surfaces
  any tampering.

### Phase 3 — bootstrap
- `bin/arclink-fleet-join.sh` shellcheck clean, `bash -n` clean,
  idempotent.
- Probe wrapper rejects unknown verbs; the three known verbs emit
  parseable JSON.
- Failure paths leave the machine in a non-admitting state.

### Phase 4 — inventory daemon
- New compose service runs cleanly; three cadences operate independently.
- State derivation: 3 failures → `degraded`, 10 → `unreachable`, recovery
  back to `active` on success.
- Probe history pruned to operator-configured retention.
- Probe SLI calculable per host and per fleet from the probe table.

### Phase 5 — CLI surface
- Every existing scriptable subcommand has a `--json` mode.
- `register-worker` has a fully non-interactive form.
- New subcommands present and tested:
  `enrollment mint|list|revoke`,
  `inventory health|rotate-key|re-attest|probe-all`.
- Exit codes documented in `docs/arclink/fleet-cli.md`.

### Phase 6 — cloud provisioning
- Hetzner and Linode provisioning workflows create machines, bootstrap
  them via cloud-init + join script, register inventory rows.
- Idempotency keys prevent duplicate machine creation on re-run.
- Teardown drains, removes, then releases the cloud resource.
- Region-tier placement preference is honored in `place_deployment`.

### Phase 7 — live proof
- Two-host live proof runbook written in `research/`.
- Operator authorizes the run, results captured as evidence with
  timestamps and host IDs.
- `mission_status.md` and `research/BUILD_COMPLETION_NOTES.md` updated
  honestly.

## Validation Floor

Per-phase focused validation:

```bash
python3 -m py_compile python/arclink_fleet.py python/arclink_inventory.py \
  python/arclink_executor.py python/arclink_action_worker.py \
  python/arclink_sovereign_worker.py \
  python/arclink_fleet_inventory_worker.py python/arclink_control.py \
  python/arclink_api_auth.py python/arclink_hosted_api.py \
  python/arclink_dashboard.py
python3 tests/test_arclink_fleet.py
python3 tests/test_arclink_inventory.py
python3 tests/test_arclink_action_worker.py
python3 tests/test_arclink_executor.py
python3 tests/test_arclink_sovereign_worker.py
python3 tests/test_arclink_hosted_api.py
python3 tests/test_arclink_api_auth.py
python3 tests/test_arclink_dashboard.py
python3 tests/test_arclink_schema.py
```

Broad validation before `done`:

```bash
bash -n deploy.sh bin/*.sh test.sh
shellcheck bin/arclink-fleet-join.sh bin/arclink-fleet-probe-wrapper \
  bin/deploy.sh
cd web
npm test
npm run lint
npm run build
npm run test:browser
```

Compile every touched Python module before completion. Live
host-mutating, payment, public-bot mutation, real-cloud-provider,
remote-SSH-against-non-loopback, and remote deploy/upgrade proof remain
explicitly operator-gated.

## Explicitly Deferred

- Worker-pushed heartbeats (architectural decision: pull-only for v1).
- Auto-migration on host degradation (placement bookkeeping exists;
  auto-trigger is a follow-on mission).
- GPU-aware placement constraints (inventory surfaces GPU; placement
  doesn't yet schedule on GPU type/count).
- DigitalOcean, AWS, GCP, Azure cloud-provider provisioning.
- Two-key separation (probe key + deploy key with narrower restriction)
  — operator-locked simplicity choice; revisit on threat model change.
- Dashboard fleet UI for Captains (operator-only for v1).
- Self-service worker enrollment for non-operator Captains (operator-only).
- Hardware attestation via TPM / Secure Boot signatures (future:
  cryptographic machine identity beyond fingerprint).
- Multi-tenant fleet isolation across operators (single-operator fleet
  per Sovereign Control Node for v1).

## Required Posture

- Treat current source as ground truth where docs disagree; update docs
  after behavior is true.
- Prefer focused regression tests before code changes when behavior is
  risky.
- Do not touch Hermes core, `arclink-priv`, or any private state.
- Do not run live production deploys, upgrades, payment flows, public bot
  mutations, real cloud-provider provisioning, or remote-SSH-against-non-
  loopback proof unless the operator authorizes that specific step.
- Apply the vocabulary canon (`docs/arclink/vocabulary.md`): operator
  surfaces stay technical; Captain-facing surfaces use the canon.
- Reuse existing rails: `notification_outbox`, `docker-job-loop.sh`,
  `arclink_evidence.redact_value`, `arclink_audit_log`,
  `arclink_dashboard` snapshots, the hosted API auth rails,
  `arclink_public_bots` command dispatch.
- Fleet operations are operator-only. Captain visibility into the fleet
  is limited to "Your Pod is healthy on a Sovereign worker" — no host
  IDs, no fleet topology, no operator metadata leakage.

## Done Means

- A new operator can mint an enrollment token via
  `deploy.sh control enrollment mint`, run the bootstrap script on a
  clean Ubuntu/Debian/Rocky machine, and watch the inventory worker
  transition the machine to `active` within one probe cycle — with the
  audit chain root entry written and the SSH key, fingerprint, and
  attestation timestamp captured.
- `deploy.sh control inventory health --json` returns a structured fleet
  summary suitable for automation; every other scriptable subcommand
  supports `--json`.
- Day-2 admin actions (restart, teardown, rollout, pause/resume, pod
  migration) route to the deployment's actual placement host, evidenced
  by audit-log entries per action.
- Hetzner and Linode provisioning workflows create machines, bootstrap
  them, register inventory rows, and tear them down idempotently.
- Region-tier placement is honored; degraded hosts are excluded from
  new placements; unreachable hosts emit operator notifications.
- Audit chain integrity is checkable via `inventory health`; tampering
  surfaces as a P0 notification.
- Operator runbook (`docs/arclink/fleet-operator-runbook.md`) documents
  every operator action including disaster recovery.
- Live two-host proof recorded in `research/` with real timestamps and
  host IDs.
- `mission_status.md` updated honestly — no claim of fleet readiness
  without the live proof.
- All focused and broad validation passes; no new live-credential
  dependency in CI.

## References

- `python/arclink_fleet.py` — placement, registration, drain, capacity.
- `python/arclink_inventory.py` — inventory CRUD, probe.
- `python/arclink_executor.py` — `SubprocessDockerComposeRunner`,
  `SshDockerComposeRunner`, secret resolvers.
- `python/arclink_sovereign_worker.py` — provisioning daemon,
  `_executor_for_host` (to be factored).
- `python/arclink_action_worker.py` — action daemon, the static-host gap.
- `python/arclink_control.py` — schema for both registries and
  audit log.
- `bin/deploy.sh` — operator CLI, existing `control fleet-key`,
  `register-worker`, `inventory ...` subcommands.
- `tests/test_arclink_fleet.py`, `tests/test_arclink_inventory.py`,
  `tests/test_arclink_inventory_hetzner.py`,
  `tests/test_arclink_inventory_linode.py`.
- `docs/arclink/vocabulary.md` — operator vs Captain vocabulary split.
- `research/RALPHIE_ARCLINK_ECOSYSTEM_GAP_REPAIR_STEERING.md` —
  ecosystem context, vocabulary, prior decisions.
- `research/RALPHIE_ARCPOD_CAPTAIN_CONSOLE_STEERING.md` — prior mission
  closeout; introduced `arclink_inventory_machines` and inventory CLI.
