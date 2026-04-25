#!/usr/bin/env python3
from __future__ import annotations

import os
import json
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


def test_generated_web_service_units_follow_access_state() -> None:
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
        hermes_home = home / ".local" / "share" / "almanac-agent" / "hermes-home"
        vault_dir = root / "shared" / "vault"
        state_dir = hermes_home / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        vault_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "almanac-web-access.json").write_text(
            json.dumps(
                {
                    "dashboard_backend_port": 19021,
                    "dashboard_proxy_port": 29021,
                    "code_port": 39021,
                    "code_container_name": "almanac-agent-code-agent-test",
                }
            ),
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                str(SCRIPT),
                "agent-test",
                str(REPO),
                str(hermes_home),
                '["discord"]',
                "",
                str(hermes_bin),
            ],
            env={
                **os.environ,
                "HOME": str(home),
                "PATH": f"{fakebin}:{os.environ.get('PATH', '')}",
                "ALMANAC_AGENT_VAULT_DIR": str(vault_dir),
            },
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode == 0, f"install-agent-user-services failed: stdout={result.stdout!r} stderr={result.stderr!r}")

        dashboard_unit = home / ".config" / "systemd" / "user" / "almanac-user-agent-dashboard.service"
        proxy_unit = home / ".config" / "systemd" / "user" / "almanac-user-agent-dashboard-proxy.service"
        code_unit = home / ".config" / "systemd" / "user" / "almanac-user-agent-code.service"
        gateway_unit = home / ".config" / "systemd" / "user" / "almanac-user-agent-gateway.service"
        local_wrapper = home / ".local" / "bin" / "almanac-agent-hermes"
        backup_wrapper = home / ".local" / "bin" / "almanac-agent-configure-backup"
        installed_plugin = hermes_home / "plugins" / "almanac-managed-context" / "__init__.py"
        installed_start_hook = hermes_home / "hooks" / "almanac-telegram-start" / "handler.py"
        home_almanac = home / "Almanac"
        hermes_vault = hermes_home / "Vault"
        hermes_almanac = hermes_home / "Almanac"
        expect(dashboard_unit.is_file(), f"expected dashboard unit: {dashboard_unit}")
        expect(proxy_unit.is_file(), f"expected dashboard proxy unit: {proxy_unit}")
        expect(code_unit.is_file(), f"expected code unit: {code_unit}")
        expect(gateway_unit.is_file(), f"expected gateway unit: {gateway_unit}")
        expect(local_wrapper.is_file(), f"expected local Hermes wrapper: {local_wrapper}")
        expect(backup_wrapper.is_file(), f"expected local backup wrapper: {backup_wrapper}")
        expect(installed_plugin.is_file(), f"expected Almanac plugin at first install: {installed_plugin}")
        expect(installed_start_hook.is_file(), f"expected Telegram /start hook at first install: {installed_start_hook}")
        for link_path in (home_almanac, hermes_vault, hermes_almanac):
            expect(link_path.is_symlink(), f"expected vault symlink: {link_path}")
            expect(os.readlink(link_path) == str(vault_dir), f"bad symlink target for {link_path}: {os.readlink(link_path)!r}")

        dashboard_text = dashboard_unit.read_text(encoding="utf-8")
        proxy_text = proxy_unit.read_text(encoding="utf-8")
        code_text = code_unit.read_text(encoding="utf-8")
        gateway_text = gateway_unit.read_text(encoding="utf-8")
        local_wrapper_text = local_wrapper.read_text(encoding="utf-8")
        backup_wrapper_text = backup_wrapper.read_text(encoding="utf-8")
        installed_plugin_text = installed_plugin.read_text(encoding="utf-8")
        installed_start_hook_text = installed_start_hook.read_text(encoding="utf-8")
        expect("--port 19021" in dashboard_text, dashboard_text)
        expect("--listen-port 29021" in proxy_text, proxy_text)
        expect("run-agent-code-server.sh" in code_text, code_text)
        expect("almanac-agent-code-agent-test" in code_text, code_text)
        expect("gateway run --replace" in gateway_text, gateway_text)
        expect("Environment=TELEGRAM_REACTIONS=true" in gateway_text, gateway_text)
        expect("Environment=DISCORD_REACTIONS=true" in gateway_text, gateway_text)
        install_text = SCRIPT.read_text(encoding="utf-8")
        expect('dirname "$HERMES_BIN")/../..' in install_text, install_text)
        expect('RUNTIME_DIR="$runtime_dir" "$mcps_script" "$HERMES_HOME"' in install_text, install_text)
        expect(f'HERMES_HOME="${{HERMES_HOME:-{hermes_home}}}"' in local_wrapper_text, local_wrapper_text)
        expect(str(hermes_bin) in local_wrapper_text, local_wrapper_text)
        expect("should_restart_gateway" in local_wrapper_text, local_wrapper_text)
        expect("setup|model|auth|login|logout|config|tools|mcp|plugins|skills" in local_wrapper_text, local_wrapper_text)
        expect("systemctl --user restart almanac-user-agent-gateway.service" in local_wrapper_text, local_wrapper_text)
        expect("Restarting Almanac messaging gateway so config changes apply" in local_wrapper_text, local_wrapper_text)
        expect("configure-agent-backup.sh" in backup_wrapper_text, backup_wrapper_text)
        expect("register_command(" in installed_plugin_text and '"start"' in installed_plugin_text, installed_plugin_text)
        expect('"command_name": "steer"' in installed_start_hook_text, installed_start_hook_text)
        print("PASS test_generated_web_service_units_follow_access_state")


def test_generated_backup_units_follow_backup_state_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fakebin = root / "fakebin"
        fakebin.mkdir(parents=True, exist_ok=True)
        systemctl_log = root / "systemctl.log"
        (fakebin / "systemctl").write_text(
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' \"$*\" >> \"$SYSTEMCTL_LOG\"\n"
            "exit 0\n",
            encoding="utf-8",
        )
        (fakebin / "systemctl").chmod(0o755)

        hermes_bin = root / "hermes"
        hermes_bin.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        hermes_bin.chmod(0o755)

        home = root / "home"
        hermes_home = home / ".local" / "share" / "almanac-agent" / "hermes-home"
        state_dir = hermes_home / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "almanac-agent-backup.env").write_text(
            "AGENT_BACKUP_REMOTE='git@github.com:example/private.git'\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                str(SCRIPT),
                "agent-test",
                str(REPO),
                str(hermes_home),
                '["tui-only"]',
                "",
                str(hermes_bin),
            ],
            env={
                **os.environ,
                "HOME": str(home),
                "PATH": f"{fakebin}:{os.environ.get('PATH', '')}",
                "SYSTEMCTL_LOG": str(systemctl_log),
            },
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode == 0, f"install-agent-user-services failed: stdout={result.stdout!r} stderr={result.stderr!r}")

        backup_service = home / ".config" / "systemd" / "user" / "almanac-user-agent-backup.service"
        backup_timer = home / ".config" / "systemd" / "user" / "almanac-user-agent-backup.timer"
        expect(backup_service.is_file(), f"expected backup service unit: {backup_service}")
        expect(backup_timer.is_file(), f"expected backup timer unit: {backup_timer}")
        backup_text = backup_service.read_text(encoding="utf-8")
        expect("backup-agent-home.sh" in backup_text, backup_text)
        expect(str(hermes_home) in backup_text, backup_text)

        log = systemctl_log.read_text(encoding="utf-8")
        expect("--user enable almanac-user-agent-backup.timer" in log, log)
        expect("--user restart almanac-user-agent-backup.timer" in log, log)
        expect(
            "--user start almanac-user-agent-backup.service" not in log,
            "install/upgrade should not force a backup before the deploy key has been installed",
        )
        print("PASS test_generated_backup_units_follow_backup_state_file")


def test_missing_native_hermes_gateway_units_do_not_abort_install() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fakebin = root / "fakebin"
        fakebin.mkdir(parents=True, exist_ok=True)
        systemctl_log = root / "systemctl.log"
        (fakebin / "systemctl").write_text(
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' \"$*\" >> \"$SYSTEMCTL_LOG\"\n"
            "if [[ \"$*\" == *\"list-unit-files hermes-gateway\"* ]]; then\n"
            "  exit 1\n"
            "fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        (fakebin / "systemctl").chmod(0o755)

        hermes_bin = root / "hermes"
        hermes_bin.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        hermes_bin.chmod(0o755)

        home = root / "home"
        hermes_home = home / ".local" / "share" / "almanac-agent" / "hermes-home"
        hermes_home.mkdir(parents=True, exist_ok=True)

        result = subprocess.run(
            [
                str(SCRIPT),
                "agent-test",
                str(REPO),
                str(hermes_home),
                '["tui-only","discord"]',
                "",
                str(hermes_bin),
            ],
            env={
                **os.environ,
                "HOME": str(home),
                "PATH": f"{fakebin}:{os.environ.get('PATH', '')}",
                "SYSTEMCTL_LOG": str(systemctl_log),
            },
            text=True,
            capture_output=True,
            check=False,
        )
        expect(
            result.returncode == 0,
            f"install-agent-user-services should tolerate no native Hermes gateway units: stdout={result.stdout!r} stderr={result.stderr!r}",
        )
        gateway_unit = home / ".config" / "systemd" / "user" / "almanac-user-agent-gateway.service"
        expect(gateway_unit.is_file(), f"expected Almanac gateway unit despite missing native units: {gateway_unit}")
        log = systemctl_log.read_text(encoding="utf-8")
        expect("enable almanac-user-agent-gateway.service" in log, log)
        print("PASS test_missing_native_hermes_gateway_units_do_not_abort_install")


def main() -> int:
    test_generated_activate_path_watches_trigger_file_and_parent_directory()
    test_generated_web_service_units_follow_access_state()
    test_generated_backup_units_follow_backup_state_file()
    test_missing_native_hermes_gateway_units_do_not_abort_install()
    print("PASS all 4 agent-user-services regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
