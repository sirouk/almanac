#!/usr/bin/env python3
from __future__ import annotations

from arclink_test_helpers import expect, load_module, memory_db


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
    print("PASS test_telegram_parse_update")


def test_telegram_handle_update_through_bot_contract() -> None:
    control = load_module("almanac_control.py", "almanac_control_tg_handle_test")
    tg = load_module("arclink_telegram.py", "arclink_telegram_handle_test")
    conn = memory_db(control)

    update = {
        "update_id": 1,
        "message": {"message_id": 1, "chat": {"id": 42}, "from": {"id": 99}, "text": "/start"},
    }
    result = tg.handle_telegram_update(conn, update)
    expect(result is not None, "should have result")
    expect(result["chat_id"] == "42", result["chat_id"])
    expect(result["action"] == "prompt_identity", result["action"])
    expect("ArcLink" in result["text"], result["text"])
    print("PASS test_telegram_handle_update_through_bot_contract")


def test_telegram_fake_transport_polling() -> None:
    control = load_module("almanac_control.py", "almanac_control_tg_poll_test")
    tg = load_module("arclink_telegram.py", "arclink_telegram_poll_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_tg_poll_test")
    conn = memory_db(control)
    transport = tg.FakeTelegramTransport()
    stripe = adapters.FakeStripeClient()

    transport.enqueue_update("42", "99", "/start")
    transport.enqueue_update("42", "99", "email test@example.test")

    cfg = tg.TelegramConfig(bot_token="", bot_username="test", webhook_url="", api_base="")
    tg.run_telegram_polling(
        conn, cfg,
        transport=transport,
        stripe_client=stripe,
        base_domain="example.test",
        max_iterations=2,
    )
    expect(len(transport.sent_messages) == 2, f"expected 2 replies, got {len(transport.sent_messages)}")
    expect("ArcLink" in transport.sent_messages[0]["text"], transport.sent_messages[0]["text"])
    expect("Email saved" in transport.sent_messages[1]["text"], transport.sent_messages[1]["text"])
    print("PASS test_telegram_fake_transport_polling")


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
    test_telegram_refuses_live_without_token()
    test_live_transport_requires_token()
    test_telegram_validate_live_readiness()
    print("PASS all 7 ArcLink Telegram adapter tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
