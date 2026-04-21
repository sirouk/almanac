---
name: almanac-notion-mcp
description: Use when a user's Notion workspace is already connected through the official Notion MCP and the task should read or update that user-owned Notion space.
---

# Almanac Notion MCP

Use this skill after the user-owned Notion MCP connection is already live.

This skill is for the user's own Notion workspace reached through Notion's
hosted MCP, not the shared Almanac SSOT.

## Preconditions

- if the Notion MCP is not connected yet, use `almanac-ssot-connect` first
- if the task is about the shared organizational Notion space, use
  `almanac-ssot` instead
- shared organizational writes and attribution do not go through this lane;
  they stay on Almanac's centralized brokered rail

## Official References

- Notion MCP quickstart:
  `https://developers.notion.com/docs/get-started-with-mcp`
- Hosted Notion MCP endpoint:
  `https://mcp.notion.com/mcp`

## Working Style

- verify the Notion MCP is reachable before leaning on it
- prefer narrow reads first: list recent pages, search by exact title, inspect
  one target page or database
- when writing, keep the scope tight and match the user's requested surface
- confirm before archive, delete, or broad multi-page edits

## Almanac-Specific Rails

- treat the user-owned Notion MCP and the shared Almanac SSOT as separate lanes
- if the task mixes both, name which one you are reading from or writing to
- use qmd / Almanac vault retrieval for shared private vault context
- use the user-owned Notion MCP for that user's personal or workspace-specific
  Notion tasks

## Guardrails

- do not ask the user to reveal secrets that the MCP/OAuth flow can handle
- do not silently copy organizational SSOT data into a private Notion space
- do not assume every Notion page is writable just because the MCP is connected
- if the Notion MCP response conflicts with Almanac SSOT context, surface the
  distinction instead of guessing
