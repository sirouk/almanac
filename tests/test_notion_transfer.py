#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "bin" / "notion-transfer.py"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_tool():
    spec = importlib.util.spec_from_file_location("notion_transfer", TOOL_PATH)
    expect(spec is not None and spec.loader is not None, "could not load notion-transfer.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_notion_id_extracts_url_and_plain_ids() -> None:
    tool = load_tool()
    expected = "351d9880-18ca-80bd-89e7-f1988f75b862"
    expect(tool.notion_id("https://www.notion.so/The-Almanac-351d988018ca80bd89e7f1988f75b862?pvs=13") == expected, "url id extraction failed")
    expect(tool.notion_id("351d988018ca80bd89e7f1988f75b862") == expected, "plain id normalization failed")
    print("PASS test_notion_id_extracts_url_and_plain_ids")


def test_property_schema_is_workspace_portable() -> None:
    tool = load_tool()
    schema = tool.sanitize_property_schema(
        {
            "Name": {"id": "title-id", "type": "title", "title": {}},
            "Stage": {
                "id": "status-id",
                "type": "status",
                "status": {
                    "options": [{"id": "old-option-id", "name": "Doing", "color": "blue"}],
                    "groups": [{"id": "old-group-id", "name": "Active", "option_ids": ["old-option-id"]}],
                },
            },
            "Owner": {"id": "people-id", "type": "people", "people": {}},
            "Related": {"id": "relation-id", "type": "relation", "relation": {"data_source_id": "old"}},
        }
    )
    expect("Name" in schema and schema["Name"] == {"title": {}}, f"title schema not portable: {schema}")
    expect(schema["Stage"]["status"]["options"] == [{"name": "Doing", "color": "blue"}], f"status options kept old ids: {schema}")
    expect("groups" not in schema["Stage"]["status"], f"status groups should not preserve old ids: {schema}")
    expect("Owner" not in schema, f"people schema should be skipped: {schema}")
    expect("Related" not in schema, f"relation schema should be skipped until id remapping exists: {schema}")
    print("PASS test_property_schema_is_workspace_portable")


def test_page_properties_skip_nonportable_values() -> None:
    tool = load_tool()
    props = tool.sanitize_page_properties(
        {
            "Name": {"type": "title", "title": [{"plain_text": "Roadmap", "href": None}]},
            "Notes": {"type": "rich_text", "rich_text": [{"plain_text": "hello", "href": None}]},
            "Stage": {"type": "select", "select": {"id": "old", "name": "Doing", "color": "blue"}},
            "Related": {"type": "relation", "relation": [{"id": "old-page"}]},
            "Edited": {"type": "last_edited_time", "last_edited_time": "2026-01-01T00:00:00.000Z"},
        },
        title_fallback="Fallback",
    )
    expect(props["Name"]["title"][0]["text"]["content"] == "Roadmap", f"title was not sanitized: {props}")
    expect(props["Notes"]["rich_text"][0]["text"]["content"] == "hello", f"rich text was not sanitized: {props}")
    expect(props["Stage"] == {"select": {"name": "Doing"}}, f"select should use destination option name: {props}")
    expect("Related" not in props, f"relations should wait for an id remap pass: {props}")
    expect("Edited" not in props, f"read-only values should be skipped: {props}")
    print("PASS test_page_properties_skip_nonportable_values")


def test_page_parent_payload_uses_plain_title_property() -> None:
    tool = load_tool()
    payload = tool.page_create_payload(
        {
            "properties": {
                "Name": {"type": "title", "title": [{"plain_text": "Child page"}]},
                "Status": {"type": "select", "select": {"name": "Doing"}},
            }
        },
        {"type": "page_id", "page_id": "dest"},
    )
    expect(payload["properties"]["title"][0]["text"]["content"] == "Child page", f"page-parent title shape is wrong: {payload}")
    expect("Name" not in payload["properties"] and "Status" not in payload["properties"], f"page-parent payload should not include database properties: {payload}")
    print("PASS test_page_parent_payload_uses_plain_title_property")


def test_block_payloads_are_create_safe() -> None:
    tool = load_tool()
    heading = tool.block_create_payload(
        {
            "type": "heading_4",
            "heading_4": {"rich_text": [{"plain_text": "Tiny heading"}], "color": "default"},
        }
    )
    link = tool.block_create_payload({"type": "link_preview", "link_preview": {"url": "https://example.com"}})
    breadcrumb = tool.block_create_payload({"type": "breadcrumb", "breadcrumb": {}})
    expect(heading["type"] == "heading_3", f"heading_4 should map to a supported heading: {heading}")
    expect(link == {"type": "bookmark", "bookmark": {"url": "https://example.com", "caption": []}}, f"link preview should map to bookmark: {link}")
    expect(breadcrumb["type"] == "paragraph", f"breadcrumb should become a placeholder: {breadcrumb}")
    expect("id" not in str(heading) and "id" not in str(link), "block create payloads should not preserve source ids")
    print("PASS test_block_payloads_are_create_safe")


def test_cli_is_token_file_only() -> None:
    text = TOOL_PATH.read_text(encoding="utf-8")
    expect("--source-token-file" in text and "--dest-token-file" in text and "--token-file" in text, "expected token-file arguments")
    expect("add_argument(\"--token\"" not in text and "add_argument('--token'" not in text, "tokens must not be accepted directly on argv")
    print("PASS test_cli_is_token_file_only")


def main() -> int:
    tests = [
        test_notion_id_extracts_url_and_plain_ids,
        test_property_schema_is_workspace_portable,
        test_page_properties_skip_nonportable_values,
        test_page_parent_payload_uses_plain_title_property,
        test_block_payloads_are_create_safe,
        test_cli_is_token_file_only,
    ]
    for test in tests:
        test()
    print(f"PASS all {len(tests)} notion transfer tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
