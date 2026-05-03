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


def seed_active_public_bot_deployment(
    control,
    conn,
    *,
    channel: str = "telegram",
    channel_identity: str = "tg:42",
    prefix: str = "arc-testpod",
    base_domain: str = "control.example.ts.net",
) -> dict[str, str]:
    user_id = f"arcusr_{prefix.replace('-', '_')}"
    deployment_id = f"arcdep_{prefix.replace('-', '_')}"
    session_id = f"onb_{prefix.replace('-', '_')}"
    now = control.utc_now_iso()
    control.upsert_arclink_user(
        conn,
        user_id=user_id,
        email=f"{prefix}@example.test",
        display_name="Bot Buyer",
        entitlement_state="paid",
    )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id=deployment_id,
        user_id=user_id,
        prefix=prefix,
        base_domain=base_domain,
        status="active",
        metadata={
            "ingress_mode": "tailscale",
            "tailscale_dns_name": base_domain,
            "tailscale_host_strategy": "path",
            "selected_plan_id": "starter",
        },
    )
    conn.execute(
        """
        INSERT INTO arclink_onboarding_sessions (
          session_id, channel, channel_identity, status, current_step,
          email_hint, display_name_hint, selected_plan_id, selected_model_id,
          user_id, deployment_id, checkout_state, metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, 'first_contacted', 'first_agent_contact', ?, ?, 'starter', 'moonshotai/Kimi-K2.6-TEE', ?, ?, 'paid', '{}', ?, ?)
        """,
        (
            session_id,
            channel,
            channel_identity,
            f"{prefix}@example.test",
            "Bot Buyer",
            user_id,
            deployment_id,
            now,
            now,
        ),
    )
    conn.commit()
    return {"user_id": user_id, "deployment_id": deployment_id, "session_id": session_id, "prefix": prefix}


def test_public_bot_turns_share_onboarding_contract_and_open_fake_checkout() -> None:
    control = load_module("arclink_control.py", "arclink_control_public_bot_test")
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
        text="/email bot@example.test",
    )
    named = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:42",
        text="/name Bot Buyer",
    )
    planned = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:42",
        text="/plan starter",
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


def test_public_bot_action_catalog_has_real_platform_commands() -> None:
    bots = load_module("arclink_public_bots.py", "arclink_public_bots_action_catalog_test")
    telegram = bots.arclink_public_bot_telegram_commands()
    telegram_names = {item["command"] for item in telegram}
    expect("connect_notion" in telegram_names, str(telegram))
    expect("config_backup" in telegram_names, str(telegram))
    expect("connect-notion" not in telegram_names, str(telegram))
    expect("config-backup" not in telegram_names, str(telegram))

    discord = bots.arclink_public_bot_discord_application_commands()
    discord_names = {item["name"] for item in discord}
    expect({"arclink", "connect-notion", "config-backup", "email", "name", "plan"} <= discord_names, str(discord_names))
    email = next(item for item in discord if item["name"] == "email")
    plan = next(item for item in discord if item["name"] == "plan")
    expect(email["options"][0]["name"] == "address", str(email))
    expect({choice["value"] for choice in plan["options"][0]["choices"]} == {"starter", "operator", "scale"}, str(plan))
    print("PASS test_public_bot_action_catalog_has_real_platform_commands")


def test_public_bot_contract_rejects_wrong_channel_and_secret_metadata() -> None:
    control = load_module("arclink_control.py", "arclink_control_public_bot_secret_test")
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
    control = load_module("arclink_control.py", "arclink_control_public_bot_rate_limit_test")
    bots = load_module("arclink_public_bots.py", "arclink_public_bots_rate_limit_test")
    conn = memory_db(control)

    for _ in range(20):
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
    expect(len(rows) == 20 and {row["scope"] for row in rows} == {"arclink:onboarding:discord"}, str(rows))
    print("PASS test_public_bot_turns_use_shared_onboarding_rate_limit")


def test_public_bot_connect_notion_resolves_active_deployment_and_records_event() -> None:
    control = load_module("arclink_control.py", "arclink_control_public_bot_notion_test")
    bots = load_module("arclink_public_bots.py", "arclink_public_bots_notion_test")
    conn = memory_db(control)
    seeded = seed_active_public_bot_deployment(control, conn, prefix="arc-notionpod")

    turn = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:42",
        text="/connect-notion",
    )
    expect(turn.action == "connect_notion", str(turn))
    expect(
        "https://control.example.ts.net/u/arc-notionpod/notion/webhook" in turn.reply,
        turn.reply,
    )
    ready = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:42",
        text="ready",
    )
    expect(ready.action == "connect_notion_ready", str(ready))
    stored = conn.execute(
        "SELECT metadata_json, current_step FROM arclink_onboarding_sessions WHERE session_id = ?",
        (seeded["session_id"],),
    ).fetchone()
    metadata = json.loads(stored["metadata_json"])
    expect("public_bot_workflow" not in metadata, str(metadata))
    expect(metadata.get("connect_notion_user_marked_ready_at"), str(metadata))
    events = [
        row["event_type"]
        for row in conn.execute(
            "SELECT event_type FROM arclink_events WHERE subject_id = ? ORDER BY created_at, event_id",
            (seeded["deployment_id"],),
        ).fetchall()
    ]
    expect("public_bot:connect_notion_requested" in events, str(events))
    expect("public_bot:connect_notion_ready" in events, str(events))
    print("PASS test_public_bot_connect_notion_resolves_active_deployment_and_records_event")


def test_public_bot_config_backup_collects_private_repo_without_secret_leakage() -> None:
    control = load_module("arclink_control.py", "arclink_control_public_bot_backup_test")
    bots = load_module("arclink_public_bots.py", "arclink_public_bots_backup_test")
    conn = memory_db(control)
    seeded = seed_active_public_bot_deployment(
        control,
        conn,
        channel="discord",
        channel_identity="discord:buyer",
        prefix="arc-backuppod",
    )

    opened = bots.handle_arclink_public_bot_turn(
        conn,
        channel="discord",
        channel_identity="discord:buyer",
        text="/config-backup",
    )
    expect(opened.action == "prompt_backup_repo", str(opened))
    expect("owner/repo" in opened.reply and "dedicated deploy key" in opened.reply, opened.reply)
    recorded = bots.handle_arclink_public_bot_turn(
        conn,
        channel="discord",
        channel_identity="discord:buyer",
        text="sirouk/arclink-agent-backup",
    )
    expect(recorded.action == "record_backup_repo", str(recorded))
    expect("sirouk/arclink-agent-backup/settings/keys" in recorded.reply, recorded.reply)
    stored = conn.execute(
        "SELECT metadata_json FROM arclink_onboarding_sessions WHERE session_id = ?",
        (seeded["session_id"],),
    ).fetchone()
    metadata = json.loads(stored["metadata_json"])
    expect(metadata.get("config_backup_owner_repo") == "sirouk/arclink-agent-backup", str(metadata))
    expect("public_bot_workflow" not in metadata, str(metadata))
    dumped = json.dumps([dict(row) for row in conn.execute("SELECT * FROM arclink_events").fetchall()])
    expect("secret" not in dumped.lower() and "token" not in dumped.lower(), dumped)
    print("PASS test_public_bot_config_backup_collects_private_repo_without_secret_leakage")


def test_public_bot_workflow_commands_do_not_create_blank_onboarding_sessions() -> None:
    control = load_module("arclink_control.py", "arclink_control_public_bot_no_session_test")
    bots = load_module("arclink_public_bots.py", "arclink_public_bots_no_session_test")
    conn = memory_db(control)

    turn = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:new",
        text="/connect-notion",
    )
    expect(turn.action == "connect_notion_unavailable", str(turn))
    expect("once your ArcLink pod exists" in turn.reply, turn.reply)
    count = conn.execute("SELECT COUNT(*) AS n FROM arclink_onboarding_sessions").fetchone()["n"]
    expect(count == 0, f"workflow command should not create an onboarding session, got {count}")
    print("PASS test_public_bot_workflow_commands_do_not_create_blank_onboarding_sessions")


def main() -> int:
    test_public_bot_turns_share_onboarding_contract_and_open_fake_checkout()
    test_public_bot_action_catalog_has_real_platform_commands()
    test_public_bot_contract_rejects_wrong_channel_and_secret_metadata()
    test_public_bot_turns_use_shared_onboarding_rate_limit()
    test_public_bot_connect_notion_resolves_active_deployment_and_records_event()
    test_public_bot_config_backup_collects_private_repo_without_secret_leakage()
    test_public_bot_workflow_commands_do_not_create_blank_onboarding_sessions()
    print("PASS all 7 ArcLink public bot tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
