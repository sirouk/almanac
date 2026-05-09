#!/usr/bin/env python3
from __future__ import annotations

import json

from arclink_test_helpers import expect, load_module


def _oauth_fixture():
    mod = load_module("arclink_chutes_oauth.py", "arclink_chutes_oauth_test")
    config = mod.ChutesOAuthConfig(
        client_id="arclink-test-client",
        client_secret_ref="secret://arclink/chutes/oauth/client-secret",
        redirect_uri="https://control.example.test/api/v1/user/provider/chutes/callback",
    )
    state_store = mod.InMemoryChutesOAuthStateStore()
    token_store = mod.InMemoryChutesOAuthTokenStore()
    exchanger = mod.FakeChutesOAuthCodeExchanger()
    return mod, config, state_store, token_store, exchanger


def _assert_no_raw_oauth_material(payload: object) -> None:
    text = json.dumps(payload, sort_keys=True)
    for forbidden in (
        "fake-chutes-access-token-material",
        "fake-chutes-refresh-token-material",
        "fake-chutes-id-token-material",
        "secret://arclink/chutes/oauth/user-1/access",
        "secret://arclink/chutes/oauth/client-secret",
    ):
        expect(forbidden not in text, text)


def test_chutes_oauth_connect_plan_scopes_and_public_shape() -> None:
    mod, config, state_store, _token_store, _exchanger = _oauth_fixture()
    plan = mod.start_chutes_oauth_connect(
        user_id="user-1",
        session_id="sess-1",
        config=config,
        state_store=state_store,
        include_usage_read=True,
        include_billing_read=True,
        now=1000,
    )
    public = plan.to_public()
    expect(public["provider"] == "chutes", str(public))
    expect(public["csrf_required"] is True, str(public))
    expect(public["pkce"] == "S256", str(public))
    expect("state=" in public["authorize_url"], str(public))
    expect("code_challenge=" in public["authorize_url"], str(public))
    expect("billing:read" in public["scopes"], str(public))
    expect("usage:read" in public["scopes"], str(public))
    expect(any(item["scope"] == "chutes:invoke" for item in public["scope_display"]), str(public))
    _assert_no_raw_oauth_material(public)
    print("PASS test_chutes_oauth_connect_plan_scopes_and_public_shape")


def test_chutes_oauth_callback_validates_state_csrf_and_user_scope() -> None:
    mod, config, state_store, token_store, exchanger = _oauth_fixture()
    plan = mod.start_chutes_oauth_connect(
        user_id="user-1",
        session_id="sess-1",
        config=config,
        state_store=state_store,
        now=1000,
    )
    try:
        mod.complete_chutes_oauth_callback(
            user_id="user-1",
            session_id="sess-1",
            state="wrong-state",
            csrf_token=plan.csrf_token,
            code="code-1",
            config=config,
            state_store=state_store,
            token_store=token_store,
            exchanger=exchanger,
            now=1001,
        )
    except mod.ChutesOAuthError as exc:
        expect("state mismatch" in str(exc), str(exc))
    else:
        raise AssertionError("expected state mismatch to fail")

    plan = mod.start_chutes_oauth_connect(
        user_id="user-1",
        session_id="sess-1",
        config=config,
        state_store=state_store,
        now=1000,
    )
    try:
        mod.complete_chutes_oauth_callback(
            user_id="user-2",
            session_id="sess-1",
            state=plan.state,
            csrf_token=plan.csrf_token,
            code="code-1",
            config=config,
            state_store=state_store,
            token_store=token_store,
            exchanger=exchanger,
            now=1001,
        )
    except mod.ChutesOAuthError as exc:
        expect("not scoped" in str(exc), str(exc))
    else:
        raise AssertionError("expected user scope mismatch to fail")
    connection = mod.complete_chutes_oauth_callback(
        user_id="user-1",
        session_id="sess-1",
        state=plan.state,
        csrf_token=plan.csrf_token,
        code="code-1",
        config=config,
        state_store=state_store,
        token_store=token_store,
        exchanger=exchanger,
        now=1001,
    )
    expect(connection.user_id == "user-1", str(connection))

    plan = mod.start_chutes_oauth_connect(
        user_id="user-1",
        session_id="sess-1",
        config=config,
        state_store=state_store,
        now=1000,
    )
    try:
        mod.complete_chutes_oauth_callback(
            user_id="user-1",
            session_id="sess-1",
            state=plan.state,
            csrf_token="wrong-csrf",
            code="code-1",
            config=config,
            state_store=state_store,
            token_store=token_store,
            exchanger=exchanger,
            now=1001,
        )
    except mod.ChutesOAuthError as exc:
        expect("CSRF" in str(exc), str(exc))
    else:
        raise AssertionError("expected CSRF mismatch to fail")
    connection = mod.complete_chutes_oauth_callback(
        user_id="user-1",
        session_id="sess-1",
        state=plan.state,
        csrf_token=plan.csrf_token,
        code="code-1",
        config=config,
        state_store=state_store,
        token_store=token_store,
        exchanger=exchanger,
        now=1001,
    )
    expect(connection.user_id == "user-1", str(connection))
    print("PASS test_chutes_oauth_callback_validates_state_csrf_and_user_scope")


def test_chutes_oauth_callback_stores_secret_refs_and_public_connection_only() -> None:
    mod, config, state_store, token_store, exchanger = _oauth_fixture()
    plan = mod.start_chutes_oauth_connect(
        user_id="user-1",
        session_id="sess-1",
        config=config,
        state_store=state_store,
        include_usage_read=True,
        now=1000,
    )
    connection = mod.complete_chutes_oauth_callback(
        user_id="user-1",
        session_id="sess-1",
        state=plan.state,
        csrf_token=plan.csrf_token,
        code="code-1",
        config=config,
        state_store=state_store,
        token_store=token_store,
        exchanger=exchanger,
        now=1001,
    )
    expect(connection.access_token_ref.startswith("secret://arclink/chutes/oauth/user-1/access/"), connection.access_token_ref)
    expect(connection.refresh_token_ref.startswith("secret://arclink/chutes/oauth/user-1/refresh/"), connection.refresh_token_ref)
    expect(len(token_store.tokens) == 2, str(token_store.tokens))
    expect(exchanger.calls[0]["client_secret_ref_present"] is True, str(exchanger.calls))
    public = connection.to_public()
    expect(public["connected"] is True, str(public))
    expect(public["account"]["user_id"] == "chutes_user_1", str(public))
    expect(public["usage_readiness"] == "available", str(public))
    expect(public["billing_readiness"] == "not_requested", str(public))
    expect(public["token_ref_present"] is True, str(public))
    expect(public["disconnect"]["status"] == "ready", str(public))
    _assert_no_raw_oauth_material(public)
    print("PASS test_chutes_oauth_callback_stores_secret_refs_and_public_connection_only")


def test_chutes_oauth_disconnect_is_ready_but_live_revoke_proof_gated() -> None:
    mod, config, state_store, token_store, exchanger = _oauth_fixture()
    plan = mod.start_chutes_oauth_connect(
        user_id="user-1",
        session_id="sess-1",
        config=config,
        state_store=state_store,
    )
    connection = mod.complete_chutes_oauth_callback(
        user_id="user-1",
        session_id="sess-1",
        state=plan.state,
        csrf_token=plan.csrf_token,
        code="code-1",
        config=config,
        state_store=state_store,
        token_store=token_store,
        exchanger=exchanger,
    )
    disconnected = mod.disconnect_chutes_oauth(connection)
    expect(disconnected["connected"] is False, str(disconnected))
    expect(disconnected["token_refs_removed"] is True, str(disconnected))
    expect(disconnected["live_revoke"] == "proof_gated_until_operator_authorizes_chutes_oauth_revoke", str(disconnected))
    _assert_no_raw_oauth_material(disconnected)
    try:
        mod.disconnect_chutes_oauth(connection, revoke_live=True)
    except mod.ChutesOAuthError as exc:
        expect("proof-gated" in str(exc), str(exc))
    else:
        raise AssertionError("expected live revoke to remain proof-gated")
    print("PASS test_chutes_oauth_disconnect_is_ready_but_live_revoke_proof_gated")


def test_chutes_oauth_config_rejects_raw_secret_and_bad_redirect() -> None:
    mod = load_module("arclink_chutes_oauth.py", "arclink_chutes_oauth_validation_test")
    try:
        mod.ChutesOAuthConfig(
            client_id="arclink-test-client",
            client_secret_ref="csc_raw_client_secret",
            redirect_uri="https://control.example.test/callback",
        )
    except mod.ChutesOAuthError as exc:
        expect("secret:// reference" in str(exc) or "raw secret" in str(exc), str(exc))
    else:
        raise AssertionError("expected raw client secret to fail")
    try:
        mod.ChutesOAuthConfig(
            client_id="arclink-test-client",
            client_secret_ref="secret://arclink/chutes/oauth/client-secret",
            redirect_uri="http://control.example.test/callback",
        )
    except mod.ChutesOAuthError as exc:
        expect("HTTPS" in str(exc), str(exc))
    else:
        raise AssertionError("expected non-TLS redirect to fail")
    print("PASS test_chutes_oauth_config_rejects_raw_secret_and_bad_redirect")


def main() -> int:
    test_chutes_oauth_connect_plan_scopes_and_public_shape()
    test_chutes_oauth_callback_validates_state_csrf_and_user_scope()
    test_chutes_oauth_callback_stores_secret_refs_and_public_connection_only()
    test_chutes_oauth_disconnect_is_ready_but_live_revoke_proof_gated()
    test_chutes_oauth_config_rejects_raw_secret_and_bad_redirect()
    print("PASS all 5 ArcLink Chutes OAuth tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
