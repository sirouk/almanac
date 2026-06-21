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

import asyncio
import hashlib
import hmac
import importlib.util
import json
import os
import re
import sys
import tempfile
import types
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


class _RecordingRest:
    """Minimal in-memory stand-in for ``_DiscordRest`` request capture."""

    def __init__(self, *, getme: dict | None = None) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []
        self._getme = getme or {"id": "999000111222333444", "username": "arclink-bot"}
        self._post_seq = 0

    async def request(self, method: str, path: str, *, payload=None):
        self.calls.append((method, path, payload))
        if method == "GET" and path == "/users/@me":
            return dict(self._getme)
        if method == "POST" and path.endswith("/messages"):
            self._post_seq += 1
            return {"id": f"new-{self._post_seq}"}
        return {}


def test_bridge_internal_deadline_fires_structured_error() -> None:
    # C-4: a wedged turn must hit the bridge's OWN internal deadline and surface
    # a structured error (not hang forever / not pin the agent).
    bridge = _load_module(BRIDGE_PY, "arclink_public_agent_bridge_c4_deadline_test")
    old_env = os.environ.copy()
    try:
        os.environ["ARCLINK_PUBLIC_AGENT_BRIDGE_DEADLINE_SECONDS"] = "1"

        async def _never_returns(_payload):
            await asyncio.sleep(3600)
            return {}

        bridge._dispatch_platform = _never_returns  # type: ignore[assignment]

        raised = False
        try:
            asyncio.run(bridge._run({"platform": "telegram"}))
        except bridge._BridgeDeadlineExceeded as exc:
            raised = True
            expect(
                str(exc) == bridge.BRIDGE_DEADLINE_EXCEEDED_MESSAGE,
                f"deadline error must carry the structured message: {exc!r}",
            )
        expect(raised, "a hung turn must raise _BridgeDeadlineExceeded, not hang")

        # main() must translate that into a non-zero exit + the structured JSON,
        # reading the payload from stdin.
        old_stdin, old_stdout = sys.stdin, sys.stdout
        import io

        sys.stdin = io.StringIO(json.dumps({"platform": "telegram"}))
        sys.stdout = captured = io.StringIO()
        try:
            rc = bridge.main()
        finally:
            sys.stdin, sys.stdout = old_stdin, old_stdout
        expect(rc == 1, f"deadline must exit non-zero, got {rc}")
        out = json.loads(captured.getvalue().strip())
        expect(out.get("ok") is False, f"structured failure must report ok=false: {out}")
        expect(
            out.get("error") == bridge.BRIDGE_DEADLINE_EXCEEDED_MESSAGE,
            f"structured error must be the deadline message: {out}",
        )
    finally:
        os.environ.clear()
        os.environ.update(old_env)
    print("PASS test_bridge_internal_deadline_fires_structured_error")


def test_interim_streaming_edit_failure_is_nonfatal_final_still_fatal() -> None:
    # H-3: an INTERIM streaming edit (finalize=False) that raises (429/400) must
    # NOT fail the turn -- it is swallowed + a non-raising failed result returned
    # so streaming continues. A FINAL edit (finalize=True) and ``send`` failures
    # remain FATAL (re-raise) so a genuinely-failed final delivery fails the turn.
    bridge = _load_module(BRIDGE_PY, "arclink_public_agent_bridge_h3_interim_test")
    evidence = bridge._DeliveryEvidence()

    state = {"raise_until_call": 0, "calls": 0}

    class _Adapter:
        async def edit_message(self, chat_id, message_id, content, *, finalize=False, **_kw):
            state["calls"] += 1
            if state["calls"] <= state["raise_until_call"]:
                raise RuntimeError("discord http 429: rate limited")
            return bridge.SimpleNamespace(success=True, message_id=message_id, error="", raw_response=None)

        async def send(self, chat_id, content, *args, **_kw):
            raise RuntimeError("discord http 500: send failed")

    adapter = _Adapter()
    bridge._install_delivery_evidence(adapter, evidence)

    # (a) interim edit raises -> swallowed, returns non-raising failed result.
    state["raise_until_call"] = 1
    result = asyncio.run(adapter.edit_message("c", "m", "interim", finalize=False))
    expect(result is not None and result.success is False, "interim edit failure must be swallowed (non-raising failed result)")

    # (b) FINAL edit raises -> must propagate (turn fails).
    state["raise_until_call"] = 99
    raised_final = False
    try:
        asyncio.run(adapter.edit_message("c", "m", "final", finalize=True))
    except RuntimeError:
        raised_final = True
    expect(raised_final, "a FINAL (finalize=True) edit failure must re-raise and fail the turn")

    # (c) send raises -> must propagate (a real send is the final delivery).
    raised_send = False
    try:
        asyncio.run(adapter.send("c", "hi"))
    except RuntimeError:
        raised_send = True
    expect(raised_send, "a send failure must re-raise so we never falsely report delivered")
    print("PASS test_interim_streaming_edit_failure_is_nonfatal_final_still_fatal")


def test_interim_429_retry_after_honored_with_bounded_backoff() -> None:
    # H-3: a Telegram-style 429 with retry_after is honored with ONE bounded
    # retry rather than raising; if the retry succeeds the interim edit succeeds.
    bridge = _load_module(BRIDGE_PY, "arclink_public_agent_bridge_h3_retry_test")
    evidence = bridge._DeliveryEvidence()

    class _RetryAfter(Exception):
        def __init__(self) -> None:
            super().__init__("Flood control exceeded. Retry after 2")
            self.retry_after = 2

    # retry_after must be clamped to the bounded max.
    wait = bridge._retry_after_seconds(_RetryAfter())
    expect(wait is not None, "retry_after error must be recognized")
    expect(wait <= bridge.BRIDGE_INTERIM_RETRY_AFTER_MAX_SECONDS, f"retry_after must be bounded, got {wait}")
    # A non-429 error must NOT be treated as a retry.
    expect(bridge._retry_after_seconds(RuntimeError("discord http 400: bad")) is None, "non-429 must not retry")

    state = {"calls": 0}

    class _Adapter:
        async def edit_message(self, chat_id, message_id, content, *, finalize=False, **_kw):
            state["calls"] += 1
            if state["calls"] == 1:
                raise _RetryAfter()
            return bridge.SimpleNamespace(success=True, message_id=message_id, error="", raw_response=None)

    adapter = _Adapter()
    # Avoid actually sleeping the bounded backoff in the test.
    orig_sleep = bridge.asyncio.sleep

    async def _fast_sleep(_seconds):
        return None

    bridge.asyncio.sleep = _fast_sleep  # type: ignore[assignment]
    try:
        bridge._install_delivery_evidence(adapter, evidence)
        result = asyncio.run(adapter.edit_message("c", "m", "interim", finalize=False))
    finally:
        bridge.asyncio.sleep = orig_sleep  # type: ignore[assignment]
    expect(state["calls"] == 2, f"429 must trigger exactly one bounded retry, calls={state['calls']}")
    expect(result.success is True, "a successful retry after 429 must yield a successful interim edit")
    print("PASS test_interim_429_retry_after_honored_with_bounded_backoff")


def test_malformed_id_fails_fast_before_agent_runs() -> None:
    # H-4: a malformed (non-numeric) chat_id/channel_id/user_id must fail fast
    # with a structured error BEFORE the agent turn runs (before any gateway
    # import). Strict shape enforcement is gated ON via the env flag (default-off
    # so existing placeholder-id harnesses stay unaffected).
    bridge = _load_module(BRIDGE_PY, "arclink_public_agent_bridge_h4_validate_test")
    old_env = os.environ.copy()
    try:
        # Default-off: legacy non-empty behavior, non-numeric placeholder allowed.
        os.environ.pop("ARCLINK_PUBLIC_AGENT_BRIDGE_VALIDATE_IDS", None)
        expect(
            bridge._require_numeric_id({"chat_id": "tg-chat"}, "chat_id", negatives_ok=True) == "tg-chat",
            "with the gate OFF a placeholder id must pass (legacy behavior preserved)",
        )

        os.environ["ARCLINK_PUBLIC_AGENT_BRIDGE_VALIDATE_IDS"] = "1"

        # Direct shape checks: telegram chat ids may be negative; non-numeric rejected.
        expect(
            bridge._require_numeric_id({"chat_id": "-100200300"}, "chat_id", negatives_ok=True) == "-100200300",
            "negative telegram chat_id ok",
        )
        for bad in ("abc", "12ab", "@user", "tg-chat", "", "  "):
            rejected = False
            try:
                bridge._require_numeric_id({"chat_id": bad}, "chat_id", negatives_ok=True)
            except RuntimeError:
                rejected = True
            expect(rejected, f"malformed chat_id {bad!r} must be rejected when the gate is ON")
        # Discord ids must be positive snowflakes -> a negative is malformed.
        neg_rejected = False
        try:
            bridge._require_numeric_id({"channel_id": "-5"}, "channel_id")
        except RuntimeError:
            neg_rejected = True
        expect(neg_rejected, "discord channel_id must reject a negative id")

        # End-to-end: _run_telegram must raise the malformed-id error fast. We
        # rely on the fact that validation precedes _add_runtime_paths(): if it
        # did NOT run first the error would be the runtime-missing sentinel.
        sentinel = "Hermes runtime source is missing"
        err = ""
        try:
            asyncio.run(bridge._run_telegram({"bot_token": "t", "chat_id": "not-a-number", "text": "hi"}))
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
        expect("malformed chat_id" in err, f"malformed chat_id must fail fast with its own error, got: {err!r}")
        expect(sentinel not in err, "validation must run BEFORE the runtime/gateway path is touched")
    finally:
        os.environ.clear()
        os.environ.update(old_env)
    print("PASS test_malformed_id_fails_fast_before_agent_runs")


def test_discord_getme_resolves_real_bot_user_id() -> None:
    # H-2: the Discord bot user id must come from getMe (/users/@me), not the
    # hard-coded placeholder; getMe failure falls back to the placeholder.
    bridge = _load_module(BRIDGE_PY, "arclink_public_agent_bridge_h2_getme_test")

    rest = _RecordingRest(getme={"id": "424242424242424242", "username": "realbot"})
    resolved = asyncio.run(bridge._resolve_discord_bot_user_id(rest, "bot-token"))
    expect(resolved == "424242424242424242", f"must use the REAL getMe id, got {resolved!r}")
    expect(("GET", "/users/@me", None) in rest.calls, "must call Discord getMe")

    class _FailingRest:
        async def request(self, method, path, *, payload=None):
            raise RuntimeError("discord http 401: unauthorized")

    fallback = asyncio.run(bridge._resolve_discord_bot_user_id(_FailingRest(), "bot-token"))
    expect(fallback == bridge.DISCORD_BRIDGE_FALLBACK_USER_ID, f"getMe failure must fall back, got {fallback!r}")
    print("PASS test_discord_getme_resolves_real_bot_user_id")


def _install_fake_gateway(bridge, *, rest: _RecordingRest, drive) -> None:
    """Install a minimal fake ``gateway.*`` + ``aiohttp`` so ``_run_discord``
    runs end-to-end with our recording REST and a fake adapter that streams via
    the REAL bridge-installed ``edit_message`` (``drive`` does the streaming)."""

    class _Platform:
        DISCORD = "discord"
        TELEGRAM = "telegram"

    class _PlatformConfig:
        def __init__(self) -> None:
            self.enabled = False
            self.token = ""
            self.gateway_restart_notification = True
            self.reply_to_mode = "first"
            self.home_channel = None

    class _HomeChannel:
        def __init__(self, **kw) -> None:
            self.__dict__.update(kw)

    class _Cfg:
        def __init__(self) -> None:
            self.platforms = {}
            self.streaming = bridge.SimpleNamespace(enabled=False, transport="")

    def _load_gateway_config():
        return _Cfg()

    class _MessageType:
        COMMAND = "command"
        TEXT = "text"

    class _SendResult:
        def __init__(self, success=False, message_id=None, error=None, raw_response=None, continuation_message_ids=()):
            self.success = success
            self.message_id = message_id
            self.error = error
            self.raw_response = raw_response
            self.continuation_message_ids = continuation_message_ids

    class _MessageEvent:
        def __init__(self, **kw) -> None:
            self.__dict__.update(kw)

    class _SessionSource:
        def __init__(self, **kw) -> None:
            self.__dict__.update(kw)

    class _Adapter:
        MAX_MESSAGE_LENGTH = 2000
        _reply_to_mode = "first"

        def __init__(self) -> None:
            self.send = None
            self.edit_message = None
            self.send_typing = None
            self.stop_typing = None
            self._client = None

        def format_message(self, content):
            return content

        def truncate_message(self, content, _limit):
            # Force a 3-chunk overflow regardless of length so the test is
            # deterministic about the overflow-send behavior.
            return ["CHUNK-A", "CHUNK-B", "CHUNK-C"]

        def set_message_handler(self, *_a, **_k):
            pass

        def set_fatal_error_handler(self, *_a, **_k):
            pass

        def set_session_store(self, *_a, **_k):
            pass

        def set_busy_session_handler(self, *_a, **_k):
            pass

        async def handle_message(self, _event):
            # Stream one interim edit through the REAL bridge-installed closure.
            await drive(self)

    class _Runner:
        def __init__(self, _cfg) -> None:
            self.adapters = {}
            self.session_store = object()

        def _create_adapter(self, _platform, _cfg):
            return _Adapter()

        def _handle_message(self, *_a, **_k):
            pass

        def _handle_adapter_fatal_error(self, *_a, **_k):
            pass

        def _handle_active_session_busy_message(self, *_a, **_k):
            pass

    gateway = types.ModuleType("gateway")
    gateway_config = types.ModuleType("gateway.config")
    gateway_config.HomeChannel = _HomeChannel
    gateway_config.Platform = _Platform
    gateway_config.PlatformConfig = _PlatformConfig
    gateway_config.load_gateway_config = _load_gateway_config
    gateway_platforms = types.ModuleType("gateway.platforms")
    gateway_platforms_base = types.ModuleType("gateway.platforms.base")
    gateway_platforms_base.MessageEvent = _MessageEvent
    gateway_platforms_base.MessageType = _MessageType
    gateway_platforms_base.SendResult = _SendResult
    gateway_run = types.ModuleType("gateway.run")
    gateway_run.GatewayRunner = _Runner
    gateway_session = types.ModuleType("gateway.session")
    gateway_session.SessionSource = _SessionSource

    # aiohttp stand-in: _DiscordRest.__aenter__ builds a session, but we patch
    # the whole class so the bridge uses our recording REST instead.
    aiohttp = types.ModuleType("aiohttp")
    aiohttp.ClientSession = lambda *a, **k: None
    aiohttp.ClientTimeout = lambda *a, **k: None

    for name, mod in {
        "gateway": gateway,
        "gateway.config": gateway_config,
        "gateway.platforms": gateway_platforms,
        "gateway.platforms.base": gateway_platforms_base,
        "gateway.run": gateway_run,
        "gateway.session": gateway_session,
        "aiohttp": aiohttp,
    }.items():
        sys.modules[name] = mod


def test_discord_edit_overflow_sends_all_chunks() -> None:
    # H-2: a streamed Discord edit whose content exceeds 2000 chars must send the
    # overflow chunks as ADDITIONAL messages instead of silently dropping them.
    bridge = _load_module(BRIDGE_PY, "arclink_public_agent_bridge_h2_overflow_test")
    rest = _RecordingRest()

    captured: dict = {}

    async def _drive(adapter) -> None:
        # Call the REAL bridge-installed edit_message closure with overflow
        # content; truncate_message returns 3 chunks deterministically.
        result = await adapter.edit_message("123456789", "orig-msg", "x" * 6000, finalize=True)
        captured["result"] = result

    # Patch _DiscordRest + _add_runtime_paths + getMe so _run_discord runs.
    orig_rest_cls = bridge._DiscordRest
    orig_add_paths = bridge._add_runtime_paths
    orig_resolve = bridge._resolve_discord_bot_user_id

    class _RestCtx:
        def __init__(self, _token) -> None:
            pass

        async def __aenter__(self):
            return rest

        async def __aexit__(self, *_a):
            return None

    async def _fake_resolve(_rest, _token):
        return "555"

    _install_fake_gateway(bridge, rest=rest, drive=_drive)
    bridge._DiscordRest = _RestCtx  # type: ignore[assignment]
    bridge._add_runtime_paths = lambda: None  # type: ignore[assignment]
    bridge._resolve_discord_bot_user_id = _fake_resolve  # type: ignore[assignment]
    old_env = os.environ.copy()
    try:
        summary = asyncio.run(
            bridge._run_discord(
                {
                    "bot_token": "t",
                    "channel_id": "123456789",
                    "user_id": "987654321",
                    "text": "hello",
                }
            )
        )
    finally:
        bridge._DiscordRest = orig_rest_cls  # type: ignore[assignment]
        bridge._add_runtime_paths = orig_add_paths  # type: ignore[assignment]
        bridge._resolve_discord_bot_user_id = orig_resolve  # type: ignore[assignment]
        for name in list(sys.modules):
            if name == "aiohttp" or name == "gateway" or name.startswith("gateway."):
                sys.modules.pop(name, None)
        os.environ.clear()
        os.environ.update(old_env)

    # One PATCH for chunk[0], then a POST for each of the 2 overflow chunks.
    patches = [c for c in rest.calls if c[0] == "PATCH"]
    posts = [c for c in rest.calls if c[0] == "POST" and c[1].endswith("/messages")]
    expect(len(patches) == 1, f"first chunk must be PATCHed into the existing message, got {len(patches)}")
    expect(len(posts) == 2, f"both overflow chunks must be POSTed as new messages, got {len(posts)}: {posts}")
    # The overflow chunks must carry the actual chunk content, not be dropped.
    post_contents = [(p[2] or {}).get("content") for p in posts]
    expect(post_contents == ["CHUNK-B", "CHUNK-C"], f"overflow content must be sent, got {post_contents}")
    # The result must report continuation ids so the gateway keeps full visibility.
    result = captured["result"]
    expect(result.continuation_message_ids == ("new-1", "new-2"), f"continuation ids must be reported: {result.continuation_message_ids}")
    expect(result.message_id == "new-2", f"message_id must be the LAST visible chunk: {result.message_id}")
    expect(isinstance(summary, dict), "run must still return an evidence summary")
    print("PASS test_discord_edit_overflow_sends_all_chunks")


def main() -> int:
    test_bridge_replay_dispatch_uses_known_handler_names()
    test_pinned_hermes_source_still_exposes_bridge_coupling()
    test_getme_cache_secret_uses_only_dedicated_secret_and_disables_on_missing()
    test_bridge_root_runtime_uid_gid_requires_resolution()
    test_bridge_root_drop_closure_asserts_and_does_not_swallow_setgroups()
    test_bridge_internal_deadline_fires_structured_error()
    test_interim_streaming_edit_failure_is_nonfatal_final_still_fatal()
    test_interim_429_retry_after_honored_with_bounded_backoff()
    test_malformed_id_fails_fast_before_agent_runs()
    test_discord_getme_resolves_real_bot_user_id()
    test_discord_edit_overflow_sends_all_chunks()
    print("PASS all 11 public agent bridge pin tests")
    return 0


if __name__ == "__main__":
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    raise SystemExit(main())
