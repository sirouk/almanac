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
from typing import Any, Callable, Sequence

_PYTHON_DIR = Path(__file__).resolve().parent
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from almanac_control import (
    Config,
    config_env_value,
    connect_db,
    json_dumps,
    json_loads,
    note_refresh_job,
    queue_notification,
    utc_now_iso,
)
from almanac_http import http_request, parse_json_object


PROMPT_VERSION = "memory-synth-v1"
DEFAULT_MAX_SOURCES_PER_RUN = 12
DEFAULT_MAX_SOURCE_CHARS = 4500
DEFAULT_MAX_OUTPUT_TOKENS = 450
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_FAILURE_RETRY_SECONDS = 3600
DEFAULT_CARDS_IN_CONTEXT = 8
TEXT_SUFFIXES = {".md", ".markdown", ".mdx", ".txt", ".text"}
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
    endpoint = _resolve_chat_endpoint(_env("ALMANAC_MEMORY_SYNTH_ENDPOINT", "").strip() or _env("PDF_VISION_ENDPOINT", ""))
    model = (_env("ALMANAC_MEMORY_SYNTH_MODEL", "").strip() or _env("PDF_VISION_MODEL", "").strip())
    api_key = (_env("ALMANAC_MEMORY_SYNTH_API_KEY", "").strip() or _env("PDF_VISION_API_KEY", "").strip())
    enabled_raw = _env("ALMANAC_MEMORY_SYNTH_ENABLED", "auto").strip().lower()
    explicit_enabled = enabled_raw not in {"", "auto"}
    enabled = _boolish(enabled_raw) if explicit_enabled else bool(endpoint and model and api_key)
    state_dir = Path(_env("ALMANAC_MEMORY_SYNTH_STATE_DIR", str(cfg.state_dir / "memory-synth"))).expanduser()
    return SynthesisSettings(
        enabled=enabled,
        explicit_enabled=explicit_enabled,
        endpoint=endpoint,
        model=model,
        api_key=api_key,
        max_sources_per_run=_int_env("ALMANAC_MEMORY_SYNTH_MAX_SOURCES_PER_RUN", DEFAULT_MAX_SOURCES_PER_RUN, minimum=1, maximum=100),
        max_source_chars=_int_env("ALMANAC_MEMORY_SYNTH_MAX_SOURCE_CHARS", DEFAULT_MAX_SOURCE_CHARS, minimum=500, maximum=50_000),
        max_output_tokens=_int_env("ALMANAC_MEMORY_SYNTH_MAX_OUTPUT_TOKENS", DEFAULT_MAX_OUTPUT_TOKENS, minimum=100, maximum=4000),
        timeout_seconds=_int_env("ALMANAC_MEMORY_SYNTH_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS, minimum=5, maximum=600),
        failure_retry_seconds=_int_env(
            "ALMANAC_MEMORY_SYNTH_FAILURE_RETRY_SECONDS",
            DEFAULT_FAILURE_RETRY_SECONDS,
            minimum=60,
            maximum=86_400,
        ),
        cards_in_context=_int_env("ALMANAC_MEMORY_SYNTH_CARDS_IN_CONTEXT", DEFAULT_CARDS_IN_CONTEXT, minimum=1, maximum=30),
        state_dir=state_dir,
        status_file=Path(_env("ALMANAC_MEMORY_SYNTH_STATUS_FILE", str(state_dir / "status.json"))).expanduser(),
        lock_file=Path(_env("ALMANAC_MEMORY_SYNTH_LOCK_FILE", str(state_dir / "synth.lock"))).expanduser(),
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
        if not path.is_dir():
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
                    if dirname and not dirname.startswith(".") and dirname not in SKIP_DIR_NAMES
                ],
                key=str.casefold,
            )[:80]
            for filename in sorted(filenames, key=str.casefold):
                if len(result) >= limit:
                    return result
                if not filename or filename.startswith("."):
                    continue
                path = Path(current_root) / filename
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
        if not path.is_file() or path.stat().st_size > 2_000_000:
            return ""
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return _clean_space(raw, limit=max_chars)


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
    for child in _safe_iterdir(vault_root):
        if not child.name or child.name.startswith("."):
            continue
        if child.is_file() and child.suffix.casefold() in TEXT_SUFFIXES | {".pdf"}:
            stat = _safe_stat(child)
            root_files.append(
                {
                    "path": child.name,
                    "kind": "pdf" if child.suffix.casefold() == ".pdf" else "text",
                    "size": stat.st_size if stat else 0,
                    "mtime": int(stat.st_mtime) if stat else 0,
                    "snippet": _read_file_snippet(child, max_chars=600) if child.suffix.casefold() in TEXT_SUFFIXES else "",
                }
            )
            continue
        if not child.is_dir() or child.name in SKIP_DIR_NAMES:
            continue

        repo_inventory = _is_repo_inventory(child, folder_name=child.name)
        subfolders: list[str] = []
        repos: list[str] = []
        text_files: list[str] = []
        pdfs: list[str] = []
        snippets: list[dict[str, str]] = []
        fingerprints: list[str] = []
        nested_dirs = _safe_iterdir(child)
        for nested in nested_dirs[:250]:
            if not nested.name or nested.name.startswith(".") or nested.name in SKIP_DIR_NAMES:
                continue
            stat = _safe_stat(nested)
            if nested.is_dir():
                if repo_inventory or (nested / ".git").exists():
                    repos.append(nested.name)
                else:
                    subfolders.append(nested.name)
                    for grandchild in _safe_iterdir(nested)[:40]:
                        if grandchild.is_dir() and not grandchild.name.startswith(".") and grandchild.name not in SKIP_DIR_NAMES:
                            subfolders.append(f"{nested.name}/{grandchild.name}")
                fingerprints.append(f"d:{nested.name}:{int(stat.st_mtime) if stat else 0}")
                continue
            if not nested.is_file():
                continue
            suffix = nested.suffix.casefold()
            fingerprints.append(f"f:{nested.name}:{stat.st_size if stat else 0}:{int(stat.st_mtime) if stat else 0}")
            if suffix == ".pdf":
                pdfs.append(nested.name)
            elif suffix in TEXT_SUFFIXES:
                text_files.append(nested.name)

        preferred_snippet_files = [
            path
            for path in [child / ".vault", child / "README.md", child / "README.txt", child / "readme.md", child / "readme.txt"]
            if path.is_file()
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
            for path in _bounded_walk_files(child, suffixes=TEXT_SUFFIXES | {".pdf"}, limit=200):
                rel_path = _path_rel(path, child)
                stat = _safe_stat(path)
                fingerprints.append(f"deep:{rel_path}:{stat.st_size if stat else 0}:{int(stat.st_mtime) if stat else 0}")

        payload = {
            "source": "vault",
            "folder": child.name,
            "repo_inventory": repo_inventory,
            "repos": _compact_unique(repos, limit=30),
            "subfolders": _compact_unique(subfolders, limit=40),
            "text_files": _compact_unique(text_files, limit=30),
            "pdfs": _compact_unique(pdfs, limit=30),
            "snippets": snippets,
            "fingerprint": _compact_unique(fingerprints, limit=80, item_limit=220),
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
        }
        candidates.append(_candidate_from_payload("vault", "__root_files__", "Vault root files", payload, source_count=len(root_files)))

    candidates.sort(key=lambda item: (0 if item.source_title.casefold() in {"agents_kb", "projects", "research"} else 1, item.source_title.casefold()))
    return candidates


def _notion_area_from_row(row: sqlite3.Row) -> str:
    try:
        from almanac_control import _notion_landmark_area

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
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = Path(_env("ALMANAC_NOTION_INDEX_MARKDOWN_DIR", str(cfg.state_dir / "notion-index" / "markdown"))) / path
    try:
        path.resolve().relative_to(cfg.state_dir.resolve())
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
        for row in area_rows[:80]:
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
            fingerprints.append(
                ":".join(
                    [
                        str(row["doc_key"] or ""),
                        str(row["content_hash"] or ""),
                        str(row["indexed_at"] or ""),
                    ]
                )
            )
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
            "page_count": len(pages),
            "owners": _compact_unique(owners, limit=10),
            "pages": page_examples[:35],
            "snippets": snippets,
            "fingerprint": _compact_unique(fingerprints, limit=100, item_limit=240),
        }
        candidates.append(
            _candidate_from_payload(
                "notion",
                area,
                area,
                payload,
                source_count=len(pages),
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
    parts = _source_text_budget(
        [
            f"Source kind: {candidate.source_kind}",
            f"Source key: {candidate.source_key}",
            f"Source title: {candidate.source_title}",
            json.dumps(candidate.payload, ensure_ascii=False, sort_keys=True),
        ],
        settings.max_source_chars,
    )
    return "\n".join(parts)


def call_openai_compatible_model(candidate: SourceCandidate, settings: SynthesisSettings) -> dict[str, Any]:
    if not (settings.endpoint and settings.model and settings.api_key):
        raise RuntimeError("memory synthesis LLM is not configured")
    system_prompt = (
        "You compress private organizational knowledge into compact retrieval hints for AI agents. "
        "Return strict JSON only. Do not include secrets, credentials, or long excerpts. "
        "This card is an awareness hint, not evidence; phrase uncertain inferences conservatively."
    )
    user_prompt = (
        "Build one compact memory card from this bounded source inventory. "
        "Use the source names, folders, page titles, snippets, and PDFs as retrieval cues. "
        "If the source is too thin or mostly boilerplate, set inject=false.\n\n"
        "Required JSON shape:\n"
        '{"summary":"<=35 words","topics":["<=6"],"entities":["<=8"],'
        '"retrieval_queries":["<=5 concise searches"],"source_hints":["<=5 filenames/pages/folders"],'
        '"confidence":"low|medium|high","inject":true}\n\n'
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


def _normalize_card_payload(raw: dict[str, Any]) -> dict[str, Any]:
    confidence = str(raw.get("confidence") or "low").strip().lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = "low"
    return {
        "summary": _clean_space(raw.get("summary"), limit=260),
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
        "inject": bool(raw.get("inject", True)),
    }


def render_card_text(candidate: SourceCandidate, card: dict[str, Any]) -> str:
    if not card.get("inject") or not str(card.get("summary") or "").strip():
        return ""
    bits = [f"- [{candidate.source_kind}:{candidate.source_title}] {card['summary']}"]
    topics = ", ".join(card.get("topics") or [])
    entities = ", ".join(card.get("entities") or [])
    queries = "; ".join(card.get("retrieval_queries") or [])
    hints = ", ".join(card.get("source_hints") or [])
    if topics:
        bits.append(f"Topics: {topics}.")
    if entities:
        bits.append(f"Entities: {entities}.")
    if queries:
        bits.append(f"Search hints: {queries}.")
    if hints:
        bits.append(f"Sources to fetch: {hints}.")
    bits.append(f"Confidence: {card.get('confidence') or 'low'}.")
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
    model_client = model_client or call_openai_compatible_model

    with settings.lock_file.open("a", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        with connect_db(cfg) as conn:
            if not settings.enabled:
                note = (
                    "memory synthesis disabled until ALMANAC_MEMORY_SYNTH_* or PDF_VISION_* LLM config is present"
                    if not settings.explicit_enabled
                    else "memory synthesis disabled by ALMANAC_MEMORY_SYNTH_ENABLED"
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
