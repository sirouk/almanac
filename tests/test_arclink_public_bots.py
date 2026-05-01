#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_module(filename: str, name: str):
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    path = PYTHON_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def memory_db(control):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    control.ensure_schema(conn)
    return conn


def test_public_bot_turns_share_onboarding_contract_and_open_fake_checkout() -> None:
    control = load_module("almanac_control.py", "almanac_control_public_bot_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_public_bot_test")
    bots = load_module("arclink_public_bots.py", "arclink_public_bots_test")
    conn = memory_db(control)
    stripe = adapters.FakeStripeClient()

    started = bots.handle_arclink_public_bot_turn(conn, channel="telegram", channel_identity="tg:42", text="/start")
    expect(started.action == "prompt_identity", str(started))
    emailed = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:42",
        text="email bot@example.test",
    )
    named = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:42",
        text="name Bot Buyer",
    )
    planned = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:42",
        text="plan starter",
    )
    checkout = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:42",
        text="checkout",
        stripe_client=stripe,
        base_domain="example.test",
    )
    expect({started.session_id, emailed.session_id, named.session_id, planned.session_id, checkout.session_id} == {started.session_id}, "session changed")
    expect(checkout.action == "open_checkout" and checkout.checkout_url.startswith("https://stripe.test/checkout/"), str(checkout))
    session = conn.execute(
        "SELECT channel, channel_identity, status, checkout_state, email_hint, display_name_hint FROM arclink_onboarding_sessions WHERE session_id = ?",
        (checkout.session_id,),
    ).fetchone()
    expect(session["channel"] == "telegram" and session["channel_identity"] == "tg:42", str(dict(session)))
    expect(session["status"] == "checkout_open" and session["checkout_state"] == "open", str(dict(session)))
    expect(session["email_hint"] == "bot@example.test" and session["display_name_hint"] == "Bot Buyer", str(dict(session)))
    events = {
        row["event_type"]
        for row in conn.execute("SELECT event_type FROM arclink_onboarding_events WHERE session_id = ?", (checkout.session_id,)).fetchall()
    }
    expect({"started", "question_answered", "checkout_opened"} <= events, str(events))
    print("PASS test_public_bot_turns_share_onboarding_contract_and_open_fake_checkout")


def test_public_bot_contract_rejects_wrong_channel_and_secret_metadata() -> None:
    control = load_module("almanac_control.py", "almanac_control_public_bot_secret_test")
    bots = load_module("arclink_public_bots.py", "arclink_public_bots_secret_test")
    conn = memory_db(control)
    try:
        bots.handle_arclink_public_bot_turn(conn, channel="web", channel_identity="web:1", text="/start")
    except bots.ArcLinkPublicBotError as exc:
        expect("unsupported" in str(exc), str(exc))
    else:
        raise AssertionError("expected unsupported channel to fail")

    try:
        bots.handle_arclink_public_bot_turn(
            conn,
            channel="discord",
            channel_identity="discord:1",
            text="/start",
            metadata={"discord_bot_token": "123456:abcdefghijklmnopqrstuvwxyz123456"},
        )
    except Exception as exc:
        expect("secret material" in str(exc), str(exc))
    else:
        raise AssertionError("expected public bot metadata secret to fail")
    stored = json.dumps([dict(row) for row in conn.execute("SELECT * FROM arclink_onboarding_sessions").fetchall()])
    expect("123456:" not in stored and "bot_token" not in stored, stored)
    print("PASS test_public_bot_contract_rejects_wrong_channel_and_secret_metadata")


def test_public_bot_turns_use_shared_onboarding_rate_limit() -> None:
    control = load_module("almanac_control.py", "almanac_control_public_bot_rate_limit_test")
    bots = load_module("arclink_public_bots.py", "arclink_public_bots_rate_limit_test")
    conn = memory_db(control)

    for _ in range(5):
        turn = bots.handle_arclink_public_bot_turn(
            conn,
            channel="discord",
            channel_identity="discord:limited",
            text="status",
        )
        expect(turn.channel == "discord", str(turn))
    try:
        bots.handle_arclink_public_bot_turn(
            conn,
            channel="discord",
            channel_identity="discord:limited",
            text="status",
        )
    except Exception as exc:
        expect("rate limit" in str(exc), str(exc))
    else:
        raise AssertionError("expected public bot shared rate limit to fail")
    rows = [
        dict(row)
        for row in conn.execute(
            "SELECT scope, subject FROM rate_limits WHERE subject = 'discord:limited' ORDER BY id"
        ).fetchall()
    ]
    expect(len(rows) == 5 and {row["scope"] for row in rows} == {"arclink:onboarding:discord"}, str(rows))
    print("PASS test_public_bot_turns_use_shared_onboarding_rate_limit")


def main() -> int:
    test_public_bot_turns_share_onboarding_contract_and_open_fake_checkout()
    test_public_bot_contract_rejects_wrong_channel_and_secret_metadata()
    test_public_bot_turns_use_shared_onboarding_rate_limit()
    print("PASS all 3 ArcLink public bot tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
