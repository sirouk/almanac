#!/usr/bin/env python3
"""Back up and best-effort restore a Notion page subtree.

This utility is intentionally token-file based. Do not pass Notion tokens on
argv; process listings and shell history are the wrong place for secrets.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import re
import sys
import time
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path
from typing import Any


API_BASE = "https://api.notion.com/v1"
DEFAULT_API_VERSION = "2026-03-11"
MAX_BATCH_BLOCKS = 100
UUID_RE = re.compile(r"([0-9a-fA-F]{32}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})")

READ_ONLY_PROPERTY_TYPES = {
    "created_by",
    "created_time",
    "last_edited_by",
    "last_edited_time",
    "formula",
    "rollup",
    "unique_id",
    "verification",
}
WRITABLE_PROPERTY_TYPES = {
    "title",
    "rich_text",
    "number",
    "select",
    "multi_select",
    "status",
    "date",
    "checkbox",
    "url",
    "email",
    "phone_number",
    "files",
    "relation",
}
SCHEMA_PROPERTY_TYPES = {
    "title",
    "rich_text",
    "number",
    "select",
    "multi_select",
    "status",
    "date",
    "checkbox",
    "url",
    "email",
    "phone_number",
    "files",
}
TEXT_BLOCK_TYPES = {
    "paragraph",
    "heading_1",
    "heading_2",
    "heading_3",
    "bulleted_list_item",
    "numbered_list_item",
    "quote",
    "to_do",
    "toggle",
    "callout",
}
MEDIA_BLOCK_TYPES = {"image", "video", "pdf", "file", "audio"}
SIMPLE_BLOCK_TYPES = {"divider", "table_of_contents"}


class NotionError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def eprint(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def notion_id(ref: str) -> str:
    value = str(ref or "").strip()
    match = UUID_RE.search(value)
    if not match:
        raise SystemExit(f"Could not find a Notion page/database id in: {ref}")
    raw = match.group(1).replace("-", "").lower()
    return f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"


def read_token(path: Path) -> str:
    if not path.exists():
        raise SystemExit(f"Token file does not exist: {path}")
    token = path.read_text(encoding="utf-8").strip()
    if not token:
        raise SystemExit(f"Token file is empty: {path}")
    return token


class NotionClient:
    def __init__(self, token_file: Path, *, label: str, api_version: str) -> None:
        self.token_file = token_file
        self.label = label
        self.api_version = api_version
        self.token = read_token(token_file)

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": self.api_version,
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(f"{API_BASE}{path}", data=data, headers=headers, method=method)
        for attempt in range(1, 7):
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                    return json.loads(raw) if raw.strip() else {}
            except urllib.error.HTTPError as exc:
                raw = exc.read().decode("utf-8", errors="replace")
                detail = raw
                try:
                    parsed = json.loads(raw)
                    detail = str(parsed.get("message") or parsed.get("code") or raw)
                except Exception:
                    pass
                if exc.code in {429, 500, 502, 503, 504} and attempt < 6:
                    retry_after = exc.headers.get("Retry-After")
                    if retry_after:
                        delay = max(1.0, min(30.0, float(retry_after)))
                    else:
                        delay = min(30.0, 0.75 * (2 ** (attempt - 1))) + random.random()
                    time.sleep(delay)
                    continue
                raise NotionError(exc.code, f"{self.label} {method} {path}: {detail}") from exc
            except urllib.error.URLError as exc:
                if attempt < 6:
                    time.sleep(min(30.0, 0.75 * (2 ** (attempt - 1))) + random.random())
                    continue
                raise NotionError(0, f"{self.label} {method} {path}: {exc}") from exc
        raise NotionError(0, f"{self.label} {method} {path}: retry exhausted")

    def paged_get(self, path: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        cursor = ""
        while True:
            suffix = "?page_size=100"
            if cursor:
                suffix += f"&start_cursor={cursor}"
            response = self.request("GET", f"{path}{suffix}")
            items.extend([item for item in response.get("results") or [] if isinstance(item, dict)])
            if not response.get("has_more"):
                return items
            cursor = str(response.get("next_cursor") or "")

    def paged_post(self, path: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        cursor = ""
        while True:
            request_payload = dict(payload)
            request_payload["page_size"] = 100
            if cursor:
                request_payload["start_cursor"] = cursor
            response = self.request("POST", path, request_payload)
            items.extend([item for item in response.get("results") or [] if isinstance(item, dict)])
            if not response.get("has_more"):
                return items
            cursor = str(response.get("next_cursor") or "")


def rich_text_plain(value: list[dict[str, Any]]) -> str:
    return "".join(str(part.get("plain_text") or "") for part in value if isinstance(part, dict))


def sanitize_rich_text(value: Any, *, limit: int = 1900) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    used = 0
    for part in value:
        if not isinstance(part, dict):
            continue
        plain = str(part.get("plain_text") or "")
        if not plain:
            continue
        remaining = limit - used
        if remaining <= 0:
            break
        text = plain[:remaining]
        item: dict[str, Any] = {"type": "text", "text": {"content": text}}
        href = part.get("href")
        if href:
            item["text"]["link"] = {"url": str(href)}
        annotations = part.get("annotations")
        if isinstance(annotations, dict):
            item["annotations"] = {
                key: value
                for key, value in annotations.items()
                if key in {"bold", "italic", "strikethrough", "underline", "code", "color"}
            }
        out.append(item)
        used += len(text)
    return out


def page_title(page: dict[str, Any]) -> str:
    properties = page.get("properties") if isinstance(page.get("properties"), dict) else {}
    for prop in properties.values():
        if isinstance(prop, dict) and prop.get("type") == "title":
            title = rich_text_plain(prop.get("title") or [])
            return title.strip() or "(untitled)"
    return "(untitled)"


def data_source_title(data_source: dict[str, Any]) -> str:
    return rich_text_plain(data_source.get("title") or []).strip() or "(untitled)"


def database_title(database: dict[str, Any]) -> str:
    return rich_text_plain(database.get("title") or []).strip() or "(untitled)"


def page_parent(page: dict[str, Any]) -> tuple[str, str]:
    parent = page.get("parent") if isinstance(page.get("parent"), dict) else {}
    kind = str(parent.get("type") or "")
    if kind == "workspace":
        return kind, "workspace"
    return kind, str(parent.get(kind) or "")


def clean_select_options(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(payload)
    if isinstance(cleaned.get("options"), list):
        cleaned["options"] = [
            {key: value for key, value in option.items() if key in {"name", "color"}}
            for option in cleaned["options"]
            if isinstance(option, dict) and option.get("name")
        ]
    # Status groups contain source-workspace option ids. They are not portable,
    # so let Notion create destination-side default groups instead.
    cleaned.pop("groups", None)
    return cleaned


def sanitize_property_schema(properties: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, prop in properties.items():
        if not isinstance(prop, dict):
            continue
        prop_type = str(prop.get("type") or "")
        if prop_type not in SCHEMA_PROPERTY_TYPES:
            continue
        config = prop.get(prop_type)
        if not isinstance(config, dict):
            config = {}
        clean_config = json.loads(json.dumps(config))
        if prop_type in {"select", "multi_select", "status"}:
            clean_config = clean_select_options(clean_config)
        clean_config.pop("id", None)
        clean_prop = {prop_type: clean_config}
        description = prop.get("description")
        if isinstance(description, str) and description:
            clean_prop["description"] = description
        out[str(name)] = clean_prop
    if not any(isinstance(value, dict) and "title" in value for value in out.values()):
        out = {"Name": {"title": {}}, **out}
    return out


def sanitize_file_list(value: Any) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return files
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "Notion file")
        if item.get("type") == "external" and isinstance(item.get("external"), dict):
            url = item["external"].get("url")
            if url:
                files.append({"name": name, "type": "external", "external": {"url": str(url)}})
    return files


def sanitize_page_properties(properties: dict[str, Any], *, title_fallback: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    saw_title = False
    for name, prop in properties.items():
        if not isinstance(prop, dict):
            continue
        prop_type = str(prop.get("type") or "")
        if prop_type in READ_ONLY_PROPERTY_TYPES or prop_type not in WRITABLE_PROPERTY_TYPES:
            continue
        if prop_type == "title":
            saw_title = True
            out[str(name)] = {"title": sanitize_rich_text(prop.get("title") or []) or [{"type": "text", "text": {"content": title_fallback[:1900]}}]}
        elif prop_type == "rich_text":
            out[str(name)] = {"rich_text": sanitize_rich_text(prop.get("rich_text") or [])}
        elif prop_type in {"number", "checkbox", "url", "email", "phone_number"}:
            out[str(name)] = {prop_type: prop.get(prop_type)}
        elif prop_type == "date":
            out[str(name)] = {"date": prop.get("date")}
        elif prop_type in {"select", "status"}:
            option = prop.get(prop_type)
            out[str(name)] = {prop_type: {"name": option.get("name")} if isinstance(option, dict) and option.get("name") else None}
        elif prop_type == "multi_select":
            out[str(name)] = {"multi_select": [{"name": option.get("name")} for option in prop.get("multi_select") or [] if isinstance(option, dict) and option.get("name")]}
        elif prop_type == "files":
            out[str(name)] = {"files": sanitize_file_list(prop.get("files"))}
        elif prop_type == "relation":
            # Relations are restored in a later pass only when both sides are mapped.
            continue
    if not saw_title:
        out["title"] = {"title": [{"type": "text", "text": {"content": title_fallback[:1900]}}]}
    return out


def sanitize_page_parent_title(properties: dict[str, Any], *, title_fallback: str) -> dict[str, Any]:
    for prop in properties.values():
        if isinstance(prop, dict) and prop.get("type") == "title":
            title = sanitize_rich_text(prop.get("title") or [])
            if title:
                return {"title": title}
    return {"title": [{"type": "text", "text": {"content": title_fallback[:1900]}}]}


def fetch_block_tree(client: NotionClient, block_id: str, *, errors: list[dict[str, str]], seen_blocks: set[str]) -> list[dict[str, Any]]:
    if block_id in seen_blocks:
        errors.append({"kind": "block_children", "id": block_id, "error": "duplicate block traversal skipped"})
        return []
    seen_blocks.add(block_id)
    try:
        blocks = client.paged_get(f"/blocks/{block_id}/children")
    except NotionError as exc:
        errors.append({"kind": "block_children", "id": block_id, "error": exc.message})
        return []
    for block in blocks:
        if block.get("has_children"):
            block["_children"] = fetch_block_tree(client, str(block.get("id") or ""), errors=errors, seen_blocks=seen_blocks)
    return blocks


def child_database_ids(blocks: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    stack = list(blocks)
    while stack:
        block = stack.pop()
        if block.get("type") == "child_database":
            block_id = str(block.get("id") or "")
            if block_id:
                ids.append(block_id)
        stack.extend([child for child in block.get("_children") or [] if isinstance(child, dict)])
    return ids


def backup_page_tree(client: NotionClient, root_ref: str, output_dir: Path) -> dict[str, Any]:
    root_id = notion_id(root_ref)
    output_dir.mkdir(parents=True, exist_ok=True)
    errors: list[dict[str, str]] = []
    pages: dict[str, dict[str, Any]] = {}
    page_blocks: dict[str, list[dict[str, Any]]] = {}
    databases: dict[str, dict[str, Any]] = {}
    data_sources: dict[str, dict[str, Any]] = {}
    data_source_rows: dict[str, list[str]] = {}
    page_queue: deque[str] = deque([root_id])
    database_queue: deque[str] = deque()

    me = client.request("GET", "/users/me")
    while page_queue:
        page_id = page_queue.popleft()
        if page_id in pages:
            continue
        eprint(f"backup page {len(pages) + 1}: {page_id}")
        try:
            page = client.request("GET", f"/pages/{page_id}")
            pages[page_id] = page
        except NotionError as exc:
            errors.append({"kind": "page", "id": page_id, "error": exc.message})
            continue
        blocks = fetch_block_tree(client, page_id, errors=errors, seen_blocks=set())
        page_blocks[page_id] = blocks
        for block in blocks:
            stack = [block]
            while stack:
                current = stack.pop()
                block_type = current.get("type")
                block_id = str(current.get("id") or "")
                if block_type == "child_page" and block_id not in pages:
                    page_queue.append(block_id)
                elif block_type == "child_database" and block_id not in databases:
                    database_queue.append(block_id)
                stack.extend([child for child in current.get("_children") or [] if isinstance(child, dict)])
        while database_queue:
            database_id = database_queue.popleft()
            if database_id in databases:
                continue
            eprint(f"backup database {len(databases) + 1}: {database_id}")
            try:
                database = client.request("GET", f"/databases/{database_id}")
                databases[database_id] = database
            except NotionError as exc:
                errors.append({"kind": "database", "id": database_id, "error": exc.message})
                continue
            for data_source_ref in database.get("data_sources") or []:
                if not isinstance(data_source_ref, dict):
                    continue
                data_source_id = str(data_source_ref.get("id") or "")
                if not data_source_id or data_source_id in data_sources:
                    continue
                try:
                    data_source = client.request("GET", f"/data_sources/{data_source_id}")
                    data_sources[data_source_id] = data_source
                    rows = client.paged_post(f"/data_sources/{data_source_id}/query", {})
                    data_source_rows[data_source_id] = [str(row.get("id") or "") for row in rows if row.get("object") == "page"]
                    for row_id in data_source_rows[data_source_id]:
                        if row_id not in pages:
                            page_queue.append(row_id)
                except NotionError as exc:
                    errors.append({"kind": "data_source", "id": data_source_id, "error": exc.message})

    root_page = pages.get(root_id) or {}
    manifest = {
        "created_at": iso_now(),
        "api_version": client.api_version,
        "root_page_id": root_id,
        "root_page_title": page_title(root_page),
        "root_page_url": root_page.get("url"),
        "connection": {
            "id": me.get("id"),
            "name": me.get("name"),
            "workspace_name": (me.get("bot") or {}).get("workspace_name") if isinstance(me.get("bot"), dict) else "",
            "type": me.get("type"),
        },
        "counts": {
            "pages": len(pages),
            "databases": len(databases),
            "data_sources": len(data_sources),
            "database_rows": sum(len(rows) for rows in data_source_rows.values()),
            "errors": len(errors),
        },
        "errors": errors,
    }
    snapshot = {
        "manifest": manifest,
        "pages": pages,
        "page_blocks": page_blocks,
        "databases": databases,
        "data_sources": data_sources,
        "data_source_rows": data_source_rows,
    }
    (output_dir / "backup.json").write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def sanitize_icon_or_cover(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    value_type = value.get("type")
    if value_type == "emoji" and value.get("emoji"):
        return {"type": "emoji", "emoji": value.get("emoji")}
    if value_type == "external" and isinstance(value.get("external"), dict) and value["external"].get("url"):
        return {"type": "external", "external": {"url": value["external"]["url"]}}
    return None


def page_create_payload(page: dict[str, Any], parent: dict[str, str], *, title_override: str = "") -> dict[str, Any]:
    title = title_override.strip() or page_title(page)
    properties = page.get("properties") if isinstance(page.get("properties"), dict) else {}
    payload: dict[str, Any] = {
        "parent": parent,
        "properties": (
            sanitize_page_parent_title(properties, title_fallback=title)
            if parent.get("type") == "page_id"
            else sanitize_page_properties(properties, title_fallback=title)
        ),
    }
    icon = sanitize_icon_or_cover(page.get("icon"))
    cover = sanitize_icon_or_cover(page.get("cover"))
    if icon:
        payload["icon"] = icon
    if cover:
        payload["cover"] = cover
    return payload


def database_create_payload(database: dict[str, Any], data_source: dict[str, Any], parent_page_id: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": sanitize_rich_text(database.get("title") or []) or [{"type": "text", "text": {"content": database_title(database)}}],
        "initial_data_source": {
            "properties": sanitize_property_schema(data_source.get("properties") if isinstance(data_source.get("properties"), dict) else {})
        },
        "is_inline": bool(database.get("is_inline", True)),
    }
    description = sanitize_rich_text(database.get("description") or [])
    if description:
        payload["description"] = description
    icon = sanitize_icon_or_cover(database.get("icon"))
    cover = sanitize_icon_or_cover(database.get("cover"))
    if icon:
        payload["icon"] = icon
    if cover:
        payload["cover"] = cover
    return payload


def external_file_payload(block_type: str, block_payload: dict[str, Any]) -> dict[str, Any] | None:
    if isinstance(block_payload.get("external"), dict) and block_payload["external"].get("url"):
        return {
            block_type: {
                "type": "external",
                "external": {"url": block_payload["external"]["url"]},
                "caption": sanitize_rich_text(block_payload.get("caption") or []),
            }
        }
    return None


def block_placeholder(text: str) -> dict[str, Any]:
    return {
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": text[:1900]}}],
        },
    }


def block_create_payload(block: dict[str, Any]) -> dict[str, Any] | None:
    block_type = str(block.get("type") or "")
    payload = block.get(block_type) if isinstance(block.get(block_type), dict) else {}
    if block_type in {"child_page", "child_database"}:
        return None
    if block_type == "heading_4":
        body: dict[str, Any] = {
            "rich_text": sanitize_rich_text(payload.get("rich_text") or []),
            "color": payload.get("color", "default"),
        }
        if "is_toggleable" in payload:
            body["is_toggleable"] = bool(payload.get("is_toggleable"))
        return {"type": "heading_3", "heading_3": body}
    if block_type in TEXT_BLOCK_TYPES:
        body: dict[str, Any] = {
            "rich_text": sanitize_rich_text(payload.get("rich_text") or []),
            "color": payload.get("color", "default"),
        }
        if block_type in {"heading_1", "heading_2", "heading_3"} and "is_toggleable" in payload:
            body["is_toggleable"] = bool(payload.get("is_toggleable"))
        if block_type == "to_do":
            body["checked"] = bool(payload.get("checked", False))
        if block_type == "callout":
            icon = sanitize_icon_or_cover(payload.get("icon"))
            if icon:
                body["icon"] = icon
        return {"type": block_type, block_type: body}
    if block_type == "code":
        return {
            "type": "code",
            "code": {
                "rich_text": sanitize_rich_text(payload.get("rich_text") or [], limit=19000),
                "language": payload.get("language") or "plain text",
                "caption": sanitize_rich_text(payload.get("caption") or []),
            },
        }
    if block_type == "equation":
        return {"type": "equation", "equation": {"expression": str(payload.get("expression") or "")}}
    if block_type in SIMPLE_BLOCK_TYPES:
        return {"type": block_type, block_type: {}}
    if block_type in MEDIA_BLOCK_TYPES:
        media = external_file_payload(block_type, payload)
        return media or block_placeholder(f"[Notion transfer skipped {block_type} block with non-external file]")
    if block_type in {"embed", "bookmark", "link_preview"}:
        url = str(payload.get("url") or "")
        if url:
            create_type = "bookmark" if block_type == "link_preview" else block_type
            return {"type": create_type, create_type: {"url": url, "caption": sanitize_rich_text(payload.get("caption") or [])}}
        return None
    if block_type == "table":
        return {
            "type": "table",
            "table": {
                "table_width": int(payload.get("table_width") or 1),
                "has_column_header": bool(payload.get("has_column_header", False)),
                "has_row_header": bool(payload.get("has_row_header", False)),
            },
        }
    if block_type == "table_row":
        cells = []
        for cell in payload.get("cells") or []:
            cells.append(sanitize_rich_text(cell if isinstance(cell, list) else []))
        return {"type": "table_row", "table_row": {"cells": cells}}
    if block_type in {"breadcrumb", "column_list", "column", "synced_block", "template", "unsupported"}:
        return block_placeholder(f"[Notion transfer skipped {block_type} block]")
    return block_placeholder(f"[Notion transfer skipped unsupported block type: {block_type or 'unknown'}]")


def chunked(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


class Restorer:
    def __init__(self, client: NotionClient, snapshot: dict[str, Any], *, dry_run: bool) -> None:
        self.client = client
        self.snapshot = snapshot
        self.dry_run = dry_run
        self.id_map: dict[str, str] = {}
        self.warnings: list[str] = []
        self.ops: list[dict[str, str]] = []

    def op(self, kind: str, old_id: str, title: str = "") -> None:
        self.ops.append({"kind": kind, "old_id": old_id, "title": title})
        if self.dry_run:
            eprint(f"dry-run {kind}: {title or old_id}")
        else:
            eprint(f"restore {kind}: {title or old_id}")

    def create_page(self, old_page_id: str, parent: dict[str, str], *, title_override: str = "") -> str:
        if old_page_id in self.id_map:
            return self.id_map[old_page_id]
        page = self.snapshot["pages"][old_page_id]
        title = title_override.strip() or page_title(page)
        self.op("page", old_page_id, title)
        if self.dry_run:
            new_id = f"dry-run-page-{len(self.id_map) + 1}"
        else:
            created = self.client.request("POST", "/pages", page_create_payload(page, parent, title_override=title_override))
            new_id = str(created.get("id") or "")
        self.id_map[old_page_id] = new_id
        self.restore_blocks(old_page_id, new_id)
        return new_id

    def create_database(self, old_database_id: str, parent_page_id: str) -> str:
        if old_database_id in self.id_map:
            return self.id_map[old_database_id]
        database = self.snapshot["databases"].get(old_database_id)
        if not isinstance(database, dict):
            self.warnings.append(f"database {old_database_id} was referenced but not present in backup")
            return ""
        data_source_refs = [item for item in database.get("data_sources") or [] if isinstance(item, dict) and item.get("id")]
        old_data_source_id = str(data_source_refs[0].get("id") or "") if data_source_refs else ""
        data_source = self.snapshot["data_sources"].get(old_data_source_id) or {}
        self.op("database", old_database_id, database_title(database))
        if self.dry_run:
            new_database_id = f"dry-run-database-{len(self.id_map) + 1}"
            new_data_source_id = f"dry-run-data-source-{len(self.id_map) + 1}"
        else:
            created = self.client.request("POST", "/databases", database_create_payload(database, data_source, parent_page_id))
            new_database_id = str(created.get("id") or "")
            created_sources = created.get("data_sources") if isinstance(created.get("data_sources"), list) else []
            new_data_source_id = str((created_sources[0] if created_sources else {}).get("id") or "")
        self.id_map[old_database_id] = new_database_id
        if old_data_source_id and new_data_source_id:
            self.id_map[old_data_source_id] = new_data_source_id
            for row_id in self.snapshot.get("data_source_rows", {}).get(old_data_source_id, []):
                if row_id in self.snapshot["pages"]:
                    self.create_page(row_id, {"type": "data_source_id", "data_source_id": new_data_source_id})
        return new_database_id

    def append_blocks(self, parent_id: str, blocks: list[dict[str, Any]]) -> list[str]:
        payloads = [payload for payload in (block_create_payload(block) for block in blocks) if payload is not None]
        new_ids: list[str] = []
        if not payloads:
            return new_ids
        if self.dry_run:
            return [f"dry-run-block-{len(self.ops)}-{index}" for index, _ in enumerate(payloads, start=1)]
        for batch in chunked(payloads, MAX_BATCH_BLOCKS):
            response = self.client.request("PATCH", f"/blocks/{parent_id}/children", {"children": batch})
            new_ids.extend(str(item.get("id") or "") for item in response.get("results") or [] if isinstance(item, dict))
        return new_ids

    def restore_blocks(self, old_page_id: str, new_page_id: str) -> None:
        blocks = self.snapshot.get("page_blocks", {}).get(old_page_id, [])
        for block in blocks:
            block_type = str(block.get("type") or "")
            old_block_id = str(block.get("id") or "")
            if block_type == "child_page":
                self.create_page(old_block_id, {"type": "page_id", "page_id": new_page_id})
                continue
            if block_type == "child_database":
                self.create_database(old_block_id, new_page_id)
                continue
            new_ids = self.append_blocks(new_page_id, [block])
            if old_block_id and new_ids:
                self.id_map[old_block_id] = new_ids[0]
                children = [child for child in block.get("_children") or [] if isinstance(child, dict)]
                if children:
                    self.restore_child_blocks(children, new_ids[0])

    def restore_child_blocks(self, blocks: list[dict[str, Any]], new_parent_id: str) -> None:
        for block in blocks:
            block_type = str(block.get("type") or "")
            old_block_id = str(block.get("id") or "")
            if block_type == "child_page":
                self.create_page(old_block_id, {"type": "page_id", "page_id": new_parent_id})
                continue
            if block_type == "child_database":
                self.create_database(old_block_id, new_parent_id)
                continue
            new_ids = self.append_blocks(new_parent_id, [block])
            if old_block_id and new_ids:
                self.id_map[old_block_id] = new_ids[0]
                children = [child for child in block.get("_children") or [] if isinstance(child, dict)]
                if children:
                    self.restore_child_blocks(children, new_ids[0])


def restore_backup(client: NotionClient, backup_dir: Path, dest_parent_ref: str, *, title: str, dry_run: bool) -> dict[str, Any]:
    backup_path = backup_dir / "backup.json"
    snapshot = json.loads(backup_path.read_text(encoding="utf-8"))
    root_page_id = str(snapshot.get("manifest", {}).get("root_page_id") or "")
    if not root_page_id:
        raise SystemExit(f"Backup has no root_page_id: {backup_path}")
    dest_parent_id = notion_id(dest_parent_ref)
    # Verify destination page access before a dry-run or write run.
    client.request("GET", f"/pages/{dest_parent_id}")
    restorer = Restorer(client, snapshot, dry_run=dry_run)
    new_root_id = restorer.create_page(root_page_id, {"type": "page_id", "page_id": dest_parent_id}, title_override=title)
    result = {
        "ok": True,
        "dry_run": dry_run,
        "backup_dir": str(backup_dir),
        "dest_parent_id": dest_parent_id,
        "new_root_id": new_root_id,
        "operation_counts": {},
        "warnings": restorer.warnings,
    }
    counts: dict[str, int] = {}
    for op in restorer.ops:
        counts[op["kind"]] = counts.get(op["kind"], 0) + 1
    result["operation_counts"] = counts
    (backup_dir / ("restore-dry-run.json" if dry_run else "restore-result.json")).write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def discover(client: NotionClient) -> dict[str, Any]:
    me = client.request("GET", "/users/me")
    pages = client.paged_post("/search", {"filter": {"property": "object", "value": "page"}})
    data_sources = client.paged_post("/search", {"filter": {"property": "object", "value": "data_source"}})
    return {
        "connection": {
            "id": me.get("id"),
            "name": me.get("name"),
            "workspace_name": (me.get("bot") or {}).get("workspace_name") if isinstance(me.get("bot"), dict) else "",
            "type": me.get("type"),
        },
        "pages": [{"id": item.get("id"), "title": page_title(item), "url": item.get("url"), "parent": item.get("parent")} for item in pages],
        "data_sources": [{"id": item.get("id"), "title": data_source_title(item), "url": item.get("url"), "parent": item.get("parent")} for item in data_sources],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Back up and best-effort restore a Notion page subtree.")
    parser.add_argument("--api-version", default=DEFAULT_API_VERSION)
    sub = parser.add_subparsers(dest="command", required=True)

    discover_parser = sub.add_parser("discover", help="List connection identity and visible pages/data sources.")
    discover_parser.add_argument("--token-file", required=True, type=Path)
    discover_parser.add_argument("--label", default="notion")

    backup_parser = sub.add_parser("backup", help="Back up a source root page subtree.")
    backup_parser.add_argument("--source-token-file", required=True, type=Path)
    backup_parser.add_argument("--source-root", required=True)
    backup_parser.add_argument("--output-dir", required=True, type=Path)

    restore_parser = sub.add_parser("restore", help="Restore a backup under a destination parent page.")
    restore_parser.add_argument("--dest-token-file", required=True, type=Path)
    restore_parser.add_argument("--backup-dir", required=True, type=Path)
    restore_parser.add_argument("--dest-parent", required=True)
    restore_parser.add_argument("--title", default="")
    restore_parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    if args.command == "discover":
        client = NotionClient(args.token_file, label=args.label, api_version=args.api_version)
        print(json.dumps(discover(client), indent=2, sort_keys=True))
        return 0
    if args.command == "backup":
        client = NotionClient(args.source_token_file, label="source", api_version=args.api_version)
        manifest = backup_page_tree(client, args.source_root, args.output_dir)
        print(json.dumps({"ok": True, "output_dir": str(args.output_dir), "manifest": manifest}, indent=2, sort_keys=True))
        return 0
    if args.command == "restore":
        client = NotionClient(args.dest_token_file, label="destination", api_version=args.api_version)
        result = restore_backup(client, args.backup_dir, args.dest_parent, title=args.title, dry_run=args.dry_run)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
