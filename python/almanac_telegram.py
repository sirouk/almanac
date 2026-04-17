#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def _telegram_url(bot_token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{bot_token}/{method}"


def _request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
        raise RuntimeError(f"telegram http {exc.code}: {body[:200]}") from exc

    try:
        payload_json = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"telegram returned invalid json: {body[:200]}") from exc
    if not payload_json.get("ok", False):
        description = str(payload_json.get("description") or "unknown telegram error")
        raise RuntimeError(description)
    result = payload_json.get("result")
    return result if isinstance(result, dict) else {"result": result}


def telegram_send_message(
    *,
    bot_token: str,
    chat_id: str,
    text: str,
    reply_to_message_id: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text if len(text) <= 4000 else text[:3997] + "...",
    }
    if reply_to_message_id is not None:
        payload["reply_to_message_id"] = int(reply_to_message_id)
    return _request_json(
        _telegram_url(bot_token, "sendMessage"),
        method="POST",
        payload=payload,
        timeout=20,
    )


def telegram_get_me(*, bot_token: str) -> dict[str, Any]:
    return _request_json(_telegram_url(bot_token, "getMe"), timeout=20)


def telegram_get_updates(
    *,
    bot_token: str,
    offset: int | None = None,
    timeout: int = 25,
) -> list[dict[str, Any]]:
    params = {"timeout": str(timeout)}
    if offset is not None:
        params["offset"] = str(offset)
    query = urllib.parse.urlencode(params)
    url = _telegram_url(bot_token, "getUpdates")
    if query:
        url = f"{url}?{query}"
    payload = _request_json(url, timeout=timeout + 10)
    result = payload.get("result", payload)
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    return []
