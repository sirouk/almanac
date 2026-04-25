#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "bin" / "run-agent-code-server.sh"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_run_agent_code_server_seeds_dark_theme_without_overwriting_existing_theme() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fakebin = root / "fakebin"
        fakebin.mkdir(parents=True, exist_ok=True)
        podman_log = root / "podman.log"
        (fakebin / "podman").write_text(
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' \"$*\" >" + str(podman_log) + "\n"
            "exit 0\n",
            encoding="utf-8",
        )
        (fakebin / "podman").chmod(0o755)

        hermes_home = root / "hermes-home"
        workspace_home = root / "workspace"
        vault_dir = root / "shared" / "vault"
        access_state = hermes_home / "state" / "almanac-web-access.json"
        access_state.parent.mkdir(parents=True, exist_ok=True)
        workspace_home.mkdir(parents=True, exist_ok=True)
        vault_dir.mkdir(parents=True, exist_ok=True)
        (workspace_home / "Vault").symlink_to(vault_dir)
        workspace_file = hermes_home / "state" / "code-server" / "workspace" / "almanac.code-workspace"
        workspace_file.parent.mkdir(parents=True, exist_ok=True)
        workspace_file.write_text(
            json.dumps(
                {
                    "folders": [
                        {"name": "Workspace", "path": "/workspace"},
                        {"name": "Almanac", "path": "/almanac-vault"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        access_state.write_text(
            json.dumps(
                {
                    "code_port": 39021,
                    "password": "pw",
                    "unix_user": "agent-test",
                }
            ),
            encoding="utf-8",
        )

        result = subprocess.run(
            [str(SCRIPT), str(access_state), str(workspace_home), str(hermes_home)],
            env={**os.environ, "PATH": f"{fakebin}:{os.environ.get('PATH', '')}"},
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode == 0, f"run-agent-code-server failed: stdout={result.stdout!r} stderr={result.stderr!r}")

        settings_path = hermes_home / "state" / "code-server" / "data" / "User" / "settings.json"
        expect(settings_path.is_file(), f"expected settings.json to exist at {settings_path}")
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        expect(settings.get("workbench.colorTheme") == "Default Dark Modern", settings_path.read_text(encoding="utf-8"))
        almanac_alias = workspace_home / "Almanac"
        expect(almanac_alias.is_symlink(), f"expected friendly Almanac symlink at {almanac_alias}")
        expect(os.readlink(almanac_alias) == str(vault_dir), f"bad Almanac alias target: {os.readlink(almanac_alias)!r}")
        expect(not workspace_file.exists(), f"expected stale duplicate workspace file to be removed: {workspace_file}")
        podman_args = podman_log.read_text(encoding="utf-8")
        expect(f"{workspace_home}:/workspace:rw" in podman_args, podman_args)
        expect(f"{vault_dir}:/almanac-vault:rw" in podman_args, podman_args)
        expect(f"{vault_dir}:{vault_dir}:rw" in podman_args, podman_args)
        expect("/almanac-workspace" not in podman_args, podman_args)
        expect("/workspace\n" in podman_args or podman_args.rstrip().endswith(" /workspace"), podman_args)

        settings_path.write_text(
            json.dumps({"workbench.colorTheme": "Solarized Light"}, indent=2) + "\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [str(SCRIPT), str(access_state), str(workspace_home), str(hermes_home)],
            env={**os.environ, "PATH": f"{fakebin}:{os.environ.get('PATH', '')}"},
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode == 0, f"run-agent-code-server second run failed: stdout={result.stdout!r} stderr={result.stderr!r}")
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        expect(settings.get("workbench.colorTheme") == "Solarized Light", settings_path.read_text(encoding="utf-8"))
        print("PASS test_run_agent_code_server_seeds_dark_theme_without_overwriting_existing_theme")


def main() -> int:
    test_run_agent_code_server_seeds_dark_theme_without_overwriting_existing_theme()
    print("PASS all 1 run-agent-code-server regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
