#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
CONTROL_PY = REPO / "python" / "almanac_control.py"


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


def test_activation_trigger_dir_repairs_owner_when_root_creates_or_touches_it() -> None:
    mod = load_module(CONTROL_PY, "almanac_control_activation_trigger_permissions_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "almanac.env"
        write_config(
            config_path,
            {
                "ALMANAC_USER": "almanac",
                "ALMANAC_HOME": str(root / "home-almanac"),
                "ALMANAC_REPO_DIR": str(root / "repo"),
                "ALMANAC_PRIV_DIR": str(root / "priv"),
                "STATE_DIR": str(root / "state"),
                "RUNTIME_DIR": str(root / "state" / "runtime"),
                "VAULT_DIR": str(root / "vault"),
                "ALMANAC_DB_PATH": str(root / "state" / "almanac-control.sqlite3"),
                "ALMANAC_AGENTS_STATE_DIR": str(root / "state" / "agents"),
                "ALMANAC_CURATOR_DIR": str(root / "state" / "curator"),
                "ALMANAC_CURATOR_MANIFEST": str(root / "state" / "curator" / "manifest.json"),
                "ALMANAC_CURATOR_HERMES_HOME": str(root / "state" / "curator" / "hermes-home"),
                "ALMANAC_ARCHIVED_AGENTS_DIR": str(root / "state" / "archived-agents"),
                "ALMANAC_RELEASE_STATE_FILE": str(root / "state" / "almanac-release.json"),
            },
        )

        old_env = os.environ.copy()
        os.environ["ALMANAC_CONFIG_FILE"] = str(config_path)
        original_geteuid = mod.os.geteuid
        original_getpwnam = mod.pwd.getpwnam
        original_chown = mod.os.chown
        chown_calls: list[tuple[str, int, int]] = []
        try:
            cfg = mod.Config.from_env()
            trigger_dir = cfg.state_dir / "activation-triggers"
            trigger_dir.mkdir(parents=True, exist_ok=True)

            mod.os.geteuid = lambda: 0
            mod.pwd.getpwnam = lambda name: SimpleNamespace(pw_uid=1005, pw_gid=1005)

            def fake_chown(path, uid, gid):
                chown_calls.append((str(path), int(uid), int(gid)))

            mod.os.chown = fake_chown
            path = mod.activation_trigger_dir(cfg)

            expect(path == trigger_dir, f"expected trigger dir path {trigger_dir}, got {path}")
            expect(trigger_dir.is_dir(), f"expected trigger dir to exist: {trigger_dir}")
            expect(
                chown_calls == [(str(trigger_dir), 1005, 1005)],
                f"expected activation trigger dir to be chowned to almanac when touched by root, got {chown_calls}",
            )
            print("PASS test_activation_trigger_dir_repairs_owner_when_root_creates_or_touches_it")
        finally:
            mod.os.geteuid = original_geteuid
            mod.pwd.getpwnam = original_getpwnam
            mod.os.chown = original_chown
            os.environ.clear()
            os.environ.update(old_env)


def main() -> int:
    test_activation_trigger_dir_repairs_owner_when_root_creates_or_touches_it()
    print("PASS all 1 activation-trigger permission regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
