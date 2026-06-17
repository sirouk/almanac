#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
BATCHER_PY = PYTHON_DIR / "arclink_ssot_batcher.py"
CONTROL_PY = PYTHON_DIR / "arclink_control.py"


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


def test_ssot_batcher_processes_events_and_reindex_queue() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    batcher = load_module(BATCHER_PY, "arclink_ssot_batcher_combined_flow_test")

    class FakeConfig:
        pass

    cfg = FakeConfig()
    conn_obj = object()
    calls: list[tuple[str, object]] = []

    class _FakeConnCtx:
        def __enter__(self):
            return conn_obj

        def __exit__(self, exc_type, exc, tb):
            return False

    batcher.Config.from_env = classmethod(lambda cls: cfg)  # type: ignore[assignment]
    batcher.connect_db = lambda provided_cfg: (_FakeConnCtx() if provided_cfg is cfg else None)
    batcher.process_pending_notion_events = lambda conn: (
        calls.append(("events", conn)) or {"processed": 2, "reindex_entities": 1}
    )
    batcher.consume_notion_reindex_queue = lambda conn, provided_cfg, actor="": (
        calls.append(("reindex", conn, provided_cfg, actor))
        or {"ok": True, "status": "ok", "processed_notifications": 1}
    )

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        batcher.main()

    payload = json.loads(buffer.getvalue())
    expect(payload["events"]["processed"] == 2, str(payload))
    expect(payload["reindex"]["processed_notifications"] == 1, str(payload))
    expect(calls == [("events", conn_obj), ("reindex", conn_obj, cfg, "ssot-batcher")], str(calls))
    print("PASS test_ssot_batcher_processes_events_and_reindex_queue")


def _config_values(root: Path) -> dict[str, str]:
    return {
        "ARCLINK_USER": "arclink",
        "ARCLINK_HOME": str(root / "home-arclink"),
        "ARCLINK_REPO_DIR": str(root / "repo"),
        "ARCLINK_PRIV_DIR": str(root / "priv"),
        "STATE_DIR": str(root / "state"),
        "RUNTIME_DIR": str(root / "state" / "runtime"),
        "VAULT_DIR": str(root / "vault"),
        "ARCLINK_DB_PATH": str(root / "state" / "arclink-control.sqlite3"),
        "ARCLINK_AGENTS_STATE_DIR": str(root / "state" / "agents"),
        "ARCLINK_CURATOR_DIR": str(root / "state" / "curator"),
        "ARCLINK_CURATOR_MANIFEST": str(root / "state" / "curator" / "manifest.json"),
        "ARCLINK_CURATOR_HERMES_HOME": str(root / "state" / "curator" / "hermes-home"),
        "ARCLINK_ARCHIVED_AGENTS_DIR": str(root / "state" / "archived-agents"),
        "ARCLINK_RELEASE_STATE_FILE": str(root / "state" / "arclink-release.json"),
        "ARCLINK_QMD_URL": "http://127.0.0.1:8181/mcp",
        "ARCLINK_MCP_HOST": "127.0.0.1",
        "ARCLINK_MCP_PORT": "8282",
    }


def _write_config(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(f'{key}="{value}"' for key, value in values.items()) + "\n", encoding="utf-8")


def test_notion_event_batcher_claims_rows_before_processing() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_ssot_batcher_claim_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        _write_config(config_path, _config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            with control.connect_db(cfg) as conn:
                now = control.utc_now_iso()
                conn.executemany(
                    """
                    INSERT INTO notion_webhook_events (
                      event_id, event_type, payload_json, received_at, batch_status
                    ) VALUES (?, ?, ?, ?, 'pending')
                    """,
                    [
                        ("evt-1", "page.content_updated", json.dumps({"object": "event"}), now),
                        ("evt-2", "page.content_updated", json.dumps({"object": "event"}), now),
                    ],
                )
                conn.commit()

                claimed = control._claim_pending_notion_webhook_events(conn, limit=1)
                expect(len(claimed) == 1, str([dict(row) for row in claimed]))
                expect(claimed[0]["event_id"] == "evt-1", str(dict(claimed[0])))

                control._notion_event_entity_ref = lambda payload: ("", "")
                control._map_event_to_affected_users = lambda conn, payload: ([], True, payload)
                result = control.process_pending_notion_events(conn)
                expect(result["processed"] == 1, str(result))
                rows = {
                    row["event_id"]: row["batch_status"]
                    for row in conn.execute("SELECT event_id, batch_status FROM notion_webhook_events").fetchall()
                }
                expect(rows == {"evt-1": "processing", "evt-2": "processed"}, str(rows))

                conn.execute(
                    "UPDATE notion_webhook_events SET batch_claimed_at = ? WHERE event_id = 'evt-1'",
                    ("2026-01-01T00:00:00+00:00",),
                )
                conn.commit()
                result = control.process_pending_notion_events(conn)
                expect(result["processed"] == 1, str(result))
                final_status = conn.execute(
                    "SELECT batch_status FROM notion_webhook_events WHERE event_id = 'evt-1'"
                ).fetchone()["batch_status"]
                expect(final_status == "processed", final_status)
            print("PASS test_notion_event_batcher_claims_rows_before_processing")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_notion_reindex_consumer_lease_blocks_overlapping_sync() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_ssot_batcher_reindex_lease_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        _write_config(config_path, _config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        conn1 = None
        conn2 = None
        real_sync = control.sync_shared_notion_index
        try:
            cfg = control.Config.from_env()
            conn1 = control.connect_db(cfg)
            conn2 = control.connect_db(cfg)
            now = control.utc_now_iso()
            control.note_refresh_job(
                conn1,
                job_name="notion-index-sync",
                job_kind="notion-index-sync",
                target_id="notion",
                schedule="test",
                status="ok",
                note="recent full sweep",
            )
            conn1.execute(
                """
                INSERT INTO notification_outbox (
                  target_kind, target_id, channel_kind, message, extra_json, created_at,
                  attempt_count, last_attempt_at, next_attempt_at, delivered_at, delivery_error
                ) VALUES (?, ?, ?, ?, ?, ?, 0, NULL, ?, NULL, NULL)
                """,
                (
                    "curator",
                    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "notion-reindex",
                    "page changed",
                    json.dumps({"source_kind": "page"}),
                    now,
                    now,
                ),
            )
            conn1.commit()

            calls: list[dict[str, object]] = []
            nested_results: list[dict[str, object]] = []

            def fake_sync(conn, cfg, *, full, page_ids, database_ids, actor):
                calls.append(
                    {
                        "full": full,
                        "page_ids": list(page_ids),
                        "database_ids": list(database_ids),
                        "actor": actor,
                    }
                )
                nested_results.append(control.consume_notion_reindex_queue(conn2, cfg, actor="nested"))
                return {
                    "ok": True,
                    "status": "ok",
                    "full": full,
                    "unresolved_pages": [],
                    "unresolved_databases": [],
                }

            control.sync_shared_notion_index = fake_sync
            result = control.consume_notion_reindex_queue(conn1, cfg, actor="outer")
            expect(result["ok"] is True and result["processed_notifications"] == 1, str(result))
            expect(len(calls) == 1, str(calls))
            expect(nested_results and nested_results[0]["status"] == "busy", str(nested_results))
            delivered = conn1.execute(
                "SELECT delivered_at FROM notification_outbox WHERE channel_kind = 'notion-reindex'"
            ).fetchone()
            expect(bool(str(delivered["delivered_at"] or "")), str(dict(delivered)))
            lease_value = control.get_setting(conn1, control.NOTION_REINDEX_CONSUMER_LEASE_KEY, "")
            expect(lease_value == "", f"expected reindex lease to be released, got {lease_value!r}")
            print("PASS test_notion_reindex_consumer_lease_blocks_overlapping_sync")
        finally:
            control.sync_shared_notion_index = real_sync
            if conn1 is not None:
                conn1.close()
            if conn2 is not None:
                conn2.close()
            os.environ.clear()
            os.environ.update(old_env)


def main() -> int:
    test_ssot_batcher_processes_events_and_reindex_queue()
    test_notion_event_batcher_claims_rows_before_processing()
    test_notion_reindex_consumer_lease_blocks_overlapping_sync()
    print("PASS all 3 ssot batcher regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
