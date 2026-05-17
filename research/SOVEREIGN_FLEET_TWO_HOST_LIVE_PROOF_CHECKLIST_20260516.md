# Sovereign Fleet Two-Host Live Proof Checklist

Date prepared: 2026-05-16

Purpose: define the operator-gated Phase 7 proof required before ArcLink
Sovereign fleet readiness can be claimed.

## Authorization Gate

Do not run this proof until the operator explicitly authorizes the live run in
the current conversation or maintenance window and names the target hosts or
provider resources.

The authorization must include:

- Control node checkout and branch to use.
- Two target worker hosts or provider resources.
- Confirmation that non-loopback SSH, clean-host bootstrap, prerequisite
  installation, and probe traffic are allowed.
- Confirmation that provider create/delete calls are allowed if the proof uses
  Hetzner or Linode instead of existing hosts.
- Evidence destination under `research/`.

## Preflight

- Confirm the worktree does not contain private state or secrets in public
  files.
- Run focused local validation before live mutation:
  `git diff --check`,
  `bash -n deploy.sh bin/*.sh bin/lib/*.sh bin/arclink-fleet-probe-wrapper test.sh`,
  fleet/enrollment/inventory/provider tests, and audit Wave 1 tests.
- Confirm `./deploy.sh control inventory health --json` works locally or in
  the authorized control environment without leaking token, fingerprint, SSH,
  provider, or billing material.
- Confirm SSH keys and enrollment HMAC root are operator-owned and are not
  printed in logs.

## Live Steps

1. Mint two enrollment tokens with `./deploy.sh control enrollment mint`.
2. Bootstrap each target worker with `bin/arclink-fleet-join.sh`, passing
   enrollment token material through stdin or a protected token file, never
   through argv.
3. Capture prereq-install summary from each worker callback, redacted.
4. Run `./deploy.sh control inventory probe-all --json`.
5. Confirm both linked fleet hosts become `active` within one probe cycle.
6. Place or use a deployment on each host and run a safe day-2 action proof.
7. Confirm each action audit row includes the resolved `host_id` and `adapter`.
8. Run `./deploy.sh control inventory health --json` and verify audit-chain
   integrity.
9. Drain and remove any temporary proof hosts, or explicitly record why they
   remain enrolled.

## Evidence To Record

- UTC start and end timestamps.
- Control node commit SHA.
- Redacted enrollment IDs, host IDs, provider IDs, and regions.
- Redacted callback summaries, probe summaries, health JSON, and action audit
  summaries.
- Any failures, retries, cleanup actions, and residual admitted hosts.

## Completion Rule

Only after the authorized live run succeeds should `mission_status.md` claim
fleet readiness. If authorization is not granted or the proof is skipped,
status remains operator-gated.
