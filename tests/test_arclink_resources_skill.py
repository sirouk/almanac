#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "skills" / "arclink-resources" / "scripts" / "show-resources.sh"
SKILL = REPO / "skills" / "arclink-resources" / "SKILL.md"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_arclink_resources_skill_renders_local_no_secret_bundle() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        hermes_home = root / "hermes-home"
        user_home = root / "home" / "operator2"
        state_dir = hermes_home / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        user_home.mkdir(parents=True, exist_ok=True)
        (state_dir / "arclink-web-access.json").write_text(
            json.dumps(
                {
                    "unix_user": "operator2",
                    "username": "operator2",
                    "nextcloud_username": "operator2",
                    "dashboard_url": "https://arclink.example.test:30012/",
                    "code_url": "https://arclink.example.test:40012/",
                    "tailscale_host": "arclink.example.test",
                    "remote_setup_url": "https://arclink.example.test/setup-remote-hermes-client.sh",
                    "password": "do-not-print",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        (state_dir / "arclink-vault-reconciler.json").write_text(
            json.dumps(
                {
                    "resource-ref": (
                        "Canonical user access rails and shared ArcLink addresses:\n"
                        "- Legacy Nextcloud access is disabled; use Drive in Hermes.\n"
                        "- QMD MCP retrieval rail: https://arclink.example.test:8445/mcp\n"
                        "- Shared Notion SSOT: https://www.notion.so/The-ArcLink-00000000000040008000000000000003\n"
                        "- Credentials are intentionally omitted from plugin-managed context."
                    )
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [str(SCRIPT)],
            env={**os.environ, "HERMES_HOME": str(hermes_home), "HOME": str(user_home)},
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode == 0, f"show-resources failed: stdout={result.stdout!r} stderr={result.stderr!r}")
        output = result.stdout
        expect("ArcLink resources:" in output, output)
        expect("Hermes dashboard: https://arclink.example.test:30012/" in output, output)
        expect("Dashboard username: operator2" in output, output)
        expect("Nextcloud login:" not in output, output)
        expect(f"Workspace root: {user_home}" in output, output)
        expect(f"ArcLink vault: {user_home / 'ArcLink'}" in output, output)
        expect("Shared Notion SSOT: https://www.notion.so/The-ArcLink-00000000000040008000000000000003" in output, output)
        expect("Remote SSH target after key install: operator2@arclink.example.test" in output, output)
        expect("Raven" not in output, output)
        expect("raw.githubusercontent.com/example/arclink" not in output, output)
        expect("do-not-print" not in output, output)
        expect("QMD MCP retrieval rail:" not in output, output)
        print("PASS test_arclink_resources_skill_renders_local_no_secret_bundle")


def test_arclink_resources_skill_documents_home_alias_contract() -> None:
    body = SKILL.read_text(encoding="utf-8")
    expect("/arclink-resources" in body, body)
    expect("~/ArcLink" in body, body)
    expect("never print passwords" in body, body)
    expect("central service-user paths" in body, body)
    expect("Curator/operator" in body, body)
    expect("Raven" not in body, body)
    script_body = SCRIPT.read_text(encoding="utf-8")
    expect("raw.githubusercontent.com/example/arclink" not in script_body, script_body)
    print("PASS test_arclink_resources_skill_documents_home_alias_contract")


def main() -> int:
    test_arclink_resources_skill_renders_local_no_secret_bundle()
    test_arclink_resources_skill_documents_home_alias_contract()
    print("PASS all 2 ArcLink resources skill tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
