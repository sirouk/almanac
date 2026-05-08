#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
MCP_SERVER = REPO / "python" / "arclink_mcp_server.py"
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


def test_arclink_mcp_tools_advertise_actionable_input_schemas() -> None:
    mod = load_module(MCP_SERVER, "arclink_mcp_server_schema_test")
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
    expect(ssot_write["properties"]["operation"]["enum"] == ["insert", "update", "append", "create_page", "create_database"], str(ssot_write))
    expect(ssot_write["properties"]["read_after"]["default"] is False, str(ssot_write))
    expect("archive" not in ssot_write["properties"]["operation"]["enum"], str(ssot_write))
    expect("delete" not in ssot_write["properties"]["operation"]["enum"], str(ssot_write))
    expect("Required for append/update" in ssot_write["properties"]["target_id"]["description"], str(ssot_write))
    expect("configured ArcLink root page" in ssot_write["properties"]["target_id"]["description"], str(ssot_write))
    expect("children" in ssot_write["properties"]["payload"]["description"], str(ssot_write))
    expect("create_page" in ssot_write["properties"]["payload"]["description"], str(ssot_write))
    expect("create_database" in ssot_write["properties"]["payload"]["description"], str(ssot_write))
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

    knowledge_combo = mod._tool_schema("knowledge.search-and-fetch")
    expect(knowledge_combo["required"] == ["query"], str(knowledge_combo))
    expect(knowledge_combo["properties"]["search_limit"]["maximum"] == 5, str(knowledge_combo))
    expect(knowledge_combo["properties"]["vault_fetch_limit"]["maximum"] == 2, str(knowledge_combo))
    expect(knowledge_combo["properties"]["notion_fetch_limit"]["maximum"] == 3, str(knowledge_combo))
    expect(knowledge_combo["properties"]["body_char_limit"]["maximum"] == 12000, str(knowledge_combo))
    expect(knowledge_combo["properties"]["sources"]["items"]["enum"] == ["vault", "notion"], str(knowledge_combo))

    ssot_status = mod._tool_schema("ssot.status")
    expect(ssot_status["required"] == ["pending_id"], str(ssot_status))

    agent_token_tools = {
        "catalog.vaults",
        "vaults.refresh",
        "vaults.subscribe",
        "vault.search",
        "vault.fetch",
        "vault.search-and-fetch",
        "knowledge.search",
        "knowledge.search-and-fetch",
        "agents.managed-memory",
        "agents.consume-notifications",
        "shares.request",
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
    print("PASS test_arclink_mcp_tools_advertise_actionable_input_schemas")


def test_high_value_sample_calls_match_advertised_schemas() -> None:
    mod = load_module(MCP_SERVER, "arclink_mcp_server_sample_schema_test")
    samples = {
        "notion.search": {"query": "Example Unicorn", "limit": 5, "rerank": False},
        "notion.fetch": {"target_id": "https://www.notion.so/example"},
        "notion.query": {"target_id": "database-id", "query": {"filter": {}}, "limit": 25},
        "notion.search-and-fetch": {
            "query": "Example Unicorn",
            "search_limit": 5,
            "fetch_limit": 2,
            "body_char_limit": 4000,
            "rerank": False,
        },
        "vault.search": {
            "query": "Example Lattice",
            "collections": ["vault", "vault-pdf-ingest"],
            "limit": 5,
        },
        "vault.fetch": {
            "file": "vault-pdf-ingest/projects/example/lattice/lattice-paper-1-pdf.md",
            "fromLine": 1,
            "maxLines": 80,
            "lineNumbers": True,
        },
        "vault.search-and-fetch": {
            "query": "Example Lattice",
            "collections": ["vault", "vault-pdf-ingest"],
            "search_limit": 5,
            "fetch_limit": 1,
            "body_char_limit": 6000,
        },
        "knowledge.search": {
            "query": "Example Lattice",
            "sources": ["vault", "notion"],
            "limit": 5,
            "rerank": False,
        },
        "knowledge.search-and-fetch": {
            "query": "Example Lattice",
            "sources": ["vault", "notion"],
            "search_limit": 5,
            "vault_fetch_limit": 1,
            "notion_fetch_limit": 2,
            "body_char_limit": 6000,
            "rerank": False,
        },
        "shares.request": {
            "recipient_email": "recipient@example.test",
            "resource_kind": "drive",
            "resource_root": "vault",
            "resource_path": "/Projects/brief.md",
            "display_name": "Project Brief",
        },
        "ssot.write": {
            "operation": "create_page",
            "payload": {"title": "Org Notes", "children": [{"type": "paragraph", "paragraph": {"rich_text": []}}]},
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
    mod = load_module(MCP_SERVER, "arclink_mcp_server_descriptions_test")
    # Every hot rail must teach the agent when to prefer it over an overlapping rail.
    expectations = {
        "ssot.read": ("For broad knowledge lookup by phrase", "notion.search"),
        "ssot.pending": ("for a specific pending_id, call ssot.status",),
        "ssot.write": ("For cross-turn follow-up on a queued write, call ssot.status", "create_page", "create_database", "inherit org access"),
        "ssot.status": ("Prefer over ssot.pending when the pending_id is already known",),
        "notion.search": ("prefer notion.search-and-fetch when you also need the body",),
        "notion.fetch": ("Prefer over notion.search when the user already gave a URL or id",),
        "notion.query": (
            "one shared Notion database/data source",
            "exact database/data-source target",
            "do not fan out live queries",
        ),
        "notion.search-and-fetch": ("One-shot replacement", "search_limit", "fetch_limit"),
        "vault.search": ("Prefer vault.search-and-fetch when you need the body",),
        "vault.fetch": ("return plain structured text", "Prefer over raw qmd.get", "metadata block", "stays inline in text"),
        "vault.search-and-fetch": ("One-shot replacement for qmd.query followed by qmd.get", "vault-pdf-ingest", "does not rerank", "metadata block", "stays inline in text"),
        "knowledge.search": ("both vault/PDF and shared Notion", "source is unclear"),
        "knowledge.search-and-fetch": ("vault/PDF and shared Notion", "files, PDFs, cloned docs, or shared Notion pages"),
        "shares.request": ("read-only Drive/Code share", "pending for owner approval", "never shares Linked resources"),
    }
    for tool, needles in expectations.items():
        description = mod.TOOLS[tool]
        for needle in needles:
            expect(needle in description, f"{tool} description missing guidance {needle!r}: {description!r}")
    print("PASS test_hot_tool_descriptions_carry_when_to_call_guidance")


def test_runtime_helpers_close_schema_bypass_gaps() -> None:
    mod = load_module(MCP_SERVER, "arclink_mcp_server_runtime_helper_test")
    expect(mod._clamp_int(0, default=2, minimum=0, maximum=3) == 0, "fetch_limit=0 must stay zero")
    expect(mod._clamp_int("250", default=25, minimum=1, maximum=100) == 100, "limits should clamp high strings")
    expect(mod._bool_arg({"subscribed": False}, "subscribed", required=True) is False, "false boolean should stay false")
    try:
        mod._bool_arg({"subscribed": "false"}, "subscribed", required=True)
    except ValueError as exc:
        expect("must be a boolean" in str(exc), str(exc))
    else:
        raise AssertionError("string 'false' should not pass boolean runtime validation")
    parsed = mod._dict_arg({"payload": '{"children":[]}'}, "payload", required=True)
    expect(parsed == {"children": []}, f"JSON object strings should be accepted, got {parsed!r}")
    try:
        mod._dict_arg({"payload": []}, "payload", required=True)
    except ValueError as exc:
        expect("must be an object" in str(exc), str(exc))
    else:
        raise AssertionError("list payload should not pass object runtime validation")
    try:
        mod._dict_arg({"payload": '["not-an-object"]'}, "payload", required=True)
    except ValueError as exc:
        expect("must decode to an object" in str(exc), str(exc))
    else:
        raise AssertionError("JSON array string should not pass object runtime validation")
    try:
        mod._dict_arg({"payload": '{"children":'}, "payload", required=True)
    except ValueError as exc:
        expect("valid JSON object string" in str(exc), str(exc))
    else:
        raise AssertionError("malformed JSON object string should fail clearly")
    expect(mod._knowledge_sources_arg({}) == ["vault", "notion"], "default knowledge sources should include both rails")
    expect(mod._knowledge_sources_arg({"sources": ["notion", "vault", "notion"]}) == ["notion", "vault"], "knowledge sources should dedupe while preserving order")
    try:
        mod._knowledge_sources_arg({"sources": ["filesystem"]})
    except ValueError as exc:
        expect("vault and notion" in str(exc), str(exc))
    else:
        raise AssertionError("invalid knowledge source should fail clearly")
    print("PASS test_runtime_helpers_close_schema_bypass_gaps")


def test_agent_share_request_tool_creates_scoped_pending_grant() -> None:
    control = load_module(PYTHON_DIR / "arclink_control.py", "arclink_control_mcp_share_test")
    mod = load_module(MCP_SERVER, "arclink_mcp_server_share_test")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    control.ensure_schema(conn)
    control.upsert_arclink_user(
        conn,
        user_id="arcusr_share_owner",
        email="owner@example.test",
        display_name="Share Owner",
        entitlement_state="paid",
    )
    control.upsert_arclink_user(
        conn,
        user_id="arcusr_share_recipient",
        email="recipient@example.test",
        display_name="Share Recipient",
        entitlement_state="paid",
    )
    control.upsert_arclink_user(
        conn,
        user_id="arcusr_foreign_owner",
        email="foreign@example.test",
        display_name="Foreign Owner",
        entitlement_state="paid",
    )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="arcdep_share_owner",
        user_id="arcusr_share_owner",
        prefix="share-owner-1a2b",
        base_domain="example.test",
        agent_id="agent-share",
        status="active",
    )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="arcdep_foreign",
        user_id="arcusr_foreign_owner",
        prefix="foreign-owner-1a2b",
        base_domain="example.test",
        agent_id="agent-foreign",
        status="active",
    )
    token_payload = control._issue_bootstrap_token(
        conn,
        request_id=None,
        agent_id="agent-share",
        requester_identity="Share Agent",
        source_ip="127.0.0.1",
        issued_by="test",
        activate_now=True,
    )
    conn.commit()

    result = mod._create_agent_share_request(
        conn,
        {
            "token": token_payload["raw_token"],
            "recipient_email": "recipient@example.test",
            "resource_kind": "drive",
            "resource_root": "vault",
            "resource_path": "/Projects/brief.md",
            "display_name": "Project Brief",
        },
    )
    grant = result["grant"]
    expect(result["ok"] is True, str(result))
    expect(result["agent_id"] == "agent-share", str(result))
    expect(result["deployment_id"] == "arcdep_share_owner", str(result))
    expect(result["approval_required"] is True and result["recipient_acceptance_required"] is True, str(result))
    expect(grant["owner_user_id"] == "arcusr_share_owner", str(grant))
    expect(grant["recipient_user_id"] == "arcusr_share_recipient", str(grant))
    expect(grant["resource_root"] == "vault" and grant["resource_path"] == "/Projects/brief.md", str(grant))
    expect(grant["status"] == "pending_owner_approval", str(grant))
    expect(grant["reshare_allowed"] is False, str(grant))
    stored = conn.execute("SELECT metadata_json FROM arclink_share_grants WHERE grant_id = ?", (grant["grant_id"],)).fetchone()
    metadata = json.loads(stored["metadata_json"])
    expect(metadata["requested_via"] == "arclink-mcp", metadata)
    expect(metadata["requested_by_agent_id"] == "agent-share", metadata)

    try:
        mod._create_agent_share_request(
            conn,
            {
                "token": token_payload["raw_token"],
                "recipient_user_id": "arcusr_share_recipient",
                "resource_kind": "drive",
                "resource_root": "linked",
                "resource_path": "/already-linked.md",
            },
        )
    except ValueError as exc:
        expect("linked" in str(exc), str(exc))
    else:
        raise AssertionError("shares.request must reject linked-root reshare")

    try:
        mod._create_agent_share_request(
            conn,
            {
                "token": token_payload["raw_token"],
                "deployment_id": "arcdep_foreign",
                "recipient_user_id": "arcusr_share_recipient",
                "resource_kind": "drive",
                "resource_root": "vault",
                "resource_path": "/Projects/brief.md",
            },
        )
    except PermissionError as exc:
        expect("outside this agent" in str(exc), str(exc))
    else:
        raise AssertionError("shares.request must reject deployments outside the agent scope")
    print("PASS test_agent_share_request_tool_creates_scoped_pending_grant")


def test_ssot_write_result_promotes_receipt_fields() -> None:
    mod = load_module(MCP_SERVER, "arclink_mcp_server_ssot_receipt_test")
    normalized = mod._normalize_ssot_write_result(
        {
            "applied": True,
            "target_id": "page-id",
            "notion_result": {
                "id": "notion-page-id",
                "url": "https://www.notion.so/example-page",
            },
        }
    )
    expect(normalized["final_state"] == "applied", str(normalized))
    expect(normalized["url"] == "https://www.notion.so/example-page", str(normalized))
    expect(normalized["page_url"] == "https://www.notion.so/example-page", str(normalized))
    expect(normalized["result_id"] == "notion-page-id", str(normalized))
    print("PASS test_ssot_write_result_promotes_receipt_fields")


def test_search_and_fetch_compacts_search_payloads() -> None:
    mod = load_module(MCP_SERVER, "arclink_mcp_server_compact_search_test")
    indexed_file = (
        "/home/arclink/arclink/arclink-priv/state/notion-index/markdown/root/"
        "00000000000040008000000000000001-000.md"
    )
    compact = mod._compact_notion_search_result(
        {
            "ok": True,
            "query": "Example Unicorn",
            "collection": "notion",
            "index_ready": True,
            "index_doc_count": 1,
            "roots": [{"id": "root"}],
            "results": [
                {
                    "source": "index",
                    "page_id": "",
                    "page_url": "",
                    "page_title": "Example Unicorn",
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
    expect(hit["page_id"] == "00000000000040008000000000000001", str(compact))
    expect(mod._notion_search_hit_target_id({"file": indexed_file}) == "00000000000040008000000000000001", str(compact))
    expect(len(hit["snippet"]) <= 120, str(compact))
    expect(hit["snippet_truncated"] is True, str(compact))
    print("PASS test_search_and_fetch_compacts_search_payloads")


def test_vault_qmd_helpers_normalize_resource_content() -> None:
    mod = load_module(MCP_SERVER, "arclink_mcp_server_qmd_helper_test")
    compact = mod._extract_qmd_text_result(
        {
            "content": [
                {
                    "type": "resource",
                    "resource": {
                        "uri": "qmd://vault-pdf-ingest/projects/example/lattice/lattice-paper-1-pdf.md",
                        "mimeType": "text/markdown",
                        "text": "1: # Lattice\n2: Example Lattice reduces communication overhead.\n",
                    },
                }
            ]
        },
        body_char_limit=10_000,
    )
    expect(compact["ok"] is True, str(compact))
    expect(compact["uri"] == "qmd://vault-pdf-ingest/projects/example/lattice/lattice-paper-1-pdf.md", str(compact))
    expect("Example Lattice" in compact["text"], str(compact))
    expect(compact["text_truncated"] is False, str(compact))
    with_metadata = mod._extract_qmd_text_result(
        {"content": [{"type": "resource", "resource": {"text": "---\na: b\n---\n# Lattice\nBody\n"}}]},
        body_char_limit=10_000,
    )
    expect(with_metadata["metadata_present"] is True, str(with_metadata))
    expect(with_metadata["metadata_format"] == "yaml", str(with_metadata))
    expect(with_metadata["metadata_stripped"] is False, str(with_metadata))
    expect(with_metadata["metadata"] == "a: b", str(with_metadata))
    expect(with_metadata["frontmatter"] == "a: b", str(with_metadata))
    expect(with_metadata["stripped_metadata"] == "a: b", str(with_metadata))
    expect("metadata" in with_metadata["metadata_notice"], str(with_metadata))
    expect(with_metadata["text"].startswith("---\na: b\n---\n# Lattice"), str(with_metadata))

    search_args = mod._qmd_query_arguments({"query": "Example Lattice"})
    expect(search_args["collections"] == ["vault", "vault-pdf-ingest"], str(search_args))
    expect(search_args["searches"][0] == {"type": "lex", "query": "Example Lattice"}, str(search_args))
    expect(search_args["searches"][1] == {"type": "vec", "query": "Example Lattice"}, str(search_args))
    expect(search_args["rerank"] is False, str(search_args))
    expect(mod._qmd_query_arguments({"query": "Example Lattice", "rerank": True})["rerank"] is False, "vault bridge must ignore rerank")
    expect(len(mod._qmd_query_arguments({"query": "Example Lattice"}, include_vec=False)["searches"]) == 1, "lex fallback should be possible")
    print("PASS test_vault_qmd_helpers_normalize_resource_content")


def test_notion_index_fallback_returns_qmd_markdown_body() -> None:
    mod = load_module(MCP_SERVER, "arclink_mcp_server_notion_qmd_fallback_test")
    calls: list[tuple[str, dict]] = []

    def fake_mcp_tool_call(url: str, tool: str, args: dict, **_kwargs):
        calls.append((tool, args))
        expect(url == "http://qmd.example/mcp", url)
        expect(tool == "get", tool)
        expect(args["file"] == "notion-shared/root/replay-page.md", str(args))
        return {
            "content": [
                {
                    "type": "resource",
                    "resource": {
                        "uri": "qmd://notion-shared/root/replay-page.md",
                        "mimeType": "text/markdown",
                        "text": "# Replay Page\n\nARCLINK_REPLAY_NOTION_DRI stays retrievable from the index.",
                    },
                }
            ]
        }

    mod._mcp_tool_call = fake_mcp_tool_call
    fetched = mod._qmd_fetch_notion_index_file(
        SimpleNamespace(qmd_url="http://qmd.example/mcp"),
        {"body_char_limit": 1000},
        file_value="notion-shared/root/replay-page.md",
    )
    expect(calls, "qmd get should be called")
    expect(fetched["target_kind"] == "indexed-markdown", str(fetched))
    expect(fetched["fetch_source"] == "qmd-index-fallback", str(fetched))
    expect("ARCLINK_REPLAY_NOTION_DRI" in fetched["markdown"], str(fetched))
    print("PASS test_notion_index_fallback_returns_qmd_markdown_body")


def test_vault_source_metadata_adapts_to_vault_roots_repos_and_pdf_sidecars() -> None:
    mod = load_module(MCP_SERVER, "arclink_mcp_server_source_metadata_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        vault_dir = root / "knowledge-base"
        state_dir = root / "state"
        repo_dir = vault_dir / "TeamDocs"
        repo_dir.mkdir(parents=True)
        (repo_dir / ".vault").write_text(
            "name: Team Knowledge\ncategory: docs\nowner: engineering\ndefault_subscribed: true\n",
            encoding="utf-8",
        )
        (repo_dir / "README.md").write_text("# Team Docs\n\nRetrieval source.\n", encoding="utf-8")
        subprocess.run(["git", "init", "-b", "main", str(repo_dir)], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", "ArcLink Test"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(repo_dir), "config", "user.email", "arclink-test@example.com"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(repo_dir), "remote", "add", "origin", "https://github.com/example/team-docs.git"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(repo_dir), "add", "README.md", ".vault"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(repo_dir), "commit", "-m", "seed"], check=True, capture_output=True, text=True)

        cfg = SimpleNamespace(vault_dir=vault_dir.resolve(), state_dir=state_dir.resolve())
        direct = mod._vault_source_metadata(
            cfg,
            "qmd://vault/TeamDocs/README.md",
            include_hash=True,
            include_repo_details=True,
        )
        expect(direct["vault_dir_name"] == "knowledge-base", str(direct))
        expect(direct["nearest_vault_root"]["name"] == "Team Knowledge", str(direct))
        expect(direct["nearest_vault_root"]["rel_path"] == "TeamDocs", str(direct))
        expect(direct["is_git_repo"] is True, str(direct))
        expect(direct["repo"]["remote_origin"] == "https://github.com/example/team-docs.git", str(direct))
        expect(direct["repo"]["branch"] == "main", str(direct))
        expect(direct["repo"]["commit"], str(direct))
        expect(len(direct["source_sha256"]) == 64, str(direct))
        displayed = mod._vault_source_metadata(
            cfg,
            "qmd://vault/TeamDocs/README.md",
            include_hash=False,
            include_repo_details=True,
            display_vault_root="/home/alice/ArcLink",
        )
        expect(displayed["vault_root_path"] == "/home/alice/ArcLink", str(displayed))
        expect(displayed["source_host_path"] == "/home/alice/ArcLink/TeamDocs/README.md", str(displayed))
        expect(displayed["nearest_vault_root"]["host_path"] == "/home/alice/ArcLink/TeamDocs", str(displayed))
        expect(displayed["repo"]["root_host_path"] == "/home/alice/ArcLink/TeamDocs", str(displayed))

        lowercased_qmd_path = mod._vault_source_metadata(
            cfg,
            "qmd://vault/teamdocs/readme.md",
            include_hash=False,
            include_repo_details=True,
            display_vault_root="/home/alice/ArcLink",
        )
        expect(lowercased_qmd_path["source_exists"] is True, str(lowercased_qmd_path))
        expect(lowercased_qmd_path["source_rel_path"] == "TeamDocs/README.md", str(lowercased_qmd_path))
        expect(lowercased_qmd_path["source_host_path"] == "/home/alice/ArcLink/TeamDocs/README.md", str(lowercased_qmd_path))

        pdf_source = vault_dir / "Research" / "Example Lattice Paper.pdf"
        pdf_source.parent.mkdir(parents=True)
        pdf_source.write_bytes(b"%PDF-pretend")
        generated = state_dir / "pdf-ingest" / "markdown" / "Research" / "Example Lattice Paper-pdf.md"
        generated.parent.mkdir(parents=True)
        generated.write_text(
            "---\n"
            "arclink_generated: true\n"
            "arclink_source_type: pdf\n"
            "source_rel_path: 'Research/Example Lattice Paper.pdf'\n"
            "source_sha256: 'upstream-sha'\n"
            "---\n"
            "# Example Lattice Paper\n",
            encoding="utf-8",
        )
        pdf_meta = mod._vault_source_metadata(cfg, "qmd://vault-pdf-ingest/Research/Example Lattice Paper-pdf.md", include_hash=False)
        expect(pdf_meta["generated"] is True, str(pdf_meta))
        expect(pdf_meta["source_type"] == "pdf", str(pdf_meta))
        expect(pdf_meta["source_rel_path"] == "Research/Example Lattice Paper.pdf", str(pdf_meta))
        expect(pdf_meta["generated_metadata"]["generated_markdown_rel_path"] == "Research/Example Lattice Paper-pdf.md", str(pdf_meta))
        expect(pdf_meta["source_exists"] is True, str(pdf_meta))

        manifest = state_dir / "pdf-ingest" / "manifest.sqlite3"
        conn = sqlite3.connect(manifest)
        conn.execute(
            """
            CREATE TABLE pdf_ingest_manifest (
              source_rel_path TEXT PRIMARY KEY,
              source_abs_path TEXT NOT NULL,
              generated_abs_path TEXT NOT NULL,
              source_sha256 TEXT,
              source_size INTEGER NOT NULL,
              source_mtime INTEGER NOT NULL,
              extractor TEXT,
              pipeline_signature TEXT,
              status TEXT NOT NULL,
              error TEXT,
              updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO pdf_ingest_manifest (
              source_rel_path, source_abs_path, generated_abs_path, source_sha256,
              source_size, source_mtime, extractor, pipeline_signature, status, error, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ok', NULL, ?)
            """,
            (
                "Research/Example Lattice Paper.pdf",
                str(pdf_source),
                str(generated),
                "manifest-sha",
                12,
                42,
                "pdftotext",
                "pipeline",
                "2026-04-24T00:00:00Z",
            ),
        )
        conn.commit()
        conn.close()
        normalized_pdf_meta = mod._vault_source_metadata(
            cfg,
            "qmd://vault-pdf-ingest/research/example-lattice-paper-pdf.md",
            include_hash=False,
        )
        expect(normalized_pdf_meta["source_type"] == "pdf", str(normalized_pdf_meta))
        expect(normalized_pdf_meta["source_rel_path"] == "Research/Example Lattice Paper.pdf", str(normalized_pdf_meta))
        expect(normalized_pdf_meta["generated_metadata"]["source_sha256"] == "manifest-sha", str(normalized_pdf_meta))
    print("PASS test_vault_source_metadata_adapts_to_vault_roots_repos_and_pdf_sidecars")


def main() -> int:
    test_arclink_mcp_tools_advertise_actionable_input_schemas()
    test_high_value_sample_calls_match_advertised_schemas()
    test_tools_list_serves_rich_schemas_not_empty_objects()
    test_hot_tool_descriptions_carry_when_to_call_guidance()
    test_runtime_helpers_close_schema_bypass_gaps()
    test_agent_share_request_tool_creates_scoped_pending_grant()
    test_ssot_write_result_promotes_receipt_fields()
    test_search_and_fetch_compacts_search_payloads()
    test_vault_qmd_helpers_normalize_resource_content()
    test_notion_index_fallback_returns_qmd_markdown_body()
    test_vault_source_metadata_adapts_to_vault_roots_repos_and_pdf_sidecars()
    print("PASS all 11 ArcLink MCP schema tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
