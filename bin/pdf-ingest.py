#!/usr/bin/env python3
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from almanac_http import http_request, parse_json_object


VAULT_DIR = Path(os.environ["VAULT_DIR"]).resolve()
MARKDOWN_DIR = Path(os.environ["PDF_INGEST_MARKDOWN_DIR"]).resolve()
MANIFEST_DB = Path(os.environ["PDF_INGEST_MANIFEST_DB"]).resolve()
STATUS_FILE = Path(os.environ["PDF_INGEST_STATUS_FILE"]).resolve()
REQUESTED_EXTRACTOR = os.environ.get("PDF_INGEST_EXTRACTOR", "auto")
NEXTCLOUD_VAULT_MOUNT_POINT = os.environ.get("NEXTCLOUD_VAULT_MOUNT_POINT", "/Vault")
FORCE_DOCLING_OCR = os.environ.get("PDF_INGEST_DOCLING_FORCE_OCR", "0") == "1"
PDF_VISION_ENDPOINT_RAW = os.environ.get("PDF_VISION_ENDPOINT", "").strip()
PDF_VISION_MODEL = os.environ.get("PDF_VISION_MODEL", "").strip()
PDF_VISION_API_KEY = os.environ.get("PDF_VISION_API_KEY", "").strip()

try:
    PDF_VISION_MAX_PAGES = max(0, int(os.environ.get("PDF_VISION_MAX_PAGES", "6")))
except ValueError:
    PDF_VISION_MAX_PAGES = 6

VISION_TIMEOUT_SECONDS = 90
VISION_MAX_TOKENS = 350
# Deliberately limited to filesystem/locale context for local extraction tools.
# Do not add API keys or deployment secrets here.
SAFE_TOOL_ENV_KEYS = ("HOME", "PATH", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TMPDIR")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def yaml_quote(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_backend() -> str:
    if REQUESTED_EXTRACTOR in {"none", "disabled"}:
        return "disabled"

    if REQUESTED_EXTRACTOR == "auto":
        for candidate in ("docling", "pdftotext"):
            if shutil.which(candidate):
                return candidate
        raise RuntimeError("no PDF extractor available; looked for docling and pdftotext")

    if shutil.which(REQUESTED_EXTRACTOR):
        return REQUESTED_EXTRACTOR

    raise RuntimeError(f"requested PDF extractor '{REQUESTED_EXTRACTOR}' is not installed")


def resolve_vision_endpoint(endpoint: str) -> str:
    normalized = endpoint.strip().rstrip("/")
    if not normalized:
        return ""
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/completions"):
        return normalized[: -len("/completions")] + "/chat/completions"
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return normalized


PDF_VISION_ENDPOINT = resolve_vision_endpoint(PDF_VISION_ENDPOINT_RAW)


def vision_enabled() -> bool:
    return bool(PDF_VISION_ENDPOINT and PDF_VISION_MODEL and PDF_VISION_API_KEY and PDF_VISION_MAX_PAGES > 0)


def source_rel_path(source_path: Path) -> str:
    return source_path.relative_to(VAULT_DIR).as_posix()


def generated_markdown_path(relative_source_path: str) -> Path:
    rel = PurePosixPath(relative_source_path)
    parts = list(rel.parts)
    filename = f"{PurePosixPath(parts[-1]).stem}-pdf.md"
    return MARKDOWN_DIR.joinpath(*parts[:-1], filename)


def legacy_generated_markdown_path(relative_source_path: str) -> Path:
    rel = PurePosixPath(relative_source_path)
    parts = list(rel.parts)
    filename = parts[-1] + ".md"
    return MARKDOWN_DIR.joinpath(*parts[:-1], filename)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def prune_empty_parents(path: Path, stop_at: Path) -> None:
    current = path.parent
    while current != stop_at and current.exists():
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def tool_subprocess_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for key in SAFE_TOOL_ENV_KEYS:
        value = os.environ.get(key)
        if value:
            env[key] = value
    return env


def extract_with_pdftotext(source_path: Path) -> str:
    result = subprocess.run(
        ["pdftotext", "-enc", "UTF-8", "-nopgbrk", str(source_path), "-"],
        env=tool_subprocess_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        error = (result.stderr or result.stdout or "pdftotext failed").strip()
        raise RuntimeError(error)

    text = (result.stdout or "").strip()
    if not text:
        raise RuntimeError("pdftotext extracted no text")

    return text


def extract_with_docling(source_path: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="almanac-docling-") as tmpdir:
        command = ["docling", "--from", "pdf", "--to", "md", "--output", tmpdir]
        if FORCE_DOCLING_OCR:
            command.append("--force-ocr")
        command.append(str(source_path))
        result = subprocess.run(
            command,
            env=tool_subprocess_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            error = (result.stderr or result.stdout or "docling failed").strip()
            raise RuntimeError(error)

        markdown_files = sorted(Path(tmpdir).rglob("*.md"))
        if not markdown_files:
            raise RuntimeError("docling did not produce a markdown file")

        text = markdown_files[0].read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            raise RuntimeError("docling produced an empty markdown file")

        return text


def extract_markdown(source_path: Path, backend: str) -> str:
    if backend == "docling":
        return extract_with_docling(source_path)
    if backend == "pdftotext":
        return extract_with_pdftotext(source_path)
    raise RuntimeError(f"unsupported extractor backend '{backend}'")


def extract_text_body(source_path: Path, backend: str) -> tuple[str, str | None]:
    try:
        return extract_markdown(source_path, backend), None
    except Exception as exc:  # noqa: BLE001
        return "", str(exc)


def build_pipeline_signature(backend: str) -> str:
    parts = [
        f"extractor={backend}",
        f"docling_force_ocr={int(FORCE_DOCLING_OCR)}",
        f"vision={int(vision_enabled())}",
    ]
    if vision_enabled():
        parts.extend(
            [
                f"vision_endpoint={PDF_VISION_ENDPOINT}",
                f"vision_model={PDF_VISION_MODEL}",
                f"vision_max_pages={PDF_VISION_MAX_PAGES}",
            ]
        )
    return "|".join(parts)


def extract_chat_message_text(payload: dict) -> str:
    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError("vision response did not include choices")

    message = (choices[0] or {}).get("message") or {}
    content = message.get("content")

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
            elif "text" in item:
                parts.append(str(item["text"]))
        return "\n".join(part.strip() for part in parts if part and part.strip()).strip()

    raise RuntimeError("vision response did not include textual message content")


def normalize_caption_text(text: str) -> str:
    normalized = text.strip()
    if not normalized:
        return ""
    if normalized.upper() == "NONE":
        return ""
    return normalized


def call_vision_model(page_number: int, image_path: Path) -> str:
    image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    payload = {
        "model": PDF_VISION_MODEL,
        "temperature": 0,
        "max_tokens": VISION_MAX_TOKENS,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You extract concise retrieval-oriented visual notes from PDF page images. "
                    "Focus on diagrams, charts, tables, architecture drawings, screenshots, equations, "
                    "figure captions, labels, and spatial relationships that OCR or markdown conversion may miss. "
                    "Return plain markdown bullet points or short paragraphs. "
                    "If the page contains no meaningful visual-only information beyond ordinary prose text, reply with NONE."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Summarize only the visual information from PDF page {page_number}. "
                            "Do not restate ordinary body text unless it is required to identify a figure or chart."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_b64}",
                        },
                    },
                ],
            },
        ],
    }

    response = http_request(
        PDF_VISION_ENDPOINT,
        method="POST",
        headers={
            "Authorization": f"Bearer {PDF_VISION_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json_payload=payload,
        timeout=VISION_TIMEOUT_SECONDS,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"vision endpoint returned HTTP {response.status_code}: {response.text[:400].strip()}")
    data = parse_json_object(response, label="vision endpoint")
    return normalize_caption_text(extract_chat_message_text(data))


def page_number_from_image(path: Path) -> int:
    stem = path.stem
    if "-" in stem:
        maybe_number = stem.rsplit("-", 1)[-1]
        if maybe_number.isdigit():
            return int(maybe_number)
    return 0


def generate_visual_notes(source_path: Path) -> tuple[list[tuple[int, str]], dict]:
    stats = {
        "rendered": 0,
        "captioned": 0,
        "failed": 0,
        "failures": [],
    }

    if not vision_enabled():
        return [], stats

    if shutil.which("pdftoppm") is None:
        raise RuntimeError("pdftoppm is required for PDF vision captions")

    with tempfile.TemporaryDirectory(prefix="almanac-pdf-vision-") as tmpdir:
        prefix = Path(tmpdir) / "page"
        result = subprocess.run(
            [
                "pdftoppm",
                "-png",
                "-f",
                "1",
                "-l",
                str(PDF_VISION_MAX_PAGES),
                str(source_path),
                str(prefix),
            ],
            env=tool_subprocess_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            error = (result.stderr or result.stdout or "pdftoppm failed").strip()
            raise RuntimeError(error)

        images = sorted(
            Path(tmpdir).glob("page-*.png"),
            key=page_number_from_image,
        )
        if not images:
            raise RuntimeError("pdftoppm did not render any page images")

        stats["rendered"] = len(images)
        notes: list[tuple[int, str]] = []

        for image_path in images:
            page_number = page_number_from_image(image_path)
            try:
                caption = call_vision_model(page_number, image_path)
            except Exception as exc:  # noqa: BLE001
                stats["failed"] += 1
                stats["failures"].append({"page": page_number, "error": str(exc)})
                continue

            if caption:
                notes.append((page_number, caption))
                stats["captioned"] += 1

        return notes, stats


def render_markdown(
    relative_source_path: str,
    source_path: Path,
    sha256: str,
    size: int,
    mtime: int,
    backend: str,
    extracted_body: str,
    text_error: str | None,
    visual_notes: list[tuple[int, str]],
    vision_stats: dict,
    pipeline_signature: str,
) -> str:
    source_vault_path = f"{NEXTCLOUD_VAULT_MOUNT_POINT.rstrip('/')}/{relative_source_path}"
    source_almanac_path = f"~/Almanac/{relative_source_path}"
    frontmatter = [
        "---",
        "almanac_generated: true",
        "almanac_source_type: pdf",
        f"source_vault_path: {yaml_quote(source_vault_path)}",
        f"source_almanac_path: {yaml_quote(source_almanac_path)}",
        f"source_rel_path: {yaml_quote(relative_source_path)}",
        f"source_sha256: {yaml_quote(sha256)}",
        f"source_size_bytes: {size}",
        f"source_mtime_epoch: {mtime}",
        f"extractor: {yaml_quote(backend)}",
        f"generated_at: {yaml_quote(utc_now())}",
        f"pipeline_signature: {yaml_quote(pipeline_signature)}",
        f"vision_captions_enabled: {'true' if vision_enabled() else 'false'}",
        f"vision_captions_present: {'true' if visual_notes else 'false'}",
        f"vision_model: {yaml_quote(PDF_VISION_MODEL if vision_enabled() else '')}",
        f"vision_pages_rendered: {int(vision_stats.get('rendered', 0))}",
        f"vision_pages_captioned: {int(vision_stats.get('captioned', 0))}",
        f"vision_pages_failed: {int(vision_stats.get('failed', 0))}",
        "---",
        "",
    ]

    body_parts: list[str] = []

    if backend == "pdftotext":
        title = PurePosixPath(relative_source_path).name
        body_parts.extend([f"# {title}", "", "## Extracted Text", ""])
        if extracted_body.strip():
            body_parts.extend([extracted_body.strip(), ""])
        else:
            placeholder = "_No machine-readable text layer was extracted from this PDF._"
            if text_error:
                placeholder = f"{placeholder}\n\n_Text extraction note: {text_error}_"
            body_parts.extend([placeholder, ""])
    else:
        if extracted_body.strip():
            body_parts.extend([extracted_body.strip(), ""])
        else:
            title = PurePosixPath(relative_source_path).name
            body_parts.extend([f"# {title}", "", "_No markdown text was extracted from this PDF._", ""])

    if visual_notes:
        body_parts.extend(["## Visual Notes", ""])
        for page_number, caption in visual_notes:
            label = f"### Page {page_number}" if page_number else "### Visual Summary"
            body_parts.extend([label, "", caption.strip(), ""])

    return "\n".join(frontmatter + body_parts).rstrip() + "\n"


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pdf_ingest_manifest (
            source_rel_path TEXT PRIMARY KEY,
            source_abs_path TEXT NOT NULL,
            generated_abs_path TEXT NOT NULL,
            source_sha256 TEXT,
            source_size INTEGER NOT NULL,
            source_mtime INTEGER NOT NULL,
            extractor TEXT,
            pipeline_signature TEXT,
            status TEXT NOT NULL,
            error TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )

    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(pdf_ingest_manifest)").fetchall()
    }
    if "pipeline_signature" not in columns:
        conn.execute("ALTER TABLE pdf_ingest_manifest ADD COLUMN pipeline_signature TEXT")


def open_manifest() -> sqlite3.Connection:
    ensure_parent(MANIFEST_DB)
    conn = sqlite3.connect(MANIFEST_DB)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn


def list_pdf_sources() -> list[Path]:
    if not VAULT_DIR.exists():
        return []

    pdfs = []
    vault_root = VAULT_DIR.resolve()
    for path in VAULT_DIR.rglob("*"):
        if path.is_symlink() or path.suffix.lower() != ".pdf":
            continue
        try:
            resolved = path.resolve(strict=True)
        except OSError:
            continue
        if not path.is_file():
            continue
        try:
            if os.path.commonpath([str(resolved), str(vault_root)]) != str(vault_root):
                continue
        except ValueError:
            continue
        pdfs.append(path)
    return sorted(pdfs)


def remove_generated_artifacts(path: Path) -> None:
    if path.exists():
        path.unlink()
        prune_empty_parents(path, MARKDOWN_DIR)


def promote_generated_artifact(relative_source_path: str, canonical_path: Path, manifest_generated_path: str | None) -> bool:
    """Move/delete legacy PDF sidecars so the filesystem matches the canonical
    `-pdf.md` naming qmd already exposes in display paths."""
    changed = False
    candidates: list[Path] = []

    if manifest_generated_path:
        candidates.append(Path(manifest_generated_path))
    candidates.append(legacy_generated_markdown_path(relative_source_path))

    seen: set[str] = set()
    for candidate in candidates:
        candidate_key = str(candidate)
        if candidate_key in seen:
            continue
        seen.add(candidate_key)

        if candidate == canonical_path or not candidate.exists():
            continue

        if canonical_path.exists():
            remove_generated_artifacts(candidate)
            changed = True
            continue

        ensure_parent(canonical_path)
        candidate.replace(canonical_path)
        prune_empty_parents(candidate, MARKDOWN_DIR)
        changed = True

    return changed


def write_status_file(summary: dict) -> None:
    ensure_parent(STATUS_FILE)
    STATUS_FILE.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def merge_vision_stats(summary: dict, relative_path: str, stats: dict) -> None:
    summary["vision_pages_rendered"] += int(stats.get("rendered", 0))
    summary["vision_pages_captioned"] += int(stats.get("captioned", 0))
    summary["vision_pages_failed"] += int(stats.get("failed", 0))
    for failure in stats.get("failures", []):
        record = {"path": relative_path}
        record.update(failure)
        summary["vision_failures"].append(record)


def main() -> int:
    backend = resolve_backend()
    conn = open_manifest()
    pipeline_signature = build_pipeline_signature(backend)
    summary = {
        "last_run_at": utc_now(),
        "backend": backend,
        "vault_dir": str(VAULT_DIR),
        "markdown_dir": str(MARKDOWN_DIR),
        "total_pdfs": 0,
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "removed": 0,
        "failed": 0,
        "qmd_refresh_needed": False,
        "failed_documents": [],
        "removed_documents": [],
        "changed_documents": [],
        "vision_enabled": vision_enabled(),
        "vision_model": PDF_VISION_MODEL if vision_enabled() else "",
        "vision_max_pages": PDF_VISION_MAX_PAGES if vision_enabled() else 0,
        "vision_pages_rendered": 0,
        "vision_pages_captioned": 0,
        "vision_pages_failed": 0,
        "vision_failures": [],
    }

    if backend == "disabled":
        write_status_file(summary)
        print(json.dumps(summary))
        return 0

    sources = list_pdf_sources()
    summary["total_pdfs"] = len(sources)
    seen_rel_paths: set[str] = set()

    for source in sources:
        relative_path = source_rel_path(source)
        seen_rel_paths.add(relative_path)
        generated_path = generated_markdown_path(relative_path)
        legacy_path = legacy_generated_markdown_path(relative_path)
        stat = source.stat()
        source_size = int(stat.st_size)
        source_mtime = int(stat.st_mtime)

        row = conn.execute(
            """
            SELECT source_sha256, source_size, source_mtime, pipeline_signature, status, generated_abs_path
              FROM pdf_ingest_manifest
             WHERE source_rel_path = ?
            """,
            (relative_path,),
        ).fetchone()
        manifest_generated_path = str(row["generated_abs_path"]) if row and row["generated_abs_path"] else None

        if (
            row is not None
            and row["source_size"] == source_size
            and row["source_mtime"] == source_mtime
            and row["pipeline_signature"] == pipeline_signature
            and row["status"] == "ok"
            and (
                Path(row["generated_abs_path"]).exists()
                or generated_path.exists()
                or legacy_path.exists()
            )
        ):
            artifact_changed = promote_generated_artifact(relative_path, generated_path, manifest_generated_path)
            conn.execute(
                """
                UPDATE pdf_ingest_manifest
                   SET source_abs_path = ?,
                       generated_abs_path = ?,
                       source_size = ?,
                       source_mtime = ?,
                       updated_at = ?,
                       error = NULL
                 WHERE source_rel_path = ?
                """,
                (str(source), str(generated_path), source_size, source_mtime, utc_now(), relative_path),
            )
            summary["unchanged"] += 1
            if artifact_changed:
                summary["unchanged"] -= 1
                summary["updated"] += 1
                summary["changed_documents"].append(relative_path)
            continue

        sha256 = file_sha256(source)
        if (
            row is not None
            and row["source_sha256"] == sha256
            and row["pipeline_signature"] == pipeline_signature
            and row["status"] == "ok"
            and (
                Path(row["generated_abs_path"]).exists()
                or generated_path.exists()
                or legacy_path.exists()
            )
        ):
            artifact_changed = promote_generated_artifact(relative_path, generated_path, manifest_generated_path)
            conn.execute(
                """
                UPDATE pdf_ingest_manifest
                   SET source_abs_path = ?,
                       generated_abs_path = ?,
                       source_size = ?,
                       source_mtime = ?,
                       updated_at = ?,
                       error = NULL
                 WHERE source_rel_path = ?
                """,
                (str(source), str(generated_path), source_size, source_mtime, utc_now(), relative_path),
            )
            if artifact_changed:
                summary["updated"] += 1
                summary["changed_documents"].append(relative_path)
            else:
                summary["unchanged"] += 1
            continue

        try:
            extracted_body, text_error = extract_text_body(source, backend)
            visual_notes: list[tuple[int, str]] = []
            vision_stats = {"rendered": 0, "captioned": 0, "failed": 0, "failures": []}

            if vision_enabled():
                try:
                    visual_notes, vision_stats = generate_visual_notes(source)
                except Exception as exc:  # noqa: BLE001
                    vision_stats = {
                        "rendered": 0,
                        "captioned": 0,
                        "failed": 1,
                        "failures": [{"error": str(exc)}],
                    }

            merge_vision_stats(summary, relative_path, vision_stats)

            if not extracted_body.strip() and not visual_notes:
                if text_error:
                    raise RuntimeError(text_error)
                raise RuntimeError("no text or visual notes were extracted from this PDF")

            rendered_markdown = render_markdown(
                relative_path,
                source,
                sha256,
                source_size,
                source_mtime,
                backend,
                extracted_body,
                text_error,
                visual_notes,
                vision_stats,
                pipeline_signature,
            )
            ensure_parent(generated_path)
            generated_path.write_text(rendered_markdown, encoding="utf-8")
            for obsolete_path in {legacy_path, Path(manifest_generated_path) if manifest_generated_path else None}:
                if obsolete_path is None or obsolete_path == generated_path:
                    continue
                remove_generated_artifacts(obsolete_path)
            conn.execute(
                """
                INSERT INTO pdf_ingest_manifest (
                    source_rel_path,
                    source_abs_path,
                    generated_abs_path,
                    source_sha256,
                    source_size,
                    source_mtime,
                    extractor,
                    pipeline_signature,
                    status,
                    error,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ok', NULL, ?)
                ON CONFLICT(source_rel_path) DO UPDATE SET
                    source_abs_path = excluded.source_abs_path,
                    generated_abs_path = excluded.generated_abs_path,
                    source_sha256 = excluded.source_sha256,
                    source_size = excluded.source_size,
                    source_mtime = excluded.source_mtime,
                    extractor = excluded.extractor,
                    pipeline_signature = excluded.pipeline_signature,
                    status = 'ok',
                    error = NULL,
                    updated_at = excluded.updated_at
                """,
                (
                    relative_path,
                    str(source),
                    str(generated_path),
                    sha256,
                    source_size,
                    source_mtime,
                    backend,
                    pipeline_signature,
                    utc_now(),
                ),
            )
            key = "updated" if row is not None else "created"
            summary[key] += 1
            summary["changed_documents"].append(relative_path)
        except Exception as exc:  # noqa: BLE001
            remove_generated_artifacts(generated_path)
            conn.execute(
                """
                INSERT INTO pdf_ingest_manifest (
                    source_rel_path,
                    source_abs_path,
                    generated_abs_path,
                    source_sha256,
                    source_size,
                    source_mtime,
                    extractor,
                    pipeline_signature,
                    status,
                    error,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'failed', ?, ?)
                ON CONFLICT(source_rel_path) DO UPDATE SET
                    source_abs_path = excluded.source_abs_path,
                    generated_abs_path = excluded.generated_abs_path,
                    source_sha256 = excluded.source_sha256,
                    source_size = excluded.source_size,
                    source_mtime = excluded.source_mtime,
                    extractor = excluded.extractor,
                    pipeline_signature = excluded.pipeline_signature,
                    status = 'failed',
                    error = excluded.error,
                    updated_at = excluded.updated_at
                """,
                (
                    relative_path,
                    str(source),
                    str(generated_path),
                    sha256,
                    source_size,
                    source_mtime,
                    backend,
                    pipeline_signature,
                    str(exc),
                    utc_now(),
                ),
            )
            summary["failed"] += 1
            summary["failed_documents"].append({"path": relative_path, "error": str(exc)})

    stale_rows = conn.execute("SELECT source_rel_path, generated_abs_path FROM pdf_ingest_manifest").fetchall()
    for row in stale_rows:
        relative_path = row["source_rel_path"]
        if relative_path in seen_rel_paths:
            continue
        generated_path = Path(row["generated_abs_path"])
        remove_generated_artifacts(generated_path)
        conn.execute("DELETE FROM pdf_ingest_manifest WHERE source_rel_path = ?", (relative_path,))
        summary["removed"] += 1
        summary["removed_documents"].append(relative_path)

    conn.commit()
    conn.close()

    summary["qmd_refresh_needed"] = bool(summary["created"] or summary["updated"] or summary["removed"])
    write_status_file(summary)
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
