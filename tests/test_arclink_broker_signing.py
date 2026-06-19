#!/usr/bin/env python3
"""GAP-019 pass-2 broker request-signing hardening tests.

Covers, for every trusted-host broker/helper:

  * sign/verify HMAC round-trip (valid signature accepts when require_signed),
  * tampered body / expired timestamp / replayed nonce all reject when
    require_signed is on,
  * bare-token-only admits when require_signed is OFF and is rejected when ON,
  * the lock-step-safe accept-both skew matrix (legacy client + new broker, new
    client + legacy-style request) never breaks admission at require_signed=off,
  * H3 (supervisor broker container/backend_host binding), and
  * M1 (agent-process uid/gid binding).
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


def load_module(name: str):
    path = PYTHON_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


signing = load_module("arclink_broker_signing")


class FreshStore:
    """A NonceStore whose backing file lives in a throwaway temp dir per broker."""

    def __init__(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.path = Path(self._dir.name) / "signature-nonces.json"
        self.store = signing.NonceStore(lambda: self.path)

    def cleanup(self) -> None:
        self._dir.cleanup()


def _bearer_and_signed_headers(token: str, body: bytes, bearer_header: str, **kw):
    headers = {bearer_header: token}
    headers.update(signing.sign_broker_request(token, body, **kw))
    return headers


# ---------------------------------------------------------------------------
# Shared sign/verify primitives.
# ---------------------------------------------------------------------------

def test_shared_sign_verify_roundtrip_and_rejections() -> None:
    token = "shared-broker-token"
    bearer = "X-Test-Bearer"
    body = b'{"operation":"x","value":1}'

    fresh = FreshStore()
    try:
        # Valid signature accepts when require_signed is on.
        headers = _bearer_and_signed_headers(token, body, bearer)
        ok, reason = signing.verify_broker_request(
            token, headers, body, fresh.store, bearer_header=bearer, require_signed=True
        )
        expect(ok and reason == "ok", f"valid signature must accept: {reason}")

        # Replayed nonce rejects (same nonce again).
        ok, reason = signing.verify_broker_request(
            token, headers, body, fresh.store, bearer_header=bearer, require_signed=True
        )
        expect(not ok and reason == "nonce_replayed", f"replay must reject: {reason}")

        # Tampered body rejects (signature no longer covers the bytes).
        headers2 = _bearer_and_signed_headers(token, body, bearer)
        ok, reason = signing.verify_broker_request(
            token, headers2, body + b"X", fresh.store, bearer_header=bearer, require_signed=True
        )
        expect(not ok and reason == "signature_mismatch", f"tampered body must reject: {reason}")

        # Expired timestamp rejects.
        old_ts = int(time.time()) - (signing.REQUEST_SIGNATURE_TTL_SECONDS + 60)
        headers3 = _bearer_and_signed_headers(token, body, bearer, timestamp=old_ts)
        ok, reason = signing.verify_broker_request(
            token, headers3, body, fresh.store, bearer_header=bearer, require_signed=True
        )
        expect(not ok and reason == "timestamp_expired", f"expired ts must reject: {reason}")

        # Wrong bearer token always rejects, signed or not.
        headers4 = _bearer_and_signed_headers(token, body, bearer)
        ok, reason = signing.verify_broker_request(
            "wrong-token", headers4, body, fresh.store, bearer_header=bearer, require_signed=True
        )
        expect(not ok and reason == "bearer_token_invalid", f"wrong bearer must reject: {reason}")
    finally:
        fresh.cleanup()
    print("PASS test_shared_sign_verify_roundtrip_and_rejections")


def test_shared_accept_both_admission_matrix() -> None:
    token = "matrix-token"
    bearer = "X-Test-Bearer"
    body = b'{"k":"v"}'

    # require_signed OFF: bare token (no signature headers) admits -> legacy
    # client + new broker is a no-op.
    fresh = FreshStore()
    try:
        bare = {bearer: token}
        ok, reason = signing.verify_broker_request(
            token, bare, body, fresh.store, bearer_header=bearer, require_signed=False
        )
        expect(ok and reason == "bare_token_admitted", f"off: bare token must admit: {reason}")

        # require_signed OFF: new client + new broker (signed) also admits, and
        # an INVALID signature alongside a valid bare token still admits.
        signed = _bearer_and_signed_headers(token, body, bearer)
        ok, reason = signing.verify_broker_request(
            token, signed, body, fresh.store, bearer_header=bearer, require_signed=False
        )
        expect(ok, "off: signed request must admit")

        bad_sig = {bearer: token,
                   signing.TIMESTAMP_HEADER: str(int(time.time())),
                   signing.NONCE_HEADER: "bogusnonce-000000",
                   signing.SIGNATURE_HEADER: "0" * 64}
        ok, reason = signing.verify_broker_request(
            token, bad_sig, body, fresh.store, bearer_header=bearer, require_signed=False
        )
        expect(ok and reason == "bare_token_admitted",
               f"off: invalid signature must not reject a valid bare token: {reason}")

        # require_signed ON: bare token (no signature) is rejected.
        ok, reason = signing.verify_broker_request(
            token, bare, body, fresh.store, bearer_header=bearer, require_signed=True
        )
        expect(not ok and reason == "signature_missing", f"on: bare token must reject: {reason}")
    finally:
        fresh.cleanup()
    print("PASS test_shared_accept_both_admission_matrix")


def test_require_signed_enforced_env_flag() -> None:
    old = os.environ.get("ARCLINK_BROKER_REQUIRE_SIGNED")
    try:
        for value, expected in (("", False), ("0", False), ("no", False), ("off", False),
                                ("1", True), ("true", True), ("on", True), ("YES", True)):
            os.environ["ARCLINK_BROKER_REQUIRE_SIGNED"] = value
            expect(signing.require_signed_enforced() is expected,
                   f"flag {value!r} -> {signing.require_signed_enforced()} (want {expected})")
        os.environ.pop("ARCLINK_BROKER_REQUIRE_SIGNED", None)
        expect(signing.require_signed_enforced() is False, "unset flag must be OFF (default)")
    finally:
        if old is None:
            os.environ.pop("ARCLINK_BROKER_REQUIRE_SIGNED", None)
        else:
            os.environ["ARCLINK_BROKER_REQUIRE_SIGNED"] = old
    print("PASS test_require_signed_enforced_env_flag")


# ---------------------------------------------------------------------------
# Per-broker _is_authorized round-trip + accept-both skew, with a temp nonce
# store so replay state is isolated per case.
# ---------------------------------------------------------------------------

def _exercise_broker_is_authorized(module, *, token_env: str, token_value: str, bearer_header: str,
                                   label: str) -> None:
    body = b'{"operation":"noop"}'
    fresh = FreshStore()
    old_env = os.environ.copy()
    try:
        os.environ[token_env] = token_value
        module._NONCE_STORE = fresh.store  # isolate replay state

        # --- require_signed OFF (default): accept-both ---
        os.environ.pop("ARCLINK_BROKER_REQUIRE_SIGNED", None)

        # Legacy client: bare token only (no signature) -> admits.
        bare = {bearer_header: token_value}
        expect(module._is_authorized(bare, body) is True, f"{label}: off bare token must admit")

        # New client: signed -> admits.
        signed = _bearer_and_signed_headers(token_value, body, bearer_header)
        expect(module._is_authorized(signed, body) is True, f"{label}: off signed must admit")

        # Wrong bearer token -> rejected even off.
        wrong = {bearer_header: "nope"}
        expect(module._is_authorized(wrong, body) is False, f"{label}: off wrong token must reject")

        # New client + legacy-style broker view: extra/unknown headers ignored,
        # valid bare token still admits (skew no-op).
        skew = {bearer_header: token_value, "X-Unknown-Header": "junk"}
        expect(module._is_authorized(skew, body) is True, f"{label}: off skew must admit")

        # --- require_signed ON: enforce signed+nonce ---
        os.environ["ARCLINK_BROKER_REQUIRE_SIGNED"] = "1"
        fresh2 = FreshStore()
        module._NONCE_STORE = fresh2.store
        try:
            # Bare token now rejected.
            expect(module._is_authorized({bearer_header: token_value}, body) is False,
                   f"{label}: on bare token must reject")
            # Valid signed accepts.
            signed_on = _bearer_and_signed_headers(token_value, body, bearer_header)
            expect(module._is_authorized(signed_on, body) is True, f"{label}: on signed must accept")
            # Replay of same nonce rejects.
            expect(module._is_authorized(signed_on, body) is False, f"{label}: on replay must reject")
            # Tampered body rejects.
            signed_t = _bearer_and_signed_headers(token_value, body, bearer_header)
            expect(module._is_authorized(signed_t, body + b"!") is False,
                   f"{label}: on tampered body must reject")
            # Expired timestamp rejects.
            old_ts = int(time.time()) - (signing.REQUEST_SIGNATURE_TTL_SECONDS + 60)
            signed_e = _bearer_and_signed_headers(token_value, body, bearer_header, timestamp=old_ts)
            expect(module._is_authorized(signed_e, body) is False,
                   f"{label}: on expired ts must reject")
        finally:
            fresh2.cleanup()
    finally:
        os.environ.clear()
        os.environ.update(old_env)
        fresh.cleanup()
    print(f"PASS test_{label}_is_authorized_signing")


def test_deployment_exec_broker_signing() -> None:
    module = load_module("arclink_deployment_exec_broker")
    _exercise_broker_is_authorized(
        module,
        token_env="ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN",
        token_value="deploy-token",
        bearer_header=module.executor.DEPLOYMENT_EXEC_BROKER_TOKEN_HEADER,
        label="deployment_exec_broker",
    )


def test_gateway_exec_broker_signing() -> None:
    module = load_module("arclink_gateway_exec_broker")
    # gateway broker token reads through delivery.config_env_value; set both.
    old = os.environ.copy()
    try:
        _exercise_broker_is_authorized(
            module,
            token_env="ARCLINK_GATEWAY_EXEC_BROKER_TOKEN",
            token_value="gateway-token",
            bearer_header=module.delivery.GATEWAY_EXEC_BROKER_TOKEN_HEADER,
            label="gateway_exec_broker",
        )
    finally:
        os.environ.clear()
        os.environ.update(old)


def test_agent_supervisor_broker_signing() -> None:
    module = load_module("arclink_agent_supervisor_broker")
    _exercise_broker_is_authorized(
        module,
        token_env="ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN",
        token_value="supervisor-token",
        bearer_header=module.AGENT_SUPERVISOR_BROKER_TOKEN_HEADER,
        label="agent_supervisor_broker",
    )


def test_agent_user_helper_signing() -> None:
    module = load_module("arclink_agent_user_helper")
    _exercise_broker_is_authorized(
        module,
        token_env="ARCLINK_AGENT_USER_HELPER_TOKEN",
        token_value="user-helper-token",
        bearer_header=module.AGENT_USER_HELPER_TOKEN_HEADER,
        label="agent_user_helper",
    )


def test_agent_process_helper_signing() -> None:
    module = load_module("arclink_agent_process_helper")
    _exercise_broker_is_authorized(
        module,
        token_env="ARCLINK_AGENT_PROCESS_HELPER_TOKEN",
        token_value="process-helper-token",
        bearer_header=module.AGENT_PROCESS_HELPER_TOKEN_HEADER,
        label="agent_process_helper",
    )


def test_migration_capture_helper_signing() -> None:
    module = load_module("arclink_migration_capture_helper")
    _exercise_broker_is_authorized(
        module,
        token_env="ARCLINK_MIGRATION_CAPTURE_HELPER_TOKEN",
        token_value="migration-token",
        bearer_header=module.MIGRATION_CAPTURE_HELPER_TOKEN_HEADER,
        label="migration_capture_helper",
    )


def test_operator_upgrade_broker_signing_strict() -> None:
    # Operator-upgrade broker is unconditionally strict (its client always signs).
    module = load_module("arclink_operator_upgrade_broker")
    body = b'{"operation":"run_operator_upgrade","log_path":"/p/state/operator-actions/u.log"}'
    bearer = module.OPERATOR_UPGRADE_BROKER_TOKEN_HEADER
    token = "operator-upgrade-token"
    fresh = FreshStore()
    old_env = os.environ.copy()
    try:
        os.environ["ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN"] = token
        # Bind shared store to a temp file via the module globals it owns.
        module._SEEN_SIGNATURE_NONCES.clear()
        module._SEEN_SIGNATURE_NONCES_LOADED_FROM = ""
        module._NONCE_STORE = signing.NonceStore(
            lambda: fresh.path,
            seen=module._SEEN_SIGNATURE_NONCES,
            max_entries=lambda: module.MAX_SEEN_SIGNATURE_NONCES,
            loaded_from_get=lambda: module._SEEN_SIGNATURE_NONCES_LOADED_FROM,
            loaded_from_set=module._set_seen_nonces_loaded_from,
        )

        ts = int(time.time())
        nonce = "operator-nonce-000001"
        sig = signing.sign_broker_request(token, body, timestamp=ts, nonce=nonce)
        headers = {
            bearer: token,
            module.OPERATOR_UPGRADE_BROKER_TIMESTAMP_HEADER: sig[signing.TIMESTAMP_HEADER],
            module.OPERATOR_UPGRADE_BROKER_NONCE_HEADER: sig[signing.NONCE_HEADER],
            module.OPERATOR_UPGRADE_BROKER_SIGNATURE_HEADER: sig[signing.SIGNATURE_HEADER],
        }
        # Strict even with require_signed unset / off: signed accepts.
        os.environ.pop("ARCLINK_BROKER_REQUIRE_SIGNED", None)
        expect(module._is_authorized(headers, body) is True, "operator-upgrade signed must accept")
        # Bare token alone rejected (strict).
        expect(module._is_authorized({bearer: token}, body) is False,
               "operator-upgrade bare token must reject (strict)")
        # Replay rejected.
        expect(module._is_authorized(headers, body) is False, "operator-upgrade replay must reject")
    finally:
        os.environ.clear()
        os.environ.update(old_env)
        fresh.cleanup()
    print("PASS test_operator_upgrade_broker_signing_strict")


# ---------------------------------------------------------------------------
# H3: supervisor broker container/backend_host binding.
# ---------------------------------------------------------------------------

def test_agent_supervisor_broker_h3_container_binding() -> None:
    module = load_module("arclink_agent_supervisor_broker")
    old_env = os.environ.copy()
    try:
        os.environ["ARCLINK_DOCKER_AGENT_SUPERVISOR_CONTAINER"] = "arclink-control-supervisor-1"

        # Request that names the configured container -> resolves to it.
        resolved = module._resolve_supervisor_container(
            {"supervisor_container": "arclink-control-supervisor-1"}
        )
        expect(resolved == "arclink-control-supervisor-1", f"matching container must resolve: {resolved}")

        # Request that names a DIFFERENT container -> rejected (no arbitrary attach).
        try:
            module._resolve_supervisor_container({"supervisor_container": "attacker-container"})
            raise AssertionError("mismatched supervisor container must be rejected")
        except ValueError as exc:
            expect("does not match the configured container" in str(exc), str(exc))

        # Request that omits the container -> falls back to the configured one.
        resolved = module._resolve_supervisor_container({})
        expect(resolved == "arclink-control-supervisor-1", f"omitted container must use configured: {resolved}")

        # backend_host re-derivation: stub _network_container_ip to a known IP and
        # confirm a mismatched request backend_host is rejected.
        module.os.environ["ARCLINK_DOCKER_IMAGE"] = "arclink/app:local"
        module.os.environ["ARCLINK_REPO_DIR"] = "/home/arclink/arclink"
        module.os.environ["ARCLINK_DOCKER_HOST_PRIV_DIR"] = "/home/arclink/arclink/arclink-priv"
        module.os.environ["ARCLINK_DOCKER_CONTAINER_PRIV_DIR"] = module.CONTAINER_PRIVATE_ROOT
        old_ip = module._network_container_ip
        module._network_container_ip = lambda net, container: "10.42.0.7"
        try:
            req = {
                "operation": "ensure_dashboard_proxy",
                "agent_id": "agent1",
                "network": module.docker_dashboard_network_name("agent1"),
                "container_name": module.docker_dashboard_proxy_container_name("agent1"),
                "backend_host": "10.42.0.99",  # disagrees with the derived 10.42.0.7
                "backend_port": 3000,
                "proxy_port": 13210,
                "access_file": module.CONTAINER_PRIVATE_ROOT + "/state/agent1/access",
            }
            try:
                module._ensure_dashboard_proxy(req)
                raise AssertionError("mismatched backend_host must be rejected")
            except ValueError as exc:
                expect("backend host does not match the supervisor container network IP" in str(exc),
                       f"H3 backend_host mismatch reason: {exc}")
        finally:
            module._network_container_ip = old_ip
    finally:
        os.environ.clear()
        os.environ.update(old_env)
    print("PASS test_agent_supervisor_broker_h3_container_binding")


def test_agent_supervisor_broker_h3_configured_but_unresolved_rejects() -> None:
    """H3(b): when the supervisor container IS configured but its network IP
    cannot be resolved, the broker fails closed instead of trusting the request's
    backend_host (no race-to-SSRF). With NO configured container the validated
    request value is still accepted (round-1 accept-both)."""
    module = load_module("arclink_agent_supervisor_broker")
    old_env = os.environ.copy()
    old_ip = module._network_container_ip
    try:
        os.environ["ARCLINK_DOCKER_AGENT_SUPERVISOR_CONTAINER"] = "arclink-control-supervisor-1"
        os.environ["ARCLINK_DOCKER_IMAGE"] = "arclink/app:local"
        os.environ["ARCLINK_REPO_DIR"] = "/home/arclink/arclink"
        os.environ["ARCLINK_DOCKER_HOST_PRIV_DIR"] = "/home/arclink/arclink/arclink-priv"
        os.environ["ARCLINK_DOCKER_CONTAINER_PRIV_DIR"] = module.CONTAINER_PRIVATE_ROOT

        req = {
            "operation": "ensure_dashboard_proxy",
            "agent_id": "agent1",
            "network": module.docker_dashboard_network_name("agent1"),
            "container_name": module.docker_dashboard_proxy_container_name("agent1"),
            "backend_host": "10.42.0.99",
            "backend_port": 3000,
            "proxy_port": 13210,
            "access_file": module.CONTAINER_PRIVATE_ROOT + "/state/agent1/access",
        }

        # Configured container, but the network IP lookup returns empty -> REJECT.
        module._network_container_ip = lambda net, container: ""
        try:
            module._ensure_dashboard_proxy(req)
            raise AssertionError("configured-but-unresolved supervisor must be rejected")
        except ValueError as exc:
            expect(
                "could not resolve the configured supervisor container network IP" in str(exc),
                f"H3(b) unresolved reason: {exc}",
            )

        # With NO configured container, the empty lookup must NOT reject: the
        # validated request backend_host is accepted (round-1 accept-both).
        os.environ.pop("ARCLINK_DOCKER_AGENT_SUPERVISOR_CONTAINER", None)
        captured: dict[str, str] = {}

        def fake_proxy_config_hash(config):
            captured["backend_host"] = str(config.get("backend_host") or "")
            return "deadbeef"

        old_hash = module._proxy_config_hash
        old_running = module._container_running_with_hash
        module._proxy_config_hash = fake_proxy_config_hash
        module._container_running_with_hash = lambda name, h: True  # short-circuit before docker run
        try:
            ok = module._ensure_dashboard_proxy(req)
            expect(ok.get("changed") is False, f"accept-both should short-circuit cleanly: {ok}")
            expect(captured.get("backend_host") == "10.42.0.99",
                   f"unconfigured broker must trust validated request backend_host: {captured}")
        finally:
            module._proxy_config_hash = old_hash
            module._container_running_with_hash = old_running
    finally:
        module._network_container_ip = old_ip
        os.environ.clear()
        os.environ.update(old_env)
    print("PASS test_agent_supervisor_broker_h3_configured_but_unresolved_rejects")


# ---------------------------------------------------------------------------
# M1: agent-process uid/gid binding.
# ---------------------------------------------------------------------------

def test_agent_process_helper_m1_uid_gid_binding() -> None:
    module = load_module("arclink_agent_process_helper")
    import pwd

    me = pwd.getpwuid(os.getuid())
    unix_user = me.pw_name

    # Matching uid/gid -> bound to the resolved account.
    uid, gid = module._bind_uid_gid_to_account(unix_user, me.pw_uid, me.pw_gid)
    expect(uid == me.pw_uid and gid == me.pw_gid, f"matching uid/gid must bind: {uid},{gid}")

    # Mismatched uid -> rejected (cannot run as an arbitrary uid such as 0).
    bad_uid = me.pw_uid + 1
    try:
        module._bind_uid_gid_to_account(unix_user, bad_uid, me.pw_gid)
        raise AssertionError("mismatched uid must be rejected")
    except ValueError as exc:
        expect("uid/gid does not match the resolved Unix account" in str(exc), str(exc))

    # Unknown account, no assignment file -> accept-both fallback returns the
    # request ids unchanged (preserves first-ever JIT account creation).
    uid, gid = module._bind_uid_gid_to_account("definitely-no-such-user-xyz", 31337, 31337)
    expect(uid == 31337 and gid == 31337, f"unknown account must fall back: {uid},{gid}")
    print("PASS test_agent_process_helper_m1_uid_gid_binding")


def test_agent_process_helper_m1_unknown_user_assignment_binding() -> None:
    """M1: an unknown OS account (not yet in this container's pwd db) is bound to
    the agent-user-helper's persisted .arclink-user-ids.json assignment under the
    Docker agent-home-root: a matching request binds, a mismatched one is
    rejected (no arbitrary uid/gid for an unknown user)."""
    import json as _json
    import tempfile as _tempfile

    module = load_module("arclink_agent_process_helper")
    unknown_user = "definitely-no-such-user-xyz"
    with _tempfile.TemporaryDirectory() as tmp:
        home_root = Path(tmp)
        assignments = {unknown_user: {"uid": 23456, "gid": 23456}}
        (home_root / module.AGENT_ID_ASSIGNMENTS_FILE).write_text(
            _json.dumps(assignments), encoding="utf-8"
        )

        # Matching request uid/gid -> bound to the persisted assignment.
        uid, gid = module._bind_uid_gid_to_account(unknown_user, 23456, 23456, home_root=home_root)
        expect(uid == 23456 and gid == 23456, f"persisted assignment must bind: {uid},{gid}")

        # Mismatched request uid/gid -> rejected (cannot run as an arbitrary id).
        try:
            module._bind_uid_gid_to_account(unknown_user, 0, 0, home_root=home_root)
            raise AssertionError("mismatched unknown-user uid/gid must be rejected")
        except ValueError as exc:
            expect("does not match the persisted Unix account assignment" in str(exc), str(exc))

        # A user with NO persisted assignment entry stays accept-both (no
        # entry -> the only legitimately-unverifiable case).
        uid, gid = module._bind_uid_gid_to_account("another-unknown-user", 41000, 41000, home_root=home_root)
        expect(uid == 41000 and gid == 41000, f"no assignment entry must fall back: {uid},{gid}")
    print("PASS test_agent_process_helper_m1_unknown_user_assignment_binding")


def main() -> int:
    test_shared_sign_verify_roundtrip_and_rejections()
    test_shared_accept_both_admission_matrix()
    test_require_signed_enforced_env_flag()
    test_deployment_exec_broker_signing()
    test_gateway_exec_broker_signing()
    test_agent_supervisor_broker_signing()
    test_agent_user_helper_signing()
    test_agent_process_helper_signing()
    test_migration_capture_helper_signing()
    test_operator_upgrade_broker_signing_strict()
    test_agent_supervisor_broker_h3_container_binding()
    test_agent_supervisor_broker_h3_configured_but_unresolved_rejects()
    test_agent_process_helper_m1_uid_gid_binding()
    test_agent_process_helper_m1_unknown_user_assignment_binding()
    print("ALL broker signing hardening tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
