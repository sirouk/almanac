#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONTROL_PY = REPO / "python" / "arclink_control.py"


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


def test_connect_db_tolerates_locked_journal_mode_pragma() -> None:
    mod = load_module(CONTROL_PY, "arclink_control_db_lock_test")

    class FakeConn:
        row_factory = None

        def __init__(self) -> None:
            self.statements: list[str] = []

        def execute(self, sql: str, *args, **kwargs):
            self.statements.append(sql)
            if sql == "PRAGMA journal_mode = DELETE":
                raise sqlite3.OperationalError("database is locked")
            return self

    fake_conn = FakeConn()
    original_connect = mod.sqlite3.connect
    original_schema = mod.ensure_schema
    original_migrate = mod._migrate_onboarding_bot_tokens
    original_expire = mod.expire_stale_ssot_pending_writes
    original_env = mod.config_env_value
    old_env = os.environ.copy()
    try:
        mod.sqlite3.connect = lambda *_args, **_kwargs: fake_conn
        mod.ensure_schema = lambda *_args, **_kwargs: None
        mod._migrate_onboarding_bot_tokens = lambda *_args, **_kwargs: None
        mod.expire_stale_ssot_pending_writes = lambda *_args, **_kwargs: None
        mod.config_env_value = lambda key, default="": "DELETE" if key == "ARCLINK_SQLITE_JOURNAL_MODE" else default
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config" / "arclink.env"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                "\n".join(
                    [
                        f"ARCLINK_REPO_DIR={root}",
                        f"ARCLINK_PRIV_DIR={root / 'priv'}",
                        f"STATE_DIR={root / 'state'}",
                        f"RUNTIME_DIR={root / 'runtime'}",
                        f"VAULT_DIR={root / 'vault'}",
                    ]
                ),
                encoding="utf-8",
            )
            os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
        expect(conn is fake_conn, "connect_db should return the opened connection")
        expect(fake_conn.statements[0] == "PRAGMA busy_timeout = 15000", str(fake_conn.statements))
        expect("PRAGMA foreign_keys = ON" in fake_conn.statements, str(fake_conn.statements))
        print("PASS test_connect_db_tolerates_locked_journal_mode_pragma")
    finally:
        mod.sqlite3.connect = original_connect
        mod.ensure_schema = original_schema
        mod._migrate_onboarding_bot_tokens = original_migrate
        mod.expire_stale_ssot_pending_writes = original_expire
        mod.config_env_value = original_env
        os.environ.clear()
        os.environ.update(old_env)


if __name__ == "__main__":
    test_connect_db_tolerates_locked_journal_mode_pragma()
