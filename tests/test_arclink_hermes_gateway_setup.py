#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "bin" / "arclink-hermes-gateway-setup.sh"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_managed_setup_skips_hermes_native_service_prompts() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fakebin = root / "bin"
        fakebin.mkdir()
        hermes_bin = fakebin / "hermes"
        hermes_bin.write_text("#!/usr/bin/env bash\nexit 99\n", encoding="utf-8")
        hermes_bin.chmod(0o755)
        (fakebin / "python3").symlink_to(sys.executable)

        package = root / "hermes_cli"
        package.mkdir()
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "gateway.py").write_text(
            """
def print_info(message):
    print(f"INFO:{message}")


def prompt_yes_no(question, default=True):
    print(f"ORIGINAL_PROMPT:{question}")
    return True


def install_linux_gateway_from_setup(force=False):
    print("ORIGINAL_INSTALL")
    return "system", True


def gateway_setup():
    print("INSTALL_PROMPT=%s" % prompt_yes_no("  Install the gateway as a systemd service? (runs in background, starts on boot)", True))
    print("RESTART_PROMPT=%s" % prompt_yes_no("  Restart the gateway to pick up changes?", True))
    print("GROUP_PROMPT=%s" % prompt_yes_no("  Enable group messaging? (disabled by default for security)", False))
    scope, did_install = install_linux_gateway_from_setup(force=False)
    print(f"INSTALL_SCOPE={scope}")
    print(f"INSTALL_DID={did_install}")
""",
            encoding="utf-8",
        )

        result = subprocess.run(
            [str(SCRIPT), str(hermes_bin), str(root / "hermes-home")],
            env={
                **os.environ,
                "PYTHONPATH": str(root),
            },
            text=True,
            capture_output=True,
            check=False,
        )

        expect(result.returncode == 0, f"managed wrapper failed: stdout={result.stdout!r} stderr={result.stderr!r}")
        expect("INSTALL_PROMPT=False" in result.stdout, result.stdout)
        expect("RESTART_PROMPT=False" in result.stdout, result.stdout)
        expect("GROUP_PROMPT=True" in result.stdout, result.stdout)
        expect("INSTALL_SCOPE=None" in result.stdout, result.stdout)
        expect("INSTALL_DID=False" in result.stdout, result.stdout)
        expect("ORIGINAL_PROMPT:  Enable group messaging?" in result.stdout, result.stdout)
        expect("ORIGINAL_PROMPT:  Install the gateway" not in result.stdout, result.stdout)
        expect("ORIGINAL_PROMPT:  Restart the gateway" not in result.stdout, result.stdout)
        expect("ORIGINAL_INSTALL" not in result.stdout, result.stdout)
    print("PASS test_managed_setup_skips_hermes_native_service_prompts")


def main() -> int:
    test_managed_setup_skips_hermes_native_service_prompts()
    print("PASS all 1 arclink-hermes-gateway-setup regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
