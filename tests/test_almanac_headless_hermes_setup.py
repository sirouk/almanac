#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "python" / "almanac_headless_hermes_setup.py"


def load_module(path: Path, name: str):
    python_dir = str(REPO / "python")
    if python_dir not in sys.path:
        sys.path.insert(0, python_dir)
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
    fake_root = root / "fakepkgs"
    package_dir = fake_root / "hermes_cli"
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "default_soul.py").write_text(
        "DEFAULT_SOUL_MD = (\n"
        "    'You are Hermes Agent, an intelligent AI assistant created by Nous Research. '\n"
        "    'Be direct and useful.'\n"
        ")\n",
        encoding="utf-8",
    )
    (package_dir / "config.py").write_text(
        "from __future__ import annotations\n"
        "import json, os\n"
        "from pathlib import Path\n"
        "\n"
        "_CONFIG_PATH = Path(os.environ['FAKE_HERMES_CONFIG_PATH'])\n"
        "_ENV_PATH = Path(os.environ.get('FAKE_HERMES_ENV_PATH', str(_CONFIG_PATH.with_suffix('.env.json'))))\n"
        "\n"
        "def load_config():\n"
        "    if _CONFIG_PATH.exists():\n"
        "        return json.loads(_CONFIG_PATH.read_text(encoding='utf-8'))\n"
        "    return {}\n"
        "\n"
        "def save_config(config):\n"
        "    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)\n"
        "    _CONFIG_PATH.write_text(json.dumps(config, indent=2, sort_keys=True) + '\\n', encoding='utf-8')\n"
        "\n"
        "def _load_env():\n"
        "    if _ENV_PATH.exists():\n"
        "        return json.loads(_ENV_PATH.read_text(encoding='utf-8'))\n"
        "    return {}\n"
        "\n"
        "def _save_env(payload):\n"
        "    _ENV_PATH.parent.mkdir(parents=True, exist_ok=True)\n"
        "    _ENV_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\\n', encoding='utf-8')\n"
        "\n"
        "def save_env_value(key, value):\n"
        "    payload = _load_env()\n"
        "    payload[str(key)] = str(value)\n"
        "    _save_env(payload)\n"
        "\n"
        "def _delete_env_value(key):\n"
        "    payload = _load_env()\n"
        "    payload.pop(str(key), None)\n"
        "    _save_env(payload)\n"
        "\n"
        "def save_anthropic_api_key(value):\n"
        "    save_env_value('ANTHROPIC_API_KEY', value)\n"
        "    _delete_env_value('ANTHROPIC_TOKEN')\n"
        "    _delete_env_value('CLAUDE_CODE_OAUTH_TOKEN')\n"
        "\n"
        "def save_anthropic_oauth_token(value):\n"
        "    save_env_value('ANTHROPIC_TOKEN', value)\n"
        "    _delete_env_value('ANTHROPIC_API_KEY')\n"
        "    _delete_env_value('CLAUDE_CODE_OAUTH_TOKEN')\n"
        "\n"
        "def use_anthropic_claude_code_credentials(save_fn=save_env_value):\n"
        "    _delete_env_value('ANTHROPIC_API_KEY')\n"
        "    _delete_env_value('ANTHROPIC_TOKEN')\n"
        "    _delete_env_value('CLAUDE_CODE_OAUTH_TOKEN')\n",
        encoding="utf-8",
    )
    agent_dir = fake_root / "agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "__init__.py").write_text("", encoding="utf-8")
    (agent_dir / "anthropic_adapter.py").write_text(
        "from __future__ import annotations\n"
        "import json, os\n"
        "from pathlib import Path\n"
        "\n"
        "def _write_claude_code_credentials(access_token, refresh_token, expires_at_ms, scopes=None):\n"
        "    path = Path(os.environ['FAKE_CLAUDE_CREDENTIALS_PATH'])\n"
        "    path.parent.mkdir(parents=True, exist_ok=True)\n"
        "    payload = {\n"
        "        'claudeAiOauth': {\n"
        "            'accessToken': str(access_token),\n"
        "            'refreshToken': str(refresh_token),\n"
        "            'expiresAt': int(expires_at_ms),\n"
        "            'scopes': list(scopes or []),\n"
        "        }\n"
        "    }\n"
        "    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\\n', encoding='utf-8')\n"
        "    path.chmod(0o600)\n",
        encoding="utf-8",
    )
    return fake_root


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
        home = root / "home"
        org_skill_root = home / "Almanac" / "Agents_Skills" / "ralphie" / "skills"
        org_skill = org_skill_root / "software-development" / "ralphie-orchestration" / "SKILL.md"
        org_skill.parent.mkdir(parents=True, exist_ok=True)
        org_skill.write_text(
            "---\nname: ralphie-orchestration\ndescription: Ralphie orchestration\n---\n# Ralphie\n",
            encoding="utf-8",
        )
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
                "HOME": str(home),
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
        expect("Hermes runtime base:" in soul_text, soul_text)
        expect("You are Hermes Agent, an intelligent AI assistant created by Nous Research. Be direct and useful." in soul_text, soul_text)
        expect("Almanac identity overlay:" in soul_text, soul_text)
        expect("You are Kor" in soul_text, soul_text)
        expect("Kora Reed" in soul_text, soul_text)
        expect("Acme Labs" in soul_text, soul_text)
        expect("Hermes deployment lane" in soul_text, soul_text)
        expect("America/New_York" in soul_text, soul_text)
        expect("22:00-08:00 weekdays" in soul_text, soul_text)
        expect("Curator brought you online through the Almanac" in soul_text, soul_text)
        expect("Notion is the shared source of truth when the operating context uses it" in soul_text, soul_text)
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
        expect("private/shared-vault questions as qmd-first work" in prefill_messages[0]["content"], prefill_messages)
        expect("not repo-wide searches to rediscover the rail" in prefill_messages[0]["content"], prefill_messages)
        expect("[managed:notion-ref]" in prefill_messages[0]["content"], prefill_messages)
        expect("[managed:notion-stub]" in prefill_messages[0]["content"], prefill_messages)
        expect("[managed:today-plate]" in prefill_messages[0]["content"], prefill_messages)
        expect("almanac-managed-context plugin can inject refreshed local Almanac context into future turns" in prefill_messages[0]["content"], prefill_messages)
        expect("the next session, /reset, or a gateway restart" not in prefill_messages[0]["content"], prefill_messages)
        expect("almanac-qmd-mcp for vault retrieval" not in prefill_messages[0]["content"], prefill_messages)

        hermes_cfg = json.loads(hermes_config.read_text(encoding="utf-8"))
        expect(hermes_cfg["prefill_messages_file"] == str(prefill_path), hermes_cfg)
        expect(hermes_cfg["agent"]["prefill_messages_file"] == str(prefill_path), hermes_cfg)
        expect(hermes_cfg["skills"]["external_dirs"] == [str(org_skill_root)], hermes_cfg)
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


def test_reasoning_effort_is_written_to_hermes_agent_config() -> None:
    module = load_module(SCRIPT, "almanac_headless_setup_reasoning_effort_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fake_pkg_root = write_fake_hermes_cli(root)
        hermes_config = root / "fake-hermes-config.json"
        hermes_config.write_text("{}\n", encoding="utf-8")

        old_env = os.environ.copy()
        old_path = list(sys.path)
        old_modules = {
            name: sys.modules.pop(name)
            for name in ["hermes_cli", "hermes_cli.config"]
            if name in sys.modules
        }
        os.environ["FAKE_HERMES_CONFIG_PATH"] = str(hermes_config)
        sys.path.insert(0, str(fake_pkg_root))
        try:
            module._write_reasoning_effort({"reasoning_effort": "xhigh"})
            cfg = json.loads(hermes_config.read_text(encoding="utf-8"))
            expect(cfg["agent"]["reasoning_effort"] == "xhigh", cfg)

            module._write_reasoning_effort({"reasoning_effort": "turbo"})
            cfg = json.loads(hermes_config.read_text(encoding="utf-8"))
            expect(cfg["agent"]["reasoning_effort"] == "xhigh", cfg)

            module._write_reasoning_effort({"reasoning_effort": "off"})
            cfg = json.loads(hermes_config.read_text(encoding="utf-8"))
            expect(cfg["agent"]["reasoning_effort"] == "none", cfg)
        finally:
            os.environ.clear()
            os.environ.update(old_env)
            sys.path[:] = old_path
            sys.modules.update(old_modules)
    print("PASS test_reasoning_effort_is_written_to_hermes_agent_config")


def test_anthropic_oauth_seed_writes_claude_code_credentials_and_clears_env_tokens() -> None:
    module = load_module(SCRIPT, "almanac_headless_setup_anthropic_claude_code_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fake_pkg_root = write_fake_hermes_cli(root)
        hermes_config = root / "fake-hermes-config.json"
        hermes_env = root / "fake-hermes-env.json"
        claude_credentials = root / "home" / ".claude" / ".credentials.json"
        secret_path = root / "anthropic-secret.json"
        hermes_config.write_text(
            json.dumps(
                {
                    "model": {
                        "provider": "anthropic",
                        "default": "claude-opus-legacy",
                        "base_url": "https://legacy.example.invalid",
                    }
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        hermes_env.write_text(
            json.dumps(
                {
                    "ANTHROPIC_API_KEY": "legacy-api-key",
                    "ANTHROPIC_TOKEN": "legacy-oauth-token",
                    "CLAUDE_CODE_OAUTH_TOKEN": "legacy-setup-token",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        secret_path.write_text(
            json.dumps(
                {
                    "kind": "claude_code_oauth",
                    "accessToken": "access-test-token",
                    "refreshToken": "refresh-test-token",
                    "expiresAt": 1_810_000_000_000,
                    "scopes": ["user:inference", "user:profile"],
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        old_env = os.environ.copy()
        old_path = list(sys.path)
        old_modules = {
            name: sys.modules.pop(name)
            for name in ["hermes_cli", "hermes_cli.config", "agent", "agent.anthropic_adapter"]
            if name in sys.modules
        }
        os.environ["FAKE_HERMES_CONFIG_PATH"] = str(hermes_config)
        os.environ["FAKE_HERMES_ENV_PATH"] = str(hermes_env)
        os.environ["FAKE_CLAUDE_CREDENTIALS_PATH"] = str(claude_credentials)
        sys.path.insert(0, str(fake_pkg_root))
        try:
            module._seed_anthropic({"model_id": "claude-opus-4-7"}, str(secret_path))

            credentials = json.loads(claude_credentials.read_text(encoding="utf-8"))
            oauth = credentials["claudeAiOauth"]
            expect(oauth["accessToken"] == "access-test-token", credentials)
            expect(oauth["refreshToken"] == "refresh-test-token", credentials)
            expect(oauth["expiresAt"] == 1_810_000_000_000, credentials)
            expect(oauth["scopes"] == ["user:inference", "user:profile"], credentials)
            expect(stat.S_IMODE(claude_credentials.stat().st_mode) == 0o600, oct(claude_credentials.stat().st_mode))

            env_payload = json.loads(hermes_env.read_text(encoding="utf-8"))
            expect("ANTHROPIC_API_KEY" not in env_payload, env_payload)
            expect("ANTHROPIC_TOKEN" not in env_payload, env_payload)
            expect("CLAUDE_CODE_OAUTH_TOKEN" not in env_payload, env_payload)

            cfg = json.loads(hermes_config.read_text(encoding="utf-8"))
            expect(cfg["model"]["provider"] == "anthropic", cfg)
            expect(cfg["model"]["default"] == "claude-opus-4-7", cfg)
            expect("base_url" not in cfg["model"], cfg)
        finally:
            os.environ.clear()
            os.environ.update(old_env)
            sys.path[:] = old_path
            for name in ["hermes_cli", "hermes_cli.config", "agent", "agent.anthropic_adapter"]:
                sys.modules.pop(name, None)
            sys.modules.update(old_modules)
    print("PASS test_anthropic_oauth_seed_writes_claude_code_credentials_and_clears_env_tokens")


def main() -> int:
    test_identity_only_writes_soul_and_dual_surface_prefill_config()
    test_render_soul_fails_loudly_on_unknown_placeholder()
    test_reasoning_effort_is_written_to_hermes_agent_config()
    test_anthropic_oauth_seed_writes_claude_code_credentials_and_clears_env_tokens()
    print("PASS all 4 headless Hermes setup tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
