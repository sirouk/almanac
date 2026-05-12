#!/usr/bin/env python3
from __future__ import annotations

import time

from arclink_test_helpers import expect, load_module, memory_db, seed_active_public_bot_deployment


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
    expect("Raven" in result["data"]["content"], result["data"]["content"])
    expect(result["action"] == "prompt_name", result["action"])
    expect(result["data"].get("components"), str(result["data"]))
    print("PASS test_discord_slash_command_through_bot_contract")


def test_discord_registered_action_command_options_parse_to_bot_contract() -> None:
    dc = load_module("arclink_discord.py", "arclink_discord_registered_action_parse_test")
    interaction = {
        "type": 2,
        "channel_id": "ch_1",
        "member": {"user": {"id": "u_1"}},
        "data": {"name": "name", "options": [{"name": "display_name", "value": "Buyer"}]},
    }
    parsed = dc.parse_discord_interaction(interaction)
    expect(parsed is not None, "expected parse result")
    expect(parsed["text"] == "name Buyer", str(parsed))

    plan = {
        "type": 2,
        "channel_id": "ch_1",
        "member": {"user": {"id": "u_1"}},
        "data": {"name": "plan", "options": [{"name": "tier", "value": "scale"}]},
    }
    parsed_plan = dc.parse_discord_interaction(plan)
    expect(parsed_plan["text"] == "plan scale", str(parsed_plan))
    pair = {
        "type": 2,
        "channel_id": "ch_1",
        "member": {"user": {"id": "u_1"}},
        "data": {"name": "pair-channel", "options": [{"name": "code", "value": "AB12CD"}]},
    }
    parsed_pair = dc.parse_discord_interaction(pair)
    expect(parsed_pair["text"] == "/pair-channel AB12CD", str(parsed_pair))
    link = {
        "type": 2,
        "channel_id": "ch_1",
        "member": {"user": {"id": "u_1"}},
        "data": {"name": "link-channel", "options": [{"name": "code", "value": "ZX98YU"}]},
    }
    parsed_link = dc.parse_discord_interaction(link)
    expect(parsed_link["text"] == "/link-channel ZX98YU", str(parsed_link))
    raven_name = {
        "type": 2,
        "channel_id": "ch_1",
        "member": {"user": {"id": "u_1"}},
        "data": {
            "name": "raven-name",
            "options": [
                {"name": "scope", "value": "account"},
                {"name": "display_name", "value": "Valkyrie"},
            ],
        },
    }
    parsed_raven_name = dc.parse_discord_interaction(raven_name)
    expect(parsed_raven_name["text"] == "/raven-name account Valkyrie", str(parsed_raven_name))
    agent = {
        "type": 2,
        "channel_id": "ch_1",
        "member": {"user": {"id": "u_1"}},
        "data": {"name": "agent", "options": [{"name": "message", "value": "/reload-mcp"}]},
    }
    parsed_agent = dc.parse_discord_interaction(agent)
    expect(parsed_agent["text"] == "/reload-mcp", str(parsed_agent))
    component = {
        "type": 3,
        "channel_id": "ch_1",
        "member": {"user": {"id": "u_1"}},
        "data": {"custom_id": "arclink:/plan sovereign"},
    }
    parsed_component = dc.parse_discord_interaction(component)
    expect(parsed_component["text"] == "/plan sovereign", str(parsed_component))
    print("PASS test_discord_registered_action_command_options_parse_to_bot_contract")


def test_discord_message_event_through_bot_contract() -> None:
    dc = load_module("arclink_discord.py", "arclink_discord_msg_test")
    control = load_module("arclink_control.py", "arclink_control_dc_msg_test")
    conn = memory_db(control)

    transport = dc.FakeDiscordTransport()
    msg = transport.make_message(user_id="discord_user_2", channel_id="ch_2", content="name Test Buyer")

    # First start a session
    start = transport.make_message(user_id="discord_user_2", channel_id="ch_2", content="/start")
    dc.handle_discord_interaction(conn, start)

    result = dc.handle_discord_interaction(conn, msg)
    expect(result is not None, "should have result")
    expect(result["type"] == 4, str(result["type"]))
    expect("Welcome aboard, Test Buyer" in result["data"]["content"], result["data"]["content"])
    expect("Founders - $149/month" in str(result["data"].get("components", [])), str(result["data"]))
    expect("Sovereign / Scale" in str(result["data"].get("components", [])), str(result["data"]))
    print("PASS test_discord_message_event_through_bot_contract")


def test_discord_status_reports_selected_agent_label() -> None:
    dc = load_module("arclink_discord.py", "arclink_discord_selected_agent_test")
    control = load_module("arclink_control.py", "arclink_control_dc_selected_agent_test")
    conn = memory_db(control)
    transport = dc.FakeDiscordTransport()
    seeded = seed_active_public_bot_deployment(
        control,
        conn,
        channel="discord",
        channel_identity="discord:discord_user_3",
        prefix="arc-dc-prime",
    )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="arcdep_dc_bob",
        user_id=seeded["user_id"],
        prefix="arc-dc-bob",
        base_domain="control.example.ts.net",
        status="active",
        metadata={
            "agent_name": "Bob",
            "ingress_mode": "tailscale",
            "tailscale_dns_name": "control.example.ts.net",
            "tailscale_host_strategy": "path",
        },
    )

    switched = dc.handle_discord_interaction(
        conn,
        transport.make_message(user_id="discord_user_3", channel_id="ch_3", content="/agent-bob"),
    )
    expect(switched is not None and switched["action"] == "switch_agent", str(switched))
    status = dc.handle_discord_interaction(
        conn,
        transport.make_message(user_id="discord_user_3", channel_id="ch_3", content="/status"),
    )
    expect(status is not None and status["action"] == "show_status", str(status))
    expect("Agent at the helm: Bob" in status["data"]["content"], status["data"]["content"])
    expect("onboarding only" not in status["data"]["content"].lower(), status["data"]["content"])
    agent_turn = dc.handle_discord_interaction(
        conn,
        transport.make_message(user_id="discord_user_3", channel_id="ch_3", content="/agent hello active agent"),
    )
    expect(agent_turn is not None and agent_turn["action"] == "agent_message_queued", str(agent_turn))
    expect(agent_turn["data"]["content"] == "Sent to your active agent.", str(agent_turn["data"]))
    expect("I am routing" not in agent_turn["data"]["content"], str(agent_turn["data"]))
    queued = conn.execute(
        "SELECT target_kind, target_id, channel_kind, message, extra_json FROM notification_outbox ORDER BY id DESC LIMIT 1"
    ).fetchone()
    expect(queued["target_kind"] == "public-agent-turn", str(dict(queued)))
    expect(queued["target_id"] == "discord:discord_user_3", str(dict(queued)))
    expect(queued["channel_kind"] == "discord", str(dict(queued)))
    expect(queued["message"] == "hello active agent", str(dict(queued)))
    import json

    extra = json.loads(queued["extra_json"])
    expect(extra["discord_channel_id"] == "ch_3", str(extra))
    expect(extra["discord_user_id"] == "discord_user_3", str(extra))

    arbitrary_agent_command = dc.handle_discord_interaction(
        conn,
        transport.make_message(user_id="discord_user_3", channel_id="ch_3", content="/yolo"),
    )
    expect(
        arbitrary_agent_command is not None and arbitrary_agent_command["action"] == "agent_message_queued",
        str(arbitrary_agent_command),
    )
    expect(arbitrary_agent_command["data"]["content"] == "Sent to your active agent.", str(arbitrary_agent_command["data"]))
    expect("I am routing" not in arbitrary_agent_command["data"]["content"], str(arbitrary_agent_command["data"]))
    arbitrary_row = conn.execute(
        "SELECT target_kind, target_id, channel_kind, message, extra_json FROM notification_outbox ORDER BY id DESC LIMIT 1"
    ).fetchone()
    expect(arbitrary_row["target_kind"] == "public-agent-turn", str(dict(arbitrary_row)))
    expect(arbitrary_row["target_id"] == "discord:discord_user_3", str(dict(arbitrary_row)))
    expect(arbitrary_row["channel_kind"] == "discord", str(dict(arbitrary_row)))
    expect(arbitrary_row["message"] == "/yolo", str(dict(arbitrary_row)))
    arbitrary_extra = json.loads(arbitrary_row["extra_json"])
    expect(arbitrary_extra["discord_channel_id"] == "ch_3", str(arbitrary_extra))
    expect(arbitrary_extra["discord_user_id"] == "discord_user_3", str(arbitrary_extra))
    expect(arbitrary_extra["source_kind"] == "agent_command", str(arbitrary_extra))
    print("PASS test_discord_status_reports_selected_agent_label")


def test_discord_full_onboarding_flow() -> None:
    dc = load_module("arclink_discord.py", "arclink_discord_flow_test")
    control = load_module("arclink_control.py", "arclink_control_dc_flow_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_dc_flow_test")
    conn = memory_db(control)
    stripe = adapters.FakeStripeClient()
    transport = dc.FakeDiscordTransport()

    steps = [
        ("/start", "prompt_name"),
        ("name Discord Bot", "prompt_package"),
        ("plan sovereign", "open_checkout"),
    ]
    session_ids = set()
    for text, expected_action in steps:
        interaction = transport.make_message(user_id="42", channel_id="ch_1", content=text)
        result = dc.handle_discord_interaction(
            conn, interaction, stripe_client=stripe, base_domain="example.test"
        )
        expect(result is not None, f"no result for {text}")
        expect(result["action"] == expected_action, f"expected {expected_action}, got {result['action']}")
        if expected_action == "open_checkout":
            expect(result["data"].get("components"), str(result["data"]))
            expect(result["data"]["components"][0]["components"][0]["url"].startswith("https://stripe.test"), str(result["data"]))
        session_ids.add(result["session_id"])

    expect(len(session_ids) == 1, f"session changed: {session_ids}")

    checkout = transport.make_message(user_id="42", channel_id="ch_1", content="checkout")
    result = dc.handle_discord_interaction(
        conn, checkout, stripe_client=stripe, base_domain="example.test"
    )
    expect(result["action"] == "open_checkout", result["action"])
    expect(result["data"].get("components"), str(result["data"]))
    expect(result["data"]["components"][0]["components"][0]["url"].startswith("https://stripe.test"), str(result["data"]))
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
    timestamp = str(int(time.time()))

    # PING
    ping_body = json.dumps({"id": "int_ping", "type": 1})
    result = dc.handle_discord_webhook_request(
        conn, body=ping_body, signature="sig", timestamp=timestamp, config=config,
    )
    expect(result["type"] == 1, f"expected PONG, got {result}")

    # Slash command
    cmd_body = json.dumps({
        "id": "int_cmd",
        "type": 2,
        "channel_id": "ch_1",
        "member": {"user": {"id": "u_1"}},
        "data": {"name": "arclink", "options": [{"name": "message", "value": "/start"}]},
    })
    result = dc.handle_discord_webhook_request(
        conn, body=cmd_body, signature="sig", timestamp=timestamp, config=config,
    )
    expect(result["type"] == 4, f"expected type 4, got {result}")
    expect("Raven" in result["data"]["content"], result["data"]["content"])

    # Bad signature
    bad_config = dc.DiscordConfig(bot_token="tok", app_id="app1", public_key="bad_key", guild_id="g1")
    try:
        dc.handle_discord_webhook_request(
            conn, body=json.dumps({"id": "int_bad_sig", "type": 1}), signature="sig", timestamp=timestamp, config=bad_config,
        )
    except dc.ArcLinkDiscordError as exc:
        expect("signature" in str(exc), str(exc))
    else:
        raise AssertionError("expected signature error")

    try:
        dc.handle_discord_webhook_request(
            conn, body=json.dumps({"id": "int_stale", "type": 1}), signature="sig", timestamp="1", config=config,
        )
    except dc.ArcLinkDiscordError as exc:
        expect("stale" in str(exc), str(exc))
    else:
        raise AssertionError("expected stale timestamp error")

    try:
        dc.handle_discord_webhook_request(
            conn, body=cmd_body, signature="sig", timestamp=timestamp, config=config,
        )
    except dc.ArcLinkDiscordError as exc:
        expect("duplicate" in str(exc), str(exc))
    else:
        raise AssertionError("expected duplicate interaction error")

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


def test_discord_registers_public_bot_actions() -> None:
    dc = load_module("arclink_discord.py", "arclink_discord_register_actions_test")
    calls: list[dict[str, object]] = []

    def fake_request(path, *, bot_token, method="GET", payload=None, timeout=30):
        calls.append({
            "path": path,
            "bot_token": bot_token,
            "method": method,
            "payload": payload,
            "timeout": timeout,
        })
        return [{"name": item["name"]} for item in payload]

    dc._request_any_json = fake_request
    cfg = dc.DiscordConfig(bot_token="tok", app_id="app123", public_key="pk", guild_id="")
    result = dc.register_arclink_public_discord_commands(cfg)

    expect(len(calls) == 1, str(calls))
    expect(calls[0]["path"] == "/applications/app123/commands", str(calls[0]))
    expect(calls[0]["method"] == "PUT", str(calls[0]))
    names = {item["name"] for item in calls[0]["payload"]}
    expect({"arclink", "agent", "connect-notion", "config-backup", "pair-channel", "link-channel", "raven-name", "agents", "name", "plan"} <= names, str(names))
    expect("email" not in names, str(names))
    expect(result["scope"] == "global", str(result))
    expect(result["result_count"] == len(calls[0]["payload"]), str(result))
    print("PASS test_discord_registers_public_bot_actions")


def test_discord_credential_ack_updates_original_component_message() -> None:
    dc = load_module("arclink_discord.py", "arclink_discord_credential_ack_update_test")
    control = load_module("arclink_control.py", "arclink_control_dc_credential_ack_update_test")
    conn = memory_db(control)
    seeded = seed_active_public_bot_deployment(
        control,
        conn,
        channel="discord",
        channel_identity="discord:discord_user_cred",
        prefix="arc-dc-cred",
    )

    result = dc.handle_discord_interaction(
        conn,
        {
            "type": 3,
            "channel_id": "ch_cred",
            "user": {"id": "discord_user_cred", "username": "buyer"},
            "message": {"id": "msg_secret_handoff"},
            "data": {"custom_id": "arclink:/credentials-stored"},
        },
    )

    expect(result is not None and result["action"] == "credentials_stored", str(result))
    expect(result["type"] == 7, str(result))
    expect("Password:" not in result["data"]["content"], str(result["data"]))
    expect("removed" in result["data"]["content"].lower(), str(result["data"]))
    labels = [
        component.get("label")
        for row in result["data"].get("components", [])
        for component in row.get("components", [])
    ]
    expect("Wire Notion" in labels and "Check Status" in labels, str(labels))
    row = conn.execute(
        """
        SELECT status, acknowledged_at, removed_at
        FROM arclink_credential_handoffs
        WHERE deployment_id = ?
          AND credential_kind = 'dashboard_password'
        """,
        (seeded["deployment_id"],),
    ).fetchone()
    expect(row["status"] == "removed" and bool(row["acknowledged_at"]) and bool(row["removed_at"]), str(dict(row)))
    print("PASS test_discord_credential_ack_updates_original_component_message")


def main() -> int:
    test_discord_config_from_env()
    test_discord_ping_pong()
    test_discord_slash_command_through_bot_contract()
    test_discord_registered_action_command_options_parse_to_bot_contract()
    test_discord_message_event_through_bot_contract()
    test_discord_status_reports_selected_agent_label()
    test_discord_full_onboarding_flow()
    test_discord_verify_signature_test_mode()
    test_discord_webhook_handler()
    test_discord_live_transport_requires_config()
    test_discord_validate_live_readiness()
    test_discord_registers_public_bot_actions()
    test_discord_credential_ack_updates_original_component_message()
    print("PASS all 13 ArcLink Discord adapter tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
