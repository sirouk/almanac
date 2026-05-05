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
    expect(started.action == "prompt_name", str(started))
    expect("Stripe collects your email" in started.reply, started.reply)
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
    expect({started.session_id, named.session_id, planned.session_id, checkout.session_id} == {started.session_id}, "session changed")
    expect(checkout.action == "open_checkout" and checkout.checkout_url.startswith("https://stripe.test/checkout/"), str(checkout))
    expect(checkout.buttons and checkout.buttons[0].label == "Hire My First Agent", str(checkout.buttons))
    session = conn.execute(
        "SELECT channel, channel_identity, status, checkout_state, email_hint, display_name_hint FROM arclink_onboarding_sessions WHERE session_id = ?",
        (checkout.session_id,),
    ).fetchone()
    expect(session["channel"] == "telegram" and session["channel_identity"] == "tg:42", str(dict(session)))
    expect(session["status"] == "checkout_open" and session["checkout_state"] == "open", str(dict(session)))
    expect(session["email_hint"] == "" and session["display_name_hint"] == "Bot Buyer", str(dict(session)))
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
    expect("pair_channel" in telegram_names, str(telegram))
    expect("connect-notion" not in telegram_names, str(telegram))
    expect("config-backup" not in telegram_names, str(telegram))

    discord = bots.arclink_public_bot_discord_application_commands()
    discord_names = {item["name"] for item in discord}
    expect({"arclink", "connect-notion", "config-backup", "pair-channel", "agents", "name", "plan"} <= discord_names, str(discord_names))
    expect("email" not in discord_names, str(discord_names))
    plan = next(item for item in discord if item["name"] == "plan")
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
    expect("once your first agent is awake aboard ArcLink" in turn.reply, turn.reply)
    count = conn.execute("SELECT COUNT(*) AS n FROM arclink_onboarding_sessions").fetchone()["n"]
    expect(count == 0, f"workflow command should not create an onboarding session, got {count}")
    print("PASS test_public_bot_workflow_commands_do_not_create_blank_onboarding_sessions")


def test_public_bot_agents_roster_add_agent_and_switch_are_account_aware() -> None:
    control = load_module("arclink_control.py", "arclink_control_public_bot_agents_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_public_bot_agents_test")
    bots = load_module("arclink_public_bots.py", "arclink_public_bots_agents_test")
    conn = memory_db(control)
    stripe = adapters.FakeStripeClient()

    unavailable = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:new",
        text="/agents",
    )
    expect(unavailable.action == "agents_unavailable", str(unavailable))
    expect(unavailable.buttons and unavailable.buttons[0].label == "Start Launch", str(unavailable.buttons))

    seeded = seed_active_public_bot_deployment(control, conn, prefix="arc-prime")
    roster = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:42",
        text="/agents",
    )
    expect(roster.action == "show_agents", str(roster))
    expect(any(button.command == "/add-agent" for button in roster.buttons), str(roster.buttons))

    add = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:42",
        text="/add-agent",
        stripe_client=stripe,
        additional_agent_price_id="price_additional_agent",
        base_domain="example.test",
    )
    expect(add.action == "open_add_agent_checkout", str(add))
    expect(add.checkout_url.startswith("https://stripe.test/checkout/"), str(add))
    checkout = stripe.checkout_sessions[add.checkout_url.rsplit("/", 1)[1]]
    expect(checkout["price_id"] == "price_additional_agent", str(checkout))
    add_session = conn.execute(
        "SELECT user_id, selected_plan_id, metadata_json FROM arclink_onboarding_sessions WHERE session_id = ?",
        (add.session_id,),
    ).fetchone()
    add_metadata = json.loads(add_session["metadata_json"])
    expect(add_session["user_id"] == seeded["user_id"], str(dict(add_session)))
    expect(add_session["selected_plan_id"] == "additional_agent", str(dict(add_session)))
    expect(add_metadata.get("active_deployment_id") == seeded["deployment_id"], str(add_metadata))

    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="arcdep_bob",
        user_id=seeded["user_id"],
        prefix="arc-bob",
        base_domain="control.example.ts.net",
        status="active",
        metadata={
            "agent_name": "Bob",
            "ingress_mode": "tailscale",
            "tailscale_dns_name": "control.example.ts.net",
            "tailscale_host_strategy": "path",
        },
    )
    switched = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:42",
        text="/agent-bob",
    )
    expect(switched.action == "switch_agent", str(switched))
    expect(switched.deployment_id == "arcdep_bob", str(switched))
    notion = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:42",
        text="/connect-notion",
    )
    expect(notion.action == "connect_notion", str(notion))
    expect("/u/arc-bob/notion/webhook" in notion.reply, notion.reply)
    print("PASS test_public_bot_agents_roster_add_agent_and_switch_are_account_aware")


def test_public_bot_pair_channel_links_account_across_telegram_and_discord() -> None:
    control = load_module("arclink_control.py", "arclink_control_public_bot_pair_test")
    bots = load_module("arclink_public_bots.py", "arclink_public_bots_pair_test")
    conn = memory_db(control)
    seeded = seed_active_public_bot_deployment(control, conn, prefix="arc-pair")

    opened = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:42",
        text="/pair-channel",
    )
    expect(opened.action == "pair_channel_code", str(opened))
    code_row = conn.execute(
        """
        SELECT code, status, source_session_id, source_channel, source_channel_identity
        FROM arclink_channel_pairing_codes
        WHERE source_session_id = ?
        """,
        (seeded["session_id"],),
    ).fetchone()
    expect(code_row is not None and code_row["status"] == "open", str(dict(code_row or {})))
    code = str(code_row["code"])
    expect(f"/pair-channel {code}" in opened.reply, opened.reply)

    claimed = bots.handle_arclink_public_bot_turn(
        conn,
        channel="discord",
        channel_identity="discord:99",
        text=f"/pair-channel {code}",
    )
    expect(claimed.action == "pair_channel_claimed", str(claimed))
    expect(claimed.user_id == seeded["user_id"], str(claimed))
    expect(claimed.deployment_id == seeded["deployment_id"], str(claimed))
    expect("Same ArcLink identity" in claimed.reply, claimed.reply)
    target = conn.execute(
        """
        SELECT session_id, user_id, deployment_id, metadata_json
        FROM arclink_onboarding_sessions
        WHERE channel = 'discord'
          AND channel_identity = 'discord:99'
        """
    ).fetchone()
    expect(target is not None, "expected paired Discord session")
    expect(target["user_id"] == seeded["user_id"], str(dict(target)))
    expect(target["deployment_id"] == seeded["deployment_id"], str(dict(target)))
    metadata = json.loads(target["metadata_json"])
    expect(metadata.get("paired_from_session_id") == seeded["session_id"], str(metadata))
    status = conn.execute("SELECT status, claimed_session_id FROM arclink_channel_pairing_codes WHERE code = ?", (code,)).fetchone()
    expect(status["status"] == "claimed" and status["claimed_session_id"] == target["session_id"], str(dict(status)))

    roster = bots.handle_arclink_public_bot_turn(
        conn,
        channel="discord",
        channel_identity="discord:99",
        text="/agents",
    )
    expect(roster.action == "show_agents", str(roster))
    expect("Your ArcLink crew" in roster.reply, roster.reply)
    notion = bots.handle_arclink_public_bot_turn(
        conn,
        channel="discord",
        channel_identity="discord:99",
        text="/connect-notion",
    )
    expect(notion.action == "connect_notion", str(notion))
    expect("/u/arc-pair/notion/webhook" in notion.reply, notion.reply)
    print("PASS test_public_bot_pair_channel_links_account_across_telegram_and_discord")


def main() -> int:
    test_public_bot_turns_share_onboarding_contract_and_open_fake_checkout()
    test_public_bot_action_catalog_has_real_platform_commands()
    test_public_bot_contract_rejects_wrong_channel_and_secret_metadata()
    test_public_bot_turns_use_shared_onboarding_rate_limit()
    test_public_bot_connect_notion_resolves_active_deployment_and_records_event()
    test_public_bot_config_backup_collects_private_repo_without_secret_leakage()
    test_public_bot_workflow_commands_do_not_create_blank_onboarding_sessions()
    test_public_bot_agents_roster_add_agent_and_switch_are_account_aware()
    test_public_bot_pair_channel_links_account_across_telegram_and_discord()
    test_public_bot_aboard_freeform_routes_to_helm_not_onboarding()
    test_public_bot_agent_label_uses_user_display_name()
    print("PASS all 11 ArcLink public bot tests")
    return 0


def test_public_bot_aboard_freeform_routes_to_helm_not_onboarding() -> None:
    """Routing law: once a user has a live pod, freeform messages and even
    /start re-triggers must NOT spit onboarding copy. They must hand the user
    a clean Helm pointer with the slash-command map for calling Raven back.
    """
    control = load_module("arclink_control.py", "arclink_control_public_bot_aboard_test")
    bots = load_module("arclink_public_bots.py", "arclink_public_bots_aboard_test")
    conn = memory_db(control)
    seed_active_public_bot_deployment(
        control, conn,
        channel="telegram", channel_identity="tg:99",
        prefix="arc-c7dbf98030b3",
    )

    # Freeform "hey there" from an aboard user must get the routing-law reply.
    freeform = bots.handle_arclink_public_bot_turn(conn, channel="telegram", channel_identity="tg:99", text="hey there")
    expect(freeform.action == "aboard_freeform", f"expected aboard_freeform got {freeform.action}")
    expect("onboarding only" in freeform.reply.lower(), freeform.reply)
    expect("Stripe collects" not in freeform.reply, "must not show onboarding copy to a paid user")
    expect("Send `/name" not in freeform.reply, "must not prompt for /name to a paid user")
    expect(any(b.label == "Open Helm" and b.url for b in freeform.buttons), "expected Open Helm URL button")
    expect(any(b.command == "/agents" for b in freeform.buttons), "expected Show My Crew button")

    # /start re-trigger from an aboard user gets the same routing-law reply,
    # NOT the onboarding "Stripe collects your email" prompt.
    restart = bots.handle_arclink_public_bot_turn(conn, channel="telegram", channel_identity="tg:99", text="/start")
    expect(restart.action == "aboard_freeform", f"expected aboard_freeform on /start re-trigger, got {restart.action}")
    expect("Stripe collects" not in restart.reply, "/start re-trigger leaked onboarding copy")

    # Slash commands still call Raven back: /agents must still show the crew.
    crew = bots.handle_arclink_public_bot_turn(conn, channel="telegram", channel_identity="tg:99", text="/agents")
    expect(crew.action == "show_agents", str(crew.action))

    # /help on an aboard user goes to the postlaunch control panel.
    helped = bots.handle_arclink_public_bot_turn(conn, channel="telegram", channel_identity="tg:99", text="/help")
    expect("Bridge is open" in helped.reply, helped.reply)

    print("PASS test_public_bot_aboard_freeform_routes_to_helm_not_onboarding")


def test_public_bot_agent_label_uses_user_display_name() -> None:
    """Agent labels must use the user's chosen display name, not the cryptic
    Title-Cased prefix hash. When a user has multiple pods sharing the same
    name, append a short prefix tail like '#69f2' so they're distinguishable.
    """
    control = load_module("arclink_control.py", "arclink_control_public_bot_label_test")
    bots = load_module("arclink_public_bots.py", "arclink_public_bots_label_test")
    conn = memory_db(control)

    # First pod with display_name_hint = "Chris"
    seed = seed_active_public_bot_deployment(
        control, conn,
        channel="telegram", channel_identity="tg:777",
        prefix="arc-c7dbf98030b3",
    )
    conn.execute(
        "UPDATE arclink_onboarding_sessions SET display_name_hint = 'Chris' WHERE deployment_id = ?",
        (seed["deployment_id"],),
    )
    conn.commit()

    crew = bots.handle_arclink_public_bot_turn(conn, channel="telegram", channel_identity="tg:777", text="/agents")
    expect("Chris" in crew.reply, f"expected user's name in roster, got: {crew.reply}")
    expect("C7Dbf98030B3" not in crew.reply, "must not show cryptic Title-Cased prefix hash as label")

    # Add a second pod under the same user → both should be distinguished
    # with the prefix tail like "#9805".
    second_dep = "arcdep_second"
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id=second_dep,
        user_id=seed["user_id"],
        prefix="arc-69f25807d6ab",
        base_domain="control.example.ts.net",
        status="active",
        metadata={"ingress_mode": "tailscale", "tailscale_dns_name": "control.example.ts.net"},
    )
    conn.execute(
        "INSERT INTO arclink_onboarding_sessions (session_id, channel, channel_identity, status, current_step, "
        "email_hint, display_name_hint, selected_plan_id, selected_model_id, user_id, deployment_id, checkout_state, metadata_json, created_at, updated_at) "
        "VALUES (?, 'web', ?, 'first_contacted', 'first_agent_contact', '', 'Chris', 'starter', 'moonshotai/Kimi-K2.6-TEE', ?, ?, 'paid', '{}', ?, ?)",
        (
            "onb_second", "web:second",
            seed["user_id"], second_dep,
            control.utc_now_iso(), control.utc_now_iso(),
        ),
    )
    conn.commit()

    crew2 = bots.handle_arclink_public_bot_turn(conn, channel="telegram", channel_identity="tg:777", text="/agents")
    # Both names appear; at least one carries a #tail to disambiguate.
    expect(crew2.reply.count("Chris") >= 2, f"expected two Chris entries, got: {crew2.reply}")
    expect("#" in crew2.reply, f"expected disambiguator suffix, got: {crew2.reply}")
    print("PASS test_public_bot_agent_label_uses_user_display_name")


if __name__ == "__main__":
    raise SystemExit(main())
