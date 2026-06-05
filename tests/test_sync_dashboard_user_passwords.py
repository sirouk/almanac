#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

from arclink_test_helpers import expect, load_module

REPO = Path(__file__).resolve().parents[1]


def load_sync_module():
    path = REPO / "bin" / "sync-dashboard-user-passwords.py"
    spec = importlib.util.spec_from_file_location("sync_dashboard_user_passwords_test", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def memory_db(control) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    control.ensure_schema(conn)
    return conn


def test_dashboard_password_sync_prefers_canonical_user_secret_once() -> None:
    control = load_module("arclink_control.py", "arclink_control_dashboard_sync_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_dashboard_sync_test")
    sync = load_sync_module()
    conn = memory_db(control)
    control.upsert_arclink_user(conn, user_id="user_1", email="captain@example.test", display_name="Captain")
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_old",
        user_id="user_1",
        prefix="old",
        status="active",
    )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="dep_new",
        user_id="user_1",
        prefix="new",
        status="active",
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        old_env = os.environ.copy()
        os.environ["ARCLINK_SECRET_STORE_DIR"] = str(root / "secrets")
        try:
            canonical_ref = "secret://arclink/dashboard/users/user_1/password"
            canonical_path = api._dashboard_password_secret_path(
                deployment_id="",
                user_id="user_1",
                secret_ref=canonical_ref,
            )
            assert canonical_path is not None
            canonical_path.parent.mkdir(parents=True, exist_ok=True)
            canonical_path.write_text("arc_canonical_password\n", encoding="utf-8")
            for deployment_id, prefix, password in (
                ("dep_old", "old", "arc_stale_old_password"),
                ("dep_new", "new", "arc_newer_but_not_canonical"),
            ):
                roots = load_module("arclink_provisioning.py", f"arclink_provisioning_{deployment_id}").render_arclink_state_roots(
                    deployment_id=deployment_id,
                    prefix=prefix,
                    state_root_base=str(root / "deployments"),
                )
                access = Path(roots["hermes_home"]) / "state" / "arclink-web-access.json"
                access.parent.mkdir(parents=True, exist_ok=True)
                access.write_text(json.dumps({"password": password}), encoding="utf-8")
            summary = sync.sync_dashboard_user_passwords(conn, state_root_base=str(root / "deployments"))
            row = conn.execute("SELECT password_hash FROM arclink_users WHERE user_id = 'user_1'").fetchone()
            expect(summary["users"] == 1 and summary["updated"] == 1, str(summary))
            expect(api.verify_arclink_password("arc_canonical_password", row["password_hash"]), str(row["password_hash"]))
            expect(not api.verify_arclink_password("arc_stale_old_password", row["password_hash"]), str(row["password_hash"]))
            print("PASS test_dashboard_password_sync_prefers_canonical_user_secret_once")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


if __name__ == "__main__":
    test_dashboard_password_sync_prefers_canonical_user_secret_once()
    print("PASS all dashboard password sync tests")
