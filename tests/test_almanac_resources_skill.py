#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "skills" / "almanac-resources" / "scripts" / "show-resources.sh"
SKILL = REPO / "skills" / "almanac-resources" / "SKILL.md"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_almanac_resources_skill_renders_local_no_secret_bundle() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        hermes_home = root / "hermes-home"
        user_home = root / "home" / "veight"
        state_dir = hermes_home / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        user_home.mkdir(parents=True, exist_ok=True)
        (state_dir / "almanac-web-access.json").write_text(
            json.dumps(
                {
                    "unix_user": "veight",
                    "username": "veight",
                    "nextcloud_username": "veight",
                    "dashboard_url": "https://kor.tail77f45e.ts.net:30012/",
                    "code_url": "https://kor.tail77f45e.ts.net:40012/",
                    "tailscale_host": "kor.tail77f45e.ts.net",
                    "password": "do-not-print",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        (state_dir / "almanac-vault-reconciler.json").write_text(
            json.dumps(
                {
                    "resource-ref": (
                        "Canonical user access rails and shared Almanac addresses:\n"
                        "- Vault access in Nextcloud: https://kor.tail77f45e.ts.net:8445/ (shared mount: /Vault)\n"
                        "- QMD MCP retrieval rail: https://kor.tail77f45e.ts.net:8445/mcp\n"
                        "- Shared Notion SSOT: https://www.notion.so/The-Almanac-3497afdeade580789a3cc26cbef6a140\n"
                        "- Credentials are intentionally omitted from managed memory."
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
        expect("Almanac resources:" in output, output)
        expect("Hermes dashboard: https://kor.tail77f45e.ts.net:30012/" in output, output)
        expect("Dashboard username: veight" in output, output)
        expect("Nextcloud login: veight" in output, output)
        expect(f"Workspace root: {user_home}" in output, output)
        expect(f"Almanac vault: {user_home / 'Almanac'}" in output, output)
        expect("Shared Notion SSOT: https://www.notion.so/The-Almanac-3497afdeade580789a3cc26cbef6a140" in output, output)
        expect("Remote SSH target after key install: veight@kor.tail77f45e.ts.net" in output, output)
        expect("do-not-print" not in output, output)
        expect("QMD MCP retrieval rail:" not in output, output)
        print("PASS test_almanac_resources_skill_renders_local_no_secret_bundle")


def test_almanac_resources_skill_documents_home_alias_contract() -> None:
    body = SKILL.read_text(encoding="utf-8")
    expect("/almanac-resources" in body, body)
    expect("~/Almanac" in body, body)
    expect("never print passwords" in body, body)
    expect("central service-user paths" in body, body)
    print("PASS test_almanac_resources_skill_documents_home_alias_contract")


def main() -> int:
    test_almanac_resources_skill_renders_local_no_secret_bundle()
    test_almanac_resources_skill_documents_home_alias_contract()
    print("PASS all 2 Almanac resources skill tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
