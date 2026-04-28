#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import tempfile
import sqlite3
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COMMON_SH = REPO / "bin" / "common.sh"
VAULT_WATCH_SH = REPO / "bin" / "vault-watch.sh"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def extract(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def bash(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", "-lc", script], cwd=str(REPO), text=True, capture_output=True, check=False)


def test_vault_watch_defaults_to_low_latency_debounce() -> None:
    body = COMMON_SH.read_text(encoding="utf-8")
    expect(
        'VAULT_WATCH_DEBOUNCE_SECONDS="${VAULT_WATCH_DEBOUNCE_SECONDS:-0.5}"' in body,
        "vault hot reload should default to a sub-second idle debounce",
    )
    expect(
        'VAULT_WATCH_MAX_BATCH_SECONDS="${VAULT_WATCH_MAX_BATCH_SECONDS:-10}"' in body,
        "vault hot reload should cap burst batching so continuous edits still refresh",
    )
    print("PASS test_vault_watch_defaults_to_low_latency_debounce")


def test_vault_watch_accepts_fractional_debounce() -> None:
    body = VAULT_WATCH_SH.read_text(encoding="utf-8")
    snippet = extract(body, "read_next_event() {", "\ndrain_event_burst() {")
    script = f"""
{snippet}
exec {{vault_watch_fd}}< <(sleep 0.2)
if read_next_event 0.05 >/tmp/almanac-vault-watch-fractional.out; then
  printf 'unexpected_event\\n'
else
  printf 'fractional_timeout_ok\\n'
fi
exec {{vault_watch_fd}}<&-
"""
    result = bash(script)
    expect(result.returncode == 0, f"fractional debounce case failed: stdout={result.stdout!r} stderr={result.stderr!r}")
    expect("fractional_timeout_ok" in result.stdout, result.stdout)
    print("PASS test_vault_watch_accepts_fractional_debounce")


def test_vault_watch_caps_continuous_burst_batches() -> None:
    body = VAULT_WATCH_SH.read_text(encoding="utf-8")
    snippet = extract(body, "drain_event_burst() {", '\necho "Watching $VAULT_DIR for vault changes..."')
    expect("VAULT_WATCH_MAX_BATCH_SECONDS" in snippet, "drain_event_burst should use a max batch window")
    expect("SECONDS - batch_started_at" in snippet, "drain_event_burst should stop continuous bursts on elapsed time")
    print("PASS test_vault_watch_caps_continuous_burst_batches")


def test_directory_events_only_trigger_pdf_reconcile_when_needed() -> None:
    body = VAULT_WATCH_SH.read_text(encoding="utf-8")
    snippet = extract(body, "is_pdf_path() {", "\nstart_event_stream() {")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        empty_dir = root / "RepoClone"
        pdf_dir = root / "ResearchDrop"
        deleted_pdf_dir = root / "DeletedPdfTree"
        manifest_db = root / "pdf-manifest.sqlite3"
        empty_dir.mkdir()
        pdf_dir.mkdir()
        (pdf_dir / "wide-table.pdf").write_bytes(b"%PDF-pretend")
        conn = sqlite3.connect(manifest_db)
        conn.execute("CREATE TABLE pdf_ingest_manifest (source_rel_path TEXT PRIMARY KEY)")
        conn.execute(
            "INSERT INTO pdf_ingest_manifest (source_rel_path) VALUES (?)",
            ("DeletedPdfTree/old-file.pdf",),
        )
        conn.commit()
        conn.close()
        script = f"""
{snippet}
PDF_INGEST_ENABLED=1
VAULT_DIR={root}
PDF_INGEST_MANIFEST_DB={manifest_db}

vault_watch_need_qmd=0
vault_watch_need_pdf=0
vault_watch_need_vault_reload=0
vault_watch_notify_paths=()
fold_event_into_flags {empty_dir} 'CREATE,ISDIR'
printf 'empty_dir=%s/%s\\n' "$vault_watch_need_qmd" "$vault_watch_need_pdf"

vault_watch_need_qmd=0
vault_watch_need_pdf=0
vault_watch_need_vault_reload=0
vault_watch_notify_paths=()
fold_event_into_flags {pdf_dir} 'MOVED_TO,ISDIR'
printf 'pdf_dir=%s/%s\\n' "$vault_watch_need_qmd" "$vault_watch_need_pdf"

vault_watch_need_qmd=0
vault_watch_need_pdf=0
vault_watch_need_vault_reload=0
vault_watch_notify_paths=()
fold_event_into_flags {root / 'DeletedTree'} 'DELETE,ISDIR'
printf 'deleted_dir=%s/%s\\n' "$vault_watch_need_qmd" "$vault_watch_need_pdf"

vault_watch_need_qmd=0
vault_watch_need_pdf=0
vault_watch_need_vault_reload=0
vault_watch_notify_paths=()
fold_event_into_flags {deleted_pdf_dir} 'DELETE,ISDIR'
printf 'deleted_pdf_dir=%s/%s\\n' "$vault_watch_need_qmd" "$vault_watch_need_pdf"
"""
        result = bash(script)
        expect(result.returncode == 0, f"vault-watch function case failed: stdout={result.stdout!r} stderr={result.stderr!r}")
        expect("empty_dir=1/0" in result.stdout, result.stdout)
        expect("pdf_dir=1/1" in result.stdout, result.stdout)
        expect("deleted_dir=1/0" in result.stdout, result.stdout)
        expect("deleted_pdf_dir=1/1" in result.stdout, result.stdout)
    print("PASS test_directory_events_only_trigger_pdf_reconcile_when_needed")


def main() -> int:
    test_vault_watch_defaults_to_low_latency_debounce()
    test_vault_watch_accepts_fractional_debounce()
    test_vault_watch_caps_continuous_burst_batches()
    test_directory_events_only_trigger_pdf_reconcile_when_needed()
    print("PASS all 4 vault watch regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
