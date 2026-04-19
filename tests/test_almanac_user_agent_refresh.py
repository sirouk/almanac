#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SOURCE_SCRIPT = REPO / "bin" / "user-agent-refresh.sh"
CONTROL_PY = REPO / "python" / "almanac_control.py"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_fake_rpc_client(path: Path) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "from __future__ import annotations\n"
        "import argparse, json, os\n"
        "from pathlib import Path\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--url', required=True)\n"
        "parser.add_argument('--tool', required=True)\n"
        "parser.add_argument('--json-args', default='{}')\n"
        "args = parser.parse_args()\n"
        "payload = json.loads(args.json_args)\n"
        "log_path = Path(os.environ['ALMANAC_FAKE_RPC_LOG'])\n"
        "entries = []\n"
        "if log_path.exists():\n"
        "    entries = json.loads(log_path.read_text(encoding='utf-8'))\n"
        "entries.append({'tool': args.tool, 'url': args.url, 'payload': payload})\n"
        "log_path.write_text(json.dumps(entries, indent=2, sort_keys=True) + '\\n', encoding='utf-8')\n"
        "if args.tool == 'vaults.refresh':\n"
        "    result = {'active_subscriptions': ['Projects'], 'qmd_url': 'https://kor.tail77f45e.ts.net/mcp'}\n"
        "elif args.tool == 'agents.managed-memory':\n"
        "    result = {\n"
        "        'agent_id': 'agent-jeef',\n"
        "        'almanac-skill-ref': 'Use almanac-qmd-mcp for retrieval and almanac-vault-reconciler for drift repair.',\n"
        "        'vault-ref': 'Vault root: /srv/almanac/vault\\nDedicated agent name: Jeef',\n"
        "        'qmd-ref': 'qmd MCP (deep retrieval): https://kor.tail77f45e.ts.net/mcp',\n"
        "        'vault-topology': 'Subscribed vaults (+ = subscribed, · = default, - = unsubscribed):\\n  + Projects: Active project workspaces\\n  - Teams: Team coordination',\n"
        "        'catalog': [\n"
        "            {'vault_name': 'Projects', 'default_subscribed': 1, 'description': 'Active project workspaces'},\n"
        "            {'vault_name': 'Teams', 'default_subscribed': 0, 'description': 'Team coordination'},\n"
        "        ],\n"
        "        'subscriptions': [\n"
        "            {'vault_name': 'Projects', 'subscribed': 1, 'default_subscribed': 1},\n"
        "            {'vault_name': 'Teams', 'subscribed': 0, 'default_subscribed': 0},\n"
        "        ],\n"
        "    }\n"
        "elif args.tool == 'agents.consume-notifications':\n"
        "    result = {\n"
        "        'agent_id': 'agent-jeef',\n"
        "        'notifications': [\n"
        "            {'channel_kind': 'vault-change', 'message': 'Projects vault updated', 'created_at': '2026-04-19T19:00:00+00:00'},\n"
        "            {'channel_kind': 'subscription', 'message': 'Teams -> False', 'created_at': '2026-04-19T19:05:00+00:00'},\n"
        "        ],\n"
        "    }\n"
        "else:\n"
        "    raise SystemExit(f'unsupported tool: {args.tool}')\n"
        "print(json.dumps(result, indent=2, sort_keys=True))\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_user_agent_refresh_materializes_managed_stubs_and_recent_events() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo_dir = root / "repo"
        bin_dir = repo_dir / "bin"
        python_dir = repo_dir / "python"
        hermes_home = root / "hermes-home"
        rpc_log = root / "rpc-log.json"

        bin_dir.mkdir(parents=True, exist_ok=True)
        python_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE_SCRIPT, bin_dir / "user-agent-refresh.sh")
        (bin_dir / "user-agent-refresh.sh").chmod(0o755)
        shutil.copy2(CONTROL_PY, python_dir / "almanac_control.py")
        write_fake_rpc_client(python_dir / "almanac_rpc_client.py")

        token_file = hermes_home / "secrets" / "almanac-bootstrap-token"
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text("tok_jeef\n", encoding="utf-8")

        enrollment_state = hermes_home / "state" / "almanac-enrollment.json"
        enrollment_state.parent.mkdir(parents=True, exist_ok=True)
        enrollment_state.write_text(json.dumps({"status": "active"}) + "\n", encoding="utf-8")

        memory_path = hermes_home / "memories" / "MEMORY.md"
        memory_path.parent.mkdir(parents=True, exist_ok=True)
        memory_path.write_text(
            "Persistent preference\n§\n[managed:qmd-ref]\nold qmd routing\n§\nAnother note\n§\n[managed:vault-topology]\nold topology\n",
            encoding="utf-8",
        )

        recent_events_path = hermes_home / "state" / "almanac-recent-events.json"
        recent_events_path.write_text(
            json.dumps(
                {
                    "agent_id": "agent-jeef",
                    "events": [
                        {
                            "channel_kind": "existing",
                            "message": "carry forward",
                            "created_at": "2026-04-19T18:00:00+00:00",
                        }
                    ],
                    "last_consumed_count": 1,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [str(bin_dir / "user-agent-refresh.sh")],
            env={
                **os.environ,
                "HERMES_HOME": str(hermes_home),
                "HOME": str(root / "home-jeef"),
                "ALMANAC_MCP_URL": "http://127.0.0.1:8282/mcp",
                "ALMANAC_FAKE_RPC_LOG": str(rpc_log),
            },
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode == 0, f"expected user-agent-refresh to succeed, got rc={result.returncode} stderr={result.stderr!r}")

        state_path = hermes_home / "state" / "almanac-vault-reconciler.json"
        stub_path = hermes_home / "memories" / "almanac-managed-stubs.md"
        expect(state_path.is_file(), f"expected reconciler state file: {state_path}")
        expect(stub_path.is_file(), f"expected managed stubs markdown: {stub_path}")

        state_payload = json.loads(state_path.read_text(encoding="utf-8"))
        expect(state_payload["agent_id"] == "agent-jeef", state_payload)
        expect(state_payload["catalog"][0]["vault_name"] == "Projects", state_payload)
        expect(state_payload["subscriptions"][0]["vault_name"] == "Projects", state_payload)

        stub_body = stub_path.read_text(encoding="utf-8")
        expect("# Almanac managed memory stubs" in stub_body, stub_body)
        expect("[managed:almanac-skill-ref]" in stub_body, stub_body)
        expect("Dedicated agent name: Jeef" in stub_body, stub_body)

        memory_entries = [entry.strip() for entry in memory_path.read_text(encoding="utf-8").split("\n§\n") if entry.strip()]
        expect(memory_entries[0] == "Persistent preference", memory_entries)
        expect(memory_entries[1] == "Another note", memory_entries)
        expect(all("old qmd routing" not in entry for entry in memory_entries), memory_entries)
        expect(all("old topology" not in entry for entry in memory_entries), memory_entries)
        managed_prefixes = [
            "[managed:almanac-skill-ref]",
            "[managed:vault-ref]",
            "[managed:qmd-ref]",
            "[managed:vault-topology]",
        ]
        for prefix in managed_prefixes:
            expect(any(entry.startswith(prefix) for entry in memory_entries), f"missing {prefix} in {memory_entries}")

        events_payload = json.loads(recent_events_path.read_text(encoding="utf-8"))
        expect(events_payload["agent_id"] == "agent-jeef", events_payload)
        expect(events_payload["last_consumed_count"] == 2, events_payload)
        expect(len(events_payload["events"]) == 3, events_payload)
        expect(events_payload["events"][0]["message"] == "carry forward", events_payload)
        expect(events_payload["events"][1]["message"] == "Projects vault updated", events_payload)
        expect(events_payload["events"][2]["message"] == "Teams -> False", events_payload)

        rpc_calls = json.loads(rpc_log.read_text(encoding="utf-8"))
        expect([call["tool"] for call in rpc_calls] == ["vaults.refresh", "agents.managed-memory", "agents.consume-notifications"], rpc_calls)
        expect(all(call["payload"].get("token") == "tok_jeef" for call in rpc_calls), rpc_calls)
        expect(rpc_calls[-1]["payload"].get("limit") == 200, rpc_calls)
        print("PASS test_user_agent_refresh_materializes_managed_stubs_and_recent_events")


def main() -> int:
    test_user_agent_refresh_materializes_managed_stubs_and_recent_events()
    print("PASS all 1 user-agent refresh regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
