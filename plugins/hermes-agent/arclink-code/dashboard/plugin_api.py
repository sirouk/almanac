from __future__ import annotations

import difflib
import email.utils
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from typing import Any
import uuid

try:
    from fastapi import APIRouter, HTTPException, Request
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


router = APIRouter()

_TEXT_EXTENSIONS = {
    ".css",
    ".env",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mdx",
    ".py",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
_SKIP_DIR_NAMES = {".git", ".hg", ".svn", "__pycache__", "node_modules", ".next"}
_MAX_TEXT_BYTES = 1_000_000
_MAX_DIFF_BYTES = 400_000
_MAX_SEARCH_FILE_BYTES = 400_000
_MAX_SEARCH_RESULTS = 80
_MAX_REPOS = 80
_MAX_REPO_SCAN_DEPTH = 4
_MAX_TREE_DEPTH = 4
_MAX_TREE_CHILDREN = 200
_GIT_TIMEOUT_SECONDS = 15
_TRASH_INDEX_VERSION = 1


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes")).expanduser()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".arclink-code-", suffix=".json.tmp")
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


def _clean_url(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith(("https://", "http://")):
        return text
    return ""


def _clean_text(value: Any, limit: int = 160) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def _workspace_root() -> Path:
    explicit = os.environ.get("ARCLINK_CODE_WORKSPACE_ROOT")
    if explicit:
        return Path(explicit).expanduser().resolve(strict=False)
    return Path(os.environ.get("HOME") or str(Path.home())).expanduser().resolve(strict=False)


def _load_access() -> dict[str, Any]:
    return _load_json(_hermes_home() / "state" / "arclink-web-access.json")


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


def _resolve(raw_path: Any) -> tuple[Path, str]:
    root = _workspace_root()
    relative = _clean_relative_path(raw_path)
    target = (root / relative).resolve(strict=False)
    if target != root and root not in target.parents:
        raise HTTPException(status_code=403, detail="Path is outside ArcLink Code")
    return target, relative


def _require_operable_path(raw_path: Any) -> tuple[Path, str]:
    target, relative = _resolve(raw_path)
    if not relative:
        raise HTTPException(status_code=400, detail="Workspace root cannot be changed by this operation")
    if not target.exists():
        raise HTTPException(status_code=404, detail="Workspace path does not exist")
    return target, relative


def _require_destination(raw_path: Any, *, overwrite: bool = False) -> tuple[Path, str]:
    target, relative = _resolve(raw_path)
    if not relative:
        raise HTTPException(status_code=400, detail="Workspace root is not a valid destination")
    if target.exists() and not overwrite:
        raise HTTPException(status_code=409, detail="Destination already exists")
    parent = target.parent.resolve(strict=False)
    root = _workspace_root()
    if parent != root and root not in parent.parents:
        raise HTTPException(status_code=403, detail="Destination parent is outside ArcLink Code")
    parent.mkdir(parents=True, exist_ok=True)
    return target, relative


def _clean_leaf_name(raw_name: Any) -> str:
    name = str(raw_name or "").strip()
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="A safe file or folder name is required")
    return name


def _trash_dir() -> Path:
    return _hermes_home() / "state" / "arclink-code-trash"


def _trash_index_path() -> Path:
    return _trash_dir() / "index.json"


def _load_trash_index() -> dict[str, Any]:
    payload = _load_json(_trash_index_path())
    entries = payload.get("entries")
    return {
        "version": _TRASH_INDEX_VERSION,
        "entries": entries if isinstance(entries, list) else [],
    }


def _save_trash_index(payload: dict[str, Any]) -> None:
    _write_json_atomic(_trash_index_path(), payload)


def _trash_payload() -> dict[str, Any]:
    index = _load_trash_index()
    entries = [entry for entry in index["entries"] if isinstance(entry, dict)]
    entries.sort(key=lambda entry: str(entry.get("trashed_at") or ""), reverse=True)
    return {
        "trash": [
            {
                "id": str(entry.get("id") or ""),
                "name": str(entry.get("name") or ""),
                "path": str(entry.get("path") or ""),
                "kind": str(entry.get("kind") or "file"),
                "trashed_at": str(entry.get("trashed_at") or ""),
            }
            for entry in entries
            if entry.get("id") and entry.get("path")
        ]
    }


def _copy_confined(source: Path, destination: Path) -> None:
    if source.is_symlink():
        raise HTTPException(status_code=400, detail="Symlink copy is not supported")
    if source.is_dir():
        destination.mkdir(parents=True, exist_ok=False)
        for child in source.iterdir():
            if child.name in _SKIP_DIR_NAMES or child.is_symlink():
                continue
            _copy_confined(child, destination / child.name)
        shutil.copystat(source, destination, follow_symlinks=False)
        return
    if not source.is_file():
        raise HTTPException(status_code=400, detail="Workspace path is not copyable")
    shutil.copy2(source, destination, follow_symlinks=False)


def _iso_from_timestamp(value: float) -> str:
    return email.utils.formatdate(value, usegmt=True)


def _is_text_file(path: Path) -> bool:
    if path.suffix.lower() in _TEXT_EXTENSIONS:
        return True
    mime = mimetypes.guess_type(str(path))[0] or ""
    return mime.startswith("text/") or mime in {"application/json", "application/xml"}


def _language_for(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return {
        ".css": "css",
        ".html": "html",
        ".js": "javascript",
        ".json": "json",
        ".jsx": "javascript",
        ".md": "markdown",
        ".mdx": "markdown",
        ".py": "python",
        ".sh": "shell",
        ".sql": "sql",
        ".toml": "toml",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".xml": "xml",
        ".yaml": "yaml",
        ".yml": "yaml",
    }.get(suffix, "plaintext")


def _entry_sort_key(path: Path) -> tuple[bool, str]:
    return (not (not path.is_symlink() and path.is_dir()), path.name.lower())


def _item_for(path: Path, relative: str) -> dict[str, Any]:
    try:
        stat = path.stat()
    except OSError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    is_dir = path.is_dir()
    mime = "inode/directory" if is_dir else (mimetypes.guess_type(str(path))[0] or "application/octet-stream")
    return {
        "name": path.name or "Workspace",
        "path": _display_path(relative),
        "kind": "folder" if is_dir else "file",
        "size": 0 if is_dir else stat.st_size,
        "modified": _iso_from_timestamp(stat.st_mtime),
        "mime": mime,
        "text": bool((not is_dir) and _is_text_file(path) and stat.st_size <= _MAX_TEXT_BYTES),
        "language": _language_for(relative),
    }


def _tree_for(path: Path, relative: str, depth: int) -> dict[str, Any]:
    node = _item_for(path, relative)
    if not path.is_dir():
        return node
    children: list[dict[str, Any]] = []
    if depth > 0:
        for child in sorted(path.iterdir(), key=_entry_sort_key):
            if len(children) >= _MAX_TREE_CHILDREN:
                node["truncated"] = True
                break
            if child.name in _SKIP_DIR_NAMES or child.is_symlink():
                continue
            child_relative = child.relative_to(_workspace_root()).as_posix()
            children.append(_tree_for(child, child_relative, depth - 1))
    node["children"] = children
    return node


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".arclink-code-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_display_path(path: Path) -> str:
    root = _workspace_root()
    try:
        relative = path.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Repository is outside ArcLink Code") from exc
    return _display_path(relative.as_posix())


def _workspace_display_path(path: Path) -> str:
    root = _workspace_root()
    try:
        relative = path.resolve(strict=False).relative_to(root)
    except ValueError:
        return ""
    return _display_path(relative.as_posix())


def _resolve_repo(raw_repo: Any) -> tuple[Path, str]:
    repo, relative = _resolve(raw_repo or "/")
    if not repo.is_dir():
        raise HTTPException(status_code=404, detail="Repository path does not exist")
    if not (repo / ".git").exists():
        raise HTTPException(status_code=400, detail="Selected folder is not a git repository")
    return repo, relative


def _clean_repo_file_path(raw_path: Any) -> str:
    relative = _clean_relative_path(raw_path)
    if not relative:
        raise HTTPException(status_code=400, detail="A repository file path is required")
    return relative


def _resolve_repo_file(repo: Path, raw_path: Any) -> tuple[Path, str]:
    relative = _clean_repo_file_path(raw_path)
    target = (repo / relative).resolve(strict=False)
    if target != repo and repo not in target.parents:
        raise HTTPException(status_code=403, detail="Repository file is outside ArcLink Code")
    return target, relative


def _run_git(repo: Path, args: list[str], *, check: bool = True) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            text=True,
            capture_output=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="git is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="git command timed out") from exc
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "git command failed").strip()
        raise HTTPException(status_code=400, detail=detail[:500])
    return result.stdout


def _read_repo_text(path: Path) -> str:
    if not path.exists():
        return ""
    if not path.is_file():
        raise HTTPException(status_code=400, detail="Repository path is not a file")
    stat = path.stat()
    if stat.st_size > _MAX_DIFF_BYTES or not _is_text_file(path):
        raise HTTPException(status_code=415, detail="This file is not diffable here")
    return path.read_text(encoding="utf-8", errors="replace")


def _git_object_text(repo: Path, spec: str, *, allow_missing: bool = True) -> str:
    output = _run_git(repo, ["show", spec], check=False)
    if output:
        if len(output.encode("utf-8", errors="replace")) > _MAX_DIFF_BYTES:
            raise HTTPException(status_code=413, detail="Diff source is too large")
        return output
    if allow_missing:
        return ""
    raise HTTPException(status_code=404, detail="Git object was not found")


def _unified_diff(before: str, after: str, before_label: str, after_label: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=before_label,
            tofile=after_label,
            lineterm="",
        )
    )


def _git_branch(repo: Path) -> str:
    branch = _run_git(repo, ["branch", "--show-current"], check=False).strip()
    if branch:
        return branch
    short = _run_git(repo, ["rev-parse", "--short", "HEAD"], check=False).strip()
    return short or "detached"


def _repo_item(root: Path, repo: Path) -> dict[str, Any]:
    display = _repo_display_path(repo)
    return {
        "name": repo.name or "Workspace",
        "path": display,
        "branch": _git_branch(repo),
        "root": str(repo),
        "workspace_root": str(root),
    }


def _discover_repos(root: Path) -> list[dict[str, Any]]:
    if not root.is_dir():
        return []
    repos: list[dict[str, Any]] = []
    for current_root, dirnames, _filenames in os.walk(root):
        current = Path(current_root)
        try:
            relative = current.relative_to(root)
        except ValueError:
            continue
        depth = 0 if str(relative) == "." else len(relative.parts)
        dirnames[:] = [name for name in dirnames if name not in _SKIP_DIR_NAMES]
        if (current / ".git").exists():
            repos.append(_repo_item(root, current))
            if len(repos) >= _MAX_REPOS:
                break
        if depth >= _MAX_REPO_SCAN_DEPTH:
            dirnames[:] = []
    repos.sort(key=lambda item: (item["path"] != "/", str(item["path"]).lower()))
    return repos


def _status_label(code: str) -> str:
    labels = {
        "??": "Untracked",
        "A": "Added",
        "D": "Deleted",
        "M": "Modified",
        "R": "Renamed",
        "C": "Copied",
        "U": "Conflict",
    }
    compact = code.replace(" ", "")
    if not compact:
        return "Clean"
    if "U" in compact:
        return "Conflict"
    parts = [labels.get(char, char) for char in compact]
    return " / ".join(parts)


def _change_record(path: str, x_status: str, y_status: str, old_path: str = "") -> dict[str, Any]:
    raw = f"{x_status}{y_status}"
    return {
        "path": path,
        "old_path": old_path,
        "status": raw,
        "label": _status_label(raw),
        "staged": x_status not in {" ", "?"},
        "unstaged": y_status != " ",
        "untracked": x_status == "?" and y_status == "?",
    }


def _git_status_payload(repo: Path, repo_relative: str) -> dict[str, Any]:
    output = _run_git(repo, ["status", "--porcelain=v1", "-z", "-b"])
    records = output.split("\0")
    branch = _git_branch(repo)
    staged: list[dict[str, Any]] = []
    unstaged: list[dict[str, Any]] = []
    untracked: list[dict[str, Any]] = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        if record.startswith("## "):
            branch = record[3:] or branch
            continue
        if len(record) < 4:
            continue
        x_status = record[0]
        y_status = record[1]
        path = record[3:]
        old_path = ""
        if x_status in {"R", "C"} and index < len(records):
            old_path = records[index]
            index += 1
        change = _change_record(path, x_status, y_status, old_path)
        if change["staged"]:
            staged.append(change)
        if change["untracked"]:
            untracked.append(change)
        elif change["unstaged"]:
            unstaged.append(change)
    return {
        "repo": _display_path(repo_relative),
        "branch": branch,
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
        "clean": not staged and not unstaged and not untracked,
    }


def _git_action_result(command: str, stdout: str = "") -> dict[str, str]:
    return {
        "command": command,
        "summary": _clean_text(stdout, 500) or "Completed",
    }


def _git_diff_payload(repo: Path, repo_relative: str, file_path: str, *, staged: bool = False, untracked: bool = False) -> dict[str, Any]:
    target, relative = _resolve_repo_file(repo, file_path)
    if untracked:
        before = ""
        after = _read_repo_text(target)
        mode = "untracked"
        unified = _unified_diff(before, after, "/dev/null", f"b/{relative}")
    elif staged:
        before = _git_object_text(repo, f"HEAD:{relative}")
        after = _git_object_text(repo, f":{relative}")
        mode = "staged"
        unified = _run_git(repo, ["diff", "--cached", "--", relative], check=False)
    else:
        before = _git_object_text(repo, f":{relative}")
        after = _read_repo_text(target)
        mode = "working-tree"
        unified = _run_git(repo, ["diff", "--", relative], check=False)
    if len(unified.encode("utf-8", errors="replace")) > _MAX_DIFF_BYTES:
        raise HTTPException(status_code=413, detail="Diff is too large")
    return {
        "repo": _display_path(repo_relative),
        "path": relative,
        "mode": mode,
        "language": _language_for(relative),
        "before": before,
        "after": after,
        "diff": unified,
    }


@router.get("/status")
async def status() -> dict[str, Any]:
    access = _load_access()
    url = _clean_url(access.get("code_url") or access.get("code_local_url"))
    root = _workspace_root()
    vault_path = root / "ArcLink"
    vault_display_path = _workspace_display_path(vault_path)
    username = _clean_text(access.get("username") or access.get("unix_user"), 80)
    return {
        "plugin": "arclink-code",
        "label": "ArcLink Code",
        "version": "1.0.0",
        "status_contract": 1,
        "available": root.is_dir(),
        "url": url,
        "username": username,
        "workspace_root": str(root),
        "vault_path": str(vault_path),
        "vault_display_path": vault_display_path,
        "roots": [
            {"id": "workspace", "label": "Workspace", "path": "/", "available": root.is_dir()},
            {"id": "vault", "label": "Vault", "path": vault_display_path, "available": bool(vault_display_path and vault_path.exists())},
        ],
        "editor": "native",
        "full_ide_available": bool(url),
        "monaco_global_available": False,
        "capabilities": {
            "manual_save_only": True,
            "file_explorer": True,
            "nested_explorer": True,
            "file_operations": True,
            "search": True,
            "git_source_control": True,
            "repos": True,
            "git_pull_push": True,
            "gitignore": True,
            "light_theme": True,
        },
    }


@router.get("/repos")
async def repos() -> dict[str, Any]:
    root = _workspace_root()
    return {"workspace_root": str(root), "repos": _discover_repos(root)}


@router.post("/repos/open")
async def open_repo(request: Request) -> dict[str, Any]:
    payload = await request.json()
    root = _workspace_root()
    target, relative = _resolve_repo(payload.get("path") or "/")
    repo = _repo_item(root, target)
    return {"ok": True, "repo": repo, "status": _git_status_payload(target, relative)}


@router.get("/git/status")
async def git_status(repo: str = "/") -> dict[str, Any]:
    target, relative = _resolve_repo(repo)
    return _git_status_payload(target, relative)


@router.get("/git/diff")
async def git_diff(repo: str = "/", path: str = "", staged: bool = False, untracked: bool = False) -> dict[str, Any]:
    target, relative = _resolve_repo(repo)
    return _git_diff_payload(target, relative, path, staged=staged, untracked=untracked)


@router.post("/git/stage")
async def git_stage(request: Request) -> dict[str, Any]:
    payload = await request.json()
    repo, relative = _resolve_repo(payload.get("repo") or "/")
    if bool(payload.get("all")):
        _run_git(repo, ["add", "-A"])
    else:
        path = _clean_repo_file_path(payload.get("path"))
        _run_git(repo, ["add", "--", path])
    return {"ok": True, "status": _git_status_payload(repo, relative), "last_git_result": _git_action_result("stage")}


@router.post("/git/unstage")
async def git_unstage(request: Request) -> dict[str, Any]:
    payload = await request.json()
    repo, relative = _resolve_repo(payload.get("repo") or "/")
    if bool(payload.get("all")):
        _run_git(repo, ["restore", "--staged", "."])
    else:
        path = _clean_repo_file_path(payload.get("path"))
        _run_git(repo, ["restore", "--staged", "--", path])
    return {"ok": True, "status": _git_status_payload(repo, relative), "last_git_result": _git_action_result("unstage")}


@router.post("/git/discard")
async def git_discard(request: Request) -> dict[str, Any]:
    payload = await request.json()
    if payload.get("confirm") is not True:
        raise HTTPException(status_code=400, detail="Discard requires explicit confirmation")
    repo, relative = _resolve_repo(payload.get("repo") or "/")
    if bool(payload.get("all")):
        _run_git(repo, ["restore", "--staged", "."])
        _run_git(repo, ["restore", "."])
        _run_git(repo, ["clean", "-fd"])
    else:
        path = _clean_repo_file_path(payload.get("path"))
        if bool(payload.get("untracked")):
            _run_git(repo, ["clean", "-fd", "--", path])
        else:
            _run_git(repo, ["restore", "--", path])
    return {"ok": True, "status": _git_status_payload(repo, relative), "last_git_result": _git_action_result("discard")}


@router.post("/git/commit")
async def git_commit(request: Request) -> dict[str, Any]:
    payload = await request.json()
    repo, relative = _resolve_repo(payload.get("repo") or "/")
    message = _clean_text(payload.get("message"), 240)
    if not message:
        raise HTTPException(status_code=400, detail="Commit message is required")
    result = _run_git(repo, ["commit", "-m", message])
    return {"ok": True, "status": _git_status_payload(repo, relative), "last_git_result": _git_action_result("commit", result)}


@router.post("/git/ignore")
async def git_ignore(request: Request) -> dict[str, Any]:
    payload = await request.json()
    repo, relative = _resolve_repo(payload.get("repo") or "/")
    path = _clean_repo_file_path(payload.get("path"))
    gitignore = repo / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8", errors="replace").splitlines() if gitignore.exists() else []
    if path not in existing:
        lines = existing + [path]
        _write_text_atomic(gitignore, "\n".join(lines).rstrip("\n") + "\n")
    return {"ok": True, "status": _git_status_payload(repo, relative), "last_git_result": _git_action_result("gitignore", path)}


@router.post("/git/pull")
async def git_pull(request: Request) -> dict[str, Any]:
    payload = await request.json()
    if payload.get("confirm") is not True:
        raise HTTPException(status_code=400, detail="Pull requires explicit confirmation")
    repo, relative = _resolve_repo(payload.get("repo") or "/")
    result = _run_git(repo, ["pull", "--ff-only"])
    return {"ok": True, "status": _git_status_payload(repo, relative), "last_git_result": _git_action_result("pull --ff-only", result)}


@router.post("/git/push")
async def git_push(request: Request) -> dict[str, Any]:
    payload = await request.json()
    if payload.get("confirm") is not True:
        raise HTTPException(status_code=400, detail="Push requires explicit confirmation")
    repo, relative = _resolve_repo(payload.get("repo") or "/")
    result = _run_git(repo, ["push"])
    return {"ok": True, "status": _git_status_payload(repo, relative), "last_git_result": _git_action_result("push", result)}


@router.get("/items")
async def items(path: str = "/") -> dict[str, Any]:
    root = _workspace_root()
    target, relative = _resolve(path)
    if not root.is_dir():
        raise HTTPException(status_code=404, detail="ArcLink Code workspace is not available")
    if not target.exists():
        raise HTTPException(status_code=404, detail="Workspace path does not exist")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="Workspace path is not a folder")
    entries: list[dict[str, Any]] = []
    for child in sorted(target.iterdir(), key=_entry_sort_key):
        if child.name in _SKIP_DIR_NAMES or child.is_symlink():
            continue
        entries.append(_item_for(child, child.relative_to(root).as_posix()))
    return {"path": _display_path(relative), "items": entries}


@router.get("/tree")
async def tree(path: str = "/", depth: int = 3) -> dict[str, Any]:
    root = _workspace_root()
    target, relative = _resolve(path)
    if not root.is_dir():
        raise HTTPException(status_code=404, detail="ArcLink Code workspace is not available")
    if not target.exists():
        raise HTTPException(status_code=404, detail="Workspace path does not exist")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="Workspace path is not a folder")
    bounded_depth = max(0, min(int(depth), _MAX_TREE_DEPTH))
    return {"path": _display_path(relative), "depth": bounded_depth, "tree": _tree_for(target, relative, bounded_depth)}


@router.get("/search")
async def search(q: str = "", path: str = "/") -> dict[str, Any]:
    query = str(q or "").strip()
    if not query:
        return {"query": "", "results": []}
    root = _workspace_root()
    base, base_relative = _resolve(path)
    if not base.exists() or not base.is_dir():
        raise HTTPException(status_code=404, detail="Search path does not exist")
    lowered = query.lower()
    results: list[dict[str, Any]] = []
    for current_root, dirnames, filenames in os.walk(base):
        current = Path(current_root)
        try:
            current.relative_to(root)
        except ValueError:
            continue
        dirnames[:] = [
            name for name in dirnames
            if name not in _SKIP_DIR_NAMES and not (current / name).is_symlink()
        ]
        for name in filenames:
            if len(results) >= _MAX_SEARCH_RESULTS:
                break
            child = current / name
            if child.is_symlink() or not child.is_file():
                continue
            relative = child.relative_to(root).as_posix()
            haystack_path = relative.lower()
            matched_line = ""
            if lowered not in haystack_path:
                if child.stat().st_size > _MAX_SEARCH_FILE_BYTES or not _is_text_file(child):
                    continue
                try:
                    for line_no, line in enumerate(child.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
                        if lowered in line.lower():
                            matched_line = f"{line_no}: {_clean_text(line, 220)}"
                            break
                except OSError:
                    continue
                if not matched_line:
                    continue
            results.append(
                {
                    "name": child.name,
                    "path": _display_path(relative),
                    "kind": "file",
                    "language": _language_for(relative),
                    "match": matched_line or "Path match",
                }
            )
        if len(results) >= _MAX_SEARCH_RESULTS:
            break
    return {"query": query, "path": _display_path(base_relative), "results": results, "truncated": len(results) >= _MAX_SEARCH_RESULTS}


@router.get("/file")
async def file(path: str) -> dict[str, Any]:
    target, relative = _resolve(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Workspace file does not exist")
    if target.stat().st_size > _MAX_TEXT_BYTES or not _is_text_file(target):
        raise HTTPException(status_code=415, detail="This file is not editable here")
    return {
        "path": _display_path(relative),
        "name": target.name,
        "language": _language_for(relative),
        "content": target.read_text(encoding="utf-8", errors="replace"),
        "hash": _file_hash(target),
        "modified": _iso_from_timestamp(target.stat().st_mtime),
    }


@router.post("/save")
async def save(request: Request) -> dict[str, Any]:
    payload = await request.json()
    target, relative = _resolve(payload.get("path"))
    if target.exists() and not target.is_file():
        raise HTTPException(status_code=400, detail="Workspace path is not a file")
    expected_hash = str(payload.get("expected_hash") or payload.get("hash") or "").strip()
    if expected_hash and target.exists() and _file_hash(target) != expected_hash:
        raise HTTPException(status_code=409, detail="File changed on disk; reload before saving")
    content = str(payload.get("content") or "")
    _write_text_atomic(target, content)
    return {
        "ok": True,
        "path": _display_path(relative),
        "hash": _file_hash(target),
        "size": target.stat().st_size,
        "modified": _iso_from_timestamp(target.stat().st_mtime),
    }


@router.post("/mkdir")
async def mkdir(request: Request) -> dict[str, Any]:
    payload = await request.json()
    target, relative = _resolve(payload.get("path"))
    target.mkdir(parents=True, exist_ok=True)
    return {"ok": True, "path": _display_path(relative)}


@router.post("/ops/rename")
async def rename_item(request: Request) -> dict[str, Any]:
    payload = await request.json()
    source, _relative = _require_operable_path(payload.get("path"))
    name = _clean_leaf_name(payload.get("name"))
    destination_path = _display_path((source.parent / name).relative_to(_workspace_root()).as_posix())
    destination, destination_relative = _require_destination(destination_path)
    shutil.move(str(source), str(destination))
    return {"ok": True, "path": _display_path(destination_relative), "item": _item_for(destination, destination_relative)}


@router.post("/ops/move")
async def move_item(request: Request) -> dict[str, Any]:
    payload = await request.json()
    source, _source_relative = _require_operable_path(payload.get("path"))
    destination, destination_relative = _require_destination(payload.get("destination"))
    shutil.move(str(source), str(destination))
    return {"ok": True, "path": _display_path(destination_relative), "item": _item_for(destination, destination_relative)}


@router.post("/ops/duplicate")
async def duplicate_item(request: Request) -> dict[str, Any]:
    payload = await request.json()
    source, _source_relative = _require_operable_path(payload.get("path"))
    raw_destination = payload.get("destination")
    if raw_destination:
        destination, destination_relative = _require_destination(raw_destination)
    else:
        stem = source.stem
        suffix = source.suffix
        if source.is_dir():
            stem = source.name
            suffix = ""
        for index in range(1, 100):
            candidate_name = f"{stem} copy{'' if index == 1 else f' {index}'}{suffix}"
            candidate = source.parent / candidate_name
            if not candidate.exists():
                destination = candidate
                destination_relative = destination.relative_to(_workspace_root()).as_posix()
                break
        else:
            raise HTTPException(status_code=409, detail="Unable to find a duplicate name")
    _copy_confined(source, destination)
    return {"ok": True, "path": _display_path(destination_relative), "item": _item_for(destination, destination_relative)}


@router.post("/ops/trash")
async def trash_item(request: Request) -> dict[str, Any]:
    payload = await request.json()
    if payload.get("confirm") is not True:
        raise HTTPException(status_code=400, detail="Trash requires explicit confirmation")
    source, source_relative = _require_operable_path(payload.get("path"))
    entry_id = uuid.uuid4().hex
    destination = _trash_dir() / "files" / entry_id
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    index = _load_trash_index()
    index["entries"].append(
        {
            "id": entry_id,
            "name": source.name,
            "path": _display_path(source_relative),
            "kind": "folder" if destination.is_dir() else "file",
            "trashed_at": _iso_from_timestamp(time.time()),
        }
    )
    _save_trash_index(index)
    return {"ok": True, "trash_id": entry_id, **_trash_payload()}


@router.get("/trash")
async def trash() -> dict[str, Any]:
    return _trash_payload()


@router.post("/ops/restore")
async def restore_item(request: Request) -> dict[str, Any]:
    payload = await request.json()
    entry_id = str(payload.get("id") or "").strip()
    if not entry_id:
        raise HTTPException(status_code=400, detail="Trash id is required")
    index = _load_trash_index()
    entries = [entry for entry in index["entries"] if isinstance(entry, dict)]
    entry = next((item for item in entries if item.get("id") == entry_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="Trash item was not found")
    source = _trash_dir() / "files" / entry_id
    if not source.exists():
        raise HTTPException(status_code=404, detail="Trash payload was not found")
    destination, destination_relative = _require_destination(entry.get("path"))
    shutil.move(str(source), str(destination))
    index["entries"] = [item for item in entries if item.get("id") != entry_id]
    _save_trash_index(index)
    return {"ok": True, "path": _display_path(destination_relative), "item": _item_for(destination, destination_relative), **_trash_payload()}
