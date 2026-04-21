---
name: almanac-first-contact
description: Use after Almanac enrolls a user agent to verify the default MCPs, install the default Almanac skills, resolve default vault subscriptions, materialize the managed-memory stubs, and complete first-contact orientation.
---

# Almanac First Contact

Use this skill immediately after a user agent is enrolled.

On a normal shared-host enrollment, `activate-agent.sh` runs this automatically on first flight after registration succeeds.

## Execution

Run the executable first-contact script to perform verification and resolution:

```bash
scripts/run-first-contact.sh
```

The script expects these environment variables (all normally exported by `init.sh agent` or `activate-agent.sh`):

- `ALMANAC_MCP_URL` — control-plane MCP URL, e.g. `http://127.0.0.1:8282/mcp`
- `ALMANAC_QMD_URL` — retrieval-plane MCP URL
- `ALMANAC_BOOTSTRAP_TOKEN_FILE` — path to the agent's raw bootstrap token
- `ALMANAC_SHARED_REPO_DIR` — absolute path to the shared repo root

Its output is a JSON summary on stdout. A non-zero exit code means first-contact failed a hard check; the operator should inspect before proceeding.

On a shared host, `ALMANAC_SHARED_REPO_DIR` may live under `/home/almanac/almanac`. Treat that as the shared deployment root, not as another enrolled user's workspace.

## Goals

- confirm the agent is using the shared-host Almanac deployment
- verify the default MCP set is registered:
  - `almanac-mcp`
  - `almanac-qmd`
  - `chutes-kb` when configured
- resolve the active `.vault` catalog and surface subscribed vs default state
- run one initial vault refresh via `vaults.refresh`
- load the canonical managed-memory payload from Curator's published snapshot when available, falling back to `agents.managed-memory` only when needed
- materialize the agent-local managed-memory stubs immediately in the agent's own `HERMES_HOME`
- note the home channel in the manifest (already set at enrollment)
- emit a curator brief-fanout ping so the Curator knows to push initial briefs and follow-up managed-memory updates

## First-flight outputs

After a successful run, the enrolled user agent should have:

- `$HERMES_HOME/state/almanac-vault-reconciler.json`
- `$HERMES_HOME/memories/almanac-managed-stubs.md`
- `$HERMES_HOME/memories/MEMORY.md` with the managed Almanac routing entries

These are not optional extras. First-contact is not complete until the initial memory stubs exist.

## Guardrails

- treat qmd as the retrieval plane and `almanac-mcp` as the control plane
- use the passed environment variables plus MCP responses; do not inspect central deployment secrets such as `almanac.env`, `.almanac-operator.env`, or source `bin/common.sh` from a user-agent session
- do not browse other users' home directories; stay within the current user's `HERMES_HOME` plus the shared Almanac MCP and qmd surfaces
- do not store raw vault bodies or PDF bodies in built-in memory
- if vault subscription defaults already exist from a prior archived enrollment, keep them unless the user explicitly changes them
- if the user only has TUI enabled, skip home-channel configuration without treating it as a failure
- never write to the vault from this skill — it is read-only verification
