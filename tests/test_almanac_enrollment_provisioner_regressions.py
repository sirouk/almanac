#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROVISIONER_PY = REPO / "python" / "almanac_enrollment_provisioner.py"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def extract(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def test_onboarding_paths_refresh_managed_memory_after_access_surfaces_exist() -> None:
    text = PROVISIONER_PY.read_text(encoding="utf-8")
    telegram = extract(text, "def _configure_user_telegram_gateway", "def _configure_user_discord_gateway")
    discord = extract(text, "def _configure_user_discord_gateway", "def _run_pending_onboarding_gateway_configs")
    auto = extract(text, "def _run_one(conn, cfg: Config, row: dict) -> None:", "def main() -> None:")

    expect("_refresh_user_agent_memory(" in telegram, "telegram onboarding should refresh managed memory")
    expect("_refresh_user_agent_memory(" in discord, "discord onboarding should refresh managed memory")
    expect("_refresh_user_agent_memory(" in auto, "auto-provision onboarding should refresh managed memory")
    print("PASS test_onboarding_paths_refresh_managed_memory_after_access_surfaces_exist")


def main() -> int:
    test_onboarding_paths_refresh_managed_memory_after_access_surfaces_exist()
    print("PASS all 1 enrollment provisioner regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
