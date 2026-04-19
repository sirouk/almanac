#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONTROL_PY = REPO / "python" / "almanac_control.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_config(path: Path, values: dict[str, str]) -> None:
    lines = [f"{key}={json.dumps(value)}" for key, value in values.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def init_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Almanac Test"], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "almanac-test@example.com"], check=True, capture_output=True, text=True)


def init_bare_git_repo(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--bare", str(path)], check=True, capture_output=True, text=True)


def commit_all(path: Path, message: str) -> None:
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(path), "commit", "-m", message], check=True, capture_output=True, text=True)


def make_config(root: Path) -> Path:
    config_path = root / "config" / "almanac.env"
    values = {
        "ALMANAC_USER": "almanac",
        "ALMANAC_HOME": str(root / "home-almanac"),
        "ALMANAC_REPO_DIR": str(root / "repo"),
        "ALMANAC_PRIV_DIR": str(root / "priv"),
        "STATE_DIR": str(root / "state"),
        "RUNTIME_DIR": str(root / "state" / "runtime"),
        "VAULT_DIR": str(root / "vault"),
        "ALMANAC_DB_PATH": str(root / "state" / "almanac-control.sqlite3"),
        "ALMANAC_AGENTS_STATE_DIR": str(root / "state" / "agents"),
        "ALMANAC_CURATOR_DIR": str(root / "state" / "curator"),
        "ALMANAC_CURATOR_MANIFEST": str(root / "state" / "curator" / "manifest.json"),
        "ALMANAC_CURATOR_HERMES_HOME": str(root / "state" / "curator" / "hermes-home"),
        "ALMANAC_ARCHIVED_AGENTS_DIR": str(root / "state" / "archived-agents"),
        "ALMANAC_RELEASE_STATE_FILE": str(root / "state" / "almanac-release.json"),
        "ALMANAC_QMD_URL": "http://127.0.0.1:8181/mcp",
        "ALMANAC_MCP_HOST": "127.0.0.1",
        "ALMANAC_MCP_PORT": "8282",
        "OPERATOR_NOTIFY_CHANNEL_PLATFORM": "tui-only",
        "OPERATOR_NOTIFY_CHANNEL_ID": "operator",
        "ALMANAC_MODEL_PRESET_CODEX": "openai:codex",
        "ALMANAC_MODEL_PRESET_OPUS": "anthropic:claude-opus",
        "ALMANAC_MODEL_PRESET_CHUTES": "chutes:auto-failover",
        "ALMANAC_CURATOR_CHANNELS": "tui-only",
    }
    write_config(config_path, values)
    return config_path


def write_repos_vault(root: Path) -> Path:
    repos_dir = root / "vault" / "Repos"
    repos_dir.mkdir(parents=True, exist_ok=True)
    (repos_dir / ".vault").write_text(
        "\n".join(
            [
                "name: Repos",
                "description: Repository inventory",
                "owner: organization",
                "default_subscribed: true",
                "category: inventory",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return repos_dir


def test_discover_vault_repo_sources_skips_managed_mirror_content() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_repo_discovery_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = make_config(root)
        repos_dir = write_repos_vault(root)
        human_note = repos_dir / "almanac.md"
        human_note.write_text(
            "# Almanac\n\nRepository URL: https://github.com/example/almanac\n",
            encoding="utf-8",
        )
        managed_dir = repos_dir / "_mirrors" / "example-almanac"
        managed_dir.mkdir(parents=True, exist_ok=True)
        (managed_dir / "REPO-SYNC.md").write_text(
            "<!-- managed: almanac-repo-sync -->\nhttps://github.com/example/ignored\n",
            encoding="utf-8",
        )

        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            discovered = mod.discover_vault_repo_sources(cfg)
            expect(len(discovered) == 1, f"expected one discovered repo source, got {discovered}")
            source = discovered[0]
            expect(source["canonical_url"] == "https://github.com/example/almanac", str(source))
            expect(source["source_paths"] == [str(human_note)], str(source))
            expect(source["local_repo_paths"] == [], str(source))
        finally:
            os.environ.clear()
            os.environ.update(old_env)

        print("PASS test_discover_vault_repo_sources_skips_managed_mirror_content")


def test_discover_vault_repo_sources_finds_git_repo_anywhere_in_vault() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_repo_local_discovery_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = make_config(root)
        write_repos_vault(root)
        local_repo = root / "vault" / "Projects" / "roadmap" / "demo-repo"
        init_git_repo(local_repo)
        subprocess.run(
            ["git", "-C", str(local_repo), "remote", "add", "origin", "https://github.com/example/demo-repo.git"],
            check=True,
            capture_output=True,
            text=True,
        )

        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            discovered = mod.discover_vault_repo_sources(cfg)
            expect(len(discovered) == 1, f"expected one discovered repo source, got {discovered}")
            source = discovered[0]
            expect(source["canonical_url"] == "https://github.com/example/demo-repo", str(source))
            expect(source["source_paths"] == [], str(source))
            expect(source["local_repo_paths"] == [str(local_repo)], str(source))
        finally:
            os.environ.clear()
            os.environ.update(old_env)

        print("PASS test_discover_vault_repo_sources_finds_git_repo_anywhere_in_vault")


def test_sync_vault_repo_mirrors_exports_markdown_and_tracks_changes() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_repo_sync_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = make_config(root)
        repos_dir = write_repos_vault(root)
        repo_note = repos_dir / "almanac.md"
        repo_note.write_text(
            "# Almanac\n\nRepository URL: https://github.com/example/almanac\n",
            encoding="utf-8",
        )

        source_repo = root / "source-repo"
        init_git_repo(source_repo)
        (source_repo / "README.md").write_text("first sync\n", encoding="utf-8")
        (source_repo / "docs").mkdir(parents=True, exist_ok=True)
        (source_repo / "docs" / "guide.md").write_text("guide v1\n", encoding="utf-8")
        (source_repo / "src").mkdir(parents=True, exist_ok=True)
        (source_repo / "src" / "main.py").write_text("print('not mirrored')\n", encoding="utf-8")
        commit_all(source_repo, "initial")

        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            mod.reload_vault_definitions(conn, cfg)

            result = mod.sync_vault_repo_mirrors(
                conn,
                cfg,
                repo_sources=[
                    {
                        "canonical_url": "https://github.com/example/almanac",
                        "remote_url": str(source_repo),
                        "source_paths": [str(repo_note)],
                        "local_repo_paths": [],
                    }
                ],
            )
            mirror_root = root / "vault" / "Repos" / "_mirrors" / "example-almanac"
            expect((mirror_root / "README.md").is_file(), f"expected README mirror in {mirror_root}")
            expect((mirror_root / "docs" / "guide.md").is_file(), f"expected docs mirror in {mirror_root}")
            expect(not (mirror_root / "src" / "main.py").exists(), f"unexpected source mirror in {mirror_root}")
            status_note = (mirror_root / "REPO-SYNC.md").read_text(encoding="utf-8")
            expect("https://github.com/example/almanac" in status_note, status_note)
            expect(str(repo_note) in status_note, status_note)
            expect(any(path.endswith("Repos/_mirrors/example-almanac/README.md") for path in result["changed_paths"]), str(result))
            expect(result["repos_total"] == 1, str(result))

            (source_repo / "README.md").write_text("second sync\n", encoding="utf-8")
            (source_repo / "docs" / "guide.md").unlink()
            commit_all(source_repo, "update docs")

            second = mod.sync_vault_repo_mirrors(
                conn,
                cfg,
                repo_sources=[
                    {
                        "canonical_url": "https://github.com/example/almanac",
                        "remote_url": str(source_repo),
                        "source_paths": [str(repo_note)],
                        "local_repo_paths": [],
                    }
                ],
            )
            expect((mirror_root / "README.md").read_text(encoding="utf-8") == "second sync\n", "expected updated README content")
            expect(not (mirror_root / "docs" / "guide.md").exists(), "expected removed guide mirror")
            expect(any(path.endswith("Repos/_mirrors/example-almanac/README.md") for path in second["changed_paths"]), str(second))
            expect(any(path.endswith("Repos/_mirrors/example-almanac/docs/guide.md") for path in second["changed_paths"]), str(second))

            job = conn.execute(
                "SELECT last_status, last_note FROM refresh_jobs WHERE job_name = 'vault-github-sync'"
            ).fetchone()
            expect(job is not None, "expected vault-github-sync refresh job row")
            expect(str(job["last_status"]) == "ok", str(dict(job)))
        finally:
            os.environ.clear()
            os.environ.update(old_env)

        print("PASS test_sync_vault_repo_mirrors_exports_markdown_and_tracks_changes")


def test_sync_vault_repo_mirrors_pulls_local_repo_in_place() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_local_repo_sync_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = make_config(root)
        write_repos_vault(root)
        local_repo = root / "vault" / "Projects" / "roadmap" / "demo-repo"
        remote_bare = root / "remote.git"
        source_repo = root / "source-repo"
        init_bare_git_repo(remote_bare)
        init_git_repo(source_repo)
        subprocess.run(["git", "-C", str(source_repo), "remote", "add", "origin", str(remote_bare)], check=True, capture_output=True, text=True)
        (source_repo / "README.md").write_text("first local sync\n", encoding="utf-8")
        commit_all(source_repo, "initial")
        subprocess.run(["git", "-C", str(source_repo), "push", "-u", "origin", "main"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "clone", "-b", "main", str(remote_bare), str(local_repo)], check=True, capture_output=True, text=True)

        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            conn = mod.connect_db(cfg)
            mod.reload_vault_definitions(conn, cfg)

            (source_repo / "README.md").write_text("second local sync\n", encoding="utf-8")
            commit_all(source_repo, "update local repo")
            subprocess.run(["git", "-C", str(source_repo), "push", "origin", "main"], check=True, capture_output=True, text=True)

            result = mod.sync_vault_repo_mirrors(
                conn,
                cfg,
                repo_sources=[
                    {
                        "canonical_url": "https://github.com/example/demo-repo",
                        "remote_url": str(remote_bare),
                        "source_paths": [],
                        "local_repo_paths": [str(local_repo)],
                    }
                ],
            )
            expect((local_repo / "README.md").read_text(encoding="utf-8") == "second local sync\n", "expected in-place repo pull to update README")
            expect((root / "vault" / "Repos" / "_mirrors" / "example-demo-repo").exists() is False, "did not expect mirror dir for in-place repo sync")
            expect(any(path.endswith("Projects/roadmap/demo-repo/README.md") for path in result["changed_paths"]), str(result))
            expect(result["repos_total"] == 1, str(result))
            expect(result["repos_failed"] == [], str(result))
            status = result["repo_statuses"][0]
            expect(status["mode"] == "in-place", str(status))
        finally:
            os.environ.clear()
            os.environ.update(old_env)

        print("PASS test_sync_vault_repo_mirrors_pulls_local_repo_in_place")


def main() -> int:
    test_discover_vault_repo_sources_skips_managed_mirror_content()
    test_discover_vault_repo_sources_finds_git_repo_anywhere_in_vault()
    test_sync_vault_repo_mirrors_exports_markdown_and_tracks_changes()
    test_sync_vault_repo_mirrors_pulls_local_repo_in_place()
    print("PASS all 4 repo sync regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
