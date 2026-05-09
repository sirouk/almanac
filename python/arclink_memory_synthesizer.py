#!/usr/bin/env python3
from __future__ import annotations

import dataclasses
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

_PYTHON_DIR = Path(__file__).resolve().parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from arclink_control import (
    Config,
    config_env_value,
    connect_db,
    json_dumps,
    json_loads,
    note_refresh_job,
    queue_notification,
    utc_now_iso,
)
from arclink_http import http_request, parse_json_object


PROMPT_VERSION = "memory-synth-v3"
LOCAL_FALLBACK_MODEL = "local-non-llm-fallback"
DEFAULT_MAX_SOURCES_PER_RUN = 12
DEFAULT_MAX_SOURCE_CHARS = 4500
DEFAULT_MAX_OUTPUT_TOKENS = 450
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_FAILURE_RETRY_SECONDS = 3600
DEFAULT_CARDS_IN_CONTEXT = 8
TEXT_SUFFIXES = {".md", ".markdown", ".mdx", ".txt", ".text"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".tif", ".heic", ".svg"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".mpeg", ".mpg", ".wmv", ".flv"}
AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".aiff"}
OFFICE_SUFFIXES = {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".odt", ".ods", ".odp", ".rtf"}
DATA_SUFFIXES = {
    ".csv",
    ".tsv",
    ".json",
    ".jsonl",
    ".ndjson",
    ".yaml",
    ".yml",
    ".toml",
    ".xml",
    ".html",
    ".htm",
    ".ics",
    ".vcf",
    ".eml",
    ".msg",
    ".sql",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".parquet",
    ".ipynb",
}
DESIGN_SUFFIXES = {".fig", ".sketch", ".psd", ".ai", ".indd", ".xd", ".xcf"}
ARCHIVE_SUFFIXES = {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar"}
ASSET_SUFFIXES = (
    IMAGE_SUFFIXES | VIDEO_SUFFIXES | AUDIO_SUFFIXES | OFFICE_SUFFIXES | DATA_SUFFIXES | DESIGN_SUFFIXES | ARCHIVE_SUFFIXES
)
SIGNATURE_SUFFIXES = TEXT_SUFFIXES | {".pdf"} | ASSET_SUFFIXES
SKIP_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".cache",
    ".mypy_cache",
    ".pytest_cache",
    ".next",
    ".turbo",
}
SENSITIVE_PATTERN = re.compile(
    r"(?i)\b(token|api[_-]?key|password|passwd|secret|cookie|authorization|jwt|oauth)\b\s*[:=]\s*([^\s'\";,]+)"
)
URL_CREDENTIAL_PATTERN = re.compile(r"(?i)((?:https?|ssh)://[^/\s:]+:)([^@\s/]+)(@)")


@dataclasses.dataclass(frozen=True)
class SynthesisSettings:
    enabled: bool
    explicit_enabled: bool
    endpoint: str
    model: str
    api_key: str
    max_sources_per_run: int
    max_source_chars: int
    max_output_tokens: int
    timeout_seconds: int
    failure_retry_seconds: int
    cards_in_context: int
    state_dir: Path
    status_file: Path
    lock_file: Path


@dataclasses.dataclass(frozen=True)
class SourceCandidate:
    source_kind: str
    source_key: str
    source_title: str
    payload: dict[str, Any]
    source_count: int
    token_estimate: int

    @property
    def card_id(self) -> str:
        return _sha256(f"{self.source_kind}:{self.source_key}")[:32]

    @property
    def source_signature(self) -> str:
        return _sha256(json_dumps(self.payload))


ModelClient = Callable[[SourceCandidate, SynthesisSettings], dict[str, Any]]


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _env(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value is not None:
        return value
    return config_env_value(name, default)


def _boolish(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _int_env(name: str, default: int, *, minimum: int = 0, maximum: int = 1_000_000) -> int:
    try:
        value = int(str(_env(name, str(default))).strip())
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def _resolve_chat_endpoint(endpoint: str) -> str:
    normalized = str(endpoint or "").strip().rstrip("/")
    if not normalized:
        return ""
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/completions"):
        return normalized[: -len("/completions")] + "/chat/completions"
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return normalized


def load_settings(cfg: Config | None = None) -> SynthesisSettings:
    cfg = cfg or Config.from_env()
    endpoint = _resolve_chat_endpoint(_env("ARCLINK_MEMORY_SYNTH_ENDPOINT", "").strip() or _env("PDF_VISION_ENDPOINT", ""))
    model = (_env("ARCLINK_MEMORY_SYNTH_MODEL", "").strip() or _env("PDF_VISION_MODEL", "").strip())
    api_key = (_env("ARCLINK_MEMORY_SYNTH_API_KEY", "").strip() or _env("PDF_VISION_API_KEY", "").strip())
    enabled_raw = _env("ARCLINK_MEMORY_SYNTH_ENABLED", "auto").strip().lower()
    explicit_enabled = enabled_raw not in {"", "auto"}
    has_llm_config = bool(endpoint and model and api_key)
    enabled = _boolish(enabled_raw) if explicit_enabled else has_llm_config
    if enabled and not has_llm_config:
        model = LOCAL_FALLBACK_MODEL
    state_dir = Path(_env("ARCLINK_MEMORY_SYNTH_STATE_DIR", str(cfg.state_dir / "memory-synth"))).expanduser()
    return SynthesisSettings(
        enabled=enabled,
        explicit_enabled=explicit_enabled,
        endpoint=endpoint,
        model=model,
        api_key=api_key,
        max_sources_per_run=_int_env("ARCLINK_MEMORY_SYNTH_MAX_SOURCES_PER_RUN", DEFAULT_MAX_SOURCES_PER_RUN, minimum=1, maximum=100),
        max_source_chars=_int_env("ARCLINK_MEMORY_SYNTH_MAX_SOURCE_CHARS", DEFAULT_MAX_SOURCE_CHARS, minimum=500, maximum=50_000),
        max_output_tokens=_int_env("ARCLINK_MEMORY_SYNTH_MAX_OUTPUT_TOKENS", DEFAULT_MAX_OUTPUT_TOKENS, minimum=100, maximum=4000),
        timeout_seconds=_int_env("ARCLINK_MEMORY_SYNTH_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS, minimum=5, maximum=600),
        failure_retry_seconds=_int_env(
            "ARCLINK_MEMORY_SYNTH_FAILURE_RETRY_SECONDS",
            DEFAULT_FAILURE_RETRY_SECONDS,
            minimum=60,
            maximum=86_400,
        ),
        cards_in_context=_int_env("ARCLINK_MEMORY_SYNTH_CARDS_IN_CONTEXT", DEFAULT_CARDS_IN_CONTEXT, minimum=1, maximum=30),
        state_dir=state_dir,
        status_file=Path(_env("ARCLINK_MEMORY_SYNTH_STATUS_FILE", str(state_dir / "status.json"))).expanduser(),
        lock_file=Path(_env("ARCLINK_MEMORY_SYNTH_LOCK_FILE", str(state_dir / "synth.lock"))).expanduser(),
    )


def _clean_space(value: Any, *, limit: int = 300) -> str:
    text = " ".join(str(value or "").replace("\x00", " ").split())
    text = URL_CREDENTIAL_PATTERN.sub(r"\1[REDACTED]\3", text)
    text = SENSITIVE_PATTERN.sub(r"\1=[REDACTED]", text)
    return text[:limit].rstrip()


def _compact_unique(values: Sequence[Any], *, limit: int = 8, item_limit: int = 120) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean_space(value, limit=item_limit)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _safe_iterdir(path: Path) -> list[Path]:
    try:
        if path.is_symlink() or not path.is_dir():
            return []
        return sorted(path.iterdir(), key=lambda item: item.name.casefold())
    except OSError:
        return []


def _safe_stat(path: Path) -> os.stat_result | None:
    try:
        return path.stat()
    except OSError:
        return None


def _bounded_walk_files(root: Path, *, suffixes: set[str], limit: int = 800) -> list[Path]:
    result: list[Path] = []
    try:
        for current_root, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(
                [
                    dirname
                    for dirname in dirnames
                    if dirname
                    and not dirname.startswith(".")
                    and dirname not in SKIP_DIR_NAMES
                    and not (Path(current_root) / dirname).is_symlink()
                ],
                key=str.casefold,
            )[:80]
            for filename in sorted(filenames, key=str.casefold):
                if len(result) >= limit:
                    return result
                if not filename or filename.startswith("."):
                    continue
                path = Path(current_root) / filename
                if path.is_symlink():
                    continue
                if path.suffix.casefold() in suffixes:
                    result.append(path)
    except OSError:
        return result
    return result


def _path_rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _read_file_snippet(path: Path, *, max_chars: int) -> str:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 2_000_000:
            return ""
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return _clean_space(raw, limit=max_chars)


def _file_content_hash(path: Path) -> str:
    try:
        if path.is_symlink() or not path.is_file():
            return ""
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""


def _file_fingerprint(prefix: str, path: Path, root: Path, stat: os.stat_result | None = None) -> str:
    stat = stat or _safe_stat(path)
    rel_path = _path_rel(path, root)
    content_hash = _file_content_hash(path)
    return (
        f"{prefix}:{rel_path}:"
        f"{stat.st_size if stat else 0}:"
        f"{content_hash or 'unreadable'}"
    )


def _source_text_budget(parts: Sequence[str], max_chars: int) -> list[str]:
    result: list[str] = []
    used = 0
    for part in parts:
        text = _clean_space(part, limit=max_chars)
        if not text:
            continue
        remaining = max_chars - used
        if remaining <= 0:
            break
        result.append(text[:remaining])
        used += len(result[-1])
    return result


def _candidate_from_payload(
    source_kind: str,
    source_key: str,
    source_title: str,
    payload: dict[str, Any],
    *,
    source_count: int,
) -> SourceCandidate:
    serialized = json_dumps(payload)
    return SourceCandidate(
        source_kind=source_kind,
        source_key=source_key,
        source_title=source_title,
        payload=payload,
        source_count=source_count,
        token_estimate=max(1, len(serialized) // 4),
    )


def _pdf_sidecar_root(cfg: Config) -> Path:
    return Path(_env("PDF_INGEST_MARKDOWN_DIR", str(cfg.state_dir / "pdf-ingest" / "markdown"))).expanduser()


def _pdf_sidecar_snippets(cfg: Config, relative_top: str, *, limit: int, max_chars: int) -> list[dict[str, str]]:
    root = _pdf_sidecar_root(cfg)
    top = root / relative_top
    if not top.is_dir():
        return []
    snippets: list[dict[str, str]] = []
    for path in _bounded_walk_files(top, suffixes={".md"}, limit=400):
        snippet = _read_file_snippet(path, max_chars=max_chars)
        if not snippet:
            continue
        snippets.append({"path": _path_rel(path, root), "snippet": snippet})
        if len(snippets) >= limit:
            break
    return snippets


def _asset_kind_for_suffix(suffix: str) -> str:
    normalized = str(suffix or "").casefold()
    if normalized in IMAGE_SUFFIXES:
        return "image"
    if normalized in VIDEO_SUFFIXES:
        return "video"
    if normalized in AUDIO_SUFFIXES:
        return "audio"
    if normalized in OFFICE_SUFFIXES:
        return "office"
    if normalized in DATA_SUFFIXES:
        return "data"
    if normalized in DESIGN_SUFFIXES:
        return "design"
    if normalized in ARCHIVE_SUFFIXES:
        return "archive"
    if normalized == ".pdf":
        return "pdf"
    if normalized in TEXT_SUFFIXES:
        return "text"
    return "other"


def _asset_summary_for_path(path: Path, root: Path, *, max_rel_len: int = 180) -> dict[str, Any]:
    stat = _safe_stat(path)
    return {
        "path": _clean_space(_path_rel(path, root), limit=max_rel_len),
        "kind": _asset_kind_for_suffix(path.suffix),
        "size": stat.st_size if stat else 0,
        "mtime": int(stat.st_mtime) if stat else 0,
    }


def _payload_for_prompt(payload: dict[str, Any]) -> dict[str, Any]:
    prompt_payload = dict(payload)
    prompt_payload.pop("fingerprint_hash", None)
    fingerprint = prompt_payload.pop("fingerprint", [])
    fingerprint_count = prompt_payload.pop("fingerprint_count", None)
    if isinstance(fingerprint_count, int):
        prompt_payload["fingerprint_count"] = fingerprint_count
    elif isinstance(fingerprint, list):
        prompt_payload["fingerprint_count"] = len(fingerprint)
    asset_examples = prompt_payload.get("asset_examples")
    if isinstance(asset_examples, list):
        prompt_payload["asset_examples"] = [
            {
                "path": str(item.get("path") or ""),
                "kind": str(item.get("kind") or ""),
                "size": int(item.get("size") or 0),
            }
            for item in asset_examples
            if isinstance(item, dict)
        ][:24]
    root_files = prompt_payload.get("files")
    if isinstance(root_files, list):
        prompt_payload["files"] = [
            {
                key: value
                for key, value in {
                    "path": item.get("path"),
                    "kind": item.get("kind"),
                    "size": item.get("size"),
                    "snippet": item.get("snippet"),
                }.items()
                if value not in {"", None}
            }
            for item in root_files
            if isinstance(item, dict)
        ][:60]
    return prompt_payload


def _fingerprint_digest(fingerprints: Sequence[str]) -> dict[str, Any]:
    cleaned = [str(fingerprint or "") for fingerprint in fingerprints if str(fingerprint or "")]
    return {
        "fingerprint": _compact_unique(cleaned, limit=80, item_limit=220),
        "fingerprint_count": len(cleaned),
        "fingerprint_hash": _sha256(json_dumps(cleaned)),
    }


def _is_repo_inventory(child: Path, *, folder_name: str, category: str = "") -> bool:
    lowered = folder_name.casefold()
    if lowered in {"repos", "repositories", "source", "code"}:
        return True
    if category.casefold() in {"repo", "repos", "repository", "repositories", "repository-inventory", "code"}:
        return True
    if (child / ".git").exists():
        return True
    visible_dirs = [item for item in _safe_iterdir(child) if item.is_dir() and not item.name.startswith(".")]
    if not visible_dirs:
        return False
    repos = sum(1 for item in visible_dirs[:40] if (item / ".git").exists())
    return repos >= 3


def build_vault_candidates(cfg: Config, settings: SynthesisSettings) -> list[SourceCandidate]:
    vault_root = cfg.vault_dir
    if not vault_root.is_dir():
        return []
    candidates: list[SourceCandidate] = []
    root_files: list[dict[str, Any]] = []
    root_fingerprints: list[str] = []
    for child in _safe_iterdir(vault_root):
        if not child.name or child.name.startswith("."):
            continue
        if child.is_symlink():
            continue
        if child.is_file() and child.suffix.casefold() in SIGNATURE_SUFFIXES:
            stat = _safe_stat(child)
            root_fingerprints.append(_file_fingerprint("root", child, vault_root, stat))
            root_item = _asset_summary_for_path(child, vault_root, max_rel_len=140)
            root_item["snippet"] = _read_file_snippet(child, max_chars=600) if child.suffix.casefold() in TEXT_SUFFIXES else ""
            root_files.append(root_item)
            continue
        if not child.is_dir() or child.name in SKIP_DIR_NAMES:
            continue

        repo_inventory = _is_repo_inventory(child, folder_name=child.name)
        subfolders: list[str] = []
        repos: list[str] = []
        text_files: list[str] = []
        pdfs: list[str] = []
        asset_examples: list[dict[str, Any]] = []
        asset_counts: dict[str, int] = {}
        asset_seen: set[str] = set()
        snippets: list[dict[str, str]] = []
        fingerprints: list[str] = []
        nested_dirs = _safe_iterdir(child)
        for nested in nested_dirs[:250]:
            if not nested.name or nested.name.startswith(".") or nested.name in SKIP_DIR_NAMES or nested.is_symlink():
                continue
            stat = _safe_stat(nested)
            if nested.is_dir():
                if repo_inventory or (nested / ".git").exists():
                    repos.append(nested.name)
                else:
                    subfolders.append(nested.name)
                    for grandchild in _safe_iterdir(nested)[:40]:
                        if (
                            grandchild.is_dir()
                            and not grandchild.is_symlink()
                            and not grandchild.name.startswith(".")
                            and grandchild.name not in SKIP_DIR_NAMES
                        ):
                            subfolders.append(f"{nested.name}/{grandchild.name}")
                fingerprints.append(f"d:{nested.name}:{int(stat.st_mtime) if stat else 0}")
                continue
            if not nested.is_file():
                continue
            suffix = nested.suffix.casefold()
            fingerprints.append(_file_fingerprint("f", nested, child, stat))
            if suffix == ".pdf":
                pdfs.append(nested.name)
            elif suffix in TEXT_SUFFIXES:
                text_files.append(nested.name)
            if suffix in ASSET_SUFFIXES:
                kind = _asset_kind_for_suffix(suffix)
                rel_path = _path_rel(nested, child)
                if rel_path not in asset_seen:
                    asset_seen.add(rel_path)
                    asset_counts[kind] = asset_counts.get(kind, 0) + 1
                    if len(asset_examples) < 24:
                        asset_examples.append(_asset_summary_for_path(nested, child))

        preferred_snippet_files = [
            path
            for path in [child / ".vault", child / "README.md", child / "README.txt", child / "readme.md", child / "readme.txt"]
            if path.is_file() and not path.is_symlink()
        ]
        for path in preferred_snippet_files[:3]:
            snippet = _read_file_snippet(path, max_chars=min(900, settings.max_source_chars // 4))
            if snippet:
                snippets.append({"path": _path_rel(path, vault_root), "snippet": snippet})
        if not snippets and not repo_inventory:
            for path in _bounded_walk_files(child, suffixes=TEXT_SUFFIXES, limit=800):
                if len(snippets) >= 4:
                    break
                snippet = _read_file_snippet(path, max_chars=min(700, settings.max_source_chars // 4))
                if snippet:
                    snippets.append({"path": _path_rel(path, vault_root), "snippet": snippet})
        snippets.extend(
            _pdf_sidecar_snippets(
                cfg,
                child.name,
                limit=max(0, 4 - len(snippets)),
                max_chars=min(700, settings.max_source_chars // 4),
            )
        )
        snippets = snippets[:4]
        if not repo_inventory:
            for path in _bounded_walk_files(child, suffixes=SIGNATURE_SUFFIXES, limit=300):
                rel_path = _path_rel(path, child)
                stat = _safe_stat(path)
                suffix = path.suffix.casefold()
                fingerprints.append(_file_fingerprint("deep", path, child, stat))
                if suffix in ASSET_SUFFIXES:
                    kind = _asset_kind_for_suffix(suffix)
                    if rel_path not in asset_seen:
                        asset_seen.add(rel_path)
                        asset_counts[kind] = asset_counts.get(kind, 0) + 1
                        if len(asset_examples) < 24:
                            asset_examples.append(_asset_summary_for_path(path, child))

        payload = {
            "source": "vault",
            "folder": child.name,
            "repo_inventory": repo_inventory,
            "repos": _compact_unique(repos, limit=30),
            "subfolders": _compact_unique(subfolders, limit=40),
            "text_files": _compact_unique(text_files, limit=30),
            "pdfs": _compact_unique(pdfs, limit=30),
            "asset_counts": dict(sorted(asset_counts.items())),
            "asset_examples": asset_examples[:24],
            "snippets": snippets,
            **_fingerprint_digest(fingerprints),
        }
        candidates.append(
            _candidate_from_payload(
                "vault",
                child.name,
                child.name,
                payload,
                source_count=len(nested_dirs),
            )
        )

    if root_files:
        payload = {
            "source": "vault",
            "folder": "/",
            "files": root_files[:60],
            **_fingerprint_digest(root_fingerprints),
        }
        candidates.append(_candidate_from_payload("vault", "__root_files__", "Vault root files", payload, source_count=len(root_files)))

    candidates.sort(key=lambda item: (0 if item.source_title.casefold() in {"agents_kb", "projects", "research"} else 1, item.source_title.casefold()))
    return candidates


def _notion_area_from_row(row: sqlite3.Row) -> str:
    try:
        from arclink_control import _notion_landmark_area

        breadcrumb = json_loads(str(row["breadcrumb_json"] or "[]"), [])
        if not isinstance(breadcrumb, list):
            breadcrumb = []
        return _notion_landmark_area(breadcrumb, str(row["page_title"] or ""))
    except Exception:
        title = str(row["page_title"] or "").strip()
        return title[:120] if title else "Shared Notion"


def _safe_notion_markdown_path(cfg: Config, raw_path: str) -> Path | None:
    text = str(raw_path or "").strip()
    if not text:
        return None
    markdown_root = Path(_env("ARCLINK_NOTION_INDEX_MARKDOWN_DIR", str(cfg.state_dir / "notion-index" / "markdown"))).expanduser()
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = markdown_root / path
    try:
        path.resolve().relative_to(markdown_root.resolve())
    except (OSError, ValueError):
        return None
    return path


def build_notion_candidates(conn: sqlite3.Connection, cfg: Config, settings: SynthesisSettings) -> list[SourceCandidate]:
    try:
        rows = conn.execute(
            """
            SELECT doc_key, root_id, source_page_id, source_page_url, source_kind, file_path,
                   page_title, section_heading, section_ordinal, breadcrumb_json, owners_json,
                   last_edited_time, content_hash, indexed_at, state
            FROM notion_index_documents
            WHERE state = 'active'
            ORDER BY MAX(CASE WHEN last_edited_time != '' THEN last_edited_time ELSE indexed_at END, indexed_at) DESC
            LIMIT 600
            """
        ).fetchall()
    except sqlite3.Error:
        return []

    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        grouped.setdefault(_notion_area_from_row(row), []).append(row)

    candidates: list[SourceCandidate] = []
    for area, area_rows in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0].casefold())):
        pages: dict[str, dict[str, Any]] = {}
        snippets: list[dict[str, str]] = []
        fingerprints: list[str] = []
        owners: list[str] = []
        all_page_ids = {
            str(row["source_page_id"] or "").strip()
            for row in area_rows
            if str(row["source_page_id"] or "").strip()
        }
        for index, row in enumerate(area_rows):
            fingerprints.append(
                ":".join(
                    [
                        str(row["doc_key"] or ""),
                        str(row["content_hash"] or ""),
                        str(row["indexed_at"] or ""),
                    ]
                )
            )
            if index >= 80:
                continue
            page_id = str(row["source_page_id"] or "").strip()
            title = _clean_space(row["page_title"], limit=160) or page_id[:8]
            owners_payload = json_loads(str(row["owners_json"] or "[]"), [])
            if isinstance(owners_payload, list):
                owners.extend(str(owner) for owner in owners_payload)
            entry = pages.setdefault(
                page_id,
                {
                    "title": title,
                    "kind": str(row["source_kind"] or "page"),
                    "url": str(row["source_page_url"] or ""),
                    "sections": [],
                    "last_edited_time": str(row["last_edited_time"] or ""),
                },
            )
            heading = _clean_space(row["section_heading"], limit=120)
            if heading:
                entry["sections"].append(heading)
            if len(snippets) < 6:
                path = _safe_notion_markdown_path(cfg, str(row["file_path"] or ""))
                snippet = _read_file_snippet(path, max_chars=min(650, settings.max_source_chars // 4)) if path else ""
                if snippet:
                    snippets.append({"title": title, "section": heading, "snippet": snippet})

        page_examples = []
        for page in pages.values():
            page_examples.append(
                {
                    "title": page["title"],
                    "kind": page["kind"],
                    "sections": _compact_unique(page.get("sections") or [], limit=6),
                    "last_edited_time": page.get("last_edited_time") or "",
                }
            )
        payload = {
            "source": "notion",
            "area": area,
            "page_count": len(all_page_ids) or len(pages),
            "owners": _compact_unique(owners, limit=10),
            "pages": page_examples[:35],
            "snippets": snippets,
            **_fingerprint_digest(fingerprints),
        }
        candidates.append(
            _candidate_from_payload(
                "notion",
                area,
                area,
                payload,
                source_count=len(all_page_ids) or len(pages),
            )
        )
    return candidates


def build_candidates(conn: sqlite3.Connection, cfg: Config, settings: SynthesisSettings) -> list[SourceCandidate]:
    candidates = build_vault_candidates(cfg, settings)
    candidates.extend(build_notion_candidates(conn, cfg, settings))
    return candidates


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = str(text or "").strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        payload = json.loads(stripped)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        payload = json.loads(stripped[start : end + 1])
        if isinstance(payload, dict):
            return payload
    raise RuntimeError("model did not return a JSON object")


def _candidate_prompt(candidate: SourceCandidate, settings: SynthesisSettings) -> str:
    prompt_payload = _payload_for_prompt(candidate.payload)
    parts = _source_text_budget(
        [
            f"Source kind: {candidate.source_kind}",
            f"Source key: {candidate.source_key}",
            f"Source title: {candidate.source_title}",
            json.dumps(prompt_payload, ensure_ascii=False, sort_keys=True),
        ],
        settings.max_source_chars,
    )
    return "\n".join(parts)


def call_openai_compatible_model(candidate: SourceCandidate, settings: SynthesisSettings) -> dict[str, Any]:
    if not (settings.endpoint and settings.model and settings.api_key):
        raise RuntimeError("memory synthesis LLM is not configured")
    system_prompt = (
        "You compress private user and organization knowledge into compact retrieval hints for AI agents. "
        "Return strict JSON only. Do not include secrets, credentials, or long excerpts. "
        "This card is an awareness hint, not evidence; phrase uncertain inferences conservatively. "
        "The source may belong to a family, household, solo entrepreneur, creator, business, nonprofit, "
        "research group, school, club, Discord community, local team, or large organization."
    )
    user_prompt = (
        "Build one compact memory card from this bounded source inventory. "
        "Use source names, folders, page titles, snippets, PDFs, media/data asset inventories, and owners as retrieval cues. "
        "Prefer durable nouns and workflows over generic labels. "
        "Set trust_score from 0.0 to 1.0 based on source specificity and freshness. "
        "Only list contradiction_signals or disagreement_signals when the bounded source inventory explicitly shows conflicting facts, owners, dates, decisions, or positions. "
        "If the source is too thin or mostly boilerplate, set inject=false.\n\n"
        "Required JSON shape:\n"
        '{"summary":"<=35 words","domains":["<=5 e.g. family, creator, community, business"],'
        '"workflows":["<=6 recurring activities or jobs-to-be-done"],'
        '"content_types":["<=6 e.g. PDFs, videos, invoices, notes, runbooks"],'
        '"topics":["<=6"],"entities":["<=8"],'
        '"retrieval_queries":["<=5 concise searches"],"source_hints":["<=5 filenames/pages/folders/assets"],'
        '"confidence":"low|medium|high","trust_score":0.0,'
        '"contradiction_signals":["<=4 explicit conflicts"],"disagreement_signals":["<=4 explicit disagreements"],'
        '"inject":true}\n\n'
        + _candidate_prompt(candidate, settings)
    )
    response = http_request(
        settings.endpoint,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.api_key}",
            "Content-Type": "application/json",
        },
        json_payload={
            "model": settings.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": settings.max_output_tokens,
        },
        timeout=settings.timeout_seconds,
        allow_loopback_http=True,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"memory synthesis LLM returned HTTP {response.status_code}")
    payload = parse_json_object(response, label="memory synthesis LLM")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("memory synthesis LLM returned no choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else {}
    content = message.get("content") if isinstance(message, dict) else ""
    return _extract_json_object(str(content or ""))


KEYWORD_STOPWORDS = {
    "about",
    "after",
    "agent",
    "agents",
    "alpha",
    "and",
    "archive",
    "before",
    "current",
    "draft",
    "example",
    "file",
    "files",
    "for",
    "from",
    "into",
    "local",
    "note",
    "notes",
    "open",
    "page",
    "pages",
    "private",
    "shared",
    "source",
    "state",
    "status",
    "test",
    "the",
    "this",
    "user",
    "vault",
    "with",
    "work",
}


def _settings_has_llm_config(settings: SynthesisSettings) -> bool:
    return bool(settings.endpoint and settings.model and settings.api_key and settings.model != LOCAL_FALLBACK_MODEL)


def _payload_list(payload: Mapping[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    return value if isinstance(value, list) else []


def _phrase_candidates(values: Sequence[Any], *, limit: int = 8) -> list[str]:
    phrases: list[str] = []
    for value in values:
        text = _clean_space(value, limit=180)
        if not text:
            continue
        path_name = Path(text.split(":", 1)[0]).stem if "/" in text or "." in text else text
        cleaned = re.sub(r"[_\-.]+", " ", path_name)
        cleaned = re.sub(r"[^A-Za-z0-9 ]+", " ", cleaned)
        cleaned = " ".join(
            part
            for part in cleaned.split()
            if len(part) > 2 and part.casefold() not in KEYWORD_STOPWORDS and not part.isdigit()
        )
        if cleaned:
            phrases.append(cleaned[:80])
        if len(phrases) >= limit:
            break
    return _compact_unique(phrases, limit=limit, item_limit=80)


def _snippet_keywords(snippets: Sequence[Any], *, limit: int = 8) -> list[str]:
    values: list[str] = []
    for snippet in snippets:
        if isinstance(snippet, dict):
            values.extend(
                str(snippet.get(key) or "")
                for key in ("path", "title", "section", "snippet")
                if str(snippet.get(key) or "")
            )
        else:
            values.append(str(snippet or ""))
    tokens: list[str] = []
    for text in values:
        for match in re.finditer(r"\b[A-Za-z][A-Za-z0-9_-]{2,}\b", _clean_space(text, limit=600)):
            token = match.group(0).replace("_", " ").replace("-", " ")
            if token.casefold() in KEYWORD_STOPWORDS:
                continue
            tokens.append(token)
            if len(tokens) >= limit * 3:
                break
    return _compact_unique(tokens, limit=limit, item_limit=80)


def _infer_domains(candidate: SourceCandidate, payload: Mapping[str, Any], topics: Sequence[str]) -> list[str]:
    haystack = " ".join(
        [
            candidate.source_kind,
            candidate.source_title,
            json_dumps(payload.get("asset_counts") or {}),
            " ".join(topics),
            " ".join(str(item) for item in _payload_list(payload, "subfolders")),
        ]
    ).casefold()
    domains: list[str] = []
    rules = [
        ("research", ("research", "protocol", "paper", "study", "benchmark")),
        ("creator", ("creator", "episode", "studio", "content", "thumbnail", "video")),
        ("family", ("family", "school", "household", "calendar")),
        ("business", ("business", "trading", "market", "customer", "invoice", "operation")),
        ("code", ("repo", "repository", "source", "git", "code")),
        ("organization", ("notion", "ssot", "workspace", "owner")),
    ]
    for label, needles in rules:
        if any(needle in haystack for needle in needles):
            domains.append(label)
    if not domains:
        domains.append("workspace")
    return _compact_unique(domains, limit=5, item_limit=80)


def _local_fallback_content_types(payload: Mapping[str, Any]) -> list[str]:
    content: list[str] = []
    if payload.get("repo_inventory") or payload.get("repos"):
        content.append("repositories")
    if payload.get("text_files") or payload.get("files") or payload.get("snippets"):
        content.append("notes")
    if payload.get("pdfs"):
        content.append("PDFs")
    asset_counts = payload.get("asset_counts")
    if isinstance(asset_counts, dict):
        content.extend(str(kind) for kind, count in sorted(asset_counts.items()) if int(count or 0) > 0)
    if payload.get("pages"):
        content.append("Notion pages")
    if payload.get("owners"):
        content.append("ownership metadata")
    return _compact_unique(content or ["routing metadata"], limit=6, item_limit=80)


def _local_fallback_source_hints(payload: Mapping[str, Any]) -> list[str]:
    hints: list[str] = []
    for key in ("text_files", "pdfs", "repos", "subfolders"):
        hints.extend(str(value) for value in _payload_list(payload, key))
    for item in _payload_list(payload, "asset_examples"):
        if isinstance(item, dict):
            hints.append(str(item.get("path") or ""))
    for item in _payload_list(payload, "snippets"):
        if isinstance(item, dict):
            hints.append(str(item.get("path") or item.get("title") or ""))
    for item in _payload_list(payload, "pages"):
        if isinstance(item, dict):
            hints.append(str(item.get("title") or ""))
    return _compact_unique(hints, limit=5, item_limit=120)


def local_non_llm_fallback_model(candidate: SourceCandidate, settings: SynthesisSettings) -> dict[str, Any]:
    """Build low-fidelity retrieval hints from already bounded source metadata."""
    payload = _payload_for_prompt(candidate.payload)
    source_hints = _local_fallback_source_hints(payload)
    topic_values: list[Any] = [candidate.source_title, candidate.source_key]
    for key in ("repos", "subfolders", "text_files", "pdfs", "owners"):
        topic_values.extend(_payload_list(payload, key))
    for item in _payload_list(payload, "pages"):
        if isinstance(item, dict):
            topic_values.append(item.get("title"))
            topic_values.extend(item.get("sections") if isinstance(item.get("sections"), list) else [])
    for item in _payload_list(payload, "snippets"):
        if isinstance(item, dict):
            topic_values.append(item.get("path") or item.get("title"))
            topic_values.append(item.get("snippet"))
    topics = _compact_unique(
        [*_phrase_candidates(topic_values, limit=8), *_snippet_keywords(_payload_list(payload, "snippets"), limit=8)],
        limit=6,
        item_limit=80,
    )
    domains = _infer_domains(candidate, payload, topics)
    content_types = _local_fallback_content_types(payload)
    entities = _compact_unique(
        [candidate.source_title, *_payload_list(payload, "owners")],
        limit=8,
        item_limit=80,
    )
    workflows = _compact_unique(
        [
            "retrieval triage",
            "source review",
            "workspace orientation",
            "Notion review" if candidate.source_kind == "notion" else "",
            "repository inspection" if payload.get("repo_inventory") or payload.get("repos") else "",
        ],
        limit=6,
        item_limit=100,
    )
    query_seed = _compact_unique([candidate.source_title, *topics, *source_hints], limit=5, item_limit=120)
    source_count = max(1, int(candidate.source_count or payload.get("page_count") or payload.get("fingerprint_count") or 1))
    content_label = ", ".join(content_types[:3])
    summary = (
        f"Local fallback found {source_count} {candidate.source_kind} cue(s) for {candidate.source_title}; "
        f"use retrieval for {content_label or 'source metadata'}."
    )
    return {
        "summary": summary,
        "domains": domains,
        "workflows": workflows,
        "content_types": content_types,
        "topics": topics,
        "entities": entities,
        "retrieval_queries": query_seed,
        "source_hints": source_hints,
        "confidence": "low",
        "trust_score": 0.4,
        "contradiction_signals": [],
        "disagreement_signals": [],
        "inject": bool(source_hints or topics or content_types),
    }


def _normalize_trust_score(value: Any, *, confidence: str) -> float:
    fallback = {
        "low": 0.35,
        "medium": 0.65,
        "high": 0.85,
    }.get(confidence, 0.35)
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = fallback
    if score < 0:
        score = 0.0
    if score > 1:
        score = 1.0
    return round(score, 2)


def _normalize_card_payload(raw: dict[str, Any]) -> dict[str, Any]:
    confidence = str(raw.get("confidence") or "low").strip().lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = "low"
    trust_score = _normalize_trust_score(raw.get("trust_score"), confidence=confidence)
    return {
        "summary": _clean_space(raw.get("summary"), limit=260),
        "domains": _compact_unique(raw.get("domains") if isinstance(raw.get("domains"), list) else [], limit=5, item_limit=80),
        "workflows": _compact_unique(raw.get("workflows") if isinstance(raw.get("workflows"), list) else [], limit=6, item_limit=100),
        "content_types": _compact_unique(raw.get("content_types") if isinstance(raw.get("content_types"), list) else [], limit=6, item_limit=80),
        "topics": _compact_unique(raw.get("topics") if isinstance(raw.get("topics"), list) else [], limit=6, item_limit=80),
        "entities": _compact_unique(raw.get("entities") if isinstance(raw.get("entities"), list) else [], limit=8, item_limit=80),
        "retrieval_queries": _compact_unique(
            raw.get("retrieval_queries") if isinstance(raw.get("retrieval_queries"), list) else [],
            limit=5,
            item_limit=120,
        ),
        "source_hints": _compact_unique(
            raw.get("source_hints") if isinstance(raw.get("source_hints"), list) else [],
            limit=5,
            item_limit=120,
        ),
        "confidence": confidence,
        "trust_score": trust_score,
        "contradiction_signals": _compact_unique(
            raw.get("contradiction_signals") if isinstance(raw.get("contradiction_signals"), list) else [],
            limit=4,
            item_limit=140,
        ),
        "disagreement_signals": _compact_unique(
            raw.get("disagreement_signals") if isinstance(raw.get("disagreement_signals"), list) else [],
            limit=4,
            item_limit=140,
        ),
        "inject": bool(raw.get("inject", True)),
    }


def render_card_text(candidate: SourceCandidate, card: dict[str, Any]) -> str:
    if not card.get("inject") or not str(card.get("summary") or "").strip():
        return ""
    bits = [f"- [{candidate.source_kind}:{candidate.source_title}] {card['summary']}"]
    domains = ", ".join(card.get("domains") or [])
    workflows = ", ".join(card.get("workflows") or [])
    content_types = ", ".join(card.get("content_types") or [])
    topics = ", ".join(card.get("topics") or [])
    entities = ", ".join(card.get("entities") or [])
    queries = "; ".join(card.get("retrieval_queries") or [])
    hints = ", ".join(card.get("source_hints") or [])
    contradictions = "; ".join(card.get("contradiction_signals") or [])
    disagreements = "; ".join(card.get("disagreement_signals") or [])
    if domains:
        bits.append(f"Domains: {domains}.")
    if workflows:
        bits.append(f"Workflows: {workflows}.")
    if content_types:
        bits.append(f"Content: {content_types}.")
    if topics:
        bits.append(f"Topics: {topics}.")
    if entities:
        bits.append(f"Entities: {entities}.")
    if queries:
        bits.append(f"Search hints: {queries}.")
    if hints:
        bits.append(f"Sources to fetch: {hints}.")
    confidence = str(card.get("confidence") or "low").strip().lower()
    bits.append(f"Confidence: {confidence}.")
    bits.append(f"Trust score: {_normalize_trust_score(card.get('trust_score'), confidence=confidence):.2f}.")
    if contradictions:
        bits.append(f"Contradiction signals: {contradictions}.")
    if disagreements:
        bits.append(f"Disagreement signals: {disagreements}.")
    return " ".join(bits)


def _existing_cards(conn: sqlite3.Connection) -> dict[tuple[str, str], sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT *
        FROM memory_synthesis_cards
        """
    ).fetchall()
    return {(str(row["source_kind"] or ""), str(row["source_key"] or "")): row for row in rows}


def _should_retry_failed(row: sqlite3.Row, settings: SynthesisSettings) -> bool:
    updated_at = str(row["updated_at"] or "")
    if not updated_at:
        return True
    try:
        import datetime as dt

        parsed = dt.datetime.fromisoformat(updated_at)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        age = (dt.datetime.now(dt.timezone.utc) - parsed.astimezone(dt.timezone.utc)).total_seconds()
        return age >= settings.failure_retry_seconds
    except ValueError:
        return True


def _upsert_card(
    conn: sqlite3.Connection,
    candidate: SourceCandidate,
    settings: SynthesisSettings,
    *,
    status: str,
    card_json: dict[str, Any],
    card_text: str,
    last_error: str = "",
) -> bool:
    now = utc_now_iso()
    existing = conn.execute(
        """
        SELECT card_id, source_signature, prompt_version, model, status, card_json, card_text, last_error
        FROM memory_synthesis_cards
        WHERE source_kind = ? AND source_key = ?
        """,
        (candidate.source_kind, candidate.source_key),
    ).fetchone()
    existing_key = (
        str(existing["source_signature"] or "") if existing else "",
        str(existing["prompt_version"] or "") if existing else "",
        str(existing["model"] or "") if existing else "",
        str(existing["status"] or "") if existing else "",
        str(existing["card_json"] or "") if existing else "",
        str(existing["card_text"] or "") if existing else "",
        str(existing["last_error"] or "") if existing else "",
    )
    new_card_json = json_dumps(card_json)
    new_key = (
        candidate.source_signature,
        PROMPT_VERSION,
        settings.model,
        status,
        new_card_json,
        card_text,
        last_error,
    )
    if existing is not None and existing_key == new_key:
        return False
    conn.execute(
        """
        INSERT INTO memory_synthesis_cards (
          card_id, source_kind, source_key, source_title, source_signature,
          prompt_version, model, status, card_json, card_text, source_count,
          token_estimate, last_error, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_kind, source_key) DO UPDATE SET
          source_title = excluded.source_title,
          source_signature = excluded.source_signature,
          prompt_version = excluded.prompt_version,
          model = excluded.model,
          status = excluded.status,
          card_json = excluded.card_json,
          card_text = excluded.card_text,
          source_count = excluded.source_count,
          token_estimate = excluded.token_estimate,
          last_error = excluded.last_error,
          updated_at = excluded.updated_at
        """,
        (
            candidate.card_id,
            candidate.source_kind,
            candidate.source_key,
            candidate.source_title,
            candidate.source_signature,
            PROMPT_VERSION,
            settings.model,
            status,
            new_card_json,
            card_text,
            int(candidate.source_count),
            int(candidate.token_estimate),
            _clean_space(last_error, limit=500),
            now,
            now,
        ),
    )
    conn.commit()
    return True


def _mark_stale_cards(conn: sqlite3.Connection, active_keys: set[tuple[str, str]]) -> int:
    rows = conn.execute(
        """
        SELECT source_kind, source_key
        FROM memory_synthesis_cards
        WHERE status != 'stale'
          AND source_kind IN ('vault', 'notion')
        """
    ).fetchall()
    stale = [
        (str(row["source_kind"] or ""), str(row["source_key"] or ""))
        for row in rows
        if (str(row["source_kind"] or ""), str(row["source_key"] or "")) not in active_keys
    ]
    if not stale:
        return 0
    now = utc_now_iso()
    conn.executemany(
        """
        UPDATE memory_synthesis_cards
        SET status = 'stale', card_text = '', last_error = '', updated_at = ?
        WHERE source_kind = ? AND source_key = ?
        """,
        [(now, kind, key) for kind, key in stale],
    )
    conn.commit()
    return len(stale)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-memory-synth-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _write_status(settings: SynthesisSettings, payload: dict[str, Any]) -> None:
    safe_payload = {
        key: value
        for key, value in payload.items()
        if key not in {"api_key", "authorization", "token", "secret", "password"}
    }
    _atomic_write_json(settings.status_file, safe_payload)


def run_once(
    cfg: Config | None = None,
    *,
    model_client: ModelClient | None = None,
) -> dict[str, Any]:
    cfg = cfg or Config.from_env()
    settings = load_settings(cfg)
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    settings.lock_file.parent.mkdir(parents=True, exist_ok=True)
    model_client = model_client or (
        call_openai_compatible_model if _settings_has_llm_config(settings) else local_non_llm_fallback_model
    )

    with settings.lock_file.open("a", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        with connect_db(cfg) as conn:
            if not settings.enabled:
                note = (
                    "memory synthesis disabled until ARCLINK_MEMORY_SYNTH_* or PDF_VISION_* LLM config is present"
                    if not settings.explicit_enabled
                    else "memory synthesis disabled by ARCLINK_MEMORY_SYNTH_ENABLED"
                )
                note_refresh_job(
                    conn,
                    job_name="memory-synth",
                    job_kind="memory-synth",
                    target_id="global",
                    schedule="timer",
                    status="disabled",
                    note=note,
                )
                result = {
                    "status": "disabled",
                    "changed": 0,
                    "synthesized": 0,
                    "skipped": 0,
                    "failed": 0,
                    "stale": 0,
                    "note": note,
                    "finished_at": utc_now_iso(),
                }
                _write_status(settings, result)
                return result

            candidates = build_candidates(conn, cfg, settings)
            active_keys = {(candidate.source_kind, candidate.source_key) for candidate in candidates}
            stale_count = _mark_stale_cards(conn, active_keys)
            existing = _existing_cards(conn)
            to_process: list[SourceCandidate] = []
            skipped = 0
            for candidate in candidates:
                row = existing.get((candidate.source_kind, candidate.source_key))
                if (
                    row is not None
                    and str(row["status"] or "") == "ok"
                    and str(row["source_signature"] or "") == candidate.source_signature
                    and str(row["prompt_version"] or "") == PROMPT_VERSION
                    and str(row["model"] or "") == settings.model
                ):
                    skipped += 1
                    continue
                if row is not None and str(row["status"] or "") == "failed" and not _should_retry_failed(row, settings):
                    skipped += 1
                    continue
                to_process.append(candidate)
            to_process = sorted(to_process, key=lambda item: (-item.source_count, item.source_kind, item.source_key))[
                : settings.max_sources_per_run
            ]

            synthesized = 0
            failed = 0
            changed = stale_count
            errors: list[str] = []
            for candidate in to_process:
                try:
                    card_json = _normalize_card_payload(model_client(candidate, settings))
                    card_text = render_card_text(candidate, card_json)
                    if _upsert_card(
                        conn,
                        candidate,
                        settings,
                        status="ok",
                        card_json=card_json,
                        card_text=card_text,
                    ):
                        changed += 1
                    synthesized += 1
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    errors.append(f"{candidate.source_kind}:{candidate.source_key}: {_clean_space(exc, limit=160)}")
                    preserved_text = ""
                    preserved_json: dict[str, Any] = {}
                    previous = existing.get((candidate.source_kind, candidate.source_key))
                    if previous is not None and str(previous["card_text"] or ""):
                        preserved_text = str(previous["card_text"] or "")
                        preserved_json = json_loads(str(previous["card_json"] or "{}"), {})
                        if not isinstance(preserved_json, dict):
                            preserved_json = {}
                    if _upsert_card(
                        conn,
                        candidate,
                        settings,
                        status="failed",
                        card_json=preserved_json,
                        card_text=preserved_text,
                        last_error=str(exc),
                    ):
                        changed += 1

            if changed:
                queue_notification(
                    conn,
                    target_kind="curator",
                    target_id="curator",
                    channel_kind="brief-fanout",
                    message="Memory synthesis cards refreshed for managed context.",
                    extra={
                        "source": "memory-synth",
                        "changed_cards": changed,
                        "synthesized": synthesized,
                        "failed": failed,
                        "stale": stale_count,
                    },
                )

            status = "ok" if failed == 0 else "warn"
            note_refresh_job(
                conn,
                job_name="memory-synth",
                job_kind="memory-synth",
                target_id="global",
                schedule="timer",
                status=status,
                note=(
                    f"candidates={len(candidates)}; synthesized={synthesized}; skipped={skipped}; "
                    f"changed={changed}; stale={stale_count}; failed={failed}"
                ),
            )
            result = {
                "status": status,
                "changed": changed,
                "synthesized": synthesized,
                "skipped": skipped,
                "failed": failed,
                "stale": stale_count,
                "candidate_count": len(candidates),
                "model": settings.model,
                "prompt_version": PROMPT_VERSION,
                "errors": errors[:8],
                "finished_at": utc_now_iso(),
            }
            _write_status(settings, result)
            return result


def main() -> int:
    result = run_once()
    print(json.dumps(result, sort_keys=True))
    return 1 if result.get("status") == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
