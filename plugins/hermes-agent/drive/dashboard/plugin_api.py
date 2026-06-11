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
import urllib.request
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
    ".cfg",
    ".conf",
    ".cpp",
    ".c",
    ".diff",
    ".dockerfile",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".jsx",
    ".json",
    ".log",
    ".lock",
    ".md",
    ".mdx",
    ".patch",
    ".php",
    ".py",
    ".rb",
    ".rst",
    ".rs",
    ".sh",
    ".sql",
    ".text",
    ".toml",
    ".tsv",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
_TRASH_DIR_NAME = ".drive-trash"
_LINKED_MANIFEST_NAME = ".arclink-linked-resources.json"
_SKIP_DIR_NAMES = {".git", ".hg", ".svn", "__pycache__", "node_modules", _TRASH_DIR_NAME}
_SENSITIVE_DIR_NAMES = {".ssh"}
_SENSITIVE_FILE_NAMES = {
    _LINKED_MANIFEST_NAME,
    ".env",
    "arclink-bootstrap-token",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
}
_MAX_TEXT_BYTES = 1_000_000
_MAX_JSON_BODY_BYTES = _MAX_TEXT_BYTES + 64_000
_DEFAULT_MAX_UPLOAD_BYTES = 256 * 1024 * 1024
_MAX_UPLOAD_BYTES_CEILING = 2 * 1024 * 1024 * 1024
_UPLOAD_READ_CHUNK_BYTES = 1024 * 1024
_DEFAULT_MAX_UPLOAD_FILES = 200
_DEFAULT_MAX_UPLOAD_DIRECTORIES = 1000
_DEFAULT_MAX_UPLOAD_METADATA_BYTES = 256 * 1024
_DEFAULT_MAX_UPLOAD_TOTAL_BYTES = 1024 * 1024 * 1024
_MAX_UPLOAD_TOTAL_BYTES_CEILING = 8 * 1024 * 1024 * 1024
_SEARCH_LIMIT = 300
_MAX_CHILD_COUNT = 999
_SHARE_REQUEST_BROKER_TOKEN_HEADER = "X-ArcLink-Share-Request-Broker-Token"
_ROOT_METADATA = {
    "workspace": {
        "label": "Workspace",
        "icon": "workspace",
        "tooltip": "This Hermes Agent's own writable workspace: Projects, Repos, Research, and local knowledge.",
        "description": "This Hermes Agent's own writable workspace: Projects, Repos, Research, and local knowledge.",
        "order": 10,
    },
    "fleet": {
        "label": "Fleet",
        "icon": "fleet",
        "tooltip": "Shared read/write space for this Captain's fleet of ArcPods, synced across machines.",
        "description": "Shared read/write space for this Captain's fleet of ArcPods, synced across machines.",
        "order": 20,
    },
    "linked": {
        "label": "Linked",
        "icon": "linked",
        "tooltip": "Folders shared with you from other Captains or ArcPods; accepted read/write shares can be edited here.",
        "description": "Folders shared with you from other Captains or ArcPods; accepted read/write shares can be edited here.",
        "order": 30,
    },
}


def _root_label(root_id: str) -> str:
    """Captain-facing label for a Drive root id, for error copy and badges."""
    normalized = str(root_id or "").strip().lower()
    metadata = _ROOT_METADATA.get(normalized)
    if metadata:
        return str(metadata.get("label") or normalized.title() or "Drive")
    if normalized == "vault":
        return "Workspace"
    return normalized.title() or "Drive"


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes")).expanduser()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _linked_manifest(root: Path) -> dict[str, Any]:
    payload = _load_json(root / _LINKED_MANIFEST_NAME)
    entries = payload.get("entries")
    if not isinstance(entries, dict):
        entries = {}
    return entries


def _linked_manifest_entry(root: Path, path: Path) -> dict[str, Any] | None:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return None
    parts = relative.parts
    if not parts:
        return None
    entry = _linked_manifest(root).get(parts[0])
    return entry if isinstance(entry, dict) else None


def _manifest_bool(value: Any, *, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"0", "false", "no", "off"}:
        return False
    if text in {"1", "true", "yes", "on"}:
        return True
    return default


def _linked_entry_writable(entry: dict[str, Any]) -> bool:
    access_mode = str(entry.get("access_mode") or "").strip().lower().replace("-", "_")
    return access_mode == "read_write" and not _manifest_bool(entry.get("read_only"), default=True)


def _linked_root_has_writable_share(root: Path | None) -> bool:
    """True when at least one accepted read/write shared folder exists under Linked."""
    if root is None:
        return False
    try:
        entries = _linked_manifest(root.resolve(strict=False))
    except OSError:
        return False
    for entry in entries.values():
        if not isinstance(entry, dict):
            continue
        if str(entry.get("resource_kind") or "").strip().lower() != "directory":
            continue
        if _linked_entry_writable(entry):
            return True
    return False


def _linked_target_allowed(root: Path, path: Path, resolved: Path) -> bool:
    entry = _linked_manifest_entry(root, path)
    if not entry:
        return False
    source = Path(str(entry.get("source_path") or "")).expanduser().resolve(strict=False)
    if not str(source):
        return False
    return resolved == source or source in resolved.parents


def _linked_writable_source(root: Path, raw_path: Any, *, allow_share_root: bool = False) -> tuple[Path, str, Path, str]:
    root_resolved = root.resolve(strict=False)
    relative = _clean_relative_path(raw_path)
    if not relative:
        raise HTTPException(status_code=403, detail="Choose a shared folder before writing to Linked")
    slug, _separator, remainder = relative.partition("/")
    entry = _linked_manifest(root_resolved).get(slug)
    if not isinstance(entry, dict):
        raise HTTPException(status_code=403, detail="Linked writes are limited to accepted shared folders")
    if not _linked_entry_writable(entry):
        raise HTTPException(status_code=403, detail="Linked resource is read-only")
    if str(entry.get("resource_kind") or "").strip().lower() != "directory":
        raise HTTPException(status_code=403, detail="Only shared folders are writable from Linked")
    source = Path(str(entry.get("source_path") or "")).expanduser().resolve(strict=False)
    if not source.is_dir():
        raise HTTPException(status_code=404, detail="Shared folder source is not available")
    if not remainder and not allow_share_root:
        raise HTTPException(status_code=403, detail="The shared folder itself is system-managed")
    target, source_relative = _resolve_local(source, remainder, root_id="")
    return target, source_relative, source, slug


def _resolve_writable_local(
    root_id: str,
    root: Path,
    raw_path: Any,
    *,
    allow_share_root: bool = False,
) -> tuple[Path, str, Path, str]:
    if str(root_id or "").strip().lower() != "linked":
        target, relative = _resolve_local(root, raw_path, root_id=root_id)
        return target, relative, root.resolve(strict=False), ""
    target, relative, source, slug = _linked_writable_source(root, raw_path, allow_share_root=allow_share_root)
    return target, relative, source, slug


def _linked_display_path(slug: str, relative: str) -> str:
    return _display_path(posixpath.join(slug, relative) if relative else slug)


def _clean_url(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith(("https://", "http://")):
        return text
    return ""


def _clean_text(value: Any, limit: int = 160) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def _form_value(value: Any, fallback: Any = "") -> Any:
    default = getattr(value, "default", None)
    if default is not None and value.__class__.__module__.startswith("fastapi."):
        return default
    return fallback if value is None else value


def _env_first(*keys: str) -> str:
    for key in keys:
        value = str(os.environ.get(key) or "").strip()
        if value:
            return value
    return ""


async def _request_body_limited(request: Request, *, max_bytes: int, label: str) -> bytes | None:
    headers = getattr(request, "headers", {}) or {}
    try:
        content_length = int(str(headers.get("content-length") or headers.get("Content-Length") or "0"))
    except (TypeError, ValueError):
        content_length = 0
    if content_length > max_bytes:
        raise HTTPException(status_code=413, detail=f"{label} request body is too large")
    stream_reader = getattr(request, "stream", None)
    if callable(stream_reader):
        chunks: list[bytes] = []
        total = 0
        async for chunk in stream_reader():
            if isinstance(chunk, str):
                chunk = chunk.encode("utf-8")
            total += len(chunk)
            if total > max_bytes:
                raise HTTPException(status_code=413, detail=f"{label} request body is too large")
            chunks.append(bytes(chunk))
        return b"".join(chunks)
    body_reader = getattr(request, "body", None)
    if callable(body_reader):
        raw = await body_reader()
        if len(raw) > max_bytes:
            raise HTTPException(status_code=413, detail=f"{label} request body is too large")
        return bytes(raw)
    return None


async def _request_json(request: Request, *, max_bytes: int = _MAX_JSON_BODY_BYTES) -> dict[str, Any]:
    raw = await _request_body_limited(request, max_bytes=max_bytes, label="Drive")
    if raw is not None:
        if not raw:
            return {}
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise HTTPException(status_code=400, detail="Drive request body must be JSON") from None
    else:
        parsed = await request.json()
        if parsed is None:
            return {}
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="Drive request body must be a JSON object")
    return parsed


def _bounded_env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = str(os.environ.get(name) or "").strip()
    try:
        value = int(raw) if raw else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _max_upload_bytes() -> int:
    return _bounded_env_int(
        "DRIVE_MAX_UPLOAD_BYTES",
        _DEFAULT_MAX_UPLOAD_BYTES,
        minimum=1,
        maximum=_MAX_UPLOAD_BYTES_CEILING,
    )


def _max_upload_files() -> int:
    return _bounded_env_int("DRIVE_MAX_UPLOAD_FILES", _DEFAULT_MAX_UPLOAD_FILES, minimum=1, maximum=5000)


def _max_upload_directories() -> int:
    return _bounded_env_int("DRIVE_MAX_UPLOAD_DIRECTORIES", _DEFAULT_MAX_UPLOAD_DIRECTORIES, minimum=0, maximum=20000)


def _max_upload_metadata_bytes() -> int:
    return _bounded_env_int("DRIVE_MAX_UPLOAD_METADATA_BYTES", _DEFAULT_MAX_UPLOAD_METADATA_BYTES, minimum=0, maximum=4 * 1024 * 1024)


def _max_upload_total_bytes() -> int:
    return _bounded_env_int(
        "DRIVE_MAX_UPLOAD_TOTAL_BYTES",
        _DEFAULT_MAX_UPLOAD_TOTAL_BYTES,
        minimum=1,
        maximum=_MAX_UPLOAD_TOTAL_BYTES_CEILING,
    )


async def _read_upload_bytes(upload_file: UploadFile) -> bytes:
    """Read one browser-uploaded file with a hard per-file memory ceiling."""
    max_bytes = _max_upload_bytes()
    chunks: list[bytes] = []
    total = 0
    while True:
        unbounded_read = False
        try:
            chunk = await upload_file.read(_UPLOAD_READ_CHUNK_BYTES)  # type: ignore[call-arg]
        except TypeError:
            chunk = await upload_file.read()
            unbounded_read = True
        if not chunk:
            break
        if isinstance(chunk, str):
            chunk = chunk.encode("utf-8")
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail="Upload file is too large")
        chunks.append(bytes(chunk))
        if unbounded_read or len(chunk) < _UPLOAD_READ_CHUNK_BYTES:
            break
    return b"".join(chunks)


async def _write_upload_file_atomic(upload_file: UploadFile, target: Path) -> int:
    """Write one browser upload to a local target without buffering the file in RAM."""
    max_bytes = _max_upload_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), prefix=f".{target.name}.upload-", suffix=".tmp")
    tmp_path = Path(tmp_name)
    total = 0
    try:
        with os.fdopen(fd, "wb") as handle:
            while True:
                unbounded_read = False
                try:
                    chunk = await upload_file.read(_UPLOAD_READ_CHUNK_BYTES)  # type: ignore[call-arg]
                except TypeError:
                    chunk = await upload_file.read()
                    unbounded_read = True
                if not chunk:
                    break
                if isinstance(chunk, str):
                    chunk = chunk.encode("utf-8")
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(status_code=413, detail="Upload file is too large")
                handle.write(bytes(chunk))
                if unbounded_read or len(chunk) < _UPLOAD_READ_CHUNK_BYTES:
                    break
            handle.flush()
        os.replace(tmp_path, target)
        return total
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass
        raise


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
    access = _load_json(state_dir / "arclink-web-access.json")
    if not access:
        access = _load_json(state_dir / "web-access.json")
    return (
        access,
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
        os.environ.get("ARCLINK_WORKSPACE_ROOT"),
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
    candidates: list[Path] = []
    for value in (
        os.environ.get("ARCLINK_WORKSPACE_ROOT"),
        os.environ.get("DRIVE_WORKSPACE_ROOT"),
        os.environ.get("ARCLINK_DRIVE_ROOT"),
        os.environ.get("DRIVE_ROOT"),
        os.environ.get("KNOWLEDGE_VAULT_ROOT"),
        os.environ.get("AGENT_VAULT_DIR"),
        os.environ.get("VAULT_DIR"),
        os.environ.get("ARCLINK_CODE_WORKSPACE_ROOT"),
        os.environ.get("CODE_WORKSPACE_ROOT"),
    ):
        if value:
            candidates.append(Path(value).expanduser())
    candidates.extend(
        [
            _hermes_home() / "workspace",
        ]
    )
    return candidates


def _candidate_linked_roots() -> list[Path]:
    candidates: list[Path] = []
    for value in (
        os.environ.get("DRIVE_LINKED_ROOT"),
        os.environ.get("ARCLINK_LINKED_RESOURCES_ROOT"),
    ):
        if value:
            candidates.append(Path(value).expanduser())
    candidates.append(_hermes_home() / "linked")
    return candidates


def _candidate_fleet_roots() -> list[Path]:
    candidates: list[Path] = []
    for value in (
        os.environ.get("DRIVE_FLEET_SHARED_ROOT"),
        os.environ.get("ARCLINK_FLEET_SHARED_ROOT"),
    ):
        if value:
            candidates.append(Path(value).expanduser())
    candidates.append(_hermes_home() / "fleet-shared")
    return candidates


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _is_sensitive_path(path: Path) -> bool:
    lowered_parts = {part.lower() for part in path.parts}
    if lowered_parts & _SENSITIVE_DIR_NAMES:
        return True
    name = path.name.lower()
    if name in _SENSITIVE_FILE_NAMES:
        return True
    if name == ".env" or name.startswith(".env."):
        return True
    if "bootstrap-token" in name:
        return True
    if name == ".arclink-operator.env":
        return True
    if "arclink-priv" in lowered_parts and (name.endswith(".env") or name in {"docker.env", "arclink.env", "install.answers.env"}):
        return True
    resolved = path.expanduser().resolve(strict=False)
    hermes = _hermes_home().expanduser().resolve(strict=False)
    for private_root in (hermes / "secrets", hermes / "state"):
        if resolved == private_root or _is_relative_to(resolved, private_root):
            return True
    return False


def _assert_not_sensitive(path: Path) -> None:
    if _is_sensitive_path(path):
        raise HTTPException(status_code=403, detail="Secret or private runtime paths are not available in Drive")


def _share_request_broker_url() -> str:
    return _clean_url(_env_first("DRIVE_SHARE_REQUEST_BROKER_URL", "ARCLINK_SHARE_REQUEST_BROKER_URL"))


def _share_request_broker_token_file() -> Path | None:
    value = _env_first("DRIVE_SHARE_REQUEST_BROKER_TOKEN_FILE", "ARCLINK_SHARE_REQUEST_BROKER_TOKEN_FILE")
    return Path(value).expanduser() if value else None


def _clean_broker_token(value: str) -> str:
    token = str(value or "").strip()
    if not token or len(token) > 4096:
        return ""
    if any(ord(char) < 33 or ord(char) > 126 for char in token):
        return ""
    return token


def _share_request_broker_token() -> str:
    token_file = _share_request_broker_token_file()
    if token_file is None:
        return ""
    try:
        return _clean_broker_token(token_file.read_text(encoding="utf-8"))
    except OSError:
        return ""


def _owner_deployment_id() -> str:
    value = _env_first("DRIVE_OWNER_DEPLOYMENT_ID", "ARCLINK_OWNER_DEPLOYMENT_ID", "ARCLINK_DEPLOYMENT_ID")
    if value:
        return _clean_text(value, 120)
    access, _managed = _access_state()
    return _clean_text(access.get("owner_deployment_id") or access.get("deployment_id"), 120)


def _share_request_auth_headers() -> dict[str, str]:
    token = _share_request_broker_token()
    if not token:
        raise HTTPException(status_code=503, detail="ArcLink share-request broker authentication is not configured")
    return {_SHARE_REQUEST_BROKER_TOKEN_HEADER: token}


def _share_request_state() -> dict[str, Any]:
    broker_url = _share_request_broker_url()
    auth_configured = bool(_share_request_broker_token())
    owner_deployment_configured = bool(_owner_deployment_id())
    enabled = bool(broker_url and auth_configured and owner_deployment_configured)
    reason = ""
    if not broker_url:
        reason = "ArcLink share-request broker is not configured"
    elif not auth_configured:
        reason = "ArcLink share-request broker authentication is not configured"
    elif not owner_deployment_configured:
        reason = "ArcLink share-request broker deployment identity is not configured"
    return {
        "enabled": enabled,
        "available": enabled,
        "broker": "arclink-share-grants",
        "status": "enabled" if enabled else "disabled",
        "reason": reason,
        "direct_links": False,
    }


def _first_existing_dir(candidates: list[Path]) -> Path | None:
    for candidate in candidates:
        try:
            if candidate.is_dir() and not _is_sensitive_path(candidate):
                return candidate.resolve(strict=False)
        except OSError:
            continue
    return None


def _same_root(left: Path | None, right: Path | None) -> bool:
    if left is None or right is None:
        return False
    try:
        return left.resolve(strict=False) == right.resolve(strict=False)
    except OSError:
        return False


def _local_root() -> Path | None:
    return _first_existing_dir(_candidate_vault_roots())


def _root_capabilities(
    *,
    available: bool,
    backend: str,
    webdav_available: bool = False,
    read_only: bool = False,
    share_request_enabled: bool = False,
    linked: bool = False,
) -> dict[str, bool]:
    local = bool(available and backend == "local")
    if linked:
        # Linked is system-managed: writes are only possible inside accepted
        # read/write shared folders, so write-style capabilities follow the
        # manifest truth instead of advertising full local capabilities.
        writable = bool(local and not read_only)
        return {
            "batch": local,
            "copy": local,
            "delete": writable,
            "download": local,
            "drag_drop_upload": writable,
            "duplicate": local,
            "favorites": False,
            "folder_upload": writable,
            "folders": writable,
            "move": writable,
            "new_file": writable,
            "preview": local,
            "rename": writable,
            "restore": writable,
            "search": local,
            "share_request": False,
            "sharing": False,
            "trash": writable,
            "upload": writable,
            "nextcloud_webdav": False,
        }
    if read_only:
        return {
            "batch": False,
            "copy": local,
            "delete": False,
            "download": local,
            "drag_drop_upload": False,
            "duplicate": local,
            "favorites": False,
            "folder_upload": False,
            "folders": local,
            "move": False,
            "new_file": False,
            "preview": local,
            "rename": False,
            "restore": False,
            "search": local,
            "share_request": False,
            "sharing": False,
            "trash": False,
            "upload": False,
            "nextcloud_webdav": False,
        }
    return {
        "batch": local,
        "copy": local,
        "delete": local,
        "download": local or backend == "nextcloud-webdav",
        "drag_drop_upload": local or backend == "nextcloud-webdav",
        "duplicate": local,
        "favorites": False,
        "folder_upload": local or backend == "nextcloud-webdav",
        "folders": local or backend == "nextcloud-webdav",
        "move": local or backend == "nextcloud-webdav",
        "new_file": local,
        "preview": local or backend == "nextcloud-webdav",
        "rename": local or backend == "nextcloud-webdav",
        "restore": local,
        "search": local,
        "share_request": bool(local and share_request_enabled),
        "sharing": False,
        "trash": local,
        "upload": local or backend == "nextcloud-webdav",
        "nextcloud_webdav": bool(webdav_available),
    }


def _root_descriptor(
    root_id: str,
    label: str,
    root: Path | None,
    *,
    webdav_available: bool = False,
    read_only: bool = False,
    share_request_enabled: bool = False,
    resource_root: str = "",
    linked: bool = False,
) -> dict[str, Any]:
    available = root is not None
    child_count, child_count_truncated = _visible_child_count(root_id, root, root) if root is not None else (0, False)
    metadata = _ROOT_METADATA.get(root_id, {})
    return {
        "id": root_id,
        "label": str(metadata.get("label") or label),
        "icon": str(metadata.get("icon") or root_id),
        "tooltip": str(metadata.get("tooltip") or ""),
        "description": str(metadata.get("description") or ""),
        "order": int(metadata.get("order") or 100),
        "available": available,
        "backend": "local" if available else "unavailable",
        "path": str(root) if root else "",
        "display_path": "/",
        "resource_root": resource_root or root_id,
        "child_count": child_count,
        "child_count_truncated": child_count_truncated,
        "read_only": read_only,
        "capabilities": _root_capabilities(
            available=available,
            backend="local" if available else "unavailable",
            webdav_available=webdav_available,
            read_only=read_only,
            share_request_enabled=share_request_enabled,
            linked=linked,
        ),
    }


def _local_root_descriptors(webdav_available: bool = False, share_request_enabled: bool = False) -> list[dict[str, Any]]:
    vault = _first_existing_dir(_candidate_vault_roots())
    workspace = _first_existing_dir(_candidate_workspace_roots()) or vault
    workspace_resource_root = "vault" if _same_root(workspace, vault) else "workspace"
    linked_root = _first_existing_dir(_candidate_linked_roots())
    return [
        _root_descriptor(
            "workspace",
            "Workspace",
            workspace,
            webdav_available=webdav_available,
            share_request_enabled=share_request_enabled,
            resource_root=workspace_resource_root,
        ),
        _root_descriptor(
            "fleet",
            "Fleet",
            _first_existing_dir(_candidate_fleet_roots()),
            webdav_available=webdav_available,
        ),
        _root_descriptor(
            "linked",
            "Linked",
            linked_root,
            read_only=not _linked_root_has_writable_share(linked_root),
            linked=True,
        ),
    ]


def _default_root_id(roots: list[dict[str, Any]]) -> str:
    for preferred in ("workspace", "fleet", "linked"):
        for root in roots:
            if root.get("id") == preferred and root.get("available"):
                return preferred
    return ""


def _root_context(raw_root: Any = None) -> dict[str, Any]:
    root_id = str(raw_root or "").strip().lower()
    roots = _local_root_descriptors()
    if not root_id:
        root_id = _default_root_id(roots)
    if root_id == "vault":
        vault = _first_existing_dir(_candidate_vault_roots())
        if vault is None:
            raise HTTPException(status_code=404, detail="Workspace root is not available")
        return _root_descriptor(
            "workspace",
            "Workspace",
            vault,
            share_request_enabled=bool(_share_request_state().get("enabled")),
            resource_root="vault",
        )
    if root_id not in {"vault", "workspace", "fleet", "linked"}:
        raise HTTPException(status_code=400, detail="Unknown Drive root")
    for root in roots:
        if root["id"] == root_id:
            if not root.get("available"):
                raise HTTPException(status_code=404, detail=f"{root['label']} root is not available")
            return root
    raise HTTPException(status_code=404, detail="Drive root is not available")


_WRITABLE_ROOT_IDS = {"vault", "workspace", "fleet"}


def _assert_writable_root(root_id: str) -> None:
    """Fail closed before any Drive write: only owned writable roots may proceed.

    Linked passes through because every Linked write path must route through
    _linked_writable_source, which authorizes writes per accepted read/write
    shared folder and rejects everything else. Any other root id is rejected
    so future read-only roots cannot silently reach write handlers.
    """
    normalized = str(root_id or "").strip().lower()
    if normalized == "linked":
        return
    if normalized not in _WRITABLE_ROOT_IDS:
        raise HTTPException(status_code=403, detail=f"{_root_label(normalized)} root is read-only")


def _share_item_kind(path: Path) -> str:
    if path.is_dir():
        return "directory"
    if path.is_file():
        return "file"
    raise HTTPException(status_code=404, detail="Drive item does not exist")


def _share_request_payload(payload: dict[str, Any], ctx: dict[str, Any], target: Path, relative: str) -> dict[str, Any]:
    owner_deployment = _owner_deployment_id()
    if not owner_deployment:
        raise HTTPException(status_code=503, detail="ArcLink share-request broker deployment identity is not configured")
    display_name = _clean_text(payload.get("display_name") or target.name or _display_path(relative), 120)
    return {
        "contract": "arclink-share-grants",
        "source_plugin": "drive",
        "owner_deployment_id": owner_deployment,
        "resource_root": str(ctx.get("resource_root") or ctx.get("id") or "vault"),
        "resource_path": _display_path(relative),
        "resource_kind": "drive",
        "item_kind": _share_item_kind(target),
        "display_name": display_name,
        "requested_access": "read_write",
        "share_mode": "claim_nonce",
        "reshare_allowed": False,
    }


def _share_request_response(broker_result: dict[str, Any], request_payload: dict[str, Any]) -> dict[str, Any]:
    nonce = _clean_text(broker_result.get("nonce"), 120)
    if not nonce:
        raise HTTPException(status_code=502, detail="ArcLink share-request broker did not return a share link")
    try:
        expires_in_hours = int(broker_result.get("expires_in_hours") or 12)
    except (TypeError, ValueError):
        expires_in_hours = 12
    copy_text = str(broker_result.get("copy_text") or "")[:400]
    accept_command = _clean_text(broker_result.get("accept_command") or f"/arclink_share_accept {nonce}", 200)
    return {
        "ok": True,
        "broker": "arclink-share-grants",
        "mode": "claim_nonce",
        "nonce": nonce,
        "accept_command": accept_command,
        "copy_text": copy_text or (
            "A share request is available for review by Raven:\n" + accept_command
        ),
        "expires_at": _clean_text(broker_result.get("expires_at"), 60),
        "expires_in_hours": expires_in_hours,
        "display_name": _clean_text(request_payload.get("display_name"), 120),
        "request": request_payload,
    }


def _submit_share_request_to_broker(url: str, payload: dict[str, Any], auth_headers: dict[str, str]) -> dict[str, Any]:
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    headers.update(auth_headers)
    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response_body = response.read(1_000_000)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="ArcLink share-request broker rejected the request") from exc
    try:
        decoded = json.loads(response_body.decode("utf-8") or "{}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail="ArcLink share-request broker returned invalid JSON") from exc
    if not isinstance(decoded, dict):
        raise HTTPException(status_code=502, detail="ArcLink share-request broker returned invalid JSON")
    if decoded.get("ok") is False:
        raise HTTPException(status_code=502, detail=_clean_text(decoded.get("detail"), 200) or "ArcLink share-request broker failed")
    return decoded


def _meta_path() -> Path:
    return _hermes_home() / "state" / "drive-meta.json"


def _load_meta() -> dict[str, Any]:
    meta = _load_json(_meta_path())
    trash = meta.get("trash")
    if not isinstance(trash, dict):
        trash = {}
    return {"trash": trash}


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


def _json_list_form(raw_value: Any) -> list[Any]:
    if raw_value is None or raw_value == "":
        return []
    if isinstance(raw_value, list):
        return raw_value
    try:
        value = json.loads(str(raw_value))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Upload path metadata is invalid") from exc
    if not isinstance(value, list):
        raise HTTPException(status_code=400, detail="Upload path metadata must be a list")
    return value


def _clean_upload_relative_path(raw_path: Any, fallback_name: Any = "") -> str:
    candidate = str(raw_path or fallback_name or "").replace("\\", "/").strip().lstrip("/")
    parts: list[str] = []
    for part in candidate.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            raise HTTPException(status_code=400, detail="Upload path traversal is not allowed")
        parts.append(_sanitized_name(part))
    if not parts:
        parts.append(_sanitized_name(fallback_name))
    if len(parts) > 48:
        raise HTTPException(status_code=400, detail="Upload folder nesting is too deep")
    return "/".join(parts)


def _top_level_upload_folder(relative_path: str, directory_paths: set[str]) -> str:
    top = relative_path.split("/", 1)[0]
    if "/" in relative_path or relative_path in directory_paths:
        return top
    return ""


def _rewrite_keep_both_folder_uploads(
    root_path: Path,
    target_dir_path: str,
    relative_paths: list[str],
    directory_paths: list[str],
    *,
    policy: str,
    root_id: str,
) -> tuple[list[str], list[str]]:
    if policy != "keep-both":
        return relative_paths, directory_paths
    directory_set = set(directory_paths)
    top_folders = sorted(
        {
            folder
            for folder in [_top_level_upload_folder(path, directory_set) for path in [*relative_paths, *directory_paths]]
            if folder
        }
    )
    if not top_folders:
        return relative_paths, directory_paths
    rewrites: dict[str, str] = {}
    for folder in top_folders:
        target, _relative = _resolve_local(root_path, _join_display(target_dir_path, folder), root_id=root_id)
        rewritten = _resolve_conflict_destination(target, conflict="keep-both")
        rewrites[folder] = rewritten.name

    def rewrite(path: str) -> str:
        if not path:
            return path
        top, separator, rest = path.partition("/")
        replacement = rewrites.get(top)
        if not replacement:
            return path
        return replacement + (separator + rest if separator else "")

    return [rewrite(path) for path in relative_paths], [rewrite(path) for path in directory_paths]


def _webdav_ensure_collections(profile: dict[str, Any], raw_path: Any) -> None:
    relative = _clean_relative_path(raw_path)
    if not relative:
        return
    cursor = ""
    for part in relative.split("/"):
        cursor = posixpath.join(cursor, part) if cursor else part
        try:
            _dav_request(profile, "MKCOL", _display_path(cursor))
        except HTTPException as exc:
            if getattr(exc, "status_code", None) not in {405, 409}:
                raise


def _assert_accessible_path(root: Path, target: Path, *, root_id: str = "") -> None:
    root_resolved = root.resolve(strict=False)
    if target == root_resolved:
        return
    try:
        target.parent.relative_to(root_resolved)
    except ValueError:
        raise HTTPException(status_code=403, detail="Path is outside the selected Drive root")
    resolved = target.resolve(strict=False)
    if resolved == root_resolved or root_resolved in resolved.parents:
        return
    if str(root_id or "").strip().lower() == "linked" and _linked_target_allowed(root_resolved, target, resolved):
        return
    raise HTTPException(status_code=403, detail="Path is outside the selected Drive root")


def _resolve_local(root: Path, raw_path: Any, *, root_id: str = "") -> tuple[Path, str]:
    relative_path = _clean_relative_path(raw_path)
    root_resolved = root.resolve(strict=False)
    target = root_resolved / relative_path
    _assert_accessible_path(root_resolved, target, root_id=root_id)
    if relative_path:
        _assert_not_sensitive(target)
    return target, relative_path


def _assert_within_root(root: Path, path: Path, *, root_id: str = "") -> None:
    _assert_accessible_path(root.resolve(strict=False), path, root_id=root_id)


def _safe_child_relative(root: Path, path: Path, *, root_id: str = "") -> str | None:
    try:
        _assert_within_root(root, path, root_id=root_id)
        _assert_not_sensitive(path)
        return path.relative_to(root).as_posix()
    except (HTTPException, ValueError, OSError):
        return None


def _visible_child_count(root_id: str, root: Path, path: Path, *, limit: int = _MAX_CHILD_COUNT) -> tuple[int, bool]:
    try:
        children = path.iterdir()
    except OSError:
        return 0, False
    count = 0
    for child in children:
        if _should_skip(child):
            continue
        if _safe_child_relative(root, child, root_id=root_id) is None:
            continue
        count += 1
        if count > limit:
            return limit, True
    return count, False


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
    if path.name == ".env" or path.name.startswith(".env."):
        return True
    if path.suffix.lower() in _TEXT_EXTENSIONS:
        return True
    mime = mimetypes.guess_type(str(path))[0] or ""
    return mime.startswith("text/") or mime in {"application/json", "application/xml"}


def _iso_from_timestamp(value: float) -> str:
    return email.utils.formatdate(value, usegmt=True)


def _item_from_local(root_id: str, root: Path, path: Path, relative_path: str) -> dict[str, Any]:
    _assert_within_root(root, path, root_id=root_id)
    try:
        stat = path.stat()
    except OSError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    is_dir = path.is_dir()
    mime = "inode/directory" if is_dir else (mimetypes.guess_type(str(path))[0] or "application/octet-stream")
    display = _display_path(relative_path)
    child_count, child_count_truncated = _visible_child_count(root_id, root, path) if is_dir else (0, False)
    can_write = root_id != "linked"
    can_delete = can_write and bool(relative_path)
    can_upload = can_write and is_dir
    can_rename = can_delete
    if root_id == "linked":
        entry = _linked_manifest_entry(root, path)
        can_write = bool(entry and _linked_entry_writable(entry))
        share_root = bool(entry and len(Path(relative_path).parts) == 1)
        can_upload = can_write and is_dir
        can_delete = can_write and bool(relative_path) and not share_root
        can_rename = can_delete
    return {
        "name": path.name or "Drive",
        "root": root_id,
        "path": display,
        "kind": "folder" if is_dir else "file",
        "size": 0 if is_dir else stat.st_size,
        "modified": _iso_from_timestamp(stat.st_mtime),
        "mime": mime,
        "text": bool((not is_dir) and _is_text_item(path) and stat.st_size <= _MAX_TEXT_BYTES),
        "child_count": child_count,
        "child_count_truncated": child_count_truncated,
        "can_write": can_write,
        "can_upload": can_upload,
        "can_delete": can_delete,
        "can_rename": can_rename,
    }


def _should_skip(path: Path) -> bool:
    return path.name in _SKIP_DIR_NAMES


def _list_local(root_id: str, root: Path, raw_path: Any, *, query: str = "") -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    folder: dict[str, Any] | None = None
    if query.strip():
        needle = query.strip().lower()
        for current_root, dirnames, filenames in os.walk(root, followlinks=root_id == "linked"):
            dirnames[:] = [
                name
                for name in dirnames
                if name not in _SKIP_DIR_NAMES and _safe_child_relative(root, Path(current_root) / name, root_id=root_id) is not None
            ]
            for name in sorted([*dirnames, *filenames]):
                if needle not in name.lower():
                    continue
                candidate = Path(current_root) / name
                relative = _safe_child_relative(root, candidate, root_id=root_id)
                if relative is None:
                    continue
                items.append(_item_from_local(root_id, root, candidate, relative))
                if len(items) >= _SEARCH_LIMIT:
                    break
            if len(items) >= _SEARCH_LIMIT:
                break
        current_path = "/"
    else:
        target, relative = _resolve_local(root, raw_path, root_id=root_id)
        if not target.exists():
            raise HTTPException(status_code=404, detail=f"{_root_label(root_id)} path does not exist")
        if not target.is_dir():
            raise HTTPException(status_code=400, detail=f"{_root_label(root_id)} path is not a folder")
        folder = _item_from_local(root_id, root, target, relative)
        safe_children = [child for child in target.iterdir() if _safe_child_relative(root, child, root_id=root_id) is not None]
        for child in sorted(safe_children, key=lambda value: (not value.is_dir(), value.name.lower())):
            if _should_skip(child):
                continue
            child_relative = _safe_child_relative(root, child, root_id=root_id)
            if child_relative is None:
                continue
            items.append(_item_from_local(root_id, root, child, child_relative))
        current_path = _display_path(relative)
    return {
        "backend": "local-vault",
        "root": root_id,
        "path": current_path,
        "folder": folder,
        "items": items,
        "query": query.strip(),
    }


def _move_local(root_id: str, root: Path, source_path: Any, destination_path: Any) -> dict[str, Any]:
    _assert_writable_root(root_id)
    source, source_relative, source_root, source_slug = _resolve_writable_local(root_id, root, source_path)
    destination, destination_relative, destination_root, destination_slug = _resolve_writable_local(
        root_id,
        root,
        destination_path,
        allow_share_root=True,
    )
    if source_root != destination_root:
        raise HTTPException(status_code=400, detail="Move between shared folders is not supported")
    if not source.exists():
        raise HTTPException(status_code=404, detail="Drive source path does not exist")
    if source == source_root:
        raise HTTPException(status_code=400, detail="Cannot move the Drive root")
    if destination.exists():
        raise HTTPException(status_code=409, detail="Destination already exists")
    if source.is_dir() and (destination == source or source in destination.parents):
        raise HTTPException(status_code=400, detail="Cannot move a folder into itself")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    source_display = _linked_display_path(source_slug, source_relative) if source_slug else _display_path(source_relative)
    destination_display = _linked_display_path(destination_slug, destination_relative) if destination_slug else _display_path(destination_relative)
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


def _copy_confined(source: Path, destination: Path) -> None:
    _assert_not_sensitive(source)
    _assert_not_sensitive(destination)
    if source.is_symlink():
        raise HTTPException(status_code=400, detail="Symlink copy is not supported")
    if source.is_dir():
        destination.mkdir(parents=True, exist_ok=False)
        for child in source.iterdir():
            if child.name in _SKIP_DIR_NAMES or child.is_symlink() or _is_sensitive_path(child):
                continue
            _copy_confined(child, destination / child.name)
        shutil.copystat(source, destination, follow_symlinks=False)
        return
    shutil.copy2(source, destination, follow_symlinks=False)


def _copy_local(root_id: str, root: Path, source_path: Any, destination_path: Any, *, conflict: str = "reject") -> dict[str, Any]:
    _assert_writable_root(root_id)
    source, source_relative, source_root, source_slug = _resolve_writable_local(root_id, root, source_path)
    destination, destination_relative, destination_root, destination_slug = _resolve_writable_local(
        root_id,
        root,
        destination_path,
        allow_share_root=True,
    )
    if source_root != destination_root:
        raise HTTPException(status_code=400, detail="Copy between shared folders is not supported")
    if not source.exists():
        raise HTTPException(status_code=404, detail="Drive source path does not exist")
    if source == source_root:
        raise HTTPException(status_code=400, detail="Cannot copy the Drive root")
    if source.is_dir() and (destination == source or source in destination.parents):
        raise HTTPException(status_code=400, detail="Cannot copy a folder into itself")
    _assert_no_symlink_escape(source_root, source)
    destination = _resolve_conflict_destination(destination, conflict=conflict)
    destination_relative = destination.relative_to(destination_root).as_posix()
    destination.parent.mkdir(parents=True, exist_ok=True)
    _copy_confined(source, destination)
    return {
        "ok": True,
        "root": root_id,
        "path": _linked_display_path(source_slug, source_relative) if source_slug else _display_path(source_relative),
        "destination": _linked_display_path(destination_slug, destination_relative) if destination_slug else _display_path(destination_relative),
    }


def _default_writable_root_id() -> str:
    for candidate in _local_root_descriptors():
        if candidate.get("id") in {"vault", "workspace"} and candidate.get("available") and not candidate.get("read_only"):
            return str(candidate["id"])
    raise HTTPException(status_code=404, detail="No writable Drive root is available")


def _copy_between_roots(
    source_ctx: dict[str, Any],
    destination_ctx: dict[str, Any],
    source_path: Any,
    destination_path: Any,
    *,
    conflict: str = "reject",
) -> dict[str, Any]:
    source_root_id = str(source_ctx["id"])
    destination_root_id = str(destination_ctx["id"])
    if source_root_id != "linked":
        raise HTTPException(status_code=400, detail="Cross-root copy is only supported from Linked into owned roots")
    _assert_writable_root(destination_root_id)
    source_root = Path(source_ctx["path"])
    destination_root = Path(destination_ctx["path"])
    source, source_relative = _resolve_local(source_root, source_path, root_id=source_root_id)
    destination, destination_relative = _resolve_local(destination_root, destination_path, root_id=destination_root_id)
    if not source.exists():
        raise HTTPException(status_code=404, detail="Drive source path does not exist")
    if source == source_root:
        raise HTTPException(status_code=400, detail="Cannot copy the Linked root")
    source_for_copy = source.resolve(strict=False)
    _assert_not_sensitive(source)
    _assert_not_sensitive(source_for_copy)
    if source_for_copy.is_dir() and (destination == source_for_copy or source_for_copy in destination.parents):
        raise HTTPException(status_code=400, detail="Cannot copy a folder into itself")
    destination = _resolve_conflict_destination(destination, conflict=conflict)
    destination_relative = destination.relative_to(destination_root.resolve(strict=False)).as_posix()
    destination.parent.mkdir(parents=True, exist_ok=True)
    _copy_confined(source_for_copy, destination)
    return {
        "ok": True,
        "root": source_root_id,
        "path": _display_path(source_relative),
        "destination_root": destination_root_id,
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
        raise HTTPException(status_code=400, detail="Cannot move the Drive root")
    _dav_request(
        profile,
        "MOVE",
        source_display,
        headers={"Destination": _webdav_url(profile, destination_display), "Overwrite": "F"},
    )
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


def _item_from_dav(profile: dict[str, Any], response: ET.Element) -> dict[str, Any]:
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
    suffix = Path(relative).suffix.lower()
    return {
        "name": posixpath.basename(relative.rstrip("/")) or "Drive",
        "path": display,
        "kind": "folder" if is_dir else "file",
        "size": 0 if is_dir else size,
        "modified": _text_from(prop, "d:getlastmodified"),
        "mime": mime,
        "text": bool((not is_dir) and (mime.startswith("text/") or suffix in _TEXT_EXTENSIONS) and size <= _MAX_TEXT_BYTES),
    }


def _list_dav(profile: dict[str, Any], raw_path: Any, *, query: str = "") -> dict[str, Any]:
    if query.strip():
        raise HTTPException(status_code=400, detail="Search is available through the local Drive backend")
    _status, body, _headers = _dav_request(
        profile,
        "PROPFIND",
        raw_path,
        body=_propfind_body(),
        headers={"Depth": "1", "Content-Type": "application/xml"},
    )
    root = ET.fromstring(body)
    items: list[dict[str, Any]] = []
    current_path = _display_path(_clean_relative_path(raw_path))
    for response in root.findall("d:response", _DAV_NS):
        item = _item_from_dav(profile, response)
        if item["path"] == current_path:
            continue
        items.append(item)
    items.sort(key=lambda item: (item["kind"] != "folder", str(item["name"]).lower()))
    return {
        "backend": "nextcloud-webdav",
        "path": current_path,
        "items": items,
        "query": "",
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
    share_request_state = _share_request_state()
    roots = _local_root_descriptors(
        webdav_available=webdav_available,
        share_request_enabled=bool(share_request_state.get("enabled")),
    )
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
        "share_request": share_request_state,
        "mount": nextcloud.get("mount") or "/Vault",
        "username": nextcloud.get("username") or "",
        "url": nextcloud.get("url") or "",
        "source": nextcloud.get("source") or "",
        "local_root": str(root.get("path") or "") if root else "",
        "capabilities": dict(root.get("capabilities") or {}) if root else _root_capabilities(
            available=backend["name"] == "nextcloud-webdav",
            backend=backend["name"],
            webdav_available=webdav_available,
            share_request_enabled=bool(share_request_state.get("enabled")),
        ),
    }


@router.post("/share/request")
async def share_request(request: Request) -> dict[str, Any]:
    payload = await _request_json(request)
    payload = payload if isinstance(payload, dict) else {}
    ctx = _root_context(payload.get("root") or payload.get("root_id"))
    if str(ctx.get("id") or "").strip().lower() == "linked":
        raise HTTPException(status_code=403, detail="Linked resources cannot be reshared from Drive")
    target, relative = _resolve_local(Path(ctx["path"]), payload.get("path"), root_id=ctx["id"])
    request_payload = _share_request_payload(payload, ctx, target, relative)
    broker_url = _share_request_broker_url()
    if not broker_url:
        raise HTTPException(status_code=503, detail="ArcLink share-request broker is not configured")
    auth_headers = _share_request_auth_headers()
    broker_result = _submit_share_request_to_broker(broker_url, request_payload, auth_headers)
    return _share_request_response(broker_result, request_payload)


@router.get("/items")
async def items(path: str = "/", query: str = "", root: str = "") -> dict[str, Any]:
    if root:
        ctx = _root_context(root)
        return _list_local(ctx["id"], Path(ctx["path"]), path, query=query)
    backend = _backend()
    if backend["name"] == "local-vault":
        return _list_local("vault", backend["root"], path, query=query)
    if backend["name"] == "nextcloud-webdav":
        return _list_dav(backend["profile"], path, query=query)
    ctx = _root_context(root)
    return _list_local(ctx["id"], Path(ctx["path"]), path, query=query)


@router.get("/content")
async def content(path: str, root: str = "") -> dict[str, Any]:
    if root:
        ctx = _root_context(root)
        target, relative = _resolve_local(Path(ctx["path"]), path, root_id=ctx["id"])
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
        target, relative = _resolve_local(backend["root"], path, root_id="vault")
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
        target, _relative = _resolve_local(Path(ctx["path"]), path, root_id=ctx["id"])
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Drive file does not exist")
        return FileResponse(str(target), filename=target.name, media_type=mimetypes.guess_type(str(target))[0])
    backend = _backend()
    if backend["name"] == "local-vault":
        target, _relative = _resolve_local(backend["root"], path, root_id="vault")
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
        target, _relative = _resolve_local(Path(ctx["path"]), path, root_id=ctx["id"])
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Drive file does not exist")
        return FileResponse(
            str(target),
            media_type=mimetypes.guess_type(str(target))[0] or "application/octet-stream",
            headers={"Content-Disposition": _inline_content_disposition(target.name)},
        )
    backend = _backend()
    if backend["name"] == "local-vault":
        target, _relative = _resolve_local(backend["root"], path, root_id="vault")
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
    payload = await _request_json(request)
    root_id = payload.get("root") or ""
    path = payload.get("path") or "/"
    name = payload.get("name")
    if name:
        path = _join_display(str(path), _sanitized_name(name))
    if root_id:
        ctx = _root_context(root_id)
        _assert_writable_root(ctx["id"])
        target, relative, _effective_root, slug = _resolve_writable_local(ctx["id"], Path(ctx["path"]), path)
        target.mkdir(parents=True, exist_ok=True)
        return {"ok": True, "root": ctx["id"], "path": _linked_display_path(slug, relative) if slug else _display_path(relative)}
    backend = _backend()
    if backend["name"] == "local-vault":
        target, relative = _resolve_local(backend["root"], path, root_id="vault")
        target.mkdir(parents=True, exist_ok=True)
        return {"ok": True, "root": "vault", "path": _display_path(relative)}
    if backend["name"] == "nextcloud-webdav":
        _dav_request(backend["profile"], "MKCOL", path)
        return {"ok": True, "path": _display_path(_clean_relative_path(path))}
    raise HTTPException(status_code=404, detail="Drive is not available")


@router.post("/move")
async def move(request: Request) -> dict[str, Any]:
    payload = await _request_json(request)
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
    payload = await _request_json(request)
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


@router.post("/delete")
async def delete(request: Request) -> dict[str, Any]:
    payload = await _request_json(request)
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
    _assert_writable_root(root_id)
    target, relative, effective_root, slug = _resolve_writable_local(root_id, root, raw_path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Drive path does not exist")
    if target == effective_root:
        raise HTTPException(status_code=400, detail="Cannot delete the Drive root")
    item_kind = "folder" if target.is_dir() else "file"
    trash_target = _next_trash_path(effective_root, relative)
    shutil.move(str(target), str(trash_target))
    display = _linked_display_path(slug, relative) if slug else _display_path(relative)
    trash_relative = trash_target.relative_to(effective_root).as_posix()
    trash_display = _linked_display_path(slug, trash_relative) if slug else _display_path(trash_relative)
    meta = _load_meta()
    _root_meta(meta, "trash", root_id)[trash_display] = {
        "root": root_id,
        "original_path": display,
        "trash_path": trash_display,
        "kind": item_kind,
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
        target, _relative = _resolve_local(root_path, trash_path, root_id=root_id)
        if target.exists():
            records.append(record)
    return {"root": root_id, "items": records}


@router.post("/restore")
async def restore(request: Request) -> dict[str, Any]:
    payload = await _request_json(request)
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
    _assert_writable_root(root_id)
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
    trash_target, _trash_relative, effective_root, slug = _resolve_writable_local(root_id, root_path, requested)
    destination, destination_relative, destination_root, destination_slug = _resolve_writable_local(
        root_id,
        root_path,
        record.get("original_path"),
        allow_share_root=True,
    )
    if effective_root != destination_root:
        raise HTTPException(status_code=400, detail="Restore between shared folders is not supported")
    if destination.exists():
        raise HTTPException(status_code=409, detail="Original path already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(trash_target), str(destination))
    trash_records.pop(requested, None)
    _save_meta(meta)
    display_slug = destination_slug or slug
    return {"ok": True, "root": root_id, "path": _linked_display_path(display_slug, destination_relative) if display_slug else _display_path(destination_relative)}


@router.post("/upload")
async def upload(
    path: str = Form("/"),
    root: str = Form(""),
    conflict: str = Form("reject"),
    relative_paths: str = Form(""),
    directories: str = Form(""),
    files: list[UploadFile] | None = File(None),
) -> dict[str, Any]:
    root = _form_value(root, "")
    ctx: dict[str, Any] | None = _root_context(root) if root else None
    if ctx is not None:
        _assert_writable_root(ctx["id"])
    backend = _backend()
    uploaded: list[dict[str, Any]] = []
    target_dir_path = _clean_relative_path(_form_value(path, "/"))
    policy = str(_form_value(conflict, "reject") or "reject").strip().lower()
    if policy not in {"reject", "keep-both"}:
        raise HTTPException(status_code=400, detail="Unsupported conflict policy")
    file_items = list(files or [])
    if len(file_items) > _max_upload_files():
        raise HTTPException(status_code=413, detail="Too many files in one upload")
    if len(_form_value(relative_paths, "").encode("utf-8")) > _max_upload_metadata_bytes():
        raise HTTPException(status_code=413, detail="Upload relative-path metadata is too large")
    if len(_form_value(directories, "").encode("utf-8")) > _max_upload_metadata_bytes():
        raise HTTPException(status_code=413, detail="Upload directory metadata is too large")
    relative_path_metadata = _json_list_form(_form_value(relative_paths, ""))
    uploaded_paths = [
        _clean_upload_relative_path(
            relative_path_metadata[index] if index < len(relative_path_metadata) else "",
            upload_file.filename,
        )
        for index, upload_file in enumerate(file_items)
    ]
    directory_paths = [
        _clean_upload_relative_path(item, item)
        for item in _json_list_form(_form_value(directories, ""))
        if str(item or "").strip()
    ]
    if len(directory_paths) > _max_upload_directories():
        raise HTTPException(status_code=413, detail="Too many directories in one upload")
    if len(uploaded_paths) != len(file_items):
        raise HTTPException(status_code=400, detail="Upload file metadata is inconsistent")
    if not uploaded_paths and not directory_paths:
        raise HTTPException(status_code=400, detail="Upload is empty")
    if ctx is not None:
        effective_target_dir = target_dir_path
        effective_root_path = Path(ctx["path"])
        linked_slug = ""
        if ctx["id"] == "linked":
            target_dir, effective_target_dir, effective_root_path, linked_slug = _resolve_writable_local(
                ctx["id"],
                Path(ctx["path"]),
                target_dir_path,
                allow_share_root=True,
            )
            if not target_dir.is_dir():
                raise HTTPException(status_code=400, detail="Upload target must be a shared folder")
        uploaded_paths, directory_paths = _rewrite_keep_both_folder_uploads(
            effective_root_path,
            effective_target_dir,
            uploaded_paths,
            directory_paths,
            policy=policy,
            root_id="" if ctx["id"] == "linked" else ctx["id"],
        )
        for directory_path in directory_paths:
            target, _relative = _resolve_local(
                effective_root_path,
                _join_display(effective_target_dir, directory_path),
                root_id="" if ctx["id"] == "linked" else ctx["id"],
            )
            target.mkdir(parents=True, exist_ok=True)
    elif backend["name"] == "local-vault":
        uploaded_paths, directory_paths = _rewrite_keep_both_folder_uploads(
            backend["root"],
            target_dir_path,
            uploaded_paths,
            directory_paths,
            policy=policy,
            root_id="vault",
        )
        for directory_path in directory_paths:
            target, _relative = _resolve_local(backend["root"], _join_display(target_dir_path, directory_path), root_id="vault")
            target.mkdir(parents=True, exist_ok=True)
    elif backend["name"] == "nextcloud-webdav":
        if policy == "keep-both":
            raise HTTPException(status_code=400, detail="Keep-both upload conflict policy is only available for local Drive roots")
        for directory_path in directory_paths:
            _webdav_ensure_collections(backend["profile"], _join_display(target_dir_path, directory_path))
    total_uploaded = 0
    max_total = _max_upload_total_bytes()
    local_written_targets: list[Path] = []
    for upload_file, relative_upload_path in zip(file_items, uploaded_paths, strict=True):
        display = _join_display(target_dir_path, relative_upload_path)
        if ctx is not None:
            if ctx["id"] == "linked":
                target, relative = _resolve_local(effective_root_path, _join_display(effective_target_dir, relative_upload_path), root_id="")
            else:
                target, relative = _resolve_local(Path(ctx["path"]), display, root_id=ctx["id"])
            target = _resolve_conflict_destination(target, conflict=policy)
            relative = target.relative_to(effective_root_path if ctx["id"] == "linked" else Path(ctx["path"])).as_posix()
            size = await _write_upload_file_atomic(upload_file, target)
            if total_uploaded + size > max_total:
                try:
                    target.unlink(missing_ok=True)
                except OSError:
                    pass
                for written_target in local_written_targets:
                    try:
                        written_target.unlink(missing_ok=True)
                    except OSError:
                        pass
                raise HTTPException(status_code=413, detail="Upload request is too large")
            total_uploaded += size
            local_written_targets.append(target)
            uploaded.append({
                "root": ctx["id"],
                "path": _linked_display_path(linked_slug, relative) if ctx["id"] == "linked" else _display_path(relative),
                "size": size,
            })
        elif backend["name"] == "local-vault":
            target, relative = _resolve_local(backend["root"], display, root_id="vault")
            target = _resolve_conflict_destination(target, conflict=policy)
            relative = target.relative_to(backend["root"]).as_posix()
            size = await _write_upload_file_atomic(upload_file, target)
            if total_uploaded + size > max_total:
                try:
                    target.unlink(missing_ok=True)
                except OSError:
                    pass
                for written_target in local_written_targets:
                    try:
                        written_target.unlink(missing_ok=True)
                    except OSError:
                        pass
                raise HTTPException(status_code=413, detail="Upload request is too large")
            total_uploaded += size
            local_written_targets.append(target)
            uploaded.append({"root": "vault", "path": _display_path(relative), "size": size})
        elif backend["name"] == "nextcloud-webdav":
            content_bytes = await _read_upload_bytes(upload_file)
            if total_uploaded + len(content_bytes) > max_total:
                raise HTTPException(status_code=413, detail="Upload request is too large")
            total_uploaded += len(content_bytes)
            headers = {"If-None-Match": "*"} if policy == "reject" else {}
            parent = posixpath.dirname(_clean_relative_path(display))
            _webdav_ensure_collections(backend["profile"], _display_path(parent))
            _dav_request(backend["profile"], "PUT", display, body=content_bytes, headers=headers)
            uploaded.append({"path": display, "size": len(content_bytes)})
        else:
            raise HTTPException(status_code=404, detail="Drive is not available")
    return {"ok": True, "uploaded": uploaded}


@router.post("/new-file")
async def new_file(request: Request) -> dict[str, Any]:
    payload = await _request_json(request)
    ctx = _root_context(payload.get("root"))
    _assert_writable_root(ctx["id"])
    parent = payload.get("path") or "/"
    name = _sanitized_name(payload.get("name"))
    target, relative, _effective_root, slug = _resolve_writable_local(
        ctx["id"],
        Path(ctx["path"]),
        _join_display(str(parent), name),
    )
    if target.exists():
        raise HTTPException(status_code=409, detail="File already exists")
    if target.suffix.lower() not in _TEXT_EXTENSIONS:
        raise HTTPException(status_code=400, detail="New file is limited to text-like file extensions")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(payload.get("content") or ""), encoding="utf-8")
    return {"ok": True, "root": ctx["id"], "path": _linked_display_path(slug, relative) if slug else _display_path(relative)}


@router.post("/copy")
async def copy(request: Request) -> dict[str, Any]:
    payload = await _request_json(request)
    root_id = payload.get("root")
    ctx = _root_context(root_id)
    destination_root = payload.get("destination_root") or (_default_writable_root_id() if ctx["id"] == "linked" else ctx["id"])
    destination_ctx = _root_context(destination_root)
    source_path = payload.get("path") or payload.get("source_path")
    destination_path = payload.get("destination_path") or payload.get("destination")
    if not source_path or not destination_path:
        raise HTTPException(status_code=400, detail="Source and destination are required")
    if destination_ctx["id"] != ctx["id"]:
        return _copy_between_roots(
            ctx,
            destination_ctx,
            source_path,
            destination_path,
            conflict=str(payload.get("conflict") or "reject"),
        )
    return _copy_local(
        ctx["id"],
        Path(ctx["path"]),
        source_path,
        destination_path,
        conflict=str(payload.get("conflict") or "reject"),
    )


@router.post("/duplicate")
async def duplicate(request: Request) -> dict[str, Any]:
    payload = await _request_json(request)
    ctx = _root_context(payload.get("root"))
    source_path = payload.get("path") or payload.get("source_path")
    if not source_path:
        raise HTTPException(status_code=400, detail="Source path is required")
    if ctx["id"] == "linked":
        destination_root = payload.get("destination_root") or _default_writable_root_id()
        destination_path = payload.get("destination_path") or _display_path(posixpath.basename(_clean_relative_path(source_path)))
        return _copy_between_roots(
            ctx,
            _root_context(destination_root),
            source_path,
            destination_path,
            conflict="keep-both",
        )
    return _copy_local(
        ctx["id"],
        Path(ctx["path"]),
        source_path,
        _duplicate_destination(source_path),
        conflict="keep-both",
    )


@router.post("/batch")
async def batch(request: Request) -> dict[str, Any]:
    payload = await _request_json(request)
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
            elif action == "copy":
                destination_root = payload.get("destination_root") or (_default_writable_root_id() if ctx["id"] == "linked" else ctx["id"])
                destination_folder = payload.get("destination_folder") or payload.get("destination_path")
                if not destination_folder:
                    raise HTTPException(status_code=400, detail="Batch copy destination folder is required")
                destination = _join_display(str(destination_folder), posixpath.basename(_clean_relative_path(raw_path)))
                destination_ctx = _root_context(destination_root)
                if destination_ctx["id"] != ctx["id"]:
                    result = _copy_between_roots(
                        ctx,
                        destination_ctx,
                        raw_path,
                        destination,
                        conflict=str(payload.get("conflict") or "reject"),
                    )
                else:
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
