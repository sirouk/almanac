#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
NEXTCLOUD_UP = REPO / "bin" / "nextcloud-up.sh"


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


def test_ensure_nextcloud_vault_mount_skips_duplicate_option_writes() -> None:
    text = NEXTCLOUD_UP.read_text()
    snippet = extract(text, "nextcloud_mount_state_from_json() {", "run_podman_nextcloud() {")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        log_path = tmp_path / "occ.log"
        mount_json = (
            '[{"mount_id":1,"mount_point":"\\/Vault","storage":"\\\\OC\\\\Files\\\\Storage\\\\Local",'
            '"authentication_type":"null::null","configuration":{"datadir":"\\/srv\\/vault"},'
            '"options":{"enable_sharing":true,"readonly":false},"applicable_users":[],"applicable_groups":[]}]'
        )
        script = f"""
{snippet}
LOG_PATH={log_path}
NEXTCLOUD_VAULT_MOUNT_POINT=/Vault
NEXTCLOUD_VAULT_CONTAINER_PATH=/srv/vault
nextcloud_occ() {{
  if [[ "$1" == "app:enable" ]]; then
    return 0
  fi
  if [[ "$1" == "files_external:list" ]]; then
    printf '%s\\n' '{mount_json}'
    return 0
  fi
  printf '%s\\n' "$*" >> "$LOG_PATH"
  return 0
}}
nextcloud_exec_www_data() {{
  return 0
}}
ensure_nextcloud_vault_mount
if [[ -f "$LOG_PATH" ]]; then
  cat "$LOG_PATH"
fi
"""
        result = bash(script)
        expect(result.returncode == 0, f"nextcloud mount idempotence case failed: {result.stderr}")
        expect(
            "files_external:option" not in result.stdout,
            f"expected no duplicate option writes when options already match, got: {result.stdout!r}",
        )
    print("PASS test_ensure_nextcloud_vault_mount_skips_duplicate_option_writes")


def main() -> int:
    test_ensure_nextcloud_vault_mount_skips_duplicate_option_writes()
    print("PASS all 1 nextcloud regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
