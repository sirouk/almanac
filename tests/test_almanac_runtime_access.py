#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
CONTROL_PY = PYTHON_DIR / "almanac_control.py"


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


def write_config(path: Path, values: dict[str, str]) -> None:
    lines = [f"{key}={json.dumps(value)}" for key, value in values.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_grant_agent_runtime_access_sets_repo_runtime_and_activation_acls() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    control = load_module(CONTROL_PY, "almanac_control_runtime_access_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        almanac_home = root / "home-almanac"
        repo_dir = almanac_home / "almanac"
        private_dir = repo_dir / "almanac-priv"
        state_dir = private_dir / "state"
        runtime_dir = state_dir / "runtime"
        config_path = private_dir / "config" / "almanac.env"

        (runtime_dir / "hermes-venv" / "bin").mkdir(parents=True, exist_ok=True)
        (runtime_dir / "hermes-agent-src").mkdir(parents=True, exist_ok=True)
        (repo_dir / "bin").mkdir(parents=True, exist_ok=True)
        (runtime_dir / "hermes-venv" / "bin" / "python3").write_text(
            "#!/usr/bin/env python3\n",
            encoding="utf-8",
        )

        write_config(
            config_path,
            {
                "ALMANAC_USER": "almanac",
                "ALMANAC_HOME": str(almanac_home),
                "ALMANAC_REPO_DIR": str(repo_dir),
                "ALMANAC_PRIV_DIR": str(private_dir),
                "STATE_DIR": str(state_dir),
                "RUNTIME_DIR": str(runtime_dir),
                "VAULT_DIR": str(private_dir / "vault"),
                "ALMANAC_DB_PATH": str(state_dir / "almanac-control.sqlite3"),
                "ALMANAC_AGENTS_STATE_DIR": str(state_dir / "agents"),
                "ALMANAC_CURATOR_DIR": str(state_dir / "curator"),
                "ALMANAC_CURATOR_MANIFEST": str(state_dir / "curator" / "manifest.json"),
                "ALMANAC_CURATOR_HERMES_HOME": str(state_dir / "curator" / "hermes-home"),
                "ALMANAC_ARCHIVED_AGENTS_DIR": str(state_dir / "archived-agents"),
                "ALMANAC_RELEASE_STATE_FILE": str(state_dir / "almanac-release.json"),
            },
        )

        old_env = os.environ.copy()
        commands: list[list[str]] = []
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        original_which = control.shutil.which
        original_run = control.subprocess.run
        try:
            control.shutil.which = lambda name: "/usr/bin/setfacl" if name == "setfacl" else original_which(name)

            def fake_run(cmd, check=False, **kwargs):  # type: ignore[no-untyped-def]
                commands.append([str(part) for part in cmd])

                class Result:
                    returncode = 0

                return Result()

            control.subprocess.run = fake_run
            cfg = control.Config.from_env()
            result = control.grant_agent_runtime_access(cfg, unix_user="alice", agent_id="agent-test")
        finally:
            control.shutil.which = original_which
            control.subprocess.run = original_run
            os.environ.clear()
            os.environ.update(old_env)

        activation_dir = control.activation_trigger_path(cfg, "agent-test").parent
        joined = "\n".join(" ".join(cmd) for cmd in commands)
        expect(result["unix_user"] == "alice", result)
        expect(result["agent_id"] == "agent-test", result)
        expect(str(repo_dir) in joined, f"expected repo ACL call, saw: {joined}")
        expect(str(runtime_dir / "hermes-venv") in joined, f"expected hermes runtime ACL call, saw: {joined}")
        expect(str(runtime_dir / "hermes-agent-src") in joined, f"expected hermes source ACL call, saw: {joined}")
        expect(str(activation_dir) in joined, f"expected activation dir ACL call, saw: {joined}")
        expect(
            any(cmd[:4] == ["/usr/bin/setfacl", "-m", "u:alice:--x", str(almanac_home)] for cmd in commands),
            f"expected traverse ACL for almanac home, saw: {joined}",
        )
        print("PASS test_grant_agent_runtime_access_sets_repo_runtime_and_activation_acls")


def main() -> int:
    test_grant_agent_runtime_access_sets_repo_runtime_and_activation_acls()
    print("PASS all 1 runtime access regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
