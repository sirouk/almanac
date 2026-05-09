#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

import arclink_control as control
import arclink_memory_synthesizer as synth


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_config(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(f"{key}={json.dumps(value)}" for key, value in values.items()) + "\n", encoding="utf-8")


def base_config(root: Path) -> dict[str, str]:
    return {
        "ARCLINK_USER": "arclink",
        "ARCLINK_HOME": str(root / "home-arclink"),
        "ARCLINK_REPO_DIR": str(root / "repo"),
        "ARCLINK_PRIV_DIR": str(root / "priv"),
        "STATE_DIR": str(root / "state"),
        "RUNTIME_DIR": str(root / "state" / "runtime"),
        "VAULT_DIR": str(root / "vault"),
        "ARCLINK_DB_PATH": str(root / "state" / "arclink-control.sqlite3"),
        "ARCLINK_AGENTS_STATE_DIR": str(root / "state" / "agents"),
        "ARCLINK_CURATOR_DIR": str(root / "state" / "curator"),
        "ARCLINK_CURATOR_MANIFEST": str(root / "state" / "curator" / "manifest.json"),
        "ARCLINK_CURATOR_HERMES_HOME": str(root / "state" / "curator" / "hermes-home"),
        "ARCLINK_ARCHIVED_AGENTS_DIR": str(root / "state" / "archived-agents"),
        "ARCLINK_RELEASE_STATE_FILE": str(root / "state" / "arclink-release.json"),
        "ARCLINK_QMD_URL": "http://127.0.0.1:8181/mcp",
        "ARCLINK_MCP_HOST": "127.0.0.1",
        "ARCLINK_MCP_PORT": "8282",
        "ARCLINK_MEMORY_SYNTH_ENABLED": "1",
        "ARCLINK_MEMORY_SYNTH_ENDPOINT": "https://llm.example.test/v1/chat/completions",
        "ARCLINK_MEMORY_SYNTH_MODEL": "vision-model-test",
        "ARCLINK_MEMORY_SYNTH_API_KEY": "test-key",
        "ARCLINK_MEMORY_SYNTH_MAX_SOURCES_PER_RUN": "20",
        "ARCLINK_MEMORY_SYNTH_FAILURE_RETRY_SECONDS": "60",
        "ARCLINK_MEMORY_SYNTH_CARDS_IN_CONTEXT": "1",
        "ARCLINK_MODEL_PRESET_CODEX": "openai:codex",
        "ARCLINK_MODEL_PRESET_OPUS": "anthropic:claude-opus",
        "ARCLINK_MODEL_PRESET_CHUTES": "chutes:model-router",
    }


def local_fallback_config(root: Path) -> dict[str, str]:
    values = base_config(root)
    values.update(
        {
            "ARCLINK_MEMORY_SYNTH_ENABLED": "1",
            "ARCLINK_MEMORY_SYNTH_ENDPOINT": "",
            "ARCLINK_MEMORY_SYNTH_MODEL": "",
            "ARCLINK_MEMORY_SYNTH_API_KEY": "",
            "PDF_VISION_ENDPOINT": "",
            "PDF_VISION_MODEL": "",
            "PDF_VISION_API_KEY": "",
        }
    )
    return values


def insert_agent(conn, root: Path) -> None:
    now = control.utc_now_iso()
    hermes_home = root / "home-testuser" / ".local" / "share" / "arclink-agent" / "hermes-home"
    (hermes_home / "state").mkdir(parents=True, exist_ok=True)
    conn.execute(
        """
        INSERT INTO agents (
          agent_id, role, unix_user, display_name, status, hermes_home, manifest_path,
          archived_state_path, model_preset, model_string, channels_json,
          allowed_mcps_json, home_channel_json, operator_notify_channel_json,
          notes, created_at, last_enrolled_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "agent-test",
            "user",
            "testuser",
            "Test User",
            "active",
            str(hermes_home),
            str(root / "state" / "agents" / "agent-test" / "manifest.json"),
            None,
            "codex",
            "openai:codex",
            json.dumps(["tui-only"]),
            json.dumps([]),
            json.dumps({"platform": "tui", "channel_id": ""}),
            json.dumps({}),
            "",
            now,
            now,
        ),
    )
    conn.commit()


def seed_sources(root: Path, conn) -> None:
    (root / "vault" / "Research").mkdir(parents=True)
    (root / "vault" / "Research" / ".vault").write_text(
        "name: Research\n"
        "description: Fictional shared research notes\n"
        "owner: operator\n"
        "default_subscribed: true\n"
        "category: research\n",
        encoding="utf-8",
    )
    (root / "vault" / "Research" / "Horizon protocol notes.md").write_text(
        "# Horizon protocol\nPrivacy preserving distributed systems notes and open research questions.\n",
        encoding="utf-8",
    )
    (root / "vault" / "Projects" / "Nimbus Trading Lab").mkdir(parents=True)
    (root / "vault" / "Projects" / "Nimbus Trading Lab" / "Market making.md").write_text(
        "# Nimbus Trading Lab market making\nInventory control, spread policy, and execution-risk notes.\n",
        encoding="utf-8",
    )
    (root / "vault" / "Repos" / "archive-delta").mkdir(parents=True)
    (root / "vault" / "Repos" / "archive-delta" / ".git").mkdir()
    (root / "vault" / "Repos" / "archive-delta" / "README.md").write_text("# Archive Delta\n", encoding="utf-8")
    (root / "vault" / "Creator Studio" / "Episodes").mkdir(parents=True)
    (root / "vault" / "Creator Studio" / ".vault").write_text(
        "name: Creator Studio\n"
        "description: Fictional creator production workspace\n"
        "owner: operator\n"
        "default_subscribed: false\n"
        "category: creator\n",
        encoding="utf-8",
    )
    (root / "vault" / "Creator Studio" / "Episodes" / "pilot-cut.mp4").write_bytes(b"video")
    (root / "vault" / "Creator Studio" / "Episodes" / "thumbnail.png").write_bytes(b"image")
    (root / "vault" / "Creator Studio" / "content-calendar.csv").write_text(
        "episode,status\npilot,draft\n",
        encoding="utf-8",
    )
    (root / "vault" / "Family Hub").mkdir(parents=True)
    (root / "vault" / "Family Hub" / "school-calendar.csv").write_text("date,event\n2026-05-01,example\n", encoding="utf-8")
    (root / "vault" / "Big Archive").mkdir(parents=True)
    for index in range(100):
        (root / "vault" / "Big Archive" / f"note-{index:03d}.md").write_text(
            f"# Note {index:03d}\nFictional bulk archive note.\n",
            encoding="utf-8",
        )
    outside = root / "outside"
    outside.mkdir()
    (outside / "private-note.md").write_text("off-vault private note", encoding="utf-8")
    (root / "vault" / "Creator Studio" / "linked-private-note.md").symlink_to(outside / "private-note.md")

    notion_md = root / "state" / "notion-index" / "markdown" / "root-1" / "abc" / "0000.md"
    notion_md.parent.mkdir(parents=True, exist_ok=True)
    notion_md.write_text(
        "# Example Work Focus\nKora owns an offline workflow prototype and latency benchmark.\n",
        encoding="utf-8",
    )
    now = control.utc_now_iso()
    conn.execute(
        """
        INSERT INTO notion_index_documents (
          doc_key, root_id, source_page_id, source_page_url, source_kind,
          file_path, page_title, section_heading, section_ordinal,
          breadcrumb_json, owners_json, last_edited_time, content_hash,
          indexed_at, state
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "root-1:abc:0",
            "root-1",
            "abc",
            "https://www.notion.so/abc",
            "page",
            str(notion_md),
            "Example Work Focus",
            "Current Work",
            0,
            json.dumps(["Example Workspace", "Work Focus", "Example Work Focus"]),
            json.dumps(["Kora"]),
            now,
            "hash-abc",
            now,
            "active",
        ),
    )
    conn.commit()


def test_memory_synthesizer_caches_cards_and_injects_recall_stubs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, base_config(root))
        old_env = os.environ.copy()
        os.environ.update(base_config(root))
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            with control.connect_db(cfg) as conn:
                insert_agent(conn, root)
                seed_sources(root, conn)
                control.reload_vault_definitions(conn, cfg)
                conn.execute("DELETE FROM notification_outbox")
                conn.commit()
                settings = synth.load_settings(cfg)
                candidates = synth.build_candidates(conn, cfg, settings)
                creator = next(candidate for candidate in candidates if candidate.source_key == "Creator Studio")
                creator_payload = json.dumps(creator.payload, sort_keys=True)
                expect('"video": 1' in creator_payload, creator_payload)
                expect('"image": 1' in creator_payload, creator_payload)
                expect('"data": 1' in creator_payload, creator_payload)
                expect('"fingerprint_hash"' in creator_payload, creator_payload)
                expect("pilot-cut.mp4" in creator_payload and "thumbnail.png" in creator_payload, creator_payload)
                expect("linked-private-note" not in creator_payload, creator_payload)
                expect("off-vault private note" not in creator_payload, creator_payload)
                creator_prompt = synth._candidate_prompt(creator, settings)
                expect("fingerprint_count" in creator_prompt, creator_prompt)
                expect("fingerprint_hash" not in creator_prompt, creator_prompt)
                expect("deep:content-calendar.csv" not in creator_prompt, creator_prompt)
                expect("pilot-cut.mp4" in creator_prompt and "thumbnail.png" in creator_prompt, creator_prompt)
                archive = next(candidate for candidate in candidates if candidate.source_key == "Big Archive")
                archive_signature = archive.source_signature
                archive_hash = str(archive.payload.get("fingerprint_hash") or "")
                (root / "vault" / "Big Archive" / "note-099.md").write_text(
                    "# Note 099\nUpdated fictional bulk archive note.\n",
                    encoding="utf-8",
                )
                refreshed_candidates = synth.build_candidates(conn, cfg, settings)
                refreshed_archive = next(candidate for candidate in refreshed_candidates if candidate.source_key == "Big Archive")
                expect(str(refreshed_archive.payload.get("fingerprint_hash") or "") != archive_hash, refreshed_archive.payload)
                expect(refreshed_archive.source_signature != archive_signature, refreshed_archive.payload)

            calls: list[str] = []

            def fake_model(candidate: synth.SourceCandidate, settings: synth.SynthesisSettings) -> dict[str, object]:
                calls.append(f"{candidate.source_kind}:{candidate.source_key}")
                source_text = json.dumps(candidate.payload, sort_keys=True)
                return {
                    "summary": f"{candidate.source_title} contains compact orientation for retrieval.",
                    "domains": ["creator", "family", "business"],
                    "workflows": ["content planning", "household coordination", "research review"],
                    "content_types": ["notes", "PDFs", "videos", "images", "tables"],
                    "topics": ["research" if "Horizon" in source_text else "operations"],
                    "entities": ["Horizon Protocol", "Nimbus Trading Lab", "Archive Delta", "Example Workspace"],
                    "retrieval_queries": [candidate.source_title, "Horizon protocol", "Nimbus Trading Lab market making"],
                    "source_hints": [candidate.source_title],
                    "confidence": "medium",
                    "trust_score": 0.72,
                    "contradiction_signals": ["Horizon protocol notes list open research questions next to final protocol language"],
                    "disagreement_signals": ["Nimbus spread policy notes include unresolved execution-risk tradeoffs"],
                    "inject": True,
                }

            first = synth.run_once(cfg, model_client=fake_model)
            expect(first["status"] == "ok", str(first))
            expect(first["synthesized"] >= 4, str(first))
            expect(any(call == "vault:Creator Studio" for call in calls), calls)
            expect(any(call == "vault:Family Hub" for call in calls), calls)
            expect(any(call == "vault:Research" for call in calls), calls)
            expect(any(call == "vault:Projects" for call in calls), calls)
            expect(any(call == "vault:Repos" for call in calls), calls)
            expect(any(call.startswith("notion:Work Focus") for call in calls), calls)

            with control.connect_db(cfg) as conn:
                card_rows = conn.execute("SELECT source_kind, source_key, card_json, card_text FROM memory_synthesis_cards WHERE status = 'ok'").fetchall()
                card_text = "\n".join(str(row["card_text"] or "") for row in card_rows)
                expect("Research contains compact orientation" in card_text, card_text)
                expect("Projects contains compact orientation" in card_text, card_text)
                expect("Repos contains compact orientation" in card_text, card_text)
                expect("Nimbus Trading Lab" in card_text, card_text)
                expect("Archive Delta" in card_text, card_text)
                expect("Domains: creator, family, business." in card_text, card_text)
                expect("Workflows: content planning, household coordination, research review." in card_text, card_text)
                expect("Content: notes, PDFs, videos, images, tables." in card_text, card_text)
                expect("Confidence: medium." in card_text, card_text)
                expect("Trust score: 0.72." in card_text, card_text)
                expect("Contradiction signals: Horizon protocol notes list open research questions next to final protocol language." in card_text, card_text)
                expect("Disagreement signals: Nimbus spread policy notes include unresolved execution-risk tradeoffs." in card_text, card_text)
                parsed_cards = [json.loads(str(row["card_json"] or "{}")) for row in card_rows]
                expect(all(card.get("trust_score") == 0.72 for card in parsed_cards), parsed_cards)
                expect(
                    all(card.get("contradiction_signals") for card in parsed_cards)
                    and all(card.get("disagreement_signals") for card in parsed_cards),
                    parsed_cards,
                )
                fanout = conn.execute(
                    "SELECT COUNT(*) AS c FROM notification_outbox WHERE target_kind = 'curator' AND channel_kind = 'brief-fanout'"
                ).fetchone()
                expect(int(fanout["c"]) == 1, f"expected one curator fanout notification, got {fanout['c']}")
                conn.execute(
                    "UPDATE memory_synthesis_cards SET updated_at = ? WHERE source_kind = 'vault' AND source_key = ?",
                    ("2026-01-01T00:00:00+00:00", "Research"),
                )
                conn.execute(
                    "UPDATE memory_synthesis_cards SET updated_at = ? WHERE source_kind = 'vault' AND source_key = ?",
                    ("2026-12-31T00:00:00+00:00", "Creator Studio"),
                )
                conn.commit()
                payload = control.build_managed_memory_payload(conn, cfg, agent_id="agent-test")
                expect("Semantic synthesis cards:" in payload["recall-stubs"], payload["recall-stubs"])
                expect("Compact recall hints only" in payload["recall-stubs"], payload["recall-stubs"])
                expect("[vault:Research]" in payload["recall-stubs"], payload["recall-stubs"])
                expect("Trust score: 0.72." in payload["recall-stubs"], payload["recall-stubs"])
                expect("Contradiction signals:" in payload["recall-stubs"], payload["recall-stubs"])
                expect("Disagreement signals:" in payload["recall-stubs"], payload["recall-stubs"])
                expect("[vault:Creator Studio]" not in payload["recall-stubs"], payload["recall-stubs"])

            calls.clear()
            second = synth.run_once(cfg, model_client=fake_model)
            expect(second["synthesized"] == 0, str(second))
            expect(calls == [], f"unchanged sources should not call model again: {calls}")

            (root / "vault" / "Research" / "Horizon protocol notes.md").write_text(
                "# Horizon protocol\nUpdated privacy preserving distributed systems notes.\n",
                encoding="utf-8",
            )
            third = synth.run_once(cfg, model_client=fake_model)
            expect(third["synthesized"] == 1, str(third))
            expect(calls == ["vault:Research"], f"only the changed vault folder should be re-synthesized: {calls}")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_memory_synthesizer_source_signature_uses_file_content_hash() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        write_config(config_path, base_config(root))
        old_env = os.environ.copy()
        os.environ.update(base_config(root))
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            folder = root / "vault" / "Same Size"
            folder.mkdir(parents=True)
            note = folder / "note.md"
            note.write_text("Alpha-1111\n", encoding="utf-8")
            os.utime(note, (1_700_000_000, 1_700_000_000))
            with control.connect_db(cfg) as conn:
                settings = synth.load_settings(cfg)
                first = synth.build_candidates(conn, cfg, settings)
                first_candidate = next(candidate for candidate in first if candidate.source_key == "Same Size")
                first_signature = first_candidate.source_signature
                first_fingerprint = str(first_candidate.payload.get("fingerprint_hash") or "")

                note.write_text("Beta--2222\n", encoding="utf-8")
                os.utime(note, (1_700_000_000, 1_700_000_000))
                second = synth.build_candidates(conn, cfg, settings)
                second_candidate = next(candidate for candidate in second if candidate.source_key == "Same Size")

                expect(second_candidate.source_signature != first_signature, second_candidate.payload)
                expect(str(second_candidate.payload.get("fingerprint_hash") or "") != first_fingerprint, second_candidate.payload)
            print("PASS test_memory_synthesizer_source_signature_uses_file_content_hash")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_memory_synthesizer_local_fallback_runs_without_llm_config() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        values = local_fallback_config(root)
        write_config(config_path, values)
        old_env = os.environ.copy()
        os.environ.update(values)
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            with control.connect_db(cfg) as conn:
                insert_agent(conn, root)
                seed_sources(root, conn)
                control.reload_vault_definitions(conn, cfg)
                conn.execute("DELETE FROM notification_outbox")
                conn.commit()

            settings = synth.load_settings(cfg)
            expect(settings.enabled is True, str(settings))
            expect(settings.model == synth.LOCAL_FALLBACK_MODEL, str(settings))
            expect(settings.endpoint == "", str(settings))
            result = synth.run_once(cfg)
            expect(result["status"] == "ok", str(result))
            expect(result["model"] == synth.LOCAL_FALLBACK_MODEL, str(result))
            expect(result["synthesized"] >= 4, str(result))
            expect(result["failed"] == 0, str(result))

            with control.connect_db(cfg) as conn:
                card_rows = conn.execute(
                    "SELECT source_kind, source_key, card_json, card_text FROM memory_synthesis_cards WHERE status = 'ok'"
                ).fetchall()
                expect(len(card_rows) >= 4, f"expected local fallback cards, got {len(card_rows)}")
                card_text = "\n".join(str(row["card_text"] or "") for row in card_rows)
                expect("Local fallback found" in card_text, card_text)
                expect("Confidence: low." in card_text, card_text)
                expect("Trust score: 0.40." in card_text, card_text)
                expect("off-vault private note" not in card_text, card_text)
                parsed_cards = [json.loads(str(row["card_json"] or "{}")) for row in card_rows]
                expect(all(card.get("confidence") == "low" for card in parsed_cards), parsed_cards)
                expect(all(card.get("trust_score") == 0.4 for card in parsed_cards), parsed_cards)
                expect(any("Creator Studio" in (card.get("retrieval_queries") or []) for card in parsed_cards), parsed_cards)
                payload = control.build_managed_memory_payload(conn, cfg, agent_id="agent-test")
                expect("Semantic synthesis cards:" in payload["recall-stubs"], payload["recall-stubs"])
                expect("Compact recall hints only" in payload["recall-stubs"], payload["recall-stubs"])
                expect("[vault:Research]" in payload["recall-stubs"], payload["recall-stubs"])
            print("PASS test_memory_synthesizer_local_fallback_runs_without_llm_config")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_memory_synthesizer_notion_paths_stay_inside_index_root() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config" / "arclink.env"
        values = base_config(root)
        notion_root = root / "state" / "notion-index" / "markdown"
        values["ARCLINK_NOTION_INDEX_MARKDOWN_DIR"] = str(notion_root)
        write_config(config_path, values)
        old_env = os.environ.copy()
        os.environ.update(values)
        os.environ["ARCLINK_CONFIG_FILE"] = str(config_path)
        try:
            cfg = control.Config.from_env()
            safe = synth._safe_notion_markdown_path(cfg, "root-1/page.md")
            expect(safe == notion_root / "root-1" / "page.md", str(safe))
            outside_state = synth._safe_notion_markdown_path(cfg, str(root / "state" / "other" / "page.md"))
            expect(outside_state is None, str(outside_state))
            escaped = synth._safe_notion_markdown_path(cfg, "../other/page.md")
            expect(escaped is None, str(escaped))
            print("PASS test_memory_synthesizer_notion_paths_stay_inside_index_root")
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def main() -> int:
    test_memory_synthesizer_caches_cards_and_injects_recall_stubs()
    test_memory_synthesizer_source_signature_uses_file_content_hash()
    test_memory_synthesizer_local_fallback_runs_without_llm_config()
    test_memory_synthesizer_notion_paths_stay_inside_index_root()
    print("PASS all 4 memory synthesizer tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
