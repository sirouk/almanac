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
    expect(
        'ARCLINK_MEMORY_SYNTH_ON_VAULT_CHANGE="${ARCLINK_MEMORY_SYNTH_ON_VAULT_CHANGE:-1}"' in body,
        "vault changes should request a low-latency memory synthesis pass by default",
    )
    print("PASS test_vault_watch_defaults_to_low_latency_debounce")


def test_vault_watch_accepts_fractional_debounce() -> None:
    body = VAULT_WATCH_SH.read_text(encoding="utf-8")
    snippet = extract(body, "read_next_event() {", "\ndrain_event_burst() {")
    script = f"""
{snippet}
vault_watch_fd=9
exec 9< <(sleep 0.2)
if read_next_event 0.05 >/tmp/arclink-vault-watch-fractional.out; then
  printf 'unexpected_event\\n'
else
  printf 'fractional_timeout_ok\\n'
fi
exec 9<&-
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


def test_vault_watch_requests_async_memory_synthesis_without_blocking() -> None:
    body = VAULT_WATCH_SH.read_text(encoding="utf-8")
    snippet = extract(body, "request_memory_synth_refresh() {", "\nfold_event_into_flags() {")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bin_dir = root / "bin"
        bin_dir.mkdir()
        log_path = root / "memory-synth.log"
        (bin_dir / "memory-synth.sh").write_text(
            "#!/usr/bin/env bash\n"
            "sleep 0.05\n"
            f"printf 'ran\\n' >> {log_path}\n",
            encoding="utf-8",
        )
        (bin_dir / "memory-synth.sh").chmod(0o755)
        script = f"""
lowercase() {{
  printf '%s\\n' "$1" | tr '[:upper:]' '[:lower:]'
}}
SCRIPT_DIR={bin_dir}
ARCLINK_MEMORY_SYNTH_ON_VAULT_CHANGE=0
ARCLINK_MEMORY_SYNTH_ENABLED=1
count_log_lines() {{
  if [[ -e {log_path} ]]; then
    wc -l < {log_path} | tr -d '[:space:]'
  else
    printf 0
  fi
}}
{snippet}
request_memory_synth_refresh
sleep 0.1
printf 'disabled_count=%s\\n' "$(count_log_lines)"
ARCLINK_MEMORY_SYNTH_ON_VAULT_CHANGE=1
request_memory_synth_refresh
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if [[ "$(count_log_lines)" -ge 1 ]]; then
    break
  fi
  sleep 0.1
done
printf 'enabled_count=%s\\n' "$(count_log_lines)"
"""
        result = bash(script)
        expect(result.returncode == 0, f"memory synth request case failed: stdout={result.stdout!r} stderr={result.stderr!r}")
        expect("disabled_count=0" in result.stdout, result.stdout)
        expect("enabled_count=1" in result.stdout, result.stdout)
    print("PASS test_vault_watch_requests_async_memory_synthesis_without_blocking")


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
printf 'empty_dir_notify=%s\\n' "${{#vault_watch_notify_paths[@]}}"

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
        expect("empty_dir_notify=1" in result.stdout, result.stdout)
        expect("pdf_dir=1/1" in result.stdout, result.stdout)
        expect("deleted_dir=1/0" in result.stdout, result.stdout)
        expect("deleted_pdf_dir=1/1" in result.stdout, result.stdout)
    print("PASS test_directory_events_only_trigger_pdf_reconcile_when_needed")


def test_qmd_pending_embeddings_count_reads_qmd_status_output() -> None:
    body = COMMON_SH.read_text(encoding="utf-8")
    snippet = extract(body, "qmd_pending_embeddings_count() {", "\nconfigure_qmd_collections() {")
    script = f"""
ensure_nvm() {{ :; }}
timeout() {{
  shift
  "$@"
}}
qmd() {{
  printf 'Index: arclink\\nPending: 7 need embedding\\nEmbedded: 22\\n'
}}
QMD_INDEX_NAME=arclink
{snippet}
printf 'pending=%s\\n' "$(qmd_pending_embeddings_count)"
"""
    result = bash(script)
    expect(result.returncode == 0, f"qmd pending count case failed: stdout={result.stdout!r} stderr={result.stderr!r}")
    expect("pending=7" in result.stdout, result.stdout)
    expect("timeout 3s qmd" in snippet, snippet)
    print("PASS test_qmd_pending_embeddings_count_reads_qmd_status_output")


def main() -> int:
    test_vault_watch_defaults_to_low_latency_debounce()
    test_vault_watch_accepts_fractional_debounce()
    test_vault_watch_caps_continuous_burst_batches()
    test_vault_watch_requests_async_memory_synthesis_without_blocking()
    test_directory_events_only_trigger_pdf_reconcile_when_needed()
    test_qmd_pending_embeddings_count_reads_qmd_status_output()
    print("PASS all 6 vault watch regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
