#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
CONTROL_PY = PYTHON_DIR / "almanac_control.py"
ONBOARDING_PY = PYTHON_DIR / "almanac_onboarding_flow.py"
PROVISIONER_PY = PYTHON_DIR / "almanac_enrollment_provisioner.py"


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
        "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "discord",
        "OPERATOR_NOTIFY_CHANNEL_ID": "999",
        "ALMANAC_MODEL_PRESET_CODEX": "openai:codex",
        "ALMANAC_MODEL_PRESET_OPUS": "anthropic:claude-opus",
        "ALMANAC_MODEL_PRESET_CHUTES": "chutes:model-router",
        "ALMANAC_CURATOR_CHANNELS": "tui-only,discord",
        "ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "0",
        "ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED": "1",
        "ENABLE_TAILSCALE_SERVE": "1",
        "TAILSCALE_DNS_NAME": "kor.tail77f45e.ts.net",
    }


def insert_agent(mod, conn, *, agent_id: str, unix_user: str, hermes_home: Path) -> None:
    now = mod.utc_now_iso()
    conn.execute(
        """
        INSERT INTO agents (
          agent_id, role, unix_user, display_name, status, hermes_home, manifest_path,
          archived_state_path, model_preset, model_string, channels_json,
          allowed_mcps_json, home_channel_json, operator_notify_channel_json,
          created_at, last_enrolled_at
        ) VALUES (?, 'user', ?, ?, 'active', ?, ?, NULL, 'opus', 'anthropic:claude-opus', '["tui-only","discord"]', '[]', '{}', '{}', ?, ?)
        """,
        (agent_id, unix_user, unix_user, str(hermes_home), str(hermes_home / "manifest.json"), now, now),
    )
    conn.commit()


def test_completed_onboarding_user_can_queue_remote_ssh_key_install() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_remote_ssh_key_queue_test")
    onboarding = load_module(ONBOARDING_PY, "almanac_onboarding_remote_ssh_key_queue_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            hermes_home = root / "homes" / "sirouk" / ".local" / "share" / "almanac-agent" / "hermes-home"
            (hermes_home / "state").mkdir(parents=True, exist_ok=True)
            (hermes_home / "state" / "almanac-web-access.json").write_text(
                json.dumps({"unix_user": "sirouk", "username": "sirouk", "tailscale_host": "kor.tail77f45e.ts.net"}),
                encoding="utf-8",
            )
            insert_agent(control, conn, agent_id="agent-sirouk", unix_user="sirouk", hermes_home=hermes_home)
            session = control.start_onboarding_session(
                conn,
                cfg,
                platform="discord",
                chat_id="555",
                sender_id="777",
                sender_username="sirouk",
                sender_display_name="Chris",
            )
            control.save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="completed",
                linked_agent_id="agent-sirouk",
                answers={"unix_user": "sirouk", "bot_platform": "discord"},
            )
            pubkey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIRemoteHermesKey almanac-remote-hermes@test"
            replies = onboarding.process_onboarding_message(
                cfg,
                onboarding.IncomingMessage(
                    platform="discord",
                    chat_id="555",
                    sender_id="777",
                    sender_username="sirouk",
                    sender_display_name="Chris",
                    text=f"/ssh-key {pubkey}",
                ),
                validate_bot_token=lambda token: onboarding.BotIdentity(bot_id="unused"),
            )
            expect(len(replies) == 1, str(replies))
            expect("Remote agent key install queued for `sirouk`" in replies[0].text, replies[0].text)
            expect("generated `hermes-almanac-*` wrapper" in replies[0].text, replies[0].text)
            expect("remote config, skills, MCP tools, and files" in replies[0].text, replies[0].text)
            row = conn.execute("SELECT * FROM operator_actions WHERE action_kind = 'install-agent-ssh-key'").fetchone()
            expect(row is not None, "expected queued operator action")
            payload = json.loads(str(row["requested_target"]))
            expect(payload["unix_user"] == "sirouk", str(payload))
            expect(payload["pubkey"] == pubkey, str(payload))
            expect(payload["tailscale_host"] == "kor.tail77f45e.ts.net", str(payload))
            print("PASS test_completed_onboarding_user_can_queue_remote_ssh_key_install")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_remote_ssh_key_install_requires_completed_sender_lane() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_remote_ssh_key_requires_lane_test")
    onboarding = load_module(ONBOARDING_PY, "almanac_onboarding_remote_ssh_key_requires_lane_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            control.connect_db(cfg)
            replies = onboarding.process_onboarding_message(
                cfg,
                onboarding.IncomingMessage(
                    platform="discord",
                    chat_id="555",
                    sender_id="777",
                    sender_username="sirouk",
                    sender_display_name="Chris",
                    text="/ssh-key ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIRemoteHermesKey test",
                ),
                validate_bot_token=lambda token: onboarding.BotIdentity(bot_id="unused"),
            )
            expect(len(replies) == 1, str(replies))
            expect("after your agent lane is completed" in replies[0].text, replies[0].text)
            print("PASS test_remote_ssh_key_install_requires_completed_sender_lane")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_root_maintenance_reclaims_stale_remote_ssh_key_action_and_notifies_user() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_remote_ssh_key_root_test")
    provisioner = load_module(PROVISIONER_PY, "almanac_enrollment_provisioner_remote_ssh_key_root_test")
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
                chat_id="555",
                sender_id="777",
                sender_username="sirouk",
                sender_display_name="Chris",
            )
            session = control.save_onboarding_session(
                conn,
                session_id=str(session["session_id"]),
                state="completed",
                linked_agent_id="agent-sirouk",
                answers={"unix_user": "sirouk"},
            )
            pubkey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIRemoteHermesKey almanac-remote-hermes@test"
            action, _created = control.request_operator_action(
                conn,
                action_kind="install-agent-ssh-key",
                requested_by="sirouk",
                request_source="discord-remote-ssh-key",
                requested_target=json.dumps(
                    {
                        "session_id": session["session_id"],
                        "agent_id": "agent-sirouk",
                        "unix_user": "sirouk",
                        "pubkey": pubkey,
                        "tailscale_host": "kor.tail77f45e.ts.net",
                    },
                    sort_keys=True,
                ),
                dedupe_by_target=True,
            )
            action_id = int(action["id"])
            control.mark_operator_action_running(
                conn,
                action_id=action_id,
                note="stale in-flight action from crashed process",
                log_path=str(root / "missing.log"),
            )
            conn.execute(
                "UPDATE operator_actions SET started_at = ? WHERE id = ?",
                ("2000-01-01T00:00:00+00:00", action_id),
            )
            conn.commit()

            calls: list[tuple[str, str]] = []
            user_messages: list[str] = []

            def fake_install(cfg, *, unix_user, pubkey, log_path):
                calls.append((unix_user, pubkey))
                log_path.write_text("Installed SSH key\n", encoding="utf-8")
                return subprocess.CompletedProcess(args=["install-agent-ssh-key"], returncode=0)

            provisioner._run_install_agent_ssh_key = fake_install
            provisioner.send_session_message = lambda cfg, session, text, **kwargs: user_messages.append(text)
            provisioner._run_pending_remote_ssh_key_actions(conn, cfg)

            expect(calls == [("sirouk", pubkey)], str(calls))
            refreshed = conn.execute("SELECT status, note FROM operator_actions WHERE action_kind = 'install-agent-ssh-key'").fetchone()
            expect(refreshed is not None and refreshed["status"] == "completed", str(dict(refreshed) if refreshed else {}))
            expect(user_messages and "hermes-almanac-*" in user_messages[0], str(user_messages))
            expect(user_messages and "remote config, skills, MCP tools, and files" in user_messages[0], str(user_messages))
            expect(user_messages and "ssh sirouk@kor.tail77f45e.ts.net" in user_messages[0], str(user_messages))
            print("PASS test_root_maintenance_reclaims_stale_remote_ssh_key_action_and_notifies_user")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_root_maintenance_install_ssh_key_uses_discovered_config_file() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_remote_ssh_key_config_env_test")
    provisioner = load_module(PROVISIONER_PY, "almanac_enrollment_provisioner_remote_ssh_key_config_env_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            seen: dict[str, object] = {}

            def fake_run(args, *, cwd, env, text, stdout, stderr, check):
                seen["args"] = list(args)
                seen["cwd"] = cwd
                seen["config_file"] = env.get("ALMANAC_CONFIG_FILE")
                stdout.write("Installed SSH key\n")
                return subprocess.CompletedProcess(args=args, returncode=0)

            original_run = provisioner.subprocess.run
            provisioner.subprocess.run = fake_run
            try:
                result = provisioner._run_install_agent_ssh_key(
                    cfg,
                    unix_user="sirouk",
                    pubkey="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIRemoteHermesKey test",
                    log_path=root / "install.log",
                )
            finally:
                provisioner.subprocess.run = original_run

            expect(result.returncode == 0, str(result))
            expect(seen.get("config_file") == str(config_path), str(seen))
            expect(str(seen.get("cwd")) == str(REPO), str(seen))
            expect("install-agent-ssh-key.sh" in " ".join(str(x) for x in seen.get("args", [])), str(seen))
            print("PASS test_root_maintenance_install_ssh_key_uses_discovered_config_file")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def main() -> int:
    test_completed_onboarding_user_can_queue_remote_ssh_key_install()
    test_remote_ssh_key_install_requires_completed_sender_lane()
    test_root_maintenance_reclaims_stale_remote_ssh_key_action_and_notifies_user()
    test_root_maintenance_install_ssh_key_uses_discovered_config_file()
    print("PASS all 4 remote SSH key onboarding tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
