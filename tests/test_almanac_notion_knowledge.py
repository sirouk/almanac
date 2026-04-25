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


def insert_agent(mod, conn, *, agent_id: str, unix_user: str, display_name: str = "Chris") -> None:
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
                    "url": "https://www.notion.so/chutes-unicorn-bbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                    "last_edited_time": "2026-04-21T12:05:00+00:00",
                    "properties": {
                        **_title_property("Chutes Unicorn"),
                        "Owner": {
                            "type": "people",
                            "people": [{"name": "Chris"}],
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
            expect("Breadcrumb: Workspace Root > Chutes Unicorn" in indexed_body, indexed_body)
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
            insert_agent(mod, conn, agent_id="agent-test", unix_user="sirouk")

            root_page_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            page_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
            database_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
            data_source_id = "dddddddd-dddd-dddd-dddd-dddddddddddd"
            file_path = mod._notion_index_markdown_dir(cfg) / mod._notion_index_doc_relative_path(root_page_id, page_id, 0)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            body = mod._render_notion_index_section_document(
                page_title="Chutes Unicorn",
                page_url="https://www.notion.so/chutes-unicorn-bbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                page_id=page_id,
                root_title="Workspace Root",
                root_id=root_page_id,
                breadcrumb=["Workspace Root", "Projects", "Chutes Unicorn"],
                section_heading="Summary",
                owners=["Chris"],
                last_edited_time="2026-04-21T12:05:00+00:00",
                body="Unicorn details",
            )
            mod._upsert_notion_index_document(
                conn,
                doc_key=mod._notion_index_doc_key(root_page_id, page_id, 0),
                root_id=root_page_id,
                source_page_id=page_id,
                source_page_url="https://www.notion.so/chutes-unicorn-bbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                source_kind="page",
                file_path=file_path,
                page_title="Chutes Unicorn",
                section_heading="Summary",
                section_ordinal=0,
                breadcrumb=["Workspace Root", "Projects", "Chutes Unicorn"],
                owners=["Chris"],
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
                    else {"kind": "page", "id": page_id, "url": "https://www.notion.so/chutes-unicorn-bbbbbbbbbbbbbbbbbbbbbbbbbbbb", "title": "Chutes Unicorn"}
                )
            )
            mod.retrieve_notion_page = lambda **kwargs: {
                "id": page_id,
                "url": "https://www.notion.so/chutes-unicorn-bbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "last_edited_time": "2026-04-21T12:05:00+00:00",
                "properties": _title_property("Chutes Unicorn"),
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
            expect(search_result["results"][0]["page_title"] == "Chutes Unicorn", str(search_result))
            expect(search_result["results"][0]["breadcrumb"] == ["Workspace Root", "Projects", "Chutes Unicorn"], str(search_result))
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


def main() -> int:
    test_sync_shared_notion_index_indexes_page_tree_into_qmd_markdown_docs()
    test_notion_search_fetch_and_query_use_shared_index_and_live_reads()
    test_consume_notion_reindex_queue_batches_targets_and_marks_notifications_delivered()
    test_process_pending_notion_events_queues_full_reindex_for_data_source_and_file_upload()
    test_incremental_reindex_parent_walks_brand_new_page_under_known_root()
    print("PASS all 5 shared notion knowledge regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
