#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "bin" / "install-user-services.sh"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_config(path: Path, values: dict[str, str]) -> None:
    lines = [f"{key}={json.dumps(value)}" for key, value in values.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_install_user_services_enables_and_starts_core_and_curator_units() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fakebin = root / "fakebin"
        fakebin.mkdir(parents=True, exist_ok=True)
        log_path = root / "systemctl.log"
        (fakebin / "systemctl").write_text(
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' \"$*\" >> \"$SYSTEMCTL_LOG\"\n"
            "exit 0\n",
            encoding="utf-8",
        )
        (fakebin / "systemctl").chmod(0o755)

        home = root / "home"
        config_path = root / "almanac-priv" / "config" / "almanac.env"
        write_config(
            config_path,
            {
                "ALMANAC_USER": "almanac",
                "ALMANAC_HOME": str(root / "home-almanac"),
                "ALMANAC_REPO_DIR": str(REPO),
                "ALMANAC_PRIV_DIR": str(root / "almanac-priv"),
                "STATE_DIR": str(root / "almanac-priv" / "state"),
                "RUNTIME_DIR": str(root / "almanac-priv" / "state" / "runtime"),
                "VAULT_DIR": str(root / "almanac-priv" / "vault"),
                "ALMANAC_DB_PATH": str(root / "almanac-priv" / "state" / "almanac-control.sqlite3"),
                "ALMANAC_AGENTS_STATE_DIR": str(root / "almanac-priv" / "state" / "agents"),
                "ALMANAC_CURATOR_DIR": str(root / "almanac-priv" / "state" / "curator"),
                "ALMANAC_CURATOR_MANIFEST": str(root / "almanac-priv" / "state" / "curator" / "manifest.json"),
                "ALMANAC_CURATOR_HERMES_HOME": str(root / "almanac-priv" / "state" / "curator" / "hermes-home"),
                "ALMANAC_ARCHIVED_AGENTS_DIR": str(root / "almanac-priv" / "state" / "archived-agents"),
                "ALMANAC_RELEASE_STATE_FILE": str(root / "almanac-priv" / "state" / "almanac-release.json"),
                "PDF_INGEST_ENABLED": "1",
                "ENABLE_QUARTO": "1",
                "ENABLE_NEXTCLOUD": "0",
                "ALMANAC_CURATOR_CHANNELS": "tui-only,discord",
                "ALMANAC_CURATOR_DISCORD_ONBOARDING_ENABLED": "1",
                "ALMANAC_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "0",
            },
        )

        result = subprocess.run(
            [str(SCRIPT)],
            env={
                **os.environ,
                "HOME": str(home),
                "PATH": f"{fakebin}:{os.environ.get('PATH', '')}",
                "ALMANAC_CONFIG_FILE": str(config_path),
                "XDG_RUNTIME_DIR": str(root / "run-user"),
                "DBUS_SESSION_BUS_ADDRESS": f"unix:path={root / 'run-user' / 'bus'}",
                "SYSTEMCTL_LOG": str(log_path),
            },
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode == 0, f"install-user-services failed: stdout={result.stdout!r} stderr={result.stderr!r}")

        log = log_path.read_text(encoding="utf-8")
        expect("--user enable almanac-curator-refresh.timer" in log, f"expected curator refresh enable, got: {log!r}")
        expect("almanac-curator-refresh.timer" in log and "--user restart" in log, f"expected curator refresh restart, got: {log!r}")
        expect("--user start almanac-curator-refresh.service" in log, f"expected curator refresh oneshot start, got: {log!r}")
        expect("almanac-mcp.service" in log and "--user restart" in log, f"expected Almanac MCP restart, got: {log!r}")
        expect("almanac-notion-webhook.service" in log and "--user restart" in log, f"expected Notion webhook restart, got: {log!r}")
        expect("almanac-qmd-mcp.service" in log and "--user restart" in log, f"expected qmd MCP restart, got: {log!r}")
        expect("almanac-vault-watch.service" in log and "--user restart" in log, f"expected vault watch restart, got: {log!r}")
        expect("almanac-notification-delivery.timer" in log and "--user restart" in log, f"expected notification delivery timer restart, got: {log!r}")
        expect("--user enable almanac-health-watch.timer" in log, f"expected health watch timer enable, got: {log!r}")
        expect("almanac-health-watch.timer" in log and "--user restart" in log, f"expected health watch timer restart, got: {log!r}")
        expect("--user enable almanac-hermes-docs-sync.timer" in log, f"expected Hermes docs sync timer enable, got: {log!r}")
        expect("--user start almanac-hermes-docs-sync.service" in log, f"expected Hermes docs sync oneshot start, got: {log!r}")
        expect("--user restart almanac-curator-discord-onboarding.service" in log, f"expected Discord onboarding restart, got: {log!r}")
        print("PASS test_install_user_services_enables_and_starts_core_and_curator_units")


def main() -> int:
    test_install_user_services_enables_and_starts_core_and_curator_units()
    print("PASS all 1 install-user-services regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
