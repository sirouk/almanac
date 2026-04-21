#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "python" / "almanac_headless_hermes_setup.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_fake_hermes_cli(root: Path) -> Path:
    package_dir = root / "fakepkgs" / "hermes_cli"
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "config.py").write_text(
        "from __future__ import annotations\n"
        "import json, os\n"
        "from pathlib import Path\n"
        "\n"
        "_CONFIG_PATH = Path(os.environ['FAKE_HERMES_CONFIG_PATH'])\n"
        "\n"
        "def load_config():\n"
        "    if _CONFIG_PATH.exists():\n"
        "        return json.loads(_CONFIG_PATH.read_text(encoding='utf-8'))\n"
        "    return {}\n"
        "\n"
        "def save_config(config):\n"
        "    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)\n"
        "    _CONFIG_PATH.write_text(json.dumps(config, indent=2, sort_keys=True) + '\\n', encoding='utf-8')\n",
        encoding="utf-8",
    )
    return package_dir.parent


def write_almanac_config(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "ALMANAC_ORG_NAME='Acme Labs'",
                "ALMANAC_ORG_MISSION='Make serious research more legible and actionable.'",
                "ALMANAC_ORG_PRIMARY_PROJECT='Hermes deployment lane'",
                "ALMANAC_ORG_TIMEZONE='America/New_York'",
                "ALMANAC_ORG_QUIET_HOURS='22:00-08:00 weekdays'",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_identity_only_writes_soul_and_dual_surface_prefill_config() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        hermes_home = root / "hermes-home"
        fake_pkg_root = write_fake_hermes_cli(root)
        almanac_config = root / "almanac-priv" / "config" / "almanac.env"
        hermes_config = root / "fake-hermes-config.json"
        hermes_config.write_text(
            json.dumps(
                {
                    "plugins": {"disabled": ["almanac-managed-context", "other-plugin"]}
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        write_almanac_config(almanac_config)

        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--identity-only", "--bot-name", "Kor", "--unix-user", "kor", "--user-name", "Kora Reed"],
            cwd=str(REPO),
            env={
                **os.environ,
                "HERMES_HOME": str(hermes_home),
                "ALMANAC_CONFIG_FILE": str(almanac_config),
                "FAKE_HERMES_CONFIG_PATH": str(hermes_config),
                "PYTHONPATH": f"{fake_pkg_root}{os.pathsep}{REPO / 'python'}",
            },
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode == 0, f"identity-only seed failed: stdout={result.stdout!r} stderr={result.stderr!r}")

        payload = json.loads(result.stdout)
        soul_path = Path(payload["soul_file"])
        prefill_path = Path(payload["prefill_messages_file"])
        identity_state_path = Path(payload["identity_state_file"])
        expect(payload["identity_only"] is True, payload)
        expect(soul_path == hermes_home / "SOUL.md", payload)
        expect(prefill_path == hermes_home / "state" / "almanac-prefill-messages.json", payload)
        expect(identity_state_path == hermes_home / "state" / "almanac-identity-context.json", payload)
        expect(soul_path.is_file(), f"expected SOUL.md at {soul_path}")
        expect(prefill_path.is_file(), f"expected prefill file at {prefill_path}")
        expect(identity_state_path.is_file(), f"expected identity state file at {identity_state_path}")

        soul_text = soul_path.read_text(encoding="utf-8")
        expect("You are Kor" in soul_text, soul_text)
        expect("Kora Reed" in soul_text, soul_text)
        expect("Acme Labs" in soul_text, soul_text)
        expect("Hermes deployment lane" in soul_text, soul_text)
        expect("America/New_York" in soul_text, soul_text)
        expect("22:00-08:00 weekdays" in soul_text, soul_text)
        expect("Curator brought you online through the Almanac" in soul_text, soul_text)
        expect("Notion is the organization's single source of truth" in soul_text, soul_text)
        expect("Check the current Almanac verification state" in soul_text, soul_text)
        expect("Hermes dashboard:" not in soul_text, soul_text)
        expect("Code workspace:" not in soul_text, soul_text)
        expect("$" not in soul_text, soul_text)

        identity_state = json.loads(identity_state_path.read_text(encoding="utf-8"))
        expect(identity_state["agent_label"] == "Kor", identity_state)
        expect(identity_state["user_name"] == "Kora Reed", identity_state)
        expect(identity_state["org_name"] == "Acme Labs", identity_state)
        expect(identity_state["org_mission"] == "Make serious research more legible and actionable.", identity_state)
        expect(identity_state["org_primary_project"] == "Hermes deployment lane", identity_state)
        expect(identity_state["org_timezone"] == "America/New_York", identity_state)
        expect(identity_state["org_quiet_hours"] == "22:00-08:00 weekdays", identity_state)

        prefill_messages = json.loads(prefill_path.read_text(encoding="utf-8"))
        expect(prefill_messages[0]["role"] == "system", prefill_messages)
        expect("[managed:resource-ref]" in prefill_messages[0]["content"], prefill_messages)
        expect("Your durable identity lives at HERMES_HOME/SOUL.md" in prefill_messages[0]["content"], prefill_messages)
        expect("preferred name, desk hours, or current focus" in prefill_messages[0]["content"], prefill_messages)
        expect("save them in your own local memory entries" in prefill_messages[0]["content"], prefill_messages)
        expect("a skill tells you the right workflow and guardrails" in prefill_messages[0]["content"], prefill_messages)
        expect("Do not decide that a capability is missing just because raw env vars are absent" in prefill_messages[0]["content"], prefill_messages)
        expect("[managed:notion-stub]" in prefill_messages[0]["content"], prefill_messages)
        expect("almanac-managed-context plugin can inject refreshed local Almanac context into future turns" in prefill_messages[0]["content"], prefill_messages)
        expect("the next session, /reset, or a gateway restart" not in prefill_messages[0]["content"], prefill_messages)
        expect("almanac-qmd-mcp for vault retrieval" not in prefill_messages[0]["content"], prefill_messages)

        hermes_cfg = json.loads(hermes_config.read_text(encoding="utf-8"))
        expect(hermes_cfg["prefill_messages_file"] == str(prefill_path), hermes_cfg)
        expect(hermes_cfg["agent"]["prefill_messages_file"] == str(prefill_path), hermes_cfg)
        expect("almanac-managed-context" not in hermes_cfg["plugins"]["disabled"], hermes_cfg)
        expect("other-plugin" in hermes_cfg["plugins"]["disabled"], hermes_cfg)
        print("PASS test_identity_only_writes_soul_and_dual_surface_prefill_config")


def test_render_soul_fails_loudly_on_unknown_placeholder() -> None:
    module = load_module(SCRIPT, "almanac_headless_setup_render_guard_test")
    original_template = module.SOUL_TEMPLATE_PATH
    with tempfile.TemporaryDirectory() as tmp:
        broken_template = Path(tmp) / "SOUL.md.tmpl"
        broken_template.write_text("You are $agent_label and $missing_value.\n", encoding="utf-8")
        module.SOUL_TEMPLATE_PATH = broken_template
        try:
            try:
                module._render_soul("Kor", "kor", "Kora Reed")
            except SystemExit as exc:
                expect("missing_value" in str(exc), str(exc))
            else:
                raise AssertionError("expected unknown SOUL placeholder to abort loudly")
        finally:
            module.SOUL_TEMPLATE_PATH = original_template
    print("PASS test_render_soul_fails_loudly_on_unknown_placeholder")


def main() -> int:
    test_identity_only_writes_soul_and_dual_surface_prefill_config()
    test_render_soul_fails_loudly_on_unknown_placeholder()
    print("PASS all 2 headless Hermes setup tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
