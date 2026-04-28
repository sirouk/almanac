#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
BATCHER_PY = PYTHON_DIR / "almanac_ssot_batcher.py"


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
    batcher = load_module(BATCHER_PY, "almanac_ssot_batcher_combined_flow_test")

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


def main() -> int:
    test_ssot_batcher_processes_events_and_reindex_queue()
    print("PASS all 1 ssot batcher regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
