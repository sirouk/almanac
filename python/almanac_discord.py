#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


DISCORD_API_BASE = "https://discord.com/api/v10"
DISCORD_USER_AGENT = "AlmanacDiscord/1.0 (+https://github.com/sirouk/almanac)"


def _request_json(
    path: str,
    *,
    bot_token: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    data = None
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Accept": "application/json",
        "User-Agent": DISCORD_USER_AGENT,
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(f"{DISCORD_API_BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
        raise RuntimeError(f"discord http {exc.code}: {body[:200]}") from exc

    try:
        payload_json = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"discord returned invalid json: {body[:200]}") from exc
    if isinstance(payload_json, dict):
        return payload_json
    raise RuntimeError(f"discord returned unexpected payload: {body[:200]}")


def discord_get_current_user(*, bot_token: str) -> dict[str, Any]:
    return _request_json("/users/@me", bot_token=bot_token, timeout=20)


def discord_send_message(*, bot_token: str, channel_id: str, text: str) -> dict[str, Any]:
    return _request_json(
        f"/channels/{channel_id}/messages",
        bot_token=bot_token,
        method="POST",
        payload={"content": text if len(text) <= 1900 else text[:1897] + "..."},
        timeout=20,
    )
