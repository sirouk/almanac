#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PDF_INGEST_PY = REPO / "bin" / "pdf-ingest.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_tool_subprocess_env_scrubs_secrets() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        env = {
            **os.environ,
            "VAULT_DIR": str(root / "vault"),
            "PDF_INGEST_MARKDOWN_DIR": str(root / "markdown"),
            "PDF_INGEST_MANIFEST_DB": str(root / "manifest.sqlite3"),
            "PDF_INGEST_STATUS_FILE": str(root / "status.json"),
            "PDF_VISION_API_KEY": "vision-secret",
            "POSTGRES_PASSWORD": "db-secret",
            "PATH": "/tmp/tainted",
            "HOME": str(root / "home"),
        }
        old_env = os.environ.copy()
        os.environ.clear()
        os.environ.update(env)
        try:
            module = load_module(PDF_INGEST_PY, "pdf_ingest_env_scrub_test")
            scrubbed = module.tool_subprocess_env()
            expect(scrubbed.get("PATH") == "/tmp/tainted", str(scrubbed))
            expect(scrubbed.get("HOME") == str(root / "home"), str(scrubbed))
            expect("PDF_VISION_API_KEY" not in scrubbed, str(scrubbed))
            expect("POSTGRES_PASSWORD" not in scrubbed, str(scrubbed))
            print("PASS test_tool_subprocess_env_scrubs_secrets")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_list_pdf_sources_rejects_symlink_escapes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        vault = root / "vault"
        outside = root / "outside"
        vault.mkdir(parents=True)
        outside.mkdir(parents=True)
        (vault / "inside.pdf").write_bytes(b"%PDF-1.4\n% inside\n")
        (outside / "secret.pdf").write_bytes(b"%PDF-1.4\n% outside\n")
        (vault / "linked.pdf").symlink_to(outside / "secret.pdf")
        env = {
            **os.environ,
            "VAULT_DIR": str(vault),
            "PDF_INGEST_MARKDOWN_DIR": str(root / "markdown"),
            "PDF_INGEST_MANIFEST_DB": str(root / "manifest.sqlite3"),
            "PDF_INGEST_STATUS_FILE": str(root / "status.json"),
        }
        old_env = os.environ.copy()
        os.environ.clear()
        os.environ.update(env)
        try:
            module = load_module(PDF_INGEST_PY, "pdf_ingest_symlink_rejection_test")
            sources = {path.name for path in module.list_pdf_sources()}
            expect(sources == {"inside.pdf"}, str(sources))
            print("PASS test_list_pdf_sources_rejects_symlink_escapes")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_generated_artifact_cleanup_refuses_paths_outside_markdown_root() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        markdown = root / "markdown"
        outside = root / "outside.md"
        inside = markdown / "doc.md"
        outside.write_text("outside\n", encoding="utf-8")
        inside.parent.mkdir(parents=True)
        inside.write_text("inside\n", encoding="utf-8")
        env = {
            **os.environ,
            "VAULT_DIR": str(root / "vault"),
            "PDF_INGEST_MARKDOWN_DIR": str(markdown),
            "PDF_INGEST_MANIFEST_DB": str(root / "manifest.sqlite3"),
            "PDF_INGEST_STATUS_FILE": str(root / "status.json"),
        }
        old_env = os.environ.copy()
        os.environ.clear()
        os.environ.update(env)
        try:
            module = load_module(PDF_INGEST_PY, "pdf_ingest_cleanup_guard_test")
            expect(module.remove_generated_artifacts(outside) is False, "outside cleanup must be refused")
            expect(outside.exists(), "outside file must not be unlinked")
            symlink = markdown / "linked.md"
            symlink.symlink_to(outside)
            try:
                module.require_generated_artifact_path(symlink)
            except RuntimeError:
                pass
            else:
                raise AssertionError("symlinked generated output path should be refused before write")
            expect(module.remove_generated_artifacts(inside) is True, "inside cleanup should remove generated artifact")
            expect(not inside.exists(), "inside generated file should be removed")
            print("PASS test_generated_artifact_cleanup_refuses_paths_outside_markdown_root")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_vision_endpoint_is_hashed_in_generated_frontmatter() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        env = {
            **os.environ,
            "VAULT_DIR": str(root / "vault"),
            "PDF_INGEST_MARKDOWN_DIR": str(root / "markdown"),
            "PDF_INGEST_MANIFEST_DB": str(root / "manifest.sqlite3"),
            "PDF_INGEST_STATUS_FILE": str(root / "status.json"),
            "PDF_VISION_ENDPOINT": "https://user:secret@endpoint.example.test/v1",
            "PDF_VISION_MODEL": "vision-model",
            "PDF_VISION_API_KEY": "vision-secret",
            "PDF_VISION_MAX_PAGES": "1",
        }
        old_env = os.environ.copy()
        os.environ.clear()
        os.environ.update(env)
        try:
            module = load_module(PDF_INGEST_PY, "pdf_ingest_endpoint_redaction_test")
            signature = module.build_pipeline_signature("pdftotext")
            rendered = module.render_markdown(
                "packet.pdf",
                root / "vault" / "packet.pdf",
                "abc123",
                12,
                123,
                "pdftotext",
                "body",
                None,
                [],
                {"rendered": 0, "captioned": 0, "failed": 0},
                signature,
            )
            expect("user:secret" not in signature, signature)
            expect("endpoint.example.test" not in signature, signature)
            expect("vision_endpoint_sha256=" in signature, signature)
            expect("user:secret" not in rendered, rendered)
            expect("endpoint.example.test" not in rendered, rendered)
            print("PASS test_vision_endpoint_is_hashed_in_generated_frontmatter")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_pdf_same_size_same_second_rewrite_updates_sidecar() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        vault = root / "vault"
        pdf = vault / "packet.pdf"
        vault.mkdir(parents=True)
        pdf.write_text("Alpha-1111\n", encoding="utf-8")
        os.utime(pdf, (1_700_000_000, 1_700_000_000))
        env = {
            **os.environ,
            "VAULT_DIR": str(vault),
            "PDF_INGEST_MARKDOWN_DIR": str(root / "markdown"),
            "PDF_INGEST_MANIFEST_DB": str(root / "manifest.sqlite3"),
            "PDF_INGEST_STATUS_FILE": str(root / "status.json"),
            "PDF_INGEST_EXTRACTOR": "auto",
        }
        old_env = os.environ.copy()
        os.environ.clear()
        os.environ.update(env)
        try:
            module = load_module(PDF_INGEST_PY, "pdf_ingest_same_size_rewrite_test")
            module.resolve_backend = lambda: "pdftotext"
            module.extract_text_body = lambda source, backend: (source.read_text(encoding="utf-8"), None)
            module.generate_visual_notes = lambda source: ([], {"rendered": 0, "captioned": 0, "failed": 0, "failures": []})

            first_status = module.main()
            expect(first_status == 0, f"first ingest failed with {first_status}")
            generated = root / "markdown" / "packet-pdf.md"
            expect("Alpha-1111" in generated.read_text(encoding="utf-8"), generated.read_text(encoding="utf-8"))

            pdf.write_text("Beta--2222\n", encoding="utf-8")
            os.utime(pdf, (1_700_000_000, 1_700_000_000))
            second_status = module.main()
            expect(second_status == 0, f"second ingest failed with {second_status}")
            summary = json.loads((root / "status.json").read_text(encoding="utf-8"))
            rendered = generated.read_text(encoding="utf-8")
            expect(summary["updated"] == 1, str(summary))
            expect("Beta--2222" in rendered and "Alpha-1111" not in rendered, rendered)
            print("PASS test_pdf_same_size_same_second_rewrite_updates_sidecar")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def main() -> int:
    test_tool_subprocess_env_scrubs_secrets()
    test_list_pdf_sources_rejects_symlink_escapes()
    test_generated_artifact_cleanup_refuses_paths_outside_markdown_root()
    test_vision_endpoint_is_hashed_in_generated_frontmatter()
    test_pdf_same_size_same_second_rewrite_updates_sidecar()
    print("PASS all 5 pdf ingest env tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
