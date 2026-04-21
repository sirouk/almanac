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
CONTROL_PY = PYTHON_DIR / "almanac_control.py"
CURATOR_ONBOARDING_PY = PYTHON_DIR / "almanac_curator_onboarding.py"


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


def test_telegram_operator_approve_callback_replaces_message_and_clears_buttons() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_curator_onboarding_callback_test")
    curator = load_module(CURATOR_ONBOARDING_PY, "almanac_curator_onboarding_callback_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(
            config_path,
            {
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
                "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "telegram",
                "OPERATOR_NOTIFY_CHANNEL_ID": "42",
            },
        )
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            session = control.start_onboarding_session(
                conn,
                cfg,
                platform="telegram",
                chat_id="100",
                sender_id="100",
                sender_username="sirouk",
                sender_display_name="Chris",
            )
            session = control.save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="awaiting-operator-approval",
                answers={"full_name": "Chris"},
            )

            replacements: list[str] = []
            answers: list[str] = []
            outbound: list[str] = []

            curator.notify_session_state = lambda cfg, updated: None
            curator._replace_operator_callback_message = (
                lambda bot_token, callback_query, text: replacements.append(text)
            )
            curator._clear_operator_callback_buttons = lambda bot_token, callback_query: outbound.append("cleared")
            curator.telegram_answer_callback_query = (
                lambda **kwargs: answers.append(str(kwargs.get("text") or ""))
            )
            curator.send_text = lambda bot_token, chat_id, text, **kwargs: outbound.append(text)

            curator._handle_operator_callback(
                cfg=cfg,
                bot_token="test-token",
                callback_query={
                    "id": "cb_1",
                    "data": f"almanac:onboarding:approve:{session['session_id']}",
                    "message": {
                        "chat": {"id": "42", "type": "private"},
                        "message_id": 7,
                        "text": "Review this onboarding request.",
                    },
                    "from": {"id": "42", "username": "cksirouk"},
                },
            )

            refreshed = control.get_onboarding_session(conn, str(session["session_id"]))
            expect(refreshed is not None, "expected refreshed onboarding session")
            expect(str(refreshed.get("state") or "") == "awaiting-bot-token", str(refreshed))
            expect(len(replacements) == 1, str(replacements))
            expect("Approved" in replacements[0], replacements[0])
            expect("@cksirouk" in replacements[0], replacements[0])
            expect(outbound == [], str(outbound))
            expect(len(answers) == 1 and "Approved" in answers[0], str(answers))
            print("PASS test_telegram_operator_approve_callback_replaces_message_and_clears_buttons")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def main() -> int:
    test_telegram_operator_approve_callback_replaces_message_and_clears_buttons()
    print("PASS all 1 curator onboarding regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
