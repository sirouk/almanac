#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MCP_SERVER = REPO / "python" / "almanac_mcp_server.py"
PYTHON_DIR = REPO / "python"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_module(path: Path, name: str):
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def assert_sample_matches_outer_schema(schema: dict, sample: dict, name: str) -> None:
    properties = schema.get("properties") or {}
    unknown = set(sample) - set(properties)
    expect(not unknown, f"{name} sample uses unknown args {sorted(unknown)}: {schema}")
    missing = [key for key in schema.get("required", []) if key not in sample]
    expect(not missing, f"{name} sample missing required args {missing}: {sample}")
    for key, value in sample.items():
        enum = properties.get(key, {}).get("enum")
        if enum:
            expect(value in enum, f"{name}.{key}={value!r} not in enum {enum}")


def test_almanac_mcp_tools_advertise_actionable_input_schemas() -> None:
    mod = load_module(MCP_SERVER, "almanac_mcp_server_schema_test")
    expect(set(mod.TOOLS) == set(mod.TOOL_SCHEMAS), f"schema/tool drift: {set(mod.TOOLS) ^ set(mod.TOOL_SCHEMAS)}")
    disallowed_top_level = {"oneOf", "anyOf", "allOf", "enum", "not"}
    for name in mod.TOOLS:
        schema = mod._tool_schema(name)
        expect(schema.get("type") == "object", f"{name} schema must be object: {schema}")
        expect("properties" in schema, f"{name} missing properties: {schema}")
        expect(schema.get("additionalProperties") is False, f"{name} should not be open-ended: {schema}")
        found = sorted(disallowed_top_level & set(schema))
        expect(not found, f"{name} uses top-level OpenAI-incompatible JSONSchema keys {found}: {schema}")

    ssot_write = mod._tool_schema("ssot.write")
    expect(ssot_write["required"] == ["operation", "payload"], str(ssot_write))
    expect(ssot_write["properties"]["operation"]["enum"] == ["insert", "update", "append"], str(ssot_write))
    expect(ssot_write["properties"]["read_after"]["default"] is False, str(ssot_write))
    expect("archive" not in ssot_write["properties"]["operation"]["enum"], str(ssot_write))
    expect("delete" not in ssot_write["properties"]["operation"]["enum"], str(ssot_write))
    expect("Required for append/update" in ssot_write["properties"]["target_id"]["description"], str(ssot_write))
    expect("children" in ssot_write["properties"]["payload"]["description"], str(ssot_write))
    expect("Harness-injected" in ssot_write["properties"]["token"]["description"], str(ssot_write))

    notion_combo = mod._tool_schema("notion.search-and-fetch")
    expect(notion_combo["required"] == ["query"], str(notion_combo))
    expect(notion_combo["properties"]["fetch_limit"]["maximum"] == 3, str(notion_combo))
    expect(notion_combo["properties"]["body_char_limit"]["maximum"] == 12000, str(notion_combo))

    vault_combo = mod._tool_schema("vault.search-and-fetch")
    expect(vault_combo["required"] == ["query"], str(vault_combo))
    expect(vault_combo["properties"]["search_limit"]["maximum"] == 5, str(vault_combo))
    expect(vault_combo["properties"]["fetch_limit"]["maximum"] == 2, str(vault_combo))
    expect(vault_combo["properties"]["fetch_limit"]["default"] == 1, str(vault_combo))
    expect(vault_combo["properties"]["body_char_limit"]["maximum"] == 12000, str(vault_combo))
    expect(vault_combo["properties"]["lineNumbers"]["default"] is False, str(vault_combo))
    expect("rerank" not in vault_combo["properties"], str(vault_combo))

    ssot_status = mod._tool_schema("ssot.status")
    expect(ssot_status["required"] == ["pending_id"], str(ssot_status))

    agent_token_tools = {
        "catalog.vaults",
        "vaults.refresh",
        "vaults.subscribe",
        "vault.search",
        "vault.fetch",
        "vault.search-and-fetch",
        "agents.managed-memory",
        "agents.consume-notifications",
        "ssot.read",
        "ssot.pending",
        "ssot.status",
        "ssot.write",
        "notion.search",
        "notion.fetch",
        "notion.query",
        "notion.search-and-fetch",
    }
    for tool_name in agent_token_tools:
        schema = mod._tool_schema(tool_name)
        expect("token" in schema["properties"], str(schema))
        expect("token" not in schema["required"], f"{tool_name} should rely on harness token injection: {schema}")

    operator_schema = mod._tool_schema("bootstrap.approve")
    expect(operator_schema["properties"]["surface"]["enum"] == ["curator-channel", "curator-tui", "ctl"], str(operator_schema))
    expect(operator_schema["required"] == ["operator_token", "request_id"], str(operator_schema))
    print("PASS test_almanac_mcp_tools_advertise_actionable_input_schemas")


def test_high_value_sample_calls_match_advertised_schemas() -> None:
    mod = load_module(MCP_SERVER, "almanac_mcp_server_sample_schema_test")
    samples = {
        "notion.search": {"query": "Chutes Unicorn", "limit": 5, "rerank": False},
        "notion.fetch": {"target_id": "https://www.notion.so/example"},
        "notion.query": {"target_id": "database-id", "query": {"filter": {}}, "limit": 25},
        "notion.search-and-fetch": {
            "query": "Chutes Unicorn",
            "search_limit": 5,
            "fetch_limit": 2,
            "body_char_limit": 4000,
            "rerank": False,
        },
        "vault.search": {
            "query": "Chutes MESH",
            "collections": ["vault", "vault-pdf-ingest"],
            "limit": 5,
        },
        "vault.fetch": {
            "file": "vault-pdf-ingest/projects/chutes/mesh/mesh-paper-1-pdf.md",
            "fromLine": 1,
            "maxLines": 80,
            "lineNumbers": True,
        },
        "vault.search-and-fetch": {
            "query": "Chutes MESH",
            "collections": ["vault", "vault-pdf-ingest"],
            "search_limit": 5,
            "fetch_limit": 1,
            "body_char_limit": 6000,
        },
        "ssot.write": {
            "operation": "append",
            "target_id": "page-id",
            "payload": {"children": [{"type": "paragraph"}]},
            "read_after": True,
        },
        "ssot.status": {"pending_id": "ssotw_123"},
    }
    for name, sample in samples.items():
        assert_sample_matches_outer_schema(mod._tool_schema(name), sample, name)
    print("PASS test_high_value_sample_calls_match_advertised_schemas")


def test_tools_list_serves_rich_schemas_not_empty_objects() -> None:
    body = MCP_SERVER.read_text(encoding="utf-8")
    expect('"inputSchema": _tool_schema(name)' in body, body)
    expect('"inputSchema": {"type": "object"}' not in body, body)
    print("PASS test_tools_list_serves_rich_schemas_not_empty_objects")


def test_hot_tool_descriptions_carry_when_to_call_guidance() -> None:
    mod = load_module(MCP_SERVER, "almanac_mcp_server_descriptions_test")
    # Every hot rail must teach the agent when to prefer it over an overlapping rail.
    expectations = {
        "ssot.read": ("For broad knowledge lookup by phrase", "notion.search"),
        "ssot.pending": ("for a specific pending_id, call ssot.status",),
        "ssot.write": ("For cross-turn follow-up on a queued write, call ssot.status",),
        "ssot.status": ("Prefer over ssot.pending when the pending_id is already known",),
        "notion.search": ("prefer notion.search-and-fetch when you also need the body",),
        "notion.fetch": ("Prefer over notion.search when the user already gave a URL or id",),
        "notion.query": ("Prefer for owner/status/due/assignee filters",),
        "notion.search-and-fetch": ("One-shot replacement", "search_limit", "fetch_limit"),
        "vault.search": ("Prefer vault.search-and-fetch when you need the body",),
        "vault.fetch": ("return plain structured text", "Prefer over raw qmd.get"),
        "vault.search-and-fetch": ("One-shot replacement for qmd.query followed by qmd.get", "vault-pdf-ingest", "does not rerank"),
    }
    for tool, needles in expectations.items():
        description = mod.TOOLS[tool]
        for needle in needles:
            expect(needle in description, f"{tool} description missing guidance {needle!r}: {description!r}")
    print("PASS test_hot_tool_descriptions_carry_when_to_call_guidance")


def test_runtime_helpers_close_schema_bypass_gaps() -> None:
    mod = load_module(MCP_SERVER, "almanac_mcp_server_runtime_helper_test")
    expect(mod._clamp_int(0, default=2, minimum=0, maximum=3) == 0, "fetch_limit=0 must stay zero")
    expect(mod._clamp_int("250", default=25, minimum=1, maximum=100) == 100, "limits should clamp high strings")
    expect(mod._bool_arg({"subscribed": False}, "subscribed", required=True) is False, "false boolean should stay false")
    try:
        mod._bool_arg({"subscribed": "false"}, "subscribed", required=True)
    except ValueError as exc:
        expect("must be a boolean" in str(exc), str(exc))
    else:
        raise AssertionError("string 'false' should not pass boolean runtime validation")
    try:
        mod._dict_arg({"payload": []}, "payload", required=True)
    except ValueError as exc:
        expect("must be an object" in str(exc), str(exc))
    else:
        raise AssertionError("list payload should not pass object runtime validation")
    print("PASS test_runtime_helpers_close_schema_bypass_gaps")


def test_search_and_fetch_compacts_search_payloads() -> None:
    mod = load_module(MCP_SERVER, "almanac_mcp_server_compact_search_test")
    indexed_file = (
        "/home/almanac/almanac/almanac-priv/state/notion-index/markdown/root/"
        "3497afdeade580e2a3ade527c8b42249-000.md"
    )
    compact = mod._compact_notion_search_result(
        {
            "ok": True,
            "query": "Chutes Unicorn",
            "collection": "notion",
            "index_ready": True,
            "index_doc_count": 1,
            "roots": [{"id": "root"}],
            "results": [
                {
                    "source": "index",
                    "page_id": "",
                    "page_url": "",
                    "page_title": "Chutes Unicorn",
                    "file": indexed_file,
                    "snippet": "x" * 900,
                    "raw_result": {"content": "y" * 5000},
                }
            ],
        },
        snippet_char_limit=120,
    )
    hit = compact["results"][0]
    expect("raw_result" not in hit, str(compact))
    expect(hit["page_id"] == "3497afdeade580e2a3ade527c8b42249", str(compact))
    expect(mod._notion_search_hit_target_id({"file": indexed_file}) == "3497afdeade580e2a3ade527c8b42249", str(compact))
    expect(len(hit["snippet"]) <= 120, str(compact))
    expect(hit["snippet_truncated"] is True, str(compact))
    print("PASS test_search_and_fetch_compacts_search_payloads")


def test_vault_qmd_helpers_normalize_resource_content() -> None:
    mod = load_module(MCP_SERVER, "almanac_mcp_server_qmd_helper_test")
    compact = mod._extract_qmd_text_result(
        {
            "content": [
                {
                    "type": "resource",
                    "resource": {
                        "uri": "qmd://vault-pdf-ingest/projects/chutes/mesh/mesh-paper-1-pdf.md",
                        "mimeType": "text/markdown",
                        "text": "1: # Mesh\n2: Chutes MESH reduces communication overhead.\n",
                    },
                }
            ]
        },
        body_char_limit=10_000,
    )
    expect(compact["ok"] is True, str(compact))
    expect(compact["uri"] == "qmd://vault-pdf-ingest/projects/chutes/mesh/mesh-paper-1-pdf.md", str(compact))
    expect("Chutes MESH" in compact["text"], str(compact))
    expect(compact["text_truncated"] is False, str(compact))
    stripped = mod._extract_qmd_text_result(
        {"content": [{"type": "resource", "resource": {"text": "---\na: b\n---\n# Mesh\nBody\n"}}]},
        body_char_limit=10_000,
    )
    expect(stripped["metadata_stripped"] is True, str(stripped))
    expect(stripped["text"].startswith("# Mesh"), str(stripped))

    search_args = mod._qmd_query_arguments({"query": "Chutes MESH"})
    expect(search_args["collections"] == ["vault", "vault-pdf-ingest"], str(search_args))
    expect(search_args["searches"][0] == {"type": "lex", "query": "Chutes MESH"}, str(search_args))
    expect(search_args["searches"][1] == {"type": "vec", "query": "Chutes MESH"}, str(search_args))
    expect(search_args["rerank"] is False, str(search_args))
    expect(mod._qmd_query_arguments({"query": "Chutes MESH", "rerank": True})["rerank"] is False, "vault bridge must ignore rerank")
    expect(len(mod._qmd_query_arguments({"query": "Chutes MESH"}, include_vec=False)["searches"]) == 1, "lex fallback should be possible")
    print("PASS test_vault_qmd_helpers_normalize_resource_content")


def main() -> int:
    test_almanac_mcp_tools_advertise_actionable_input_schemas()
    test_high_value_sample_calls_match_advertised_schemas()
    test_tools_list_serves_rich_schemas_not_empty_objects()
    test_hot_tool_descriptions_carry_when_to_call_guidance()
    test_runtime_helpers_close_schema_bypass_gaps()
    test_search_and_fetch_compacts_search_payloads()
    test_vault_qmd_helpers_normalize_resource_content()
    print("PASS all 7 Almanac MCP schema tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
