# ArcLink Sovereign Fleet CLI

`./deploy.sh control ...` is the canonical Operator surface for Sovereign
fleet work. Scriptable subcommands support `--json`; JSON output is intended
to parse as a single object on stdout.

## Exit Codes

- `0`: command completed.
- `1`: runtime failure, validation failure, unavailable prerequisite, or
  provider/client failure.
- `2`: invalid command or invalid arguments.

Live SSH, cloud, and destructive provider operations remain proof-gated by the
Operator (live remote-fleet apply: PG-FLEET / PG-PROVISION; live Cloudflare DNS:
PG-INGRESS; cloud provider create/destroy: GAP-021, parity-only no-secret
tests). Use `--no-smoke-test` on registration when recording inventory without
live SSH proof.

## Fleet Key

```bash
./deploy.sh control fleet-key
./deploy.sh control fleet-key --json
./deploy.sh control fleet-key --rotate --json
```

`--rotate` creates a new control fleet SSH keypair and leaves the previous
keypair beside it with a timestamped `rotated-...` suffix. The JSON response
contains the public key and configured key path; it never prints private key
material.

`fleet-key --rotate` (and `inventory rotate-key` below) are SSH-key operations
owned by `deploy.sh`, not subcommands of the Python `arclink_inventory.py` /
`arclink_fleet*.py` CLIs — those Python CLIs have no rotate-key verb. Both write
the new keypair to the durable runtime config; live SSH executor work against
fleet workers stays proof-gated (PG-FLEET / PG-PROVISION) until the new public
key is reinstalled on each worker.

## Enrollment

```bash
./deploy.sh control enrollment mint --ttl-seconds 3600 --json
./deploy.sh control enrollment list --all --json
./deploy.sh control enrollment revoke <enrollment-id> --json
./deploy.sh control enrollment rotate-secret --json
./deploy.sh control enrollment verify-audit-chain --json
```

Mint is the only command that returns cleartext enrollment token material, and
only in that one response.

## Worker Registration

Interactive:

```bash
./deploy.sh control register-worker
```

Scriptable:

```bash
./deploy.sh control register-worker \
  --hostname worker-1.example.test \
  --ssh-host 203.0.113.10 \
  --ssh-user arclink \
  --region iad \
  --capacity-slots 4 \
  --tags-json '{"tier":"standard"}' \
  --no-smoke-test \
  --json
```

Scriptable registration updates the SSH executor allowlist and records the
fleet host. With `--json`, the command does not restart control services; the
response includes `restart_required: true`. JSON mode skips the live SSH smoke
test by default so stdout remains parseable; add `--smoke-test` when that live
proof is explicitly authorized.

## Inventory

```bash
./deploy.sh control inventory list --json
./deploy.sh control inventory list --all --filter status=ready --filter region=iad --json
./deploy.sh control inventory probe <machine-id|hostname> --json
./deploy.sh control inventory probe-all --json
./deploy.sh control inventory add hetzner --json
./deploy.sh control inventory add linode --json
./deploy.sh control inventory add hetzner --hostname worker-fsn1 --server-type cx22 --image ubuntu-24.04 --region fsn1 --ssh-key <key-name-or-id> --idempotency-key worker-fsn1-create --json
./deploy.sh control inventory add linode --hostname worker-use1 --server-type g6-standard-2 --image linode/ubuntu24.04 --region us-east --ssh-key <public-key> --idempotency-key worker-use1-create --json
./deploy.sh control inventory drain <machine-id|hostname> --json
./deploy.sh control inventory remove <machine-id|hostname> --json
./deploy.sh control inventory remove <machine-id|hostname> --destroy --idempotency-key worker-remove-1 --json
./deploy.sh control inventory rotate-key --json
./deploy.sh control inventory re-attest <machine-id|hostname> --machine-fingerprint <fingerprint> --json
./deploy.sh control inventory health --notify --json
./deploy.sh control inventory set-strategy <headroom|standard_unit> --json
```

Supported list filters are `machine_id`, `provider`, `hostname`, `ssh_host`,
`ssh_user`, `region`, `status`, `machine_host_link`, and `host_id`.

`inventory add hetzner` and `inventory add linode` list provider servers when
no hostname is supplied. With `--hostname`, they create a provider machine and
register a pending inventory row idempotently. Provider tokens are read from
the provider environment (`HETZNER_API_TOKEN` or `LINODE_API_TOKEN`) and are
never printed. Destructive provider removal requires the inventory machine to
be drained first plus an explicit `--destroy`; use `--force` only for an
Operator-approved recovery case after confirming no active placements remain.

## Placement Strategy

`inventory set-strategy <headroom|standard_unit>` sets the
`ARCLINK_FLEET_PLACEMENT_STRATEGY` runtime-config env var via `deploy.sh` and
rewrites the durable Docker runtime config. It does **not** write control-DB
state — there is no persisted strategy column. Placement reads the value live
from `ARCLINK_FLEET_PLACEMENT_STRATEGY` on every placement decision
(`arclink_fleet.place_deployment`), so the change takes effect on the next
deployment placed, not retroactively. `headroom` (the default) picks the host
with the most free capacity slots; `standard_unit` picks the host with the most
available ASU.

Note the boundary: the bare Python CLI form
(`python3 python/arclink_inventory.py set-strategy ...`) only **prints** the
chosen strategy — it neither writes the runtime config nor mutates control-DB
state. Use the `deploy.sh control inventory set-strategy` wrapper above to make
the change durable.
