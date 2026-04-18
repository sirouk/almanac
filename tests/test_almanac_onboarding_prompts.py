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


def test_discord_prompt_and_operator_review_reflect_primary_control_channel() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_onboarding_prompt_test")
    onboarding = load_module(ONBOARDING_PY, "almanac_onboarding_prompt_test")
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
                "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "discord",
                "OPERATOR_NOTIFY_CHANNEL_ID": "123456789012345678",
                "ALMANAC_CURATOR_CHANNELS": "tui-only",
            },
        )

        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            expect(cfg.curator_discord_onboarding_enabled is True, f"expected discord onboarding to default on, got {cfg}")

            prompt = onboarding.session_prompt(
                cfg,
                {
                    "state": "awaiting-bot-token",
                    "answers": {
                        "bot_platform": "discord",
                        "preferred_bot_name": "KorBon",
                    },
                },
            )
            expect("Open Installation and copy the install link" in prompt, prompt)
            expect("share a server" in prompt or "Add App" in prompt, prompt)

            review = onboarding._operator_review_message(  # noqa: SLF001
                cfg,
                {
                    "session_id": "onb_test",
                    "platform": "discord",
                    "sender_id": "42",
                    "sender_username": "operator-user",
                    "sender_display_name": "Operator User",
                    "answers": {
                        "full_name": "Operator User",
                        "unix_user": "operatoruser",
                        "purpose": "Keep the org moving",
                        "bot_platform": "discord",
                        "preferred_bot_name": "KorBon",
                        "model_preset": "codex",
                    },
                },
            )
            expect("Discord approve: /approve onb_test" in review, review)
            expect("configured primary Discord operator channel" in review, review)
            print("PASS test_discord_prompt_and_operator_review_reflect_primary_control_channel")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def main() -> int:
    test_discord_prompt_and_operator_review_reflect_primary_control_channel()
    print("PASS all 1 onboarding prompt regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
