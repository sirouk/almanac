#!/usr/bin/env python3
from __future__ import annotations

from typing import Any

from almanac_http import http_request, parse_json_object


DISCORD_API_BASE = "https://discord.com/api/v10"
DISCORD_USER_AGENT = "AlmanacDiscord/1.0 (+https://github.com/example/almanac)"


def _request_json(
    path: str,
    *,
    bot_token: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Accept": "application/json",
        "User-Agent": DISCORD_USER_AGENT,
    }
    if payload is not None:
        headers["Content-Type"] = "application/json"
    response = http_request(
        f"{DISCORD_API_BASE}{path}",
        method=method,
        headers=headers,
        json_payload=payload,
        timeout=timeout,
        allow_loopback_http=False,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"discord http {response.status_code}: {response.text[:200]}")
    return parse_json_object(response, label="discord")


def discord_get_current_user(*, bot_token: str) -> dict[str, Any]:
    return _request_json("/users/@me", bot_token=bot_token, timeout=20)


def discord_create_dm_channel(*, bot_token: str, recipient_id: str) -> dict[str, Any]:
    return _request_json(
        "/users/@me/channels",
        bot_token=bot_token,
        method="POST",
        payload={"recipient_id": str(recipient_id).strip()},
        timeout=20,
    )


def discord_send_message(
    *,
    bot_token: str,
    channel_id: str,
    text: str,
    components: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"content": text if len(text) <= 1900 else text[:1897] + "..."}
    if components is not None:
        payload["components"] = components
    return _request_json(
        f"/channels/{channel_id}/messages",
        bot_token=bot_token,
        method="POST",
        payload=payload,
        timeout=20,
    )


def discord_edit_message(
    *,
    bot_token: str,
    channel_id: str,
    message_id: str,
    text: str | None = None,
    components: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if text is not None:
        payload["content"] = text if len(text) <= 1900 else text[:1897] + "..."
    if components is not None:
        payload["components"] = components
    return _request_json(
        f"/channels/{channel_id}/messages/{message_id}",
        bot_token=bot_token,
        method="PATCH",
        payload=payload,
        timeout=20,
    )
