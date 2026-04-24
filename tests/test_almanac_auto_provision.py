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
PROVISIONER_PY = REPO / "python" / "almanac_enrollment_provisioner.py"
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
        "ALMANAC_MODEL_PRESET_CHUTES": "chutes:model-router",
        "ALMANAC_CURATOR_CHANNELS": "tui-only",
        "ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "0",
        "ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED": "0",
    }


def insert_auto_provision_request(mod, conn, request_id: str, unix_user: str = "autoprovbot") -> None:
    now = mod.utc_now_iso()
    conn.execute(
        """
        INSERT INTO bootstrap_requests (
          request_id, requester_identity, unix_user, source_ip, requested_at, expires_at,
          status, auto_provision, requested_model_preset, requested_channels_json,
          approval_surface, approval_actor, approved_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'approved', 1, ?, ?, ?, ?, ?)
        """,
        (
            request_id,
            "Remote Auto",
            unix_user,
            "127.0.0.1",
            now,
            now,
            "codex",
            json.dumps(["tui-only"]),
            "ctl",
            "test",
            now,
        ),
    )
    conn.commit()


def test_mark_auto_provision_started_claims_only_once_until_finished() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_auto_provision_claim_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_auto_provision_request(mod, conn, "req_claim")

            first_attempt = mod.mark_auto_provision_started(conn, "req_claim")
            second_attempt = mod.mark_auto_provision_started(conn, "req_claim")
            row = conn.execute(
                "SELECT provision_attempts, provision_started_at FROM bootstrap_requests WHERE request_id = ?",
                ("req_claim",),
            ).fetchone()

            expect(first_attempt == 1, f"expected first claim attempt to be 1, got {first_attempt}")
            expect(second_attempt == 0, f"expected second claim to be rejected, got {second_attempt}")
            expect(int(row["provision_attempts"] or 0) == 1, f"expected attempts to stay at 1, got {dict(row)}")
            expect(bool(row["provision_started_at"]), f"expected provision_started_at to be set, got {dict(row)}")

            mod.mark_auto_provision_finished(conn, request_id="req_claim", error="boom", next_attempt_at="")
            retried_attempt = mod.mark_auto_provision_started(conn, "req_claim")
            row = conn.execute(
                "SELECT provision_attempts, provision_started_at, provision_error FROM bootstrap_requests WHERE request_id = ?",
                ("req_claim",),
            ).fetchone()
            expect(retried_attempt == 2, f"expected retry claim to become attempt 2 after finish(error), got {retried_attempt}")
            expect(int(row["provision_attempts"] or 0) == 2, f"expected attempts to become 2 after retry, got {dict(row)}")
            expect(bool(row["provision_started_at"]), f"expected retry to set provision_started_at again, got {dict(row)}")
            expect(not row["provision_error"], f"expected retry claim to clear provision_error, got {dict(row)}")
            print("PASS test_mark_auto_provision_started_claims_only_once_until_finished")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_stale_auto_provision_claims_are_reclaimable() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_auto_provision_stale_claim_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            insert_auto_provision_request(mod, conn, "req_stale")

            first_attempt = mod.mark_auto_provision_started(conn, "req_stale")
            pending = mod.list_pending_auto_provision_requests(conn, cfg)
            expect(first_attempt == 1, f"expected first stale-claim attempt to be 1, got {first_attempt}")
            expect(not pending, f"freshly claimed request should not remain pending, got {[row['request_id'] for row in pending]}")

            conn.execute(
                "UPDATE bootstrap_requests SET provision_started_at = ? WHERE request_id = ?",
                ("2000-01-01T00:00:00+00:00", "req_stale"),
            )
            conn.commit()

            pending = mod.list_pending_auto_provision_requests(conn, cfg)
            expect([row["request_id"] for row in pending] == ["req_stale"], f"expected stale request to be reclaimable, got {pending}")
            reclaimed_attempt = mod.mark_auto_provision_started(conn, "req_stale")
            expect(reclaimed_attempt == 2, f"expected stale reclaim to become attempt 2, got {reclaimed_attempt}")
            print("PASS test_stale_auto_provision_claims_are_reclaimable")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_run_one_uses_devnull_stdin_for_headless_init() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_auto_provision_run_one_control")
    provisioner = load_module(PROVISIONER_PY, "almanac_enrollment_provisioner_stdin_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(config_path, config_values(root))
        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            conn = control.connect_db(cfg)
            insert_auto_provision_request(control, conn, "req_run_one")
            row = control.list_pending_auto_provision_requests(conn, cfg)[0]

            calls: list[dict[str, object]] = []
            memory_refresh_calls: list[dict[str, object]] = []

            def fake_run(cmd, **kwargs):
                calls.append({"cmd": cmd, **kwargs})
                return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

            provisioner.ensure_unix_user_ready = lambda unix_user: {"home": str(root / "home" / unix_user), "uid": 1234}
            provisioner._grant_auto_provision_access = lambda cfg, *, unix_user, agent_id: None
            provisioner._wait_for_user_bus = lambda uid, timeout_seconds=15: None
            provisioner.issue_auto_provision_token = lambda conn, request_id: {"raw_token": "tok_test"}
            provisioner.get_agent = lambda conn, agent_id: {"hermes_home": str(root / "home" / "user" / ".local" / "share" / "almanac-agent" / "hermes-home")}
            provisioner._provision_user_access_surfaces = lambda *args, **kwargs: {"dashboard_url": "", "code_url": "", "username": "tester", "password": "secret"}
            provisioner._refresh_user_agent_memory = lambda *args, **kwargs: memory_refresh_calls.append(kwargs)
            provisioner.subprocess.run = fake_run

            provisioner._run_one(conn, cfg, row)

            expect(calls, "expected _run_one to invoke subprocess.run for init.sh")
            last = calls[-1]
            expect(last.get("stdin") is subprocess.DEVNULL, f"expected headless init to use DEVNULL stdin, got {last}")
            env = last.get("env") or {}
            expect(env.get("ALMANAC_BOOTSTRAP_REQUEST_ID") == "req_run_one", env)
            expect(env.get("ALMANAC_INIT_MODEL_PRESET") == "codex", env)
            expect(env.get("ALMANAC_SHARED_REPO_DIR") == str(REPO), env)
            expect("ALMANAC_SSOT_NOTION_TOKEN" not in env, env)
            expect("POSTGRES_PASSWORD" not in env, env)
            expect(len(memory_refresh_calls) == 1, f"expected one managed-memory refresh call, got {memory_refresh_calls}")
            expect(memory_refresh_calls[0]["agent_id"] == "agent-autoprovbot", memory_refresh_calls)
            print("PASS test_run_one_uses_devnull_stdin_for_headless_init")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_run_as_user_scrubs_ambient_env() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    provisioner = load_module(PROVISIONER_PY, "almanac_enrollment_provisioner_env_scrub_test")
    calls: list[dict[str, object]] = []

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": cmd, **kwargs})
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    old_env = os.environ.copy()
    os.environ["ALMANAC_SSOT_NOTION_TOKEN"] = "secret-should-not-leak"
    os.environ["POSTGRES_PASSWORD"] = "postgres-should-not-leak"
    os.environ["PATH"] = "/tmp/not-the-real-path"
    os.environ["LANG"] = "en_US.UTF-8"
    provisioner.subprocess.run = fake_run
    try:
        provisioner._run_as_user(
            unix_user="scrubtest",
            home=Path("/home/scrubtest"),
            uid=1234,
            hermes_home=Path("/home/scrubtest/.local/share/almanac-agent/hermes-home"),
            cmd=["systemctl", "--user", "is-active", "dummy.service"],
        )
        expect(calls, "expected _run_as_user to invoke subprocess.run")
        env = calls[-1].get("env") or {}
        expect(env.get("HOME") == "/home/scrubtest", env)
        expect(env.get("USER") == "scrubtest", env)
        expect(env.get("HERMES_HOME") == "/home/scrubtest/.local/share/almanac-agent/hermes-home", env)
        expect(env.get("LANG") == "en_US.UTF-8", env)
        expect(env.get("PATH") == provisioner._DEFAULT_USER_PATH, env)
        expect("ALMANAC_SSOT_NOTION_TOKEN" not in env, env)
        expect("POSTGRES_PASSWORD" not in env, env)
        print("PASS test_run_as_user_scrubs_ambient_env")
    finally:
        os.environ.clear()
        os.environ.update(old_env)


def main() -> int:
    test_mark_auto_provision_started_claims_only_once_until_finished()
    test_stale_auto_provision_claims_are_reclaimable()
    test_run_one_uses_devnull_stdin_for_headless_init()
    test_run_as_user_scrubs_ambient_env()
    print("PASS all 4 auto-provision regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
