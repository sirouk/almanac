#!/usr/bin/env python3
from __future__ import annotations

import urllib.parse
from typing import Any

from almanac_http import http_request, parse_json_object


def _telegram_url(bot_token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{bot_token}/{method}"


def _request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    headers = {}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    response = http_request(
        url,
        method=method,
        headers=headers,
        json_payload=payload,
        timeout=timeout,
        allow_loopback_http=False,
    )
    try:
        payload_json = parse_json_object(response, label="telegram")
    except RuntimeError as exc:
        if response.status_code >= 400:
            raise RuntimeError(f"telegram http {response.status_code}: {response.text[:200]}") from exc
        raise
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
    reply_markup: dict[str, Any] | None = None,
    parse_mode: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text if len(text) <= 4000 else text[:3997] + "...",
    }
    if reply_to_message_id is not None:
        payload["reply_to_message_id"] = int(reply_to_message_id)
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    if parse_mode:
        payload["parse_mode"] = parse_mode
    return _request_json(
        _telegram_url(bot_token, "sendMessage"),
        method="POST",
        payload=payload,
        timeout=20,
    )


def telegram_answer_callback_query(
    *,
    bot_token: str,
    callback_query_id: str,
    text: str = "",
    show_alert: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "callback_query_id": callback_query_id,
        "show_alert": bool(show_alert),
    }
    if text:
        payload["text"] = text[:200]
    return _request_json(
        _telegram_url(bot_token, "answerCallbackQuery"),
        method="POST",
        payload=payload,
        timeout=20,
    )


def telegram_edit_message_reply_markup(
    *,
    bot_token: str,
    chat_id: str,
    message_id: int,
    reply_markup: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": int(message_id),
        "reply_markup": reply_markup if reply_markup is not None else {"inline_keyboard": []},
    }
    return _request_json(
        _telegram_url(bot_token, "editMessageReplyMarkup"),
        method="POST",
        payload=payload,
        timeout=20,
    )


def telegram_edit_message_text(
    *,
    bot_token: str,
    chat_id: str,
    message_id: int,
    text: str,
    reply_markup: dict[str, Any] | None = None,
    parse_mode: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": int(message_id),
        "text": text if len(text) <= 4000 else text[:3997] + "...",
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    if parse_mode:
        payload["parse_mode"] = parse_mode
    return _request_json(
        _telegram_url(bot_token, "editMessageText"),
        method="POST",
        payload=payload,
        timeout=20,
    )


def telegram_get_me(*, bot_token: str) -> dict[str, Any]:
    return _request_json(_telegram_url(bot_token, "getMe"), timeout=20)


def telegram_set_my_commands(
    *,
    bot_token: str,
    commands: list[dict[str, str]],
    scope: dict[str, Any] | None = None,
    language_code: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "commands": [
            {
                "command": str(item.get("command") or "").strip().lstrip("/"),
                "description": str(item.get("description") or "").strip(),
            }
            for item in commands
            if str(item.get("command") or "").strip() and str(item.get("description") or "").strip()
        ]
    }
    if scope is not None:
        payload["scope"] = scope
    if language_code:
        payload["language_code"] = language_code
    return _request_json(
        _telegram_url(bot_token, "setMyCommands"),
        method="POST",
        payload=payload,
        timeout=20,
    )


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
