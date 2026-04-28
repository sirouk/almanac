#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROTATE_SH = REPO / "bin" / "rotate-nextcloud-secrets.sh"


def run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True, check=False)


def bash(script: str) -> subprocess.CompletedProcess[str]:
    return run(["bash", "-lc", script], cwd=REPO)


def extract(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker)
    end = text.rindex(end_marker)
    return text[start:end]


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_rotate_nextcloud_runtime_secrets_orders_mutations_safely() -> None:
    text = ROTATE_SH.read_text()
    snippet = extract(text, "validate_rotation_secret() {", "\nrotate_nextcloud_runtime_secrets\n")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        log_path = tmp_path / "rotate.log"
        script = f"""
{snippet}
LOG_PATH={log_path}
ENABLE_NEXTCLOUD=1
POSTGRES_PASSWORD=oldpg
NEXTCLOUD_ADMIN_PASSWORD=oldadmin
POSTGRES_USER=nextcloud
NEXTCLOUD_ADMIN_USER=admin
NEXTCLOUD_ROTATE_POSTGRES_PASSWORD=newpg
NEXTCLOUD_ROTATE_ADMIN_PASSWORD=newadmin
require_real_layout() {{ return 0; }}
nextcloud_verify_runtime_ready() {{ printf 'verify\\n' >> "$LOG_PATH"; return 0; }}
nextcloud_reset_admin_password() {{ printf 'admin:%s:%s\\n' "$1" "$2" >> "$LOG_PATH"; return 0; }}
nextcloud_rotate_postgres_password() {{ printf 'db:%s:%s\\n' "$1" "$2" >> "$LOG_PATH"; return 0; }}
nextcloud_set_dbpassword_config() {{ printf 'config:%s\\n' "$1" >> "$LOG_PATH"; return 0; }}
rotate_nextcloud_runtime_secrets
cat "$LOG_PATH"
"""
        result = bash(script)
        expect(result.returncode == 0, f"nextcloud secret rotation order case failed: {result.stderr}")
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        expect(
            lines == ["verify", "admin:admin:newadmin", "db:oldpg:newpg", "config:newpg", "verify"],
            f"expected safe rotation order, got: {lines!r}",
        )
    print("PASS test_rotate_nextcloud_runtime_secrets_orders_mutations_safely")


def test_rotate_nextcloud_runtime_secrets_rolls_back_on_dbpassword_write_failure() -> None:
    text = ROTATE_SH.read_text()
    snippet = extract(text, "validate_rotation_secret() {", "\nrotate_nextcloud_runtime_secrets\n")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        log_path = tmp_path / "rollback.log"
        script = f"""
{snippet}
LOG_PATH={log_path}
ENABLE_NEXTCLOUD=1
POSTGRES_PASSWORD=oldpg
NEXTCLOUD_ADMIN_PASSWORD=oldadmin
POSTGRES_USER=nextcloud
NEXTCLOUD_ADMIN_USER=admin
NEXTCLOUD_ROTATE_POSTGRES_PASSWORD=newpg
NEXTCLOUD_ROTATE_ADMIN_PASSWORD=newadmin
require_real_layout() {{ return 0; }}
nextcloud_verify_runtime_ready() {{ return 0; }}
nextcloud_reset_admin_password() {{ printf 'admin:%s:%s\\n' "$1" "$2" >> "$LOG_PATH"; return 0; }}
nextcloud_rotate_postgres_password() {{ printf 'db:%s:%s\\n' "$1" "$2" >> "$LOG_PATH"; return 0; }}
nextcloud_set_dbpassword_config() {{ printf 'config-fail:%s\\n' "$1" >> "$LOG_PATH"; return 1; }}
rotate_nextcloud_runtime_secrets || true
cat "$LOG_PATH"
"""
        result = bash(script)
        expect(result.returncode == 0, f"nextcloud secret rotation rollback case failed: {result.stderr}")
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        expect(
            lines == [
                "admin:admin:newadmin",
                "db:oldpg:newpg",
                "config-fail:newpg",
                "db:newpg:oldpg",
                "admin:admin:oldadmin",
            ],
            f"expected rollback on dbpassword write failure, got: {lines!r}",
        )
    print("PASS test_rotate_nextcloud_runtime_secrets_rolls_back_on_dbpassword_write_failure")


def test_rotate_nextcloud_runtime_secrets_reads_new_passwords_from_files() -> None:
    text = ROTATE_SH.read_text()
    snippet = extract(text, "validate_rotation_secret() {", "\nrotate_nextcloud_runtime_secrets\n")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        log_path = tmp_path / "file-secrets.log"
        pg_file = tmp_path / "postgres-password"
        admin_file = tmp_path / "admin-password"
        pg_file.write_text("filepg\n", encoding="utf-8")
        admin_file.write_text("fileadmin\n", encoding="utf-8")
        script = f"""
{snippet}
LOG_PATH={log_path}
ENABLE_NEXTCLOUD=1
POSTGRES_PASSWORD=oldpg
NEXTCLOUD_ADMIN_PASSWORD=oldadmin
POSTGRES_USER=nextcloud
NEXTCLOUD_ADMIN_USER=admin
NEXTCLOUD_ROTATE_POSTGRES_PASSWORD_FILE={pg_file}
NEXTCLOUD_ROTATE_ADMIN_PASSWORD_FILE={admin_file}
require_real_layout() {{ return 0; }}
nextcloud_verify_runtime_ready() {{ return 0; }}
nextcloud_reset_admin_password() {{ printf 'admin:%s:%s\\n' "$1" "$2" >> "$LOG_PATH"; return 0; }}
nextcloud_rotate_postgres_password() {{ printf 'db:%s:%s\\n' "$1" "$2" >> "$LOG_PATH"; return 0; }}
nextcloud_set_dbpassword_config() {{ printf 'config:%s\\n' "$1" >> "$LOG_PATH"; return 0; }}
rotate_nextcloud_runtime_secrets
cat "$LOG_PATH"
"""
        result = bash(script)
        expect(result.returncode == 0, f"nextcloud file-secret case failed: {result.stderr}")
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        expect(
            lines == ["admin:admin:fileadmin", "db:oldpg:filepg", "config:filepg"],
            f"expected file-backed rotation secrets, got: {lines!r}",
        )
    print("PASS test_rotate_nextcloud_runtime_secrets_reads_new_passwords_from_files")


def main() -> int:
    test_rotate_nextcloud_runtime_secrets_orders_mutations_safely()
    test_rotate_nextcloud_runtime_secrets_rolls_back_on_dbpassword_write_failure()
    test_rotate_nextcloud_runtime_secrets_reads_new_passwords_from_files()
    print("PASS all 3 nextcloud secret rotation regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
