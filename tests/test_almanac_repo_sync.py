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


def init_git_repo(path: Path, branch: str = "main") -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", branch, str(path)], check=True, capture_output=True, text=True)
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


def make_clone_with_remote(
    root: Path, *, clone_path: Path, branch: str = "main", seed_content: dict[str, str] | None = None
) -> tuple[Path, Path]:
    """Build a bare remote and a vault-side clone for sync tests. Returns
    (bare_remote, seed_repo) so a test can push new commits to bare_remote
    and then exercise the rail against clone_path."""
    bare_remote = root / f"{clone_path.name}-remote.git"
    seed_repo = root / f"{clone_path.name}-seed"
    init_bare_git_repo(bare_remote)
    init_git_repo(seed_repo, branch=branch)
    subprocess.run(
        ["git", "-C", str(seed_repo), "remote", "add", "origin", str(bare_remote)],
        check=True,
        capture_output=True,
        text=True,
    )
    for rel, content in (seed_content or {"README.md": "seed\n"}).items():
        target = seed_repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    commit_all(seed_repo, "initial")
    subprocess.run(
        ["git", "-C", str(seed_repo), "push", "-u", "origin", branch],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "clone", "-b", branch, str(bare_remote), str(clone_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return bare_remote, seed_repo


def test_discover_vault_repo_sources_ignores_markdown_url_mentions() -> None:
    """The rail no longer scans markdown for github URLs. A note mentioning
    a repo URL must NOT cause that repo to appear as a sync source."""
    mod = load_module(CONTROL_PY, "almanac_control_repo_discovery_no_urlmining")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = make_config(root)
        repos_dir = write_repos_vault(root)
        human_note = repos_dir / "almanac.md"
        human_note.write_text(
            "# Almanac\n\nUseful reference: https://github.com/example/almanac\n"
            "See also git@github.com:example/other.git for something else.\n",
            encoding="utf-8",
        )

        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            discovered = mod.discover_vault_repo_sources(cfg)
            expect(discovered == [], f"expected zero discovered sources; URL-mining is retired, got {discovered}")
        finally:
            os.environ.clear()
            os.environ.update(old_env)

        print("PASS test_discover_vault_repo_sources_ignores_markdown_url_mentions")


def test_discover_vault_repo_sources_finds_local_git_checkouts() -> None:
    """Operator clones a repo into the vault; discovery returns that path
    with its origin URL (canonical-normalized for github)."""
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
            expect(source["remote_url"] == "https://github.com/example/demo-repo.git", str(source))
            expect(source["source_paths"] == [], str(source))
            expect(source["local_repo_paths"] == [str(local_repo)], str(source))
        finally:
            os.environ.clear()
            os.environ.update(old_env)

        print("PASS test_discover_vault_repo_sources_finds_local_git_checkouts")


def test_discover_vault_repo_sources_skips_pinned_sync_trees_and_legacy_mirrors() -> None:
    """Discovery must not pull checkouts under pinned-sync trees (identified
    by .almanac-source.json) or inside the legacy Repos/_mirrors/ subtree,
    even if they happen to contain a .git/ directory."""
    mod = load_module(CONTROL_PY, "almanac_control_repo_discovery_skips_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = make_config(root)
        write_repos_vault(root)

        # A legitimate operator checkout — must be found.
        legit_repo = root / "vault" / "Projects" / "demo"
        init_git_repo(legit_repo)
        subprocess.run(
            ["git", "-C", str(legit_repo), "remote", "add", "origin", "https://github.com/example/demo.git"],
            check=True,
            capture_output=True,
            text=True,
        )

        # A pinned-sync tree — must be skipped.
        pinned_dir = root / "vault" / "Repos" / "hermes-agent-docs"
        pinned_dir.mkdir(parents=True, exist_ok=True)
        (pinned_dir / ".almanac-source.json").write_text("{\n  \"repo_ref\": \"abc123\"\n}\n", encoding="utf-8")
        hidden_repo_in_pinned = pinned_dir / "nested-checkout"
        init_git_repo(hidden_repo_in_pinned)
        subprocess.run(
            ["git", "-C", str(hidden_repo_in_pinned), "remote", "add", "origin", "https://github.com/example/leaked.git"],
            check=True,
            capture_output=True,
            text=True,
        )

        # Legacy mirrors subtree — must be skipped.
        legacy_mirror = root / "vault" / "Repos" / "_mirrors" / "example-legacy"
        init_git_repo(legacy_mirror)
        subprocess.run(
            ["git", "-C", str(legacy_mirror), "remote", "add", "origin", "https://github.com/example/legacy.git"],
            check=True,
            capture_output=True,
            text=True,
        )

        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        try:
            cfg = mod.Config.from_env()
            discovered = mod.discover_vault_repo_sources(cfg)
            expect(len(discovered) == 1, f"expected exactly one repo (legit only), got {discovered}")
            expect(discovered[0]["local_repo_paths"] == [str(legit_repo)], str(discovered[0]))
        finally:
            os.environ.clear()
            os.environ.update(old_env)

        print("PASS test_discover_vault_repo_sources_skips_pinned_sync_trees_and_legacy_mirrors")


def test_sync_vault_repo_mirrors_hard_resets_to_origin_overwriting_local_changes() -> None:
    """Pulling a vault checkout must match origin/<branch> exactly:
      - remote updates applied (README: seed -> updated)
      - local uncommitted edits are overwritten
      - local commits ahead of origin are dropped
      - untracked files are cleaned, including gitignored build caches
    """
    mod = load_module(CONTROL_PY, "almanac_control_hard_reset_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = make_config(root)
        write_repos_vault(root)
        local_repo = root / "vault" / "Projects" / "demo"
        bare_remote, seed_repo = make_clone_with_remote(
            root,
            clone_path=local_repo,
            seed_content={
                "README.md": "seed\n",
                ".gitignore": "build/\n",
            },
        )

        # Advance origin.
        (seed_repo / "README.md").write_text("updated\n", encoding="utf-8")
        (seed_repo / "docs.md").write_text("new doc\n", encoding="utf-8")
        commit_all(seed_repo, "upstream update")
        subprocess.run(["git", "-C", str(seed_repo), "push", "origin", "main"], check=True, capture_output=True, text=True)

        # Muck up the local checkout in every way that should be overwritten.
        (local_repo / "README.md").write_text("MY LOCAL HACK\n", encoding="utf-8")           # uncommitted edit
        (local_repo / "scratch.md").write_text("untracked\n", encoding="utf-8")              # untracked file
        (local_repo / "build").mkdir(parents=True, exist_ok=True)
        (local_repo / "build" / "artifact.bin").write_text("binary\n", encoding="utf-8")     # gitignored file — MUST be cleaned

        # And a local commit ahead of origin that should also be dropped.
        (local_repo / "local-only.md").write_text("local only commit\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(local_repo), "add", "local-only.md"], check=True, capture_output=True, text=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(local_repo),
                "-c",
                "user.name=Local Hack",
                "-c",
                "user.email=local@example.com",
                "commit",
                "-m",
                "will be dropped",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

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
                        "canonical_url": "https://github.com/example/demo",
                        "remote_url": str(bare_remote),
                        "source_paths": [],
                        "local_repo_paths": [str(local_repo)],
                    }
                ],
            )

            # Remote state wins.
            expect((local_repo / "README.md").read_text(encoding="utf-8") == "updated\n", "README must match origin")
            expect((local_repo / "docs.md").read_text(encoding="utf-8") == "new doc\n", "new upstream file must land")
            # Local-only commit was dropped: local-only.md no longer exists.
            expect(not (local_repo / "local-only.md").exists(), "local commit ahead of origin must be dropped")
            # Untracked non-ignored file was cleaned.
            expect(not (local_repo / "scratch.md").exists(), "untracked non-gitignored files must be cleaned")
            # Gitignored files are also cleaned; the vault mirror should match upstream, not local dev state.
            expect(not (local_repo / "build").exists(), "gitignored build/ must be cleaned by git clean -fdx")

            # No managed mirror dir under Repos/_mirrors should be created.
            expect(
                not (root / "vault" / "Repos" / "_mirrors").exists()
                or not any((root / "vault" / "Repos" / "_mirrors").iterdir()),
                "legacy mirror dir must not be created by the new rail",
            )

            expect(result["repos_total"] == 1, str(result))
            expect(result["repos_failed"] == [], str(result))
            status = result["repo_statuses"][0]
            expect(status["mode"] == "in-place-pull", str(status))
            expect(status["syncs"][0]["branch"] == "main", str(status))
            expect(
                any(path.endswith("Projects/demo/README.md") for path in result["changed_paths"]),
                str(result),
            )
        finally:
            os.environ.clear()
            os.environ.update(old_env)

        print("PASS test_sync_vault_repo_mirrors_hard_resets_to_origin_overwriting_local_changes")


def test_sync_vault_repo_mirrors_honors_explicit_remote_override() -> None:
    """The preflight/explicit-source path can pass a remote_url that differs
    from the checkout's current origin. The sync primitive must honor that
    remote instead of trying to fetch a placeholder GitHub origin."""
    mod = load_module(CONTROL_PY, "almanac_control_remote_override_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = make_config(root)
        write_repos_vault(root)
        local_repo = root / "vault" / "Projects" / "demo-override"
        bare_remote, seed_repo = make_clone_with_remote(root, clone_path=local_repo)

        subprocess.run(
            ["git", "-C", str(local_repo), "remote", "set-url", "origin", "https://github.com/example/demo-override.git"],
            check=True,
            capture_output=True,
            text=True,
        )
        (seed_repo / "README.md").write_text("override remote update\n", encoding="utf-8")
        commit_all(seed_repo, "upstream override update")
        subprocess.run(["git", "-C", str(seed_repo), "push", "origin", "main"], check=True, capture_output=True, text=True)

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
                        "canonical_url": "https://github.com/example/demo-override",
                        "remote_url": str(bare_remote),
                        "source_paths": [],
                        "local_repo_paths": [str(local_repo)],
                    }
                ],
            )
            expect(result["repos_failed"] == [], str(result))
            expect((local_repo / "README.md").read_text(encoding="utf-8") == "override remote update\n", "expected explicit remote update")
            origin = subprocess.run(
                ["git", "-C", str(local_repo), "remote", "get-url", "origin"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            expect(origin == str(bare_remote), f"expected origin to be reset to explicit remote, got {origin!r}")
        finally:
            os.environ.clear()
            os.environ.update(old_env)

        print("PASS test_sync_vault_repo_mirrors_honors_explicit_remote_override")


def test_sync_vault_repo_mirrors_reports_failure_on_detached_head_and_keeps_going() -> None:
    """A detached HEAD or missing origin must not crash the rail; the faulty
    repo is recorded as a failure while other repos still sync cleanly."""
    mod = load_module(CONTROL_PY, "almanac_control_detached_head_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = make_config(root)
        write_repos_vault(root)

        good_repo = root / "vault" / "Projects" / "good"
        bad_repo = root / "vault" / "Projects" / "bad"
        good_bare, _ = make_clone_with_remote(root, clone_path=good_repo)

        # bad_repo: detached HEAD, no upstream branch to pull.
        init_git_repo(bad_repo)
        (bad_repo / "README.md").write_text("x\n", encoding="utf-8")
        commit_all(bad_repo, "one")
        commit_sha = subprocess.run(
            ["git", "-C", str(bad_repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        subprocess.run(
            ["git", "-C", str(bad_repo), "remote", "add", "origin", str(good_bare)],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(["git", "-C", str(bad_repo), "checkout", "--detach", commit_sha], check=True, capture_output=True, text=True)

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
                        "canonical_url": "https://github.com/example/good",
                        "remote_url": str(good_bare),
                        "source_paths": [],
                        "local_repo_paths": [str(good_repo)],
                    },
                    {
                        "canonical_url": "https://github.com/example/bad",
                        "remote_url": str(good_bare),
                        "source_paths": [],
                        "local_repo_paths": [str(bad_repo)],
                    },
                ],
            )
            expect(result["repos_total"] == 2, str(result))
            expect(len(result["repos_synced"]) == 1, str(result))
            expect(len(result["repos_failed"]) == 1, str(result))
            expect("no active branch" in result["repos_failed"][0], str(result))
            expect(
                any(status.get("errors") for status in result["repo_statuses"]),
                str(result),
            )
        finally:
            os.environ.clear()
            os.environ.update(old_env)

        print("PASS test_sync_vault_repo_mirrors_reports_failure_on_detached_head_and_keeps_going")


def main() -> int:
    test_discover_vault_repo_sources_ignores_markdown_url_mentions()
    test_discover_vault_repo_sources_finds_local_git_checkouts()
    test_discover_vault_repo_sources_skips_pinned_sync_trees_and_legacy_mirrors()
    test_sync_vault_repo_mirrors_hard_resets_to_origin_overwriting_local_changes()
    test_sync_vault_repo_mirrors_honors_explicit_remote_override()
    test_sync_vault_repo_mirrors_reports_failure_on_detached_head_and_keeps_going()
    print("PASS all 6 repo sync regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
