#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONFIGURE_SCRIPT = REPO / "bin" / "configure-agent-backup.sh"
BACKUP_SCRIPT = REPO / "bin" / "backup-agent-home.sh"


def run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env, text=True, capture_output=True, check=False)


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_public_api_fixture(root: Path, owner: str, repo: str, *, private: bool) -> str:
    api_root = root / "api" / "repos" / owner
    api_root.mkdir(parents=True, exist_ok=True)
    (api_root / repo).write_text(f'{{"private": {"true" if private else "false"}}}', encoding="utf-8")
    return f"file://{root / 'api'}"


def test_configure_agent_backup_refuses_public_github_repo() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        hermes_home = root / "hermes-home"
        (hermes_home / "state").mkdir(parents=True, exist_ok=True)
        api_base = write_public_api_fixture(root, "example", "public-repo", private=False)

        fakebin = root / "fakebin"
        fakebin.mkdir(parents=True, exist_ok=True)
        (fakebin / "ssh-keyscan").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        (fakebin / "ssh-keyscan").chmod(0o755)

        result = run(
            [
                str(CONFIGURE_SCRIPT),
                str(hermes_home),
                "--remote",
                "git@github.com:example/public-repo.git",
            ],
            env={
                **os.environ,
                "HOME": str(root),
                "PATH": f"{fakebin}:{os.environ.get('PATH', '')}",
                "AGENT_BACKUP_GITHUB_API_BASE": api_base,
                "ALMANAC_AGENT_BACKUP_ALLOW_TEST_GITHUB_API_BASE": "1",
            },
        )
        expect(result.returncode != 0, "expected public GitHub repo to be refused")
        expect("Refusing to back up a Hermes home to a public GitHub repository" in result.stderr, result.stderr)
        print("PASS test_configure_agent_backup_refuses_public_github_repo")


def test_configure_agent_backup_defaults_to_core_snapshot_without_sessions() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        hermes_home = root / "hermes-home"
        (hermes_home / "state").mkdir(parents=True, exist_ok=True)
        api_base = write_public_api_fixture(root, "example", "private-repo", private=True)
        fakebin = root / "fakebin"
        fakebin.mkdir(parents=True, exist_ok=True)
        (fakebin / "ssh-keyscan").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        (fakebin / "ssh-keyscan").chmod(0o755)

        result = run(
            [
                str(CONFIGURE_SCRIPT),
                str(hermes_home),
                "--remote",
                "git@github.com:example/private-repo.git",
            ],
            env={
                **os.environ,
                "HOME": str(root),
                "PATH": f"{fakebin}:{os.environ.get('PATH', '')}",
                "AGENT_BACKUP_GITHUB_API_BASE": api_base,
                "ALMANAC_AGENT_BACKUP_ALLOW_TEST_GITHUB_API_BASE": "1",
            },
        )
        expect(result.returncode == 0, f"expected private backup config to succeed: stdout={result.stdout!r} stderr={result.stderr!r}")
        state_body = (hermes_home / "state" / "almanac-agent-backup.env").read_text(encoding="utf-8")
        expect("AGENT_BACKUP_INCLUDE_SESSIONS=0" in state_body, state_body)
        expect("Session transcripts stay out of the backup unless" in result.stdout, result.stdout)
        expect("deploy key with write access" in result.stdout, result.stdout)
        expect("separate per-user backup key" in result.stdout, result.stdout)
        expect("do not reuse the Almanac upstream code-push key" in result.stdout, result.stdout)
        print("PASS test_configure_agent_backup_defaults_to_core_snapshot_without_sessions")


def test_configure_agent_backup_refuses_when_visibility_check_errors() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        hermes_home = root / "hermes-home"
        (hermes_home / "state").mkdir(parents=True, exist_ok=True)
        api_root = root / "api"
        api_root.mkdir(parents=True, exist_ok=True)
        fakebin = root / "fakebin"
        fakebin.mkdir(parents=True, exist_ok=True)
        (fakebin / "ssh-keyscan").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        (fakebin / "ssh-keyscan").chmod(0o755)

        result = run(
            [
                str(CONFIGURE_SCRIPT),
                str(hermes_home),
                "--remote",
                "git@github.com:example/private-repo.git",
            ],
            env={
                **os.environ,
                "HOME": str(root),
                "PATH": f"{fakebin}:{os.environ.get('PATH', '')}",
                "AGENT_BACKUP_GITHUB_API_BASE": "https://api.github.invalid",
                "ALMANAC_AGENT_BACKUP_ALLOW_TEST_GITHUB_API_BASE": "1",
            },
        )
        expect(result.returncode != 0, "expected visibility-check error to be refused")
        expect("Could not verify GitHub visibility" in result.stderr, result.stderr)
        print("PASS test_configure_agent_backup_refuses_when_visibility_check_errors")


def test_configure_agent_backup_refuses_untrusted_api_base_without_test_flag() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        hermes_home = root / "hermes-home"
        (hermes_home / "state").mkdir(parents=True, exist_ok=True)

        result = run(
            [
                str(CONFIGURE_SCRIPT),
                str(hermes_home),
                "--remote",
                "git@github.com:example/private-repo.git",
            ],
            env={
                **os.environ,
                "HOME": str(root),
                "AGENT_BACKUP_GITHUB_API_BASE": "https://api.github.invalid",
            },
        )
        expect(result.returncode != 0, "expected non-default GitHub API base to be refused")
        expect("Refusing non-default GitHub API base" in result.stderr, result.stderr)
        print("PASS test_configure_agent_backup_refuses_untrusted_api_base_without_test_flag")


def test_backup_agent_home_pushes_curated_snapshot_to_private_repo() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        hermes_home = root / "hermes-home"
        (hermes_home / "state").mkdir(parents=True, exist_ok=True)
        (hermes_home / "memories").mkdir(parents=True, exist_ok=True)
        (hermes_home / "sessions").mkdir(parents=True, exist_ok=True)
        (hermes_home / "logs").mkdir(parents=True, exist_ok=True)
        (hermes_home / "secrets").mkdir(parents=True, exist_ok=True)
        (hermes_home / "SOUL.md").write_text("soul\n", encoding="utf-8")
        (hermes_home / "config.yaml").write_text("model: test\n", encoding="utf-8")
        (hermes_home / "memories" / "MEMORY.md").write_text("memory\n", encoding="utf-8")
        (hermes_home / "sessions" / "session.json").write_text("session\n", encoding="utf-8")
        (hermes_home / "logs" / "agent.log").write_text("log\n", encoding="utf-8")
        (hermes_home / "secrets" / "token").write_text("secret\n", encoding="utf-8")
        (hermes_home / "state" / "almanac-identity-context.json").write_text("{}", encoding="utf-8")

        bare_remote = root / "remote.git"
        run(["git", "init", "--bare", str(bare_remote)])

        api_base = write_public_api_fixture(root, "example", "private-repo", private=True)
        git_global = root / "gitconfig"
        git_global.write_text(
            f'[url "{bare_remote.as_posix()}"]\n\tinsteadOf = git@github.com:example/private-repo.git\n',
            encoding="utf-8",
        )

        key_path = root / ".ssh" / "agent-backup"
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_text("private", encoding="utf-8")
        (root / ".ssh" / "agent-backup.pub").write_text("public", encoding="utf-8")
        known_hosts = root / ".ssh" / "known_hosts"
        known_hosts.write_text("github.com test\n", encoding="utf-8")

        state_file = hermes_home / "state" / "almanac-agent-backup.env"
        state_file.write_text(
            "\n".join(
                [
                    "AGENT_BACKUP_REMOTE='git@github.com:example/private-repo.git'",
                    "AGENT_BACKUP_BRANCH='main'",
                    "AGENT_BACKUP_INCLUDE_SESSIONS='1'",
                    f"AGENT_BACKUP_KEY_PATH='{key_path}'",
                    f"AGENT_BACKUP_KNOWN_HOSTS_FILE='{known_hosts}'",
                    f"AGENT_BACKUP_REPO_DIR='{root / 'local-backup'}'",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        fakebin = root / "fakebin"
        fakebin.mkdir(parents=True, exist_ok=True)
        (fakebin / "ssh-keyscan").write_text("#!/usr/bin/env bash\nprintf '%s\\n' 'github.com ssh-ed25519 AAAATEST'\n", encoding="utf-8")
        (fakebin / "ssh-keyscan").chmod(0o755)

        result = run(
            [str(BACKUP_SCRIPT), str(hermes_home)],
            env={
                **os.environ,
                "HOME": str(root),
                "PATH": f"{fakebin}:{os.environ.get('PATH', '')}",
                "AGENT_BACKUP_GITHUB_API_BASE": api_base,
                "ALMANAC_AGENT_BACKUP_ALLOW_TEST_GITHUB_API_BASE": "1",
                "GIT_CONFIG_GLOBAL": str(git_global),
            },
        )
        expect(result.returncode == 0, f"backup-agent-home failed: stdout={result.stdout!r} stderr={result.stderr!r}")

        checkout = root / "checkout"
        run(["git", "clone", "--branch", "main", str(bare_remote), str(checkout)])
        expect((checkout / "SOUL.md").read_text(encoding="utf-8") == "soul\n", "expected SOUL.md in backup")
        expect((checkout / "config.yaml").read_text(encoding="utf-8") == "model: test\n", "expected config.yaml in backup")
        expect((checkout / "memories" / "MEMORY.md").read_text(encoding="utf-8") == "memory\n", "expected memories in backup")
        expect((checkout / "sessions" / "session.json").read_text(encoding="utf-8") == "session\n", "expected sessions in backup")
        expect(not (checkout / "secrets").exists(), "did not expect secrets to be backed up")
        expect(not (checkout / "logs").exists(), "did not expect logs to be backed up")
        expect((checkout / "MANIFEST.json").is_file(), "expected MANIFEST.json in backup")
        print("PASS test_backup_agent_home_pushes_curated_snapshot_to_private_repo")


def main() -> int:
    test_configure_agent_backup_refuses_public_github_repo()
    test_configure_agent_backup_defaults_to_core_snapshot_without_sessions()
    test_configure_agent_backup_refuses_when_visibility_check_errors()
    test_configure_agent_backup_refuses_untrusted_api_base_without_test_flag()
    test_backup_agent_home_pushes_curated_snapshot_to_private_repo()
    print("PASS all 5 agent backup regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
