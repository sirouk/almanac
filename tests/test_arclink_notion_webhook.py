#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http import HTTPStatus
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
WEBHOOK_PY = PYTHON_DIR / "arclink_notion_webhook.py"
CONTROL_PY = PYTHON_DIR / "arclink_control.py"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _config_values(root: Path) -> dict[str, str]:
    return {
        "ARCLINK_USER": "arclink",
        "ARCLINK_HOME": str(root / "home-arclink"),
        "ARCLINK_REPO_DIR": str(root / "repo"),
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


def _write_config(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(f'{k}="{v}"' for k, v in values.items()) + "\n", encoding="utf-8")


def test_handle_verification_token_post_refuses_overwrite_until_reset() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_notion_webhook_test")
    webhook = load_module(WEBHOOK_PY, "arclink_notion_webhook_test")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        _write_config(config_path, _config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            with control.connect_db(cfg) as conn:
                # First handshake is rejected until an operator arms the install window.
                status, body = webhook.handle_verification_token_post(conn, "tok_initial_secret")
                expect(
                    status == HTTPStatus.PRECONDITION_FAILED,
                    f"expected PRECONDITION_FAILED before arming, got {status} {body}",
                )
                expect("not armed" in str(body.get("error") or "").lower(), str(body))

                armed = webhook.arm_verification_token_install(conn, ttl_seconds=600, actor="operator")
                expect(armed["armed"] is True, str(armed))
                expect(bool(armed["armed_until"]), str(armed))

                # Armed handshake stores the token and clears the arm window.
                status, body = webhook.handle_verification_token_post(conn, "tok_initial_secret")
                expect(status == HTTPStatus.OK, f"expected OK on first store, got {status} {body}")
                expect(body.get("status") == "verification_token_stored", str(body))
                stored = control.get_setting(conn, webhook.NOTION_WEBHOOK_VERIFICATION_TOKEN_KEY, "")
                expect(stored == "tok_initial_secret", f"expected token stored, got {stored!r}")
                armed_after, armed_until_after = webhook._verification_token_install_armed(conn)
                expect(not armed_after and armed_until_after == "", f"expected install window cleared, got {armed_after} {armed_until_after}")
                installed_at = control.get_setting(conn, webhook.NOTION_WEBHOOK_VERIFICATION_TOKEN_INSTALLED_AT_KEY, "")
                expect(bool(installed_at), f"expected installed_at to be recorded, got {installed_at!r}")

                # Second handshake from any local caller must NOT overwrite the secret.
                status, body = webhook.handle_verification_token_post(conn, "tok_attacker_overwrite")
                expect(status == HTTPStatus.CONFLICT, f"expected CONFLICT on second store, got {status} {body}")
                expect("rotate" in str(body.get("error") or "").lower(), f"expected rotate hint in error, got {body}")
                stored = control.get_setting(conn, webhook.NOTION_WEBHOOK_VERIFICATION_TOKEN_KEY, "")
                expect(stored == "tok_initial_secret", f"expected unchanged token, got {stored!r}")

                # Empty/whitespace token should be rejected as bad request.
                status, body = webhook.handle_verification_token_post(conn, "")
                expect(status == HTTPStatus.BAD_REQUEST, f"expected BAD_REQUEST on empty token, got {status} {body}")
                status, body = webhook.handle_verification_token_post(conn, "   \n  ")
                expect(status == HTTPStatus.BAD_REQUEST, f"expected BAD_REQUEST on whitespace token, got {status} {body}")

                # Operator clears the secret and rearms the next install window.
                cleared = webhook.reset_verification_token(conn, actor="operator", rearm_ttl_seconds=300)
                expect(cleared["previously_set"] is True, str(cleared))
                expect(cleared["armed"] is True, str(cleared))
                expect(bool(cleared["armed_until"]), str(cleared))
                status, body = webhook.handle_verification_token_post(conn, "tok_rotated_secret")
                expect(status == HTTPStatus.OK, f"expected OK after reset, got {status} {body}")
                stored = control.get_setting(conn, webhook.NOTION_WEBHOOK_VERIFICATION_TOKEN_KEY, "")
                expect(stored == "tok_rotated_secret", f"expected rotated token stored, got {stored!r}")
            print("PASS test_handle_verification_token_post_refuses_overwrite_until_reset")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_handle_verification_token_post_refuses_handshake_after_reset_without_rearm() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_notion_webhook_reset_without_rearm_test")
    webhook = load_module(WEBHOOK_PY, "arclink_notion_webhook_reset_without_rearm_test")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        _write_config(config_path, _config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            with control.connect_db(cfg) as conn:
                armed = webhook.arm_verification_token_install(conn, ttl_seconds=600, actor="operator")
                expect(armed["armed"] is True, str(armed))
                status, body = webhook.handle_verification_token_post(conn, "tok_initial_secret")
                expect(status == HTTPStatus.OK, f"expected OK on first store, got {status} {body}")

                cleared = webhook.reset_verification_token(conn, actor="operator", rearm_ttl_seconds=0)
                expect(cleared["armed"] is False, str(cleared))
                expect(cleared["armed_until"] == "", str(cleared))

                status, body = webhook.handle_verification_token_post(conn, "tok_should_be_refused")
                expect(
                    status == HTTPStatus.PRECONDITION_FAILED,
                    f"expected PRECONDITION_FAILED after reset without rearm, got {status} {body}",
                )
                expect("not armed" in str(body.get("error") or "").lower(), str(body))
            print("PASS test_handle_verification_token_post_refuses_handshake_after_reset_without_rearm")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_webhook_module_exposes_setting_key_constant() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    webhook = load_module(WEBHOOK_PY, "arclink_notion_webhook_constant_test")
    expect(
        webhook.NOTION_WEBHOOK_VERIFICATION_TOKEN_KEY == "notion_webhook_verification_token",
        f"expected canonical setting key, got {webhook.NOTION_WEBHOOK_VERIFICATION_TOKEN_KEY!r}",
    )
    print("PASS test_webhook_module_exposes_setting_key_constant")


def test_signed_verification_token_post_is_accepted() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "arclink_control_notion_webhook_signed_post_test")
    webhook = load_module(WEBHOOK_PY, "arclink_notion_webhook_signed_post_test")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        _write_config(config_path, _config_values(root))
        old_env = os.environ.copy()
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        server = None
        thread = None
        try:
            cfg = control.Config.from_env()
            with control.connect_db(cfg) as conn:
                armed = webhook.arm_verification_token_install(conn, ttl_seconds=600, actor="operator")
                expect(armed["armed"] is True, str(armed))

            server = webhook.Server(("127.0.0.1", 0), webhook.Handler, cfg)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            payload = {"verification_token": "tok_signed_secret"}
            req = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/notion/webhook",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "X-Notion-Signature": "sha256=bogus-for-handshake",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                expect(resp.status == HTTPStatus.OK, f"expected OK, got {resp.status} {body}")
                expect(body.get("status") == "verification_token_stored", str(body))

            with control.connect_db(cfg) as conn:
                stored = control.get_setting(conn, webhook.NOTION_WEBHOOK_VERIFICATION_TOKEN_KEY, "")
                expect(stored == "tok_signed_secret", f"expected signed handshake token stored, got {stored!r}")
            print("PASS test_signed_verification_token_post_is_accepted")
        finally:
            if server is not None:
                server.shutdown()
                server.server_close()
            if thread is not None:
                thread.join(timeout=5)
            os.environ.clear()
            os.environ.update(old_env)


def test_kick_ssot_batcher_debounces_bursts_and_invokes_systemctl() -> None:
    import time

    mod = load_module(WEBHOOK_PY, "arclink_notion_webhook_kick_test")
    spawned: list[list[str]] = []

    class FakePopen:
        def __init__(self, args, **kwargs):
            spawned.append(list(args))

    real_popen = mod.subprocess.Popen
    real_debounce = mod._BATCHER_KICK_DEBOUNCE_SECONDS
    mod.subprocess.Popen = FakePopen
    mod._BATCHER_KICK_DEBOUNCE_SECONDS = 0.1
    try:
        # A burst of three rapid kicks should debounce to a single spawn
        # once the quiet window elapses.
        mod._kick_ssot_batcher()
        mod._kick_ssot_batcher()
        mod._kick_ssot_batcher()
        time.sleep(0.3)
    finally:
        mod.subprocess.Popen = real_popen
        mod._BATCHER_KICK_DEBOUNCE_SECONDS = real_debounce

    expect(len(spawned) == 1, f"expected 1 debounced spawn, got {len(spawned)}")
    args = spawned[0]
    expect(
        args[:5] == ["systemctl", "--user", "--no-block", "start", "arclink-ssot-batcher.service"],
        str(args),
    )
    print("PASS test_kick_ssot_batcher_debounces_bursts_and_invokes_systemctl")


def main() -> int:
    test_webhook_module_exposes_setting_key_constant()
    test_handle_verification_token_post_refuses_overwrite_until_reset()
    test_handle_verification_token_post_refuses_handshake_after_reset_without_rearm()
    test_signed_verification_token_post_is_accepted()
    test_kick_ssot_batcher_debounces_bursts_and_invokes_systemctl()
    print("PASS all 5 ArcLink notion webhook regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
