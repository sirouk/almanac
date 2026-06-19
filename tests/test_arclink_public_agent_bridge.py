#!/usr/bin/env python3
"""Pin-compatibility checks for the public Agent gateway bridge.

The bridge replays raw platform updates through PRIVATE Hermes adapter
methods. A hermes-agent pin bump can rename or refactor those methods with no
failing ArcLink unit test, silently degrading every bridged turn to a
placeholder. These tests pin the coupling: when the local Hermes source
checkout is present, every private symbol the bridge calls must still exist
there, and the bridge's own replay dispatch must reference exactly those
symbols.
"""
from __future__ import annotations

import hashlib
import hmac
import importlib.util
import os
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
BRIDGE_PY = PYTHON_DIR / "arclink_public_agent_bridge.py"
BRIDGE_ROOT_PY = PYTHON_DIR / "arclink_public_agent_bridge_root.py"


def _load_module(path: Path, name: str):
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

# The symbols the bridge replays into, per integration point.
TELEGRAM_ADAPTER_HANDLERS = (
    "_handle_text_message",
    "_handle_command",
    "_handle_media_message",
    "_handle_location_message",
    "_handle_callback_query",
)
COMMANDS_MODULE_HELPERS = (
    "telegram_menu_commands",
    "_is_gateway_available",
    "_requires_argument",
    "_resolve_config_gates",
    "_sanitize_telegram_name",
)


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _hermes_source_root() -> Path | None:
    candidates = [
        os.environ.get("ARCLINK_HERMES_AGENT_SRC", ""),
        str(REPO / "arclink-priv" / "state" / "hermes-docs-src"),
        str(REPO / "arclink-priv" / "state" / "runtime" / "hermes-agent-src"),
    ]
    for candidate in candidates:
        path = Path(candidate) if candidate else None
        if path and (path / "gateway" / "platforms" / "telegram.py").is_file():
            return path
    return None


def test_bridge_replay_dispatch_uses_known_handler_names() -> None:
    body = BRIDGE_PY.read_text(encoding="utf-8")
    for handler in TELEGRAM_ADAPTER_HANDLERS:
        expect(handler in body, f"bridge no longer references {handler}; update this pin test too")
    # The replay must accept edited messages so caption/media edits re-enter
    # natively instead of degrading to a placeholder turn.
    expect('getattr(update, "edited_message", None)' in body, "bridge must replay edited_message updates")
    # Album merging: a telegram_update_json_list payload must replay each item
    # in one process so Hermes' media-group debounce can merge them.
    expect("telegram_update_json_list" in body, "bridge must support album update lists")
    # Discord sends must pin default-deny mentions.
    expect('"allowed_mentions"' in body, "bridge Discord sends must pin allowed_mentions default-deny")
    expect("discord_components" in body, "bridge Discord sends must preserve component metadata")
    expect("discord_embeds" in body, "bridge Discord sends must preserve embed metadata")
    expect("discord_attachments" in body, "bridge Discord sends must preserve attachment metadata")
    print("PASS test_bridge_replay_dispatch_uses_known_handler_names")


def test_pinned_hermes_source_still_exposes_bridge_coupling() -> None:
    root = _hermes_source_root()
    if root is None:
        print("SKIP test_pinned_hermes_source_still_exposes_bridge_coupling (no local hermes source)")
        return
    telegram_text = (root / "gateway" / "platforms" / "telegram.py").read_text(encoding="utf-8")
    for handler in TELEGRAM_ADAPTER_HANDLERS:
        expect(
            re.search(rf"def {re.escape(handler)}\(", telegram_text) is not None,
            f"pinned hermes source lost {handler}; the bridge replay (and per-update parse) must be re-aligned "
            "before bumping the hermes-agent pin",
        )
    commands_path = root / "hermes_cli" / "commands.py"
    expect(commands_path.is_file(), "pinned hermes source lost hermes_cli/commands.py")
    commands_text = commands_path.read_text(encoding="utf-8")
    for helper in COMMANDS_MODULE_HELPERS:
        expect(
            re.search(rf"def {re.escape(helper)}\(", commands_text) is not None,
            f"pinned hermes source lost hermes_cli.commands.{helper}; ArcLink menu derivation must be re-aligned "
            "before bumping the hermes-agent pin",
        )
    print("PASS test_pinned_hermes_source_still_exposes_bridge_coupling")


def test_getme_cache_secret_uses_only_dedicated_secret_and_disables_on_missing() -> None:
    # H2: the getMe L2 cache key must derive ONLY from the dedicated secret (never
    # the session pepper / operator-action / web-session secrets), so writer (root
    # wrapper) and reader pick the SAME key. With none present, L2 is disabled
    # (secret == b"") and we log exactly once.
    bridge = _load_module(BRIDGE_PY, "arclink_public_agent_bridge_h2_secret_test")
    old_env = os.environ.copy()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        secret_file = root / "getme-cache-secret"
        secret_file.write_text("dedicated-secret-value\n", encoding="utf-8")
        try:
            # ONLY the legacy fallbacks present -> must NOT be used anymore.
            os.environ.clear()
            os.environ.update(
                {
                    "ARCLINK_SESSION_HASH_PEPPER": "session-pepper-should-be-ignored",
                    "HERMES_HOME": str(root / "hermes-home"),
                    "ARCLINK_PRIV_DIR": str(root / "priv"),
                }
            )
            bridge._BRIDGE_GETME_CACHE_SECRET_MISSING_LOGGED = False
            logged: list[str] = []
            orig_write = bridge.sys.stderr.write
            bridge.sys.stderr.write = lambda msg: logged.append(msg)  # type: ignore[assignment]
            try:
                expect(
                    bridge._bridge_getme_cache_secret() == b"",
                    "legacy pepper/web-session secrets must NOT enable L2 anymore",
                )
                # A second call must NOT log again (log once).
                expect(bridge._bridge_getme_cache_secret() == b"", "still disabled")
            finally:
                bridge.sys.stderr.write = orig_write
            expect(len(logged) == 1, f"missing secret must log exactly once, got {len(logged)}: {logged}")

            # With ONLY the dedicated secret present -> stable, deterministic key.
            os.environ.clear()
            os.environ.update({"ARCLINK_BRIDGE_GETME_CACHE_SECRET_FILE": str(secret_file)})
            secret = bridge._bridge_getme_cache_secret()
            expect(secret == b"dedicated-secret-value", repr(secret))
            token = "123:abc"
            key1 = bridge._bridge_getme_cache_key(token)
            key2 = bridge._bridge_getme_cache_key(token)
            expected = hmac.new(b"dedicated-secret-value", token.encode("utf-8"), hashlib.sha256).hexdigest()
            expect(key1 == key2 == expected, f"key must be stable HMAC of dedicated secret: {key1} {key2} {expected}")
        finally:
            os.environ.clear()
            os.environ.update(old_env)
    print("PASS test_getme_cache_secret_uses_only_dedicated_secret_and_disables_on_missing")


def test_bridge_root_runtime_uid_gid_requires_resolution() -> None:
    # H3: the runtime uid/gid resolver must NEVER hardcode (1000,1000); it raises
    # when nothing resolves, and honours explicit ARCLINK_UID/GID.
    root_mod = _load_module(BRIDGE_ROOT_PY, "arclink_public_agent_bridge_root_h3_resolver_test")
    old_env = os.environ.copy()
    try:
        os.environ.clear()
        os.environ.update({"ARCLINK_UID": "4242", "ARCLINK_GID": "4343"})
        expect(root_mod._runtime_uid_gid() == (4242, 4343), "explicit ARCLINK_UID/GID must win")

        # Nothing resolvable -> raise (no guessed 1000,1000 fallback). Force the
        # account lookup and HERMES_HOME stat to fail.
        os.environ.clear()
        os.environ.update({"HERMES_HOME": "/nonexistent/hermes/home"})
        orig_getpwnam = root_mod.pwd.getpwnam
        root_mod.pwd.getpwnam = lambda name: (_ for _ in ()).throw(KeyError(name))
        try:
            raised = False
            try:
                root_mod._runtime_uid_gid()
            except RuntimeError:
                raised = True
            expect(raised, "unresolved uid/gid must raise, never return (1000,1000)")
        finally:
            root_mod.pwd.getpwnam = orig_getpwnam
    finally:
        os.environ.clear()
        os.environ.update(old_env)
    print("PASS test_bridge_root_runtime_uid_gid_requires_resolution")


def test_bridge_root_drop_closure_asserts_and_does_not_swallow_setgroups() -> None:
    # H3: the privilege-drop closure must (a) NOT swallow setgroups failure, and
    # (b) assert the uid/gid drop actually took effect, raising on mismatch.
    root_mod = _load_module(BRIDGE_ROOT_PY, "arclink_public_agent_bridge_root_h3_drop_test")
    uid, gid = 4242, 4343
    osmod = root_mod.os
    saved = {
        name: getattr(osmod, name)
        for name in ("setgroups", "setgid", "setuid", "getuid", "geteuid", "getgid", "getegid")
    }
    try:
        # (a) setgroups failure must propagate (fail closed), not be swallowed.
        osmod.setgroups = lambda groups: (_ for _ in ()).throw(OSError("setgroups denied"))
        osmod.setgid = lambda g: None
        osmod.setuid = lambda u: None
        osmod.getuid = lambda: uid
        osmod.geteuid = lambda: uid
        osmod.getgid = lambda: gid
        osmod.getegid = lambda: gid
        drop = root_mod._drop_to_runtime_user(uid, gid)
        raised = False
        try:
            drop()
        except OSError:
            raised = True
        expect(raised, "setgroups failure must propagate so the spawn fails closed")

        # (b) a silent no-op drop (ids did not change) must raise on the assert.
        osmod.setgroups = lambda groups: None
        osmod.getuid = lambda: 0  # drop did not stick
        osmod.geteuid = lambda: 0
        drop2 = root_mod._drop_to_runtime_user(uid, gid)
        raised2 = False
        try:
            drop2()
        except RuntimeError:
            raised2 = True
        expect(raised2, "a drop that did not change uid must raise the post-drop assert")

        # (c) a clean, effective drop passes.
        osmod.getuid = lambda: uid
        osmod.geteuid = lambda: uid
        drop3 = root_mod._drop_to_runtime_user(uid, gid)
        drop3()  # must not raise
    finally:
        for name, fn in saved.items():
            setattr(osmod, name, fn)
    print("PASS test_bridge_root_drop_closure_asserts_and_does_not_swallow_setgroups")


def main() -> int:
    test_bridge_replay_dispatch_uses_known_handler_names()
    test_pinned_hermes_source_still_exposes_bridge_coupling()
    test_getme_cache_secret_uses_only_dedicated_secret_and_disables_on_missing()
    test_bridge_root_runtime_uid_gid_requires_resolution()
    test_bridge_root_drop_closure_asserts_and_does_not_swallow_setgroups()
    print("PASS all 5 public agent bridge pin tests")
    return 0


if __name__ == "__main__":
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    raise SystemExit(main())
