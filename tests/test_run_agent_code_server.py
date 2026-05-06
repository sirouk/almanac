#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "bin" / "run-agent-code-server.sh"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def create_fake_runtime(fakebin: Path, runtime: str, log_path: Path, append: bool = False) -> None:
    redirect = ">>" if append else ">"
    (fakebin / runtime).write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$*\" {redirect}{shlex.quote(str(log_path))}\n"
        "exit 0\n",
        encoding="utf-8",
    )
    (fakebin / runtime).chmod(0o755)


def run_code_server_script(
    access_state: Path,
    workspace_home: Path,
    hermes_home: Path,
    fakebin: Path,
    **env: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), str(access_state), str(workspace_home), str(hermes_home)],
        env={**os.environ, "PATH": f"{fakebin}:{os.environ.get('PATH', '')}", **env},
        text=True,
        capture_output=True,
        check=False,
    )


def test_run_agent_code_server_seeds_dark_theme_without_overwriting_existing_theme() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fakebin = root / "fakebin"
        fakebin.mkdir(parents=True, exist_ok=True)
        podman_log = root / "podman.log"
        create_fake_runtime(fakebin, "podman", podman_log)

        hermes_home = root / "hermes-home"
        workspace_home = root / "workspace"
        vault_dir = root / "shared" / "vault"
        access_state = hermes_home / "state" / "arclink-web-access.json"
        access_state.parent.mkdir(parents=True, exist_ok=True)
        workspace_home.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            os.chown(workspace_home, 1000, 1000)
        vault_dir.mkdir(parents=True, exist_ok=True)
        (workspace_home / "Vault").symlink_to(vault_dir)
        workspace_file = hermes_home / "state" / "code-server" / "workspace" / "arclink.code-workspace"
        workspace_file.parent.mkdir(parents=True, exist_ok=True)
        workspace_file.write_text(
            json.dumps(
                {
                    "folders": [
                        {"name": "Workspace", "path": "/workspace"},
                        {"name": "ArcLink", "path": "/arclink-vault"},
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

        result = run_code_server_script(access_state, workspace_home, hermes_home, fakebin)
        expect(result.returncode == 0, f"run-agent-code-server failed: stdout={result.stdout!r} stderr={result.stderr!r}")

        settings_path = hermes_home / "state" / "code-server" / "data" / "User" / "settings.json"
        expect(settings_path.is_file(), f"expected settings.json to exist at {settings_path}")
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        expect(settings.get("workbench.colorTheme") == "Default Dark Modern", settings_path.read_text(encoding="utf-8"))
        expect(settings.get("workbench.secondarySideBar.defaultVisibility") == "hidden", settings_path.read_text(encoding="utf-8"))
        expect(settings.get("workbench.startupEditor") == "none", settings_path.read_text(encoding="utf-8"))
        arclink_alias = workspace_home / "ArcLink"
        expect(arclink_alias.is_symlink(), f"expected friendly ArcLink symlink at {arclink_alias}")
        expect(os.readlink(arclink_alias) == str(vault_dir), f"bad ArcLink alias target: {os.readlink(arclink_alias)!r}")
        expect(not workspace_file.exists(), f"expected stale duplicate workspace file to be removed: {workspace_file}")
        podman_args = podman_log.read_text(encoding="utf-8")
        expect(f"{workspace_home}:/workspace:rw" in podman_args, podman_args)
        expect(f"{vault_dir}:/arclink-vault:rw" in podman_args, podman_args)
        expect(f"{vault_dir}:{vault_dir}:rw" in podman_args, podman_args)
        expect("--user 0:0" not in podman_args, podman_args)
        expect("--userns=keep-id" in podman_args, podman_args)
        expect(f"--user {workspace_home.stat().st_uid}:{workspace_home.stat().st_gid}" in podman_args, podman_args)
        expect("/arclink-workspace" not in podman_args, podman_args)
        expect("/workspace\n" in podman_args or podman_args.rstrip().endswith(" /workspace"), podman_args)

        settings_path.write_text(
            json.dumps(
                {
                    "workbench.colorTheme": "Solarized Light",
                    "workbench.secondarySideBar.defaultVisibility": "visible",
                    "workbench.startupEditor": "welcomePage",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        result = run_code_server_script(access_state, workspace_home, hermes_home, fakebin)
        expect(result.returncode == 0, f"run-agent-code-server second run failed: stdout={result.stdout!r} stderr={result.stderr!r}")
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        expect(settings.get("workbench.colorTheme") == "Solarized Light", settings_path.read_text(encoding="utf-8"))
        expect(settings.get("workbench.secondarySideBar.defaultVisibility") == "visible", settings_path.read_text(encoding="utf-8"))
        expect(settings.get("workbench.startupEditor") == "welcomePage", settings_path.read_text(encoding="utf-8"))
        print("PASS test_run_agent_code_server_seeds_dark_theme_without_overwriting_existing_theme")


def test_run_agent_code_server_supports_docker_runtime_without_podman() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fakebin = root / "fakebin"
        fakebin.mkdir(parents=True, exist_ok=True)
        docker_log = root / "docker.log"
        create_fake_runtime(fakebin, "docker", docker_log, append=True)

        hermes_home = root / "hermes-home"
        workspace_home = root / "workspace"
        access_state = hermes_home / "state" / "arclink-web-access.json"
        access_state.parent.mkdir(parents=True, exist_ok=True)
        workspace_home.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            os.chown(workspace_home, 1000, 1000)
        access_state.write_text(
            json.dumps(
                {
                    "code_port": 39022,
                    "password": "pw",
                    "unix_user": "agent-docker",
                    "code_container_name": "arclink-agent-docker-code",
                }
            ),
            encoding="utf-8",
        )

        result = run_code_server_script(
            access_state,
            workspace_home,
            hermes_home,
            fakebin,
            ARCLINK_CONTAINER_RUNTIME="docker",
        )
        expect(result.returncode == 0, f"run-agent-code-server docker mode failed: stdout={result.stdout!r} stderr={result.stderr!r}")
        docker_args = docker_log.read_text(encoding="utf-8")
        expect("rm -f arclink-agent-docker-code" in docker_args, docker_args)
        expect("run --rm --name arclink-agent-docker-code --pull missing" in docker_args, docker_args)
        expect("--replace" not in docker_args, docker_args)
        expect("--userns=keep-id" not in docker_args, docker_args)
        expect(f"{workspace_home}:/workspace:rw" in docker_args, docker_args)
        print("PASS test_run_agent_code_server_supports_docker_runtime_without_podman")


def main() -> int:
    test_run_agent_code_server_seeds_dark_theme_without_overwriting_existing_theme()
    test_run_agent_code_server_supports_docker_runtime_without_podman()
    print("PASS all 2 run-agent-code-server regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
