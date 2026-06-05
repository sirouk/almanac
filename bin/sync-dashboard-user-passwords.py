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

from arclink_api_auth import (  # noqa: E402
    _dashboard_password_secret_path,
    set_arclink_user_password,
    verify_arclink_password,
)
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


def _load_secret_password(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return value if value.startswith("arc_") else ""


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
    scanned = updated = skipped = missing = users = 0
    seen_users: set[str] = set()
    for row in rows:
        scanned += 1
        user_id = str(row["user_id"] or "").strip()
        if not user_id or user_id in seen_users:
            continue
        seen_users.add(user_id)
        users += 1
        canonical_ref = f"secret://arclink/dashboard/users/{user_id}/password"
        password = _load_secret_password(
            _dashboard_password_secret_path(
                deployment_id="",
                user_id=user_id,
                secret_ref=canonical_ref,
            )
        )
        roots = render_arclink_state_roots(
            deployment_id=str(row["deployment_id"]),
            prefix=str(row["prefix"]),
            state_root_base=state_root_base,
        )
        if not password:
            access_path = Path(roots["hermes_home"]) / "state" / "arclink-web-access.json"
            password = _load_access_password(access_path)
        if not password:
            missing += 1
            continue
        current_hash = str(row["password_hash"] or "")
        if current_hash and verify_arclink_password(password, current_hash):
            skipped += 1
            continue
        set_arclink_user_password(conn, user_id=user_id, password=password)
        updated += 1
    return {"scanned": scanned, "users": users, "updated": updated, "skipped": skipped, "missing": missing}


def main() -> None:
    cfg = Config.from_env()
    state_root_base = str(os.environ.get("ARCLINK_STATE_ROOT_BASE") or "/arcdata/deployments").strip()
    with connect_db(cfg) as conn:
        summary = sync_dashboard_user_passwords(conn, state_root_base=state_root_base)
    print(json.dumps({"dashboard_user_passwords": summary}, sort_keys=True))


if __name__ == "__main__":
    main()
