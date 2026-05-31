# ArcLink Sovereign Fleet Operator Runbook

This runbook covers source-level fleet operations. Live host and provider
proofs require explicit Operator authorization.

For the Docker-socket/root trusted-host services that back live host mutation
(GAP-019, risk-accepted only), see the GAP-019 entries in
`docs/arclink/operations-runbook.md` (authoritative). For the fleet operator
CLI reference, see `docs/arclink/fleet-cli.md`.

## Single-Machine Mode (docker-local-starter, no SSH)

For a single Control Node that also runs ArcPods on its own host, there is no
enrollment token and no SSH join. The control machine registers itself as a
fleet host and is admitted by a dedicated no-SSH probe path.

1. Register the local machine as a fleet host by running the Sovereign worker
   with `ARCLINK_REGISTER_LOCAL_FLEET_HOST=1`. `process_sovereign_batch`
   (in `python/arclink_sovereign_worker.py`) calls `register_fleet_host` for the
   local host and stamps host metadata with `executor` (the value of
   `ARCLINK_EXECUTOR_ADAPTER`), `ingress_mode`, `edge_target`, and
   `state_root_base`. Set `ARCLINK_LOCAL_FLEET_SSH_HOST` to `localhost`,
   `127.0.0.1`, or `::1` (the three values in `LOCAL_SSH_HOST_ALIASES`).

2. The fleet inventory worker
   (`python/arclink_fleet_inventory_worker.py`) flags the host for the
   `docker-local-starter` probe mode when all three conditions hold (computed in
   `_host_rows`, written to `_arclink_docker_local_starter_probe`):

   - `ARCLINK_DOCKER_MODE` is truthy, AND
   - the linked inventory machine metadata `executor == "local"`, AND
   - the host `ssh_host` is one of `localhost`, `127.0.0.1`, `::1`.

   When flagged, `SshProbeRunner` short-circuits to `_docker_local_starter_probe`
   and never opens SSH. That probe always returns `ok=True` with
   `admitting=True` and `probe_mode="docker-local-starter"`, so the host is
   admitted on the local machine alone. This is the local-real, single-machine
   equivalent of the remote enrollment path below.

3. Confirm admission with the same inventory commands used for remote workers:

   ```bash
   ./deploy.sh control inventory health --json
   ./deploy.sh control inventory list --filter status=ready --json
   ```

Live remote-fleet apply and worker execution remain proof-gated (PG-FLEET /
PG-PROVISION); the docker-local-starter admission path itself is local-real and
does not need that authorization.

## Enroll A Worker

This is the remote-fleet path. For a single-machine Control Node, use
[Single-Machine Mode](#single-machine-mode-docker-local-starter-no-ssh) above
instead of an enrollment token.

1. Mint a token:

   ```bash
   ./deploy.sh control enrollment mint --ttl-seconds 3600 --json
   ```

   Mint returns cleartext token material only once. Keep it out of shell
   history and logs.

2. Fetch the control fleet public key for worker SSH access:

   ```bash
   ./deploy.sh control fleet-key --json
   ```

3. On the worker, run `bin/arclink-fleet-join.sh` as root with the enrollment
   token supplied by file or stdin and the control fleet public key supplied as
   a file:

   ```bash
   bin/arclink-fleet-join.sh \
     --control-url https://control.example.test \
     --token-file /path/to/enrollment-token \
     --authorized-key-file /path/to/control-fleet-key.pub \
     --hostname worker-1.example.test \
     --ssh-host 203.0.113.10 \
     --ssh-user arclink \
     --region iad \
     --capacity-slots 4 \
     --json
   ```

   Enrollment tokens are intentionally rejected on argv. The join script owns
   worker-local setup for the service user, authorized key, state root, Docker
   group membership, probe wrapper, machine fingerprint, and callback payload.
   It writes a local non-admitting state before callback and admits the worker
   only after the control callback succeeds.

   By default the join script runs the shared prerequisite installer. Use
   `--skip-prereq-install` only for a pre-hardened worker image where
   prerequisites were installed through another approved path; the skip is
   recorded in the callback summary.

4. Confirm inventory:

   ```bash
   ./deploy.sh control inventory health --json
   ./deploy.sh control inventory list --filter status=ready --json
   ```

## Register An Existing SSH Worker

For inventory-only registration without live SSH proof:

```bash
./deploy.sh control register-worker \
  --hostname worker-1.example.test \
  --ssh-host 203.0.113.10 \
  --ssh-user arclink \
  --region iad \
  --capacity-slots 4 \
  --no-smoke-test \
  --json
```

Rerun without `--no-smoke-test` only when live SSH proof is authorized.
In `--json` mode, use `--smoke-test` to opt into that proof while keeping the
machine-readable result on stdout.

## Probe And Health

```bash
./deploy.sh control inventory probe-all --json
./deploy.sh control inventory health --notify --json
```

Health verifies audit-chain integrity, expires stale pending enrollments, and
summarizes host capacity, regions, probe SLI, and health states. Audit-chain
tampering queues a P0 Operator notification.

For explicit audit-chain proof, run:

```bash
./deploy.sh control enrollment verify-audit-chain --json
```

## Cloud Provider Inventory

List provider-visible workers without changing control state:

```bash
./deploy.sh control inventory add hetzner --json
./deploy.sh control inventory add linode --json
```

Create and register a provider worker idempotently:

```bash
./deploy.sh control inventory add hetzner \
  --hostname worker-fsn1 \
  --server-type cx22 \
  --image ubuntu-24.04 \
  --region fsn1 \
  --ssh-key <key-name-or-id> \
  --idempotency-key worker-fsn1-create \
  --json
```

The local provider path records the machine as pending and preserves provider
resource, billing, region, tag, and bootstrap metadata. Worker admission still
depends on the enrollment callback and probe cycle; live provider creation,
SSH wait, and join proof require explicit Operator authorization.

The no-secret local lifecycle harness uses fake Hetzner and Linode clients to
prove create idempotency, duplicate-host handling, probe handoff, drain guards,
destroy calls, and destroy replay. It does not prove real provider APIs, SSH
wait, worker join, or live destroy behavior.

## Drain And Remove

```bash
./deploy.sh control inventory drain <machine-id|hostname> --json
./deploy.sh control inventory remove <machine-id|hostname> --json
./deploy.sh control inventory remove <machine-id|hostname> --destroy --json
```

Removal fails while active placements still point at the linked fleet host.
Drain first, migrate placements, then remove. For Hetzner and Linode machines,
`--destroy` calls the provider delete API after the drain guard passes; use an
idempotency key for repeatable teardown evidence.

## Key Rotation And Re-Attestation

Rotate the control fleet SSH key:

```bash
./deploy.sh control fleet-key --rotate --json
./deploy.sh control inventory rotate-key --json
```

Install the new public key on workers before relying on SSH executor work.

Re-attest an inventory machine after an Operator-approved fingerprint change:

```bash
./deploy.sh control inventory re-attest <machine-id|hostname> \
  --machine-fingerprint <fingerprint> \
  --reason "approved host rebuild" \
  --json
```

## Disaster Recovery

1. Restore the control database and private config from the Operator backup.
2. Run `./deploy.sh control health`.
3. Run `./deploy.sh control inventory health --notify --json`.
4. Reinstall the current control fleet public key on workers if SSH executor
   proof fails.
5. Re-mint enrollment tokens for any worker that was not consumed before the
   restore point; old pending tokens should be revoked.
