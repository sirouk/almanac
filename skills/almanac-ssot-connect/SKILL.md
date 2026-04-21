---
name: almanac-ssot-connect
description: Optional helper for linking a user's separate personal Notion workspace through the official Notion MCP flow; not part of Almanac's default shared Notion contract.
---

# Almanac SSOT Connect

Use this skill only when the user wants their own agent to connect to a
separate personal Notion workspace.

This is distinct from the shared Almanac SSOT:

- `almanac-ssot` is for the operator-managed organizational Notion space
  brokered through Almanac's own `ssot.read` / `ssot.write` rails
- `almanac-ssot-connect` is for the user's own Notion MCP connection
- shared organizational Notion verification now happens through Curator during
  onboarding; this skill is only for the user's separate private/user-owned
  Notion lane

Do not blur those two surfaces together. This is optional personal-Notion
setup, not the default shared Almanac Notion knowledge rail.

## Default Flow

1. clarify whether they mean the shared organizational SSOT or their own Notion
2. if they mean the shared SSOT, hand back to `almanac-ssot` or the operator
3. if they mean their own Notion, walk them through the official Notion MCP setup
4. verify the MCP connection with one search and one fetch before treating it as live
5. once connected, hand ongoing work to `almanac-notion-mcp`

## Official References

- Notion MCP quickstart:
  `https://developers.notion.com/docs/get-started-with-mcp`
- Hosted Notion MCP endpoint:
  `https://mcp.notion.com/mcp`

## What To Tell The User

- use your MCP client's add-server flow and point it at `https://mcp.notion.com/mcp`
- complete the Notion OAuth approval flow in the browser your MCP client opens
- once the connection succeeds, verify it with:
  - one search for a page you expect to see
  - one fetch of the matching page URL or ID

For Codex / OpenAI MCP clients, the hosted tools may surface as `search` and
`fetch` instead of `notion-search` and `notion-fetch`.

## Optional Codex Bench

Inside this repo, the project-level Codex config can be used as an operator
bench to validate the hosted Notion MCP.

Use this exact sequence:

1. run `codex mcp get notion --json` to confirm the project sees the server
2. run `codex mcp login notion`
3. complete the OAuth flow in the browser
4. verify with one real search and one real fetch

Helper:

- `scripts/check-codex-notion-mcp.sh`

If the user is on a shared-host Almanac agent, keep the language simple:

- the shared SSOT is already operator-managed
- this step is only for the user's own private Notion lane

## Guardrails

- prefer OAuth through the official Notion MCP flow; do not ask for the user's
  Notion password
- do not ask the user to paste long-lived OAuth tokens into chat if the client
  can authorize directly
- do not store user-owned Notion credentials in Almanac managed memory
- do not treat success as complete until one real search and one real fetch work
- do not confuse a working OAuth connection with proof that broad retrieval is
  exhaustive, fresh, or complete
- if the user wants organization-wide updates in the shared SSOT, use
  `almanac-ssot`, not their private Notion MCP
