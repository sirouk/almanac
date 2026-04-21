#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from typing import Any, Callable
from urllib import error, parse, request

NOTION_API_BASE_URL = "https://api.notion.com/v1"
DEFAULT_NOTION_API_VERSION = "2026-03-11"
_NOTION_ID_RE = re.compile(
    r"([0-9a-fA-F]{32}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
)


class NotionApiError(RuntimeError):
    def __init__(self, *, status: int, message: str, code: str = ""):
        super().__init__(message)
        self.status = int(status)
        self.message = str(message or "").strip()
        self.code = str(code or "").strip()


def _normalize_uuid(raw_value: str) -> str:
    compact = str(raw_value or "").strip().replace("-", "").lower()
    if len(compact) != 32 or any(ch not in "0123456789abcdef" for ch in compact):
        raise ValueError("Notion page/database URL must include a valid 32-character object id")
    return (
        f"{compact[:8]}-{compact[8:12]}-{compact[12:16]}-{compact[16:20]}-{compact[20:]}"
    )


def normalize_notion_space_url(space_ref: str) -> str:
    raw_value = str(space_ref or "").strip()
    if not raw_value:
        return ""
    parsed = parse.urlparse(raw_value)
    if parsed.scheme and parsed.netloc:
        return parse.urlunparse(parsed._replace(params="", query="", fragment=""))
    return raw_value


def extract_notion_space_id(space_ref: str) -> str:
    raw_value = str(space_ref or "").strip()
    if not raw_value:
        raise ValueError("Notion page/database URL is required")

    candidates: list[str] = []
    parsed = parse.urlparse(raw_value)
    if parsed.scheme and parsed.netloc:
        path = parse.unquote(parsed.path or "")
        fragment = parse.unquote(parsed.fragment or "")
        candidates.extend(match.group(1) for match in _NOTION_ID_RE.finditer(path))
        candidates.extend(match.group(1) for match in _NOTION_ID_RE.finditer(fragment))
    if not candidates:
        candidates.extend(match.group(1) for match in _NOTION_ID_RE.finditer(raw_value))
    if not candidates:
        raise ValueError("Could not find a Notion page/database id in that value")
    return _normalize_uuid(candidates[-1])


def _rich_text_to_plain_text(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        text = str(item.get("plain_text") or "").strip()
        if text:
            parts.append(text)
    return "".join(parts).strip()


def _page_title(payload: dict[str, Any]) -> str:
    properties = payload.get("properties")
    if not isinstance(properties, dict):
        return ""
    for prop in properties.values():
        if not isinstance(prop, dict):
            continue
        if str(prop.get("type") or "").strip() != "title":
            continue
        return _rich_text_to_plain_text(prop.get("title"))
    return ""


def _database_title(payload: dict[str, Any]) -> str:
    return _rich_text_to_plain_text(payload.get("title"))


def _request_json(
    method: str,
    path: str,
    *,
    token: str,
    api_version: str,
    payload: dict[str, Any] | None = None,
    urlopen_fn: Callable[..., Any] = request.urlopen,
) -> dict[str, Any]:
    body = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": api_version,
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = request.Request(
        f"{NOTION_API_BASE_URL}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urlopen_fn(req, timeout=15) as response:
            raw = response.read().decode("utf-8") or "{}"
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        message = raw.strip() or f"http {exc.code}"
        code = ""
        try:
            payload_json = json.loads(raw or "{}")
        except json.JSONDecodeError:
            payload_json = {}
        if isinstance(payload_json, dict):
            message = str(payload_json.get("message") or payload_json.get("error") or message)
            code = str(payload_json.get("code") or "")
        raise NotionApiError(status=exc.code, message=message, code=code) from exc
    except error.URLError as exc:
        raise RuntimeError(f"Unable to reach Notion API: {exc.reason}") from exc

    try:
        payload_json = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Notion API returned invalid JSON: {raw[:200]}") from exc
    if not isinstance(payload_json, dict):
        raise RuntimeError("Notion API returned an unexpected response shape")
    return payload_json


def _friendly_api_error(exc: NotionApiError, *, target: str) -> RuntimeError:
    if exc.status == 401:
        return RuntimeError("Notion rejected the integration secret. Check ALMANAC_SSOT_NOTION_TOKEN.")
    if exc.status == 403:
        return RuntimeError(
            f"Notion accepted the integration secret but denied access to {target}. "
            "Make sure the integration has access to that page/database."
        )
    if exc.status == 404:
        return RuntimeError(
            f"Notion could not retrieve {target}. Make sure the URL is correct and the integration is connected there. "
            "If you are pointing at the workspace Home screen, create a normal page for Almanac, connect the integration "
            "to that page, and use that page URL instead."
        )
    return RuntimeError(f"Notion API error for {target}: {exc.message or f'http {exc.status}'}")


def _integration_summary(payload: dict[str, Any]) -> dict[str, str]:
    bot_info = payload.get("bot")
    workspace_name = ""
    integration_name = str(payload.get("name") or "").strip()
    if isinstance(bot_info, dict):
        workspace_name = str(bot_info.get("workspace_name") or "").strip()
        owner = bot_info.get("owner")
        if isinstance(owner, dict):
            user_info = owner.get("user")
            if isinstance(user_info, dict) and not integration_name:
                integration_name = str(user_info.get("name") or "").strip()
    if not integration_name:
        integration_name = str(payload.get("id") or "Notion integration")
    return {
        "id": str(payload.get("id") or "").strip(),
        "name": integration_name or "Notion integration",
        "workspace_name": workspace_name,
        "type": str(payload.get("type") or "").strip(),
    }


def _resolve_target(
    *,
    token: str,
    api_version: str,
    target_id: str,
    urlopen_fn: Callable[..., Any] = request.urlopen,
) -> dict[str, str]:
    page_error: NotionApiError | None = None
    try:
        payload = _request_json(
            "GET",
            f"/pages/{target_id}",
            token=token,
            api_version=api_version,
            urlopen_fn=urlopen_fn,
        )
        return {
            "kind": "page",
            "id": str(payload.get("id") or target_id).strip() or target_id,
            "title": _page_title(payload),
            "url": str(payload.get("url") or "").strip(),
        }
    except NotionApiError as exc:
        page_error = exc
        if exc.status not in {400, 404}:
            raise _friendly_api_error(exc, target=f"page {target_id}") from exc

    try:
        payload = _request_json(
            "GET",
            f"/databases/{target_id}",
            token=token,
            api_version=api_version,
            urlopen_fn=urlopen_fn,
        )
        return {
            "kind": "database",
            "id": str(payload.get("id") or target_id).strip() or target_id,
            "title": _database_title(payload),
            "url": str(payload.get("url") or "").strip(),
        }
    except NotionApiError as exc:
        if exc.status not in {400, 404}:
            raise _friendly_api_error(exc, target=f"database {target_id}") from exc
        if page_error is not None:
            raise _friendly_api_error(page_error, target=f"Notion target {target_id}") from exc
        raise _friendly_api_error(exc, target=f"Notion target {target_id}") from exc


def resolve_notion_target(
    *,
    target_id: str,
    token: str,
    api_version: str = DEFAULT_NOTION_API_VERSION,
    urlopen_fn: Callable[..., Any] = request.urlopen,
) -> dict[str, str]:
    normalized_target_id = extract_notion_space_id(target_id)
    return _resolve_target(
        token=token,
        api_version=api_version,
        target_id=normalized_target_id,
        urlopen_fn=urlopen_fn,
    )


def notion_request_json(
    method: str,
    path: str,
    *,
    token: str,
    api_version: str = DEFAULT_NOTION_API_VERSION,
    payload: dict[str, Any] | None = None,
    urlopen_fn: Callable[..., Any] = request.urlopen,
) -> dict[str, Any]:
    return _request_json(
        method,
        path,
        token=token,
        api_version=api_version,
        payload=payload,
        urlopen_fn=urlopen_fn,
    )


def retrieve_notion_page(
    *,
    page_id: str,
    token: str,
    api_version: str = DEFAULT_NOTION_API_VERSION,
    urlopen_fn: Callable[..., Any] = request.urlopen,
) -> dict[str, Any]:
    target_id = extract_notion_space_id(page_id)
    try:
        return _request_json(
            "GET",
            f"/pages/{target_id}",
            token=token,
            api_version=api_version,
            urlopen_fn=urlopen_fn,
        )
    except NotionApiError as exc:
        raise _friendly_api_error(exc, target=f"page {target_id}") from exc


def retrieve_notion_database(
    *,
    database_id: str,
    token: str,
    api_version: str = DEFAULT_NOTION_API_VERSION,
    urlopen_fn: Callable[..., Any] = request.urlopen,
) -> dict[str, Any]:
    target_id = extract_notion_space_id(database_id)
    try:
        return _request_json(
            "GET",
            f"/databases/{target_id}",
            token=token,
            api_version=api_version,
            urlopen_fn=urlopen_fn,
        )
    except NotionApiError as exc:
        raise _friendly_api_error(exc, target=f"database {target_id}") from exc


def retrieve_notion_data_source(
    *,
    data_source_id: str,
    token: str,
    api_version: str = DEFAULT_NOTION_API_VERSION,
    urlopen_fn: Callable[..., Any] = request.urlopen,
) -> dict[str, Any]:
    target_id = extract_notion_space_id(data_source_id)
    try:
        return _request_json(
            "GET",
            f"/data_sources/{target_id}",
            token=token,
            api_version=api_version,
            urlopen_fn=urlopen_fn,
        )
    except NotionApiError as exc:
        raise _friendly_api_error(exc, target=f"data source {target_id}") from exc


def query_notion_data_source(
    *,
    data_source_id: str,
    token: str,
    api_version: str = DEFAULT_NOTION_API_VERSION,
    payload: dict[str, Any] | None = None,
    urlopen_fn: Callable[..., Any] = request.urlopen,
) -> dict[str, Any]:
    target_id = extract_notion_space_id(data_source_id)
    try:
        return _request_json(
            "POST",
            f"/data_sources/{target_id}/query",
            token=token,
            api_version=api_version,
            payload=payload or {},
            urlopen_fn=urlopen_fn,
        )
    except NotionApiError as exc:
        raise _friendly_api_error(exc, target=f"data source {target_id}") from exc


def query_notion_database_legacy(
    *,
    database_id: str,
    token: str,
    api_version: str = DEFAULT_NOTION_API_VERSION,
    payload: dict[str, Any] | None = None,
    urlopen_fn: Callable[..., Any] = request.urlopen,
) -> dict[str, Any]:
    target_id = extract_notion_space_id(database_id)
    try:
        return _request_json(
            "POST",
            f"/databases/{target_id}/query",
            token=token,
            api_version=api_version,
            payload=payload or {},
            urlopen_fn=urlopen_fn,
        )
    except NotionApiError as exc:
        raise _friendly_api_error(exc, target=f"database {target_id}") from exc


def query_notion_collection(
    *,
    database_id: str,
    token: str,
    api_version: str = DEFAULT_NOTION_API_VERSION,
    payload: dict[str, Any] | None = None,
    urlopen_fn: Callable[..., Any] = request.urlopen,
) -> dict[str, Any]:
    database = retrieve_notion_database(
        database_id=database_id,
        token=token,
        api_version=api_version,
        urlopen_fn=urlopen_fn,
    )
    data_sources = database.get("data_sources") if isinstance(database, dict) else None
    if isinstance(data_sources, list) and data_sources:
        first = data_sources[0] if isinstance(data_sources[0], dict) else {}
        data_source_id = str(first.get("id") or "").strip()
        if data_source_id:
            result = query_notion_data_source(
                data_source_id=data_source_id,
                token=token,
                api_version=api_version,
                payload=payload or {},
                urlopen_fn=urlopen_fn,
            )
            return {
                "query_kind": "data_source",
                "database": database,
                "data_source_id": data_source_id,
                "result": result,
            }
    result = query_notion_database_legacy(
        database_id=database_id,
        token=token,
        api_version=api_version,
        payload=payload or {},
        urlopen_fn=urlopen_fn,
    )
    return {
        "query_kind": "database",
        "database": database,
        "data_source_id": "",
        "result": result,
    }


def retrieve_notion_page_markdown(
    *,
    page_id: str,
    token: str,
    api_version: str = DEFAULT_NOTION_API_VERSION,
    urlopen_fn: Callable[..., Any] = request.urlopen,
) -> dict[str, Any]:
    target_id = extract_notion_space_id(page_id)
    try:
        return _request_json(
            "GET",
            f"/pages/{target_id}/markdown",
            token=token,
            api_version=api_version,
            urlopen_fn=urlopen_fn,
        )
    except NotionApiError as exc:
        raise _friendly_api_error(exc, target=f"page markdown {target_id}") from exc


def retrieve_notion_user(
    *,
    user_id: str,
    token: str,
    api_version: str = DEFAULT_NOTION_API_VERSION,
    urlopen_fn: Callable[..., Any] = request.urlopen,
) -> dict[str, Any]:
    target_id = extract_notion_space_id(user_id)
    try:
        return _request_json(
            "GET",
            f"/users/{target_id}",
            token=token,
            api_version=api_version,
            urlopen_fn=urlopen_fn,
        )
    except NotionApiError as exc:
        raise _friendly_api_error(exc, target=f"user {target_id}") from exc


def _database_parent_payload(
    *,
    database_id: str,
    token: str,
    api_version: str,
    urlopen_fn: Callable[..., Any],
) -> dict[str, Any]:
    database = retrieve_notion_database(
        database_id=database_id,
        token=token,
        api_version=api_version,
        urlopen_fn=urlopen_fn,
    )
    data_sources = database.get("data_sources") if isinstance(database, dict) else None
    if isinstance(data_sources, list) and data_sources:
        first = data_sources[0] if isinstance(data_sources[0], dict) else {}
        data_source_id = str(first.get("id") or "").strip()
        if data_source_id:
            return {"type": "data_source_id", "data_source_id": data_source_id}
    return {"type": "database_id", "database_id": database_id}


def create_notion_page(
    *,
    parent_id: str,
    parent_kind: str,
    token: str,
    payload: dict[str, Any] | None = None,
    api_version: str = DEFAULT_NOTION_API_VERSION,
    urlopen_fn: Callable[..., Any] = request.urlopen,
) -> dict[str, Any]:
    normalized_parent_id = extract_notion_space_id(parent_id)
    normalized_parent_kind = str(parent_kind or "").strip().lower()
    create_payload = dict(payload or {})
    if normalized_parent_kind == "database":
        create_payload["parent"] = _database_parent_payload(
            database_id=normalized_parent_id,
            token=token,
            api_version=api_version,
            urlopen_fn=urlopen_fn,
        )
    elif normalized_parent_kind == "page":
        create_payload["parent"] = {"type": "page_id", "page_id": normalized_parent_id}
    else:
        raise ValueError("parent_kind must be 'database' or 'page'")
    try:
        return _request_json(
            "POST",
            "/pages",
            token=token,
            api_version=api_version,
            payload=create_payload,
            urlopen_fn=urlopen_fn,
        )
    except NotionApiError as exc:
        raise _friendly_api_error(exc, target=f"{normalized_parent_kind} {normalized_parent_id}") from exc


def create_notion_database(
    *,
    parent_page_id: str,
    title: str,
    properties: dict[str, Any],
    api_version: str = DEFAULT_NOTION_API_VERSION,
    token: str,
    description: str = "",
    urlopen_fn: Callable[..., Any] = request.urlopen,
) -> dict[str, Any]:
    normalized_parent_id = extract_notion_space_id(parent_page_id)
    title_value = str(title or "").strip() or "Almanac Verification"
    title_payload = [
        {
            "type": "text",
            "text": {
                "content": title_value,
            },
        }
    ]
    create_payload: dict[str, Any] = {
        "parent": {"type": "page_id", "page_id": normalized_parent_id},
        "title": title_payload,
        "initial_data_source": {"properties": dict(properties or {})},
    }
    compact_description = str(description or "").strip()
    if compact_description:
        create_payload["description"] = [
            {
                "type": "text",
                "text": {
                    "content": compact_description,
                },
            }
        ]
    try:
        return _request_json(
            "POST",
            "/databases",
            token=token,
            api_version=api_version,
            payload=create_payload,
            urlopen_fn=urlopen_fn,
        )
    except NotionApiError as exc:
        raise _friendly_api_error(exc, target=f"page {normalized_parent_id}") from exc


def update_notion_page(
    *,
    page_id: str,
    token: str,
    payload: dict[str, Any] | None = None,
    api_version: str = DEFAULT_NOTION_API_VERSION,
    urlopen_fn: Callable[..., Any] = request.urlopen,
) -> dict[str, Any]:
    target_id = extract_notion_space_id(page_id)
    try:
        return _request_json(
            "PATCH",
            f"/pages/{target_id}",
            token=token,
            api_version=api_version,
            payload=payload or {},
            urlopen_fn=urlopen_fn,
        )
    except NotionApiError as exc:
        raise _friendly_api_error(exc, target=f"page {target_id}") from exc


def handshake_notion_space(
    *,
    space_url: str,
    token: str,
    api_version: str = DEFAULT_NOTION_API_VERSION,
    urlopen_fn: Callable[..., Any] = request.urlopen,
) -> dict[str, Any]:
    normalized_space_url = normalize_notion_space_url(space_url)
    normalized_token = str(token or "").strip()
    normalized_api_version = str(api_version or DEFAULT_NOTION_API_VERSION).strip() or DEFAULT_NOTION_API_VERSION

    if not normalized_space_url:
        raise RuntimeError("Notion page/database URL is required for the SSOT handshake")
    if not normalized_token:
        raise RuntimeError("Notion integration secret is required for the SSOT handshake")

    try:
        target_id = extract_notion_space_id(normalized_space_url)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    try:
        me_payload = _request_json(
            "GET",
            "/users/me",
            token=normalized_token,
            api_version=normalized_api_version,
            urlopen_fn=urlopen_fn,
        )
    except NotionApiError as exc:
        raise _friendly_api_error(exc, target="the Notion integration") from exc
    target = _resolve_target(
        token=normalized_token,
        api_version=normalized_api_version,
        target_id=target_id,
        urlopen_fn=urlopen_fn,
    )
    integration = _integration_summary(me_payload)
    return {
        "ok": True,
        "space_url": normalized_space_url,
        "space_id": target["id"],
        "space_kind": target["kind"],
        "space_title": target["title"],
        "target_url": normalize_notion_space_url(target["url"] or normalized_space_url),
        "api_version": normalized_api_version,
        "integration": integration,
    }
