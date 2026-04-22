#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
NOTION_MCP_SKILL = REPO / "skills" / "almanac-notion-mcp" / "SKILL.md"
NOTION_KNOWLEDGE_SKILL = REPO / "skills" / "almanac-notion-knowledge" / "SKILL.md"
SSOT_CONNECT_SKILL = REPO / "skills" / "almanac-ssot-connect" / "SKILL.md"
SSOT_SKILL = REPO / "skills" / "almanac-ssot" / "SKILL.md"
CODEX_CONFIG = REPO / ".codex" / "config.toml"
CONNECT_SCRIPT = REPO / "skills" / "almanac-ssot-connect" / "scripts" / "check-codex-notion-mcp.sh"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_notion_mcp_skill_teaches_search_then_fetch() -> None:
    body = NOTION_MCP_SKILL.read_text(encoding="utf-8")
    expect("optional personal/operator tooling" in body, body)
    expect("not the core Almanac-wide" in body, body)
    expect("search-first, fetch-second retrieval" in body, body)
    expect("notion-search" in body, body)
    expect("notion-fetch" in body, body)
    expect("search" in body and "fetch" in body, body)
    expect("Do not fetch every search hit." in body, body)
    expect("search is for discovery, fetch is for reading" in body, body)
    expect("shared SSOT broker" in body, body)
    expect("at most 2 search calls" in body, body)
    expect("at most 3 fetches" in body, body)
    expect("I may not have access" in body, body)
    expect("the index may not have caught up yet" in body, body)
    expect("Lane Routing" in body, body)
    print("PASS test_notion_mcp_skill_teaches_search_then_fetch")


def test_notion_knowledge_skill_teaches_shared_three_tool_split() -> None:
    body = NOTION_KNOWLEDGE_SKILL.read_text(encoding="utf-8")
    expect("shared Almanac Notion knowledge rail" in body, body)
    expect("knowledge question -> `search`" in body, body)
    expect('"read this exact page" -> `fetch`' in body, body)
    expect('"what is assigned / due / in progress" -> `query`' in body, body)
    expect("database/data source" in body or "database or data source" in body, body)
    expect("attachment" in body.lower(), body)
    expect("search is qmd-backed" in body, body)
    expect("fetch` and `query` are live Notion reads" in body, body)
    expect("scripts/curate-notion.sh search" in body, body)
    expect("scripts/curate-notion.sh fetch" in body, body)
    expect("scripts/curate-notion.sh query" in body, body)
    print("PASS test_notion_knowledge_skill_teaches_shared_three_tool_split")


def test_ssot_connect_requires_search_and_fetch_verification() -> None:
    body = SSOT_CONNECT_SKILL.read_text(encoding="utf-8")
    expect("optional personal-Notion" in body, body)
    expect("Optional Codex Bench" in body, body)
    expect("verify the MCP connection with one search and one fetch" in body, body)
    expect("`search`" in body and "`fetch`" in body, body)
    expect("`notion-search`" in body and "`notion-fetch`" in body, body)
    expect("one real search and one real fetch work" in body, body)
    expect("codex mcp get notion --json" in body, body)
    expect("codex mcp login notion" in body, body)
    expect("scripts/check-codex-notion-mcp.sh" in body, body)
    print("PASS test_ssot_connect_requires_search_and_fetch_verification")


def test_ssot_skill_marks_broker_as_non_workspace_search_lane() -> None:
    body = SSOT_SKILL.read_text(encoding="utf-8")
    expect("not as a broad" in body and "documentation search tool" in body, body)
    expect("default shared Almanac" in body and "workspace-search path" in body, body)
    expect("owner, status, due date, or assignee" in body, body)
    expect("name both sources" in body, body)
    print("PASS test_ssot_skill_marks_broker_as_non_workspace_search_lane")


def test_project_codex_config_and_connect_script_exist() -> None:
    config_body = CODEX_CONFIG.read_text(encoding="utf-8")
    script_body = CONNECT_SCRIPT.read_text(encoding="utf-8")
    expect("[mcp_servers.notion]" in config_body, config_body)
    expect('url = "https://mcp.notion.com/mcp"' in config_body, config_body)
    expect("codex mcp get notion --json" in script_body, script_body)
    expect("codex mcp login notion" in script_body, script_body)
    expect("Search is for candidate discovery." in script_body, script_body)
    print("PASS test_project_codex_config_and_connect_script_exist")


def main() -> int:
    test_notion_mcp_skill_teaches_search_then_fetch()
    test_notion_knowledge_skill_teaches_shared_three_tool_split()
    test_ssot_connect_requires_search_and_fetch_verification()
    test_ssot_skill_marks_broker_as_non_workspace_search_lane()
    test_project_codex_config_and_connect_script_exist()
    print("PASS all 5 notion skill text regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
