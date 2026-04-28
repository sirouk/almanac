#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO / "bin" / "retrieval-journey-replay.py"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_module():
    spec = importlib.util.spec_from_file_location("retrieval_journey_replay", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["retrieval_journey_replay"] = module
    spec.loader.exec_module(module)
    return module


def test_journeys_cover_world_class_personas_and_sources() -> None:
    mod = load_module()
    journeys = mod.build_journeys("abc123", include_pdf=True, include_notion=True)
    personas = {journey.persona for journey in journeys}
    sources = {journey.source for journey in journeys}
    expect(
        {
            "business_operator",
            "organization_worker",
            "family",
            "individual",
            "creator",
            "developer_repo",
            "document_heavy_team",
            "notion_driven_team",
        }.issubset(personas),
        str(personas),
    )
    expect({"vault-markdown", "vault-text", "cloned-repo", "pdf-sidecar", "notion-shared"}.issubset(sources), str(sources))
    for journey in journeys:
        expect(journey.expected_markers, f"{journey.persona} should assert exact evidence markers")
        expect(journey.tool in {"vault.search-and-fetch", "knowledge.search-and-fetch", "notion.search-and-fetch"}, journey.tool)
    print("PASS test_journeys_cover_world_class_personas_and_sources")


def test_payload_texts_ignores_query_echo_and_checks_fetched_evidence() -> None:
    mod = load_module()
    needle = "ALMANAC_REPLAY_echo_probe"
    echoed_payload = {
        "query": needle,
        "fetched": [
            {
                "fetch": {"text": "unrelated answer body"},
                "search_hit": {"snippet": "still unrelated"},
            }
        ],
    }
    expect(not any(needle in text for text in mod.payload_texts(echoed_payload)), "query echo must not count as evidence")
    evidence_payload = {
        "query": "natural language question",
        "source_results": {
            "vault": {
                "query": "still not evidence",
                "fetched": [
                    {
                        "fetch": {"text": f"answer body with {needle}"},
                        "search_hit": {"file": "vault/replay.md"},
                    }
                ],
            }
        },
    }
    expect(any(needle in text for text in mod.payload_texts(evidence_payload)), "fetched text should count as evidence")
    print("PASS test_payload_texts_ignores_query_echo_and_checks_fetched_evidence")


def test_seed_vault_creates_repo_bulk_and_extractable_pdf() -> None:
    mod = load_module()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "Almanac"
        replay_root = mod.seed_vault(root, "seedprobe", bulk_count=3, include_pdf=True)
        expect(".almanac" not in replay_root.as_posix(), "replay root must not use a hidden path skipped by qmd")
        expect((replay_root / "business" / "mira-board-prep.md").exists(), "business markdown missing")
        expect((replay_root / "family" / "rowan-week.txt").exists(), "family text missing")
        expect((replay_root / "repos" / "fluxbridge" / ".git").exists(), "local cloned-repo fixture missing")
        expect(len(list((replay_root / "bulk").glob("*.md"))) == 3, "bulk count mismatch")
        pdf_path = replay_root / "pdf" / "studio-insurance.pdf"
        expect(pdf_path.exists(), "PDF fixture missing")
        if subprocess.run(["bash", "-lc", "command -v pdftotext"], capture_output=True).returncode == 0:
            result = subprocess.run(["pdftotext", "-enc", "UTF-8", "-nopgbrk", str(pdf_path), "-"], text=True, capture_output=True, check=False)
            expect(result.returncode == 0, result.stderr)
            expect("PDF_INSURANCE" in result.stdout, result.stdout)
    print("PASS test_seed_vault_creates_repo_bulk_and_extractable_pdf")


def test_scorecard_records_accuracy_and_persona_timings() -> None:
    mod = load_module()
    with tempfile.TemporaryDirectory() as tmp:
        scorecard = Path(tmp) / "scorecard.jsonl"
        report = {
            "ok": True,
            "run_id": "scoreprobe",
            "seed": {"bulk_count": 3},
            "summary": {"accuracy": 1.0, "journeys": 1, "passed": 1, "failed": 0},
            "results": [
                {
                    "persona": "business_operator",
                    "source": "vault-markdown",
                    "ok": True,
                    "seconds": 0.42,
                    "attempts": 1,
                    "missing": [],
                    "expected": ["marker"],
                }
            ],
        }
        mod.append_scorecard(str(scorecard), report, label="unit")
        lines = scorecard.read_text(encoding="utf-8").splitlines()
        expect(len(lines) == 1, lines)
        entry = json.loads(lines[0])
        expect(entry["label"] == "unit", entry)
        expect(entry["summary"]["accuracy"] == 1.0, entry)
        expect(entry["personas"][0]["persona"] == "business_operator", entry)
    print("PASS test_scorecard_records_accuracy_and_persona_timings")


def test_almanac_ctl_exposes_retrieval_replay_command() -> None:
    ctl = (REPO / "python" / "almanac_ctl.py").read_text(encoding="utf-8")
    wrapper = (REPO / "bin" / "almanac-ctl").read_text(encoding="utf-8")
    expect('subparsers.add_parser("retrieval")' in ctl, "retrieval domain missing from almanac_ctl")
    expect('retrieval_sub.add_parser("replay")' in ctl, "retrieval replay command missing")
    expect('"unset QMD_INDEX_DB_PATH INDEX_PATH; "' in ctl, "qmd refresh runuser command should clear root-derived qmd cache env")
    expect('export XDG_CACHE_HOME="$HOME/.cache";' in ctl, "qmd refresh runuser command should pin service-user cache")
    expect('domain_arg="$arg"' in wrapper, "wrapper should detect domain after global flags")
    expect('"$domain_arg" == "retrieval" && "$action_arg" == "replay"' in wrapper, "retrieval replay should sudo through wrapper")
    expect('ALMANAC_CONFIG_FILE="${ALMANAC_CONFIG_FILE:-$CONFIG_FILE}"' in wrapper, "sudo re-exec should preserve discovered config")
    print("PASS test_almanac_ctl_exposes_retrieval_replay_command")


def main() -> int:
    test_journeys_cover_world_class_personas_and_sources()
    test_payload_texts_ignores_query_echo_and_checks_fetched_evidence()
    test_seed_vault_creates_repo_bulk_and_extractable_pdf()
    test_scorecard_records_accuracy_and_persona_timings()
    test_almanac_ctl_exposes_retrieval_replay_command()
    print("PASS all 5 retrieval journey replay tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
