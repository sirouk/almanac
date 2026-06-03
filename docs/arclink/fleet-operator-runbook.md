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

1. Fetch the control fleet public key for first-contact SSH access:

   ```bash
   ./deploy.sh control fleet-key --json
   ```

   Append the returned public key to the exact first-contact account ArcLink
   should use on the fresh worker, normally `root` or an account with
   passwordless `sudo -n`. Do not replace `authorized_keys`; ArcLink does not
   change `sshd_config`, does not change port 22, and does not delete existing
   SSH keys.

2. Run push-button registration from the Control Node:

   Interactive:

   ```bash
   ./deploy.sh control register-worker
   ```

   The normal interactive flow asks for the inventory hostname and the
   first-contact SSH host only. ArcLink derives the WireGuard endpoint from the
   control node, publishes a WireGuard-bound private control ingress, generates
   the private control URL from the control tunnel IP, assigns the worker tunnel
   IP, configures the worker, registers the worker's long-lived fleet address
   as the WireGuard IP, syncs the peer, and smoke-tests the private mesh. Use
   `ARCLINK_FLEET_REGISTER_ADVANCED_PROMPTS=1` only for unusual networks.

   Scriptable:

   ```bash
   ./deploy.sh control register-worker \
     --hostname worker-1 \
     --ssh-host 10.44.0.11 \
     --bootstrap-remote \
     --bootstrap-ssh-host 203.0.113.10 \
     --bootstrap-ssh-user root \
     --ssh-user arclink \
     --capacity-slots 4 \
     --json
   ```

   `register-worker --bootstrap-remote` mints the one-time enrollment token,
   stages only `bin/arclink-fleet-join.sh`, `bin/arclink-fleet-probe-wrapper`,
   `bin/lib/ensure-prereqs.sh`, and the control fleet public key over SSH, then
   runs the join remotely as root or passwordless `sudo -n`. The enrollment
   token is passed over stdin, never argv, and is revoked if the remote join
   fails. The join script owns worker-local setup for the service user,
   authorized key, state root, Docker group membership, WireGuard config,
   additive firewall allowance where `ufw`/`firewalld` is active, probe wrapper,
   machine fingerprint, and callback payload. It writes a local non-admitting
   state before callback and admits the worker only after the control callback
   succeeds.

   Prefer a production private mesh/WireGuard address for scriptable
   `--ssh-host`; use `--bootstrap-ssh-host` for the provider/public first-contact
   address. If `--wireguard-worker-ip` is omitted during remote bootstrap,
   ArcLink assigns the next tunnel IP and uses it as the worker private DNS/IP.
   The callback persists that private DNS/IP into inventory and fleet-host
   metadata, so ArcPods placed on this worker render their dashboard, Drive,
   Code, Terminal, and Notion links against the worker that actually owns the
   containers. `--tailscale-dns-name` is optional access compatibility metadata.
   The bootstrap callback uses an internally selected public or Tailscale Control
   Node URL because the Control Node cannot know the worker WireGuard public key
   before the fresh worker generates it. The Operator is not prompted for this
   value in the normal flow. After the callback, `register-worker` reads the
   callback-reported public key and syncs the peer into the Control Node config
   and live interface; remote ArcPods then render control, share-broker, and
   inference-router URLs through the generated WireGuard private control URL. If
   the worker public key is already known, pass it to
   `register-worker --wireguard-public-key` and the peer is appended before
   bootstrap too.
   Cross-machine Captain shared folders use the Control Node WireGuard SSH git
   hub by default, for example
   `ssh://arclink@10.44.0.1/arcdata/captains/{user}/fleet-shared.git`. Set
   `ARCLINK_FLEET_SHARE_HUB_URL` only to override that default with a dedicated
   remote git hub.

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
  --hostname worker-1 \
  --ssh-host 10.44.0.11 \
  --wireguard-private-ip 10.44.0.11 \
  --tailscale-dns-name worker-1.tailnet.ts.net \
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
