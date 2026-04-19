#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "bin" / "install-agent-user-services.sh"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_generated_activate_path_watches_trigger_file_and_parent_directory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fakebin = root / "fakebin"
        fakebin.mkdir(parents=True, exist_ok=True)
        (fakebin / "systemctl").write_text(
            "#!/usr/bin/env bash\n"
            "exit 0\n",
            encoding="utf-8",
        )
        (fakebin / "systemctl").chmod(0o755)

        hermes_bin = root / "hermes"
        hermes_bin.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        hermes_bin.chmod(0o755)

        home = root / "home"
        home.mkdir(parents=True, exist_ok=True)
        trigger_path = "/srv/almanac/state/activation-triggers/agent-test.json"

        result = subprocess.run(
            [
                str(SCRIPT),
                "agent-test",
                "/srv/almanac",
                "/home/test/.local/share/almanac-agent/hermes-home",
                '["tui-only"]',
                trigger_path,
                str(hermes_bin),
            ],
            env={
                **os.environ,
                "HOME": str(home),
                "PATH": f"{fakebin}:{os.environ.get('PATH', '')}",
            },
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode == 0, f"install-agent-user-services failed: stdout={result.stdout!r} stderr={result.stderr!r}")

        path_unit = home / ".config" / "systemd" / "user" / "almanac-user-agent-activate.path"
        expect(path_unit.is_file(), f"expected path unit to be generated: {path_unit}")
        content = path_unit.read_text(encoding="utf-8")
        lines = {line.strip() for line in content.splitlines() if line.strip()}
        expect(f"PathChanged={trigger_path}" in lines, content)
        expect(f"PathModified={trigger_path}" in lines, content)
        expect("PathChanged=/srv/almanac/state/activation-triggers" in lines, content)
        expect("PathModified=/srv/almanac/state/activation-triggers" in lines, content)
        print("PASS test_generated_activate_path_watches_trigger_file_and_parent_directory")


def main() -> int:
    test_generated_activate_path_watches_trigger_file_and_parent_directory()
    print("PASS all 1 agent-user-services regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
