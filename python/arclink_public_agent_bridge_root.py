#!/usr/bin/env python3
"""Root-only preload wrapper for the public Agent gateway bridge.

The Hermes turn itself must run as the normal runtime user. This wrapper exists
only so L2 can keep a root-owned Telegram getMe cache outside Agent-writable
trees, then hand the non-secret bot profile to the unprivileged bridge child.
"""
from __future__ import annotations

import asyncio
import json
import os
import pwd
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

import arclink_public_agent_bridge as bridge


CHILD_SCRIPT = Path(__file__).with_name("arclink_public_agent_bridge.py")
DEFAULT_RUNTIME_USER = "arclink"


def _payload_from_raw(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return dict(data) if isinstance(data, Mapping) else {}


def _runtime_uid_gid() -> tuple[int, int]:
    uid_text = str(os.environ.get("ARCLINK_UID") or "").strip()
    gid_text = str(os.environ.get("ARCLINK_GID") or "").strip()
    if uid_text.isdigit() and gid_text.isdigit() and int(uid_text) > 0 and int(gid_text) > 0:
        return int(uid_text), int(gid_text)
    try:
        entry = pwd.getpwnam(DEFAULT_RUNTIME_USER)
        return int(entry.pw_uid), int(entry.pw_gid)
    except KeyError:
        pass
    hermes_home = str(os.environ.get("HERMES_HOME") or "").strip()
    if hermes_home:
        try:
            st = Path(hermes_home).stat()
            if int(st.st_uid) > 0 and int(st.st_gid) > 0:
                return int(st.st_uid), int(st.st_gid)
        except OSError:
            pass
    return 1000, 1000


def _drop_to_runtime_user(uid: int, gid: int):
    def _drop() -> None:
        try:
            os.setgroups([])
        except OSError:
            pass
        os.setgid(gid)
        os.setuid(uid)

    return _drop


async def _fetch_live_bot_user(bot_token: str, cache_path: Path) -> dict[str, Any]:
    bridge._add_runtime_paths()
    from telegram import Bot

    bot = Bot(token=bot_token)
    try:
        await bot.initialize()
        bridge._write_getme_cache(cache_path, bot)
        return bridge._bot_user_to_cache_dict(bot)
    finally:
        shutdown = getattr(bot, "shutdown", None)
        if callable(shutdown):
            try:
                await shutdown()
            except Exception:
                pass


def _preload_telegram_getme(payload: Mapping[str, Any]) -> dict[str, Any]:
    if str(payload.get("platform") or "").strip().lower() != "telegram":
        return {}
    if not bridge.BRIDGE_GETME_CACHE_ENABLED:
        return {}
    bot_token = str(payload.get("bot_token") or "").strip()
    if not bot_token:
        return {}
    try:
        cache_path = bridge._bridge_getme_cache_path(bot_token)
        if cache_path is None:
            return {}
        cached = bridge._read_getme_cache(cache_path)
        if cached:
            return cached
        return asyncio.run(_fetch_live_bot_user(bot_token, cache_path))
    except Exception:
        return {}


def _child_env(preloaded_user: Mapping[str, Any]) -> dict[str, str]:
    env = dict(os.environ)
    if preloaded_user:
        env[bridge.BRIDGE_GETME_PRELOADED_USER_ENV] = json.dumps(dict(preloaded_user), sort_keys=True)
    else:
        env.pop(bridge.BRIDGE_GETME_PRELOADED_USER_ENV, None)
    return env


def main() -> int:
    raw = sys.stdin.read()
    payload = _payload_from_raw(raw)
    preloaded_user = _preload_telegram_getme(payload)
    uid, gid = _runtime_uid_gid()
    preexec_fn = _drop_to_runtime_user(uid, gid) if os.geteuid() == 0 else None
    proc = subprocess.run(
        [sys.executable, str(CHILD_SCRIPT)],
        input=raw,
        check=False,
        text=True,
        capture_output=True,
        env=_child_env(preloaded_user),
        preexec_fn=preexec_fn,
    )
    sys.stdout.write(proc.stdout or "")
    sys.stderr.write(proc.stderr or "")
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
