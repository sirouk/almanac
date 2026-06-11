#!/usr/bin/env python3
"""Pin-compatibility checks for the public Agent gateway bridge.

The bridge replays raw platform updates through PRIVATE Hermes adapter
methods. A hermes-agent pin bump can rename or refactor those methods with no
failing ArcLink unit test, silently degrading every bridged turn to a
placeholder. These tests pin the coupling: when the local Hermes source
checkout is present, every private symbol the bridge calls must still exist
there, and the bridge's own replay dispatch must reference exactly those
symbols.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
BRIDGE_PY = PYTHON_DIR / "arclink_public_agent_bridge.py"

# The symbols the bridge replays into, per integration point.
TELEGRAM_ADAPTER_HANDLERS = (
    "_handle_text_message",
    "_handle_command",
    "_handle_media_message",
    "_handle_location_message",
    "_handle_callback_query",
)
COMMANDS_MODULE_HELPERS = (
    "telegram_menu_commands",
    "_is_gateway_available",
    "_requires_argument",
    "_resolve_config_gates",
    "_sanitize_telegram_name",
)


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _hermes_source_root() -> Path | None:
    candidates = [
        os.environ.get("ARCLINK_HERMES_AGENT_SRC", ""),
        str(REPO / "arclink-priv" / "state" / "hermes-docs-src"),
        str(REPO / "arclink-priv" / "state" / "runtime" / "hermes-agent-src"),
    ]
    for candidate in candidates:
        path = Path(candidate) if candidate else None
        if path and (path / "gateway" / "platforms" / "telegram.py").is_file():
            return path
    return None


def test_bridge_replay_dispatch_uses_known_handler_names() -> None:
    body = BRIDGE_PY.read_text(encoding="utf-8")
    for handler in TELEGRAM_ADAPTER_HANDLERS:
        expect(handler in body, f"bridge no longer references {handler}; update this pin test too")
    # The replay must accept edited messages so caption/media edits re-enter
    # natively instead of degrading to a placeholder turn.
    expect('getattr(update, "edited_message", None)' in body, "bridge must replay edited_message updates")
    # Album merging: a telegram_update_json_list payload must replay each item
    # in one process so Hermes' media-group debounce can merge them.
    expect("telegram_update_json_list" in body, "bridge must support album update lists")
    # Discord sends must pin default-deny mentions.
    expect('"allowed_mentions"' in body, "bridge Discord sends must pin allowed_mentions default-deny")
    print("PASS test_bridge_replay_dispatch_uses_known_handler_names")


def test_pinned_hermes_source_still_exposes_bridge_coupling() -> None:
    root = _hermes_source_root()
    if root is None:
        print("SKIP test_pinned_hermes_source_still_exposes_bridge_coupling (no local hermes source)")
        return
    telegram_text = (root / "gateway" / "platforms" / "telegram.py").read_text(encoding="utf-8")
    for handler in TELEGRAM_ADAPTER_HANDLERS:
        expect(
            re.search(rf"def {re.escape(handler)}\(", telegram_text) is not None,
            f"pinned hermes source lost {handler}; the bridge replay (and per-update parse) must be re-aligned "
            "before bumping the hermes-agent pin",
        )
    commands_path = root / "hermes_cli" / "commands.py"
    expect(commands_path.is_file(), "pinned hermes source lost hermes_cli/commands.py")
    commands_text = commands_path.read_text(encoding="utf-8")
    for helper in COMMANDS_MODULE_HELPERS:
        expect(
            re.search(rf"def {re.escape(helper)}\(", commands_text) is not None,
            f"pinned hermes source lost hermes_cli.commands.{helper}; ArcLink menu derivation must be re-aligned "
            "before bumping the hermes-agent pin",
        )
    print("PASS test_pinned_hermes_source_still_exposes_bridge_coupling")


def main() -> int:
    test_bridge_replay_dispatch_uses_known_handler_names()
    test_pinned_hermes_source_still_exposes_bridge_coupling()
    print("PASS all 2 public agent bridge pin tests")
    return 0


if __name__ == "__main__":
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    raise SystemExit(main())
