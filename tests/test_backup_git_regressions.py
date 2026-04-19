#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COMMON_SH = REPO / "bin" / "common.sh"


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


def main() -> int:
    test_prepare_backup_git_transport_uses_deploy_key_and_known_hosts()
    print("PASS all 1 backup git regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
