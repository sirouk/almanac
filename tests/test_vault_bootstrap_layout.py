#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "bin" / "reconcile-vault-layout.py"

LEGACY_VAULT_FILES: dict[str, dict[str, str]] = {
    "Inbox": {
        ".vault": """name: Inbox
description: Unsorted notes that have not been triaged yet; scratch pad for new captures.
owner: operator
default_subscribed: true
category: workspace
tags:
  - triage
  - scratch
brief_template: Unsorted capture surface; items here are in-flight and unstable.
""",
        "README.md": "# Inbox\n\nDrop rough notes, captures, and uploads here first.\n",
    },
    "People": {
        ".vault": """name: People
description: Profiles and reference notes about individuals the organization interacts with.
owner: operator
default_subscribed: true
category: directory
tags:
  - people
  - contacts
""",
        "README.md": "# People\n\nKeep relationship notes, context, and follow-ups here.\n",
    },
    "Projects": {
        ".vault": """name: Projects
description: Active project workspaces, briefs, and decision logs.
owner: operator
default_subscribed: true
category: workspace
tags:
  - projects
  - active
""",
        "README.md": "# Projects\n\nCreate one folder per project and keep durable notes close to the work.\n",
    },
    "Teams": {
        ".vault": """name: Teams
description: Team charters, norms, and rituals. Not auto-subscribed by default.
owner: operator
default_subscribed: false
category: directory
tags:
  - teams
  - charters
""",
        "README.md": "# Teams\n\nShared operating notes, rituals, and references live here.\n",
    },
}


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_reconcile_vault_layout_creates_realistic_org_structure_and_prunes_legacy_defaults() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        vault_dir = root / "vault"
        vault_dir.mkdir(parents=True, exist_ok=True)

        for dirname, files in LEGACY_VAULT_FILES.items():
            target_dir = vault_dir / dirname
            target_dir.mkdir(parents=True, exist_ok=True)
            for relative_path, body in files.items():
                (target_dir / relative_path).write_text(body, encoding="utf-8")

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--repo-dir",
                str(REPO),
                "--vault-dir",
                str(vault_dir),
                "--repo-url",
                "https://github.com/sirouk/almanac",
            ],
            env={**os.environ},
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode == 0, f"expected reconcile-vault-layout to succeed, got rc={result.returncode} stderr={result.stderr!r}")

        for dirname in ("Research", "Skills", "Projects", "Repos", "Plugins"):
            target_dir = vault_dir / dirname
            expect(target_dir.is_dir(), f"expected {dirname} directory to exist")
            expect((target_dir / ".vault").is_file(), f"expected {dirname}/.vault metadata file")
            metadata = (target_dir / ".vault").read_text(encoding="utf-8")
            expect("default_subscribed:" in metadata, f"expected subscription flag in {dirname}/.vault: {metadata!r}")
            expect("brief_template:" in metadata, f"expected brief template in {dirname}/.vault: {metadata!r}")

        for legacy in ("Inbox", "People", "Teams"):
            expect(not (vault_dir / legacy).exists(), f"expected untouched legacy default {legacy} to be pruned")

        projects_readme = (vault_dir / "Projects" / "README.md").read_text(encoding="utf-8")
        expect("organization" in projects_readme.lower(), projects_readme)

        repos_note = (vault_dir / "Repos" / "almanac.md").read_text(encoding="utf-8")
        expect("https://github.com/sirouk/almanac" in repos_note, repos_note)

        project_note = (vault_dir / "Projects" / "almanac.md").read_text(encoding="utf-8")
        expect("Almanac" in project_note, project_note)

        skill_notes = sorted(path.name for path in (vault_dir / "Skills").glob("*.md") if path.name != "README.md")
        expected_skill_notes = {
            "almanac-first-contact.md",
            "almanac-qmd-mcp.md",
            "almanac-ssot.md",
            "almanac-upgrade-orchestrator.md",
            "almanac-vault-reconciler.md",
            "almanac-vaults.md",
        }
        expect(expected_skill_notes.issubset(set(skill_notes)), f"missing seeded skill notes: expected {expected_skill_notes}, got {skill_notes}")

        plugin_notes = sorted(path.name for path in (vault_dir / "Plugins").glob("*.md") if path.name != "README.md")
        expected_plugin_notes = {"almanac-managed-context.md"}
        expect(expected_plugin_notes.issubset(set(plugin_notes)), f"missing seeded plugin notes: expected {expected_plugin_notes}, got {plugin_notes}")
        print("PASS test_reconcile_vault_layout_creates_realistic_org_structure_and_prunes_legacy_defaults")


def test_reconcile_vault_layout_uses_upstream_repo_env_when_repo_dir_is_not_git() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo_dir = root / "repo-copy"
        vault_dir = root / "vault"
        repo_dir.mkdir(parents=True, exist_ok=True)
        vault_dir.mkdir(parents=True, exist_ok=True)

        (repo_dir / "templates").symlink_to(REPO / "templates", target_is_directory=True)
        (repo_dir / "skills").symlink_to(REPO / "skills", target_is_directory=True)
        (repo_dir / "plugins").symlink_to(REPO / "plugins", target_is_directory=True)

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--repo-dir",
                str(repo_dir),
                "--vault-dir",
                str(vault_dir),
            ],
            env={**os.environ, "ALMANAC_UPSTREAM_REPO_URL": "https://github.com/sirouk/almanac.git"},
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode == 0, f"expected reconcile-vault-layout env fallback to succeed, got rc={result.returncode} stderr={result.stderr!r}")
        repos_note = (vault_dir / "Repos" / "almanac.md").read_text(encoding="utf-8")
        expect("https://github.com/sirouk/almanac" in repos_note, repos_note)
        print("PASS test_reconcile_vault_layout_uses_upstream_repo_env_when_repo_dir_is_not_git")


def main() -> int:
    test_reconcile_vault_layout_creates_realistic_org_structure_and_prunes_legacy_defaults()
    test_reconcile_vault_layout_uses_upstream_repo_env_when_repo_dir_is_not_git()
    print("PASS all 2 vault bootstrap layout regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
