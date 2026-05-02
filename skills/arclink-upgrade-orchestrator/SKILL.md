---
name: arclink-upgrade-orchestrator
description: Use when Curator or the operator needs to check whether the deployed ArcLink host is behind its tracked upstream, summarize the upgrade state, and ask the operator to run `./deploy.sh upgrade`.
---

# ArcLink Upgrade Orchestrator

Use this skill when:

- Curator reports that a new ArcLink commit is available upstream
- the operator asks whether the shared host should be upgraded
- the operator wants a concise rollout checklist for upgrading ArcLink itself
- you need to confirm what commit is deployed and what upstream commit is newer

This skill is for the shared host and Curator only.

It is not for user-agent refresh work.

Enrolled user bots should not use this skill and should not inspect host-level
deployment config such as `arclink.env`.

## Authority boundary

Curator does not execute upgrades.

The Curator process runs as the operator service user (non-root) and has no
`sudo` rights. It can:

- detect that upstream is ahead of the deployed commit
- queue exactly one operator notification per new upstream SHA
- summarize the upgrade state and ask the operator to run the upgrade
- verify the post-upgrade health state once the operator confirms

It cannot:

- run `./deploy.sh upgrade` on its own
- modify systemd units, files under `/etc`, or files outside the ArcLink
  service-user tree

The privileged upgrade apply path is `./deploy.sh upgrade`, which
self-reexecutes under `sudo` via `--apply-upgrade`. Only an operator with
sudo on the host can run it.

## First checks

Inspect these first:

- `bin/arclink-ctl upgrade check`
- `bin/deploy.sh`
- `bin/health.sh`
- `arclink-priv/config/arclink.env`
- `arclink-priv/state/arclink-release.json` when present

The deployed upgrade source is the tracked upstream in `arclink.env`, not the
checkout you happen to be standing in.

## Preferred workflow

1. Run `./bin/arclink-ctl upgrade check`.
2. Summarize:
   - deployed commit
   - tracked upstream repo and branch
   - upstream head commit
   - whether an upgrade is actually available
3. Ask the operator to run `./deploy.sh upgrade` on the host when they are
   ready. Do not claim you will run it yourself.
4. After the operator confirms the upgrade finished, run `./deploy.sh health`
   to verify.
5. Report only the outcome that matters: upgraded or not, current commit, and
   any remaining warnings or failures.

## Operator-facing commands

Manual check:

```bash
./bin/arclink-ctl upgrade check
```

Host upgrade (operator-only, requires sudo on the host):

```bash
./deploy.sh upgrade
```

Post-upgrade verification:

```bash
./deploy.sh health
```

## Guardrails

- Do not claim Curator ran or will run the upgrade. Curator nags; the operator
  executes.
- Do not route enrolled user bots into this workflow. It is operator-only.
- Do not use a local developer checkout (for example `~/arclink` on a laptop)
  as the upgrade source for production.
- Prefer the configured `ARCLINK_UPSTREAM_REPO_URL` and `ARCLINK_UPSTREAM_BRANCH`.
- If you are talking to the operator through Telegram, Discord, or another remote
  channel, ask them to run `./deploy.sh upgrade` on the host. Do not assume a
  host-side TUI session is available to you.
- Always ask the operator to follow up with `./deploy.sh health` after an
  upgrade, and surface any remaining failures.
- If `upgrade check` says the deployed release state is missing, say that
  plainly and treat `./deploy.sh upgrade` as the repair path the operator
  should run.

## Expected output shape

Keep it short.

Good:

- `ArcLink is behind upstream: 1234abcd5678 -> 9abc0123def4 on example/arclink main. Please run ./deploy.sh upgrade on the host when ready.`
- `ArcLink upgrade confirmed. Health is clean; current release is 9abc0123def4.`

Avoid long changelog dumps unless the operator asks for them.
