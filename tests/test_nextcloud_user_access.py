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
CONTROL_PY = REPO / "python" / "arclink_control.py"
NEXTCLOUD_ACCESS_PY = REPO / "python" / "arclink_nextcloud_access.py"
PYTHON_DIR = REPO / "python"


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


def config_values(root: Path, *, enable_nextcloud: str) -> dict[str, str]:
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
        "ARCLINK_NOTION_WEBHOOK_HOST": "127.0.0.1",
        "ARCLINK_NOTION_WEBHOOK_PORT": "8283",
        "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "tui-only",
        "OPERATOR_NOTIFY_CHANNEL_ID": "",
        "ARCLINK_MODEL_PRESET_CODEX": "openai:codex",
        "ARCLINK_MODEL_PRESET_OPUS": "anthropic:claude-opus",
        "ARCLINK_MODEL_PRESET_CHUTES": "chutes:model-router",
        "ARCLINK_CURATOR_CHANNELS": "tui-only",
        "ARCLINK_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "0",
        "ARCLINK_CURATOR_DISCORD_ONBOARDING_ENABLED": "0",
        "ENABLE_NEXTCLOUD": enable_nextcloud,
        "ARCLINK_NAME": "arclink",
    }


def test_sync_nextcloud_user_access_skips_when_disabled() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_nextcloud_access_disabled_test")
    nextcloud_access = load_module(NEXTCLOUD_ACCESS_PY, "arclink_nextcloud_access_disabled_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root, enable_nextcloud="0"))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()

            def fail_occ(*args, **kwargs):
                raise AssertionError("Nextcloud commands should not run while disabled")

            nextcloud_access._nextcloud_occ = fail_occ
            result = nextcloud_access.sync_nextcloud_user_access(
                cfg,
                username="alex",
                password="sup3rsecret",
                display_name="Alex",
            )
            expect(result == {"enabled": False, "synced": False, "skipped": "disabled"}, str(result))
            print("PASS test_sync_nextcloud_user_access_skips_when_disabled")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_sync_nextcloud_user_access_creates_missing_user() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_nextcloud_access_create_test")
    nextcloud_access = load_module(NEXTCLOUD_ACCESS_PY, "arclink_nextcloud_access_create_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root, enable_nextcloud="1"))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            calls: list[tuple[list[str], dict[str, str] | None, bool]] = []

            def fake_occ(cfg_arg, *args: str, extra_env=None, check=True):
                calls.append((list(args), extra_env, check))
                if list(args) == ["status", "--output=json"]:
                    return subprocess.CompletedProcess(list(args), 0, stdout="{}", stderr="")
                if list(args) == ["user:info", "sir-ouk", "--output=json"]:
                    return subprocess.CompletedProcess(list(args), 1, stdout="", stderr="missing")
                if args and args[0] == "user:add":
                    return subprocess.CompletedProcess(list(args), 0, stdout="", stderr="")
                raise AssertionError(f"unexpected occ call: args={args!r} extra_env={extra_env!r}")

            nextcloud_access._nextcloud_occ = fake_occ
            result = nextcloud_access.sync_nextcloud_user_access(
                cfg,
                username="Sir Ouk",
                password="sup3rsecret",
                display_name="Alex Example",
            )

            expect(result["enabled"] is True, str(result))
            expect(result["synced"] is True, str(result))
            expect(result["created"] is True, str(result))
            expect(result["username"] == "sir-ouk", str(result))
            expect(len(calls) == 3, f"expected 3 occ calls, got {calls!r}")
            create_args, create_env, _ = calls[-1]
            expect(create_args[0:3] == ["user:add", "--password-from-env", "--no-interaction"], str(create_args))
            expect("--display-name=Alex Example" in create_args, str(create_args))
            expect(create_args[-3:] == ["-g", "arclink-users", "sir-ouk"], str(create_args))
            expect(create_env == {"OC_PASS": "sup3rsecret"}, str(create_env))
            print("PASS test_sync_nextcloud_user_access_creates_missing_user")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_sync_nextcloud_user_access_resets_existing_user_password() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_nextcloud_access_reset_test")
    nextcloud_access = load_module(NEXTCLOUD_ACCESS_PY, "arclink_nextcloud_access_reset_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root, enable_nextcloud="1"))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            calls: list[tuple[list[str], dict[str, str] | None, bool]] = []

            def fake_occ(cfg_arg, *args: str, extra_env=None, check=True):
                calls.append((list(args), extra_env, check))
                if list(args) == ["status", "--output=json"]:
                    return subprocess.CompletedProcess(list(args), 0, stdout="{}", stderr="")
                if list(args) == ["user:info", "alex", "--output=json"]:
                    return subprocess.CompletedProcess(list(args), 0, stdout="{}", stderr="")
                if args and args[0] == "user:resetpassword":
                    return subprocess.CompletedProcess(list(args), 0, stdout="", stderr="")
                raise AssertionError(f"unexpected occ call: args={args!r} extra_env={extra_env!r}")

            nextcloud_access._nextcloud_occ = fake_occ
            result = nextcloud_access.sync_nextcloud_user_access(
                cfg,
                username="alex",
                password="sup3rsecret",
                display_name="Alex Example",
            )

            expect(result["enabled"] is True, str(result))
            expect(result["synced"] is True, str(result))
            expect(result["created"] is False, str(result))
            expect(len(calls) == 3, f"expected 3 occ calls, got {calls!r}")
            reset_args, reset_env, _ = calls[-1]
            expect(
                reset_args == ["user:resetpassword", "--password-from-env", "--no-interaction", "alex"],
                str(reset_args),
            )
            expect(reset_env == {"OC_PASS": "sup3rsecret"}, str(reset_env))
            print("PASS test_sync_nextcloud_user_access_resets_existing_user_password")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_delete_nextcloud_user_access_skips_when_disabled() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_nextcloud_access_delete_disabled_test")
    nextcloud_access = load_module(NEXTCLOUD_ACCESS_PY, "arclink_nextcloud_access_delete_disabled_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root, enable_nextcloud="0"))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()

            def fail_occ(*args, **kwargs):
                raise AssertionError("Nextcloud commands should not run while disabled")

            nextcloud_access._nextcloud_occ = fail_occ
            result = nextcloud_access.delete_nextcloud_user_access(cfg, username="alex")
            expect(result == {"enabled": False, "deleted": False, "skipped": "disabled"}, str(result))
            print("PASS test_delete_nextcloud_user_access_skips_when_disabled")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_delete_nextcloud_user_access_deletes_existing_user() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_nextcloud_access_delete_test")
    nextcloud_access = load_module(NEXTCLOUD_ACCESS_PY, "arclink_nextcloud_access_delete_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root, enable_nextcloud="1"))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            calls: list[tuple[list[str], dict[str, str] | None, bool]] = []

            def fake_occ(cfg_arg, *args: str, extra_env=None, check=True):
                calls.append((list(args), extra_env, check))
                if list(args) == ["status", "--output=json"]:
                    return subprocess.CompletedProcess(list(args), 0, stdout="{}", stderr="")
                if list(args) == ["user:info", "alex", "--output=json"]:
                    return subprocess.CompletedProcess(list(args), 0, stdout="{}", stderr="")
                if list(args) == ["user:delete", "alex"]:
                    return subprocess.CompletedProcess(list(args), 0, stdout="", stderr="")
                raise AssertionError(f"unexpected occ call: args={args!r} extra_env={extra_env!r}")

            nextcloud_access._nextcloud_occ = fake_occ
            result = nextcloud_access.delete_nextcloud_user_access(cfg, username="alex")

            expect(result["enabled"] is True, str(result))
            expect(result["deleted"] is True, str(result))
            expect(result["exists"] is True, str(result))
            expect(len(calls) == 3, f"expected 3 occ calls, got {calls!r}")
            delete_args, delete_env, _ = calls[-1]
            expect(delete_args == ["user:delete", "alex"], str(delete_args))
            expect(delete_env is None, str(delete_env))
            print("PASS test_delete_nextcloud_user_access_deletes_existing_user")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_nextcloud_occ_scrubs_ambient_env() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_nextcloud_access_env_test")
    nextcloud_access = load_module(NEXTCLOUD_ACCESS_PY, "arclink_nextcloud_access_env_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "home-arclink").mkdir(parents=True, exist_ok=True)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root, enable_nextcloud="1"))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        os.environ["ARCLINK_SSOT_NOTION_TOKEN"] = "sentinel-secret"
        os.environ["POSTGRES_PASSWORD"] = "db-secret"
        os.environ["PATH"] = "/tmp/tainted"
        try:
            cfg = control.Config.from_env()
            captured: dict[str, object] = {}

            nextcloud_access._runtime_exec_base = lambda cfg_arg, extra_env=None: ["runuser", "-u", cfg_arg.arclink_user, "--", "podman", "exec", "app"]

            def fake_run(cmd, **kwargs):
                captured["cmd"] = cmd
                captured["env"] = kwargs.get("env")
                return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")

            nextcloud_access.subprocess.run = fake_run
            nextcloud_access._nextcloud_occ(cfg, "status", "--output=json")

            env = captured.get("env")
            expect(isinstance(env, dict), str(captured))
            env = dict(env)
            expect(env.get("PATH") == nextcloud_access._SAFE_HOST_PATH, str(env))
            expect(env.get("HOME") == str(cfg.arclink_home), str(env))
            expect(env.get("USER") == cfg.arclink_user, str(env))
            expect("ARCLINK_SSOT_NOTION_TOKEN" not in env, str(env))
            expect("POSTGRES_PASSWORD" not in env, str(env))
            print("PASS test_nextcloud_occ_scrubs_ambient_env")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_nextcloud_occ_uses_service_user_safe_cwd() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_nextcloud_occ_cwd_test")
    nextcloud_access = load_module(NEXTCLOUD_ACCESS_PY, "arclink_nextcloud_access_occ_cwd_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "home-arclink").mkdir(parents=True, exist_ok=True)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root, enable_nextcloud="1"))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            captured: dict[str, object] = {}

            nextcloud_access._runtime_exec_base = lambda cfg_arg, extra_env=None: ["runuser", "-u", cfg_arg.arclink_user, "--", "podman", "exec", "app"]

            def fake_run(cmd, **kwargs):
                captured["cmd"] = cmd
                captured["cwd"] = kwargs.get("cwd")
                return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")

            nextcloud_access.subprocess.run = fake_run
            nextcloud_access._nextcloud_occ(cfg, "status", "--output=json")

            expect(captured["cwd"] == str((root / "home-arclink").resolve()), str(captured))
            print("PASS test_nextcloud_occ_uses_service_user_safe_cwd")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_nextcloud_docker_mode_prefers_docker_exec() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_nextcloud_docker_exec_test")
    nextcloud_access = load_module(NEXTCLOUD_ACCESS_PY, "arclink_nextcloud_docker_exec_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, config_values(root, enable_nextcloud="1"))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        os.environ["ARCLINK_DOCKER_MODE"] = "1"
        os.environ["ARCLINK_NAME"] = "customlink"
        try:
            cfg = control.Config.from_env()
            original_which = nextcloud_access.shutil.which
            nextcloud_access.shutil.which = lambda name: f"/usr/bin/{name}" if name in {"docker", "podman"} else None
            try:
                cmd = nextcloud_access._runtime_exec_base(cfg, extra_env={"OC_PASS": "secret"})
            finally:
                nextcloud_access.shutil.which = original_which
            expect(cmd[:2] == ["/usr/bin/docker", "exec"], str(cmd))
            expect("podman" not in cmd, str(cmd))
            expect("-e" in cmd and "OC_PASS=secret" in cmd, str(cmd))
            expect(cmd[-2:] == ["33:33", "customlink-nextcloud-1"], str(cmd))
            print("PASS test_nextcloud_docker_mode_prefers_docker_exec")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def main() -> int:
    test_sync_nextcloud_user_access_skips_when_disabled()
    test_sync_nextcloud_user_access_creates_missing_user()
    test_sync_nextcloud_user_access_resets_existing_user_password()
    test_delete_nextcloud_user_access_skips_when_disabled()
    test_delete_nextcloud_user_access_deletes_existing_user()
    test_nextcloud_occ_scrubs_ambient_env()
    test_nextcloud_occ_uses_service_user_safe_cwd()
    test_nextcloud_docker_mode_prefers_docker_exec()
    print("PASS all 8 nextcloud access regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
