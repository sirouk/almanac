#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
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
            "selected_plan_id": "sovereign",
        },
    )
    conn.execute(
        """
        INSERT INTO arclink_onboarding_sessions (
          session_id, channel, channel_identity, status, current_step,
          email_hint, display_name_hint, selected_plan_id, selected_model_id,
          user_id, deployment_id, checkout_state, metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, 'first_contacted', 'first_agent_contact', ?, ?, 'sovereign', 'moonshotai/Kimi-K2.6-TEE', ?, ?, 'paid', '{}', ?, ?)
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


def seed_credential_handoffs(
    control,
    conn,
    seeded: dict[str, str],
    *,
    status: str = "removed",
) -> None:
    now = control.utc_now_iso()
    removed_at = now if status == "removed" else ""
    acknowledged_at = now if status == "removed" else ""
    for kind, display_name in (
        ("dashboard_password", "Dashboard password"),
        ("chutes_api_key", "Chutes provider key"),
    ):
        conn.execute(
            """
            INSERT OR REPLACE INTO arclink_credential_handoffs (
              handoff_id, user_id, deployment_id, credential_kind, display_name,
              secret_ref, delivery_hint, status, revealed_at, acknowledged_at,
              removed_at, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', ?, ?)
            """,
            (
                f"cred_{seeded['deployment_id']}_{kind}",
                seeded["user_id"],
                seeded["deployment_id"],
                kind,
                display_name,
                f"secret://arclink/test/{seeded['deployment_id']}/{kind}",
                "Copy into a password manager, then acknowledge.",
                status,
                now,
                acknowledged_at,
                removed_at,
                now,
                now,
            ),
        )
    conn.commit()


def test_public_bot_turns_share_onboarding_contract_and_open_fake_checkout() -> None:
    control = load_module("arclink_control.py", "arclink_control_public_bot_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_public_bot_test")
    bots = load_module("arclink_public_bots.py", "arclink_public_bots_test")
    conn = memory_db(control)
    stripe = adapters.FakeStripeClient()

    started = bots.handle_arclink_public_bot_turn(conn, channel="telegram", channel_identity="tg:42", text="/start")
    expect(started.action == "prompt_name", str(started))
    expect("Founders, Sovereign, or Scale" in started.reply, started.reply)
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
        text="/plan sovereign",
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
    checkout_session = stripe.checkout_sessions[checkout.checkout_url.rsplit("/", 1)[1]]
    expect(f"/checkout/success?session={checkout.session_id}" in checkout_session["success_url"], str(checkout_session))
    expect(f"/checkout/cancel?session={checkout.session_id}" in checkout_session["cancel_url"], str(checkout_session))
    expect(checkout.buttons and checkout.buttons[0].label == "Hire Sovereign - $199/month", str(checkout.buttons))
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


def test_public_bot_cancel_closes_open_checkout_without_creating_new_session() -> None:
    control = load_module("arclink_control.py", "arclink_control_public_bot_cancel_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_public_bot_cancel_test")
    bots = load_module("arclink_public_bots.py", "arclink_public_bots_cancel_test")
    conn = memory_db(control)
    stripe = adapters.FakeStripeClient()

    bots.handle_arclink_public_bot_turn(conn, channel="telegram", channel_identity="tg:cancel", text="/start")
    bots.handle_arclink_public_bot_turn(conn, channel="telegram", channel_identity="tg:cancel", text="/plan sovereign")
    checkout = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:cancel",
        text="/checkout",
        stripe_client=stripe,
    )
    cancelled = bots.handle_arclink_public_bot_turn(conn, channel="telegram", channel_identity="tg:cancel", text="/cancel")
    expect(cancelled.action == "onboarding_cancelled", str(cancelled))
    expect(cancelled.session_id == checkout.session_id, str(cancelled))
    row = conn.execute(
        "SELECT status, checkout_state FROM arclink_onboarding_sessions WHERE session_id = ?",
        (checkout.session_id,),
    ).fetchone()
    expect(row["status"] == "payment_cancelled" and row["checkout_state"] == "cancelled", str(dict(row)))
    events = [
        str(item["event_type"])
        for item in conn.execute(
            "SELECT event_type FROM arclink_onboarding_events WHERE session_id = ?",
            (checkout.session_id,),
        ).fetchall()
    ]
    expect("payment_cancelled" in events, str(events))
    empty_cancel = bots.handle_arclink_public_bot_turn(conn, channel="telegram", channel_identity="tg:none", text="/cancel")
    expect(empty_cancel.action == "nothing_to_cancel", str(empty_cancel))
    count = conn.execute("SELECT COUNT(*) AS n FROM arclink_onboarding_sessions WHERE channel_identity = 'tg:none'").fetchone()["n"]
    expect(count == 0, f"cancel without an active setup must not create a blank session, found {count}")
    print("PASS test_public_bot_cancel_closes_open_checkout_without_creating_new_session")


def test_public_bot_scale_checkout_uses_scale_price_and_reserves_three_agents() -> None:
    control = load_module("arclink_control.py", "arclink_control_public_bot_scale_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_public_bot_scale_test")
    bots = load_module("arclink_public_bots.py", "arclink_public_bots_scale_test")
    conn = memory_db(control)
    stripe = adapters.FakeStripeClient()

    bots.handle_arclink_public_bot_turn(
        conn, channel="telegram", channel_identity="tg:scale", text="/start", display_name_hint="Scale Buyer",
    )
    named = bots.handle_arclink_public_bot_turn(
        conn, channel="telegram", channel_identity="tg:scale", text="/name",
    )
    expect(named.action == "prompt_name_input", str(named.action))
    package = bots.handle_arclink_public_bot_turn(
        conn, channel="telegram", channel_identity="tg:scale", text="Scale Buyer",
    )
    expect([b.label for b in package.buttons] == ["Founders - $149/month", "Sovereign / Scale"], str(package.buttons))
    standard = bots.handle_arclink_public_bot_turn(
        conn, channel="telegram", channel_identity="tg:scale", text="/packages standard",
    )
    expect([b.label for b in standard.buttons] == ["Sovereign - $199/month", "Scale - $275/month"], str(standard.buttons))
    planned = bots.handle_arclink_public_bot_turn(
        conn, channel="telegram", channel_identity="tg:scale", text="/plan scale",
    )
    expect("Scale is locked" in planned.reply, planned.reply)
    expect("Agents onboard ArcLink with Federation" in planned.reply, planned.reply)

    checkout = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:scale",
        text="/checkout",
        stripe_client=stripe,
        price_id="price_sovereign_test",
        scale_price_id="price_scale_test",
        base_domain="example.test",
    )
    expect(checkout.action == "open_checkout", str(checkout.action))
    checkout_session = stripe.checkout_sessions[checkout.checkout_url.rsplit("/", 1)[1]]
    expect(checkout_session["price_id"] == "price_scale_test", str(checkout_session))
    expect(checkout_session["line_items"] == [{"price": "price_scale_test", "quantity": 1}], str(checkout_session))
    session = conn.execute(
        "SELECT user_id, deployment_id, selected_plan_id FROM arclink_onboarding_sessions WHERE session_id = ?",
        (checkout.session_id,),
    ).fetchone()
    expect(session["selected_plan_id"] == "scale", str(dict(session)))
    deployments = conn.execute(
        "SELECT deployment_id, metadata_json FROM arclink_deployments WHERE user_id = ? ORDER BY deployment_id",
        (session["user_id"],),
    ).fetchall()
    expect(len(deployments) == 3, f"expected three scale deployments, got {len(deployments)}")
    indexes = sorted(json.loads(row["metadata_json"]).get("bundle_agent_index") for row in deployments)
    expect(indexes == [1, 2, 3], str(indexes))
    print("PASS test_public_bot_scale_checkout_uses_scale_price_and_reserves_three_agents")


def test_public_bot_founders_checkout_uses_founders_price() -> None:
    control = load_module("arclink_control.py", "arclink_control_public_bot_founders_test")
    adapters = load_module("arclink_adapters.py", "arclink_adapters_public_bot_founders_test")
    bots = load_module("arclink_public_bots.py", "arclink_public_bots_founders_test")
    conn = memory_db(control)
    stripe = adapters.FakeStripeClient()

    bots.handle_arclink_public_bot_turn(conn, channel="telegram", channel_identity="tg:founders", text="/start", display_name_hint="Founder")
    planned = bots.handle_arclink_public_bot_turn(conn, channel="telegram", channel_identity="tg:founders", text="/plan founders")
    expect("Limited 100 Founders is locked" in planned.reply, planned.reply)
    expect([b.label for b in planned.buttons] == ["Hire Founders - $149/month", "Change Package"], str(planned.buttons))

    checkout = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:founders",
        text="/checkout",
        stripe_client=stripe,
        price_id="price_sovereign_test",
        founders_price_id="price_founders_test",
        scale_price_id="price_scale_test",
        base_domain="example.test",
    )
    checkout_session = stripe.checkout_sessions[checkout.checkout_url.rsplit("/", 1)[1]]
    expect(checkout_session["price_id"] == "price_founders_test", str(checkout_session))
    expect(checkout.buttons[0].label == "Hire Founders - $149/month", str(checkout.buttons))
    session = conn.execute(
        "SELECT selected_plan_id FROM arclink_onboarding_sessions WHERE session_id = ?",
        (checkout.session_id,),
    ).fetchone()
    expect(session["selected_plan_id"] == "founders", str(dict(session)))
    print("PASS test_public_bot_founders_checkout_uses_founders_price")


def test_public_bot_action_catalog_has_real_platform_commands() -> None:
    bots = load_module("arclink_public_bots.py", "arclink_public_bots_action_catalog_test")
    telegram = bots.arclink_public_bot_telegram_commands()
    telegram_names = {item["command"] for item in telegram}
    expect("connect_notion" in telegram_names, str(telegram))
    expect("config_backup" in telegram_names, str(telegram))
    expect("pair_channel" in telegram_names, str(telegram))
    expect("link_channel" in telegram_names, str(telegram))
    expect("raven_name" in telegram_names, str(telegram))
    expect("upgrade_hermes" in telegram_names, str(telegram))
    expect("agent" in telegram_names, str(telegram))
    expect("connect-notion" not in telegram_names, str(telegram))
    expect("config-backup" not in telegram_names, str(telegram))
    expect("upgrade-hermes" not in telegram_names, str(telegram))

    discord = bots.arclink_public_bot_discord_application_commands()
    discord_names = {item["name"] for item in discord}
    expect({"arclink", "agent", "connect-notion", "config-backup", "pair-channel", "link-channel", "raven-name", "upgrade-hermes", "agents", "name", "plan"} <= discord_names, str(discord_names))
    expect("email" not in discord_names, str(discord_names))
    plan = next(item for item in discord if item["name"] == "plan")
    expect({choice["value"] for choice in plan["options"][0]["choices"]} == {"founders", "sovereign", "scale"}, str(plan))
    agent = next(item for item in discord if item["name"] == "agent")
    expect(agent["options"][0]["name"] == "message" and agent["options"][0]["required"] is True, str(agent))
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
    seed_credential_handoffs(control, conn, seeded)

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
    expect("does not verify the Notion integration" in turn.reply, turn.reply)
    expect("ready for dashboard verification" in turn.reply, turn.reply)
    ready = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:42",
        text="ready",
    )
    expect(ready.action == "connect_notion_ready", str(ready))
    expect("not a completed Notion verification yet" in ready.reply, ready.reply)
    stored = conn.execute(
        "SELECT metadata_json, current_step FROM arclink_onboarding_sessions WHERE session_id = ?",
        (seeded["session_id"],),
    ).fetchone()
    metadata = json.loads(stored["metadata_json"])
    expect("public_bot_workflow" not in metadata, str(metadata))
    expect(metadata.get("connect_notion_user_marked_ready_at"), str(metadata))
    expect(metadata.get("connect_notion_public_status") == "ready_for_dashboard_verification", str(metadata))
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


def test_public_bot_connect_notion_waits_for_credential_acknowledgement() -> None:
    control = load_module("arclink_control.py", "arclink_control_public_bot_notion_gate_test")
    bots = load_module("arclink_public_bots.py", "arclink_public_bots_notion_gate_test")
    conn = memory_db(control)
    seeded = seed_active_public_bot_deployment(control, conn, prefix="arc-notiongate")

    blocked = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:42",
        text="/connect-notion",
    )
    expect(blocked.action == "connect_notion_credentials_required", str(blocked))
    expect("credential handoff closed" in blocked.reply, blocked.reply)
    expect("/credentials" in blocked.reply and "confirm storage" in blocked.reply, blocked.reply)
    expect("No Notion tokens or API keys belong in chat" in blocked.reply, blocked.reply)

    seed_credential_handoffs(control, conn, seeded, status="available")
    still_blocked = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:42",
        text="/connect-notion",
    )
    expect(still_blocked.action == "connect_notion_credentials_required", str(still_blocked))
    expect("Dashboard password" in still_blocked.reply and "Chutes provider key" in still_blocked.reply, still_blocked.reply)

    seed_credential_handoffs(control, conn, seeded, status="removed")
    opened = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:42",
        text="/connect-notion",
    )
    expect(opened.action == "connect_notion", str(opened))
    expect("brokered shared-root Notion SSOT rail" in opened.reply, opened.reply)
    expect("does not verify the Notion integration" in opened.reply, opened.reply)
    expect("Email sharing alone is not treated as proof" in opened.reply, opened.reply)
    print("PASS test_public_bot_connect_notion_waits_for_credential_acknowledgement")


def test_public_bot_credentials_reveal_and_ack_dashboard_password() -> None:
    control = load_module("arclink_control.py", "arclink_control_public_bot_credentials_test")
    bots = load_module("arclink_public_bots.py", "arclink_public_bots_credentials_test")
    conn = memory_db(control)
    seeded = seed_active_public_bot_deployment(control, conn, prefix="arc-credpod")
    secret_ref = f"secret://arclink/dashboard/{seeded['deployment_id']}/password"
    old_secret_store = os.environ.get("ARCLINK_SECRET_STORE_DIR")
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["ARCLINK_SECRET_STORE_DIR"] = tmp
        secret_dir = Path(tmp) / seeded["deployment_id"]
        secret_dir.mkdir(parents=True)
        secret_path = secret_dir / f"{hashlib.sha256(secret_ref.encode('utf-8')).hexdigest()}.secret"
        secret_path.write_text("arc_public_bot_dashboard_password\n", encoding="utf-8")
        try:
            revealed = bots.handle_arclink_public_bot_turn(
                conn,
                channel="telegram",
                channel_identity="tg:42",
                text="/credentials",
            )
            expect(revealed.action == "credentials_revealed", str(revealed))
            expect("arc_public_bot_dashboard_password" in revealed.reply, revealed.reply)
            expect("I Stored It" in [button.label for button in revealed.buttons], str(revealed.buttons))
            row = conn.execute(
                """
                SELECT status, revealed_at, removed_at
                FROM arclink_credential_handoffs
                WHERE deployment_id = ?
                  AND credential_kind = 'dashboard_password'
                """,
                (seeded["deployment_id"],),
            ).fetchone()
            expect(row["status"] == "available" and bool(row["revealed_at"]) and not row["removed_at"], str(dict(row)))

            stored = bots.handle_arclink_public_bot_turn(
                conn,
                channel="telegram",
                channel_identity="tg:42",
                text="/credentials-stored",
            )
            expect(stored.action == "credentials_stored", str(stored))
            expect("removed" in stored.reply.lower(), stored.reply)
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
        finally:
            if old_secret_store is None:
                os.environ.pop("ARCLINK_SECRET_STORE_DIR", None)
            else:
                os.environ["ARCLINK_SECRET_STORE_DIR"] = old_secret_store
    print("PASS test_public_bot_credentials_reveal_and_ack_dashboard_password")


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
    expect("does not mint, install, or verify the deploy key" in opened.reply, opened.reply)
    recorded = bots.handle_arclink_public_bot_turn(
        conn,
        channel="discord",
        channel_identity="discord:buyer",
        text="sirouk/arclink-agent-backup",
    )
    expect(recorded.action == "record_backup_repo", str(recorded))
    expect("sirouk/arclink-agent-backup/settings/keys" in recorded.reply, recorded.reply)
    expect("pending key setup" in recorded.reply and "backup is not active yet" in recorded.reply, recorded.reply)
    stored = conn.execute(
        "SELECT metadata_json FROM arclink_onboarding_sessions WHERE session_id = ?",
        (seeded["session_id"],),
    ).fetchone()
    metadata = json.loads(stored["metadata_json"])
    expect(metadata.get("config_backup_owner_repo") == "sirouk/arclink-agent-backup", str(metadata))
    expect(metadata.get("config_backup_public_status") == "repo_recorded_pending_key_setup", str(metadata))
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

    upgrade = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:new",
        text="/upgrade_hermes",
    )
    expect(upgrade.action == "upgrade_hermes_unavailable", str(upgrade))
    expect("unmanaged `hermes update`" in upgrade.reply, upgrade.reply)
    count = conn.execute("SELECT COUNT(*) AS n FROM arclink_onboarding_sessions").fetchone()["n"]
    expect(count == 0, f"upgrade command should not create an onboarding session, got {count}")

    direct_update = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:new",
        text="/update",
    )
    expect(direct_update.action == "upgrade_hermes_unavailable", str(direct_update))
    expect("unmanaged `hermes update`" in direct_update.reply, direct_update.reply)
    count = conn.execute("SELECT COUNT(*) AS n FROM arclink_onboarding_sessions").fetchone()["n"]
    expect(count == 0, f"direct Hermes update command should not create an onboarding session, got {count}")
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
    expect(unavailable.buttons and unavailable.buttons[0].label == "Take Me Aboard", str(unavailable.buttons))

    seeded = seed_active_public_bot_deployment(control, conn, prefix="arc-prime")
    roster = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:42",
        text="/agents",
    )
    expect(roster.action == "show_agents", str(roster))
    expect(any(button.command == "/add-agent" for button in roster.buttons), str(roster.buttons))

    upgrade = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:42",
        text="/upgrade-hermes",
    )
    expect(upgrade.action == "upgrade_hermes_controlled", str(upgrade))
    expect("ArcLink" in upgrade.reply and "`hermes update`" in upgrade.reply, upgrade.reply)
    expect(any(button.command == "/status" for button in upgrade.buttons), str(upgrade.buttons))

    direct_update = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:42",
        text="/update",
    )
    expect(direct_update.action == "upgrade_hermes_controlled", str(direct_update))
    expect("ArcLink" in direct_update.reply and "`hermes update`" in direct_update.reply, direct_update.reply)

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
    expect(f"kind=additional_agent&session={add.session_id}" in checkout["success_url"], str(checkout))
    expect(f"kind=additional_agent&session={add.session_id}" in checkout["cancel_url"], str(checkout))
    add_session = conn.execute(
        "SELECT user_id, selected_plan_id, metadata_json FROM arclink_onboarding_sessions WHERE session_id = ?",
        (add.session_id,),
    ).fetchone()
    add_metadata = json.loads(add_session["metadata_json"])
    expect(add_session["user_id"] == seeded["user_id"], str(dict(add_session)))
    expect(add_session["selected_plan_id"] == "agent_expansion_sovereign", str(dict(add_session)))
    expect(add_metadata["agent_expansion_plan_id"] == "sovereign", str(add_metadata))
    expect(add_metadata["agent_expansion_monthly_price"] == "$99/month", str(add_metadata))
    expect(add_metadata.get("active_deployment_id") == seeded["deployment_id"], str(add_metadata))

    scale_seed = seed_active_public_bot_deployment(
        control,
        conn,
        channel="telegram",
        channel_identity="tg:scale_add",
        prefix="arc-scale-add",
    )
    conn.execute(
        "UPDATE arclink_deployments SET metadata_json = ? WHERE deployment_id = ?",
        (
            json.dumps({
                "ingress_mode": "tailscale",
                "tailscale_dns_name": "control.example.ts.net",
                "tailscale_host_strategy": "path",
                "selected_plan_id": "scale",
            }, sort_keys=True),
            scale_seed["deployment_id"],
        ),
    )
    conn.execute(
        "UPDATE arclink_onboarding_sessions SET selected_plan_id = ? WHERE session_id = ?",
        ("scale", scale_seed["session_id"]),
    )
    conn.commit()
    scale_add = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:scale_add",
        text="/add-agent",
        stripe_client=stripe,
        sovereign_agent_expansion_price_id="price_sovereign_expansion",
        scale_agent_expansion_price_id="price_scale_expansion",
        base_domain="example.test",
    )
    expect(scale_add.action == "open_add_agent_checkout", str(scale_add))
    scale_checkout = stripe.checkout_sessions[scale_add.checkout_url.rsplit("/", 1)[1]]
    expect(scale_checkout["price_id"] == "price_scale_expansion", str(scale_checkout))
    expect("$79/month" in scale_add.reply, scale_add.reply)

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
    seed_credential_handoffs(control, conn, {"user_id": seeded["user_id"], "deployment_id": "arcdep_bob"})
    switched = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:42",
        text="/agent-bob",
    )
    expect(switched.action == "switch_agent", str(switched))
    expect(switched.deployment_id == "arcdep_bob", str(switched))
    status = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:42",
        text="/status",
    )
    expect(status.action == "show_status", str(status))
    expect(status.deployment_id == "arcdep_bob", str(status))
    expect("Agent at the helm: Bob" in status.reply, status.reply)
    expect("onboarding only" not in status.reply.lower(), status.reply)
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
    seed_credential_handoffs(control, conn, seeded)

    opened = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:42",
        text="/link-channel",
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
    expect(f"/link-channel {code}" in opened.reply, opened.reply)

    claimed = bots.handle_arclink_public_bot_turn(
        conn,
        channel="discord",
        channel_identity="discord:99",
        text=f"/link_channel {code}",
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


def test_public_bot_pair_channel_refuses_existing_other_account() -> None:
    control = load_module("arclink_control.py", "arclink_control_public_bot_pair_mismatch_test")
    bots = load_module("arclink_public_bots.py", "arclink_public_bots_pair_mismatch_test")
    conn = memory_db(control)
    account_a = seed_active_public_bot_deployment(
        control,
        conn,
        channel="telegram",
        channel_identity="tg:account-a",
        prefix="arc-account-a",
    )
    account_b = seed_active_public_bot_deployment(
        control,
        conn,
        channel="discord",
        channel_identity="discord:account-b",
        prefix="arc-account-b",
    )

    opened = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:account-a",
        text="/link-channel",
    )
    code = str(conn.execute(
        "SELECT code FROM arclink_channel_pairing_codes WHERE source_session_id = ?",
        (account_a["session_id"],),
    ).fetchone()["code"])

    refused = bots.handle_arclink_public_bot_turn(
        conn,
        channel="discord",
        channel_identity="discord:account-b",
        text=f"/link-channel {code}",
    )
    expect(opened.action == "pair_channel_code", str(opened))
    expect(refused.action == "pair_channel_account_mismatch", str(refused))
    expect(refused.user_id == account_b["user_id"], str(refused))
    expect(refused.deployment_id == account_b["deployment_id"], str(refused))
    row = conn.execute("SELECT status, claimed_session_id FROM arclink_channel_pairing_codes WHERE code = ?", (code,)).fetchone()
    expect(row["status"] == "open" and row["claimed_session_id"] == "", str(dict(row)))
    target = conn.execute(
        """
        SELECT user_id, deployment_id
        FROM arclink_onboarding_sessions
        WHERE channel = 'discord'
          AND channel_identity = 'discord:account-b'
        """
    ).fetchone()
    expect(target["user_id"] == account_b["user_id"], str(dict(target)))
    expect(target["deployment_id"] == account_b["deployment_id"], str(dict(target)))

    roster = bots.handle_arclink_public_bot_turn(
        conn,
        channel="discord",
        channel_identity="discord:account-b",
        text="/agents",
    )
    expect(roster.user_id == account_b["user_id"], str(roster))
    expect(roster.deployment_id == account_b["deployment_id"], str(roster))
    expect(account_a["prefix"] not in roster.reply, roster.reply)
    print("PASS test_public_bot_pair_channel_refuses_existing_other_account")


def test_public_bot_share_approval_buttons_are_owner_scoped() -> None:
    control = load_module("arclink_control.py", "arclink_control_public_bot_share_buttons_test")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_public_bot_share_buttons_test")
    bots = load_module("arclink_public_bots.py", "arclink_public_bots_share_buttons_test")
    conn = memory_db(control)
    owner = seed_active_public_bot_deployment(
        control,
        conn,
        channel="telegram",
        channel_identity="tg:share-owner",
        prefix="arc-share-owner",
    )
    recipient = seed_active_public_bot_deployment(
        control,
        conn,
        channel="discord",
        channel_identity="discord:share-recipient",
        prefix="arc-share-recipient",
    )
    owner_session = api.create_arclink_user_session(conn, user_id=owner["user_id"], session_id="usess_bot_share_owner")

    result = api.create_user_share_grant_api(
        conn,
        session_id=owner_session["session_id"],
        session_token=owner_session["session_token"],
        csrf_token=owner_session["csrf_token"],
        recipient_user_id=recipient["user_id"],
        resource_kind="drive",
        resource_root="vault",
        resource_path="/Projects/brief.md",
        display_name="Project Brief",
    )
    expect(result.status == 201, str(result))
    grant = result.payload["grant"]
    grant_id = grant["grant_id"]
    expect(result.payload["owner_notification"]["queued"] is True, str(result.payload))
    notification = conn.execute(
        """
        SELECT target_kind, target_id, channel_kind, message, extra_json
        FROM notification_outbox
        WHERE target_kind = 'public-bot-user'
          AND channel_kind = 'telegram'
          AND target_id = 'tg:share-owner'
        """
    ).fetchone()
    expect(notification is not None, "expected Raven owner approval notification")
    extra = json.loads(notification["extra_json"])
    buttons = extra["telegram_reply_markup"]["inline_keyboard"][0]
    callbacks = {button["text"]: button["callback_data"] for button in buttons}
    expect(callbacks["Approve"] == f"arclink:/raven approve {grant_id}", str(callbacks))
    expect(callbacks["Deny"] == f"arclink:/raven deny {grant_id}", str(callbacks))

    refused = bots.handle_arclink_public_bot_turn(
        conn,
        channel="discord",
        channel_identity="discord:share-recipient",
        text=f"/share-approve {grant_id}",
    )
    expect(refused.action == "share_grant_not_found", str(refused))
    status = conn.execute("SELECT status FROM arclink_share_grants WHERE grant_id = ?", (grant_id,)).fetchone()["status"]
    expect(status == "pending_owner_approval", str(status))

    approved = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:share-owner",
        text=f"/share-approve {grant_id}",
    )
    expect(approved.action == "share_grant_approved", str(approved))
    status = conn.execute("SELECT status FROM arclink_share_grants WHERE grant_id = ?", (grant_id,)).fetchone()["status"]
    expect(status == "approved", str(status))

    second = api.create_user_share_grant_api(
        conn,
        session_id=owner_session["session_id"],
        session_token=owner_session["session_token"],
        csrf_token=owner_session["csrf_token"],
        recipient_user_id=recipient["user_id"],
        resource_kind="drive",
        resource_root="vault",
        resource_path="/Projects/closed.md",
        display_name="Closed Brief",
    )
    second_grant = second.payload["grant"]["grant_id"]
    denied = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:share-owner",
        text=f"/share-deny {second_grant}",
    )
    expect(denied.action == "share_grant_denied", str(denied))
    denied_status = conn.execute("SELECT status FROM arclink_share_grants WHERE grant_id = ?", (second_grant,)).fetchone()["status"]
    expect(denied_status == "denied", str(denied_status))
    audit_actions = {
        row["action"]
        for row in conn.execute("SELECT action FROM arclink_audit_log WHERE target_kind = 'share_grant'").fetchall()
    }
    expect({"share_grant_requested", "share_grant_approved", "share_grant_denied"} <= audit_actions, str(audit_actions))
    print("PASS test_public_bot_share_approval_buttons_are_owner_scoped")


def test_public_bot_ignores_cross_user_active_deployment_metadata() -> None:
    control = load_module("arclink_control.py", "arclink_control_public_bot_active_scope_test")
    bots = load_module("arclink_public_bots.py", "arclink_public_bots_active_scope_test")
    conn = memory_db(control)
    account_a = seed_active_public_bot_deployment(
        control,
        conn,
        channel="telegram",
        channel_identity="tg:active-a",
        prefix="arc-active-a",
    )
    account_b = seed_active_public_bot_deployment(
        control,
        conn,
        channel="telegram",
        channel_identity="tg:active-b",
        prefix="arc-active-b",
    )
    conn.execute(
        """
        UPDATE arclink_onboarding_sessions
        SET metadata_json = ?
        WHERE session_id = ?
        """,
        (
            json.dumps({"active_deployment_id": account_a["deployment_id"]}, sort_keys=True),
            account_b["session_id"],
        ),
    )
    conn.commit()

    roster = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:active-b",
        text="/agents",
    )
    expect(roster.action == "show_agents", str(roster))
    expect(roster.user_id == account_b["user_id"], str(roster))
    expect(roster.deployment_id == account_b["deployment_id"], str(roster))
    expect(account_a["prefix"] not in roster.reply, roster.reply)
    print("PASS test_public_bot_ignores_cross_user_active_deployment_metadata")


def test_public_bot_withholds_unpublished_tailnet_app_urls() -> None:
    control = load_module("arclink_control.py", "arclink_control_public_bots_tailnet_unavailable_test")
    bots = load_module("arclink_public_bots.py", "arclink_public_bots_tailnet_unavailable_test")
    conn = memory_db(control)
    seeded = seed_active_public_bot_deployment(
        control,
        conn,
        channel="telegram",
        channel_identity="tg:unavailable",
        prefix="arc-unavailable",
        base_domain="worker.example.ts.net",
    )
    conn.execute(
        """
        UPDATE arclink_deployments
        SET metadata_json = ?
        WHERE deployment_id = ?
        """,
        (
            json.dumps(
                {
                    "ingress_mode": "tailscale",
                    "tailscale_dns_name": "worker.example.ts.net",
                    "tailscale_host_strategy": "path",
                    "tailnet_service_ports": {"hermes": 8443, "files": 8444, "code": 8445},
                    "tailnet_app_publication": {"status": "unavailable", "failed_roles": ["files"]},
                },
                sort_keys=True,
            ),
            seeded["deployment_id"],
        ),
    )
    conn.commit()
    deployment = dict(conn.execute("SELECT * FROM arclink_deployments WHERE deployment_id = ?", (seeded["deployment_id"],)).fetchone())
    access = bots._deployment_access(deployment)
    expect(access == {"dashboard": "https://worker.example.ts.net/u/arc-unavailable"}, str(access))
    print("PASS test_public_bot_withholds_unpublished_tailnet_app_urls")


def test_public_bot_raven_display_name_is_channel_and_account_scoped() -> None:
    control = load_module("arclink_control.py", "arclink_control_public_bot_raven_name_test")
    bots = load_module("arclink_public_bots.py", "arclink_public_bots_raven_name_test")
    conn = memory_db(control)

    channel_set = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:alias",
        text="/raven_name channel Starling",
    )
    expect(channel_set.action == "raven_name_channel_set", str(channel_set))
    expect(channel_set.bot_display_name == "Starling", str(channel_set))
    started = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:alias",
        text="/start",
    )
    expect("Starling here. ArcLink is in range." in started.reply, started.reply)

    try:
        bots.handle_arclink_public_bot_turn(
            conn,
            channel="telegram",
            channel_identity="tg:alias",
            text="/raven_name channel @everyone",
        )
    except bots.ArcLinkPublicBotError as exc:
        expect("Raven display name" in str(exc), str(exc))
    else:
        raise AssertionError("expected unsafe Raven display name to fail closed")

    seeded = seed_active_public_bot_deployment(
        control,
        conn,
        channel="telegram",
        channel_identity="tg:raven-owner",
        prefix="arc-raven-name",
        base_domain="control.example.ts.net",
    )
    now = control.utc_now_iso()
    conn.execute(
        """
        INSERT INTO arclink_onboarding_sessions (
          session_id, channel, channel_identity, status, current_step,
          email_hint, display_name_hint, selected_plan_id, selected_model_id,
          user_id, deployment_id, checkout_state, metadata_json, created_at, updated_at
        ) VALUES (?, 'discord', 'discord:raven-owner', 'first_contacted', 'first_agent_contact',
          '', 'Bot Buyer', 'sovereign', 'moonshotai/Kimi-K2.6-TEE', ?, ?, 'paid', '{}', ?, ?)
        """,
        ("onb_raven_name_discord", seeded["user_id"], seeded["deployment_id"], now, now),
    )
    conn.commit()

    account_set = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:raven-owner",
        text="/raven_name account Valkyrie",
    )
    expect(account_set.action == "raven_name_account_set", str(account_set))
    discord_freeform = bots.handle_arclink_public_bot_turn(
        conn,
        channel="discord",
        channel_identity="discord:raven-owner",
        text="hello",
    )
    expect(discord_freeform.action == "agent_message_queued", str(discord_freeform.action))
    expect("I am routing" not in discord_freeform.reply, discord_freeform.reply)

    channel_override = bots.handle_arclink_public_bot_turn(
        conn,
        channel="discord",
        channel_identity="discord:raven-owner",
        text="/raven-name channel Starling",
    )
    expect(channel_override.action == "raven_name_channel_set", str(channel_override))
    discord_override = bots.handle_arclink_public_bot_turn(
        conn,
        channel="discord",
        channel_identity="discord:raven-owner",
        text="hello again",
    )
    expect(discord_override.action == "agent_message_queued", str(discord_override.action))
    expect("I am routing" not in discord_override.reply, discord_override.reply)
    telegram_still_account = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:raven-owner",
        text="hello again",
    )
    expect(telegram_still_account.action == "agent_message_queued", str(telegram_still_account.action))
    expect("I am routing" not in telegram_still_account.reply, telegram_still_account.reply)

    channel_reset = bots.handle_arclink_public_bot_turn(
        conn,
        channel="discord",
        channel_identity="discord:raven-owner",
        text="/raven_name reset",
    )
    expect(channel_reset.action == "raven_name_channel_reset", str(channel_reset))
    discord_after_channel_reset = bots.handle_arclink_public_bot_turn(
        conn,
        channel="discord",
        channel_identity="discord:raven-owner",
        text="hello after channel reset",
    )
    expect(discord_after_channel_reset.action == "agent_message_queued", str(discord_after_channel_reset.action))
    expect("I am routing" not in discord_after_channel_reset.reply, discord_after_channel_reset.reply)

    account_reset = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:raven-owner",
        text="/raven_name reset-account",
    )
    expect(account_reset.action == "raven_name_account_reset", str(account_reset))
    telegram_after_account_reset = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:raven-owner",
        text="hello after account reset",
    )
    expect(telegram_after_account_reset.action == "agent_message_queued", str(telegram_after_account_reset.action))
    expect("I am routing" not in telegram_after_account_reset.reply, telegram_after_account_reset.reply)

    roster = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:raven-owner",
        text="/agents",
    )
    expect("Bot Buyer" in roster.reply, roster.reply)
    expect("Valkyrie" not in roster.reply and "Starling" not in roster.reply, roster.reply)

    unattached_reset = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:unlinked-account-reset",
        text="/raven_name reset-account",
    )
    expect(unattached_reset.action == "raven_name_account_unavailable", str(unattached_reset))
    empty_user_rows = conn.execute(
        "SELECT COUNT(*) AS n FROM arclink_public_bot_identity WHERE scope_kind = 'user' AND user_id = ''"
    ).fetchone()["n"]
    expect(empty_user_rows == 0, f"empty user account-scope row collision: {empty_user_rows}")
    try:
        bots._store_raven_display_name(conn, scope_kind="user", user_id="", display_name="Bad")
    except bots.ArcLinkPublicBotError as exc:
        expect("user id" in str(exc), str(exc))
    else:
        raise AssertionError("expected empty account-scope Raven name store to fail")
    print("PASS test_public_bot_raven_display_name_is_channel_and_account_scoped")


def main() -> int:
    test_public_bot_turns_share_onboarding_contract_and_open_fake_checkout()
    test_public_bot_cancel_closes_open_checkout_without_creating_new_session()
    test_public_bot_scale_checkout_uses_scale_price_and_reserves_three_agents()
    test_public_bot_action_catalog_has_real_platform_commands()
    test_public_bot_contract_rejects_wrong_channel_and_secret_metadata()
    test_public_bot_turns_use_shared_onboarding_rate_limit()
    test_public_bot_connect_notion_resolves_active_deployment_and_records_event()
    test_public_bot_connect_notion_waits_for_credential_acknowledgement()
    test_public_bot_credentials_reveal_and_ack_dashboard_password()
    test_public_bot_config_backup_collects_private_repo_without_secret_leakage()
    test_public_bot_workflow_commands_do_not_create_blank_onboarding_sessions()
    test_public_bot_agents_roster_add_agent_and_switch_are_account_aware()
    test_public_bot_pair_channel_links_account_across_telegram_and_discord()
    test_public_bot_pair_channel_refuses_existing_other_account()
    test_public_bot_share_approval_buttons_are_owner_scoped()
    test_public_bot_ignores_cross_user_active_deployment_metadata()
    test_public_bot_withholds_unpublished_tailnet_app_urls()
    test_public_bot_raven_display_name_is_channel_and_account_scoped()
    test_public_bot_aboard_freeform_queues_agent_turn_not_onboarding()
    test_public_bot_agent_label_uses_user_display_name()
    test_public_bot_greets_by_captured_display_name_and_offers_two_buttons()
    print("PASS all 21 ArcLink public bot tests")
    return 0


def test_public_bot_aboard_freeform_queues_agent_turn_not_onboarding() -> None:
    """Once a user has a live pod, freeform messages become selected-agent
    turns through Raven. Raven-owned slash commands stay on Raven; other slash
    commands pass through to the active agent.
    """
    control = load_module("arclink_control.py", "arclink_control_public_bot_aboard_test")
    bots = load_module("arclink_public_bots.py", "arclink_public_bots_aboard_test")
    conn = memory_db(control)
    seed_active_public_bot_deployment(
        control, conn,
        channel="telegram", channel_identity="tg:99",
        prefix="arc-c7dbf98030b3",
    )

    # Freeform "hey there" from an aboard user queues an agent turn.
    freeform = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:99",
        text="hey there",
        metadata={"telegram_message_id": "4321"},
    )
    expect(freeform.action == "agent_message_queued", f"expected agent_message_queued got {freeform.action}")
    expect("From now on, your normal messages in this channel will be routed to your active agent" in freeform.reply, freeform.reply)
    expect("I am routing" not in freeform.reply, freeform.reply)
    expect("onboarding only" not in freeform.reply.lower(), freeform.reply)
    expect("Stripe collects" not in freeform.reply, "must not show onboarding copy to a paid user")
    expect("Send `/name" not in freeform.reply, "must not prompt for /name to a paid user")
    expect(any(b.label == "Open Helm" and b.url for b in freeform.buttons), "expected Open Helm URL button")
    expect(any(b.command == "/agents" for b in freeform.buttons), "expected Show My Crew button")
    queued = conn.execute(
        "SELECT target_kind, target_id, channel_kind, message, extra_json FROM notification_outbox WHERE target_kind = 'public-agent-turn'"
    ).fetchone()
    expect(queued is not None, "expected queued public-agent-turn notification")
    expect(queued["target_id"] == "tg:99", str(dict(queued)))
    expect(queued["channel_kind"] == "telegram", str(dict(queued)))
    expect(queued["message"] == "hey there", str(dict(queued)))
    queued_extra = json.loads(str(queued["extra_json"] or "{}"))
    expect(queued_extra.get("source_kind") == "chat", str(queued_extra))
    expect(queued_extra.get("telegram_reply_to_message_id") == "4321", str(queued_extra))

    # The bridge intro is a one-time channel handoff, not repeated forever.
    second_freeform = bots.handle_arclink_public_bot_turn(conn, channel="telegram", channel_identity="tg:99", text="second note")
    expect(second_freeform.action == "agent_message_queued", str(second_freeform.action))
    expect("From now on" not in second_freeform.reply, second_freeform.reply)
    expect(second_freeform.reply == "", second_freeform.reply)

    # Unknown bare slash commands are still active-agent commands even before
    # Telegram has refreshed/stored the active Hermes command inventory.
    arbitrary_slash_without_inventory = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:99",
        text="/yolo",
    )
    expect(arbitrary_slash_without_inventory.action == "agent_message_queued", str(arbitrary_slash_without_inventory.action))
    expect(arbitrary_slash_without_inventory.reply == "", arbitrary_slash_without_inventory.reply)
    expect("I am routing" not in arbitrary_slash_without_inventory.reply, arbitrary_slash_without_inventory.reply)

    # /start re-trigger from an aboard user gets the control help reply,
    # NOT the onboarding "Stripe collects your email" prompt.
    restart = bots.handle_arclink_public_bot_turn(conn, channel="telegram", channel_identity="tg:99", text="/start")
    expect(restart.action == "show_help", f"expected show_help on /start re-trigger, got {restart.action}")
    expect("Stripe collects" not in restart.reply, "/start re-trigger leaked onboarding copy")

    # Without a refreshed Telegram command inventory, legacy Raven aliases
    # remain backward-compatible.
    crew = bots.handle_arclink_public_bot_turn(conn, channel="telegram", channel_identity="tg:99", text="/agents")
    expect(crew.action == "show_agents", str(crew.action))

    # Once Telegram command-scope refresh records active Hermes commands,
    # conflicting bare slash commands belong to the selected agent. Raven's
    # control surface remains available through /raven.
    conn.execute(
        """
        UPDATE arclink_onboarding_sessions
        SET metadata_json = ?
        WHERE channel = 'telegram' AND channel_identity = 'tg:99'
        """,
        (json.dumps({"telegram_active_agent_command_names": ["agents", "status", "help"]}),),
    )
    conn.commit()
    agent_agents = bots.handle_arclink_public_bot_turn(conn, channel="telegram", channel_identity="tg:99", text="/agents")
    expect(agent_agents.action == "agent_message_queued", str(agent_agents.action))
    raven_crew = bots.handle_arclink_public_bot_turn(conn, channel="telegram", channel_identity="tg:99", text="/raven agents")
    expect(raven_crew.action == "show_agents", str(raven_crew.action))

    # Non-Raven slash commands pass through to the active agent, preserving the
    # user's Hermes command text instead of being swallowed by Raven help.
    provider = bots.handle_arclink_public_bot_turn(conn, channel="telegram", channel_identity="tg:99", text="/provider")
    expect(provider.action == "agent_message_queued", str(provider.action))
    expect("Bridge is open" not in provider.reply, provider.reply)
    slash_row = conn.execute(
        """
        SELECT message, extra_json
        FROM notification_outbox
        WHERE target_kind = 'public-agent-turn'
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    expect(slash_row["message"] == "/provider", str(dict(slash_row)))
    slash_extra = json.loads(str(slash_row["extra_json"] or "{}"))
    expect(slash_extra.get("source_kind") == "agent_command", str(slash_extra))

    arbitrary_slash = bots.handle_arclink_public_bot_turn(conn, channel="telegram", channel_identity="tg:99", text="/yolo")
    expect(arbitrary_slash.action == "agent_message_queued", str(arbitrary_slash.action))
    expect(arbitrary_slash.reply == "", arbitrary_slash.reply)
    expect("I am routing" not in arbitrary_slash.reply, arbitrary_slash.reply)
    arbitrary_row = conn.execute(
        """
        SELECT message, extra_json
        FROM notification_outbox
        WHERE target_kind = 'public-agent-turn'
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    expect(arbitrary_row["message"] == "/yolo", str(dict(arbitrary_row)))
    arbitrary_extra = json.loads(str(arbitrary_row["extra_json"] or "{}"))
    expect(arbitrary_extra.get("source_kind") == "agent_command", str(arbitrary_extra))

    # /agent is an explicit Raven-owned pass-through for platforms whose slash
    # command menus cannot expose every active Hermes command.
    agent_command = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:99",
        text="/agent /reload-mcp",
    )
    expect(agent_command.action == "agent_message_queued", str(agent_command.action))
    agent_row = conn.execute(
        """
        SELECT message, extra_json
        FROM notification_outbox
        WHERE target_kind = 'public-agent-turn'
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    expect(agent_row["message"] == "/reload-mcp", str(dict(agent_row)))

    # Raven's postlaunch control panel moves behind /raven when the active
    # agent owns the bare slash namespace.
    helped = bots.handle_arclink_public_bot_turn(conn, channel="telegram", channel_identity="tg:99", text="/raven help")
    expect("Bridge is open" in helped.reply, helped.reply)
    fallback_status = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:99",
        text="/arclink_ops0 status",
    )
    expect(fallback_status.action == "show_status", str(fallback_status.action))

    # Registered Raven launch/setup commands stay with Raven after onboarding
    # instead of accidentally becoming agent prompts.
    package = bots.handle_arclink_public_bot_turn(conn, channel="telegram", channel_identity="tg:99", text="/packages")
    expect(package.action == "show_help", str(package.action))

    print("PASS test_public_bot_aboard_freeform_queues_agent_turn_not_onboarding")


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
        "VALUES (?, 'web', ?, 'first_contacted', 'first_agent_contact', '', 'Chris', 'sovereign', 'moonshotai/Kimi-K2.6-TEE', ?, ?, 'paid', '{}', ?, ?)",
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


def test_public_bot_greets_by_captured_display_name_and_offers_two_buttons() -> None:
    """The /start greeting must address the user by the name we picked up
    from the channel profile (Telegram first_name, Discord global_name) and
    offer exactly two buttons: Take Me Aboard and Update Name. No status
    check button on the cold-open greeting. That has nothing to read yet.
    """
    control = load_module("arclink_control.py", "arclink_control_public_bot_greet_test")
    bots = load_module("arclink_public_bots.py", "arclink_public_bots_greet_test")
    conn = memory_db(control)

    started = bots.handle_arclink_public_bot_turn(
        conn,
        channel="telegram",
        channel_identity="tg:9001",
        text="/start",
        display_name_hint="Chris",
    )
    expect("Welcome aboard, Chris" in started.reply, f"expected greeting by name, got: {started.reply}")
    expect("Founders, Sovereign, or Scale" in started.reply, started.reply)
    labels = [b.label for b in started.buttons]
    expect(labels == ["Take Me Aboard", "Update Name"], f"unexpected buttons: {labels}")
    expect("Check Status" not in labels, "no status-check on cold-open greeting")
    expect("Update Name" in labels, "Update Name belongs on the cold-open greeting")

    # Take Me Aboard opens the two-package choice.
    aboard = bots.handle_arclink_public_bot_turn(
        conn, channel="telegram", channel_identity="tg:9001",
        text="/packages", display_name_hint="Chris",
    )
    expect(aboard.action == "prompt_package", str(aboard.action))
    expect([b.label for b in aboard.buttons] == ["Founders - $149/month", "Sovereign / Scale"], str(aboard.buttons))
    standard = bots.handle_arclink_public_bot_turn(
        conn, channel="telegram", channel_identity="tg:9001",
        text="/packages standard", display_name_hint="Chris",
    )
    expect([b.label for b in standard.buttons] == ["Sovereign - $199/month", "Scale - $275/month"], str(standard.buttons))

    # Update Name (bare /name) prompts for input rather than blanking the
    # captured name. The current name is shown back to the user.
    update_name = bots.handle_arclink_public_bot_turn(
        conn, channel="telegram", channel_identity="tg:9001",
        text="/name", display_name_hint="Chris",
    )
    expect(update_name.action == "prompt_name_input", str(update_name.action))
    expect("I am listening" in update_name.reply, update_name.reply)

    renamed = bots.handle_arclink_public_bot_turn(
        conn, channel="telegram", channel_identity="tg:9001",
        text="Sirouk",
        display_name_hint="Chris",
    )
    expect("Welcome aboard, Sirouk" in renamed.reply, renamed.reply)
    expect("$149/month" in renamed.reply, renamed.reply)
    expect("$199/month" in renamed.reply, renamed.reply)
    expect("$275/month" in renamed.reply, renamed.reply)
    expect([b.label for b in renamed.buttons] == ["Founders - $149/month", "Sovereign / Scale"], str(renamed.buttons))
    expect(len(renamed.buttons) == 2, str(renamed.buttons))

    # If no display name was provided by the channel, the greeting falls back
    # to the generic line and the buttons are unchanged.
    fresh = bots.handle_arclink_public_bot_turn(
        conn, channel="discord", channel_identity="discord:9002", text="/start",
    )
    expect("Raven here. ArcLink is in range." in fresh.reply, fresh.reply)
    expect([b.label for b in fresh.buttons] == ["Take Me Aboard", "Update Name"], str(fresh.buttons))
    print("PASS test_public_bot_greets_by_captured_display_name_and_offers_two_buttons")


if __name__ == "__main__":
    raise SystemExit(main())
