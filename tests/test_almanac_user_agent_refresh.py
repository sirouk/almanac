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
MODEL_PROVIDERS_PY = REPO / "python" / "almanac_model_providers.py"
NOTION_SSOT_PY = REPO / "python" / "almanac_notion_ssot.py"
ORG_PROFILE_PY = REPO / "python" / "almanac_org_profile.py"
RESOURCE_MAP_PY = REPO / "python" / "almanac_resource_map.py"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_fake_rpc_client(path: Path) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "from __future__ import annotations\n"
        "import argparse\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n"
        "\n"
        "def _log_call(*, tool_name: str, url: str, payload: dict) -> None:\n"
        "    log_path = Path(os.environ['ALMANAC_FAKE_RPC_LOG'])\n"
        "    entries = []\n"
        "    if log_path.exists():\n"
        "        entries = json.loads(log_path.read_text(encoding='utf-8'))\n"
        "    entries.append({'tool': tool_name, 'url': url, 'payload': payload})\n"
        "    log_path.write_text(json.dumps(entries, indent=2, sort_keys=True) + '\\n', encoding='utf-8')\n"
        "\n"
        "def _dispatch(*, url: str, tool_name: str, payload: dict) -> dict:\n"
        "    _log_call(tool_name=tool_name, url=url, payload=payload)\n"
        "    if tool_name == 'vaults.refresh':\n"
        "        return {'active_subscriptions': ['Projects'], 'qmd_url': 'https://almanac.example.test/mcp'}\n"
        "    if tool_name == 'agents.managed-memory':\n"
        "        return {\n"
        "        'agent_id': 'agent-guide',\n"
        "        'almanac-skill-ref': 'Use almanac-qmd-mcp for retrieval and almanac-vault-reconciler for drift repair.',\n"
        "        'vault-ref': 'Vault root: /srv/almanac/vault\\nDedicated agent name: Guide',\n"
        "        'resource-ref': 'Canonical user access rails and shared Almanac addresses:\\n- Hermes dashboard: https://almanac.example.test:30011/\\n- Code workspace: https://almanac.example.test:40011/\\n- Credentials are intentionally omitted from plugin-managed context.',\n"
        "        'qmd-ref': 'qmd MCP (deep retrieval): https://almanac.example.test/mcp',\n"
        "        'notion-ref': 'Shared Notion knowledge rail: notion.search / notion.fetch / notion.query via Almanac MCP.',\n"
        "        'vault-topology': 'Subscribed vaults (+ = subscribed, · = default, - = unsubscribed):\\n  + Projects: Active project workspaces\\n  - Teams: Team coordination',\n"
        "        'recall-stubs': 'Retrieval memory stubs:\\n- Projects: ask vault.search-and-fetch for depth.',\n"
        "        'today-plate': 'Today plate:\\n- Scoped work: 2 owned/assigned record(s). Due today/overdue: 1. Pending write approvals: 0.\\n- Work candidates:\\n  - Example Unicorn launch — status In Progress — due today 2026-04-23',\n"
        "        'vault_path_contract': 'user-home-almanac-v1',\n"
        "        'catalog': [\n"
        "            {'vault_name': 'Projects', 'default_subscribed': 1, 'description': 'Active project workspaces'},\n"
        "            {'vault_name': 'Teams', 'default_subscribed': 0, 'description': 'Team coordination'},\n"
        "        ],\n"
        "        'subscriptions': [\n"
        "            {'vault_name': 'Projects', 'subscribed': 1, 'default_subscribed': 1},\n"
        "            {'vault_name': 'Teams', 'subscribed': 0, 'default_subscribed': 0},\n"
        "        ],\n"
        "        }\n"
        "    if tool_name == 'agents.consume-notifications':\n"
        "        return {\n"
        "        'agent_id': 'agent-guide',\n"
        "        'notifications': [\n"
        "            {'channel_kind': 'vault-change', 'message': 'Projects vault updated', 'created_at': '2026-04-19T19:00:00+00:00'},\n"
        "            {'channel_kind': 'subscription', 'message': 'Teams -> False', 'created_at': '2026-04-19T19:05:00+00:00'},\n"
        "        ],\n"
        "        }\n"
        "    raise RuntimeError(f'unsupported tool: {tool_name}')\n"
        "\n"
        "def mcp_call(url: str, tool_name: str, arguments: dict) -> dict:\n"
        "    return _dispatch(url=url, tool_name=tool_name, payload=arguments)\n"
        "\n"
        "def main() -> None:\n"
        "    parser = argparse.ArgumentParser()\n"
        "    parser.add_argument('--url', required=True)\n"
        "    parser.add_argument('--tool', required=True)\n"
        "    parser.add_argument('--json-args', default='{}')\n"
        "    parser.add_argument('--json-args-file', default='')\n"
        "    args = parser.parse_args()\n"
        "    payload = json.loads(Path(args.json_args_file).read_text(encoding='utf-8') if args.json_args_file else args.json_args)\n"
        "    result = _dispatch(url=args.url, tool_name=args.tool, payload=payload)\n"
        "    json.dump(result, sys.stdout, indent=2, sort_keys=True)\n"
        "    sys.stdout.write('\\n')\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    main()\n",
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
        shutil.copy2(MODEL_PROVIDERS_PY, python_dir / "almanac_model_providers.py")
        shutil.copy2(NOTION_SSOT_PY, python_dir / "almanac_notion_ssot.py")
        shutil.copy2(ORG_PROFILE_PY, python_dir / "almanac_org_profile.py")
        shutil.copy2(RESOURCE_MAP_PY, python_dir / "almanac_resource_map.py")
        write_fake_rpc_client(python_dir / "almanac_rpc_client.py")

        agents_state_dir = root / "agents-state" / "agent-guide"
        agents_state_dir.mkdir(parents=True, exist_ok=True)
        (agents_state_dir / "managed-memory.json").write_text(
            json.dumps(
                {
                    "agent_id": "agent-guide",
                    "almanac-skill-ref": "Use almanac-qmd-mcp for retrieval and almanac-vault-reconciler for drift repair.",
                    "vault-ref": "Vault root: /srv/almanac/vault\nDedicated agent name: Guide",
                    "resource-ref": "Canonical user access rails and shared Almanac addresses:\n- Hermes dashboard: https://almanac.example.test:30011/\n- Code workspace: https://almanac.example.test:40011/\n- Credentials are intentionally omitted from plugin-managed context.",
                    "qmd-ref": "qmd MCP (deep retrieval): https://almanac.example.test/mcp",
                    "notion-ref": "Shared Notion knowledge rail: notion.search / notion.fetch / notion.query via Almanac MCP.",
                    "vault-topology": "Subscribed vaults (+ = subscribed, · = default, - = unsubscribed):\n  + Projects: Active project workspaces\n  - Teams: Team coordination",
                    "recall-stubs": "Retrieval memory stubs:\n- Projects: ask vault.search-and-fetch for depth.",
                    "today-plate": "Today plate:\n- Scoped work: 2 owned/assigned record(s). Due today/overdue: 1. Pending write approvals: 0.\n- Work candidates:\n  - Example Unicorn launch — status In Progress — due today 2026-04-23",
                    "vault_path_contract": "user-home-almanac-v1",
                    "catalog": [
                        {"vault_name": "Projects", "default_subscribed": 1, "description": "Active project workspaces"},
                        {"vault_name": "Teams", "default_subscribed": 0, "description": "Team coordination"},
                    ],
                    "subscriptions": [
                        {"vault_name": "Projects", "subscribed": 1, "default_subscribed": 1},
                        {"vault_name": "Teams", "subscribed": 0, "default_subscribed": 0},
                    ],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        token_file = hermes_home / "secrets" / "almanac-bootstrap-token"
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text("tok_guide\n", encoding="utf-8")

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
                    "agent_id": "agent-guide",
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
                "HOME": str(root / "home-guide"),
                "ALMANAC_MCP_URL": "http://127.0.0.1:8282/mcp",
                "ALMANAC_FAKE_RPC_LOG": str(rpc_log),
                "ALMANAC_AGENT_ID": "agent-guide",
                "ALMANAC_AGENTS_STATE_DIR": str(root / "agents-state"),
            },
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode == 0, f"expected user-agent-refresh to succeed, got rc={result.returncode} stderr={result.stderr!r}")

        state_path = hermes_home / "state" / "almanac-vault-reconciler.json"
        stub_path = hermes_home / "memories" / "almanac-managed-stubs.md"
        expect(state_path.is_file(), f"expected reconciler state file: {state_path}")
        expect(not stub_path.exists(), f"dynamic managed context should not be mirrored to markdown: {stub_path}")

        state_payload = json.loads(state_path.read_text(encoding="utf-8"))
        expect(state_payload["agent_id"] == "agent-guide", state_payload)
        expect(state_payload["catalog"][0]["vault_name"] == "Projects", state_payload)
        expect(state_payload["subscriptions"][0]["vault_name"] == "Projects", state_payload)
        expect("notion-ref" in state_payload, state_payload)
        expect("today-plate" in state_payload, state_payload)
        expect("notion.search / notion.fetch / notion.query" in state_payload["notion-ref"], state_payload)
        expect("Example Unicorn launch" in state_payload["today-plate"], state_payload)
        expect("Hermes dashboard: https://almanac.example.test:30011/" in state_payload["resource-ref"], state_payload)
        expect("Code workspace: https://almanac.example.test:40011/" in state_payload["resource-ref"], state_payload)
        expect(len(str(state_payload.get("managed_memory_revision") or "")) >= 12, state_payload)

        memory_entries = [entry.strip() for entry in memory_path.read_text(encoding="utf-8").split("\n§\n") if entry.strip()]
        expect(memory_entries[0] == "Persistent preference", memory_entries)
        expect(memory_entries[1] == "Another note", memory_entries)
        expect(all("old qmd routing" not in entry for entry in memory_entries), memory_entries)
        expect(all("old topology" not in entry for entry in memory_entries), memory_entries)
        expect(all(not entry.startswith("[managed:") for entry in memory_entries), memory_entries)

        events_payload = json.loads(recent_events_path.read_text(encoding="utf-8"))
        expect(events_payload["agent_id"] == "agent-guide", events_payload)
        expect(events_payload["last_consumed_count"] == 2, events_payload)
        expect(len(events_payload["events"]) == 3, events_payload)
        expect(events_payload["events"][0]["message"] == "carry forward", events_payload)
        expect(events_payload["events"][1]["message"] == "Projects vault updated", events_payload)
        expect(events_payload["events"][2]["message"] == "Teams -> False", events_payload)

        rpc_calls = json.loads(rpc_log.read_text(encoding="utf-8"))
        expect([call["tool"] for call in rpc_calls] == ["vaults.refresh", "agents.consume-notifications"], rpc_calls)
        expect(all(call["payload"].get("token") == "tok_guide" for call in rpc_calls), rpc_calls)
        expect(rpc_calls[-1]["payload"].get("limit") == 200, rpc_calls)
        print("PASS test_user_agent_refresh_materializes_managed_stubs_and_recent_events")


def test_user_agent_refresh_falls_back_to_live_managed_memory_when_central_payload_is_invalid() -> None:
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
        shutil.copy2(MODEL_PROVIDERS_PY, python_dir / "almanac_model_providers.py")
        shutil.copy2(NOTION_SSOT_PY, python_dir / "almanac_notion_ssot.py")
        shutil.copy2(ORG_PROFILE_PY, python_dir / "almanac_org_profile.py")
        shutil.copy2(RESOURCE_MAP_PY, python_dir / "almanac_resource_map.py")
        write_fake_rpc_client(python_dir / "almanac_rpc_client.py")

        agents_state_dir = root / "agents-state" / "agent-guide"
        agents_state_dir.mkdir(parents=True, exist_ok=True)
        (agents_state_dir / "managed-memory.json").write_text("{not-json}\n", encoding="utf-8")

        token_file = hermes_home / "secrets" / "almanac-bootstrap-token"
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text("tok_guide\n", encoding="utf-8")

        enrollment_state = hermes_home / "state" / "almanac-enrollment.json"
        enrollment_state.parent.mkdir(parents=True, exist_ok=True)
        enrollment_state.write_text(json.dumps({"status": "active"}) + "\n", encoding="utf-8")

        result = subprocess.run(
            [str(bin_dir / "user-agent-refresh.sh")],
            env={
                **os.environ,
                "HERMES_HOME": str(hermes_home),
                "HOME": str(root / "home-guide"),
                "ALMANAC_MCP_URL": "http://127.0.0.1:8282/mcp",
                "ALMANAC_FAKE_RPC_LOG": str(rpc_log),
                "ALMANAC_AGENT_ID": "agent-guide",
                "ALMANAC_AGENTS_STATE_DIR": str(root / "agents-state"),
            },
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode == 0, f"expected invalid central payload to fall back live, got rc={result.returncode} stderr={result.stderr!r}")
        expect("Ignoring invalid central managed-memory payload" in result.stderr, result.stderr)

        state_path = hermes_home / "state" / "almanac-vault-reconciler.json"
        state_payload = json.loads(state_path.read_text(encoding="utf-8"))
        expect(state_payload["agent_id"] == "agent-guide", state_payload)
        expect("notion.search / notion.fetch / notion.query" in state_payload["notion-ref"], state_payload)

        rpc_calls = json.loads(rpc_log.read_text(encoding="utf-8"))
        expect([call["tool"] for call in rpc_calls] == ["vaults.refresh", "agents.managed-memory", "agents.consume-notifications"], rpc_calls)
        expect(all(call["payload"].get("token") == "tok_guide" for call in rpc_calls), rpc_calls)
        print("PASS test_user_agent_refresh_falls_back_to_live_managed_memory_when_central_payload_is_invalid")


def test_user_agent_refresh_rejects_wrong_agent_central_payload() -> None:
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
        shutil.copy2(MODEL_PROVIDERS_PY, python_dir / "almanac_model_providers.py")
        shutil.copy2(NOTION_SSOT_PY, python_dir / "almanac_notion_ssot.py")
        shutil.copy2(ORG_PROFILE_PY, python_dir / "almanac_org_profile.py")
        shutil.copy2(RESOURCE_MAP_PY, python_dir / "almanac_resource_map.py")
        write_fake_rpc_client(python_dir / "almanac_rpc_client.py")

        agents_state_dir = root / "agents-state" / "agent-guide"
        agents_state_dir.mkdir(parents=True, exist_ok=True)
        (agents_state_dir / "managed-memory.json").write_text(
            json.dumps(
                {
                    "agent_id": "agent-other",
                    "vault-ref": "wrong",
                    "qmd-ref": "wrong",
                    "vault_path_contract": "user-home-almanac-v1",
                    "catalog": [],
                    "subscriptions": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )

        token_file = hermes_home / "secrets" / "almanac-bootstrap-token"
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text("tok_guide\n", encoding="utf-8")
        enrollment_state = hermes_home / "state" / "almanac-enrollment.json"
        enrollment_state.parent.mkdir(parents=True, exist_ok=True)
        enrollment_state.write_text(json.dumps({"status": "active"}) + "\n", encoding="utf-8")

        result = subprocess.run(
            [str(bin_dir / "user-agent-refresh.sh")],
            env={
                **os.environ,
                "HERMES_HOME": str(hermes_home),
                "HOME": str(root / "home-guide"),
                "ALMANAC_MCP_URL": "http://127.0.0.1:8282/mcp",
                "ALMANAC_FAKE_RPC_LOG": str(rpc_log),
                "ALMANAC_AGENT_ID": "agent-guide",
                "ALMANAC_AGENTS_STATE_DIR": str(root / "agents-state"),
            },
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode == 0, result.stderr)
        expect("agent_id mismatch" in result.stderr, result.stderr)
        rpc_calls = json.loads(rpc_log.read_text(encoding="utf-8"))
        expect([call["tool"] for call in rpc_calls] == ["vaults.refresh", "agents.managed-memory", "agents.consume-notifications"], rpc_calls)
        print("PASS test_user_agent_refresh_rejects_wrong_agent_central_payload")


def test_central_managed_payload_is_acl_private_not_world_readable() -> None:
    source = CONTROL_PY.read_text(encoding="utf-8")
    grant_start = source.index("def _grant_managed_payload_read_access(")
    grant_end = source.index("def publish_central_managed_memory(", grant_start)
    grant_source = source[grant_start:grant_end]
    expect("path.chmod(0o640)" in grant_source, "central managed payload should not be world-readable")
    expect("path.chmod(0o644)" not in grant_source, "central managed payload must not use world-readable permissions")
    expect("setfacl" in grant_source and "cfg.private_dir" in grant_source and "cfg.agents_state_dir" in grant_source, "enrolled user access should use narrow ACLs")
    print("PASS test_central_managed_payload_is_acl_private_not_world_readable")


def main() -> int:
    test_user_agent_refresh_materializes_managed_stubs_and_recent_events()
    test_user_agent_refresh_falls_back_to_live_managed_memory_when_central_payload_is_invalid()
    test_user_agent_refresh_rejects_wrong_agent_central_payload()
    test_central_managed_payload_is_acl_private_not_world_readable()
    print("PASS all 4 user-agent refresh regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
