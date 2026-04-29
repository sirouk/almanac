#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
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


def main() -> int:
    test_tool_subprocess_env_scrubs_secrets()
    test_list_pdf_sources_rejects_symlink_escapes()
    print("PASS all 2 pdf ingest env tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
