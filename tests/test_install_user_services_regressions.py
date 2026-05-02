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
        config_path = root / "arclink-priv" / "config" / "arclink.env"
        write_config(
            config_path,
            {
                "ARCLINK_USER": "arclink",
                "ARCLINK_HOME": str(root / "home-arclink"),
                "ARCLINK_REPO_DIR": str(REPO),
                "ARCLINK_PRIV_DIR": str(root / "arclink-priv"),
                "STATE_DIR": str(root / "arclink-priv" / "state"),
                "RUNTIME_DIR": str(root / "arclink-priv" / "state" / "runtime"),
                "VAULT_DIR": str(root / "arclink-priv" / "vault"),
                "ARCLINK_DB_PATH": str(root / "arclink-priv" / "state" / "arclink-control.sqlite3"),
                "ARCLINK_AGENTS_STATE_DIR": str(root / "arclink-priv" / "state" / "agents"),
                "ARCLINK_CURATOR_DIR": str(root / "arclink-priv" / "state" / "curator"),
                "ARCLINK_CURATOR_MANIFEST": str(root / "arclink-priv" / "state" / "curator" / "manifest.json"),
                "ARCLINK_CURATOR_HERMES_HOME": str(root / "arclink-priv" / "state" / "curator" / "hermes-home"),
                "ARCLINK_ARCHIVED_AGENTS_DIR": str(root / "arclink-priv" / "state" / "archived-agents"),
                "ARCLINK_RELEASE_STATE_FILE": str(root / "arclink-priv" / "state" / "arclink-release.json"),
                "PDF_INGEST_ENABLED": "1",
                "ENABLE_QUARTO": "1",
                "ENABLE_NEXTCLOUD": "0",
                "ARCLINK_CURATOR_CHANNELS": "tui-only,discord",
                "ARCLINK_CURATOR_DISCORD_ONBOARDING_ENABLED": "1",
                "ARCLINK_CURATOR_TELEGRAM_ONBOARDING_ENABLED": "0",
            },
        )

        result = subprocess.run(
            [str(SCRIPT)],
            env={
                **os.environ,
                "HOME": str(home),
                "PATH": f"{fakebin}:{os.environ.get('PATH', '')}",
                "ARCLINK_CONFIG_FILE": str(config_path),
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
        expect("--user enable arclink-curator-refresh.timer" in log, f"expected curator refresh enable, got: {log!r}")
        expect("arclink-curator-refresh.timer" in log and "--user restart" in log, f"expected curator refresh restart, got: {log!r}")
        expect("--user start arclink-curator-refresh.service" in log, f"expected curator refresh oneshot start, got: {log!r}")
        expect("--user enable arclink-memory-synth.timer" in log, f"expected memory synth timer enable, got: {log!r}")
        expect("arclink-memory-synth.timer" in log and "--user restart" in log, f"expected memory synth timer restart, got: {log!r}")
        expect("--user start arclink-memory-synth.service" in log, f"expected memory synth oneshot start, got: {log!r}")
        expect("arclink-mcp.service" in log and "--user restart" in log, f"expected ArcLink MCP restart, got: {log!r}")
        expect("arclink-notion-webhook.service" in log and "--user restart" in log, f"expected Notion webhook restart, got: {log!r}")
        expect("arclink-qmd-mcp.service" in log and "--user restart" in log, f"expected qmd MCP restart, got: {log!r}")
        expect("arclink-vault-watch.service" in log and "--user restart" in log, f"expected vault watch restart, got: {log!r}")
        expect("arclink-notification-delivery.timer" in log and "--user restart" in log, f"expected notification delivery timer restart, got: {log!r}")
        expect("--user enable arclink-health-watch.timer" in log, f"expected health watch timer enable, got: {log!r}")
        expect("arclink-health-watch.timer" in log and "--user restart" in log, f"expected health watch timer restart, got: {log!r}")
        expect("--user enable arclink-hermes-docs-sync.timer" in log, f"expected Hermes docs sync timer enable, got: {log!r}")
        expect("--user start arclink-hermes-docs-sync.service" in log, f"expected Hermes docs sync oneshot start, got: {log!r}")
        expect("--user restart arclink-curator-discord-onboarding.service" in log, f"expected Discord onboarding restart, got: {log!r}")
        print("PASS test_install_user_services_enables_and_starts_core_and_curator_units")


def main() -> int:
    test_install_user_services_enables_and_starts_core_and_curator_units()
    print("PASS all 1 install-user-services regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
