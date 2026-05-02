#!/usr/bin/env python3
from __future__ import annotations

import os
import json
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONFIGURE_SCRIPT = REPO / "bin" / "configure-agent-backup.sh"
BACKUP_SCRIPT = REPO / "bin" / "backup-agent-home.sh"
INSTALL_CRON_SCRIPT = REPO / "bin" / "install-agent-cron-jobs.sh"


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
                "ARCLINK_AGENT_BACKUP_ALLOW_TEST_GITHUB_API_BASE": "1",
            },
        )
        expect(result.returncode != 0, "expected public GitHub repo to be refused")
        expect("Refusing to back up a Hermes home to a public GitHub repository" in result.stderr, result.stderr)
        print("PASS test_configure_agent_backup_refuses_public_github_repo")


def test_configure_agent_backup_prepares_pending_snapshot_with_sessions() -> None:
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
                "ARCLINK_AGENT_BACKUP_ALLOW_TEST_GITHUB_API_BASE": "1",
            },
        )
        expect(result.returncode == 0, f"expected private backup config to succeed: stdout={result.stdout!r} stderr={result.stderr!r}")
        pending_body = (hermes_home / "state" / "arclink-agent-backup.pending.env").read_text(encoding="utf-8")
        expect(not (hermes_home / "state" / "arclink-agent-backup.env").exists(), "backup must stay inactive until write access verifies")
        expect("AGENT_BACKUP_INCLUDE_SESSIONS=1" in pending_body, pending_body)
        expect("Session transcripts are included by default" in result.stdout, result.stdout)
        expect("deploy key with write access" in result.stdout, result.stdout)
        expect("separate per-user backup key" in result.stdout, result.stdout)
        expect("do not reuse the ArcLink upstream code-push key" in result.stdout, result.stdout)
        print("PASS test_configure_agent_backup_prepares_pending_snapshot_with_sessions")


def test_configure_agent_backup_verify_activates_after_private_write_check() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        hermes_home = root / "hermes-home"
        (hermes_home / "state").mkdir(parents=True, exist_ok=True)
        api_base = write_public_api_fixture(root, "example", "private-repo", private=True)
        bare_remote = root / "remote.git"
        run(["git", "init", "--bare", str(bare_remote)])
        git_global = root / "gitconfig"
        git_global.write_text(
            f'[url "{bare_remote.as_posix()}"]\n\tinsteadOf = git@github.com:example/private-repo.git\n',
            encoding="utf-8",
        )
        fakebin = root / "fakebin"
        fakebin.mkdir(parents=True, exist_ok=True)
        (fakebin / "ssh-keyscan").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        (fakebin / "ssh-keyscan").chmod(0o755)

        common_env = {
            **os.environ,
            "HOME": str(root),
            "PATH": f"{fakebin}:{os.environ.get('PATH', '')}",
            "AGENT_BACKUP_GITHUB_API_BASE": api_base,
            "ARCLINK_AGENT_BACKUP_ALLOW_TEST_GITHUB_API_BASE": "1",
            "GIT_CONFIG_GLOBAL": str(git_global),
        }
        prepare = run(
            [
                str(CONFIGURE_SCRIPT),
                str(hermes_home),
                "--remote",
                "git@github.com:example/private-repo.git",
            ],
            env=common_env,
        )
        expect(prepare.returncode == 0, f"prepare failed: stdout={prepare.stdout!r} stderr={prepare.stderr!r}")
        stale_timer = root / ".config" / "systemd" / "user" / "arclink-user-agent-backup.timer"
        stale_timer.parent.mkdir(parents=True, exist_ok=True)
        stale_timer.write_text("[Timer]\nOnUnitActiveSec=4h\n", encoding="utf-8")
        verify = run([str(CONFIGURE_SCRIPT), str(hermes_home), "--verify"], env=common_env)
        expect(verify.returncode == 0, f"verify failed: stdout={verify.stdout!r} stderr={verify.stderr!r}")
        state_body = (hermes_home / "state" / "arclink-agent-backup.env").read_text(encoding="utf-8")
        expect("AGENT_BACKUP_REMOTE=git@github.com:example/private-repo.git" in state_body, state_body)
        expect(not (hermes_home / "state" / "arclink-agent-backup.pending.env").exists(), "pending state should clear after verify")
        expect(not stale_timer.exists(), "verify should remove the legacy systemd backup timer file")
        expect("Write check passed" in verify.stdout, verify.stdout)
        print("PASS test_configure_agent_backup_verify_activates_after_private_write_check")


def test_install_agent_cron_jobs_schedules_backup_and_records_status() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fake_repo = root / "repo"
        fake_bin = fake_repo / "bin"
        fake_bin.mkdir(parents=True, exist_ok=True)
        fake_backup = fake_bin / "backup-agent-home.sh"
        fake_backup.write_text(
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' 'fake backup ok'\n",
            encoding="utf-8",
        )
        fake_backup.chmod(0o755)

        hermes_home = root / "hermes-home"
        state_dir = hermes_home / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "arclink-agent-backup.env").write_text(
            "AGENT_BACKUP_REMOTE='git@github.com:example/private-repo.git'\n",
            encoding="utf-8",
        )

        install = run([str(INSTALL_CRON_SCRIPT), str(fake_repo), str(hermes_home)])
        expect(install.returncode == 0, f"cron install failed: stdout={install.stdout!r} stderr={install.stderr!r}")
        jobs_payload = json.loads((hermes_home / "cron" / "jobs.json").read_text(encoding="utf-8"))
        jobs = [job for job in jobs_payload.get("jobs", []) if job.get("managed_kind") == "agent-home-backup"]
        expect(len(jobs) == 1, json.dumps(jobs_payload, indent=2))
        job = jobs[0]
        expect(job["id"] == "a1bac0ffee42", str(job))
        expect(job["enabled"] is True, str(job))
        expect(job["script"] == "arclink_agent_backup.py", str(job))
        expect(job["deliver"] == "origin", str(job))
        expect(job["schedule"] == {"kind": "interval", "minutes": 240, "display": "every 240m"}, str(job))
        expect("script_timeout_seconds: 1800" in (hermes_home / "config.yaml").read_text(encoding="utf-8"), "expected cron script timeout")

        wrapper = hermes_home / "scripts" / "arclink_agent_backup.py"
        first_run = run(["python3", str(wrapper)], env={**os.environ, "HERMES_HOME": str(hermes_home)})
        expect(first_run.returncode == 0, f"cron wrapper failed: stdout={first_run.stdout!r} stderr={first_run.stderr!r}")
        gate = json.loads(first_run.stdout.strip().splitlines()[-1])
        expect(gate["wakeAgent"] is False, str(gate))
        expect(gate["status"] == "ok", str(gate))
        last_run = json.loads((hermes_home / "state" / "agent-home-backup" / "last-run.json").read_text(encoding="utf-8"))
        expect(last_run["ok"] is True and last_run["status"] == "ok", str(last_run))

        fake_backup.write_text(
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' 'fake backup failed' >&2\n"
            "exit 42\n",
            encoding="utf-8",
        )
        fake_backup.chmod(0o755)
        failed_run = run(["python3", str(wrapper)], env={**os.environ, "HERMES_HOME": str(hermes_home)})
        expect(failed_run.returncode == 1, f"cron wrapper should wake Hermes on failure: stdout={failed_run.stdout!r} stderr={failed_run.stderr!r}")
        failed_gate = json.loads(failed_run.stdout.strip().splitlines()[-1])
        expect(failed_gate["wakeAgent"] is True, str(failed_gate))
        expect(failed_gate["status"] == "error", str(failed_gate))
        failed_last_run = json.loads((hermes_home / "state" / "agent-home-backup" / "last-run.json").read_text(encoding="utf-8"))
        expect(failed_last_run["ok"] is False and failed_last_run["returncode"] == 42, str(failed_last_run))
        print("PASS test_install_agent_cron_jobs_schedules_backup_and_records_status")


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
                "ARCLINK_AGENT_BACKUP_ALLOW_TEST_GITHUB_API_BASE": "1",
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
        (hermes_home / "state" / "arclink-identity-context.json").write_text("{}", encoding="utf-8")

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

        state_file = hermes_home / "state" / "arclink-agent-backup.env"
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
                "ARCLINK_AGENT_BACKUP_ALLOW_TEST_GITHUB_API_BASE": "1",
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
    test_configure_agent_backup_prepares_pending_snapshot_with_sessions()
    test_configure_agent_backup_verify_activates_after_private_write_check()
    test_install_agent_cron_jobs_schedules_backup_and_records_status()
    test_configure_agent_backup_refuses_when_visibility_check_errors()
    test_configure_agent_backup_refuses_untrusted_api_base_without_test_flag()
    test_backup_agent_home_pushes_curated_snapshot_to_private_repo()
    print("PASS all 7 agent backup regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
