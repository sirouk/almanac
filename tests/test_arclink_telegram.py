#!/usr/bin/env python3
from __future__ import annotations

from arclink_test_helpers import expect, load_module, memory_db, seed_active_public_bot_deployment


def test_telegram_config_from_env() -> None:
    tg = load_module("arclink_telegram.py", "arclink_telegram_config_test")
    cfg = tg.TelegramConfig.from_env({"TELEGRAM_BOT_TOKEN": "123:abc", "TELEGRAM_BOT_USERNAME": "testbot"})
    expect(cfg.is_live, "should be live with token")
    expect(cfg.bot_token == "123:abc", cfg.bot_token)
    empty = tg.TelegramConfig.from_env({})
    expect(not empty.is_live, "should not be live without token")
    print("PASS test_telegram_config_from_env")


def test_telegram_parse_update() -> None:
    tg = load_module("arclink_telegram.py", "arclink_telegram_parse_test")
    update = {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "chat": {"id": 42},
            "from": {"id": 99},
            "text": "/start",
        },
    }
    parsed = tg.parse_telegram_update(update)
    expect(parsed is not None, "should parse")
    expect(parsed["chat_id"] == "42", parsed["chat_id"])
    expect(parsed["user_id"] == "99", parsed["user_id"])
    expect(parsed["text"] == "/start", parsed["text"])

    empty = tg.parse_telegram_update({"update_id": 2})
    expect(empty is None, "should be None for non-message")
    callback = tg.parse_telegram_update({
        "update_id": 3,
        "callback_query": {
            "id": "cb_1",
            "from": {"id": 99},
            "message": {"chat": {"id": 42}},
            "data": "arclink:/plan sovereign",
        },
    })
    expect(callback is not None, "should parse callback")
    expect(callback["text"] == "/plan sovereign", str(callback))
    print("PASS test_telegram_parse_update")


def test_telegram_handle_update_through_bot_contract() -> None:
    control = load_module("arclink_control.py", "arclink_control_tg_handle_test")
    tg = load_module("arclink_telegram.py", "arclink_telegram_handle_test")
    conn = memory_db(control)

    update = {
        "update_id": 1,
        "message": {"message_id": 1, "chat": {"id": 42}, "from": {"id": 99}, "text": "/start"},
    }
    result = tg.handle_telegram_update(conn, update)
    expect(result is not None, "should have result")
    expect(result["chat_id"] == "42", result["chat_id"])
    expect(result["action"] == "prompt_name", result["action"])
    expect("Raven" in result["text"], result["text"])
    expect(result.get("reply_markup"), str(result))
    print("PASS test_telegram_handle_update_through_bot_contract")


def test_telegram_fake_transport_polling() -> None:
    control = load_module("arclink_control.py", "arclink_control_tg_poll_test")
    tg = load_module("arclink_telegram.py", "arclink_telegram_poll_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_tg_poll_test")
    conn = memory_db(control)
    transport = tg.FakeTelegramTransport()
    stripe = adapters.FakeStripeClient()

    transport.enqueue_update("42", "99", "/start")
    transport.enqueue_update("42", "99", "name Test Buyer")

    cfg = tg.TelegramConfig(bot_token="", bot_username="test", webhook_url="", api_base="")
    tg.run_telegram_polling(
        conn, cfg,
        transport=transport,
        stripe_client=stripe,
        base_domain="example.test",
        max_iterations=2,
    )
    expect(len(transport.sent_messages) == 2, f"expected 2 replies, got {len(transport.sent_messages)}")
    expect("Raven" in transport.sent_messages[0]["text"], transport.sent_messages[0]["text"])
    expect("Welcome aboard, Test Buyer" in transport.sent_messages[1]["text"], transport.sent_messages[1]["text"])
    expect("Founders - $149/month" in str(transport.sent_messages[1].get("reply_markup", {})), str(transport.sent_messages[1]))
    expect("Sovereign / Scale" in str(transport.sent_messages[1].get("reply_markup", {})), str(transport.sent_messages[1]))
    expect("reply_markup" in transport.sent_messages[1], str(transport.sent_messages[1]))
    print("PASS test_telegram_fake_transport_polling")


def test_telegram_registers_public_bot_actions() -> None:
    tg = load_module("arclink_telegram.py", "arclink_telegram_register_actions_test")
    calls: list[dict[str, object]] = []
    tg.telegram_set_my_commands = lambda **kwargs: calls.append(kwargs) or {"result": True}

    result = tg.register_arclink_public_telegram_commands("123:abc")

    expect(len(calls) == 2, str(calls))
    command_sets = [{item["command"] for item in call["commands"]} for call in calls]
    expect("connect_notion" in command_sets[0], str(command_sets))
    expect("config_backup" in command_sets[0], str(command_sets))
    expect("link_channel" in command_sets[0], str(command_sets))
    expect("raven_name" in command_sets[0], str(command_sets))
    expect("agents" in command_sets[0], str(command_sets))
    expect("agent" in command_sets[0], str(command_sets))
    expect("email" not in command_sets[0], str(command_sets))
    expect("connect-notion" not in command_sets[0], str(command_sets))
    expect(calls[0].get("scope") is None, str(calls[0]))
    expect(calls[1].get("scope") == {"type": "all_private_chats"}, str(calls[1]))
    expect("agents" in result["registered"] and "plan" in result["registered"], str(result))
    print("PASS test_telegram_registers_public_bot_actions")


def test_telegram_active_chat_scope_adds_agent_commands() -> None:
    control = load_module("arclink_control.py", "arclink_control_tg_active_scope_test")
    tg = load_module("arclink_telegram.py", "arclink_telegram_active_scope_test")
    conn = memory_db(control)
    seed_active_public_bot_deployment(
        control,
        conn,
        channel="telegram",
        channel_identity="tg:99",
        prefix="arc-tg-scope",
    )
    calls: list[dict[str, object]] = []
    tg.telegram_set_my_commands = lambda **kwargs: calls.append(kwargs) or {"result": True}

    result = tg.handle_telegram_update(
        conn,
        {"update_id": 20, "message": {"message_id": 9, "chat": {"id": 42}, "from": {"id": 99}, "text": "/raven agents"}},
        telegram_bot_token="123:abc",
    )

    expect(result is not None and result["action"] == "show_agents", str(result))
    expect(calls, "expected per-chat command scope refresh")
    expect(calls[0]["scope"] == {"type": "chat", "chat_id": 42}, str(calls[0]))
    names = {item["command"] for item in calls[0]["commands"]}
    expect("raven" in names, str(names))
    expect("agents" in names and "status" in names and "help" in names, str(names))
    expect("model" in names, str(names))
    expect("provider" in names, str(names))
    expect("reload_mcp" in names, str(names))
    expect("credentials" not in names and "connect_notion" not in names, str(names))
    expect("update" not in names, "unsafe direct Hermes update must stay hidden")
    expect(len(names) == len(calls[0]["commands"]), "command names must be unique")
    expect(len(names) <= 100, "Telegram command limit exceeded")
    expect(result.get("command_scope", {}).get("include_agent_commands") is True, str(result.get("command_scope")))
    expect(result.get("command_scope", {}).get("raven_command") == "raven", str(result.get("command_scope")))

    agent_agents = tg.handle_telegram_update(
        conn,
        {"update_id": 21, "message": {"message_id": 10, "chat": {"id": 42}, "from": {"id": 99}, "text": "/agents"}},
        telegram_bot_token="123:abc",
    )
    expect(agent_agents is not None and agent_agents["action"] == "agent_message_queued", str(agent_agents))

    before = len(calls)
    skipped = tg.refresh_arclink_public_telegram_chat_commands(
        bot_token="123:abc",
        chat_id="42",
        include_agent_commands=True,
    )
    expect(len(calls) == before, "unchanged command scope should be cached")
    expect(skipped.get("skipped") is True and skipped.get("reason") == "unchanged", str(skipped))
    print("PASS test_telegram_active_chat_scope_adds_agent_commands")


def test_telegram_status_reports_selected_agent_label() -> None:
    control = load_module("arclink_control.py", "arclink_control_tg_selected_agent_test")
    tg = load_module("arclink_telegram.py", "arclink_telegram_selected_agent_test")
    conn = memory_db(control)
    seeded = seed_active_public_bot_deployment(
        control,
        conn,
        channel="telegram",
        channel_identity="tg:99",
        prefix="arc-tg-prime",
    )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="arcdep_tg_bob",
        user_id=seeded["user_id"],
        prefix="arc-tg-bob",
        base_domain="control.example.ts.net",
        status="active",
        metadata={
            "agent_name": "Bob",
            "ingress_mode": "tailscale",
            "tailscale_dns_name": "control.example.ts.net",
            "tailscale_host_strategy": "path",
        },
    )

    switched = tg.handle_telegram_update(
        conn,
        {"update_id": 10, "message": {"message_id": 1, "chat": {"id": 42}, "from": {"id": 99}, "text": "/agent-bob"}},
    )
    expect(switched is not None and switched["action"] == "switch_agent", str(switched))
    status = tg.handle_telegram_update(
        conn,
        {"update_id": 11, "message": {"message_id": 2, "chat": {"id": 42}, "from": {"id": 99}, "text": "/raven status"}},
    )
    expect(status is not None and status["action"] == "show_status", str(status))
    expect("Agent at the helm: Bob" in status["text"], status["text"])
    expect("onboarding only" not in status["text"].lower(), status["text"])
    print("PASS test_telegram_status_reports_selected_agent_label")


def test_telegram_webhook_registration_allows_buttons() -> None:
    tg = load_module("arclink_telegram.py", "arclink_telegram_webhook_register_test")
    calls: list[dict[str, object]] = []
    tg.telegram_set_webhook = lambda **kwargs: calls.append(kwargs) or {"result": True}

    result = tg.ensure_arclink_public_telegram_webhook("123:abc", "https://example.test/api/v1/webhooks/telegram")

    expect(calls, "expected setWebhook call")
    expect(calls[0]["webhook_url"] == "https://example.test/api/v1/webhooks/telegram", str(calls))
    expect("callback_query" in calls[0]["allowed_updates"], str(calls))
    expect(result["allowed_updates"] == ["message", "edited_message", "callback_query"], str(result))
    skipped = tg.ensure_arclink_public_telegram_webhook("123:abc", "")
    expect(skipped.get("skipped") is True, str(skipped))
    print("PASS test_telegram_webhook_registration_allows_buttons")


def test_telegram_refuses_live_without_token() -> None:
    tg = load_module("arclink_telegram.py", "arclink_telegram_refuse_test")
    cfg = tg.TelegramConfig(bot_token="", bot_username="", webhook_url="", api_base="")
    try:
        tg.run_telegram_polling(None, cfg, max_iterations=1)
    except tg.ArcLinkTelegramError as exc:
        expect("TELEGRAM_BOT_TOKEN" in str(exc), str(exc))
    else:
        raise AssertionError("expected error without token")
    print("PASS test_telegram_refuses_live_without_token")


def test_live_transport_requires_token() -> None:
    tg = load_module("arclink_telegram.py", "arclink_telegram_live_test")
    cfg = tg.TelegramConfig(bot_token="", bot_username="", webhook_url="", api_base="")
    try:
        tg.LiveTelegramTransport(cfg)
    except tg.ArcLinkTelegramError as exc:
        expect("TELEGRAM_BOT_TOKEN" in str(exc), str(exc))
    else:
        raise AssertionError("expected error without token")

    # With token, construction succeeds
    cfg_live = tg.TelegramConfig(bot_token="123:abc", bot_username="test", webhook_url="", api_base="http://localhost")
    transport = tg.LiveTelegramTransport(cfg_live)
    expect(transport.config.bot_token == "123:abc", "token not set")
    print("PASS test_live_transport_requires_token")


def test_telegram_validate_live_readiness() -> None:
    tg = load_module("arclink_telegram.py", "arclink_telegram_readiness_test")
    full = tg.TelegramConfig.from_env({"TELEGRAM_BOT_TOKEN": "123:abc", "TELEGRAM_BOT_USERNAME": "testbot"})
    expect(full.validate_live_readiness() == [], f"expected empty, got {full.validate_live_readiness()}")
    missing_token = tg.TelegramConfig.from_env({})
    missing = missing_token.validate_live_readiness()
    expect("TELEGRAM_BOT_TOKEN" in missing, str(missing))
    expect("TELEGRAM_BOT_USERNAME" in missing, str(missing))
    print("PASS test_telegram_validate_live_readiness")


def main() -> int:
    test_telegram_config_from_env()
    test_telegram_parse_update()
    test_telegram_handle_update_through_bot_contract()
    test_telegram_fake_transport_polling()
    test_telegram_registers_public_bot_actions()
    test_telegram_active_chat_scope_adds_agent_commands()
    test_telegram_status_reports_selected_agent_label()
    test_telegram_webhook_registration_allows_buttons()
    test_telegram_refuses_live_without_token()
    test_live_transport_requires_token()
    test_telegram_validate_live_readiness()
    print("PASS all 11 ArcLink Telegram adapter tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
