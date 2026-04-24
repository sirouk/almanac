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
CONTROL_PY = REPO / "python" / "almanac_control.py"
NEXTCLOUD_ACCESS_PY = REPO / "python" / "almanac_nextcloud_access.py"
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
        "ALMANAC_NOTION_WEBHOOK_HOST": "127.0.0.1",
        "ALMANAC_NOTION_WEBHOOK_PORT": "8283",
        "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "tui-only",
        "OPERATOR_NOTIFY_CHANNEL_ID": "",
        "ALMANAC_MODEL_PRESET_CODEX": "openai:codex",
        "ALMANAC_MODEL_PRESET_OPUS": "anthropic:claude-opus",
        "ALMANAC_MODEL_PRESET_CHUTES": "chutes:model-router",
        "ALMANAC_CURATOR_CHANNELS": "tui-only",
        "ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "0",
        "ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED": "0",
        "ENABLE_NEXTCLOUD": enable_nextcloud,
        "ALMANAC_NAME": "almanac",
    }


def test_sync_nextcloud_user_access_skips_when_disabled() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_nextcloud_access_disabled_test")
    nextcloud_access = load_module(NEXTCLOUD_ACCESS_PY, "almanac_nextcloud_access_disabled_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root, enable_nextcloud="0"))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()

            def fail_occ(*args, **kwargs):
                raise AssertionError("Nextcloud commands should not run while disabled")

            nextcloud_access._nextcloud_occ = fail_occ
            result = nextcloud_access.sync_nextcloud_user_access(
                cfg,
                username="sirouk",
                password="sup3rsecret",
                display_name="Chris",
            )
            expect(result == {"enabled": False, "synced": False, "skipped": "disabled"}, str(result))
            print("PASS test_sync_nextcloud_user_access_skips_when_disabled")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_sync_nextcloud_user_access_creates_missing_user() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_nextcloud_access_create_test")
    nextcloud_access = load_module(NEXTCLOUD_ACCESS_PY, "almanac_nextcloud_access_create_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root, enable_nextcloud="1"))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
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
                display_name="Chris Sirouk",
            )

            expect(result["enabled"] is True, str(result))
            expect(result["synced"] is True, str(result))
            expect(result["created"] is True, str(result))
            expect(result["username"] == "sir-ouk", str(result))
            expect(len(calls) == 3, f"expected 3 occ calls, got {calls!r}")
            create_args, create_env, _ = calls[-1]
            expect(create_args[0:3] == ["user:add", "--password-from-env", "--no-interaction"], str(create_args))
            expect("--display-name=Chris Sirouk" in create_args, str(create_args))
            expect(create_args[-3:] == ["-g", "almanac-users", "sir-ouk"], str(create_args))
            expect(create_env == {"OC_PASS": "sup3rsecret"}, str(create_env))
            print("PASS test_sync_nextcloud_user_access_creates_missing_user")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_sync_nextcloud_user_access_resets_existing_user_password() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_nextcloud_access_reset_test")
    nextcloud_access = load_module(NEXTCLOUD_ACCESS_PY, "almanac_nextcloud_access_reset_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root, enable_nextcloud="1"))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            calls: list[tuple[list[str], dict[str, str] | None, bool]] = []

            def fake_occ(cfg_arg, *args: str, extra_env=None, check=True):
                calls.append((list(args), extra_env, check))
                if list(args) == ["status", "--output=json"]:
                    return subprocess.CompletedProcess(list(args), 0, stdout="{}", stderr="")
                if list(args) == ["user:info", "sirouk", "--output=json"]:
                    return subprocess.CompletedProcess(list(args), 0, stdout="{}", stderr="")
                if args and args[0] == "user:resetpassword":
                    return subprocess.CompletedProcess(list(args), 0, stdout="", stderr="")
                raise AssertionError(f"unexpected occ call: args={args!r} extra_env={extra_env!r}")

            nextcloud_access._nextcloud_occ = fake_occ
            result = nextcloud_access.sync_nextcloud_user_access(
                cfg,
                username="sirouk",
                password="sup3rsecret",
                display_name="Chris Sirouk",
            )

            expect(result["enabled"] is True, str(result))
            expect(result["synced"] is True, str(result))
            expect(result["created"] is False, str(result))
            expect(len(calls) == 3, f"expected 3 occ calls, got {calls!r}")
            reset_args, reset_env, _ = calls[-1]
            expect(
                reset_args == ["user:resetpassword", "--password-from-env", "--no-interaction", "sirouk"],
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
    control = load_module(CONTROL_PY, "almanac_control_nextcloud_access_delete_disabled_test")
    nextcloud_access = load_module(NEXTCLOUD_ACCESS_PY, "almanac_nextcloud_access_delete_disabled_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root, enable_nextcloud="0"))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()

            def fail_occ(*args, **kwargs):
                raise AssertionError("Nextcloud commands should not run while disabled")

            nextcloud_access._nextcloud_occ = fail_occ
            result = nextcloud_access.delete_nextcloud_user_access(cfg, username="sirouk")
            expect(result == {"enabled": False, "deleted": False, "skipped": "disabled"}, str(result))
            print("PASS test_delete_nextcloud_user_access_skips_when_disabled")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_delete_nextcloud_user_access_deletes_existing_user() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_nextcloud_access_delete_test")
    nextcloud_access = load_module(NEXTCLOUD_ACCESS_PY, "almanac_nextcloud_access_delete_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root, enable_nextcloud="1"))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            calls: list[tuple[list[str], dict[str, str] | None, bool]] = []

            def fake_occ(cfg_arg, *args: str, extra_env=None, check=True):
                calls.append((list(args), extra_env, check))
                if list(args) == ["status", "--output=json"]:
                    return subprocess.CompletedProcess(list(args), 0, stdout="{}", stderr="")
                if list(args) == ["user:info", "sirouk", "--output=json"]:
                    return subprocess.CompletedProcess(list(args), 0, stdout="{}", stderr="")
                if list(args) == ["user:delete", "sirouk"]:
                    return subprocess.CompletedProcess(list(args), 0, stdout="", stderr="")
                raise AssertionError(f"unexpected occ call: args={args!r} extra_env={extra_env!r}")

            nextcloud_access._nextcloud_occ = fake_occ
            result = nextcloud_access.delete_nextcloud_user_access(cfg, username="sirouk")

            expect(result["enabled"] is True, str(result))
            expect(result["deleted"] is True, str(result))
            expect(result["exists"] is True, str(result))
            expect(len(calls) == 3, f"expected 3 occ calls, got {calls!r}")
            delete_args, delete_env, _ = calls[-1]
            expect(delete_args == ["user:delete", "sirouk"], str(delete_args))
            expect(delete_env is None, str(delete_env))
            print("PASS test_delete_nextcloud_user_access_deletes_existing_user")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_nextcloud_occ_scrubs_ambient_env() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_nextcloud_access_env_test")
    nextcloud_access = load_module(NEXTCLOUD_ACCESS_PY, "almanac_nextcloud_access_env_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "home-almanac").mkdir(parents=True, exist_ok=True)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root, enable_nextcloud="1"))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        os.environ["ALMANAC_SSOT_NOTION_TOKEN"] = "sentinel-secret"
        os.environ["POSTGRES_PASSWORD"] = "db-secret"
        os.environ["PATH"] = "/tmp/tainted"
        try:
            cfg = control.Config.from_env()
            captured: dict[str, object] = {}

            nextcloud_access._runtime_exec_base = lambda cfg_arg, extra_env=None: ["runuser", "-u", cfg_arg.almanac_user, "--", "podman", "exec", "app"]

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
            expect(env.get("HOME") == str(cfg.almanac_home), str(env))
            expect(env.get("USER") == cfg.almanac_user, str(env))
            expect("ALMANAC_SSOT_NOTION_TOKEN" not in env, str(env))
            expect("POSTGRES_PASSWORD" not in env, str(env))
            print("PASS test_nextcloud_occ_scrubs_ambient_env")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_nextcloud_occ_uses_service_user_safe_cwd() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_nextcloud_occ_cwd_test")
    nextcloud_access = load_module(NEXTCLOUD_ACCESS_PY, "almanac_nextcloud_access_occ_cwd_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "home-almanac").mkdir(parents=True, exist_ok=True)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root, enable_nextcloud="1"))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            captured: dict[str, object] = {}

            nextcloud_access._runtime_exec_base = lambda cfg_arg, extra_env=None: ["runuser", "-u", cfg_arg.almanac_user, "--", "podman", "exec", "app"]

            def fake_run(cmd, **kwargs):
                captured["cmd"] = cmd
                captured["cwd"] = kwargs.get("cwd")
                return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")

            nextcloud_access.subprocess.run = fake_run
            nextcloud_access._nextcloud_occ(cfg, "status", "--output=json")

            expect(captured["cwd"] == str(root / "home-almanac"), str(captured))
            print("PASS test_nextcloud_occ_uses_service_user_safe_cwd")
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
    print("PASS all 7 nextcloud access regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
