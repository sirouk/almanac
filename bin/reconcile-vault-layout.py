#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
from pathlib import Path

MANAGED_MARKER_MD = "<!-- managed: arclink-default-vault -->"
MANAGED_MARKER_NOTE = "<!-- managed: arclink-generated-vault-note -->"
MANAGED_MARKER_VAULT = "# managed: arclink-default-vault"
AGENT_SKILLS_DIRNAME = "Agents_Skills"
AGENT_PLUGINS_DIRNAME = "Agents_Plugins"
LEGACY_AGENT_SKILLS_DIRNAME = "Skills"
LEGACY_AGENT_PLUGINS_DIRNAME = "Plugins"
AGENT_LAYOUT_MIGRATIONS = (
    (LEGACY_AGENT_SKILLS_DIRNAME, AGENT_SKILLS_DIRNAME),
    (LEGACY_AGENT_PLUGINS_DIRNAME, AGENT_PLUGINS_DIRNAME),
)
CANONICAL_REPO_URL = "https://github.com/sirouk/arclink"
LEGACY_REPO_NAME = "alma" "nac"

LEGACY_DEFAULTS: dict[str, dict[str, str]] = {
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconcile ArcLink's default shared-vault layout.")
    parser.add_argument("--repo-dir", required=True, help="Path to the ArcLink repo checkout")
    parser.add_argument("--vault-dir", required=True, help="Path to the shared vault root")
    parser.add_argument("--repo-url", default="", help="Optional GitHub repo URL override")
    parser.add_argument("--hermes-skills-dir", default="", help="Optional Hermes bundled skills directory")
    return parser.parse_args()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def sync_text(path: Path, content: str, *, legacy_contents: list[str] | None = None) -> str:
    legacy_contents = legacy_contents or []
    marker = content.splitlines()[0].strip() if content.splitlines() else ""
    if not path.exists():
        write_text(path, content)
        return "created"

    existing = read_text(path)
    if existing == content:
        return "unchanged"

    if marker and existing.startswith(marker):
        write_text(path, content)
        return "updated"

    if existing in legacy_contents:
        write_text(path, content)
        return "updated"

    return "preserved"


def remove_managed_note(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        existing = read_text(path)
    except (OSError, UnicodeDecodeError):
        return False
    if existing.startswith(MANAGED_MARKER_NOTE):
        path.unlink()
        return True
    return False


def is_managed_vault_file(path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    try:
        existing = read_text(path)
    except (OSError, UnicodeDecodeError):
        return False
    return (
        existing.startswith(MANAGED_MARKER_MD)
        or existing.startswith(MANAGED_MARKER_NOTE)
        or existing.startswith(MANAGED_MARKER_VAULT)
    )


def is_fully_managed_tree(root: Path) -> bool:
    if root.is_symlink() or not root.is_dir():
        return False
    for child in root.rglob("*"):
        if child.is_symlink():
            return False
        if child.is_file():
            if not is_managed_vault_file(child):
                return False
            continue
        if child.is_dir():
            continue
        return False
    return True


def remove_empty_ancestors(path: Path, stop_at: Path) -> int:
    if not path.exists():
        return 0
    removed = 0
    current = path
    while current == stop_at or stop_at in current.parents:
        try:
            current.rmdir()
        except OSError:
            break
        else:
            removed += 1
        if current == stop_at:
            break
        current = current.parent
    return removed


def move_managed_files(source_dir: Path, target_dir: Path) -> dict[str, int]:
    counts = {"moved_files": 0, "removed_files": 0, "removed_dirs": 0}
    if source_dir.is_symlink() or not source_dir.is_dir():
        return counts

    managed_files = sorted(
        (path for path in source_dir.rglob("*") if path.is_file() and not path.is_symlink()),
        key=lambda path: path.relative_to(source_dir).as_posix(),
    )
    touched_source_dirs: set[Path] = set()
    for source_path in managed_files:
        if not is_managed_vault_file(source_path):
            continue
        touched_source_dirs.add(source_path.parent)
        relative_path = source_path.relative_to(source_dir)
        target_path = target_dir / relative_path
        if target_path.exists():
            source_path.unlink()
            counts["removed_files"] += 1
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_path), str(target_path))
        counts["moved_files"] += 1

    for source_parent in sorted(touched_source_dirs, key=lambda path: len(path.parts), reverse=True):
        counts["removed_dirs"] += remove_empty_ancestors(source_parent, source_dir)
    return counts


def migrate_agent_vault_layout(vault_dir: Path) -> dict[str, int]:
    counts = {"renamed_dirs": 0, "moved_files": 0, "removed_files": 0, "removed_dirs": 0}
    for legacy_name, target_name in AGENT_LAYOUT_MIGRATIONS:
        source_dir = vault_dir / legacy_name
        target_dir = vault_dir / target_name
        if source_dir.is_symlink() or not source_dir.is_dir():
            continue

        if not target_dir.exists() and is_fully_managed_tree(source_dir):
            source_dir.rename(target_dir)
            counts["renamed_dirs"] += 1
            continue

        migrated = move_managed_files(source_dir, target_dir)
        for key, value in migrated.items():
            counts[key] += value
    return counts


def normalize_repo_url(repo_url: str) -> str:
    value = repo_url.strip()
    if value.endswith(".git"):
        value = value[:-4]
    if re.search(rf"github\.com[:/]sirouk/{LEGACY_REPO_NAME}$", value):
        value = CANONICAL_REPO_URL
    return value.rstrip("/")


def discover_repo_url(repo_dir: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "remote", "get-url", "origin"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return normalize_repo_url(result.stdout.strip())


def template_vault_dirs(repo_dir: Path) -> list[Path]:
    root = repo_dir / "templates" / "arclink-priv" / "vault"
    return sorted(
        path
        for path in root.iterdir()
        if path.is_dir()
        and not path.name.startswith(".")
        and any(child.is_file() for child in path.iterdir())
    )


def prune_legacy_dir(vault_dir: Path, dirname: str) -> bool:
    target = vault_dir / dirname
    legacy_files = LEGACY_DEFAULTS.get(dirname, {})
    if not target.is_dir() or not legacy_files:
        return False

    actual_files = sorted(path for path in target.rglob("*") if path.is_file())
    relative_names = {path.relative_to(target).as_posix() for path in actual_files}
    if relative_names != set(legacy_files):
        return False

    for relative_name, expected_body in legacy_files.items():
        path = target / relative_name
        if not path.is_file() or read_text(path) != expected_body:
            return False

    shutil.rmtree(target)
    return True


def load_skill_metadata(skill_dir: Path) -> tuple[str, str]:
    skill_file = skill_dir / "SKILL.md"
    name = skill_dir.name
    description = ""
    if not skill_file.is_file():
        return name, description

    text = read_text(skill_file)
    frontmatter_match = re.match(r"---\n(.*?)\n---\n", text, flags=re.DOTALL)
    if frontmatter_match:
        for raw_line in frontmatter_match.group(1).splitlines():
            line = raw_line.strip()
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("description:"):
                description = line.split(":", 1)[1].strip()
    return name, description


def load_plugin_metadata(plugin_dir: Path) -> tuple[str, str]:
    manifest_file = plugin_dir / "plugin.yaml"
    name = plugin_dir.name
    description = ""
    if not manifest_file.is_file():
        return name, description

    for raw_line in read_text(manifest_file).splitlines():
        line = raw_line.strip()
        if line.startswith("name:"):
            name = line.split(":", 1)[1].strip()
        elif line.startswith("description:"):
            description = line.split(":", 1)[1].strip()
    return name, description


def make_skill_note(skill_id: str, name: str, description: str, repo_url: str) -> str:
    lines = [
        MANAGED_MARKER_NOTE,
        f"# {name}",
        "",
        f"Skill ID: `{skill_id}`",
        "",
        f"Description: {description or 'Shipped with ArcLink for shared agent workflows.'}",
        "",
        "How to use this note:",
        "- Capture local conventions, examples, and rollout status for this skill.",
        "- Link the operators, agents, and workflows that depend on it.",
        "- Keep durable usage guidance here while the SKILL.md stays the executable reference.",
        "",
        "Sources:",
        f"- Local: `skills/{skill_id}/SKILL.md`",
    ]
    if repo_url:
        lines.append(f"- GitHub: {repo_url}/tree/main/skills/{skill_id}")
    lines.extend(
        [
            "",
            "Suggested expansions:",
            "- org-specific examples",
            "- known pitfalls",
            "- rollout / ownership",
            "- related vault notes and runbooks",
            "",
        ]
    )
    return "\n".join(lines)


def make_hermes_skill_note(skill_id: str, rel_dir: str, name: str, description: str, hermes_ref: str) -> str:
    source_url = f"https://github.com/NousResearch/hermes-agent/tree/{hermes_ref or 'main'}/skills/{rel_dir}"
    lines = [
        MANAGED_MARKER_NOTE,
        f"# {name}",
        "",
        f"Skill ID: `{skill_id}`",
        f"Hermes category path: `skills/{rel_dir}`",
        "",
        f"Description: {description or 'Bundled with the pinned Hermes agent runtime.'}",
        "",
        "How to use this note:",
        "- Capture local setup notes, rollout status, and examples for this Hermes bundled skill.",
        "- Keep durable organization guidance here while the SKILL.md stays the executable reference.",
        "- Put credentials and private setup values in the user's Hermes home, not in this shared note.",
        "",
        "Sources:",
        f"- Local runtime: `hermes-agent-src/skills/{rel_dir}/SKILL.md`",
        f"- Upstream: {source_url}",
        "",
        "Suggested expansions:",
        "- org-specific examples",
        "- required credentials and setup ownership",
        "- known pitfalls",
        "- related vault notes and runbooks",
        "",
    ]
    return "\n".join(lines)


def make_skill_folder_readme(title: str, body: str) -> str:
    return "\n".join(
        [
            MANAGED_MARKER_NOTE,
            f"# {title}",
            "",
            body,
            "",
        ]
    )


def discover_hermes_skills_dir(repo_dir: Path, explicit: str) -> Path | None:
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    for env_name in ("ARCLINK_HERMES_BUNDLED_SKILLS_DIR", "HERMES_BUNDLED_SKILLS"):
        value = os.environ.get(env_name, "").strip()
        if value:
            candidates.append(Path(value))
    runtime_dir = os.environ.get("RUNTIME_DIR", "").strip()
    if runtime_dir:
        candidates.append(Path(runtime_dir) / "hermes-agent-src" / "skills")
    candidates.append(repo_dir / "arclink-priv" / "state" / "runtime" / "hermes-agent-src" / "skills")

    for candidate in candidates:
        if candidate.is_dir() and any(candidate.rglob("SKILL.md")):
            return candidate
    return None


def make_repo_note(repo_name: str, repo_url: str, repo_dir: Path) -> str:
    lines = [
        MANAGED_MARKER_NOTE,
        f"# {repo_name}",
        "",
        "Repository role: shared source of truth for code, deployment, and operational behavior.",
        "",
    ]
    if repo_url:
        lines.append(f"Repository URL: {repo_url}")
    lines.extend(
        [
            f"Local checkout: `{repo_dir}`",
            "",
            "What belongs here:",
            "- architecture notes",
            "- deployment and CI quirks",
            "- release / migration notes",
            "- onboarding guidance for contributors and agents",
            "",
        ]
    )
    return "\n".join(lines)


def make_project_note(project_name: str, repo_name: str, repo_url: str) -> str:
    lines = [
        MANAGED_MARKER_NOTE,
        f"# {project_name}",
        "",
        "Project role: shared organizational workspace for the ArcLink system and its operational roadmap.",
        "",
        f"Primary repo: {repo_name}",
    ]
    if repo_url:
        lines.append(f"Repo URL: {repo_url}")
    lines.extend(
        [
            "",
            "Suggested project subtopics:",
            "- roadmap and priorities",
            "- architecture decisions",
            "- deployment / environment notes",
            "- operator procedures",
            "- cross-team dependencies",
            "",
        ]
    )
    return "\n".join(lines)


def make_plugin_note(plugin_id: str, name: str, description: str, repo_url: str) -> str:
    lines = [
        MANAGED_MARKER_NOTE,
        f"# {name}",
        "",
        f"Plugin ID: `{plugin_id}`",
        "",
        f"Description: {description or 'Hermes Agent plugin shipped with ArcLink for shared managed-context refresh.'}",
        "",
        "How to use this note:",
        "- capture rollout status and the agent cohorts that should have this plugin installed",
        "- record what the plugin injects or automates at runtime",
        "- document caveats, compatibility notes, and troubleshooting",
        "",
        "Sources:",
        f"- Local: `plugins/hermes-agent/{plugin_id}/plugin.yaml`",
    ]
    if repo_url:
        lines.append(f"- GitHub: {repo_url}/tree/main/plugins/hermes-agent/{plugin_id}")
    lines.extend(
        [
            "",
            "Suggested expansions:",
            "- rollout / ownership",
            "- compatibility matrix",
            "- operator runbooks",
            "- related vault notes and skills",
            "",
        ]
    )
    return "\n".join(lines)


def reconcile_static_vault_templates(repo_dir: Path, vault_dir: Path) -> dict[str, int]:
    counts = {"created": 0, "updated": 0, "preserved": 0}
    for template_dir in template_vault_dirs(repo_dir):
        target_dir = vault_dir / template_dir.name
        target_dir.mkdir(parents=True, exist_ok=True)
        for child in sorted(path for path in template_dir.iterdir() if path.is_file()):
            legacy_body = LEGACY_DEFAULTS.get(template_dir.name, {}).get(child.name)
            result = sync_text(target_dir / child.name, read_text(child), legacy_contents=[legacy_body] if legacy_body else None)
            if result in counts:
                counts[result] += 1
    return counts


def reconcile_dynamic_notes(repo_dir: Path, vault_dir: Path, repo_url: str, hermes_skills_dir: Path | None) -> dict[str, int]:
    counts = {"created": 0, "updated": 0, "preserved": 0}
    skills_dir = vault_dir / AGENT_SKILLS_DIRNAME
    legacy_skills_dir = vault_dir / LEGACY_AGENT_SKILLS_DIRNAME
    arclink_skills_dir = skills_dir / "ArcLink"
    hermes_notes_dir = skills_dir / "Hermes"
    for note_path, title, body in (
        (
            arclink_skills_dir / "README.md",
            "ArcLink Skills",
            "Notes for the ArcLink-managed skills installed into every Curator and enrolled-agent Hermes home.",
        ),
        (
            hermes_notes_dir / "README.md",
            "Hermes Bundled Skills",
            "Notes for the official skills bundled with the pinned Hermes runtime and synced into agent Hermes homes.",
        ),
    ):
        result = sync_text(note_path, make_skill_folder_readme(title, body))
        if result in counts:
            counts[result] += 1

    for skill_dir in sorted(path for path in (repo_dir / "skills").iterdir() if path.is_dir() and (path / "SKILL.md").is_file()):
        name, description = load_skill_metadata(skill_dir)
        result = sync_text(
            arclink_skills_dir / f"{skill_dir.name}.md",
            make_skill_note(skill_dir.name, name, description, repo_url),
        )
        if result in counts:
            counts[result] += 1
        remove_managed_note(skills_dir / f"{skill_dir.name}.md")
        remove_managed_note(legacy_skills_dir / f"{skill_dir.name}.md")
        remove_managed_note(legacy_skills_dir / "ArcLink" / f"{skill_dir.name}.md")

    if hermes_skills_dir is not None:
        hermes_ref = os.environ.get("ARCLINK_HERMES_AGENT_REF", "").strip()
        for skill_file in sorted(hermes_skills_dir.rglob("SKILL.md")):
            skill_dir = skill_file.parent
            if any(part in {".git", ".github", ".hub"} for part in skill_file.parts):
                continue
            try:
                rel_dir = skill_dir.relative_to(hermes_skills_dir).as_posix()
            except ValueError:
                continue
            name, description = load_skill_metadata(skill_dir)
            result = sync_text(
                hermes_notes_dir / f"{rel_dir}.md",
                make_hermes_skill_note(skill_dir.name, rel_dir, name, description, hermes_ref),
            )
            if result in counts:
                counts[result] += 1

    plugins_root = repo_dir / "plugins" / "hermes-agent"
    plugins_dir = vault_dir / AGENT_PLUGINS_DIRNAME
    legacy_plugins_dir = vault_dir / LEGACY_AGENT_PLUGINS_DIRNAME
    if plugins_root.is_dir():
        for plugin_dir in sorted(path for path in plugins_root.iterdir() if path.is_dir() and (path / "plugin.yaml").is_file()):
            name, description = load_plugin_metadata(plugin_dir)
            result = sync_text(
                plugins_dir / f"{plugin_dir.name}.md",
                make_plugin_note(plugin_dir.name, name, description, repo_url),
            )
            if result in counts:
                counts[result] += 1
            remove_managed_note(legacy_plugins_dir / f"{plugin_dir.name}.md")

    repo_name = repo_url.rsplit("/", 1)[-1] if repo_url else repo_dir.name
    repo_note = make_repo_note(repo_name, repo_url, repo_dir)
    result = sync_text(vault_dir / "Repos" / f"{repo_name}.md", repo_note)
    if result in counts:
        counts[result] += 1

    project_note = make_project_note("ArcLink", repo_name, repo_url)
    result = sync_text(vault_dir / "Projects" / "arclink.md", project_note)
    if result in counts:
        counts[result] += 1

    return counts


def main() -> int:
    args = parse_args()
    repo_dir = Path(args.repo_dir).resolve()
    vault_dir = Path(args.vault_dir).resolve()
    repo_url = (
        normalize_repo_url(args.repo_url)
        or normalize_repo_url(os.environ.get("ARCLINK_UPSTREAM_REPO_URL", ""))
        or discover_repo_url(repo_dir)
    )
    hermes_skills_dir = discover_hermes_skills_dir(repo_dir, args.hermes_skills_dir)

    vault_dir.mkdir(parents=True, exist_ok=True)

    pruned = [name for name in ("Inbox", "People", "Teams") if prune_legacy_dir(vault_dir, name)]
    migrated_agent_layout = migrate_agent_vault_layout(vault_dir)
    static_counts = reconcile_static_vault_templates(repo_dir, vault_dir)
    dynamic_counts = reconcile_dynamic_notes(repo_dir, vault_dir, repo_url, hermes_skills_dir)

    print(f"vault_dir={vault_dir}")
    if repo_url:
        print(f"repo_url={repo_url}")
    if pruned:
        print("pruned_legacy_defaults=" + ",".join(pruned))
    if any(migrated_agent_layout.values()):
        print(
            "migrated_agent_layout="
            f"renamed_dirs:{migrated_agent_layout['renamed_dirs']} "
            f"moved_files:{migrated_agent_layout['moved_files']} "
            f"removed_files:{migrated_agent_layout['removed_files']} "
            f"removed_dirs:{migrated_agent_layout['removed_dirs']}"
        )
    print(
        "static_files="
        f"created:{static_counts['created']} updated:{static_counts['updated']} preserved:{static_counts['preserved']}"
    )
    print(
        "dynamic_notes="
        f"created:{dynamic_counts['created']} updated:{dynamic_counts['updated']} preserved:{dynamic_counts['preserved']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
