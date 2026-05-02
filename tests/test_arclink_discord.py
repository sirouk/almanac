#!/usr/bin/env python3
from __future__ import annotations

from arclink_test_helpers import expect, load_module, memory_db


def test_discord_config_from_env() -> None:
    dc = load_module("arclink_discord.py", "arclink_discord_config_test")
    cfg = dc.DiscordConfig.from_env({
        "DISCORD_BOT_TOKEN": "token",
        "DISCORD_APP_ID": "app123",
        "DISCORD_PUBLIC_KEY": "key",
    })
    expect(cfg.is_live, "should be live with all fields")
    empty = dc.DiscordConfig.from_env({})
    expect(not empty.is_live, "should not be live without fields")
    print("PASS test_discord_config_from_env")


def test_discord_ping_pong() -> None:
    dc = load_module("arclink_discord.py", "arclink_discord_ping_test")
    control = load_module("arclink_control.py", "arclink_control_dc_ping_test")
    conn = memory_db(control)
    result = dc.handle_discord_interaction(conn, {"type": 1})
    expect(result == {"type": 1}, str(result))
    print("PASS test_discord_ping_pong")


def test_discord_slash_command_through_bot_contract() -> None:
    dc = load_module("arclink_discord.py", "arclink_discord_slash_test")
    control = load_module("arclink_control.py", "arclink_control_dc_slash_test")
    conn = memory_db(control)

    transport = dc.FakeDiscordTransport()
    interaction = transport.make_slash_command(
        user_id="discord_user_1", channel_id="ch_1", message="/start"
    )
    result = dc.handle_discord_interaction(conn, interaction)
    expect(result is not None, "should have result")
    expect(result["type"] == 4, str(result["type"]))
    expect("ArcLink" in result["data"]["content"], result["data"]["content"])
    expect(result["action"] == "prompt_identity", result["action"])
    print("PASS test_discord_slash_command_through_bot_contract")


def test_discord_message_event_through_bot_contract() -> None:
    dc = load_module("arclink_discord.py", "arclink_discord_msg_test")
    control = load_module("arclink_control.py", "arclink_control_dc_msg_test")
    conn = memory_db(control)

    transport = dc.FakeDiscordTransport()
    msg = transport.make_message(user_id="discord_user_2", channel_id="ch_2", content="email test@example.test")

    # First start a session
    start = transport.make_message(user_id="discord_user_2", channel_id="ch_2", content="/start")
    dc.handle_discord_interaction(conn, start)

    result = dc.handle_discord_interaction(conn, msg)
    expect(result is not None, "should have result")
    expect(result["type"] == 4, str(result["type"]))
    expect("Email saved" in result["data"]["content"], result["data"]["content"])
    print("PASS test_discord_message_event_through_bot_contract")


def test_discord_full_onboarding_flow() -> None:
    dc = load_module("arclink_discord.py", "arclink_discord_flow_test")
    control = load_module("arclink_control.py", "arclink_control_dc_flow_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_dc_flow_test")
    conn = memory_db(control)
    stripe = adapters.FakeStripeClient()
    transport = dc.FakeDiscordTransport()

    steps = [
        ("/start", "prompt_identity"),
        ("email bot@discord.test", "prompt_name"),
        ("name Discord Bot", "prompt_plan"),
        ("plan starter", "prompt_checkout"),
    ]
    session_ids = set()
    for text, expected_action in steps:
        interaction = transport.make_message(user_id="42", channel_id="ch_1", content=text)
        result = dc.handle_discord_interaction(
            conn, interaction, stripe_client=stripe, base_domain="example.test"
        )
        expect(result is not None, f"no result for {text}")
        expect(result["action"] == expected_action, f"expected {expected_action}, got {result['action']}")
        session_ids.add(result["session_id"])

    expect(len(session_ids) == 1, f"session changed: {session_ids}")

    checkout = transport.make_message(user_id="42", channel_id="ch_1", content="checkout")
    result = dc.handle_discord_interaction(
        conn, checkout, stripe_client=stripe, base_domain="example.test"
    )
    expect(result["action"] == "open_checkout", result["action"])
    expect("stripe.test" in result["data"]["content"], result["data"]["content"])
    print("PASS test_discord_full_onboarding_flow")


def test_discord_verify_signature_test_mode() -> None:
    dc = load_module("arclink_discord.py", "arclink_discord_sig_test")
    expect(dc.verify_discord_signature("body", "sig", "ts", "test_public_key"), "test key should pass")
    expect(not dc.verify_discord_signature("body", "sig", "ts", "real_key_without_nacl"), "bad key should fail")
    print("PASS test_discord_verify_signature_test_mode")


def test_discord_webhook_handler() -> None:
    import json
    control = load_module("arclink_control.py", "arclink_control_dc_webhook_test")
    dc = load_module("arclink_discord.py", "arclink_discord_webhook_test")
    conn = memory_db(control)
    config = dc.DiscordConfig(bot_token="tok", app_id="app1", public_key="test_public_key", guild_id="g1")

    # PING
    ping_body = json.dumps({"type": 1})
    result = dc.handle_discord_webhook_request(
        conn, body=ping_body, signature="sig", timestamp="ts", config=config,
    )
    expect(result["type"] == 1, f"expected PONG, got {result}")

    # Slash command
    cmd_body = json.dumps({
        "type": 2,
        "channel_id": "ch_1",
        "member": {"user": {"id": "u_1"}},
        "data": {"name": "arclink", "options": [{"name": "message", "value": "/start"}]},
    })
    result = dc.handle_discord_webhook_request(
        conn, body=cmd_body, signature="sig", timestamp="ts", config=config,
    )
    expect(result["type"] == 4, f"expected type 4, got {result}")
    expect("ArcLink" in result["data"]["content"], result["data"]["content"])

    # Bad signature
    bad_config = dc.DiscordConfig(bot_token="tok", app_id="app1", public_key="bad_key", guild_id="g1")
    try:
        dc.handle_discord_webhook_request(
            conn, body=cmd_body, signature="sig", timestamp="ts", config=bad_config,
        )
    except dc.ArcLinkDiscordError as exc:
        expect("signature" in str(exc), str(exc))
    else:
        raise AssertionError("expected signature error")

    print("PASS test_discord_webhook_handler")


def test_discord_live_transport_requires_config() -> None:
    dc = load_module("arclink_discord.py", "arclink_discord_live_test")
    cfg = dc.DiscordConfig(bot_token="", app_id="", public_key="", guild_id="")
    try:
        dc.LiveDiscordTransport(cfg)
    except dc.ArcLinkDiscordError as exc:
        expect("DISCORD_BOT_TOKEN" in str(exc), str(exc))
    else:
        raise AssertionError("expected error without token")

    cfg_live = dc.DiscordConfig(bot_token="tok", app_id="app1", public_key="pk", guild_id="g1")
    transport = dc.LiveDiscordTransport(cfg_live)
    expect(transport.config.app_id == "app1", "config not set")
    print("PASS test_discord_live_transport_requires_config")


def test_discord_validate_live_readiness() -> None:
    dc = load_module("arclink_discord.py", "arclink_discord_readiness_test")
    full = dc.DiscordConfig.from_env({
        "DISCORD_BOT_TOKEN": "tok", "DISCORD_APP_ID": "app1", "DISCORD_PUBLIC_KEY": "pk",
    })
    expect(full.validate_live_readiness() == [], f"expected empty, got {full.validate_live_readiness()}")
    empty = dc.DiscordConfig.from_env({})
    missing = empty.validate_live_readiness()
    expect("DISCORD_BOT_TOKEN" in missing, str(missing))
    expect("DISCORD_APP_ID" in missing, str(missing))
    expect("DISCORD_PUBLIC_KEY" in missing, str(missing))
    print("PASS test_discord_validate_live_readiness")


def main() -> int:
    test_discord_config_from_env()
    test_discord_ping_pong()
    test_discord_slash_command_through_bot_contract()
    test_discord_message_event_through_bot_contract()
    test_discord_full_onboarding_flow()
    test_discord_verify_signature_test_mode()
    test_discord_webhook_handler()
    test_discord_live_transport_requires_config()
    test_discord_validate_live_readiness()
    print("PASS all 9 ArcLink Discord adapter tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
