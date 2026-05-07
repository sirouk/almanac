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
        trigger_path = "/srv/arclink/state/activation-triggers/agent-test.json"

        result = subprocess.run(
            [
                str(SCRIPT),
                "agent-test",
                "/srv/arclink",
                "/home/test/.local/share/arclink-agent/hermes-home",
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

        path_unit = home / ".config" / "systemd" / "user" / "arclink-user-agent-activate.path"
        expect(path_unit.is_file(), f"expected path unit to be generated: {path_unit}")
        content = path_unit.read_text(encoding="utf-8")
        lines = {line.strip() for line in content.splitlines() if line.strip()}
        expect(f"PathChanged={trigger_path}" in lines, content)
        expect(f"PathModified={trigger_path}" in lines, content)
        expect("PathChanged=/srv/arclink/state/activation-triggers" in lines, content)
        expect("PathModified=/srv/arclink/state/activation-triggers" in lines, content)
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

        runtime_dir = root / "runtime"
        hermes_bin = runtime_dir / "hermes-venv" / "bin" / "hermes"
        hermes_bin.parent.mkdir(parents=True, exist_ok=True)
        hermes_bin.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        hermes_bin.chmod(0o755)
        bundled_skill_dir = runtime_dir / "hermes-agent-src" / "skills" / "productivity" / "google-workspace"
        bundled_skill_dir.mkdir(parents=True, exist_ok=True)
        (bundled_skill_dir / "SKILL.md").write_text(
            "---\nname: google-workspace\ndescription: Google Workspace tools.\n---\n",
            encoding="utf-8",
        )
        sync_script = runtime_dir / "hermes-agent-src" / "tools" / "skills_sync.py"
        sync_script.parent.mkdir(parents=True, exist_ok=True)
        sync_script.write_text(
            "import os, shutil\n"
            "from pathlib import Path\n"
            "src = Path(os.environ['HERMES_BUNDLED_SKILLS']) / 'productivity' / 'google-workspace'\n"
            "dst = Path(os.environ['HERMES_HOME']) / 'skills' / 'productivity' / 'google-workspace'\n"
            "dst.parent.mkdir(parents=True, exist_ok=True)\n"
            "if dst.exists(): shutil.rmtree(dst)\n"
            "shutil.copytree(src, dst)\n",
            encoding="utf-8",
        )

        home = root / "home"
        hermes_home = home / ".local" / "share" / "arclink-agent" / "hermes-home"
        vault_dir = root / "shared" / "vault"
        state_dir = hermes_home / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        vault_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "arclink-web-access.json").write_text(
            json.dumps(
                {
                    "dashboard_backend_port": 19021,
                    "dashboard_proxy_port": 29021,
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
                "ARCLINK_AGENT_VAULT_DIR": str(vault_dir),
            },
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode == 0, f"install-agent-user-services failed: stdout={result.stdout!r} stderr={result.stderr!r}")

        dashboard_unit = home / ".config" / "systemd" / "user" / "arclink-user-agent-dashboard.service"
        proxy_unit = home / ".config" / "systemd" / "user" / "arclink-user-agent-dashboard-proxy.service"
        code_unit = home / ".config" / "systemd" / "user" / "arclink-user-agent-code.service"
        gateway_unit = home / ".config" / "systemd" / "user" / "arclink-user-agent-gateway.service"
        local_wrapper = home / ".local" / "bin" / "arclink-agent-hermes"
        backup_wrapper = home / ".local" / "bin" / "arclink-agent-configure-backup"
        installed_plugin = hermes_home / "plugins" / "arclink-managed-context" / "__init__.py"
        installed_start_hook = hermes_home / "hooks" / "arclink-telegram-start" / "handler.py"
        installed_bundled_skill = hermes_home / "skills" / "productivity" / "google-workspace" / "SKILL.md"
        home_arclink = home / "ArcLink"
        hermes_vault = hermes_home / "Vault"
        hermes_arclink = hermes_home / "ArcLink"
        expect(dashboard_unit.is_file(), f"expected dashboard unit: {dashboard_unit}")
        expect(proxy_unit.is_file(), f"expected dashboard proxy unit: {proxy_unit}")
        expect(not code_unit.exists(), f"legacy code-server unit should be removed: {code_unit}")
        expect(gateway_unit.is_file(), f"expected gateway unit: {gateway_unit}")
        expect(local_wrapper.is_file(), f"expected local Hermes wrapper: {local_wrapper}")
        expect(backup_wrapper.is_file(), f"expected local backup wrapper: {backup_wrapper}")
        expect(installed_plugin.is_file(), f"expected ArcLink plugin at first install: {installed_plugin}")
        expect(installed_start_hook.is_file(), f"expected Telegram /start hook at first install: {installed_start_hook}")
        expect(installed_bundled_skill.is_file(), f"expected bundled Hermes skill at first install: {installed_bundled_skill}")
        for link_path in (home_arclink, hermes_vault, hermes_arclink):
            expect(link_path.is_symlink(), f"expected vault symlink: {link_path}")
            expect(os.readlink(link_path) == str(vault_dir), f"bad symlink target for {link_path}: {os.readlink(link_path)!r}")

        dashboard_text = dashboard_unit.read_text(encoding="utf-8")
        proxy_text = proxy_unit.read_text(encoding="utf-8")
        gateway_text = gateway_unit.read_text(encoding="utf-8")
        local_wrapper_text = local_wrapper.read_text(encoding="utf-8")
        backup_wrapper_text = backup_wrapper.read_text(encoding="utf-8")
        installed_plugin_text = installed_plugin.read_text(encoding="utf-8")
        installed_start_hook_text = installed_start_hook.read_text(encoding="utf-8")
        expect("--port 19021" in dashboard_text, dashboard_text)
        expect("--listen-port 29021" in proxy_text, proxy_text)
        expect("arclink_basic_auth_proxy.py" in proxy_text and "--access-file" in proxy_text, proxy_text)
        expect("gateway run --replace" in gateway_text, gateway_text)
        expect("Environment=HERMES_CRON_SCRIPT_TIMEOUT=1800" in gateway_text, gateway_text)
        expect("Environment=TELEGRAM_REACTIONS=true" in gateway_text, gateway_text)
        expect("Environment=DISCORD_REACTIONS=true" in gateway_text, gateway_text)
        expect(f"Environment=HERMES_BUNDLED_SKILLS={(runtime_dir / 'hermes-agent-src' / 'skills').resolve()}" in gateway_text, gateway_text)
        install_text = SCRIPT.read_text(encoding="utf-8")
        expect("sync-hermes-bundled-skills.sh" in install_text, install_text)
        expect("migrate-hermes-config.sh" in install_text, install_text)
        expect('dirname "$HERMES_BIN")/../..' in install_text, install_text)
        expect('RUNTIME_DIR="$runtime_dir" "$mcps_script" "$HERMES_HOME"' in install_text, install_text)
        expect(f'HERMES_HOME="${{HERMES_HOME:-{hermes_home}}}"' in local_wrapper_text, local_wrapper_text)
        expect("HERMES_BUNDLED_SKILLS=" in local_wrapper_text, local_wrapper_text)
        expect(str(hermes_bin) in local_wrapper_text, local_wrapper_text)
        expect("should_restart_gateway" in local_wrapper_text, local_wrapper_text)
        expect("setup|model|auth|login|logout|config|tools|mcp|plugins|skills" in local_wrapper_text, local_wrapper_text)
        expect("systemctl --user restart arclink-user-agent-gateway.service" in local_wrapper_text, local_wrapper_text)
        expect("Restarting ArcLink messaging gateway so config changes apply" in local_wrapper_text, local_wrapper_text)
        expect("configure-agent-backup.sh" in backup_wrapper_text, backup_wrapper_text)
        expect("register_command(" in installed_plugin_text and '"start"' in installed_plugin_text, installed_plugin_text)
        expect('"command_name": "steer"' in installed_start_hook_text, installed_start_hook_text)
        print("PASS test_generated_web_service_units_follow_access_state")


def test_generated_backup_cron_job_follows_backup_state_file() -> None:
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
        hermes_home = home / ".local" / "share" / "arclink-agent" / "hermes-home"
        state_dir = hermes_home / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "arclink-agent-backup.env").write_text(
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

        backup_service = home / ".config" / "systemd" / "user" / "arclink-user-agent-backup.service"
        backup_timer = home / ".config" / "systemd" / "user" / "arclink-user-agent-backup.timer"
        backup_cron_script = hermes_home / "scripts" / "arclink_agent_backup.py"
        backup_jobs_file = hermes_home / "cron" / "jobs.json"
        config_file = hermes_home / "config.yaml"
        expect(backup_service.is_file(), f"expected backup service unit: {backup_service}")
        expect(not backup_timer.exists(), f"legacy backup timer should not be generated: {backup_timer}")
        expect(backup_cron_script.is_file(), f"expected Hermes cron backup script: {backup_cron_script}")
        expect(backup_jobs_file.is_file(), f"expected Hermes cron jobs file: {backup_jobs_file}")
        backup_text = backup_service.read_text(encoding="utf-8")
        expect("backup-agent-home.sh" in backup_text, backup_text)
        expect(str(hermes_home) in backup_text, backup_text)
        jobs_payload = json.loads(backup_jobs_file.read_text(encoding="utf-8"))
        backup_jobs = [job for job in jobs_payload.get("jobs", []) if job.get("managed_kind") == "agent-home-backup"]
        expect(len(backup_jobs) == 1, json.dumps(jobs_payload, indent=2))
        backup_job = backup_jobs[0]
        expect(backup_job["id"] == "a1bac0ffee42", str(backup_job))
        expect(backup_job["enabled"] is True, str(backup_job))
        expect(backup_job["script"] == "arclink_agent_backup.py", str(backup_job))
        expect(backup_job["schedule"] == {"kind": "interval", "minutes": 240, "display": "every 240m"}, str(backup_job))
        expect("script_timeout_seconds: 1800" in config_file.read_text(encoding="utf-8"), config_file.read_text(encoding="utf-8"))

        log = systemctl_log.read_text(encoding="utf-8")
        expect("--user disable --now arclink-user-agent-backup.timer" in log, log)
        expect("--user enable arclink-user-agent-backup.timer" not in log, log)
        expect("--user restart arclink-user-agent-backup.timer" not in log, log)
        expect(
            "--user start arclink-user-agent-backup.service" not in log,
            "install/upgrade should not force a backup before the deploy key has been installed",
        )
        print("PASS test_generated_backup_cron_job_follows_backup_state_file")


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
        hermes_home = home / ".local" / "share" / "arclink-agent" / "hermes-home"
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
        gateway_unit = home / ".config" / "systemd" / "user" / "arclink-user-agent-gateway.service"
        expect(gateway_unit.is_file(), f"expected ArcLink gateway unit despite missing native units: {gateway_unit}")
        log = systemctl_log.read_text(encoding="utf-8")
        expect("enable arclink-user-agent-gateway.service" in log, log)
        print("PASS test_missing_native_hermes_gateway_units_do_not_abort_install")


def main() -> int:
    test_generated_activate_path_watches_trigger_file_and_parent_directory()
    test_generated_web_service_units_follow_access_state()
    test_generated_backup_cron_job_follows_backup_state_file()
    test_missing_native_hermes_gateway_units_do_not_abort_install()
    print("PASS all 4 agent-user-services regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
