#!/usr/bin/env python3
from __future__ import annotations

import json

from arclink_test_helpers import expect, load_module


def _adapter(*, allow_live_mutation: bool = False):
    mod = load_module("arclink_chutes_live.py", "arclink_chutes_live_adapter_test")
    credential_ref = "secret://arclink/chutes/accounts/user-1"
    token_ref = "secret://arclink/chutes/oauth/user-1/access"
    resolver = mod.StaticSecretResolver(
        {
            credential_ref: "resolved-provider-material",
            token_ref: "resolved-oauth-material",
        }
    )
    transport = mod.FakeChutesLiveTransport()
    adapter = mod.ChutesLiveAdapter(
        credential_ref=credential_ref,
        transport=transport,
        secret_resolver=resolver,
        allow_live_mutation=allow_live_mutation,
    )
    return mod, adapter, transport, token_ref


def _assert_public_payload_has_no_secret_material(payload: object) -> None:
    text = json.dumps(payload, sort_keys=True)
    for forbidden in (
        "resolved-provider-material",
        "resolved-oauth-material",
        "one-time-provider-secret-redacted-by-boundary",
    ):
        expect(forbidden not in text, text)
    expect("secret://arclink/chutes/accounts/user-1" not in text, text)


def test_chutes_live_adapter_reads_fixture_backed_account_usage_and_catalog() -> None:
    mod, adapter, transport, token_ref = _adapter()
    payloads = [
        adapter.list_models(),
        adapter.get_me(),
        adapter.get_subscription_usage(),
        adapter.get_user_usage("chutes_user_1", page=1, limit=50, per_chute=True, chute_id="kimi-k2-6-tee"),
        adapter.get_quota_usage("kimi-k2-6-tee"),
        adapter.get_quotas(),
        adapter.get_discounts(),
        adapter.get_price_overrides(),
        adapter.list_api_keys(),
        adapter.list_scopes(),
        adapter.introspect_oauth_token(token_ref),
    ]
    expect(payloads[0]["data"][0]["id"] == "moonshotai/Kimi-K2.6-TEE", str(payloads[0]))
    expect(payloads[1]["username"] == "arcuser", str(payloads[1]))
    expect(payloads[2]["usage_cents"] == 123, str(payloads[2]))
    expect(payloads[3]["items"][0]["requests"] == 3, str(payloads[3]))
    expect(payloads[4]["limit"] == 100, str(payloads[4]))
    expect(payloads[8]["items"][0]["api_key_id"] == "fake_existing_key", str(payloads[8]))
    expect(payloads[9]["items"][2]["scope"] == "chutes:invoke", str(payloads[9]))
    expect(payloads[10]["active"] is True and payloads[10]["token_ref_present"] is True, str(payloads[10]))
    for payload in payloads:
        _assert_public_payload_has_no_secret_material(payload)
    expect(any(call["path"].startswith("/users/chutes_user_1/usage?") for call in transport.calls), str(transport.calls))
    print("PASS test_chutes_live_adapter_reads_fixture_backed_account_usage_and_catalog")


def test_chutes_live_adapter_mutations_are_explicitly_proof_gated_and_redacted() -> None:
    mod, blocked, _blocked_transport, _token_ref = _adapter()
    try:
        blocked.create_api_key("ArcLink invoke", admin=False, scopes=["chutes:invoke"])
    except mod.ChutesLiveAdapterError as exc:
        expect("proof-gated" in str(exc), str(exc))
    else:
        raise AssertionError("expected API-key creation to require explicit mutation authorization")

    _mod, adapter, transport, _token_ref = _adapter(allow_live_mutation=True)
    created = adapter.create_api_key("ArcLink invoke", admin=False, scopes=["chutes:invoke"])
    expect(created["api_key_id"] == "fake_key_1", str(created))
    expect(created["secret_ref"].startswith("secret://arclink/chutes/api-keys/"), str(created))
    expect(created["redacted_fields"] == ["api_key"], str(created))
    _assert_public_payload_has_no_secret_material(created)

    listed = adapter.list_api_keys()
    expect(any(item["api_key_id"] == "fake_key_1" for item in listed["items"]), str(listed))
    deleted = adapter.delete_api_key("fake_key_1")
    expect(deleted == {"api_key_id": "fake_key_1", "deleted": True}, str(deleted))
    transfer = adapter.transfer_balance("recipient_user_2", "12.5")
    expect(transfer["status"] == "fake_not_executed", str(transfer))
    expect(transfer["live_status"] == "proof_gated_until_authorized_provider_transfer", str(transfer))
    _assert_public_payload_has_no_secret_material(transfer)
    expect(
        [call["method"] for call in transport.calls if call["path"] in {"/api_keys/", "/api_keys/fake_key_1", "/users/balance_transfer"}]
        == ["POST", "GET", "DELETE", "POST"],
        str(transport.calls),
    )
    print("PASS test_chutes_live_adapter_mutations_are_explicitly_proof_gated_and_redacted")


def test_chutes_live_adapter_rejects_raw_credentials_and_bad_scope() -> None:
    mod = load_module("arclink_chutes_live.py", "arclink_chutes_live_validation_test")
    try:
        mod.ChutesLiveAdapter(
            credential_ref="plain-provider-material",
            transport=mod.FakeChutesLiveTransport(),
            secret_resolver=mod.StaticSecretResolver({}),
        )
    except mod.ChutesLiveAdapterError as exc:
        expect("secret:// reference" in str(exc), str(exc))
    else:
        raise AssertionError("expected raw credential to be rejected")

    adapter_mod, adapter, _transport, _token_ref = _adapter(allow_live_mutation=True)
    try:
        adapter.get_user_usage("../other-user")
    except adapter_mod.ChutesLiveAdapterError as exc:
        expect("single path segment" in str(exc), str(exc))
    else:
        raise AssertionError("expected path traversal user id to be rejected")

    try:
        adapter.introspect_oauth_token("oauth-token-material")
    except adapter_mod.ChutesLiveAdapterError as exc:
        expect("secret:// reference" in str(exc), str(exc))
    else:
        raise AssertionError("expected raw OAuth token to be rejected")
    print("PASS test_chutes_live_adapter_rejects_raw_credentials_and_bad_scope")


def main() -> int:
    test_chutes_live_adapter_reads_fixture_backed_account_usage_and_catalog()
    test_chutes_live_adapter_mutations_are_explicitly_proof_gated_and_redacted()
    test_chutes_live_adapter_rejects_raw_credentials_and_bad_scope()
    print("PASS all 3 ArcLink Chutes live adapter tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
