#!/usr/bin/env python3
from __future__ import annotations

import json

from arclink_test_helpers import auth_headers, expect, load_module, memory_db


def seed_pods(control, conn) -> None:
    control.upsert_arclink_user(
        conn,
        user_id="arcusr_alpha",
        email="alpha@example.test",
        display_name="Alpha Captain",
        entitlement_state="paid",
    )
    control.upsert_arclink_user(
        conn,
        user_id="arcusr_beta",
        email="beta@example.test",
        display_name="Beta Captain",
        entitlement_state="paid",
    )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="arcdep_alpha_1",
        user_id="arcusr_alpha",
        prefix="alpha-one",
        base_domain="example.test",
        agent_id="agent-alpha-1",
        agent_name="Atlas",
        status="active",
    )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="arcdep_alpha_2",
        user_id="arcusr_alpha",
        prefix="alpha-two",
        base_domain="example.test",
        agent_id="agent-alpha-2",
        agent_name="Beacon",
        status="active",
    )
    control.reserve_arclink_deployment_prefix(
        conn,
        deployment_id="arcdep_beta_1",
        user_id="arcusr_beta",
        prefix="beta-one",
        base_domain="example.test",
        agent_id="agent-beta-1",
        agent_name="Cinder",
        status="active",
    )
    conn.commit()


def insert_grant(control, conn, *, status: str = "accepted", expires_at: str = "2999-01-01T00:00:00+00:00") -> str:
    grant_id = f"grant_{status}"
    now = control.utc_now_iso()
    conn.execute(
        """
        INSERT INTO arclink_share_grants (
          grant_id, owner_user_id, recipient_user_id, resource_kind, resource_root,
          resource_path, display_name, access_mode, status, expires_at, approved_at,
          accepted_at, revoked_at, metadata_json, created_at, updated_at
        ) VALUES (?, 'arcusr_alpha', 'arcusr_beta', 'pod_comms', 'pod_comms',
          '*', 'Alpha/Beta Comms', 'read', ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            grant_id,
            status,
            expires_at,
            now if status in {"approved", "accepted"} else "",
            now if status == "accepted" else "",
            now if status == "revoked" else "",
            json.dumps({
                "owner_deployment_id": "arcdep_alpha_1",
                "recipient_deployment_id": "arcdep_beta_1",
            }),
            now,
            now,
        ),
    )
    conn.commit()
    return grant_id


def test_same_captain_send_enqueues_notification_and_audit() -> None:
    control = load_module("arclink_control.py", "arclink_control_pod_comms_same")
    comms = load_module("arclink_pod_comms.py", "arclink_pod_comms_same")
    conn = memory_db(control)
    seed_pods(control, conn)

    result = comms.send_pod_message(
        conn,
        sender_deployment_id="arcdep_alpha_1",
        recipient_deployment_id="arcdep_alpha_2",
        body="Move the launch checklist to the top.",
    )

    expect(result["message"]["sender_user_id"] == "arcusr_alpha", str(result))
    expect(result["message"]["recipient_user_id"] == "arcusr_alpha", str(result))
    expect(result["message"]["status"] == "queued", str(result))
    expect(result["notification_id"] > 0, str(result))
    outbox = conn.execute("SELECT target_kind, target_id, channel_kind, extra_json FROM notification_outbox").fetchone()
    expect(outbox["target_kind"] == "user-agent", str(dict(outbox)))
    expect(outbox["target_id"] == "agent-alpha-2", str(dict(outbox)))
    expect(outbox["channel_kind"] == "pod-message", str(dict(outbox)))
    expect(json.loads(outbox["extra_json"])["message_id"] == result["message"]["message_id"], outbox["extra_json"])
    actions = {row["action"] for row in conn.execute("SELECT action FROM arclink_audit_log").fetchall()}
    events = {row["event_type"] for row in conn.execute("SELECT event_type FROM arclink_events").fetchall()}
    expect("pod_message_sent" in actions, str(actions))
    expect("pod_message_sent" in events, str(events))
    print("PASS test_same_captain_send_enqueues_notification_and_audit")


def test_cross_captain_send_requires_active_pod_comms_grant() -> None:
    control = load_module("arclink_control.py", "arclink_control_pod_comms_grant")
    comms = load_module("arclink_pod_comms.py", "arclink_pod_comms_grant")
    conn = memory_db(control)
    seed_pods(control, conn)

    for status in ("pending_owner_approval", "approved", "revoked", "expired"):
        conn.execute("DELETE FROM arclink_share_grants")
        insert_grant(control, conn, status=status, expires_at="2000-01-01T00:00:00+00:00" if status == "expired" else "2999-01-01T00:00:00+00:00")
        try:
            comms.send_pod_message(
                conn,
                sender_deployment_id="arcdep_alpha_1",
                recipient_deployment_id="arcdep_beta_1",
                body="Cross-Captain hello",
            )
        except PermissionError as exc:
            expect("share grant" in str(exc), str(exc))
        else:
            raise AssertionError(f"cross-Captain {status} grant should be refused")

    conn.execute("DELETE FROM arclink_share_grants")
    grant_id = insert_grant(control, conn, status="accepted")
    result = comms.send_pod_message(
        conn,
        sender_deployment_id="arcdep_alpha_1",
        recipient_deployment_id="arcdep_beta_1",
        body="Cross-Captain hello",
        attachments=[{"grant_id": grant_id, "label": "accepted projection"}],
    )
    attachment = result["message"]["attachments"][0]
    expect(attachment["grant_id"] == grant_id, str(result))
    expect(attachment["resource_kind"] == "pod_comms", str(result))
    print("PASS test_cross_captain_send_requires_active_pod_comms_grant")


def test_rate_limit_list_delivery_and_redaction() -> None:
    control = load_module("arclink_control.py", "arclink_control_pod_comms_rate")
    comms = load_module("arclink_pod_comms.py", "arclink_pod_comms_rate")
    conn = memory_db(control)
    seed_pods(control, conn)

    sent = []
    for index in range(60):
        sent.append(comms.send_pod_message(
            conn,
            sender_deployment_id="arcdep_alpha_1",
            recipient_deployment_id="arcdep_alpha_2",
            body=f"message {index}",
        ))
    try:
        comms.send_pod_message(
            conn,
            sender_deployment_id="arcdep_alpha_1",
            recipient_deployment_id="arcdep_alpha_2",
            body="message 61",
        )
    except Exception as exc:
        expect("rate limit" in str(exc).lower(), str(exc))
    else:
        raise AssertionError("61st message in one minute should be rate limited")

    inbox = comms.list_pod_messages(conn, deployment_id="arcdep_alpha_2", direction="inbox", limit=100)
    outbox = comms.list_pod_messages(conn, deployment_id="arcdep_alpha_1", direction="outbox", limit=100)
    expect(len(inbox["messages"]) == 60, str(inbox))
    expect(len(outbox["messages"]) == 60, str(outbox))

    message_id = sent[0]["message"]["message_id"]
    delivered = comms.mark_pod_message_delivered(conn, message_id=message_id, actor_id="delivery-test")
    expect(delivered["message"]["status"] == "delivered", str(delivered))
    redacted = comms.redact_pod_message(conn, message_id=message_id, actor_id="operator-test", reason="test")
    expect(redacted["message"]["status"] == "redacted", str(redacted))
    expect(redacted["message"]["body"] == "", str(redacted))
    actions = [row["action"] for row in conn.execute("SELECT action FROM arclink_audit_log ORDER BY created_at").fetchall()]
    expect("pod_message_delivered" in actions, str(actions))
    expect("pod_message_redacted" in actions, str(actions))
    print("PASS test_rate_limit_list_delivery_and_redaction")


def test_hosted_comms_routes_scope_user_and_redact_admin_body() -> None:
    control = load_module("arclink_control.py", "arclink_control_pod_comms_hosted")
    api = load_module("arclink_api_auth.py", "arclink_api_auth_pod_comms_hosted")
    comms = load_module("arclink_pod_comms.py", "arclink_pod_comms_hosted")
    hosted = load_module("arclink_hosted_api.py", "arclink_hosted_api_pod_comms")
    conn = memory_db(control)
    seed_pods(control, conn)
    comms.send_pod_message(
        conn,
        sender_deployment_id="arcdep_alpha_1",
        recipient_deployment_id="arcdep_alpha_2",
        body="Captain narrative stays Captain-scoped.",
    )
    api.upsert_arclink_admin(conn, admin_id="admin_comms", email="admin-comms@example.test", role="ops")
    user_session = api.create_arclink_user_session(conn, user_id="arcusr_alpha", session_id="usess_comms")
    admin_session = api.create_arclink_admin_session(conn, admin_id="admin_comms", session_id="asess_comms")
    config = hosted.HostedApiConfig(env={"ARCLINK_BASE_DOMAIN": "example.test"})

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/user/comms",
        headers=auth_headers(user_session),
        config=config,
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect(payload["comms"][0]["body"] == "Captain narrative stays Captain-scoped.", str(payload))

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/admin/comms",
        headers=auth_headers(admin_session),
        config=config,
        remote_addr="203.0.113.10",
    )
    expect(status == 403, f"admin comms should be CIDR gated: {status} {payload}")

    status, payload, _ = hosted.route_arclink_hosted_api(
        conn,
        method="GET",
        path="/api/v1/admin/comms",
        headers=auth_headers(admin_session),
        config=config,
        remote_addr="127.0.0.1",
    )
    expect(status == 200, f"expected 200 got {status}: {payload}")
    expect("body" not in payload["comms"][0], str(payload))
    expect("attachments" not in payload["comms"][0], str(payload))
    print("PASS test_hosted_comms_routes_scope_user_and_redact_admin_body")


def test_mcp_pod_comms_tools_scope_to_authenticated_agent() -> None:
    control = load_module("arclink_control.py", "arclink_control_pod_comms_mcp")
    mcp = load_module("arclink_mcp_server.py", "arclink_mcp_server_pod_comms")
    conn = memory_db(control)
    seed_pods(control, conn)
    token_payload = control._issue_bootstrap_token(
        conn,
        request_id=None,
        agent_id="agent-alpha-1",
        requester_identity="Alpha Agent",
        source_ip="127.0.0.1",
        issued_by="test",
        activate_now=True,
    )
    conn.commit()

    sent = mcp._send_agent_pod_comms(
        conn,
        {
            "token": token_payload["raw_token"],
            "recipient_deployment_id": "arcdep_alpha_2",
            "body": "MCP scoped hello",
        },
    )
    expect(sent["message"]["sender_deployment_id"] == "arcdep_alpha_1", str(sent))
    attachment = mcp._create_agent_pod_comms_share_file(
        conn,
        {
            "token": token_payload["raw_token"],
            "recipient_deployment_id": "arcdep_alpha_2",
            "resource_kind": "drive",
            "resource_root": "vault",
            "resource_path": "/Projects/brief.md",
            "display_name": "Brief",
        },
    )
    expect(attachment["grant"]["status"] == "accepted", str(attachment))
    with_attachment = mcp._send_agent_pod_comms(
        conn,
        {
            "token": token_payload["raw_token"],
            "recipient_deployment_id": "arcdep_alpha_2",
            "body": "MCP attachment hello",
            "attachments": [{"grant_id": attachment["grant"]["grant_id"]}],
        },
    )
    expect(with_attachment["message"]["attachments"][0]["grant_id"] == attachment["grant"]["grant_id"], str(with_attachment))
    listed = mcp._list_agent_pod_comms(conn, {"token": token_payload["raw_token"], "direction": "outbox"})
    expect({row["message_id"] for row in listed["messages"]} >= {sent["message"]["message_id"], with_attachment["message"]["message_id"]}, str(listed))
    try:
        mcp._send_agent_pod_comms(
            conn,
            {
                "token": token_payload["raw_token"],
                "deployment_id": "arcdep_beta_1",
                "recipient_deployment_id": "arcdep_alpha_2",
                "body": "scope break",
            },
        )
    except PermissionError as exc:
        expect("outside this agent" in str(exc), str(exc))
    else:
        raise AssertionError("pod_comms.send must reject sender deployments outside the agent")
    print("PASS test_mcp_pod_comms_tools_scope_to_authenticated_agent")


def main() -> int:
    test_same_captain_send_enqueues_notification_and_audit()
    test_cross_captain_send_requires_active_pod_comms_grant()
    test_rate_limit_list_delivery_and_redaction()
    test_hosted_comms_routes_scope_user_and_redact_admin_body()
    test_mcp_pod_comms_tools_scope_to_authenticated_agent()
    print("PASS all 5 ArcLink Pod Comms tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
