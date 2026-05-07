from __future__ import annotations

import email.utils
import json
import mimetypes
import os
from pathlib import Path
import posixpath
import re
import shutil
import tempfile
import time
from typing import Any
import urllib.parse
import xml.etree.ElementTree as ET

try:
    from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
    from fastapi.responses import FileResponse, Response
except Exception:
    class HTTPException(Exception):  # type: ignore
        def __init__(self, status_code: int = 500, detail: str = "") -> None:
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class APIRouter:  # type: ignore
        def get(self, *_args, **_kwargs):
            return lambda fn: fn

        def post(self, *_args, **_kwargs):
            return lambda fn: fn

        def put(self, *_args, **_kwargs):
            return lambda fn: fn

        def delete(self, *_args, **_kwargs):
            return lambda fn: fn

    class Request:  # type: ignore
        pass

    class UploadFile:  # type: ignore
        pass

    class Response:  # type: ignore
        def __init__(
            self,
            content: bytes = b"",
            media_type: str = "application/octet-stream",
            headers: dict[str, str] | None = None,
        ) -> None:
            self.content = content
            self.media_type = media_type
            self.headers = {str(key).lower(): value for key, value in (headers or {}).items()}

    class FileResponse:  # type: ignore
        def __init__(
            self,
            path: str,
            filename: str | None = None,
            media_type: str | None = None,
            headers: dict[str, str] | None = None,
        ) -> None:
            self.path = path
            self.filename = filename
            self.media_type = media_type
            self.headers = {str(key).lower(): value for key, value in (headers or {}).items()}

    def File(default: Any = None, **_kwargs: Any) -> Any:  # type: ignore
        return default

    def Form(default: Any = None, **_kwargs: Any) -> Any:  # type: ignore
        return default


router = APIRouter()

_DAV_NS = {"d": "DAV:", "oc": "http://owncloud.org/ns"}
_TEXT_EXTENSIONS = {
    ".css",
    ".csv",
    ".env",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".log",
    ".md",
    ".mdx",
    ".py",
    ".rst",
    ".sh",
    ".text",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
_TRASH_DIR_NAME = ".drive-trash"
_SKIP_DIR_NAMES = {".git", ".hg", ".svn", "__pycache__", "node_modules", _TRASH_DIR_NAME}
_MAX_TEXT_BYTES = 1_000_000
_SEARCH_LIMIT = 300


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes")).expanduser()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _clean_url(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith(("https://", "http://")):
        return text
    return ""


def _clean_text(value: Any, limit: int = 160) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def _env_first(*keys: str) -> str:
    for key in keys:
        value = str(os.environ.get(key) or "").strip()
        if value:
            return value
    return ""


def _inline_content_disposition(filename: str) -> str:
    safe = re.sub(r'[\r\n"]+', "_", filename or "preview")
    encoded = urllib.parse.quote(filename or "preview", safe="")
    return f'inline; filename="{safe}"; filename*=UTF-8\'\'{encoded}'


def _first_url(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        url = _clean_url(payload.get(key))
        if url:
            return url
    return ""


def _access_state() -> tuple[dict[str, Any], dict[str, Any]]:
    state_dir = _hermes_home() / "state"
    return (
        _load_json(state_dir / "web-access.json"),
        _load_json(state_dir / "vault-reconciler.json"),
    )


def _nextcloud_surface(access: dict[str, Any], managed: dict[str, Any]) -> dict[str, Any]:
    return {
        "available": False,
        "url": "",
        "mount": _clean_text(access.get("nextcloud_mount") or access.get("nextcloud_mount_point"), 80) or "/Vault",
        "username": "",
        "source": "",
    }


def _candidate_vault_roots() -> list[Path]:
    home = Path(os.environ.get("HOME") or str(Path.home())).expanduser()
    candidates: list[Path] = []
    for value in (
        os.environ.get("DRIVE_ROOT"),
        os.environ.get("KNOWLEDGE_VAULT_ROOT"),
        os.environ.get("AGENT_VAULT_DIR"),
        os.environ.get("VAULT_DIR"),
    ):
        if value:
            candidates.append(Path(value).expanduser())
    candidates.extend(
        [
            home / "Vault",
            _hermes_home() / "Vault",
        ]
    )
    return candidates


def _candidate_workspace_roots() -> list[Path]:
    home = Path(os.environ.get("HOME") or str(Path.home())).expanduser()
    candidates: list[Path] = []
    for value in (
        os.environ.get("DRIVE_WORKSPACE_ROOT"),
        os.environ.get("CODE_WORKSPACE_ROOT"),
    ):
        if value:
            candidates.append(Path(value).expanduser())
    candidates.extend(
        [
            home,
            _hermes_home() / "workspace",
        ]
    )
    return candidates


def _first_existing_dir(candidates: list[Path]) -> Path | None:
    for candidate in candidates:
        try:
            if candidate.is_dir():
                return candidate.resolve(strict=False)
        except OSError:
            continue
    return None


def _local_root() -> Path | None:
    return _first_existing_dir(_candidate_vault_roots())


def _root_capabilities(*, available: bool, backend: str, webdav_available: bool = False) -> dict[str, bool]:
    local = bool(available and backend == "local")
    return {
        "batch": local,
        "copy": local,
        "delete": local,
        "download": local or backend == "nextcloud-webdav",
        "drag_drop_upload": local or backend == "nextcloud-webdav",
        "duplicate": local,
        "favorites": False,
        "folders": local or backend == "nextcloud-webdav",
        "move": local or backend == "nextcloud-webdav",
        "new_file": local,
        "preview": local or backend == "nextcloud-webdav",
        "rename": local or backend == "nextcloud-webdav",
        "restore": local,
        "search": local,
        "sharing": False,
        "trash": local,
        "upload": local or backend == "nextcloud-webdav",
        "nextcloud_webdav": bool(webdav_available),
    }


def _root_descriptor(root_id: str, label: str, root: Path | None, *, webdav_available: bool = False) -> dict[str, Any]:
    available = root is not None
    return {
        "id": root_id,
        "label": label,
        "available": available,
        "backend": "local" if available else "unavailable",
        "path": str(root) if root else "",
        "capabilities": _root_capabilities(
            available=available,
            backend="local" if available else "unavailable",
            webdav_available=webdav_available,
        ),
    }


def _local_root_descriptors(webdav_available: bool = False) -> list[dict[str, Any]]:
    return [
        _root_descriptor("vault", "Vault", _first_existing_dir(_candidate_vault_roots()), webdav_available=webdav_available),
        _root_descriptor(
            "workspace",
            "Workspace",
            _first_existing_dir(_candidate_workspace_roots()),
            webdav_available=webdav_available,
        ),
    ]


def _default_root_id(roots: list[dict[str, Any]]) -> str:
    for preferred in ("vault", "workspace"):
        for root in roots:
            if root.get("id") == preferred and root.get("available"):
                return preferred
    return ""


def _root_context(raw_root: Any = None) -> dict[str, Any]:
    root_id = str(raw_root or "").strip().lower()
    roots = _local_root_descriptors()
    if not root_id:
        root_id = _default_root_id(roots)
    if root_id not in {"vault", "workspace"}:
        raise HTTPException(status_code=400, detail="Unknown Drive root")
    for root in roots:
        if root["id"] == root_id:
            if not root.get("available"):
                raise HTTPException(status_code=404, detail=f"{root['label']} root is not available")
            return root
    raise HTTPException(status_code=404, detail="Drive root is not available")


def _meta_path() -> Path:
    return _hermes_home() / "state" / "drive-meta.json"


def _load_meta() -> dict[str, Any]:
    meta = _load_json(_meta_path())
    favorites = meta.get("favorites")
    if not isinstance(favorites, dict):
        favorites = {}
    trash = meta.get("trash")
    if not isinstance(trash, dict):
        trash = {}
    return {"favorites": favorites, "trash": trash}


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".drive-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _save_meta(meta: dict[str, Any]) -> None:
    _write_json_atomic(_meta_path(), meta)


def _root_meta(meta: dict[str, Any], key: str, root_id: str) -> dict[str, Any]:
    bucket = meta.setdefault(key, {})
    if not isinstance(bucket, dict):
        bucket = {}
        meta[key] = bucket
    root_bucket = bucket.get(root_id)
    if not isinstance(root_bucket, dict):
        legacy_values = {path: value for path, value in bucket.items() if isinstance(path, str) and path.startswith("/")}
        root_bucket = legacy_values if root_id == "vault" and legacy_values else {}
        for path in legacy_values:
            bucket.pop(path, None)
        bucket[root_id] = root_bucket
    return root_bucket


def _clean_relative_path(raw_path: Any) -> str:
    text = str(raw_path or "/").replace("\\", "/").strip()
    if text in {"", "/", "."}:
        return ""
    text = text.lstrip("/")
    parts: list[str] = []
    for part in text.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            raise HTTPException(status_code=400, detail="Path traversal is not allowed")
        parts.append(part)
    return "/".join(parts)


def _display_path(relative_path: str) -> str:
    return "/" + relative_path.strip("/") if relative_path else "/"


def _error_display_path(raw_path: Any) -> str:
    try:
        return _display_path(_clean_relative_path(raw_path))
    except HTTPException:
        return "<invalid path>"


def _join_display(parent: str, name: str) -> str:
    parent_rel = _clean_relative_path(parent)
    return _display_path(posixpath.join(parent_rel, name) if parent_rel else name)


def _sanitized_name(raw_name: Any) -> str:
    name = Path(str(raw_name or "")).name.strip()
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=400, detail="Name cannot be blank")
    return name


def _resolve_local(root: Path, raw_path: Any) -> tuple[Path, str]:
    relative_path = _clean_relative_path(raw_path)
    target = (root / relative_path).resolve(strict=False)
    root_resolved = root.resolve(strict=False)
    if target != root_resolved and root_resolved not in target.parents:
        raise HTTPException(status_code=403, detail="Path is outside the selected Drive root")
    return target, relative_path


def _assert_within_root(root: Path, path: Path) -> None:
    resolved = path.resolve(strict=False)
    root_resolved = root.resolve(strict=False)
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise HTTPException(status_code=403, detail="Path is outside the selected Drive root")


def _safe_child_relative(root: Path, path: Path) -> str | None:
    try:
        _assert_within_root(root, path)
        return path.relative_to(root).as_posix()
    except (HTTPException, ValueError, OSError):
        return None


def _trash_root(root: Path) -> Path:
    return (root / _TRASH_DIR_NAME).resolve(strict=False)


def _next_trash_path(root: Path, relative_path: str) -> Path:
    trash_root = _trash_root(root)
    trash_root.mkdir(parents=True, exist_ok=True)
    safe_tail = relative_path.replace("/", "__").strip("_") or "item"
    safe_tail = re.sub(r"[^A-Za-z0-9._-]+", "_", safe_tail)[:140] or "item"
    base = f"{int(time.time())}-{safe_tail}"
    candidate = trash_root / base
    counter = 1
    while candidate.exists():
        candidate = trash_root / f"{base}-{counter}"
        counter += 1
    return candidate


def _is_text_item(path: Path) -> bool:
    if path.suffix.lower() in _TEXT_EXTENSIONS:
        return True
    mime = mimetypes.guess_type(str(path))[0] or ""
    return mime.startswith("text/") or mime in {"application/json", "application/xml"}


def _iso_from_timestamp(value: float) -> str:
    return email.utils.formatdate(value, usegmt=True)


def _item_from_local(root_id: str, root: Path, path: Path, relative_path: str, meta: dict[str, Any]) -> dict[str, Any]:
    _assert_within_root(root, path)
    try:
        stat = path.stat()
    except OSError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    is_dir = path.is_dir()
    mime = "inode/directory" if is_dir else (mimetypes.guess_type(str(path))[0] or "application/octet-stream")
    display = _display_path(relative_path)
    return {
        "name": path.name or "Drive",
        "root": root_id,
        "path": display,
        "kind": "folder" if is_dir else "file",
        "size": 0 if is_dir else stat.st_size,
        "modified": _iso_from_timestamp(stat.st_mtime),
        "mime": mime,
        "favorite": bool(_root_meta(meta, "favorites", root_id).get(display)),
        "text": bool((not is_dir) and _is_text_item(path) and stat.st_size <= _MAX_TEXT_BYTES),
    }


def _should_skip(path: Path) -> bool:
    return path.name in _SKIP_DIR_NAMES


def _list_local(root_id: str, root: Path, raw_path: Any, *, query: str = "", favorites_only: bool = False) -> dict[str, Any]:
    meta = _load_meta()
    items: list[dict[str, Any]] = []
    if query.strip():
        needle = query.strip().lower()
        for current_root, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                name
                for name in dirnames
                if name not in _SKIP_DIR_NAMES and _safe_child_relative(root, Path(current_root) / name) is not None
            ]
            for name in sorted([*dirnames, *filenames]):
                if needle not in name.lower():
                    continue
                candidate = Path(current_root) / name
                relative = _safe_child_relative(root, candidate)
                if relative is None:
                    continue
                item = _item_from_local(root_id, root, candidate, relative, meta)
                if favorites_only and not item["favorite"]:
                    continue
                items.append(item)
                if len(items) >= _SEARCH_LIMIT:
                    break
            if len(items) >= _SEARCH_LIMIT:
                break
        current_path = "/"
    else:
        target, relative = _resolve_local(root, raw_path)
        if not target.exists():
            raise HTTPException(status_code=404, detail="Vault path does not exist")
        if not target.is_dir():
            raise HTTPException(status_code=400, detail="Vault path is not a folder")
        safe_children = [child for child in target.iterdir() if _safe_child_relative(root, child) is not None]
        for child in sorted(safe_children, key=lambda value: (not value.is_dir(), value.name.lower())):
            if _should_skip(child):
                continue
            child_relative = _safe_child_relative(root, child)
            if child_relative is None:
                continue
            item = _item_from_local(root_id, root, child, child_relative, meta)
            if favorites_only and not item["favorite"]:
                continue
            items.append(item)
        current_path = _display_path(relative)
    return {
        "backend": "local-vault",
        "root": root_id,
        "path": current_path,
        "items": items,
        "query": query.strip(),
        "favorites_only": bool(favorites_only),
    }


def _move_local(root_id: str, root: Path, source_path: Any, destination_path: Any) -> dict[str, Any]:
    source, source_relative = _resolve_local(root, source_path)
    destination, destination_relative = _resolve_local(root, destination_path)
    if not source.exists():
        raise HTTPException(status_code=404, detail="Drive source path does not exist")
    if source == root:
        raise HTTPException(status_code=400, detail="Cannot move the Drive root")
    if destination.exists():
        raise HTTPException(status_code=409, detail="Destination already exists")
    if source.is_dir() and (destination == source or source in destination.parents):
        raise HTTPException(status_code=400, detail="Cannot move a folder into itself")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    meta = _load_meta()
    favorites = _root_meta(meta, "favorites", root_id)
    source_display = _display_path(source_relative)
    destination_display = _display_path(destination_relative)
    for favorite_path in list(favorites):
        if favorite_path == source_display or favorite_path.startswith(source_display + "/"):
            favorites[destination_display + favorite_path[len(source_display) :]] = favorites.pop(favorite_path)
    if source_display == destination_display:
        favorites[destination_display] = True
    _save_meta(meta)
    return {"ok": True, "root": root_id, "path": source_display, "destination": destination_display}


def _rename_destination(raw_path: Any, raw_name: Any) -> str:
    relative = _clean_relative_path(raw_path)
    if not relative:
        raise HTTPException(status_code=400, detail="Cannot rename the Drive root")
    name = _sanitized_name(raw_name)
    parent = posixpath.dirname(relative)
    return _display_path(posixpath.join(parent, name) if parent else name)


def _assert_no_symlink_escape(root: Path, target: Path) -> None:
    if target.is_symlink():
        resolved = target.resolve(strict=False)
        root_resolved = root.resolve(strict=False)
        if resolved != root_resolved and root_resolved not in resolved.parents:
            raise HTTPException(status_code=403, detail="Symlink escapes are not allowed")
    if target.is_dir():
        for current_root, dirnames, filenames in os.walk(target, followlinks=False):
            current = Path(current_root)
            for name in [*dirnames, *filenames]:
                candidate = current / name
                if candidate.is_symlink():
                    resolved = candidate.resolve(strict=False)
                    root_resolved = root.resolve(strict=False)
                    if resolved != root_resolved and root_resolved not in resolved.parents:
                        raise HTTPException(status_code=403, detail="Symlink escapes are not allowed")


def _keep_both_destination(destination: Path) -> Path:
    if not destination.exists():
        return destination
    parent = destination.parent
    stem = destination.stem[:-5] if destination.stem.endswith(" copy") else destination.stem
    suffix = destination.suffix
    for counter in range(2, 1000):
        candidate = parent / f"{stem} copy {counter}{suffix}"
        if not candidate.exists():
            return candidate
    raise HTTPException(status_code=409, detail="Could not find a non-conflicting destination")


def _resolve_conflict_destination(destination: Path, *, conflict: str) -> Path:
    policy = str(conflict or "reject").strip().lower()
    if policy not in {"reject", "keep-both"}:
        raise HTTPException(status_code=400, detail="Unsupported conflict policy")
    if destination.exists():
        if policy == "keep-both":
            return _keep_both_destination(destination)
        raise HTTPException(status_code=409, detail="Destination already exists")
    return destination


def _copy_local(root_id: str, root: Path, source_path: Any, destination_path: Any, *, conflict: str = "reject") -> dict[str, Any]:
    source, source_relative = _resolve_local(root, source_path)
    destination, destination_relative = _resolve_local(root, destination_path)
    if not source.exists():
        raise HTTPException(status_code=404, detail="Drive source path does not exist")
    if source == root:
        raise HTTPException(status_code=400, detail="Cannot copy the Drive root")
    if source.is_dir() and (destination == source or source in destination.parents):
        raise HTTPException(status_code=400, detail="Cannot copy a folder into itself")
    _assert_no_symlink_escape(root, source)
    destination = _resolve_conflict_destination(destination, conflict=conflict)
    destination_relative = destination.relative_to(root).as_posix()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination, symlinks=True)
    else:
        shutil.copy2(source, destination, follow_symlinks=False)
    return {
        "ok": True,
        "root": root_id,
        "path": _display_path(source_relative),
        "destination": _display_path(destination_relative),
    }


def _duplicate_destination(raw_path: Any) -> str:
    relative = _clean_relative_path(raw_path)
    if not relative:
        raise HTTPException(status_code=400, detail="Cannot duplicate the Drive root")
    parent = posixpath.dirname(relative)
    name = posixpath.basename(relative)
    stem = Path(name).stem
    suffix = Path(name).suffix
    duplicate_name = f"{stem} copy{suffix}" if suffix else f"{name} copy"
    return _display_path(posixpath.join(parent, duplicate_name) if parent else duplicate_name)


def _move_webdav(profile: dict[str, Any], source_path: Any, destination_path: Any) -> dict[str, Any]:
    source_display = _display_path(_clean_relative_path(source_path))
    destination_display = _display_path(_clean_relative_path(destination_path))
    if source_display == "/":
        raise HTTPException(status_code=400, detail="Cannot move the vault root")
    _dav_request(
        profile,
        "MOVE",
        source_display,
        headers={"Destination": _webdav_url(profile, destination_display), "Overwrite": "F"},
    )
    meta = _load_meta()
    favorites = meta.setdefault("favorites", {})
    for favorite_path in list(favorites):
        if favorite_path == source_display or favorite_path.startswith(source_display + "/"):
            favorites[destination_display + favorite_path[len(source_display) :]] = favorites.pop(favorite_path)
    _save_meta(meta)
    return {"ok": True, "path": source_display, "destination": destination_display}


def _webdav_profile(nextcloud: dict[str, Any]) -> dict[str, Any]:
    return {"available": False}


def _webdav_url(profile: dict[str, Any], raw_path: Any) -> str:
    relative = _clean_relative_path(raw_path)
    base = str(profile["webdav_base"]).rstrip("/")
    if not relative:
        return base
    return f"{base}/{urllib.parse.quote(relative, safe='/')}"


def _dav_request(
    profile: dict[str, Any],
    method: str,
    raw_path: Any,
    *,
    body: bytes | str | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, bytes, dict[str, str]]:
    raise HTTPException(status_code=501, detail="Nextcloud WebDAV access is disabled; use the local Drive backend.")


def _propfind_body() -> str:
    return """<?xml version="1.0"?>
<d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns">
  <d:prop>
    <d:getcontentlength />
    <d:getcontenttype />
    <d:getlastmodified />
    <d:resourcetype />
    <oc:favorite />
  </d:prop>
</d:propfind>
"""


def _text_from(element: ET.Element | None, xpath: str) -> str:
    if element is None:
        return ""
    found = element.find(xpath, _DAV_NS)
    return "" if found is None or found.text is None else found.text


def _dav_relative_from_href(profile: dict[str, Any], href: str) -> str:
    href_path = urllib.parse.unquote(urllib.parse.urlparse(href).path).rstrip("/")
    base_path = urllib.parse.unquote(urllib.parse.urlparse(str(profile["webdav_base"])).path).rstrip("/")
    if href_path == base_path:
        return ""
    if href_path.startswith(base_path + "/"):
        return href_path[len(base_path) + 1 :]
    return posixpath.basename(href_path)


def _item_from_dav(profile: dict[str, Any], response: ET.Element, meta: dict[str, Any]) -> dict[str, Any]:
    href = _text_from(response, "d:href")
    relative = _dav_relative_from_href(profile, href)
    prop = response.find("d:propstat/d:prop", _DAV_NS)
    resource_type = prop.find("d:resourcetype/d:collection", _DAV_NS) if prop is not None else None
    is_dir = resource_type is not None
    display = _display_path(relative)
    size_text = _text_from(prop, "d:getcontentlength")
    try:
        size = int(size_text or "0")
    except ValueError:
        size = 0
    mime = "inode/directory" if is_dir else (_text_from(prop, "d:getcontenttype") or "application/octet-stream")
    favorite = _text_from(prop, "oc:favorite") == "1" or bool((meta.get("favorites") or {}).get(display))
    suffix = Path(relative).suffix.lower()
    return {
        "name": posixpath.basename(relative.rstrip("/")) or "Drive",
        "path": display,
        "kind": "folder" if is_dir else "file",
        "size": 0 if is_dir else size,
        "modified": _text_from(prop, "d:getlastmodified"),
        "mime": mime,
        "favorite": favorite,
        "text": bool((not is_dir) and (mime.startswith("text/") or suffix in _TEXT_EXTENSIONS) and size <= _MAX_TEXT_BYTES),
    }


def _list_dav(profile: dict[str, Any], raw_path: Any, *, query: str = "", favorites_only: bool = False) -> dict[str, Any]:
    if query.strip():
        raise HTTPException(status_code=400, detail="Search is available through the local vault backend")
    _status, body, _headers = _dav_request(
        profile,
        "PROPFIND",
        raw_path,
        body=_propfind_body(),
        headers={"Depth": "1", "Content-Type": "application/xml"},
    )
    meta = _load_meta()
    root = ET.fromstring(body)
    items: list[dict[str, Any]] = []
    current_path = _display_path(_clean_relative_path(raw_path))
    for response in root.findall("d:response", _DAV_NS):
        item = _item_from_dav(profile, response, meta)
        if item["path"] == current_path:
            continue
        if favorites_only and not item["favorite"]:
            continue
        items.append(item)
    items.sort(key=lambda item: (item["kind"] != "folder", str(item["name"]).lower()))
    return {
        "backend": "nextcloud-webdav",
        "path": current_path,
        "items": items,
        "query": "",
        "favorites_only": bool(favorites_only),
    }


def _backend() -> dict[str, Any]:
    access, managed = _access_state()
    nextcloud = _nextcloud_surface(access, managed)
    webdav = _webdav_profile(nextcloud)
    local = _local_root()
    preferred = str(
        _env_first(
            "DRIVE_BACKEND",
            "KNOWLEDGE_VAULT_BACKEND",
        )
        or "auto"
    ).strip().lower()
    if preferred in {"nextcloud", "nextcloud-webdav", "webdav"} and webdav.get("available"):
        return {"name": "nextcloud-webdav", "profile": webdav, "local_root": local, "nextcloud": nextcloud}
    if local is not None:
        return {"name": "local-vault", "root": local, "profile": webdav, "nextcloud": nextcloud}
    if webdav.get("available"):
        return {"name": "nextcloud-webdav", "profile": webdav, "local_root": local, "nextcloud": nextcloud}
    return {"name": "unavailable", "nextcloud": nextcloud}


@router.get("/status")
async def status() -> dict[str, Any]:
    backend = _backend()
    nextcloud = dict(backend.get("nextcloud") or {})
    nextcloud.pop("password", None)
    webdav_available = bool((backend.get("profile") or {}).get("available"))
    roots = _local_root_descriptors(webdav_available=webdav_available)
    default_root = _default_root_id(roots)
    root = next((item for item in roots if item.get("id") == default_root), None)
    available = bool(default_root)
    return {
        "plugin": "drive",
        "label": "Drive",
        "version": "1.0.0",
        "status_contract": 1,
        "available": available or backend["name"] == "nextcloud-webdav",
        "backend": "local-roots" if available else backend["name"],
        "roots": roots,
        "default_root": default_root,
        "mount": nextcloud.get("mount") or "/Vault",
        "username": nextcloud.get("username") or "",
        "url": nextcloud.get("url") or "",
        "source": nextcloud.get("source") or "",
        "local_root": str(root.get("path") or "") if root else "",
        "capabilities": dict(root.get("capabilities") or {}) if root else _root_capabilities(
            available=backend["name"] == "nextcloud-webdav",
            backend=backend["name"],
            webdav_available=webdav_available,
        ),
    }


@router.get("/items")
async def items(path: str = "/", query: str = "", favorites_only: bool = False, root: str = "") -> dict[str, Any]:
    if root:
        ctx = _root_context(root)
        return _list_local(ctx["id"], Path(ctx["path"]), path, query=query, favorites_only=favorites_only)
    backend = _backend()
    if backend["name"] == "local-vault":
        return _list_local("vault", backend["root"], path, query=query, favorites_only=favorites_only)
    if backend["name"] == "nextcloud-webdav":
        return _list_dav(backend["profile"], path, query=query, favorites_only=favorites_only)
    ctx = _root_context(root)
    return _list_local(ctx["id"], Path(ctx["path"]), path, query=query, favorites_only=favorites_only)


@router.get("/content")
async def content(path: str, root: str = "") -> dict[str, Any]:
    if root:
        ctx = _root_context(root)
        target, relative = _resolve_local(Path(ctx["path"]), path)
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Drive file does not exist")
        if target.stat().st_size > _MAX_TEXT_BYTES or not _is_text_item(target):
            raise HTTPException(status_code=415, detail="File preview is not available")
        return {
            "root": ctx["id"],
            "path": _display_path(relative),
            "content": target.read_text(encoding="utf-8", errors="replace"),
            "modified": _iso_from_timestamp(target.stat().st_mtime),
        }
    backend = _backend()
    if backend["name"] == "local-vault":
        target, relative = _resolve_local(backend["root"], path)
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Drive file does not exist")
        if target.stat().st_size > _MAX_TEXT_BYTES or not _is_text_item(target):
            raise HTTPException(status_code=415, detail="File preview is not available")
        return {
            "root": "vault",
            "path": _display_path(relative),
            "content": target.read_text(encoding="utf-8", errors="replace"),
            "modified": _iso_from_timestamp(target.stat().st_mtime),
        }
    if backend["name"] == "nextcloud-webdav":
        _status, body, headers = _dav_request(backend["profile"], "GET", path)
        content_type = headers.get("Content-Type", "")
        if len(body) > _MAX_TEXT_BYTES or not (
            content_type.startswith("text/") or Path(path).suffix.lower() in _TEXT_EXTENSIONS
        ):
            raise HTTPException(status_code=415, detail="File preview is not available")
        return {
            "path": _display_path(_clean_relative_path(path)),
            "content": body.decode("utf-8", "replace"),
            "modified": headers.get("Last-Modified", ""),
        }
    raise HTTPException(status_code=404, detail="Drive is not available")


@router.get("/download")
async def download(path: str, root: str = "") -> Any:
    if root:
        ctx = _root_context(root)
        target, _relative = _resolve_local(Path(ctx["path"]), path)
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Drive file does not exist")
        return FileResponse(str(target), filename=target.name, media_type=mimetypes.guess_type(str(target))[0])
    backend = _backend()
    if backend["name"] == "local-vault":
        target, _relative = _resolve_local(backend["root"], path)
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Drive file does not exist")
        return FileResponse(str(target), filename=target.name, media_type=mimetypes.guess_type(str(target))[0])
    if backend["name"] == "nextcloud-webdav":
        _status, body, headers = _dav_request(backend["profile"], "GET", path)
        return Response(content=body, media_type=headers.get("Content-Type") or "application/octet-stream")
    raise HTTPException(status_code=404, detail="Drive is not available")


@router.get("/preview")
async def preview(path: str, root: str = "") -> Any:
    if root:
        ctx = _root_context(root)
        target, _relative = _resolve_local(Path(ctx["path"]), path)
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Drive file does not exist")
        return FileResponse(
            str(target),
            media_type=mimetypes.guess_type(str(target))[0] or "application/octet-stream",
            headers={"Content-Disposition": _inline_content_disposition(target.name)},
        )
    backend = _backend()
    if backend["name"] == "local-vault":
        target, _relative = _resolve_local(backend["root"], path)
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Drive file does not exist")
        return FileResponse(
            str(target),
            media_type=mimetypes.guess_type(str(target))[0] or "application/octet-stream",
            headers={"Content-Disposition": _inline_content_disposition(target.name)},
        )
    if backend["name"] == "nextcloud-webdav":
        _status, body, headers = _dav_request(backend["profile"], "GET", path)
        filename = Path(path).name or "preview"
        return Response(
            content=body,
            media_type=headers.get("Content-Type") or mimetypes.guess_type(path)[0] or "application/octet-stream",
            headers={"Content-Disposition": _inline_content_disposition(filename)},
        )
    raise HTTPException(status_code=404, detail="Drive is not available")


@router.post("/mkdir")
async def mkdir(request: Request) -> dict[str, Any]:
    payload = await request.json()
    root_id = payload.get("root") or ""
    path = payload.get("path") or "/"
    name = payload.get("name")
    if name:
        path = _join_display(str(path), _sanitized_name(name))
    if root_id:
        ctx = _root_context(root_id)
        target, relative = _resolve_local(Path(ctx["path"]), path)
        target.mkdir(parents=True, exist_ok=True)
        return {"ok": True, "root": ctx["id"], "path": _display_path(relative)}
    backend = _backend()
    if backend["name"] == "local-vault":
        target, relative = _resolve_local(backend["root"], path)
        target.mkdir(parents=True, exist_ok=True)
        return {"ok": True, "root": "vault", "path": _display_path(relative)}
    if backend["name"] == "nextcloud-webdav":
        _dav_request(backend["profile"], "MKCOL", path)
        return {"ok": True, "path": _display_path(_clean_relative_path(path))}
    raise HTTPException(status_code=404, detail="Drive is not available")


@router.post("/move")
async def move(request: Request) -> dict[str, Any]:
    payload = await request.json()
    root_id = payload.get("root") or ""
    destination_root = payload.get("destination_root") or root_id
    source_path = payload.get("path") or payload.get("source_path")
    destination_path = payload.get("destination_path") or payload.get("destination")
    if not source_path or not destination_path:
        raise HTTPException(status_code=400, detail="Source and destination are required")
    if root_id:
        if destination_root != root_id:
            raise HTTPException(status_code=400, detail="Cross-root move is not supported")
        ctx = _root_context(root_id)
        return _move_local(ctx["id"], Path(ctx["path"]), source_path, destination_path)
    backend = _backend()
    if backend["name"] == "local-vault":
        return _move_local("vault", backend["root"], source_path, destination_path)
    if backend["name"] == "nextcloud-webdav":
        return _move_webdav(backend["profile"], source_path, destination_path)
    raise HTTPException(status_code=404, detail="Drive is not available")


@router.post("/rename")
async def rename(request: Request) -> dict[str, Any]:
    payload = await request.json()
    root_id = payload.get("root") or ""
    source_path = payload.get("path") or payload.get("source_path")
    if not source_path:
        raise HTTPException(status_code=400, detail="Source path is required")
    destination_path = _rename_destination(source_path, payload.get("name"))
    if root_id:
        ctx = _root_context(root_id)
        return _move_local(ctx["id"], Path(ctx["path"]), source_path, destination_path)
    backend = _backend()
    if backend["name"] == "local-vault":
        return _move_local("vault", backend["root"], source_path, destination_path)
    if backend["name"] == "nextcloud-webdav":
        return _move_webdav(backend["profile"], source_path, destination_path)
    raise HTTPException(status_code=404, detail="Drive is not available")


@router.post("/favorite")
async def favorite(request: Request) -> dict[str, Any]:
    payload = await request.json()
    root_id = str(payload.get("root") or "").strip().lower()
    if root_id:
        _root_context(root_id)
    display = _display_path(_clean_relative_path(payload.get("path")))
    is_favorite = bool(payload.get("favorite"))
    meta = _load_meta()
    favorites = _root_meta(meta, "favorites", root_id or "vault")
    if is_favorite:
        favorites[display] = True
    else:
        favorites.pop(display, None)
    _save_meta(meta)
    backend = _backend()
    if backend["name"] == "nextcloud-webdav":
        value = "1" if is_favorite else "0"
        body = f"""<?xml version="1.0"?>
<d:propertyupdate xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns">
  <d:set><d:prop><oc:favorite>{value}</oc:favorite></d:prop></d:set>
</d:propertyupdate>
"""
        _dav_request(backend["profile"], "PROPPATCH", display, body=body, headers={"Content-Type": "application/xml"})
    return {"ok": True, "root": root_id or "vault", "path": display, "favorite": is_favorite}


@router.post("/delete")
async def delete(request: Request) -> dict[str, Any]:
    payload = await request.json()
    root_id = payload.get("root") or ""
    if root_id:
        ctx = _root_context(root_id)
        return _delete_local(ctx["id"], Path(ctx["path"]), payload.get("path"))
    backend = _backend()
    if backend["name"] == "local-vault":
        return _delete_local("vault", backend["root"], payload.get("path"))
    if backend["name"] == "nextcloud-webdav":
        path = _display_path(_clean_relative_path(payload.get("path")))
        _dav_request(backend["profile"], "DELETE", path)
        return {"ok": True, "path": path}
    raise HTTPException(status_code=404, detail="Drive is not available")


def _delete_local(root_id: str, root: Path, raw_path: Any) -> dict[str, Any]:
    target, relative = _resolve_local(root, raw_path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Drive path does not exist")
    if target == root:
        raise HTTPException(status_code=400, detail="Cannot delete the Drive root")
    trash_target = _next_trash_path(root, relative)
    shutil.move(str(target), str(trash_target))
    display = _display_path(relative)
    trash_relative = trash_target.relative_to(root).as_posix()
    trash_display = _display_path(trash_relative)
    meta = _load_meta()
    favorites = _root_meta(meta, "favorites", root_id)
    for favorite_path in list(favorites):
        if favorite_path == display or favorite_path.startswith(display + "/"):
            favorites.pop(favorite_path, None)
    _root_meta(meta, "trash", root_id)[trash_display] = {
        "root": root_id,
        "original_path": display,
        "trash_path": trash_display,
        "deleted_at": _iso_from_timestamp(time.time()),
    }
    _save_meta(meta)
    return {"ok": True, "root": root_id, "path": display, "trash_path": trash_display}


@router.get("/trash")
async def trash(root: str = "") -> dict[str, Any]:
    if root:
        ctx = _root_context(root)
        root_id = ctx["id"]
        root_path = Path(ctx["path"])
    else:
        backend = _backend()
        if backend["name"] != "local-vault":
            return {"items": []}
        root_id = "vault"
        root_path = backend["root"]
    meta = _load_meta()
    records = []
    for trash_path, record in sorted(_root_meta(meta, "trash", root_id).items()):
        target, _relative = _resolve_local(root_path, trash_path)
        if target.exists():
            records.append(record)
    return {"root": root_id, "items": records}


@router.post("/restore")
async def restore(request: Request) -> dict[str, Any]:
    payload = await request.json()
    root_id = payload.get("root") or ""
    if root_id:
        ctx = _root_context(root_id)
        root_path = Path(ctx["path"])
        resolved_root_id = ctx["id"]
    else:
        backend = _backend()
        if backend["name"] != "local-vault":
            raise HTTPException(status_code=400, detail="Restore is only available for local Drive roots")
        root_path = backend["root"]
        resolved_root_id = "vault"
    return _restore_local(resolved_root_id, root_path, payload.get("path") or payload.get("trash_path"))


def _restore_local(root_id: str, root_path: Path, raw_path: Any) -> dict[str, Any]:
    requested = _display_path(_clean_relative_path(raw_path))
    meta = _load_meta()
    trash_records = _root_meta(meta, "trash", root_id)
    record = trash_records.get(requested)
    if record is None:
        for candidate in trash_records.values():
            if candidate.get("original_path") == requested:
                record = candidate
                requested = str(candidate.get("trash_path") or "")
                break
    if not record:
        raise HTTPException(status_code=404, detail="Trash record does not exist")
    trash_target, _trash_relative = _resolve_local(root_path, requested)
    destination, destination_relative = _resolve_local(root_path, record.get("original_path"))
    if destination.exists():
        raise HTTPException(status_code=409, detail="Original path already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(trash_target), str(destination))
    trash_records.pop(requested, None)
    _save_meta(meta)
    return {"ok": True, "root": root_id, "path": _display_path(destination_relative)}


@router.post("/upload")
async def upload(
    path: str = Form("/"),
    root: str = Form(""),
    conflict: str = Form("reject"),
    files: list[UploadFile] = File(...),
) -> dict[str, Any]:
    ctx: dict[str, Any] | None = _root_context(root) if root else None
    backend = _backend()
    uploaded: list[dict[str, Any]] = []
    target_dir_path = _clean_relative_path(path)
    policy = str(conflict or "reject").strip().lower()
    if policy not in {"reject", "keep-both"}:
        raise HTTPException(status_code=400, detail="Unsupported conflict policy")
    for upload_file in files:
        name = _sanitized_name(upload_file.filename)
        display = _join_display(target_dir_path, name)
        content_bytes = await upload_file.read()
        if ctx is not None:
            target, relative = _resolve_local(Path(ctx["path"]), display)
            target = _resolve_conflict_destination(target, conflict=policy)
            relative = target.relative_to(Path(ctx["path"])).as_posix()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content_bytes)
            uploaded.append({"root": ctx["id"], "path": _display_path(relative), "size": len(content_bytes)})
        elif backend["name"] == "local-vault":
            target, relative = _resolve_local(backend["root"], display)
            target = _resolve_conflict_destination(target, conflict=policy)
            relative = target.relative_to(backend["root"]).as_posix()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content_bytes)
            uploaded.append({"root": "vault", "path": _display_path(relative), "size": len(content_bytes)})
        elif backend["name"] == "nextcloud-webdav":
            if policy == "keep-both":
                raise HTTPException(status_code=400, detail="Keep-both upload conflict policy is only available for local Drive roots")
            headers = {"If-None-Match": "*"} if policy == "reject" else {}
            _dav_request(backend["profile"], "PUT", display, body=content_bytes, headers=headers)
            uploaded.append({"path": display, "size": len(content_bytes)})
        else:
            raise HTTPException(status_code=404, detail="Drive is not available")
    return {"ok": True, "uploaded": uploaded}


@router.post("/new-file")
async def new_file(request: Request) -> dict[str, Any]:
    payload = await request.json()
    ctx = _root_context(payload.get("root"))
    parent = payload.get("path") or "/"
    name = _sanitized_name(payload.get("name"))
    target, relative = _resolve_local(Path(ctx["path"]), _join_display(str(parent), name))
    if target.exists():
        raise HTTPException(status_code=409, detail="File already exists")
    if target.suffix.lower() not in _TEXT_EXTENSIONS:
        raise HTTPException(status_code=400, detail="New file is limited to text-like file extensions")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(payload.get("content") or ""), encoding="utf-8")
    return {"ok": True, "root": ctx["id"], "path": _display_path(relative)}


@router.post("/copy")
async def copy(request: Request) -> dict[str, Any]:
    payload = await request.json()
    root_id = payload.get("root")
    destination_root = payload.get("destination_root") or root_id
    if destination_root != root_id:
        raise HTTPException(status_code=400, detail="Cross-root copy is not supported")
    ctx = _root_context(root_id)
    source_path = payload.get("path") or payload.get("source_path")
    destination_path = payload.get("destination_path") or payload.get("destination")
    if not source_path or not destination_path:
        raise HTTPException(status_code=400, detail="Source and destination are required")
    return _copy_local(
        ctx["id"],
        Path(ctx["path"]),
        source_path,
        destination_path,
        conflict=str(payload.get("conflict") or "reject"),
    )


@router.post("/duplicate")
async def duplicate(request: Request) -> dict[str, Any]:
    payload = await request.json()
    ctx = _root_context(payload.get("root"))
    source_path = payload.get("path") or payload.get("source_path")
    if not source_path:
        raise HTTPException(status_code=400, detail="Source path is required")
    return _copy_local(
        ctx["id"],
        Path(ctx["path"]),
        source_path,
        _duplicate_destination(source_path),
        conflict="keep-both",
    )


@router.post("/batch")
async def batch(request: Request) -> dict[str, Any]:
    payload = await request.json()
    action = str(payload.get("action") or "").strip().lower()
    root_id = payload.get("root")
    paths = payload.get("paths") or []
    if not isinstance(paths, list) or not paths:
        raise HTTPException(status_code=400, detail="Batch paths are required")
    ctx = _root_context(root_id)
    results: list[dict[str, Any]] = []
    for raw_path in paths:
        try:
            if action == "trash":
                result = _delete_local(ctx["id"], Path(ctx["path"]), raw_path)
            elif action == "favorite":
                is_favorite = bool(payload.get("favorite", True))
                meta = _load_meta()
                favorites = _root_meta(meta, "favorites", ctx["id"])
                display = _display_path(_clean_relative_path(raw_path))
                if is_favorite:
                    favorites[display] = True
                else:
                    favorites.pop(display, None)
                _save_meta(meta)
                result = {"ok": True, "root": ctx["id"], "path": display, "favorite": is_favorite}
            elif action == "copy":
                destination_root = payload.get("destination_root") or ctx["id"]
                if destination_root != ctx["id"]:
                    raise HTTPException(status_code=400, detail="Cross-root copy is not supported")
                destination_folder = payload.get("destination_folder") or payload.get("destination_path")
                if not destination_folder:
                    raise HTTPException(status_code=400, detail="Batch copy destination folder is required")
                destination = _join_display(str(destination_folder), posixpath.basename(_clean_relative_path(raw_path)))
                result = _copy_local(
                    ctx["id"],
                    Path(ctx["path"]),
                    raw_path,
                    destination,
                    conflict=str(payload.get("conflict") or "reject"),
                )
            elif action == "move":
                destination_root = payload.get("destination_root") or ctx["id"]
                if destination_root != ctx["id"]:
                    raise HTTPException(status_code=400, detail="Cross-root move is not supported")
                destination_folder = payload.get("destination_folder") or payload.get("destination_path")
                if not destination_folder:
                    raise HTTPException(status_code=400, detail="Batch move destination folder is required")
                destination = _join_display(str(destination_folder), posixpath.basename(_clean_relative_path(raw_path)))
                result = _move_local(ctx["id"], Path(ctx["path"]), raw_path, destination)
            elif action == "restore":
                result = _restore_local(ctx["id"], Path(ctx["path"]), raw_path)
            else:
                raise HTTPException(status_code=400, detail="Unsupported batch action")
            results.append(result)
        except HTTPException as exc:
            results.append({
                "ok": False,
                "root": ctx["id"],
                "path": _error_display_path(raw_path),
                "status": exc.status_code,
                "detail": exc.detail,
            })
    return {"ok": all(bool(result.get("ok")) for result in results), "root": ctx["id"], "action": action, "results": results}
