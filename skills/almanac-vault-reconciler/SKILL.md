---
name: almanac-vault-reconciler
description: Use when an agent needs to keep compact managed memories aligned with an Almanac vault behind qmd, run an initial reconciliation, or schedule recurring 4-hour Almanac vault sync and health checks with terse notices.
---

# Almanac Vault Reconciler

Use this skill when the user wants an agent to treat a shared markdown vault plus qmd
as the long-term knowledge layer while keeping only a small, managed memory stub
inside the agent.

This skill is for ongoing maintenance, not full-content ingestion.

It does not turn every note or PDF into built-in agent memory.

## Core contract

The vault is the source of truth.

qmd is the deep retrieval layer over that vault.

Built-in memory should hold only compact routing hints, not note bodies or large
knowledge dumps. Managed memory here is only a compact routing stub, not a full
copy of document bodies.

Managed memory entries must use these prefixes exactly:

- `[managed:almanac-skill-ref]`
- `[managed:vault-ref]`
- `[managed:qmd-ref]`
- `[managed:vault-topology]`

Only touch memories with those prefixes.

## Use this skill to

- discover the active shared vault that qmd is indexing
- reconcile managed memory pointers against the live vault and qmd state
- run one initial reconciliation so the agent starts from current vault reality
- create or repair a recurring 4-hour reconciliation job
- emit a terse Almanac health notice on each recurring run
- detect drift between filesystem topology, qmd coverage, and managed memory

## Preferred tools

Prefer the agent's native memory tool, MCP client, and scheduler.

For Hermes, the relevant commands are:

```bash
hermes mcp add <name> --url <endpoint>
hermes mcp test <name>
hermes cron list
hermes cron create "every 4h" "<prompt>" --name "<name>" --skill almanac-vault-reconciler
hermes cron edit <job_id> --schedule "every 4h" --prompt "<prompt>" --skill almanac-vault-reconciler
hermes cron run <job_id>
```

If you are not running inside Hermes, map those same ideas onto the local
platform:

- MCP server registration
- memory read and write
- recurring scheduler
- one-shot execution

## Onboarding workflow

When the user asks to enable this memory system, do this in order:

1. Confirm the qmd endpoint and register it with the agent's MCP client.
2. Verify the MCP connection with the platform's MCP test flow.
3. Discover the active vault and current qmd collection state.
4. If local qmd CLI access exists and the index is stale, refresh it once.
5. Run one reconciliation immediately.
6. Create or repair one recurring 4-hour job.

Do not stop after "saving context to memory." The skill is not complete until
the first reconciliation has run and the recurring job exists.

Hermes loads `MEMORY.md` as a frozen snapshot at session start. On first setup,
write or refresh the managed routing stubs immediately so future sessions start
with the correct qmd-first routing behavior. Do not rely on background memory
review or session-end flush to keep those stubs current.

## MCP setup guardrails

Prefer qmd through MCP over direct filesystem reads when it is available.

If the user provides an MCP URL, add it directly instead of searching the web
for unrelated skills or endpoints.

Important:

- do not treat a plain `GET` request to `/mcp` returning `404` as proof that the
  MCP endpoint is broken
- validate MCP with the agent's MCP test command or MCP tool call
- if the GitHub repo is private and a raw `SKILL.md` URL returns `404`, treat
  that as an authentication problem, not as proof that the skill does not exist
- do not browse other users' home directories; for user-agent runs, stay within
  the current user's `HERMES_HOME` plus the shared Almanac MCP and qmd
  surfaces

## Discovery signals

Choose the active vault by weighing these signals in order:

1. explicit user-provided vault path
2. qmd collection path or qmd status output
3. existing managed memories
4. last known good state file
5. conventional vault paths on disk

A repo-local `almanac-priv` next to a source checkout is not enough on its own.
If that path has no `config/almanac.env`, treat it as a scaffold until stronger
evidence says otherwise.

The chosen vault should:

- exist
- be readable
- contain markdown
- agree with qmd when possible

If multiple plausible vaults remain, report the ambiguity clearly instead of
guessing.

If the live qmd listener belongs to another user such as `almanac`, prefer the
deployed instance behind that listener over source-checkout defaults owned by
the current interactive user.

If that deployed instance lives under `/home/almanac/almanac`, treat that path
as the shared service-user deployment root. It is normal shared infrastructure,
not another enrolled user's private workspace.

## What to inspect

Prefer native tools first, then local files as supporting evidence.

Useful supporting locations:

- `$HERMES_HOME/memories/MEMORY.md`
- `$HERMES_HOME/memories/USER.md`
- `$HERMES_HOME/state/almanac-vault-reconciler.json`

For user-agent runs on a shared host, do not inspect central deployment files
such as `/home/almanac/almanac/almanac-priv/config/almanac.env`,
`.almanac-operator.env`, or source `/home/almanac/almanac/bin/common.sh`.
Use the already wired MCP endpoints and the agent-local state above instead.

Read the memory files if you need to understand current managed entries, but do
not hand-edit them unless the user explicitly asks for direct file edits, other
than the narrow Hermes-cron fallback described below for the managed entries.

## Hermes memory behavior that matters

On Hermes, built-in memory works like this:

- `MEMORY.md` and `USER.md` are loaded from disk as a frozen snapshot at session start
- native memory-tool writes persist to disk immediately, but they become automatic prompt context on the next session start
- scheduled Hermes cron runs are started with `skip_memory=True`, so the native memory tool may be unavailable there by design

Because of that:

- do not rely on background memory review or session-end flush to keep these managed stubs current
- the first reconciliation run should write the managed routing stubs immediately so future sessions start with the right qmd reflex
- a cron reconciliation may need a narrow direct-file fallback for just the managed entries

## First-run refresh

If the agent has shell access to the qmd host, make sure qmd is current before
the first reconciliation.

Use the lightest correct path:

- inside Almanac, prefer repo wrappers such as `bin/qmd-refresh.sh`
- otherwise use the local qmd CLI, such as `qmd update` and `qmd embed`

If the agent has only remote MCP access and cannot refresh qmd locally, report
that limitation and continue with reconciliation against the current index.

For user-agent runs on a shared host, never switch from the shared qmd surface
into browsing another user's home directory just to infer the vault target.

Do not run refresh commands against a repo-local scaffold vault unless a real
deployment config points there or the user explicitly confirms that target.

## Reconciliation workflow

Each run should do all of the following:

1. Resolve the active vault.
2. Scan the vault and infer a high-level topology.
3. Read current managed memory entries.
4. Check qmd health and collection alignment.
5. Check representative qmd coverage for the populated vault branches.
6. Update managed memories if the memory tool is available.
7. Write or refresh the reconciler state file.
8. Report what changed, what drift remains, and whether follow-up is needed.

## Topology rules

Infer topology from the actual vault, not from stale memory alone.

Prefer populated branches over empty placeholders.

The topology summary should stay compact. Good inputs include:

- populated top-level folders
- populated major sub-areas when they are meaningful
- root landing notes such as `Home.md`

Do not dump every filename into memory.

## qmd checks

For qmd, verify at least:

- collection exists
- collection path matches the chosen vault when possible
- indexed document count
- embedding backlog, if exposed
- vector search availability
- representative coverage for populated major branches

Check both directions:

- filesystem or vault topology should be represented in qmd
- managed topology memory should not keep pointing at vanished branches

If qmd count drift is small but persistent, report it as drift instead of
pretending everything matches.

## Managed memory behavior

The managed memories should stay short and durable.

Recommended shape:

- `[managed:almanac-skill-ref]` Almanac skills are active defaults and when to reach for each
- `[managed:vault-ref]` active vault path and role
- `[managed:qmd-ref]` qmd is the deeper retrieval layer for vault-relevant work; for private or shared-vault questions or follow-ups grounded in the current discussion, query qmd before web search, including PDF-derived collections such as `vault-pdf-ingest` when present; those PDF-derived notes may be generated Markdown reconciled from PDFs and can include visual captions for diagrams, charts, and figures from PDF pages
- `[managed:vault-topology]` compact summary of the populated high-level topology

The content of those stubs should be explicit enough that a future session can
infer the retrieval behavior without being reminded by the user.

These stubs are not meant to answer the user's question by themselves. They are
meant to trigger qmd retrieval reflexively.

Good example shapes:

- `[managed:almanac-skill-ref]` Installed Almanac skills are active defaults. Use almanac-qmd-mcp for vault retrieval and follow-ups, almanac-vaults for subscription and catalog work, almanac-vault-reconciler for Almanac memory drift or repair, almanac-ssot for SSOT coordination, and almanac-first-contact for Almanac setup or diagnostic checks.
- `[managed:vault-ref] Shared Almanac vault lives behind qmd; treat the vault as the source of truth for private knowledge.`
- `[managed:qmd-ref] For private/shared-vault questions or follow-ups grounded in the current discussion, use qmd first via MCP. Run mixed lex plus vec queries against vault and vault-pdf-ingest when present. Fall back to direct local qmd service or CLI only if MCP is unavailable.`
- `[managed:vault-topology] High-level populated areas only, such as major folders or landing notes; no note bodies or long file lists.`

Do not make these memories vague. They should not just say that qmd exists.
They should tell a future agent when to use qmd, how to use it at a high level,
and when to include the PDF-derived collection.

Use the memory tool for add, update, and removal when it is available.

On Hermes, prefer the native memory tool in normal interactive or agent
sessions.

If you are running inside a Hermes cron job and the native memory tool is
unavailable:

- directly patch only the four `[managed:*]` entries in `$HERMES_HOME/memories/MEMORY.md`
- preserve every unrelated entry exactly as-is
- preserve Hermes's `§`-delimited entry format
- keep the resulting `MEMORY.md` content within Hermes's built-in memory char budget
- do not edit `USER.md`

If the memory tool is unavailable:

- do not silently fail
- outside the Hermes cron fallback above, do not hand-edit memory files by default
- report that reconciliation was blocked at the memory-write step
- still write the state file and complete the health report

## Missing-vault safety

Do not immediately delete managed memories on the first failed vault check.

Use a grace period:

- first failure: report unavailable or stale state and preserve managed entries
- repeated failures with no matching qmd collection: remove or replace only the
  managed entries

This prevents temporary unmounts or path glitches from causing destructive
cleanup.

## State file

Keep a compact state file at:

```text
$HERMES_HOME/state/almanac-vault-reconciler.json
```

Track at least:

- `last_run_at`
- `last_success_at`
- `consecutive_failures`
- `last_good_vault_path`
- `last_good_qmd_collection`
- `last_topology_summary`
- `issues`

Use the state file to distinguish persistent drift from transient noise.

## Recurring job

Create or repair one job, not duplicates.

Recommended Hermes job name:

```text
Almanac Vault Sync + Health
```

Recommended recurring prompt:

```text
Run almanac-vault-reconciler. Discover the active shared vault behind qmd. Refresh and prune only the compact managed memory stubs [managed:almanac-skill-ref], [managed:vault-ref], [managed:qmd-ref], and [managed:vault-topology] so future sessions know Almanac skills are active defaults and use qmd first for private/shared-vault questions and follow-ups from the current discussion, including PDF-derived collections when present. Keep built-in memory compact, use the native memory tool when available, and in Hermes cron patch only those four managed entries directly in $HERMES_HOME/memories/MEMORY.md if the memory tool is unavailable. Verify vault sync, qmd indexing, and memory-state alignment, refresh the state file, and emit a terse Almanac health notice: one line on success, at most two lines on warn/fail. Keep the vault read-oriented unless the user explicitly asked for writes.
```

Recommended schedule:

```text
every 4h
```

List existing jobs first.

If a job with the recommended purpose or name already exists, edit it instead
of creating another one.

After creating or editing the job, run it once immediately.

## Reporting

Default scheduled output should be terse.

For recurring 4-hour runs:

- success: exactly 1 short line
- warn or fail: at most 2 short lines
- include only Almanac sync, qmd indexing, managed-memory status, and drift or blocked state
- do not dump vault topology, file lists, disk details, or long diagnostics unless the user explicitly asked for detail

Recommended success shape:

- `Almanac health ok: sync current, qmd indexed, managed memory refreshed, drift=none.`

Recommended warn or fail shape:

- `Almanac health warn: sync current, qmd partial, managed memory unchanged.`
- `Drift: missing qmd coverage for <area>; blocked: <issue>.`

For interactive or explicitly requested diagnostic runs, it is fine to add a
few short bullets with:

- active vault path
- qmd collection and indexed-doc state
- managed memory actions taken
- unresolved drift or blocked steps

## Success criteria

This skill is behaving correctly when:

- qmd is configured and verified through MCP
- the agent ran one reconciliation immediately
- one recurring 4-hour job exists
- managed memories point to the live vault and qmd layer
- the state file reflects the latest run
- the user receives a clear report instead of vague reassurance
