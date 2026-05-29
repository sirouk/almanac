#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
CONTROL_PY = PYTHON_DIR / "arclink_control.py"
OPERATOR_AGENT_PY = PYTHON_DIR / "arclink_operator_agent.py"


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


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_config(path: Path, values: dict[str, str]) -> None:
    lines = [f"{key}={json.dumps(value)}" for key, value in values.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def config_values(root: Path) -> dict[str, str]:
    return {
        "ARCLINK_USER": "arclink",
        "ARCLINK_HOME": str(root / "home-arclink"),
        "ARCLINK_REPO_DIR": str(REPO),
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


def with_db():
    control = load_module(CONTROL_PY, "arclink_control_operator_agent_test")
    operator_agent = load_module(OPERATOR_AGENT_PY, "arclink_operator_agent_test")
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    config_path = root / "config" / "arclink.env"
    write_config(config_path, config_values(root))
    old_env = os.environ.copy()
    os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
    try:
        cfg = control.Config.from_env()
        conn = control.connect_db(cfg)
        return tmp, old_env, conn, control, operator_agent
    except Exception:
        os.environ.clear()
        os.environ.update(old_env)
        tmp.cleanup()
        raise


def cleanup(tmp, old_env) -> None:
    os.environ.clear()
    os.environ.update(old_env)
    tmp.cleanup()


def test_operator_agent_lifecycle_and_single_invariant() -> None:
    tmp, old_env, conn, control, oa = with_db()
    try:
        # No agent yet: not routable, resolves to None.
        expect(oa.operator_agent_deployment(conn) is None, "no operator agent before setup")
        expect(oa.operator_conversation_routable(conn) is False, "not routable before setup")
        expect(oa.assert_single_operator_agent(conn) == 0, "zero operator agents before setup")

        user = oa.ensure_operator_agent_user(conn, user_id="operator", email="op@example.test", display_name="Ops")
        expect(user["entitlement_state"] == "comp", str(user))

        deployment = oa.ensure_operator_agent_deployment(conn, user_id="operator", status="reserved")
        expect(deployment["deployment_id"] == "operator", str(deployment))
        expect(deployment["user_id"] == "operator", str(deployment))
        meta = json.loads(deployment["metadata_json"]) if isinstance(deployment["metadata_json"], str) else deployment["metadata_json"]
        expect(bool(meta.get("operator_agent")) is True, str(meta))
        expect(int(meta.get("bundle_agent_count") or 0) == 1, str(meta))

        # Reserved (not ready) => not routable yet.
        expect(oa.operator_conversation_routable(conn) is False, "reserved deployment is not routable")

        # Idempotent re-run returns the same single agent.
        again = oa.ensure_operator_agent_deployment(conn, user_id="operator")
        expect(again["deployment_id"] == "operator", str(again))
        expect(oa.assert_single_operator_agent(conn) == 1, "exactly one operator agent after idempotent re-run")

        # Refuse a SECOND operator agent.
        raised = False
        try:
            oa.ensure_operator_agent_deployment(conn, user_id="operator", deployment_id="operator-2", prefix="operator-two")
        except oa.OperatorAgentError:
            raised = True
        expect(raised, "creating a second operator agent must raise")
        expect(oa.assert_single_operator_agent(conn) == 1, "still exactly one operator agent")

        # Promote to active => routable.
        conn.execute("UPDATE arclink_deployments SET status = 'active' WHERE deployment_id = 'operator'")
        conn.commit()
        expect(oa.operator_conversation_routable(conn) is True, "active operator deployment is routable")
        print("PASS test_operator_agent_lifecycle_and_single_invariant")
    finally:
        cleanup(tmp, old_env)


def test_operator_agent_turn_enqueues_only_when_ready() -> None:
    tmp, old_env, conn, control, oa = with_db()
    try:
        oa.ensure_operator_agent_user(conn, user_id="operator")
        oa.ensure_operator_agent_deployment(conn, user_id="operator", status="reserved")

        # Not ready: enqueue is a no-op.
        before = conn.execute("SELECT COUNT(*) AS n FROM notification_outbox").fetchone()["n"]
        none_result = oa.enqueue_operator_agent_turn(
            conn,
            channel="telegram",
            channel_identity="tg:42",
            text="status of the fleet please",
        )
        expect(none_result is None, "enqueue before ready must be a no-op")
        expect(conn.execute("SELECT COUNT(*) AS n FROM notification_outbox").fetchone()["n"] == before, "no notification queued before ready")

        conn.execute("UPDATE arclink_deployments SET status = 'active' WHERE deployment_id = 'operator'")
        conn.commit()
        nid = oa.enqueue_operator_agent_turn(
            conn,
            channel="telegram",
            channel_identity="tg:42",
            text="what is broken on the fleet?",
            reply_to_message_id="5005",
            display_name="Ops",
        )
        expect(isinstance(nid, int) and nid > 0, f"expected a notification id, got {nid}")
        row = conn.execute(
            "SELECT target_kind, target_id, channel_kind, message, extra_json FROM notification_outbox ORDER BY id DESC LIMIT 1"
        ).fetchone()
        expect(row["target_kind"] == "public-agent-turn", dict(row))
        expect(row["target_id"] == "tg:42", dict(row))
        expect(row["channel_kind"] == "telegram", dict(row))
        expect(row["message"] == "what is broken on the fleet?", dict(row))
        extra = json.loads(row["extra_json"]) if row["extra_json"] else {}
        expect(extra.get("deployment_id") == "operator", str(extra))
        expect(extra.get("source_kind") == "operator_chat", str(extra))
        expect(extra.get("telegram_reply_to_message_id") == "5005", str(extra))
        print("PASS test_operator_agent_turn_enqueues_only_when_ready")
    finally:
        cleanup(tmp, old_env)


def test_telegram_operator_free_form_routes_to_agent_or_intro() -> None:
    tmp, old_env, conn, control, oa = with_db()
    try:
        telegram = load_module(PYTHON_DIR / "arclink_telegram.py", "arclink_telegram_operator_free_form_test")
        env = {
            "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "telegram",
            "OPERATOR_NOTIFY_CHANNEL_ID": "42",
            "ARCLINK_OPERATOR_TELEGRAM_USER_IDS": "42",
        }
        parsed = {
            "chat_id": "42",
            "user_id": "42",
            "chat_type": "private",
            "text": "how is the fleet doing today?",
            "message_id": "7",
        }
        oa.ensure_operator_agent_user(conn, user_id="operator")
        oa.ensure_operator_agent_deployment(conn, user_id="operator", status="reserved")

        # Agent not ready: free-form text returns the Raven control intro.
        intro = telegram._handle_operator_telegram_update(conn, parsed, env=env)
        expect(intro is not None and intro.get("action") == "operator_raven_intro", str(intro))
        expect(conn.execute("SELECT COUNT(*) AS n FROM notification_outbox").fetchone()["n"] == 0, "no turn queued before agent is ready")

        # Promote the agent => free-form text routes to it.
        conn.execute("UPDATE arclink_deployments SET status = 'active' WHERE deployment_id = 'operator'")
        conn.commit()
        routed = telegram._handle_operator_telegram_update(conn, parsed, env=env)
        expect(routed is not None and routed.get("action") == "operator_agent_turn_queued", str(routed))
        expect(routed.get("text") == "", "routed turn replies asynchronously, no inline text")
        row = conn.execute(
            "SELECT target_kind, message, extra_json FROM notification_outbox ORDER BY id DESC LIMIT 1"
        ).fetchone()
        expect(row is not None and row["target_kind"] == "public-agent-turn", str(dict(row) if row else None))
        expect(row["message"] == "how is the fleet doing today?", dict(row))

        # A slash control command still reaches Raven, not the agent.
        status = telegram._handle_operator_telegram_update(
            conn, {**parsed, "text": "/operator_status"}, env=env
        )
        expect(status is not None and "operator_raven" in str(status.get("action")), str(status))
        print("PASS test_telegram_operator_free_form_routes_to_agent_or_intro")
    finally:
        cleanup(tmp, old_env)


if __name__ == "__main__":
    test_operator_agent_lifecycle_and_single_invariant()
    test_operator_agent_turn_enqueues_only_when_ready()
    test_telegram_operator_free_form_routes_to_agent_or_intro()
    print("PASS all operator agent tests")
