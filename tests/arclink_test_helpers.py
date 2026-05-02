"""Shared test utilities for ArcLink test suite."""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_module(filename: str, name: str):
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    path = PYTHON_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def memory_db(control):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    control.ensure_schema(conn)
    return conn


def auth_headers(session: dict, *, csrf: bool = False) -> dict[str, str]:
    """Build Authorization + Session-Id headers from a session dict."""
    h = {
        "Authorization": f"Bearer {session['session_token']}",
        "X-ArcLink-Session-Id": session["session_id"],
    }
    if csrf:
        h["X-ArcLink-CSRF-Token"] = session["csrf_token"]
    return h


def sign_stripe(adapters, payload: str) -> str:
    """Sign a Stripe webhook payload using the test secret."""
    return adapters.sign_stripe_webhook(payload, "whsec_test", timestamp=int(time.time()))
