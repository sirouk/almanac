# Research Summary

<confidence>96</confidence>

## Scope

This Attempt 8 PLAN refresh inspected the ArcLink Dream Buildout sources
required by the phase prompt: `AGENTS.md`,
`research/RALPHIE_ARCLINK_DREAM_BUILDOUT_STEERING.md`, `USER_JOURNEY.md`,
`GAPS.md`, `IMPLEMENTATION_PLAN.md`, and `research/COVERAGE_MATRIX.md`.

The pass stayed local. It did not inspect `arclink-priv/`, user homes, secret
files, deploy keys, `.env` values, OAuth stores, bot tokens, production
services, live Stripe/Telegram/Discord/Notion/Cloudflare/Tailscale/provider
accounts, remote hosts, Docker runtime state, systemd, or Hermes core.

## Current Posture

`GAP-025` was checked first. It is closed by current source and test evidence:
the broad no-secret Python suite was rerun during this PLAN refresh and passed
with 1235 passed, 6 skipped, and 81 warnings in 63.06s. That is local Python
validation only; it does not close live proof gates or web/Node browser proof.

The active next slice is `GAP-016`, the Linked-resource copy/duplicate policy
mismatch. Current docs and plugin tests say accepted Linked resources are
read-only, cannot be reshared, and may be copied or duplicated only into the
recipient's owned Vault/Workspace roots. The MCP `shares.request` response still
reports `copy_duplicate_policy: policy_question`, so agents can describe the
policy as undecided.

Focused plan validation was rerun locally:

```bash
python3 -m pytest -q tests/test_arclink_mcp_schemas.py::test_agent_share_request_tool_creates_scoped_pending_grant tests/test_arclink_plugins.py::test_arclink_drive_and_code_expose_read_only_linked_root --maxfail=20
python3 -m pytest -q tests/test_arclink_plugins.py tests/test_arclink_mcp_schemas.py --maxfail=20
```

Results: 2 passed, then 45 passed in 4.09s.

The broad `GAP-025` gate was also rerun:

```bash
python3 -m pytest -q tests
```

Result: 1235 passed, 6 skipped, 81 warnings.

## Build Handoff

Proceed to the bounded local `GAP-016` slice. Add the missing MCP assertion
first, then align `python/arclink_mcp_server.py` and
`plugins/hermes-agent/arclink-managed-context/__init__.py` with the existing
Drive/Code Linked-root behavior. Inspect `docs/arclink/operations-runbook.md`
and change it only if it no longer matches source truth.

The first reproduction command is:

```bash
python3 -m pytest -q tests/test_arclink_mcp_schemas.py::test_agent_share_request_tool_creates_scoped_pending_grant tests/test_arclink_plugins.py::test_arclink_drive_and_code_expose_read_only_linked_root --maxfail=20
```

The focused surface command is:

```bash
python3 -m pytest -q tests/test_arclink_plugins.py tests/test_arclink_mcp_schemas.py --maxfail=20
```

Run `python3 -m pytest -q tests` after source/test edits to keep `GAP-025`
honest.

## Boundaries

Allowed work for the next slice is local source, tests, and docs. Do not run
`deploy.sh`, Docker mutation, system service commands, Stripe, Telegram,
Discord, live Notion, Cloudflare, Tailscale, SSH fleet, provider mutation, or
other live/host-mutating commands in the unattended build pass.

`GAP-014`, `GAP-015`, `PG-BOTS`, and `PG-HERMES` remain separate browser,
notification, live bot, and live workspace gates. `GAP-019` remains reduced but
open for helper splits, stronger isolation, runtime alert integration, or an
operator residual-risk decision.
