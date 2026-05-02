#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(REPO_DIR / "python"))

from arclink_rpc_client import mcp_call  # noqa: E402


@dataclass(frozen=True)
class Journey:
    persona: str
    source: str
    tool: str
    query: str
    expected_markers: tuple[str, ...]
    collections: tuple[str, ...] = ("vault", "vault-pdf-ingest")


def marker(run_id: str, name: str) -> str:
    return f"ARCLINK_REPLAY_{run_id}_{name}"


def build_journeys(run_id: str, include_pdf: bool, include_notion: bool) -> list[Journey]:
    journeys = [
        Journey(
            persona="business_operator",
            source="vault-markdown",
            tool="knowledge.search-and-fetch",
            query="What should Mira prioritize before the Monday board prep and which renewal is risky?",
            expected_markers=(marker(run_id, "BUSINESS_BOARD"), marker(run_id, "BUSINESS_RENEWAL")),
        ),
        Journey(
            persona="organization_worker",
            source="vault-markdown",
            tool="knowledge.search-and-fetch",
            query="Who owns the Nimbus onboarding API migration and what is blocking the work?",
            expected_markers=(marker(run_id, "ORG_OWNER"), marker(run_id, "ORG_BLOCKER")),
        ),
        Journey(
            persona="family",
            source="vault-text",
            tool="vault.search-and-fetch",
            query="What food allergy and pickup change should the family helper remember for Rowan?",
            expected_markers=(marker(run_id, "FAMILY_ALLERGY"), marker(run_id, "FAMILY_PICKUP")),
        ),
        Journey(
            persona="individual",
            source="vault-markdown",
            tool="vault.search-and-fetch",
            query="What routine did Jules choose after PT and what should they avoid this week?",
            expected_markers=(marker(run_id, "INDIVIDUAL_ROUTINE"), marker(run_id, "INDIVIDUAL_AVOID")),
        ),
        Journey(
            persona="creator",
            source="vault-markdown",
            tool="knowledge.search-and-fetch",
            query="What sponsor deliverables does Kai owe and what thumbnail style rule matters?",
            expected_markers=(marker(run_id, "CREATOR_SPONSOR"), marker(run_id, "CREATOR_STYLE")),
        ),
        Journey(
            persona="developer_repo",
            source="cloned-repo",
            tool="vault.search-and-fetch",
            query="What retry window and owner did the FluxBridge repo note specify?",
            expected_markers=(marker(run_id, "REPO_RETRY"), marker(run_id, "REPO_OWNER")),
        ),
    ]
    if include_pdf:
        journeys.append(
            Journey(
                persona="document_heavy_team",
                source="pdf-sidecar",
                tool="vault.search-and-fetch",
                query="What does the studio insurance PDF say is due Friday?",
                expected_markers=(marker(run_id, "PDF_INSURANCE"),),
                collections=("vault-pdf-ingest",),
            )
        )
    if include_notion:
        journeys.append(
            Journey(
                persona="notion_driven_team",
                source="notion-shared",
                tool="notion.search-and-fetch",
                query="What does the shared Notion replay page say about the Acorn launch decision?",
                expected_markers=(marker(run_id, "NOTION_DECISION"), marker(run_id, "NOTION_DRI")),
                collections=("notion-shared",),
            )
        )
    return journeys


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


def pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_simple_pdf(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    stream_lines = ["BT", "/F1 11 Tf", "72 720 Td", "14 TL"]
    for index, line in enumerate(lines):
        if index:
            stream_lines.append("T*")
        stream_lines.append(f"({pdf_escape(line)}) Tj")
    stream_lines.append("ET")
    stream = "\n".join(stream_lines).encode("utf-8")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    chunks = [b"%PDF-1.4\n"]
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(sum(len(chunk) for chunk in chunks))
        chunks.append(f"{index} 0 obj\n".encode("ascii") + obj + b"\nendobj\n")
    xref_offset = sum(len(chunk) for chunk in chunks)
    xref = [b"xref\n", f"0 {len(objects) + 1}\n".encode("ascii"), b"0000000000 65535 f \n"]
    for offset in offsets[1:]:
        xref.append(f"{offset:010d} 00000 n \n".encode("ascii"))
    trailer = (
        b"trailer\n"
        + f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode("ascii")
        + b"startxref\n"
        + str(xref_offset).encode("ascii")
        + b"\n%%EOF\n"
    )
    path.write_bytes(b"".join(chunks + xref + [trailer]))


def seed_vault(root: Path, run_id: str, bulk_count: int, include_pdf: bool) -> Path:
    # qmd intentionally behaves like common glob/indexers and skips hidden path
    # segments. Keep the replay root visible so this exercises real recall.
    replay_root = root / "Research" / "arclink-retrieval-replay" / run_id
    if replay_root.exists():
        shutil.rmtree(replay_root)

    write_text(
        replay_root / "business" / "mira-board-prep.md",
        f"""
        # Mira Board Prep

        Mira's Monday board prep priority is a cash-runway covenant rename.
        Evidence marker: {marker(run_id, "BUSINESS_BOARD")}

        The renewal risk is the ACME annual renewal because procurement has not signed the data addendum.
        Evidence marker: {marker(run_id, "BUSINESS_RENEWAL")}
        """,
    )
    write_text(
        replay_root / "organization" / "nimbus-api-migration.md",
        f"""
        # Nimbus Onboarding API Migration

        Avery owns the OAuth callback migration.
        Evidence marker: {marker(run_id, "ORG_OWNER")}

        The blocker is a production DNS freeze until the security review closes.
        Evidence marker: {marker(run_id, "ORG_BLOCKER")}
        """,
    )
    write_text(
        replay_root / "family" / "rowan-week.txt",
        f"""
        Rowan cannot have cashews or cashew pesto at school events.
        Evidence marker: {marker(run_id, "FAMILY_ALLERGY")}

        Thursday robotics pickup moved to the east library door at 5:20 PM.
        Evidence marker: {marker(run_id, "FAMILY_PICKUP")}
        """,
    )
    write_text(
        replay_root / "individual" / "jules-pt-plan.md",
        f"""
        # Jules PT Plan

        Jules chose a ten-minute mobility ladder after breakfast.
        Evidence marker: {marker(run_id, "INDIVIDUAL_ROUTINE")}

        Jules should avoid hill running this week.
        Evidence marker: {marker(run_id, "INDIVIDUAL_AVOID")}
        """,
    )
    write_text(
        replay_root / "creator" / "kai-sponsor-brief.md",
        f"""
        # Kai Sponsor Brief

        Kai owes three short reels and one pinned community post to the sponsor.
        Evidence marker: {marker(run_id, "CREATOR_SPONSOR")}

        The thumbnail rule is no beige thumbnails; use high-contrast green with visible product texture.
        Evidence marker: {marker(run_id, "CREATOR_STYLE")}
        """,
    )

    repo = replay_root / "repos" / "fluxbridge"
    write_text(
        repo / "README.md",
        f"""
        # FluxBridge

        Retry window: 45 seconds before surfacing a customer-visible timeout.
        Evidence marker: {marker(run_id, "REPO_RETRY")}

        Owner: Priya handles the queue handoff and replay alarms.
        Evidence marker: {marker(run_id, "REPO_OWNER")}
        """,
    )
    subprocess.run(["git", "init", "-q"], cwd=repo, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    bulk_dir = replay_root / "bulk"
    for index in range(max(0, bulk_count)):
        write_text(
            bulk_dir / f"drop-{index:03d}.md",
            f"""
            # Bulk replay note {index:03d}

            This file simulates a large vault drop for retrieval replay.
            Run id: {run_id}
            Bulk marker: {marker(run_id, f"BULK_{index:03d}")}
            """,
        )

    if include_pdf:
        write_simple_pdf(
            replay_root / "pdf" / "studio-insurance.pdf",
            [
                "Studio insurance renewal packet",
                f"Certificate binder is due Friday. Evidence marker: {marker(run_id, 'PDF_INSURANCE')}",
            ],
        )
    return replay_root


def seed_notion(notion_root: Path | None, run_id: str) -> Path | None:
    if notion_root is None:
        return None
    path = notion_root / "arclink-replay" / f"shared-decision-{run_id}.md"
    write_text(
        path,
        f"""
        # Shared Notion Replay Decision

        The Acorn launch decision is to ship the concierge onboarding pilot before the public waitlist.
        Evidence marker: {marker(run_id, "NOTION_DECISION")}

        The DRI is Lena, with Devon as backup reviewer.
        Evidence marker: {marker(run_id, "NOTION_DRI")}
        """,
    )
    return path


def payload_texts(payload: dict[str, Any]) -> list[str]:
    texts: list[str] = []

    def collect(value: Any, key_name: str = "") -> None:
        if key_name == "query":
            return
        if isinstance(value, str):
            texts.append(value)
            return
        if isinstance(value, (int, float, bool)) or value is None:
            return
        if isinstance(value, list):
            for item in value:
                collect(item)
            return
        if isinstance(value, dict):
            for key, item in value.items():
                collect(item, str(key))

    for item in payload.get("fetched") or []:
        collect(item)
    search = payload.get("search")
    if isinstance(search, dict):
        for item in search.get("results") or []:
            collect(item)
    for item in payload.get("results") or []:
        collect(item)
    for source_result in (payload.get("source_results") or {}).values():
        collect(source_result)
    return texts


def call_journey(url: str, token: str, journey: Journey, timeout: float, poll_interval: float) -> dict[str, Any]:
    started = time.perf_counter()
    attempts = 0
    last_files: list[str] = []
    missing = list(journey.expected_markers)
    while True:
        attempts += 1
        args: dict[str, Any] = {
            "token": token,
            "query": journey.query,
            "collections": list(journey.collections),
            "search_limit": 5,
            "fetch_limit": 2,
            "body_char_limit": 8000,
        }
        payload = mcp_call(url, journey.tool, args)
        texts = payload_texts(payload)
        haystack = "\n".join(texts)
        missing = [expected for expected in journey.expected_markers if expected not in haystack]
        last_files = sorted(
            {
                str(value)
                for text in texts
                for value in [text]
                if value.startswith("vault/") or value.startswith("qmd://") or "/ArcLink/" in value
            }
        )[:8]
        if not missing:
            return {
                "persona": journey.persona,
                "source": journey.source,
                "tool": journey.tool,
                "ok": True,
                "seconds": round(time.perf_counter() - started, 3),
                "attempts": attempts,
                "expected": list(journey.expected_markers),
                "missing": [],
                "files": last_files,
            }
        if time.perf_counter() - started > timeout:
            return {
                "persona": journey.persona,
                "source": journey.source,
                "tool": journey.tool,
                "ok": False,
                "seconds": round(time.perf_counter() - started, 3),
                "attempts": attempts,
                "expected": list(journey.expected_markers),
                "missing": missing,
                "files": last_files,
            }
        time.sleep(poll_interval)


def run_command(command: str | None) -> dict[str, Any] | None:
    if not command:
        return None
    started = time.perf_counter()
    result = subprocess.run(command, shell=True, text=True, capture_output=True, check=False)
    return {
        "command": command,
        "returncode": result.returncode,
        "seconds": round(time.perf_counter() - started, 3),
        "stdout_tail": "\n".join((result.stdout or "").splitlines()[-8:]),
        "stderr_tail": "\n".join((result.stderr or "").splitlines()[-8:]),
    }


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * p))))
    return round(float(ordered[rank]), 3)


def append_scorecard(path: str, report: dict[str, Any], *, label: str) -> None:
    if not path:
        return
    scorecard_path = Path(path).expanduser()
    scorecard_path.parent.mkdir(parents=True, exist_ok=True)
    summary = dict(report.get("summary") or {})
    entry = {
        "created_at_epoch": round(time.time(), 3),
        "label": label,
        "ok": bool(report.get("ok")),
        "run_id": report.get("run_id"),
        "seed": report.get("seed"),
        "summary": summary,
        "personas": [
            {
                "persona": item.get("persona"),
                "source": item.get("source"),
                "ok": bool(item.get("ok")),
                "seconds": item.get("seconds"),
                "attempts": item.get("attempts"),
                "missing": item.get("missing") or [],
            }
            for item in report.get("results", [])
            if isinstance(item, dict)
        ],
    }
    with scorecard_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed and replay cross-persona ArcLink retrieval journeys.")
    parser.add_argument("--mcp-url", default=os.environ.get("ARCLINK_MCP_URL", "http://127.0.0.1:8282/mcp"))
    parser.add_argument("--token-file", required=True, help="Agent bootstrap token file readable by the current user.")
    parser.add_argument("--vault-root", default=str(Path.home() / "ArcLink"))
    parser.add_argument("--notion-index-root", default="", help="Optional notion-shared markdown root to seed.")
    parser.add_argument("--after-seed-command", default="", help="Optional shell command after seeding, e.g. qmd-refresh for direct notion-index seeding.")
    parser.add_argument("--after-cleanup-command", default="", help="Optional shell command after cleanup.")
    parser.add_argument("--bulk-count", type=int, default=30)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--run-id", default=uuid.uuid4().hex[:12])
    parser.add_argument("--no-pdf", action="store_true")
    parser.add_argument("--keep-data", action="store_true")
    parser.add_argument("--scorecard-file", default="", help="Optional JSONL scorecard file to append this run to.")
    parser.add_argument("--label", default="manual", help="Label stored with --scorecard-file entries.")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    token = Path(args.token_file).read_text(encoding="utf-8").strip()
    vault_root = Path(args.vault_root).expanduser().resolve()
    notion_root = Path(args.notion_index_root).expanduser().resolve() if args.notion_index_root else None
    include_pdf = not args.no_pdf
    include_notion = notion_root is not None

    started = time.perf_counter()
    replay_root: Path | None = None
    notion_doc: Path | None = None
    after_seed: dict[str, Any] | None = None
    after_cleanup: dict[str, Any] | None = None
    results: list[dict[str, Any]] = []
    try:
        replay_root = seed_vault(vault_root, args.run_id, args.bulk_count, include_pdf)
        notion_doc = seed_notion(notion_root, args.run_id)
        after_seed = run_command(args.after_seed_command)
        journeys = build_journeys(args.run_id, include_pdf=include_pdf, include_notion=include_notion)
        results = [
            call_journey(args.mcp_url, token, journey, args.timeout, args.poll_interval)
            for journey in journeys
        ]
    finally:
        if not args.keep_data:
            if replay_root is not None and replay_root.exists():
                shutil.rmtree(replay_root)
            if notion_doc is not None and notion_doc.exists():
                notion_doc.unlink()
                try:
                    notion_doc.parent.rmdir()
                except OSError:
                    pass
            after_cleanup = run_command(args.after_cleanup_command)

    ok_count = sum(1 for item in results if item.get("ok"))
    journey_seconds = [float(item.get("seconds") or 0.0) for item in results]
    sources = sorted({str(item.get("source") or "") for item in results if str(item.get("source") or "")})
    personas = sorted({str(item.get("persona") or "") for item in results if str(item.get("persona") or "")})
    command_failures = [
        item
        for item in (after_seed, after_cleanup)
        if item is not None and item.get("returncode") not in (0, None)
    ]
    report = {
        "ok": ok_count == len(results) and not command_failures,
        "run_id": args.run_id,
        "seed": {
            "vault_root": str(vault_root),
            "replay_root": str(replay_root) if replay_root else "",
            "notion_doc": str(notion_doc) if notion_doc else "",
            "bulk_count": args.bulk_count,
            "include_pdf": include_pdf,
            "include_notion": include_notion,
        },
        "after_seed": after_seed,
        "after_cleanup": after_cleanup,
        "summary": {
            "journeys": len(results),
            "passed": ok_count,
            "failed": len(results) - ok_count,
            "accuracy": round((ok_count / len(results)) if results else 0.0, 4),
            "persona_coverage": personas,
            "source_coverage": sources,
            "command_failures": len(command_failures),
            "total_seconds": round(time.perf_counter() - started, 3),
            "max_journey_seconds": max((float(item["seconds"]) for item in results), default=0.0),
            "p95_journey_seconds": percentile(journey_seconds, 0.95),
        },
        "results": results,
    }
    append_scorecard(args.scorecard_file, report, label=args.label)
    if args.scorecard_file:
        report["scorecard_file"] = str(Path(args.scorecard_file).expanduser())
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Retrieval journey replay: {ok_count}/{len(results)} passed in {report['summary']['total_seconds']}s")
        for item in results:
            status = "PASS" if item["ok"] else "FAIL"
            print(f"{status} {item['persona']} [{item['source']}] {item['seconds']}s attempts={item['attempts']}")
            if item["missing"]:
                print(f"  missing: {', '.join(item['missing'])}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
