#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CTL_PY = REPO / "python" / "arclink_ctl.py"


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


def test_discord_error_target_retry_classifier() -> None:
    if str(REPO / "python") not in sys.path:
        sys.path.insert(0, str(REPO / "python"))
    mod = load_module(CTL_PY, "arclink_ctl_regressions")
    expect(
        mod._discord_error_suggests_target_retry(
            'discord http 404: {"message": "Unknown Channel", "code": 10003}',
            target_kind="channel",
        ),
        "expected unknown channel to retry the channel target first",
    )
    expect(
        mod._discord_error_suggests_target_retry(
            "discord target does not look like a webhook URL: https://example.invalid/hook",
            target_kind="webhook",
        ),
        "expected invalid webhook targets to retry the target",
    )
    expect(
        not mod._discord_error_suggests_target_retry(
            'discord http 401: {"message": "401: Unauthorized"}',
            target_kind="channel",
        ),
        "did not expect auth failures to look like channel-target problems",
    )
    print("PASS test_discord_error_target_retry_classifier")


def main() -> int:
    test_discord_error_target_retry_classifier()
    print("PASS all 1 arclink-ctl regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
