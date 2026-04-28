#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONTROL_PY = REPO / "python" / "almanac_control.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_config(path: Path, values: dict[str, str]) -> None:
    lines = [f"{key}={json.dumps(value)}" for key, value in values.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def config_values(root: Path) -> dict[str, str]:
    return {
        "ALMANAC_USER": "almanac",
        "ALMANAC_HOME": str(root / "home-almanac"),
        "ALMANAC_REPO_DIR": str(REPO),
        "ALMANAC_PRIV_DIR": str(root / "priv"),
        "STATE_DIR": str(root / "state"),
        "RUNTIME_DIR": str(root / "state" / "runtime"),
        "VAULT_DIR": str(root / "vault"),
        "ALMANAC_DB_PATH": str(root / "state" / "almanac-control.sqlite3"),
        "ALMANAC_AGENTS_STATE_DIR": str(root / "state" / "agents"),
        "ALMANAC_CURATOR_DIR": str(root / "state" / "curator"),
        "ALMANAC_CURATOR_MANIFEST": str(root / "state" / "curator" / "manifest.json"),
        "ALMANAC_CURATOR_HERMES_HOME": str(root / "state" / "curator" / "hermes-home"),
        "ALMANAC_ARCHIVED_AGENTS_DIR": str(root / "state" / "archived-agents"),
        "ALMANAC_RELEASE_STATE_FILE": str(root / "state" / "almanac-release.json"),
        "ALMANAC_QMD_URL": "http://127.0.0.1:8181/mcp",
        "ALMANAC_MCP_HOST": "127.0.0.1",
        "ALMANAC_MCP_PORT": "8282",
        "ALMANAC_SSOT_NOTION_ROOT_PAGE_URL": "https://www.notion.so/workspace-root-aaaaaaaaaaaabbbbbbbbbbbbbbbb",
        "ALMANAC_SSOT_NOTION_ROOT_PAGE_ID": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "ALMANAC_SSOT_NOTION_SPACE_URL": "https://www.notion.so/workspace-root-aaaaaaaaaaaabbbbbbbbbbbbbbbb",
        "ALMANAC_SSOT_NOTION_SPACE_ID": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "ALMANAC_SSOT_NOTION_SPACE_KIND": "page",
        "ALMANAC_SSOT_NOTION_TOKEN": "secret_test",
        "ALMANAC_SSOT_NOTION_API_VERSION": "2026-03-11",
        "ALMANAC_NOTION_INDEX_ROOTS": "https://www.notion.so/workspace-root-aaaaaaaaaaaabbbbbbbbbbbbbbbb",
        "ALMANAC_NOTION_INDEX_COLLECTION_NAME": "notion-shared",
        "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "tui-only",
        "OPERATOR_NOTIFY_CHANNEL_ID": "",
        "ALMANAC_MODEL_PRESET_CODEX": "openai:codex",
        "ALMANAC_MODEL_PRESET_OPUS": "anthropic:claude-opus",
        "ALMANAC_MODEL_PRESET_CHUTES": "chutes:model-router",
        "ALMANAC_CURATOR_CHANNELS": "tui-only",
        "ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "0",
        "ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED": "0",
    }


def insert_agent(mod, conn, *, agent_id: str, unix_user: str, display_name: str = "Alex") -> None:
    now = mod.utc_now_iso()
    conn.execute(
        """
        INSERT INTO agents (
          agent_id, role, unix_user, display_name, status, hermes_home, manifest_path,
          archived_state_path, model_preset, model_string, channels_json,
          allowed_mcps_json, home_channel_json, operator_notify_channel_json,
          notes, created_at, last_enrolled_at
        ) VALUES (?, 'user', ?, ?, 'active', ?, ?, NULL, 'codex', 'openai:codex', '["tui-only"]', '[]', '{}', '{}', '', ?, ?)
        """,
        (
            agent_id,
            unix_user,
            display_name,
            str(Path("/home") / unix_user / ".local" / "share" / "almanac-agent" / "hermes-home"),
            str(Path("/tmp") / f"{agent_id}-manifest.json"),
            now,
            now,
        ),
    )
    conn.commit()


def _title_property(title: str) -> dict[str, object]:
    return {
        "Name": {
            "type": "title",
            "title": [
                {
                    "plain_text": title,
                    "type": "text",
                    "text": {"content": title},
                }
            ],
        }
    }


def test_sync_shared_notion_index_indexes_page_tree_into_qmd_markdown_docs() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_notion_index_sync_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            root_page_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            child_page_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
            refresh_calls: list[bool] = []

            mod._resolve_notion_index_roots = lambda **kwargs: [
                {
                    "root_ref": "https://www.notion.so/workspace-root-aaaaaaaaaaaabbbbbbbbbbbbbbbb",
                    "root_kind": "page",
                    "root_id": root_page_id,
                    "root_url": "https://www.notion.so/workspace-root-aaaaaaaaaaaabbbbbbbbbbbbbbbb",
                    "root_title": "Workspace Root",
                    "root_page_id": root_page_id,
                    "root_page_url": "https://www.notion.so/workspace-root-aaaaaaaaaaaabbbbbbbbbbbbbbbb",
                    "root_page_title": "Workspace Root",
                }
            ]
            mod.retrieve_notion_page = lambda **kwargs: (
                {
                    "id": root_page_id,
                    "url": "https://www.notion.so/workspace-root-aaaaaaaaaaaabbbbbbbbbbbbbbbb",
                    "last_edited_time": "2026-04-21T12:00:00+00:00",
                    "properties": _title_property("Workspace Root"),
                }
                if kwargs["page_id"] == root_page_id
                else {
                    "id": child_page_id,
                    "url": "https://www.notion.so/example-unicorn-bbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                    "last_edited_time": "2026-04-21T12:05:00+00:00",
                    "properties": {
                        **_title_property("Example Unicorn"),
                        "Owner": {
                            "type": "people",
                            "people": [{"name": "Alex"}],
                        },
                    },
                }
            )
            mod.list_notion_block_children_all = lambda **kwargs: (
                [{"type": "child_page", "id": child_page_id}]
                if kwargs["block_id"] == root_page_id
                else (
                    [
                        {
                            "id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
                            "type": "file",
                            "has_children": False,
                            "file": {
                                "type": "file",
                                "name": "roadmap.txt",
                                "caption": [{"plain_text": "Roadmap attachment"}],
                                "file": {"url": "https://files.example/roadmap.txt"},
                            },
                        }
                    ]
                    if kwargs["block_id"] == child_page_id
                    else []
                )
            )
            mod.retrieve_notion_page_markdown = lambda **kwargs: (
                {"markdown": "# Overview\n\nRoot note"} if kwargs["page_id"] == root_page_id else {"markdown": "# Summary\n\nUnicorn details\n\n## Activity\n\nFresh updates"}
            )
            mod._extract_notion_attachment_text = lambda ref: {
                "status": "extracted",
                "body": "Roadmap attachment\n\nDetailed milestones and owners",
                "content_type": "text/plain",
            }
            mod._refresh_qmd_after_notion_sync = lambda cfg, embed=False: refresh_calls.append(bool(embed))

            result = mod.sync_shared_notion_index(conn, cfg, full=True, actor="test")
            expect(result["ok"] is True and result["status"] == "ok", str(result))
            expect(result["changed_docs"] == 4, str(result))
            expect(result["collection"] == "notion-shared", str(result))
            expect(result["processed_roots"] == [root_page_id], str(result))
            expect(refresh_calls == [True], str(refresh_calls))

            rows = conn.execute(
                """
                SELECT source_page_id, page_title, section_heading, source_kind, file_path
                FROM notion_index_documents
                ORDER BY source_page_id, section_ordinal
                """
            ).fetchall()
            expect(len(rows) == 4, str([dict(row) for row in rows]))
            page_ids = [str(row["source_page_id"]) for row in rows]
            expect(page_ids.count(root_page_id) == 1, str(page_ids))
            expect(page_ids.count(child_page_id) == 3, str(page_ids))
            expect(any(str(row["source_kind"]) == "attachment" for row in rows), str([dict(row) for row in rows]))

            attachment_row = next(row for row in rows if str(row["source_kind"]) == "attachment")
            indexed_file = Path(str(attachment_row["file_path"]))
            expect(indexed_file.is_file(), f"expected indexed markdown file at {indexed_file}")
            indexed_body = indexed_file.read_text(encoding="utf-8")
            expect("Roadmap attachment" in indexed_body, indexed_body)
            expect("Attachment name: roadmap.txt" in indexed_body, indexed_body)
            expect("Breadcrumb: Workspace Root > Example Unicorn" in indexed_body, indexed_body)
            print("PASS test_sync_shared_notion_index_indexes_page_tree_into_qmd_markdown_docs")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_notion_search_fetch_and_query_use_shared_index_and_live_reads() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_notion_knowledge_tools_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_agent(mod, conn, agent_id="agent-test", unix_user="alex")

            root_page_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            page_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
            database_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
            data_source_id = "dddddddd-dddd-dddd-dddd-dddddddddddd"
            file_path = mod._notion_index_markdown_dir(cfg) / mod._notion_index_doc_relative_path(root_page_id, page_id, 0)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            body = mod._render_notion_index_section_document(
                page_title="Example Unicorn",
                page_url="https://www.notion.so/example-unicorn-bbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                page_id=page_id,
                root_title="Workspace Root",
                root_id=root_page_id,
                breadcrumb=["Workspace Root", "Projects", "Example Unicorn"],
                section_heading="Summary",
                owners=["Alex"],
                last_edited_time="2026-04-21T12:05:00+00:00",
                body="Unicorn details",
            )
            mod._upsert_notion_index_document(
                conn,
                doc_key=mod._notion_index_doc_key(root_page_id, page_id, 0),
                root_id=root_page_id,
                source_page_id=page_id,
                source_page_url="https://www.notion.so/example-unicorn-bbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                source_kind="page",
                file_path=file_path,
                page_title="Example Unicorn",
                section_heading="Summary",
                section_ordinal=0,
                breadcrumb=["Workspace Root", "Projects", "Example Unicorn"],
                owners=["Alex"],
                last_edited_time="2026-04-21T12:05:00+00:00",
                content=body,
            )
            conn.commit()

            mod._resolve_notion_index_roots = lambda **kwargs: [
                {
                    "root_ref": "root-page",
                    "root_kind": "page",
                    "root_id": root_page_id,
                    "root_url": "https://www.notion.so/workspace-root-aaaaaaaaaaaabbbbbbbbbbbbbbbb",
                    "root_title": "Workspace Root",
                    "root_page_id": root_page_id,
                    "root_page_url": "https://www.notion.so/workspace-root-aaaaaaaaaaaabbbbbbbbbbbbbbbb",
                    "root_page_title": "Workspace Root",
                },
                {
                    "root_ref": "root-db",
                    "root_kind": "database",
                    "root_id": database_id,
                    "root_url": "https://www.notion.so/database-cccccccccccccccccccccccccccc",
                    "root_title": "Project Tracker",
                    "root_page_id": root_page_id,
                    "root_page_url": "https://www.notion.so/workspace-root-aaaaaaaaaaaabbbbbbbbbbbbbbbb",
                    "root_page_title": "Workspace Root",
                },
            ]
            mcp_search_calls: list[dict] = []

            def fake_mcp_call(url, method, arguments):
                mcp_search_calls.append({"url": url, "method": method, "arguments": dict(arguments)})
                return {
                    "results": [
                        {
                            "file": f"qmd://notion-shared/{file_path.relative_to(mod._notion_index_markdown_dir(cfg)).as_posix()}",
                            "score": 0.92,
                            "snippet": "Unicorn details",
                        }
                    ]
                }

            mod.mcp_call = fake_mcp_call
            mod.resolve_notion_target = lambda **kwargs: (
                {"kind": "database", "id": database_id, "url": "https://www.notion.so/database-cccccccccccccccccccccccccccc", "title": "Project Tracker"}
                if kwargs["target_id"] == database_id
                else (
                    {"kind": "data_source", "id": data_source_id, "url": "", "title": "Project Tracker"}
                    if kwargs["target_id"] == data_source_id
                    else {"kind": "page", "id": page_id, "url": "https://www.notion.so/example-unicorn-bbbbbbbbbbbbbbbbbbbbbbbbbbbb", "title": "Example Unicorn"}
                )
            )
            mod.retrieve_notion_page = lambda **kwargs: {
                "id": page_id,
                "url": "https://www.notion.so/example-unicorn-bbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "last_edited_time": "2026-04-21T12:05:00+00:00",
                "properties": _title_property("Example Unicorn"),
            }
            mod.retrieve_notion_page_markdown = lambda **kwargs: {"markdown": "# Summary\n\nUnicorn details"}
            mod.list_notion_block_children_all = lambda **kwargs: (
                [
                    {
                        "id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
                        "type": "file",
                        "has_children": False,
                        "file": {
                            "type": "file",
                            "name": "brief.txt",
                            "caption": [{"plain_text": "Live file ref"}],
                            "file": {"url": "https://files.example/brief.txt"},
                        },
                    }
                ]
                if kwargs["block_id"] == page_id
                else []
            )
            mod.retrieve_notion_database = lambda **kwargs: {
                "id": database_id,
                "title": [{"plain_text": "Project Tracker"}],
                "data_sources": [{"id": data_source_id}],
                "properties": {"Name": {"type": "title"}},
            }
            mod.retrieve_notion_data_source = lambda **kwargs: {
                "id": data_source_id,
                "parent": {"type": "database_id", "database_id": database_id},
                "title": [{"plain_text": "Project Tracker"}],
                "properties": {"Status": {"type": "status"}},
            }
            mod.query_notion_data_source = lambda **kwargs: {
                "results": [
                    {
                        "id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
                        "properties": {
                            **_title_property("Draft docs"),
                            "Status": {"type": "status", "status": {"name": "In Progress"}},
                        },
                    }
                ],
                "has_more": False,
                "next_cursor": None,
            }
            mod.query_notion_collection = lambda **kwargs: {
                "query_kind": "data_source",
                "database": {"id": database_id, "title": [{"plain_text": "Project Tracker"}]},
                "data_source_id": data_source_id,
                "result": {
                    "results": [
                        {
                            "id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
                            "properties": {
                                **_title_property("Draft docs"),
                                "Status": {"type": "status", "status": {"name": "In Progress"}},
                            },
                        }
                    ],
                    "has_more": False,
                    "next_cursor": None,
                },
            }

            search_result = mod.notion_search(
                conn,
                cfg,
                agent_id="agent-test",
                query_text="Unicorn",
                requested_by_actor="test",
            )
            expect(search_result["ok"] is True, str(search_result))
            expect(search_result["results"][0]["page_title"] == "Example Unicorn", str(search_result))
            expect(search_result["results"][0]["breadcrumb"] == ["Workspace Root", "Projects", "Example Unicorn"], str(search_result))
            expect(search_result["results"][0]["source"] == "index", str(search_result))
            expect(len(mcp_search_calls) == 1, str(mcp_search_calls))
            expect(mcp_search_calls[0]["arguments"].get("rerank") is False, str(mcp_search_calls[0]))

            reranked_result = mod.notion_search(
                conn,
                cfg,
                agent_id="agent-test",
                query_text="Unicorn",
                rerank=True,
                requested_by_actor="test",
            )
            expect(reranked_result["ok"] is True, str(reranked_result))
            expect(len(mcp_search_calls) == 2, str(mcp_search_calls))
            expect(mcp_search_calls[1]["arguments"].get("rerank") is True, str(mcp_search_calls[1]))
            rerank_audit = conn.execute(
                "SELECT note FROM notion_retrieval_audit WHERE operation = 'search' ORDER BY id ASC"
            ).fetchall()
            expect("rerank=false" in str(rerank_audit[0]["note"]), str(rerank_audit))
            expect("rerank=true" in str(rerank_audit[1]["note"]), str(rerank_audit))

            fetch_page_result = mod.notion_fetch(
                conn,
                cfg,
                agent_id="agent-test",
                target_id=page_id,
                requested_by_actor="test",
            )
            expect(fetch_page_result["ok"] is True and fetch_page_result["target_kind"] == "page", str(fetch_page_result))
            expect(fetch_page_result["indexed"] is True, str(fetch_page_result))
            expect("Unicorn details" in fetch_page_result["markdown"], str(fetch_page_result))
            expect(fetch_page_result["attachments"][0]["name"] == "brief.txt", str(fetch_page_result))
            expect(fetch_page_result["attachments"][0]["caption"] == "Live file ref", str(fetch_page_result))

            fetch_db_result = mod.notion_fetch(
                conn,
                cfg,
                agent_id="agent-test",
                target_id=database_id,
                requested_by_actor="test",
            )
            expect(fetch_db_result["target_kind"] == "database", str(fetch_db_result))
            expect(fetch_db_result["data_source_id"] == data_source_id, str(fetch_db_result))

            fetch_data_source_result = mod.notion_fetch(
                conn,
                cfg,
                agent_id="agent-test",
                target_id=data_source_id,
                requested_by_actor="test",
            )
            expect(fetch_data_source_result["target_kind"] == "data_source", str(fetch_data_source_result))
            expect(fetch_data_source_result["database_id"] == database_id, str(fetch_data_source_result))

            query_result = mod.notion_query(
                conn,
                cfg,
                agent_id="agent-test",
                target_id=database_id,
                query={"filter": {"property": "Status", "status": {"equals": "In Progress"}}},
                limit=25,
                requested_by_actor="test",
            )
            expect(query_result["ok"] is True, str(query_result))
            expect(query_result["root"]["root_id"] == database_id, str(query_result))
            expect(query_result["results"][0]["properties"]["Status"]["status"]["name"] == "In Progress", str(query_result))

            query_data_source_result = mod.notion_query(
                conn,
                cfg,
                agent_id="agent-test",
                target_id=data_source_id,
                query={"filter": {"property": "Status", "status": {"equals": "In Progress"}}},
                limit=25,
                requested_by_actor="test",
            )
            expect(query_data_source_result["ok"] is True, str(query_data_source_result))
            expect(query_data_source_result["target_kind"] == "data_source", str(query_data_source_result))
            expect(query_data_source_result["data_source_id"] == data_source_id, str(query_data_source_result))
            expect(query_data_source_result["results"][0]["properties"]["Status"]["status"]["name"] == "In Progress", str(query_data_source_result))

            audit_rows = conn.execute(
                "SELECT operation, decision FROM notion_retrieval_audit ORDER BY id ASC"
            ).fetchall()
            expect(
                [(str(row["operation"]), str(row["decision"])) for row in audit_rows] == [
                    ("search", "allow"),
                    ("search", "allow"),
                    ("fetch", "allow"),
                    ("fetch", "allow"),
                    ("fetch", "allow"),
                    ("query", "allow"),
                    ("query", "allow"),
                ],
                str([dict(row) for row in audit_rows]),
            )
            print("PASS test_notion_search_fetch_and_query_use_shared_index_and_live_reads")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_consume_notion_reindex_queue_batches_targets_and_marks_notifications_delivered() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_notion_reindex_queue_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            now = mod.utc_now_iso()
            conn.execute(
                """
                INSERT INTO refresh_jobs (job_name, job_kind, target_id, schedule, last_run_at, last_status, last_note)
                VALUES ('notion-index-sync', 'notion-index-sync', 'notion', 'webhook + 4h full sweep', ?, 'ok', '')
                """,
                (now,),
            )
            conn.commit()

            page_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
            database_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
            mod._queue_notion_reindex_notification(conn, target_id=page_id, source_kind="page", message="page change")
            mod._queue_notion_reindex_notification(conn, target_id=database_id, source_kind="database", message="database change")
            conn.commit()

            sync_calls: list[dict[str, object]] = []

            def fake_sync(conn, cfg, *, full=False, page_ids=None, database_ids=None, actor="system", urlopen_fn=None):
                sync_calls.append(
                    {
                        "full": bool(full),
                        "page_ids": sorted(page_ids or []),
                        "database_ids": sorted(database_ids or []),
                        "actor": actor,
                    }
                )
                return {
                    "ok": True,
                    "status": "ok",
                    "full": bool(full),
                    "page_ids": sorted(page_ids or []),
                    "database_ids": sorted(database_ids or []),
                }

            mod.sync_shared_notion_index = fake_sync
            result = mod.consume_notion_reindex_queue(conn, cfg, actor="test")
            expect(result["ok"] is True and result["processed_notifications"] == 2, str(result))
            expect(sync_calls == [{"full": False, "page_ids": [page_id], "database_ids": [database_id], "actor": "test"}], str(sync_calls))

            delivered = conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM notification_outbox
                WHERE channel_kind = 'notion-reindex' AND delivered_at IS NOT NULL
                """
            ).fetchone()
            expect(int(delivered["c"] if delivered else 0) == 2, str(dict(delivered) if delivered else {}))
            print("PASS test_consume_notion_reindex_queue_batches_targets_and_marks_notifications_delivered")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_process_pending_notion_events_queues_full_reindex_for_data_source_and_file_upload() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_notion_event_pipeline_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            mod.store_notion_event(
                conn,
                event_id="evt-data-source",
                event_type="data_source.schema_updated",
                payload={"id": "evt-data-source", "type": "data_source.schema_updated", "entity": {"id": "dddddddd-dddd-dddd-dddd-dddddddddddd", "type": "data_source"}},
            )
            mod.store_notion_event(
                conn,
                event_id="evt-file-upload",
                event_type="file_upload.completed",
                payload={"id": "evt-file-upload", "type": "file_upload.completed", "entity": {"id": "ffffffff-ffff-ffff-ffff-ffffffffffff", "type": "file_upload"}},
            )
            mod._map_event_to_affected_users = lambda conn_arg, payload: ([], True, payload)

            result = mod.process_pending_notion_events(conn)
            expect(result["processed"] == 2, str(result))
            expect(result["reindex_entities"] == 1, str(result))

            queued = conn.execute(
                """
                SELECT target_id, channel_kind, extra_json
                FROM notification_outbox
                WHERE channel_kind = 'notion-reindex'
                ORDER BY id ASC
                """
            ).fetchall()
            expect(len(queued) == 1, str([dict(row) for row in queued]))
            expect(str(queued[0]["target_id"]) == "full", str(dict(queued[0])))
            extra = json.loads(str(queued[0]["extra_json"] or "{}"))
            expect(extra.get("source_kind") == "full", str(extra))
            print("PASS test_process_pending_notion_events_queues_full_reindex_for_data_source_and_file_upload")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_incremental_reindex_parent_walks_brand_new_page_under_known_root() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_notion_parent_walk_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            root_page_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            new_page_id = "dddddddd-dddd-dddd-dddd-dddddddddddd"

            mod._resolve_notion_index_roots = lambda **kwargs: [
                {
                    "root_ref": "https://www.notion.so/workspace-root-aaaaaaaaaaaabbbbbbbbbbbbbbbb",
                    "root_kind": "page",
                    "root_id": root_page_id,
                    "root_url": "https://www.notion.so/workspace-root-aaaaaaaaaaaabbbbbbbbbbbbbbbb",
                    "root_title": "Workspace Root",
                    "root_page_id": root_page_id,
                    "root_page_url": "https://www.notion.so/workspace-root-aaaaaaaaaaaabbbbbbbbbbbbbbbb",
                    "root_page_title": "Workspace Root",
                }
            ]

            def fake_retrieve_page(**kwargs):
                page_id = kwargs["page_id"]
                if page_id == new_page_id:
                    return {
                        "id": new_page_id,
                        "url": f"https://www.notion.so/to-do-list-{new_page_id.replace('-', '')}",
                        "last_edited_time": "2026-04-25T16:43:00+00:00",
                        "parent": {"type": "page_id", "page_id": root_page_id},
                        "properties": _title_property("To Do List"),
                    }
                return {
                    "id": root_page_id,
                    "url": "https://www.notion.so/workspace-root-aaaaaaaaaaaabbbbbbbbbbbbbbbb",
                    "last_edited_time": "2026-04-25T16:00:00+00:00",
                    "parent": {"type": "workspace", "workspace": True},
                    "properties": _title_property("Workspace Root"),
                }

            mod.retrieve_notion_page = fake_retrieve_page
            mod.list_notion_block_children_all = lambda **kwargs: []
            mod.retrieve_notion_page_markdown = lambda **kwargs: {
                "markdown": "# Overview\n\nClaim ownership of the new task list."
            }
            mod._extract_notion_attachment_text = lambda ref: {"status": "metadata-only", "body": "", "content_type": ""}
            mod._refresh_qmd_after_notion_sync = lambda cfg, embed=False: None

            result = mod.sync_shared_notion_index(
                conn,
                cfg,
                full=False,
                page_ids=[new_page_id],
                actor="parent-walk-test",
            )
            expect(result["ok"] is True, str(result))
            expect(result["status"] == "ok", str(result))
            expect(result["unresolved_pages"] == [], str(result))
            expect(result["changed_docs"] >= 1, str(result))
            expect(result["full"] is False, str(result))

            indexed_rows = conn.execute(
                "SELECT source_page_id, page_title, breadcrumb_json FROM notion_index_documents WHERE source_page_id = ?",
                (new_page_id,),
            ).fetchall()
            expect(len(indexed_rows) >= 1, str([dict(row) for row in indexed_rows]))
            crumbs = json.loads(str(indexed_rows[0]["breadcrumb_json"] or "[]"))
            expect(crumbs[:1] == ["Workspace Root"], f"orphan breadcrumb missing root prefix: {crumbs}")
            expect("To Do List" in crumbs, str(crumbs))

            # Cooldown row split: incremental run must NOT touch the full-sweep clock.
            full_row = conn.execute(
                "SELECT job_name, last_status FROM refresh_jobs WHERE job_name = 'notion-index-sync'"
            ).fetchone()
            incremental_row = conn.execute(
                "SELECT job_name, last_status FROM refresh_jobs WHERE job_name = 'notion-index-sync-incremental'"
            ).fetchone()
            expect(full_row is None, f"full-sweep row leaked from incremental run: {dict(full_row) if full_row else {}}")
            expect(incremental_row is not None, "expected notion-index-sync-incremental refresh_jobs row")
            expect(mod._notion_index_full_sweep_due(conn) is True, "full sweep should still be due after incremental run")

            print("PASS test_incremental_reindex_parent_walks_brand_new_page_under_known_root")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_notion_reindex_queue_retries_unresolved_brand_new_page() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_notion_reindex_retry_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            root_page_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            new_page_id = "dddddddd-dddd-dddd-dddd-dddddddddddd"
            mod.note_refresh_job(
                conn,
                job_name="notion-index-sync",
                job_kind="notion-index-sync",
                target_id="notion",
                schedule="webhook + 1h full sweep",
                status="ok",
                note="recent full sweep",
            )
            mod._queue_notion_reindex_notification(
                conn,
                target_id=new_page_id,
                source_kind="page",
                message="new page webhook",
            )
            conn.commit()

            mod._resolve_notion_index_roots = lambda **kwargs: [
                {
                    "root_ref": "https://www.notion.so/workspace-root-aaaaaaaaaaaabbbbbbbbbbbbbbbb",
                    "root_kind": "page",
                    "root_id": root_page_id,
                    "root_url": "https://www.notion.so/workspace-root-aaaaaaaaaaaabbbbbbbbbbbbbbbb",
                    "root_title": "Workspace Root",
                    "root_page_id": root_page_id,
                    "root_page_url": "https://www.notion.so/workspace-root-aaaaaaaaaaaabbbbbbbbbbbbbbbb",
                    "root_page_title": "Workspace Root",
                }
            ]

            def unavailable_page(**kwargs):
                raise RuntimeError("notion parent not visible yet")

            mod.retrieve_notion_page = unavailable_page
            mod._refresh_qmd_after_notion_sync = lambda cfg, embed=False: None

            result = mod.consume_notion_reindex_queue(conn, cfg, actor="retry-test")
            expect(result["ok"] is True, str(result))
            expect(result["status"] == "warn", str(result))
            expect(result["retry_notifications"] == 1, str(result))

            row = conn.execute(
                """
                SELECT delivered_at, attempt_count, next_attempt_at, delivery_error
                FROM notification_outbox
                WHERE target_kind = 'curator'
                  AND channel_kind = 'notion-reindex'
                  AND target_id = ?
                """,
                (new_page_id,),
            ).fetchone()
            expect(row is not None, "expected queued reindex row")
            expect(row["delivered_at"] is None, str(dict(row)))
            expect(int(row["attempt_count"] or 0) == 1, str(dict(row)))
            expect(str(row["next_attempt_at"] or "").strip(), str(dict(row)))
            expect("eventual-consistency" in str(row["delivery_error"] or ""), str(dict(row)))
            print("PASS test_notion_reindex_queue_retries_unresolved_brand_new_page")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_incremental_reindex_removes_trashed_page_docs() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_notion_trashed_page_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            root_page_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            target_page_id = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"

            # Seed the index as if the page was previously crawled.
            now = mod.utc_now_iso()
            conn.execute(
                """
                INSERT INTO notion_index_documents (
                  doc_key, root_id, source_page_id, source_page_url, source_kind, file_path,
                  page_title, section_heading, section_ordinal, breadcrumb_json,
                  owners_json, last_edited_time, content_hash, indexed_at, state
                ) VALUES (?, ?, ?, ?, 'page', ?, 'Doomed Note', 'Overview', 0, '["Workspace Root","Doomed Note"]', '[]', ?, 'h', ?, 'active')
                """,
                (
                    f"{root_page_id}:{target_page_id}:0",
                    root_page_id,
                    target_page_id,
                    "https://www.notion.so/doomed",
                    str(root / "doomed.md"),
                    now,
                    now,
                ),
            )
            conn.commit()
            (root / "doomed.md").write_text("seed", encoding="utf-8")

            mod._resolve_notion_index_roots = lambda **kwargs: [
                {
                    "root_ref": "https://www.notion.so/workspace-root-aaaaaaaaaaaabbbbbbbbbbbbbbbb",
                    "root_kind": "page",
                    "root_id": root_page_id,
                    "root_url": "https://www.notion.so/workspace-root-aaaaaaaaaaaabbbbbbbbbbbbbbbb",
                    "root_title": "Workspace Root",
                    "root_page_id": root_page_id,
                    "root_page_url": "https://www.notion.so/workspace-root-aaaaaaaaaaaabbbbbbbbbbbbbbbb",
                    "root_page_title": "Workspace Root",
                }
            ]
            mod.retrieve_notion_page = lambda **kwargs: {
                "id": kwargs["page_id"],
                "url": "https://www.notion.so/doomed",
                "in_trash": True,
                "parent": {"type": "page_id", "page_id": root_page_id},
                "properties": _title_property("Doomed Note"),
            }
            mod._refresh_qmd_after_notion_sync = lambda cfg, embed=False: None

            result = mod.sync_shared_notion_index(
                conn,
                cfg,
                full=False,
                page_ids=[target_page_id],
                actor="trash-test",
            )
            expect(result["ok"] is True and result["status"] == "ok", str(result))
            remaining = conn.execute(
                "SELECT COUNT(*) AS c FROM notion_index_documents WHERE source_page_id = ?",
                (target_page_id,),
            ).fetchone()
            expect(int(remaining["c"]) == 0, "trashed page should leave no rows")
            expect(result["changed_docs"] == 1, str(result))
            print("PASS test_incremental_reindex_removes_trashed_page_docs")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def _people_property(name: str, *user_ids: str) -> dict[str, object]:
    return {
        name: {
            "type": "people",
            "people": [{"object": "user", "id": uid} for uid in user_ids],
        }
    }


def test_today_plate_discovers_child_task_databases_and_filters_owner_items() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_today_plate_discovery_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            root_page_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            owner_db_id = "11111111-1111-1111-1111-111111111111"
            unrelated_db_id = "22222222-2222-2222-2222-222222222222"
            dri_db_id = "33333333-3333-3333-3333-333333333333"
            user_notion_id = "user-notion-id-xxxx"
            insert_agent(mod, conn, agent_id="agent-guide", unix_user="alex", display_name="Guide")
            agent_row = conn.execute(
                "SELECT * FROM agents WHERE agent_id = ?",
                ("agent-guide",),
            ).fetchone()
            identity = {
                "verification_status": "verified",
                "notion_user_email": "alex@example.com",
                "notion_user_id": user_notion_id,
                "claimed_notion_email": "alex@example.com",
            }

            mod.list_notion_block_children_all = lambda **kwargs: (
                [
                    {"type": "child_database", "id": owner_db_id},
                    {"type": "child_database", "id": unrelated_db_id},
                    {"type": "child_database", "id": dri_db_id},
                ]
                if extract_id(kwargs.get("block_id", "")) == root_page_id
                else []
            )

            def fake_load_schema(*, target_id, settings, notion_kwargs):
                if extract_id(target_id) == owner_db_id:
                    return (
                        {
                            "id": owner_db_id,
                            "url": "https://www.notion.so/tasks",
                            "title": [{"plain_text": "Tasks for the team"}],
                        },
                        {"properties": {"Name": {"type": "title"}, "Owner": {"type": "people"}}},
                    )
                if extract_id(target_id) == unrelated_db_id:
                    return (
                        {
                            "id": unrelated_db_id,
                            "url": "https://www.notion.so/notes",
                            "title": [{"plain_text": "Reference notes"}],
                        },
                        {"properties": {"Name": {"type": "title"}}},
                    )
                if extract_id(target_id) == dri_db_id:
                    return (
                        {
                            "id": dri_db_id,
                            "url": "https://www.notion.so/initiatives",
                            "title": [{"plain_text": "Initiatives"}],
                        },
                        {
                            "properties": {
                                "Name": {"type": "title"},
                                # Conceptually identical to Owner but with a workspace-specific label
                                "DRI": {"type": "people"},
                                "Reviewer": {"type": "people"},
                                # Provenance, must be ignored as an ownership channel
                                "Changed By": {"type": "people"},
                            }
                        },
                    )
                raise RuntimeError(f"unexpected target {target_id}")

            mod._load_notion_collection_schema = fake_load_schema

            queried_ids: list[str] = []
            queried_filters: list[object] = []

            def fake_query(*, database_id, token, api_version, payload, **kwargs):
                normalized = extract_id(database_id)
                queried_ids.append(normalized)
                queried_filters.append((payload or {}).get("filter"))
                if normalized == owner_db_id:
                    return {
                        "result": {
                            "results": [
                                {
                                    "id": "row-owner-1",
                                    "url": "https://www.notion.so/row-owner-1",
                                    "last_edited_time": "2026-04-25T19:00:00+00:00",
                                    "properties": {
                                        **_title_property("Wire up daily plate"),
                                        **_people_property("Owner", user_notion_id),
                                    },
                                },
                                {
                                    "id": "row-owner-2",
                                    "url": "https://www.notion.so/row-owner-2",
                                    "last_edited_time": "2026-04-24T08:00:00+00:00",
                                    "properties": {
                                        **_title_property("Brief Joof on rollout"),
                                        **_people_property("Owner", user_notion_id),
                                    },
                                },
                            ]
                        }
                    }
                if normalized == dri_db_id:
                    return {
                        "result": {
                            "results": [
                                {
                                    "id": "row-dri-1",
                                    "url": "https://www.notion.so/row-dri-1",
                                    "last_edited_time": "2026-04-25T20:00:00+00:00",
                                    "properties": {
                                        **_title_property("North-star initiative"),
                                        # The user appears under the workspace-specific
                                        # "DRI" channel and "Reviewer", and "Changed By"
                                        # is provenance only and must NOT count as a role.
                                        **_people_property("DRI", user_notion_id),
                                        **_people_property("Reviewer", user_notion_id, "other-user"),
                                        **_people_property("Changed By", user_notion_id),
                                    },
                                },
                            ]
                        }
                    }
                raise AssertionError(f"unexpected DB queried: {database_id}")

            mod.query_notion_collection_all = fake_query

            settings = {
                "token": "secret_test",
                "api_version": "2026-03-11",
                "space_id": root_page_id,
                "space_kind": "page",
                "space_url": f"https://www.notion.so/{root_page_id.replace('-', '')}",
            }
            mod._require_shared_notion_settings = lambda: settings

            stub_cache: dict[str, object] = {}
            plate_text = mod._build_today_plate(
                conn,
                agent_row=agent_row,
                identity=identity,
                notion_stub_cache=stub_cache,
            )

            # Both ownership-channel databases discovered; the no-people-property one ignored.
            expect("Tasks for the team" in plate_text, plate_text)
            expect("Initiatives" in plate_text, plate_text)
            expect("Reference notes" not in plate_text, plate_text)
            # Headline language is conceptual ("ownership surfaces"), not keyword-matched.
            expect("Ownership surfaces discovered" in plate_text, plate_text)
            expect("opaque ownership channels" in plate_text, plate_text)
            # Per-DB ownership-channel labels are surfaced verbatim, including
            # the workspace-specific "DRI" / "Reviewer" pair.
            expect("Tasks for the team (Owner)" in plate_text, plate_text)
            expect("Initiatives (DRI, Reviewer)" in plate_text, plate_text)
            # Per-row role tag uses the workspace's actual property names —
            # "Owner" for the Owner DB row, "DRI, Reviewer" for the Initiatives row,
            # and the provenance "Changed By" must NOT show up as a role.
            expect("Wire up daily plate — as Owner" in plate_text, plate_text)
            expect("North-star initiative — as DRI, Reviewer" in plate_text, plate_text)
            expect("Changed By" not in plate_text, plate_text)
            expect("Verification: confirmed" in plate_text, plate_text)
            expect("Per-surface breakdown" in plate_text, plate_text)

            # Notion was queried with an OR filter spanning every people-typed
            # property on the data source — verbatim names, no special-casing of
            # Owner/Assignee.
            owner_filter = queried_filters[queried_ids.index(owner_db_id)]
            dri_filter = queried_filters[queried_ids.index(dri_db_id)]
            expect(
                owner_filter == {"property": "Owner", "people": {"contains": user_notion_id}},
                str(owner_filter),
            )
            expect(
                dri_filter
                == {
                    "or": [
                        {"property": "DRI", "people": {"contains": user_notion_id}},
                        {"property": "Reviewer", "people": {"contains": user_notion_id}},
                    ]
                },
                str(dri_filter),
            )

            stored_ids = stub_cache.get(f"today-plate-ids:agent-guide")
            expect(
                set(stored_ids or []) == {"row-owner-1", "row-owner-2", "row-dri-1"},
                str(stored_ids),
            )
            print("PASS test_today_plate_discovers_child_task_databases_and_filters_owner_items")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def extract_id(target: str) -> str:
    text = str(target or "").strip()
    if "-" in text and len(text) >= 32:
        return text
    if len(text) == 32:
        return f"{text[0:8]}-{text[8:12]}-{text[12:16]}-{text[16:20]}-{text[20:]}"
    return text


def test_today_plate_page_scoped_without_task_db_falls_back_to_qmd_message() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_today_plate_no_task_db_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            root_page_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            insert_agent(mod, conn, agent_id="agent-guide", unix_user="alex")
            agent_row = conn.execute(
                "SELECT * FROM agents WHERE agent_id = ?",
                ("agent-guide",),
            ).fetchone()
            mod._require_shared_notion_settings = lambda: {
                "token": "secret_test",
                "api_version": "2026-03-11",
                "space_id": root_page_id,
                "space_kind": "page",
                "space_url": f"https://www.notion.so/{root_page_id.replace('-', '')}",
            }
            mod.list_notion_block_children_all = lambda **kwargs: []
            plate = mod._build_today_plate(
                conn,
                agent_row=agent_row,
                identity={"verification_status": "verified", "notion_user_id": "user-x"},
                notion_stub_cache={},
            )
            expect("No structured ownership surfaces discovered" in plate, plate)
            expect("people-typed property" in plate, plate)
            expect("knowledge.search-and-fetch" in plate, plate)
            # And critically: do NOT bake in keyword instructions.
            expect("'task'" not in plate and "'todo'" not in plate, plate)
            print("PASS test_today_plate_page_scoped_without_task_db_falls_back_to_qmd_message")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def main() -> int:
    test_sync_shared_notion_index_indexes_page_tree_into_qmd_markdown_docs()
    test_notion_search_fetch_and_query_use_shared_index_and_live_reads()
    test_consume_notion_reindex_queue_batches_targets_and_marks_notifications_delivered()
    test_process_pending_notion_events_queues_full_reindex_for_data_source_and_file_upload()
    test_incremental_reindex_parent_walks_brand_new_page_under_known_root()
    test_notion_reindex_queue_retries_unresolved_brand_new_page()
    test_incremental_reindex_removes_trashed_page_docs()
    test_today_plate_discovers_child_task_databases_and_filters_owner_items()
    test_today_plate_page_scoped_without_task_db_falls_back_to_qmd_message()
    print("PASS all 9 shared notion knowledge regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
