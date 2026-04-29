#!/usr/bin/env python3
from __future__ import annotations

import shlex
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COMMON_SH = REPO / "bin" / "common.sh"
BACKUP_SH = REPO / "bin" / "backup-to-github.sh"


def run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True, check=False)


def bash(script: str) -> subprocess.CompletedProcess[str]:
    return run(["bash", "-lc", script], cwd=REPO)


def extract(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_prepare_backup_git_transport_uses_deploy_key_and_known_hosts() -> None:
    text = COMMON_SH.read_text()
    snippet = extract(text, "backup_git_remote_uses_ssh() {", "run_compose() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        key_path = tmp_path / "backup-key"
        known_hosts_path = tmp_path / "known_hosts"
        key_path.write_text("private", encoding="utf-8")
        script = f"""
{snippet}
BACKUP_GIT_REMOTE=git@github.com:acme/almanac-priv.git
BACKUP_GIT_DEPLOY_KEY_PATH={key_path}
BACKUP_GIT_KNOWN_HOSTS_FILE={known_hosts_path}
ssh-keyscan() {{
  printf '%s\\n' 'github.com ssh-ed25519 AAAATESTKEY'
}}
prepare_backup_git_transport
printf 'GIT_SSH_COMMAND=%s\\n' "$GIT_SSH_COMMAND"
printf 'KNOWN_HOSTS=%s\\n' "$(cat "$BACKUP_GIT_KNOWN_HOSTS_FILE")"
"""
        result = bash(script)
        expect(result.returncode == 0, f"prepare_backup_git_transport case failed: {result.stderr}")
        expect(
            f'GIT_SSH_COMMAND=ssh -i "{key_path}" -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="{known_hosts_path}"'
            in result.stdout,
            f"expected deploy-key GIT_SSH_COMMAND, got: {result.stdout!r}",
        )
        expect(
            "KNOWN_HOSTS=github.com ssh-ed25519 AAAATESTKEY" in result.stdout,
            f"expected known_hosts entry, got: {result.stdout!r}",
        )
    print("PASS test_prepare_backup_git_transport_uses_deploy_key_and_known_hosts")


def test_shared_backup_refuses_public_github_remote() -> None:
    text = COMMON_SH.read_text()
    snippet = extract(text, "github_owner_repo_from_remote() {", "backup_git_remote_host() {")
    script = f"""
{snippet}
github_repo_visibility() {{
  printf '%s\\n' public
}}
BACKUP_GIT_REMOTE=git@github.com:acme/almanac-priv.git
if require_private_github_backup_remote "$BACKUP_GIT_REMOTE"; then
  echo should-have-failed
  exit 1
fi
"""
    result = bash(script)
    expect(result.returncode == 0, f"public shared backup refusal failed: stdout={result.stdout!r} stderr={result.stderr!r}")
    expect("Refusing to back up almanac-priv to a public GitHub repository" in result.stderr, result.stderr)
    print("PASS test_shared_backup_refuses_public_github_remote")


def test_backup_to_github_excludes_repo_local_key_material() -> None:
    common_text = COMMON_SH.read_text()
    backup_text = BACKUP_SH.read_text()
    common_snippet = extract(common_text, "path_is_within_dir() {", "run_compose() {")
    backup_snippet = extract(backup_text, "exclude_paths=()", '\nif ! git -C "$ALMANAC_PRIV_DIR" diff --cached --quiet --exit-code; then')
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        repo_path = tmp_path / "almanac-priv"
        (repo_path / "config" / "keys").mkdir(parents=True)
        (repo_path / "config" / "ssh").mkdir(parents=True)
        (repo_path / "vault").mkdir(parents=True)
        (repo_path / "vault" / "note.md").write_text("hello\n", encoding="utf-8")
        (repo_path / "config" / "keys" / "almanac-backup-ed25519").write_text("private\n", encoding="utf-8")
        (repo_path / "config" / "keys" / "almanac-backup-ed25519.pub").write_text("public\n", encoding="utf-8")
        (repo_path / "config" / "ssh" / "known_hosts").write_text("github.com key\n", encoding="utf-8")
        run(["git", "init", "-b", "main", str(repo_path)])
        script = f"""
{common_snippet}
ALMANAC_PRIV_DIR={repo_path}
BACKUP_GIT_DEPLOY_KEY_PATH={repo_path / 'config' / 'keys' / 'almanac-backup-ed25519'}
BACKUP_GIT_KNOWN_HOSTS_FILE={repo_path / 'config' / 'ssh' / 'known_hosts'}
{backup_snippet}
git -C "$ALMANAC_PRIV_DIR" diff --cached --name-only
"""
        result = bash(script)
        expect(result.returncode == 0, f"backup exclusion case failed: {result.stderr}")
        staged = {line.strip() for line in result.stdout.splitlines() if line.strip()}
        expect("vault/note.md" in staged, f"expected normal content to stage, got: {staged!r}")
        expect(
            "config/keys/almanac-backup-ed25519" not in staged
            and "config/keys/almanac-backup-ed25519.pub" not in staged
            and "config/ssh/known_hosts" not in staged,
            f"expected repo-local key material to be excluded, got: {staged!r}",
        )
    print("PASS test_backup_to_github_excludes_repo_local_key_material")


def test_backup_to_github_skips_nested_git_checkouts_without_submodule_dirt() -> None:
    common_text = COMMON_SH.read_text()
    backup_text = BACKUP_SH.read_text()
    common_snippet = extract(common_text, "path_is_within_dir() {", "run_compose() {")
    backup_snippet = extract(backup_text, "exclude_paths=()", '\nif ! git -C "$ALMANAC_PRIV_DIR" diff --cached --quiet --exit-code; then')
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        repo_path = tmp_path / "almanac-priv"
        nested = repo_path / "vault" / "Repos" / "team-docs"
        nested.mkdir(parents=True)
        run(["git", "init", "-b", "main", str(nested)])
        (nested / "README.md").write_text("nested repo content\n", encoding="utf-8")
        run(["git", "-C", str(nested), "add", "README.md"])
        run(
            [
                "git",
                "-C",
                str(nested),
                "-c",
                "user.name=Backup Bot",
                "-c",
                "user.email=backup@example.com",
                "commit",
                "-m",
                "nested seed",
            ]
        )
        (nested / "draft.md").write_text("local untracked work\n", encoding="utf-8")
        (repo_path / "vault" / "note.md").write_text("normal vault note\n", encoding="utf-8")
        run(["git", "init", "-b", "main", str(repo_path)])
        script = f"""
{common_snippet}
ALMANAC_PRIV_DIR={repo_path}
BACKUP_GIT_DEPLOY_KEY_PATH=
BACKUP_GIT_KNOWN_HOSTS_FILE=
{backup_snippet}
git -C "$ALMANAC_PRIV_DIR" diff --cached --name-only
"""
        result = bash(script)
        expect(result.returncode == 0, f"backup nested checkout case failed: stdout={result.stdout!r} stderr={result.stderr!r}")
        staged = {line.strip() for line in result.stdout.splitlines() if line.strip()}
        expect("vault/note.md" in staged, f"expected normal vault file to stage, got: {staged!r}")
        expect(
            not any(line == "vault/Repos/team-docs" or line.startswith("vault/Repos/team-docs/") for line in staged),
            f"nested git checkouts must not be staged as gitlinks or private backup content, got: {staged!r}",
        )
    print("PASS test_backup_to_github_skips_nested_git_checkouts_without_submodule_dirt")


def test_backup_to_github_skips_ignored_state_tree_with_nested_git_checkout() -> None:
    common_text = COMMON_SH.read_text()
    backup_text = BACKUP_SH.read_text()
    common_snippet = extract(common_text, "path_is_within_dir() {", "run_compose() {")
    backup_snippet = extract(backup_text, "exclude_paths=()", '\nif ! git -C "$ALMANAC_PRIV_DIR" diff --cached --quiet --exit-code; then')
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        repo_path = tmp_path / "almanac-priv"
        runtime_repo = repo_path / "state" / "runtime" / "hermes-agent-src"
        runtime_repo.mkdir(parents=True)
        run(["git", "init", "-b", "main", str(runtime_repo)])
        (runtime_repo / "README.md").write_text("runtime checkout\n", encoding="utf-8")
        (repo_path / ".gitignore").write_text("state/\n", encoding="utf-8")
        (repo_path / "vault").mkdir(parents=True)
        (repo_path / "vault" / "note.md").write_text("normal vault note\n", encoding="utf-8")
        run(["git", "init", "-b", "main", str(repo_path)])
        script = f"""
{common_snippet}
ALMANAC_PRIV_DIR={repo_path}
BACKUP_GIT_DEPLOY_KEY_PATH=
BACKUP_GIT_KNOWN_HOSTS_FILE=
{backup_snippet}
git -C "$ALMANAC_PRIV_DIR" diff --cached --name-only
"""
        result = bash(script)
        expect(result.returncode == 0, f"backup ignored state case failed: stdout={result.stdout!r} stderr={result.stderr!r}")
        staged = {line.strip() for line in result.stdout.splitlines() if line.strip()}
        expect(".gitignore" in staged, f"expected gitignore to stage, got: {staged!r}")
        expect("vault/note.md" in staged, f"expected normal vault file to stage, got: {staged!r}")
        expect(not any(line == "state" or line.startswith("state/") for line in staged), f"ignored state tree must not stage, got: {staged!r}")
    print("PASS test_backup_to_github_skips_ignored_state_tree_with_nested_git_checkout")


def test_reconcile_backup_remote_archives_unrelated_history_and_force_aligns_main() -> None:
    backup_text = BACKUP_SH.read_text()
    snippet = extract(backup_text, "reconcile_backup_git_remote_branch() {", '\nif [[ ! -d "$ALMANAC_PRIV_DIR/.git" ]]; then')
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        local_repo = tmp_path / "local"
        seed_repo = tmp_path / "seed"
        bare_remote = tmp_path / "remote.git"

        run(["git", "init", "-b", "main", str(local_repo)])
        (local_repo / "vault").mkdir(parents=True)
        (local_repo / "vault" / "note.md").write_text("local-state\n", encoding="utf-8")
        run(["git", "-C", str(local_repo), "add", "."])
        run(
            [
                "git",
                "-C",
                str(local_repo),
                "-c",
                "user.name=Backup Bot",
                "-c",
                "user.email=backup@example.com",
                "commit",
                "-m",
                "local root",
            ]
        )

        run(["git", "init", "-b", "main", str(seed_repo)])
        (seed_repo / "vault").mkdir(parents=True)
        (seed_repo / "vault" / "legacy.md").write_text("legacy-remote\n", encoding="utf-8")
        run(["git", "-C", str(seed_repo), "add", "."])
        run(
            [
                "git",
                "-C",
                str(seed_repo),
                "-c",
                "user.name=Backup Bot",
                "-c",
                "user.email=backup@example.com",
                "commit",
                "-m",
                "remote root",
            ]
        )

        run(["git", "init", "--bare", str(bare_remote)])
        run(["git", "-C", str(seed_repo), "remote", "add", "origin", str(bare_remote)])
        run(["git", "-C", str(seed_repo), "push", "origin", "main"])
        run(["git", "-C", str(local_repo), "remote", "add", "origin", str(bare_remote)])

        script = f"""
{snippet}
BACKUP_GIT_BRANCH=main
BACKUP_GIT_AUTHOR_NAME='Backup Bot'
BACKUP_GIT_AUTHOR_EMAIL='backup@example.com'
reconcile_backup_git_remote_branch {local_repo} "$BACKUP_GIT_BRANCH"
printf 'local=%s\\n' "$(git -C {shlex.quote(str(local_repo))} rev-parse main)"
printf 'remote=%s\\n' "$(git -C {shlex.quote(str(bare_remote))} rev-parse refs/heads/main)"
printf 'needs_push=%s\\n' "$BACKUP_RECONCILE_PUSH_REQUIRED"
printf 'archives=%s\\n' "$(git -C {shlex.quote(str(bare_remote))} for-each-ref --format='%(refname:short)' refs/heads/archive/)"
"""
        result = bash(script)
        expect(result.returncode == 0, f"backup unrelated-history reconcile failed: {result.stderr}")
        local_head = next(line.split("=", 1)[1] for line in result.stdout.splitlines() if line.startswith("local="))
        remote_head = next(line.split("=", 1)[1] for line in result.stdout.splitlines() if line.startswith("remote="))
        needs_push = next(line.split("=", 1)[1] for line in result.stdout.splitlines() if line.startswith("needs_push="))
        archives = [line.split("=", 1)[1] for line in result.stdout.splitlines() if line.startswith("archives=")]
        expect(local_head == remote_head, f"expected remote main to align to local head, got {result.stdout!r}")
        expect(needs_push == "0", f"expected unrelated-history reconcile to satisfy the push, got {result.stdout!r}")
        expect(any(item.startswith("archive/main-pre-align-") for item in archives), f"expected archive branch, got {result.stdout!r}")
    print("PASS test_reconcile_backup_remote_archives_unrelated_history_and_force_aligns_main")


def test_reconcile_backup_remote_fast_forwards_local_without_follow_up_push() -> None:
    backup_text = BACKUP_SH.read_text()
    snippet = extract(backup_text, "reconcile_backup_git_remote_branch() {", '\nif [[ ! -d "$ALMANAC_PRIV_DIR/.git" ]]; then')
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        local_repo = tmp_path / "local"
        seed_repo = tmp_path / "seed"
        bare_remote = tmp_path / "remote.git"

        run(["git", "init", "-b", "main", str(local_repo)])
        (local_repo / "vault").mkdir(parents=True)
        (local_repo / "vault" / "note.md").write_text("shared-root\n", encoding="utf-8")
        run(["git", "-C", str(local_repo), "add", "."])
        run(
            [
                "git",
                "-C",
                str(local_repo),
                "-c",
                "user.name=Backup Bot",
                "-c",
                "user.email=backup@example.com",
                "commit",
                "-m",
                "root",
            ]
        )

        run(["git", "init", "--bare", str(bare_remote)])
        run(["git", "-C", str(local_repo), "remote", "add", "origin", str(bare_remote)])
        run(["git", "-C", str(local_repo), "push", "origin", "main"])

        run(["git", "clone", "--branch", "main", str(bare_remote), str(seed_repo)])
        (seed_repo / "vault" / "remote.md").write_text("remote-ahead\n", encoding="utf-8")
        run(["git", "-C", str(seed_repo), "add", "."])
        run(
            [
                "git",
                "-C",
                str(seed_repo),
                "-c",
                "user.name=Backup Bot",
                "-c",
                "user.email=backup@example.com",
                "commit",
                "-m",
                "remote ahead",
            ]
        )
        run(["git", "-C", str(seed_repo), "push", "origin", "main"])

        script = f"""
{snippet}
BACKUP_GIT_BRANCH=main
reconcile_backup_git_remote_branch {local_repo} "$BACKUP_GIT_BRANCH"
printf 'local=%s\\n' "$(git -C {shlex.quote(str(local_repo))} rev-parse main)"
printf 'remote=%s\\n' "$(git -C {shlex.quote(str(bare_remote))} rev-parse --verify refs/heads/main)"
printf 'needs_push=%s\\n' "$BACKUP_RECONCILE_PUSH_REQUIRED"
"""
        result = bash(script)
        expect(result.returncode == 0, f"backup fast-forward reconcile failed: {result.stderr}")
        local_head = next(line.split("=", 1)[1] for line in result.stdout.splitlines() if line.startswith("local="))
        remote_head = next(line.split("=", 1)[1] for line in result.stdout.splitlines() if line.startswith("remote="))
        needs_push = next(line.split("=", 1)[1] for line in result.stdout.splitlines() if line.startswith("needs_push="))
        expect(local_head == remote_head, f"expected local main to fast-forward to remote head, got {result.stdout!r}")
        expect(needs_push == "0", f"expected fast-forward reconcile to skip a follow-up push, got {result.stdout!r}")
    print("PASS test_reconcile_backup_remote_fast_forwards_local_without_follow_up_push")


def main() -> int:
    test_prepare_backup_git_transport_uses_deploy_key_and_known_hosts()
    test_shared_backup_refuses_public_github_remote()
    test_backup_to_github_excludes_repo_local_key_material()
    test_backup_to_github_skips_nested_git_checkouts_without_submodule_dirt()
    test_backup_to_github_skips_ignored_state_tree_with_nested_git_checkout()
    test_reconcile_backup_remote_archives_unrelated_history_and_force_aligns_main()
    test_reconcile_backup_remote_fast_forwards_local_without_follow_up_push()
    print("PASS all 7 backup git regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
