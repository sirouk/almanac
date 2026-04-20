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
ONBOARDING_PY = PYTHON_DIR / "almanac_onboarding_flow.py"


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
        "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "tui-only",
        "OPERATOR_NOTIFY_CHANNEL_ID": "",
        "ALMANAC_MODEL_PRESET_CODEX": "openai:codex",
        "ALMANAC_MODEL_PRESET_OPUS": "anthropic:claude-opus",
        "ALMANAC_MODEL_PRESET_CHUTES": "chutes:auto-failover",
        "ALMANAC_CURATOR_CHANNELS": "tui-only",
        "ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "0",
        "ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED": "0",
    }


def test_cancel_wipes_pre_provision_onboarding_state() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_onboarding_cancel_pre_test")
    onboarding = load_module(ONBOARDING_PY, "almanac_onboarding_cancel_pre_test")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            session = control.start_onboarding_session(
                conn,
                cfg,
                platform="discord",
                chat_id="dm-42",
                sender_id="user-42",
                sender_username="sirouk",
                sender_display_name="Chris",
            )
            session_id = str(session["session_id"])
            bot_token_path = control.write_onboarding_platform_token_secret(cfg, session_id, "discord", "discord-bot-token")
            provider_secret_path = control.write_onboarding_secret(cfg, session_id, "openai-codex", "provider-token")
            control.save_onboarding_session(
                conn,
                session_id=session_id,
                state="awaiting-provider-browser-auth",
                answers={
                    "full_name": "Chris",
                    "unix_user": "sirouk",
                    "preferred_bot_name": "KorBon",
                    "model_preset": "codex",
                    "provider_browser_auth": {"status": "pending"},
                    "pending_provider_secret_path": provider_secret_path,
                },
                pending_bot_token="",
                pending_bot_token_path=bot_token_path,
                operator_notified_at=control.utc_now_iso(),
                approved_at=control.utc_now_iso(),
                approved_by_actor="operator",
            )

            messages = onboarding.process_onboarding_message(
                cfg,
                onboarding.IncomingMessage(
                    platform="discord",
                    chat_id="dm-42",
                    sender_id="user-42",
                    sender_username="sirouk",
                    sender_display_name="Chris",
                    text="/cancel",
                ),
                validate_bot_token=lambda raw: onboarding.BotIdentity(bot_id="1"),
            )

            expect(len(messages) == 1, f"expected one outbound message, got {messages}")
            expect("wiped the staged onboarding state" in messages[0].text, messages[0].text)

            cancelled = control.get_onboarding_session(conn, session_id, redact_secrets=False)
            expect(cancelled is not None, "expected cancelled onboarding session to remain queryable")
            expect(str(cancelled["state"]) == "cancelled", f"expected cancelled state, got {cancelled}")
            expect((cancelled.get("answers") or {}) == {}, f"expected answers to be wiped, got {cancelled}")
            expect(str(cancelled.get("pending_bot_token_path") or "") == "", f"expected pending bot token path to clear, got {cancelled}")
            expect(str(cancelled.get("approved_by_actor") or "") == "", f"expected approval metadata to clear, got {cancelled}")
            expect(not Path(bot_token_path).exists(), f"expected bot token secret to be deleted: {bot_token_path}")
            expect(not Path(provider_secret_path).exists(), f"expected provider secret to be deleted: {provider_secret_path}")
            expect(not (cfg.state_dir / "onboarding-secrets" / session_id).exists(), "expected per-session secret dir to be removed")
            active = control.find_active_onboarding_session(conn, platform="discord", sender_id="user-42")
            expect(active is None, f"expected no active onboarding session after cancel, got {active}")
            print("PASS test_cancel_wipes_pre_provision_onboarding_state")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_cancel_refuses_after_provisioning_has_started() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_onboarding_cancel_post_test")
    onboarding = load_module(ONBOARDING_PY, "almanac_onboarding_cancel_post_test")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            session = control.start_onboarding_session(
                conn,
                cfg,
                platform="discord",
                chat_id="dm-84",
                sender_id="user-84",
                sender_username="sirouk",
                sender_display_name="Chris",
            )
            session_id = str(session["session_id"])
            bot_token_path = control.write_onboarding_platform_token_secret(cfg, session_id, "discord", "discord-bot-token")
            provider_secret_path = control.write_onboarding_secret(cfg, session_id, "openai-codex", "provider-token")
            control.save_onboarding_session(
                conn,
                session_id=session_id,
                state="provision-pending",
                answers={
                    "full_name": "Chris",
                    "unix_user": "sirouk",
                    "preferred_bot_name": "KorBon",
                    "model_preset": "codex",
                    "pending_provider_secret_path": provider_secret_path,
                },
                linked_request_id="req_cancel_me",
                linked_agent_id="agent-sirouk",
                pending_bot_token="",
                pending_bot_token_path=bot_token_path,
                approved_at=control.utc_now_iso(),
                approved_by_actor="operator",
            )

            messages = onboarding.process_onboarding_message(
                cfg,
                onboarding.IncomingMessage(
                    platform="discord",
                    chat_id="dm-84",
                    sender_id="user-84",
                    sender_username="sirouk",
                    sender_display_name="Chris",
                    text="/cancel",
                ),
                validate_bot_token=lambda raw: onboarding.BotIdentity(bot_id="1"),
            )

            expect(len(messages) == 1, f"expected one outbound message, got {messages}")
            expect("already started provisioning your lane" in messages[0].text, messages[0].text)
            expect("req_cancel_me" in messages[0].text, messages[0].text)

            unchanged = control.get_onboarding_session(conn, session_id, redact_secrets=False)
            expect(unchanged is not None, "expected provision-pending session to remain queryable")
            expect(str(unchanged["state"]) == "provision-pending", f"expected session to stay provision-pending, got {unchanged}")
            expect(
                str((unchanged.get("answers") or {}).get("pending_provider_secret_path") or "") == provider_secret_path,
                f"expected provider secret path to remain staged, got {unchanged}",
            )
            expect(Path(bot_token_path).exists(), f"expected bot token secret to remain staged: {bot_token_path}")
            expect(Path(provider_secret_path).exists(), f"expected provider secret to remain staged: {provider_secret_path}")
            active = control.find_active_onboarding_session(conn, platform="discord", sender_id="user-84")
            expect(active is not None, "expected provision-pending session to remain active")
            print("PASS test_cancel_refuses_after_provisioning_has_started")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def main() -> int:
    test_cancel_wipes_pre_provision_onboarding_state()
    test_cancel_refuses_after_provisioning_has_started()
    print("PASS all 2 onboarding cancel regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
