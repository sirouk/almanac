#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HEALTH_SH = REPO / "bin" / "health.sh"


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


def test_placeholder_secret_detection_and_reporting() -> None:
    text = HEALTH_SH.read_text()
    snippet = extract(text, "trim_secret_marker() {", "check_curator_gateway_runtime() {")
    script = f"""
PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0
STRICT_MODE=0
pass() {{ printf 'PASS:%s\\n' "$1"; }}
warn() {{ printf 'WARN:%s\\n' "$1"; }}
fail() {{ printf 'FAIL:%s\\n' "$1"; }}
warn_or_fail() {{ warn "$1"; }}
{snippet}
ENABLE_NEXTCLOUD=1
POSTGRES_PASSWORD=change-me
NEXTCLOUD_ADMIN_PASSWORD=real-secret
check_placeholder_secrets
"""
    result = bash(script)
    expect(result.returncode == 0, f"placeholder detection case failed: {result.stderr}")
    expect(
        "WARN:POSTGRES_PASSWORD still uses a placeholder secret" in result.stdout,
        f"expected placeholder Postgres warning, got: {result.stdout!r}",
    )
    expect(
        "PASS:NEXTCLOUD_ADMIN_PASSWORD is not a placeholder secret" in result.stdout,
        f"expected non-placeholder Nextcloud admin pass, got: {result.stdout!r}",
    )
    print("PASS test_placeholder_secret_detection_and_reporting")


def test_activation_trigger_write_probe_reports_writable_and_unwritable_states() -> None:
    text = HEALTH_SH.read_text()
    snippet = extract(text, "check_almanac_mcp_status() {", "check_vault_definition_health() {")
    script = f"""
PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0
STRICT_MODE=0
pass() {{ printf 'PASS:%s\\n' "$1"; }}
warn() {{ printf 'WARN:%s\\n' "$1"; }}
fail() {{ printf 'FAIL:%s\\n' "$1"; }}
warn_or_fail() {{ warn "$1"; }}
STATE_DIR="$(mktemp -d)"
mkdir -p "$STATE_DIR/activation-triggers"
{snippet}
check_activation_trigger_write_access
chmod 0555 "$STATE_DIR/activation-triggers"
check_activation_trigger_write_access
"""
    result = bash(script)
    expect(result.returncode == 0, f"activation-trigger probe case failed: {result.stderr}")
    expect(
        "PASS:activation trigger directory is writable:" in result.stdout,
        f"expected writable activation-trigger pass, got: {result.stdout!r}",
    )
    expect(
        "WARN:activation trigger directory is not writable:" in result.stdout,
        f"expected unwritable activation-trigger warning, got: {result.stdout!r}",
    )
    print("PASS test_activation_trigger_write_probe_reports_writable_and_unwritable_states")


def main() -> int:
    test_placeholder_secret_detection_and_reporting()
    test_activation_trigger_write_probe_reports_writable_and_unwritable_states()
    print("PASS all 2 health regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
