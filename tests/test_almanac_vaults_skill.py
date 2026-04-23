#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SOURCE_SCRIPT = REPO / "skills" / "almanac-vaults" / "scripts" / "curate-vaults.sh"
SKILL = REPO / "skills" / "almanac-vaults" / "SKILL.md"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_fake_rpc_client(repo_dir: Path) -> None:
    target = repo_dir / "python" / "almanac_rpc_client.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "#!/usr/bin/env python3\n"
        "from __future__ import annotations\n"
        "import argparse, json\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--url')\n"
        "parser.add_argument('--tool')\n"
        "parser.add_argument('--json-args')\n"
        "args = parser.parse_args()\n"
        "if args.tool == 'catalog.vaults':\n"
        "    print(json.dumps({'vaults': [{'vault_name': 'Projects', 'subscribed': True, 'default_subscribed': True, 'description': 'Active project workspaces'}]}))\n"
        "elif args.tool == 'vaults.refresh':\n"
        "    print(json.dumps({'active_subscriptions': ['Projects'], 'qmd_url': 'http://127.0.0.1:8181/mcp'}))\n"
        "elif args.tool == 'agents.managed-memory':\n"
        "    print(json.dumps({'agent_id': 'agent-test', 'vault-topology': '+ Projects', 'almanac-skill-ref': 'ok', 'vault-ref': 'ok', 'qmd-ref': 'ok'}))\n"
        "elif args.tool == 'vaults.subscribe':\n"
        "    payload = json.loads(args.json_args)\n"
        "    print(json.dumps({'agent_id': 'agent-test', 'vault_name': payload['vault_name'], 'subscribed': payload['subscribed']}))\n"
        "else:\n"
        "    raise SystemExit(f'unsupported tool: {args.tool}')\n",
        encoding="utf-8",
    )
    target.chmod(0o755)


def test_installed_curate_vaults_uses_repo_env_fallback() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        hermes_home = root / "hermes-home"
        installed_script = hermes_home / "skills" / "almanac-vaults" / "scripts" / "curate-vaults.sh"
        installed_script.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE_SCRIPT, installed_script)
        installed_script.chmod(0o755)

        token_file = hermes_home / "secrets" / "almanac-bootstrap-token"
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text("tok_test\n", encoding="utf-8")

        fake_repo = root / "shared-repo"
        write_fake_rpc_client(fake_repo)

        result = subprocess.run(
            [str(installed_script), "list"],
            env={
                **os.environ,
                "HERMES_HOME": str(hermes_home),
                "ALMANAC_REPO_DIR": str(fake_repo),
            },
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode == 0, f"expected installed curate-vaults to succeed, got rc={result.returncode} stderr={result.stderr!r}")
        expect("Vault catalog (1 vaults):" in result.stdout, f"unexpected output: {result.stdout!r}")
        expect("Projects" in result.stdout, f"expected Projects in output: {result.stdout!r}")
        print("PASS test_installed_curate_vaults_uses_repo_env_fallback")


def test_vaults_skill_prefers_mcp_recipe_over_shell_wrapper() -> None:
    body = SKILL.read_text(encoding="utf-8")
    expect("## Hermes Recipe Card" in body, body)
    expect(body.index("## Hermes Recipe Card") < body.index("## Contract"), body)
    expect('"tool":"catalog.vaults"' in body, body)
    expect('"tool":"vaults.refresh"' in body, body)
    expect('"tool":"agents.managed-memory"' in body, body)
    expect('"tool":"vaults.subscribe"' in body, body)
    expect("plugin injects local auth" in body, body)
    expect("<bootstrap token>" not in body, body)
    expect("Read the bootstrap token from" not in body, body)
    expect("Preferred agent path: call the `almanac-mcp` MCP tools directly." in body, body)
    expect("## Human CLI Fallback" in body, body)
    expect("not the preferred Hermes" in body, body)
    expect(body.index("## Human CLI Fallback") < body.index("scripts/curate-vaults.sh curate"), body)
    expect("Run the script first" not in body, body)
    print("PASS test_vaults_skill_prefers_mcp_recipe_over_shell_wrapper")


def main() -> int:
    test_installed_curate_vaults_uses_repo_env_fallback()
    test_vaults_skill_prefers_mcp_recipe_over_shell_wrapper()
    print("PASS all 2 almanac-vaults skill regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
