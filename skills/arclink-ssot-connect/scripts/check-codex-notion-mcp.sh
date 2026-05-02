#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../../.. && pwd)"
config_path="$repo_root/.codex/config.toml"

if ! command -v codex >/dev/null 2>&1; then
  echo "Codex CLI is not installed or not on PATH." >&2
  echo "Install Codex, then rerun this helper." >&2
  exit 2
fi

echo "Repo root: $repo_root"
echo "Expected project config: $config_path"

if [[ ! -f "$config_path" ]]; then
  echo "Missing project-level Codex config for Notion MCP." >&2
  echo "Expected: [mcp_servers.notion] with url = \"https://mcp.notion.com/mcp\"" >&2
  exit 2
fi

if codex mcp get notion --json >/dev/null 2>&1; then
  echo "Notion MCP is configured for this project."
else
  echo "Notion MCP is not visible to Codex in this project." >&2
  echo "Try: codex mcp add notion --url https://mcp.notion.com/mcp" >&2
  exit 2
fi

echo
echo "Next steps:"
echo "  1. Run: codex mcp login notion"
echo "  2. Complete the browser OAuth flow."
echo "  3. In Codex, verify one real search and one real fetch."
echo
echo "Suggested verification prompts:"
echo "  - Search Notion for \"Example Unicorn\" and show the top candidate pages."
echo "  - Fetch the best matching page and summarize the body."
echo
echo "Remember:"
echo "  - Search is for candidate discovery."
echo "  - Fetch is for reading the actual page body or database/data-source detail."
echo "  - Thin or zero results may mean access scope, not absence."
