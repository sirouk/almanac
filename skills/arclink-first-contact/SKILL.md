---
name: arclink-first-contact
description: Use after ArcLink enrolls a user agent and installs the default skills/MCP config to verify live ArcLink MCP and qmd calls, resolve default vault subscriptions, materialize plugin-managed context state, and complete first-contact orientation.
---

# ArcLink First Contact

Use this skill immediately after a user agent is enrolled.

On a normal shared-host enrollment, `activate-agent.sh` runs this automatically on first flight after registration succeeds.

## Execution

Run the executable first-contact script to perform verification and resolution:

```bash
scripts/run-first-contact.sh
```

The script expects these environment variables (all normally exported by `init.sh agent` or `activate-agent.sh`):

- `ARCLINK_MCP_URL` - control-plane MCP URL, e.g. `http://127.0.0.1:8282/mcp`
- `ARCLINK_QMD_URL` - retrieval-plane MCP URL
- `ARCLINK_BOOTSTRAP_TOKEN_FILE` - path to the agent's raw bootstrap token
- `ARCLINK_SHARED_REPO_DIR` - absolute path to the shared repo root

Its output is a JSON summary on stdout. A non-zero exit code means first-contact failed a hard check; the operator should inspect before proceeding.

On a shared host, `ARCLINK_SHARED_REPO_DIR` is the shared deployment root, not another enrolled user's workspace. Use `~/ArcLink` as the user-visible vault root.

## Goals

- confirm the agent is using the shared-host ArcLink deployment
- verify the configured ArcLink MCP URL is callable through `arclink-rpc`
- verify the configured qmd MCP URL is callable through a real raw MCP probe
- treat Hermes MCP registration as already handled by `activate-agent.sh`,
  `init.sh`, and `bin/upsert-hermes-mcps.sh`; this script validates the rails
  rather than inspecting Hermes config
- verify the retrieval rail is actually callable by running a real qmd `tools/call` probe instead of only trusting the configured URL
- when the shared Notion knowledge rail is configured on the host, verify it by running one real `notion.search` probe through `arclink-mcp`
- resolve the active `.vault` catalog and surface subscribed vs default state
- run one initial vault refresh via `vaults.refresh`
- load the canonical managed-memory payload for plugin context from Curator's published snapshot when available, falling back to `agents.managed-memory` only when needed
- materialize the agent-local plugin-managed context state immediately in the agent's own `HERMES_HOME`
- respect the home-channel state that enrollment already recorded
- trigger the normal vault refresh rail, which can queue Curator fanout for
  follow-up plugin-context updates

## First-flight outputs

After a successful run, the enrolled user agent should have:

- `$HERMES_HOME/state/arclink-vault-reconciler.json`

This is not an optional extra. First-contact is not complete until the initial plugin context state exists. Dynamic `[managed:*]` context is hot-injected by the `arclink-managed-context` plugin; it is not written into Hermes `MEMORY.md`.

The JSON summary should also include a successful qmd probe record. If qmd cannot answer a real MCP query call, first-contact is not complete.

When shared Notion indexing is configured for the host, the summary should also include a successful `notion.search` probe record. If that rail is configured but not callable, first-contact is not complete.

## Guardrails

- treat qmd as the retrieval plane and `arclink-mcp` as the control plane
- use the passed environment variables plus MCP responses; do not inspect central deployment secrets such as `arclink.env`, `.arclink-operator.env`, or source `bin/common.sh` from a user-agent session
- do not browse other users' home directories; stay within the current user's `HERMES_HOME` plus the shared ArcLink MCP and qmd surfaces
- do not store raw vault bodies or PDF bodies in built-in memory
- if vault subscription defaults already exist from a prior archived enrollment, keep them unless the user explicitly changes them
- if the user only has TUI enabled, skip home-channel configuration without treating it as a failure
- never write to the vault from this skill - it is read-only verification
