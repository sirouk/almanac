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
        hermes_skills_dir = root / "runtime" / "hermes-agent-src" / "skills"
        google_workspace_dir = hermes_skills_dir / "productivity" / "google-workspace"
        google_workspace_dir.mkdir(parents=True, exist_ok=True)
        (google_workspace_dir / "SKILL.md").write_text(
            "---\n"
            "name: google-workspace\n"
            "description: Use Gmail, Calendar, Drive, Sheets, Docs, and Contacts.\n"
            "---\n"
            "# Google Workspace\n",
            encoding="utf-8",
        )
        legacy_flat_skill_note = vault_dir / "Skills" / "arclink-qmd-mcp.md"
        legacy_flat_skill_note.parent.mkdir(parents=True, exist_ok=True)
        legacy_flat_skill_note.write_text(
            "<!-- managed: arclink-generated-vault-note -->\n# Legacy flat skill note\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--repo-dir",
                str(REPO),
                "--vault-dir",
                str(vault_dir),
                "--repo-url",
                "https://github.com/example/arclink",
                "--hermes-skills-dir",
                str(hermes_skills_dir),
            ],
            env={**os.environ},
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode == 0, f"expected reconcile-vault-layout to succeed, got rc={result.returncode} stderr={result.stderr!r}")

        for dirname in ("Research", "Agents_KB", "Agents_Skills", "Projects", "Repos", "Agents_Plugins"):
            target_dir = vault_dir / dirname
            expect(target_dir.is_dir(), f"expected {dirname} directory to exist")
            expect((target_dir / ".vault").is_file(), f"expected {dirname}/.vault metadata file")
            metadata = (target_dir / ".vault").read_text(encoding="utf-8")
            expect("default_subscribed:" in metadata, f"expected subscription flag in {dirname}/.vault: {metadata!r}")
            expect("brief_template:" in metadata, f"expected brief template in {dirname}/.vault: {metadata!r}")

        for legacy in ("Inbox", "People", "Teams"):
            expect(not (vault_dir / legacy).exists(), f"expected untouched legacy default {legacy} to be pruned")
        expect(not (vault_dir / "Skills").exists(), "expected managed legacy Skills directory to be migrated away")
        expect(not (vault_dir / "Plugins").exists(), "expected legacy Plugins directory not to be recreated")

        projects_readme = (vault_dir / "Projects" / "README.md").read_text(encoding="utf-8")
        expect("organization" in projects_readme.lower(), projects_readme)

        repos_note = (vault_dir / "Repos" / "arclink.md").read_text(encoding="utf-8")
        expect("https://github.com/example/arclink" in repos_note, repos_note)

        project_note = (vault_dir / "Projects" / "arclink.md").read_text(encoding="utf-8")
        expect("ArcLink" in project_note, project_note)

        arclink_skill_notes = sorted(path.name for path in (vault_dir / "Agents_Skills" / "ArcLink").glob("*.md") if path.name != "README.md")
        expected_skill_notes = {
            "arclink-first-contact.md",
            "arclink-notion-knowledge.md",
            "arclink-notion-mcp.md",
            "arclink-qmd-mcp.md",
            "arclink-resources.md",
            "arclink-ssot.md",
            "arclink-ssot-connect.md",
            "arclink-upgrade-orchestrator.md",
            "arclink-vault-reconciler.md",
            "arclink-vaults.md",
        }
        expect(expected_skill_notes.issubset(set(arclink_skill_notes)), f"missing seeded ArcLink skill notes: expected {expected_skill_notes}, got {arclink_skill_notes}")
        expect(not legacy_flat_skill_note.exists(), f"expected generated flat skill note to be removed: {legacy_flat_skill_note}")
        hermes_skill_note = vault_dir / "Agents_Skills" / "Hermes" / "productivity" / "google-workspace.md"
        expect(hermes_skill_note.is_file(), f"missing Hermes bundled skill note: {hermes_skill_note}")
        expect("Gmail" in hermes_skill_note.read_text(encoding="utf-8"), hermes_skill_note.read_text(encoding="utf-8"))

        plugin_notes = sorted(path.name for path in (vault_dir / "Agents_Plugins").glob("*.md") if path.name != "README.md")
        expected_plugin_notes = {"arclink-managed-context.md"}
        expect(expected_plugin_notes.issubset(set(plugin_notes)), f"missing seeded plugin notes: expected {expected_plugin_notes}, got {plugin_notes}")
        print("PASS test_reconcile_vault_layout_creates_realistic_org_structure_and_prunes_legacy_defaults")


def test_reconcile_vault_layout_preserves_custom_legacy_agent_dirs_while_migrating_managed_files() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        vault_dir = root / "vault"
        vault_dir.mkdir(parents=True, exist_ok=True)

        legacy_skills_dir = vault_dir / "Skills"
        legacy_plugins_dir = vault_dir / "Plugins"
        (legacy_skills_dir / "ArcLink").mkdir(parents=True, exist_ok=True)
        legacy_plugins_dir.mkdir(parents=True, exist_ok=True)
        (legacy_skills_dir / ".vault").write_text(
            "# managed: arclink-default-vault\nname: Skills\n",
            encoding="utf-8",
        )
        (legacy_skills_dir / "README.md").write_text(
            "<!-- managed: arclink-default-vault -->\n# Skills\n",
            encoding="utf-8",
        )
        (legacy_skills_dir / "ArcLink" / "arclink-ssot.md").write_text(
            "<!-- managed: arclink-generated-vault-note -->\n# Old SSOT note\n",
            encoding="utf-8",
        )
        (legacy_skills_dir / "custom-playbook.md").write_text(
            "# Custom legacy skill note\n\nKeep this where the operator put it.\n",
            encoding="utf-8",
        )
        (legacy_plugins_dir / "arclink-managed-context.md").write_text(
            "<!-- managed: arclink-generated-vault-note -->\n# Old plugin note\n",
            encoding="utf-8",
        )
        (legacy_plugins_dir / "local-plugin-idea.md").write_text(
            "# Local plugin idea\n\nThis is operator-authored content.\n",
            encoding="utf-8",
        )

        for _ in range(2):
            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--repo-dir",
                    str(REPO),
                    "--vault-dir",
                    str(vault_dir),
                    "--repo-url",
                    "https://github.com/example/arclink",
                ],
                env={**os.environ},
                text=True,
                capture_output=True,
                check=False,
            )
            expect(result.returncode == 0, f"expected reconcile-vault-layout to succeed, got rc={result.returncode} stderr={result.stderr!r}")

        expect((legacy_skills_dir / "custom-playbook.md").is_file(), "expected custom legacy Skills content to be preserved")
        expect((legacy_plugins_dir / "local-plugin-idea.md").is_file(), "expected custom legacy Plugins content to be preserved")
        expect(not (legacy_skills_dir / ".vault").exists(), "expected managed legacy Skills metadata to move away")
        expect(not (legacy_skills_dir / "README.md").exists(), "expected managed legacy Skills README to move away")
        expect(not (legacy_skills_dir / "ArcLink" / "arclink-ssot.md").exists(), "expected managed legacy skill note to move away")
        expect(not (legacy_plugins_dir / "arclink-managed-context.md").exists(), "expected managed legacy plugin note to move away")

        skills_metadata = (vault_dir / "Agents_Skills" / ".vault").read_text(encoding="utf-8")
        plugins_metadata = (vault_dir / "Agents_Plugins" / ".vault").read_text(encoding="utf-8")
        expect("name: Agents_Skills" in skills_metadata, skills_metadata)
        expect("name: Agents_Plugins" in plugins_metadata, plugins_metadata)
        expect((vault_dir / "Agents_Skills" / "ArcLink" / "arclink-ssot.md").is_file(), "expected migrated/generated ArcLink skill note")
        expect((vault_dir / "Agents_Plugins" / "arclink-managed-context.md").is_file(), "expected migrated/generated plugin note")
        print("PASS test_reconcile_vault_layout_preserves_custom_legacy_agent_dirs_while_migrating_managed_files")


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
            env={**os.environ, "ARCLINK_UPSTREAM_REPO_URL": "https://github.com/example/arclink.git"},
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode == 0, f"expected reconcile-vault-layout env fallback to succeed, got rc={result.returncode} stderr={result.stderr!r}")
        repos_note = (vault_dir / "Repos" / "arclink.md").read_text(encoding="utf-8")
        expect("https://github.com/example/arclink" in repos_note, repos_note)
        print("PASS test_reconcile_vault_layout_uses_upstream_repo_env_when_repo_dir_is_not_git")


def test_reconcile_vault_layout_sanitizes_pre_rebrand_origin() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo_dir = root / "repo-copy"
        vault_dir = root / "vault"
        repo_dir.mkdir(parents=True, exist_ok=True)
        vault_dir.mkdir(parents=True, exist_ok=True)

        (repo_dir / "templates").symlink_to(REPO / "templates", target_is_directory=True)
        (repo_dir / "skills").symlink_to(REPO / "skills", target_is_directory=True)
        (repo_dir / "plugins").symlink_to(REPO / "plugins", target_is_directory=True)

        legacy_repo = "alma" "nac"
        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--repo-dir",
                str(repo_dir),
                "--vault-dir",
                str(vault_dir),
                "--repo-url",
                f"https://github.com/sirouk/{legacy_repo}.git",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode == 0, f"expected reconcile-vault-layout legacy URL fallback to succeed, got rc={result.returncode} stderr={result.stderr!r}")
        repos_note = (vault_dir / "Repos" / "arclink.md").read_text(encoding="utf-8")
        expect("https://github.com/sirouk/arclink" in repos_note, repos_note)
        expect(legacy_repo not in repos_note, repos_note)
        print("PASS test_reconcile_vault_layout_sanitizes_pre_rebrand_origin")


def main() -> int:
    test_reconcile_vault_layout_creates_realistic_org_structure_and_prunes_legacy_defaults()
    test_reconcile_vault_layout_preserves_custom_legacy_agent_dirs_while_migrating_managed_files()
    test_reconcile_vault_layout_uses_upstream_repo_env_when_repo_dir_is_not_git()
    test_reconcile_vault_layout_sanitizes_pre_rebrand_origin()
    print("PASS all 4 vault bootstrap layout regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
