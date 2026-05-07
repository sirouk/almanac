#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_PYTHON = _REPO / "python"
if str(_PYTHON) not in sys.path:
    sys.path.insert(0, str(_PYTHON))

from arclink_api_auth import set_arclink_user_password, verify_arclink_password  # noqa: E402
from arclink_control import Config, connect_db  # noqa: E402
from arclink_provisioning import render_arclink_state_roots  # noqa: E402


def _load_access_password(path: Path) -> str:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("password") or "").strip()


def sync_dashboard_user_passwords(conn: sqlite3.Connection, *, state_root_base: str) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT d.deployment_id, d.user_id, d.prefix, u.password_hash
        FROM arclink_deployments d
        JOIN arclink_users u ON u.user_id = d.user_id
        WHERE d.status IN ('active', 'running', 'provisioning', 'provisioning_ready')
        ORDER BY d.updated_at DESC, d.deployment_id ASC
        """
    ).fetchall()
    scanned = updated = skipped = missing = 0
    for row in rows:
        scanned += 1
        roots = render_arclink_state_roots(
            deployment_id=str(row["deployment_id"]),
            prefix=str(row["prefix"]),
            state_root_base=state_root_base,
        )
        access_path = Path(roots["hermes_home"]) / "state" / "arclink-web-access.json"
        password = _load_access_password(access_path)
        if not password:
            missing += 1
            continue
        current_hash = str(row["password_hash"] or "")
        if current_hash and verify_arclink_password(password, current_hash):
            skipped += 1
            continue
        set_arclink_user_password(conn, user_id=str(row["user_id"]), password=password)
        updated += 1
    return {"scanned": scanned, "updated": updated, "skipped": skipped, "missing": missing}


def main() -> None:
    cfg = Config.from_env()
    state_root_base = str(os.environ.get("ARCLINK_STATE_ROOT_BASE") or "/arcdata/deployments").strip()
    with connect_db(cfg) as conn:
        summary = sync_dashboard_user_passwords(conn, state_root_base=state_root_base)
    print(json.dumps({"dashboard_user_passwords": summary}, sort_keys=True))


if __name__ == "__main__":
    main()
