---
name: almanac-qmd-mcp
description: Use when an agent needs to connect to an Almanac qmd index, configure or verify the local qmd MCP endpoint, or answer private/shared-vault questions by querying qmd on a host that runs Almanac.
---

# Almanac qmd MCP

Use this skill when the user wants an agent to work with the Almanac vault through qmd, either by:

- connecting to the local qmd MCP HTTP endpoint
- connecting to the tailnet-exposed qmd MCP endpoint from another machine
- configuring an MCP client such as Hermes
- answering questions that may depend on shared private vault knowledge
- verifying that qmd indexing or the MCP daemon is healthy
- falling back to direct `qmd` CLI access when MCP integration is not the best fit
- handing another agent a stable path for ongoing vault-memory reconciliation

## What to look for

Check these local files first:

- `$HERMES_HOME/state/almanac-vault-reconciler.json` and `$HERMES_HOME/memories/almanac-managed-stubs.md` for safe, agent-local Almanac routing state
- `docs/hermes-qmd-config.yaml` for the default MCP client snippet
- `bin/qmd-daemon.sh` for how the qmd MCP server is started
- `bin/qmd-refresh.sh` for index refresh and embeddings
- `bin/health.sh` for the expected service and port state
- `/home/almanac/almanac/skills/almanac-qmd-mcp` and `/home/almanac/almanac/skills/almanac-vault-reconciler` when Hermes is running on the same host as the deployed Almanac instance and needs the shared skill text, not central secrets or private config

Typical deployed paths:

- public repo: `/home/almanac/almanac`
- private repo: `/home/almanac/almanac/almanac-priv`
- local MCP endpoint: `http://127.0.0.1:8181/mcp`
- tailnet MCP endpoint: `https://<almanac-node>.<tailnet>/mcp`
- default qmd index name: `almanac`
- default qmd collection name: `vault`

On a shared-host user agent, `/home/almanac/almanac` is the service-user
deployment root. Reading shared repo content there is expected. Treat it as
read-only shared infrastructure, not as another enrolled user's workspace.

Do not read `/home/almanac/almanac/almanac-priv/config/almanac.env`,
`.almanac-operator.env`, or source `bin/common.sh` from a user-agent session.
Those central deployment files may contain secrets and are outside the normal
least-privilege boundary for an enrolled user bot. Prefer the already wired MCP
URLs, `bin/almanac-rpc`, and the agent-local Almanac state under `$HERMES_HOME`
instead.

Do not assume these values; prefer agent-local state and already wired MCP
configuration before central deploy config.

Do not treat a repo-adjacent `almanac-priv` directory as proof that you found
the live vault. If `config/almanac.env` is missing there, it may only be a
scaffold inside a source checkout.

## Preferred workflow

1. Discover the effective settings.
2. If the client supports MCP HTTP servers, connect it to the qmd endpoint.
3. If MCP is unavailable or unnecessary, use `qmd` directly against the local index.
4. If the user wants recurring vault-memory upkeep, pair this skill with `skills/almanac-vault-reconciler/SKILL.md`.
5. If the user asks for troubleshooting, check the health script, service state, port state, and collection state before changing anything.

## Answering vault-backed questions

When the user asks a question that could plausibly be answered by shared private
documents, team notes, uploaded PDFs, internal terminology, company-specific
plans, codenames, or a follow-up grounded in the current discussion, query qmd
before you search the public web or answer from general model memory.

Examples:

- "Do you know about Chutes MESH?"
- "What do our vault docs say about this?"
- "Did the PDFs I uploaded get picked up?"
- questions about internal roadmaps, project names, specs, decks, or research PDFs

For those questions:

1. query qmd first
2. seed qmd with the user's current wording, close acronym or spelling variants, and both lexical and semantic retrieval
3. prefer both the primary vault collection and any PDF-derived collection such as `vault-pdf-ingest` when present
4. answer from qmd results if they exist
5. only fall back to public-web search if qmd does not contain the answer, or if the user explicitly asks for public verification

Do not answer "I don't know" or jump to public search before checking qmd when
the topic looks vault-backed.

## MCP client setup

Choose the endpoint based on where the client runs:

- same host as Almanac: use the local MCP URL
- another device or agent on the same tailnet: use the Tailscale HTTPS URL for `/mcp`

If the agent or client supports MCP HTTP configuration, use a server entry shaped like this:

```yaml
mcp_servers:
  qmd:
    url: "http://127.0.0.1:8181/mcp"
    timeout: 30
```

Use the actual configured port if `QMD_MCP_PORT` differs.

For a remote Hermes agent on your tailnet, the shape is the same but the URL should be the tailnet endpoint:

```yaml
mcp_servers:
  qmd:
    url: "https://<almanac-node>.<tailnet>/mcp"
    timeout: 30
```

If the client already has its own MCP configuration format, map the same endpoint into that format instead of forcing this YAML shape.

Do not decide the endpoint is broken just because a plain browser or `curl` GET
to `/mcp` returns `404`. Prefer the client's MCP test flow.

## Pairing with the reconciler skill

If the user wants the agent to stay aligned with the vault over time, this
skill should lead into `skills/almanac-vault-reconciler/SKILL.md`.

Expected handoff:

1. connect the agent to qmd over MCP
2. verify the MCP connection with the agent's MCP test path
3. run one vault-memory reconciliation immediately
4. create or repair one 4-hour recurring reconciliation job

If the local qmd listener is owned by another user such as `almanac`, prefer
that deployed instance and its live qmd collection over defaults inferred from a
different checkout.

Inside Hermes, the normal shape is:

```bash
hermes mcp add almanac-qmd --url "<endpoint>"
hermes mcp test almanac-qmd
hermes cron create "every 4h" "<prompt>" --name "Almanac Vault Sync + Health" --skill almanac-vault-reconciler
```

If the recurring job already exists, edit it instead of creating a duplicate.

## Query strategy

For best recall on vault knowledge, use a mixed retrieval strategy instead of a
single exact-term search when possible:

- `lex` for explicit names, filenames, and quoted phrases
- `vec` for natural-language meaning
- use the current discussion as seed context for query phrasing, especially when the user is asking a short follow-up like "what about now?" or naming an internal term without much context
- include `vault-pdf-ingest` alongside `vault` when PDF ingestion is enabled

If a user is asking about a newly uploaded PDF, check the PDF-derived collection
first or alongside the main vault collection. Those PDF-derived notes may be
generated Markdown reconciled from PDFs and can include visual captions for
diagrams, charts, and figures from PDF pages.

## Direct qmd fallback

When MCP is not the right path, use direct qmd commands.

Common patterns:

```bash
qmd --index almanac collection show vault
qmd --index almanac update
qmd --index almanac embed
qmd --index almanac mcp --http --port 8181
```

Inside an Almanac checkout, prefer the repo wrappers when they exist:

```bash
bin/qmd-shell.sh collection show vault
bin/qmd-refresh.sh
bin/qmd-daemon.sh
```

## Verification

For verification, prefer these checks in order:

1. `bin/health.sh`
2. confirm the qmd MCP port is listening
3. confirm the qmd collection exists in the configured index
4. confirm the client is pointing at the same endpoint the daemon is serving
5. if the client is remote, confirm the Tailscale URL is reachable and not using `127.0.0.1`

If the daemon is managed by user systemd, the relevant unit is:

- `almanac-qmd-mcp.service`

Related vault-sync services:

- `almanac-vault-watch.service`
- `almanac-qmd-update.timer`
- `almanac-pdf-ingest.timer`

## Guardrails

- Treat the vault as the authoritative knowledge source and avoid writing to it unless the user explicitly asks.
- Prefer reading effective config over assuming defaults.
- For a user-agent session on a shared host, never inspect central deployment
  secrets such as `almanac.env` or source `bin/common.sh`; use the already
  wired MCP endpoints and agent-local Almanac state instead.
- Do not hard-code Hermes-specific behavior when a generic MCP client path will do.
- If both MCP and direct qmd CLI are viable, choose the lighter path for the user’s task.
- Prefer MCP and qmd over direct filesystem scraping when the vault is meant to stay read-oriented.
- For private or shared-vault knowledge questions, prefer qmd before web search.
- If qmd has relevant hits, do not ignore them and answer from the public web instead.
- Do not refresh or reindex a repo-local scaffold vault unless the user explicitly confirms that is the intended target.
