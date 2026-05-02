#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "bin" / "arclink-context-telemetry"


def expect(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


def test_context_telemetry_summarizes_jsonl_for_humans_and_machines() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "telemetry.jsonl"
        records = [
            {
                "ts": "2026-04-23T10:00:00+00:00",
                "session_id": "a",
                "injected": True,
                "gate": ["first_turn", "recipe"],
                "recipes": ["ssot.write"],
                "context_chars": 1200,
                "context_mode": "full",
                "managed_revision": "rev-a",
                "platform": "discord",
            },
            {
                "ts": "2026-04-23T10:01:00+00:00",
                "session_id": "b",
                "injected": True,
                "gate": ["recipe"],
                "recipes": ["ssot.write"],
                "context_chars": 320,
                "context_mode": "recipe_only",
                "managed_revision": "rev-a",
                "platform": "discord",
            },
            {
                "ts": "2026-04-23T10:02:00+00:00",
                "session_id": "c",
                "injected": False,
                "gate": [],
                "recipes": [],
                "context_chars": 0,
                "managed_revision": "rev-b",
                "platform": "telegram",
                "reason": "no_gate",
            },
            {
                "ts": "2026-04-23T10:03:00+00:00",
                "session_id": "c",
                "event": "tool_token_injected",
                "tool_token_injected": True,
                "tool_name": "mcp_arclink_mcp_notion_search_and_fetch",
            },
        ]
        path.write_text(
            "\n".join(json.dumps(record, sort_keys=True) for record in records) + "\nnot-json\n",
            encoding="utf-8",
        )

        machine = subprocess.run(
            [str(SCRIPT), "--json", str(path)],
            text=True,
            capture_output=True,
            check=False,
        )
        expect(machine.returncode == 0, machine.stderr)
        summary = json.loads(machine.stdout)
        expect(summary["records"] == 4, summary)
        expect(summary["invalid_lines"] == 1, summary)
        expect(summary["injected"] == 2, summary)
        expect(summary["suppressed"] == 1, summary)
        expect(summary["context_modes"]["recipe_only"] == 1, summary)
        expect(summary["context_modes"]["suppressed"] == 1, summary)
        expect(summary["gates"]["recipe"] == 2, summary)
        expect(summary["recipes"]["ssot.write"] == 2, summary)
        expect(summary["reasons"]["no_gate"] == 1, summary)
        expect(summary["events"]["tool_token_injected"] == 1, summary)
        expect(summary["tool_token_injections"] == 1, summary)
        expect(summary["token_injected_tools"]["mcp_arclink_mcp_notion_search_and_fetch"] == 1, summary)
        expect(summary["platforms"]["(tool-call)"] == 1, summary)
        expect(summary["managed_revisions"] == 2, summary)

        human = subprocess.run(
            [str(SCRIPT), str(path)],
            text=True,
            capture_output=True,
            check=False,
        )
        expect(human.returncode == 0, human.stderr)
        expect("ArcLink context telemetry" in human.stdout, human.stdout)
        expect("injected: 2; suppressed: 1" in human.stdout, human.stdout)
        expect("recipes: ssot.write=2" in human.stdout, human.stdout)
        expect("tool token injections: 1" in human.stdout, human.stdout)
        expect("token-injected tools: mcp_arclink_mcp_notion_search_and_fetch=1" in human.stdout, human.stdout)
        expect("(tool-call)=1" in human.stdout, human.stdout)
        expect("events: tool_token_injected=1" in human.stdout, human.stdout)
        print("PASS test_context_telemetry_summarizes_jsonl_for_humans_and_machines")


def test_context_telemetry_defaults_to_hermes_home_state() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        hermes_home = Path(tmp) / "hermes-home"
        path = hermes_home / "state" / "arclink-context-telemetry.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "ts": "2026-04-23T10:00:00+00:00",
                    "injected": False,
                    "gate": [],
                    "recipes": [],
                    "context_chars": 0,
                    "reason": "no_gate",
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [str(SCRIPT), "--json"],
            env={**os.environ, "HERMES_HOME": str(hermes_home)},
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode == 0, result.stderr)
        summary = json.loads(result.stdout)
        expect(summary["paths"] == [str(path)], summary)
        expect(summary["suppressed"] == 1, summary)
        print("PASS test_context_telemetry_defaults_to_hermes_home_state")


def main() -> int:
    test_context_telemetry_summarizes_jsonl_for_humans_and_machines()
    test_context_telemetry_defaults_to_hermes_home_state()
    print("PASS all 2 ArcLink context telemetry tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
